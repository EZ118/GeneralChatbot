# -*- coding: utf-8 -*-
"""settings.json 的读写、校验、旧配置迁移与线程安全快照。"""

from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import paths
from .jsonutil import atomic_write_json
from .constants import (
    DEFAULT_OCR_LANGUAGE,
    DEFAULT_OCR_SCALE,
    DEFAULT_TRIGGER,
    MAX_OCR_SCALE,
)
from .prompts import DEFAULT_SYSTEM_PROMPT


@dataclass(frozen=True)
class SettingsSnapshot:
    api_base: str
    api_key: str
    model: str
    input_pos: tuple[int, int] | None
    capture_region: tuple[int, int, int, int] | None
    trigger: str
    system_prompt: str
    ocr_language: str
    ocr_scale: int

    @property
    def api_ready(self) -> bool:
        return bool(self.api_base and self.api_key and self.model)


DEFAULTS: dict[str, Any] = {
    "api_base": "",
    "api_key": "",
    "model": "",
    "input_pos": None,
    "capture_region": None,
    "trigger": DEFAULT_TRIGGER,
    "system_prompt": DEFAULT_SYSTEM_PROMPT,
    "ocr_language": DEFAULT_OCR_LANGUAGE,
    "ocr_scale": DEFAULT_OCR_SCALE,
}


def _as_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize(raw: Any) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raw = {}

    def text(key: str) -> str:
        value = raw.get(key, DEFAULTS[key])
        return str(value).strip() if value is not None else ""

    api_base = text("api_base").rstrip("/")
    api_key = text("api_key")
    model = text("model")

    input_pos = None
    value = raw.get("input_pos")
    if isinstance(value, (list, tuple)) and len(value) == 2:
        x, y = _as_int(value[0]), _as_int(value[1])
        if x is not None and y is not None:
            input_pos = [x, y]

    capture_region = None
    value = raw.get("capture_region")
    if isinstance(value, (list, tuple)) and len(value) == 4:
        nums = [_as_int(v) for v in value]
        if all(v is not None for v in nums):
            x, y, w, h = (int(v) for v in nums)  # type: ignore[arg-type]
            if w > 0 and h > 0:
                capture_region = [x, y, w, h]

    trigger = text("trigger") or DEFAULT_TRIGGER

    prompt_value = raw.get("system_prompt", DEFAULTS["system_prompt"])
    system_prompt = str(prompt_value).replace("\r\n", "\n").replace("\r", "\n") if prompt_value else ""
    if not system_prompt.strip():
        system_prompt = DEFAULT_SYSTEM_PROMPT

    ocr_language = text("ocr_language") or DEFAULT_OCR_LANGUAGE
    scale = _as_int(raw.get("ocr_scale", DEFAULT_OCR_SCALE))
    ocr_scale = DEFAULT_OCR_SCALE if scale is None else max(1, min(MAX_OCR_SCALE, scale))

    return {
        "api_base": api_base,
        "api_key": api_key,
        "model": model,
        "input_pos": input_pos,
        "capture_region": capture_region,
        "trigger": trigger,
        "system_prompt": system_prompt,
        "ocr_language": ocr_language,
        "ocr_scale": ocr_scale,
    }


class Settings:
    """线程安全的配置对象。UI 线程写入，工作线程通过 snapshot() 读取。"""

    def __init__(
        self,
        path: Path | None = None,
        legacy_path: Path | None = None,
    ) -> None:
        self.path = Path(path) if path else paths.SETTINGS_FILE
        self.legacy_path = Path(legacy_path) if legacy_path else paths.LEGACY_SETTINGS_FILE
        self._lock = threading.RLock()
        self._data = _normalize({})
        self.error: str | None = None
        self.migrated_from: Path | None = None
        self.created = False
        self.load()

    # ------------------------------------------------------------------ load/save
    def load(self) -> None:
        source = self.path
        if not source.is_file():
            if self.legacy_path.is_file():
                source = self.legacy_path
                self.migrated_from = source
            else:
                # 没有任何配置文件时，立即生成 settings.json，
                # 其中 system_prompt 为 DEFAULT_SYSTEM_PROMPT。
                with self._lock:
                    self._data = _normalize({})
                self.created = self.save()
                return

        try:
            with open(source, "r", encoding="utf-8") as f:
                raw = json.load(f)
        except Exception as e:
            self.error = f"读取配置失败（{source.name}）：{e}"
            return

        normalized = _normalize(raw)
        with self._lock:
            self._data = normalized

        if self.migrated_from is not None:
            if not self.save():
                # 迁移失败不影响本次运行，但会在 UI 日志里提示
                pass

    def save(self) -> bool:
        try:
            with self._lock:
                payload = self._to_dict_locked()
            atomic_write_json(self.path, payload)
            self.error = None
            return True
        except Exception as e:
            self.error = f"写入配置失败（{self.path.name}）：{e}"
            return False

    # ------------------------------------------------------------------ access
    def snapshot(self) -> SettingsSnapshot:
        with self._lock:
            data = dict(self._data)
        pos = data.get("input_pos")
        region = data.get("capture_region")
        return SettingsSnapshot(
            api_base=data["api_base"],
            api_key=data["api_key"],
            model=data["model"],
            input_pos=tuple(pos) if pos else None,  # type: ignore[arg-type]
            capture_region=tuple(region) if region else None,  # type: ignore[arg-type]
            trigger=data["trigger"],
            system_prompt=data["system_prompt"],
            ocr_language=data["ocr_language"],
            ocr_scale=int(data["ocr_scale"]),
        )

    def update(self, **changes: Any) -> None:
        with self._lock:
            raw = dict(self._data)
            raw.update(changes)
            self._data = _normalize(raw)

    def _to_dict_locked(self) -> dict[str, Any]:
        data = dict(self._data)
        for key in ("input_pos", "capture_region"):
            if data.get(key):
                data[key] = list(data[key])
        return data

    def to_dict(self) -> dict[str, Any]:
        with self._lock:
            return self._to_dict_locked()
