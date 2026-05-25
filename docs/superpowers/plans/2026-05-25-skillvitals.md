# skillvitals Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.
>
> **Execution note (2026-05-25):** This plan is being executed inline, solo, overnight, by the same agent that wrote it (full context retained). The PRD (`PRD.md` material in the kickoff message) is treated as the finalized spec. Brainstorming was not possible (author asleep); design decisions that deviate from the PRD are flagged inline under "Deviations from PRD" and are grounded in the real Claude Code data formats discovered during reconnaissance.

**Goal:** Ship `skillvitals`, an MCP server + CLI that treats every installed Claude Code skill as a monitored service — reporting fire counts, dormancy, context cost, health, and prescribed fixes.

**Architecture:** Pure-function core (registry scan, log parse, analysis) feeding three surfaces: a Click CLI, a FastMCP server, and a Jinja2 HTML dashboard. SQLite is the persistence layer. No cloud component. Everything reads from `~/.claude/`.

**Tech Stack:** Python 3.11+, FastMCP, Click, Rich, Jinja2, PyYAML, SQLite (stdlib), optional `anthropic` for live activation testing / LLM rewrites.

---

## Reconnaissance findings (ground truth, verified on this machine)

These shape the design and override PRD assumptions where they conflict:

1. **Skill discovery:** `SKILL.md` files live under `~/.claude/skills/**`, `~/.claude/plugins/cache/**`, and project-local `.claude/skills/**`. The same skill appears multiple times (e.g. `resume-tailoring` in both a local dir and the plugin cache). **Must dedupe by normalized name**, preferring a canonical source.
2. **Frontmatter:** YAML between `---` fences. Keys: `name` (bare, e.g. `resume-tailoring`), `description`.
3. **Activation signal — richer than the PRD's "Skill() tool calls":**
   - **Explicit fires:** assistant messages contain a `tool_use` block with `"name":"Skill"` and `input.skill` = the **namespaced** id (`plugin:skill`, e.g. `superpowers:writing-plans`). Each has a top-level `timestamp`. This is the true "fire."
   - **Engagement/attribution:** many lines carry top-level `attributionSkill` (namespaced id) + `attributionPlugin`. These tag every assistant message produced while a skill was active — a measure of *depth of use*, not just invocation. `message.usage` on these lines gives real token costs.
   - **DEVIATION FROM PRD:** the PRD only mentions `Skill()` tool calls. We capture both signals. Fire count = explicit invokes; engagement = attribution message count; health uses the ratio.
4. **Session JSONL top-level keys of interest:** `type` (`user`/`assistant`/`system`/...), `timestamp` (ISO8601 Z), `sessionId`, `cwd`, `version` (e.g. `2.1.146`), `gitBranch`, `message` (with `usage`), `attributionSkill`, `attributionPlugin`, `toolUseResult`.
5. **Name join:** logs use `plugin:skill`; frontmatter uses bare `skill`. Join on the skill segment (after the last `:`). Skills in logs but not registry = "orphan" (uninstalled/renamed). Skills in registry but never in logs = "never-fired".
6. **Context cost:** estimate from `SKILL.md` byte length (`tokens ≈ ceil(chars/4)`). `resume-tailoring` ≈ 35.6 KB ≈ 8.9k tokens.
7. **Toolchain:** `uv` present, Python 3.12 local, `fastmcp` 3.3.1 installs clean, `sqlite3` available.

## File structure

```
src/skillvitals/
  __init__.py        # version
  config.py          # path resolution (~/.claude roots, db path), constants, env overrides
  tokens.py          # estimate_tokens(text), humanize(n) -> "2.1k"
  models.py          # dataclasses: Skill, Fire, SessionInfo, ParseError, SkillVitals, Prescription
  registry.py        # scan_skills(roots) -> list[Skill]; frontmatter parse; quality score; dedupe
  logparser.py       # parse_sessions(projects_dir) -> (fires, sessions, errors); schema-aware adapter
  storage.py         # Database: ingest()/load_*; SQLite schema skills/fires/sessions
  analysis.py        # compute_vitals(skills, fires, window_days, now) -> list[SkillVitals]; dormant()
  report.py          # render_report(vitals) -> markdown str; render_table for Rich
  prescribe.py       # rule engine -> list[Prescription]; optional LLM rewriter
  testharness.py     # synth prompts from description; headless runner; activation measurement
  dashboard.py       # render_dashboard(vitals) -> html str
  templates/dashboard.html.j2
  cli.py             # Click group: scan/history/dormancy/report/test/prescribe/dashboard/serve
  server.py          # FastMCP server: vitals_* tools
tests/
  conftest.py        # fake_claude_home fixture: synthetic skills tree + JSONL
  fixtures/*.jsonl
  test_*.py          # one per module
```

## Health model (defensible, documented)

Per skill, within a window (default 14 days), classify:

- `never-fired` — zero lifetime fires AND zero attribution.
- `dormant` — has fired historically but **0 activation within the window**.
- `misfiring` — activated within window but **low follow-through**: `engagement_ratio = attribution_msgs / max(invokes,1) < 2`. Proxy for wrong-prompt activation (invoked then dropped).
- `healthy` — activated within window with adequate engagement.

`orphan` is a separate flag (in logs, not in registry).

## Description quality score (0–100)

Weighted components, each documented in `registry.py`:
- length band (ideal 80–600 chars) — 40 pts
- trigger phrasing (`use when`, `when the user`) — 25 pts
- specificity (digits, parentheses, examples, proper nouns) — 20 pts
- has name + valid frontmatter — 15 pts

---

## Tasks (TDD: failing test → run → implement → run → commit)

### Task 1: Scaffold (DONE inline)
- [x] `uv init --package`, pyproject with deps, ruff/pytest config, plan doc, git init.

### Task 2: tokens + models
- [ ] `test_tokens.py`: `estimate_tokens("a"*40)==10`; `humanize(2100)=="2.1k"`, `humanize(950)=="950"`.
- [ ] Implement `tokens.py`.
- [ ] `models.py`: frozen dataclasses with the fields used downstream (see modules). No tests beyond import (dataclasses are data).
- [ ] Commit.

### Task 3: registry scanner
- [ ] `test_registry.py`: given a temp tree with two SKILL.md (one dup, one bad frontmatter), `scan_skills` returns deduped Skills with correct name/description/tokens; quality score monotonic (good desc > empty desc); invalid frontmatter → `frontmatter_valid=False`.
- [ ] Implement `registry.py`.
- [ ] Commit.

### Task 4: log parser
- [ ] `test_logparser.py`: feed a fixture JSONL containing (a) a Skill tool_use line, (b) an attribution line with usage, (c) a malformed line, (d) an unrelated line. Assert 1 invoke Fire, 1 attribution Fire with token fields, 1 ParseError, sessions captured. Timestamps parsed to aware datetimes.
- [ ] Implement `logparser.py` (per-line adapter, fail-soft, collect errors; capture `version` for schema awareness).
- [ ] Commit.

### Task 5: storage
- [ ] `test_storage.py`: ingest skills+fires+sessions into `:memory:`/temp db; load back equal; re-ingest is idempotent (upsert by key); schema has skills/fires/sessions.
- [ ] Implement `storage.py`.
- [ ] Commit.

### Task 6: analysis
- [ ] `test_analysis.py`: construct Skills + Fires; assert vitals: fire_count, last_fired, engagement, context_tokens, days_dormant, status classification across all four states; `dormant(vitals, n)` filters correctly; orphan detection.
- [ ] Implement `analysis.py`.
- [ ] Commit.

### Task 7: report
- [ ] `test_report.py`: `render_report(vitals)` markdown contains table headers, the dormant-token-cost summary line, per-skill rows, status emoji.
- [ ] Implement `report.py` (markdown + Rich table builder).
- [ ] Commit.

### Task 8: prescribe
- [ ] `test_prescribe.py`: short description → "expand description" rx; no trigger words → "add trigger phrasing" rx; two skills with near-identical descriptions → "redundant" rx; dormant + healthy alternative → suggestion. LLM path is guarded behind a flag and not exercised in unit tests (injected client mock returns canned text).
- [ ] Implement `prescribe.py`.
- [ ] Commit.

### Task 9: test harness
- [ ] `test_testharness.py`: `synth_prompts(description, n)` returns n prompts derived from description (rule-based fallback, deterministic); `measure_activation(skill, prompts, runner=fake_runner)` aggregates green/yellow/red from runner results without calling any real CLI. Real runner shells `claude -p` and parses output for the skill id — covered by a mocked subprocess test only.
- [ ] Implement `testharness.py`.
- [ ] Commit.

### Task 10: dashboard
- [ ] `test_dashboard.py`: `render_dashboard(vitals)` returns self-contained HTML (`<!doctype`, inline `<style>`, no external `src=`), one row per skill, sortable table markup present.
- [ ] Implement `dashboard.py` + template.
- [ ] Commit.

### Task 11: CLI + server
- [ ] `test_cli.py`: CliRunner over `scan/dormancy/report/dashboard` pointed at the fake claude home via env var; exit 0; expected substrings. `serve` importable.
- [ ] Implement `cli.py` (Click) + `server.py` (FastMCP tools wrapping core).
- [ ] Commit.

### Task 12: integration on real data
- [ ] Run `skillvitals scan` / `report` / `dormancy` against real `~/.claude`. Verify the four real skills (resume-tailoring, writing-skills, skill-creator, writing-plans) show fires; dormant skills show context cost; no crashes; schema-drift handled.
- [ ] Commit.

### Task 13: README + packaging + final pass
- [ ] README with demo block, install, MCP config snippet, "how it works", privacy (local-only), publish-yourself steps. LICENSE (MIT). `uv build` produces wheel+sdist. `ruff check` clean. Full `pytest` green. **Do NOT publish to PyPI or push to a public remote** — leave as documented manual steps.
- [ ] Commit.

## Deviations from PRD (summary)

1. **Two activation signals** (invoke + attribution), not just `Skill()` calls — strictly richer, grounded in real logs.
2. **Publishing is left manual.** Building the package, git repo, and README is reversible/local; publishing to PyPI and creating a public GitHub repo are outward-facing and irreversible, and require the author's credentials/identity. Prepared but not executed.
3. **`vitals_test` live runner is opt-in** and isolated behind a mockable interface; default unit tests never spawn a real `claude` process or spend tokens.
4. Tool name `vitals_dashboard` (PRD Week-2 checklist) used for the dashboard MCP tool; CLI subcommand is `dashboard`.

## Self-review

- Spec coverage: scan ✓ (T3), history ✓ (T4+T6), dormancy ✓ (T6), report ✓ (T7), test ✓ (T9), prescribe ✓ (T8), dashboard ✓ (T10), SQLite ✓ (T5), MCP server ✓ (T11), README/PyPI ✓ (T13, publish manual).
- Non-goals respected: no hook generation, single-user, local SQLite, show-don't-apply prescriptions.
- Types consistent: `SkillVitals` is the single analysis output consumed by report/prescribe/dashboard/cli.
