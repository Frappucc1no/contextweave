# RecallLoom Protocol

## Contents

- Purpose
- Core Concepts
- Storage Resolution
- State vs Evidence
- Update Discipline
- Progressive Disclosure
- Machine-Readable Contract
- Validator Semantics
- Managed Bridge And Exclude Blocks
- Versioning

## Purpose

RecallLoom defines a lightweight, file-native protocol for preserving project continuity across sessions.

It is designed for projects where the main challenge is not a single turn of reasoning, but staying aligned over time:

- keeping stable framing stable
- keeping current state current
- keeping milestone evidence durable
- avoiding context drift across sessions or tools

For protocol `1.0`, this protocol supports serialized multi-session use over time.
It does not promise safe overlapping writes by multiple writers on the same project.

Mutating helper operations should be serialized per project.

## Core Concepts

RecallLoom separates project memory into three distinct roles.

### Stable framing

Stored in `STORAGE_ROOT/context_brief.md`.

This file should explain:

- what the project is
- what phase it is in
- what the main source of truth is
- what boundaries or constraints matter

It should stay short and change rarely.

For protocol `1.0`, this file also carries required file-state metadata.

### Current state

Stored in `STORAGE_ROOT/rolling_summary.md`.

This file is the primary continuity surface for active work.

It should answer:

- what is true right now
- what the active judgments are
- what the risks are
- what the next step is

It is an overwrite-style snapshot, not a running log.

For protocol `1.0`, this file also carries required file-state metadata.

### Milestone evidence

Stored in `STORAGE_ROOT/daily_logs/YYYY-MM-DD.md`.

These files preserve milestone-level history:

- deliverables completed
- important confirmed facts
- key decisions
- blockers
- next recommended direction

They are append-only and intentionally less frequent.

For protocol `1.0`, each daily log also carries required entry metadata that identifies appended milestone units.

An initialization helper may optionally create an empty daily-log scaffold for the current day.
That scaffold is still only a starting structure, not proof that a milestone already occurred.
When a scaffold exists, the first real append still becomes `entry-1`.

## Storage Resolution

RecallLoom uses one and only one storage root per project.

Allowed storage modes:

- `hidden`
- `visible`

Default storage mode:

- `hidden`

Resolved storage roots:

- `hidden` -> `PROJECT_ROOT/.recallloom/`
- `visible` -> `PROJECT_ROOT/recallloom/`

### Required config file

Every valid storage root must contain:

- `config.json`
- `state.json`

This file is required for both storage modes.

If `config.json` is malformed or violates the contract, tools should stop with a clear configuration error instead of silently guessing.

### Resolution algorithm

When a tool resolves `STORAGE_ROOT`, it should:

1. locate the project root
2. check for `PROJECT_ROOT/.recallloom/config.json`
3. check for `PROJECT_ROOT/recallloom/config.json`
4. if exactly one exists, that storage root is authoritative
5. if neither exists, there is no initialized RecallLoom workspace
6. if both exist, that is an invalid conflict state and tools should stop with a clear error

RecallLoom does not support silently preferring one sidecar over the other when both are present.

The storage root is reserved for RecallLoom-managed assets.

Do not place unrelated project files inside:

- `PROJECT_ROOT/.recallloom/`
- `PROJECT_ROOT/recallloom/`

For the current `0.3.0` release line on protocol `1.0`, the package-level declaration source for managed storage-root assets is:

- `recallloom/managed-assets.json`

Tools should use that declaration source, together with the core protocol rules in this document, to decide which optional managed namespaces and dynamic file patterns are valid.

This allows the protocol to stay explicit while avoiding repeated hard-coded path lists across helpers.

### Optional managed namespaces

Protocol `1.0` continues to center on the core managed assets:

- `config.json`
- `state.json`
- `context_brief.md`
- `rolling_summary.md`
- `daily_logs/`
- `update_protocol.md`

For the current `0.3.0` release line, one additional optional managed namespace is recognized:

- `STORAGE_ROOT/companion/`

This namespace is:

- RecallLoom-managed
- optional
- reserved for intermediate or workflow-layer assets that do not replace core truth files

This namespace is not:

- a second storage root
- a free-form user scratch directory
- a place for unrelated project files

When a workspace has not enabled companion-backed features, the absence of `STORAGE_ROOT/companion/` must not be treated as damage or incompleteness.

Current recognized subtree in this `0.3.0` release line:

- `STORAGE_ROOT/companion/recovery/`

This subtree is for:

- recovery proposals
- review records
- archived recovery artifacts

This subtree is not for:

- replacing `rolling_summary.md`, `daily_logs/`, or `context_brief.md`
- keeping arbitrary project notes
- turning companion into a second truth layer

`state.json` is the machine-readable sidecar state source for:

- workspace revision
- update_protocol revision
- bridge state
- git exclude mode

Removal tools may refuse to proceed unless the user explicitly confirms forced deletion of unknown assets.

### Why this rule exists

This rule keeps the protocol:

- explicit
- scriptable
- safe to validate
- understandable to external integrators

## State vs Evidence

This distinction is central to the protocol.

- State belongs in `rolling_summary.md`.
- Evidence and milestone history belong in daily logs.
- Stable framing belongs in `context_brief.md`.

If this separation breaks down, continuity quality degrades quickly:

- the current state becomes noisy
- milestone evidence becomes hard to find
- framing gets buried in operational detail

## Lifecycle

The protocol is built around a small number of repeated lifecycle actions:

1. Cold start
2. Current-state maintenance
3. Milestone recording
4. Compression
5. Archive
6. Stale content retirement

### Cold start

Read the maintained files in order before continuing work.

### Current-state maintenance

Keep the rolling summary up to date whenever the working model changes in a durable way.

### Milestone recording

Write to daily logs sparingly and only when the session produced milestone-level value.

### Compression

When `rolling_summary.md` becomes hard to scan, compress it and preserve moved detail in the daily log.

### Archive

When daily logs accumulate past their useful immediate horizon, archive older entries according to project rules.

### Stale content retirement

False, superseded, or no-longer-useful content should not remain in the active continuity layer.

## Multi-Session Assumptions

RecallLoom assumes multiple sessions may touch the same project over time.

This can mean:

- the same agent resuming later
- a different agent resuming later
- multiple tools interacting with the same files over time

The protocol therefore prefers:

- reread-before-write
- overwrite only where appropriate
- append-only milestone logs
- explicit reconciliation when other writers may exist

For packaged helper writes in the current `0.3.0` release line, RecallLoom also uses:

- project-scoped write locking
- revision-aware commits for overwrite-style files
- revision-aware appends for daily-log entries
- atomic replace for managed overwrite-style writes

This safety layer does not replace editorial judgment:

- the agent still decides what should change
- the helpers decide whether the prepared write is still safe to apply
- the helpers do not decide whether the prepared content is semantically correct or editorially sound

Recommended deterministic write flow:

1. run preflight
2. prepare the intended content change
3. commit overwrite-style files with revision-aware helper writes
4. append milestone log entries with revision-aware helper appends

## Progressive Disclosure

RecallLoom is intentionally designed so that not everything needs to be read at once.

The expected loading order is:

1. skill entrypoint
2. matching profile if needed
3. shared protocol docs as needed
4. project files under `STORAGE_ROOT`
5. helper scripts only when deterministic support is needed

This is how the package stays lightweight while still being structured.

## Machine-Readable Contract

RecallLoom uses a machine-readable contract layer for managed workspace files.

This contract is normative for protocol `1.0`.

### File markers

Every managed file must begin with a file marker of this shape:

```text
<!-- recallloom:file=<file_key> version=<protocol_version> lang=<workspace_language> -->
```

Examples:

- `recallloom:file=context_brief`
- `recallloom:file=rolling_summary`
- `recallloom:file=daily_log`
- `recallloom:file=update_protocol`

### Section markers

Every required structured section must include a section marker of this shape:

```text
<!-- section: <section_key> -->
```

Examples:

- `section: mission`
- `section: current_state`
- `section: next_step`

### File-state metadata marker

For `context_brief.md`, `rolling_summary.md`, and `update_protocol.md`, the file also carries a file-state metadata marker.

It uses this shape:

```text
<!-- file-state: revision=<n> | updated-at=<timestamp> | writer-id=<writer> | base-workspace-revision=<n> -->
```

For protocol `1.0`:

- helper-generated files place this marker in the leading metadata block
- third-party writers should follow the helper-generated placement rather than relying on parser tolerance
- current readers accept it within the first four lines as a compatibility tolerance

### Daily-log entry metadata marker

For `daily_logs/YYYY-MM-DD.md`, the file also carries an entry metadata marker for the first appended milestone unit.

It uses this shape:

```text
<!-- daily-log-entry: entry-id=<id> | created-at=<timestamp> | writer-id=<writer> | entry-seq=<n> -->
```

- a daily log may contain multiple milestone entry blocks
- each appended entry begins with its own `daily-log-entry` marker
- append-only means adding a new entry block rather than rewriting prior entry blocks in place

### Daily-log scaffold marker

An initialization helper may optionally create a scaffold daily log before any real milestone entry exists.

That scaffold uses this shape:

```text
<!-- daily-log-scaffold: true -->
```

For protocol `1.0`:

- scaffold logs are not counted as active milestone entries
- scaffold logs keep `state.json.daily_logs` in the null/zero cursor shape until the first real append
- the first real append to a scaffold still becomes `entry-1`

For protocol `1.0`:

- helper-generated files place the first entry marker immediately after the file marker
- third-party writers should follow that placement for the first entry marker
- readers identify the latest entry by scanning the whole log, not by assuming a fixed line number

### Rolling summary metadata marker

For `rolling_summary.md`, the second line is also part of the machine-readable contract.

It must use this exact shape:

```text
<!-- last-writer: [<tool_name>] | YYYY-MM-DD -->
```

Example:

```text
<!-- last-writer: [RecallLoom] | 2026-04-07 -->
```

### What is normative

For protocol `1.0`, the normative machine-readable layer is:

- file markers
- file marker version metadata
- the rolling-summary `last-writer` metadata marker
- file-state metadata markers
- daily-log entry metadata markers
- section markers
- `lang` metadata in file markers
- `config.json` fields defined by the protocol
- `state.json` fields defined by the protocol

Language consistency rule:

- every managed file marker `lang` value must match `config.json.workspace_language`

Current supported workspace languages for protocol `1.0`:

- `en`
- `zh-CN`

For protocol `1.0`, RecallLoom is a two-language system.

It does not claim generic locale support beyond the values listed above.

Version compatibility rules:

- `config.json.protocol_version` must use a supported RecallLoom protocol version
- every managed file marker `version` must use a supported RecallLoom protocol version
- when `config.json.protocol_version` is supported, managed file marker versions should match it

Storage declaration rule:

- `config.json.storage_mode` must match the physical sidecar location
- `.recallloom/config.json` implies `storage_mode=hidden`
- `recallloom/config.json` implies `storage_mode=visible`

### What is display-only

For protocol `1.0`, the display layer is:

- visible markdown headings
- natural-language wording inside files
- localized heading labels

This means:

- headings may vary within the supported protocol `1.0` workspace languages
- labels may differ within the supported protocol `1.0` workspace languages
- marker keys must remain stable

### Why this distinction matters

This allows RecallLoom to support:

- multilingual workspace files
- deterministic validation
- stable third-party integrations
- future renderer evolution without breaking the core contract

## Validator Semantics

For protocol `1.0`, validator behavior is deterministic and marker-driven.

Expected semantic checks include:

- duplicate section markers are invalid
- unknown section markers should be surfaced explicitly
- unsupported protocol versions should be surfaced explicitly
- storage declaration mismatches should be surfaced explicitly
- malformed bridge or exclude managed blocks should be surfaced explicitly
- missing required file-state or daily-log-entry metadata should be surfaced explicitly

## Managed Bridge And Exclude Blocks

RecallLoom also uses managed block boundaries for two integration surfaces:

- thin bridges inside supported root entry files
- the hidden-sidecar exclude block inside `.git/info/exclude`

### Supported root entry files for thin bridges

Current supported root entry files for the current `0.3.0` release line:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`

### Bridge managed block boundaries

Bridge blocks use these exact boundary markers:

```text
<!-- RecallLoom managed bridge start -->
...
<!-- RecallLoom managed bridge end -->
```

### Exclude managed block boundaries

The hidden-sidecar exclude block uses these exact boundary markers:

```text
# RecallLoom managed block start
...
# RecallLoom managed block end
```

These markers define the RecallLoom-managed region.

Validation may report errors if:

- only one boundary marker is present
- duplicate managed blocks exist
- start/end ordering is invalid

## Versioning

For protocol `1.0`, version metadata is part of the enforced machine-readable contract.

Current protocol `1.0` rule set:

- `config.json.protocol_version` must use a supported protocol version
- every managed file marker `version` must use a supported protocol version
- when `config.json.protocol_version` is supported, managed file marker versions should match it

Current supported protocol versions:

- `1.0`

Validator behavior for protocol `1.0`:

- unsupported config versions should be surfaced as errors
- unsupported file marker versions should be surfaced as errors
- config/file version mismatches should be surfaced as errors

Compatibility intent:

- keep the core file model stable across protocol `1.0` workspaces
- evolve details through package revisions without weakening the current validator-visible contract
