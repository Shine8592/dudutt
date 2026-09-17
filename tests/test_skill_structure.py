#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""校验 dudutt SKILL 的结构与 frontmatter 格式。"""

import re
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# 相对定位：本文件在 tests/ 下，SKILL 在 ../skill/dudutt/
# ⚠️ 不能用绝对路径——CI 在 Linux 上跑，Windows 路径不存在（此为曾经踩过的坑）
SRC = Path(__file__).resolve().parent.parent / "skill" / "dudutt"
FAIL = 0


def check(name, cond, detail=""):
    global FAIL
    print(f"  [{'PASS' if cond else 'FAIL'}] {name} {detail if not cond else ''}")
    if not cond:
        FAIL += 1


def main():
    if not (SRC / "SKILL.md").exists():
        print(f"[FAIL] 找不到 SKILL.md：{SRC}")
        return 1

    text = (SRC / "SKILL.md").read_text(encoding="utf-8")
    m = re.match(r"^---\r?\n(.*?)\r?\n---\r?\n", text, re.S)
    check("frontmatter 可解析", bool(m))
    if not m:
        return 1
    fm = m.group(1)

    print("\n--- frontmatter 字段 ---")
    for line in fm.splitlines():
        if ":" in line and not line.startswith(" "):
            k, v = line.split(":", 1)
            print(f"  {k.strip()}: {v.strip()[:65]}{'...' if len(v) > 65 else ''}")

    print("\n--- 校验 ---")
    check("有 name 字段", bool(re.search(r"^name:\s*\S+", fm, re.M)))
    check("有 description 字段", bool(re.search(r"^description:\s*\S+", fm, re.M)))
    nm = re.search(r"^name:\s*(\S+)", fm, re.M)
    check("name 与目录名一致", nm and nm.group(1) == "dudutt",
          f"got={nm.group(1) if nm else None}")

    desc = re.search(r"^description:\s*(.+)$", fm, re.M)
    if desc:
        d = desc.group(1)
        check("description 长度合理(<=500)", len(d) <= 500, f"len={len(d)}")
        check("description 有触发词", "快团团" in d)
        check("description 有排除条件(Do NOT)",
              "Do NOT" in d or "不要" in d or "不使用" in d)

    print("\n--- 引用文件 ---")
    refs = sorted(set(re.findall(r"references/([a-z\-]+\.md)", text)))
    for r in refs:
        p = SRC / "references" / r
        check(f"references/{r}", p.exists())

    print("\n--- 内容完整性 ---")
    check("含安全铁律章节", "铁律" in text)
    check("含下架能力说明", "下架" in text)
    check("含改价能力说明", "改价" in text)
    check("含 data-testid 指引", "data-testid" in text)
    check("含危险操作警告", "不可逆" in text or "不能撤销" in text)
    check("警告不要调内部接口", "内部接口" in text or "严禁" in text)

    total = sum(f.stat().st_size for f in SRC.rglob("*") if f.is_file())
    n = len([f for f in SRC.rglob("*") if f.is_file()])
    print(f"\n共 {n} 个文件，{total / 1024:.1f} KB")

    print("\n" + "=" * 50)
    print("结果：" + ("全部通过" if FAIL == 0 else f"{FAIL} 项失败"))
    print("=" * 50)
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
