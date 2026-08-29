import os
from config import ADMIN_ID
from pyrogram import Client, filters
from pyrogram.types import Message


def register_admin_handlers(app: Client, db):

    # =========================================================
    # ADD CHANNEL
    # =========================================================

    @app.on_message(
        filters.command("addchannel") & filters.user(ADMIN_ID)
    )
    async def add_channel(client: Client, message: Message):

        if len(message.command) < 3:
            await message.reply(
                "❌ فرمت صحیح:\n\n"
                "/addchannel CHANNEL_ID INVITE_LINK"
            )
            return

        try:
            channel_id = int(message.command[1])
        except ValueError:
            await message.reply("❌ Channel ID باید عددی باشد.")
            return

        invite_link = message.command[2]

        try:
            # گرفتن اطلاعات کانال از تلگرام
            chat = await client.get_chat(channel_id)

            # اسم کانال
            channel_name = chat.title or "بدون نام"

            # اضافه کردن به دیتابیس
            added = db.add_sponsor_channel(
                channel_id=channel_id,
                invite_link=invite_link
            )

            if added:
                await message.reply(
                    f"✅ کانال اضافه شد.\n\n"
                    f"📢 نام: {channel_name}\n"
                    f"🆔 ID: `{channel_id}`"
                )
            else:
                await message.reply(
                    "⚠️ این کانال قبلاً در لیست اسپانسرها وجود دارد."
                )

        except Exception as e:

            print("ADD CHANNEL ERROR:", repr(e))

            # خیلی مهم
            try:
                db.conn.rollback()
            except Exception:
                pass

            await message.reply(
                "❌ هنگام اضافه کردن کانال خطایی رخ داد."
            )


    # =========================================================
    # DELETE CHANNEL - SHOW LIST
    # =========================================================

    @app.on_message(
        filters.command("deletechannel") & filters.user(ADMIN_ID)
    )
    async def delete_channel(client: Client, message: Message):

        try:

            channels = db.get_sponsor_channels()

            if not channels:
                await message.reply(
                    "📭 هیچ کانال اسپانسری ثبت نشده."
                )
                return

            text = "📢 کانال‌های اسپانسر:\n\n"

            for index, channel in enumerate(channels, start=1):

                channel_id = channel["channel_id"]
                invite_link = channel["invite_link"]

                try:
                    chat = await client.get_chat(channel_id)

                    channel_name = (
                        chat.title
                        or chat.username
                        or str(channel_id)
                    )

                except Exception as e:

                    print(
                        f"GET CHAT ERROR ({channel_id}):",
                        repr(e)
                    )

                    channel_name = str(channel_id)

                text += (
                    f"{index}. {channel_name}\n"
                    f"   🆔 `{channel_id}`\n\n"
                )

            text += (
                "برای حذف، شماره کانال را ارسال کنید.\n"
                "مثلاً:\n"
                "`2`"
            )

            await message.reply(text)

        except Exception as e:

            print("DELETE CHANNEL LIST ERROR:", repr(e))

            try:
                db.conn.rollback()
            except Exception:
                pass

            await message.reply(
                "❌ خطا در دریافت لیست کانال‌ها."
            )


    # =========================================================
    # DELETE CHANNEL - SELECT NUMBER
    # =========================================================

    @app.on_message(
        filters.text
        & filters.user(ADMIN_ID)
        & ~filters.command(
            [
                "start",
                "addchannel",
                "deletechannel"
            ]
        )
    )
    async def delete_channel_selection(
        client: Client,
        message: Message
    ):

        # فقط عدد قبول کن
        if not message.text.strip().isdigit():
            return

        try:

            number = int(message.text.strip())

            channels = db.get_sponsor_channels()

            if not channels:
                await message.reply(
                    "📭 هیچ کانال اسپانسری وجود ندارد."
                )
                return

            # بررسی محدوده
            if number < 1 or number > len(channels):

                await message.reply(
                    f"❌ شماره باید بین 1 تا {len(channels)} باشد."
                )
                return

            # شماره 1 یعنی index صفر
            selected_channel = channels[number - 1]

            channel_id = selected_channel["channel_id"]

            try:
                chat = await client.get_chat(channel_id)

                channel_name = (
                    chat.title
                    or chat.username
                    or str(channel_id)
                )

            except Exception:

                channel_name = str(channel_id)

            # حذف
            deleted = db.remove_sponsor_channel(channel_id)

            if deleted:

                await message.reply(
                    f"✅ کانال حذف شد.\n\n"
                    f"📢 {channel_name}\n"
                    f"🆔 `{channel_id}`"
                )

            else:

                await message.reply(
                    "❌ کانال پیدا نشد."
                )

        except Exception as e:

            print(
                "DELETE CHANNEL ERROR:",
                repr(e)
            )

            try:
                db.conn.rollback()
            except Exception:
                pass

            await message.reply(
                "❌ هنگام حذف کانال خطایی رخ داد."
            )

