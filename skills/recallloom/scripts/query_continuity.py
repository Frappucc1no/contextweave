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
    read_text,
    scan_auto_attached_context_text,
    section_keys_in_text,
    sorted_daily_log_files,
    StorageResolutionError,
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
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def tokenize_query(query: str) -> list[str]:
    return [token.casefold() for token in re.findall(r"[A-Za-z0-9_/-]+", query) if len(token) >= 2]


def score_text(text: str, query_terms: list[str]) -> int:
    lowered = text.casefold()
    return sum(lowered.count(term) for term in query_terms)


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
) -> list[dict]:
    text = read_text(path)
    hits: list[dict] = []
    keys = section_keys_in_text(text)
    if not keys:
        score = score_text(text, query_terms)
        if score > 0:
            hits.append(
                {
                    "path": str(path),
                    "section": None,
                    "score": score,
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
        hits.append(
            {
                "path": str(path),
                "section": key,
                "score": score,
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
    return [
        {
            "path": item["path"],
            "section": item["section"],
            "source_type": item["source_type"],
            "excerpt": item["excerpt"],
            "score": item["score"],
        }
        for item in hits
    ]


def token_estimate(text: str) -> int:
    words = len(re.findall(r"\S+", text))
    return max(1, round(words / 0.75))


def budget_hint(estimate: int) -> str:
    if estimate <= 120:
        return "small"
    if estimate <= 300:
        return "medium"
    return "large"


def confidence_for_hits(continuity_confidence: str, hits: list[dict]) -> str:
    if not hits:
        return "low"
    if continuity_confidence == "high" and hits[0]["score"] >= 2:
        return "high"
    if continuity_confidence == "broken":
        return "low"
    return "medium"


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
            scan_mode="quick",
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
    hits.extend(gather_file_hits(path=summary_path, source_type="rolling_summary", query_terms=query_terms))
    if context_brief_path.is_file():
        hits.extend(gather_file_hits(path=context_brief_path, source_type="context_brief", query_terms=query_terms))

    if latest_daily_log is not None:
        sources_considered.append(
            {"path": str(latest_daily_log), "source_type": "latest_daily_log", "included": True}
        )
        hits.extend(gather_file_hits(path=latest_daily_log, source_type="latest_daily_log", query_terms=query_terms))

    if args.include_daily_logs:
        recent_logs = sorted_daily_log_files(logs_dir)[-3:]
        for log_path in recent_logs:
            if latest_daily_log is not None and log_path == latest_daily_log:
                continue
            sources_considered.append(
                {"path": str(log_path), "source_type": "recent_daily_log", "included": True}
            )
            hits.extend(gather_file_hits(path=log_path, source_type="recent_daily_log", query_terms=query_terms))

    hits.sort(key=lambda item: (-item["score"], item["path"], item["section"] or ""))
    hits = hits[: args.limit]

    citations = [
        {
            "path": item["path"],
            "section": item["section"],
            "source_type": item["source_type"],
        }
        for item in hits
    ]

    synthesized_lines = [f"Query: {args.query}", ""]
    if not hits:
        synthesized_lines.append("No strong continuity hits were found in the current core continuity files.")
    else:
        synthesized_lines.append("Relevant continuity recall:")
        for item in hits:
            section_label = f" [{item['section']}]" if item["section"] else ""
            synthesized_lines.append(f"- {Path(item['path']).name}{section_label}: {item['excerpt']}")
    synthesized_recall = "\n".join(synthesized_lines).strip()

    attach_scan = scan_auto_attached_context_text(synthesized_recall)
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

    estimate = token_estimate(synthesized_recall)
    payload = {
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "continuity_confidence": freshness["continuity_confidence"],
        "query": args.query,
        "token_estimate": estimate,
        "budget_hint": budget_hint(estimate),
        "sources_considered": sources_considered,
        "hits": hits,
        "synthesized_recall": synthesized_recall,
        "citations": citations,
        "supporting_context_window": supporting_context_window(hits, mode=args.mode),
        "continuity_snapshot": {
            "workspace_revision_seen": state["workspace_revision"],
            "rolling_summary_revision_seen": summary_state.revision,
            "latest_active_daily_log_seen": str(latest_daily_log) if latest_daily_log else None,
            "continuity_confidence": freshness["continuity_confidence"],
            "task_type": "query_continuity",
        },
        "source_type": "core_continuity_only",
        "confidence": confidence_for_hits(freshness["continuity_confidence"], hits),
        "freshness_state": {
            "workspace_artifact_scan_mode": freshness["workspace_artifact_scan_mode"],
            "workspace_artifact_scan_performed": freshness["workspace_artifact_scan_performed"],
            "workspace_artifact_newer_than_summary": freshness["workspace_artifact_newer_than_summary"],
            "summary_revision_stale": freshness["summary_revision_stale"],
            "workspace_newer_than_summary": freshness["workspace_newer_than_summary"],
        },
        "conflict_state": "potentially_stale" if freshness["workspace_newer_than_summary"] else "none",
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
