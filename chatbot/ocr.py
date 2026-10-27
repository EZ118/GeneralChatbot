# -*- coding: utf-8 -*-
"""Windows.Media.Ocr 封装。

只使用 Windows 10 1809 (build 17763) 就已存在的 OCR API。
winrt 绑定打包进 exe，最终用户不需要安装任何 Python 包。
"""

from __future__ import annotations

import asyncio
import threading
from dataclasses import dataclass
from typing import Any

from .constants import DEFAULT_OCR_LANGUAGE


class OcrError(RuntimeError):
    pass


@dataclass(frozen=True)
class OcrProbe:
    ok: bool
    available: tuple[str, ...]
    chosen: str | None
    error: str | None = None


def _load_winrt() -> tuple[Any, Any, Any, Any, Any, Any]:
    try:
        from winrt.windows.media.ocr import OcrEngine
        from winrt.windows.globalization import Language
        from winrt.windows.graphics.imaging import (
            SoftwareBitmap,
            BitmapPixelFormat,
            BitmapAlphaMode,
        )
        from winrt.windows.storage.streams import DataWriter
    except Exception as e:  # pragma: no cover - 取决于系统环境
        raise OcrError(
            "无法加载 Windows OCR 组件（winrt）。"
            "请确认使用的是打包后的 exe，或已安装 requirements.txt 中的依赖。"
            f"\n详细信息：{e}"
        ) from e
    return OcrEngine, Language, SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode, DataWriter


def available_languages() -> list[str]:
    OcrEngine, _, _, _, _, _ = _load_winrt()
    try:
        return [str(lang.language_tag) for lang in OcrEngine.available_recognizer_languages]
    except Exception as e:
        raise OcrError(f"枚举 OCR 语言失败：{e}") from e


def _choose_language(languages: list[str], preferred: str) -> str | None:
    preferred = (preferred or "").strip()
    if preferred:
        for lang in languages:
            if lang.casefold() == preferred.casefold() and lang.casefold().startswith("zh"):
                return lang

    zh = [lang for lang in languages if lang.casefold().startswith("zh")]
    if not zh:
        return None
    hans = [lang for lang in zh if "hans" in lang.casefold()]
    return (hans or zh)[0]


def probe_environment(preferred: str = DEFAULT_OCR_LANGUAGE) -> OcrProbe:
    try:
        languages = available_languages()
    except OcrError as e:
        return OcrProbe(False, (), None, str(e))

    chosen = _choose_language(languages, preferred)
    if chosen is None:
        found = "、".join(languages) if languages else "无"
        return OcrProbe(
            False,
            tuple(languages),
            None,
            "系统没有安装中文 OCR 语言包，无法识别中文。\n"
            f"本机可用 OCR 语言：{found}\n"
            "请安装中文（简体）语言包及其 OCR 可选功能后重试。",
        )
    return OcrProbe(True, tuple(languages), chosen)


async def _await_operation(operation: Any) -> Any:
    return await operation


class WindowsOcr:
    """线程安全的 OCR 封装；每个线程缓存自己的 OcrEngine。"""

    def __init__(self) -> None:
        self._local = threading.local()

    def _engine(self, language: str) -> Any:
        cache = getattr(self._local, "engines", None)
        if cache is None:
            cache = {}
            self._local.engines = cache
        if language in cache:
            engine = cache[language]
        else:
            OcrEngine, Language, _, _, _, _ = _load_winrt()
            try:
                engine = OcrEngine.try_create_from_language(Language(language))
            except Exception as e:
                raise OcrError(f"创建 OCR 引擎失败（{language}）：{e}") from e
            if engine is None:
                raise OcrError(
                    f"无法创建 OCR 引擎（{language}）。"
                    "请检查该语言的 OCR 语言包是否已安装。"
                )
            cache[language] = engine
        return engine

    def recognize(
        self,
        bgra: bytes,
        width: int,
        height: int,
        language: str = DEFAULT_OCR_LANGUAGE,
    ) -> list[str]:
        if width <= 0 or height <= 0:
            raise OcrError("识别区域尺寸无效")
        expected = width * height * 4
        if len(bgra) < expected:
            raise OcrError(
                f"图像数据长度不足：期望 {expected} 字节，实际 {len(bgra)} 字节"
            )

        OcrEngine, _, SoftwareBitmap, BitmapPixelFormat, BitmapAlphaMode, DataWriter = _load_winrt()
        max_dim = 10000
        try:
            max_dim = int(OcrEngine.max_image_dimension)
        except Exception:
            pass
        if width > max_dim or height > max_dim:
            raise OcrError(f"识别区域过大（{width}x{height}），Windows OCR 上限为 {max_dim}")

        engine = self._engine(language)

        try:
            writer = DataWriter()
            writer.write_bytes(bgra[:expected])
            buffer = writer.detach_buffer()
            bitmap = SoftwareBitmap.create_copy_from_buffer(
                buffer,
                BitmapPixelFormat.BGRA8,
                width,
                height,
                BitmapAlphaMode.IGNORE,
            )
            result = asyncio.run(_await_operation(engine.recognize_async(bitmap)))
        except OcrError:
            raise
        except Exception as e:
            raise OcrError(f"OCR 识别失败：{e}") from e

        found: list[tuple[float, str]] = []
        for line in result.lines:
            text = str(line.text or "")
            y = 0.0
            try:
                words = list(line.words)
                if words:
                    y = min(float(w.bounding_rect.y) for w in words)
            except Exception:
                pass
            found.append((y, text))

        found.sort(key=lambda item: item[0])
        return [text for _, text in found]
