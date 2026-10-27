# -*- coding: utf-8 -*-
"""设置对话框。"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
from tkinter import messagebox, scrolledtext, ttk

from ..api import ChatClient
from ..constants import MAX_OCR_SCALE, TEST_TIMEOUT
from ..prompts import DEFAULT_SYSTEM_PROMPT
from ..textutil import truncate


def _center(dlg: tk.Toplevel, parent: tk.Misc) -> None:
    dlg.update_idletasks()
    width = dlg.winfo_width()
    height = dlg.winfo_height()
    if width <= 1:
        width = dlg.winfo_reqwidth()
    if height <= 1:
        height = dlg.winfo_reqheight()
    x = parent.winfo_rootx() + max(0, (parent.winfo_width() - width) // 2)
    y = parent.winfo_rooty() + max(0, (parent.winfo_height() - height) // 2)
    dlg.geometry(f"+{x}+{y}")


def open_model_dialog(app) -> None:  # noqa: ANN001
    snap = app.settings.snapshot()
    dlg = tk.Toplevel(app.root)
    dlg.title("设置模型")
    dlg.transient(app.root)
    dlg.resizable(False, False)
    dlg.grab_set()

    frame = ttk.Frame(dlg, padding=14)
    frame.pack(fill="both", expand=True)

    base_var = tk.StringVar(value=snap.api_base or "https://api.openai.com/v1")
    key_var = tk.StringVar(value=snap.api_key)
    model_var = tk.StringVar(value=snap.model or "gpt-4o-mini")

    ttk.Label(frame, text="API Base URL：").grid(row=0, column=0, sticky="w", pady=5)
    e_base = ttk.Entry(frame, textvariable=base_var, width=56)
    e_base.grid(row=0, column=1, pady=5, sticky="we")

    ttk.Label(frame, text="API Key：").grid(row=1, column=0, sticky="w", pady=5)
    e_key = ttk.Entry(frame, textvariable=key_var, width=56, show="*")
    e_key.grid(row=1, column=1, pady=5, sticky="we")

    ttk.Label(frame, text="Model：").grid(row=2, column=0, sticky="w", pady=5)
    e_model = ttk.Entry(frame, textvariable=model_var, width=56)
    e_model.grid(row=2, column=1, pady=5, sticky="we")

    ttk.Label(
        frame,
        text="API Base 可填写到 /v1，也可直接填写完整的 /chat/completions 地址。",
        foreground="#666",
    ).grid(row=3, column=0, columnspan=2, sticky="w", pady=(0, 8))

    test_row = ttk.Frame(frame)
    test_row.grid(row=4, column=0, columnspan=2, sticky="we", pady=(0, 4))
    test_btn = ttk.Button(test_row, text="测试连接（可选）")
    test_btn.pack(side="left")
    result_var = tk.StringVar(value="")
    result_label = ttk.Label(
        test_row, textvariable=result_var, foreground="#666", wraplength=420
    )
    result_label.pack(side="left", padx=(10, 0), fill="x", expand=True)

    if snap.api_key:
        result_var.set("可使用当前填写的内容测试连接，测试不会保存配置。")

    def save() -> None:
        base = base_var.get().strip().rstrip("/")
        key = key_var.get().strip()
        model = model_var.get().strip()
        if not base or not key or not model:
            messagebox.showwarning("提示", "API Base、API Key、Model 三项都不能为空", parent=dlg)
            return
        app.settings.update(api_base=base, api_key=key, model=model)
        if not app.settings.save():
            messagebox.showerror("保存失败", app.settings.error or "写入配置失败", parent=dlg)
            return
        app.log(f"模型已设置并保存：{model}")
        app.refresh_status()
        dlg.destroy()

    def start_test() -> None:
        base = base_var.get().strip().rstrip("/")
        key = key_var.get().strip()
        model = model_var.get().strip()
        if not base or not key or not model:
            messagebox.showwarning("提示", "请先填写完整的三项内容", parent=dlg)
            return
        test_btn.configure(state="disabled", text="测试中…")
        result_var.set("正在连接，请稍候…")
        result_label.configure(foreground="#666")
        results: queue.Queue[tuple[bool, str]] = queue.Queue()

        def work() -> None:
            try:
                client = ChatClient(base, key, model, timeout=TEST_TIMEOUT)
                reply = client.chat(
                    [{"role": "user", "content": "请只回复：OK"}],
                )
                results.put((True, reply))
            except Exception as e:
                results.put((False, str(e)))

        threading.Thread(target=work, name="test-connection", daemon=True).start()

        def poll() -> None:
            if not dlg.winfo_exists():
                return
            try:
                ok, message = results.get_nowait()
            except queue.Empty:
                dlg.after(100, poll)
                return
            test_btn.configure(state="normal", text="测试连接（可选）")
            if ok:
                result_label.configure(foreground="#1b7f3a")
                result_var.set(f"连接成功，模型返回：{truncate(message, 100)}")
            else:
                result_label.configure(foreground="#b00020")
                result_var.set(f"连接失败：{truncate(message, 160)}")

        dlg.after(100, poll)

    test_btn.configure(command=start_test)

    buttons = ttk.Frame(frame)
    buttons.grid(row=5, column=0, columnspan=2, pady=(12, 0))
    ttk.Button(buttons, text="保存", command=save).pack(side="left", padx=6)
    ttk.Button(buttons, text="取消", command=dlg.destroy).pack(side="left", padx=6)

    dlg.bind("<Escape>", lambda e: dlg.destroy())
    dlg.bind("<Return>", lambda e: save())
    _center(dlg, app.root)
    e_base.focus_set()


def open_reply_settings_dialog(app) -> None:  # noqa: ANN001
    snap = app.settings.snapshot()
    dlg = tk.Toplevel(app.root)
    dlg.title("消息与识别设置")
    dlg.transient(app.root)
    dlg.resizable(False, False)
    dlg.grab_set()

    frame = ttk.Frame(dlg, padding=14)
    frame.pack(fill="both", expand=True)

    trigger_var = tk.StringVar(value=snap.trigger)
    ttk.Label(frame, text="触发关键词：").grid(row=0, column=0, sticky="w", pady=5)
    ttk.Entry(frame, textvariable=trigger_var, width=36).grid(
        row=0, column=1, sticky="we", pady=5
    )
    ttk.Label(
        frame,
        text="识别区域内某行 OCR 文本包含该关键词时，才会触发回复。\n"
        "匹配会忽略空格、全角/半角差异，例如 @周 与 @ 周 都能命中。",
        foreground="#666",
    ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

    ttk.Separator(frame, orient="horizontal").grid(
        row=2, column=0, columnspan=2, sticky="we", pady=8
    )
    ttk.Label(frame, text="OCR 语言：").grid(row=3, column=0, sticky="w", pady=5)
    languages = [lang for lang in app.ocr_languages if lang.casefold().startswith("zh")]
    current_language = snap.ocr_language
    if not languages:
        languages = [current_language]
    if current_language not in languages:
        languages.insert(0, current_language)
    language_var = tk.StringVar(value=current_language)
    ttk.Combobox(
        frame, textvariable=language_var, values=languages, state="readonly", width=33
    ).grid(row=3, column=1, sticky="we", pady=5)

    ttk.Label(frame, text="识别放大倍数：").grid(row=4, column=0, sticky="w", pady=5)
    scale_var = tk.StringVar(value=str(snap.ocr_scale))
    ttk.Combobox(
        frame,
        textvariable=scale_var,
        values=[str(i) for i in range(1, MAX_OCR_SCALE + 1)],
        state="readonly",
        width=33,
    ).grid(row=4, column=1, sticky="we", pady=5)

    ttk.Label(
        frame,
        text="默认 2 倍更适合小字号；区域很大或字体清晰时可用 1 倍。\n"
        "正式识别时如果当前倍率没有命中触发词，会自动尝试另一个倍率。\n"
        "运行中修改语言后需要重新点一次开始。",
        foreground="#666",
    ).grid(row=5, column=0, columnspan=2, sticky="w", pady=(0, 6))

    def save() -> None:
        trigger = trigger_var.get().strip()
        if not trigger:
            messagebox.showwarning("提示", "触发关键词不能为空", parent=dlg)
            return
        try:
            scale = int(scale_var.get())
        except ValueError:
            scale = 1
        scale = max(1, min(MAX_OCR_SCALE, scale))
        app.settings.update(
            trigger=trigger,
            ocr_language=language_var.get().strip() or current_language,
            ocr_scale=scale,
        )
        if not app.settings.save():
            messagebox.showerror("保存失败", app.settings.error or "写入配置失败", parent=dlg)
            return
        app.log(f"消息与识别设置已保存：触发词 {trigger}，OCR {language_var.get()} ×{scale}")
        app.refresh_status()
        dlg.destroy()

    buttons = ttk.Frame(frame)
    buttons.grid(row=6, column=0, columnspan=2, pady=(12, 0))
    ttk.Button(buttons, text="保存", command=save).pack(side="left", padx=6)
    ttk.Button(buttons, text="取消", command=dlg.destroy).pack(side="left", padx=6)

    dlg.bind("<Escape>", lambda e: dlg.destroy())
    dlg.bind("<Return>", lambda e: save())
    _center(dlg, app.root)


def open_prompt_dialog(app) -> None:  # noqa: ANN001
    snap = app.settings.snapshot()
    dlg = tk.Toplevel(app.root)
    dlg.title("编辑系统提示词")
    dlg.transient(app.root)
    dlg.geometry("760x560")
    dlg.minsize(520, 360)
    dlg.grab_set()

    frame = ttk.Frame(dlg, padding=12)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="系统提示词会保存到 settings.json，支持多行；每次请求都会作为 system 消息发送。",
        foreground="#555",
    ).pack(anchor="w", pady=(0, 6))

    text = scrolledtext.ScrolledText(
        frame, wrap="word", font=("Microsoft YaHei", 10)
    )
    text.pack(fill="both", expand=True)
    text.insert("1.0", snap.system_prompt)
    text.focus_set()

    def restore_default() -> None:
        if messagebox.askyesno(
            "恢复默认", "确定要把编辑框内容恢复为默认系统提示词吗？", parent=dlg
        ):
            text.delete("1.0", "end")
            text.insert("1.0", DEFAULT_SYSTEM_PROMPT)

    def save() -> None:
        content = text.get("1.0", "end").strip("\n")
        if not content.strip():
            messagebox.showwarning("提示", "系统提示词不能为空", parent=dlg)
            return
        app.settings.update(system_prompt=content)
        if not app.settings.save():
            messagebox.showerror("保存失败", app.settings.error or "写入配置失败", parent=dlg)
            return
        app.log(f"系统提示词已保存（{len(content)} 字）")
        dlg.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons, text="恢复默认", command=restore_default).pack(side="left")
    ttk.Button(buttons, text="取消", command=dlg.destroy).pack(side="right", padx=4)
    ttk.Button(buttons, text="保存", command=save).pack(side="right", padx=4)

    dlg.bind("<Escape>", lambda e: dlg.destroy())
    _center(dlg, app.root)


def open_inject_memory_dialog(app) -> None:  # noqa: ANN001
    dlg = tk.Toplevel(app.root)
    dlg.title("注入记忆")
    dlg.transient(app.root)
    dlg.geometry("620x440")
    dlg.minsize(460, 300)
    dlg.grab_set()

    frame = ttk.Frame(dlg, padding=12)
    frame.pack(fill="both", expand=True)

    ttk.Label(
        frame,
        text="输入要注入到 AI 记忆上下文中的内容（如身份设定、群规、已确认的事实）。\n"
        "注入后会作为 system 消息保留，并在压缩记忆时保留下来。",
        foreground="#555",
    ).pack(anchor="w", pady=(0, 6))

    text = scrolledtext.ScrolledText(
        frame, wrap="word", font=("Microsoft YaHei", 10)
    )
    text.pack(fill="both", expand=True)
    text.focus_set()

    def inject() -> None:
        content = text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("提示", "内容不能为空", parent=dlg)
            return
        app.memory.add_system("【用户注入】" + content)
        saved = app.memory.save()
        app.log(
            f"已注入记忆（{len(content)} 字）"
            + ("" if saved else "，但写入 memory.json 失败")
        )
        app.refresh_status()
        dlg.destroy()

    buttons = ttk.Frame(frame)
    buttons.pack(fill="x", pady=(10, 0))
    ttk.Button(buttons, text="取消", command=dlg.destroy).pack(side="right", padx=4)
    ttk.Button(buttons, text="注入", command=inject).pack(side="right", padx=4)

    dlg.bind("<Escape>", lambda e: dlg.destroy())
    _center(dlg, app.root)
