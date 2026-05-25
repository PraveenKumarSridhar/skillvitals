"""Session log parser.

Reads Claude Code session JSONL from ``~/.claude/projects/<project>/<id>.jsonl``
and extracts two activation signals per skill:

  * INVOKE      — an assistant ``tool_use`` block named "Skill" (a true fire).
  * ATTRIBUTION — a line tagged with ``attributionSkill`` (an assistant message
                  produced while the skill was active; measures engagement).

Design goals (PRD risk: "log format isn't a stable API"):
  * Schema-version aware — captures the CLI ``version`` on every fire.
  * Fail-soft per line — a malformed line becomes a ``ParseError`` we surface,
    never a crash and never a silent drop.
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .models import Fire, FireKind, ParseError, SessionInfo, normalize_name


def parse_timestamp(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        # Python 3.11+ fromisoformat handles 'Z', but normalize for safety.
        return datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (ValueError, TypeError):
        return None


def _split_id(skill_id: str) -> tuple[str, str | None]:
    """('superpowers:writing-plans') -> name 'writing-plans', plugin 'superpowers'."""
    name = normalize_name(skill_id)
    plugin = skill_id.rsplit(":", 1)[0] if ":" in skill_id else None
    return name, plugin


def _usage(message: dict) -> dict[str, int]:
    u = message.get("usage") or {}
    return {
        "input_tokens": int(u.get("input_tokens") or 0),
        "output_tokens": int(u.get("output_tokens") or 0),
        "cache_read_tokens": int(u.get("cache_read_input_tokens") or 0),
        "cache_creation_tokens": int(u.get("cache_creation_input_tokens") or 0),
    }


def parse_line(obj: dict) -> list[Fire]:
    """Extract zero or more Fire records from a single parsed JSONL object."""
    fires: list[Fire] = []
    ts = parse_timestamp(obj.get("timestamp"))
    session_id = obj.get("sessionId") or ""
    cwd = obj.get("cwd")
    git_branch = obj.get("gitBranch")
    version = obj.get("version")
    message = obj.get("message") if isinstance(obj.get("message"), dict) else {}
    usage = _usage(message)

    # 1) explicit Skill() invocation
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if (
                isinstance(block, dict)
                and block.get("type") == "tool_use"
                and block.get("name") == "Skill"
            ):
                skill_id = (block.get("input") or {}).get("skill")
                if skill_id:
                    name, plugin = _split_id(skill_id)
                    fires.append(
                        Fire(
                            skill_id=skill_id,
                            name=name,
                            plugin=plugin,
                            kind=FireKind.INVOKE,
                            timestamp=ts or datetime.min.replace(tzinfo=None),
                            session_id=session_id,
                            cwd=cwd,
                            git_branch=git_branch,
                            cli_version=version,
                            **usage,
                        )
                    )

    # 2) attribution (engagement) signal
    attr = obj.get("attributionSkill")
    if attr:
        name, plugin_from_id = _split_id(attr)
        plugin = obj.get("attributionPlugin") or plugin_from_id
        fires.append(
            Fire(
                skill_id=attr,
                name=name,
                plugin=plugin,
                kind=FireKind.ATTRIBUTION,
                timestamp=ts or datetime.min.replace(tzinfo=None),
                session_id=session_id,
                cwd=cwd,
                git_branch=git_branch,
                cli_version=version,
                **usage,
            )
        )

    return fires


def _parse_file(path: Path, project: str) -> tuple[list[Fire], dict, list[ParseError]]:
    fires: list[Fire] = []
    errors: list[ParseError] = []
    # session meta keyed by session_id
    meta: dict[str, dict] = {}
    try:
        raw_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError as e:
        return fires, meta, [ParseError(str(path), 0, f"unreadable: {e}")]

    for i, line in enumerate(raw_lines, start=1):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError as e:
            errors.append(ParseError(str(path), i, f"json: {e.msg}"))
            continue
        if not isinstance(obj, dict):
            continue

        sid = obj.get("sessionId") or path.stem
        m = meta.setdefault(
            sid,
            {"project": project, "cwd": obj.get("cwd"), "version": obj.get("version"),
             "first": None, "last": None, "fires": 0},
        )
        ts = parse_timestamp(obj.get("timestamp"))
        if ts:
            if m["first"] is None or ts < m["first"]:
                m["first"] = ts
            if m["last"] is None or ts > m["last"]:
                m["last"] = ts
        if obj.get("cwd"):
            m["cwd"] = obj["cwd"]
        if obj.get("version"):
            m["version"] = obj["version"]

        try:
            line_fires = parse_line(obj)
        except Exception as e:  # defensive: never let one weird line abort the file
            errors.append(ParseError(str(path), i, f"shape: {type(e).__name__}: {e}"))
            continue
        for f in line_fires:
            fires.append(f)
            if f.kind == FireKind.INVOKE:
                meta[f.session_id if f.session_id in meta else sid]["fires"] += 1

    return fires, meta, errors


def parse_sessions(projects_dir: Path) -> tuple[list[Fire], list[SessionInfo], list[ParseError]]:
    """Parse every session JSONL under ``projects_dir``.

    Returns (fires, sessions, errors). Missing directory yields empty results.
    """
    projects_dir = Path(projects_dir)
    all_fires: list[Fire] = []
    all_errors: list[ParseError] = []
    sessions: list[SessionInfo] = []

    if not projects_dir.exists():
        return all_fires, sessions, all_errors

    for project_dir in sorted(p for p in projects_dir.iterdir() if p.is_dir()):
        for jsonl in sorted(project_dir.glob("*.jsonl")):
            fires, meta, errors = _parse_file(jsonl, project_dir.name)
            all_fires.extend(fires)
            all_errors.extend(errors)
            for sid, m in meta.items():
                sessions.append(
                    SessionInfo(
                        session_id=sid,
                        project=m["project"],
                        cwd=m["cwd"],
                        cli_version=m["version"],
                        first_ts=m["first"],
                        last_ts=m["last"],
                        fire_count=m["fires"],
                    )
                )

    return all_fires, sessions, all_errors
