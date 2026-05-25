"""skillvitals MCP server.

Exposes skill observability as MCP tools so you can ask Claude Code things like
"which of my skills are dormant?" and get a real answer from your own logs.

Run with:  skillvitals serve     (or)   uvx skillvitals serve
Tools return markdown text.
"""

from __future__ import annotations

from datetime import UTC, datetime

from fastmcp import FastMCP

from .analysis import dormant_on_activation_cost, dormant_token_cost, find_dormant
from .dashboard import write_dashboard
from .pipeline import collect
from .prescribe import prescribe as run_prescribe
from .registry import scan_skills
from .report import humanize_age, render_markdown
from .testharness import synth_prompts
from .tokens import humanize

mcp = FastMCP("skillvitals")


@mcp.tool
def vitals_scan(days: int = 14) -> str:
    """Scan all installed Claude Code skills and report, per skill: fire count,
    engagement, context-token cost, last-seen, and health status
    (healthy / dormant / misfiring / never-fired). The headline diagnostic."""
    now = datetime.now(UTC)
    snap = collect(window_days=days, now=now)
    return render_markdown(snap.vitals, now=now, dormant_days=days)


@mcp.tool
def vitals_history(days: int = 30) -> str:
    """Per-skill activation history from session logs: how many times each skill
    was invoked vs. engaged, across how many sessions, and when it last fired."""
    now = datetime.now(UTC)
    snap = collect(window_days=days, now=now)
    lines = ["| skill | invokes | engaged | sessions | last seen |",
             "|-------|---------|---------|----------|-----------|"]
    for v in sorted(snap.vitals, key=lambda v: (-v.attribution_count, -v.invoke_count)):
        lines.append(f"| {v.name} | {v.invoke_count} | {v.attribution_count} | "
                     f"{v.sessions} | {humanize_age(v.days_dormant)} |")
    return "\n".join(lines)


@mcp.tool
def vitals_dormancy(days: int = 14) -> str:
    """List skills inactive for >= `days`. Skills load progressively, so the
    standing per-session cost is each skill's always-loaded description; its body
    loads only when it activates. Both are shown."""
    now = datetime.now(UTC)
    snap = collect(window_days=days, now=now)
    dead = find_dormant(snap.vitals, days=days, now=now)
    always = dormant_token_cost(snap.vitals, days=days, now=now)
    onfire = dormant_on_activation_cost(snap.vitals, days=days, now=now)
    lines = [f"## {len(dead)} dormant skills (inactive ≥ {days}d)", "",
             "| skill | always-on | on-fire | last seen |",
             "|-------|-----------|---------|-----------|"]
    for v in dead:
        last = "never" if v.days_dormant is None else f"{v.days_dormant}d ago"
        lines.append(f"| {v.name} | {humanize(v.always_on_tokens)} | "
                     f"{humanize(v.on_activation_tokens)} | {last} |")
    lines += ["", f"**{humanize(always)} tokens of always-loaded descriptions ride along every "
              f"session.** Another {humanize(onfire)} tokens (their bodies) load only on activation."]
    return "\n".join(lines)


@mcp.tool
def vitals_report(days: int = 14) -> str:
    """Full terminal-style markdown report: the scan table plus the dormant
    token-cost summary and a pointer to prescriptions."""
    now = datetime.now(UTC)
    snap = collect(window_days=days, now=now)
    return render_markdown(snap.vitals, now=now, dormant_days=days)


@mcp.tool
def vitals_prescribe(days: int = 14) -> str:
    """Suggest concrete fixes for problematic skills: expand thin descriptions,
    add trigger phrasing, fix invalid frontmatter, flag redundant or expensive
    dormant skills. Show, don't apply."""
    now = datetime.now(UTC)
    snap = collect(window_days=days, now=now)
    rx = run_prescribe(snap.vitals, now=now)
    if not rx:
        return "No prescriptions — your skills look healthy."
    lines = [f"## {len(rx)} prescriptions", ""]
    for p in rx:
        lines.append(f"- **[{p.severity.value}] {p.skill_name}** — {p.rule}: {p.message}")
    return "\n".join(lines)


@mcp.tool
def vitals_test(skill: str, n: int = 10) -> str:
    """Generate a synthetic activation-test prompt battery for a skill from its
    description (dry run — does not spawn Claude Code or spend tokens). Use the
    `skillvitals test --live` CLI command to measure real activation."""
    snap = collect(persist=False)
    skills = {s.name: s for s in snap.skills}
    if skill not in skills:
        return f"Skill '{skill}' not found. Available: {', '.join(sorted(skills))}"
    prompts = synth_prompts(skills[skill].description, n=n)
    body = "\n".join(f"{i}. {p}" for i, p in enumerate(prompts, 1))
    return f"## {len(prompts)} synthetic test prompts for `{skill}`\n\n{body}"


@mcp.tool
def vitals_dashboard(days: int = 14) -> str:
    """Render the self-contained HTML dashboard to ~/.skillvitals/dashboard.html
    and return its path."""
    now = datetime.now(UTC)
    snap = collect(window_days=days, now=now)
    rx = run_prescribe(snap.vitals, now=now)
    path = write_dashboard(snap.vitals, snap.config.dashboard_path,
                           now=now, dormant_days=days, prescriptions=rx)
    return f"Dashboard written to {path}"


def _scan_only():  # tiny helper to keep imports used / aid debugging
    return scan_skills([])


if __name__ == "__main__":
    mcp.run()
