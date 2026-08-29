"""
Database layer.

Uses a psycopg2 ThreadedConnectionPool so that concurrent Pyrogram handlers
can run DB operations without serializing on a single connection.

The public API is synchronous (matching the existing project style) and each
public method obtains its own connection from the pool. Multi-statement
transactions are wrapped in `with self.transaction() as cur:` blocks.
"""
from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from typing import Any, Dict, List, Optional, Tuple

import psycopg2
from psycopg2 import pool as pg_pool
from psycopg2.extras import DictCursor, RealDictCursor

logger = logging.getLogger(__name__)


class Database:
    def __init__(self, url: str, minconn: int = 1, maxconn: int = 10):
        if not url:
            raise RuntimeError("DATABASE_URL is not configured")
        self._pool = pg_pool.ThreadedConnectionPool(
            minconn=minconn,
            maxconn=maxconn,
            dsn=url,
        )
        # keep legacy attribute for backwards-compat with admin.py (db.conn.rollback())
        self.conn = self._pool.getconn()  # long-lived for legacy callers

    # ------------------------------------------------------------------
    # connection helpers
    # ------------------------------------------------------------------
    @contextmanager
    def _cursor(self, *, autocommit: bool = False, real_dict: bool = True):
        conn = self._pool.getconn()
        cur = None
        try:
            conn.autocommit = autocommit
            cur = conn.cursor(cursor_factory=RealDictCursor if real_dict else DictCursor)
            yield conn, cur
            if not autocommit:
                conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if cur is not None:
                cur.close()
            self._pool.putconn(conn)

    @contextmanager
    def transaction(self):
        """Yield a cursor inside a single transaction; commit or rollback."""
        conn = self._pool.getconn()
        cur = None
        try:
            conn.autocommit = False
            cur = conn.cursor(cursor_factory=RealDictCursor)
            yield cur
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            if cur is not None:
                cur.close()
            self._pool.putconn(conn)

    def close(self):
        try:
            if self.conn and not self.conn.closed:
                self._pool.putconn(self.conn)
        except Exception:
            pass
        try:
            self._pool.closeall()
        except Exception:
            pass

    # ==================================================================
    # SCHEMA / MIGRATIONS
    # ==================================================================
    def create_tables(self):
        """Create all tables if they don't exist.

        Existing tables are altered in-place with `ADD COLUMN IF NOT EXISTS`
        so the existing `users` and `sponsor_channels` tables are preserved.
        """
        try:
            with self._cursor(autocommit=True) as (_, cur):
                # ---------------- users ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS users (
                        user_id           BIGINT PRIMARY KEY,
                        internal_id       BIGSERIAL,
                        name              TEXT,
                        age               SMALLINT,
                        city              TEXT,
                        gender            TEXT,
                        profile_picture  TEXT,
                        bio               TEXT,
                        wallet_balance    NUMERIC(12, 0) DEFAULT 0,
                        status            TEXT NOT NULL DEFAULT 'active',
                        search_status     TEXT NOT NULL DEFAULT 'idle',
                        premium_until     TIMESTAMPTZ,
                        referral_count    INT NOT NULL DEFAULT 0,
                        joined_at         TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_activity     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                # new columns added incrementally for backward compat
                for col, ddl in [
                    ("internal_id",    "BIGSERIAL"),
                    ("status",         "TEXT NOT NULL DEFAULT 'active'"),
                    ("search_status",  "TEXT NOT NULL DEFAULT 'idle'"),
                    ("premium_until",  "TIMESTAMPTZ"),
                    ("referral_count", "INT NOT NULL DEFAULT 0"),
                    ("joined_at",      "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
                    ("last_activity",  "TIMESTAMPTZ NOT NULL DEFAULT NOW()"),
                ]:
                    cur.execute(
                        f"ALTER TABLE users ADD COLUMN IF NOT EXISTS {col} {ddl}"
                    )
                # legacy wallet_balance default upgrade
                cur.execute(
                    "ALTER TABLE users ALTER COLUMN wallet_balance "
                    "SET DEFAULT 0"
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS users_internal_id_uidx "
                    "ON users (internal_id)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS users_search_status_idx "
                    "ON users (search_status)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS users_status_idx "
                    "ON users (status)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS users_gender_city_idx "
                    "ON users (gender, city, status)"
                )

                # ---------------- sponsor_channels (existing) ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS sponsor_channels (
                        channel_id   BIGINT PRIMARY KEY,
                        invite_link  TEXT NOT NULL
                    )
                    """
                )

                # ---------------- blocked_users ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS blocked_users (
                        blocker_id   BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        blocked_id   BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        created_at   TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        PRIMARY KEY (blocker_id, blocked_id)
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS blocked_blocked_idx "
                    "ON blocked_users (blocked_id)"
                )

                # ---------------- referrals ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS referrals (
                        id              BIGSERIAL PRIMARY KEY,
                        referrer_id     BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        referred_id     BIGINT NOT NULL UNIQUE REFERENCES users (user_id) ON DELETE CASCADE,
                        reward_given    BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS referrals_referrer_idx "
                    "ON referrals (referrer_id)"
                )

                # ---------------- chat_sessions ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id              BIGSERIAL PRIMARY KEY,
                        user_a          BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        user_b          BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        status          TEXT NOT NULL DEFAULT 'active',
                        started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        ended_at        TIMESTAMPTZ,
                        ended_by         BIGINT,
                        CHECK (user_a <> user_b)
                    )
                    """
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS chat_session_active_uniq "
                    "ON chat_sessions (user_a) WHERE status = 'active'"
                )
                cur.execute(
                    "CREATE UNIQUE INDEX IF NOT EXISTS chat_session_active_uniq_b "
                    "ON chat_sessions (user_b) WHERE status = 'active'"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS chat_sessions_status_idx "
                    "ON chat_sessions (status)"
                )

                # ---------------- search_filters (per-user search prefs) ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_filters (
                        user_id        BIGINT PRIMARY KEY REFERENCES users (user_id) ON DELETE CASCADE,
                        gender_pref    TEXT NOT NULL DEFAULT 'any',
                        location_pref  TEXT NOT NULL DEFAULT 'any',
                        premium        BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

                # ---------------- search_queue (in-flight matchmakings) ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS search_queue (
                        user_id        BIGINT PRIMARY KEY REFERENCES users (user_id) ON DELETE CASCADE,
                        gender_pref    TEXT NOT NULL DEFAULT 'any',
                        location_pref  TEXT NOT NULL DEFAULT 'any',
                        premium        BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS search_queue_created_idx "
                    "ON search_queue (created_at)"
                )

                # ---------------- wallet_transactions ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS wallet_transactions (
                        id              BIGSERIAL PRIMARY KEY,
                        user_id         BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        amount          INTEGER NOT NULL,
                        type            TEXT NOT NULL,
                        description     TEXT,
                        balance_after   INTEGER,
                        created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS wallet_txn_user_idx "
                    "ON wallet_transactions (user_id, created_at DESC)"
                )

                # ---------------- reports ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reports (
                        id                 BIGSERIAL PRIMARY KEY,
                        reporter_id        BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        reported_user_id   BIGINT NOT NULL REFERENCES users (user_id) ON DELETE CASCADE,
                        chat_session_id    BIGINT REFERENCES chat_sessions (id) ON DELETE SET NULL,
                        reason             TEXT,
                        status             TEXT NOT NULL DEFAULT 'open',
                        created_at         TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS reports_status_idx "
                    "ON reports (status, created_at DESC)"
                )
                cur.execute(
                    "CREATE INDEX IF NOT EXISTS reports_reported_idx "
                    "ON reports (reported_user_id)"
                )

                # ---------------- settings (config overrides) ----------------
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS bot_settings (
                        key         TEXT PRIMARY KEY,
                        value       TEXT,
                        updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                    """
                )

            logger.info("Database schema ready")
        except Exception:
            raise

    # ==================================================================
    # USERS
    # ==================================================================
    def add_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Insert user if not present. Returns the row (with internal_id)."""
        with self._cursor() as (_, cur):
            cur.execute(
                """
                INSERT INTO users (user_id, wallet_balance)
                VALUES (%s, 0)
                ON CONFLICT (user_id) DO NOTHING
                """
            )
        return self.get_user(user_id)

    def get_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM users WHERE user_id = %s", (user_id,)
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def get_user_by_internal_id(self, internal_id: int) -> Optional[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM users WHERE internal_id = %s", (internal_id,)
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def update_user_fields(
        self, user_id: int, **fields: Any
    ) -> Optional[Dict[str, Any]]:
        if not fields:
            return self.get_user(user_id)
        allowed = {
            "name", "age", "city", "gender", "profile_picture",
            "bio", "status", "search_status", "premium_until",
            "referral_count", "last_activity",
        }
        assignments: List[str] = []
        values: List[Any] = []
        for k, v in fields.items():
            if k not in allowed:
                continue
            assignments.append(f"{k} = %s")
            values.append(v)
        if not assignments:
            return self.get_user(user_id)
        values.append(user_id)
        with self._cursor() as (_, cur):
            cur.execute(
                f"UPDATE users SET {', '.join(assignments)} "
                "WHERE user_id = %s RETURNING *",
                values,
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def touch_user_activity(self, user_id: int):
        with self._cursor() as (_, cur):
            cur.execute(
                "UPDATE users SET last_activity = NOW() WHERE user_id = %s",
                (user_id,),
            )

    def count_users(self) -> int:
        with self._cursor() as (_, cur):
            cur.execute("SELECT COUNT(*) AS n FROM users")
            row = cur.fetchone()
        return int(row["n"]) if row else 0

    def count_active_users(self, since_hours: int = 24) -> int:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT COUNT(*) AS n FROM users "
                "WHERE last_activity > NOW() - (%s || ' hours')::INTERVAL",
                (str(since_hours),),
            )
            row = cur.fetchone()
        return int(row["n"]) if row else 0

    def list_users(self, limit: int = 100, offset: int = 0) -> List[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM users ORDER BY joined_at DESC LIMIT %s OFFSET %s",
                (limit, offset),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ==================================================================
    # WALLET
    # ==================================================================
    def get_balance(self, user_id: int) -> int:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT wallet_balance FROM users WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        return int(row["wallet_balance"]) if row else 0

    def adjust_wallet_atomic(
        self,
        user_id: int,
        amount: int,
        txn_type: str,
        description: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """Atomically add `amount` to user's wallet and record a transaction.

        Refuses to go negative. Returns the new balance dict or None if
        insufficient funds / user not found.
        """
        if amount == 0:
            return {"balance": self.get_balance(user_id), "skipped": True}
        with self.transaction() as cur:
            cur.execute(
                """
                UPDATE users
                SET wallet_balance = wallet_balance + %s
                WHERE user_id = %s
                  AND (wallet_balance + %s) >= 0
                RETURNING wallet_balance
                """,
                (amount, user_id, amount),
            )
            row = cur.fetchone()
            if not row:
                return None
            new_balance = int(row["wallet_balance"])
            cur.execute(
                """
                INSERT INTO wallet_transactions
                  (user_id, amount, type, description, balance_after)
                VALUES (%s, %s, %s, %s, %s)
                RETURNING id
                """,
                (user_id, amount, txn_type, description, new_balance),
            )
            txn = cur.fetchone()
        return {
            "balance": new_balance,
            "transaction_id": txn["id"] if txn else None,
        }

    def list_transactions(
        self, user_id: int, limit: int = 20
    ) -> List[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                """
                SELECT * FROM wallet_transactions
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ==================================================================
    # SPONSOR CHANNELS (existing, preserved)
    # ==================================================================
    def get_sponsor_channels(self) -> List[Dict[str, Any]]:
        try:
            with self._cursor() as (_, cur):
                cur.execute(
                    "SELECT channel_id, invite_link "
                    "FROM sponsor_channels ORDER BY channel_id"
                )
                rows = cur.fetchall()
            return [
                {"channel_id": r["channel_id"], "invite_link": r["invite_link"]}
                for r in rows
            ]
        except Exception:
            raise

    def add_sponsor_channel(
        self, channel_id: int, invite_link: str
    ) -> bool:
        try:
            with self._cursor() as (_, cur):
                cur.execute(
                    """
                    INSERT INTO sponsor_channels (channel_id, invite_link)
                    VALUES (%s, %s)
                    ON CONFLICT (channel_id) DO NOTHING
                    RETURNING channel_id
                    """,
                    (channel_id, invite_link),
                )
                result = cur.fetchone()
            return result is not None
        except Exception:
            raise

    def remove_sponsor_channel(self, channel_id: int) -> bool:
        try:
            with self._cursor() as (_, cur):
                cur.execute(
                    "DELETE FROM sponsor_channels WHERE channel_id = %s "
                    "RETURNING channel_id",
                    (channel_id,),
                )
                result = cur.fetchone()
            return result is not None
        except Exception:
            raise

    # ==================================================================
    # REFERRALS
    # ==================================================================
    def create_referral(
        self, referrer_id: int, referred_id: int
    ) -> Optional[Dict[str, Any]]:
        if referrer_id == referred_id:
            return None
        try:
            with self._cursor() as (_, cur):
                cur.execute(
                    """
                    INSERT INTO referrals (referrer_id, referred_id, reward_given)
                    VALUES (%s, %s, FALSE)
                    ON CONFLICT (referred_id) DO NOTHING
                    RETURNING id
                    """,
                    (referrer_id, referred_id),
                )
                result = cur.fetchone()
            return dict(result) if result else None
        except Exception:
            raise

    def mark_referral_rewarded(self, referral_id: int):
        with self._cursor() as (_, cur):
            cur.execute(
                "UPDATE referrals SET reward_given = TRUE WHERE id = %s",
                (referral_id,),
            )

    def get_referral_stats(self, referrer_id: int) -> Dict[str, Any]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT COUNT(*) AS n, COALESCE(SUM("
                "CASE WHEN reward_given THEN 1 ELSE 0 END"
                "),0) AS rewarded "
                "FROM referrals WHERE referrer_id = %s",
                (referrer_id,),
            )
            row = cur.fetchone()
        return {
            "total": int(row["n"]),
            "rewarded": int(row["rewarded"]),
        }

    # ==================================================================
    # BLOCKS
    # ==================================================================
    def block_user(self, blocker_id: int, blocked_id: int) -> bool:
        if blocker_id == blocked_id:
            return False
        try:
            with self._cursor() as (_, cur):
                cur.execute(
                    """
                    INSERT INTO blocked_users (blocker_id, blocked_id)
                    VALUES (%s, %s)
                    ON CONFLICT (blocker_id, blocked_id) DO NOTHING
                    RETURNING blocker_id
                    """,
                    (blocker_id, blocked_id),
                )
                result = cur.fetchone()
            return result is not None
        except Exception:
            raise

    def is_blocked(self, a: int, b: int) -> bool:
        """True if A has blocked B OR B has blocked A."""
        with self._cursor() as (_, cur):
            cur.execute(
                """
                SELECT 1 FROM blocked_users
                WHERE (blocker_id = %s AND blocked_id = %s)
                   OR (blocker_id = %s AND blocked_id = %s)
                LIMIT 1
                """,
                (a, b, b, a),
            )
            return cur.fetchone() is not None

    # ==================================================================
    # CHAT SESSIONS
    # ==================================================================
    def get_active_session_for_user(
        self, user_id: int
    ) -> Optional[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                """
                SELECT * FROM chat_sessions
                WHERE (user_a = %s OR user_b = %s) AND status = 'active'
                LIMIT 1
                """,
                (user_id, user_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def get_session(self, session_id: int) -> Optional[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM chat_sessions WHERE id = %s",
                (session_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def end_session(
        self, session_id: int, ended_by: int
    ) -> Optional[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                """
                UPDATE chat_sessions
                SET status = 'ended', ended_at = NOW(), ended_by = %s
                WHERE id = %s AND status = 'active'
                RETURNING *
                """,
                (ended_by, session_id),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def end_all_active_sessions_for_user(self, user_id: int):
        """Used by /reset and admin tools."""
        with self._cursor() as (_, cur):
            cur.execute(
                """
                UPDATE chat_sessions
                SET status = 'ended', ended_at = NOW(), ended_by = %s
                WHERE (user_a = %s OR user_b = %s) AND status = 'active'
                """,
                (user_id, user_id, user_id),
            )

    def count_active_sessions(self) -> int:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT COUNT(*) AS n FROM chat_sessions WHERE status = 'active'"
            )
            row = cur.fetchone()
        return int(row["n"]) if row else 0

    def count_total_sessions(self) -> int:
        with self._cursor() as (_, cur):
            cur.execute("SELECT COUNT(*) AS n FROM chat_sessions")
            row = cur.fetchone()
        return int(row["n"]) if row else 0

    # ==================================================================
    # SEARCH QUEUE + MATCHMAKING
    # ==================================================================
    def enqueue_search(
        self,
        user_id: int,
        gender_pref: str = "any",
        location_pref: str = "any",
        premium: bool = False,
    ):
        with self._cursor() as (_, cur):
            cur.execute(
                """
                INSERT INTO search_queue
                  (user_id, gender_pref, location_pref, premium, created_at)
                VALUES (%s, %s, %s, %s, NOW())
                ON CONFLICT (user_id) DO UPDATE
                  SET gender_pref = EXCLUDED.gender_pref,
                      location_pref = EXCLUDED.location_pref,
                      premium = EXCLUDED.premium,
                      created_at = NOW()
                """,
                (user_id, gender_pref, location_pref, premium),
            )

    def dequeue_search(self, user_id: int):
        with self._cursor() as (_, cur):
            cur.execute(
                "DELETE FROM search_queue WHERE user_id = %s",
                (user_id,),
            )

    def get_search_entry(self, user_id: int) -> Optional[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM search_queue WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        return dict(row) if row else None

    def find_match(
        self, user_id: int, gender_pref: str, location_pref: str,
        premium: bool,
    ) -> Optional[Dict[str, Any]]:
        """Atomically find a compatible partner and create a chat session.

        Bidirectional filter respect:
          - MY filters must match the candidate's profile.
          - Candidate's filters must match MY profile.
        Locks the search_queue, users, and chat_sessions rows to prevent
        double-matching. Unique partial indexes on chat_sessions additionally
        guarantee only one active session per user.
        """
        with self.transaction() as cur:
            # lock our own queue entry
            cur.execute(
                "SELECT * FROM search_queue WHERE user_id = %s FOR UPDATE",
                (user_id,),
            )
            mine = cur.fetchone()
            if not mine:
                return None

            # lock my own user row to read stable profile values
            me = self._get_user_for_update(cur, user_id)
            if not me:
                return None

            my_gender = me["gender"] or "any"
            my_city = me["city"] or "any"

            # Candidate filter clauses (my prefs vs. partner's profile).
            clauses: List[str] = []
            params: List[Any] = [user_id, user_id, user_id, user_id]
            if gender_pref and gender_pref != "any":
                clauses.append("u.gender = %s")
                params.append(gender_pref)
            if location_pref and location_pref != "any":
                clauses.append("u.city = %s")
                params.append(location_pref)
            candidate_filter = (" AND " + " AND ".join(clauses)) if clauses else ""

            # Partner's prefs must accept MY profile.
            partner_gender_clause = ""
            partner_location_clause = ""
            if my_gender and my_gender != "any":
                partner_gender_clause = (
                    " AND (q.gender_pref = 'any' OR q.gender_pref = %s)"
                )
                params.append(my_gender)
            if my_city and my_city != "any":
                partner_location_clause = (
                    " AND (q.location_pref = 'any' OR q.location_pref = %s)"
                )
                params.append(my_city)

            sql = f"""
                SELECT q.*, u.gender, u.city
                FROM search_queue q
                JOIN users u ON u.user_id = q.user_id
                WHERE q.user_id <> %s
                  AND q.user_id NOT IN (
                      SELECT blocked_id FROM blocked_users WHERE blocker_id = %s
                  )
                  AND %s NOT IN (
                      SELECT blocked_id FROM blocked_users WHERE blocker_id = q.user_id
                  )
                  AND NOT EXISTS (
                      SELECT 1 FROM chat_sessions cs
                      WHERE cs.status = 'active'
                        AND (cs.user_a = q.user_id OR cs.user_b = q.user_id)
                  )
                  AND u.user_id NOT IN (
                      SELECT cs.user_a FROM chat_sessions cs
                      WHERE cs.status = 'active' AND %s IN (cs.user_a, cs.user_b)
                  )
                  {partner_gender_clause}
                  {partner_location_clause}
                  {candidate_filter}
                ORDER BY q.premium DESC, q.created_at ASC
                LIMIT 5
                FOR UPDATE OF q SKIP LOCKED
            """
            cur.execute(sql, params)
            candidates = cur.fetchall()
            if not candidates:
                return None

            # take the first compatible candidate
            partner = candidates[0]

            try:
                cur.execute(
                    """
                    INSERT INTO chat_sessions (user_a, user_b, status, started_at)
                    VALUES (%s, %s, 'active', NOW())
                    RETURNING *
                    """,
                    (user_id, partner["user_id"]),
                )
                session = cur.fetchone()
            except Exception:
                # race: someone else grabbed one of us — unique indexes
                # rejected the insert; abort safely.
                raise

            cur.execute(
                "DELETE FROM search_queue WHERE user_id IN (%s, %s)",
                (user_id, partner["user_id"]),
            )
            cur.execute(
                "UPDATE users SET search_status = 'chatting' "
                "WHERE user_id IN (%s, %s)",
                (user_id, partner["user_id"]),
            )
            return dict(session)

    # internal helper used inside a transaction
    def _get_user_for_update(self, cur, user_id: int) -> Optional[Dict[str, Any]]:
        cur.execute(
            "SELECT * FROM users WHERE user_id = %s FOR UPDATE",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None

    def list_search_queue(self) -> List[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM search_queue ORDER BY created_at ASC"
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    # ==================================================================
    # REPORTS
    # ==================================================================
    def create_report(
        self,
        reporter_id: int,
        reported_user_id: int,
        chat_session_id: Optional[int],
        reason: str,
    ) -> Dict[str, Any]:
        with self._cursor() as (_, cur):
            cur.execute(
                """
                INSERT INTO reports
                  (reporter_id, reported_user_id, chat_session_id, reason, status)
                VALUES (%s, %s, %s, %s, 'open')
                RETURNING *
                """,
                (reporter_id, reported_user_id, chat_session_id, reason),
            )
            row = cur.fetchone()
        return dict(row)

    def count_reports_by_reporter_since(
        self, reporter_id: int, seconds: int
    ) -> int:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT COUNT(*) AS n FROM reports "
                "WHERE reporter_id = %s AND created_at > NOW() - (%s || ' seconds')::INTERVAL",
                (reporter_id, str(seconds)),
            )
            row = cur.fetchone()
        return int(row["n"]) if row else 0

    def list_open_reports(self, limit: int = 50) -> List[Dict[str, Any]]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM reports WHERE status = 'open' "
                "ORDER BY created_at DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
        return [dict(r) for r in rows]

    def set_report_status(self, report_id: int, status: str):
        with self._cursor() as (_, cur):
            cur.execute(
                "UPDATE reports SET status = %s WHERE id = %s",
                (status, report_id),
            )

    # ==================================================================
    # SETTINGS (overrides for prices etc.)
    # ==================================================================
    def get_setting(self, key: str, default: Optional[str] = None) -> Optional[str]:
        with self._cursor() as (_, cur):
            cur.execute(
                "SELECT value FROM bot_settings WHERE key = %s", (key,)
            )
            row = cur.fetchone()
        if row and row["value"] is not None:
            return row["value"]
        return default

    def set_setting(self, key: str, value: str):
        with self._cursor() as (_, cur):
            cur.execute(
                """
                INSERT INTO bot_settings (key, value, updated_at)
                VALUES (%s, %s, NOW())
                ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value,
                                                 updated_at = NOW()
                """,
                (key, value),
            )
