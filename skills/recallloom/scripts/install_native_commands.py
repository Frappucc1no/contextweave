#!/usr/bin/env python3
"""Render and install native command wrappers for supported host CLIs."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import shlex
import sys

from _common import (
    cli_failure_payload,
    cli_failure_payload_for_exception,
    ConfigContractError,
    EnvironmentContractError,
    enforce_package_support_gate,
    ensure_supported_python_version,
    exit_with_cli_error,
    now_iso_timestamp,
    public_json_payload,
    public_project_path,
    read_text,
    write_text,
)


SCRIPT_DIR = Path(__file__).resolve().parent
NATIVE_COMMAND_ROOT = SCRIPT_DIR.parent / "native_commands"
SUPPORTED_HOSTS = ("claude-code", "gemini-cli", "opencode")
SUPPORTED_SCOPES = ("project", "user")
MANAGED_MARKER_LABEL = "RecallLoom managed native command"
REQUIRED_NATIVE_COMMANDS = {
    "claude-code": {"rl-init.md", "rl-resume.md", "rl-status.md", "rl-validate.md"},
    "gemini-cli": {"rl-init.toml", "rl-resume.toml", "rl-status.toml", "rl-validate.toml"},
    "opencode": {"rl-init.md", "rl-resume.md", "rl-status.md", "rl-validate.md"},
}
LEGACY_WRAPPER_SIGNATURES = {
    # v0.3.1-v0.3.2 shipped init/status/validate unmarked wrappers with these bodies.
    # v0.3.3 kept those bodies and added the same unmarked resume form.
    "claude-code": {
        "rl-init.md": """---
description: Initialize RecallLoom in the current project
disable-model-invocation: true
---

RecallLoom initialization result:

```!
__DISPATCHER_COMMAND__ init . --json
```

Summarize briefly:

- whether initialization succeeded
- the storage root
- the suggested next actions

Do not apply any bridge automatically.
""",
        "rl-resume.md": """---
description: Resume RecallLoom continuity for the current project
disable-model-invocation: true
---

RecallLoom resume:

```!
__DISPATCHER_COMMAND__ resume . --json
```

Summarize briefly:

- the continuity state
- the top recommended next actions
- the current workday recommendation
""",
        "rl-status.md": """---
description: Show RecallLoom continuity status for the current project
disable-model-invocation: true
---

RecallLoom status:

```!
__DISPATCHER_COMMAND__ status . --json
```

Summarize briefly:

- current continuity confidence
- the top recommended actions
- the current workday recommendation
""",
        "rl-validate.md": """---
description: Validate RecallLoom continuity files for the current project
disable-model-invocation: true
---

RecallLoom validation result:

```!
__DISPATCHER_COMMAND__ validate . --json
```

Summarize briefly:

- whether the workspace is valid
- any errors
- any warnings
""",
    },
    "gemini-cli": {
        "rl-init.toml": '''description = "Initialize RecallLoom in the current project"
prompt = """
RecallLoom initialization result:
!{__DISPATCHER_COMMAND__ init . --json}

Summarize briefly:
- whether initialization succeeded
- the storage root
- the suggested next actions

Do not apply any bridge automatically.
"""
''',
        "rl-resume.toml": '''description = "Resume RecallLoom continuity for the current project"
prompt = """
RecallLoom resume:
!{__DISPATCHER_COMMAND__ resume . --json}

Summarize briefly:
- the continuity state
- the top recommended next actions
- the current workday recommendation
"""
''',
        "rl-status.toml": '''description = "Show RecallLoom continuity status for the current project"
prompt = """
RecallLoom status:
!{__DISPATCHER_COMMAND__ status . --json}

Summarize briefly:
- current continuity confidence
- the top recommended actions
- the current workday recommendation
"""
''',
        "rl-validate.toml": '''description = "Validate RecallLoom continuity files for the current project"
prompt = """
RecallLoom validation result:
!{__DISPATCHER_COMMAND__ validate . --json}

Summarize briefly:
- whether the workspace is valid
- any errors
- any warnings
"""
''',
    },
    "opencode": {
        "rl-init.md": """---
description: Initialize RecallLoom in the current project
---

RecallLoom initialization result:

!`__DISPATCHER_COMMAND__ init . --json`

Summarize briefly:

- whether initialization succeeded
- the storage root
- the suggested next actions

Do not apply any bridge automatically.
""",
        "rl-resume.md": """---
description: Resume RecallLoom continuity for the current project
---

RecallLoom resume:

!`__DISPATCHER_COMMAND__ resume . --json`

Summarize briefly:

- the continuity state
- the top recommended next actions
- the current workday recommendation
""",
        "rl-status.md": """---
description: Show RecallLoom continuity status for the current project
---

RecallLoom status:

!`__DISPATCHER_COMMAND__ status . --json`

Summarize briefly:

- current continuity confidence
- the top recommended actions
- the current workday recommendation
""",
        "rl-validate.md": """---
description: Validate RecallLoom continuity files for the current project
---

RecallLoom validation result:

!`__DISPATCHER_COMMAND__ validate . --json`

Summarize briefly:

- whether the workspace is valid
- any errors
- any warnings
""",
    },
}


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
            'for example: "/abs/path/to/python3" "/abs/path/to/recallloom.py"'
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


def current_python_command() -> str:
    candidate = Path(sys.executable).expanduser()
    if candidate.is_absolute():
        return f'"{candidate}"'
    try:
        resolved = candidate.resolve()
    except OSError:
        resolved = candidate
    return f'"{resolved}"'


def host_command_dir(host: str, *, scope: str, project: Path) -> Path:
    if host == "claude-code":
        return (project / ".claude" / "commands") if scope == "project" else (Path.home() / ".claude" / "commands")
    if host == "gemini-cli":
        return (project / ".gemini" / "commands") if scope == "project" else (Path.home() / ".gemini" / "commands")
    if host == "opencode":
        return (project / ".opencode" / "commands") if scope == "project" else (Path.home() / ".config" / "opencode" / "commands")
    raise AssertionError(f"Unsupported host: {host}")


def detect_dispatcher_command(project: Path, *, scope: str) -> str:
    python_command = current_python_command()
    candidates = [
        project / "skills" / "recallloom" / "scripts" / "recallloom.py",
        project / ".claude" / "skills" / "recallloom" / "scripts" / "recallloom.py",
        project / ".agents" / "skills" / "recallloom" / "scripts" / "recallloom.py",
        SCRIPT_DIR / "recallloom.py",
    ]
    for candidate in candidates:
        if candidate.is_file():
            if scope == "project":
                try:
                    rel = candidate.relative_to(project)
                    return f'{python_command} "{rel.as_posix()}"'
                except ValueError:
                    return f'{python_command} "{candidate}"'
            return f'{python_command} "{candidate}"'
    raise ConfigContractError(
        "Could not auto-detect a RecallLoom dispatcher path. Re-run with --dispatcher-command."
    )


def classify_project_scope_dispatcher_path(dispatcher_command: str, project: Path) -> tuple[str, str | None]:
    try:
        tokens = shlex.split(dispatcher_command)
    except ValueError:
        return ("unknown", None)
    if not tokens:
        return ("unknown", None)

    script_token = next((token for token in reversed(tokens) if token.endswith("recallloom.py")), None)
    if script_token is None:
        return ("unknown", None)

    candidate = Path(script_token).expanduser()
    if not candidate.is_absolute():
        return ("relative_project_dispatcher", None)

    try:
        resolved = candidate.resolve()
        project_resolved = project.resolve()
    except OSError:
        resolved = candidate
        project_resolved = project
    try:
        resolved.relative_to(project_resolved)
    except ValueError:
        return (
            "absolute_external_dispatcher",
            "project scope only stays naturally portable when the dispatcher lives inside the project; the current dispatcher command uses an absolute path outside the project.",
        )
    return (
        "absolute_project_dispatcher",
        "project scope is installed in-project, but the generated dispatcher command still uses an absolute path and will drift if the project moves.",
    )


def escape_toml_basic_string_fragment(value: str) -> str:
    """Escape text that will be interpolated inside a TOML basic string."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\b", "\\b")
        .replace("\t", "\\t")
        .replace("\n", "\\n")
        .replace("\f", "\\f")
        .replace("\r", "\\r")
    )


def dispatcher_command_for_host_template(host: str, dispatcher_command: str) -> str:
    if host == "gemini-cli":
        return escape_toml_basic_string_fragment(dispatcher_command)
    return dispatcher_command


def render_templates_for_host(host: str, *, dispatcher_command: str) -> dict[str, str]:
    template_dir = NATIVE_COMMAND_ROOT / host
    if not template_dir.is_dir():
        raise ConfigContractError(f"Missing native command template directory: {template_dir}")
    rendered: dict[str, str] = {}
    template_dispatcher_command = dispatcher_command_for_host_template(host, dispatcher_command)
    for template_path in sorted(template_dir.iterdir()):
        if not template_path.is_file() or not template_path.name.endswith(".tmpl"):
            continue
        target_name = template_path.name[:-5]
        rendered[target_name] = append_managed_marker(
            read_text(template_path).replace("__DISPATCHER_COMMAND__", template_dispatcher_command),
            host=host,
            filename=target_name,
        )
    if not rendered:
        raise ConfigContractError(f"No native command templates found for host {host}.")
    missing_required = sorted(REQUIRED_NATIVE_COMMANDS[host] - set(rendered))
    if missing_required:
        raise ConfigContractError(
            f"Missing required native command templates for host {host}: {', '.join(missing_required)}"
        )
    return rendered


def command_id_for_filename(filename: str) -> str:
    command_id = Path(filename).stem
    if not any(command_id == Path(required_name).stem for host_names in REQUIRED_NATIVE_COMMANDS.values() for required_name in host_names):
        raise ConfigContractError(f"Unsupported native command wrapper filename: {filename}")
    return command_id


def managed_marker_for_wrapper(host: str, filename: str) -> str:
    command_id = command_id_for_filename(filename)
    marker_body = f"{MANAGED_MARKER_LABEL}: host={host}; command={command_id}"
    if host == "gemini-cli":
        return f"# {marker_body}"
    return f"<!-- {marker_body} -->"


def append_managed_marker(content: str, *, host: str, filename: str) -> str:
    marker = managed_marker_for_wrapper(host, filename)
    stripped = content.rstrip("\n")
    if marker in stripped:
        return stripped + "\n"
    return f"{stripped}\n\n{marker}\n"


def has_managed_marker(host: str, filename: str, existing_content: str) -> bool:
    return managed_marker_for_wrapper(host, filename) in existing_content


def legacy_template_matcher_for_host(host: str, filename: str) -> re.Pattern[str]:
    host_signatures = LEGACY_WRAPPER_SIGNATURES.get(host)
    if host_signatures is None:
        raise ConfigContractError(f"Unsupported host: {host}")
    legacy_template_text = host_signatures.get(filename)
    if legacy_template_text is None:
        raise ConfigContractError(f"Missing legacy native command signature for host={host} file={filename}")
    pattern = re.escape(legacy_template_text).replace(re.escape("__DISPATCHER_COMMAND__"), r".+?")
    return re.compile(rf"\A{pattern}\Z", re.DOTALL)


def is_legacy_recallloom_managed_wrapper(host: str, filename: str, existing_content: str) -> bool:
    return legacy_template_matcher_for_host(host, filename).fullmatch(existing_content) is not None


def is_recallloom_managed_wrapper(host: str, filename: str, existing_content: str) -> bool:
    return has_managed_marker(host, filename, existing_content) or is_legacy_recallloom_managed_wrapper(
        host,
        filename,
        existing_content,
    )


def write_wrapper_content(destination: Path, content: str) -> None:
    if destination.is_symlink():
        write_text(destination.resolve(strict=True), content)
        return
    write_text(destination, content)


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
        is_symlink = destination.is_symlink()
        existed = destination.exists() or is_symlink
        existing_content = read_text(destination) if existed and (destination.exists() or not is_symlink) else None
        changed = (not existed) or existing_content != content
        recallloom_managed = bool(
            existed and existing_content is not None and is_recallloom_managed_wrapper(host, filename, existing_content)
        )
        if existed and changed and is_symlink and not force:
            results.append(
                {
                    "file": str(destination),
                    "changed": True,
                    "applied": False,
                    "managed": recallloom_managed,
                    "symlink": True,
                    "reason": "exists_requires_force",
                }
            )
            continue
        if existed and changed and not force and not recallloom_managed:
            results.append(
                {
                    "file": str(destination),
                    "changed": True,
                    "applied": False,
                    "managed": False,
                    "symlink": is_symlink,
                    "reason": "exists_requires_force",
                }
            )
            continue
        applied_change = apply and changed
        if applied_change:
            write_wrapper_content(destination, content)
        results.append(
            {
                "file": str(destination),
                "changed": changed,
                "applied": applied_change,
                "managed": recallloom_managed,
                "symlink": is_symlink,
                "reason": (
                    "refreshed_managed"
                    if applied_change and recallloom_managed
                    else "written"
                    if applied_change
                    else "no_change"
                    if not changed
                    else "preview"
                ),
            }
        )

    return {
        "host": host,
        "scope": scope,
        "destination_dir": str(destination_dir),
        "dispatcher_command": dispatcher_command,
        "results": results,
    }


def public_dispatcher_command(command: str, *, project_root: Path) -> str:
    try:
        tokens = shlex.split(command)
    except ValueError:
        return command

    public_tokens: list[str] = []
    for token in tokens:
        if not token or token.startswith("-"):
            public_tokens.append(token)
            continue
        candidate = Path(token).expanduser()
        if not candidate.is_absolute() and "/" not in token and "\\" not in token:
            public_tokens.append(token)
            continue
        public_tokens.append(public_project_path(token, project_root=project_root) or candidate.name or token)
    return shlex.join(public_tokens)


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

    project = project_root(args.target)
    if not project.exists():
        message = f"Target path does not exist: {project}"
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=message,
            payload=cli_failure_payload(
                "not_project_root",
                error=message,
                details={"target_path": str(project)},
            ),
        )
    if not project.is_dir():
        message = f"Target path is not a directory: {project}"
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=message,
            payload=cli_failure_payload(
                "not_project_root",
                error=message,
                details={"target_path": str(project)},
            ),
        )

    try:
        dispatcher_command = args.dispatcher_command or detect_dispatcher_command(project, scope=args.scope)
    except ConfigContractError as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload=cli_failure_payload_for_exception(exc, default_reason="invalid_prepared_input"),
        )

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
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload=cli_failure_payload_for_exception(exc, default_reason="invalid_prepared_input"),
        )
    except (OSError, UnicodeDecodeError) as exc:
        message = f"Filesystem error: {exc}"
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=message,
            payload=cli_failure_payload("damaged_sidecar", error=message),
        )

    project_scope_path_stability = "not_applicable"
    project_scope_path_advisory = None
    if args.scope == "project":
        project_scope_path_stability, project_scope_path_advisory = classify_project_scope_dispatcher_path(
            dispatcher_command,
            project,
        )

    all_results = [result for host_payload in host_results for result in host_payload["results"]]
    changed_count = sum(1 for result in all_results if result["changed"])
    applied_count = sum(1 for result in all_results if result["applied"])
    requires_force_count = sum(1 for result in all_results if result["reason"] == "exists_requires_force")
    ok = not (args.yes and requires_force_count > 0)

    payload = {
        "ok": ok,
        "project_root": str(project),
        "scope": args.scope,
        "recommended_scope": "project",
        "scope_advisory": (
            "project scope is the recommended public default; user scope remains supported but is intentionally downgraded because it depends on a stable absolute dispatcher path and is easier to drift."
            if args.scope == "user"
            else "project scope is the recommended public default."
        ),
        "project_scope_path_stability": project_scope_path_stability,
        "project_scope_path_advisory": project_scope_path_advisory,
        "requested_apply": bool(args.yes),
        "applied": applied_count > 0,
        "result_counts": {
            "total": len(all_results),
            "changed": changed_count,
            "applied": applied_count,
            "requires_force": requires_force_count,
        },
        "generated_at": now_iso_timestamp(),
        "host_results": host_results,
        "note": (
            "Native command wrappers are local host integrations. "
            "They are convenience entrypoints for supported hosts, not a replacement for the RecallLoom skill package."
        ),
    }

    if args.json:
        public_payload = public_json_payload(payload, project_root=project)
        for host_payload in public_payload.get("host_results", []):
            if not isinstance(host_payload, dict):
                continue
            dispatcher_command = host_payload.get("dispatcher_command")
            if isinstance(dispatcher_command, str):
                host_payload["dispatcher_command"] = public_dispatcher_command(
                    dispatcher_command,
                    project_root=project,
                )
        print(json.dumps(public_payload, ensure_ascii=False, indent=2))
    else:
        if not args.yes:
            print(f"Previewed native RecallLoom command wrappers for scope={args.scope}")
        elif not ok:
            print(f"Native RecallLoom command wrapper refresh requires --force for some existing files (scope={args.scope})")
        elif applied_count > 0:
            print(f"Installed native RecallLoom command wrappers for scope={args.scope}")
        else:
            print(f"Native RecallLoom command wrappers already matched the current render for scope={args.scope}")
        if args.scope == "user":
            print("Advisory: project scope remains the recommended public default; user scope is supported but downgraded.")
        elif project_scope_path_advisory is not None:
            print(f"Advisory: {project_scope_path_advisory}")
        for host_payload in host_results:
            print(f"- {host_payload['host']}: {host_payload['destination_dir']}")
            for result in host_payload["results"]:
                status = "changed" if result["changed"] else "unchanged"
                if result["reason"] == "exists_requires_force":
                    status = "requires --force"
                print(f"  - {Path(result['file']).name}: {status}")

    raise SystemExit(0 if ok else 1)


if __name__ == "__main__":
    main()
