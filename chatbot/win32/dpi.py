# -*- coding: utf-8 -*-
"""进程 DPI 感知。必须在创建 Tk 根窗口之前调用。"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2 = ctypes.c_void_p(-4)


def enable_dpi_awareness() -> str:
    """返回实际使用的模式，便于写日志。"""
    if sys.platform != "win32":
        return "non-windows"

    user32 = ctypes.WinDLL("user32", use_last_error=True)
    try:
        user32.SetProcessDpiAwarenessContext.argtypes = [ctypes.c_void_p]
        user32.SetProcessDpiAwarenessContext.restype = wintypes.BOOL
        if user32.SetProcessDpiAwarenessContext(
            DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2
        ):
            return "per-monitor-v2"
    except Exception:
        pass

    try:
        shcore = ctypes.WinDLL("shcore", use_last_error=True)
        shcore.SetProcessDpiAwareness.argtypes = [ctypes.c_int]
        shcore.SetProcessDpiAwareness.restype = ctypes.c_long
        # 2 = PROCESS_PER_MONITOR_DPI_AWARE
        if shcore.SetProcessDpiAwareness(2) == 0:
            return "per-monitor"
    except Exception:
        pass

    try:
        user32.SetProcessDPIAware()
        return "system"
    except Exception:
        return "none"


def windows_build() -> int:
    try:
        return int(sys.getwindowsversion().build)
    except Exception:
        return 0
