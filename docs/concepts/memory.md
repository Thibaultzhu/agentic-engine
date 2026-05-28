# Memory & RAG

Two complementary stores ship in v0.3:

| Component  | Lives in                       | Use it for                              |
|------------|--------------------------------|-----------------------------------------|
| `Memory`   | In-process list                | Short-lived per-agent scratchpad.       |
| `RAGMemory`| `chromadb` PersistentClient or | Cross-session retrievable knowledge.    |
|            | local BM25 fallback            |                                         |

## RAGMemory at a glance

```python
from agentic_engine import RAGMemory

rag = RAGMemory(persist_dir="~/.agentic-engine/rag")
rag.add("Bailian Singapore endpoint requires a separate API key.",
        metadata={"scope": "ops"})
hits = rag.search("singapore endpoint", top_k=3)
for text, score, meta in hits:
    print(f"[{score:.3f}] {text}")
```

* If `chromadb` is installed and `persist_dir` is provided, vectors are
  embedded with the default sentence transformer and persisted to disk.
* Otherwise, a small BM25 implementation (`_BM25Lite`) handles
  retrieval. Same API, no dependencies.

## Wiring into Agent loops

```python
from agentic_engine import Agent, RAGMemory

rag = RAGMemory(persist_dir="~/.agentic-engine/rag")

class _RagAgent(Agent):
    def _build_messages(self, user_input):
        msgs = super()._build_messages(user_input)
        ctx = "\n".join(t for t, _, _ in rag.search(user_input, top_k=4))
        if ctx:
            msgs.insert(1, {"role": "system",
                            "content": f"Project memory:\n{ctx}"})
        return msgs
```

(For convenience, the public `Agent.use_bootstrap_memory` flag also
prepends the `Memory` snapshot, and the wrapper above can be replaced
by feeding rag hits into `Memory.bootstrap`.)
