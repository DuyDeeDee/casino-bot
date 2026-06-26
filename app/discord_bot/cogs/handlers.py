import logging
import ssl

import aiohttp
import discord
from discord.ext import commands
from discord.ext.commands.errors import (
    BadArgument,
    BotMissingPermissions,
    CommandInvokeError,
    CommandNotFound,
    CommandOnCooldown,
    MaxConcurrencyReached,
    MemberNotFound,
    MissingPermissions,
    MissingRequiredArgument,
    TooManyArguments,
    UserNotFound,
)

from app.config import config
from app.discord_bot.modules.helpers import (
    InsufficientCreditsException,
    InsufficientFundsException,
    make_embed,
)
from app.discord_bot.modules.economy import Economy

logger = logging.getLogger(__name__)


class Handlers(commands.Cog, name="handlers"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self._ready_once = False
        self.economy = getattr(client, "economy", None) or Economy()
        client.before_invoke(self.before_command_hook)

    async def before_command_hook(self, ctx: commands.Context):
        if not self.economy or (ctx.author and ctx.author.bot):
            return
            
        user_id = ctx.author.id
        
        # Nếu chưa nhận quà khởi nghiệp và lệnh không phải là khoinghiep hoặc help
        if not self.economy.has_claimed_start(user_id):
            if ctx.command and ctx.command.name in ["khoinghiep", "help"]:
                return
                
            prefix = self.client.command_prefix
            if isinstance(prefix, list):
                prefix = prefix[0]
            embed = make_embed(
                title="👋 CHÀO MỪNG THÀNH VIÊN MỚI! 👋",
                description=(
                    f"Chào mừng **{ctx.author.name}** lần đầu tiên sử dụng Casino Bot! 🏙️🎰\n\n"
                    f"Vì bạn là người mới và chưa khởi nghiệp, ví của bạn hiện đang trống rỗng.\n"
                    f"Hãy sử dụng lệnh khởi nghiệp dưới đây để nhận **1,000,000 VND** làm vốn ban đầu:\n\n"
                    f"👉 👉 **`{prefix}khoinghiep`** (hoặc `{prefix}batdau`) 👈 👈\n\n"
                    f"Sau khi nhận tiền, bạn có thể tham gia các trò chơi hoặc làm việc kiếm thêm tiền bằng lệnh `{prefix}work`.\n"
                    f"Gõ `{prefix}help` để xem toàn bộ danh sách lệnh."
                ),
                color=discord.Color.gold(),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            try:
                await ctx.send(embed=embed)
            except Exception:
                pass
            raise commands.CheckFailure("Chưa khởi nghiệp")

    @commands.Cog.listener()
    async def on_ready(self):
        if self._ready_once:
            return
        self._ready_once = True
        logger.info("%s is ready", self.client.user)
        try:
            await self.client.change_presence(
                activity=discord.Game(f"blackjack | {config.bot.prefix}help")
            )
        except discord.HTTPException:
            pass

    @commands.Cog.listener()
    async def on_command_error(self, ctx: commands.Context, error):
        if hasattr(ctx.command, "on_error"):
            return

        if isinstance(error, commands.CheckFailure) and str(error) == "Chưa khởi nghiệp":
            return

        if isinstance(error, CommandInvokeError):
            await self.on_command_error(ctx, error.original)
            return

        if isinstance(error, CommandNotFound):
            return

        if isinstance(error, (MissingRequiredArgument, TooManyArguments, BadArgument)):
            command_name = ctx.command.name if ctx.command else ""
            prefix = self.client.command_prefix
            if isinstance(prefix, list):
                prefix = prefix[0]
            await ctx.send(f"❌ **Sử dụng sai cú pháp!** Gõ `{prefix}help {command_name}` để xem hướng dẫn.")
            return

        if isinstance(error, (UserNotFound, MemberNotFound)):
            await ctx.send(f"Không tìm thấy thành viên `{error.argument}`.")
            return

        if isinstance(error, MissingPermissions):
            await ctx.send(
                "Bạn phải có các quyền sau: "
                + ", ".join(f"`{perm}`" for perm in error.missing_perms)
            )
            return

        if isinstance(error, BotMissingPermissions):
            await ctx.send(
                "Bot phải có các quyền sau: "
                + ", ".join(f"`{perm}`" for perm in error.missing_perms)
            )
            return

        if isinstance(error, InsufficientFundsException):
            await ctx.send(str(error))
            await ctx.invoke(self.client.get_command("money"))
            return

        if isinstance(error, InsufficientCreditsException):
            await ctx.send(str(error))
            await ctx.invoke(self.client.get_command("money"))
            return

        if isinstance(error, CommandOnCooldown):
            seconds = int(error.retry_after)
            seconds = seconds % (24 * 3600)
            hours = seconds // 3600
            seconds %= 3600
            minutes = seconds // 60
            seconds %= 60
            await ctx.send(f"Thời gian chờ còn lại: {hours} giờ {minutes} phút {seconds} giây.")
            return

        if isinstance(error, MaxConcurrencyReached):
            await ctx.send("Lệnh này đang được thực hiện cho bạn rồi.")
            return

        if isinstance(error, (aiohttp.ClientError, ssl.SSLError, TimeoutError, ConnectionResetError)):
            logger.warning(
                "Transient network error while handling command=%s",
                ctx.command.qualified_name if ctx.command else None,
                exc_info=error,
            )
            return

        if isinstance(error, discord.HTTPException) and (error.status >= 500 or error.status == 0):
            logger.warning(
                "Discord API transient HTTP error while handling command=%s status=%s",
                ctx.command.qualified_name if ctx.command else None,
                error.status,
                exc_info=error,
            )
            return

        raise error


async def setup(client: commands.Bot):
    await client.add_cog(Handlers(client))
