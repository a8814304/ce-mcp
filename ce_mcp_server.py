#!/usr/bin/env python3
"""
CE MCP Server v2.0 - Cheat Engine MCP Server
通过文件 IPC 与 CE Lua 通信，实现完整的 MCP 工具集
协议: c_X.txt(命令) -> go.txt(触发) -> r_X.txt(结果) -> d_X.txt(完成)

用法: python ce_mcp_server.py
依赖: Python 3.8+ 标准库（无外部依赖）
"""

import json
import sys
import os
import time
import random
import string
import subprocess
import threading
import struct
import re

# ============================================================
# 配置
# ============================================================

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))


def _load_config():
    cfg_path = os.path.join(SCRIPT_DIR, "config.json")
    cfg = {}
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, 'r', encoding='utf-8') as f:
                cfg = json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            print(f"[ce-mcp] config.json load failed: {e}", file=sys.stderr)
    return cfg


_CFG = _load_config()

IPC_DIR = _CFG.get("ipc_dir") or os.path.join(SCRIPT_DIR, "ipc")
os.makedirs(IPC_DIR, exist_ok=True)

CE_EXE = _CFG.get("ce_exe") or r"C:\Program Files\Cheat Engine 7.5\cheatengine-x86_64.exe"

# MCP 协议版本
MCP_PROTOCOL_VERSION = "2024-11-05"

# 默认超时
DEFAULT_TIMEOUT = 15.0
SCAN_TIMEOUT = 60.0


# ============================================================
# CE 桥接层
# ============================================================

class CEBridge:
    """通过文件 IPC 与 CE Lua 通信"""

    def __init__(self):
        self._proc = None
        self._lock = threading.Lock()

    def ensure_running(self):
        """确保 CE 进程正在运行"""
        # 通过进程名检测（最可靠）
        try:
            import subprocess as sp
            for exe in ('myce-x86_64.exe', 'myce.exe', 'cheatengine-x86_64.exe', 'cheatengine.exe'):
                r = sp.run(['tasklist', '/FI', f'IMAGENAME eq {exe}', '/NH'],
                           capture_output=True, text=True, timeout=5)
                if exe.lower() in r.stdout.lower():
                    return True
        except Exception:
            pass

        # 通过窗口标题检测
        try:
            import ctypes
            for title in ("Cheat Engine 7.5", "Cheat Engine 7.4", "Cheat Engine 7.3",
                          "Cheat Engine", "My Cheat Engine"):
                if ctypes.windll.user32.FindWindowW(None, title):
                    return True
        except Exception:
            pass
        
        # 尝试启动 CE
        if self._proc and self._proc.poll() is None:
            return True
        try:
            self._proc = subprocess.Popen(
                [CE_EXE], cwd=os.path.dirname(CE_EXE),
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
            )
            time.sleep(3)
            return True
        except (FileNotFoundError, OSError) as e:
            # 启动失败（可能需要管理员权限），但 CE 可能已经在运行
            # 检查 IPC 是否有响应来判断
            return self._test_ipc()
    
    def _test_ipc(self):
        """通过 IPC 测试 CE 是否在响应"""
        try:
            cmd_id = 'ping_' + ''.join(random.choices(string.ascii_lowercase, k=4))
            cmd_path = os.path.join(IPC_DIR, f"c_{cmd_id}.txt")
            n_path = os.path.join(IPC_DIR, "n.txt")
            go_path = os.path.join(IPC_DIR, "go.txt")
            res_path = os.path.join(IPC_DIR, f"r_{cmd_id}.txt")
            done_path = os.path.join(IPC_DIR, f"d_{cmd_id}.txt")
            
            # UTF8 without BOM
            with open(cmd_path, 'w', encoding='utf-8-sig') as f:
                pass  # utf-8-sig strips BOM on write? No, it adds it.
            # Use plain utf-8
            import io
            for p in [done_path, res_path]:
                try: os.remove(p)
                except: pass
            
            with open(cmd_path, 'w', encoding='utf-8') as f:
                f.write('{"cmd":"status","args":{}}')
            with open(n_path, 'w', encoding='utf-8') as f:
                f.write(cmd_id)
            with open(go_path, 'w', encoding='utf-8') as f:
                f.write('')
            
            time.sleep(2)
            if os.path.exists(done_path):
                try: os.remove(done_path)
                except: pass
                try: os.remove(res_path)
                except: pass
                try: os.remove(cmd_path)
                except: pass
                return True
            return False
        except Exception:
            return False

    def send(self, lua_code: str, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """发送 Lua 代码到 CE 执行，等待返回 JSON 结果"""
        with self._lock:
            cmd_id = ''.join(random.choices(string.ascii_lowercase + string.digits, k=8))
            cmd_path = os.path.join(IPC_DIR, f"c_{cmd_id}.txt")
            n_path = os.path.join(IPC_DIR, "n.txt")
            go_path = os.path.join(IPC_DIR, "go.txt")
            res_path = os.path.join(IPC_DIR, f"r_{cmd_id}.txt")
            done_path = os.path.join(IPC_DIR, f"d_{cmd_id}.txt")

            # 清理可能存在的旧文件
            for p in [done_path, res_path]:
                try:
                    os.remove(p)
                except OSError:
                    pass

            # 写命令文件
            with open(cmd_path, 'w', encoding='utf-8') as f:
                f.write(lua_code)

            # 写命令 ID
            with open(n_path, 'w', encoding='utf-8') as f:
                f.write(cmd_id)

            # 写触发文件（deleteFile 检测，不锁文件）
            with open(go_path, 'w') as f:
                f.write('')

            # 等待结果
            deadline = time.time() + timeout
            while time.time() < deadline:
                if os.path.exists(done_path):
                    try:
                        with open(res_path, 'r', encoding='utf-8') as f:
                            content = f.read().strip()
                        result = json.loads(content) if content else {"ok": False, "error": "Empty response"}
                    except (json.JSONDecodeError, IOError) as e:
                        result = {"ok": False, "error": f"Parse error: {e}"}
                    finally:
                        for p in [done_path, res_path, cmd_path]:
                            try:
                                os.remove(p)
                            except OSError:
                                pass
                    return result
                time.sleep(0.03)

            # 超时清理
            for p in [cmd_path, go_path, done_path, res_path]:
                try:
                    os.remove(p)
                except OSError:
                    pass
            
            # speedhack 等阻塞型操作超时后，CE 定时器可能已卡死
            # 尝试检测 CE 是否仍可响应
            timeout_msg = f"Timeout after {timeout}s"
            if timeout <= 5.0:
                timeout_msg += " (可能 CE 内部函数阻塞导致定时器卡死，建议重启 CE)"
            return {"ok": False, "error": {"code": "TIMEOUT", "message": timeout_msg}}

    def call(self, cmd: str, args: dict = None, timeout: float = DEFAULT_TIMEOUT) -> dict:
        """调用 CE 端处理器"""
        # 构造 Lua 表达式格式的命令
        # CE 端 parseJSON 会 load('return ' + json)，所以直接发送 JSON
        msg = json.dumps({"cmd": cmd, "args": args or {}}, ensure_ascii=False)
        return self.send(msg, timeout)


# ============================================================
# MCP Server
# ============================================================

class MCPServer:
    def __init__(self, ce: CEBridge):
        self.ce = ce
        self._running = True
        self.tools = self._define_tools()

    def _define_tools(self):
        """定义所有 MCP 工具"""
        tools = []

        # ---- 模块一：进程管理 ----
        tools.append({
            "name": "ce_process_list",
            "description": "枚举系统进程列表。可选 filter 参数模糊匹配进程名。",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "进程名过滤关键词（模糊匹配）"}
                }
            }
        })
        tools.append({
            "name": "ce_process_open",
            "description": "附加到目标进程（通过 PID 或进程名）",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "pid": {"type": "integer", "description": "目标进程 PID"},
                    "process_name": {"type": "string", "description": "目标进程名称"}
                }
            }
        })
        tools.append({
            "name": "ce_process_close",
            "description": "断开与当前目标进程的连接",
            "inputSchema": {"type": "object", "properties": {}}
        })
        tools.append({
            "name": "ce_process_info",
            "description": "返回当前已附加进程的详细信息",
            "inputSchema": {"type": "object", "properties": {}}
        })
        tools.append({
            "name": "ce_process_modules",
            "description": "获取目标进程加载的所有模块（DLL）信息",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "filter": {"type": "string", "description": "模块名过滤关键词"}
                }
            }
        })

        # ---- 模块二：内存扫描 ----
        tools.append({
            "name": "ce_scan_first",
            "description": "对目标进程内存进行首次扫描",
            "inputSchema": {
                "type": "object",
                "required": ["value_type", "scan_type"],
                "properties": {
                    "value_type": {"type": "string", "enum": ["byte", "int16", "int32", "int64", "float32", "float64", "string", "bytes"]},
                    "scan_type": {"type": "string", "enum": ["exact", "unknown", "between", "greater_than", "less_than"]},
                    "value": {"type": "string", "description": "目标值（exact 模式必填）"},
                    "value2": {"type": "string", "description": "范围扫描的上界（between 模式）"},
                    "start_address": {"type": "string", "description": "扫描起始地址（十六进制）"},
                    "end_address": {"type": "string", "description": "扫描结束地址（十六进制）"},
                    "hex": {"type": "boolean", "description": "value 是否为十六进制"},
                    "string_type": {"type": "string", "enum": ["ascii", "utf8", "utf16"]},
                    "writable": {"type": "boolean", "description": "是否只扫描可写内存"}
                }
            }
        })
        tools.append({
            "name": "ce_scan_next",
            "description": "在已有扫描结果基础上进行二次筛选扫描",
            "inputSchema": {
                "type": "object",
                "required": ["scan_type"],
                "properties": {
                    "scan_type": {"type": "string", "enum": ["exact", "increased", "decreased", "changed", "unchanged", "greater_than", "less_than", "between"]},
                    "value": {"type": "string", "description": "目标值"},
                    "value2": {"type": "string", "description": "范围上界（between 模式）"},
                    "hex": {"type": "boolean", "description": "value 是否为十六进制"}
                }
            }
        })
        tools.append({
            "name": "ce_scan_results",
            "description": "返回当前扫描结果列表",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": 100, "maximum": 1000}
                }
            }
        })
        tools.append({
            "name": "ce_scan_reset",
            "description": "清空当前扫描结果，准备新一轮扫描",
            "inputSchema": {"type": "object", "properties": {}}
        })
        tools.append({
            "name": "ce_scan_aob",
            "description": "通过字节数组特征码（AOB）搜索内存，支持通配符 ??",
            "inputSchema": {
                "type": "object",
                "required": ["pattern"],
                "properties": {
                    "pattern": {"type": "string", "description": "特征码，如 '48 8B ?? 05'"},
                    "module_name": {"type": "string", "description": "限定搜索的模块名"},
                    "start_address": {"type": "string"},
                    "end_address": {"type": "string"}
                }
            }
        })

        # ---- 模块三：内存读写 ----
        tools.append({
            "name": "ce_memory_read",
            "description": "从指定地址读取指定类型的数据",
            "inputSchema": {
                "type": "object",
                "required": ["address", "value_type"],
                "properties": {
                    "address": {"type": "string", "description": "内存地址（十六进制或 CE 地址表达式）"},
                    "value_type": {"type": "string", "enum": ["byte", "int16", "int32", "int64", "float32", "float64", "string", "bytes"]},
                    "length": {"type": "integer", "description": "读取长度（bytes/string 类型）"}
                }
            }
        })
        tools.append({
            "name": "ce_memory_write",
            "description": "向指定地址写入指定类型的数据",
            "inputSchema": {
                "type": "object",
                "required": ["address", "value_type", "value"],
                "properties": {
                    "address": {"type": "string", "description": "内存地址"},
                    "value_type": {"type": "string", "enum": ["byte", "int16", "int32", "int64", "float32", "float64", "string", "bytes"]},
                    "value": {"type": "string", "description": "要写入的值"},
                    "hex": {"type": "boolean", "description": "value 是否为十六进制"}
                }
            }
        })
        tools.append({
            "name": "ce_memory_read_batch",
            "description": "一次性读取多个地址的数据",
            "inputSchema": {
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "array", "maxItems": 100,
                        "items": {
                            "type": "object",
                            "required": ["address", "value_type"],
                            "properties": {
                                "address": {"type": "string"},
                                "value_type": {"type": "string", "enum": ["byte", "int16", "int32", "int64", "float32", "float64", "string", "bytes"]},
                                "length": {"type": "integer"}
                            }
                        }
                    }
                }
            }
        })
        tools.append({
            "name": "ce_memory_write_batch",
            "description": "一次性写入多个地址的数据",
            "inputSchema": {
                "type": "object",
                "required": ["items"],
                "properties": {
                    "items": {
                        "type": "array", "maxItems": 100,
                        "items": {
                            "type": "object",
                            "required": ["address", "value_type", "value"],
                            "properties": {
                                "address": {"type": "string"},
                                "value_type": {"type": "string", "enum": ["byte", "int16", "int32", "int64", "float32", "float64", "string", "bytes"]},
                                "value": {"type": "string"}
                            }
                        }
                    }
                }
            }
        })
        tools.append({
            "name": "ce_memory_freeze",
            "description": "冻结/解冻指定地址的值（持续写回）",
            "inputSchema": {
                "type": "object",
                "required": ["address", "value_type", "value", "action"],
                "properties": {
                    "address": {"type": "string"},
                    "value_type": {"type": "string", "enum": ["byte", "int16", "int32", "int64", "float32", "float64", "string", "bytes"]},
                    "value": {"type": "string"},
                    "action": {"type": "string", "enum": ["freeze", "unfreeze"]},
                    "description": {"type": "string", "description": "记录描述"}
                }
            }
        })

        # ---- 模块四：地址列表管理 ----
        tools.append({
            "name": "ce_addresslist_add",
            "description": "将地址添加到 CE 地址列表",
            "inputSchema": {
                "type": "object",
                "required": ["address", "value_type"],
                "properties": {
                    "address": {"type": "string"},
                    "value_type": {"type": "string", "enum": ["byte", "int16", "int32", "int64", "float32", "float64", "string", "bytes"]},
                    "description": {"type": "string"},
                    "value": {"type": "string"}
                }
            }
        })
        tools.append({
            "name": "ce_addresslist_remove",
            "description": "从地址列表中删除指定记录",
            "inputSchema": {
                "type": "object",
                "required": ["id"],
                "properties": {"id": {"type": "integer"}}
            }
        })
        tools.append({
            "name": "ce_addresslist_list",
            "description": "返回当前 CE 地址列表中的所有记录",
            "inputSchema": {
                "type": "object",
                "properties": {
                    "offset": {"type": "integer", "default": 0},
                    "limit": {"type": "integer", "default": 100}
                }
            }
        })
        tools.append({
            "name": "ce_addresslist_update",
            "description": "修改地址列表中指定记录的属性",
            "inputSchema": {
                "type": "object",
                "required": ["id"],
                "properties": {
                    "id": {"type": "integer"},
                    "description": {"type": "string"},
                    "value": {"type": "string"},
                    "frozen": {"type": "boolean"}
                }
            }
        })
        tools.append({
            "name": "ce_addresslist_clear",
            "description": "清空 CE 地址列表中的所有记录",
            "inputSchema": {"type": "object", "properties": {}}
        })

        # ---- 模块五：变速控制 ----
        tools.append({
            "name": "ce_speedhack_enable",
            "description": "启用 SpeedHack 并设置速度倍率",
            "inputSchema": {
                "type": "object",
                "required": ["speed"],
                "properties": {
                    "speed": {"type": "number", "description": "速度倍率（0.01~100）", "minimum": 0.01, "maximum": 100}
                }
            }
        })
        tools.append({
            "name": "ce_speedhack_disable",
            "description": "禁用 SpeedHack",
            "inputSchema": {"type": "object", "properties": {}}
        })

        # ---- 模块六：Lua 脚本执行 ----
        tools.append({
            "name": "ce_lua_execute",
            "description": "在 CE 中执行任意 Lua 脚本",
            "inputSchema": {
                "type": "object",
                "required": ["script"],
                "properties": {
                    "script": {"type": "string", "description": "Lua 脚本代码"},
                    "timeout_ms": {"type": "integer", "default": 5000}
                }
            }
        })

        # ---- 模块七：汇编与注入 ----
        tools.append({
            "name": "ce_autoasm_execute",
            "description": "执行 Auto Assembler 汇编脚本",
            "inputSchema": {
                "type": "object",
                "required": ["script"],
                "properties": {
                    "script": {"type": "string", "description": "Auto Assembler 脚本内容"}
                }
            }
        })
        tools.append({
            "name": "ce_disassemble",
            "description": "反汇编指定地址的指令",
            "inputSchema": {
                "type": "object",
                "required": ["address"],
                "properties": {
                    "address": {"type": "string"},
                    "count": {"type": "integer", "default": 10}
                }
            }
        })

        # ---- 模块八：CT 文件管理 ----
        tools.append({
            "name": "ce_ct_load",
            "description": "加载 Cheat Table (.CT) 文件",
            "inputSchema": {
                "type": "object",
                "required": ["path"],
                "properties": {
                    "path": {"type": "string"},
                    "merge": {"type": "boolean", "default": False}
                }
            }
        })
        tools.append({
            "name": "ce_ct_save",
            "description": "保存当前地址列表到 .CT 文件",
            "inputSchema": {
                "type": "object",
                "required": ["path"],
                "properties": {"path": {"type": "string"}}
            }
        })

        # ---- 模块九：系统与状态 ----
        tools.append({
            "name": "ce_status",
            "description": "返回 CE 当前运行状态（健康检查）",
            "inputSchema": {"type": "object", "properties": {}}
        })
        tools.append({
            "name": "ce_version",
            "description": "返回 Cheat Engine 版本信息",
            "inputSchema": {"type": "object", "properties": {}}
        })

        return tools

    # ============================================================
    # MCP 协议处理
    # ============================================================

    def _send(self, msg):
        sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
        sys.stdout.flush()

    def _read(self):
        line = sys.stdin.readline()
        if not line:
            return None
        line = line.strip()
        if not line:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    def _ok(self, msg_id, result):
        self._send({
            "jsonrpc": "2.0", "id": msg_id,
            "result": {
                "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
            }
        })

    def _err(self, msg_id, code, message):
        self._send({
            "jsonrpc": "2.0", "id": msg_id,
            "error": {"code": code, "message": message}
        })

    # ============================================================
    # 工具调用路由
    # ============================================================

    # 工具名到 CE 命令的映射
    TOOL_MAP = {
        "ce_process_list":      ("process_list",       DEFAULT_TIMEOUT),
        "ce_process_open":      ("process_open",       DEFAULT_TIMEOUT),
        "ce_process_close":     ("process_close",      DEFAULT_TIMEOUT),
        "ce_process_info":      ("process_info",       DEFAULT_TIMEOUT),
        "ce_process_modules":   ("process_modules",    DEFAULT_TIMEOUT),
        "ce_scan_first":        ("scan_first",         SCAN_TIMEOUT),
        "ce_scan_next":         ("scan_next",          SCAN_TIMEOUT),
        "ce_scan_results":      ("scan_results",       DEFAULT_TIMEOUT),
        "ce_scan_reset":        ("scan_reset",         DEFAULT_TIMEOUT),
        "ce_scan_aob":          ("scan_aob",           SCAN_TIMEOUT),
        "ce_memory_read":       ("memory_read",        DEFAULT_TIMEOUT),
        "ce_memory_write":      ("memory_write",       DEFAULT_TIMEOUT),
        "ce_memory_read_batch": ("memory_read_batch",  DEFAULT_TIMEOUT),
        "ce_memory_write_batch":("memory_write_batch", DEFAULT_TIMEOUT),
        "ce_memory_freeze":     ("memory_freeze",      DEFAULT_TIMEOUT),
        "ce_addresslist_add":   ("addresslist_add",    DEFAULT_TIMEOUT),
        "ce_addresslist_remove":("addresslist_remove", DEFAULT_TIMEOUT),
        "ce_addresslist_list":  ("addresslist_list",   DEFAULT_TIMEOUT),
        "ce_addresslist_update":("addresslist_update", DEFAULT_TIMEOUT),
        "ce_addresslist_clear": ("addresslist_clear",  DEFAULT_TIMEOUT),
        "ce_speedhack_enable":  ("speedhack_enable",   3.0),
        "ce_speedhack_disable": ("speedhack_disable",  3.0),
        "ce_lua_execute":       ("lua_execute",        30.0),
        "ce_autoasm_execute":   ("autoasm_execute",    30.0),
        "ce_disassemble":       ("disassemble",        DEFAULT_TIMEOUT),
        "ce_ct_load":           ("ct_load",            DEFAULT_TIMEOUT),
        "ce_ct_save":           ("ct_save",            DEFAULT_TIMEOUT),
        "ce_status":            ("status",             5.0),
        "ce_version":           ("version",            5.0),
    }

    def _call_tool(self, name, args):
        """调用 CE 工具"""
        if name not in self.TOOL_MAP:
            raise ValueError(f"Unknown tool: {name}")

        cmd, timeout = self.TOOL_MAP[name]

        # lua_execute 特殊处理：参数名映射
        if name == "ce_lua_execute":
            args = {"code": args.get("script", ""), "timeout_ms": args.get("timeout_ms", 5000)}

        result = self.ce.call(cmd, args, timeout=timeout)

        if not result.get("ok", False):
            err = result.get("error", {})
            if isinstance(err, str):
                return {"success": False, "error": {"code": "CE_ERROR", "message": err}}
            return {"success": False, "error": err}

        # 去掉 ok 字段，用 success 替代
        data = {k: v for k, v in result.items() if k != "ok"}
        return {"success": True, "data": data, "error": None}

    # ============================================================
    # 主循环
    # ============================================================

    def run(self):
        print("CE-MCP Server v2.0 started", file=sys.stderr, flush=True)

        while self._running:
            msg = self._read()
            if msg is None:
                break

            method = msg.get("method", "")
            msg_id = msg.get("id")

            if method == "initialize":
                self._send({
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {
                        "protocolVersion": MCP_PROTOCOL_VERSION,
                        "capabilities": {"tools": {}},
                        "serverInfo": {"name": "ce-mcp", "version": "2.0.0"}
                    }
                })

            elif method == "notifications/initialized":
                pass

            elif method == "tools/list":
                self._send({
                    "jsonrpc": "2.0", "id": msg_id,
                    "result": {"tools": self.tools}
                })

            elif method == "tools/call":
                params = msg.get("params", {})
                name = params.get("name", "")
                args = params.get("arguments", {})

                try:
                    result = self._call_tool(name, args)
                    self._ok(msg_id, result)
                except Exception as e:
                    self._err(msg_id, -32000, str(e))

            elif method == "ping":
                self._send({"jsonrpc": "2.0", "id": msg_id, "result": {}})

            else:
                if msg_id is not None:
                    self._err(msg_id, -32601, f"Unknown method: {method}")

        print("CE-MCP stopped", file=sys.stderr)


# ============================================================
# 入口
# ============================================================

if __name__ == "__main__":
    server = MCPServer(CEBridge())
    try:
        server.run()
    except KeyboardInterrupt:
        pass
