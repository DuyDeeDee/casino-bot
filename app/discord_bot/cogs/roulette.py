import asyncio
from datetime import datetime
import json
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

# European Roulette board
RED_NUMBERS = {1, 3, 5, 7, 9, 12, 14, 16, 18, 19, 21, 23, 25, 27, 30, 32, 34, 36}
BLACK_NUMBERS = {2, 4, 6, 8, 10, 11, 13, 15, 17, 20, 22, 24, 26, 28, 29, 31, 33, 35}

VIP_TIERS = [
    {
        "name": "Bronze",
        "title": "🎰 Tân Binh Roulette",
        "max_bet": 1_000_000,
        "emoji": "🥉",
        "req_plays": 0,
        "req_achievements": 0,
        "win_bonus": 0.0,
        "loss_refund": 0.0,
        "chip_rate": 1,
        "lucky_mult": 1.0,
    },
    {
        "name": "Silver",
        "title": "🍀 Con Cưng Thần May",
        "max_bet": 3_000_000,
        "emoji": "🥈",
        "req_plays": 100,
        "req_achievements": 1,
        "win_bonus": 0.02,
        "loss_refund": 0.0,
        "chip_rate": 1,
        "lucky_mult": 1.0,
    },
    {
        "name": "Gold",
        "title": "💎 Cao Thủ Roulette",
        "max_bet": 6_000_000,
        "emoji": "🥇",
        "req_plays": 500,
        "req_achievements": 3,
        "win_bonus": 0.05,
        "loss_refund": 0.05,
        "chip_rate": 1,
        "lucky_mult": 1.0,
    },
    {
        "name": "Diamond",
        "title": "👑 Vua Roulette",
        "max_bet": 10_000_000,
        "emoji": "💎",
        "req_plays": 1500,
        "req_achievements": 5,
        "win_bonus": 0.08,
        "loss_refund": 0.10,
        "chip_rate": 2,
        "lucky_mult": 1.0,
    },
    {
        "name": "Legend",
        "title": "🎲 Huyền Thoại Casino",
        "max_bet": 20_000_000,
        "emoji": "👑",
        "req_plays": 3500,
        "req_achievements": 7,
        "win_bonus": 0.12,
        "loss_refund": 0.15,
        "chip_rate": 2,
        "lucky_mult": 1.5,
    },
]


def get_user_vip(stats: dict) -> dict:
    plays = stats.get("plays", 0)
    achievements = stats.get("achievements", [])
    num_ach = len(achievements)
    
    if plays >= 3500 and num_ach >= 7:
        return VIP_TIERS[4]
    if plays >= 1500 and num_ach >= 5:
        return VIP_TIERS[3]
    if plays >= 500 and num_ach >= 3:
        return VIP_TIERS[2]
    if plays >= 100 and num_ach >= 1:
        return VIP_TIERS[1]
    return VIP_TIERS[0]


def get_vip_buffs_description(vip: dict) -> str:
    buffs = []
    if vip["win_bonus"] > 0:
        buffs.append(f"➕ Tăng thưởng thắng cược: `+{vip['win_bonus']*100:.0f}%` payout")
    if vip["loss_refund"] > 0:
        buffs.append(f"🛡️ Bảo hiểm hoàn cược thua: `{vip['loss_refund']*100:.0f}%` số tiền thua")
    if vip["chip_rate"] > 1:
        buffs.append(f"⚡ Tốc độ tích lũy Chip May Mắn: x{vip['chip_rate']}")
    if vip["lucky_mult"] > 1.0:
        buffs.append(f"🌟 Nhân thưởng số may mắn hàng ngày: x{vip['lucky_mult']}")
    
    if not buffs:
        return "❌ Chưa có đặc quyền VIP nào hoạt động."
    return "\n".join(f"• {b}" for b in buffs)


def get_next_vip_requirement(plays: int, achievements: list) -> str:
    num_ach = len(achievements)
    
    # VIP levels index: 0=Bronze, 1=Silver, 2=Gold, 3=Diamond, 4=Legend
    current_tier_idx = 0
    if plays >= 3500 and num_ach >= 7:
        current_tier_idx = 4
    elif plays >= 1500 and num_ach >= 5:
        current_tier_idx = 3
    elif plays >= 500 and num_ach >= 3:
        current_tier_idx = 2
    elif plays >= 100 and num_ach >= 1:
        current_tier_idx = 1
        
    if current_tier_idx == 4:
        return "✨ Bạn đã đạt cấp bậc cao nhất (Huyền Thoại Casino)!"
        
    next_tier = VIP_TIERS[current_tier_idx + 1]
    req_plays = next_tier["req_plays"]
    req_ach = next_tier["req_achievements"]
    
    return (
        f"➡️ **Tiến trình VIP tiếp theo ({next_tier['emoji']} {next_tier['name']}):**\n"
        f"• Số ván chơi: `{plays}/{req_plays}`\n"
        f"• Thành tựu đạt được: `{num_ach}/{req_ach}`"
    )



def get_daily_lucky_number(user_id: int) -> int:
    today_str = datetime.now().strftime("%Y-%m-%d")
    seed = f"{user_id}:{today_str}"
    temp_rand = random.Random(seed)
    return temp_rand.randint(0, 36)


def get_number_color(num: int) -> str:
    if num == 0:
        return "🟢"
    elif num in RED_NUMBERS:
        return "🔴"
    else:
        return "⚫"


def describe_number(num: int) -> str:
    if num == 0:
        return "🟢 **0** (Xanh, Số đặc biệt)"
    color = "🔴" if num in RED_NUMBERS else "⚫"
    color_name = "Đỏ" if num in RED_NUMBERS else "Đen"
    even_odd = "Chẵn" if num % 2 == 0 else "Lẻ"
    low_high = "Thấp" if num <= 18 else "Cao"
    
    # Dozen
    if num <= 12:
        dozen = "Tá 1"
    elif num <= 24:
        dozen = "Tá 2"
    else:
        dozen = "Tá 3"
        
    # Column
    if num in {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34}:
        col = "Cột 1"
    elif num in {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35}:
        col = "Cột 2"
    else:
        col = "Cột 3"
        
    return f"{color} **{num}** ({color_name}, {even_odd}, {low_high}, {dozen}, {col})"


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



def parse_bet_choice(choice_str: str) -> Optional[tuple[str, str]]:
    choice_str = choice_str.strip().lower()
    
    # Colors
    if choice_str in ["red", "đỏ", "do"]:
        return "color", "red"
    if choice_str in ["black", "đen", "den"]:
        return "color", "black"
    if choice_str in ["green", "xanh", "xanh lá", "xanh la"]:
        return "color", "green"
        
    # Even / Odd
    if choice_str in ["even", "chẵn", "chan"]:
        return "even_odd", "even"
    if choice_str in ["odd", "lẻ", "le"]:
        return "even_odd", "odd"
        
    # Low / High
    if choice_str in ["low", "thấp", "thap", "1-18"]:
        return "low_high", "low"
    if choice_str in ["high", "cao", "19-36"]:
        return "low_high", "high"
        
    # Columns
    if choice_str in ["col1", "cột1", "cot1", "column1"]:
        return "column", "col1"
    if choice_str in ["col2", "cột2", "cot2", "column2"]:
        return "column", "col2"
    if choice_str in ["col3", "cột3", "cot3", "column3"]:
        return "column", "col3"
        
    # Dozens
    if choice_str in ["dozen1", "tá1", "ta1", "1-12"]:
        return "dozen", "dozen1"
    if choice_str in ["dozen2", "tá2", "ta2", "13-24"]:
        return "dozen", "dozen2"
    if choice_str in ["dozen3", "tá3", "ta3", "25-36"]:
        return "dozen", "dozen3"
        
    # Multiple/Single Numbers
    parts = choice_str.replace(",", " ").split()
    if 1 <= len(parts) <= 4:
        try:
            nums = [int(p) for p in parts]
            if all(0 <= n <= 36 for n in nums):
                unique_nums = sorted(list(set(nums)))
                return "number", " ".join(str(n) for n in unique_nums)
        except ValueError:
            pass
            
    return None


def get_vietnamese_bet_name(bet_type: str, bet_choice: str) -> str:
    if bet_type == "color":
        mapping = {"red": "🔴 Đỏ (Red)", "black": "⚫ Đen (Black)", "green": "🟢 Xanh (Green / Số 0)"}
        return mapping.get(bet_choice, bet_choice)
    if bet_type == "even_odd":
        mapping = {"even": "⚪ Chẵn (Even)", "odd": "⚪ Lẻ (Odd)"}
        return mapping.get(bet_choice, bet_choice)
    if bet_type == "low_high":
        mapping = {"low": "📈 Thấp (Low 1-18)", "high": "📈 Cao (High 19-36)"}
        return mapping.get(bet_choice, bet_choice)
    if bet_type == "column":
        mapping = {"col1": "🏛 Cột 1", "col2": "🏛 Cột 2", "col3": "🏛 Cột 3"}
        return mapping.get(bet_choice, bet_choice)
    if bet_type == "dozen":
        mapping = {"dozen1": "🏘 Tá 1 (1-12)", "dozen2": "🏘 Tá 2 (13-24)", "dozen3": "🏘 Tá 3 (25-36)"}
        return mapping.get(bet_choice, bet_choice)
    if bet_type == "number":
        chosen_nums = bet_choice.split()
        if len(chosen_nums) == 1:
            return f"🔢 Số {chosen_nums[0]}"
        else:
            return f"🎲 Nhiều số: {', '.join(chosen_nums)}"
    return bet_choice


def check_win(bet_type: str, bet_choice: str, rolled_num: int) -> bool:
    if bet_type == "color":
        if bet_choice == "red":
            return rolled_num in RED_NUMBERS
        if bet_choice == "black":
            return rolled_num in BLACK_NUMBERS
        if bet_choice == "green":
            return rolled_num == 0
            
    if bet_type == "even_odd":
        if rolled_num == 0:
            return False
        if bet_choice == "even":
            return rolled_num % 2 == 0
        if bet_choice == "odd":
            return rolled_num % 2 != 0
            
    if bet_type == "low_high":
        if rolled_num == 0:
            return False
        if bet_choice == "low":
            return 1 <= rolled_num <= 18
        if bet_choice == "high":
            return 19 <= rolled_num <= 36
            
    if bet_type == "column":
        if rolled_num == 0:
            return False
        col1 = {1, 4, 7, 10, 13, 16, 19, 22, 25, 28, 31, 34}
        col2 = {2, 5, 8, 11, 14, 17, 20, 23, 26, 29, 32, 35}
        col3 = {3, 6, 9, 12, 15, 18, 21, 24, 27, 30, 33, 36}
        if bet_choice == "col1":
            return rolled_num in col1
        if bet_choice == "col2":
            return rolled_num in col2
        if bet_choice == "col3":
            return rolled_num in col3
            
    if bet_type == "dozen":
        if rolled_num == 0:
            return False
        if bet_choice == "dozen1":
            return 1 <= rolled_num <= 12
        if bet_choice == "dozen2":
            return 13 <= rolled_num <= 24
        if bet_choice == "dozen3":
            return 25 <= rolled_num <= 36
            
    if bet_type == "number":
        chosen_nums = [int(x) for x in bet_choice.split()]
        return rolled_num in chosen_nums
        
    return False


def get_payout_multiplier(bet_type: str, bet_choice: str, lucky_number: int) -> int:
    if bet_type == "color":
        if bet_choice == "green":
            return 36
        return 2
    if bet_type == "even_odd":
        return 2
    if bet_type == "low_high":
        return 2
    if bet_type == "column":
        return 3
    if bet_type == "dozen":
        return 3
    if bet_type == "number":
        chosen_nums = [int(x) for x in bet_choice.split()]
        if len(chosen_nums) == 1:
            if chosen_nums[0] == lucky_number:
                return 40
            return 36
        else:
            return 9
    return 1


def check_achievements(
    stats: dict,
    bet_type: str,
    bet_choice: str,
    bet_amount: int,
    hit_number: int,
    lucky_number: int,
    won: bool,
) -> tuple[list[str], list[str]]:
    newly_unlocked = []
    unlocked = set(stats.get("achievements", []))
    
    def unlock(name):
        if name not in unlocked:
            unlocked.add(name)
            newly_unlocked.append(name)

    # 1. Roulette đầu tiên
    if stats["plays"] >= 1:
        unlock("Roulette đầu tiên")
    
    # 2. Thắng 10 lần
    if stats["wins"] >= 10:
        unlock("Thắng 10 lần")
        
    # 3. Thắng 100 lần
    if stats["wins"] >= 100:
        unlock("Thắng 100 lần")
        
    # 4. Trúng số 0
    if won and hit_number == 0:
        if bet_choice == "green" or bet_choice == "0" or (bet_type == "number" and "0" in bet_choice.split()):
            unlock("Trúng số 0")
            
    # 5. Trúng Lucky Number
    if won and bet_type == "number" and str(lucky_number) == bet_choice:
        unlock("Trúng Lucky Number")
        
    # 6. Thắng 5 ván liên tiếp
    if stats["max_streak"] >= 5:
        unlock("Thắng 5 ván liên tiếp")
        
    # 7. Cược 1 triệu trong một ván
    if bet_amount >= 1_000_000:
        unlock("Cược 1 triệu trong một ván")
        
    return list(unlocked), newly_unlocked


class RouletteBetModal(discord.ui.Modal):
    def __init__(self, bet_type: str, bet_choice: str, roulette_cog):
        super().__init__(title="Số Tiền Muốn Cược")
        self.bet_type = bet_type
        self.bet_choice = bet_choice
        self.roulette_cog = roulette_cog
        
        self.amount_input = discord.ui.TextInput(
            label="Số tiền muốn cược",
            placeholder="Ví dụ: 10k, 500k, 1m, all",
            required=True,
            max_length=20,
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        # Handle queueing the bet
        await interaction.response.defer()
        
        user = interaction.user
        val_str = self.amount_input.value
        
        profile = self.roulette_cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.followup.send(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).",
                ephemeral=True,
            )
            return
            
        channel_id = interaction.channel_id
        lobby = self.roulette_cog.active_lobbies.get(channel_id)
        if not lobby:
            await interaction.followup.send(
                "❌ Bàn cược này đã hết hạn hoặc bị hủy.",
                ephemeral=True,
            )
            return
            
        user_bets = lobby["bets"].get(user.id, [])
        total_queued = sum(b["amount"] for b in user_bets)
        if total_queued + amount > current_money:
            await interaction.followup.send(
                f"❌ Bạn không đủ tiền! Số tiền hiện có: {current_money:,} VNĐ, đã cược trước đó: {total_queued:,} VNĐ, muốn cược thêm: {amount:,} VNĐ.",
                ephemeral=True,
            )
            return
            
        if user.id not in lobby["bets"]:
            lobby["bets"][user.id] = []
        lobby["bets"][user.id].append({
            "type": self.bet_type,
            "choice": self.bet_choice,
            "amount": amount
        })
        
        viet_choice = get_vietnamese_bet_name(self.bet_type, self.bet_choice)
        await interaction.followup.send(
            f"✅ Đã thêm cược **{amount:,} VNĐ** vào cửa **{viet_choice}**!",
            ephemeral=True,
        )
        await self.roulette_cog.update_lobby(channel_id)


class RouletteNumberBetModal(discord.ui.Modal):
    def __init__(self, roulette_cog):
        super().__init__(title="Đặt Cược Số")
        self.roulette_cog = roulette_cog
        
        self.numbers_input = discord.ui.TextInput(
            label="Nhập 1 đến 4 số (cách nhau bởi dấu cách)",
            placeholder="Ví dụ: 17 hoặc 7 11 15 20",
            required=True,
            max_length=20,
        )
        self.amount_input = discord.ui.TextInput(
            label="Số tiền muốn cược",
            placeholder="Ví dụ: 10k, 500k, 1m, all",
            required=True,
            max_length=20,
        )
        self.add_item(self.numbers_input)
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user = interaction.user
        numbers_str = self.numbers_input.value
        val_str = self.amount_input.value
        
        parsed = parse_bet_choice(numbers_str)
        if not parsed or parsed[0] != "number":
            await interaction.followup.send(
                "❌ Lựa chọn số không hợp lệ! Hãy nhập từ 1 đến 4 số từ 0 đến 36.",
                ephemeral=True,
            )
            return
            
        bet_type, bet_choice = parsed
        
        profile = self.roulette_cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.followup.send(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).",
                ephemeral=True,
            )
            return
            
        channel_id = interaction.channel_id
        lobby = self.roulette_cog.active_lobbies.get(channel_id)
        if not lobby:
            await interaction.followup.send(
                "❌ Bàn cược này đã hết hạn hoặc bị hủy.",
                ephemeral=True,
            )
            return
            
        user_bets = lobby["bets"].get(user.id, [])
        total_queued = sum(b["amount"] for b in user_bets)
        if total_queued + amount > current_money:
            await interaction.followup.send(
                f"❌ Bạn không đủ tiền! Số tiền hiện có: {current_money:,} VNĐ, đã cược trước đó: {total_queued:,} VNĐ, muốn cược thêm: {amount:,} VNĐ.",
                ephemeral=True,
            )
            return
            
        if user.id not in lobby["bets"]:
            lobby["bets"][user.id] = []
        lobby["bets"][user.id].append({
            "type": bet_type,
            "choice": bet_choice,
            "amount": amount
        })
        
        viet_choice = get_vietnamese_bet_name(bet_type, bet_choice)
        await interaction.followup.send(
            f"✅ Đã thêm cược **{amount:,} VNĐ** vào cửa **{viet_choice}**!",
            ephemeral=True,
        )
        await self.roulette_cog.update_lobby(channel_id)


class RouletteSimpleBetView(discord.ui.View):
    def __init__(self, user_id: int, roulette_cog):
        super().__init__(timeout=60.0)
        self.user_id = user_id
        self.roulette_cog = roulette_cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Chỉ người gọi lệnh mới có thể tương tác!", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Chọn cửa cược Màu / Chẵn Lẻ / Thấp Cao...",
        options=[
            discord.SelectOption(label="🔴 Đỏ (Red)", value="color:red", description="Trả thưởng x2"),
            discord.SelectOption(label="⚫ Đen (Black)", value="color:black", description="Trả thưởng x2"),
            discord.SelectOption(label="🟢 Xanh (Green / Số 0)", value="color:green", description="Trả thưởng x36"),
            discord.SelectOption(label="⚪ Chẵn (Even)", value="even_odd:even", description="Trả thưởng x2 (Trừ số 0)"),
            discord.SelectOption(label="⚪ Lẻ (Odd)", value="even_odd:odd", description="Trả thưởng x2"),
            discord.SelectOption(label="📈 Thấp (Low 1-18)", value="low_high:low", description="Trả thưởng x2"),
            discord.SelectOption(label="📈 Cao (High 19-36)", value="low_high:high", description="Trả thưởng x2"),
        ]
    )
    async def select_bet(self, interaction: discord.Interaction, select: discord.ui.Select):
        bet_type, bet_choice = select.values[0].split(":")
        modal = RouletteBetModal(bet_type, bet_choice, self.roulette_cog)
        await interaction.response.send_modal(modal)


class RouletteGroupBetView(discord.ui.View):
    def __init__(self, user_id: int, roulette_cog):
        super().__init__(timeout=60.0)
        self.user_id = user_id
        self.roulette_cog = roulette_cog

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Chỉ người gọi lệnh mới có thể tương tác!", ephemeral=True)
            return False
        return True

    @discord.ui.select(
        placeholder="Chọn cược Cột / Tá...",
        options=[
            discord.SelectOption(label="🏛 Cột 1 (Column 1)", value="column:col1", description="1, 4, 7... Trả thưởng x3"),
            discord.SelectOption(label="🏛 Cột 2 (Column 2)", value="column:col2", description="2, 5, 8... Trả thưởng x3"),
            discord.SelectOption(label="🏛 Cột 3 (Column 3)", value="column:col3", description="3, 6, 9... Trả thưởng x3"),
            discord.SelectOption(label="🏘 Tá 1 (1-12)", value="dozen:dozen1", description="Số từ 1 đến 12. Trả thưởng x3"),
            discord.SelectOption(label="🏘 Tá 2 (13-24)", value="dozen:dozen2", description="Số từ 13 đến 24. Trả thưởng x3"),
            discord.SelectOption(label="🏘 Tá 3 (25-36)", value="dozen:dozen3", description="Số từ 25 đến 36. Trả thưởng x3"),
        ]
    )
    async def select_bet(self, interaction: discord.Interaction, select: discord.ui.Select):
        bet_type, bet_choice = select.values[0].split(":")
        modal = RouletteBetModal(bet_type, bet_choice, self.roulette_cog)
        await interaction.response.send_modal(modal)


class RouletteLobbyView(discord.ui.View):
    def __init__(self, channel_id: int, host_id: int, roulette_cog):
        super().__init__(timeout=120.0)
        self.channel_id = channel_id
        self.host_id = host_id
        self.roulette_cog = roulette_cog
        self.setup_buttons()

    def setup_buttons(self):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        has_bets = False
        if lobby and lobby["bets"]:
            has_bets = any(len(b) > 0 for b in lobby["bets"].values())
            
        if has_bets:
            btn_spin = discord.ui.Button(label="Quay Bàn Xoay 🎡", style=discord.ButtonStyle.success, custom_id="lobby_spin", row=1)
            btn_spin.callback = self.spin_callback
            self.add_item(btn_spin)
            
            btn_cancel = discord.ui.Button(label="Hủy Cược Của Tôi ❌", style=discord.ButtonStyle.danger, custom_id="lobby_cancel", row=1)
            btn_cancel.callback = self.cancel_callback
            self.add_item(btn_cancel)
            
        if lobby:
            btn_close = discord.ui.Button(label="Hủy Bàn 🧹", style=discord.ButtonStyle.secondary, custom_id="lobby_close", row=1)
            btn_close.callback = self.close_callback
            self.add_item(btn_close)

    async def spin_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Chỉ chủ bàn mới có thể quay bàn xoay!", ephemeral=True)
            return
            
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if not lobby or not lobby["bets"] or not any(len(b) > 0 for b in lobby["bets"].values()):
            await interaction.response.send_message("❌ Chưa có ai cược trên bàn này!", ephemeral=True)
            return
            
        await interaction.response.defer()
        await self.roulette_cog.run_multi_spin(interaction, interaction.user, lobby)

    async def cancel_callback(self, interaction: discord.Interaction):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if lobby and interaction.user.id in lobby["bets"]:
            del lobby["bets"][interaction.user.id]
            await interaction.response.send_message("🧹 Đã hủy toàn bộ cược của bạn tại bàn này.", ephemeral=True)
            await self.roulette_cog.update_lobby(self.channel_id)
        else:
            await interaction.response.send_message("❌ Bạn chưa đặt cược nào tại bàn này để hủy.", ephemeral=True)

    async def close_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Chỉ chủ bàn mới có thể hủy/đóng bàn!", ephemeral=True)
            return
            
        if self.channel_id in self.roulette_cog.active_lobbies:
            del self.roulette_cog.active_lobbies[self.channel_id]
            
        await interaction.response.send_message("🧹 Bàn quay Roulette đã bị hủy bởi chủ bàn.", ephemeral=False)
        embed = discord.Embed(title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰", description="❌ Bàn quay đã bị chủ bàn hủy bỏ.", color=discord.Color.red())
        try:
            await interaction.message.edit(embed=embed, view=None)
        except Exception:
            pass

    async def on_timeout(self):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if lobby:
            if self.channel_id in self.roulette_cog.active_lobbies:
                del self.roulette_cog.active_lobbies[self.channel_id]
            try:
                embed = discord.Embed(title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰", description="⏱️ Bàn quay đã tự động đóng do hết thời gian chờ.", color=discord.Color.red())
                await lobby["message"].edit(embed=embed, view=None)
            except Exception:
                pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="Cược Đơn Giản", style=discord.ButtonStyle.primary, emoji="🔴")
    async def bet_simple(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if not lobby:
            await interaction.response.send_message("❌ Bàn cược này đã hết hạn hoặc bị hủy.", ephemeral=True)
            return
        view = RouletteSimpleBetView(interaction.user.id, self.roulette_cog)
        await interaction.response.send_message(
            "Chọn cửa cược Màu / Chẵn Lẻ / Thấp Cao từ menu bên dưới:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Cược Nhóm (Cột/Tá)", style=discord.ButtonStyle.primary, emoji="🏛")
    async def bet_group(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if not lobby:
            await interaction.response.send_message("❌ Bàn cược này đã hết hạn hoặc bị hủy.", ephemeral=True)
            return
        view = RouletteGroupBetView(interaction.user.id, self.roulette_cog)
        await interaction.response.send_message(
            "Chọn cửa cược Cột / Tá từ menu bên dưới:",
            view=view,
            ephemeral=True,
        )

    @discord.ui.button(label="Cược Số", style=discord.ButtonStyle.success, emoji="🔢")
    async def bet_numbers(self, interaction: discord.Interaction, button: discord.ui.Button):
        lobby = self.roulette_cog.active_lobbies.get(self.channel_id)
        if not lobby:
            await interaction.response.send_message("❌ Bàn cược này đã hết hạn hoặc bị hủy.", ephemeral=True)
            return
        modal = RouletteNumberBetModal(self.roulette_cog)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Thống Kê & Rank", style=discord.ButtonStyle.secondary, emoji="📊")
    async def view_stats(self, interaction: discord.Interaction, button: discord.ui.Button):
        stats = self.roulette_cog.economy.get_roulette(interaction.user.id)
        lucky_number = get_daily_lucky_number(interaction.user.id)
        vip = get_user_vip(stats)
        
        # calculate win rate
        plays = stats["plays"]
        win_rate = (stats["wins"] / plays * 100) if plays > 0 else 0
        
        # most hit number
        num_stats = stats.get("number_stats", {})
        if num_stats:
            most_lucky_num = max(num_stats, key=num_stats.get)
            hit_count = num_stats[most_lucky_num]
            most_lucky_str = f"Số **{most_lucky_num}** ({hit_count} lần trúng)"
        else:
            most_lucky_str = "Chưa có"

        ach_list = stats.get("achievements", [])
        ach_str = "\n".join(f"🏆 {ach}" for ach in ach_list) if ach_list else "*Chưa có*"
        
        desc = (
            f"**CẤP BẬC VIP:** {vip['emoji']} **{vip['title']}**\n"
            f"⭐ **Đặc quyền VIP đang kích hoạt:**\n{get_vip_buffs_description(vip)}\n\n"
            f"{get_next_vip_requirement(plays, ach_list)}\n\n"
            f"🍀 Số may mắn hôm nay: **{lucky_number}** (Thưởng x40 khi cược trúng)\n"
            f"⚡ Chip May Mắn hiện có: **{stats['chips']}/10** (Thưởng thêm `+{stats['chips'] * 0.5}%`)\n\n"
            f"📊 **BẢNG THỐNG KÊ CHI TIẾT:**\n"
            f"• Đã chơi: `{plays}` ván\n"
            f"• Thắng: `{stats['wins']}` | Thua: `{stats['losses']}`\n"
            f"• Tỉ lệ thắng: `{win_rate:.1f}%`\n"
            f"• Chuỗi thắng hiện tại: `{stats['streak']}` ván\n"
            f"• Chuỗi thắng dài nhất: `{stats['max_streak']}` ván\n"
            f"• Tổng lãi ròng: `{(stats['profit']):+,} VNĐ`\n"
            f"• Số may mắn nhất: {most_lucky_str}\n\n"
            f"🏆 **THÀNH TỰU ĐÃ ĐẠT ({len(ach_list)}/7):**\n"
            f"{ach_str}"
        )
        
        embed = make_embed(
            title=f"📊 THỐNG KÊ ROULETTE - {interaction.user.display_name} 📊",
            description=desc,
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class Roulette(commands.Cog, name="Roulette"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", None) or Economy()
        self.active_lobbies = {}  # channel_id -> { "message": discord.Message, "host_id": int, "bets": {user_id: list_of_bets} }



    @commands.command(
        brief="Chơi Roulette Châu Âu (Cổ điển & Nhiều lựa chọn)",
        usage="rl [cửa_cược] [tiền_cược]",
        aliases=["roulette", "roulete"],
    )
    async def rl(
        self,
        ctx: commands.Context,
        bet_choice_raw: str = None,
        bet_amount_raw: str = None,
        *extra_numbers,
    ):
        user_id = ctx.author.id
        stats = self.economy.get_roulette(user_id)
        vip = get_user_vip(stats)
        
        # Intercept stats / thongke command
        if bet_choice_raw and bet_choice_raw.strip().lower() in ["stats", "thongke", "thống kê", "tk"]:
            lucky_number = get_daily_lucky_number(user_id)
            plays = stats["plays"]
            win_rate = (stats["wins"] / plays * 100) if plays > 0 else 0
            
            num_stats = stats.get("number_stats", {})
            if num_stats:
                most_lucky_num = max(num_stats, key=num_stats.get)
                hit_count = num_stats[most_lucky_num]
                most_lucky_str = f"Số **{most_lucky_num}** ({hit_count} lần trúng)"
            else:
                most_lucky_str = "Chưa có"

            ach_list = stats.get("achievements", [])
            ach_str = "\n".join(f"🏆 {ach}" for ach in ach_list) if ach_list else "*Chưa có*"
            
            desc = (
                f"**CẤP BẬC VIP:** {vip['emoji']} **{vip['title']}**\n"
                f"⭐ **Đặc quyền VIP đang kích hoạt:**\n{get_vip_buffs_description(vip)}\n\n"
                f"{get_next_vip_requirement(plays, ach_list)}\n\n"
                f"🍀 Số may mắn hôm nay: **{lucky_number}** (Thưởng x40 khi cược trúng)\n"
                f"⚡ Chip May Mắn hiện có: **{stats['chips']}/10** (Thưởng thêm `+{stats['chips'] * 0.5}%`)\n\n"
                f"📊 **BẢNG THỐNG KÊ CHI TIẾT:**\n"
                f"• Đã chơi: `{plays}` ván\n"
                f"• Thắng: `{stats['wins']}` | Thua: `{stats['losses']}`\n"
                f"• Tỉ lệ thắng: `{win_rate:.1f}%`\n"
                f"• Chuỗi thắng hiện tại: `{stats['streak']}` ván\n"
                f"• Chuỗi thắng dài nhất: `{stats['max_streak']}` ván\n"
                f"• Tổng lãi ròng: `{(stats['profit']):+,} VNĐ`\n"
                f"• Số may mắn nhất: {most_lucky_str}\n\n"
                f"🏆 **THÀNH TỰU ĐÃ ĐẠT ({len(ach_list)}/7):**\n"
                f"{ach_str}"
            )
            
            embed = make_embed(
                title=f"📊 THỐNG KÊ ROULETTE - {ctx.author.display_name} 📊",
                description=desc,
                color=discord.Color.gold(),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return



        # If no arguments are provided, open the interactive lobby
        if bet_choice_raw is None:
            channel_id = ctx.channel.id
            if channel_id in self.active_lobbies:
                existing_msg = self.active_lobbies[channel_id].get("message")
                url = existing_msg.jump_url if existing_msg else ""
                await ctx.send(f"❌ Đã có một bàn Roulette đang hoạt động trong kênh này! {url}")
                return
                
            lucky_number = get_daily_lucky_number(user_id)
            desc = (
                f"Chào mừng bạn đến với **Roulette Châu Âu (Bàn Multiplayer)** 🎡\n\n"
                f"🍀 Số may mắn của bạn hôm nay: **{lucky_number}** (Thưởng x40 khi cược đơn trúng!)\n"
                f"👑 VIP Rank của bạn: {vip['emoji']} **{vip['title']}**\n"
                f"⭐ **Đặc quyền VIP đang kích hoạt:**\n{get_vip_buffs_description(vip)}\n\n"
                f"💰 Giới hạn cược: Không giới hạn\n"
                f"⚡ Chip May Mắn hiện tại: **{stats['chips']}/10**\n\n"
                f"Mọi người hãy chọn các nút cược bên dưới để tham gia đặt cược!"
            )
            embed = make_embed(
                title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰",
                description=desc,
                color=discord.Color.dark_theme(),
            )
            view = RouletteLobbyView(channel_id, user_id, self)
            msg = await ctx.send(embed=embed, view=view)
            self.active_lobbies[channel_id] = {
                "message": msg,
                "host_id": user_id,
                "bets": {}
            }
            return

        # Parsing bet amount
        # Handle cases where multiple numbers are passed, e.g. !roulette 7 11 15 20 100000
        # If extra numbers exist, bet_amount is the last argument
        all_args = [bet_choice_raw, bet_amount_raw] + list(extra_numbers)
        bet_amount_str = all_args[-1]
        bet_choices_str = " ".join(all_args[:-1])
        
        # Parse the choices
        parsed = parse_bet_choice(bet_choices_str)
        if not parsed:
            # Let's try if the user entered amount first, e.g. !roulette 100000 đỏ
            # Swap them and check
            bet_amount_str = all_args[0]
            bet_choices_str = " ".join(all_args[1:])
            parsed = parse_bet_choice(bet_choices_str)
            if not parsed:
                await ctx.send(
                    f"❌ **Lỗi:** Cửa cược không hợp lệ!\n"
                    f"Ví dụ cửa cược hợp lệ:\n"
                    f"• Màu: `đỏ` (red), `đen` (black), `green` (xanh)\n"
                    f"• Chẵn lẻ: `chẵn` (even), `lẻ` (odd)\n"
                    f"• Thấp cao: `thấp` (low), `cao` (high)\n"
                    f"• Tá/Cột: `cột1`, `tá1`, ...\n"
                    f"• Số: `17` hoặc tối đa 4 số: `7 11 15 20`"
                )
                return
                
        bet_type, bet_choice = parsed
        
        profile = self.economy.get_entry(user_id)
        current_money = profile[1]
        
        amount = parse_bet_amount(bet_amount_str, current_money)
        if amount <= 0:
            await ctx.send("❌ **Lỗi:** Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).")
            return
            
        # Execute the spin
        await self.run_spin(ctx, ctx.author, bet_type, bet_choice, amount)

    async def run_spin(self, ctx_or_interaction, user, bet_type: str, bet_choice: str, bet_amount: int):
        user_id = user.id
        stats = self.economy.get_roulette(user_id)
        vip = get_user_vip(stats)
        
        # Check money available
        try:
            validate_money_bet(self.economy, user_id, bet_amount)
        except Exception as e:
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send(str(e), ephemeral=True)
            else:
                await ctx_or_interaction.send(str(e))
            return
            
        # Deduct money immediately
        self.economy.add_money(user_id, -bet_amount)
        log_wallet_change(
            logger,
            event="roulette_place_bet",
            user_id=user_id,
            money_delta=-bet_amount,
            bet_type=bet_type,
            bet_choice=bet_choice,
            bet_amount=bet_amount,
        )

        lucky_number = get_daily_lucky_number(user_id)
        viet_choice = get_vietnamese_bet_name(bet_type, bet_choice)
        
        # Spin animation setup
        spinning_embed = make_embed(
            title="🎡 ROULETTE ĐANG QUAY... 🎡",
            description=(
                f"👤 Người chơi: **{user.display_name}**\n"
                f"🎲 Cửa cược: **{viet_choice}**\n"
                f"💰 Tiền cược: **{bet_amount:,} VNĐ**\n\n"
                f"⚡ *Bàn xoay đang quay tròn...*\n"
                f"⚫🔴⚫🔴🟢⚫🔴⚫🔴⚫🔴🟢⚫🔴"
            ),
            color=discord.Color.dark_theme(),
        )
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            msg = await ctx_or_interaction.followup.send(embed=spinning_embed)
        else:
            msg = await ctx_or_interaction.send(embed=spinning_embed)

        await asyncio.sleep(1.5)
        
        # Slowing down animation
        slowing_embed = make_embed(
            title="🎡 VÒNG QUAY ĐANG CHẬM DẦN... 🎡",
            description=(
                f"👤 Người chơi: **{user.display_name}**\n"
                f"🎲 Cửa cược: **{viet_choice}**\n"
                f"💰 Tiền cược: **{bet_amount:,} VNĐ**\n\n"
                f"⚡ *Bóng đang nhảy quanh các ô...*\n"
                f"🟢⚫🔴⚫🔴🟢⚫🔴"
            ),
            color=discord.Color.dark_theme(),
        )
        await msg.edit(embed=slowing_embed)
        
        await asyncio.sleep(1.5)
        
        # Final result calculation
        rolled_num = random.randint(0, 36)
        rolled_color = get_number_color(rolled_num)
        desc_rolled = describe_number(rolled_num)
        
        won = check_win(bet_type, bet_choice, rolled_num)
        
        # Database transaction details
        profit = 0
        payout = 0
        chips_delta = 0
        new_chips_count = stats["chips"]
        vip_win_bonus = 0
        refund = 0
        chip_rate = vip.get("chip_rate", 1)
        
        if won:
            is_lucky_hit = (bet_type == "number" and bet_choice == str(lucky_number))
            multiplier = get_payout_multiplier(bet_type, bet_choice, lucky_number)
            if is_lucky_hit and vip.get("lucky_mult", 1.0) > 1.0:
                multiplier = int(multiplier * vip["lucky_mult"])
                
            base_payout = bet_amount * multiplier
            
            # Luck chip bonus logic
            chip_bonus_percent = stats["chips"] * 0.005 # 0.5% per chip
            chip_bonus = int(base_payout * chip_bonus_percent)
            
            # VIP win bonus
            vip_win_bonus = int(base_payout * vip.get("win_bonus", 0.0))
            
            payout = base_payout + chip_bonus + vip_win_bonus
            profit = payout - bet_amount
            
            # Consume all chips
            new_chips_count = 0
            
            # Add payout to player's wallet
            self.economy.add_money(user_id, payout)
            log_wallet_change(
                logger,
                event="roulette_payout_win",
                user_id=user_id,
                money_delta=payout,
                payout=payout,
                base_payout=base_payout,
                chip_bonus=chip_bonus,
                vip_win_bonus=vip_win_bonus,
                profit=profit,
            )
        else:
            payout = 0
            refund = int(bet_amount * vip.get("loss_refund", 0.0))
            profit = -bet_amount + refund
            
            if refund > 0:
                self.economy.add_money(user_id, refund)
            
            # Accumulate chips (max 10)
            if stats["chips"] < 10:
                new_chips_count = min(10, stats["chips"] + chip_rate)
            log_wallet_change(
                logger,
                event="roulette_payout_lose",
                user_id=user_id,
                money_delta=refund,
                refund=refund,
                profit=profit,
            )
            
        # Update statistics in database
        plays_delta = 1
        wins_delta = 1 if won else 0
        losses_delta = 0 if won else 1
        
        # Streak calculations
        if won:
            new_streak = stats["streak"] + 1
        else:
            new_streak = 0
            
        new_max_streak = max(stats["max_streak"], new_streak)
        
        # Update hit stats
        num_stats = stats.get("number_stats", {})
        num_str = str(rolled_num)
        num_stats[num_str] = num_stats.get(num_str, 0) + 1
        
        # Achievements checking
        temp_stats_for_check = {
            "plays": stats["plays"] + plays_delta,
            "wins": stats["wins"] + wins_delta,
            "losses": stats["losses"] + losses_delta,
            "streak": new_streak,
            "max_streak": new_max_streak,
            "achievements": stats["achievements"],
        }
        
        all_ach, newly_unlocked = check_achievements(
            temp_stats_for_check,
            bet_type,
            bet_choice,
            bet_amount,
            rolled_num,
            lucky_number,
            won,
        )
        
        # Commit stats updates
        self.economy.update_roulette(
            user_id,
            plays=plays_delta,
            wins=wins_delta,
            losses=losses_delta,
            profit=profit,
            streak=new_streak,
            max_streak=new_max_streak,
            chips=new_chips_count,
            number_stats=num_stats,
            achievements=all_ach,
        )
        
        # Display results
        embed_color = discord.Color.green() if won else discord.Color.red()
        emoji_title = "🎉 THẮNG LỚN! 🎉" if won else "💸 THUA CUỘC 💸"
        
        desc = (
            f"🎡 **Bóng đã dừng tại ô:** {desc_rolled}\n\n"
            f"• Cửa cược: **{viet_choice}**\n"
            f"• Tiền đặt cược: `{bet_amount:,} VNĐ`\n"
        )
        
        if won:
            desc += f"• Tiền thắng cơ bản: `+{bet_amount * multiplier:,} VNĐ` (x{multiplier})\n"
            if stats["chips"] > 0:
                desc += (
                    f"• Thưởng thêm từ **{stats['chips']} Chip May Mắn**: `+{chip_bonus_percent*100:.1f}%` (+{chip_bonus:,} VNĐ)\n"
                    f"👉 *Toàn bộ chip đã được tiêu hao về 0.*\n"
                )
            if vip_win_bonus > 0:
                desc += f"• Thưởng thêm từ **VIP {vip['name']}** (`+{vip['win_bonus']*100:.0f}%`): `+{vip_win_bonus:,} VNĐ`\n"
            desc += f"🏆 **Tổng thực nhận:** `+{payout:,} VNĐ` (**Lợi nhuận:** `+{profit:,} VNĐ`)\n"
        else:
            desc += f"💔 **Thua cuộc:** `-{bet_amount:,} VNĐ`\n"
            if refund > 0:
                desc += f"🛡️ **Bảo hiểm VIP {vip['name']}** (`{vip['loss_refund']*100:.0f}%`): Hoàn lại `+{refund:,} VNĐ`\n"
            desc += f"🍀 *Bạn tích lũy thêm {chip_rate} Chip May Mắn!* (Số chip hiện có: **{new_chips_count}/10**)\n"
            
        # Add win streak indicators
        if won:
            streak_milestones = {3: "🔥 3 thắng liên tiếp!", 5: "🔥 5 thắng liên tiếp!! Bùng nổ!", 10: "🔥 10 thắng liên tiếp!!! Quái kiệt!"}
            if new_streak in streak_milestones:
                desc += f"\n**{streak_milestones[new_streak]}**"
            elif new_streak > 1:
                desc += f"\n🔥 `{new_streak}` thắng liên tiếp"
                
        embed = make_embed(
            title=f"{emoji_title} ROULETTE - {user.display_name} {emoji_title}",
            description=desc,
            color=embed_color,
        )
        
        if newly_unlocked:
            embed.add_field(
                name="🏆 THÀNH TỰU MỚI ĐÃ MỞ KHÓA!",
                value="\n".join(f"• **{ach}**" for ach in newly_unlocked),
                inline=False,
            )
            
        embed.set_thumbnail(url=user.display_avatar.url)
        await msg.edit(embed=embed)



    async def update_lobby(self, channel_id: int):
        lobby = self.active_lobbies.get(channel_id)
        if not lobby:
            return
            
        msg = lobby["message"]
        if not msg:
            return
            
        # Build description showing all bets
        host_id = lobby["host_id"]
        bets_dict = lobby["bets"]
        
        # Check if there are any bets overall
        has_any_bets = any(len(b) > 0 for b in bets_dict.values())
        
        if not has_any_bets:
            stats = self.economy.get_roulette(host_id)
            vip = get_user_vip(stats)
            lucky_number = get_daily_lucky_number(host_id)
            
            desc = (
                f"Chào mừng bạn đến với **Roulette Châu Âu (Bàn Multiplayer)** 🎡\n\n"
                f"🍀 Số may mắn của chủ bàn hôm nay: **{lucky_number}**\n"
                f"👑 VIP Rank của chủ bàn: {vip['emoji']} **{vip['title']}**\n"
                f"⭐ **Đặc quyền VIP của chủ bàn:**\n{get_vip_buffs_description(vip)}\n\n"
                f"💰 Giới hạn cược: Không giới hạn\n"
                f"⚡ Chip May Mắn chủ bàn: **{stats['chips']}/10**\n\n"
                f"Mọi người hãy chọn các nút cược bên dưới để tham gia đặt cược!"
            )
        else:
            bet_list_str = ""
            total_table_bet = 0
            for u_id, u_bets in bets_dict.items():
                if not u_bets:
                    continue
                user_total = sum(b["amount"] for b in u_bets)
                total_table_bet += user_total
                
                # Fetch user name or mention
                user_mention = f"<@{u_id}>"
                
                user_bets_strs = []
                for b in u_bets:
                    viet_choice = get_vietnamese_bet_name(b["type"], b["choice"])
                    user_bets_strs.append(f"{viet_choice} (`{b['amount']:,}` VNĐ)")
                
                bet_list_str += f"• {user_mention}: {', '.join(user_bets_strs)} — **Tổng: `{user_total:,}` VNĐ**\n"
                
            desc = (
                f"🎡 **Roulette Châu Âu - BÀN CƯỢC MULTIPLAYER** 🎡\n\n"
                f"🎟️ **CÁC CỬA CƯỢC ĐÃ ĐẶT:**\n"
                f"{bet_list_str}\n"
                f"💰 **Tổng tiền cược cả bàn:** `{total_table_bet:,} VNĐ`\n\n"
                f"Chủ bàn bấm nút **Quay Bàn Xoay 🎡** để bắt đầu quay, hoặc người chơi bấm **Hủy Cược Của Tôi ❌** để rút cược."
            )
            
        view = RouletteLobbyView(channel_id, host_id, self)
        embed = make_embed(
            title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰",
            description=desc,
            color=discord.Color.dark_theme() if not has_any_bets else discord.Color.green(),
        )
        try:
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error updating lobby message: {e}")

    async def run_multi_spin(self, ctx_or_interaction, host, lobby: dict):
        channel_id = lobby["message"].channel.id if lobby["message"] else ctx_or_interaction.channel.id
        
        # Calculate valid participants and their bets
        valid_bets_by_user = {}
        users_to_warn = []
        total_table_bet = 0
        
        for u_id, u_bets in list(lobby["bets"].items()):
            if not u_bets:
                continue
            u_total = sum(b["amount"] for b in u_bets)
            
            # Check player's money at spin time
            u_profile = self.economy.get_entry(u_id)
            current_money = u_profile[1] if u_profile else 0
            
            if current_money < u_total:
                users_to_warn.append(u_id)
            else:
                valid_bets_by_user[u_id] = u_bets
                total_table_bet += u_total
                
                # Deduct money
                self.economy.add_money(u_id, -u_total)
                log_wallet_change(
                    logger,
                    event="roulette_place_multi_bet",
                    user_id=u_id,
                    money_delta=-u_total,
                    total_bet=u_total,
                )

        if not valid_bets_by_user:
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send("❌ Không có người chơi nào đủ tiền để quay bàn xoay!", ephemeral=True)
            else:
                await ctx_or_interaction.send("❌ Không có người chơi nào đủ tiền để quay bàn xoay!")
            # Clean up the lobby since it can't proceed
            if channel_id in self.active_lobbies:
                del self.active_lobbies[channel_id]
            return

        # Spin animation setup
        participants_mentions = ", ".join(f"<@{u_id}>" for u_id in valid_bets_by_user.keys())
        spinning_embed = make_embed(
            title="🎡 ROULETTE ĐANG QUAY... 🎡",
            description=(
                f"👥 Người chơi: {participants_mentions}\n"
                f"🎟️ Đang quay bàn cược với **{len(valid_bets_by_user)}** người chơi...\n"
                f"💰 Tổng cược toàn bàn: **{total_table_bet:,} VNĐ**\n\n"
                f"⚡ *Bàn xoay đang quay tròn...*\n"
                f"⚫🔴⚫🔴🟢⚫🔴⚫🔴⚫🔴🟢⚫🔴"
            ),
            color=discord.Color.dark_theme(),
        )
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            msg = await ctx_or_interaction.followup.send(embed=spinning_embed)
        else:
            msg = await ctx_or_interaction.send(embed=spinning_embed)

        await asyncio.sleep(1.5)
        
        # Slowing down animation
        slowing_embed = make_embed(
            title="🎡 VÒNG QUAY ĐANG CHẬM DẦN... 🎡",
            description=(
                f"👥 Người chơi: {participants_mentions}\n"
                f"🎟️ Đang quay bàn cược với **{len(valid_bets_by_user)}** người chơi...\n"
                f"💰 Tổng cược toàn bàn: **{total_table_bet:,} VNĐ**\n\n"
                f"⚡ *Bóng đang nhảy quanh các ô...*\n"
                f"🟢⚫🔴⚫🔴🟢⚫🔴"
            ),
            color=discord.Color.dark_theme(),
        )
        await msg.edit(embed=slowing_embed)
        
        await asyncio.sleep(1.5)
        
        # Final result calculation
        rolled_num = random.randint(0, 36)
        desc_rolled = describe_number(rolled_num)
        
        # Process payouts for each player
        results_desc_parts = []
        overall_net_profit = 0
        
        for u_id, u_bets in valid_bets_by_user.items():
            user = self.client.get_user(u_id)
            user_display = user.display_name if user else f"ID: {u_id}"
            
            stats = self.economy.get_roulette(u_id)
            vip = get_user_vip(stats)
            chip_rate = vip.get("chip_rate", 1)
            lucky_number = get_daily_lucky_number(u_id)
            
            u_total_bet = sum(b["amount"] for b in u_bets)
            u_total_payout = 0
            u_total_profit = 0
            u_total_refund = 0
            any_won = False
            details_logs = []
            
            for b in u_bets:
                won = check_win(b["type"], b["choice"], rolled_num)
                viet_choice = get_vietnamese_bet_name(b["type"], b["choice"])
                
                if won:
                    any_won = True
                    is_lucky_hit = (b["type"] == "number" and b["choice"] == str(lucky_number))
                    multiplier = get_payout_multiplier(b["type"], b["choice"], lucky_number)
                    if is_lucky_hit and vip.get("lucky_mult", 1.0) > 1.0:
                        multiplier = int(multiplier * vip["lucky_mult"])
                        
                    base_payout = b["amount"] * multiplier
                    
                    # Chip bonus
                    chip_bonus_percent = stats["chips"] * 0.005
                    chip_bonus = int(base_payout * chip_bonus_percent)
                    
                    # VIP Win Bonus
                    vip_win_bonus = int(base_payout * vip.get("win_bonus", 0.0))
                    
                    payout = base_payout + chip_bonus + vip_win_bonus
                    p_profit = payout - b["amount"]
                    
                    u_total_payout += payout
                    u_total_profit += p_profit
                    
                    bonus_str = []
                    if chip_bonus > 0:
                        bonus_str.append(f"+{chip_bonus:,} VNĐ từ {stats['chips']} Chip")
                    if vip_win_bonus > 0:
                        bonus_str.append(f"+{vip_win_bonus:,} VNĐ từ VIP")
                    
                    bonus_desc = f" ({', '.join(bonus_str)})" if bonus_str else ""
                    details_logs.append(f"  🟢 **{viet_choice}** (Cược: `{b['amount']:,}`): **Thắng!** +`{payout:,}` VNĐ{bonus_desc}")
                else:
                    refund = int(b["amount"] * vip.get("loss_refund", 0.0))
                    p_profit = -b["amount"] + refund
                    u_total_profit += p_profit
                    u_total_refund += refund
                    
                    refund_str = f" (Hoàn tiền VIP: `+{refund:,}` VNĐ)" if refund > 0 else ""
                    details_logs.append(f"  🔴 **{viet_choice}** (Cược: `{b['amount']:,}`): **Thua!**{refund_str}")
            
            overall_net_profit += u_total_profit
            
            # Update chip count
            new_chips_count = stats["chips"]
            if any_won:
                new_chips_count = 0
                total_to_add = u_total_payout + u_total_refund
                if total_to_add > 0:
                    self.economy.add_money(u_id, total_to_add)
                    log_wallet_change(
                        logger,
                        event="roulette_multi_payout_win",
                        user_id=u_id,
                        money_delta=total_to_add,
                        payout=u_total_payout,
                        refund=u_total_refund,
                        profit=u_total_profit,
                    )
            else:
                if stats["chips"] < 10:
                    new_chips_count = min(10, stats["chips"] + chip_rate)
                if u_total_refund > 0:
                    self.economy.add_money(u_id, u_total_refund)
                log_wallet_change(
                    logger,
                    event="roulette_multi_payout_lose",
                    user_id=u_id,
                    money_delta=u_total_refund,
                    refund=u_total_refund,
                    profit=u_total_profit,
                )
                
            # Update database stats
            plays_delta = 1
            won_round = u_total_profit > 0
            wins_delta = 1 if won_round else 0
            losses_delta = 0 if won_round else 1
            
            new_streak = stats["streak"] + 1 if won_round else 0
            new_max_streak = max(stats["max_streak"], new_streak)
            
            num_stats = stats.get("number_stats", {})
            num_str = str(rolled_num)
            num_stats[num_str] = num_stats.get(num_str, 0) + 1
            
            temp_stats_for_check = {
                "plays": stats["plays"] + plays_delta,
                "wins": stats["wins"] + wins_delta,
                "losses": stats["losses"] + losses_delta,
                "streak": new_streak,
                "max_streak": new_max_streak,
                "achievements": stats["achievements"],
            }
            
            all_ach, newly_unlocked = check_achievements(
                temp_stats_for_check,
                "multi",
                "multi",
                u_total_bet,
                rolled_num,
                lucky_number,
                won_round,
            )
            
            self.economy.update_roulette(
                u_id,
                plays=plays_delta,
                wins=wins_delta,
                losses=losses_delta,
                profit=u_total_profit,
                streak=new_streak,
                max_streak=new_max_streak,
                chips=new_chips_count,
                number_stats=num_stats,
                achievements=all_ach,
            )
            
            # Format results for this player
            user_res_str = f"👤 **{user_display}**:\n" + "\n".join(details_logs) + "\n"
            if u_total_profit > 0:
                user_res_str += f"  💰 **Tổng thực nhận:** `+{u_total_payout + u_total_refund:,} VNĐ` (Lợi nhuận ròng: `{u_total_profit:+,} VNĐ`)"
            elif u_total_profit < 0:
                user_res_str += f"  💸 **Tổng thực nhận:** `{u_total_payout + u_total_refund:,} VNĐ` (Lợi nhuận ròng: `{u_total_profit:,} VNĐ` | Tích lũy {chip_rate} chip, hiện có: **{new_chips_count}/10**)"
            else:
                user_res_str += f"  ⚖️ **Tổng thực nhận:** `{u_total_payout + u_total_refund:,} VNĐ` (Lợi nhuận ròng: `0 VNĐ`)"
                
            if newly_unlocked:
                user_res_str += f"\n  🏆 *Thành tựu mới:* {', '.join(newly_unlocked)}"
            
            results_desc_parts.append(user_res_str)

        # Append warnings for skipped players
        if users_to_warn:
            warn_mentions = ", ".join(f"<@{u_id}>" for u_id in users_to_warn)
            results_desc_parts.append(f"\n⚠️ **Bị bỏ qua do không đủ tiền:** {warn_mentions}")

        embed_color = discord.Color.green() if overall_net_profit > 0 else (discord.Color.red() if overall_net_profit < 0 else discord.Color.light_grey())
        emoji_title = "🎉 KẾT QUẢ VÒNG QUAY 🎉"
        
        results_str = "\n".join(results_desc_parts)
        desc = (
            f"🎡 **Bóng đã dừng tại ô:** {desc_rolled}\n\n"
            f"📋 **BẢNG KẾT QUẢ CHI TIẾT:**\n"
            f"{results_str}\n\n"
            f"--- \n"
            f"💰 **Tổng cược bàn:** `{total_table_bet:,} VNĐ`\n"
            f"📈 **Tổng lợi nhuận cả bàn:** `{overall_net_profit:+,} VNĐ`\n"
        )
        
        embed = make_embed(
            title=f"{emoji_title} ROULETTE MULTIPLAYER {emoji_title}",
            description=desc,
            color=embed_color,
        )
        
        await msg.edit(embed=embed)
        
        # Clear queued state
        if channel_id in self.active_lobbies:
            del self.active_lobbies[channel_id]


async def setup(client: commands.Bot):
    await client.add_cog(Roulette(client))
