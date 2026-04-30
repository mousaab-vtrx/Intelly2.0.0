from __future__ import annotations

import json
from contextlib import contextmanager
from datetime import date
from typing import Any, Iterator

# Import database abstraction layer
from ..db import Database


ReportRecord = dict[str, Any]
REPORT_COLUMNS = (
    "id, title, report_type, is_active, created_at, report_date, "
    "structured_content, plain_text, latex_content, pdf_path, tex_path, metadata_json"
)


class ReportRepository:
    def __init__(self, database_url: str) -> None:
        self.db = Database.factory(database_url)

    @contextmanager
    def connect(self) -> Iterator[Any]:
        """Context manager for database connections."""
        with self.db.connect() as conn:
            yield conn

    def init_db(self) -> None:
        """Initialize database tables using database abstraction layer."""
        self.db.init_tables()

    def _serialize(self, record: ReportRecord) -> tuple[Any, ...]:
        return (
            record["id"],
            record["title"],
            record["report_type"],
            bool(record.get("is_active")),
            record["created_at"],
            record.get("report_date"),
            json.dumps(record["structured_content"]),
            record["plain_text"],
            record["latex_content"],
            record.get("pdf_path"),
            record.get("tex_path"),
            json.dumps(record["metadata"]),
        )

    def _row_to_dict(self, row: Any) -> dict[str, Any] | None:
        """Convert database row to dictionary."""
        if row is None:
            return None

        if isinstance(row, tuple):
            keys = [
                "id", "title", "report_type", "is_active", "created_at", "report_date",
                "structured_content", "plain_text", "latex_content", "pdf_path", "tex_path", "metadata_json"
            ]
            return dict(zip(keys, row))

        return row

    def _row_to_record(self, row: Any) -> ReportRecord | None:
        row_dict = self._row_to_dict(row)
        if row_dict is None:
            return None
        
        return {
            "id": row_dict["id"],
            "title": row_dict["title"],
            "report_type": row_dict["report_type"],
            "is_active": bool(row_dict["is_active"]),
            "created_at": row_dict["created_at"],
            "report_date": row_dict["report_date"],
            "structured_content": (
                json.loads(row_dict["structured_content"])
                if isinstance(row_dict["structured_content"], str)
                else row_dict["structured_content"]
            ),
            "plain_text": row_dict["plain_text"],
            "latex_content": row_dict["latex_content"],
            "pdf_path": row_dict["pdf_path"],
            "tex_path": row_dict["tex_path"],
            "metadata": (
                json.loads(row_dict["metadata_json"])
                if isinstance(row_dict["metadata_json"], str)
                else row_dict["metadata_json"]
            ),
        }

    def replace_active_notification_report(self, record: ReportRecord) -> ReportRecord:
        with self.connect() as conn:
            conn.execute("BEGIN")
            conn.execute(
                """
                UPDATE reports
                SET is_active = %s
                WHERE report_type = %s AND is_active = %s
                """,
                (False, "notification_report", True),
            )
            conn.execute(
                """
                INSERT INTO reports (
                    id, title, report_type, is_active, created_at, report_date,
                    structured_content, plain_text, latex_content, pdf_path, tex_path, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                self._serialize(record),
            )
            conn.commit()
        return record

    def upsert_daily_report(self, record: ReportRecord) -> ReportRecord:
        with self.connect() as conn:
            conn.execute("BEGIN")
            existing = conn.fetchone(
                """
                SELECT id FROM reports
                WHERE report_type = 'daily_full_report' AND report_date = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (record["report_date"],),
            )
            if existing:
                conn.execute("DELETE FROM reports WHERE id = %s", (existing[0],))
            conn.execute(
                """
                INSERT INTO reports (
                    id, title, report_type, is_active, created_at, report_date,
                    structured_content, plain_text, latex_content, pdf_path, tex_path, metadata_json
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                self._serialize(record),
            )
            conn.commit()
        return record

    def get_active_notification_report(self) -> ReportRecord | None:
        with self.connect() as conn:
            row = conn.fetchone(
                """
                SELECT """ + REPORT_COLUMNS + """
                FROM reports
                WHERE report_type = %s AND is_active = %s
                LIMIT 1
                """,
                ("notification_report", True),
            )
        return self._row_to_record(row)

    def get_daily_report_for_date(self, report_date: str) -> ReportRecord | None:
        with self.connect() as conn:
            row = conn.fetchone(
                """
                SELECT """ + REPORT_COLUMNS + """
                FROM reports
                WHERE report_type = 'daily_full_report' AND report_date = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (report_date,),
            )
        return self._row_to_record(row)

    def get_report(self, report_id: str) -> ReportRecord | None:
        with self.connect() as conn:
            row = conn.fetchone(
                "SELECT " + REPORT_COLUMNS + " FROM reports WHERE id = %s",
                (report_id,),
            )
        return self._row_to_record(row)

    def get_latest_report(self, report_type: str) -> ReportRecord | None:
        with self.connect() as conn:
            row = conn.fetchone(
                """
                SELECT """ + REPORT_COLUMNS + """
                FROM reports
                WHERE report_type = %s
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (report_type,),
            )
        return self._row_to_record(row)

    def list_recent_reports(self, limit: int = 10, report_type: str | None = None) -> list[ReportRecord]:
        with self.connect() as conn:
            if report_type:
                rows = conn.fetchall(
                    """
                    SELECT """ + REPORT_COLUMNS + """
                    FROM reports
                    WHERE report_type = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                    """,
                    (report_type, limit),
                )
            else:
                rows = conn.fetchall(
                    "SELECT " + REPORT_COLUMNS + " FROM reports ORDER BY created_at DESC LIMIT %s",
                    (limit,),
                )
        return [record for row in rows if (record := self._row_to_record(row))]

    def search_prior_reports(self, limit: int = 5) -> list[ReportRecord]:
        return self.list_recent_reports(limit=limit)

    def today_str(self) -> str:
        return date.today().isoformat()
