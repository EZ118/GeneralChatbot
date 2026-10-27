# -*- coding: utf-8 -*-
"""OCR 文本的清理与触发词匹配。

Windows OCR 会在汉字、中文标点、@ 之间插入空格，例如：
    "@周 知 羿 讲 个 笑 话"
这里把它整理成 "@周知羿讲个笑话"，同时保留英文单词之间的空格。
"""

from __future__ import annotations

import re
import unicodedata

_CJK = "\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff"
_CJK_PUNCT = "，。！？；：、（）【】《》〈〉「」『』“”‘’…—～·"
_CJK_LIKE = f"[{_CJK}{_CJK_PUNCT}@＠]"


def compact_ocr_text(text: object) -> str:
    """整理 OCR 行：去掉汉字/中文标点/@ 之间的空格。"""
    if text is None:
        return ""
    s = str(text).replace("\u00a0", " ").replace("\u3000", " ")
    s = re.sub(r"\s+", " ", s).strip()
    if not s:
        return ""

    # 反复处理，直到不再变化（相邻空格会互相影响）
    previous = None
    while previous != s:
        previous = s
        s = re.sub(rf"(?<={_CJK_LIKE}) (?={_CJK_LIKE})", "", s)

    # "第 2 行" -> "第2行"
    s = re.sub(rf"(?<=[{_CJK}]) (?=[0-9])", "", s)
    s = re.sub(rf"(?<=[0-9]) (?=[{_CJK}])", "", s)
    return s.strip()


def normalize_match(text: object) -> str:
    """用于触发词匹配/去重：全角转半角、去掉所有空白、忽略大小写。"""
    if text is None:
        return ""
    s = unicodedata.normalize("NFKC", str(text))
    s = re.sub(r"\s+", "", s)
    return s.casefold()


def contains_trigger(text: object, trigger: object) -> bool:
    trig = normalize_match(trigger)
    if not trig:
        return False
    return trig in normalize_match(text)


def dedupe_key(text: object) -> str:
    return normalize_match(text)


def truncate(text: object, limit: int = 80) -> str:
    s = str(text or "").replace("\r", " ").replace("\n", " ")
    if len(s) <= limit:
        return s
    return s[: max(0, limit - 1)] + "…"
