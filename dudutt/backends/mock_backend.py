#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
模拟后端（Mock）。

用途：在没有企业资质 / 未拿到凭据时，让整条链路（工具层 → 动作 → 返回）
可以被完整验证与演示。**它明确标记自己是 mock**，绝不冒充真实数据。

设计原则（防止"假成功"污染真实判断）：
- 所有返回体都带 "mock": true
- 初始化时打印醒目提示到 stderr
- 数据存在内存里，进程结束即丢弃
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from dudutt.backends.base import (
    SUPPORT_NATIVE,
    SUPPORT_WORKAROUND,
    Action,
    BaseBackend,
    Support,
    unsupported,
)


@dataclass
class MockBackend(BaseBackend):
    """内存模拟后端，用于演示与测试。"""

    name: str = field(default="mock", init=False)
    _seq: int = 0
    _groups: dict[str, dict] = field(default_factory=dict, repr=False)
    _goods: dict[int, dict] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        self._seed()

    # ------------------------------------------------------------------

    def _next_id(self) -> int:
        self._seq += 1
        return 100000 + self._seq

    def _seed(self) -> None:
        """预置一条示例数据，让只读工具立刻有内容可看。"""
        now = int(time.time())
        act = "KTT20260101001"
        self._groups[act] = {
            "activity_no": act,
            "title": "【示例团】云南高山沃柑 5斤装",
            "status": 1,
            "status_label": "跟团中",
            "create_time": now * 1000,
            "start_time": now * 1000,
            "end_time": (now + 7 * 86400) * 1000,
            "update_time": now * 1000,
            "is_help_sell": 0,
        }
        gid = self._next_id()
        self._goods[gid] = {
            "goods_id": gid,
            "activity_no": act,
            "category_name": "生鲜水果",
            "goods_name": "云南高山沃柑 5斤装",
            "goods_desc": "现摘现发，甜度 13+，坏果包赔。",
            "goods_image_list": [],
            "market_price": 4980,
            "limit_buy": 0,
            "is_activity_delete": 0,
            "create_time": now * 1000,
            "update_time": now * 1000,
            "sku_list": [
                {
                    "sku_id": 1,
                    "price_in_fen": 2980,
                    "quantity": 100,
                    "total_quantity": 100,
                    "sold_quantity": 0,
                    "quantity_type": 0,
                    "spec_list": [],
                }
            ],
        }

    # ---- 能力协商 ----

    def capabilities(self) -> dict[str, Support]:
        """mock 后端刻意声明为"能力完整"——它代表理想目标态，
        用于验证工具层在能力齐全时的行为。"""
        return {
            Action.LIST_GROUPS: Support(SUPPORT_NATIVE, "mock_memory", ""),
            Action.LIST_GOODS: Support(SUPPORT_NATIVE, "mock_memory", ""),
            Action.GET_GOODS: Support(SUPPORT_NATIVE, "mock_memory", ""),
            Action.PUBLISH_GOODS: Support(SUPPORT_NATIVE, "mock_memory", ""),
            Action.SET_STOCK: Support(SUPPORT_NATIVE, "mock_memory", ""),
            Action.DELIST_GOODS: Support(
                SUPPORT_NATIVE, "mock_memory", "mock 模拟真正的下架（状态置为已删除）"
            ),
            Action.UPDATE_PRICE: Support(
                SUPPORT_NATIVE, "mock_memory", "mock 模拟真实改价"
            ),
        }

    # ---- 只读 ----

    def list_groups(
        self,
        start_update_time: Optional[int] = None,
        end_update_time: Optional[int] = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        groups = list(self._groups.values())
        return {
            "ok": True,
            "mock": True,
            "backend": self.name,
            "total": len(groups),
            "page": page,
            "size": size,
            "groups": groups,
        }

    def list_goods(
        self,
        activity_no: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        goods = list(self._goods.values())
        if activity_no:
            goods = [g for g in goods if g.get("activity_no") == activity_no]
        return {
            "ok": True,
            "mock": True,
            "backend": self.name,
            "total": len(goods),
            "page": page,
            "size": size,
            "goods": goods,
        }

    def get_goods(self, goods_id: int) -> dict:
        g = self._goods.get(int(goods_id))
        if not g:
            return {
                "ok": False,
                "mock": True,
                "error": f"商品不存在：{goods_id}",
            }
        return {"ok": True, "mock": True, "backend": self.name, "goods": g}

    # ---- 写操作 ----

    def publish_goods(self, spec: dict) -> dict:
        now = int(time.time())
        act = f"KTT{now}"
        self._groups[act] = {
            "activity_no": act,
            "title": spec.get("title"),
            "status": -10 if spec.get("is_save_preview") == 1 else 1,
            "status_label": "待发布" if spec.get("is_save_preview") == 1 else "跟团中",
            "create_time": now * 1000,
            "start_time": spec.get("start_time"),
            "end_time": spec.get("end_time"),
            "update_time": now * 1000,
            "is_help_sell": 0,
        }
        created = []
        for item in spec.get("goods_list") or []:
            gid = self._next_id()
            sku_list = []
            for sku in item.get("sku_list") or []:
                sku_list.append(
                    {
                        "sku_id": self._next_id(),
                        "price_in_fen": sku.get("price_in_fen", 0),
                        "quantity": sku.get("total_quantity", 0),
                        "total_quantity": sku.get("total_quantity", 0),
                        "sold_quantity": 0,
                        "quantity_type": sku.get("quantity_type", 0),
                        "spec_id_list": sku.get("spec_id_list", []),
                        "thumb_url": sku.get("thumb_url"),
                        "external_sku_id": sku.get("external_sku_id"),
                    }
                )
            self._goods[gid] = {
                "goods_id": gid,
                "activity_no": act,
                "category_name": item.get("category_name"),
                "goods_name": item.get("goods_name"),
                "goods_desc": item.get("goods_desc"),
                "goods_image_list": item.get("pic_url_list") or [],
                "market_price": item.get("market_price", 0),
                "limit_buy": item.get("limit_buy", 0),
                "is_activity_delete": 0,
                "create_time": now * 1000,
                "update_time": now * 1000,
                "sku_list": sku_list,
            }
            created.append(gid)

        return {
            "ok": True,
            "mock": True,
            "backend": self.name,
            "activity_no": act,
            "goods_ids": created,
            "is_preview": spec.get("is_save_preview") == 1,
            "via": "mock_memory",
        }

    def set_stock(
        self,
        goods_id: int,
        sku_id: int,
        quantity_delta: int,
        modify_quantity_type: int = 2,
    ) -> dict:
        g = self._goods.get(int(goods_id))
        if not g:
            return {"ok": False, "mock": True, "error": f"商品不存在：{goods_id}"}
        for sku in g.get("sku_list") or []:
            if int(sku.get("sku_id", 0)) == int(sku_id):
                if modify_quantity_type == 1:
                    sku["quantity"] = max(
                        0, int(sku.get("quantity", 0)) + int(quantity_delta)
                    )
                else:
                    sku["quantity"] = max(0, int(quantity_delta))
                sku["total_quantity"] = sku["quantity"]
                g["update_time"] = int(time.time()) * 1000
                return {
                    "ok": True,
                    "mock": True,
                    "backend": self.name,
                    "goods_id": int(goods_id),
                    "sku_id": int(sku_id),
                    "quantity": sku["quantity"],
                    "mode": "增量" if modify_quantity_type == 1 else "全量设置",
                }
        return {
            "ok": False,
            "mock": True,
            "error": f"SKU 不存在：{sku_id}",
        }

    def delist_goods(
        self, goods_id: int, sku_ids: Optional[list[int]] = None, **kwargs
    ) -> dict:
        """mock 下架：把商品标记为已删除（模拟真实下架效果）。"""
        _ = (sku_ids, kwargs)
        g = self._goods.get(int(goods_id))
        if not g:
            return {"ok": False, "mock": True, "error": f"商品不存在：{goods_id}"}
        g["is_activity_delete"] = 1
        for sku in g.get("sku_list") or []:
            sku["quantity"] = 0
            sku["total_quantity"] = 0
        act = g.get("activity_no")
        if act in self._groups:
            self._groups[act]["status"] = 30
            self._groups[act]["status_label"] = "已删除"
        return {
            "ok": True,
            "mock": True,
            "backend": self.name,
            "goods_id": int(goods_id),
            "method": "delist",
            "note": "mock 模拟真实下架（商品标记删除、团状态置为已删除）",
        }

    def update_price(
        self, goods_id: int, sku_id: int, price_in_fen: int, **kwargs
    ) -> dict:
        """mock 改价：直接改 SKU 价格（模拟浏览器后端的真实能力）。"""
        _ = kwargs
        g = self._goods.get(int(goods_id))
        if not g:
            return {"ok": False, "mock": True, "error": f"商品不存在：{goods_id}"}
        for sku in g.get("sku_list") or []:
            if int(sku.get("sku_id", 0)) == int(sku_id):
                old = sku.get("price_in_fen")
                sku["price_in_fen"] = int(price_in_fen)
                g["update_time"] = int(time.time()) * 1000
                return {
                    "ok": True,
                    "mock": True,
                    "backend": self.name,
                    "goods_id": int(goods_id),
                    "sku_id": int(sku_id),
                    "old_price_in_fen": old,
                    "new_price_in_fen": int(price_in_fen),
                }
        return {"ok": False, "mock": True, "error": f"SKU 不存在：{sku_id}"}

    def health_check(self) -> dict:
        return {
            "ok": True,
            "mock": True,
            "backend": self.name,
            "note": "模拟后端：数据仅存于内存，进程结束即丢弃，不会触达快团团。",
        }
