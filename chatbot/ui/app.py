# -*- coding: utf-8 -*-
"""主窗口。"""

from __future__ import annotations

import logging
import math
import os
import queue
import tempfile
import threading
import time
import tkinter as tk
import traceback
from tkinter import messagebox, scrolledtext, ttk

from ..constants import APP_TITLE, UI_LOG_MAX_LINES
from ..controller import BotController
from ..imageutil import bgra_to_ppm
from ..memory import MemoryStore
from ..ocr import OcrProbe, WindowsOcr, probe_environment
from ..settings import Settings
from ..textutil import compact_ocr_text, contains_trigger
from ..win32.capture import capture_bgra
from ..win32.monitors import monitor_from_point
from .dialogs import (
    open_inject_memory_dialog,
    open_model_dialog,
    open_prompt_dialog,
    open_reply_settings_dialog,
)
from .overlay import ScreenSelector


class App:
    def __init__(self, root: tk.Tk, settings: Settings, probe: OcrProbe) -> None:
        self.root = root
        self.settings = settings
        self.probe = probe
        self.memory = MemoryStore()
        self.ocr = WindowsOcr()
        self.ocr_languages = list(probe.available)
        self.controller = BotController(settings, self.memory, self.log)

        self._log_queue: queue.Queue[str] = queue.Queue()
        self._preview: tk.Toplevel | None = None
        self._preview_photo: tk.PhotoImage | None = None
        self._selector: ScreenSelector | None = None
        self._closing = False

        self._build_ui()
        self._log_startup()

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.report_callback_exception = self._on_tk_exception
        self.root.bind("<F5>", lambda e: self.toggle_run())
        self.root.after(100, self._drain_logs)
        self.root.after(1000, self._tick)

    # ------------------------------------------------------------------ ui
    def _build_ui(self) -> None:
        self.root.title(APP_TITLE)
        self.root.geometry("900x650")
        self.root.minsize(760, 520)

        outer = ttk.Frame(self.root, padding=10)
        outer.pack(fill="both", expand=True)

        row1 = ttk.Frame(outer)
        row1.pack(fill="x", pady=2)
        ttk.Button(row1, text="设置模型", command=self.open_model_dialog).pack(
            side="left", padx=3
        )
        ttk.Button(row1, text="选择输入框位置", command=self.pick_input).pack(
            side="left", padx=3
        )
        ttk.Button(row1, text="选择识别区域", command=self.pick_capture).pack(
            side="left", padx=3
        )
        ttk.Button(row1, text="消息与识别设置", command=self.open_reply_dialog).pack(
            side="left", padx=3
        )
        ttk.Button(row1, text="编辑系统提示词", command=self.open_prompt_dialog).pack(
            side="left", padx=3
        )

        row2 = ttk.Frame(outer)
        row2.pack(fill="x", pady=(6, 2))
        self.preview_btn = ttk.Button(
            row2, text="预览识别区域", command=self.preview_region
        )
        self.preview_btn.pack(side="left", padx=3)
        self.compress_btn = ttk.Button(row2, text="压缩记忆", command=self.compress_memory)
        self.compress_btn.pack(side="left", padx=3)
        ttk.Button(row2, text="注入记忆", command=self.open_inject_memory).pack(
            side="left", padx=3
        )
        self.toggle_btn = ttk.Button(
            row2, text="▶ 开始识别/回复", command=self.toggle_run
        )
        self.toggle_btn.pack(side="left", padx=3)

        self.status_var = tk.StringVar(value="")
        self.status_label = ttk.Label(
            outer, textvariable=self.status_var, foreground="#333", wraplength=860
        )
        self.status_label.pack(fill="x", pady=(8, 2))

        ttk.Label(
            outer,
            text="提示：把聊天窗口放在识别区域内；程序发送时会移动鼠标并按键，请勿同时操作鼠标键盘。",
            foreground="#777",
        ).pack(fill="x", pady=(0, 8))

        log_frame = ttk.Frame(outer)
        log_frame.pack(fill="both", expand=True)
        ttk.Label(log_frame, text="运行日志").pack(anchor="w")
        self.log_box = scrolledtext.ScrolledText(
            log_frame,
            height=20,
            state="disabled",
            font=("Consolas", 9),
            wrap="word",
        )
        self.log_box.pack(fill="both", expand=True)

        self.refresh_status()

    # ------------------------------------------------------------------ logging
    def log(self, message: str) -> None:
        text = str(message)
        self._log_queue.put(f"[{time.strftime('%H:%M:%S')}] {text}")
        logging.getLogger("chatbot").info(text)

    def _drain_logs(self) -> None:
        if self._closing:
            return
        try:
            while True:
                line = self._log_queue.get_nowait()
                self.log_box.configure(state="normal")
                self.log_box.insert("end", line + "\n")
                self.log_box.see("end")
                try:
                    line_count = int(self.log_box.index("end-1c").split(".")[0])
                    if line_count > UI_LOG_MAX_LINES:
                        self.log_box.delete("1.0", f"{line_count - UI_LOG_MAX_LINES + 200}.0")
                except Exception:
                    pass
                self.log_box.configure(state="disabled")
        except queue.Empty:
            pass
        except Exception:
            pass
        finally:
            if not self._closing:
                self.root.after(100, self._drain_logs)

    def _log_startup(self) -> None:
        if self.settings.migrated_from is not None:
            self.log(
                f"已把旧配置 {self.settings.migrated_from.name} 迁移为 {self.settings.path.name}"
            )
        elif self.settings.created:
            self.log(
                f"未找到 {self.settings.path.name}，已创建默认配置"
                "（system_prompt 为默认初始化内容）"
            )
        elif self.settings.path.is_file():
            self.log(f"已读取 {self.settings.path.name}")
        else:
            self.log("未找到 settings.json，使用默认配置")
        if self.settings.error:
            self.log(f"⚠ {self.settings.error}")

        self.log(
            "Windows OCR 可用语言："
            + ("、".join(self.probe.available) if self.probe.available else "无")
        )
        if self.probe.chosen:
            self.log(f"本次使用的 OCR 语言：{self.probe.chosen}")
        if self.memory.error:
            self.log(f"⚠ {self.memory.error}")
        self.log(f"记忆：{len(self.memory)} 条")

    # ------------------------------------------------------------------ status
    def refresh_status(self) -> None:
        snap = self.settings.snapshot()
        pos = f"({snap.input_pos[0]},{snap.input_pos[1]})" if snap.input_pos else "未设置"
        region = str(snap.capture_region) if snap.capture_region else "未设置"
        api = snap.api_base or "未设置"
        if len(api) > 48:
            api = api[:45] + "…"
        self.status_var.set(
            f"API: {api}  |  模型: {snap.model or '未设置'}  |  "
            f"输入位置: {pos}  |  识别区域: {region}  |  "
            f"触发词: {snap.trigger}  |  OCR: {snap.ocr_language} ×{snap.ocr_scale}  |  "
            f"记忆: {len(self.memory)} 条"
        )

    def _tick(self) -> None:
        if self._closing:
            return
        try:
            self.refresh_status()
            running = self.controller.running
            self.toggle_btn.configure(
                text="■ 停止" if running else "▶ 开始识别/回复"
            )
            self.preview_btn.configure(state="disabled" if running else "normal")
            if self.controller.compressing:
                self.compress_btn.configure(state="disabled", text="压缩中…")
            else:
                self.compress_btn.configure(state="normal", text="压缩记忆")
        except Exception:
            pass
        self.root.after(1000, self._tick)

    # ------------------------------------------------------------------ dialogs
    def open_model_dialog(self) -> None:
        open_model_dialog(self)

    def open_reply_dialog(self) -> None:
        open_reply_settings_dialog(self)

    def open_prompt_dialog(self) -> None:
        open_prompt_dialog(self)

    def open_inject_memory(self) -> None:
        open_inject_memory_dialog(self)

    # ------------------------------------------------------------------ selection
    def pick_input(self) -> None:
        self._open_selector("point")

    def pick_capture(self) -> None:
        self._open_selector("rect")

    def _open_selector(self, mode: str) -> None:
        if self.controller.running:
            messagebox.showwarning("提示", "请先停止识别/回复，再重新选择区域", parent=self.root)
            return
        self._close_preview()
        self.root.withdraw()
        self.root.update_idletasks()

        def done(result: tuple[int, ...] | None) -> None:
            self._selector = None
            try:
                self.root.deiconify()
                self.root.lift()
            except Exception:
                pass
            if not result:
                self.log("已取消选择")
                return
            if mode == "point":
                x, y = int(result[0]), int(result[1])
                self.settings.update(input_pos=(x, y))
                description = f"输入框位置已设为 ({x},{y})"
            else:
                x, y, w, h = (int(v) for v in result)
                self.settings.update(capture_region=(x, y, w, h))
                description = f"识别区域已设为 ({x},{y}) {w}×{h}"
            if not self.settings.save():
                self.log(f"⚠ {self.settings.error or '配置保存失败'}")
            else:
                self.log(description + "，已保存")
            self.refresh_status()

        try:
            self._selector = ScreenSelector(self.root, mode, done)
        except Exception as e:
            self._selector = None
            try:
                self.root.deiconify()
            except Exception:
                pass
            messagebox.showerror("选择失败", f"无法创建屏幕选择器：{e}", parent=self.root)

    # ------------------------------------------------------------------ preview
    def preview_region(self) -> None:
        if self.controller.running:
            messagebox.showwarning("提示", "识别运行中不能预览，请先停止", parent=self.root)
            return
        snap = self.settings.snapshot()
        if not snap.capture_region:
            messagebox.showwarning("提示", "请先选择识别区域", parent=self.root)
            return
        self._close_preview()
        self.root.withdraw()
        self.root.update_idletasks()
        self.root.after(260, self._do_preview)

    def _do_preview(self) -> None:
        if self._closing:
            return
        snap = self.settings.snapshot()
        region = snap.capture_region
        if not region:
            self.root.deiconify()
            return

        ppm_path = ""
        try:
            current_probe = probe_environment(snap.ocr_language)
            if not current_probe.ok:
                raise RuntimeError(current_probe.error or "Windows OCR 不可用")
            language = current_probe.chosen or snap.ocr_language
            used_scale = snap.ocr_scale
            x, y, w, h = region

            def grab(scale: int):
                bgra, bw, bh = capture_bgra(x, y, w, h, scale=scale)
                raw_lines = self.ocr.recognize(bgra, bw, bh, language)
                compacted = [compact_ocr_text(line) for line in raw_lines]
                compacted = [line for line in compacted if line]
                return bgra, bw, bh, compacted

            bgra, bw, bh, lines = grab(snap.ocr_scale)
            hits = sum(1 for line in lines if contains_trigger(line, snap.trigger))
            if hits == 0:
                fallback_scale = 1 if snap.ocr_scale != 1 else 2
                try:
                    bgra2, bw2, bh2, lines2 = grab(fallback_scale)
                    hits2 = sum(
                        1 for line in lines2 if contains_trigger(line, snap.trigger)
                    )
                    if hits2 > 0:
                        bgra, bw, bh, lines, hits = bgra2, bw2, bh2, lines2, hits2
                        used_scale = fallback_scale
                except Exception:
                    pass

            ppm = bgra_to_ppm(bgra, bw, bh)
            handle = tempfile.NamedTemporaryFile(
                prefix="chatbot_preview_", suffix=".ppm", delete=False
            )
            ppm_path = handle.name
            handle.write(ppm)
            handle.close()

            photo = tk.PhotoImage(master=self.root, file=ppm_path)
            factor = max(
                1,
                math.ceil(photo.width() / 860),
                math.ceil(photo.height() / 600),
            )
            if factor > 1:
                photo = photo.subsample(factor, factor)
        except Exception as e:
            try:
                self.root.deiconify()
            except Exception:
                pass
            if ppm_path:
                try:
                    os.unlink(ppm_path)
                except OSError:
                    pass
            messagebox.showerror("预览失败", f"无法识别当前区域：{e}", parent=self.root)
            return
        finally:
            try:
                self.root.deiconify()
                self.root.lift()
            except Exception:
                pass
            if ppm_path:
                try:
                    os.unlink(ppm_path)
                except OSError:
                    pass

        self._show_preview(
            region, photo, lines, hits, snap.trigger, language, used_scale
        )

    def _show_preview(
        self,
        region: tuple[int, int, int, int],
        photo: tk.PhotoImage,
        lines: list[str],
        hits: int,
        trigger: str,
        ocr_language: str,
        scale: int,
    ) -> None:
        win = tk.Toplevel(self.root)
        self._preview = win
        self._preview_photo = photo
        win.title("识别区域预览")
        win.attributes("-topmost", True)
        win.protocol("WM_DELETE_WINDOW", self._close_preview)
        win.bind("<Escape>", lambda e: self._close_preview())

        frame = ttk.Frame(win, padding=10)
        frame.pack(fill="both", expand=True)
        ttk.Label(
            frame,
            text=(
                f"区域 {region}  |  OCR {ocr_language} ×{scale}  |  触发词 {trigger}  |  "
                f"命中 {hits} 行"
            ),
            foreground="#333",
        ).pack(anchor="w", pady=(0, 6))

        image_label = ttk.Label(frame, image=photo)
        image_label.pack(anchor="w", pady=(0, 8))

        text = scrolledtext.ScrolledText(
            frame, height=10, wrap="word", font=("Microsoft YaHei", 10)
        )
        text.pack(fill="both", expand=True)
        if lines:
            for line in lines:
                mark = "✔ " if contains_trigger(line, trigger) else "   "
                text.insert("end", f"{mark}{line}\n")
        else:
            text.insert("end", "没有识别到文字。\n")
        text.configure(state="disabled")

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="关闭", command=self._close_preview).pack(side="right")
        ttk.Button(
            buttons,
            text="刷新预览",
            command=lambda: (self._close_preview(), self.preview_region()),
        ).pack(side="right", padx=6)

        self.root.update_idletasks()
        monitor = monitor_from_point(
            int(region[0] + region[2] // 2), int(region[1] + region[3] // 2)
        )
        width = min(920, max(540, int(region[2]) + 90))
        height = min(680, max(380, int(region[3]) + 300))
        pos_x = int(region[0]) + int(region[2]) + 14
        if pos_x + width > monitor.right:
            pos_x = max(monitor.left + 10, monitor.right - width - 10)
        pos_y = int(region[1])
        if pos_y + height > monitor.bottom:
            pos_y = max(monitor.top + 10, monitor.bottom - height - 10)
        win.geometry(f"{width}x{height}+{pos_x}+{pos_y}")
        win.lift()

    def _close_preview(self) -> None:
        win = self._preview
        self._preview = None
        self._preview_photo = None
        if win is not None:
            try:
                win.destroy()
            except Exception:
                pass

    # ------------------------------------------------------------------ run control
    def toggle_run(self) -> None:
        if self.controller.running:
            self.controller.stop()
            self.refresh_status()
            return

        self._close_preview()
        ok, error = self.controller.start()
        if not ok:
            messagebox.showwarning("提示", error, parent=self.root)
            return
        self.refresh_status()

    # ------------------------------------------------------------------ compression
    def compress_memory(self) -> None:
        if self.controller.running:
            messagebox.showwarning("提示", "请先停止识别/回复，再压缩记忆", parent=self.root)
            return
        if self.controller.compressing:
            self.log("压缩已在进行中，请稍候")
            return

        def work() -> None:
            try:
                self.controller.compress_memory()
            except Exception as e:
                self.log(f"压缩失败：{e}")

        threading.Thread(target=work, name="compress-memory", daemon=True).start()

    # ------------------------------------------------------------------ errors/close
    def _on_tk_exception(self, exc_type, exc_value, exc_tb) -> None:  # noqa: ANN001
        detail = "".join(traceback.format_exception(exc_type, exc_value, exc_tb))
        self.log(f"界面异常：{exc_value}")
        logging.getLogger("chatbot").error("界面异常\n%s", detail)
        try:
            messagebox.showerror("界面异常", str(exc_value), parent=self.root)
        except Exception:
            pass

    def _on_close(self) -> None:
        if self._closing:
            return
        self._closing = True
        try:
            self._close_preview()
        except Exception:
            pass
        try:
            self.controller.shutdown()
        except Exception:
            pass
        try:
            self.settings.save()
        except Exception:
            pass
        try:
            self.memory.save()
        except Exception:
            pass
        logging.getLogger("chatbot").info("程序退出")
        try:
            self.root.destroy()
        except Exception:
            pass
