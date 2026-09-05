import logging
import time

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import EMOJI_VND, make_embed

logger = logging.getLogger(__name__)

# Term days -> (settings key for rate, default rate, display name)
BANK_TERMS: dict[str, tuple[str, float, str]] = {
    "1": ("bank_rate_1d", 0.01, "1 ngày"),
    "7": ("bank_rate_7d", 0.10, "7 ngày"),
    "30": ("bank_rate_30d", 0.50, "30 ngày"),
}


def _term_rate(economy: Economy, term: str) -> float:
    """Current rate for a term, tunable via system_settings."""
    key, default, _ = BANK_TERMS[term]
    try:
        return float(economy.get_setting(key, str(default)))
    except (TypeError, ValueError):
        return default
EARLY_WITHDRAW_FEE = 0.05


def _parse_amount(raw: str) -> int:
    s = raw.lower().strip().replace(".", "").replace(",", "")
    mult = 1
    if s.endswith("k"):
        mult, s = 1_000, s[:-1]
    elif s.endswith("m") or s.endswith("tr"):
        mult, s = 1_000_000, s[:-2] if s.endswith("tr") else s[:-1]
    try:
        val = int(float(s) * mult)
    except ValueError:
        raise commands.BadArgument("Số tiền không hợp lệ!")
    return val


class Bank(commands.Cog):
    """Ngân hàng tiết kiệm: gửi tiền khóa kỳ hạn nhận lãi."""

    def __init__(self, client: commands.Bot):
        self.client = client
        self.bot = client
        self.economy: Economy = getattr(client, "economy", None) or Economy()

    @commands.group(name="bank", brief="Ngân hàng tiết kiệm: gửi tiền nhận lãi theo kỳ hạn.", invoke_without_command=True)
    async def bank(self, ctx: commands.Context):
        await self._show_bank(ctx)

    async def _show_bank(self, ctx: commands.Context):
        user_id = ctx.author.id
        deposits = self.economy.get_bank_deposits(user_id)
        now = int(time.time())

        if not deposits:
            embed = make_embed(
                title="🏦 NGÂN HÀNG CASINO 🏦",
                description=(
                    "Bạn chưa có sổ tiết kiệm nào!\n\n"
                    "**Kỳ hạn & lãi suất hiện tại:**\n"
                    + "\n".join(
                        f"• **{name}**: {_term_rate(self.economy, term) * 100:.0f}% lãi"
                        for term, (_, _, name) in sorted(BANK_TERMS.items())
                    )
                    + "\n\n➡️ Gõ `i?bank deposit <số tiền> <1|7|30>` để gửi tiền.\n"
                    "🔒 Tiền trong ngân hàng **không thể bị cướp** và không thể dùng cược!"
                ),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        lines = []
        total_principal = 0
        for dep_id, amount, term_days, rate, deposit_at in deposits:
            total_principal += amount
            mature_at = deposit_at + term_days * 86400
            interest = int(amount * rate)
            if now >= mature_at:
                status = "🟢 **ĐÁO HẠN — rút được gốc + lãi!**"
            else:
                remain = mature_at - now
                hours = remain // 3600
                minutes = (remain % 3600) // 60
                status = f"⏳ Còn **{hours} giờ {minutes} phút** mới đáo hạn"
            lines.append(
                f"📜 **Sổ #{dep_id}** — `{amount:,}` {EMOJI_VND} ({term_days} ngày, lãi {rate * 100:.0f}% = `+{interest:,}` {EMOJI_VND})\n└ {status}"
            )

        cap = int(self.economy.get_setting("bank_cap", "100000000"))
        embed = make_embed(
            title="🏦 SỔ TIẾT KIỆM CỦA BẠN",
            description=(
                "\n".join(lines)
                + f"\n\n💵 **Tổng gốc đang gửi:** `{total_principal:,}` {EMOJI_VND}"
                f"\n🏦 **Hạn mức gửi tối đa:** `{cap:,}` {EMOJI_VND}"
            ),
            color=discord.Color.blue()
        )
        embed.set_footer(text="Rút sớm: mất toàn bộ lãi + phí 5% gốc. Gõ i?bank withdraw <số sổ>")
        await ctx.send(embed=embed)

    @bank.command(name="deposit", aliases=["gui", "send"])
    async def deposit(self, ctx: commands.Context, amount_str: str = None, term: str = None):
        if not amount_str or not term:
            await ctx.send("❌ Dùng: `i?bank deposit <số tiền> <1|7|30>` (đơn vị ngày).")
            return
        try:
            amount = _parse_amount(amount_str)
        except commands.BadArgument:
            await ctx.send("❌ Số tiền không hợp lệ! Ví dụ: `i?bank deposit 50m 7`")
            return
        if term not in BANK_TERMS:
            await ctx.send("❌ Kỳ hạn chỉ nhận `1`, `7` hoặc `30` (ngày).")
            return

        user_id = ctx.author.id
        if amount <= 0:
            await ctx.send("❌ Số tiền gửi phải lớn hơn 0!")
            return

        rate = _term_rate(self.economy, term)
        _, _, term_name = BANK_TERMS[term]
        cap = int(self.economy.get_setting("bank_cap", "100000000"))

        with self.economy.transaction():
            current_total = self.economy.get_bank_total(user_id)
            if current_total + amount > cap:
                await ctx.send(
                    f"❌ Vượt hạn mức gửi tối đa! Bạn đang gửi `{current_total:,}` {EMOJI_VND}, hạn mức `{cap:,}` {EMOJI_VND}."
                )
                return

            money = self.economy.get_entry(user_id)[1]
            if money < amount:
                await ctx.send(f"❌ Ví của bạn chỉ có `{money:,}` {EMOJI_VND}, không đủ để gửi `{amount:,}` {EMOJI_VND}.")
                return

            self.economy.add_money(user_id, -amount)
            dep_id = self.economy.add_bank_deposit(user_id, amount, term, rate)
        interest = int(amount * rate)
        logger.info("Bank deposit: user=%s amount=%s term=%sd", user_id, amount, term)

        embed = make_embed(
            title="🏦 GỬI TIỀN THÀNH CÔNG",
            description=(
                f"📜 **Sổ tiết kiệm #{dep_id}** đã mở!\n\n"
                f"💵 **Gốc:** `{amount:,}` {EMOJI_VND}\n"
                f"⏳ **Kỳ hạn:** {term_name}\n"
                f"💰 **Lãi khi đáo hạn:** `+{interest:,}` {EMOJI_VND}\n"
                f"🎁 **Nhận về lúc đáo hạn:** `{amount + interest:,}` {EMOJI_VND}\n\n"
                f"🔒 Tiền đang bị khóa — rút sớm sẽ mất lãi + phí 5%."
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @bank.command(name="withdraw", aliases=["rut"])
    async def withdraw(self, ctx: commands.Context, deposit_id: int = None):
        if deposit_id is None:
            await ctx.send("❌ Dùng: `i?bank withdraw <số sổ>` (xem `i?bank`).")
            return

        user_id = ctx.author.id
        row = self.economy.get_bank_deposit(deposit_id)
        if not row or row[1] != user_id:
            await ctx.send("❌ Không tìm thấy sổ tiết kiệm này (hoặc không phải của bạn).")
            return

        _, _, amount, term_days, rate, deposit_at = row
        now = int(time.time())
        mature_at = deposit_at + term_days * 86400

        if now >= mature_at:
            interest = int(amount * rate)
            payout = amount + interest
            note = f"💰 **Lãi đáo hạn:** `+{interest:,}` {EMOJI_VND}"
        else:
            fee = int(amount * EARLY_WITHDRAW_FEE)
            payout = amount - fee
            note = (
                f"⚠️ **RÚT SỚM** (còn {(mature_at - now) // 3600} giờ nữa mới đáo hạn)\n"
                f"💸 **Phí phạt 5%:** `-{fee:,}` {EMOJI_VND} (mất toàn bộ lãi)"
            )

        with self.economy.transaction():
            # Check existence again inside transaction
            check_row = self.economy.get_bank_deposit(deposit_id)
            if not check_row or check_row[1] != user_id:
                await ctx.send("❌ Không tìm thấy sổ tiết kiệm này (hoặc đã được rút).")
                return
            self.economy.remove_bank_deposit(deposit_id)
            self.economy.add_money(user_id, payout)
        logger.info("Bank withdraw: user=%s deposit=%s payout=%s", user_id, deposit_id, payout)

        embed = make_embed(
            title="🏦 RÚT TIỀN THÀNH CÔNG",
            description=(
                f"{note}\n\n"
                f"💵 **Nhận về ví:** `{payout:,}` {EMOJI_VND}\n"
                f"💳 **Số dư hiện tại:** `{self.economy.get_entry(user_id)[1]:,}` {EMOJI_VND}"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @bank.command(name="stats", hidden=True)
    async def stats(self, ctx: commands.Context):
        if ctx.author.id not in config.bot.owner_ids and not await ctx.bot.is_owner(ctx.author):
            await ctx.send("❌ Chỉ Admin/Owner mới dùng được lệnh này!")
            return
        total, count = self.economy.get_bank_stats()
        embed = make_embed(
            title="🏦 THỐNG KÊ NGÂN HÀNG",
            description=(
                f"💰 **Tổng tiền đang khóa trong ngân hàng:** `{total:,}` {EMOJI_VND}\n"
                f"📜 **Số sổ tiết kiệm đang hoạt động:** `{count}`"
            ),
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)


async def setup(client: commands.Bot):
    await client.add_cog(Bank(client))
