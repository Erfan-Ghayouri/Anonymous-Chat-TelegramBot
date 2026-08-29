"""Wallet handler — balance + transaction history."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, Message

from database.db import Database
from services.sponsors import SponsorService, sponsor_required
from services.wallet import WalletService
from utils.keyboards import MAIN_KB_LABELS, main_keyboard, wallet_inline
from utils.persian import fmt_balance, fmt_relative

logger = logging.getLogger(__name__)

TXN_TYPE_LABELS = {
    "signup_bonus":    "🎁 پاداش عضویت",
    "referral_reward": "🎁 پاداش دعوت",
    "premium_search":  "⭐ جستجوی ویژه",
    "feature_usage":   "🔧 استفاده از امکانات",
    "bonus":           "🎁 پاداش",
    "admin_adjust":    "⚙️ تنظیم ادمین",
    "coin_purchase":   "💰 خرید سکه",
}


def register_wallet_handlers(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
    wallet: WalletService,
):
    @app.on_message(
        filters.text(MAIN_KB_LABELS["wallet"]) & filters.private
    )
    @sponsor_required(sponsor_service)
    async def show_wallet(client: Client, message: Message):
        await _render_wallet(message)

    @app.on_callback_query(filters.regex(r"^w:(?P<action>back)$"))
    async def wallet_back(client: Client, q: CallbackQuery):
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await q.message.reply("🏠 منوی اصلی", reply_markup=main_keyboard())

    @app.on_callback_query(filters.regex(r"^w:(?P<action>tx)$"))
    async def wallet_tx(client: Client, q: CallbackQuery):
        await q.answer()
        rows = wallet.transactions(q.from_user.id, limit=20)
        if not rows:
            await q.message.reply("📭 شما هنوز تراکنشی نداشته‌اید.")
            return
        text = "📜 **تراکنش‌های اخیر شما:**\n\n"
        for r in rows:
            amount = int(r["amount"])
            sign = "+" if amount >= 0 else ""
            label = TXN_TYPE_LABELS.get(r["type"], r["type"])
            desc = r["description"] or "—"
            when = fmt_relative(r["created_at"])
            text += (
                f"{sign}{amount:,} 🪙  — {label}\n"
                f"   {desc}\n"
                f"   {when}\n\n"
            )
        await q.message.reply(text)

    async def _render_wallet(message: Message):
        bal = wallet.balance(message.from_user.id)
        text = (
            "💰 **کیف پول شما**\n\n"
            f"موجودی فعلی: {fmt_balance(bal)}\n\n"
            "💡 راه‌های افزایش موجودی:\n"
            "• دعوت دوستان\n"
            "• پاداش‌های مدیریتی\n"
        )
        await message.reply(text, reply_markup=wallet_inline())
