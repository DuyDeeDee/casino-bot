import asyncio
import logging
import random
import json
from typing import Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# Tower multipliers for each floor completed
TOWER_MULTIPLIERS = {
    1: 1.25,
    2: 1.70,
    3: 2.40,
    4: 3.60,
    5: 5.50,
    6: 8.50
}

# Floor weights/probabilities for egg spawns (0-indexed floor list from 0 to 5)
# Each entry is a list of tuples: (num_eggs, probability)
FLOOR_PROBABILITIES = {
    0: [(1, 0.90), (2, 0.10), (3, 0.00)],  # Floor 1
    1: [(1, 0.80), (2, 0.20), (3, 0.00)],  # Floor 2
    2: [(1, 0.70), (2, 0.28), (3, 0.02)],  # Floor 3
    3: [(1, 0.60), (2, 0.35), (3, 0.05)],  # Floor 4
    4: [(1, 0.45), (2, 0.45), (3, 0.10)],  # Floor 5
    5: [(1, 0.30), (2, 0.50), (3, 0.20)]   # Floor 6
}

TOWER_ACHIEVEMENTS = {
    "first_play": "🐉 Trứng Rồng Đầu Tiên (Chơi ván Tower đầu tiên)",
    "cashout_2x": "💎 Leo Tháp An Toàn (Cash out với hệ số >= 2.0x)",
    "cashout_5x": "💎 Bậc Thầy Leo Tháp (Cash out với hệ số >= 5.0x)",
    "perfect_clear": "🏆 Chinh Phục Rồng Cổ Đại (Vượt qua cả 6 tầng và thắng 8.50x)",
    "survive_3_eggs": "☠️ Sinh Tử Kỳ Tích (Vượt qua một tầng có 3 quả trứng)",
    "lucky_escape": "🍀 Thần May Mắn Gõ Cửa (Thắng một ván mà có ít nhất hai tầng xuất hiện 2 hoặc 3 trứng)"
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


def check_and_unlock_tower_achievements(stats: dict, game_info: dict) -> list[str]:
    unlocked = set(stats.get("achievements", []))
    newly_unlocked = []

    plays = stats.get("plays", 0) + 1
    if plays >= 1 and "first_play" not in unlocked:
        newly_unlocked.append("first_play")

    if game_info.get("win", False) or game_info.get("cashout", False):
        multiplier = game_info.get("multiplier", 1.0)
        
        if multiplier >= 2.0 and "cashout_2x" not in unlocked:
            newly_unlocked.append("cashout_2x")
        if multiplier >= 5.0 and "cashout_5x" not in unlocked:
            newly_unlocked.append("cashout_5x")
        if game_info.get("floors_cleared") == 6 and "perfect_clear" not in unlocked:
            newly_unlocked.append("perfect_clear")
            
        if game_info.get("survived_3_eggs", False) and "survive_3_eggs" not in unlocked:
            newly_unlocked.append("survive_3_eggs")
        if game_info.get("multi_egg_floors_count", 0) >= 2 and "lucky_escape" not in unlocked:
            newly_unlocked.append("lucky_escape")
            
    return newly_unlocked


class TowerColumnButton(discord.ui.Button):
    def __init__(self, label: str, index: int):
        super().__init__(
            label=label,
            style=discord.ButtonStyle.primary,
            custom_id=f"tower_col_{label.lower()}",
            row=0
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
            
        await interaction.response.defer()
        await self.view.process_column_selection(self.index)


class TowerCashOutButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="💵 Cash Out",
            style=discord.ButtonStyle.success,
            custom_id="tower_cash_out_btn",
            row=1,
            disabled=True
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.view.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return
            
        await interaction.response.defer()
        await self.view.process_cash_out()


class TowerGameView(discord.ui.View):
    def __init__(self, ctx: commands.Context, cog: "Tower", user_id: int, bet_amount: int):
        super().__init__(timeout=60.0)
        self.ctx = ctx
        self.cog = cog
        self.user_id = user_id
        self.bet_amount = bet_amount
        self.message: Optional[discord.Message] = None
        self.game_finished = False

        # Gameplay tracking
        self.current_floor = 0  # 0 to 5
        self.choices = [None] * 6  # Stores chosen column (0 to 3) for each floor
        self.survived_3_eggs = False
        self.multi_egg_floors_count = 0

        # Generate board: 6 floors, 4 columns
        # 0 = safe, 1 = egg (bomb)
        self.board = []
        for f_idx in range(6):
            # Choose number of eggs for this floor
            probs = FLOOR_PROBABILITIES[f_idx]
            choices = [p[0] for p in probs]
            weights = [p[1] for p in probs]
            num_eggs = random.choices(choices, weights=weights, k=1)[0]
            
            row_cells = [0] * 4
            egg_indices = random.sample(range(4), num_eggs)
            for idx in egg_indices:
                row_cells[idx] = 1
            self.board.append(row_cells)

        # Build column buttons (Row 0)
        self.column_buttons = []
        for col_idx, col_name in enumerate(["A", "B", "C", "D"]):
            btn = TowerColumnButton(label=col_name, index=col_idx)
            self.add_item(btn)
            self.column_buttons.append(btn)

        # Build Cash Out button (Row 1)
        self.cash_out_button = TowerCashOutButton()
        self.add_item(self.cash_out_button)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True

    def render_board(self, reveal_all: bool = False, hit_col: int = None, hit_floor: int = None) -> str:
        lines = []
        for floor_idx in range(5, -1, -1):
            floor_num = floor_idx + 1
            row_cells = self.board[floor_idx]
            choice_col = self.choices[floor_idx]
            
            cell_strs = []
            for col_idx in range(4):
                is_egg = (row_cells[col_idx] == 1)
                
                if reveal_all:
                    if floor_idx == hit_floor and col_idx == hit_col:
                        cell_strs.append("💥")
                    elif is_egg:
                        cell_strs.append("🥚")
                    elif choice_col == col_idx:
                        cell_strs.append("🟩")
                    else:
                        cell_strs.append("🟩")
                else:
                    if choice_col == col_idx:
                        cell_strs.append("🟩")
                    else:
                        cell_strs.append("⬜")
                        
            cells_line = " ".join(cell_strs)
            if floor_idx == self.current_floor and not reveal_all:
                lines.append(f"👉 **Tầng {floor_num}**    {cells_line}")
            else:
                lines.append(f"   **Tầng {floor_num}**    {cells_line}")
                
        return "\n".join(lines)

    async def process_column_selection(self, col_index: int):
        if self.game_finished:
            return

        self.choices[self.current_floor] = col_index
        num_eggs = sum(self.board[self.current_floor])

        # Check if they hit an egg
        if self.board[self.current_floor][col_index] == 1:
            await self.process_loss(col_index, self.current_floor)
            return

        # Safe! Track milestones
        if num_eggs == 3:
            self.survived_3_eggs = True
        if num_eggs >= 2:
            self.multi_egg_floors_count += 1

        self.current_floor += 1

        # Check if they finished the tower
        if self.current_floor == 6:
            await self.process_win()
            return

        # Enable Cash Out after passing at least Floor 1
        if self.current_floor > 0:
            self.cash_out_button.disabled = False

        await self.update_message(state="playing")

    async def process_loss(self, hit_col: int, hit_floor: int):
        self.game_finished = True
        self.stop()
        self.cog.active_users.discard(self.user_id)
        self.cog.active_games.pop(self.user_id, None)

        # Disable all UI elements
        for btn in self.column_buttons:
            btn.disabled = True
        self.remove_item(self.cash_out_button)

        # Update stats
        stats = self.cog.economy.get_tower_stats(self.user_id)
        new_achievements = list(stats["achievements"])
        newly_unlocked = check_and_unlock_tower_achievements(stats, {"win": False})
        new_achievements.extend(newly_unlocked)

        self.cog.economy.update_tower_stats(
            self.user_id,
            plays=1,
            losses=1,
            profit=-self.bet_amount,
            streak=0,
            achievements=new_achievements
        )

        board_str = self.render_board(reveal_all=True, hit_col=hit_col, hit_floor=hit_floor)
        desc = (
            f"🥚 **RỒNG ĐÃ THỨC TỈNH! BẠN THẤT BẠI!**\n\n"
            f"👤 **Người chơi:** {self.ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
            f"❌ Bạn đã chọn cột `{chr(ord('A') + hit_col)}` ở **Tầng {hit_floor + 1}** trúng Trứng Rồng!\n"
            f"📉 **Lợi nhuận:** **`-{self.bet_amount:,} VNĐ`**\n"
            f"🔥 Chuỗi thắng đã reset về `0`.\n\n"
            f"{board_str}"
        )
        embed = make_embed(
            title="🐉 DRAGON TOWER - THẤT BẠI",
            description=desc,
            color=discord.Color.red()
        )
        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{TOWER_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

        await self.message.edit(embed=embed, view=self)

    async def process_win(self):
        self.game_finished = True
        self.stop()
        self.cog.active_users.discard(self.user_id)
        self.cog.active_games.pop(self.user_id, None)

        for btn in self.column_buttons:
            btn.disabled = True
        self.remove_item(self.cash_out_button)

        multiplier = TOWER_MULTIPLIERS[6]
        payout = int(self.bet_amount * multiplier)
        net_profit = payout - self.bet_amount

        # Award payout
        self.cog.economy.add_money(self.user_id, payout)
        log_wallet_change(logger, event="tower_win_perfect", user_id=self.user_id, money_delta=payout, ctx=self.ctx)

        # Update stats
        stats = self.cog.economy.get_tower_stats(self.user_id)
        current_streak = stats.get("streak", 0)
        new_streak = current_streak + 1
        new_max_streak = max(new_streak, stats.get("max_streak", 0))

        game_info = {
            "win": True,
            "multiplier": multiplier,
            "floors_cleared": 6,
            "survived_3_eggs": self.survived_3_eggs,
            "multi_egg_floors_count": self.multi_egg_floors_count
        }

        newly_unlocked = check_and_unlock_tower_achievements(stats, game_info)
        new_achievements = list(stats["achievements"])
        new_achievements.extend(newly_unlocked)

        self.cog.economy.update_tower_stats(
            self.user_id,
            plays=1,
            wins=1,
            profit=net_profit,
            streak=new_streak,
            max_streak=new_max_streak,
            achievements=new_achievements
        )

        board_str = self.render_board(reveal_all=True)
        desc = (
            f"🏆 **CHIẾN THẮNG HOÀN MỸ! CHINH PHỤC RỒNG CỔ ĐẠI!**\n\n"
            f"👤 **Người chơi:** {self.ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
            f"📈 **Hệ số nhân:** `{multiplier:.2f}x`\n"
            f"💰 **Tổng nhận:** **`+{payout:,} VNĐ`** (Lợi nhuận: `+{net_profit:,} VNĐ`)\n"
            f"🔥 Chuỗi thắng hiện tại: `{new_streak}`\n\n"
            f"{board_str}"
        )
        embed = make_embed(
            title="🐉 DRAGON TOWER - HOÀN MỸ",
            description=desc,
            color=discord.Color.gold()
        )
        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{TOWER_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

        await self.message.edit(embed=embed, view=self)

    async def process_cash_out(self):
        self.game_finished = True
        self.stop()
        self.cog.active_users.discard(self.user_id)
        self.cog.active_games.pop(self.user_id, None)

        for btn in self.column_buttons:
            btn.disabled = True
        self.remove_item(self.cash_out_button)

        multiplier = TOWER_MULTIPLIERS[self.current_floor]
        payout = int(self.bet_amount * multiplier)
        net_profit = payout - self.bet_amount

        # Award payout
        self.cog.economy.add_money(self.user_id, payout)
        log_wallet_change(logger, event="tower_cashout", user_id=self.user_id, money_delta=payout, ctx=self.ctx)

        # Update stats
        stats = self.cog.economy.get_tower_stats(self.user_id)
        current_streak = stats.get("streak", 0)
        new_streak = current_streak + 1
        new_max_streak = max(new_streak, stats.get("max_streak", 0))

        game_info = {
            "cashout": True,
            "multiplier": multiplier,
            "floors_cleared": self.current_floor,
            "survived_3_eggs": self.survived_3_eggs,
            "multi_egg_floors_count": self.multi_egg_floors_count
        }

        newly_unlocked = check_and_unlock_tower_achievements(stats, game_info)
        new_achievements = list(stats["achievements"])
        new_achievements.extend(newly_unlocked)

        self.cog.economy.update_tower_stats(
            self.user_id,
            plays=1,
            wins=1,
            profit=net_profit,
            streak=new_streak,
            max_streak=new_max_streak,
            achievements=new_achievements
        )

        board_str = self.render_board(reveal_all=True)
        desc = (
            f"💵 **RÚT TIỀN THÀNH CÔNG (CASH OUT)!**\n\n"
            f"👤 **Người chơi:** {self.ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
            f"📈 **Hệ số nhân:** `{multiplier:.2f}x` (Đã vượt qua tầng {self.current_floor})\n"
            f"💰 **Tổng nhận:** **`+{payout:,} VNĐ`** (Lợi nhuận: `+{net_profit:,} VNĐ`)\n"
            f"🔥 Chuỗi thắng hiện tại: `{new_streak}`\n\n"
            f"{board_str}"
        )
        embed = make_embed(
            title="🐉 DRAGON TOWER - CASH OUT",
            description=desc,
            color=discord.Color.green()
        )
        if newly_unlocked:
            achievement_texts = "\n".join([f"✨ **{TOWER_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)

        await self.message.edit(embed=embed, view=self)

    async def update_message(self, state="playing"):
        board_str = self.render_board(reveal_all=False)
        
        current_mult = TOWER_MULTIPLIERS.get(self.current_floor, 1.00) if self.current_floor > 0 else 1.00
        next_mult = TOWER_MULTIPLIERS[self.current_floor + 1]
        
        current_payout = int(self.bet_amount * current_mult)
        next_payout = int(self.bet_amount * next_mult)

        # Generate warning if active floor contains exactly 3 eggs
        warning_msg = ""
        if self.current_floor < 6 and sum(self.board[self.current_floor]) == 3:
            warning_msg = (
                "\n> ☠️ **Nguy hiểm!**\n"
                "> *Bạn cảm nhận được luồng sát khí...*\n"
                "> *Có điều gì đó bất thường ở tầng này...*\n"
            )

        desc = (
            f"👤 **Người chơi:** {self.ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
            f"💰 **Bảo toàn:** `{current_payout:,} VNĐ` (`{current_mult:.2f}x`)\n"
            f"⏭️ **Tầng kế:** `{next_payout:,} VNĐ` (`{next_mult:.2f}x`)\n"
            f"{warning_msg}\n"
            f"{board_str}"
        )
        embed = make_embed(
            title="🐉 DRAGON TOWER",
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

        for btn in self.column_buttons:
            btn.disabled = True
        self.remove_item(self.cash_out_button)

        if self.current_floor > 0:
            # Auto cashout
            multiplier = TOWER_MULTIPLIERS[self.current_floor]
            payout = int(self.bet_amount * multiplier)
            net_profit = payout - self.bet_amount

            self.cog.economy.add_money(self.user_id, payout)
            log_wallet_change(logger, event="tower_timeout_cashout", user_id=self.user_id, money_delta=payout)

            stats = self.cog.economy.get_tower_stats(self.user_id)
            current_streak = stats.get("streak", 0)
            new_streak = current_streak + 1
            new_max_streak = max(new_streak, stats.get("max_streak", 0))

            game_info = {
                "cashout": True,
                "multiplier": multiplier,
                "floors_cleared": self.current_floor,
                "survived_3_eggs": self.survived_3_eggs,
                "multi_egg_floors_count": self.multi_egg_floors_count
            }

            newly_unlocked = check_and_unlock_tower_achievements(stats, game_info)
            new_achievements = list(stats["achievements"])
            new_achievements.extend(newly_unlocked)

            self.cog.economy.update_tower_stats(
                self.user_id,
                plays=1,
                wins=1,
                profit=net_profit,
                streak=new_streak,
                max_streak=new_max_streak,
                achievements=new_achievements
            )

            board_str = self.render_board(reveal_all=True)
            desc = (
                f"⏱️ **TỰ ĐỘNG CASH OUT (TIMEOUT)**\n\n"
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💵 **Tiền cược:** `{self.bet_amount:,} VNĐ`\n"
                f"📈 **Hệ số:** `{multiplier:.2f}x`\n"
                f"💰 **Tổng nhận:** **`+{payout:,} VNĐ`**\n"
                f"*Tự động rút tiền do người chơi không tương tác.*\n\n"
                f"{board_str}"
            )
            embed = make_embed(
                title="🐉 DRAGON TOWER - TỰ ĐỘNG CASH OUT",
                description=desc,
                color=discord.Color.green()
            )
            if newly_unlocked:
                achievement_texts = "\n".join([f"✨ **{TOWER_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
                embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)
        else:
            # Refund
            self.cog.economy.add_money(self.user_id, self.bet_amount)
            log_wallet_change(logger, event="tower_timeout_refund", user_id=self.user_id, money_delta=self.bet_amount)

            board_str = self.render_board(reveal_all=True)
            desc = (
                f"⏱️ **HỦY VÁN ĐẤU (TIMEOUT)**\n\n"
                f"👤 **Người chơi:** {self.ctx.author.mention}\n"
                f"💵 **Hoàn tiền:** `{self.bet_amount:,} VNĐ`\n"
                f"*Ván đấu tự động hủy và hoàn tiền do người chơi không tương tác.*\n\n"
                f"{board_str}"
            )
            embed = make_embed(
                title="🐉 DRAGON TOWER - HỦY VÁN ĐẤU",
                description=desc,
                color=discord.Color.orange()
            )

        try:
            await self.message.edit(embed=embed, view=self)
        except Exception:
            pass


class TowerLobbyView(discord.ui.View):
    def __init__(self, cog: "Tower", user_id: int):
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
        stats = self.cog.economy.get_tower_stats(self.user_id)
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
            f"🐉 **Số trận đã chơi:** `{plays}`\n"
            f"🏆 **Số trận thắng (hoặc cashout):** `{wins}`\n"
            f"❌ **Số trận thất bại:** `{losses}`\n"
            f"📈 **Tỷ lệ thắng:** `{win_rate:.1f}%`\n"
            f"🔥 **Chuỗi thắng dài nhất:** `{max_streak}`\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{streak}`\n"
            f"💸 **Tổng lợi nhuận:** `{profit_sign}{profit:,} VNĐ`\n"
        )
        embed = make_embed(
            title=f"📊 THỐNG KÊ DRAGON TOWER - {interaction.user.name.upper()}",
            description=desc,
            color=discord.Color.purple()
        )
        if achievements_list:
            ach_texts = "\n".join([f"✨ {TOWER_ACHIEVEMENTS[a]}" for a in achievements_list if a in TOWER_ACHIEVEMENTS])
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value=ach_texts, inline=False)
        else:
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value="*Chưa mở khóa thành tựu nào*", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏆 Xếp hạng", style=discord.ButtonStyle.secondary, emoji="🏆")
    async def rank_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.economy.cur.execute(
            "SELECT user_id, profit, max_streak, plays FROM user_tower ORDER BY profit DESC LIMIT 10"
        )
        rows = self.cog.economy.cur.fetchall()
        if not rows:
            await interaction.response.send_message("ℹ️ Chưa có ai xếp hạng Dragon Tower.", ephemeral=True)
            return
        desc = ""
        for i, row in enumerate(rows, 1):
            u_id, profit, max_streak, plays = row
            member = interaction.guild.get_member(u_id)
            name = member.name if member else f"ID: {u_id}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            profit_sign = "+" if profit >= 0 else ""
            desc += f"{medal} **{name}** • Lợi nhuận: `{profit_sign}{profit:,} VNĐ` • Chuỗi thắng dài nhất: `{max_streak}` *(Lượt chơi: {plays})*\n"
        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG CAO THỦ DRAGON TOWER",
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


class Tower(commands.Cog, name="Tower"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.active_users = set()
        self.active_games = {}  # user_id -> TowerGameView

    @commands.command(
        brief="Chơi game Dragon Tower - leo tháp tránh trứng rồng để nhận thưởng.",
        usage="tower [tiền cược]",
        aliases=["t", "dragontower"]
    )
    async def tower(self, ctx: commands.Context, bet_amount_str: str = None):
        user_id = ctx.author.id
        
        if bet_amount_str is None:
            view = TowerLobbyView(self, user_id)
            embed = make_embed(
                title="🐉 SẢNH CHỜ DRAGON TOWER",
                description=(
                    "Tháp gồm **4 cột (A, B, C, D) × 6 tầng**. Hãy cẩn thận di chuyển từ tầng 1 đến tầng 6, "
                    "tránh những quả Trứng Rồng để không đánh thức Rồng Mẹ!\n\n"
                    "🔥 **Điều thú vị:** Càng lên cao, số trứng xuất hiện ngẫu nhiên ở mỗi tầng càng nhiều (từ 1 đến 3 quả).\n"
                    "☠️ **Đặc biệt:** Nếu tầng tiếp theo có **3 quả trứng** (xác suất sống chỉ 25%), bạn sẽ cảm nhận được luồng sát khí bất thường!\n\n"
                    "💵 **Bảng hệ số nhân:**\n"
                    "• Tầng 1: `1.25x`\n"
                    "• Tầng 2: `1.70x`\n"
                    "• Tầng 3: `2.40x`\n"
                    "• Tầng 4: `3.60x`\n"
                    "• Tầng 5: `5.50x`\n"
                    "• Tầng 6: `8.50x` (Chinh Phục Rồng Cổ Đại)\n\n"
                    "👉 **Cú pháp chơi:** `i?tower <tiền cược>`\n"
                    "👉 **Ví dụ:** `i?tower 100k` hoặc `i?tower all`\n\n"
                    "Chọn một nút bấm dưới đây để xem chỉ số của bạn:"
                ),
                color=discord.Color.purple()
            )
            embed.set_footer(text="🎰 Casino Bot • Dragon Tower")
            view.message = await ctx.send(embed=embed, view=view)
            return

        if user_id in self.active_users:
            await ctx.send("❌ **Lỗi:** Bạn đang có một ván Dragon Tower đang diễn ra. Vui lòng hoàn thành ván đấu hiện tại!")
            return

        current_money = self.economy.get_entry(user_id)[1]
        bet_amount = parse_bet_amount(bet_amount_str, current_money)

        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 VNĐ.")
            return

        try:
            validate_money_bet(self.economy, user_id, bet_amount)
            self.economy.add_money(user_id, -bet_amount)
            log_wallet_change(logger, event="tower_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
        except Exception as e:
            await ctx.send(f"❌ {e}")
            return

        # Start game view
        self.active_users.add(user_id)
        view = TowerGameView(ctx, self, user_id, bet_amount)
        self.active_games[user_id] = view

        # Display initial embed
        next_mult = TOWER_MULTIPLIERS[1]
        next_payout = int(bet_amount * next_mult)
        
        warning_msg = ""
        # Check warning for floor 1 (though floor 1 weight for 3 eggs is 0%, we keep it generic)
        if sum(view.board[0]) == 3:
            warning_msg = (
                "\n> ☠️ **Nguy hiểm!**\n"
                "> *Bạn cảm nhận được luồng sát khí...*\n"
                "> *Có điều gì đó bất thường ở tầng này...*\n"
            )

        board_str = view.render_board(reveal_all=False)
        desc = (
            f"👤 **Người chơi:** {ctx.author.mention}\n"
            f"💵 **Tiền cược:** `{bet_amount:,} VNĐ`\n"
            f"💰 **Bảo toàn:** `0 VNĐ` (`1.00x`)\n"
            f"⏭️ **Tầng kế:** `{next_payout:,} VNĐ` (`{next_mult:.2f}x`)\n"
            f"{warning_msg}\n"
            f"{board_str}"
        )
        embed = make_embed(
            title="🐉 DRAGON TOWER",
            description=desc,
            color=discord.Color.purple()
        )
        
        view.message = await ctx.send(embed=embed, view=view)


async def setup(bot: commands.Bot):
    await bot.add_cog(Tower(bot))
