# Publishing skillvitals

Everything here is **left for you to run** — I built and validated the package
locally but deliberately did not publish to PyPI or push to a public GitHub
repo, because those are irreversible, outward-facing, and tied to your identity
and credentials. Do these when you're awake and ready to launch.

## 0. Pre-flight (already done / verify)

```bash
uv run pytest                 # 47 passing
uv run ruff check src tests   # clean
uv build                      # builds dist/*.whl and dist/*.tar.gz
```

A clean-room install of the built wheel has been verified to expose the
`skillvitals` console script and run `skillvitals scan` (see
`docs/superpowers/plans/` notes).

## 1. Set the real homepage URLs

`pyproject.toml` currently points `Homepage`/`Repository`/`Issues` at
`github.com/pk/skillvitals`. Update those to your actual GitHub username/org
before publishing.

## 2. Create the GitHub repo

```bash
gh repo create skillvitals --public --source=. --remote=origin \
  --description "Skill observability for Claude Code"
git push -u origin main
```

(Record a demo GIF of `skillvitals scan` and drop it in the README — the
dormant-token line is the viral asset.)

## 3. Publish to PyPI

Test on TestPyPI first:

```bash
uv publish --publish-url https://test.pypi.org/legacy/ --token <test-token>
uvx --index-url https://test.pypi.org/simple/ skillvitals scan   # smoke test
```

Then the real thing:

```bash
uv publish --token <pypi-token>      # uses dist/ from `uv build`
```

Verify:

```bash
uvx skillvitals scan
```

## 4. Register with MCP directories

- Glama, mcpmarket.com (per the PRD launch plan).

## 5. Launch posts

Drafts/checklist live in the PRD (Show HN, r/ClaudeAI, LinkedIn, X thread, the
DM tour). The headline is always the dead-token number from your own machine.

## Name availability (from the PRD, last checked 2026-05-25)

`skillvitals` was reported available on PyPI / npm / GitHub and `skillvitals.dev`
was free. **Re-check immediately before publishing** — these can change.
Fallbacks: `skillscope`, `skillmon`, `skill-doctor`.
