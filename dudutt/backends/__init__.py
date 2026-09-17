#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
后端工厂：按环境变量选择后端，支持自动降级。

选择逻辑（DUDUTT_BACKEND）：
- "api"（默认）：官方 POP API。缺凭据时报错并提示改用 mock。
- "browser"：浏览器自动化。
- "mock"：内存模拟，无需凭据，用于演示与开发。
- "auto"：优先 api，凭据缺失则退 browser，再缺则退 mock（每次降级都明确告知）。

为什么需要 auto：Agent 拿到明确的后端名，才知道后续结果的可信边界
（mock 的结果不能当真实经营数据用）。
"""

from __future__ import annotations

import os
import sys

from dudutt.backends.base import BaseBackend
from dudutt.backends.mock_backend import MockBackend

ENV_BACKEND = "DUDUTT_BACKEND"

# 后端名
BACKEND_API = "api"
BACKEND_BROWSER = "browser"
BACKEND_MOCK = "mock"
BACKEND_AUTO = "auto"


def _env() -> dict[str, str]:
    return dict(os.environ)


def _has_api_credentials(env: dict[str, str]) -> bool:
    return bool(
        (env.get("DUDUTT_CLIENT_ID") or "").strip()
        and (env.get("DUDUTT_CLIENT_SECRET") or "").strip()
    )


def build_backend(name: str | None = None) -> tuple[BaseBackend, list[str]]:
    """构造后端。

    返回 (backend, notes)：notes 记录降级原因，供上层告知 Agent/用户。
    """
    env = _env()
    requested = (name or env.get(ENV_BACKEND) or BACKEND_API).strip().lower()
    notes: list[str] = []

    def make_api() -> BaseBackend:
        from dudutt.backends.api_backend import build_api_backend

        return build_api_backend()

    def make_browser() -> BaseBackend:
        from dudutt.backends.browser_backend import build_browser_backend

        return build_browser_backend()

    if requested == BACKEND_MOCK:
        return MockBackend(), ["使用模拟后端：数据不触达快团团，仅供演示与测试。"]

    if requested == BACKEND_BROWSER:
        return make_browser(), []

    if requested == BACKEND_AUTO:
        if _has_api_credentials(env):
            try:
                return make_api(), []
            except Exception as e:  # 凭据在但构造失败
                notes.append(f"官方 API 后端构造失败（{e}），尝试浏览器后端。")
        else:
            notes.append("未检测到官方 API 凭据，尝试浏览器后端。")
        try:
            backend = make_browser()
            # 浏览器后端即使构造成功也可能未就绪，交给 readiness 判断
            return backend, notes
        except Exception as e:
            notes.append(f"浏览器后端构造失败（{e}），降级为模拟后端。")
            return MockBackend(), notes

    # 默认：官方 API
    if not _has_api_credentials(env):
        # 明确报错，不静默降级——否则用户会以为在用真 API
        raise RuntimeError(
            "未配置官方 API 凭据。请设置环境变量：\n"
            "    DUDUTT_CLIENT_ID=你的client_id\n"
            "    DUDUTT_CLIENT_SECRET=你的client_secret\n"
            "    DUDUTT_ACCESS_TOKEN=你的access_token\n\n"
            "如暂时没有凭据：\n"
            "    - 想跑通流程演示：DUDUTT_BACKEND=mock\n"
            "    - 想用浏览器兜底：DUDUTT_BACKEND=browser\n"
            "    - 想自动选择：    DUDUTT_BACKEND=auto\n\n"
            "资质申请流程见 docs/SETUP.md"
        )
    return make_api(), notes


def warn(msg: str) -> None:
    """把提示写到 stderr，保证 stdout 是纯净的 MCP 协议流。"""
    print(f"[dudutt] {msg}", file=sys.stderr, flush=True)
