import pyrogram as kurigram

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    BOT_USERNAME,
    DATABASE_URL
)

from database.db import Database
from handlers.admin import register_admin_handlers
from handlers.start import register_start_handler
from services.sponsors import SponsorService, sponsor_required

db = Database(DATABASE_URL)
db.create_tables()


app = kurigram.Client(
    "ChatoChi Telegram Bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

sponsor_service = SponsorService(
    db,
    BOT_USERNAME
)

register_start_handler(
    app,
    db,
    sponsor_service
)

register_admin_handlers(
    app,
    db
)

app.run()