#!/usr/bin/env python3
"""Load and validate the RecallLoom contract registry."""

from __future__ import annotations

import json
import os
from pathlib import Path, PurePosixPath
import re

PROTOCOL_VERSION_RE = re.compile(r"^[0-9]+\.[0-9]+(?:\.[0-9]+)*$")
PACKAGE_ROOT = Path(__file__).resolve().parents[3]
CONTRACT_REGISTRY_OVERRIDE_ENV = "RECALLLOOM_CONTRACT_REGISTRY_PATH"
CONTRACT_SCHEMA_OVERRIDE_ENV = "RECALLLOOM_CONTRACT_SCHEMA_PATH"
DEFAULT_CONTRACT_REGISTRY_PATH = PACKAGE_ROOT / "references" / "contract-registry.json"
DEFAULT_CONTRACT_SCHEMA_PATH = PACKAGE_ROOT / "references" / "contract-schema.json"


def resolve_contract_registry_path() -> Path:
    return Path(
        os.environ.get(CONTRACT_REGISTRY_OVERRIDE_ENV, str(DEFAULT_CONTRACT_REGISTRY_PATH))
    ).expanduser().resolve()


def resolve_contract_schema_path() -> Path:
    return Path(
        os.environ.get(CONTRACT_SCHEMA_OVERRIDE_ENV, str(DEFAULT_CONTRACT_SCHEMA_PATH))
    ).expanduser().resolve()


def _read_json(path: Path, *, label: str) -> dict:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Missing {label} file: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Malformed {label} file: {path}") from exc
    except UnicodeDecodeError as exc:
        raise RuntimeError(f"{label.capitalize()} file is not valid UTF-8: {path}") from exc
    if not isinstance(payload, dict):
        raise RuntimeError(f"{label.capitalize()} file must be a JSON object: {path}")
    return payload


def _require_non_empty_string(value: object, *, context: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError(f"{context} must be a non-empty string")
    return value.strip()


def _require_string_list(value: object, *, context: str, allow_empty: bool = False) -> list[str]:
    if not isinstance(value, list):
        raise RuntimeError(f"{context} must be a list")
    if not allow_empty and not value:
        raise RuntimeError(f"{context} must be a non-empty list")
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized_item = _require_non_empty_string(item, context=context)
        if normalized_item in seen:
            raise RuntimeError(f"{context} must not contain duplicates: {normalized_item}")
        seen.add(normalized_item)
        normalized.append(normalized_item)
    return normalized


def _require_text_line_list(value: object, *, context: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise RuntimeError(f"{context} must be a non-empty list")
    normalized: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise RuntimeError(f"{context} must contain only strings")
        normalized.append(item)
    return normalized


def _normalize_relative_path(value: object, *, context: str) -> str:
    raw = _require_non_empty_string(value, context=context)
    normalized = PurePosixPath(raw).as_posix()
    if (
        normalized in {".", ""}
        or normalized.startswith("../")
        or normalized.startswith("/")
        or ".." in PurePosixPath(normalized).parts
    ):
        raise RuntimeError(f"{context} must be a relative path, got '{raw}'")
    return normalized


def _require_object(value: object, *, context: str) -> dict:
    if not isinstance(value, dict):
        raise RuntimeError(f"{context} must be an object")
    return value


def load_contract_schema(schema_path: Path | None = None) -> dict:
    path = resolve_contract_schema_path() if schema_path is None else Path(schema_path).expanduser().resolve()
    payload = _read_json(path, label="contract schema")

    schema_uri = payload.get("$schema")
    schema_type = payload.get("type")
    required = payload.get("required")
    if not isinstance(schema_uri, str) or "json-schema.org" not in schema_uri:
        raise RuntimeError(f"contract schema must declare a JSON Schema URI: {path}")
    if schema_type != "object":
        raise RuntimeError(f"contract schema root type must be 'object': {path}")
    if not isinstance(required, list) or not required:
        raise RuntimeError(f"contract schema must declare non-empty required fields: {path}")
    return payload


def _resolve_schema_ref(ref: str, *, root_schema: dict) -> dict:
    if not ref.startswith("#/"):
        raise RuntimeError(f"Unsupported schema ref: {ref}")
    current: object = root_schema
    for part in ref[2:].split("/"):
        if not isinstance(current, dict) or part not in current:
            raise RuntimeError(f"Unresolvable schema ref: {ref}")
        current = current[part]
    if not isinstance(current, dict):
        raise RuntimeError(f"Schema ref does not resolve to an object: {ref}")
    return current


def _schema_validate(value: object, schema: dict, *, root_schema: dict, context: str) -> None:
    if "$ref" in schema:
        resolved = _resolve_schema_ref(schema["$ref"], root_schema=root_schema)
        _schema_validate(value, resolved, root_schema=root_schema, context=context)
        return

    if "const" in schema and value != schema["const"]:
        raise RuntimeError(f"{context} must equal {schema['const']!r}")

    schema_type = schema.get("type")
    if schema_type == "object":
        if not isinstance(value, dict):
            raise RuntimeError(f"{context} must be an object")
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise RuntimeError(f"{context} is missing required fields: {missing}")
        properties = schema.get("properties", {})
        for key, property_schema in properties.items():
            if key in value:
                _schema_validate(
                    value[key],
                    property_schema,
                    root_schema=root_schema,
                    context=f"{context}.{key}",
                )
        extra_keys = set(value.keys()) - set(properties.keys())
        additional = schema.get("additionalProperties", True)
        if additional is False and extra_keys:
            raise RuntimeError(f"{context} contains unsupported fields: {sorted(extra_keys)}")
        if isinstance(additional, dict):
            for key in sorted(extra_keys):
                _schema_validate(
                    value[key],
                    additional,
                    root_schema=root_schema,
                    context=f"{context}.{key}",
                )
        return

    if schema_type == "array":
        if not isinstance(value, list):
            raise RuntimeError(f"{context} must be a list")
        min_items = schema.get("minItems")
        if isinstance(min_items, int) and len(value) < min_items:
            raise RuntimeError(f"{context} must contain at least {min_items} items")
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for index, item in enumerate(value):
                _schema_validate(
                    item,
                    items_schema,
                    root_schema=root_schema,
                    context=f"{context}[{index}]",
                )
        return

    if schema_type == "string":
        if not isinstance(value, str):
            raise RuntimeError(f"{context} must be a string")
        min_length = schema.get("minLength")
        if isinstance(min_length, int) and len(value) < min_length:
            raise RuntimeError(f"{context} must be at least {min_length} characters long")
        return

    if schema_type == "integer":
        if isinstance(value, bool) or not isinstance(value, int):
            raise RuntimeError(f"{context} must be an integer")
        return


def _validate_protocol(payload: dict, *, context: str) -> dict:
    current = _require_non_empty_string(payload.get("current"), context=f"{context}.current")
    if not PROTOCOL_VERSION_RE.match(current):
        raise RuntimeError(f"{context}.current must use dotted version form such as '1.0'")
    supported = _require_string_list(payload.get("supported"), context=f"{context}.supported")
    if not all(PROTOCOL_VERSION_RE.match(item) for item in supported):
        raise RuntimeError(f"{context}.supported must contain dotted version strings")
    if current not in supported:
        raise RuntimeError(f"{context}.current must be included in {context}.supported")
    return {"current": current, "supported": supported}


def _validate_workspace(payload: dict, *, context: str) -> dict:
    languages = _require_string_list(payload.get("languages"), context=f"{context}.languages")
    storage_modes = _require_string_list(payload.get("storage_modes"), context=f"{context}.storage_modes")
    bridge_targets = _require_string_list(payload.get("bridge_targets"), context=f"{context}.bridge_targets")
    return {
        "languages": languages,
        "storage_modes": storage_modes,
        "bridge_targets": bridge_targets,
    }


def _validate_document_labels(
    labels_payload: object,
    *,
    context: str,
    languages: list[str],
    expected_keys: list[str],
) -> dict:
    labels = _require_object(labels_payload, context=context)
    normalized: dict[str, dict[str, str]] = {}
    for language in languages:
        language_labels = _require_object(labels.get(language), context=f"{context}.{language}")
        normalized[language] = {}
        for section_key in expected_keys:
            normalized[language][section_key] = _require_non_empty_string(
                language_labels.get(section_key),
                context=f"{context}.{language}.{section_key}",
            )
    extra_languages = sorted(set(labels.keys()) - set(languages))
    if extra_languages:
        raise RuntimeError(f"{context} contains unsupported languages: {extra_languages}")
    return normalized


def _validate_update_protocol_labels(
    labels_payload: object,
    *,
    context: str,
    languages: list[str],
) -> dict:
    labels = _require_object(labels_payload, context=context)
    normalized: dict[str, dict[str, object]] = {}
    for language in languages:
        language_labels = _require_object(labels.get(language), context=f"{context}.{language}")
        normalized[language] = {
            "title": _require_non_empty_string(
                language_labels.get("title"),
                context=f"{context}.{language}.title",
            ),
            "body": _require_text_line_list(
                language_labels.get("body"),
                context=f"{context}.{language}.body",
            ),
        }
    extra_languages = sorted(set(labels.keys()) - set(languages))
    if extra_languages:
        raise RuntimeError(f"{context} contains unsupported languages: {extra_languages}")
    return normalized


def _validate_file_contract(
    file_key: str,
    payload: object,
    *,
    languages: list[str],
) -> dict:
    contract = _require_object(payload, context=f"files.{file_key}")
    required_sections = _require_string_list(
        contract.get("required_sections"),
        context=f"files.{file_key}.required_sections",
        allow_empty=True,
    )
    optional_sections = _require_string_list(
        contract.get("optional_sections"),
        context=f"files.{file_key}.optional_sections",
        allow_empty=True,
    )
    overlap = sorted(set(required_sections).intersection(optional_sections))
    if overlap:
        raise RuntimeError(
            f"files.{file_key}.required_sections and optional_sections must be disjoint, found {overlap}"
        )
    render_order = _require_string_list(
        contract.get("render_order"),
        context=f"files.{file_key}.render_order",
        allow_empty=True,
    )
    expected_render_keys = required_sections + optional_sections
    if sorted(render_order) != sorted(expected_render_keys):
        raise RuntimeError(
            f"files.{file_key}.render_order must exactly cover required and optional sections"
        )

    normalized = {
        "required_sections": required_sections,
        "optional_sections": optional_sections,
        "render_order": render_order,
    }

    if file_key == "daily_log":
        path_pattern = _normalize_relative_path(
            contract.get("path_pattern"),
            context="files.daily_log.path_pattern",
        )
        if "{date}" not in path_pattern:
            raise RuntimeError("files.daily_log.path_pattern must include '{date}'")
        normalized["path_pattern"] = path_pattern
        normalized["labels"] = _validate_document_labels(
            contract.get("labels"),
            context="files.daily_log.labels",
            languages=languages,
            expected_keys=required_sections,
        )
        return normalized

    normalized["path"] = _normalize_relative_path(
        contract.get("path"),
        context=f"files.{file_key}.path",
    )

    if file_key in {"config", "state"}:
        labels = contract.get("labels")
        if labels != {}:
            raise RuntimeError(f"files.{file_key}.labels must be an empty object")
        return {**normalized, "labels": {}}

    if file_key == "update_protocol":
        normalized["labels"] = _validate_update_protocol_labels(
            contract.get("labels"),
            context="files.update_protocol.labels",
            languages=languages,
        )
        return normalized

    normalized["labels"] = _validate_document_labels(
        contract.get("labels"),
        context=f"files.{file_key}.labels",
        languages=languages,
        expected_keys=required_sections + optional_sections,
    )
    return normalized


def _validate_files(payload: object, *, languages: list[str]) -> dict:
    files = _require_object(payload, context="files")
    required_file_keys = (
        "config",
        "state",
        "context_brief",
        "rolling_summary",
        "daily_log",
        "update_protocol",
    )
    missing = [file_key for file_key in required_file_keys if file_key not in files]
    if missing:
        raise RuntimeError(f"files is missing required entries: {missing}")
    extra = sorted(set(files.keys()) - set(required_file_keys))
    if extra:
        raise RuntimeError(f"files contains unsupported entries: {extra}")
    return {
        file_key: _validate_file_contract(file_key, files[file_key], languages=languages)
        for file_key in required_file_keys
    }


def _validate_templated_marker(payload: object, *, context: str) -> dict:
    marker = _require_object(payload, context=context)
    regex = _require_non_empty_string(marker.get("regex"), context=f"{context}.regex")
    try:
        re.compile(regex)
    except re.error as exc:
        raise RuntimeError(f"{context}.regex must be a valid regular expression") from exc
    return {
        "template": _require_non_empty_string(marker.get("template"), context=f"{context}.template"),
        "regex": regex,
    }


def _validate_range_marker(payload: object, *, context: str) -> dict:
    marker = _require_object(payload, context=context)
    return {
        "start": _require_non_empty_string(marker.get("start"), context=f"{context}.start"),
        "end": _require_non_empty_string(marker.get("end"), context=f"{context}.end"),
    }


def _validate_markers(payload: object) -> dict:
    markers = _require_object(payload, context="markers")
    required_keys = (
        "file",
        "file_state",
        "daily_log_entry",
        "daily_log_scaffold",
        "last_writer",
        "bridge",
        "git_exclude",
    )
    missing = [marker_key for marker_key in required_keys if marker_key not in markers]
    if missing:
        raise RuntimeError(f"markers is missing required entries: {missing}")
    extra = sorted(set(markers.keys()) - set(required_keys))
    if extra:
        raise RuntimeError(f"markers contains unsupported entries: {extra}")
    return {
        "file": _validate_templated_marker(markers["file"], context="markers.file"),
        "file_state": _validate_templated_marker(markers["file_state"], context="markers.file_state"),
        "daily_log_entry": _validate_templated_marker(
            markers["daily_log_entry"], context="markers.daily_log_entry"
        ),
        "daily_log_scaffold": _validate_templated_marker(
            markers["daily_log_scaffold"], context="markers.daily_log_scaffold"
        ),
        "last_writer": _validate_templated_marker(markers["last_writer"], context="markers.last_writer"),
        "bridge": _validate_range_marker(markers["bridge"], context="markers.bridge"),
        "git_exclude": _validate_range_marker(markers["git_exclude"], context="markers.git_exclude"),
    }


def _validate_doc_sync_blocks(payload: object) -> dict:
    blocks = _require_object(payload, context="doc_sync_blocks")
    normalized: dict[str, dict[str, list[str]]] = {}
    for block_name, block_payload in blocks.items():
        _require_non_empty_string(block_name, context="doc_sync_blocks key")
        block = _require_object(block_payload, context=f"doc_sync_blocks.{block_name}")
        normalized[block_name] = {
            "source_keys": _require_string_list(
                block.get("source_keys"),
                context=f"doc_sync_blocks.{block_name}.source_keys",
            ),
            "targets": [
                _normalize_relative_path(item, context=f"doc_sync_blocks.{block_name}.targets")
                for item in _require_string_list(
                    block.get("targets"),
                    context=f"doc_sync_blocks.{block_name}.targets",
                )
            ],
        }
    return normalized


def load_contract_registry(
    registry_path: Path | None = None,
    schema_path: Path | None = None,
) -> dict:
    path = resolve_contract_registry_path() if registry_path is None else Path(registry_path).expanduser().resolve()
    schema = load_contract_schema(schema_path)
    payload = _read_json(path, label="contract registry")
    _schema_validate(payload, schema, root_schema=schema, context="contract registry")

    registry_version = payload.get("registry_version")
    if registry_version != 1:
        raise RuntimeError(f"contract registry version must be 1: {path}")

    protocol = _validate_protocol(_require_object(payload.get("protocol"), context="protocol"), context="protocol")
    workspace = _validate_workspace(
        _require_object(payload.get("workspace"), context="workspace"),
        context="workspace",
    )
    files = _validate_files(payload.get("files"), languages=workspace["languages"])
    markers = _validate_markers(payload.get("markers"))
    dynamic_asset_rule_kinds = _require_string_list(
        payload.get("dynamic_asset_rule_kinds"),
        context="dynamic_asset_rule_kinds",
    )
    doc_sync_blocks = _validate_doc_sync_blocks(payload.get("doc_sync_blocks"))

    return {
        "registry_version": registry_version,
        "protocol": protocol,
        "workspace": workspace,
        "files": files,
        "markers": markers,
        "dynamic_asset_rule_kinds": dynamic_asset_rule_kinds,
        "doc_sync_blocks": doc_sync_blocks,
    }
