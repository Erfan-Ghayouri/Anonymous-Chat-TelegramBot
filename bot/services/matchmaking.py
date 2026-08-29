"""
Matchmaking service.

Wraps the database's `find_match` and `enqueue_search`/`dequeue_search` so
handlers don't have to touch the DB directly. Keeps a small in-memory cache
of "currently searching" users so we can do an extra-fast path before hitting
the DB.
"""
from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, Optional, Tuple

from database.db import Database

logger = logging.getLogger(__name__)


class MatchmakingService:
    def __init__(self, db: Database):
        self.db = db
        # the queue's poller
        self._poll_task: Optional[asyncio.Task] = None
        # notifications subscribers: user_id -> asyncio.Event (woken when their
        # search should re-evaluate)
        self._waiters: Dict[int, asyncio.Event] = {}

    # ------------------------------------------------------------------
    # search lifecycle
    # ------------------------------------------------------------------
    def start_search(
        self,
        user_id: int,
        gender_pref: str = "any",
        location_pref: str = "any",
        premium: bool = False,
    ) -> None:
        # refuse to enqueue if already in an active chat
        active = self.db.get_active_session_for_user(user_id)
        if active:
            raise RuntimeError("user already in an active chat session")
        self.db.enqueue_search(
            user_id,
            gender_pref=gender_pref,
            location_pref=location_pref,
            premium=premium,
        )
        self._wake(user_id)

    def cancel_search(self, user_id: int) -> None:
        self.db.dequeue_search(user_id)
        self._clear_waiter(user_id)

    def is_searching(self, user_id: int) -> bool:
        return self.db.get_search_entry(user_id) is not None

    # ------------------------------------------------------------------
    # single attempt at matching a single user (returns session row or None)
    # ------------------------------------------------------------------
    def attempt_match(self, user_id: int) -> Optional[Dict[str, Any]]:
        entry = self.db.get_search_entry(user_id)
        if not entry:
            return None
        try:
            return self.db.find_match(
                user_id,
                entry["gender_pref"] or "any",
                entry["location_pref"] or "any",
                bool(entry["premium"]),
            )
        except Exception as exc:
            logger.warning("find_match failed for %s: %s", user_id, exc)
            return None

    # ------------------------------------------------------------------
    # one matchmaking pass over the whole queue (called by the poller)
    # ------------------------------------------------------------------
    def poll_once(self) -> int:
        """Try to match every user currently in the queue.

        Returns the number of matches created.
        """
        queue = self.db.list_search_queue()
        # premium users first, oldest first
        queue.sort(key=lambda r: (not r["premium"], r["created_at"]))
        matched = 0
        for entry in queue:
            session = self.attempt_match(entry["user_id"])
            if session:
                matched += 1
                self._wake(session["user_a"])
                self._wake(session["user_b"])
        return matched

    # ------------------------------------------------------------------
    # poller (background task) — runs every ~1.5s
    # ------------------------------------------------------------------
    async def start_poller(self) -> None:
        if self._poll_task and not self._poll_task.done():
            return
        self._poll_task = asyncio.create_task(self._poll_loop())

    async def stop_poller(self) -> None:
        if self._poll_task:
            self._poll_task.cancel()
            try:
                await self._poll_task
            except (asyncio.CancelledError, Exception):
                pass
            self._poll_task = None

    async def _poll_loop(self) -> None:
        while True:
            try:
                # run blocking DB poll in executor so we don't block the loop
                await asyncio.to_thread(self.poll_once)
            except Exception as exc:
                logger.exception("matchmaking poll error: %s", exc)
            await asyncio.sleep(1.5)

    # ------------------------------------------------------------------
    # waiter wakeup primitives
    # ------------------------------------------------------------------
    def _wake(self, user_id: int) -> None:
        ev = self._waiters.get(user_id)
        if ev:
            ev.set()

    def _clear_waiter(self, user_id: int) -> None:
        self._waiters.pop(user_id, None)

    async def wait_for_match(
        self,
        user_id: int,
        timeout_s: float,
    ) -> Optional[Dict[str, Any]]:
        """Block until a match is found for `user_id` or timeout expires."""
        ev = asyncio.Event()
        self._waiters[user_id] = ev

        deadline = time.monotonic() + timeout_s
        while True:
            # try once immediately
            session = self.attempt_match(user_id)
            if session:
                self._clear_waiter(user_id)
                return session
            if not self.is_searching(user_id):
                self._clear_waiter(user_id)
                return None
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                self._clear_waiter(user_id)
                return None
            try:
                await asyncio.wait_for(ev.wait(), timeout=min(remaining, 2.0))
            except asyncio.TimeoutError:
                pass
            ev.clear()
