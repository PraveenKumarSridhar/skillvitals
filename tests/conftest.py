import json

import pytest


@pytest.fixture
def fake_claude_home(tmp_path):
    """A minimal but realistic ~/.claude tree: 3 skills + a session log."""
    home = tmp_path / ".claude"
    skills = home / "skills"

    def write_skill(name, desc):
        p = skills / name / "SKILL.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(f"---\nname: {name}\ndescription: {desc}\n---\n" + "body " * 200,
                     encoding="utf-8")

    write_skill("docx", "Use when the user wants to create or edit Word .docx documents")
    write_skill("data-analysis", "Use when analyzing datasets with pandas and computing statistics")
    write_skill("leakcheck", "Use when scanning for secrets and credential leaks in a repo")

    proj = home / "projects" / "-Users-x-proj"
    proj.mkdir(parents=True)
    rows = [
        {"type": "assistant", "timestamp": "2026-05-24T10:00:00Z", "sessionId": "s1",
         "cwd": "/Users/x/proj", "version": "2.1.146",
         "message": {"role": "assistant", "usage": {"output_tokens": 100},
                     "content": [{"type": "tool_use", "name": "Skill", "id": "t1",
                                  "input": {"skill": "user:docx"}}]}},
        {"type": "assistant", "timestamp": "2026-05-24T10:01:00Z", "sessionId": "s1",
         "attributionSkill": "user:docx", "attributionPlugin": "user",
         "message": {"role": "assistant", "usage": {"output_tokens": 50}, "content": []}},
    ]
    (proj / "s1.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n", encoding="utf-8")
    return home
