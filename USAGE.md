# Using ContextWeave

ContextWeave is an installable skill package, not a standalone application binary.

The package is meant to be:

- installed into a compatible skill directory
- read by an agent as documentation plus deterministic helper scripts

Typical installation patterns include:

- a project-scoped skills directory
- a user-scoped skills directory

The exact installation path depends on the host agent tool.
This package itself stays host-agnostic:

- install the whole `skills/contextweave/` directory from the source repository as one skill package
- place it in the directory your host already uses for installed skills
- let the host discover and trigger `SKILL.md` through its standard skill mechanism

This installable package does not bundle host-specific adapter docs or a custom launcher.

## Installation Shape

The installed package directory should keep the name `contextweave/`.

This file is the operator guide for repository-level installation guidance and helper-script use.

If you are reading from a source checkout, the installable skill root lives at:

- `skills/contextweave/`

The repository root may also contain landing-page READMEs, marketing assets, and other human-facing documentation that are not part of the installed skill directory.

Typical layouts look like:

```text
<user-skills-dir>/
  contextweave/
    SKILL.md
    package-metadata.json
    managed-assets.json
    references/
    profiles/
    scripts/
```

```text
<project-skills-dir>/
  contextweave/
    SKILL.md
    package-metadata.json
    managed-assets.json
    references/
    profiles/
    scripts/
```

You can install it by copying or symlinking the package directory into a compatible skills folder.

Examples:

```bash
cp -R /path/to/contextweave/skills/contextweave /path/to/<user-skills-dir>/contextweave
```

```bash
ln -s /absolute/path/to/contextweave/skills/contextweave /path/to/<project-skills-dir>/contextweave
```

If you are using the Skills CLI against the public GitHub repository, the canonical install form is:

```bash
npx skills add https://github.com/Frappucc1no/contextweave --skill contextweave
```

Keep the package contents together.
Do not copy only `SKILL.md` without the accompanying `references/`, `profiles/`, and `scripts/` folders.
Do not remove `package-metadata.json`; it is the package's version and capability source of truth.
Do not remove `managed-assets.json`; packaged helpers use it as the single declaration source for managed storage-root assets on the current `0.2.1` release line.
When building a public release from a source checkout, exclude local metadata and caches such as `.git/`, `__pycache__/`, `*.pyc`, and `.DS_Store`.

For controlled audit or regression checks, you may temporarily point helpers at an alternate managed-assets file by setting `CONTEXTWEAVE_MANAGED_ASSETS_PATH=/absolute/path/to/file.json` for that single command invocation.

## Managed Asset Registry

The current `0.2.1` release line ships:

- `managed-assets.json`

This file is the single package-level declaration source for:

- required managed files
- optional managed files
- required managed directories
- managed directories
- supported dynamic storage-root file patterns
- optional managed namespaces such as `STORAGE_ROOT/companion/`

Packaged helpers should consume this file rather than maintaining repeated hard-coded path allowlists.

If this file is missing or malformed, treat the package as invalid rather than best-effort.

## Host Expectations

ContextWeave expects a host agent tool that can:

- read an installed `SKILL.md`
- follow package-relative references such as `references/...` and `profiles/...`
- work on file-based projects
- allow explicit execution of packaged helper scripts when deterministic support is needed
- support its own normal skill install/discovery flow for a single packaged skill directory

## Concurrency Boundary

ContextWeave does not promise safe arbitrary overlapping writes to the same project workspace.

For the current `0.2.1` release line, the packaged mutating helpers enforce a minimal hard-guard layer:

- project-scoped write locking
- atomic replace for managed overwrite-style files
- revision-aware commits for `context_brief.md`, `rolling_summary.md`, and `update_protocol.md`
- revision-aware milestone appends for daily logs

For the current `0.2.1` release line:

- read-only helpers may run at any time
- mutating helpers are serialized single-project operations
- if another tool may have written recently, rerun `validate_context.py` or `preflight_context_check.py` before writing
- do not run `init_context.py`, `archive_logs.py`, `remove_context.py`, or `manage_entry_bridge.py` concurrently on the same project
- direct manual overwrites of managed files bypass these hard guards and should be treated as unsupported
- helpers automatically reclaim clearly stale write locks when the recorded lock pid is no longer alive
- if a lock still needs manual recovery, use `unlock_write_lock.py` instead of deleting the lock file blindly

## Runtime Requirements

The packaged helper scripts currently assume:

- a UTF-8 capable filesystem environment
- a file-based project workspace that the host agent can read and update

Current package `0.2.1` / protocol `1.0` runtime limits:

<!-- ContextWeave metadata sync start: runtime-requirements -->
- minimum Python version: `3.10`
- supported `workspace_language` values:
  - `en`
  - `zh-CN`
- supported root entry files for thin bridges:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `GEMINI.md`
  - `.github/copilot-instructions.md`
<!-- ContextWeave metadata sync end: runtime-requirements -->

If your host environment cannot meet those assumptions, treat the helper scripts as unsupported rather than best-effort.

## Script Invocation

Run helper scripts explicitly with any Python `3.10+` interpreter that is available in your host environment.
The exact command name is host-specific:

- macOS/Linux often use `python3`
- Windows often uses `py -3.13` or another `py -3.x` launcher target
- some environments may expose a full interpreter path instead

Point that interpreter at the installed package path:

```text
<python-3.10+ interpreter> /path/to/contextweave/scripts/init_context.py ...
<python-3.10+ interpreter> /path/to/contextweave/scripts/validate_context.py ...
<python-3.10+ interpreter> /path/to/contextweave/scripts/remove_context.py ...
<python-3.10+ interpreter> /path/to/contextweave/scripts/manage_entry_bridge.py ...
```

Concrete examples:

```bash
# macOS/Linux
python3.13 /path/to/contextweave/scripts/init_context.py ...

# Windows
py -3.13 \path\to\contextweave\scripts\init_context.py ...
```

If you are already inside the installed `contextweave/` package directory, or inside `skills/contextweave/` in a source checkout, the equivalent shorter form is:

```text
<python-3.10+ interpreter> scripts/init_context.py ...
```

Do not assume the scripts are executable directly as `./script.py` and do not assume the host agent runs them automatically.

These scripts are helper utilities that ship inside the skill package.
They are not the primary user interface of ContextWeave.

## Helper Script Map

The installable package currently ships these user-facing helper scripts:

### `init_context.py`

- Purpose: initialize a new ContextWeave sidecar in a project
- Typical use: first-time setup
- Writes files: yes
- Safety model: refuses conflicting storage modes and refuses partial or untrusted pre-existing sidecar content; a pre-existing sidecar must already contain both `config.json` and `state.json`, and that `state.json` must pass the shared state contract loader; rerunning against an already healthy workspace is idempotent, and `--force` does not reset an existing healthy sidecar
- Hidden-mode side effect: may add a managed ContextWeave block to `.git/info/exclude`; if that managed block is already malformed, initialization now refuses instead of silently treating it as healthy
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project
- Rerun note: `init_context.py` is for first-time setup, not for rebuilding current project state; use revision-aware helpers for later content changes
- `--create-daily-log` note: this flag creates an empty daily-log scaffold for today; it is optional and should not be treated as proof that a milestone already happened
- Scaffold note: the scaffold does not consume a real entry number; the first real append still becomes `entry-1`

### `validate_context.py`

- Purpose: validate managed files, markers, versions, and structural integrity
- Typical use: after setup, after repairs, before trusting a workspace
- Writes files: no
- Safety model: read-only; reports non-managed assets inside the storage root when they are not covered by the managed asset registry

### `detect_project_root.py`

- Purpose: resolve the current ContextWeave project root and storage root
- Typical use: debugging, tooling, integration checks
- Writes files: no
- Safety model: read-only

### `preflight_context_check.py`

- Purpose: run a continuity freshness and write-target check before a formal write, or when a heavier verification pass is preferred over a minimal cold start
- Typical use: before a major write, or during a deeper continuity review after the initial restore pass
- Writes files: no
- Safety model: read-only; returns primary write targets, conditional review targets, and the current revision context needed for safe helper writes
- Staleness signals: marks the summary as stale both when newer non-context workspace artifacts exist and when `workspace_revision` has advanced beyond the summary's `base_workspace_revision`
- Cold-start note: default behavior now stays on the lighter sidecar-visible freshness path; normal cold start should still restore and review first, not automatically continue project work
- `--full` note: add this flag when you intentionally want the heavier workspace artifact scan before a higher-confidence write or audit pass
- `--quick` compatibility note: this flag still exists, but it now just makes the default quick path explicit

### `archive_logs.py`

- Purpose: move older daily logs into `daily_logs/archive/`
- Typical use: retention cleanup after log growth
- Writes files: yes
- Safety model: preview-first; requires `--yes` to apply; `--before` works as a standalone date filter unless `--max-active` is also explicitly set
- Revision note: archiving older logs does not by itself advance `workspace_revision` when the latest active daily-log cursor stays unchanged
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project

### `commit_context_file.py`

- Purpose: safely commit a prepared `context_brief.md`, `rolling_summary.md`, or `update_protocol.md`
- Typical use: AI or a human prepares content, then commits it with revision checks
- Writes files: yes
- Safety model: requires expected file revision and expected workspace revision; refuses stale writes; validates marker-safe `writer-id` values; rejects missing/duplicate/unknown required section markers before writing
- `update_protocol.md` behavior: this helper can write `update_protocol.md`, but it does not independently reread project-local override prose before every commit
- Concurrency boundary: serialized per project via the shared write lock

### `append_daily_log_entry.py`

- Purpose: safely append a milestone entry to a daily log
- Typical use: add a new milestone entry without rewriting the entire daily log from scratch
- Writes files: yes
- Safety model: requires expected workspace revision; validates required daily-log sections before writing; rejects marker-unsafe `writer-id` values; appends a new entry metadata block and updates sidecar state
- Scaffold behavior: if the target file is still an initialization scaffold, the first real append replaces that scaffold and writes `entry-1`
- Date policy: this helper requires an explicit `--date`. In normal use, pass the latest active ISO-dated daily log date suggested by preflight, or an intentionally newer ISO date when starting a new active day. Use `--allow-historical` only when intentionally backfilling an older log
- `update_protocol.md` behavior: this helper does not independently reread project-local override prose before every append; use preflight or explicit review first when local override rules matter
- Concurrency boundary: serialized per project via the shared write lock

### `recommend_workday.py`

- Purpose: recommend the current logical workday and append target date for a ContextWeave workspace
- Typical use: cross-day judgment, active-day review, or before choosing a daily-log append date
- Writes files: no
- Safety model: read-only recommendation helper; does not mutate sidecar files and does not replace explicit date confirmation for real writes
- Recommendation model: uses the latest active daily log, rolling summary `next_step`, rollover hour, and simple closure language heuristics to emit recommendation types such as `continue_active_day` or `start_new_active_day`
- Explicit intent model: `--session-intent` lets the caller elevate the user's current intent into the recommendation decision, using the same recommendation-type vocabulary returned by the helper
- Date priority model: an explicit `--preferred-date` takes priority over the helper's default suggestion. If the preferred date disagrees with the heuristic result, the helper returns `review_date_before_append`.
- Project-local override model: if `update_protocol.md` contains explicit workday or time-policy cues, the helper surfaces those cues and may return `review_date_before_append` instead of silently applying the heuristic suggestion
- Current scope note: the machineized signal set currently includes the latest active daily log cursor, `rolling_summary.md` `next_step`, closure-language heuristics, explicit session intent, and surfaced project-local time-policy cues. Broader workspace new-day trajectory remains an operator-reviewed signal rather than a separate machine-readable contract in `v0.2.1`.
- Relationship to preflight: this helper complements, not replaces, `preflight_context_check.py`; use it when deciding the likely workday path, then still use preflight before formal writes

### `summarize_continuity_status.py`

- Purpose: summarize continuity confidence, recommended actions, and workday guidance in one read-only response
- Typical use: ambient resume status, continuity review, or a single structured checkpoint before deciding the next operator action
- Writes files: no
- Safety model: read-only; combines current workspace revision, rolling summary freshness, recommended actions, and workday recommendation without mutating the workspace
- Snapshot model: includes a structured `continuity_snapshot` payload containing the currently seen workspace revision, summary revision, context-brief revision, update-protocol revision, latest active daily-log cursor, logical workday, confidence, and task type
- Workday output model: includes the heuristic recommendation, the applied decision-priority source, and any project-local time-policy cues surfaced from `update_protocol.md`
- Intent model: accepts the same optional `--session-intent` hint as `recommend_workday.py`, so a status review can incorporate the user's explicit current intent without mutating workspace state
- Scope note: this helper is an orientation surface, not a write surface; formal writes still require `preflight_context_check.py` plus the normal revision-aware helpers

### `stage_recovery_proposal.py`

- Purpose: stage a prepared recovery proposal into `companion/recovery/proposals/`
- Typical use: after a human or model has prepared a recovery proposal from user-provided history materials
- Writes files: yes
- Safety model: acquires the project write lock, validates the proposal against the minimum `v0.2.1` section set, refuses empty source content, creates the managed companion directories if needed, and refuses to overwrite an existing staged proposal
- Scope note: this helper only manages proposal placement; it does not decide proposal contents and does not promote anything into core continuity files

### `record_recovery_review.py`

- Purpose: record a prepared review note for a staged recovery proposal under `companion/recovery/review_log/`
- Typical use: after a human or model reviews a proposal and wants to preserve the review outcome before promotion
- Writes files: yes
- Safety model: acquires the project write lock, requires the proposal file to live under `companion/recovery/proposals/`, validates the review against the minimum `v0.2.1` review structure, refuses empty source content, and refuses to overwrite an existing review record
- Scope note: this helper records review state only; promotion into `rolling_summary.md`, `daily_logs/`, or `context_brief.md` still goes through the normal helper write path

### `prepare_recovery_promotion.py`

- Purpose: prepare structured safe-write context for a reviewed recovery proposal before promotion into core continuity files
- Typical use: after a proposal and review record already exist and a model or human is ready to choose durable target content
- Writes files: no
- Safety model: read-only; requires the proposal to live under `companion/recovery/proposals/`, the review to live under `companion/recovery/review_log/`, the review filename to match the proposal stem, and both documents to satisfy the minimum `v0.2.1` proposal/review structure
- Output model: returns proposal/review digests plus the current `safe_write_context` for `rolling_summary.md`, `context_brief.md`, and the latest daily-log append cursor
- Scope note: this helper does not promote anything by itself; it only prepares the promotion context for the existing write helpers

## Revision-Aware Write Flow

When a session needs deterministic write safety:

1. Run `preflight_context_check.py --json` for the default quick path, or `preflight_context_check.py --full --json` when you intentionally want the heavier workspace artifact scan.
2. Read the returned `safe_write_context`.
3. Let the agent or human prepare the actual content change.
4. Use `commit_context_file.py` for overwrite-style files.
5. Use `append_daily_log_entry.py` for milestone log entries.

This keeps the split clear:

- the agent decides what to write
- the helper scripts refuse stale or overlapping writes when the revision context no longer matches
- the helper scripts do not act as semantic editors or fact-checkers for the prepared content itself
- `preflight_context_check.py`, `archive_logs.py`, and bridge guidance are the main helper surfaces that explicitly call out `update_protocol.md` review in the current `0.2.1` release line

### `remove_context.py`

- Purpose: remove an existing ContextWeave sidecar from a project
- Typical use: uninstall, cleanup for one project, or recovery removal for a damaged workspace
- Writes files: yes
- Safety model: preview-first; refuses non-managed assets unless `--force` is explicitly passed; refuses sidecar removal while managed bridge blocks still exist in root entry files
- Uninstall note: the current `0.2.1` release line keeps uninstall as a two-step flow when root entry files also contain managed bridge blocks. Remove bridge blocks first, then remove the sidecar
- Recovery note: if normal workspace detection fails, this helper can fall back to recovery discovery; use `--storage-mode hidden|visible` to disambiguate sidecar conflicts
- Failure note: if sidecar removal succeeds but follow-up cleanup such as `.git/info/exclude` removal fails, the helper reports that partial-cleanup state explicitly instead of hiding it behind a generic failure
- Hidden-mode side effect: may remove the managed ContextWeave block from `.git/info/exclude`
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project

### `manage_entry_bridge.py`

- Purpose: preview, apply, or remove thin bridges in supported root entry files
- Typical use: connect root entry files to ContextWeave continuity files
- Writes files: yes
- Safety model: preview-first; only supported root entry files are allowed; malformed existing bridge blocks are rejected fail-closed; the current `0.2.1` release line accepts exactly one bridge target per invocation
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project

### `unlock_write_lock.py`

- Purpose: inspect or remove a stale project-scoped ContextWeave write lock
- Typical use: recovery after an interrupted mutating helper leaves `.contextweave.write.lock` behind
- Writes files: yes, but only when removing a lock
- Safety model: preview-first; refuses to remove a lock whose recorded pid still appears alive unless `--force` is explicitly passed
- Recovery note: this helper can be run from a project subdirectory; it will search upward for the project-root lock path

## Managed Bridge And Exclude Boundaries

Thin bridges only apply to these root entry files:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`

Bridge block boundaries:

```text
<!-- ContextWeave managed bridge start -->
...
<!-- ContextWeave managed bridge end -->
```

Hidden-sidecar exclude block boundaries:

```text
# ContextWeave managed block start
...
# ContextWeave managed block end
```

Those markers define the ContextWeave-managed region.
If they become incomplete, duplicated, or reordered, validation may fail and bridge management should not be treated as healthy.

### Internal helper module

- `_common.py` is an internal shared module
- it is not intended to be called directly as a user-facing script

## Typical First Steps

1. Install the whole `skills/contextweave/` directory from the source repository into the skill directory your host already uses.
2. Let the host rediscover skills using its standard skill flow.
3. Open a terminal in the installed `contextweave/` package directory, or in `skills/contextweave/` if you are working from a source checkout.
4. Run:

```bash
python3.13 scripts/init_context.py /absolute/path/to/project
python3.13 scripts/validate_context.py /absolute/path/to/project --json
```

5. Confirm that `validate_context.py` returns `"valid": true`.
6. Optionally bridge an existing root entry file.
7. Only add `--create-daily-log` if you intentionally want an empty daily-log scaffold for today.

If your environment uses a different compatible interpreter, replace `python3.13` with any Python `3.10+` interpreter available on that machine.
