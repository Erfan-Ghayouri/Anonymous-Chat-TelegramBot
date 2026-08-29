"""
/start handler with referral processing and welcome screen.

Existing sponsor-channel gate is preserved via @sponsor_required.
"""
from __future__ import annotations

import logging
from functools import wraps

from pyrogram import Client, filters
from pyrogram.types import Message

from database.db import Database
from services.sponsors import SponsorService, sponsor_required
from services.users import UserService
from services.referral import ReferralService
from services.wallet import WalletService
from utils.keyboards import main_keyboard
from utils.persian import fmt_user_id, fmt_balance
import config

logger = logging.getLogger(__name__)


def register_start_handler(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
    users: UserService = None,
    referrals: ReferralService = None,
    wallet: WalletService = None,
):
    if users is None:
        users = UserService(db)
    if wallet is None:
        wallet = WalletService(db)
    if referrals is None:
        referrals = ReferralService(db, wallet, users)

    @app.on_message(filters.command("start"))
    @sponsor_required(sponsor_service)
    async def start(client: Client, message: Message):
        tg_id = message.from_user.id
        payload = message.command[1] if len(message.command) > 1 else ""

        # /start=check is just a re-evaluation of sponsor membership
        if payload == "check":
            await message.reply(
                "✅ عضویت شما در کانال‌های اسپانسر بررسی شد.",
                reply_markup=main_keyboard(),
            )
            return

        # ensure user exists (idempotent + bonus-aware)
        users.ensure_user(tg_id)

        # process referral if present
        referrer_id = referrals.parse_referral_payload(payload)
        if referrer_id and referrer_id != tg_id:
            try:
                referrals.process_referral(referrer_id, tg_id)
            except Exception as exc:
                logger.warning("referral processing failed: %s", exc)

        user = users.get_profile(tg_id)
        internal_id = fmt_user_id(user.get("internal_id") if user else None)
        coins = wallet.balance(tg_id)

        text = (
            "🌟 **به گفتگوی ناشناس خوش آمدید!**\n\n"
            "بدون فاش کردن هویتتان با افراد جدید آشنا شوید.\n\n"
            "✨ گفتگوی کاملاً ناشناس\n"
            "🔎 جستجوی تصادفی و فیلتردار\n"
            "👤 پروفایل شخصی\n"
            "💬 مچ‌سازی سریع\n"
            "🎁 سکه‌های رایگان از طریق دعوت دوستان\n\n"
            f"🆔 شناسه شما: `{internal_id}`\n"
            f"💰 موجودی فعلی: {fmt_balance(coins)}\n\n"
            "برای شروع، از منوی زیر استفاده کنید 👇"
        )
        await message.reply(text, reply_markup=main_keyboard())
