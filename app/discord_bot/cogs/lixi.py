import asyncio
import logging
import random
from typing import Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)


def parse_bet_amount(val_str: str, current_money: int) -> int:
    val_str = val_str.strip().lower()
    if val_str in ["all", "allin", "all-in", "tất tay"]:
        return current_money
    
    has_suffix = val_str.endswith("k") or val_str.endswith("m")
    
    if has_suffix:
        val_str = val_str.replace(",", "")
        multiplier = 1000 if val_str.endswith("k") else 1000000
        val_str = val_str[:-1].strip()
    else:
        val_str = val_str.replace(",", "")
        if "." in val_str:
            parts = val_str.split(".")
            if len(parts[-1]) == 3:
                val_str = val_str.replace(".", "")
            else:
                val_str = "".join(parts[:-1]) + "." + parts[-1]
        multiplier = 1
        
    try:
        return int(float(val_str) * multiplier)
    except ValueError:
        return 0


def split_lixi(total_amount: int, num_parts: int, min_amount: int = 1000) -> list[int]:
    if num_parts <= 0:
        return []
    if num_parts == 1:
        return [total_amount]
    
    parts = []
    remaining = total_amount
    for i in range(num_parts - 1):
        # Double-mean method to split
        # We must leave at least (num_parts - 1 - i) * min_amount for the remaining parts
        max_limit = (remaining // (num_parts - i)) * 2
        max_possible = min(max_limit, remaining - (num_parts - 1 - i) * min_amount)
        if max_possible <= min_amount:
            val = min_amount
        else:
            val = random.randint(min_amount, max_possible)
        parts.append(val)
        remaining -= val
    parts.append(remaining)
    random.shuffle(parts)
    return parts


class LixiView(discord.ui.View):
    def __init__(
        self,
        client: commands.Bot,
        sender: discord.Member,
        total_amount: int,
        num_parts: int,
        parts: list[int],
        wish: Optional[str],
        timeout: float = 120.0
    ):
        super().__init__(timeout=timeout)
        self.client = client
        self.sender = sender
        self.total_amount = total_amount
        self.num_parts = num_parts
        self.parts = parts
        self.wish = wish
        self.economy = getattr(client, "economy", None) or Economy()
        self.claims = []  # list of tuples: (user_id, user_name, amount)
        self.claimed_user_ids = set()
        self.message: Optional[discord.Message] = None
        self.is_finished = False

    async def update_embed(self, status_text: Optional[str] = None):
        desc = ""
        if self.wish:
            desc += f"💬 Lời chúc: **{self.wish}**\n\n"
        
        desc += (
            f"👤 **Người phát:** {self.sender.mention}\n"
            f"💵 **Tổng lì xì:** `{self.total_amount:,} VND`\n"
            f"👥 **Số người bốc:** `{self.num_parts}`\n"
            f"📥 **Đã bốc:** `{len(self.claims)}/{self.num_parts}` phần\n\n"
        )
        
        if self.claims:
            desc += "🏆 **Danh sách đã bốc được lì xì:**\n"
            for i, (uid, name, amount) in enumerate(self.claims, 1):
                desc += f"{i}. **{name}** bốc được `{amount:,} VND` 🧧\n"
        else:
            desc += "*Chưa có ai bốc lì xì này, nhanh tay lên nào!*"

        if status_text:
            desc += f"\n\n{status_text}"

        embed = make_embed(
            title="🧧 LÌ XÌ MAY MẮN CHƯA BỐC! 🧧",
            description=desc,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=self.sender.display_avatar.url)
        
        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    @discord.ui.button(label="🧧 Bốc Lì Xì", style=discord.ButtonStyle.success, custom_id="btn_claim_lixi")
    async def claim_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_finished:
            await interaction.response.send_message("❌ Bao lì xì này đã kết thúc rồi!", ephemeral=True)
            return

        if interaction.user.id == self.sender.id:
            await interaction.response.send_message("❌ Bạn không thể tự bốc lì xì của chính mình!", ephemeral=True)
            return

        if interaction.user.id in self.claimed_user_ids:
            await interaction.response.send_message("❌ Bạn đã bốc lì xì này rồi, hãy nhường cơ hội cho người khác nhé!", ephemeral=True)
            return

        await interaction.response.defer()

        if not self.parts:
            self.is_finished = True
            for child in self.children:
                child.disabled = True
            await self.update_embed("🎉 **Lì xì đã được bốc hết!**")
            self.stop()
            return

        # Claim a part
        claimed_amount = self.parts.pop(0)
        self.claimed_user_ids.add(interaction.user.id)
        self.claims.append((interaction.user.id, interaction.user.name, claimed_amount))

        # Add money to clamer's wallet
        self.economy.add_money(interaction.user.id, claimed_amount)
        log_wallet_change(
            logger,
            event="lixi_claim",
            user_id=interaction.user.id,
            money_delta=claimed_amount,
            sender_id=self.sender.id,
            total_lixi_pool=self.total_amount
        )

        if not self.parts:
            self.is_finished = True
            for child in self.children:
                child.disabled = True
            await self.update_embed("🎉 **Lì xì đã được bốc hết!**")
            self.stop()
        else:
            await self.update_embed()

    async def on_timeout(self):
        if self.is_finished:
            return
        self.is_finished = True
        for child in self.children:
            child.disabled = True

        # Refund any leftover money
        leftover = sum(self.parts)
        if leftover > 0:
            self.economy.add_money(self.sender.id, leftover)
            log_wallet_change(
                logger,
                event="lixi_timeout_refund",
                user_id=self.sender.id,
                money_delta=leftover,
                total_lixi_pool=self.total_amount
            )
            status_text = f"⏱️ **Hết thời gian!** Số tiền dư `{leftover:,} VND` đã được trả lại cho {self.sender.mention}."
        else:
            status_text = "⏱️ **Hết thời gian!** Lì xì đã kết thúc."

        # Edit embed with final status
        desc = ""
        if self.wish:
            desc += f"💬 Lời chúc: **{self.wish}**\n\n"
        
        desc += (
            f"👤 **Người phát:** {self.sender.mention}\n"
            f"💵 **Tổng lì xì:** `{self.total_amount:,} VND`\n"
            f"👥 **Số người bốc:** `{self.num_parts}`\n"
            f"📥 **Đã bốc:** `{len(self.claims)}/{self.num_parts}` phần\n\n"
        )
        
        if self.claims:
            desc += "🏆 **Danh sách đã bốc được lì xì:**\n"
            for i, (uid, name, amount) in enumerate(self.claims, 1):
                desc += f"{i}. **{name}** bốc được `{amount:,} VND` 🧧\n"
        else:
            desc += "*Không có ai bốc lì xì này.*\n"
            
        desc += f"\n\n{status_text}"

        embed = make_embed(
            title="🧧 LÌ XÌ ĐÃ KẾT THÚC! 🧧",
            description=desc,
            color=discord.Color.dark_red()
        )
        embed.set_thumbnail(url=self.sender.display_avatar.url)

        if self.message:
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass


class Lixi(commands.Cog, name="Lixi"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()

    @commands.command(
        brief="Tạo bao lì xì cho mọi người bốc ngẫu nhiên.",
        usage="lixi <tổng_tiền> <số_người_bốc> [lời_chúc]",
        aliases=["lucky", "hongbao"]
    )
    async def lixi(
        self,
        ctx: commands.Context,
        total_amount_str: str = None,
        num_parts: int = None,
        *,
        wish: str = None
    ):
        user_id = ctx.author.id
        
        if total_amount_str is None or num_parts is None:
            prefix = ctx.prefix
            embed = make_embed(
                title="🧧 HƯỚNG DẪN SỬ DỤNG LỆNH LÌ XÌ 🧧",
                description=(
                    f"Phát lì xì vào kênh chat, chia làm nhiều phần ngẫu nhiên cho mọi người bốc.\n\n"
                    f"👉 **Cú pháp:** `{prefix}lixi <tổng_tiền> <số_người_bốc> [lời_chúc]`\n"
                    f"👉 **Ví dụ:** `{prefix}lixi 500k 5 Phát tài phát lộc!`\n"
                    f"👉 **Ví dụ:** `{prefix}lixi 2.5m 10`\n\n"
                    f"💡 *Lưu ý: Tiền thừa từ các bao lì xì không được bốc hết sau 2 phút sẽ tự động hoàn lại vào tài khoản của bạn.*"
                ),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return

        current_money = self.economy.get_entry(user_id)[1]
        total_amount = parse_bet_amount(total_amount_str, current_money)

        if total_amount <= 0:
            await ctx.send("❌ Số tiền lì xì không hợp lệ.")
            return

        if num_parts <= 0:
            await ctx.send("❌ Số người bốc phải lớn hơn 0.")
            return

        if num_parts > 50:
            await ctx.send("❌ Số người bốc tối đa trong một lần là 50 người.")
            return

        min_required = num_parts * 1000
        if total_amount < min_required:
            await ctx.send(f"❌ Với `{num_parts}` người bốc, tổng số tiền tối thiểu phải là `{min_required:,} VND` (mỗi phần tối thiểu 1,000 VND).")
            return

        if current_money < total_amount:
            await ctx.send(f"❌ Bạn không đủ tiền để phát lì xì! Số dư của bạn: `{current_money:,} VND` (thiếu `{(total_amount - current_money):,} VND`).")
            return

        # Deduct total amount from creator's balance immediately
        self.economy.add_money(user_id, -total_amount)
        log_wallet_change(
            logger,
            event="lixi_create",
            user_id=user_id,
            money_delta=-total_amount,
            num_parts=num_parts,
            wish=wish
        )

        # Generate random split parts
        parts = split_lixi(total_amount, num_parts)

        # Build View and initial Embed
        view = LixiView(
            client=self.bot,
            sender=ctx.author,
            total_amount=total_amount,
            num_parts=num_parts,
            parts=parts,
            wish=wish,
            timeout=120.0
        )

        desc = ""
        if wish:
            desc += f"💬 Lời chúc: **{wish}**\n\n"
        
        desc += (
            f"👤 **Người phát:** {ctx.author.mention}\n"
            f"💵 **Tổng lì xì:** `{total_amount:,} VND`\n"
            f"👥 **Số người bốc:** `{num_parts}`\n"
            f"📥 **Đã bốc:** `0/{num_parts}` phần\n\n"
            f"*Chưa có ai bốc lì xì này, nhanh tay lên nào!*"
        )

        embed = make_embed(
            title="🧧 LÌ XÌ MAY MẮN CHƯA BỐC! 🧧",
            description=desc,
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)

        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


async def setup(bot: commands.Bot):
    await bot.add_cog(Lixi(bot))
