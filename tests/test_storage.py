from datetime import UTC, datetime

from skillvitals.models import Fire, FireKind, SessionInfo, Skill
from skillvitals.storage import Database


def _skill(name="docx"):
    return Skill(name=name, description="Use when editing Word docs", path=f"/s/{name}/SKILL.md",
                 source="user", plugin=None, context_tokens=2100, quality_score=80,
                 quality_breakdown={"total": 80}, frontmatter_valid=True)


def _fire(ts, kind=FireKind.INVOKE, name="docx", sid="s1"):
    return Fire(skill_id=name, name=name, plugin=None, kind=kind,
                timestamp=datetime(2026, 5, ts, 12, 0, tzinfo=UTC), session_id=sid,
                output_tokens=100)


def _session(sid="s1"):
    return SessionInfo(session_id=sid, project="-proj", cwd="/proj", cli_version="2.1.146",
                       first_ts=datetime(2026, 5, 1, tzinfo=UTC),
                       last_ts=datetime(2026, 5, 20, tzinfo=UTC), fire_count=1)


def test_ingest_and_load_roundtrip(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    db.ingest([_skill()], [_fire(10), _fire(11, FireKind.ATTRIBUTION)], [_session()])

    skills = db.load_skills()
    assert len(skills) == 1
    assert skills[0].name == "docx"
    assert skills[0].context_tokens == 2100
    assert skills[0].quality_breakdown["total"] == 80

    fires = db.load_fires()
    assert len(fires) == 2
    assert {f.kind for f in fires} == {FireKind.INVOKE, FireKind.ATTRIBUTION}
    assert all(f.timestamp.tzinfo is not None for f in fires)

    sessions = db.load_sessions()
    assert len(sessions) == 1 and sessions[0].session_id == "s1"
    db.close()


def test_reingest_is_idempotent(tmp_path):
    path = tmp_path / "db.sqlite"
    db = Database(path)
    fires = [_fire(10), _fire(11, FireKind.ATTRIBUTION)]
    db.ingest([_skill()], fires, [_session()])
    db.ingest([_skill()], fires, [_session()])  # same data again
    assert len(db.load_fires()) == 2  # no duplicates
    assert len(db.load_skills()) == 1

    # a genuinely new fire accumulates
    db.ingest([], [_fire(12)], [])
    assert len(db.load_fires()) == 3
    db.close()


def test_schema_has_expected_tables(tmp_path):
    db = Database(tmp_path / "db.sqlite")
    names = {r[0] for r in db.conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
    assert {"skills", "fires", "sessions"} <= names
    db.close()
