"""
Persian reply + inline keyboards used throughout the bot.

The main reply keyboard has 7 buttons arranged in a 3x3-ish grid (one cell
empty). The chat keyboard is INLINE only — reply keyboards would intercept
the user's text input and break the relay.
"""
from __future__ import annotations

from typing import List, Optional

from pyrogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ReplyKeyboardMarkup,
    KeyboardButton,
)


# ---------- reply keyboard ---------- #
MAIN_KB_LABELS = {
    "profile":   "👤 پروفایل من",
    "search":    "🔎 جستجوی ناشناس",
    "premium":   "⭐ جستجوی ویژه",
    "wallet":    "💰 کیف پول",
    "guide":     "📖 راهنما",
    "invite":    "🎁 دعوت دوستان",
    "settings":  "⚙️ تنظیمات",
}


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [
            [
                KeyboardButton(MAIN_KB_LABELS["profile"]),
                KeyboardButton(MAIN_KB_LABELS["search"]),
                KeyboardButton(MAIN_KB_LABELS["premium"]),
            ],
            [
                KeyboardButton(MAIN_KB_LABELS["wallet"]),
                KeyboardButton(MAIN_KB_LABELS["guide"]),
                KeyboardButton(MAIN_KB_LABELS["invite"]),
            ],
            [KeyboardButton(MAIN_KB_LABELS["settings"])],
        ],
        resize_keyboard=True,
        is_persistent=False,
    )


def back_only_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        [[KeyboardButton("🔙 بازگشت")]],
        resize_keyboard=True,
        is_persistent=False,
    )


# ---------- inline keyboards ---------- #
def profile_inline_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✏️ ویرایش پروفایل", callback_data="p:edit"),
                InlineKeyboardButton("📝 ویرایش بیو", callback_data="p:bio"),
            ],
            [
                InlineKeyboardButton("⚧ تغییر جنسیت", callback_data="p:gender"),
                InlineKeyboardButton("📍 تغییر موقعیت", callback_data="p:city"),
            ],
            [
                InlineKeyboardButton("👤 نام نمایشی", callback_data="p:name"),
                InlineKeyboardButton("🎂 تغییر سن", callback_data="p:age"),
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="p:back")],
        ]
    )


def gender_picker_inline(callback_prefix: str = "g") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚹 آقا", callback_data=f"{callback_prefix}:male"),
                InlineKeyboardButton("🚺 خانم", callback_data=f"{callback_prefix}:female"),
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data=f"{callback_prefix}:back")],
        ]
    )


def search_filters_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⚧ جنسیت: همه", callback_data="f:gender"),
                InlineKeyboardButton("📍 موقعیت: همه", callback_data="f:location"),
            ],
            [InlineKeyboardButton("🔎 شروع جستجو", callback_data="s:start")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="s:back")],
        ]
    )


def search_filters_inline_stateful(
    gender_label: str, location_label: str
) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(f"⚧ جنسیت: {gender_label}", callback_data="f:gender"),
                InlineKeyboardButton(f"📍 موقعیت: {location_label}", callback_data="f:location"),
            ],
            [InlineKeyboardButton("🔎 شروع جستجو", callback_data="s:start")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="s:back")],
        ]
    )


def gender_filter_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🚹 آقا", callback_data="fg:male"),
                InlineKeyboardButton("🚺 خانم", callback_data="fg:female"),
            ],
            [InlineKeyboardButton("🌐 همه", callback_data="fg:any")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="fg:back")],
        ]
    )


def location_filter_inline(cities: List[str]) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    chunk = 2
    for i in range(0, len(cities), chunk):
        row = []
        for c in cities[i : i + chunk]:
            row.append(InlineKeyboardButton(c, callback_data=f"fl:{c}"))
        rows.append(row)
    rows.append([InlineKeyboardButton("🌐 همه شهرها", callback_data="fl:any")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="fl:back")])
    return InlineKeyboardMarkup(rows)


def chat_controls_inline() -> InlineKeyboardMarkup:
    """The ONLY chat-control buttons. NO Direct Message button anywhere."""
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("⏭ شخص بعدی", callback_data="c:next"),
                InlineKeyboardButton("🚫 مسدود", callback_data="c:block"),
            ],
            [
                InlineKeyboardButton("❌ پایان گفتگو", callback_data="c:end"),
                InlineKeyboardButton("🚨 گزارش", callback_data="c:report"),
            ],
        ]
    )


def search_again_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔎 جستجوی مجدد", callback_data="s:again")]]
    )


def wallet_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📜 تاریخچه تراکنش‌ها", callback_data="w:tx")],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="w:back")],
        ]
    )


def invite_inline(ref_link: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📤 ارسال لینک دعوت", url=ref_link)],
            [InlineKeyboardButton("📋 کپی لینک دعوت", switch_inline_query=ref_link)],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="i:back")],
        ]
    )


def settings_inline(is_premium: bool) -> InlineKeyboardMarkup:
    rows: List[List[InlineKeyboardButton]] = []
    label = "✅ ویژه فعال" if is_premium else "❌ بدون ویژه"
    rows.append([InlineKeyboardButton(label, callback_data="st:noop")])
    rows.append([InlineKeyboardButton("🚫 لیست مسدود شده‌ها", callback_data="st:blocked")])
    rows.append([InlineKeyboardButton("🆘 پشتیبانی", callback_data="st:support")])
    rows.append([InlineKeyboardButton("🔙 بازگشت", callback_data="st:back")])
    return InlineKeyboardMarkup(rows)


def help_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔎 جستجو", callback_data="h:search"),
                InlineKeyboardButton("👤 پروفایل", callback_data="h:profile"),
            ],
            [
                InlineKeyboardButton("🚫 مسدود", callback_data="h:block"),
                InlineKeyboardButton("🚨 گزارش", callback_data="h:report"),
            ],
            [
                InlineKeyboardButton("💰 کیف پول", callback_data="h:wallet"),
                InlineKeyboardButton("🎁 دعوت", callback_data="h:invite"),
            ],
            [
                InlineKeyboardButton("⭐ ویژه", callback_data="h:premium"),
                InlineKeyboardButton("💬 چت", callback_data="h:chat"),
            ],
            [InlineKeyboardButton("🔙 بازگشت", callback_data="h:back")],
        ]
    )


def admin_main_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("📊 آمار", callback_data="a:stats"),
                InlineKeyboardButton("📨 پیام همگانی", callback_data="a:broadcast"),
            ],
            [
                InlineKeyboardButton("🚨 گزارش‌ها", callback_data="a:reports"),
                InlineKeyboardButton("⚙️ تنظیمات", callback_data="a:settings"),
            ],
            [InlineKeyboardButton("🔙 بستن", callback_data="a:close")],
        ]
    )


def admin_back_inline() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🔙 بازگشت", callback_data="a:back")]]
    )


def confirm_cancel_inline(prefix: str = "x") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ تأیید", callback_data=f"{prefix}:yes"),
                InlineKeyboardButton("❌ لغو", callback_data=f"{prefix}:no"),
            ]
        ]
    )
