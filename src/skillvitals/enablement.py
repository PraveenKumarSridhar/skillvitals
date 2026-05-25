"""Read Claude Code's plugin enable-state and map skills to plugins.

Enable/disable is per-plugin, keyed 'plugin@marketplace' in settings.json's
`enabledPlugins`. A skill is disabled when its owning plugin is present and
False, enabled when present and True, and unknown (None) when we cannot resolve
it. We never guess 'disabled' (PRD risk R1): a falsely-disabled enabled skill
would be worse than an unknown.
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .models import Skill


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _settings_files(claude_home: Path, cwd: Path | None) -> list[Path]:
    files = [claude_home / "settings.json", claude_home / "settings.local.json"]
    if cwd:
        files += [cwd / ".claude" / "settings.json", cwd / ".claude" / "settings.local.json"]
    return files


def read_enabled_plugins(claude_home: Path, cwd: Path | None = None) -> dict[str, bool]:
    """Merged {'plugin@marketplace': bool}; project settings override user."""
    merged: dict[str, bool] = {}
    for f in _settings_files(claude_home, cwd):
        ep = _load(f).get("enabledPlugins")
        if isinstance(ep, dict):
            merged.update({k: bool(v) for k, v in ep.items()})
    return merged


def read_marketplaces(claude_home: Path, cwd: Path | None = None) -> dict[str, str]:
    """marketplace name -> source directory path (best effort)."""
    out: dict[str, str] = {}
    for f in _settings_files(claude_home, cwd):
        mk = _load(f).get("extraKnownMarketplaces")
        if isinstance(mk, dict):
            for name, spec in mk.items():
                path = ((spec or {}).get("source") or {}).get("path")
                if path:
                    out[name] = str(path)
    return out


def _plugin_ref(skill: Skill, marketplaces: dict[str, str]) -> str | None:
    parts = Path(skill.path).parts
    if "cache" in parts and "plugins" in parts:
        i = parts.index("cache")
        if len(parts) > i + 2:
            marketplace, plugin = parts[i + 1], parts[i + 2]
            return f"{plugin}@{marketplace}"
    # user-dir skill: match against a known marketplace whose path contains it
    sp = Path(skill.path)
    for name, mpath in marketplaces.items():
        mp = Path(mpath)
        try:
            rel = sp.relative_to(mp)
        except ValueError:
            continue
        if rel.parts:
            return f"{rel.parts[0]}@{name}"
    return None


def annotate_enablement(
    skills: list[Skill], claude_home: Path, cwd: Path | None = None
) -> list[Skill]:
    """Return new Skills with `plugin_ref` + `enabled` resolved from settings."""
    enabled_map = read_enabled_plugins(claude_home, cwd)
    marketplaces = read_marketplaces(claude_home, cwd)
    out: list[Skill] = []
    for s in skills:
        ref = _plugin_ref(s, marketplaces)
        enabled = enabled_map.get(ref) if ref is not None else None
        out.append(replace(s, plugin_ref=ref, enabled=enabled))
    return out
