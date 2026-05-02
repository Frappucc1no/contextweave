# Anti-Patterns

## Do Not Turn the Rolling Summary Into a Log

`rolling_summary.md` is a snapshot, not a running journal.

## Do Not Write Every Small Change to the Daily Log

Daily logs are for milestones, not noise.

## Do Not Treat Carryover As A Milestone

Cross-day carryover is a continuity decision, not a daily-log milestone by itself.

## Do Not Leave False or Outdated Facts in Place

Stale or disproven content should be retired.

## Do Not Update Context After Trivial Reads

Reading existing context does not itself justify a write.

## Do Not Load Everything by Default

Use progressive disclosure. Read only what is needed.

## Do Not Write Just Because A Conversation Happened

`no_write` is a normal successful exit when no durable project fact changed.

## Do Not Store Stable Rules In The Rolling Summary By Default

Long-lived workflow rules and source-of-truth routing belong in `context_brief.md`, not as rolling-summary clutter.

## Do Not Put Correct Content In The Wrong Layer

A fact can be true and still belong in the wrong continuity file.

- Stable rules belong in `context_brief.md`.
- Current phase, active risks, active judgments, and next steps belong in `rolling_summary.md`.
- Completed decisions, validations, releases, and other durable evidence belong in the daily log.

If one event contains more than one kind of fact, split the facts by layer.
Do not copy the same sentence into multiple files.

## Do Not Let Helpers Decide Semantic Layers

Read-side helpers can expose freshness, trust, revision context, and static write-tier guidance.
They are not content classifiers.

The agent must still decide whether the prepared continuity content is `stable_rule`, `current_state`, `milestone_evidence`, `no_write`, `defer`, `confirm`, or `multi_layer_split`.

If the agent cannot explain the layer choice in one sentence, stop with `defer` or `confirm` instead of guessing.

## Do Not Hard-Bind the Core Protocol to One Platform

Platform-specific guidance belongs in adapters, not in the core protocol.

## Do Not Confuse Package Support With Sidecar Protocol

Package support gates belong to the installed package runtime and user cache.
Do not write support state into `state.json`, and do not use `protocol_version` as a substitute for package support policy.

## Do Not Hard-Block Solely Because Advisory Fetch Failed

Network failure by itself should produce `unknown_offline` or reuse a prior cache result.
It should not become a surprise mutating-action block unless a cached or fresh advisory explicitly requires that block.
