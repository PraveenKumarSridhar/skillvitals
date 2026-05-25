# skillvitals 0.2.0 — PRD

> **Status:** Draft for build. **Author:** Pk. **Date:** 2026-05-25.
> **Trigger:** Two correct pieces of feedback on the launch (Reddit) exposed real flaws in 0.1.0. This PRD specifies the fixes before any code is written, and is deliberately grounded in data verified on a real machine — 0.1.0 shipped a wrong number because it assumed a mechanism instead of checking it.

---

## 1. Background — what 0.1.0 got wrong

Two comments, both true:

> **"Skills are not loaded every time."**

> **"It showed me 'healthy' for skills which are disabled for a while. I'm not sure about the reliability of the numbers."**

0.1.0 has two defects:

1. **The token-cost metric is wrong.** It reports each skill's full `SKILL.md` size and frames dormant skills as "costing you N tokens **per session**." That is not how skills load.
2. **Health ignores enabled/disabled state.** Health is derived purely from logged history, and the registry lists `SKILL.md` files on disk regardless of whether their plugin is enabled. A recently-active-then-disabled skill therefore reports `healthy`.

These flaws are in the **headline metric** (the viral "23.5k tokens/session" line) and a **core classification**. They must be fixed honestly, and the public messaging (README, PyPI description, demo, posts) corrected.

## 2. Ground truth (verified on a real machine, 2026-05-25)

### 2.1 Skills load progressively
Claude Code loads each skill's **name + description** at session start so the model knows the skill exists. The **body of `SKILL.md` is loaded only when the skill activates.** Therefore:

- **Always-on per-session cost of a skill = its description tokens** (~tens to low hundreds of tokens).
- **Body tokens = the cost incurred when the skill activates**, not a standing per-session tax.

0.1.0 conflated body size with per-session cost, overstating dormant cost by roughly 10x.

### 2.2 Enabled/disabled state lives in settings
`~/.claude/settings.json` (and `settings.local.json`, and project `.claude/settings.json`) contains:

```json
"enabledPlugins": {
  "resume-tailoring@local-skills": true,
  "superpowers@claude-plugins-official": true,
  "skill-creator@claude-plugins-official": true
}
```

Enable/disable is at the **plugin** level, keyed `"<plugin>@<marketplace>"`. A skill is **disabled** when its owning plugin is missing from this map or set to `false`. `extraKnownMarketplaces` maps marketplace names to sources (e.g. `local-skills` → the user's `~/.claude/skills` directory).

### 2.3 Claude Code keeps a native skill-usage ledger
`~/.claude.json` contains:

```json
"skillUsage": {
  "superpowers:writing-plans": { "usageCount": 1, "lastUsedAt": 1779698256246 },
  "skill-creator:skill-creator": { "usageCount": 1, "lastUsedAt": 1779663615677 }
}
```

`lastUsedAt` is epoch-ms. This is an authoritative source for invocation count and last-used, and it corroborated 0.1.0's dormancy findings. It does **not** contain engagement depth or per-session breakdown — that still comes from the JSONL `attributionSkill` signal.

## 3. Goals / non-goals

**Goals**
- G1. Replace the misleading single token number with an honest two-part metric: **always-on (description) tokens** vs **on-activation (body) tokens**.
- G2. Detect enabled/disabled state and stop calling disabled skills `healthy`.
- G3. Adopt `skillUsage` as a corroborating/primary source for invocation count + last-used; reconcile with the JSONL signal.
- G4. Correct all public messaging (README, PyPI, demo GIF, launch posts) and post an honest follow-up to the Reddit thread.

**Non-goals**
- Measuring exact live context-window composition per session (out of scope; we estimate description tokens and label them as the always-on figure).
- Changing the activation/engagement model itself (it's sound).
- Auto-applying fixes (still show-don't-apply).

## 4. Problem 1 — honest token metric

### 4.1 New definitions
- `always_on_tokens` = estimated tokens of the skill's **frontmatter description** (the part always loaded). Computed from the description string.
- `on_activation_tokens` = estimated tokens of the **full `SKILL.md`** (loaded only when the skill fires). This is today's `context_tokens`, renamed for honesty.
- Drop the phrase "per session" from anything referencing body size.

### 4.2 Output changes
- `scan` / `report` / dashboard: replace the single `ctx` column with **`always-on`** and **`on-fire`** columns (or `ctx (always/on-fire)`).
- **Headline rewrite.** Old: *"13 dormant skills are costing you 23.5k tokens per session."* New, accurate framing, e.g.:
  > *"You have 13 dormant skills. Their descriptions add ~Xk tokens to every session; their bodies (~23.5k tokens) load only if they ever fire."*
  The emphasis shifts from "dead token tax" to: dormant skills clutter selection and carry maintenance/ambiguity cost, and their always-on description footprint is the real standing cost.
- `dormancy` command: report **always-on** cost as the per-session number, and show body size separately as "would load on activation."

### 4.3 Modules touched
- `models.Skill`: add `description_tokens` (always-on); keep full-size as `context_tokens` but treat/label as on-activation.
- `registry`: compute `description_tokens = estimate_tokens(description)`.
- `analysis.SkillVitals`: expose both numbers; `dormant_token_cost` becomes **always-on** sum (with a separate `dormant_on_fire_cost` available).
- `report`, `dashboard`, `server`: new columns + corrected summary copy.

## 5. Problem 2 — enabled/disabled awareness

### 5.1 New data source: `hooks`/`config` → enabled plugins
Add a reader for `enabledPlugins` across `settings.json`, `settings.local.json`, and project `.claude/settings.json` (project overrides user). Returns the merged `{ "plugin@marketplace": bool }` map plus the `extraKnownMarketplaces` mapping.

### 5.2 Skill → plugin@marketplace mapping
- **Plugin-cache skills:** path `.../plugins/cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md` → `"<plugin>@<marketplace>"`.
- **User-dir skills** (`~/.claude/skills/<skill>/...`): map via `extraKnownMarketplaces` whose source path contains the skill (e.g. `local-skills`) → `"<skill-dir>@<marketplace>"`. Fall back to "unknown marketplace" when it can't be resolved.
- A skill is **enabled** iff its `plugin@marketplace` key is present and `true`. Missing/`false` ⇒ **disabled**.

### 5.3 New status taxonomy
Add `disabled` and make `healthy` explicitly window-scoped:
- `disabled` — installed on disk but its plugin is not enabled. **Takes precedence** over activity-based statuses (a disabled skill is never `healthy`, even with recent logged fires).
- `healthy` / `misfiring` / `dormant` / `never-fired` / `orphan` — unchanged, but documentation states clearly these reflect **logged activity within the window** and can lag a just-changed config.
- Disabled skills are excluded from the "dead weight" cost line (they're not loaded at all) but listed with a `disabled` tag.

### 5.4 Modules touched
- New `config`/`plugins` reader for `enabledPlugins` + marketplaces.
- `models.Skill`: add `enabled: bool | None` and `plugin_ref: str | None` (`plugin@marketplace`).
- `registry`: resolve `plugin_ref` and `enabled` during scan.
- `analysis`: `disabled` precedence in `_classify`; exclude disabled from dormant-cost.
- `report`/`dashboard`/`server`: surface `disabled`; footnote that health is window-scoped.

## 6. Problem 3 (opportunity) — reconcile with native `skillUsage`

- Read `skillUsage` from `~/.claude.json`: `{ id: { usageCount, lastUsedAt(ms) } }`.
- Use it as a **second source** for invocation count + last-used, joined on normalized name.
- **Reconciliation rule:** prefer the **max** of (JSONL invoke count, `skillUsage.usageCount`) for "fires", and the **latest** of (JSONL last fire, `skillUsage.lastUsedAt`) for "last seen". Keep JSONL as the sole source for **engagement** and **sessions** (skillUsage lacks these).
- Surface a discrepancy note if the two sources disagree materially (a cheap way to catch our own parser drift — directly addresses the "reliability of numbers" complaint).

## 7. Output / UX summary (after 0.2.0)

```
skill            fires  engaged  always-on  on-fire  last seen  status
frontend-design     31      140        140     6.4k  today      healthy
old-helper           4       20         90     2.1k  2d ago     disabled
data-analysis        0        0        110     4.2k  never      never-fired
```

Headline:
> 13 dormant/never-fired skills add ~2.0k tokens of always-loaded descriptions per session. Their bodies (~23.5k tokens) load only when they activate.

## 8. Verification plan (must pass before publishing 0.2.0)

- **V1.** Recompute always-on (description) tokens for the real skill set; confirm the new per-session number is in the low thousands, not ~23k. Publish only a measured/derived number.
- **V2.** Toggle a plugin to `false` in a fixture settings, confirm its skill flips to `disabled` and drops out of the dead-weight cost even with recent logged fires (this is the exact bug the commenter hit — make it a regression test).
- **V3.** Cross-check JSONL invoke counts vs `skillUsage.usageCount` on real data; document any divergence and the reconciliation outcome.
- **V4.** Full `pytest` green (existing 47 + new tests for: description_tokens, enabled-state reader, plugin_ref mapping, disabled precedence, skillUsage merge).

## 9. Versioning, migration, rollout

- Version **0.2.0** (output schema changes → minor bump, pre-1.0).
- SQLite: additive columns (`description_tokens`, `enabled`, `plugin_ref`); bump an internal schema version; migrate or recreate on open.
- Rollout: build → V1–V4 → bump version → `uv build` → `uv publish` (needs a fresh **project-scoped** PyPI token; the 0.1.0 token was exposed and must be revoked) → regenerate demo GIF + dashboard → update README/PyPI copy → post the honest Reddit follow-up.

## 10. Risks

- **R1. Marketplace mapping for user-dir skills is heuristic.** If `plugin_ref` can't be resolved, mark `enabled = None` (unknown) rather than guessing `disabled` — never falsely call an enabled skill disabled.
- **R2. `skillUsage` semantics.** `usageCount` may count sessions, not invocations. Treat it as corroboration, not gospel; never silently overwrite the JSONL-derived number, surface divergence.
- **R3. Progressive-disclosure nuance.** If some skill content beyond the description is always loaded in a future Claude Code version, the always-on number is a floor. Label it an estimate.
- **R4. Messaging blast radius.** The wrong number is already public (PyPI, GitHub, Reddit, posts). Correct all of them; treat the Reddit reply as part of the deliverable, not an afterthought.

## 11. Open questions

- Should `scan` hide `disabled` skills by default (with a `--all` flag) or always show them tagged? *Proposed: show, tagged.*
- Is `skillUsage.usageCount` per-invocation or per-session? Resolve in V3 and document.
- Do we want a `--strict` mode that fails loudly if JSONL and `skillUsage` disagree beyond a threshold? *Defer to a later version unless V3 shows frequent drift.*
