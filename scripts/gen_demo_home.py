"""Create a fake ~/.claude home populated with the synthetic demo skills + logs,
so `skillvitals scan` can be recorded for the demo GIF without touching any real
personal data.

    python scripts/gen_demo_home.py /tmp/demo-claude
"""

from __future__ import annotations

import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

# Reuse the same fabricated data the demo dashboard uses.
sys.path.insert(0, str(Path(__file__).parent))
from gen_demo import ACTIVITY, NOW, SKILLS  # noqa: E402


def _skill_md(name: str, desc: str, ctx_tokens: int) -> str:
    head = f"---\nname: {name}\ndescription: {desc}\n---\n\n# {name}\n\n"
    # estimate_tokens = ceil(chars / 4); pad the body to hit the target token count.
    target_chars = ctx_tokens * 4
    pad = max(0, target_chars - len(head))
    body = ("This skill's instructions go here. " * ((pad // 35) + 1))[:pad]
    return head + body


def main():
    home = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/demo-claude")
    skills_dir = home / "skills"
    for name, desc, ctx, _q in SKILLS:
        p = skills_dir / name / "SKILL.md"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(_skill_md(name, desc, ctx), encoding="utf-8")

    proj = home / "projects" / "-demo-project"
    proj.mkdir(parents=True, exist_ok=True)
    rows = []
    for name, (inv, att, ago) in ACTIVITY.items():
        ts = (NOW - timedelta(days=ago)).isoformat()
        for _ in range(inv):
            rows.append({"type": "assistant", "timestamp": ts, "sessionId": "demo",
                         "cwd": "/demo", "version": "2.1.146",
                         "message": {"role": "assistant", "usage": {"output_tokens": 80},
                                     "content": [{"type": "tool_use", "name": "Skill", "id": "t",
                                                  "input": {"skill": f"demo:{name}"}}]}})
        for _ in range(att):
            rows.append({"type": "assistant", "timestamp": ts, "sessionId": "demo",
                         "attributionSkill": f"demo:{name}", "attributionPlugin": "demo",
                         "message": {"role": "assistant", "usage": {"output_tokens": 40},
                                     "content": []}})
    (proj / "demo.jsonl").write_text("\n".join(json.dumps(r) for r in rows) + "\n",
                                     encoding="utf-8")

    # enable-state: all skills enabled except changelog-writer (plugin turned off),
    # so the demo showcases the `disabled` status. Marketplace maps the skills dir.
    enabled = {f"{name}@demo": (name != "changelog-writer") for name, *_ in SKILLS}
    (home / "settings.json").write_text(json.dumps({
        "enabledPlugins": enabled,
        "extraKnownMarketplaces": {
            "demo": {"source": {"source": "directory", "path": str(skills_dir)}},
        },
    }), encoding="utf-8")
    print(f"demo home ready at {home} ({len(SKILLS)} skills, {len(rows)} log lines)")


if __name__ == "__main__":
    main()
