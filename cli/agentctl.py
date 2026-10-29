#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""兼容入口：真正的 CLI 在 skills/tmp-preview-agent/scripts/agentctl.py。

拆成两处是故意的：技能包要能整体拷走单独用（一个文件、只用标准库），
而仓库里 cli/agentctl.py 这个路径已经写在文档和别人的脚本里，不能断。
"""
import pathlib
import runpy
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
TARGET = ROOT / "skills" / "tmp-preview-agent" / "scripts" / "agentctl.py"

if not TARGET.exists():
    sys.exit(f"找不到 CLI 实现：{TARGET}")

runpy.run_path(str(TARGET), run_name="__main__")
