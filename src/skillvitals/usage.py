"""Read Claude Code's native per-skill usage ledger from ~/.claude.json.

An authoritative second source for invocation count + last-used. Joined on the
bare (normalized) skill name; when both a namespaced and a bare id exist for the
same skill we keep the larger count and the later timestamp.
"""

from __future__ import annotations

import json
from pathlib import Path

from .models import SkillUsage, normalize_name


def read_skill_usage(claude_home: Path) -> dict[str, SkillUsage]:
    path = Path(claude_home).parent / ".claude.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    raw = data.get("skillUsage")
    if not isinstance(raw, dict):
        return {}
    out: dict[str, SkillUsage] = {}
    for sid, rec in raw.items():
        if not isinstance(rec, dict):
            continue
        name = normalize_name(sid)
        count = int(rec.get("usageCount") or 0)
        last = rec.get("lastUsedAt")
        last = int(last) if isinstance(last, (int, float)) else None
        prev = out.get(name)
        if prev is None:
            out[name] = SkillUsage(count, last)
        else:
            times = [t for t in (prev.last_used_ms, last) if t is not None]
            out[name] = SkillUsage(
                max(prev.usage_count, count),
                max(times) if times else None,
            )
    return out
