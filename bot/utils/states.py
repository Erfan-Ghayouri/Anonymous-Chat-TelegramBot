"""
Simple in-memory FSM.

Pyrogram doesn't ship a state machine like aiogram's. We keep one here.

States are keyed by (user_id). A state consists of:
  - state: a string constant from STATES below
  - data: a dict of contextual values (e.g. target_user_id, partial input)

The store is ephemeral. If the process restarts, in-progress FSM flows are
lost — which is acceptable for things like bio entry; the user can simply
try again. Persistent flows (chat sessions, wallet, etc.) live in the DB.
"""
from __future__ import annotations

import time
from typing import Any, Dict, Optional


class States:
    IDLE = "idle"
    EDIT_NAME = "edit_name"
    EDIT_BIO = "edit_bio"
    EDIT_AGE = "edit_age"
    EDIT_CITY = "edit_city"
    REPORT_REASON = "report_reason"
    ADMIN_BROADCAST = "admin_broadcast"
    ADMIN_ADJUST_COINS_USER = "admin_adj_user"
    ADMIN_ADJUST_COINS_AMOUNT = "admin_adj_amount"


class StateStore:
    def __init__(self) -> None:
        self._store: Dict[int, Dict[str, Any]] = {}

    def set(self, user_id: int, state: str, data: Optional[Dict[str, Any]] = None) -> None:
        self._store[user_id] = {
            "state": state,
            "data": dict(data or {}),
            "ts": time.time(),
        }

    def get(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self._store.get(user_id)

    def state(self, user_id: int) -> str:
        s = self._store.get(user_id)
        return s["state"] if s else States.IDLE

    def data(self, user_id: int) -> Dict[str, Any]:
        s = self._store.get(user_id)
        return s["data"] if s else {}

    def update(self, user_id: int, **kwargs: Any) -> None:
        s = self._store.setdefault(
            user_id, {"state": States.IDLE, "data": {}, "ts": time.time()}
        )
        s["data"].update(kwargs)

    def clear(self, user_id: int) -> None:
        self._store.pop(user_id, None)

    def cleanup(self, max_age_seconds: int = 600) -> int:
        """Drop stale FSM entries. Returns number of cleared entries."""
        now = time.time()
        stale = [uid for uid, s in self._store.items() if now - s["ts"] > max_age_seconds]
        for uid in stale:
            self._store.pop(uid, None)
        return len(stale)


# shared singleton
state_store = StateStore()
