"""
Chat handler — anonymous message relay + chat controls.

Relay behavior (THE central feature):
  • Any private message from a user who has an active chat session is
    forwarded to the other participant via `client.copy_message`.
  • `copy_message` does NOT include a "forwarded from" header, so the
    partner sees the message as a fresh bot message — anonymous.

Chat controls (inline only, NO Direct Message button):
  • ⏭ شخص بعدی (Next)  -> end current + start new search
  • 🚫 مسدود (Block)  -> block + end
  • ❌ پایان گفتگو (End) -> end session, notify both
  • 🚨 گزارش (Report)  -> prompt for reason (FSM)
"""
from __future__ import annotations

import asyncio
import logging

from pyrogram import Client, filters, ContinuePropagation
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import Database
from services.chat import ChatService
from services.matchmaking import MatchmakingService
from services.reports import ReportService
from services.sponsors import SponsorService, sponsor_required
from services.users import UserService
from utils.keyboards import (
    chat_controls_inline,
    main_keyboard,
    search_again_inline,
    back_only_keyboard,
)
from utils.persian import fmt_user_id
from utils.rate_limit import message_limiter
from utils.states import States, state_store
import config


logger = logging.getLogger(__name__)


def register_chat_handlers(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
    users: UserService,
    chats: ChatService,
    matchmaking: MatchmakingService,
    reports: ReportService,
):
    # ---------------------------------------------------------------- #
    # CHAT CONTROL CALLBACKS  (c:)
    # ---------------------------------------------------------------- #
    @app.on_callback_query(filters.regex(r"^c:(?P<action>next|block|end|report)$"))
    async def chat_control(client: Client, q: CallbackQuery):
        action = q.matches[0]["action"]
        tg_id = q.from_user.id
        session = chats.active_session_for(tg_id)
        if not session:
            await q.answer("❌ گفتگویی فعال نیست.", show_alert=True)
            return
        partner_id = chats.partner_of(session, tg_id)
        partner_user = users.get_profile(partner_id) if partner_id else None
        partner_id_label = (
            fmt_user_id(partner_user.get("internal_id"))
            if partner_user else "#?"
        )

        if action == "next":
            # end current
            chats.end_session(session["id"], tg_id)
            await q.answer("پایان یافت — در حال جستجوی فرد جدید...")
            # notify partner
            try:
                await app.send_message(
                    partner_id,
                    "⏭ طرف مقابل گفتگو را ترک کرد.\n"
                    "می‌توانید دوباره جستجو کنید.",
                    reply_markup=search_again_inline(),
                )
            except Exception as exc:
                logger.warning("notify partner (next) failed: %s", exc)
            try:
                await q.message.delete()
            except Exception:
                pass
            # immediately enter new search
            await _start_new_search(app, tg_id, q.message)

        elif action == "block":
            chats.block_and_end(tg_id)
            await q.answer("🚫 مسدود شد")
            try:
                await app.send_message(
                    partner_id,
                    "❌ طرف مقابل گفتگو را به اتمام رساند.",
                    reply_markup=search_again_inline(),
                )
            except Exception as exc:
                logger.warning("notify partner (block) failed: %s", exc)
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.reply(
                "🚫 کاربر مقابل مسدود شد.\n"
                "دیگر هرگز با شما مچ نخواهد شد.",
                reply_markup=main_keyboard(),
            )

        elif action == "end":
            chats.end_session(session["id"], tg_id)
            await q.answer("پایان یافت")
            try:
                await app.send_message(
                    partner_id,
                    "❌ طرف مقابل گفتگو را پایان داد.\n"
                    "هر زمان که خواستید می‌توانید دوباره جستجو کنید.",
                    reply_markup=search_again_inline(),
                )
            except Exception as exc:
                logger.warning("notify partner (end) failed: %s", exc)
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.reply(
                "❌ **گفتگو پایان یافت.**\n\n"
                "هر زمان که خواستید می‌توانید دوباره جستجو کنید.",
                reply_markup=search_again_inline(),
            )

        elif action == "report":
            # set FSM state to collect reason
            state_store.set(
                tg_id,
                States.REPORT_REASON,
                {
                    "reported_user_id": partner_id,
                    "chat_session_id": session["id"],
                    "partner_label": partner_id_label,
                },
            )
            await q.answer()
            await q.message.reply(
                f"🚨 لطفاً دلیل گزارش کاربر {partner_id_label} را در یک پیام بنویسید:\n"
                "(حداکثر ۱۰۰۰ کاراکتر) — برای لغو «بازگشت» را بزنید.",
                reply_markup=back_only_keyboard(),
            )

    # ---------------------------------------------------------------- #
    # REPORT REASON TEXT INPUT  (group=5 so it doesn't clash with relay)
    # ---------------------------------------------------------------- #
    @app.on_message(
        filters.text & filters.private,
        group=5,
    )
    async def report_reason_handler(client: Client, message: Message):
        tg_id = message.from_user.id
        st = state_store.state(tg_id)
        if st != States.REPORT_REASON:
            return  # not our concern; let other handlers run

        if (message.text or "").strip() == "🔙 بازگشت":
            state_store.clear(tg_id)
            await message.reply(
                "🔙 گزارش لغو شد.",
                reply_markup=main_keyboard(),
            )
            return

        data = state_store.data(tg_id)
        reason = (message.text or "").strip()[:1000]
        created = reports.create(
            reporter_id=tg_id,
            reported_user_id=data.get("reported_user_id"),
            chat_session_id=data.get("chat_session_id"),
            reason=reason,
        )
        state_store.clear(tg_id)
        if not created:
            await message.reply(
                "⏳ لطفاً چند ثانیه صبر کنید و دوباره تلاش کنید (محدودیت نرخ).",
                reply_markup=main_keyboard(),
            )
            return
        await message.reply(
            "✅ گزارش شما ثبت شد.\n"
            "تیم ما در اسرع وقت آن را بررسی خواهد کرد.",
            reply_markup=main_keyboard(),
        )

    # ---------------------------------------------------------------- #
    # MESSAGE RELAY  (group=8: runs after control callbacks, but
    # the FSM/cancel handlers above run earlier via lower groups)
    # ---------------------------------------------------------------- #
    @app.on_message(
        (filters.text | filters.media | filters.sticker) & filters.private,
        group=8,
    )
    async def relay_message(client: Client, message: Message):
        tg_id = message.from_user.id if message.from_user else None
        if not tg_id:
            return
        # if user is in any FSM flow that should consume the message, bail out
        st = state_store.state(tg_id)
        if st != States.IDLE:
            return  # let the FSM handler take it
        # rate-limit
        if not message_limiter.hit(tg_id, config.MSG_PER_MIN_LIMIT, 60):
            try:
                await message.reply(
                    "⏳ پیام‌های زیادی ارسال کردید. کمی صبر کنید."
                )
            except Exception:
                pass
            return
        # relay
        delivered = await chats.relay(client, message)
        if delivered:
            return
        # if not delivered and user is not searching, just ignore silently —
        # they were not in a chat. We don't want to "swallow" the message as
        # a feature, but we also don't want to spam "no active chat" notices.

    # ---------------------------------------------------------------- #
    # helper: kick off a fresh search after Next
    # ---------------------------------------------------------------- #
    async def _start_new_search(app, user_id: int, message: Message):
        # pull stored filters
        with db._cursor() as (_, cur):
            cur.execute(
                "SELECT * FROM search_filters WHERE user_id = %s",
                (user_id,),
            )
            f = cur.fetchone()
        if not f:
            f = {"gender_pref": "any", "location_pref": "any", "premium": False}
        try:
            matchmaking.start_search(
                user_id,
                gender_pref=f["gender_pref"] or "any",
                location_pref=f["location_pref"] or "any",
                premium=bool(f.get("premium") or users.is_premium(user_id)),
            )
        except RuntimeError:
            await message.reply("⚠️ شما از قبل در صف جستجو هستید.")
            return
        await message.reply(
            "🔎 در حال جستجوی فرد جدید..."
        )
        asyncio.create_task(_wait(app, user_id, message))

    async def _wait(app, user_id: int, message: Message):
        try:
            session = await matchmaking.wait_for_match(
                user_id, timeout_s=config.MAX_SEARCH_QUEUE_SECONDS
            )
        except Exception:
            session = None
        if not session:
            matchmaking.cancel_search(user_id)
            try:
                await message.reply(
                    "⚠️ کاربری یافت نشد. بعداً دوباره تلاش کنید.",
                    reply_markup=search_again_inline(),
                )
            except Exception:
                pass
            return
        a, b = session["user_a"], session["user_b"]
        text = (
            "🎉 **فردی پیدا شد!**\n\n"
            "گفتگوی ناشناس شما آغاز شد."
        )
        for uid in (a, b):
            try:
                await app.send_message(
                    uid, text, reply_markup=chat_controls_inline()
                )
            except Exception as exc:
                logger.warning("notify match user=%s failed: %s", uid, exc)
