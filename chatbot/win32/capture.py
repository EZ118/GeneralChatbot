# -*- coding: utf-8 -*-
"""GDI 截屏，返回自上而下的 BGRA 像素。"""

from __future__ import annotations

import ctypes
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)

SRCCOPY = 0x00CC0020
CAPTUREBLT = 0x40000000
COLORONCOLOR = 3


class CaptureError(RuntimeError):
    pass


class BITMAPINFOHEADER(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BITMAPINFO(ctypes.Structure):
    _fields_ = [
        ("bmiHeader", BITMAPINFOHEADER),
        ("bmiColors", wintypes.DWORD * 3),
    ]


user32.GetDC.argtypes = [wintypes.HWND]
user32.GetDC.restype = wintypes.HDC
user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
user32.ReleaseDC.restype = ctypes.c_int

gdi32.CreateCompatibleDC.argtypes = [wintypes.HDC]
gdi32.CreateCompatibleDC.restype = wintypes.HDC
gdi32.CreateCompatibleBitmap.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
gdi32.CreateCompatibleBitmap.restype = wintypes.HBITMAP
gdi32.SelectObject.argtypes = [wintypes.HDC, wintypes.HGDIOBJ]
gdi32.SelectObject.restype = wintypes.HGDIOBJ
gdi32.BitBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]
gdi32.BitBlt.restype = wintypes.BOOL
gdi32.StretchBlt.argtypes = [
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.HDC,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    ctypes.c_int,
    wintypes.DWORD,
]
gdi32.StretchBlt.restype = wintypes.BOOL
gdi32.SetStretchBltMode.argtypes = [wintypes.HDC, ctypes.c_int]
gdi32.SetStretchBltMode.restype = ctypes.c_int
gdi32.GetDIBits.argtypes = [
    wintypes.HDC,
    wintypes.HBITMAP,
    wintypes.UINT,
    wintypes.UINT,
    ctypes.c_void_p,
    ctypes.POINTER(BITMAPINFO),
    wintypes.UINT,
]
gdi32.GetDIBits.restype = ctypes.c_int
gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
gdi32.DeleteObject.restype = wintypes.BOOL
gdi32.DeleteDC.argtypes = [wintypes.HDC]
gdi32.DeleteDC.restype = wintypes.BOOL


def capture_bgra(
    x: int,
    y: int,
    width: int,
    height: int,
    scale: int = 1,
) -> tuple[bytes, int, int]:
    """抓取屏幕矩形，返回 (BGRA 字节, 宽, 高)。

    scale > 1 时直接在 GDI 里放大，避免 Python 逐像素处理。
    """
    x, y, width, height = int(x), int(y), int(width), int(height)
    scale = max(1, min(3, int(scale)))
    if width <= 0 or height <= 0:
        raise CaptureError(f"识别区域尺寸无效：{width}x{height}")

    dst_w, dst_h = width * scale, height * scale
    hdc_screen = user32.GetDC(None)
    if not hdc_screen:
        raise CaptureError(f"GetDC 失败（错误码 {ctypes.get_last_error()}）")

    hdc_mem = None
    hbmp = None
    old_obj = None
    try:
        hdc_mem = gdi32.CreateCompatibleDC(hdc_screen)
        if not hdc_mem:
            raise CaptureError(f"CreateCompatibleDC 失败（错误码 {ctypes.get_last_error()}）")

        hbmp = gdi32.CreateCompatibleBitmap(hdc_screen, dst_w, dst_h)
        if not hbmp:
            raise CaptureError(f"CreateCompatibleBitmap 失败（错误码 {ctypes.get_last_error()}）")

        old_obj = gdi32.SelectObject(hdc_mem, hbmp)
        if not old_obj:
            raise CaptureError(f"SelectObject 失败（错误码 {ctypes.get_last_error()}）")

        if scale == 1:
            ok = gdi32.BitBlt(
                hdc_mem, 0, 0, dst_w, dst_h, hdc_screen, x, y, SRCCOPY | CAPTUREBLT
            )
            if not ok:
                # 某些远程桌面/显卡驱动对 CAPTUREBLT 支持不好，退回普通模式
                ok = gdi32.BitBlt(
                    hdc_mem, 0, 0, dst_w, dst_h, hdc_screen, x, y, SRCCOPY
                )
        else:
            gdi32.SetStretchBltMode(hdc_mem, COLORONCOLOR)
            ok = gdi32.StretchBlt(
                hdc_mem,
                0,
                0,
                dst_w,
                dst_h,
                hdc_screen,
                x,
                y,
                width,
                height,
                SRCCOPY | CAPTUREBLT,
            )
            if not ok:
                ok = gdi32.StretchBlt(
                    hdc_mem,
                    0,
                    0,
                    dst_w,
                    dst_h,
                    hdc_screen,
                    x,
                    y,
                    width,
                    height,
                    SRCCOPY,
                )

        if not ok:
            raise CaptureError(f"截屏失败（错误码 {ctypes.get_last_error()}）")

        buffer = ctypes.create_string_buffer(dst_w * dst_h * 4)
        bitmap_info = BITMAPINFO()
        bitmap_info.bmiHeader.biSize = ctypes.sizeof(BITMAPINFOHEADER)
        bitmap_info.bmiHeader.biWidth = dst_w
        bitmap_info.bmiHeader.biHeight = -dst_h  # 负数 = 自上而下
        bitmap_info.bmiHeader.biPlanes = 1
        bitmap_info.bmiHeader.biBitCount = 32
        bitmap_info.bmiHeader.biCompression = 0  # BI_RGB

        scanlines = gdi32.GetDIBits(
            hdc_mem,
            hbmp,
            0,
            dst_h,
            buffer,
            ctypes.byref(bitmap_info),
            0,
        )
        if scanlines == 0:
            raise CaptureError(f"GetDIBits 失败（错误码 {ctypes.get_last_error()}）")

        return buffer.raw, dst_w, dst_h
    finally:
        if hdc_mem and old_obj:
            gdi32.SelectObject(hdc_mem, old_obj)
        if hbmp:
            gdi32.DeleteObject(hbmp)
        if hdc_mem:
            gdi32.DeleteDC(hdc_mem)
        if hdc_screen:
            user32.ReleaseDC(None, hdc_screen)
