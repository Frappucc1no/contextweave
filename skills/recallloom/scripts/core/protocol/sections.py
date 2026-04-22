#!/usr/bin/env python3
"""Section and heading helpers for RecallLoom protocol files."""

from __future__ import annotations

import re
from typing import Iterable

from core.protocol.contracts import SECTION_MARKER_RE

MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.*?)\s*$")
HEADING_NUMBER_PREFIX_RE = re.compile(r"^\s*[0-9]+(?:\.[0-9]+)*[.)、:：-]?\s*")
UPDATE_PROTOCOL_TIME_POLICY_KEYWORDS = (
    "workday",
    "logical workday",
    "work day",
    "active day",
    "rollover",
    "rollover_hour",
    "timezone",
    "time zone",
    "cross-day",
    "cross day",
    "append target",
    "append date",
    "start new day",
    "close day",
    "yesterday",
    "today",
    "工作日",
    "逻辑工作日",
    "时区",
    "跨天",
    "追加日期",
    "追加日志日期",
    "关闭昨天",
    "开启新的一天",
    "昨天",
    "今天",
)


def extract_section_text(text: str, section_key: str) -> str:
    lines = text.splitlines()
    start_marker = f"<!-- section: {section_key} -->"
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == start_marker:
            start_idx = idx + 1
            break
    if start_idx is None:
        return ""

    collected: list[str] = []
    for line in lines[start_idx:]:
        if line.strip().startswith("<!-- section: "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def markdown_heading_titles(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        match = MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        title = HEADING_NUMBER_PREFIX_RE.sub("", match.group("title").strip())
        title = title.strip().strip(":：-").strip()
        if title:
            headings.append(title.casefold())
    return headings


def missing_recovery_headings(text: str, heading_groups: tuple[tuple[str, ...], ...]) -> list[str]:
    headings = set(markdown_heading_titles(text))
    missing: list[str] = []
    for group in heading_groups:
        if not any(alias.casefold() in headings for alias in group):
            missing.append(group[0])
    return missing


def detect_update_protocol_time_policy_cues(text: str) -> list[str]:
    lowered = text.casefold()
    return [keyword for keyword in UPDATE_PROTOCOL_TIME_POLICY_KEYWORDS if keyword.casefold() in lowered]


def section_keys_in_text(text: str) -> list[str]:
    keys: list[str] = []
    for line in text.splitlines():
        match = SECTION_MARKER_RE.match(line.strip())
        if match:
            keys.append(match.group("section_key"))
    return keys


def missing_section_keys(text: str, required_keys: Iterable[str]) -> list[str]:
    keys = set(section_keys_in_text(text))
    return [key for key in required_keys if key not in keys]


def duplicate_section_keys(text: str) -> list[str]:
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for key in section_keys_in_text(text):
        seen[key] = seen.get(key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            duplicates.append(key)
    return sorted(duplicates)


def unknown_section_keys(text: str, allowed_keys: Iterable[str]) -> list[str]:
    allowed = set(allowed_keys)
    unknown: set[str] = set()
    for key in section_keys_in_text(text):
        if key not in allowed:
            unknown.add(key)
    return sorted(unknown)
