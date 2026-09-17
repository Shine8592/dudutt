#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
审计层：记录每一次写操作，支持追溯与回看。

为什么必须有：商品误下架、价格误改都是**真实经营损失**，
写操作的证据链是出事后唯一能复盘的东西。

设计（汲取自 duduExcel 的备份/回滚思想，但电商操作无法"回滚"，
因此改为"可追溯 + 可对账"）：
- JSONL 追加写，天然容错、可流式读取
- 每条记录含：时间、动作、后端、参数、结果、幂等键
- 默认落盘 ~/.dudutt/audit.jsonl，可用 DUDUTT_AUDIT_PATH 覆盖
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Optional

ENV_AUDIT_PATH = "DUDUTT_AUDIT_PATH"
DEFAULT_AUDIT_DIR = ".dudutt"
DEFAULT_AUDIT_FILE = "audit.jsonl"


def audit_path() -> Path:
    """返回审计日志路径，必要时创建父目录。"""
    custom = (os.environ.get(ENV_AUDIT_PATH) or "").strip()
    if custom:
        p = Path(custom).expanduser()
    else:
        p = Path.home() / DEFAULT_AUDIT_DIR / DEFAULT_AUDIT_FILE
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record(
    action: str,
    backend: str,
    params: dict,
    result: dict,
    *,
    idempotency_key: Optional[str] = None,
    dry_run: bool = False,
) -> dict:
    """追加一条审计记录，返回该条目。

    审计写失败**不应**阻断主流程（否则日志问题会导致业务动作失败），
    但会在返回值里带 warning 让调用方知晓。
    """
    entry = {
        "ts": time.time(),
        "iso": time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime()),
        "action": action,
        "backend": backend,
        "dry_run": dry_run,
        "idempotency_key": idempotency_key,
        "params": _safe(params),
        "ok": bool(result.get("ok")) if isinstance(result, dict) else None,
        "result_summary": _summary(result),
    }
    try:
        p = audit_path()
        with p.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        entry["audit_file"] = str(p)
    except Exception as e:
        entry["audit_warning"] = f"审计写入失败：{e}"
    return entry


def _safe(obj: Any, depth: int = 0) -> Any:
    """截断过深/过大的参数，避免审计文件被图片 base64 之类撑爆。"""
    if depth > 4:
        return "..."
    if isinstance(obj, dict):
        return {k: _safe(v, depth + 1) for k, v in list(obj.items())[:50]}
    if isinstance(obj, (list, tuple)):
        items = [_safe(v, depth + 1) for v in list(obj)[:50]]
        if len(obj) > 50:
            items.append(f"...(共{len(obj)}项)")
        return items
    if isinstance(obj, str) and len(obj) > 500:
        return obj[:500] + "...(已截断)"
    return obj


def _summary(result: Any) -> Any:
    """只保留结果的关键字段，避免审计文件膨胀。"""
    if not isinstance(result, dict):
        return str(result)[:200]
    keys = ("ok", "activity_no", "goods_id", "sku_id", "error", "note", "method",
            "old_price_in_fen", "new_price_in_fen", "quantity", "mode")
    return {k: result[k] for k in keys if k in result}


def tail(limit: int = 20) -> dict:
    """读取最近 N 条审计记录（倒序）。"""
    p = audit_path()
    if not p.exists():
        return {"ok": True, "entries": [], "audit_file": str(p), "note": "尚无审计记录"}
    try:
        lines = p.read_text(encoding="utf-8").splitlines()
    except Exception as e:
        return {"ok": False, "error": f"读取审计日志失败：{e}", "audit_file": str(p)}

    entries = []
    for line in reversed(lines[-max(limit * 3, limit):]):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except ValueError:
            continue
        if len(entries) >= limit:
            break
    return {
        "ok": True,
        "audit_file": str(p),
        "count": len(entries),
        "entries": entries,
    }
