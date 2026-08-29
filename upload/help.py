from database.db import Database

from pyrogram.types import Message
from pyrogram import filters, Client

from services.sponsors import SponsorService, sponsor_required


def help_register_handler(
    app: Client,
    db: Database,
    sponsor_service: SponsorService
):
    @app.on_message(filters.command("help"))
    @sponsor_required(sponsor_service)
    async def help(client: Client, message: Message):
        pass