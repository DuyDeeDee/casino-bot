import asyncio
import logging
import random
import time
from typing import Optional, Union

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
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


def get_hand_emoji(hand: str) -> str:
    if hand == "bua":
        return "✊ Búa"
    if hand == "keo":
        return "✌️ Kéo"
    if hand == "bao":
        return "🖐️ Bao"
    return "❓"


def evaluate_hands(h1: str, h2: str) -> int:
    """Returns 1 if h1 wins, 2 if h2 wins, 0 if draw"""
    if h1 == h2:
        return 0
    if (h1 == "bua" and h2 == "keo") or (h1 == "keo" and h2 == "bao") or (h1 == "bao" and h2 == "bua"):
        return 1
    return 2


def format_scoreboard(player1_name: str, player2_name: str, rounds_history: list, total_rounds: int) -> str:
    cols = [f" Hiệp {i+1} " for i in range(total_rounds)]
    header = "│".join(cols)
    
    p1_status = []
    p2_status = []
    
    for i in range(total_rounds):
        if i < len(rounds_history):
            r = rounds_history[i]
            p1_choice = r["p1_choice"]
            p2_choice = r["p2_choice"]
            winner = r["winner"]
            
            p1_sym = "✊" if p1_choice == "bua" else "✌️" if p1_choice == "keo" else "🖐️" if p1_choice == "bao" else "❌"
            p2_sym = "✊" if p2_choice == "bua" else "✌️" if p2_choice == "keo" else "🖐️" if p2_choice == "bao" else "❌"
            
            if winner == 1:
                p1_status.append(f"✅ {p1_sym}")
                p2_status.append(f"❌ {p2_sym}")
            elif winner == 2:
                p1_status.append(f"❌ {p1_sym}")
                p2_status.append(f"✅ {p2_sym}")
            else:
                p1_status.append(f"🤝 {p1_sym}")
                p2_status.append(f"🤝 {p2_sym}")
        else:
            p1_status.append(" ⏳  ")
            p2_status.append(" ⏳  ")
            
    p1_cols = [f" {status} " for status in p1_status]
    p2_cols = [f" {status} " for status in p2_status]
    
    p1_line = f"  {player1_name:<10} │" + "│".join(p1_cols)
    p2_line = f"  {player2_name:<10} │" + "│".join(p2_cols)
    
    return f"```\n  Chế độ: Best of {total_rounds}\n  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n  Hiệp       │{header}\n{p1_line}\n{p2_line}\n```"


# Ephemeral button view to collect player's choice privately
class BkbEphemeralChoiceView(discord.ui.View):
    def __init__(self, callback_fn, user_id: int):
        super().__init__(timeout=30.0)
        self.callback_fn = callback_fn
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chọn của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Búa ✊", style=discord.ButtonStyle.primary)
    async def select_bua(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback_fn(interaction, "bua")
        self.stop()

    @discord.ui.button(label="Kéo ✌️", style=discord.ButtonStyle.primary)
    async def select_keo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback_fn(interaction, "keo")
        self.stop()

    @discord.ui.button(label="Bao 🖐️", style=discord.ButtonStyle.primary)
    async def select_bao(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.callback_fn(interaction, "bao")
        self.stop()


# Solo view to select hand and play again
class BkbSoloView(discord.ui.View):
    def __init__(self, cog: "Bkb", ctx: commands.Context, bet_amount: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.user_id = ctx.author.id
        self.bet_amount = bet_amount
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True

    async def play_game(self, interaction: discord.Interaction, player_choice: str):
        await interaction.response.defer()
        
        # Deduct bet amount
        try:
            validate_money_bet(self.cog.economy, self.user_id, self.bet_amount)
            self.cog.economy.add_money(self.user_id, -self.bet_amount)
            log_wallet_change(logger, event="bkb_solo_bet", user_id=self.user_id, money_delta=-self.bet_amount, ctx=self.ctx)
        except Exception as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return

        bot_choice = random.choice(["bua", "keo", "bao"])
        outcome = evaluate_hands(player_choice, bot_choice)
        
        stats = self.cog.economy.get_bkb_stats(self.user_id)
        current_streak = stats["streak"]
        
        net_profit = 0
        winnings = 0
        
        if outcome == 1:  # Player Win
            # Calculate win streak payout
            multiplier = 1.0
            streak_bonus_text = ""
            if current_streak >= 5:
                multiplier = 1.5
                streak_bonus_text = f"\n🔥 Nhân {multiplier}x tiền thưởng nhờ chuỗi thắng {current_streak}!"
                
            winnings = int(self.bet_amount * (1 + multiplier)) # get bet back + win amount
            net_profit = winnings - self.bet_amount
            self.cog.economy.add_money(self.user_id, winnings)
            log_wallet_change(logger, event="bkb_solo_win", user_id=self.user_id, money_delta=winnings, ctx=self.ctx)
            
            new_streak = current_streak + 1
            self.cog.economy.update_bkb_stats(
                self.user_id,
                plays=1,
                wins=1,
                profit=net_profit,
                streak=new_streak,
                max_streak=max(stats["max_streak"], new_streak)
            )
            
            color = discord.Color.green()
            result_title = "🏆 BẠN THẮNG!"
            result_desc = (
                f"👤 **Bạn:** {get_hand_emoji(player_choice)}\n"
                f"🤖 **Bot:** {get_hand_emoji(bot_choice)}\n\n"
                f"💥 {get_hand_emoji(player_choice)} thắng {get_hand_emoji(bot_choice)}!{streak_bonus_text}\n"
                f"💰 **Nhận:** `+{net_profit:,} xu` | Ví: **{self.cog.economy.get_entry(self.user_id)[1]:,} xu**"
            )
        elif outcome == 2:  # Player Lose
            net_profit = -self.bet_amount
            self.cog.economy.update_bkb_stats(
                self.user_id,
                plays=1,
                losses=1,
                profit=net_profit,
                streak=0
            )
            color = discord.Color.red()
            result_title = "💥 BẠN THUA!"
            result_desc = (
                f"👤 **Bạn:** {get_hand_emoji(player_choice)}\n"
                f"🤖 **Bot:** {get_hand_emoji(bot_choice)}\n\n"
                f"💥 {get_hand_emoji(bot_choice)} thắng {get_hand_emoji(player_choice)}!\n"
                f"💸 **Mất:** `-{self.bet_amount:,} xu` | Ví: **{self.cog.economy.get_entry(self.user_id)[1]:,} xu**"
            )
        else:  # Draw
            winnings = self.bet_amount
            self.cog.economy.add_money(self.user_id, winnings)
            log_wallet_change(logger, event="bkb_solo_draw", user_id=self.user_id, money_delta=winnings, ctx=self.ctx)
            
            self.cog.economy.update_bkb_stats(
                self.user_id,
                plays=1,
                draws=1
            )
            color = discord.Color.light_grey()
            result_title = "🤝 HOÀ!"
            result_desc = (
                f"👤 **Bạn:** {get_hand_emoji(player_choice)}\n"
                f"🤖 **Bot:** {get_hand_emoji(bot_choice)}\n\n"
                f"🤝 Hoà nhau! Hoàn trả tiền cược.\n"
                f"Ví: **{self.cog.economy.get_entry(self.user_id)[1]:,} xu**"
            )

        embed = make_embed(
            title=result_title,
            description=result_desc,
            color=color
        )
        
        # Play again view
        view = BkbPlayAgainView(self.cog, self.ctx, self.bet_amount)
        if self.message:
            view.message = await self.message.edit(embed=embed, view=view)
        else:
            view.message = await interaction.followup.send(embed=embed, view=view)

    @discord.ui.button(label="Búa ✊", style=discord.ButtonStyle.primary)
    async def select_bua(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play_game(interaction, "bua")

    @discord.ui.button(label="Kéo ✌️", style=discord.ButtonStyle.primary)
    async def select_keo(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play_game(interaction, "keo")

    @discord.ui.button(label="Bao 🖐️", style=discord.ButtonStyle.primary)
    async def select_bao(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.play_game(interaction, "bao")


class BkbPlayAgainView(discord.ui.View):
    def __init__(self, cog: "Bkb", ctx: commands.Context, bet_amount: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.user_id = ctx.author.id
        self.bet_amount = bet_amount
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔄 Chơi lại", style=discord.ButtonStyle.success)
    async def replay(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Verify wallet has enough funds
        current_money = self.cog.economy.get_entry(self.user_id)[1]
        if current_money < self.bet_amount:
            await interaction.response.send_message("❌ Bạn không đủ tiền để chơi tiếp!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        # Display solo selection again
        stats = self.cog.economy.get_bkb_stats(self.user_id)
        current_streak = stats["streak"]
        streak_text = f"\n🔥 Bạn đang có chuỗi thắng {current_streak} liên tiếp!" if current_streak > 0 else ""
        
        embed = make_embed(
            title="✊✌️🖐️ BÚA KÉO BAO (Solo)",
            description=(
                f"┌──────────────────────────┐\n"
                f"│  ✊✌️🖐️  BÚA KÉO BAO    │\n"
                f"│  Cược: {self.bet_amount:,} xu          │\n"
                f"│  Thắng: {self.bet_amount*2:,} xu         │\n"
                f"└──────────────────────────┘\n"
                f"Chọn trong 15 giây!{streak_text}"
            ),
            color=discord.Color.blue()
        )
        
        view = BkbSoloView(self.cog, self.ctx, self.bet_amount)
        view.message = self.message
        await self.message.edit(embed=embed, view=view)


# Invite view for 1v1 challenges
class BkbChallengeInviteView(discord.ui.View):
    def __init__(self, cog: "Bkb", ctx: commands.Context, opponent: discord.Member, bet_amount: int, is_bo3: bool = False, is_bo5: bool = False, challenger_predict: Optional[str] = None):
        super().__init__(timeout=45.0)
        self.cog = cog
        self.ctx = ctx
        self.challenger = ctx.author
        self.opponent = opponent
        self.bet_amount = bet_amount
        self.is_bo3 = is_bo3
        self.is_bo5 = is_bo5
        self.challenger_predict = challenger_predict
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Nút này chỉ dành cho người được thách đấu!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✅ Chấp nhận", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        # Check both players' money before starting
        c_money = self.cog.economy.get_entry(self.challenger.id)[1]
        o_money = self.cog.economy.get_entry(self.opponent.id)[1]
        
        if c_money < self.bet_amount:
            await interaction.followup.send(f"❌ Trận đấu bị huỷ vì {self.challenger.mention} không đủ tiền cược!")
            self.stop()
            return
        if o_money < self.bet_amount:
            await interaction.followup.send(f"❌ Trận đấu bị huỷ vì {self.opponent.mention} không đủ tiền cược!")
            self.stop()
            return
            
        # Deduct money from both players
        self.cog.economy.add_money(self.challenger.id, -self.bet_amount)
        self.cog.economy.add_money(self.opponent.id, -self.bet_amount)
        log_wallet_change(logger, event="bkb_1v1_bet", user_id=self.challenger.id, money_delta=-self.bet_amount, ctx=self.ctx)
        log_wallet_change(logger, event="bkb_1v1_bet", user_id=self.opponent.id, money_delta=-self.bet_amount, ctx=self.ctx)

        self.stop()
        
        # Launch game loop
        if self.is_bo3 or self.is_bo5:
            game = BkbBoMatch(
                cog=self.cog,
                ctx=self.ctx,
                player1=self.challenger,
                player2=self.opponent,
                bet=self.bet_amount,
                total_rounds=3 if self.is_bo3 else 5,
                message=self.message
            )
            await game.start()
        else:
            game = BkbSingleMatch(
                cog=self.cog,
                ctx=self.ctx,
                player1=self.challenger,
                player2=self.opponent,
                bet=self.bet_amount,
                p1_predict=self.challenger_predict,
                message=self.message
            )
            await game.start()

    @discord.ui.button(label="❌ Từ chối", style=discord.ButtonStyle.danger)
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        embed = make_embed(
            title="⚔️ THÁCH ĐẤU BỊ TỪ CHỐI",
            description=f"❌ {self.opponent.mention} đã từ chối lời thách đấu từ {self.challenger.mention}.",
            color=discord.Color.red()
        )
        await self.message.edit(embed=embed, view=None)
        self.stop()

    async def on_timeout(self):
        try:
            embed = make_embed(
                title="⚔️ THÁCH ĐẤU HẾT HẠN",
                description=f"⏳ Lời thách đấu của {self.challenger.mention} dành cho {self.opponent.mention} đã hết hạn.",
                color=discord.Color.red()
            )
            await self.message.edit(embed=embed, view=None)
        except Exception:
            pass


# 1v1 Choice collector view in public channel
class Bkb1v1ChoiceView(discord.ui.View):
    def __init__(self, match_obj, player1: discord.Member, player2: discord.Member, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.match_obj = match_obj
        self.p1 = player1
        self.p2 = player2

    async def on_timeout(self):
        await self.match_obj.handle_timeout()

    @discord.ui.button(label="🖐️ Chọn tay", style=discord.ButtonStyle.success)
    async def make_choice(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id != self.p1.id and user_id != self.p2.id:
            await interaction.response.send_message("❌ Bạn không tham gia trận thách đấu này!", ephemeral=True)
            return
            
        if user_id in self.match_obj.choices:
            await interaction.response.send_message("❌ Bạn đã chọn rồi!", ephemeral=True)
            return

        # Send private ephemeral buttons
        view = BkbEphemeralChoiceView(self.receive_ephemeral_choice, user_id)
        await interaction.response.send_message(
            content="Chọn bí mật của bạn! Đối thủ không thấy.",
            view=view,
            ephemeral=True
        )

    async def receive_ephemeral_choice(self, interaction: discord.Interaction, hand: str):
        await interaction.response.edit_message(content=f"✅ Bạn đã chọn: {get_hand_emoji(hand)}", view=None)
        await self.match_obj.register_choice(interaction.user.id, hand)


# Single Match coordinator
class BkbSingleMatch:
    def __init__(self, cog: "Bkb", ctx: commands.Context, player1: discord.Member, player2: discord.Member, bet: int, p1_predict: Optional[str] = None, message: Optional[discord.Message] = None):
        self.cog = cog
        self.ctx = ctx
        self.p1 = player1
        self.p2 = player2
        self.bet = bet
        self.p1_predict = p1_predict
        self.message = message
        self.choices = {}
        if p1_predict:
            self.choices[player1.id] = p1_predict
        self.resolved = False

    async def start(self):
        p1_status = "Đã đặt trước" if self.p1_predict else "Đang chọn..."
        p2_status = "Đang chọn..."
        
        predict_tag = f" (Đã đặt trước: {get_hand_emoji(self.p1_predict)})" if self.p1_predict else ""
        
        embed = make_embed(
            title="⚔️ THÁCH ĐẤU BÚA KÉO BAO",
            description=(
                f"👊 {self.p1.mention}{predict_tag} : {p1_status}\n"
                f"❓ {self.p2.mention} : {p2_status}\n\n"
                f"Nhấp vào nút bên dưới để chọn tay (bí mật của bạn)."
            ),
            color=discord.Color.blue()
        )
        self.view = Bkb1v1ChoiceView(self, self.p1, self.p2, timeout=30.0)
        await self.message.edit(embed=embed, view=self.view)

    async def handle_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        self.view.stop()
        
        # Refund both
        self.cog.economy.add_money(self.p1.id, self.bet)
        self.cog.economy.add_money(self.p2.id, self.bet)
        log_wallet_change(logger, event="bkb_1v1_refund_timeout", user_id=self.p1.id, money_delta=self.bet, ctx=self.ctx)
        log_wallet_change(logger, event="bkb_1v1_refund_timeout", user_id=self.p2.id, money_delta=self.bet, ctx=self.ctx)
        
        timeout_desc = "Trận đấu bị huỷ và hoàn tiền vì có người không chọn tay kịp thời."
        embed = make_embed(
            title="⚔️ THÁCH ĐẤU BỊ HUỶ",
            description=timeout_desc,
            color=discord.Color.red()
        )
        try:
            await self.message.edit(embed=embed, view=None)
        except Exception:
            pass

    async def register_choice(self, user_id: int, hand: str):
        if self.resolved:
            return
        self.choices[user_id] = hand
        
        # Update embed statuses
        p1_status = "Đã chọn" if self.p1.id in self.choices else "Đang chọn..."
        p2_status = "Đã chọn" if self.p2.id in self.choices else "Đang chọn..."
        predict_tag = f" (Đã đặt trước: {get_hand_emoji(self.p1_predict)})" if self.p1_predict else ""
        
        embed = make_embed(
            title="⚔️ THÁCH ĐẤU BÚA KÉO BAO",
            description=(
                f"👊 {self.p1.mention}{predict_tag} : {p1_status}\n"
                f"❓ {self.p2.mention} : {p2_status}\n\n"
                f"Nhấp vào nút bên dưới để chọn tay (bí mật của bạn)."
            ),
            color=discord.Color.blue()
        )
        await self.message.edit(embed=embed, view=self.view)
        
        if len(self.choices) == 2:
            self.resolved = True
            self.view.stop()
            await self.resolve_game()

    async def resolve_game(self):
        c1 = self.choices[self.p1.id]
        c2 = self.choices[self.p2.id]
        
        outcome = evaluate_hands(c1, c2)
        
        # Read stats
        s1 = self.cog.economy.get_bkb_stats(self.p1.id)
        s2 = self.cog.economy.get_bkb_stats(self.p2.id)
        
        if outcome == 0:  # Draw
            # Refund
            self.cog.economy.add_money(self.p1.id, self.bet)
            self.cog.economy.add_money(self.p2.id, self.bet)
            log_wallet_change(logger, event="bkb_1v1_refund_draw", user_id=self.p1.id, money_delta=self.bet, ctx=self.ctx)
            log_wallet_change(logger, event="bkb_1v1_refund_draw", user_id=self.p2.id, money_delta=self.bet, ctx=self.ctx)
            
            # Update DB stats
            self.cog.economy.update_bkb_stats(self.p1.id, plays=1, draws=1)
            self.cog.economy.update_bkb_stats(self.p2.id, plays=1, draws=1)
            self.cog.economy.update_bkb_h2h(self.p1.id, self.p2.id, draw=True)
            
            title = "⚔️ KẾT QUẢ THÁCH ĐẤU"
            desc = (
                f"  {self.p1.display_name}    vs    {self.p2.display_name}\n"
                f"    {get_hand_emoji(c1)}              {get_hand_emoji(c2)}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🤝 Hoà! Không ai mất xu.\n"
            )
            color = discord.Color.light_grey()
        elif outcome == 1:  # Player 1 Wins
            # Payout
            payout = self.bet * 2
            net_profit_p1 = self.bet
            net_profit_p2 = -self.bet
            
            predict_info = ""
            if self.p1_predict:
                # 2.5x payout means winner gets: bet * 3.5 total (Original bet back + 2.5x net win)
                payout = int(self.bet * 3.5)
                net_profit_p1 = int(self.bet * 2.5)
                predict_info = f"\n🎯 Thắng dự đoán trước: Nhận thưởng 2.5x tiền cược!"
                
            self.cog.economy.add_money(self.p1.id, payout)
            log_wallet_change(logger, event="bkb_1v1_win", user_id=self.p1.id, money_delta=payout, ctx=self.ctx)
            
            # Update DB stats
            streak1 = s1["streak"] + 1
            self.cog.economy.update_bkb_stats(self.p1.id, plays=1, wins=1, profit=net_profit_p1, streak=streak1, max_streak=max(s1["max_streak"], streak1))
            self.cog.economy.update_bkb_stats(self.p2.id, plays=1, losses=1, profit=net_profit_p2, streak=0)
            self.cog.economy.update_bkb_h2h(self.p1.id, self.p2.id, p1_win=True, profit_delta=net_profit_p1)
            
            title = "⚔️ KẾT QUẢ THÁCH ĐẤU"
            desc = (
                f"  {self.p1.display_name}    vs    {self.p2.display_name}\n"
                f"    {get_hand_emoji(c1)}              {get_hand_emoji(c2)}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏆 {self.p1.mention} THẮNG!\n"
                f"💰 **Nhận:** `+{net_profit_p1:,} xu`{predict_info}"
            )
            color = discord.Color.green()
        else:  # Player 2 Wins
            # Payout
            payout = self.bet * 2
            net_profit_p2 = self.bet
            net_profit_p1 = -self.bet
            
            self.cog.economy.add_money(self.p2.id, payout)
            log_wallet_change(logger, event="bkb_1v1_win", user_id=self.p2.id, money_delta=payout, ctx=self.ctx)
            
            # Update DB stats
            streak2 = s2["streak"] + 1
            self.cog.economy.update_bkb_stats(self.p2.id, plays=1, wins=1, profit=net_profit_p2, streak=streak2, max_streak=max(s2["max_streak"], streak2))
            self.cog.economy.update_bkb_stats(self.p1.id, plays=1, losses=1, profit=net_profit_p1, streak=0)
            self.cog.economy.update_bkb_h2h(self.p1.id, self.p2.id, p2_win=True, profit_delta=net_profit_p1) # profit_delta from p1 perspective (loss)
            
            title = "⚔️ KẾT QUẢ THÁCH ĐẤU"
            desc = (
                f"  {self.p1.display_name}    vs    {self.p2.display_name}\n"
                f"    {get_hand_emoji(c1)}              {get_hand_emoji(c2)}\n"
                f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"🏆 {self.p2.mention} THẮNG!\n"
                f"💰 **Nhận:** `+{net_profit_p2:,} xu`"
            )
            color = discord.Color.green()

        embed = make_embed(
            title=title,
            description=desc,
            color=color
        )
        
        # Challenge back options
        view = BkbChallengeAgainView(self.cog, self.ctx, self.p1, self.p2, self.bet)
        await self.message.edit(embed=embed, view=view)


class BkbChallengeAgainView(discord.ui.View):
    def __init__(self, cog: "Bkb", ctx: commands.Context, p1: discord.Member, p2: discord.Member, bet: int):
        super().__init__(timeout=45.0)
        self.cog = cog
        self.ctx = ctx
        self.p1 = p1
        self.p2 = p2
        self.bet = bet

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.p1.id and interaction.user.id != self.p2.id:
            await interaction.response.send_message("❌ Bạn không tham gia trận thách đấu này!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🔄 Thách lại", style=discord.ButtonStyle.success)
    async def rematch(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        challenger = interaction.user
        opponent = self.p2 if challenger.id == self.p1.id else self.p1
        
        # Verify wallets
        c_money = self.cog.economy.get_entry(challenger.id)[1]
        o_money = self.cog.economy.get_entry(opponent.id)[1]
        
        if c_money < self.bet or o_money < self.bet:
            await interaction.followup.send("❌ Có người chơi không đủ tiền cược cho trận đấu mới!", ephemeral=True)
            return

        embed = make_embed(
            title="⚔️ THÁCH ĐẤU BÚA KÉO BAO",
            description=(
                f"👊 {challenger.mention} vs ❓ {opponent.mention}\n"
                f"💰 Cược: {self.bet:,} xu mỗi người\n━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                f"@{opponent.display_name} — Bạn có chấp nhận thách lại?"
            ),
            color=discord.Color.blue()
        )
        
        view = BkbChallengeInviteView(self.cog, self.ctx, opponent, self.bet)
        # We reuse the same message
        view.message = await interaction.message.edit(embed=embed, view=view)
        self.stop()

    @discord.ui.button(label="🏃 Bỏ qua", style=discord.ButtonStyle.secondary)
    async def skip(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await interaction.message.edit(view=None)
        self.stop()


# Best of Match coordinator
class BkbBoMatch:
    def __init__(self, cog: "Bkb", ctx: commands.Context, player1: discord.Member, player2: discord.Member, bet: int, total_rounds: int, message: Optional[discord.Message] = None):
        self.cog = cog
        self.ctx = ctx
        self.p1 = player1
        self.p2 = player2
        self.bet = bet
        self.total_rounds = total_rounds
        self.message = message
        self.rounds_history = []
        self.p1_wins = 0
        self.p2_wins = 0
        self.target_wins = (total_rounds // 2) + 1
        self.current_round = 1
        self.choices = {}
        self.resolved = False

    async def start(self):
        await self.start_round()

    async def start_round(self):
        self.choices.clear()
        self.resolved = False
        
        score_board = format_scoreboard(self.p1.display_name, self.p2.display_name, self.rounds_history, self.total_rounds)
        
        desc = (
            f"💰 **Cược tổng:** `{self.bet * 2:,} xu`\n"
            f"🏆 Thắng **{self.target_wins}** hiệp trước → **WIN**\n\n"
            f"{score_board}\n"
            f"🎮 **Hiệp {self.current_round}**: Hai người đang chọn tay..."
        )
        embed = make_embed(
            title=f"⚔️ BEST OF {self.total_rounds} — BÚA KÉO BAO",
            description=desc,
            color=discord.Color.blue()
        )
        self.view = Bkb1v1ChoiceView(self, self.p1, self.p2, timeout=30.0)
        await self.message.edit(embed=embed, view=self.view)

    async def handle_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        self.view.stop()
        
        # If round timed out, see who chose
        p1_chose = self.p1.id in self.choices
        p2_chose = self.p2.id in self.choices
        
        if p1_chose and not p2_chose:
            # P1 wins the round by default
            self.choices[self.p2.id] = "disqualified"
            await self.resolve_round()
        elif p2_chose and not p1_chose:
            # P2 wins round by default
            self.choices[self.p1.id] = "disqualified"
            await self.resolve_round()
        else:
            # Both timed out or game aborted
            # Refund remaining bet
            self.cog.economy.add_money(self.p1.id, self.bet)
            self.cog.economy.add_money(self.p2.id, self.bet)
            log_wallet_change(logger, event="bkb_bo_refund_timeout", user_id=self.p1.id, money_delta=self.bet, ctx=self.ctx)
            log_wallet_change(logger, event="bkb_bo_refund_timeout", user_id=self.p2.id, money_delta=self.bet, ctx=self.ctx)
            
            embed = make_embed(
                title=f"⚔️ MATCH ABORTED",
                description="Trận đấu BO bị huỷ và hoàn tiền vì không ai chọn tay kịp thời.",
                color=discord.Color.red()
            )
            try:
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass

    async def register_choice(self, user_id: int, hand: str):
        if self.resolved:
            return
        self.choices[user_id] = hand
        
        if len(self.choices) == 2:
            self.resolved = True
            self.view.stop()
            await self.resolve_round()

    async def resolve_round(self):
        c1 = self.choices[self.p1.id]
        c2 = self.choices[self.p2.id]
        
        if c1 == "disqualified" and c2 == "disqualified":
            # Round remains a draw
            round_winner = 0
        elif c1 == "disqualified":
            round_winner = 2
        elif c2 == "disqualified":
            round_winner = 1
        else:
            round_winner = evaluate_hands(c1, c2)
            
        if round_winner == 1:
            self.p1_wins += 1
            self.rounds_history.append({"p1_choice": c1, "p2_choice": c2, "winner": 1})
            self.current_round += 1
        elif round_winner == 2:
            self.p2_wins += 1
            self.rounds_history.append({"p1_choice": c1, "p2_choice": c2, "winner": 2})
            self.current_round += 1
        else:
            # Replay drawn round (doesn't count, re-initialize choice)
            embed = make_embed(
                title=f"⚔️ HIỆP HOÀ — ĐẤU LẠI",
                description=f"Hiệp {self.current_round} hoà! Đang tải lại hiệp để phân thắng bại...",
                color=discord.Color.light_grey()
            )
            await self.message.edit(embed=embed, view=None)
            await asyncio.sleep(3.0)
            await self.start_round()
            return

        # Check match win condition
        if self.p1_wins == self.target_wins or self.p2_wins == self.target_wins:
            await self.resolve_match()
        else:
            # Proceed to next round
            score_board = format_scoreboard(self.p1.display_name, self.p2.display_name, self.rounds_history, self.total_rounds)
            leader_name = self.p1.display_name if self.p1_wins > self.p2_wins else self.p2.display_name
            leader_score = max(self.p1_wins, self.p2_wins)
            loser_score = min(self.p1_wins, self.p2_wins)
            
            desc = (
                f"💰 **Cược tổng:** `{self.bet * 2:,} xu`\n"
                f"🏆 Thắng **{self.target_wins}** hiệp trước → **WIN**\n\n"
                f"{score_board}\n"
                f"🔥 **{leader_name}** đang dẫn **{leader_score}-{loser_score}**!\n"
                f"Chuyển sang hiệp kế tiếp trong giây lát..."
            )
            embed = make_embed(
                title=f"⚔️ BEST OF {self.total_rounds} — BÚA KÉO BAO",
                description=desc,
                color=discord.Color.blue()
            )
            await self.message.edit(embed=embed, view=None)
            await asyncio.sleep(4.0)
            await self.start_round()

    async def resolve_match(self):
        score_board = format_scoreboard(self.p1.display_name, self.p2.display_name, self.rounds_history, self.total_rounds)
        
        s1 = self.cog.economy.get_bkb_stats(self.p1.id)
        s2 = self.cog.economy.get_bkb_stats(self.p2.id)
        
        if self.p1_wins == self.target_wins:
            winner = self.p1
            loser = self.p2
            winnings = self.bet * 2
            net_profit_w = self.bet
            net_profit_l = -self.bet
            
            self.cog.economy.add_money(self.p1.id, winnings)
            log_wallet_change(logger, event="bkb_bo_win", user_id=self.p1.id, money_delta=winnings, ctx=self.ctx)
            
            # Update stats
            streak1 = s1["streak"] + 1
            self.cog.economy.update_bkb_stats(self.p1.id, plays=1, wins=1, profit=net_profit_w, streak=streak1, max_streak=max(s1["max_streak"], streak1))
            self.cog.economy.update_bkb_stats(self.p2.id, plays=1, losses=1, profit=net_profit_l, streak=0)
            self.cog.economy.update_bkb_h2h(self.p1.id, self.p2.id, p1_win=True, profit_delta=net_profit_w)
            
        else:
            winner = self.p2
            loser = self.p1
            winnings = self.bet * 2
            net_profit_w = self.bet
            net_profit_l = -self.bet
            
            self.cog.economy.add_money(self.p2.id, winnings)
            log_wallet_change(logger, event="bkb_bo_win", user_id=self.p2.id, money_delta=winnings, ctx=self.ctx)
            
            # Update stats
            streak2 = s2["streak"] + 1
            self.cog.economy.update_bkb_stats(self.p2.id, plays=1, wins=1, profit=net_profit_w, streak=streak2, max_streak=max(s2["max_streak"], streak2))
            self.cog.economy.update_bkb_stats(self.p1.id, plays=1, losses=1, profit=net_profit_l, streak=0)
            self.cog.economy.update_bkb_h2h(self.p1.id, self.p2.id, p2_win=True, profit_delta=net_profit_l)
            
        desc = (
            f"💰 **Nồi thưởng:** `{self.bet * 2:,} xu`\n\n"
            f"{score_board}\n"
            f"🏆 **{winner.mention} THẮNG CHUNG CUỘC!**\n"
            f"💰 **Nhận:** `+{net_profit_w:,} xu` vào ví!"
        )
        embed = make_embed(
            title=f"⚔️ KẾT QUẢ BEST OF {self.total_rounds}",
            description=desc,
            color=discord.Color.gold()
        )
        
        # Challenger back options
        view = BkbChallengeAgainView(self.cog, self.ctx, self.p1, self.p2, self.bet)
        await self.message.edit(embed=embed, view=view)


# Party Lobby View
class BkbPartyLobbyView(discord.ui.View):
    def __init__(self, cog: "Bkb", ctx: commands.Context, bet: int):
        super().__init__(timeout=45.0)
        self.cog = cog
        self.ctx = ctx
        self.host = ctx.author
        self.bet = bet
        self.players = [ctx.author]
        self.message: Optional[discord.Message] = None
        self.started = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="🙋 Tham gia", style=discord.ButtonStyle.success)
    async def join_lobby(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.started:
            await interaction.response.send_message("❌ Lobby đã bắt đầu chơi!", ephemeral=True)
            return
            
        user = interaction.user
        if user.id in [p.id for p in self.players]:
            await interaction.response.send_message("❌ Bạn đã tham gia lobby rồi!", ephemeral=True)
            return
            
        if len(self.players) >= 8:
            await interaction.response.send_message("❌ Lobby đã đầy (tối đa 8 người)!", ephemeral=True)
            return
            
        # Verify and deduct money
        p_money = self.cog.economy.get_entry(user.id)[1]
        if p_money < self.bet:
            await interaction.response.send_message("❌ Bạn không đủ tiền cược!", ephemeral=True)
            return
            
        await interaction.response.defer()
        
        self.cog.economy.add_money(user.id, -self.bet)
        log_wallet_change(logger, event="bkb_party_bet", user_id=user.id, money_delta=-self.bet, ctx=self.ctx)
        self.players.append(user)
        
        await self.update_lobby()
        
        if len(self.players) == 8:
            self.stop()
            await self.start_game()

    @discord.ui.button(label="🚀 Bắt đầu", style=discord.ButtonStyle.primary)
    async def force_start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("❌ Chỉ có người tạo phòng mới được kích hoạt!", ephemeral=True)
            return
            
        if len(self.players) < 2:
            await interaction.response.send_message("❌ Cần ít nhất 2 người để chơi!", ephemeral=True)
            return
            
        await interaction.response.defer()
        self.stop()
        await self.start_game()

    @discord.ui.button(label="❌ Huỷ phòng", style=discord.ButtonStyle.danger)
    async def cancel_lobby(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host.id:
            await interaction.response.send_message("❌ Chỉ người tạo phòng mới được huỷ phòng!", ephemeral=True)
            return
            
        await interaction.response.defer()
        self.stop()
        
        # Refund everyone
        for p in self.players:
            self.cog.economy.add_money(p.id, self.bet)
            log_wallet_change(logger, event="bkb_party_refund", user_id=p.id, money_delta=self.bet, ctx=self.ctx)
            
        embed = make_embed(
            title="🎪 LOBBY PARTY BỊ HUỶ",
            description=f"❌ Phòng Party cược {self.bet:,} xu đã bị huỷ bởi người tạo {self.host.mention}. Đã hoàn tiền cược cho tất cả.",
            color=discord.Color.red()
        )
        await self.message.edit(embed=embed, view=None)

    async def update_lobby(self):
        player_list_str = "\n".join([f"✅ {p.mention} đã vào" for p in self.players])
        embed = make_embed(
            title="🎪 PARTY BÚA KÉO BAO",
            description=(
                f"💰 **Cược:** `{self.bet:,} xu/người`\n"
                f"👥 **Thành viên ({len(self.players)}/8):**\n"
                f"{player_list_str}\n\n"
                f"⏳ Đang chờ thêm người..."
            ),
            color=discord.Color.blue()
        )
        # Update Join button label with bet
        self.join_lobby.label = f"🙋 Tham gia — {self.bet:,} xu"
        await self.message.edit(embed=embed, view=self)

    async def start_game(self):
        self.started = True
        game = BkbPartyMatch(self.cog, self.ctx, self.players, self.bet, self.message)
        await game.start()

    async def on_timeout(self):
        if self.started:
            return
            
        if len(self.players) >= 2:
            self.started = True
            await self.start_game()
        else:
            # Cancel and refund
            for p in self.players:
                self.cog.economy.add_money(p.id, self.bet)
                log_wallet_change(logger, event="bkb_party_refund", user_id=p.id, money_delta=self.bet, ctx=self.ctx)
                
            embed = make_embed(
                title="🎪 LOBBY PARTY BỊ HUỶ",
                description="❌ Hết thời gian chờ mà phòng không đủ 2 người chơi. Hoàn tiền cược.",
                color=discord.Color.red()
            )
            try:
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass


# Choice view in channel for Party Mode
class BkbPartyChoiceView(discord.ui.View):
    def __init__(self, match_obj, players: list, timeout: float = 15.0):
        super().__init__(timeout=timeout)
        self.match_obj = match_obj
        self.players = players

    async def on_timeout(self):
        await self.match_obj.handle_timeout()

    @discord.ui.button(label="✊ Chọn tay", style=discord.ButtonStyle.success)
    async def make_choice(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        if user_id not in [p.id for p in self.players]:
            await interaction.response.send_message("❌ Bạn không tham gia trận đấu Party này!", ephemeral=True)
            return
            
        if user_id in self.match_obj.choices:
            await interaction.response.send_message("❌ Bạn đã chọn rồi!", ephemeral=True)
            return

        # Send private ephemeral buttons
        view = BkbEphemeralChoiceView(self.receive_ephemeral_choice, user_id)
        await interaction.response.send_message(
            content="Chọn bí mật của bạn! Đối thủ không thấy.",
            view=view,
            ephemeral=True
        )

    async def receive_ephemeral_choice(self, interaction: discord.Interaction, hand: str):
        await interaction.response.edit_message(content=f"✅ Bạn đã chọn: {get_hand_emoji(hand)}", view=None)
        await self.match_obj.register_choice(interaction.user.id, hand)


# Party Match coordinator
class BkbPartyMatch:
    def __init__(self, cog: "Bkb", ctx: commands.Context, players: list, bet: int, message: discord.Message):
        self.cog = cog
        self.ctx = ctx
        self.players = players
        self.bet = bet
        self.message = message
        self.choices = {}
        self.total_pot = bet * len(players)
        self.resolved = False
        self.view = None

    async def start(self):
        await self.update_message()

    async def handle_timeout(self):
        if self.resolved:
            return
        self.resolved = True
        self.view.stop()
        await self.resolve_match()

    async def register_choice(self, user_id: int, hand: str):
        if self.resolved:
            return
        self.choices[user_id] = hand
        await self.update_message()
        
        if len(self.choices) == len(self.players):
            self.resolved = True
            self.view.stop()
            await self.resolve_match()

    async def update_message(self):
        statuses = []
        for p in self.players:
            status = "✅ Đã chọn" if p.id in self.choices else "⏳ Đang chọn..."
            statuses.append(f"👤 {p.mention} — {status}")
            
        embed = make_embed(
            title="🎪 PARTY BÚA KÉO BAO — CHỌN TAY",
            description=(
                f"💰 **Nồi thưởng:** `{self.total_pot:,} xu`\n"
                f"⏰ Có **15 giây** để chọn tay cược!\n\n"
                f"{chr(10).join(statuses)}"
            ),
            color=discord.Color.blue()
        )
        if self.view is None:
            self.view = BkbPartyChoiceView(self, self.players, timeout=15.0)
        await self.message.edit(embed=embed, view=self.view)

    async def resolve_match(self):
        # Filter active players (who chose in time)
        active_players = [p for p in self.players if p.id in self.choices]
        disqualified_players = [p for p in self.players if p.id not in self.choices]
        
        # If no one chose, refund remaining bet
        if not active_players:
            # Refund everyone
            for p in self.players:
                self.cog.economy.add_money(p.id, self.bet)
                log_wallet_change(logger, event="bkb_party_refund", user_id=p.id, money_delta=self.bet, ctx=self.ctx)
                
            embed = make_embed(
                title="🎪 KẾT QUẢ PARTY",
                description="❌ Trận đấu bị huỷ vì không ai chọn tay kịp thời. Hoàn trả tiền cược.",
                color=discord.Color.red()
            )
            await self.message.edit(embed=embed, view=None)
            return

        # List all chosen hands
        bua_players = [p for p in active_players if self.choices[p.id] == 'bua']
        keo_players = [p for p in active_players if self.choices[p.id] == 'keo']
        bao_players = [p for p in active_players if self.choices[p.id] == 'bao']
        
        hand_counts = []
        if bua_players: hand_counts.append("bua")
        if keo_players: hand_counts.append("keo")
        if bao_players: hand_counts.append("bao")
        
        is_draw = False
        winner_hand = ""
        winners = []
        losers = []
        
        if len(hand_counts) == 3 or len(hand_counts) == 1:
            is_draw = True
        else:
            # Only 2 choices present
            if "bua" in hand_counts and "keo" in hand_counts:
                winner_hand = "bua"
                winners = bua_players
                losers = keo_players
            elif "keo" in hand_counts and "bao" in hand_counts:
                winner_hand = "keo"
                winners = keo_players
                losers = bao_players
            elif "bao" in hand_counts and "bua" in hand_counts:
                winner_hand = "bao"
                winners = bao_players
                losers = bua_players

        # Render choices list
        choices_str_list = []
        for p in active_players:
            choices_str_list.append(f"• {p.display_name} → {get_hand_emoji(self.choices[p.id])}")
        for p in disqualified_players:
            choices_str_list.append(f"• {p.display_name} → ❌ Không chọn")
            
        hands_summary = f"✊ {len(bua_players)} người │ ✌️ {len(keo_players)} người │ 🖐️ {len(bao_players)} người"
        
        if is_draw:
            # Refund all participants
            for p in self.players:
                self.cog.economy.add_money(p.id, self.bet)
                log_wallet_change(logger, event="bkb_party_refund_draw", user_id=p.id, money_delta=self.bet, ctx=self.ctx)
                
            desc = (
                f"{chr(10).join(choices_str_list)}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"{hands_summary}\n\n"
                f"🤝 Cả 3 loại đều có hoặc tất cả cùng chọn 1 loại → **HOÀ TOÀN BỘ!**\n"
                f"Hoàn trả tiền cược cho tất cả mọi người."
            )
            color = discord.Color.light_grey()
        else:
            # Share pot among winners
            num_winners = len(winners)
            win_share = self.total_pot // num_winners
            
            for w in winners:
                self.cog.economy.add_money(w.id, win_share)
                log_wallet_change(logger, event="bkb_party_win", user_id=w.id, money_delta=win_share, ctx=self.ctx)
                
                # Update stats
                self.cog.economy.update_bkb_stats(w.id, plays=1, wins=1, profit=win_share - self.bet)
                
            for l in losers:
                self.cog.economy.update_bkb_stats(l.id, plays=1, losses=1, profit=-self.bet)
                
            for dq in disqualified_players:
                self.cog.economy.update_bkb_stats(dq.id, plays=1, losses=1, profit=-self.bet)
                
            winners_mention = ", ".join([w.mention for w in winners])
            
            desc = (
                f"{chr(10).join(choices_str_list)}\n"
                f"━━━━━━━━━━━━━━━━━━━\n"
                f"{hands_summary}\n\n"
                f"🏆 **{get_hand_emoji(winner_hand)}** THẮNG vòng này!\n"
                f"🎉 {winners_mention} chia đôi/nồi thưởng!\n"
                f"💰 **Nhận:** `+{win_share:,} xu` mỗi người."
            )
            color = discord.Color.gold()
            
        embed = make_embed(
            title="🎪 KẾT QUẢ PARTY BÚA KÉO BAO",
            description=desc,
            color=color
        )
        await self.message.edit(embed=embed, view=None)


class Bkb(commands.Cog, name="Bkb"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()

    @commands.command(
        brief="Trò chơi Búa Kéo Bao (✊✌️🖐️) - Solo, 1v1, BO3/5, Party.",
        usage="bkb [tiền cược] / bkb stats [@user] / bkb party [cược] / bkb @user [cược] [bo3/bo5] [--keo bua/keo/bao]",
        aliases=["buakeobao", "oantuti", "ott"]
    )
    async def bkb(self, ctx: commands.Context, *args):
        user_id = ctx.author.id
        
        # 1. Help menu if no arguments
        if not args:
            embed = make_embed(
                title="✊✌️🖐️ GAME BÚA KÉO BAO",
                description=(
                    "Trò chơi đơn giản nhưng cực kỳ cuốn hút!\n\n"
                    "👉 **CÁC CHẾ ĐỘ CHƠI:**\n"
                    "• **Solo vs Bot**: `i!bkb <cược>`\n"
                    "• **Thách đấu 1v1**: `i!bkb @MinhThu <cược>`\n"
                    "• **Best of 3/5**: `i!bkb @MinhThu <cược> bo3` (hoặc `bo5`)\n"
                    "• **Lobby Party**: `i!bkb party <cược>`\n"
                    "• **Thống kê**: `i!bkb stats` hoặc `i!bkb stats @MinhThu`\n\n"
                    "👉 **ĐẶC BIỆT:**\n"
                    "• **Chuỗi thắng**: Solo thắng liên tiếp 5 trận trở lên được **x1.5** tiền thắng.\n"
                    "• **Đặt trước kèo (1v1)**: Thêm `--keo bua/keo/bao` để công khai tay cược. Nhận **x2.5** tiền thắng nếu thắng!"
                ),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        first_arg = args[0].strip().lower()
        
        # 2. Stats Mode
        if first_arg == "stats":
            target_user = ctx.author
            if ctx.message.mentions:
                target_user = ctx.message.mentions[0]
                
            # Head-to-Head stats
            if target_user.id != ctx.author.id:
                h2h = self.economy.get_bkb_h2h(ctx.author.id, target_user.id)
                p1 = ctx.author
                p2 = target_user
                
                # Check mapping based on ID order
                p1_wins = h2h["player_one_wins"] if p1.id < p2.id else h2h["player_two_wins"]
                p2_wins = h2h["player_two_wins"] if p1.id < p2.id else h2h["player_one_wins"]
                draws = h2h["draws"]
                total = p1_wins + p2_wins + draws
                
                profit_trans = h2h["profit_transfer"]
                if p1.id > p2.id:
                    profit_trans = -profit_trans
                    
                profit_sign = "+" if profit_trans >= 0 else ""
                
                embed = make_embed(
                    title="⚔️ LỊCH SỬ ĐỐI ĐẦU BKB",
                    description=(
                        f"👊 **{p1.display_name}** vs **{p2.display_name}**\n"
                        f"━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                        f"• Tổng số trận: **{total}**\n"
                        f"• **{p1.display_name}** thắng: `{p1_wins} 🏆`\n"
                        f"• **{p2.display_name}** thắng: `{p2_wins} 🏆`\n"
                        f"• Hoà: `{draws} 🤝`\n"
                        f"• Tiền đổi chủ: `{profit_sign}{profit_trans:,} xu` về phía **{p1.display_name}**"
                    ),
                    color=discord.Color.blue()
                )
            else:
                # Overall player stats
                stats = self.economy.get_bkb_stats(user_id)
                plays = stats["plays"]
                wins = stats["wins"]
                losses = stats["losses"]
                draws = stats["draws"]
                profit = stats["profit"]
                streak = stats["streak"]
                max_streak = stats["max_streak"]
                
                win_rate = (wins / plays) * 100 if plays > 0 else 0
                profit_sign = "+" if profit >= 0 else ""
                
                embed = make_embed(
                    title=f"📊 THỐNG KÊ BKB — {target_user.display_name}",
                    description=(
                        f"• Tổng ván chơi: **{plays}**\n"
                        f"• Thắng / Thua / Hoà: `{wins}` / `{losses}` / `{draws}`\n"
                        f"• Tỷ lệ thắng: `{win_rate:.1f}%`\n"
                        f"• Lợi nhuận: `{profit_sign}{profit:,} xu`\n"
                        f"• Chuỗi thắng hiện tại: `{streak}`\n"
                        f"• Chuỗi thắng lớn nhất: `{max_streak}`"
                    ),
                    color=discord.Color.blue()
                )
            await ctx.send(embed=embed)
            return

        # 3. Party Mode
        if first_arg == "party":
            bet_str = args[1] if len(args) > 1 else "1000"
            current_money = self.economy.get_entry(user_id)[1]
            bet_amount = parse_bet_amount(bet_str, current_money)
            
            if bet_amount < 1000:
                await ctx.send("❌ Tiền cược tối thiểu là 1,000 xu.")
                return
                
            try:
                validate_money_bet(self.economy, user_id, bet_amount)
            except Exception as e:
                await ctx.send(f"❌ {e}")
                return
                
            # Deduct bet for the creator immediately
            self.economy.add_money(user_id, -bet_amount)
            log_wallet_change(logger, event="bkb_party_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
            
            view = BkbPartyLobbyView(self, ctx, bet_amount)
            
            embed = make_embed(
                title="🎪 PARTY BÚA KÉO BAO",
                description=(
                    f"💰 **Cược:** `{bet_amount:,} xu/người`\n"
                    f"👥 **Thành viên (1/8):**\n"
                    f"✅ {ctx.author.mention} đã vào\n\n"
                    f"⏳ Đang chờ thêm người..."
                ),
                color=discord.Color.blue()
            )
            view.message = await ctx.send(embed=embed, view=view)
            return

        # 4. 1v1 / BO Match Mode
        if ctx.message.mentions:
            opponent = ctx.message.mentions[0]
            if opponent.id == ctx.author.id:
                await ctx.send("❌ Bạn không thể thách đấu chính mình!")
                return
                
            # Look for bet string in args (usually args[1] or args[0] might be the mention, so we iterate)
            bet_str = None
            is_bo3 = False
            is_bo5 = False
            predict_choice = None
            
            for index, arg in enumerate(args):
                arg_clean = arg.lower()
                if "bo3" in arg_clean:
                    is_bo3 = True
                elif "bo5" in arg_clean:
                    is_bo5 = True
                elif "--keo" in arg_clean:
                    if index + 1 < len(args):
                        next_arg = args[index + 1].strip().lower()
                        if next_arg in ["bua", "búa"]:
                            predict_choice = "bua"
                        elif next_arg in ["keo", "kéo"]:
                            predict_choice = "keo"
                        elif next_arg in ["bao"]:
                            predict_choice = "bao"
                elif arg_clean.startswith("<@") or arg_clean.startswith("stats") or arg_clean.startswith("party"):
                    pass
                else:
                    # Keep the first number-like string as bet
                    if not bet_str:
                        # Strip trailing characters that might be part of bo3/bo5/--keo
                        numeric_part = ""
                        for char in arg_clean:
                            if char.isdigit() or char in ["k", "m", ".", ",", "a", "l", "-"]:
                                numeric_part += char
                        if numeric_part:
                            bet_str = numeric_part

            bet_str = bet_str or "1000"
            c_money = self.economy.get_entry(user_id)[1]
            bet_amount = parse_bet_amount(bet_str, c_money)
            
            if bet_amount < 1000:
                await ctx.send("❌ Tiền cược tối thiểu là 1,000 xu.")
                return
                
            # Pre-validate funds
            o_money = self.economy.get_entry(opponent.id)[1]
            if c_money < bet_amount:
                await ctx.send("❌ Bạn không đủ tiền cược!")
                return
            if o_money < bet_amount:
                await ctx.send(f"❌ {opponent.display_name} không đủ tiền cược!")
                return

            bo_type = "BEST OF 3" if is_bo3 else "BEST OF 5" if is_bo5 else "1v1 THÁCH ĐẤU"
            predict_text = f"\n🎯 Quyết tâm đặt trước: {get_hand_emoji(predict_choice)} (Thắng nhận x2.5 cược)" if predict_choice else ""
            
            embed = make_embed(
                title=f"⚔️ {bo_type} BÚA KÉO BAO",
                description=(
                    f"👊 **{ctx.author.mention}** vs **{opponent.mention}**\n"
                    f"💰 **Cược:** `{bet_amount:,} xu mỗi người`{predict_text}\n"
                    f"━━━━━━━━━━━━━━━━━━━━━━━━━\n"
                    f"{opponent.mention} — Bạn có chấp nhận lời thách đấu này?"
                ),
                color=discord.Color.blue()
            )
            view = BkbChallengeInviteView(self, ctx, opponent, bet_amount, is_bo3, is_bo5, predict_choice)
            view.message = await ctx.send(embed=embed, view=view)
            return

        # 5. Solo vs Bot Mode (Default)
        bet_str = args[0]
        current_money = self.economy.get_entry(user_id)[1]
        bet_amount = parse_bet_amount(bet_str, current_money)
        
        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 xu.")
            return
            
        try:
            validate_money_bet(self.economy, user_id, bet_amount)
        except Exception as e:
            await ctx.send(f"❌ {e}")
            return
            
        stats = self.economy.get_bkb_stats(user_id)
        current_streak = stats["streak"]
        streak_text = f"\n🔥 Bạn đang có chuỗi thắng {current_streak} liên tiếp!" if current_streak > 0 else ""
        
        embed = make_embed(
            title="✊✌️🖐️ BÚA KÉO BAO (Solo)",
            description=(
                f"┌──────────────────────────┐\n"
                f"│  ✊✌️🖐️  BÚA KÉO BAO    │\n"
                f"│  Cược: {bet_amount:,} xu          │\n"
                f"│  Thắng: {bet_amount*2:,} xu         │\n"
                f"└──────────────────────────┘\n"
                f"Chọn trong 15 giây!{streak_text}"
            ),
            color=discord.Color.blue()
        )
        
        view = BkbSoloView(self, ctx, bet_amount)
        view.message = await ctx.send(embed=embed, view=view)


async def setup(client: commands.Bot):
    await client.add_cog(Bkb(client))
