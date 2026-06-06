#!/usr/bin/env python3
"""Discord Casino Bot - Discord Only Mode"""

import asyncio
import logging

from app.common import setup_logging
from app.config import config
from app.discord_bot.bot import client

logger = logging.getLogger(__name__)


async def main() -> None:
    """Start the Discord bot."""
    setup_logging()
    
    if not config.bot.token:
        raise ValueError(
            "DISCORD_TOKEN is not set. Please set it in your .env file or environment variables."
        )
    
    logger.info("Starting Casino Bot (Discord Only Mode)...")
    async with client:
        await client.start(config.bot.token)


if __name__ == "__main__":
    asyncio.run(main())
