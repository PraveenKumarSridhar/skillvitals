"""Lightweight hook-coverage detection.

The ecosystem's answer to low skill activation is a UserPromptSubmit hook that
forces skill evaluation (skills-hook, claude-skills-supercharged, etc.).
skillvitals doesn't generate hooks (explicit non-goal) — it just reports whether
one is configured, so a dormant skill's diagnosis can say "no activation hook is
helping it fire."

We read ``settings.json`` / ``settings.local.json`` from the .claude dir and the
project dir, and look for a UserPromptSubmit hook. This is a global signal, not
per-skill — we deliberately don't claim more precision than we can defend.
"""

from __future__ import annotations

import json
from pathlib import Path


def _load_settings(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def detect_skill_hook(claude_home: Path, cwd: Path | None = None) -> dict:
    """Return {'has_prompt_hook': bool, 'sources': [paths], 'mentions_skill': bool}."""
    candidates = [
        claude_home / "settings.json",
        claude_home / "settings.local.json",
    ]
    if cwd:
        candidates += [cwd / ".claude" / "settings.json", cwd / ".claude" / "settings.local.json"]

    has_hook = False
    mentions_skill = False
    sources: list[str] = []
    for path in candidates:
        if not path.exists():
            continue
        data = _load_settings(path)
        hooks = data.get("hooks") or {}
        if "UserPromptSubmit" in hooks and hooks["UserPromptSubmit"]:
            has_hook = True
            sources.append(str(path))
            if "skill" in json.dumps(hooks["UserPromptSubmit"]).lower():
                mentions_skill = True
    return {"has_prompt_hook": has_hook, "sources": sources, "mentions_skill": mentions_skill}
