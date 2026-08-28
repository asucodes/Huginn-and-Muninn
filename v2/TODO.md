# Taknee V2: Active Work Backlog & Agent Handoff Protocol

This file serves as the **central state tracker** for any developer or AI agent continuing work on Taknee V2.

---

## 1. Active Sprint: Phase 1 & 2 (Radar & Swarm Foundation)

### Immediate Next Tasks (Priority Order):

1. [ ] **Task 1: Build the Free-Tier Live Radar (`src/taknee/swarm/radar.py`)**
   - Implement OpenRouter `:free` model discovery (`GET https://openrouter.ai/api/v1/models`).
   - Implement GroqCloud & Google AI Studio Gemini Flash live health probes.
   - Add unit tests in `tests/test_swarm_radar.py`.

2. [ ] **Task 2: Build the Multi-Key Swarm Rotator (`src/taknee/swarm/rotator.py`)**
   - Support multiple API keys per provider in `~/.taknee/settings.json`.
   - Implement automatic instant failover on HTTP 429 rate limit exceptions.
   - Add local Ollama zero-cost offline fallback.

3. [ ] **Task 3: Implement Prompt Cache Packer (`src/taknee/swarm/cache_optimizer.py`)**
   - Deterministic prompt ordering (`System Prompt -> Global Guidelines -> Repo Map -> Context Items -> Scratchpad`).
   - Prefix hash verification for OpenRouter/Gemini cache optimization.

4. [ ] **Task 4: Build Ephemeral Git Worktree Manager (`src/taknee/engine/sandbox.py`)**
   - Worktree creation, tool execution confinement, and auto-cleanup.

5. [ ] **Task 5: Implement Milestone DAG Execution Loop (`src/taknee/engine/graph.py`)**
   - Replaces `orchestrator.py` with the 3-milestone autonomous state graph.

---

## 2. Agent Handoff Protocol

When picking up this codebase in a new session or turn:
1. **Read `v2/README.md` & `v2/ROADMAP.md`** to understand the high-level architecture.
2. **Check this `v2/TODO.md`** to identify the topmost uncompleted task in the Active Sprint.
3. **Execute the task**, write corresponding unit tests under `tests/`, and verify all tests pass (`.venv\Scripts\pytest -q`).
4. **Update the checkboxes in `v2/ROADMAP.md` and `v2/TODO.md`** with completed work.
5. **Commit the milestone** cleanly using conventional commit formatting (`feat(...)`, `refactor(...)`, `test(...)`).

---

## 3. Reference Blueprints in this Directory
* **System Manifesto**: [`v2/README.md`](v2/README.md)
* **Master Roadmap**: [`v2/ROADMAP.md`](v2/ROADMAP.md)
* **Radar & Swarm Spec**: [`v2/RADAR_SYSTEM_SPEC.md`](v2/RADAR_SYSTEM_SPEC.md)
* **Harness & Sandbox Spec**: [`v2/HARNESS_ARCHITECTURE.md`](v2/HARNESS_ARCHITECTURE.md)
