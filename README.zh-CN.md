<div align="center">

<h1>🧶 RecallLoom</h1>

**一个长期项目，不该因为切模型、换智能体、跨会话，就一次次重新开始。**

[![Version](https://img.shields.io/badge/version-v0.3.0-111827)](./skills/recallloom/package-metadata.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](./skills/recallloom/package-metadata.json)

[English](./README.md) · **简体中文**

</div>

RecallLoom 是一个面向长期 AI 工作的可安装 continuity skill。把它接进一个真实项目之后，你就可以直接用自然语言继续推进，比如：`继续这个项目`、`恢复项目上下文`、`从上次停下的地方继续`。

它不是另一个管理面板，也不是被锁在某个平台里的私有记忆。RecallLoom 会把一小组真正重要的连续性信息留在工作区里，让下一次进入项目的人，无论是模型、智能体，还是协作者，都能从同一份项目现实继续，而不是重新从聊天记录里拼凑。

<!-- Suggested image slot: ./docs/images/readme-hero-system.png -->

## 💡 为什么需要 RecallLoom？

如果你已经在混用 `Claude Code`、`Codex`、`Gemini CLI`、`Qwen Code`，或者经常把工作交给新的会话，你大概率已经遇到过这些问题：

- 每换一个工具，都要重新解释一遍项目。
- 一旦换了新的智能体，项目之前为什么这样做，很容易断掉一截。
- 平台自带的记忆一离开原平台，就带不走了。
- 新协作者很难判断“现在到底什么是真的”。
- 项目一做久，历史讨论、半成品想法、当前结论就会越堆越乱。

真正拖慢长期 AI 工作的，很多时候不是模型不够强，而是 **项目连续性总在中断**。

RecallLoom 做的事情很直接：把项目自己的“连续性记忆”放回项目本身，而且就是普通文件、可审阅、可跟着项目一起移动。这样谁来接手，先恢复核心现实，再继续推进，而不是先花很久重建上下文。

## ✅ 一旦接入，你会立刻感受到什么

- **换模型时，不再像重新开始**：关键背景、当前状态、进展和下一步都已经跟着项目走。
- **新智能体更容易接手**：不用从旧聊天记录里猜今天到底什么才算准。
- **协作成本明显下降**：后来加入的人，不必先看完所有历史，才能知道项目进行到哪了。
- **“当前真相”终于能被看见**：现在成立的判断，不会再轻易埋进旧讨论里。
- **回来继续时会轻松很多**：更像是在续上项目，而不是在重建项目。

## 🆕 `v0.3.0` 这次真正交付了什么

`v0.3.0` 是 RecallLoom 的读侧强化版本。

它建立在 `v0.2.2` 已完成的品牌切换基础上，同时把三件事真正补稳：

- **可按 query 召回 continuity**：`query_continuity.py` 现在可以返回带 citations、confidence、freshness、conflict state 和有界 supporting context 的召回结果。
- **读侧基线真正统一**：`preflight`、`status`、`query_continuity` 现在共享 freshness 和 digest 原语，不再各说各话。
- **附着前的 recall 更安全**：读侧输出会显式 surface `update_protocol.md`，限制局部上下文窗口，并对返回文本面做 attached-text scan。

所以 `v0.3.0` 不再只是品牌与运行面统一后的下一小步，而是第一次把 RecallLoom 的 read-side recall layer 补到了真正可依赖的程度。

## 🧭 最容易理解它的方式

> 你可以把 RecallLoom 想成一本留在项目里的“项目工作手册”，而不是留在某个会话里的记忆。

这本手册会让四件事始终更容易恢复：

- **这个项目到底是什么**
- **现在什么是真的**
- **已经发生了哪些关键进展**
- **接下来最值得做什么**

你不需要先记住内部文件名，也不需要先理解底层规则。先抓住这个心智模型，就已经抓住它最重要的价值了。

## 🎯 更适合哪些长期工作

当一个项目需要跨天、跨会话、跨工具、跨模型或跨协作者继续时，RecallLoom 的价值会明显上升。

- **混用平台和模型的人**：每次切工具时，不再支付完整的“重启成本”。
- **同一项目里使用多个智能体的人**：即使不断有新会话进入，项目也不容易失去锚点。
- **研究与写作工作**：让来源、判断、进展和未决问题不容易散掉。
- **产品与文档协作**：让范围、决策和下一步行动更容易恢复。
- **软件项目协调**：让状态、阻塞项和实现方向在跨会话中保持可见。
- **混合型长期项目**：当项目同时包含写作、产品、代码和运营时，通用连续性路径通常是最安全的起点。

## 🧩 内置场景模式

RecallLoom 提供了 4 种内置模式，让同一套连续性思路可以适配不同项目形态。如果你暂时不确定，先从通用模式开始。

| 模式 | 最适合什么项目 | 它主要帮你稳住什么 |
|---|---|---|
| 通用模式 | 项目同时混合研究、写作、产品、代码或运营工作 | 整体项目现实，不会过早把项目理解窄了 |
| 研究写作模式 | 以来源、论点、证据和长文写作为主的工作 | 论点、证据和写作进展 |
| 产品文档模式 | 以 PRD、RFC、策略文档和利益相关者对齐为主的工作 | 范围、决策和待定问题 |
| 软件协调模式 | 以工程规划、仓库执行和实现推进为主的工作 | 状态、阻塞项和下一步行动 |

安装后，最常见的自然语言触发语包括：

- `继续这个项目`
- `恢复项目上下文`
- `从上次停下的地方继续`
- `记录今天的关键进展`

<!-- Suggested image slot: ./docs/images/readme-profile-strip.png -->

## ✨ 它为什么有用，但又不会变得很重

RecallLoom 的关键，不是“多记东西”，而是“把不同性质的项目现实拆开保存”，而不是混成一份越来越长的大笔记。

| 这本“项目手册”的部分 | 它帮下一次进入项目的人恢复什么 |
|---|---|
| 项目说明 | 这个项目是什么，应该怎么理解它 |
| 当前状态 | 现在什么是真的 |
| 进展轨迹 | 真正发生过什么，而不只是讨论过什么 |
| 安全护栏 | 什么时候该谨慎读，什么时候该谨慎写 |

所以，它不是要求新会话把所有历史全读一遍，而是先给它一个更小、更稳、更适合站住脚的起点。

<!-- Suggested image slot: ./docs/images/readme-architecture-map.png -->

<details>
  <summary><strong>查看底层文件对应关系</strong></summary>

| 通俗说法 | 底层对应 |
|---|---|
| 项目说明 | `context_brief.md` |
| 当前状态 | `rolling_summary.md` |
| 进展轨迹 | `daily_logs/YYYY-MM-DD.md` |
| 安全护栏 | `config.json`、`state.json`、可选 `update_protocol.md` |

```text
PROJECT_ROOT/
├── your-project-files...
└── .recallloom/                    # 或 recallloom/
    ├── context_brief.md
    ├── rolling_summary.md
    ├── daily_logs/
    ├── config.json
    ├── state.json
    ├── update_protocol.md          # 可选
    └── companion/                  # 只在需要时出现
```

</details>

## 🚀 快速开始

如果你只是想判断它对自己有没有用，最快的测试方式很简单：

1. 把它装上。
2. 接到一个你确定还会回来的真实项目里。
3. 隔一段时间，再用另一个会话、模型或智能体回来继续。

如果那个“回来继续”的瞬间明显轻松了，它就在发挥作用。

### 第一步：安装它

#### 方式 A：最快试用

如果你的环境支持 [skills.sh](https://skills.sh/docs/cli) 这类开放 Skills CLI，可以直接安装：

```bash
npx skills add https://github.com/Frappucc1no/recall-loom --skill recallloom
```

#### 方式 B：接入现有 AI 工具并长期使用

如果当前工具支持目录式技能包，就把整个包目录接入对应的技能目录：

```bash
cp -R /path/to/recall-loom/skills/recallloom /path/to/<skills-dir>/recallloom

# 或
ln -s /absolute/path/to/recall-loom/skills/recallloom /path/to/<skills-dir>/recallloom
```

### 第二步：接到真实项目里

如果你已经位于安装好的 `recallloom/` 包目录，或者源码仓库的 `skills/recallloom/` 目录，可以直接运行：

```bash
python3.13 scripts/init_context.py /absolute/path/to/project
python3.13 scripts/validate_context.py /absolute/path/to/project --json
```

如果你的环境不是 `python3.13`，替换成任意可用的 Python `3.10+` 即可。

当 `validate_context.py` 返回 `"valid": true` 时，说明项目已经接入成功。

### 第三步：回到 AI 工具里，直接自然触发

你不需要先记复杂命令，可以直接说：

| 你可以说 | 最适合什么时候 |
|---|---|
| `继续这个项目` | 项目已经有连续性文件，准备继续推进时 |
| `先帮我恢复项目上下文` | 想先恢复上下文，再决定下一步时 |
| `从上次停下的地方继续` | 跨会话回来继续同一项工作时 |
| `记录今天的关键进展` | 想把重要进展沉淀进连续性文件时 |

## 📦 如果你想看技能包结构

第一次阅读时，大多数人其实不需要关心内部包结构。等你想看安装和集成细节时，再看下面这部分即可：

<details>
  <summary><strong>查看包的基本形态</strong></summary>

```text
recallloom/
├── SKILL.md
├── profiles/
├── references/
├── scripts/
├── package-metadata.json
└── ...
```

| 组成部分 | 作用 |
|---|---|
| `SKILL.md` | 给 AI 工具读取的主入口文件 |
| `profiles/` | 面向不同项目形态的默认模式 |
| `references/` | 协议细节、文件契约和操作说明 |
| `scripts/` | 用于初始化、校验、恢复和护栏写入的辅助脚本 |
| `package-metadata.json` | 版本与能力元信息 |

</details>

<details>
  <summary><strong>查看版本信息与运行前提</strong></summary>

### 版本信息

- 包版本：`0.3.0`
- 协议版本：`1.0`
- 当前支持的协议版本：
  - `1.0`

### 运行前提

- Python 版本要求：`3.10` 及以上
- 支持的工作区语言：
  - `en`
  - `zh-CN`
- 支持的入口桥接文件：
  - `AGENTS.md`
  - `CLAUDE.md`
  - `GEMINI.md`
  - `.github/copilot-instructions.md`

</details>

<details>
  <summary><strong>查看常见安装位置</strong></summary>

| 环境 | 推荐接法 | 最适合什么时候 |
|---|---|---|
| Skills CLI 生态 | `npx skills add https://github.com/Frappucc1no/recall-loom --skill recallloom` | 想最快开始试的人 |
| Codex | 接入 `.agents/skills/recallloom` | 想在仓库内做项目级长期协作 |
| Claude Code | 接入 `~/.claude/skills/recallloom` 或 `.claude/skills/recallloom` | 想做用户级或项目级安装 |
| 其他目录式工具 | 把整个目录接入该工具的技能文件夹 | 想跨工具复用同一套连续性文件 |

</details>

## ❓ FAQ

<details>
  <summary><strong>它会自动改我的项目代码吗？</strong></summary>
  <p>不会。它的主要关注点是连续性层本身；正式写入应该通过明确触发和更安全的更新路径发生。</p>
</details>

<details>
  <summary><strong>我可以把它接到一个已经在推进中的项目里吗？</strong></summary>
  <p>可以。这恰恰是它最适合的场景之一：把稳定背景、当前状态和关键进展补进一个已经在跑的项目里，让后续会话更容易继续。</p>
</details>

<details>
  <summary><strong>它只适合编程项目吗？</strong></summary>
  <p>不是。它同样适合研究写作、产品文档协作、软件项目协调，以及混合型长期项目。如果暂时不明显属于某个专用模式，通用连续性路径就是最稳妥的默认选择。</p>
</details>

<details>
  <summary><strong>我是不是每天都要维护很多文件？</strong></summary>
  <p>不需要。它强调的是最小必要连续性集合，而不是把每次会话都变成文档劳动。只有真正长期有价值的状态才值得留下。</p>
</details>

<details>
  <summary><strong>我必须绑定某个 AI 工具吗？</strong></summary>
  <p>不需要。它的核心思路就是文件原生连续性。只要工具能安装这类技能包并读取项目文件，同一套项目状态就更容易跨工具延续。</p>
</details>

## 🌟 当前版本亮点

- **query 导向的 continuity 召回**：`query_continuity.py` 可以返回有界、可引用的召回结果，而不是让下一次会话手工翻所有 continuity 文件。
- **读侧 freshness / conflict 更一致**：`preflight`、`status`、`query_continuity` 现在能给出更统一的读侧判断。
- **附着前输出更安全**：read-side recall 现在会限制上下文窗口、surface project-local override review，并在返回前做 attached-text scan。
- **工作日推荐**：帮助智能体判断更适合继续哪一天的工作，减少跨天续写时的混乱。
- **恢复提案与审阅记录**：让历史恢复过程更清楚，也更适合团队协作与人工把关。
- **`v0.2.2` 建立的品牌与运行面统一，仍然是基础**：公共品牌、安装路径和默认连续性表面继续统一指向 `RecallLoom`。

## 📚 延伸阅读

- [SKILL.md](./skills/recallloom/SKILL.md)
- [USAGE.md](./USAGE.md)
- [profiles/](./skills/recallloom/profiles/)
- [file-contracts.md](./skills/recallloom/references/file-contracts.md)
- [protocol.md](./skills/recallloom/references/protocol.md)

## 📄 开源协议

本项目基于 Apache License 2.0 协议开源。详见 [LICENSE](./LICENSE) 与 [NOTICE](./NOTICE)。
