#!/usr/bin/env python3
"""Template rendering helpers for RecallLoom protocol files."""

from __future__ import annotations

from core.protocol.contracts import (
    CONTEXT_BRIEF_RENDER_ORDER,
    LABELS,
    SECTION_KEYS,
    validate_workspace_language,
)
from core.protocol.markers import (
    daily_log_scaffold_marker,
    file_marker,
    file_state_marker,
    rolling_summary_header,
    section_marker,
)


def render_heading(level: int, heading: str) -> str:
    return "#" * level + " " + heading


def render_section_block(level: int, section_key: str, heading: str, body: list[str] | None = None) -> str:
    lines = [section_marker(section_key), render_heading(level, heading)]
    if body is None:
        lines.extend(["", "-"])
    else:
        lines.extend(["", *body])
    return "\n".join(lines)


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


def render_rolling_summary_template(
    tool_name: str,
    day: str,
    language: str,
    *,
    timestamp: str,
    workspace_revision: int,
) -> str:
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
        parts.append(render_section_block(1, section_key, labels[section_key], guidance[section_key]))
    return "\n".join(parts) + "\n"


def render_daily_log_template(language: str, *, tool_name: str, timestamp: str) -> str:
    del tool_name
    del timestamp
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


def render_update_protocol_template(
    language: str,
    *,
    tool_name: str,
    timestamp: str,
    workspace_revision: int,
) -> str:
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
        return render_context_brief_template(
            language,
            tool_name=tool_name,
            timestamp=timestamp,
            workspace_revision=workspace_revision,
        )
    if file_key == "rolling_summary":
        return render_rolling_summary_template(
            tool_name,
            day,
            language,
            timestamp=timestamp,
            workspace_revision=workspace_revision,
        )
    if file_key == "daily_log":
        return render_daily_log_template(language, tool_name=tool_name, timestamp=timestamp)
    if file_key == "update_protocol":
        return render_update_protocol_template(
            language,
            tool_name=tool_name,
            timestamp=timestamp,
            workspace_revision=workspace_revision,
        )
    raise KeyError(file_key)
