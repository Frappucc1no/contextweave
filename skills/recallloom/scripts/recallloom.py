#!/usr/bin/env python3
"""Unified operator-friendly entrypoint for RecallLoom helper workflows."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

from core.protocol.contracts import ROOT_ENTRY_CANDIDATES

from _common import (
    ConfigContractError,
    EnvironmentContractError,
    ensure_supported_python_version,
    exit_with_cli_error,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED_BRIDGE_TARGETS = [path.as_posix() for path in ROOT_ENTRY_CANDIDATES]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified RecallLoom command entry for init, validate, status, and bridge flows."
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Initialize a RecallLoom workspace, validate it, and return next-step guidance.",
    )
    init_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project root directory to initialize. Defaults to the current working directory.",
    )
    init_parser.add_argument(
        "--tool-name",
        default="RecallLoom",
        help="Tool name used in generated metadata such as the rolling summary marker.",
    )
    init_parser.add_argument(
        "--date",
        help="Date to use for generated metadata and optional daily log file.",
    )
    init_parser.add_argument(
        "--storage-mode",
        choices=["hidden", "visible"],
        help="Storage layout mode. Defaults to hidden sidecar mode.",
    )
    init_parser.add_argument(
        "--workspace-language",
        choices=["en", "zh-CN"],
        help="Language used for generated workspace files.",
    )
    init_parser.add_argument(
        "--create-daily-log",
        action="store_true",
        help="Optionally create today's daily log scaffold during initialization.",
    )
    init_parser.add_argument(
        "--force",
        action="store_true",
        help="Apply first-time initialization writes even if a managed file path already exists.",
    )
    init_parser.add_argument(
        "--skip-git-exclude",
        action="store_true",
        help="Do not add .recallloom/ to .git/info/exclude when using hidden mode in a git repo.",
    )
    init_parser.add_argument(
        "--bridge",
        choices=SUPPORTED_BRIDGE_TARGETS,
        help="Optionally apply a thin bridge to one supported root entry file after successful init+validate.",
    )
    init_parser.add_argument(
        "--yes",
        action="store_true",
        help="Required together with --bridge to apply the bridge instead of only suggesting it.",
    )
    init_parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output.",
    )

    validate_parser = subparsers.add_parser(
        "validate",
        help="Validate a RecallLoom workspace and managed file contracts.",
    )
    validate_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project path or a descendant path. Defaults to the current working directory.",
    )
    validate_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    status_parser = subparsers.add_parser(
        "status",
        help="Summarize current continuity status, confidence, and workday recommendation.",
    )
    status_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project path or a descendant path. Defaults to the current working directory.",
    )
    status_parser.add_argument(
        "--timezone",
        help="Optional IANA timezone such as Asia/Shanghai. Defaults to the host local timezone.",
    )
    status_parser.add_argument(
        "--now",
        help="Current time in ISO 8601 format.",
    )
    status_parser.add_argument(
        "--rollover-hour",
        type=int,
        default=3,
        help="Logical day rollover hour in 24-hour form. Defaults to 3.",
    )
    status_parser.add_argument(
        "--preferred-date",
        help="Optional explicit append target date in YYYY-MM-DD form for workday guidance.",
    )
    status_parser.add_argument(
        "--session-intent",
        choices=[
            "backfill_previous_day_closure",
            "close_previous_day_then_start_new_day",
            "continue_active_day",
            "log_not_needed_for_this_session",
            "review_date_before_append",
            "start_new_active_day",
        ],
        help="Optional explicit session-intent hint using one of the recommendation types.",
    )
    status_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    bridge_parser = subparsers.add_parser(
        "bridge",
        help="Preview, apply, or remove a RecallLoom thin bridge in one supported root entry file.",
    )
    bridge_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project path or a descendant path. Defaults to the current working directory.",
    )
    bridge_parser.add_argument(
        "--file",
        action="append",
        default=[],
        help="Specific project-root-relative entry file to bridge. At most one target per invocation.",
    )
    bridge_parser.add_argument(
        "--remove",
        action="store_true",
        help="Remove RecallLoom managed bridge blocks instead of adding or updating them.",
    )
    bridge_parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply the change. Without this flag, the command runs in preview mode.",
    )
    bridge_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

    return parser


def _run_helper_json(
    parser,
    *,
    helper_name: str,
    helper_args: list[str],
    json_mode_on_failure: bool,
) -> dict:
    cmd = [sys.executable, str(SCRIPT_DIR / helper_name), *helper_args, "--json"]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.returncode != 0:
        parsed_error = None
        if proc.stdout:
            try:
                parsed_error = json.loads(proc.stdout)
            except json.JSONDecodeError:
                parsed_error = None
        if json_mode_on_failure:
            if proc.stdout:
                print(proc.stdout, end="")
                raise SystemExit(proc.returncode)
            exit_with_cli_error(
                parser,
                json_mode=True,
                exit_code=proc.returncode,
                message=proc.stderr.strip() or f"{helper_name} failed.",
            )
        error_message = (
            parsed_error.get("error")
            if isinstance(parsed_error, dict) and isinstance(parsed_error.get("error"), str)
            else proc.stderr.strip() or f"{helper_name} failed."
        )
        exit_with_cli_error(
            parser,
            json_mode=False,
            exit_code=proc.returncode,
            message=error_message,
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        exit_with_cli_error(
            parser,
            json_mode=True,
            exit_code=2,
            message=f"{helper_name} returned invalid JSON: {exc}",
        )
    raise AssertionError("unreachable")


def _run_helper_passthrough(*, helper_name: str, helper_args: list[str]) -> None:
    cmd = [sys.executable, str(SCRIPT_DIR / helper_name), *helper_args]
    proc = subprocess.run(cmd, text=True, capture_output=True, check=False)
    if proc.stdout:
        print(proc.stdout, end="")
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    raise SystemExit(proc.returncode)


def _bridge_candidates(project_root: Path) -> list[str]:
    return [rel for rel in SUPPORTED_BRIDGE_TARGETS if (project_root / rel).is_file()]


def _suggested_next_actions(*, bridge_candidates: list[str]) -> list[str]:
    actions = ["rl-status", "continue this project"]
    if bridge_candidates:
        actions.insert(1, f"rl-bridge --file {bridge_candidates[0]} --yes")
    return actions


def _print_init_summary(payload: dict) -> None:
    print(f"RecallLoom init completed for {payload['project_root']}")
    print(f"Storage root: {payload['storage_root']}")
    print(f"Storage mode: {payload['storage_mode']}")
    print(f"Workspace language: {payload['workspace_language']}")
    print(f"Validated: {'yes' if payload['validated'] else 'no'}")
    if payload.get("bridge_candidates"):
        print("Bridge candidates:")
        for item in payload["bridge_candidates"]:
            print(f"  - {item}")
    if payload.get("bridge_applied"):
        print(f"Bridge applied: {payload['bridge_applied'][0]['target']}")
    print("Suggested next actions:")
    for action in payload["suggested_next_actions"]:
        print(f"  - {action}")


def _handle_init(parser, args: argparse.Namespace) -> None:
    init_args = [args.target]
    if args.tool_name:
        init_args.extend(["--tool-name", args.tool_name])
    if args.date:
        init_args.extend(["--date", args.date])
    if args.storage_mode:
        init_args.extend(["--storage-mode", args.storage_mode])
    if args.workspace_language:
        init_args.extend(["--workspace-language", args.workspace_language])
    if args.create_daily_log:
        init_args.append("--create-daily-log")
    if args.force:
        init_args.append("--force")
    if args.skip_git_exclude:
        init_args.append("--skip-git-exclude")

    init_payload = _run_helper_json(
        parser,
        helper_name="init_context.py",
        helper_args=init_args,
        json_mode_on_failure=args.json,
    )
    if not init_payload.get("project_root") or not init_payload.get("storage_root"):
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message="init_context.py returned an incomplete payload.",
        )

    validate_payload = _run_helper_json(
        parser,
        helper_name="validate_context.py",
        helper_args=[args.target],
        json_mode_on_failure=args.json,
    )

    bridge_payload = None
    if args.bridge:
        if not args.yes:
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message="--bridge requires --yes. Bridge application stays explicit.",
            )
        bridge_payload = _run_helper_json(
            parser,
            helper_name="manage_entry_bridge.py",
            helper_args=[args.target, "--file", args.bridge, "--yes"],
            json_mode_on_failure=args.json,
        )

    project_root = Path(init_payload["project_root"])
    bridge_candidates = _bridge_candidates(project_root)
    payload = {
        "ok": True,
        "command": "init",
        "project_root": init_payload["project_root"],
        "storage_root": init_payload["storage_root"],
        "storage_mode": init_payload["storage_mode"],
        "workspace_language": init_payload["workspace_language"],
        "initialized": True,
        "already_initialized": bool(init_payload.get("already_initialized", False)),
        "validated": bool(validate_payload.get("valid", False)),
        "init": init_payload,
        "validate": validate_payload,
        "bridge_candidates": bridge_candidates,
        "bridge_applied": bridge_payload.get("results") if bridge_payload else None,
        "suggested_next_actions": _suggested_next_actions(bridge_candidates=bridge_candidates),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        _print_init_summary(payload)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=getattr(args, "json", False), exit_code=2, message=str(exc))

    if args.command == "init":
        _handle_init(parser, args)
        return

    if args.command == "validate":
        if args.json:
            payload = _run_helper_json(
                parser,
                helper_name="validate_context.py",
                helper_args=[args.target],
                json_mode_on_failure=True,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _run_helper_passthrough(helper_name="validate_context.py", helper_args=[args.target])
        return

    if args.command == "status":
        helper_args = [args.target]
        if args.timezone:
            helper_args.extend(["--timezone", args.timezone])
        if args.now:
            helper_args.extend(["--now", args.now])
        if args.rollover_hour is not None:
            helper_args.extend(["--rollover-hour", str(args.rollover_hour)])
        if args.preferred_date:
            helper_args.extend(["--preferred-date", args.preferred_date])
        if args.session_intent:
            helper_args.extend(["--session-intent", args.session_intent])
        if args.json:
            payload = _run_helper_json(
                parser,
                helper_name="summarize_continuity_status.py",
                helper_args=helper_args,
                json_mode_on_failure=True,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _run_helper_passthrough(
                helper_name="summarize_continuity_status.py", helper_args=helper_args
            )
        return

    if args.command == "bridge":
        helper_args = [args.target]
        for rel in args.file:
            helper_args.extend(["--file", rel])
        if args.remove:
            helper_args.append("--remove")
        if args.yes:
            helper_args.append("--yes")
        if args.json:
            payload = _run_helper_json(
                parser,
                helper_name="manage_entry_bridge.py",
                helper_args=helper_args,
                json_mode_on_failure=True,
            )
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _run_helper_passthrough(helper_name="manage_entry_bridge.py", helper_args=helper_args)
        return

    raise ConfigContractError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
