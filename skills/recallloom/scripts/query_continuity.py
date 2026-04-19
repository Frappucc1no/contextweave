#!/usr/bin/env python3
"""Query RecallLoom continuity files through a read-only recall surface."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from _common import (
    ConfigContractError,
    continuity_digest_bundle,
    evaluate_continuity_freshness,
    exit_with_cli_error,
    FILE_KEYS,
    ensure_supported_python_version,
    EnvironmentContractError,
    extract_section_text,
    find_recallloom_root,
    latest_active_daily_log,
    parse_file_state_marker,
    parse_iso_date,
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
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def tokenize_query(query: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[A-Za-z0-9_/-]+", query) if len(token) >= 2]


def score_text(text: str, query_terms: list[str]) -> int:
    lowered = text.casefold()
    return sum(lowered.count(term) for term in query_terms)


def matched_query_terms(text: str, query_terms: list[str]) -> int:
    lowered = text.casefold()
    unique_terms = []
    seen: set[str] = set()
    for term in query_terms:
        if term in seen:
            continue
        seen.add(term)
        unique_terms.append(term)
    return sum(1 for term in unique_terms if term in lowered)


def excerpt_text(text: str, *, max_lines: int = 5) -> str:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue
        stripped = stripped.lstrip("-* ").strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= max_lines:
            break
    return "\n".join(lines)


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
            exact_phrase = full_query in text.casefold()
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
        exact_phrase = full_query in section_text.casefold()
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
                "excerpt": item["excerpt"],
                "score": item["score"],
            }
        )
        consumed_tokens += excerpt_budget
    return window


def token_estimate(text: str) -> int:
    words = len(re.findall(r"\S+", text))
    return max(1, round(words / 0.75))


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


def section_priority(source_type: str, section: str | None) -> int:
    if section is None:
        return 0
    return SECTION_PRIORITY.get(source_type, {}).get(section, 0)


def log_recency_value(path_raw: str, source_type: str) -> int:
    if source_type not in {"latest_daily_log", "recent_daily_log"}:
        return 0
    try:
        return parse_iso_date(Path(path_raw).stem).toordinal()
    except ValueError:
        return 0


def sort_hits(hits: list[dict]) -> list[dict]:
    ordered = list(hits)
    ordered.sort(
        key=lambda item: (
            -int(item["exact_phrase"]),
            -item["matched_terms"],
            -item["score"],
            -source_priority(item["source_type"]),
            -section_priority(item["source_type"], item["section"]),
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
) -> str:
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
    conflict_state: str,
    query_terms: list[str],
) -> str:
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
    hits: list[dict],
    mode: str,
    conflict_state: str,
    update_protocol_present: bool,
) -> str:
    lines = [f"Query: {query}", ""]
    if not hits:
        lines.append("No strong continuity hits were found in the current core continuity files.")
        if update_protocol_present:
            lines.extend(
                [
                    "",
                    "Project-local note: review update_protocol.md before turning continuity recall into a write decision.",
                ]
            )
        return "\n".join(lines).strip()

    if mode == "detailed":
        lines.append("Relevant continuity recall (expanded):")
        for item in hits:
            section_label = f" [{item['section']}]" if item["section"] else ""
            source_label = f" ({item['source_type']})"
            lines.append(
                f"- {Path(item['path']).name}{section_label}{source_label}: {item['excerpt']}"
            )
    else:
        lines.append("Relevant continuity recall (compact attach-safe):")
        for item in hits[:3]:
            section_label = f" [{item['section']}]" if item["section"] else ""
            lines.append(f"- {Path(item['path']).name}{section_label}: {item['excerpt']}")

    if conflict_state != "none":
        lines.extend(
            [
                "",
                f"Freshness note: {conflict_state}. Review current workspace state before trusting this recall for writes.",
            ]
        )
    if update_protocol_present:
        lines.extend(
            [
                "",
                "Project-local note: review update_protocol.md before turning continuity recall into a write decision.",
            ]
        )
    return "\n".join(lines).strip()


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
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    if args.limit < 1:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message="--limit must be >= 1")

    query_terms = tokenize_query(args.query)
    if not query_terms:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message="Query must contain searchable terms.")
    full_query = args.query.strip().casefold()

    try:
        workspace = find_recallloom_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No RecallLoom project root found.")

    summary_path = workspace.storage_root / FILE_KEYS["rolling_summary"]
    context_brief_path = workspace.storage_root / FILE_KEYS["context_brief"]
    state_path = workspace.storage_root / FILE_KEYS["state"]
    update_protocol_path = workspace.storage_root / FILE_KEYS["update_protocol"]
    logs_dir = workspace.storage_root / "daily_logs"

    try:
        state = json.loads(read_text(state_path))
        summary_state = parse_file_state_marker(read_text(summary_path))
        if summary_state is None:
            exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Missing required file-state metadata marker: {summary_path}")
        latest_daily_log = latest_active_daily_log(logs_dir)
        freshness = evaluate_continuity_freshness(
            project_root=workspace.project_root,
            storage_root=workspace.storage_root,
            summary_path=summary_path,
            workspace_revision=state["workspace_revision"],
            summary_base_workspace_revision=summary_state.base_workspace_revision,
            latest_daily_log_exists=latest_daily_log is not None,
            scan_mode="full",
        )
        summary_text = read_text(summary_path)
        latest_daily_log_text = read_text(latest_daily_log) if latest_daily_log is not None else ""
    except (OSError, UnicodeDecodeError, KeyError, json.JSONDecodeError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem/state error: {exc}")

    sources_considered: list[dict] = [
        {"path": str(summary_path), "source_type": "rolling_summary", "included": True},
        {"path": str(context_brief_path), "source_type": "context_brief", "included": context_brief_path.is_file()},
        {"path": str(update_protocol_path), "source_type": "update_protocol", "included": update_protocol_path.is_file()},
    ]

    hits: list[dict] = []
    hits.extend(
        gather_file_hits(
            path=summary_path,
            source_type="rolling_summary",
            query_terms=query_terms,
            full_query=full_query,
        )
    )
    if context_brief_path.is_file():
        hits.extend(
            gather_file_hits(
                path=context_brief_path,
                source_type="context_brief",
                query_terms=query_terms,
                full_query=full_query,
            )
        )

    if latest_daily_log is not None:
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

    if args.include_daily_logs:
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

    hits = sort_hits(hits)
    hits = hits[: args.limit]
    conflict_state = conflict_state_for_hits(freshness=freshness, hits=hits)

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
    synthesized_recall = render_synthesized_recall(
        query=args.query,
        hits=public_hit_list,
        mode=args.mode,
        conflict_state=conflict_state,
        update_protocol_present=update_protocol_path.is_file(),
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
        )

    estimate = token_estimate(
        attach_scan_text_surface(
            synthesized_recall=synthesized_recall,
            hits=[],
            supporting_window=support_window if args.mode == "detailed" else [],
        )
    )
    payload = {
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "continuity_confidence": freshness["continuity_confidence"],
        "query": args.query,
        "token_estimate": estimate,
        "budget_hint": budget_hint(estimate),
        "output_variant": output_variant_for_mode(args.mode),
        "sources_considered": sources_considered,
        "override_review_targets": (
            [
                {
                    "path": str(update_protocol_path),
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
            "latest_active_daily_log_seen": str(latest_daily_log) if latest_daily_log else None,
            "latest_workspace_artifact_seen": (
                str(freshness["latest_workspace_artifact"])
                if freshness["latest_workspace_artifact"] is not None
                else None
            ),
            "continuity_confidence": freshness["continuity_confidence"],
            "task_type": "query_continuity",
        },
        "source_type": "core_continuity_only",
        "confidence": confidence_for_hits(
            freshness["continuity_confidence"],
            hits,
            conflict_state=conflict_state,
            query_terms=query_terms,
        ),
        "freshness_state": {
            "workspace_artifact_scan_mode": freshness["workspace_artifact_scan_mode"],
            "workspace_artifact_scan_performed": freshness["workspace_artifact_scan_performed"],
            "latest_workspace_artifact": (
                str(freshness["latest_workspace_artifact"])
                if freshness["latest_workspace_artifact"] is not None
                else None
            ),
            "workspace_artifact_newer_than_summary": freshness["workspace_artifact_newer_than_summary"],
            "summary_revision_stale": freshness["summary_revision_stale"],
            "workspace_newer_than_summary": freshness["workspace_newer_than_summary"],
        },
        "conflict_state": conflict_state,
        "attach_scan": attach_scan,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(synthesized_recall)
        if citations:
            print("\nCitations:")
            for citation in citations:
                section = f" [{citation['section']}]" if citation["section"] else ""
                print(f"- {citation['path']}{section}")


if __name__ == "__main__":
    main()
