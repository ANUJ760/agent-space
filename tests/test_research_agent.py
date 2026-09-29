"""Tests for M38 — Research Agent.

Validates:
- ResearchAgent metadata, role, and capabilities
- Untrusted content sanitization (HTML stripping, prompt injection defense, control character removal)
- Evidence extraction and source metadata tracking
- Structured research artifact generation in AgentResult
"""

from agents.protocol import AgentExecutionStatus, TaskContext
from agents.research_agent import ResearchAgent, sanitize_untrusted_content


class TestResearchAgent:
    def test_sanitize_untrusted_content(self) -> None:
        malicious = "<script>alert('xss')</script>Normal text <img src=x onerror=hack()>\x00\x07"
        clean = sanitize_untrusted_content(malicious)
        assert "<script>" not in clean
        assert "<img" not in clean
        assert "Normal text" in clean
        assert "\x00" not in clean

    def test_agent_initialization(self) -> None:
        agent = ResearchAgent(name="DeepResearcher")
        assert agent.name == "DeepResearcher"
        assert agent.role == "RESEARCHER"
        assert "research" in agent.capabilities

    async def test_execution_with_search_tool(self) -> None:
        async def mock_search(queries: list[str]) -> list[dict[str, str]]:
            return [
                {
                    "url": "https://ietf.org/rfc/rfc9110.html",
                    "title": "HTTP Semantics RFC",
                    "content": "<p>RFC 9110 defines HTTP semantics, status codes, and headers.</p>",
                },
                {
                    "url": "https://auth0.com/docs/tokens",
                    "title": "Token Best Practices",
                    "content": "Access tokens should have short lifespans (5-15 minutes).",
                },
            ]

        agent = ResearchAgent(tools={"web_search": mock_search})
        ctx = TaskContext(
            task_id="t-res-1",
            project_id="p-1",
            title="Investigate HTTP caching and token lifespans",
        )

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert len(result.artifacts) == 1
        artifact = result.artifacts[0]
        assert artifact["name"] == "research_report.json"

        content = artifact["content"]
        assert content["sources_count"] == 2
        assert len(content["sources"]) == 2
        assert content["sources"][0]["url"] == "https://ietf.org/rfc/rfc9110.html"
        assert "<p>" not in content["sources"][0]["snippet"]
        assert len(content["key_findings"]) == 2
