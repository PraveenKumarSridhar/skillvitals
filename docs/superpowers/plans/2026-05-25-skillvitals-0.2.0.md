# skillvitals 0.2.0 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the two 0.1.0 flaws found in launch feedback: the misleading per-session token metric (skills load progressively) and health that ignores disabled state; and reconcile against Claude Code's native `skillUsage` ledger.

**Architecture:** Two new pure-reader modules (`enablement.py`, `usage.py`) feed the existing pipeline. `registry` gains a description-token estimate; `analysis` gains a `disabled` status (overriding activity), an always-on vs on-activation token split, and native-usage reconciliation. Surfaces (report/dashboard/cli/server) get new columns and corrected copy.

**Tech Stack:** Python 3.11+, stdlib json, existing deps. No new dependencies.

**Spec:** `docs/prd/2026-05-25-skillvitals-0.2.0.md`. Read it first.

---

## File structure

- Create `src/skillvitals/enablement.py` — read `enabledPlugins` + `extraKnownMarketplaces` from settings; map each skill to `plugin@marketplace`; annotate skills with `enabled`/`plugin_ref`.
- Create `src/skillvitals/usage.py` — read `~/.claude.json` `skillUsage` into `{name: SkillUsage}`.
- Modify `models.py` — `Health.DISABLED`; `Skill.{description_tokens,enabled,plugin_ref}`; `SkillVitals.{always_on_tokens,on_activation_tokens,enabled,native_usage_count,source_discrepancy}`; `SkillUsage` dataclass.
- Modify `registry.py` — set `description_tokens`.
- Modify `analysis.py` — `_classify` disabled precedence; token split; native reconciliation; dormant cost = always-on.
- Modify `config.py` — `claude_json_path` property.
- Modify `report.py`, `dashboard.py` + template, `server.py`, `cli.py` — columns + copy.
- Modify `pipeline.py` — wire enablement + usage.
- Tests: `tests/test_enablement.py`, `tests/test_usage.py`, extend `test_analysis.py`, `test_registry.py`, `test_report.py`, `test_cli.py`, `conftest.py`.

---

### Task 1: models — DISABLED status, new Skill/SkillVitals/SkillUsage fields

**Files:** Modify `src/skillvitals/models.py`. Test: `tests/test_models.py` (new).

- [ ] **Step 1: Write the failing test**

```python
# tests/test_models.py
from skillvitals.models import Health, Skill, SkillUsage


def test_disabled_health_exists_with_label_emoji():
    assert Health.DISABLED.value == "disabled"


def test_skill_new_fields_default():
    s = Skill("x", "d", "/x", "user", None, 100, 50, {}, True)
    assert s.description_tokens == 0
    assert s.enabled is None
    assert s.plugin_ref is None


def test_skill_usage_dataclass():
    u = SkillUsage(usage_count=3, last_used_ms=1779698256246)
    assert u.usage_count == 3 and u.last_used_ms == 1779698256246
```

- [ ] **Step 2: Run, expect fail** — `uv run --no-sync pytest tests/test_models.py -q` → ImportError/AttributeError.

- [ ] **Step 3: Implement.** In `models.py`:
  - Add to `Health`: `DISABLED = "disabled"`.
  - Add to `SkillVitals.status_emoji` map: `Health.DISABLED: "🚫"`.
  - Append to `Skill` (after `frontmatter_valid`):
    ```python
    description_tokens: int = 0  # always-on cost (loaded every session)
    enabled: bool | None = None  # None = unknown
    plugin_ref: str | None = None  # 'plugin@marketplace'
    ```
  - New dataclass:
    ```python
    @dataclass(frozen=True)
    class SkillUsage:
        """Claude Code's own per-skill ledger from ~/.claude.json."""
        usage_count: int
        last_used_ms: int | None
    ```
  - Append to `SkillVitals` (with defaults):
    ```python
    always_on_tokens: int = 0
    on_activation_tokens: int = 0
    enabled: bool | None = None
    native_usage_count: int = 0
    source_discrepancy: str | None = None
    ```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git add -A && git commit -m "feat(0.2.0): models for disabled status, token split, native usage"`.

---

### Task 2: registry — estimate description tokens (the always-on cost)

**Files:** Modify `src/skillvitals/registry.py`. Test: extend `tests/test_registry.py`.

- [ ] **Step 1: Failing test**

```python
# append to tests/test_registry.py
def test_description_tokens_estimated(tmp_path):
    fm = "---\nname: a\ndescription: " + ("word " * 40) + "\n---\nbody body body"
    root = tmp_path / "skills"
    (root / "a").mkdir(parents=True)
    (root / "a" / "SKILL.md").write_text(fm, encoding="utf-8")
    s = {x.name: x for x in scan_skills([(root, "user")])}["a"]
    assert s.description_tokens > 0
    # always-on (description) is smaller than full body cost
    assert s.description_tokens < s.context_tokens
```

- [ ] **Step 2: Run, expect fail** (`description_tokens == 0`).
- [ ] **Step 3: Implement.** In `registry._scan_root`, where `Skill(...)` is built, add `description_tokens=estimate_tokens(description),` (import already present).
- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(0.2.0): registry estimates always-on description tokens"`.

---

### Task 3: enablement.py — read enabled plugins, map skills, annotate

**Files:** Create `src/skillvitals/enablement.py`. Test: `tests/test_enablement.py`.

Ground truth: `settings.json` has `enabledPlugins: {"superpowers@claude-plugins-official": true}` and `extraKnownMarketplaces: {"local-skills": {"source": {"path": ".../.claude/skills"}}}`. Plugin-cache path: `.../plugins/cache/<marketplace>/<plugin>/<version>/skills/<skill>/SKILL.md`.

- [ ] **Step 1: Failing test**

```python
# tests/test_enablement.py
import json
from pathlib import Path

from skillvitals.enablement import annotate_enablement, read_enabled_plugins
from skillvitals.models import Skill


def _settings(home: Path, data: dict):
    home.mkdir(parents=True, exist_ok=True)
    (home / "settings.json").write_text(json.dumps(data), encoding="utf-8")


def _skill(name, path, plugin=None):
    return Skill(name, "d", path, "plugin" if plugin else "user", plugin, 100, 50, {}, True)


def test_read_enabled_plugins_merges(tmp_path):
    home = tmp_path / ".claude"
    _settings(home, {"enabledPlugins": {"superpowers@official": True, "old@mp": False}})
    m = read_enabled_plugins(home, cwd=tmp_path / "proj")
    assert m["superpowers@official"] is True
    assert m["old@mp"] is False


def test_annotate_plugin_cache_skill_enabled(tmp_path):
    home = tmp_path / ".claude"
    _settings(home, {"enabledPlugins": {"superpowers@claude-plugins-official": True}})
    p = (home / "plugins" / "cache" / "claude-plugins-official" / "superpowers"
         / "5.1.0" / "skills" / "tdd" / "SKILL.md")
    s = _skill("tdd", str(p), plugin="superpowers")
    out = {x.name: x for x in annotate_enablement([s], home, cwd=None)}
    assert out["tdd"].plugin_ref == "superpowers@claude-plugins-official"
    assert out["tdd"].enabled is True


def test_annotate_disabled_when_plugin_false(tmp_path):
    home = tmp_path / ".claude"
    _settings(home, {"enabledPlugins": {"superpowers@claude-plugins-official": False}})
    p = (home / "plugins" / "cache" / "claude-plugins-official" / "superpowers"
         / "5.1.0" / "skills" / "tdd" / "SKILL.md")
    s = _skill("tdd", str(p), plugin="superpowers")
    out = {x.name: x for x in annotate_enablement([s], home, cwd=None)}
    assert out["tdd"].enabled is False


def test_user_dir_skill_maps_via_marketplace(tmp_path):
    home = tmp_path / ".claude"
    skills_dir = home / "skills"
    _settings(home, {
        "enabledPlugins": {"resume-tailoring@local-skills": True},
        "extraKnownMarketplaces": {"local-skills": {"source": {"path": str(skills_dir)}}},
    })
    p = skills_dir / "resume-tailoring" / "SKILL.md"
    s = _skill("resume-tailoring", str(p))
    out = {x.name: x for x in annotate_enablement([s], home, cwd=None)}
    assert out["resume-tailoring"].plugin_ref == "resume-tailoring@local-skills"
    assert out["resume-tailoring"].enabled is True


def test_unknown_mapping_stays_none(tmp_path):
    home = tmp_path / ".claude"
    _settings(home, {"enabledPlugins": {}})
    s = _skill("mystery", str(tmp_path / "somewhere" / "SKILL.md"))
    out = {x.name: x for x in annotate_enablement([s], home, cwd=None)}
    assert out["mystery"].enabled is None  # never guess "disabled"
```

- [ ] **Step 2: Run, expect fail** (no module).
- [ ] **Step 3: Implement** `src/skillvitals/enablement.py`:

```python
"""Read Claude Code's plugin enable-state and map skills to plugins.

Enable/disable is per-plugin, keyed 'plugin@marketplace' in settings.json's
`enabledPlugins`. A skill is disabled when its owning plugin is present and
False; enabled when present and True; unknown (None) when we cannot resolve it
(we never guess 'disabled', per PRD risk R1).
"""

from __future__ import annotations

import json
from dataclasses import replace
from pathlib import Path

from .models import Skill


def _load(path: Path) -> dict:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def _settings_files(claude_home: Path, cwd: Path | None) -> list[Path]:
    files = [claude_home / "settings.json", claude_home / "settings.local.json"]
    if cwd:
        files += [cwd / ".claude" / "settings.json", cwd / ".claude" / "settings.local.json"]
    return files


def read_enabled_plugins(claude_home: Path, cwd: Path | None = None) -> dict[str, bool]:
    merged: dict[str, bool] = {}
    for f in _settings_files(claude_home, cwd):
        data = _load(f)
        ep = data.get("enabledPlugins")
        if isinstance(ep, dict):
            merged.update({k: bool(v) for k, v in ep.items()})
    return merged


def read_marketplaces(claude_home: Path, cwd: Path | None = None) -> dict[str, str]:
    """marketplace name -> source directory path (best effort)."""
    out: dict[str, str] = {}
    for f in _settings_files(claude_home, cwd):
        mk = _load(f).get("extraKnownMarketplaces")
        if isinstance(mk, dict):
            for name, spec in mk.items():
                path = (((spec or {}).get("source") or {}).get("path"))
                if path:
                    out[name] = str(path)
    return out


def _plugin_ref(skill: Skill, marketplaces: dict[str, str]) -> str | None:
    parts = Path(skill.path).parts
    if "cache" in parts and "plugins" in parts:
        i = parts.index("cache")
        if len(parts) > i + 2:
            marketplace, plugin = parts[i + 1], parts[i + 2]
            return f"{plugin}@{marketplace}"
    # user-dir skill: match against a known marketplace whose path contains it
    sp = str(Path(skill.path))
    for name, mpath in marketplaces.items():
        if sp.startswith(str(Path(mpath))):
            # plugin name = the skill's top dir under the marketplace path
            rel = Path(sp).relative_to(Path(mpath))
            return f"{rel.parts[0]}@{name}"
    return None


def annotate_enablement(
    skills: list[Skill], claude_home: Path, cwd: Path | None = None
) -> list[Skill]:
    enabled_map = read_enabled_plugins(claude_home, cwd)
    marketplaces = read_marketplaces(claude_home, cwd)
    out: list[Skill] = []
    for s in skills:
        ref = _plugin_ref(s, marketplaces)
        enabled = enabled_map.get(ref) if ref is not None else None
        out.append(replace(s, plugin_ref=ref, enabled=enabled))
    return out
```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(0.2.0): enablement reader + skill->plugin mapping"`.

---

### Task 4: usage.py — read native skillUsage ledger

**Files:** Create `src/skillvitals/usage.py`; modify `config.py`. Test: `tests/test_usage.py`.

- [ ] **Step 1: Failing test**

```python
# tests/test_usage.py
import json

from skillvitals.usage import read_skill_usage


def test_read_skill_usage(tmp_path):
    # ~/.claude.json sits next to the .claude dir
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude.json").write_text(json.dumps({"skillUsage": {
        "superpowers:writing-plans": {"usageCount": 2, "lastUsedAt": 1779698256246},
        "docx": {"usageCount": 5, "lastUsedAt": 1779000000000},
    }}), encoding="utf-8")
    u = read_skill_usage(tmp_path / ".claude")
    assert u["writing-plans"].usage_count == 2  # joined on bare name
    assert u["writing-plans"].last_used_ms == 1779698256246
    assert u["docx"].usage_count == 5


def test_read_skill_usage_missing(tmp_path):
    (tmp_path / ".claude").mkdir()
    assert read_skill_usage(tmp_path / ".claude") == {}
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement.**
  - In `config.py`, add property to `Config`:
    ```python
    @property
    def claude_json_path(self) -> Path:
        return self.home.parent / ".claude.json"
    ```
  - Create `src/skillvitals/usage.py`:
    ```python
    """Read Claude Code's native per-skill usage ledger from ~/.claude.json.

    Authoritative second source for invocation count + last-used. Joined on the
    bare (normalized) skill name; when both a namespaced and bare id exist we keep
    the larger count and the later timestamp.
    """

    from __future__ import annotations

    import json
    from pathlib import Path

    from .models import SkillUsage, normalize_name


    def read_skill_usage(claude_home: Path) -> dict[str, SkillUsage]:
        path = Path(claude_home).parent / ".claude.json"
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        raw = data.get("skillUsage")
        if not isinstance(raw, dict):
            return {}
        out: dict[str, SkillUsage] = {}
        for sid, rec in raw.items():
            if not isinstance(rec, dict):
                continue
            name = normalize_name(sid)
            count = int(rec.get("usageCount") or 0)
            last = rec.get("lastUsedAt")
            last = int(last) if isinstance(last, (int, float)) else None
            prev = out.get(name)
            if prev is None:
                out[name] = SkillUsage(count, last)
            else:
                out[name] = SkillUsage(
                    max(prev.usage_count, count),
                    max([t for t in (prev.last_used_ms, last) if t is not None], default=None),
                )
        return out
    ```

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(0.2.0): native skillUsage reader"`.

---

### Task 5: analysis — disabled precedence, token split, native reconciliation

**Files:** Modify `src/skillvitals/analysis.py`. Test: extend `tests/test_analysis.py`.

- [ ] **Step 1: Failing tests**

```python
# append to tests/test_analysis.py
from skillvitals.models import Health, SkillUsage
from datetime import datetime, timezone  # already imported as UTC; reuse


def _disabled_skill(name, tokens=3000):
    s = mk_skill(name, tokens)
    return type(s)(**{**s.__dict__, "enabled": False, "description_tokens": 100})


def test_disabled_overrides_healthy():
    skills = [_disabled_skill("off")]
    fires = [fire("off", 24, FireKind.INVOKE), *[fire("off", 24) for _ in range(5)]]
    v = compute_vitals(skills, fires, window_days=14, now=NOW)[0]
    assert v.health == Health.DISABLED
    assert v.enabled is False


def test_token_split_and_dormant_cost_uses_always_on():
    s = mk_skill("dead", tokens=5000)
    s = type(s)(**{**s.__dict__, "description_tokens": 120, "enabled": True})
    vitals = compute_vitals([s], [], window_days=14, now=NOW)
    v = vitals[0]
    assert v.always_on_tokens == 120
    assert v.on_activation_tokens == 5000
    # dormant cost is the always-on (real per-session) number, not the body
    assert dormant_token_cost(vitals, days=14, now=NOW) == 120


def test_native_usage_reconciliation():
    s = mk_skill("docx")
    s = type(s)(**{**s.__dict__, "enabled": True})
    usage = {"docx": SkillUsage(usage_count=9, last_used_ms=int(NOW.timestamp() * 1000))}
    v = compute_vitals([s], [fire("docx", 20, FireKind.INVOKE)], window_days=14,
                       now=NOW, usage=usage)[0]
    assert v.invoke_count == 9  # max(jsonl=1, native=9)
    assert v.native_usage_count == 9
    assert v.source_discrepancy is not None  # 1 vs 9 disagreement surfaced


def test_disabled_excluded_from_dormant():
    s = _disabled_skill("off", tokens=4000)
    s = type(s)(**{**s.__dict__, "description_tokens": 90})
    vitals = compute_vitals([s], [], window_days=14, now=NOW)
    assert dormant_token_cost(vitals, days=14, now=NOW) == 0
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement** in `analysis.py`:
  - `_classify` gains `enabled: bool | None` param; first checks (after orphan): `if enabled is False: return Health.DISABLED`.
    ```python
    def _classify(*, has_skill, enabled, total_activity, window_activity,
                  invoke_count, engagement_ratio) -> Health:
        if not has_skill:
            return Health.ORPHAN
        if enabled is False:
            return Health.DISABLED
        if total_activity == 0:
            return Health.NEVER_FIRED
        if window_activity == 0:
            return Health.DORMANT
        if invoke_count > 0 and engagement_ratio < MISFIRE_THRESHOLD:
            return Health.MISFIRING
        return Health.HEALTHY
    ```
  - `compute_vitals` signature gains `usage: dict[str, SkillUsage] | None = None`.
  - Inside the per-name loop, after counting jsonl invokes:
    ```python
    native = (usage or {}).get(name)
    native_count = native.usage_count if native else 0
    jsonl_invokes = invoke_count
    invoke_count = max(jsonl_invokes, native_count)
    # reconcile last_fired with native lastUsedAt
    native_last = None
    if native and native.last_used_ms:
        native_last = datetime.fromtimestamp(native.last_used_ms / 1000, tz=now.tzinfo or UTC)
    candidates = [t for t in (last_fired, native_last) if t]
    last_fired = max(candidates) if candidates else None
    days_dormant = (now - last_fired).days if last_fired else None
    discrepancy = (f"jsonl={jsonl_invokes} native={native_count}"
                   if native_count and native_count != jsonl_invokes else None)
    ```
  - Build `SkillVitals(..., always_on_tokens=skill.description_tokens if skill else 0,
    on_activation_tokens=context_tokens, enabled=skill.enabled if skill else None,
    native_usage_count=native_count, source_discrepancy=discrepancy)`.
  - Pass `enabled=skill.enabled if skill else None` to `_classify`.
  - `_is_dormant_for`: add `if v.health == Health.DISABLED: return False` (disabled are not dead weight, they don't load).
  - `dormant_token_cost`: sum `v.always_on_tokens` (not context_tokens).
  - Add `dormant_on_activation_cost(vitals, ...)` summing `v.on_activation_tokens` for reporting.

- [ ] **Step 4: Run, expect pass** (`uv run --no-sync pytest tests/test_analysis.py -q`).
- [ ] **Step 5: Commit** — `git commit -am "feat(0.2.0): disabled status, token split, native reconciliation"`.

---

### Task 6: report + dashboard — columns, copy, disabled

**Files:** Modify `report.py`, `dashboard.py`, `templates/dashboard.html.j2`. Test: extend `tests/test_report.py`.

- [ ] **Step 1: Failing test**

```python
# append to tests/test_report.py
from skillvitals.models import Health


def test_report_splits_tokens_and_honest_headline():
    skills = [Skill("dead", "Use when X", "/d", "user", None, 4200, 30, {}, True)]
    # make it dormant + always-on small
    skills[0] = type(skills[0])(**{**skills[0].__dict__, "description_tokens": 110, "enabled": True})
    fires = [Fire("dead", "dead", None, FireKind.INVOKE,
                  datetime(2026, 4, 1, tzinfo=UTC), "s")]
    vitals = compute_vitals(skills, fires, window_days=14, now=NOW)
    md = render_markdown(vitals, now=NOW, dormant_days=14)
    assert "always-on" in md and "on-fire" in md
    assert "per session" in md
    # honest: the per-session number is the always-on (110 -> "110"), not the body
    assert "load only when they activate" in md.lower() or "on activation" in md.lower()
```

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement.**
  - `report._STATUS_LABEL`: add `Health.DISABLED: "🚫 disabled"`.
  - `render_markdown` table header → `| skill | fires | engaged | always-on | on-fire | last seen | status |`; rows use `humanize(v.always_on_tokens)` and `humanize(v.on_activation_tokens)`.
  - Replace the headline block with the honest two-part copy:
    ```python
    from .analysis import dormant_on_activation_cost
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
    ```
  - `build_rich_table`: add `always-on` + `on-fire` columns; add color for DISABLED (`"red"`); footnote line via caller.
  - `dashboard._rows`: add `always_on`, `on_fire` keys; `_STATUS_LABEL`/class includes `disabled`. Template: add two columns (`always-on`, `on-fire`) replacing single `ctx`; update the summary cards copy to "always-loaded tokens / session".

- [ ] **Step 4: Run, expect pass.**
- [ ] **Step 5: Commit** — `git commit -am "feat(0.2.0): honest token columns + disabled in report/dashboard"`.

---

### Task 7: pipeline + cli + server — wire enablement & usage, corrected copy

**Files:** Modify `pipeline.py`, `cli.py`, `server.py`. Test: extend `tests/test_cli.py`, `conftest.py`.

- [ ] **Step 1: Failing test** — extend `conftest.fake_claude_home` to write a `settings.json` (with `enabledPlugins` marking `data-analysis`'s plugin disabled via a marketplace) and a `~/.claude.json` with `skillUsage`. Then:

```python
# append to tests/test_cli.py
def test_scan_shows_disabled_and_token_split(fake_claude_home):
    r = _run(["scan", "--now", "2026-05-25"], fake_claude_home)
    assert r.exit_code == 0
    assert "always-on" in r.output and "on-fire" in r.output
    assert "per session" in r.output
```

(Update `conftest.py` `fake_claude_home` to also create `home/"settings.json"` with an `enabledPlugins`/`extraKnownMarketplaces` for the `local-skills` dir, and `tmp_path/".claude.json"` with a `skillUsage` entry for `docx`.)

- [ ] **Step 2: Run, expect fail.**
- [ ] **Step 3: Implement.**
  - `pipeline.collect`: after `scan_skills`, call `annotate_enablement(skills, config.home, config.cwd)`; read `usage = read_skill_usage(config.home)`; pass `usage=usage` into `compute_vitals`. Store `usage` and enabled info on the `Snapshot` if needed.
  - `cli.scan`: keep using `build_rich_table`; the corrected dormant copy already comes via report or replicate the two-part line; surface count of disabled.
  - `server` tool docstrings: update `vitals_dormancy`/`vitals_scan` wording to "always-loaded" framing (cosmetic; the markdown comes from `render_markdown`).

- [ ] **Step 4: Run, expect pass** (`uv run --no-sync pytest -q`).
- [ ] **Step 5: Commit** — `git commit -am "feat(0.2.0): wire enablement + native usage through pipeline/cli/server"`.

---

### Task 8: verification (PRD V1–V4) on real data

**Files:** none (verification). Uses superpowers:verification-before-completion.

- [ ] **V1** — run `skillvitals scan` against real `~/.claude`; record the new always-on per-session number; confirm it is low-thousands, not ~23k. Paste output.
- [ ] **V2** — regression test (in `test_analysis.py`, already added `test_disabled_overrides_healthy`) confirms a disabled skill with recent fires is not `healthy`. Confirm green.
- [ ] **V3** — print real JSONL invoke counts vs `skillUsage.usageCount`; document divergence + whether `usageCount` looks per-session or per-invocation; confirm reconciliation surfaces discrepancies.
- [ ] **V4** — `uv run --no-sync pytest -q` all green; `uv run --no-sync ruff check src tests` clean.

---

### Task 9: messaging + release prep (no publish without user + fresh token)

**Files:** `README.md`, `pyproject.toml` (version → 0.2.0), regenerate `docs/skillvitals-demo.gif` + `docs/launch/*`, draft Reddit reply.

- [ ] Update README: replace "per session" framing with always-on vs on-fire; bump demo numbers; note disabled status + window-scoped health.
- [ ] Bump `version = "0.2.0"`.
- [ ] Regenerate demo home/GIF (`scripts/gen_demo_home.py` adds a `disabled` example + token split) and re-render `vhs scripts/demo.tape`.
- [ ] Update `docs/launch/*` posts to the corrected number/framing.
- [ ] Draft the honest Reddit follow-up (already outlined with the user).
- [ ] **STOP for user:** do not `uv publish` or push public until the user revokes the exposed 0.1.0 token, provides a project-scoped token, and approves. Build + `uv build` locally; leave publish as the gated final step.

---

## Self-review

**Spec coverage:** G1 token split → Tasks 1,2,5,6. G2 disabled → Tasks 1,3,5,6. G3 native usage → Tasks 1,4,5. G4 messaging → Task 9. Verification V1–V4 → Task 8. PRD §5.2 mapping → Task 3. PRD §6 reconciliation rule (max/latest, surface divergence) → Task 5. ✓

**Placeholder scan:** no TBD/"handle errors" placeholders; each code step shows code. ✓

**Type consistency:** `description_tokens`/`enabled`/`plugin_ref` on Skill (Task 1) used in Tasks 3,5. `always_on_tokens`/`on_activation_tokens`/`native_usage_count`/`source_discrepancy` on SkillVitals (Task 1) used in Tasks 5,6. `SkillUsage(usage_count,last_used_ms)` (Task 1) used in Tasks 4,5. `Health.DISABLED` (Task 1) used in 5,6. `annotate_enablement`/`read_enabled_plugins`/`read_marketplaces` (Task 3) used in Task 7. `read_skill_usage` (Task 4) used in Task 7. `dormant_on_activation_cost` (Task 5) used in Task 6. ✓

**Note on test construction:** tests mutate frozen dataclasses via `type(s)(**{**s.__dict__, ...})`; acceptable for tests. Production code uses `dataclasses.replace` (Task 3).
