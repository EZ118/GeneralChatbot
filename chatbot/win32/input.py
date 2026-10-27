# -*- coding: utf-8 -*-
"""Win32 鼠标/键盘输入（替代 pyautogui）。"""

from __future__ import annotations

import ctypes
import re
import time
from ctypes import wintypes

from ..constants import (
    SEND_CLICK_WAIT,
    SEND_ENTER_WAIT,
    SEND_PASTE_WAIT,
    SEND_SELECT_WAIT,
)
from .clipboard import ClipboardError, set_clipboard_text

user32 = ctypes.WinDLL("user32", use_last_error=True)

INPUT_MOUSE = 0
INPUT_KEYBOARD = 1
KEYEVENTF_KEYUP = 0x0002
MOUSEEVENTF_LEFTDOWN = 0x0002
MOUSEEVENTF_LEFTUP = 0x0004

VK_CONTROL = 0x11
VK_A = 0x41
VK_V = 0x56
VK_RETURN = 0x0D

ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", wintypes.LONG),
        ("dy", wintypes.LONG),
        ("mouseData", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", wintypes.WORD),
        ("wScan", wintypes.WORD),
        ("dwFlags", wintypes.DWORD),
        ("time", wintypes.DWORD),
        ("dwExtraInfo", ULONG_PTR),
    ]


class HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", wintypes.DWORD),
        ("wParamL", wintypes.WORD),
        ("wParamH", wintypes.WORD),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", MOUSEINPUT),
        ("ki", KEYBDINPUT),
        ("hi", HARDWAREINPUT),
    ]


class INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", wintypes.DWORD),
        ("u", _INPUT_UNION),
    ]


user32.SendInput.argtypes = [wintypes.UINT, ctypes.POINTER(INPUT), ctypes.c_int]
user32.SendInput.restype = wintypes.UINT
user32.SetCursorPos.argtypes = [ctypes.c_int, ctypes.c_int]
user32.SetCursorPos.restype = wintypes.BOOL


class InputError(RuntimeError):
    pass


def _send(inp: INPUT) -> None:
    sent = user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))
    if sent != 1:
        error = ctypes.get_last_error()
        hint = ""
        if error in (0, 5):
            hint = " 如果目标聊天程序以管理员身份运行，请用管理员身份启动本程序。"
        raise InputError(f"SendInput 失败（错误码 {error}）。{hint}")


def _mouse(flags: int) -> None:
    inp = INPUT()
    inp.type = INPUT_MOUSE
    inp.mi = MOUSEINPUT(0, 0, 0, flags, 0, 0)
    _send(inp)


def _key(vk: int, up: bool = False) -> None:
    inp = INPUT()
    inp.type = INPUT_KEYBOARD
    inp.ki = KEYBDINPUT(
        wVk=vk,
        wScan=0,
        dwFlags=KEYEVENTF_KEYUP if up else 0,
        time=0,
        dwExtraInfo=0,
    )
    _send(inp)


def click(x: int, y: int) -> None:
    if not user32.SetCursorPos(int(x), int(y)):
        raise InputError(f"移动鼠标失败（错误码 {ctypes.get_last_error()}）")
    time.sleep(0.03)
    _mouse(MOUSEEVENTF_LEFTDOWN)
    time.sleep(0.02)
    _mouse(MOUSEEVENTF_LEFTUP)


def hotkey(*virtual_keys: int) -> None:
    pressed: list[int] = []
    try:
        for vk in virtual_keys:
            _key(vk, up=False)
            pressed.append(vk)
            time.sleep(0.01)
    finally:
        for vk in reversed(pressed):
            try:
                _key(vk, up=True)
            except Exception:
                pass
            time.sleep(0.01)


def press_enter() -> None:
    hotkey(VK_RETURN)


def send_reply(text: str, input_pos: tuple[int, int]) -> None:
    """点击输入框 → 全选 → 粘贴 → 回车。"""
    message = re.sub(r"\s+", " ", str(text or "")).strip()
    if not message:
        raise InputError("回复内容为空")
    if not input_pos or len(input_pos) != 2:
        raise InputError("未设置输入框位置")

    click(int(input_pos[0]), int(input_pos[1]))
    time.sleep(SEND_CLICK_WAIT)

    hotkey(VK_CONTROL, VK_A)
    time.sleep(SEND_SELECT_WAIT)

    try:
        set_clipboard_text(message)
    except ClipboardError:
        raise
    except Exception as e:
        raise InputError(f"写入剪贴板失败：{e}") from e
    time.sleep(SEND_PASTE_WAIT)

    hotkey(VK_CONTROL, VK_V)
    time.sleep(SEND_PASTE_WAIT)

    hotkey(VK_RETURN)
    time.sleep(SEND_ENTER_WAIT)
