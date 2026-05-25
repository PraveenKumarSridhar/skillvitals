"""skillvitals command-line interface.

    skillvitals scan         # the headline: fires, ctx cost, health per skill
    skillvitals report       # markdown report (shareable / save with --output)
    skillvitals history      # per-skill activation history
    skillvitals dormancy     # dead-weight skills + token cost
    skillvitals prescribe    # suggested fixes (--rewrite for LLM rewrites)
    skillvitals test         # synthetic activation test (--live to really run)
    skillvitals dashboard    # write the self-contained HTML dashboard
    skillvitals serve        # run as an MCP server (stdio)
"""

from __future__ import annotations

import os
from datetime import UTC, datetime

import click
from rich.console import Console
from rich.table import Table

from . import __version__

console = Console()


def _now(value: str | None) -> datetime:
    if value:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    return datetime.now(UTC)


def _apply_home(claude_home: str | None) -> None:
    if claude_home:
        os.environ["SKILLVITALS_CLAUDE_HOME"] = claude_home


def _collect(window_days: int, now: datetime, persist: bool = True):
    from .pipeline import collect

    return collect(window_days=window_days, now=now, persist=persist)


now_opt = click.option("--now", default=None, help="Override 'now' (ISO date) — for testing.")
home_opt = click.option("--claude-home", default=None, help="Path to the .claude dir.")
days_opt = click.option("--days", default=14, show_default=True, help="Dormancy/activity window in days.")


@click.group(help="Skill observability for Claude Code.")
@click.version_option(__version__, prog_name="skillvitals")
def main() -> None:
    pass


@main.command()
@home_opt
@days_opt
@now_opt
def scan(claude_home, days, now):
    """Scan installed skills and report fires, context cost, and health."""
    _apply_home(claude_home)
    from .analysis import dormant_token_cost, find_dormant
    from .hooks import detect_skill_hook
    from .report import build_rich_table
    from .tokens import humanize

    n = _now(now)
    snap = _collect(days, n)
    console.print(build_rich_table(snap.vitals))

    cost = dormant_token_cost(snap.vitals, days=days, now=n)
    dead = find_dormant(snap.vitals, days=days, now=n)
    if dead:
        console.print(
            f"\n[yellow]{len(dead)} dormant/never-fired skills are costing you "
            f"[bold]{humanize(cost)}[/bold] tokens per session.[/yellow]"
        )
        console.print("Run [cyan]skillvitals prescribe[/cyan] for fixes.")

    hook = detect_skill_hook(snap.config.home, snap.config.cwd)
    status = "[green]detected[/green]" if hook["has_prompt_hook"] else "[dim]not detected[/dim]"
    console.print(f"\nSkill-activation hook (UserPromptSubmit): {status}")
    if snap.errors:
        console.print(f"[dim]{len(snap.errors)} unparseable log line(s) skipped.[/dim]")


@main.command()
@home_opt
@days_opt
@now_opt
@click.option("--output", "-o", default=None, help="Write markdown to a file instead of stdout.")
def report(claude_home, days, now, output):
    """Render the full markdown report."""
    _apply_home(claude_home)
    from .report import render_markdown

    n = _now(now)
    snap = _collect(days, n)
    md = render_markdown(snap.vitals, now=n, dormant_days=days)
    if output:
        from pathlib import Path

        Path(output).write_text(md, encoding="utf-8")
        console.print(f"[green]Wrote[/green] {output}")
    else:
        click.echo(md)


@main.command()
@home_opt
@days_opt
@now_opt
def history(claude_home, days, now):
    """Show per-skill activation history."""
    _apply_home(claude_home)
    from .report import humanize_age

    n = _now(now)
    snap = _collect(days, n)
    table = Table(title=f"skill activation history (last {days}d window)", header_style="bold cyan")
    for col in ("skill", "invokes", "engaged", "sessions", "last seen", "first seen"):
        table.add_column(col, justify="right" if col in {"invokes", "engaged", "sessions"} else "left")
    for v in sorted(snap.vitals, key=lambda v: (-v.attribution_count, -v.invoke_count)):
        first = v.first_fired.date().isoformat() if v.first_fired else "—"
        table.add_row(v.name, str(v.invoke_count), str(v.attribution_count),
                      str(v.sessions), humanize_age(v.days_dormant), first)
    console.print(table)


@main.command()
@home_opt
@days_opt
@now_opt
def dormancy(claude_home, days, now):
    """List skills inactive for N days and their context cost."""
    _apply_home(claude_home)
    from .analysis import dormant_token_cost, find_dormant
    from .tokens import humanize

    n = _now(now)
    snap = _collect(days, n)
    dead = find_dormant(snap.vitals, days=days, now=n)
    table = Table(title=f"dormant skills (inactive ≥ {days}d)", header_style="bold yellow")
    table.add_column("skill")
    table.add_column("ctx tokens", justify="right")
    table.add_column("last seen")
    for v in dead:
        last = "never" if v.days_dormant is None else f"{v.days_dormant}d ago"
        table.add_row(v.name, humanize(v.context_tokens), last)
    console.print(table)
    console.print(
        f"\n[bold yellow]{humanize(dormant_token_cost(snap.vitals, days=days, now=n))}[/bold yellow]"
        " tokens of dead weight loaded every session."
    )


def _make_client():
    """Build an anthropic client if the extra is installed and a key is set."""
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return None
    try:
        import anthropic

        return anthropic.Anthropic()
    except ImportError:
        return None


@main.command()
@home_opt
@days_opt
@now_opt
@click.option("--rewrite", is_flag=True, help="Use an LLM to rewrite weak descriptions (opt-in, uses your key).")
def prescribe(claude_home, days, now, rewrite):
    """Suggest fixes for dormant / low-activation / redundant skills."""
    _apply_home(claude_home)
    from .prescribe import prescribe as run_prescribe
    from .prescribe import rewrite_description

    n = _now(now)
    snap = _collect(days, n)
    rx = run_prescribe(snap.vitals, now=n)
    if not rx:
        console.print("[green]No prescriptions — your skills look healthy.[/green]")
        return

    sev_color = {"critical": "red", "warn": "yellow", "info": "dim"}
    by_skill: dict[str, list] = {}
    for p in rx:
        by_skill.setdefault(p.skill_name, []).append(p)
    for skill_name, items in by_skill.items():
        console.print(f"\n[bold]{skill_name}[/bold]")
        for p in items:
            c = sev_color.get(p.severity.value, "white")
            console.print(f"  [{c}]●[/{c}] [{c}]{p.rule}[/{c}]: {p.message}")

    if rewrite:
        client = _make_client()
        if client is None:
            console.print("\n[yellow]--rewrite needs the 'llm' extra and ANTHROPIC_API_KEY.[/yellow]")
            return
        console.print("\n[bold]Suggested description rewrites:[/bold]")
        skills = {s.name: s for s in snap.skills}
        targets = {p.skill_name for p in rx
                   if p.rule in {"description-too-short", "no-trigger-words", "low-quality"}}
        for name in targets:
            if name in skills:
                new = rewrite_description(skills[name], client=client)
                if new:
                    console.print(f"\n[bold]{name}[/bold]:\n  {new}")


@main.command(name="test")
@home_opt
@click.option("--skill", required=True, help="Skill name to test.")
@click.option("--n", default=10, show_default=True, help="Number of synthetic prompts.")
@click.option("--live", is_flag=True, help="Actually run prompts through headless Claude Code.")
def test_cmd(claude_home, skill, n, live):
    """Generate (and optionally run) an activation test battery for a skill."""
    _apply_home(claude_home)
    from .config import load_config
    from .registry import scan_skills
    from .testharness import make_cli_runner, measure_activation, synth_prompts

    config = load_config()
    skills = {s.name: s for s in scan_skills(config.skill_roots())}
    if skill not in skills:
        raise click.ClickException(f"Skill '{skill}' not found. Run `skillvitals scan` to list skills.")

    prompts = synth_prompts(skills[skill].description, n=n)
    console.print(f"[bold]{skill}[/bold] — {len(prompts)} synthetic test prompts:")
    for i, p in enumerate(prompts, 1):
        console.print(f"  {i}. {p}")

    if not live:
        console.print("\n[dim]Dry run. Re-run with --live to measure real activation "
                      "(spawns headless Claude Code, uses your plan).[/dim]")
        return

    console.print("\n[cyan]Running live activation test…[/cyan]")
    runner = make_cli_runner(skill, claude_home=config.home, cwd=config.cwd)
    res = measure_activation(skill, prompts, runner=runner)
    color = {"green": "green", "yellow": "yellow", "red": "red"}[res.grade]
    console.print(f"Activation rate: [{color}]{res.activation_rate:.0%}[/{color}] "
                  f"({res.activations}/{res.prompts_run}) — [{color}]{res.grade}[/{color}]")


@main.command()
@home_opt
@days_opt
@now_opt
@click.option("--output", "-o", default=None, help="Where to write the HTML (default ~/.skillvitals/dashboard.html).")
@click.option("--open", "open_", is_flag=True, help="Open the dashboard in your browser.")
def dashboard(claude_home, days, now, output, open_):
    """Generate the self-contained HTML dashboard."""
    _apply_home(claude_home)
    from .dashboard import write_dashboard
    from .prescribe import prescribe as run_prescribe

    n = _now(now)
    snap = _collect(days, n)
    out = output or str(snap.config.dashboard_path)
    rx = run_prescribe(snap.vitals, now=n)
    path = write_dashboard(snap.vitals, out, now=n, dormant_days=days, prescriptions=rx)
    console.print(f"[green]Dashboard written to[/green] {path}")
    if open_:
        import webbrowser

        webbrowser.open(f"file://{path}")


@main.command()
@home_opt
def serve(claude_home):
    """Run skillvitals as an MCP server (stdio transport)."""
    _apply_home(claude_home)
    from .server import mcp

    mcp.run()


if __name__ == "__main__":
    main()
