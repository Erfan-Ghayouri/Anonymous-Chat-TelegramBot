"""Block service."""
from __future__ import annotations

from database.db import Database


class BlockService:
    def __init__(self, db: Database):
        self.db = db

    def block(self, blocker_id: int, blocked_id: int) -> bool:
        """Idempotent. Returns True if the (blocker, blocked) pair is now blocked."""
        return self.db.block_user(blocker_id, blocked_id)

    def is_blocked(self, a: int, b: int) -> bool:
        return self.db.is_blocked(a, b)
