import asyncio
import json
import logging
from typing import Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.economy import Economy

logger = logging.getLogger(__name__)

REJOIN_DELAY_SECONDS = 3.0
TARGETS_SETTING_KEY = "voice_afk_targets"


class VoiceAfk(commands.Cog, name="voice_afk"):
    """
    Cog quản lý treo bot trong phòng voice (AFK Call 24/7).
    Chuyển thể từ hệ thống Voice AFK của Ilis_AFK:
      - Tự động giữ kết nối voice channel 24/7 kể cả khi phòng trống.
      - Tự động kết nối lại (Auto-reconnect sau 3s) khi bị rớt mạng hoặc lỗi server voice.
      - Kiểm tra Audit Log: nếu Admin chủ động kick thì tôn trọng và dừng treo.
      - Tự động ghi nhớ và vào lại đúng kênh sau khi bot restart (Persistent Reconnect).
      - Các lệnh trực tiếp: i?join, i?leave, i?ping, i?voice
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy: Economy = getattr(bot, "economy", None) or Economy()
        self.targets: dict[int, int] = {}  # guild_id -> channel_id
        self.rejoin_tasks: dict[int, asyncio.Task] = {}
        self._load_targets()

    def _load_targets(self) -> None:
        """Tải danh sách phòng voice AFK cần treo từ database."""
        try:
            raw = self.economy.get_setting(TARGETS_SETTING_KEY, "{}")
            data = json.loads(raw) if raw else {}
            self.targets = {int(k): int(v) for k, v in data.items()}
        except Exception as e:
            logger.error("VoiceAfk: Không thể nạp voice_afk_targets: %s", e)
            self.targets = {}

    def _save_targets(self) -> None:
        """Lưu danh sách phòng voice AFK vào database."""
        try:
            data = {str(k): v for k, v in self.targets.items()}
            self.economy.set_setting(TARGETS_SETTING_KEY, json.dumps(data))
        except Exception as e:
            logger.error("VoiceAfk: Không thể lưu voice_afk_targets: %s", e)

    def set_target(self, guild_id: int, channel_id: int) -> None:
        self.targets[guild_id] = channel_id
        self._save_targets()

    def clear_target(self, guild_id: int) -> None:
        if guild_id in self.targets:
            del self.targets[guild_id]
            self._save_targets()

    def cog_unload(self):
        for task in self.rejoin_tasks.values():
            if not task.done():
                task.cancel()
        self.rejoin_tasks.clear()

    # ─────────────────────────────────────────────────────────────────────────
    # Event Listeners
    # ─────────────────────────────────────────────────────────────────────────

    @commands.Cog.listener()
    async def on_ready(self):
        """Khi bot khởi động, tự động kết nối lại vào tất cả các phòng voice đã lưu."""
        self._load_targets()
        if not self.targets:
            return

        logger.info("VoiceAfk: Đang kiểm tra %d phòng voice AFK cần khôi phục...", len(self.targets))
        for guild_id, channel_id in list(self.targets.items()):
            guild = self.bot.get_guild(guild_id)
            if not guild:
                continue

            channel = guild.get_channel(channel_id)
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                continue

            vc = guild.voice_client
            if vc is None or not vc.is_connected():
                perms = channel.permissions_for(guild.me)
                if not perms.connect:
                    logger.warning("VoiceAfk: Thiếu quyền Connect vào '%s' trong %s", channel.name, guild.name)
                    continue

                try:
                    await channel.connect(reconnect=True, self_deaf=False, self_mute=False)
                    logger.info("VoiceAfk: Đã tự động vào lại voice '%s' (Server: %s)", channel.name, guild.name)
                except Exception as e:
                    logger.error("VoiceAfk: Không thể vào lại voice '%s': %s", channel.name, e)
            elif vc.channel.id != channel_id:
                try:
                    await vc.move_to(channel)
                except Exception as e:
                    logger.error("VoiceAfk: Lỗi di chuyển về '%s': %s", channel.name, e)

    @commands.Cog.listener()
    async def on_voice_state_update(
        self,
        member: discord.Member,
        before: discord.VoiceState,
        after: discord.VoiceState,
    ):
        """Theo dõi trạng thái voice của bot để auto-reconnect hoặc cập nhật mục tiêu."""
        # Chỉ xử lý khi chính bot bị tác động
        if member.id != self.bot.user.id:
            return

        guild = member.guild
        guild_id = guild.id

        # 1. Bot bị ngắt kết nối khỏi voice hoàn toàn
        if after.channel is None:
            target_id = self.targets.get(guild_id)
            if not target_id:
                return  # Không có target treo ở guild này

            # Kiểm tra xem có phải do Admin dùng quyền Disconnect kick bot không
            is_admin_kick = False
            try:
                async for entry in guild.audit_logs(action=discord.AuditLogAction.member_disconnect, limit=1):
                    now = discord.utils.utcnow()
                    if (
                        entry.target
                        and entry.target.id == self.bot.user.id
                        and entry.user
                        and entry.user.id != self.bot.user.id
                        and (now - entry.created_at).total_seconds() < 7
                    ):
                        is_admin_kick = True
                    break
            except (discord.Forbidden, discord.HTTPException):
                # Không có quyền đọc audit log -> coi như rớt mạng để auto-reconnect
                is_admin_kick = False

            if is_admin_kick:
                logger.info("VoiceAfk: Bot bị Admin disconnect tại server %s. Đã dừng chế độ treo.", guild.name)
                self.clear_target(guild_id)
                return

            # Nếu do mạng lag / Discord reset server: lên lịch tự kết nối lại sau 3s
            logger.info("VoiceAfk: Bot bị ngắt kết nối tại %s. Chuẩn bị tự động kết nối lại sau 3s...", guild.name)
            existing_task = self.rejoin_tasks.get(guild_id)
            if existing_task and not existing_task.done():
                existing_task.cancel()

            self.rejoin_tasks[guild_id] = asyncio.create_task(
                self._schedule_reconnect(guild, target_id)
            )

        # 2. Bot được Admin chuyển sang phòng voice khác
        elif before.channel and after.channel and before.channel.id != after.channel.id:
            if guild_id in self.targets:
                logger.info(
                    "VoiceAfk: Bot được chuyển phòng từ '%s' sang '%s' tại %s. Cập nhật phòng AFK mới.",
                    before.channel.name,
                    after.channel.name,
                    guild.name,
                )
                self.set_target(guild_id, after.channel.id)

    async def _schedule_reconnect(self, guild: discord.Guild, target_channel_id: int):
        """Chờ một khoảng thời gian rồi thử kết nối lại vào phòng voice mục tiêu."""
        try:
            await asyncio.sleep(REJOIN_DELAY_SECONDS)

            if self.targets.get(guild.id) != target_channel_id:
                return

            channel = guild.get_channel(target_channel_id)
            if not isinstance(channel, (discord.VoiceChannel, discord.StageChannel)):
                logger.warning("VoiceAfk: Phòng voice %s không còn tồn tại.", target_channel_id)
                self.clear_target(guild.id)
                return

            vc = guild.voice_client
            if vc is None or not vc.is_connected():
                perms = channel.permissions_for(guild.me)
                if perms.connect:
                    await channel.connect(reconnect=True, self_deaf=False, self_mute=False)
                    logger.info("VoiceAfk: Đã tự động kết nối lại thành công vào voice '%s'", channel.name)
                else:
                    logger.warning("VoiceAfk: Thiếu quyền Connect khi tự động kết nối lại vào '%s'", channel.name)
            elif vc.channel.id != target_channel_id:
                await vc.move_to(channel)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error("VoiceAfk: Lỗi khi tự động kết nối lại trong %s: %s", guild.name, e)
        finally:
            self.rejoin_tasks.pop(guild.id, None)

    # ─────────────────────────────────────────────────────────────────────────
    # Core Logic Handlers
    # ─────────────────────────────────────────────────────────────────────────

    async def _execute_join(self, ctx: commands.Context, channel: Optional[discord.VoiceChannel] = None):
        if not ctx.guild:
            await ctx.send("❌ Lệnh này chỉ sử dụng được trong server.")
            return

        target_channel = channel
        if target_channel is None:
            if ctx.author.voice and ctx.author.voice.channel:
                target_channel = ctx.author.voice.channel

        if not target_channel:
            await ctx.send("❌ Bạn cần vào một voice channel trước hoặc tag tên kênh!", delete_after=10)
            return

        perms = target_channel.permissions_for(ctx.guild.me)
        if not perms.connect:
            await ctx.send(f"❌ Bot không có quyền kết nối (`Connect`) vào kênh **{target_channel.name}**!", delete_after=10)
            return

        vc = ctx.guild.voice_client
        if vc and vc.is_connected():
            if vc.channel.id == target_channel.id:
                self.set_target(ctx.guild.id, target_channel.id)
                await ctx.send(f"🔊 Bot đã ở trong **{target_channel.name}** rồi và đang bật chế độ treo AFK 24/7!")
                return
            else:
                await vc.move_to(target_channel)
                self.set_target(ctx.guild.id, target_channel.id)
                await ctx.send(f"✅ Đã chuyển sang **{target_channel.name}** - sẽ duy trì treo 24/7 dù không còn ai trong phòng!")
                return

        try:
            await target_channel.connect(reconnect=True, self_deaf=False, self_mute=False)
            self.set_target(ctx.guild.id, target_channel.id)
            await ctx.send(f"✅ Đã vào **{target_channel.name}** - sẽ ở lại và tự động kết nối lại dù không còn ai trong phòng!")
        except Exception as e:
            logger.error("VoiceAfk: Lỗi khi kết nối voice: %s", e)
            await ctx.send(f"❌ Lỗi khi kết nối vào voice channel: `{e}`")

    async def _execute_leave(self, ctx: commands.Context):
        if not ctx.guild:
            return

        vc = ctx.guild.voice_client
        self.clear_target(ctx.guild.id)

        # Hủy task reconnect nếu đang chờ
        rejoin_task = self.rejoin_tasks.pop(ctx.guild.id, None)
        if rejoin_task and not rejoin_task.done():
            rejoin_task.cancel()

        if vc and vc.is_connected():
            await vc.disconnect(force=True)
            await ctx.send("👋 Đã rời khỏi voice channel và hủy chế độ treo AFK.")
        else:
            await ctx.send("❌ Bot không đang ở trong voice channel nào!", delete_after=8)

    async def _execute_ping(self, ctx: commands.Context):
        if not ctx.guild:
            return

        api_ping = round(self.bot.latency * 1000)
        vc = ctx.guild.voice_client
        if vc and vc.is_connected():
            voice_ping = f"`{round(vc.latency * 1000)}ms`" if vc.latency is not None else "`Đang đồng bộ`"
            voice_info = f"`{vc.channel.name}` | Latency: {voice_ping}"
        else:
            voice_info = "`Không kết nối voice`"

        await ctx.send(f"🏓 **API**: `{api_ping}ms` | **Voice**: {voice_info}")

    async def _execute_status(self, ctx: commands.Context):
        if not ctx.guild:
            return

        vc = ctx.guild.voice_client
        target_id = self.targets.get(ctx.guild.id)
        target_channel = ctx.guild.get_channel(target_id) if target_id else None

        embed = discord.Embed(title="🔊 Trạng Thái Voice AFK 24/7", color=discord.Color.purple())

        if vc and vc.is_connected():
            status_str = f"🟢 Đang kết nối tại: **{vc.channel.name}**"
            latency_str = f"{vc.latency * 1000:.1f}ms" if vc.latency is not None else "Đang đồng bộ"
        else:
            status_str = "🔴 Không có kết nối voice"
            latency_str = "N/A"

        target_str = f"**{target_channel.name}** (`{target_id}`)" if target_channel else "Chưa thiết lập"
        auto_rejoin_str = "Bật (Tự reconnect sau 3s nếu rớt)" if target_id else "Tắt"

        embed.add_field(name="Trạng Thái Kết Nối", value=status_str, inline=False)
        embed.add_field(name="Phòng Treo Cố Định", value=target_str, inline=True)
        embed.add_field(name="Auto-Rejoin", value=auto_rejoin_str, inline=True)
        embed.add_field(name="Voice Latency", value=latency_str, inline=True)
        embed.set_footer(text=f"Lệnh: {ctx.prefix}join | {ctx.prefix}leave | {ctx.prefix}ping | {ctx.prefix}voice")

        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────────────────────────────────
    # Command Implementations (Trực tiếp với prefix của bot)
    # ─────────────────────────────────────────────────────────────────────────

    @commands.command(
        name="join",
        aliases=["vjoin", "voicejoin"],
        brief="Bot vào voice channel của bạn và treo 24/7.",
        usage="join [tên kênh]",
    )
    async def join_cmd(self, ctx: commands.Context, *, channel: Optional[discord.VoiceChannel] = None):
        await self._execute_join(ctx, channel)

    @commands.command(
        name="leave",
        aliases=["vleave", "voiceleave"],
        brief="Bot rời khỏi voice channel và dừng treo AFK.",
        usage="leave",
    )
    async def leave_cmd(self, ctx: commands.Context):
        await self._execute_leave(ctx)

    @commands.command(
        name="ping",
        aliases=["vping", "latency"],
        brief="Đo độ trễ API Discord và Voice Server.",
        usage="ping",
    )
    async def ping_cmd(self, ctx: commands.Context):
        await self._execute_ping(ctx)

    @commands.command(
        name="voicestatus",
        aliases=["vstatus", "voice"],
        brief="Xem trạng thái kết nối voice AFK 24/7.",
        usage="voicestatus",
    )
    async def voicestatus_cmd(self, ctx: commands.Context):
        await self._execute_status(ctx)


async def setup(bot: commands.Bot):
    await bot.add_cog(VoiceAfk(bot))
