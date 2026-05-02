"""Stable failure contracts and reason registry for RecallLoom."""

from __future__ import annotations

import os


FAILURE_REASON_ALIASES = {
    "attached_text_safety_blocked": "attach_scan_blocked",
}


FAILURE_REASON_REGISTRY = {
    "python_runtime_unavailable": {
        "blocked": True,
        "recoverability": "retryable",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["find_compatible_python", "report_blocked_runtime"],
        "user_message": {
            "en": "RecallLoom cannot start yet because this environment does not provide Python 3.10 or newer.",
            "zh-CN": "当前环境还不能启动 RecallLoom，因为这里没有可用的 Python 3.10+ 运行时。",
        },
        "operator_note": {
            "en": "Find or point the host at a compatible Python 3.10+ interpreter before retrying.",
            "zh-CN": "请先找到或指定兼容的 Python 3.10+ 解释器，再重试。",
        },
    },
    "not_project_root": {
        "blocked": False,
        "recoverability": "user_input_required",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["confirm_project_root", "retry_init"],
        "user_message": {
            "en": "This path does not look like the project root yet.",
            "zh-CN": "当前路径还不像真正的项目根目录。",
        },
        "operator_note": {
            "en": "Choose the real project root before retrying.",
            "zh-CN": "请先切到真实项目根目录，再重试。",
        },
    },
    "no_project_root": {
        "blocked": False,
        "recoverability": "not_initialized",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["rl-init", "choose_project_root"],
        "user_message": {
            "en": "This project has not been attached to RecallLoom yet.",
            "zh-CN": "当前项目还没有接入 RecallLoom。",
        },
        "operator_note": {
            "en": "Initialize RecallLoom at the correct project root before using status or bridge flows.",
            "zh-CN": "请先在正确的项目根目录初始化 RecallLoom，再使用 status 或 bridge 流程。",
        },
    },
    "damaged_sidecar": {
        "blocked": True,
        "recoverability": "operator_repair_required",
        "surface_level": "user_safe",
        "trust_effect": "damaged",
        "next_actions": ["repair_existing_sidecar", "rerun_validate_or_init"],
        "user_message": {
            "en": "The existing RecallLoom workspace is not trustworthy yet and needs repair before continuing.",
            "zh-CN": "当前已有的 RecallLoom 工作区还不可信，需要先修复后再继续。",
        },
        "operator_note": {
            "en": "Do not hand-build or patch managed files blindly; repair the damaged sidecar first.",
            "zh-CN": "不要手工拼接或盲改 managed 文件；请先修复 damaged sidecar。",
        },
    },
    "dual_sidecar_conflict": {
        "blocked": True,
        "recoverability": "operator_repair_required",
        "surface_level": "user_safe",
        "trust_effect": "conflicting",
        "next_actions": ["resolve_sidecar_conflict", "rerun_validate_or_init"],
        "user_message": {
            "en": "This project has conflicting RecallLoom sidecars, so RecallLoom should stop instead of guessing.",
            "zh-CN": "当前项目存在冲突的 RecallLoom sidecar，应该先停下而不是继续猜。",
        },
        "operator_note": {
            "en": "Resolve the hidden-vs-visible sidecar conflict before retrying.",
            "zh-CN": "请先处理隐藏 sidecar 与可见 sidecar 的冲突，再重试。",
        },
    },
    "attach_scan_blocked": {
        "blocked": True,
        "recoverability": "security_blocked",
        "surface_level": "user_safe",
        "trust_effect": "security_blocked",
        "next_actions": ["revise_bridge_text", "retry_bridge"],
        "user_message": {
            "en": "The current text did not pass the safety check.",
            "zh-CN": "当前文本没有通过安全检查。",
        },
        "operator_note": {
            "en": "Adjust the text without weakening the attached-text safety rules.",
            "zh-CN": "请调整文本，但不要削弱 attached-text safety 规则。",
        },
    },
    "invalid_date": {
        "blocked": False,
        "recoverability": "user_input_required",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["correct_date_input", "retry_init"],
        "user_message": {
            "en": "The requested date is not a valid YYYY-MM-DD value.",
            "zh-CN": "当前给定的日期不是合法的 YYYY-MM-DD 值。",
        },
        "operator_note": {
            "en": "Fix the date value before retrying.",
            "zh-CN": "请先修正日期，再重试。",
        },
    },
    "invalid_tool_name": {
        "blocked": False,
        "recoverability": "user_input_required",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["correct_tool_name", "retry_init"],
        "user_message": {
            "en": "The requested tool name is not valid for RecallLoom metadata.",
            "zh-CN": "当前给定的工具名不符合 RecallLoom 元数据约束。",
        },
        "operator_note": {
            "en": "Choose a valid tool name before retrying.",
            "zh-CN": "请先改成合法的工具名，再重试。",
        },
    },
    "invalid_storage_boundary": {
        "blocked": True,
        "recoverability": "operator_repair_required",
        "surface_level": "user_safe",
        "trust_effect": "conflicting",
        "next_actions": ["correct_storage_target", "retry_init"],
        "user_message": {
            "en": "The requested storage layout is not valid for this project path.",
            "zh-CN": "当前请求的存储布局与这个项目路径不兼容。",
        },
        "operator_note": {
            "en": "Choose a valid project root and storage layout before retrying.",
            "zh-CN": "请先确认合法的项目根目录与存储布局，再重试。",
        },
    },
    "reinit_create_daily_log_not_allowed": {
        "blocked": False,
        "recoverability": "user_input_required",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["use_append_daily_log_entry", "retry_without_create_daily_log"],
        "user_message": {
            "en": "This project is already initialized. Create new milestone entries through the daily-log append helper instead.",
            "zh-CN": "当前项目已经初始化；如需记录新的日志条目，请改用 daily log append helper。",
        },
        "operator_note": {
            "en": "Do not use --create-daily-log during re-initialization of an existing workspace.",
            "zh-CN": "不要在已初始化工作区上继续使用 --create-daily-log。",
        },
    },
    "stale_write_context": {
        "blocked": True,
        "recoverability": "retryable",
        "surface_level": "operator",
        "trust_effect": "review_required",
        "next_actions": ["rerun_preflight", "reread_current_files"],
        "user_message": {
            "en": "The current write context is stale and needs to be refreshed before writing.",
            "zh-CN": "当前写入上下文已经过期，写入前需要先刷新。",
        },
        "operator_note": {
            "en": "Rerun preflight, reread current revisions, and retry with fresh expected revisions.",
            "zh-CN": "请重新执行 preflight，读取最新 revision 后再重试。",
        },
    },
    "write_lock_busy": {
        "blocked": True,
        "recoverability": "retryable",
        "surface_level": "operator",
        "trust_effect": "review_required",
        "next_actions": ["wait_for_active_writer", "retry_helper"],
        "user_message": {
            "en": "Another RecallLoom write appears to be in progress.",
            "zh-CN": "当前似乎已有另一个 RecallLoom 写入正在进行。",
        },
        "operator_note": {
            "en": "Wait for the active writer to finish, then retry. Only clear a stale lock after checking ownership and age.",
            "zh-CN": "请等待当前写入完成后再重试；只有在确认锁已过期且归属清楚后，才清理 stale lock。",
        },
    },
    "malformed_managed_file": {
        "blocked": True,
        "recoverability": "operator_repair_required",
        "surface_level": "operator",
        "trust_effect": "damaged",
        "next_actions": ["repair_managed_file", "rerun_validate_or_helper"],
        "user_message": {
            "en": "A managed RecallLoom file is malformed and must be repaired before continuing.",
            "zh-CN": "存在损坏的 RecallLoom managed 文件，需要先修复后再继续。",
        },
        "operator_note": {
            "en": "Repair the malformed managed file instead of bypassing marker or section checks.",
            "zh-CN": "请修复损坏的 managed 文件，不要绕过 marker 或 section 校验。",
        },
    },
    "invalid_prepared_input": {
        "blocked": True,
        "recoverability": "user_input_required",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["revise_prepared_input", "retry_helper"],
        "user_message": {
            "en": "The prepared input is not valid for this helper.",
            "zh-CN": "当前准备输入不符合这个 helper 的要求。",
        },
        "operator_note": {
            "en": "Fix the prepared source file or stdin content before retrying.",
            "zh-CN": "请先修正 source file 或 stdin 内容，再重试。",
        },
    },
    "historical_append_requires_confirmation": {
        "blocked": True,
        "recoverability": "user_input_required",
        "surface_level": "user_safe",
        "trust_effect": "none",
        "next_actions": ["confirm_historical_append", "retry_with_allow_historical"],
        "user_message": {
            "en": "Appending to an older daily log requires explicit confirmation.",
            "zh-CN": "向较旧的 daily log 追加内容需要显式确认。",
        },
        "operator_note": {
            "en": "Use --allow-historical only when the historical append is intentional.",
            "zh-CN": "只有在确实要回填历史日志时，才使用 --allow-historical。",
        },
    },
    "project_time_policy_review_required": {
        "blocked": True,
        "recoverability": "user_input_required",
        "surface_level": "user_safe",
        "trust_effect": "review_required",
        "next_actions": ["review_update_protocol", "confirm_date_choice"],
        "user_message": {
            "en": "Project-local time policy requires a date review before continuing.",
            "zh-CN": "项目本地时间策略要求先复核日期，再继续。",
        },
        "operator_note": {
            "en": "Review update_protocol.md and confirm the intended date before writing.",
            "zh-CN": "请先检查 update_protocol.md，并确认目标日期后再写入。",
        },
    },
    "trust_review_required": {
        "blocked": True,
        "recoverability": "user_input_required",
        "surface_level": "operator",
        "trust_effect": "review_required",
        "next_actions": ["review_current_continuity", "refresh_before_high_risk_actions"],
        "user_message": {
            "en": "RecallLoom needs a continuity review before a higher-risk action can continue.",
            "zh-CN": "在继续更高风险动作前，需要先复核当前 RecallLoom continuity。",
        },
        "operator_note": {
            "en": "Review the current continuity files and refresh state before proceeding.",
            "zh-CN": "请先复核当前 continuity 文件，并刷新状态后再继续。",
        },
    },
    "continuity_drift_review_required": {
        "blocked": True,
        "recoverability": "user_input_required",
        "surface_level": "operator",
        "trust_effect": "review_required",
        "next_actions": ["review_current_workspace_state", "refresh_rolling_summary"],
        "user_message": {
            "en": "Current continuity may have drifted from the workspace and should be reviewed before higher-risk actions.",
            "zh-CN": "当前 continuity 可能已经和工作区现实脱节，继续高风险动作前应先复核。",
        },
        "operator_note": {
            "en": "Review current workspace reality and refresh the rolling summary before trusting it for writes.",
            "zh-CN": "请先复核当前工作区现实并刷新 rolling summary，再把它当作写入依据。",
        },
    },
    "storage_cleanup_incomplete": {
        "blocked": True,
        "recoverability": "operator_repair_required",
        "surface_level": "operator",
        "trust_effect": "none",
        "next_actions": ["remove_tombstone_storage", "verify_context_removal"],
        "user_message": {
            "en": "RecallLoom removal moved the storage root aside, but final cleanup is still incomplete.",
            "zh-CN": "RecallLoom 已把存储目录移走，但最后的清理还没有完成。",
        },
        "operator_note": {
            "en": "Delete the tombstone storage path and confirm that removal is complete before treating uninstall as finished.",
            "zh-CN": "请删除 tombstone 存储目录，并确认卸载已经真正完成后，再把这次移除视为结束。",
        },
    },
    "registry_contract_invalid": {
        "blocked": True,
        "recoverability": "operator_repair_required",
        "surface_level": "debug",
        "trust_effect": "damaged",
        "next_actions": ["repair_reason_registry", "rerun_bootstrap"],
        "user_message": {
            "en": "RecallLoom cannot continue because its failure-contract registry is invalid.",
            "zh-CN": "RecallLoom 当前无法继续，因为 failure-contract registry 已损坏。",
        },
        "operator_note": {
            "en": "Repair the failure-contract registry before retrying bootstrap or helper execution.",
            "zh-CN": "请先修复 failure-contract registry，再重新执行 bootstrap 或 helper。",
        },
    },
    "package_support_blocked": {
        "blocked": True,
        "recoverability": "upgrade_required",
        "surface_level": "user_safe",
        "trust_effect": "review_required",
        "next_actions": ["upgrade_recallloom_package", "rerun_support_check"],
        "user_message": {
            "en": "This RecallLoom package must be upgraded before this action can continue.",
            "zh-CN": "当前 RecallLoom 包需要先升级，才能继续执行这个动作。",
        },
        "operator_note": {
            "en": "Check the installed package path, native wrappers, and support advisory before retrying.",
            "zh-CN": "请先检查当前安装包路径、原生命令 wrapper 与 support advisory，再重试。",
        },
    },
}


def preferred_failure_language(env: dict[str, str] | None = None) -> str:
    env = env or os.environ
    lang = env.get("LC_ALL") or env.get("LC_MESSAGES") or env.get("LANG") or ""
    return "zh-CN" if lang.lower().startswith("zh") else "en"


def normalize_failure_reason(reason: str) -> str:
    normalized = FAILURE_REASON_ALIASES.get(reason, reason)
    if normalized not in FAILURE_REASON_REGISTRY:
        raise RuntimeError(f"Unknown failure reason: {reason}")
    return normalized


def failure_reason_contract(reason: str) -> dict:
    return FAILURE_REASON_REGISTRY[normalize_failure_reason(reason)]


def failure_payload(
    reason: str,
    *,
    language: str,
    error: str | None = None,
    details: dict | None = None,
    findings: list | None = None,
    extra: dict | None = None,
) -> dict:
    normalized_reason = normalize_failure_reason(reason)
    contract = failure_reason_contract(normalized_reason)
    payload = {
        "ok": False,
        "blocked": contract["blocked"],
        "blocked_reason": normalized_reason,
        "recoverability": contract["recoverability"],
        "surface_level": contract["surface_level"],
        "trust_effect": contract["trust_effect"],
        "next_actions": list(contract["next_actions"]),
        "user_message": contract["user_message"][language],
    }
    if error is not None:
        payload["error"] = error
    operator_note = contract.get("operator_note")
    if operator_note:
        payload["operator_note"] = operator_note[language]
    if details:
        payload["details"] = details
    if findings:
        payload["findings"] = findings
    if extra:
        payload.update(extra)
    return payload
