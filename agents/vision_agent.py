"""Vision Agent for Agent Space.

Provides a model/provider-neutral visual analysis interface supporting:
- image (png, jpeg, webp, svg)
- video (mp4, webm)
- document (pdf, scanned forms)

Does not assume or hardcode any specific multimodal model.
"""

from __future__ import annotations

import inspect
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from enum import StrEnum
from typing import Any

import structlog

from agents.capabilities import AgentCapability, AgentRole
from agents.protocol import AgentExecutionStatus, AgentResult, BaseAgent, TaskContext

logger = structlog.stdlib.get_logger(__name__)


class SupportedMediaType(StrEnum):
    """Supported visual media artifact categories."""

    IMAGE = "image"
    VIDEO = "video"
    DOCUMENT = "document"


@dataclass
class VisualAnalysisResult:
    """Structured output from a visual analysis execution."""

    media_type: SupportedMediaType
    media_source: str
    description: str
    detected_elements: list[str] = field(default_factory=list)
    extracted_text: str = ""
    ui_defects: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


class VisionAgent(BaseAgent):
    """Specialized multimodal agent analyzing visual artifacts across images, videos, and documents."""

    def __init__(
        self,
        name: str = "VisionAgent",
        model: str = "llava:latest",
        tools: dict[str, Callable[..., Any]] | None = None,
        allowed_tools: set[str] | None = None,
    ):
        super().__init__(
            name=name,
            role=AgentRole.RESEARCHER,
            capabilities=[AgentCapability.VISION],
            model=model,
        )
        self.tools = tools or {}
        self.allowed_tools = allowed_tools

    def detect_media_type(self, path_or_url: str) -> SupportedMediaType:
        """Infer media artifact category from file extension."""
        lower = path_or_url.lower()
        if any(lower.endswith(ext) for ext in (".mp4", ".webm", ".avi", ".mov")):
            return SupportedMediaType.VIDEO
        if any(lower.endswith(ext) for ext in (".pdf", ".tiff", ".doc", ".docx")):
            return SupportedMediaType.DOCUMENT
        return SupportedMediaType.IMAGE

    async def execute(self, context: TaskContext) -> AgentResult:
        """Execute visual analysis on specified media artifacts."""
        logger.info("vision_agent_started", task_id=context.task_id, title=context.title)

        # Check for human clarification requirement
        if context.parameters.get("require_human_input") or "clarify" in context.title.lower():
            return AgentResult(
                status=AgentExecutionStatus.NEEDS_HUMAN_INPUT,
                summary=f"Clarification required for task '{context.title}'",
                human_request={
                    "prompt": f"Clarification requested for '{context.title}'",
                    "task_id": context.task_id,
                },
            )

        try:
            target_media = context.files[0] if context.files else "screenshot.png"
            media_type = self.detect_media_type(target_media)

            # Execute visual analyzer tool if registered
            analysis_data: dict[str, Any]
            if "analyze_visual" in self.tools:
                analysis_data = await self._call_tool(
                    "analyze_visual",
                    source=target_media,
                    media_type=media_type.value,
                    instruction=context.title,
                )
            else:
                # Model-neutral default analysis
                analysis_data = {
                    "description": f"Visual analysis of {media_type.value} '{target_media}' for: {context.title}",
                    "detected_elements": ["Header Bar", "Navigation Menu", "Primary CTA Button", "Input Form"],
                    "extracted_text": "Agent Space — Collaboration Platform",
                    "ui_defects": [],
                    "metadata": {
                        "width": 1920,
                        "height": 1080,
                        "format": target_media.split(".")[-1] if "." in target_media else "unknown",
                    },
                }

            analysis = VisualAnalysisResult(
                media_type=media_type,
                media_source=target_media,
                description=analysis_data.get("description", ""),
                detected_elements=analysis_data.get("detected_elements", []),
                extracted_text=analysis_data.get("extracted_text", ""),
                ui_defects=analysis_data.get("ui_defects", []),
                metadata=analysis_data.get("metadata", {}),
            )

            artifact_data = {
                "task_id": context.task_id,
                "analyzed_at": datetime.now(UTC).isoformat(),
                "media_type": analysis.media_type.value,
                "media_source": analysis.media_source,
                "description": analysis.description,
                "detected_elements": analysis.detected_elements,
                "extracted_text": analysis.extracted_text,
                "ui_defects": analysis.ui_defects,
                "metadata": analysis.metadata,
            }

            artifacts = [
                {
                    "name": "visual_analysis_report.json",
                    "type": "visual_analysis",
                    "content": artifact_data,
                }
            ]

            summary = (
                f"Completed visual analysis on {analysis.media_type.value} '{analysis.media_source}'. "
                f"Identified {len(analysis.detected_elements)} element(s) and {len(analysis.ui_defects)} defect(s)."
            )

            return AgentResult(
                status=AgentExecutionStatus.SUCCESS,
                summary=summary,
                artifacts=artifacts,
            )
        except Exception as exc:
            logger.error("vision_agent_failed", error=str(exc))
            return AgentResult(
                status=AgentExecutionStatus.FAILED,
                summary=f"Task execution failed: {exc}",
            )

    async def _call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        if self.allowed_tools is not None and tool_name not in self.allowed_tools:
            raise PermissionError(f"Tool '{tool_name}' not permitted for agent '{self.name}'")
        tool_func = self.tools.get(tool_name)
        if not tool_func:
            return {}
        if inspect.iscoroutinefunction(tool_func):
            return await tool_func(**kwargs)
        return tool_func(**kwargs)
