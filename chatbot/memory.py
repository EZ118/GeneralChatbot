# -*- coding: utf-8 -*-
"""对话记忆。

存储结构仍然是 memory.json 里的消息列表，兼容旧版本：
    [{"role": "system"|"user"|"assistant", "content": "..."}]

写入约定：
- 一轮问答通过 add_exchange() 成对写入，绝不会出现半截配对；
- 发送失败/API 失败时不写；
- 压缩只替换对话部分，保留用户注入的 system 条目。
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from . import paths
from .jsonutil import atomic_write_json

SUMMARY_PREFIX = "【历史记忆摘要】"
VALID_ROLES = {"system", "user", "assistant"}


class MemoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = Path(path) if path else paths.MEMORY_FILE
        self._lock = threading.RLock()
        self._messages: list[dict[str, str]] = []
        self.error: str | None = None
        self.load()

    # ------------------------------------------------------------------ load/save
    def load(self) -> None:
        if not self.path.is_file():
            return
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            self.error = f"读取记忆失败：{e}"
            return
        if not isinstance(data, list):
            self.error = "读取记忆失败：文件不是消息列表"
            return

        messages: list[dict[str, str]] = []
        for item in data:
            if not isinstance(item, dict):
                continue
            role = item.get("role")
            content = item.get("content")
            if role in VALID_ROLES and isinstance(content, str):
                messages.append({"role": role, "content": content})
        with self._lock:
            self._messages = messages
        self.error = None

    def save(self) -> bool:
        try:
            with self._lock:
                snapshot = [dict(m) for m in self._messages]
            atomic_write_json(self.path, snapshot)
            self.error = None
            return True
        except Exception as e:
            self.error = f"写入记忆失败：{e}"
            return False

    # ------------------------------------------------------------------ writes
    def add_exchange(self, user_text: str, assistant_text: str) -> None:
        user_text = str(user_text or "").strip()
        assistant_text = str(assistant_text or "").strip()
        if not user_text or not assistant_text:
            return
        with self._lock:
            self._messages.append({"role": "user", "content": user_text})
            self._messages.append({"role": "assistant", "content": assistant_text})

    def add_system(self, content: str) -> None:
        content = str(content or "").strip()
        if not content:
            return
        with self._lock:
            self._messages.append({"role": "system", "content": content})

    def apply_compression(self, summary: str) -> None:
        summary = str(summary or "").strip()
        if not summary:
            raise ValueError("摘要为空")
        with self._lock:
            systems = [dict(m) for m in self._messages if m["role"] == "system"]
            self._messages = systems + [
                {"role": "assistant", "content": SUMMARY_PREFIX + summary}
            ]

    # ------------------------------------------------------------------ reads
    def snapshot(self) -> list[dict[str, str]]:
        with self._lock:
            return [dict(m) for m in self._messages]

    def build_context(self, max_pairs: int) -> list[dict[str, str]]:
        """构造请求上下文：全部 system 注入 + 历史摘要 + 最近 N 组完整问答。"""
        with self._lock:
            messages = [dict(m) for m in self._messages]

        systems = [m for m in messages if m["role"] == "system"]
        summaries = [
            m
            for m in messages
            if m["role"] == "assistant" and m["content"].startswith(SUMMARY_PREFIX)
        ]
        dialogue = [
            m
            for m in messages
            if m["role"] in ("user", "assistant")
            and not (m["role"] == "assistant" and m["content"].startswith(SUMMARY_PREFIX))
        ]

        if max_pairs > 0:
            tail = dialogue[-max_pairs * 2 :]
            # 只保留完整的 user/assistant 对：必须从 user 开始、以 assistant 结束
            while tail and tail[0]["role"] != "user":
                tail.pop(0)
            while tail and tail[-1]["role"] != "assistant":
                tail.pop()
        else:
            tail = []

        return systems + summaries + tail

    def dialogue_text(self) -> str:
        with self._lock:
            messages = [dict(m) for m in self._messages]
        lines: list[str] = []
        for m in messages:
            if m["role"] not in ("user", "assistant"):
                continue
            speaker = "群友" if m["role"] == "user" else "助手"
            lines.append(f"{speaker}: {m['content']}")
        return "\n".join(lines)

    def __len__(self) -> int:
        with self._lock:
            return len(self._messages)
