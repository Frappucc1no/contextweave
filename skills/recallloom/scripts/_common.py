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
METADATA_PATH = PACKAGE_ROOT / "package-metadata.json"
MANAGED_ASSETS_OVERRIDE_ENV = "RECALLLOOM_MANAGED_ASSETS_PATH"
DEFAULT_MANAGED_ASSETS_PATH = PACKAGE_ROOT / "managed-assets.json"
MANAGED_ASSETS_PATH = Path(os.environ.get(MANAGED_ASSETS_OVERRIDE_ENV, str(DEFAULT_MANAGED_ASSETS_PATH))).expanduser().resolve()
CONTEXT_DIRNAME = ".recallloom"
VISIBLE_DIRNAME = "recallloom"
DEFAULT_STORAGE_MODE = "hidden"
VISIBLE_STORAGE_MODE = "visible"
SUPPORTED_STORAGE_MODES = {DEFAULT_STORAGE_MODE, VISIBLE_STORAGE_MODE}
SUPPORTED_DYNAMIC_ASSET_RULE_KINDS = {"iso_daily_log", "recovery_proposal", "review_record"}
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

DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_DIRS = {
    ".git",
    ".hg",
    ".svn",
    ".idea",
    ".vscode",
    ".venv",
    "venv",
    "__pycache__",
    "node_modules",
    "dist",
    "build",
    "coverage",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}

DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_FILES = {
    ".DS_Store",
    ".recallloom.write.lock",
}

ATTACH_SCAN_HARD_BLOCK_PATTERNS = (
    re.compile(r"\bignore (all )?(previous|prior|above) (instructions|rules|guidance)\b", re.I),
    re.compile(r"\b(disregard|override) (the )?(system prompt|developer message|instructions?)\b", re.I),
    re.compile(r"\b(reveal|print|dump|show|exfiltrat\w*)\b.{0,40}\b(secret|token|password|api key|credential|ssh key|env)\b", re.I | re.S),
)

ATTACH_SCAN_WARNING_PATTERNS = (
    re.compile(r"\b(secret|token|password|credential|api key)\b", re.I),
    re.compile(r"\bignore\b", re.I),
)


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
        if normalized_item in {".", ""} or normalized_item.startswith("../") or normalized_item.startswith("/"):
            raise RuntimeError(f"{field} contains an invalid relative path '{item}': {source_path}")
        if normalized_item in seen:
            raise RuntimeError(f"{field} contains a duplicate path '{normalized_item}': {source_path}")
        seen.add(normalized_item)
        normalized.append(normalized_item)
    return normalized


def extract_section_text(text: str, section_key: str) -> str:
    lines = text.splitlines()
    start_marker = f"<!-- section: {section_key} -->"
    start_idx = None
    for idx, line in enumerate(lines):
        if line.strip() == start_marker:
            start_idx = idx + 1
            break
    if start_idx is None:
        return ""

    collected: list[str] = []
    for line in lines[start_idx:]:
        if line.strip().startswith("<!-- section: "):
            break
        collected.append(line)
    return "\n".join(collected).strip()


def markdown_heading_titles(text: str) -> list[str]:
    headings: list[str] = []
    for line in text.splitlines():
        match = MARKDOWN_HEADING_RE.match(line)
        if not match:
            continue
        title = HEADING_NUMBER_PREFIX_RE.sub("", match.group("title").strip())
        title = title.strip().strip(":：-").strip()
        if title:
            headings.append(title.casefold())
    return headings


def missing_recovery_headings(text: str, heading_groups: tuple[tuple[str, ...], ...]) -> list[str]:
    headings = set(markdown_heading_titles(text))
    missing: list[str] = []
    for group in heading_groups:
        normalized_group = {item.casefold() for item in group}
        if headings.isdisjoint(normalized_group):
            missing.append(group[0])
    return missing


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
    lowered = text.casefold()
    return [keyword for keyword in UPDATE_PROTOCOL_TIME_POLICY_KEYWORDS if keyword.casefold() in lowered]


def load_managed_assets_metadata() -> dict:
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
        if not isinstance(kind, str) or kind not in SUPPORTED_DYNAMIC_ASSET_RULE_KINDS:
            raise RuntimeError(
                "dynamic_file_rules.kind must be one of "
                f"{sorted(SUPPORTED_DYNAMIC_ASSET_RULE_KINDS)}: {MANAGED_ASSETS_PATH}"
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


try:
    PACKAGE_METADATA = load_package_metadata()
    MANAGED_ASSETS_METADATA = load_managed_assets_metadata()
except RuntimeError as exc:
    raise SystemExit(str(exc))
PACKAGE_NAME = PACKAGE_METADATA["package_name"]
DISPLAY_NAME = PACKAGE_METADATA["display_name"]
PACKAGE_VERSION = PACKAGE_METADATA["package_version"]
CURRENT_PROTOCOL_VERSION = PACKAGE_METADATA["protocol_version"]
SUPPORTED_PROTOCOL_VERSIONS = set(PACKAGE_METADATA["supported_protocol_versions"])
MINIMUM_PYTHON_VERSION = PACKAGE_METADATA["minimum_python_version"]
MINIMUM_PYTHON_VERSION_PARTS = tuple(int(part) for part in MINIMUM_PYTHON_VERSION.split("."))
DEFAULT_WORKSPACE_LANGUAGE = PACKAGE_METADATA["supported_workspace_languages"][0]
SUPPORTED_WORKSPACE_LANGUAGES = set(PACKAGE_METADATA["supported_workspace_languages"])
MANAGED_ASSET_REQUIRED_FILES = tuple(MANAGED_ASSETS_METADATA["required_files"])
MANAGED_ASSET_OPTIONAL_FILES = tuple(MANAGED_ASSETS_METADATA["optional_files"])
MANAGED_ASSET_REQUIRED_DIRECTORIES = tuple(MANAGED_ASSETS_METADATA["required_directories"])
MANAGED_ASSET_DIRECTORIES = tuple(MANAGED_ASSETS_METADATA["managed_directories"])
MANAGED_ASSET_DYNAMIC_RULES = tuple(MANAGED_ASSETS_METADATA["dynamic_file_rules"])

FILE_KEYS = {
    "config": "config.json",
    "state": "state.json",
    "context_brief": "context_brief.md",
    "rolling_summary": "rolling_summary.md",
    "update_protocol": "update_protocol.md",
}


def is_required_storage_file(rel_path: str) -> bool:
    return PurePosixPath(rel_path).as_posix() in MANAGED_ASSET_REQUIRED_FILES


def is_optional_storage_file(rel_path: str) -> bool:
    return PurePosixPath(rel_path).as_posix() in MANAGED_ASSET_OPTIONAL_FILES


def is_required_storage_directory(rel_path: str) -> bool:
    return PurePosixPath(rel_path).as_posix() in MANAGED_ASSET_REQUIRED_DIRECTORIES

SECTION_KEYS = {
    "context_brief": ["mission", "current_phase", "source_of_truth", "core_workflow", "boundaries"],
    "rolling_summary": [
        "current_state",
        "active_judgments",
        "risks_open_questions",
        "next_step",
        "recent_pivots",
    ],
    "daily_log": [
        "work_completed",
        "confirmed_facts",
        "key_decisions",
        "risks_blockers",
        "recommended_next_step",
    ],
    "update_protocol": ["project_specific_overrides"],
}

OPTIONAL_SECTION_KEYS = {
    "context_brief": ["audience_stakeholders", "scope"],
}

CONTEXT_BRIEF_RENDER_ORDER = [
    "mission",
    "audience_stakeholders",
    "current_phase",
    "scope",
    "source_of_truth",
    "core_workflow",
    "boundaries",
]

LABELS = {
    "en": {
        "context_brief": {
            "mission": "Mission",
            "audience_stakeholders": "Audience / Stakeholders",
            "current_phase": "Current Phase",
            "scope": "Scope",
            "source_of_truth": "Source of Truth",
            "core_workflow": "Core Workflow",
            "boundaries": "Boundaries",
        },
        "rolling_summary": {
            "current_state": "Current State",
            "active_judgments": "Active Judgments",
            "risks_open_questions": "Risks / Open Questions",
            "next_step": "Next Step",
            "recent_pivots": "Recent Pivots",
        },
        "daily_log": {
            "work_completed": "Work Completed",
            "confirmed_facts": "Confirmed Facts",
            "key_decisions": "Key Decisions",
            "risks_blockers": "Risks / Blockers",
            "recommended_next_step": "Recommended Next Step",
        },
        "update_protocol": {
            "title": "Project-Specific Overrides",
            "body": [
                "Use this file to define project-local overrides for:",
                "",
                "- read order",
                "- write rules",
                "- archive rules",
                "- evidence priority",
                "- stronger project constraints",
            ],
        },
    },
    "zh-CN": {
        "context_brief": {
            "mission": "项目使命",
            "audience_stakeholders": "受众与相关方",
            "current_phase": "当前阶段",
            "scope": "范围",
            "source_of_truth": "事实来源",
            "core_workflow": "核心工作流",
            "boundaries": "边界与约束",
        },
        "rolling_summary": {
            "current_state": "当前状态",
            "active_judgments": "当前判断",
            "risks_open_questions": "风险与未决问题",
            "next_step": "下一步",
            "recent_pivots": "近期判断反转",
        },
        "daily_log": {
            "work_completed": "完成工作",
            "confirmed_facts": "确认事实",
            "key_decisions": "关键决策",
            "risks_blockers": "风险与阻塞",
            "recommended_next_step": "建议下一步",
        },
        "update_protocol": {
            "title": "项目级覆盖规则",
            "body": [
                "使用此文件定义项目级覆盖规则：",
                "",
                "- 读取顺序",
                "- 写入规则",
                "- 归档规则",
                "- 证据优先级",
                "- 更强的项目约束",
            ],
        },
    },
}

LAST_WRITER_RE = re.compile(
    r"^<!-- last-writer: \[(?P<tool>[^\]]+)\] \| (?P<date>\d{4}-\d{2}-\d{2}) -->$"
)
FILE_STATE_RE = re.compile(
    r"^<!-- file-state: revision=(?P<revision>\d+) \| updated-at=(?P<updated_at>[^ ]+) \| writer-id=(?P<writer_id>[^|]+?) \| base-workspace-revision=(?P<base_workspace_revision>\d+) -->$"
)
DAILY_LOG_ENTRY_RE = re.compile(
    r"^<!-- daily-log-entry: entry-id=(?P<entry_id>[^ ]+) \| created-at=(?P<created_at>[^ ]+) \| writer-id=(?P<writer_id>[^|]+?) \| entry-seq=(?P<entry_seq>\d+) -->$"
)
DAILY_LOG_SCAFFOLD_RE = re.compile(r"^<!-- daily-log-scaffold: true -->$")
DATE_FILE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}\.md$")
FILE_MARKER_RE = re.compile(
    r"^<!-- recallloom:file=(?P<file_key>[a-z_]+) version=(?P<version>[0-9]+\.[0-9]+(?:\.[0-9]+)*) lang=(?P<lang>[^ ]+) -->$"
)
SECTION_MARKER_RE = re.compile(r"^<!-- section: (?P<section_key>[a-z_]+) -->$")
BRIDGE_START = "<!-- RecallLoom managed bridge start -->"
BRIDGE_END = "<!-- RecallLoom managed bridge end -->"
EXCLUDE_BLOCK_START = "# RecallLoom managed block start"
EXCLUDE_BLOCK_END = "# RecallLoom managed block end"
ROOT_ENTRY_CANDIDATES = [
    Path(path_str) for path_str in PACKAGE_METADATA["supported_bridge_targets"]
]
ROOT_ENTRY_CANDIDATE_STRINGS = {path.as_posix() for path in ROOT_ENTRY_CANDIDATES}


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
    if any(ch in value for ch in {"|", "\n", "\r"}):
        raise ConfigContractError(
            "writer_id may not contain '|', or line-break characters because it is embedded in machine-readable markers"
        )
    return value.strip()
WORKSPACE_LOCK_FILENAME = ".recallloom.write.lock"
STALE_LOCK_MAX_AGE_SECONDS = 6 * 3600


@dataclass(frozen=True)
class WorkspaceInfo:
    project_root: Path
    storage_root: Path
    storage_mode: str
    workspace_language: str
    config_path: Path | None
    declared_storage_mode: str | None = None
    storage_mode_matches_path: bool = True
    protocol_version: str | None = None
    protocol_version_supported: bool = True


@dataclass(frozen=True)
class RecoveryWorkspaceInfo:
    project_root: Path
    storage_root: Path
    storage_mode: str


@dataclass(frozen=True)
class FileMarkerInfo:
    file_key: str
    version: str
    language: str


@dataclass(frozen=True)
class FileStateInfo:
    revision: int
    updated_at: str
    writer_id: str
    base_workspace_revision: int


@dataclass(frozen=True)
class DailyLogEntryInfo:
    entry_id: str
    created_at: str
    writer_id: str
    entry_seq: int


@dataclass(frozen=True)
class ValidationFinding:
    level: str
    code: str
    message: str
    path: Path


class StorageResolutionError(RuntimeError):
    """Raised when RecallLoom storage roots are ambiguous or invalid."""


class ConfigContractError(RuntimeError):
    """Raised when config.json is malformed or violates the protocol contract."""


class EnvironmentContractError(RuntimeError):
    """Raised when the runtime environment does not satisfy package requirements."""


class LockBusyError(RuntimeError):
    """Raised when a project-scoped write lock is already held."""


def normalize_start_path(raw_path: str | Path) -> Path:
    try:
        path = Path(raw_path).expanduser().resolve()
        return path.parent if path.is_file() else path
    except OSError as exc:
        raise StorageResolutionError(f"Failed to resolve start path {raw_path}: {exc}") from exc


def ensure_supported_python_version() -> None:
    current = sys.version_info[: len(MINIMUM_PYTHON_VERSION_PARTS)]
    if current < MINIMUM_PYTHON_VERSION_PARTS:
        raise EnvironmentContractError(
            "RecallLoom helper scripts require "
            f"Python {MINIMUM_PYTHON_VERSION}+; current interpreter is "
            f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
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
    return project_root / WORKSPACE_LOCK_FILENAME


def load_lock_payload(lock_path: Path) -> dict:
    try:
        data = json.loads(read_text(lock_path))
    except (FileNotFoundError, json.JSONDecodeError, UnicodeDecodeError, OSError):
        return {}
    return data if isinstance(data, dict) else {}


def parse_lock_timestamp(value: str | None) -> datetime | None:
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed


def pid_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    else:
        return True


def reclaim_stale_workspace_lock(lock_path: Path) -> bool:
    if not lock_path.exists():
        return False

    payload = load_lock_payload(lock_path)
    pid = payload.get("pid")
    if not isinstance(pid, int):
        return False
    if pid_is_alive(pid):
        return False
    try:
        lock_path.unlink()
        return True
    except FileNotFoundError:
        return False


@contextmanager
def workspace_write_lock(project_root: Path, owner: str):
    lock_path = project_lock_path(project_root)
    fd: int | None = None
    for _ in range(2):
        try:
            fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            payload = json.dumps({"owner": owner, "pid": os.getpid(), "created_at": now_iso_timestamp()})
            os.write(fd, payload.encode("utf-8"))
            os.fsync(fd)
            break
        except FileExistsError:
            if not reclaim_stale_workspace_lock(lock_path):
                lock_payload = load_lock_payload(lock_path)
                lock_owner = lock_payload.get("owner", "unknown")
                lock_pid = lock_payload.get("pid", "unknown")
                lock_created_at = lock_payload.get("created_at", "unknown")
                raise LockBusyError(
                    "Refusing to continue because another RecallLoom mutating operation appears to be running for "
                    f"{project_root} (owner={lock_owner}, pid={lock_pid}, created_at={lock_created_at}). "
                    "If this lock is stale or malformed, inspect or remove it explicitly with unlock_write_lock.py."
                )
    else:
        raise LockBusyError(
            f"Refusing to continue because a stale RecallLoom lock could not be reclaimed for {project_root}."
        )
    try:
        yield lock_path
    finally:
        if fd is not None:
            os.close(fd)
        try:
            lock_path.unlink()
        except FileNotFoundError:
            pass


def config_payload(
    *,
    storage_mode: str,
    workspace_language: str,
    created_by: str,
    created_at: str,
    protocol_version: str = CURRENT_PROTOCOL_VERSION,
) -> dict:
    return {
        "protocol_version": protocol_version,
        "storage_mode": storage_mode,
        "workspace_language": workspace_language,
        "created_by": created_by,
        "created_at": created_at,
    }


def initial_workspace_state(
    *,
    tool_name: str,
    timestamp: str,
    git_exclude_mode: str,
) -> dict:
    state = {
        "workspace_revision": 1,
        "update_protocol_revision": 1,
        "git_exclude_mode": git_exclude_mode,
        "bridged_entries": {},
        "files": {
            "context_brief": {
                "file_revision": 1,
                "updated_at": timestamp,
                "writer_id": tool_name,
                "base_workspace_revision": 1,
            },
            "rolling_summary": {
                "file_revision": 1,
                "updated_at": timestamp,
                "writer_id": tool_name,
                "base_workspace_revision": 1,
            },
            "update_protocol": {
                "file_revision": 1,
                "updated_at": timestamp,
                "writer_id": tool_name,
                "base_workspace_revision": 1,
            },
        },
        "daily_logs": {
            "latest_file": None,
            "latest_entry_id": None,
            "latest_entry_seq": 0,
            "entry_count": 0,
        },
    }
    return state


def load_workspace_state(path: Path) -> dict:
    try:
        data = load_json(path)
    except FileNotFoundError as exc:
        raise ConfigContractError(f"Missing state file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigContractError(f"Malformed JSON in state file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigContractError(f"State file is not valid UTF-8: {path}") from exc
    if not isinstance(data, dict):
        raise ConfigContractError(f"State file must contain a JSON object: {path}")
    required = {
        "workspace_revision",
        "update_protocol_revision",
        "git_exclude_mode",
        "bridged_entries",
        "files",
        "daily_logs",
    }
    missing = sorted(required.difference(data.keys()))
    if missing:
        raise ConfigContractError(f"State file is missing required fields {missing}: {path}")

    if not isinstance(data["workspace_revision"], int) or data["workspace_revision"] < 1:
        raise ConfigContractError(
            f"state.json workspace_revision must be a positive integer: {path}"
        )
    if not isinstance(data["update_protocol_revision"], int) or data["update_protocol_revision"] < 1:
        raise ConfigContractError(
            f"state.json update_protocol_revision must be a positive integer: {path}"
        )
    if data["git_exclude_mode"] not in {"managed", "skipped", "not_applicable"}:
        raise ConfigContractError(
            f"state.json git_exclude_mode must be one of managed/skipped/not_applicable: {path}"
        )

    bridged_entries = data["bridged_entries"]
    if not isinstance(bridged_entries, dict):
        raise ConfigContractError(f"state.json bridged_entries must be an object: {path}")
    for rel_target, bridge_state in bridged_entries.items():
        if not isinstance(rel_target, str) or not rel_target.strip():
            raise ConfigContractError(
                f"state.json bridged_entries keys must be non-empty strings: {path}"
            )
        if rel_target not in ROOT_ENTRY_CANDIDATE_STRINGS:
            raise ConfigContractError(
                "state.json bridged_entries keys must be supported root entry file paths "
                f"{sorted(ROOT_ENTRY_CANDIDATE_STRINGS)}: {path}"
            )
        if not isinstance(bridge_state, dict):
            raise ConfigContractError(
                f"state.json bridged_entries values must be objects: {path}"
            )
        if "update_protocol_revision_seen" in bridge_state:
            value = bridge_state["update_protocol_revision_seen"]
            if not isinstance(value, int) or value < 1:
                raise ConfigContractError(
                    f"state.json bridged_entries.{rel_target}.update_protocol_revision_seen must be a positive integer: {path}"
                )
        if "latest_daily_log_seen" in bridge_state:
            value = bridge_state["latest_daily_log_seen"]
            if value is not None and (not isinstance(value, str) or not value.strip()):
                raise ConfigContractError(
                    f"state.json bridged_entries.{rel_target}.latest_daily_log_seen must be null or a non-empty string: {path}"
                )
        if "updated_at" in bridge_state:
            value = bridge_state["updated_at"]
            if not isinstance(value, str) or not value.strip():
                raise ConfigContractError(
                    f"state.json bridged_entries.{rel_target}.updated_at must be a non-empty string: {path}"
                )

    files = data["files"]
    if not isinstance(files, dict):
        raise ConfigContractError(f"state.json files must be an object: {path}")
    for file_key in ("context_brief", "rolling_summary", "update_protocol"):
        entry = files.get(file_key)
        if not isinstance(entry, dict):
            raise ConfigContractError(
                f"state.json files.{file_key} must be an object: {path}"
            )
        if not isinstance(entry.get("file_revision"), int) or entry["file_revision"] < 1:
            raise ConfigContractError(
                f"state.json files.{file_key}.file_revision must be a positive integer: {path}"
            )
        if not isinstance(entry.get("updated_at"), str) or not entry["updated_at"].strip():
            raise ConfigContractError(
                f"state.json files.{file_key}.updated_at must be a non-empty string: {path}"
            )
        if not isinstance(entry.get("writer_id"), str) or not entry["writer_id"].strip():
            raise ConfigContractError(
                f"state.json files.{file_key}.writer_id must be a non-empty string: {path}"
            )
        if (
            not isinstance(entry.get("base_workspace_revision"), int)
            or entry["base_workspace_revision"] < 1
        ):
            raise ConfigContractError(
                f"state.json files.{file_key}.base_workspace_revision must be a positive integer: {path}"
            )

    daily_logs = data["daily_logs"]
    if not isinstance(daily_logs, dict):
        raise ConfigContractError(f"state.json daily_logs must be an object: {path}")
    latest_file = daily_logs.get("latest_file")
    if latest_file is not None and (not isinstance(latest_file, str) or not latest_file.strip()):
        raise ConfigContractError(
            f"state.json daily_logs.latest_file must be null or a non-empty string: {path}"
        )
    latest_entry_id = daily_logs.get("latest_entry_id")
    if latest_entry_id is not None and (
        not isinstance(latest_entry_id, str) or not latest_entry_id.strip()
    ):
        raise ConfigContractError(
            f"state.json daily_logs.latest_entry_id must be null or a non-empty string: {path}"
        )
    latest_entry_seq = daily_logs.get("latest_entry_seq")
    if not isinstance(latest_entry_seq, int) or latest_entry_seq < 0:
        raise ConfigContractError(
            f"state.json daily_logs.latest_entry_seq must be a non-negative integer: {path}"
        )
    entry_count = daily_logs.get("entry_count")
    if not isinstance(entry_count, int) or entry_count < 0:
        raise ConfigContractError(
            f"state.json daily_logs.entry_count must be a non-negative integer: {path}"
        )
    if entry_count < latest_entry_seq:
        raise ConfigContractError(
            f"state.json daily_logs.entry_count cannot be smaller than latest_entry_seq: {path}"
        )
    if latest_file is None:
        if latest_entry_id is not None or latest_entry_seq != 0 or entry_count != 0:
            raise ConfigContractError(
                "state.json daily_logs must use the null/zero cursor shape when no active daily log exists: "
                f"{path}"
            )
    else:
        latest_parts = PurePosixPath(latest_file).parts
        if len(latest_parts) != 2 or latest_parts[0] != "daily_logs" or not DATE_FILE_RE.match(latest_parts[1]):
            raise ConfigContractError(
                "state.json daily_logs.latest_file must point to an active ISO-dated daily log under "
                f"daily_logs/: {path}"
            )
        try:
            parse_iso_date(Path(latest_parts[1]).stem)
        except ValueError as exc:
            raise ConfigContractError(
                "state.json daily_logs.latest_file must use a valid ISO-dated daily log filename under "
                f"daily_logs/: {path}"
            ) from exc
        if latest_entry_id is None or latest_entry_seq < 1 or entry_count < 1:
            raise ConfigContractError(
                "state.json daily_logs must record a non-null latest_entry_id and positive entry counters "
                f"when latest_file is set: {path}"
            )
    if "updated_at" in daily_logs:
        updated_at = daily_logs["updated_at"]
        if not isinstance(updated_at, str) or not updated_at.strip():
            raise ConfigContractError(
                f"state.json daily_logs.updated_at must be a non-empty string when present: {path}"
            )
    return data


def validate_storage_mode(value: str) -> str:
    if value not in SUPPORTED_STORAGE_MODES:
        raise ConfigContractError(f"Unsupported storage_mode: {value}")
    return value


def validate_workspace_language(value: str) -> str:
    if value not in SUPPORTED_WORKSPACE_LANGUAGES:
        raise ConfigContractError(f"Unsupported workspace_language: {value}")
    return value


def validate_protocol_version(value: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ConfigContractError("protocol_version must be a non-empty string")
    if not PROTOCOL_VERSION_RE.match(value):
        raise ConfigContractError(
            f"protocol_version must use dotted string form such as '1.0', got: {value}"
        )
    return value


def load_and_validate_config(
    path: Path,
    default_storage_mode: str,
    *,
    allow_unsupported_version: bool = False,
    allow_storage_mode_mismatch: bool = False,
) -> dict:
    try:
        data = load_json(path)
    except FileNotFoundError as exc:
        raise ConfigContractError(f"Missing config file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise ConfigContractError(f"Malformed JSON in config file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise ConfigContractError(f"Config file is not valid UTF-8: {path}") from exc
    except OSError as exc:
        raise ConfigContractError(f"Config file is not readable: {path} ({exc})") from exc

    if not isinstance(data, dict):
        raise ConfigContractError(f"Config file must contain a JSON object: {path}")

    required = {
        "protocol_version",
        "storage_mode",
        "workspace_language",
        "created_by",
        "created_at",
    }
    missing = sorted(required.difference(data.keys()))
    if missing:
        raise ConfigContractError(
            f"Config file is missing required fields {missing}: {path}"
        )

    storage_mode = validate_storage_mode(data.get("storage_mode", default_storage_mode))
    storage_mode_matches_path = storage_mode == default_storage_mode
    if not storage_mode_matches_path and not allow_storage_mode_mismatch:
        raise ConfigContractError(
            f"storage_mode '{storage_mode}' does not match the storage root implied by {path}"
        )
    workspace_language = validate_workspace_language(
        data.get("workspace_language", DEFAULT_WORKSPACE_LANGUAGE)
    )

    protocol_version = validate_protocol_version(data.get("protocol_version"))
    protocol_version_supported = protocol_version in SUPPORTED_PROTOCOL_VERSIONS
    if not protocol_version_supported and not allow_unsupported_version:
        raise ConfigContractError(
            f"Unsupported protocol_version {protocol_version} in config file: {path}"
        )

    created_by = data.get("created_by")
    created_at = data.get("created_at")
    if not isinstance(created_by, str) or not created_by.strip():
        raise ConfigContractError(f"created_by must be a non-empty string in config file: {path}")
    if not isinstance(created_at, str) or not created_at.strip():
        raise ConfigContractError(f"created_at must be a non-empty string in config file: {path}")

    return {
        "protocol_version": protocol_version,
        "protocol_version_supported": protocol_version_supported,
        "storage_mode": storage_mode,
        "storage_mode_matches_path": storage_mode_matches_path,
        "workspace_language": workspace_language,
        "created_by": created_by,
        "created_at": created_at,
    }


def hidden_storage_root(project_root: Path) -> Path:
    return project_root / CONTEXT_DIRNAME


def visible_storage_root(project_root: Path) -> Path:
    return project_root / VISIBLE_DIRNAME


def recovery_storage_roots(project_root: Path) -> list[Path]:
    roots: list[Path] = []
    hidden = hidden_storage_root(project_root)
    visible = visible_storage_root(project_root)
    if is_recovery_storage_candidate(project_root, hidden, DEFAULT_STORAGE_MODE):
        roots.append(hidden)
    if is_recovery_storage_candidate(project_root, visible, VISIBLE_STORAGE_MODE):
        roots.append(visible)
    return roots


def visible_root_has_sidecar_signals(storage_root: Path) -> bool:
    signals = {
        "config.json",
        "state.json",
        "context_brief.md",
        "rolling_summary.md",
        "update_protocol.md",
        "daily_logs",
    }
    if not storage_root.is_dir():
        return False
    return any((storage_root / name).exists() for name in signals)


def looks_like_installable_package_dir(storage_root: Path) -> bool:
    if not storage_root.is_dir():
        return False
    return (
        (storage_root / "package-metadata.json").is_file()
        and (storage_root / "SKILL.md").is_file()
        and (storage_root / "scripts").is_dir()
    )


def damaged_sidecar_reason(project_root: Path, storage_root: Path, storage_mode: str) -> str | None:
    config_path = storage_root / FILE_KEYS["config"]
    if config_path.is_file():
        return None

    if storage_mode == DEFAULT_STORAGE_MODE:
        if storage_root.is_file():
            return (
                f"Detected a damaged RecallLoom hidden sidecar under {project_root}: "
                f"{storage_root} exists but {config_path} is missing."
            )
        if storage_root.is_dir() and any(storage_root.iterdir()):
            return (
                f"Detected a damaged RecallLoom hidden sidecar under {project_root}: "
                f"{storage_root} exists and is non-empty, but {config_path} is missing."
            )
        return None

    if storage_root.is_dir():
        if looks_like_installable_package_dir(storage_root):
            return None
        if visible_root_has_sidecar_signals(storage_root):
            return (
                f"Detected a damaged RecallLoom visible sidecar under {project_root}: "
                f"{storage_root} contains RecallLoom sidecar files, but {config_path} is missing."
            )
    return None


def is_recovery_storage_candidate(project_root: Path, storage_root: Path, storage_mode: str) -> bool:
    if (storage_root / FILE_KEYS["config"]).is_file():
        return True
    return damaged_sidecar_reason(project_root, storage_root, storage_mode) is not None


def infer_storage_mode_from_root(storage_root: Path) -> str:
    if storage_root.name == CONTEXT_DIRNAME:
        return DEFAULT_STORAGE_MODE
    if storage_root.name == VISIBLE_DIRNAME:
        return VISIBLE_STORAGE_MODE
    raise StorageResolutionError(f"Cannot infer RecallLoom storage mode from path: {storage_root}")


def find_recovery_workspace(
    start_path: str | Path,
    *,
    requested_storage_mode: str | None = None,
) -> RecoveryWorkspaceInfo | None:
    start = normalize_start_path(start_path)
    if requested_storage_mode is not None:
        requested_storage_mode = validate_storage_mode(requested_storage_mode)

    for candidate in (start, *start.parents):
        roots = recovery_storage_roots(candidate)
        if not roots:
            continue

        if requested_storage_mode is not None:
            target_root = storage_root_for_mode(candidate, requested_storage_mode)
            if is_recovery_storage_candidate(candidate, target_root, requested_storage_mode):
                return RecoveryWorkspaceInfo(
                    project_root=candidate,
                    storage_root=target_root,
                    storage_mode=requested_storage_mode,
                )
            continue

        for root in roots:
            if start == root or root in start.parents:
                return RecoveryWorkspaceInfo(
                    project_root=candidate,
                    storage_root=root,
                    storage_mode=infer_storage_mode_from_root(root),
                )

        if len(roots) == 1:
            root = roots[0]
            return RecoveryWorkspaceInfo(
                project_root=candidate,
                storage_root=root,
                storage_mode=infer_storage_mode_from_root(root),
            )

        raise StorageResolutionError(
            f"Multiple RecallLoom storage roots exist under {candidate}. "
            "Re-run with an explicit storage mode or target a path inside the desired sidecar."
        )

    return None


def find_recovery_project_root(start_path: str | Path) -> Path:
    start = normalize_start_path(start_path)
    for candidate in (start, *start.parents):
        if project_lock_path(candidate).exists():
            return candidate
        if recovery_storage_roots(candidate):
            return candidate
    return start


def storage_root_for_mode(project_root: Path, storage_mode: str) -> Path:
    storage_mode = validate_storage_mode(storage_mode)
    if storage_mode == DEFAULT_STORAGE_MODE:
        return hidden_storage_root(project_root)
    return visible_storage_root(project_root)


def config_path_for_mode(project_root: Path, storage_mode: str) -> Path:
    return storage_root_for_mode(project_root, storage_mode) / FILE_KEYS["config"]


def file_path(workspace: WorkspaceInfo, file_key: str) -> Path:
    if file_key == "daily_logs_dir":
        return workspace.storage_root / "daily_logs"
    return workspace.storage_root / FILE_KEYS[file_key]


def file_marker(file_key: str, language: str, version: str = CURRENT_PROTOCOL_VERSION) -> str:
    return f"<!-- recallloom:file={file_key} version={version} lang={language} -->"


def file_state_marker(
    *,
    revision: int,
    updated_at: str,
    writer_id: str,
    base_workspace_revision: int,
) -> str:
    return (
        f"<!-- file-state: revision={revision} | updated-at={updated_at} | "
        f"writer-id={writer_id} | base-workspace-revision={base_workspace_revision} -->"
    )


def daily_log_entry_marker(
    *,
    entry_id: str,
    created_at: str,
    writer_id: str,
    entry_seq: int,
) -> str:
    return (
        f"<!-- daily-log-entry: entry-id={entry_id} | created-at={created_at} | "
        f"writer-id={writer_id} | entry-seq={entry_seq} -->"
    )


def daily_log_scaffold_marker() -> str:
    return "<!-- daily-log-scaffold: true -->"


def section_marker(section_key: str) -> str:
    return f"<!-- section: {section_key} -->"


def render_heading(level: int, heading: str) -> str:
    return "#" * level + " " + heading


def render_section_block(level: int, section_key: str, heading: str, body: list[str] | None = None) -> str:
    lines = [section_marker(section_key), render_heading(level, heading)]
    if body is None:
        lines.extend(["", "-"])
    else:
        lines.extend(["", *body])
    return "\n".join(lines)


def rolling_summary_header(tool_name: str, day: str) -> str:
    return f"<!-- last-writer: [{tool_name}] | {day} -->"


def render_context_brief_template(language: str, *, tool_name: str, timestamp: str, workspace_revision: int) -> str:
    language = validate_workspace_language(language)
    labels = LABELS[language]["context_brief"]
    parts = [
        file_marker("context_brief", language),
        file_state_marker(
            revision=1,
            updated_at=timestamp,
            writer_id=tool_name,
            base_workspace_revision=workspace_revision,
        ),
    ]
    for section_key in CONTEXT_BRIEF_RENDER_ORDER:
        parts.append("")
        parts.append(render_section_block(1, section_key, labels[section_key]))
    return "\n".join(parts) + "\n"


def render_rolling_summary_template(tool_name: str, day: str, language: str, *, timestamp: str, workspace_revision: int) -> str:
    language = validate_workspace_language(language)
    labels = LABELS[language]["rolling_summary"]
    guidance = {
        "en": {
            "current_state": [
                "Write the validated handoff-first state here:",
                "",
                "- Active state",
                "- Relevant files",
                "- Critical context",
            ],
            "active_judgments": [
                "Record the coordination judgments that matter right now:",
                "",
                "- Key decisions",
                "- Active assumptions",
                "- Tradeoffs in force",
            ],
            "risks_open_questions": [
                "Make blocker visibility explicit:",
                "",
                "- Blocked items",
                "- Open questions",
                "- External dependencies",
            ],
            "next_step": [
                "Describe the handoff-first next move:",
                "",
                "- Active task",
                "- Owner or role when known",
                "- Immediate next action",
            ],
            "recent_pivots": [
                "-",
            ],
        },
        "zh-CN": {
            "current_state": [
                "这里优先写 handoff-first 的已确认当前状态：",
                "",
                "- 当前活跃状态",
                "- 相关文件",
                "- 关键上下文",
            ],
            "active_judgments": [
                "这里记录当前真正影响推进的判断：",
                "",
                "- 关键决策",
                "- 当前假设",
                "- 仍在生效的取舍",
            ],
            "risks_open_questions": [
                "把阻塞与未决问题写清楚：",
                "",
                "- 当前阻塞",
                "- 未决问题",
                "- 外部依赖",
            ],
            "next_step": [
                "这里写 handoff-first 的下一步：",
                "",
                "- 当前任务",
                "- 已知负责人或角色",
                "- 立刻要做的动作",
            ],
            "recent_pivots": [
                "-",
            ],
        },
    }[language]
    parts = [
        file_marker("rolling_summary", language),
        rolling_summary_header(tool_name, day),
        file_state_marker(
            revision=1,
            updated_at=timestamp,
            writer_id=tool_name,
            base_workspace_revision=workspace_revision,
        ),
    ]
    for section_key in SECTION_KEYS["rolling_summary"]:
        parts.append("")
        block = render_section_block(1, section_key, labels[section_key], guidance[section_key])
        parts.append(block)
    return "\n".join(parts) + "\n"


def render_daily_log_template(language: str, *, tool_name: str, timestamp: str) -> str:
    language = validate_workspace_language(language)
    labels = LABELS[language]["daily_log"]
    parts = [
        file_marker("daily_log", language),
        daily_log_scaffold_marker(),
    ]
    for section_key in SECTION_KEYS["daily_log"]:
        parts.append("")
        parts.append(render_section_block(1, section_key, labels[section_key]))
    return "\n".join(parts) + "\n"


def render_update_protocol_template(language: str, *, tool_name: str, timestamp: str, workspace_revision: int) -> str:
    language = validate_workspace_language(language)
    labels = LABELS[language]["update_protocol"]
    parts = [
        file_marker("update_protocol", language),
        file_state_marker(
            revision=1,
            updated_at=timestamp,
            writer_id=tool_name,
            base_workspace_revision=workspace_revision,
        ),
        "",
        render_section_block(1, "project_specific_overrides", labels["title"], labels["body"]),
    ]
    return "\n".join(parts) + "\n"


def render_template(
    file_key: str,
    *,
    tool_name: str,
    day: str,
    language: str,
    timestamp: str,
    workspace_revision: int,
) -> str:
    if file_key == "context_brief":
        return render_context_brief_template(language, tool_name=tool_name, timestamp=timestamp, workspace_revision=workspace_revision)
    if file_key == "rolling_summary":
        return render_rolling_summary_template(tool_name, day, language, timestamp=timestamp, workspace_revision=workspace_revision)
    if file_key == "daily_log":
        return render_daily_log_template(language, tool_name=tool_name, timestamp=timestamp)
    if file_key == "update_protocol":
        return render_update_protocol_template(language, tool_name=tool_name, timestamp=timestamp, workspace_revision=workspace_revision)
    raise KeyError(file_key)


def detect_workspace(
    project_root: Path,
    *,
    allow_unsupported_version: bool = False,
    allow_storage_mode_mismatch: bool = False,
) -> WorkspaceInfo | None:
    hidden_root = hidden_storage_root(project_root)
    hidden_config = hidden_root / FILE_KEYS["config"]
    visible_root = visible_storage_root(project_root)
    visible_config = visible_root / FILE_KEYS["config"]

    try:
        hidden_exists = hidden_config.is_file()
        visible_exists = visible_config.is_file()
        hidden_damaged = damaged_sidecar_reason(project_root, hidden_root, DEFAULT_STORAGE_MODE)
        visible_damaged = damaged_sidecar_reason(project_root, visible_root, VISIBLE_STORAGE_MODE)
    except OSError as exc:
        raise ConfigContractError(
                f"Failed to inspect RecallLoom storage roots under {project_root}: {exc}"
        ) from exc

    if hidden_exists and visible_exists:
        raise StorageResolutionError(
            f"Conflicting RecallLoom storage roots found under {project_root}: "
            f"{hidden_root} and {visible_root}. Resolve the conflict before continuing."
        )

    if hidden_exists:
        if visible_damaged is not None:
            raise StorageResolutionError(
                f"Conflicting RecallLoom storage roots found under {project_root}: "
                f"{hidden_root} is valid, but {visible_root} is a damaged visible sidecar. "
                "Resolve the conflict before continuing."
            )
        data = load_and_validate_config(
            hidden_config,
            DEFAULT_STORAGE_MODE,
            allow_unsupported_version=allow_unsupported_version,
            allow_storage_mode_mismatch=allow_storage_mode_mismatch,
        )
        return WorkspaceInfo(
            project_root=project_root,
            storage_root=hidden_root,
            storage_mode=DEFAULT_STORAGE_MODE,
            workspace_language=data["workspace_language"],
            config_path=hidden_config,
            declared_storage_mode=data["storage_mode"],
            storage_mode_matches_path=data["storage_mode_matches_path"],
            protocol_version=data["protocol_version"],
            protocol_version_supported=data["protocol_version_supported"],
        )

    if visible_exists:
        if hidden_damaged is not None:
            raise StorageResolutionError(
                f"Conflicting RecallLoom storage roots found under {project_root}: "
                f"{visible_root} is valid, but {hidden_root} is a damaged hidden sidecar. "
                "Resolve the conflict before continuing."
            )
        data = load_and_validate_config(
            visible_config,
            VISIBLE_STORAGE_MODE,
            allow_unsupported_version=allow_unsupported_version,
            allow_storage_mode_mismatch=allow_storage_mode_mismatch,
        )
        return WorkspaceInfo(
            project_root=project_root,
            storage_root=visible_root,
            storage_mode=VISIBLE_STORAGE_MODE,
            workspace_language=data["workspace_language"],
            config_path=visible_config,
            declared_storage_mode=data["storage_mode"],
            storage_mode_matches_path=data["storage_mode_matches_path"],
            protocol_version=data["protocol_version"],
            protocol_version_supported=data["protocol_version_supported"],
        )

    if hidden_damaged is not None and visible_damaged is not None:
        raise StorageResolutionError(
            f"Detected conflicting damaged RecallLoom storage roots under {project_root}: "
            f"{hidden_root} and {visible_root}. Resolve the conflict before continuing."
        )
    if hidden_damaged is not None:
        raise ConfigContractError(hidden_damaged)
    if visible_damaged is not None:
        raise ConfigContractError(visible_damaged)

    return None


def find_recallloom_root(
    start_path: str | Path,
    *,
    allow_unsupported_version: bool = False,
    allow_storage_mode_mismatch: bool = False,
) -> WorkspaceInfo | None:
    start = normalize_start_path(start_path)
    for candidate in (start, *start.parents):
        workspace = detect_workspace(
            candidate,
            allow_unsupported_version=allow_unsupported_version,
            allow_storage_mode_mismatch=allow_storage_mode_mismatch,
        )
        if workspace is not None:
            return workspace
    return None

def ensure_git_exclude_entry(project_root: Path, entry: str = f"{CONTEXT_DIRNAME}/") -> bool:
    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        return False

    exclude_path = git_dir / "info" / "exclude"
    exclude_path.parent.mkdir(parents=True, exist_ok=True)
    block = [
        EXCLUDE_BLOCK_START,
        entry,
        EXCLUDE_BLOCK_END,
    ]
    if exclude_path.exists():
        current = exclude_path.read_text(encoding="utf-8")
        ok, reason = exclude_block_integrity(current)
        if not ok:
            detail_map = {
                "exclude_start_end_mismatch": "managed block start/end markers are mismatched",
                "exclude_duplicate_blocks": "multiple managed exclude blocks are present",
                "exclude_order_invalid": "managed block markers are out of order",
            }
            detail = detail_map.get(reason, "the managed exclude block is malformed")
            raise ConfigContractError(
                f"Refusing to update .git/info/exclude because {detail}: {exclude_path}"
            )
        managed_block = managed_exclude_block_text(current)
        if managed_block is not None and entry in managed_block:
            return True
        text = current.rstrip("\n") + "\n\n" + "\n".join(block) + "\n"
        atomic_write_if_unchanged(exclude_path, expected_text=current, new_text=text)
    else:
        text = "\n".join(block) + "\n"
        write_text(exclude_path, text)
    return True


def remove_git_exclude_block(project_root: Path) -> bool:
    git_dir = project_root / ".git"
    if not git_dir.is_dir():
        return False

    exclude_path = git_dir / "info" / "exclude"
    if not exclude_path.exists():
        return False

    lines = exclude_path.read_text(encoding="utf-8").splitlines()
    start_marker = EXCLUDE_BLOCK_START
    end_marker = EXCLUDE_BLOCK_END
    if start_marker not in lines or end_marker not in lines:
        return False

    start_idx = lines.index(start_marker)
    end_idx = lines.index(end_marker, start_idx)
    new_lines = lines[:start_idx] + lines[end_idx + 1 :]
    text = "\n".join(new_lines).strip("\n")
    current = exclude_path.read_text(encoding="utf-8")
    atomic_write_if_unchanged(exclude_path, expected_text=current, new_text=((text + "\n") if text else ""))
    return True


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
    paths = list(paths)
    if not paths:
        return None
    return max(paths, key=lambda path: path.stat().st_mtime)


def parse_file_marker(text: str) -> FileMarkerInfo | None:
    first_line = text.splitlines()[0].strip() if text.splitlines() else ""
    match = FILE_MARKER_RE.match(first_line)
    if not match:
        return None
    return FileMarkerInfo(
        file_key=match.group("file_key"),
        version=match.group("version"),
        language=match.group("lang"),
    )


def parse_file_state_marker(text: str) -> FileStateInfo | None:
    lines = text.splitlines()
    for line in lines[:4]:
        match = FILE_STATE_RE.match(line.strip())
        if match:
            return FileStateInfo(
                revision=int(match.group("revision")),
                updated_at=match.group("updated_at"),
                writer_id=match.group("writer_id").strip(),
                base_workspace_revision=int(match.group("base_workspace_revision")),
            )
    return None


def parse_daily_log_entry_marker(text: str) -> DailyLogEntryInfo | None:
    lines = text.splitlines()
    for line in lines[:4]:
        match = DAILY_LOG_ENTRY_RE.match(line.strip())
        if match:
            return DailyLogEntryInfo(
                entry_id=match.group("entry_id"),
                created_at=match.group("created_at"),
                writer_id=match.group("writer_id").strip(),
                entry_seq=int(match.group("entry_seq")),
            )
    return None


def parse_daily_log_scaffold_marker(text: str) -> bool:
    lines = text.splitlines()
    for line in lines[:4]:
        if DAILY_LOG_SCAFFOLD_RE.match(line.strip()):
            return True
    return False


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
) -> str:
    if not workspace_valid:
        return "broken"
    artifact_newer = bool(workspace_artifact_is_newer)
    if (summary_revision_is_stale and not latest_daily_log_exists) or (
        artifact_newer and not latest_daily_log_exists
    ):
        return "low"
    if summary_revision_is_stale or artifact_newer or not latest_daily_log_exists:
        return "medium"
    return "high"


def _digest_excerpt(text: str, *, max_lines: int = 4) -> str | None:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue
        stripped = stripped.lstrip("-* ").strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= max_lines:
            break
    if not lines:
        return None
    return " | ".join(lines)


def continuity_digest_bundle(
    *,
    summary_text: str,
    latest_daily_log_text: str | None = None,
) -> dict:
    next_step_text = extract_section_text(summary_text, "next_step")
    risks_text = extract_section_text(summary_text, "risks_open_questions")
    active_task_digest = _digest_excerpt(next_step_text)
    blocked_digest = _digest_excerpt(risks_text)

    latest_relevant_log_digest = None
    if latest_daily_log_text:
        log_sections = [
            extract_section_text(latest_daily_log_text, "work_completed"),
            extract_section_text(latest_daily_log_text, "key_decisions"),
            extract_section_text(latest_daily_log_text, "recommended_next_step"),
        ]
        latest_relevant_log_digest = _digest_excerpt(
            "\n".join(section for section in log_sections if section.strip())
        )

    suggested_handoff_sections: list[str] = []
    if active_task_digest:
        suggested_handoff_sections.append("next_step")
    if blocked_digest:
        suggested_handoff_sections.append("risks_open_questions")
    if latest_relevant_log_digest:
        suggested_handoff_sections.append("latest_daily_log")

    return {
        "active_task_digest": active_task_digest,
        "blocked_digest": blocked_digest,
        "latest_relevant_log_digest": latest_relevant_log_digest,
        "suggested_handoff_sections": suggested_handoff_sections,
    }


def scan_auto_attached_context_text(text: str) -> dict:
    hard_block_reasons: list[str] = []
    warnings: list[str] = []

    if INVISIBLE_UNICODE_RE.search(text):
        hard_block_reasons.append("invisible_unicode")

    for pattern in ATTACH_SCAN_HARD_BLOCK_PATTERNS:
        if pattern.search(text):
            hard_block_reasons.append(pattern.pattern)

    for pattern in ATTACH_SCAN_WARNING_PATTERNS:
        if pattern.search(text):
            warnings.append(pattern.pattern)

    return {
        "blocked": bool(hard_block_reasons),
        "hard_block_reasons": hard_block_reasons,
        "warnings": warnings,
    }


def iter_workspace_artifacts(
    project_root: Path,
    storage_root: Path,
    *,
    excluded_dirs: set[str] | None = None,
    excluded_files: set[str] | None = None,
) -> list[Path]:
    excluded_dirs = excluded_dirs or DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_DIRS
    excluded_files = excluded_files or DEFAULT_WORKSPACE_ARTIFACT_EXCLUDED_FILES
    artifacts: list[Path] = []
    for path in project_root.rglob("*"):
        if not path.is_file():
            continue
        try:
            path.relative_to(storage_root)
            continue
        except ValueError:
            pass
        if path.name in excluded_files:
            continue
        rel_path = path.relative_to(project_root)
        if any(part in excluded_dirs for part in rel_path.parent.parts):
            continue
        artifacts.append(path)
    return artifacts


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
    if scan_mode not in {"quick", "full"}:
        raise ValueError(f"Unsupported scan_mode: {scan_mode}")

    workspace_artifact_scan_performed = scan_mode == "full"
    latest_workspace_artifact = None
    workspace_artifact_is_newer = None
    summary_mtime = summary_path.stat().st_mtime

    if workspace_artifact_scan_performed:
        latest_workspace_artifact = latest_file(
            iter_workspace_artifacts(project_root, storage_root)
        )
        workspace_artifact_is_newer = (
            latest_workspace_artifact is not None
            and latest_workspace_artifact.stat().st_mtime > summary_mtime
        )

    summary_revision_is_stale = workspace_revision > summary_base_workspace_revision
    workspace_is_newer = (
        (workspace_artifact_is_newer if workspace_artifact_is_newer is not None else False)
        or summary_revision_is_stale
    )
    continuity_confidence = continuity_confidence_level(
        workspace_valid=True,
        summary_revision_is_stale=summary_revision_is_stale,
        workspace_artifact_is_newer=workspace_artifact_is_newer,
        latest_daily_log_exists=latest_daily_log_exists,
    )

    return {
        "workspace_artifact_scan_mode": scan_mode,
        "workspace_artifact_scan_performed": workspace_artifact_scan_performed,
        "latest_workspace_artifact": latest_workspace_artifact,
        "workspace_artifact_newer_than_summary": workspace_artifact_is_newer,
        "summary_revision_stale": summary_revision_is_stale,
        "workspace_newer_than_summary": workspace_is_newer,
        "summary_stale": workspace_is_newer,
        "continuity_confidence": continuity_confidence,
    }


def daily_log_sequence_error(entries: list[DailyLogEntryInfo]) -> str | None:
    if not entries:
        return "Missing required daily-log-entry metadata marker."
    expected = list(range(1, len(entries) + 1))
    actual = [entry.entry_seq for entry in entries]
    if actual != expected:
        return f"Expected contiguous entry_seq values {expected}, found {actual}."
    return None


def section_keys_in_text(text: str) -> list[str]:
    keys: list[str] = []
    for line in text.splitlines():
        match = SECTION_MARKER_RE.match(line.strip())
        if match:
            keys.append(match.group("section_key"))
    return keys


def missing_section_keys(text: str, required_keys: Iterable[str]) -> list[str]:
    keys = set(section_keys_in_text(text))
    return [key for key in required_keys if key not in keys]


def duplicate_section_keys(text: str) -> list[str]:
    seen: dict[str, int] = {}
    duplicates: list[str] = []
    for key in section_keys_in_text(text):
        seen[key] = seen.get(key, 0) + 1
    for key, count in seen.items():
        if count > 1:
            duplicates.append(key)
    return sorted(duplicates)


def unknown_section_keys(text: str, allowed_keys: Iterable[str]) -> list[str]:
    allowed = set(allowed_keys)
    unknown: set[str] = set()
    for key in section_keys_in_text(text):
        if key not in allowed:
            unknown.add(key)
    return sorted(unknown)


def bridge_block_integrity(text: str) -> tuple[bool, str | None]:
    start_count = text.count(BRIDGE_START)
    end_count = text.count(BRIDGE_END)
    if start_count == 0 and end_count == 0:
        return True, None
    if start_count != end_count:
        return False, "bridge_start_end_mismatch"
    if start_count > 1:
        return False, "bridge_duplicate_blocks"
    if text.find(BRIDGE_START) > text.find(BRIDGE_END):
        return False, "bridge_order_invalid"
    return True, None


def exclude_block_integrity(text: str) -> tuple[bool, str | None]:
    start_marker = EXCLUDE_BLOCK_START
    end_marker = EXCLUDE_BLOCK_END
    start_count = text.count(start_marker)
    end_count = text.count(end_marker)
    if start_count == 0 and end_count == 0:
        return True, None
    if start_count != end_count:
        return False, "exclude_start_end_mismatch"
    if start_count > 1:
        return False, "exclude_duplicate_blocks"
    if text.find(start_marker) > text.find(end_marker):
        return False, "exclude_order_invalid"
    return True, None


def managed_exclude_block_text(text: str) -> str | None:
    start_idx = text.find(EXCLUDE_BLOCK_START)
    end_idx = text.find(EXCLUDE_BLOCK_END)
    if start_idx == -1 and end_idx == -1:
        return None
    if start_idx == -1 or end_idx == -1 or start_idx > end_idx:
        return None
    return text[start_idx : end_idx + len(EXCLUDE_BLOCK_END)]


def to_posix_relative(from_dir: Path, to_path: Path) -> str:
    return Path(os.path.relpath(to_path, start=from_dir)).as_posix()


def detect_root_entry_files(project_root: Path) -> list[Path]:
    found: list[Path] = []
    for rel_path in ROOT_ENTRY_CANDIDATES:
        candidate = project_root / rel_path
        if candidate.is_file():
            found.append(candidate)
    return found


def known_storage_assets(storage_root: Path) -> set[Path]:
    assets: set[Path] = set()
    for rel_path in [
        *MANAGED_ASSET_REQUIRED_FILES,
        *MANAGED_ASSET_OPTIONAL_FILES,
        *MANAGED_ASSET_REQUIRED_DIRECTORIES,
        *MANAGED_ASSET_DIRECTORIES,
    ]:
        assets.add(storage_root / PurePosixPath(rel_path))
    return assets


def known_storage_asset_kind_map(storage_root: Path) -> dict[Path, str]:
    asset_kinds: dict[Path, str] = {}
    for rel_path in [*MANAGED_ASSET_REQUIRED_FILES, *MANAGED_ASSET_OPTIONAL_FILES]:
        asset_kinds[storage_root / PurePosixPath(rel_path)] = "file"
    for rel_path in MANAGED_ASSET_REQUIRED_DIRECTORIES:
        asset_kinds[storage_root / PurePosixPath(rel_path)] = "directory"
    for rel_path in MANAGED_ASSET_DIRECTORIES:
        asset_kinds[storage_root / PurePosixPath(rel_path)] = "directory"
    return asset_kinds


def _matches_dynamic_storage_asset_rule(path: Path, storage_root: Path) -> bool:
    if not path.is_file():
        return False
    for rule in MANAGED_ASSET_DYNAMIC_RULES:
        base_dir = storage_root / PurePosixPath(rule["base_dir"])
        if path.parent != base_dir:
            continue
        kind = rule["kind"]
        if kind == "iso_daily_log" and DATE_FILE_RE.match(path.name):
            try:
                parse_iso_date(path.stem)
            except ValueError:
                continue
            return True
        if kind == "recovery_proposal" and RECOVERY_PROPOSAL_FILE_RE.match(path.name):
            return True
        if kind == "review_record" and REVIEW_RECORD_FILE_RE.match(path.name):
            return True
    return False


def unknown_storage_assets(storage_root: Path) -> list[Path]:
    if not storage_root.is_dir():
        return []
    known = known_storage_asset_kind_map(storage_root)
    unknown: list[Path] = []

    for path in sorted(storage_root.rglob("*")):
        if path.name == ".DS_Store":
            continue
        if is_official_temp_storage_asset(path, storage_root):
            continue
        expected_kind = known.get(path)
        if expected_kind == "file" and path.is_file():
            continue
        if expected_kind == "directory" and path.is_dir():
            continue
        if _matches_dynamic_storage_asset_rule(path, storage_root):
            continue
        unknown.append(path)

    return unknown


def is_official_temp_storage_asset(path: Path, storage_root: Path) -> bool:
    if not path.is_file():
        return False
    if not path.name.startswith("."):
        return False
    candidate_name, sep, _suffix = path.name[1:].partition(".tmp-")
    if not sep or not candidate_name:
        return False

    if path.parent == storage_root:
        for rel_path in [*MANAGED_ASSET_REQUIRED_FILES, *MANAGED_ASSET_OPTIONAL_FILES]:
            rel = PurePosixPath(rel_path)
            if rel.parent.as_posix() in {".", ""} and rel.name == candidate_name:
                return True

    for rule in MANAGED_ASSET_DYNAMIC_RULES:
        base_dir = storage_root / PurePosixPath(rule["base_dir"])
        if path.parent != base_dir:
            continue
        kind = rule["kind"]
        if kind == "iso_daily_log" and DATE_FILE_RE.match(candidate_name):
            try:
                parse_iso_date(Path(candidate_name).stem)
            except ValueError:
                return False
            return True
        if kind == "recovery_proposal" and RECOVERY_PROPOSAL_FILE_RE.match(candidate_name):
            return True
        if kind == "review_record" and REVIEW_RECORD_FILE_RE.match(candidate_name):
            return True

    return False


def render_bridge_block(workspace: WorkspaceInfo, target_file: Path) -> str:
    target_dir = target_file.parent
    language = workspace.workspace_language
    config = to_posix_relative(target_dir, workspace.storage_root / FILE_KEYS["config"])
    update_protocol = to_posix_relative(target_dir, workspace.storage_root / FILE_KEYS["update_protocol"])
    context_brief = to_posix_relative(target_dir, workspace.storage_root / FILE_KEYS["context_brief"])
    rolling_summary = to_posix_relative(target_dir, workspace.storage_root / FILE_KEYS["rolling_summary"])
    daily_logs_dir = to_posix_relative(target_dir, workspace.storage_root / "daily_logs")
    has_update_protocol = (workspace.storage_root / FILE_KEYS["update_protocol"]).is_file()

    if language == "zh-CN":
        body = [
            BRIDGE_START,
            "本项目使用 RecallLoom 管理持久化项目连续性上下文。",
            "",
            "需要恢复项目连续性时，请优先读取：",
            f"- {config}",
        ]
        if has_update_protocol:
            body.append(f"- {update_protocol}（先人工查看其中的项目级覆盖规则）")
        body.extend(
            [
            f"- {context_brief}",
            f"- {rolling_summary}",
            f"- {daily_logs_dir}/（如存在 active 日志，则读取其中最新的一份 active daily log）",
            "",
            "平台入口文档负责工具行为规则；RecallLoom 负责项目连续性状态。",
            "如果存在 update_protocol.md，请先人工查看其中的覆盖规则；v1 helper 不会自动解析其中的自然语言内容。",
            "不要随意覆盖这些文件。",
            BRIDGE_END,
            ]
        )
    else:
        body = [
            BRIDGE_START,
            "This project uses RecallLoom for persistent project continuity.",
            "",
            "For continuity state, read:",
            f"- {config}",
        ]
        if has_update_protocol:
            body.append(f"- {update_protocol} (review project-local overrides first)")
        body.extend(
            [
            f"- {context_brief}",
            f"- {rolling_summary}",
            f"- the latest active daily log under {daily_logs_dir}/ if one exists",
            "",
            "Platform entry files define tool behavior; RecallLoom defines project continuity state.",
            "If update_protocol.md exists, review its project-local overrides first; v1 helpers do not parse natural-language override prose automatically.",
            "Do not overwrite these files casually.",
            BRIDGE_END,
            ]
        )
    return "\n".join(body)


def replace_or_insert_bridge(text: str, block: str) -> str:
    if BRIDGE_START in text and BRIDGE_END in text:
        pattern = re.compile(
            re.escape(BRIDGE_START) + r".*?" + re.escape(BRIDGE_END),
            flags=re.S,
        )
        updated = pattern.sub(block, text, count=1)
        return updated if updated.endswith("\n") else updated + "\n"

    lines = text.splitlines()
    if lines and lines[0].strip() == "---":
        try:
            end_idx = next(i for i, line in enumerate(lines[1:], start=1) if line.strip() == "---")
        except StopIteration:
            end_idx = -1
        if end_idx != -1:
            head = "\n".join(lines[: end_idx + 1]).rstrip("\n")
            tail = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
            pieces = [head, "", block]
            if tail:
                pieces.extend(["", tail])
            result = "\n".join(pieces)
            return result if result.endswith("\n") else result + "\n"

    stripped = text.rstrip("\n")
    if stripped:
        result = stripped + "\n\n" + block + "\n"
    else:
        result = block + "\n"
    return result


def remove_bridge_block(text: str) -> tuple[str, bool]:
    if BRIDGE_START not in text or BRIDGE_END not in text:
        return text, False
    pattern = re.compile(
        r"\n*" + re.escape(BRIDGE_START) + r".*?" + re.escape(BRIDGE_END) + r"\n*",
        flags=re.S,
    )
    updated = pattern.sub("\n\n", text, count=1)
    updated = re.sub(r"\n{3,}", "\n\n", updated).strip("\n")
    return ((updated + "\n") if updated else ""), True
