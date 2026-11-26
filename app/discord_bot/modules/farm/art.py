"""Original Ilis Farm emoji and media from the legacy bot's asset catalog."""

import json
from pathlib import Path
from random import choice

import discord

with Path(__file__).with_name("art.json").open(encoding="utf-8") as source:
    ART = json.load(source)

COLOR = 0xCC0022
FOOTER = "🥀 Ilis Farm"


def emoji(ctx, key: str, fallback: str = "") -> str:
    key = key.lower()
    custom = ART["custom_emoji"].get(key)
    if custom:
        ref = discord.PartialEmoji.from_str(custom)
        cached = ctx.bot.get_emoji(ref.id)
        if cached and cached.is_usable():
            if ctx.guild is None or cached.guild_id == ctx.guild.id:
                return custom
            if ctx.channel.permissions_for(ctx.me).external_emojis:
                return custom
    return ART["fallback_emoji"].get(key, fallback)


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
