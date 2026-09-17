#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务动作与护栏测试（用 mock 后端 + 内存后端，不触网）。

重点验证三件事：
1. 能力协商：不支持的动作用 unsupported 明确报错（而非幻觉成功）
2. 安全护栏：dry_run 默认不执行；幂等键防重复
3. 参数校验：发布商品的必填/上限校验生效
"""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

# 审计写到临时目录，避免污染用户真实日志
os.environ["DUDUTT_AUDIT_PATH"] = str(
    Path(__file__).parent / "_tmp_audit.jsonl"
)

from dudutt import actions
from dudutt.backends.api_backend import ApiBackend
from dudutt.backends.base import Action, Support, SUPPORT_NONE, BaseBackend
from dudutt.backends.mock_backend import MockBackend
from dudutt.pop_client import PopClient

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


class NoSupportBackend(BaseBackend):
    """一个所有动作都不支持的后端，用于测试能力协商是否正确阻断。"""

    name = "nosupport"

    def capabilities(self):
        return {
            a: Support(SUPPORT_NONE, "", f"{a} 不支持（测试用）")
            for a in (Action.PUBLISH_GOODS, Action.DELIST_GOODS,
                      Action.UPDATE_PRICE, Action.SET_STOCK)
        }

    def list_groups(self, **kw):
        return {"ok": True, "backend": self.name}

    def list_goods(self, **kw):
        return {"ok": True, "backend": self.name}

    def get_goods(self, goods_id):
        return {"ok": True, "backend": self.name}


# ---------------------------------------------------------------------------
# 1. 能力协商
# ---------------------------------------------------------------------------


def test_api_backend_capabilities():
    print("\n[1] 官方 API 后端的能力声明（必须如实）")
    b = ApiBackend(client=PopClient(client_id="c", client_secret="s"))
    caps = b.capabilities()

    check(
        "发布商品 = native",
        caps[Action.PUBLISH_GOODS].level == "native",
    )
    check(
        "改库存 = native",
        caps[Action.SET_STOCK].level == "native",
    )
    check(
        "下架 = workaround（不是 native，因为有副作用）",
        caps[Action.DELIST_GOODS].level == "workaround",
    )
    check(
        "改价 = none（官方确实没有）",
        caps[Action.UPDATE_PRICE].level == "none",
    )
    check(
        "下架的 caveat 说明了副作用",
        "库存" in caps[Action.DELIST_GOODS].caveat,
    )


def test_unsupported_blocks():
    print("\n[2] 后端不支持时必须明确阻断（不能幻觉成功）")
    b = NoSupportBackend()

    r = actions.publish_goods(b, {"title": "x"}, dry_run=False)
    check("不支持的动作返回 unsupported=True", r.get("unsupported") is True)
    check("不含虚假的 ok=True", r.get("ok") is False)
    check("给出了切换后端的提示", "hint" in r or "error" in r)


def test_api_update_price_unsupported():
    print("\n[3] 官方 API 改价必须返回 unsupported + 替代方案")
    b = ApiBackend(client=PopClient(client_id="c", client_secret="s"))
    r = actions.update_price(b, goods_id=1, sku_id=1, price_in_fen=100,
                             dry_run=False)
    check("改价被标记 unsupported", r.get("unsupported") is True)
    check("给出了替代方案", bool(r.get("alternative")))
    check(
        "替代方案提到浏览器后端",
        "browser" in (r.get("alternative") or ""),
    )


# ---------------------------------------------------------------------------
# 4. dry_run 护栏
# ---------------------------------------------------------------------------


def test_dry_run_default():
    print("\n[4] dry_run 默认只演不执行")
    b = MockBackend()
    before = len(b._goods)

    r = actions.publish_goods(
        b,
        {
            "title": "测试团",
            "start_time": 1,
            "end_time": 2,
            "goods_list": [{
                "goods_name": "商品A",
                "category_name": "分类",
                "goods_desc": "描述",
                "sku_list": [{
                    "price_in_fen": 100,
                    "quantity_type": 0,
                    "total_quantity": 10,
                    "spec_id_list": [],
                }],
            }],
        },
        dry_run=True,
    )
    check("dry_run 返回 ok", r.get("ok") is True)
    check("dry_run 标记为 True", r.get("dry_run") is True)
    check("dry_run 含 will_do 预览", bool(r.get("will_do")))
    check("dry_run 未真正创建商品", len(b._goods) == before,
          f"before={before} after={len(b._goods)}")
    check("dry_run 给出下一步说明", "dry_run=false" in (r.get("next_step") or ""))


def test_real_execution():
    print("\n[5] dry_run=false 真正执行")
    b = MockBackend()
    before = len(b._goods)

    r = actions.publish_goods(
        b,
        {
            "title": "测试团",
            "start_time": 1,
            "end_time": 2,
            "goods_list": [{
                "goods_name": "商品A",
                "category_name": "分类",
                "goods_desc": "描述",
                "sku_list": [{
                    "price_in_fen": 100,
                    "quantity_type": 0,
                    "total_quantity": 10,
                    "spec_id_list": [],
                }],
            }],
        },
        dry_run=False,
    )
    check("真正执行成功", r.get("ok") is True)
    check("确实创建了商品", len(b._goods) == before + 1)
    check("返回了 activity_no", bool(r.get("activity_no")))


# ---------------------------------------------------------------------------
# 6. 幂等
# ---------------------------------------------------------------------------


def test_idempotency():
    print("\n[6] 幂等键防止重复执行")
    actions.reset_idempotency_cache()
    b = MockBackend()
    before = len(b._goods)
    spec = {
        "title": "幂等测试团",
        "start_time": 1,
        "end_time": 2,
        "goods_list": [{
            "goods_name": "商品B",
            "category_name": "分类",
            "goods_desc": "描述",
            "sku_list": [{
                "price_in_fen": 100,
                "quantity_type": 0,
                "total_quantity": 5,
                "spec_id_list": [],
            }],
        }],
    }

    r1 = actions.publish_goods(b, spec, dry_run=False, idempotency_key="K1")
    r2 = actions.publish_goods(b, spec, dry_run=False, idempotency_key="K1")

    check("第一次执行成功", r1.get("ok") is True)
    check("第二次被识别为幂等重放", r2.get("idempotent_replay") is True)
    check(
        "只创建了一次商品（关键！防重复建团）",
        len(b._goods) == before + 1,
        f"expected {before + 1}, got {len(b._goods)}",
    )


# ---------------------------------------------------------------------------
# 7. 参数校验
# ---------------------------------------------------------------------------


def test_validate_publish_spec():
    print("\n[7] 发布参数校验")
    v = actions.validate_publish_spec

    check("空 spec 报多个问题", len(v({})) >= 4)

    good = {
        "title": "t", "start_time": 1, "end_time": 2,
        "goods_list": [{
            "goods_name": "n", "category_name": "c", "goods_desc": "d",
            "sku_list": [{
                "price_in_fen": 1, "quantity_type": 0,
                "total_quantity": 1, "spec_id_list": [],
            }],
        }],
    }
    check("合法 spec 无问题", v(good) == [], f"got={v(good)}")

    # total_quantity 超上限
    bad_qty = {
        "title": "t", "start_time": 1, "end_time": 2,
        "goods_list": [{
            "goods_name": "n", "category_name": "c", "goods_desc": "d",
            "sku_list": [{
                "price_in_fen": 1, "quantity_type": 0,
                "total_quantity": 2_000_000, "spec_id_list": [],
            }],
        }],
    }
    problems = v(bad_qty)
    check("超 100 万库存被拦", any("100 万" in p for p in problems),
          f"got={problems}")

    # 图片超 20 张
    bad_pic = {
        "title": "t", "start_time": 1, "end_time": 2,
        "goods_list": [{
            "goods_name": "n", "category_name": "c", "goods_desc": "d",
            "pic_url_list": [f"u{i}" for i in range(21)],
            "sku_list": [{
                "price_in_fen": 1, "quantity_type": 0,
                "total_quantity": 1, "spec_id_list": [],
            }],
        }],
    }
    problems2 = v(bad_pic)
    check("超 20 张图被拦", any("20 张" in p for p in problems2),
          f"got={problems2}")

    # 时间倒置
    bad_time = dict(good, start_time=100, end_time=50)
    check("end<=start 被拦", any("end_time" in p for p in v(bad_time)))


# ---------------------------------------------------------------------------
# 8. 库存与下架
# ---------------------------------------------------------------------------


def test_set_stock():
    print("\n[8] 改库存")
    b = MockBackend()
    goods = b.list_goods()["goods"][0]
    gid, sid = goods["goods_id"], goods["sku_list"][0]["sku_id"]

    r = actions.set_stock(b, gid, sid, 50, modify_quantity_type=2, dry_run=False)
    check("全量设置成功", r.get("ok") is True)
    check("库存被设为 50", r.get("quantity") == 50)

    r2 = actions.set_stock(b, gid, sid, -10, modify_quantity_type=1, dry_run=False)
    check("增量 -10 成功", r2.get("ok") is True)
    check("库存变成 40", r2.get("quantity") == 40, f"got={r2.get('quantity')}")

    r3 = actions.set_stock(b, gid, sid, -5, modify_quantity_type=2, dry_run=False)
    check("全量模式拒绝负库存", r3.get("ok") is False)


def test_delist_api_uses_workaround():
    print("\n[9] API 后端下架 = 库存归零变通（method 必须标明）")
    b = ApiBackend(client=PopClient(client_id="c", client_secret="s"))

    # 伪造 client.call，避免真联网
    calls = []

    def fake_call(api, biz=None):
        calls.append((api, biz))
        if api == "pdd.ktt.goods.query.single":
            return {"result": {"sku_list": [{"sku_id": 7}, {"sku_id": 8}]}}
        return {"success": True}

    b.client.call = fake_call  # type: ignore[method-assign]

    r = b.delist_goods(goods_id=1)
    check("下架执行成功", r.get("ok") is True)
    check("method 标明 workaround_stock_zero",
          r.get("method") == "workaround_stock_zero")
    check("caveat 说明了副作用", "库存" in (r.get("caveat") or ""))
    check("对两个 SKU 都做了归零", len(r.get("skus") or []) == 2)
    check(
        "归零时用了全量模式(2)",
        all(c[1].get("modify_quantity_type") == 2
            for c in calls if c[0] == "pdd.ktt.goods.incr.quantity"),
    )


def test_health_check_mock():
    print("\n[10] mock 后端健康检查")
    b = MockBackend()
    r = b.health_check()
    check("ok", r.get("ok") is True)
    check("明确标记为 mock", r.get("mock") is True)


def main() -> int:
    print("=" * 60)
    print("dudutt —— 业务动作与护栏测试")
    print("=" * 60)
    test_api_backend_capabilities()
    test_unsupported_blocks()
    test_api_update_price_unsupported()
    test_dry_run_default()
    test_real_execution()
    test_idempotency()
    test_validate_publish_spec()
    test_set_stock()
    test_delist_api_uses_workaround()
    test_health_check_mock()
    print("\n" + "=" * 60)
    print(f"结果：{PASS} 通过 / {FAIL} 失败")
    print("=" * 60)

    # 清理测试审计文件
    try:
        Path(os.environ["DUDUTT_AUDIT_PATH"]).unlink(missing_ok=True)
    except Exception:
        pass

    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
