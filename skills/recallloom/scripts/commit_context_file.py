#!/usr/bin/env python3
"""Safely commit a prepared RecallLoom managed file with revision checks."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    ConfigContractError,
    DISPLAY_NAME,
    EnvironmentContractError,
    FILE_KEYS,
    LockBusyError,
    OPTIONAL_SECTION_KEYS,
    SECTION_KEYS,
    StorageResolutionError,
    atomic_write_if_unchanged,
    duplicate_section_keys,
    dump_json,
    ensure_supported_python_version,
    exit_with_cli_error,
    file_marker,
    file_state_marker,
    find_recallloom_root,
    load_workspace_state,
    missing_section_keys,
    now_iso_timestamp,
    parse_file_marker,
    parse_file_state_marker,
    read_text,
    restore_text_snapshot,
    rolling_summary_header,
    today_iso,
    unknown_section_keys,
    validate_tool_name,
    validate_writer_id,
    workspace_write_lock,
)


WRITABLE_FILE_KEYS = {"context_brief", "rolling_summary", "update_protocol"}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely commit a prepared RecallLoom managed file with revision checks."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument("--file-key", required=True, choices=sorted(WRITABLE_FILE_KEYS))
    parser.add_argument("--source-file", required=True, help="Path to prepared markdown content.")
    parser.add_argument("--expected-file-revision", type=int, required=True)
    parser.add_argument("--expected-workspace-revision", type=int, required=True)
    parser.add_argument("--writer-id", default=DISPLAY_NAME)
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def strip_managed_headers(file_key: str, text: str) -> str:
    lines = text.splitlines()
    stripped: list[str] = []
    for idx, line in enumerate(lines):
        candidate = line.strip()
        if idx == 0 and candidate.startswith("<!-- recallloom:file="):
            continue
        if file_key == "rolling_summary" and idx == 1 and candidate.startswith("<!-- last-writer:"):
            continue
        if candidate.startswith("<!-- file-state:"):
            continue
        stripped.append(line)
    return "\n".join(stripped).lstrip("\n")


def build_managed_text(
    *,
    file_key: str,
    body_text: str,
    language: str,
    writer_id: str,
    file_revision: int,
    base_workspace_revision: int,
    timestamp: str,
) -> str:
    parts = [file_marker(file_key, language)]
    if file_key == "rolling_summary":
        parts.append(rolling_summary_header(writer_id, today_iso()))
    parts.append(
        file_state_marker(
            revision=file_revision,
            updated_at=timestamp,
            writer_id=writer_id,
            base_workspace_revision=base_workspace_revision,
        )
    )
    body = body_text.rstrip("\n")
    if body:
        parts.extend(["", body])
    return "\n".join(parts) + "\n"


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    source_path = Path(args.source_file).expanduser().resolve()
    if not source_path.is_file():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Source file does not exist: {source_path}",
        )

    try:
        workspace = find_recallloom_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No RecallLoom project root found.")

    target_path = workspace.storage_root / FILE_KEYS[args.file_key]
    if not target_path.is_file():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Missing target file: {target_path}",
        )

    try:
        with workspace_write_lock(workspace.project_root, "commit_context_file.py"):
            try:
                writer_id = (
                    validate_tool_name(args.writer_id)
                    if args.file_key == "rolling_summary"
                    else validate_writer_id(args.writer_id)
                )
            except ConfigContractError as exc:
                exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

            state_path = workspace.storage_root / FILE_KEYS["state"]
            state = load_workspace_state(state_path)
            if state["workspace_revision"] != args.expected_workspace_revision:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=3,
                    message=(
                        f"Workspace revision changed from {args.expected_workspace_revision} to "
                        f"{state['workspace_revision']}. Rerun preflight before writing."
                    ),
                )

            current_text = read_text(target_path)
            current_marker = parse_file_marker(current_text)
            if current_marker is None:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Target file is missing a valid file marker: {target_path}",
                )
            if current_marker.file_key != args.file_key:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Target file marker '{current_marker.file_key}' does not match requested file key "
                        f"'{args.file_key}'. Repair the target file before committing."
                    ),
                )
            if current_marker.language != workspace.workspace_language:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Target file language marker '{current_marker.language}' does not match workspace_language "
                        f"'{workspace.workspace_language}'. Repair the target file before committing."
                    ),
                )
            current_state = parse_file_state_marker(current_text)
            if current_state is None:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Target file is missing a valid file-state marker: {target_path}",
                )
            if current_state.revision != args.expected_file_revision:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=3,
                    message=(
                        f"File revision changed from {args.expected_file_revision} to "
                        f"{current_state.revision}. Reread the file before writing."
                    ),
                )

            source_text = read_text(source_path)
            source_marker = parse_file_marker(source_text)
            if source_marker is not None and source_marker.file_key != args.file_key:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Source file marker '{source_marker.file_key}' does not match requested file key '{args.file_key}'."
                    ),
                )

            timestamp = now_iso_timestamp()
            new_file_revision = current_state.revision + 1
            new_workspace_revision = state["workspace_revision"] + 1
            body_text = strip_managed_headers(args.file_key, source_text)
            missing_keys = missing_section_keys(body_text, SECTION_KEYS[args.file_key])
            if missing_keys:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to commit because the prepared file is missing required section markers: "
                        + ", ".join(missing_keys)
                    ),
                )
            duplicate_keys = duplicate_section_keys(body_text)
            if duplicate_keys:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to commit because the prepared file contains duplicate section markers: "
                        + ", ".join(duplicate_keys)
                    ),
                )
            unknown_keys = unknown_section_keys(
                body_text,
                [*SECTION_KEYS[args.file_key], *OPTIONAL_SECTION_KEYS.get(args.file_key, [])],
            )
            if unknown_keys:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to commit because the prepared file contains unknown section markers: "
                        + ", ".join(unknown_keys)
                    ),
                )
            new_text = build_managed_text(
                file_key=args.file_key,
                body_text=body_text,
                language=workspace.workspace_language,
                writer_id=writer_id,
                file_revision=new_file_revision,
                base_workspace_revision=new_workspace_revision,
                timestamp=timestamp,
            )
            try:
                atomic_write_if_unchanged(target_path, expected_text=current_text, new_text=new_text)
            except OSError as exc:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Filesystem error while writing {target_path}: {exc}",
                )

            state["workspace_revision"] = new_workspace_revision
            state["files"][args.file_key] = {
                "file_revision": new_file_revision,
                "updated_at": timestamp,
                "writer_id": writer_id,
                "base_workspace_revision": new_workspace_revision,
            }
            if args.file_key == "update_protocol":
                state["update_protocol_revision"] = new_file_revision
            try:
                dump_json(state_path, state)
            except OSError as exc:
                try:
                    restore_text_snapshot(target_path, existed=True, text=current_text)
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
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "file_key": args.file_key,
        "target_path": str(target_path),
        "new_file_revision": new_file_revision,
        "new_workspace_revision": new_workspace_revision,
        "writer_id": writer_id,
        "ok": True,
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Committed {args.file_key} to {target_path}")


if __name__ == "__main__":
    main()
