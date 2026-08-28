# Taknee V2: Free-Tier Radar & Swarm Mesh Specification

---

## 1. System Objective
The **Free-Tier Radar & Swarm Mesh** is Taknee's core economic engine. Its mission is to deliver **limitless, high-speed, zero-cost AI coding compute** by dynamically aggregating, monitoring, and load-balancing across all available free tiers and promotional credits.

---

## 2. Component Architecture

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                          FREE-TIER RADAR & SWARM MESH                                  │
├────────────────────────────────────────────────────────────────────────────────────────┤
│                                                                                        │
│  ┌─────────────────────────┐  ┌─────────────────────────┐  ┌────────────────────────┐  │
│  │   LIVE PROBE SCRAPER    │  │   MULTI-KEY VAULT POOL  │  │  PROMPT CACHE PACKER   │  │
│  │                         │  │                         │  │                        │  │
│  │ • OpenRouter :free sync │  │ • Multi-key per provider│  │ • Immutable Prefix Hash│  │
│  │ • Groq 30 RPM monitor   │  │ • Instant 429 failover  │  │ • 90%+ Cache Hit Rate  │  │
│  │ • Gemini Flash quota    │  │ • Health & latency score│  │ • System/Repo alignment│  │
│  │ • Social promo drops    │  │ • Local Ollama fallback │  │                        │  │
│  └───────────┬─────────────┘  └───────────┬─────────────┘  └───────────┬────────────┘  │
│              │                            │                            │               │
│              └────────────────────────────┼────────────────────────────┘               │
│                                           │                                            │
│                                           ▼                                            │
│                       [DYNAMIC TIER ROUTER & SWARM DISPATCH]                           │
│                                                                                        │
│         Tier 0 (Fast Filter)  ──> Groq Llama 3.3 (500 t/s) / Local 7B (<300ms)         │
│         Tier 1 (Core Coder)   ──> OpenRouter :free Qwen 3 Coder 30B / Ollama 14/30B    │
│         Tier 2 (Heavy Repair) ──> Google AI Studio Gemini 2.0 Flash / Llama 3.3 70B    │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

---

## 3. Supported Free-Tier Providers & Capabilities

| Provider | Access Method | Rate Limit / Quota | Latency / Speed | Best Suited Task |
| :--- | :--- | :--- | :--- | :--- |
| **Groq Cloud** | Free API Key | 30 RPM / 14,400 RPD | ~500 tokens/sec | AST Querying, File Filtering, Diagnostics |
| **OpenRouter** | Free API Key | 50 RPD (Base) / 1,000 RPD (Active) | ~60 tokens/sec | Multi-file `SEARCH/REPLACE` Patches |
| **Google AI Studio** | Free API Key | 15 RPM / 1M token window | ~80 tokens/sec | Large-repo map indexing, complex reasoning |
| **Cerebras / NIM** | Free Dev Tier | High token burst | ~1,000 tokens/sec | Fast syntax checking and unit test verification |
| **Z.ai / DeepSeek** | Promo Grants / Low PAYG | High throughput | ~50 tokens/sec | Escalated repair loops |
| **Ollama / vLLM** | Local In-Process | Unlimited / Offline | Hardware-bound | 100% Private Offline Zero-Cost Fallback |

---

## 4. Swarm Failover & Load-Balancing Logic

When an agent needs an LLM call:

1. **Tier Resolution**: The task stage determines the required model tier (e.g. `Tier 0: Filter`, `Tier 1: Coder`, `Tier 2: Architect`).
2. **Health & Quota Check**: The router checks the live health matrix:
   - Is Provider A cooling down from a 429? $\rightarrow$ Skip to Provider B.
   - Did Provider B return a 404 for a rotated `:free` slug? $\rightarrow$ Auto-update catalog and route to Provider C.
3. **Prompt Cache Alignment**:
   - The payload is structured with exact immutable prefixes: `[System Prompt] + [Agents.md Rules] + [Repo Map Skeleton] + [Recent History] + [Scratchpad]`.
   - Maximizes KV cache reuse on OpenRouter, Gemini, and DeepSeek, reducing TTFT by 10x.
4. **Zero-Latency Fallback**:
   - If all cloud free tiers are rate-limited or offline, the request automatically falls back to local **Ollama** (e.g., `qwen2.5-coder:7b` or `qwen3:8b`) without throwing an unhandled exception.

---

## 5. Security & Key Privacy
* Keys are stored locally in `~/.taknee/settings.json` (POSIX `0600` permissions).
* Keys are never logged in SQLite traces, never transmitted over external networks, and never echoed back in API GET responses.
