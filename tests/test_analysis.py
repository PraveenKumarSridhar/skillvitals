from datetime import UTC, datetime

from skillvitals.analysis import compute_vitals, dormant_token_cost, find_dormant
from skillvitals.models import Fire, FireKind, Health, Skill

NOW = datetime(2026, 5, 25, tzinfo=UTC)


def mk_skill(name, tokens=3000):
    # description_tokens (always-on) is a fraction of the body (on-activation)
    return Skill(name=name, description="d", path=f"/{name}", source="user", plugin=None,
                 context_tokens=tokens, quality_score=50, quality_breakdown={},
                 frontmatter_valid=True, description_tokens=tokens // 50)


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
    # sorted by always-on (description) cost descending
    assert dead[0].always_on_tokens >= dead[-1].always_on_tokens
    # honest per-session cost is the always-on (description) tokens, not bodies
    assert dormant_token_cost(vitals, days=14, now=NOW) == (5000 // 50) + (2000 // 50)


from skillvitals.models import Health as _Health, SkillUsage as _SkillUsage
from dataclasses import replace as _replace


def test_disabled_overrides_healthy():
    s = _replace(mk_skill("off"), enabled=False, description_tokens=100)
    fires = [fire("off", 24, FireKind.INVOKE), *[fire("off", 24) for _ in range(5)]]
    v = compute_vitals([s], fires, window_days=14, now=NOW)[0]
    assert v.health == _Health.DISABLED
    assert v.enabled is False


def test_token_split_and_dormant_cost_uses_always_on():
    s = _replace(mk_skill("dead", tokens=5000), description_tokens=120, enabled=True)
    vitals = compute_vitals([s], [], window_days=14, now=NOW)
    v = vitals[0]
    assert v.always_on_tokens == 120
    assert v.on_activation_tokens == 5000
    assert dormant_token_cost(vitals, days=14, now=NOW) == 120  # not the body


def test_native_usage_reconciliation():
    s = _replace(mk_skill("docx"), enabled=True)
    usage = {"docx": _SkillUsage(usage_count=9, last_used_ms=int(NOW.timestamp() * 1000))}
    v = compute_vitals([s], [fire("docx", 20, FireKind.INVOKE)], window_days=14,
                       now=NOW, usage=usage)[0]
    assert v.invoke_count == 9       # max(jsonl=1, native=9)
    assert v.native_usage_count == 9
    assert v.source_discrepancy is not None


def test_disabled_excluded_from_dormant():
    s = _replace(mk_skill("off", tokens=4000), enabled=False, description_tokens=90)
    vitals = compute_vitals([s], [], window_days=14, now=NOW)
    assert dormant_token_cost(vitals, days=14, now=NOW) == 0
