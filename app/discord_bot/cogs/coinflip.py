import asyncio
from datetime import datetime
import logging
import random
from typing import Optional

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# Game Balance Settings
COINFLIP_WIN_RATE = 0.46        # Tỷ lệ thắng chế độ chơi đơn (46%)
DOUBLECOIN_WIN_RATE = 0.20      # Tỷ lệ thắng chế độ cược 2 xu (20%)
DOUBLE_ROUND_WIN_RATE = 0.45    # Tỷ lệ thắng mỗi vòng double-or-nothing (45%)

# VIP Tiers for Coin Flip
VIP_TIERS = [
    {
        "name": "Bronze",
        "title": "🪙 Người Tung Xu",
        "req_plays": 0,
    },
    {
        "name": "Silver",
        "title": "🍀 Thần May",
        "req_plays": 10,
    },
    {
        "name": "Gold",
        "title": "💰 Cao Thủ Coin Flip",
        "req_plays": 50,
    },
    {
        "name": "Diamond",
        "title": "👑 Vua Đồng Xu",
        "req_plays": 150,
    },
]

ACHIEVEMENTS = {
    "first_flip": "🏅 Đồng Xu Đầu Tiên (Chơi ván đầu tiên)",
    "wins_10": "🥉 Kẻ Liều Lĩnh (Thắng 10 ván)",
    "wins_100": "🥈 Thần May (Thắng 100 ván)",
    "wins_500": "🎖️ Chiến Binh Đồng Xu (Thắng 500 ván)",
    "wins_1000": "🥇 Vua Coin Flip (Thắng 1000 ván)",
    "streak_5": "🔥 Chuỗi 5 (Thắng 5 ván liên tiếp)",
    "streak_10": "⚡ Chuỗi 10 (Thắng 10 ván liên tiếp)",
    "streak_15": "👑 Huyền Thoại Casino (Thắng 15 ván liên tiếp)",
    "bet_1m": "💎 Đại Gia Đồng Xu (Cược 1M+ trong 1 ván)",
}


def get_user_vip(stats: dict) -> dict:
    plays = stats.get("plays", 0)
    if plays >= 150:
        return VIP_TIERS[3]
    if plays >= 50:
        return VIP_TIERS[2]
    if plays >= 10:
        return VIP_TIERS[1]
    return VIP_TIERS[0]


def get_user_lucky_side(user_id: int) -> str:
    today_str = datetime.now().strftime("%Y-%m-%d")
    seed = f"{user_id}:{today_str}:coinflip"
    temp_rand = random.Random(seed)
    return "heads" if temp_rand.random() < 0.5 else "tails"


def check_and_unlock_achievements(stats: dict, last_bet: int) -> list[str]:
    unlocked = set(stats.get("achievements", []))
    newly_unlocked = []

    plays = stats.get("plays", 0)
    wins = stats.get("wins", 0)
    streak = stats.get("streak", 0)

    if plays >= 1 and "first_flip" not in unlocked:
        newly_unlocked.append("first_flip")
    if wins >= 10 and "wins_10" not in unlocked:
        newly_unlocked.append("wins_10")
    if wins >= 100 and "wins_100" not in unlocked:
        newly_unlocked.append("wins_100")
    if wins >= 500 and "wins_500" not in unlocked:
        newly_unlocked.append("wins_500")
    if wins >= 1000 and "wins_1000" not in unlocked:
        newly_unlocked.append("wins_1000")
    if streak >= 5 and "streak_5" not in unlocked:
        newly_unlocked.append("streak_5")
    if streak >= 10 and "streak_10" not in unlocked:
        newly_unlocked.append("streak_10")
    if streak >= 15 and "streak_15" not in unlocked:
        newly_unlocked.append("streak_15")
    if last_bet >= 1_000_000 and "bet_1m" not in unlocked:
        newly_unlocked.append("bet_1m")

    return newly_unlocked


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


class CoinFlipLobbyView(discord.ui.View):
    def __init__(self, cog: "CoinFlip", user_id: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.user_id = user_id
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải bảng điều khiển của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="📊 Thống kê", style=discord.ButtonStyle.secondary, emoji="📊")
    async def stats_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        stats = self.cog.economy.get_coinflip(self.user_id)
        plays = stats["plays"]
        wins = stats["wins"]
        losses = stats["losses"]
        profit = stats["profit"]
        streak = stats["streak"]
        max_streak = stats["max_streak"]
        max_win = stats["max_win_amount"]
        achievements_list = stats["achievements"]
        
        win_rate = (wins / plays * 100) if plays > 0 else 0.0
        profit_sign = "+" if profit >= 0 else ""
        
        vip = get_user_vip(stats)
        lucky_side = get_user_lucky_side(self.user_id)
        lucky_side_vn = "🦅 NGỬA (Heads)" if lucky_side == "heads" else "🌸 SẤP (Tails)"

        desc = (
            f"👑 **Danh hiệu VIP:** `{vip['title']}` *(Lượt chơi: {plays})*\n"
            f"🍀 **Lucky Side hôm nay:** `{lucky_side_vn}`\n\n"
            f"🪙 **Số trận đã chơi:** `{plays}`\n"
            f"🏆 **Số trận thắng:** `{wins}`\n"
            f"❌ **Số trận thua:** `{losses}`\n"
            f"📈 **Tỷ lệ thắng:** `{win_rate:.1f}%`\n"
            f"🔥 **Chuỗi thắng dài nhất:** `{max_streak}`\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{streak}`\n"
            f"💰 **Thắng lớn nhất:** `{max_win:,} VNĐ`\n"
            f"💸 **Tổng lợi nhuận:** `{profit_sign}{profit:,} VNĐ`\n"
        )
        embed = make_embed(
            title=f"📊 THỐNG KÊ COIN FLIP - {interaction.user.name.upper()}",
            description=desc,
            color=discord.Color.blue()
        )
        if achievements_list:
            ach_texts = "\n".join([f"✨ {ACHIEVEMENTS[a]}" for a in achievements_list if a in ACHIEVEMENTS])
            embed.add_field(name="🏆 HUY HIỆU ĐÃ ĐẠT", value=ach_texts, inline=False)
        else:
            embed.add_field(name="🏆 HUY HIỆU ĐÃ ĐẠT", value="*Chưa mở khóa huy hiệu nào*", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏆 Xếp hạng", style=discord.ButtonStyle.secondary, emoji="🏆")
    async def rank_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.economy.cur.execute(
            "SELECT user_id, profit, max_streak, plays FROM user_coinflip ORDER BY profit DESC LIMIT 10"
        )
        rows = self.cog.economy.cur.fetchall()
        if not rows:
            await interaction.response.send_message("ℹ️ Chưa có ai xếp hạng Coin Flip.", ephemeral=True)
            return
        desc = ""
        for i, row in enumerate(rows, 1):
            u_id, profit, max_streak, plays = row
            member = interaction.guild.get_member(u_id)
            name = member.name if member else f"ID: {u_id}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            profit_sign = "+" if profit >= 0 else ""
            desc += f"{medal} **{name}** • Lợi nhuận: `{profit_sign}{profit:,} VNĐ` • Chuỗi: `{max_streak}` *(Lượt chơi: {plays})*\n"
        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG CAO THỦ COIN FLIP",
            description=desc,
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🍀 Mặt may mắn", style=discord.ButtonStyle.secondary, emoji="🍀")
    async def lucky_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        lucky_side = get_user_lucky_side(self.user_id)
        side_vn = "🦅 NGỬA (Heads)" if lucky_side == "heads" else "🌸 SẤP (Tails)"
        embed = make_embed(
            title="🍀 MẶT MAY MẮN CỦA BẠN HÔM NAY",
            description=(
                f"🪙 Lucky Side hôm nay của bạn là: **{side_vn}**\n\n"
                f"💡 **Mẹo:** Cược mặt này trong lệnh `i?cf` và chiến thắng để nhận phần thưởng gấp **x2.2** tiền cược!"
            ),
            color=discord.Color.green()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CoinFlipPlayView(discord.ui.View):
    def __init__(self, ctx: commands.Context, cog: "CoinFlip", user_id: int, bet_amount: int):
        super().__init__(timeout=30.0)
        self.ctx = ctx
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.message: Optional[discord.Message] = None
        self.handled = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt cược của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🦅 Cược Ngửa (Heads)", style=discord.ButtonStyle.success, emoji="🦅")
    async def bet_heads(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        await self.cog.play_regular_flip(self.ctx, "heads", "🦅 NGỬA (Heads)", self.bet_amount, self.message)

    @discord.ui.button(label="🌸 Cược Sấp (Tails)", style=discord.ButtonStyle.primary, emoji="🌸")
    async def bet_tails(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        await self.cog.play_regular_flip(self.ctx, "tails", "🌸 SẤP (Tails)", self.bet_amount, self.message)

    @discord.ui.button(label="🪙 Double Coin (x4)", style=discord.ButtonStyle.danger, emoji="🪙")
    async def bet_double_coin(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        view = DoubleCoinChoiceView(self.ctx, self.cog, self.user_id, self.bet_amount)
        embed = make_embed(
            title="🪙🪙 DOUBLE COIN (HAI ĐỒNG XU)",
            description=(
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n\n"
                f"Tung cùng lúc 2 đồng xu. Đoán đúng kết quả cả 2 mặt để nhận **x4** tiền cược!\n\n"
                f"Chọn tổ hợp cược của bạn:"
            ),
            color=discord.Color.purple()
        )
        view.message = self.message
        await self.message.edit(embed=embed, view=view)

    async def on_timeout(self):
        if not self.handled and self.message:
            embed = make_embed(
                title="⏱️ VÁN CƯỢC BỊ HỦY",
                description=f"👤 **Người chơi:** {self.ctx.author.mention}\n\n*Hết thời gian chọn cược. Tiền cược đã được hoàn lại.*",
                color=discord.Color.red()
            )
            try:
                # Refund
                self.cog.economy.add_money(self.user_id, self.bet_amount)
                log_wallet_change(logger, event="coinflip_timeout_refund", user_id=self.user_id, money_delta=self.bet_amount)
                for child in self.children:
                    child.disabled = True
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


class DoubleCoinChoiceView(discord.ui.View):
    def __init__(self, ctx: commands.Context, cog: "CoinFlip", user_id: int, bet_amount: int):
        super().__init__(timeout=30.0)
        self.ctx = ctx
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.message: Optional[discord.Message] = None
        self.handled = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt cược của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🦅🦅 Ngửa-Ngửa", style=discord.ButtonStyle.success)
    async def choice_hh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        await self.cog.play_double_coin_flip(self.ctx, "heads", "heads", "🦅 Ngửa | 🦅 Ngửa", self.bet_amount, self.message)

    @discord.ui.button(label="🦅🌸 Ngửa-Sấp", style=discord.ButtonStyle.primary)
    async def choice_ht(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        await self.cog.play_double_coin_flip(self.ctx, "heads", "tails", "🦅 Ngửa | 🌸 Sấp", self.bet_amount, self.message)

    @discord.ui.button(label="🌸🦅 Sấp-Ngửa", style=discord.ButtonStyle.primary)
    async def choice_th(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        await self.cog.play_double_coin_flip(self.ctx, "tails", "heads", "🌸 Sấp | 🦅 Ngửa", self.bet_amount, self.message)

    @discord.ui.button(label="🌸🌸 Sấp-Sấp", style=discord.ButtonStyle.success)
    async def choice_tt(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        await self.cog.play_double_coin_flip(self.ctx, "tails", "tails", "🌸 Sấp | 🌸 Sấp", self.bet_amount, self.message)

    @discord.ui.button(label="🔙 Quay lại", style=discord.ButtonStyle.danger)
    async def go_back(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.handled = True
        self.stop()
        view = CoinFlipPlayView(self.ctx, self.cog, self.user_id, self.bet_amount)
        embed = make_embed(
            title="🪙 TRÒ CHƠI COIN FLIP - CỬA CƯỢC",
            description=(
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n\n"
                f"Hãy chọn cửa cược hoặc chế độ phụ ở bên dưới:"
            ),
            color=discord.Color.blue()
        )
        view.message = self.message
        await self.message.edit(embed=embed, view=view)

    async def on_timeout(self):
        if not self.handled and self.message:
            embed = make_embed(
                title="⏱️ VÁN CƯỢC BỊ HỦY",
                description=f"👤 **Người chơi:** {self.ctx.author.mention}\n\n*Hết thời gian chọn cược. Tiền cược đã được hoàn lại.*",
                color=discord.Color.red()
            )
            try:
                self.cog.economy.add_money(self.user_id, self.bet_amount)
                log_wallet_change(logger, event="coinflip_timeout_refund", user_id=self.user_id, money_delta=self.bet_amount)
                for child in self.children:
                    child.disabled = True
                await self.message.edit(embed=embed, view=self)
            except Exception:
                pass


class DoubleOrNothingView(discord.ui.View):
    def __init__(
        self,
        ctx: commands.Context,
        cog: "CoinFlip",
        user_id: int,
        initial_bet: int,
        current_pool: int,
        lucky_side_match: bool,
        user_choice: str
    ):
        super().__init__(timeout=30.0)
        self.ctx = ctx
        self.cog = cog
        self.user_id = user_id
        self.initial_bet = initial_bet
        self.current_pool = current_pool
        self.lucky_side_match = lucky_side_match
        self.user_choice = user_choice
        self.message: Optional[discord.Message] = None
        self.collected = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt cược của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="💰 Nhận thưởng", style=discord.ButtonStyle.success, custom_id="cf_collect")
    async def collect(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.collect_reward()

    @discord.ui.button(label="🎲 Double or Nothing", style=discord.ButtonStyle.primary, custom_id="cf_double")
    async def double_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        await self.cog.play_double_round(self.ctx, self)

    async def collect_reward(self):
        if self.collected:
            return
        self.collected = True
        self.stop()

        # Add winnings back to wallet
        self.cog.economy.add_money(self.user_id, self.current_pool)
        log_wallet_change(logger, event="coinflip_double_collect", user_id=self.user_id, money_delta=self.current_pool, ctx=self.ctx)

        # Update stats
        stats = self.cog.economy.get_coinflip(self.user_id)
        new_plays = stats["plays"] + 1
        new_wins = stats["wins"] + 1
        new_streak = stats["streak"] + 1
        new_max_streak = max(stats["max_streak"], new_streak)
        net_profit = self.current_pool - self.initial_bet
        new_profit = stats["profit"] + net_profit
        new_max_win = max(stats["max_win_amount"], self.current_pool)
        
        new_achievements = list(stats["achievements"])
        newly_unlocked = check_and_unlock_achievements(
            {**stats, "plays": new_plays, "wins": new_wins, "streak": new_streak},
            self.initial_bet
        )
        new_achievements.extend(newly_unlocked)

        self.cog.economy.update_coinflip(
            self.user_id,
            plays=1,
            wins=1,
            profit=net_profit,
            streak=new_streak,
            max_streak=new_max_streak,
            max_win_amount=new_max_win,
            achievements=new_achievements
        )

        embed = make_embed(
            title="🏆 CHỐT LỜI THÀNH CÔNG!",
            description=(
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💰 **Tiền mang về:** `{self.current_pool:,} VNĐ`\n"
                f"📈 **Lợi nhuận ròng:** `+{net_profit:,} VNĐ`\n"
                f"🔥 **Chuỗi thắng hiện tại:** `{new_streak}`"
            ),
            color=discord.Color.gold()
        )
        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

        # Update message
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(content=None, embed=embed, view=self)
            except discord.HTTPException:
                pass

    async def on_timeout(self):
        if not self.collected:
            await self.collect_reward()


class CoinFlip(commands.Cog, name="CoinFlip"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()

    @commands.command(
        brief="Chơi Tung Đồng Xu 50/50 bằng nút bấm.",
        usage="coinflip / cf [tiền cược]",
        aliases=["cf"]
    )
    async def coinflip(self, ctx: commands.Context, bet_amount_str: str = None):
        user_id = ctx.author.id
        
        if bet_amount_str is None:
            view = CoinFlipLobbyView(self, user_id)
            embed = make_embed(
                title="🪙 SẢNH CHỜ COIN FLIP",
                description=(
                    "Dự đoán mặt sấp hay ngửa của đồng xu để nhân đôi tiền cược!\n\n"
                    "👉 **Cú pháp chơi:** `i?cf <tiền cược>`\n"
                    "👉 **Ví dụ:** `i?cf 100k` hoặc `i?cf all` (tất tay)\n\n"
                    "Chọn một nút bấm dưới đây để xem chỉ số của bạn:"
                ),
                color=discord.Color.blue()
            )
            embed.set_footer(text="🎰 Casino Bot • Tung Đồng Xu")
            view.message = await ctx.send(embed=embed, view=view)
            return

        current_money = self.economy.get_entry(user_id)[1]
        
        # Parse Bet Amount
        bet_amount = parse_bet_amount(bet_amount_str, current_money)
        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 VNĐ.")
            return

        try:
            # Validate and deduct money
            validate_money_bet(self.economy, user_id, bet_amount)
            self.economy.add_money(user_id, -bet_amount)
            log_wallet_change(logger, event="coinflip_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
        except Exception as e:
            await ctx.send(f"❌ {e}")
            return

        # Show cược options view
        view = CoinFlipPlayView(ctx, self, user_id, bet_amount)
        embed = make_embed(
            title="🪙 TRÒ CHƠI COIN FLIP - CỬA CƯỢC",
            description=(
                f"👤 **Người chơi:** {ctx.author.mention}\n"
                f"💵 **Tiền cược:** `{bet_amount:,} VNĐ`\n\n"
                f"Hãy chọn cửa cược hoặc chế độ phụ ở bên dưới:"
            ),
            color=discord.Color.blue()
        )
        view.message = await ctx.send(embed=embed, view=view)

    async def play_regular_flip(self, ctx: commands.Context, user_choice: str, user_choice_vn: str, bet_amount: int, play_msg: discord.Message):
        user_id = ctx.author.id
        
        # Determine Lucky Side of the day
        lucky_side = get_user_lucky_side(user_id)
        lucky_side_vn = "🦅 NGỬA (Heads)" if lucky_side == "heads" else "🌸 SẤP (Tails)"

        # Animation message edits
        await play_msg.edit(content="🪙 **Đồng xu được tung lên...**\n⬆️", embed=None, view=None)
        await asyncio.sleep(0.8)
        await play_msg.edit(content="🪙 **Đồng xu được tung lên...**\n⬆️\n⬆️")
        await asyncio.sleep(0.8)
        await play_msg.edit(content="🪙 **Đồng xu được tung lên...**\n⬆️\n⬆️\n⬆️")
        await asyncio.sleep(0.8)

        # Outcome based on win rate
        is_win = random.random() < COINFLIP_WIN_RATE
        if is_win:
            coin_result = user_choice
        else:
            coin_result = "tails" if user_choice == "heads" else "heads"
        coin_result_vn = "🦅 NGỬA" if coin_result == "heads" else "🌸 SẤP"

        if coin_result == user_choice:
            # User Won
            lucky_match = (user_choice == lucky_side)
            multiplier = 2.2 if lucky_match else 2.0
            winnings = int(bet_amount * multiplier)
            
            desc = (
                f"Kết quả: **{coin_result_vn}**\n"
                f"Bạn chọn: **{user_choice_vn}**\n\n"
                f"🏆 **Bạn thắng!**\n"
            )
            if lucky_match:
                desc += f"🍀 Trùng **Lucky Side** hôm nay ({lucky_side_vn})! Nhận **x2.2** thưởng!\n"
            desc += f"💰 Tiền thắng: `+{winnings:,} VNĐ`"
            
            embed = make_embed(
                title="🪙 COIN FLIP - CHIẾN THẮNG!",
                description=desc,
                color=discord.Color.green()
            )
            
            view = DoubleOrNothingView(
                ctx=ctx,
                cog=self,
                user_id=user_id,
                initial_bet=bet_amount,
                current_pool=winnings,
                lucky_side_match=lucky_match,
                user_choice=user_choice
            )
            await play_msg.edit(content=None, embed=embed, view=view)
            view.message = play_msg
        else:
            # User Lost
            desc = (
                f"Kết quả: **{coin_result_vn}**\n"
                f"Bạn chọn: **{user_choice_vn}**\n\n"
                f"❌ **Bạn thua!**\n"
                f"💸 Tiền mất: `-{bet_amount:,} VNĐ`"
            )
            embed = make_embed(
                title="🪙 COIN FLIP - THẤT BẠI!",
                description=desc,
                color=discord.Color.red()
            )
            
            # Save loss stats
            stats = self.economy.get_coinflip(user_id)
            new_plays = stats["plays"] + 1
            new_losses = stats["losses"] + 1
            new_profit = stats["profit"] - bet_amount
            
            new_achievements = list(stats["achievements"])
            newly_unlocked = check_and_unlock_achievements(
                {**stats, "plays": new_plays, "losses": new_losses, "streak": 0},
                bet_amount
            )
            new_achievements.extend(newly_unlocked)

            self.economy.update_coinflip(
                user_id,
                plays=1,
                losses=1,
                profit=-bet_amount,
                streak=0,
                achievements=new_achievements
            )

            if newly_unlocked:
                achievement_texts = "\n".join([f"✨ **{ACHIEVEMENTS[a]}**" for a in newly_unlocked])
                embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

            await play_msg.edit(content=None, embed=embed, view=None)

    async def play_double_coin_flip(self, ctx: commands.Context, choice1: str, choice2: str, choice_vn: str, bet_amount: int, play_msg: discord.Message):
        user_id = ctx.author.id
        
        # Animation edits
        await play_msg.edit(content="🪙🪙 **Cả hai đồng xu đang bay lên...**\n⬆️ ⬆️", embed=None, view=None)
        await asyncio.sleep(1.0)

        is_win = random.random() < DOUBLECOIN_WIN_RATE
        if is_win:
            coin1_res = choice1
            coin2_res = choice2
        else:
            # Pick a losing combination
            outcomes = [("heads", "heads"), ("heads", "tails"), ("tails", "heads"), ("tails", "tails")]
            outcomes.remove((choice1, choice2))
            coin1_res, coin2_res = random.choice(outcomes)
        
        c1_res_vn = "🦅 NGỬA" if coin1_res == "heads" else "🌸 SẤP"
        c2_res_vn = "🦅 NGỬA" if coin2_res == "heads" else "🌸 SẤP"

        if is_win:
            winnings = bet_amount * 4
            self.economy.add_money(user_id, winnings)
            log_wallet_change(logger, event="doublecoin_win", user_id=user_id, money_delta=winnings, ctx=ctx)

            desc = (
                f"Kết quả:\n"
                f"• Đồng xu 1: **{c1_res_vn}**\n"
                f"• Đồng xu 2: **{c2_res_vn}**\n\n"
                f"Dự đoán của bạn: **{choice_vn}**\n\n"
                f"🏆 **BẠN THẮNG X4 THƯỞNG!**\n"
                f"💰 Tiền thắng: `+{winnings:,} VNĐ`"
            )
            embed = make_embed(
                title="🪙🪙 DOUBLE COIN - THẮNG LỚN!",
                description=desc,
                color=discord.Color.green()
            )
            
            stats = self.economy.get_coinflip(user_id)
            new_plays = stats["plays"] + 1
            new_wins = stats["wins"] + 1
            new_streak = stats["streak"] + 1
            new_max_streak = max(stats["max_streak"], new_streak)
            new_profit = stats["profit"] + (winnings - bet_amount)
            new_max_win = max(stats["max_win_amount"], winnings)
            
            new_achievements = list(stats["achievements"])
            newly_unlocked = check_and_unlock_achievements(
                {**stats, "plays": new_plays, "wins": new_wins, "streak": new_streak},
                bet_amount
            )
            new_achievements.extend(newly_unlocked)

            self.economy.update_coinflip(
                user_id,
                plays=1,
                wins=1,
                profit=(winnings - bet_amount),
                streak=new_streak,
                max_streak=new_max_streak,
                max_win_amount=new_max_win,
                achievements=new_achievements
            )
        else:
            desc = (
                f"Kết quả:\n"
                f"• Đồng xu 1: **{c1_res_vn}**\n"
                f"• Đồng xu 2: **{c2_res_vn}**\n\n"
                f"Dự đoán của bạn: **{choice_vn}**\n\n"
                f"❌ **BẠN THUA!**\n"
                f"💸 Tiền mất: `-{bet_amount:,} VNĐ`"
            )
            embed = make_embed(
                title="🪙🪙 DOUBLE COIN - THẤT BẠI!",
                description=desc,
                color=discord.Color.red()
            )
            
            stats = self.economy.get_coinflip(user_id)
            new_plays = stats["plays"] + 1
            new_losses = stats["losses"] + 1
            new_profit = stats["profit"] - bet_amount
            
            new_achievements = list(stats["achievements"])
            newly_unlocked = check_and_unlock_achievements(
                {**stats, "plays": new_plays, "losses": new_losses, "streak": 0},
                bet_amount
            )
            new_achievements.extend(newly_unlocked)

            self.economy.update_coinflip(
                user_id,
                plays=1,
                losses=1,
                profit=-bet_amount,
                streak=0,
                achievements=new_achievements
            )

        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

        await play_msg.edit(content=None, embed=embed, view=None)

    async def play_double_round(self, ctx: commands.Context, previous_view: DoubleOrNothingView):
        user_id = previous_view.user_id
        old_pool = previous_view.current_pool
        initial_bet = previous_view.initial_bet
        play_msg = previous_view.message

        # Double animation edits
        await play_msg.edit(content=f"🎲 **Đang Double... Cược tiếp tất cả `{old_pool:,} VNĐ`!**\n🪙 Tung đồng xu...", embed=None, view=None)
        await asyncio.sleep(0.8)
        await play_msg.edit(content=f"🎲 **Đang Double... Cược tiếp tất cả `{old_pool:,} VNĐ`!**\n🪙 Tung đồng xu...\n⬆️")
        await asyncio.sleep(0.8)
        await play_msg.edit(content=f"🎲 **Đang Double... Cược tiếp tất cả `{old_pool:,} VNĐ`!**\n🪙 Tung đồng xu...\n⬆️\n⬆️")
        await asyncio.sleep(0.8)

        # Flip again based on win rate
        is_win = random.random() < DOUBLE_ROUND_WIN_RATE
        if is_win:
            coin_result = user_choice
        else:
            coin_result = "tails" if user_choice == "heads" else "heads"
        user_choice = previous_view.user_choice
        user_choice_vn = "🦅 NGỬA (Heads)" if user_choice == "heads" else "🌸 SẤP (Tails)"
        coin_result_vn = "🦅 NGỬA" if coin_result == "heads" else "🌸 SẤP"

        if coin_result == user_choice:
            new_pool = old_pool * 2
            desc = (
                f"Kết quả: **{coin_result_vn}**\n"
                f"Bạn chọn: **{user_choice_vn}**\n\n"
                f"🏆 **DOUBLE THÀNH CÔNG!**\n"
                f"💰 Bể thưởng hiện tại: `{new_pool:,} VNĐ`\n\n"
                f"Bạn muốn tiếp tục Double hay chốt lời?"
            )
            embed = make_embed(
                title="🎲 COIN FLIP - DOUBLE UP!",
                description=desc,
                color=discord.Color.green()
            )
            
            next_view = DoubleOrNothingView(
                ctx=ctx,
                cog=self,
                user_id=user_id,
                initial_bet=initial_bet,
                current_pool=new_pool,
                lucky_side_match=previous_view.lucky_side_match,
                user_choice=user_choice
            )
            await play_msg.edit(content=None, embed=embed, view=next_view)
            next_view.message = play_msg
        else:
            desc = (
                f"Kết quả: **{coin_result_vn}**\n"
                f"Bạn chọn: **{user_choice_vn}**\n\n"
                f"💥 **THẤT BẠI!** Bạn mất sạch toàn bộ chuỗi cược Double!\n"
                f"💸 Tiền mất: `-{initial_bet:,} VNĐ`"
            )
            embed = make_embed(
                title="💥 COIN FLIP - MẤT TRẮNG!",
                description=desc,
                color=discord.Color.red()
            )
            
            stats = self.economy.get_coinflip(user_id)
            new_plays = stats["plays"] + 1
            new_losses = stats["losses"] + 1
            new_profit = stats["profit"] - initial_bet
            
            new_achievements = list(stats["achievements"])
            newly_unlocked = check_and_unlock_achievements(
                {**stats, "plays": new_plays, "losses": new_losses, "streak": 0},
                initial_bet
            )
            new_achievements.extend(newly_unlocked)

            self.economy.update_coinflip(
                user_id,
                plays=1,
                losses=1,
                profit=-initial_bet,
                streak=0,
                achievements=new_achievements
            )

            if newly_unlocked:
                achievement_texts = "\n".join([f"✨ **{ACHIEVEMENTS[a]}**" for a in newly_unlocked])
                embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

            await play_msg.edit(content=None, embed=embed, view=None)


async def setup(bot: commands.Bot):
    await bot.add_cog(CoinFlip(bot))
