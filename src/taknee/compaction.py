"""Compaction — addresses, not summaries (docs/decisions.md D5).

The task context is a list of typed items. Pinned items (task prompt,
AGENTS.md digest, user pins, last fail log, decisions) are NEVER compacted.
Non-pinned bodies beyond the budget become address entries:
  [compacted span #<id>: 40-token preview...]
which can be re-hydrated from the store/index on demand. Code is addressable;
summarizing code is how small models invent APIs — so we don't.
"""

from __future__ import annotations

from dataclasses import dataclass, field

SOFT_TRIGGER = 0.70  # compact when projected > 70% of the *selected model's* window


@dataclass
class ContextItem:
    key: str
    content: str
    pinned: bool = False
    kind: str = "body"  # body|address after assembly

    @property
    def tokens(self) -> int:
        return estimate_tokens(self.content)


def estimate_tokens(text: str) -> int:
    """Cheap heuristic (~4 chars/token); router/compaction only need order-of-magnitude."""
    return max(1, len(text) // 4)


def should_compact(projected_tokens: int, window_tokens: int) -> bool:
    return projected_tokens > SOFT_TRIGGER * window_tokens


def assemble(items: list[ContextItem], window_tokens: int) -> tuple[str, dict]:
    """Build the working context under `window_tokens`.

    Returns (context_text, stats). Pinned items always ship in full (they are
    sized to fit any window by construction); the oldest non-pinned bodies are
    demoted to addresses until we are under budget.
    """
    pinned = [i for i in items if i.pinned]
    floating = [i for i in items if not i.pinned]

    kept: list[ContextItem] = []
    budget = window_tokens - sum(i.tokens for i in pinned)
    for item in reversed(floating):  # newest (last) first — recency wins
        if item.tokens <= budget:
            kept.append(item)
            budget -= item.tokens
        else:
            break
    kept.reverse()

    compacted = [i for i in floating if i not in kept]
    lines: list[str] = []
    for i in pinned:
        lines.append(f"### {i.key} (pinned)\n{i.content}")
    for i in kept:
        lines.append(f"### {i.key}\n{i.content}")
    for i in compacted:
        lines.append(f"### {i.key}\n[compacted] {preview(i.content)} …")

    stats = {
        "items_total": len(items),
        "items_kept": len(pinned) + len(kept),
        "items_compacted": len(compacted),
        "tokens_before": sum(i.tokens for i in items),
        "tokens_after": estimate_tokens("\n".join(lines)),
    }
    return "\n\n".join(lines), stats


def preview(text: str, max_tokens: int = 40) -> str:
    words = text.split()
    return " ".join(words[: max_tokens * 2])[: max_tokens * 8]


def decision_ledger(decisions: list[str]) -> ContextItem:
    """Numbered one-liners; append-only so nothing is misremembered."""
    body = "\n".join(f"{i+1}. {d}" for i, d in enumerate(decisions)) or "(none yet)"
    return ContextItem("decisions", body, pinned=True)
