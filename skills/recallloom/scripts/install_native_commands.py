#!/usr/bin/env python3
"""Render and install native command wrappers for supported host CLIs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    ConfigContractError,
    EnvironmentContractError,
    ensure_supported_python_version,
    exit_with_cli_error,
    now_iso_timestamp,
    read_text,
    write_text,
)


SCRIPT_DIR = Path(__file__).resolve().parent
NATIVE_COMMAND_ROOT = SCRIPT_DIR.parent / "native_commands"
SUPPORTED_HOSTS = ("claude-code", "gemini-cli", "opencode")
SUPPORTED_SCOPES = ("project", "user")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Render and optionally install native RecallLoom command wrappers for supported host CLIs."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project root directory used for project-scoped command installation. Defaults to current directory.",
    )
    parser.add_argument(
        "--host",
        choices=list(SUPPORTED_HOSTS) + ["all"],
        required=True,
        help="Which host command format to install.",
    )
    parser.add_argument(
        "--scope",
        choices=SUPPORTED_SCOPES,
        default="project",
        help="Install commands into the project or user command directory. Defaults to project.",
    )
    parser.add_argument(
        "--dispatcher-command",
        help=(
            "Exact shell command prefix to invoke the RecallLoom dispatcher, "
            'for example: python "/abs/path/to/recallloom.py"'
        ),
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing command files.",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Apply the installation. Without this flag, the script runs in preview mode.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print structured JSON output.",
    )
    return parser


def project_root(path_raw: str) -> Path:
    return Path(path_raw).expanduser().resolve()


def host_command_dir(host: str, *, scope: str, project: Path) -> Path:
    if host == "claude-code":
        return (project / ".claude" / "commands") if scope == "project" else (Path.home() / ".claude" / "commands")
    if host == "gemini-cli":
        return (project / ".gemini" / "commands") if scope == "project" else (Path.home() / ".gemini" / "commands")
    if host == "opencode":
        return (project / ".opencode" / "commands") if scope == "project" else (Path.home() / ".config" / "opencode" / "commands")
    raise AssertionError(f"Unsupported host: {host}")


def detect_dispatcher_command(project: Path) -> str:
    candidates = [
        project / "skills" / "recallloom" / "scripts" / "recallloom.py",
        project / ".claude" / "skills" / "recallloom" / "scripts" / "recallloom.py",
        project / ".agents" / "skills" / "recallloom" / "scripts" / "recallloom.py",
        SCRIPT_DIR / "recallloom.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            try:
                rel = candidate.relative_to(project)
                return f'python "{rel.as_posix()}"'
            except ValueError:
                return f'python "{candidate}"'
    raise ConfigContractError(
        "Could not auto-detect a RecallLoom dispatcher path. Re-run with --dispatcher-command."
    )


def render_templates_for_host(host: str, *, dispatcher_command: str) -> dict[str, str]:
    template_dir = NATIVE_COMMAND_ROOT / host
    if not template_dir.is_dir():
        raise ConfigContractError(f"Missing native command template directory: {template_dir}")
    rendered: dict[str, str] = {}
    for template_path in sorted(template_dir.iterdir()):
        if not template_path.is_file() or not template_path.name.endswith(".tmpl"):
            continue
        target_name = template_path.name[:-5]
        rendered[target_name] = read_text(template_path).replace("__DISPATCHER_COMMAND__", dispatcher_command)
    if not rendered:
        raise ConfigContractError(f"No native command templates found for host {host}.")
    return rendered


def install_host(
    host: str,
    *,
    scope: str,
    project: Path,
    dispatcher_command: str,
    force: bool,
    apply: bool,
) -> dict:
    destination_dir = host_command_dir(host, scope=scope, project=project)
    rendered = render_templates_for_host(host, dispatcher_command=dispatcher_command)
    results = []

    for filename, content in rendered.items():
        destination = destination_dir / filename
        existed = destination.exists()
        changed = (not existed) or destination.read_text(encoding="utf-8") != content
        if existed and not force and changed:
            results.append(
                {
                    "file": str(destination),
                    "changed": True,
                    "applied": False,
                    "reason": "exists_requires_force",
                }
            )
            continue
        if apply:
            destination.parent.mkdir(parents=True, exist_ok=True)
            write_text(destination, content)
        results.append(
            {
                "file": str(destination),
                "changed": changed,
                "applied": apply,
                "reason": "written" if apply and changed else "no_change" if not changed else "preview",
            }
        )

    return {
        "host": host,
        "scope": scope,
        "destination_dir": str(destination_dir),
        "dispatcher_command": dispatcher_command,
        "results": results,
    }


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    project = project_root(args.target)
    if not project.exists():
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=f"Target path does not exist: {project}")

    try:
        dispatcher_command = args.dispatcher_command or detect_dispatcher_command(project)
    except ConfigContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    hosts = list(SUPPORTED_HOSTS) if args.host == "all" else [args.host]

    try:
        host_results = [
            install_host(
                host,
                scope=args.scope,
                project=project,
                dispatcher_command=dispatcher_command,
                force=args.force,
                apply=args.yes,
            )
            for host in hosts
        ]
    except ConfigContractError as exc:
        exit_with_cli_error(parser, json_mode=args.json, exit_code=2, message=str(exc))

    payload = {
        "ok": True,
        "project_root": str(project),
        "scope": args.scope,
        "applied": bool(args.yes),
        "generated_at": now_iso_timestamp(),
        "host_results": host_results,
        "note": (
            "Native command wrappers are local host integrations. "
            "They are convenience entrypoints for supported hosts, not a replacement for the RecallLoom skill package."
        ),
    }

    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        action = "Installed" if args.yes else "Previewed"
        print(f"{action} native RecallLoom command wrappers for scope={args.scope}")
        for host_payload in host_results:
            print(f"- {host_payload['host']}: {host_payload['destination_dir']}")
            for result in host_payload["results"]:
                status = "changed" if result["changed"] else "unchanged"
                if result["reason"] == "exists_requires_force":
                    status = "requires --force"
                print(f"  - {Path(result['file']).name}: {status}")


if __name__ == "__main__":
    main()
