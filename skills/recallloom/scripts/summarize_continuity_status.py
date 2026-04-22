#!/usr/bin/env python3
"""Summarize current continuity status, confidence, and workday recommendation."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from core.continuity.freshness import (
    continuity_state_for_workspace as shared_continuity_state_for_workspace,
    continuity_digest_bundle,
    evaluate_continuity_freshness,
    freshness_risk_summary,
    summary_matches_empty_shell_template as shared_summary_matches_empty_shell_template,
)
from core.protocol.contracts import FILE_KEYS
from core.protocol.markers import parse_file_state_marker
from core.protocol.sections import extract_section_text

from _common import (
    ConfigContractError,
    DAILY_LOGS_DIRNAME,
    detect_update_protocol_time_policy_cues,
    EnvironmentContractError,
    ensure_supported_python_version,
    exit_with_cli_error,
    find_recallloom_root,
    latest_active_daily_log,
    load_workspace_state,
    parse_daily_log_entry_line,
    parse_iso_date,
    read_text,
    StorageResolutionError,
)

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
        description="Summarize continuity confidence, recommended actions, and workday guidance."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument(
        "--timezone",
        help="Optional IANA timezone such as Asia/Shanghai. Defaults to the host local timezone.",
    )
    parser.add_argument(
        "--now",
        help=(
            "Current time in ISO 8601 format. If omitted, the helper uses the host's current local time. "
            "If the value is naive, it is interpreted in --timezone or the host local timezone."
        ),
    )
    parser.add_argument(
        "--rollover-hour",
        type=int,
        default=3,
        help="Logical day rollover hour in 24-hour form. Defaults to 3.",
    )
    parser.add_argument(
        "--preferred-date",
        help="Optional explicit append target date in YYYY-MM-DD form for workday guidance.",
    )
    parser.add_argument(
        "--session-intent",
        choices=[
            "backfill_previous_day_closure",
            "close_previous_day_then_start_new_day",
            "continue_active_day",
            "log_not_needed_for_this_session",
            "review_date_before_append",
            "start_new_active_day",
        ],
        help="Optional explicit session-intent hint using one of the recommendation types.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def resolve_now(now_raw: str | None, timezone_name: str | None) -> tuple[datetime, str]:
    tzinfo = None
    if timezone_name:
        try:
            tzinfo = ZoneInfo(timezone_name)
        except ZoneInfoNotFoundError as exc:
            raise ValueError(f"Unknown timezone: {timezone_name}") from exc

    if now_raw:
        try:
            now = datetime.fromisoformat(now_raw)
        except ValueError as exc:
            raise ValueError(f"Invalid --now value: {now_raw}") from exc
        if now.tzinfo is None:
            if tzinfo is None:
                tzinfo = datetime.now().astimezone().tzinfo
            now = now.replace(tzinfo=tzinfo)
        elif tzinfo is not None:
            now = now.astimezone(tzinfo)
    else:
        now = datetime.now().astimezone()
        if tzinfo is not None:
            now = now.astimezone(tzinfo)

    zone_label = timezone_name or str(now.tzinfo)
    return now, zone_label

def detect_closure_signal(daily_log_text: str) -> tuple[bool, list[str]]:
    closure_keywords = (
        "end-of-day",
        "end of day",
        "day closed",
        "close day",
        "closure recorded",
        "wrapped for the day",
        "收工",
        "收尾",
        "结束今天",
        "今日收尾",
    )
    lowered = daily_log_text.lower()
    matches = [keyword for keyword in closure_keywords if keyword in lowered]
    return (len(matches) > 0, matches)


def latest_daily_log_entry_info(latest_daily_log: Path | None):
    if latest_daily_log is None:
        return None
    latest_entry = None
    for line in read_text(latest_daily_log).splitlines():
        entry = parse_daily_log_entry_line(line)
        if entry is not None:
            latest_entry = entry
    return latest_entry

def recommended_actions_for_status(
    *,
    continuity_confidence: str,
    continuity_state: str,
    update_protocol_exists: bool,
    context_brief_exists: bool,
    latest_daily_log_exists: bool,
    summary_stale: bool,
) -> list[str]:
    actions: list[str] = []
    if continuity_state == "initialized_empty_shell":
        actions.append("seed_initial_continuity")
    elif summary_stale:
        actions.append("update_rolling_summary")
    else:
        actions.append("resume_from_summary")
    if update_protocol_exists:
        actions.append("review_update_protocol")
    if context_brief_exists:
        actions.append("review_context_brief")
    if latest_daily_log_exists:
        actions.append("review_latest_daily_log")
    if (
        continuity_state != "initialized_empty_shell"
        and continuity_confidence == "medium"
        and "update_rolling_summary" not in actions
    ):
        actions.append("consider_refresh_summary")
    return actions


def workday_recommendation(
    *,
    now: datetime,
    rollover_hour: int,
    latest_daily_log: Path | None,
    summary_next_step_is_empty: bool,
    preferred_date_raw: str | None,
    update_protocol_text: str,
    host_explicit: bool,
    session_intent: str | None,
) -> dict:
    latest_active_day = None
    if latest_daily_log is not None:
        latest_active_day = parse_iso_date(latest_daily_log.stem)
    logical_workday = now.date() if now.hour >= rollover_hour else (now.date() - timedelta(days=1))
    project_time_policy_cues = detect_update_protocol_time_policy_cues(update_protocol_text)
    daily_log_text = read_text(latest_daily_log) if latest_daily_log is not None else ""
    closure_detected, closure_keywords = detect_closure_signal(daily_log_text)
    recommendation = "log_not_needed_for_this_session"
    suggested_date = logical_workday.isoformat()
    reasoning: list[str] = []
    if latest_active_day is None:
        recommendation = "start_new_active_day"
        reasoning.append("No active daily log exists yet.")
    elif latest_active_day == logical_workday:
        recommendation = "continue_active_day"
        suggested_date = latest_active_day.isoformat()
        reasoning.append("Latest active day matches the current logical workday.")
    else:
        suggested_date = logical_workday.isoformat()
        if closure_detected:
            recommendation = "start_new_active_day"
            reasoning.append("Latest active day appears closed based on closure language in the daily log.")
        elif not summary_next_step_is_empty:
            recommendation = "close_previous_day_then_start_new_day"
            reasoning.append("Latest active day is behind the current logical workday and the summary still has an unfinished next step.")
        else:
            recommendation = "backfill_previous_day_closure"
            reasoning.append("Latest active day is behind, but no unfinished next step is visible in the rolling summary.")

    heuristic_recommendation = recommendation
    heuristic_suggested_date = suggested_date
    date_resolution_source = "heuristic_default"
    date_sensitive = latest_active_day is None or latest_active_day != logical_workday
    if session_intent is not None:
        recommendation = session_intent
        reasoning.append(
            f"Using the explicit session intent {session_intent} instead of the heuristic recommendation {heuristic_recommendation}."
        )
        if session_intent == "continue_active_day" and latest_active_day is not None:
            suggested_date = latest_active_day.isoformat()
        elif session_intent == "backfill_previous_day_closure" and latest_active_day is not None:
            suggested_date = latest_active_day.isoformat()
        elif session_intent in {"start_new_active_day", "close_previous_day_then_start_new_day"}:
            suggested_date = logical_workday.isoformat()
        date_resolution_source = "user_explicit"
    if preferred_date_raw:
        preferred_date = parse_iso_date(preferred_date_raw).isoformat()
        date_resolution_source = "user_explicit"
        if preferred_date != heuristic_suggested_date:
            recommendation = "review_date_before_append"
            reasoning.append(
                f"Using the explicit preferred date {preferred_date} instead of the heuristic suggestion {heuristic_suggested_date}."
            )
        else:
            reasoning.append(f"Explicit preferred date {preferred_date} matches the heuristic suggestion.")
        suggested_date = preferred_date
    elif project_time_policy_cues and date_sensitive:
        recommendation = "review_date_before_append"
        date_resolution_source = "project_local_review"
        reasoning.append(
            "Project-local time-policy cues were detected in update_protocol.md; review them before applying the heuristic date suggestion."
        )

    if preferred_date_raw:
        decision_priority_applied = "user_explicit"
    elif session_intent is not None:
        decision_priority_applied = "user_explicit"
    elif project_time_policy_cues and date_sensitive:
        decision_priority_applied = "project_local_review"
    elif host_explicit:
        decision_priority_applied = "host_explicit"
    else:
        decision_priority_applied = "host_default"

    return {
        "logical_workday": logical_workday.isoformat(),
        "latest_active_day": latest_active_day.isoformat() if latest_active_day else None,
        "closure_detected": closure_detected,
        "closure_keywords": closure_keywords,
        "session_intent": session_intent,
        "project_time_policy_present": bool(update_protocol_text.strip()),
        "project_time_policy_cues": project_time_policy_cues,
        "project_time_policy_review_required": bool(project_time_policy_cues and date_sensitive),
        "decision_priority_applied": decision_priority_applied,
        "recommendation_type": recommendation,
        "heuristic_recommendation_type": heuristic_recommendation,
        "heuristic_suggested_date": heuristic_suggested_date,
        "preferred_date": preferred_date_raw,
        "date_resolution_source": date_resolution_source,
        "suggested_date": suggested_date,
        "reasoning": reasoning,
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if not 0 <= args.rollover_hour <= 23:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message="Invalid --rollover-hour value.")
    try:
        now, zone_label = resolve_now(args.now, args.timezone)
    except ValueError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if args.preferred_date:
        try:
            parse_iso_date(args.preferred_date)
        except ValueError:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Invalid --preferred-date value: {args.preferred_date}",
                payload={"continuity_confidence": "broken"},
            )

    try:
        workspace = find_recallloom_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload={"continuity_confidence": "broken"},
        )
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No RecallLoom project root found.")

    try:
        summary_path = workspace.storage_root / FILE_KEYS["rolling_summary"]
        if not summary_path.is_file():
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file: {summary_path}",
                payload={"continuity_confidence": "broken"},
            )
        summary_state = parse_file_state_marker(read_text(summary_path))
        if summary_state is None:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file-state metadata marker: {summary_path}",
                payload={"continuity_confidence": "broken"},
            )

        try:
            state = load_workspace_state(workspace.storage_root / FILE_KEYS["state"])
        except ConfigContractError as exc:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=str(exc),
                payload={"continuity_confidence": "broken"},
            )
        context_brief_path = workspace.storage_root / FILE_KEYS["context_brief"]
        update_protocol_path = workspace.storage_root / FILE_KEYS["update_protocol"]
        context_brief_state = None
        if context_brief_path.is_file():
            context_brief_state = parse_file_state_marker(read_text(context_brief_path))
            if context_brief_state is None:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Missing required file-state metadata marker: {context_brief_path}",
                    payload={"continuity_confidence": "broken"},
                )
        update_protocol_state = None
        if update_protocol_path.is_file():
            update_protocol_state = parse_file_state_marker(read_text(update_protocol_path))
            if update_protocol_state is None:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Missing required file-state metadata marker: {update_protocol_path}",
                    payload={"continuity_confidence": "broken"},
                )
        summary_text = read_text(summary_path)
        update_protocol_text = read_text(update_protocol_path) if update_protocol_path.is_file() else ""
        latest_daily_log = latest_active_daily_log(workspace.storage_root / DAILY_LOGS_DIRNAME)
        latest_daily_log_entry = latest_daily_log_entry_info(latest_daily_log)
        latest_daily_log_text = read_text(latest_daily_log) if latest_daily_log is not None else ""
        freshness = evaluate_continuity_freshness(
            project_root=workspace.project_root,
            storage_root=workspace.storage_root,
            summary_path=summary_path,
            workspace_revision=state["workspace_revision"],
            summary_base_workspace_revision=summary_state.base_workspace_revision,
            latest_daily_log_exists=latest_daily_log is not None,
            scan_mode="quick",
        )
        digests = continuity_digest_bundle(
            summary_text=summary_text,
            latest_daily_log_text=latest_daily_log_text,
        )
        continuity_state, continuity_seeded = continuity_state_for_workspace(
            state=state,
            summary_text=summary_text,
            latest_daily_log_exists=latest_daily_log is not None,
        )
        if continuity_state == "initialized_empty_shell":
            digests = {
                "active_task_digest": None,
                "blocked_digest": None,
                "latest_relevant_log_digest": None,
                "suggested_handoff_sections": [],
            }
        summary_stale = freshness["summary_stale"]
        confidence = freshness["continuity_confidence"]
        freshness_risk = freshness_risk_summary(
            workspace_artifact_scan_mode=freshness["workspace_artifact_scan_mode"],
            workspace_artifact_scan_performed=freshness["workspace_artifact_scan_performed"],
            workspace_artifact_newer_than_summary=freshness["workspace_artifact_newer_than_summary"],
            summary_revision_stale=freshness["summary_revision_stale"],
            continuity_confidence=confidence,
        )
        actions = recommended_actions_for_status(
            continuity_confidence=confidence,
            continuity_state=continuity_state,
            update_protocol_exists=update_protocol_path.is_file(),
            context_brief_exists=context_brief_path.is_file(),
            latest_daily_log_exists=latest_daily_log is not None,
            summary_stale=summary_stale,
        )
        workday = workday_recommendation(
            now=now,
            rollover_hour=args.rollover_hour,
            latest_daily_log=latest_daily_log,
            summary_next_step_is_empty=(
                continuity_state == "initialized_empty_shell"
                or digests["active_task_digest"] is None
            ),
            preferred_date_raw=args.preferred_date,
            update_protocol_text=update_protocol_text,
            host_explicit=args.timezone is not None or args.rollover_hour != 3,
            session_intent=args.session_intent,
        )
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Filesystem error: {exc}",
            payload={"continuity_confidence": "broken"},
        )

    payload = {
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "timezone": zone_label,
        "now": now.isoformat(),
        "workspace_revision": state["workspace_revision"],
        "rolling_summary_revision": summary_state.revision,
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
        "summary_stale": summary_stale,
        "continuity_confidence": confidence,
        "freshness_risk_level": freshness_risk["level"],
        "freshness_risk_note": freshness_risk["note"],
        "continuity_state": continuity_state,
        "continuity_seeded": continuity_seeded,
        "active_task_digest": digests["active_task_digest"],
        "blocked_digest": digests["blocked_digest"],
        "latest_relevant_log_digest": digests["latest_relevant_log_digest"],
        "suggested_handoff_sections": digests["suggested_handoff_sections"],
        "recommended_actions": actions,
        "latest_active_daily_log": str(latest_daily_log) if latest_daily_log else None,
        "continuity_snapshot": {
            "project_root": str(workspace.project_root),
            "storage_root": str(workspace.storage_root),
            "workspace_revision_seen": state["workspace_revision"],
            "rolling_summary_revision_seen": summary_state.revision,
            "context_brief_revision_seen": context_brief_state.revision if context_brief_state else None,
            "update_protocol_revision_seen": update_protocol_state.revision if update_protocol_state else None,
            "latest_active_daily_log_seen": str(latest_daily_log) if latest_daily_log else None,
            "latest_active_daily_log_entry_seq_seen": (
                latest_daily_log_entry.entry_seq if latest_daily_log_entry is not None else None
            ),
            "logical_workday_seen": workday["logical_workday"],
            "continuity_confidence": confidence,
            "continuity_state": continuity_state,
            "continuity_seeded": continuity_seeded,
            "task_type": "status_review",
        },
        "workday": workday,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"RecallLoom root: {workspace.project_root}")
        print(f"Continuity confidence: {confidence}")
        if freshness_risk["note"]:
            print(f"Freshness risk: {freshness_risk['level']} - {freshness_risk['note']}")
        print(f"Continuity state: {continuity_state}")
        print("Recommended actions:")
        for action in actions:
            print(f"  - {action}")
        print(f"Workday recommendation: {workday['recommendation_type']}")
        print(f"Suggested date: {workday['suggested_date']}")


if __name__ == "__main__":
    main()
