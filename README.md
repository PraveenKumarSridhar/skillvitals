# skillvitals

**Skill observability for Claude Code.** See which of your skills fire, which are
dormant, what they cost in context, and what's broken.

Claude Code skills are supposed to auto-activate. In practice many never fire —
they just sit in every session burning context tokens. The ecosystem has plenty
of tools to *generate* skill-activation hooks. `skillvitals` is the missing
diagnostic layer: it treats every installed skill as a monitored service and
tells you *did it fire? when? at what context cost? is it dead weight?*

```text
$ skillvitals scan

                                  skillvitals
┏━━━━━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ skill                  ┃ fires ┃ engaged ┃  ctx ┃ last seen ┃ status         ┃
┡━━━━━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ writing-plans          │     1 │     228 │ 1.5k │ today     │ ✅ healthy     │
│ resume-tailoring       │     2 │      39 │ 8.9k │ 2d ago    │ ✅ healthy     │
│ writing-skills         │     1 │      20 │ 5.6k │ today     │ ✅ healthy     │
│ skill-creator          │     1 │      18 │ 8.2k │ today     │ ✅ healthy     │
│ subagent-driven-devel… │     0 │       0 │ 3.1k │ never     │ 💤 never-fired │
│ brainstorming          │     0 │       0 │ 2.6k │ never     │ 💤 never-fired │
│ …                      │       │         │      │           │                │
└────────────────────────┴───────┴─────────┴──────┴───────────┴────────────────┘

13 dormant/never-fired skills are costing you 23.5k tokens per session.
Run `skillvitals prescribe` for fixes.
```

That last line is the point: **most people have thousands of tokens of dead
weight in every single session and no way to see it.**

## Install

```bash
uvx skillvitals scan          # run without installing
# or
pip install skillvitals
```

Requires Python 3.11+. Reads your existing Claude Code data under `~/.claude` —
nothing is sent anywhere (see [Privacy](#privacy)).

## Commands

| Command | What it does |
|---------|--------------|
| `skillvitals scan` | Headline table: fires, engagement, context cost, health, per skill. |
| `skillvitals report` | Markdown report (`-o report.md` to save / share). |
| `skillvitals history` | Per-skill activation history across sessions. |
| `skillvitals dormancy` | Skills inactive for N days and the tokens they cost (`--days 14`). |
| `skillvitals prescribe` | Concrete fixes for weak/dormant/redundant skills (`--rewrite` for LLM rewrites). |
| `skillvitals test --skill X` | Synthetic activation-test prompts (`--live` runs them through headless Claude Code). |
| `skillvitals dashboard --open` | Self-contained HTML dashboard at `~/.skillvitals/dashboard.html`. |
| `skillvitals serve` | Run as an MCP server. |

## Use it as an MCP server

`skillvitals` is also an MCP server, so you can ask Claude Code about your skills
in plain language ("which of my skills are dormant?").

```bash
claude mcp add skillvitals -- uvx skillvitals serve
```

Or add it to your MCP config manually:

```json
{
  "mcpServers": {
    "skillvitals": { "command": "uvx", "args": ["skillvitals", "serve"] }
  }
}
```

Exposed tools: `vitals_scan`, `vitals_history`, `vitals_dormancy`,
`vitals_report`, `vitals_prescribe`, `vitals_test`, `vitals_dashboard`.

## How it works

skillvitals reads two things, entirely locally:

1. **Your installed skills** — every `SKILL.md` under `~/.claude/skills`, the
   plugin cache, and the current project's `.claude/skills`. It parses the
   frontmatter, estimates the context cost (tokens of the loaded `SKILL.md`),
   and scores description quality.

2. **Your session logs** — the JSONL transcripts under `~/.claude/projects`. It
   extracts two activation signals per skill:
   - **fires** — explicit `Skill()` invocations (the skill was activated).
   - **engaged** — assistant messages tagged with that skill's `attributionSkill`
     (how much the skill was actually leaned on afterward).

Joining the two gives each skill a health status:

| status | meaning |
|--------|---------|
| ✅ **healthy** | activated recently with real follow-through |
| ⚠️ **misfiring** | invoked but barely used afterward — may be matching the wrong prompts |
| ⚠️ **dormant** | activated before, but not within the window |
| 💤 **never-fired** | installed, costs tokens, has never activated |
| ❓ **orphan** | appears in logs but is no longer installed |

These are honest heuristics, not ground truth — the thresholds are documented in
`analysis.py` and `prescribe.py`.

## Privacy

100% local. skillvitals only reads files already on your machine under
`~/.claude`, writes a local SQLite cache to `~/.skillvitals/db.sqlite`, and a
local HTML file. **No network calls, no telemetry, nothing leaves your machine** —
with two explicit, opt-in exceptions:

- `skillvitals test --live` spawns headless Claude Code to measure real activation.
- `skillvitals prescribe --rewrite` calls the Anthropic API to rewrite weak
  descriptions. Requires `pip install 'skillvitals[llm]'` and `ANTHROPIC_API_KEY`.

Both are off by default.

## What it deliberately doesn't do

- **Generate activation hooks.** That space is well covered (`skills-hook`,
  `claude-skills-supercharged`, …). Pair skillvitals with one of those — it
  *reports* whether a `UserPromptSubmit` hook exists, it doesn't write one.
- **Auto-apply fixes.** v1 shows prescriptions; it doesn't edit your skills.
- **Phone home.** No cloud, no accounts, no team aggregation.

## Configuration

Environment variables (all optional):

- `SKILLVITALS_CLAUDE_HOME` — the `.claude` dir (default `~/.claude`).
- `SKILLVITALS_HOME` — where the db + dashboard live (default `~/.skillvitals`).
- `ANTHROPIC_API_KEY` — only needed for the opt-in LLM features.

## Development

```bash
uv sync --extra llm
uv run pytest        # 47 tests
uv run ruff check src tests
```

## License

MIT © 2026 Pk
