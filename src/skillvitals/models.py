"""Core data structures shared across skillvitals modules.

These are plain dataclasses (data, not behavior). The analysis layer turns
``Skill`` + ``Fire`` records into ``SkillVitals``, which is the single object
consumed by report / prescribe / dashboard / cli.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


def normalize_name(skill_id: str) -> str:
    """Reduce a namespaced id ('plugin:skill') to its bare skill segment.

    Logs use 'plugin:skill'; frontmatter uses bare 'skill'. We join on the
    bare segment so a skill matches regardless of how it was referenced.
    """
    return skill_id.rsplit(":", 1)[-1].strip()


@dataclass(frozen=True)
class Skill:
    """A discovered skill from the registry scan."""

    name: str  # bare name from frontmatter (or directory)
    description: str
    path: str  # absolute path to SKILL.md
    source: str  # 'user' | 'plugin' | 'project'
    plugin: str | None  # plugin name when known (from path)
    context_tokens: int  # estimated tokens of the SKILL.md
    quality_score: int  # 0-100 description quality
    quality_breakdown: dict[str, int]  # component -> points
    frontmatter_valid: bool
    description_tokens: int = 0  # always-on cost: the part loaded every session
    enabled: bool | None = None  # None = could not determine
    plugin_ref: str | None = None  # 'plugin@marketplace' (enable-state key)

    @property
    def namespaced_id(self) -> str:
        if self.plugin:
            return f"{self.plugin}:{self.name}"
        return self.name


class FireKind(str, Enum):
    INVOKE = "invoke"  # explicit Skill() tool_use — a true "fire"
    ATTRIBUTION = "attribution"  # assistant message produced while skill active


@dataclass(frozen=True)
class Fire:
    """A single activation signal extracted from a session log."""

    skill_id: str  # namespaced id as it appears in the log
    name: str  # normalized bare name (join key)
    plugin: str | None
    kind: FireKind
    timestamp: datetime  # timezone-aware
    session_id: str
    cwd: str | None = None
    git_branch: str | None = None
    cli_version: str | None = None
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0


@dataclass(frozen=True)
class SkillUsage:
    """Claude Code's own per-skill ledger from ~/.claude.json (skillUsage)."""

    usage_count: int
    last_used_ms: int | None


@dataclass(frozen=True)
class SessionInfo:
    session_id: str
    project: str  # the project dir name under ~/.claude/projects
    cwd: str | None
    cli_version: str | None
    first_ts: datetime | None
    last_ts: datetime | None
    fire_count: int = 0


@dataclass(frozen=True)
class ParseError:
    """A line we could not interpret — surfaced, never silently dropped."""

    file: str
    line_no: int
    reason: str


class Health(str, Enum):
    HEALTHY = "healthy"
    DORMANT = "dormant"
    MISFIRING = "misfiring"
    NEVER_FIRED = "never-fired"
    ORPHAN = "orphan"  # in logs but not installed
    DISABLED = "disabled"  # installed on disk but its plugin is not enabled


@dataclass
class SkillVitals:
    """Per-skill rollup — the unit every surface renders."""

    name: str
    skill: Skill | None  # None for orphan skills (in logs, not installed)
    invoke_count: int
    attribution_count: int
    window_invoke_count: int
    window_attribution_count: int
    last_fired: datetime | None
    first_fired: datetime | None
    days_dormant: int | None  # days since last activation, None if never fired
    context_tokens: int
    tokens_per_fire: int  # context tokens consumed when it activates
    engagement_ratio: float
    health: Health
    sessions: int  # distinct sessions it appeared in
    always_on_tokens: int = 0  # description tokens — loaded every session
    on_activation_tokens: int = 0  # full SKILL.md tokens — loaded only when it fires
    enabled: bool | None = None
    native_usage_count: int = 0  # from Claude Code's own skillUsage ledger
    source_discrepancy: str | None = None  # set when jsonl and native counts disagree

    @property
    def total_fires(self) -> int:
        return self.invoke_count

    @property
    def status_emoji(self) -> str:
        return {
            Health.HEALTHY: "✅",
            Health.DORMANT: "⚠️",
            Health.MISFIRING: "⚠️",
            Health.NEVER_FIRED: "💤",
            Health.ORPHAN: "❓",
            Health.DISABLED: "🚫",
        }[self.health]


class Severity(str, Enum):
    INFO = "info"
    WARN = "warn"
    CRITICAL = "critical"


@dataclass
class Prescription:
    """A suggested fix for a skill. Show, don't apply (v1)."""

    skill_name: str
    rule: str  # machine id, e.g. 'description-too-short'
    severity: Severity
    message: str  # human-readable explanation
    suggestion: str | None = None  # concrete proposed change (e.g. rewritten desc)
    diff: str | None = None  # optional config/text diff


@dataclass
class TestResult:
    """Outcome of running synthetic prompts against a skill (vitals_test)."""

    skill_name: str
    prompts_run: int
    activations: int  # how many prompts triggered the skill
    activation_rate: float
    grade: str  # 'green' | 'yellow' | 'red'
    detail: list[dict] = field(default_factory=list)
