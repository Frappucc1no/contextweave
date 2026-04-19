#!/usr/bin/env python3
"""Safely append a milestone entry to a RecallLoom daily log."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    atomic_write_if_unchanged,
    ConfigContractError,
    DAILY_LOG_ENTRY_RE,
    DISPLAY_NAME,
    EnvironmentContractError,
    FILE_KEYS,
    LockBusyError,
    StorageResolutionError,
    daily_log_entry_marker,
    dump_json,
    ensure_supported_python_version,
    exit_with_cli_error,
    file_marker,
    find_recallloom_root,
    latest_active_daily_log,
    load_workspace_state,
    missing_section_keys,
    now_iso_timestamp,
    duplicate_section_keys,
    parse_daily_log_entry_line,
    parse_daily_log_scaffold_marker,
    parse_iso_date,
    parse_file_marker,
    read_text,
    restore_text_snapshot,
    SECTION_KEYS,
    unknown_section_keys,
    validate_iso_date,
    validate_writer_id,
    workspace_write_lock,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely append a milestone entry to a RecallLoom daily log."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument("--date", required=True, help="Daily log date in YYYY-MM-DD.")
    parser.add_argument(
        "--allow-historical",
        action="store_true",
        help=(
            "Allow appending to a non-latest ISO-dated daily log. "
            "Without this flag, appends to older daily logs are rejected."
        ),
    )
    parser.add_argument("--entry-file", required=True, help="Path to prepared entry markdown content.")
    parser.add_argument("--expected-workspace-revision", type=int, required=True)
    parser.add_argument("--writer-id", default=DISPLAY_NAME)
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def build_entry_block(body_text: str, *, writer_id: str, entry_seq: int) -> str:
    marker = daily_log_entry_marker(
        entry_id=f"entry-{entry_seq}",
        created_at=now_iso_timestamp(),
        writer_id=writer_id,
        entry_seq=entry_seq,
    )
    body = body_text.strip("\n")
    return marker if not body else marker + "\n\n" + body


def existing_entry_sequences(text: str) -> list[int]:
    sequences: list[int] = []
    for line in text.splitlines():
        entry = parse_daily_log_entry_line(line)
        if entry is not None:
            sequences.append(entry.entry_seq)
    return sequences


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    if not validate_iso_date(args.date):
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Invalid --date value: {args.date}")
    try:
        writer_id = validate_writer_id(args.writer_id)
    except ConfigContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    entry_path = Path(args.entry_file).expanduser().resolve()
    if not entry_path.is_file():
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Entry file does not exist: {entry_path}")

    try:
        workspace = find_recallloom_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No RecallLoom project root found.")

    target_path = workspace.storage_root / "daily_logs" / f"{args.date}.md"
    try:
        with workspace_write_lock(workspace.project_root, "append_daily_log_entry.py"):
            state_path = workspace.storage_root / FILE_KEYS["state"]
            state = load_workspace_state(state_path)
            if state["workspace_revision"] != args.expected_workspace_revision:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=3,
                    message=(
                        f"Workspace revision changed from {args.expected_workspace_revision} to "
                        f"{state['workspace_revision']}. Rerun preflight before appending."
                    ),
                )

            logs_dir = workspace.storage_root / "daily_logs"
            latest_existing = latest_active_daily_log(logs_dir)
            target_date = parse_iso_date(args.date)
            latest_existing_date = parse_iso_date(latest_existing.stem) if latest_existing is not None else None
            if (
                latest_existing_date is not None
                and target_date < latest_existing_date
                and not args.allow_historical
            ):
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Refusing to append to non-latest daily log {target_path}. "
                        f"The latest active ISO-dated daily log is {latest_existing}. "
                        "Re-run with --allow-historical only when you intentionally need a historical append."
                    ),
                )

            body_text = read_text(entry_path)
            missing_keys = missing_section_keys(body_text, SECTION_KEYS["daily_log"])
            if missing_keys:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to append a daily-log entry because the prepared entry file is missing required "
                        "section markers: " + ", ".join(missing_keys)
                    ),
                )
            duplicate_keys = duplicate_section_keys(body_text)
            if duplicate_keys:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to append a daily-log entry because the prepared entry file contains duplicate "
                        "section markers: " + ", ".join(duplicate_keys)
                    ),
                )
            unknown_keys = unknown_section_keys(body_text, SECTION_KEYS["daily_log"])
            if unknown_keys:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to append a daily-log entry because the prepared entry file contains unknown "
                        "section markers: " + ", ".join(unknown_keys)
                    ),
                )
            next_seq = 1
            target_existed = target_path.exists()
            current_text = read_text(target_path) if target_existed else ""
            if target_path.exists():
                marker = parse_file_marker(current_text)
                if marker is None or marker.file_key != "daily_log":
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=f"Target daily log is missing a valid daily_log file marker: {target_path}",
                    )
                scaffold = parse_daily_log_scaffold_marker(current_text)
                sequences = existing_entry_sequences(current_text)
                if scaffold and sequences:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=f"Refusing to append to malformed scaffold daily log {target_path}: scaffold marker cannot coexist with entry markers.",
                    )
                expected_sequences = list(range(1, len(sequences) + 1))
                if sequences != expected_sequences:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            f"Refusing to append to damaged daily log {target_path}. "
                            f"Expected contiguous entry_seq values {expected_sequences}, found {sequences}."
                        ),
                    )
                next_seq = len(sequences) + 1
                if scaffold and not sequences:
                    header = file_marker("daily_log", workspace.workspace_language)
                    updated_text = header + "\n" + build_entry_block(body_text, writer_id=writer_id, entry_seq=next_seq) + "\n"
                else:
                    updated_text = (
                        current_text.rstrip("\n")
                        + "\n\n"
                        + build_entry_block(body_text, writer_id=writer_id, entry_seq=next_seq)
                        + "\n"
                    )
                try:
                    atomic_write_if_unchanged(
                        target_path,
                        expected_text=current_text,
                        new_text=updated_text,
                    )
                except OSError as exc:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=f"Filesystem error while writing {target_path}: {exc}",
                    )
            else:
                header = file_marker("daily_log", workspace.workspace_language)
                updated_text = header + "\n" + build_entry_block(body_text, writer_id=writer_id, entry_seq=next_seq) + "\n"
                try:
                    atomic_write_if_unchanged(
                        target_path,
                        expected_text="",
                        new_text=updated_text,
                    )
                except OSError as exc:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=f"Filesystem error while writing {target_path}: {exc}",
                    )

            state["workspace_revision"] += 1
            target_is_latest_after_write = (
                latest_existing_date is None or target_date >= latest_existing_date
            )
            if target_is_latest_after_write:
                state["daily_logs"]["latest_file"] = str(target_path.relative_to(workspace.storage_root))
                state["daily_logs"]["latest_entry_id"] = f"entry-{next_seq}"
                state["daily_logs"]["latest_entry_seq"] = next_seq
                state["daily_logs"]["entry_count"] = next_seq
            try:
                dump_json(state_path, state)
            except OSError as exc:
                try:
                    restore_text_snapshot(target_path, existed=target_existed, text=current_text)
                except OSError as rollback_exc:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            f"Failed to update state after writing {target_path}: {exc}. "
                            f"Rollback also failed: {rollback_exc}. Workspace may be partially updated."
                        ),
                    )
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Failed to update state after writing {target_path}: {exc}. "
                        "The target file was restored to its previous content."
                    ),
                )
    except LockBusyError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=3, message=str(exc))
    except ConfigContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem error: {exc}")

    payload = {
        "ok": True,
        "target_path": str(target_path),
        "entry_seq": next_seq,
        "new_workspace_revision": state["workspace_revision"],
        "allow_historical": args.allow_historical,
        "state_cursor_updated": target_is_latest_after_write,
        "writer_id": writer_id,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Appended daily log entry to {target_path}")


if __name__ == "__main__":
    main()
