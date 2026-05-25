import json
from datetime import UTC

from skillvitals.logparser import parse_line, parse_sessions
from skillvitals.models import FireKind

# Shapes mirror real ~/.claude session JSONL discovered during recon.
INVOKE = {
    "type": "assistant",
    "timestamp": "2026-05-22T21:18:41.670Z",
    "sessionId": "sess-1",
    "cwd": "/Users/x/proj",
    "version": "2.1.146",
    "gitBranch": "main",
    "message": {
        "role": "assistant",
        "usage": {"input_tokens": 6, "output_tokens": 494, "cache_read_input_tokens": 46549,
                  "cache_creation_input_tokens": 4876},
        "content": [
            {"type": "tool_use", "name": "Skill", "id": "toolu_1",
             "input": {"skill": "resume-tailoring:resume-tailoring", "args": "JD: ..."}}
        ],
    },
}
ATTRIBUTION = {
    "type": "assistant",
    "timestamp": "2026-05-24T22:43:45.030Z",
    "sessionId": "sess-1",
    "cwd": "/Users/x/proj",
    "version": "2.1.146",
    "attributionSkill": "superpowers:writing-skills",
    "attributionPlugin": "superpowers",
    "message": {"role": "assistant",
                "usage": {"input_tokens": 3, "output_tokens": 120,
                          "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 200},
                "content": [{"type": "text", "text": "working"}]},
}
UNRELATED = {"type": "user", "timestamp": "2026-05-24T22:00:00.000Z", "sessionId": "sess-1",
             "message": {"role": "user", "content": "hi"}}


def test_parse_line_invoke():
    fires = parse_line(INVOKE)
    assert len(fires) == 1
    f = fires[0]
    assert f.kind == FireKind.INVOKE
    assert f.skill_id == "resume-tailoring:resume-tailoring"
    assert f.name == "resume-tailoring"
    assert f.plugin == "resume-tailoring"
    assert f.session_id == "sess-1"
    assert f.cli_version == "2.1.146"
    assert f.timestamp.tzinfo is not None
    assert f.timestamp.astimezone(UTC).hour == 21
    assert f.output_tokens == 494


def test_parse_line_attribution_with_plugin_and_tokens():
    fires = parse_line(ATTRIBUTION)
    assert len(fires) == 1
    f = fires[0]
    assert f.kind == FireKind.ATTRIBUTION
    assert f.name == "writing-skills"
    assert f.plugin == "superpowers"
    assert f.cache_read_tokens == 1000
    assert f.cache_creation_tokens == 200


def test_parse_line_unrelated_yields_nothing():
    assert parse_line(UNRELATED) == []


def test_parse_sessions_aggregates(tmp_path):
    proj = tmp_path / "-Users-x-proj"
    proj.mkdir(parents=True)
    f = proj / "sess-1.jsonl"
    lines = [json.dumps(INVOKE), json.dumps(ATTRIBUTION), "{not valid json", json.dumps(UNRELATED)]
    f.write_text("\n".join(lines) + "\n", encoding="utf-8")

    fires, sessions, errors = parse_sessions(tmp_path)

    assert len(fires) == 2  # invoke + attribution
    assert len(errors) == 1  # the malformed line
    assert errors[0].line_no == 3
    assert len(sessions) == 1
    s = sessions[0]
    assert s.session_id == "sess-1"
    assert s.project == "-Users-x-proj"
    assert s.fire_count == 1  # invokes only count as fires
    assert s.first_ts is not None and s.last_ts is not None
    assert s.last_ts >= s.first_ts


def test_parse_sessions_missing_dir_is_empty(tmp_path):
    fires, sessions, errors = parse_sessions(tmp_path / "nope")
    assert fires == [] and sessions == [] and errors == []
