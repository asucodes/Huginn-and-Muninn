# Huginn & Muninn

An agentic coding system for **small open-weight models (≤80B total parameters)**. Named for Odin's two ravens: **Huginn** (thought) is the part that flies out and acts, running tasks autonomously; **Muninn** (memory) recalls context, spans, and session history across runs. The kernel was previously codenamed "Taknee"; the `taknee` package and CLI names are kept for compatibility. The editor host is [VSCodium](https://vscodium.com) (prebuilt Code-OSS, no Copilot, no telemetry); all agent behavior lives in this repo: a Python kernel plus a thin extension.

**Plan of record:** [`docs/06-plan-of-record.md`](docs/06-plan-of-record.md) (decisions, architecture, build order, ownership). Everything else in `docs/` is research and trade-off evidence.

## Dev quickstart

```bash
# kernel
uv sync --group dev
uv run pytest -q
uv run taknee            # serves http://127.0.0.1:47821

# extension (in VSCodium/VS Code)
cd apps/extension
npm install && npm run compile
# open apps/extension in the editor and press F5 (Extension Development Host)
```

Open a **project folder** (the codebase to work on) in the dev host. The kernel indexes that folder only , indexes are per-workspace by design.

## Layout

```
src/taknee/     kernel: catalog, settings, store(spans), providers, router,
                orchestrator (state machine), retrieval, compaction, patches,
                tools, agents_md, api (FastAPI loopback)
apps/extension/ VSCodium extension: chat, settings (API keys), review, traces
tests/          kernel unit tests (offline, no API keys needed)
docs/           planning + research + decision log
```

## Constraints we enforce in code

- Every model call goes through `catalog.py` (allowlist with **published total** param counts; ban list with reasons).
- Providers: free-tier / pay-as-you-go / local only (Groq, OpenRouter, NVIDIA NIM, Ollama; Cerebras/Mistral stretch).
- Per-task governors: 2400 s, $0.40, step/fingerprint caps (margins under the eval ceilings 2700 s / $0.50).
- Side-effecting commands require human approval; read-only tools are free.
- API keys are entered in the Settings screen and never logged.
