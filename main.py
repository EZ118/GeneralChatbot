# -*- coding: utf-8 -*-
"""程序入口。"""

from __future__ import annotations

import ctypes
import logging
import sys
import time
import traceback

from chatbot.constants import APP_TITLE, MIN_WINDOWS_BUILD
from chatbot.logging_setup import setup_logging
from chatbot.ocr import probe_environment
from chatbot.paths import APP_DIR, LOG_FILE
from chatbot.settings import Settings
from chatbot.win32.dpi import enable_dpi_awareness, windows_build


def _message_box(text: str, title: str = APP_TITLE, error: bool = True) -> None:
    try:
        ctypes.windll.user32.MessageBoxW(0, text, title, 0x10 if error else 0x40)
    except Exception:
        print(text, file=sys.stderr)


def _self_test(settings: Settings, probe) -> int:  # noqa: ANN001
    """打包后/1809 实机冒烟测试：抓取识别区域并执行一次真实 OCR。"""
    from chatbot.ocr import WindowsOcr
    from chatbot.textutil import compact_ocr_text
    from chatbot.win32.capture import capture_bgra

    snap = settings.snapshot()
    region = snap.capture_region or (0, 0, 800, 200)
    language = probe.chosen or snap.ocr_language
    lines: list[str] = []
    error_text = ""
    elapsed_ms = 0.0
    try:
        bgra, width, height = capture_bgra(*region, scale=snap.ocr_scale)
        started = time.perf_counter()
        raw_lines = WindowsOcr().recognize(bgra, width, height, language)
        elapsed_ms = (time.perf_counter() - started) * 1000
        lines = [compact_ocr_text(line) for line in raw_lines]
        lines = [line for line in lines if line]
    except Exception:
        error_text = traceback.format_exc()

    report = [
        f"time: {time.strftime('%Y-%m-%d %H:%M:%S')}",
        f"windows_build: {windows_build()}",
        f"ocr_languages: {', '.join(probe.available)}",
        f"ocr_language_used: {language}",
        f"region: {region}",
        f"scale: {snap.ocr_scale}",
        f"elapsed_ms: {elapsed_ms:.1f}",
        f"line_count: {len(lines)}",
        "lines:",
        *[f"  {line}" for line in lines],
    ]
    if error_text:
        report += ["error:", error_text]
    report_path = APP_DIR / "self-test.log"
    try:
        report_path.write_text("\n".join(report) + "\n", encoding="utf-8")
    except OSError:
        report_path = None

    if error_text:
        _message_box(
            "OCR 自检失败：\n"
            + error_text.strip().splitlines()[-1]
            + (f"\n\n日志：{report_path}" if report_path else ""),
            error=True,
        )
        return 3

    _message_box(
        f"OCR 自检通过。\n\n"
        f"Windows build: {windows_build()}\n"
        f"OCR 语言: {language}\n"
        f"识别到 {len(lines)} 行，耗时 {elapsed_ms:.0f} ms。\n\n"
        f"日志：{report_path}",
        error=False,
    )
    return 0


def _check_platform() -> str | None:
    if sys.platform != "win32":
        return "本程序只支持 Windows 10 1809 及以上版本。"
    build = windows_build()
    if build and build < MIN_WINDOWS_BUILD:
        return (
            f"当前 Windows 版本 build {build}，低于 Windows 10 1809（build 17763）。\n"
            "请升级系统后再运行。"
        )
    return None


def main() -> int:
    error = _check_platform()
    if error:
        _message_box(error)
        return 1

    dpi_mode = enable_dpi_awareness()
    logger = setup_logging(LOG_FILE)
    logger.info("程序启动，Windows build=%s，DPI=%s", windows_build(), dpi_mode)

    settings = Settings()
    if settings.error:
        logger.warning(settings.error)
    if settings.migrated_from is not None:
        logger.info("配置已从 %s 迁移到 %s", settings.migrated_from, settings.path)

    probe = probe_environment(settings.snapshot().ocr_language)
    if not probe.ok:
        logger.error("OCR 环境检查失败：%s", probe.error)
        _message_box(probe.error or "Windows OCR 不可用。")
        return 2

    if "--self-test" in sys.argv[1:]:
        return _self_test(settings, probe)

    import tkinter as tk

    from chatbot.ui.app import App

    root = tk.Tk()
    App(root, settings, probe)
    try:
        root.mainloop()
    finally:
        logger.info("主循环结束")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except SystemExit:
        raise
    except Exception as exc:  # pragma: no cover - 最后兜底
        logging.getLogger("chatbot").exception("程序异常退出")
        _message_box(f"程序异常退出：\n{exc}\n\n{traceback.format_exc()[-1200:]}")
        raise
