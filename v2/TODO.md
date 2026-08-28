# Taknee V2: Active Work Backlog & Agent Handoff Protocol

This file serves as the **central state tracker** for any developer or AI agent continuing work on Taknee V2.

---

## 1. Active Sprint: Dual-Track V2 Engine & Radar

### Completed Deliverables (Kernel & Radar Foundation):
- [x] **[K] Transport Bridge (`src/taknee/transport/client.py`)**: Wires SwarmRotator to real LLM calls with automatic 429 failover.
- [x] **[K] First-Run CLI Wizard (`src/taknee/cli/setup.py`)**: `taknee setup`, `taknee doctor`, `taknee models`, and `taknee deals` commands.
- [x] **[K] Git Worktree Sandbox (`src/taknee/engine/sandbox.py`)**: Ephemeral branch isolation in `.taknee/worktrees/<task-id>` with jailed tools and clean merge/prune.
- [x] **[K] Python AST Repo Map (`src/taknee/index/repo_map.py`)**: Token-budgeted symbol extractor for system prompt orientation.
- [x] **[K] Autonomous Milestone DAG (`src/taknee/engine/graph.py`)**: 3-milestone event-driven ReAct loop (*Plan -> Sandbox Action Loop -> Auto-Verify -> Proof*).
- [x] **[R] Community Deal Feed Scraper (`src/taknee/radar/community_feed.py`)**: Live scans of Hacker News, GitHub, and OpenRouter for free API promotions.
- [x] **[R] Changelog Tracker (`src/taknee/radar/changelog_tracker.py`)**: Detects newly added zero-cost models across provider catalogs.
- [x] **[R] Radar API Endpoints (`src/taknee/api.py`)**: `/radar/models`, `/radar/status`, `/radar/deals`, `/radar/deltas`.
- [x] **[UI] Consumer Landing Page (`README.md`)**: High-converting, developer-friendly landing page with free-tier compute matrix and quickstarts.
- [x] **[TEST] V2 Core Test Suite (`tests/test_v2_core.py`)**: 113/113 tests passing cleanly.

### Immediate Next Tasks:
1. [ ] **VS Code Extension Radar Panel (`apps/extension/src/radar.ts`)**: Add a live visual "Free Tier Radar & Deals" panel in the sidebar.
2. [ ] **Tree-sitter Multi-Language Grammar Indexer (`src/taknee/index/ast_indexer.py`)**: Extend AST parsing to TypeScript, Rust, and Go.
3. [ ] **Native Model Context Protocol (MCP) Client (`src/taknee/engine/mcp_client.py`)**: Connect to external developer tools via MCP.

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
