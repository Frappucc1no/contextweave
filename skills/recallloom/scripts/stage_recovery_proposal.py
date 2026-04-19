#!/usr/bin/env python3
"""Stage a prepared recovery proposal into the RecallLoom companion namespace."""

from __future__ import annotations

import argparse
import json
import re
from datetime import datetime
from pathlib import Path

from _common import (
    ConfigContractError,
    EnvironmentContractError,
    ensure_supported_python_version,
    exit_with_cli_error,
    find_recallloom_root,
    LockBusyError,
    now_iso_timestamp,
    read_text,
    StorageResolutionError,
    text_digest,
    validate_recovery_proposal_text,
    workspace_write_lock,
    write_text,
)


FILENAME_STAMP_RE = re.compile(r"^\d{4}-\d{2}-\d{2}-\d{6}$")
SAFE_ID_RE = re.compile(r"[^A-Za-z0-9._-]+")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Stage a prepared recovery proposal into companion/recovery/proposals."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument("--source-file", required=True, help="Path to prepared proposal markdown content.")
    parser.add_argument(
        "--proposal-id",
        help="Optional stable identifier used in the staged proposal filename. Defaults to a slug from the source filename.",
    )
    parser.add_argument(
        "--filename-stamp",
        help="Optional filename stamp in YYYY-MM-DD-HHMMSS form. Defaults to the current local time.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def normalize_proposal_id(raw_value: str) -> str:
    normalized = SAFE_ID_RE.sub("-", raw_value.strip()).strip("-._")
    if not normalized:
        raise ValueError("Proposal id is empty after normalization.")
    return normalized


def resolve_filename_stamp(raw_value: str | None) -> str:
    if raw_value:
        if not FILENAME_STAMP_RE.match(raw_value):
            raise ValueError(
                f"Invalid --filename-stamp value: {raw_value}. Expected YYYY-MM-DD-HHMMSS."
            )
        return raw_value
    return datetime.now().astimezone().strftime("%Y-%m-%d-%H%M%S")


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
        body_text = read_text(source_path)
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Filesystem error: {exc}",
        )
    if not body_text.strip():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Source file is empty: {source_path}",
        )
    proposal_errors = validate_recovery_proposal_text(body_text)
    if proposal_errors:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message="Invalid recovery proposal content:\n- " + "\n- ".join(proposal_errors),
        )

    try:
        proposal_id = normalize_proposal_id(args.proposal_id or source_path.stem)
        filename_stamp = resolve_filename_stamp(args.filename_stamp)
    except ValueError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    try:
        workspace = find_recallloom_root(args.path)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No RecallLoom project root found.")

    proposals_dir = workspace.storage_root / "companion" / "recovery" / "proposals"
    review_log_dir = workspace.storage_root / "companion" / "recovery" / "review_log"
    archive_dir = workspace.storage_root / "companion" / "recovery" / "archive"
    target_path = proposals_dir / f"{filename_stamp}-{proposal_id}.md"

    try:
        with workspace_write_lock(workspace.project_root, "stage_recovery_proposal.py"):
            proposals_dir.mkdir(parents=True, exist_ok=True)
            review_log_dir.mkdir(parents=True, exist_ok=True)
            archive_dir.mkdir(parents=True, exist_ok=True)
            if target_path.exists():
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Refusing to overwrite an existing recovery proposal: {target_path}",
                )
            write_text(target_path, body_text.rstrip("\n") + "\n")
    except LockBusyError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=3, message=str(exc))
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem error: {exc}")

    payload = {
        "ok": True,
        "proposal_path": str(target_path),
        "proposal_id": proposal_id,
        "filename_stamp": filename_stamp,
        "source_file": str(source_path),
        "source_digest": text_digest(body_text),
        "staged_at": now_iso_timestamp(),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Staged recovery proposal: {target_path}")


if __name__ == "__main__":
    main()
