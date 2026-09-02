import logging
import time
import typing

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

        # 1. Kiểm tra Server: Nếu bot có danh sách Server cho phép (allowed_guild_ids)
        # Server không thuộc danh sách -> bỏ qua hoàn toàn (không tích XP, không gửi tin)
        allowed_guilds = getattr(config.bot, "allowed_guild_ids", None)
        if allowed_guilds and message.guild.id not in allowed_guilds:
            return

        # 2. Tích XP chat
        try:
            leveled_up, level, _ = grant_chat_xp(self.economy, message.author.id)
        except Exception:
            logger.exception("grant_chat_xp failed for user %s", message.author.id)
            return

        if not leveled_up:
            return

        # 3. Phương án 1: Kiểm tra Kênh bị cấm (camkenh / blocked_channels)
        # Vẫn được tích XP nhưng KHÔNG gửi tin nhắn thông báo lên cấp vào kênh bị cấm
        guild_id = message.guild.id
        channel_id = message.channel.id
        db_blocked = self.economy.get_blocked_channels(guild_id) if self.economy else []
        global_blocked = getattr(config.bot, "blocked_channels", None) or []
        all_blocked = set(db_blocked).union(global_blocked)

        if channel_id in all_blocked:
            return

        # 4. Gửi thông báo lên cấp tại các kênh hợp lệ (tự xóa sau 15s)
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
                f"**📤 Quỹ cho vàng hôm nay:** `{info_gold['sent']:,}/{info_gold['give_cap']:,}` thỏi — còn `{info_gold['sent_remaining']:,}`\n"
                f"**📥 Quỹ nhận vàng hôm nay:** `{info_gold['received']:,}/{info_gold['receive_cap']:,}` thỏi — còn `{info_gold['received_remaining']:,}`\n\n"
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
        usage="setgivecap <cấp> <số_tiền|clear> [money|gold]",
        aliases=["setgivecaptransfer"],
        hidden=True,
    )
    async def setgivecap(self, ctx: commands.Context, level: int = None, amount: str = None, currency: str = "money"):
        kind = "transfer_gold" if currency.lower() in ("gold", "vang", "vàng") else "transfer"
        await self._handle_set_limit(ctx, kind, level, amount)

    @commands.command(
        brief="[Owner] Đặt hạn mức tổng cho/nhận MỖI NGÀY cho một cấp độ (ghi đè công thức).",
        usage="setgivedaily <cấp> <số_tiền|clear> [money|gold]",
        hidden=True,
    )
    async def setgivedaily(self, ctx: commands.Context, level: int = None, amount: str = None, currency: str = "money"):
        kind = "daily_gold" if currency.lower() in ("gold", "vang", "vàng") else "daily"
        await self._handle_set_limit(ctx, kind, level, amount)

    async def _handle_set_limit(self, ctx, kind: str, level: int, amount: str):
        if not (self._is_owner(ctx) or await ctx.bot.is_owner(ctx.author)):
            await ctx.send("❌ **Lỗi:** Chỉ có Admin/Owner mới có quyền sử dụng lệnh này!")
            return

        is_gold = "gold" in kind
        unit = "thỏi vàng" if is_gold else "VND"
        label = f"mỗi lần ({unit})" if "transfer" in kind else f"cho mỗi ngày ({unit})"
        if level is None:
            cmd = "setgivecap" if "transfer" in kind else "setgivedaily"
            await ctx.send(
                f"❌ **Cú pháp:** `{ctx.prefix}{cmd} <cấp 0-{MAX_MEMBER_LEVEL}> <số_lượng|clear> [money|gold]` — ví dụ: `50k`, `2m`, `5 gold`, `clear`."
            )
            return
        if not (0 <= level <= MAX_MEMBER_LEVEL):
            await ctx.send(f"❌ **Lỗi:** Cấp độ phải trong khoảng `0`–`{MAX_MEMBER_LEVEL}`.")
            return
        if amount is None:
            curr_type = "gold" if is_gold else "money"
            current = transfer_cap(level, self.economy, curr_type) if "transfer" in kind else daily_give_cap(level, self.economy, curr_type)
            await ctx.send(
                f"⚙️ Hạn mức hiện tại của cấp **{level}** ({label}): `{current:,} {unit}`."
            )
            return

        value = _parse_limit_val(amount)
        if value == "invalid":
            await ctx.send(f"❌ **Lỗi:** Số lượng không hợp lệ. Ví dụ: `10k`, `500k`, `2m`, `5` hoặc `clear`.")
            return
        if value is not None and value < 0:
            await ctx.send("❌ **Lỗi:** Số lượng không được âm. Dùng `0` để tắt cho/nhận ở cấp này, `clear` để về mặc định.")
            return

        set_override(self.economy, kind, level, value)
        if value is None:
            await ctx.send(f"✅ Đã xoá override — cấp **{level}** dùng lại công thức mặc định ({label}).")
        else:
            note = " (quỹ nhận của cấp này tự = 1,5×)" if "daily" in kind else ""
            await ctx.send(f"✅ Đã đặt hạn mức {label} của cấp **{level}** thành `{value:,} {unit}`{note}.")

    @commands.command(
        brief="Xem bảng hạn mức cho/nhận tiền và vàng theo cấp độ.",
        usage="givelimits",
        aliases=["givelimit", "hanhmuc"],
    )
    async def givelimits(self, ctx: commands.Context):
        overrides = _get_overrides(self.economy)
        gold_price = self.economy.get_gold_price()
        rows = []
        for idx, (start, _) in enumerate(GIVE_CAP_BANDS):
            end = GIVE_CAP_BANDS[idx + 1][0] - 1 if idx + 1 < len(GIVE_CAP_BANDS) else MAX_MEMBER_LEVEL
            tcap = transfer_cap(start, self.economy, "money")
            gcap = daily_give_cap(start, self.economy, "money")
            rcap = daily_receive_cap(start, self.economy, "money")

            tcap_gold = transfer_cap(start, self.economy, "gold")
            gcap_gold = daily_give_cap(start, self.economy, "gold")
            rcap_gold = daily_receive_cap(start, self.economy, "gold")

            marked = " ⚙️" if (str(start) in overrides.get("transfer", {}) or str(start) in overrides.get("daily", {})) else ""
            rows.append(
                f"• Cấp **{start}–{end}**{marked}:\n"
                f"  💵 **VND:** `{tcap:,}/lần` — Cho `{gcap:,}/ngày` — Nhận `{rcap:,}/ngày`\n"
                f"  🥇 **Vàng:** `{tcap_gold:,} thỏi/lần` — Cho `{gcap_gold:,}/ngày` — Nhận `{rcap_gold:,}/ngày`"
            )

        embed = make_embed(
            title="⚖️ GIỚI HẠN CHO/NHẬN TIỀN & VÀNG THEO CẤP ĐỘ",
            description=(
                f"Mỗi lần chuyển tối đa = **min**(hạn mức người cho, hạn mức người nhận).\n"
                f"Mỗi ngày: tổng **cho** ≤ quỹ cho, tổng **nhận** ≤ quỹ nhận (= 1,5× quỹ cho) của từng bên.\n"
                f"*(Hạn mức vàng được tự động quy đổi theo giá vàng hiện tại: `{gold_price:,} VND/thỏi`)*\n\n"
                + "\n\n".join(rows)
                + "\n\n💡 *Chat để tăng cấp. ⚙️ = cấp đầu khung bị owner ghi đè thủ công.*"
            ),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    # ─────────────────────────────────────────────
    # Admin / Owner: $setlevel <@user/ID> <cấp 0-50> [xp]
    # ─────────────────────────────────────────────
    @commands.command(
        name="setlevel",
        aliases=["setcap", "setcapdo", "setmemberlevel", "setchatlevel"],
        brief="[ADMIN] Đặt cấp độ chat & hạn mức cho/nhận tiền cho một thành viên.",
        usage="setlevel <@thành_viên/ID> <cấp 0-50> [xp]",
    )
    async def setlevel(
        self,
        ctx: commands.Context,
        target: typing.Union[discord.Member, discord.User, str] = None,
        level: int = None,
        xp: int = 0,
    ):
        """Đặt cấp độ thành viên (chỉ dành cho Quản trị viên server hoặc Bot Owner/Admin)."""
        cfg_bot = getattr(config, "bot", None)
        owner_ids = set(getattr(cfg_bot, "owner_ids", None) or [])
        admin_ids = set(getattr(cfg_bot, "admin_ids", None) or [])
        try:
            is_app_owner = await ctx.bot.is_owner(ctx.author)
        except Exception:
            is_app_owner = False
        is_bot_admin = ctx.author.id in owner_ids or ctx.author.id in admin_ids or is_app_owner
        is_guild_admin = bool(ctx.guild) and ctx.author.guild_permissions.administrator

        if not (is_bot_admin or is_guild_admin):
            await ctx.send("❌ **Lỗi:** Chỉ Quản trị viên server hoặc Bot Admin/Owner mới có quyền đặt cấp độ thành viên!")
            return

        if target is None or level is None:
            await ctx.send(
                f"❌ **Cú pháp:** `{ctx.prefix}setlevel <@thành_viên/ID> <cấp 0-{MAX_MEMBER_LEVEL}> [xp]`\n"
                f"👉 *Ví dụ:* `{ctx.prefix}setlevel @Member 20` hoặc `{ctx.prefix}setlevel 123456789 35 500`"
            )
            return

        # Resolve target user
        target_user = None
        target_id = None
        if isinstance(target, (discord.Member, discord.User)):
            target_user = target
            target_id = target.id
        elif isinstance(target, str):
            clean_str = target.strip("<@!> ")
            if clean_str.isdigit():
                target_id = int(clean_str)
                target_user = ctx.guild.get_member(target_id) if ctx.guild else None
                if not target_user:
                    target_user = self.client.get_user(target_id)
            else:
                await ctx.send("❌ **Lỗi:** Vui lòng tag hoặc nhập ID hợp lệ của thành viên!")
                return

        if not target_id:
            await ctx.send("❌ **Lỗi:** Không tìm thấy thông tin thành viên được chỉ định!")
            return

        if target_user and target_user.bot:
            await ctx.send("❌ Không thể đặt cấp độ cho Bot!")
            return

        if not (0 <= level <= MAX_MEMBER_LEVEL):
            await ctx.send(f"❌ **Lỗi:** Cấp độ phải nằm trong khoảng từ `0` đến `{MAX_MEMBER_LEVEL}`.")
            return

        if xp < 0:
            xp = 0

        now = time.time()
        self.economy.set_member_level(target_id, level, xp, now)

        # Lấy thông tin hạn mức mới
        info = remaining_daily(self.economy, target_id, "money")
        info_gold = remaining_daily(self.economy, target_id, "gold")

        mention_str = target_user.mention if target_user else f"<@{target_id}>"
        avatar_url = target_user.display_avatar.url if (target_user and hasattr(target_user, "display_avatar")) else None

        embed = make_embed(
            title="⭐ CẬP NHẬT CẤP ĐỘ THÀNH VIÊN ⭐",
            description=(
                f"✅ Đã đặt cấp độ thành công cho **{mention_str}**!\n\n"
                f"⭐ **Cấp độ mới:** `{level}/{MAX_MEMBER_LEVEL}` (XP: `{xp:,}`)\n\n"
                f"💸 **Hạn mức chuyển VND (mỗi lần):** `{info['transfer_cap']:,} VND`\n"
                f"📤 **Quỹ cho VND hôm nay:** `{info['give_cap']:,} VND`\n"
                f"📥 **Quỹ nhận VND hôm nay:** `{info['receive_cap']:,} VND`\n\n"
                f"🥇 **Hạn mức chuyển Vàng (mỗi lần):** `{info_gold['transfer_cap']:,} thỏi vàng`\n"
                f"📤 **Quỹ cho Vàng hôm nay:** `{info_gold['give_cap']:,} thỏi`\n"
                f"📥 **Quỹ nhận Vàng hôm nay:** `{info_gold['receive_cap']:,} thỏi`"
            ),
            color=discord.Color.green(),
        )
        if avatar_url:
            embed.set_thumbnail(url=avatar_url)
        embed.set_footer(text=f"Thực hiện bởi: {ctx.author.display_name} • Cấp độ thành viên")
        await ctx.send(embed=embed)


async def setup(client: commands.Bot):
    await client.add_cog(ChatLevels(client))
