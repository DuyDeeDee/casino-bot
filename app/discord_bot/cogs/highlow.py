import asyncio
from io import BytesIO
import hashlib
import json
import logging
import random
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from PIL import Image, ImageDraw

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.card import Card
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, ABS_PATH
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

def render_compact_cards(history: list[Card], show_facedown: bool) -> BytesIO:
    card_w = 72
    card_h = 96
    gap = 24
    
    # We display up to the last 5 cards in history
    display_history = history[-5:] if len(history) > 5 else history
    
    num_cards = len(display_history)
    if show_facedown:
        num_cards += 1
        
    width = num_cards * card_w + (num_cards - 1) * gap
    height = card_h
    
    # Create fully transparent canvas
    bg = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    
    x = 0
    for i, card in enumerate(display_history):
        with Image.open(ABS_PATH / "modules" / "cards" / card.image) as img:
            card_img = img.convert("RGBA").resize((card_w, card_h), Image.Resampling.LANCZOS)
            bg.alpha_composite(card_img, (x, 0))
            card_img.close()
            
        x += card_w
        if i < num_cards - 1:
            draw = ImageDraw.Draw(bg)
            # Draw a sleek right-pointing arrow polygon in the center of the gap
            draw.polygon([
                (x + 6, height // 2 - 6),
                (x + 18, height // 2),
                (x + 6, height // 2 + 6)
            ], fill=(200, 200, 200, 255))
            x += gap
            
    if show_facedown:
        with Image.open(ABS_PATH / "modules" / "cards" / "red_back.png") as img:
            card_img = img.convert("RGBA").resize((card_w, card_h), Image.Resampling.LANCZOS)
            bg.alpha_composite(card_img, (x, 0))
            card_img.close()
            
    output = BytesIO()
    bg.save(output, format="PNG")
    output.seek(0)
    bg.close()
    return output

# Classic Mode Multipliers
CLASSIC_MULTIPLIERS = [1.0, 1.5, 2.2, 3.3, 5.0, 7.5, 11.0, 16.0, 25.0]

HIGHLOW_ACHIEVEMENTS = {
    "first_play": "🏅 Chơi High & Low lần đầu (Chơi ván đầu tiên)",
    "streak_5": "🎯 Đoán đúng 5 lần liên tiếp (Đạt chuỗi 5)",
    "streak_10": "🎯 Đoán đúng 10 lần liên tiếp (Đạt chuỗi 10)",
    "cashout_20x": "👑 Cash Out 20x (Cash Out với hệ số >= 20.0x)",
    "win_10m": "💰 Thắng 10 triệu (Thắng >= 10,000,000 VNĐ trong 1 ván)",
    "streak_15": "🔥 Chuỗi thắng 15 lá (Đoán đúng 15 lần liên tiếp)",
    "lucky_card_match": "🍀 Lá bài may mắn (Rút trúng Lucky Card của ngày)",
}

VIP_TIERS = [
    {"name": "Bronze", "title": "Người Mới", "req_plays": 0},
    {"name": "Silver", "title": "Thợ Đoán", "req_plays": 10},
    {"name": "Gold", "title": "Cao Thủ High & Low", "req_plays": 50},
    {"name": "Diamond", "title": "Vua Bài", "req_plays": 150},
    {"name": "Master", "title": "Huyền Thoại Casino", "req_plays": 300},
    {"name": "Grand Master", "title": "Thần Bài Vô Song", "req_plays": 500},
]


def parse_bet_amount(val_str: str, current_money: int) -> int:
    val_str = val_str.strip().lower()
    if val_str in ["all", "allin", "all-in", "tất tay"]:
        from app.discord_bot.modules.betting import get_capped_all_in_amount
        return get_capped_all_in_amount(current_money)

    val_str = val_str.replace(",", "").replace(".", "")

    multiplier = 1
    if val_str.endswith("k"):
        multiplier = 1_000
        val_str = val_str[:-1].strip()
    elif val_str.endswith("m"):
        multiplier = 1_000_000
        val_str = val_str[:-1].strip()

    try:
        return int(float(val_str) * multiplier)
    except ValueError:
        return 0


def get_daily_lucky_card() -> str:
    """Returns a deterministic lucky card value rank based on current day (UTC)."""
    today_str = datetime.utcnow().strftime("%Y-%m-%d")
    h = hashlib.sha256(today_str.encode()).hexdigest()
    values = ["2", "3", "4", "5", "6", "7", "8", "9", "10", "jack", "queen", "king", "ace"]
    val_index = int(h, 16) % len(values)
    return values[val_index]


def get_lucky_card_display(card_name: str) -> str:
    val_display = {
        "2": "2", "3": "3", "4": "4", "5": "5", "6": "6", "7": "7", "8": "8", "9": "9", "10": "10",
        "jack": "J", "queen": "Q", "king": "K", "ace": "A"
    }
    return val_display.get(card_name, card_name.title())


def calculate_dynamic_multiplier(current_card_value: int, guess_high: bool) -> float:
    """
    Calculates dynamic multiplier based on winning probability.
    Card values: 2 to 14 (Ace is 14)
    """
    if guess_high:
        ranks_higher = 14 - current_card_value
        if ranks_higher == 0:
            return 0.0
        prob = ranks_higher / 12.0
    else:
        ranks_lower = current_card_value - 2
        if ranks_lower == 0:
            return 0.0
        prob = ranks_lower / 12.0

    factor = 0.90 / prob  # 10% house edge
    return max(1.05, round(factor, 2))


def get_user_vip(stats: dict) -> dict:
    plays = stats.get("plays", 0)
    streak = stats.get("max_streak", 0)
    max_mult = stats.get("max_multiplier", 0.0)

    # Calculate VIP tier based on plays or exceptional feats
    if plays >= 500 or streak >= 12 or max_mult >= 50.0:
        return VIP_TIERS[5]  # Grand Master
    if plays >= 300 or streak >= 10 or max_mult >= 25.0:
        return VIP_TIERS[4]  # Master
    if plays >= 150 or streak >= 8:
        return VIP_TIERS[3]  # Diamond
    if plays >= 50 or streak >= 5:
        return VIP_TIERS[2]  # Gold
    if plays >= 10:
        return VIP_TIERS[1]  # Silver
    return VIP_TIERS[0]  # Bronze


def check_and_unlock_highlow_achievements(stats: dict, game_info: dict) -> list[str]:
    unlocked = set(stats.get("achievements", []))
    newly_unlocked = []

    plays = stats.get("plays", 0) + 1

    if plays >= 1 and "first_play" not in unlocked:
        newly_unlocked.append("first_play")

    streak = game_info.get("streak", 0)
    if streak >= 5 and "streak_5" not in unlocked:
        newly_unlocked.append("streak_5")
    if streak >= 10 and "streak_10" not in unlocked:
        newly_unlocked.append("streak_10")
    if streak >= 15 and "streak_15" not in unlocked:
        newly_unlocked.append("streak_15")

    multiplier = game_info.get("multiplier", 1.0)
    if multiplier >= 20.0 and "cashout_20x" not in unlocked:
        newly_unlocked.append("cashout_20x")

    profit = game_info.get("profit", 0)
    if profit >= 10_000_000 and "win_10m" not in unlocked:
        newly_unlocked.append("win_10m")

    if game_info.get("lucky_card_match", False) and "lucky_card_match" not in unlocked:
        newly_unlocked.append("lucky_card_match")

    return newly_unlocked


class HighLowLobbyView(discord.ui.View):
    def __init__(self, cog: "HighLow", user_id: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.user_id = user_id
        self.message = None

    @discord.ui.button(label="📊 Thống kê", style=discord.ButtonStyle.primary, emoji="📊")
    async def stats_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải yêu cầu của bạn!", ephemeral=True)
            return

        stats = self.cog.economy.get_highlow_stats(self.user_id)
        plays = stats["plays"]
        wins = stats["wins"]
        losses = stats["losses"]
        profit = stats["profit"]
        streak = stats["streak"]
        max_streak = stats["max_streak"]
        max_mult = stats["max_multiplier"]
        achievements_list = stats["achievements"]
        vip = get_user_vip(stats)

        win_rate = (wins / plays * 100) if plays > 0 else 0.0
        profit_sign = "+" if profit >= 0 else ""

        desc = (
            f"👑 **Danh hiệu:** `{vip['title']}` ({vip['name']})\n"
            f"🃏 **Số ván đã chơi:** `{plays}`\n"
            f"🏆 **Số ván thắng:** `{wins}`\n"
            f"❌ **Số ván thua:** `{losses}`\n"
            f"📈 **Tỷ lệ thắng:** `{win_rate:.1f}%`\n"
            f"🔥 **Chuỗi đoán đúng dài nhất:** `{max_streak}`\n"
            f"🔥 **Chuỗi đoán đúng hiện tại:** `{streak}`\n"
            f"🔝 **Hệ số Cash Out cao nhất:** `{max_mult:.2f}x`\n"
            f"💸 **Tổng lợi nhuận:** `{profit_sign}{profit:,} VNĐ`\n"
        )
        embed = make_embed(
            title=f"📊 THỐNG KÊ HIGH & LOW - {interaction.user.name.upper()}",
            description=desc,
            color=discord.Color.purple()
        )
        if achievements_list:
            ach_texts = "\n".join([f"✨ {HIGHLOW_ACHIEVEMENTS[a]}" for a in achievements_list if a in HIGHLOW_ACHIEVEMENTS])
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value=ach_texts, inline=False)
        else:
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value="*Chưa mở khóa thành tựu nào*", inline=False)

        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏆 Xếp hạng", style=discord.ButtonStyle.secondary, emoji="🏆")
    async def rank_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải yêu cầu của bạn!", ephemeral=True)
            return

        self.cog.economy.cur.execute(
            "SELECT user_id, profit, max_multiplier, max_streak, plays FROM user_highlow ORDER BY profit DESC LIMIT 10"
        )
        rows = self.cog.economy.cur.fetchall()
        if not rows:
            await interaction.response.send_message("ℹ️ Chưa có ai xếp hạng High & Low.", ephemeral=True)
            return

        desc = ""
        for i, row in enumerate(rows, 1):
            u_id, profit, max_mult, max_streak, plays = row
            member = interaction.guild.get_member(u_id)
            name = member.name if member else f"ID: {u_id}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            profit_sign = "+" if profit >= 0 else ""
            desc += (
                f"{medal} **{name}** • Lợi nhuận: `{profit_sign}{profit:,} VNĐ` "
                f"• Chuỗi: `{max_streak}` • Max Mult: `{max_mult:.2f}x` *(Lượt: {plays})*\n"
            )

        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG CAO THỦ HIGH & LOW",
            description=desc,
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_timeout(self):
        if self.message:
            try:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(view=self)
            except Exception:
                pass


class HighLowModeSelectionView(discord.ui.View):
    def __init__(self, cog: "HighLow", ctx: commands.Context, bet_amount: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.user_id = ctx.author.id
        self.bet_amount = bet_amount
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Cổ điển (Classic)", style=discord.ButtonStyle.primary, emoji="🃏")
    async def classic_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.start_game("classic")

    @discord.ui.button(label="Thử thách Chuỗi (Streak)", style=discord.ButtonStyle.secondary, emoji="🎯")
    async def streak_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        view = HighLowStreakTargetView(self.cog, self.ctx, self.bet_amount)
        view.message = self.message
        
        embed = make_embed(
            title="🎯 CHỌN MỤC TIÊU THỬ THÁCH",
            description=(
                f"Hãy chọn mục tiêu đoán đúng liên tiếp của bạn:\n\n"
                f"• **3 Lượt**: Hoàn thành nhân thêm **1.05x**\n"
                f"• **5 Lượt**: Hoàn thành nhân thêm **1.10x**\n"
                f"• **7 Lượt**: Hoàn thành nhân thêm **1.15x**\n"
                f"• **10 Lượt**: Hoàn thành nhân thêm **1.20x**\n\n"
                f"⚠️ *Nếu dừng trước mục tiêu, chỉ nhận hệ số thường. Nếu đoán sai trước mục tiêu, bạn mất tất cả.*"
            ),
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Hardcore (Sinh tử)", style=discord.ButtonStyle.danger, emoji="🔥")
    async def hardcore_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.start_game("hardcore")

    async def start_game(self, mode: str, streak_target: Optional[int] = None):
        self.stop()
        self.cog.active_users.add(self.user_id)
        
        try:
            self.cog.economy.add_money(self.user_id, -self.bet_amount)
            log_wallet_change(logger, event="highlow_bet", user_id=self.user_id, money_delta=-self.bet_amount, ctx=self.ctx)
        except Exception as e:
            self.cog.active_users.discard(self.user_id)
            await self.ctx.send(f"❌ Lỗi trừ tiền: {e}")
            return

        game_view = HighLowGameView(self.cog, self.ctx, self.bet_amount, mode, streak_target)
        game_view.message = self.message
        await game_view.initialize_game()

    async def on_timeout(self):
        if self.message:
            try:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(content="💤 Hết thời gian chọn chế độ.", view=self)
            except Exception:
                pass


class HighLowStreakTargetView(discord.ui.View):
    def __init__(self, cog: "HighLow", ctx: commands.Context, bet_amount: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.user_id = ctx.author.id
        self.bet_amount = bet_amount
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="3 Lượt (3.5x)", style=discord.ButtonStyle.primary)
    async def target_3(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.start_game(3)

    @discord.ui.button(label="5 Lượt (8.5x)", style=discord.ButtonStyle.primary)
    async def target_5(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.start_game(5)

    @discord.ui.button(label="7 Lượt (18.0x)", style=discord.ButtonStyle.primary)
    async def target_7(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.start_game(7)

    @discord.ui.button(label="10 Lượt (45.0x)", style=discord.ButtonStyle.primary)
    async def target_10(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.start_game(10)

    @discord.ui.button(label="⬅️ Quay lại", style=discord.ButtonStyle.secondary)
    async def back_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        view = HighLowModeSelectionView(self.cog, self.ctx, self.bet_amount)
        view.message = self.message
        
        embed = make_embed(
            title="🎮 CHỌN CHẾ ĐỘ CHƠI HIGH & LOW",
            description=(
                f"Hãy chọn chế độ bạn muốn thử thách:\n\n"
                f"• 🃏 **Cổ điển (Classic)**: Hệ số thay đổi linh hoạt theo tỷ lệ thực của lá bài hiện tại. Cash out bất kỳ lúc nào.\n"
                f"• 🎯 **Thử thách Chuỗi**: Đặt mục tiêu chuỗi đoán đúng để ăn thêm bonus.\n"
                f"• 🔥 **Hardcore**: Đoán đúng liên tục 10 lá để nhận bonus x1.3, không thể cash out giữa chừng."
            ),
            color=discord.Color.purple()
        )
        await interaction.response.edit_message(embed=embed, view=view)

    async def start_game(self, target: int):
        self.stop()
        self.cog.active_users.add(self.user_id)
        try:
            self.cog.economy.add_money(self.user_id, -self.bet_amount)
            log_wallet_change(logger, event="highlow_bet", user_id=self.user_id, money_delta=-self.bet_amount, ctx=self.ctx)
        except Exception as e:
            self.cog.active_users.discard(self.user_id)
            await self.ctx.send(f"❌ Lỗi trừ tiền: {e}")
            return

        game_view = HighLowGameView(self.cog, self.ctx, self.bet_amount, "streak_challenge", target)
        game_view.message = self.message
        await game_view.initialize_game()

    async def on_timeout(self):
        if self.message:
            try:
                for child in self.children:
                    child.disabled = True
                await self.message.edit(content="💤 Hết thời gian chọn mục tiêu.", view=self)
            except Exception:
                pass


class HighLowGameView(discord.ui.View):
    def __init__(self, cog: "HighLow", ctx: commands.Context, bet_amount: int, mode: str, streak_target: Optional[int] = None):
        super().__init__(timeout=90.0)
        self.cog = cog
        self.ctx = ctx
        self.user_id = ctx.author.id
        self.bet_amount = bet_amount
        self.mode = mode
        self.streak_target = streak_target
        self.message = None

        # Build full deck
        self.deck = []
        for suit in Card.suits:
            for val in range(2, 15):
                self.deck.append(Card(suit, val))
        random.shuffle(self.deck)

        self.history = []
        self.current_card = self.deck.pop()
        self.history.append(self.current_card)

        self.multiplier = 1.0
        self.streak = 0
        self.lucky_card_match = False
        self.daily_lucky_val = get_daily_lucky_card()
        
        # Check if initial card matches lucky card
        if self.current_card.name == self.daily_lucky_val:
            self.lucky_card_match = True

        # Build UI buttons dynamically
        self.btn_high = discord.ui.Button(label="Cao hơn", style=discord.ButtonStyle.primary, emoji="⬆️", row=0)
        self.btn_low = discord.ui.Button(label="Thấp hơn", style=discord.ButtonStyle.primary, emoji="⬇️", row=0)
        
        self.btn_red = discord.ui.Button(label="Đỏ", style=discord.ButtonStyle.danger, emoji="🔴", row=1)
        self.btn_black = discord.ui.Button(label="Đen", style=discord.ButtonStyle.secondary, emoji="⚫", row=1)

        self.btn_clubs = discord.ui.Button(label="Chuồn ♣", style=discord.ButtonStyle.success, row=2)
        self.btn_diamonds = discord.ui.Button(label="Rô ♦", style=discord.ButtonStyle.success, row=2)
        self.btn_hearts = discord.ui.Button(label="Cơ ♥", style=discord.ButtonStyle.success, row=2)
        self.btn_spades = discord.ui.Button(label="Bích ♠", style=discord.ButtonStyle.success, row=2)

        self.btn_cashout = discord.ui.Button(label="Cash Out", style=discord.ButtonStyle.success, emoji="💰", row=3)

        # Callbacks
        self.btn_high.callback = lambda i: self.process_guess(i, "high")
        self.btn_low.callback = lambda i: self.process_guess(i, "low")
        self.btn_red.callback = lambda i: self.process_guess(i, "red")
        self.btn_black.callback = lambda i: self.process_guess(i, "black")
        self.btn_clubs.callback = lambda i: self.process_guess(i, "clubs")
        self.btn_diamonds.callback = lambda i: self.process_guess(i, "diamonds")
        self.btn_hearts.callback = lambda i: self.process_guess(i, "hearts")
        self.btn_spades.callback = lambda i: self.process_guess(i, "spades")
        self.btn_cashout.callback = self.cash_out

        # Add buttons to view
        self.add_item(self.btn_high)
        self.add_item(self.btn_low)
        self.add_item(self.btn_red)
        self.add_item(self.btn_black)
        self.add_item(self.btn_clubs)
        self.add_item(self.btn_diamonds)
        self.add_item(self.btn_hearts)
        self.add_item(self.btn_spades)
        self.add_item(self.btn_cashout)

        self.update_button_states()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True

    def update_button_states(self):
        self.btn_high.disabled = (self.current_card.value == 14)
        self.btn_low.disabled = (self.current_card.value == 2)
        
        payout_current = int(self.bet_amount * self.multiplier)
        
        # 1. High/Low labels with diffs
        if not self.btn_high.disabled:
            factor_high = calculate_dynamic_multiplier(self.current_card.value, True)
            payout_high = int(self.bet_amount * round(self.multiplier * factor_high, 2))
            diff_high = payout_high - payout_current
            self.btn_high.label = f"Cao hơn (+{diff_high:,})"
        else:
            self.btn_high.label = "Cao hơn"
            
        if not self.btn_low.disabled:
            factor_low = calculate_dynamic_multiplier(self.current_card.value, False)
            payout_low = int(self.bet_amount * round(self.multiplier * factor_low, 2))
            diff_low = payout_low - payout_current
            self.btn_low.label = f"Thấp hơn (+{diff_low:,})"
        else:
            self.btn_low.label = "Thấp hơn"
            
        # 2. Red/Black labels with diffs
        payout_red_black = int(self.bet_amount * round(self.multiplier * 1.90, 2))
        diff_red_black = payout_red_black - payout_current
        self.btn_red.label = f"Đỏ (+{diff_red_black:,})"
        self.btn_black.label = f"Đen (+{diff_red_black:,})"
        
        # 3. Suits labels with diffs
        payout_suit = int(self.bet_amount * round(self.multiplier * 3.6, 2))
        diff_suit = payout_suit - payout_current
        self.btn_clubs.label = f"Chuồn (+{diff_suit:,})"
        self.btn_diamonds.label = f"Rô (+{diff_suit:,})"
        self.btn_hearts.label = f"Cơ (+{diff_suit:,})"
        self.btn_spades.label = f"Bích (+{diff_suit:,})"
        
        if self.mode == "hardcore":
            self.btn_cashout.disabled = True
            self.btn_cashout.label = "Hardcore (Không Cash Out)"
        else:
            self.btn_cashout.disabled = (self.streak == 0)
            self.btn_cashout.label = f"Cash Out ({payout_current:,} VNĐ)"

    async def initialize_game(self):
        await self.render_and_send()

    async def render_and_send(self, is_final: bool = False, msg_suffix: str = ""):
        loop = asyncio.get_event_loop()
        card_bytes = await loop.run_in_executor(
            None,
            render_compact_cards,
            self.history,
            not is_final,
        )

        file = discord.File(card_bytes, filename="highlow.png")
        
        mode_names = {
            "classic": "🃏 Cổ điển",
            "hardcore": "🔥 Hardcore (10 lượt)",
            "streak_challenge": f"🎯 Thử thách Chuỗi ({self.streak_target} lượt)"
        }
        
        target_info = "Bất kỳ lúc nào"
        if self.mode == "hardcore":
            target_info = "Phải đoán đúng 10 lượt liên tiếp"
        elif self.mode == "streak_challenge":
            target_info = f"Đoán đúng {self.streak_target} lượt"

        lucky_display = get_lucky_card_display(self.daily_lucky_val)
        lucky_status = " (ĐÃ KÍCH HOẠT! +10% Lợi nhuận)" if self.lucky_card_match else ""

        desc = (
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ` | "
            f"🔥 **Chuỗi đoán đúng:** `{self.streak}`\n"
            f"🎯 **Yêu cầu:** `{target_info}` | "
            f"🍀 **Lucky Card:** `{lucky_display}`{lucky_status}\n"
            f"⚡ **Hệ số:** `{self.multiplier:.2f}x` | "
            f"💰 **Cash Out:** `{int(self.bet_amount * self.multiplier):,} VNĐ`\n\n"
            f"**Lá bài hiện tại:** `{self.current_card}`\n"
        )
        if msg_suffix:
            desc += f"\n{msg_suffix}"

        embed = make_embed(
            title=f"🃏 {self.ctx.author.name} is playing High & Low",
            description=desc,
            color=discord.Color.purple()
        )
        embed.set_image(url="attachment://highlow.png")

        if is_final:
            embed.set_footer(text="Sylus Meow • Trò chơi kết thúc.")
            await self.message.edit(embed=embed, attachments=[file], view=None)
        else:
            embed.set_footer(text="Lá tiếp theo sẽ cao hơn hay thấp hơn?")
            await self.message.edit(embed=embed, attachments=[file], view=self)

    async def process_guess(self, interaction: discord.Interaction, guess: str):
        await interaction.response.defer()
        
        next_card = self.deck.pop()

        if next_card.value == self.current_card.value:
            self.history.append(next_card)
            self.current_card = next_card
            await self.conclude_game(win=False, suffix="❌ **Lá bài trùng giá trị!** Nhà cái ăn tất. Bạn đã mất toàn bộ số tiền cược.")
            return

        is_correct = False
        is_gold_card = random.random() < 0.03

        if guess == "high":
            is_correct = (next_card.value > self.current_card.value)
        elif guess == "low":
            is_correct = (next_card.value < self.current_card.value)
        elif guess == "red":
            is_correct = (next_card.suit in ["diamonds", "hearts"])
        elif guess == "black":
            is_correct = (next_card.suit in ["clubs", "spades"])
        elif guess == "clubs":
            is_correct = (next_card.suit == "clubs")
        elif guess == "diamonds":
            is_correct = (next_card.suit == "diamonds")
        elif guess == "hearts":
            is_correct = (next_card.suit == "hearts")
        elif guess == "spades":
            is_correct = (next_card.suit == "spades")

        # Store old card value to calculate probability for current guess
        old_card_value = self.current_card.value

        self.history.append(next_card)
        self.current_card = next_card

        if next_card.name == self.daily_lucky_val:
            self.lucky_card_match = True

        if is_correct:
            self.streak += 1
            
            factor = 1.0
            if guess in ["high", "low"]:
                factor = calculate_dynamic_multiplier(old_card_value, guess == "high")
            elif guess in ["red", "black"]:
                factor = 1.90
            elif guess in ["clubs", "diamonds", "hearts", "spades"]:
                factor = 3.6
            
            if is_gold_card:
                factor = round(factor * 1.05, 2)
            
            self.multiplier = round(self.multiplier * factor, 2)

            if self.mode == "streak_challenge" and self.streak == self.streak_target:
                boost_factors = {3: 1.01, 5: 1.03, 7: 1.05, 10: 1.10}
                factor = boost_factors.get(self.streak_target, 1.0)
                self.multiplier = round(self.multiplier * factor, 2)
                await self.conclude_game(win=True, suffix=f"🎉 **Đã đạt mục tiêu chuỗi {self.streak_target} lượt! Tự động Cash Out với bonus x{factor}!**")
                return
            
            if self.mode == "hardcore" and self.streak == 10:
                self.multiplier = round(self.multiplier * 1.10, 2)
                await self.conclude_game(win=True, suffix="🔥 **CHÚC MỪNG! Bạn đã hoàn thành chế độ Hardcore 10 lượt và nhận thêm 10% bonus!**")
                return

            self.update_button_states()
            msg_suffix = "✅ **Đoán chính xác!** "
            if is_gold_card:
                msg_suffix += "✨ *Lá bài Mạ Vàng được kích hoạt (+5% hệ số lượt này)!*"
            await self.render_and_send(msg_suffix=msg_suffix)

        else:
            await self.conclude_game(win=False, suffix=f"❌ **Đoán sai!** Lá tiếp theo là `{next_card}`. Bạn đã mất toàn bộ số tiền cược.")

    async def cash_out(self, interaction: discord.Interaction):
        await interaction.response.defer()
        await self.conclude_game(win=True, suffix="💰 **Bạn đã chủ động Cash Out chốt lời thành công!**")

    async def conclude_game(self, win: bool, suffix: str):
        self.cog.active_users.discard(self.user_id)
        self.stop()
        
        payout = 0
        if win:
            payout = int(self.bet_amount * self.multiplier)
            if self.lucky_card_match:
                profit_margin = payout - self.bet_amount
                if profit_margin > 0:
                    bonus = int(profit_margin * 0.10)
                    payout += bonus
                    suffix += f"\n🍀 *Nhận thêm +10% tiền lãi từ Daily Lucky Card: `+{bonus:,} VNĐ`*"

        profit_delta = payout - self.bet_amount

        if payout > 0:
            self.cog.economy.add_money(self.user_id, payout)
            log_wallet_change(logger, event="highlow_payout", user_id=self.user_id, money_delta=payout, ctx=self.ctx)

        stats = self.cog.economy.get_highlow_stats(self.user_id)
        old_max_streak = stats.get("max_streak", 0)
        old_max_mult = stats.get("max_multiplier", 0.0)

        game_info = {
            "streak": self.streak,
            "multiplier": self.multiplier if win else 0.0,
            "profit": profit_delta,
            "lucky_card_match": self.lucky_card_match
        }

        newly_unlocked = check_and_unlock_highlow_achievements(stats, game_info)
        updated_achievements = list(stats.get("achievements", []))
        if newly_unlocked:
            updated_achievements.extend(newly_unlocked)

        self.cog.economy.update_highlow_stats(
            self.user_id,
            plays=1,
            wins=1 if win else 0,
            losses=0 if win else 1,
            profit=profit_delta,
            streak=self.streak if win else 0,
            max_streak=max(old_max_streak, self.streak),
            max_multiplier=max(old_max_mult, self.multiplier if win else 0.0),
            achievements=updated_achievements
        )

        desc_suffix = f"\n**Kết quả:** "
        if profit_delta > 0:
            desc_suffix += f"🟢 Thắng `+{profit_delta:,} VNĐ`"
        elif profit_delta < 0:
            desc_suffix += f"🔴 Thua `-{abs(profit_delta):,} VNĐ`"
        else:
            desc_suffix += f"⚪ Hòa ván chơi"

        if newly_unlocked:
            ach_texts = "\n".join([f"✨ **{HIGHLOW_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            desc_suffix += f"\n\n🏆 **THÀNH TỰU MỚI:**\n{ach_texts}"

        await self.render_and_send(is_final=True, msg_suffix=f"{suffix}\n{desc_suffix}")

    async def on_timeout(self):
        if self.user_id in self.cog.active_users:
            self.cog.active_users.discard(self.user_id)
            if self.streak > 0:
                await self.conclude_game(win=True, suffix="💤 **Hết thời gian chờ! Tự động Cash Out hệ số hiện tại.**")
            else:
                await self.conclude_game(win=False, suffix="💤 **Hết thời gian chờ! Bạn đã mất tiền cược do chưa đoán trúng lượt nào.**")


class HighLow(commands.Cog, name="HighLow"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.active_users = set()

    @commands.group(
        name="highlow",
        aliases=["hl"],
        brief="Trò chơi bài Tây High & Low (Cao hoặc Thấp) cực kỳ hấp dẫn.",
        usage="highlow [tiền cược]",
        invoke_without_command=True
    )
    async def highlow_cmd(self, ctx: commands.Context, bet_amount_str: str = None):
        user_id = ctx.author.id

        if bet_amount_str is None:
            view = HighLowLobbyView(self, user_id)
            daily_lucky = get_daily_lucky_card()
            lucky_disp = get_lucky_card_display(daily_lucky)

            embed = make_embed(
                title="🃏 SẢNH CHỜ HIGH & LOW",
                description=(
                    f"Chào mừng bạn đến với bàn chơi High & Low (Cao hoặc Thấp)!\n"
                    f"Rút bài và dự đoán lá tiếp theo Cao hơn, Thấp hơn hoặc đoán Màu/Chất để nhân số tiền thắng.\n\n"
                    f"🍀 **Lucky Card hôm nay:** `{lucky_disp}` (Nhận thêm +10% tiền lãi nếu rút trúng)\n\n"
                    f"👉 **Cú pháp chơi:** `i?hl <tiền cược>`\n"
                    f"👉 **Ví dụ:** `i?hl 100k` hoặc `i?hl all` (tất tay)\n\n"
                    f"Chọn một nút bấm dưới đây để xem chỉ số của bạn hoặc bảng xếp hạng:"
                ),
                color=discord.Color.purple()
            )
            embed.set_footer(text="Casino Bot • High & Low Poker")
            view.message = await ctx.send(embed=embed, view=view)
            return

        if user_id in self.active_users:
            await ctx.send("❌ **Lỗi:** Bạn đang có một ván chơi High & Low chưa hoàn thành!")
            return

        current_money = self.economy.get_entry(user_id)[1]
        bet_amount = parse_bet_amount(bet_amount_str, current_money)

        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 VNĐ.")
            return

        try:
            validate_money_bet(self.economy, user_id, bet_amount)
        except Exception as e:
            await ctx.send(f"❌ {e}")
            return

        view = HighLowModeSelectionView(self, ctx, bet_amount)
        embed = make_embed(
            title="🎮 CHỌN CHẾ ĐỘ CHƠI HIGH & LOW",
            description=(
                f"👤 **Người chơi:** {ctx.author.mention}\n"
                f"💵 **Tiền cược:** `{bet_amount:,} VNĐ`\n\n"
                f"Hãy chọn chế độ bạn muốn thử thách:\n\n"
                f"• 🃏 **Cổ điển (Classic)**: Hệ số thay đổi linh hoạt theo tỷ lệ thực của lá bài hiện tại. Cash out bất kỳ lúc nào.\n"
                f"• 🎯 **Thử thách Chuỗi**: Đặt mục tiêu chuỗi đoán đúng để ăn thêm bonus.\n"
                f"• 🔥 **Hardcore**: Đoán đúng liên tục 10 lá để nhận bonus x1.3, không thể cash out giữa chừng."
            ),
            color=discord.Color.purple()
        )
        view.message = await ctx.send(embed=embed, view=view)

    @highlow_cmd.command(name="stats", brief="Xem thống kê chơi High & Low.")
    async def stats_sub(self, ctx: commands.Context, member: discord.Member = None):
        target_user = member or ctx.author
        stats = self.economy.get_highlow_stats(target_user.id)
        plays = stats["plays"]
        wins = stats["wins"]
        losses = stats["losses"]
        profit = stats["profit"]
        streak = stats["streak"]
        max_streak = stats["max_streak"]
        max_mult = stats["max_multiplier"]
        achievements_list = stats["achievements"]
        vip = get_user_vip(stats)

        win_rate = (wins / plays * 100) if plays > 0 else 0.0
        profit_sign = "+" if profit >= 0 else ""

        desc = (
            f"👑 **Danh hiệu:** `{vip['title']}` ({vip['name']})\n"
            f"🃏 **Số ván đã chơi:** `{plays}`\n"
            f"🏆 **Số ván thắng:** `{wins}`\n"
            f"❌ **Số ván thua:** `{losses}`\n"
            f"📈 **Tỷ lệ thắng:** `{win_rate:.1f}%`\n"
            f"🔥 **Chuỗi đoán đúng dài nhất:** `{max_streak}`\n"
            f"🔥 **Chuỗi đoán đúng hiện tại:** `{streak}`\n"
            f"🔝 **Hệ số Cash Out cao nhất:** `{max_mult:.2f}x`\n"
            f"💸 **Tổng lợi nhuận:** `{profit_sign}{profit:,} VNĐ`\n"
        )
        embed = make_embed(
            title=f"📊 THỐNG KÊ HIGH & LOW - {target_user.name.upper()}",
            description=desc,
            color=discord.Color.purple()
        )
        if achievements_list:
            ach_texts = "\n".join([f"✨ {HIGHLOW_ACHIEVEMENTS[a]}" for a in achievements_list if a in HIGHLOW_ACHIEVEMENTS])
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value=ach_texts, inline=False)
        else:
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value="*Chưa mở khóa thành tựu nào*", inline=False)

        await ctx.send(embed=embed)

    @highlow_cmd.command(name="rank", aliases=["leaderboard", "bxh"], brief="Xem bảng xếp hạng cao thủ High & Low.")
    async def rank_sub(self, ctx: commands.Context):
        self.economy.cur.execute(
            "SELECT user_id, profit, max_multiplier, max_streak, plays FROM user_highlow ORDER BY profit DESC LIMIT 10"
        )
        rows = self.economy.cur.fetchall()
        if not rows:
            await ctx.send("ℹ️ Chưa có ai xếp hạng High & Low.")
            return

        desc = ""
        for i, row in enumerate(rows, 1):
            u_id, profit, max_mult, max_streak, plays = row
            member = ctx.guild.get_member(u_id)
            name = member.name if member else f"ID: {u_id}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            profit_sign = "+" if profit >= 0 else ""
            desc += (
                f"{medal} **{name}** • Lợi nhuận: `{profit_sign}{profit:,} VNĐ` "
                f"• Chuỗi: `{max_streak}` • Max Mult: `{max_mult:.2f}x` *(Lượt: {plays})*\n"
            )

        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG CAO THỦ HIGH & LOW",
            description=desc,
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)
