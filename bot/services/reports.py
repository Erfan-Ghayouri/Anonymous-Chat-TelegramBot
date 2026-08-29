"""Reports service."""
from __future__ import annotations

import time
from typing import Any, Dict, List, Optional

from database.db import Database
import config


class ReportService:
    def __init__(self, db: Database):
        self.db = db

    def create(
        self,
        reporter_id: int,
        reported_user_id: int,
        chat_session_id: Optional[int],
        reason: str,
    ) -> Optional[Dict[str, Any]]:
        """Create a report. Enforces a per-reporter cooldown to prevent spam."""
        recent = self.db.count_reports_by_reporter_since(
            reporter_id, config.REPORT_COOLDOWN_SEC
        )
        if recent > 0:
            return None  # rate-limited
        reason = (reason or "").strip()[:1000]
        return self.db.create_report(
            reporter_id, reported_user_id, chat_session_id, reason
        )

    def list_open(self, limit: int = 50) -> List[Dict[str, Any]]:
        return self.db.list_open_reports(limit=limit)

    def resolve(self, report_id: int, status: str = "resolved"):
        self.db.set_report_status(report_id, status)
