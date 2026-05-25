"""Skill registry scanner.

Discovers every ``SKILL.md`` across the configured roots, parses YAML
frontmatter, estimates context cost, scores description quality, and dedupes
skills that appear in more than one location (very common — the same skill
exists in both a user dir and the plugin cache).
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from pathlib import Path
from typing import NamedTuple, Union

import yaml

from .models import Skill
from .tokens import estimate_tokens


class ScanRoot(NamedTuple):
    """A directory to scan, tagged with the source label its skills get."""

    path: Path
    source: str  # 'user' | 'project' | 'plugin'


RootLike = Union[ScanRoot, "tuple[Path, str]", Path]

_FRONTMATTER_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n?", re.S)

# Trigger phrasing that correlates with reliable auto-activation.
_TRIGGER_PATTERNS = [
    r"\buse when\b",
    r"\bwhen the user\b",
    r"\bwhen you\b",
    r"\btrigger\b",
]


_KV_RE = re.compile(r"^(name|description|when_to_use|license|version)\s*:\s*(.*)$", re.M)


def _regex_frontmatter(block: str) -> dict:
    """Lenient single-line key extraction. Real SKILL.md descriptions often
    contain ': ' (e.g. quoted examples), which strict YAML rejects — so we
    fall back to grabbing everything after the first colon on each key line."""
    out: dict[str, str] = {}
    for key, val in _KV_RE.findall(block):
        out[key] = val.strip().strip("'\"")
    return out


def parse_frontmatter(text: str) -> tuple[dict, bool]:
    """Return (frontmatter dict, valid).

    Tries strict YAML first; on failure (or when it yields no usable keys),
    falls back to lenient line-based extraction. ``valid`` means a frontmatter
    fence was present and we recovered at least a name or description.
    """
    m = _FRONTMATTER_RE.match(text)
    if not m:
        return {}, False
    block = m.group(1)
    data: dict = {}
    try:
        loaded = yaml.safe_load(block)
        if isinstance(loaded, dict):
            data = {k: v for k, v in loaded.items() if v is not None}
    except yaml.YAMLError:
        data = {}
    if not data.get("name") and not data.get("description"):
        data = {**_regex_frontmatter(block), **data}
    valid = bool(data.get("name") or data.get("description"))
    return data, valid


def quality_score(description: str, *, has_name: bool, valid: bool) -> dict[str, int]:
    """Score a description 0-100. Returns component breakdown plus 'total'.

    Components (documented in the PRD's spirit — length, triggers, specificity):
      - length band   (40): ideal 80-600 chars
      - trigger words  (25): 'use when', 'when the user', ...
      - specificity    (20): digits, parentheses, examples, multiple clauses
      - structure      (15): valid frontmatter + has a name
    """
    desc = (description or "").strip()
    n = len(desc)

    if n == 0:
        length = 0
    elif n < 40:
        length = 12
    elif n < 80:
        length = 26
    elif n <= 600:
        length = 40
    elif n <= 1000:
        length = 30
    else:
        length = 18

    low = desc.lower()
    trigger = 25 if any(re.search(p, low) for p in _TRIGGER_PATTERNS) else 0

    specificity = 0
    if re.search(r"\d", desc):
        specificity += 6
    if "(" in desc and ")" in desc:
        specificity += 6
    if re.search(r"\b(e\.g\.|such as|like|example)\b", low):
        specificity += 4
    if desc.count(",") >= 2:
        specificity += 4
    specificity = min(specificity, 20)

    structure = (8 if valid else 0) + (7 if has_name else 0)

    total = length + trigger + specificity + structure
    return {
        "length": length,
        "trigger": trigger,
        "specificity": specificity,
        "structure": structure,
        "total": min(total, 100),
    }


def _classify_path(path: Path, default_source: str) -> tuple[str, str | None]:
    """Return (source, plugin). Plugin-cache files always classify as 'plugin'
    regardless of the root's default label; everything else keeps the default."""
    parts = path.parts
    if "cache" in parts and "plugins" in parts:
        # .../plugins/cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md
        try:
            i = parts.index("cache")
            plugin = parts[i + 2] if len(parts) > i + 2 else None
        except ValueError:
            plugin = None
        return "plugin", plugin
    return default_source, None


def _scan_root(root: ScanRoot) -> list[Skill]:
    if not root.path.exists():
        return []
    skills: list[Skill] = []
    for md in sorted(root.path.rglob("SKILL.md")):
        try:
            text = md.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        fm, valid = parse_frontmatter(text)
        name = (fm.get("name") or "").strip() if valid else ""
        if not name:
            # fall back to the skill's directory name
            name = md.parent.name
        description = (fm.get("description") or "").strip() if valid else ""
        source, plugin = _classify_path(md, root.source)
        q = quality_score(description, has_name=bool(fm.get("name")), valid=valid)
        skills.append(
            Skill(
                name=name,
                description=description,
                path=str(md),
                source=source,
                plugin=plugin,
                context_tokens=estimate_tokens(text),
                quality_score=q["total"],
                quality_breakdown=q,
                frontmatter_valid=valid,
                description_tokens=estimate_tokens(description),
            )
        )
    return skills


def _dedupe(skills: list[Skill]) -> list[Skill]:
    """Keep one Skill per name: the largest copy (most complete), then shortest path."""
    best: dict[str, Skill] = {}
    for s in skills:
        cur = best.get(s.name)
        if cur is None:
            best[s.name] = s
            continue
        if (s.context_tokens, -len(s.path)) > (cur.context_tokens, -len(cur.path)):
            best[s.name] = s
    return sorted(best.values(), key=lambda s: s.name)


def _coerce_root(r: RootLike) -> ScanRoot:
    if isinstance(r, ScanRoot):
        return r
    if isinstance(r, tuple):
        path, source = r
        return ScanRoot(Path(path), source)
    return ScanRoot(Path(r), "user")  # bare path defaults to user source


def scan_skills(roots: Sequence[RootLike]) -> list[Skill]:
    """Scan all roots, returning a deduped, name-sorted list of skills.

    Each root may be a ``ScanRoot``, a ``(path, source)`` tuple, or a bare path
    (which defaults to source='user'). Plugin-cache files are always tagged
    'plugin' regardless of the root label.
    """
    found: list[Skill] = []
    for r in roots:
        found.extend(_scan_root(_coerce_root(r)))
    return _dedupe(found)
