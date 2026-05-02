# Using RecallLoom

RecallLoom is an installable skill package, not a standalone application binary.

The package is meant to be:

- installed into a compatible skill directory
- read by an agent as documentation plus deterministic helper scripts

Typical installation patterns include:

- a project-scoped skills directory
- a user-scoped skills directory

The exact installation path depends on the host agent tool.
This package itself stays host-agnostic:

- install the whole `skills/recallloom/` directory from the source repository as one skill package
- place it in the directory your host already uses for installed skills
- let the host discover and trigger `SKILL.md` through its standard skill mechanism

This installable package keeps the core protocol host-agnostic.
It does not depend on a required host-specific adapter or a custom launcher, though it does ship optional native wrapper templates for supported hosts.

This file is the operator guide.
Start from `README.md` or `README.zh-CN.md` for the public first-use path, and come here when you need command-level details, helper behavior, or debugging boundaries.

Operator rule for first attach:

- prefer the normal user flow of “initialize the project” before dropping to command aliases
- treat `rl-init` and `scripts/recallloom.py init` as the stable operator surface
- if no compatible Python `3.10+` runtime is available, stop and report blocked rather than hand-building `.recallloom/` or `recallloom/`

## Public Language Rules

RecallLoom should default to user task language rather than internal implementation language.

- Prefer “initialize”, “restore”, “import existing project reality”, “continue”, and “record progress”.
- Do not make helper names, section keys, or the internal `coldstart` label the first thing users see.
- Treat internal action names as operator surfaces, not as the default public mental model.

## Fast And Deep Paths

RecallLoom now treats fast path as the default interaction mode.

- Fast path: shortest trustworthy route, lowest interruption cost, and usually one short interaction.
- Deep path: only when sources conflict, source coverage is insufficient, risk is too high for a direct recommendation, or the user explicitly asks for deeper review.
- Host-memory signals remain opt-in and hint-only; if they participate, the interaction should bias toward explicit review rather than silent trust.

## Layered Write Judgment

Continuity writes are still agent decisions.
Helpers can make the write safer by returning freshness state, revision guards, and default write-tier targets, but they do not decide what the prepared content means.

Before writing, the agent should choose one of:

- `no_write`
- `stable_rule`
- `current_state`
- `milestone_evidence`
- `multi_layer_split`
- `defer`
- `confirm`

Use `context_brief.md` for stable rules and source-of-truth routing, `rolling_summary.md` for active current state, and the daily log for milestone evidence.
When a session creates multiple kinds of facts, split the facts by layer instead of duplicating one sentence across files.
If the layer cannot be explained clearly, stop with `defer` or `confirm`.

## Installation Shape

The installed package directory should keep the name `recallloom/`.

This file is the operator guide for repository-level installation guidance and helper-script use.

If you are reading from a source checkout, the installable skill root lives at:

- `skills/recallloom/`

The repository root may also contain landing-page READMEs, marketing assets, and other human-facing documentation that are not part of the installed skill directory.

Typical layouts look like:

```text
<user-skills-dir>/
  recallloom/
    SKILL.md
    package-metadata.json
    managed-assets.json
    references/
    profiles/
    scripts/
    native_commands/
    LICENSE
    NOTICE
```

```text
<project-skills-dir>/
  recallloom/
    SKILL.md
    package-metadata.json
    managed-assets.json
    references/
    profiles/
    scripts/
    native_commands/
    LICENSE
    NOTICE
```

You can install it by copying or symlinking the package directory into a compatible skills folder.

Examples:

```bash
cp -R /path/to/recall-loom/skills/recallloom /path/to/<user-skills-dir>/recallloom
```

```bash
ln -s /absolute/path/to/recall-loom/skills/recallloom /path/to/<project-skills-dir>/recallloom
```

If you are using a Skills CLI, install and update through the host's normal skill flow:

```bash
npx skills add https://github.com/Frappucc1no/recall-loom --skill recallloom
npx skills update
```

Keep the package contents together.
Do not copy only `SKILL.md` without the accompanying `references/`, `profiles/`, `scripts/`, and `native_commands/` folders.
Do not remove `package-metadata.json`; it is the package's version and capability source of truth.
Do not remove `managed-assets.json`; packaged helpers use it as the single declaration source for managed storage-root assets.
When packaging from a source checkout, exclude local metadata and caches such as `.git/`, `__pycache__/`, `*.pyc`, and `.DS_Store`.

For controlled audit or regression checks, you may temporarily point helpers at an alternate managed-assets file by setting `RECALLLOOM_MANAGED_ASSETS_PATH=/absolute/path/to/file.json` for that single command invocation.

## Managed Asset Registry

The package ships:

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

RecallLoom expects a host agent tool that can:

- read an installed `SKILL.md`
- follow package-relative references such as `references/...` and `profiles/...`
- work on file-based projects
- allow explicit execution of packaged helper scripts when deterministic support is needed
- support its own normal skill install/discovery flow for a single packaged skill directory

## Concurrency Boundary

RecallLoom does not promise safe arbitrary overlapping writes to the same project workspace.

The packaged mutating helpers enforce a minimal hard-guard layer:

- project-scoped write locking
- atomic replace for managed overwrite-style files
- revision-aware commits for `context_brief.md`, `rolling_summary.md`, and `update_protocol.md`
- revision-aware milestone appends for daily logs

For the current package line:

- read-only helpers may run at any time
- mutating helpers are serialized single-project operations
- if another tool may have written recently, rerun `validate_context.py` or `preflight_context_check.py` before writing
- do not run `init_context.py`, `archive_logs.py`, `remove_context.py`, or `manage_entry_bridge.py` concurrently on the same project
- direct manual overwrites of managed files bypass these hard guards and should be treated as unsupported
- helpers automatically reclaim clearly stale write locks when the recorded lock pid is no longer alive
- if a lock still needs manual recovery, use `unlock_write_lock.py` instead of deleting the lock file blindly

## Package Support Gate

RecallLoom package support is checked separately from project sidecar protocol compatibility.

For the current package line, helpers perform a lightweight daily package-support check:

- the advisory is cached by local date and installed package path
- dispatcher may pass same-day support payloads through `RECALLLOOM_SUPPORT_STATE_JSON`, but child helpers still authorize from their own same-day cache or advisory read
- cache files live in the user cache, not in project `.recallloom/`
- network or advisory failures do not, by themselves, hard-block first use
- `readonly_only` blocks mutating helpers while keeping diagnostic and read-only helpers available
- `diagnostic_only` keeps only diagnostic actions available

The default advisory URL is stored in `skills/recallloom/package-metadata.json` as `support_advisory_url`.
The default URL points at the canonical public advisory document for this package.
Operators can rerun support/readiness checks against the same canonical URL after publishing package updates rather than rewriting the URL for each environment.
Operators can override it with `RECALLLOOM_SUPPORT_ADVISORY_URL`, or test / mirror it with `RECALLLOOM_SUPPORT_ADVISORY_FILE`.

When blocked, helpers return the shared failure contract with `blocked_reason: package_support_blocked` and a `package_support` object containing the support state, action level, advisory source, cache source, update hints, and install-topology diagnostic reason.

See `skills/recallloom/references/package-support-policy.md` for the advisory schema and environment overrides.

## Runtime Requirements

The packaged helper scripts currently assume:

- a UTF-8 capable filesystem environment
- a file-based project workspace that the host agent can read and update

Current package / protocol runtime limits:

<!-- RecallLoom metadata sync start: runtime-requirements -->
- minimum Python version: `3.10`
- supported `workspace_language` values:
  - `en`
  - `zh-CN`
- supported root entry files for thin bridges:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `GEMINI.md`
  - `.github/copilot-instructions.md`
<!-- RecallLoom metadata sync end: runtime-requirements -->

If your host environment cannot meet those assumptions, treat the helper scripts as unsupported rather than best-effort.

## Blocked Contract

Runtime and initialization failures should stay deterministic:

- if the environment cannot supply Python `3.10+`, stop with a blocked runtime result instead of inventing a sidecar
- if the target path does not look like a project root yet, fail closed and choose the right root first; a brand-new empty directory is still allowed when you intentionally want RecallLoom to initialize a new project root
- if an existing sidecar is partial, damaged, or conflicting, repair it before retrying

## Script Invocation

Run helper scripts explicitly with any Python `3.10+` interpreter that is available in your host environment.
The exact command name is host-specific:

- many environments can simply use `python`
- some macOS/Linux environments prefer `python3`
- some Windows environments prefer `py`
- some environments may expose a full interpreter path instead

Point that interpreter at the installed package path:

```text
<python-3.10+ interpreter> /path/to/recallloom/scripts/recallloom.py init ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/recallloom.py resume ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/recallloom.py validate ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/recallloom.py status ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/recallloom.py bridge ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/init_context.py ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/validate_context.py ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/remove_context.py ...
<python-3.10+ interpreter> /path/to/recallloom/scripts/manage_entry_bridge.py ...
```

Concrete examples:

```bash
# Generic
python /path/to/recallloom/scripts/recallloom.py init /absolute/path/to/project
```

If you are already inside the installed `recallloom/` package directory, or inside `skills/recallloom/` in a source checkout, the equivalent shorter form is:

```text
<python-3.10+ interpreter> scripts/recallloom.py init ...
<python-3.10+ interpreter> scripts/init_context.py ...
```

Do not assume the scripts are executable directly as `./script.py` and do not assume the host agent runs them automatically.

These scripts are helper utilities that ship inside the skill package.
They are not the primary user interface of RecallLoom.

## Unified Command Entry

The package includes a single operator-friendly dispatcher:

- `scripts/recallloom.py`

This file is meant to give operators one stable entrypoint for the most common actions instead of making them memorize multiple helper script names.

The initial command surface is:

- `init`
- `resume`
- `validate`
- `status`
- `bridge`

Typical forms:

```bash
python scripts/recallloom.py init /absolute/path/to/project
python scripts/recallloom.py resume /absolute/path/to/project
python scripts/recallloom.py validate /absolute/path/to/project
python scripts/recallloom.py status /absolute/path/to/project
python scripts/recallloom.py bridge /absolute/path/to/project --file AGENTS.md --yes
```

At the product language level, these can be referred to as:

- `rl-init`
- `rl-resume`
- `rl-validate`
- `rl-status`
- `rl-bridge`

In hosts that support native custom commands, those names can later map directly to real commands.
In hosts that do not, they still work as stable action names that an agent can interpret and execute through the same underlying workflow.

This is the command/operator layer.
It is not the only way users should think about first use.

The primary user flow remains:

1. install the skill package
2. explicitly invoke RecallLoom once in the conversation
3. let the agent decide whether initialization is needed
4. confirm initialization, or use `rl-init` when the host exposes that stable action name

If the host cannot provide Python `3.10+`, do not replace this flow with manual sidecar creation.

## Host Restore Routing Contract

Initialized-project restore should be treated as a routing contract, not as open-ended skill relevance:

1. On generic prompts such as “continue this project”, “restore project context”, or “pick up where we left off”, the host/router should run a cheap valid-sidecar gate before broad skill fan-out.
2. If a valid RecallLoom sidecar exists, route the request into the normal RecallLoom fast path and keep the first response low-jargon and result-first.
3. If the sidecar is missing, conflicting, damaged, or clearly insufficient for the task, the host may fall back to initialization, repair, or broader review flows.
4. Broad workflow or memory systems should defer in the RecallLoom-first case instead of claiming the first hop.
5. Native wrappers and bridge text can support explicit operator actions, but they do not replace host/router first-claim control for generic restore requests.

Current operator anchor:

- `rl-resume` is the single stable operator-facing action name for the initialized-project restore checkpoint in the current package line.
- `rl-status` remains the operator-facing inspection command for continuity status.
- Natural-language restore prompts remain the primary public path.
- Do not invent a host-local stable action name that is not documented and tested in the package.

## Native Command Wrappers

The package also ships a helper for hosts that support native custom commands:

- `scripts/install_native_commands.py`

This helper renders and installs local command wrappers for:

- `claude-code`
- `gemini-cli`
- `opencode`

Current wrapper scope:

- `rl-init`
- `rl-resume`
- `rl-status`
- `rl-validate`

Typical project-scoped install examples:

```bash
<python-3.10+ interpreter> scripts/install_native_commands.py <ABS_PROJECT_ROOT> --host claude-code --scope project --yes
<python-3.10+ interpreter> scripts/install_native_commands.py <ABS_PROJECT_ROOT> --host gemini-cli --scope project --yes
<python-3.10+ interpreter> scripts/install_native_commands.py <ABS_PROJECT_ROOT> --host opencode --scope project --yes
```

If you want all supported host wrappers at once:

```bash
<python-3.10+ interpreter> scripts/install_native_commands.py <ABS_PROJECT_ROOT> --host all --scope project --yes
```

User-scoped install remains supported, but it is intentionally downgraded in the public guidance:

```bash
<python-3.10+ interpreter> scripts/install_native_commands.py <ABS_PROJECT_ROOT> --host claude-code --scope user --yes
```

Use `user` scope only when you explicitly want wrappers in your host-global command directory and accept that they depend on an absolute dispatcher path. The public default remains `project` scope.

`project` scope is only naturally more portable when the dispatcher path itself lives inside the project and can remain relative. If the helper reports that `scope=project` still produced an absolute dispatcher path, treat that install as a portability downgrade rather than assuming project scope is automatically stable.

Important target-path note:

- when you run this helper from inside the installed `recallloom/` package directory, do **not** use that package directory as the `project` scope target
- `project` scope should point at the real project root where you want `.claude/commands`, `.gemini/commands`, or `.opencode/commands` to be created
- if your host environment does not expose a plain `python` command, either use the correct interpreter directly or pass `--dispatcher-command`

Important boundary:

- these wrappers are convenience entrypoints
- they do not replace the RecallLoom skill package
- they all delegate to the same underlying dispatcher
- bridge and continuity state semantics stay unchanged
- they are a convenience layer, not the primary user path
- the generated dispatcher command uses the current Python interpreter path by default, which is safer than assuming a global `python` alias, but it may still drift when your environment upgrades or relocates that interpreter
- the public wrapper surface includes `rl-resume` as the single operator-facing restore target
- `rl-bridge` remains part of the action surface through the dispatcher and helper scripts, but is not required as a native wrapper in this package line
- generic continue/restore routing still belongs to host/router policy rather than wrapper count

## Helper Script Map

The installable package currently ships these user-facing helper scripts:

### `recallloom.py`

- Purpose: unified operator-friendly wrapper for the most common RecallLoom workflows
- Typical use: first entrypoint for init / resume / validate / status / bridge
- Writes files: depends on subcommand
- Safety model: does not replace helper semantics; it orchestrates existing helpers and keeps them as the execution truth
- Failure-contract note: normalized failure payloads now keep machine-readable routing fields such as `blocked_reason`, `recoverability`, `surface_level`, and `trust_effect`
- Initial scope:
  - `init`
  - `resume`
  - `validate`
  - `status`
  - `bridge`

### `install_native_commands.py`

- Purpose: render and optionally install local native command wrappers for supported host CLIs
- Typical use: optional convenience layer for hosts that benefit from `rl-init`, `rl-resume`, `rl-status`, and `rl-validate` as native custom commands
- Writes files: yes when `--yes` is passed; otherwise preview-only
- Safety model: preview-first; refuses unsupported hosts, requires a resolvable dispatcher command, and does not alter RecallLoom sidecar semantics
- Failure-contract note: runtime, target path, dispatcher/template, and filesystem failures now return the shared machine-readable failure schema
- Current host scope:
  - `claude-code`
  - `gemini-cli`
  - `opencode`
- Scope recommendation:
  - `project` scope is the recommended public default
  - `user` scope remains supported but is intentionally downgraded because it depends on a stable absolute dispatcher path
  - `project` scope can still degrade to an absolute dispatcher path when the dispatcher itself is outside the project; when that happens, expect advisory output and treat it as less portable than a relative in-project dispatcher

### `init_context.py`

- Purpose: initialize a new RecallLoom sidecar in a project
- Typical use: first-time setup
- Writes files: yes
- Safety model: refuses conflicting storage modes and refuses partial or untrusted pre-existing sidecar content; a pre-existing sidecar must already contain both `config.json` and `state.json`, and that `state.json` must pass the shared state contract loader; rerunning against an already healthy workspace is idempotent, and `--force` does not reset an existing healthy sidecar
- Hidden-mode side effect: may add a managed RecallLoom block to `.git/info/exclude`, using the `.recallloom/` entry; if that managed block is already malformed, initialization now refuses instead of silently treating it as healthy
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project
- Rerun note: `init_context.py` is for first-time setup, not for rebuilding current project state; use revision-aware helpers for later content changes
- `--create-daily-log` note: this flag creates an empty daily-log scaffold for today; it is optional and should not be treated as proof that a milestone already happened
- Scaffold note: the scaffold does not consume a real entry number; the first real append still becomes `entry-1`
- Failure-contract note: initialization failures now use the shared failure schema instead of a separate local contract copy

### `validate_context.py`

- Purpose: validate managed files, markers, versions, and structural integrity
- Typical use: after setup, after repairs, before trusting a workspace
- Writes files: no
- Safety model: read-only; reports non-managed assets inside the storage root when they are not covered by the managed asset registry

### `detect_project_root.py`

- Purpose: resolve the current RecallLoom project root and storage root
- Typical use: debugging, tooling, integration checks
- Writes files: no
- Safety model: read-only

### `preflight_context_check.py`

- Purpose: run a continuity freshness and write-target check before a formal write, or when a heavier verification pass is preferred over a minimal cold start
- Typical use: before a major write, or during a deeper continuity review after the initial restore pass
- Writes files: no
- Safety model: read-only; returns primary write targets, conditional review targets, and the current revision context needed for safe helper writes
- Write-tier note: now also returns the default `stable_rule` / `current_state` / `milestone_evidence` mapping plus explicit exit modes such as `no_write`, `merge_current_state`, and `append_milestone`
- Trust note: now also returns `sidecar_trust_state`, `continuity_drift_risk_level`, and `allowed_operation_level` so hosts can distinguish structural trust from drift risk before writes
- Staleness signals: marks the summary as stale both when newer non-context workspace artifacts exist and when `workspace_revision` has advanced beyond the summary's `base_workspace_revision`
- Cold-start note: default behavior now stays on the lighter sidecar-visible freshness path; normal cold start should still restore and review first, not automatically continue project work
- `--full` note: add this flag when you intentionally want the heavier workspace artifact scan before a higher-confidence write or audit pass
- `--quick` compatibility note: this flag still exists, but it now just makes the default quick path explicit
- `--fail-on-stale` note: when combined with a stale result, the helper exits non-zero instead of only reporting the risk in JSON/text output
- Current read-side note: this helper now surfaces handoff-first fields such as `active_task_digest`, `blocked_digest`, `latest_relevant_log_digest`, `suggested_handoff_sections`, and `suggested_read_set`

### `archive_logs.py`

- Purpose: move older daily logs into `daily_logs/archive/`
- Typical use: retention cleanup after log growth
- Writes files: yes
- Safety model: preview-first; requires `--yes` to apply; `--before` works as a standalone date filter unless `--max-active` is also explicitly set
- Revision note: archiving older logs does not by itself advance `workspace_revision` when the latest active daily-log cursor stays unchanged
- Failure-contract note: runtime, root resolution, invalid date / retention input, malformed daily-log filenames or sequence state, archive target collisions, write-lock contention, and filesystem rollback failures now return the shared machine-readable failure schema
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project

### `commit_context_file.py`

- Purpose: safely commit a prepared `context_brief.md`, `rolling_summary.md`, or `update_protocol.md`
- Typical use: AI or a human prepares content, then commits it with revision checks through `--source-file` or UTF-8 `--stdin`
- Writes files: yes
- Safety model: requires expected file revision and expected workspace revision; refuses stale writes; validates marker-safe `writer-id` values; rejects missing/duplicate/unknown required section markers before writing
- Failure-contract note: runtime, root resolution, no-root, prepared input, malformed target managed files, stale write context, attached-text safety, write-lock contention, and filesystem/state rollback failures now return the shared machine-readable failure schema
- `update_protocol.md` behavior: this helper can write `update_protocol.md`, but it does not independently reread project-local override prose before every commit
- Concurrency boundary: serialized per project via the shared write lock

### `append_daily_log_entry.py`

- Purpose: safely append a milestone entry to a daily log
- Typical use: add a new milestone entry without rewriting the entire daily log from scratch, using `--entry-file` or UTF-8 `--stdin`
- Writes files: yes
- Safety model: requires expected workspace revision; validates required daily-log sections before writing; rejects marker-unsafe `writer-id` values; appends a new entry metadata block and updates sidecar state
- Failure-contract note: runtime, root resolution, no-root, invalid date, prepared entry input, malformed target daily log, stale write context, historical append guard, attached-text safety, write-lock contention, and filesystem/state rollback failures now return the shared machine-readable failure schema
- Scaffold behavior: if the target file is still an initialization scaffold, the first real append replaces that scaffold and writes `entry-1`
- Date policy: this helper requires an explicit `--date`. In normal use, pass the logical-workday date suggested by preflight or `recommend_workday.py`. Use `--allow-historical` only when intentionally backfilling an older log
- `update_protocol.md` behavior: this helper does not independently reread project-local override prose before every append; use preflight or explicit review first when local override rules matter
- Concurrency boundary: serialized per project via the shared write lock

### `recommend_workday.py`

- Purpose: recommend the current logical workday and append target date for a RecallLoom workspace
- Typical use: cross-day judgment, active-day review, or before choosing a daily-log append date
- Writes files: no
- Safety model: read-only recommendation helper; does not mutate sidecar files and does not replace explicit date confirmation for real writes
- Recommendation model: uses the latest active daily log, rolling summary `next_step`, rollover hour, and closure language heuristics to emit structured workday guidance
- Carryover model: a previous active day without explicit closure now defaults to `start_new_day_with_carryover` instead of treating the prior day as a repair-first path
- Output model: returns `workday_state`, `recommendation_type`, `suggested_date`, `requires_user_confirmation`, and `user_visible_prompt_level`
- Explicit intent model: `--session-intent` lets the caller elevate the user's current intent into the recommendation decision, using the same recommendation-type vocabulary returned by the helper
- Date priority model: an explicit `--preferred-date` takes priority over the helper's default suggestion. If the preferred date disagrees with the heuristic result, the helper returns `review_date_before_append`.
- Project-local override model: if `update_protocol.md` contains explicit workday or time-policy cues, the helper surfaces those cues and may return `review_date_before_append` instead of silently applying the heuristic suggestion
- Failure-contract note: runtime, root resolution, no-root, invalid date / time inputs, malformed daily-log filenames, missing managed files or metadata markers, damaged state, and filesystem failures now return the shared machine-readable failure schema
- Current scope note: the machineized signal set includes the latest active daily log cursor, `rolling_summary.md` `next_step`, closure-language heuristics, explicit session intent, and surfaced project-local time-policy cues; it still stays in the helper surface rather than upgrading protocol `1.0`
- Relationship to preflight: this helper complements, not replaces, `preflight_context_check.py`; use it when deciding the likely workday path, then still use preflight before formal writes

### `summarize_continuity_status.py`

- Purpose: summarize continuity confidence, recommended actions, and workday guidance in one read-only response
- Typical use: ambient resume status, continuity review, or a single structured checkpoint before deciding the next operator action
- Writes files: no
- Safety model: read-only; combines current workspace revision, rolling summary freshness, recommended actions, and workday recommendation without mutating the workspace
- Snapshot model: includes a structured `continuity_snapshot` payload containing the currently seen workspace revision, summary revision, context-brief revision, update-protocol revision, latest active daily-log cursor, logical workday, confidence, and task type
- Workday output model: shares the same `workday_state`, carryover default, confirmation flags, and project-local time-policy review behavior as `recommend_workday.py`
- Trust output model: now also returns `sidecar_trust_state`, `continuity_drift_risk_level`, and `allowed_operation_level`
- Intent model: accepts the same optional `--session-intent` hint as `recommend_workday.py`, so a status review can incorporate the user's explicit current intent without mutating workspace state
- Scope note: this helper is an orientation surface, not a write surface; formal writes still require `preflight_context_check.py` plus the normal revision-aware helpers
- Current read-side note: this helper now shares the same freshness baseline and handoff-first digest fields as `preflight_context_check.py`

### `generate_coldstart_proposal.py`

- Purpose: generate a structured cold-start proposal from controlled source tiers before any continuity promotion happens
- Typical use: when a workspace is initialized but still empty-shell and you want a reviewable initial proposal instead of writing directly into `rolling_summary.md` or `context_brief.md`
- Writes files: no
- Safety model: read-only; Tier A/B/C are scanned by default, Tier D only enters through explicit `--source`, Tier E git signal only enters through explicit `--include-git-signal`, and Tier F host-memory sources remain disabled by default
- Host-memory adapter note: `--enable-host-memory` reserves the Tier F adapter entrance, but it stays explicit and hint-only. Enabling it requires an explicit source label, exactly one of `--host-memory-path` or `--host-memory-command`, and an explicit confidence level. Path mode may read the given file; command mode is declared in metadata but not auto-executed.
- Path-selection note: returns a `path_recommendation` object that distinguishes `fast_path` from `deep_path`. Fast path is recommended only when project framing plus current-state signals are already sufficient; host-memory use or weak source coverage upgrades the recommendation to deep path.
- Output model: returns a proposal markdown body plus machine-readable metadata such as `source_tiers_used`, `proposal_sections_present`, detected promotion targets, host-memory adapter state, and the recommended interaction path
- Failure-contract note: runtime, root resolution, no-root, invalid host-memory adapter input, damaged state, and filesystem failures now return the shared machine-readable failure schema
- Promotion note: this helper does not stage, review, or promote anything by itself; pair it with `stage_recovery_proposal.py` only after the generated proposal has been checked

### `stage_recovery_proposal.py`

- Purpose: stage a prepared recovery proposal into `companion/recovery/proposals/`
- Typical use: after a human or model has prepared a recovery proposal from user-provided history materials
- Writes files: yes
- Safety model: acquires the project write lock, validates the proposal against the minimum recovery proposal section set, refuses empty source content, creates the managed companion directories if needed, and refuses to overwrite an existing staged proposal
- Failure-contract note: runtime, source input, proposal structure, root resolution, overwrite, write-lock, and filesystem failures now return the shared machine-readable failure schema
- Structured output note: now returns machine-readable `proposal_sections_present`, detected source tiers, and detected promotion targets in addition to the staged proposal path
- Scope note: this helper only manages proposal placement; it does not decide proposal contents and does not promote anything into core continuity files

### `record_recovery_review.py`

- Purpose: record a prepared review note for a staged recovery proposal under `companion/recovery/review_log/`
- Typical use: after a human or model reviews a proposal and wants to preserve the review outcome before promotion
- Writes files: yes
- Safety model: acquires the project write lock, requires the proposal file to live under `companion/recovery/proposals/`, validates the review against the minimum recovery review structure, refuses empty source content, and refuses to overwrite an existing review record
- Failure-contract note: runtime, source input, review structure, proposal path / filename validation, root resolution, overwrite, write-lock, and filesystem failures now return the shared machine-readable failure schema
- Review-action note: returns a machine-readable `review_action` classification that distinguishes accept, accept-after-edit, reject, and hint-only outcomes
- Scope note: this helper records review state only; promotion into `rolling_summary.md`, `daily_logs/`, or `context_brief.md` still goes through the normal helper write path

### `prepare_recovery_promotion.py`

- Purpose: prepare structured safe-write context for a reviewed recovery proposal before promotion into core continuity files
- Typical use: after a proposal and review record already exist and a model or human is ready to choose durable target content
- Writes files: no
- Safety model: read-only; requires the proposal to live under `companion/recovery/proposals/`, the review to live under `companion/recovery/review_log/`, the review filename to match the proposal stem, and both documents to satisfy the minimum recovery proposal/review structure
- Failure-contract note: runtime, root resolution, proposal/review path and filename validation, malformed proposal/review content, damaged core continuity files, and filesystem failures now return the shared machine-readable failure schema
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
- `preflight_context_check.py`, `archive_logs.py`, and bridge guidance are the main helper surfaces that explicitly call out `update_protocol.md` review in the current package line

### `remove_context.py`

- Purpose: remove an existing RecallLoom sidecar from a project
- Typical use: uninstall, cleanup for one project, or recovery removal for a damaged workspace
- Writes files: yes
- Safety model: preview-first; refuses non-managed assets unless `--force` is explicitly passed; refuses sidecar removal while managed bridge blocks still exist in root entry files
- Uninstall note: the current package line keeps uninstall as a two-step flow when root entry files also contain managed bridge blocks. Remove bridge blocks first, then remove the sidecar
- Recovery note: if normal workspace detection fails, this helper can fall back to recovery discovery; use `--storage-mode hidden|visible` to disambiguate sidecar conflicts
- Failure note: if sidecar removal succeeds but follow-up cleanup such as `.git/info/exclude` removal fails, the helper reports that partial-cleanup state explicitly instead of hiding it behind a generic failure
- Failure-contract note: runtime, no-root, recovery resolution, invalid storage boundary, bridge-block cleanup requirements, unknown assets, write-lock contention, malformed git exclude blocks, and filesystem failures now return the shared machine-readable failure schema
- Hidden-mode side effect: may remove the managed RecallLoom block from `.git/info/exclude`
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project

### `manage_entry_bridge.py`

- Purpose: preview, apply, or remove thin bridges in supported root entry files
- Typical use: connect root entry files to RecallLoom continuity files
- Writes files: yes
- Safety model: preview-first; only supported root entry files are allowed; malformed existing bridge blocks are rejected fail-closed; the current package line accepts exactly one bridge target per invocation
- Attach-safety note: bridge text is scanned before apply; obvious prompt overrides, invisible unicode, and secret-exfil patterns hard block the write, while suspicious-but-ambiguous patterns are surfaced as warnings in the scan result
- Failure-contract note: bridge helper failures now return the shared machine-readable failure schema for attached-text safety blocks, invalid targets, malformed bridge blocks, missing continuity files, and write-lock contention
- Concurrency boundary: do not run concurrently with any other mutating helper on the same project

### `query_continuity.py`

- Purpose: query current RecallLoom continuity through a read-only recall surface
- Typical use: retrieve project-relevant continuity without manually reading every managed file
- Writes files: no
- Default read boundary: core continuity files first (`rolling_summary.md`, `context_brief.md`, latest active daily log, optional recent daily logs)
- Ranking model: when match strength ties, current-state files are preferred over historical logs in this order: `rolling_summary.md` -> `context_brief.md` -> latest active daily log -> recent daily logs
- Output model: returns `answer`, `hits`, `citations`, `risk_freshness_note`, `synthesized_recall`, `token_estimate`, `budget_hint`, `continuity_confidence`, `freshness_state`, `conflict_state`, `sidecar_trust_state`, `continuity_drift_risk_level`, `allowed_operation_level`, `output_variant`, and `override_review_targets`
- Answer-first rule: the compact and detailed output surfaces now follow the same order: `answer -> supporting citations -> risk/freshness note`
- Citation model: daily-log citations now include explicit `date` values in addition to `path`, `section`, and `source_type`
- Freshness model: the helper now defaults to the quick freshness path and can explicitly upgrade to the fuller workspace-artifact freshness pass when `--full` is requested; `conflict_state` still explicitly surfaces cases such as `workspace_artifact_newer_than_summary`, `summary_revision_stale`, or `multi_source_review_recommended`
- Freshness risk model: the returned `freshness_state` now also includes `freshness_risk_level` and `freshness_risk_note`, so quick-scan and stale-summary risk are explicit instead of hidden in lower-level booleans
- Override model: when `update_protocol.md` exists, the helper now surfaces it as an explicit review target before the recall should be used to choose a write target
- Output-variant model: `brief` maps to a compact attach-safe response, while `detailed` maps to a more expanded contextual response with a bounded `supporting_context_window`
- Budget model: `supporting_context_window` is now trimmed by a small budget instead of expanding every top hit in detailed mode
- Safety model: attach-safe output is scanned before return; companion is not read by default and no files are written

### `unlock_write_lock.py`

- Purpose: inspect or remove a stale project-scoped RecallLoom write lock
- Typical use: recovery after an interrupted mutating helper leaves `.recallloom.write.lock` behind
- Writes files: yes, but only when removing a lock
- Safety model: preview-first; refuses to remove a lock whose recorded pid still appears alive unless `--force` is explicitly passed
- Recovery note: this helper can be run from a project subdirectory; it will search upward for the project-root lock path
- Failure-contract note: runtime, recovery root resolution, live write-lock refusal, and filesystem failures now return the shared machine-readable failure schema

## Managed Bridge And Exclude Boundaries

Thin bridges only apply to these root entry files:

- `AGENTS.md`
- `CLAUDE.md`
- `GEMINI.md`
- `.github/copilot-instructions.md`

Bridge block boundaries:

```text
<!-- RecallLoom managed bridge start -->
...
<!-- RecallLoom managed bridge end -->
```

Hidden-sidecar exclude block boundaries:

```text
# RecallLoom managed block start
...
# RecallLoom managed block end
```

Those markers define the current managed region.
If they become incomplete, duplicated, or reordered, validation may fail and bridge management should not be treated as healthy.

### Internal helper module

- `_common.py` is an internal shared module
- it is not intended to be called directly as a user-facing script

## Typical First Steps

1. Install the whole `skills/recallloom/` directory from the source repository into the skill directory your host already uses.
2. Let the host rediscover skills using its standard skill flow.
3. Open a terminal in the installed `recallloom/` package directory, or in `skills/recallloom/` if you are working from a source checkout.
4. Run:

```bash
python scripts/recallloom.py init /absolute/path/to/project
```

5. Confirm that the `init` result reports a validated workspace.
6. Optionally bridge an existing root entry file.
7. Only add `--create-daily-log` if you intentionally want an empty daily-log scaffold for today.

If `python` on your machine does not point to a compatible Python `3.10+` interpreter, replace it with whatever Python `3.10+` command or full path is actually available on that machine.
