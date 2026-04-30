from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from copilot import _build_llm

from .retrieval import ReportRetrievalTool


def _extract_json_object(raw_text: str) -> dict[str, Any]:
    text = raw_text.strip()
    if "```" in text:
        parts = text.split("```")
        for part in parts:
            candidate = part.strip()
            if candidate.startswith("json"):
                candidate = candidate[4:].strip()
            if candidate.startswith("{") and candidate.endswith("}"):
                return json.loads(candidate)
    if text.startswith("{") and text.endswith("}"):
        return json.loads(text)
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return json.loads(text[start : end + 1])
    raise ValueError("No JSON object found in model response")


def _plain_text(structured_content: dict[str, Any]) -> str:
    lines = [structured_content.get("executive_summary", "")]
    for section in structured_content.get("sections", []):
        lines.append(section.get("heading", "Section"))
        lines.extend(section.get("bullets", []))
    lines.extend(structured_content.get("continuity_notes", []))
    return "\n".join(line for line in lines if line)


@dataclass
class AgentOutput:
    structured_content: dict[str, Any]
    metadata: dict[str, Any]
    plain_text: str


class ReportHistoryTool:
    def __init__(self, retriever: ReportRetrievalTool) -> None:
        self.retriever = retriever

    def latest(self, report_type: str) -> dict[str, Any] | None:
        return self.retriever.latest_report(report_type)


class ReportAgent:
    def __init__(self, retriever: ReportRetrievalTool) -> None:
        self.retriever = retriever
        self.report_history = ReportHistoryTool(retriever)

    def _fallback_content(
        self,
        report_type: str,
        telemetry: dict[str, Any],
        alerts: list[dict[str, Any]],
        scheduled_tasks: list[dict[str, Any]],
        tool_analysis: dict[str, Any] | None = None,
    ) -> AgentOutput:
        timestamp = datetime.now(timezone.utc).isoformat()
        alert_lines = [
            f"{alert.get('level', 'info').upper()}: {alert.get('message', 'No message')}"
            for alert in alerts[-3:]
        ] or ["No critical alerts captured in the latest window."]
        structured_content = {
            "title": "Daily Full Report" if report_type == "daily_full_report" else "Notification Report",
            "executive_summary": "Automated fallback report generated from live telemetry, alerts, and scheduling context for operator review and direct guidance.",
            "sections": [
                {
                    "heading": "Operational Status",
                    "bullets": [
                        f"UV Dose is currently {telemetry.get('uv_dose_mj_cm2', 'N/A')} mJ/cm2.",
                        f"Lamp Power is currently {telemetry.get('lamp_power_pct', 'N/A')}%.",
                        f"Lamp Health is currently {telemetry.get('lamp_health_pct', 'N/A')}%.",
                    ],
                },
                {
                    "heading": "Risks and Deviations",
                    "bullets": alert_lines + (
                        [
                            tool_analysis.get("pyod", {}).get("summary"),
                            tool_analysis.get("prophet", {}).get("summary"),
                        ]
                        if tool_analysis
                        else []
                    ),
                },
                {
                    "heading": "Recommended Actions",
                    "bullets": [
                        "Review the latest alert history and confirm whether any deviation is persistent or transient.",
                        "Validate UV dose, lamp condition, and water quality before issuing any operational direction.",
                        f"Use the reviewed context to prepare direct operator guidance for {len(scheduled_tasks)} queued task(s).",
                    ],
                },
            ],
            "continuity_notes": [
                "Fallback report used because the primary LLM pipeline was unavailable.",
                "Direct guidance should be confirmed by an operator before field execution.",
            ],
            "sources": ["Live telemetry", "Recent alerts", "Scheduled task queue"],
        }
        return AgentOutput(
            structured_content=structured_content,
            metadata={
                "title": structured_content["title"],
                "timestamp": timestamp,
                "type": report_type,
            },
            plain_text=_plain_text(structured_content),
        )

    def generate(
        self,
        report_type: str,
        telemetry: dict[str, Any],
        alerts: list[dict[str, Any]],
        scheduled_tasks: list[dict[str, Any]],
        generation_reason: str | None = None,
        tool_analysis: dict[str, Any] | None = None,
    ) -> AgentOutput:
        try:
            llm = _build_llm()
            latest_notification = self.report_history.latest("notification_report")
            latest_same_type = self.report_history.latest(report_type)
            knowledge_chunks = self.retriever.retrieve_knowledge(
                f"{report_type} reactor conditions maintenance compliance operational summary"
            )
            prior_report_chunks = self.retriever.retrieve_prior_reports(
                f"{report_type} continuity previous operational summary"
            )
            prompt = f"""
You are a ReAct-style UV reactor reporting agent with agentic RAG.
Use the retrieval tool evidence, latest report continuity, and current user data.
Write for operators who need clear review outcomes and direct next-step guidance.
Do not reveal your chain-of-thought.

Report type: {report_type}
Generation reason: {generation_reason or "scheduled or operator initiated"}
Current telemetry and user data:
{self.retriever.user_data(telemetry, alerts, scheduled_tasks)}

Latest report of this type:
{json.dumps(latest_same_type["structured_content"], indent=2) if latest_same_type else "None"}

Latest notification report:
{json.dumps(latest_notification["structured_content"], indent=2) if latest_notification else "None"}

Retrieved internal documents:
{json.dumps(knowledge_chunks, indent=2)}

Retrieved prior report evidence:
{json.dumps(prior_report_chunks, indent=2)}

PyOD and Prophet tool outputs:
{json.dumps(tool_analysis or {}, indent=2)}

Return ONLY valid JSON with this shape:
{{
  "title": "string",
  "executive_summary": "string",
  "sections": [
    {{"heading": "Operational Status", "bullets": ["...", "..."]}},
    {{"heading": "Risks and Deviations", "bullets": ["...", "..."]}},
    {{"heading": "Recommended Actions", "bullets": ["step-by-step operator guidance...", "..."]}}
  ],
  "continuity_notes": ["..."],
  "sources": ["..."]
}}

Requirements:
- The executive summary must read like a reviewed operations brief, not a generic recap.
- "Recommended Actions" must contain concrete, ordered, operator-ready instructions suitable for a polished PDF handoff.
- Ground each action in the telemetry, alerts, scheduling context, or retrieved evidence.
- Keep bullets concise but specific.
"""
            response = llm.invoke(prompt).content
            structured_content = _extract_json_object(response)

            timestamp = datetime.now(timezone.utc).isoformat()
            metadata = {
                "title": structured_content.get("title", "UV Reactor Report"),
                "timestamp": timestamp,
                "type": report_type,
            }
            return AgentOutput(
                structured_content=structured_content,
                metadata=metadata,
                plain_text=_plain_text(structured_content),
            )
        except Exception:
            return self._fallback_content(report_type, telemetry, alerts, scheduled_tasks, tool_analysis)

    def self_correct(
        self,
        report_type: str,
        prior_output: AgentOutput,
        error_message: str,
    ) -> AgentOutput:
        try:
            llm = _build_llm()
            prompt = f"""
Repair the structured report JSON for report type {report_type}.
The LaTeX or PDF generation failed with this error:
{error_message}

Previous JSON:
{json.dumps(prior_output.structured_content, indent=2)}

Return ONLY corrected JSON with the same schema and plain-text-safe content.
"""
            response = llm.invoke(prompt).content
            structured_content = _extract_json_object(response)
            metadata = {
                **prior_output.metadata,
                "title": structured_content.get("title", prior_output.metadata["title"]),
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            return AgentOutput(
                structured_content=structured_content,
                metadata=metadata,
                plain_text=_plain_text(structured_content),
            )
        except Exception:
            return prior_output
