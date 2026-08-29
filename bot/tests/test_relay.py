"""
Tests for the message relay.

These use a fake Pyrogram Client so we don't need a real Telegram connection.
"""
import asyncio
import os
import sys
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from .conftest import PG_AVAILABLE


pytestmark = pytest.mark.skipif(
    not PG_AVAILABLE, reason="TEST_DATABASE_URL / DATABASE_URL not reachable"
)


def _run(coro):
    return asyncio.run(coro)


class FakeMessage:
    def __init__(self, chat_id, message_id, from_user_id):
        self.chat = type("C", (), {"id": chat_id})()
        self.id = message_id
        self.from_user = type("U", (), {"id": from_user_id})()


class FakeClient:
    def __init__(self):
        self.copies = []
    async def copy_message(self, chat_id, from_chat_id, message_id):
        self.copies.append((chat_id, from_chat_id, message_id))


def test_relay_no_active_session(fresh_db):
    from services.chat import ChatService
    from services.blocks import BlockService
    chats = ChatService(fresh_db, BlockService(fresh_db))
    client = FakeClient()
    msg = FakeMessage(999, 1, 999)  # user 999 not in DB
    delivered = _run(chats.relay(client, msg))
    assert delivered is False
    assert client.copies == []


def test_relay_delivers_to_partner(fresh_db):
    from services.users import UserService
    from services.matchmaking import MatchmakingService
    from services.chat import ChatService
    from services.blocks import BlockService
    users = UserService(fresh_db)
    users.ensure_user(20001)
    users.ensure_user(20002)
    users.set_gender(20001, "male")
    users.set_gender(20002, "female")
    mm = MatchmakingService(fresh_db)
    chats = ChatService(fresh_db, BlockService(fresh_db))
    mm.start_search(20001)
    mm.start_search(20002)
    mm.attempt_match(20001)

    client = FakeClient()
    # user 20001 sends a message -> should copy to 20002
    msg = FakeMessage(20001, 42, 20001)
    delivered = _run(chats.relay(client, msg))
    assert delivered is True
    assert client.copies == [(20002, 20001, 42)]

    # user 20002 sends a message -> should copy to 20001
    msg2 = FakeMessage(20002, 7, 20002)
    delivered2 = _run(chats.relay(client, msg2))
    assert delivered2 is True
    assert client.copies[-1] == (20001, 20002, 7)


def test_relay_after_session_ends(fresh_db):
    """A message sent AFTER the session ended must NOT be relayed."""
    from services.users import UserService
    from services.matchmaking import MatchmakingService
    from services.chat import ChatService
    from services.blocks import BlockService
    users = UserService(fresh_db)
    users.ensure_user(30001)
    users.ensure_user(30002)
    users.set_gender(30001, "male")
    users.set_gender(30002, "female")
    mm = MatchmakingService(fresh_db)
    chats = ChatService(fresh_db, BlockService(fresh_db))
    mm.start_search(30001)
    mm.start_search(30002)
    s = mm.attempt_match(30001)
    # end the session
    chats.end_session(s["id"], 30001)
    # now send a message — should not be relayed
    client = FakeClient()
    msg = FakeMessage(30001, 100, 30001)
    delivered = _run(chats.relay(client, msg))
    assert delivered is False
    assert client.copies == []
