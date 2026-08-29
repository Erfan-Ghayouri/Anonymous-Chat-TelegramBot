from functools import wraps

from pyrogram import Client
from pyrogram.types import (
    Message,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)


class SponsorService:

    def __init__(self, database, bot_username):
        self.database = database
        self.bot_username = bot_username

    async def get_missing_channels(self, client, user_id):
        channels = self.database.get_sponsor_channels()

        missing_channels = []

        for channel in channels:
            channel_id = channel["channel_id"]

            try:
                member = await client.get_chat_member(
                    channel_id,
                    user_id
                )

                if member.status in ("left", "kicked"):
                    missing_channels.append(channel)

            except Exception:
                missing_channels.append(channel)

        return missing_channels

    def create_keyboard(self, missing_channels):
        buttons = []

        for channel in missing_channels:
            buttons.append([
                InlineKeyboardButton(
                    "📢 عضویت در کانال",
                    url=channel["invite_link"]
                )
            ])

        buttons.append([
            InlineKeyboardButton(
                "✅ بررسی عضویت",
                url=f"https://t.me/{self.bot_username}?start=check"
            )
        ])

        return InlineKeyboardMarkup(buttons)

    async def check_and_reply(self, client, message):
        user_id = message.from_user.id

        missing_channels = await self.get_missing_channels(
            client,
            user_id
        )

        if not missing_channels:
            return True

        keyboard = self.create_keyboard(missing_channels)

        await message.reply(
            "❌ برای استفاده از ربات ابتدا در کانال‌های اسپانسر عضو شوید.",
            reply_markup=keyboard
        )

        return False

    async def check_user(self, client, user_id):
        missing_channels = await self.get_missing_channels(
            client,
            user_id
        )

        return len(missing_channels) == 0


def sponsor_required(sponsor_service):

    def decorator(func):

        @wraps(func)
        async def wrapper(
            client: Client,
            message: Message,
            *args,
            **kwargs
        ):
            allowed = await sponsor_service.check_and_reply(
                client,
                message
            )

            if not allowed:
                return

            return await func(
                client,
                message,
                *args,
                **kwargs
            )

        return wrapper

    return decorator
