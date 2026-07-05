import logging

import discord
from discord.ext import commands

# Force all embeds in the bot to use purple color
_original_embed_init = discord.Embed.__init__

def _custom_embed_init(self, *args, **kwargs):
    kwargs['color'] = discord.Color.purple()
    _original_embed_init(self, *args, **kwargs)
    self._colour = discord.Color.purple()

@property
def _forced_color(self):
    return discord.Color.purple()

@_forced_color.setter
def _forced_color(self, val):
    self._colour = discord.Color.purple()

discord.Embed.__init__ = _custom_embed_init
discord.Embed.color = _forced_color
discord.Embed.colour = _forced_color

from app.config import config
from app.discord_bot.cogs import (
    Blackjack,
    GamblingHelpers,
    Handlers,
    Help,
    MultiBlackjack,
    Slots,
    AIHelper,
    Simulator,
    GamblingGames,
    Daga,
    Xe,
    Roulette,
    CoinFlip,
    HorseRace,
    Crash,
    ScratchCard,
    Bkb,
    Baito,
    Lixi,
    Mines,
    Plinko,
    HighLow,
    Marry,
    Uno,
    Tower,
)

from app.discord_bot.modules.economy import Economy

logger = logging.getLogger(__name__)

COGS = (
    Blackjack,
    GamblingHelpers,
    Handlers,
    Help,
    Slots,
    MultiBlackjack,
    AIHelper,
    Simulator,
    GamblingGames,
    Daga,
    Xe,
    Roulette,
    CoinFlip,
    HorseRace,
    Crash,
    ScratchCard,
    Bkb,
    Baito,
    Lixi,
    Mines,
    Plinko,
    HighLow,
    Marry,
    Uno,
    Tower,
)




def build_intents() -> discord.Intents:
    intents = discord.Intents.default()
    intents.guilds = True
    intents.messages = True
    intents.message_content = True
    intents.members = True
    return intents


class CasinoBot(commands.Bot):
    def __init__(self) -> None:
        p = config.bot.prefix
        prefixes = [p.lower(), p.upper()] if p.lower() != p.upper() else [p]
        super().__init__(
            command_prefix=prefixes,
            owner_ids=set(config.bot.owner_ids),
            intents=build_intents(),
        )
        self.remove_command("help")
        self._cogs_loaded = False
        self.economy = Economy()

    async def setup_hook(self) -> None:
        await register_cogs(self)

    async def close(self) -> None:
        try:
            self.economy.close()
        finally:
            await super().close()


client = CasinoBot()


async def register_cogs(bot: commands.Bot | None = None) -> None:
    bot = bot or client
    if isinstance(bot, CasinoBot) and bot._cogs_loaded:
        return

    for cog in COGS:
        if bot.get_cog(cog.__name__):
            continue
        await bot.add_cog(cog(bot))
        logger.info("Loaded cog: %s", cog.__name__)

    if isinstance(bot, CasinoBot):
        bot._cogs_loaded = True