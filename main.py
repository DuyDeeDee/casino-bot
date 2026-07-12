#!/usr/bin/env python3
"""Discord Casino Bot - Discord Only Mode"""

import asyncio
import logging

from app.common import setup_logging
from app.config import config
from app.discord_bot.bot import client

logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Discord bot with auto-reconnect on failure."""
    setup_logging()

    if not config.bot.token:
        raise ValueError(
            "DISCORD_TOKEN is not set. Please set it in your .env file or environment variables."
        )

    while True:
        try:
            logger.info("Starting Casino Bot (Discord Only Mode)...")
            async with client:
                await client.start(config.bot.token, reconnect=True)
        except (KeyboardInterrupt, asyncio.CancelledError):
            logger.info("Bot shutting down (signal received).")
            break
        except Exception as e:
            logger.error("Bot crashed with unexpected error: %s — restarting in 5s...", e, exc_info=True)
            await asyncio.sleep(5)
        else:
            if client.is_closed():
                logger.info("Bot stopped cleanly (client is closed). Exiting.")
                break
            else:
                logger.warning("client.start() finished unexpectedly (client is not closed). Reconnecting in 5s...")
                await asyncio.sleep(5)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
