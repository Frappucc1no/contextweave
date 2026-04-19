<div align="center">

<h1>🧶 RecallLoom</h1>

**A long-running project should not feel like it has to restart every time you switch models, agents, or sessions.**

[![Version](https://img.shields.io/badge/version-v0.3.0-111827)](./skills/recallloom/package-metadata.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](./skills/recallloom/package-metadata.json)

**English** · [简体中文](./README.zh-CN.md)

</div>

RecallLoom is an installable continuity skill for long-running AI work. You install it once, connect it to a real project, and then simply speak naturally: `continue this project`, `restore project context`, `pick up where we left off`.

It is not another dashboard, and it is not a private memory silo locked inside one platform. RecallLoom keeps a small shared continuity surface inside the workspace itself, so the next model, the next agent, or the next collaborator can resume from the same project reality instead of rebuilding it from chat history.

<!-- Suggested image slot: ./docs/images/readme-hero-system.png -->

## 💡 Why RecallLoom?

If you already switch between `Claude Code`, `Codex`, `Gemini CLI`, `Qwen Code`, or hand work to fresh sessions, you have probably felt some version of this already:

- Every tool switch comes with a restart tax.
- Every new agent loses part of the project's why.
- Platform-native memory stops being useful the moment the work moves.
- New collaborators cannot tell what is actually true right now.
- Long-running work turns into a blur of history, half-finished ideas, and current conclusions.

What slows long-running AI work down is often not weak model quality. It is **broken project continuity**.

RecallLoom gives the project a place to keep its own memory in plain files inside the workspace, so whoever picks the work up next can recover the essentials without reconstructing the whole story from scratch.

## ✅ What Changes Once You Use It

- **Switching models feels less like restarting**: the key background, current state, progress, and next step already live with the project.
- **Fresh agents can enter faster**: they do not have to infer today's truth from yesterday's thread.
- **Collaboration gets easier**: new people can understand where the project stands without reading everything that ever happened.
- **“What is true now” becomes visible**: current reality stops getting buried under old discussion.
- **Resuming work feels calmer**: you return to a project that still knows itself.

## 🆕 What `v0.3.0` Establishes

`v0.3.0` is the read-side hardening release for RecallLoom.

It builds on the `v0.2.2` brand-cutover foundation and establishes three things together:

- **A query-oriented continuity recall surface**: `query_continuity.py` can now surface relevant continuity with citations, confidence, freshness, conflict state, and bounded supporting context.
- **A stronger shared read-side baseline**: `preflight`, `status`, and `query_continuity` now align on the same freshness and digest primitives instead of drifting into separate interpretations.
- **A safer attach-ready recall path**: read-side outputs now surface `update_protocol.md`, bound the contextual window, and run the attached-text scan across the returned recall surface.

This means `v0.3.0` is the first release where RecallLoom has both a unified brand/runtime surface and a materially stronger read-side recall layer for long-running work.

## 🧭 The Easiest Way To Think About It

> Think of RecallLoom as a project handbook that stays with the project, not with one session.

That handbook makes four things easy to recover:

- **What this project is**
- **What is true right now**
- **What important progress has happened**
- **What the next sensible move is**

You do not need to memorize internal file names to understand the value. The point is simply that the project stays understandable across time, tools, and handoffs.

## 🎯 Who It Fits Best

RecallLoom becomes much more valuable when a project has to continue across days, sessions, tools, models, or collaborators.

- **People who mix platforms and models**: move between tools without paying the full restart cost every time.
- **People who use multiple agents on the same project**: keep the project grounded even when fresh sessions keep entering the work.
- **Research and writing work**: keep source-backed thinking, progress, and open questions from drifting apart.
- **Product and document collaboration**: keep scope, decisions, and next actions easier to recover.
- **Software project coordination**: keep status, blockers, and implementation direction visible across sessions.
- **Mixed long-running work**: when a project spans writing, product, code, and operations at the same time, the general continuity path is the safest default.

## 🧩 Built-In Work Modes

RecallLoom ships with four built-in work modes so the same continuity idea can fit different project shapes. If you are unsure, start with the general mode.

| Work mode | Best when | What it helps keep steady |
|---|---|---|
| General continuity | The project mixes research, writing, product, code, or operations | The overall project reality, without over-assuming the project shape |
| Research writing | The work is driven by sources, claims, evidence, and long-form writing | Claims, evidence, and writing progress |
| Product docs | The work is driven by PRDs, RFCs, strategy docs, and stakeholder alignment | Scope, decisions, and open questions |
| Software coordination | The work is driven by engineering planning, repo execution, and implementation follow-through | Status, blockers, and next actions |

Typical natural-language triggers once the skill is installed:

- `continue this project`
- `restore project context`
- `pick up where we left off`
- `record today's progress`

<!-- Suggested image slot: ./docs/images/readme-profile-strip.png -->

## ✨ How It Stays Useful Without Becoming Heavy

RecallLoom works because it keeps a few kinds of project reality separate instead of blending everything into one giant note.

| Part of the handbook | What it helps the next session recover |
|---|---|
| Project explainer | What this project is and how to approach it |
| Current snapshot | What is true right now |
| Progress trail | What actually happened, not just what was discussed |
| Safety rail | When to read more carefully and when to write more carefully |

So instead of asking a new session to read everything, you give it a smaller, more stable surface to stand on first.

<!-- Suggested image slot: ./docs/images/readme-architecture-map.png -->

<details>
  <summary><strong>See the underlying files</strong></summary>

| Plain-English part | Under the hood |
|---|---|
| Project explainer | `context_brief.md` |
| Current snapshot | `rolling_summary.md` |
| Progress trail | `daily_logs/YYYY-MM-DD.md` |
| Safety rail | `config.json`, `state.json`, optional `update_protocol.md` |

```text
PROJECT_ROOT/
├── your-project-files...
└── .recallloom/                    # or recallloom/
    ├── context_brief.md
    ├── rolling_summary.md
    ├── daily_logs/
    ├── config.json
    ├── state.json
    ├── update_protocol.md          # optional
    └── companion/                  # appears only when needed
```

</details>

## 🚀 Quick Start

If you want to know whether RecallLoom is useful for you, the fastest test is simple:

1. Install it.
2. Attach it to a real project you know you will come back to.
3. Return later with a different session, model, or agent.

If that return moment feels noticeably easier, it is doing its job.

### Step 1: Install it

#### Option A: Fastest possible trial

If your environment supports an open Skills CLI such as [skills.sh](https://skills.sh/docs/cli), install directly:

```bash
npx skills add https://github.com/Frappucc1no/recall-loom --skill recallloom
```

#### Option B: Long-term use inside your existing AI tool

If your tool uses a directory-based skills setup, install the whole package directory into the appropriate skills folder:

```bash
cp -R /path/to/recall-loom/skills/recallloom /path/to/<skills-dir>/recallloom

# or
ln -s /absolute/path/to/recall-loom/skills/recallloom /path/to/<skills-dir>/recallloom
```

### Step 2: Attach it to a real project

If you are already inside the installed `recallloom/` package directory, or inside `skills/recallloom/` in a source checkout, run:

```bash
python3.13 scripts/init_context.py /absolute/path/to/project
python3.13 scripts/validate_context.py /absolute/path/to/project --json
```

If your environment does not use `python3.13`, replace it with any available Python `3.10+` interpreter.

When `validate_context.py` returns `"valid": true`, the project has been connected successfully.

### Step 3: Go back to your AI tool and speak naturally

You do not need to memorize special commands first. Start with prompts such as:

| You can say | Best used when |
|---|---|
| `continue this project` | The project already has continuity files and you want to keep moving. |
| `restore project context` | You want to restore context first and decide what to do next after that. |
| `pick up where we left off` | You are returning to the same work after a previous session. |
| `record today's progress` | You want to capture meaningful progress in the continuity files. |

## 📦 If You Want The Skill-Package View

Most people do not need the internal package shape on first read. When you do want the install and integration view, here it is:

<details>
  <summary><strong>See the package shape</strong></summary>

```text
recallloom/
├── SKILL.md
├── profiles/
├── references/
├── scripts/
├── package-metadata.json
└── ...
```

| Part | Role |
|---|---|
| `SKILL.md` | Agent-facing entrypoint and default workflow |
| `profiles/` | Guidance for different project shapes |
| `references/` | Protocol details, file contracts, and playbooks |
| `scripts/` | Helpers for init, validation, recovery, and guarded writes |
| `package-metadata.json` | Version and capability metadata |

</details>

<details>
  <summary><strong>See package facts and runtime assumptions</strong></summary>

### Package Facts

<!-- RecallLoom metadata sync start: package-metadata -->
- package version: `0.3.0`
- protocol version: `1.0`
- supported protocol versions:
  - `1.0`
<!-- RecallLoom metadata sync end: package-metadata -->

### Runtime Assumptions

<!-- RecallLoom metadata sync start: runtime-assumptions -->
- Python 3.10 or newer
- supported workspace languages:
  - `en`
  - `zh-CN`
- supported bridge targets:
  - `AGENTS.md`
  - `CLAUDE.md`
  - `GEMINI.md`
  - `.github/copilot-instructions.md`
<!-- RecallLoom metadata sync end: runtime-assumptions -->

</details>

<details>
  <summary><strong>See common install locations</strong></summary>

| Environment | Recommended setup | Best when |
|---|---|---|
| Skills CLI ecosystem | `npx skills add https://github.com/Frappucc1no/recall-loom --skill recallloom` | You want the fastest possible trial. |
| Codex | Install into `.agents/skills/recallloom` | You want project-level, long-running repository collaboration. |
| Claude Code | Install into `~/.claude/skills/recallloom` or `.claude/skills/recallloom` | You want user-level or project-level installation. |
| Other directory-based tools | Install the whole directory into that tool's skills folder | You want to reuse the same continuity files across tools. |

</details>

## ❓ FAQ

<details>
  <summary><strong>Will it automatically edit my project code?</strong></summary>
  <p>No. Its primary concern is the continuity layer itself, and formal writes are meant to happen through explicit triggers and safer update paths.</p>
</details>

<details>
  <summary><strong>Can I attach it to a project that is already in progress?</strong></summary>
  <p>Yes. That is one of the best use cases: add stable background, current state, and important progress to a project that is already moving so future sessions can continue more easily.</p>
</details>

<details>
  <summary><strong>Is it only for coding projects?</strong></summary>
  <p>No. It also works well for research writing, product document collaboration, software project coordination, and mixed long-running projects. If a project does not clearly fit a specialized mode, the general continuity path is the safest default.</p>
</details>

<details>
  <summary><strong>Do I need to maintain a lot of files every day?</strong></summary>
  <p>No. The goal is a minimum useful continuity set, not turning every session into documentation work. Only durable state that is actually worth keeping should be recorded.</p>
</details>

<details>
  <summary><strong>Do I have to commit to one specific AI tool?</strong></summary>
  <p>No. The whole idea is file-native continuity. As long as a tool can install this kind of skill package and read project files, it becomes much easier to carry the same project state across tools.</p>
</details>

## 🌟 Current Version Highlights

- **Query-oriented continuity recall**: `query_continuity.py` can return bounded, cited recall instead of forcing the next session to manually scan every continuity file.
- **Shared freshness and conflict surfacing**: `preflight`, `status`, and `query_continuity` now expose a more coherent read-side picture before writes or handoffs.
- **Safer attach-ready outputs**: read-side recall now stays bounded, surfaces project-local override review, and runs through the attached-text scan before return.
- **Workday recommendation**: Helps an agent judge which day of work is most appropriate to continue, reducing confusion across day boundaries.
- **Recovery proposals and review records**: Makes historical recovery clearer and easier to review collaboratively.
- **Brand and runtime alignment from `v0.2.2` remains the foundation**: the public brand, install path, and default continuity surface stay aligned on `RecallLoom`.

## 📚 Further Reading

- [SKILL.md](./skills/recallloom/SKILL.md)
- [USAGE.md](./USAGE.md)
- [profiles/](./skills/recallloom/profiles/)
- [file-contracts.md](./skills/recallloom/references/file-contracts.md)
- [protocol.md](./skills/recallloom/references/protocol.md)

## 📄 License

This project is released under Apache License 2.0. See [LICENSE](./LICENSE) and [NOTICE](./NOTICE) for details.
