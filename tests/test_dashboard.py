import re
from datetime import UTC, datetime

from skillvitals.analysis import compute_vitals
from skillvitals.dashboard import render_dashboard
from skillvitals.models import Fire, FireKind, Skill

NOW = datetime(2026, 5, 25, tzinfo=UTC)


def _vitals():
    skills = [
        Skill("docx", "Use when editing Word docs", "/d", "user", None, 2100, 80, {}, True),
        Skill("data-analysis", "old", "/da", "user", None, 4200, 30, {}, True),
    ]
    fires = [Fire("docx", "docx", None, FireKind.INVOKE, NOW, "s1")]
    return compute_vitals(skills, fires, window_days=14, now=NOW)


def test_dashboard_is_self_contained_html():
    html = render_dashboard(_vitals(), now=NOW, dormant_days=14)
    assert html.lstrip().lower().startswith("<!doctype html")
    assert "<style>" in html  # inline CSS
    # no external resources — fully offline / self-contained
    assert "http://" not in html and "https://" not in html
    assert "cdn" not in html.lower()
    assert "<link" not in html.lower()


def test_dashboard_has_row_per_skill_and_viral_number():
    html = render_dashboard(_vitals(), now=NOW, dormant_days=14)
    assert "docx" in html and "data-analysis" in html
    # one <tr> in the body per skill (plus header row)
    body_rows = re.findall(r'<tr[^>]*class="skill-row"', html)
    assert len(body_rows) == 2
    assert "4.2k" in html  # dormant token cost (data-analysis is dead weight)


def test_dashboard_is_sortable():
    html = render_dashboard(_vitals(), now=NOW, dormant_days=14)
    # vanilla-JS sortable: clickable headers wired up, no framework
    assert "sortTable" in html or "data-sort" in html
