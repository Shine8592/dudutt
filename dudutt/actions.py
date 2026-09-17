#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
业务动作层：把"后端能力"包装成"带护栏的业务动作"。

三层职责分离：
- backends/  只管"怎么调用"（API / 浏览器 / mock）
- actions.py 管"能不能做 + 该不该做"（能力协商 / dry-run / 幂等 / 审计）
- server.py  只管"暴露成 MCP 工具"（参数校验 / 描述）

为什么写操作默认 dry_run：
快团团的写操作直接影响真实经营（下架=停售、改价=改收入）。
Agent 的意图经常是对的，但参数可能错。默认先演一遍，
让人/Agent 看到"将要发生什么"再确认，是唯一稳妥的默认值。
"""

from __future__ import annotations

import os
import time
from typing import Any, Optional

from dudutt import audit
from dudutt.backends.base import (
    SUPPORT_NATIVE,
    SUPPORT_WORKAROUND,
    Action,
    BackendError,
    BaseBackend,
    blocked_payload,
)
from dudutt.pop_client import PopError

# ---------------------------------------------------------------------------
# 幂等：同一 key 在窗口期内只真正执行一次
# ---------------------------------------------------------------------------

ENV_IDEMPOTENCY_TTL = "DUDUTT_IDEMPOTENCY_TTL"
DEFAULT_IDEMPOTENCY_TTL = 600  # 秒

# 进程内幂等缓存：{key: (timestamp, result)}
_IDEMPOTENCY_CACHE: dict[str, tuple[float, dict]] = {}


def _idem_ttl() -> int:
    raw = (os.environ.get(ENV_IDEMPOTENCY_TTL) or "").strip()
    if raw:
        try:
            return int(raw)
        except ValueError:
            pass
    return DEFAULT_IDEMPOTENCY_TTL


def _idem_get(key: str) -> Optional[dict]:
    item = _IDEMPOTENCY_CACHE.get(key)
    if not item:
        return None
    ts, result = item
    if time.time() - ts > _idem_ttl():
        _IDEMPOTENCY_CACHE.pop(key, None)
        return None
    return result


def _idem_put(key: str, result: dict) -> None:
    _IDEMPOTENCY_CACHE[key] = (time.time(), result)


def reset_idempotency_cache() -> None:
    """清空幂等缓存（测试用）。"""
    _IDEMPOTENCY_CACHE.clear()


# ---------------------------------------------------------------------------
# 统一返回包装
# ---------------------------------------------------------------------------


def _wrap_error(e: Exception, action: str, backend: str) -> dict:
    """把异常统一成结构化错误。"""
    if isinstance(e, PopError):
        d = e.to_dict()
        d["action"] = action
        d["backend"] = backend
        return d
    return {
        "ok": False,
        "action": action,
        "backend": backend,
        "error": str(e),
    }


def _guard_write(
    backend: BaseBackend,
    action: str,
    params: dict,
    dry_run: bool,
    idempotency_key: Optional[str],
    preview: dict,
) -> Optional[dict]:
    """写操作的通用护栏。返回非 None 表示应提前返回。

    依次检查：能力 → 幂等 → dry_run。
    """
    support = backend.support_for(action)

    # 1) 能力检查：后端不支持就直接说清楚，绝不假装成功
    #    替代方案统一从 Support.alternative 取，保证能力声明处的信息不会丢
    if not support.usable:
        result = blocked_payload(
            action,
            backend.name,
            support,
            hint=(
                "可尝试：DUDUTT_BACKEND=browser 使用浏览器兜底；"
                "或用 capabilities 工具查看各后端能力对比。"
            ),
        )
        audit.record(action, backend.name, params, result, dry_run=dry_run,
                     idempotency_key=idempotency_key)
        return result

    # 2) 幂等：同一 key 重复调用直接返回上次结果（防重复执行）
    if idempotency_key:
        cached = _idem_get(idempotency_key)
        if cached is not None:
            return {
                **cached,
                "idempotent_replay": True,
                "note": "检测到相同 idempotency_key 的近期调用，未重复执行。",
            }

    # 3) dry_run：只演不执行（默认行为）
    if dry_run:
        result = {
            "ok": True,
            "dry_run": True,
            "action": action,
            "backend": backend.name,
            "support_level": support.level,
            "via": support.via,
            "caveat": support.caveat,
            "will_do": preview,
            "next_step": (
                "确认无误后，用相同参数并设置 dry_run=false 真正执行。"
                "写操作会记入审计日志。"
            ),
        }
        audit.record(action, backend.name, params, result, dry_run=True,
                     idempotency_key=idempotency_key)
        return result

    return None


# ---------------------------------------------------------------------------
# 业务动作
# ---------------------------------------------------------------------------


def list_groups(
    backend: BaseBackend,
    start_update_time: Optional[int] = None,
    end_update_time: Optional[int] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """查询团列表（只读）。"""
    try:
        return backend.list_groups(
            start_update_time=start_update_time,
            end_update_time=end_update_time,
            page=page,
            size=size,
        )
    except (PopError, BackendError, NotImplementedError) as e:
        return _wrap_error(e, Action.LIST_GROUPS, backend.name)


def list_goods(
    backend: BaseBackend,
    activity_no: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """查询商品列表（只读）。"""
    try:
        return backend.list_goods(activity_no=activity_no, page=page, size=size)
    except (PopError, BackendError, NotImplementedError) as e:
        return _wrap_error(e, Action.LIST_GOODS, backend.name)


def get_goods(backend: BaseBackend, goods_id: int) -> dict:
    """查询单个商品（只读）。"""
    try:
        return backend.get_goods(int(goods_id))
    except (PopError, BackendError, NotImplementedError) as e:
        return _wrap_error(e, Action.GET_GOODS, backend.name)


def publish_goods(
    backend: BaseBackend,
    spec: dict,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """发布商品。

    spec 必填：title, start_time, end_time, goods_list
    goods_list 每项必填：category_name, goods_desc, goods_name, sku_list
    sku_list 每项必填：price_in_fen, quantity_type, spec_id_list, total_quantity
    """
    action = Action.PUBLISH_GOODS
    support = backend.support_for(action)

    # 先查能力、再校验参数：若动作根本不可能，讨论参数细节会误导调用方
    # （他能改好参数，但依然做不到）
    if not support.usable:
        result = blocked_payload(
            action, backend.name, support,
            hint="可用 capabilities 工具查看各后端能力对比。",
        )
        audit.record(action, backend.name, {"spec": spec}, result, dry_run=dry_run,
                     idempotency_key=idempotency_key)
        return result

    problems = validate_publish_spec(spec)
    if problems:
        result = {
            "ok": False,
            "action": action,
            "backend": backend.name,
            "error": "发布参数校验未通过。",
            "problems": problems,
        }
        audit.record(action, backend.name, {"spec": spec}, result, dry_run=dry_run,
                     idempotency_key=idempotency_key)
        return result

    preview = {
        "title": spec.get("title"),
        "goods_count": len(spec.get("goods_list") or []),
        "goods_names": [
            g.get("goods_name") for g in (spec.get("goods_list") or [])
        ],
        "start_time": spec.get("start_time"),
        "end_time": spec.get("end_time"),
        "is_preview_only": spec.get("is_save_preview") == 1,
        "note": (
            "将调用官方创建团购接口。⚠️ 创建后价格锁死，无法再改。"
            if support.level == SUPPORT_NATIVE and backend.name == "api"
            else "将创建团购。"
        ),
    }

    early = _guard_write(backend, action, {"spec": spec}, dry_run,
                         idempotency_key, preview)
    if early is not None:
        return early

    try:
        result = backend.publish_goods(spec)
    except (PopError, BackendError, NotImplementedError) as e:
        result = _wrap_error(e, action, backend.name)

    if idempotency_key and result.get("ok"):
        _idem_put(idempotency_key, result)
    audit.record(action, backend.name, {"spec": spec}, result, dry_run=False,
                 idempotency_key=idempotency_key)
    return result


def set_stock(
    backend: BaseBackend,
    goods_id: int,
    sku_id: int,
    quantity: int,
    modify_quantity_type: int = 2,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """改库存。

    modify_quantity_type：1=增量修改（quantity 为增减值），2=全量设置（默认）
    """
    action = Action.SET_STOCK
    if quantity < 0 and modify_quantity_type == 2:
        return {
            "ok": False,
            "action": action,
            "error": "全量设置模式下库存不能为负。若想减少库存请用增量模式(-1)。",
        }
    params = {
        "goods_id": goods_id,
        "sku_id": sku_id,
        "quantity": quantity,
        "modify_quantity_type": modify_quantity_type,
    }
    preview = {
        "goods_id": goods_id,
        "sku_id": sku_id,
        "mode": "增量" if modify_quantity_type == 1 else "全量设置",
        "quantity": quantity,
    }
    early = _guard_write(backend, action, params, dry_run, idempotency_key, preview)
    if early is not None:
        return early

    try:
        result = backend.set_stock(
            goods_id=int(goods_id),
            sku_id=int(sku_id),
            quantity_delta=int(quantity),
            modify_quantity_type=int(modify_quantity_type),
        )
    except (PopError, BackendError, NotImplementedError) as e:
        result = _wrap_error(e, action, backend.name)

    if idempotency_key and result.get("ok"):
        _idem_put(idempotency_key, result)
    audit.record(action, backend.name, params, result, dry_run=False,
                 idempotency_key=idempotency_key)
    return result


def delist_goods(
    backend: BaseBackend,
    goods_id: int,
    sku_ids: Optional[list[int]] = None,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """下架商品。

    官方 API 只能变通（库存归零），浏览器后端可真正下架。
    返回体里的 method 字段说明实际用了哪种。
    """
    action = Action.DELIST_GOODS
    support = backend.support_for(action)
    params = {"goods_id": goods_id, "sku_ids": sku_ids}
    preview = {
        "goods_id": goods_id,
        "method": (
            "库存全量置 0（变通）"
            if support.level == SUPPORT_WORKAROUND
            else "真实下架"
        ),
        "caveat": support.caveat,
        "skus_to_zero": sku_ids or "自动查询该商品全部 SKU",
    }
    early = _guard_write(backend, action, params, dry_run, idempotency_key, preview)
    if early is not None:
        return early

    try:
        result = backend.delist_goods(goods_id=int(goods_id), sku_ids=sku_ids)
    except (PopError, BackendError, NotImplementedError) as e:
        result = _wrap_error(e, action, backend.name)

    if idempotency_key and result.get("ok"):
        _idem_put(idempotency_key, result)
    audit.record(action, backend.name, params, result, dry_run=False,
                 idempotency_key=idempotency_key)
    return result


def update_price(
    backend: BaseBackend,
    goods_id: int,
    sku_id: int,
    price_in_fen: int,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """改价。

    官方 API 不支持，会返回 unsupported（并给出替代方案）；
    浏览器/mock 后端可执行。
    """
    action = Action.UPDATE_PRICE
    support = backend.support_for(action)

    if price_in_fen < 0:
        return {"ok": False, "action": action, "error": "价格不能为负。"}

    params = {
        "goods_id": goods_id,
        "sku_id": sku_id,
        "price_in_fen": price_in_fen,
    }
    preview = {
        "goods_id": goods_id,
        "sku_id": sku_id,
        "new_price_in_fen": price_in_fen,
        "new_price_yuan": round(price_in_fen / 100, 2),
        "support_level": support.level,
    }
    early = _guard_write(backend, action, params, dry_run, idempotency_key, preview)
    if early is not None:
        return early

    try:
        result = backend.update_price(
            goods_id=int(goods_id), sku_id=int(sku_id), price_in_fen=int(price_in_fen)
        )
    except (PopError, BackendError, NotImplementedError) as e:
        result = _wrap_error(e, action, backend.name)

    if idempotency_key and result.get("ok"):
        _idem_put(idempotency_key, result)
    audit.record(action, backend.name, params, result, dry_run=False,
                 idempotency_key=idempotency_key)
    return result


# ---------------------------------------------------------------------------
# 参数校验
# ---------------------------------------------------------------------------


def validate_publish_spec(spec: dict) -> list[str]:
    """校验发布商品参数，返回问题列表（空列表=通过）。

    校验依据官方 pdd.ktt.group.create 文档：
    - goods_list 每项必填 category_name / goods_desc / goods_name / sku_list
    - sku_list 每项必填 price_in_fen / quantity_type / spec_id_list / total_quantity
    - total_quantity 最大 100w
    - pic_url_list 不超过 20 张
    """
    problems: list[str] = []
    if not isinstance(spec, dict):
        return ["spec 必须是对象"]

    for key in ("title", "start_time", "end_time", "goods_list"):
        if not spec.get(key):
            problems.append(f"缺少必填字段：{key}")

    goods_list = spec.get("goods_list")
    if goods_list is not None:
        if not isinstance(goods_list, list) or not goods_list:
            problems.append("goods_list 必须是非空数组")
        else:
            for i, g in enumerate(goods_list):
                if not isinstance(g, dict):
                    problems.append(f"goods_list[{i}] 必须是对象")
                    continue
                for key in ("category_name", "goods_desc", "goods_name", "sku_list"):
                    if not g.get(key):
                        problems.append(f"goods_list[{i}] 缺少必填字段：{key}")
                if len(g.get("pic_url_list") or []) > 20:
                    problems.append(f"goods_list[{i}].pic_url_list 不能超过 20 张")
                skus = g.get("sku_list")
                if isinstance(skus, list):
                    for j, s in enumerate(skus):
                        if not isinstance(s, dict):
                            problems.append(f"goods_list[{i}].sku_list[{j}] 必须是对象")
                            continue
                        for key in ("price_in_fen", "quantity_type",
                                    "spec_id_list", "total_quantity"):
                            if s.get(key) is None:
                                problems.append(
                                    f"goods_list[{i}].sku_list[{j}] 缺少必填字段：{key}"
                                )
                        tq = s.get("total_quantity")
                        if isinstance(tq, int) and tq > 1_000_000:
                            problems.append(
                                f"goods_list[{i}].sku_list[{j}].total_quantity "
                                f"超过上限 100 万"
                            )

    # 时间合理性
    start, end = spec.get("start_time"), spec.get("end_time")
    if isinstance(start, int) and isinstance(end, int) and end <= start:
        problems.append("end_time 必须晚于 start_time")

    return problems
