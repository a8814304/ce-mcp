# CE-MCP — Cheat Engine MCP Server (纯 Python / 零依赖)

让 AI（Claude Desktop、VS Code Copilot、Cursor 等任意 MCP 客户端）直接操控 Cheat Engine：
进程附加、内存扫描、内存读写、地址列表、变速、Lua/Auto Assembler 执行、CT 表管理。

## 特点

- **纯 Python 标准库实现**，无任何外部依赖，无需编译，无需 .NET / Visual Studio
- **标准 MCP 协议**（stdio 传输），任何 MCP 客户端开箱即用
- **文件 IPC 桥接**：CE 侧只需一个 autorun Lua 脚本，兼容 CE 7.x（无需 7.6.2+ 插件 API）
- **29 个工具，9 大模块**：进程管理 / 首次·再次扫描 / AOB 特征码 / 内存读写(含批量·冻结) / 地址列表 / SpeedHack / Lua 执行 / 汇编·反汇编 / CT 文件

## 架构

```
MCP 客户端 (Claude 等)
   │ stdio (JSON-RPC / MCP)
ce_mcp_server.py (Python)
   │ 文件 IPC: c_X.txt(命令) → go.txt(触发) → r_X.txt(结果) → d_X.txt(完成)
autorun/ce_mcp.lua (CE 内 200ms 定时器轮询)
   │ CE Lua API
Cheat Engine → 目标进程
```

## 安装

1. 把 `autorun/ce_mcp.lua` 复制到 Cheat Engine 安装目录的 `autorun\` 文件夹
2. （可选）复制 `config.example.json` 为 `config.json` 并按本机路径修改：
   ```json
   {
     "ce_exe": "C:\\Program Files\\Cheat Engine 7.5\\cheatengine-x86_64.exe",
     "ipc_dir": "C:\\Program Files\\Cheat Engine 7.5\\ce-mcp\\ipc"
   }
   ```
   - `ipc_dir` 必须与 Lua 端一致。Lua 端默认使用 `<CE目录>\ce-mcp\ipc\`；不配置时 Python 端默认使用本仓库目录下的 `ipc\`，此时请在 `ce_mcp.lua` 顶部把 `IPC_DIR` 改成相同路径
   - `ce_exe` 用于 CE 未运行时自动拉起（可省略，手动启动 CE 即可）
3. 启动 Cheat Engine（autorun 自动加载桥接脚本）
4. 在 MCP 客户端中配置本服务器，例如 Claude Desktop `claude_desktop_config.json`：
   ```json
   {
     "mcpServers": {
       "cheat-engine": {
         "command": "python",
         "args": ["X:\\path\\to\\ce-mcp\\ce_mcp_server.py"]
       }
     }
   }
   ```

要求：Windows + Python 3.8+ + Cheat Engine 7.x。

## 工具一览

| 模块 | 工具 |
|------|------|
| 进程管理 | `ce_process_list` `ce_process_open` `ce_process_close` `ce_process_info` `ce_process_modules` |
| 内存扫描 | `ce_scan_first` `ce_scan_next` `ce_scan_results` `ce_scan_reset` `ce_scan_aob` |
| 内存读写 | `ce_memory_read` `ce_memory_write` `ce_memory_read_batch` `ce_memory_write_batch` `ce_memory_freeze` |
| 地址列表 | `ce_addresslist_add` `ce_addresslist_remove` `ce_addresslist_list` `ce_addresslist_update` `ce_addresslist_clear` |
| 变速控制 | `ce_speedhack_enable` `ce_speedhack_disable` |
| Lua 执行 | `ce_lua_execute` |
| 汇编注入 | `ce_autoasm_execute` `ce_disassemble` |
| CT 文件 | `ce_ct_load` `ce_ct_save` |
| 系统状态 | `ce_status` `ce_version` |

## 测试

CE 运行且 autorun 脚本加载后：

```powershell
python tests\test_all_tools.py
```

历史测试报告见 [docs/TEST_REPORT.md](docs/TEST_REPORT.md)（其中记录的 4 个 Bug 已在当前版本修复）。

## 与同类项目的区别

- [ShadowNineX/ce-mcp](https://github.com/ShadowNineX/ce-mcp)：C# 插件 DLL + HTTP MCP，需 CE 7.6.2+ 与 .NET 10 运行时
- [Eruditi/CE-MCP-Plugin](https://github.com/Eruditi/CE-MCP-Plugin)：C 插件 + 自定义 TCP 协议（非 MCP）
- 本项目：纯 Python + stdio 标准 MCP + 文件 IPC，零依赖零编译，安装门槛最低

## 免责声明

本项目仅用于学习、研究与单机环境调试。请勿用于在线游戏或任何违反服务条款/法律法规的用途，后果自负。

## License

MIT
