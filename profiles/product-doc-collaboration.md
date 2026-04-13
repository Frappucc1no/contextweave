# Product Document Collaboration Profile

Use this profile when the project is driven by:

- PRDs
- strategy docs
- scope discussions
- stakeholder-aligned product writing

## Primary Risks

Product-document projects drift when:

- scope changes are discussed but not reflected in the current state
- stakeholder concerns are remembered vaguely
- old priorities linger after a new decision
- milestone document progress gets mixed with loose brainstorming

## What to Emphasize

In this profile, emphasize:

- decision traceability
- scope drift control
- stakeholder context
- next-step clarity
- phase-aware document progress

## File Emphasis

- `STORAGE_ROOT/context_brief.md`
  Keep the project mission, audience, phase, scope, and decision boundaries explicit.
  Prefer section keys rather than display headings when reasoning about structure:
  - `mission` for document purpose
  - `audience_stakeholders` for readers and stakeholders
  - `current_phase` for the active document phase
  - `scope` for product surface and decision scope
  - `boundaries` for decision constraints and non-goals
  Display headings may render as localized labels such as `Audience / Stakeholders` or `受众与相关方`.

- `STORAGE_ROOT/rolling_summary.md`
  Focus on:
  - `current_state` for the current document and product state
  - `active_judgments` for stable product direction or tradeoff decisions
  - `risks_open_questions` for blockers and unresolved concerns
  - `next_step` for the next recommended document move

- `STORAGE_ROOT/daily_logs/`
  Record milestone decisions, completed sections, and meaningful changes in stakeholder direction.

## Common Anti-Pattern

Do not treat every discussion point as a durable decision.

Only write stable product direction into maintained memory once it materially changes the working model.
