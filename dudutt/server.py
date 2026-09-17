#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dudutt MCP 服务入口。

设计上贯彻两条主线：
- 诚实能力边界：官方不支持的动作明确报 unsupported，绝不幻觉出结果
- 安全护栏：写操作默认 dry_run；幂等键防重复；审计日志可追溯

工具描述（docstring）是 Agent 唯一能看到的说明书，因此每条都写明：
用途 / 何时用 / 能力边界 / 限制。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional

# 启动早期把包目录加入 sys.path，兼容以 stdio 被宿主拉起的场景
# （沿用 duduExcel / 记忆系统 mcp_server.py 的同款处理）
sys.path.insert(0, str(Path(__file__).parent.parent))

try:
    from mcp.server.mcpserver import MCPServer
except ImportError as e:  # pragma: no cover
    raise SystemExit(
        f"缺少 mcp 依赖：{e}\n请执行：pip install 'mcp>=2.0.0' requests"
    )

from dudutt import actions, audit
from dudutt.api_map import group_status_label, list_apis
from dudutt.backends import build_backend, warn

SERVER_VERSION = "0.1.0"

mcp = MCPServer("dudutt")

# 后端在 main() 里初始化；此处用懒加载保证工具被调用时一定已就绪
_BACKEND: Any = None
_NOTES: list[str] = []


def get_backend():
    """懒加载后端单例。"""
    global _BACKEND, _NOTES
    if _BACKEND is None:
        _BACKEND, _NOTES = build_backend()
        for note in _NOTES:
            warn(note)
    return _BACKEND


def _as_bool(v: Any, default: bool) -> bool:
    """把参数稳健地转成布尔值。

    坑：MCP SDK 对带默认值的 bool 参数，schema→函数调用绑定时
    可能不传递该键，导致工具内始终拿到默认值。
    因此同时接受 bool、字符串（"true"/"1"/"yes"）与 None。
    （与 duduExcel 的同款处理保持一致）
    """
    if v is None:
        return default
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return bool(v)
    if isinstance(v, str):
        s = v.strip().lower()
        if s in ("true", "1", "yes", "y", "on"):
            return True
        if s in ("false", "0", "no", "n", "off"):
            return False
    return default


# ---------------------------------------------------------------------------
# 能力与诊断（Agent 应该先调这些）
# ---------------------------------------------------------------------------


@mcp.tool()
def capabilities() -> dict:
    """【先调这个】查看当前后端支持哪些动作，以及各后端的完整能力对比。

    为什么必须先调：快团团的官方 API **没有「下架」和「改价」接口**。
    直接调用这两个工具会得到 unsupported 错误，而不是虚假的成功。
    本工具如实告知每个动作在当前后端下的支持程度：

    - native：原生直接支持
    - workaround：支持但有副作用（如"下架"实为库存归零）
    - none：不支持

    返回：当前后端各动作支持情况 + 官方接口清单 + 各后端对比。
    """
    backend = get_backend()
    desc = backend.describe()
    desc["ok"] = True
    desc["notes"] = _NOTES
    desc["server_version"] = SERVER_VERSION

    # 三个后端的横向对比，让 Agent 一眼看出该切哪个后端
    desc["backend_matrix"] = {
        "api": {
            "publish_goods": "native",
            "set_stock": "native",
            "delist_goods": "workaround（库存归零）",
            "update_price": "none（官方无此接口）",
        },
        "browser": {
            "publish_goods": "native（不稳定）",
            "set_stock": "native",
            "delist_goods": "native（真实下架）",
            "update_price": "native（真实改价）",
        },
        "mock": {
            "publish_goods": "native（模拟）",
            "set_stock": "native（模拟）",
            "delist_goods": "native（模拟）",
            "update_price": "native（模拟）",
        },
    }
    return desc


@mcp.tool()
def health_check() -> dict:
    """检查后端连通性与就绪状态（凭据是否有效、浏览器是否已登录等）。

    用途：排查问题时**第一个**调用的工具。
    官方 API 后端会拉取拼多多服务器时间验证签名；浏览器后端会报告登录态与选择器校准状态。
    """
    backend = get_backend()
    try:
        result = backend.health_check()
    except Exception as e:
        result = {"ok": False, "backend": backend.name, "error": str(e)}
    result["backend_name"] = backend.name
    return result


# ---------------------------------------------------------------------------
# 只读工具
# ---------------------------------------------------------------------------


@mcp.tool()
def list_groups(
    start_update_time: Optional[int] = None,
    end_update_time: Optional[int] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """查询团（团购活动）列表。

    参数：
    - start_update_time / end_update_time：毫秒级时间戳。
      官方**要求必填**且起止差**不能超过 7 天**；不传则默认查最近 7 天。
    - page / size：分页（size 建议 ≤ 50，避免返回体过大）

    返回每个团的 activity_no（团号）、title、status（状态码+中文标签）、
    start_time / end_time、is_help_sell（0=我发布 1=我帮卖）。

    团状态：-10 待发布 / -5 未开始 / 1 跟团中 / 20 已结束 / 30 已删除
    """
    return actions.list_groups(
        get_backend(),
        start_update_time=start_update_time,
        end_update_time=end_update_time,
        page=page,
        size=size,
    )


@mcp.tool()
def list_goods(
    activity_no: Optional[str] = None,
    page: int = 1,
    size: int = 20,
) -> dict:
    """查询商品列表。

    参数：
    - activity_no：团号，省略则查全部商品
    - page / size：分页

    返回每个商品的 goods_id、goods_name、category_name、market_price（划线价，单位分）、
    以及 sku_list（含 sku_id、price_in_fen 价格分、quantity 剩余库存、total_quantity 总库存）。

    提示：拿到 goods_id 和 sku_id 后才能做改库存 / 下架 / 改价。
    """
    return actions.list_goods(
        get_backend(), activity_no=activity_no, page=page, size=size
    )


@mcp.tool()
def get_goods(goods_id: int) -> dict:
    """查询单个商品的完整详情（含全部 SKU 与规格）。

    用途：改价/改库存前先看清楚当前值，避免盲改。
    """
    return actions.get_goods(get_backend(), int(goods_id))


# ---------------------------------------------------------------------------
# 写操作工具（默认 dry_run）
# ---------------------------------------------------------------------------


@mcp.tool()
def publish_goods(
    title: str,
    goods_list: list[dict],
    start_time: Optional[int] = None,
    end_time: Optional[int] = None,
    is_save_preview: int = 0,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """【发布商品】创建团购活动。

    ⚠️ 默认 dry_run=true：只返回"将要发布什么"，不真正执行。
    确认无误后再次调用并传 dry_run=false。

    参数：
    - title：团购标题（必填）
    - goods_list：商品数组（必填，不能为空），每项需包含：
        * goods_name：商品名
        * category_name：分类名
        * goods_desc：商品描述
        * sku_list：SKU 数组，每项需含
            - price_in_fen：价格（单位：**分**，如 29.8 元 = 2980）
            - quantity_type：0=普通库存 1=无限库存
            - total_quantity：总库存（最大 100 万）
            - spec_id_list：规格 ID 列表，无规格传 []
        * pic_url_list（可选）：商品图 URL 列表，**不超过 20 张**
        * market_price（可选）：划线价（分），0 表示无
        * limit_buy（可选）：限购数，0 表示不限购
    - start_time / end_time：毫秒级时间戳；不传则默认"现在开始、7 天后结束"
    - is_save_preview：1=先存为**预览团**（不公开，确认后再发），0=直接发布
    - idempotency_key：幂等键，相同键在 10 分钟内重复调用不会重复建团

    重要限制（官方 API 后端）：
    团创建后**价格即锁死**，官方未提供改价接口。请务必先 dry_run 核对价格。
    需要先预览再发布时，把 is_save_preview 设为 1。
    """
    import time as _t

    now_ms = int(_t.time() * 1000)
    spec: dict[str, Any] = {
        "title": title,
        "goods_list": goods_list,
        "is_save_preview": int(is_save_preview),
        "start_time": int(start_time) if start_time else now_ms,
        "end_time": int(end_time) if end_time else now_ms + 7 * 86400 * 1000,
    }
    return actions.publish_goods(
        get_backend(),
        spec,
        dry_run=_as_bool(dry_run, True),
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def set_stock(
    goods_id: int,
    sku_id: int,
    quantity: int,
    modify_quantity_type: int = 2,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """【改库存】设置或增减某个 SKU 的库存。

    ⚠️ 默认 dry_run=true，确认后传 dry_run=false 执行。

    参数：
    - goods_id / sku_id：目标商品与 SKU（先用 list_goods 获取）
    - quantity：库存值
    - modify_quantity_type：
        * 2（默认）= **全量设置**：直接把库存设为 quantity
        * 1 = **增量修改**：在现有库存上增减 quantity（如 -5 表示减 5）

    返回：改后的 quantity 与所用模式。
    """
    return actions.set_stock(
        get_backend(),
        goods_id=int(goods_id),
        sku_id=int(sku_id),
        quantity=int(quantity),
        modify_quantity_type=int(modify_quantity_type),
        dry_run=_as_bool(dry_run, True),
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def delist_goods(
    goods_id: int,
    sku_ids: Optional[list[int]] = None,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """【下架商品】停止销售某商品。

    ⚠️ **能力边界（必读）**：
    官方 API **没有下架接口**。在 api 后端下，本工具只能**变通实现**：
    把该商品所有 SKU 库存全量置 0（效果≈售罄），商品记录仍然存在。
    返回体的 method 字段会标明实际用了哪种方式（workaround_stock_zero / delist）。

    如需**真正下架/删除**，请切换浏览器后端：
        DUDUTT_BACKEND=browser
    （需先完成登录与选择器校准，见 capabilities 工具的输出）

    参数：
    - goods_id：商品 ID
    - sku_ids：可选，指定要清零的 SKU；省略则自动查询该商品全部 SKU
    - dry_run：默认 true，先预演；确认后传 false
    """
    return actions.delist_goods(
        get_backend(),
        goods_id=int(goods_id),
        sku_ids=sku_ids,
        dry_run=_as_bool(dry_run, True),
        idempotency_key=idempotency_key,
    )


@mcp.tool()
def update_price(
    goods_id: int,
    sku_id: int,
    price_in_fen: int,
    dry_run: bool = True,
    idempotency_key: Optional[str] = None,
) -> dict:
    """【改价】修改某个 SKU 的价格。

    ⚠️ **能力边界（必读）**：
    官方 API **没有改价接口** —— 团创建后价格即锁死。
    在 api 后端下调用本工具会返回 unsupported（不是失败，是"做不到"），
    并给出替代方案。

    可用途径：
    1. 切换浏览器后端（DUDUTT_BACKEND=browser）直接操作后台
    2. 下架当前团，用新价格重新发布

    参数：
    - goods_id / sku_id：目标 SKU（先用 list_goods 获取）
    - price_in_fen：新价格，单位**分**（如 29.8 元 = 2980）
    - dry_run：默认 true
    """
    return actions.update_price(
        get_backend(),
        goods_id=int(goods_id),
        sku_id=int(sku_id),
        price_in_fen=int(price_in_fen),
        dry_run=_as_bool(dry_run, True),
        idempotency_key=idempotency_key,
    )


# ---------------------------------------------------------------------------
# 辅助工具
# ---------------------------------------------------------------------------


@mcp.tool()
def list_official_apis(keyword: Optional[str] = None) -> dict:
    """列出快团团全部官方接口（36 个）及其用途、授权模式、限流、限制说明。

    用途：当需要超出本服务已封装动作的能力时（如订单、售后、物流、供货商），
    用本工具查到对应接口名，再据此扩展或直接调用。

    参数：
    - keyword：可选，按接口名/中文名/用途过滤（如 "order"、"订单"、"库存"）
    """
    apis = list_apis()
    if keyword:
        kw = keyword.strip().lower()
        apis = [
            a for a in apis
            if kw in a["name"].lower()
            or kw in a["label"]
            or kw in a["purpose"]
        ]
    return {
        "ok": True,
        "count": len(apis),
        "keyword": keyword,
        "apis": apis,
    }


@mcp.tool()
def audit_log(limit: int = 20) -> dict:
    """查看最近的写操作审计记录（倒序）。

    用途：复盘"谁在什么时候改了哪个商品"，或排查某个写操作到底执行了没有。
    每条记录含时间、动作、后端、参数、结果摘要、是否 dry_run。

    参数：
    - limit：返回条数（默认 20，倒序）
    """
    return audit.tail(limit=int(limit))


def main() -> None:
    """启动 stdio 传输（本地优先，凭据不出机器）。"""
    # 启动即初始化后端，让配置问题在启动阶段就暴露（而非等第一次调用）
    backend = get_backend()
    warn(f"后端已就绪：{backend.name}（v{SERVER_VERSION}）")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
