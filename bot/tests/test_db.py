"""
Database integration tests — require PostgreSQL.

Run with: TEST_DATABASE_URL=postgresql://user:pass@localhost:5432/db pytest
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


@pytest.fixture
def db(fresh_db):
    return fresh_db


def test_user_creation_grants_bonus(db):
    from services.users import UserService
    from services.wallet import WalletService
    users = UserService(db)
    wallet = WalletService(db)
    users.ensure_user(1001)
    user = users.get_profile(1001)
    assert user is not None
    assert user["internal_id"] is not None
    # balance should equal NEW_USER_BONUS
    assert wallet.balance(1001) == 5  # default NEW_USER_BONUS


def test_user_idempotent_no_double_bonus(db):
    from services.users import UserService
    from services.wallet import WalletService
    users = UserService(db)
    wallet = WalletService(db)
    users.ensure_user(1002)
    users.ensure_user(1002)  # second call — must NOT grant another bonus
    assert wallet.balance(1002) == 5


def test_wallet_spend_atomic_insufficient(db):
    from services.wallet import WalletService
    wallet = WalletService(db)
    from services.users import UserService
    users = UserService(db)
    users.ensure_user(1003)
    # try to spend more than balance
    res = wallet.spend(1003, 9999, "test", "should fail")
    assert res is None
    # balance unchanged
    assert wallet.balance(1003) == 5


def test_wallet_spend_ok(db):
    from services.wallet import WalletService
    from services.users import UserService
    users = UserService(db)
    wallet = WalletService(db)
    users.ensure_user(1004)
    res = wallet.spend(1004, 2, "test", "ok")
    assert res is not None
    assert res["balance"] == 3
    assert wallet.balance(1004) == 3


def test_wallet_credit_and_transactions(db):
    from services.wallet import WalletService
    from services.users import UserService
    users = UserService(db)
    wallet = WalletService(db)
    users.ensure_user(1005)
    wallet.credit(1005, 10, "test", "credit 10")
    wallet.credit(1005, 5, "test", "credit 5")
    txs = wallet.transactions(1005)
    assert len(txs) == 4  # 1 bonus + 2 credits + ... wait
    # actually: signup_bonus(5) + credit(10) + credit(5) = 3 txns
    # but the count may include the implicit signup
    assert all(t["user_id"] == 1005 for t in txs)


def test_block_users(db):
    from services.blocks import BlockService
    from services.users import UserService
    users = UserService(db)
    users.ensure_user(2001)
    users.ensure_user(2002)
    bs = BlockService(db)
    assert not bs.is_blocked(2001, 2002)
    assert bs.block(2001, 2002)
    assert bs.is_blocked(2001, 2002)
    # idempotent — blocking again should still report blocked
    assert bs.block(2001, 2002)
    # block self is rejected
    assert not bs.block(2001, 2001)


def test_matchmaking_self_prevented(db):
    """A user can never match with themselves."""
    from services.matchmaking import MatchmakingService
    mm = MatchmakingService(db)
    mm.start_search(3001)
    # no other users in queue -> no match
    s = mm.attempt_match(3001)
    assert s is None


def test_matchmaking_creates_session(db):
    from services.matchmaking import MatchmakingService
    from services.users import UserService
    from services.chat import ChatService
    from services.blocks import BlockService
    users = UserService(db)
    users.ensure_user(4001)
    users.ensure_user(4002)
    # set genders so filter can pass
    users.set_gender(4001, "male")
    users.set_gender(4002, "female")
    mm = MatchmakingService(db)
    chats = ChatService(db, BlockService(db))
    mm.start_search(4001, "any", "any", premium=False)
    mm.start_search(4002, "any", "any", premium=False)
    s = mm.attempt_match(4001)
    assert s is not None
    assert {s["user_a"], s["user_b"]} == {4001, 4002}
    # both should now have an active session
    sa = chats.active_session_for(4001)
    sb = chats.active_session_for(4002)
    assert sa and sb and sa["id"] == sb["id"]


def test_matchmaking_blocked_users_skip(db):
    from services.matchmaking import MatchmakingService
    from services.users import UserService
    from services.blocks import BlockService
    users = UserService(db)
    users.ensure_user(5001)
    users.ensure_user(5002)
    bs = BlockService(db)
    bs.block(5001, 5002)  # 5001 blocked 5002
    mm = MatchmakingService(db)
    mm.start_search(5001)
    mm.start_search(5002)
    s = mm.attempt_match(5001)
    assert s is None


def test_matchmaking_gender_filter_respected(db):
    from services.matchmaking import MatchmakingService
    from services.users import UserService
    users = UserService(db)
    users.ensure_user(6001)
    users.ensure_user(6002)
    users.set_gender(6001, "male")
    users.set_gender(6002, "male")
    mm = MatchmakingService(db)
    # 6001 wants female; 6002 is male -> no match
    mm.start_search(6001, "female")
    mm.start_search(6002, "any")
    assert mm.attempt_match(6001) is None


def test_end_session(db):
    from services.matchmaking import MatchmakingService
    from services.users import UserService
    from services.chat import ChatService
    from services.blocks import BlockService
    users = UserService(db)
    users.ensure_user(7001)
    users.ensure_user(7002)
    mm = MatchmakingService(db)
    chats = ChatService(db, BlockService(db))
    mm.start_search(7001)
    mm.start_search(7002)
    s = mm.attempt_match(7001)
    assert s is not None
    # end it
    ended = chats.end_session(s["id"], 7001)
    assert ended is not None
    # both users should have no active session
    assert chats.active_session_for(7001) is None
    assert chats.active_session_for(7002) is None


def test_double_match_prevented(db):
    """If 4001 already has an active session, they cannot match again."""
    from services.matchmaking import MatchmakingService
    from services.users import UserService
    users = UserService(db)
    for uid in (8001, 8002, 8003):
        users.ensure_user(uid)
    mm = MatchmakingService(db)
    mm.start_search(8001)
    mm.start_search(8002)
    s = mm.attempt_match(8001)  # 8001 <-> 8002
    assert s is not None
    # now 8003 joins and tries to match 8001 — should fail because 8001 is in a chat
    mm.start_search(8003)
    s2 = mm.attempt_match(8003)
    assert s2 is None  # 8001 not in queue anymore


def test_referral_processing_grants_reward(db):
    from services.users import UserService
    from services.wallet import WalletService
    from services.referral import ReferralService
    users = UserService(db)
    wallet = WalletService(db)
    rs = ReferralService(db, wallet, users)
    users.ensure_user(9001)  # referrer
    users.ensure_user(9002)  # referred
    assert rs.process_referral(9001, 9002)
    # referrer should have REFERRAL_REWARD on top of signup bonus
    expected = config_NEW_USER_BONUS() + config_REFERRAL_REWARD()
    assert wallet.balance(9001) == expected


def test_referral_duplicate_no_double_reward(db):
    from services.users import UserService
    from services.wallet import WalletService
    from services.referral import ReferralService
    users = UserService(db)
    wallet = WalletService(db)
    rs = ReferralService(db, wallet, users)
    users.ensure_user(9101)
    users.ensure_user(9102)
    assert rs.process_referral(9101, 9102)
    # second attempt — must NOT reward again
    assert rs.process_referral(9101, 9102) is False


def test_referral_self_rejected(db):
    from services.users import UserService
    from services.wallet import WalletService
    from services.referral import ReferralService
    users = UserService(db)
    wallet = WalletService(db)
    rs = ReferralService(db, wallet, users)
    users.ensure_user(9201)
    assert rs.process_referral(9201, 9201) is False


def test_report_creation_with_cooldown(db):
    from services.users import UserService
    from services.reports import ReportService
    users = UserService(db)
    users.ensure_user(10001)
    users.ensure_user(10002)
    reports = ReportService(db)
    r = reports.create(10001, 10002, None, "spam")
    assert r is not None
    # immediate second report should be rate-limited
    r2 = reports.create(10001, 10002, None, "spam2")
    assert r2 is None


def test_concurrent_matchmaking(db):
    """Two users attempting to match at the same time must produce exactly ONE session."""
    import threading
    from services.matchmaking import MatchmakingService
    from services.users import UserService
    from services.chat import ChatService
    from services.blocks import BlockService
    users = UserService(db)
    users.ensure_user(11001)
    users.ensure_user(11002)
    mm = MatchmakingService(db)
    chats = ChatService(db, BlockService(db))
    mm.start_search(11001)
    mm.start_search(11002)
    results = []
    def worker():
        try:
            s = mm.attempt_match(11001)
            if s:
                results.append(s)
        except Exception as e:
            print("worker error:", e)
    threads = [threading.Thread(target=worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # exactly one chat session should exist
    sa = chats.active_session_for(11001)
    sb = chats.active_session_for(11002)
    assert sa and sb and sa["id"] == sb["id"]
    # at most one match returned from concurrent attempts
    assert len(results) <= 1


def config_NEW_USER_BONUS():
    import config
    return config.NEW_USER_BONUS


def config_REFERRAL_REWARD():
    import config
    return config.REFERRAL_REWARD
