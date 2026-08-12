"""
Pillow Renderer for Tu Tien Profile Card (PNG/GIF Kunst style).
Renders 18 attributes, spiritual roots, progress bars, cultivator badges, and VIP Glowing Gold Frames.
"""

import os
import io
import math
from typing import Optional
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from app.discord_bot.modules.tutien.models import CultivatorProfile

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "..", ".."))
FONT_PATH = os.path.join(PROJECT_ROOT, "test.ttf")


def get_font(size: int, is_bold: bool = False) -> ImageFont.FreeTypeFont:
    """
    Attempts to load fonts with full Vietnamese unicode diacritics support.
    Falls back to Windows fonts (Segoe UI, Arial, Calibri, Tahoma) or Linux fonts (DejaVu Sans).
    """
    fallbacks = []
    if os.name == 'nt':  # Windows
        if is_bold:
            fallbacks.extend([
                "segoeuib.ttf", "arialbd.ttf", "calibrib.ttf", "tahomabd.ttf",
                "C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf",
                "C:/Windows/Fonts/calibrib.ttf"
            ])
        else:
            fallbacks.extend([
                "segoeui.ttf", "arial.ttf", "calibri.ttf", "tahoma.ttf",
                "C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf",
                "C:/Windows/Fonts/calibri.ttf"
            ])
    else:  # Linux/Mac
        if is_bold:
            fallbacks.extend([
                "DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf"
            ])
        else:
            fallbacks.extend([
                "DejaVuSans.ttf", "LiberationSans-Regular.ttf", "FreeSans.ttf",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf"
            ])

    for f in fallbacks:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            pass

    return ImageFont.load_default()


def draw_rounded_rect(draw: ImageDraw.ImageDraw, coords, radius: int, fill, outline=None, width=1):
    draw.rounded_rectangle(coords, radius=radius, fill=fill, outline=outline, width=width)


def draw_progress_bar(
    draw: ImageDraw.ImageDraw,
    x: int, y: int, width: int, height: int,
    percent: float,
    fill_color: tuple,
    bg_color: tuple = (30, 35, 45, 255),
    border_color: tuple = (80, 90, 110, 255)
):
    percent = max(0.0, min(1.0, percent))
    draw_rounded_rect(draw, (x, y, x + width, y + height), radius=height // 2, fill=bg_color, outline=border_color, width=1)
    fill_w = int(width * percent)
    if fill_w > 4:
        draw_rounded_rect(draw, (x + 1, y + 1, x + fill_w - 1, y + height - 1), radius=(height - 2) // 2, fill=fill_color)


def render_tutien_profile_card(player: CultivatorProfile, avatar_bytes: Optional[bytes] = None) -> io.BytesIO:
    """
    Renders a 900x580 PNG Profile Card featuring 18 Attributes & Xianxia Aesthetic.
    If player is VIP or has Monthly Pass, renders a Gold Glowing Border & VIP Crown Badge.
    """
    WIDTH, HEIGHT = 900, 580
    is_vip = player.vip_level > 0 or player.is_vip_pass
    
    # 1. Base Canvas & Background Artwork
    bg_color = (18, 16, 28, 255) if is_vip else (12, 14, 22, 255)
    img = Image.new("RGBA", (WIDTH, HEIGHT), bg_color)
    
    # Check for dynamic background image based on realm
    bg_path = "pictures/bg_tiende.jpg" if player.realm_index >= 20 else ("pictures/bg_kimdan.jpg" if player.realm_index >= 10 else None)
    if bg_path and os.path.exists(bg_path):
        try:
            bg_img = Image.open(bg_path).convert("RGBA").resize((WIDTH, HEIGHT))
            # Blend with dark overlay for readability
            dark_overlay = Image.new("RGBA", (WIDTH, HEIGHT), (12, 14, 22, 180))
            bg_img = Image.alpha_composite(bg_img, dark_overlay)
            img.paste(bg_img, (0, 0))
        except Exception:
            pass

    draw = ImageDraw.Draw(img)

    # Glowing Outer Border (Gold for VIP, Dark Steel for F2P)
    border_color = (255, 215, 0, 255) if is_vip else (180, 140, 60, 255)
    border_w = 3 if is_vip else 2
    draw_rounded_rect(draw, (10, 10, WIDTH - 10, HEIGHT - 10), radius=16, fill=(18, 22, 34, 255), outline=border_color, width=border_w)
    draw_rounded_rect(draw, (16, 16, WIDTH - 16, HEIGHT - 16), radius=12, fill=(24, 28, 42, 255), outline=(60, 70, 95, 255), width=1)

    # Fonts
    font_title = get_font(26, is_bold=True)
    font_header = get_font(20, is_bold=True)
    font_bold = get_font(16, is_bold=True)
    font_regular = get_font(14, is_bold=False)
    font_small = get_font(12, is_bold=False)

    # 2. Header Panel
    title_text = "☯ THÔNG TIN TU SĨ ☯"
    if is_vip:
        vip_tag = f" [ 👑 VIP {player.vip_level} ]" if player.vip_level > 0 else " [ 📜 ĐẠO TÂM TÔN GIẢ ]"
        title_text += vip_tag

    draw.text((WIDTH // 2, 35), title_text, font=font_title, fill=(255, 215, 0, 255) if is_vip else (235, 195, 95, 255), anchor="mm")
    draw.line([(40, 60), (WIDTH - 40, 60)], fill=(210, 165, 75, 255) if is_vip else (120, 95, 45, 255), width=1)

    # 3. Avatar Box
    av_x, av_y, av_size = 40, 80, 110
    av_border = (255, 215, 0, 255) if is_vip else (210, 165, 75, 255)
    draw_rounded_rect(draw, (av_x - 3, av_y - 3, av_x + av_size + 3, av_y + av_size + 3), radius=10, fill=(35, 40, 55, 255), outline=av_border, width=2)

    if avatar_bytes:
        try:
            av_img = Image.open(io.BytesIO(avatar_bytes)).convert("RGBA")
            av_img = av_img.resize((av_size, av_size))
            img.paste(av_img, (av_x, av_y), av_img)
        except Exception:
            draw.text((av_x + av_size // 2, av_y + av_size // 2), "☯", font=font_title, fill=(200, 200, 200, 255), anchor="mm")
    else:
        draw.text((av_x + av_size // 2, av_y + av_size // 2), "☯", font=font_title, fill=(200, 200, 200, 255), anchor="mm")

    # 4. Basic Info
    info_x = av_x + av_size + 25
    draw.text((info_x, 82), f"Đạo Hiệu : {player.dao_hieu}", font=font_bold, fill=(255, 255, 255, 255))
    sect_str = player.sect_name if player.sect_name else "Tự Tu (Vô Tông Môn)"
    draw.text((info_x + 360, 82), f"Tông Môn: {sect_str}", font=font_regular, fill=(180, 200, 220, 255))

    draw.text((info_x, 112), f"Cảnh Giới: 🔵 {player.realm_name}", font=font_bold, fill=(100, 200, 255, 255))
    draw.text((info_x + 360, 112), f"Luyện Thể: 💪 {player.body_realm_name}", font=font_regular, fill=(255, 180, 120, 255))

    # Exp Bar
    exp_percent = player.exp / float(player.required_exp) if player.required_exp > 0 else 1.0
    draw.text((info_x, 142), "Tu Vi:", font=font_small, fill=(200, 200, 200, 255))
    draw_progress_bar(draw, info_x + 50, 144, 420, 16, exp_percent, fill_color=(75, 180, 245, 255))
    draw.text((info_x + 480, 142), f"{exp_percent * 100:.1f}% ({player.exp:,} / {player.required_exp:,})", font=font_small, fill=(180, 220, 255, 255))

    draw.line([(40, 205), (WIDTH - 40, 205)], fill=(50, 60, 80, 255), width=1)

    # 5. Core 18 Attributes Section Grid
    grid_y = 220

    # Column 1
    draw.text((40, grid_y), f"⚡ Linh Căn: {player.linh_can_element} ({player.linh_can_quality})", font=font_bold, fill=(255, 215, 0, 255))
    
    # Căn Cơ
    draw.text((40, grid_y + 35), f"🛡️ Căn Cơ: {player.can_co:.0f}%", font=font_regular, fill=(220, 220, 220, 255))
    draw_progress_bar(draw, 160, grid_y + 37, 220, 14, player.can_co / 100.0, fill_color=(100, 210, 120, 255))

    # Tâm Cảnh
    draw.text((40, grid_y + 65), f"🧘 Tâm Cảnh: {player.tam_canh:.0f}%", font=font_regular, fill=(220, 220, 220, 255))
    draw_progress_bar(draw, 160, grid_y + 67, 220, 14, player.tam_canh / 100.0, fill_color=(140, 120, 240, 255))

    # Đạo Tâm & Ngộ Tính
    draw.text((40, grid_y + 95), f"⚔️ Đạo Tâm: {player.dao_tam} điểm", font=font_regular, fill=(240, 140, 100, 255))
    draw.text((40, grid_y + 125), f"🧠 Ngộ Tính: {player.ngo_tinh} điểm", font=font_regular, fill=(130, 210, 255, 255))

    # HP / Mana
    draw.text((40, grid_y + 155), f"❤️ Khí Huyết (HP): {player.hp:,} / {player.max_hp:,}", font=font_regular, fill=(255, 100, 100, 255))
    draw.text((40, grid_y + 185), f"💧 Chân Nguyên (MP): {player.mana:,} / {player.max_mana:,}", font=font_regular, fill=(100, 180, 255, 255))

    # Column 2
    col2_x = 470

    # Thần Thức & Tinh Lực
    draw.text((col2_x, grid_y + 35), f"🧬 Thần Thức: {player.than_thuc} Điểm", font=font_regular, fill=(200, 160, 255, 255))
    
    # Tinh lực (Stamina)
    draw.text((col2_x, grid_y + 65), f"🔥 Tinh Lực: {player.tinh_luc} / {player.max_tinh_luc}", font=font_regular, fill=(255, 160, 80, 255))
    draw_progress_bar(draw, col2_x + 150, grid_y + 67, 200, 14, player.tinh_luc / float(player.max_tinh_luc), fill_color=(255, 140, 50, 255))

    # Nghiệp Lực
    karma_status = "Chính Đạo" if player.nghiep_luc <= 20 else ("Tà Đạo" if player.nghiep_luc <= 50 else "Ma Tu")
    karma_color = (120, 220, 120, 255) if player.nghiep_luc <= 20 else (255, 80, 80, 255)
    draw.text((col2_x, grid_y + 95), f"☯ Nghiệp Lực: {player.nghiep_luc} ({karma_status})", font=font_regular, fill=karma_color)

    # Cơ Duyên & Thiên Đạo Điểm
    draw.text((col2_x, grid_y + 125), f"✨ Cơ Duyên: {player.co_duyen} Điểm", font=font_regular, fill=(255, 225, 120, 255))
    draw.text((col2_x, grid_y + 155), f"🌌 Thiên Đạo Điểm: {player.thien_dao_diem:,} Điểm", font=font_regular, fill=(180, 220, 255, 255))

    # Two Currencies (Linh Thạch & Tiên Ngọc)
    draw.text((col2_x, grid_y + 185), f"💎 Linh Thạch: {player.linh_thach:,}  |  🌟 Tiên Ngọc: {player.tien_ngoc:,}", font=font_bold, fill=(255, 215, 0, 255))

    # Footer Info (Gongfa, Dongphu)
    draw.line([(40, 520), (WIDTH - 40, 520)], fill=(50, 60, 80, 255), width=1)
    gongfa_name = player.active_dao_domain if player.active_dao_domain else "《Phàm Nhân Quyết》"
    draw.text((40, 535), f"📜 Công Pháp Chủ Tu: {gongfa_name}", font=font_small, fill=(220, 220, 180, 255))
    draw.text((WIDTH - 40, 535), f"🏠 Động Phủ: Cấp {player.dong_phu_level} (Linh Khí +{player.dong_phu_level * 15}%)", font=font_small, fill=(180, 220, 180, 255), anchor="rm")

    output = io.BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    return output
