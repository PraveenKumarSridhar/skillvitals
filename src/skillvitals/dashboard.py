"""Self-contained HTML dashboard (single file, inline CSS + vanilla JS sort).

No build step, no framework, no external resources — the file works offline and
can be opened straight from disk. Jinja2-rendered from the bundled template.
"""

from __future__ import annotations

from datetime import UTC, datetime

from jinja2 import Environment, PackageLoader, select_autoescape

from .analysis import dormant_token_cost, find_dormant
from .models import Health, Prescription, SkillVitals
from .prescribe import prescribe
from .report import humanize_age
from .tokens import humanize

_STATUS_LABEL = {
    Health.HEALTHY: "healthy", Health.DORMANT: "dormant", Health.MISFIRING: "misfiring",
    Health.NEVER_FIRED: "never-fired", Health.ORPHAN: "orphan",
}

_env = Environment(
    loader=PackageLoader("skillvitals", "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


def _rows(vitals: list[SkillVitals]) -> list[dict]:
    order = {Health.HEALTHY: 0, Health.MISFIRING: 1, Health.DORMANT: 2,
             Health.NEVER_FIRED: 3, Health.ORPHAN: 4}
    rows = []
    for v in sorted(vitals, key=lambda v: (order[v.health], -v.attribution_count, -v.context_tokens)):
        rows.append({
            "name": v.name,
            "fires": v.invoke_count,
            "engaged": v.attribution_count,
            "ctx": v.context_tokens,
            "ctx_h": humanize(v.context_tokens),
            "quality": v.skill.quality_score if v.skill else 0,
            "last_seen": humanize_age(v.days_dormant),
            "age_v": -1 if v.days_dormant is None else v.days_dormant,
            "status_label": _STATUS_LABEL[v.health],
            "status_class": v.health.value,
        })
    return rows


def render_dashboard(
    vitals: list[SkillVitals],
    *,
    now: datetime | None = None,
    dormant_days: int = 14,
    prescriptions: list[Prescription] | None = None,
    generated_at: str | None = None,
) -> str:
    now = now or datetime.now(UTC)
    if prescriptions is None:
        prescriptions = prescribe(vitals, now=now)
    dead = find_dormant(vitals, days=dormant_days, now=now)
    template = _env.get_template("dashboard.html.j2")
    return template.render(
        rows=_rows(vitals),
        prescriptions=[
            {"skill_name": p.skill_name, "severity": p.severity.value, "message": p.message}
            for p in prescriptions
        ],
        total=len(vitals),
        healthy=sum(1 for v in vitals if v.health == Health.HEALTHY),
        dormant_count=len(dead),
        dormant_cost_h=humanize(dormant_token_cost(vitals, days=dormant_days, now=now)),
        generated_at=generated_at or now.strftime("%Y-%m-%d %H:%M UTC"),
    )


def write_dashboard(vitals: list[SkillVitals], path, **kwargs) -> str:
    from pathlib import Path

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    html = render_dashboard(vitals, **kwargs)
    path.write_text(html, encoding="utf-8")
    return str(path)
