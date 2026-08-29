"""Referral handler — show invite link + stats."""
from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, Message

from database.db import Database
from services.referral import ReferralService
from services.sponsors import SponsorService, sponsor_required
from services.users import UserService
from services.wallet import WalletService
from utils.keyboards import MAIN_KB_LABELS, invite_inline, main_keyboard
from utils.persian import fmt_balance
import config

logger = logging.getLogger(__name__)


def register_referral_handlers(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
    users: UserService,
    wallet: WalletService,
    referrals: ReferralService,
):
    @app.on_message(
        filters.text(MAIN_KB_LABELS["invite"]) & filters.private
    )
    @sponsor_required(sponsor_service)
    async def show_invite(client: Client, message: Message):
        await _render_invite(message)

    @app.on_callback_query(filters.regex(r"^i:(?P<action>back)$"))
    async def invite_back(client: Client, q: CallbackQuery):
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await q.message.reply("🏠 منوی اصلی", reply_markup=main_keyboard())

    async def _render_invite(message: Message):
        tg_id = message.from_user.id
        users.ensure_user(tg_id)
        link = referrals.build_referral_link(tg_id, config.BOT_USERNAME)
        stats = referrals.stats(tg_id)
        text = (
            "🎁 **دعوت دوستان**\n\n"
            "با دعوت دوستان خود، برای هر عضو موفق پاداش سکه دریافت کنید!\n\n"
            f"👥 دعوت‌های موفق: {stats['total']}\n"
            f"🪙 سکه‌های کسب‌شده: {stats['earned_coins']}\n\n"
            "🔗 لینک اختصاصی شما:"
        )
        await message.reply(
            f"{text}\n\n`{link}`\n\n"
            "آن را کپی یا ارسال کنید.",
            reply_markup=invite_inline(link),
        )
