---
name: contextweave
description: Use when a task involves continuing a project, restoring project context, maintaining file-based project memory, updating current-state summaries, or recording meaningful progress across sessions. Works best for long-horizon, file-based projects and supports research writing, product document collaboration, and software project coordination.
---

# ContextWeave

ContextWeave is a portable context harness for session-based agents.

It provides a lightweight file model for project continuity across sessions without requiring heavy infrastructure.

The goal is not to remember everything. The goal is to keep the right project state durable, readable, and recoverable across sessions.

## Package Scope

This file is the agent-facing entrypoint for the installable `contextweave/` skill package.

Install and trigger this package through your host agent's normal skill discovery flow.
ContextWeave itself does not define a custom host-specific launcher inside the package.

For package inventory, installation guidance, and helper-script runtime details, see:

- `README.md`
- `USAGE.md`

## When To Use It

Use ContextWeave when you need to:

- continue an existing project after a pause
- restore project context from maintained files
- maintain current-state project memory
- record meaningful milestone progress
- reduce context drift across sessions or tools

Typical triggers include:

- continue this project
- restore project context
- pick up where we left off
- update the project memory
- record today’s progress
- prepare a clean next-step handoff inside the maintained project files

## Core File Model

ContextWeave uses three primary memory layers:

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

- `PROJECT_ROOT/.contextweave/` (default)
- `PROJECT_ROOT/contextweave/` (optional visible sidecar)

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

ContextWeave prefers the smallest valid write set, not maximal updating.

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

ContextWeave currently provides three profiles:

- `profiles/research-writing.md`
- `profiles/product-doc-collaboration.md`
- `profiles/software-project-coordination.md`

Use the profile that best matches the project shape.

Profiles do not replace the core protocol. They refine emphasis, evidence handling, and common drift risks for different project types.

## What ContextWeave Does Not Try To Be

ContextWeave does not try to be:

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
