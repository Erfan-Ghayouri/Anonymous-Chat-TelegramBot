"""
Admin handler.

Preserves the EXISTING sponsor-channel add/delete commands from the original
project (/addchannel, /deletechannel) and adds new admin tools:

  /admin                       — main admin panel (inline buttons)
  /stats                       — quick stats
  /broadcast <text>           — broadcast message to all users (sent in chunks)
  /adjust <user_id> <amount>   — adjust a user's coin balance
  /userinfo <user_id>          — show user info (admin view)
  /ban <user_id>               — set user status to 'banned'
  /unban <user_id>             — set user status to 'active'

The single legacy ADMIN_ID env var still works because we fall back to it in
config.ADMIN_IDS.
"""
from __future__ import annotations

import asyncio
import logging

import config
from pyrogram import Client, filters
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database.db import Database
from services.chat import ChatService
from services.reports import ReportService
from services.users import UserService
from services.wallet import WalletService
from utils.keyboards import admin_back_inline, admin_main_inline
from utils.states import States, state_store
from utils.persian import fmt_balance, fmt_user_id

logger = logging.getLogger(__name__)

ADMIN_FILTER = filters.user(config.ADMIN_IDS) if config.ADMIN_IDS else filters.user([])


def register_admin_handlers(
    app: Client,
    db: Database,
    users: UserService = None,
    wallet: WalletService = None,
    chats: ChatService = None,
    reports: ReportService = None,
):
    users = users or UserService(db)
    wallet = wallet or WalletService(db)
    chats = chats or ChatService(db, __import__("services.blocks", fromlist=["BlockService"]).BlockService(db))
    reports = reports or ReportService(db)

    # =========================================================
    # EXISTING — ADD CHANNEL  (preserved from original admin.py)
    # =========================================================
    @app.on_message(
        filters.command("addchannel") & ADMIN_FILTER
    )
    async def add_channel(client: Client, message: Message):
        if len(message.command) < 3:
            await message.reply(
                "❌ فرمت صحیح:\n\n/addchannel CHANNEL_ID INVITE_LINK"
            )
            return
        try:
            channel_id = int(message.command[1])
        except ValueError:
            await message.reply("❌ Channel ID باید عددی باشد.")
            return
        invite_link = message.command[2]
        try:
            chat = await client.get_chat(channel_id)
            channel_name = chat.title or "بدون نام"
            added = db.add_sponsor_channel(
                channel_id=channel_id, invite_link=invite_link
            )
            if added:
                await message.reply(
                    f"✅ کانال اضافه شد.\n\n"
                    f"📢 نام: {channel_name}\n"
                    f"🆔 ID: `{channel_id}`"
                )
            else:
                await message.reply("⚠️ این کانال قبلاً در لیست اسپانسرها وجود دارد.")
        except Exception as e:
            print("ADD CHANNEL ERROR:", repr(e))
            try:
                db.conn.rollback()
            except Exception:
                pass
            await message.reply("❌ هنگام اضافه کردن کانال خطایی رخ داد.")

    # =========================================================
    # EXISTING — DELETE CHANNEL (LIST)
    # =========================================================
    @app.on_message(
        filters.command("deletechannel") & ADMIN_FILTER
    )
    async def delete_channel_list(client: Client, message: Message):
        try:
            channels = db.get_sponsor_channels()
            if not channels:
                await message.reply("📭 هیچ کانال اسپانسری ثبت نشده.")
                return
            text = "📢 کانال‌های اسپانسر:\n\n"
            for index, channel in enumerate(channels, start=1):
                channel_id = channel["channel_id"]
                try:
                    chat = await client.get_chat(channel_id)
                    channel_name = (
                        chat.title or chat.username or str(channel_id)
                    )
                except Exception:
                    channel_name = str(channel_id)
                text += (
                    f"{index}. {channel_name}\n"
                    f"   🆔 `{channel_id}`\n\n"
                )
            text += (
                "برای حذف، شماره کانال را ارسال کنید.\n"
                "مثلاً:\n`2`"
            )
            await message.reply(text)
        except Exception as e:
            print("DELETE CHANNEL LIST ERROR:", repr(e))
            try:
                db.conn.rollback()
            except Exception:
                pass
            await message.reply("❌ خطا در دریافت لیست کانال‌ها.")

    # =========================================================
    # EXISTING — DELETE CHANNEL (SELECT NUMBER)
    # Note: filter is tightened to ONLY match digit text from admins so it
    # no longer swallows broadcast messages or any other admin input.
    # =========================================================
    @app.on_message(
        filters.regex(r"^\d+$")
        & filters.text
        & ADMIN_FILTER
        & ~filters.command(
            [
                "start",
                "help",
                "addchannel",
                "deletechannel",
                "stats",
                "broadcast",
                "adjust",
                "userinfo",
                "ban",
                "unban",
                "admin",
            ]
        )
        & filters.private,
        group=2,
    )
    async def delete_channel_selection(
        client: Client,
        message: Message
    ):
        # skip if admin is in any FSM state (e.g. broadcast mode)
        if state_store.state(message.from_user.id) != "idle":
            return  # let other handlers try
        try:
            number = int(message.text.strip())
            channels = db.get_sponsor_channels()
            if not channels:
                await message.reply("📭 هیچ کانال اسپانسری وجود ندارد.")
                return
            if number < 1 or number > len(channels):
                await message.reply(
                    f"❌ شماره باید بین 1 تا {len(channels)} باشد."
                )
                return
            selected_channel = channels[number - 1]
            channel_id = selected_channel["channel_id"]
            try:
                chat = await client.get_chat(channel_id)
                channel_name = (
                    chat.title or chat.username or str(channel_id)
                )
            except Exception:
                channel_name = str(channel_id)
            deleted = db.remove_sponsor_channel(channel_id)
            if deleted:
                await message.reply(
                    f"✅ کانال حذف شد.\n\n"
                    f"📢 {channel_name}\n"
                    f"🆔 `{channel_id}`"
                )
            else:
                await message.reply("❌ کانال پیدا نشد.")
        except Exception as e:
            print("DELETE CHANNEL ERROR:", repr(e))
            try:
                db.conn.rollback()
            except Exception:
                pass
            await message.reply("❌ هنگام حذف کانال خطایی رخ داد.")

    # =========================================================
    # NEW — /admin panel
    # =========================================================
    @app.on_message(
        filters.command("admin") & ADMIN_FILTER & filters.private
    )
    async def admin_panel(client: Client, message: Message):
        await message.reply(
            "🛠 **پنل مدیریت**\n\n"
            "از منوی زیر انتخاب کنید:",
            reply_markup=admin_main_inline(),
        )

    # =========================================================
    # NEW — /stats quick stats
    # =========================================================
    @app.on_message(
        filters.command("stats") & ADMIN_FILTER
    )
    async def stats_cmd(client: Client, message: Message):
        text = _build_stats_text(db, chats)
        await message.reply(text)

    # =========================================================
    # NEW — /broadcast <text>
    # =========================================================
    @app.on_message(
        filters.command("broadcast") & ADMIN_FILTER
    )
    async def broadcast_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply("❌ فرمت: `/broadcast متن پیام`")
            return
        # get full text after the command
        full_text = message.text or message.caption or ""
        parts = full_text.split(maxsplit=1)
        if len(parts) < 2:
            await message.reply("❌ متن پیام خالی است.")
            return
        payload = parts[1]
        await message.reply("📨 شروع ارسال همگانی...")
        asyncio.create_task(_broadcast(app, db, message.from_user.id, payload))

    # =========================================================
    # NEW — /adjust <telegram_id> <amount>
    # =========================================================
    @app.on_message(
        filters.command("adjust") & ADMIN_FILTER
    )
    async def adjust_cmd(client: Client, message: Message):
        if len(message.command) < 3:
            await message.reply("❌ فرمت: `/adjust USER_ID AMOUNT`")
            return
        try:
            target_id = int(message.command[1])
            amount = int(message.command[2])
        except ValueError:
            await message.reply("❌ پارامترها باید عدد باشند.")
            return
        target = db.get_user(target_id)
        if not target:
            await message.reply("❌ کاربر یافت نشد.")
            return
        result = wallet.credit(
            target_id,
            amount,
            "admin_adjust",
            f"تنظیم ادمین — ادمین {message.from_user.id}",
        )
        await message.reply(
            f"✅ کیف پول کاربر `{fmt_user_id(target['internal_id'])}` تغییر کرد.\n"
            f"   تغییر: {amount:+,} 🪙\n"
            f"   موجودی جدید: {fmt_balance(result['balance'])}"
        )

    # =========================================================
    # NEW — /userinfo <telegram_id>
    # =========================================================
    @app.on_message(
        filters.command("userinfo") & ADMIN_FILTER
    )
    async def userinfo_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply("❌ فرمت: `/userinfo USER_ID`")
            return
        try:
            tid = int(message.command[1])
        except ValueError:
            await message.reply("❌ USER_ID باید عدد باشد.")
            return
        u = db.get_user(tid)
        if not u:
            await message.reply("❌ کاربر یافت نشد.")
            return
        from utils.persian import user_gender_label
        text = (
            f"👤 **اطلاعات کاربر**\n\n"
            f"🆔 داخلی: `{fmt_user_id(u['internal_id'])}`\n"
            f"🆔 تلگرام: `{u['user_id']}`\n"
            f"👤 نام: {u.get('name') or '—'}\n"
            f"⚧ جنسیت: {user_gender_label(u)}\n"
            f"📍 شهر: {u.get('city') or '—'}\n"
            f"🎂 سن: {u.get('age') or '—'}\n"
            f"📝 بیو: {u.get('bio') or '—'}\n"
            f"💰 موجودی: {fmt_balance(u.get('wallet_balance') or 0)}\n"
            f"📊 وضعیت: {u.get('status') or '—'}\n"
            f"🔍 جستجو: {u.get('search_status') or '—'}\n"
            f"🎁 دعوت‌ها: {u.get('referral_count') or 0}\n"
        )
        await message.reply(text)

    # =========================================================
    # NEW — /ban & /unban
    # =========================================================
    @app.on_message(filters.command("ban") & ADMIN_FILTER)
    async def ban_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply("❌ فرمت: `/ban USER_ID`")
            return
        try:
            tid = int(message.command[1])
        except ValueError:
            await message.reply("❌ USER_ID باید عدد باشد.")
            return
        db.update_user_fields(tid, status="banned")
        # end any active session
        chats.end_session_for_user(tid)
        await message.reply(f"✅ کاربر `{tid}` مسدود شد.")

    @app.on_message(filters.command("unban") & ADMIN_FILTER)
    async def unban_cmd(client: Client, message: Message):
        if len(message.command) < 2:
            await message.reply("❌ فرمت: `/unban USER_ID`")
            return
        try:
            tid = int(message.command[1])
        except ValueError:
            await message.reply("❌ USER_ID باید عدد باشد.")
            return
        db.update_user_fields(tid, status="active")
        await message.reply(f"✅ کاربر `{tid}` رفع مسدودیت شد.")

    # =========================================================
    # NEW — admin inline keyboard routing
    # =========================================================
    @app.on_callback_query(filters.regex(r"^a:(?P<action>back|close)$") & ADMIN_FILTER)
    async def admin_back(client: Client, q: CallbackQuery):
        await q.answer()
        try:
            await q.message.delete()
        except Exception:
            pass
        await q.message.reply("🛠 پنل مدیریت", reply_markup=admin_main_inline())

    @app.on_callback_query(filters.regex(r"^a:(?P<action>stats)$") & ADMIN_FILTER)
    async def admin_stats(client: Client, q: CallbackQuery):
        await q.answer()
        text = _build_stats_text(db, chats)
        await q.message.reply(text, reply_markup=admin_back_inline())

    @app.on_callback_query(filters.regex(r"^a:(?P<action>broadcast)$") & ADMIN_FILTER)
    async def admin_broadcast_start(client: Client, q: CallbackQuery):
        await q.answer()
        state_store.set(q.from_user.id, States.ADMIN_BROADCAST)
        await q.message.reply(
            "📨 لطفاً متن پیام همگانی را ارسال کنید (متن، عکس، ویدیو و ...):\n"
            "برای لغو «بازگشت» را بزنید.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("🔙 بازگشت", callback_data="a:close")]]
            ),
        )

    @app.on_message(group=4)
    async def admin_broadcast_capture(client: Client, message: Message):
        if not (message.from_user and message.from_user.id in config.ADMIN_IDS):
            return
        st = state_store.state(message.from_user.id)
        if st != States.ADMIN_BROADCAST:
            return
        state_store.clear(message.from_user.id)
        await message.reply("📨 شروع ارسال همگانی...")
        asyncio.create_task(_broadcast_message_object(app, db, message))

    @app.on_callback_query(filters.regex(r"^a:(?P<action>reports)$") & ADMIN_FILTER)
    async def admin_reports(client: Client, q: CallbackQuery):
        await q.answer()
        rows = reports.list_open(limit=20)
        if not rows:
            await q.message.reply("📭 گزارش باز وجود ندارد.")
            return
        text = "🚨 **گزارش‌های باز:**\n\n"
        for r in rows:
            text += (
                f"• #{r['id']} — گزارش‌دهنده `{r['reporter_id']}` "
                f"علیه `{r['reported_user_id']}`\n"
                f"  دلیل: {r['reason'] or '—'}\n\n"
            )
        await q.message.reply(text, reply_markup=admin_back_inline())

    @app.on_callback_query(filters.regex(r"^a:(?P<action>settings)$") & ADMIN_FILTER)
    async def admin_settings_menu(client: Client, q: CallbackQuery):
        await q.answer()
        text = (
            "⚙️ **تنظیمات قابل تغییر از دیتابیس**\n\n"
            f"• قیمت جستجوی ویژه: {config.PREMIUM_SEARCH_PRICE} 🪙\n"
            f"• پاداش دعوت: {config.REFERRAL_REWARD} 🪙\n"
            f"• پاداش عضویت: {config.NEW_USER_BONUS} 🪙\n\n"
            "برای تغییر مقادیر، فایل `.env` را ویرایش کنید.\n"
            "(تنها برخی مقادیر قابل ذخیره‌سازی در دیتابیس هستند.)"
        )
        await q.message.reply(text, reply_markup=admin_back_inline())


def _build_stats_text(db: Database, chats: ChatService) -> str:
    total_users = db.count_users()
    active_users = db.count_active_users(24)
    active_chats = chats.active_count()
    total_chats = chats.total_count()
    with db._cursor() as (_, cur):
        cur.execute("SELECT COUNT(*) AS n FROM reports WHERE status='open'")
        open_reports = int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM blocked_users")
        blocks = int(cur.fetchone()["n"])
        cur.execute("SELECT COUNT(*) AS n FROM search_queue")
        in_queue = int(cur.fetchone()["n"])
    return (
        "📊 **آمار ربات**\n\n"
        f"👥 کل کاربران: {total_users:,}\n"
        f"🟢 فعال (۲۴ ساعت): {active_users:,}\n"
        f"🔍 در صف جستجو: {in_queue:,}\n"
        f"💬 گفتگوهای فعال: {active_chats:,}\n"
        f"💬 کل گفتگوها: {total_chats:,}\n"
        f"🚫 مسدودی‌ها: {blocks:,}\n"
        f"🚨 گزارش‌های باز: {open_reports:,}"
    )


async def _broadcast(app: Client, db: Database, admin_id: int, text: str):
    """Broadcast a plain-text message to all users in chunks."""
    sent = 0
    failed = 0
    offset = 0
    batch_size = 200
    while True:
        with db._cursor() as (_, cur):
            cur.execute(
                "SELECT user_id FROM users ORDER BY user_id LIMIT %s OFFSET %s",
                (batch_size, offset),
            )
            rows = cur.fetchall()
        if not rows:
            break
        for r in rows:
            uid = r["user_id"]
            try:
                await app.send_message(uid, text)
                sent += 1
            except Exception as exc:
                logger.info("broadcast send to %s failed: %s", uid, exc)
                failed += 1
            await asyncio.sleep(0.05)  # avoid flood
        offset += batch_size
    try:
        await app.send_message(
            admin_id,
            f"✅ پایان ارسال همگانی\nموفق: {sent}\nناموفق: {failed}",
        )
    except Exception:
        pass


async def _broadcast_message_object(app: Client, db: Database, message: Message):
    """Forward the admin's actual message object (preserves media) to all users."""
    sent = 0
    failed = 0
    offset = 0
    batch_size = 200
    while True:
        with db._cursor() as (_, cur):
            cur.execute(
                "SELECT user_id FROM users ORDER BY user_id LIMIT %s OFFSET %s",
                (batch_size, offset),
            )
            rows = cur.fetchall()
        if not rows:
            break
        for r in rows:
            uid = r["user_id"]
            try:
                await app.copy_message(
                    chat_id=uid,
                    from_chat_id=message.chat.id,
                    message_id=message.id,
                )
                sent += 1
            except Exception as exc:
                logger.info("broadcast copy to %s failed: %s", uid, exc)
                failed += 1
            await asyncio.sleep(0.05)
        offset += batch_size
    try:
        await app.send_message(
            message.from_user.id,
            f"✅ پایان ارسال همگانی\nموفق: {sent}\nناموفق: {failed}",
        )
    except Exception:
        pass
