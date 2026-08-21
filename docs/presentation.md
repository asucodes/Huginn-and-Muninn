# 10-minute presentation outline

Two presenters. Y26s must be ready for a separate implementation Q&A.

1. **Problem (45s)** — Small models fail at long ReAct. Scoring kills cost. Hidden eval is multi-file, long-horizon.
2. **Score math (45s)** — Drive C to $0 with free-tier/Ollama. Stop before $0.50 / 2700s. Accuracy still in the numerator.
3. **IDE choice (45s)** — VSCodium + our extension. Not a VS Code fork (EclipseSource: marketplace + rebase). Not Atom. Not Theia AI. Not Cursor.
4. **Orchestrator (2 min)** — Agentless pipeline in a state machine. Tests verify, not a reviewer LLM. Caps and backtrack.
5. **Retrieval (1.5 min)** — AST chunks + BM25 + identifier Jaccard + import hop. Isolation demo.
6. **Live demo (3 min)** — Settings keys → route chip → pin a span → hunk reject → traces. `/bytheway`.
7. **What we refused (1 min)** — 480B “free” coder models, Gemini (no param card), debate swarms.

If they ask “did an LLM write this?”: point at `docs/decisions.md` and the test that bans DeepSeek-V3.
