#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
跨平台输出兼容层。

问题：Windows 上 Python 的 stdout/stderr 默认用系统 ANSI 代码页
（简体中文 Windows 是 cp936/GBK，英文是 cp1252）。直接 print 中文会抛：

    UnicodeEncodeError: 'gbk' codec can't encode character ...

后果：
- CI 上 Windows job 全部崩溃而 Ubuntu 正常（Ubuntu 默认 UTF-8）
- 用户本地终端也可能遇到

处理：把标准输出/错误流重配置为 UTF-8。日志/调试输出用 replace 容错，
保证极端字符不会让整个服务因为一句日志而挂掉。
"""

from __future__ import annotations

import sys


def force_utf8(streams=None) -> None:
    """把标准流切换为 UTF-8。

    参数：
    - streams：可选的流序列，默认 (sys.stdout, sys.stderr)

    注意：某些流（被重定向到不支持 reconfigure 的对象）会没有该方法，
    此时静默跳过——不能因为日志编码问题让主流程失败。
    """
    targets = streams if streams is not None else (sys.stdout, sys.stderr)
    for stream in targets:
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            # 流不支持重配置（如已被重定向到自定义对象），忽略
            pass
