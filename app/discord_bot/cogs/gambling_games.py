import asyncio
import io
import logging
import random
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

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
        return current_money
    
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
    base_img_path = "pictures/taixiu_bg.png"
    img = Image.open(base_img_path).convert("RGBA")
    # Crop to frame (924x570)
    cropped = img.crop((50, 200, 974, 770))
    draw = ImageDraw.Draw(cropped)
    
    # Load fonts
    font_large = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 100)
    font_medium = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 36)
    font_small = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 24)
    
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
    base_img_path = "pictures/baucua_bg.png"
    img = Image.open(base_img_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    # Load fonts
    font_large = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 60)
    font_medium = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 32)
    font_small = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 18)
    
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

        # Deduct balance immediately to prevent exploits
        self.lobby_view.cog.economy.add_money(user.id, -amount)
        
        if self.side == "tai":
            self.lobby_view.tai_bets[user.id] = self.lobby_view.tai_bets.get(user.id, 0) + amount
        else:
            self.lobby_view.xiu_bets[user.id] = self.lobby_view.xiu_bets.get(user.id, 0) + amount
            
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


class TaiXiuLobbyView(discord.ui.View):
    def __init__(self, cog, session_id: int, timeout: float = 40.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session_id = session_id
        self.tai_bets = {}
        self.xiu_bets = {}
        self.user_names = {}
        self.is_closed = False
        self.message = None
        self.seconds_remaining = 30

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
        
        tai_list = []
        for uid, amt in self.tai_bets.items():
            name = self.user_names.get(uid, f"User {uid}")
            tai_list.append(f"• **{name}**: `{amt:,} VND`")
            
        xiu_list = []
        for uid, amt in self.xiu_bets.items():
            name = self.user_names.get(uid, f"User {uid}")
            xiu_list.append(f"• **{name}**: `{amt:,} VND`")
            
        tai_list_str = "\n".join(tai_list) if tai_list else "*Chưa có*"
        xiu_list_str = "\n".join(xiu_list) if xiu_list else "*Chưa có*"
        
        currency = "<a:emoji_287:1514350238687821845>"
        
        embed = make_embed(
            title=f"🎲 PHIÊN TÀI XỈU #{self.session_id} 🎲",
            description=f"⏳ **Thời gian đặt cược còn lại:** `{self.seconds_remaining} giây`\n\n👉 Nhấp vào nút bên dưới để chọn cửa và đặt cược.",
            color=discord.Color.dark_theme()
        )
        
        # Put Tai and Xiu side-by-side using inline fields
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
        
        embed.set_image(url="attachment://taixiu.png")
        return embed

    @discord.ui.button(label="TÀI", style=discord.ButtonStyle.primary, emoji="🔵")
    async def bet_tai(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        modal = TaiXiuBetModal(side="tai", lobby_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="XỈU", style=discord.ButtonStyle.danger, emoji="🔴")
    async def bet_xiu(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc!", ephemeral=True)
            return
        modal = TaiXiuBetModal(side="xiu", lobby_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="HỦY CƯỢC", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message("❌ Phiên cược đã kết thúc! Không thể hủy cược.", ephemeral=True)
            return
            
        user = interaction.user
        refund_amount = 0
        side = None
        if user.id in self.tai_bets:
            refund_amount = self.tai_bets.pop(user.id)
            side = "tai"
        elif user.id in self.xiu_bets:
            refund_amount = self.xiu_bets.pop(user.id)
            side = "xiu"
            
        if refund_amount > 0:
            self.cog.economy.add_money(user.id, refund_amount)
            
            log_wallet_change(
                logger,
                event="taixiu_cancel_bet",
                user_id=user.id,
                money_delta=refund_amount,
                side=side,
                bet_amount=refund_amount,
            )
            await interaction.response.send_message(f"✅ Đã hủy cược thành công! Hoàn lại **{refund_amount:,} VND** vào ví.", ephemeral=True)
            await self.update_message()
        else:
            await interaction.response.send_message("❌ Bạn chưa đặt cược trong phiên này!", ephemeral=True)

    @discord.ui.button(label="LỊCH SỬ", style=discord.ButtonStyle.secondary, emoji="📜")
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
        
        embed = make_embed(
            title=f"🦀 PHIÊN BẦU CUA #{self.session_id} 🦀",
            description=f"⏳ **Thời gian đặt cược còn lại:** `{self.seconds_remaining} giây`\n\n👉 Nhấp vào các nút bên dưới để chọn linh vật cược.",
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


class GamblingGames(commands.Cog, name="GamblingGames"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())
        self.active_taixiu_sessions = set()
        self.taixiu_history = []
        self.active_baucua_sessions = set()
        self.baucua_history = []

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
            
            dice = [random.randint(1, 6) for _ in range(3)]
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
                
            winners = []
            winner_mentions = []
            losers = []
            
            for uid, amt in view.tai_bets.items():
                name = view.user_names.get(uid, f"User {uid}")
                if winning_side == "tai":
                    self.economy.add_money(uid, 2 * amt)
                    new_bal = self.economy.get_entry(uid)[1]
                    winners.append(f"• **{name}**: Thắng `+{amt:,} VND` (Số dư: `{new_bal:,} VND`)")
                    winner_mentions.append(f"<@{uid}>")
                    log_wallet_change(
                        logger,
                        event="taixiu_payout_win",
                        user_id=uid,
                        money_delta=amt,
                        ctx=ctx,
                        bet=amt,
                        session_id=session_id,
                    )
                else:
                    new_bal = self.economy.get_entry(uid)[1]
                    losers.append(f"• **{name}**: Thua `-{amt:,} VND` (Số dư: `{new_bal:,} VND`)")
                    log_wallet_change(
                        logger,
                        event="taixiu_payout_lose",
                        user_id=uid,
                        money_delta=-amt,
                        ctx=ctx,
                        bet=amt,
                        session_id=session_id,
                    )
                    
            for uid, amt in view.xiu_bets.items():
                name = view.user_names.get(uid, f"User {uid}")
                if winning_side == "xiu":
                    self.economy.add_money(uid, 2 * amt)
                    new_bal = self.economy.get_entry(uid)[1]
                    winners.append(f"• **{name}**: Thắng `+{amt:,} VND` (Số dư: `{new_bal:,} VND`)")
                    winner_mentions.append(f"<@{uid}>")
                    log_wallet_change(
                        logger,
                        event="taixiu_payout_win",
                        user_id=uid,
                        money_delta=amt,
                        ctx=ctx,
                        bet=amt,
                        session_id=session_id,
                    )
                else:
                    new_bal = self.economy.get_entry(uid)[1]
                    losers.append(f"• **{name}**: Thua `-{amt:,} VND` (Số dư: `{new_bal:,} VND`)")
                    log_wallet_change(
                        logger,
                        event="taixiu_payout_lose",
                        user_id=uid,
                        money_delta=-amt,
                        ctx=ctx,
                        bet=amt,
                        session_id=session_id,
                    )
                    
            dice_emojis = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣", 4: "4️⃣", 5: "5️⃣", 6: "6️⃣"}
            dice_str = " ".join(dice_emojis[d] for d in dice)
            
            winner_section = "\n".join(winners) if winners else "*Không có*"
            loser_section = "\n".join(losers) if losers else "*Không có*"
            
            result_desc = (
                f"🎲 **Kết quả:** {dice_str}\n"
                f"📊 **Tổng số nút:** `{total}` ➔ **{result_text}!**\n\n"
                f"🏆 **Danh sách thắng cuộc:**\n{winner_section}\n\n"
                f"💸 **Danh sách thua cuộc:**\n{loser_section}"
            )
            
            color = discord.Color.green() if winners else discord.Color.red()
            
            result_embed = make_embed(
                title=f"🎲 KẾT QUẢ TÀI XỈU #{session_id} 🎲",
                description=result_desc,
                color=color,
            )
            result_embed.set_image(url="attachment://taixiu.png")
            
            result_label = f"{result_text} - {total}"
                
            img_bytes = generate_taixiu_image(
                0,
                view.tai_bets,
                view.xiu_bets,
                result_text=result_label,
                dice=dice
            )
            file = discord.File(img_bytes, filename="taixiu.png")
            
            await message.edit(embed=result_embed, attachments=[file], view=view)
            
            if winner_mentions:
                await ctx.send(f"🎉 Chúc mừng các đại gia đã chiến thắng phiên #{session_id}: {', '.join(winner_mentions)}!")
        except Exception as e:
            logger.error(f"Error in taixiu command: {e}", exc_info=True)
            await ctx.send(f"❌ Có lỗi xảy ra trong phiên Tài Xỉu #{session_id}.")
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
            
            winners = []
            winner_mentions = []
            losers = []
            
            user_ids = set()
            for mascot in view.bets:
                for uid in view.bets[mascot]:
                    user_ids.add(uid)
                    
            mascot_names_viet = {"nai": "Nai", "bau": "Bầu", "ga": "Gà", "ca": "Cá", "cua": "Cua", "tom": "Tôm"}
            
            for uid in user_ids:
                name = view.user_names.get(uid, f"User {uid}")
                total_payout = 0
                total_bet_for_user = 0
                details = []
                
                for mascot in view.bets:
                    if uid in view.bets[mascot]:
                        amt = view.bets[mascot][uid]
                        total_bet_for_user += amt
                        count = dice.count(mascot)
                        if count > 0:
                            payout = (count + 1) * amt
                            total_payout += payout
                            details.append(f"{mascot_names_viet[mascot]} (x{count}): +{count*amt:,} VND")
                        else:
                            details.append(f"{mascot_names_viet[mascot]}: -{amt:,} VND")
                
                net_profit = total_payout - total_bet_for_user
                if total_payout > 0:
                    self.economy.add_money(uid, total_payout)
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
                    
            mascot_emojis = {"ca": "🐟", "cua": "🦀", "tom": "🦐", "nai": "🦌", "bau": "🍐", "ga": "🐓"}
            dice_str = " ".join(mascot_emojis[d] for d in dice)
            
            winner_section = "\n".join(winners) if winners else "*Không có*"
            loser_section = "\n".join(losers) if losers else "*Không có*"
            
            result_desc = (
                f"🎲 **Kết quả lắc:** {dice_str}\n\n"
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
            
            img_bytes = generate_baucua_image(
                0,
                view.bets,
                result_text=result_label,
                dice_results=dice
            )
            file = discord.File(img_bytes, filename="baucua.png")
            
            await message.edit(embed=result_embed, attachments=[file], view=view)
            
            if winner_mentions:
                await ctx.send(f"🎉 Chúc mừng các đại gia đã chiến thắng phiên #{session_id}: {', '.join(winner_mentions)}!")
        except Exception as e:
            logger.error(f"Error in baucua command: {e}", exc_info=True)
            await ctx.send(f"❌ Có lỗi xảy ra trong phiên Bầu Cua #{session_id}.")
        finally:
            self.active_baucua_sessions.discard(channel_id)


async def setup(client: commands.Bot):
    await client.add_cog(GamblingGames(client))
