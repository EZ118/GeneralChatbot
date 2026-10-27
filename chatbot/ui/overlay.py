# -*- coding: utf-8 -*-
"""全屏半透明取点/拉框选择器。"""

from __future__ import annotations

import tkinter as tk
from typing import Callable

from ..win32.monitors import MonitorRect, get_cursor_pos, list_monitors
from ..win32.window import place_topmost


class ScreenSelector:
    """在每块显示器上创建一个置顶覆盖窗。

    mode = "point" 取输入框位置；"rect" 拉取识别区域。
    结果坐标均为虚拟屏幕物理像素。
    """

    def __init__(
        self,
        root: tk.Tk,
        mode: str,
        on_done: Callable[[tuple[int, ...] | None], None],
    ) -> None:
        self.root = root
        self.mode = mode
        self.on_done = on_done
        self.start: tuple[int, int] | None = None
        self.active: tuple[MonitorRect, tk.Canvas, tk.Toplevel, float, float] | None = None
        self.rect_id: int | None = None
        self.size_id: int | None = None
        self._finished = False
        self._windows: list[tk.Toplevel] = []

        monitors = list_monitors()
        if not monitors:
            self._finish(None)
            return

        try:
            for monitor in monitors:
                self._create_overlay(monitor)
            self.root.bind_all("<Escape>", self._on_escape)
            self.root.after(80, self._focus_cursor_monitor)
        except Exception:
            self._cleanup()
            raise

    # ------------------------------------------------------------------ ui
    def _create_overlay(self, monitor: MonitorRect) -> None:
        win = tk.Toplevel(self.root)
        self._windows.append(win)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="black")
        try:
            win.attributes("-alpha", 0.30)
        except Exception:
            pass

        canvas = tk.Canvas(win, bg="black", highlightthickness=0, cursor="crosshair")
        canvas.pack(fill="both", expand=True)
        win.update_idletasks()

        if not place_topmost(win, monitor.left, monitor.top, monitor.width, monitor.height):
            try:
                win.geometry(
                    f"{monitor.width}x{monitor.height}+{monitor.left}+{monitor.top}"
                )
            except Exception:
                pass
        win.update_idletasks()
        win.update()

        canvas_w = max(1, canvas.winfo_width())
        canvas_h = max(1, canvas.winfo_height())
        sx = monitor.width / canvas_w
        sy = monitor.height / canvas_h

        tip = (
            "点击目标输入框（Esc 取消）"
            if self.mode == "point"
            else "按住鼠标左键拖拽选择识别区域（Esc 取消）"
        )
        canvas.create_text(
            canvas_w // 2,
            max(32, int(42 / sy)),
            text=tip,
            fill="#ffe066",
            font=("Microsoft YaHei", 20, "bold"),
        )
        canvas.create_text(
            canvas_w // 2,
            max(58, int(76 / sy)),
            text="当前屏幕：" + f"{monitor.width}×{monitor.height}",
            fill="#bfbfbf",
            font=("Microsoft YaHei", 10),
        )

        canvas.bind("<Button-1>", lambda e: self._press(e, monitor, canvas, win, sx, sy))
        canvas.bind("<B1-Motion>", lambda e: self._drag(e))
        canvas.bind("<ButtonRelease-1>", lambda e: self._release(e))
        canvas.bind("<Button-3>", lambda e: self._cancel())
        win.bind("<Escape>", lambda e: self._cancel())

    def _focus_cursor_monitor(self) -> None:
        if self._finished or not self._windows:
            return
        x, y = get_cursor_pos()
        best = None
        for win in self._windows:
            try:
                if (
                    win.winfo_rootx() <= x < win.winfo_rootx() + win.winfo_width()
                    and win.winfo_rooty() <= y < win.winfo_rooty() + win.winfo_height()
                ):
                    best = win
                    break
            except Exception:
                continue
        (best or self._windows[0]).focus_force()

    # ------------------------------------------------------------------ mouse
    def _press(
        self,
        event: tk.Event,
        monitor: MonitorRect,
        canvas: tk.Canvas,
        win: tk.Toplevel,
        sx: float,
        sy: float,
    ) -> None:
        self.start = (event.x, event.y)
        self.active = (monitor, canvas, win, sx, sy)
        try:
            win.focus_force()
        except Exception:
            pass
        if self.mode == "rect":
            self.rect_id = canvas.create_rectangle(
                event.x, event.y, event.x, event.y, outline="#ff4d4d", width=2
            )
            self.size_id = canvas.create_text(
                event.x + 12,
                event.y + 12,
                text="",
                anchor="nw",
                fill="#ff8080",
                font=("Microsoft YaHei", 10, "bold"),
            )

    def _drag(self, event: tk.Event) -> None:
        if self.mode != "rect" or not self.start or self.active is None:
            return
        monitor, canvas, _, sx, sy = self.active
        if self.rect_id is not None:
            canvas.coords(self.rect_id, self.start[0], self.start[1], event.x, event.y)
        if self.size_id is not None:
            width = abs(event.x - self.start[0]) * sx
            height = abs(event.y - self.start[1]) * sy
            canvas.coords(self.size_id, event.x + 12, event.y + 12)
            canvas.itemconfigure(self.size_id, text=f"{int(width)} × {int(height)}")

    def _release(self, event: tk.Event) -> None:
        if self._finished or self.start is None or self.active is None:
            return
        monitor, _, _, sx, sy = self.active
        if self.mode == "point":
            x = monitor.left + int(self.start[0] * sx)
            y = monitor.top + int(self.start[1] * sy)
            self._finish((x, y))
            return

        x1, y1 = self.start
        x2, y2 = event.x, event.y
        left = monitor.left + int(min(x1, x2) * sx)
        top = monitor.top + int(min(y1, y2) * sy)
        width = int(abs(x2 - x1) * sx)
        height = int(abs(y2 - y1) * sy)
        if width < 10 or height < 10:
            self._cancel()
            return
        self._finish((left, top, width, height))

    def _on_escape(self, event: tk.Event | None = None) -> None:
        self._cancel()

    def _cancel(self) -> None:
        self._finish(None)

    # ------------------------------------------------------------------ finish
    def _cleanup(self) -> None:
        for win in self._windows:
            try:
                win.destroy()
            except Exception:
                pass
        self._windows.clear()
        try:
            self.root.unbind_all("<Escape>")
        except Exception:
            pass

    def _finish(self, result: tuple[int, ...] | None) -> None:
        if self._finished:
            return
        self._finished = True
        self._cleanup()
        try:
            self.on_done(result)
        except Exception:
            pass
