#!/usr/bin/env python
"""
Migration tool for moving data from SQLite to PostgreSQL with pgvector support.

Usage:
    python migrate_to_postgres.py --source sqlite:///ops_data.db --target postgresql://user:pass@localhost:5432/uvreactor
    python migrate_to_postgres.py --backup  # Backup SQLite before migration
"""

from __future__ import annotations

import argparse
import json
import logging
import shutil
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

# Add parent directory to path
import os
sys.path.insert(0, str(Path(__file__).parent))

from db import Database, SqliteDatabase

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)
DEFAULT_SQLITE_URL = f"sqlite:///{Path(__file__).with_name('ops_data.db')}"


class MigrationTool:
    """Handle migration between database backends."""

    def __init__(self, source_db: Database, target_db: Database) -> None:
        self.source_db = source_db
        self.target_db = target_db
        self.migrated_count = {"reports": 0, "scheduled_tasks": 0}

    def backup_sqlite(self, db_path: str | Path) -> Path | None:
        """Create a backup of SQLite database."""
        db_path = Path(db_path)
        if not db_path.exists():
            logger.warning(f"SQLite database not found at {db_path}")
            return None

        backup_path = db_path.parent / f"{db_path.name}.backup.{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(db_path, backup_path)
            logger.info(f"✓ Created backup at {backup_path}")
            return backup_path
        except Exception as e:
            logger.error(f"✗ Failed to backup SQLite: {e}")
            raise

    def migrate_reports(self) -> int:
        """Migrate reports table from source to target."""
        logger.info("Migrating reports table...")
        count = 0

        try:
            with self.source_db.connect() as source_conn:
                rows = source_conn.fetchall(
                    """
                    SELECT id, title, report_type, is_active, created_at, report_date,
                           structured_content, plain_text, latex_content, pdf_path, tex_path, metadata_json
                    FROM reports
                    """
                )

            if not rows:
                logger.info("No reports to migrate")
                return 0

            with self.target_db.connect() as target_conn:
                for row in rows:
                    # Convert SQLite row to dict
                    if hasattr(row, 'keys'):  # sqlite3.Row
                        row_dict = dict(row)
                    else:  # tuple
                        row_dict = {
                            "id": row[0],
                            "title": row[1],
                            "report_type": row[2],
                            "is_active": bool(row[3]),
                            "created_at": row[4],
                            "report_date": row[5],
                            "structured_content": row[6],
                            "plain_text": row[7],
                            "latex_content": row[8],
                            "pdf_path": row[9],
                            "tex_path": row[10],
                            "metadata_json": row[11],
                        }

                    # Parse JSON fields if needed
                    if isinstance(row_dict["structured_content"], str):
                        row_dict["structured_content"] = json.loads(row_dict["structured_content"])
                    if isinstance(row_dict["metadata_json"], str):
                        row_dict["metadata_json"] = json.loads(row_dict["metadata_json"])

                    target_conn.execute(
                        """
                        INSERT INTO reports (
                            id, title, report_type, is_active, created_at, report_date,
                            structured_content, plain_text, latex_content, pdf_path, tex_path, metadata_json
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            title = EXCLUDED.title,
                            report_type = EXCLUDED.report_type,
                            is_active = EXCLUDED.is_active,
                            created_at = EXCLUDED.created_at,
                            report_date = EXCLUDED.report_date,
                            structured_content = EXCLUDED.structured_content,
                            plain_text = EXCLUDED.plain_text,
                            latex_content = EXCLUDED.latex_content,
                            pdf_path = EXCLUDED.pdf_path,
                            tex_path = EXCLUDED.tex_path,
                            metadata_json = EXCLUDED.metadata_json
                        """,
                        (
                            row_dict["id"],
                            row_dict["title"],
                            row_dict["report_type"],
                            row_dict["is_active"],
                            row_dict["created_at"],
                            row_dict["report_date"],
                            json.dumps(row_dict["structured_content"]),
                            row_dict["plain_text"],
                            row_dict["latex_content"],
                            row_dict["pdf_path"],
                            row_dict["tex_path"],
                            json.dumps(row_dict["metadata_json"]),
                        ),
                    )
                    count += 1

                target_conn.commit()
                logger.info(f"✓ Migrated {count} reports")

        except Exception as e:
            logger.error(f"✗ Error migrating reports: {e}")
            raise

        return count

    def migrate_scheduled_tasks(self) -> int:
        """Migrate scheduled_tasks table from source to target."""
        logger.info("Migrating scheduled_tasks table...")
        count = 0

        try:
            with self.source_db.connect() as source_conn:
                rows = source_conn.fetchall(
                    """
                    SELECT id, text, status, completed, created_at, scheduled_for, executed_at, ai_evaluation
                    FROM scheduled_tasks
                    """
                )

            if not rows:
                logger.info("No scheduled tasks to migrate")
                return 0

            with self.target_db.connect() as target_conn:
                for row in rows:
                    # Convert SQLite row to dict
                    if hasattr(row, 'keys'):  # sqlite3.Row
                        row_dict = dict(row)
                    else:  # tuple
                        row_dict = {
                            "id": row[0],
                            "text": row[1],
                            "status": row[2],
                            "completed": bool(row[3]),
                            "created_at": row[4],
                            "scheduled_for": row[5],
                            "executed_at": row[6],
                            "ai_evaluation": row[7],
                        }

                    # Parse JSON fields if needed
                    if row_dict["ai_evaluation"] and isinstance(row_dict["ai_evaluation"], str):
                        row_dict["ai_evaluation"] = json.loads(row_dict["ai_evaluation"])

                    target_conn.execute(
                        """
                        INSERT INTO scheduled_tasks (
                            id, text, status, completed, created_at, scheduled_for, executed_at, ai_evaluation
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id) DO UPDATE SET
                            text = EXCLUDED.text,
                            status = EXCLUDED.status,
                            completed = EXCLUDED.completed,
                            created_at = EXCLUDED.created_at,
                            scheduled_for = EXCLUDED.scheduled_for,
                            executed_at = EXCLUDED.executed_at,
                            ai_evaluation = EXCLUDED.ai_evaluation
                        """,
                        (
                            row_dict["id"],
                            row_dict["text"],
                            row_dict["status"],
                            row_dict["completed"],
                            row_dict["created_at"],
                            row_dict["scheduled_for"],
                            row_dict["executed_at"],
                            json.dumps(row_dict["ai_evaluation"]) if row_dict["ai_evaluation"] else None,
                        ),
                    )
                    count += 1

                target_conn.commit()
                logger.info(f"✓ Migrated {count} scheduled tasks")

        except Exception as e:
            logger.error(f"✗ Error migrating scheduled tasks: {e}")
            raise

        return count

    def verify_migration(self) -> bool:
        """Verify that all data was migrated correctly."""
        logger.info("Verifying migration...")

        try:
            with self.source_db.connect() as source_conn:
                source_reports = source_conn.fetchone(
                    "SELECT COUNT(*) as count FROM reports"
                )
                source_tasks = source_conn.fetchone(
                    "SELECT COUNT(*) as count FROM scheduled_tasks"
                )

            with self.target_db.connect() as target_conn:
                target_reports = target_conn.fetchone(
                    "SELECT COUNT(*) as count FROM reports"
                )
                target_tasks = target_conn.fetchone(
                    "SELECT COUNT(*) as count FROM scheduled_tasks"
                )

            # Handle both sqlite3.Row and tuple responses
            source_reports_count = (
                source_reports[0] if isinstance(source_reports, tuple) else source_reports["count"]
            )
            source_tasks_count = (
                source_tasks[0] if isinstance(source_tasks, tuple) else source_tasks["count"]
            )
            target_reports_count = (
                target_reports[0] if isinstance(target_reports, tuple) else target_reports["count"]
            )
            target_tasks_count = (
                target_tasks[0] if isinstance(target_tasks, tuple) else target_tasks["count"]
            )

            reports_match = source_reports_count == target_reports_count
            tasks_match = source_tasks_count == target_tasks_count

            logger.info(f"Reports: {source_reports_count} source → {target_reports_count} target {'✓' if reports_match else '✗'}")
            logger.info(f"Tasks: {source_tasks_count} source → {target_tasks_count} target {'✓' if tasks_match else '✗'}")

            return reports_match and tasks_match

        except Exception as e:
            logger.error(f"✗ Verification failed: {e}")
            return False

    def run(self) -> bool:
        """Execute the full migration."""
        logger.info("=" * 60)
        logger.info("Database Migration Tool")
        logger.info("=" * 60)

        try:
            # Initialize target database
            logger.info("Initializing target database schema...")
            self.target_db.init_tables()

            # Migrate tables
            reports_count = self.migrate_reports()
            tasks_count = self.migrate_scheduled_tasks()

            # Verify
            if self.verify_migration():
                logger.info("=" * 60)
                logger.info("✓ Migration completed successfully!")
                logger.info(f"  - Reports: {reports_count}")
                logger.info(f"  - Tasks: {tasks_count}")
                logger.info("=" * 60)
                return True
            else:
                logger.error("✗ Migration verification failed")
                return False

        except Exception as e:
            logger.error(f"✗ Migration failed: {e}")
            return False


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migrate UV Reactor data from SQLite to PostgreSQL with pgvector"
    )
    parser.add_argument(
        "--source",
        default=DEFAULT_SQLITE_URL,
        help=f"Source database URL (default: {DEFAULT_SQLITE_URL})",
    )
    parser.add_argument(
        "--target",
        help="Target PostgreSQL URL (e.g., postgresql://user:pass@localhost:5432/uvreactor)",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="Backup SQLite database before migration",
    )
    parser.add_argument(
        "--verify-only",
        action="store_true",
        help="Only verify existing migration without migrating data",
    )

    args = parser.parse_args()

    if not args.target:
        parser.print_help()
        logger.error("--target is required")
        return 1

    try:
        # Create database instances
        source_db = Database.factory(args.source)
        target_db = Database.factory(args.target)

        # Backup if requested
        if args.backup and isinstance(source_db, SqliteDatabase):
            logger.info("Creating backup...")
            migrator = MigrationTool(source_db, target_db)
            migrator.backup_sqlite(source_db.db_path)
        else:
            migrator = MigrationTool(source_db, target_db)

        # Run migration
        if args.verify_only:
            success = migrator.verify_migration()
            return 0 if success else 1
        else:
            success = migrator.run()
            return 0 if success else 1

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
