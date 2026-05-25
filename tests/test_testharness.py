from skillvitals.testharness import grade_rate, make_cli_runner, measure_activation, synth_prompts


def test_synth_prompts_deterministic_and_derived():
    desc = "Use when the user wants to analyze A/B test results and compute lift and p-values"
    a = synth_prompts(desc, n=8)
    b = synth_prompts(desc, n=8)
    assert a == b  # deterministic
    assert len(a) == 8
    blob = " ".join(a).lower()
    assert "lift" in blob or "a/b" in blob or "analyze" in blob


def test_synth_prompts_handles_empty():
    assert synth_prompts("", n=3) == []


def test_grade_rate_boundaries():
    assert grade_rate(0.9) == "green"
    assert grade_rate(0.7) == "green"
    assert grade_rate(0.5) == "yellow"
    assert grade_rate(0.3) == "yellow"
    assert grade_rate(0.1) == "red"


def test_measure_activation_with_fake_runner():
    prompts = ["activate yes", "no", "yes please", "nope"]

    def runner(prompt: str) -> bool:
        return "yes" in prompt

    res = measure_activation("docx", prompts, runner=runner)
    assert res.skill_name == "docx"
    assert res.prompts_run == 4
    assert res.activations == 2
    assert res.activation_rate == 0.5
    assert res.grade == "yellow"


def test_make_cli_runner_detects_activation_from_session_log(tmp_path):
    # Fake `claude -p --output-format json` output carrying a session id,
    # plus a session log that shows the skill activated. No real process.
    import json

    home = tmp_path / ".claude"
    proj = home / "projects" / "p"
    proj.mkdir(parents=True)
    (proj / "sess-xyz.jsonl").write_text(
        json.dumps({"type": "assistant", "timestamp": "2026-05-25T00:00:00Z",
                    "sessionId": "sess-xyz", "attributionSkill": "x:docx",
                    "message": {"role": "assistant", "content": []}}) + "\n",
        encoding="utf-8",
    )

    class _Completed:
        returncode = 0
        stdout = json.dumps({"session_id": "sess-xyz", "result": "done"})
        stderr = ""

    def fake_run(*args, **kwargs):
        return _Completed()

    runner = make_cli_runner("docx", claude_home=home, run=fake_run)
    assert runner("please edit my docx") is True


def test_make_cli_runner_handles_failure_gracefully(tmp_path):
    def boom(*a, **k):
        raise FileNotFoundError("claude not installed")

    runner = make_cli_runner("docx", claude_home=tmp_path, run=boom)
    assert runner("anything") is False
