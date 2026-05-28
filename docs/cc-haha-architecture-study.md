# 高层架构研究：cc-haha 类桌面 Agent 工作台

> 本文是一份**纯研究性的高层架构观察**，仅基于 cc-haha 项目公开 README 和 `docs/`
> 中已经公开发表的设计概念。**不复制任何源代码**，不对实现细节做逆向再现。
> 目的：帮助理解"桌面端多 Agent 工作台"这一类产品的通用结构，作为
> `agentic-engine` 设计取舍的参照系。

## 一、产品形态摘要（来自其公开 README）

cc-haha 公开声明自己是"桌面端 Claude Code 工作台"，把若干能力集中在一个
macOS / Windows 应用里：会话管理、多项目切换、git 分支与 Worktree、右侧代码改
动面板、Diff 视图、权限审批流、模型供应商切换、Computer Use（截屏/点击）、
H5 远程访问、IM 接入、定时任务、Token 用量统计。

技术栈（其 README 公开列出）：TypeScript / Tauri 2 / React + Vite / Bun /
Ink / Commander / Anthropic SDK / MCP / LSP。

## 二、抽离出来的"桌面 Agent 工作台"通用架构

把以上能力归类，几乎所有同类产品都会出现以下九个层次。这里只描述层次本身，
不涉及任何特定实现：

```
+----------------------------------------------------------+
| 1. 桌面外壳 (Tauri / Electron / Wails)                    |
|    - 系统托盘、菜单、自动更新、单实例锁                    |
+----------------------------------------------------------+
| 2. 渲染层 (React / Vue / Svelte)                          |
|    - 多标签会话、文件树、Diff 视图、权限确认弹窗            |
+----------------------------------------------------------+
| 3. 进程桥 (IPC / native bridge)                           |
|    - 渲染进程 ↔ 主进程的事件流                              |
+----------------------------------------------------------+
| 4. 会话与 Agent 编排核心                                   |
|    - Agent 定义、工具池、循环、子 Agent、Team              |
+----------------------------------------------------------+
| 5. 工具 / 命令 / Skills 注册表                              |
|    - 文件、Bash、网络、版本控制工具；斜杠命令；Skills 插件  |
+----------------------------------------------------------+
| 6. 提供商抽象 (Provider Layer)                             |
|    - 多模型、多 API（兼容/原生）、token 计费记录            |
+----------------------------------------------------------+
| 7. 持久化与记忆                                             |
|    - 会话历史、记忆文件、配置、状态机                        |
+----------------------------------------------------------+
| 8. 远程通道 (IM / H5 / 移动)                               |
|    - 飞书/钉钉/微信/Telegram 适配器；一次性令牌入口         |
+----------------------------------------------------------+
| 9. 系统能力                                                 |
|    - Computer Use（截屏/键鼠）、定时任务、本地 MCP server   |
+----------------------------------------------------------+
```

## 三、cc-haha 公开文档体现出的若干设计决定

下列条目均出自其 `docs/` 公开说明（README、agent/usage-guide、memory/usage-guide
等），是**公开发表的设计概念**，并非源码：

1. **多类型 Agent**：内置若干"通用 / 探索 / 规划 / 验证 / 指南 / 配置类"角色，每个有
   自己的工具池上限、模型上限、读写边界。这与 OpenAI Agents SDK 的 specialist
   agents 思路一致。
2. **后台 Agent 与通知协议**：长任务可异步化，主 Agent 收到结构化完成通知。
   这是 CrewAI / AutoGen 早期版本就有的"async worker + event"通用模式。
3. **Agent Teams 与队员消息**：Team Lead 创建命名队员，互相通过命名消息通信，
   广播 / 关停握手。LangGraph 的 swarm 例子里有相似抽象。
4. **多种权限模式**：default / plan / acceptEdits / bypassPermissions / dontAsk
   等，把"风险动作的处置策略"显式化为枚举 — 通用而独立于具体实现。
5. **四类记忆**：用户画像 / 行为反馈 / 项目动态 / 外部引用。这种维度分类几乎
   就是写作类 LLM 应用通用的"我应该记什么"清单，源头早于 cc-haha。
6. **Skills 插件**：以 `.md` 文件 + frontmatter 的格式描述能力 — 与 Anthropic
   公开的 Agent Skills 规范一致，也与本框架默认的 SKILL.md 形态对齐。
7. **IM 多通道接入**：飞书 / 钉钉 / 微信 / Telegram，每个通道实现统一的"发送 +
   订阅 + 审批转发"接口。这是企业 ChatOps 普遍做法。
8. **Worktree 隔离**：让 Agent 在独立 git worktree 中改文件，主工作区不受影响。
   这是 git 自带能力的常规组合用法。

## 四、从这个研究映射到 `agentic-engine` 的取舍

| 通用层    | cc-haha 形态（桌面工作台）            | 本项目选择                       | 理由                                    |
|----------|---------------------------------|---------------------------------|---------------------------------------|
| 1+2+3    | Tauri + React + IPC             | 不做 GUI                         | 桌面壳本身是大工程，独立项目更合适      |
| 4        | TS 主代理 + 多类型子代理 + Teams | Python `Agent` + `Orchestrator` | 五原语、单文件可读                     |
| 5        | TS 工具 + 斜杠命令 + Skills       | `@tool` 装饰器 + SKILL.md       | 不引入命令 DSL，函数即工具             |
| 6        | Anthropic SDK + 多 provider      | OpenAI 兼容 + 百炼默认           | 与你已有的 Hermes / 多 Agent 栈一致     |
| 7        | 文件型记忆 + 会话 DB              | 仅文件型四 scope                | 入门用，需要 DB 时再加适配             |
| 8        | 飞书/钉钉/微信/Telegram          | `IMAdapter` 抽象 + 两个 stub     | 通道类很多，先给契约和最常用两家       |
| 9        | Computer Use / cron / MCP        | 不内嵌 cron；不内嵌 Computer Use | 操作系统已有调度器；视觉自动化是独立坑 |

## 五、为什么本项目不试图"做一个一样的"

1. **法律边界**：cc-haha 自述基于泄露的 Anthropic Claude Code 源码修复。它的
   实现细节属于第三方版权，复制或"小幅替换后复制"都越界。
2. **工程边界**：桌面壳 + IPC + 渲染层 + 远程 H5 + Computer Use 的工程量远大
   于 Agent 编排核心。复刻整套对学习"agent 怎么跑"无加分。
3. **学习边界**：上面那些"通用层"才是可迁移的知识。把它们用 ~1k 行 Python 复
   现一遍，比读一份十万行 TS 桌面工程更容易吸收。

## 六、扩展建议

如果将来希望本项目长成同类工作台，按层渐进而不是一次到位：

1. 先扩 `core` —— 加 worktree 隔离的 helper、加后台任务的本地通知文件协议；
2. 再加 GUI —— 单独建仓做 Tauri 壳，调用 `agentic_engine.server` 的 HTTP；
3. 最后做远程 / IM —— 用现有 `adapters/` 接通真实平台 SDK。

## 参考材料（公开链接）

- cc-haha README（公开）
- CrewAI 文档与代码 https://github.com/crewAIInc/crewAI
- Microsoft AutoGen https://github.com/microsoft/autogen
- LangGraph https://github.com/langchain-ai/langgraph
- OpenAI Agents SDK https://github.com/openai/openai-agents-python
- Anthropic Agent Skills 公开规范
