# General Project Continuity Profile

Use this profile when the project is driven by:

- mixed deliverables rather than one dominant artifact type
- cross-functional coordination across multiple roles
- long-running initiatives that span planning, execution, and review
- internal, client, operational, or creative projects that need continuity
- uncertainty about which specialized profile is the right fit

This is the default ContextWeave profile.

Use it unless a specialized profile is a high-confidence match.

## Primary Risks

General long-running projects drift when:

- the project mission stays implicit while tasks keep moving
- mixed artifacts evolve but the current state is not re-aligned
- next-step ownership is assumed rather than written down
- unresolved questions get buried inside scattered notes
- sessions continue from different assumptions because no specialized lens fits cleanly

## What to Emphasize

In this profile, emphasize:

- stable mission and phase framing
- source-of-truth clarity across mixed artifacts
- current-state clarity that a new session can trust quickly
- explicit next-step ownership
- unresolved risks and handoff readiness

## File Emphasis

- `STORAGE_ROOT/context_brief.md`
  Keep the mission, audience, phase, scope, source of truth, core workflow, and boundaries explicit.
  Prefer section keys rather than display headings when reasoning about structure:
  - `mission` for the overall objective
  - `audience_stakeholders` for the people involved or affected
  - `current_phase` for the current stage of the work
  - `scope` for what is in and out right now
  - `source_of_truth` for the authoritative artifact or evidence surface
  - `core_workflow` for how the work typically moves forward
  - `boundaries` for constraints, non-goals, and guardrails

- `STORAGE_ROOT/rolling_summary.md`
  Focus on:
  - `current_state` for what is true right now across the project
  - `active_judgments` for stable working assumptions or decisions
  - `risks_open_questions` for unresolved concerns that still affect progress
  - `next_step` for the clearest next move

- `STORAGE_ROOT/daily_logs/`
  Record milestone-level progress, cross-functional shifts, and handoff-worthy changes.

## Common Anti-Pattern

Do not force a mixed or unclear project into a specialized profile just because one artifact is currently prominent.

Stay on the general profile until the project shape is clearly dominated by a specialized continuity risk pattern.
