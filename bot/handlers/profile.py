"""
Profile handler — view and edit the user's profile card.

Profile fields:
  - name, gender, city, age, bio (editable)
  - internal #ID, coin balance (read-only)

Helpers are defined INSIDE the register function so they can close over the
`users` service, avoiding the need for global app state.
"""
from __future__ import annotations

import logging

from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    Message,
)

from database.db import Database
from services.sponsors import SponsorService, sponsor_required
from services.users import UserService
from utils.keyboards import (
    MAIN_KB_LABELS,
    back_only_keyboard,
    gender_picker_inline,
    location_filter_inline,
    main_keyboard,
    profile_inline_keyboard,
)
from utils.persian import (
    fmt_balance,
    fmt_user_id,
    user_gender_label,
)
from utils.states import States, state_store
from utils.validation import (
    PERSIAN_CITIES,
    validate_age,
    validate_bio,
    validate_city,
    validate_name,
    normalize_city,
)

logger = logging.getLogger(__name__)


def register_profile_handlers(
    app: Client,
    db: Database,
    sponsor_service: SponsorService,
    users: UserService,
):
    def _profile_text(user) -> str:
        if not user:
            return "⚠️ پروفایل شما یافت نشد. لطفاً /start را بزنید."
        name = user.get("name") or "—"
        city = user.get("city") or "—"
        bio = user.get("bio") or "—"
        age = user.get("age") or "—"
        gender = user_gender_label(user)
        coins = int(user.get("wallet_balance") or 0)
        iid = fmt_user_id(user.get("internal_id"))
        return (
            "👤 **پروفایل من**\n\n"
            f"🆔 شناسه: `{iid}`\n"
            f"👤 نام: {name}\n"
            f"⚧ جنسیت: {gender}\n"
            f"🎂 سن: {age}\n"
            f"📍 شهر: {city}\n"
            f"📝 بیو: {bio}\n\n"
            f"💰 موجودی: {fmt_balance(coins)}"
        )

    async def _render_new(message: Message):
        user = users.get_profile(message.from_user.id)
        await message.reply(
            _profile_text(user),
            reply_markup=profile_inline_keyboard(),
        )

    async def _render_edit(message: Message):
        user = users.get_profile(message.from_user.id)
        await message.edit_text(
            _profile_text(user),
            reply_markup=profile_inline_keyboard(),
        )

    # ---------------------------------------------------------------- #
    # reply keyboard entry
    # ---------------------------------------------------------------- #
    @app.on_message(
        filters.text(MAIN_KB_LABELS["profile"]) & filters.private
    )
    @sponsor_required(sponsor_service)
    async def show_profile(client: Client, message: Message):
        await _render_new(message)

    # ---------------------------------------------------------------- #
    # inline keyboard: profile actions
    # ---------------------------------------------------------------- #
    @app.on_callback_query(filters.regex(r"^p:(?P<action>back)$"))
    async def profile_back(client: Client, q: CallbackQuery):
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await q.message.reply(
            "🏠 به منوی اصلی بازگشتید.",
            reply_markup=main_keyboard(),
        )

    @app.on_callback_query(filters.regex(r"^p:(?P<action>bio|gender|city|name|age)$"))
    async def profile_action(client: Client, q: CallbackQuery):
        action = q.matches[0]["action"]
        tg_id = q.from_user.id
        users.touch(tg_id)

        if action == "bio":
            await q.answer()
            state_store.set(tg_id, States.EDIT_BIO)
            await q.message.reply(
                "📝 بیوگرافی جدید خود را ارسال کنید (حداکثر ۵۰۰ کاراکتر):",
                reply_markup=back_only_keyboard(),
            )
        elif action == "name":
            await q.answer()
            state_store.set(tg_id, States.EDIT_NAME)
            await q.message.reply(
                "✏️ نام نمایشی جدید را ارسال کنید:",
                reply_markup=back_only_keyboard(),
            )
        elif action == "age":
            await q.answer()
            state_store.set(tg_id, States.EDIT_AGE)
            await q.message.reply(
                "🎂 سن خود را به عدد ارسال کنید (۱۳ تا ۱۲۰):",
                reply_markup=back_only_keyboard(),
            )
        elif action == "city":
            await q.answer()
            state_store.set(tg_id, States.EDIT_CITY)
            await q.message.reply(
                "📍 شهر خود را انتخاب کنید یا به‌صورت متنی ارسال کنید:",
                reply_markup=location_filter_inline(PERSIAN_CITIES[:20]),
            )
        elif action == "gender":
            await q.answer()
            await q.message.reply(
                "⚧ جنسیت خود را انتخاب کنید:",
                reply_markup=gender_picker_inline(callback_prefix="pg"),
            )

    # ---------------------------------------------------------------- #
    # gender picker (own profile) — `pg:`
    # ---------------------------------------------------------------- #
    @app.on_callback_query(filters.regex(r"^pg:(?P<value>male|female|back)$"))
    async def own_gender_pick(client: Client, q: CallbackQuery):
        value = q.matches[0]["value"]
        if value == "back":
            await q.answer()
            await _render_edit(q.message)
            return
        try:
            users.set_gender(q.from_user.id, value)
            await q.answer("✅ ذخیره شد")
        except Exception:
            await q.answer("❌ خطا", show_alert=True)
            return
        await _render_edit(q.message)

    # ---------------------------------------------------------------- #
    # city picker (own profile) — only triggers if user is in EDIT_CITY
    # ---------------------------------------------------------------- #
    @app.on_callback_query(filters.regex(r"^fl:(?P<city>[^:]+)$"))
    async def own_city_pick(client: Client, q: CallbackQuery):
        st = state_store.state(q.from_user.id)
        if st != States.EDIT_CITY:
            return  # let the search filter handler take it (it returns None
                    # to signal "we don't own this")
        city = q.matches[0]["city"]
        if city == "back":
            await q.answer()
            state_store.clear(q.from_user.id)
            await _render_edit(q.message)
            return
        users.set_city(q.from_user.id, city)
        state_store.clear(q.from_user.id)
        await q.answer("✅ ذخیره شد")
        await _render_edit(q.message)

    # ---------------------------------------------------------------- #
    # text inputs for FSM flows
    # NOTE: this handler must be registered with a LOWER priority than the
    # main-keyboard buttons handler and the chat relay, otherwise it would
    # swallow everything. We register this in a higher group number so other
    # handlers take precedence.
    # ---------------------------------------------------------------- #
    @app.on_message(
        filters.text & filters.private,
        group=10,
    )
    @sponsor_required(sponsor_service)
    async def profile_text_handler(client: Client, message: Message):
        tg_id = message.from_user.id
        st = state_store.state(tg_id)
        text = (message.text or "").strip()

        if st == States.IDLE:
            return  # nothing for us; let other handlers try

        # universal "back" while in any FSM state
        if text == "🔙 بازگشت":
            state_store.clear(tg_id)
            await message.reply(
                "🔙 از ویرایش خارج شدید.",
                reply_markup=main_keyboard(),
            )
            return

        if st == States.EDIT_NAME:
            if not validate_name(text):
                await message.reply(
                    "⚠️ نام نامعتبر است. فقط حروف فارسی/انگلیسی استفاده کنید."
                )
                return
            users.set_name(tg_id, text)
            state_store.clear(tg_id)
            await message.reply(
                "✅ نام شما با موفقیت به‌روزرسانی شد.",
                reply_markup=main_keyboard(),
            )
            return

        if st == States.EDIT_BIO:
            if not validate_bio(text):
                await message.reply("⚠️ بیو باید بین ۱ تا ۵۰۰ کاراکتر باشد.")
                return
            users.set_bio(tg_id, text)
            state_store.clear(tg_id)
            await message.reply(
                "✅ بیو با موفقیت به‌روزرسانی شد.",
                reply_markup=main_keyboard(),
            )
            return

        if st == States.EDIT_AGE:
            if not validate_age(text):
                await message.reply("⚠️ سن باید عددی بین ۱۳ تا ۱۲۰ باشد.")
                return
            users.set_age(tg_id, int(text))
            state_store.clear(tg_id)
            await message.reply(
                "✅ سن شما به‌روزرسانی شد.",
                reply_markup=main_keyboard(),
            )
            return

        if st == States.EDIT_CITY:
            if not validate_city(text):
                await message.reply("⚠️ شهر نامعتبر است.")
                return
            users.set_city(tg_id, normalize_city(text))
            state_store.clear(tg_id)
            await message.reply(
                "✅ شهر شما به‌روزرسانی شد.",
                reply_markup=main_keyboard(),
            )
            return
