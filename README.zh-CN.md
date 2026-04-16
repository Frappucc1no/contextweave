# ContextWeave

> 面向长周期 AI 项目的文件原生连续性层。

`ContextWeave` 用一组可审阅、可恢复、可复用的项目文件，把项目中真正重要的状态固定下来，让同一个项目在跨会话、跨工具、跨 agent 继续时不必反复从头对齐。

[English](./README.md) · 简体中文

[![License: Apache-2.0](https://img.shields.io/badge/license-Apache%202.0-blue.svg)](./LICENSE)
[![Protocol Version](https://img.shields.io/badge/protocol-1.0-0f766e)](./package-metadata.json)
[![Python](https://img.shields.io/badge/python-3.10%2B-3776AB)](./package-metadata.json)

## 它是什么

`ContextWeave` 适合那些会持续推进的项目。

它不把连续性建立在单一聊天窗口或单一平台私有 memory 上，而是把项目里真正重要的状态落在工作区本身。

这套状态设计出来，就是为了在项目继续时，快速回答四个实际问题：

- 这个项目是什么？
- 现在什么是真的？
- 已经发生过哪些重要进展？
- 接下来最值得做什么？

## 当前版本新增了什么

当前 `0.2.0` 版本是在原 `0.1.0` 连续性模型上做安全外延，而不是替换原模型。

升级方向包括：

- 更安全的冷启动
- 更小的默认读取集合
- 更清晰的连续性可信度
- recommendation-first 的工作日判断
- 通过“恢复提案”实现的历史辅助恢复
- 落在 sidecar 内部的最小 companion 命名空间

这条 `0.2.0` 版本线是刻意克制的：

- **不会** 引入第二个 storage root
- **不会** 静默自动改写项目状态
- **不会** 交付可执行 `/cw-*` 命令
- **不会** 让 companion 数据取代 core truth files

## 产品模型

当前模型有三层。

### 1. Core continuity

这是项目的正式真相层。

- `context_brief.md`
- `rolling_summary.md`
- `daily_logs/YYYY-MM-DD.md`

### 2. Ambient continuity

这是“读取并判断”的连续性层。

它帮助 session：

- 发现当前项目已经启用了 ContextWeave
- 先读取最小必要的连续性集合
- 判断当前连续性是否仍可信
- 给出下一步建议动作

### 3. Minimal companion foundation

这是围绕 core 的最小工作流层。

当前它主要用来：

- 承接恢复提案
- 承接审阅记录
- 把这些中间工件留在 sidecar 里，但不污染 core truth files

它当前**不等于**：

- 完整任务系统
- 完整 inbox 系统
- 命令运行时

## 它做得好的事情

- 把稳定 framing 和当前状态拆开
- 把当前状态和里程碑证据拆开
- 给后续 session 一个真实的连续性表面
- 让项目连续性留在可审计的工作区文件里
- 降低跨会话、跨工具、跨 agent 的理解漂移
- 对正式写入增加安全门禁

## 它不试图做什么

`ContextWeave` 不是：

- 通用 memory server
- 平台原生 memory 的全面替代品
- 重型 autonomous agent framework
- 完整任务管理产品
- 静默自动文档机

它的目标更窄，也更清楚：

> 只把正确的项目状态稳定留下来，并让后续 session 能安全地继续。

## 安全性与兼容性

当前 `0.2.0` 版本被设计成建立在 `0.1.0` 之上的安全适配升级，而不是重建式升级。

这意味着：

- 健康的 `0.1.0` 工作区应该继续可用
- 新 sidecar 资产保持 optional
- `companion/` 只应在真正使用 companion 能力时出现
- 旧项目不应该被强行要求重建 sidecar 才能继续工作

如果你要从 `0.1.0` 升级，建议先看：

- 完整源代码仓库中的 `2026-04-16-contextweave-0.1.0-to-v0.2.0-migration-and-rollback-note.md`

## Core 文件模型

storage root 仍然只能是：

- `PROJECT_ROOT/.contextweave/`
- `PROJECT_ROOT/contextweave/`

其中的 core continuity 资产保持为：

- `config.json`
- `state.json`
- `context_brief.md`
- `rolling_summary.md`
- `daily_logs/`
- `update_protocol.md`

当前 `0.2.0` 版本还额外承认一个 optional managed namespace：

- `STORAGE_ROOT/companion/`

当前预期子树：

- `STORAGE_ROOT/companion/recovery/`

这里用于存放：

- recovery proposals
- review records
- archived recovery artifacts

它不是任意 scratch 文件夹。

## 受管资产注册表

当前包还额外包含：

- `managed-assets.json`

这个文件是包级的受管资产声明源，用来定义：

- 必需 managed files
- optional managed files
- 必需 managed directories
- managed directories
- 支持的动态文件模式
- optional managed namespaces

这能让 helper 的行为和 validator 规则在 sidecar 继续演进时保持一致。

## 冷启动行为

当前冷启动方向是：

1. 找到项目根
2. 先读取最小连续性集合
3. 只有任务真的需要时才扩展读取
4. 正式写入前再做 freshness 判断
5. 先恢复和建议，再决定是否执行

在实践中，这意味着：

- 先从 `config.json`、`state.json`、`rolling_summary.md` 开始
- `update_protocol.md` 只在本地规则真的重要时再进入
- `context_brief.md` 只在 framing 不够时再读取
- latest active daily log 只在里程碑证据或工作日判断需要时再读取

最重要的行为约束是：

> 恢复上下文不等于自动继续执行未完成事项。

## 工作日 recommendation

当前 `0.2.0` 版本还加入了 recommendation-first 的工作日判断层。

它帮助回答：

- 当前应该继续哪个 active day？
- 当前是否应该开启新 active day？
- 上一个 active day 是否看起来还没收尾？
- 当前日志日期默认更适合 yesterday 还是 today？

它只做 recommendation。

它**不会**静默：

- 补 yesterday closure
- 创建 new day log
- 回填 historical date

## 历史辅助恢复

当前历史恢复方向是刻意收窄的。

它支持：

- 用户主动提供 transcript
- 用户主动提供 export
- 用户主动提供摘要
- 经审阅的 recovery proposal

它当前**不支持**：

- 自动扫描未文档化本地历史缓存
- 把平台 memory 当项目真相
- 未经审阅直接把历史材料写进 core files

当前目标流程是：

1. 收集历史材料
2. 形成 recovery proposal
3. 记录 review
4. 准备 promotion context
5. 再决定是否通过正式 helper 写入 durable state

## 安装型包结构

请把完整的 `contextweave/` 目录当作一个可安装包：

```text
contextweave/
├── SKILL.md
├── README.md
├── README.zh-CN.md
├── USAGE.md
├── package-metadata.json
├── managed-assets.json
├── profiles/
├── references/
├── scripts/
├── LICENSE
└── NOTICE
```

不要只复制 `SKILL.md`。
如果是从源码 checkout 打包，请排除 `.git/`、`__pycache__/`、`*.pyc`、`.DS_Store` 这类本地元数据与缓存文件。

## 常见安装方式

如果你的环境是目录式 skills，直接安装整个目录：

```bash
cp -R /path/to/contextweave /path/to/<skills-dir>/contextweave
```

或者：

```bash
ln -s /absolute/path/to/contextweave /path/to/<skills-dir>/contextweave
```

常见路径包括：

- Codex：`.agents/skills/contextweave`
- Claude Code：`~/.claude/skills/contextweave` 或 `.claude/skills/contextweave`
- 其他目录式环境：该工具自己的 skills 目录

## 接下来读什么

- [SKILL.md](./SKILL.md)：agent-facing 入口
- [USAGE.md](./USAGE.md)：helper 使用与运行说明
- [references/protocol.md](./references/protocol.md)：协议模型
- [references/file-contracts.md](./references/file-contracts.md)：文件级 contract
- [references/operation-playbooks.md](./references/operation-playbooks.md)：读写 playbook
- 如果你正在阅读完整源代码仓库，可继续看 `docs/adapters/README.md` 中的宿主适配总览；该文件不包含在单独安装的 `contextweave/` 包目录里

## 当前状态

这个仓库当前已经进入 `0.2.0` 发布线。

已经成立的事情包括：

- `0.1.0` 的连续性基线已经存在
- 当前 `0.2.0` 版本已经落下 managed asset registration
- 当前 `0.2.0` 版本已经落下更克制的 cold-start guidance
- 当前 `0.2.0` 版本已经落下 workday recommendation helper
- 当前 `0.2.0` 版本已经落下第一批 recovery workflow helper

当前版本仍然刻意没有纳入的事情包括：

- `/cw-*` 命令运行时
- 完整 task / capture companion 层

更准确的期待是：

> 当前 `0.2.0` 版本已经可用、范围清晰、可公开发布；更大的命令层和 companion 扩展留到后续版本再做。

## 许可证

本项目采用 Apache License 2.0 发布。  
详见 [LICENSE](./LICENSE) 与 [NOTICE](./NOTICE)。
