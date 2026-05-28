# 使用手册

> 五分钟从安装到跑通一个 5 人开发队。

## 1. 安装

```bash
git clone https://github.com/Thibaultzhu/agentic-engine.git
cd agentic-engine
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## 2. 配置百炼 API

```bash
cp .env.example .env
$EDITOR .env
```

至少填一项：

```
AGENTIC_REGION=sg
DASHSCOPE_API_KEY_SG=sk-...
```

国内用户改 `AGENTIC_REGION=cn` 并填 `DASHSCOPE_API_KEY_CN`。

## 3. Hello world

```bash
agentic version
agentic chat "用三句话介绍你自己"
```

## 4. 单 Agent 加工具

```python
from agentic_engine import Agent
from agentic_engine.tools import read_file, list_dir, grep_text

a = Agent(
    name="repo-explorer",
    role="explorer",
    system_prompt="你只用工具回答问题。",
    tools=[read_file, list_dir, grep_text],
)
a.run("当前目录里有什么 Python 文件，挑一个解释作用")
```

## 5. 自定义工具

```python
from agentic_engine import tool

@tool(name="add", description="加法")
def add(a: int, b: int) -> int:
    return a + b
```

`Agent` 接收一个 `tools=[add, ...]`，运行时自动 schema 化。

## 6. 三种编排模式

```python
from agentic_engine import Agent, Orchestrator

orch = Orchestrator(agents=[a1, a2, a3])

# 串：a1 -> a2 -> a3
orch.run_sequential("初始任务")

# 并：每个 agent 一个独立子任务
orch.run_parallel({"a1": "...", "a2": "...", "a3": "..."})

# 团队：leader 拆分 + 队员并行 + leader 收口
orch.dispatch(leader_name="a1", goal="复杂目标")
```

## 7. 持久化记忆

```python
from agentic_engine import Memory

m = Memory()
m.add("user", "我偏好简洁回答")
m.add("project", "本仓 push 前必须 ruff + pytest 全绿")

a = Agent(name="x", memory=m, use_bootstrap_memory=True, ...)
# m.bootstrap_block() 会被自动写进 system 里
```

CLI 等价：

```bash
agentic memory add  --scope user --text "我偏好简洁回答"
agentic memory show --scope user
agentic memory search --text 简洁
```

## 8. 写一个 Skill

```bash
mkdir -p ~/.agentic-engine/skills/release-notes
```

```markdown
---
name: release-notes
description: 从 git log 生成 release notes 草稿
version: 1.0.0
triggers:
  - release notes
  - changelog
---

# Steps
1. `git log --oneline -n 50`
2. 按 feat/fix/chore 分组
3. 输出 markdown 表
```

```bash
agentic skills            # 验证已被发现
```

## 9. 5 人开发队

```bash
agentic dev-team "做一个把 markdown 转成 PDF 的小 CLI，含 pytest"
```

或者 Python：

```python
from agentic_engine.teams import build_dev_team

team = build_dev_team()
results = team.run_sequential("Goal here")
```

## 10. HTTP 服务

```bash
uvicorn agentic_engine.server:app --port 9120
curl -s -X POST http://localhost:9120/chat \
  -H 'content-type: application/json' \
  -d '{"message":"hello"}' | jq .
```

## 11. 权限模式

```python
from agentic_engine import Agent, PermissionMode

def approve(name, args):
    print(f"approve {name}({args})? [y/N] ", end="")
    return input().strip().lower() == "y"

a = Agent(
    name="careful",
    permission=PermissionMode.DEFAULT,
    approval_hook=approve,
    tools=[...],
)
```

| 模式            | 行为                                |
|-----------------|------------------------------------|
| `DEFAULT`       | 危险动作走 `approval_hook`           |
| `PLAN`          | 每个工具调用都要批                   |
| `ACCEPT_EDITS`  | 只读自动放，写要批                   |
| `BYPASS`        | 全放（仅可信自动化）                 |
| `DONT_ASK`      | 凡未预批的全拒                       |

## 12. 接 IM 通道

```python
from agentic_engine.adapters import FeishuAdapter

ad = FeishuAdapter(webhook="https://open.feishu.cn/open-apis/bot/v2/hook/...")
ad.send("group_xxx", "构建完成 ✅")
```

入站推送需要自己起 FastAPI 路由对接平台事件回调；本框架只给契约。

## 13. 故障排查

| 现象                                       | 原因                          | 解法                                |
|-------------------------------------------|------------------------------|-------------------------------------|
| `openai.AuthenticationError`              | API Key 没填或区域不匹配       | 检查 `AGENTIC_REGION` 和对应 KEY      |
| Bailian 报 `Range of input length`         | 历史消息太长                  | 减小 `max_turns` 或换 `qwen3-max`    |
| Skill 没被发现                            | 路径不在搜索路径               | 放到 `<repo>/skills/` 或 `~/.agentic-engine/skills/` |
| 工具被拒                                  | 当前权限模式禁了              | 切到 `ACCEPT_EDITS` 或挂 `approval_hook` |
| `bash_run [refused]`                       | 命令命中黑名单                 | 改写命令；或把命令拆细                |
