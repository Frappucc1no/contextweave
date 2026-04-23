---
name: recallloom
description: Use when a task involves continuing a project, restoring project context, maintaining file-based project memory, updating current-state summaries, or recording meaningful progress across sessions. Works best for long-horizon, file-based projects and supports research writing, product document collaboration, software project coordination, and broader cross-functional project continuity.
---

# RecallLoom

RecallLoom is a portable context harness for session-based agents.

It provides a lightweight file model for project continuity across sessions without requiring heavy infrastructure.

The goal is not to remember everything. The goal is to keep the right project state durable, readable, and recoverable across sessions.

## Package Scope

This file is the agent-facing entrypoint for the installable `recallloom/` skill package.

Install and trigger this package through your host agent's normal skill discovery flow.
RecallLoom itself does not require a custom host-specific launcher inside the package.
The package may still ship optional native wrapper templates for supported hosts.

This installable package is intentionally kept lean.
Human-facing repository landing pages and marketing docs may exist upstream, but they are not bundled into the installed skill directory.

For package inventory, protocol details, and helper-script behavior, rely on the files that ship inside the package itself:

- `package-metadata.json`
- `references/file-contracts.md`
- `references/operation-playbooks.md`
- `references/protocol.md`

## Package Facts

<!-- RecallLoom metadata sync start: package-metadata -->
- package version: `0.3.3`
- protocol version: `1.0`
- supported protocol versions:
  - `1.0`
<!-- RecallLoom metadata sync end: package-metadata -->

## Runtime Assumptions

<!-- RecallLoom metadata sync start: runtime-assumptions -->
- Python 3.10 or newer
- supported workspace languages:
  - `en`
  - `zh-CN`
- supported bridge targets:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `GEMINI.md`
  - `.github/copilot-instructions.md`
<!-- RecallLoom metadata sync end: runtime-assumptions -->

## When To Use It

Use RecallLoom when you need to:

- continue an existing project after a pause
- restore project context from maintained files
- maintain current-state project memory
- record meaningful milestone progress
- reduce context drift across sessions or tools

Typical triggers include:

- continue this project
- restore project context
- pick up where we left off
- rl-init
- update the project memory
- record today’s progress
- prepare a clean next-step handoff inside the maintained project files

## First Attach Behavior

On first explicit invocation in a project, RecallLoom should not assume the workspace is already initialized.

The correct flow is:

1. detect whether a valid RecallLoom sidecar already exists
2. if it exists, continue normally without making initialization into extra ceremony
3. if it does not exist, explain that the project is not initialized yet and ask whether initialization should be performed
4. if the user explicitly confirms, or directly says `rl-init`, run the standard initialization action
5. if the environment cannot provide Python `3.10+`, stop with a blocked runtime result instead of hand-building a sidecar

For this package, the intended initialization action is:

- initialize the sidecar
- validate the workspace
- return the next recommended actions

This means `rl-init` should be treated as a stable high-level action name, even in hosts that do not expose it as a native slash command.

## Current Action Surface

For the current package line, the stable action names are:

- `rl-init`
- `rl-resume`
- `rl-validate`
- `rl-status`
- `rl-bridge`

`rl-init` is the primary operator-friendly first-attach action name.
The others are operator-facing stable action names that can be interpreted by the host agent or mapped into native custom commands when the host supports that surface.

## Initialized-Project Restore Contract

When a host or agent sees a generic initialized-project restore request:

1. check for a valid RecallLoom sidecar before broad skill fan-out
2. if the sidecar is valid, route into the normal RecallLoom fast path
3. let broader memory or workflow systems participate only when the sidecar is missing, conflicting, clearly insufficient, or the user explicitly asks for deeper review

For the current package line, `rl-resume` is the single stable operator-facing action name for that initialized-project restore checkpoint.
Natural-language restore requests are still the primary public path.
Do not invent a manual sidecar fallback or a host-local restore alias that is not backed by the package contract.

## Public Interaction Rules

RecallLoom should default to user task language, not implementation language.

- Prefer “initialize”, “restore”, “import existing project reality”, “continue”, and “record progress”.
- Do not lead with helper names, section keys, or the internal `coldstart` label unless the user is explicitly doing operator/debug work.
- Keep the first response result-first and action-light: one clear next move is better than exposing internal flow.
- Do not invent a manual sidecar fallback when runtime requirements are missing; surface the blocked state and stop.

## Fast And Deep Paths

RecallLoom should treat fast path as the default interaction mode.

- Fast path: smallest trustworthy source set, shortest interaction, lowest interruption cost.
- Deep path: only when sources conflict, source coverage is insufficient, risk is too high for a direct recommendation, or the user explicitly asks for deeper review.
- Host-memory inputs remain opt-in and hint-only; their presence should bias the agent toward explicit review instead of silent promotion.

## Core File Model

RecallLoom uses three primary memory layers:

- `STORAGE_ROOT/context_brief.md`: stable project framing
- `STORAGE_ROOT/rolling_summary.md`: overwrite-style current-state snapshot
- `STORAGE_ROOT/daily_logs/YYYY-MM-DD.md`: append-only milestone evidence
- `STORAGE_ROOT/config.json`: machine-readable workspace settings
- `STORAGE_ROOT/state.json`: machine-readable sidecar state for concurrency-aware helpers
- `STORAGE_ROOT/update_protocol.md`: recommended project-local override layer for read and write behavior

File responsibilities in one sentence:

- `context_brief.md` explains what this project is and how it should be approached.
- `rolling_summary.md` explains what is true right now.
- `daily_logs/` explain what happened at milestone level.
- `config.json` keeps storage and language settings stable.
- `state.json` tracks workspace revision and helper-visible sidecar state.
- `update_protocol.md`, when present, can narrow or strengthen the default read/write rules for this specific project.

`STORAGE_ROOT` is one of:

- `PROJECT_ROOT/.recallloom/` (default)
- `PROJECT_ROOT/recallloom/` (optional visible sidecar)

Exactly one valid `STORAGE_ROOT` may exist for a project at a time.

If both sidecars exist, that is a conflict and tools should stop rather than guess.

See `references/file-contracts.md` for the detailed contract.

Machine-readable markers, not heading labels, are the normative file contract.

This allows workspace files to stay localizable without breaking validation or integration.

For protocol `1.0`, supported workspace languages are limited to `en` and `zh-CN`.

## Minimum Cold-Start Flow

1. Find the project root.
2. Read `STORAGE_ROOT/config.json`.
3. Read `STORAGE_ROOT/state.json`.
4. Read `STORAGE_ROOT/rolling_summary.md`.
5. If `STORAGE_ROOT/update_protocol.md` exists, surface it before expanding beyond the minimum continuity set.
6. Read `STORAGE_ROOT/context_brief.md` only when the current task needs framing, scope, source-of-truth, or phase context that the summary does not already cover.
7. Read the latest active daily log only when milestone evidence, workday judgment, or external-writer reconciliation requires it.
8. Run a quick freshness check before trusting older context or before a major write.

Cold start should restore and judge first.
It should not automatically continue `next_step` or execute project work just because continuity files were read.

See `references/operation-playbooks.md` for the full flow.

## Current Read-Side Helpers

The current `0.3.3` line now has three read-side helper directions worth knowing:

- `preflight_context_check.py`
  - revision-aware freshness review before formal writes
  - returns handoff-first digests and suggested read targets
- `summarize_continuity_status.py`
  - ambient continuity status surface using the same freshness baseline
  - returns the same handoff-first digest family for quick orientation
- `query_continuity.py`
  - read-only continuity recall surface
  - returns answer-first recall with `answer`, supporting citations, and a risk/freshness note
  - also returns hits, token estimate, budget hint, freshness/conflict state, an output variant label, and override review targets
  - daily-log citations include explicit `date` values
  - prefers current-state files over historical daily logs when match strength ties
  - defaults to the quick freshness path, but can explicitly upgrade to a fuller freshness scan when needed
  - can explicitly surface freshness conflicts when the workspace has moved beyond the current summary
  - explicitly surfaces freshness risk via `freshness_risk_level` and `freshness_risk_note`
  - surfaces `update_protocol.md` as a review target before recall should drive write decisions
  - keeps `supporting_context_window` bounded instead of expanding every matching excerpt

All attach-safe continuity text returned through these read-side surfaces is expected to respect the shared attached-text scan rules.

## Minimum Write Rules

- Before choosing a write target, read `STORAGE_ROOT/update_protocol.md` if it exists.
- Update the rolling summary for current-state changes.
- Update `context_brief.md` only for high-level framing changes.
- Update the daily log only for milestone-level events.
- Do not update context files for trivial reads or minor edits with no durable change.

Practical interpretation:

- New stable fact or next-step change: usually `rolling_summary.md`
- High-level mission or phase change: maybe `context_brief.md`
- Deliverable completion or end-of-day milestone: daily log

Project-local overrides may narrow the default read order, write order, or archive behavior, but they do not replace the core file contract.

For protocol `1.0`, `update_protocol.md` is a human-reviewed override layer.
Preflight, archive guidance, and thin-bridge guidance should surface it clearly, but helpers do not automatically execute its natural-language rules.

RecallLoom prefers the smallest valid write set, not maximal updating.

When deterministic write safety matters, keep the roles separate:

- the agent decides what should change and prepares the content
- the packaged helper scripts decide whether the write is still safe to apply

For overwrite-style files, use revision-aware helper commits instead of blind file replacement whenever possible.

Revision-aware write helpers protect against stale writes, but they do not automatically reread `update_protocol.md` on every commit or append.

Preflight checks may keep `context_brief.md` and existing daily logs out of the primary write-target list, but they should still surface them as conditional review targets when framing drift or milestone logging needs to be considered.

When generating or maintaining workspace files, prefer the user's workspace language when it is one of the supported protocol `1.0` workspace languages (`en`, `zh-CN`).

## When Not To Update Context

Do not update context files just because:

- you performed a cold start
- you answered a short question with no durable project change
- you explored without reaching a stable conclusion
- you made wording-only edits

The protocol is designed to reduce noise, not to turn every session into documentation work.

## Profiles

RecallLoom currently provides four profiles:

- `profiles/general-project-continuity.md`
- `profiles/research-writing.md`
- `profiles/product-doc-collaboration.md`
- `profiles/software-project-coordination.md`

Profiles do not replace the core protocol.
They are thin guidance layers that refine emphasis, evidence handling, and common drift risks for different project shapes.

Default rule:

- use `general-project-continuity.md` by default
- switch to a specialized profile only when the project shape is a high-confidence match
- if you are unsure, do not guess; stay on the general profile

Use the specialized profiles only when the primary artifact, working style, and likely drift risks clearly line up:

- `research-writing.md`
  - use when the work is driven by sources, claims, evidence, and long-form analytical writing
- `product-doc-collaboration.md`
  - use when the work is driven by PRDs, RFCs, strategy docs, scope decisions, or stakeholder-aligned product writing
- `software-project-coordination.md`
  - use when the work is driven by engineering planning, spec-to-implementation coordination, or repo-level software project continuity

Use `general-project-continuity.md` when:

- the project mixes multiple artifact types
- the project is cross-functional rather than domain-pure
- no specialized profile is an obvious fit
- you need a stable fallback that preserves continuity without over-assuming the project shape

## What RecallLoom Does Not Try To Be

RecallLoom does not try to be:

- a general-purpose memory server
- a full agent execution runtime
- a replacement for platform-specific instruction files
- a heavy autonomous coding framework

It is the project continuity layer, not the whole agent stack.

## Where To Read More

- `references/protocol.md`
- `references/file-contracts.md`
- `references/operation-playbooks.md`
- `references/anti-patterns.md`
- `references/profiles.md`

## License

This package is released under Apache License 2.0.
