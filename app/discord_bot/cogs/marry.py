import asyncio
from io import BytesIO
import logging
import random
import time
from datetime import datetime
import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont, ImageChops
import requests

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, ABS_PATH
from app.discord_bot.modules.profile_renderer import load_font
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# List of wedding rings mapping
RINGS = {
    "ring_grass": "Nhẫn Cỏ 🌾",
    "ring_quartz": "Nhẫn Thạch Anh Trắng 💍",
    "ring_aquamarine": "Nhẫn Sương Mai Aquamarine 💧",
    "ring_emerald": "Nhẫn Thanh Xuân Lục Bảo 🌿",
    "ring_amethyst": "Nhẫn Trăng Khuyết Amethyst 🌙",
    "ring_cupid": "Nhẫn Tình Yêu Cupid 💘",
    "ring_citrine": "Nhẫn Vương Miện Citrine 👑",
    "ring_ruby": "Nhẫn Hồng Ngọc Bách Hợp 🌹",
    "ring_sapphire": "Nhẫn Lam Ngọc Tinh Tú ✨",
    "ring_sunburst": "Nhẫn Nhật Quang Thái Dương ☀️",
    "ring_gothic": "Nhẫn Hắc Dạ Gothic 🖤",
    "ring_angel": "Nhẫn Cánh Thần Sapphire 👼",
    "ring_divine": "Nhẫn Hào Quang Vĩnh Cửu 🌌",
    "ring_eternal_butterfly": "Nhẫn Song Điệp Vĩnh Hằng 🦋",
    "ring_nhankat": "Nhẫn Kat 🌸"
}

RING_IMAGES = {
    "ring_grass": "Nhẫn Cỏ.png",
    "ring_quartz": "Nhẫn Thạch Anh Trắng.png",
    "ring_aquamarine": "Nhẫn Sương Mai Aquamarine.png",
    "ring_emerald": "Nhẫn Thanh Xuân Lục Bảo.png",
    "ring_amethyst": "Nhẫn Trăng Khuyết Amethyst.png",
    "ring_cupid": "Nhẫn Tình Yêu Cupid.png",
    "ring_citrine": "Nhẫn Vương Miện Citrine.png",
    "ring_ruby": "Nhẫn Hồng Ngọc Bách Hợp.png",
    "ring_sapphire": "Nhẫn Lam Ngọc Tinh Tú.png",
    "ring_sunburst": "Nhẫn Nhật Quang Thái Dương.png",
    "ring_gothic": "Nhẫn Hắc Dạ.png",
    "ring_angel": "Nhẫn Cánh Thần Sapphire.png",
    "ring_divine": "Nhẫn Hào Quang Vĩnh Cửu.png",
    "ring_eternal_butterfly": "Nhan_sal.png",
    "ring_nhankat": "NhanKat.png"
}

# Couple Assets Dictionaries
COUPLE_ESTATES = {
    "estate_apartment":     {"name": "<:cozyhouse:1529904984311857192> Căn Hộ Ấm Cúng",           "price": 30,              "buff": 6},
    "estate_villa":         {"name": "<:modernluxuryvillawithpool:1529905019498004510> Biệt Thự Vườn",             "price": 50,             "buff": 15},
    "estate_beach":         {"name": "<:beachresort:1529905154214727830>Nhà Biển Thiên Đường",     "price": 80,             "buff": 20},
    "estate_penthouse":     {"name": "<:penhouse:1529905033900982273> Penthouse Sky View",         "price": 120,             "buff": 28},
    "estate_island":        {"name": "<:tropicalisland:1529905080730648667> Đảo Riêng Tư",             "price": 200,            "buff": 38},
    "estate_palace":        {"name": "<:palacehouse:1529905194672984064> Cung Điện Hoàng Gia",       "price": 400,            "buff": 50},
    "estate_sky_castle":    {"name": "<:cloudcastle:1529905210779242566> Lâu Đài Trên Mây",          "price": 1_000,          "buff": 70},
    "estate_space_station": {"name": "<:spaceshiphouse:1529905224356073613> Trạm Vũ Trụ Tình Yêu",     "price": 5_000,          "buff": 100},
}

COUPLE_VEHICLES = {
    "vehicle_scooter":   {"name": "<:Scooter:1529908359988514847> Xe Máy Đôi",          "price": 9,              "buff": 2},
    "vehicle_car":       {"name": "<:romanticcar:1529908376262410300> Ô Tô Lãng Mạn",       "price": 19,              "buff": 5},
    "vehicle_suv":       {"name": "<:SUV:1529908436437958666> SUV Gia Đình",         "price": 49,              "buff": 9},
    "vehicle_limo":      {"name": "<:limousine:1529908452661395536> Limousine Sang Trọng", "price": 89,             "buff": 14},
    "vehicle_supercar":  {"name": "<:supercar:1529908470751690822> Siêu Xe Thể Thao",   "price": 149,             "buff": 20},
    "vehicle_yacht":     {"name": "<:boatpng:1529908484546498802> Du Thuyền Tình Yêu",  "price": 349,            "buff": 28},
    "vehicle_jet":       {"name": "<:plane:1529914731962433548> Phi Cơ Riêng",        "price": 599,            "buff": 38},
    "vehicle_spaceship": {"name": "<:spaceshipremovebgpreview:1529914772500381917> Phi Thuyền Vũ Trụ",   "price": 1_999,          "buff": 55},
}

COUPLE_PETS = {
    "pet_hamster":  {"name": "<:cute_hamster:1529906150756061274> Hamster Đôi",          "price": 2,              "buff": 1},
    "pet_cat":      {"name": "<:cute_cat:1529906168556818432> Mèo Anh Lông Dài",     "price": 15,              "buff": 4},
    "pet_dog":      {"name": "<:cute_corgi:1529906218100064397> Shiba Inu Ngốc Nghếch","price": 39,              "buff": 8},
    "pet_capybara": {"name": "<:capybara:1529907688274661518> Capybara Thân Thiện",  "price": 64,             "buff": 12},
    "pet_fox":      {"name": "<:arctic_fox:1529907673494192200> Cáo Tuyết Đô Thị",     "price": 84,            "buff": 25},
    "pet_dragon":   {"name": "<:fantasy_dragon:1529907944089583717> Rồng Linh Thú Cổ Đại", "price": 104,            "buff": 35},
    "pet_phoenix":  {"name": "<:phoenix:1529907955657343117> Phượng Hoàng Băng Tuyết","price": 149,          "buff": 50},
    "pet_unicorn":  {"name": "<:unicorn:1529907967535612087> Kỳ Lân Tinh Tú",      "price": 499,          "buff": 80},
}

ESTATE_IMAGES = {
    "estate_apartment": "cozyhouse.png",
    "estate_villa": "modern luxury villa with pool.png",
    "estate_beach": "beachresort.png",
    "estate_penthouse": "penhouse.png",
    "estate_island": "tropicalisland.png",
    "estate_palace": "palace-house.png",
    "estate_sky_castle": "cloudcastle.png",
    "estate_space_station": "spaceship.png"
}

VEHICLE_IMAGES = {
    "vehicle_scooter": "Scooter.png",
    "vehicle_car": "romanticcar.png",
    "vehicle_suv": "SUV.png",
    "vehicle_limo": "limousine.png",
    "vehicle_supercar": "supercar.png",
    "vehicle_yacht": "boat-png.png",
    "vehicle_jet": "plane.png",
    "vehicle_spaceship": "spaceship-removebg-preview.png"
}

PET_IMAGES = {
    "pet_hamster": "cute_hamster.png",
    "pet_cat": "cute_cat.png",
    "pet_dog": "cute_corgi.png",
    "pet_capybara": "capybara.png",
    "pet_fox": "arctic_fox.png",
    "pet_dragon": "fantasy_dragon.png",
    "pet_phoenix": "phoenix.png",
    "pet_unicorn": "unicorn.png"
}


def refund_couple_assets_on_divorce(economy: Economy, user_one: int, user_two: int) -> str:
    """Refunds 25% of purchased estate, vehicle, and pet prices to original buyers upon divorce."""
    assets = economy.get_couple_assets(user_one, user_two)
    if not assets:
        return ""
    
    estate_id, estate_price, estate_bought_by, vehicle_id, vehicle_price, vehicle_bought_by, pet_id, pet_price, pet_bought_by = assets
    refund_messages = []
    
    if estate_id and estate_price > 0 and estate_bought_by > 0:
        estate_refund = int(estate_price * 0.25)
        if estate_refund > 0:
            economy.add_credits(estate_bought_by, estate_refund)
            estate_name = COUPLE_ESTATES.get(estate_id, {}).get("name", estate_id)
            refund_messages.append(f"🏠 **{estate_name}:** Hoàn trả 25% (`+{estate_refund:,} Thỏi Vàng`) cho <@{estate_bought_by}>")
            
    if vehicle_id and vehicle_price > 0 and vehicle_bought_by > 0:
        vehicle_refund = int(vehicle_price * 0.25)
        if vehicle_refund > 0:
            economy.add_credits(vehicle_bought_by, vehicle_refund)
            vehicle_name = COUPLE_VEHICLES.get(vehicle_id, {}).get("name", vehicle_id)
            refund_messages.append(f"🚗 **{vehicle_name}:** Hoàn trả 25% (`+{vehicle_refund:,} Thỏi Vàng`) cho <@{vehicle_bought_by}>")

    if pet_id and pet_price > 0 and pet_bought_by > 0:
        pet_refund = int(pet_price * 0.25)
        if pet_refund > 0:
            economy.add_credits(pet_bought_by, pet_refund)
            pet_name = COUPLE_PETS.get(pet_id, {}).get("name", pet_id)
            refund_messages.append(f"🐾 **{pet_name}:** Hoàn trả 25% (`+{pet_refund:,} Thỏi Vàng`) cho <@{pet_bought_by}>")

    economy.clear_couple_assets(user_one, user_two)
    
    if refund_messages:
        return "\n\n💰 **Thanh lý tài sản phu thê (25% giá trị):**\n" + "\n".join(refund_messages)
    return ""


# Sweet sayings for interactions
INTERACT_SAYINGS = {
    "Kiss": [
        "Chụt! Một nụ hôn nồng cháy gửi đến người thương ❤️",
        "Hôn nhẹ lên má cậu một cái nè, yêu ghê cơ 🥰",
        "Thương nhiều lắm mới trao nụ hôn ngọt ngào này đó 😘",
        "Nụ hôn ngọt ngào nhất thế gian này dành riêng cho cậu 💋",
        "Chụt! Mong rằng nụ hôn này làm cậu mỉm cười cả ngày hôm nay ✨"
    ],
    "Hug": [
        "Ôm một cái thật chặt để tiếp thêm năng lượng cho cậu nhé 🤗",
        "Ấm áp ghê, muốn ôm cậu mãi như thế này thôi 💖",
        "Nhận lấy chiếc ôm siêu to khổng lồ từ tớ nè! 🧸",
        "Bất cứ khi nào mệt mỏi, hãy nhớ luôn có một chiếc ôm đợi cậu 🌸",
        "Gửi trọn tình cảm vào cái ôm ấm áp này nhắn gửi tới cậu 💕"
    ],
    "Pat": [
        "Xoa đầu ngoan ngoan nè, thương thương lắm luôn á 👋",
        "Cậu đã làm tốt lắm rồi, xoa đầu khen thưởng cái nè 🥰",
        "Xoa xoa đầu, mong mọi muộn phiền của cậu đều tan biến nhé 💫",
        "Ngoan nào ngoan nào, có tớ ở đây rồi 🥺",
        "Nhìn cưng xỉu thế này chỉ muốn xoa đầu mãi thôi 😸"
    ],
    "Fuck": [
        "Một đêm nồng cháy và đầy yêu thương bên bạn đời của mình... 💕",
        "Ân ái mặn nồng, tình cảm đôi ta càng thêm thắt chặt gắn kết cấu 🥰",
        "Yêu thương đong đầy, những giây phút thăng hoa ngọt ngào bên nhau 💖",
        "Quấn quýt không rời, tình yêu phu thê nồng cháy thăng hoa đầy cảm xúc ✨"
    ]
}

def get_avatar_img(user) -> Image.Image:
    """Downloads user avatar or returns a fallback grey placeholder."""
    try:
        url = str(user.display_avatar.url)
        resp = requests.get(url, timeout=3)
        if resp.status_code == 200:
            return Image.open(BytesIO(resp.content)).convert("RGBA")
    except Exception as e:
        logger.warning(f"Failed to fetch avatar for {user.id}: {e}")
    return Image.new("RGBA", (150, 150), (120, 120, 120, 255))


def crop_circle(img: Image.Image, size: int = 120, mode: str = "cover") -> Image.Image:
    """Crops an image into a circle with transparency, supporting cover or contain modes."""
    img = img.convert("RGBA")
    w, h = img.size
    
    if mode == "cover":
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        img = img.crop((left, top, left + min_dim, top + min_dim))
        img = img.resize((size, size), Image.Resampling.LANCZOS)
    else:  # contain / fit mode (for Xe & Pet object PNGs so subject is fully preserved)
        target_max = int(size * 0.88)
        scale = min(target_max / w, target_max / h)
        new_w = max(1, int(w * scale))
        new_h = max(1, int(h * scale))
        resized_img = img.resize((new_w, new_h), Image.Resampling.LANCZOS)
        
        canvas = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        offset_x = (size - new_w) // 2
        offset_y = (size - new_h) // 2
        canvas.paste(resized_img, (offset_x, offset_y), mask=resized_img)
        img = canvas

    mask = Image.new("L", (size, size), 0)
    mask_draw = ImageDraw.Draw(mask)
    mask_draw.ellipse((0, 0, size, size), fill=255)
    
    output = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    output.paste(img, (0, 0), mask=mask)
    img.close()
    return output


def render_marriage_certificate(proposer, target, ring_id: str) -> BytesIO:
    """Draws a beautiful romantic marriage certificate."""
    # 800 x 500
    bg = Image.new("RGBA", (800, 500), (255, 240, 245, 255)) # LavenderBlush
    draw = ImageDraw.Draw(bg)
    
    # Ornate double border
    draw.rectangle((15, 15, 785, 485), outline=(183, 110, 121, 255), width=3) # Rose gold
    draw.rectangle((22, 22, 778, 478), outline=(183, 110, 121, 100), width=1)
    
    # Header Font & Texts
    font_header = load_font("bold", 38)
    font_title = load_font("bold", 22)
    font_sub = load_font("regular", 16)
    font_names = load_font("bold", 18)
    
    # Title Header
    draw.text((400, 60), "GIẤY CHỨNG NHẬN KẾT HÔN", fill=(128, 0, 32, 255), anchor="mm", font=font_header) # Burgundy
    draw.text((400, 110), "Đã chính thức thề nguyện gắn kết đồng hành bên nhau", fill=(80, 80, 80, 255), anchor="mm", font=font_sub)
    
    # Load avatars
    prop_avatar = get_avatar_img(proposer)
    tar_avatar = get_avatar_img(target)
    
    prop_circle = crop_circle(prop_avatar, 130)
    tar_circle = crop_circle(tar_avatar, 130)
    
    # Paste avatars
    bg.paste(prop_circle, (135, 175), mask=prop_circle)
    bg.paste(tar_circle, (535, 175), mask=tar_circle)
    
    # Gold borders around avatars
    draw.ellipse((133, 173, 267, 307), outline=(255, 215, 0, 255), width=4)
    draw.ellipse((533, 173, 667, 307), outline=(255, 215, 0, 255), width=4)
    
    # Names centered under avatars
    draw.text((200, 335), proposer.display_name, fill=(128, 0, 32, 255), anchor="mm", font=font_names)
    draw.text((600, 335), target.display_name, fill=(128, 0, 32, 255), anchor="mm", font=font_names)
    
    # Center overlapping wedding rings
    draw.ellipse((365, 220, 415, 270), outline=(255, 215, 0, 255), width=4)
    draw.ellipse((385, 220, 435, 270), outline=(255, 215, 0, 255), width=4)
    # Red heart outline in middle intersection
    draw.text((400, 245), "❤️", fill=(255, 0, 0, 255), anchor="mm", font=font_title)
    
    # Ring and Date description
    ring_name = RINGS.get(ring_id, "Nhẫn Cưới")
    date_str = datetime.now().strftime("Ngày %d tháng %m năm %Y")
    
    draw.text((400, 400), f"Vật chứng hôn nhân: {ring_name}", fill=(50, 50, 50, 255), anchor="mm", font=font_title)
    draw.text((400, 435), f"Chứng chỉ kết hôn lập tại sảnh Casino vào {date_str}", fill=(120, 120, 120, 255), anchor="mm", font=font_sub)
    
    # Output to BytesIO
    buf = BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    bg.close()
    return buf


def render_couple_banner(proposer, target, ring_type: str, love_points: int, joint_wallet: int, married_days: int, proposer_ig: str = "", target_ig: str = "", relationship_status: str = "Vợ Chồng", married_at: int = 0, saying: str = "", estate_name: str = "", vehicle_name: str = "", pet_name: str = "") -> BytesIO:
    """Draws a beautiful custom profile banner for married couples using the template."""
    bg_path = ABS_PATH.parent.parent / "pictures" / "Marry" / "banner_marry2.png"
    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGBA")
    else:
        bg_fallback = ABS_PATH.parent.parent / "pictures" / "Marry" / "banner_marry.png"
        if bg_fallback.exists():
            bg = Image.open(bg_fallback).convert("RGBA")
        else:
            # Fallback to plain pink background of same dimensions
            bg = Image.new("RGBA", (1672, 941), (252, 229, 237, 255))
        
    width, height = bg.size
    
    # Create overlay for transparent drawing
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    
    # Load fonts — vogueeb.ttf for display, Roboto for small stat text
    _font_dir = ABS_PATH.parent.parent / "data" / "fonts"
    _font_path = _font_dir / "vogueeb.ttf"

    def _vogue(size: int) -> ImageFont.FreeTypeFont:
        """Load vogueeb.ttf, fallback to Roboto Bold if missing."""
        try:
            return ImageFont.truetype(str(_font_path), size)
        except Exception:
            return load_font("bold", size)

    def _roboto(size: int) -> ImageFont.FreeTypeFont:
        return load_font("bold", size)

    font_large   = _vogue(30)   # display names (decreased from 56 to 30)
    font_medium  = _vogue(48)   # status text "Vợ Chồng" (increased to 48 and pulled higher)
    font_stats   = _vogue(20)   # stats inside heart (decreased to 20 to fit assets)
    font_username = _vogue(30)  # usernames below avatar (decreased from 42 to 30)
    font_regular = _roboto(22)  # IG text in bottom box (decreased from 28 to 22)
    
    # ── Calibrated coordinates from template scan ──────────────────
    # Left  avatar slot center: (412, 412), radius ~174
    # Right avatar slot center: (1243, 412), radius ~177
    # Avatar diameter reduced to 260 to fit neatly inside the frame slot
    LEFT_CX,  LEFT_CY  = 412,  412
    RIGHT_CX, RIGHT_CY = 1243, 412
    AVATAR_DIAM = 260

    # 1. Load and process avatars
    p_avatar = get_avatar_img(proposer)
    t_avatar = get_avatar_img(target)

    p_circle = crop_circle(p_avatar, AVATAR_DIAM)
    t_circle = crop_circle(t_avatar, AVATAR_DIAM)

    overlay.paste(p_circle, (LEFT_CX  - AVATAR_DIAM // 2, LEFT_CY  - AVATAR_DIAM // 2), mask=p_circle)
    overlay.paste(t_circle, (RIGHT_CX - AVATAR_DIAM // 2, RIGHT_CY - AVATAR_DIAM // 2), mask=t_circle)

    p_avatar.close(); t_avatar.close()
    p_circle.close(); t_circle.close()

    PASTEL_PINK   = (235, 110, 145, 255)  # pastel pink replaces PURPLE
    LIGHT_PINK    = (255, 150, 180, 255)  # light pink replaces LIGHT_PURPLE
    BORDER_PINK   = (255, 182, 193, 255)  # border pink replaces PASTEL_PURPLE

    # Draw pastel pink border around avatars: "Avatar được bọc bởi một lớp viền màu hồng pátel"
    draw.ellipse((LEFT_CX - 130, LEFT_CY - 130, LEFT_CX + 130, LEFT_CY + 130), outline=BORDER_PINK, width=6)
    draw.ellipse((RIGHT_CX - 130, RIGHT_CY - 130, RIGHT_CX + 130, RIGHT_CY + 130), outline=BORDER_PINK, width=6)

    # 2. Display names inside white nameplate box above avatar
    draw.text((LEFT_CX,  205), proposer.display_name, fill=LIGHT_PINK, anchor="mm", font=font_large)
    draw.text((RIGHT_CX, 205), target.display_name,   fill=LIGHT_PINK, anchor="mm", font=font_large)

    # 3. Discord usernames inside the card below the avatar (Y = 600, inside the frame): "kéo username lên trên như ảnh"
    draw.text((LEFT_CX,  600), proposer.name, fill=PASTEL_PINK, anchor="mm", font=font_username)
    draw.text((RIGHT_CX, 600), target.name,   fill=PASTEL_PINK, anchor="mm", font=font_username)

    # 4. Relationship status high above the big heart: "Kéo chữ vợ chồng lên cao hơn nữa đi" (moved to Y = 180)
    draw.text((836, 180), relationship_status, fill=PASTEL_PINK, anchor="mm", font=font_medium)

    # 5. Stats inside the big heart
    date_str = "Chưa rõ"
    if married_at > 0:
        date_str = datetime.fromtimestamp(married_at).strftime("%d/%m/%Y")

    draw.text((836, 385), f"Ngày Kết Hôn : {date_str}",      fill=PASTEL_PINK, anchor="mm", font=font_stats)
    draw.text((836, 420), f"Đã Kết Hôn : {married_days} ngày", fill=PASTEL_PINK, anchor="mm", font=font_stats)
    draw.text((836, 455), f"Điểm thân mật : {love_points:,}",  fill=PASTEL_PINK, anchor="mm", font=font_stats)
    
    asset_line = f"🏠 {estate_name or 'Chưa có'}  |  🚗 {vehicle_name or 'Chưa có'}"
    draw.text((836, 490), asset_line, fill=PASTEL_PINK, anchor="mm", font=font_stats)
    pet_line = f"🐾 Thú Cưng: {pet_name or 'Chưa có'}"
    draw.text((836, 525), pet_line, fill=PASTEL_PINK, anchor="mm", font=font_stats)
    
    # 6. Load and paste Ring image centered exactly at the bottom-right heart: "fix lại hình chiếc nhẫn sao cho nó nằm ở giữa cái trái tim ở góc dưới"
    ring_file = RING_IMAGES.get(ring_type)
    if ring_file:
        ring_path = ABS_PATH.parent.parent / "pictures" / "Marry" / ring_file
        if ring_path.exists():
            try:
                ring_img = Image.open(ring_path).convert("RGBA")
                ring_img = ring_img.resize((130, 130), Image.Resampling.LANCZOS)
                overlay.paste(ring_img, (1475 - 65, 825 - 65), mask=ring_img)
                ring_img.close()
            except Exception as e:
                logger.error(f"Failed to draw wedding ring image: {e}")
                
    # 7. Instagram handles inside the bottom rectangular box: "tên ins thì nằm ở trong hình chữ nhật ở dưới cơ mà"
    if not bg_path.exists():
        # Box 1: Left IG
        draw.rounded_rectangle(
            [480, 780, 810, 860],
            radius=15,
            fill=(255, 255, 255, 120),
            outline=(255, 255, 255, 255),
            width=3
        )
        # Box 2: Right IG
        draw.rounded_rectangle(
            [850, 780, 1180, 860],
            radius=15,
            fill=(255, 255, 255, 120),
            outline=(255, 255, 255, 255),
            width=3
        )
    
    left_ig_str = f"ins / {proposer_ig}" if proposer_ig else "ins / chưa đặt"
    right_ig_str = f"ins / {target_ig}" if target_ig else "ins / chưa đặt"
    
    # Draw Instagram handles in bottom box corners (X = 350, 1320, Y = 810)
    draw.text((300,  810), left_ig_str,  fill=LIGHT_PINK, anchor="lm", font=font_regular)
    draw.text((1200, 810), right_ig_str, fill=LIGHT_PINK, anchor="rm", font=font_regular)
    
    # Draw custom saying centered in the middle of the bottom box at Y = 845
    if saying:
        font_saying = _vogue(24)
        draw.text((836, 845), saying, fill=PASTEL_PINK, anchor="mm", font=font_saying)
        
    # Draw joint wallet balance centered near the bottom of the box at Y = 880
    joint_wallet_str = f"Quỹ chung: {joint_wallet:,} VND"
    draw.text((836, 880), joint_wallet_str, fill=PASTEL_PINK, anchor="mm", font=font_regular)
    
    # Composite overlay on background
    bg.paste(overlay, (0, 0), mask=overlay)
    overlay.close()
    
    buf = BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    bg.close()
    return buf


def render_assets_banner(proposer, target, estate_id: str | None, estate_price: int, vehicle_id: str | None, vehicle_price: int, pet_id: str | None, pet_price: int, total_buff: int) -> BytesIO:
    """Draws custom assets banner for married couples displaying BĐS, Xe, and Pet."""
    bg_path = ABS_PATH.parent.parent / "pictures" / "Marry" / "banner_bds_xe_pet.png"
    if bg_path.exists():
        bg = Image.open(bg_path).convert("RGBA")
    else:
        bg = Image.new("RGBA", (1672, 941), (252, 229, 237, 255))
        
    overlay = Image.new("RGBA", bg.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    _font_dir = ABS_PATH.parent.parent / "data" / "fonts"
    _font_path = _font_dir / "vogueeb.ttf"

    def _vogue(size: int) -> ImageFont.FreeTypeFont:
        try:
            return ImageFont.truetype(str(_font_path), size)
        except Exception:
            return load_font("bold", size)

    font_title = _vogue(28)
    font_text  = _vogue(22)

    PASTEL_PINK = (235, 110, 145, 255)
    DARK_TEXT   = (180, 70, 105, 255)

    marry_dir = ABS_PATH.parent.parent / "pictures" / "Marry"

    from app.discord_bot.modules.profile_renderer import strip_emoji

    # Row 1: BĐS (CX: 345, CY: 240, diameter: 150) - mode="cover" for scenery photos
    if estate_id and estate_id in ESTATE_IMAGES:
        e_path = marry_dir / "BĐS" / ESTATE_IMAGES[estate_id]
        if e_path.exists():
            try:
                e_img = Image.open(e_path).convert("RGBA")
                e_c = crop_circle(e_img, 150, mode="cover")
                overlay.paste(e_c, (345 - 150 // 2, 240 - 150 // 2), mask=e_c)
                e_img.close()
                e_c.close()
            except Exception as e:
                logger.error(f"Failed to draw estate image: {e}")

    e_info = COUPLE_ESTATES.get(estate_id, {}) if estate_id else {}
    e_name = strip_emoji(e_info.get("name", "Chưa sở hữu"))
    e_buff = e_info.get("buff", 0)
    draw.text((953, 195), f"BẤT ĐỘNG SẢN : {e_name}", fill=DARK_TEXT, anchor="mm", font=font_title)
    draw.text((953, 245), f"Giá trị : {estate_price:,} Gold" if estate_id else "Giá trị : 0 Gold", fill=PASTEL_PINK, anchor="mm", font=font_text)
    draw.text((953, 285), f"Buff : +{e_buff} pts/ngày vào giới hạn thân mật", fill=PASTEL_PINK, anchor="mm", font=font_text)

    # Row 2: Xe (CX: 345, CY: 505, diameter: 150) - mode="contain" for object PNGs
    if vehicle_id and vehicle_id in VEHICLE_IMAGES:
        v_path = marry_dir / "Xe" / VEHICLE_IMAGES[vehicle_id]
        if v_path.exists():
            try:
                v_img = Image.open(v_path).convert("RGBA")
                v_c = crop_circle(v_img, 150, mode="contain")
                overlay.paste(v_c, (345 - 150 // 2, 505 - 150 // 2), mask=v_c)
                v_img.close()
                v_c.close()
            except Exception as e:
                logger.error(f"Failed to draw vehicle image: {e}")

    v_info = COUPLE_VEHICLES.get(vehicle_id, {}) if vehicle_id else {}
    v_name = strip_emoji(v_info.get("name", "Chưa sở hữu"))
    v_buff = v_info.get("buff", 0)
    draw.text((953, 460), f"PHƯƠNG TIỆN : {v_name}", fill=DARK_TEXT, anchor="mm", font=font_title)
    draw.text((953, 510), f"Giá trị : {vehicle_price:,} Gold" if vehicle_id else "Giá trị : 0 Gold", fill=PASTEL_PINK, anchor="mm", font=font_text)
    draw.text((953, 550), f"Buff : +{v_buff} pts/ngày vào giới hạn thân mật", fill=PASTEL_PINK, anchor="mm", font=font_text)

    # Row 3: Pet (CX: 345, CY: 765, diameter: 150) - mode="contain" for object PNGs
    if pet_id and pet_id in PET_IMAGES:
        p_path = marry_dir / "Pet" / PET_IMAGES[pet_id]
        if p_path.exists():
            try:
                p_img = Image.open(p_path).convert("RGBA")
                p_c = crop_circle(p_img, 150, mode="contain")
                overlay.paste(p_c, (345 - 150 // 2, 765 - 150 // 2), mask=p_c)
                p_img.close()
                p_c.close()
            except Exception as e:
                logger.error(f"Failed to draw pet image: {e}")

    p_info = COUPLE_PETS.get(pet_id, {}) if pet_id else {}
    p_name = strip_emoji(p_info.get("name", "Chưa sở hữu"))
    p_buff = p_info.get("buff", 0)
    draw.text((953, 720), f"THÚ CƯNG : {p_name}", fill=DARK_TEXT, anchor="mm", font=font_title)
    draw.text((953, 770), f"Giá trị : {pet_price:,} Gold" if pet_id else "Giá trị : 0 Gold", fill=PASTEL_PINK, anchor="mm", font=font_text)
    draw.text((953, 810), f"Buff : +{p_buff} pts/ngày vào giới hạn thân mật", fill=PASTEL_PINK, anchor="mm", font=font_text)

    bg.paste(overlay, (0, 0), mask=overlay)
    overlay.close()

    buf = BytesIO()
    bg.save(buf, format="PNG")
    buf.seek(0)
    bg.close()
    return buf


class CoupleBannerView(discord.ui.View):
    """View with 2 buttons: 'Couple 💖' and 'Tài sản 🏰' to switch between couple profile and assets banner."""
    def __init__(self, author: discord.Member, proposer, spouse, marriage_data: tuple, assets_data: tuple | None, economy: Economy, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.proposer = proposer
        self.spouse = spouse
        self.marriage_data = marriage_data
        self.assets_data = assets_data
        self.economy = economy
        self.current_tab = 0
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Nút bấm này không phải dành cho bạn!", ephemeral=True)
            return False
        return True

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == f"banner_tab_{self.current_tab}":
                    child.style = discord.ButtonStyle.primary
                else:
                    child.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="Couple 💖", style=discord.ButtonStyle.primary, custom_id="banner_tab_0")
    async def tab_couple(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_tab = 0
        self.update_buttons()

        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = self.marriage_data
        married_days = max(1, (int(time.time()) - married_at) // 86400)
        ig_handles = self.economy.get_marriage_ig(user_one, user_two)
        if self.proposer.id == user_one:
            author_ig, spouse_ig = ig_handles[0], ig_handles[1]
        else:
            author_ig, spouse_ig = ig_handles[1], ig_handles[0]
        rel_status = self.economy.get_marriage_status(user_one, user_two)
        saying = self.economy.get_marriage_saying(user_one, user_two)

        estate_name, vehicle_name, pet_name = "", "", ""
        if self.assets_data:
            if self.assets_data[0] and self.assets_data[0] in COUPLE_ESTATES:
                estate_name = COUPLE_ESTATES[self.assets_data[0]]["name"]
            if self.assets_data[3] and self.assets_data[3] in COUPLE_VEHICLES:
                vehicle_name = COUPLE_VEHICLES[self.assets_data[3]]["name"]
            if self.assets_data[6] and self.assets_data[6] in COUPLE_PETS:
                pet_name = COUPLE_PETS[self.assets_data[6]]["name"]

        buf = await asyncio.to_thread(
            render_couple_banner,
            self.proposer,
            self.spouse,
            ring_type,
            love_points,
            joint_wallet,
            married_days,
            author_ig,
            spouse_ig,
            rel_status,
            married_at,
            saying,
            estate_name,
            vehicle_name,
            pet_name
        )
        file = discord.File(fp=buf, filename="couple_profile.png")
        await interaction.edit_original_response(attachments=[file], view=self)

    @discord.ui.button(label="Tài Sản 🏰", style=discord.ButtonStyle.secondary, custom_id="banner_tab_1")
    async def tab_assets(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        self.current_tab = 1
        self.update_buttons()

        e_id, e_price, v_id, v_price, p_id, p_price = None, 0, None, 0, None, 0
        if self.assets_data:
            e_id, e_price = self.assets_data[0], self.assets_data[1]
            v_id, v_price = self.assets_data[3], self.assets_data[4]
            p_id, p_price = self.assets_data[6], self.assets_data[7]

        ring_type = self.marriage_data[2]
        ring_base = 30 if ring_type == "ring_eternal_butterfly" else 20
        e_buff = COUPLE_ESTATES.get(e_id, {}).get("buff", 0) if e_id else 0
        v_buff = COUPLE_VEHICLES.get(v_id, {}).get("buff", 0) if v_id else 0
        p_buff = COUPLE_PETS.get(p_id, {}).get("buff", 0) if p_id else 0
        total_buff = ring_base + e_buff + v_buff + p_buff

        buf = await asyncio.to_thread(
            render_assets_banner,
            self.proposer,
            self.spouse,
            e_id,
            e_price,
            v_id,
            v_price,
            p_id,
            p_price,
            total_buff
        )
        file = discord.File(fp=buf, filename="couple_assets.png")
        await interaction.edit_original_response(attachments=[file], view=self)

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class MarriageView(discord.ui.View):
    """View with Accept/Decline buttons for proposal flows."""
    def __init__(self, proposer: discord.User | discord.Member, target: discord.User | discord.Member, ring_id: str, economy: Economy):
        super().__init__(timeout=60.0)
        self.proposer = proposer
        self.target = target
        self.ring_id = ring_id
        self.economy = economy
        self.accepted = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.target.id:
            await interaction.response.send_message("❌ Nút bấm này dành cho người được cầu hôn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Đồng ý ✅", style=discord.ButtonStyle.success, custom_id="marry_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = True
        self.stop()
        
        # Verify proposer still has the ring
        inventory = dict(self.economy.get_inventory(self.proposer.id))
        if inventory.get(self.ring_id, 0) <= 0:
            await interaction.response.send_message("❌ Người cầu hôn không còn sở hữu nhẫn cưới này để kết hôn!", ephemeral=True)
            return
            
        # Consume ring & execute marriage
        self.economy.add_inventory_item(self.proposer.id, self.ring_id, -1)
        self.economy.create_marriage(self.proposer.id, self.target.id, self.ring_id)
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Render and send certificate
        await interaction.channel.send("💘 **Đang lập giấy đăng ký kết hôn...**")
        buf = await asyncio.to_thread(render_marriage_certificate, self.proposer, self.target, self.ring_id)
        file = discord.File(fp=buf, filename="marriage_certificate.png")
        
        embed = make_embed(
            title="💖 CHÚC MỪNG HẠN PHÚC GIA ĐÌNH MỚI 💖",
            description=f"Chúc mừng **{self.proposer.mention}** và **{self.target.mention}** đã thề ước kết duyên vợ chồng thành công!",
            color=discord.Color.magenta()
        )
        embed.set_image(url="attachment://marriage_certificate.png")
        
        # Global divine alert
        if self.ring_id == "ring_divine":
            broadcast = (
                "🎇🎆✨ **THÔNG BÁO TOÀN SEVER** ✨🎆🎇\n"
                f"🎉💎 **CHÚC MỪNG HẠN PHÚC GIA ĐÌNH MỚI!** **{self.proposer.mention}** đã kết hôn cùng "
                f"**{self.target.mention}** bằng **Nhẫn Hào Quang Vĩnh Cửu** lấp lánh thần thánh sang trọng nhất! Trăm năm hạnh phúc! 💖🥂"
            )
            await interaction.channel.send(broadcast)
            
        await interaction.channel.send(embed=embed, file=file)

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.danger, custom_id="marry_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = False
        self.stop()
        
        # Disable buttons
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"💔 **{self.target.mention}** đã từ chối lời cầu hôn của **{self.proposer.mention}**.")


class DivorceView(discord.ui.View):
    """View with Accept/Decline buttons for mutual divorce flows."""
    def __init__(self, initiator: discord.User | discord.Member, spouse: discord.User | discord.Member, economy: Economy):
        super().__init__(timeout=60.0)
        self.initiator = initiator
        self.spouse = spouse
        self.economy = economy
        self.confirmed = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.spouse.id:
            await interaction.response.send_message("❌ Chỉ người bạn đời mới có thể bấm xác nhận ly hôn đồng thuận!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Đồng ý ✅", style=discord.ButtonStyle.success, custom_id="divorce_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Get marriage details to split joint wallet
        marriage = self.economy.get_marriage(self.initiator.id)
        if marriage:
            user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
            split = joint_wallet // 2
            
            # Refund assets 25%
            refund_str = refund_couple_assets_on_divorce(self.economy, user_one, user_two)

            # Delete marriage and return wallet cash
            self.economy.delete_marriage(user_one, user_two)
            if split > 0:
                self.economy.add_money(user_one, split)
                self.economy.add_money(user_two, split)
                
            desc = (
                f"💔 Hai bạn đã chính thức đường ai nấy đi.\n"
                f"🏦 **Quỹ chung chia đôi:** Mỗi người nhận lại `+{split:,} VND` vào tài khoản ví."
                f"{refund_str}"
            )
        else:
            desc = "❌ Không tìm thấy thông tin hôn nhân để chia tài sản."
            
        embed = make_embed(
            title="💔 LY HÔN ĐỒNG THUẬN THÀNH CÔNG 💔",
            description=desc,
            color=discord.Color.red()
        )
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.danger, custom_id="divorce_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"❌ **{self.spouse.mention}** đã từ chối ký đơn ly hôn đồng thuận. Hãy dùng tùy chọn ly hôn đơn phương!")


class CoupleShopView(discord.ui.View):
    """View with 3 tab buttons to browse Estate, Vehicle, and Pet shop."""
    def __init__(self, author: discord.Member, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.current_tab = 0
        self.message = None

    def get_embed(self) -> discord.Embed:
        if self.current_tab == 0:
            desc = "### 🏠 DANH SÁCH BẤT ĐỘNG SẢN CẶP ĐÔI\n"
            desc += "Mua bằng lệnh: `i?couple buy nha <ID>` (trừ thỏi vàng cá nhân)\n\n"
            for k, v in COUPLE_ESTATES.items():
                desc += f"• **`{k}`** — {v['name']}\n  └ Giá: **{v['price']:,} Thỏi Vàng** | Buff: `+{v['buff']} pts/ngày` vào giới hạn thân mật\n"
            embed = make_embed(
                title="🏬 CỬA HÀNG CẶP ĐÔI - BẤT ĐỘNG SẢN 🏠",
                description=desc,
                color=discord.Color.gold()
            )
            embed.set_footer(text="Trang 1/3 • Bất Động Sản")
        elif self.current_tab == 1:
            desc = "### 🚗 DANH SÁCH PHƯƠNG TIỆN CẶP ĐÔI\n"
            desc += "Mua bằng lệnh: `i?couple buy xe <ID>` (trừ thỏi vàng cá nhân)\n\n"
            for k, v in COUPLE_VEHICLES.items():
                desc += f"• **`{k}`** — {v['name']}\n  └ Giá: **{v['price']:,} Thỏi Vàng** | Buff: `+{v['buff']} pts/ngày` vào giới hạn thân mật\n"
            embed = make_embed(
                title="🏬 CỬA HÀNG CẶP ĐÔI - PHƯƠNG TIỆN 🚗",
                description=desc,
                color=discord.Color.blue()
            )
            embed.set_footer(text="Trang 2/3 • Phương Tiện")
        else:
            desc = "### 🐾 DANH SÁCH THÚ CƯNG CẶP ĐÔI\n"
            desc += "Mua bằng lệnh: `i?couple buy pet <ID>` (trừ thỏi vàng cá nhân)\n\n"
            for k, v in COUPLE_PETS.items():
                desc += f"• **`{k}`** — {v['name']}\n  └ Giá: **{v['price']:,} Thỏi Vàng** | Buff: `+{v['buff']} pts/ngày` vào giới hạn thân mật\n"
            embed = make_embed(
                title="🏬 CỬA HÀNG CẶP ĐÔI - THÚ CƯNG 🐾",
                description=desc,
                color=discord.Color.green()
            )
            embed.set_footer(text="Trang 3/3 • Thú Cưng")
        return embed

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == f"tab_{self.current_tab}":
                    child.style = discord.ButtonStyle.primary
                else:
                    child.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="Bất Động Sản 🏠", style=discord.ButtonStyle.primary, custom_id="tab_0")
    async def tab_estate(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Phương Tiện 🚗", style=discord.ButtonStyle.secondary, custom_id="tab_1")
    async def tab_vehicle(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Thú Cưng 🐾", style=discord.ButtonStyle.secondary, custom_id="tab_2")
    async def tab_pet(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = 2
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("❌ Menu này không phải của bạn!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


class CoupleWithdrawView(discord.ui.View):
    """View with Accept/Decline buttons for couple joint wallet withdraw flows."""
    def __init__(self, proposer: discord.User | discord.Member, spouse: discord.User | discord.Member, amount: int, economy: Economy, ctx: commands.Context):
        super().__init__(timeout=60.0)
        self.proposer = proposer
        self.spouse = spouse
        self.amount = amount
        self.economy = economy
        self.ctx = ctx
        self.confirmed = None
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.spouse.id:
            await interaction.response.send_message("❌ Chỉ người bạn đời mới có thể xác nhận rút tiền!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="Đồng ý ✅", style=discord.ButtonStyle.success, custom_id="withdraw_accept")
    async def accept(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        # Double check marriage and wallet balance
        marriages = self.economy.get_marriages(self.proposer.id)
        marriage = None
        for m in marriages:
            m_user_one, m_user_two, *_ = m
            if self.spouse.id in (m_user_one, m_user_two):
                marriage = m
                break
                
        if not marriage:
            await interaction.channel.send("❌ Thất bại: Hôn nhân này không còn tồn tại!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        if joint_wallet < self.amount:
            await interaction.channel.send(f"❌ Thất bại: Quỹ chung hiện tại không đủ để rút (Chỉ còn `{joint_wallet:,} VND`!)")
            return
            
        # Perform withdrawal
        self.economy.update_joint_wallet(user_one, user_two, -self.amount)
        self.economy.add_money(self.proposer.id, self.amount)
        
        log_wallet_change(
            logger,
            event="couple_joint_withdraw",
            user_id=self.proposer.id,
            money_delta=self.amount,
            joint_balance=joint_wallet - self.amount,
            ctx=self.ctx
        )
        
        embed = make_embed(
            title="🏦 RÚT TIỀN QUỸ CHUNG THÀNH CÔNG 🏦",
            description=(
                f"**{self.spouse.name}** đã đồng ý cho **{self.proposer.name}** rút tiền từ quỹ phu thê:\n\n"
                f"💰 **Nhận lại ví:** `+{self.amount:,} VND`\n"
                f"🏦 **Số dư quỹ chung còn lại:** `{joint_wallet - self.amount:,} VND`"
            ),
            color=discord.Color.green()
        )
        await interaction.channel.send(embed=embed)

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.danger, custom_id="withdraw_decline")
    async def decline(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        await interaction.channel.send(f"❌ **{self.spouse.mention}** đã từ chối yêu cầu rút tiền phu thê của **{self.proposer.mention}**.")


class Marry(commands.Cog):
    """Cog for community Couple features and rewards."""
    def __init__(self, bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", Economy())

    async def is_admin_user(self, user) -> bool:
        if user.id in config.bot.owner_ids or user.id in config.bot.admin_ids:
            return True
        if user.id in self.bot.owner_ids:
            return True
        try:
            return await self.bot.is_owner(user)
        except Exception:
            return False

    def _resolve_marriage_and_args(self, user_id: int, args: list[str]) -> tuple[tuple | None, list[str]]:
        marriages = self.economy.get_marriages(user_id)
        if not marriages:
            return None, args
            
        if args and args[0].isdigit():
            idx = int(args[0])
            if 1 <= idx <= len(marriages):
                return marriages[idx - 1], args[1:]
                
        return marriages[0], args

    @commands.command(
        brief="Cầu hôn một người chơi khác trong server.",
        usage="marry @user"
    )
    async def marry(self, ctx: commands.Context, target: discord.Member):
        if target.bot:
            await ctx.send("❌ Bạn không thể kết hôn cùng bot!")
            return
            
        if target.id == ctx.author.id:
            await ctx.send("❌ Bạn không thể kết hôn với chính bản thân mình!")
            return
            
        # Check active marriages limit
        author_marriages = self.economy.get_marriages(ctx.author.id)
        author_limit = 5 if await self.is_admin_user(ctx.author) else 1
        if len(author_marriages) >= author_limit:
            if author_limit == 1:
                await ctx.send("❌ Bạn đang trong một cuộc hôn nhân! Hãy ly hôn (i?divorce) trước khi đi tìm bến đỗ mới.")
            else:
                await ctx.send(f"❌ Bạn đã đạt giới hạn kết hôn tối đa là {author_limit} người cùng lúc!")
            return
            
        target_marriages = self.economy.get_marriages(target.id)
        target_limit = 5 if await self.is_admin_user(target) else 1
        if len(target_marriages) >= target_limit:
            if target_limit == 1:
                await ctx.send(f"❌ **{target.name}** đã kết hôn rồi! Đập chậu cướp hoa là hành vi trái đạo đức.")
            else:
                await ctx.send(f"❌ **{target.name}** đã đạt giới hạn kết hôn tối đa là {target_limit} người cùng lúc!")
            return

            
        # Check owned rings in inventory
        inventory = dict(self.economy.get_inventory(ctx.author.id))
        
        # Select best ring owned
        owned_rings = [k for k in RINGS.keys() if inventory.get(k, 0) > 0]
        if not owned_rings:
            await ctx.send("❌ **Bạn không sở hữu nhẫn cưới nào!** Hãy sử dụng `i?shop` để mua một chiếc nhẫn cầu hôn trước.")
            return
            
        # Prioritize divine > angel > gothic > sunburst > sapphire > ruby > citrine > nhankat > cupid > amethyst > emerald > aquamarine > quartz > grass
        ring_priority = [
            "ring_eternal_butterfly",
            "ring_divine",
            "ring_angel",
            "ring_gothic",
            "ring_sunburst",
            "ring_sapphire",
            "ring_ruby",
            "ring_citrine",
            "ring_nhankat",
            "ring_cupid",
            "ring_amethyst",
            "ring_emerald",
            "ring_aquamarine",
            "ring_quartz",
            "ring_grass"
        ]
        ring_id = next(r for r in ring_priority if r in owned_rings)
        ring_name = RINGS[ring_id]
        
        view = MarriageView(ctx.author, target, ring_id, self.economy)
        embed = make_embed(
            title="💞 LỜI CẦU HÔN LÃNG MẠN 💞",
            description=(
                f"💍 **{ctx.author.mention}** đang quỳ xuống trao chiếc **{ring_name}** cầu hôn bạn đời **{target.mention}**!\n\n"
                f"*Bạn có đồng ý kết duyên trăm năm, đồng cam cộng khổ cùng họ không?*"
            ),
            color=discord.Color.magenta()
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.group(name="couple", brief="Quản lý thông tin gia đình cặp đôi.", invoke_without_command=True, usage="couple [chỉ_số/người_dùng] [chỉ_số]")
    async def couple_cmd(self, ctx: commands.Context, index_or_user: str = None, index: int = None):
        # Displays the couple profile banner
        # Parse arguments
        target_user = ctx.author
        target_index = 1
        
        if index_or_user is not None:
            # Check if index_or_user is a number
            try:
                target_index = int(index_or_user)
            except ValueError:
                # Try parsing as user/member
                try:
                    target_user = await commands.MemberConverter().convert(ctx, index_or_user)
                except commands.BadArgument:
                    await ctx.send("❌ Người dùng không hợp lệ!")
                    return
                # If index is also provided
                if index is not None:
                    target_index = index
                    
        if target_index < 1:
            await ctx.send("❌ Chỉ số cặp đôi phải lớn hơn hoặc bằng 1!")
            return
            
        marriages = self.economy.get_marriages(target_user.id)
        if not marriages:
            if target_user.id == ctx.author.id:
                await ctx.send(f"❌ Bạn chưa kết hôn! Hãy sắm nhẫn cưới rồi cầu hôn ai đó bằng: `{config.bot.prefix}marry @user`")
            else:
                await ctx.send(f"❌ **{target_user.name}** chưa kết hôn!")
            return
            
        if target_index > len(marriages):
            if len(marriages) == 1:
                await ctx.send(f"❌ **{target_user.display_name}** chỉ có 1 cuộc hôn nhân!")
            else:
                await ctx.send(f"❌ **{target_user.display_name}** chỉ có {len(marriages)} cuộc hôn nhân! (Hãy nhập chỉ số từ 1 đến {len(marriages)})")
            return
            
        marriage = marriages[target_index - 1]
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        
        # Accumulate Quỹ Chung interest if ring_eternal_butterfly
        if ring_type == "ring_eternal_butterfly" and joint_wallet > 0:
            last_interest, last_wish = self.economy.get_marriage_times(user_one, user_two)
            now = int(time.time())
            
            # If last_interest is 0, initialize it to married_at
            if last_interest == 0:
                last_interest = married_at
                self.economy.update_marriage_times(user_one, user_two, last_interest_time=last_interest)
                
            # Calculate calendar days since last interest
            import datetime
            last_date = datetime.date.fromtimestamp(last_interest)
            now_date = datetime.date.fromtimestamp(now)
            days_passed = (now_date - last_date).days
            
            if days_passed > 0:
                total_interest = 0
                temp_wallet = joint_wallet
                for _ in range(min(days_passed, 30)): # Cap at 30 days of inactivity to prevent overflow
                    day_interest = int(temp_wallet * 0.03)
                    day_interest = min(15_000_000, day_interest) # Cap daily interest at 15M
                    total_interest += day_interest
                    temp_wallet += day_interest
                
                if total_interest > 0:
                    self.economy.update_joint_wallet(user_one, user_two, total_interest)
                    self.economy.update_marriage_times(user_one, user_two, last_interest_time=now)
                    joint_wallet += total_interest
        
        # Get spouse object
        spouse_id = user_two if target_user.id == user_one else user_one
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try: spouse = await self.bot.fetch_user(spouse_id)
            except Exception: pass
            
        if not spouse:
            # Fallback mock user if missing
            class FallbackUser:
                def __init__(self, uid):
                    self.id = uid
                    self.display_name = f"User_ID:{uid}"
                    self.display_avatar = self
                    self.url = "https://example.com/avatar.png"
            spouse = FallbackUser(spouse_id)
            
        married_days = max(1, (int(time.time()) - married_at) // 86400)
        
        loading_msg = await ctx.send("⌛ **Đang kết xuất thông tin gia đình...**")
        
        # Get IG handles
        ig_handles = self.economy.get_marriage_ig(user_one, user_two)
        # Determine which IG belongs to target_user and which to spouse
        if target_user.id == user_one:
            author_ig, spouse_ig = ig_handles[0], ig_handles[1]
        else:
            author_ig, spouse_ig = ig_handles[1], ig_handles[0]
            
        # Get custom status
        rel_status = self.economy.get_marriage_status(user_one, user_two)
        
        # Get custom saying
        saying = self.economy.get_marriage_saying(user_one, user_two)
        
        # Get couple assets for banner display
        assets = self.economy.get_couple_assets(user_one, user_two)
        estate_name = ""
        vehicle_name = ""
        pet_name = ""
        if assets:
            if assets[0] and assets[0] in COUPLE_ESTATES:
                estate_name = COUPLE_ESTATES[assets[0]]["name"]
            if assets[3] and assets[3] in COUPLE_VEHICLES:
                vehicle_name = COUPLE_VEHICLES[assets[3]]["name"]
            if assets[6] and assets[6] in COUPLE_PETS:
                pet_name = COUPLE_PETS[assets[6]]["name"]

        buf = await asyncio.to_thread(
            render_couple_banner, 
            target_user, 
            spouse, 
            ring_type, 
            love_points, 
            joint_wallet, 
            married_days,
            author_ig,
            spouse_ig,
            rel_status,
            married_at,
            saying,
            estate_name,
            vehicle_name,
            pet_name
        )
        view = CoupleBannerView(ctx.author, target_user, spouse, marriage, assets, self.economy)
        file = discord.File(fp=buf, filename="couple_profile.png")
        msg = await ctx.send(file=file, view=view)
        view.message = msg
        
        try:
            await loading_msg.delete()
        except Exception:
            pass

    @couple_cmd.command(
        name="top",
        aliases=["leaderboard", "bxh"],
        brief="Xem bảng xếp hạng các cặp đôi trong server.",
        usage="couple top [love/wallet/days]"
    )
    async def couple_top(self, ctx: commands.Context, sort_type: str = "love"):
        """Xem bảng xếp hạng các cặp đôi trong server theo nhiều tiêu chí khác nhau."""
        # Normalize sort type
        sort_type = sort_type.lower().strip()
        
        # Map sort type to database query parameter
        if sort_type in ["love", "tim", "point", "points", "than_mat", "thanmat"]:
            db_sort = "love_points"
            title_sort = "Điểm Thân Mật 💞"
        elif sort_type in ["wallet", "quy", "money", "tien", "quychung", "quy_chung"]:
            db_sort = "joint_wallet"
            title_sort = "Số Dư Quỹ Chung 🏦"
        elif sort_type in ["days", "day", "time", "ngay", "hanh_phuc", "hanhphuc"]:
            db_sort = "married_at"
            title_sort = "Thời Gian Kết Hôn (Số Ngày) 📅"
        else:
            await ctx.send("❌ Loại bảng xếp hạng không hợp lệ! Hãy sử dụng: `love` (Điểm thân mật), `wallet` (Quỹ chung), hoặc `days` (Số ngày kết hôn).")
            return
            
        loading_msg = await ctx.send("⌛ **Đang tải bảng xếp hạng cặp đôi...**")
        
        top_marriages = self.economy.get_top_marriages(db_sort, limit=10)
        
        if not top_marriages:
            await ctx.send("❌ Chưa có cặp đôi nào kết hôn trên hệ thống!")
            try:
                await loading_msg.delete()
            except Exception:
                pass
            return
            
        embed = make_embed(
            title=f"🏆 BẢNG XẾP HẠNG CẶP ĐÔI - {title_sort.upper()} 🏆",
            description="Dưới đây là danh sách 10 cặp đôi nổi bật nhất server:\n\n",
            color=discord.Color.magenta()
        )
        
        lines = []
        for idx, m in enumerate(top_marriages):
            user_one, user_two, ring_type, love_points, joint_wallet, married_at = m
            
            # Get spouse names or mentions
            u1 = self.bot.get_user(user_one)
            if not u1:
                try: u1 = await self.bot.fetch_user(user_one)
                except Exception: u1 = None
                
            u2 = self.bot.get_user(user_two)
            if not u2:
                try: u2 = await self.bot.fetch_user(user_two)
                except Exception: u2 = None
                
            name1 = u1.mention if u1 else f"ID: {user_one}"
            name2 = u2.mention if u2 else f"ID: {user_two}"
            
            ring_emoji = RINGS.get(ring_type, ring_type)
            
            # Formatting rank prefix
            if idx == 0:
                rank_str = "👑 **Top 1**"
            elif idx == 1:
                rank_str = "🥈 **Top 2**"
            elif idx == 2:
                rank_str = "🥉 **Top 3**"
            else:
                rank_str = f"#️⃣ **Top {idx + 1}**"
                
            # Formatting value representation
            if db_sort == "love_points":
                val_str = f"`{love_points:,} 💞`"
            elif db_sort == "joint_wallet":
                val_str = f"`{joint_wallet:,} VND` 🏦"
            else:
                # married_at
                days = max(1, (int(time.time()) - married_at) // 86400)
                val_str = f"`{days:,} ngày` 📅"
                
            lines.append(f"{rank_str}: {name1} ❤️ {name2}\n└ 💍 Tín vật: {ring_emoji} | Đạt: {val_str}")
            
        embed.description += "\n\n".join(lines)
        embed.set_footer(text=f"Sử dụng: '{config.bot.prefix}couple top [love/wallet/days]' để đổi bảng xếp hạng.")
        
        await ctx.send(embed=embed)
        try:
            await loading_msg.delete()
        except Exception:
            pass

    @couple_cmd.command(name="setig", aliases=["instagram", "ig"], brief="Đặt tài khoản Instagram hiển thị trên banner.", usage="couple setig [chỉ_số] <tên_ig>")

    async def couple_setig(self, ctx: commands.Context, *, args_str: str = ""):
        """Đặt tài khoản Instagram của bạn để hiển thị trên profile cặp đôi."""
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn!")
            return
        if not remaining_args:
            await ctx.send("❌ Vui lòng cung cấp tài khoản Instagram!")
            return
            
        ig_handle = remaining_args[0]
        # Clean handle (remove @ if present)
        clean_handle = ig_handle.strip().lstrip('@')
        if len(clean_handle) > 30:
            await ctx.send("❌ Tên tài khoản Instagram quá dài (tối đa 30 ký tự)!")
            return
            
        user_one, user_two = marriage[0], marriage[1]
        self.economy.update_marriage_ig(user_one, user_two, ctx.author.id, clean_handle)
        await ctx.send(f"✅ Đã cập nhật tài khoản Instagram của bạn thành: `ins / {clean_handle}` cho cuộc hôn nhân này!")

    @couple_cmd.command(name="status", aliases=["setstatus", "trangthai"], brief="Đặt trạng thái mối quan hệ cặp đôi.", usage="couple status [chỉ_số] <trạng_thái>")
    async def couple_status(self, ctx: commands.Context, *, args_str: str = ""):
        """Đặt trạng thái mối quan hệ của cặp đôi (ví dụ: situation ship, mãi bên nhau...)."""
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn!")
            return
        if not remaining_args:
            await ctx.send("❌ Vui lòng cung cấp trạng thái quan hệ!")
            return
            
        status_text = " ".join(remaining_args)
        clean_status = status_text.strip()
        if len(clean_status) > 20:
            await ctx.send("❌ Trạng thái mối quan hệ quá dài (tối đa 20 ký tự)!")
            return
            
        user_one, user_two = marriage[0], marriage[1]
        self.economy.update_marriage_status(user_one, user_two, clean_status)
        await ctx.send(f"✅ Đã cập nhật trạng thái mối quan hệ thành: `{clean_status}` cho cuộc hôn nhân này!")

    @couple_cmd.command(name="setsaying", aliases=["saying", "quote", "setquote", "slogan"], brief="Đặt câu nói/slogan cho cặp đôi dưới banner.", usage="couple setsaying [chỉ_số] <câu_nói>")
    async def couple_setsaying(self, ctx: commands.Context, *, args_str: str = ""):
        """Đặt câu nói/slogan cho cặp đôi hiển thị ở khung dưới banner."""
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn!")
            return
        if not remaining_args:
            await ctx.send("❌ Vui lòng cung cấp câu nói!")
            return
            
        saying_text = " ".join(remaining_args)
        clean_saying = saying_text.strip()
        user_one, user_two = marriage[0], marriage[1]
        if clean_saying.lower() in ("xoa", "clear", "none"):
            self.economy.update_marriage_saying(user_one, user_two, "")
            await ctx.send("✅ Đã xóa câu nói của cặp đôi cho cuộc hôn nhân này!")
            return
            
        if len(clean_saying) > 100:
            await ctx.send("❌ Câu nói quá dài (tối đa 100 ký tự)!")
            return
            
        self.economy.update_marriage_saying(user_one, user_two, clean_saying)
        await ctx.send(f"✅ Đã cập nhật câu nói thành: `{clean_saying}` cho cuộc hôn nhân này!")

    @couple_cmd.command(name="changering", aliases=["doinhan", "doi_nhan", "swapring"], brief="Thay nhẫn cưới hiện tại bằng nhẫn mới (hoàn nhẫn cũ).", usage="couple changering [chỉ_số] [tên_nhẫn]")
    async def couple_changering(self, ctx: commands.Context, *, args_str: str = ""):
        """Thay thế nhẫn cưới hiện tại bằng một chiếc nhẫn mới trong túi đồ của bạn (hoàn lại nhẫn cũ)."""
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn!")
            return

        user_one, user_two, old_ring_type, love_points, joint_wallet, married_at, _, _ = marriage

        # Check owned rings in inventory
        inventory = dict(self.economy.get_inventory(ctx.author.id))
        owned_rings = [k for k in RINGS.keys() if inventory.get(k, 0) > 0]

        if not owned_rings:
            await ctx.send("❌ **Bạn không sở hữu nhẫn cưới nào trong túi đồ!** Vui lòng mua nhẫn mới từ sảnh `i?shop`.")
            return

        selected_ring_id = None
        if remaining_args:
            input_ring = " ".join(remaining_args).lower().strip()
            # Try to match key or name
            for k, v in RINGS.items():
                if input_ring in k.lower() or input_ring in v.lower():
                    selected_ring_id = k
                    break

            if not selected_ring_id or selected_ring_id not in owned_rings:
                await ctx.send(f"❌ Bạn không sở hữu nhẫn cưới nào khớp với '{input_ring}' trong túi đồ!")
                return
        else:
            # Prioritize best ring
            ring_priority = [
                "ring_eternal_butterfly",
                "ring_divine",
                "ring_angel",
                "ring_gothic",
                "ring_sunburst",
                "ring_sapphire",
                "ring_ruby",
                "ring_citrine",
                "ring_nhankat",
                "ring_cupid",
                "ring_amethyst",
                "ring_emerald",
                "ring_aquamarine",
                "ring_quartz",
                "ring_grass"
            ]
            selected_ring_id = next((r for r in ring_priority if r in owned_rings), None)

        if not selected_ring_id:
            await ctx.send("❌ Không thể xác định nhẫn cưới để đổi!")
            return

        if selected_ring_id == old_ring_type:
            await ctx.send(f"❌ Cuộc hôn nhân này hiện tại đã sử dụng **{RINGS[old_ring_type]}** rồi, không cần đổi cùng loại nhẫn!")
            return

        # Perform the ring swap
        # 1. Deduct new ring
        self.economy.add_inventory_item(ctx.author.id, selected_ring_id, -1)
        # 2. Return old ring
        self.economy.add_inventory_item(ctx.author.id, old_ring_type, 1)
        # 3. Update database
        self.economy.update_marriage_ring(user_one, user_two, selected_ring_id)

        log_wallet_change(
            logger,
            event="couple_change_ring",
            user_id=ctx.author.id,
            old_ring=old_ring_type,
            new_ring=selected_ring_id,
            ctx=ctx
        )

        embed = make_embed(
            title="💖 THAY THẾ NHẪN CƯỚI THÀNH CÔNG 💖",
            description=(
                f"Đã đổi tín vật kết duyên thành công cho cuộc hôn nhân này!\n\n"
                f"📦 **Nhẫn cũ hoàn trả vào túi đồ:** {RINGS.get(old_ring_type, old_ring_type)}\n"
                f"✨ **Tín vật mới của gia đình:** {RINGS[selected_ring_id]}"
            ),
            color=discord.Color.magenta()
        )
        await ctx.send(embed=embed)

    @couple_cmd.command(name="deposit", aliases=["gop"], brief="Góp tiền vào quỹ chung phu thê.", usage="couple deposit [chỉ_số] <số_tiền/all>")
    async def couple_deposit(self, ctx: commands.Context, *, args_str: str = ""):
        # Deposit to joint wallet
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể mở khóa và góp tiền vào quỹ chung!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        if not remaining_args:
            await ctx.send("❌ Vui lòng nhập số tiền muốn góp!")
            return
            
        amount = remaining_args[0]
        # Get user cash balance
        profile_entry = self.economy.get_entry(ctx.author.id)
        user_cash = profile_entry[1]

        # Parse deposit amount
        if amount.lower() in ["all", "tất tay"]:
            money_val = user_cash
        else:
            try:
                # Custom parse multiplier like 100k, 1m
                val_str = amount.lower().replace("k", "000").replace("m", "000000").replace(",", "").replace(".", "")
                money_val = int(val_str)
            except Exception:
                await ctx.send("❌ Số tiền nhập vào không hợp lệ!")
                return
                
        if money_val <= 0:
            await ctx.send("❌ Số tiền góp phải lớn hơn 0.")
            return
            
        if user_cash < money_val:
            await ctx.send(f"❌ Bạn không đủ tiền! Bạn chỉ có `{user_cash:,} VND`.")
            return
            
        # Deduct cash
        self.economy.add_money(ctx.author.id, -money_val)
        new_joint = self.economy.update_joint_wallet(user_one, user_two, money_val)
        
        log_wallet_change(
            logger,
            event="couple_joint_deposit",
            user_id=ctx.author.id,
            money_delta=-money_val,
            joint_balance=new_joint,
            ctx=ctx
        )
        
        embed = make_embed(
            title="🏦 GÓP TIỀN QUỸ CHUNG THÀNH CÔNG 🏦",
            description=(
                f"**{ctx.author.name}** đã góp thành công vào quỹ gia đình:\n\n"
                f"💸 **Tiền góp:** `-{money_val:,} VND`\n"
                f"🏦 **Số dư quỹ chung mới:** `{new_joint:,} VND`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @couple_cmd.command(name="withdraw", aliases=["rut"], brief="Rút tiền từ quỹ chung phu thê (cần bạn đời đồng ý).", usage="couple withdraw [chỉ_số] <số_tiền/all>")
    async def couple_withdraw(self, ctx: commands.Context, *, args_str: str = ""):
        # Withdraw from joint wallet
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể rút tiền từ quỹ chung!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        if not remaining_args:
            await ctx.send("❌ Vui lòng nhập số tiền muốn rút!")
            return
            
        amount = remaining_args[0]
        # Parse withdraw amount
        if amount.lower() == "all" or amount.lower() == "tất tay":
            money_val = joint_wallet
        else:
            try:
                # Custom parse multiplier like 100k, 1m
                val_str = amount.lower().replace("k", "000").replace("m", "000000").replace(",", "").replace(".", "")
                money_val = int(val_str)
            except Exception:
                await ctx.send("❌ Số tiền nhập vào không hợp lệ!")
                return
                
        if money_val <= 0:
            await ctx.send("❌ Số tiền rút phải lớn hơn 0.")
            return
            
        if joint_wallet < money_val:
            await ctx.send(f"❌ Quỹ chung không đủ tiền! Quỹ chỉ có `{joint_wallet:,} VND`.")
            return
            
        # Get spouse object
        spouse_id = user_two if ctx.author.id == user_one else user_one
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try:
                spouse = await self.bot.fetch_user(spouse_id)
            except Exception:
                pass
            
        if not spouse:
            await ctx.send("❌ Không thể tìm thấy thông tin bạn đời để yêu cầu đồng ý!")
            return
            
        view = CoupleWithdrawView(ctx.author, spouse, money_val, self.economy, ctx)
        embed = make_embed(
            title="🏦 YÊU CẦU RÚT TIỀN QUỸ PHU THÊ 🏦",
            description=(
                f"💍 **{ctx.author.mention}** muốn rút **`{money_val:,} VND`** từ quỹ chung.\n\n"
                f"🔔 Bạn đời **{spouse.mention}** vui lòng xác nhận đồng ý hoặc từ chối yêu cầu này!"
            ),
            color=discord.Color.magenta()
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg


    @couple_cmd.command(name="wish", aliases=["uoc", "uocnguyen"], brief="Cầu chúc phúc phu thê nhận quà mỗi ngày (Chỉ dành cho Nhẫn Song Điệp Vĩnh Hằng).", usage="couple wish [chỉ_số]")
    async def couple_wish(self, ctx: commands.Context, *, args_str: str = ""):
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn phải kết hôn mới có thể thực hiện lệnh ước nguyện!")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        if ring_type != "ring_eternal_butterfly":
            await ctx.send("❌ **Lệnh này là đặc quyền độc nhất chỉ dành cho cặp đôi sở hữu Nhẫn Song Điệp Vĩnh Hằng 🦋!**")
            return
            
        # Get timestamps
        last_interest, last_wish = self.economy.get_marriage_times(user_one, user_two)
        
        # Check calendar day reset for wish
        now = int(time.time())
        now_struct = time.localtime(now)
        last_wish_struct = time.localtime(last_wish)
        
        if last_wish > 0 and now_struct.tm_yday == last_wish_struct.tm_yday and now_struct.tm_year == last_wish_struct.tm_year:
            await ctx.send("⏳ **Hôm nay hai bạn đã thực hiện ước nguyện rồi!** Vui lòng quay lại vào ngày mai nhé.")
            return
            
        # Grant reward: +5 intimacy points and +200,000 VND to joint wallet
        self.economy.update_marriage_times(user_one, user_two, last_wish_time=now)
        self.economy.update_joint_wallet(user_one, user_two, 200_000)
        
        self.economy.cur.execute(
            "UPDATE user_marry SET love_points = love_points + 5 WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        self.economy.conn.commit()
        
        embed = make_embed(
            title="🦋 ƯỚC NGUYỆN PHU THÊ VĨNH HẰNG 🦋",
            description=(
                f"💞 Hai bạn cùng hướng về **Nhẫn Song Điệp Vĩnh Hằng** lấp lánh và cầu nguyện cho tình cảm keo sơn vĩnh kết đồng tâm...\n\n"
                f"✨ **Chúc phúc Ước nguyện thành công:**\n"
                f"💖 **Điểm thân mật:** `+5 điểm`\n"
                f"🏦 **Cộng vào Quỹ Chung:** `+200,000 VND`"
            ),
            color=discord.Color.magenta()
        )
        await ctx.send(embed=embed)

    def _get_couple_daily_limit(self, ring_type: str, assets: tuple | None) -> int:
        base = 30 if ring_type == "ring_eternal_butterfly" else 20
        if not assets:
            return base
        e_id, _, _, v_id, _, _, p_id, _, _ = assets
        e_buff = COUPLE_ESTATES.get(e_id, {}).get("buff", 0) if e_id else 0
        v_buff = COUPLE_VEHICLES.get(v_id, {}).get("buff", 0) if v_id else 0
        p_buff = COUPLE_PETS.get(p_id, {}).get("buff", 0) if p_id else 0
        return base + e_buff + v_buff + p_buff

    @couple_cmd.command(name="shop", aliases=["store", "cuahang"], brief="Xem danh sách bất động sản, phương tiện và thú cưng cặp đôi.")
    async def couple_shop(self, ctx: commands.Context):
        view = CoupleShopView(ctx.author)
        embed = view.get_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @couple_cmd.group(name="buy", brief="Mua nhà, xe hoặc thú cưng cho cặp đôi.", invoke_without_command=True)
    async def couple_buy(self, ctx: commands.Context, item_type: str = None, item_id: str = None):
        if ctx.invoked_subcommand is None:
            if item_type and item_id:
                item_type = item_type.lower().strip()
                if item_type in ["nha", "bds", "estate"]:
                    await ctx.invoke(self.couple_buy_nha, item_id=item_id)
                    return
                elif item_type in ["xe", "vehicle", "phuongtien"]:
                    await ctx.invoke(self.couple_buy_xe, item_id=item_id)
                    return
                elif item_type in ["pet", "thucung", "thu"]:
                    await ctx.invoke(self.couple_buy_pet, item_id=item_id)
                    return
            await ctx.send("❌ Cú pháp: `i?couple buy nha <ID>`, `i?couple buy xe <ID>`, hoặc `i?couple buy pet <ID>`. Gõ `i?couple shop` để xem danh sách món đồ!")

    @couple_buy.command(name="nha", aliases=["bds", "estate"], brief="Mua nhà / bất động sản cho cặp đôi.")
    async def couple_buy_nha(self, ctx: commands.Context, item_id: str):
        marriage, _ = self._resolve_marriage_and_args(ctx.author.id, [])
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn nên không thể mua bất động sản cặp đôi!")
            return

        user_one, user_two = marriage[0], marriage[1]
        item_id = item_id.lower().strip()
        if item_id not in COUPLE_ESTATES:
            await ctx.send(f"❌ ID bất động sản `{item_id}` không hợp lệ! Hãy gõ `i?couple shop` để xem danh sách.")
            return

        estate_info = COUPLE_ESTATES[item_id]
        price = estate_info["price"]

        profile = self.economy.get_entry(ctx.author.id)
        gold = profile[2]
        if gold < price:
            await ctx.send(f"❌ Bạn không đủ thỏi vàng! `{estate_info['name']}` có giá `{price:,} Thỏi Vàng`, nhưng bạn chỉ có `{gold:,} Thỏi Vàng`.")
            return

        assets = self.economy.get_couple_assets(user_one, user_two)
        refund_msg = ""
        if assets and assets[0] and assets[1] > 0 and assets[2] > 0:
            old_id, old_price, old_buyer = assets[0], assets[1], assets[2]
            if old_id == item_id:
                await ctx.send(f"❌ Cặp đôi của bạn hiện đã sở hữu {estate_info['name']} rồi!")
                return
            refund_amount = int(old_price * 0.25)
            if refund_amount > 0 and old_buyer > 0:
                self.economy.add_credits(old_buyer, refund_amount)
                old_name = COUPLE_ESTATES.get(old_id, {}).get("name", old_id)
                refund_msg = f"\n📦 **Thanh lý {old_name} cũ:** Hoàn lại 25% (`+{refund_amount:,} Thỏi Vàng`) cho <@{old_buyer}>."

        self.economy.add_credits(ctx.author.id, -price)
        self.economy.set_couple_estate(user_one, user_two, item_id, price, ctx.author.id)

        log_wallet_change(
            logger,
            event="couple_buy_estate",
            user_id=ctx.author.id,
            credits_delta=-price,
            estate_id=item_id,
            ctx=ctx
        )

        embed = make_embed(
            title="🏠 MUA BẤT ĐỘNG SẢN CẶP ĐÔI THÀNH CÔNG 🏠",
            description=(
                f"**{ctx.author.name}** đã mua thành công **{estate_info['name']}** cho tổ ấm gia đình!\n\n"
                f"🟡 **Chi phí:** `-{price:,} Thỏi Vàng` (trừ ví vàng cá nhân)\n"
                f"✨ **Buff thân mật:** `+{estate_info['buff']} pts/ngày` vào giới hạn thân mật hàng ngày!{refund_msg}"
            ),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @couple_buy.command(name="xe", aliases=["vehicle", "phuongtien"], brief="Mua xe / phương tiện cho cặp đôi.")
    async def couple_buy_xe(self, ctx: commands.Context, item_id: str):
        marriage, _ = self._resolve_marriage_and_args(ctx.author.id, [])
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn nên không thể mua phương tiện cặp đôi!")
            return

        user_one, user_two = marriage[0], marriage[1]
        item_id = item_id.lower().strip()
        if item_id not in COUPLE_VEHICLES:
            await ctx.send(f"❌ ID phương tiện `{item_id}` không hợp lệ! Hãy gõ `i?couple shop` để xem danh sách.")
            return

        vehicle_info = COUPLE_VEHICLES[item_id]
        price = vehicle_info["price"]

        profile = self.economy.get_entry(ctx.author.id)
        gold = profile[2]
        if gold < price:
            await ctx.send(f"❌ Bạn không đủ thỏi vàng! `{vehicle_info['name']}` có giá `{price:,} Thỏi Vàng`, nhưng bạn chỉ có `{gold:,} Thỏi Vàng`.")
            return

        assets = self.economy.get_couple_assets(user_one, user_two)
        refund_msg = ""
        if assets and assets[3] and assets[4] > 0 and assets[5] > 0:
            old_id, old_price, old_buyer = assets[3], assets[4], assets[5]
            if old_id == item_id:
                await ctx.send(f"❌ Cặp đôi của bạn hiện đã sở hữu {vehicle_info['name']} rồi!")
                return
            refund_amount = int(old_price * 0.25)
            if refund_amount > 0 and old_buyer > 0:
                self.economy.add_credits(old_buyer, refund_amount)
                old_name = COUPLE_VEHICLES.get(old_id, {}).get("name", old_id)
                refund_msg = f"\n📦 **Thanh lý {old_name} cũ:** Hoàn lại 25% (`+{refund_amount:,} Thỏi Vàng`) cho <@{old_buyer}>."

        self.economy.add_credits(ctx.author.id, -price)
        self.economy.set_couple_vehicle(user_one, user_two, item_id, price, ctx.author.id)

        log_wallet_change(
            logger,
            event="couple_buy_vehicle",
            user_id=ctx.author.id,
            credits_delta=-price,
            vehicle_id=item_id,
            ctx=ctx
        )

        embed = make_embed(
            title="🚗 MUA PHƯƠNG TIỆN CẶP ĐÔI THÀNH CÔNG 🚗",
            description=(
                f"**{ctx.author.name}** đã sắm thành công **{vehicle_info['name']}** cho cặp đôi!\n\n"
                f"🟡 **Chi phí:** `-{price:,} Thỏi Vàng` (trừ ví vàng cá nhân)\n"
                f"✨ **Buff thân mật:** `+{vehicle_info['buff']} pts/ngày` vào giới hạn thân mật hàng daily!{refund_msg}"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @couple_buy.command(name="pet", aliases=["thucung", "thu"], brief="Mua thú cưng cho cặp đôi.")
    async def couple_buy_pet(self, ctx: commands.Context, item_id: str):
        marriage, _ = self._resolve_marriage_and_args(ctx.author.id, [])
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn nên không thể mua thú cưng cặp đôi!")
            return

        user_one, user_two = marriage[0], marriage[1]
        item_id = item_id.lower().strip()
        if item_id not in COUPLE_PETS:
            await ctx.send(f"❌ ID thú cưng `{item_id}` không hợp lệ! Hãy gõ `i?couple shop` để xem danh sách.")
            return

        pet_info = COUPLE_PETS[item_id]
        price = pet_info["price"]

        profile = self.economy.get_entry(ctx.author.id)
        gold = profile[2]
        if gold < price:
            await ctx.send(f"❌ Bạn không đủ thỏi vàng! `{pet_info['name']}` có giá `{price:,} Thỏi Vàng`, nhưng bạn chỉ có `{gold:,} Thỏi Vàng`.")
            return

        assets = self.economy.get_couple_assets(user_one, user_two)
        refund_msg = ""
        if assets and assets[6] and assets[7] > 0 and assets[8] > 0:
            old_id, old_price, old_buyer = assets[6], assets[7], assets[8]
            if old_id == item_id:
                await ctx.send(f"❌ Cặp đôi của bạn hiện đã sở hữu {pet_info['name']} rồi!")
                return
            refund_amount = int(old_price * 0.25)
            if refund_amount > 0 and old_buyer > 0:
                self.economy.add_credits(old_buyer, refund_amount)
                old_name = COUPLE_PETS.get(old_id, {}).get("name", old_id)
                refund_msg = f"\n📦 **Thanh lý {old_name} cũ:** Hoàn lại 25% (`+{refund_amount:,} Thỏi Vàng`) cho <@{old_buyer}>."

        self.economy.add_credits(ctx.author.id, -price)
        self.economy.set_couple_pet(user_one, user_two, item_id, price, ctx.author.id)

        log_wallet_change(
            logger,
            event="couple_buy_pet",
            user_id=ctx.author.id,
            credits_delta=-price,
            pet_id=item_id,
            ctx=ctx
        )

        embed = make_embed(
            title="🐾 MUA THÚ CƯNG CẶP ĐÔI THÀNH CÔNG 🐾",
            description=(
                f"**{ctx.author.name}** đã nhận nuôi thành công **{pet_info['name']}** cho hai bạn!\n\n"
                f"🟡 **Chi phí:** `-{price:,} Thỏi Vàng` (trừ ví vàng cá nhân)\n"
                f"✨ **Buff thân mật:** `+{pet_info['buff']} pts/ngày` vào giới hạn thân mật hàng daily!{refund_msg}"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @couple_cmd.command(name="assets", aliases=["estate", "vehicle", "pet", "items", "taisan"], brief="Xem danh sách tài sản và buff của cặp đôi.", usage="couple assets [chỉ_số/người_dùng]")
    async def couple_assets_cmd(self, ctx: commands.Context, index_or_user: str = None, index: int = None):
        target_user = ctx.author
        target_index = 1
        
        if index_or_user is not None:
            try:
                target_index = int(index_or_user)
            except ValueError:
                try:
                    target_user = await commands.MemberConverter().convert(ctx, index_or_user)
                except commands.BadArgument:
                    await ctx.send("❌ Người dùng không hợp lệ!")
                    return
                if index is not None:
                    target_index = index
                    
        marriages = self.economy.get_marriages(target_user.id)
        if not marriages:
            await ctx.send(f"❌ {'Bạn' if target_user.id == ctx.author.id else target_user.name} chưa kết hôn!")
            return
            
        if target_index < 1 or target_index > len(marriages):
            await ctx.send(f"❌ Chỉ số cặp đôi không hợp lệ! (1 đến {len(marriages)})")
            return
            
        marriage = marriages[target_index - 1]
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        
        assets = self.economy.get_couple_assets(user_one, user_two)
        
        estate_str = "Chưa có"
        estate_buff = 0
        vehicle_str = "Chưa có"
        vehicle_buff = 0
        pet_str = "Chưa có"
        pet_buff = 0

        if assets:
            e_id, e_price, e_buyer, v_id, v_price, v_buyer, p_id, p_price, p_buyer = assets
            if e_id and e_id in COUPLE_ESTATES:
                e_info = COUPLE_ESTATES[e_id]
                estate_str = f"{e_info['name']} (`+{e_info['buff']} pts/ngày`)"
                estate_buff = e_info['buff']
            if v_id and v_id in COUPLE_VEHICLES:
                v_info = COUPLE_VEHICLES[v_id]
                vehicle_str = f"{v_info['name']} (`+{v_info['buff']} pts/ngày`)"
                vehicle_buff = v_info['buff']
            if p_id and p_id in COUPLE_PETS:
                p_info = COUPLE_PETS[p_id]
                pet_str = f"{p_info['name']} (`+{p_info['buff']} pts/ngày`)"
                pet_buff = p_info['buff']

        ring_base = 30 if ring_type == "ring_eternal_butterfly" else 20
        total_limit = ring_base + estate_buff + vehicle_buff + pet_buff
        ring_name = RINGS.get(ring_type, ring_type)

        desc = (
            f"💍 **Tín vật kết duyên:** {ring_name} (`{ring_base} pts/ngày`)\n\n"
            f"🏠 **Bất Động Sản:** {estate_str}\n"
            f"🚗 **Phương Tiện:** {vehicle_str}\n"
            f"🐾 **Thú Cưng:** {pet_str}\n\n"
            f"📊 **TỔNG GIỚI HẠN THÂN MẬT HÀNG NGÀY:**\n"
            f"💖 **`{total_limit} Điểm thân mật / ngày`** (Nhẫn {ring_base} + BĐS {estate_buff} + Xe {vehicle_buff} + Thú {pet_buff})"
        )

        embed = make_embed(
            title=f"🏰 TÀI SẢN PHU THÊ & BUFF CẶP ĐÔI 🏰",
            description=desc,
            color=discord.Color.magenta()
        )
        await ctx.send(embed=embed)


    async def process_interact(self, ctx: commands.Context, target: discord.Member, action: str, emoji: str, action_type: str):
        marriages = self.economy.get_marriages(ctx.author.id)
        if not marriages:
            await ctx.send(f"❌ Lệnh tương tác cặp đôi chỉ dành cho người đã kết hôn!")
            return
            
        # Find active marriage matching this target spouse
        active_marriage = None
        for m in marriages:
            m_user_one, m_user_two, *_ = m
            m_spouse_id = m_user_two if ctx.author.id == m_user_one else m_user_one
            if target.id == m_spouse_id:
                active_marriage = m
                break
                
        if not active_marriage:
            # Adultery (target is not one of active spouses)
            deduct_pts = 10
            
            # Deduct points from all marriages
            last_new_pts = 0
            for m in marriages:
                m_user_one, m_user_two, *_ = m
                last_new_pts = self.economy.deduct_love_points(m_user_one, m_user_two, deduct_pts)
                
            spouse_mentions = []
            for m in marriages:
                m_user_one, m_user_two, *_ = m
                m_spouse_id = m_user_two if ctx.author.id == m_user_one else m_user_one
                spouse_mentions.append(f"<@{m_spouse_id}>")
            spouse_list_str = " hoặc ".join(spouse_mentions)
            
            embed = make_embed(
                title="💔 PHÁT HIỆN NGOẠI TÌNH 💔",
                description=(
                    f"⚠️ **{ctx.author.mention}** đã tương tác thân mật ({action}) với **{target.mention}** "
                    f"trong khi đã kết hôn cùng {spouse_list_str}!\n\n"
                    f"💔 **Hành vi ngoại tình bị phát hiện!**\n"
                    f"📉 Toàn bộ gia đình của bạn bị phạt trừ `-{deduct_pts}` Điểm thân mật.\n"
                    f"💞 **Điểm thân mật hiện tại (couple gần nhất):** `{last_new_pts}` điểm."
                ),
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today = active_marriage

            
        # Try to add love points
        now = int(time.time())
        base_points = 10 if action_type == "Fuck" else 5
        
        # Ring buff intimacy multipliers from shop descriptions
        ring_love_buffs = {
            "ring_quartz": 0.02,
            "ring_aquamarine": 0.03,
            "ring_emerald": 0.04,
            "ring_amethyst": 0.05,
            "ring_cupid": 0.07,
            "ring_nhankat": 0.08,
            "ring_citrine": 0.09,
            "ring_ruby": 0.12,
            "ring_sapphire": 0.15,
            "ring_sunburst": 0.20,
            "ring_gothic": 0.25,
            "ring_angel": 0.30,
            "ring_divine": 0.50,
            "ring_eternal_butterfly": 0.15
        }
        
        if ring_type == "ring_eternal_butterfly":
            points_to_add = 15 if action_type == "Fuck" else 7
        else:
            buff_pct = ring_love_buffs.get(ring_type, 0.0)
            import math
            points_to_add = math.ceil(base_points * (1 + buff_pct))
            
        old_love_points = love_points
        assets = self.economy.get_couple_assets(user_one, user_two)
        total_limit = self._get_couple_daily_limit(ring_type, assets)
        new_points, success = self.economy.add_love_points(user_one, user_two, points_to_add, now, daily_limit=total_limit)
        added_points = new_points - old_love_points
        
        limit_desc = f"{total_limit} điểm/ngày"
        if success and added_points > 0:
            pts_msg = f" Bạn nhận được `+{added_points} Điểm thân mật` (Giới hạn tối đa {limit_desc})."
        else:
            pts_msg = f" (Hôm nay hai bạn đã đạt giới hạn tối đa {limit_desc})."
            
        embed_desc = f"{emoji} **{ctx.author.name}** đã trao một {action} nồng thắm cho bạn đời của mình **{target.name}**!{pts_msg}"
        sayings = INTERACT_SAYINGS.get(action_type, [])
        if sayings:
            saying = random.choice(sayings)
            embed_desc += f"\n\n*\" {saying} \"*"
            
        embed = make_embed(
            description=embed_desc,
            color=discord.Color.magenta()
        )
        
        gif_dir = ABS_PATH.parent.parent / "pictures" / "Marry" / action_type
        file = None
        if gif_dir.exists() and gif_dir.is_dir():
            gifs = list(gif_dir.glob("*.gif"))
            if gifs:
                chosen_gif = random.choice(gifs)
                file = discord.File(str(chosen_gif), filename="interact.gif")
                embed.set_image(url="attachment://interact.gif")
                
        if file:
            await ctx.send(embed=embed, file=file)
        else:
            await ctx.send(embed=embed)

    @commands.command(brief="Ôm bạn đời của mình.")
    async def hug(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cái ôm ấm áp", "🤗", "Hug")

    @commands.command(brief="Hôn bạn đời của mình.")
    async def kiss(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "nụ hôn nồng cháy", "💋", "Kiss")

    @commands.command(brief="Xoa đầu bạn đời của mình.")
    async def pat(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cái xoa đầu ngọt ngào", "👋", "Pat")

    @commands.command(brief="Ân ái nồng cháy với bạn đời của mình.")
    async def fuck(self, ctx: commands.Context, target: discord.Member):
        await self.process_interact(ctx, target, "cuộc ân ái nồng cháy", "🔞", "Fuck")

    @commands.command(
        brief="Hủy bỏ cuộc hôn nhân hiện tại (Ly hôn).",
        usage="divorce [chỉ_số]"
    )
    async def divorce(self, ctx: commands.Context, *, args_str: str = ""):
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            await ctx.send("❌ Bạn chưa kết hôn thì ly hôn cái gì?")
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try: spouse = await self.bot.fetch_user(spouse_id)
            except Exception: pass
            
        # Find index of this marriage
        marriages = self.economy.get_marriages(ctx.author.id)
        idx = marriages.index(marriage) + 1
        
        # Give two options
        # We check author cash for Unilateral divorce
        author_profile = self.economy.get_entry(ctx.author.id)
        cash = author_profile[1]
        
        unilateral_cost = max(10_000_000, int(cash * 0.10))
        
        embed = make_embed(
            title="💔 ĐƠN LY HÔN (DIVORCE MENU) 💔",
            description=(
                f"Bạn đang yêu cầu chấm dứt hôn nhân cùng <@{spouse_id}>.\n\n"
                f"Hãy chọn một trong hai phương án giải quyết dưới đây:\n"
                f"1️⃣ **Ly hôn Đồng Thuận (Mutual):** Gõ `i?divorcemutual {idx}` (Cả hai cùng ký đơn, không mất phí, quỹ chung chia đôi).\n"
                f"2️⃣ **Ly hôn Đơn Phương (Unilateral):** Gõ `i?divorceforce {idx}` (Không cần bên kia đồng ý, án phí tòa án rất đắt: **{unilateral_cost:,} VND** (10% ví của bạn), 50% án phí sẽ đền bù cho bạn đời của bạn)."
            ),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(name="divorcemutual", aliases=["divorce_mutual", "divmutual"], hidden=True)
    async def divorce_mutual(self, ctx: commands.Context, *, args_str: str = ""):
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            return
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        spouse = self.bot.get_user(spouse_id)
        if not spouse:
            try: spouse = await self.bot.fetch_user(spouse_id)
            except Exception: pass
            
        view = DivorceView(ctx.author, spouse, self.economy)
        embed = make_embed(
            title="📜 ĐƠN LY HÔN ĐỒNG THUẬN 📜",
            description=f"**{ctx.author.mention}** đề xuất ly hôn đồng thuận. Mời **{spouse.mention}** bấm nút ký đơn để xác nhận giải tán gia đình.",
            color=discord.Color.red()
        )
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @commands.command(name="divorceforce", aliases=["divorce_force", "divforce"], hidden=True)
    async def divorce_force(self, ctx: commands.Context, *, args_str: str = ""):
        args = args_str.split()
        marriage, remaining_args = self._resolve_marriage_and_args(ctx.author.id, args)
        if not marriage:
            return
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if ctx.author.id == user_one else user_one
        
        author_profile = self.economy.get_entry(ctx.author.id)
        cash = author_profile[1]
        
        unilateral_cost = max(10_000_000, int(cash * 0.10))
        if ring_type == "ring_eternal_butterfly":
            unilateral_cost = unilateral_cost // 2
            
        if cash < unilateral_cost:
            await ctx.send(f"❌ Bạn không đủ tiền mặt trong ví để trả án phí ly hôn đơn phương! Cần `{unilateral_cost:,} VND` nhưng bạn chỉ có `{cash:,} VND`.")
            return
            
        # Refund assets 25%
        refund_str = refund_couple_assets_on_divorce(self.economy, user_one, user_two)

        # Execute force divorce
        split = joint_wallet // 2
        self.economy.delete_marriage(user_one, user_two)
        
        # Apply economic penalty
        self.economy.add_money(ctx.author.id, -unilateral_cost)
        # 50% of the penalty is compensated to the spouse
        compensation = unilateral_cost // 2
        self.economy.add_money(spouse_id, compensation)
        
        # Split joint wallet
        if split > 0:
            self.economy.add_money(user_one, split)
            self.economy.add_money(user_two, split)
            
        log_wallet_change(
            logger,
            event="couple_divorce_force",
            user_id=ctx.author.id,
            money_delta=-unilateral_cost,
            spouse_id=spouse_id,
            compensation=compensation,
            split=split,
            ctx=ctx
        )
        
        embed = make_embed(
            title="💔 LY HÔN ĐƠN PHƯƠNG THÀNH CÔNG 💔",
            description=(
                f"**{ctx.author.mention}** đã đơn phương ly hôn cùng bạn đời.\n\n"
                f"💸 **Án phí khấu trừ:** `-{unilateral_cost:,} VND` từ ví của bạn.\n"
                f"🎁 **Bồi thường tổn thất phu thê:** chuyển `+{compensation:,} VND` cho <@{spouse_id}>.\n"
                f"🏦 **Quỹ chung chia đôi:** Mỗi người nhận lại `+{split:,} VND`."
                f"{refund_str}"
            ),
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)


    # ── ADMIN COMMANDS ──────────────────────────────────────────────────────────

    @commands.command(
        name="admindel_marry",
        aliases=["admin_divorce", "xoahonnhan"],
        brief="[ADMIN] Xoá hôn nhân của một người dùng bất kỳ.",
        usage="admindel_marry @user",
        hidden=True
    )
    async def admin_delete_marriage(self, ctx: commands.Context, target: str):
        """
        [ADMIN] Xoá toàn bộ hôn nhân của người dùng được chỉ định (bằng ID hoặc ping) mà không mất phí.
        Lệnh này dành cho Admin của server hoặc Chủ bot. Không có bồi thường và không có thông báo cho đương sự.
        """
        is_owner = ctx.author.id in config.bot.owner_ids or await ctx.bot.is_owner(ctx.author)
        is_admin = ctx.author.guild_permissions.administrator if ctx.guild else False
        if not (is_owner or is_admin):
            await ctx.send("❌ **Lỗi:** Lệnh này chỉ dành cho Admin của server hoặc Chủ bot!")
            return

        # Parse ID from ping or get raw ID
        target_clean = target.strip("<@!>")
        try:
            target_id = int(target_clean)
        except ValueError:
            await ctx.send("❌ **Lỗi:** Định dạng ID hoặc tag người dùng không hợp lệ!")
            return

        marriage = self.economy.get_marriage(target_id)
        if not marriage:
            await ctx.send(
                embed=make_embed(
                    title="❌ Không tìm thấy hôn nhân",
                    description=f"Người dùng có ID **{target_id}** hiện không có hôn nhân nào trong hệ thống.",
                    color=discord.Color.red()
                )
            )
            return

        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage

        # Resolve spouse
        spouse_id = user_two if target_id == user_one else user_one
        spouse = self.bot.get_user(spouse_id)
        spouse_name = spouse.name if spouse else f"ID:{spouse_id}"

        ring_name = RINGS.get(ring_type, ring_type)
        days = max(1, (int(time.time()) - married_at) // 86400)

        # Refund assets 25%
        refund_str = refund_couple_assets_on_divorce(self.economy, user_one, user_two)

        # Delete marriage record
        self.economy.delete_marriage(user_one, user_two)

        logger.warning(
            f"[ADMIN] {ctx.author} deleted marriage between "
            f"user_one={user_one} and user_two={user_two} "
            f"(ring={ring_type}, days={days}, joint_wallet={joint_wallet})"
        )

        embed = make_embed(
            title="🗑️ HÔN NHÂN ĐÃ BỊ XOÁ (ADMIN)",
            description=(
                f"Đã xoá thành công hôn nhân của cặp đôi:\n\n"
                f"👤 **Người 1:** <@{user_one}> (ID: `{user_one}`)\n"
                f"👤 **Người 2:** <@{user_two}> (ID: `{user_two}`)\n"
                f"💍 **Nhẫn:** {ring_name}\n"
                f"📅 **Thời gian kết hôn:** {days:,} ngày\n"
                f"🏦 **Quỹ chung bị xoá:** {joint_wallet:,} VND *(không hoàn trả)*"
                f"{refund_str}\n\n"
                f"⚠️ *Cặp đôi sẽ không nhận được thông báo tự động.*"
            ),
            color=discord.Color.dark_red()
        )
        embed.set_footer(text=f"Thực hiện bởi Admin: {ctx.author} | {ctx.author.id}")
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Marry(bot))
