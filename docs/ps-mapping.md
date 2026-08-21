# Problem-statement → code

Official PDF is saved as `docs/ps-official.pdf` (not in git). This table is what we implement.

| # | Requirement | Where |
| --- | --- | --- |
| 1 | Multi-agent orchestration, failures, stuck detection | `orchestrator.py` state machine + caps |
| 2 | ≤80B total params, free/PAYG/local, 8GB VRAM local | `catalog.py` allow + ban lists |
| 3 | Smart routing, visible, fallback, **settings screen** | `router.py`, status bar, `taknee.settings` |
| 4 | Automatic compaction, no lost pins/AGENTS.md | `compaction.py` |
| 5 | Code retrieval, per-codebase isolation, beyond keyword/vector | `retrieval.py` + isolation test |
| 6 | Resume after close | SQLite in `<ws>/.taknee/taknee.db` |
| 7 | Manual pins, clickable tags, `/bytheway` | extension + `pin` / `bytheway` |
| 8 | Tools + approval for side effects | `tools.py`, Review webview |
| 9 | AGENTS.md | `agents_md.py`, pinned in compaction |
| 10 | Git diffs, hunk accept/reject, partial continue | `patches.py`, `resolve_approval` |
| 11 | Trace dashboard live + post-hoc | `store.spans`, Traces view |

Scoring implication we optimize: **drive C to $0** with free-tier/Ollama, stop before 2700s/$0.50, put remaining budget into localization recovery not extra agents.
