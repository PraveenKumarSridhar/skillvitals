"""Path resolution and configuration.

Everything reads from the user's Claude Code data under ``~/.claude``. All
locations are overridable via environment variables so tests (and curious
users) can point skillvitals at a fixture tree:

  SKILLVITALS_CLAUDE_HOME   -> the .claude dir (default ~/.claude)
  CLAUDE_CONFIG_DIR         -> respected as a fallback (Claude Code's own var)
  SKILLVITALS_HOME          -> where the db + dashboard live (default ~/.skillvitals)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .registry import ScanRoot

DORMANT_DAYS_DEFAULT = 14
HISTORY_DAYS_DEFAULT = 30


def claude_home() -> Path:
    env = os.environ.get("SKILLVITALS_CLAUDE_HOME") or os.environ.get("CLAUDE_CONFIG_DIR")
    if env:
        return Path(env).expanduser()
    return Path.home() / ".claude"


def skillvitals_home() -> Path:
    env = os.environ.get("SKILLVITALS_HOME")
    base = Path(env).expanduser() if env else Path.home() / ".skillvitals"
    return base


@dataclass
class Config:
    home: Path  # the .claude dir
    sv_home: Path  # ~/.skillvitals
    cwd: Path

    @property
    def projects_dir(self) -> Path:
        return self.home / "projects"

    @property
    def db_path(self) -> Path:
        return self.sv_home / "db.sqlite"

    @property
    def dashboard_path(self) -> Path:
        return self.sv_home / "dashboard.html"

    def skill_roots(self) -> list[ScanRoot]:
        """Roots to scan, in precedence order. Plugin-cache files self-tag as
        'plugin' regardless of label (see registry._classify_path)."""
        roots = [
            ScanRoot(self.home / "skills", "user"),
            ScanRoot(self.home / "plugins" / "cache", "plugin"),
        ]
        project_skills = self.cwd / ".claude" / "skills"
        if project_skills.exists():
            roots.insert(0, ScanRoot(project_skills, "project"))
        return roots


def load_config(cwd: Path | None = None) -> Config:
    return Config(
        home=claude_home(),
        sv_home=skillvitals_home(),
        cwd=Path(cwd) if cwd else Path.cwd(),
    )
