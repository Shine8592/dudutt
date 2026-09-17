#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
端到端演示：用 mock 后端走完「发布 → 改库存 → 改价 → 下架」全流程。

运行：
    python examples/demo.py

无需任何凭据（内部用 mock 后端）。
"""

import os
import sys
from pathlib import Path

# Windows 终端默认 GBK/cp1252，print 中文会 UnicodeEncodeError
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass

# 用 mock 后端，避免演示时触达真实店铺
os.environ["DUDUTT_BACKEND"] = "mock"
os.environ["DUDUTT_AUDIT_PATH"] = str(
    Path(__file__).parent / "_demo_audit.jsonl"
)

sys.path.insert(0, str(Path(__file__).parent.parent))

from dudutt import actions
from dudutt.backends.mock_backend import MockBackend


def hr(title: str) -> None:
    print("\n" + "=" * 64)
    print(title)
    print("=" * 64)


def main() -> int:
    backend = MockBackend()

    hr("0. 能力查询：这个后端能做什么")
    for entry in backend.describe()["actions"]:
        mark = {"native": "√", "workaround": "~", "none": "×"}.get(
            entry["support"], "?"
        )
        print(f"  {mark} {entry['action']:<16} {entry['via']}")
        if entry["caveat"]:
            print(f"      └ {entry['caveat']}")

    hr("1. 查询现有商品")
    goods = backend.list_goods()["goods"]
    for g in goods:
        sku = g["sku_list"][0]
        print(f"  [{g['goods_id']}] {g['goods_name']}")
        print(f"      价格 {sku['price_in_fen'] / 100:.2f} 元 / 库存 {sku['quantity']}")

    hr("2. 发布商品（先 dry_run 预演）")
    spec = {
        "title": "【演示】赣南脐橙 10斤装",
        "start_time": 1,
        "end_time": 9999999999999,
        "goods_list": [{
            "goods_name": "赣南脐橙 10斤装",
            "category_name": "生鲜水果",
            "goods_desc": "产地直发，皮薄多汁，坏果包赔。",
            "market_price": 6980,
            "sku_list": [{
                "price_in_fen": 3980,
                "quantity_type": 0,
                "total_quantity": 200,
                "spec_id_list": [],
            }],
        }],
    }
    r = actions.publish_goods(backend, spec, dry_run=True)
    print(f"  dry_run      : {r['dry_run']}")
    print(f"  将发布       : {r['will_do']['title']}")
    print(f"  商品数       : {r['will_do']['goods_count']}")
    print(f"  预览团       : {r['will_do']['is_preview_only']}")
    print(f"  提示         : {r['will_do']['note']}")

    hr("3. 确认后真正发布")
    r = actions.publish_goods(
        backend, spec, dry_run=False, idempotency_key="demo-001"
    )
    act = r["activity_no"]
    gid = r["goods_ids"][0]
    print(f"  团号         : {act}")
    print(f"  商品 ID      : {gid}")

    hr("4. 幂等验证：同一个 key 再发一次")
    r2 = actions.publish_goods(
        backend, spec, dry_run=False, idempotency_key="demo-001"
    )
    print(f"  幂等重放     : {r2.get('idempotent_replay')}")
    print(f"  商品总数     : {len(backend.list_goods()['goods'])}（未增加即正确）")

    hr("5. 改库存")
    sku_id = backend.get_goods(gid)["goods"]["sku_list"][0]["sku_id"]
    r = actions.set_stock(backend, gid, sku_id, 88, dry_run=False)
    print(f"  全量设为     : {r['quantity']}")

    hr("6. 改价")
    r = actions.update_price(backend, gid, sku_id, 3580, dry_run=False)
    if r.get("ok"):
        print(f"  {r['old_price_in_fen'] / 100:.2f} 元 → "
              f"{r['new_price_in_fen'] / 100:.2f} 元")
    else:
        print(f"  不支持：{r.get('error')}")
        print(f"  替代方案：{r.get('alternative')}")

    hr("7. 下架商品")
    r = actions.delist_goods(backend, gid, dry_run=False)
    print(f"  方式         : {r.get('method')}")
    print(f"  说明         : {r.get('note') or r.get('caveat')}")

    hr("8. 审计日志")
    from dudutt import audit

    log = audit.tail(limit=3)
    for e in log["entries"]:
        flag = "预演" if e["dry_run"] else "执行"
        print(f"  [{flag}] {e['iso']} {e['action']:<14} ok={e['ok']}")

    print("\n演示结束。审计文件：", log["audit_file"])
    try:
        Path(log["audit_file"]).unlink(missing_ok=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
