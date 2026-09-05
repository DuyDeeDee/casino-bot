import asyncio
import logging
import typing
import discord
from discord.ext import commands
from app.config import config

logger = logging.getLogger(__name__)


def has_jail_permission():
    """Quyền dùng lệnh phạt tù / ân xá: Quản lý tin nhắn, Quản trị viên server, hoặc Admin/Owner bot."""
    async def predicate(ctx: commands.Context) -> bool:
        if not ctx.guild:
            return False

        owner_ids = set(getattr(config.bot, "owner_ids", []) or [])
        admin_ids = set(getattr(config.bot, "admin_ids", []) or [])
        if ctx.author.id in owner_ids or ctx.author.id in admin_ids:
            return True

        try:
            if await ctx.bot.is_owner(ctx.author):
                return True
        except Exception:
            pass

        perms = ctx.channel.permissions_for(ctx.author)
        if perms.administrator or perms.manage_messages:
            return True

        err = commands.MissingPermissions(["manage_messages"])
        err.missing_perms = ["manage_messages"]
        raise err

    predicate.perms = {"manage_messages": True}
    return commands.check(predicate)


class Jail(commands.Cog):
    """Hệ thống Phạt tù, Mute và Cải tạo lau dọn"""

    def __init__(self, bot: commands.Bot) -> None:
        self.bot = bot
        self.bot.add_check(self.global_jail_command_check)

    async def cog_unload(self) -> None:
        self.bot.remove_check(self.global_jail_command_check)

    async def _reply_or_send(self, ctx: commands.Context, content: str = None, **kwargs) -> discord.Message:
        """Gửi tin nhắn phản hồi dưới dạng reply đến lệnh của người dùng, fallback về send nếu lỗi."""
        try:
            return await ctx.reply(content, **kwargs)
        except (discord.HTTPException, discord.InvalidArgument):
            return await ctx.send(content, **kwargs)

    async def _is_admin_or_owner(self, ctx: commands.Context, user: discord.Member | discord.User = None) -> bool:
        """Kiểm tra xem user có phải là Bot Owner, Bot Admin hoặc Server Admin (Administrator/Owner server) hay không."""
        target_user = user or ctx.author
        if not target_user:
            return False

        # 1. Bot Owner
        owner_ids = set(getattr(config.bot, "owner_ids", []) or [])
        if target_user.id in owner_ids:
            return True
        if hasattr(self.bot, "owner_ids") and self.bot.owner_ids and target_user.id in self.bot.owner_ids:
            return True
        try:
            if await self.bot.is_owner(target_user):
                return True
        except Exception:
            pass

        # 2. Bot Admin
        admin_ids = set(getattr(config.bot, "admin_ids", []) or [])
        if target_user.id in admin_ids:
            return True

        # 3. Server Admin & Server Owner
        if ctx.guild:
            if target_user.id == ctx.guild.owner_id:
                return True
            member = target_user if isinstance(target_user, discord.Member) else ctx.guild.get_member(target_user.id)
            if member and getattr(member, "guild_permissions", None) and member.guild_permissions.administrator:
                return True

        return False

    async def _is_bot_owner(self, user: discord.Member | discord.User) -> bool:
        """Kiểm tra xem một user có phải là Bot Owner hay không."""
        if not user:
            return False
        owner_ids = set(getattr(config.bot, "owner_ids", []) or [])
        if user.id in owner_ids:
            return True
        if hasattr(self.bot, "owner_ids") and self.bot.owner_ids and user.id in self.bot.owner_ids:
            return True
        try:
            if await self.bot.is_owner(user):
                return True
        except Exception:
            pass
        return False

    async def _is_bot_admin(self, user: discord.Member | discord.User) -> bool:
        """Kiểm tra xem một user có phải là Bot Admin hay không."""
        if not user:
            return False
        admin_ids = set(getattr(config.bot, "admin_ids", []) or [])
        return user.id in admin_ids

    async def global_jail_command_check(self, ctx: commands.Context) -> bool:
        """Global check: Chặn tù nhân sử dụng các lệnh bot khác ngoài lau dọn."""
        if ctx.author.bot:
            return True

        # Cho phép các lệnh quản lý tù / lau dọn / quản lý kênh
        allowed_commands = {
            "lacdit", "laudon", "cleanjail", "caizao",
            "phattu", "jail", "tonggiam",
            "anxatu", "unjail", "thabong",
            "setkenhtu", "setjailchannel",
            "setvaitrotu", "setjailrole",
            "danhsachtu", "jailist",
            "camkenh", "setcamkenh", "blockchannel",
            "gocamkenh", "unblockchannel",
            "setkenhchoiduoc", "allowchannel", "setallowedchannel",
            "danhsachkenhcam", "listcamkenh", "blockedchannels",
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
    @commands.guild_only()
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

        await self._reply_or_send(ctx, f"✅ **Thành công!** Đã thiết lập Kênh Nhà Tù tại: {channel.mention}")

    @commands.command(
        name="setvaitrotu",
        aliases=["setjailrole"],
        brief="Cài đặt Role Tù Nhân cho server (dùng để Mute tù nhân).",
        usage="setvaitrotu <@Role>",
    )
    @commands.guild_only()
    @commands.has_permissions(administrator=True)
    async def setvaitrotu(self, ctx: commands.Context, role: discord.Role) -> None:
        """Cài đặt Role Tù Nhân cho server (dùng để Mute tù nhân)."""
        self.bot.economy.set_jail_role(ctx.guild.id, role.id)
        await self._reply_or_send(ctx, f"✅ **Thành công!** Đã thiết lập Role Tù Nhân tại: {role.mention}")

    @commands.command(
        name="phattu",
        aliases=["jail", "tonggiam"],
        brief="Tống giam người chơi với số lần lắc đít chỉ định.",
        usage="phattu <@user> [số_lần] [lý_do]",
    )
    @commands.guild_only()
    @has_jail_permission()
    async def phattu(
        self,
        ctx: commands.Context,
        target: discord.Member,
        count: typing.Optional[int] = 100,
        *,
        reason: str = "Không có lý do",
    ) -> None:
        """Tống giam người chơi với số lần lắc đít chỉ định."""
        if count is None or count <= 0:
            count = 100

        # Không thể phạt bot khác
        if target.bot:
            await self._reply_or_send(ctx, "❌ Không thể tống giam bot!")
            return

        is_caller_admin_or_owner = await self._is_admin_or_owner(ctx, ctx.author)
        is_caller_bot_owner = await self._is_bot_owner(ctx.author)
        is_target_bot_owner = await self._is_bot_owner(target)
        is_target_bot_admin = await self._is_bot_admin(target)

        # Bảo vệ Bot Owner & Bot Admin: Không ai được tống giam Bot Owner / Bot Admin (trừ khi chính Bot Owner thao tác)
        if (is_target_bot_owner or is_target_bot_admin) and not is_caller_bot_owner:
            await self._reply_or_send(
                ctx,
                f"<:zh_deo:1545378962992009217>",
            )
            return

        # Kiểm tra tự phạt chính mình (Admin/Owner bot có thể tự phạt để test tính năng)
        if not is_caller_admin_or_owner and target.id == ctx.author.id:
            await self._reply_or_send(ctx, "❌ **Lỗi phân quyền:** Bạn không thể tự phạt chính mình.")
            return

        # Nếu không phải Admin hoặc Owner bot: Phải tuân theo thứ bậc role
        if not is_caller_admin_or_owner:
            # Kiểm tra cấp bậc Bot (Người này có cấp bậc cao hơn hoặc bằng Bot, hoặc là Server Owner)
            if target.id == ctx.guild.owner_id or target.top_role >= ctx.guild.me.top_role:
                await self._reply_or_send(
                    ctx,
                    f"<:zh_deo:1545378962992009217>",
                )
                return

            # Kiểm tra cấp bậc người thực hiện lệnh (Người dùng có cấp bậc cao hơn hoặc bằng người thực hiện)
            if ctx.author.id != ctx.guild.owner_id and target.top_role >= ctx.author.top_role:
                await self._reply_or_send(
                    ctx,
                    f"<:zh_deo:1545378962992009217>",
                )
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
            if jail_role >= ctx.guild.me.top_role:
                logger.warning(f"Role tù nhân ({jail_role.name}) có cấp bậc cao hơn hoặc bằng Bot.")
            else:
                try:
                    await target.add_roles(jail_role, reason=f"Phạt tù bởi {ctx.author}: {reason}")
                except discord.Forbidden:
                    logger.warning(f"Bot thiếu quyền thêm role tù nhân cho {target}")
                except Exception as e:
                    logger.warning(f"Could not add jail role to {target}: {e}")

        prefix = ctx.prefix
        if isinstance(prefix, list):
            prefix = prefix[0]

        # Tin nhắn phản hồi kết quả tống giam tại kênh thực hiện lệnh
        sentence_text = (
            f"<a:tick:1536052984440553532> **Đã tống giam __{target.name}__ vào tầng hầm để lắc đít <a:nhay:1536053206868557985>**\n"
            f"> <a:lacdit3:1536053449341276200> **Hình phạt:** `{count}` lần lắc đít\n"
            f"> <a:blink:1526231036231680082> **Lý do:** {reason}"
        )

        sentence_text_fallback = (
            f"✅ **Đã tống giam __{target.name}__ vào tầng hầm để lắc đít 🐕**\n"
            f"> 🧹 **Hình phạt:** `{count}` lần lắc đít\n"
            f"> 📄 **Lý do:** {reason}"
        )

        try:
            await self._reply_or_send(ctx, sentence_text)
        except Exception as e:
            logger.warning(f"Could not send sentence_text with custom emojis: {e}")
            try:
                await self._reply_or_send(ctx, sentence_text_fallback)
            except Exception as e2:
                logger.error(f"Failed to send fallback sentence_text: {e2}")

        # Thông báo TÙ NHÂN MỚI gửi vào kênh bị phạt tù (Jail Channel)
        jail_notice = (
            f"<a:nhay:1536053206868557985> **TÙ NHÂN MỚI** <a:nhay:1536053206868557985>\n"
            f"{target.mention} vừa bị chuyển vào đây!\n"
            f"> <a:lacdit3:1536053449341276200> **Hình phạt:** `{count}` lần lắc đít\n"
            f"> <a:blink:1526231036231680082> **Lý do:** {reason}\n\n"
            f"💡 *Cải tạo tốt để sớm được khoan hồng bằng lệnh:* `{prefix}lacdit`"
        )

        jail_notice_fallback = (
            f"🚨 **TÙ NHÂN MỚI** 🚨\n"
            f"{target.mention} vừa bị chuyển vào đây!\n"
            f"> 🧹 **Hình phạt:** `{count}` lần lắc đít\n"
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
                    logger.warning(f"Could not send custom jail notice: {e}")
                    try:
                        await jail_channel.send(jail_notice_fallback)
                    except Exception as e2:
                        logger.error(f"Failed to send fallback jail notice: {e2}")
        else:
            # Nếu server chưa cài kênh tù riêng, gửi kèm thông báo tù nhân mới ở kênh hiện tại
            try:
                await ctx.send(jail_notice)
            except Exception as e:
                logger.warning(f"Could not send custom jail notice: {e}")
                try:
                    await ctx.send(jail_notice_fallback)
                except Exception as e2:
                    logger.error(f"Failed to send fallback jail notice: {e2}")

    @commands.command(
        name="lacdit",
        aliases=["laudon", "cleanjail", "caizao"],
        brief="Lắc đít cải tạo để giảm án phạt tù.",
        usage="lacdit",
    )
    @commands.guild_only()
    @commands.cooldown(1, 2, commands.BucketType.user)
    async def lacdit(self, ctx: commands.Context) -> None:
        """Lắc đít cải tạo để giảm án tù."""
        guild_id = ctx.guild.id if ctx.guild else 0
        jail_info = self.bot.economy.get_jail_info(ctx.author.id, guild_id)
        if not jail_info:
            await self._reply_or_send(ctx, "❌ Bạn không ở trong tù!")
            return

        # Kiểm tra nếu đã cài kênh nhà tù mà gõ sai kênh
        jail_channel_id = self.bot.economy.get_jail_channel(guild_id)
        if jail_channel_id and ctx.channel.id != jail_channel_id:
            await self._reply_or_send(ctx, f"❌ Bạn chỉ có thể lắc đít cải tạo trong kênh <#{jail_channel_id}>!")
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

            await self._reply_or_send(
                ctx,
                f"🎉 **MÃ HẠN TÙ!** {ctx.author.mention} đã hoàn thành tất cả `{jail_info['total_clean_count']}` lần lắc đít và chính thức được **XUẤT TÙ**!",
            )
        else:
            await self._reply_or_send(
                ctx,
                f"<a:lacdit1:1535528561685823498> {ctx.author.mention} vừa lắc đít 1 lượt! Còn lại **{remaining}/{jail_info['total_clean_count']}** lần.",
            )

    @commands.command(
        name="anxatu",
        aliases=["unjail", "thabong"],
        brief="Tha bổng / Ân xá cho tù nhân trước thời hạn (Chỉ Admin/Owner bot).",
        usage="anxatu <@user>",
    )
    @commands.guild_only()
    async def anxatu(self, ctx: commands.Context, target: discord.Member) -> None:
        """Tha bổng / Ân xá cho tù nhân trước thời hạn (Chỉ Admin/Owner bot)."""
        guild_id = ctx.guild.id if ctx.guild else 0

        # Kiểm tra quyền: Chỉ Admin và Owner của bot mới có quyền sử dụng
        is_bot_owner = await self._is_bot_owner(ctx.author)
        is_bot_admin = await self._is_bot_admin(ctx.author)
        if not (is_bot_owner or is_bot_admin):
            await self._reply_or_send(ctx, "<:zh_deo:1545378962992009217> ")
            return

        if not self.bot.economy.is_in_jail(target.id, guild_id):
            await self._reply_or_send(ctx, f"❌ {target.mention} hiện không ở trong tù!")
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

        await self._reply_or_send(ctx, f"🔓 **Ân xá thành công!** {target.mention} đã được tha bổng và giải phóng trước thời hạn.")

    @commands.command(
        name="danhsachtu",
        aliases=["jailist", "tunan"],
        brief="Xem danh sách các tù nhân đang thụ án.",
        usage="danhsachtu",
    )
    @commands.guild_only()
    async def danhsachtu(self, ctx: commands.Context) -> None:
        """Xem danh sách các tù nhân đang thụ án."""
        prisoners = self.bot.economy.get_all_prisoners(ctx.guild.id)
        if not prisoners:
            await self._reply_or_send(ctx, "🕊️ Hiện tại không có tù nhân nào trong Server!")
            return

        lines = ["🏛️ **DANH SÁCH TÙ NHÂN ĐANG THỤ ÁN** 🏛️"]
        for idx, p in enumerate(prisoners, start=1):
            user = ctx.guild.get_member(p["user_id"])
            user_str = user.mention if user else f"User ID `{p['user_id']}`"
            lines.append(
                f"{idx}. {user_str} - Còn lại: `{p['clean_count']}/{p['total_clean_count']}` lần | Lý do: {p['reason']}"
            )

        await self._reply_or_send(ctx, "\n".join(lines))


async def setup(bot: commands.Bot) -> None:
    await bot.add_cog(Jail(bot))
