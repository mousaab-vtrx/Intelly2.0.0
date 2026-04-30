from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import chromadb
from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

from .repository import ReportRepository


class ReportRetrievalTool:
    def __init__(self, base_dir: Path, repository: ReportRepository) -> None:
        self.base_dir = base_dir
        self.repository = repository
        self._embedding = DefaultEmbeddingFunction()

    def _client(self) -> chromadb.PersistentClient:
        return chromadb.PersistentClient(path=str(self.base_dir / "chroma_db"))

    def retrieve_knowledge(self, query: str, n_results: int = 4) -> list[str]:
        try:
            collection = self._client().get_or_create_collection(
                name="uv-plant-knowledge",
                embedding_function=self._embedding,
            )
            results = collection.query(query_texts=[query], n_results=n_results)
            return results.get("documents", [[]])[0]
        except Exception:
            return []

    def retrieve_prior_reports(self, query: str, n_results: int = 3) -> list[str]:
        snippets: list[str] = []
        try:
            collection = self._client().get_or_create_collection(
                name="uv-report-history",
                embedding_function=self._embedding,
            )
            results = collection.query(query_texts=[query], n_results=n_results)
            snippets.extend(results.get("documents", [[]])[0])
        except Exception:
            pass

        if not snippets:
            recent = self.repository.search_prior_reports(limit=n_results)
            snippets.extend(report["plain_text"] for report in recent)
        return snippets[:n_results]

    def latest_report(self, report_type: str) -> dict[str, Any] | None:
        return self.repository.get_latest_report(report_type)

    def user_data(self, telemetry: dict[str, Any], alerts: list[dict[str, Any]], scheduled_tasks: list[dict[str, Any]]) -> str:
        payload = {
            "telemetry": telemetry,
            "recent_alerts": alerts[-5:],
            "scheduled_tasks": scheduled_tasks[-5:],
        }
        return json.dumps(payload, default=str, indent=2)

    def index_report(self, report: dict[str, Any]) -> None:
        try:
            collection = self._client().get_or_create_collection(
                name="uv-report-history",
                embedding_function=self._embedding,
            )
            collection.upsert(
                ids=[report["id"]],
                documents=[report["plain_text"]],
                metadatas=[{
                    "report_type": report["report_type"],
                    "created_at": report["created_at"],
                    "title": report["title"],
                }],
            )
        except Exception:
            return
