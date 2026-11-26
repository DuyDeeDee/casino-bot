"""Original Ilis Farm emoji and media from the legacy bot's asset catalog."""

import asyncio
import json
import logging
from pathlib import Path
from random import choice

import aiohttp
import discord

with Path(__file__).with_name("art.json").open(encoding="utf-8") as source:
    ART = json.load(source)

COLOR = 0xCC0022
FOOTER = "🥀 Ilis Farm"
PET_RARITY = {
    "common": ("Thường", 0x444444),
    "uncommon": ("Không phổ biến", 0x2A7A40),
    "rare": ("Hiếm", 0x1565C0),
    "epic": ("Sử thi", 0x6A1B9A),
    "legendary": ("Huyền thoại", 0xB84C00),
    "mythic": ("Thần thoại", COLOR),
}
logger = logging.getLogger(__name__)


class FarmEmojis:
    def __init__(self, bot):
        self.bot = bot
        self.originals = {
            key: discord.PartialEmoji.from_str(value) for key, value in ART["custom_emoji"].items()
        }
        self.application = {}
        self._lock = asyncio.Lock()

    def emoji(self, ctx, key: str, fallback: str = "") -> str:
        key = key.lower()
        owned = self.application.get(key)
        if owned:
            return owned
        ref = self.originals.get(key)
        if ref:
            cached = self.bot.get_emoji(ref.id)
            if cached and cached.is_usable():
                if ctx.guild is None or cached.guild_id == ctx.guild.id:
                    return str(cached)
                if ctx.channel.permissions_for(ctx.me).external_emojis:
                    return str(cached)
        return ART["fallback_emoji"].get(key, fallback)

    async def sync(self) -> None:
        async with self._lock:
            if len(self.application) == len(self.originals):
                return
            try:
                existing = await self.bot.fetch_application_emojis()
            except (discord.HTTPException, discord.MissingApplicationID) as error:
                logger.warning("Could not list Ilis Farm application emojis (%s)", type(error).__name__)
                return
            by_id = {emoji.id: emoji for emoji in existing}
            by_name = {emoji.name: emoji for emoji in existing}
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=8)) as session:
                for key, ref in self.originals.items():
                    name = f"ilis_{key}_{str(ref.id)[-6:]}"
                    owned = by_id.get(ref.id) or by_name.get(name)
                    if not owned:
                        try:
                            async with session.get(ref.url, params={"size": 128}) as response:
                                response.raise_for_status()
                                data = await response.read()
                            owned = await self.bot.create_application_emoji(name=name, image=data)
                        except (aiohttp.ClientError, asyncio.TimeoutError, discord.HTTPException, ValueError) as error:
                            logger.warning(
                                "Could not copy Ilis Farm emoji %s (%s, status=%s)",
                                key, type(error).__name__, getattr(error, "status", None),
                            )
                            continue
                    self.application[key] = str(owned)
            logger.info("Ilis Farm application emojis available: %d/%d", len(self.application), len(self.originals))


def image(key: str) -> str | None:
    return ART["images"].get(key.lower())


def thumbnail(key: str) -> str | None:
    key = key.lower()
    if key in ART["images"]:
        return ART["images"][key]
    custom = ART["custom_emoji"].get(key)
    return discord.PartialEmoji.from_str(custom).url if custom else None


def action_image(activity: str) -> str | None:
    images = ART["actions"].get(activity)
    return choice(images) if images else None
