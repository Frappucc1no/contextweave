# ContextWeave

> A file-native continuity layer for long-running AI projects.

`ContextWeave` keeps the important state of a project durable, reviewable, and reusable across sessions, tools, and agents.

English · [简体中文](./README.zh-CN.md)

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Protocol Version](https://img.shields.io/badge/protocol-1.0-0f766e)](./package-metadata.json)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](./package-metadata.json)

## What It Is

`ContextWeave` is built for projects that continue over time.

Instead of depending on one chat window or one platform's private memory, it keeps a small, explicit project state inside the workspace itself.

That project state is designed to answer four practical questions quickly:

- What is this project?
- What is true right now?
- What important progress has already happened?
- What should happen next?

## What The Current Version Adds

The current `0.2.0` version extends the original `0.1.0` continuity model without replacing it.

The direction is:

- safer cold starts
- smaller default reads
- clearer continuity confidence
- recommendation-first workday handling
- history-assisted recovery through reviewed proposals
- a minimal companion namespace inside the sidecar

The upgrade is intentionally conservative:

- it does **not** introduce a second storage root
- it does **not** silently auto-write project state
- it does **not** ship executable `/cw-*` commands
- it does **not** turn companion data into the new source of truth

## Product Model

The current model has three layers.

### 1. Core continuity

This is the durable project truth.

- `context_brief.md`
- `rolling_summary.md`
- `daily_logs/YYYY-MM-DD.md`

### 2. Ambient continuity

This is the read-and-judge layer.

It helps a session:

- detect that the project already uses ContextWeave
- read the smallest useful continuity set first
- judge whether the current continuity is still trustworthy
- recommend what needs review next

### 3. Minimal companion foundation

This is the smallest workflow layer around the core.

It currently exists to:

- hold recovery proposals
- hold review records
- keep those intermediate assets inside the sidecar without polluting core truth files

It does **not** currently mean:

- a full task system
- a full inbox system
- a command runtime

## What It Does Well

- keeps stable framing separate from current state
- keeps current state separate from milestone evidence
- gives sessions a real continuity surface to resume from
- makes project continuity auditable in workspace files
- reduces drift between sessions, tools, and agents
- adds guardrails around formal writes

## What It Does Not Try To Do

`ContextWeave` is not:

- a general-purpose memory server
- a replacement for every platform-native memory feature
- a heavy autonomous agent framework
- a full task management product
- a silent auto-documentation machine

The goal is narrower:

> keep the right project state durable and make future sessions easier to resume safely

## Safety And Compatibility

The current `0.2.0` version is designed as a safe extension of `0.1.0`, not a reset.

That means:

- healthy `0.1.0` workspaces should continue to work
- new sidecar assets stay optional
- `companion/` should appear only when companion-backed features are actually used
- older projects should not be forced to rebuild their sidecar just to stay valid

If you are upgrading from `0.1.0`, see:

- the repository-level `2026-04-16-contextweave-0.1.0-to-v0.2.0-migration-and-rollback-note.md` when you are reviewing the full source checkout

## Core Files

The storage root remains one of:

- `PROJECT_ROOT/.contextweave/`
- `PROJECT_ROOT/contextweave/`

Inside that root, the core continuity model remains:

- `config.json`
- `state.json`
- `context_brief.md`
- `rolling_summary.md`
- `daily_logs/`
- `update_protocol.md`

The current `0.2.0` version also recognizes an optional managed namespace:

- `STORAGE_ROOT/companion/`

Current intended subtree:

- `STORAGE_ROOT/companion/recovery/`

This is for:

- recovery proposals
- review records
- archived recovery artifacts

It is not a free-form scratch folder.

## Managed Asset Registry

The current package also ships:

- `managed-assets.json`

This file is the package-level declaration source for:

- required managed files
- optional managed files
- required managed directories
- managed directories
- supported dynamic file patterns
- optional managed namespaces

That keeps helper behavior and validation rules aligned as the sidecar grows.

## Cold Start Behavior

The current cold-start direction is:

1. find the project root
2. read the minimum continuity set first
3. expand only when the task really needs more context
4. judge freshness before formal writes
5. recommend before executing

In practice this means:

- start from `config.json`, `state.json`, and `rolling_summary.md`
- review `update_protocol.md` when local rules matter
- read `context_brief.md` only when framing is needed
- read the latest active daily log only when milestone evidence or workday judgment needs it

The important product behavior is:

> restoring context should not automatically continue unfinished work

## Workday Recommendation

The current `0.2.0` version also adds recommendation-first workday handling.

This layer helps answer:

- should the session continue the previous active day?
- should it start a new active day?
- does the previous day appear unclosed?
- what date is the best default suggestion for a new log entry?

It is recommendation-only.

It does **not** silently:

- close the previous day
- create a new daily log
- backfill historical dates

## History-Assisted Recovery

The current recovery direction is intentionally narrow.

It supports:

- user-provided transcripts
- user-provided exports
- user-provided summaries
- reviewed recovery proposals

It does **not** currently support:

- automatic scanning of undocumented local history caches
- using platform memory as the source of truth
- promoting history directly into core files without review

The intended flow is:

1. collect history material
2. prepare a recovery proposal
3. review that proposal
4. prepare promotion context
5. only then write durable changes through the normal write helpers

## Installed Package Layout

Treat the full `contextweave/` directory as one installable package:

```text
contextweave/
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── USAGE.md
├── package-metadata.json
├── managed-assets.json
├── profiles/
├── references/
├── scripts/
├── LICENSE
└── NOTICE
```

Do not copy only `SKILL.md`.
When packaging from a source checkout, exclude local metadata and caches such as `.git/`, `__pycache__/`, `*.pyc`, and `.DS_Store`.

## Common Installation Pattern

If your environment uses directory-based skills, install the whole package directory:

```bash
cp -R /path/to/contextweave /path/to/<skills-dir>/contextweave
```

or

```bash
ln -s /absolute/path/to/contextweave /path/to/<skills-dir>/contextweave
```

Typical paths:

- Codex: `.agents/skills/contextweave`
- Claude Code: `~/.claude/skills/contextweave` or `.claude/skills/contextweave`
- other directory-based environments: the tool's normal skills directory

## Where To Read Next

- [SKILL.md](./SKILL.md): agent-facing entrypoint
- [USAGE.md](./USAGE.md): helper usage and runtime notes
- [references/protocol.md](./references/protocol.md): protocol model
- [references/file-contracts.md](./references/file-contracts.md): file-level contract
- [references/operation-playbooks.md](./references/operation-playbooks.md): read/write playbooks
- repository-level host adapter overview in `docs/adapters/README.md` when you are reading the full source checkout; that file is not bundled inside a standalone installed `contextweave/` package

## Current Status

This repository is now on the `0.2.0` release line.

What is already true:

- the `0.1.0` continuity baseline exists
- the current `0.2.0` version has already added managed asset registration
- the current `0.2.0` version has already added smaller cold-start guidance
- the current `0.2.0` version has already added workday recommendation helpers
- the current `0.2.0` version has already added the first reviewed recovery workflow helpers

What is intentionally still out of scope for this release:

- a command runtime for `/cw-*`
- full task and capture companion layers

The right expectation is:

> the `0.2.0` release line is usable, scoped, and publicly publishable, while larger command and companion expansions remain future work

## License

This project is released under Apache License 2.0.  
See [LICENSE](./LICENSE) and [NOTICE](./NOTICE) for details.
