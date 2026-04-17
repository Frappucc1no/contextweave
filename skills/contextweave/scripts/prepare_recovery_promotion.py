#!/usr/bin/env python3
"""Prepare structured promotion context for a reviewed recovery proposal."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    ConfigContractError,
    EnvironmentContractError,
    ensure_supported_python_version,
    exit_with_cli_error,
    FILE_KEYS,
    find_contextweave_root,
    latest_active_daily_log,
    load_workspace_state,
    parse_daily_log_entry_line,
    parse_file_state_marker,
    read_text,
    RECOVERY_PROPOSAL_FILE_RE,
    REVIEW_RECORD_FILE_RE,
    StorageResolutionError,
    text_digest,
    validate_recovery_proposal_text,
    validate_recovery_review_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare safe-write promotion context for a reviewed recovery proposal."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument(
        "--proposal-file",
        required=True,
        help="Proposal filename or path. Relative values are resolved against companion/recovery/proposals/ first.",
    )
    parser.add_argument(
        "--review-file",
        help=(
            "Optional review filename or path. Relative values are resolved against "
            "companion/recovery/review_log/ first. Defaults to <proposal-stem>.review.md."
        ),
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def resolve_candidate_path(raw_value: str, base_dir: Path, project_root: Path) -> Path:
    candidate = Path(raw_value).expanduser()
    if candidate.is_absolute():
        return candidate.resolve()

    base_relative = base_dir / raw_value
    if base_relative.exists():
        return base_relative.resolve()

    project_relative = project_root / raw_value
    return project_relative.resolve()


def latest_daily_log_entry_info(latest_daily_log: Path | None):
    if latest_daily_log is None:
        return None
    latest_entry = None
    for line in read_text(latest_daily_log).splitlines():
        entry = parse_daily_log_entry_line(line)
        if entry is not None:
            latest_entry = entry
    return latest_entry


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

    proposals_dir = (workspace.storage_root / "companion" / "recovery" / "proposals").resolve()
    review_log_dir = (workspace.storage_root / "companion" / "recovery" / "review_log").resolve()

    proposal_path = resolve_candidate_path(args.proposal_file, proposals_dir, workspace.project_root)
    if not proposal_path.is_file():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Proposal file does not exist: {proposal_path}",
        )
    if proposal_path.parent != proposals_dir:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "Proposal file must live under companion/recovery/proposals/: "
                f"{proposal_path}"
            ),
        )
    if not RECOVERY_PROPOSAL_FILE_RE.match(proposal_path.name):
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "Proposal filename does not match the expected recovery proposal shape: "
                f"{proposal_path.name}"
            ),
        )

    review_name = args.review_file or f"{proposal_path.stem}.review.md"
    review_path = resolve_candidate_path(review_name, review_log_dir, workspace.project_root)
    if not review_path.is_file():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Review file does not exist: {review_path}",
        )
    if review_path.parent != review_log_dir:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "Review file must live under companion/recovery/review_log/: "
                f"{review_path}"
            ),
        )
    if not REVIEW_RECORD_FILE_RE.match(review_path.name):
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "Review filename does not match the expected review record shape: "
                f"{review_path.name}"
            ),
        )
    expected_review_name = f"{proposal_path.stem}.review.md"
    if review_path.name != expected_review_name:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "Review filename must map to the proposal stem exactly. "
                f"Expected {expected_review_name}, found {review_path.name}."
            ),
        )

    try:
        proposal_text = read_text(proposal_path)
        review_text = read_text(review_path)
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Filesystem error: {exc}",
        )
    if not proposal_text.strip():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Proposal file is empty: {proposal_path}",
        )
    if not review_text.strip():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Review file is empty: {review_path}",
        )
    proposal_errors = validate_recovery_proposal_text(proposal_text)
    if proposal_errors:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message="Recovery proposal failed structure checks:\n- " + "\n- ".join(proposal_errors),
        )
    review_errors = validate_recovery_review_text(review_text)
    if review_errors:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message="Recovery review failed structure checks:\n- " + "\n- ".join(review_errors),
        )

    try:
        state_path = workspace.storage_root / FILE_KEYS["state"]
        state = load_workspace_state(state_path)

        summary_path = workspace.storage_root / FILE_KEYS["rolling_summary"]
        context_brief_path = workspace.storage_root / FILE_KEYS["context_brief"]
        if not summary_path.is_file():
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file: {summary_path}",
            )
        summary_state = parse_file_state_marker(read_text(summary_path))
        if summary_state is None:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file-state metadata marker: {summary_path}",
            )
        if not context_brief_path.is_file():
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file: {context_brief_path}",
            )
        context_brief_state = parse_file_state_marker(read_text(context_brief_path))
        if context_brief_state is None:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file-state metadata marker: {context_brief_path}",
            )
        latest_daily_log = latest_active_daily_log(workspace.storage_root / "daily_logs")
        latest_daily_log_entry = latest_daily_log_entry_info(latest_daily_log)
    except ConfigContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    except (OSError, UnicodeDecodeError) as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem error: {exc}")

    payload = {
        "ok": True,
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "proposal_path": str(proposal_path),
        "proposal_digest": text_digest(proposal_text),
        "review_path": str(review_path),
        "review_digest": text_digest(review_text),
        "promotion_ready": True,
        "safe_write_context": {
            "workspace_revision": state["workspace_revision"],
            "commit_context_file": {
                "rolling_summary": {
                    "path": str(summary_path.relative_to(workspace.project_root)),
                    "expected_file_revision": summary_state.revision if summary_state else None,
                    "expected_workspace_revision": state["workspace_revision"],
                },
                "context_brief": {
                    "path": str(context_brief_path.relative_to(workspace.project_root)),
                    "expected_file_revision": context_brief_state.revision if context_brief_state else None,
                    "expected_workspace_revision": state["workspace_revision"],
                }
                if context_brief_state is not None
                else None,
            },
            "append_daily_log_entry": {
                "latest_file": (
                    str(latest_daily_log.relative_to(workspace.project_root))
                    if latest_daily_log is not None
                    else None
                ),
                "latest_entry_id": latest_daily_log_entry.entry_id if latest_daily_log_entry else None,
                "latest_entry_seq": latest_daily_log_entry.entry_seq if latest_daily_log_entry else None,
                "suggested_date": latest_daily_log.stem if latest_daily_log is not None else None,
                "expected_workspace_revision": state["workspace_revision"],
            },
        },
        "notes": [
            "This helper does not promote any content into core continuity files.",
            "Only rolling_summary.md, context_brief.md, and daily log appends are valid promotion targets for reviewed recovery content.",
            "A model or human must still decide what content is durable enough to write and which target file is appropriate.",
        ],
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"Prepared recovery promotion context for: {proposal_path}")
        print(f"Review record: {review_path}")
        print("Use the returned safe_write_context with the normal write helpers after content review.")


if __name__ == "__main__":
    main()
