# -*- coding: utf-8 -*-
"""应用路径。所有可写文件都放在 exe / main.py 所在目录。"""

from __future__ import annotations

import sys
from pathlib import Path


def _app_dir() -> Path:
    # PyInstaller
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent

    # Nuitka（有时 sys.executable 仍指向 python.exe，用 argv[0] 兜底）
    try:
        exe = Path(sys.executable).resolve()
        if exe.name.lower() not in {"python.exe", "pythonw.exe"}:
            return exe.parent
    except Exception:
        pass
    try:
        argv0 = Path(sys.argv[0]).resolve()
        if argv0.suffix.lower() == ".exe":
            return argv0.parent
    except Exception:
        pass

    # 源码运行：chatbot/ 的父目录
    return Path(__file__).resolve().parent.parent


APP_DIR = _app_dir()
SETTINGS_FILE = APP_DIR / "settings.json"
LEGACY_SETTINGS_FILE = APP_DIR / "chatbot.json"
MEMORY_FILE = APP_DIR / "memory.json"
LOG_FILE = APP_DIR / "chatbot.log"
