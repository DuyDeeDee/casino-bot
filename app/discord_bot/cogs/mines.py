import asyncio
import logging
import random
from typing import Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# Multipliers mapping: Bombs -> [multipliers list from 1st safe cell to last]
MINES_MULTIPLIERS = {
    1: [1.07, 1.21, 1.38, 1.60, 1.90, 2.30, 3.10, 5.00],
    2: [1.19, 1.48, 1.88, 2.45, 3.35, 4.90, 8.20],
    3: [1.35, 1.90, 2.80, 4.30, 7.00, 12.00],  # User's exact example
    4: [1.55, 2.50, 4.25, 7.80, 16.00],
    5: [1.85, 3.60, 7.80, 20.00],
    6: [2.30, 5.80, 18.00],
    7: [3.10, 11.50],
    8: [7.50]
}

MINES_ACHIEVEMENTS = {
    "first_play": "🏅 Chơi Mines lần đầu (Chơi ván đầu tiên)",
    "cashout_3x": "💎 Cash Out 3x (Cash Out với hệ số >= 3.0x)",
    "cashout_5x": "💎 Cash Out 5x (Cash Out với hệ số >= 5.0x)",
    "cashout_10x": "👑 Cash Out 10x (Cash Out với hệ số >= 10.0x)",
    "survive_7_bombs": "☠️ Sống sót với 7 bom (Thắng ván chơi có 7 bom)",
    "clear_all_safe": "🔥 Mở toàn bộ ô an toàn (Mở sạch ô an toàn và thắng)"
}

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


def index_to_coordinate(index: int) -> str:
    row = index // 3 + 1
    col = chr(ord('A') + index % 3)
    return f"{col}{row}"

def check_and_unlock_mines_achievements(stats: dict, game_info: dict) -> list[str]:
    unlocked = set(stats.get("achievements", []))
    newly_unlocked = []

    plays = stats.get("plays", 0) + 1  # current play is already counted in stats parameter if not in DB
    
    if plays >= 1 and "first_play" not in unlocked:
        newly_unlocked.append("first_play")
        
    if game_info.get("win", False):
        multiplier = game_info.get("multiplier", 0.0)
        bombs = game_info.get("bombs", 0)
        opened_cells = game_info.get("opened_cells", 0)
        total_safe_cells = 9 - bombs
        
        if multiplier >= 3.0 and "cashout_3x" not in unlocked:
            newly_unlocked.append("cashout_3x")
        if multiplier >= 5.0 and "cashout_5x" not in unlocked:
            newly_unlocked.append("cashout_5x")
        if multiplier >= 10.0 and "cashout_10x" not in unlocked:
            newly_unlocked.append("cashout_10x")
        if bombs == 7 and "survive_7_bombs" not in unlocked:
            newly_unlocked.append("survive_7_bombs")
        if opened_cells == total_safe_cells and "clear_all_safe" not in unlocked:
            newly_unlocked.append("clear_all_safe")
            
    return newly_unlocked


class MinesCellButton(discord.ui.Button):
    def __init__(self, index: int, row: int):
        super().__init__(
            label="?",
            style=discord.ButtonStyle.secondary,
            row=row,
            custom_id=f"mines_cell_{index}"
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
            
        await interaction.response.defer()
        await self.view.process_cell_selection(self.index)


class MinesGameView(discord.ui.View):
    def __init__(self, ctx: commands.Context, cog: "Mines", user_id: int, bet_amount: int, num_bombs: int):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.num_bombs = num_bombs
        self.message: Optional[discord.Message] = None
        self.game_finished = False

        # Initialize board: 0 = safe, 1 = bomb
        self.board = [0] * 9
        bomb_indices = random.sample(range(9), num_bombs)
        for idx in bomb_indices:
            self.board[idx] = 1

        # Random safe cell designated as the Lucky Gem
        safe_indices = [i for i in range(9) if self.board[i] == 0]
        self.lucky_gem_index = random.choice(safe_indices)

        self.states = ["unopened"] * 9
        self.opened_count = 0
        self.lucky_gem_found = False

        # Build dynamic 3x3 buttons
        self.buttons = []
        for i in range(9):
            row = i // 3
            btn = MinesCellButton(index=i, row=row)
            self.add_item(btn)
            self.buttons.append(btn)

        # Add Cash Out button in row 3
        self.cash_out_button = discord.ui.Button(
            label="💵 Cash Out",
            style=discord.ButtonStyle.success,
            row=3,
            disabled=True,
            custom_id="mines_cash_out_btn"
        )
        self.cash_out_button.callback = self.cash_out_callback
        self.add_item(self.cash_out_button)

        # Temporary variables for payout calculation
        self.final_payout = 0
        self.new_streak = 0
        self.multiplier = 0.0
        self.base_payout = 0
        self.gem_bonus = 0
        self.streak_bonus = 0

        # Double or nothing choice cards
        self.winning_card = -1
        self.double_button = None
        self.claim_button = None
        self.card_left_button = None
        self.card_right_button = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True

    def reveal_all_cells(self):
        for idx, btn in enumerate(self.buttons):
            btn.disabled = True
            if self.board[idx] == 1:
                btn.emoji = "💣"
                btn.label = None
                btn.style = discord.ButtonStyle.danger
            else:
                if idx == self.lucky_gem_index:
                    btn.emoji = "💎"
                    btn.label = None
                    btn.style = discord.ButtonStyle.primary
                else:
                    btn.emoji = "🟩"
                    btn.label = None
                    btn.style = discord.ButtonStyle.success

    async def process_cell_selection(self, index: int):
        if self.game_finished:
            return

        self.states[index] = "opened"
        self.opened_count += 1

        gem_found = (index == self.lucky_gem_index)
        if gem_found:
            self.lucky_gem_found = True

        # Check if bomb
        if self.board[index] == 1:
            await self.process_boom(index)
            return

        # Check if all safe cells are opened
        total_safe = 9 - self.num_bombs
        if self.opened_count == total_safe:
            await self.process_perfect_win()
            return

        # Update button look
        btn = self.buttons[index]
        if gem_found:
            btn.emoji = "💎"
            btn.label = None
            btn.style = discord.ButtonStyle.primary
        else:
            btn.emoji = "🟩"
            btn.label = None
            btn.style = discord.ButtonStyle.success
        btn.disabled = True

        if self.opened_count > 0:
            self.cash_out_button.disabled = False

        await self.update_message_content(state="playing", gem_found=gem_found)

    async def process_boom(self, boom_index: int):
        self.game_finished = True
        self.stop()
        self.cog.active_users.discard(self.user_id)
        self.cog.active_games.pop(self.user_id, None)

        self.reveal_all_cells()
        self.buttons[boom_index].emoji = "💥"
        self.remove_item(self.cash_out_button)

        # Update stats in database
        stats = self.cog.economy.get_mines_stats(self.user_id)
        new_achievements = list(stats["achievements"])
        newly_unlocked = check_and_unlock_mines_achievements(stats, {"win": False, "bombs": self.num_bombs})
        new_achievements.extend(newly_unlocked)

        self.cog.economy.update_mines_stats(
            self.user_id,
            plays=1,
            losses=1,
            profit=-self.bet_amount,
            streak=0,
            achievements=new_achievements
        )

        desc = (
            f"💥 **BOOM! BẠN ĐÃ MỞ TRÚNG BOM!**\n"
            f"👤 **Người chơi:** {self.ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n\n"
            f"❌ Bạn đã mở trúng ô bom ở vị trí `{index_to_coordinate(boom_index)}`. Trò chơi kết thúc!\n"
            f"📉 **Mất:** **`-{self.bet_amount:,} VNĐ`**\n"
            f"🔥 Chuỗi thắng đã bị reset về `0`."
        )

        embed = make_embed(
            title="💣 TRÒ CHƠI MINES - THẤT BẠI",
            description=desc,
            color=discord.Color.red()
        )

        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{MINES_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

        await self.message.edit(embed=embed, view=self)

    async def process_perfect_win(self):
        self.game_finished = True
        self.stop()
        self.cog.active_users.discard(self.user_id)
        self.cog.active_games.pop(self.user_id, None)

        self.reveal_all_cells()
        self.remove_item(self.cash_out_button)

        multiplier = MINES_MULTIPLIERS[self.num_bombs][self.opened_count - 1]
        base_payout = int(self.bet_amount * multiplier)
        
        gem_bonus = 0
        if self.lucky_gem_found:
            gem_bonus = int(self.bet_amount * 0.20)
            
        payout = base_payout + gem_bonus
        
        stats = self.cog.economy.get_mines_stats(self.user_id)
        current_streak = stats.get("streak", 0)
        new_streak = current_streak + 1
        
        streak_bonus_percent = 0.0
        if new_streak >= 10:
            streak_bonus_percent = 0.10
        elif new_streak >= 5:
            streak_bonus_percent = 0.05
        elif new_streak >= 3:
            streak_bonus_percent = 0.02
            
        streak_bonus = int(payout * streak_bonus_percent)
        final_payout = payout + streak_bonus

        # Credit payout to wallet
        self.cog.economy.add_money(self.user_id, final_payout)
        log_wallet_change(logger, event="mines_perfect_win", user_id=self.user_id, money_delta=final_payout, ctx=self.ctx)

        new_max_streak = max(stats["max_streak"], new_streak)
        game_info = {
            "win": True,
            "multiplier": multiplier,
            "bombs": self.num_bombs,
            "opened_cells": self.opened_count
        }
        newly_unlocked = check_and_unlock_mines_achievements(stats, game_info)
        new_achievements = list(stats["achievements"])
        new_achievements.extend(newly_unlocked)

        self.cog.economy.update_mines_stats(
            self.user_id,
            plays=1,
            wins=1,
            profit=final_payout - self.bet_amount,
            streak=new_streak,
            max_streak=new_max_streak,
            achievements=new_achievements
        )

        desc = (
            f"👑 **HOÀN THÀNH TOÀN BỘ Ô AN TOÀN! VICTORY PERFECT!**\n"
            f"👤 **Người chơi:** {self.ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
            f"📈 **Hệ số tối đa:** `{multiplier:.2f}x`\n"
            f"💰 **Tiền thưởng cơ bản:** `{base_payout:,} VNĐ`\n"
        )
        if self.lucky_gem_found:
            desc += f"💎 **Lucky Gem Bonus:** `+{gem_bonus:,} VNĐ` (+20%)\n"
        if streak_bonus > 0:
            desc += f"🔥 **Chuỗi thắng ({new_streak}):** `+{streak_bonus:,} VNĐ`\n"
            
        desc += f"\n💵 **Tổng nhận:** **`+{final_payout:,} VNĐ`**"

        embed = make_embed(
            title="💣 TRÒ CHƠI MINES - HOÀN MỸ",
            description=desc,
            color=discord.Color.gold()
        )
        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{MINES_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

        await self.message.edit(embed=embed, view=self)

    async def cash_out_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.process_cashout_decision()

    async def process_cashout_decision(self):
        self.game_finished = True
        self.cog.active_users.discard(self.user_id)
        self.cog.active_games.pop(self.user_id, None)

        multiplier = MINES_MULTIPLIERS[self.num_bombs][self.opened_count - 1]
        base_payout = int(self.bet_amount * multiplier)
        
        gem_bonus = 0
        if self.lucky_gem_found:
            gem_bonus = int(self.bet_amount * 0.20)
            
        payout = base_payout + gem_bonus
        
        stats = self.cog.economy.get_mines_stats(self.user_id)
        current_streak = stats.get("streak", 0)
        new_streak = current_streak + 1
        
        streak_bonus_percent = 0.0
        if new_streak >= 10:
            streak_bonus_percent = 0.10
        elif new_streak >= 5:
            streak_bonus_percent = 0.05
        elif new_streak >= 3:
            streak_bonus_percent = 0.02
            
        streak_bonus = int(payout * streak_bonus_percent)
        self.final_payout = payout + streak_bonus
        self.new_streak = new_streak
        
        self.multiplier = multiplier
        self.base_payout = base_payout
        self.gem_bonus = gem_bonus
        self.streak_bonus = streak_bonus
        
        self.reveal_all_cells()
        self.remove_item(self.cash_out_button)
        
        self.double_button = discord.ui.Button(
            label="🎲 Double or Nothing",
            style=discord.ButtonStyle.primary,
            row=3,
            custom_id="mines_double_button"
        )
        self.double_button.callback = self.double_or_nothing_callback
        
        self.claim_button = discord.ui.Button(
            label="💵 Nhận Tiền",
            style=discord.ButtonStyle.success,
            row=3,
            custom_id="mines_claim_button"
        )
        self.claim_button.callback = self.claim_callback
        
        self.add_item(self.double_button)
        self.add_item(self.claim_button)
        
        await self.update_message_content(state="cashout_decision")

    async def double_or_nothing_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.process_double_or_nothing_start()

    async def process_double_or_nothing_start(self):
        self.remove_item(self.double_button)
        self.remove_item(self.claim_button)
        
        self.winning_card = random.randint(0, 1)
        
        self.card_left_button = discord.ui.Button(
            label="🃏 Lá bài bên Trái",
            style=discord.ButtonStyle.primary,
            row=3,
            custom_id="mines_card_left"
        )
        self.card_left_button.callback = self.card_left_callback
        
        self.card_right_button = discord.ui.Button(
            label="🃏 Lá bài bên Phải",
            style=discord.ButtonStyle.primary,
            row=3,
            custom_id="mines_card_right"
        )
        self.card_right_button.callback = self.card_right_callback
        
        self.add_item(self.card_left_button)
        self.add_item(self.card_right_button)
        
        await self.update_message_content(state="double_or_nothing")

    async def card_left_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
        await self.process_double_choice(interaction, clicked_index=0)

    async def card_right_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
        await self.process_double_choice(interaction, clicked_index=1)

    async def process_double_choice(self, interaction: discord.Interaction, clicked_index: int):
        await interaction.response.defer()
        self.stop()
        
        is_win = (clicked_index == self.winning_card)
        
        self.remove_item(self.card_left_button)
        self.remove_item(self.card_right_button)
        
        left_emoji = "✅" if self.winning_card == 0 else "❌"
        right_emoji = "✅" if self.winning_card == 1 else "❌"
        
        self.card_left_button = discord.ui.Button(
            label=f"{left_emoji} Lá bài bên Trái",
            style=discord.ButtonStyle.success if self.winning_card == 0 else discord.ButtonStyle.danger,
            row=3,
            disabled=True
        )
        self.card_right_button = discord.ui.Button(
            label=f"{right_emoji} Lá bài bên Phải",
            style=discord.ButtonStyle.success if self.winning_card == 1 else discord.ButtonStyle.danger,
            row=3,
            disabled=True
        )
        self.add_item(self.card_left_button)
        self.add_item(self.card_right_button)
        
        stats = self.cog.economy.get_mines_stats(self.user_id)
        new_achievements = list(stats["achievements"])
        
        if is_win:
            doubled_payout = self.final_payout * 2
            self.cog.economy.add_money(self.user_id, doubled_payout)
            log_wallet_change(logger, event="mines_double_win", user_id=self.user_id, money_delta=doubled_payout, ctx=self.ctx)
            
            new_max_streak = max(stats["max_streak"], self.new_streak)
            game_info = {
                "win": True,
                "multiplier": self.multiplier * 2,
                "bombs": self.num_bombs,
                "opened_cells": self.opened_count
            }
            newly_unlocked = check_and_unlock_mines_achievements(stats, game_info)
            new_achievements.extend(newly_unlocked)
            
            self.cog.economy.update_mines_stats(
                self.user_id,
                plays=1,
                wins=1,
                profit=doubled_payout - self.bet_amount,
                streak=self.new_streak,
                max_streak=new_max_streak,
                achievements=new_achievements
            )
            
            desc = (
                f"🎉 **DOUBLE OR NOTHING THÀNH CÔNG!**\n"
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💵 **Tiền cược gốc:** `{self.bet_amount:,} VNĐ`\n"
                f"📈 **Hệ số cược gốc:** `{self.multiplier:.2f}x`\n"
                f"🃏 **Lựa chọn:** Lá bài {'bên Trái' if clicked_index == 0 else 'bên Phải'} (Chính Xác!)\n\n"
                f"💰 **Số tiền trước khi Double:** `{self.final_payout:,} VNĐ`\n"
                f"💵 **Tổng nhận nhân đôi:** **`+{doubled_payout:,} VNĐ`**"
            )
            embed = make_embed(
                title="🎲 DOUBLE OR NOTHING - CHIẾN THẮNG",
                description=desc,
                color=discord.Color.green()
            )
            if newly_unlocked:
                achievement_texts = "\n".join([f"✨ **{MINES_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
                embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)
        else:
            self.cog.economy.update_mines_stats(
                self.user_id,
                plays=1,
                losses=1,
                profit=-self.bet_amount,
                streak=0
            )
            
            desc = (
                f"💀 **DOUBLE OR NOTHING THẤT BẠI!**\n"
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💵 **Tiền cược gốc:** `{self.bet_amount:,} VNĐ`\n"
                f"🃏 **Lựa chọn:** Lá bài {'bên Trái' if clicked_index == 0 else 'bên Phải'} (Sai mất rồi!)\n\n"
                f"💥 Bạn đã mất toàn bộ tiền thắng của ván chơi này!\n"
                f"📉 **Thua:** **`-{self.bet_amount:,} VNĐ`**\n"
                f"🔥 Chuỗi thắng đã bị reset về `0`."
            )
            embed = make_embed(
                title="🎲 DOUBLE OR NOTHING - THẤT BẠI",
                description=desc,
                color=discord.Color.red()
            )
            
        await self.message.edit(embed=embed, view=self)

    async def claim_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
        await interaction.response.defer()
        self.stop()
        await self.process_cashout_claim()

    async def process_cashout_claim(self):
        self.cog.economy.add_money(self.user_id, self.final_payout)
        log_wallet_change(logger, event="mines_win", user_id=self.user_id, money_delta=self.final_payout, ctx=self.ctx)
        
        stats = self.cog.economy.get_mines_stats(self.user_id)
        new_max_streak = max(stats["max_streak"], self.new_streak)
        game_info = {
            "win": True,
            "multiplier": self.multiplier,
            "bombs": self.num_bombs,
            "opened_cells": self.opened_count
        }
        newly_unlocked = check_and_unlock_mines_achievements(stats, game_info)
        new_achievements = list(stats["achievements"])
        new_achievements.extend(newly_unlocked)
        
        self.cog.economy.update_mines_stats(
            self.user_id,
            plays=1,
            wins=1,
            profit=self.final_payout - self.bet_amount,
            streak=self.new_streak,
            max_streak=new_max_streak,
            achievements=new_achievements
        )
        
        self.remove_item(self.double_button)
        self.remove_item(self.claim_button)
        
        desc = (
            f"✅ **CASH OUT THÀNH CÔNG!**\n"
            f"👤 **Người chơi:** {self.ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
            f"📈 **Hệ số mở ô:** `{self.multiplier:.2f}x`\n"
            f"💰 **Tiền thưởng cơ bản:** `{self.base_payout:,} VNĐ`\n"
        )
        if self.lucky_gem_found:
            desc += f"💎 **Lucky Gem Bonus:** `+{self.gem_bonus:,} VNĐ` (+20%)\n"
        if self.streak_bonus > 0:
            desc += f"🔥 **Chuỗi thắng ({self.new_streak}):** `+{self.streak_bonus:,} VNĐ`\n"
            
        desc += f"\n💵 **Tổng nhận:** **`+{self.final_payout:,} VNĐ`**"
        
        embed = make_embed(
            title="💣 TRÒ CHƠI MINES - CHIẾN THẮNG",
            description=desc,
            color=discord.Color.green()
        )
        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{MINES_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)
            
        await self.message.edit(embed=embed, view=self)

    async def update_message_content(self, state: str = "playing", gem_found: bool = False):
        user_mention = self.ctx.author.mention
        
        if state == "playing":
            if self.opened_count == 0:
                current_mult = 0.0
                current_payout = 0
                next_mult = MINES_MULTIPLIERS[self.num_bombs][0]
                next_payout = int(self.bet_amount * next_mult)
            else:
                current_mult = MINES_MULTIPLIERS[self.num_bombs][self.opened_count - 1]
                current_payout = int(self.bet_amount * current_mult)
                
                total_safe = 9 - self.num_bombs
                if self.opened_count < total_safe:
                    next_mult = MINES_MULTIPLIERS[self.num_bombs][self.opened_count]
                    next_payout = int(self.bet_amount * next_mult)
                else:
                    next_mult = 0.0
                    next_payout = 0
                    
            desc = (
                f"👤 **Người chơi:** {user_mention}\n"
                f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`  💣 **Số Bom:** `{self.num_bombs}`\n"
            )
            
            desc += f"💰 **Cash Out:** `{current_payout:,} VNĐ` (`{current_mult:.2f}x`)\n"
            if next_payout > 0:
                desc += f"⏭️ **Tiếp theo:** `{next_payout:,} VNĐ` (`{next_mult:.2f}x`)\n"
            else:
                desc += f"⏭️ **Tiếp theo:** `N/A`\n"
                
            if self.lucky_gem_found:
                desc += f"💎 **Lucky Gem Bonus:** `+{int(self.bet_amount * 0.20):,} VNĐ` (+20%)\n"
                
            if gem_found:
                desc += f"\n💎 ✨ **Lucky Gem!** Bạn đã mở được Kim Cương Vàng! Nhận thêm `+20%` tiền cược nếu cash out thành công!"
                
            embed = make_embed(
                title="💣 TRÒ CHƠI MINES (3x3)",
                description=desc,
                color=discord.Color.purple()
            )
            
        elif state == "cashout_decision":
            desc = (
                f"💰 **BẠN ĐÃ CASH OUT THÀNH CÔNG!**\n"
                f"👤 **Người chơi:** {user_mention}\n"
                f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
                f"📈 **Hệ số cược:** `{self.multiplier:.2f}x`\n"
                f"💰 **Tiền thưởng cơ bản:** `{self.base_payout:,} VNĐ`\n"
            )
            if self.lucky_gem_found:
                desc += f"💎 **Lucky Gem Bonus:** `+{self.gem_bonus:,} VNĐ` (+20%)\n"
            if self.streak_bonus > 0:
                desc += f"🔥 **Chuỗi thắng ({self.new_streak}):** `+{self.streak_bonus:,} VNĐ`\n"
                
            desc += (
                f"\n💵 **Tổng nhận hiện tại:** **`{self.final_payout:,} VNĐ`**\n\n"
                f"🎲 **CƠ HỘI NHÂN ĐÔI:** Bạn muốn nhận luôn tiền cược hay thử thách nhân đôi số tiền thưởng với **Double or Nothing**?"
            )
            embed = make_embed(
                title="💣 MINES - QUYẾT ĐỊNH CASH OUT",
                description=desc,
                color=discord.Color.blue()
            )
            
        elif state == "double_or_nothing":
            desc = (
                f"🃏 **DOUBLE OR NOTHING**\n"
                f"👤 **Người chơi:** {user_mention}\n"
                f"💵 **Tiền thưởng hiện tại:** `{self.final_payout:,} VNĐ`\n\n"
                f"🂠   🂠\n\n"
                f"Hãy click chọn **một trong hai lá bài** ở bên dưới. Chọn đúng lá thành công sẽ nhân đôi số tiền (`{self.final_payout * 2:,} VNĐ`). Chọn sai sẽ mất sạch tiền thắng!"
            )
            embed = make_embed(
                title="🎲 DOUBLE OR NOTHING - CHỌN BÀI",
                description=desc,
                color=discord.Color.purple()
            )
            
        await self.message.edit(embed=embed, view=self)

    async def on_timeout(self):
        if self.game_finished:
            return
        self.game_finished = True
        self.stop()
        self.cog.active_users.discard(self.user_id)
        self.cog.active_games.pop(self.user_id, None)
        
        self.reveal_all_cells()
        for child in self.children:
            child.disabled = True
            
        if self.opened_count == 0:
            self.cog.economy.add_money(self.user_id, self.bet_amount)
            log_wallet_change(logger, event="mines_timeout_refund", user_id=self.user_id, money_delta=self.bet_amount)
            
            embed = make_embed(
                title="⏱️ VÁN CHƠI BỊ HỦY",
                description=f"👤 **Người chơi:** {self.ctx.author.mention}\n\n*Hết thời gian chờ (60s) mà không mở ô nào. Tiền cược đã được hoàn lại.*",
                color=discord.Color.red()
            )
            await self.message.edit(embed=embed, view=self)
        else:
            # Auto cashout
            multiplier = MINES_MULTIPLIERS[self.num_bombs][self.opened_count - 1]
            base_payout = int(self.bet_amount * multiplier)
            
            gem_bonus = 0
            if self.lucky_gem_found:
                gem_bonus = int(self.bet_amount * 0.20)
                
            payout = base_payout + gem_bonus
            
            stats = self.cog.economy.get_mines_stats(self.user_id)
            current_streak = stats.get("streak", 0)
            new_streak = current_streak + 1
            
            streak_bonus_percent = 0.0
            if new_streak >= 10:
                streak_bonus_percent = 0.10
            elif new_streak >= 5:
                streak_bonus_percent = 0.05
            elif new_streak >= 3:
                streak_bonus_percent = 0.02
                
            streak_bonus = int(payout * streak_bonus_percent)
            final_payout = payout + streak_bonus
            
            self.cog.economy.add_money(self.user_id, final_payout)
            log_wallet_change(logger, event="mines_timeout_cashout", user_id=self.user_id, money_delta=final_payout)
            
            new_max_streak = max(stats["max_streak"], new_streak)
            game_info = {
                "win": True,
                "multiplier": multiplier,
                "bombs": self.num_bombs,
                "opened_cells": self.opened_count
            }
            newly_unlocked = check_and_unlock_mines_achievements(stats, game_info)
            new_achievements = list(stats["achievements"])
            new_achievements.extend(newly_unlocked)
            
            self.cog.economy.update_mines_stats(
                self.user_id,
                plays=1,
                wins=1,
                profit=final_payout - self.bet_amount,
                streak=new_streak,
                max_streak=new_max_streak,
                achievements=new_achievements
            )
            
            desc = (
                f"⏱️ **TỰ ĐỘNG CASH OUT (TIMEOUT)**\n"
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
                f"📈 **Hệ số:** `{multiplier:.2f}x`\n"
                f"💰 **Tổng nhận:** **`+{final_payout:,} VNĐ`**\n"
                f"*Tự động cash out do người chơi không tương tác.*"
            )
            embed = make_embed(
                title="💣 TRÒ CHƠI MINES - TỰ ĐỘNG CASH OUT",
                description=desc,
                color=discord.Color.green()
            )
            if newly_unlocked:
                achievement_texts = "\n".join([f"✨ **{MINES_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
                embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)
                
            await self.message.edit(embed=embed, view=self)


class MinesLobbyView(discord.ui.View):
    def __init__(self, cog: "Mines", user_id: int):
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
        stats = self.cog.economy.get_mines_stats(self.user_id)
        plays = stats["plays"]
        wins = stats["wins"]
        losses = stats["losses"]
        profit = stats["profit"]
        streak = stats["streak"]
        max_streak = stats["max_streak"]
        achievements_list = stats["achievements"]
        
        win_rate = (wins / plays * 100) if plays > 0 else 0.0
        profit_sign = "+" if profit >= 0 else ""
        
        desc = (
            f"💣 **Số trận đã chơi:** `{plays}`\n"
            f"🏆 **Số trận thắng:** `{wins}`\n"
            f"❌ **Số trận thua:** `{losses}`\n"
            f"📈 **Tỷ lệ thắng:** `{win_rate:.1f}%`\n"
            f"🔥 **Chuỗi thắng dài nhất:** `{max_streak}`\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{streak}`\n"
            f"💸 **Tổng lợi nhuận:** `{profit_sign}{profit:,} VNĐ`\n"
        )
        embed = make_embed(
            title=f"📊 THỐNG KÊ MINES - {interaction.user.name.upper()}",
            description=desc,
            color=discord.Color.purple()
        )
        if achievements_list:
            ach_texts = "\n".join([f"✨ {MINES_ACHIEVEMENTS[a]}" for a in achievements_list if a in MINES_ACHIEVEMENTS])
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value=ach_texts, inline=False)
        else:
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value="*Chưa mở khóa thành tựu nào*", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏆 Xếp hạng", style=discord.ButtonStyle.secondary, emoji="🏆")
    async def rank_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.economy.cur.execute(
            "SELECT user_id, profit, max_streak, plays FROM user_mines ORDER BY profit DESC LIMIT 10"
        )
        rows = self.cog.economy.cur.fetchall()
        if not rows:
            await interaction.response.send_message("ℹ️ Chưa có ai xếp hạng Mines.", ephemeral=True)
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
            title="🏆 BẢNG XẾP HẠNG CAO THỦ MINES",
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


class Mines(commands.Cog, name="Mines"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.active_users = set()
        self.active_games = {} # user_id -> MinesGameView

    @commands.command(
        brief="Chơi trò chơi Mines 3x3 tương tác bằng nút bấm.",
        usage="mines [tiền cược] [số bom]",
        aliases=["m"]
    )
    async def mines(self, ctx: commands.Context, bet_amount_str: str = None, bombs_str: str = None):
        user_id = ctx.author.id
        
        if bet_amount_str is None:
            view = MinesLobbyView(self, user_id)
            embed = make_embed(
                title="💣 SẢNH CHỜ MINES (3x3)",
                description=(
                    "Bàn chơi gồm **9 ô (3x3)** chứa Bom và Kim Cương. Hãy cẩn thận mở từng ô an toàn để tích lũy hệ số nhân và nhận thưởng lớn!\n\n"
                    "👉 **Cú pháp chơi:** `i?mines <tiền cược> <số bom>`\n"
                    "👉 **Ví dụ:** `i?mines 100k 3` hoặc `i?mines 10k 5`\n\n"
                    "Chọn một nút bấm dưới đây để xem chỉ số của bạn:"
                ),
                color=discord.Color.purple()
            )
            embed.set_footer(text="🎰 Casino Bot • Mines 3x3")
            view.message = await ctx.send(embed=embed, view=view)
            return

        if user_id in self.active_users:
            await ctx.send("❌ **Lỗi:** Bạn đã có một ván Mines đang diễn ra. Vui lòng hoàn thành ván chơi hiện tại!")
            return

        # Parse number of bombs
        if bombs_str is None:
            await ctx.send("❌ Vui lòng nhập số bom (từ 1 đến 8).\nVí dụ: `i?mines 10k 3`")
            return

        try:
            num_bombs = int(bombs_str)
        except ValueError:
            await ctx.send("❌ Số bom phải là một số nguyên từ 1 đến 8.")
            return

        if num_bombs < 1 or num_bombs > 8:
            await ctx.send("❌ Số bom không hợp lệ! Vui lòng chọn từ 1 đến 8 bom.")
            return

        current_money = self.economy.get_entry(user_id)[1]
        bet_amount = parse_bet_amount(bet_amount_str, current_money)
        
        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 VNĐ.")
            return

        try:
            validate_money_bet(self.economy, user_id, bet_amount)
            self.economy.add_money(user_id, -bet_amount)
            log_wallet_change(logger, event="mines_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
        except Exception as e:
            await ctx.send(f"❌ {e}")
            return

        # Start game view
        self.active_users.add(user_id)
        view = MinesGameView(ctx, self, user_id, bet_amount, num_bombs)
        self.active_games[user_id] = view

        # Display initial embed
        next_mult = MINES_MULTIPLIERS[num_bombs][0]
        next_payout = int(bet_amount * next_mult)
        
        desc = (
            f"👤 **Người chơi:** {ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{bet_amount:,} VNĐ`  💣 **Số Bom:** `{num_bombs}`\n"
            f"💰 **Cash Out:** `0 VNĐ` (`0.00x`)\n"
            f"⏭️ **Tiếp theo:** `{next_payout:,} VNĐ` (`{next_mult:.2f}x`)\n"
        )
        embed = make_embed(
            title="💣 TRÒ CHƠI MINES (3x3)",
            description=desc,
            color=discord.Color.purple()
        )
        
        view.message = await ctx.send(embed=embed, view=view)



async def setup(bot: commands.Bot):
    await bot.add_cog(Mines(bot))
