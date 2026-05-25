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


def test_read_skill_usage_merges_bare_and_namespaced(tmp_path):
    (tmp_path / ".claude").mkdir()
    (tmp_path / ".claude.json").write_text(json.dumps({"skillUsage": {
        "resume-tailoring": {"usageCount": 1, "lastUsedAt": 100},
        "resume-tailoring:resume-tailoring": {"usageCount": 3, "lastUsedAt": 500},
    }}), encoding="utf-8")
    u = read_skill_usage(tmp_path / ".claude")
    assert u["resume-tailoring"].usage_count == 3  # max
    assert u["resume-tailoring"].last_used_ms == 500  # latest


def test_read_skill_usage_missing(tmp_path):
    (tmp_path / ".claude").mkdir()
    assert read_skill_usage(tmp_path / ".claude") == {}
