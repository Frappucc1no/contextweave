#!/usr/bin/env python3
"""Manage thin bridges from root entry files to ContextWeave continuity files."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    bridge_block_integrity,
    ConfigContractError,
    EnvironmentContractError,
    exit_with_cli_error,
    atomic_write_if_unchanged,
    LockBusyError,
    load_workspace_state,
    dump_json,
    FILE_KEYS,
    latest_active_daily_log,
    managed_file_contract_issue,
    now_iso_timestamp,
    ROOT_ENTRY_CANDIDATES,
    restore_text_snapshot,
    StorageResolutionError,
    detect_root_entry_files,
    ensure_supported_python_version,
    find_contextweave_root,
    read_text,
    remove_bridge_block,
    render_bridge_block,
    replace_or_insert_bridge,
    workspace_write_lock,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Preview, apply, or remove ContextWeave thin bridges in root entry files."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project path or a descendant path. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--file",
        action="append",
        default=[],
        help=(
            "Specific project-root-relative entry file to bridge. "
            "Only officially supported root entry files are allowed. "
            "v1 accepts at most one target per invocation."
        ),
    )
    parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove ContextWeave managed bridge blocks instead of adding or updating them.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply the change. Without this flag, the script runs in preview mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output.",
    )
    return parser


def resolve_targets(project_root: Path, explicit_files: list[str]) -> list[Path]:
    if explicit_files:
        targets: list[Path] = []
        allowed = {str(path.as_posix()) for path in ROOT_ENTRY_CANDIDATES}
        for rel in explicit_files:
            normalized_rel = Path(rel).as_posix()
            if normalized_rel not in allowed:
                raise ValueError(
                    "Refusing to bridge a non-supported file. Allowed targets are: "
                    + ", ".join(sorted(allowed))
                )
            candidate = (project_root / normalized_rel).resolve()
            try:
                candidate.relative_to(project_root)
            except ValueError:
                raise ValueError(f"Refusing to modify a file outside the project root: {candidate}")
            targets.append(candidate)
        return targets
    return detect_root_entry_files(project_root)


def bridge_integrity_message(reason: str | None, target: Path) -> str:
    detail_map = {
        "bridge_start_end_mismatch": "bridge start/end markers are mismatched",
        "bridge_duplicate_blocks": "multiple managed bridge blocks are present",
        "bridge_order_invalid": "bridge start/end markers are out of order",
    }
    detail = detail_map.get(reason, "the managed bridge block is malformed")
    return (
        f"Refusing to modify {target} because {detail}. "
        "Repair or remove the malformed bridge block manually before retrying."
    )


def missing_continuity_files(workspace) -> list[Path]:
    issues: list[Path] = []
    required = [
        workspace.storage_root / "config.json",
    ]
    for path in required:
        if not path.is_file():
            issues.append(path)
    contract_paths = [
        (workspace.storage_root / FILE_KEYS["context_brief"], "context_brief"),
        (workspace.storage_root / FILE_KEYS["rolling_summary"], "rolling_summary"),
    ]
    update_protocol_path = workspace.storage_root / FILE_KEYS["update_protocol"]
    if update_protocol_path.exists():
        contract_paths.append((update_protocol_path, "update_protocol"))
    for path, file_key in contract_paths:
        issue = managed_file_contract_issue(
            path,
            file_key=file_key,
            workspace_language=workspace.workspace_language,
            expected_protocol_version=workspace.protocol_version,
        )
        if issue is not None:
            issues.append(path)
    if not (workspace.storage_root / "daily_logs").is_dir():
        issues.append(workspace.storage_root / "daily_logs")
    return issues


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
        targets = resolve_targets(workspace.project_root, args.file)
    except ValueError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if not targets:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=1,
            message="No eligible entry files found. Use --file to specify a target.",
        )

    if len(targets) > 1:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=(
                "v1 bridge operations accept exactly one target per invocation. "
                "Re-run with a single explicit --file argument."
            ),
        )

    try:
        with workspace_write_lock(workspace.project_root, "manage_entry_bridge.py"):
            state_path = workspace.storage_root / FILE_KEYS["state"]
            try:
                state = load_workspace_state(state_path)
            except ConfigContractError as exc:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=str(exc),
                )

            results = []
            for target in targets:
                if not target.is_file():
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=f"Target entry file does not exist: {target}",
                    )

                current_text = read_text(target)
                ok, reason = bridge_block_integrity(current_text)
                if not ok:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=3,
                        message=bridge_integrity_message(reason, target),
                    )

                missing = missing_continuity_files(workspace)
                if missing:
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            "Refusing to modify entry files because required continuity files are missing:\n"
                            + "\n".join(str(path) for path in missing)
                        ),
                    )

                if args.remove:
                    updated_text, changed = remove_bridge_block(current_text)
                else:
                    block = render_bridge_block(workspace, target)
                    updated_text = replace_or_insert_bridge(current_text, block)
                    changed = updated_text != current_text

                rel_target = str(target.relative_to(workspace.project_root))
                state_changed = False
                if args.remove:
                    if rel_target in state["bridged_entries"]:
                        state["bridged_entries"].pop(rel_target, None)
                        state_changed = True
                else:
                    latest_daily_log = latest_active_daily_log(workspace.storage_root / "daily_logs")
                    next_bridge_state = {
                        "update_protocol_revision_seen": state["update_protocol_revision"],
                        "latest_daily_log_seen": (
                            str(latest_daily_log.relative_to(workspace.storage_root))
                            if latest_daily_log is not None
                            else None
                        ),
                        "updated_at": now_iso_timestamp(),
                    }
                    if state["bridged_entries"].get(rel_target) != next_bridge_state:
                        state["bridged_entries"][rel_target] = next_bridge_state
                        state_changed = True

                if args.yes and (changed or state_changed):
                    if changed:
                        try:
                            atomic_write_if_unchanged(target, expected_text=current_text, new_text=updated_text)
                        except OSError as exc:
                            exit_with_cli_error(
                                parser,
                                json_mode=args.json,
                                exit_code=2,
                                message=f"Filesystem error while writing {target}: {exc}",
                            )
                    try:
                        dump_json(state_path, state)
                    except OSError as exc:
                        if changed:
                            try:
                                restore_text_snapshot(target, existed=True, text=current_text)
                            except OSError as rollback_exc:
                                exit_with_cli_error(
                                    parser,
                                    json_mode=args.json,
                                    exit_code=2,
                                    message=(
                                        f"Failed to update state after writing {target}: {exc}. "
                                        f"Rollback also failed: {rollback_exc}. Workspace may be partially updated."
                                    ),
                                )
                            exit_with_cli_error(
                                parser,
                                json_mode=args.json,
                                exit_code=2,
                                message=(
                                    f"Failed to update state after writing {target}: {exc}. "
                                    "The target file was restored to its previous content."
                                ),
                            )
                        exit_with_cli_error(
                            parser,
                            json_mode=args.json,
                            exit_code=2,
                            message=(
                                f"Failed to update bridge state for {target}: {exc}. "
                                "No file content was changed."
                            ),
                        )

                results.append(
                    {
                        "target": str(target),
                        "action": "remove" if args.remove else "apply",
                        "changed": changed,
                        "state_changed": state_changed,
                        "applied": args.yes and (changed or state_changed),
                    }
                )
    except LockBusyError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=3, message=str(exc))
    except OSError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem error: {exc}")

    payload = {
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "storage_mode": workspace.storage_mode,
        "workspace_language": workspace.workspace_language,
        "dry_run": not args.yes,
        "results": results,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for result in results:
            state = "would change" if not args.yes and result["changed"] else "changed" if result["applied"] else "no change"
            print(f"{result['target']}: {state}")


if __name__ == "__main__":
    main()
