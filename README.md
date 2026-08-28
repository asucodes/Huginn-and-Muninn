# ⚡ Huginn & Muninn (Taknee 2.0)

> **"Give developers frontier-grade coding autonomy without charging a single dollar."**

An autonomous, local-first AI coding agent and IDE extension powered by a **Live Free-Tier Compute Radar & Multi-Provider Swarm Mesh**.

---

## 🚀 Why Huginn & Muninn?

Proprietary tools (Cursor, Windsurf, Claude Code, Devin) lock developers behind **$20–$200/month paywalls** and restrict model selection. 

**Huginn & Muninn is 100% free and open-source**:
* **$0.00 Monthly Cost**: Designed from day 1 for zero-budget developers, indie hackers, and students.
* **Instant Free-Tier Swarm**: Combines Groq (500 t/s), OpenRouter (`:free` models), Google AI Studio (Gemini 2.0 Flash), and local Ollama into a unified, rate-limit-proof compute pool.
* **Zero-Risk Sandboxing**: Runs all code exploration, multi-file edits, and test runs in isolated **Git worktrees** — your active editor workspace is never modified until you approve the diff.
* **Live Community Deal Radar**: Scans Reddit, Hacker News, and OpenRouter in real-time for new free AI API drops and promotional credits.
* **Battle-Tested Open-Source Foundation**: Adapts proven patterns from the **OpenAI Codex Harness**, **SWE-agent** ACI, and **Aider**'s fuzzy search-replace algorithms.

---

## ⚡ Quick Start (< 2 Minutes)

### 1. Install & Setup

```bash
# Clone the repository
git clone https://github.com/asucodes/Huginn-and-Muninn.git
cd Huginn-and-Muninn

# Install dependencies (using uv or pip)
uv sync --group dev

# Launch the interactive Free-Tier Setup Wizard
uv run taknee setup
```

### 2. Inspect Live Health & Free Deals

```bash
# Check provider health and active free models
uv run taknee doctor

# List all discovered zero-cost models across providers
uv run taknee models

# Scan community deals for new free API credit drops
uv run taknee deals
```

### 3. Start the Kernel & IDE Extension

```bash
# Start the kernel loopback server
uv run taknee serve

# Run in VS Code / VSCodium:
cd apps/extension
npm install && npm run compile
# Open apps/extension and press F5
```

---

## 📊 Live Free-Tier Compute Matrix

| Provider | Free Tier Value | Latency / Speed | Best Suited Task |
| :--- | :--- | :--- | :--- |
| **Groq Cloud** | Permanent Free Tier (30 RPM) | ~500 t/s | Fast AST Querying, File Filtering, Diagnostics |
| **OpenRouter** | Rotating `:free` Models (Qwen 3 Coder 30B, Llama 3.3) | ~60 t/s | Multi-file `SEARCH/REPLACE` Patches |
| **Google AI Studio** | 15 RPM / 1M Context Window | ~80 t/s | Large-repo map indexing, complex reasoning |
| **Local Ollama / vLLM** | 100% Free & Offline | Hardware-bound | Unlimited private offline fallback |

---

## 🏗️ Architecture & Open-Source Attribution

* **Autonomous Milestone DAG** (`src/taknee/engine/graph.py`): Event-driven ReAct loop adapted from **mini-SWE-agent** (MIT) & **OpenAI Harness** (Apache-2.0).
* **Git Worktree Isolation** (`src/taknee/engine/sandbox.py`): Ephemeral branch sandboxing adapted from **OpenHands** (MIT).
* **Fuzzy Patch Engine** (`src/taknee/patches.py`): Multi-tier search-and-replace algorithm adapted from **Aider** (Apache-2.0).
* **Free-Tier Radar & Swarm** (`src/taknee/swarm/` & `src/taknee/radar/`): Live multi-provider failover mesh and community deal scraper.

---

## 📜 License & Compliance

Released under the **MIT License**. All external algorithms and open-source inspirations are attributed in module documentation.

