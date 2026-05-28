# Eval harness

A tiny harness for regression-testing prompts and tool flows.

## Define tasks

`evals/golden/basic.json`:

```json
[
  {
    "name": "echo-greeting",
    "input": "Say hello to Alice in one short sentence.",
    "expect": {"kind": "regex", "value": "(?i)hello,?\\s+alice"}
  },
  {
    "name": "json-passthrough",
    "input": "Return the JSON object {\"ok\":true} verbatim.",
    "expect": {"kind": "contains", "value": "\"ok\": true"}
  },
  {
    "name": "math-add",
    "input": "What is 17 + 25? Just the number.",
    "expect": {"kind": "regex", "value": "\\b42\\b"},
    "rubric": "Numerical answer must be exactly 42."
  }
]
```

## Run them

```python
from agentic_engine import Agent, run_eval, load_tasks

tasks = load_tasks("evals/golden/")

def factory():
    return Agent(name="eval", role="general-purpose")

report = run_eval(tasks, agent_factory=factory)
print(report.to_dict())
```

…or via the server:

```bash
curl -X POST http://127.0.0.1:8765/eval \
  -H "X-Admin-Key: $AGENTIC_ADMIN_KEY" \
  -H "Content-Type: application/json" \
  -d '{"path": "evals/golden/basic.json"}'
```

## Judgement modes

| `expect.kind` | Meaning                                       |
|---------------|-----------------------------------------------|
| `contains`    | Case-insensitive substring on the agent output|
| `regex`       | `re.search(pattern, output, re.S | re.I)`     |
| `llm`         | Ask Bailian Qwen to grade `PASS`/`FAIL` per `rubric` |

## CI integration

Wire the eval harness into your release pipeline:

```yaml
- name: Eval
  run: |
    pip install -e ".[server,auth]"
    python -m agentic_engine.evals run evals/golden/
```

A non-zero exit code from `run_eval` (`pass_rate < 1.0`) fails the
release.
