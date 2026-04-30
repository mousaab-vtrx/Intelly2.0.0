from __future__ import annotations

import asyncio
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4

from .agent import AgentOutput, ReportAgent
from .cache import ReportCache
from .pdf_pipeline import LatexPdfPipeline
from .repository import ReportRecord, ReportRepository
from .retrieval import ReportRetrievalTool


ContextProvider = Callable[[], dict[str, Any]]


@dataclass
class ReportServiceConfig:
    base_dir: Path
    artifacts_dir: Path
    redis_url: str
    database_url: str


class ReportService:
    def __init__(self, config: ReportServiceConfig, context_provider: ContextProvider) -> None:
        self.config = config
        self.context_provider = context_provider
        self.repository = ReportRepository(config.database_url)
        self.cache = ReportCache(config.redis_url)
        self.retriever = ReportRetrievalTool(config.base_dir, self.repository)
        self.agent = ReportAgent(self.retriever)
        self.pipeline = LatexPdfPipeline(config.artifacts_dir)

    def startup(self) -> None:
        self.repository.init_db()
        self.cache.connect()

    def shutdown(self) -> None:
        self.cache.close()

    async def ensure_active_notification_report(self) -> ReportRecord:
        active = self.get_active_report()
        if active:
            return active
        return await self.generate_report("notification_report", "startup bootstrap")

    def _today(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _cache_report(self, record: ReportRecord) -> None:
        if record["report_type"] == "notification_report":
            self.cache.set_json("report:active", record, ttl_seconds=3600)
        if record["report_type"] == "daily_full_report" and record.get("report_date"):
            self.cache.set_json(f"report:daily:{record['report_date']}", record, ttl_seconds=86400)
        if record.get("pdf_path"):
            self.cache.cache_pdf(record["id"], Path(record["pdf_path"]))

    def get_active_report(self) -> ReportRecord | None:
        cached = self.cache.get_json("report:active")
        if cached:
            return cached
        record = self.repository.get_active_notification_report()
        if record:
            self._cache_report(record)
        return record

    def get_daily_today_report(self) -> ReportRecord | None:
        report_date = self._today()
        cached = self.cache.get_json(f"report:daily:{report_date}")
        if cached:
            return cached
        record = self.repository.get_daily_report_for_date(report_date)
        if record:
            self._cache_report(record)
        return record

    def get_report(self, report_id: str) -> ReportRecord | None:
        return self.repository.get_report(report_id)

    async def generate_report(self, report_type: str, reason: str | None = None) -> ReportRecord:
        return await asyncio.to_thread(self._generate_report_sync, report_type, reason)

    def _build_record(self, report_id: str, report_type: str, agent_output: AgentOutput, pdf_path: Path, tex_path: Path) -> ReportRecord:
        report_date = self._today() if report_type == "daily_full_report" else None
        return {
            "id": report_id,
            "title": agent_output.metadata["title"],
            "report_type": report_type,
            "is_active": report_type == "notification_report",
            "created_at": agent_output.metadata["timestamp"],
            "report_date": report_date,
            "structured_content": agent_output.structured_content,
            "plain_text": agent_output.plain_text,
            "latex_content": tex_path.read_text(encoding="utf-8"),
            "pdf_path": str(pdf_path),
            "tex_path": str(tex_path),
            "metadata": agent_output.metadata,
        }

    def _generate_report_sync(self, report_type: str, reason: str | None = None) -> ReportRecord:
        context = self.context_provider()
        report_id = str(uuid4())
        agent_output = self.agent.generate(
            report_type=report_type,
            telemetry=context.get("telemetry", {}),
            alerts=context.get("alerts", []),
            scheduled_tasks=context.get("scheduled_tasks", []),
            generation_reason=reason,
            tool_analysis=context.get("tool_analysis", {}),
        )
        agent_output.metadata = {
            **agent_output.metadata,
            "generation_reason": reason or "scheduled or operator initiated",
            "telemetry_snapshot": context.get("telemetry", {}),
            "alerts_snapshot": context.get("alerts", [])[-12:],
            "scheduled_tasks_count": len(context.get("scheduled_tasks", [])),
            "scheduled_tasks_snapshot": context.get("scheduled_tasks", [])[:5],
        }
        try:
            artifacts = self.pipeline.run(report_id, agent_output.structured_content, agent_output.metadata)
        except Exception as err:
            corrected = self.agent.self_correct(report_type, agent_output, str(err))
            corrected.metadata = {
                **corrected.metadata,
                "generation_reason": reason or "scheduled or operator initiated",
                "telemetry_snapshot": context.get("telemetry", {}),
                "alerts_snapshot": context.get("alerts", [])[-12:],
                "scheduled_tasks_count": len(context.get("scheduled_tasks", [])),
                "scheduled_tasks_snapshot": context.get("scheduled_tasks", [])[:5],
            }
            artifacts = self.pipeline.run(report_id, corrected.structured_content, corrected.metadata)
            agent_output = corrected

        record = self._build_record(report_id, report_type, agent_output, artifacts.pdf_path, artifacts.tex_path)
        if report_type == "notification_report":
            persisted = self.repository.replace_active_notification_report(record)
            self.cache.delete("report:active")
        else:
            persisted = self.repository.upsert_daily_report(record)
            if persisted.get("report_date"):
                self.cache.delete(f"report:daily:{persisted['report_date']}")
        self.retriever.index_report(persisted)
        self._cache_report(persisted)
        return persisted

    async def regenerate(self, report_type: str) -> ReportRecord:
        return await self.generate_report(report_type, reason="forced regeneration")
