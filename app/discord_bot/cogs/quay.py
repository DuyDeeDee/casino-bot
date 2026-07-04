import asyncio
from datetime import datetime
import logging
import random
import time
import os
import math
from io import BytesIO
from PIL import Image, ImageDraw

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.helpers import InsufficientFundsException
from app.discord_bot.modules.profile_renderer import load_font, fetch_avatar

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

# Helpers for custom drawing
def make_circular(img: Image.Image, size: tuple[int, int]) -> Image.Image:
    img = img.resize(size, Image.Resampling.LANCZOS)
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)
    draw.ellipse([0, 0, size[0], size[1]], fill=255)
    output = Image.new("RGBA", size, (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    return output

def draw_ferris_wheel_logo(draw: ImageDraw.ImageDraw, x1, y1, x2, y2):
    cx = (x1 + x2) / 2
    cy = (y1 + y2) / 2
    r_outer = (x2 - x1) * 0.35
    r_inner = r_outer * 0.3
    
    # Outer ring
    draw.ellipse([cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer], outline=(255, 255, 255, 255), width=2)
    # Inner ring
    draw.ellipse([cx - r_inner, cy - r_inner, cx + r_inner, cy + r_inner], fill=(255, 255, 255, 255))
    
    # Spokes
    for i in range(8):
        angle = math.radians(i * 45)
        dx = r_outer * math.cos(angle)
        dy = r_outer * math.sin(angle)
        draw.line([cx, cy, cx + dx, cy + dy], fill=(255, 255, 255, 200), width=1)
        
    # Stand
    draw.line([cx, cy, cx - r_outer * 0.8, cy + r_outer * 1.1], fill=(255, 255, 255, 255), width=2)
    draw.line([cx, cy, cx + r_outer * 0.8, cy + r_outer * 1.1], fill=(255, 255, 255, 255), width=2)
    draw.line([cx - r_outer * 0.9, cy + r_outer * 1.1, cx + r_outer * 0.9, cy + r_outer * 1.1], fill=(255, 255, 255, 255), width=1)

def render_lobby_image(username: str, avatar_img: Image.Image, bet_amount: int, chosen_color: str) -> BytesIO:
    width = 600
    height = 380
    
    # Fonts
    font_title = load_font("bold", 18)
    font_subtitle = load_font("regular", 11)
    font_bold_medium = load_font("bold", 12)
    font_regular_medium = load_font("regular", 11)
    font_small = load_font("regular", 9)
    font_bold_small = load_font("bold", 9)
    
    # Base background #151824
    img = Image.new("RGBA", (width, height), (21, 24, 36, 255))
    draw = ImageDraw.Draw(img)
    
    # Header Icon Box
    draw.rounded_rectangle([25, 20, 60, 55], radius=6, fill=(200, 168, 75, 255))
    draw_ferris_wheel_logo(draw, 25, 20, 60, 55)
    
    # Titles
    draw.text((75, 20), "VÒNG QUAY MAY MẮN", fill=(200, 168, 75, 255), font=font_title)
    draw.text((75, 43), "Xác nhận đặt cược", fill=(100, 110, 140, 255), font=font_subtitle)
    
    # Status pill: CHUẨN BỊ
    draw.rounded_rectangle([480, 24, 575, 50], radius=4, outline=(200, 168, 75, 255), width=1)
    draw.text((527, 37), "CHUẨN BỊ", fill=(200, 168, 75, 255), font=font_bold_small, anchor="mm")
    
    draw.line([25, 70, 575, 70], fill=(35, 40, 55, 255), width=1)
    
    # Profile avatar
    avatar_resized = make_circular(avatar_img, (36, 36))
    img.paste(avatar_resized, (25, 80), avatar_resized)
    
    # Profile labels
    draw.text((72, 82), "NGƯỜI CHƠI", fill=(100, 110, 140, 255), font=font_small)
    draw.text((72, 94), f"@{username}", fill=(255, 255, 255, 255), font=font_bold_medium)
    
    # Bet amount pill on right
    bet_str = f"{bet_amount:,} VNĐ"
    try:
        bet_w = font_bold_medium.getlength(bet_str)
    except AttributeError:
        bet_w = len(bet_str) * 6
    pill_w = max(90, int(bet_w) + 20)
    bx1 = 575 - pill_w
    bx2 = 575
    draw.rounded_rectangle([bx1, 83, bx2, 107], radius=4, fill=(13, 50, 27, 255), outline=(34, 197, 94, 255), width=1)
    draw.text((bx1 + pill_w/2, 95), bet_str, fill=(34, 197, 94, 255), font=font_bold_medium, anchor="mm")
    
    # Selection Label
    draw.text((25, 137), "ĐÃ CHỌN", fill=(100, 110, 140, 255), font=font_bold_small)
    
    color_labels = {
        "blue": ("Xanh dương • x2", (91, 140, 255, 255)),
        "green": ("Xanh lá • x3", (34, 197, 94, 255)),
        "yellow": ("Vàng • x5", (234, 179, 8, 255)),
        "red": ("Đỏ • x10", (239, 68, 68, 255))
    }
    
    sel_text, sel_col = color_labels[chosen_color]
    # Draw selection highlight pill
    draw.rounded_rectangle([95, 131, 235, 153], radius=4, fill=(20, 25, 45, 255), outline=sel_col, width=1)
    # Draw solid dot inside pill
    draw.ellipse([103, 138, 111, 146], fill=sel_col)
    # Draw text
    draw.text((118, 142), sel_text, fill=sel_col, font=font_bold_medium, anchor="lm")
    
    # Grid bet options
    options = [
        ("blue", "Xanh dương", "x2", "40% - thắng", (91, 140, 255, 255), (20, 30, 60, 255)),
        ("green", "Xanh lá", "x3", "33% - thắng", (34, 197, 94, 255), (10, 45, 25, 255)),
        ("yellow", "Vàng", "x5", "20% - thắng", (234, 179, 8, 255), (45, 35, 10, 255)),
        ("red", "Đỏ", "x10", "7% - thắng", (239, 68, 68, 255), (45, 15, 15, 255))
    ]
    
    coords = [
        (25, 168, 290, 238),
        (310, 168, 575, 238),
        (25, 248, 290, 318),
        (310, 248, 575, 318)
    ]
    
    for idx, opt in enumerate(options):
        key, label, mult, pct_label, txt_color, bg_selected = opt
        cx1, cy1, cx2, cy2 = coords[idx]
        
        is_selected = (key == chosen_color)
        payout_val = bet_amount * int(mult[1:])
        payout_str = f"{pct_label} {payout_val:,}"
        
        if is_selected:
            draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=6, fill=bg_selected, outline=txt_color, width=2)
            # CHỌN label with custom vector checkmark
            draw.text((cx2 - 50, cy1 + 15), "CHỌN", fill=txt_color, font=font_bold_small, anchor="rt")
            chk_x = cx2 - 47
            draw.line([(chk_x, 11 + cy1), (chk_x + 3, 14 + cy1), (chk_x + 8, 8 + cy1)], fill=txt_color, width=2)
        else:
            draw.rounded_rectangle([cx1, cy1, cx2, cy2], radius=6, fill=(21, 24, 36, 255), outline=(35, 40, 55, 255), width=1)
            
        # Draw solid circle natively
        draw.ellipse([cx1 + 15, cy1 + 25, cx1 + 31, cy1 + 41], fill=txt_color)
        draw.text((cx1 + 45, cy1 + 22), label, fill=(255, 255, 255, 255) if is_selected else (140, 150, 175, 255), font=font_regular_medium, anchor="lm")
        draw.text((cx1 + 45, cy1 + 40), mult, fill=txt_color, font=font_title, anchor="lm")
        draw.text((cx1 + 45, cy1 + 58), payout_str, fill=txt_color if is_selected else (100, 110, 130, 255), font=font_small, anchor="lm")
        
    draw.line([25, 332, 575, 332], fill=(35, 40, 55, 255), width=1)
    
    # Footer bulb logo
    draw.ellipse([27, 345, 37, 355], fill=(234, 179, 8, 255))
    draw.line([32, 354, 32, 358], fill=(234, 179, 8, 255), width=2)
    draw.text((45, 347), "Nhấn Quay ngay! để bắt đầu. Kết quả sẽ hiện sau khi vòng quay dừng lại.", fill=(100, 110, 135, 255), font=font_small)
    
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out

def render_result_image(username: str, avatar_img: Image.Image, bet_amount: int, chosen_color: str, result_color: str, payout: int, profit: int, is_win: bool) -> BytesIO:
    width = 600
    height = 380
    
    # Fonts
    font_title = load_font("bold", 18)
    font_subtitle = load_font("regular", 11)
    font_bold_medium = load_font("bold", 12)
    font_regular_medium = load_font("regular", 11)
    font_small = load_font("regular", 9)
    font_bold_small = load_font("bold", 9)
    font_big = load_font("bold", 14)
    
    img = Image.new("RGBA", (width, height), (21, 24, 36, 255))
    draw = ImageDraw.Draw(img)
    
    # Header Logo
    draw.rounded_rectangle([25, 20, 60, 55], radius=6, fill=(200, 168, 75, 255))
    draw_ferris_wheel_logo(draw, 25, 20, 60, 55)
    
    draw.text((75, 20), "VÒNG QUAY MAY MẮN", fill=(200, 168, 75, 255), font=font_title)
    draw.text((75, 43), "Color Wheel Betting", fill=(100, 110, 140, 255), font=font_subtitle)
    
    # Status pill: THẮNG / THUA
    if is_win:
        draw.rounded_rectangle([480, 24, 575, 50], radius=4, fill=(13, 50, 27, 255), outline=(34, 197, 94, 255), width=1)
        draw.text((527, 37), "THẮNG", fill=(34, 197, 94, 255), font=font_bold_small, anchor="mm")
    else:
        draw.rounded_rectangle([480, 24, 575, 50], radius=4, fill=(50, 13, 13, 255), outline=(239, 68, 68, 255), width=1)
        draw.text((527, 37), "THUA", fill=(239, 68, 68, 255), font=font_bold_small, anchor="mm")
        
    draw.line([25, 70, 575, 70], fill=(35, 40, 55, 255), width=1)
    
    # Profile Y=80
    avatar_resized = make_circular(avatar_img, (36, 36))
    img.paste(avatar_resized, (25, 80), avatar_resized)
    
    draw.text((72, 82), "NGƯỜI CHƠI", fill=(100, 110, 140, 255), font=font_small)
    draw.text((72, 94), f"@{username}", fill=(255, 255, 255, 255), font=font_bold_medium)
    
    # Payout indicator pill
    payout_str = f"{payout:,} VNĐ"
    try:
        payout_w = font_bold_medium.getlength(payout_str)
    except AttributeError:
        payout_w = len(payout_str) * 6
    pill_w = max(90, int(payout_w) + 20)
    bx1 = 575 - pill_w
    bx2 = 575
    
    pill_bg = (13, 50, 27, 255) if is_win else (30, 35, 50, 255)
    pill_border = (34, 197, 94, 255) if is_win else (100, 110, 135, 255)
    pill_text_color = (34, 197, 94, 255) if is_win else (255, 255, 255, 255)
    
    draw.rounded_rectangle([bx1, 83, bx2, 107], radius=4, fill=pill_bg, outline=pill_border, width=1)
    draw.text((bx1 + pill_w/2, 95), payout_str, fill=pill_text_color, font=font_bold_medium, anchor="mm")
    
    draw.line([25, 125, 575, 125], fill=(35, 40, 55, 255), width=1)
    
    # Choice comparison
    draw.text((25, 135), "ĐÃ CHỌN", fill=(100, 110, 140, 255), font=font_small)
    draw.text((310, 135), "KẾT QUẢ VÒNG QUAY", fill=(100, 110, 140, 255), font=font_small)
    
    color_names = { "blue": "Xanh dương", "green": "Xanh lá", "yellow": "Vàng", "red": "Đỏ" }
    color_mults = { "blue": "x2", "green": "x3", "yellow": "x5", "red": "x10" }
    color_rgb = {
        "blue": (91, 140, 255, 255),
        "green": (34, 197, 94, 255),
        "yellow": (234, 179, 8, 255),
        "red": (239, 68, 68, 255)
    }
    
    chosen_name = color_names[chosen_color]
    chosen_mult = color_mults[chosen_color]
    chosen_col = color_rgb[chosen_color]
    
    result_name = color_names[result_color]
    result_mult = color_mults[result_color]
    result_col = color_rgb[result_color]
    
    # Drawn chosen pill circle + label
    draw.ellipse([25, 153, 37, 165], fill=chosen_col)
    draw.text((45, 159), f"{chosen_name} • {chosen_mult}", fill=chosen_col, font=font_big, anchor="lm")
    
    # Drawn result pill circle + label
    draw.ellipse([310, 153, 322, 165], fill=result_col)
    draw.text((330, 159), f"{result_name} • {result_mult}", fill=result_col, font=font_big, anchor="lm")
    
    # Draw checkmark/cross vector lines
    txt_w = font_big.getlength(f"{result_name} • {result_mult}")
    chk_x = 330 + txt_w + 10
    if is_win:
        draw.line([(chk_x, 157), (chk_x + 3, 161), (chk_x + 8, 151)], fill=(34, 197, 94, 255), width=2)
    else:
        draw.line([(chk_x, 153), (chk_x + 8, 161)], fill=(239, 68, 68, 255), width=2)
        draw.line([(chk_x, 161), (chk_x + 8, 153)], fill=(239, 68, 68, 255), width=2)
        
    # Highlight banner Y=190
    banner_bg = (13, 50, 27, 255) if is_win else (50, 13, 13, 255)
    banner_border = (34, 197, 94, 255) if is_win else (239, 68, 68, 255)
    banner_text = f"Vòng quay dừng tại {result_name.upper()} ({result_mult})"
    banner_sub = "Chúc mừng! Bạn đoán đúng màu ván này." if is_win else "Chúc bạn may mắn lần sau!"
    
    draw.rounded_rectangle([25, 190, 575, 250], radius=6, fill=banner_bg, outline=banner_border, width=1)
    
    # Checkmark/cross icon box vector lines
    draw.rounded_rectangle([40, 202, 70, 238], radius=4, fill=banner_border)
    if is_win:
        draw.line([(48, 220), (53, 226), (63, 212)], fill=(255, 255, 255, 255), width=3)
    else:
        draw.line([(48, 212), (62, 228)], fill=(255, 255, 255, 255), width=3)
        draw.line([(48, 228), (62, 212)], fill=(255, 255, 255, 255), width=3)
        
    draw.text((85, 208), banner_text, fill=(255, 255, 255, 255), font=font_big, anchor="lm")
    draw.text((85, 232), banner_sub, fill=(180, 230, 200, 255) if is_win else (240, 180, 180, 255), font=font_subtitle, anchor="lm")
    
    # Summary Grid Y=265
    draw.rounded_rectangle([25, 265, 575, 345], radius=6, fill=(18, 20, 30, 255), outline=(35, 40, 55, 255), width=1)
    draw.line([208, 265, 208, 345], fill=(35, 40, 55, 255), width=1)
    draw.line([392, 265, 392, 345], fill=(35, 40, 55, 255), width=1)
    
    draw.text((116, 282), "TIỀN CƯỢC", fill=(100, 110, 140, 255), font=font_bold_small, anchor="mm")
    draw.text((300, 282), "NHẬN VỀ", fill=(100, 110, 140, 255), font=font_bold_small, anchor="mm")
    draw.text((483, 282), "LỢI NHUẬN", fill=(100, 110, 140, 255), font=font_bold_small, anchor="mm")
    
    profit_sign = "+" if profit >= 0 else ""
    profit_col = (34, 197, 94, 255) if profit >= 0 else (239, 68, 68, 255)
    
    draw.text((116, 315), f"{bet_amount:,}", fill=(255, 255, 255, 255), font=font_big, anchor="mm")
    draw.text((300, 315), f"{payout:,}", fill=(34, 197, 94, 255) if is_win else (140, 140, 140, 255), font=font_big, anchor="mm")
    draw.text((483, 315), f"{profit_sign}{profit:,}", fill=profit_col, font=font_big, anchor="mm")
    
    out = BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


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

class ColorWheelSelectionView(discord.ui.View):
    def __init__(self, cog: "Quay", ctx: commands.Context, bet_amount: int):
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
        await interaction.response.defer()
        self.chosen_color = color
        self.update_button_styles()
        
        # Render the updated lobby PNG
        avatar_img = await self.cog.get_avatar_img(self.ctx.author)
        lobby_buf = render_lobby_image(self.ctx.author.display_name, avatar_img, self.bet_amount, self.chosen_color)
        file = discord.File(lobby_buf, filename="lobby.png")
        
        embed = self.cog.format_confirm_embed()
        embed.set_image(url="attachment://lobby.png")
        
        await self.message.edit(embed=embed, attachments=[file], view=self)

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
        await interaction.response.defer()
        self.clicked = True
        self.stop()
        await self.cog.run_spin(self.ctx, self.bet_amount, self.chosen_color, self.message)

    @discord.ui.button(label="Hủy", style=discord.ButtonStyle.danger, emoji="❌", row=1)
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.clicked = True
        self.stop()
        self.cog.active_players.discard(self.ctx.author.id)
        
        embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN",
            description=f"❌ **{self.ctx.author.mention} đã hủy lượt quay.**",
        )
        await self.message.edit(embed=embed, attachments=[], view=None)

    async def on_timeout(self):
        if not self.clicked:
            self.stop()
            self.cog.active_players.discard(self.ctx.author.id)
            embed = CasinoEmbed(
                title="🎡 VÒNG QUAY MAY MẮN",
                description=f"⏱️ **Đã hết thời gian xác nhận. Lượt quay bị hủy.**",
            )
            try:
                await self.message.edit(embed=embed, attachments=[], view=None)
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

    async def get_avatar_img(self, user: discord.User) -> Image.Image:
        avatar_url = user.display_avatar.url
        try:
            avatar_bytes = await fetch_avatar(avatar_url)
            if avatar_bytes:
                return Image.open(BytesIO(avatar_bytes)).convert("RGBA")
        except Exception as e:
            logger.error(f"Failed to fetch avatar: {e}")
            
        # Fallback card circular avatar
        avatar_img = Image.new("RGBA", (40, 40), (88, 101, 242, 255))
        draw = ImageDraw.Draw(avatar_img)
        draw.text((20, 20), user.display_name[0].upper(), fill=(255, 255, 255, 255), anchor="mm")
        return avatar_img

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
        if user_id in self.active_players:
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
        self.active_players.add(user_id)
        
        # Render the initial lobby card PNG
        avatar_img = await self.get_avatar_img(ctx.author)
        lobby_buf = render_lobby_image(ctx.author.display_name, avatar_img, bet_amount, "blue")
        file = discord.File(lobby_buf, filename="lobby.png")
        
        # Build selection embed
        embed = self.format_confirm_embed()
        embed.set_image(url="attachment://lobby.png")
        
        view = ColorWheelSelectionView(self, ctx, bet_amount)
        view.message = await ctx.send(embed=embed, file=file, view=view)

    def format_confirm_embed(self) -> CasinoEmbed:
        embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN"
        )
        embed.set_footer(text="Chọn màu sắc cược ở dưới rồi nhấn 'Quay ngay!'")
        return embed

    async def run_spin(self, ctx: commands.Context, bet_amount: int, chosen_color: str, message: discord.Message):
        user_id = ctx.author.id
        guild_id = ctx.guild.id if ctx.guild else 0
        
        # Double check money
        current_money = self.economy.get_entry(user_id)[1]
        if current_money < bet_amount:
            self.active_players.discard(user_id)
            await message.edit(content="❌ Bạn không đủ tiền trong ví để quay!", embed=None, attachments=[], view=None)
            return
            
        # Deduct wallet
        self.economy.add_money(user_id, -bet_amount)
        log_wallet_change(logger, event="color_wheel_bet", user_id=user_id, money_delta=-bet_amount, ctx=ctx)
        
        # Random spin slot
        win_idx = random.randint(0, 29)
        result_color = WHEEL_LAYOUT[win_idx]
        
        # Generate spin GIF and static result PNG in memory using Pillow (similar to Plinko cog)
        try:
            gif_buffer, png_buffer = render_wheel_gif(win_idx)
            gif_file = discord.File(gif_buffer, filename="wheel_spin.gif")
            png_file = discord.File(png_buffer, filename="wheel_result.png")
        except Exception as e:
            logger.error(f"Pillow GIF generation failed: {e}", exc_info=True)
            # Refund
            self.economy.add_money(user_id, bet_amount)
            log_wallet_change(logger, event="color_wheel_error_refund", user_id=user_id, money_delta=bet_amount, ctx=ctx)
            self.active_players.discard(user_id)
            await message.edit(content="❌ Đã xảy ra lỗi khi tạo hiệu ứng vòng quay.", embed=None, attachments=[], view=None)
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

        # Render custom results dashboard card PNG
        avatar_img = await self.get_avatar_img(ctx.author)
        result_buf = render_result_image(ctx.author.display_name, avatar_img, bet_amount, chosen_color, result_color, payout, profit, is_win)
        result_file = discord.File(result_buf, filename="result.png")
        
        # Formulate final embed
        now = datetime.now()
        am_pm = "SA" if now.hour < 12 else "CH"
        hour = now.hour if now.hour <= 12 else now.hour - 12
        if hour == 0:
            hour = 12
        footer_text = f"Sylus Meow • {now.strftime('%d/%m/%Y')} {hour:02d}:{now.strftime('%M')} {am_pm}"
        
        final_embed = CasinoEmbed(
            title="🎡 VÒNG QUAY MAY MẮN"
        )
        final_embed.set_image(url="attachment://result.png")
        final_embed.set_thumbnail(url="attachment://wheel_result.png")
        final_embed.set_footer(text=footer_text)
        
        # Edit the message to show final results card and attach static final wheel image as thumbnail
        try:
            await message.edit(embed=final_embed, attachments=[result_file, png_file])
        except Exception:
            # Fallback if attachments cannot be edited easily
            await message.delete()
            await ctx.send(files=[result_file, png_file], embed=final_embed)
            
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
            await ctx.send("❌ **Sử dụng sai cú pháp!** Cú pháp: `/quay [tiền_cược]`", ephemeral=True)
            return True
            
        # Propagate other errors
        return False

async def setup(bot: commands.Bot):
    await bot.add_cog(Quay(bot))
