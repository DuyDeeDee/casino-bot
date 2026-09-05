import re
from datetime import datetime
from pathlib import Path

from discord import Color, Embed


EMOJI_VND = "<:VND:1545815183589511370>"
EMOJI_GOLD = "<:GOLD:1545815236035219637>"


class BetLimitViolationException(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)


class InsufficientFundsException(Exception):
    def __init__(self, current, bet) -> None:
        self.needs = bet - current
        super().__init__()

    def __str__(self) -> str:
        return f"Bạn cần thêm {self.needs:,} {EMOJI_VND} để chơi."


class InsufficientCreditsException(Exception):
    def __init__(self, current: int, required: int) -> None:
        self.needs = required - current
        super().__init__()

    def __str__(self) -> str:
        return f"Bạn cần thêm {self.needs:,} {EMOJI_GOLD}."


ABS_PATH = Path(__file__).resolve().parent.parent
COG_FOLDER = str(ABS_PATH / "cogs")


def make_embed(title=None, description=None, color=None, author=None,
               image=None, link=None, footer=None) -> Embed:
    """Wrapper for making discord embeds"""
    embed = Embed(
        title=title or None,
        description=description or None,
        url=link or None,
        color=color if color else Color.random()
    )
    if author:
        embed.set_author(name=author)
    if image:
        embed.set_image(url=image)
    if footer:
        embed.set_footer(text=footer)
    else:
        embed.set_footer(text=datetime.now().strftime("%m/%d/%Y %H:%M:%S"))
    return embed


_AMOUNT_RE = re.compile(r"^(\d[\d.,]*)([km]?)(\d*)$")


def parse_amount(text: str) -> int | None:
    """Parses money input: '500', '100k', '1.5m', '1.000.000', '1,000,000'.

    '.' and ',' act as thousands separators when no k/m suffix is present, and as
    decimal separators when a k/m suffix is present. Returns None if invalid.
    """
    if not text:
        return None
    cleaned = text.strip().lower().replace(" ", "").replace("_", "")
    match = _AMOUNT_RE.match(cleaned)
    if not match or match.group(3):  # trailing digits after a k/m suffix (e.g. "1m5") are invalid
        return None
    digits_part, suffix, _ = match.groups()
    multiplier = {"k": 1_000, "m": 1_000_000}.get(suffix, 1)
    try:
        if suffix:
            whole, _, frac = digits_part.replace(",", ".").partition(".")
            if not whole.isdigit() or (frac and not frac.isdigit()) or len(frac) > 6:
                return None
            value = int(whole + frac) * multiplier
            if frac:
                value //= 10 ** len(frac)
            return value
        return int(digits_part.replace(".", "").replace(",", ""))
    except ValueError:
        return None


def calc_gold(vnd: int) -> tuple[int, int, int, int]:
    """Top-up exchange rate: 1,000 VND = 1 Gold, plus 2% bonus Gold per full
    100,000 VND deposited (capped at 40%).

    Returns (base_gold, bonus_gold, bonus_pct, total_gold). The single source
    of truth for both the i?nap price display and i?addtopup crediting.
    """
    base_gold = (vnd // 1000) * 1
    bonus_tier = vnd // 100_000
    bonus_pct = min(40, bonus_tier * 2)
    bonus_gold = int(base_gold * (bonus_pct / 100))
    return base_gold, bonus_gold, bonus_pct, base_gold + bonus_gold
