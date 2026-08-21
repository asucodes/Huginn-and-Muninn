# Taknee architecture

Taknee is an agentic coding **IDE for small/medium open-weight models**. The editor host is VSCodium (Code-OSS, no Copilot). All agent behavior lives in a local Python kernel.

```
User
  │
  ▼
VSCodium  +  Taknee extension (settings, chat, traces, hunk review, route chip)
  │  HTTP 127.0.0.1:47821
  ▼
taknee kernel
  settings → router → orchestrator (state machine)
                      ├ retrieval (per-workspace index)
                      ├ providers (Groq / NIM / OpenRouter / Ollama)
                      ├ approvals (diffs, terminal)
                      ├ compaction (span addresses)
                      └ sqlite traces
  │
  ▼
Workspace files  +  <workspace>/.taknee/  +  ~/.taknee/settings.json
```

## Kernel packages (`src/taknee/`)

| Module | Job |
| --- | --- |
| `catalog.py` | Allowlisted models with **total** param counts and sources |
| `settings.py` | API keys; written by the Settings screen |
| `store.py` | SQLite: tasks, spans, events, approvals |
| `retrieval.py` | AST-shaped chunks, BM25, identifier overlap, import expansion |
| `router.py` | Feature-based model+provider pick; cooldown |
| `providers.py` | OpenAI-compatible chat, no SDK retries |
| `orchestrator.py` | State machine, stuck detection, budgets |
| `compaction.py` | Pin AGENTS.md / pins / fails; drop raw bodies |
| `patches.py` | Unified diff parse + hunk apply |
| `tools.py` | Read-only git/fs, DDG search, gated tests |
| `agents_md.py` | Parse test/build/style from `AGENTS.md` |
| `api.py` | FastAPI on loopback |

## State machine

```
start → retrieve → localize → patch → [approval] → apply → verify
             ▲                         reject-all → stop
             └── diagnose ←──── fail ──┘
```

Caps: max steps, max seconds (2400), max USD (0.40), same-failure fingerprint ×3, empty-patch ×3. Exceeding a cap **stops and persists** so resume is exact (reload the task id from sqlite).

## Traces

Every agent and tool call is a span: parent, model, provider, `route_reason`, full input/output, span_ids in context, tokens, time, $. The Traces view reads the same table live and after completion.

## IPC

The extension never holds provider keys in its own storage. It posts to the kernel. Keys never log.

## What Free Claude Code taught us (and what we did not copy)

FCC is a **protocol proxy** for Claude Code / Codex. Useful ideas: catalog-driven providers, loopback settings, visible routing, generation-safe config. We did **not** clone Anthropic/Responses translation — our product is an IDE kernel, not a Claude facade.
