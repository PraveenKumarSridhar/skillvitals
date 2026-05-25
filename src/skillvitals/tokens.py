"""Token estimation and human-friendly formatting.

We deliberately avoid a tokenizer dependency. A skill's context cost is the
size of its loaded ``SKILL.md``; the ~4-chars-per-token heuristic is accurate
enough to rank skills by bloat, which is all the product needs.
"""

from __future__ import annotations

import math

CHARS_PER_TOKEN = 4


def estimate_tokens(text: str) -> int:
    """Estimate token count from character length (4 chars/token, rounded up)."""
    if not text:
        return 0
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def humanize(n: int) -> str:
    """Format a token count compactly: 950 -> '950', 2100 -> '2.1k'."""
    if n < 1000:
        return str(n)
    return f"{n / 1000:.1f}k"
