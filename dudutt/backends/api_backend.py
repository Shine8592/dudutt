#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
官方 POP API 后端。

能力边界（如实声明，不粉饰）：
- 发布商品 ✅ 原生：pdd.ktt.group.create
- 改库存   ✅ 原生：pdd.ktt.goods.incr.quantity
- 下架商品 ⚠️ 变通：官方无下架接口，只能把库存全量置 0（效果≈售罄）
- 改价     ❌ 不支持：团创建后价格锁死，官方未开放修改接口

"变通"与"不支持"必须区分：前者能达成业务目标但有副作用，
后者根本做不到。Agent 据此决定是否降级到浏览器后端。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

from dudutt.api_map import (
    API_GOODS_INCR_QUANTITY,
    API_GOODS_QUERY_LIST,
    API_GOODS_QUERY_SINGLE,
    API_GROUP_CREATE,
    API_GROUP_QUERY_LIST,
    API_GROUP_QUERY_STATUS,
    group_status_label,
)
from dudutt.backends.base import (
    SUPPORT_NATIVE,
    SUPPORT_NONE,
    SUPPORT_WORKAROUND,
    Action,
    BaseBackend,
    Support,
    unsupported,
)
from dudutt.pop_client import PopClient, PopError


@dataclass
class ApiBackend(BaseBackend):
    """官方 API 后端。"""

    client: PopClient = None  # type: ignore[assignment]
    name: str = field(default="api", init=False)

    # ------------------------------------------------------------------
    # 能力协商
    # ------------------------------------------------------------------

    def capabilities(self) -> dict[str, Support]:
        return {
            Action.LIST_GROUPS: Support(
                SUPPORT_NATIVE, API_GROUP_QUERY_LIST.name, "起止时间差不能超过 7 天"
            ),
            Action.LIST_GOODS: Support(
                SUPPORT_NATIVE, API_GOODS_QUERY_LIST.name, "分页返回"
            ),
            Action.GET_GOODS: Support(
                SUPPORT_NATIVE, API_GOODS_QUERY_SINGLE.name, ""
            ),
            Action.PUBLISH_GOODS: Support(
                SUPPORT_NATIVE,
                API_GROUP_CREATE.name,
                "创建后价格即锁死，后续无法改价；is_save_preview=1 可先存预览团",
            ),
            Action.SET_STOCK: Support(
                SUPPORT_NATIVE,
                API_GOODS_INCR_QUANTITY.name,
                "modify_quantity_type=2 为全量设置",
            ),
            Action.DELIST_GOODS: Support(
                SUPPORT_WORKAROUND,
                f"{API_GOODS_INCR_QUANTITY.name}（库存归零）",
                "官方无下架接口。本实现把库存全量置 0，效果≈售罄；"
                "商品/团记录仍然存在，需彻底删除请用浏览器后端",
                alternative=(
                    "如需真正下架/删除：DUDUTT_BACKEND=browser "
                    "（需先完成登录与选择器校准）"
                ),
            ),
            Action.UPDATE_PRICE: Support(
                SUPPORT_NONE,
                "",
                "官方 API 无改价接口：团创建后价格即锁死，无法通过接口修改。",
                alternative=(
                    "方案一：改用浏览器后端（DUDUTT_BACKEND=browser）直接操作后台；"
                    "方案二：下架当前团后新建一个团，用新价格重新发布。"
                ),
            ),
        }

    # ------------------------------------------------------------------
    # 只读
    # ------------------------------------------------------------------

    def list_groups(
        self,
        start_update_time: Optional[int] = None,
        end_update_time: Optional[int] = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """查询团列表。

        官方要求 start/end 均为必填，且起止差不超过 7 天。
        未传时默认查最近 7 天，避免 Agent 每次都要自己算时间戳。
        """
        now_ms = int(time.time() * 1000)
        end = end_update_time or now_ms
        start = start_update_time or (end - 7 * 24 * 3600 * 1000)

        if start > end:
            return {
                "ok": False,
                "error": "start_update_time 不能晚于 end_update_time",
            }
        if end - start > 7 * 24 * 3600 * 1000:
            return {
                "ok": False,
                "error": "起止时间差不能超过 7 天（官方限制），请缩小查询范围",
            }

        data = self.client.call(
            API_GROUP_QUERY_LIST.name,
            {
                "start_update_time": start,
                "end_update_time": end,
                "page": page,
                "size": size,
            },
        )
        activities = (data or {}).get("activity_list") or []
        for a in activities:
            if isinstance(a, dict) and "status" in a:
                a["status_label"] = group_status_label(a.get("status"))
        return {
            "ok": True,
            "backend": self.name,
            "total": (data or {}).get("total"),
            "page": page,
            "size": size,
            "groups": activities,
        }

    def list_goods(
        self,
        activity_no: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """查询商品列表。"""
        biz: dict[str, Any] = {"page": page, "size": size}
        if activity_no:
            biz["activity_no"] = activity_no
        data = self.client.call(API_GOODS_QUERY_LIST.name, biz)
        return {
            "ok": True,
            "backend": self.name,
            "total": (data or {}).get("total"),
            "page": page,
            "size": size,
            "goods": (data or {}).get("goods_list") or [],
        }

    def get_goods(self, goods_id: int) -> dict:
        """查询单个商品详情。"""
        data = self.client.call(
            API_GOODS_QUERY_SINGLE.name, {"goods_id": goods_id}
        )
        result = (data or {}).get("result") or {}
        return {"ok": True, "backend": self.name, "goods": result}

    # ------------------------------------------------------------------
    # 写操作
    # ------------------------------------------------------------------

    def publish_goods(self, spec: dict) -> dict:
        """发布商品（创建团购）。

        spec 需包含 title / start_time / end_time / goods_list，
        其中 goods_list 每项需 category_name / goods_desc / goods_name / sku_list。
        """
        missing = [
            k for k in ("title", "start_time", "end_time", "goods_list")
            if not spec.get(k)
        ]
        if missing:
            return {
                "ok": False,
                "error": f"缺少必填参数：{', '.join(missing)}",
                "required": ["title", "start_time", "end_time", "goods_list"],
            }

        data = self.client.call(API_GROUP_CREATE.name, spec)
        activity_no = (data or {}).get("activity_no")
        out = {
            "ok": bool((data or {}).get("success", True)),
            "backend": self.name,
            "activity_no": activity_no,
            "via": API_GROUP_CREATE.name,
            "raw": data,
        }
        # 创建是异步的：立刻回查一次状态，让调用方知道是否真的建成了
        if activity_no:
            try:
                status = self.client.call(
                    API_GROUP_QUERY_STATUS.name, {"activity_no": activity_no}
                )
                out["status"] = status
            except PopError as e:
                out["status_check_error"] = str(e)
        return out

    def set_stock(
        self,
        goods_id: int,
        sku_id: int,
        quantity_delta: int,
        modify_quantity_type: int = 2,
    ) -> dict:
        """改库存。

        modify_quantity_type：1=增量修改，2=全量设置（默认全量，更符合直觉）
        """
        data = self.client.call(
            API_GOODS_INCR_QUANTITY.name,
            {
                "goods_id": goods_id,
                "sku_id": sku_id,
                "quantity_delta": quantity_delta,
                "modify_quantity_type": modify_quantity_type,
            },
        )
        return {
            "ok": bool((data or {}).get("success", True)),
            "backend": self.name,
            "goods_id": goods_id,
            "sku_id": sku_id,
            "quantity_delta": quantity_delta,
            "modify_quantity_type": modify_quantity_type,
            "mode": "增量" if modify_quantity_type == 1 else "全量设置",
            "via": API_GOODS_INCR_QUANTITY.name,
        }

    def delist_goods(
        self, goods_id: int, sku_ids: Optional[list[int]] = None, **kwargs
    ) -> dict:
        """下架商品（变通实现：库存全量归零）。

        ⚠️ 官方无下架接口。本方法把该商品所有 SKU 库存置 0，
        效果≈售罄下架，但商品记录仍然存在。
        需要真正删除请使用浏览器后端。
        """
        _ = kwargs
        # 先查商品拿到 sku 列表（未显式传入时）
        if not sku_ids:
            try:
                detail = self.get_goods(goods_id).get("goods") or {}
                sku_ids = [
                    s.get("sku_id")
                    for s in (detail.get("sku_list") or [])
                    if isinstance(s, dict) and s.get("sku_id")
                ]
            except PopError as e:
                return {
                    "ok": False,
                    "error": f"下架前查询商品失败：{e}",
                    "goods_id": goods_id,
                }

        if not sku_ids:
            return {
                "ok": False,
                "error": "未找到任何 SKU，无法通过库存归零变通下架",
                "goods_id": goods_id,
            }

        results = []
        for sku_id in sku_ids:
            try:
                r = self.set_stock(
                    goods_id=goods_id,
                    sku_id=sku_id,
                    quantity_delta=0,
                    modify_quantity_type=2,
                )
                results.append(r)
            except PopError as e:
                results.append({"ok": False, "sku_id": sku_id, "error": str(e)})

        ok = all(r.get("ok") for r in results)
        return {
            "ok": ok,
            "backend": self.name,
            "goods_id": goods_id,
            "method": "workaround_stock_zero",
            "caveat": (
                "官方无下架接口，已将该商品全部 SKU 库存置 0（效果≈售罄）。"
                "商品/团记录仍然存在；如需真正删除请使用浏览器后端。"
            ),
            "skus": results,
        }

    def update_price(self, **kwargs) -> dict:
        """改价 —— 官方 API 不支持，如实返回。"""
        return unsupported(
            Action.UPDATE_PRICE,
            self.name,
            "官方 API 无改价接口：团创建后价格即锁死，无法通过接口修改。",
            alternative=(
                "方案一：改用浏览器后端（DUDUTT_BACKEND=browser）直接操作后台；"
                "方案二：下架当前团后新建一个团，用新价格重新发布。"
            ),
        )

    def health_check(self) -> dict:
        """连通性检查：拉取拼多多服务器时间验证签名与网络。"""
        return self.client.health_check()


def build_api_backend() -> ApiBackend:
    """从环境变量构造官方 API 后端。"""
    return ApiBackend(client=PopClient.from_env())
