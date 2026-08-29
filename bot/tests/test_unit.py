"""Pure unit tests — no DB needed. Always runnable."""
import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from utils.validation import (
    validate_name, validate_bio, validate_age, validate_city,
    normalize_city, PERSIAN_CITIES,
)
from utils.persian import (
    fmt_balance, fmt_user_id, gender_filter_label, location_filter_label,
    GENDER_LABELS,
)
from utils.states import StateStore, States
from utils.rate_limit import RateLimiter
from services.referral import ReferralService
import config


class StubWallet:
    def __init__(self):
        self.credited = []
    def reward_referral(self, referrer_id):
        self.credited.append(referrer_id)


class StubUsers:
    def ensure_user(self, _):
        return {"internal_id": 1, "referral_count": 0}


class StubDB:
    def __init__(self):
        self.created = []
        self.marked = []
        self.updates = {}
    def create_referral(self, r, c):
        self.created.append((r, c))
        return {"id": len(self.created)} if (r, c) not in [(x[0], x[1]) for x in self.created[:-1]] else None
    def mark_referral_rewarded(self, rid):
        self.marked.append(rid)
    def update_user_fields(self, uid, **kw):
        self.updates[uid] = kw


def test_validate_name_accepts_persian():
    assert validate_name("علی رضا") is True or validate_name("علی رضا")  # tolerant


def test_validate_name_rejects_long():
    assert not validate_name("x" * 200)


def test_validate_bio_bounds():
    assert validate_bio("") is False
    assert validate_bio("hello")
    assert not validate_bio("x" * 501)


def test_validate_age():
    assert validate_age("25")
    assert not validate_age("12")
    assert not validate_age("121")
    assert not validate_age("abc")


def test_validate_city_persian():
    assert validate_city("تهران")
    assert not validate_city("")


def test_normalize_city():
    assert normalize_city("تهران") in PERSIAN_CITIES
    # something unknown — returned as-is
    assert normalize_city("نامشهود") == "نامشهود"


def test_fmt_balance():
    assert fmt_balance(1200) == "1,200 🪙"
    assert fmt_balance(0) == "0 🪙"


def test_fmt_user_id():
    assert fmt_user_id(482731) == "#482731"
    assert fmt_user_id(None) == "#?"


def test_gender_labels():
    assert gender_filter_label("any") == "🌐 همه"
    assert gender_filter_label("male") == "🚹 آقا"
    assert gender_filter_label("female") == "🚺 خانم"


def test_location_labels():
    assert location_filter_label("any") == "🌐 همه"
    assert location_filter_label("تهران").startswith("📍")


def test_state_store_basic():
    s = StateStore()
    assert s.state(1) == States.IDLE
    s.set(1, States.EDIT_BIO, {"old": "x"})
    assert s.state(1) == States.EDIT_BIO
    assert s.data(1)["old"] == "x"
    s.update(1, extra="y")
    assert s.data(1)["extra"] == "y"
    s.clear(1)
    assert s.state(1) == States.IDLE


def test_state_store_cleanup():
    import time as t
    s = StateStore()
    s.set(1, States.EDIT_BIO)
    s._store[1]["ts"] = t.time() - 99999
    n = s.cleanup(max_age_seconds=10)
    assert n == 1
    assert s.state(1) == States.IDLE


def test_rate_limiter_within_limit():
    rl = RateLimiter()
    for _ in range(5):
        assert rl.hit(1, 5, 60)
    assert not rl.hit(1, 5, 60)


def test_rate_limiter_separate_keys():
    rl = RateLimiter()
    for _ in range(5):
        assert rl.hit(1, 5, 60)
    assert rl.hit(2, 5, 60)  # different user


def test_referral_payload_parsing():
    rs = ReferralService(StubDB(), StubWallet(), StubUsers())
    assert rs.parse_referral_payload("ref_1234567") == 1234567
    assert rs.parse_referral_payload("") is None
    assert rs.parse_referral_payload("ref_") is None
    assert rs.parse_referral_payload("hello") is None
    assert rs.parse_referral_payload("ref_abc") is None


def test_referral_link_builds():
    rs = ReferralService(StubDB(), StubWallet(), StubUsers())
    link = rs.build_referral_link(123, "my_bot")
    assert link == "https://t.me/my_bot?start=ref_123"


def test_referral_self_rejected():
    db = StubDB()
    rs = ReferralService(db, StubWallet(), StubUsers())
    assert rs.process_referral(100, 100) is False
    assert db.created == []


def test_referral_idempotent():
    """Second call with same referrer/referred must NOT reward again."""
    db = StubDB()
    wallet = StubWallet()
    rs = ReferralService(db, wallet, StubUsers())
    # first call creates a referral
    assert rs.process_referral(100, 200)
    # second call: same referrer+referred — our stub returns None for the
    # second INSERT so no reward should happen
    db.create_referral = lambda *a, **k: None  # simulate unique constraint
    assert rs.process_referral(100, 200) is False
    assert len(wallet.credited) == 1
