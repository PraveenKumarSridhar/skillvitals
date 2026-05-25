from skillvitals.models import Health, Skill, SkillUsage


def test_disabled_health_exists():
    assert Health.DISABLED.value == "disabled"


def test_skill_new_fields_default():
    s = Skill("x", "d", "/x", "user", None, 100, 50, {}, True)
    assert s.description_tokens == 0
    assert s.enabled is None
    assert s.plugin_ref is None


def test_skill_usage_dataclass():
    u = SkillUsage(usage_count=3, last_used_ms=1779698256246)
    assert u.usage_count == 3 and u.last_used_ms == 1779698256246
