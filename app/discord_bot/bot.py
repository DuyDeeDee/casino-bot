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


import time


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
        self.cooldown_tracker = {}
        self.add_check(self.global_cooldown_check)

    async def setup_hook(self) -> None:
        self.add_command(setcooldown)
        await register_cogs(self)

    async def close(self) -> None:
        try:
            self.economy.close()
        finally:
            await super().close()

    async def global_cooldown_check(self, ctx: commands.Context) -> bool:
        if await self.is_owner(ctx.author):
            return True
            
        cooldown_str = self.economy.get_setting("global_cooldown")
        if cooldown_str:
            try:
                cooldown_val = float(cooldown_str)
            except ValueError:
                cooldown_val = 2.0
        else:
            cooldown_val = 2.0

        if cooldown_val <= 0:
            return True

        now = time.time()
        user_id = ctx.author.id
        
        if user_id in self.cooldown_tracker:
            last_time = self.cooldown_tracker[user_id]
            retry_after = cooldown_val - (now - last_time)
            if retry_after > 0:
                cooldown_obj = commands.Cooldown(1, cooldown_val)
                raise commands.CommandOnCooldown(cooldown_obj, retry_after, commands.BucketType.user)
                
        self.cooldown_tracker[user_id] = now
        return True


@commands.command(
    brief="Cấu hình thời gian chờ (cooldown) toàn cục cho bot.",
    usage="setcooldown [số giây]",
    aliases=["setcd"],
    hidden=True
)
@commands.is_owner()
async def setcooldown(ctx: commands.Context, seconds_str: str):
    bot = ctx.bot
    try:
        seconds = float(seconds_str)
        if seconds < 0:
            await ctx.send("❌ Số giây cooldown không được âm.")
            return
    except ValueError:
        await ctx.send("❌ Vui lòng nhập số giây hợp lệ (số thực hoặc số nguyên).")
        return

    bot.economy.set_setting("global_cooldown", str(seconds))
    if seconds > 0:
        await ctx.send(f"✅ Đã thiết lập thời gian chờ (cooldown) toàn cục là `{seconds} giây`.")
    else:
        await ctx.send("✅ Đã tắt thời gian chờ (cooldown) toàn cục.")




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