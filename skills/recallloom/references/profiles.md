# Profiles

Profiles are guidance layers built on top of the shared RecallLoom protocol.

They do not replace the core protocol.

## Default Rule

Use `general-project-continuity.md` by default.

Switch to a specialized profile only when the project shape is a high-confidence match.

If the project is mixed, ambiguous, or still changing shape, stay on the general profile.

## Current Profiles

- `general-project-continuity.md`
- `research-writing.md`
- `product-doc-collaboration.md`
- `software-project-coordination.md`

## How to Choose

Use this quick selector:

1. Is the project primarily driven by sources, claims, evidence, and long-form analytical writing?
   Use `research-writing.md`.
2. Is the project primarily driven by PRDs, RFCs, strategy docs, scope decisions, or stakeholder-aligned product writing?
   Use `product-doc-collaboration.md`.
3. Is the project primarily driven by engineering planning, spec-to-implementation coordination, or repo-level software project continuity?
   Use `software-project-coordination.md`.
4. If none of the above is a high-confidence match, use `general-project-continuity.md`.

High confidence means the main artifact type, working style, and likely drift risks all line up clearly.

When choosing, look at:

- artifact type
- working style
- continuity risks
- evidence needs

## Profile Summary

- `general-project-continuity.md`
  - default profile for mixed, cross-functional, or unclear long-running projects
- `research-writing.md`
  - best when the hard problem is keeping claims, evidence, and section progress aligned
- `product-doc-collaboration.md`
  - best when the hard problem is keeping scope, stakeholder context, and durable decisions aligned
- `software-project-coordination.md`
  - best when the hard problem is keeping specs, implementation state, and project coordination aligned

## Shared vs Profile-Specific

Shared:

- file model
- write discipline
- stale retirement
- cold-start expectations

Profile-specific:

- evidence patterns
- artifact emphasis
- likely drift risks
- preferred review lens
