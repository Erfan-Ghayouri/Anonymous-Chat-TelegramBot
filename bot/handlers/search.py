"""
Anonymous search handler — random + filtered matchmaking.

Flow:
  1. User clicks 🔎 جستجوی ناشناس from main reply keyboard.
  2. Bot shows the filter inline keyboard (gender / location / start).
  3. User picks filters; saved per-user.
  4. User clicks «شروع جستجو». Bot enqueues the search, sends "searching…".
  5. Background poller matches them; both users get the "match found" card
     with chat controls.
  6. Premium search charges coins first.
"""
from __future__ import annotations

import asyncio
import logging
import time

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import Database
from services.chat import ChatService
from services.matchmaking import MatchmakingService
from services.sponsors import SponsorService, sponsor_required
from services.users import UserService
from services.wallet import WalletService
from utils.keyboards import (
    MAIN_KB_LABELS,
    chat_controls_inline,
    gender_filter_inline,
    location_filter_inline,
    main_keyboard,
    search_filters_inline_stateful,
)
from utils.persian import (
    fmt_balance,
    gender_filter_label,
    location_filter_label,
)
from utils.rate_limit import search_limiter
from utils.states import state_store
from utils.validation import PERSIAN_CITIES
import config


logger = logging.getLogger(__name__)


def register_search_handlers(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
    users: UserService,
    wallet: WalletService,
    matchmaking: MatchmakingService,
    chats: ChatService,
):
    # ---- default filter storage on a per-user row in search_filters table --- #
    def _get_filters(user_id: int):
        with db._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM search_filters WHERE user_id = %s",
                (user_id,),
            )
            row = cur.fetchone()
        if not row:
            return {"gender_pref": "any", "location_pref": "any", "premium": False}
        return dict(row)

    def _save_filters(user_id: int, **kwargs):
        fields = ["gender_pref", "location_pref", "premium"]
        updates = {k: kwargs[k] for k in fields if k in kwargs}
        if not updates:
            return
        assignments = [f"{k} = %s" for k in updates]
        values = list(updates.values()) + [user_id]
        with db._cursor() as (_, cur):
            cur.execute(
                f"""
                INSERT INTO search_filters (user_id, {", ".join(updates.keys())})
                VALUES (%s, {", ".join(["%s"] * len(updates))})
                ON CONFLICT (user_id) DO UPDATE SET
                  {", ".join(f"{k} = EXCLUDED.{k}" for k in updates)}
                """,
                [user_id] + list(updates.values()),
            )

    async def _show_filters(message: Message):
        tg_id = message.from_user.id
        f = _get_filters(tg_id)
        gl = gender_filter_label(f["gender_pref"])
        ll = location_filter_label(f["location_pref"])
        await message.reply(
            "🔎 **جستجوی ناشناس**\n\n"
            "فیلترهای خود را تنظیم کنید و سپس روی «شروع جستجو» بزنید:",
            reply_markup=search_filters_inline_stateful(gl, ll),
        )

    # ----------------------------------------------------------------- #
    # entry from reply keyboard
    # ----------------------------------------------------------------- #
    @app.on_message(
        filters.text(MAIN_KB_LABELS["search"]) & filters.private
    )
    @sponsor_required(sponsor_service)
    async def search_kb(client: Client, message: Message):
        await _show_filters(message)

    # ----------------------------------------------------------------- #
    # premium entry
    # ----------------------------------------------------------------- #
    @app.on_message(
        filters.text(MAIN_KB_LABELS["premium"]) & filters.private
    )
    @sponsor_required(sponsor_service)
    async def premium_kb(client: Client, message: Message):
        tg_id = message.from_user.id
        bal = wallet.balance(tg_id)
        price = config.PREMIUM_SEARCH_PRICE
        if bal < price:
            await message.reply(
                f"⭐ **جستجوی ویژه**\n\n"
                f"برای فعال‌سازی جستجوی ویژه به {price:,} 🪙 نیاز دارید.\n"
                f"موجودی فعلی شما: {fmt_balance(bal)}\n\n"
                f"با دعوت دوستان یا خرید سکه، موجودی خود را افزایش دهید."
            )
            return
        await message.reply(
            f"⭐ **جستجوی ویژه**\n\n"
            f"هزینه: {price:,} 🪙\n"
            f"موجودی شما: {fmt_balance(bal)}\n\n"
            "با تأیید، {price} سکه از کیف شما کسر شده و جستجوی ویژه برای "
            "{min} دقیقه فعال می‌شود.".format(price=price, min=config.PREMIUM_SEARCH_DURATION_MIN),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("✅ تأیید و فعال‌سازی", callback_data="pm:buy"),
                        InlineKeyboardButton("❌ لغو", callback_data="pm:cancel"),
                    ]
                ]
            ),
        )

    @app.on_callback_query(filters.regex(r"^pm:(?P<action>buy|cancel)$"))
    async def premium_buy(client: Client, q: CallbackQuery):
        action = q.matches[0]["action"]
        if action == "cancel":
            await q.answer("لغو شد")
            try:
                await q.message.delete()
            except Exception:
                pass
            return
        tg_id = q.from_user.id
        result = wallet.charge_premium_search(tg_id)
        if not result:
            await q.answer(
                f"❌ موجودی کافی نیست. قیمت: {config.PREMIUM_SEARCH_PRICE:,} 🪙",
                show_alert=True,
            )
            return
        users.grant_premium(tg_id, config.PREMIUM_SEARCH_DURATION_MIN)
        _save_filters(tg_id, premium=True)
        await q.answer("✅ جستجوی ویژه فعال شد")
        await q.message.edit_text(
            f"⭐ جستجوی ویژه فعال شد.\n"
            f"مدت: {config.PREMIUM_SEARCH_DURATION_MIN} دقیقه\n\n"
            "حالا روی «جستجوی ناشناس» بزنید تا با اولویت ویژه جستجو کنید."
        )

    # ----------------------------------------------------------------- #
    # filter buttons: gender / location / start / back
    # ----------------------------------------------------------------- #
    @app.on_callback_query(filters.regex(r"^f:(?P<what>gender|location)$"))
    async def filter_pick(client: Client, q: CallbackQuery):
        what = q.matches[0]["what"]
        await q.answer()
        if what == "gender":
            await q.message.reply(
                "🔞 جنسیت مورد نظر خود را انتخاب کنید:",
                reply_markup=gender_filter_inline(),
            )
        elif what == "location":
            await q.message.reply(
                "📍 شهر مورد نظر خود را انتخاب کنید:",
                reply_markup=location_filter_inline(PERSIAN_CITIES[:20]),
            )

    @app.on_callback_query(filters.regex(r"^fg:(?P<value>male|female|any|back)$"))
    async def gender_filter_set(client: Client, q: CallbackQuery):
        value = q.matches[0]["value"]
        if value == "back":
            await q.answer()
            try:
                await q.message.delete()
            except Exception:
                pass
            return
        _save_filters(q.from_user.id, gender_pref=value)
        await q.answer("✅ ذخیره شد")

    @app.on_callback_query(filters.regex(r"^fl:(?P<city>[^:]+)$"))
    async def location_filter_set(client: Client, q: CallbackQuery):
        # the profile handler runs first if in EDIT_CITY state; if not, it
        # returns and we get here.
        st = state_store.state(q.from_user.id)
        from utils.states import States
        if st == States.EDIT_CITY:
            return  # let profile handler take it
        city = q.matches[0]["city"]
        if city == "back":
            await q.answer()
            try:
                await q.message.delete()
            except Exception:
                pass
            return
        _save_filters(q.from_user.id, location_pref=city)
        await q.answer("✅ ذخیره شد")

    @app.on_callback_query(filters.regex(r"^s:(?P<action>start|back|again)$"))
    async def search_action(client: Client, q: CallbackQuery):
        action = q.matches[0]["action"]
        if action == "back":
            await q.answer()
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.reply("🏠 منوی اصلی", reply_markup=main_keyboard())
            return
        if action == "again":
            await q.answer()
            await _do_search(q.message, q.from_user.id)
            return
        await q.answer()
        await _do_search(q.message, q.from_user.id)

    async def _do_search(message: Message, user_id: int):
        # rate-limit
        if not search_limiter.hit(user_id, 1, config.SEARCH_COOLDOWN_SEC):
            await message.reply(
                f"⏳ لطفاً چند ثانیه صبر کنید و دوباره تلاش کنید."
            )
            return
        # refuse if user has an active chat
        if chats.active_session_for(user_id):
            await message.reply(
                "💬 شما در یک گفتگوی فعال هستید. ابتدا آن را پایان دهید."
            )
            return
        f = _get_filters(user_id)
        is_premium = users.is_premium(user_id)
        try:
            matchmaking.start_search(
                user_id,
                gender_pref=f["gender_pref"],
                location_pref=f["location_pref"],
                premium=bool(f.get("premium") or is_premium),
            )
        except RuntimeError:
            await message.reply("⚠️ شما در حال حاضر در صف جستجو هستید.")
            return

        await message.reply(
            "🔎 در حال جستجوی فرد مناسب...\n"
            "چند لحظه صبر کنید. به‌محض یافتن کاربر، به شما اطلاع می‌دهیم."
        )
        # wait for match in background (no blocking here; the poller will
        # notify. But also do a one-shot immediate attempt.)
        asyncio.create_task(_wait_for_match(message, user_id))

    async def _wait_for_match(message: Message, user_id: int):
        try:
            session = await matchmaking.wait_for_match(
                user_id, timeout_s=config.MAX_SEARCH_QUEUE_SECONDS
            )
        except Exception as exc:
            logger.exception("wait_for_match: %s", exc)
            session = None
        if not session:
            # search timed out / cancelled
            matchmaking.cancel_search(user_id)
            try:
                await message.reply(
                    "⚠️ کاربری مطابق فیلترهای شما یافت نشد.\n"
                    "می‌توانید فیلترها را بازتر کنید یا کمی بعد دوباره تلاش کنید.",
                    reply_markup=InlineKeyboardMarkup(
                        [[InlineKeyboardButton("🔎 جستجوی مجدد", callback_data="s:again")]]
                    ),
                )
            except Exception:
                pass
            return
        # match found — notify both users
        await _notify_match(session)

    async def _notify_match(session):
        a, b = session["user_a"], session["user_b"]
        text = (
            "🎉 **فردی پیدا شد!**\n\n"
            "گفتگوی ناشناس شما آغاز شد. هر پیامی بفرستید به‌صورت کاملاً "
            "ناشناس برای شخص مقابل ارسال می‌شود.\n\n"
            "⚠️ هرگز اطلاعات شخصی (شماره، آیدی، آدرس) را فاش نکنید."
        )
        for uid in (a, b):
            try:
                await app.send_message(
                    uid,
                    text,
                    reply_markup=chat_controls_inline(),
                )
            except Exception as exc:
                logger.warning("notify match user=%s failed: %s", uid, exc)
