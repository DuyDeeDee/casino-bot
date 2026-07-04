import asyncio
from datetime import datetime
import logging
import random
import time
import os
import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.helpers import InsufficientFundsException

logger = logging.getLogger(__name__)

# Colors configuration matching spec
WHEEL_CONFIG = {
    'blue':   { 'slots': 12, 'multiplier': 2,  'emoji': '🔵', 'label': 'Xanh dương', 'color_arg': 'xanh' },
    'green':  { 'slots': 10, 'multiplier': 3,  'emoji': '🟢', 'label': 'Xanh lá',    'color_arg': 'xanhla' },
    'yellow': { 'slots': 6,  'multiplier': 5,  'emoji': '🟡', 'label': 'Vàng',       'color_arg': 'vang' },
    'red':    { 'slots': 2,  'multiplier': 10, 'emoji': '🔴', 'label': 'Đỏ',         'color_arg': 'do' },
}

COLOR_MAP = {
    "xanh": "blue",
    "xanhla": "green",
    "vang": "yellow",
    "do": "red"
}

# The exact 30-slot layout from the Node.js script
WHEEL_LAYOUT = [
  'blue', 'green', 'blue', 'green', 'yellow', 'green', 'yellow', 'blue', 'yellow', 'blue',
  'yellow', 'blue', 'green', 'blue', 'green', 'yellow', 'blue', 'green', 'blue', 'green',
  'blue', 'green', 'blue', 'red', 'blue', 'yellow', 'green', 'blue', 'green', 'red'
]

class CasinoEmbed(discord.Embed):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._colour = discord.Color.from_str("#c8a84b")

    @property
    def color(self):
        return discord.Color.from_str("#c8a84b")

    @color.setter
    def color(self, value):
        pass

    @property
    def colour(self):
        return discord.Color.from_str("#c8a84b")

    @colour.setter
    def colour(self, value):
        pass

def parse_bet_amount(val_str: str, current_money: int) -> int:
    val_str = val_str.strip().lower()
    if val_str in ["all", "allin", "all-in", "tất tay"]:
        from app.discord_bot.modules.betting import get_capped_all_in_amount
        return get_capped_all_in_amount(current_money)
    
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

class ColorWheelConfirmView(discord.ui.View):
    def __init__(self, cog: "Quay", ctx: commands.Context, bet_amount: int, chosen_color: str):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.bet_amount = bet_amount
        self.chosen_color = chosen_color
        self.message = None
        self.clicked = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Đây không phải lượt quay của bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Quay ngay!", style=discord.ButtonStyle.success, emoji="🎡")
    async def spin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.clicked = True
        self.stop()
        await self.cog.run_spin(self.ctx, self.bet_amount, self.chosen_color, self.message)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.clicked = True
        self.stop()
        self.cog.active_players.discard(self.ctx.author.id)
        
        embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description=f"❌ **{self.ctx.author.mention} đã hủy lượt quay.**",
        )
        await self.message.edit(embed=embed, view=None)

    async def on_timeout(self):
        if not self.clicked:
            self.stop()
            self.cog.active_players.discard(self.ctx.author.id)
            embed = CasinoEmbed(
                title="🎡 VÒNG QUAY MAY MẮN",
                description=f"⏱️ **Đã hết thời gian xác nhận. Lượt quay bị hủy.**",
            )
            try:
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass

class Quay(commands.Cog, name="Quay"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.active_players = set()
        
        # Initialize SQLite database schema for SpinResult logs
        try:
            self.economy.cur.execute(
                """CREATE TABLE IF NOT EXISTS spin_results (
                    user_id TEXT,
                    guild_id TEXT,
                    bet_amount INTEGER,
                    chosen_color TEXT,
                    result_color TEXT,
                    multiplier INTEGER,
                    is_win INTEGER,
                    payout INTEGER,
                    profit INTEGER,
                    timestamp TEXT
                )"""
            )
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to create spin_results table: {e}")

    @commands.hybrid_command(
        name="quay",
        brief="Chơi game casino Vòng Quay May Mắn. Ví dụ: `i?quay 50k xanh`\nCác màu hợp lệ: `xanh` (x2), `xanhla` (x3), `vang` (x5), `do` (x10)",
        usage="quay [tiền_cược] [màu]",
        description="Đoán màu và cược tiền vào Color Wheel"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        bet_amount_str="Số tiền đặt cược (Tối thiểu 1,000, Tối đa 10,000,000, VD: 50k, 50000, all)",
        mau="Màu cược: xanh (x2), xanhla (x3), vang (x5), do (x10)"
    )
    @discord.app_commands.choices(mau=[
        discord.app_commands.Choice(name="🔵 Xanh dương (x2)", value="xanh"),
        discord.app_commands.Choice(name="🟢 Xanh lá (x3)", value="xanhla"),
        discord.app_commands.Choice(name="🟡 Vàng (x5)", value="vang"),
        discord.app_commands.Choice(name="🔴 Đỏ (x10)", value="do")
    ])
    async def quay(self, ctx: commands.Context, bet_amount_str: str, mau: str):
        user_id = ctx.author.id
        
        # Concurrency check
        if user_id in self.active_players:
            await ctx.send("❌ Bạn đang có một ván quay khác đang diễn ra. Vui lòng hoàn thành ván đó trước.", ephemeral=True)
            return

        # Cooldown is handled by decorator and cog_command_error

        # Parse and validate chosen color
        mau = mau.lower().strip()
        if mau not in COLOR_MAP:
            await ctx.send("❌ Màu cược không hợp lệ. Vui lòng chọn một trong: xanh, xanhla, vang, do.", ephemeral=True)
            return
            
        chosen_color = COLOR_MAP[mau]
        
        # Get wallet balance
        current_money = self.economy.get_entry(user_id)[1]
        
        # Parse bet amount
        bet_amount = parse_bet_amount(bet_amount_str, current_money)
        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 VNĐ.", ephemeral=True)
            return
        if bet_amount > 10000000:
            await ctx.send("❌ Tiền cược tối đa là 10,000,000 VNĐ.", ephemeral=True)
            return
            
        if current_money < bet_amount:
            await ctx.send(f"❌ Bạn không đủ tiền trong ví để thực hiện cược này. Ví của bạn: {current_money:,} VNĐ.", ephemeral=True)
            return
            
        # Lock player in this cog
        self.active_players.add(user_id)
        
        # Build selection embed
        embed = self.format_confirm_embed(ctx.author.mention, bet_amount, chosen_color)
        
        view = ColorWheelConfirmView(self, ctx, bet_amount, chosen_color)
        view.message = await ctx.send(embed=embed, view=view)

    def format_confirm_embed(self, user_mention: str, bet_amount: int, chosen_color: str) -> CasinoEmbed:
        opts = {
            "blue": "🔵 Xanh dương · x2 · 40%",
            "green": "🟢 Xanh lá · x3 · 33%",
            "yellow": "🟡 Vàng · x5 · 20%",
            "red": "🔴 Đỏ · x10 · 7%"
        }
        
        desc_lines = []
        for key, text in opts.items():
            if key == chosen_color:
                desc_lines.append(f"**[ĐÃ CHỌN]**\n{text}\n")
            else:
                desc_lines.append(f"{text}")
                
        desc = (
            f"👤 **Người chơi:** {user_mention}\n"
            f"💰 **Tiền cược:** `{bet_amount:,} VNĐ`\n\n"
            "\n".join(desc_lines)
        )
        
        embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description=desc
        )
        embed.set_footer(text="Nhấn nút dưới đây để bắt đầu quay!")
        return embed

    async def run_spin(self, ctx: commands.Context, bet_amount: int, chosen_color: str, message: discord.Message):
        user_id = ctx.author.id
        guild_id = ctx.guild.id if ctx.guild else 0
        
        # Double check money
        current_money = self.economy.get_entry(user_id)[1]
        if current_money < bet_amount:
            self.active_players.discard(user_id)
            await message.edit(content="❌ Bạn không đủ tiền trong ví để quay!", embed=None, view=None)
            return
            
        # Deduct wallet
        self.economy.add_money(user_id, -bet_amount)
        log_wallet_change(logger, event="color_wheel_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
        
        # Random spin slot
        win_idx = random.randint(0, 29)
        result_color = WHEEL_LAYOUT[win_idx]
        
        # Generate spin GIF
        gif_filename = f"wheel_spin_{user_id}_{int(time.time())}.gif"
        gif_path = os.path.join(config.storage.data_dir, gif_filename)
        
        try:
            node_path = "node"
            script_path = os.path.join("app", "discord_bot", "modules", "wheel_spinner.js")
            
            proc = await asyncio.create_subprocess_exec(
                node_path, script_path, str(win_idx), gif_path,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, stderr = await proc.communicate()
            
            if proc.returncode != 0:
                logger.error(f"Node GIF generation failed: {stderr.decode()}")
                # Refund
                self.economy.add_money(user_id, bet_amount)
                log_wallet_change(logger, event="color_wheel_error_refund", user_id=user_id, money_delta=bet_amount, ctx=ctx)
                self.active_players.discard(user_id)
                await message.edit(content="❌ Đã xảy ra lỗi khi tạo hiệu ứng vòng quay.", embed=None, view=None)
                return
        except Exception as e:
            logger.error(f"Error calling Node script: {e}")
            self.economy.add_money(user_id, bet_amount)
            log_wallet_change(logger, event="color_wheel_error_refund", user_id=user_id, money_delta=bet_amount, ctx=ctx)
            self.active_players.discard(user_id)
            await message.edit(content="❌ Không thể kết nối với dịch vụ tạo hiệu ứng.", embed=None, view=None)
            return

        # Send embedding GIF "Vòng quay đang chạy..."
        file = discord.File(gif_path, filename="wheel_spin.gif")
        spinning_embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description="⏳ **Vòng quay đang chạy... Chúc bạn may mắn!**"
        )
        spinning_embed.set_image(url="attachment://wheel_spin.gif")
        
        # Edit the message
        await message.edit(content=None, embed=spinning_embed, attachments=[file], view=None)
        
        # Wait 1.5 seconds for spin
        await asyncio.sleep(1.5)
        
        # Calculate result
        is_win = (result_color == chosen_color)
        cfg_res = WHEEL_CONFIG[result_color]
        multiplier = cfg_res["multiplier"]
        
        payout = 0
        profit = -bet_amount
        if is_win:
            payout = bet_amount * multiplier
            profit = payout - bet_amount
            # Add money to player wallet
            self.economy.add_money(user_id, payout)
            log_wallet_change(logger, event="color_wheel_win", user_id=user_id, money_delta=payout, ctx=ctx)
        else:
            log_wallet_change(logger, event="color_wheel_loss", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
            
        # Log to Database
        try:
            self.economy.cur.execute(
                """INSERT INTO spin_results (
                    user_id, guild_id, bet_amount, chosen_color,
                    result_color, multiplier, is_win, payout, profit, timestamp
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    str(user_id),
                    str(guild_id),
                    bet_amount,
                    chosen_color,
                    result_color,
                    multiplier,
                    1 if is_win else 0,
                    payout,
                    profit,
                    datetime.now().isoformat()
                )
            )
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to record spin result to DB: {e}")

        # Formulate final embed
        now = datetime.now()
        am_pm = "SA" if now.hour < 12 else "CH"
        hour = now.hour if now.hour <= 12 else now.hour - 12
        if hour == 0:
            hour = 12
        footer_text = f"Sylus Meow • {now.strftime('%d/%m/%Y')} {hour:02d}:{now.strftime('%M')} {am_pm}"
        
        result_desc_lines = []
        result_desc_lines.append("🎡 VÒNG QUAY MAY MẮN")
        result_desc_lines.append("━━━━━━━━━━━━━━━━━━━")
        result_desc_lines.append(f"👤 Người chơi: {ctx.author.mention}")
        result_desc_lines.append(f"💰 Tiền cược:  {bet_amount:,} VNĐ\n")
        
        result_desc_lines.append("[ĐÃ CHỌN]")
        cfg_chosen = WHEEL_CONFIG[chosen_color]
        pct_chosen = "40%" if chosen_color == 'blue' else "33%" if chosen_color == 'green' else "20%" if chosen_color == 'yellow' else "7%"
        result_desc_lines.append(f"{cfg_chosen['emoji']} {cfg_chosen['label']} · x{cfg_chosen['multiplier']} · {pct_chosen}\n")
        
        result_desc_lines.append("KẾT QUẢ VÒNG QUAY")
        color_label_upper = cfg_res['label'].upper()
        if is_win:
            result_desc_lines.append(f"✅ {cfg_res['emoji']} {color_label_upper} (x{multiplier})\n")
        else:
            result_desc_lines.append(f"{cfg_res['emoji']} {color_label_upper} (x{multiplier}) — Không trúng\n")
            
        result_desc_lines.append("━━━ KẾT QUẢ ━━━")
        col_profit = "Lợi nhuận" if is_win else "Lỗ"
        result_desc_lines.append(f"Tiền cược  │ Nhận về   │ {col_profit}")
        
        # Alignment logic
        bet_str = f"{bet_amount:,}".ljust(11)
        payout_str = f"{payout:,}".ljust(10)
        profit_val_str = f"+{profit:,}" if is_win else f"-{abs(profit):,}"
        result_desc_lines.append(f"{bet_str}│ {payout_str}│ {profit_val_str}\n")
        
        if is_win:
            result_desc_lines.append(f"✅ CHÚC MỪNG! Bạn đã thắng ván này.")
        else:
            result_desc_lines.append(f"❌ Chúc bạn may mắn lần sau.")
            
        result_desc_lines.append("━━━━━━━━━━━━━━━━━━━")
        
        final_embed = CasinoEmbed(
            description="\n".join(result_desc_lines)
        )
        final_embed.set_footer(text=footer_text)
        
        # Edit the message to show final result and remove attachments
        try:
            await message.edit(embed=final_embed, attachments=[])
        except Exception:
            # Fallback if attachments cannot be cleared easily
            await message.delete()
            await ctx.send(embed=final_embed)
            
        # Clean up temporary GIF file
        try:
            if os.path.exists(gif_path):
                os.remove(gif_path)
        except Exception as e:
            logger.warning(f"Failed to delete temp gif: {e}")
            
        # Unlock player
        self.active_players.discard(user_id)

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        # Local exception handler to send ephemeral errors on interactions
        if isinstance(error, commands.CommandOnCooldown):
            seconds = int(error.retry_after)
            await ctx.send(f"❌ **Lệnh đang trong thời gian chờ!** Vui lòng thử lại sau `{seconds}` giây.", ephemeral=True)
            return True
            
        if isinstance(error, InsufficientFundsException):
            await ctx.send("❌ **Bạn không đủ tiền trong ví để thực hiện cược này.**", ephemeral=True)
            return True
            
        if isinstance(error, commands.BadArgument):
            await ctx.send("❌ **Sử dụng sai cú pháp!** Cú pháp: `/quay [tiền_cược] [màu]`", ephemeral=True)
            return True
            
        # Propagate other errors
        return False

async def setup(bot: commands.Bot):
    await bot.add_cog(Quay(bot))
