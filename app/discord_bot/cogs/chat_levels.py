import logging

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.member_levels import (
    CHAT_XP_COOLDOWN_SECONDS,
    CHAT_XP_MAX,
    CHAT_XP_MIN,
    GIVE_CAP_BANDS,
    MAX_MEMBER_LEVEL,
    _get_overrides,
    daily_give_cap,
    daily_receive_cap,
    grant_chat_xp,
    remaining_daily,
    set_override,
    transfer_cap,
    xp_to_next_level,
)

logger = logging.getLogger(__name__)

CURRENCY_UNIT = {"money": "VND", "gold": "thỏi vàng"}


def _parse_limit_val(val_str: str):
    """Parse số tiền hỗ trợ hậu tố k/m; trả về None cho 'clear', 'invalid' nếu sai cú pháp."""
    val_str = val_str.lower().strip()
    if val_str in ["clear", "reset", "none", "null", "khong", "không"]:
        return None
    multiplier = 1
    if val_str.endswith("k"):
        multiplier, val_str = 1000, val_str[:-1]
    elif val_str.endswith("m"):
        multiplier, val_str = 1_000_000, val_str[:-1]
    try:
        return int(float(val_str.replace(",", "")) * multiplier)
    except ValueError:
        return "invalid"


class ChatLevels(commands.Cog, name="ChatLevels"):
    """Cấp độ thành viên tăng khi chat + giới hạn cho/nhận tiền theo cấp."""

    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = client.economy

    # ─────────────────────────────────────────────
    # Listener: tích XP chat (10-20 XP mỗi 60s)
    # ─────────────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or message.guild is None:
            return
        try:
            leveled_up, level, _ = grant_chat_xp(self.economy, message.author.id)
        except Exception:
            logger.exception("grant_chat_xp failed for user %s", message.author.id)
            return
        if leveled_up:
            try:
                await message.channel.send(
                    f"🎉 Chúc mừng **{message.author.display_name}** đã đạt **Cấp độ {level}**! "
                    f"Hạn mức cho/nhận tiền đã được nâng lên.",
                    delete_after=15,
                )
            except Exception:
                pass

    # ─────────────────────────────────────────────
    # Command: $level [@thành_viên]
    # ─────────────────────────────────────────────
    @commands.command(
        brief="Xem cấp độ của bạn (tăng khi chat) và hạn mức cho/nhận tiền hôm nay.",
        usage="level [@thành_viên]",
        aliases=["capdo", "mylevel", "trinhdo"],
    )
    async def level(self, ctx: commands.Context, target: discord.Member = None):
        member = target or ctx.author
        if member.bot:
            await ctx.send("❌ Bot không có cấp độ thành viên!")
            return

        info = remaining_daily(self.economy, member.id, "money")
        info_gold = remaining_daily(self.economy, member.id, "gold")
        level, xp = info["level"], info["xp"]
        need = xp_to_next_level(level)

        if need <= 0:
            progress = "🏆 **Cấp tối đa!**"
        else:
            filled = int(10 * xp / need)
            bar = "█" * filled + "░" * (10 - filled)
            progress = f"`{bar}` `{xp:,}/{need:,} XP`"

        embed = make_embed(
            title="📊 CẤP ĐỘ THÀNH VIÊN",
            description=(
                f"👤 **Thành viên:** {member.mention}\n"
                f"⭐ **Cấp độ:** `{level}/{MAX_MEMBER_LEVEL}`\n"
                f"📈 **Tiến độ:** {progress}\n\n"
                f"**💸 Hạn mức chuyển tiền VND (mỗi lần):** `{info['transfer_cap']:,}` VND\n"
                f"**📤 Quỹ cho hôm nay:** `{info['sent']:,}/{info['give_cap']:,}` VND — còn `{info['sent_remaining']:,}`\n"
                f"**📥 Quỹ nhận hôm nay:** `{info['received']:,}/{info['receive_cap']:,}` VND — còn `{info['received_remaining']:,}`\n\n"
                f"**🥇 Hạn mức vàng (mỗi lần):** `{info_gold['transfer_cap']:,}` thỏi vàng\n"
                f"**📤 Đã cho vàng hôm nay:** còn `{info_gold['sent_remaining']:,}`\n"
                f"**📥 Đã nhận vàng hôm nay:** còn `{info_gold['received_remaining']:,}`\n\n"
                f"💡 *Chat nhiều để tăng cấp — càng lên cấp hạn mức cho/nhận càng lớn!*"
            ),
            color=discord.Color.blurple(),
        )
        embed.set_footer(text=f"💬 Kiếm {CHAT_XP_MIN}–{CHAT_XP_MAX} XP mỗi tin nhắn (tối đa 1 lần/{CHAT_XP_COOLDOWN_SECONDS}s)")
        embed.set_thumbnail(url=member.display_avatar.url)
        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────
    # Owner: $setgivecap / $setgivedaily / $givelimits
    # ─────────────────────────────────────────────
    def _is_owner(self, ctx: commands.Context) -> bool:
        return ctx.author.id in config.bot.owner_ids

    @commands.command(
        brief="[Owner] Đặt hạn mức chuyển tiền MỖI LẦN cho một cấp độ (ghi đè công thức).",
        usage="setgivecap <cấp> <số_tiền|clear>",
        aliases=["setgivecaptransfer"],
        hidden=True,
    )
    async def setgivecap(self, ctx: commands.Context, level: int = None, amount: str = None):
        await self._handle_set_limit(ctx, "transfer", level, amount)

    @commands.command(
        brief="[Owner] Đặt hạn mức tổng cho/nhận MỖI NGÀY cho một cấp độ (ghi đè công thức).",
        usage="setgivedaily <cấp> <số_tiền|clear>",
        hidden=True,
    )
    async def setgivedaily(self, ctx: commands.Context, level: int = None, amount: str = None):
        await self._handle_set_limit(ctx, "daily", level, amount)

    async def _handle_set_limit(self, ctx, kind: str, level: int, amount: str):
        if not (self._is_owner(ctx) or await ctx.bot.is_owner(ctx.author)):
            await ctx.send("❌ **Lỗi:** Chỉ có Admin/Owner mới có quyền sử dụng lệnh này!")
            return

        label = "mỗi lần" if kind == "transfer" else "cho mỗi ngày"
        if level is None:
            await ctx.send(
                f"❌ **Cú pháp:** `{ctx.prefix}set{'givecap' if kind == 'transfer' else 'givedaily'} "
                f"<cấp 0-{MAX_MEMBER_LEVEL}> <số_tiền|clear>` — ví dụ: `50k`, `2m`, `clear`."
            )
            return
        if not (0 <= level <= MAX_MEMBER_LEVEL):
            await ctx.send(f"❌ **Lỗi:** Cấp độ phải trong khoảng `0`–`{MAX_MEMBER_LEVEL}`.")
            return
        if amount is None:
            current = transfer_cap(level, self.economy) if kind == "transfer" else daily_give_cap(level, self.economy)
            await ctx.send(
                f"⚙️ Hạn mức hiện tại của cấp **{level}** ({label}): `{current:,} VND`."
            )
            return

        value = _parse_limit_val(amount)
        if value == "invalid":
            await ctx.send("❌ **Lỗi:** Số tiền không hợp lệ. Ví dụ: `10k`, `500k`, `2m` hoặc `clear`.")
            return
        if value is not None and value < 0:
            await ctx.send("❌ **Lỗi:** Số tiền không được âm. Dùng `0` để tắt cho/nhận ở cấp này, `clear` để về bảng mặc định.")
            return

        set_override(self.economy, kind, level, value)
        if value is None:
            await ctx.send(f"✅ Đã xoá override — cấp **{level}** dùng lại bảng mặc định ({label}).")
        else:
            note = " (quỹ nhận của cấp này tự = 1,5×)" if kind == "daily" else ""
            await ctx.send(f"✅ Đã đặt hạn mức {label} của cấp **{level}** thành `{value:,} VND`{note}.")

    @commands.command(
        brief="Xem bảng hạn mức cho/nhận tiền theo cấp độ.",
        usage="givelimits",
        aliases=["givelimit", "hanhmuc"],
    )
    async def givelimits(self, ctx: commands.Context):
        overrides = _get_overrides(self.economy)
        rows = []
        for idx, (start, _) in enumerate(GIVE_CAP_BANDS):
            end = GIVE_CAP_BANDS[idx + 1][0] - 1 if idx + 1 < len(GIVE_CAP_BANDS) else MAX_MEMBER_LEVEL
            tcap = transfer_cap(start, self.economy)
            gcap = daily_give_cap(start, self.economy)
            rcap = daily_receive_cap(start, self.economy)
            marked = " ⚙️" if (str(start) in overrides.get("transfer", {}) or str(start) in overrides.get("daily", {})) else ""
            rows.append(f"Cấp **{start}–{end}**{marked}: `{tcap:,} VND/lần` — cho `{gcap:,}/ngày` — nhận `{rcap:,}/ngày`")

        embed = make_embed(
            title="⚖️ GIỚI HẠN CHO/NHẬN TIỀN THEO CẤP ĐỘ",
            description=(
                f"Mỗi lần chuyển tối đa = **min**(hạn mức người cho, hạn mức người nhận).\n"
                f"Mỗi ngày: tổng **cho** ≤ quỹ cho, tổng **nhận** ≤ quỹ nhận (= 1,5× quỹ cho) của từng bên.\n\n"
                + "\n".join(rows)
                + "\n\n💡 *Chat để tăng cấp. ⚙️ = cấp đầu khung bị owner ghi đè thủ công.*"
            ),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)


async def setup(client: commands.Bot):
    await client.add_cog(ChatLevels(client))
