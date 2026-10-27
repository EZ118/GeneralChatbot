# -*- coding: utf-8 -*-
"""无第三方依赖的图像转换工具。"""

from __future__ import annotations


def bgra_to_ppm(data: bytes, width: int, height: int) -> bytes:
    """把自上而下的 BGRA 像素转换成 Tk 可读取的 PPM (P6) 字节。"""
    if width <= 0 or height <= 0:
        raise ValueError("图像尺寸无效")
    expected = width * height * 4
    if len(data) < expected:
        raise ValueError(f"像素数据不足：期望 {expected} 字节，实际 {len(data)} 字节")

    rgb = bytearray(width * height * 3)
    # 扩展切片赋值在 C 层完成，比逐像素循环快很多
    rgb[0::3] = data[2:expected:4]
    rgb[1::3] = data[1:expected:4]
    rgb[2::3] = data[0:expected:4]
    header = f"P6\n{width} {height}\n255\n".encode("ascii")
    return header + bytes(rgb)


def bgra_brightness(data: bytes, width: int, height: int, step: int = 16) -> float:
    """粗略计算平均亮度（0-255），用于调试/诊断，不参与 OCR 主流程。"""
    expected = width * height * 4
    if expected <= 0 or len(data) < expected:
        return 0.0
    total = 0
    count = 0
    stride = max(4, int(step) * 4)
    for i in range(0, expected, stride):
        total += (data[i] + data[i + 1] + data[i + 2]) // 3
        count += 1
    return total / count if count else 0.0
