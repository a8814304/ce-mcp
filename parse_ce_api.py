#!/usr/bin/env python3
"""Parse CE Lua _G enumeration output and categorize all functions."""
import json

INPUT = r"C:\Users\admin\.zcode\v2\acp-config\claude\1d56a544003a\projects\C--Users-admin-ZCodeProject\74555da5-c040-4144-8580-9b38154a547b\tool-results\mcp-ce-mcp-ce_lua_execute-1783753925852.txt"

with open(INPUT, encoding='utf-8') as f:
    outer = json.load(f)

inner = json.loads(outer[0]["text"])
text = inner["data"]["output"]
lines = text.split("\n")

# Extract function list
func_start, obj_start = None, None
for i, line in enumerate(lines):
    s = line.strip()
    if s == "== Functions ==":
        func_start = i + 1
    elif s == "== Objects ==":
        obj_start = i + 1

funcs = [l.strip() for l in lines[func_start:obj_start-1] if l.strip()] if func_start and obj_start else []
objs = [l.strip() for l in lines[obj_start:] if l.strip()] if obj_start else []

# Category definitions: (name, keywords)
CATEGORIES = [
    ("内存读写", ["read", "write", "rewrit", "readand", "reador", "readxor"]),
    ("扫描搜索", ["aobscan", "scan", "found", "memscan"]),
    ("进程/模块", ["process", "module", "kernel", "inject", "dll", "opensprocess"]),
    ("地址列表", ["addresslist", "memoryrecord"]),
    ("反汇编/汇编", ["assemble", "disassemble", "opcode", "autoassembl"]),
    ("代码注入/内存分配", ["alloc", "freez", "inject", "hook", "patch"]),
    ("字节表/数据转换", ["byte", "bswap", "wordto", "dwordto", "qwordto", "doubleto", "floatto", "bytetable"]),
    ("窗体/控件", ["form_", "button_", "checkbox_", "combobox_", "control_", "component_", "panel_", "splitter_", "tabsheet_", "radiogroup_", "mainmenu_", "popupmenu_", "label_", "memo_", "groupbox_", "toolbar_", "statusbar_", "progressbar_", "trackbar_", "scrollbox_", "pagecontrol_", "notebook_"]),
    ("树/列表视图", ["treeview", "listview", "listcolumn", "listitem", "treenode", "treeitems"]),
    ("Lua钩子/类系统", ["luahook", "luacode", "lua_", "registerclass", "registerlua"]),
    ("数学/位运算", ["band", "bnot", "bor", "bshl", "bshr", "bxor", "ceil", "floor", "round", "sqrt", "sin", "cos", "tan", "log", "exp", "pow", "abs", "max", "min", "random", "pi"]),
    ("字符串/编码", ["stringto", "utf8", "utf16", "ansi", "encode", "decode", "widestring", "translate"]),
    ("文件/IO", ["fileexists", "createfile", "loadtable", "savetable", "loadlibrary", "getcheatfolder", "getcurrentdir"]),
    ("画布/绘图", ["canvas", "pixel", "gradient", "draw", "pen", "brush", "font", "ellipse", "rect", "floodfill"]),
    ("定时器/时间", ["timer", "thread", "sleep", "synchronize", "timet", "gettickcount", "now", "date", "calendar"]),
    ("调试/异常", ["debug", "exception", "errorlog", "getcrashmap", "onprojectexception"]),
    ("符号/反编译", ["symbol", "dissect", "pseudocode", "decompile", "getstructure", "getenum", "mono", "dotnet", "java"]),
    ("网络", ["socket", "http", "inet", "net", "server", "client", "url", "web"]),
    ("系统/信息", ["getceversion", "cheatengineis", "cpuid", "beep", "checksynchronize", "checkversion", "connect", "getglobal", "getarchitecture", "speedhack", "version", "configuration", "findwindow"]),
    ("对话框/消息", ["showmessage", "messagedialog", "input", "question", "opendialog", "save", "color", "fontdialog"]),
    ("多线程/同步", ["createevent", "createcrit", "setevent", "resetevent", "waitfor", "lock", "unlock", "interlocked"]),
    ("其他", []),
]

def categorize(funcs):
    result = {k: [] for k, _ in CATEGORIES}
    used = set()
    for cat_name, keywords in CATEGORIES:
        for f in funcs:
            fl = f.lower()
            if any(kw in fl for kw in keywords):
                result[cat_name].append(f)
                used.add(f)
    remaining = [f for f in funcs if f not in used]
    result["其他"] = remaining
    return result

cats = categorize(funcs)
non_empty = [(k, v) for k, v in cats.items() if v]
non_empty.sort(key=lambda x: -len(x[1]))

total = sum(len(v) for _, v in non_empty)
print(f"CE Lua API 枚举结果")
print(f"{'='*60}")
print(f"_G 全局条目总数: 3444")
print(f"全局函数: {len(funcs)}")
print(f"全局对象/表: {len(objs)}")
print(f"可分类函数: {total}")
print()

for cat_name, items in non_empty:
    s = sorted(items)
    if len(s) <= 30:
        print(f"## {cat_name} ({len(s)} 个)")
        for it in s:
            print(f"    {it}")
    else:
        print(f"## {cat_name} ({len(s)} 个)")
        for it in s[:15]:
            print(f"    {it}")
        print(f"    ... (中间省略 {len(s)-30} 个)")
        for it in s[-15:]:
            print(f"    {it}")
    print()

print(f"=== Objects/Tables ({len(objs)}) ===")
for o in sorted(objs):
    print(f"    {o}")
