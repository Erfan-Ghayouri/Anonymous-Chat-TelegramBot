"""
Bot entry point.

Wires all handlers together with the shared database, services, and sponsor
gate.
"""
from __future__ import annotations

import asyncio
import logging
import signal

import pyrogram as kurigram

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    BOT_USERNAME,
    DATABASE_URL,
)

from database.db import Database
from services.blocks import BlockService
from services.chat import ChatService
from services.matchmaking import MatchmakingService
from services.referral import ReferralService
from services.reports import ReportService
from services.sponsors import SponsorService
from services.users import UserService
from services.wallet import WalletService

from handlers.admin import register_admin_handlers
from handlers.chat import register_chat_handlers
from handlers.help import register_help_handler
from handlers.profile import register_profile_handlers
from handlers.referral import register_referral_handlers
from handlers.search import register_search_handlers
from handlers.settings import register_settings_handlers
from handlers.start import register_start_handler
from handlers.wallet import register_wallet_handlers

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


def build_app():
    if not BOT_TOKEN:
        raise RuntimeError("BOT_TOKEN is not configured in .env")
    if not API_ID or not API_HASH:
        raise RuntimeError("API_ID / API_HASH are not configured in .env")
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured in .env")

    db = Database(DATABASE_URL)
    db.create_tables()

    app = kurigram.Client(
        "ChatoChiBot",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
    )

    # --- services (singletons; shared across handlers) ---
    sponsor_service = SponsorService(db, BOT_USERNAME)
    users = UserService(db)
    wallet = WalletService(db)
    blocks = BlockService(db)
    chats = ChatService(db, blocks)
    matchmaking = MatchmakingService(db)
    referrals = ReferralService(db, wallet, users)
    reports = ReportService(db)

    # --- handlers ---
    register_start_handler(
        app, db, sponsor_service, users=users, referrals=referrals, wallet=wallet
    )
    register_help_handler(app, db, sponsor_service)
    register_profile_handlers(app, db, sponsor_service, users)
    register_search_handlers(
        app, db, sponsor_service, users, wallet, matchmaking, chats
    )
    register_chat_handlers(
        app, db, sponsor_service, users, chats, matchmaking, reports
    )
    register_wallet_handlers(app, db, sponsor_service, wallet)
    register_referral_handlers(
        app, db, sponsor_service, users, wallet, referrals
    )
    register_settings_handlers(app, db, sponsor_service, users, blocks)
    register_admin_handlers(
        app, db, users=users, wallet=wallet, chats=chats, reports=reports
    )

    return app, matchmaking, db


async def main_async() -> None:
    app, matchmaking, db = build_app()

    stop_event = asyncio.Event()

    def _set_stop(*_):
        stop_event.set()

    # Pyrogram 2 / kurigram accept loop kwarg
    try:
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            try:
                loop.add_signal_handler(sig, _set_stop)
            except (NotImplementedError, RuntimeError):
                pass
    except Exception:
        pass

    try:
        await app.start()
        logger.info("Bot started")
        await matchmaking.start_poller()
        logger.info("Matchmaking poller started")

        await stop_event.wait()
    finally:
        try:
            await matchmaking.stop_poller()
        except Exception:
            pass
        try:
            await app.stop()
        except Exception:
            pass
        try:
            db.close()
        except Exception:
            pass


def main() -> None:
    try:
        asyncio.run(main_async())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
