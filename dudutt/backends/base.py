#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端抽象层：定义「快团团网店管理动作」的稳定接口。

为什么要抽象：官方 API 与浏览器自动化能力**不对等**——
官方没有「下架」「改价」接口，而浏览器有。若把两者混在一个类里，
调用方永远分不清"失败是因为没权限、还是因为根本没这功能"。

因此定义 Action（动作）+ Capability（能力声明）两层：
- 每个后端如实声明自己支持哪些动作（supported / 变通 / 不支持）
- 调用方先查能力，再执行；不支持时得到明确错误而非幻觉结果

汲取自 sbroenne 系列 MCP 的"多操作分发"模式：
工具层只负责参数校验与分发，具体实现落在后端。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional

# ---------------------------------------------------------------------------
# 动作定义
# ---------------------------------------------------------------------------


class Action:
    """动作名常量（避免各处硬编码字符串拼错）。"""

    CAPABILITIES = "capabilities"
    LIST_GROUPS = "list_groups"
    LIST_GOODS = "list_goods"
    GET_GOODS = "get_goods"
    PUBLISH_GOODS = "publish_goods"
    DELIST_GOODS = "delist_goods"
    UPDATE_PRICE = "update_price"
    SET_STOCK = "set_stock"
    HEALTH_CHECK = "health_check"


# 支持程度
SUPPORT_NATIVE = "native"  # 原生直接支持
SUPPORT_WORKAROUND = "workaround"  # 支持，但需变通（副作用已说明）
SUPPORT_NONE = "none"  # 不支持

# 写操作（需要护栏的动作集合）
WRITE_ACTIONS = frozenset(
    {
        Action.PUBLISH_GOODS,
        Action.DELIST_GOODS,
        Action.UPDATE_PRICE,
        Action.SET_STOCK,
    }
)

# 所有动作
ALL_ACTIONS = (
    Action.LIST_GROUPS,
    Action.LIST_GOODS,
    Action.GET_GOODS,
    Action.PUBLISH_GOODS,
    Action.DELIST_GOODS,
    Action.UPDATE_PRICE,
    Action.SET_STOCK,
)


@dataclass(frozen=True)
class Support:
    """一个动作在某后端下的支持情况。"""

    level: str  # SUPPORT_NATIVE / SUPPORT_WORKAROUND / SUPPORT_NONE
    via: str = ""  # 实现途径（接口名或"浏览器后台"）
    caveat: str = ""  # 副作用 / 限制说明（必须如实告知）
    alternative: str = ""  # 不支持时的替代方案（在能力声明处给出，避免丢失）

    @property
    def usable(self) -> bool:
        return self.level != SUPPORT_NONE


def unsupported(action: str, backend: str, reason: str, alternative: str = "") -> dict:
    """构造一个"不支持"的标准错误返回。

    统一格式让 Agent 能稳定解析，并看到可行的替代方案。
    """
    out = {
        "ok": False,
        "unsupported": True,
        "action": action,
        "backend": backend,
        "error": reason,
    }
    if alternative:
        out["alternative"] = alternative
    return out


def blocked_payload(
    action: str, backend: str, support: "Support", hint: str = ""
) -> dict:
    """由 Support 声明直接构造阻断返回。

    为什么统一走这里：替代方案必须写在**能力声明**处（Support.alternative），
    否则一旦被 _guard_write 提前拦截，后端实现里的替代方案就永远看不到。
    """
    out = {
        "ok": False,
        "unsupported": True,
        "action": action,
        "backend": backend,
        "error": support.caveat or f"当前后端（{backend}）不支持该动作。",
    }
    if support.alternative:
        out["alternative"] = support.alternative
    if hint:
        out["hint"] = hint
    return out


class BackendError(Exception):
    """后端执行失败。消息面向 Agent，需可读、可纠正。"""


# ---------------------------------------------------------------------------
# 后端基类
# ---------------------------------------------------------------------------


@dataclass
class BaseBackend(ABC):
    """后端基类：所有具体后端实现此接口。"""

    name: str = "base"

    # ---- 能力协商 ----

    @abstractmethod
    def capabilities(self) -> dict[str, Support]:
        """返回本后端对每个动作的支持情况。"""

    def support_for(self, action: str) -> Support:
        """查询单个动作的支持情况。"""
        caps = self.capabilities()
        return caps.get(action, Support(SUPPORT_NONE, "", "未知动作"))

    def describe(self) -> dict:
        """给 Agent 看的能力说明（capabilities 工具的返回体）。"""
        caps = self.capabilities()
        entries = []
        for action in ALL_ACTIONS:
            s = caps.get(action)
            if s is None:
                continue
            entries.append(
                {
                    "action": action,
                    "support": s.level,
                    "via": s.via,
                    "caveat": s.caveat,
                    "alternative": s.alternative,
                    "usable": s.usable,
                }
            )
        return {
            "backend": self.name,
            "actions": entries,
            "write_actions": sorted(WRITE_ACTIONS),
        }

    # ---- 只读动作（各后端按需重写）----

    @abstractmethod
    def list_groups(
        self,
        start_update_time: Optional[int] = None,
        end_update_time: Optional[int] = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """查询团列表。"""

    @abstractmethod
    def list_goods(
        self,
        activity_no: Optional[str] = None,
        page: int = 1,
        size: int = 20,
    ) -> dict:
        """查询商品列表。"""

    @abstractmethod
    def get_goods(self, goods_id: int) -> dict:
        """查询单个商品详情。"""

    # ---- 写动作（各后端按需重写）----

    def publish_goods(self, spec: dict) -> dict:
        """发布商品。"""
        raise NotImplementedError

    def delist_goods(self, **kwargs) -> dict:
        """下架商品。"""
        raise NotImplementedError

    def update_price(self, **kwargs) -> dict:
        """改价。"""
        raise NotImplementedError

    def set_stock(self, **kwargs) -> dict:
        """改库存。"""
        raise NotImplementedError

    def health_check(self) -> dict:
        """连通性检查。"""
        return {"ok": True, "backend": self.name}
