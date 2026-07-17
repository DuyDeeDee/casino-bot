import asyncio
import logging
import random
import time
import json
import datetime
from typing import Optional, Dict

import discord
from discord.ext import commands

from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.giaima_renderer import render_guess_image

logger = logging.getLogger(__name__)

DIFF_CONFIGS = {
    "easy": {
        "name": "Dễ",
        "emoji": "🟢",
        "length": 4,
        "duplicates": False,
        "guesses": 6,
        "time_limit": 300,  # 5 minutes
        "multiplier": 1.2
    },
    "normal": {
        "name": "Thường",
        "emoji": "🟡",
        "length": 5,
        "duplicates": False,
        "guesses": 5,
        "time_limit": 300,  # 5 minutes
        "multiplier": 2.2
    },
    "hard": {
        "name": "Khó",
        "emoji": "🟠",
        "length": 5,
        "duplicates": True,
        "guesses": 4,
        "time_limit": 180,  # 3 minutes
        "multiplier": 4.0
    },
    "nightmare": {
        "name": "Ác Mộng",
        "emoji": "🔴",
        "length": 6,
        "duplicates": True,
        "guesses": 3,
        "time_limit": 120,  # 2 minutes
        "multiplier": 8.0
    }
}

GIAIMA_ACHIEVEMENTS = {
    "first_win": "🧩 Bản Thể Giải Mã (Thắng ván Giải Mã đầu tiên)",
    "speed_solve": "⚡ Thần Tốc (Giải đúng ở lượt đoán đầu tiên)",
    "no_hint_nightmare": "🔥 Không Khoan Nhượng (Thắng độ khó Ác Mộng không dùng gợi ý)",
    "combo_master": "🏆 Bậc Thầy Giải Mã (Đạt chuỗi thắng combo x50%)"
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

async def get_user_name(bot: commands.Bot, user_id: int) -> str:
    user = bot.get_user(user_id)
    if user:
        return user.name
    try:
        user = await bot.fetch_user(user_id)
        return user.name
    except Exception:
        return f"Người chơi {user_id}"

def get_color_emoji(color: str) -> str:
    if color == "green":
        return "🟩"
    elif color == "yellow":
        return "🟨"
    elif color == "blue":
        return "🟦"
    else:
        return "⬛"

def check_guess(secret: list, guess: list, wildcard_digit: Optional[int] = None) -> list:
    length = len(secret)
    result = [None] * length
    secret_matched = [False] * length
    guess_matched = [False] * length
    
    for i in range(length):
        if guess[i] == secret[i]:
            if wildcard_digit is not None and guess[i] == wildcard_digit:
                result[i] = "blue"
            else:
                result[i] = "green"
            secret_matched[i] = True
            guess_matched[i] = True
            
    for i in range(length):
        if not guess_matched[i]:
            for j in range(length):
                if not secret_matched[j] and guess[i] == secret[j]:
                    if wildcard_digit is not None and guess[i] == wildcard_digit:
                        result[i] = "blue"
                    else:
                        result[i] = "yellow"
                    secret_matched[j] = True
                    guess_matched[i] = True
                    break
            if result[i] is None:
                result[i] = "gray"
                
    return result

def check_and_unlock_giaima_achievements(stats: dict, game_info: dict) -> list[str]:
    unlocked = set(stats.get("achievements", []))
    newly_unlocked = []
    
    if game_info.get("win", False):
        if "first_win" not in unlocked:
            newly_unlocked.append("first_win")
            
        if game_info.get("guesses_used", 1) == 1 and "speed_solve" not in unlocked:
            newly_unlocked.append("speed_solve")
            
        if game_info.get("difficulty") == "nightmare" and game_info.get("hints_used", 0) == 0 and "no_hint_nightmare" not in unlocked:
            newly_unlocked.append("no_hint_nightmare")
            
        new_streak = stats.get("streak", 0) + 1
        if new_streak >= 5 and "combo_master" not in unlocked:
            newly_unlocked.append("combo_master")
            
    return newly_unlocked

def make_game_embed(view: "GiaiMaGameView") -> discord.Embed:
    elapsed = int(time.time() - view.start_time)
    remaining = max(0, view.cfg["time_limit"] - elapsed)
    m, s = divmod(remaining, 60)
    time_str = f"{m:02d}:{s:02d}"
    
    desc = (
        f"🔐 **GIẢI MÃ BÍ MẬT — Độ khó: {view.cfg['name']}**\n"
        f"🪙 **Cược:** `{view.bet_amount:,} VND` | **Combo:** `x{1 + 0.1 * min(view.streak, 5):.1f}`\n\n"
    )
    
    if view.guesses:
        desc += "📝 **Lịch sử đoán:**\n"
        for idx, (guess, colors) in enumerate(view.guesses):
            emoji_str = " ".join(get_color_emoji(c) for c in colors)
            guess_str = " ".join(f"[{d}]" for d in guess)
            desc += f"Lượt {idx+1}: {guess_str}  →  {emoji_str}\n"
    else:
        desc += "*Chưa có lượt đoán nào. Hãy nhấn Nhập Mã để bắt đầu!*\n"
        
    desc += f"\n⏳ **Còn lại:** `{time_str}` | 🎯 **Lượt:** `{len(view.guesses)}/{view.cfg['guesses']}`"
    
    if view.is_free_play:
        desc += " | 🎁 **Lượt miễn phí**"
        
    embed = make_embed(
        title="🔐 GIẢI MÃ BÍ MẬT",
        description=desc,
        color=discord.Color.purple()
    )
    embed.set_footer(text="🎰 Casino Bot • Giải Mã Bí Mật")
    return embed

def make_pvp_embed(view: "GiaiMaPvPMatchView") -> discord.Embed:
    elapsed = int(time.time() - view.start_time)
    remaining = max(0, 300 - elapsed)
    m, s = divmod(remaining, 60)
    time_str = f"{m:02d}:{s:02d}"
    
    desc = (
        f"⚔️ **ĐỐI ĐẦU GIẢI MÃ BÍ MẬT** ⚔️\n"
        f"💰 **Bể cược:** `{2 * view.bet:,} VND` | ⏳ **Thời gian:** `{time_str}`\n\n"
    )
    
    p1_status = "Đang đoán..." if not view.p1_done else "Hoàn thành"
    desc += f"👤 **Người chơi 1:** {view.p1.mention} ({p1_status})\n"
    desc += f"🎯 **Lượt:** `{len(view.p1_guesses)}/5` đoán\n"
    if view.p1_guesses:
        desc += "📝 **Lịch sử emojis:**\n"
        for idx, (_, colors) in enumerate(view.p1_guesses):
            emoji_str = " ".join(get_color_emoji(c) for c in colors)
            desc += f"Lượt {idx+1}: {emoji_str}\n"
    else:
        desc += "*Chưa có lượt đoán nào.*\n"
        
    desc += "\n"
    
    p2_status = "Đang đoán..." if not view.p2_done else "Hoàn thành"
    desc += f"👤 **Người chơi 2:** {view.p2.mention} ({p2_status})\n"
    desc += f"🎯 **Lượt:** `{len(view.p2_guesses)}/5` đoán\n"
    if view.p2_guesses:
        desc += "📝 **Lịch sử emojis:**\n"
        for idx, (_, colors) in enumerate(view.p2_guesses):
            emoji_str = " ".join(get_color_emoji(c) for c in colors)
            desc += f"Lượt {idx+1}: {emoji_str}\n"
    else:
        desc += "*Chưa có lượt đoán nào.*\n"
        
    embed = make_embed(
        title="⚔️ ĐỐI ĐẦU GIẢI MÃ BÍ MẬT",
        description=desc,
        color=discord.Color.orange()
    )
    embed.set_footer(text="🎰 Casino Bot • PvP GiaiMa")
    return embed

def make_boss_embed(jackpot: int, history: list) -> discord.Embed:
    desc = (
        f"Một mật mã siêu khó gồm **6 chữ số** đã được thiết lập cho cả server!\n"
        f"Mọi người hãy cùng thử tài đoán mật mã để giải mã Boss.\n\n"
        f"💰 **JACKPOT HIỆN TẠI:** **`{jackpot:,} VND`**\n"
        f"⚙️ **Cơ chế:** Mỗi lượt đoán sai của bất kỳ ai sẽ **cộng thêm 1,000 VND** vào Jackpot!\n"
        f"👉 Bấm nút **[🔓 Thử Vận May]** dưới đây để nhập dự đoán (cooldown 30s).\n\n"
    )
    
    if history:
        desc += "📝 **10 lượt đoán gần đây nhất:**\n"
        for item in reversed(history):
            desc += f"• **{item['username']}** đoán `{item['guess']}`: {item['emojis']}\n"
    else:
        desc += "*Chưa có ai thực hiện lượt đoán nào. Hãy là người đầu tiên thử vận may!*"
        
    embed = make_embed(
        title="👾 BOSS SERVER — MẬT MÃ TOÀN SERVER",
        description=desc,
        color=discord.Color.dark_purple()
    )
    embed.set_footer(text="🎰 Casino Bot • Boss Event")
    return embed


class GiaiMaLobbyView(discord.ui.View):
    def __init__(self, cog: "GiaiMa", user_id: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.user_id = user_id
        self.message = None
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lobby của bạn!", ephemeral=True)
            return False
        return True
        
    @discord.ui.button(label="🟢 Dễ", style=discord.ButtonStyle.success, custom_id="giaima_lobby_easy")
    async def easy_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_difficulty(interaction, "easy")
        
    @discord.ui.button(label="🟡 Thường", style=discord.ButtonStyle.primary, custom_id="giaima_lobby_normal")
    async def normal_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_difficulty(interaction, "normal")
        
    @discord.ui.button(label="🟠 Khó", style=discord.ButtonStyle.danger, custom_id="giaima_lobby_hard")
    async def hard_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_difficulty(interaction, "hard")
        
    @discord.ui.button(label="🔴 Ác Mộng", style=discord.ButtonStyle.danger, custom_id="giaima_lobby_nightmare")
    async def nightmare_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.process_difficulty(interaction, "nightmare")
        
    @discord.ui.button(label="📊 Thống Kê", style=discord.ButtonStyle.secondary, custom_id="giaima_lobby_stats", row=1)
    async def stats_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        stats = self.cog.economy.get_giaima_stats(self.user_id)
        ach_unlocked = stats.get("achievements", [])
        
        desc = (
            f"👤 **Chỉ số giải mã của:** {interaction.user.mention}\n\n"
            f"🎮 **Tổng số ván chơi:** `{stats['plays']}`\n"
            f"✅ **Số ván thắng:** `{stats['wins']}`\n"
            f"❌ **Số ván thua:** `{stats['losses']}`\n"
            f"📈 **Tỷ lệ thắng:** `{stats['wins'] / max(1, stats['plays']) * 100:.1f}%`\n"
            f"💰 **Tổng lợi nhuận:** `{stats['profit']:,} VND`\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{stats['streak']}`\n"
            f"⚡ **Chuỗi thắng dài nhất:** `{stats['max_streak']}`\n\n"
            f"🏆 **Thành tựu đã mở khóa ({len(ach_unlocked)}/{len(GIAIMA_ACHIEVEMENTS)}):**\n"
        )
        for key, name in GIAIMA_ACHIEVEMENTS.items():
            status = "✅" if key in ach_unlocked else "❌"
            desc += f"{status} {name}\n"
            
        embed = make_embed(
            title="📊 THỐNG KÊ GIẢI MÃ BÍ MẬT",
            description=desc,
            color=discord.Color.purple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)
        
    @discord.ui.button(label="🏆 Xếp Hạng", style=discord.ButtonStyle.secondary, custom_id="giaima_lobby_leaderboard", row=1)
    async def leaderboard_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.cog.economy.cur.execute("SELECT user_id, wins, profit FROM user_giaima ORDER BY wins DESC LIMIT 10")
        rows = self.cog.economy.cur.fetchall()
        
        desc = "🏆 **Top 10 Bậc Thầy Giải Mã (Theo số trận thắng):**\n\n"
        if not rows:
            desc += "*Chưa có dữ liệu xếp hạng.*"
        else:
            for idx, (uid, wins, profit) in enumerate(rows):
                name = await get_user_name(self.cog.bot, uid)
                desc += f"{idx+1}. **{name}** — `{wins} thắng` (Lợi nhuận: `{profit:,} VND`)\n"
                
        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG GIẢI MÃ",
            description=desc,
            color=discord.Color.purple()
        )
        await interaction.followup.send(embed=embed, ephemeral=True)

    @discord.ui.button(label="⚔️ Thách Đấu", style=discord.ButtonStyle.secondary, custom_id="giaima_lobby_pvp", row=1)
    async def pvp_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.user_id in self.cog.active_games:
            await interaction.response.send_message("❌ Bạn đang trong một ván chơi Giải Mã!", ephemeral=True)
            return
        if self.user_id in self.cog.active_pvp:
            await interaction.response.send_message("❌ Bạn đang có lời mời thách đấu hoặc trận đấu PvP!", ephemeral=True)
            return
            
        view = discord.ui.View(timeout=60.0)
        select = discord.ui.UserSelect(placeholder="Chọn đối thủ thách đấu...", custom_id="giaima_pvp_select")
        
        async def select_callback(inter: discord.Interaction):
            if inter.user.id != self.user_id:
                await inter.response.send_message("❌ Đây không phải lượt chọn của bạn!", ephemeral=True)
                return
            
            selected_user = select.values[0]
            if selected_user.id == self.user_id:
                await inter.response.send_message("❌ Bạn không thể thách đấu chính mình!", ephemeral=True)
                return
            if selected_user.bot:
                await inter.response.send_message("❌ Bạn không thể thách đấu bot!", ephemeral=True)
                return
                
            modal = GiaiMaPvPBetModal(self.cog, inter.user, selected_user)
            await inter.response.send_modal(modal)
            
        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("⚔️ Hãy chọn đối thủ thách đấu:", view=view, ephemeral=True)
        
    async def process_difficulty(self, interaction: discord.Interaction, difficulty: str):
        if self.user_id in self.cog.active_games:
            await interaction.response.send_message("❌ Bạn đang có một ván Giải Mã đang diễn ra!", ephemeral=True)
            return
        if self.user_id in self.cog.active_pvp:
            await interaction.response.send_message("❌ Bạn đang tham gia trận đấu PvP Giải Mã!", ephemeral=True)
            return
            
        stats = self.cog.economy.get_giaima_stats(self.user_id)
        
        if difficulty == "easy":
            last_play = stats.get("last_free_play", 0)
            last_play_dt = datetime.datetime.fromtimestamp(last_play, datetime.timezone.utc).date()
            now_dt = datetime.datetime.now(datetime.timezone.utc).date()
            free_available = (last_play_dt != now_dt)
            
            if free_available:
                view = GiaiMaFreePlayChoiceView(self.cog, self.user_id, stats)
                embed = make_embed(
                    title="🎁 LƯỢT CHƠI MIỄN PHÍ HẰNG NGÀY",
                    description=(
                        f"Chào {interaction.user.mention}, bạn có **1 lượt chơi độ DỄ miễn phí** hôm nay!\n\n"
                        f"• Nếu chọn **Chơi Miễn Phí**: Bạn không cần đặt cược. Thắng nhận thưởng cố định lên tới `500 VND`.\n"
                        f"• Nếu chọn **Đặt Cược**: Bạn sẽ đặt cược bình thường và được áp dụng hệ số nhân độ khó x1.2."
                    ),
                    color=discord.Color.purple()
                )
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
                return
                
        modal = GiaiMaBetModal(self.cog, difficulty)
        await interaction.response.send_modal(modal)


class GiaiMaFreePlayChoiceView(discord.ui.View):
    def __init__(self, cog: "GiaiMa", user_id: int, stats: dict):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.user_id = user_id
        self.stats = stats
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải lượt chọn của bạn!", ephemeral=True)
            return False
        return True
        
    @discord.ui.button(label="🎁 Chơi Miễn Phí", style=discord.ButtonStyle.success, custom_id="giaima_free_choice_free")
    async def free_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        
        now_ts = int(time.time())
        self.cog.economy.update_giaima_stats(self.user_id, last_free_play=now_ts)
        self.cog.economy.update_giaima_stats(self.user_id, plays=1)
        
        cfg = DIFF_CONFIGS["easy"]
        secret_code = random.sample(range(10), k=cfg["length"])
        
        game_view = GiaiMaGameView(interaction.user, self.cog, "easy", 0, secret_code, is_free_play=True)
        self.cog.active_games[self.user_id] = game_view
        
        embed = make_game_embed(game_view)
        game_view.message = await interaction.channel.send(embed=embed, view=game_view)
        
        self.stop()
        await interaction.edit_original_response(content="✅ Đã bắt đầu ván chơi miễn phí trong kênh!", embed=None, view=None)

    @discord.ui.button(label="🪙 Đặt Cược", style=discord.ButtonStyle.primary, custom_id="giaima_free_choice_bet")
    async def bet_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        modal = GiaiMaBetModal(self.cog, "easy")
        await interaction.response.send_modal(modal)
        self.stop()
        await interaction.edit_original_response(content="⏳ Đang mở bảng đặt cược...", embed=None, view=None)


class GiaiMaBetModal(discord.ui.Modal):
    def __init__(self, cog: "GiaiMa", difficulty: str):
        super().__init__(title="🔐 Đặt Cược Giải Mã Bí Mật")
        self.cog = cog
        self.difficulty = difficulty
        self.config = DIFF_CONFIGS[difficulty]
        
        self.bet_input = discord.ui.TextInput(
            label=f"Nhập số coin cược (Hệ số x{self.config['multiplier']:.1f})",
            placeholder="Ví dụ: 10k, 5000, all...",
            required=True
        )
        self.add_item(self.bet_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        user_id = interaction.user.id
        
        if user_id in self.cog.active_games:
            await interaction.followup.send("❌ Bạn đang có một ván Giải Mã đang diễn ra!", ephemeral=True)
            return
        if user_id in self.cog.active_pvp:
            await interaction.followup.send("❌ Bạn đang trong một trận đấu PvP Giải Mã!", ephemeral=True)
            return
            
        current_money = self.cog.economy.get_entry(user_id)[1]
        bet_amount = parse_bet_amount(self.bet_input.value, current_money)
        
        if bet_amount < 1000:
            await interaction.followup.send("❌ Tiền cược tối thiểu là 1,000 VND.", ephemeral=True)
            return
            
        try:
            validate_money_bet(self.cog.economy, user_id, bet_amount)
            self.cog.economy.add_money(user_id, -bet_amount)
            log_wallet_change(logger, event="giaima_bet", user_id=user_id, money_delta=-bet_amount, channel_id=interaction.channel_id)
        except Exception as e:
            await interaction.followup.send(f"❌ {e}", ephemeral=True)
            return
            
        self.cog.economy.update_giaima_stats(user_id, plays=1)
        
        cfg = self.config
        if cfg["duplicates"]:
            secret_code = [random.randint(0, 9) for _ in range(cfg["length"])]
        else:
            secret_code = random.sample(range(10), k=cfg["length"])
            
        wildcard_digit = None
        if self.difficulty == "nightmare" and random.random() < 0.05:
            wildcard_digit = random.choice(list(set(secret_code)))
            
        game_view = GiaiMaGameView(interaction.user, self.cog, self.difficulty, bet_amount, secret_code, wildcard_digit=wildcard_digit)
        self.cog.active_games[user_id] = game_view
        
        embed = make_game_embed(game_view)
        game_view.message = await interaction.channel.send(embed=embed, view=game_view)


class GiaiMaGameView(discord.ui.View):
    def __init__(self, user: discord.User, cog: "GiaiMa", difficulty: str, bet_amount: int, secret_code: list, wildcard_digit: Optional[int] = None, is_free_play: bool = False):
        self.cfg = DIFF_CONFIGS[difficulty]
        super().__init__(timeout=float(self.cfg["time_limit"]))
        self.user = user
        self.cog = cog
        self.difficulty = difficulty
        self.bet_amount = bet_amount
        self.secret_code = secret_code
        self.wildcard_digit = wildcard_digit
        self.is_free_play = is_free_play
        
        self.guesses = []
        self.hints_used = 0
        self.start_time = time.time()
        self.game_finished = False
        self.message = None
        
        stats = self.cog.economy.get_giaima_stats(user.id)
        self.streak = stats.get("streak", 0)
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
            return False
        return True
        
    @discord.ui.button(label="🔢 Nhập Mã", style=discord.ButtonStyle.success, custom_id="giaima_game_input")
    async def input_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        elapsed = time.time() - self.start_time
        if elapsed >= self.cfg["time_limit"]:
            await self.process_loss(reason="timeout")
            await interaction.response.send_message("⏰ Đã hết thời gian giải mã!", ephemeral=True)
            return
            
        modal = GiaiMaInputModal(self)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="💡 Mua Gợi Ý", style=discord.ButtonStyle.primary, custom_id="giaima_game_hint")
    async def hint_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        elapsed = time.time() - self.start_time
        if elapsed >= self.cfg["time_limit"]:
            await self.process_loss(reason="timeout")
            await interaction.response.send_message("⏰ Đã hết thời gian giải mã!", ephemeral=True)
            return
            
        view = discord.ui.View(timeout=60.0)
        select = discord.ui.Select(
            placeholder="Chọn loại gợi ý muốn mua...",
            custom_id="giaima_hint_select",
            options=[
                discord.SelectOption(
                    label="Gợi ý nhẹ",
                    value="light",
                    description=f"Giá: {1000 if self.is_free_play else int(1000 + 0.1 * self.bet_amount):,} VND - Tiết lộ 1 vị trí"
                ),
                discord.SelectOption(
                    label="Gợi ý mạnh",
                    value="strong",
                    description=f"Giá: {2000 if self.is_free_play else int(2000 + 0.2 * self.bet_amount):,} VND - Loại trừ 2 số sai"
                )
            ]
        )
        
        async def select_callback(inter: discord.Interaction):
            if inter.user.id != self.user.id:
                await inter.response.send_message("❌ Đây không phải lượt chơi của bạn!", ephemeral=True)
                return
            await inter.response.defer(ephemeral=True)
            
            hint_type = select.values[0]
            price = 1000 if hint_type == "light" else 2000
            if not self.is_free_play:
                price = int(1000 + 0.1 * self.bet_amount) if hint_type == "light" else int(2000 + 0.2 * self.bet_amount)
                
            user_money = self.cog.economy.get_entry(self.user.id)[1]
            if user_money < price:
                await inter.followup.send("❌ Bạn không đủ tiền để mua gợi ý này!", ephemeral=True)
                return
                
            self.cog.economy.add_money(self.user.id, -price)
            log_wallet_change(logger, event="giaima_hint", user_id=self.user.id, money_delta=-price, channel_id=inter.channel_id)
            
            self.hints_used += 1
            self.streak = 0
            self.cog.economy.update_giaima_stats(self.user.id, streak=0)
            
            hint_msg = ""
            if hint_type == "light":
                not_solved_indices = list(range(len(self.secret_code)))
                if self.guesses:
                    last_colors = self.guesses[-1][1]
                    not_solved_indices = [idx for idx, c in enumerate(last_colors) if c != "green"]
                if not not_solved_indices:
                    not_solved_indices = list(range(len(self.secret_code)))
                    
                target_idx = random.choice(not_solved_indices)
                hint_msg = f"💡 **Gợi ý nhẹ:** Vị trí số `{target_idx + 1}` là chữ số **`{self.secret_code[target_idx]}`**."
            else:
                all_digits = set(range(10))
                secret_digits = set(self.secret_code)
                not_in_code = list(all_digits - secret_digits)
                if len(not_in_code) >= 2:
                    excluded = random.sample(not_in_code, 2)
                    hint_msg = f"💡 **Gợi ý mạnh:** Chữ số **`{excluded[0]}`** và **`{excluded[1]}`** chắc chắn **KHÔNG** xuất hiện trong mật mã."
                elif len(not_in_code) == 1:
                    hint_msg = f"💡 **Gợi ý mạnh:** Chữ số **`{not_in_code[0]}`** chắc chắn **KHÔNG** xuất hiện trong mật mã."
                else:
                    hint_msg = f"💡 **Gợi ý mạnh:** Không còn chữ số nào để loại trừ!"
                    
            await inter.followup.send(hint_msg, ephemeral=True)
            await self.update_board()
            
        select.callback = select_callback
        view.add_item(select)
        await interaction.response.send_message("💡 Chọn loại gợi ý muốn mua:", view=view, ephemeral=True)

    @discord.ui.button(label="🚪 Bỏ Cuộc", style=discord.ButtonStyle.secondary, custom_id="giaima_game_forfeit")
    async def forfeit_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = discord.ui.View(timeout=30.0)
        confirm_btn = discord.ui.Button(label="✅ Xác Nhận Bỏ Cuộc", style=discord.ButtonStyle.danger)
        cancel_btn = discord.ui.Button(label="❌ Hủy", style=discord.ButtonStyle.secondary)
        
        async def confirm_callback(inter: discord.Interaction):
            if inter.user.id != self.user.id:
                return
            await inter.response.defer()
            await self.process_loss(reason="forfeit")
            view.stop()
            await inter.edit_original_response(content="❌ Bạn đã bỏ cuộc.", view=None)
            
        async def cancel_callback(inter: discord.Interaction):
            if inter.user.id != self.user.id:
                return
            await inter.response.defer()
            view.stop()
            await inter.edit_original_response(content="✅ Đã hủy bỏ cuộc.", view=None)
            
        confirm_btn.callback = confirm_callback
        cancel_btn.callback = cancel_callback
        view.add_item(confirm_btn)
        view.add_item(cancel_btn)
        await interaction.response.send_message("⚠️ Bạn có chắc chắn muốn bỏ cuộc và chấp nhận mất toàn bộ cược?", view=view, ephemeral=True)
        
    async def update_board(self):
        embed = make_game_embed(self)
        await self.message.edit(embed=embed, view=self)
        
    async def on_timeout(self):
        if not self.game_finished:
            await self.process_loss(reason="timeout")
            
    async def process_guess(self, guess_str: str):
        if self.game_finished:
            return
            
        guess_digits = [int(char) for char in guess_str]
        colors = check_guess(self.secret_code, guess_digits, self.wildcard_digit)
        self.guesses.append((guess_digits, colors))
        
        is_win = all(c in ["green", "blue"] for c in colors)
        
        if is_win:
            await self.process_win()
        elif len(self.guesses) >= self.cfg["guesses"]:
            await self.process_loss(reason="no_guesses")
        else:
            await self.update_board()
            
    async def process_win(self):
        self.game_finished = True
        self.stop()
        self.cog.active_games.pop(self.user.id, None)
        
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                
        elapsed = int(time.time() - self.start_time)
        remaining = max(0, self.cfg["time_limit"] - elapsed)
        
        guesses_ratio = (self.cfg["guesses"] - len(self.guesses)) / self.cfg["guesses"]
        time_ratio = remaining / self.cfg["time_limit"]
        
        combo_bonus = 0.1 * min(self.streak, 5)
        hint_penalty = 0.15 * self.hints_used
        
        payout = 0
        net_mult = 0
        if self.is_free_play:
            net_mult = (1 + combo_bonus) * (1 - hint_penalty) * (0.7 + 0.3 * guesses_ratio) * (0.8 + 0.2 * time_ratio)
            payout = int(500 * net_mult)
        else:
            net_mult = self.cfg["multiplier"] * (1 + combo_bonus) * (1 - hint_penalty) * (0.7 + 0.3 * guesses_ratio) * (0.8 + 0.2 * time_ratio)
            payout = int(self.bet_amount * net_mult)
            
        payout = max(0, payout)
        
        if payout > 0:
            self.cog.economy.add_money(self.user.id, payout)
            log_wallet_change(logger, event="giaima_win", user_id=self.user.id, money_delta=payout, channel_id=self.message.channel.id)
            
        stats = self.cog.economy.get_giaima_stats(self.user.id)
        new_streak = stats["streak"] + 1 if self.hints_used == 0 else 0
        new_max_streak = max(stats["max_streak"], new_streak)
        profit = payout - self.bet_amount
        
        game_info = {
            "win": True,
            "guesses_used": len(self.guesses),
            "difficulty": self.difficulty,
            "hints_used": self.hints_used
        }
        new_achievements = list(stats["achievements"])
        newly_unlocked = check_and_unlock_giaima_achievements(stats, game_info)
        new_achievements.extend(newly_unlocked)
        
        self.cog.economy.update_giaima_stats(
            self.user.id,
            wins=1,
            profit=profit,
            streak=new_streak,
            max_streak=new_max_streak,
            achievements=new_achievements
        )
        
        img_buf = render_guess_image(self.guesses[-1][0], self.guesses[-1][1])
        emoji_str = " ".join(get_color_emoji(c) for c in self.guesses[-1][1])
        
        desc = (
            f"🎉 **GIẢI MÃ THÀNH CÔNG! BẠN ĐÃ CHIẾN THẮNG!**\n\n"
            f"👤 **Người chơi:** {self.user.mention}\n"
            f"🔐 **Mật mã đúng:** `{' '.join(str(d) for d in self.secret_code)}`\n"
            f"🎯 **Số lượt đoán:** `{len(self.guesses)}/{self.cfg['guesses']}`\n"
            f"⏳ **Thời gian giải:** `{elapsed} giây`\n"
            f"📈 **Hệ số thưởng:** `x{net_mult:.2f}`\n"
            f"💰 **Tiền thưởng nhận được:** **`{payout:,} VND`**\n"
            f"📈 **Lợi nhuận ròng:** **`{profit:+,} VND`**\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{new_streak}` (Combo: `x{1 + 0.1 * min(new_streak, 5):.1f}`)\n\n"
            f"Kết quả lượt đoán cuối: {emoji_str}"
        )
        
        embed = make_embed(
            title="🔓 GIẢI MÃ BÍ MẬT - CHIẾN THẮNG",
            description=desc,
            color=discord.Color.green()
        )
        if newly_unlocked:
            ach_texts = "\n".join(f"✨ **{GIAIMA_ACHIEVEMENTS[a]}**" for a in newly_unlocked)
            embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=ach_texts, inline=False)
            
        file = discord.File(img_buf, filename="guess.png")
        embed.set_image(url="attachment://guess.png")
        
        await self.message.edit(embed=embed, view=self, attachments=[file])
        
    async def process_loss(self, reason: str = "no_guesses"):
        self.game_finished = True
        self.stop()
        self.cog.active_games.pop(self.user.id, None)
        
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                
        stats = self.cog.economy.get_giaima_stats(self.user.id)
        profit = -self.bet_amount
        
        self.cog.economy.update_giaima_stats(
            self.user.id,
            losses=1,
            profit=profit,
            streak=0
        )
        
        code_str = " ".join(str(d) for d in self.secret_code)
        
        reason_str = "Hết lượt đoán"
        if reason == "timeout":
            reason_str = f"Hết thời gian giải mã ({self.cfg['time_limit']} giây)"
        elif reason == "forfeit":
            reason_str = "Người chơi bỏ cuộc"
            
        desc = (
            f"😢 **GIẢI MÃ THẤT BẠI! GAME OVER!**\n\n"
            f"👤 **Người chơi:** {self.user.mention}\n"
            f"🔐 **Mật mã đúng là:** **`{code_str}`**\n"
            f"❌ **Lý do:** {reason_str}\n"
            f"📉 **Lợi nhuận:** **`-{self.bet_amount:,} VND`**\n"
            f"🔥 Chuỗi thắng đã reset về `0`.\n\n"
        )
        
        if self.guesses:
            emoji_str = " ".join(get_color_emoji(c) for c in self.guesses[-1][1])
            desc += f"Kết quả lượt đoán cuối: {emoji_str}"
            
        embed = make_embed(
            title="🔒 GIẢI MÃ BÍ MẬT - THẤT BẠI",
            description=desc,
            color=discord.Color.red()
        )
        
        if self.guesses:
            img_buf = render_guess_image(self.guesses[-1][0], self.guesses[-1][1])
            file = discord.File(img_buf, filename="guess.png")
            embed.set_image(url="attachment://guess.png")
            await self.message.edit(embed=embed, view=self, attachments=[file])
        else:
            await self.message.edit(embed=embed, view=self)


class GiaiMaInputModal(discord.ui.Modal):
    def __init__(self, game_view: GiaiMaGameView):
        super().__init__(title="🔐 Nhập Mã Giải Mã")
        self.game_view = game_view
        self.code_input = discord.ui.TextInput(
            label=f"Nhập mã số gồm {game_view.cfg['length']} chữ số",
            placeholder="Ví dụ: 1234...",
            min_length=game_view.cfg['length'],
            max_length=game_view.cfg['length'],
            required=True
        )
        self.add_item(self.code_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        guess_str = self.code_input.value.strip()
        
        if not guess_str.isdigit():
            await interaction.followup.send("❌ Mã đoán chỉ được phép chứa các chữ số từ 0 đến 9!", ephemeral=True)
            return
            
        await self.game_view.process_guess(guess_str)


class GiaiMaPvPBetModal(discord.ui.Modal):
    def __init__(self, cog: "GiaiMa", challenger: discord.Member, opponent: discord.Member):
        super().__init__(title="⚔️ Thách Đấu - Nhập Tiền Cược")
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent
        
        self.bet_input = discord.ui.TextInput(
            label="Nhập số coin thách đấu",
            placeholder="Ví dụ: 50k, 10000, all...",
            required=True
        )
        self.add_item(self.bet_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        challenger_money = self.cog.economy.get_entry(self.challenger.id)[1]
        bet_amount = parse_bet_amount(self.bet_input.value, challenger_money)
        
        if bet_amount < 1000:
            await interaction.followup.send("❌ Tiền cược tối thiểu là 1,000 VND.", ephemeral=True)
            return
            
        opponent_money = self.cog.economy.get_entry(self.opponent.id)[1]
        if challenger_money < bet_amount:
            await interaction.followup.send("❌ Bạn không đủ tiền trong tài khoản!", ephemeral=True)
            return
        if opponent_money < bet_amount:
            await interaction.followup.send(f"❌ Đối thủ ({self.opponent.display_name}) không đủ tiền cược ({bet_amount:,} VND)!", ephemeral=True)
            return
            
        view = GiaiMaPvPInviteView(self.cog, self.challenger, self.opponent, bet_amount)
        embed = make_embed(
            title="⚔️ THÁCH ĐẤU GIẢI MÃ BÍ MẬT ⚔️",
            description=(
                f"{self.challenger.mention} đã gửi lời thách đấu Giải Mã Bí Mật đến {self.opponent.mention}!\n\n"
                f"💰 **Mức cược:** `{bet_amount:,} VND` mỗi người (Tổng bể: `{2 * bet_amount:,} VND`)\n"
                f"⚙️ **Độ khó:** Thường (5 chữ số, không trùng lặp, 5 phút, 5 lượt đoán)\n\n"
                f"👉 {self.opponent.mention}, hãy chọn **Chấp Nhận** hoặc **Từ Chối** trong 60 giây!"
            ),
            color=discord.Color.orange()
        )
        invite_msg = await interaction.channel.send(content=f"{self.opponent.mention}", embed=embed, view=view)
        view.message = invite_msg


class GiaiMaPvPInviteView(discord.ui.View):
    def __init__(self, cog: "GiaiMa", challenger: discord.Member, opponent: discord.Member, bet_amount: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.challenger = challenger
        self.opponent = opponent
        self.bet_amount = bet_amount
        self.message = None
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("❌ Chỉ người được thách đấu mới có thể phản hồi!", ephemeral=True)
            return False
        return True
        
    @discord.ui.button(label="✅ Chấp Nhận", style=discord.ButtonStyle.success, custom_id="giaima_pvp_accept")
    async def accept_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        
        c_money = self.cog.economy.get_entry(self.challenger.id)[1]
        o_money = self.cog.economy.get_entry(self.opponent.id)[1]
        
        if c_money < self.bet_amount:
            await interaction.channel.send(f"❌ Ván thách đấu bị hủy do {self.challenger.mention} không còn đủ tiền cược.")
            await self.message.delete()
            return
        if o_money < self.bet_amount:
            await interaction.channel.send(f"❌ Ván thách đấu bị hủy do {self.opponent.mention} không đủ tiền cược.")
            await self.message.delete()
            return
            
        self.cog.economy.add_money(self.challenger.id, -self.bet_amount)
        self.cog.economy.add_money(self.opponent.id, -self.bet_amount)
        
        log_wallet_change(logger, event="giaima_pvp_bet", user_id=self.challenger.id, money_delta=-self.bet_amount, channel_id=interaction.channel_id)
        log_wallet_change(logger, event="giaima_pvp_bet", user_id=self.opponent.id, money_delta=-self.bet_amount, channel_id=interaction.channel_id)
        
        secret_code = random.sample(range(10), k=5)
        
        match_view = GiaiMaPvPMatchView(self.cog, self.challenger, self.opponent, self.bet_amount, secret_code)
        self.cog.active_pvp[self.challenger.id] = match_view
        self.cog.active_pvp[self.opponent.id] = match_view
        
        embed = make_pvp_embed(match_view)
        await self.message.edit(embed=embed, view=match_view)
        match_view.message = self.message

    @discord.ui.button(label="❌ Từ Chối", style=discord.ButtonStyle.danger, custom_id="giaima_pvp_decline")
    async def decline_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.stop()
        await self.message.edit(content=f"❌ {self.opponent.mention} đã từ chối lời thách đấu.", embed=None, view=None)
        
    async def on_timeout(self):
        if self.message:
            try:
                await self.message.edit(content=f"⏰ Lời thách đấu của {self.challenger.mention} đã hết hạn phản hồi.", embed=None, view=None)
            except Exception:
                pass


class GiaiMaPvPMatchView(discord.ui.View):
    def __init__(self, cog: "GiaiMa", p1: discord.Member, p2: discord.Member, bet: int, secret_code: list):
        super().__init__(timeout=300.0)
        self.cog = cog
        self.p1 = p1
        self.p2 = p2
        self.bet = bet
        self.secret_code = secret_code
        
        self.p1_guesses = []
        self.p2_guesses = []
        self.p1_done = False
        self.p2_done = False
        
        self.start_time = time.time()
        self.message = None
        self.game_finished = False
        
    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id not in [self.p1.id, self.p2.id]:
            await interaction.response.send_message("❌ Bạn không tham gia ván đấu PvP này!", ephemeral=True)
            return False
        return True
        
    @discord.ui.button(label="🔢 Nhập Mã", style=discord.ButtonStyle.success, custom_id="giaima_pvp_input")
    async def pvp_input_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid == self.p1.id and self.p1_done:
            await interaction.response.send_message("❌ Bạn đã hoàn thành lượt chơi của mình!", ephemeral=True)
            return
        if uid == self.p2.id and self.p2_done:
            await interaction.response.send_message("❌ Bạn đã hoàn thành lượt chơi của mình!", ephemeral=True)
            return
            
        modal = GiaiMaPvPInputModal(self)
        await interaction.response.send_modal(modal)
        
    @discord.ui.button(label="📋 Xem Lượt Đoán Của Tôi", style=discord.ButtonStyle.primary, custom_id="giaima_pvp_view_guesses")
    async def view_guesses_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer(ephemeral=True)
        uid = interaction.user.id
        guesses = self.p1_guesses if uid == self.p1.id else self.p2_guesses
        
        if not guesses:
            await interaction.followup.send("💡 Bạn chưa thực hiện lượt đoán nào!", ephemeral=True)
            return
            
        history_text = "📋 **Lịch sử đoán của bạn (Có chữ số):**\n"
        for idx, (g_dig, cols) in enumerate(guesses):
            emoji_str = " ".join(get_color_emoji(c) for c in cols)
            dig_str = " ".join(f"[{d}]" for d in g_dig)
            history_text += f"Lượt {idx+1}: {dig_str}  →  {emoji_str}\n"
            
        img_buf = render_guess_image(guesses[-1][0], guesses[-1][1])
        file = discord.File(img_buf, filename="my_guess.png")
        
        await interaction.followup.send(content=history_text, file=file, ephemeral=True)
        
    @discord.ui.button(label="🚪 Bỏ Cuộc", style=discord.ButtonStyle.secondary, custom_id="giaima_pvp_forfeit")
    async def pvp_forfeit_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        uid = interaction.user.id
        winner = self.p2 if uid == self.p1.id else self.p1
        loser = self.p1 if uid == self.p1.id else self.p2
        
        await self.finish_match(winner, loser, reason="forfeit")
        
    async def on_timeout(self):
        if not self.game_finished:
            await self.finish_match(None, None, reason="timeout")
            
    async def process_pvp_guess(self, user_id: int, guess_str: str, interaction: discord.Interaction):
        guess_digits = [int(c) for c in guess_str]
        colors = check_guess(self.secret_code, guess_digits)
        
        is_p1 = (user_id == self.p1.id)
        guesses = self.p1_guesses if is_p1 else self.p2_guesses
        guesses.append((guess_digits, colors))
        
        is_win = all(c == "green" for c in colors)
        
        history_text = "📋 **Kết quả lượt đoán của bạn:**\n"
        for idx, (g_dig, cols) in enumerate(guesses):
            emoji_str = " ".join(get_color_emoji(c) for c in cols)
            dig_str = " ".join(f"[{d}]" for d in g_dig)
            history_text += f"Lượt {idx+1}: {dig_str}  →  {emoji_str}\n"
            
        img_buf = render_guess_image(guess_digits, colors)
        file = discord.File(img_buf, filename="guess.png")
        
        await interaction.followup.send(content=history_text, file=file, ephemeral=True)
        
        if is_win:
            if is_p1:
                self.p1_done = True
            else:
                self.p2_done = True
            winner = self.p1 if is_p1 else self.p2
            loser = self.p2 if is_p1 else self.p1
            await self.finish_match(winner, loser, reason="solve")
            return
            
        if len(guesses) >= 5:
            if is_p1:
                self.p1_done = True
            else:
                self.p2_done = True
                
        if self.p1_done and self.p2_done:
            await self.finish_match(None, None, reason="no_guesses")
        else:
            embed = make_pvp_embed(self)
            await self.message.edit(embed=embed, view=self)
            
    async def finish_match(self, winner: Optional[discord.Member], loser: Optional[discord.Member], reason: str):
        self.game_finished = True
        self.stop()
        
        self.cog.active_pvp.pop(self.p1.id, None)
        self.cog.active_pvp.pop(self.p2.id, None)
        
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
                
        code_str = " ".join(str(d) for d in self.secret_code)
        
        if winner:
            pool = int(2 * self.bet * 0.95)
            self.cog.economy.add_money(winner.id, pool)
            log_wallet_change(logger, event="giaima_pvp_win", user_id=winner.id, money_delta=pool, channel_id=self.message.channel.id)
            
            self.cog.economy.update_giaima_stats(winner.id, plays=1, wins=1, profit=pool - self.bet)
            self.cog.economy.update_giaima_stats(loser.id, plays=1, losses=1, profit=-self.bet)
            
            desc = (
                f"🏆 **TRẬN ĐẤU KẾT THÚC — CHIẾN THẮNG THUỘC VỀ {winner.mention}!**\n\n"
                f"👤 **Người thắng:** {winner.mention} (+`{pool:,} VND`)\n"
                f"👤 **Người thua:** {loser.mention} (-`{self.bet:,} VND`)\n"
                f"🔐 **Mật mã đúng là:** **`{code_str}`**\n\n"
            )
            if reason == "forfeit":
                desc += f"🚪 **Lý do:** {loser.mention} đã bỏ cuộc giữa chừng."
            else:
                desc += f"⚡ **Lý do:** {winner.mention} đã giải mã thành công mật mã trước!"
        else:
            self.cog.economy.add_money(self.p1.id, self.bet)
            self.cog.economy.add_money(self.p2.id, self.bet)
            log_wallet_change(logger, event="giaima_pvp_refund", user_id=self.p1.id, money_delta=self.bet, channel_id=self.message.channel.id)
            log_wallet_change(logger, event="giaima_pvp_refund", user_id=self.p2.id, money_delta=self.bet, channel_id=self.message.channel.id)
            
            self.cog.economy.update_giaima_stats(self.p1.id, plays=1, losses=1, profit=0)
            self.cog.economy.update_giaima_stats(self.p2.id, plays=1, losses=1, profit=0)
            
            desc = (
                f"🤝 **TRẬN ĐẤU KẾT THÚC — HÒA!**\n\n"
                f"🔐 **Mật mã đúng là:** **`{code_str}`**\n"
                f"💰 Cả 2 người chơi đều được hoàn tiền cược (`{self.bet:,} VND`).\n\n"
            )
            if reason == "timeout":
                desc += "⏰ **Lý do:** Đã hết 5 phút thời gian thi đấu."
            else:
                desc += "❌ **Lý do:** Cả hai người đều hết lượt đoán mà không tìm ra đáp án."
                
        desc += f"\n📊 **Tiến độ cuối cùng:**\n"
        desc += f"👤 {self.p1.mention}: `{len(self.p1_guesses)}/5` lượt đoán\n"
        if self.p1_guesses:
            desc += " ".join(get_color_emoji(c) for c in self.p1_guesses[-1][1]) + "\n"
        desc += f"👤 {self.p2.mention}: `{len(self.p2_guesses)}/5` lượt đoán\n"
        if self.p2_guesses:
            desc += " ".join(get_color_emoji(c) for c in self.p2_guesses[-1][1]) + "\n"
            
        embed = make_embed(
            title="⚔️ ĐỐI ĐẦU GIẢI MẠ — KẾT QUẢ",
            description=desc,
            color=discord.Color.purple()
        )
        await self.message.edit(embed=embed, view=self)


class GiaiMaPvPInputModal(discord.ui.Modal):
    def __init__(self, match_view: GiaiMaPvPMatchView):
        super().__init__(title="🔐 PvP Nhập Mã")
        self.match_view = match_view
        self.code_input = discord.ui.TextInput(
            label="Nhập mã số gồm 5 chữ số",
            placeholder="Ví dụ: 08529...",
            min_length=5,
            max_length=5,
            required=True
        )
        self.add_item(self.code_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guess_str = self.code_input.value.strip()
        
        if not guess_str.isdigit():
            await interaction.followup.send("❌ Mã đoán chỉ chứa các chữ số từ 0 đến 9!", ephemeral=True)
            return
            
        await self.match_view.process_pvp_guess(interaction.user.id, guess_str, interaction)


class BossEventGuessView(discord.ui.View):
    def __init__(self, cog: "GiaiMa"):
        super().__init__(timeout=None)
        self.cog = cog
        
    @discord.ui.button(label="🔓 Thử Vận May", style=discord.ButtonStyle.success, custom_id="giaima_boss_guess")
    async def guess_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        is_active = self.cog.economy.get_setting("giaima_boss_active") == "1"
        if not is_active:
            await interaction.response.send_message("❌ Sự kiện Boss Server hiện tại không hoạt động hoặc đã kết thúc!", ephemeral=True)
            return
            
        uid = interaction.user.id
        now = time.time()
        last_guess = self.cog.boss_cooldowns.get(uid, 0)
        cooldown_duration = 30.0
        if now - last_guess < cooldown_duration:
            rem = int(cooldown_duration - (now - last_guess))
            await interaction.response.send_message(f"❌ Bạn đang trong thời gian chờ! Vui lòng đợi {rem} giây nữa để đoán tiếp.", ephemeral=True)
            return
            
        modal = GiaiMaBossInputModal(self.cog)
        await interaction.response.send_modal(modal)


class GiaiMaBossInputModal(discord.ui.Modal):
    def __init__(self, cog: "GiaiMa"):
        super().__init__(title="🔓 Boss Server - Giải Mã")
        self.cog = cog
        
        self.code_input = discord.ui.TextInput(
            label="Nhập mật mã đoán gồm 6 chữ số",
            placeholder="Ví dụ: 951357...",
            min_length=6,
            max_length=6,
            required=True
        )
        self.add_item(self.code_input)
        
    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        guess_str = self.code_input.value.strip()
        uid = interaction.user.id
        
        if not guess_str.isdigit():
            await interaction.followup.send("❌ Mã đoán chỉ được phép chứa các chữ số từ 0 đến 9!", ephemeral=True)
            return
            
        is_active = self.cog.economy.get_setting("giaima_boss_active") == "1"
        if not is_active:
            await interaction.followup.send("❌ Sự kiện Boss Server đã kết thúc trước đó!", ephemeral=True)
            return
            
        self.cog.boss_cooldowns[uid] = time.time()
        
        secret_str = self.cog.economy.get_setting("giaima_boss_code")
        secret_code = [int(c) for c in secret_str]
        
        guess_digits = [int(c) for c in guess_str]
        colors = check_guess(secret_code, guess_digits)
        emoji_str = " ".join(get_color_emoji(c) for c in colors)
        
        is_win = all(c == "green" for c in colors)
        
        jackpot_str = self.cog.economy.get_setting("giaima_boss_jackpot") or "100000"
        jackpot = int(jackpot_str)
        
        img_buf = render_guess_image(guess_digits, colors)
        file = discord.File(img_buf, filename="boss_guess.png")
        
        if is_win:
            self.cog.economy.add_money(uid, jackpot)
            log_wallet_change(logger, event="giaima_boss_jackpot_win", user_id=uid, money_delta=jackpot, channel_id=interaction.channel_id)
            
            self.cog.economy.set_setting("giaima_boss_active", "0")
            
            desc = (
                f"🎉🎉 **CHÚC MỪNG {interaction.user.mention} ĐÃ GIẢI MÃ THÀNH CÔNG BOSS SERVER!** 🎉🎉\n\n"
                f"🔐 **Mật mã đúng của Boss:** **`{guess_str}`**\n"
                f"💰 **Phần thưởng Jackpot:** **`{jackpot:,} VND`**\n\n"
                f"Sự kiện Boss Server đã chính thức khép lại. Cảm ơn mọi người đã tham gia đoán!"
            )
            embed = make_embed(
                title="👾 BOSS SERVER - GIẢI MÃ THÀNH CÔNG!",
                description=desc,
                color=discord.Color.green()
            )
            embed.set_image(url="attachment://boss_guess.png")
            
            msg_id = self.cog.economy.get_setting("giaima_boss_message_id")
            chan_id = self.cog.economy.get_setting("giaima_boss_channel_id")
            if msg_id and chan_id:
                try:
                    channel = self.cog.bot.get_channel(int(chan_id))
                    if channel:
                        msg = await channel.fetch_message(int(msg_id))
                        if msg:
                            view = discord.ui.View()
                            btn = discord.ui.Button(label="🔓 Thử Vận May (Đã Giải Mã)", style=discord.ButtonStyle.success, disabled=True)
                            view.add_item(btn)
                            await msg.edit(embed=embed, view=view, attachments=[file])
                except Exception as e:
                    logger.error(f"Failed to edit boss message: {e}")
                    
            await interaction.followup.send(f"🎉 Tuyệt vời! Bạn đã mở khóa mật mã Boss và nhận **{jackpot:,} VND**!", ephemeral=True)
        else:
            new_jackpot = jackpot + 1000
            self.cog.economy.set_setting("giaima_boss_jackpot", str(new_jackpot))
            
            history_str = self.cog.economy.get_setting("giaima_boss_guesses") or "[]"
            history = json.loads(history_str)
            
            history.append({
                "username": interaction.user.name,
                "guess": guess_str,
                "emojis": emoji_str,
                "time": int(time.time())
            })
            history = history[-10:]
            self.cog.economy.set_setting("giaima_boss_guesses", json.dumps(history))
            
            msg_id = self.cog.economy.get_setting("giaima_boss_message_id")
            chan_id = self.cog.economy.get_setting("giaima_boss_channel_id")
            if msg_id and chan_id:
                try:
                    channel = self.cog.bot.get_channel(int(chan_id))
                    if channel:
                        msg = await channel.fetch_message(int(msg_id))
                        if msg:
                            embed = make_boss_embed(new_jackpot, history)
                            await msg.edit(embed=embed)
                except Exception as e:
                    logger.error(f"Failed to update boss message: {e}")
                    
            await interaction.followup.send(f"❌ Sai rồi! Kết quả của bạn: {emoji_str}\n💰 Jackpot tăng thêm 1,000 VND!", file=file, ephemeral=True)


class GiaiMa(commands.Cog, name="GiaiMa"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.active_games: Dict[int, GiaiMaGameView] = {}
        self.active_pvp: Dict[int, GiaiMaPvPMatchView] = {}
        self.boss_cooldowns: Dict[int, float] = {}
        
        # Load persistent views on init
        self.bot.add_view(BossEventGuessView(self))

    @commands.group(
        name="giaima",
        aliases=["gm", "mastermind", "decryption"],
        brief="Trò chơi đoán số - Giải mã bí mật.",
        invoke_without_command=True
    )
    async def giaima_group(self, ctx: commands.Context):
        """
        Bảng điều khiển chính của trò chơi Giải Mã Bí Mật.
        """
        user_id = ctx.author.id
        if user_id in self.active_games:
            await ctx.send("❌ Bạn đang có một ván Giải Mã đang diễn ra! Hãy hoàn thành ván cũ trước.")
            return
        if user_id in self.active_pvp:
            await ctx.send("❌ Bạn đang trong một trận đấu PvP Giải Mã!")
            return
            
        view = GiaiMaLobbyView(self, user_id)
        embed = make_embed(
            title="🔐 GIẢI MÃ BÍ MẬT — SẢNH CHỜ",
            description=(
                "Hãy tìm ra mật mã bí mật bằng cách đoán các dãy số!\n"
                "Sau mỗi lượt đoán, các chữ số sẽ đổi màu tương tự Wordle:\n\n"
                "🟩 **Xanh lá:** Đúng chữ số, đúng vị trí.\n"
                "🟨 **Vàng:** Đúng chữ số, sai vị trí.\n"
                "⬛ **Xám:** Số không có trong mật mã.\n"
                "🟦 **Xanh dương (Nightmare):** Số thuộc về Wildcard trúng bất kỳ vị trí nào.\n\n"
                "⚙️ **Bảng độ khó & Hệ số thưởng:**\n"
                "• 🟢 **Dễ:** 4 chữ số, không trùng lặp | 5 phút | 6 lượt | `x1.2`\n"
                "• 🟡 **Thường:** 5 chữ số, không trùng lặp | 5 phút | 5 lượt | `x2.2`\n"
                "• 🟠 **Khó:** 5 chữ số, có trùng lặp | 3 phút | 4 lượt | `x4.0`\n"
                "• 🔴 **Ác Mộng:** 6 chữ số, có trùng lặp | 2 phút | 3 lượt | `x8.0`\n\n"
                "👉 Hãy click vào một trong các nút dưới đây để bắt đầu chơi hoặc xem xếp hạng!"
            ),
            color=discord.Color.purple()
        )
        embed.set_footer(text="🎰 Casino Bot • Giải Mã Bí Mật")
        view.message = await ctx.send(embed=embed, view=view)

    @giaima_group.command(name="pvp", brief="Thách đấu PvP Giải Mã Bí Mật.")
    async def pvp_command(self, ctx: commands.Context, opponent: discord.Member, bet_amount_str: str):
        """
        Thách đấu PvP Giải Mã Bí Mật với một người chơi khác.
        Cú pháp: i?giaima pvp <@user> <bet>
        Ví dụ: i?giaima pvp @Username 50k
        """
        user_id = ctx.author.id
        if opponent.id == user_id:
            await ctx.send("❌ Bạn không thể thách đấu chính mình!")
            return
        if opponent.bot:
            await ctx.send("❌ Bạn không thể thách đấu bot!")
            return
            
        if user_id in self.active_games or opponent.id in self.active_games:
            await ctx.send("❌ Một trong hai người chơi đang có một ván Giải Mã đơn lẻ đang hoạt động.")
            return
        if user_id in self.active_pvp or opponent.id in self.active_pvp:
            await ctx.send("❌ Một trong hai người chơi đang trong trạng thái thách đấu/PvP khác.")
            return
            
        challenger_money = self.economy.get_entry(user_id)[1]
        bet_amount = parse_bet_amount(bet_amount_str, challenger_money)
        
        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 VND.")
            return
            
        opponent_money = self.economy.get_entry(opponent.id)[1]
        if challenger_money < bet_amount:
            await ctx.send("❌ Bạn không đủ tiền trong tài khoản!")
            return
        if opponent_money < bet_amount:
            await ctx.send(f"❌ Đối thủ ({opponent.display_name}) không đủ tiền cược ({bet_amount:,} VND)!")
            return
            
        view = GiaiMaPvPInviteView(self, ctx.author, opponent, bet_amount)
        embed = make_embed(
            title="⚔️ THÁCH ĐẤU GIẢI MÃ BÍ MẬT ⚔️",
            description=(
                f"{ctx.author.mention} đã gửi lời thách đấu Giải Mã Bí Mật đến {opponent.mention}!\n\n"
                f"💰 **Mức cược:** `{bet_amount:,} VND` mỗi người (Tổng bể: `{2 * bet_amount:,} VND`)\n"
                f"⚙️ **Độ khó:** Thường (5 chữ số, không trùng lặp, 5 phút, 5 lượt đoán)\n\n"
                f"👉 {opponent.mention}, hãy chọn **Chấp Nhận** hoặc **Từ Chối** trong 60 giây!"
            ),
            color=discord.Color.orange()
        )
        invite_msg = await ctx.send(content=opponent.mention, embed=embed, view=view)
        view.message = invite_msg

    @commands.group(
        name="giaimaboss",
        brief="Quản lý/Tham gia sự kiện Boss Server giải mã.",
        invoke_without_command=True
    )
    async def giaimaboss_group(self, ctx: commands.Context):
        """
        Hiển thị trạng thái sự kiện Boss Server.
        """
        is_active = self.economy.get_setting("giaima_boss_active") == "1"
        if not is_active:
            await ctx.send("❌ Hiện tại không có sự kiện Boss Server nào hoạt động.")
            return
            
        jackpot_str = self.economy.get_setting("giaima_boss_jackpot") or "100000"
        jackpot = int(jackpot_str)
        
        history_str = self.economy.get_setting("giaima_boss_guesses") or "[]"
        history = json.loads(history_str)
        
        embed = make_boss_embed(jackpot, history)
        view = BossEventGuessView(self)
        await ctx.send(embed=embed, view=view)

    @giaimaboss_group.command(name="start", brief="Bắt đầu sự kiện Boss Server (Admin).")
    @commands.has_permissions(administrator=True)
    async def boss_start(self, ctx: commands.Context, jackpot_start_str: str = "100k"):
        """
        Bắt đầu một sự kiện Boss Server mới.
        Cú pháp: i?giaimaboss start [jackpot_start]
        Ví dụ: i?giaimaboss start 100k
        """
        is_active = self.economy.get_setting("giaima_boss_active") == "1"
        if is_active:
            await ctx.send("❌ Sự kiện Boss Server đang chạy rồi! Vui lòng dừng sự kiện cũ trước.")
            return
            
        jackpot_start = parse_bet_amount(jackpot_start_str, 999_999_999)
        if jackpot_start <= 0:
            jackpot_start = 100_000
            
        # Generate boss code (6 digits, duplicates allowed)
        secret_code = [random.randint(0, 9) for _ in range(6)]
        secret_str = "".join(str(d) for d in secret_code)
        
        # Save to database settings
        self.economy.set_setting("giaima_boss_active", "1")
        self.economy.set_setting("giaima_boss_code", secret_str)
        self.economy.set_setting("giaima_boss_jackpot", str(jackpot_start))
        self.economy.set_setting("giaima_boss_guesses", "[]")
        self.economy.set_setting("giaima_boss_channel_id", str(ctx.channel.id))
        
        embed = make_boss_embed(jackpot_start, [])
        view = BossEventGuessView(self)
        msg = await ctx.send(embed=embed, view=view)
        
        self.economy.set_setting("giaima_boss_message_id", str(msg.id))
        await ctx.send(f"✅ Đã khởi chạy sự kiện Boss Server thành công với Jackpot khởi điểm: `{jackpot_start:,} VND`!")

    @giaimaboss_group.command(name="stop", brief="Dừng sự kiện Boss Server (Admin).")
    @commands.has_permissions(administrator=True)
    async def boss_stop(self, ctx: commands.Context):
        """
        Dừng và hủy sự kiện Boss Server hiện tại.
        """
        is_active = self.economy.get_setting("giaima_boss_active") == "1"
        if not is_active:
            await ctx.send("❌ Hiện tại không có sự kiện Boss Server nào hoạt động.")
            return
            
        secret_str = self.economy.get_setting("giaima_boss_code") or "N/A"
        self.economy.set_setting("giaima_boss_active", "0")
        
        # Edit boss message to reveal code and disable buttons
        msg_id = self.economy.get_setting("giaima_boss_message_id")
        chan_id = self.economy.get_setting("giaima_boss_channel_id")
        if msg_id and chan_id:
            try:
                channel = self.bot.get_channel(int(chan_id))
                if channel:
                    msg = await channel.fetch_message(int(msg_id))
                    if msg:
                        embed = msg.embeds[0]
                        embed.title = "👾 BOSS SERVER — ĐÃ BỊ DỪNG"
                        embed.description = f"❌ Sự kiện đã bị Admin hủy bỏ.\n🔐 Mật mã đúng của Boss là: **`{secret_str}`**"
                        view = discord.ui.View()
                        btn = discord.ui.Button(label="🔓 Thử Vận May (Đã Kết Thúc)", style=discord.ButtonStyle.success, disabled=True)
                        view.add_item(btn)
                        await msg.edit(embed=embed, view=view)
            except Exception as e:
                logger.error(f"Failed to stop boss message: {e}")
                
        await ctx.send(f"✅ Đã dừng sự kiện Boss Server. Mật mã đúng là: `{secret_str}`.")


async def setup(bot: commands.Bot):
    await bot.add_cog(GiaiMa(bot))
