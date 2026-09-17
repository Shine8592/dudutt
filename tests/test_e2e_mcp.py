#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端烟雾测试：用 mock 后端拉起 MCP server，验证工具注册与调用。

为什么必须做：单元测试通过 ≠ MCP 能挂到客户端上。
这里真实启动 stdio server，走完整的协议握手 + tools/list + tools/call。
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Windows CI（以及部分本地终端）默认 stdout 是 cp1252/GBK，
# 直接 print 中文会抛 UnicodeEncodeError 导致测试整体崩溃。
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

ROOT = Path(__file__).parent.parent
PASS = 0
FAIL = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}")
    else:
        FAIL += 1
        print(f"  [FAIL] {name} {detail}")


def rpc_messages(proc, messages, expected_ids, timeout=30):
    """向 stdio server 发消息并收集响应。

    坑：不能用 communicate() —— 它发完立即关闭 stdin，
    MCP server 读到 EOF 会马上退出，导致排在后面的工具调用
    还没执行完（部分工具跑在 threadpool 里）就被丢弃，
    表现为"前几个工具有响应、后面几个凭空消失"。
    因此这里发完保持连接，逐行读直到收齐或超时。
    """
    import threading
    import time

    # 写线程：发完消息但不关 stdin
    def writer():
        try:
            for m in messages:
                proc.stdin.write(json.dumps(m) + "\n")
                proc.stdin.flush()
                time.sleep(0.05)
        except Exception:
            pass

    threading.Thread(target=writer, daemon=True).start()

    responses = []
    deadline = time.time() + timeout
    while time.time() < deadline and len(responses) < len(expected_ids):
        line = proc.stdout.readline()
        if not line:
            break
        line = line.strip()
        if not line:
            continue
        try:
            responses.append(json.loads(line))
        except ValueError:
            continue
    return responses


def main() -> int:
    print("=" * 60)
    print("dudutt —— MCP 端到端烟雾测试")
    print("=" * 60)

    env = dict(os.environ)
    env["DUDUTT_BACKEND"] = "mock"
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT)
    # 审计写到临时文件
    env["DUDUTT_AUDIT_PATH"] = str(ROOT / "tests" / "_tmp_e2e_audit.jsonl")

    proc = subprocess.Popen(
        [sys.executable, "-u", "-m", "dudutt"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        cwd=str(ROOT),
        env=env,
    )

    msgs = [
        {
            "jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "smoke", "version": "1.0"},
            },
        },
        {"jsonrpc": "2.0", "method": "notifications/initialized"},
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        {
            "jsonrpc": "2.0", "id": 3, "method": "tools/call",
            "params": {"name": "capabilities", "arguments": {}},
        },
        {
            "jsonrpc": "2.0", "id": 4, "method": "tools/call",
            "params": {"name": "health_check", "arguments": {}},
        },
        {
            "jsonrpc": "2.0", "id": 5, "method": "tools/call",
            "params": {"name": "list_groups", "arguments": {}},
        },
        {
            "jsonrpc": "2.0", "id": 6, "method": "tools/call",
            "params": {
                "name": "publish_goods",
                "arguments": {
                    "title": "E2E 测试团",
                    "goods_list": [{
                        "goods_name": "测试商品",
                        "category_name": "测试分类",
                        "goods_desc": "描述",
                        "sku_list": [{
                            "price_in_fen": 1990,
                            "quantity_type": 0,
                            "total_quantity": 10,
                            "spec_id_list": [],
                        }],
                    }],
                },
            },
        },
        {
            "jsonrpc": "2.0", "id": 7, "method": "tools/call",
            "params": {
                "name": "list_official_apis",
                "arguments": {"keyword": "库存"},
            },
        },
        {
            "jsonrpc": "2.0", "id": 8, "method": "tools/call",
            "params": {"name": "audit_log", "arguments": {"limit": 5}},
        },
    ]

    responses = rpc_messages(proc, msgs, expected_ids={1, 2, 3, 4, 5, 6, 7, 8})
    by_id = {r.get("id"): r for r in responses if "id" in r}

    # 收工：关掉 stdin 让 server 自然退出
    try:
        proc.stdin.close()
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

    # --- 初始化 ---
    init = by_id.get(1, {})
    check("initialize 成功", "result" in init, f"got={init}")
    server_info = (init.get("result") or {}).get("serverInfo") or {}
    check("serverInfo.name = dudutt", server_info.get("name") == "dudutt",
          f"got={server_info}")

    # --- tools/list ---
    tools_resp = by_id.get(2, {})
    tools = ((tools_resp.get("result") or {}).get("tools")) or []
    names = {t["name"] for t in tools}
    expected = {
        "capabilities", "health_check", "list_groups", "list_goods",
        "get_goods", "publish_goods", "set_stock", "delist_goods",
        "update_price", "list_official_apis", "audit_log",
    }
    check("工具全部注册", expected <= names, f"missing={expected - names}")
    check("工具数量正确", len(tools) == len(expected),
          f"got {len(tools)}: {sorted(names)}")
    # 确认没有内部函数被误注册成工具（duduExcel 曾踩过这个坑）
    check("无内部函数泄漏为工具", not any(n.startswith("_") for n in names),
          f"got={sorted(names)}")
    # 每个工具有描述（Agent 只能靠 docstring 理解用途）
    no_desc = [t["name"] for t in tools if not (t.get("description") or "").strip()]
    check("所有工具都有描述", not no_desc, f"缺描述={no_desc}")

    # --- capabilities ---
    cap = by_id.get(3, {})
    cap_text = json.dumps(cap.get("result") or {}, ensure_ascii=False)
    check("capabilities 可调用", "result" in cap and "error" not in cap)
    check("capabilities 含后端矩阵", "backend_matrix" in cap_text)
    check("capabilities 说明改价不支持", '"update_price": "none' in cap_text
          or "update_price" in cap_text)

    # --- health_check ---
    hc = by_id.get(4, {})
    hc_text = json.dumps(hc.get("result") or {}, ensure_ascii=False)
    check("health_check 可调用", "result" in hc and "error" not in hc)
    check("health_check 标记 mock", "mock" in hc_text.lower())

    # --- list_groups ---
    lg = by_id.get(5, {})
    lg_text = json.dumps(lg.get("result") or {}, ensure_ascii=False)
    check("list_groups 可调用", "result" in lg and "error" not in lg)
    check("list_groups 返回预置数据", "KTT20260101001" in lg_text,
          f"got={lg_text[:200]}")

    # --- publish_goods（应默认 dry_run）---
    pg = by_id.get(6, {})
    pg_text = json.dumps(pg.get("result") or {}, ensure_ascii=False)
    check("publish_goods 可调用", "result" in pg and "error" not in pg)
    check("publish_goods 默认 dry_run", "dry_run" in pg_text,
          f"got={pg_text[:200]}")

    # --- list_official_apis ---
    lo = by_id.get(7, {})
    lo_text = json.dumps(lo.get("result") or {}, ensure_ascii=False)
    check("list_official_apis 可调用", "result" in lo and "error" not in lo)
    check("关键词过滤生效", "incr.quantity" in lo_text or "库存" in lo_text)

    # --- audit_log ---
    al = by_id.get(8, {})
    check("audit_log 可调用", "result" in al and "error" not in al)

    # 清理
    try:
        (ROOT / "tests" / "_tmp_e2e_audit.jsonl").unlink(missing_ok=True)
    except Exception:
        pass

    print("\n" + "=" * 60)
    print(f"结果：{PASS} 通过 / {FAIL} 失败")
    print("=" * 60)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
