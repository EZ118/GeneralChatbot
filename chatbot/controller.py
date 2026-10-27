# -*- coding: utf-8 -*-
"""识别、API、发送的单线程流水线。"""

from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field
from typing import Callable

from .api import ChatClient
from .constants import (
    COMPRESS_TIMEOUT,
    MAX_CONTEXT_PAIRS,
    MAX_SEEN,
    POLL_INTERVAL,
    SEEN_EXPIRE,
)
from .memory import MemoryStore
from .ocr import OcrError, WindowsOcr, probe_environment
from .prompts import COMPRESS_PROMPT, COMPRESS_SYSTEM_PROMPT, USER_PROMPT_TEMPLATE
from .settings import Settings
from .textutil import compact_ocr_text, contains_trigger, dedupe_key, truncate
from .win32.capture import CaptureError, capture_bgra
from .win32.input import send_reply


class SeenCache:
    def __init__(self, ttl: float = SEEN_EXPIRE, max_items: int = MAX_SEEN) -> None:
        self.ttl = float(ttl)
        self.max_items = int(max_items)
        self._lock = threading.Lock()
        self._items: dict[str, float] = {}

    def seen(self, key: str) -> bool:
        now = time.time()
        with self._lock:
            expired = [k for k, t in self._items.items() if now - t > self.ttl]
            for k in expired:
                self._items.pop(k, None)
            if key in self._items:
                return True
            self._items[key] = now
            while len(self._items) > self.max_items:
                self._items.pop(next(iter(self._items)))
            return False


@dataclass
class _RunState:
    stop: threading.Event = field(default_factory=threading.Event)
    queue: queue.Queue[str] = field(default_factory=queue.Queue)
    seen: SeenCache = field(default_factory=SeenCache)
    language: str = ""


class BotController:
    def __init__(
        self,
        settings: Settings,
        memory: MemoryStore,
        log: Callable[[str], None],
    ) -> None:
        self.settings = settings
        self.memory = memory
        self.log = log
        self._ocr = WindowsOcr()
        self._lock = threading.RLock()
        self._run: _RunState | None = None
        self._running = False
        self._threads: list[threading.Thread] = []
        self._compressing = False
        self._last_error_log: dict[str, float] = {}

    # ------------------------------------------------------------------ state
    @property
    def running(self) -> bool:
        with self._lock:
            return self._running

    @property
    def compressing(self) -> bool:
        with self._lock:
            return self._compressing

    # ------------------------------------------------------------------ start/stop
    def start(self) -> tuple[bool, str]:
        with self._lock:
            if self._running:
                return False, "已经在运行中"
            if self._compressing:
                return False, "正在压缩记忆，请稍候"

        snap = self.settings.snapshot()
        if not snap.api_ready:
            return False, "请先在“设置模型”里填写 API Base、API Key 和模型名。"
        if not snap.input_pos:
            return False, "请先点击“选择输入框位置”，指定聊天输入框。"
        if not snap.capture_region:
            return False, "请先点击“选择识别区域”，框选消息区域。"
        if not snap.trigger.strip():
            return False, "请先在“消息与识别设置”里填写触发关键词。"

        probe = probe_environment(snap.ocr_language)
        if not probe.ok:
            return False, probe.error or "Windows OCR 不可用。"

        run = _RunState(language=probe.chosen or snap.ocr_language)
        threads = [
            threading.Thread(
                target=self._recognize_loop, args=(run,), name="recognize", daemon=True
            ),
            threading.Thread(
                target=self._worker_loop, args=(run,), name="worker", daemon=True
            ),
        ]
        with self._lock:
            self._run = run
            self._running = True
            self._threads = threads
        for thread in threads:
            thread.start()

        self.log(
            f"开始识别 / 回复（OCR 语言 {run.language}，触发词 {snap.trigger}）"
        )
        return True, ""

    def stop(self) -> None:
        with self._lock:
            run = self._run
            if not self._running or run is None:
                return
            self._running = False
            self._run = None

        run.stop.set()
        dropped = 0
        while True:
            try:
                run.queue.get_nowait()
                dropped += 1
            except queue.Empty:
                break
        self.log("已停止" + (f"，丢弃 {dropped} 条排队消息" if dropped else ""))

    def shutdown(self) -> None:
        self.stop()
        with self._lock:
            threads = list(self._threads)
        for thread in threads:
            try:
                thread.join(timeout=0.5)
            except Exception:
                pass

    def _abort(self, run: _RunState, message: str) -> None:
        self.log(message)
        run.stop.set()
        with self._lock:
            if self._run is run:
                self._running = False
                self._run = None

    def _log_throttled(self, key: str, message: str, interval: float = 30.0) -> None:
        now = time.time()
        last = self._last_error_log.get(key, 0.0)
        if now - last >= interval:
            self._last_error_log[key] = now
            self.log(message)

    # ------------------------------------------------------------------ recognition
    def _ocr_region(self, region: tuple[int, int, int, int], scale: int, language: str) -> list[str]:
        x, y, w, h = region
        bgra, bw, bh = capture_bgra(x, y, w, h, scale=scale)
        raw_lines = self._ocr.recognize(bgra, bw, bh, language)
        lines = [compact_ocr_text(line) for line in raw_lines]
        return [line for line in lines if line]

    def _recognize_loop(self, run: _RunState) -> None:
        try:
            while not run.stop.is_set():
                snap = self.settings.snapshot()
                region = snap.capture_region
                if not region:
                    self._abort(run, "识别区域未设置，识别线程退出")
                    return
                try:
                    lines = self._ocr_region(region, snap.ocr_scale, run.language)
                    if not any(contains_trigger(line, snap.trigger) for line in lines):
                        # Windows OCR 在小字号下偶尔会把触发词中的某个字认错，
                        # 换一个倍率再试一次，只在第一遍完全没命中时执行。
                        fallback_scale = 1 if snap.ocr_scale != 1 else 2
                        try:
                            fallback_lines = self._ocr_region(
                                region, fallback_scale, run.language
                            )
                        except (CaptureError, OcrError):
                            fallback_lines = []
                        if any(
                            contains_trigger(line, snap.trigger)
                            for line in fallback_lines
                        ):
                            lines = fallback_lines
                            self._log_throttled(
                                "fallback",
                                f"触发词在 ×{snap.ocr_scale} 未命中，改用 ×{fallback_scale} 识别成功",
                                120.0,
                            )
                    for text in lines:
                        if not contains_trigger(text, snap.trigger):
                            continue
                        key = dedupe_key(text)
                        if not key or run.seen.seen(key):
                            continue
                        run.queue.put(text)
                        self.log(f"命中触发词 → 排队：{truncate(text, 60)}")
                except (CaptureError, OcrError) as e:
                    self._log_throttled("recognize", f"识别失败：{e}")
                except Exception as e:
                    self._log_throttled("recognize", f"识别异常：{e}")
                run.stop.wait(POLL_INTERVAL)
        except Exception as e:
            self._abort(run, f"识别线程异常退出：{e}")

    # ------------------------------------------------------------------ worker
    def _worker_loop(self, run: _RunState) -> None:
        try:
            while True:
                try:
                    message = run.queue.get(timeout=0.3)
                except queue.Empty:
                    if run.stop.is_set():
                        return
                    continue

                if run.stop.is_set():
                    return

                snap = self.settings.snapshot()
                if not snap.api_ready or not snap.input_pos:
                    self.log("API 或输入位置配置不完整，跳过这条消息")
                    continue

                context = self.memory.build_context(MAX_CONTEXT_PAIRS)
                messages = [{"role": "system", "content": snap.system_prompt}]
                messages.extend(context)
                messages.append(
                    {
                        "role": "user",
                        "content": USER_PROMPT_TEMPLATE.format(message=message),
                    }
                )

                try:
                    client = ChatClient(snap.api_base, snap.api_key, snap.model)
                    reply = client.chat(messages)
                except Exception as e:
                    self.log(f"API 请求失败：{e}")
                    continue

                if run.stop.is_set():
                    self.log("已停止，丢弃已生成但未发送的回复")
                    return

                try:
                    send_reply(reply, snap.input_pos)
                except Exception as e:
                    self.log(f"发送失败：{e}")
                    continue

                self.memory.add_exchange(message, reply)
                saved = self.memory.save()
                self.log(
                    f"已发送：{truncate(reply, 80)}"
                    + ("" if saved else "（记忆保存失败）")
                )
        except Exception as e:
            self._abort(run, f"发送线程异常退出：{e}")

    # ------------------------------------------------------------------ memory compression
    def compress_memory(self) -> str:
        with self._lock:
            if self._running:
                raise RuntimeError("请先停止识别/回复，再压缩记忆")
            if self._compressing:
                raise RuntimeError("压缩已在进行中")
            self._compressing = True

        try:
            snap = self.settings.snapshot()
            if not snap.api_ready:
                raise RuntimeError("请先设置模型")
            history = self.memory.dialogue_text()
            if not history.strip():
                return "记忆为空，无需压缩"

            client = ChatClient(snap.api_base, snap.api_key, snap.model)
            summary = client.chat(
                [
                    {"role": "system", "content": COMPRESS_SYSTEM_PROMPT},
                    {
                        "role": "user",
                        "content": COMPRESS_PROMPT
                        + "\n\n=== 对话记录 ===\n"
                        + history,
                    },
                ],
                timeout=COMPRESS_TIMEOUT,
            ).strip()
            if not summary:
                raise RuntimeError("模型返回空摘要")

            self.memory.apply_compression(summary)
            saved = self.memory.save()
            count = len(self.memory)
            message = f"记忆压缩完成（当前 {count} 条）"
            if not saved:
                message += "，但写入 memory.json 失败"
            self.log(message)
            return message
        finally:
            with self._lock:
                self._compressing = False
