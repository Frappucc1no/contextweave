# Software Project Coordination Profile

Use this profile when the project is driven by:

- engineering planning
- specs and implementation coordination
- software project status continuity
- repo-level project organization
- multi-session software project handoff

This profile is coordination-oriented.

It is not a full autonomous coding runtime profile.

## Primary Risks

Software projects drift when:

- the implementation state and the documented state diverge
- specs and plans fall behind the actual workspace
- different sessions anchor on different assumptions
- coordination notes become a weak substitute for explicit current state
- blockers and ownership gaps stay implicit instead of visible

## What to Emphasize

In this profile, emphasize:

- verified project state continuity
- decision traceability
- spec and plan alignment
- reducing drift across sessions and tools
- clear next-step ownership at the project level

## File Emphasis

- `STORAGE_ROOT/context_brief.md`
  Keep mission, phase, scope, source of truth, and core workflow boundaries clear.
  Prefer section keys rather than display headings when reasoning about structure:
  - `mission` for project objective
  - `audience_stakeholders` for team ownership and coordination surfaces
  - `current_phase` for current delivery phase
  - `scope` for system boundary and delivery scope
  - `source_of_truth` for code/spec/plan authority
  - `core_workflow` for coordination flow boundaries
  Display headings may render as localized labels such as `Source of Truth` or `事实来源`.

- `STORAGE_ROOT/rolling_summary.md`
  Focus on:
  - `current_state` for the actual validated project state right now
  - `active_judgments` for active coordination assumptions, tradeoffs, or decisions
  - `risks_open_questions` for blockers, unresolved dependencies, and verification gaps
  - `next_step` for the next coordination move

- `STORAGE_ROOT/daily_logs/`
  Record milestone implementation outcomes, validated changes, and meaningful coordination shifts.

## Common Anti-Pattern

Do not confuse software-project coordination with full coding automation.

Do not let plans or backlog notes substitute for verified current state.

RecallLoom can support software projects well at the project-state layer without claiming to replace the entire engineering execution stack.
