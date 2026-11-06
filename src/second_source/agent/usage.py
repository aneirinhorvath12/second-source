"""Token and cost accounting across a run."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any

# USD per million tokens (input, output), keyed by model ID. Fill these in from
# https://docs.claude.com pricing before quoting a cost per contract; until then
# cost_usd() returns None rather than a made-up number.
PRICES: dict[str, tuple[float, float]] = {}


@dataclass
class Usage:
    tokens: dict[str, list[int]] = field(default_factory=lambda: defaultdict(lambda: [0, 0, 0, 0]))

    def add(self, model: str, usage: Any) -> None:
        t = self.tokens[model]
        t[0] += getattr(usage, "input_tokens", 0) or 0
        t[1] += getattr(usage, "output_tokens", 0) or 0
        t[2] += getattr(usage, "cache_read_input_tokens", 0) or 0
        t[3] += getattr(usage, "cache_creation_input_tokens", 0) or 0

    def cost_usd(self) -> float | None:
        total = 0.0
        for model, (inp, out, cache_read, cache_write) in self.tokens.items():
            if model not in PRICES:
                return None
            p_in, p_out = PRICES[model]
            total += (inp * p_in + out * p_out + cache_read * p_in * 0.1
                      + cache_write * p_in * 1.25) / 1e6
        return total

    def summary(self) -> dict[str, Any]:
        return {"tokens": {m: dict(zip(["input", "output", "cache_read", "cache_write"], v,
                                       strict=True)) for m, v in self.tokens.items()},
                "estimated_cost_usd": self.cost_usd()}

    def reset(self) -> None:
        self.tokens.clear()


USAGE = Usage()
