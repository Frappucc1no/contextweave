#!/usr/bin/env python3
"""Initialize a ContextWeave file structure in a target project."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from _common import (
    bridge_block_integrity,
    ConfigContractError,
    DEFAULT_STORAGE_MODE,
    DEFAULT_WORKSPACE_LANGUAGE,
    EnvironmentContractError,
    exit_with_cli_error,
    FILE_KEYS,
    LockBusyError,
    SUPPORTED_STORAGE_MODES,
    SUPPORTED_WORKSPACE_LANGUAGES,
    VISIBLE_STORAGE_MODE,
    config_path_for_mode,
    config_payload,
    ensure_git_exclude_entry,
    ensure_supported_python_version,
    initial_workspace_state,
    latest_active_daily_log,
    load_and_validate_config,
    load_workspace_state,
    managed_file_contract_issue,
    now_iso_timestamp,
    read_text,
    render_template,
    restore_text_snapshot,
    ROOT_ENTRY_CANDIDATES,
    storage_root_for_mode,
    today_iso,
    MANAGED_ASSET_REQUIRED_DIRECTORIES,
    MANAGED_ASSET_REQUIRED_FILES,
    unknown_storage_assets,
    validate_iso_date,
    validate_storage_mode,
    validate_tool_name,
    validate_workspace_language,
    workspace_write_lock,
    write_text,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Initialize a ContextWeave file structure in a project directory."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default=".",
        help="Project root directory to initialize. Defaults to the current working directory.",
    )
    parser.add_argument(
        "--tool-name",
        default="ContextWeave",
        help="Tool name used in generated metadata such as the rolling summary marker.",
    )
    parser.add_argument(
        "--date",
        default=today_iso(),
        help="Date to use for generated metadata and optional daily log file.",
    )
    parser.add_argument(
        "--storage-mode",
        default=DEFAULT_STORAGE_MODE,
        choices=sorted(SUPPORTED_STORAGE_MODES),
        help="Storage layout mode. Defaults to hidden sidecar mode.",
    )
    parser.add_argument(
        "--workspace-language",
        default=DEFAULT_WORKSPACE_LANGUAGE,
        choices=sorted(SUPPORTED_WORKSPACE_LANGUAGES),
        help="Language used for generated workspace files.",
    )
    parser.add_argument(
        "--create-daily-log",
        action="store_true",
        help="Optionally create today's daily log scaffold during initialization.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Apply first-time initialization writes even if a managed file path already exists; reruns on a healthy workspace remain idempotent and do not rebuild it.",
    )
    parser.add_argument(
        "--skip-git-exclude",
        action="store_true",
        help="Do not add .contextweave/ to .git/info/exclude when using hidden mode in a git repo.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print a JSON summary instead of human-readable output.",
    )
    return parser


def write_if_needed(path: Path, text: str, force: bool, created: list[str], skipped: list[str]) -> None:
    if path.exists() and not force:
        skipped.append(str(path))
        return
    write_text(path, text)
    created.append(str(path))


def bridge_state_snapshot(workspace, state: dict, timestamp: str) -> tuple[dict, bool]:
    latest_daily_log = latest_active_daily_log(workspace.storage_root / "daily_logs")
    next_entries: dict[str, dict] = {}
    changed = False
    for rel_path in ROOT_ENTRY_CANDIDATES:
        target = workspace.project_root / rel_path
        if not target.is_file():
            continue
        text = read_text(target)
        ok, reason = bridge_block_integrity(text)
        if not ok:
            raise ConfigContractError(
                f"Refusing to initialize because {target} contains a malformed managed bridge block ({reason})."
            )
        has_bridge_block = "<!-- ContextWeave managed bridge start -->" in text
        rel_key = str(rel_path)
        if has_bridge_block:
            next_entries[rel_key] = {
                "update_protocol_revision_seen": state["update_protocol_revision"],
                "latest_daily_log_seen": (
                    str(latest_daily_log.relative_to(workspace.storage_root))
                    if latest_daily_log is not None
                    else None
                ),
                "updated_at": timestamp,
            }
    if next_entries != state.get("bridged_entries", {}):
        changed = True
    state["bridged_entries"] = next_entries
    return state, changed


def rollback_init_writes(file_snapshots: list[tuple[Path, bool, str]], created_dirs: list[Path]) -> None:
    for path, existed, text in reversed(file_snapshots):
        restore_text_snapshot(path, existed=existed, text=text)
    for directory in reversed(created_dirs):
        try:
            directory.rmdir()
        except (FileNotFoundError, OSError):
            pass


def existing_storage_issue(
    *,
    storage_root: Path,
    storage_mode: str,
    workspace_language: str,
) -> str | None:
    if not storage_root.exists():
        return None
    if not storage_root.is_dir():
        return f"Refusing to initialize because the storage root path already exists as a non-directory: {storage_root}"

    has_content = any(storage_root.iterdir())
    if not has_content:
        return None

    unknown_assets = unknown_storage_assets(storage_root)
    if unknown_assets:
        return (
            "Refusing to initialize because the storage root already contains non-managed assets:\n"
            + "\n".join(str(path) for path in unknown_assets)
        )

    config_path = storage_root / FILE_KEYS["config"]
    if not config_path.is_file():
        return (
            "Refusing to initialize because the storage root already contains files but no valid config.json. "
            "This looks like a partial or non-ContextWeave sidecar."
        )

    try:
        existing_config = load_and_validate_config(config_path, storage_mode)
    except ConfigContractError as exc:
        return (
            "Refusing to initialize because the existing storage root has an invalid config.json. "
            f"Details: {exc}"
        )

    state_path = storage_root / FILE_KEYS["state"]
    if not state_path.is_file():
        return (
            "Refusing to initialize because the existing storage root is missing required state.json. "
            "This looks like a partial or damaged ContextWeave sidecar."
        )
    try:
        load_workspace_state(state_path)
    except ConfigContractError as exc:
        return (
            "Refusing to initialize because the existing storage root has an invalid state.json. "
            f"Details: {exc}"
        )

    if existing_config["workspace_language"] != workspace_language:
        return (
            "Refusing to initialize because the existing workspace uses a different workspace_language "
            f"({existing_config['workspace_language']} vs requested {workspace_language})."
        )

    required_files = {
        rel_path: storage_root / rel_path
        for rel_path in MANAGED_ASSET_REQUIRED_FILES
        if rel_path not in {FILE_KEYS["config"], FILE_KEYS["state"]}
    }
    missing_files = [name for name, path in required_files.items() if not path.is_file()]
    if missing_files:
        return (
            "Refusing to initialize because the existing storage root is missing required managed files "
            "for a healthy workspace: "
            + ", ".join(missing_files)
            + ". This looks like a partial or damaged ContextWeave sidecar."
        )

    required_dirs = {rel_path: storage_root / rel_path for rel_path in MANAGED_ASSET_REQUIRED_DIRECTORIES}
    missing_dirs = [name for name, path in required_dirs.items() if not path.is_dir()]
    if missing_dirs:
        return (
            "Refusing to initialize because the existing storage root is missing required managed directories "
            "for a healthy workspace: "
            + ", ".join(missing_dirs)
            + ". This looks like a partial or damaged ContextWeave sidecar."
        )

    contract_checks = [
        (
            storage_root / FILE_KEYS["context_brief"],
            "context_brief",
            existing_config["workspace_language"],
            existing_config["protocol_version"],
        ),
        (
            storage_root / FILE_KEYS["rolling_summary"],
            "rolling_summary",
            existing_config["workspace_language"],
            existing_config["protocol_version"],
        ),
    ]
    update_protocol_path = storage_root / FILE_KEYS["update_protocol"]
    if update_protocol_path.exists():
        contract_checks.append(
            (
                update_protocol_path,
                "update_protocol",
                existing_config["workspace_language"],
                existing_config["protocol_version"],
            )
        )
    for path, file_key, expected_language, expected_version in contract_checks:
        issue = managed_file_contract_issue(
            path,
            file_key=file_key,
            workspace_language=expected_language,
            expected_protocol_version=expected_version,
        )
        if issue is not None:
            return (
                "Refusing to initialize because the existing storage root contains a damaged managed file. "
                f"Details: {issue}"
            )

    return None


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    created_dirs: list[Path] = []
    file_snapshots: list[tuple[Path, bool, str]] = []
    exclude_snapshot: tuple[Path, bool, str] | None = None
    try:
        ensure_supported_python_version()
    except EnvironmentContractError as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload={"project_root": str(Path(args.target).expanduser().resolve()), "initialized": False},
        )

    project_root = Path(args.target).expanduser().resolve()
    project_root.mkdir(parents=True, exist_ok=True)

    if not validate_iso_date(args.date):
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Invalid --date value: {args.date}. Expected YYYY-MM-DD.",
            payload={"project_root": str(project_root), "initialized": False},
        )

    storage_mode = validate_storage_mode(args.storage_mode)
    workspace_language = validate_workspace_language(args.workspace_language)
    try:
        tool_name = validate_tool_name(args.tool_name)
    except ConfigContractError as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload={"project_root": str(project_root), "initialized": False},
        )

    try:
        with workspace_write_lock(project_root, "init_context.py"):
            opposite_mode = VISIBLE_STORAGE_MODE if storage_mode == DEFAULT_STORAGE_MODE else DEFAULT_STORAGE_MODE
            opposite_root = storage_root_for_mode(project_root, opposite_mode)
            opposite_config = config_path_for_mode(project_root, opposite_mode)
            if opposite_config.exists():
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        "A ContextWeave workspace already exists in a different storage mode for this project. "
                        "Remove it first or keep using the existing mode."
                    ),
                    payload={"project_root": str(project_root), "initialized": False},
                )
            if opposite_root.exists():
                if opposite_root.is_file():
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            "A path for the opposite storage mode already exists and is not a directory. "
                            "Remove it before initializing this project."
                        ),
                        payload={"project_root": str(project_root), "initialized": False},
                    )
                if any(opposite_root.iterdir()):
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            "A non-empty storage root already exists for the opposite storage mode. "
                            "This looks like a conflicting or partial sidecar. Remove it before initializing this project."
                        ),
                        payload={"project_root": str(project_root), "initialized": False},
                    )

            storage_root = storage_root_for_mode(project_root, storage_mode)
            if storage_root.exists() and not storage_root.is_dir():
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=(
                        f"Refusing to initialize because the storage root path already exists as a non-directory: {storage_root}"
                    ),
                    payload={"project_root": str(project_root), "initialized": False},
                )
            issue = existing_storage_issue(
                storage_root=storage_root,
                storage_mode=storage_mode,
                workspace_language=workspace_language,
            )
            if issue is not None:
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=issue,
                    payload={"project_root": str(project_root), "initialized": False},
                )

            existing_valid_storage = storage_root.exists() and any(storage_root.iterdir())
            if existing_valid_storage:
                state_path = storage_root / FILE_KEYS["state"]
                state = load_workspace_state(state_path)
                requested_daily_log = storage_root / "daily_logs" / f"{args.date}.md"
                if args.create_daily_log and not requested_daily_log.exists():
                    exit_with_cli_error(
                        parser,
                        json_mode=args.json,
                        exit_code=2,
                        message=(
                            "Refusing to create a new daily log during re-initialization of an existing workspace. "
                            "Use append_daily_log_entry.py for new milestone entries instead."
                        ),
                        payload={"project_root": str(project_root), "initialized": False},
                    )

                git_exclude_updated = False
                if storage_mode == DEFAULT_STORAGE_MODE and not args.skip_git_exclude:
                    git_exclude_updated = ensure_git_exclude_entry(project_root)
                    if git_exclude_updated and state.get("git_exclude_mode") != "managed":
                        state["git_exclude_mode"] = "managed"

                state, state_reconciled = bridge_state_snapshot(
                    workspace=type(
                        "InitWorkspace",
                        (),
                        {
                            "project_root": project_root,
                            "storage_root": storage_root,
                            "update_protocol_revision": state["update_protocol_revision"],
                        },
                    )(),
                    state=state,
                    timestamp=now_iso_timestamp(),
                )
                created: list[str] = []
                if state_reconciled:
                    write_text(state_path, json.dumps(state, ensure_ascii=False, indent=2) + "\n")
                    created.append(str(state_path))

                skipped: list[str] = []
                created_set = set(created)
                for path in (
                    storage_root / FILE_KEYS["context_brief"],
                    storage_root / FILE_KEYS["rolling_summary"],
                    storage_root / FILE_KEYS["update_protocol"],
                    config_path_for_mode(project_root, storage_mode),
                    storage_root / FILE_KEYS["state"],
                ):
                    if path.exists() and str(path) not in created_set:
                        skipped.append(str(path))
                if args.create_daily_log and requested_daily_log.exists():
                    skipped.append(str(requested_daily_log))

                summary = {
                    "project_root": str(project_root),
                    "storage_root": str(storage_root),
                    "storage_mode": storage_mode,
                    "workspace_language": workspace_language,
                    "created": created,
                    "skipped": skipped,
                    "daily_log_created": False,
                    "config_created": False,
                    "git_exclude_updated": git_exclude_updated,
                    "already_initialized": True,
                    "state_reconciled": state_reconciled,
                }
                if args.json:
                    print(json.dumps(summary, ensure_ascii=False, indent=2))
                else:
                    print(f"ContextWeave is already initialized in {project_root}")
                    print(f"Storage mode: {storage_mode}")
                    print(f"Workspace language: {workspace_language}")
                    print(f"Storage root: {storage_root}")
                    if skipped:
                        print("Skipped existing:")
                        for item in skipped:
                            print(f"  - {item}")
                    if git_exclude_updated:
                        print("Updated .git/info/exclude for .contextweave/")
                return

            storage_root_preexisted = storage_root.exists()
            storage_root.mkdir(parents=True, exist_ok=True)
            required_directory_paths = [
                storage_root / rel_path for rel_path in MANAGED_ASSET_REQUIRED_DIRECTORIES
            ]
            daily_logs_dir = storage_root / "daily_logs"
            preexisting_dirs = {path: path.exists() for path in required_directory_paths}
            for directory in sorted(required_directory_paths, key=lambda item: len(item.parts)):
                directory.mkdir(parents=True, exist_ok=True)
            if not storage_root_preexisted:
                created_dirs.append(storage_root)
            for directory in required_directory_paths:
                if not preexisting_dirs[directory]:
                    created_dirs.append(directory)

            created: list[str] = []
            skipped: list[str] = []

            timestamp = now_iso_timestamp()
            workspace_revision = 1

            managed_files = {
                storage_root / FILE_KEYS["context_brief"]: render_template(
                    "context_brief",
                    tool_name=tool_name,
                    day=args.date,
                    language=workspace_language,
                    timestamp=timestamp,
                    workspace_revision=workspace_revision,
                ),
                storage_root / FILE_KEYS["rolling_summary"]: render_template(
                    "rolling_summary",
                    tool_name=tool_name,
                    day=args.date,
                    language=workspace_language,
                    timestamp=timestamp,
                    workspace_revision=workspace_revision,
                ),
                storage_root / FILE_KEYS["update_protocol"]: render_template(
                    "update_protocol",
                    tool_name=tool_name,
                    day=args.date,
                    language=workspace_language,
                    timestamp=timestamp,
                    workspace_revision=workspace_revision,
                ),
            }

            if args.create_daily_log:
                managed_files[daily_logs_dir / f"{args.date}.md"] = render_template(
                    "daily_log",
                    tool_name=tool_name,
                    day=args.date,
                    language=workspace_language,
                    timestamp=timestamp,
                    workspace_revision=workspace_revision,
                )

            for path, text in managed_files.items():
                if path.exists() and not args.force:
                    skipped.append(str(path))
                    continue
                existed = path.exists()
                previous_text = read_text(path) if existed else ""
                write_text(path, text)
                file_snapshots.append((path, existed, previous_text))
                created.append(str(path))

            config_created = False
            config_path = config_path_for_mode(project_root, storage_mode)
            payload = config_payload(
                storage_mode=storage_mode,
                workspace_language=workspace_language,
                created_by=tool_name,
                created_at=timestamp,
            )
            if config_path.exists() and not args.force:
                skipped.append(str(config_path))
            else:
                existed = config_path.exists()
                previous_text = read_text(config_path) if existed else ""
                write_text(config_path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
                file_snapshots.append((config_path, existed, previous_text))
                created.append(str(config_path))
                config_created = True

            git_exclude_updated = False
            if storage_mode == DEFAULT_STORAGE_MODE and not args.skip_git_exclude:
                exclude_path = project_root / ".git" / "info" / "exclude"
                exclude_snapshot = (
                    exclude_path,
                    exclude_path.exists(),
                    read_text(exclude_path) if exclude_path.exists() else "",
                )
                git_exclude_updated = ensure_git_exclude_entry(project_root)

            git_exclude_mode = (
                "managed"
                if storage_mode == DEFAULT_STORAGE_MODE and git_exclude_updated
                else "skipped"
                if storage_mode == DEFAULT_STORAGE_MODE
                else "not_applicable"
            )

            state_path = storage_root / FILE_KEYS["state"]
            state_payload = initial_workspace_state(
                tool_name=tool_name,
                timestamp=timestamp,
                git_exclude_mode=git_exclude_mode,
            )
            try:
                state_payload, state_reconciled = bridge_state_snapshot(
                    workspace=type(
                        "InitWorkspace",
                        (),
                        {
                            "project_root": project_root,
                            "storage_root": storage_root,
                            "update_protocol_revision": state_payload["update_protocol_revision"],
                        },
                    )(),
                    state=state_payload,
                    timestamp=timestamp,
                )
            except ConfigContractError as exc:
                rollback_init_writes(file_snapshots, created_dirs)
                if exclude_snapshot is not None:
                    restore_text_snapshot(
                        exclude_snapshot[0], existed=exclude_snapshot[1], text=exclude_snapshot[2]
                    )
                exit_with_cli_error(
                    parser,
                    json_mode=args.json,
                    exit_code=2,
                    message=str(exc),
                    payload={"project_root": str(project_root), "initialized": False},
                )
            if state_path.exists() and not args.force:
                skipped.append(str(state_path))
            else:
                existed = state_path.exists()
                previous_text = read_text(state_path) if existed else ""
                write_text(state_path, json.dumps(state_payload, ensure_ascii=False, indent=2) + "\n")
                file_snapshots.append((state_path, existed, previous_text))
                created.append(str(state_path))

            summary = {
                "project_root": str(project_root),
                "storage_root": str(storage_root),
                "storage_mode": storage_mode,
                "workspace_language": workspace_language,
                "created": created,
                "skipped": skipped,
                "daily_log_created": args.create_daily_log,
                "config_created": config_created,
                "git_exclude_updated": git_exclude_updated,
                "state_reconciled": state_reconciled,
            }
    except LockBusyError as exc:
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=3,
            message=str(exc),
            payload={"project_root": str(project_root), "initialized": False},
        )
    except ConfigContractError as exc:
        try:
            rollback_init_writes(file_snapshots, created_dirs)
        except OSError:
            pass
        if exclude_snapshot is not None:
            try:
                restore_text_snapshot(exclude_snapshot[0], existed=exclude_snapshot[1], text=exclude_snapshot[2])
            except OSError:
                pass
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=str(exc),
            payload={"project_root": str(project_root), "initialized": False},
        )
    except (OSError, UnicodeDecodeError) as exc:
        try:
            rollback_init_writes(file_snapshots, created_dirs)
        except OSError:
            pass
        if "exclude_snapshot" in locals() and exclude_snapshot is not None:
            try:
                restore_text_snapshot(exclude_snapshot[0], existed=exclude_snapshot[1], text=exclude_snapshot[2])
            except OSError:
                pass
        exit_with_cli_error(
            parser,
            json_mode=args.json,
            exit_code=2,
            message=f"Filesystem error: {exc}",
            payload={"project_root": str(project_root), "initialized": False},
        )

    if args.json:
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        print(f"Initialized ContextWeave in {project_root}")
        print(f"Storage mode: {storage_mode}")
        print(f"Workspace language: {workspace_language}")
        print(f"Storage root: {storage_root}")
        if created:
            print("Created:")
            for item in created:
                print(f"  - {item}")
        if skipped:
            print("Skipped existing:")
            for item in skipped:
                print(f"  - {item}")
        if git_exclude_updated:
            print("Updated .git/info/exclude for .contextweave/")


if __name__ == "__main__":
    main()
