"""
Centralized configuration loader.

All configurable business values (prices, rewards, etc.) MUST be read here,
never hard-coded in handlers or services.
"""
import os
from typing import List

from dotenv import load_dotenv

load_dotenv()


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env(name: str, default: str) -> str:
    val = os.getenv(name)
    if val is None or val.strip() == "":
        return default
    return val.strip()


def _env_list_int(name: str, fallback_name: str | None = None) -> List[int]:
    """Parse a comma-separated list of ints. Falls back to a single-int env var."""
    raw = os.getenv(name)
    ids: List[int] = []
    if raw and raw.strip():
        for part in raw.split(","):
            part = part.strip()
            if part.isdigit():
                ids.append(int(part))
    if not ids and fallback_name:
        fb = os.getenv(fallback_name)
        if fb and fb.strip().isdigit():
            ids.append(int(fb.strip()))
    return ids


# --- Telegram / bot credentials ---
API_ID: int = _env_int("API_ID", 0)
API_HASH: str = _env("API_HASH", "")
BOT_TOKEN: str = _env("BOT_TOKEN", "")
BOT_USERNAME: str = _env("BOT_USERNAME", "").lstrip("@")

# --- Database ---
DATABASE_URL: str = _env("DATABASE_URL", "")

# --- Admins ---
ADMIN_IDS: List[int] = _env_list_int("ADMIN_IDS", fallback_name="ADMIN_ID")

# --- Pricing / economy (all configurable, no hard-coded prices elsewhere) ---
NEW_USER_BONUS: int = _env_int("NEW_USER_BONUS", 5)
REFERRAL_REWARD: int = _env_int("REFERRAL_REWARD", 20)
PREMIUM_SEARCH_PRICE: int = _env_int("PREMIUM_SEARCH_PRICE", 50)
PREMIUM_SEARCH_DURATION_MIN: int = _env_int("PREMIUM_SEARCH_DURATION_MIN", 30)

# --- Rate limits & anti-abuse ---
REPORT_COOLDOWN_SEC: int = _env_int("REPORT_COOLDOWN_SEC", 60)
SEARCH_COOLDOWN_SEC: int = _env_int("SEARCH_COOLDOWN_SEC", 3)
MSG_PER_MIN_LIMIT: int = _env_int("MSG_PER_MIN_LIMIT", 60)

# --- Matchmaking tuning ---
MAX_SEARCH_QUEUE_SECONDS: int = _env_int("MAX_SEARCH_QUEUE_SECONDS", 120)
INACTIVE_USER_TIMEOUT_HOURS: int = _env_int("INACTIVE_USER_TIMEOUT_HOURS", 168)

# --- Bot behavior ---
ENABLE_SPONSOR_CHECK: bool = _env("ENABLE_SPONSOR_CHECK", "1") == "1"


def is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS
