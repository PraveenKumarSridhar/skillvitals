"""Orchestration shared by the CLI and the MCP server.

Single source of truth for "scan everything, parse logs, compute vitals,
optionally persist". Both surfaces call this so they can never diverge.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

from .analysis import compute_vitals
from .config import Config, load_config
from .enablement import annotate_enablement
from .logparser import parse_sessions
from .models import Fire, ParseError, SessionInfo, Skill, SkillVitals
from .registry import scan_skills
from .storage import Database
from .usage import read_skill_usage


@dataclass
class Snapshot:
    config: Config
    skills: list[Skill]
    fires: list[Fire]
    sessions: list[SessionInfo]
    errors: list[ParseError]
    vitals: list[SkillVitals] = field(default_factory=list)
    now: datetime = field(default_factory=lambda: datetime.now(UTC))


def collect(
    config: Config | None = None,
    *,
    window_days: int = 14,
    now: datetime | None = None,
    persist: bool = True,
) -> Snapshot:
    """Scan registry + parse logs + compute vitals. Persists to SQLite by default."""
    config = config or load_config()
    now = now or datetime.now(UTC)

    skills = scan_skills(config.skill_roots())
    skills = annotate_enablement(skills, config.home, config.cwd)
    fires, sessions, errors = parse_sessions(config.projects_dir)
    usage = read_skill_usage(config.home)
    vitals = compute_vitals(skills, fires, window_days=window_days, now=now, usage=usage)

    if persist:
        try:
            db = Database(config.db_path)
            db.ingest(skills, fires, sessions)
            db.close()
        except Exception:
            # Persistence is a convenience, not a requirement — never block a read.
            pass

    return Snapshot(
        config=config, skills=skills, fires=fires, sessions=sessions,
        errors=errors, vitals=vitals, now=now,
    )
