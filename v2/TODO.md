# Taknee V2: Active Work Backlog & Agent Handoff Protocol

This file serves as the **central state tracker** for any developer or AI agent continuing work on Taknee V2.

---

## 1. Active Sprint: Phase 3 (Next-Gen Autonomous Harness)

### Completed Tasks in Phase 2 (Radar & Swarm):
- [x] **Task 1: Free-Tier Live Radar (`src/taknee/swarm/radar.py`)** (OpenRouter `:free` probe, Groq/Gemini health matrix, verified offline models).
- [x] **Task 2: Multi-Key Swarm Rotator (`src/taknee/swarm/rotator.py`)** (Multi-key per provider, instant 0ms 429 failover, local Ollama fallback).
- [x] **Task 3: Prompt Cache Packer (`src/taknee/swarm/cache_optimizer.py`)** (Deterministic prefix hash, 90%+ KV cache optimization).
- [x] **Task 4: Swarm Unit Tests (`tests/test_swarm_radar.py`)** (105/105 tests passing).

### Immediate Next Tasks (Priority Order for Phase 3):

1. [ ] **Task 3.1: Build Ephemeral Git Worktree Sandbox (`src/taknee/engine/sandbox.py`)**
   - Implement `GitWorktreeSandbox`: creates temporary branches in `.taknee/worktrees/<task-id>`, executes jailed tools, and supports clean 1-click merge / prune.
   - Add unit tests in `tests/test_engine_sandbox.py`.

2. [ ] **Task 3.2: Implement Autonomous Milestone DAG (`src/taknee/engine/graph.py`)**
   - Replaces `orchestrator.py` with the 3-milestone event-driven ReAct loop (*Plan -> Sandbox Action Loop -> Auto-Verify -> Proof*).
   - Add unit tests in `tests/test_engine_graph.py`.

3. [ ] **Task 3.3: Async PTY Terminal Manager (`src/taknee/engine/terminal.py`)**
   - Persistent pseudo-terminal manager for interactive test runners and streaming CLI tools.

4. [ ] **Task 3.4: Integrate Tree-sitter Codebase AST Indexer (`src/taknee/index/ast_indexer.py`)**
   - Multi-language AST definition and caller graph indexer.

---

## 2. Agent Handoff Protocol

When picking up this codebase in a new session or turn:
1. **Read `v2/README.md` & `v2/ROADMAP.md`** to understand the high-level architecture.
2. **Check this `v2/TODO.md`** to identify the topmost uncompleted task in the Active Sprint (currently: Task 3.1 `src/taknee/engine/sandbox.py`).
3. **Execute the task**, write corresponding unit tests under `tests/`, and verify all tests pass (`.venv\Scripts\pytest -q`).
4. **Update the checkboxes in `v2/ROADMAP.md` and `v2/TODO.md`** with completed work.
5. **Commit the milestone** cleanly using conventional commit formatting (`feat(...)`, `refactor(...)`, `test(...)`).

---

## 3. Reference Blueprints in this Directory
* **System Manifesto**: [`v2/README.md`](v2/README.md)
* **Master Roadmap**: [`v2/ROADMAP.md`](v2/ROADMAP.md)
* **Radar & Swarm Spec**: [`v2/RADAR_SYSTEM_SPEC.md`](v2/RADAR_SYSTEM_SPEC.md)
* **Harness & Sandbox Spec**: [`v2/HARNESS_ARCHITECTURE.md`](v2/HARNESS_ARCHITECTURE.md)
