"""
Chat session service + anonymous message relay.

The relay is the heart of the bot: every message sent by either user in an
active session is forwarded to the other participant, with no "Direct Message"
button and no Telegram-side identity leak.

Approach: use Pyrogram's `copy_message` to send the message to the partner.
`copy_message` does NOT include a "forwarded from" header, so the partner
sees the message as if it came from the bot directly. The original sender's
Telegram ID is never exposed.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from pyrogram import Client
from pyrogram.types import Message
from pyrogram.errors import (
    UserIsBlocked,
    ChatIdInvalid,
    PeerIdInvalid,
    Forbidden,
    SlowmodeWait,
    FloodWait,
    RPCError,
)

from database.db import Database
from services.blocks import BlockService

logger = logging.getLogger(__name__)


class ChatService:
    def __init__(self, db: Database, blocks: BlockService):
        self.db = db
        self.blocks = blocks

    # ------------------------------------------------------------------
    # session lookups
    # ------------------------------------------------------------------
    def active_session_for(self, user_id: int) -> Optional[Dict[str, Any]]:
        return self.db.get_active_session_for_user(user_id)

    def partner_of(self, session: Dict[str, Any], user_id: int) -> Optional[int]:
        """Return the partner's telegram_id for this session, or None."""
        if session["user_a"] == user_id:
            return session["user_b"]
        if session["user_b"] == user_id:
            return session["user_a"]
        return None

    # ------------------------------------------------------------------
    # session lifecycle
    # ------------------------------------------------------------------
    def end_session(
        self,
        session_id: int,
        ended_by: int,
    ) -> Optional[Dict[str, Any]]:
        session = self.db.end_session(session_id, ended_by)
        if session:
            self.db.update_user_fields(
                session["user_a"], search_status="idle"
            )
            self.db.update_user_fields(
                session["user_b"], search_status="idle"
            )
        return session

    def end_session_for_user(self, user_id: int) -> Optional[Dict[str, Any]]:
        """Convenience: end whatever active session this user has."""
        session = self.active_session_for(user_id)
        if not session:
            return None
        return self.end_session(session["id"], user_id)

    # ------------------------------------------------------------------
    # message relay
    # ------------------------------------------------------------------
    async def relay(
        self,
        client: Client,
        message: Message,
    ) -> bool:
        """Relay `message` to the sender's partner.

        Returns True if delivered, False if the sender has no active session
        (handlers should treat as "no-op").
        """
        sender_id = message.from_user.id if message.from_user else None
        if not sender_id:
            return False

        # ignore our own bot messages / channel posts etc.
        if message.chat and message.chat.id != sender_id:
            # only relay DM messages (private chat with bot)
            return False

        session = self.active_session_for(sender_id)
        if not session:
            return False

        # race: session may have just ended (status flip happened between our
        # SELECT and now). Re-check status atomically.
        if session["status"] != "active":
            return False

        partner_id = self.partner_of(session, sender_id)
        if not partner_id or partner_id == sender_id:
            return False

        try:
            await client.copy_message(
                chat_id=partner_id,
                from_chat_id=message.chat.id,
                message_id=message.id,
            )
            return True
        except (UserIsBlocked, ChatIdInvalid, PeerIdInvalid, Forbidden):
            # partner blocked the bot or deleted their account
            logger.info(
                "Partner %s unreachable; ending session %s",
                partner_id, session["id"],
            )
            self.end_session(session["id"], sender_id)
            return False
        except FloodWait as fw:
            logger.warning("FloodWait %s while relaying", fw.value)
            return False
        except SlowmodeWait:
            return False
        except RPCError as exc:
            logger.warning("Relay RPC error: %s", exc)
            return False
        except Exception as exc:
            logger.exception("Unexpected relay error: %s", exc)
            return False

    # ------------------------------------------------------------------
    # block + end combined (used by the Block button)
    # ------------------------------------------------------------------
    def block_and_end(
        self,
        blocker_id: int,
    ) -> Optional[Dict[str, Any]]:
        """End the active session for `blocker_id` and add a block relation."""
        session = self.active_session_for(blocker_id)
        if not session:
            return None
        partner_id = self.partner_of(session, blocker_id)
        ended = self.end_session(session["id"], blocker_id)
        if partner_id:
            self.blocks.block(blocker_id, partner_id)
        return ended

    # ------------------------------------------------------------------
    # stats
    # ------------------------------------------------------------------
    def active_count(self) -> int:
        return self.db.count_active_sessions()

    def total_count(self) -> int:
        return self.db.count_total_sessions()
