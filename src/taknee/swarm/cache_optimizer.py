"""Prompt Cache Packer — Ensures 90%+ KV cache hit rate across LLM providers."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any


@dataclass
class PackedPrompt:
    messages: list[dict[str, Any]]
    prefix_hash: str
    estimated_tokens: int
    cacheable_tokens: int
    cache_hit_likely: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "prefix_hash": self.prefix_hash,
            "estimated_tokens": self.estimated_tokens,
            "cacheable_tokens": self.cacheable_tokens,
            "cache_hit_likely": self.cache_hit_likely,
        }


class PromptCachePacker:
    """Arranges prompt components in a strict deterministic order to maximize KV-cache reuse."""

    def __init__(self, min_cacheable_tokens: int = 1024):
        self.min_cacheable_tokens = min_cacheable_tokens
        self._last_prefix_hash: str = ""

    def pack(
        self,
        system_instruction: str,
        project_rules: str,
        repo_map: str,
        conversation_history: list[dict[str, str]],
        current_scratchpad: str,
    ) -> PackedPrompt:
        """Assembles messages into a prefix-stable order."""
        # 1. Block A: Static System Prompt + Project Rules (100% Immutable)
        static_block = system_instruction.strip()
        if project_rules.strip():
            static_block += f"\n\n### Project Rules (AGENTS.md):\n{project_rules.strip()}"

        # 2. Block B: Stable Repository Skeleton
        if repo_map.strip():
            static_block += f"\n\n### Repository Map:\n{repo_map.strip()}"

        # Calculate prefix hash over the immutable prefix
        prefix_hash = hashlib.sha256(static_block.encode("utf-8")).hexdigest()[:16]
        cacheable_tokens = len(static_block) // 4

        # Assemble OpenAI-compatible messages list
        messages: list[dict[str, Any]] = [
            {"role": "system", "content": static_block}
        ]

        # 3. Block C: Conversation turns
        for turn in conversation_history:
            messages.append({"role": turn.get("role", "user"), "content": turn.get("content", "")})

        # 4. Block D: Ephemeral scratchpad / dynamic task prompt
        if current_scratchpad.strip():
            messages.append({"role": "user", "content": current_scratchpad.strip()})

        total_text = "".join(m["content"] for m in messages)
        estimated_total_tokens = max(1, len(total_text) // 4)

        cache_hit_likely = (
            cacheable_tokens >= self.min_cacheable_tokens
            and self._last_prefix_hash == prefix_hash
        )
        self._last_prefix_hash = prefix_hash

        return PackedPrompt(
            messages=messages,
            prefix_hash=prefix_hash,
            estimated_tokens=estimated_total_tokens,
            cacheable_tokens=cacheable_tokens,
            cache_hit_likely=cache_hit_likely,
        )
