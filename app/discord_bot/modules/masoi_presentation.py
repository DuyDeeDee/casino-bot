"""Shared live presentation helpers; transient locks are never checkpointed."""
import asyncio
import math
import time
import discord


def ui_lock(game, name):
    attr = f"_{name}_ui_lock"
    lock = getattr(game, attr, None)
    if lock is None:
        lock = asyncio.Lock()
        setattr(game, attr, lock)
    return lock


def remaining_night_seconds(game):
    return max(0, math.ceil(game.night_deadline - time.monotonic()))


def select_badge(value, fallback="⚖️"):
    """Text badges stay in the embed; don't send arbitrary text as component emoji."""
    emoji = discord.PartialEmoji.from_str(value)
    if emoji.id is not None:
        return emoji
    # Conservative Unicode check: one symbol, optional tone/VS/keycap/ZWJ, or flag.
    def symbol(char):
        code = ord(char)
        return (0x1F000 <= code <= 0x1FAFF or 0x2600 <= code <= 0x27BF
                or 0x2300 <= code <= 0x23FF or 0x2B00 <= code <= 0x2BFF
                or 0x2190 <= code <= 0x21FF or 0x25A0 <= code <= 0x25FF
                or char in "©®™‼⁉〰〽㊗㊙")
    bases = [c for c in value if symbol(c) and not 0x1F3FB <= ord(c) <= 0x1F3FF]
    flag = len(bases) == 2 and all(0x1F1E6 <= ord(c) <= 0x1F1FF for c in bases)
    sequence = "\u200d" in value and all(symbol(c) or c in "\u200d\ufe0f\ufe0e" for c in value)
    keycap = len(value) in (2, 3) and value[0] in "0123456789#*" and value.endswith("\u20e3")
    single = len(bases) == 1 and all(symbol(c) or c in "\ufe0f\ufe0e" for c in value)
    if len(value) <= 32 and (single or flag or sequence or keycap):
        return emoji
    return discord.PartialEmoji.from_str(fallback)


def new_deaths(game, alive_before):
    """Include committed deaths AND subsequent hunter/lover continuations."""
    return tuple(uid for uid in sorted(alive_before) if not game.players[uid].is_alive)
