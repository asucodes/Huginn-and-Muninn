# Taknee V2: Next-Gen Agentic Harness Architecture

---

## 1. Executive Summary & Design Principles

The Taknee V2 Harness replaces the rigid 2024 SWE-bench linear conveyor belt with a modern, event-driven **Autonomous Milestone DAG** inspired by the open-source **OpenAI Harness**, **SWE-agent**, and **mini-SWE-agent**.

### Core Tenets:
1. **Dynamic Tool Use within Safe Milestones**: Agents are not constrained to single-step blind actions; they can explore, run tests, and search code iteratively inside sandboxed phases.
2. **Zero-Risk Ephemeral Worktrees**: All agent operations occur inside temporary Git worktree branches. The user's active editor workspace is never modified until the user approves the final patch diff.
3. **Deep Codebase Intelligence**: Upgraded from naive regex chunking to **Tree-sitter AST symbol graphs** across 10+ programming languages.
4. **Standard Model Context Protocol (MCP)**: Native client support to interface with external developer tools, databases, and custom skills.

---

## 2. The Milestone DAG State Graph

```
                   ┌──────────────────────────────────────┐
                   │          USER TASK PROMPT            │
                   └──────────────────┬───────────────────┘
                                      │
                                      ▼
                   ┌──────────────────────────────────────┐
                   │    MILESTONE 1: EXPLORATION & PLAN   │
                   │  • Tree-sitter Symbol Discovery      │
                   │  • Workspace Search & AST Mapping    │
                   │  • Generates Task Strategy           │
                   └──────────────────┬───────────────────┘
                                      │
                                      ▼
                   ┌──────────────────────────────────────┐
                   │   MILESTONE 2: SANDBOXED ReAct LOOP  │
                   │  • Ephemeral Git Worktree Sandbox    │
                   │  • Read File / AST Callers           │
                   │  • Write SEARCH/REPLACE Hunks        │
                   │  • Run Unit Tests / Build Check      │
                   │  • Self-Correct & Diagnose Failures  │
                   └──────────────────┬───────────────────┘
                                      │
                         [Automated Tests Pass]
                                      │
                                      ▼
                   ┌──────────────────────────────────────┐
                   │    MILESTONE 3: PROOF & HUMAN REVIEW │
                   │  • Unified Git Diff Generation       │
                   │  • Multi-hunk Accept / Reject UI     │
                   │  • 1-Click Merge into Main Branch    │
                   └──────────────────────────────────────┘
```

---

## 3. Ephemeral Git Worktree Sandboxing

1. **Isolation by Construction**:
   - For every task `task_id`, the harness runs:
     ```bash
     git worktree add .taknee/worktrees/<task_id> -b agent/<task_id> HEAD
     ```
   - All tools (`read_file`, `write_file`, `run_terminal`, `git_diff`) execute exclusively inside this jailed worktree path.
2. **Safe Verification**:
   - Test suites (e.g. `pytest`, `npm test`, `cargo test`) run against the isolated worktree without affecting open files in the IDE.
3. **1-Click Merge & Teardown**:
   - On approval: The verified commit/diff is cherry-picked or merged into the user's active branch.
   - On rejection/cancellation: The worktree is pruned (`git worktree remove --force .taknee/worktrees/<task_id>`) and the temporary branch is deleted.

---

## 4. Tree-sitter Codebase Intelligence & AST Indexer

* **Multi-Language Grammar Parsing**: Python, TypeScript, JavaScript, Rust, Go, C++, Java, C#, Ruby, PHP.
* **Symbol Dependency Graph** (Stored in SQLite WAL):
  * **Definitions**: Functions, classes, interfaces, types, methods with byte-accurate line spans.
  * **References & Callers**: Function invocation graph, import graph, and inheritance trees.
* **Specialized Agent Tools**:
  * `find_definition(symbol_name: str)`
  * `find_callers(function_name: str)`
  * `get_type_signature(class_or_func: str)`
  * `get_repo_outline(budget: int = 1000)`

---

## 5. Model Context Protocol (MCP) & Skills

* **MCP Client Integration**:
  * Communicates via standard JSON-RPC over stdio or SSE.
  * Dynamically exposes MCP tools to the agent ReAct loop (e.g., PostgreSQL query inspection, GitHub PR lookup, Brave web search).
* **Directory-Based Skills**:
  * Users can create custom skills under `.taknee/skills/<skill-name>/SKILL.md` containing prompt guidelines and custom execution workflows.
