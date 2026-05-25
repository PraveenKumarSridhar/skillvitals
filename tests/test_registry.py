from pathlib import Path

from skillvitals.registry import quality_score, scan_skills


def _write(p: Path, text: str) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


GOOD_FM = """---
name: good
description: Use when the user wants to analyze A/B test results (lift, p-values, sample size) and needs a rigorous, decision-grade readout.
---

# Good skill

Body content here that adds to the token cost.
""" + ("x" * 400)


def test_scan_parses_frontmatter_and_scores(tmp_path):
    user_root = tmp_path / "skills"
    _write(user_root / "good" / "SKILL.md", GOOD_FM)
    _write(user_root / "bad" / "SKILL.md", "no frontmatter here, just text")

    skills = {s.name: s for s in scan_skills([user_root])}

    assert "good" in skills and "bad" in skills
    good = skills["good"]
    assert good.description.startswith("Use when the user wants to analyze")
    assert good.frontmatter_valid is True
    assert good.source == "user"
    assert good.context_tokens > 100
    assert good.quality_score > skills["bad"].quality_score

    bad = skills["bad"]
    assert bad.frontmatter_valid is False
    assert bad.name == "bad"  # falls back to directory name


def test_dedupe_by_name_keeps_largest(tmp_path):
    a = tmp_path / "a" / "skills"
    b = tmp_path / "b" / "skills"
    _write(a / "dup" / "SKILL.md", "---\nname: dup\ndescription: short\n---\nsmall")
    _write(b / "dup" / "SKILL.md", "---\nname: dup\ndescription: short\n---\n" + "y" * 5000)

    skills = scan_skills([a, b])
    dups = [s for s in skills if s.name == "dup"]
    assert len(dups) == 1
    assert dups[0].context_tokens > 1000  # kept the larger copy


def test_plugin_source_and_name_from_path(tmp_path):
    cache = tmp_path / "plugins" / "cache"
    p = cache / "claude-plugins-official" / "superpowers" / "5.1.0" / "skills" / "tdd" / "SKILL.md"
    _write(p, "---\nname: tdd\ndescription: Use when implementing a feature, write tests first.\n---\nbody")

    skills = {s.name: s for s in scan_skills([cache])}
    assert skills["tdd"].source == "plugin"
    assert skills["tdd"].plugin == "superpowers"
    assert skills["tdd"].namespaced_id == "superpowers:tdd"


def test_frontmatter_with_colon_in_description_still_parses(tmp_path):
    # Real skills put colons inside their description (e.g. quoted examples),
    # which is not strictly-valid YAML. We must still extract name/description.
    fm = (
        "---\n"
        "name: study-coach\n"
        'description: Use when the user names a topic (e.g. "Module 3: caching deep dive")\n'
        "---\n# body"
    )
    root = tmp_path / "skills"
    _write(root / "study-coach" / "SKILL.md", fm)
    skills = {s.name: s for s in scan_skills([(root, "user")])}
    assert "study-coach" in skills
    s = skills["study-coach"]
    assert s.frontmatter_valid is True
    assert "Module 3" in s.description
    assert s.quality_score > 0


def test_quality_score_rewards_triggers_and_specificity():
    weak = quality_score("does stuff", has_name=True, valid=True)
    strong = quality_score(
        "Use when the user wants to analyze A/B test results (lift, p-values) "
        "for Day 9 experiments and needs a decision-grade readout.",
        has_name=True,
        valid=True,
    )
    assert strong["total"] > weak["total"]
    assert strong["total"] <= 100 and weak["total"] >= 0
