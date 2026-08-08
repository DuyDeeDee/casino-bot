import asyncio
import logging
import discord
from discord.ext import commands

logger = logging.getLogger(__name__)


class Jail(commands.Cog):
    """Hệ thống Phạt tù, Mute và Cải tạo lau dọn"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.add_check(self.global_jail_command_check)

    async def cog_unload(self) -> None:
        self.bot.remove_check(self.global_jail_command_check)

    async def global_jail_command_check(self, ctx: commands.Context) -> bool:
        """Global check: Chặn tù nhân sử dụng các lệnh bot khác ngoài lau dọn."""
        if ctx.author.bot:
            return True

        # Cho phép các lệnh quản lý tù / lau dọn
        allowed_commands = {
            "lacdit", "laudon", "cleanjail", "caizao",
            "phattu", "jail", "tonggiam",
            "anxatu", "amxatu", "unjail", "thabong",
            "setkenhtu", "setjailchannel",
            "setvaitrotu", "setjailrole",
            "danhsachtu", "jailist",
        }
        
        if ctx.command and ctx.command.name in allowed_commands:
            return True

        # Nếu người dùng đang ở trong tù -> Chặn lệnh
        guild_id = ctx.guild.id if ctx.guild else 0
        if getattr(self.bot, "economy", None) and self.bot.economy.is_in_jail(ctx.author.id, guild_id):
            jail_channel_id = self.bot.economy.get_jail_channel(guild_id)
            channel_str = f"<#{jail_channel_id}>" if jail_channel_id else "Kênh Nhà Tù"
            p = ctx.prefix
            if isinstance(p, list):
                p = p[0]
            await ctx.send(
                f"❌ **{ctx.author.mention} bạn đang ở trong tù!**\n"
                f"Bạn không thể sử dụng các lệnh bot khác. Hãy đến {channel_str} và gõ `{p}lacdit` để cải tạo."
            )
            return False

        return True

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        """Tự động xoá tin nhắn của tù nhân ở các kênh ngoài kênh Nhà Tù."""
        if message.author.bot or not message.guild:
            return

        if not getattr(self.bot, "economy", None):
            return

        if self.bot.economy.is_in_jail(message.author.id, message.guild.id):
            jail_channel_id = self.bot.economy.get_jail_channel(message.guild.id)
            # Nếu đã cài đặt kênh Nhà Tù và nhắn sai kênh -> Xóa tin nhắn & cảnh báo
            if jail_channel_id and message.channel.id != jail_channel_id:
                try:
                    await message.delete()
                except Exception:
                    pass

                p = self.bot.command_prefix
                if isinstance(p, list):
                    p = p[0]

                try:
                    warning = await message.channel.send(
                        f"🚨 {message.author.mention} **Bạn đang ở trong tù và bị MUTE ở kênh này!**\n"
                        f"Hãy di chuyển đến kênh <#{jail_channel_id}> để gõ `{p}lacdit` cải tạo."
                    )
                    await asyncio.sleep(5)
                    await warning.delete()
                except Exception:
                    pass

    @commands.command(
        name="setkenhtu",
        aliases=["setjailchannel"],
        brief="Cài đặt Kênh Nhà Tù cho server.",
        usage="setkenhtu <#kênh>",
    )
    @commands.has_permissions(administrator=True)
    async def setkenhtu(self, ctx: commands.Context, channel: discord.TextChannel) -> None:
        """Cài đặt Kênh Nhà Tù cho server."""
        self.bot.economy.set_jail_channel(ctx.guild.id, channel.id)
        
        # Nếu đã có role tù nhân, cố gắng tự động cấu hình quyền gửi tin nhắn cho kênh
        role_id = self.bot.economy.get_jail_role(ctx.guild.id)
        if role_id:
            role = ctx.guild.get_role(role_id)
            if role:
                try:
                    await channel.set_permissions(role, send_messages=True, read_messages=True)
                except Exception as e:
                    logger.warning(f"Could not update channel permissions for jail role: {e}")

        await ctx.send(f"✅ **Thành công!** Đã thiết lập Kênh Nhà Tù tại: {channel.mention}")

    @commands.command(
        name="setvaitrotu",
        aliases=["setjailrole"],
        brief="Cài đặt Role Tù Nhân cho server (dùng để Mute tù nhân).",
        usage="setvaitrotu <@Role>",
    )
    @commands.has_permissions(administrator=True)
    async def setvaitrotu(self, ctx: commands.Context, role: discord.Role) -> None:
        """Cài đặt Role Tù Nhân cho server (dùng để Mute tù nhân)."""
        self.bot.economy.set_jail_role(ctx.guild.id, role.id)
        await ctx.send(f"✅ **Thành công!** Đã thiết lập Role Tù Nhân tại: {role.mention}")

    @commands.command(
        name="phattu",
        aliases=["jail", "tonggiam"],
        brief="Tống giam người chơi với số lần lau dọn/lắc đít chỉ định.",
        usage="phattu <@user> [số_lần] [lý_do]",
    )
    @commands.has_permissions(manage_messages=True)
    async def phattu(
        self,
        ctx: commands.Context,
        target: discord.Member,
        count: int = 100,
        *,
        reason: str = "Không có lý do",
    ) -> None:
        """Tống giam người chơi với số lần lau dọn chỉ định."""
        if target.bot:
            await ctx.send("❌ Không thể tống giam bot!")
            return

        if count <= 0:
            await ctx.send("❌ Số lần lau dọn phải lớn hơn 0!")
            return

        # Lưu vào Database
        self.bot.economy.add_to_jail(
            user_id=target.id,
            guild_id=ctx.guild.id,
            jailer_id=ctx.author.id,
            clean_count=count,
            reason=reason,
        )

        # Gán Role Tù Nhân (nếu có)
        role_id = self.bot.economy.get_jail_role(ctx.guild.id)
        jail_role = ctx.guild.get_role(role_id) if role_id else None
        if not jail_role:
            # Tìm role có tên "Tù Nhân" hoặc "Tu Nhan" nếu chưa cấu hình
            jail_role = discord.utils.get(ctx.guild.roles, name="Tù Nhân") or discord.utils.get(ctx.guild.roles, name="Tu Nhan")

        if jail_role:
            try:
                await target.add_roles(jail_role, reason=f"Phạt tù bởi {ctx.author}: {reason}")
            except Exception as e:
                logger.warning(f"Could not add jail role to {target}: {e}")

        prefix = ctx.prefix
        if isinstance(prefix, list):
            prefix = prefix[0]

        # Tin nhắn phản hồi kết quả tống giam tại kênh thực hiện lệnh
        sentence_text = (
            f"✅ **PHÁN QUYẾT THÀNH CÔNG!** Đã tống giam __{target.name}__.\n"
            f"> 🧹 **Hình phạt:** `{count}` lần lau dọn.\n"
            f"> 📄 **Lý do:** {reason}"
        )

        await ctx.send(sentence_text)

        # Thông báo TÙ NHÂN MỚI gửi vào kênh bị phạt tù (Jail Channel)
        jail_notice = (
            f"🚨 **TÙ NHÂN MỚI** 🚨\n"
            f"{target.mention} vừa bị chuyển vào đây!\n"
            f"> 🧹 **Hình phạt:** `{count}` lần lau dọn.\n"
            f"> 📄 **Lý do:** {reason}\n\n"
            f"💡 *Cải tạo tốt để sớm được khoan hồng bằng lệnh:* `{prefix}lacdit`"
        )

        jail_channel_id = self.bot.economy.get_jail_channel(ctx.guild.id)
        if jail_channel_id:
            jail_channel = ctx.guild.get_channel(jail_channel_id)
            if jail_channel:
                try:
                    await jail_channel.send(jail_notice)
                except Exception as e:
                    logger.warning(f"Could not send jail notice: {e}")
        else:
            # Nếu server chưa cài kênh tù riêng, gửi kèm thông báo tù nhân mới ở kênh hiện tại
            await ctx.send(jail_notice)

    @commands.command(
        name="lacdit",
        aliases=["laudon", "cleanjail", "caizao"],
        brief="Lắc đít cải tạo để giảm án phạt tù.",
        usage="lacdit",
    )
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def lacdit(self, ctx: commands.Context) -> None:
        """Lắc đít cải tạo để giảm án tù."""
        guild_id = ctx.guild.id if ctx.guild else 0
        jail_info = self.bot.economy.get_jail_info(ctx.author.id, guild_id)
        if not jail_info:
            await ctx.send("❌ Bạn không ở trong tù!")
            return

        # Kiểm tra nếu đã cài kênh nhà tù mà gõ sai kênh
        jail_channel_id = self.bot.economy.get_jail_channel(guild_id)
        if jail_channel_id and ctx.channel.id != jail_channel_id:
            await ctx.send(f"❌ Bạn chỉ có thể lắc đít cải tạo trong kênh <#{jail_channel_id}>!")
            return

        # Giảm số lần lau dọn / lắc đít
        remaining = self.bot.economy.update_jail_clean_count(ctx.author.id, guild_id, 1)

        if remaining <= 0:
            # Gỡ Role Tù Nhân nếu có
            role_id = self.bot.economy.get_jail_role(guild_id)
            jail_role = ctx.guild.get_role(role_id) if role_id else None
            if not jail_role:
                jail_role = discord.utils.get(ctx.guild.roles, name="Tù Nhân") or discord.utils.get(ctx.guild.roles, name="Tu Nhan")
            
            if jail_role and jail_role in ctx.author.roles:
                try:
                    await ctx.author.remove_roles(jail_role, reason="Hoàn thành phạt tù")
                except Exception as e:
                    logger.warning(f"Could not remove jail role: {e}")

            await ctx.send(
                f"🎉 **MÃ HẠN TÙ!** {ctx.author.mention} đã hoàn thành tất cả `{jail_info['total_clean_count']}` lần lắc đít và chính thức được **XUẤT TÙ**!"
            )
        else:
            await ctx.send(
                f"<a:lacdit1:1535528561685823498> {ctx.author.mention} vừa lắc đít 1 lượt! Còn lại **{remaining}/{jail_info['total_clean_count']}** lần."
            )

    @commands.command(
        name="anxatu",
        aliases=["amxatu", "unjail", "thabong"],
        brief="Tha bổng / Ân xá cho tù nhân trước thời hạn.",
        usage="anxatu <@user>",
    )
    @commands.has_permissions(manage_messages=True)
    async def anxatu(self, ctx: commands.Context, target: discord.Member) -> None:
        """Tha bổng / Ân xá cho tù nhân trước thời hạn."""
        guild_id = ctx.guild.id if ctx.guild else 0
        if not self.bot.economy.is_in_jail(target.id, guild_id):
            await ctx.send(f"❌ {target.mention} hiện không ở trong tù!")
            return

        self.bot.economy.remove_from_jail(target.id, guild_id)

        # Gỡ Role Tù Nhân
        role_id = self.bot.economy.get_jail_role(ctx.guild.id)
        jail_role = ctx.guild.get_role(role_id) if role_id else None
        if not jail_role:
            jail_role = discord.utils.get(ctx.guild.roles, name="Tù Nhân") or discord.utils.get(ctx.guild.roles, name="Tu Nhan")

        if jail_role and jail_role in target.roles:
            try:
                await target.remove_roles(jail_role, reason=f"Ân xá bởi {ctx.author}")
            except Exception as e:
                logger.warning(f"Could not remove jail role: {e}")

        await ctx.send(f"🔓 **Ân xá thành công!** {target.mention} đã được tha bổng và giải phóng trước thời hạn.")

    @commands.command(
        name="danhsachtu",
        aliases=["jailist", "tunan"],
        brief="Xem danh sách các tù nhân đang thụ án.",
        usage="danhsachtu",
    )
    async def danhsachtu(self, ctx: commands.Context) -> None:
        """Xem danh sách các tù nhân đang thụ án."""
        prisoners = self.bot.economy.get_all_prisoners(ctx.guild.id)
        if not prisoners:
            await ctx.send("🕊️ Hiện tại không có tù nhân nào trong Server!")
            return

        lines = ["🏛️ **DANH SÁCH TÙ NHÂN ĐANG THỤ ÁN** 🏛️"]
        for idx, p in enumerate(prisoners, start=1):
            user = ctx.guild.get_member(p["user_id"])
            user_str = user.mention if user else f"User ID `{p['user_id']}`"
            lines.append(
                f"{idx}. {user_str} - Còn lại: `{p['clean_count']}/{p['total_clean_count']}` lần | Lý do: {p['reason']}"
            )

        await ctx.send("\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Jail(bot))
