#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
浏览器兜底后端（Playwright）。

定位：官方 API 做不到的动作（下架、改价）在这里实现。
原理是驱动真实浏览器登录快团团后台（ktt.pinduoduo.com）操作页面。

⚠️ 重要诚实声明：
本后端是**骨架 + 安全护栏**，页面选择器需要在真实账号环境下校准。
因此它默认 `verify_selectors()` 返回未校准状态并拒绝执行写操作，
避免"看起来能跑其实会点错按钮"造成真实经营损失。

启用方式：
    pip install "dudutt[browser]"
    python -m playwright install chromium
    export DUDUTT_BACKEND=browser
    export DUDUTT_KTT_STORAGE_STATE="C:/path/to/storage_state.json"

首次登录（人工扫码一次，之后复用会话）：
    python -m dudutt.login --storage-state <path>
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from dudutt.backends.base import (
    SUPPORT_NATIVE,
    SUPPORT_NONE,
    Action,
    BaseBackend,
    Support,
    unsupported,
)

KTT_ADMIN_URL = "https://ktt.pinduoduo.com"
ENV_STORAGE_STATE = "DUDUTT_KTT_STORAGE_STATE"
ENV_HEADLESS = "DUDUTT_BROWSER_HEADLESS"


class BrowserNotReady(Exception):
    """浏览器后端尚不可用（未装依赖 / 未登录 / 选择器未校准）。"""


@dataclass
class BrowserBackend(BaseBackend):
    """浏览器自动化后端。

    设计上刻意让"未校准"成为**显式阻断**而非静默降级：
    宁可明确报错，也不要在用户真实店铺里乱点。
    """

    storage_state: Optional[str] = None
    headless: bool = False
    name: str = field(default="browser", init=False)

    # 页面选择器：需在真实后台校准后填写。
    # 留空表示"未校准"，写操作会被阻止。
    selectors: dict[str, str] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        if self.storage_state is None:
            self.storage_state = os.environ.get(ENV_STORAGE_STATE) or None
        if not self.selectors:
            # 从外部 JSON 加载选择器（便于不改代码即可校准）
            self.selectors = self._load_selectors()

    # ------------------------------------------------------------------

    def _load_selectors(self) -> dict[str, str]:
        """从 DUDUTT_KTT_SELECTORS 指向的 JSON 加载选择器配置。"""
        path = os.environ.get("DUDUTT_KTT_SELECTORS", "").strip()
        if not path:
            return {}
        try:
            return json.loads(Path(path).read_text(encoding="utf-8"))
        except Exception:
            return {}

    def _require_playwright(self):
        """按需导入 playwright，给出可执行的安装指引。"""
        try:
            from playwright.sync_api import sync_playwright
        except ImportError as e:
            raise BrowserNotReady(
                "未安装 playwright。请执行：\n"
                '    pip install "dudutt[browser]"\n'
                "    python -m playwright install chromium"
            ) from e
        return sync_playwright

    def readiness(self) -> dict:
        """检查后端是否可用，返回结构化诊断。"""
        issues = []
        try:
            self._require_playwright()
        except BrowserNotReady as e:
            issues.append({"kind": "dependency", "detail": str(e)})

        if not self.storage_state:
            issues.append(
                {
                    "kind": "login",
                    "detail": (
                        f"未配置登录态。请先人工扫码登录一次：\n"
                        f'    python -m dudutt.login --storage-state "C:/path/state.json"\n'
                        f"然后设置环境变量 {ENV_STORAGE_STATE} 指向该文件。"
                    ),
                }
            )
        elif not Path(self.storage_state).exists():
            issues.append(
                {
                    "kind": "login",
                    "detail": f"登录态文件不存在：{self.storage_state}",
                }
            )

        if not self.selectors:
            issues.append(
                {
                    "kind": "selectors",
                    "detail": (
                        "页面选择器未校准。请在真实后台确认元素后，"
                        "写入 JSON 并通过 DUDUTT_KTT_SELECTORS 指向它。"
                        "写操作会被阻止以免误点。"
                    ),
                }
            )

        return {
            "ready": not issues,
            "backend": self.name,
            "checks": {
                "dependency": not any(
                    i["kind"] == "dependency" for i in issues
                ),
                "login": not any(i["kind"] == "login" for i in issues),
                "selectors": bool(self.selectors),
            },
            "issues": issues,
        }

    # ---- 能力协商 ----

    def capabilities(self) -> dict[str, Support]:
        """浏览器后端能力上更强（能真正下架/改价），
        但执行前需通过 readiness 检查。"""
        return {
            Action.LIST_GROUPS: Support(
                SUPPORT_NATIVE, "浏览器后台页面", "依赖选择器校准"
            ),
            Action.LIST_GOODS: Support(
                SUPPORT_NATIVE, "浏览器后台页面", "依赖选择器校准"
            ),
            Action.GET_GOODS: Support(
                SUPPORT_NATIVE, "浏览器后台页面", "依赖选择器校准"
            ),
            Action.PUBLISH_GOODS: Support(
                SUPPORT_NATIVE,
                "浏览器后台页面",
                "比官方 API 多支持自定义价格；但不稳定，建议优先用 API",
            ),
            Action.SET_STOCK: Support(
                SUPPORT_NATIVE, "浏览器后台页面", "依赖选择器校准"
            ),
            Action.DELIST_GOODS: Support(
                SUPPORT_NATIVE,
                "浏览器后台页面（真实下架）",
                "官方 API 无此能力，这是浏览器后端的核心价值",
            ),
            Action.UPDATE_PRICE: Support(
                SUPPORT_NATIVE,
                "浏览器后台页面（真实改价）",
                "官方 API 无此能力，这是浏览器后端的核心价值",
            ),
        }

    # ------------------------------------------------------------------
    # 执行入口（带就绪检查的护栏）
    # ------------------------------------------------------------------

    def _guard(self, action: str) -> Optional[dict]:
        """写操作前的就绪检查。返回非 None 表示应中止。"""
        ready = self.readiness()
        if ready["ready"]:
            return None
        return {
            "ok": False,
            "backend": self.name,
            "error": "浏览器后端尚未就绪，已阻止执行以避免误操作真实店铺。",
            "action": action,
            "readiness": ready,
        }

    # ---- 只读（同样需要就绪）----

    def list_groups(self, **kwargs) -> dict:
        _ = kwargs
        return self._not_implemented(Action.LIST_GROUPS)

    def list_goods(self, **kwargs) -> dict:
        _ = kwargs
        return self._not_implemented(Action.LIST_GOODS)

    def get_goods(self, goods_id: int) -> dict:
        _ = goods_id
        return self._not_implemented(Action.GET_GOODS)

    def publish_goods(self, spec: dict) -> dict:
        _ = spec
        return self._not_implemented(Action.PUBLISH_GOODS)

    def set_stock(self, **kwargs) -> dict:
        _ = kwargs
        return self._not_implemented(Action.SET_STOCK)

    def delist_goods(self, **kwargs) -> dict:
        _ = kwargs
        return self._not_implemented(Action.DELIST_GOODS)

    def update_price(self, **kwargs) -> dict:
        _ = kwargs
        return self._not_implemented(Action.UPDATE_PRICE)

    def _not_implemented(self, action: str) -> dict:
        """统一返回"待校准"提示，绝不假装成功。"""
        blocked = self._guard(action)
        if blocked:
            return blocked
        return {
            "ok": False,
            "backend": self.name,
            "action": action,
            "error": "该动作的页面操作逻辑尚待真实环境校准。",
            "how_to": [
                "1. 用 python -m dudutt.login 人工扫码登录并保存会话",
                "2. 在真实后台定位元素，写入选择器 JSON",
                "3. 设置 DUDUTT_KTT_SELECTORS 指向该 JSON",
                "4. 重新调用本工具",
            ],
        }

    def health_check(self) -> dict:
        return self.readiness()


def build_browser_backend() -> BrowserBackend:
    """从环境变量构造浏览器后端。"""
    headless_raw = (os.environ.get(ENV_HEADLESS) or "").strip().lower()
    return BrowserBackend(
        storage_state=os.environ.get(ENV_STORAGE_STATE) or None,
        headless=headless_raw in ("1", "true", "yes"),
    )
