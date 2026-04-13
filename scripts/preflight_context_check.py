#!/usr/bin/env python3
"""Run freshness and write-target checks before updating ContextWeave files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    ConfigContractError,
    EnvironmentContractError,
    exit_with_cli_error,
    FILE_KEYS,
    ensure_supported_python_version,
    invalid_iso_like_daily_log_files,
    load_workspace_state,
    parse_daily_log_entry_line,
    parse_file_state_marker,
    read_text,
    StorageResolutionError,
    find_contextweave_root,
    latest_active_daily_log,
    latest_file,
    today_iso,
)


DEFAULT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

DEFAULT_EXCLUDED_FILES = {
    ".DS_Store",
    ".contextweave.write.lock",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Check freshness and likely write targets before updating ContextWeave files."
    )
    parser.add_argument("path", nargs="?", default=".", help="Project path or a descendant path.")
    parser.add_argument(
        "--fail-on-stale",
        action="store_true",
        help="Exit non-zero if a non-context workspace artifact is newer than the rolling summary.",
    )
    parser.add_argument("--json", action="store_true", help="Print structured JSON output.")
    return parser


def iter_workspace_artifacts(project_root: Path, storage_root: Path) -> list[Path]:
    artifacts: list[Path] = []
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            path.relative_to(storage_root)
            continue
        except ValueError:
            pass
        if path.name in DEFAULT_EXCLUDED_FILES:
            continue
        rel_path = path.relative_to(project_root)
        rel_dir_parts = rel_path.parent.parts
        if any(part in DEFAULT_EXCLUDED_DIRS for part in rel_dir_parts):
            continue
        artifacts.append(path)
    return artifacts


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

    summary_path = workspace.storage_root / FILE_KEYS["rolling_summary"]
    context_brief_path = workspace.storage_root / FILE_KEYS["context_brief"]
    state_path = workspace.storage_root / FILE_KEYS["state"]
    update_protocol_path = workspace.storage_root / FILE_KEYS["update_protocol"]
    logs_dir = workspace.storage_root / "daily_logs"
    if not summary_path.is_file():
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Missing required file: {summary_path}",
        )

    invalid_daily_logs = invalid_iso_like_daily_log_files(logs_dir)
    if invalid_daily_logs:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "Refusing preflight because one or more daily log filenames match the date pattern but are invalid ISO dates:\n"
                + "\n".join(str(path) for path in invalid_daily_logs)
            ),
        )

    latest_daily_log = latest_active_daily_log(logs_dir)
    try:
        state = load_workspace_state(state_path)
    except ConfigContractError as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
        )
    summary_state = parse_file_state_marker(read_text(summary_path))
    if summary_state is None:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Missing required file-state metadata marker: {summary_path}",
        )
    context_brief_state = None
    if context_brief_path.is_file():
        context_brief_state = parse_file_state_marker(read_text(context_brief_path))
        if context_brief_state is None:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=f"Missing required file-state metadata marker: {context_brief_path}",
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
            )
    latest_daily_log_entry = None
    if latest_daily_log is not None:
        for line in read_text(latest_daily_log).splitlines():
            entry = parse_daily_log_entry_line(line)
            if entry is not None:
                latest_daily_log_entry = entry
        if latest_daily_log_entry is None:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=(
                    "Missing required daily-log-entry metadata marker in the latest ISO-dated daily log: "
                    f"{latest_daily_log}"
                ),
            )
    latest_workspace_artifact = latest_file(
        iter_workspace_artifacts(workspace.project_root, workspace.storage_root)
    )
    summary_mtime = summary_path.stat().st_mtime
    workspace_artifact_is_newer = (
        latest_workspace_artifact is not None
        and latest_workspace_artifact.stat().st_mtime > summary_mtime
    )
    summary_revision_is_stale = state["workspace_revision"] > summary_state.base_workspace_revision
    workspace_is_newer = workspace_artifact_is_newer or summary_revision_is_stale

    recommended_write_targets = [str(summary_path.relative_to(workspace.project_root))]
    conditional_review_targets = []
    if latest_daily_log is not None:
        conditional_review_targets.append(
            {
                "path": str(latest_daily_log.relative_to(workspace.project_root)),
                "reason": (
                    "Review only if this session creates a new milestone entry or end-of-day log. "
                    "Do not treat an existing daily log as a default current-state write target."
                ),
            }
        )
    if context_brief_path.is_file():
        conditional_review_targets.append(
            {
                "path": str(context_brief_path.relative_to(workspace.project_root)),
                "reason": (
                    "Review if mission, audience, scope, source of truth, workflow, "
                    "boundaries, or current phase changed."
                ),
            }
        )
    override_review_targets = []
    if update_protocol_path.is_file():
        override_review_targets.append(
            {
                "path": str(update_protocol_path.relative_to(workspace.project_root)),
                "reason": (
                    "Review project-local continuity rules before applying default cold-start, "
                    "write-target, or archive guidance. v1 helpers do not parse natural-language "
                    "override prose automatically."
                ),
            }
        )

    payload = {
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "storage_mode": workspace.storage_mode,
        "workspace_language": workspace.workspace_language,
        "context_brief": str(context_brief_path) if context_brief_path.is_file() else None,
        "state": str(state_path),
        "update_protocol": str(update_protocol_path) if update_protocol_path.is_file() else None,
        "workspace_revision": state["workspace_revision"],
        "update_protocol_revision": state["update_protocol_revision"],
        "rolling_summary": str(summary_path),
        "rolling_summary_revision": summary_state.revision if summary_state else None,
        "context_brief_revision": context_brief_state.revision if context_brief_state else None,
        "update_protocol_file_revision": update_protocol_state.revision if update_protocol_state else None,
        "latest_daily_log": str(latest_daily_log) if latest_daily_log else None,
        "latest_daily_log_entry_id": latest_daily_log_entry.entry_id if latest_daily_log_entry else None,
        "latest_daily_log_entry_seq": latest_daily_log_entry.entry_seq if latest_daily_log_entry else None,
        "daily_log_selection_rule": "latest_active_daily_log",
        "latest_workspace_artifact": str(latest_workspace_artifact) if latest_workspace_artifact else None,
        "workspace_artifact_newer_than_summary": workspace_artifact_is_newer,
        "summary_revision_stale": summary_revision_is_stale,
        "workspace_newer_than_summary": workspace_is_newer,
        "recommended_write_targets": recommended_write_targets,
        "conditional_review_targets": conditional_review_targets,
        "override_review_targets": override_review_targets,
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
                if context_brief_path.is_file()
                else None,
                "update_protocol": {
                    "path": str(update_protocol_path.relative_to(workspace.project_root)),
                    "expected_file_revision": update_protocol_state.revision if update_protocol_state else None,
                    "expected_workspace_revision": state["workspace_revision"],
                }
                if update_protocol_path.is_file()
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
                "suggested_date": (latest_daily_log.stem if latest_daily_log is not None else today_iso()),
                "expected_workspace_revision": state["workspace_revision"],
            },
        },
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"ContextWeave root: {workspace.project_root}")
        print(f"Storage root: {workspace.storage_root}")
        print(f"Storage mode: {workspace.storage_mode}")
        print(f"Workspace language: {workspace.workspace_language}")
        print(f"Rolling summary: {summary_path}")
        print(
            "Latest active daily log: "
            f"{latest_daily_log if latest_daily_log else 'none'}"
        )
        print(
            "Latest workspace artifact: "
            f"{latest_workspace_artifact if latest_workspace_artifact else 'none'}"
        )
        print(
            "Summary revision stale: "
            f"{'yes' if summary_revision_is_stale else 'no'}"
        )
        print(f"Workspace newer than summary: {'yes' if workspace_is_newer else 'no'}")
        print("Recommended write targets:")
        for target in recommended_write_targets:
            print(f"  - {target}")
        if conditional_review_targets:
            print("Conditional review targets:")
            for target in conditional_review_targets:
                print(f"  - {target['path']}: {target['reason']}")
        if override_review_targets:
            print("Override review targets:")
            for target in override_review_targets:
                print(f"  - {target['path']}: {target['reason']}")
        print("Safe write context:")
        print(f"  - workspace_revision: {state['workspace_revision']}")
        print("  - use commit_context_file.py for revision-checked writes to context_brief.md, rolling_summary.md, or update_protocol.md")
        print("  - use append_daily_log_entry.py for revision-checked daily-log milestone entries")

    raise SystemExit(3 if args.fail_on_stale and workspace_is_newer else 0)


if __name__ == "__main__":
    main()
