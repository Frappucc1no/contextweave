#!/usr/bin/env python3
"""Locate the nearest RecallLoom project root and storage layout."""

from __future__ import annotations

import argparse
import json

from _common import (
    ConfigContractError,
    EnvironmentContractError,
    StorageResolutionError,
    ensure_supported_python_version,
    exit_with_cli_error,
    find_recallloom_root,
    normalize_start_path,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Locate the nearest RecallLoom project root by walking upward."
    )
    parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Starting path. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output instead of just the resolved root.",
    )
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        start = normalize_start_path(args.path)
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload={"start_path": str(start), "found": False},
        )

    start = normalize_start_path(args.path)
    try:
        workspace = find_recallloom_root(start)
    except (StorageResolutionError, ConfigContractError) as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload={"start_path": str(start), "found": False},
        )

    if workspace is None:
        payload = {
            "start_path": str(start),
            "found": False,
            "project_root": None,
            "storage_root": None,
            "storage_mode": None,
            "workspace_language": None,
        }
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=1,
            message=f"No RecallLoom project root found from {start}.",
            payload=payload,
        )

    payload = {
        "start_path": str(start),
        "found": True,
        "project_root": str(workspace.project_root),
        "storage_root": str(workspace.storage_root),
        "storage_mode": workspace.storage_mode,
        "workspace_language": workspace.workspace_language,
        "config_path": str(workspace.config_path) if workspace.config_path else None,
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(workspace.project_root)


if __name__ == "__main__":
    main()
