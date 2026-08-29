"""Persian display helpers."""
from __future__ import annotations

from typing import Any, Dict


GENDER_LABELS = {
    "male":   "🚹 آقا",
    "female": "🚺 خانم",
    None:     "نامشخص",
}

GENDER_LABELS_FILTER = {
    "any":    "🌐 همه",
    "male":   "🚹 آقا",
    "female": "🚺 خانم",
}

LOCATION_LABELS_FILTER = {
    "any": "🌐 همه",
}


def user_gender_label(user: Dict[str, Any]) -> str:
    return GENDER_LABELS.get(user.get("gender"), GENDER_LABELS[None])


def gender_filter_label(value: str) -> str:
    return GENDER_LABELS_FILTER.get(value, value)


def location_filter_label(value: str) -> str:
    if value in (None, "", "any"):
        return LOCATION_LABELS_FILTER["any"]
    return f"📍 {value}"


def fmt_balance(coins: int) -> str:
    return f"{int(coins):,} 🪙"


def fmt_user_id(internal_id: Any) -> str:
    if internal_id is None:
        return "#?"
    return f"#{int(internal_id)}"


def fmt_relative(ts) -> str:
    """Human-friendly Persian relative time."""
    if not ts:
        return "-"
    try:
        ts = ts.timestamp()
    except AttributeError:
        try:
            ts = float(ts)
        except Exception:
            return "-"
    now = __import__("time").time()
    diff = int(now - ts)
    if diff < 60:
        return "همین الان"
    if diff < 3600:
        return f"{diff // 60} دقیقه پیش"
    if diff < 86400:
        return f"{diff // 3600} ساعت پیش"
    return f"{diff // 86400} روز پیش"
