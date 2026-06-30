import asyncio
import logging
import random
from io import BytesIO
from datetime import datetime
from typing import Optional

import discord
from discord.ext import commands
from PIL import Image, ImageDraw

from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.profile_renderer import load_font, fetch_avatar

logger = logging.getLogger(__name__)

PLINKO_ACHIEVEMENTS = {
    "first_drop": "💎 Thả bóng đầu tiên",
    "hit_10x": "🎉 Trúng 10x",
    "hit_100x": "👑 Trúng 100x",
    "win_streak_5": "🔥 Thắng 5 lần liên tiếp",
    "profit_10m": "💰 Lãi 10 triệu từ Plinko",
}

RISK_SETTINGS = {
    "low": {
        "multipliers": [1.5, 1.2, 1.0, 0.8],
        "weights": [0.05, 0.15, 0.45, 0.35],
        "description": "🟢 Risk Low: Thường rơi giữa, ít lời ít lỗ."
    },
    "medium": {
        "multipliers": [5.0, 2.0, 1.0, 0.5, 0.2],
        "weights": [0.025, 0.13, 0.40, 0.285, 0.16],
        "description": "🟡 Risk Medium: Cân bằng, ổn định."
    },
    "high": {
        "multipliers": [100.0, 25.0, 10.0, 5.0, 3.0, 2.0, 1.0, 0.5, 0.2, 0.0],
        "weights": [0.0005, 0.0025, 0.008, 0.025, 0.05, 0.10, 0.18, 0.22, 0.20, 0.214],
        "description": "🔴 Risk High: Có thể mất trắng, nhưng Jackpot cực lớn!"
    }
}

BIN_LAYOUTS = {
    "low": [1.5, 1.2, 1.0, 0.8, 1.0, 1.2, 1.5],
    "medium": [5.0, 2.0, 1.0, 0.5, 0.2, 0.5, 1.0, 2.0, 5.0],
    "high": [100.0, 25.0, 10.0, 5.0, 2.0, 0.0, 0.2, 0.5, 1.0, 3.0, 100.0]
}


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


def check_and_unlock_plinko_achievements(stats: dict, final_multiplier: float, total_profit: int) -> list[str]:
    unlocked = set(stats.get("achievements", []))
    newly_unlocked = []

    plays = stats.get("plays", 0)
    streak = stats.get("streak", 0)

    if plays >= 1 and "first_drop" not in unlocked:
        newly_unlocked.append("first_drop")
        
    if final_multiplier >= 10.0 and "hit_10x" not in unlocked:
        newly_unlocked.append("hit_10x")
        
    if final_multiplier >= 100.0 and "hit_100x" not in unlocked:
        newly_unlocked.append("hit_100x")
        
    if streak >= 5 and "win_streak_5" not in unlocked:
        newly_unlocked.append("win_streak_5")
        
    if total_profit >= 10_000_000 and "profit_10m" not in unlocked:
        newly_unlocked.append("profit_10m")
        
    return newly_unlocked


def render_plinko_gif(
    risk: str,
    multiplier: float,
    target_index: int,
    directions: list[str],
) -> BytesIO:
    # 1. Determine size
    width = 412
    height = 250
    
    # 2. Get configuration
    N = len(directions) # 6, 8, or 10
    
    frames = []
    
    for f in range(N + 1):
        # Panel bg #161a2e
        img = Image.new("RGBA", (width, height), (22, 26, 46, 255))
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        font_small = load_font("regular", 10)
        
        # Title box
        draw.text((width/2 - 45, 12), "ĐƯỜNG BÓNG RƠI", font=font_small, fill=(143, 148, 168, 255))
        
        cx = width / 2
        y0 = 35
        
        if N == 6:
            dy, dx = 26, 34
        elif N == 8:
            dy, dx = 20, 26
        else:
            dy, dx = 16, 20
            
        # Draw pegs
        for r in range(N):
            num_pegs = r + 1
            peg_xs = [cx + (i - r / 2) * dx for i in range(num_pegs)]
            y_peg = y0 + r * dy
            for px in peg_xs:
                draw.ellipse([px - 2, y_peg - 2, px + 2, y_peg + 2], fill=(71, 85, 105, 255))
                
        # Draw bins
        y_bin = y0 + N * dy
        bin_layout = BIN_LAYOUTS[risk]
        w_bin = dx - 4
        h_bin = 22
        
        for i, val in enumerate(bin_layout):
            bx_center = cx + (i - N / 2) * dx
            bx1 = bx_center - w_bin / 2
            bx2 = bx_center + w_bin / 2
            by1 = y_bin
            by2 = y_bin + h_bin
            
            is_active = (f == N and i == target_index)
            bin_text = f"{val:.1f}x" if val % 1 != 0 else f"{int(val)}x"
            
            if is_active:
                draw.rounded_rectangle([bx1, by1, bx2, by2], radius=4, fill=(45, 212, 191, 255), outline=(20, 184, 166, 255), width=1)
                try:
                    btn_w = font_small.getlength(bin_text)
                except AttributeError:
                    btn_w = len(bin_text) * 5
                draw.text((bx_center - btn_w/2, by1 + 5), bin_text, font=font_small, fill=(15, 19, 34, 255))
            else:
                draw.rounded_rectangle([bx1, by1, bx2, by2], radius=4, fill=(17, 21, 36, 255), outline=(34, 40, 62, 255), width=1)
                try:
                    btn_w = font_small.getlength(bin_text)
                except AttributeError:
                    btn_w = len(bin_text) * 5
                draw.text((bx_center - btn_w/2, by1 + 5), bin_text, font=font_small, fill=(52, 211, 153, 100))
                
        # Draw path
        path_coords = [(cx, y0 - 15)]
        offset = 0
        for s in range(1, f + 1):
            bounce = directions[s - 1]
            if bounce == "↘":
                offset += 1
            y_ball = y0 + (s - 0.5) * dy
            x_ball = cx + (offset - s / 2) * dx
            path_coords.append((x_ball, y_ball))
            
        if len(path_coords) > 1:
            draw.line(path_coords, fill=(246, 196, 69, 150), width=2)
            for px, py in path_coords[1:-1]:
                draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(246, 196, 69, 255))
                
        bx, by = path_coords[-1]
        draw.ellipse([bx - 7, by - 7, bx + 7, by + 7], fill=(239, 68, 68, 100))
        draw.ellipse([bx - 5, by - 5, bx + 5, by + 5], fill=(239, 68, 68, 255))
        draw.ellipse([bx - 2, by - 4, bx, by - 2], fill=(255, 255, 255, 200))
        
        frames.append(img)
        
    out = BytesIO()
    durations = [400] * N + [6000]
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0
    )
    out.seek(0)
    
    # Close resources
    for frame in frames:
        frame.close()
        
    return out


class PlinkoLobbyView(discord.ui.View):
    def __init__(self, cog: "Plinko", user_id: int):
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
        stats = self.cog.economy.get_plinko_stats(self.user_id)
        plays = stats["plays"]
        wins = stats["wins"]
        losses = stats["losses"]
        profit = stats["profit"]
        streak = stats["streak"]
        max_streak = stats["max_streak"]
        jackpots = stats["jackpots"]
        max_mult = stats["max_multiplier"]
        achievements_list = stats["achievements"]
        
        win_rate = (wins / plays * 100) if plays > 0 else 0.0
        profit_sign = "+" if profit >= 0 else ""
        
        desc = (
            f"🔴 **Số ván đã chơi:** `{plays}`\n"
            f"🏆 **Số ván thắng (>=1x):** `{wins}`\n"
            f"❌ **Số ván thua (<1x):** `{losses}`\n"
            f"📈 **Tỷ lệ thắng:** `{win_rate:.1f}%`\n"
            f"💥 **Số lần Jackpot (100x):** `{jackpots}`\n"
            f"🔝 **Hệ số cao nhất:** `{max_mult:.1f}x`\n"
            f"🔥 **Chuỗi thắng dài nhất:** `{max_streak}`\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{streak}`\n"
            f"💸 **Tổng lợi nhuận:** `{profit_sign}{profit:,} VNĐ`\n"
        )
        embed = make_embed(
            title=f"📊 THỐNG KÊ PLINKO - {interaction.user.name.upper()}",
            description=desc,
            color=discord.Color.purple()
        )
        if achievements_list:
            ach_texts = "\n".join([f"✨ {PLINKO_ACHIEVEMENTS[a]}" for a in achievements_list if a in PLINKO_ACHIEVEMENTS])
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value=ach_texts, inline=False)
        else:
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value="*Chưa mở khóa thành tựu nào*", inline=False)
            
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @discord.ui.button(label="🏆 Xếp hạng", style=discord.ButtonStyle.secondary, emoji="🏆")
    async def rank_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.economy.cur.execute(
            "SELECT user_id, profit, max_multiplier, plays FROM user_plinko ORDER BY profit DESC LIMIT 10"
        )
        rows = self.cog.economy.cur.fetchall()
        if not rows:
            await interaction.response.send_message("ℹ️ Chưa có ai xếp hạng Plinko.", ephemeral=True)
            return
        desc = ""
        for i, row in enumerate(rows, 1):
            u_id, profit, max_mult, plays = row
            member = interaction.guild.get_member(u_id)
            name = member.name if member else f"ID: {u_id}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            profit_sign = "+" if profit >= 0 else ""
            desc += f"{medal} **{name}** • Lợi nhuận: `{profit_sign}{profit:,} VNĐ` • Max Mult: `{max_mult:.1f}x` *(Lượt chơi: {plays})*\n"
        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG CAO THỦ PLINKO",
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


class Plinko(commands.Cog, name="Plinko"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.active_users = set()

    @commands.group(
        name="drops",
        aliases=["plinko"],
        brief="Trò chơi thả bóng Plinko kịch tính.",
        usage="drops [tiền cược] [risk]",
        invoke_without_command=True
    )
    async def plinko_cmd(self, ctx: commands.Context, bet_amount_str: str = None, risk: str = "medium"):
        user_id = ctx.author.id

        # Show lobby if no bet specified
        if bet_amount_str is None:
            view = PlinkoLobbyView(self, user_id)
            embed = make_embed(
                title="💎 SẢNH CHỜ PLINKO",
                description=(
                    "Trò chơi Plinko mô phỏng thả bóng từ trên xuống, bóng nảy qua các chốt và rơi vào các ô hệ số nhân ngẫu nhiên tùy thuộc vào mức rủi ro (Risk).\n\n"
                    "👉 **Cú pháp chơi:** `i?drops <tiền cược> [low/medium/high]`\n"
                    "👉 **Ví dụ:** `i?drops 100k high` hoặc `i?plinko 10k` (mặc định là medium)\n\n"
                    "**BẢNG THƯỞNG & TỶ LỆ:**\n"
                    "🟢 **Low Risk:** Thường rơi giữa, ít lời ít lỗ.\n"
                    "Hệ số: `0.8x`, `1.0x`, `1.2x`, `1.5x`\n\n"
                    "🟡 **Medium Risk:** Cân bằng, ổn định.\n"
                    "Hệ số: `0.2x`, `0.5x`, `1.0x`, `2.0x`, `5.0x`\n\n"
                    "🔴 **High Risk:** Dễ mất trắng, Jackpot khủng!\n"
                    "Hệ số: `0x`, `0.2x`, `0.5x`, `1.0x`, `3.0x`, `5.0x`, `10.0x`, `25.0x`, `100.0x`\n\n"
                    "Chọn một nút bấm dưới đây để xem chỉ số của bạn hoặc bảng xếp hạng:"
                ),
                color=discord.Color.purple()
            )
            embed.set_footer(text="🎰 Casino Bot • Plinko Drops")
            view.message = await ctx.send(embed=embed, view=view)
            return

        if user_id in self.active_users:
            await ctx.send("❌ **Lỗi:** Bạn đang có một ván Plinko đang chạy. Vui lòng đợi ván chơi hoàn thành!")
            return

        # Parse and validate risk
        risk = risk.strip().lower()
        if risk not in RISK_SETTINGS:
            risk = "medium"

        current_money = self.economy.get_entry(user_id)[1]
        bet_amount = parse_bet_amount(bet_amount_str, current_money)

        if bet_amount < 1000:
            await ctx.send("❌ Tiền cược tối thiểu là 1,000 VNĐ.")
            return

        try:
            validate_money_bet(self.economy, user_id, bet_amount)
            self.economy.add_money(user_id, -bet_amount)
            log_wallet_change(logger, event="plinko_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
        except Exception as e:
            await ctx.send(f"❌ {e}")
            return

        # Register user as active
        self.active_users.add(user_id)

        # Show initial loading feedback
        loading_msg = await ctx.send("🎰 **Plinko:** Đang chuẩn bị thả bóng...")

        try:
            # Draw result based on risk weights
            cfg = RISK_SETTINGS[risk]
            multiplier = random.choices(cfg["multipliers"], weights=cfg["weights"])[0]

            # Map multiplier to layout index for mapping trajectory
            layout = BIN_LAYOUTS[risk]
            matching_indices = [i for i, v in enumerate(layout) if abs(v - multiplier) < 1e-5]
            target_index = random.choice(matching_indices)

            # Generate random bounces path
            N = len(layout) - 1
            k = target_index
            choices = [1] * k + [-1] * (N - k)
            random.shuffle(choices)
            directions = ["↘" if c == 1 else "↙" for c in choices]

            # Calculate payout & net profit
            payout = int(bet_amount * multiplier)
            profit_delta = payout - bet_amount

            # Database Updates
            stats = self.economy.get_plinko_stats(user_id)
            old_streak = stats.get("streak", 0)
            old_max_streak = stats.get("max_streak", 0)
            
            # Update streaks
            is_win = (multiplier >= 1.0)
            new_streak = (old_streak + 1) if is_win else 0
            
            self.economy.update_plinko_stats(
                user_id,
                plays=1,
                wins=1 if is_win else 0,
                losses=1 if not is_win else 0,
                profit=profit_delta,
                jackpots=1 if multiplier == 100.0 else 0,
                max_multiplier=multiplier,
                streak=new_streak,
                max_streak=max(old_max_streak, new_streak)
            )

            # Give payout
            if payout > 0:
                self.economy.add_money(user_id, payout)
                log_wallet_change(logger, event="plinko_payout", user_id=user_id, money_delta=payout, ctx=ctx)

            # Check and update achievements
            updated_stats = self.economy.get_plinko_stats(user_id)
            newly_unlocked = check_and_unlock_plinko_achievements(updated_stats, multiplier, updated_stats["profit"])
            if newly_unlocked:
                updated_stats["achievements"].extend(newly_unlocked)
                self.economy.update_plinko_stats(user_id, achievements=updated_stats["achievements"])

            # Render Animated GIF
            timestamp_str = datetime.now().strftime("%d/%m/%Y · %H:%M:%S")
            
            # We wrap the CPU-bound PIL rendering in an executor to avoid blocking the asyncio event loop!
            loop = asyncio.get_event_loop()
            gif_buf = await loop.run_in_executor(
                None,
                render_plinko_gif,
                risk,
                multiplier,
                target_index,
                directions
            )

            # Send result
            file = discord.File(gif_buf, filename="plinko.gif")
            
            embed = make_embed(
                title="💎 TRÒ CHƠI PLINKO",
                color=discord.Color.purple()
            )
            
            # Determine profit sign and details representation
            profit_sign = "+" if profit_delta > 0 else "-" if profit_delta < 0 else "±"
            profit_display = f"{profit_sign}{abs(profit_delta):,} VNĐ" if profit_delta != 0 else "±0 VNĐ"
            
            desc = (
                f"👤 **Người chơi:** {ctx.author.mention}\n"
                f"💵 **Tiền cược:** `{bet_amount:,} VNĐ`\n"
                f"⚡ **Mức rủi ro:** `{risk.upper()}`\n\n"
                f"🎯 **Nhận hệ số:** `{multiplier}x`\n"
                f"💰 **Nhận về:** `{payout:,} VNĐ`\n"
                f"📈 **Lợi nhuận:** `{profit_display}`\n"
            )
            embed.description = desc
            
            if newly_unlocked:
                achievement_texts = "\n".join([f"✨ **{PLINKO_ACHIEVEMENTS[a]}**" for a in newly_unlocked])
                embed.add_field(name="🏆 THÀNH TỰU MỚI!", value=achievement_texts, inline=False)
                
            embed.set_image(url="attachment://plinko.gif")
            embed.set_footer(text=f"Sylus Meow · {timestamp_str}")
            
            await ctx.send(embed=embed, file=file)

            # Clean up loading message
            try:
                await loading_msg.delete()
            except Exception:
                pass

            # If jackpot, send special announcement message
            if multiplier == 100.0:
                try:
                    await ctx.send(
                        f"💥 **JACKPOT!!** 💥\n"
                        f"Chúc mừng **{ctx.author.name}** vừa trúng **100x** từ Plinko! 🎉\n"
                        f"Cược: **{bet_amount:,} VNĐ** ➡️ Nhận: **{payout:,} VNĐ**! 🔥🔥🔥"
                    )
                except Exception:
                    pass

        except Exception as e:
            logger.error(f"Error executing Plinko: {e}", exc_info=True)
            await ctx.send("❌ Đã xảy ra lỗi hệ thống khi xử lý lượt chơi Plinko.")
        finally:
            # Always ensure player is unregistered from active
            self.active_users.discard(user_id)

    @plinko_cmd.command(name="stats", brief="Xem thống kê chơi Plinko.")
    async def stats_sub(self, ctx: commands.Context, member: discord.Member = None):
        target_user = member or ctx.author
        stats = self.economy.get_plinko_stats(target_user.id)
        plays = stats["plays"]
        wins = stats["wins"]
        losses = stats["losses"]
        profit = stats["profit"]
        streak = stats["streak"]
        max_streak = stats["max_streak"]
        jackpots = stats["jackpots"]
        max_mult = stats["max_multiplier"]
        achievements_list = stats["achievements"]
        
        win_rate = (wins / plays * 100) if plays > 0 else 0.0
        profit_sign = "+" if profit >= 0 else ""
        
        desc = (
            f"🔴 **Số ván đã chơi:** `{plays}`\n"
            f"🏆 **Số ván thắng (>=1x):** `{wins}`\n"
            f"❌ **Số ván thua (<1x):** `{losses}`\n"
            f"📈 **Tỷ lệ thắng:** `{win_rate:.1f}%`\n"
            f"💥 **Số lần Jackpot (100x):** `{jackpots}`\n"
            f"🔝 **Hệ số cao nhất:** `{max_mult:.1f}x`\n"
            f"🔥 **Chuỗi thắng dài nhất:** `{max_streak}`\n"
            f"🔥 **Chuỗi thắng hiện tại:** `{streak}`\n"
            f"💸 **Tổng lợi nhuận:** `{profit_sign}{profit:,} VNĐ`\n"
        )
        embed = make_embed(
            title=f"📊 THỐNG KÊ PLINKO - {target_user.name.upper()}",
            description=desc,
            color=discord.Color.purple()
        )
        if achievements_list:
            ach_texts = "\n".join([f"✨ {PLINKO_ACHIEVEMENTS[a]}" for a in achievements_list if a in PLINKO_ACHIEVEMENTS])
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value=ach_texts, inline=False)
        else:
            embed.add_field(name="🏆 THÀNH TỰU ĐÃ ĐẠT", value="*Chưa mở khóa thành tựu nào*", inline=False)
            
        await ctx.send(embed=embed)

    @plinko_cmd.command(name="rank", aliases=["leaderboard", "bxh"], brief="Xem bảng xếp hạng cao thủ Plinko.")
    async def rank_sub(self, ctx: commands.Context):
        self.economy.cur.execute(
            "SELECT user_id, profit, max_multiplier, plays FROM user_plinko ORDER BY profit DESC LIMIT 10"
        )
        rows = self.economy.cur.fetchall()
        if not rows:
            await ctx.send("ℹ️ Chưa có ai xếp hạng Plinko.")
            return
        desc = ""
        for i, row in enumerate(rows, 1):
            u_id, profit, max_mult, plays = row
            member = ctx.guild.get_member(u_id)
            name = member.name if member else f"ID: {u_id}"
            medal = "🥇" if i == 1 else "🥈" if i == 2 else "🥉" if i == 3 else f"**{i}.**"
            profit_sign = "+" if profit >= 0 else ""
            desc += f"{medal} **{name}** • Lợi nhuận: `{profit_sign}{profit:,} VNĐ` • Max Mult: `{max_mult:.1f}x` *(Lượt chơi: {plays})*\n"
        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG CAO THỦ PLINKO",
            description=desc,
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)


async def setup(bot: commands.Bot):
    await bot.add_cog(Plinko(bot))
