import asyncio
import io
import math
import logging
import random
from datetime import datetime
from io import BytesIO
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from pathlib import Path

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, InsufficientFundsException
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.profile_renderer import load_font

logger = logging.getLogger(__name__)
REPO_ROOT = Path(__file__).resolve().parents[3]

MASCOT_MAPPING = {
    "ca": "🐟 Cá",
    "cua": "🦀 Cua",
    "tom": "🦐 Tôm",
    "nai": "🦌 Nai",
    "bau": "🍐 Bầu",
    "ga": "🐓 Gà",
    "🐟": "🐟 Cá",
    "🦀": "🦀 Cua",
    "🦐": "🦐 Tôm",
    "🦌": "🦌 Nai",
    "🍐": "🍐 Bầu",
    "🐓": "🐓 Gà",
}


def parse_bet_amount(val_str: str, current_money: int) -> int:
    val_str = val_str.strip().lower()
    if val_str in ["all", "allin", "all-in", "tất tay"]:
        from app.discord_bot.modules.betting import get_capped_all_in_amount
        return get_capped_all_in_amount(current_money)
    
    # Remove separators like commas or dots
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


def draw_dice_face(value: int, size: int = 60) -> Image.Image:
    # Create a blank white square with transparent background
    dice_img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(dice_img)
    
    # Base card color
    draw.rounded_rectangle(
        [(0, 0), (size - 1, size - 1)],
        radius=int(size * 0.2),
        fill="#ffffff",
        outline="#dddddd",
        width=1
    )
    
    # Pips color: Red for 1 and 4, black/grey for others
    pip_color = "#e63946" if value in [1, 4] else "#2b2d31"
    
    # Calculate pip positions based on size
    r = int(size * 0.08) # Radius of dot
    
    center = (size / 2, size / 2)
    top_left = (size * 0.28, size * 0.28)
    top_right = (size * 0.72, size * 0.28)
    bottom_left = (size * 0.28, size * 0.72)
    bottom_right = (size * 0.72, size * 0.72)
    mid_left = (size * 0.28, size * 0.5)
    mid_right = (size * 0.72, size * 0.5)
    
    pips = {
        1: [center],
        2: [top_left, bottom_right],
        3: [top_left, center, bottom_right],
        4: [top_left, top_right, bottom_left, bottom_right],
        5: [top_left, top_right, center, bottom_left, bottom_right],
        6: [top_left, top_right, mid_left, mid_right, bottom_left, bottom_right]
    }
    
    if value == 1:
        r = int(size * 0.14)
        
    for pos in pips[value]:
        x, y = pos
        draw.ellipse([(x - r, y - r), (x + r, y + r)], fill=pip_color)
        
    return dice_img


def generate_taixiu_image(seconds_remaining: int, tai_bets: dict, xiu_bets: dict, result_text: str = None, dice: list[int] = None) -> io.BytesIO:
    base_img_path = REPO_ROOT / "pictures" / "taixiu_bg.png"
    if not base_img_path.exists():
        base_img_path = "pictures/taixiu_bg.png"
    img = Image.open(base_img_path).convert("RGBA")
    # Crop to frame (924x570)
    cropped = img.crop((50, 200, 974, 770))
    draw = ImageDraw.Draw(cropped)
    
    # Load fonts
    font_large = load_font("bold", 100)
    font_medium = load_font("bold", 36)
    font_small = load_font("bold", 24)
    
    # Draw Left bet amount below "TÀI"
    tai_total = sum(tai_bets.values())
    draw.text((170, 415), f"{tai_total:,} VND", fill="#ffcc00", font=font_small, anchor="mm")
    
    # Draw Right bet amount below "XỈU"
    xiu_total = sum(xiu_bets.values())
    draw.text((754, 415), f"{xiu_total:,} VND", fill="#ffcc00", font=font_small, anchor="mm")
    
    # Draw Center Circle
    if dice:
        dice_size = 65
        spacing = 15
        total_width = 3 * dice_size + 2 * spacing
        start_x = int(462 - total_width / 2)
        start_y = 210
        
        for i, val in enumerate(dice):
            dice_img = draw_dice_face(val, size=dice_size)
            x_pos = start_x + i * (dice_size + spacing)
            cropped.paste(dice_img, (x_pos, start_y), dice_img)
            
        if result_text:
            draw.text((462, 335), result_text, fill="#ffd700", font=font_medium, anchor="mm")
    elif result_text:
        # Show single text (e.g. "LẮC")
        draw.text((462, 285), result_text, fill="#ffd700", font=font_large, anchor="mm")
    else:
        # Show countdown timer
        timer_text = str(seconds_remaining)
        draw.text((462, 285), timer_text, fill="#ffffff", font=font_large, anchor="mm")
        
    # Save to BytesIO
    output = io.BytesIO()
    cropped.save(output, format="PNG")
    output.seek(0)
    return output


def format_money_shorthand(amount: int) -> str:
    if amount == 0:
        return "0"
    if amount >= 1_000_000:
        val = amount / 1_000_000
        if val == int(val):
            return f"{int(val)}M"
        return f"{val:.1f}M"
    if amount >= 1_000:
        val = amount / 1_000
        if val == int(val):
            return f"{int(val)}K"
        return f"{val:.1f}K"
    return f"{amount}"


def draw_bet_box(draw: ImageDraw.Draw, x: int, y: int, amount: int, font: ImageFont.FreeTypeFont):
    # Box dimensions
    w, h = 120, 34
    x1, y1 = x - w // 2, y - h // 2
    x2, y2 = x + w // 2, y + h // 2
    
    # Draw dark background box
    draw.rounded_rectangle(
        [(x1, y1), (x2, y2)],
        radius=6,
        fill="#0d0e15",
        outline="#ffcc00",
        width=2
    )
    
    # Draw shorthand text inside the box
    text = format_money_shorthand(amount)
    draw.text((x, y), text, fill="#ffcc00", font=font, anchor="mm")


def generate_baucua_image(seconds_remaining: int, bets: dict, result_text: str = None, dice_results: list[str] = None) -> io.BytesIO:
    base_img_path = REPO_ROOT / "pictures" / "baucua_bg.png"
    if not base_img_path.exists():
        base_img_path = "pictures/baucua_bg.png"
    img = Image.open(base_img_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    # Load fonts
    font_large = load_font("bold", 60)
    font_medium = load_font("bold", 32)
    font_small = load_font("bold", 18)
    
    # Sum bets for each mascot
    nai_total = sum(bets.get("nai", {}).values())
    bau_total = sum(bets.get("bau", {}).values())
    ga_total = sum(bets.get("ga", {}).values())
    ca_total = sum(bets.get("ca", {}).values())
    cua_total = sum(bets.get("cua", {}).values())
    tom_total = sum(bets.get("tom", {}).values())
    
    # Draw bet boxes
    draw_bet_box(draw, 256, 290, nai_total, font_small)
    draw_bet_box(draw, 512, 290, bau_total, font_small)
    draw_bet_box(draw, 768, 290, ga_total, font_small)
    
    draw_bet_box(draw, 256, 580, ca_total, font_small)
    draw_bet_box(draw, 512, 580, cua_total, font_small)
    draw_bet_box(draw, 768, 580, tom_total, font_small)
    
    # Draw Center Display Box (centered at x=512, y=150)
    box_w, box_h = 320, 54
    bx1, by1 = 512 - box_w // 2, 150 - box_h // 2
    bx2, by2 = 512 + box_w // 2, 150 + box_h // 2
    
    draw.rounded_rectangle(
        [(bx1, by1), (bx2, by2)],
        radius=8,
        fill="#0d0e15",
        outline="#ffcc00",
        width=2
    )
    
    if dice_results:
        draw.text((512, 150), result_text, fill="#ffd700", font=font_medium, anchor="mm")
    elif result_text:
        draw.text((512, 150), result_text, fill="#ffd700", font=font_medium, anchor="mm")
    else:
        draw.text((512, 150), str(seconds_remaining), fill="#ffffff", font=font_large, anchor="mm")
        
    # Save to BytesIO
    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output


def calculate_taixiu_payout(dice: list[int], view, tax_rate: float = 0.0) -> int:
    total = sum(dice)
    if 3 <= total <= 10:
        winning_side = "xiu"
    else:
        winning_side = "tai"
        
    payout_before_tax = 0
    total_winning_bets = 0
    
    # Tai bets
    if winning_side == "tai":
        payout_before_tax += 2 * sum(view.tai_bets.values())
        total_winning_bets += sum(view.tai_bets.values())
        
    # Xiu bets
    if winning_side == "xiu":
        payout_before_tax += 2 * sum(view.xiu_bets.values())
        total_winning_bets += sum(view.xiu_bets.values())
        
    # Chan bets
    if total % 2 == 0:
        payout_before_tax += 2 * sum(view.chan_bets.values())
        total_winning_bets += sum(view.chan_bets.values())
        
    # Le bets
    if total % 2 != 0:
        payout_before_tax += 2 * sum(view.le_bets.values())
        total_winning_bets += sum(view.le_bets.values())
        
    # Number bets
    for n in range(1, 7):
        matches = dice.count(n)
        if matches > 0:
            payout_before_tax += (matches + 1) * sum(view.number_bets[n].values())
            total_winning_bets += sum(view.number_bets[n].values())
            
    net_win = payout_before_tax - total_winning_bets
    tax = 0
    if net_win > 0:
        tax = int(net_win * tax_rate)
        
    payout = payout_before_tax - tax
    return payout


class TaiXiuBetModal(discord.ui.Modal):
    def __init__(self, side: str, lobby_view):
        super().__init__(title=f"Đặt cược vào cửa {side.upper()}")
        self.side = side
        self.lobby_view = lobby_view
        
        self.bet_input = discord.ui.TextInput(
            label="Số tiền muốn cược",
            placeholder="Ví dụ: 10k, 500k, 5m, all",
            required=True,
            max_length=20
        )
        self.add_item(self.bet_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.lobby_view.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc! Bạn không thể đặt cược nữa.", ephemeral=True)
            return

        user = interaction.user
        val_str = self.bet_input.value
        
        if self.side == "tai" and user.id in self.lobby_view.xiu_bets:
            await interaction.response.send_message("❌ Bạn đã đặt cược ở cửa **XỈU** rồi! Bạn không thể đặt cược hai bên.", ephemeral=True)
            return
        if self.side == "xiu" and user.id in self.lobby_view.tai_bets:
            await interaction.response.send_message("❌ Bạn đã đặt cược ở cửa **TÀI** rồi! Bạn không thể đặt cược hai bên.", ephemeral=True)
            return
        if self.side == "chan" and user.id in self.lobby_view.le_bets:
            await interaction.response.send_message("❌ Bạn đã đặt cược ở cửa **LẺ** rồi! Bạn không thể đặt cược cả Chẵn và Lẻ.", ephemeral=True)
            return
        if self.side == "le" and user.id in self.lobby_view.chan_bets:
            await interaction.response.send_message("❌ Bạn đã đặt cược ở cửa **CHẴN** rồi! Bạn không thể đặt cược cả Chẵn và Lẻ.", ephemeral=True)
            return

        profile = self.lobby_view.cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.response.send_message("❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).", ephemeral=True)
            return
            
        if amount < 1000:
            await interaction.response.send_message("❌ Số tiền cược tối thiểu là **1,000 VND**.", ephemeral=True)
            return

        if amount > current_money:
            await interaction.response.send_message(f"❌ Bạn không đủ tiền! Số dư hiện tại của bạn là **{current_money:,} VND**.", ephemeral=True)
            return

        # Get configured max bet
        max_bet_str = self.lobby_view.cog.economy.get_setting("taixiu_max_bet")
        max_bet = int(max_bet_str) if max_bet_str is not None else 10000000  # Default 10M VND
        
        # Calculate what their new total bet for this door would be
        current_bet = 0
        if self.side == "tai":
            current_bet = self.lobby_view.tai_bets.get(user.id, 0)
        elif self.side == "xiu":
            current_bet = self.lobby_view.xiu_bets.get(user.id, 0)
        elif self.side == "chan":
            current_bet = self.lobby_view.chan_bets.get(user.id, 0)
        elif self.side == "le":
            current_bet = self.lobby_view.le_bets.get(user.id, 0)
        elif self.side.isdigit():
            num = int(self.side)
            current_bet = self.lobby_view.number_bets[num].get(user.id, 0)
            
        if current_bet + amount > max_bet:
            await interaction.response.send_message(f"❌ **Lỗi:** Giới hạn cược tối đa mỗi cửa là **{max_bet:,} VND**. Bạn đã cược `{current_bet:,} VND` ở cửa này trước đó, và muốn cược thêm `{amount:,} VND`.", ephemeral=True)
            return

        # Deduct balance immediately to prevent exploits
        self.lobby_view.cog.economy.add_money(user.id, -amount)
        
        if self.side == "tai":
            self.lobby_view.tai_bets[user.id] = self.lobby_view.tai_bets.get(user.id, 0) + amount
        elif self.side == "xiu":
            self.lobby_view.xiu_bets[user.id] = self.lobby_view.xiu_bets.get(user.id, 0) + amount
        elif self.side == "chan":
            self.lobby_view.chan_bets[user.id] = self.lobby_view.chan_bets.get(user.id, 0) + amount
        elif self.side == "le":
            self.lobby_view.le_bets[user.id] = self.lobby_view.le_bets.get(user.id, 0) + amount
        elif self.side.isdigit():
            num = int(self.side)
            self.lobby_view.number_bets[num][user.id] = self.lobby_view.number_bets[num].get(user.id, 0) + amount
            
        self.lobby_view.user_names[user.id] = user.display_name
        
        log_wallet_change(
            logger,
            event="taixiu_place_bet",
            user_id=user.id,
            money_delta=-amount,
            side=self.side,
            bet_amount=amount,
        )

        await interaction.response.send_message(f"✅ Đã đặt cược **{amount:,} VND** vào cửa **{self.side.upper()}** thành công!", ephemeral=True)
        await self.lobby_view.update_message()


class TaiXiuNumberSelect(discord.ui.Select):
    def __init__(self):
        options = [
            discord.SelectOption(label="Cược số 1 🎲", value="1"),
            discord.SelectOption(label="Cược số 2 🎲", value="2"),
            discord.SelectOption(label="Cược số 3 🎲", value="3"),
            discord.SelectOption(label="Cược số 4 🎲", value="4"),
            discord.SelectOption(label="Cược số 5 🎲", value="5"),
            discord.SelectOption(label="Cược số 6 🎲", value="6"),
        ]
        super().__init__(placeholder="Chọn số xúc xắc muốn cược...", min_values=1, max_values=1, options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        view: TaiXiuLobbyView = self.view
        if view.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        modal = TaiXiuBetModal(side=self.values[0], lobby_view=view)
        await interaction.response.send_modal(modal)


class TaiXiuLobbyView(discord.ui.View):
    def __init__(self, cog, session_id: int, timeout: float = 40.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session_id = session_id
        self.tai_bets = {}
        self.xiu_bets = {}
        self.chan_bets = {}
        self.le_bets = {}
        self.number_bets = {1: {}, 2: {}, 3: {}, 4: {}, 5: {}, 6: {}}
        self.user_names = {}
        self.is_closed = False
        self.message = None
        self.seconds_remaining = 30
        self.add_item(TaiXiuNumberSelect())

    async def update_message(self):
        if self.message:
            embed = self.create_embed()
            img_bytes = generate_taixiu_image(
                self.seconds_remaining,
                self.tai_bets,
                self.xiu_bets
            )
            file = discord.File(img_bytes, filename="taixiu.png")
            try:
                await self.message.edit(embed=embed, attachments=[file], view=self)
            except discord.HTTPException:
                pass

    def create_embed(self) -> discord.Embed:
        tai_total = sum(self.tai_bets.values())
        xiu_total = sum(self.xiu_bets.values())
        chan_total = sum(self.chan_bets.values())
        le_total = sum(self.le_bets.values())
        
        tai_list = []
        for uid, amt in self.tai_bets.items():
            name = self.user_names.get(uid, f"User {uid}")
            tai_list.append(f"• **{name}**: `{amt:,} VND`")
            
        xiu_list = []
        for uid, amt in self.xiu_bets.items():
            name = self.user_names.get(uid, f"User {uid}")
            xiu_list.append(f"• **{name}**: `{amt:,} VND`")

        chan_list = []
        for uid, amt in self.chan_bets.items():
            name = self.user_names.get(uid, f"User {uid}")
            chan_list.append(f"• **{name}**: `{amt:,} VND`")

        le_list = []
        for uid, amt in self.le_bets.items():
            name = self.user_names.get(uid, f"User {uid}")
            le_list.append(f"• **{name}**: `{amt:,} VND`")
            
        tai_list_str = "\n".join(tai_list) if tai_list else "*Chưa có*"
        xiu_list_str = "\n".join(xiu_list) if xiu_list else "*Chưa có*"
        chan_list_str = "\n".join(chan_list) if chan_list else "*Chưa có*"
        le_list_str = "\n".join(le_list) if le_list else "*Chưa có*"
        
        currency = "<a:emoji_287:1514350238687821845>"

        jackpot_str = self.cog.economy.get_setting("taixiu_jackpot")
        jackpot_val = int(jackpot_str) if jackpot_str else 0
        
        min_bet_str = self.cog.economy.get_setting("taixiu_jackpot_min_bet")
        jackpot_min_bet = int(min_bet_str) if min_bet_str else 50000
        
        embed = make_embed(
            title=f"🎲 PHIÊN TÀI XỈU #{self.session_id} 🎲",
            description=(
                f"🎰 **HŨ JACKPOT TÀI XỈU:** `{jackpot_val:,} VND` 🎰\n"
                f"🔥 *Nổ Hũ khi ra Bão 1 (1-1-1) hoặc Bão 6 (6-6-6). Chỉ chia cho người thắng cửa Xỉu (nếu ra 1-1-1) hoặc cửa Tài (nếu ra 6-6-6) với mức cược tối thiểu từ {jackpot_min_bet:,} VND!*\n\n"
                f"⏳ **Thời gian đặt cược còn lại:** `{self.seconds_remaining} giây`\n\n"
                f"👉 Nhấp vào nút/chọn menu bên dưới để chọn cửa cược."
            ),
            color=discord.Color.dark_theme()
        )
        
        embed.add_field(
            name="🔵 TÀI (11-18)",
            value=f"👥 Tổng: **{tai_total:,}** {currency}\n{tai_list_str}",
            inline=True
        )
        embed.add_field(
            name="🔴 XỈU (3-10)",
            value=f"👥 Tổng: **{xiu_total:,}** {currency}\n{xiu_list_str}",
            inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        embed.add_field(
            name="🟣 CHẴN",
            value=f"👥 Tổng: **{chan_total:,}** {currency}\n{chan_list_str}",
            inline=True
        )
        embed.add_field(
            name="🟡 LẺ",
            value=f"👥 Tổng: **{le_total:,}** {currency}\n{le_list_str}",
            inline=True
        )
        embed.add_field(name="\u200b", value="\u200b", inline=True)

        # Specific numbers summary
        num_totals = {n: sum(self.number_bets[n].values()) for n in range(1, 7)}
        num_lines = []
        for n in range(1, 7):
            tot = num_totals[n]
            if tot > 0:
                users = []
                for uid, amt in self.number_bets[n].items():
                    name = self.user_names.get(uid, f"User {uid}")
                    users.append(f"**{name}** (`{amt:,}`)")
                num_lines.append(f"🎲 **Số {n}**: Tổng `{tot:,}` VND ({', '.join(users)})")

        num_str = "\n".join(num_lines) if num_lines else "*Chưa có*"
        embed.add_field(
            name="🎲 CƯỢC SỐ XÚC XẮC CỤ THỂ",
            value=num_str,
            inline=False
        )
        
        embed.set_image(url="attachment://taixiu.png")
        return embed

    @discord.ui.button(label="TÀI", style=discord.ButtonStyle.primary, emoji="🔵", row=0)
    async def bet_tai(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        modal = TaiXiuBetModal(side="tai", lobby_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="XỈU", style=discord.ButtonStyle.danger, emoji="🔴", row=0)
    async def bet_xiu(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        modal = TaiXiuBetModal(side="xiu", lobby_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="CHẴN", style=discord.ButtonStyle.primary, emoji="🟣", row=0)
    async def bet_chan(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        modal = TaiXiuBetModal(side="chan", lobby_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="LẺ", style=discord.ButtonStyle.danger, emoji="🟡", row=0)
    async def bet_le(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        modal = TaiXiuBetModal(side="le", lobby_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="HỦY CƯỢC", style=discord.ButtonStyle.secondary, emoji="❌", row=2)
    async def cancel_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc! Không thể hủy cược.", ephemeral=True)
            return
            
        user = interaction.user
        refund_amount = 0
        refund_details = []
        
        if user.id in self.tai_bets:
            amt = self.tai_bets.pop(user.id)
            refund_amount += amt
            refund_details.append(f"TAI: {amt:,} VND")
        if user.id in self.xiu_bets:
            amt = self.xiu_bets.pop(user.id)
            refund_amount += amt
            refund_details.append(f"XIU: {amt:,} VND")
        if user.id in self.chan_bets:
            amt = self.chan_bets.pop(user.id)
            refund_amount += amt
            refund_details.append(f"CHAN: {amt:,} VND")
        if user.id in self.le_bets:
            amt = self.le_bets.pop(user.id)
            refund_amount += amt
            refund_details.append(f"LE: {amt:,} VND")
            
        for n in range(1, 7):
            if user.id in self.number_bets[n]:
                amt = self.number_bets[n].pop(user.id)
                refund_amount += amt
                refund_details.append(f"SO_{n}: {amt:,} VND")
            
        if refund_amount > 0:
            self.cog.economy.add_money(user.id, refund_amount)
            
            log_wallet_change(
                logger,
                event="taixiu_cancel_bet",
                user_id=user.id,
                money_delta=refund_amount,
                refund_details="; ".join(refund_details),
                bet_amount=refund_amount,
            )
            await interaction.response.send_message(f"✅ Đã hủy cược thành công! Hoàn lại **{refund_amount:,} VND** vào ví.", ephemeral=True)
            await self.update_message()
        else:
            await interaction.response.send_message("❌ Bạn chưa đặt cược trong phiên này!", ephemeral=True)

    @discord.ui.button(label="LỊCH SỬ", style=discord.ButtonStyle.secondary, emoji="📜", row=2)
    async def view_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        history = self.cog.taixiu_history
        if not history:
            await interaction.response.send_message("📜 Chưa có lịch sử trận đấu nào trong phiên làm việc này.", ephemeral=True)
            return
            
        history_lines = []
        for idx, item in enumerate(reversed(history)):
            session_id, dice, total, result = item
            dice_emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
            dice_str = "".join(dice_emojis[d] for d in dice)
            history_lines.append(f"`#{idx+1}` 🔹 **Phiên #{session_id}**: {dice_str} (Tổng `{total}`) ➔ **{result}**")
            
        embed = discord.Embed(
            title="📜 LỊCH SỬ 10 TRẬN TÀI XỈU GẦN NHẤT 📜",
            description="\n".join(history_lines),
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class BauCuaBetModal(discord.ui.Modal):
    def __init__(self, mascot: str, lobby_view):
        vietnamese_name = {"nai": "NAI", "bau": "BẦU", "ga": "GÀ", "ca": "CÁ", "cua": "CUA", "tom": "TÔM"}
        super().__init__(title=f"Đặt cược vào con {vietnamese_name[mascot]}")
        self.mascot = mascot
        self.lobby_view = lobby_view
        
        self.bet_input = discord.ui.TextInput(
            label="Số tiền muốn cược",
            placeholder="Ví dụ: 10k, 500k, 5m, all",
            required=True,
            max_length=20
        )
        self.add_item(self.bet_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.lobby_view.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc! Bạn không thể đặt cược nữa.", ephemeral=True)
            return

        user = interaction.user
        val_str = self.bet_input.value
        
        profile = self.lobby_view.cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.response.send_message("❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).", ephemeral=True)
            return
            
        if amount < 1000:
            await interaction.response.send_message("❌ Số tiền cược tối thiểu là **1,000 VND**.", ephemeral=True)
            return

        if amount > current_money:
            await interaction.response.send_message(f"❌ Bạn không đủ tiền! Số dư hiện tại của bạn là **{current_money:,} VND**.", ephemeral=True)
            return

        # Deduct balance immediately
        self.lobby_view.cog.economy.add_money(user.id, -amount)
        
        self.lobby_view.bets[self.mascot][user.id] = self.lobby_view.bets[self.mascot].get(user.id, 0) + amount
        self.lobby_view.user_names[user.id] = user.display_name
        
        log_wallet_change(
            logger,
            event="baucua_place_bet",
            user_id=user.id,
            money_delta=-amount,
            mascot=self.mascot,
            bet_amount=amount,
        )

        vietnamese_name = {"nai": "NAI", "bau": "BẦU", "ga": "GÀ", "ca": "CÁ", "cua": "CUA", "tom": "TÔM"}
        await interaction.response.send_message(f"✅ Đã đặt cược **{amount:,} VND** vào con **{vietnamese_name[self.mascot]}** thành công!", ephemeral=True)
        await self.lobby_view.update_message()


class BauCuaLobbyView(discord.ui.View):
    def __init__(self, cog, session_id: int, timeout: float = 40.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session_id = session_id
        self.bets = {
            "nai": {},
            "bau": {},
            "ga": {},
            "ca": {},
            "cua": {},
            "tom": {}
        }
        self.user_names = {}
        self.is_closed = False
        self.message = None
        self.seconds_remaining = 30

    async def update_message(self):
        if self.message:
            embed = self.create_embed()
            img_bytes = generate_baucua_image(
                self.seconds_remaining,
                self.bets
            )
            file = discord.File(img_bytes, filename="baucua.png")
            try:
                await self.message.edit(embed=embed, attachments=[file], view=self)
            except discord.HTTPException:
                pass

    def create_embed(self) -> discord.Embed:
        totals = {m: sum(self.bets[m].values()) for m in self.bets}
        mascot_names_viet = {"nai": "🦌 NAI", "bau": "🍐 BẦU", "ga": "🐓 GÀ", "ca": "🐟 CÁ", "cua": "🦀 CUA", "tom": "🦐 TÔM"}
        
        jackpot_str = self.cog.economy.get_setting("baucua_jackpot")
        jackpot_val = int(jackpot_str) if jackpot_str else 0
        
        embed = make_embed(
            title=f"🦀 PHIÊN BẦU CUA #{self.session_id} 🦀",
            description=(
                f"🎰 **HŨ JACKPOT BẦU CUA:** `{jackpot_val:,} VND` 🎰\n"
                f"🔥 *Bão (3 linh vật giống nhau) nổ Hũ chia tỉ lệ cược của tất cả người chơi!*\n\n"
                f"⏳ **Thời gian đặt cược còn lại:** `{self.seconds_remaining} giây`\n\n"
                f"👉 Nhấp vào các nút bên dưới để chọn linh vật cược."
            ),
            color=discord.Color.dark_theme()
        )
        
        currency = "<a:emoji_287:1514350238687821845>"
        
        for mascot, label in mascot_names_viet.items():
            user_bets = []
            for uid, amt in self.bets[mascot].items():
                name = self.user_names.get(uid, f"User {uid}")
                user_bets.append(f"• **{name}**: `{amt:,} VND`")
            bets_str = "\n".join(user_bets) if user_bets else "*Chưa có*"
            embed.add_field(
                name=label,
                value=f"👥 Tổng: **{totals[mascot]:,}** {currency}\n{bets_str}",
                inline=True
            )
            
        embed.set_image(url="attachment://baucua.png")
        return embed

    @discord.ui.button(label="NAI", style=discord.ButtonStyle.secondary, emoji="🦌", row=0)
    async def bet_nai(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        await interaction.response.send_modal(BauCuaBetModal(mascot="nai", lobby_view=self))

    @discord.ui.button(label="BẦU", style=discord.ButtonStyle.secondary, emoji="🍐", row=0)
    async def bet_bau(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        await interaction.response.send_modal(BauCuaBetModal(mascot="bau", lobby_view=self))

    @discord.ui.button(label="GÀ", style=discord.ButtonStyle.secondary, emoji="🐓", row=0)
    async def bet_ga(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        await interaction.response.send_modal(BauCuaBetModal(mascot="ga", lobby_view=self))

    @discord.ui.button(label="CÁ", style=discord.ButtonStyle.secondary, emoji="🐟", row=1)
    async def bet_ca(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        await interaction.response.send_modal(BauCuaBetModal(mascot="ca", lobby_view=self))

    @discord.ui.button(label="CUA", style=discord.ButtonStyle.secondary, emoji="🦀", row=1)
    async def bet_cua(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        await interaction.response.send_modal(BauCuaBetModal(mascot="cua", lobby_view=self))

    @discord.ui.button(label="TÔM", style=discord.ButtonStyle.secondary, emoji="🦐", row=1)
    async def bet_tom(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        await interaction.response.send_modal(BauCuaBetModal(mascot="tom", lobby_view=self))

    @discord.ui.button(label="HỦY CƯỢC", style=discord.ButtonStyle.danger, emoji="❌", row=2)
    async def cancel_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc! Không thể hủy cược.", ephemeral=True)
            return
            
        user = interaction.user
        refund_amount = 0
        refund_details = []
        for mascot in list(self.bets.keys()):
            if user.id in self.bets[mascot]:
                amt = self.bets[mascot].pop(user.id)
                refund_amount += amt
                refund_details.append(f"{mascot.upper()}: {amt:,} VND")
                
        if refund_amount > 0:
            self.cog.economy.add_money(user.id, refund_amount)
            log_wallet_change(
                logger,
                event="baucua_cancel_bet",
                user_id=user.id,
                money_delta=refund_amount,
                refund_amount=refund_amount,
                refund_details="; ".join(refund_details)
            )
            await interaction.response.send_message(f"✅ Đã hủy cược thành công! Hoàn lại **{refund_amount:,} VND** vào ví.", ephemeral=True)
            await self.update_message()
        else:
            await interaction.response.send_message("❌ Bạn chưa đặt cược trong phiên này!", ephemeral=True)

    @discord.ui.button(label="LỊCH SỬ", style=discord.ButtonStyle.secondary, emoji="📜", row=2)
    async def view_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        history = self.cog.baucua_history
        if not history:
            await interaction.response.send_message("📜 Chưa có lịch sử trận đấu nào trong phiên làm việc này.", ephemeral=True)
            return
            
        history_lines = []
        mascot_emojis = {"ca": "🐟", "cua": "🦀", "tom": "🦐", "nai": "🦌", "bau": "🍐", "ga": "🐓"}
        for idx, item in enumerate(reversed(history)):
            session_id, dice_results = item
            dice_str = " ".join(mascot_emojis.get(d, d) for d in dice_results)
            history_lines.append(f"`#{idx+1}` 🔹 **Phiên #{session_id}**: {dice_str}")
            
        embed = discord.Embed(
            title="📜 LỊCH SỬ 10 TRẬN BẦU CUA GẦN NHẤT 📜",
            description="\n".join(history_lines),
            color=discord.Color.gold()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


# Colors configuration matching spec
WHEEL_CONFIG = {
    'blue':   { 'slots': 10, 'multiplier': 2,  'emoji': '🔵', 'label': 'Xanh dương' },
    'green':  { 'slots': 9,  'multiplier': 3,  'emoji': '🟢', 'label': 'Xanh lá' },
    'yellow': { 'slots': 5,  'multiplier': 5,  'emoji': '🟡', 'label': 'Vàng' },
    'red':    { 'slots': 2,  'multiplier': 10, 'emoji': '🔴', 'label': 'Đỏ' },
    'grey':   { 'slots': 4,  'multiplier': 0,  'emoji': '⚫', 'label': 'Mất lượt' },
}

# The exact 30-slot layout
WHEEL_LAYOUT = [
  'blue', 'green', 'blue', 'green', 'grey', 'green', 'yellow', 'blue', 'yellow', 'blue',
  'yellow', 'grey', 'green', 'blue', 'green', 'yellow', 'blue', 'green', 'grey', 'green',
  'blue', 'green', 'blue', 'red', 'blue', 'grey', 'yellow', 'blue', 'green', 'red'
]

# Native Pillow Wheel Drawing
def render_wheel_gif(win_idx: int) -> tuple[BytesIO, BytesIO]:
    width = 300
    height = 300
    cx, cy = 150, 150
    radius = 120
    total_frames = 40  # 40 frames
    
    # Target index math
    target_offset = (360 - (win_idx * 12 + 6) % 360) % 360
    total_angle = 720 + target_offset
    
    font = load_font("bold", 11)
    
    frames = []
    
    for f in range(total_frames):
        # Easing out cubic
        progress = f / (total_frames - 1)
        eased_progress = 1 - math.pow(1 - progress, 3)
        current_rotation = total_angle * eased_progress
        
        # Create base image with bg color #1e1e2e
        img = Image.new("RGBA", (width, height), (30, 30, 46, 255))
        draw = ImageDraw.Draw(img)
        
        # Draw the slices
        for i in range(30):
            color_name = WHEEL_LAYOUT[i]
            
            rgb_colors = {
                'grey': {
                    'dark': (55, 60, 75, 255),
                    'light': (65, 70, 85, 255),
                    'label': 'x0',
                    'label_color': (140, 150, 160, 255)
                },
                'blue': {
                    'dark': (26, 58, 138, 255),
                    'light': (30, 61, 153, 255),
                    'label': 'x2',
                    'label_color': (91, 140, 255, 255)
                },
                'green': {
                    'dark': (13, 77, 32, 255),
                    'light': (15, 92, 38, 255),
                    'label': 'x3',
                    'label_color': (34, 197, 94, 255)
                },
                'yellow': {
                    'dark': (90, 63, 0, 255),
                    'light': (107, 76, 0, 255),
                    'label': 'x5',
                    'label_color': (234, 179, 8, 255)
                },
                'red': {
                    'dark': (122, 16, 16, 255),
                    'light': (138, 21, 21, 255),
                    'label': 'x10',
                    'label_color': (239, 68, 68, 255)
                }
            }
            
            cfg = rgb_colors[color_name]
            fill_color = cfg['dark'] if i % 2 == 0 else cfg['light']
            
            # Start/End angles in degrees
            start_deg = -90 + i * 12 + current_rotation
            end_deg = -90 + (i + 1) * 12 + current_rotation
            
            # Draw pieslice
            bbox = [cx - radius, cy - radius, cx + radius, cy + radius]
            draw.pieslice(bbox, start_deg, end_deg, fill=fill_color, outline=(30, 30, 46, 255), width=2)
            
            # Draw label text
            center_deg = start_deg + 6
            
            text_canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            text_draw = ImageDraw.Draw(text_canvas)
            
            text_x = cx + radius * 0.7
            text_y = cy
            
            text_draw.text((text_x, text_y), cfg['label'], font=font, fill=cfg['label_color'], anchor="mm")
            
            rotated_text = text_canvas.rotate(-center_deg, center=(cx, cy), resample=Image.Resampling.BICUBIC)
            
            img = Image.alpha_composite(img, rotated_text)
            draw = ImageDraw.Draw(img)
            
        # Draw outer border
        draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=(42, 42, 69, 255), width=3)
        
        # Draw central hub
        draw.ellipse([cx - 25, cy - 25, cx + 25, cy + 25], fill=(20, 20, 34, 255), outline=(42, 42, 69, 255), width=3)
        
        # Draw central dot
        draw.ellipse([cx - 4, cy - 4, cx + 4, cy + 4], fill=(200, 168, 75, 255))
        
        # Draw top indicator triangle
        draw.polygon([(cx, 32), (cx - 8, 18), (cx + 8, 18)], fill=(200, 168, 75, 255))
        
        frames.append(img)
        
    png_out = BytesIO()
    frames[-1].save(png_out, format="PNG")
    png_out.seek(0)
    
    gif_out = BytesIO()
    durations = [80] * total_frames
    frames[0].save(
        gif_out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0
    )
    gif_out.seek(0)
    
    for frame in frames:
        frame.close()
        
    return gif_out, png_out

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

class ColorWheelSelectionView(discord.ui.View):
    def __init__(self, cog: "GamblingGames", ctx: commands.Context, bet_amount: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx
        self.bet_amount = bet_amount
        self.chosen_color = "blue"
        self.message = None
        self.clicked = False
        self.update_button_styles()

    def update_button_styles(self):
        self.btn_blue.style = discord.ButtonStyle.primary if self.chosen_color == "blue" else discord.ButtonStyle.secondary
        self.btn_green.style = discord.ButtonStyle.primary if self.chosen_color == "green" else discord.ButtonStyle.secondary
        self.btn_yellow.style = discord.ButtonStyle.primary if self.chosen_color == "yellow" else discord.ButtonStyle.secondary
        self.btn_red.style = discord.ButtonStyle.primary if self.chosen_color == "red" else discord.ButtonStyle.secondary

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("❌ Đây không phải lượt quay của bạn!", ephemeral=True)
            return False
        return True

    async def update_lobby_selection(self, interaction: discord.Interaction, color: str):
        self.chosen_color = color
        self.update_button_styles()
        embed = self.cog.format_confirm_embed(self.ctx.author.mention, self.bet_amount, self.chosen_color)
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🔵 Xanh dương (x2)", style=discord.ButtonStyle.secondary, row=0)
    async def btn_blue(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_lobby_selection(interaction, "blue")

    @discord.ui.button(label="🟢 Xanh lá (x3)", style=discord.ButtonStyle.secondary, row=0)
    async def btn_green(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_lobby_selection(interaction, "green")

    @discord.ui.button(label="🟡 Vàng (x5)", style=discord.ButtonStyle.secondary, row=0)
    async def btn_yellow(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_lobby_selection(interaction, "yellow")

    @discord.ui.button(label="🔴 Đỏ (x10)", style=discord.ButtonStyle.secondary, row=0)
    async def btn_red(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.update_lobby_selection(interaction, "red")

    @discord.ui.button(label="Quay ngay!", style=discord.ButtonStyle.success, emoji="🎡", row=1)
    async def spin_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Disable all buttons immediately for instant feedback and to prevent double-clicks
        for child in self.children:
            child.disabled = True
        self.clicked = True
        self.stop()
        
        embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description="⏳ **Đang thiết lập vòng quay...**"
        )
        # Edit message immediately (very fast, no file upload yet)
        await interaction.response.edit_message(embed=embed, view=self)
        
        await self.cog.run_spin(self.ctx, self.bet_amount, self.chosen_color, self.message)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        self.clicked = True
        self.stop()
        self.cog.active_wheel_players.discard(self.ctx.author.id)
        
        embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description=f"❌ **{self.ctx.author.mention} đã hủy lượt quay.**",
        )
        await interaction.response.edit_message(embed=embed, view=None)

    async def on_timeout(self):
        if not self.clicked:
            self.stop()
            self.cog.active_wheel_players.discard(self.ctx.author.id)
            embed = CasinoEmbed(
                title="🎡 VÒNG QUAY MAY MẮN",
                description=f"⏱️ **Đã hết thời gian xác nhận. Lượt quay bị hủy.**",
            )
            try:
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass


class GamblingGames(commands.Cog, name="GamblingGames"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())
        self.active_taixiu_sessions = set()
        self.taixiu_history = []
        self.active_baucua_sessions = set()
        self.baucua_history = []
        self.active_wheel_players = set()
        
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

    @commands.command(
        brief="Chơi Tài Xỉu tương tác với 3 viên xúc xắc.",
        usage="taixiu",
        aliases=["tx"],
    )
    async def taixiu(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self.active_taixiu_sessions:
            await ctx.send("❌ **Lỗi:** Đang có một phiên Tài Xỉu đang diễn ra ở kênh này. Vui lòng đợi phiên cược kết thúc!")
            return
            
        self.active_taixiu_sessions.add(channel_id)
        session_id = random.randint(100000, 999999)
        
        try:
            view = TaiXiuLobbyView(self, session_id=session_id)
            embed = view.create_embed()
            
            img_bytes = generate_taixiu_image(
                view.seconds_remaining,
                view.tai_bets,
                view.xiu_bets
            )
            file = discord.File(img_bytes, filename="taixiu.png")
            
            message = await ctx.send(embed=embed, file=file, view=view)
            view.message = message
            
            while view.seconds_remaining > 0:
                await asyncio.sleep(5)
                view.seconds_remaining -= 5
                if view.seconds_remaining <= 0:
                    break
                await view.update_message()
                
            view.is_closed = True
            view.seconds_remaining = 0
            
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
                    
            embed = view.create_embed()
            embed.description = "🎲 **HẾT GIỜ ĐẶT CƯỢC! ĐANG LẮC XÚC XẮC...** 🎲"
            
            img_bytes = generate_taixiu_image(
                0,
                view.tai_bets,
                view.xiu_bets,
                result_text="LẮC"
            )
            file = discord.File(img_bytes, filename="taixiu.png")
            await message.edit(embed=embed, attachments=[file], view=view)
            
            await asyncio.sleep(2)
            
            # Retrieve rigging settings
            rig_rate_str = self.economy.get_setting("taixiu_rig_rate")
            rig_rate = float(rig_rate_str) if rig_rate_str else 0.0
            
            threshold_str = self.economy.get_setting("taixiu_anti_bankruptcy_threshold")
            threshold = int(threshold_str) if threshold_str else 10000000  # Default 10M VND
            
            tax_rate_str = self.economy.get_setting("taixiu_tax_rate")
            tax_rate = float(tax_rate_str) if tax_rate_str else 0.0
            
            # Calculate total bets placed in this session
            total_session_bets = (
                sum(view.tai_bets.values()) +
                sum(view.xiu_bets.values()) +
                sum(view.chan_bets.values()) +
                sum(view.le_bets.values()) +
                sum(sum(view.number_bets[n].values()) for n in range(1, 7))
            )
            
            # 1. Roll fair random dice
            fair_dice = [random.randint(1, 6) for _ in range(3)]
            fair_payout = calculate_taixiu_payout(fair_dice, view, tax_rate)
            fair_loss = fair_payout - total_session_bets
            
            # 2. Check if we override with a rigged outcome
            rig_triggered = random.random() < rig_rate
            bankruptcy_triggered = (threshold >= 0) and (fair_loss > threshold)
            
            if (rig_triggered or bankruptcy_triggered) and total_session_bets > 0:
                # Find outcome that minimizes payout
                candidates = []
                for d1 in range(1, 7):
                    for d2 in range(1, 7):
                        for d3 in range(1, 7):
                            cand_dice = [d1, d2, d3]
                            pay = calculate_taixiu_payout(cand_dice, view, tax_rate)
                            candidates.append((pay, cand_dice))
                
                # Sort by payout ascending
                candidates.sort(key=lambda x: x[0])
                min_payout = candidates[0][0]
                best_choices = [c[1] for c in candidates if c[0] == min_payout]
                selected_dice = random.choice(best_choices)
                
                rigged_payout = min_payout
                saved_amount = fair_payout - rigged_payout
                
                logger.info(
                    f"[TAI XIU RIGGING] Session {session_id} rigged. "
                    f"Reason: rig_rate={rig_triggered}, bankruptcy={bankruptcy_triggered}. "
                    f"Fair Roll: {fair_dice} (Payout: {fair_payout:,} VND). "
                    f"Rigged Roll: {selected_dice} (Payout: {rigged_payout:,} VND). "
                    f"Saved: {saved_amount:,} VND."
                )
                dice = selected_dice
            else:
                dice = fair_dice
                
            total = sum(dice)
            if 3 <= total <= 10:
                winning_side = "xiu"
                result_text = "XỈU"
            else:
                winning_side = "tai"
                result_text = "TÀI"
                
            # Add to history
            self.taixiu_history.append((session_id, dice, total, result_text))
            self.taixiu_history = self.taixiu_history[-10:]
            
            # Calculate session bets per user
            session_bets = {}
            for uid, amt in view.tai_bets.items():
                session_bets[uid] = session_bets.get(uid, 0) + amt
            for uid, amt in view.xiu_bets.items():
                session_bets[uid] = session_bets.get(uid, 0) + amt
            for uid, amt in view.chan_bets.items():
                session_bets[uid] = session_bets.get(uid, 0) + amt
            for uid, amt in view.le_bets.items():
                session_bets[uid] = session_bets.get(uid, 0) + amt
            for n in range(1, 7):
                for uid, amt in view.number_bets[n].items():
                    session_bets[uid] = session_bets.get(uid, 0) + amt

            # Check for jackpot (Bão 1-1-1 hoặc 6-6-6)
            is_jackpot_triggered = False
            jackpot_winners = []
            jackpot_val_won = 0
            if (dice[0] == dice[1] == dice[2]) and (dice[0] in (1, 6)):
                jackpot_rate_str = self.economy.get_setting("taixiu_jackpot_rate")
                jackpot_rate = float(jackpot_rate_str) if jackpot_rate_str else 1.0
                
                if random.random() < jackpot_rate:
                    min_bet_str = self.economy.get_setting("taixiu_jackpot_min_bet")
                    jackpot_min_bet = int(min_bet_str) if min_bet_str else 50000
                    
                    jackpot_winning_side = "xiu" if dice[0] == 1 else "tai"
                    side_bets = view.xiu_bets if jackpot_winning_side == "xiu" else view.tai_bets
                    
                    eligible_bets = {uid: amt for uid, amt in side_bets.items() if amt >= jackpot_min_bet}
                    total_eligible_bets = sum(eligible_bets.values())
                    
                    if total_eligible_bets > 0:
                        is_jackpot_triggered = True
                        jackpot_str = self.economy.get_setting("taixiu_jackpot")
                        jackpot_val = int(jackpot_str) if jackpot_str else 0
                        jackpot_val_won = jackpot_val
                        for uid, amt in eligible_bets.items():
                            share = int(jackpot_val * (amt / total_eligible_bets))
                            if share > 0:
                                self.economy.add_money(uid, share)
                                if share >= 1_000_000:
                                    from app.discord_bot.modules.betting import reward_spouse_share
                                    await reward_spouse_share(self.client, uid, share, ctx.channel)
                                jackpot_winners.append((uid, share))
                                log_wallet_change(
                                    logger,
                                    event="taixiu_jackpot_win",
                                    user_id=uid,
                                    money_delta=share,
                                    ctx=ctx,
                                    session_id=session_id,
                                )
                        self.economy.set_setting("taixiu_jackpot", "0")

            # Determine winners, losers and payouts
            winners = []
            winner_mentions = []
            losers = []
            user_ids = set(session_bets.keys())
            
            tax_rate_str = self.economy.get_setting("taixiu_tax_rate")
            tax_rate = float(tax_rate_str) if tax_rate_str else 0.0
            total_tax_collected = 0
            
            for uid in user_ids:
                name = view.user_names.get(uid, f"User {uid}")
                total_payout_before_tax = 0
                total_bet_for_user = session_bets[uid]
                details = []
                winning_bet_amt = 0
                
                # Tai
                if uid in view.tai_bets:
                    amt = view.tai_bets[uid]
                    if winning_side == "tai":
                        total_payout_before_tax += 2 * amt
                        winning_bet_amt += amt
                        bet_tax = int(amt * tax_rate)
                        details.append(f"Tài: +{amt - bet_tax:,} VND")
                    else:
                        details.append(f"Tài: -{amt:,} VND")
                        
                # Xiu
                if uid in view.xiu_bets:
                    amt = view.xiu_bets[uid]
                    if winning_side == "xiu":
                        total_payout_before_tax += 2 * amt
                        winning_bet_amt += amt
                        bet_tax = int(amt * tax_rate)
                        details.append(f"Xỉu: +{amt - bet_tax:,} VND")
                    else:
                        details.append(f"Xỉu: -{amt:,} VND")
                        
                # Chan
                if uid in view.chan_bets:
                    amt = view.chan_bets[uid]
                    if total % 2 == 0:
                        total_payout_before_tax += 2 * amt
                        winning_bet_amt += amt
                        bet_tax = int(amt * tax_rate)
                        details.append(f"Chẵn: +{amt - bet_tax:,} VND")
                    else:
                        details.append(f"Chẵn: -{amt:,} VND")
                        
                # Le
                if uid in view.le_bets:
                    amt = view.le_bets[uid]
                    if total % 2 != 0:
                        total_payout_before_tax += 2 * amt
                        winning_bet_amt += amt
                        bet_tax = int(amt * tax_rate)
                        details.append(f"Lẻ: +{amt - bet_tax:,} VND")
                    else:
                        details.append(f"Lẻ: -{amt:,} VND")
                        
                # Numbers 1-6
                for n in range(1, 7):
                    if uid in view.number_bets[n]:
                        amt = view.number_bets[n][uid]
                        matches = dice.count(n)
                        if matches > 0:
                            payout = (matches + 1) * amt
                            total_payout_before_tax += payout
                            winning_bet_amt += amt
                            net_win_bet = matches * amt
                            bet_tax = int(net_win_bet * tax_rate)
                            details.append(f"Số {n} (x{matches}): +{net_win_bet - bet_tax:,} VND")
                        else:
                            details.append(f"Số {n}: -{amt:,} VND")
                            
                # Calculate tax
                net_win = total_payout_before_tax - winning_bet_amt
                tax = 0
                if net_win > 0:
                    tax = int(net_win * tax_rate)
                    total_tax_collected += tax
                
                total_payout = total_payout_before_tax - tax
                    
                net_profit = total_payout - total_bet_for_user
                if total_payout > 0:
                    self.economy.add_money(uid, total_payout)
                    if total_payout >= 1_000_000:
                        from app.discord_bot.modules.betting import reward_spouse_share
                        await reward_spouse_share(self.client, uid, total_payout, ctx.channel)
                    new_bal = self.economy.get_entry(uid)[1]
                    details_str = ", ".join(details)
                    if net_profit > 0:
                        winners.append(f"• **{name}**: Thắng `+{net_profit:,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                        winner_mentions.append(f"<@{uid}>")
                    elif net_profit == 0:
                        winners.append(f"• **{name}**: Hòa vốn `{net_profit:,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                    else:
                        losers.append(f"• **{name}**: Thua lỗ `-{abs(net_profit):,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                        
                    log_wallet_change(
                        logger,
                        event="taixiu_payout_resolved",
                        user_id=uid,
                        money_delta=net_profit,
                        ctx=ctx,
                        payout=total_payout,
                        net_profit=net_profit,
                        session_id=session_id,
                    )
                else:
                    new_bal = self.economy.get_entry(uid)[1]
                    details_str = ", ".join(details)
                    losers.append(f"• **{name}**: Thua `-{total_bet_for_user:,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                    log_wallet_change(
                        logger,
                        event="taixiu_payout_resolved",
                        user_id=uid,
                        money_delta=-total_bet_for_user,
                        ctx=ctx,
                        payout=0,
                        net_profit=-total_bet_for_user,
                        session_id=session_id,
                    )

            # Add only tax collected from winning bets to the jackpot (Option B)
            jackpot_addition = total_tax_collected
            if jackpot_addition > 0:
                jackpot_str = self.economy.get_setting("taixiu_jackpot")
                jackpot_val = int(jackpot_str) if jackpot_str else 0
                new_jackpot = jackpot_val + jackpot_addition
                self.economy.set_setting("taixiu_jackpot", str(new_jackpot))

            dice_emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
            dice_str = " ".join(dice_emojis[d] for d in dice)
            
            winner_section = "\n".join(winners) if winners else "*Không có*"
            loser_section = "\n".join(losers) if losers else "*Không có*"
            
            # Format jackpot display in description
            jackpot_section = ""
            if is_jackpot_triggered:
                if jackpot_winners:
                    jw_lines = []
                    for uid, share in jackpot_winners:
                        name = view.user_names.get(uid, f"User {uid}")
                        jw_lines.append(f"🎉 **{name}**: Nhận `+{share:,} VND` từ Hũ Jackpot!")
                    jackpot_section = f"\n\n💥 **NỔ HŨ JACKPOT TÀI XỈU!** 💥\n" + "\n".join(jw_lines)
                else:
                    jackpot_section = f"\n\n💥 **NỔ HŨ JACKPOT TÀI XỈU!** 💥\n*Không có người chơi thắng cuộc hợp lệ.*"
            
            chan_le_text = "CHẴN" if total % 2 == 0 else "LẺ"
            result_desc = (
                f"🎲 **Kết quả:** {dice_str}\n"
                f"📊 **Tổng số nút:** `{total}` ➔ **{result_text}** và **{chan_le_text}**!\n"
                f"{jackpot_section}\n\n"
                f"🏆 **Danh sách thắng cuộc:**\n{winner_section}\n\n"
                f"💸 **Danh sách thua cuộc:**\n{loser_section}"
            )
            
            color = discord.Color.green() if winner_mentions else discord.Color.red()
            
            result_embed = make_embed(
                title=f"🎲 KẾT QUẢ TÀI XỈU #{session_id} 🎲",
                description=result_desc,
                color=color,
            )
            result_embed.set_image(url="attachment://taixiu.png")
            
            result_label = f"{result_text} - {total}"
            if dice[0] == dice[1] == dice[2]:
                result_label = f"BÃO - {total}"
                
            img_bytes = generate_taixiu_image(
                0,
                view.tai_bets,
                view.xiu_bets,
                result_text=result_label,
                dice=dice
            )
            file = discord.File(img_bytes, filename="taixiu.png")
            
            await message.edit(embed=result_embed, attachments=[file], view=view)
            
            if is_jackpot_triggered and jackpot_winners:
                jw_mentions = [f"<@{uid}>" for uid, _ in jackpot_winners]
                await ctx.send(f"🎉💥 **JACKPOT CỰC ĐẠI ĐÃ NỔ!** Chúc mừng {', '.join(jw_mentions)} đã chia nhau hũ Jackpot trị giá **{jackpot_val_won:,} VND**! 💥🎉")
            
            if winner_mentions:
                await ctx.send(f"🎉 Chúc mừng các đại gia đã chiến thắng phiên #{session_id}: {', '.join(winner_mentions)}!")
        except Exception as e:
            logger.error(f"Error in taixiu command: {e}", exc_info=True)
            await ctx.send(f"❌ Có lỗi xảy ra trong phiên Tài Xỉu #{session_id}: `{e}`")
        finally:
            self.active_taixiu_sessions.discard(channel_id)

    @commands.command(
        brief="Chơi Bầu Cua Cá Cọp tương tác.",
        usage="baucua",
        aliases=["bc"],
    )
    async def baucua(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self.active_baucua_sessions:
            await ctx.send("❌ **Lỗi:** Đang có một phiên Bầu Cua đang diễn ra ở kênh này. Vui lòng đợi phiên cược kết thúc!")
            return
            
        self.active_baucua_sessions.add(channel_id)
        session_id = random.randint(100000, 999999)
        
        try:
            view = BauCuaLobbyView(self, session_id=session_id)
            embed = view.create_embed()
            
            img_bytes = generate_baucua_image(
                view.seconds_remaining,
                view.bets
            )
            file = discord.File(img_bytes, filename="baucua.png")
            
            message = await ctx.send(embed=embed, file=file, view=view)
            view.message = message
            
            while view.seconds_remaining > 0:
                await asyncio.sleep(5)
                view.seconds_remaining -= 5
                if view.seconds_remaining <= 0:
                    break
                await view.update_message()
                
            view.is_closed = True
            view.seconds_remaining = 0
            
            for child in view.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
                    
            embed = view.create_embed()
            embed.description = "🎲 **HẾT GIỜ ĐẶT CƯỢC! ĐANG LẮC BẦU CUA...** 🎲"
            
            img_bytes = generate_baucua_image(
                0,
                view.bets,
                result_text="LẮC"
            )
            file = discord.File(img_bytes, filename="baucua.png")
            await message.edit(embed=embed, attachments=[file], view=view)
            
            await asyncio.sleep(2)
            
            mascots = ["nai", "bau", "ga", "ca", "cua", "tom"]
            dice = [random.choice(mascots) for _ in range(3)]
            
            # Add to history
            self.baucua_history.append((session_id, dice))
            self.baucua_history = self.baucua_history[-10:]
            
            # Calculate total bets per user in session
            session_bets = {}
            for mascot in view.bets:
                for uid, amt in view.bets[mascot].items():
                    session_bets[uid] = session_bets.get(uid, 0) + amt

            # Check for jackpot (Bão - 3 identical mascots)
            is_jackpot_triggered = False
            jackpot_winners = []
            jackpot_val_won = 0
            if dice[0] == dice[1] == dice[2]:
                jackpot_rate_str = self.economy.get_setting("baucua_jackpot_rate")
                jackpot_rate = float(jackpot_rate_str) if jackpot_rate_str is not None else 1.0
                
                if random.random() < jackpot_rate:
                    total_session_bets = sum(session_bets.values())
                    if total_session_bets > 0:
                        is_jackpot_triggered = True
                        jackpot_str = self.economy.get_setting("baucua_jackpot")
                        jackpot_val = int(jackpot_str) if jackpot_str else 0
                        jackpot_val_won = jackpot_val
                        for uid, amt in session_bets.items():
                            share = int(jackpot_val * (amt / total_session_bets))
                        if share > 0:
                            self.economy.add_money(uid, share)
                            if share >= 1_000_000:
                                from app.discord_bot.modules.betting import reward_spouse_share
                                await reward_spouse_share(self.client, uid, share, ctx.channel)
                            jackpot_winners.append((uid, share))
                            log_wallet_change(
                                logger,
                                event="baucua_jackpot_win",
                                user_id=uid,
                                money_delta=share,
                                ctx=ctx,
                                session_id=session_id,
                            )
                    self.economy.set_setting("baucua_jackpot", "0")

            winners = []
            winner_mentions = []
            losers = []
            total_tax_collected = 0
            
            user_ids = set()
            for mascot in view.bets:
                for uid in view.bets[mascot]:
                    user_ids.add(uid)
                    
            mascot_names_viet = {"nai": "Nai", "bau": "Bầu", "ga": "Gà", "ca": "Cá", "cua": "Cua", "tom": "Tôm"}

            # Read tax rate setting (same pattern as taixiu)
            tax_rate_str = self.economy.get_setting("baucua_tax_rate")
            tax_rate = float(tax_rate_str) if tax_rate_str is not None else 0.0
            
            for uid in user_ids:
                name = view.user_names.get(uid, f"User {uid}")
                total_payout_before_tax = 0
                total_bet_for_user = 0
                winning_bet_amt = 0
                details = []
                
                for mascot in view.bets:
                    if uid in view.bets[mascot]:
                        amt = view.bets[mascot][uid]
                        total_bet_for_user += amt
                        count = dice.count(mascot)
                        if count > 0:
                            payout = (count + 1) * amt
                            total_payout_before_tax += payout
                            winning_bet_amt += amt
                            net_win_bet = count * amt
                            bet_tax = int(net_win_bet * tax_rate)
                            details.append(f"{mascot_names_viet[mascot]} (x{count}): +{net_win_bet - bet_tax:,} VND")
                        else:
                            details.append(f"{mascot_names_viet[mascot]}: -{amt:,} VND")

                # Calculate tax on net winning amount
                net_win = total_payout_before_tax - winning_bet_amt
                tax = 0
                if net_win > 0:
                    tax = int(net_win * tax_rate)
                    total_tax_collected += tax

                total_payout = total_payout_before_tax - tax
                net_profit = total_payout - total_bet_for_user
                if total_payout > 0:
                    self.economy.add_money(uid, total_payout)
                    if total_payout >= 1_000_000:
                        from app.discord_bot.modules.betting import reward_spouse_share
                        await reward_spouse_share(self.client, uid, total_payout, ctx.channel)
                    new_bal = self.economy.get_entry(uid)[1]
                    details_str = ", ".join(details)
                    if net_profit > 0:
                        winners.append(f"• **{name}**: Thắng `+{net_profit:,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                        winner_mentions.append(f"<@{uid}>")
                    elif net_profit == 0:
                        winners.append(f"• **{name}**: Hòa vốn `{net_profit:,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                    else:
                        losers.append(f"• **{name}**: Thua lỗ `-{abs(net_profit):,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                        
                    log_wallet_change(
                        logger,
                        event="baucua_payout_resolved",
                        user_id=uid,
                        money_delta=net_profit,
                        ctx=ctx,
                        payout=total_payout,
                        net_profit=net_profit,
                        session_id=session_id,
                    )
                else:
                    new_bal = self.economy.get_entry(uid)[1]
                    details_str = ", ".join(details)
                    losers.append(f"• **{name}**: Thua `-{total_bet_for_user:,} VND` ({details_str}) (Số dư: `{new_bal:,} VND`)")
                    log_wallet_change(
                        logger,
                        event="baucua_payout_resolved",
                        user_id=uid,
                        money_delta=-total_bet_for_user,
                        ctx=ctx,
                        payout=0,
                        net_profit=-total_bet_for_user,
                        session_id=session_id,
                    )

            # Add tax collected from winning bets to jackpot (same as taixiu)
            jackpot_addition = total_tax_collected
            if jackpot_addition > 0:
                jackpot_str = self.economy.get_setting("baucua_jackpot")
                jackpot_val = int(jackpot_str) if jackpot_str else 0
                new_jackpot = jackpot_val + jackpot_addition
                self.economy.set_setting("baucua_jackpot", str(new_jackpot))
                    
            mascot_emojis = {"ca": "🐟", "cua": "🦀", "tom": "🦐", "nai": "🦌", "bau": "🍐", "ga": "🐓"}
            dice_str = " ".join(mascot_emojis[d] for d in dice)
            
            winner_section = "\n".join(winners) if winners else "*Không có*"
            loser_section = "\n".join(losers) if losers else "*Không có*"

            # Format jackpot display in description
            jackpot_section = ""
            if is_jackpot_triggered:
                if jackpot_winners:
                    jw_lines = []
                    for uid, share in jackpot_winners:
                        name = view.user_names.get(uid, f"User {uid}")
                        jw_lines.append(f"🎉 **{name}**: Nhận `+{share:,} VND` từ Hũ Jackpot!")
                    jackpot_section = f"\n\n💥 **NỔ HŨ JACKPOT BẦU CUA!** 💥\n" + "\n".join(jw_lines)
                else:
                    jackpot_section = f"\n\n💥 **NỔ HŨ JACKPOT BẦU CUA!** 💥\n*Không có người chơi thắng cuộc hợp lệ.*"
            
            result_desc = (
                f"🎲 **Kết quả lắc:** {dice_str}\n"
                f"{jackpot_section}\n\n"
                f"🏆 **Danh sách thắng cuộc:**\n{winner_section}\n\n"
                f"💸 **Danh sách thua cuộc:**\n{loser_section}"
            )
            
            color = discord.Color.green() if winner_mentions else discord.Color.red()
            
            result_embed = make_embed(
                title=f"🦀 KẾT QUẢ BẦU CUA #{session_id} 🦀",
                description=result_desc,
                color=color,
            )
            result_embed.set_image(url="attachment://baucua.png")
            
            result_label = " • ".join(mascot_names_viet[d].upper() for d in dice)
            if dice[0] == dice[1] == dice[2]:
                result_label = f"BÃO {mascot_names_viet[dice[0]].upper()}"
            
            img_bytes = generate_baucua_image(
                0,
                view.bets,
                result_text=result_label,
                dice_results=dice
            )
            file = discord.File(img_bytes, filename="baucua.png")
            
            await message.edit(embed=result_embed, attachments=[file], view=view)
            
            if is_jackpot_triggered and jackpot_winners:
                jw_mentions = [f"<@{uid}>" for uid, _ in jackpot_winners]
                await ctx.send(f"🎉💥 **JACKPOT BẦU CUA CỰC ĐẠI ĐÃ NỔ!** Chúc mừng {', '.join(jw_mentions)} đã chia nhau hũ Jackpot trị giá **{jackpot_val_won:,} VND**! 💥🎉")

            if winner_mentions:
                await ctx.send(f"🎉 Chúc mừng các đại gia đã chiến thắng phiên #{session_id}: {', '.join(winner_mentions)}!")
        except Exception as e:
            logger.error(f"Error in baucua command: {e}", exc_info=True)
            await ctx.send(f"❌ Có lỗi xảy ra trong phiên Bầu Cua #{session_id}.")
        finally:
            self.active_baucua_sessions.discard(channel_id)

    @commands.hybrid_command(
        name="quay",
        brief="Chơi game casino Vòng Quay May Mắn. Ví dụ: `i?quay 50k` và chọn màu trên nút bấm.",
        usage="quay [tiền_cược]",
        description="Quay vòng quay may mắn để thắng lớn"
    )
    @commands.cooldown(1, 5, commands.BucketType.user)
    @discord.app_commands.describe(
        bet_amount_str="Số tiền đặt cược (Tối thiểu 1,000, Tối đa 10,000,000, VD: 50k, 50000, all)"
    )
    async def quay(self, ctx: commands.Context, bet_amount_str: str):
        user_id = ctx.author.id
        
        # Concurrency check
        if user_id in self.active_wheel_players:
            await ctx.send("❌ Bạn đang có một ván quay khác đang diễn ra. Vui lòng hoàn thành ván đó trước.", ephemeral=True)
            return
        
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
        self.active_wheel_players.add(user_id)
        
        # Build selection embed
        embed = self.format_confirm_embed(ctx.author.mention, bet_amount, "blue")
        
        view = ColorWheelSelectionView(self, ctx, bet_amount)
        view.message = await ctx.send(embed=embed, view=view)

    def format_confirm_embed(self, user_mention: str, bet_amount: int, chosen_color: str) -> CasinoEmbed:
        opts = [
            ("blue", "🔵", "Xanh dương", "x2"),
            ("green", "🟢", "Xanh lá", "x3"),
            ("yellow", "🟡", "Vàng", "x5"),
            ("red", "🔴", "Đỏ", "x10")
        ]
        
        list_lines = []
        for key, emoji, label, mult in opts:
            if key == chosen_color:
                list_lines.append(f"➡️ **{emoji} {label} ({mult})** ◀ *[ĐÃ CHỌN]*")
            else:
                list_lines.append(f"🔹 {emoji} {label} ({mult})")
                
        desc = (
            f"👤 **Người chơi:** {user_mention}\n"
            f"💰 **Tiền cược:** `{bet_amount:,} VNĐ`\n\n"
            f"**[ TẤT CẢ Ô CƯỢC ]**\n"
            + "\n".join(list_lines)
        )
        
        embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description=desc
        )
        embed.set_footer(text="Chọn màu sắc cược ở dưới rồi nhấn 'Quay ngay!'")
        return embed

    async def run_spin(self, ctx: commands.Context, bet_amount: int, chosen_color: str, message: discord.Message):
        user_id = ctx.author.id
        guild_id = ctx.guild.id if ctx.guild else 0
        
        # Double check money
        current_money = self.economy.get_entry(user_id)[1]
        if current_money < bet_amount:
            self.active_wheel_players.discard(user_id)
            await message.edit(content="❌ Bạn không đủ tiền trong ví để quay!", embed=None, view=None)
            return
            
        # Deduct wallet
        self.economy.add_money(user_id, -bet_amount)
        log_wallet_change(logger, event="color_wheel_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
        
        # Random spin slot
        win_idx = random.randint(0, 29)
        result_color = WHEEL_LAYOUT[win_idx]
        
        # Generate spin GIF and static result PNG in memory using Pillow on a background thread
        try:
            gif_buffer, png_buffer = await asyncio.to_thread(render_wheel_gif, win_idx)
            gif_file = discord.File(gif_buffer, filename="wheel_spin.gif")
            png_file = discord.File(png_buffer, filename="wheel_result.png")
        except Exception as e:
            logger.error(f"Pillow GIF generation failed: {e}", exc_info=True)
            # Refund
            self.economy.add_money(user_id, bet_amount)
            log_wallet_change(logger, event="color_wheel_error_refund", user_id=user_id, money_delta=bet_amount, ctx=ctx)
            self.active_wheel_players.discard(user_id)
            await message.edit(content="❌ Đã xảy ra lỗi khi tạo hiệu ứng vòng quay.", embed=None, view=None)
            return

        # Send embedding GIF "Vòng quay đang chạy..."
        spinning_embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description="⏳ **Vòng quay đang chạy... Chúc bạn may mắn!**"
        )
        spinning_embed.set_image(url="attachment://wheel_spin.gif")
        
        # Edit the message
        await message.edit(content=None, embed=spinning_embed, attachments=[gif_file], view=None)
        
        # Wait 3.0 seconds for slower spin animation
        await asyncio.sleep(3.0)
        
        # Calculate result
        is_win = (result_color == chosen_color)
        cfg_res = WHEEL_CONFIG[result_color]
        cfg_chosen = WHEEL_CONFIG[chosen_color]
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

        # Formulate final embed Y-aligned text
        now = datetime.now()
        am_pm = "SA" if now.hour < 12 else "CH"
        hour = now.hour if now.hour <= 12 else now.hour - 12
        if hour == 0:
            hour = 12
        footer_text = f"Sylus Meow • {now.strftime('%d/%m/%Y')} {hour:02d}:{now.strftime('%M')} {am_pm}"
        
        result_desc_lines = []
        result_desc_lines.append("🎡 **VÒNG QUAY MAY MẮN**")
        result_desc_lines.append("━━━━━━━━━━━━━━━━━━━")
        result_desc_lines.append(f"👤 **Người chơi:** {ctx.author.mention}")
        result_desc_lines.append(f"💰 **Tiền cược:**  `{bet_amount:,} VNĐ`\n")
        
        result_desc_lines.append(f"**[ ĐÃ CHỌN ]**")
        result_desc_lines.append(f"{cfg_chosen['emoji']} **{cfg_chosen['label']} (x{cfg_chosen['multiplier']})**\n")
        
        result_desc_lines.append(f"**[ KẾT QUẢ VÒNG QUAY ]**")
        color_label_upper = cfg_res['label'].upper()
        if is_win:
            result_desc_lines.append(f"✅ {cfg_res['emoji']} **{color_label_upper} (x{multiplier})**\n")
        else:
            result_desc_lines.append(f"❌ {cfg_res['emoji']} **{color_label_upper} (x{multiplier})** — Không trúng\n")
            
        result_desc_lines.append("━━━ **KẾT QUẢ** ━━━")
        col_profit = "Lợi nhuận" if is_win else "Lỗ"
        result_desc_lines.append(f"Tiền cược  │ Nhận về   │ {col_profit}")
        
        # Alignment logic
        bet_str = f"{bet_amount:,}".ljust(11)
        payout_str = f"{payout:,}".ljust(10)
        profit_val_str = f"+{profit:,}" if is_win else f"-{abs(profit):,}"
        result_desc_lines.append(f"`{bet_str}│ {payout_str}│ {profit_val_str}`\n")
        
        if is_win:
            result_desc_lines.append(f"🎉 **CHÚC MỪNG! Bạn đã đoán trúng màu ván này.**")
        else:
            result_desc_lines.append(f"😔 **Chúc bạn may mắn lần sau.**")
            
        result_desc_lines.append("━━━━━━━━━━━━━━━━━━━")
        
        final_embed = CasinoEmbed(
            description="\n".join(result_desc_lines)
        )
        final_embed.set_image(url="attachment://wheel_result.png")
        final_embed.set_footer(text=footer_text)
        
        # Edit the message to show final result and display the static wheel PNG result
        try:
            await message.edit(embed=final_embed, attachments=[png_file])
        except Exception:
            # Fallback if attachments cannot be edited easily
            await message.delete()
            await ctx.send(file=png_file, embed=final_embed)
            
        # Unlock player
        self.active_wheel_players.discard(user_id)


async def setup(client: commands.Bot):
    await client.add_cog(GamblingGames(client))
