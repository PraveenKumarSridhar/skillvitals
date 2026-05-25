import asyncio
import os


def _call(tool, args, home):
    os.environ["SKILLVITALS_CLAUDE_HOME"] = str(home)
    os.environ["SKILLVITALS_HOME"] = str(home.parent / ".skillvitals")
    from skillvitals.server import mcp

    async def go():
        result = await mcp.call_tool(tool, args)
        # FastMCP returns a result object; pull text out of its content blocks
        blocks = getattr(result, "content", result)
        texts = [getattr(b, "text", str(b)) for b in blocks]
        return "\n".join(texts)

    return asyncio.run(go())


def test_server_lists_all_vitals_tools(fake_claude_home):
    from skillvitals.server import mcp

    names = {t.name for t in asyncio.run(mcp.list_tools())}
    assert {"vitals_scan", "vitals_history", "vitals_dormancy", "vitals_report",
            "vitals_prescribe", "vitals_test", "vitals_dashboard"} <= names


def test_vitals_scan_tool_returns_markdown(fake_claude_home):
    out = _call("vitals_scan", {"days": 14}, fake_claude_home)
    assert "skillvitals" in out
    assert "docx" in out


def test_vitals_dormancy_tool(fake_claude_home):
    out = _call("vitals_dormancy", {"days": 14}, fake_claude_home)
    assert "always-loaded" in out.lower()
    assert "on activation" in out.lower()
