#!/usr/bin/env python3
"""Protocol-level constants derived from the RecallLoom contract registry."""

from __future__ import annotations

from pathlib import Path, PurePosixPath
import re

from core.registry.loader import (
    load_contract_registry,
    load_contract_schema,
    resolve_contract_registry_path,
    resolve_contract_schema_path,
)

CONTRACT_REGISTRY_PATH = resolve_contract_registry_path()
CONTRACT_SCHEMA_PATH = resolve_contract_schema_path()
CONTRACT_BOOTSTRAP_ERROR: RuntimeError | None = None


def _install_fallback_contracts(exc: RuntimeError) -> None:
    global CONTRACT_BOOTSTRAP_ERROR
    global CONTRACT_SCHEMA
    global CONTRACT_REGISTRY
    global CURRENT_PROTOCOL_VERSION
    global SUPPORTED_PROTOCOL_VERSIONS
    global DEFAULT_WORKSPACE_LANGUAGE
    global SUPPORTED_WORKSPACE_LANGUAGES
    global SUPPORTED_STORAGE_MODES
    global SUPPORTED_DYNAMIC_ASSET_RULE_KINDS
    global FILE_KEYS
    global DAILY_LOG_PATH_PATTERN
    global DAILY_LOGS_DIRNAME
    global SECTION_KEYS
    global OPTIONAL_SECTION_KEYS
    global CONTEXT_BRIEF_RENDER_ORDER
    global LABELS
    global FILE_MARKER_TEMPLATE
    global FILE_STATE_MARKER_TEMPLATE
    global DAILY_LOG_ENTRY_MARKER_TEMPLATE
    global DAILY_LOG_SCAFFOLD_MARKER_TEMPLATE
    global LAST_WRITER_MARKER_TEMPLATE
    global LAST_WRITER_RE
    global FILE_STATE_RE
    global DAILY_LOG_ENTRY_RE
    global DAILY_LOG_SCAFFOLD_RE
    global FILE_MARKER_RE
    global SECTION_MARKER_RE
    global BRIDGE_START
    global BRIDGE_END
    global EXCLUDE_BLOCK_START
    global EXCLUDE_BLOCK_END
    global ROOT_ENTRY_CANDIDATES
    global ROOT_ENTRY_CANDIDATE_STRINGS

    CONTRACT_BOOTSTRAP_ERROR = exc
    CONTRACT_SCHEMA = {}
    CONTRACT_REGISTRY = {}
    CURRENT_PROTOCOL_VERSION = "1.0"
    SUPPORTED_PROTOCOL_VERSIONS = {"1.0"}
    DEFAULT_WORKSPACE_LANGUAGE = "en"
    SUPPORTED_WORKSPACE_LANGUAGES = {"en", "zh-CN"}
    SUPPORTED_STORAGE_MODES = {"hidden", "visible"}
    SUPPORTED_DYNAMIC_ASSET_RULE_KINDS = set()
    FILE_KEYS = {
        "config": "config.json",
        "state": "state.json",
        "context_brief": "context_brief.md",
        "rolling_summary": "rolling_summary.md",
        "update_protocol": "update_protocol.md",
    }
    DAILY_LOG_PATH_PATTERN = "daily_logs/{date}.md"
    DAILY_LOGS_DIRNAME = "daily_logs"
    SECTION_KEYS = {}
    OPTIONAL_SECTION_KEYS = {}
    CONTEXT_BRIEF_RENDER_ORDER = []
    LABELS = {}
    FILE_MARKER_TEMPLATE = "<!-- recallloom:file={file_key} version={version} lang={lang} -->"
    FILE_STATE_MARKER_TEMPLATE = (
        "<!-- file-state: revision={revision} | updated-at={updated_at} | writer-id={writer_id} "
        "| base-workspace-revision={base_workspace_revision} -->"
    )
    DAILY_LOG_ENTRY_MARKER_TEMPLATE = (
        "<!-- daily-log-entry: entry-id={entry_id} | created-at={created_at} | writer-id={writer_id} "
        "| entry-seq={entry_seq} -->"
    )
    DAILY_LOG_SCAFFOLD_MARKER_TEMPLATE = "<!-- daily-log-scaffold: true -->"
    LAST_WRITER_MARKER_TEMPLATE = "<!-- last-writer: [{tool}] | {date} -->"
    LAST_WRITER_RE = re.compile(
        r"^<!-- last-writer: \[(?P<tool>[^\]]+)\] \| (?P<date>\d{4}-\d{2}-\d{2}) -->$"
    )
    FILE_STATE_RE = re.compile(
        r"^<!-- file-state: revision=(?P<revision>\d+) \| updated-at=(?P<updated_at>[^ ]+) "
        r"\| writer-id=(?P<writer_id>[^|]+?) \| base-workspace-revision=(?P<base_workspace_revision>\d+) -->$"
    )
    DAILY_LOG_ENTRY_RE = re.compile(
        r"^<!-- daily-log-entry: entry-id=(?P<entry_id>[^ ]+) \| created-at=(?P<created_at>[^ ]+) "
        r"\| writer-id=(?P<writer_id>[^|]+?) \| entry-seq=(?P<entry_seq>\d+) -->$"
    )
    DAILY_LOG_SCAFFOLD_RE = re.compile(r"^<!-- daily-log-scaffold: true -->$")
    FILE_MARKER_RE = re.compile(
        r"^<!-- recallloom:file=(?P<file_key>[a-z_]+) version=(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)*) "
        r"lang=(?P<lang>[^ ]+) -->$"
    )
    SECTION_MARKER_RE = re.compile(r"^<!-- section: (?P<section_key>[a-z_]+) -->$")
    BRIDGE_START = "<!-- RecallLoom managed bridge start -->"
    BRIDGE_END = "<!-- RecallLoom managed bridge end -->"
    EXCLUDE_BLOCK_START = "# RecallLoom managed block start"
    EXCLUDE_BLOCK_END = "# RecallLoom managed block end"
    ROOT_ENTRY_CANDIDATES = [
        Path("AGENTS.md"),
        Path("CLAUDE.md"),
        Path("GEMINI.md"),
        Path(".github/copilot-instructions.md"),
    ]
    ROOT_ENTRY_CANDIDATE_STRINGS = {path.as_posix() for path in ROOT_ENTRY_CANDIDATES}


try:
    CONTRACT_SCHEMA = load_contract_schema(CONTRACT_SCHEMA_PATH)
    CONTRACT_REGISTRY = load_contract_registry(
        registry_path=CONTRACT_REGISTRY_PATH,
        schema_path=CONTRACT_SCHEMA_PATH,
    )

    CURRENT_PROTOCOL_VERSION = CONTRACT_REGISTRY["protocol"]["current"]
    SUPPORTED_PROTOCOL_VERSIONS = set(CONTRACT_REGISTRY["protocol"]["supported"])
    DEFAULT_WORKSPACE_LANGUAGE = CONTRACT_REGISTRY["workspace"]["languages"][0]
    SUPPORTED_WORKSPACE_LANGUAGES = set(CONTRACT_REGISTRY["workspace"]["languages"])
    SUPPORTED_STORAGE_MODES = set(CONTRACT_REGISTRY["workspace"]["storage_modes"])
    SUPPORTED_DYNAMIC_ASSET_RULE_KINDS = set(CONTRACT_REGISTRY["dynamic_asset_rule_kinds"])

    FILE_KEYS = {
        file_key: contract["path"]
        for file_key, contract in CONTRACT_REGISTRY["files"].items()
        if "path" in contract and file_key != "daily_log"
    }
    DAILY_LOG_PATH_PATTERN = CONTRACT_REGISTRY["files"]["daily_log"]["path_pattern"]
    DAILY_LOGS_DIRNAME = PurePosixPath(DAILY_LOG_PATH_PATTERN).parts[0]
    SECTION_KEYS = {
        file_key: list(contract["required_sections"])
        for file_key, contract in CONTRACT_REGISTRY["files"].items()
        if contract["required_sections"]
    }
    OPTIONAL_SECTION_KEYS = {
        file_key: list(contract["optional_sections"])
        for file_key, contract in CONTRACT_REGISTRY["files"].items()
        if contract["optional_sections"]
    }
    CONTEXT_BRIEF_RENDER_ORDER = list(CONTRACT_REGISTRY["files"]["context_brief"]["render_order"])
    LABELS = {
        language: {
            "context_brief": CONTRACT_REGISTRY["files"]["context_brief"]["labels"][language],
            "rolling_summary": CONTRACT_REGISTRY["files"]["rolling_summary"]["labels"][language],
            "daily_log": CONTRACT_REGISTRY["files"]["daily_log"]["labels"][language],
            "update_protocol": CONTRACT_REGISTRY["files"]["update_protocol"]["labels"][language],
        }
        for language in CONTRACT_REGISTRY["workspace"]["languages"]
    }

    FILE_MARKER_TEMPLATE = CONTRACT_REGISTRY["markers"]["file"]["template"]
    FILE_STATE_MARKER_TEMPLATE = CONTRACT_REGISTRY["markers"]["file_state"]["template"]
    DAILY_LOG_ENTRY_MARKER_TEMPLATE = CONTRACT_REGISTRY["markers"]["daily_log_entry"]["template"]
    DAILY_LOG_SCAFFOLD_MARKER_TEMPLATE = CONTRACT_REGISTRY["markers"]["daily_log_scaffold"]["template"]
    LAST_WRITER_MARKER_TEMPLATE = CONTRACT_REGISTRY["markers"]["last_writer"]["template"]

    LAST_WRITER_RE = re.compile(CONTRACT_REGISTRY["markers"]["last_writer"]["regex"])
    FILE_STATE_RE = re.compile(CONTRACT_REGISTRY["markers"]["file_state"]["regex"])
    DAILY_LOG_ENTRY_RE = re.compile(CONTRACT_REGISTRY["markers"]["daily_log_entry"]["regex"])
    DAILY_LOG_SCAFFOLD_RE = re.compile(CONTRACT_REGISTRY["markers"]["daily_log_scaffold"]["regex"])
    FILE_MARKER_RE = re.compile(CONTRACT_REGISTRY["markers"]["file"]["regex"])
    SECTION_MARKER_RE = re.compile(r"^<!-- section: (?P<section_key>[a-z_]+) -->$")

    BRIDGE_START = CONTRACT_REGISTRY["markers"]["bridge"]["start"]
    BRIDGE_END = CONTRACT_REGISTRY["markers"]["bridge"]["end"]
    EXCLUDE_BLOCK_START = CONTRACT_REGISTRY["markers"]["git_exclude"]["start"]
    EXCLUDE_BLOCK_END = CONTRACT_REGISTRY["markers"]["git_exclude"]["end"]

    ROOT_ENTRY_CANDIDATES = [
        Path(path_str) for path_str in CONTRACT_REGISTRY["workspace"]["bridge_targets"]
    ]
    ROOT_ENTRY_CANDIDATE_STRINGS = {path.as_posix() for path in ROOT_ENTRY_CANDIDATES}
except (RuntimeError, re.error) as exc:
    _install_fallback_contracts(exc)


def contract_bootstrap_error_message() -> str | None:
    if CONTRACT_BOOTSTRAP_ERROR is None:
        return None
    return f"RecallLoom contract registry bootstrap failed: {CONTRACT_BOOTSTRAP_ERROR}"


def validate_workspace_language(language: str) -> str:
    if language not in SUPPORTED_WORKSPACE_LANGUAGES:
        raise ValueError(f"Unsupported workspace_language: {language}")
    return language
