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
