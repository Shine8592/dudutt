#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
人工登录 CLI：保存快团团后台登录态，供浏览器后端复用。

用法：
    python -m dudutt.login                       # 默认存到 ~/.dudutt/ktt_state.json
    python -m dudutt.login --storage-state PATH  # 指定路径

流程：打开浏览器 → 人工扫码登录 → 回车确认 → 保存会话（含 cookie）
之后把该路径设为 DUDUTT_KTT_STORAGE_STATE 即可被浏览器后端使用。

为什么不自动登录：快团团用微信扫码，自动化登录既违反平台规则也不稳定。
人工扫码一次、复用会话是既合规又可靠的方式。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

DEFAULT_STATE = Path.home() / ".dudutt" / "ktt_state.json"
KTT_LOGIN_URL = "https://ktt.pinduoduo.com/login"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="人工扫码登录快团团后台并保存会话"
    )
    parser.add_argument(
        "--storage-state",
        default=str(DEFAULT_STATE),
        help=f"会话保存路径（默认 {DEFAULT_STATE}）",
    )
    parser.add_argument(
        "--url",
        default=KTT_LOGIN_URL,
        help=f"登录页地址（默认 {KTT_LOGIN_URL}）",
    )
    args = parser.parse_args()

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print(
            "未安装 playwright。请先执行：\n"
            '    pip install "dudutt[browser]"\n'
            "    python -m playwright install chromium",
            file=sys.stderr,
        )
        return 2

    state_path = Path(args.storage_state).expanduser()
    state_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"即将打开浏览器，请用微信扫码登录快团团后台。", file=sys.stderr)
    print(f"登录完成后回到本窗口按回车保存会话。", file=sys.stderr)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context()
        page = context.new_page()
        page.goto(args.url)
        try:
            input(">>> 登录完成后按回车保存会话...")
        except EOFError:
            pass
        context.storage_state(path=str(state_path))
        browser.close()

    print(f"会话已保存：{state_path}", file=sys.stderr)
    print(
        f"请设置环境变量后再启动服务：\n"
        f'    set {("DUDUTT_KTT_STORAGE_STATE=")}{state_path}   (Windows)\n'
        f'    export DUDUTT_KTT_STORAGE_STATE="{state_path}"  (macOS/Linux)',
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
