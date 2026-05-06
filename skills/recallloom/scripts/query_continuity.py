#!/usr/bin/env python3
"""Query RecallLoom continuity files through a read-only recall surface."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from core.continuity.freshness import (
    continuity_state_for_workspace as shared_continuity_state_for_workspace,
    evaluate_continuity_freshness,
    freshness_risk_summary,
    summary_matches_empty_shell_template as shared_summary_matches_empty_shell_template,
)
from core.trust.state import evaluate_trust_state

from _common import (
    ConfigContractError,
    DAILY_LOGS_DIRNAME,
    cli_failure_payload,
    cli_failure_payload_for_exception,
    enforce_package_support_gate,
    exit_with_cli_error,
    ensure_supported_python_version,
    EnvironmentContractError,
    extract_section_text,
    find_recallloom_root,
    FILE_KEYS,
    invalid_iso_like_daily_log_files,
    latest_active_daily_log,
    load_workspace_state,
    MARKDOWN_HEADING_RE,
    parse_daily_log_entry_line,
    parse_file_state_marker,
    parse_iso_date,
    public_project_path,
    public_project_root_label,
    read_text,
    scan_auto_attached_context_text,
    section_keys_in_text,
    sorted_daily_log_files,
    StorageResolutionError,
)


SOURCE_TYPE_PRIORITY = {
    "rolling_summary": 4,
    "context_brief": 3,
    "latest_daily_log": 2,
    "recent_daily_log": 1,
}

SUPPORTING_CONTEXT_WINDOW_MAX_TOKENS = 160

CJK_RUN_RE = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff]+")
ASCII_TOKEN_RE = re.compile(r"[A-Za-z0-9_/-]+")

PLACEHOLDER_RECALL_LINES = {
    "write the validated handoff-first state here:",
    "active state",
    "relevant files",
    "critical context",
    "record the coordination judgments that matter right now:",
    "key decisions",
    "active assumptions",
    "tradeoffs in force",
    "make blocker visibility explicit:",
    "blocked items",
    "open questions",
    "external dependencies",
    "describe the handoff-first next move:",
    "active task",
    "owner or role when known",
    "immediate next action",
    "这里优先写 handoff-first 的已确认当前状态：",
    "当前活跃状态",
    "相关文件",
    "关键上下文",
    "这里记录当前真正影响推进的判断：",
    "关键决策",
    "当前假设",
    "仍在生效的取舍",
    "把阻塞与未决问题写清楚：",
    "当前阻塞",
    "未决问题",
    "外部依赖",
    "这里写 handoff-first 的下一步：",
    "当前任务",
    "已知负责人或角色",
    "立刻要做的动作",
    "-",
    "none",
    "n/a",
    "todo",
    "tbd",
    "无",
    "暂无",
}
PLACEHOLDER_RECALL_LINES = {item.casefold() for item in PLACEHOLDER_RECALL_LINES}

QUERY_INTENT_KEYWORDS = {
    "status": (
        "status",
        "current state",
        "state",
        "状态",
        "现状",
        "当前状态",
        "现在情况",
    ),
    "next_step": (
        "next step",
        "next",
        "todo",
        "下一步",
        "接下来",
        "下一项",
        "后续",
    ),
    "risk": (
        "risk",
        "blocker",
        "issue",
        "风险",
        "阻塞",
        "问题",
        "隐患",
    ),
    "decision": (
        "decision",
        "judgment",
        "choice",
        "决策",
        "决定",
        "判断",
    ),
    "progress": (
        "progress",
        "milestone",
        "done",
        "进展",
        "里程碑",
        "完成",
        "推进",
    ),
    "background": (
        "background",
        "context",
        "why",
        "背景",
        "上下文",
        "缘由",
        "为什么",
    ),
    "timeline": (
        "timeline",
        "when",
        "date",
        "时间线",
        "什么时候",
        "日期",
    ),
}

INTENT_SECTION_BOOSTS = {
    "status": {
        ("rolling_summary", "current_state"): 6,
        ("context_brief", "current_phase"): 3,
        ("latest_daily_log", "confirmed_facts"): 2,
    },
    "next_step": {
        ("rolling_summary", "next_step"): 8,
        ("latest_daily_log", "recommended_next_step"): 5,
        ("recent_daily_log", "recommended_next_step"): 4,
    },
    "risk": {
        ("rolling_summary", "risks_open_questions"): 8,
        ("latest_daily_log", "risks_blockers"): 5,
        ("recent_daily_log", "risks_blockers"): 4,
    },
    "decision": {
        ("rolling_summary", "active_judgments"): 7,
        ("latest_daily_log", "key_decisions"): 6,
        ("recent_daily_log", "key_decisions"): 5,
    },
    "progress": {
        ("latest_daily_log", "work_completed"): 7,
        ("recent_daily_log", "work_completed"): 6,
        ("rolling_summary", "recent_pivots"): 3,
    },
    "background": {
        ("context_brief", "mission"): 7,
        ("context_brief", "source_of_truth"): 6,
        ("context_brief", "core_workflow"): 5,
        ("context_brief", "scope"): 4,
    },
    "timeline": {
        ("recent_daily_log", "work_completed"): 5,
        ("latest_daily_log", "work_completed"): 4,
        ("context_brief", "current_phase"): 3,
    },
}

SECTION_PRIORITY = {
    "rolling_summary": {
        "current_state": 5,
        "active_judgments": 4,
        "next_step": 3,
        "risks_open_questions": 2,
        "recent_pivots": 1,
    },
    "context_brief": {
        "current_phase": 5,
        "mission": 4,
        "source_of_truth": 4,
        "core_workflow": 3,
        "scope": 2,
        "boundaries": 2,
        "audience_stakeholders": 1,
    },
    "latest_daily_log": {
        "confirmed_facts": 5,
        "key_decisions": 4,
        "recommended_next_step": 3,
        "work_completed": 2,
        "risks_blockers": 1,
    },
    "recent_daily_log": {
        "confirmed_facts": 5,
        "key_decisions": 4,
        "recommended_next_step": 3,
        "work_completed": 2,
        "risks_blockers": 1,
    },
}

def summary_matches_empty_shell_template(summary_text: str) -> bool:
    return shared_summary_matches_empty_shell_template(summary_text)


def continuity_state_for_workspace(
    *,
    state: dict,
    summary_text: str,
    latest_daily_log_exists: bool,
) -> tuple[str, bool]:
    return shared_continuity_state_for_workspace(
        state=state,
        summary_text=summary_text,
        latest_daily_log_exists=latest_daily_log_exists,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Query RecallLoom continuity through a read-only recall surface."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument("--query", required=True, help="Query text.")
    parser.add_argument("--limit", type=int, default=5, help="Maximum number of hits to return. Defaults to 5.")
    parser.add_argument(
        "--include-daily-logs",
        action="store_true",
        help="Include recent daily logs beyond the latest active daily log.",
    )
    parser.add_argument(
        "--mode",
        choices=["brief", "detailed"],
        default="brief",
        help="Output verbosity. Defaults to brief.",
    )
    scan_mode_group = parser.add_mutually_exclusive_group()
    scan_mode_group.add_argument(
        "--quick",
        action="store_true",
        help="Use the quick freshness path only. This is the default query behavior.",
    )
    scan_mode_group.add_argument(
        "--full",
        action="store_true",
        help="Run the heavier workspace-artifact freshness scan before answering.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def _add_unique(target: list[str], seen: set[str], value: str) -> None:
    normalized = value.casefold()
    if normalized in seen:
        return
    seen.add(normalized)
    target.append(normalized)


def analyze_query(query: str) -> dict:
    stripped = query.strip()
    if not stripped:
        return {
            "terms": [],
            "error_kind": "empty_query",
            "intent": "general",
            "matched_keywords": [],
        }

    ascii_tokens = ASCII_TOKEN_RE.findall(query)
    cjk_runs = CJK_RUN_RE.findall(query)
    terms: list[str] = []
    seen: set[str] = set()
    short_fragments_found = False

    for token in ascii_tokens:
        if len(token) >= 2:
            _add_unique(terms, seen, token)
        else:
            short_fragments_found = True

    for run in cjk_runs:
        if len(run) >= 2:
            _add_unique(terms, seen, run)
            for idx in range(0, len(run) - 1):
                _add_unique(terms, seen, run[idx : idx + 2])
        else:
            short_fragments_found = True

    if terms:
        interpretation = interpret_query(query)
        return {
            "terms": terms,
            "error_kind": None,
            "intent": interpretation["intent"],
            "matched_keywords": interpretation["matched_keywords"],
        }

    if ascii_tokens or cjk_runs or short_fragments_found:
        error_kind = "query_too_short"
    else:
        error_kind = "no_searchable_fragments"
    return {
        "terms": [],
        "error_kind": error_kind,
        "intent": "general",
        "matched_keywords": [],
    }


def tokenize_query(query: str) -> list[str]:
    return analyze_query(query)["terms"]


def interpret_query(query: str) -> dict:
    lowered = query.casefold()
    best_intent = "general"
    best_keywords: list[str] = []
    best_score = 0

    for intent, keywords in QUERY_INTENT_KEYWORDS.items():
        matched = [keyword for keyword in keywords if keyword.casefold() in lowered]
        if len(matched) > best_score:
            best_score = len(matched)
            best_intent = intent
            best_keywords = matched

    return {
        "intent": best_intent,
        "matched_keywords": best_keywords,
    }


def score_text(text: str, query_terms: list[str]) -> int:
    lowered = normalized_recall_text(text)
    return sum(lowered.count(term) for term in query_terms)


def matched_query_terms(text: str, query_terms: list[str]) -> int:
    lowered = normalized_recall_text(text)
    unique_terms = []
    seen: set[str] = set()
    for term in query_terms:
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return sum(1 for term in unique_terms if term in lowered)


def normalized_content_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue
        if MARKDOWN_HEADING_RE.match(stripped):
            continue
        stripped = stripped.lstrip("-* ").strip()
        if not stripped:
            continue
        if stripped.casefold() in PLACEHOLDER_RECALL_LINES:
            continue
        lines.append(stripped)
    return lines


def normalized_recall_text(text: str) -> str:
    return "\n".join(normalized_content_lines(text)).casefold()


def excerpt_text(text: str, *, max_lines: int = 5) -> str:
    return "\n".join(normalized_content_lines(text)[:max_lines])


def gather_file_hits(
    *,
    path: Path,
    source_type: str,
    query_terms: list[str],
    full_query: str,
) -> list[dict]:
    text = read_text(path)
    hits: list[dict] = []
    keys = section_keys_in_text(text)
    if not keys:
        score = score_text(text, query_terms)
        if score > 0:
            exact_phrase = full_query in normalized_recall_text(text)
            hits.append(
                {
                    "path": str(path),
                    "section": None,
                    "score": score,
                    "matched_terms": matched_query_terms(text, query_terms),
                    "exact_phrase": exact_phrase,
                    "source_type": source_type,
                    "excerpt": excerpt_text(text),
                }
            )
        return hits

    for key in keys:
        section_text = extract_section_text(text, key)
        score = score_text(section_text, query_terms)
        if score <= 0:
            continue
        exact_phrase = full_query in normalized_recall_text(section_text)
        hits.append(
            {
                "path": str(path),
                "section": key,
                "score": score,
                "matched_terms": matched_query_terms(section_text, query_terms),
                "exact_phrase": exact_phrase,
                "source_type": source_type,
                "excerpt": excerpt_text(section_text),
            }
        )
    return hits


def supporting_context_window(
    hits: list[dict],
    *,
    mode: str,
) -> list[dict]:
    if mode != "detailed":
        return []
    window: list[dict] = []
    consumed_tokens = 0
    for item in hits[:3]:
        excerpt_budget = token_estimate(item["excerpt"])
        if window and consumed_tokens + excerpt_budget > SUPPORTING_CONTEXT_WINDOW_MAX_TOKENS:
            break
        window.append(
            {
                "path": item["path"],
                "section": item["section"],
                "source_type": item["source_type"],
                "date": item.get("date"),
                "excerpt": item["excerpt"],
                "score": item["score"],
            }
        )
        consumed_tokens += excerpt_budget
    return window


def token_estimate(text: str) -> int:
    ascii_tokens = len(ASCII_TOKEN_RE.findall(text))
    cjk_chars = sum(len(run) for run in CJK_RUN_RE.findall(text))
    non_whitespace = len(re.findall(r"\S", text))
    residual_tokens = max(0, non_whitespace - cjk_chars - ascii_tokens)
    estimate = (ascii_tokens / 0.75) + (cjk_chars * 0.65) + residual_tokens
    return max(1, round(estimate))


def budget_hint(estimate: int) -> str:
    if estimate <= 120:
        return "small"
    if estimate <= 300:
        return "medium"
    return "large"


def output_variant_for_mode(mode: str) -> str:
    if mode == "detailed":
        return "expanded_contextual"
    return "compact_attach_safe"


def source_priority(source_type: str) -> int:
    return SOURCE_TYPE_PRIORITY.get(source_type, 0)


def section_priority(source_type: str, section: str | None, *, query_intent: str = "general") -> int:
    if section is None:
        return 0
    base = SECTION_PRIORITY.get(source_type, {}).get(section, 0)
    boost = INTENT_SECTION_BOOSTS.get(query_intent, {}).get((source_type, section), 0)
    return base + boost


def log_recency_value(path_raw: str, source_type: str) -> int:
    if source_type not in {"latest_daily_log", "recent_daily_log"}:
        return 0
    try:
        return parse_iso_date(Path(path_raw).stem).toordinal()
    except ValueError:
        return 0


def sort_hits(hits: list[dict], *, query_intent: str = "general") -> list[dict]:
    ordered = list(hits)
    ordered.sort(
        key=lambda item: (
            -int(item["exact_phrase"]),
            -item["matched_terms"],
            -item["score"],
            -source_priority(item["source_type"]),
            -section_priority(item["source_type"], item["section"], query_intent=query_intent),
            -log_recency_value(item["path"], item["source_type"]),
            item["path"],
            item["section"] or "",
        )
    )
    return ordered


def citation_date(path_raw: str, source_type: str) -> str | None:
    if source_type not in {"latest_daily_log", "recent_daily_log"}:
        return None
    try:
        return parse_iso_date(Path(path_raw).stem).isoformat()
    except ValueError:
        return None


def conflict_state_for_hits(
    *,
    freshness: dict,
    hits: list[dict],
    continuity_state: str,
) -> str:
    if continuity_state == "initialized_empty_shell":
        return "empty_shell_not_seeded"
    if freshness["workspace_artifact_newer_than_summary"]:
        return "workspace_artifact_newer_than_summary"
    if freshness["summary_revision_stale"]:
        return "summary_revision_stale"
    if len(hits) >= 2:
        first = hits[0]
        second = hits[1]
        same_strength = (
            first["exact_phrase"] == second["exact_phrase"]
            and first["matched_terms"] == second["matched_terms"]
            and first["score"] == second["score"]
        )
        if same_strength and first["source_type"] != second["source_type"]:
            return "multi_source_review_recommended"
    return "none"


def confidence_for_hits(
    continuity_confidence: str,
    hits: list[dict],
    *,
    continuity_state: str,
    conflict_state: str,
    query_terms: list[str],
) -> str:
    if continuity_state == "initialized_empty_shell":
        return "low"
    if not hits:
        return "low"
    if continuity_confidence == "broken":
        return "low"
    top_hit = hits[0]
    strong_match = (
        top_hit["exact_phrase"]
        or top_hit["matched_terms"] >= max(1, len(set(query_terms)))
        or top_hit["score"] >= max(2, len(set(query_terms)))
    )
    if conflict_state in {"workspace_artifact_newer_than_summary", "summary_revision_stale"}:
        return "medium" if strong_match and continuity_confidence != "low" else "low"
    if conflict_state == "multi_source_review_recommended":
        return "medium"
    if continuity_confidence == "high" and strong_match:
        return "high"
    if strong_match:
        return "medium"
    return "low"


def public_hits(hits: list[dict]) -> list[dict]:
    return [
        {
            "path": item["path"],
            "section": item["section"],
            "score": item["score"],
            "source_type": item["source_type"],
            "date": citation_date(item["path"], item["source_type"]),
            "excerpt": item["excerpt"],
        }
        for item in hits
    ]


def render_synthesized_recall(
    *,
    query: str,
    answer: str,
    citations: list[dict],
    hits: list[dict],
    mode: str,
    risk_freshness_note: str | None,
) -> str:
    lines = [f"Query: {query}", "", f"Answer: {answer}"]
    if citations:
        lines.extend(["", "Supporting citations:"])
        citation_items = citations if mode == "detailed" else citations[:3]
        for item in citation_items:
            section_label = f" [{item['section']}]" if item["section"] else ""
            date_suffix = f" ({item['date']})" if item["date"] else ""
            lines.append(f"- {Path(item['path']).name}{section_label}{date_suffix}")
    if hits and mode == "detailed":
        lines.extend(["", "Supporting excerpts:"])
        for item in hits:
            section_label = f" [{item['section']}]" if item["section"] else ""
            source_label = f" ({item['source_type']})"
            lines.append(
                f"- {Path(item['path']).name}{section_label}{source_label}: {item['excerpt']}"
            )
    if risk_freshness_note:
        lines.extend(["", f"Risk/Freshness note: {risk_freshness_note}"])
    return "\n".join(lines).strip()


def answer_for_query(*, hits: list[dict], continuity_state: str) -> str:
    if continuity_state == "initialized_empty_shell":
        return "Continuity is initialized but not seeded yet; no project-state answer is available."
    if not hits:
        return "No strong continuity answer was found in the current core continuity files."
    return hits[0]["excerpt"]


def risk_freshness_note_for_query(
    *,
    freshness: dict,
    conflict_state: str,
    continuity_state: str,
    update_protocol_present: bool,
) -> str | None:
    notes: list[str] = []
    if continuity_state == "initialized_empty_shell":
        notes.append("Seed rolling_summary.md with real state before relying on continuity recall.")
    elif conflict_state == "multi_source_review_recommended":
        notes.append("Multiple sources tie for the top answer. Review supporting citations before trusting recall for writes.")
    elif conflict_state != "none":
        notes.append(
            f"{conflict_state}. Review current workspace state before trusting this recall for writes."
        )

    freshness_risk = freshness_risk_summary(
        workspace_artifact_scan_mode=freshness["workspace_artifact_scan_mode"],
        workspace_artifact_scan_performed=freshness["workspace_artifact_scan_performed"],
        workspace_artifact_newer_than_summary=freshness["workspace_artifact_newer_than_summary"],
        summary_revision_stale=freshness["summary_revision_stale"],
        continuity_confidence=freshness["continuity_confidence"],
    )
    if freshness_risk["note"] and freshness_risk["note"] not in notes:
        notes.append(freshness_risk["note"])

    if update_protocol_present:
        notes.append("Review update_protocol.md before turning continuity recall into a write decision.")

    return " ".join(notes) if notes else None


def attach_scan_text_surface(
    *,
    synthesized_recall: str,
    hits: list[dict],
    supporting_window: list[dict],
) -> str:
    parts = [synthesized_recall]
    for item in hits:
        parts.append(item["excerpt"])
    for item in supporting_window:
        parts.append(item["excerpt"])
    return "\n".join(part for part in parts if part.strip())


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload=cli_failure_payload("python_runtime_unavailable", error=str(exc)),
        )
    enforce_package_support_gate(parser, json_mode=args.json)

    if args.limit < 1:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message="--limit must be >= 1",
            payload=cli_failure_payload("invalid_prepared_input", error="--limit must be >= 1"),
        )

    query_analysis = analyze_query(args.query)
    query_terms = query_analysis["terms"]
    if not query_terms:
        error_messages = {
            "empty_query": "Query is empty. Provide a search question or phrase.",
            "query_too_short": "Query is too short. Add at least one meaningful English token or a two-character Chinese phrase.",
            "no_searchable_fragments": "Query does not contain any searchable fragments.",
        }
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=error_messages[query_analysis["error_kind"]],
            payload=cli_failure_payload(
                "invalid_prepared_input",
                error=error_messages[query_analysis["error_kind"]],
            ),
        )
    full_query = args.query.strip().casefold()

    try:
        workspace = find_recallloom_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload=cli_failure_payload_for_exception(exc, default_reason="damaged_sidecar"),
        )
    if workspace is None:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=1,
            message="No RecallLoom project root found.",
            payload=cli_failure_payload(
                "no_project_root",
                error="No RecallLoom project root found.",
                details={"project_root": str(Path(args.path).expanduser().resolve())},
            ),
        )

    summary_path = workspace.storage_root / FILE_KEYS["rolling_summary"]
    context_brief_path = workspace.storage_root / FILE_KEYS["context_brief"]
    state_path = workspace.storage_root / FILE_KEYS["state"]
    update_protocol_path = workspace.storage_root / FILE_KEYS["update_protocol"]
    logs_dir = workspace.storage_root / DAILY_LOGS_DIRNAME

    try:
        invalid_daily_logs = invalid_iso_like_daily_log_files(logs_dir)
        if invalid_daily_logs:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=(
                    "Refusing query because one or more daily log filenames match the date pattern but are invalid ISO dates:\n"
                    + "\n".join(str(path) for path in invalid_daily_logs)
                ),
                payload=cli_failure_payload(
                    "malformed_managed_file",
                    error=(
                        "Refusing query because one or more daily log filenames match the date pattern but are invalid ISO dates:\n"
                        + "\n".join(str(path) for path in invalid_daily_logs)
                    ),
                ),
            )
        state = load_workspace_state(state_path)
        summary_text = read_text(summary_path)
        summary_state = parse_file_state_marker(summary_text)
        if summary_state is None:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file-state metadata marker: {summary_path}",
                payload=cli_failure_payload(
                    "malformed_managed_file",
                    error=f"Missing required file-state metadata marker: {summary_path}",
                ),
            )
        if context_brief_path.is_file():
            context_brief_state = parse_file_state_marker(read_text(context_brief_path))
            if context_brief_state is None:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Missing required file-state metadata marker: {context_brief_path}",
                    payload=cli_failure_payload(
                        "malformed_managed_file",
                        error=f"Missing required file-state metadata marker: {context_brief_path}",
                    ),
                )
        if update_protocol_path.is_file():
            update_protocol_state = parse_file_state_marker(read_text(update_protocol_path))
            if update_protocol_state is None:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Missing required file-state metadata marker: {update_protocol_path}",
                    payload=cli_failure_payload(
                        "malformed_managed_file",
                        error=f"Missing required file-state metadata marker: {update_protocol_path}",
                    ),
                )
        latest_daily_log = latest_active_daily_log(logs_dir)
        latest_daily_log_text = read_text(latest_daily_log) if latest_daily_log is not None else ""
        if latest_daily_log is not None and not any(
            parse_daily_log_entry_line(line) is not None
            for line in latest_daily_log_text.splitlines()
        ):
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=(
                    "Missing required daily-log-entry metadata marker in the latest ISO-dated daily log: "
                    f"{latest_daily_log}"
                ),
                payload=cli_failure_payload(
                    "malformed_managed_file",
                    error=(
                        "Missing required daily-log-entry metadata marker in the latest ISO-dated daily log: "
                        f"{latest_daily_log}"
                    ),
                ),
            )
        scan_mode = "full" if args.full else "quick"
        freshness = evaluate_continuity_freshness(
            project_root=workspace.project_root,
            storage_root=workspace.storage_root,
            summary_path=summary_path,
            workspace_revision=state["workspace_revision"],
            summary_base_workspace_revision=summary_state.base_workspace_revision,
            latest_daily_log_exists=latest_daily_log is not None,
            scan_mode=scan_mode,
        )
        continuity_state, continuity_seeded = continuity_state_for_workspace(
            state=state,
            summary_text=summary_text,
            latest_daily_log_exists=latest_daily_log is not None,
        )
    except (OSError, UnicodeDecodeError, KeyError, ConfigContractError) as exc:
        message = f"Filesystem/state error: {exc}"
        if isinstance(exc, ConfigContractError):
            failure_contract = cli_failure_payload(
                getattr(exc, "failure_reason", None) or "damaged_sidecar",
                error=message,
            )
        else:
            failure_contract = cli_failure_payload("damaged_sidecar", error=message)
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=message,
            payload=failure_contract,
        )

    continuity_has_seeded_state = continuity_state != "initialized_empty_shell"
    sources_considered: list[dict] = [
        {
            "path": str(summary_path),
            "source_type": "rolling_summary",
            "included": continuity_has_seeded_state,
        },
        {
            "path": str(context_brief_path),
            "source_type": "context_brief",
            "included": continuity_has_seeded_state and context_brief_path.is_file(),
        },
        {"path": str(update_protocol_path), "source_type": "update_protocol", "included": update_protocol_path.is_file()},
    ]

    hits: list[dict] = []
    if continuity_has_seeded_state:
        hits.extend(
            gather_file_hits(
                path=summary_path,
                source_type="rolling_summary",
                query_terms=query_terms,
                full_query=full_query,
            )
        )
    if continuity_has_seeded_state and context_brief_path.is_file():
        hits.extend(
            gather_file_hits(
                path=context_brief_path,
                source_type="context_brief",
                query_terms=query_terms,
                full_query=full_query,
            )
        )

    if continuity_has_seeded_state and latest_daily_log is not None:
        sources_considered.append(
            {"path": str(latest_daily_log), "source_type": "latest_daily_log", "included": True}
        )
        hits.extend(
            gather_file_hits(
                path=latest_daily_log,
                source_type="latest_daily_log",
                query_terms=query_terms,
                full_query=full_query,
            )
        )

    if continuity_has_seeded_state and args.include_daily_logs:
        recent_logs = sorted_daily_log_files(logs_dir)[-3:]
        for log_path in recent_logs:
            if latest_daily_log is not None and log_path == latest_daily_log:
                continue
            sources_considered.append(
                {"path": str(log_path), "source_type": "recent_daily_log", "included": True}
            )
            hits.extend(
                gather_file_hits(
                    path=log_path,
                    source_type="recent_daily_log",
                    query_terms=query_terms,
                    full_query=full_query,
                )
            )

    hits = sort_hits(hits, query_intent=query_analysis["intent"])
    hits = hits[: args.limit]
    conflict_state = conflict_state_for_hits(
        freshness=freshness,
        hits=hits,
        continuity_state=continuity_state,
    )

    citations = [
        {
            "path": item["path"],
            "section": item["section"],
            "source_type": item["source_type"],
            "date": citation_date(item["path"], item["source_type"]),
        }
        for item in hits
    ]
    public_hit_list = public_hits(hits)
    support_window = supporting_context_window(public_hit_list, mode=args.mode)
    answer = answer_for_query(hits=public_hit_list, continuity_state=continuity_state)
    risk_freshness_note = risk_freshness_note_for_query(
        freshness=freshness,
        conflict_state=conflict_state,
        continuity_state=continuity_state,
        update_protocol_present=update_protocol_path.is_file(),
    )
    synthesized_recall = render_synthesized_recall(
        query=args.query,
        answer=answer,
        citations=citations,
        hits=public_hit_list,
        mode=args.mode,
        risk_freshness_note=risk_freshness_note,
    )

    attach_scan = scan_auto_attached_context_text(
        attach_scan_text_surface(
            synthesized_recall=synthesized_recall,
            hits=public_hit_list,
            supporting_window=support_window,
        )
    )
    if attach_scan["blocked"]:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "Refusing to return attach-safe continuity text because the synthesized recall "
                "failed the attached-text safety scan: "
                + ", ".join(attach_scan["hard_block_reasons"])
            ),
            payload=cli_failure_payload(
                "attach_scan_blocked",
                error=(
                    "Refusing to return attach-safe continuity text because the synthesized recall "
                    "failed the attached-text safety scan: "
                    + ", ".join(attach_scan["hard_block_reasons"])
                ),
                details={"hard_block_reasons": attach_scan["hard_block_reasons"]},
            ),
        )

    estimate = token_estimate(
        attach_scan_text_surface(
            synthesized_recall=synthesized_recall,
            hits=[],
            supporting_window=support_window if args.mode == "detailed" else [],
        )
    )
    trust_state = evaluate_trust_state(
        continuity_confidence=freshness["continuity_confidence"],
        continuity_state=continuity_state,
        summary_stale=freshness["summary_stale"],
        workspace_newer_than_summary=freshness["workspace_newer_than_summary"],
        conflict_state=conflict_state,
    )
    public_project_root = public_project_root_label(workspace.project_root)
    public_storage_root = public_project_path(workspace.storage_root, project_root=workspace.project_root)
    public_update_protocol_path = public_project_path(update_protocol_path, project_root=workspace.project_root)
    public_latest_daily_log = (
        public_project_path(latest_daily_log, project_root=workspace.project_root)
        if latest_daily_log is not None
        else None
    )
    public_latest_workspace_artifact = (
        public_project_path(freshness["latest_workspace_artifact"], project_root=workspace.project_root)
        if freshness["latest_workspace_artifact"] is not None
        else None
    )
    public_sources_considered = [
        {**item, "path": public_project_path(item["path"], project_root=workspace.project_root)}
        for item in sources_considered
    ]
    public_hit_list = [
        {**item, "path": public_project_path(item["path"], project_root=workspace.project_root)}
        for item in public_hit_list
    ]
    citations = [
        {**item, "path": public_project_path(item["path"], project_root=workspace.project_root)}
        for item in citations
    ]
    support_window = [
        {**item, "path": public_project_path(item["path"], project_root=workspace.project_root)}
        for item in support_window
    ]
    payload = {
        "project_root": public_project_root,
        "storage_root": public_storage_root,
        "continuity_confidence": freshness["continuity_confidence"],
        "sidecar_trust_state": trust_state["sidecar_trust_state"],
        "allowed_operation_level": trust_state["allowed_operation_level"],
        "continuity_drift_risk_level": trust_state["continuity_drift_risk_level"],
        "continuity_state": continuity_state,
        "continuity_seeded": continuity_seeded,
        "query": args.query,
        "query_interpretation": {
            "intent": query_analysis["intent"],
            "matched_keywords": query_analysis["matched_keywords"],
            "terms": query_terms,
        },
        "answer": answer,
        "risk_freshness_note": risk_freshness_note,
        "token_estimate": estimate,
        "budget_hint": budget_hint(estimate),
        "output_variant": output_variant_for_mode(args.mode),
        "sources_considered": public_sources_considered,
        "override_review_targets": (
            [
                {
                    "path": public_update_protocol_path,
                    "reason": "review_update_protocol_before_write",
                }
            ]
            if update_protocol_path.is_file()
            else []
        ),
        "hits": public_hit_list,
        "synthesized_recall": synthesized_recall,
        "citations": citations,
        "supporting_context_window": support_window,
        "continuity_snapshot": {
            "workspace_revision_seen": state["workspace_revision"],
            "rolling_summary_revision_seen": summary_state.revision,
            "latest_active_daily_log_seen": public_latest_daily_log,
            "latest_workspace_artifact_seen": public_latest_workspace_artifact,
            "continuity_confidence": freshness["continuity_confidence"],
            "continuity_state": continuity_state,
            "continuity_seeded": continuity_seeded,
            "task_type": "query_continuity",
        },
        "source_type": "core_continuity_only",
        "confidence": confidence_for_hits(
            freshness["continuity_confidence"],
            hits,
            continuity_state=continuity_state,
            conflict_state=conflict_state,
            query_terms=query_terms,
        ),
        "freshness_state": {
            "workspace_artifact_scan_mode": freshness["workspace_artifact_scan_mode"],
            "workspace_artifact_scan_performed": freshness["workspace_artifact_scan_performed"],
            "latest_workspace_artifact": public_latest_workspace_artifact,
            "workspace_artifact_newer_than_summary": freshness["workspace_artifact_newer_than_summary"],
            "summary_revision_stale": freshness["summary_revision_stale"],
            "workspace_newer_than_summary": freshness["workspace_newer_than_summary"],
            "freshness_risk_level": freshness_risk_summary(
                workspace_artifact_scan_mode=freshness["workspace_artifact_scan_mode"],
                workspace_artifact_scan_performed=freshness["workspace_artifact_scan_performed"],
                workspace_artifact_newer_than_summary=freshness["workspace_artifact_newer_than_summary"],
                summary_revision_stale=freshness["summary_revision_stale"],
                continuity_confidence=freshness["continuity_confidence"],
            )["level"],
            "freshness_risk_note": freshness_risk_summary(
                workspace_artifact_scan_mode=freshness["workspace_artifact_scan_mode"],
                workspace_artifact_scan_performed=freshness["workspace_artifact_scan_performed"],
                workspace_artifact_newer_than_summary=freshness["workspace_artifact_newer_than_summary"],
                summary_revision_stale=freshness["summary_revision_stale"],
                continuity_confidence=freshness["continuity_confidence"],
            )["note"],
        },
        "conflict_state": conflict_state,
        "attach_scan": attach_scan,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(synthesized_recall)


if __name__ == "__main__":
    main()
