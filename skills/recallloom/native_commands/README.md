# RecallLoom Native Command Templates

This directory contains host-specific native command templates for platforms that support user-defined commands.

Current supported hosts:

- `claude-code`
- `gemini-cli`
- `opencode`

These templates are not meant to be copied blindly as-is.
They contain a `__DISPATCHER_COMMAND__` placeholder and are intended to be rendered through:

- `scripts/install_native_commands.py`

The current native command set is intentionally small:

- `rl-init`
- `rl-status`
- `rl-validate`

Each command calls the unified RecallLoom dispatcher rather than re-implementing host-specific logic.
