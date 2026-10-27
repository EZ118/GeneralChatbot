# -*- coding: utf-8 -*-
"""Win32 剪贴板写入（替代 pyperclip）。"""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes

from ..constants import CLIPBOARD_RETRIES, CLIPBOARD_RETRY_DELAY

user32 = ctypes.WinDLL("user32", use_last_error=True)
kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

CF_UNICODETEXT = 13
GMEM_MOVEABLE = 0x0002
HGLOBAL = ctypes.c_void_p

user32.OpenClipboard.argtypes = [wintypes.HWND]
user32.OpenClipboard.restype = wintypes.BOOL
user32.CloseClipboard.argtypes = []
user32.CloseClipboard.restype = wintypes.BOOL
user32.EmptyClipboard.argtypes = []
user32.EmptyClipboard.restype = wintypes.BOOL
user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
user32.SetClipboardData.restype = wintypes.HANDLE

kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
kernel32.GlobalAlloc.restype = HGLOBAL
kernel32.GlobalLock.argtypes = [HGLOBAL]
kernel32.GlobalLock.restype = ctypes.c_void_p
kernel32.GlobalUnlock.argtypes = [HGLOBAL]
kernel32.GlobalUnlock.restype = wintypes.BOOL
kernel32.GlobalFree.argtypes = [HGLOBAL]
kernel32.GlobalFree.restype = HGLOBAL


class ClipboardError(RuntimeError):
    pass


def set_clipboard_text(text: str) -> None:
    """把文本写入剪贴板，剪贴板被其他程序短暂占用时自动重试。"""
    text = str(text or "").replace("\x00", " ")
    payload = text.encode("utf-16-le") + b"\x00\x00"

    last_error = 0
    for _ in range(CLIPBOARD_RETRIES):
        if not user32.OpenClipboard(None):
            last_error = ctypes.get_last_error()
            time.sleep(CLIPBOARD_RETRY_DELAY)
            continue
        try:
            if not user32.EmptyClipboard():
                last_error = ctypes.get_last_error()
                time.sleep(CLIPBOARD_RETRY_DELAY)
                continue

            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(payload))
            if not handle:
                last_error = ctypes.get_last_error()
                continue

            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                last_error = ctypes.get_last_error()
                kernel32.GlobalFree(handle)
                continue

            try:
                ctypes.memmove(pointer, payload, len(payload))
            finally:
                kernel32.GlobalUnlock(handle)

            if not user32.SetClipboardData(CF_UNICODETEXT, handle):
                last_error = ctypes.get_last_error()
                kernel32.GlobalFree(handle)
                continue

            # SetClipboardData 成功后内存归系统所有，不能 GlobalFree
            return
        finally:
            user32.CloseClipboard()
        # 正常情况下这里不会执行到

    raise ClipboardError(
        f"写入剪贴板失败（错误码 {last_error}）。"
        "可能有其他程序正在占用剪贴板，请稍后重试。"
    )
