from dataclasses import replace
from datetime import UTC, datetime

from skillvitals.analysis import compute_vitals
from skillvitals.models import Fire, FireKind, Skill
from skillvitals.report import humanize_age, render_markdown

NOW = datetime(2026, 5, 25, tzinfo=UTC)


def _vitals():
    skills = [
        Skill("active", "Use when X happens with A/B (lift)", "/a", "user", None, 1500, 80, {}, True),
        Skill("dead", "old skill", "/d", "user", None, 4200, 30, {}, True),
    ]
    fires = [
        Fire("active", "active", None, FireKind.INVOKE, datetime(2026, 5, 24, tzinfo=UTC), "s1"),
        Fire("active", "active", None, FireKind.ATTRIBUTION, datetime(2026, 5, 24, tzinfo=UTC), "s1"),
        Fire("dead", "dead", None, FireKind.INVOKE, datetime(2026, 4, 1, tzinfo=UTC), "s0"),
    ]
    return compute_vitals(skills, fires, window_days=14, now=NOW)


def test_render_markdown_has_table_and_viral_line():
    md = render_markdown(_vitals(), now=NOW, dormant_days=14)
    assert "skillvitals" in md
    assert "2 skills" in md
    # table headers (0.2.0: split into always-on vs on-fire)
    assert "skill" in md and "always-on" in md and "on-fire" in md and "status" in md
    # both skills appear
    assert "active" in md and "dead" in md
    # the dead skill's body (4200 -> 4.2k) shows as the on-activation cost
    assert "4.2k" in md
    assert "per session" in md
    assert "prescribe" in md


def test_humanize_age():
    assert humanize_age(None) == "never"
    assert humanize_age(0) == "today"
    assert humanize_age(1) == "1d ago"
    assert humanize_age(23) == "23d ago"


def test_report_splits_tokens_and_honest_headline():
    s = Skill("dead", "Use when X", "/d", "user", None, 4200, 30, {}, True)
    s = replace(s, description_tokens=110, enabled=True)
    fires = [Fire("dead", "dead", None, FireKind.INVOKE,
                  datetime(2026, 4, 1, tzinfo=UTC), "s")]
    vitals = compute_vitals([s], fires, window_days=14, now=NOW)
    md = render_markdown(vitals, now=NOW, dormant_days=14)
    assert "always-on" in md and "on-fire" in md
    assert "per session" in md
    assert "load only when they activate" in md.lower()
