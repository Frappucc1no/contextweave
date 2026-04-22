#!/usr/bin/env python3
"""Source-tier scanning and structured proposal synthesis for cold start."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

ROOT_ENTRY_CANDIDATES = (
    Path("README.md"),
    Path("AGENTS.md"),
    Path("CLAUDE.md"),
    Path("GEMINI.md"),
    Path(".github/copilot-instructions.md"),
)

HIGH_SIGNAL_DOC_RE = re.compile(r"(change ?log|spec|roadmap|architecture)", re.I)
USER_REALITY_DOC_RE = re.compile(r"(memory|status|summary|handoff|decision|milestone|progress)", re.I)
MARKDOWN_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+")
HOST_MEMORY_CONFIDENCE_LEVELS = {"low", "medium", "high"}


def normalize_text_lines(text: str, *, max_lines: int = 4) -> list[str]:
    lines: list[str] = []
    for raw in text.splitlines():
        stripped = raw.strip()
        if not stripped:
            continue
        if stripped.startswith("<!--"):
            continue
        if MARKDOWN_HEADING_RE.match(stripped):
            continue
        stripped = stripped.lstrip("-* ").strip()
        if not stripped:
            continue
        lines.append(stripped)
        if len(lines) >= max_lines:
            break
    return lines


def read_source_excerpt(path: Path, *, max_lines: int = 4) -> list[str]:
    try:
        return normalize_text_lines(path.read_text(encoding="utf-8"), max_lines=max_lines)
    except (OSError, UnicodeDecodeError):
        return []


def tier_a_sources(project_root: Path) -> list[dict]:
    sources: list[dict] = []
    for rel_path in ROOT_ENTRY_CANDIDATES:
        candidate = project_root / rel_path
        if not candidate.is_file():
            continue
        sources.append(
            {
                "tier": "A",
                "path": str(candidate),
                "relative_path": rel_path.as_posix(),
                "kind": "root_entry",
                "confidence": "high",
                "excerpt_lines": read_source_excerpt(candidate),
            }
        )
    return sources


def tier_b_sources(project_root: Path) -> list[dict]:
    sources: list[dict] = []
    docs_dir = project_root / "docs"
    seen: set[str] = set()
    if docs_dir.is_dir():
        for candidate in sorted(docs_dir.rglob("*")):
            if not candidate.is_file():
                continue
            rel = candidate.relative_to(project_root).as_posix()
            if not HIGH_SIGNAL_DOC_RE.search(candidate.stem):
                continue
            if rel in seen:
                continue
            seen.add(rel)
            sources.append(
                {
                    "tier": "B",
                    "path": str(candidate),
                    "relative_path": rel,
                    "kind": "high_signal_doc",
                    "confidence": "medium",
                    "excerpt_lines": read_source_excerpt(candidate),
                }
            )
    for candidate in sorted(project_root.iterdir()):
        if not candidate.is_file():
            continue
        rel = candidate.relative_to(project_root).as_posix()
        if rel in seen or not HIGH_SIGNAL_DOC_RE.search(candidate.stem):
            continue
        seen.add(rel)
        sources.append(
            {
                "tier": "B",
                "path": str(candidate),
                "relative_path": rel,
                "kind": "high_signal_doc",
                "confidence": "medium",
                "excerpt_lines": read_source_excerpt(candidate),
            }
        )
    return sources


def tier_c_sources(project_root: Path) -> list[dict]:
    sources: list[dict] = []
    candidates = list(project_root.glob("*.md"))
    docs_dir = project_root / "docs"
    if docs_dir.is_dir():
        candidates.extend(docs_dir.rglob("*.md"))

    seen: set[str] = set()
    for candidate in sorted({path.resolve() for path in candidates}):
        rel = candidate.relative_to(project_root).as_posix()
        if rel in seen or not USER_REALITY_DOC_RE.search(candidate.stem):
            continue
        seen.add(rel)
        sources.append(
            {
                "tier": "C",
                "path": str(candidate),
                "relative_path": rel,
                "kind": "user_reality_doc",
                "confidence": "medium",
                "excerpt_lines": read_source_excerpt(candidate),
            }
        )
    return sources


def tier_d_sources(project_root: Path, explicit_sources: list[str]) -> list[dict]:
    sources: list[dict] = []
    for raw in explicit_sources:
        candidate = Path(raw).expanduser()
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        if not candidate.is_file():
            continue
        sources.append(
            {
                "tier": "D",
                "path": str(candidate),
                "relative_path": candidate.relative_to(project_root).as_posix()
                if project_root in candidate.parents or candidate == project_root
                else str(candidate),
                "kind": "explicit_source",
                "confidence": "high",
                "excerpt_lines": read_source_excerpt(candidate),
            }
        )
    return sources


def tier_e_sources(project_root: Path, *, include_git_signal: bool, max_commits: int = 5) -> list[dict]:
    if not include_git_signal:
        return []
    try:
        proc = subprocess.run(
            ["git", "-C", str(project_root), "log", f"-n{max_commits}", "--pretty=%s"],
            text=True,
            capture_output=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return []
    lines = [line.strip() for line in proc.stdout.splitlines() if line.strip()]
    if not lines:
        return []
    return [
        {
            "tier": "E",
            "path": f"git:{index + 1}",
            "relative_path": f"git:{index + 1}",
            "kind": "recent_commit_subject",
            "confidence": "low",
            "excerpt_lines": [line],
        }
        for index, line in enumerate(lines)
    ]


def build_host_memory_adapter(
    project_root: Path,
    *,
    enabled: bool,
    source_label: str | None,
    path_raw: str | None,
    command_raw: str | None,
    confidence: str | None,
) -> dict:
    if not enabled:
        return {
            "enabled": False,
            "source": None,
            "mode": None,
            "path": None,
            "command": None,
            "confidence": None,
            "hint_only": True,
            "ingested": False,
            "error": None,
        }

    if not source_label or not source_label.strip():
        raise ValueError("Enabling host memory requires --host-memory-source.")
    if confidence not in HOST_MEMORY_CONFIDENCE_LEVELS:
        raise ValueError(
            "Enabling host memory requires --host-memory-confidence with one of: low, medium, high."
        )
    provided = [bool(path_raw), bool(command_raw)]
    if sum(provided) != 1:
        raise ValueError(
            "Enabling host memory requires exactly one of --host-memory-path or --host-memory-command."
        )

    if path_raw:
        candidate = Path(path_raw).expanduser()
        if not candidate.is_absolute():
            candidate = (project_root / candidate).resolve()
        if not candidate.is_file():
            raise ValueError(f"Host memory path does not exist: {candidate}")
        return {
            "enabled": True,
            "source": source_label.strip(),
            "mode": "path",
            "path": str(candidate),
            "command": None,
            "confidence": confidence,
            "hint_only": True,
            "ingested": True,
            "error": None,
        }

    return {
        "enabled": True,
        "source": source_label.strip(),
        "mode": "command",
        "path": None,
        "command": command_raw,
        "confidence": confidence,
        "hint_only": True,
        "ingested": False,
        "error": None,
    }


def tier_f_sources(project_root: Path, adapter: dict) -> list[dict]:
    if not adapter.get("enabled"):
        return []
    if adapter.get("mode") == "path" and adapter.get("path"):
        candidate = Path(adapter["path"])
        return [
            {
                "tier": "F",
                "path": str(candidate),
                "relative_path": (
                    candidate.relative_to(project_root).as_posix()
                    if project_root in candidate.parents or candidate == project_root
                    else str(candidate)
                ),
                "kind": "host_memory_path",
                "confidence": adapter["confidence"],
                "hint_only": True,
                "excerpt_lines": read_source_excerpt(candidate),
            }
        ]
    return [
        {
            "tier": "F",
            "path": adapter["command"],
            "relative_path": adapter["command"],
            "kind": "host_memory_command",
            "confidence": adapter["confidence"],
            "hint_only": True,
            "excerpt_lines": [
                "Host memory command declared explicitly but not executed automatically."
            ],
        }
    ]


def gather_coldstart_sources(
    project_root: Path,
    *,
    explicit_sources: list[str] | None = None,
    include_git_signal: bool = False,
    host_memory_adapter: dict | None = None,
) -> list[dict]:
    explicit_sources = explicit_sources or []
    host_memory_adapter = host_memory_adapter or {
        "enabled": False,
        "hint_only": True,
    }
    sources: list[dict] = []
    sources.extend(tier_a_sources(project_root))
    sources.extend(tier_b_sources(project_root))
    sources.extend(tier_c_sources(project_root))
    sources.extend(tier_d_sources(project_root, explicit_sources))
    sources.extend(tier_e_sources(project_root, include_git_signal=include_git_signal))
    sources.extend(tier_f_sources(project_root, host_memory_adapter))
    return sources


def _merge_excerpt_lines(sources: list[dict], *, tiers: tuple[str, ...], max_lines: int = 4) -> list[str]:
    lines: list[str] = []
    for source in sources:
        if source["tier"] not in tiers:
            continue
        for line in source.get("excerpt_lines", []):
            if line not in lines:
                lines.append(line)
            if len(lines) >= max_lines:
                return lines
    return lines


def render_coldstart_proposal(project_root: Path, sources: list[dict]) -> str:
    tiers_used = sorted({source["tier"] for source in sources})
    tier_f_sources = [source for source in sources if source["tier"] == "F"]
    source_lines = [
        f"- Tier {source['tier']} | {source['confidence']} | {source['relative_path']}"
        for source in sources
    ]
    background_lines = _merge_excerpt_lines(sources, tiers=("A", "B"), max_lines=4) or [
        "Unclear from scanned sources; needs review."
    ]
    current_state_lines = _merge_excerpt_lines(sources, tiers=("C", "D"), max_lines=4) or [
        "Current state is not yet explicit in the scanned sources; needs review."
    ]
    milestone_lines = _merge_excerpt_lines(sources, tiers=("B", "E"), max_lines=4) or [
        "No clear milestone evidence was found in the scanned sources."
    ]
    next_step_lines = _merge_excerpt_lines(sources, tiers=("C", "D", "E"), max_lines=3) or [
        "Next step is not explicit; review manually before promotion."
    ]
    tier_f_note = "Tier F host-memory sources are disabled by default and were not read."
    if tier_f_sources:
        if any(source.get("kind") == "host_memory_path" for source in tier_f_sources):
            tier_f_note = (
                "Tier F host-memory sources were included as explicit hint-only inputs and still require manual review."
            )
        else:
            tier_f_note = (
                "Tier F host-memory command metadata was included as hint-only input; the command was not auto-executed."
            )
    uncertainty_lines = [
        "Proposal is generated heuristically from file excerpts and still requires review.",
        f"Used tiers: {', '.join(tiers_used) if tiers_used else 'none'}.",
        tier_f_note,
    ]
    promotion_lines = [
        "- context_brief.md: durable project background, scope, and source-of-truth facts",
        "- rolling_summary.md: current state, next step, and active judgments",
        "- daily_logs/: milestone evidence only if worth long-term retention",
    ]

    sections = [
        ("来源摘要", [f"- Generated from {len(sources)} source(s).", *background_lines[:2]]),
        ("来源类型与可信级别", source_lines or ["- No eligible sources were found."]),
        ("候选当前状态事实", [*background_lines, *current_state_lines]),
        ("候选里程碑事件", milestone_lines),
        ("候选判断反转", ["- No judgment reversals were inferred automatically."]),
        ("候选下一步变化", next_step_lines),
        ("与当前 sidecar 的冲突", [f"- {line}" for line in uncertainty_lines]),
        ("建议提升动作", promotion_lines),
        ("审阅结论", ["- Review before promotion."]),
    ]

    parts: list[str] = []
    for heading, lines in sections:
        parts.append(f"## {heading}")
        parts.extend(lines)
        parts.append("")
    return "\n".join(parts).rstrip() + "\n"


def recommend_coldstart_path(sources: list[dict]) -> dict:
    tiers = {source["tier"] for source in sources}
    has_current_state_signal = any(source["tier"] in {"C", "D"} and source.get("excerpt_lines") for source in sources)
    has_core_project_signal = any(source["tier"] in {"A", "B"} and source.get("excerpt_lines") for source in sources)
    uses_host_memory = "F" in tiers
    uses_explicit_or_git = bool({"D", "E"} & tiers)

    fast_path = has_core_project_signal and has_current_state_signal and not uses_host_memory
    if fast_path:
        reasoning = [
            "Tier A/B project framing and Tier C/D current-state signals are both present.",
            "No host-memory fallback was needed for the default path.",
        ]
        if uses_explicit_or_git:
            reasoning.append("Tier D/E supplemental signals exist but do not by themselves force a deep path.")
        return {
            "interaction_mode": "fast_path",
            "needs_deep_review": False,
            "reasoning": reasoning,
        }

    reasoning = []
    if not has_core_project_signal:
        reasoning.append("Project framing sources are insufficient for a low-ambiguity cold start.")
    if not has_current_state_signal:
        reasoning.append("Current-state signals are insufficient to seed continuity safely.")
    if uses_host_memory:
        reasoning.append("Host memory is hint-only and should trigger explicit review before promotion.")
    if not reasoning:
        reasoning.append("Cold-start proposal still requires explicit review because source coverage is ambiguous.")
    return {
        "interaction_mode": "deep_path",
        "needs_deep_review": True,
        "reasoning": reasoning,
    }
