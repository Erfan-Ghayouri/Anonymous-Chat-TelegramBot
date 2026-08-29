from database.db import Database

from pyrogram.types import Message
from pyrogram import filters, Client

from services.sponsors import SponsorService, sponsor_required


def register_start_handler(
    app: Client,
    db: Database,
    sponsor_service: SponsorService
):

    @app.on_message(filters.command("start"))
    @sponsor_required(sponsor_service)
    async def start(client: Client, message: Message):

        user_id = message.from_user.id

        db.add_user(user_id)

        await message.reply("Hi!")