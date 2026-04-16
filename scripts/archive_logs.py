#!/usr/bin/env python3
"""Archive old ContextWeave daily logs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import shutil

from _common import (
    ConfigContractError,
    daily_log_entries,
    daily_log_sequence_error,
    EnvironmentContractError,
    exit_with_cli_error,
    LockBusyError,
    rollback_moved_files,
    StorageResolutionError,
    dump_json,
    ensure_supported_python_version,
    find_contextweave_root,
    invalid_iso_like_daily_log_files,
    load_workspace_state,
    now_iso_timestamp,
    parse_iso_date,
    sorted_active_daily_log_files,
    sorted_daily_log_files,
    workspace_write_lock,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Archive old ContextWeave daily logs.")
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument(
        "--max-active",
        type=int,
        default=None,
        help="Maximum number of active daily logs to keep before archiving older ones.",
    )
    parser.add_argument(
        "--before",
        help="Archive logs older than this ISO date (YYYY-MM-DD).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Perform the archive move. Without this flag, the script only reports what would be archived.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    try:
        workspace = find_contextweave_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No ContextWeave project root found.")

    try:
        with workspace_write_lock(workspace.project_root, "archive_logs.py"):
            logs_dir = workspace.storage_root / "daily_logs"
            archive_dir = logs_dir / "archive"
            update_protocol_path = workspace.storage_root / "update_protocol.md"
            state_path = workspace.storage_root / "state.json"
            try:
                state = load_workspace_state(state_path)
            except ConfigContractError as exc:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=str(exc),
                )
            invalid_daily_logs = invalid_iso_like_daily_log_files(logs_dir)
            if invalid_daily_logs:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to archive because one or more daily log filenames match the date pattern but are invalid ISO dates:\n"
                        + "\n".join(str(path) for path in invalid_daily_logs)
                    ),
                )
            candidates = sorted_daily_log_files(logs_dir)

            to_archive: set[Path] = set()
            effective_max_active = args.max_active if args.max_active is not None else (10 if not args.before else None)

            if args.before:
                try:
                    cutoff = parse_iso_date(args.before)
                except ValueError:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=f"Invalid --before date: {args.before}",
                    )
                for path in candidates:
                    if parse_iso_date(path.stem) < cutoff:
                        to_archive.add(path)

            if effective_max_active is not None and effective_max_active < 0:
                exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message="--max-active must be >= 0")

            if effective_max_active is not None and len(candidates) > effective_max_active:
                excess = len(candidates) - effective_max_active
                to_archive.update(candidates[:excess])

            ordered = sorted(to_archive, key=lambda path: path.stem)
            archived_targets: list[str] = []

            target_map = [(source, archive_dir / source.name) for source in ordered]
            existing_targets = [str(target) for _, target in target_map if target.exists()]
            if existing_targets:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=3,
                    message=(
                        "Refusing to archive because one or more archive targets already exist:\n"
                        + "\n".join(existing_targets)
                    ),
                )

            remaining_after_archive = [path for path in candidates if path not in to_archive]
            remaining_active = [path for path in sorted_active_daily_log_files(logs_dir) if path not in to_archive]
            latest_remaining = remaining_active[-1] if remaining_active else None
            latest_entry_id = None
            latest_entry_seq = 0
            entry_count = 0
            if latest_remaining is not None:
                latest_text = latest_remaining.read_text(encoding="utf-8")
                latest_entries = daily_log_entries(latest_text)
                sequence_error = daily_log_sequence_error(latest_entries)
                if sequence_error is not None:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            "Refusing to archive because the newest remaining daily log is damaged: "
                            f"{latest_remaining}. {sequence_error}"
                        ),
                    )
                latest_entry = latest_entries[-1]
                latest_entry_id = latest_entry.entry_id
                latest_entry_seq = latest_entry.entry_seq
                entry_count = len(latest_entries)

            previous_daily_state = state.get("daily_logs", {})
            next_latest_file = (
                str(latest_remaining.relative_to(workspace.storage_root)) if latest_remaining else None
            )
            cursor_changed = (
                previous_daily_state.get("latest_file") != next_latest_file
                or previous_daily_state.get("latest_entry_id") != latest_entry_id
                or previous_daily_state.get("latest_entry_seq") != latest_entry_seq
                or previous_daily_state.get("entry_count") != entry_count
            )

            if ordered and args.yes:
                archive_dir.mkdir(parents=True, exist_ok=True)
                applied_moves: list[tuple[Path, Path]] = []
                for source, target in target_map:
                    try:
                        shutil.move(str(source), str(target))
                    except OSError as exc:
                        if applied_moves:
                            try:
                                rollback_moved_files(applied_moves)
                            except OSError as rollback_exc:
                                exit_with_cli_error(
                                    parser,
                                    json_mode=args.json,
                                    exit_code=2,
                                    message=(
                                        f"Filesystem error while archiving {source} to {target}: {exc}. "
                                        f"Rollback also failed: {rollback_exc}. Workspace may be partially updated."
                                    ),
                                )
                        exit_with_cli_error(
                            parser,
                            json_mode=args.json,
                            exit_code=2,
                            message=(
                                f"Filesystem error while archiving {source} to {target}: {exc}. "
                                "Any earlier moved daily logs were restored to their original locations."
                            ),
                        )
                    applied_moves.append((source, target))
                    archived_targets.append(str(target))
                if cursor_changed:
                    state["workspace_revision"] += 1
                state["daily_logs"]["latest_file"] = next_latest_file
                state["daily_logs"]["latest_entry_id"] = latest_entry_id
                state["daily_logs"]["latest_entry_seq"] = latest_entry_seq
                state["daily_logs"]["entry_count"] = entry_count
                state["daily_logs"]["updated_at"] = now_iso_timestamp()
                try:
                    dump_json(state_path, state)
                except OSError as exc:
                    try:
                        rollback_moved_files(applied_moves)
                    except OSError as rollback_exc:
                        exit_with_cli_error(
                            parser,
                            json_mode=args.json,
                            exit_code=2,
                            message=(
                                f"Failed to update state after archiving daily logs: {exc}. "
                                f"Rollback also failed: {rollback_exc}. Workspace may be partially updated."
                            ),
                        )
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            f"Failed to update state after archiving daily logs: {exc}. "
                            "Moved daily logs were restored to their original locations."
                        ),
                    )
            else:
                archived_targets = [str(target) for _, target in target_map]

            payload = {
                "project_root": str(workspace.project_root),
                "storage_root": str(workspace.storage_root),
                "storage_mode": workspace.storage_mode,
                "dry_run": not args.yes,
                "effective_max_active": effective_max_active,
                "update_protocol": str(update_protocol_path) if update_protocol_path.is_file() else None,
                "override_review_required": update_protocol_path.is_file(),
                "archived_count": len(ordered),
                "archived_targets": archived_targets,
                "workspace_revision_bumped": bool(ordered and args.yes and cursor_changed),
            }
    except LockBusyError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=3, message=str(exc))
    except ConfigContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem error: {exc}")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        action = "Would archive" if not args.yes else "Archived"
        print(f"{action} {len(ordered)} daily log(s).")
        if update_protocol_path.is_file():
            print(
                "Project-local override review required: "
                f"{update_protocol_path} may narrow archive behavior. "
                "v1 helpers do not parse natural-language override prose automatically."
            )
        for item in archived_targets:
            print(f"  - {item}")


if __name__ == "__main__":
    main()
