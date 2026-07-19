import time
import discord
from discord.ext import commands


class Afk(commands.Cog, name="afk"):
    def __init__(self, client: commands.Bot):
        self.client = client
        # { user_id: {"reason": str, "time": float} }
        self._afk: dict[int, dict] = {}

    # ─────────────────────────────────────────────
    # Command: ?afk [reason]
    # ─────────────────────────────────────────────
    @commands.command(
        name="afk",
        brief="Đặt trạng thái AFK.",
        usage="afk [lý do]",
    )
    async def afk_cmd(self, ctx: commands.Context, *, reason: str = "👋"):
        user_id = ctx.author.id
        self._afk[user_id] = {"reason": reason, "time": time.time()}

        await ctx.send(f"{ctx.author.mention} <a:heartw:1528469641603579924>I set your AFK: {reason}")

    # ─────────────────────────────────────────────
    # Listener: on_message
    #   • Nếu ai mention người đang AFK → thông báo
    #   • Nếu người đang AFK tự gửi tin nhắn → xóa AFK
    # ─────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        # Bỏ qua bot
        if message.author.bot:
            return

        author_id = message.author.id

        # 1) Người đang AFK gửi tin nhắn → tự động xóa AFK
        if author_id in self._afk:
            # Tránh xóa AFK ngay khi họ vừa gõ lệnh ?afk
            afk_since = self._afk[author_id]["time"]
            if time.time() - afk_since > 3:
                del self._afk[author_id]
                try:
                    await message.channel.send(
                        f"<a:lly_ty2:1528463592876277772> {message.author.mention} AFK của bạn đã được xóa!",
                        delete_after=8,
                    )
                except Exception:
                    pass
                return  # không cần kiểm tra mention dưới nữa

        # 2) Kiểm tra xem có mention ai đang AFK không
        if not message.mentions:
            return

        notified: set[int] = set()
        for member in message.mentions:
            if member.bot or member.id == author_id:
                continue
            if member.id in notified:
                continue
            if member.id in self._afk:
                afk_data = self._afk[member.id]
                reason = afk_data["reason"]
                since = afk_data["time"]

                # Tính thời gian đã AFK
                elapsed = int(time.time() - since)
                if elapsed < 60:
                    time_str = f"{elapsed} giây"
                elif elapsed < 3600:
                    time_str = f"{elapsed // 60} phút"
                elif elapsed < 86400:
                    hours = elapsed // 3600
                    mins = (elapsed % 3600) // 60
                    time_str = f"{hours} giờ {mins} phút" if mins else f"{hours} giờ"
                else:
                    days = elapsed // 86400
                    time_str = f"{days} ngày"

                try:
                    await message.channel.send(
                        f"💤 **{member.display_name}** hiện đang AFK: {reason} — Đã AFK được **{time_str}**."
                    )
                except Exception:
                    pass
                notified.add(member.id)


async def setup(client: commands.Bot):
    await client.add_cog(Afk(client))
