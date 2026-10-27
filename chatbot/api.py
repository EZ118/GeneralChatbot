# -*- coding: utf-8 -*-
"""OpenAI Chat Completions 兼容客户端（仅标准库）。"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any

from .constants import API_TIMEOUT


class ApiError(RuntimeError):
    pass


def normalize_chat_url(api_base: str) -> str:
    base = (api_base or "").strip().rstrip("/")
    if not base:
        raise ApiError("API Base 为空")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"


def _extract_error_body(raw: bytes) -> str:
    text = raw.decode("utf-8", errors="replace").strip()
    try:
        data = json.loads(text)
        if isinstance(data, dict):
            error = data.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if isinstance(error, str):
                return error
            if data.get("message"):
                return str(data["message"])
    except Exception:
        pass
    return text or "（无响应内容）"


def _extract_content(data: Any) -> str:
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as e:
        raise ApiError("响应格式不是 OpenAI Chat Completions 格式") from e

    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        # 兼容部分服务把 content 返回为分段列表
        parts: list[str] = []
        for item in content:
            if isinstance(item, dict) and isinstance(item.get("text"), str):
                parts.append(item["text"])
            elif isinstance(item, str):
                parts.append(item)
        return "".join(parts).strip()
    return ""


class ChatClient:
    def __init__(
        self,
        api_base: str,
        api_key: str,
        model: str,
        timeout: float = API_TIMEOUT,
    ) -> None:
        self.url = normalize_chat_url(api_base)
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout
        if not self.api_key:
            raise ApiError("API Key 为空")
        if not self.model:
            raise ApiError("模型名称为空")

    def chat(
        self,
        messages: list[dict[str, str]],
        max_tokens: int | None = None,
        timeout: float | None = None,
    ) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens

        request = urllib.request.Request(
            self.url,
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
                "User-Agent": "GeneralChatbot/2.0",
            },
            method="POST",
        )

        try:
            with urllib.request.urlopen(
                request, timeout=timeout or self.timeout
            ) as response:
                raw = response.read()
        except urllib.error.HTTPError as e:
            detail = _extract_error_body(e.read())
            raise ApiError(f"HTTP {e.code}: {detail[:300]}") from e
        except urllib.error.URLError as e:
            raise ApiError(f"网络错误: {e.reason}") from e
        except TimeoutError as e:
            raise ApiError("请求超时") from e
        except Exception as e:
            raise ApiError(f"请求失败: {e}") from e

        try:
            data = json.loads(raw.decode("utf-8", errors="replace"))
        except Exception as e:
            raise ApiError("响应不是合法 JSON") from e

        content = _extract_content(data)
        if not content:
            raise ApiError("模型返回空内容")
        return content
