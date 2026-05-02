#!/usr/bin/env python3
"""Unified operator-friendly entrypoint for RecallLoom helper workflows."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path


_BOOTSTRAP_DEFAULT_MINIMUM_PYTHON_VERSION = "3.10"


def _bootstrap_failure_language() -> str:
    lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
    return "zh-CN" if lang.lower().startswith("zh") else "en"


def _bootstrap_minimum_python_version() -> tuple[tuple[int, ...], str]:
    fallback_parts = tuple(int(part) for part in _BOOTSTRAP_DEFAULT_MINIMUM_PYTHON_VERSION.split("."))
    metadata_path = Path(__file__).resolve().parent.parent / "package-metadata.json"
    try:
        payload = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        raw = _BOOTSTRAP_DEFAULT_MINIMUM_PYTHON_VERSION
    else:
        raw = payload.get("minimum_python_version", _BOOTSTRAP_DEFAULT_MINIMUM_PYTHON_VERSION)
        if not isinstance(raw, str) or not raw.strip():
            raw = _BOOTSTRAP_DEFAULT_MINIMUM_PYTHON_VERSION
    parts = raw.strip().split(".")
    if not parts or any(not part.isdigit() for part in parts):
        return fallback_parts, _BOOTSTRAP_DEFAULT_MINIMUM_PYTHON_VERSION
    normalized = tuple(int(part) for part in parts)
    return normalized, ".".join(str(part) for part in normalized)


def _bootstrap_runtime_contract(minimum_text: str) -> dict:
    return {
        "blocked": True,
        "blocked_reason": "python_runtime_unavailable",
        "recoverability": "retryable",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["find_compatible_python", "report_blocked_runtime"],
        "user_message": {
            "en": (
                "RecallLoom cannot start yet because this environment does not provide "
                f"Python {minimum_text} or newer."
            ),
            "zh-CN": f"当前环境还不能启动 RecallLoom，因为这里没有可用的 Python {minimum_text}+ 运行时。",
        },
        "operator_note": {
            "en": f"Find or point the host at a compatible Python {minimum_text}+ interpreter before retrying.",
            "zh-CN": f"请先找到或指定兼容的 Python {minimum_text}+ 解释器，再重试。",
        },
    }


def _bootstrap_runtime_payload(message: str, minimum_text: str) -> dict:
    language = _bootstrap_failure_language()
    contract = _bootstrap_runtime_contract(minimum_text)
    return {
        "ok": False,
        "blocked": contract["blocked"],
        "blocked_reason": contract["blocked_reason"],
        "recoverability": contract["recoverability"],
        "surface_level": contract["surface_level"],
        "trust_effect": contract["trust_effect"],
        "next_actions": list(contract["next_actions"]),
        "user_message": contract["user_message"][language],
        "operator_note": contract["operator_note"][language],
        "error": message,
    }


def _exit_if_runtime_unsupported() -> None:
    minimum_parts, minimum_text = _bootstrap_minimum_python_version()
    current = sys.version_info[: len(minimum_parts)]
    if current >= minimum_parts:
        return
    message = (
        "RecallLoom helper scripts require "
        f"Python {minimum_text}+; current interpreter is "
        f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    )
    if "--json" in sys.argv[1:]:
        print(json.dumps(_bootstrap_runtime_payload(message, minimum_text), ensure_ascii=False, indent=2))
    else:
        print(message, file=sys.stderr)
    raise SystemExit(2)


_exit_if_runtime_unsupported()

from core.continuity.workday import RECOMMENDATION_TYPES, describe_workday_guidance
from core.failure.contracts import failure_payload, preferred_failure_language
from core.protocol.contracts import ROOT_ENTRY_CANDIDATES
from core.support.policy import action_level_for_dispatcher

from _common import (
    ConfigContractError,
    EnvironmentContractError,
    enforce_package_support_gate,
    ensure_supported_python_version,
    exit_with_cli_error,
)


SCRIPT_DIR = Path(__file__).resolve().parent
SUPPORTED_BRIDGE_TARGETS = [path.as_posix() for path in ROOT_ENTRY_CANDIDATES]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified RecallLoom command entry for init, resume, validate, status, and bridge flows."
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

    resume_parser = subparsers.add_parser(
        "resume",
        help="Run the RecallLoom fast-path resume checkpoint for the current project.",
    )
    resume_parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project path or a descendant path. Defaults to the current working directory.",
    )
    resume_parser.add_argument(
        "--timezone",
        help="Optional IANA timezone such as Asia/Shanghai. Defaults to the host local timezone.",
    )
    resume_parser.add_argument(
        "--now",
        help="Current time in ISO 8601 format.",
    )
    resume_parser.add_argument(
        "--rollover-hour",
        type=int,
        default=3,
        help="Logical day rollover hour in 24-hour form. Defaults to 3.",
    )
    resume_parser.add_argument(
        "--preferred-date",
        help="Optional explicit append target date in YYYY-MM-DD form for workday guidance.",
    )
    resume_parser.add_argument(
        "--session-intent",
        choices=sorted(RECOMMENDATION_TYPES),
        help="Optional explicit session-intent hint using one of the recommendation types.",
    )
    resume_parser.add_argument("--json", action="store_true", help="Print structured JSON output.")

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
        choices=sorted(RECOMMENDATION_TYPES),
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


def _preferred_language() -> str:
    return preferred_failure_language(os.environ)


def _contract_payload(reason: str, *, error: str | None = None) -> dict:
    return failure_payload(reason, language=_preferred_language(), error=error)


def _infer_helper_failure_reason(helper_name: str, message: str) -> str | None:
    lowered = message.lower()
    if (
        (
            "recallloom helper scripts require python " in lowered
            and "current interpreter is " in lowered
        )
        or "runtime bootstrap failed" in message
        or "minimum_python_version" in message
    ):
        return "python_runtime_unavailable"
    if helper_name == "manage_entry_bridge.py" and "attached-text safety scan" in message:
        return "attach_scan_blocked"
    if "No RecallLoom project root found." in message:
        return "no_project_root"
    if (
        "does not look like a project root" in lowered
        or "target path does not exist" in lowered
        or "target path is not a directory" in lowered
    ):
        return "not_project_root"
    if (
        "conflicting recallloom storage roots" in lowered
        or "different storage mode" in lowered
        or "conflicting recallloom sidecar" in lowered
        or "conflicting or partial recallloom sidecar" in lowered
    ):
        return "dual_sidecar_conflict"
    if "rerun preflight before writing" in lowered or "rerun preflight before appending" in lowered:
        return "stale_write_context"
    if "allow-historical" in lowered or "non-latest daily log" in lowered:
        return "historical_append_requires_confirmation"
    if (
        "missing required file" in lowered
        or "missing required file-state" in lowered
        or "invalid state.json" in lowered
        or "missing required section markers" in lowered
        or "duplicate section markers" in lowered
        or "unknown section markers" in lowered
        or any(token in lowered for token in ("partial", "damaged", "symlink", "non-directory"))
    ):
        return "malformed_managed_file" if "section markers" in lowered else "damaged_sidecar"
    return None


def _normalize_helper_error(helper_name: str, payload: dict) -> dict:
    normalized = dict(payload)
    if normalized.get("blocked_reason"):
        return normalized
    message = normalized.get("error")
    if not isinstance(message, str):
        return normalized
    reason = _infer_helper_failure_reason(helper_name, message)
    if reason is None:
        return normalized
    normalized.update(_contract_payload(reason, error=message))
    return normalized


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
        if isinstance(parsed_error, dict):
            parsed_error = _normalize_helper_error(helper_name, parsed_error)
        if json_mode_on_failure:
            if parsed_error is not None:
                print(json.dumps(parsed_error, ensure_ascii=False, indent=2))
                raise SystemExit(proc.returncode)
            if proc.stdout:
                print(proc.stdout, end="")
                raise SystemExit(proc.returncode)
            message = proc.stderr.strip() or f"{helper_name} failed."
            reason = _infer_helper_failure_reason(helper_name, message) or "damaged_sidecar"
            exit_with_cli_error(
                parser,
                json_mode=True,
                exit_code=proc.returncode,
                message=message,
                payload=_contract_payload(reason, error=message),
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
            payload=_contract_payload(
                _infer_helper_failure_reason(helper_name, error_message) or "damaged_sidecar",
                error=error_message,
            ),
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        message = f"{helper_name} returned invalid JSON: {exc}"
        exit_with_cli_error(
            parser,
            json_mode=True,
            exit_code=2,
            message=message,
            payload=_contract_payload("registry_contract_invalid", error=message),
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
    actions = ["rl-resume", "rl-status"]
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


def _status_like_helper_args(args: argparse.Namespace) -> list[str]:
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
    return helper_args


def _resume_ready(payload: dict) -> bool:
    if payload.get("continuity_confidence") == "broken":
        return False
    if payload.get("continuity_state") == "initialized_empty_shell":
        return False
    return True


def _resume_payload(payload: dict) -> dict:
    result = dict(payload)
    result["command"] = "resume"
    result["routing_target"] = "rl-resume"
    result["resume_ready"] = _resume_ready(result)
    snapshot = result.get("continuity_snapshot")
    if isinstance(snapshot, dict):
        result["continuity_snapshot"] = {**snapshot, "task_type": "resume_checkpoint"}
    return result


def _print_resume_summary(payload: dict) -> None:
    print(f"RecallLoom resume target: {payload['project_root']}")
    print("Routing target: rl-resume")
    print(f"Resume ready: {'yes' if payload['resume_ready'] else 'no'}")
    print(f"Continuity confidence: {payload.get('continuity_confidence')}")
    print(f"Continuity state: {payload.get('continuity_state')}")
    print("Recommended actions:")
    for action in payload.get("recommended_actions", []):
        print(f"  - {action}")
    workday = payload.get("workday")
    if isinstance(workday, dict):
        guidance = describe_workday_guidance(workday, always_show=False)
        if guidance:
            print(f"Workday guidance: {guidance}")


def _handle_init(parser, args: argparse.Namespace, *, support: dict) -> None:
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
        message = "init_context.py returned an incomplete payload."
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=message,
            payload=_contract_payload("registry_contract_invalid", error=message),
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
            message = "--bridge requires --yes. Bridge application stays explicit."
            exit_with_cli_error(
                parser,
                json_mode=args.json,
                exit_code=2,
                message=message,
                payload=_contract_payload("invalid_prepared_input", error=message),
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
        "package_support": support,
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
        exit_with_cli_error(
            parser,
            json_mode=getattr(args, "json", False),
            exit_code=2,
            message=str(exc),
            payload=_contract_payload("python_runtime_unavailable"),
        )
    support = enforce_package_support_gate(
        parser,
        json_mode=getattr(args, "json", False),
        action_name=f"recallloom.py {args.command}",
        action_level=action_level_for_dispatcher(args.command),
    )

    if args.command == "init":
        _handle_init(parser, args, support=support)
        return

    if args.command == "validate":
        if args.json:
            payload = _run_helper_json(
                parser,
                helper_name="validate_context.py",
                helper_args=[args.target],
                json_mode_on_failure=True,
            )
            payload["package_support"] = support
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _run_helper_passthrough(helper_name="validate_context.py", helper_args=[args.target])
        return

    if args.command in {"status", "resume"}:
        helper_args = _status_like_helper_args(args)
        if args.json:
            payload = _run_helper_json(
                parser,
                helper_name="summarize_continuity_status.py",
                helper_args=helper_args,
                json_mode_on_failure=True,
            )
            if args.command == "resume":
                payload = _resume_payload(payload)
            payload["package_support"] = support
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            if args.command == "resume":
                payload = _run_helper_json(
                    parser,
                    helper_name="summarize_continuity_status.py",
                    helper_args=helper_args,
                    json_mode_on_failure=False,
                )
                _print_resume_summary(_resume_payload(payload))
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
            payload["package_support"] = support
            print(json.dumps(payload, ensure_ascii=False, indent=2))
        else:
            _run_helper_passthrough(helper_name="manage_entry_bridge.py", helper_args=helper_args)
        return

    raise ConfigContractError(f"Unknown command: {args.command}")


if __name__ == "__main__":
    main()
