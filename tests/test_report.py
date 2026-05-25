from datetime import datetime, timezone

from skillvitals.analysis import compute_vitals
from skillvitals.models import Fire, FireKind, Skill
from skillvitals.report import humanize_age, render_markdown

NOW = datetime(2026, 5, 25, tzinfo=timezone.utc)


def _vitals():
    skills = [
        Skill("active", "Use when X happens with A/B (lift)", "/a", "user", None, 1500, 80, {}, True),
        Skill("dead", "old skill", "/d", "user", None, 4200, 30, {}, True),
    ]
    fires = [
        Fire("active", "active", None, FireKind.INVOKE, datetime(2026, 5, 24, tzinfo=timezone.utc), "s1"),
        Fire("active", "active", None, FireKind.ATTRIBUTION, datetime(2026, 5, 24, tzinfo=timezone.utc), "s1"),
        Fire("dead", "dead", None, FireKind.INVOKE, datetime(2026, 4, 1, tzinfo=timezone.utc), "s0"),
    ]
    return compute_vitals(skills, fires, window_days=14, now=NOW)


def test_render_markdown_has_table_and_viral_line():
    md = render_markdown(_vitals(), now=NOW, dormant_days=14)
    assert "skillvitals" in md
    assert "2 skills" in md
    # table headers
    assert "skill" in md and "ctx" in md.lower() and "status" in md
    # both skills appear
    assert "active" in md and "dead" in md
    # the viral dormant-cost line, with humanized token total (4200 -> 4.2k)
    assert "4.2k" in md
    assert "per session" in md
    assert "prescribe" in md


def test_humanize_age():
    assert humanize_age(None) == "never"
    assert humanize_age(0) == "today"
    assert humanize_age(1) == "1d ago"
    assert humanize_age(23) == "23d ago"
