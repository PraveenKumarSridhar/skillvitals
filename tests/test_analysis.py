from datetime import UTC, datetime

from skillvitals.analysis import compute_vitals, dormant_token_cost, find_dormant
from skillvitals.models import Fire, FireKind, Health, Skill

NOW = datetime(2026, 5, 25, tzinfo=UTC)


def mk_skill(name, tokens=3000):
    return Skill(name=name, description="d", path=f"/{name}", source="user", plugin=None,
                 context_tokens=tokens, quality_score=50, quality_breakdown={}, frontmatter_valid=True)


def fire(name, day, kind=FireKind.ATTRIBUTION, sid="s1"):
    return Fire(skill_id=name, name=name, plugin=None, kind=kind,
                timestamp=datetime(2026, 5, day, tzinfo=UTC), session_id=sid)


def test_health_classification_all_states():
    skills = [mk_skill("healthy"), mk_skill("dorm"), mk_skill("misfire"), mk_skill("never")]
    fires = [
        # healthy: invoked + lots of engagement, all in-window
        fire("healthy", 20, FireKind.INVOKE),
        *[fire("healthy", 21) for _ in range(5)],
        # dormant: activity, but all before the 14d window (window starts 05-11)
        fire("dorm", 1, FireKind.INVOKE),
        fire("dorm", 2),
        # misfiring: invoked in-window but almost no follow-through
        fire("misfire", 20, FireKind.INVOKE),
        fire("misfire", 20),
        # never: no fires at all
        # orphan: fires for a skill not in the registry
        fire("ghost", 22, FireKind.INVOKE),
    ]
    v = {x.name: x for x in compute_vitals(skills, fires, window_days=14, now=NOW)}

    assert v["healthy"].health == Health.HEALTHY
    assert v["healthy"].engagement_ratio == 5.0
    assert v["dorm"].health == Health.DORMANT
    assert v["dorm"].days_dormant == 23
    assert v["misfire"].health == Health.MISFIRING
    assert v["never"].health == Health.NEVER_FIRED
    assert v["never"].days_dormant is None
    assert v["ghost"].health == Health.ORPHAN
    assert v["ghost"].skill is None


def test_counts_and_context_cost():
    skills = [mk_skill("a", tokens=4200)]
    fires = [fire("a", 20, FireKind.INVOKE), fire("a", 21), fire("a", 22, sid="s2")]
    v = compute_vitals(skills, fires, window_days=14, now=NOW)[0]
    assert v.invoke_count == 1
    assert v.attribution_count == 2
    assert v.context_tokens == 4200
    assert v.tokens_per_fire == 4200
    assert v.sessions == 2
    assert v.last_fired == datetime(2026, 5, 22, tzinfo=UTC)


def test_find_dormant_and_token_cost():
    skills = [mk_skill("live", 1000), mk_skill("dead", 5000), mk_skill("never", 2000)]
    fires = [fire("live", 24, FireKind.INVOKE), fire("dead", 1, FireKind.INVOKE)]
    vitals = compute_vitals(skills, fires, window_days=14, now=NOW)

    dead = find_dormant(vitals, days=14, now=NOW)
    names = {v.name for v in dead}
    assert "dead" in names  # last fired 05-01, > 14 days
    assert "never" in names  # never fired counts as dead weight
    assert "live" not in names
    # sorted by context cost descending
    assert dead[0].context_tokens >= dead[-1].context_tokens
    assert dormant_token_cost(vitals, days=14, now=NOW) == 5000 + 2000
