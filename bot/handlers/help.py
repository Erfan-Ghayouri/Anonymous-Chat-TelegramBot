"""
/help handler — Persian guide section.

Each topic is a separate inline button; clicking shows a relevant sub-section.
The full guide text is also sent when the user clicks 📖 راهنما from the main
reply keyboard.
"""
from __future__ import annotations

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import Database
from services.sponsors import SponsorService, sponsor_required
from utils.keyboards import help_inline, main_keyboard, MAIN_KB_LABELS

GUIDES = {
    "h:search": (
        "🔎 **جستجوی ناشناس**\n\n"
        "از منوی اصلی «جستجوی ناشناس» را انتخاب کنید.\n"
        "در صورت وجود افراد هم‌شناس در صف مچ‌سازی، بلافاصله به شما معرفی می‌شوند.\n\n"
        "• جنسیت و شهر مورد نظر خود را فیلتر کنید.\n"
        "• هنگام پیدا شدن، گفتگوی ناشناس شروع می‌شود.\n"
        "• هر پیام شما به‌صورت کاملاً ناشناس برای شخص مقابل ارسال می‌شود."
    ),
    "h:profile": (
        "👤 **پروفایل**\n\n"
        "در منوی اصلی «پروفایل من» را انتخاب کنید.\n"
        "می‌توانید نام، بیو، جنسیت، سن و شهر خود را تنظیم کنید.\n"
        "شناسه داخلی شما (#ID) هرگز شناسه تلگرامی شما را فاش نمی‌کند."
    ),
    "h:block": (
        "🚫 **مسدود کردن**\n\n"
        "در حین گفتگو، دکمه «مسدود» را بزنید.\n"
        "گفتگوی فعلی بلافاصله پایان می‌یابد و شخص مقابل دیگر هرگز به شما متصل نخواهد شد."
    ),
    "h:report": (
        "🚨 **گزارش تخلف**\n\n"
        "اگر کاربر مقابل رفتار نامناسبی داشت، دکمه «گزارش» را بزنید و دلیل را بنویسید.\n"
        "تیم ما گزارش‌ها را بررسی می‌کند و در صورت تایید، کاربر خاطی محروم می‌شود."
    ),
    "h:wallet": (
        "💰 **کیف پول**\n\n"
        "هر کاربر جدید به‌صورت خودکار سکه دریافت می‌کند.\n"
        "با دعوت دوستان پاداش بیشتر بگیرید.\n"
        "سکه‌ها برای فعال‌سازی «جستجوی ویژه» استفاده می‌شوند."
    ),
    "h:invite": (
        "🎁 **دعوت دوستان**\n\n"
        "لینک اختصاصی دعوت خود را با دوستان به اشتراک بگذارید.\n"
        "برای هر دوست که از طریق لینک شما عضو شود، پاداش سکه دریافت می‌کنید."
    ),
    "h:premium": (
        "⭐ **جستجوی ویژه**\n\n"
        "جستجوی ویژه اولویت بالاتری در مچ‌سازی دارد و فیلترهای بیشتری را فعال می‌کند.\n"
        "هزینهٔ فعال‌سازی قابل تنظیم است و از کیف پول شما کسر می‌شود."
    ),
    "h:chat": (
        "💬 **رفتار گفتگو**\n\n"
        "هر پیام (متن، عکس، ویس، استیکر، ویدیو و …) به‌صورت ناشناس به شخص مقابل ارسال می‌شود.\n"
        "هیچ دکمهٔ «پیام مستقیم» وجود ندارد؛ خودِ گفتگو، راه ارتباطی شماست.\n"
        "برای پایان گفتگو دکمهٔ «پایان گفتگو» را بزنید."
    ),
}


def register_help_handler(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
):
    @app.on_message(filters.command("help"))
    @sponsor_required(sponsor_service)
    async def help_cmd(client: Client, message: Message):
        await _send_help(message)

    @app.on_message(
        filters.text(MAIN_KB_LABELS["guide"])
        & filters.private
    )
    @sponsor_required(sponsor_service)
    async def help_kb(client: Client, message: Message):
        await _send_help(message)

    @app.on_callback_query(filters.regex("^h:(?P<topic>back)$"))
    async def help_back(client: Client, q: CallbackQuery):
        await q.answer()
        await q.message.edit_text(
            "📖 **راهنمای ربات**\n\n"
            "روی هر بخش کلیک کنید تا توضیحات بیشتر ببینید:",
            reply_markup=help_inline(),
        )

    @app.on_callback_query(filters.regex(r"^h:(?!back$)(?P<topic>[a-zA-Z_]+)$"))
    async def help_topic(client: Client, q: CallbackQuery):
        topic = q.matches[0]["topic"]
        text = GUIDES.get(f"h:{topic}")
        if not text:
            await q.answer("⚠️ بخش نامعتبر", show_alert=True)
            return
        await q.answer()
        back_kb = InlineKeyboardMarkup(
            [[InlineKeyboardButton("🔙 بازگشت", callback_data="h:back")]]
        )
        await q.message.edit_text(text, reply_markup=back_kb)


async def _send_help(message: Message):
    text = (
        "📖 **راهنمای ربات**\n\n"
        "برای توضیحات هر بخش، روی دکمهٔ مربوطه کلیک کنید:"
    )
    await message.reply(text, reply_markup=help_inline())
