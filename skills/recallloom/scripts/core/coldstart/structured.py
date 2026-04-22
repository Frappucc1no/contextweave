#!/usr/bin/env python3
"""Structured proposal/review parsing for RecallLoom cold start flows."""

from __future__ import annotations

import re

MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.*?)\s*$")
HEADING_NUMBER_PREFIX_RE = re.compile(r"^\s*[0-9]+(?:\.[0-9]+)*[.)、:：-]?\s*")

PROPOSAL_SECTION_ALIASES = {
    "source_summary": ("来源摘要", "source summary"),
    "source_type_confidence": ("来源类型与可信级别", "source type and confidence"),
    "candidate_current_state": ("候选当前状态事实", "candidate current-state facts"),
    "candidate_milestones": ("候选里程碑事件", "candidate milestone events"),
    "candidate_reversals": ("候选判断反转", "candidate judgment reversals"),
    "candidate_next_step": ("候选下一步变化", "candidate next-step changes"),
    "conflicts_with_sidecar": ("与当前 sidecar 的冲突", "conflicts with current sidecar"),
    "suggested_promotion_actions": ("建议提升动作", "suggested promotion actions"),
    "review_conclusion": ("审阅结论", "review conclusion"),
}

REVIEW_SECTION_ALIASES = {
    "proposal_reference": ("proposal reference", "提案引用"),
    "review_outcome": ("review outcome", "审阅结论"),
    "approved_items": ("approved items", "通过项"),
    "rejected_items": ("rejected items", "拒绝项"),
    "promotion_status": ("promotion status", "提升状态"),
    "next_action": ("next action", "下一步"),
}

PROMOTION_TARGET_MARKERS = (
    "rolling_summary.md",
    "context_brief.md",
    "daily_logs/",
    "daily_logs\\",
    "daily log",
)

NEGATED_APPROVAL_MARKERS = (
    "not approve",
    "not approved",
    "not yet approved",
    "do not approve",
    "do not accept",
    "not accepted",
    "未批准",
    "尚未批准",
    "不批准",
    "未通过",
    "尚未通过",
    "不通过",
)
HINT_ONLY_MARKERS = ("hint-only", "hint only", "保留为 hint", "仅提示", "only hint")
NEGATED_HINT_ONLY_MARKERS = (
    "no items remain hint-only",
    "no item remains hint-only",
    "no hint-only items remain",
    "not hint-only",
    "无 hint",
)


def _normalize_heading_title(raw: str) -> str:
    title = HEADING_NUMBER_PREFIX_RE.sub("", raw.strip())
    title = title.strip().strip(":：-").strip()
    return title.casefold()


def extract_heading_sections(text: str) -> dict[str, str]:
    sections: dict[str, list[str]] = {}
    current_key: str | None = None
    for line in text.splitlines():
        match = MARKDOWN_HEADING_RE.match(line)
        if match:
            current_key = _normalize_heading_title(match.group("title"))
            sections.setdefault(current_key, [])
            continue
        if current_key is not None:
            sections[current_key].append(line)
    return {
        key: "\n".join(lines).strip()
        for key, lines in sections.items()
    }


def extract_structured_sections(text: str, aliases: dict[str, tuple[str, ...]]) -> dict[str, str]:
    sections = extract_heading_sections(text)
    structured: dict[str, str] = {}
    for canonical_key, alias_group in aliases.items():
        for alias in alias_group:
            normalized_alias = _normalize_heading_title(alias)
            if normalized_alias in sections:
                structured[canonical_key] = sections[normalized_alias]
                break
    return structured


def detect_source_tiers(text: str) -> list[str]:
    found: list[str] = []
    seen: set[str] = set()
    for match in re.finditer(r"\btier\s*([A-F])\b", text, flags=re.I):
        tier = match.group(1).upper()
        if tier not in seen:
            seen.add(tier)
            found.append(tier)
    return found


def detect_promotion_targets(text: str) -> list[str]:
    found: list[str] = []
    lowered = text.casefold()
    for marker in PROMOTION_TARGET_MARKERS:
        if marker.casefold() in lowered:
            found.append(marker)
    return found


def has_non_negated_hint_only_signal(text: str) -> bool:
    for line in text.splitlines():
        lowered = line.casefold()
        if not any(keyword in lowered for keyword in HINT_ONLY_MARKERS):
            continue
        if any(keyword in lowered for keyword in NEGATED_HINT_ONLY_MARKERS):
            continue
        return True
    return False


def classify_review_action(review_sections: dict[str, str]) -> str:
    review_outcome = review_sections.get("review_outcome", "")
    promotion_status = review_sections.get("promotion_status", "")
    lowered = " ".join([review_outcome, promotion_status]).casefold()

    if any(keyword in lowered for keyword in ("reject", "rejected", "拒绝")):
        return "reject"
    if any(keyword in lowered for keyword in NEGATED_APPROVAL_MARKERS):
        return "unspecified"
    if has_non_negated_hint_only_signal("\n".join([review_outcome, promotion_status])):
        if any(keyword in lowered for keyword in ("approve", "approved", "accept", "通过", "批准", "selective")):
            return "accept_after_edit"
        return "hint_only"
    if any(keyword in lowered for keyword in ("modify", "modified", "edit", "edited", "修改", "selective")):
        if any(keyword in lowered for keyword in ("approve", "approved", "accept", "通过", "批准")):
            return "accept_after_edit"
    if any(keyword in lowered for keyword in ("approve", "approved", "accept", "accepted", "通过", "批准")):
        return "accept"
    return "unspecified"


def promotion_ready_for_action(review_action: str) -> bool:
    return review_action in {"accept", "accept_after_edit"}
