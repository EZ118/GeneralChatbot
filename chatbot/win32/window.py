# -*- coding: utf-8 -*-
"""Tk 顶层窗口的 Win32 定位辅助。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)

HWND_TOPMOST = wintypes.HWND(-1)
SWP_SHOWWINDOW = 0x0040
SWP_NOACTIVATE = 0x0010

user32.GetParent.argtypes = [wintypes.HWND]
user32.GetParent.restype = wintypes.HWND
user32.GetClassNameW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
user32.GetClassNameW.restype = ctypes.c_int
user32.SetWindowPos.argtypes = [
    wintypes.HWND,
    wintypes.HWND,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.UINT,
]
user32.SetWindowPos.restype = wintypes.BOOL


def _class_name(hwnd: int) -> str:
    buffer = ctypes.create_unicode_buffer(128)
    user32.GetClassNameW(hwnd, buffer, 128)
    return buffer.value


def toplevel_hwnd(widget) -> int:  # noqa: ANN001
    hwnd = int(widget.winfo_id())
    parent = user32.GetParent(hwnd)
    if parent and _class_name(parent) == "TkTopLevel":
        return int(parent)
    return hwnd


def place_topmost(
    widget,  # noqa: ANN001
    left: int,
    top: int,
    width: int,
    height: int,
    activate: bool = True,
) -> bool:
    flags = SWP_SHOWWINDOW | (0 if activate else SWP_NOACTIVATE)
    return bool(
        user32.SetWindowPos(
            toplevel_hwnd(widget),
            HWND_TOPMOST,
            int(left),
            int(top),
            int(width),
            int(height),
            flags,
        )
    )
