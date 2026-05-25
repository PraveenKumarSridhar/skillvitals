"""Prescription engine — show, don't apply (v1).

A rule-based first pass flags concrete problems (short description, no trigger
words, invalid frontmatter, redundancy, expensive dormancy). An optional
LLM-backed pass rewrites a description, gated behind an explicit client/flag so
the default path never spends tokens or touches the network.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

from .models import Health, Prescription, Severity, Skill, SkillVitals

MIN_DESC_LEN = 40
TRIGGER_RE = re.compile(r"\b(use when|when the user|when you|trigger)\b", re.I)
REDUNDANCY_THRESHOLD = 0.6
DORMANT_COST_TOKENS = 3000  # dormant skills above this are worth a callout
_WORD_RE = re.compile(r"[a-z0-9]+")


def _words(text: str) -> set[str]:
    return set(_WORD_RE.findall((text or "").lower()))


def jaccard(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def _skill_rules(v: SkillVitals, now: datetime) -> list[Prescription]:
    out: list[Prescription] = []
    s = v.skill
    if s is None:
        out.append(Prescription(
            v.name, "orphan", Severity.WARN,
            "Appears in session logs but is not installed (renamed or removed). "
            "Re-install it or ignore.",
        ))
        return out

    if not s.frontmatter_valid:
        out.append(Prescription(
            s.name, "invalid-frontmatter", Severity.CRITICAL,
            "SKILL.md frontmatter is missing or unparseable — the skill may never "
            "auto-activate. Add a YAML block with `name:` and `description:`.",
        ))

    desc = (s.description or "").strip()
    if len(desc) < MIN_DESC_LEN:
        out.append(Prescription(
            s.name, "description-too-short", Severity.WARN,
            f"Description is {len(desc)} chars — too thin for reliable activation. "
            "Describe the situations that should trigger it.",
        ))
    elif not TRIGGER_RE.search(desc):
        out.append(Prescription(
            s.name, "no-trigger-words", Severity.WARN,
            "Description has no trigger phrasing ('Use when…', 'when the user…'). "
            "Activation relies on the model matching intent — make it explicit.",
        ))

    if s.quality_score < 40 and s.frontmatter_valid:
        out.append(Prescription(
            s.name, "low-quality", Severity.INFO,
            f"Description quality score is {s.quality_score}/100. "
            "Add specifics: concrete nouns, examples, the triggering situation.",
        ))

    if v.health == Health.MISFIRING:
        out.append(Prescription(
            s.name, "misfiring", Severity.WARN,
            f"Invoked {v.invoke_count}× but barely used afterward "
            f"(engagement {v.engagement_ratio:.1f}). The description may match prompts "
            "it shouldn't — tighten it to the cases it actually handles.",
        ))

    if v.health in (Health.DORMANT, Health.NEVER_FIRED) and v.context_tokens >= DORMANT_COST_TOKENS:
        age = "never fired" if v.days_dormant is None else f"dormant {v.days_dormant}d"
        out.append(Prescription(
            s.name, "dormant-cost", Severity.WARN,
            f"{age.capitalize()} but costs ~{v.context_tokens} ctx tokens every session. "
            "Improve its description so it activates, or remove it to reclaim the budget.",
        ))
    return out


def _redundancy(vitals: list[SkillVitals]) -> list[Prescription]:
    out: list[Prescription] = []
    installed = [v for v in vitals if v.skill and v.skill.description]
    seen: set[tuple[str, str]] = set()
    for i, a in enumerate(installed):
        for b in installed[i + 1:]:
            sim = jaccard(a.skill.description, b.skill.description)
            if sim >= REDUNDANCY_THRESHOLD:
                key = tuple(sorted((a.name, b.name)))
                if key in seen:
                    continue
                seen.add(key)
                # flag the less-used / more-expensive of the pair
                loser = a if (a.attribution_count, -a.context_tokens) <= (
                    b.attribution_count, -b.context_tokens) else b
                other = b if loser is a else a
                out.append(Prescription(
                    loser.name, "redundant", Severity.INFO,
                    f"Description is {sim:.0%} similar to '{other.name}'. "
                    "Consider merging or renaming to avoid activation ambiguity.",
                ))
    return out


def prescribe(vitals: list[SkillVitals], *, now: datetime | None = None) -> list[Prescription]:
    """Return all prescriptions across the given vitals (rule-based)."""
    now = now or datetime.now(timezone.utc)
    out: list[Prescription] = []
    for v in vitals:
        out.extend(_skill_rules(v, now))
    out.extend(_redundancy(vitals))
    return out


_REWRITE_PROMPT = (
    "You are improving a Claude Code skill's `description` frontmatter field, which "
    "controls when the skill auto-activates. Rewrite it to start with 'Use when…', "
    "name concrete triggering situations, and stay under 500 characters. Return ONLY "
    "the new description text.\n\nSkill name: {name}\nCurrent description: {desc}"
)


def rewrite_description(skill: Skill, *, client=None, model: str = "claude-haiku-4-5-20251001"):
    """LLM-backed description rewrite. Opt-in: returns None when no client is given.

    `client` is an anthropic.Anthropic-compatible object. Injected in tests.
    """
    if client is None:
        return None
    resp = client.messages.create(
        model=model,
        max_tokens=400,
        messages=[{
            "role": "user",
            "content": _REWRITE_PROMPT.format(name=skill.name, desc=skill.description or "(empty)"),
        }],
    )
    return resp.content[0].text.strip()
