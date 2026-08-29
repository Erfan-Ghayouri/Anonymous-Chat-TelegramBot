"""
Wallet service — atomic, race-safe coin operations.

All wallet mutations go through `Database.adjust_wallet_atomic`, which:
  - uses SELECT/UPDATE FOR UPDATE-equivalent semantics via a single
    conditional UPDATE
  - refuses to let the balance go negative
  - records the resulting balance after each transaction
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from database.db import Database
import config


class WalletService:
    def __init__(self, db: Database):
        self.db = db

    def balance(self, user_id: int) -> int:
        return self.db.get_balance(user_id)

    def spend(
        self,
        user_id: int,
        amount: int,
        txn_type: str,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Spend coins. Returns None if the user can't afford it (double-spend safe)."""
        if amount <= 0:
            return None
        result = self.db.adjust_wallet_atomic(
            user_id, -amount, txn_type, description
        )
        if result is None:
            return None
        return result

    def credit(
        self,
        user_id: int,
        amount: int,
        txn_type: str,
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Credit coins. Always succeeds (admin / referral / bonus)."""
        if amount <= 0:
            return {"balance": self.balance(user_id), "skipped": True}
        return self.db.adjust_wallet_atomic(user_id, amount, txn_type, description)

    def can_afford(self, user_id: int, amount: int) -> bool:
        return self.balance(user_id) >= amount

    def transactions(self, user_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        rows = self.db.list_transactions(user_id, limit=limit)
        return [dict(r) for r in rows]

    # ---- convenience wrappers for the bot's configurable prices ----
    def charge_premium_search(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self.spend(
            user_id,
            config.PREMIUM_SEARCH_PRICE,
            "premium_search",
            f"جستجوی ویژه — {config.PREMIUM_SEARCH_DURATION_MIN} دقیقه",
        )

    def reward_referral(self, referrer_id: int) -> Dict[str, Any]:
        return self.credit(
            referrer_id,
            config.REFERRAL_REWARD,
            "referral_reward",
            "پاداش دعوت دوست",
        )
