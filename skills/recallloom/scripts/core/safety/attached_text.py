#!/usr/bin/env python3
"""Attached-text safety scanning for auto-inserted continuity content."""

from __future__ import annotations

import re

INVISIBLE_UNICODE_RE = re.compile(r"[\u200b-\u200f\u2060\u2066-\u2069\ufeff]")

ATTACH_SCAN_HARD_BLOCK_PATTERNS = (
    re.compile(r"\bignore (all )?(previous|prior|above) (instructions|rules|guidance)\b", re.I),
    re.compile(r"\b(disregard|override) (the )?(system prompt|developer message|instructions?)\b", re.I),
    re.compile(r"\b(reveal|print|dump|show|exfiltrat\w*)\b.{0,40}\b(secret|token|password|api key|credential|ssh key|env)\b", re.I | re.S),
    re.compile(r"(忽略|无视).{0,12}(之前|先前|前面|上述|以上).{0,12}(指令|规则|要求|提示)", re.I | re.S),
    re.compile(r"(绕过|覆盖|忽略).{0,12}(系统提示|系统消息|开发者消息|开发者提示|指令|规则)", re.I | re.S),
    re.compile(r"(显示|泄露|输出|打印|导出).{0,40}(secret|token|password|api key|credential|ssh key|env|环境变量|密钥|令牌|密码|凭证|私钥)", re.I | re.S),
)

ATTACH_SCAN_WARNING_PATTERNS = (
    re.compile(r"\b(secret|token|password|credential|api key)\b", re.I),
    re.compile(r"\bignore\b", re.I),
    re.compile(r"(密钥|令牌|密码|凭证|环境变量|API ?key)", re.I),
    re.compile(r"(忽略|无视)", re.I),
)


def scan_auto_attached_context_text(text: str) -> dict:
    hard_block_reasons: list[str] = []
    warnings: list[str] = []

    if INVISIBLE_UNICODE_RE.search(text):
        hard_block_reasons.append("invisible_unicode")

    for pattern in ATTACH_SCAN_HARD_BLOCK_PATTERNS:
        if pattern.search(text):
            hard_block_reasons.append(pattern.pattern)

    for pattern in ATTACH_SCAN_WARNING_PATTERNS:
        if pattern.search(text):
            warnings.append(pattern.pattern)

    return {
        "blocked": bool(hard_block_reasons),
        "hard_block_reasons": hard_block_reasons,
        "warnings": warnings,
    }
