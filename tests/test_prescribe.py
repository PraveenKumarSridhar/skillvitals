from datetime import UTC, datetime

from skillvitals.analysis import compute_vitals
from skillvitals.models import Fire, FireKind, Severity, Skill
from skillvitals.prescribe import prescribe, rewrite_description

NOW = datetime(2026, 5, 25, tzinfo=UTC)


def sk(name, desc, valid=True, q=50, tokens=2000):
    return Skill(name, desc, f"/{name}", "user", None, tokens, q, {}, valid)


def vitals_for(skills, fires=()):
    return compute_vitals(list(skills), list(fires), window_days=14, now=NOW)


def rules_for(prescriptions, name):
    return {p.rule for p in prescriptions if p.skill_name == name}


def test_short_description_flagged():
    v = vitals_for([sk("x", "does stuff")])
    rx = prescribe(v)
    assert "description-too-short" in rules_for(rx, "x")


def test_missing_trigger_words_flagged():
    v = vitals_for([sk("x", "A very long description that nonetheless never explains "
                             "the situations in which it should activate at all, sadly.")])
    assert "no-trigger-words" in rules_for(prescribe(v), "x")


def test_invalid_frontmatter_is_critical():
    v = vitals_for([sk("x", "", valid=False)])
    rx = [p for p in prescribe(v) if p.skill_name == "x" and p.rule == "invalid-frontmatter"]
    assert rx and rx[0].severity == Severity.CRITICAL


def test_redundant_skills_detected():
    desc = "Use when the user wants to convert and edit PDF documents and forms in place"
    v = vitals_for([sk("pdf", desc), sk("pdf2", desc + " quickly")])
    rx = prescribe(v)
    assert "redundant" in rules_for(rx, "pdf") or "redundant" in rules_for(rx, "pdf2")


def test_dormant_high_cost_flagged():
    fires = [Fire("big", "big", None, FireKind.INVOKE,
                  datetime(2026, 1, 1, tzinfo=UTC), "s")]
    v = vitals_for([sk("big", "Use when you need the big thing", tokens=6000)], fires)
    assert "dormant-cost" in rules_for(prescribe(v, now=NOW), "big")


def test_healthy_skill_minimal_prescriptions():
    desc = ("Use when the user wants to analyze A/B test results (lift, p-values, "
            "sample size) and needs a rigorous, decision-grade readout.")
    fires = [Fire("good", "good", None, FireKind.INVOKE, NOW, "s"),
             *[Fire("good", "good", None, FireKind.ATTRIBUTION, NOW, "s") for _ in range(4)]]
    v = vitals_for([sk("good", desc, q=95)], fires)
    crit = [p for p in prescribe(v, now=NOW)
            if p.skill_name == "good" and p.severity == Severity.CRITICAL]
    assert crit == []


class _FakeClient:
    """Mimics the anthropic client surface prescribe uses, without network."""

    class messages:
        @staticmethod
        def create(**kwargs):
            class _Block:
                text = "Use when the user wants a crisp, rewritten description."

            class _Resp:
                content = [_Block()]

            return _Resp()


def test_rewrite_description_uses_injected_client():
    s = sk("x", "does stuff")
    out = rewrite_description(s, client=_FakeClient())
    assert "Use when" in out


def test_rewrite_description_without_client_returns_none():
    assert rewrite_description(sk("x", "does stuff"), client=None) is None
