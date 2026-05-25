# skillvitals

**Skill observability for Claude Code.** See which of your skills fire, which are
dormant, what they cost in context, and what's broken.

Claude Code skills are supposed to auto-activate. In practice many never fire —
they just sit in every session burning context tokens. The ecosystem has plenty
of tools to *generate* skill-activation hooks. `skillvitals` is the missing
diagnostic layer: it treats every installed skill as a monitored service and
tells you *did it fire? when? at what context cost? is it dead weight?*

![skillvitals scan + prescribe demo](docs/skillvitals-demo.gif)

```text
$ skillvitals scan

                                  skillvitals
┏━━━━━━━━━━━━━━━━━━━━┳━━━━━━━┳━━━━━━━━━┳━━━━━━┳━━━━━━━━━━━┳━━━━━━━━━━━━━━━━┓
┃ skill              ┃ fires ┃ engaged ┃  ctx ┃ last seen ┃ status         ┃
┡━━━━━━━━━━━━━━━━━━━━╇━━━━━━━╇━━━━━━━━━╇━━━━━━╇━━━━━━━━━━━╇━━━━━━━━━━━━━━━━┩
│ frontend-design    │    31 │     140 │ 6.4k │ today     │ ✅ healthy     │
│ docx               │    47 │     120 │ 2.1k │ today     │ ✅ healthy     │
│ pdf                │    23 │      60 │ 1.8k │ 1d ago    │ ✅ healthy     │
│ sql-tuner          │     4 │       9 │ 2.6k │ 9d ago    │ ✅ healthy     │
│ ab-test-coach      │     2 │       2 │ 5.7k │ 3d ago    │ ⚠️  misfiring  │
│ leakcheck          │     1 │       3 │ 3.1k │ 40d ago   │ ⚠️  dormant    │
│ data-analysis      │     0 │       0 │ 4.2k │ never     │ 💤 never-fired │
│ changelog-writer   │     0 │       0 │ 1.4k │ never     │ 🚫 disabled    │
└────────────────────┴───────┴─────────┴──────┴───────────┴────────────────┘

2 dormant/never-fired skills add ~29 tokens of always-loaded descriptions per session.
Their bodies (~7.3k tokens) load only when they activate.
1 installed skill is disabled (plugin off): changelog-writer.
Run `skillvitals prescribe` for fixes.
```

The point: skills load progressively. What rides along in *every* session is each
skill's description; the body only loads when the skill fires. skillvitals shows
both — the standing **always-on** cost and the **on-fire** body size — so you can
see which skills are dead weight, which misfire, and which are quietly disabled.

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
   frontmatter, scores description quality, and measures two token costs:
   the **always-on** description (loaded every session) and the **on-fire** body
   (loaded only when the skill activates). It also reads `enabledPlugins` to know
   which skills are currently disabled, and reconciles against Claude Code's own
   `skillUsage` ledger so the counts don't rely on one source.

2. **Your session logs** — the JSONL transcripts under `~/.claude/projects`. It
   extracts two activation signals per skill:
   - **fires** — explicit `Skill()` invocations (the skill was activated).
   - **engaged** — assistant messages tagged with that skill's `attributionSkill`
     (how much the skill was actually leaned on afterward).

Joining these gives each skill a health status:

| status | meaning |
|--------|---------|
| ✅ **healthy** | activated recently with real follow-through |
| ⚠️ **misfiring** | invoked but barely used afterward; may be matching the wrong prompts |
| ⚠️ **dormant** | activated before, but not within the window |
| 💤 **never-fired** | installed, has never activated |
| 🚫 **disabled** | installed on disk but its plugin is turned off (never loads) |
| ❓ **orphan** | appears in logs but is no longer installed |

Health is derived from logged activity within the window, so it reflects recent
behavior and can lag a config change you just made.

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
uv run pytest        # 65 tests
uv run ruff check src tests
```

## License

MIT © 2026 Pk
