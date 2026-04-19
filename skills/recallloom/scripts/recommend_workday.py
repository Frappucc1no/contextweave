#!/usr/bin/env python3
"""Recommend the current logical workday and append target date for RecallLoom."""

from __future__ import annotations

import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from _common import (
    ConfigContractError,
    detect_update_protocol_time_policy_cues,
    EnvironmentContractError,
    ensure_supported_python_version,
    exit_with_cli_error,
    FILE_KEYS,
    find_recallloom_root,
    latest_active_daily_log,
    parse_iso_date,
    read_text,
    StorageResolutionError,
)


RECOMMENDATION_TYPES = {
    "continue_active_day",
    "start_new_active_day",
    "close_previous_day_then_start_new_day",
    "backfill_previous_day_closure",
    "log_not_needed_for_this_session",
    "review_date_before_append",
}

CLOSURE_KEYWORDS = (
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Recommend the logical workday and append target date for a RecallLoom workspace."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument(
        "--now",
        help=(
            "Current time in ISO 8601 format. If omitted, the helper uses the host's current local time. "
            "If the value is naive, it is interpreted in --timezone or the host local timezone."
        ),
    )
    parser.add_argument(
        "--timezone",
        help="Optional IANA timezone such as Asia/Shanghai. Defaults to the host local timezone.",
    )
    parser.add_argument(
        "--rollover-hour",
        type=int,
        default=3,
        help="Logical day rollover hour in 24-hour form. Defaults to 3.",
    )
    parser.add_argument(
        "--preferred-date",
        help=(
            "Optional explicit append target date in YYYY-MM-DD form. "
            "When provided, this date takes priority over the helper's default suggestion. "
            "If it disagrees with the heuristic result, the helper returns "
            "`review_date_before_append`."
        ),
    )
    parser.add_argument(
        "--session-intent",
        choices=sorted(RECOMMENDATION_TYPES),
        help=(
            "Optional explicit session-intent hint using one of the recommendation types. "
            "When provided, this takes priority over heuristic recommendation selection."
        ),
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


def is_effectively_empty_summary_next_step(text: str) -> bool:
    cleaned = []
    for line in text.splitlines():
        candidate = line.strip()
        if not candidate:
            continue
        if candidate.startswith("#"):
            continue
        if candidate in {"-", "*"}:
            continue
        cleaned.append(candidate.lstrip("-* ").strip())
    if not cleaned:
        return True
    lowered = " ".join(cleaned).strip().lower()
    return lowered in {"none", "n/a", "na", "no next step"}


def detect_closure_signal(daily_log_text: str) -> tuple[bool, list[str]]:
    lowered = daily_log_text.lower()
    matches = [keyword for keyword in CLOSURE_KEYWORDS if keyword in lowered]
    return (len(matches) > 0, matches)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    if not 0 <= args.rollover_hour <= 23:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Invalid --rollover-hour value: {args.rollover_hour}. Expected 0..23.",
        )
    preferred_date = None
    if args.preferred_date:
        try:
            preferred_date = parse_iso_date(args.preferred_date)
        except ValueError:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Invalid --preferred-date value: {args.preferred_date}",
            )

    try:
        now, zone_label = resolve_now(args.now, args.timezone)
    except ValueError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    try:
        workspace = find_recallloom_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No RecallLoom project root found.")

    try:
        latest_daily_log = latest_active_daily_log(workspace.storage_root / "daily_logs")
        latest_active_day = parse_iso_date(latest_daily_log.stem) if latest_daily_log is not None else None
        logical_workday = now.date() if now.hour >= args.rollover_hour else (now.date() - timedelta(days=1))
        update_protocol_path = workspace.storage_root / FILE_KEYS["update_protocol"]
        update_protocol_text = read_text(update_protocol_path) if update_protocol_path.is_file() else ""
        project_time_policy_cues = detect_update_protocol_time_policy_cues(update_protocol_text)

        summary_path = workspace.storage_root / "rolling_summary.md"
        summary_text = read_text(summary_path) if summary_path.is_file() else ""
        next_step_text = extract_section_text(summary_text, "next_step")
        next_step_empty = is_effectively_empty_summary_next_step(next_step_text)

        daily_log_text = read_text(latest_daily_log) if latest_daily_log is not None else ""
        closure_detected, closure_keywords = detect_closure_signal(daily_log_text)
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem error: {exc}")

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
        elif not next_step_empty:
            recommendation = "close_previous_day_then_start_new_day"
            reasoning.append("Latest active day is behind the current logical workday and the summary still has an unfinished next step.")
        else:
            recommendation = "backfill_previous_day_closure"
            reasoning.append("Latest active day is behind, but no unfinished next step is visible in the rolling summary.")

    if recommendation not in RECOMMENDATION_TYPES:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Internal error: unsupported recommendation type '{recommendation}'.",
        )

    heuristic_recommendation = recommendation
    heuristic_suggested_date = suggested_date
    date_resolution_source = "heuristic_default"
    host_explicit = args.timezone is not None or args.rollover_hour != 3
    date_sensitive = latest_active_day is None or latest_active_day != logical_workday

    if args.session_intent is not None:
        recommendation = args.session_intent
        reasoning.append(
            f"Using the explicit session intent {args.session_intent} instead of the heuristic recommendation {heuristic_recommendation}."
        )
        if args.session_intent == "continue_active_day" and latest_active_day is not None:
            suggested_date = latest_active_day.isoformat()
        elif args.session_intent == "backfill_previous_day_closure" and latest_active_day is not None:
            suggested_date = latest_active_day.isoformat()
        elif args.session_intent in {"start_new_active_day", "close_previous_day_then_start_new_day"}:
            suggested_date = logical_workday.isoformat()
        date_resolution_source = "user_explicit"

    if preferred_date is not None:
        preferred_date_iso = preferred_date.isoformat()
        date_resolution_source = "user_explicit"
        if preferred_date_iso != heuristic_suggested_date:
            recommendation = "review_date_before_append"
            reasoning.append(
                "Using the explicit preferred date "
                f"{preferred_date_iso} instead of the heuristic suggestion {heuristic_suggested_date}."
            )
        else:
            reasoning.append(
                f"Explicit preferred date {preferred_date_iso} matches the heuristic suggestion."
            )
        suggested_date = preferred_date_iso
    elif project_time_policy_cues and date_sensitive:
        recommendation = "review_date_before_append"
        date_resolution_source = "project_local_review"
        reasoning.append(
            "Project-local time-policy cues were detected in update_protocol.md; review them before applying the heuristic date suggestion."
        )

    if preferred_date is not None:
        decision_priority_applied = "user_explicit"
    elif args.session_intent is not None:
        decision_priority_applied = "user_explicit"
    elif project_time_policy_cues and date_sensitive:
        decision_priority_applied = "project_local_review"
    elif host_explicit:
        decision_priority_applied = "host_explicit"
    else:
        decision_priority_applied = "host_default"

    payload = {
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "timezone": zone_label,
        "now": now.isoformat(),
        "physical_date": now.date().isoformat(),
        "rollover_hour": args.rollover_hour,
        "logical_workday": logical_workday.isoformat(),
        "latest_active_daily_log": str(latest_daily_log) if latest_daily_log else None,
        "latest_active_day": latest_active_day.isoformat() if latest_active_day else None,
        "summary_next_step_empty": next_step_empty,
        "summary_next_step_excerpt": None if next_step_empty else next_step_text,
        "closure_detected": closure_detected,
        "closure_keywords": closure_keywords,
        "session_intent": args.session_intent,
        "preferred_date": preferred_date.isoformat() if preferred_date is not None else None,
        "date_resolution_source": date_resolution_source,
        "decision_priority_applied": decision_priority_applied,
        "project_time_policy_present": update_protocol_path.is_file(),
        "project_time_policy_cues": project_time_policy_cues,
        "project_time_policy_review_required": bool(project_time_policy_cues and date_sensitive),
        "heuristic_recommendation_type": heuristic_recommendation,
        "heuristic_suggested_date": heuristic_suggested_date,
        "recommendation_type": recommendation,
        "suggested_date": suggested_date,
        "reasoning": reasoning,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return

    print(f"RecallLoom root: {workspace.project_root}")
    print(f"Timezone: {zone_label}")
    print(f"Current time: {now.isoformat()}")
    print(f"Logical workday: {logical_workday.isoformat()}")
    print(f"Latest active daily log: {latest_daily_log if latest_daily_log else 'none'}")
    if preferred_date is not None:
        print(f"Preferred date: {preferred_date.isoformat()}")
    print(f"Date resolution source: {date_resolution_source}")
    print(f"Recommendation: {recommendation}")
    print(f"Suggested date: {suggested_date}")
    if reasoning:
        print("Why:")
        for item in reasoning:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
