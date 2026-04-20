<div align="center">

<h1>🧶 RecallLoom</h1>

**让项目自己记住自己。**

**为跨智能体、跨会话、跨模型持续推进的项目准备的连续性层。**

[![Version](https://img.shields.io/badge/version-v0.3.1-111827)](./skills/recallloom/package-metadata.json)
[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](./skills/recallloom/package-metadata.json)

[English](./README.md) · **简体中文**

</div>

![RecallLoom 顶部横幅](./docs/images/readme-topbanner.png)

如果你每次切到新的 `Claude Code`、`Codex`、`Gemini CLI` 或新的智能体，都要先花十分钟重新解释项目，那你真正缺的往往不是更聪明的模型，而是一个不会丢的 **项目连续性层**。

RecallLoom 把项目为什么存在、现在什么是真的、最近推进到哪里、下一步该怎么接上，留在项目本身，而不是锁在某个平台的私有记忆里。它不是另一个后台，不是平台私有记忆，也不是全仓静默理解器；它更像给长期项目加了一层稳定的“项目真相层”，让下一个会话能直接接上。

**快速跳转：** [它解决什么问题](#problem) · [谁最适合使用](#fit) · [快速开始](#quick-start) · [内置场景模式](#modes) · [FAQ](#faq)

<a id="problem"></a>
## 💥 它解决什么问题

如果你已经在混用不同工具、模型和会话，这些问题应该很熟：

- 每换一个工具，就要再付一遍“重启税”。
- 新会话知道仓库里“有什么”，却不知道“为什么会变成这样”。
- 新智能体进来时，很难判断“现在到底什么是真的”。
- 项目一做久，历史讨论和当前结论就很容易混在一起。

真正拖慢长期 AI 工作的，很多时候不是模型不够强，而是 **项目连续性总在中断**。

RecallLoom 做的事情很克制：它不试图凭空理解一切，而是把你已经沉淀出来、而且确实值得长期保留的项目现实留在工作区里。

![会话碎片如何重新变成可继续的项目](./docs/images/readme-continuity-story.png)

## 🧭 它怎么工作

最容易理解 RecallLoom 的方式，是把它看成一套留在项目里的“小而清楚的连续性结构”。它不把所有历史都堆成一团，而是把最该长期保留的项目现实拆成 4 个部分：

- **项目背景**：这个项目是什么，为什么会这样做。
- **当前状态**：现在进行到哪，哪些判断仍然有效。
- **关键进展**：最近真正发生了什么，哪些决定值得回看。
- **规则与边界**：哪些地方要谨慎读，哪些地方不能随便改。

新会话不需要先吞下全部历史。它更需要先恢复这 4 层项目现实，再决定下一步怎么接上。

![RecallLoom 的四层连续性结构](./docs/images/readme-philosophy-layers.png)

<a id="fit"></a>
## 🎯 谁会立刻觉得它值

如果你属于下面这些人，RecallLoom 通常会很快让你感觉“省事了”：

- **已经习惯让 AI 参与真实项目的人**：尤其是个人开发者和超小团队，会反复把同一个项目交给不同会话、不同模型、不同智能体继续推进。
- **经常在 `Claude Code`、`Codex`、`Gemini CLI` 等工具之间切换的人**：不想每换一次工具就重讲一遍项目。
- **研究写作、产品文档、软件项目协调**：这些工作都特别依赖 why、决策、进展和下一步不要漂掉。

典型高价值场景也很集中：

- **跨天回来继续**：隔了一天、一周、甚至更久，再次进入项目时，不必先靠聊天记录重建世界。
- **跨模型或跨智能体接力**：今天用 Claude，明天换 Codex、Gemini CLI 或另一个智能体，项目状态不会跟着丢。
- **长期研究 / PRD / 软件协调**：最怕“当前真相”和“历史脉络”被冲散的工作。

如果你只是一次性问答、临时聊天，或者根本不会回到同一个项目，RecallLoom 对你的价值就不会那么强。

<a id="modes"></a>
## 🧩 内置场景模式

如果你已经确认自己适合这类产品，再来看模式选择会更自然；如果暂时拿不准，先用通用模式通常最稳。

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

![四种内置模式分别适合什么项目](./docs/images/readme-profile-strip.png)

## ✨ 它为什么有用，但又不会变得很重

RecallLoom 的关键，不是“多记东西”，而是只把真正长期有价值的项目现实拆开保存，而不是混成一份越来越长的大笔记。

| 这本“项目手册”的部分 | 它帮下一次进入项目的人恢复什么 |
|---|---|
| 项目背景 | 这个项目是什么，应该怎么理解它 |
| 当前状态 | 现在什么是真的 |
| 关键进展 | 真正发生过什么，而不只是讨论过什么 |
| 规则与边界 | 什么时候该谨慎读，什么时候该谨慎写 |

所以，它不是要求新会话把所有历史全读一遍，而是先给它一个更小、更稳、更适合站住脚的起点。

![连续性结构如何落到项目文件里](./docs/images/readme-handbook-map.png)

## 🧱 这些选择是故意的

- **不污染项目主体**：连续性状态放在 sidecar，而不是硬塞进你原本的代码、文档和目录里。
- **不假装全懂整个仓库**：它聚焦恢复项目背景、当前状态、关键进展和边界，而不是冒充全仓理解器。
- **先追求可信，再追求自动**：它宁可把项目现实讲清楚，也不愿意先做一个看起来很聪明、但边界含糊的黑盒系统。

<details>
  <summary><strong>查看它在项目里是怎么落地的</strong></summary>

| 更好懂的叫法 | 项目里的对应文件 |
|---|---|
| 项目背景 | `context_brief.md` |
| 当前状态 | `rolling_summary.md` |
| 关键进展 | `daily_logs/YYYY-MM-DD.md` |
| 规则与边界 | `config.json`、`state.json`、可选 `update_protocol.md` |

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

<a id="quick-start"></a>
## 🚀 快速开始

第一次接入，其实只要记住一个动作：`rl-init`。剩下的流程按这 4 步走就够了：

1. 把技能包安装到本机
2. 第一次在对话里明确唤起 RecallLoom
3. 如果项目还没接入，就确认初始化，或直接输入 `rl-init`
4. 然后正常推进项目

### 第一步：安装

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

### 第二步：第一次显式唤起 RecallLoom

第一次使用时，先在对话里明确叫醒 RecallLoom。

不同宿主表面语法不同，但动作意图是一样的：

- 通过宿主的技能选择器找到 `recallloom`
- 或用 `@recallloom`
- 或用宿主提供的 `/skill` 选择 RecallLoom
- 或直接明确说：`请用 RecallLoom 接管这个项目`

这一步的重点只有一个：让 agent 先判断当前项目是不是已经接入 RecallLoom。

- 如果已经接入，就直接继续
- 如果还没接入，就进入初始化确认

### 第三步：用户确认，或直接输入 `rl-init`

对用户来说，真正需要记住的统一动作只有一个：

- `rl-init`

如果 agent 判断当前项目还没初始化，它应该先询问你是否要初始化。你可以：

- 直接确认
- 或直接输入：`rl-init`

这时它应执行标准初始化动作：

- 初始化 sidecar
- 校验结构
- 返回下一步建议

### 第四步：正常推进项目

初始化完成后，你就可以像平时一样继续项目。RecallLoom 此时更像一个低摩擦的连续性层：

- 在需要的时候被唤起
- 在继续项目、恢复上下文、记录关键进展时发挥作用
- 尽量减少额外操作负担

后续常见说法例如：

| 你可以说 | 最适合什么时候 |
|---|---|
| `继续这个项目` | 项目已经有连续性文件，准备继续推进时 |
| `先帮我恢复项目上下文` | 想先恢复上下文，再决定下一步时 |
| `从上次停下的地方继续` | 跨会话回来继续同一项工作时 |
| `记录今天的关键进展` | 想把重要进展沉淀进连续性文件时 |

如果你之后确实想把 `rl-init` 映射成宿主里的本地命令，可以把它理解成可选增强；当前最推荐的主路径，仍然是先按对话式流程使用 RecallLoom。

如果你想直接看底层脚本入口和操作流，而不是按对话式流程使用，可以看 [USAGE.md](./USAGE.md)。

## 📦 如果你想看技能包结构

第一次阅读时，大多数人其实可以先跳过这一段。等你真的需要看安装和集成细节时，再回来看下面这部分即可：

<details>
  <summary><strong>查看包的基本形态</strong></summary>

```text
recallloom/
├── SKILL.md
├── profiles/
├── references/
├── scripts/
├── native_commands/
├── package-metadata.json
└── ...
```

| 组成部分 | 作用 |
|---|---|
| `SKILL.md` | 给 AI 工具读取的主入口文件 |
| `profiles/` | 面向不同项目形态的默认模式 |
| `references/` | 协议细节、文件契约和操作说明 |
| `scripts/` | 用于统一入口、初始化、校验、状态、bridge 和护栏写入的辅助脚本 |
| `native_commands/` | 面向支持宿主的可选原生命令模板 |
| `package-metadata.json` | 版本与能力元信息 |

</details>

<details>
  <summary><strong>查看版本信息与运行前提</strong></summary>

### 版本信息

- 包版本：`0.3.1`
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

<a id="faq"></a>
## ❓ FAQ

<details>
  <summary><strong>它会自动改我的项目代码吗？</strong></summary>
  <p>不会。它的主要关注点是连续性层本身；正式写入应该通过明确触发和更安全的更新路径发生。</p>
</details>

<details>
  <summary><strong>如果几乎没有聊天记录或项目沉淀，它也能自动读懂整个项目吗？</strong></summary>
  <p>不能这样理解。RecallLoom 不是零上下文的全仓扫描理解器。它最擅长的是把你已经沉淀出来的项目背景、当前状态、关键进展和规则边界稳定保留下来，让下一个会话更容易接上；如果项目本身几乎没有留下这些信号，它当然也不可能凭空补出完整现实。</p>
</details>

<details>
  <summary><strong>它会一直在后台静默运行吗？</strong></summary>
  <p>当前不应这样理解。更准确地说，它现在更适合在关键节点介入，例如“继续这个项目”“恢复项目上下文”“记录今天的关键进展”。这并不意味着你要全天候手动管理它，而是说在准备交接、结束一天工作、或刚完成关键决策时，让它介入会特别有价值。</p>
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
  <p>不需要绑定单一平台。RecallLoom 的核心是文件原生连续性；当前最直接支持的桥接入口包括 `AGENTS.md`、`CLAUDE.md`、`GEMINI.md` 和 `.github/copilot-instructions.md`，因此它更适合被接进可读技能包和项目文件的工具，而不是被锁在某一个平台私有 memory 里。</p>
</details>

<details>
  <summary><strong>为什么要用 sidecar，而不是直接写进项目正文里？</strong></summary>
  <p>因为这是一个故意的设计选择。sidecar 能把连续性状态留在项目旁边，又尽量不污染你原本的代码、文档和目录结构。这样它既能跟着项目走，又不会强行侵入项目主体。</p>
</details>

## 📚 延伸阅读

- [SKILL.md](./skills/recallloom/SKILL.md)
- [USAGE.md](./USAGE.md)
- [profiles/](./skills/recallloom/profiles/)
- [file-contracts.md](./skills/recallloom/references/file-contracts.md)
- [protocol.md](./skills/recallloom/references/protocol.md)

## 📄 开源协议

本项目基于 Apache License 2.0 协议开源。详见 [LICENSE](./LICENSE) 与 [NOTICE](./NOTICE)。
