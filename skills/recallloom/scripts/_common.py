#!/usr/bin/env python3
"""Shared helpers for RecallLoom support scripts."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import sys
import tempfile
from typing import Iterable

PROTOCOL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)*$")
RECOVERY_PROPOSAL_FILE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}-[A-Za-z0-9._-]+\.md$")
REVIEW_RECORD_FILE_RE = re.compile(r"^[0-9]{4}-[0-9]{2}-[0-9]{2}-[0-9]{6}-[A-Za-z0-9._-]+\.review\.md$")
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+(?P<title>.*?)\s*$")
HEADING_NUMBER_PREFIX_RE = re.compile(r"^\s*[0-9]+(?:\.[0-9]+)*[.)、:：-]?\s*")
INVISIBLE_UNICODE_RE = re.compile(r"[\u200b-\u200f\u2060\u2066-\u2069\ufeff]")

PACKAGE_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_ROOT = Path(__file__).resolve().parent
if str(SCRIPT_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPT_ROOT))

from core.protocol import contracts as protocol_contracts
from core.protocol import markers as protocol_markers
from core.protocol import sections as protocol_sections
from core.protocol import templates as protocol_templates
from core import errors as core_errors
from core.workspace import runtime as workspace_runtime
from core.bridge import blocks as bridge_blocks
from core.continuity import freshness as continuity_freshness
from core.failure.contracts import failure_payload, preferred_failure_language
from core.output.privacy import (
    display_project_path as shared_display_project_path,
    display_project_root_label as shared_display_project_root_label,
    public_project_path as shared_public_project_path,
    public_project_root_label as shared_public_project_root_label,
    publicize_json_value,
)
from core.support.cache import SUPPORT_STATE_ENV, package_support_result
from core.support.policy import action_level_for_script
from core.safety import attached_text as safety_attached_text

METADATA_PATH = PACKAGE_ROOT / "package-metadata.json"
MANAGED_ASSETS_OVERRIDE_ENV = "RECALLLOOM_MANAGED_ASSETS_PATH"
DEFAULT_MANAGED_ASSETS_PATH = PACKAGE_ROOT / "managed-assets.json"
MANAGED_ASSETS_PATH = Path(os.environ.get(MANAGED_ASSETS_OVERRIDE_ENV, str(DEFAULT_MANAGED_ASSETS_PATH))).expanduser().resolve()
CONTEXT_DIRNAME = workspace_runtime.CONTEXT_DIRNAME
VISIBLE_DIRNAME = workspace_runtime.VISIBLE_DIRNAME
DEFAULT_STORAGE_MODE = workspace_runtime.DEFAULT_STORAGE_MODE
VISIBLE_STORAGE_MODE = workspace_runtime.VISIBLE_STORAGE_MODE
RECOVERY_PROPOSAL_REQUIRED_HEADINGS = (
    ("来源摘要", "source summary"),
    ("来源类型与可信级别", "source type and confidence"),
    ("候选当前状态事实", "candidate current-state facts"),
    ("候选里程碑事件", "candidate milestone events"),
    ("候选判断反转", "candidate judgment reversals"),
    ("候选下一步变化", "candidate next-step changes"),
    ("与当前 sidecar 的冲突", "conflicts with current sidecar"),
    ("建议提升动作", "suggested promotion actions"),
    ("审阅结论", "review conclusion"),
)
RECOVERY_REVIEW_REQUIRED_HEADINGS = (
    ("proposal reference", "提案引用"),
    ("review outcome", "审阅结论"),
    ("approved items", "通过项"),
    ("rejected items", "拒绝项"),
    ("promotion status", "提升状态"),
    ("next action", "下一步"),
)
RECOVERY_REVIEW_HINT_MARKERS = (
    "hint-only",
    "hint only",
    "kept as hint",
    "retain as hint",
    "no items remain hint-only",
    "保留为 hint",
    "仅保留为 hint",
    "只保留为 hint",
    "无 hint",
)
RECOVERY_PROMOTION_TARGET_MARKERS = (
    "rolling_summary.md",
    "context_brief.md",
    "daily_logs/",
    "daily_logs\\",
    "daily log",
)
UPDATE_PROTOCOL_TIME_POLICY_KEYWORDS = (
    "workday",
    "logical workday",
    "work day",
    "active day",
    "rollover",
    "rollover_hour",
    "timezone",
    "time zone",
    "cross-day",
    "cross day",
    "append target",
    "append date",
    "start new day",
    "close day",
    "yesterday",
    "today",
    "工作日",
    "逻辑工作日",
    "时区",
    "跨天",
    "追加日期",
    "追加日志日期",
    "关闭昨天",
    "开启新的一天",
    "昨天",
    "今天",
)

DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_DIRS = continuity_freshness.DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_DIRS
DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_FILES = continuity_freshness.DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_FILES

ATTACH_SCAN_HARD_BLOCK_PATTERNS = safety_attached_text.ATTACH_SCAN_HARD_BLOCK_PATTERNS
ATTACH_SCAN_WARNING_PATTERNS = safety_attached_text.ATTACH_SCAN_WARNING_PATTERNS


def load_package_metadata() -> dict:
    try:
        payload = json.loads(METADATA_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing package metadata file: {METADATA_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed package metadata file: {METADATA_PATH}") from exc
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Package metadata file is not valid UTF-8: {METADATA_PATH}") from exc

    required = {
        "package_name",
        "display_name",
        "package_version",
        "protocol_version",
        "supported_protocol_versions",
        "minimum_python_version",
        "supported_workspace_languages",
        "supported_bridge_targets",
    }
    missing = sorted(required.difference(payload.keys()))
    if missing:
        raise RuntimeError(
            f"Package metadata is missing required fields {missing}: {METADATA_PATH}"
        )

    if not isinstance(payload["package_name"], str) or not payload["package_name"].strip():
        raise RuntimeError(f"package_name must be a non-empty string: {METADATA_PATH}")
    if not isinstance(payload["display_name"], str) or not payload["display_name"].strip():
        raise RuntimeError(f"display_name must be a non-empty string: {METADATA_PATH}")
    if not isinstance(payload["package_version"], str) or not payload["package_version"].strip():
        raise RuntimeError(f"package_version must be a non-empty string: {METADATA_PATH}")
    if not isinstance(payload["minimum_python_version"], str) or not payload["minimum_python_version"].strip():
        raise RuntimeError(f"minimum_python_version must be a non-empty string: {METADATA_PATH}")
    if not isinstance(payload["protocol_version"], str) or not payload["protocol_version"].strip():
        raise RuntimeError(f"protocol_version must be a non-empty string: {METADATA_PATH}")
    if not PROTOCOL_VERSION_RE.match(payload["protocol_version"]):
        raise RuntimeError(
            f"protocol_version must use dotted string form such as '1.0': {METADATA_PATH}"
        )

    supported_protocols = payload["supported_protocol_versions"]
    if not isinstance(supported_protocols, list) or not supported_protocols:
        raise RuntimeError(f"supported_protocol_versions must be a non-empty list: {METADATA_PATH}")
    if not all(isinstance(item, str) and PROTOCOL_VERSION_RE.match(item) for item in supported_protocols):
        raise RuntimeError(
            f"supported_protocol_versions must contain only dotted protocol-version strings: {METADATA_PATH}"
        )
    if payload["protocol_version"] not in supported_protocols:
        raise RuntimeError(
            f"protocol_version must be included in supported_protocol_versions: {METADATA_PATH}"
        )

    languages = payload["supported_workspace_languages"]
    if not isinstance(languages, list) or not languages or not all(isinstance(item, str) and item for item in languages):
        raise RuntimeError(
            f"supported_workspace_languages must be a non-empty list of strings: {METADATA_PATH}"
        )

    bridge_targets = payload["supported_bridge_targets"]
    if not isinstance(bridge_targets, list) or not bridge_targets or not all(isinstance(item, str) and item for item in bridge_targets):
        raise RuntimeError(
            f"supported_bridge_targets must be a non-empty list of strings: {METADATA_PATH}"
        )

    return payload


def _load_relative_path_list(payload: dict, *, field: str, source_path: Path) -> list[str]:
    value = payload.get(field)
    if not isinstance(value, list):
        raise RuntimeError(f"{field} must be a list: {source_path}")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise RuntimeError(f"{field} must contain non-empty strings: {source_path}")
        normalized_item = PurePosixPath(item.strip()).as_posix()
        normalized_parts = PurePosixPath(normalized_item).parts
        if (
            normalized_item in {".", ""}
            or normalized_item.startswith("../")
            or normalized_item.startswith("/")
            or ".." in normalized_parts
        ):
            raise RuntimeError(f"{field} contains an invalid relative path '{item}': {source_path}")
        if normalized_item in seen:
            raise RuntimeError(f"{field} contains a duplicate path '{normalized_item}': {source_path}")
        seen.add(normalized_item)
        normalized.append(normalized_item)
    return normalized


def extract_section_text(text: str, section_key: str) -> str:
    return protocol_sections.extract_section_text(text, section_key)


def markdown_heading_titles(text: str) -> list[str]:
    return protocol_sections.markdown_heading_titles(text)


def missing_recovery_headings(text: str, heading_groups: tuple[tuple[str, ...], ...]) -> list[str]:
    return protocol_sections.missing_recovery_headings(text, heading_groups)


def validate_recovery_proposal_text(text: str) -> list[str]:
    errors: list[str] = []
    if not text.strip():
        return ["Recovery proposal content is empty."]

    missing = missing_recovery_headings(text, RECOVERY_PROPOSAL_REQUIRED_HEADINGS)
    if missing:
        errors.append(
            "Recovery proposal is missing required sections: "
            + ", ".join(missing)
        )

    lowered = text.casefold()
    if not any(marker.casefold() in lowered for marker in RECOVERY_PROMOTION_TARGET_MARKERS):
        errors.append(
            "Recovery proposal must explicitly name at least one promotion target such as "
            "rolling_summary.md, context_brief.md, or daily_logs/."
        )

    return errors


def validate_recovery_review_text(text: str) -> list[str]:
    errors: list[str] = []
    if not text.strip():
        return ["Recovery review content is empty."]

    missing = missing_recovery_headings(text, RECOVERY_REVIEW_REQUIRED_HEADINGS)
    if missing:
        errors.append(
            "Recovery review is missing required sections: "
            + ", ".join(missing)
        )

    lowered = text.casefold()
    if not any(marker.casefold() in lowered for marker in RECOVERY_REVIEW_HINT_MARKERS):
        errors.append(
            "Recovery review must explicitly record hint-only handling, even if the conclusion is that no items remain hint-only."
        )

    return errors


def detect_update_protocol_time_policy_cues(text: str) -> list[str]:
    return protocol_sections.detect_update_protocol_time_policy_cues(text)


def load_managed_assets_metadata(*, supported_dynamic_asset_rule_kinds: set[str]) -> dict:
    try:
        payload = json.loads(MANAGED_ASSETS_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing managed assets file: {MANAGED_ASSETS_PATH}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed managed assets file: {MANAGED_ASSETS_PATH}") from exc
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"Managed assets file is not valid UTF-8: {MANAGED_ASSETS_PATH}") from exc

    if not isinstance(payload, dict):
        raise RuntimeError(f"Managed assets file must be a JSON object: {MANAGED_ASSETS_PATH}")

    required = {
        "version",
        "required_files",
        "optional_files",
        "required_directories",
        "managed_directories",
        "dynamic_file_rules",
    }
    missing = sorted(required.difference(payload.keys()))
    if missing:
        raise RuntimeError(
            f"Managed assets file is missing required fields {missing}: {MANAGED_ASSETS_PATH}"
        )

    version = payload["version"]
    if not isinstance(version, int) or version < 1:
        raise RuntimeError(f"Managed assets version must be a positive integer: {MANAGED_ASSETS_PATH}")

    required_files = _load_relative_path_list(payload, field="required_files", source_path=MANAGED_ASSETS_PATH)
    optional_files = _load_relative_path_list(payload, field="optional_files", source_path=MANAGED_ASSETS_PATH)
    required_directories = _load_relative_path_list(
        payload, field="required_directories", source_path=MANAGED_ASSETS_PATH
    )
    managed_directories = _load_relative_path_list(
        payload, field="managed_directories", source_path=MANAGED_ASSETS_PATH
    )
    required_file_set = set(required_files)
    optional_file_set = set(optional_files)
    required_directory_set = set(required_directories)
    managed_directory_set = set(managed_directories)
    all_directory_set = required_directory_set | managed_directory_set

    overlap = sorted(required_file_set.intersection(optional_file_set))
    if overlap:
        raise RuntimeError(
            f"required_files and optional_files must be disjoint, found {overlap}: {MANAGED_ASSETS_PATH}"
        )

    file_directory_overlap = sorted((required_file_set | optional_file_set).intersection(all_directory_set))
    if file_directory_overlap:
        raise RuntimeError(
            "managed asset file paths and directory paths must be disjoint, found "
            f"{file_directory_overlap}: {MANAGED_ASSETS_PATH}"
        )

    dynamic_rules = payload["dynamic_file_rules"]
    if not isinstance(dynamic_rules, list):
        raise RuntimeError(f"dynamic_file_rules must be a list: {MANAGED_ASSETS_PATH}")
    normalized_rules: list[dict[str, str]] = []
    seen_rules: set[tuple[str, str]] = set()
    for item in dynamic_rules:
        if not isinstance(item, dict):
            raise RuntimeError(f"dynamic_file_rules must contain objects: {MANAGED_ASSETS_PATH}")
        base_dir = item.get("base_dir")
        kind = item.get("kind")
        if not isinstance(base_dir, str) or not base_dir.strip():
            raise RuntimeError(f"dynamic_file_rules.base_dir must be a non-empty string: {MANAGED_ASSETS_PATH}")
        if not isinstance(kind, str) or kind not in supported_dynamic_asset_rule_kinds:
            raise RuntimeError(
                "dynamic_file_rules.kind must be one of "
                f"{sorted(supported_dynamic_asset_rule_kinds)}: {MANAGED_ASSETS_PATH}"
            )
        normalized_base_dir = PurePosixPath(base_dir.strip()).as_posix()
        if normalized_base_dir in {".", ""} or normalized_base_dir.startswith("../") or normalized_base_dir.startswith("/"):
            raise RuntimeError(
                f"dynamic_file_rules contains an invalid base_dir '{base_dir}': {MANAGED_ASSETS_PATH}"
            )
        if normalized_base_dir not in all_directory_set:
            raise RuntimeError(
                "dynamic_file_rules.base_dir must reference a declared required_directories or managed_directories entry, "
                f"got '{normalized_base_dir}': {MANAGED_ASSETS_PATH}"
            )
        rule_key = (normalized_base_dir, kind)
        if rule_key in seen_rules:
            raise RuntimeError(
                f"dynamic_file_rules contains a duplicate rule {rule_key}: {MANAGED_ASSETS_PATH}"
            )
        seen_rules.add(rule_key)
        normalized_rules.append({"base_dir": normalized_base_dir, "kind": kind})

    return {
        "version": version,
        "required_files": required_files,
        "optional_files": optional_files,
        "required_directories": required_directories,
        "managed_directories": managed_directories,
        "dynamic_file_rules": normalized_rules,
    }


def validate_contract_registry_alignment(package_metadata: dict, contract_registry: dict) -> None:
    expected_pairs = (
        (
            "protocol_version",
            package_metadata["protocol_version"],
            contract_registry["protocol"]["current"],
        ),
        (
            "supported_protocol_versions",
            package_metadata["supported_protocol_versions"],
            contract_registry["protocol"]["supported"],
        ),
        (
            "supported_workspace_languages",
            package_metadata["supported_workspace_languages"],
            contract_registry["workspace"]["languages"],
        ),
        (
            "supported_bridge_targets",
            package_metadata["supported_bridge_targets"],
            contract_registry["workspace"]["bridge_targets"],
        ),
    )
    for field_name, metadata_value, registry_value in expected_pairs:
        if metadata_value != registry_value:
            raise RuntimeError(
                f"package metadata field '{field_name}' must stay aligned with contract registry"
            )


COMMON_BOOTSTRAP_ERROR: RuntimeError | None = None

try:
    PACKAGE_METADATA = load_package_metadata()
    CONTRACT_REGISTRY_PATH = protocol_contracts.CONTRACT_REGISTRY_PATH
    CONTRACT_SCHEMA_PATH = protocol_contracts.CONTRACT_SCHEMA_PATH
    CONTRACT_SCHEMA = protocol_contracts.CONTRACT_SCHEMA
    CONTRACT_REGISTRY = protocol_contracts.CONTRACT_REGISTRY
    if protocol_contracts.CONTRACT_BOOTSTRAP_ERROR is None:
        validate_contract_registry_alignment(PACKAGE_METADATA, CONTRACT_REGISTRY)
    MANAGED_ASSETS_METADATA = load_managed_assets_metadata(
        supported_dynamic_asset_rule_kinds=set(protocol_contracts.SUPPORTED_DYNAMIC_ASSET_RULE_KINDS)
    )
except RuntimeError as exc:
    COMMON_BOOTSTRAP_ERROR = exc
    PACKAGE_METADATA = {
        "package_name": "recallloom",
        "display_name": "RecallLoom",
        "package_version": "0.0.0-bootstrap-error",
        "protocol_version": protocol_contracts.CURRENT_PROTOCOL_VERSION,
        "supported_protocol_versions": sorted(protocol_contracts.SUPPORTED_PROTOCOL_VERSIONS),
        "minimum_python_version": "3.10",
        "supported_workspace_languages": sorted(protocol_contracts.SUPPORTED_WORKSPACE_LANGUAGES),
        "supported_bridge_targets": sorted(protocol_contracts.ROOT_ENTRY_CANDIDATE_STRINGS),
    }
    CONTRACT_REGISTRY_PATH = protocol_contracts.CONTRACT_REGISTRY_PATH
    CONTRACT_SCHEMA_PATH = protocol_contracts.CONTRACT_SCHEMA_PATH
    CONTRACT_SCHEMA = protocol_contracts.CONTRACT_SCHEMA
    CONTRACT_REGISTRY = protocol_contracts.CONTRACT_REGISTRY
    MANAGED_ASSETS_METADATA = {
        "required_files": [],
        "optional_files": [],
        "required_directories": [],
        "managed_directories": [],
        "dynamic_file_rules": [],
    }
PACKAGE_NAME = PACKAGE_METADATA["package_name"]
PACKAGE_VERSION = PACKAGE_METADATA["package_version"]


# ---------------------------------------------------------------------------
# Agent + model auto-detection for writer_id
# Reads AI_AGENT (standard agent identity) and the first model env var
# found among common provider names.  Concatenates with ``+`` as separator.
# Falls back to the package display name when no agent env is detected.
# No subprocess, no I/O — pure env reads, runs once at module load.
# ---------------------------------------------------------------------------

_AGENT_ID_CACHE: str | None = None

# Order does not imply priority; the first one found wins.
_MODEL_ENV_VARS = (
    "ANTHROPIC_MODEL",
    "OPENAI_MODEL",
    "GEMINI_MODEL",
    "MODEL",
    "LLM_MODEL",
)


def _clean_writer_value(value: str) -> str:
    """Strip control chars, pipe and bracket so the value is safe in all marker fields."""
    return "".join(ch for ch in value if ch not in {"|", "]", "\n", "\r"}).strip()


def get_default_writer_id() -> str:
    """
    Return the canonical writer-id for the current session.

    Reads ``AI_AGENT`` as-is and joins it with the first model env var
    that is set.  Falls back to ``display_name`` when neither is found.
    """
    global _AGENT_ID_CACHE
    if _AGENT_ID_CACHE is not None:
        return _AGENT_ID_CACHE

    agent_raw = os.environ.get("AI_AGENT", "")
    model_raw = ""
    for var in _MODEL_ENV_VARS:
        model_raw = os.environ.get(var, "")
        if model_raw:
            break

    agent_part = _clean_writer_value(agent_raw.split("/")[0]) if agent_raw else ""
    model_part = _clean_writer_value(model_raw) if model_raw else ""

    if agent_part:
        _AGENT_ID_CACHE = f"{agent_part}+{model_part}" if model_part else agent_part
    elif model_part:
        _AGENT_ID_CACHE = model_part
    else:
        _AGENT_ID_CACHE = PACKAGE_METADATA["display_name"]

    return _AGENT_ID_CACHE


DISPLAY_NAME = get_default_writer_id()
CURRENT_PROTOCOL_VERSION = protocol_contracts.CURRENT_PROTOCOL_VERSION
SUPPORTED_PROTOCOL_VERSIONS = protocol_contracts.SUPPORTED_PROTOCOL_VERSIONS
MINIMUM_PYTHON_VERSION = PACKAGE_METADATA["minimum_python_version"]
MINIMUM_PYTHON_VERSION_PARTS = tuple(int(part) for part in MINIMUM_PYTHON_VERSION.split("."))
DEFAULT_WORKSPACE_LANGUAGE = protocol_contracts.DEFAULT_WORKSPACE_LANGUAGE
SUPPORTED_WORKSPACE_LANGUAGES = protocol_contracts.SUPPORTED_WORKSPACE_LANGUAGES
SUPPORTED_STORAGE_MODES = protocol_contracts.SUPPORTED_STORAGE_MODES
DAILY_LOGS_DIRNAME = protocol_contracts.DAILY_LOGS_DIRNAME
SUPPORTED_DYNAMIC_ASSET_RULE_KINDS = protocol_contracts.SUPPORTED_DYNAMIC_ASSET_RULE_KINDS
MANAGED_ASSET_REQUIRED_FILES = tuple(MANAGED_ASSETS_METADATA["required_files"])
MANAGED_ASSET_OPTIONAL_FILES = tuple(MANAGED_ASSETS_METADATA["optional_files"])
MANAGED_ASSET_REQUIRED_DIRECTORIES = tuple(MANAGED_ASSETS_METADATA["required_directories"])
MANAGED_ASSET_DIRECTORIES = tuple(MANAGED_ASSETS_METADATA["managed_directories"])
MANAGED_ASSET_DYNAMIC_RULES = tuple(MANAGED_ASSETS_METADATA["dynamic_file_rules"])

FILE_KEYS = protocol_contracts.FILE_KEYS


def is_required_storage_file(rel_path: str) -> bool:
    return PurePosixPath(rel_path).as_posix() in MANAGED_ASSET_REQUIRED_FILES


def is_optional_storage_file(rel_path: str) -> bool:
    return PurePosixPath(rel_path).as_posix() in MANAGED_ASSET_OPTIONAL_FILES


def is_required_storage_directory(rel_path: str) -> bool:
    return PurePosixPath(rel_path).as_posix() in MANAGED_ASSET_REQUIRED_DIRECTORIES

SECTION_KEYS = protocol_contracts.SECTION_KEYS
OPTIONAL_SECTION_KEYS = protocol_contracts.OPTIONAL_SECTION_KEYS
CONTEXT_BRIEF_RENDER_ORDER = protocol_contracts.CONTEXT_BRIEF_RENDER_ORDER
LABELS = protocol_contracts.LABELS

FILE_MARKER_TEMPLATE = protocol_contracts.FILE_MARKER_TEMPLATE
FILE_STATE_MARKER_TEMPLATE = protocol_contracts.FILE_STATE_MARKER_TEMPLATE
DAILY_LOG_ENTRY_MARKER_TEMPLATE = protocol_contracts.DAILY_LOG_ENTRY_MARKER_TEMPLATE
DAILY_LOG_SCAFFOLD_MARKER_TEMPLATE = protocol_contracts.DAILY_LOG_SCAFFOLD_MARKER_TEMPLATE
LAST_WRITER_MARKER_TEMPLATE = protocol_contracts.LAST_WRITER_MARKER_TEMPLATE
LAST_WRITER_RE = protocol_contracts.LAST_WRITER_RE
FILE_STATE_RE = protocol_contracts.FILE_STATE_RE
DAILY_LOG_ENTRY_RE = protocol_contracts.DAILY_LOG_ENTRY_RE
DAILY_LOG_SCAFFOLD_RE = protocol_contracts.DAILY_LOG_SCAFFOLD_RE
DATE_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
FILE_MARKER_RE = protocol_contracts.FILE_MARKER_RE
SECTION_MARKER_RE = protocol_contracts.SECTION_MARKER_RE
BRIDGE_START = protocol_contracts.BRIDGE_START
BRIDGE_END = protocol_contracts.BRIDGE_END
EXCLUDE_BLOCK_START = protocol_contracts.EXCLUDE_BLOCK_START
EXCLUDE_BLOCK_END = protocol_contracts.EXCLUDE_BLOCK_END
ROOT_ENTRY_CANDIDATES = protocol_contracts.ROOT_ENTRY_CANDIDATES
ROOT_ENTRY_CANDIDATE_STRINGS = protocol_contracts.ROOT_ENTRY_CANDIDATE_STRINGS


def validate_tool_name(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigContractError("tool_name must be a non-empty string")
    if any(ch in value for ch in {"|", "]", "\n", "\r"}):
        raise ConfigContractError(
            "tool_name may not contain '|', ']', or line-break characters because it is embedded in machine-readable markers"
        )
    return value.strip()


def validate_writer_id(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigContractError("writer_id must be a non-empty string")
    if any(ch in value for ch in {"|", "]", "\n", "\r"}):
        raise ConfigContractError(
            "writer_id may not contain '|', ']', or line-break characters because it is embedded in machine-readable markers"
        )
    return value.strip()
WORKSPACE_LOCK_FILENAME = workspace_runtime.WORKSPACE_LOCK_FILENAME
STALE_LOCK_MAX_AGE_SECONDS = 6 * 3600

WorkspaceInfo = workspace_runtime.WorkspaceInfo
RecoveryWorkspaceInfo = workspace_runtime.RecoveryWorkspaceInfo
FileMarkerInfo = protocol_markers.FileMarkerInfo
FileStateInfo = protocol_markers.FileStateInfo
DailyLogEntryInfo = protocol_markers.DailyLogEntryInfo


@dataclass(frozen=True)
class ValidationFinding:
    level: str
    code: str
    message: str
    path: Path


StorageResolutionError = core_errors.StorageResolutionError
ConfigContractError = core_errors.ConfigContractError
EnvironmentContractError = core_errors.EnvironmentContractError
LockBusyError = core_errors.LockBusyError


def normalize_start_path(raw_path: str | Path) -> Path:
    return workspace_runtime.normalize_start_path(raw_path)


def ensure_supported_python_version() -> None:
    current = sys.version_info[: len(MINIMUM_PYTHON_VERSION_PARTS)]
    if current < MINIMUM_PYTHON_VERSION_PARTS:
        raise EnvironmentContractError(
            "RecallLoom helper scripts require "
            f"Python {MINIMUM_PYTHON_VERSION}+; current interpreter is "
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
        )
    contract_bootstrap_error = protocol_contracts.contract_bootstrap_error_message()
    if contract_bootstrap_error is not None:
        raise EnvironmentContractError(contract_bootstrap_error)
    if COMMON_BOOTSTRAP_ERROR is not None:
        raise EnvironmentContractError(
            f"RecallLoom runtime bootstrap failed: {COMMON_BOOTSTRAP_ERROR}"
        )


def validate_iso_date(value: str) -> bool:
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def parse_iso_date(value: str) -> date:
    return date.fromisoformat(value)


def today_iso() -> str:
    return date.today().isoformat()


def now_iso_timestamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=path.parent,
        prefix=f".{path.name}.tmp-",
        delete=False,
    ) as handle:
        handle.write(text)
        handle.flush()
        os.fsync(handle.fileno())
        temp_path = Path(handle.name)
    os.replace(temp_path, path)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def exit_with_cli_error(
    parser,
    *,
    json_mode: bool,
    exit_code: int,
    message: str,
    payload: dict | None = None,
) -> None:
    message = message.rstrip("\n")
    if json_mode:
        body = {"ok": False, "error": message}
        if payload:
            body.update(payload)
        print(json.dumps(body, ensure_ascii=False, indent=2))
        raise SystemExit(exit_code)
    parser.exit(exit_code, message + "\n")


def cli_failure_payload(
    reason: str,
    *,
    error: str | None = None,
    details: dict | None = None,
    findings: list | None = None,
    extra: dict | None = None,
) -> dict:
    normalized_details = dict(details or {})
    if reason in {"no_project_root", "not_project_root", "invalid_storage_boundary"}:
        inferred_project_root = normalized_details.get("project_root")
        if not isinstance(inferred_project_root, str) or not inferred_project_root.strip():
            raw_target = None
            argv = list(sys.argv[1:]) if len(sys.argv) > 1 else []
            if Path(sys.argv[0]).name == "recallloom.py" and argv:
                argv = argv[1:]
            if argv and not argv[0].startswith("-"):
                raw_target = argv[0]
            else:
                raw_target = "."
            try:
                normalized_details["project_root"] = str(normalize_start_path(raw_target))
            except StorageResolutionError:
                normalized_details["project_root"] = str(Path(raw_target).expanduser().resolve())
    return failure_payload(
        reason,
        language=preferred_failure_language(os.environ),
        error=error,
        details=normalized_details or None,
        findings=findings,
        extra=extra,
        script_name=Path(sys.argv[0]).name if sys.argv else None,
    )


def public_project_root_label(project_root: str | Path) -> str:
    return shared_public_project_root_label(project_root)


def public_project_path(
    path: str | Path | None,
    *,
    project_root: str | Path,
) -> str | None:
    return shared_public_project_path(path, project_root=project_root)


def display_project_root_label(project_root: str | Path) -> str:
    return shared_display_project_root_label(project_root)


def display_project_path(
    path: str | Path | None,
    *,
    project_root: str | Path,
) -> str | None:
    return shared_display_project_path(path, project_root=project_root)


def public_json_payload(
    payload: dict,
    *,
    project_root: str | Path | None,
) -> dict:
    publicized = publicize_json_value(payload, project_root=project_root)
    return publicized if isinstance(publicized, dict) else payload


def public_package_support_payload(support: dict | None) -> dict | None:
    if support is None:
        return None
    allowed_keys = (
        "allowed",
        "action_name",
        "action_level",
        "package_support_state",
        "current_version",
        "latest_version",
        "minimum_mutating_version",
        "minimum_readonly_version",
        "advisory_level",
        "reason_code",
        "update_hints",
        "checked_date",
        "checked_at",
        "source",
        "cache_hit",
        "support_diagnostic_reason",
        "user_message",
        "disabled",
    )
    public = {key: support[key] for key in allowed_keys if key in support}
    source = public.get("source")
    if isinstance(source, str):
        if source.startswith("file:"):
            public["source"] = "file"
        elif source.startswith("url:"):
            public["source"] = "url"
    return public


def exit_with_failure_contract(
    parser,
    *,
    json_mode: bool,
    exit_code: int,
    message: str,
    reason: str,
    details: dict | None = None,
    findings: list | None = None,
    extra: dict | None = None,
) -> None:
    exit_with_cli_error(
        parser,
        json_mode=json_mode,
        exit_code=exit_code,
        message=message,
        payload=cli_failure_payload(
            reason,
            error=message,
            details=details,
            findings=findings,
            extra=extra,
        ),
    )


def cli_failure_payload_for_exception(
    exc: BaseException,
    *,
    default_reason: str,
    extra: dict | None = None,
) -> dict:
    reason = getattr(exc, "failure_reason", None) or default_reason
    return cli_failure_payload(reason, error=str(exc), extra=extra)


def enforce_package_support_gate(
    parser,
    *,
    json_mode: bool,
    action_name: str | None = None,
    action_level: str | None = None,
) -> dict:
    metadata = load_package_metadata()
    script_name = Path(sys.argv[0]).name
    action_name = action_name or script_name
    action_level = action_level or action_level_for_script(script_name)
    support = package_support_result(
        package_root=PACKAGE_ROOT,
        package_version=metadata["package_version"],
        action_name=action_name,
        action_level=action_level,
        advisory_url=metadata.get("support_advisory_url"),
        env=os.environ,
    )
    os.environ[SUPPORT_STATE_ENV] = json.dumps(support, ensure_ascii=False)
    if support["allowed"]:
        return support
    message = support.get("user_message") or "RecallLoom package support gate blocked this action."
    exit_with_cli_error(
        parser,
        json_mode=json_mode,
        exit_code=4,
        message=message,
        payload=cli_failure_payload(
            "package_support_blocked",
            error=message,
            details={"package_support": support},
            extra={"package_support": support},
        ),
    )


def load_json(path: Path) -> dict:
    return json.loads(read_text(path))


def dump_json(path: Path, payload: dict) -> None:
    write_text(path, json.dumps(payload, ensure_ascii=False, indent=2) + "\n")


def text_digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def atomic_write_if_unchanged(path: Path, *, expected_text: str, new_text: str) -> None:
    current_text = read_text(path) if path.exists() else ""
    if current_text != expected_text:
        raise LockBusyError(f"Refusing to write {path} because the file changed after it was read.")
    write_text(path, new_text)


def restore_text_snapshot(path: Path, *, existed: bool, text: str) -> None:
    if existed:
        write_text(path, text)
        return
    try:
        path.unlink()
    except FileNotFoundError:
        pass


def rollback_moved_files(applied_moves: Iterable[tuple[Path, Path]]) -> None:
    for source, target in reversed(list(applied_moves)):
        if not target.exists():
            continue
        source.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(target), str(source))


def project_lock_path(project_root: Path) -> Path:
    return workspace_runtime.project_lock_path(project_root)


def load_lock_payload(lock_path: Path) -> dict:
    return workspace_runtime.load_lock_payload(lock_path)


def parse_lock_timestamp(value: str | None) -> datetime | None:
    return workspace_runtime.parse_lock_timestamp(value)


def pid_is_alive(pid: int) -> bool:
    return workspace_runtime.pid_is_alive(pid)


def reclaim_stale_workspace_lock(lock_path: Path) -> bool:
    return workspace_runtime.reclaim_stale_workspace_lock(lock_path)


@contextmanager
def workspace_write_lock(project_root: Path, owner: str):
    with workspace_runtime.workspace_write_lock(project_root, owner) as lock_path:
        yield lock_path


def config_payload(
    *,
    storage_mode: str,
    workspace_language: str,
    created_by: str,
    created_at: str,
    protocol_version: str = CURRENT_PROTOCOL_VERSION,
) -> dict:
    return workspace_runtime.config_payload(
        storage_mode=storage_mode,
        workspace_language=workspace_language,
        created_by=created_by,
        created_at=created_at,
        protocol_version=protocol_version,
    )


def initial_workspace_state(
    *,
    tool_name: str,
    timestamp: str,
    git_exclude_mode: str,
) -> dict:
    return workspace_runtime.initial_workspace_state(
        tool_name=tool_name,
        timestamp=timestamp,
        git_exclude_mode=git_exclude_mode,
    )


def load_workspace_state(path: Path) -> dict:
    return workspace_runtime.load_workspace_state(path)


def validate_storage_mode(value: str) -> str:
    return workspace_runtime.validate_storage_mode(value)


def validate_workspace_language(value: str) -> str:
    return workspace_runtime.validate_workspace_language(value)


def validate_protocol_version(value: str) -> str:
    return workspace_runtime.validate_protocol_version(value)


def load_and_validate_config(
    path: Path,
    default_storage_mode: str,
    *,
    allow_unsupported_version: bool = False,
    allow_storage_mode_mismatch: bool = False,
) -> dict:
    return workspace_runtime.load_and_validate_config(
        path,
        default_storage_mode,
        allow_unsupported_version=allow_unsupported_version,
        allow_storage_mode_mismatch=allow_storage_mode_mismatch,
    )


def hidden_storage_root(project_root: Path) -> Path:
    return workspace_runtime.hidden_storage_root(project_root)


def visible_storage_root(project_root: Path) -> Path:
    return workspace_runtime.visible_storage_root(project_root)


def recovery_storage_roots(project_root: Path) -> list[Path]:
    return workspace_runtime.recovery_storage_roots(project_root)


def visible_root_has_sidecar_signals(storage_root: Path) -> bool:
    return workspace_runtime.visible_root_has_sidecar_signals(storage_root)


def looks_like_installable_package_dir(storage_root: Path) -> bool:
    return workspace_runtime.looks_like_installable_package_dir(storage_root)


def damaged_sidecar_reason(project_root: Path, storage_root: Path, storage_mode: str) -> str | None:
    return workspace_runtime.damaged_sidecar_reason(project_root, storage_root, storage_mode)


def is_recovery_storage_candidate(project_root: Path, storage_root: Path, storage_mode: str) -> bool:
    return workspace_runtime.is_recovery_storage_candidate(project_root, storage_root, storage_mode)


def infer_storage_mode_from_root(storage_root: Path) -> str:
    return workspace_runtime.infer_storage_mode_from_root(storage_root)


def find_recovery_workspace(
    start_path: str | Path,
    *,
    requested_storage_mode: str | None = None,
) -> RecoveryWorkspaceInfo | None:
    return workspace_runtime.find_recovery_workspace(
        start_path,
        requested_storage_mode=requested_storage_mode,
    )


def find_recovery_project_root(start_path: str | Path) -> Path:
    return workspace_runtime.find_recovery_project_root(start_path)


def storage_root_for_mode(project_root: Path, storage_mode: str) -> Path:
    return workspace_runtime.storage_root_for_mode(project_root, storage_mode)


def config_path_for_mode(project_root: Path, storage_mode: str) -> Path:
    return workspace_runtime.config_path_for_mode(project_root, storage_mode)


def file_path(workspace: WorkspaceInfo, file_key: str) -> Path:
    return workspace_runtime.file_path(workspace, file_key)


def file_marker(file_key: str, language: str, version: str = CURRENT_PROTOCOL_VERSION) -> str:
    return protocol_markers.file_marker(file_key, language, version)


def file_state_marker(
    *,
    revision: int,
    updated_at: str,
    writer_id: str,
    base_workspace_revision: int,
) -> str:
    return protocol_markers.file_state_marker(
        revision=revision,
        updated_at=updated_at,
        writer_id=writer_id,
        base_workspace_revision=base_workspace_revision,
    )


def daily_log_entry_marker(
    *,
    entry_id: str,
    created_at: str,
    writer_id: str,
    entry_seq: int,
) -> str:
    return protocol_markers.daily_log_entry_marker(
        entry_id=entry_id,
        created_at=created_at,
        writer_id=writer_id,
        entry_seq=entry_seq,
    )


def daily_log_scaffold_marker() -> str:
    return protocol_markers.daily_log_scaffold_marker()


def section_marker(section_key: str) -> str:
    return protocol_markers.section_marker(section_key)


def render_heading(level: int, heading: str) -> str:
    return protocol_templates.render_heading(level, heading)


def render_section_block(level: int, section_key: str, heading: str, body: list[str] | None = None) -> str:
    return protocol_templates.render_section_block(level, section_key, heading, body)


def rolling_summary_header(tool_name: str, day: str) -> str:
    return protocol_markers.rolling_summary_header(tool_name, day)


def render_context_brief_template(language: str, *, tool_name: str, timestamp: str, workspace_revision: int) -> str:
    language = validate_workspace_language(language)
    return protocol_templates.render_context_brief_template(
        language,
        tool_name=tool_name,
        timestamp=timestamp,
        workspace_revision=workspace_revision,
    )


def render_rolling_summary_template(tool_name: str, day: str, language: str, *, timestamp: str, workspace_revision: int) -> str:
    language = validate_workspace_language(language)
    return protocol_templates.render_rolling_summary_template(
        tool_name,
        day,
        language,
        timestamp=timestamp,
        workspace_revision=workspace_revision,
    )


def render_daily_log_template(language: str, *, tool_name: str, timestamp: str) -> str:
    language = validate_workspace_language(language)
    return protocol_templates.render_daily_log_template(
        language,
        tool_name=tool_name,
        timestamp=timestamp,
    )


def render_update_protocol_template(language: str, *, tool_name: str, timestamp: str, workspace_revision: int) -> str:
    language = validate_workspace_language(language)
    return protocol_templates.render_update_protocol_template(
        language,
        tool_name=tool_name,
        timestamp=timestamp,
        workspace_revision=workspace_revision,
    )


def render_template(
    file_key: str,
    *,
    tool_name: str,
    day: str,
    language: str,
    timestamp: str,
    workspace_revision: int,
) -> str:
    language = validate_workspace_language(language)
    return protocol_templates.render_template(
        file_key,
        tool_name=tool_name,
        day=day,
        language=language,
        timestamp=timestamp,
        workspace_revision=workspace_revision,
    )


def detect_workspace(
    project_root: Path,
    *,
    allow_unsupported_version: bool = False,
    allow_storage_mode_mismatch: bool = False,
) -> WorkspaceInfo | None:
    return workspace_runtime.detect_workspace(
        project_root,
        allow_unsupported_version=allow_unsupported_version,
        allow_storage_mode_mismatch=allow_storage_mode_mismatch,
    )


def find_recallloom_root(
    start_path: str | Path,
    *,
    allow_unsupported_version: bool = False,
    allow_storage_mode_mismatch: bool = False,
) -> WorkspaceInfo | None:
    return workspace_runtime.find_recallloom_root(
        start_path,
        allow_unsupported_version=allow_unsupported_version,
        allow_storage_mode_mismatch=allow_storage_mode_mismatch,
    )

def ensure_git_exclude_entry(project_root: Path, entry: str = f"{CONTEXT_DIRNAME}/") -> bool:
    return workspace_runtime.ensure_git_exclude_entry(project_root, entry=entry)


def remove_git_exclude_block(project_root: Path) -> bool:
    return workspace_runtime.remove_git_exclude_block(project_root)


def sorted_daily_log_files(logs_dir: Path) -> list[Path]:
    dated_files: list[Path] = []
    if not logs_dir.is_dir():
        return dated_files
    for child in logs_dir.iterdir():
        if child.is_file() and DATE_FILE_RE.match(child.name):
            try:
                parse_iso_date(child.stem)
            except ValueError:
                continue
            dated_files.append(child)
    return sorted(dated_files, key=lambda path: path.stem)


def invalid_iso_like_daily_log_files(logs_dir: Path) -> list[Path]:
    invalid: list[Path] = []
    if not logs_dir.is_dir():
        return invalid
    for child in sorted(logs_dir.iterdir(), key=lambda path: path.name):
        if child.is_file() and DATE_FILE_RE.match(child.name):
            try:
                parse_iso_date(child.stem)
            except ValueError:
                invalid.append(child)
    return invalid


def latest_dated_daily_log(logs_dir: Path) -> Path | None:
    dated_files = sorted_daily_log_files(logs_dir)
    if not dated_files:
        return None
    return dated_files[-1]


def latest_file(paths: Iterable[Path]) -> Path | None:
    return continuity_freshness.latest_file(list(paths))


def parse_file_marker(text: str) -> FileMarkerInfo | None:
    return protocol_markers.parse_file_marker(text)


def parse_file_state_marker(text: str) -> FileStateInfo | None:
    return protocol_markers.parse_file_state_marker(text)


def parse_daily_log_entry_marker(text: str) -> DailyLogEntryInfo | None:
    return protocol_markers.parse_daily_log_entry_marker(text)


def parse_daily_log_scaffold_marker(text: str) -> bool:
    return protocol_markers.parse_daily_log_scaffold_marker(text)


def managed_file_contract_issue(
    path: Path,
    *,
    file_key: str,
    workspace_language: str,
    expected_protocol_version: str | None = None,
) -> str | None:
    if not path.is_file():
        return f"Missing required file: {path}"
    text = read_text(path)
    marker = parse_file_marker(text)
    if marker is None:
        return f"Missing required file marker: {path}"
    if marker.file_key != file_key:
        return (
            f"Managed file marker mismatch for {path}: expected '{file_key}', "
            f"found '{marker.file_key}'."
        )
    if marker.language != workspace_language:
        return (
            f"Managed file language mismatch for {path}: expected '{workspace_language}', "
            f"found '{marker.language}'."
        )
    if expected_protocol_version is not None and marker.version != expected_protocol_version:
        return (
            f"Managed file protocol version mismatch for {path}: expected '{expected_protocol_version}', "
            f"found '{marker.version}'."
        )
    if file_key in {"context_brief", "rolling_summary", "update_protocol"}:
        if parse_file_state_marker(text) is None:
            return f"Missing required file-state marker: {path}"
    if file_key == "rolling_summary":
        lines = text.splitlines()
        if len(lines) < 2 or LAST_WRITER_RE.match(lines[1].strip()) is None:
            return f"rolling_summary.md second line must be a valid last-writer marker: {path}"
        match = LAST_WRITER_RE.match(lines[1].strip())
        if match is not None and not validate_iso_date(match.group("date")):
            return f"rolling_summary.md contains an invalid last-writer date: {path}"
    return None


def parse_daily_log_entry_line(line: str) -> DailyLogEntryInfo | None:
    match = DAILY_LOG_ENTRY_RE.match(line.strip())
    if not match:
        return None
    return DailyLogEntryInfo(
        entry_id=match.group("entry_id"),
        created_at=match.group("created_at"),
        writer_id=match.group("writer_id").strip(),
        entry_seq=int(match.group("entry_seq")),
    )


def daily_log_entries(text: str) -> list[DailyLogEntryInfo]:
    entries: list[DailyLogEntryInfo] = []
    for line in text.splitlines():
        entry = parse_daily_log_entry_line(line)
        if entry is not None:
            entries.append(entry)
    return entries


def sorted_active_daily_log_files(logs_dir: Path) -> list[Path]:
    active: list[Path] = []
    for path in sorted_daily_log_files(logs_dir):
        if daily_log_entries(read_text(path)):
            active.append(path)
    return active


def latest_active_daily_log(logs_dir: Path) -> Path | None:
    active = sorted_active_daily_log_files(logs_dir)
    if not active:
        return None
    return active[-1]


def continuity_confidence_level(
    *,
    workspace_valid: bool,
    summary_revision_is_stale: bool,
    workspace_artifact_is_newer: bool | None,
    latest_daily_log_exists: bool,
    workspace_artifact_scan_mode: str,
) -> str:
    return continuity_freshness.continuity_confidence_level(
        workspace_valid=workspace_valid,
        summary_revision_is_stale=summary_revision_is_stale,
        workspace_artifact_is_newer=workspace_artifact_is_newer,
        latest_daily_log_exists=latest_daily_log_exists,
        workspace_artifact_scan_mode=workspace_artifact_scan_mode,
    )


def _digest_excerpt(text: str, *, max_lines: int = 4) -> str | None:
    return continuity_freshness.digest_excerpt(text, max_lines=max_lines)


def continuity_digest_bundle(
    *,
    summary_text: str,
    latest_daily_log_text: str | None = None,
) -> dict:
    return continuity_freshness.continuity_digest_bundle(
        summary_text=summary_text,
        latest_daily_log_text=latest_daily_log_text,
    )


def scan_auto_attached_context_text(text: str) -> dict:
    return safety_attached_text.scan_auto_attached_context_text(text)


def iter_workspace_artifacts(
    project_root: Path,
    storage_root: Path,
    *,
    excluded_dirs: set[str] | None = None,
    excluded_files: set[str] | None = None,
) -> list[Path]:
    return continuity_freshness.iter_workspace_artifacts(
        project_root,
        storage_root,
        excluded_dirs=excluded_dirs,
        excluded_files=excluded_files,
    )


def evaluate_continuity_freshness(
    *,
    project_root: Path,
    storage_root: Path,
    summary_path: Path,
    workspace_revision: int,
    summary_base_workspace_revision: int,
    latest_daily_log_exists: bool,
    scan_mode: str = "quick",
) -> dict:
    return continuity_freshness.evaluate_continuity_freshness(
        project_root=project_root,
        storage_root=storage_root,
        summary_path=summary_path,
        workspace_revision=workspace_revision,
        summary_base_workspace_revision=summary_base_workspace_revision,
        latest_daily_log_exists=latest_daily_log_exists,
        scan_mode=scan_mode,
    )


def daily_log_sequence_error(entries: list[DailyLogEntryInfo]) -> str | None:
    if not entries:
        return "Missing required daily-log-entry metadata marker."
    expected = list(range(1, len(entries) + 1))
    actual = [entry.entry_seq for entry in entries]
    if actual != expected:
        return f"Expected contiguous entry_seq values {expected}, found {actual}."
    return None


def section_keys_in_text(text: str) -> list[str]:
    return protocol_sections.section_keys_in_text(text)


def missing_section_keys(text: str, required_keys: Iterable[str]) -> list[str]:
    return protocol_sections.missing_section_keys(text, required_keys)


def duplicate_section_keys(text: str) -> list[str]:
    return protocol_sections.duplicate_section_keys(text)


def unknown_section_keys(text: str, allowed_keys: Iterable[str]) -> list[str]:
    return protocol_sections.unknown_section_keys(text, allowed_keys)


def bridge_block_integrity(text: str) -> tuple[bool, str | None]:
    return bridge_blocks.bridge_block_integrity(text)


def exclude_block_integrity(text: str) -> tuple[bool, str | None]:
    return bridge_blocks.exclude_block_integrity(text)


def managed_exclude_block_text(text: str) -> str | None:
    return bridge_blocks.managed_exclude_block_text(text)


def to_posix_relative(from_dir: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_dir)).as_posix()


def detect_root_entry_files(project_root: Path) -> list[Path]:
    return bridge_blocks.detect_root_entry_files(project_root)


def known_storage_assets(storage_root: Path) -> set[Path]:
    return workspace_runtime.known_storage_assets(
        storage_root,
        required_files=MANAGED_ASSET_REQUIRED_FILES,
        optional_files=MANAGED_ASSET_OPTIONAL_FILES,
        required_directories=MANAGED_ASSET_REQUIRED_DIRECTORIES,
        managed_directories=MANAGED_ASSET_DIRECTORIES,
    )


def known_storage_asset_kind_map(storage_root: Path) -> dict[Path, str]:
    return workspace_runtime.known_storage_asset_kind_map(
        storage_root,
        required_files=MANAGED_ASSET_REQUIRED_FILES,
        optional_files=MANAGED_ASSET_OPTIONAL_FILES,
        required_directories=MANAGED_ASSET_REQUIRED_DIRECTORIES,
        managed_directories=MANAGED_ASSET_DIRECTORIES,
    )


def _matches_dynamic_storage_asset_rule(path: Path, storage_root: Path) -> bool:
    return workspace_runtime.matches_dynamic_storage_asset_rule(
        path,
        storage_root,
        dynamic_rules=MANAGED_ASSET_DYNAMIC_RULES,
    )


def unknown_storage_assets(storage_root: Path) -> list[Path]:
    return workspace_runtime.unknown_storage_assets(
        storage_root,
        required_files=MANAGED_ASSET_REQUIRED_FILES,
        optional_files=MANAGED_ASSET_OPTIONAL_FILES,
        required_directories=MANAGED_ASSET_REQUIRED_DIRECTORIES,
        managed_directories=MANAGED_ASSET_DIRECTORIES,
        dynamic_rules=MANAGED_ASSET_DYNAMIC_RULES,
    )


def is_official_temp_storage_asset(path: Path, storage_root: Path) -> bool:
    return workspace_runtime.is_official_temp_storage_asset(
        path,
        storage_root,
        required_files=MANAGED_ASSET_REQUIRED_FILES,
        optional_files=MANAGED_ASSET_OPTIONAL_FILES,
        dynamic_rules=MANAGED_ASSET_DYNAMIC_RULES,
    )


def render_bridge_block(workspace: WorkspaceInfo, target_file: Path) -> str:
    return bridge_blocks.render_bridge_block(workspace, target_file)


def replace_or_insert_bridge(text: str, block: str) -> str:
    return bridge_blocks.replace_or_insert_bridge(text, block)


def remove_bridge_block(text: str) -> tuple[str, bool]:
    return bridge_blocks.remove_bridge_block(text)


def daily_logs_dir(storage_root: Path) -> Path:
    return workspace_runtime.daily_logs_dir(storage_root)


def storage_root_boundary_issue(project_root: Path, storage_root: Path, storage_mode: str) -> str | None:
    return workspace_runtime.storage_root_boundary_issue(project_root, storage_root, storage_mode)
