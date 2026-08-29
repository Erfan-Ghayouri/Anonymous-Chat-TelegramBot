"""Settings handler."""
from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from database.db import Database
from services.blocks import BlockService
from services.sponsors import SponsorService, sponsor_required
from services.users import UserService
from utils.keyboards import MAIN_KB_LABELS, main_keyboard, settings_inline

logger = logging.getLogger(__name__)


def register_settings_handlers(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
    users: UserService,
    blocks: BlockService,
):
    @app.on_message(
        filters.text(MAIN_KB_LABELS["settings"]) & filters.private
    )
    @sponsor_required(sponsor_service)
    async def show_settings(client: Client, message: Message):
        is_prem = users.is_premium(message.from_user.id)
        await message.reply(
            "⚙️ **تنظیمات**\n\n"
            "حساب و تنظیمات خود را مدیریت کنید.",
            reply_markup=settings_inline(is_prem),
        )

    @app.on_callback_query(filters.regex(r"^st:(?P<action>noop|blocked|support|back)$"))
    async def settings_action(client: Client, q: CallbackQuery):
        action = q.matches[0]["action"]
        if action == "back":
            await q.answer()
            try:
                await q.message.delete()
            except Exception:
                pass
            await q.message.reply("🏠 منوی اصلی", reply_markup=main_keyboard())
            return
        if action == "noop":
            await q.answer("این امکان خودکار است")
            return
        if action == "support":
            await q.answer()
            await q.message.reply(
                "🆘 برای پشتیبانی با آیدی ادمین در تماس باشید:"
                f"\n@{__import__('config').BOT_USERNAME}"
            )
            return
        if action == "blocked":
            await q.answer()
            tg_id = q.from_user.id
            with db._cursor() as (_, cur):
                cur.execute(
                    """
                    SELECT u.user_id, u.internal_id, u.name
                    FROM blocked_users b
                    JOIN users u ON u.user_id = b.blocked_id
                    WHERE b.blocker_id = %s
                    ORDER BY b.created_at DESC
                    LIMIT 20
                    """,
                    (tg_id,),
                )
                rows = cur.fetchall()
            if not rows:
                await q.message.reply("📭 لیست مسدود شده‌های شما خالی است.")
                return
            text = "🚫 **کاربران مسدود شده توسط شما:**\n\n"
            from utils.persian import fmt_user_id
            for r in rows:
                text += f"• {r['name'] or '—'}  (`{fmt_user_id(r['internal_id'])}`)\n"
            await q.message.reply(text)
