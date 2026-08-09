import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class ChannelControl(commands.Cog, name="ChannelControl"):
    """Hệ thống Quản lý Kênh bị Cấm / Được Phép sử dụng Bot cho từng Server."""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot

    @commands.command(
        name="camkenh",
        aliases=["setcamkenh", "blockchannel"],
        brief="Bật / Tắt cấm dùng lệnh Bot tại kênh chỉ định.",
        usage="camkenh <#kênh>",
    )
    @commands.has_permissions(administrator=True)
    async def camkenh(self, ctx: commands.Context, channel: discord.TextChannel = None) -> None:
        """Cấm hoặc Gỡ cấm sử dụng Bot tại kênh chỉ định."""
        target_channel = channel or ctx.channel
        guild_id = ctx.guild.id

        is_blocked = self.bot.economy.toggle_blocked_channel(guild_id, target_channel.id)

        if is_blocked:
            await ctx.send(
                f"🚫 **Thành công!** Đã cấm sử dụng các lệnh Bot tại kênh {target_channel.mention}.\n"
                f"*(Các lệnh thuộc danh mục `Function` vẫn được phép sử dụng)*"
            )
        else:
            await ctx.send(
                f"✅ **Thành công!** Đã gỡ cấm. Kênh {target_channel.mention} hiện tại có thể sử dụng Bot bình thường."
            )

    @commands.command(
        name="gocamkenh",
        aliases=["unblockchannel"],
        brief="Gỡ cấm dùng lệnh Bot tại kênh chỉ định.",
        usage="gocamkenh <#kênh>",
    )
    @commands.has_permissions(administrator=True)
    async def gocamkenh(self, ctx: commands.Context, channel: discord.TextChannel = None) -> None:
        """Gỡ cấm sử dụng Bot tại kênh chỉ định."""
        target_channel = channel or ctx.channel
        guild_id = ctx.guild.id

        removed = self.bot.economy.remove_blocked_channel(guild_id, target_channel.id)
        if removed:
            await ctx.send(f"✅ **Thành công!** Đã gỡ cấm dùng Bot tại kênh {target_channel.mention}.")
        else:
            await ctx.send(f"ℹ️ Kênh {target_channel.mention} vốn không nằm trong danh sách cấm.")

    @commands.command(
        name="setkenhchoiduoc",
        aliases=["allowchannel", "setallowedchannel"],
        brief="Cài đặt/Thêm kênh được phép chơi (dùng để hướng dẫn người chơi).",
        usage="setkenhchoiduoc <#kênh>",
    )
    @commands.has_permissions(administrator=True)
    async def setkenhchoiduoc(self, ctx: commands.Context, channel: discord.TextChannel = None) -> None:
        """Thêm hoặc bớt kênh được phép dùng Bot."""
        target_channel = channel or ctx.channel
        guild_id = ctx.guild.id

        is_allowed = self.bot.economy.toggle_allowed_channel(guild_id, target_channel.id)
        if is_allowed:
            await ctx.send(f"✅ **Thành công!** Đã thêm {target_channel.mention} vào danh sách kênh được phép chơi.")
        else:
            await ctx.send(f"ℹ️ Đã xóa {target_channel.mention} khỏi danh sách kênh được phép chơi.")

    @commands.command(
        name="danhsachkenhcam",
        aliases=["listcamkenh", "blockedchannels"],
        brief="Xem danh sách các kênh bị cấm sử dụng Bot trong server.",
        usage="danhsachkenhcam",
    )
    async def danhsachkenhcam(self, ctx: commands.Context) -> None:
        """Xem danh sách các kênh đang bị cấm trong server."""
        guild_id = ctx.guild.id
        blocked_ids = self.bot.economy.get_blocked_channels(guild_id)

        if not blocked_ids:
            await ctx.send("🕊️ Server này hiện chưa cấm kênh nào!")
            return

        lines = ["🚫 **DANH SÁCH KÊNCH BỊ CẤM DÙNG BOT** 🚫"]
        for idx, cid in enumerate(blocked_ids, start=1):
            ch = ctx.guild.get_channel(cid)
            ch_str = ch.mention if ch else f"Kênh ID `{cid}` (Đã xóa)"
            lines.append(f"{idx}. {ch_str}")

        lines.append("\n*(Các lệnh thuộc danh mục `Function` vẫn có thể dùng tại các kênh này)*")
        await ctx.send("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(ChannelControl(bot))
