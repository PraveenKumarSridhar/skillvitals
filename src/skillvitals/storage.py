"""SQLite persistence for skills, fires, and sessions.

Local-only (PRD: "no cloud component"). Ingestion is idempotent: fires are
de-duplicated on a natural key so re-running a scan accumulates genuinely new
activity without double-counting history.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

from .logparser import parse_timestamp
from .models import Fire, FireKind, SessionInfo, Skill

_SCHEMA = """
CREATE TABLE IF NOT EXISTS skills (
    name TEXT PRIMARY KEY,
    description TEXT,
    path TEXT,
    source TEXT,
    plugin TEXT,
    context_tokens INTEGER,
    quality_score INTEGER,
    frontmatter_valid INTEGER,
    quality_breakdown TEXT
);
CREATE TABLE IF NOT EXISTS fires (
    skill_id TEXT,
    name TEXT,
    plugin TEXT,
    kind TEXT,
    ts TEXT,
    session_id TEXT,
    cwd TEXT,
    git_branch TEXT,
    cli_version TEXT,
    input_tokens INTEGER,
    output_tokens INTEGER,
    cache_read_tokens INTEGER,
    cache_creation_tokens INTEGER,
    UNIQUE(session_id, ts, kind, name, skill_id)
);
CREATE INDEX IF NOT EXISTS idx_fires_name ON fires(name);
CREATE INDEX IF NOT EXISTS idx_fires_ts ON fires(ts);
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    project TEXT,
    cwd TEXT,
    cli_version TEXT,
    first_ts TEXT,
    last_ts TEXT,
    fire_count INTEGER
);
"""


def _iso(dt) -> str | None:
    return dt.isoformat() if dt else None


class Database:
    def __init__(self, path: Path | str):
        self.path = Path(path)
        if self.path.parent and str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(str(self.path))
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    def __enter__(self) -> Database:
        return self

    def __exit__(self, *exc) -> None:
        self.close()

    # ---- ingestion ---------------------------------------------------------
    def ingest(self, skills: list[Skill], fires: list[Fire], sessions: list[SessionInfo]) -> None:
        c = self.conn
        c.executemany(
            """INSERT OR REPLACE INTO skills
               (name, description, path, source, plugin, context_tokens,
                quality_score, frontmatter_valid, quality_breakdown)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [
                (s.name, s.description, s.path, s.source, s.plugin, s.context_tokens,
                 s.quality_score, int(s.frontmatter_valid), json.dumps(s.quality_breakdown))
                for s in skills
            ],
        )
        c.executemany(
            """INSERT OR IGNORE INTO fires
               (skill_id, name, plugin, kind, ts, session_id, cwd, git_branch, cli_version,
                input_tokens, output_tokens, cache_read_tokens, cache_creation_tokens)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            [
                (f.skill_id, f.name, f.plugin, f.kind.value, _iso(f.timestamp), f.session_id,
                 f.cwd, f.git_branch, f.cli_version, f.input_tokens, f.output_tokens,
                 f.cache_read_tokens, f.cache_creation_tokens)
                for f in fires
            ],
        )
        c.executemany(
            """INSERT OR REPLACE INTO sessions
               (session_id, project, cwd, cli_version, first_ts, last_ts, fire_count)
               VALUES (?,?,?,?,?,?,?)""",
            [
                (s.session_id, s.project, s.cwd, s.cli_version, _iso(s.first_ts),
                 _iso(s.last_ts), s.fire_count)
                for s in sessions
            ],
        )
        c.commit()

    # ---- loading -----------------------------------------------------------
    def load_skills(self) -> list[Skill]:
        rows = self.conn.execute("SELECT * FROM skills ORDER BY name").fetchall()
        return [
            Skill(
                name=r["name"], description=r["description"] or "", path=r["path"] or "",
                source=r["source"] or "user", plugin=r["plugin"],
                context_tokens=r["context_tokens"] or 0, quality_score=r["quality_score"] or 0,
                quality_breakdown=json.loads(r["quality_breakdown"] or "{}"),
                frontmatter_valid=bool(r["frontmatter_valid"]),
            )
            for r in rows
        ]

    def load_fires(self) -> list[Fire]:
        rows = self.conn.execute("SELECT * FROM fires").fetchall()
        return [
            Fire(
                skill_id=r["skill_id"], name=r["name"], plugin=r["plugin"],
                kind=FireKind(r["kind"]), timestamp=parse_timestamp(r["ts"]),
                session_id=r["session_id"], cwd=r["cwd"], git_branch=r["git_branch"],
                cli_version=r["cli_version"], input_tokens=r["input_tokens"] or 0,
                output_tokens=r["output_tokens"] or 0,
                cache_read_tokens=r["cache_read_tokens"] or 0,
                cache_creation_tokens=r["cache_creation_tokens"] or 0,
            )
            for r in rows
        ]

    def load_sessions(self) -> list[SessionInfo]:
        rows = self.conn.execute("SELECT * FROM sessions").fetchall()
        return [
            SessionInfo(
                session_id=r["session_id"], project=r["project"], cwd=r["cwd"],
                cli_version=r["cli_version"], first_ts=parse_timestamp(r["first_ts"]),
                last_ts=parse_timestamp(r["last_ts"]), fire_count=r["fire_count"] or 0,
            )
            for r in rows
        ]
