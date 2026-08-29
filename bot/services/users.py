"""
User service.

Wraps the database `users` table and exposes high-level profile operations
used by handlers. Does NOT touch the wallet or chat logic directly.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional

from database.db import Database
import config


class UserService:
    def __init__(self, db: Database):
        self.db = db

    def ensure_user(self, telegram_id: int) -> Dict[str, Any]:
        """Create the user row if missing and grant the new-user bonus."""
        existing = self.db.get_user(telegram_id)
        if existing:
            return existing
        # brand new user — grant signup bonus (atomic, idempotent)
        self.db.add_user(telegram_id)
        # re-fetch to get internal_id + defaults
        user = self.db.get_user(telegram_id)
        if user is not None and int(user.get("wallet_balance") or 0) == 0:
            self.db.adjust_wallet_atomic(
                telegram_id,
                config.NEW_USER_BONUS,
                "signup_bonus",
                "پاداش عضویت اولیه",
            )
        return self.db.get_user(telegram_id)

    def get_profile(self, telegram_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_user(telegram_id)

    def set_name(self, telegram_id: int, name: str) -> Optional[Dict[str, Any]]:
        return self.db.update_user_fields(telegram_id, name=name.strip()[:64])

    def set_bio(self, telegram_id: int, bio: str) -> Optional[Dict[str, Any]]:
        return self.db.update_user_fields(telegram_id, bio=bio.strip()[:500])

    def set_gender(self, telegram_id: int, gender: str) -> Optional[Dict[str, Any]]:
        if gender not in ("male", "female"):
            raise ValueError("gender must be 'male' or 'female'")
        return self.db.update_user_fields(telegram_id, gender=gender)

    def set_city(self, telegram_id: int, city: str) -> Optional[Dict[str, Any]]:
        return self.db.update_user_fields(telegram_id, city=city.strip()[:64])

    def set_age(self, telegram_id: int, age: int) -> Optional[Dict[str, Any]]:
        if not (13 <= age <= 120):
            raise ValueError("age out of range")
        return self.db.update_user_fields(telegram_id, age=age)

    def is_premium(self, telegram_id: int) -> bool:
        user = self.db.get_user(telegram_id)
        if not user:
            return False
        premium_until = user.get("premium_until")
        if not premium_until:
            return False
        # premium_until is a datetime
        ts = premium_until.timestamp() if hasattr(premium_until, "timestamp") else 0
        return ts > time.time()

    def grant_premium(self, telegram_id: int, minutes: int) -> Optional[Dict[str, Any]]:
        """Extend the user's premium window by `minutes` minutes."""
        with self.db.transaction() as cur:
            cur.execute(
                """
                UPDATE users
                SET premium_until = GREATEST(NOW(), COALESCE(premium_until, NOW()))
                                     + (%s || ' minutes')::INTERVAL
                WHERE user_id = %s
                RETURNING *
                """,
                (str(minutes), telegram_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def touch(self, telegram_id: int):
        self.db.touch_user_activity(telegram_id)

    def display_id(self, user: Dict[str, Any]) -> str:
        """Internal #ID used in profile cards and reports."""
        iid = user.get("internal_id")
        if iid is None:
            return "#?"
        return f"#{int(iid)}"
