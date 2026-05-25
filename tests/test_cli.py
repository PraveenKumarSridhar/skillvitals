import os

from click.testing import CliRunner

from skillvitals.cli import main


def _run(args, home):
    env = {**os.environ, "SKILLVITALS_CLAUDE_HOME": str(home),
           "SKILLVITALS_HOME": str(home.parent / ".skillvitals")}
    return CliRunner().invoke(main, args, env=env, catch_exceptions=False)


def test_scan_lists_skills_and_status(fake_claude_home):
    r = _run(["scan", "--days", "14", "--now", "2026-05-25"], fake_claude_home)
    assert r.exit_code == 0
    assert "docx" in r.output
    assert "data-analysis" in r.output
    assert "leakcheck" in r.output
    # docx fired; the other two are dead weight
    assert "tokens per session" in r.output


def test_report_markdown(fake_claude_home):
    r = _run(["report", "--now", "2026-05-25"], fake_claude_home)
    assert r.exit_code == 0
    assert "skillvitals" in r.output
    assert "| skill |" in r.output


def test_dormancy(fake_claude_home):
    r = _run(["dormancy", "--days", "14", "--now", "2026-05-25"], fake_claude_home)
    assert r.exit_code == 0
    assert "leakcheck" in r.output or "data-analysis" in r.output


def test_prescribe(fake_claude_home):
    r = _run(["prescribe", "--now", "2026-05-25"], fake_claude_home)
    assert r.exit_code == 0


def test_dashboard_writes_file(fake_claude_home, tmp_path):
    out = tmp_path / "dash.html"
    r = _run(["dashboard", "--output", str(out), "--now", "2026-05-25"], fake_claude_home)
    assert r.exit_code == 0
    assert out.exists()
    assert "<!doctype html" in out.read_text().lower()


def test_test_command_dry_run_shows_prompts(fake_claude_home):
    r = _run(["test", "--skill", "docx", "--n", "3"], fake_claude_home)
    assert r.exit_code == 0
    assert "docx" in r.output


def test_server_module_importable():
    from skillvitals import server

    assert hasattr(server, "mcp")
