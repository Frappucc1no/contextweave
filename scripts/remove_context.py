#!/usr/bin/env python3
"""Safely remove a ContextWeave workspace from a project."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path

from _common import (
    bridge_block_integrity,
    BRIDGE_START,
    ConfigContractError,
    exclude_block_integrity,
    EnvironmentContractError,
    exit_with_cli_error,
    find_recovery_workspace,
    LockBusyError,
    managed_exclude_block_text,
    read_text,
    ROOT_ENTRY_CANDIDATES,
    StorageResolutionError,
    ensure_supported_python_version,
    find_contextweave_root,
    remove_git_exclude_block,
    unknown_storage_assets,
    validate_storage_mode,
    workspace_write_lock,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Safely remove a ContextWeave workspace from a project."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project path or a descendant path. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Perform the removal. Without this flag, the script only reports what would be removed.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow removal even if the storage root contains unknown files or directories.",
    )
    parser.add_argument(
        "--storage-mode",
        choices=["hidden", "visible"],
        help="Recovery-only hint for choosing which sidecar to remove when normal workspace detection fails or both sidecars exist.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output.",
    )
    return parser


def unique_tombstone_path(project_root: Path, storage_root_name: str) -> Path:
    base = project_root / f".contextweave-delete-{storage_root_name}"
    if not base.exists():
        return base
    counter = 1
    while True:
        candidate = project_root / f".contextweave-delete-{storage_root_name}-{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def managed_bridge_targets(project_root: Path) -> tuple[list[str], list[str]]:
    healthy_targets: list[str] = []
    malformed_targets: list[str] = []
    for rel_path in ROOT_ENTRY_CANDIDATES:
        path = project_root / rel_path
        if not path.is_file():
            continue
        text = read_text(path)
        ok, reason = bridge_block_integrity(text)
        has_bridge_block = BRIDGE_START in text
        if not ok:
            malformed_targets.append(f"{path} ({reason or 'bridge_malformed'})")
            continue
        if has_bridge_block:
            healthy_targets.append(str(path))
    return healthy_targets, malformed_targets

def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    requested_storage_mode = validate_storage_mode(args.storage_mode) if args.storage_mode else None
    try:
        workspace = find_contextweave_root(
            args.path,
            allow_unsupported_version=True,
            allow_storage_mode_mismatch=True,
        )
    except (StorageResolutionError, ConfigContractError):
        workspace = None
    if workspace is None:
        try:
            workspace = find_recovery_workspace(
                args.path,
                requested_storage_mode=requested_storage_mode,
            )
        except StorageResolutionError as exc:
            exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))
    if workspace is None:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=1, message="No ContextWeave project root found.")

    try:
        with workspace_write_lock(workspace.project_root, "remove_context.py"):
            storage_root = workspace.storage_root
            if storage_root == workspace.project_root:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message="Refusing to remove ContextWeave because storage_root resolves to the project root.",
                )

            if storage_root.parent != workspace.project_root:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message="Refusing to remove ContextWeave because storage_root is not a direct child of the project root.",
                )

            if storage_root.name not in {".contextweave", "contextweave"}:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=f"Refusing to remove unexpected storage root: {storage_root}",
                )

            removed_storage = False
            storage_relocated = False
            removed_git_exclude_block = False
            tombstone_path = None
            storage_cleanup_error = None
            exclude_cleanup_error = None
            unknown_assets = [str(path) for path in unknown_storage_assets(storage_root)]
            bridge_targets, malformed_bridge_targets = managed_bridge_targets(workspace.project_root)

            if bridge_targets or malformed_bridge_targets:
                detail_lines = []
                if bridge_targets:
                    detail_lines.append("Managed bridge blocks still exist in:")
                    detail_lines.extend(bridge_targets)
                if malformed_bridge_targets:
                    detail_lines.append("Malformed bridge blocks still exist in:")
                    detail_lines.extend(malformed_bridge_targets)
                detail_lines.append(
                    "Remove or repair bridge blocks before removing the ContextWeave sidecar. "
                    "In v1 uninstall remains a two-step flow: remove bridge first, then remove the sidecar."
                )
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=3,
                    message="\n".join(detail_lines),
                )

            if args.yes and unknown_assets and not args.force:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=3,
                    message=(
                        "Refusing to remove ContextWeave because the storage root contains unknown assets. "
                        "Review the reported paths or re-run with --force."
                    ),
                )

            if args.yes:
                tombstone = unique_tombstone_path(workspace.project_root, storage_root.name)
                storage_root.rename(tombstone)
                tombstone_path = str(tombstone)
                try:
                    if tombstone.is_dir():
                        shutil.rmtree(tombstone)
                    else:
                        tombstone.unlink()
                    removed_storage = True
                    storage_relocated = False
                    tombstone_path = None
                except OSError as exc:
                    storage_relocated = True
                    storage_cleanup_error = (
                        f"Sidecar was moved to {tombstone}, but cleanup of the tombstone failed: {exc}"
                    )
                if workspace.storage_mode == "hidden":
                    exclude_path = workspace.project_root / ".git" / "info" / "exclude"
                    try:
                        removed_git_exclude_block = remove_git_exclude_block(workspace.project_root)
                    except (LockBusyError, OSError) as exc:
                        exclude_cleanup_error = (
                            "Sidecar removal succeeded, but cleanup of the ContextWeave block in "
                            f".git/info/exclude failed: {exc}"
                        )
                    else:
                        if exclude_path.is_file():
                            exclude_text = exclude_path.read_text(encoding="utf-8")
                            ok, reason = exclude_block_integrity(exclude_text)
                            has_managed_block = managed_exclude_block_text(exclude_text) is not None
                            if not removed_git_exclude_block and (has_managed_block or not ok):
                                detail_map = {
                                    "exclude_start_end_mismatch": "managed block start/end markers are mismatched",
                                    "exclude_duplicate_blocks": "multiple managed exclude blocks are present",
                                    "exclude_order_invalid": "managed block markers are out of order",
                                }
                                detail = detail_map.get(reason, "the managed exclude block still appears malformed or incomplete")
                                exclude_cleanup_error = (
                                    "Sidecar removal succeeded, but the ContextWeave block in .git/info/exclude "
                                    f"was not fully cleaned up because {detail}."
                                )

            payload = {
                "project_root": str(workspace.project_root),
                "storage_root": str(storage_root),
                "storage_mode": workspace.storage_mode,
                "dry_run": not args.yes,
                "force": args.force,
                "unknown_asset_count": len(unknown_assets),
                "unknown_assets": unknown_assets,
                "removed_storage": removed_storage,
                "storage_relocated": storage_relocated,
                "tombstone_path": tombstone_path,
                "storage_cleanup_error": storage_cleanup_error,
                "removed_git_exclude_block": removed_git_exclude_block,
                "exclude_cleanup_error": exclude_cleanup_error,
            }
    except LockBusyError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=3, message=str(exc))
    except OSError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Filesystem error: {exc}")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        if args.yes:
            if removed_storage:
                print(f"Removed ContextWeave storage root: {storage_root}")
            elif storage_relocated:
                print(
                    "ContextWeave storage root was moved out of the project, but final cleanup is incomplete: "
                    f"{tombstone_path}"
                )
            if workspace.storage_mode == "hidden":
                print(
                    "Removed ContextWeave git exclude block: "
                    f"{'yes' if removed_git_exclude_block else 'no'}"
                )
            if storage_cleanup_error:
                print(f"Warning: {storage_cleanup_error}")
            if exclude_cleanup_error:
                print(f"Warning: {exclude_cleanup_error}")
        else:
            print("Dry run only. Use --yes to remove.")
            print(f"Would remove storage root: {storage_root}")
            if unknown_assets:
                print("Unknown assets detected inside the storage root:")
                for item in unknown_assets:
                    print(f"  - {item}")
                print("Re-run with --yes --force only if you intentionally want to remove them too.")
            if workspace.storage_mode == "hidden":
                print("Would also remove the ContextWeave block from .git/info/exclude if present.")


if __name__ == "__main__":
    main()
