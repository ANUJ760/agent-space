"""Tests for M41 — Vision Agent.

Validates:
- VisionAgent metadata, role, and capabilities
- Multimodal artifact detection across image, video, and document
- Visual element detection, OCR text extraction, and UI defect identification
- Structured visual analysis artifact generation
"""

from agents.protocol import AgentExecutionStatus, TaskContext
from agents.vision_agent import SupportedMediaType, VisionAgent


class TestVisionAgent:
    def test_agent_initialization(self) -> None:
        agent = VisionAgent(name="VisualInspector")
        assert agent.name == "VisualInspector"
        assert "vision" in agent.capabilities

    def test_media_type_detection(self) -> None:
        agent = VisionAgent()
        assert agent.detect_media_type("dashboard.png") == SupportedMediaType.IMAGE
        assert agent.detect_media_type("assets/logo.svg") == SupportedMediaType.IMAGE
        assert agent.detect_media_type("recordings/demo.mp4") == SupportedMediaType.VIDEO
        assert agent.detect_media_type("recordings/walkthrough.webm") == SupportedMediaType.VIDEO
        assert agent.detect_media_type("specs/design_spec.pdf") == SupportedMediaType.DOCUMENT

    async def test_image_analysis_execution(self) -> None:
        agent = VisionAgent()
        ctx = TaskContext(
            task_id="t-vis-1",
            project_id="p-1",
            title="Inspect landing page layout",
            files=["ui/landing.png"],
        )

        result = await agent.execute(ctx)
        assert result.status == AgentExecutionStatus.SUCCESS
        assert len(result.artifacts) == 1
        artifact = result.artifacts[0]
        assert artifact["name"] == "visual_analysis_report.json"

        content = artifact["content"]
        assert content["media_type"] == "image"
        assert content["media_source"] == "ui/landing.png"
        assert len(content["detected_elements"]) > 0
        assert "Agent Space" in content["extracted_text"]

    async def test_video_and_document_analysis(self) -> None:
        async def mock_vision_tool(source: str, media_type: str, instruction: str) -> dict:
            return {
                "description": f"Analyzed {media_type} source: {source}",
                "detected_elements": ["Title Page", "Section 1 Header", "Table of Metrics"],
                "extracted_text": "System Architecture v2.0",
                "ui_defects": ["Contrast ratio too low on header"],
                "metadata": {"pages": 12, "type": media_type},
            }

        agent = VisionAgent(tools={"analyze_visual": mock_vision_tool})

        # Test Document
        ctx_doc = TaskContext(
            task_id="t-vis-doc",
            project_id="p-1",
            title="Review PDF specification",
            files=["docs/arch.pdf"],
        )
        res_doc = await agent.execute(ctx_doc)
        doc_report = res_doc.artifacts[0]["content"]
        assert doc_report["media_type"] == "document"
        assert doc_report["metadata"]["pages"] == 12
        assert len(doc_report["ui_defects"]) == 1

        # Test Video
        ctx_vid = TaskContext(
            task_id="t-vis-vid",
            project_id="p-1",
            title="Inspect screencast demo",
            files=["recordings/user_flow.mp4"],
        )
        res_vid = await agent.execute(ctx_vid)
        vid_report = res_vid.artifacts[0]["content"]
        assert vid_report["media_type"] == "video"
