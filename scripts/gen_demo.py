"""Generate a synthetic demo dashboard (no personal data).

Builds a fabricated-but-realistic set of skills + fires, runs them through the
real pipeline, and renders the dashboard. Used for the public README/demo so we
never ship anyone's actual skill usage.

    python scripts/gen_demo.py docs/sample-dashboard.html
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta

from skillvitals.analysis import compute_vitals
from skillvitals.dashboard import write_dashboard
from skillvitals.models import Fire, FireKind, Skill
from skillvitals.prescribe import prescribe

NOW = datetime(2026, 5, 25, tzinfo=UTC)

# (name, description, ctx_tokens, quality) — generic, illustrative skills only.
SKILLS = [
    ("docx", "Use when the user wants to create or edit Word .docx documents", 2100, 82),
    ("pdf", "Use when the user needs to read, split, or fill PDF files", 1800, 80),
    ("frontend-design", "Use when building or restyling React/HTML UI components", 6400, 88),
    ("data-analysis", "Analyzes datasets and computes summary statistics", 4200, 34),
    ("leakcheck", "Use when scanning a repository for secrets and credential leaks", 3100, 76),
    ("ab-test-coach", "Use when reviewing experiment results, lift, and p-values", 5700, 70),
    ("changelog-writer", "Use when drafting release notes from a git history", 1400, 64),
    ("sql-tuner", "Use when optimizing slow SQL queries and indexes", 2600, 72),
]

# fabricated activity: (name, invokes, attributions, last_active_days_ago)
ACTIVITY = {
    "docx": (47, 120, 0),
    "pdf": (23, 60, 1),
    "frontend-design": (31, 140, 0),
    "ab-test-coach": (2, 2, 3),          # invoked, barely used -> misfiring
    "sql-tuner": (4, 9, 9),
    "leakcheck": (1, 3, 40),             # fired once, long ago -> dormant
    # data-analysis, changelog-writer: never fired
}


def build():
    skills = [Skill(n, d, f"/skills/{n}/SKILL.md", "user", None, ctx, q, {"total": q}, True)
              for (n, d, ctx, q) in SKILLS]
    fires: list[Fire] = []
    for name, (inv, att, ago) in ACTIVITY.items():
        ts = NOW - timedelta(days=ago)
        for _ in range(inv):
            fires.append(Fire(name, name, None, FireKind.INVOKE, ts, "demo"))
        for _ in range(att):
            fires.append(Fire(name, name, None, FireKind.ATTRIBUTION, ts, "demo"))
    return skills, fires


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "docs/sample-dashboard.html"
    skills, fires = build()
    vitals = compute_vitals(skills, fires, window_days=14, now=NOW)
    rx = prescribe(vitals, now=NOW)
    path = write_dashboard(vitals, out, now=NOW, dormant_days=14, prescriptions=rx,
                           generated_at="2026-05-25 (demo data)")
    print(f"wrote {path}")


if __name__ == "__main__":
    main()
