"""Analysis engine: join registry skills with fire history into SkillVitals.

This is where the health model lives. Definitions (documented for honesty —
these are heuristics, not ground truth):

  never-fired : zero lifetime activations.
  dormant     : has activated before, but not within the window.
  misfiring   : activated in-window, explicitly invoked, but with low
                follow-through (engagement_ratio < MISFIRE_THRESHOLD) — a proxy
                for wrong-prompt activation (fired, then abandoned).
  healthy     : activated in-window with adequate engagement.
  orphan      : appears in logs but is not installed (uninstalled/renamed).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from .models import Fire, FireKind, Health, Skill, SkillVitals

MISFIRE_THRESHOLD = 2.0  # attribution messages per invoke below this looks like a misfire


def _classify(
    *,
    has_skill: bool,
    total_activity: int,
    window_activity: int,
    invoke_count: int,
    engagement_ratio: float,
) -> Health:
    if not has_skill:
        return Health.ORPHAN
    if total_activity == 0:
        return Health.NEVER_FIRED
    if window_activity == 0:
        return Health.DORMANT
    if invoke_count > 0 and engagement_ratio < MISFIRE_THRESHOLD:
        return Health.MISFIRING
    return Health.HEALTHY


def _tz(fires: list[Fire]):
    for f in fires:
        if f.timestamp and f.timestamp.tzinfo:
            return f.timestamp.tzinfo
    return timezone.utc


def compute_vitals(
    skills: list[Skill],
    fires: list[Fire],
    *,
    window_days: int = 14,
    now: datetime | None = None,
) -> list[SkillVitals]:
    now = now or datetime.now(tz=_tz(fires))
    window_start = now - timedelta(days=window_days)

    by_name: dict[str, list[Fire]] = {}
    for f in fires:
        by_name.setdefault(f.name, []).append(f)

    skill_by_name = {s.name: s for s in skills}
    names = set(skill_by_name) | set(by_name)

    out: list[SkillVitals] = []
    for name in sorted(names):
        skill = skill_by_name.get(name)
        group = by_name.get(name, [])

        invokes = [f for f in group if f.kind == FireKind.INVOKE]
        attrs = [f for f in group if f.kind == FireKind.ATTRIBUTION]
        win = [f for f in group if f.timestamp and f.timestamp >= window_start]
        win_invokes = [f for f in win if f.kind == FireKind.INVOKE]
        win_attrs = [f for f in win if f.kind == FireKind.ATTRIBUTION]

        stamps = [f.timestamp for f in group if f.timestamp]
        last_fired = max(stamps) if stamps else None
        first_fired = min(stamps) if stamps else None
        days_dormant = (now - last_fired).days if last_fired else None

        invoke_count = len(invokes)
        attribution_count = len(attrs)
        engagement_ratio = attribution_count / max(invoke_count, 1)

        context_tokens = skill.context_tokens if skill else 0
        health = _classify(
            has_skill=skill is not None,
            total_activity=len(group),
            window_activity=len(win),
            invoke_count=invoke_count,
            engagement_ratio=engagement_ratio,
        )

        out.append(
            SkillVitals(
                name=name,
                skill=skill,
                invoke_count=invoke_count,
                attribution_count=attribution_count,
                window_invoke_count=len(win_invokes),
                window_attribution_count=len(win_attrs),
                last_fired=last_fired,
                first_fired=first_fired,
                days_dormant=days_dormant,
                context_tokens=context_tokens,
                tokens_per_fire=context_tokens,
                engagement_ratio=engagement_ratio,
                health=health,
                sessions=len({f.session_id for f in group if f.session_id}),
            )
        )
    return out


def _is_dormant_for(v: SkillVitals, days: int, now: datetime) -> bool:
    """True if the skill has not activated within `days` (never-fired counts)."""
    if v.health == Health.ORPHAN:
        return False
    if v.last_fired is None:
        return True
    return (now - v.last_fired).days >= days


def find_dormant(
    vitals: list[SkillVitals], *, days: int = 14, now: datetime | None = None
) -> list[SkillVitals]:
    """Skills inactive for >= `days`, sorted by context cost (most expensive first)."""
    now = now or datetime.now(timezone.utc)
    dead = [v for v in vitals if _is_dormant_for(v, days, now)]
    return sorted(dead, key=lambda v: v.context_tokens, reverse=True)


def dormant_token_cost(
    vitals: list[SkillVitals], *, days: int = 14, now: datetime | None = None
) -> int:
    """Total context tokens loaded every session by dormant skills — the viral number."""
    return sum(v.context_tokens for v in find_dormant(vitals, days=days, now=now))
