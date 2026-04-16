# 🧶 ContextWeave

<div align="center">

**为长周期 AI 项目打造的文件原生“连续性记忆”层。**

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Protocol Version](https://img.shields.io/badge/protocol-1.0-0f766e)](./package-metadata.json)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](./package-metadata.json)

[English](./README.md) · **简体中文**

</div>

## 💡 为什么需要 ContextWeave？

在深度 Vibe Coding、长期研究写作，或多 Agent 协作的项目里，最大的摩擦往往不是模型能力不够，而是 **同一个项目一旦跨 Session 继续，关键上下文就开始漂移**。

ContextWeave 不把连续性建立在单一聊天窗口，也不把项目真相托付给某个平台的私有黑盒 memory。它把一组轻量、显式、可审阅的连续性文件放回项目工作区本身，让后续会话可以更快回答四个核心问题：

<table>
  <tr>
    <td width="50%"><strong>🎯 项目愿景</strong><br/>这个项目到底是什么？</td>
    <td width="50%"><strong>📍 当前真相</strong><br/>此时此刻，哪些事实是成立的？</td>
  </tr>
  <tr>
    <td><strong>🧗 历史进展</strong><br/>已经完成了哪些关键里程碑？</td>
    <td><strong>🚀 下一步行动</strong><br/>接下来最值得聚焦的是什么？</td>
  </tr>
</table>

## ✨ ContextWeave 的核心方式

| 方式 | 读者能直接感受到什么 |
|---|---|
| **🛡️ 文件原生** | 连续性状态以普通 Markdown 和 JSON 落在工作区里，易于审阅、版本管理、迁移和恢复。 |
| **⚡ 节制的冷启动** | 不是把全部历史一股脑塞给模型，而是优先读取最小连续性集合，再按任务需要扩展上下文。 |
| **🧠 分层保存信息** | 稳定背景、当前状态、机器可读控制信息、历史里程碑分别存放，降低状态漂移。 |
| **🔒 推荐优先** | 会给出恢复、工作日判断、下一步 review 建议，但不会在没有审阅的前提下偷偷改写项目状态。 |
| **🧪 写入护栏内建** | 在需要正式写入时，会通过锁和校验机制帮助降低误写、乱写项目状态的风险。 |
| **📅 恢复与接续更完整** | 支持工作日推荐、恢复提案与审阅记录，帮助长期项目更稳地继续推进。 |

## 🗺️ 先把它理解成什么

第一次接触 ContextWeave 时，可以先不要记一堆内部术语。更容易理解的方式是：

> 它像是给一个长期项目准备的一本“可持续续写的项目工作手册”。

这本手册里，最重要的不是花哨功能，而是四件事：

<table>
  <tr>
    <td width="50%"><strong>一页说明</strong><br/>让 AI 知道“这个项目到底是什么”</td>
    <td width="50%"><strong>一页状态</strong><br/>让 AI 知道“现在什么是真的”</td>
  </tr>
  <tr>
    <td><strong>一组进展记录</strong><br/>让 AI 知道“哪些关键事情真的发生过”</td>
    <td><strong>一层读写护栏</strong><br/>让 AI 知道“应该怎么读、什么时候该谨慎写”</td>
  </tr>
</table>

```mermaid
flowchart TB
    A["一个会持续很多天的 AI 项目"] --> B["项目说明\n帮助 AI 快速理解项目"]
    A --> C["当前状态\n帮助 AI 对齐最新事实"]
    A --> D["进展记录\n帮助 AI 知道已经完成了什么"]
    A --> E["读写护栏\n帮助 AI 不乱读、不乱写"]
```

## 🧱 架构怎么分层

如果把它拆开来看，ContextWeave 本质上是在解决四个不同的问题：

```mermaid
flowchart TD
    L1["第一层：项目说明层\n回答：这是什么项目？"] --> L2["第二层：当前状态层\n回答：现在什么是真的？"]
    L2 --> L3["第三层：进展记录层\n回答：哪些关键事情已经发生？"]
    L3 --> L4["辅助层：控制与安全层\n回答：应该怎么读、怎么安全写？"]
```

| 层次 | 它回答的问题 | 读者会直接得到什么 |
|---|---|---|
| 项目说明层 | 这是什么项目？ | 新会话不需要重新追问背景 |
| 当前状态层 | 现在什么是真的？ | 更容易快速对齐最新事实 |
| 进展记录层 | 哪些关键事情已经发生？ | 更容易区分完成事项和讨论痕迹 |
| 控制与安全层 | 应该怎么读、怎么安全写？ | 恢复更稳，正式写入更谨慎 |

### 1. 项目说明层

这一层负责保存那些 **不会频繁变化，但又会不断影响后续判断** 的内容，例如项目目标、当前阶段、边界、约束和关键依据。

它解决的是：新会话接进来时，AI 不需要重新问一遍“我们到底在做什么”。

### 2. 当前状态层

这一层负责保存 **此时此刻最应该相信的当前判断**，例如当前成立的事实、当前风险、尚未解决的问题和下一步焦点。

它解决的是：AI 不需要在一堆历史对话里猜“现在最新状态到底是什么”。

### 3. 进展记录层

这一层负责保存 **真正发生过的关键进展**，而不是一闪而过的讨论痕迹。它更像项目的里程碑轨迹，而不是聊天记录备份。

它解决的是：AI 能分清“这是已经完成的事实”，还是“这只是之前讨论过的想法”。

### 4. 控制与安全层

这一层不是给人直接阅读的主内容，而是给工具和辅助脚本用来保证秩序的。它主要会帮助 Agent 做这四件事：

| 它会帮忙判断什么 | 带来的效果 |
|---|---|
| 应该先读哪些内容 | 避免一上来把所有历史全读一遍 |
| 当前上下文是否足够新鲜 | 降低基于旧状态继续工作的风险 |
| 什么时候需要先 review 再写 | 让正式更新更稳妥 |
| 正式写入时怎样更谨慎 | 降低把项目状态写乱的概率 |

## 🗂️ 这些概念在文件里怎么落地

上面的四层，是给第一次接触者理解用的概念模型。它们在实际文件中的对应关系如下：

```mermaid
flowchart LR
    A["项目说明层"] --> A1["context_brief.md"]
    B["当前状态层"] --> B1["rolling_summary.md"]
    C["进展记录层"] --> C1["daily_logs/YYYY-MM-DD.md"]
    D["控制与安全层"] --> D1["config.json / state.json / update_protocol.md"]
```

| 实际文件 | 作用 |
|---|---|
| `context_brief.md` | 保存项目的稳定背景和长期框架 |
| `rolling_summary.md` | 保存当前最应该对齐的状态快照 |
| `daily_logs/YYYY-MM-DD.md` | 按日期沉淀重要进展与里程碑证据 |
| `config.json`、`state.json`、`update_protocol.md` | 帮助工具按顺序读取、谨慎写入，而不是让状态越写越乱 |

此外，ContextWeave 还提供了一块克制的伴生空间，主要用于承接 **恢复提案与审阅记录**。它的作用，是把这些中间材料和核心项目真相隔开，让恢复过程更清楚、更可审阅。

### 一眼看懂：项目里会留下什么

默认情况下，ContextWeave 会在项目里维护一小组连续性文件，而不是铺开一大堆零散缓存。

```text
PROJECT_ROOT/
├── your-project-files...
└── .contextweave/                  # 或 contextweave/
    ├── config.json
    ├── state.json
    ├── context_brief.md
    ├── rolling_summary.md
    ├── update_protocol.md         # 可选
    ├── daily_logs/
    │   └── YYYY-MM-DD.md
    └── companion/                 # 只在需要时出现
        └── recovery/
            ├── proposals/
            ├── review_log/
            └── archive/
```

可以把它理解成这样：

| 文件或目录 | 更容易理解的说法 |
|---|---|
| `context_brief.md` | 项目说明书，告诉 AI 这是什么项目。 |
| `rolling_summary.md` | 当前工作台，告诉 AI 现在什么是真的、下一步做什么。 |
| `daily_logs/` | 进展记录，告诉 AI 哪些关键事情已经真正发生过。 |
| `config.json` 与 `state.json` | 底层配置和状态，让工具读写更稳定。 |
| `companion/` | 恢复提案和审阅记录的独立区域，避免和核心项目真相混在一起。 |

如果你只是正常接入并持续使用，项目里看到的核心资产通常就是这一小组文件。

## 🔄 一个新会话是怎么接入项目的

ContextWeave 的重点，不是“把所有历史都读一遍”，而是“先读最小必要信息，再决定要不要展开”。

```mermaid
flowchart LR
    A["新会话进入项目"] --> B["先读最小连续性集合"]
    B --> C["判断当前状态是否仍然可信"]
    C --> D["只有需要时才展开更多历史"]
    D --> E["先给建议，再决定是否正式写入"]
```

这也是它为什么能同时做到两件事：

| 好处 | 结果 |
|---|---|
| 冷启动更快 | 新会话能更快进入状态 |
| 后续写入更谨慎 | 正式更新时更不容易写偏 |

## 🏁 快速开始

### 推荐方式：支持 Skills CLI 的环境

如果当前环境支持 [skills.sh](https://skills.sh/docs/cli) 这类开放 Skills CLI，可以直接安装：

```bash
npx skills add https://github.com/Frappucc1no/contextweave
```

### 通用方式：目录式接入

如果当前工具采用目录式 skills，直接把整个仓库目录接入对应的 skills 目录即可。不要只复制 `SKILL.md`。

```bash
cp -R /path/to/contextweave /path/to/<skills-dir>/contextweave

# 或
ln -s /absolute/path/to/contextweave /path/to/<skills-dir>/contextweave
```

### 支持环境

| 环境 | 如何接入 | 适合谁 |
|---|---|---|
| Skills CLI 生态 | `npx skills add https://github.com/Frappucc1no/contextweave` | 想用最直接方式安装的人 |
| Codex | 接入 `.agents/skills/contextweave` | 在项目内长期协作、需要项目级技能的人 |
| Claude Code | 接入 `~/.claude/skills/contextweave` 或 `.claude/skills/contextweave` | 想做用户级或项目级接入的人 |
| 其他支持目录式 Skills 的工具 | 将整个目录接入该工具的 skills 目录 | 需要跨工具复用同一套连续性能力的人 |

### 安装后的第一分钟

安装好包之后，最值得先做的是：给一个真实项目建立连续性目录，并确认它已经可用。

**第 1 步：初始化项目**

如果你已经在安装好的 `contextweave/` 包目录里，可以直接运行：

```bash
python3.13 scripts/init_context.py /absolute/path/to/project
python3.13 scripts/validate_context.py /absolute/path/to/project --json
```

**第 2 步：确认接入成功**

如果你的环境不是 `python3.13`，替换为任意可用的 Python `3.10+` 即可。

> 当 `validate_context.py` 返回 `"valid": true` 后，这个项目就已经接入完成。

**第 3 步：回到 AI 工具里开始使用**

接下来直接用自然语言开始即可，例如：

| 你可以直接说 | 适合什么时候用 |
|---|---|
| `continue this project` | 已经有连续性文件，准备继续推进时 |
| `restore project context` | 想先恢复上下文、再决定下一步时 |
| `pick up where we left off` | 跨会话回来继续同一个任务时 |
| `record today's progress` | 想把今天的重要进展沉淀下来时 |

<details>
  <summary><strong>查看 Codex 项目级接入示例</strong></summary>

```bash
mkdir -p .agents/skills
ln -s /absolute/path/to/contextweave .agents/skills/contextweave
```

</details>

<details>
  <summary><strong>查看 Claude Code 用户级接入示例</strong></summary>

```bash
mkdir -p ~/.claude/skills/contextweave
rsync -a /absolute/path/to/contextweave/ ~/.claude/skills/contextweave/
```

</details>

## ❓ FAQ

<details>
  <summary><strong>它会不会自动改我的项目代码？</strong></summary>
  <p>不会把你的业务代码当成默认目标去静默接管。它主要围绕连续性文件工作；当需要正式写入时，也会强调明确触发、先判断、再落盘。</p>
</details>

<details>
  <summary><strong>我已经有一个进行中的项目了，还能中途接入吗？</strong></summary>
  <p>可以。这正是它很适合的场景之一：把一个已经推进中的项目整理出稳定背景、当前状态和关键进展，让后续会话更容易继续。</p>
</details>

<details>
  <summary><strong>它只适合编程项目吗？</strong></summary>
  <p>不是。它同样适合研究写作、产品文档协作、软件项目协调这类会持续推进、需要跨会话保持一致理解的工作。</p>
</details>

<details>
  <summary><strong>我是不是每天都要维护很多文件？</strong></summary>
  <p>不需要。它强调的是最小必要连续性集合，而不是把每次对话都变成文档劳动。真正长期有价值的状态，才值得留下。</p>
</details>

<details>
  <summary><strong>它会在项目里留下很多东西吗？</strong></summary>
  <p>通常不会。核心就是一小组连续性文件，再加上按日期组织的进展记录。恢复提案、审阅记录这类材料也会被单独隔离，避免把项目目录弄乱。</p>
</details>

<details>
  <summary><strong>我必须绑定某个 AI 工具才能使用吗？</strong></summary>
  <p>不需要。ContextWeave 的思路本身是文件原生的。只要工具支持安装这类技能包，并能读取项目文件，它就更容易跨工具延续同一个项目状态。</p>
</details>

## 🌟 当前版本亮点

| 亮点 | 对读者意味着什么 |
|---|---|
| 工作日推荐 | 帮助 Agent 判断更适合继续哪一天的工作，减少跨天续写时的混乱。 |
| 恢复提案与审阅记录 | 让历史恢复过程更清楚，也更适合团队协作与人工把关。 |
| 更稳的冷启动 | 优先读取最小必要信息，让新会话更快进入状态。 |
| 更清晰的文件资产管理 | 让连续性文件、恢复材料和辅助记录各归其位，保持项目结构整洁。 |
| 更可靠的正式写入保护 | 在需要落盘时提供更谨慎的护栏，降低把项目状态写乱的风险。 |

## 📚 进阶阅读与核心规范

当你的项目接入 ContextWeave 后，如果你想深入了解它的读写契约或参与二次开发，请查阅以下核心文档：

| 文档 | 适合什么时候读 |
|---|---|
| 🤖 [**SKILL.md**](./SKILL.md) | 想看 Agent 如何把 ContextWeave 当成交互入口来使用时。 |
| 📖 [**USAGE.md**](./USAGE.md) | 想查看辅助运行时怎么用、什么时候需要人工介入时。 |
| 📜 [**references/protocol.md**](./references/protocol.md) | 想深入理解连续性模型本身时。 |
| 🔐 [**references/file-contracts.md**](./references/file-contracts.md) | 想确认什么样的状态更新才算合法、可接受时。 |

## 📄 开源协议

本项目基于 Apache License 2.0 协议开源。详见 [LICENSE](./LICENSE) 与 [NOTICE](./NOTICE)。
