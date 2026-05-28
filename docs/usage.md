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

---

## 14. 多会话 / 多项目（v0.2）

```bash
agentic sessions new --project myapp --root ./myapp --title "需求评审"
agentic sessions ls
agentic sessions show <session-id>
```

Python：

```python
from agentic_engine.core.sessions import SessionStore

store = SessionStore()
proj = store.upsert_project("myapp", "./myapp")
sess = store.new_session(proj.id, "需求评审")
store.append(sess.id, "user", "做一个 markdown -> pdf CLI")
store.append(sess.id, "assistant", "建议先写 PM 文档...")
for m in store.history(sess.id):
    print(m.role, m.content[:60])
```

## 15. 定时任务 / Cron（v0.2）

```bash
pip install -e ".[cron]"

agentic cron add daily-summary --cron "0 9 * * *" \
  --message "汇总昨日 git log 变更，发到我邮箱"
agentic cron ls
agentic cron rm <id>
```

支持的 schedule：`{kind:"cron",expr:"0 9 * * *"}` / `{kind:"interval",seconds:600}` / `{kind:"date",run_at:"2026-06-01T09:00:00"}`。

## 16. Token 用量统计（v0.2）

每一次成功的 LLM 调用都会写一行到 `~/.agentic-engine/usage.jsonl`。

```bash
agentic usage              # 全部
agentic usage --days 7     # 近 7 天
agentic usage --json
curl localhost:9120/usage
```

## 17. git worktree 隔离（v0.2）

```bash
agentic worktree add /path/to/repo --branch agent/spike
agentic worktree ls /path/to/repo
```

Python：

```python
from agentic_engine.core.worktree import add_worktree
h = add_worktree("/path/to/repo")
# h.path 是新 checkout；h.remove(force=True) 删
```

## 18. MCP 工具服务器（v0.2）

```python
from agentic_engine.core.mcp import MCPClient
from agentic_engine import Agent
from agentic_engine.tools import read_file

client = MCPClient(["python", "-m", "your_mcp_server"])
client.start()
mcp_tools = client.as_tools()

a = Agent(name="mcp-user", tools=[read_file] + mcp_tools)
a.run("调用 mcp_xxx 工具完成 Y")

client.stop()
```

## 19. Computer Use（v0.2）

```bash
pip install -e ".[computer-use]"
```

```python
from agentic_engine import Agent
from agentic_engine.tools import (
    screen_grab, screen_size, mouse_click, keyboard_type
)

a = Agent(
    name="ui-tester",
    permission=...,           # 强烈建议挂 approval_hook
    tools=[screen_grab, screen_size, mouse_click, keyboard_type],
)
a.run("截图屏幕中央，点 (400,300)，输入 hello")
```

`mouse_click / mouse_move / keyboard_type / keyboard_hotkey` 都打了
`requires_approval=True`，不会被静默放过。

## 20. Telegram 机器人（v0.2）

```bash
export TELEGRAM_BOT_TOKEN=123456:abc...
```

```python
from agentic_engine.adapters import TelegramAdapter
from agentic_engine import Agent
from agentic_engine.tools import read_file, web_fetch

a = Agent(name="tg", tools=[read_file, web_fetch])
tg = TelegramAdapter()

def on_msg(im):
    tg.send(im.chat_id, a.run(im.text, verbose=False).output)

tg.listen(on_msg)
```

## 21. H5 一次性分享（v0.2）

```bash
export AGENTIC_ADMIN_KEY=$(openssl rand -hex 16)
agentic serve --port 9120 &

TOKEN=$(curl -s -X POST localhost:9120/h5/token \
  -H "X-Admin-Key: $AGENTIC_ADMIN_KEY" | jq -r .token)
open "http://localhost:9120/h5/page?token=$TOKEN"
```

Token 默认 1800 秒过期；过期或第二次失效都会 401。

## 22. 桌面控制台

```bash
agentic serve --port 9120 &
open desktop/web/index.html
```

打开即用：左侧 sessions、中间消息流、右侧 status / usage / cron。
想包成原生窗口看 `desktop/README.md` 里的 Tauri 段。
