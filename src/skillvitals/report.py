"""Terminal-rendered reports.

`render_markdown` produces the portable text report (also what the MCP tools
return). `build_rich_table` produces a colored Rich table for the CLI. Both
read the same `SkillVitals` list, so they never disagree.
"""

from __future__ import annotations

from datetime import UTC, datetime

from .analysis import dormant_on_activation_cost, dormant_token_cost, find_dormant
from .models import Health, SkillVitals
from .tokens import humanize

_STATUS_LABEL = {
    Health.HEALTHY: "✅ healthy",
    Health.DORMANT: "⚠️  dormant",
    Health.MISFIRING: "⚠️  misfiring",
    Health.NEVER_FIRED: "💤 never-fired",
    Health.ORPHAN: "❓ orphan",
    Health.DISABLED: "🚫 disabled",
}


def humanize_age(days: int | None) -> str:
    if days is None:
        return "never"
    if days <= 0:
        return "today"
    return f"{days}d ago"


def _sort_key(v: SkillVitals):
    # active skills first (by engagement), then by context cost (bloat) descending
    order = {
        Health.HEALTHY: 0, Health.MISFIRING: 1, Health.DORMANT: 2,
        Health.NEVER_FIRED: 3, Health.DISABLED: 4, Health.ORPHAN: 5,
    }
    return (order[v.health], -v.attribution_count, -v.on_activation_tokens)


def render_markdown(
    vitals: list[SkillVitals],
    *,
    now: datetime | None = None,
    dormant_days: int = 14,
) -> str:
    now = now or datetime.now(UTC)
    rows = sorted(vitals, key=_sort_key)
    lines = [
        f"## skillvitals — {len(vitals)} skills scanned",
        "",
        "| skill | fires | engaged | always-on | on-fire | last seen | status |",
        "|-------|-------|---------|-----------|---------|-----------|--------|",
    ]
    for v in rows:
        lines.append(
            f"| {v.name} | {v.invoke_count} | {v.attribution_count} | "
            f"{humanize(v.always_on_tokens)} | {humanize(v.on_activation_tokens)} | "
            f"{humanize_age(v.days_dormant)} | {_STATUS_LABEL[v.health]} |"
        )

    dead = find_dormant(vitals, days=dormant_days, now=now)
    always = dormant_token_cost(vitals, days=dormant_days, now=now)
    onfire = dormant_on_activation_cost(vitals, days=dormant_days, now=now)
    lines += [
        "",
        f"**{len(dead)} dormant/never-fired skills add ~{humanize(always)} tokens of "
        f"always-loaded descriptions per session.** Their bodies (~{humanize(onfire)} "
        "tokens) load only when they activate.",
        "Run `skillvitals prescribe` for fixes.",
    ]
    return "\n".join(lines)


def build_rich_table(vitals: list[SkillVitals]):
    """Build a Rich Table (imported lazily so the core has no hard Rich dep)."""
    from rich.table import Table

    _color = {
        Health.HEALTHY: "green", Health.DORMANT: "yellow", Health.MISFIRING: "yellow",
        Health.NEVER_FIRED: "dim", Health.ORPHAN: "red", Health.DISABLED: "red",
    }
    table = Table(title="skillvitals", header_style="bold cyan")
    table.add_column("skill")
    table.add_column("fires", justify="right")
    table.add_column("engaged", justify="right")
    # "on-fire" = body tokens, loaded only when the skill activates (not a per-session
    # cost). Named explicitly so the column isn't mistaken for an always-on tax.
    table.add_column("on-fire", justify="right")
    table.add_column("last seen")
    table.add_column("status")
    for v in sorted(vitals, key=_sort_key):
        c = _color[v.health]
        table.add_row(
            v.name, str(v.invoke_count), str(v.attribution_count),
            humanize(v.on_activation_tokens), humanize_age(v.days_dormant),
            f"[{c}]{_STATUS_LABEL[v.health]}[/{c}]",
        )
    return table


def summary_line(vitals: list[SkillVitals], *, dormant_days: int = 14,
                 now: datetime | None = None) -> str:
    now = now or datetime.now(UTC)
    dead = find_dormant(vitals, days=dormant_days, now=now)
    always = dormant_token_cost(vitals, days=dormant_days, now=now)
    onfire = dormant_on_activation_cost(vitals, days=dormant_days, now=now)
    return (
        f"{len(dead)} dormant/never-fired skills add ~{humanize(always)} tokens of "
        f"always-loaded descriptions per session ({humanize(onfire)} more load only "
        "when they activate)."
    )
