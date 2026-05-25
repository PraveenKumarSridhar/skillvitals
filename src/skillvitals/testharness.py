"""Activation testing (vitals_test).

Generates a synthetic prompt battery from a skill's own `description`, runs each
prompt through Claude Code in headless mode, and measures how often the skill
actually activates. Outputs green / yellow / red.

The live runner is opt-in and isolated: `measure_activation` takes a `runner`
callable, so the default unit tests never spawn a `claude` process or spend
tokens. `make_cli_runner` builds the real subprocess-backed runner.
"""

from __future__ import annotations

import json
import re
import subprocess
from collections.abc import Callable
from pathlib import Path

from .logparser import parse_sessions
from .models import FireKind, Skill, TestResult

GREEN, YELLOW = 0.7, 0.3

_TEMPLATES = [
    "{c}",
    "I need help with this: {c}",
    "Can you {c}?",
    "Please help me {c}.",
    "{c} — can you handle this?",
    "Quick one: {c}",
]


def _clauses(description: str) -> list[str]:
    d = re.sub(r"^\s*use when\b[:,]?\s*", "", description.strip(), flags=re.I)
    parts = re.split(r"[.;]|(?:,\s)", d)
    return [p.strip() for p in parts if len(p.strip()) >= 8]


def synth_prompts(description: str, n: int = 10) -> list[str]:
    """Deterministically derive up to `n` test prompts from a description."""
    clauses = _clauses(description or "")
    if not clauses:
        return []
    prompts: list[str] = []
    i = 0
    while len(prompts) < n:
        clause = clauses[i % len(clauses)]
        template = _TEMPLATES[i % len(_TEMPLATES)]
        prompts.append(template.format(c=clause))
        i += 1
        if i > n * 4:  # safety against degenerate inputs
            break
    return prompts[:n]


def synth_prompts_llm(skill: Skill, n: int, client) -> list[str]:
    """LLM-backed prompt generation (opt-in). Falls back to rule-based on failure."""
    if client is None:
        return synth_prompts(skill.description, n)
    prompt = (
        f"Generate {n} realistic, varied user prompts that SHOULD trigger a Claude Code "
        f"skill described as: '{skill.description}'. Return one prompt per line, no numbering."
    )
    try:
        resp = client.messages.create(
            model="claude-haiku-4-5-20251001", max_tokens=600,
            messages=[{"role": "user", "content": prompt}],
        )
        lines = [ln.strip("-• \t") for ln in resp.content[0].text.splitlines() if ln.strip()]
        return lines[:n] or synth_prompts(skill.description, n)
    except Exception:
        return synth_prompts(skill.description, n)


def grade_rate(rate: float) -> str:
    if rate >= GREEN:
        return "green"
    if rate >= YELLOW:
        return "yellow"
    return "red"


def measure_activation(
    skill_name: str, prompts: list[str], *, runner: Callable[[str], bool]
) -> TestResult:
    """Run each prompt through `runner` and tally activations."""
    detail = []
    activations = 0
    for p in prompts:
        fired = bool(runner(p))
        activations += int(fired)
        detail.append({"prompt": p, "activated": fired})
    n = len(prompts)
    rate = (activations / n) if n else 0.0
    return TestResult(
        skill_name=skill_name, prompts_run=n, activations=activations,
        activation_rate=rate, grade=grade_rate(rate), detail=detail,
    )


def make_cli_runner(
    skill_name: str,
    *,
    claude_home: Path,
    claude_bin: str = "claude",
    cwd: Path | None = None,
    timeout: int = 120,
    run: Callable = subprocess.run,
) -> Callable[[str], bool]:
    """Build a runner that shells out to headless Claude Code and detects whether
    `skill_name` activated, by inspecting the session log the run produced.

    `run` is injectable for testing. Any failure (missing CLI, timeout, bad
    output) is swallowed and reported as a non-activation.
    """
    claude_home = Path(claude_home)
    projects_dir = claude_home / "projects"

    def runner(prompt: str) -> bool:
        try:
            completed = run(
                [claude_bin, "-p", prompt, "--output-format", "json"],
                capture_output=True, text=True, timeout=timeout, cwd=str(cwd) if cwd else None,
            )
        except Exception:
            return False
        if getattr(completed, "returncode", 1) != 0:
            return False
        session_id = None
        try:
            data = json.loads(completed.stdout or "{}")
            session_id = data.get("session_id") or data.get("sessionId")
        except (json.JSONDecodeError, AttributeError):
            return False

        fires, _, _ = parse_sessions(projects_dir)
        for f in fires:
            if f.name == skill_name and (session_id is None or f.session_id == session_id):
                if f.kind in (FireKind.INVOKE, FireKind.ATTRIBUTION):
                    return True
        return False

    return runner
