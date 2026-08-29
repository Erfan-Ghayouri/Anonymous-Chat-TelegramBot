"""Referral service."""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from database.db import Database
from services.wallet import WalletService
from services.users import UserService
import config

logger = logging.getLogger(__name__)


class ReferralService:
    def __init__(self, db: Database, wallet: WalletService, users: UserService):
        self.db = db
        self.wallet = wallet
        self.users = users

    def build_referral_link(self, referrer_telegram_id: int, bot_username: str) -> str:
        return f"https://t.me/{bot_username}?start=ref_{referrer_telegram_id}"

    def parse_referral_payload(self, payload: str) -> Optional[int]:
        """Returns the referrer's telegram_id from a `ref_<id>` payload."""
        if not payload:
            return None
        if not payload.startswith("ref_"):
            return None
        raw = payload[4:]
        if not raw.isdigit():
            return None
        return int(raw)

    def process_referral(
        self,
        referrer_telegram_id: int,
        referred_telegram_id: int,
    ) -> bool:
        """Process a referral.

        - Self-referrals are rejected.
        - Duplicate referrals on the same referred user are rejected (unique
          constraint on `referred_id`).
        - The reward is only granted once per successful insert.
        """
        if referrer_telegram_id == referred_telegram_id:
            return False
        if referrer_telegram_id <= 0 or referred_telegram_id <= 0:
            return False

        # make sure both users exist
        referrer = self.users.ensure_user(referrer_telegram_id)
        if not referrer:
            return False

        # insert referral row (idempotent due to unique(referred_id))
        created = self.db.create_referral(referrer_telegram_id, referred_telegram_id)
        if not created:
            return False

        try:
            self.wallet.reward_referral(referrer_telegram_id)
            self.db.mark_referral_rewarded(created["id"])
            self.db.update_user_fields(
                referrer_telegram_id,
                referral_count=(referrer.get("referral_count") or 0) + 1,
            )
        except Exception as exc:
            logger.exception("Failed to grant referral reward: %s", exc)
            return False
        return True

    def stats(self, referrer_telegram_id: int) -> Dict[str, Any]:
        s = self.db.get_referral_stats(referrer_telegram_id)
        earned = s["rewarded"] * config.REFERRAL_REWARD
        return {
            "total": s["total"],
            "rewarded": s["rewarded"],
            "earned_coins": earned,
        }
