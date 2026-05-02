#!/usr/bin/env python3
"""Safely commit a prepared RecallLoom managed file with revision checks."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import select
import sys
import time

from core.failure.contracts import failure_payload, preferred_failure_language
from core.protocol.contracts import FILE_KEYS, OPTIONAL_SECTION_KEYS, SECTION_KEYS
from core.protocol.markers import (
    file_marker,
    file_state_marker,
    parse_file_marker,
    parse_file_state_marker,
    rolling_summary_header,
)
from core.protocol.sections import (
    duplicate_section_keys,
    missing_section_keys,
    unknown_section_keys,
)
from core.safety.attached_text import scan_auto_attached_context_text

from _common import (
    cli_failure_payload,
    cli_failure_payload_for_exception,
    ConfigContractError,
    DISPLAY_NAME,
    EnvironmentContractError,
    LockBusyError,
    StorageResolutionError,
    atomic_write_if_unchanged,
    dump_json,
    enforce_package_support_gate,
    ensure_supported_python_version,
    exit_with_cli_error,
    exit_with_failure_contract,
    find_recallloom_root,
    load_workspace_state,
    now_iso_timestamp,
    read_text,
    restore_text_snapshot,
    today_iso,
    validate_tool_name,
    validate_writer_id,
    workspace_write_lock,
)


WRITABLE_FILE_KEYS = {"context_brief", "rolling_summary", "update_protocol"}
DEFAULT_MAX_INPUT_BYTES = 4 * 1024 * 1024
STDIN_READ_CHUNK_BYTES = 64 * 1024
STDIN_READ_TIMEOUT_SECONDS = 30
RESERVED_MARKER_PREFIXES = (
    "<!-- recallloom:file=",
    "<!-- last-writer:",
    "<!-- file-state:",
    "<!-- daily-log-entry:",
    "<!-- daily-log-scaffold",
)


def positive_int(value: str) -> int:
    try:
        parsed = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("--max-input-bytes must be an integer.") from exc
    if parsed <= 0:
        raise argparse.ArgumentTypeError("--max-input-bytes must be greater than zero.")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely commit a prepared RecallLoom managed file with revision checks."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument("--file-key", required=True, choices=sorted(WRITABLE_FILE_KEYS))
    parser.add_argument("--source-file", help="Path to prepared markdown content.")
    parser.add_argument(
        "--stdin",
        action="store_true",
        help="Read prepared markdown content from UTF-8 stdin instead of a file.",
    )
    parser.add_argument(
        "--max-input-bytes",
        type=positive_int,
        default=DEFAULT_MAX_INPUT_BYTES,
        help="Maximum prepared-content input size in bytes. Defaults to 4 MiB.",
    )
    parser.add_argument("--expected-file-revision", type=int, required=True)
    parser.add_argument("--expected-workspace-revision", type=int, required=True)
    parser.add_argument("--writer-id", default=DISPLAY_NAME)
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def read_limited_file_text(parser, *, json_mode: bool, source_path: Path, max_input_bytes: int) -> str:
    try:
        size = source_path.stat().st_size
    except OSError as exc:
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message=f"Failed to inspect source file: {exc}",
            reason="invalid_prepared_input",
        )
    if size > max_input_bytes:
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message=f"Source file exceeds --max-input-bytes ({size} > {max_input_bytes}): {source_path}",
            reason="invalid_prepared_input",
            details={"size": size, "max_input_bytes": max_input_bytes, "source_path": str(source_path)},
        )
    try:
        return read_text(source_path)
    except UnicodeDecodeError:
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message=f"Source file must be valid UTF-8: {source_path}",
            reason="invalid_prepared_input",
            details={"source_path": str(source_path)},
        )
    except OSError as exc:
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message=f"Failed to read source file: {exc}",
            reason="invalid_prepared_input",
        )
    raise AssertionError("unreachable")


def read_limited_stdin(parser, *, json_mode: bool, max_input_bytes: int) -> bytes:
    chunks: list[bytes] = []
    total = 0
    deadline = time.monotonic() + STDIN_READ_TIMEOUT_SECONDS
    fd = sys.stdin.buffer.fileno()

    while True:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            exit_with_failure_contract(
                parser,
                json_mode=json_mode,
                exit_code=2,
                message=f"Timed out while reading stdin after {STDIN_READ_TIMEOUT_SECONDS} seconds.",
                reason="invalid_prepared_input",
            )
        try:
            ready, _, _ = select.select([fd], [], [], remaining)
        except (OSError, ValueError) as exc:
            exit_with_failure_contract(
                parser,
                json_mode=json_mode,
                exit_code=2,
                message=f"Failed to poll stdin: {exc}",
                reason="invalid_prepared_input",
            )
        if not ready:
            exit_with_failure_contract(
                parser,
                json_mode=json_mode,
                exit_code=2,
                message=f"Timed out while reading stdin after {STDIN_READ_TIMEOUT_SECONDS} seconds.",
                reason="invalid_prepared_input",
            )
        try:
            chunk = os.read(fd, STDIN_READ_CHUNK_BYTES)
        except OSError as exc:
            exit_with_failure_contract(
                parser,
                json_mode=json_mode,
                exit_code=2,
                message=f"Failed to read stdin: {exc}",
                reason="invalid_prepared_input",
            )
        if chunk == b"":
            break
        chunks.append(chunk)
        total += len(chunk)
        if total > max_input_bytes:
            exit_with_failure_contract(
                parser,
                json_mode=json_mode,
                exit_code=2,
                message=f"Stdin input exceeds --max-input-bytes ({total} > {max_input_bytes}).",
                reason="invalid_prepared_input",
                details={"size": total, "max_input_bytes": max_input_bytes},
            )
    return b"".join(chunks)


def load_prepared_text(
    parser,
    *,
    json_mode: bool,
    source_file: str | None,
    use_stdin: bool,
    max_input_bytes: int,
) -> tuple[str, str]:
    if bool(source_file) == bool(use_stdin):
        if source_file and use_stdin:
            exit_with_failure_contract(
                parser,
                json_mode=json_mode,
                exit_code=2,
                message="Use exactly one prepared-content input: --source-file or --stdin.",
                reason="invalid_prepared_input",
            )
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message="Provide prepared content with --source-file or --stdin.",
            reason="invalid_prepared_input",
        )

    if source_file:
        source_path = Path(source_file).expanduser().resolve()
        if not source_path.is_file():
            exit_with_failure_contract(
                parser,
                json_mode=json_mode,
                exit_code=2,
                message=f"Source file does not exist: {source_path}",
                reason="invalid_prepared_input",
                details={"source_path": str(source_path)},
            )
        return (
            read_limited_file_text(
                parser,
                json_mode=json_mode,
                source_path=source_path,
                max_input_bytes=max_input_bytes,
            ),
            "file",
        )

    if sys.stdin.isatty():
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message="Stdin input is empty. Pipe or redirect UTF-8 prepared content when using --stdin.",
            reason="invalid_prepared_input",
        )
    raw = read_limited_stdin(parser, json_mode=json_mode, max_input_bytes=max_input_bytes)
    if raw == b"":
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message="Stdin input is empty. Pipe or redirect UTF-8 prepared content when using --stdin.",
            reason="invalid_prepared_input",
        )
    try:
        return raw.decode("utf-8"), "stdin"
    except UnicodeDecodeError:
        exit_with_failure_contract(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message="Stdin input must be valid UTF-8.",
            reason="invalid_prepared_input",
        )
    raise AssertionError("unreachable")


def strip_managed_headers(file_key: str, text: str) -> str:
    lines = text.splitlines()
    idx = 0
    if idx < len(lines) and lines[idx].strip().startswith("<!-- recallloom:file="):
        idx += 1
    if file_key == "rolling_summary" and idx < len(lines) and lines[idx].strip().startswith("<!-- last-writer:"):
        idx += 1
    if idx < len(lines) and lines[idx].strip().startswith("<!-- file-state:"):
        idx += 1
    return "\n".join(lines[idx:]).lstrip("\n")


def reserved_marker_lines(text: str) -> list[tuple[int, str]]:
    results = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        candidate = line.strip()
        if any(candidate.startswith(prefix) for prefix in RESERVED_MARKER_PREFIXES):
            results.append((line_number, candidate))
    return results


def validate_prepared_body(parser, *, json_mode: bool, body_text: str) -> None:
    reserved = reserved_marker_lines(body_text)
    if reserved:
        line_number, marker = reserved[0]
        exit_with_cli_error(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message=(
                "Refusing to commit because the prepared body contains a reserved RecallLoom marker "
                f"on line {line_number}: {marker}"
            ),
            payload=failure_payload(
                "invalid_prepared_input",
                language=preferred_failure_language(os.environ),
                error=(
                    "Refusing to commit because the prepared body contains a reserved RecallLoom marker "
                    f"on line {line_number}: {marker}"
                ),
            ),
        )
    attach_scan = scan_auto_attached_context_text(body_text)
    if attach_scan["blocked"]:
        exit_with_cli_error(
            parser,
            json_mode=json_mode,
            exit_code=2,
            message=(
                "Refusing to commit because the prepared body failed the attached-text safety scan: "
                + ", ".join(attach_scan["hard_block_reasons"])
            ),
            payload=failure_payload(
                "attach_scan_blocked",
                language=preferred_failure_language(os.environ),
                error=(
                    "Refusing to commit because the prepared body failed the attached-text safety scan: "
                    + ", ".join(attach_scan["hard_block_reasons"])
                ),
                details={"hard_block_reasons": attach_scan["hard_block_reasons"]},
            ),
        )


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
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload=cli_failure_payload("python_runtime_unavailable", error=str(exc)),
        )
    enforce_package_support_gate(parser, json_mode=args.json)

    source_text, input_mode = load_prepared_text(
        parser,
        json_mode=args.json,
        source_file=args.source_file,
        use_stdin=args.stdin,
        max_input_bytes=args.max_input_bytes,
    )

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
        exit_with_failure_contract(
            parser,
            json_mode=args.json,
            exit_code=1,
            message="No RecallLoom project root found.",
            reason="no_project_root",
        )

    target_path = workspace.storage_root / FILE_KEYS[args.file_key]
    if not target_path.is_file():
        exit_with_failure_contract(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Missing target file: {target_path}",
            reason="malformed_managed_file",
            details={"path": str(target_path)},
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
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=str(exc),
                    reason="invalid_tool_name",
                    details={"writer_id": args.writer_id},
                )

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
                    payload=failure_payload(
                        "stale_write_context",
                        language=workspace.workspace_language,
                        error=(
                            f"Workspace revision changed from {args.expected_workspace_revision} to "
                            f"{state['workspace_revision']}. Rerun preflight before writing."
                        ),
                        details={
                            "expected_workspace_revision": args.expected_workspace_revision,
                            "current_workspace_revision": state["workspace_revision"],
                        },
                    ),
                )

            current_text = read_text(target_path)
            current_marker = parse_file_marker(current_text)
            if current_marker is None:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Target file is missing a valid file marker: {target_path}",
                    reason="malformed_managed_file",
                    details={"path": str(target_path)},
                )
            if current_marker.file_key != args.file_key:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Target file marker '{current_marker.file_key}' does not match requested file key "
                        f"'{args.file_key}'. Repair the target file before committing."
                    ),
                    reason="malformed_managed_file",
                    details={"path": str(target_path)},
                )
            if current_marker.language != workspace.workspace_language:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Target file language marker '{current_marker.language}' does not match workspace_language "
                        f"'{workspace.workspace_language}'. Repair the target file before committing."
                    ),
                    reason="malformed_managed_file",
                    details={"path": str(target_path)},
                )
            current_state = parse_file_state_marker(current_text)
            if current_state is None:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Target file is missing a valid file-state marker: {target_path}",
                    reason="malformed_managed_file",
                    details={"path": str(target_path)},
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
                    payload=failure_payload(
                        "stale_write_context",
                        language=workspace.workspace_language,
                        error=(
                            f"File revision changed from {args.expected_file_revision} to "
                            f"{current_state.revision}. Reread the file before writing."
                        ),
                        details={
                            "expected_file_revision": args.expected_file_revision,
                            "current_file_revision": current_state.revision,
                        },
                    ),
                )

            source_marker = parse_file_marker(source_text)
            if source_marker is not None and source_marker.file_key != args.file_key:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Source file marker '{source_marker.file_key}' does not match requested file key '{args.file_key}'."
                    ),
                    reason="invalid_prepared_input",
                    details={"source_file_key": source_marker.file_key, "requested_file_key": args.file_key},
                )

            timestamp = now_iso_timestamp()
            new_file_revision = current_state.revision + 1
            new_workspace_revision = state["workspace_revision"] + 1
            body_text = strip_managed_headers(args.file_key, source_text)
            validate_prepared_body(parser, json_mode=args.json, body_text=body_text)
            missing_keys = missing_section_keys(body_text, SECTION_KEYS[args.file_key])
            if missing_keys:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to commit because the prepared file is missing required section markers: "
                        + ", ".join(missing_keys)
                    ),
                    reason="invalid_prepared_input",
                    details={"missing_section_keys": missing_keys},
                )
            duplicate_keys = duplicate_section_keys(body_text)
            if duplicate_keys:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to commit because the prepared file contains duplicate section markers: "
                        + ", ".join(duplicate_keys)
                    ),
                    reason="invalid_prepared_input",
                    details={"duplicate_section_keys": duplicate_keys},
                )
            unknown_keys = unknown_section_keys(
                body_text,
                [*SECTION_KEYS[args.file_key], *OPTIONAL_SECTION_KEYS.get(args.file_key, [])],
            )
            if unknown_keys:
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "Refusing to commit because the prepared file contains unknown section markers: "
                        + ", ".join(unknown_keys)
                    ),
                    reason="invalid_prepared_input",
                    details={"unknown_section_keys": unknown_keys},
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
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Filesystem error while writing {target_path}: {exc}",
                    reason="damaged_sidecar",
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
                    exit_with_failure_contract(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            f"Failed to update state after writing {target_path}: {exc}. "
                            f"Rollback also failed: {rollback_exc}. Workspace may be partially updated."
                        ),
                        reason="damaged_sidecar",
                    )
                exit_with_failure_contract(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Failed to update state after writing {target_path}: {exc}. "
                        "The target file was restored to its previous content."
                    ),
                    reason="damaged_sidecar",
                )
    except LockBusyError as exc:
        exit_with_failure_contract(
            parser,
            json_mode=args.json,
            exit_code=3,
            message=str(exc),
            reason="write_lock_busy",
        )
    except ConfigContractError as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload=cli_failure_payload_for_exception(exc, default_reason="damaged_sidecar"),
        )
    except (OSError, UnicodeDecodeError) as exc:
        message = f"Filesystem error: {exc}"
        exit_with_failure_contract(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=message,
            reason="damaged_sidecar",
        )

    payload = {
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "file_key": args.file_key,
        "input_mode": input_mode,
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
