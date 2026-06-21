import asyncio
import logging
import random
import time
import unicodedata
import re
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont
import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, ABS_PATH
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

def get_cock_image_file(name: str, fallback_to_default: bool = False) -> str | None:
    # 0. Check custom exclusive folder first
    root_path = ABS_PATH.parent.parent
    exclusive_dir = root_path / "pictures" / "exclusive_cocks"
    norm_name = name.lower().strip()
    if norm_name.startswith("gà "):
        norm_name = norm_name[3:]
    # remove accents
    norm_name = unicodedata.normalize('NFKD', norm_name).encode('ASCII', 'ignore').decode('utf-8')
    norm_name = re.sub(r'[^a-z0-9]', '', norm_name)
    custom_filename = f"{norm_name}.png"
    custom_path = exclusive_dir / custom_filename
    if custom_path.exists():
        return str(custom_path)

    # 1. Strict mapping for known breeds / characters (fallback logic)
    mapping = {
        "Goku (Ultra Instinct)": "Goku (Ultra Instinct).png",
        "Luffy (Gear 5)": "luffy-gear-5.png",
        "Naruto (Baryon Mode)": "Naruto-Baryon-Mode.png",
        "Saitama": "Saitama.png",
        "Gojo Satoru": "gojo .png",
        "Itachi Uchiha": "Itachi-Uchiha.png",
        "Vegeta": "vegeta.png",
        "Usopp": "usopp.png",
        "Killua": "Killua.png",
        "Sakura": "sakura.png",
        "Trunks": "trunks.png",
        "Levi Ackerman": "Levi-Ackerman.png",
        "Zoro": "zoro.png",
        "Akame": "akame.png",
        "Kakashi": "Kakashi.png",
        "Meliodas": "meliodas.png",
        "Ichigo": "ichigo.png",
        "Krillin": "krillin.png",
        "Zenitsu": "zenitsu.png",
        "Luffy": "luffy-gear-5.png",
        "Luffy Gear 4": "luffy-gear-5.png",
        "Doma": "douma.png",
        "Muzan": "Muzan.png",
        "Titan Thủy Tổ": "titan thuỷ tổ.png",
        "Titan Thủy Tổ Thức Tỉnh": "titan thuỷ tổ.png",
        "Madara (Giả)": "Madara.png",
        "Madara Thật": "Madara.png",
        "Kaguya": "Kaguya Otsutsuki.png",
        "Cell Hoàn Hảo": "perfect cell.png",
        "Majin Buu Hung Ác": "Majin Buu.png",
        "Kaido Người Cá": "Kaido.png",
        "Im Sama": "Imu.png",
        "Sukuna 2 Ngón": "Sukuna.png",
        "Sukuna Hoàn Chỉnh": "Sukuna.png"
    }
    
    for key, filename in mapping.items():
        if key.lower().strip() in name.lower().strip():
            path = ABS_PATH / "modules" / "daga" / filename
            if path.exists():
                return filename

    # Check if a custom anime image exists in modules/daga folder
    anime_file_path = ABS_PATH / "modules" / "daga" / custom_filename
    if anime_file_path.exists():
        return custom_filename

    # 2. Dynamic fallback check
    filename = f"{norm_name}.png"
    path = ABS_PATH / "modules" / "daga" / filename
    if path.exists():
        return filename

    # 3. Default fallback
    if fallback_to_default:
        default_path = ABS_PATH / "modules" / "daga" / "default_cock.png"
        if default_path.exists():
            return "default_cock.png"

    return None

def draw_hp_bar(draw, x_start, y_start, x_end, y_end, current_hp, max_hp, font):
    # draw background (red/gray)
    draw.rounded_rectangle([x_start, y_start, x_end, y_end], radius=4, fill=(80, 80, 80, 255))
    if max_hp <= 0:
        return
    pct = min(1.0, max(0.0, current_hp / max_hp))
    width = int((x_end - x_start) * pct)
    if width > 0:
        # draw green/yellow/red bar
        if pct > 0.5:
            bar_color = (46, 204, 113, 255) # Green
        elif pct > 0.2:
            bar_color = (241, 196, 15, 255) # Yellow
        else:
            bar_color = (231, 76, 60, 255) # Red
        draw.rounded_rectangle([x_start, y_start, x_start + width, y_end], radius=4, fill=bar_color)
    
    # draw text label in center
    label = f"{max(0, current_hp)}/{max_hp} HP"
    try:
        w = font.getlength(label)
    except AttributeError:
        w = len(label) * 7
    draw.text(((x_start + x_end) // 2 - w // 2, y_start + 1), label, font=font, fill=(255, 255, 255, 255))

def to_unsigned_ascii(text: str) -> str:
    emoji_replacements = {
        "✨": "[SKILL]",
        "🔥": "[BURN]",
        "⚔️": "[ATK]",
        "💥": "[CRIT]",
        "💨": "[DODGE]",
        "🛡️": "[SHIELD]",
        "💀": "[KO]",
        "🥊": "",
        "🟢": "",
        "🏆": "",
        "🤝": "",
        "💫": "[STUN]"
    }
    for emoji, rep in emoji_replacements.items():
        text = text.replace(emoji, rep)
        
    accents_map = {
        'a': 'áàảãạăắằẳẵặâấầẩẫậ',
        'A': 'ÁÀẢÃẠĂẮẰẲẴẶÂẤẦẨẪẬ',
        'd': 'đ',
        'D': 'Đ',
        'e': 'éèẻẽẹêếềểễệ',
        'E': 'ÉÈẺẼẸÊẾỀỂỄỆ',
        'i': 'íìỉĩị',
        'I': 'ÍÌỈĨỊ',
        'o': 'óòỏõọôốồổỗộơớờởỡợ',
        'O': 'ÓÒỎÕỌÔỐỒỔỖỘƠỚỜỞỠỢ',
        'u': 'úùủũụưứừửữự',
        'U': 'ÚÙỦŨỤƯỨỪỬỮỰ',
        'y': 'ýỳỷỹỵ',
        'Y': 'ÝỲỶỸỴ'
    }
    
    for ascii_char, accented_chars in accents_map.items():
        for char in accented_chars:
            text = text.replace(char, ascii_char)
            
    text = text.replace("**", "")
    
    clean_chars = []
    for c in text:
        val = ord(c)
        if 32 <= val <= 126:
            clean_chars.append(c)
    return "".join(clean_chars).strip()

def process_cock_image(filename: str, face_right: bool) -> Image.Image | None:
    from pathlib import Path
    if Path(filename).is_absolute():
        path = Path(filename)
    else:
        path = ABS_PATH / "modules" / "daga" / filename
        
    if not path.exists():
        return None
        
    # Original directions: True if facing left, False if facing right
    original_facing_left = {
        "thanhlong.png": True,
        "huyenvu.png": True,
        "xichlong.png": True,
        "chutuoc.png": False,
        "bachho.png": False,
        "kimo.png": False,
        "hacke.png": False,
        "default_cock.png": False,
    }
    
    has_banner = {"thanhlong.png", "chutuoc.png", "huyenvu.png", "bachho.png", "xichlong.png"}
    
    filename_name = Path(filename).name
    orig_left = original_facing_left.get(filename_name, False)
    
    # We want Left cock (User 1) to face RIGHT, Right cock (User 2) to face LEFT
    should_flip = (face_right and orig_left) or (not face_right and not orig_left)
    
    img = Image.open(path).convert("RGBA")
    img = img.resize((160, 160), Image.Resampling.LANCZOS)
    
    if should_flip:
        if filename_name in has_banner:
            width, height = img.size
            split_y = int(height * 0.80)
            top = img.crop((0, 0, width, split_y))
            bottom = img.crop((0, split_y, width, height))
            top_flipped = top.transpose(Image.FLIP_LEFT_RIGHT)
            
            flipped_img = Image.new("RGBA", (width, height))
            flipped_img.paste(top_flipped, (0, 0))
            flipped_img.paste(bottom, (0, split_y))
            img.close()
            return flipped_img
        else:
            flipped_img = img.transpose(Image.FLIP_LEFT_RIGHT)
            img.close()
            return flipped_img
            
    return img

def render_fight_frame(
    c1_name: str, c1_hp: int, c1_max_hp: int, c1_img_name: str,
    c2_name: str, c2_hp: int, c2_max_hp: int, c2_img_name: str,
    round_text: str, log_text: str
) -> BytesIO:
    c1_name = to_unsigned_ascii(c1_name)
    c2_name = to_unsigned_ascii(c2_name)
    round_text = to_unsigned_ascii(round_text)
    log_text = "\n".join(to_unsigned_ascii(line) for line in log_text.split("\n"))

    from app.discord_bot.modules.profile_renderer import load_font

    # 1. Load Background
    arena_path = ABS_PATH / "modules" / "daga" / "arena.png"
    if arena_path.exists():
        bg = Image.open(arena_path).convert("RGBA")
    else:
        # Fallback dark gradient/solid background
        bg = Image.new("RGBA", (800, 450), (26, 11, 46, 255))
        
    bg = bg.resize((800, 450), Image.Resampling.BILINEAR)
    draw = ImageDraw.Draw(bg)
    
    # 2. Draw glowing outline border
    draw.rounded_rectangle([6, 6, 794, 444], radius=16, outline=(255, 215, 0, 80), width=3)
    
    # 3. Load and paste Left Cock (User 1) - face right
    if c1_img_name:
        left_img = process_cock_image(c1_img_name, face_right=True)
        if left_img:
            bg.paste(left_img, (50, 180), mask=left_img)
            left_img.close()
            
    # 4. Load and paste Right Cock (User 2) - face left
    if c2_img_name:
        right_img = process_cock_image(c2_img_name, face_right=False)
        if right_img:
            bg.paste(right_img, (590, 180), mask=right_img)
            right_img.close()
            
    # 5. Fonts
    font_title = load_font("bold", 20)
    font_hp = load_font("bold", 12)
    font_log = load_font("regular", 14)
    font_round = load_font("bold", 24)
    
    # 6. Draw Names
    draw.text((50, 70), c1_name, font=font_title, fill=(255, 255, 255, 255))
    try:
        r_w = font_title.getlength(c2_name)
    except AttributeError:
        r_w = len(c2_name) * 12
    draw.text((750 - int(r_w), 70), c2_name, font=font_title, fill=(255, 255, 255, 255))
    
    # 7. Draw HP Bars
    draw_hp_bar(draw, 50, 100, 350, 118, c1_hp, c1_max_hp, font_hp)
    draw_hp_bar(draw, 450, 100, 750, 118, c2_hp, c2_max_hp, font_hp)
    
    # 8. Draw Round text (top center)
    try:
        round_w = font_round.getlength(round_text)
    except AttributeError:
        round_w = len(round_text) * 14
    draw.text((400 - int(round_w) // 2, 20), round_text, font=font_round, fill=(241, 196, 15, 255))
    
    # 9. Draw recent combat log in a frosted glass panel at the bottom center
    draw.rounded_rectangle(
        [50, 350, 750, 435],
        radius=10,
        fill=(255, 255, 255, 12),
        outline=(255, 255, 255, 25),
        width=1
    )
    
    # Accents on log panel borders
    draw.rounded_rectangle([50, 350, 54, 435], radius=10, fill=(241, 196, 15, 255))
    draw.rounded_rectangle([746, 350, 750, 435], radius=10, fill=(241, 196, 15, 255))
    
    y_offset = 360
    for line in log_text.split("\n"):
        if not line.strip():
            continue
        try:
            line_w = font_log.getlength(line)
        except AttributeError:
            line_w = len(line) * 7
        draw.text((400 - int(line_w) // 2, y_offset), line, font=font_log, fill=(255, 255, 255, 255))
        y_offset += 22
        if y_offset > 420:
            break
            
    # Save to BytesIO
    output = BytesIO()
    bg.save(output, format="PNG")
    output.seek(0)
    bg.close()
    return output

# Cock helper class mapping database row to attributes
GEAR_TIERS = {
    "Cựa Gỗ": "Common", "Giáp Da": "Common", "Khăn Đỏ": "Common",
    "Cựa Sắt": "Rare", "Giáp Đồng": "Rare", "Chuông Bạc": "Rare",
    "Cựa Thép": "Noble", "Giáp Thép": "Noble", "Bùa Ngọc": "Noble",
    "Cựa Dao": "Epic", "Giáp Hổ": "Epic", "Dây Chuyền Phượng": "Epic",
    "Cựa Thiên Lôi": "Legendary", "Giáp Kim Cang": "Legendary", "Ngọc Long": "Legendary",
    "Cựa Diệt Thần": "Mythic", "Giáp Thần Thú": "Mythic", "Linh Châu": "Mythic"
}

class Cock:
    def __init__(self, row):
        self.id = row[0]
        self.user_id = row[1]
        self.name = row[2]
        self.rarity = row[3]
        self.level = row[4]
        self.exp = row[5]
        self.hp = row[6]
        self.atk = row[7]
        self.df = row[8]
        self.spd = row[9]
        self.luk = row[10]
        self.weapon = row[11]
        self.armor = row[12]
        self.charm = row[13]
        self.is_active = row[14]
        self.wins = row[15]
        self.losses = row[16]
        self.streak = row[17]
        self.last_train = row[18]
        self.stars = row[19] if len(row) > 19 else 0
        self.shards = row[20] if len(row) > 20 else 0

    @property
    def display_name(self) -> str:
        if self.stars <= 0:
            return self.name
        stars_str = "⭐" * self.stars if self.stars <= 5 else f"⭐x{self.stars}"
        return f"{self.name} {stars_str}"

    @property
    def max_level(self) -> int:
        return 90 + 9 * self.stars

    def get_active_set(self) -> str | None:
        t1 = GEAR_TIERS.get(self.weapon)
        t2 = GEAR_TIERS.get(self.armor)
        t3 = GEAR_TIERS.get(self.charm)
        if t1 and t1 == t2 == t3:
            return t1
        return None

    def get_max_hp(self) -> int:
        bonus = 0
        if self.armor == "Giáp Hổ":
            bonus = 5
        elif self.armor == "Giáp Kim Cang":
            bonus = 20
        elif self.armor == "Giáp Thần Thú":
            bonus = 50
        
        hp_val = self.hp + bonus
        if self.get_active_set() == "Legendary":
            hp_val = int(hp_val * 1.2)
        return hp_val

    def get_atk(self) -> int:
        bonus = 0
        if self.weapon == "Cựa Gỗ":
            bonus = 3
        elif self.weapon == "Cựa Sắt":
            bonus = 6
        elif self.weapon == "Cựa Thép":
            bonus = 10
        elif self.weapon == "Cựa Dao":
            bonus = 15
        elif self.weapon == "Cựa Thiên Lôi":
            bonus = 20
        elif self.weapon == "Cựa Diệt Thần":
            bonus = 30
            
        atk_val = self.atk + bonus
        if self.get_active_set() == "Legendary":
            atk_val = int(atk_val * 1.2)
        return atk_val

    def get_df(self) -> int:
        bonus = 0
        if self.armor == "Giáp Da":
            bonus = 3
        elif self.armor == "Giáp Đồng":
            bonus = 6
        elif self.armor == "Giáp Thép":
            bonus = 10
        elif self.armor == "Giáp Hổ":
            bonus = 15
        elif self.armor == "Giáp Kim Cang":
            bonus = 20
        elif self.armor == "Giáp Thần Thú":
            bonus = 30
            
        df_val = self.df + bonus
        if self.get_active_set() == "Rare":
            df_val = int(df_val * 1.15)
        elif self.get_active_set() == "Legendary":
            df_val = int(df_val * 1.2)
        return df_val

    def get_spd(self) -> int:
        bonus = 0
        if self.weapon == "Cựa Dao":
            bonus = 5
        if self.charm == "Ngọc Long":
            bonus += 10
        elif self.charm == "Linh Châu":
            bonus += 20
            
        spd_val = self.spd + bonus
        if self.get_active_set() in ["Noble", "Epic"]:
            spd_val = int(spd_val * 1.15)
        elif self.get_active_set() == "Legendary":
            spd_val = int(spd_val * 1.2)
        return spd_val

    def get_luk(self) -> int:
        bonus = 0
        if self.charm == "Khăn Đỏ":
            bonus = 2
        elif self.charm == "Chuông Bạc":
            bonus = 5
        elif self.charm == "Bùa Ngọc":
            bonus = 8
        elif self.charm == "Dây Chuyền Phượng":
            bonus = 10
        elif self.charm == "Ngọc Long":
            bonus = 15
        elif self.charm == "Linh Châu":
            bonus = 20
            
        luk_val = self.luk + bonus
        if self.get_active_set() == "Legendary":
            luk_val = int(luk_val * 1.2)
        return luk_val

    def get_crit_chance(self) -> float:
        bonus = 0.0
        if self.weapon == "Cựa Thiên Lôi":
            bonus = 10.0
        elif self.weapon == "Cựa Diệt Thần":
            bonus = 15.0
        return bonus

    def get_dodge_bonus(self) -> float:
        bonus = 0.0
        if self.charm == "Linh Châu":
            bonus = 5.0
        return bonus

    def get_title(self) -> str:
        w = self.wins
        if w >= 1000:
            return "Huyền Thoại Anime 👑"
        elif w >= 500:
            return "Đại Sư Triệu Hồi 🏆"
        elif w >= 100:
            return "Bậc Thầy Triệu Hồi ⚔️"
        elif w >= 50:
            return "Nhà Lữ Hành 🛡️"
        elif w >= 10:
            return "Tân Binh 🔰"
        return "Người Mới 🌟"



def get_team_synergy(cocks: list) -> tuple[float, float, str | None, int]:
    """Calculate team synergy based on character series.
    Returns (atk_mult, def_mult, series_name, count)"""
    if len(cocks) < 2:
        return (1.0, 1.0, None, 0)
    
    series_count = {}
    for c in cocks:
        info = CHARACTER_INFO_MAP.get(c.name, None)
        if info:
            s = info["series"]
            series_count[s] = series_count.get(s, 0) + 1
    
    best_series = None
    best_count = 0
    for s, cnt in series_count.items():
        if cnt > best_count:
            best_count = cnt
            best_series = s
    
    if best_count >= 3:
        return (1.15, 1.10, f"Đội Hình Đồng Bộ ({best_series})", best_count)
    elif best_count >= 2:
        return (1.05, 1.0, best_series, best_count)
    return (1.0, 1.0, None, 0)




BREEDS = {
    "Thường": ["Usopp", "Krillin", "Zenitsu"],
    "Hiếm": ["Killua", "Sakura", "Trunks"],
    "Quý": ["Levi Ackerman", "Zoro", "Akame"],
    "Sử Thi": ["Kakashi", "Meliodas", "Ichigo"],
    "Huyền Thoại": ["Gojo Satoru", "Itachi Uchiha", "Vegeta"],
    "Thần Kê": ["Goku (Ultra Instinct)", "Luffy (Gear 5)", "Naruto (Baryon Mode)", "Saitama"],
    "Exclusive": ["Luffy"]
}

CHARACTER_INFO_MAP = {
    "Usopp": {"series": "One Piece", "active": "Bắn Tỉa", "passive": "Dũng Khí"},
    "Krillin": {"series": "Dragon Ball", "active": "Kienzan", "passive": "Chiến Binh Z"},
    "Zenitsu": {"series": "Kimetsu no Yaiba", "active": "Sấm Nhất Kiếm", "passive": "Ngủ Chiến"},
    "Killua": {"series": "Hunter x Hunter", "active": "Godspeed", "passive": "Sát Thủ Zoldyck"},
    "Sakura": {"series": "Naruto", "active": "Chakra Punch", "passive": "Hồi Phục"},
    "Trunks": {"series": "Dragon Ball", "active": "Kiếm Thần", "passive": "Saiyan Lai"},
    "Levi Ackerman": {"series": "Attack on Titan", "active": "Tấn Công Xoáy", "passive": "Ackerman"},
    "Zoro": {"series": "One Piece", "active": "Santoryu", "passive": "Thám Tử Kiếm"},
    "Akame": {"series": "Akame ga Kill", "active": "Murasame", "passive": "Sát Thủ"},
    "Kakashi": {"series": "Naruto", "active": "Chidori", "passive": "Sharingan"},
    "Meliodas": {"series": "Seven Deadly Sins", "active": "Full Counter", "passive": "Tội Phẫn Nộ"},
    "Ichigo": {"series": "Bleach", "active": "Getsuga Tensho", "passive": "Shinigami Thay Thế"},
    "Gojo Satoru": {"series": "Jujutsu Kaisen", "active": "Thuật Thức Vô Hạn", "passive": "Lục Nhãn"},
    "Itachi Uchiha": {"series": "Naruto", "active": "Amaterasu", "passive": "Mangekyou Sharingan"},
    "Vegeta": {"series": "Dragon Ball", "active": "Final Flash", "passive": "Hoàng Tử Saiyan"},
    "Goku (Ultra Instinct)": {"series": "Dragon Ball", "active": "Kamehameha x10", "passive": "Bản Năng Vô Cực"},
    "Luffy (Gear 5)": {"series": "One Piece", "active": "Gomu Thunder", "passive": "Nika"},
    "Luffy": {"series": "One Piece", "active": "Gomu Thunder", "passive": "Nika"},
    "Luffy Gear 4": {"series": "One Piece", "active": "Gear 4 - Leo Bazooka", "passive": "Nika"},
    "Naruto (Baryon Mode)": {"series": "Naruto", "active": "Rasengan Siêu Lớn", "passive": "Baryon"},
    "Saitama": {"series": "One Punch Man", "active": "Serious Punch", "passive": "Một Đấm"}
}

UPGRADED_SKILL_MAP = {
    "Usopp": "🎯 Kayaku Boshi (Ngôi Sao Thuốc Súng)",
    "Krillin": "☀️ Thái Dương Hạ San",
    "Zenitsu": "⚡ Điệu Hồn Sấm Sét",
    "Killua": "⚡ Lôi Kích (Lightning Palm)",
    "Sakura": "🌸 Bách Hào Thuật",
    "Trunks": "⚔️ Burning Attack",
    "Levi Ackerman": "🌀 Tự Do Chi Dực (Wings of Freedom)",
    "Zoro": "⚔️ Tam Thiên Thế Giới (Sanzen Sekai)",
    "Akame": "💀 Kịch Độc Murasame",
    "Kakashi": "⚡ Kamui Chidori",
    "Meliodas": "🔥 Thiên Long Kích (Divine Thousand Slashes)",
    "Ichigo": "⚔️ Saigo no Getsuga Tensho (Vô Nguyệt)",
    "Gojo Satoru": "🌀 Unlimited Void (Vô Lượng Không Xứ)",
    "Itachi Uchiha": "👁️ Tsukuyomi (Nguyệt Độc)",
    "Vegeta": "⚡ Final Flash (Tia Sáng Cuối Cùng)",
    "Goku (Ultra Instinct)": "🌟 Bản Năng Vô Cực Hoàn Hảo",
    "Luffy (Gear 5)": "⚡ Bajrang Gun (Thần Sấm Khổng Lồ)",
    "Luffy": "⚡ Bajrang Gun (Thần Sấm Khổng Lồ)",
    "Luffy Gear 4": "🦍 Gear 4 - King Cobra",
    "Naruto (Baryon Mode)": "🔥 Chế Độ Baryon (Baryon Mode)",
    "Saitama": "💥 Cú Đấm Nghiêm Túc"
}

RARITY_DISPLAY = {
    "Thường": "C",
    "Hiếm": "B",
    "Quý": "A",
    "Sử Thi": "S",
    "Huyền Thoại": "SS",
    "Thần Kê": "SSS",
    "Exclusive": "Exclusive"
}

STAT_RANGES = {
    "Thường": {"hp": (80, 100), "atk": (10, 15), "df": (8, 12), "spd": (8, 12), "luk": (5, 15)},
    "Hiếm": {"hp": (100, 120), "atk": (15, 20), "df": (12, 18), "spd": (12, 18), "luk": (10, 20)},
    "Quý": {"hp": (120, 140), "atk": (20, 28), "df": (18, 25), "spd": (18, 25), "luk": (15, 25)},
    "Sử Thi": {"hp": (140, 170), "atk": (28, 36), "df": (25, 32), "spd": (25, 32), "luk": (20, 30)},
    "Huyền Thoại": {"hp": (170, 210), "atk": (36, 48), "df": (32, 40), "spd": (32, 40), "luk": (25, 35)},
    "Thần Kê": {"hp": (210, 260), "atk": (48, 60), "df": (40, 50), "spd": (40, 50), "luk": (30, 45)},
    "Exclusive": {"hp": (500, 600), "atk": (100, 120), "df": (80, 100), "spd": (80, 100), "luk": (60, 80)}
}

INVENTORY_GEAR_NAMES = {
    "cua_go": "Cựa Gỗ (+3 Công)",
    "giap_da": "Giáp Da (+3 Thủ)",
    "khan_do": "Khăn Đỏ (+2 May)",
    "cua_sat": "Cựa Sắt (+6 Công)",
    "giap_dong": "Giáp Đồng (+6 Thủ)",
    "chuong_bac": "Chuông Bạc (+5 May)",
    "cua_thep": "Cựa Thép (+10 Công)",
    "giap_thep": "Giáp Thép (+10 Thủ)",
    "bua_ngoc": "Bùa Ngọc (+8 May)",
    "cua_dao": "Cựa Dao (+15 Công, +5 Tốc độ)",
    "giap_ho": "Giáp Hổ (+15 Thủ, +5 Máu)",
    "day_chuyen_phuong": "Dây Chuyền Phượng (+10 May)",
    "cua_thien_loi": "Cựa Thiên Lôi (+20 Công, +10% Chí mạng)",
    "giap_kim_cang": "Giáp Kim Cang (+20 Thủ, +20 Máu)",
    "ngoc_long": "Ngọc Long (+15 May, +10 Tốc độ)",
    "cua_diet_than": "Cựa Diệt Thần (+30 Công, +15% Chí mạng)",
    "giap_than_thu": "Giáp Thần Thú (+30 Thủ, +50 Máu)",
    "linh_chau": "Linh Châu (+20 May, +20 Tốc độ, 5% Né đòn)"
}

INVENTORY_FOOD_NAMES = {
    "food_thoc": "📕 Sách EXP Sơ Cấp (+10 EXP)",
    "food_ngo": "📘 Sách EXP Trung Cấp (+30 EXP)",
    "food_con_trung": "📙 Sách EXP Cao Cấp (+80 EXP)",
    "food_ca_nho": "📓 Sách EXP Cực Phẩm (+200 EXP)",
    "food_thit_bo": "🟢 Tụ Khí Đan (+500 EXP)",
    "food_hai_san": "💎 Linh Hồn Thạch (+1,000 EXP)",
    "food_trung_dd": "🧪 Thần Thú Huyết (+2,500 EXP)",
    "food_vitamin": "💊 Tẩy Tủy Đan (+5,000 EXP)",
    "food_nhan_sam": "🍄 Linh Chi Vạn Năm (+10,000 EXP)",
    "food_linh_duoc": "🍯 Hỗn Độn Linh Dịch (+50,000 EXP)",
    "item_stone_atk": "⚔️ Đá nâng ATK (+5 ATK)",
    "item_stone_def": "🛡️ Đá nâng DEF (+5 DEF)",
    "item_stone_spd": "⚡ Đá nâng SPD (+3 SPD)",
    "item_stone_breakthrough": "💎 Đá đột phá giới hạn cấp (+1 Sao)",
    "item_character_shard": "🔮 Mảnh nhân vật (Ghép S/SS tự chọn)"
}

GEAR_ID_MAP = {
    "1": ("cua_go", "weapon", "Cựa Gỗ"),
    "2": ("giap_da", "armor", "Giáp Da"),
    "3": ("khan_do", "charm", "Khăn Đỏ"),
    "4": ("cua_sat", "weapon", "Cựa Sắt"),
    "5": ("giap_dong", "armor", "Giáp Đồng"),
    "6": ("chuong_bac", "charm", "Chuông Bạc"),
    "7": ("cua_thep", "weapon", "Cựa Thép"),
    "8": ("giap_thep", "armor", "Giáp Thép"),
    "9": ("bua_ngoc", "charm", "Bùa Ngọc"),
    "10": ("cua_dao", "weapon", "Cựa Dao"),
    "11": ("giap_ho", "armor", "Giáp Hổ"),
    "12": ("day_chuyen_phuong", "charm", "Dây Chuyền Phượng"),
    "13": ("cua_thien_loi", "weapon", "Cựa Thiên Lôi"),
    "14": ("giap_kim_cang", "armor", "Giáp Kim Cang"),
    "15": ("ngoc_long", "charm", "Ngọc Long"),
    "16": ("cua_diet_than", "weapon", "Cựa Diệt Thần"),
    "17": ("giap_than_thu", "armor", "Giáp Thần Thú"),
    "18": ("linh_chau", "charm", "Linh Châu")
}

FOOD_DETAILS = {
    "1": {"item_id": "food_thoc", "name": "Sách EXP Sơ Cấp", "price": 20000, "exp": 10},
    "2": {"item_id": "food_ngo", "name": "Sách EXP Trung Cấp", "price": 54000, "exp": 30},
    "3": {"item_id": "food_con_trung", "name": "Sách EXP Cao Cấp", "price": 128000, "exp": 80},
    "4": {"item_id": "food_ca_nho", "name": "Sách EXP Cực Phẩm", "price": 280000, "exp": 200},
    "5": {"item_id": "food_thit_bo", "name": "Tụ Khí Đan", "price": 600000, "exp": 500},
    "6": {"item_id": "food_hai_san", "name": "Linh Hồn Thạch", "price": 1000000, "exp": 1000},
    "7": {"item_id": "food_trung_dd", "name": "Thần Thú Huyết", "price": 2250000, "exp": 2500},
    "8": {"item_id": "food_vitamin", "name": "Tẩy Tủy Đan", "price": 4000000, "exp": 5000},
    "9": {"item_id": "food_nhan_sam", "name": "Linh Chi Vạn Năm", "price": 7000000, "exp": 10000},
    "10": {"item_id": "food_linh_duoc", "name": "Hỗn Độn Linh Dịch", "price": 30000000, "exp": 50000},
    "11": {"item_id": "item_stone_atk", "name": "Đá nâng ATK", "price": 5000000, "exp": 0},
    "12": {"item_id": "item_stone_def", "name": "Đá nâng DEF", "price": 4000000, "exp": 0},
    "13": {"item_id": "item_stone_spd", "name": "Đá nâng SPD", "price": 4000000, "exp": 0},
    "14": {"item_id": "item_stone_breakthrough", "name": "Đá đột phá giới hạn cấp", "price": 50000000, "exp": 0},
    "15": {"item_id": "item_character_shard", "name": "Mảnh nhân vật", "price": 15000000, "exp": 0}
}

CHEST_DETAILS = {
    "1": {
        "name": "Hòm Thường",
        "price": 100_000,
        "rates": [("Common", 70), ("Rare", 25), ("Noble", 5)]
    },
    "2": {
        "name": "Hòm Cao Cấp",
        "price": 1_000_000,
        "rates": [("Rare", 50), ("Noble", 35), ("Epic", 13), ("Legendary", 2)]
    },
    "3": {
        "name": "Hòm Hoàng Kim",
        "price": 5_000_000,
        "rates": [("Noble", 40), ("Epic", 35), ("Legendary", 20), ("Mythic", 5)]
    }
}

ITEMS_BY_RARITY = {
    "Common": [("cua_go", "weapon", "Cựa Gỗ"), ("giap_da", "armor", "Giáp Da"), ("khan_do", "charm", "Khăn Đỏ")],
    "Rare": [("cua_sat", "weapon", "Cựa Sắt"), ("giap_dong", "armor", "Giáp Đồng"), ("chuong_bac", "charm", "Chuông Bạc")],
    "Noble": [("cua_thep", "weapon", "Cựa Thép"), ("giap_thep", "armor", "Giáp Thép"), ("bua_ngoc", "charm", "Bùa Ngọc")],
    "Epic": [("cua_dao", "weapon", "Cựa Dao"), ("giap_ho", "armor", "Giáp Hổ"), ("day_chuyen_phuong", "charm", "Dây Chuyền Phượng")],
    "Legendary": [("cua_thien_loi", "weapon", "Cựa Thiên Lôi"), ("giap_kim_cang", "armor", "Giáp Kim Cang"), ("ngoc_long", "charm", "Ngọc Long")],
    "Mythic": [("cua_diet_than", "weapon", "Cựa Diệt Thần"), ("giap_than_thu", "armor", "Giáp Thần Thú"), ("linh_chau", "charm", "Linh Châu")]
}

GEAR_INFO_DETAILS = {
    "cua_go": "+3 Công",
    "giap_da": "+3 Thủ",
    "khan_do": "+2 May mắn",
    "cua_sat": "+6 Công",
    "giap_dong": "+6 Thủ",
    "chuong_bac": "+5 May mắn",
    "cua_thep": "+10 Công",
    "giap_thep": "+10 Thủ",
    "bua_ngoc": "+8 May mắn",
    "cua_dao": "+15 Công\n+5 Tốc độ",
    "giap_ho": "+15 Thủ\n+5 Máu",
    "day_chuyen_phuong": "+10 May mắn",
    "cua_thien_loi": "+20 Công\n10% Chí mạng",
    "giap_kim_cang": "+20 Thủ\n+20 Máu",
    "ngoc_long": "+15 May mắn\n+10 Tốc độ",
    "cua_diet_than": "+30 Công\n15% Chí mạng",
    "giap_than_thu": "+30 Thủ\n+50 Máu",
    "linh_chau": "+20 May mắn\n+20 Tốc độ\n5% Né đòn"
}

def roll_rarity(rates: list[tuple[str, int]]) -> str:
    total = sum(r[1] for r in rates)
    roll = random.random() * total
    current = 0.0
    for rarity, chance in rates:
        current += chance
        if roll <= current:
            return rarity
    return rates[-1][0]


class AcceptFightView(discord.ui.View):
    def __init__(self, opponent: discord.Member, author: discord.Member, bet: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.opponent = opponent
        self.author = author
        self.bet = bet
        self.accepted = False

    @discord.ui.button(label="Chấp nhận thách đấu 🥊", style=discord.ButtonStyle.success)
    async def accept(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.accepted = True
        self.stop()
        try:
            await interaction.response.edit_message(content=f"✅ **{self.opponent.display_name}** đã chấp nhận thách đấu! Trận đấu đang diễn ra...", view=None)
        except Exception:
            pass

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.accepted = False
        self.stop()
        try:
            await interaction.response.edit_message(content=f"❌ **{self.opponent.display_name}** đã từ chối thách đấu.", view=None)
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.opponent.id:
            await interaction.response.send_message("Bạn không phải đối thủ được thách đấu!", ephemeral=True)
            return False
        return True


class SellOfferCockView(discord.ui.View):
    def __init__(self, user_id: int, price: int, cock_id: int, economy: Economy, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.price = price
        self.cock_id = cock_id
        self.economy = economy
        self.responded = False

    @discord.ui.button(label="Đồng ý bán 💰", style=discord.ButtonStyle.success)
    async def sell(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.responded = True
        self.stop()
        cock = self.economy.get_cock(self.cock_id)
        if not cock or cock[1] != self.user_id:
            await interaction.response.edit_message(content="❌ Chiến kê này không còn tồn tại hoặc không thuộc sở hữu của bạn.", view=None)
            return
        
        self.economy.add_money(self.user_id, self.price)
        self.economy.delete_cock(self.cock_id)
        
        log_wallet_change(
            logger,
            event="sell_cock_random_offer",
            user_id=self.user_id,
            money_delta=self.price,
            cock_id=self.cock_id,
        )
        
        try:
            await interaction.response.edit_message(content=f"✅ Bạn đã bán thành công **{cock[2]}** và nhận **+{self.price:,} VND**!", view=None)
        except Exception:
            pass

    @discord.ui.button(label="Từ chối ❌", style=discord.ButtonStyle.secondary)
    async def decline(self, interaction: discord.Interaction, _: discord.ui.Button):
        self.responded = True
        self.stop()
        try:
            await interaction.response.edit_message(content="❌ Bạn đã từ chối lời đề nghị mua gà.", view=None)
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("Lời đề nghị này không phải dành cho bạn!", ephemeral=True)
            return False
        return True
class DagaRateView(discord.ui.View):
    def __init__(self, author: discord.Member, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.current_page = 0
        self.message = None

    def get_embeds(self):
        # Page 0: Rates
        embed0 = make_embed(
            title="🔮 TỶ LỆ GACHA TRIỆU HỒI ANIME 🔮",
            description=(
                "### 🔮 TỶ LỆ CHIÊU MỘ NHÂN VẬT\n"
                "- **🔮 Banner Thường (1.000.000 VND):**\n"
                "  - <:698204c:1515422780370190377> C: **60%** | <:759990b:1515423304620703905> B: **30%** | <:780661a:1515423318587609224> A: **9%** | <:429893s:1515423348014715091> S: **0.8%** | <:915638ss:1515423361310785536> SS: **0.2%**\n"
                "- **🔮 Banner Xịn (5.000.000 VND):**\n"
                "  - <:759990b:1515423304620703905> B: **40%** | <:780661a:1515423318587609224> A: **45%** | <:429893s:1515423348014715091> S: **12%** | <:915638ss:1515423361310785536> SS: **3%**\n"
                "  *ℹ️ Có bảo hiểm (Pity) 50 lần mở liên tiếp không ra SS.*"
            ),
            color=discord.Color.gold()
        )
        embed0.set_footer(text="Trang 1/2 • Tỷ lệ Gacha")

        # Page 1: Anime Characters & Stats
        embed1 = make_embed(
            title="⚔️ NHÂN VẬT ANIME & CHỈ SỐ GỐC 📊",
            description=(
                "- <:698204c:1515422780370190377> **C:** `Usopp`, `Krillin`, `Zenitsu`\n"
                "  - *Chỉ số gốc:* ❤️ 80-100 | ⚔️ 10-15 | 🛡️ 8-12 | ⚡ 8-12 | 🍀 5-15\n"
                "- <:759990b:1515423304620703905> **B:** `Killua`, `Sakura`, `Trunks`\n"
                "  - *Chỉ số gốc:* ❤️ 100-120 | ⚔️ 15-20 | 🛡️ 12-18 | ⚡ 12-18 | 🍀 10-20\n"
                "- <:780661a:1515423318587609224> **A:** `Levi Ackerman`, `Zoro`, `Akame`\n"
                "  - *Chỉ số gốc:* ❤️ 120-140 | ⚔️ 20-28 | 🛡️ 18-25 | ⚡ 18-25 | 🍀 15-25\n"
                "- <:429893s:1515423348014715091> **S:** `Kakashi`, `Meliodas`, `Ichigo`\n"
                "  - *Chỉ số gốc:* ❤️ 140-170 | ⚔️ 28-36 | 🛡️ 25-32 | ⚡ 25-32 | 🍀 20-30\n"
                "- <:915638ss:1515423361310785536> **SS:** `Gojo Satoru`, `Itachi Uchiha`, `Vegeta`\n"
                "  - *Chỉ số gốc:* ❤️ 170-210 | ⚔️ 36-48 | 🛡️ 32-40 | ⚡ 32-40 | 🍀 25-35"
            ),
            color=discord.Color.green()
        )
        embed1.set_footer(text="Trang 2/2 • Nhân Vật & Chỉ Số")

        return [embed0, embed1]

    def update_buttons(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.custom_id == f"page_{self.current_page}":
                    child.style = discord.ButtonStyle.primary
                else:
                    child.style = discord.ButtonStyle.secondary

    @discord.ui.button(label="Tỷ Lệ 🔮", style=discord.ButtonStyle.primary, custom_id="page_0")
    async def page_rates(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        embeds = self.get_embeds()
        await interaction.response.edit_message(embed=embeds[0], view=self)

    @discord.ui.button(label="Nhân Vật ⚔️", style=discord.ButtonStyle.secondary, custom_id="page_1")
    async def page_cocks(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 1
        self.update_buttons()
        embeds = self.get_embeds()
        await interaction.response.edit_message(embed=embeds[1], view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Lệnh này không phải của bạn!", ephemeral=True)
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

class CockListView(discord.ui.View):
    def __init__(self, author: discord.Member, cocks_rows: list, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.cocks_rows = cocks_rows
        self.current_page = 0
        self.per_page = 10
        self.message = None
        self.update_buttons()

    def get_embed(self) -> discord.Embed:
        start_idx = self.current_page * self.per_page
        end_idx = start_idx + self.per_page
        page_rows = self.cocks_rows[start_idx:end_idx]

        rarity_emojis = {
            "Thường": "<:698204c:1515422780370190377>",
            "Hiếm": "<:759990b:1515423304620703905>",
            "Quý": "<:780661a:1515423318587609224>",
            "Sử Thi": "<:429893s:1515423348014715091>",
            "Huyền Thoại": "<:915638ss:1515423361310785536>",
            "Thần Kê": "<:886814sss:1515423524167225415>",
            "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
        }

        desc = ""
        for row in page_rows:
            c = Cock(row)
            active_marker = " 👑 **[ĐANG XUẤT TRẬN]**" if c.is_active else ""
            shards_progress = f" *({c.shards}/{c.stars + 1} mảnh)*" if (c.stars > 0 or c.shards > 0) else ""
            desc += f"`ID: {c.id}` - **{c.display_name}**{shards_progress} {rarity_emojis.get(c.rarity, '')} - Cấp `{c.level}`{active_marker}\n"

        total_pages = max(1, (len(self.cocks_rows) + self.per_page - 1) // self.per_page)
        
        embed = make_embed(
            title=f"⚔️ KHO NHÂN VẬT CỦA {self.author.name.upper()} ⚔️",
            description=desc or "Không có nhân vật nào ở trang này.",
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=self.author.display_avatar.url)
        embed.set_footer(text=f"Trang {self.current_page + 1}/{total_pages} • Tổng số nhân vật: {len(self.cocks_rows)}")
        return embed

    def update_buttons(self):
        total_pages = max(1, (len(self.cocks_rows) + self.per_page - 1) // self.per_page)
        self.prev_page.disabled = (self.current_page == 0)
        self.next_page.disabled = (self.current_page >= total_pages - 1)

    @discord.ui.button(label="◀️ Trang trước", style=discord.ButtonStyle.primary)
    async def prev_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page -= 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Trang sau ▶️", style=discord.ButtonStyle.primary)
    async def next_page(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page += 1
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Lệnh này không phải của bạn!", ephemeral=True)
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


class NangSaoInteractiveView(discord.ui.View):
    def __init__(self, author: discord.Member, economy, c_main=None, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.economy = economy
        self.c_main = c_main
        self.message = None
        self.setup_ui()

    def setup_ui(self):
        self.clear_items()
        
        if self.c_main is None:
            # Phase 1: Select Main Character
            cocks_rows = self.economy.get_cocks(self.author.id)
            if not cocks_rows:
                return
            
            # Show first 25 characters
            options = []
            for row in cocks_rows[:25]:
                c = Cock(row)
                star_label = f" ({c.stars}⭐)" if c.stars > 0 else ""
                display_rarity = RARITY_DISPLAY.get(c.rarity, c.rarity)
                options.append(
                    discord.SelectOption(
                        label=f"ID: {c.id} - {c.name}{star_label} [{display_rarity}]",
                        value=str(c.id),
                        description=f"Cấp: {c.level} | HP: {c.hp} | ATK: {c.atk}"
                    )
                )
            
            select = discord.ui.Select(placeholder="Chọn nhân vật muốn đột phá...", options=options)
            select.callback = self.on_main_selected
            self.add_item(select)
        else:
            # Phase 2: Breakthrough Confirmation
            # Find duplicate candidate cards from DB (not main, not active)
            breed_names = [self.c_main.name]
            if self.c_main.name in ("Luffy", "Luffy Gear 4"):
                breed_names = ["Luffy", "Luffy Gear 4"]
            placeholders = ", ".join("?" for _ in breed_names)
            
            self.economy.cur.execute(
                f"""SELECT * FROM user_cocks 
                   WHERE user_id=? AND name IN ({placeholders}) AND id!=? AND is_active=0""",
                tuple([self.author.id] + breed_names + [self.c_main.id])
            )
            candidates = self.economy.cur.fetchall()
            
            total_duplicates = self.c_main.shards + len(candidates)
            needed = self.c_main.stars + 1
            
            # Add Breakthrough button
            btn_confirm = discord.ui.Button(
                label="Đột phá",
                style=discord.ButtonStyle.success,
                emoji="💥",
                disabled=(total_duplicates < needed)
            )
            btn_confirm.callback = self.on_breakthrough_confirmed
            self.add_item(btn_confirm)
            
            # Add Cancel / Keep button
            btn_cancel = discord.ui.Button(
                label="Giữ lại",
                style=discord.ButtonStyle.danger,
                emoji="❌"
            )
            btn_cancel.callback = self.on_back_clicked
            self.add_item(btn_cancel)

    def get_embed(self) -> discord.Embed:
        if self.c_main is None:
            embed = make_embed(
                title="⭐ ĐỘT PHÁ NHÂN VẬT ⭐",
                description="Hãy chọn nhân vật chính bạn muốn đột phá từ menu thả xuống dưới đây:",
                color=discord.Color.gold()
            )
            embed.set_thumbnail(url=self.author.display_avatar.url)
            return embed
        else:
            breed_names = [self.c_main.name]
            if self.c_main.name in ("Luffy", "Luffy Gear 4"):
                breed_names = ["Luffy", "Luffy Gear 4"]
            placeholders = ", ".join("?" for _ in breed_names)
            
            self.economy.cur.execute(
                f"""SELECT * FROM user_cocks 
                   WHERE user_id=? AND name IN ({placeholders}) AND id!=? AND is_active=0""",
                tuple([self.author.id] + breed_names + [self.c_main.id])
            )
            candidates = self.economy.cur.fetchall()
            
            total_duplicates = self.c_main.shards + len(candidates)
            total_owned = 1 + total_duplicates
            needed = self.c_main.stars + 1
            
            display_rarity = RARITY_DISPLAY.get(self.c_main.rarity, self.c_main.rarity)
            current_max = 90 + 9 * self.c_main.stars
            next_max = current_max + 9
            new_skill = UPGRADED_SKILL_MAP.get(self.c_main.name, "🌀 Kỹ năng tối thượng")
            
            desc = (
                f"Bạn có **{total_owned}x {self.c_main.name} {display_rarity}**\n"
                f"Dùng **{needed} thẻ trùng** để đột phá:\n"
                f"  Max Level: **{current_max}** → **{next_max}**\n"
                f"  Kỹ năng mới: {new_skill}\n"
                f"  Chỉ số **+30%** toàn bộ\n"
            )
            if total_duplicates < needed:
                desc += f"\n❌ **Không đủ thẻ trùng:** Bạn cần {needed} thẻ trùng nhưng chỉ có {total_duplicates}."
                
            embed = make_embed(
                title=f"💥 BREAKTHROUGH — {self.c_main.name}",
                description="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n" + desc,
                color=discord.Color.red()
            )
            return embed

    async def on_main_selected(self, interaction: discord.Interaction):
        cid = int(interaction.data["values"][0])
        row = self.economy.get_cock(cid)
        if not row:
            await interaction.response.send_message("Không tìm thấy nhân vật!", ephemeral=True)
            return
        
        self.c_main = Cock(row)
        self.setup_ui()
        
        embed = self.get_embed()
        img_name = get_cock_image_file(self.c_main.name)
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_thumbnail(url=f"attachment://{img_name}")
            await interaction.response.edit_message(embed=embed, view=self, attachments=[file])
        else:
            embed.set_thumbnail(url=self.author.display_avatar.url)
            await interaction.response.edit_message(embed=embed, view=self, attachments=[])

    async def on_back_clicked(self, interaction: discord.Interaction):
        self.c_main = None
        self.setup_ui()
        await interaction.response.edit_message(embed=self.get_embed(), view=self, attachments=[])

    async def on_breakthrough_confirmed(self, interaction: discord.Interaction):
        # Double check candidate duplicates
        breed_names = [self.c_main.name]
        if self.c_main.name in ("Luffy", "Luffy Gear 4"):
            breed_names = ["Luffy", "Luffy Gear 4"]
        placeholders = ", ".join("?" for _ in breed_names)
        self.economy.cur.execute(
            f"""SELECT * FROM user_cocks 
               WHERE user_id=? AND name IN ({placeholders}) AND id!=? AND is_active=0""",
            tuple([self.author.id] + breed_names + [self.c_main.id])
        )
        candidates = self.economy.cur.fetchall()
        
        total_duplicates = self.c_main.shards + len(candidates)
        needed = self.c_main.stars + 1
        
        if total_duplicates < needed:
            await interaction.response.send_message("❌ **Lỗi:** Không đủ thẻ trùng để đột phá!", ephemeral=True)
            return
            
        # Consume candidates (delete duplicate rows) first
        candidates_to_delete = candidates[:needed]
        for cand in candidates_to_delete:
            self.economy.delete_cock(cand[0])
            
        # Consume from shards next
        remaining_needed = needed - len(candidates_to_delete)
        new_shards = self.c_main.shards - remaining_needed
        
        # Calculate new stats (30% increase)
        new_stars = self.c_main.stars + 1
        new_hp = int(self.c_main.hp * 1.3)
        new_atk = int(self.c_main.atk * 1.3)
        new_df = int(self.c_main.df * 1.3)
        new_spd = int(self.c_main.spd * 1.3)
        new_luk = int(self.c_main.luk * 1.3)
        
        new_name = self.c_main.name
        # Evolution check for Luffy -> Luffy Gear 4
        if self.c_main.name == "Luffy" and new_stars >= 6:
            new_name = "Luffy Gear 4"
            new_hp = int(self.c_main.hp * 2.0)
            new_atk = int(self.c_main.atk * 2.0)
            new_df = int(self.c_main.df * 2.0)
            new_spd = int(self.c_main.spd * 2.0)
            new_luk = int(self.c_main.luk * 2.0)
            
        kwargs = {
            "stars": new_stars,
            "shards": new_shards,
            "hp": new_hp,
            "atk": new_atk,
            "df": new_df,
            "spd": new_spd,
            "luk": new_luk
        }
        if new_name != self.c_main.name:
            kwargs["name"] = new_name
            
        self.economy.update_cock(self.c_main.id, **kwargs)
        
        self.clear_items()
        
        rarity_emojis = {
            "Thường": "<:698204c:1515422780370190377>",
            "Hiếm": "<:759990b:1515423304620703905>",
            "Quý": "<:780661a:1515423318587609224>",
            "Sử Thi": "<:429893s:1515423348014715091>",
            "Huyền Thoại": "<:915638ss:1515423361310785536>",
            "Thần Kê": "<:886814sss:1515423524167225415>",
            "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
        }
        
        star_emoji_str = "⭐" * new_stars if new_stars <= 5 else f"⭐x{new_stars}"
        display_rarity = RARITY_DISPLAY.get(self.c_main.rarity, self.c_main.rarity)
        
        desc = (
            f"🎉 **ĐỘT PHÁ THÀNH CÔNG!** 🎉\n\n"
            f"⚔️ **Nhân vật:** `{self.c_main.name}` ({star_emoji_str})\n"
            f"👑 **Độ hiếm:** {rarity_emojis.get(self.c_main.rarity, '')} `{display_rarity}`\n"
            f"❤️ **Máu (HP):** `{new_hp}` *(Tăng lên {new_stars} Sao)*\n"
            f"⚔️ **Sát thương (ATK):** `{new_atk}`\n"
            f"🛡️ **Phòng thủ (DEF):** `{new_df}`\n"
            f"⚡ **Tốc độ (SPD):** `{new_spd}`\n"
            f"🍀 **May mắn (LUK):** `{new_luk}`\n\n"
            f"🔥 Đã tiêu thụ `{needed}` thẻ trùng làm nguyên liệu đột phá."
        )
        
        embed = make_embed(
            title="💥 ĐỘT PHÁ NHÂN VẬT THÀNH CÔNG 💥",
            description=desc,
            color=discord.Color.green()
        )
        
        img_name = get_cock_image_file(self.c_main.name)
        if img_name:
            embed.set_thumbnail(url=f"attachment://{img_name}")
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Lệnh này không phải của bạn!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        self.clear_items()
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass



class PveBoss:
    def __init__(self, data):
        self.name = data["name"]
        self.hp = data["hp"]
        self.max_hp = data.get("max_hp", data["hp"])
        self.atk = data["atk"]
        self.df = data["df"]
        self.spd = data["spd"]
        self.luk = data["luk"]
        self.skills = data.get("skills", [])
        self.level = 50
        self.stars = 0
        self.shards = 0
        self.weapon = "None"
        self.armor = "None"
        self.charm = "None"

    @property
    def display_name(self) -> str:
        return self.name

    def get_max_hp(self) -> int:
        return self.max_hp

    def get_atk(self) -> int:
        return self.atk

    def get_df(self) -> int:
        return self.df

    def get_spd(self) -> int:
        return self.spd

    def get_luk(self) -> int:
        return self.luk

    def get_crit_chance(self) -> float:
        return 5.0

    def get_dodge_bonus(self) -> float:
        return 0.0

    def get_active_set(self) -> str:
        return "None"



PVE_STAGES = {
    "tower": [
        {"floor": 1, "name": "Quỷ Nhện Hạ Cấp", "series": "Kimetsu", "hp": 300, "atk": 25, "df": 15, "spd": 12, "luk": 5, "skills": [], "reward_money": 5000, "reward_exp": 30},
        {"floor": 2, "name": "Zombie Titan Nhỏ", "series": "AOT", "hp": 350, "atk": 28, "df": 18, "spd": 10, "luk": 5, "skills": [], "reward_money": 6000, "reward_exp": 35},
        {"floor": 3, "name": "Akatsuki Tép Riu", "series": "Naruto", "hp": 400, "atk": 32, "df": 20, "spd": 14, "luk": 6, "skills": [], "reward_money": 7000, "reward_exp": 40},
        {"floor": 4, "name": "Saiyan Lính Thường", "series": "Dragon Ball", "hp": 450, "atk": 35, "df": 22, "spd": 15, "luk": 6, "skills": [], "reward_money": 8000, "reward_exp": 45},
        {"floor": 5, "name": "Doma", "series": "Kimetsu", "hp": 800, "atk": 55, "df": 40, "spd": 25, "luk": 10, "skills": [], "reward_money": 15000, "reward_exp": 80, "reward_shards": 1},
        {"floor": 6, "name": "Cướp Biển Vô Danh", "series": "One Piece", "hp": 500, "atk": 38, "df": 24, "spd": 16, "luk": 7, "skills": [], "reward_money": 9000, "reward_exp": 50},
        {"floor": 7, "name": "Quỷ Nhện Trung Cấp", "series": "Kimetsu", "hp": 550, "atk": 42, "df": 26, "spd": 17, "luk": 7, "skills": [], "reward_money": 10000, "reward_exp": 55},
        {"floor": 8, "name": "Hollow Cấp Thấp", "series": "Bleach", "hp": 600, "atk": 45, "df": 28, "spd": 18, "luk": 8, "skills": [], "reward_money": 11000, "reward_exp": 60},
        {"floor": 9, "name": "Cursed Spirit Thường", "series": "Jujutsu Kaisen", "hp": 650, "atk": 48, "df": 30, "spd": 19, "luk": 8, "skills": [], "reward_money": 12000, "reward_exp": 65},
        {"floor": 10, "name": "Muzan", "series": "Kimetsu", "hp": 1500, "atk": 80, "df": 55, "spd": 35, "luk": 15, "skills": [], "reward_money": 30000, "reward_exp": 150, "reward_shards": 2},
        {"floor": 11, "name": "Titan 5m", "series": "AOT", "hp": 700, "atk": 50, "df": 32, "spd": 20, "luk": 9, "skills": [], "reward_money": 13000, "reward_exp": 70},
        {"floor": 12, "name": "Ninja Âm Bộ", "series": "Naruto", "hp": 750, "atk": 52, "df": 34, "spd": 22, "luk": 9, "skills": [], "reward_money": 14000, "reward_exp": 75},
        {"floor": 13, "name": "Frieza Soldier", "series": "Dragon Ball", "hp": 800, "atk": 55, "df": 36, "spd": 23, "luk": 10, "skills": [], "reward_money": 15000, "reward_exp": 80},
        {"floor": 14, "name": "Marine Captain", "series": "One Piece", "hp": 850, "atk": 58, "df": 38, "spd": 24, "luk": 10, "skills": [], "reward_money": 16000, "reward_exp": 85},
        {"floor": 15, "name": "Titan Thủy Tổ", "series": "AOT", "hp": 1800, "atk": 90, "df": 65, "spd": 30, "luk": 12, "skills": [], "reward_money": 35000, "reward_exp": 160, "reward_shards": 2},
        {"floor": 16, "name": "Arrancar Cấp Thấp", "series": "Bleach", "hp": 900, "atk": 60, "df": 40, "spd": 25, "luk": 11, "skills": [], "reward_money": 17000, "reward_exp": 90},
        {"floor": 17, "name": "Cursed Spirit Đặc Cấp", "series": "Jujutsu Kaisen", "hp": 950, "atk": 63, "df": 42, "spd": 26, "luk": 11, "skills": [], "reward_money": 18000, "reward_exp": 95},
        {"floor": 18, "name": "Quincy Thường", "series": "Bleach", "hp": 1000, "atk": 65, "df": 44, "spd": 27, "luk": 12, "skills": [], "reward_money": 19000, "reward_exp": 100},
        {"floor": 19, "name": "Homunculus", "series": "FMA", "hp": 1050, "atk": 68, "df": 46, "spd": 28, "luk": 12, "skills": [], "reward_money": 20000, "reward_exp": 105},
        {"floor": 20, "name": "Titan Thủy Tổ Thức Tỉnh", "series": "AOT", "hp": 2200, "atk": 100, "df": 75, "spd": 35, "luk": 15, "skills": [], "reward_money": 45000, "reward_exp": 200, "reward_shards": 3},
        {"floor": 21, "name": "Espada Số 9", "series": "Bleach", "hp": 1100, "atk": 70, "df": 48, "spd": 29, "luk": 13, "skills": [], "reward_money": 22000, "reward_exp": 110},
        {"floor": 22, "name": "Demon Cấp S", "series": "One Punch Man", "hp": 1150, "atk": 72, "df": 50, "spd": 30, "luk": 13, "skills": [], "reward_money": 23000, "reward_exp": 115},
        {"floor": 23, "name": "Chimera Ant Binh", "series": "HxH", "hp": 1200, "atk": 75, "df": 52, "spd": 31, "luk": 14, "skills": [], "reward_money": 24000, "reward_exp": 120},
        {"floor": 24, "name": "Pillar Man", "series": "JoJo", "hp": 1250, "atk": 78, "df": 54, "spd": 32, "luk": 14, "skills": [], "reward_money": 25000, "reward_exp": 125},
        {"floor": 25, "name": "Madara (Giả)", "series": "Naruto", "hp": 2500, "atk": 110, "df": 80, "spd": 38, "luk": 16, "skills": [], "reward_money": 50000, "reward_exp": 220, "reward_shards": 3},
        {"floor": 26, "name": "Walpurgis", "series": "Madoka", "hp": 1300, "atk": 80, "df": 56, "spd": 33, "luk": 15, "skills": [], "reward_money": 27000, "reward_exp": 130},
        {"floor": 27, "name": "Demon King Soldier", "series": "Seven Deadly Sins", "hp": 1350, "atk": 82, "df": 58, "spd": 34, "luk": 15, "skills": [], "reward_money": 28000, "reward_exp": 135},
        {"floor": 28, "name": "Nomu Cao Cấp", "series": "MHA", "hp": 1400, "atk": 85, "df": 60, "spd": 35, "luk": 16, "skills": [], "reward_money": 30000, "reward_exp": 140},
        {"floor": 29, "name": "Gillian", "series": "Bleach", "hp": 1450, "atk": 88, "df": 62, "spd": 36, "luk": 16, "skills": [], "reward_money": 32000, "reward_exp": 145},
        {"floor": 30, "name": "Kaguya", "series": "Naruto", "hp": 3000, "atk": 120, "df": 90, "spd": 42, "luk": 18, "skills": [], "reward_money": 60000, "reward_exp": 250, "reward_shards": 4},
        {"floor": 31, "name": "Vasto Lorde", "series": "Bleach", "hp": 1500, "atk": 90, "df": 64, "spd": 37, "luk": 17, "skills": [], "reward_money": 34000, "reward_exp": 150},
        {"floor": 32, "name": "Royal Guard", "series": "HxH", "hp": 1550, "atk": 92, "df": 66, "spd": 38, "luk": 17, "skills": [], "reward_money": 36000, "reward_exp": 155},
        {"floor": 33, "name": "Demon Dragon", "series": "One Punch Man", "hp": 1600, "atk": 95, "df": 68, "spd": 39, "luk": 18, "skills": [], "reward_money": 38000, "reward_exp": 160},
        {"floor": 34, "name": "Stand User Cấp A", "series": "JoJo", "hp": 1650, "atk": 98, "df": 70, "spd": 40, "luk": 18, "skills": [], "reward_money": 40000, "reward_exp": 165},
        {"floor": 35, "name": "Cell Hoàn Hảo", "series": "Dragon Ball", "hp": 3500, "atk": 130, "df": 95, "spd": 45, "luk": 20, "skills": [], "reward_money": 70000, "reward_exp": 280, "reward_shards": 4},
        {"floor": 36, "name": "Espada Số 4", "series": "Bleach", "hp": 1700, "atk": 100, "df": 72, "spd": 41, "luk": 19, "skills": [], "reward_money": 42000, "reward_exp": 170},
        {"floor": 37, "name": "Demon Cấp Dragon", "series": "One Punch Man", "hp": 1750, "atk": 102, "df": 74, "spd": 42, "luk": 19, "skills": [], "reward_money": 44000, "reward_exp": 175},
        {"floor": 38, "name": "Chimera Ant King Guard", "series": "HxH", "hp": 1800, "atk": 105, "df": 76, "spd": 43, "luk": 20, "skills": [], "reward_money": 46000, "reward_exp": 180},
        {"floor": 39, "name": "Quincy Sternritter", "series": "Bleach", "hp": 1850, "atk": 108, "df": 78, "spd": 44, "luk": 20, "skills": [], "reward_money": 48000, "reward_exp": 185},
        {"floor": 40, "name": "Majin Buu Hung Ác", "series": "Dragon Ball", "hp": 4000, "atk": 140, "df": 100, "spd": 48, "luk": 22, "skills": [], "reward_money": 80000, "reward_exp": 300, "reward_shards": 5},
        {"floor": 41, "name": "Aizen Hollowfied", "series": "Bleach", "hp": 1900, "atk": 110, "df": 80, "spd": 45, "luk": 21, "skills": [], "reward_money": 52000, "reward_exp": 195},
        {"floor": 42, "name": "Meruem Guard", "series": "HxH", "hp": 1950, "atk": 112, "df": 82, "spd": 46, "luk": 21, "skills": [], "reward_money": 54000, "reward_exp": 200},
        {"floor": 43, "name": "Boros", "series": "One Punch Man", "hp": 2000, "atk": 115, "df": 84, "spd": 47, "luk": 22, "skills": [], "reward_money": 56000, "reward_exp": 205},
        {"floor": 44, "name": "Dio Over Heaven", "series": "JoJo", "hp": 2050, "atk": 118, "df": 86, "spd": 48, "luk": 22, "skills": [], "reward_money": 58000, "reward_exp": 210},
        {"floor": 45, "name": "Kaido Người Cá", "series": "One Piece", "hp": 4500, "atk": 150, "df": 110, "spd": 50, "luk": 24, "skills": [], "reward_money": 100000, "reward_exp": 350, "reward_shards": 5},
        {"floor": 46, "name": "Yhwach Fragment", "series": "Bleach", "hp": 2100, "atk": 120, "df": 88, "spd": 49, "luk": 23, "skills": [], "reward_money": 65000, "reward_exp": 220},
        {"floor": 47, "name": "Goku Black", "series": "Dragon Ball", "hp": 2200, "atk": 125, "df": 90, "spd": 50, "luk": 23, "skills": [], "reward_money": 70000, "reward_exp": 230},
        {"floor": 48, "name": "Sukuna 2 Ngón", "series": "Jujutsu Kaisen", "hp": 2300, "atk": 130, "df": 92, "spd": 51, "luk": 24, "skills": [], "reward_money": 75000, "reward_exp": 240},
        {"floor": 49, "name": "Madara Thật", "series": "Naruto", "hp": 2500, "atk": 135, "df": 95, "spd": 52, "luk": 25, "skills": [], "reward_money": 80000, "reward_exp": 250},
        {"floor": 50, "name": "Im Sama", "series": "One Piece", "hp": 5500, "atk": 170, "df": 130, "spd": 60, "luk": 30, "skills": [], "reward_money": 200000, "reward_exp": 500, "reward_shards": 10},
    ],
    "raid": [
        {"name": "Sukuna Hoàn Chỉnh", "series": "Jujutsu Kaisen", "hp": 25000, "atk": 200, "df": 150, "spd": 80, "luk": 40, "skills": [], "reward_money": 500000, "reward_exp": 1000},
    ],
}





class PvePostBattleView(discord.ui.View):
    def __init__(self, cog, author_id, current_floor, unlocked_floor):
        super().__init__(timeout=60)
        self.cog = cog
        self.author_id = author_id
        self.current_floor = current_floor
        self.unlocked_floor = unlocked_floor
        self.message = None
        
        self.btn_prev.disabled = (self.current_floor <= 1)
        self.btn_next.disabled = (self.current_floor >= 50 or self.unlocked_floor <= self.current_floor)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("Lệnh này không phải của bạn!", ephemeral=True)
            return False
        return True

    async def disable_all(self, interaction):
        for child in self.children:
            child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

    @discord.ui.button(label="⏪ Tầng trước", style=discord.ButtonStyle.secondary)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.disable_all(interaction)
        ctx = await self.cog.client.get_context(interaction.message)
        ctx.author = interaction.user
        await self.cog._execute_pve_fight(ctx, self.current_floor - 1)

    @discord.ui.button(label="🔄 Đấu lại", style=discord.ButtonStyle.primary)
    async def btn_replay(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.disable_all(interaction)
        ctx = await self.cog.client.get_context(interaction.message)
        ctx.author = interaction.user
        await self.cog._execute_pve_fight(ctx, self.current_floor)

    @discord.ui.button(label="⏩ Tầng tiếp theo", style=discord.ButtonStyle.success)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        await self.disable_all(interaction)
        ctx = await self.cog.client.get_context(interaction.message)
        ctx.author = interaction.user
        await self.cog._execute_pve_fight(ctx, self.current_floor + 1)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass

class Daga(commands.Cog, name="Daga"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())

    def _level_up_cock(self, cock: Cock) -> tuple[bool, int, int]:
        exp_needed = cock.level * 100
        leveled_up = False
        start_lvl = cock.level
        
        curr_lvl = cock.level
        curr_exp = cock.exp
        curr_hp = cock.hp
        curr_atk = cock.atk
        curr_df = cock.df
        curr_spd = cock.spd
        curr_luk = cock.luk

        max_lvl = cock.max_level
        while curr_exp >= curr_lvl * 100 and curr_lvl < max_lvl:
            curr_exp -= curr_lvl * 100
            curr_lvl += 1
            leveled_up = True
            
            hp_add = random.randint(5, 10)
            atk_add = random.randint(1, 3)
            df_add = random.randint(1, 3)
            spd_add = random.randint(1, 3)
            luk_add = random.randint(1, 3)

            curr_hp += hp_add
            curr_atk += atk_add
            curr_df += df_add
            curr_spd += spd_add
            curr_luk += luk_add
            
        if leveled_up:
            self.economy.update_cock(
                cock.id,
                level=curr_lvl,
                exp=curr_exp,
                hp=curr_hp,
                atk=curr_atk,
                df=curr_df,
                spd=curr_spd,
                luk=curr_luk,
            )
            
        return leveled_up, start_lvl, curr_lvl

    async def _trigger_random_event(self, ctx: commands.Context, cock: Cock) -> None:
        # 20% chance to trigger random event
        if random.random() > 0.20:
            return

        event_roll = random.random()
        
        if event_roll < 0.35:
            # Nhặt được bí kíp EXP
            exp_gain = 50
            self.economy.update_cock(cock.id, exp=cock.exp + exp_gain)
            # Check level up
            cock_row = self.economy.get_cock(cock.id)
            if cock_row:
                lvl_up, start_lvl, end_lvl = self._level_up_cock(Cock(cock_row))
                lvl_up_msg = f"\n🎉 **NHÂN VẬT ĐÃ TĂNG TỪ CẤP {start_lvl} LÊN CẤP {end_lvl}!**" if lvl_up else ""
                await ctx.send(f"🍀 **Sự kiện ngẫu nhiên:** Nhân vật của bạn nhặt được một cuốn Bí Kíp Tu Luyện trên đường, nhận ngay **+{exp_gain} EXP**!{lvl_up_msg}")
                
        elif event_roll < 0.55:
            # Nhặt được tiền
            money_gain = random.randint(50_000, 200_000)
            self.economy.add_money(ctx.author.id, money_gain)
            await ctx.send(f"🎁 **Sự kiện ngẫu nhiên:** Trong lúc đi dạo, nhân vật của bạn nhặt được một chiếc ví rơi bên đường, nhận ngay **+{money_gain:,} VND**! 💰")
            
        elif event_roll < 0.75:
            # Nhân vật bộc phát tiềm năng
            exp_gain = 150
            self.economy.update_cock(cock.id, exp=cock.exp + exp_gain)
            
            # Check level up
            cock_row = self.economy.get_cock(cock.id)
            if cock_row:
                lvl_up, start_lvl, end_lvl = self._level_up_cock(Cock(cock_row))
                lvl_up_msg = f"\n🎉 **NHÂN VẬT ĐÃ TĂNG TỪ CẤP {start_lvl} LÊN CẤP {end_lvl}!**" if lvl_up else ""
                await ctx.send(f"⚡ **Sự kiện ngẫu nhiên:** Nhân vật bộc phát tiềm năng sức mạnh ẩn giấu, nhận ngay **+{exp_gain} EXP**!{lvl_up_msg}")
                
        else:
            # Thương nhân trả giá mua nhân vật
            rarity_multiplier = {
                "Thường": 500_000,
                "Hiếm": 2_000_000,
                "Quý": 5_000_000,
                "Sử Thi": 10_000_000,
                "Huyền Thoại": 30_000_000,
                "Thần Kê": 100_000_000
            }
            base_val = rarity_multiplier.get(cock.rarity, 500_000)
            offer_price = int(base_val * (1 + cock.level * 0.05) * random.uniform(0.7, 1.3))
            
            view = SellOfferCockView(ctx.author.id, offer_price, cock.id, self.economy)
            await ctx.send(
                f"💰 **Sự kiện ngẫu nhiên:** Có nhà sưu tầm định giá mua nhân vật **{cock.name}** của bạn với giá **{offer_price:,} VND**!\n"
                f"Bạn có đồng ý bán nhân vật này đi không?",
                view=view
            )


    async def _run_team_pve_battle(self, ctx, team_members: list, boss_data: dict, stage_type: str) -> tuple:
        c_list = team_members
        c2 = PveBoss(boss_data)
        boss_max_hp = c2.get_max_hp()

        combat_state = {}
        for c in c_list:
            p_st = {
                "hp": c.get_max_hp(), "max_hp": c.get_max_hp(),
                "base_atk": c.get_atk(), "base_df": c.get_df(),
                "base_spd": c.get_spd(), "base_luk": c.get_luk(),
                "active_used": False, "ultimate_used": False,
                "awakening_used": False, "awakened_turns": 0,
                "stunned": 0, "burn_turns": 0, "poison_turns": 0, "poison_dmg": 0,
                "shield_turns": 0, "reflect_pct": 0.0, "spd_debuff_turns": 0,
                "atk_buff_turns": 0, "atk_buff_mult": 1.0,
                "def_buff_turns": 0, "def_buff_mult": 1.0,
                "all_stats_buff_turns": 0, "dodge_buff": 0, "crit_rate_buff": 0,
                "immune_hits": 0, "absorb_heal_turns": 0,
                "copied_passive": None, "atk_reduction_pct": 0.0,
                "tu_linh_triggered": False, "rebirth_triggered": False,
                "permanent_dmg_buff": 1.0, "next_atk_buff": 1.0,
            }
            if "Krillin" in c.name: p_st["max_hp"] = int(p_st["max_hp"] * 1.08); p_st["hp"] = p_st["max_hp"]
            if "Levi" in c.name: p_st["base_spd"] = int(p_st["base_spd"] * 1.15); p_st["dodge_buff"] += 10
            if "Zoro" in c.name: p_st["base_df"] = int(p_st["base_df"] * 1.10); p_st["base_atk"] = int(p_st["base_atk"] * 1.10)
            if "Akame" in c.name: p_st["crit_rate_buff"] += 15
            if "Gojo" in c.name: p_st["dodge_buff"] += 20; p_st["crit_rate_buff"] += 15
            if "Meliodas" in c.name: p_st["base_atk"] = int(p_st["base_atk"] * 1.20)
            if "Goku" in c.name: p_st["dodge_buff"] += 35
            combat_state[c.id] = p_st

        boss_state = {
            "hp": c2.hp, "max_hp": boss_max_hp,
            "base_atk": c2.get_atk(), "base_df": c2.get_df(),
            "base_spd": c2.get_spd(), "base_luk": c2.get_luk(),
            "active_used": False, "ultimate_used": False,
            "awakening_used": False, "awakened_turns": 0,
            "stunned": 0, "burn_turns": 0, "poison_turns": 0, "poison_dmg": 0,
            "shield_turns": 0, "reflect_pct": 0.0, "spd_debuff_turns": 0,
            "atk_buff_turns": 0, "atk_buff_mult": 1.0,
            "def_buff_turns": 0, "def_buff_mult": 1.0,
            "all_stats_buff_turns": 0, "dodge_buff": 0, "crit_rate_buff": 0,
            "immune_hits": 0, "absorb_heal_turns": 0,
            "copied_passive": None, "atk_reduction_pct": 0.0,
            "tu_linh_triggered": False, "rebirth_triggered": False,
            "permanent_dmg_buff": 1.0, "next_atk_buff": 1.0,
        }
        combat_state["boss"] = boss_state

        atk_mult, def_mult, syn_series, syn_count = get_team_synergy(c_list)
        if syn_series:
            for c in c_list:
                combat_state[c.id]["base_atk"] = int(combat_state[c.id]["base_atk"] * atk_mult)
                combat_state[c.id]["base_df"] = int(combat_state[c.id]["base_df"] * def_mult)

        prep_desc = f"Đội hình ra trận đánh {c2.name}!"
        if syn_series:
            prep_desc += f"\n🔥 Đồng bộ {syn_series} ({syn_count}/3)!"

        # Determine if we should render images
        use_image = (stage_type != "tower") or (boss_data.get("floor", 0) % 5 == 0)

        if use_image:
            frame_data = render_fight_frame(
                c_list[0].name, combat_state[c_list[0].id]["max_hp"], combat_state[c_list[0].id]["max_hp"], get_cock_image_file(c_list[0].name, True),
                c2.name, boss_state["max_hp"], boss_state["max_hp"], get_cock_image_file(c2.name, True),
                "CHUẨN BỊ XUẤT TRẬN 🥊", prep_desc
            )
            file = discord.File(frame_data, filename="battle_prep.png")
            embed = make_embed(title="🏰 THÁP ĐẠI CHIẾN ANIME", description=f"⚔️ **Đội hình** vs **{c2.display_name}**", color=discord.Color.gold())
            embed.set_image(url="attachment://battle_prep.png")
            message = await ctx.send(embed=embed, file=file)
        else:
            embed = make_embed(
                title="🏰 THÁP ĐẠI CHIẾN ANIME",
                description=f"⚔️ {prep_desc}\n\n**Chuẩn bị vào trận đấu với {c2.display_name}...**",
                color=discord.Color.gold()
            )
            message = await ctx.send(embed=embed)

        battle_logs = []
        round_cnt = 1
        max_animated_rounds = 10
        active_idx = 0

        while active_idx < len(c_list) and boss_state["hp"] > 0 and round_cnt <= 30:
            ca = c_list[active_idx]
            ca_st = combat_state[ca.id]
            round_logs = [f"🥊 **HIỆP {round_cnt}** — {ca.name} vs {c2.name}"]

            if ca_st["hp"] <= 0:
                active_idx += 1
                if active_idx < len(c_list):
                    round_logs.append(f"⚔️ **{c_list[active_idx].name}** bước vào trận chiến!")
                round_cnt += 1
                battle_logs.extend(round_logs)
                continue

            # Simple attack exchange
            p_atk = ca_st["base_atk"]
            b_atk = boss_state["base_atk"]
            p_df = ca_st["base_df"]
            b_df = boss_state["base_df"]

            # Player attacks boss
            p_dmg = max(1, int((p_atk - b_df / 2) * random.uniform(0.9, 1.1)))
            is_crit = random.random() < 0.15
            if is_crit:
                p_dmg = int(p_dmg * 2.0)
                round_logs.append(f"💥 {ca.name} tung đòn chí mạng gây {p_dmg} sát thương!")
            else:
                round_logs.append(f"⚔️ {ca.name} tấn công gây {p_dmg} sát thương!")
            boss_state["hp"] -= p_dmg

            if boss_state["hp"] <= 0:
                round_logs.append(f"💀 **{c2.name}** đã bị hạ gục!")
                battle_logs.extend(round_logs)
                break

            # Boss attacks player
            b_dmg = max(1, int((b_atk - p_df / 2) * random.uniform(0.9, 1.1)))
            dodge_chance = ca_st["dodge_buff"] + ca.get_dodge_bonus()
            if random.random() * 100 < dodge_chance:
                round_logs.append(f"💨 {ca.name} né đòn nhanh như chớp!")
            else:
                ca_st["hp"] -= b_dmg
                round_logs.append(f"⚔️ {c2.name} tấn công gây {b_dmg} sát thương!")
                if ca_st["hp"] <= 0:
                    round_logs.append(f"💀 **{ca.name}** đã bị hạ gục!")
                    active_idx += 1
                    if active_idx < len(c_list):
                        round_logs.append(f"⚔️ **{c_list[active_idx].name}** bước vào trận chiến!")

            battle_logs.extend(round_logs)

            if round_cnt <= max_animated_rounds and active_idx < len(c_list) and boss_state["hp"] > 0:
                curr_c = c_list[active_idx]
                non_header = [l for l in round_logs if not l.startswith("🥊")]
                preview = "\n".join(non_header[-3:])
                if use_image:
                    frame_data = render_fight_frame(
                        curr_c.name, max(0, combat_state[curr_c.id]["hp"]), combat_state[curr_c.id]["max_hp"], get_cock_image_file(curr_c.name, True),
                        c2.name, max(0, boss_state["hp"]), boss_state["max_hp"], get_cock_image_file(c2.name, True),
                        f"HIỆP {round_cnt} 🟢", preview
                    )
                    file = discord.File(frame_data, filename=f"battle_{round_cnt}.png")
                    embed = make_embed(title="🏰 THÁP ĐẠI CHIẾN ANIME", description=f"⚔️ **Đội hình** vs **{c2.display_name}**", color=discord.Color.gold())
                    embed.set_image(url=f"attachment://battle_{round_cnt}.png")
                    try:
                        await message.edit(embed=embed, attachments=[file])
                    except Exception:
                        pass
                else:
                    desc = (
                        f"🥊 **HIỆP {round_cnt}**\n"
                        f"👤 **{curr_c.name}**: `{max(0, combat_state[curr_c.id]['hp'])}/{combat_state[curr_c.id]['max_hp']} HP`\n"
                        f"👹 **{c2.name}**: `{max(0, boss_state['hp'])}/{boss_state['max_hp']} HP`\n\n"
                        f"{preview}"
                    )
                    embed = make_embed(title="🏰 THÁP ĐẠI CHIẾN ANIME", description=desc, color=discord.Color.gold())
                    try:
                        await message.edit(embed=embed)
                    except Exception:
                        pass
                await asyncio.sleep(2.0)
            round_cnt += 1

        player_won = boss_state["hp"] <= 0

        final_round_text = "THẮNG LỢI (KO) 🏆" if player_won else "THẤT BẠI (KO) 💀"
        final_log = f"Tổ đội đã đánh bại {c2.name}!" if player_won else f"{c2.name} đã quét sạch tổ đội!"

        embed_color = discord.Color.green() if player_won else discord.Color.red()
        if use_image:
            last_idx = min(len(c_list) - 1, active_idx)
            final_frame_data = render_fight_frame(
                c_list[last_idx].name, max(0, combat_state[c_list[last_idx].id]["hp"]), combat_state[c_list[last_idx].id]["max_hp"], get_cock_image_file(c_list[last_idx].name, True),
                c2.name, max(0, boss_state["hp"]), boss_state["max_hp"], get_cock_image_file(c2.name, True),
                final_round_text, final_log
            )
            final_file = discord.File(final_frame_data, filename="battle_final.png")
            embed = make_embed(title=final_round_text, description=final_log, color=embed_color)
            embed.set_image(url="attachment://battle_final.png")
            try:
                await message.edit(embed=embed, attachments=[final_file])
            except Exception:
                await ctx.send(embed=embed, file=final_file)
        else:
            final_desc = (
                f"🏆 **KẾT QUẢ TRẬN ĐẤU**\n\n"
                f"{final_log}\n\n"
                f"Tổng số hiệp: `{round_cnt - 1}`"
            )
            embed = make_embed(title=final_round_text, description=final_desc, color=embed_color)
            try:
                await message.edit(embed=embed, attachments=[])
            except Exception:
                await ctx.send(embed=embed)

        damage_dealt = boss_data["hp"] - max(0, boss_state["hp"])
        return player_won, damage_dealt
    async def _run_team_pvp_battle(self, ctx, team_a: list, team_b: list, author: discord.Member, opponent: discord.Member, bet: int) -> tuple:
        c_list_a = team_a
        c_list_b = team_b

        combat_state = {}
        for c in c_list_a + c_list_b:
            p_st = {
                "hp": c.get_max_hp(), "max_hp": c.get_max_hp(),
                "base_atk": c.get_atk(), "base_df": c.get_df(),
                "base_spd": c.get_spd(), "base_luk": c.get_luk(),
                "active_used": False, "ultimate_used": False,
                "awakening_used": False, "awakened_turns": 0,
                "stunned": 0, "burn_turns": 0, "poison_turns": 0, "poison_dmg": 0,
                "shield_turns": 0, "reflect_pct": 0.0, "spd_debuff_turns": 0,
                "atk_buff_turns": 0, "atk_buff_mult": 1.0,
                "def_buff_turns": 0, "def_buff_mult": 1.0,
                "all_stats_buff_turns": 0, "dodge_buff": 0, "crit_rate_buff": 0,
                "immune_hits": 0, "absorb_heal_turns": 0,
                "copied_passive": None, "atk_reduction_pct": 0.0,
                "tu_linh_triggered": False, "rebirth_triggered": False,
                "permanent_dmg_buff": 1.0, "next_atk_buff": 1.0,
            }
            if "Krillin" in c.name: p_st["max_hp"] = int(p_st["max_hp"] * 1.08); p_st["hp"] = p_st["max_hp"]
            if "Levi" in c.name: p_st["base_spd"] = int(p_st["base_spd"] * 1.15); p_st["dodge_buff"] += 10
            if "Zoro" in c.name: p_st["base_df"] = int(p_st["base_df"] * 1.10); p_st["base_atk"] = int(p_st["base_atk"] * 1.10)
            if "Akame" in c.name: p_st["crit_rate_buff"] += 15
            if "Gojo" in c.name: p_st["dodge_buff"] += 20; p_st["crit_rate_buff"] += 15
            if "Meliodas" in c.name: p_st["base_atk"] = int(p_st["base_atk"] * 1.20)
            if "Goku" in c.name: p_st["dodge_buff"] += 35
            combat_state[c.id] = p_st

        atk_mult_a, def_mult_a, syn_a, syn_cnt_a = get_team_synergy(c_list_a)
        if syn_a:
            for c in c_list_a:
                combat_state[c.id]["base_atk"] = int(combat_state[c.id]["base_atk"] * atk_mult_a)
                combat_state[c.id]["base_df"] = int(combat_state[c.id]["base_df"] * def_mult_a)

        atk_mult_b, def_mult_b, syn_b, syn_cnt_b = get_team_synergy(c_list_b)
        if syn_b:
            for c in c_list_b:
                combat_state[c.id]["base_atk"] = int(combat_state[c.id]["base_atk"] * atk_mult_b)
                combat_state[c.id]["base_df"] = int(combat_state[c.id]["base_df"] * def_mult_b)

        prep_desc = f"Đại chiến Anime giữa {author.display_name} và {opponent.display_name}!"
        if syn_a: prep_desc += f"\n🔴 **{author.display_name}**: Đồng bộ {syn_a.upper()} ({syn_cnt_a}/3)"
        if syn_b: prep_desc += f"\n🔵 **{opponent.display_name}**: Đồng bộ {syn_b.upper()} ({syn_cnt_b}/3)"

        frame_data = render_fight_frame(
            c_list_a[0].name, combat_state[c_list_a[0].id]["max_hp"], combat_state[c_list_a[0].id]["max_hp"], get_cock_image_file(c_list_a[0].name, True),
            c_list_b[0].name, combat_state[c_list_b[0].id]["max_hp"], combat_state[c_list_b[0].id]["max_hp"], get_cock_image_file(c_list_b[0].name, True),
            "CHUẨN BỊ XUẤT TRẬN 🥊", prep_desc
        )
        file = discord.File(frame_data, filename="battle_prep.png")
        embed = make_embed(title="🏟️ ĐẠI CHIẾN ANIME TRỰC TIẾP", description=f"⚔️ **Đội hình {author.display_name}** vs **Đội hình {opponent.display_name}**", color=discord.Color.gold())
        embed.set_image(url="attachment://battle_prep.png")
        message = await ctx.send(embed=embed, file=file)

        battle_logs = []
        round_cnt = 1
        max_animated_rounds = 10
        active_a = 0
        active_b = 0

        while active_a < len(c_list_a) and active_b < len(c_list_b) and round_cnt <= 30:
            round_logs = []
            ca = c_list_a[active_a]
            cb = c_list_b[active_b]
            ca_st = combat_state[ca.id]
            cb_st = combat_state[cb.id]

            round_logs.append(f"🥊 **VÒNG {round_cnt}**")
            round_logs.append(f"1️⃣ **{ca.name}** (của {author.display_name}) vs 2️⃣ **{cb.name}** (của {opponent.display_name})")

            spd1 = ca_st["base_spd"]
            spd2 = cb_st["base_spd"]
            if spd1 > spd2:
                order = [(ca, cb, ca_st, cb_st), (cb, ca, cb_st, ca_st)]
            elif spd2 > spd1:
                order = [(cb, ca, cb_st, ca_st), (ca, cb, ca_st, cb_st)]
            else:
                order = [(ca, cb, ca_st, cb_st), (cb, ca, cb_st, ca_st)]

            for attacker, defender, ast, dst in order:
                if ast["hp"] <= 0 or dst["hp"] <= 0:
                    continue

                if ast["stunned"] > 0:
                    round_logs.append(f"💫 {attacker.name} bị choáng, không thể hành động!")
                    ast["stunned"] -= 1
                    continue

                # Dodge check
                dodge_chance = dst["dodge_buff"] + defender.get_dodge_bonus()
                if random.random() * 100 < dodge_chance:
                    round_logs.append(f"💨 {defender.name} né đòn nhanh như chớp!")
                    continue

                base_atk = ast["base_atk"]
                opp_df = dst["base_df"]
                damage = max(1, int((base_atk - opp_df / 2) * random.uniform(0.9, 1.1)))

                crit_chance = attacker.get_luk() * 0.5 + 5 + attacker.get_crit_chance() + ast["crit_rate_buff"]
                is_crit = random.random() * 100 < crit_chance
                if is_crit:
                    damage = int(damage * 2.0)
                    round_logs.append(f"💥 Đòn Đánh Chí Mạng từ {attacker.name}!")

                if dst["immune_hits"] > 0:
                    dst["immune_hits"] -= 1
                    round_logs.append(f"🛡️ Hào quang bảo vệ chặn đứng đòn đánh!")
                    continue

                dst["hp"] -= damage
                round_logs.append(f"⚔️ {attacker.name} tấn công gây {damage} DMG!")

            battle_logs.extend(round_logs)

            if combat_state[ca.id]["hp"] <= 0:
                round_logs.append(f"💀 **{ca.name}** đã bị hạ gục!")
                active_a += 1
                if active_a < len(c_list_a):
                    round_logs.append(f"⚔️ **{c_list_a[active_a].name}** ra trận thay thế!")

            if combat_state[cb.id]["hp"] <= 0:
                round_logs.append(f"💀 **{cb.name}** đã bị hạ gục!")
                active_b += 1
                if active_b < len(c_list_b):
                    round_logs.append(f"⚔️ **{c_list_b[active_b].name}** ra trận thay thế!")

            if round_cnt <= max_animated_rounds and active_a < len(c_list_a) and active_b < len(c_list_b):
                non_header = [l for l in round_logs if not l.startswith("🥊") and not l.startswith("1️⃣")]
                preview = "\n".join(non_header[-3:])
                frame_data = render_fight_frame(
                    c_list_a[active_a].name, combat_state[c_list_a[active_a].id]["hp"], combat_state[c_list_a[active_a].id]["max_hp"], get_cock_image_file(c_list_a[active_a].name, True),
                    c_list_b[active_b].name, combat_state[c_list_b[active_b].id]["hp"], combat_state[c_list_b[active_b].id]["max_hp"], get_cock_image_file(c_list_b[active_b].name, True),
                    f"HIỆP PVP {round_cnt} 🟢", preview
                )
                file = discord.File(frame_data, filename=f"battle_{round_cnt}.png")
                embed = make_embed(title="🏟️ ĐẠI CHIẾN ANIME TRỰC TIẾP", description=f"⚔️ **Đội hình {author.display_name}** vs **Đội hình {opponent.display_name}**", color=discord.Color.gold())
                embed.set_image(url=f"attachment://battle_{round_cnt}.png")
                try:
                    await message.edit(embed=embed, attachments=[file])
                except Exception:
                    pass
                await asyncio.sleep(2.0)

            round_cnt += 1

        won_a = None
        if active_a >= len(c_list_a) and active_b < len(c_list_b):
            won_a = False
        elif active_b >= len(c_list_b) and active_a < len(c_list_a):
            won_a = True

        winner = author if won_a is True else (opponent if won_a is False else None)
        loser = opponent if won_a is True else (author if won_a is False else None)

        if winner is None:
            final_round_text = "HÒA NHAU 🤝"
            final_log = "Trận đấu bất phân thắng bại!"
            embed_title = "🤝 TRẬN ĐẤU HÒA NHAU 🤝"
            desc = (
                f"🏟️ **SÂN ĐẤU ĐÁ GÀ TRỰC TIẾP**\n"
                f"⚔️ Đội hình của {author.display_name} vs Đội hình của {opponent.display_name}\n\n"
                f"📝 **Diễn biến hiệp cuối:**\n"
                f"... {final_log}"
            )
            embed_color = discord.Color.light_grey()
        else:
            final_round_text = "KẾT THÚC (KO) 🏆"
            final_log = f"Đội hình của {winner.display_name} giành chiến thắng!"
            embed_title = f"🏆 {winner.display_name.upper()} CHIẾN THẮNG 🏆"
            log_preview = "\n".join(battle_logs[-6:])
            desc = (
                f"🏟️ **SÂN ĐẤU ĐÁ GÀ TRỰC TIẾP**\n"
                f"⚔️ Đội hình của {author.display_name} vs Đội hình của {opponent.display_name}\n\n"
                f"📝 **Diễn biến hiệp cuối:**\n"
                f"... {log_preview}\n\n"
                f"🏆 **Người chiến thắng:** {winner.mention}\n"
                f"💰 **Số tiền nhận:** `+{bet:,} VND` (và **+150 EXP**)\n\n"
                f"💸 **Người thua cuộc:** {loser.mention}\n"
                f"📉 **Số tiền mất:** `-{bet:,} VND` (và **+20 EXP**)"
            )
            embed_color = discord.Color.green() if winner == author else discord.Color.red()

        last_show_a = min(len(c_list_a) - 1, active_a)
        last_show_b = min(len(c_list_b) - 1, active_b)

        final_frame_data = render_fight_frame(
            c_list_a[last_show_a].name, max(0, combat_state[c_list_a[last_show_a].id]["hp"]), combat_state[c_list_a[last_show_a].id]["max_hp"], get_cock_image_file(c_list_a[last_show_a].name, True),
            c_list_b[last_show_b].name, max(0, combat_state[c_list_b[last_show_b].id]["hp"]), combat_state[c_list_b[last_show_b].id]["max_hp"], get_cock_image_file(c_list_b[last_show_b].name, True),
            final_round_text, final_log
        )
        final_file = discord.File(final_frame_data, filename="battle_final.png")
        embed = make_embed(title=embed_title, description=desc, color=embed_color)
        embed.set_image(url="attachment://battle_final.png")
        try:
            await message.edit(embed=embed, attachments=[final_file])
        except Exception:
            await ctx.send(embed=embed, file=final_file)

        return won_a, battle_logs

    @commands.group(
        name="anime",
        brief="Hệ thống nuôi, đấu và chiêu mộ nhân vật Anime.",
        usage="anime [subcommand]",
        aliases=["daga", "dg", "am"],
        invoke_without_command=True,
    )
    async def daga_group(self, ctx: commands.Context):
        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]
            
        desc = (
            "⚔️ **HỆ THỐNG ĐẠI CHIẾN ANIME - HƯỚNG DẪN LỆNH** ⚔️\n\n"
            f"🛒 **Cửa hàng & Gacha:**\n"
            f"🔹 `{prefix}anime shop` — Xem cửa hàng bán gacha banner và vật phẩm nâng cấp.\n"
            f"🔹 `{prefix}anime buy banner <ID>` — Triệu hồi nhân vật gacha từ banner.\n"
            f"🔹 `{prefix}anime buy food <ID> <số_lượng>` — Mua vật phẩm nâng cấp EXP nhân vật.\n"
            f"🔹 `{prefix}anime rate` — Xem tỷ lệ triệu hồi và danh sách nhân vật.\n\n"
            f"👤 **Quản lý nhân vật:**\n"
            f"🔹 `{prefix}anime list` — Xem danh sách các nhân vật đang sở hữu.\n"
            f"🔹 `{prefix}anime active <ID_nhân_vật>` — Đặt nhân vật làm chính xuất trận.\n"
            f"🔹 `{prefix}anime info [ID_nhân_vật]` — Xem chi tiết chỉ số của nhân vật.\n"
            f"🔹 `{prefix}anime skill [tên_nhân_vật]` — Xem thông tin chi tiết kỹ năng của nhân vật.\n"
            f"🔹 `{prefix}anime team` — Quản lý đội hình 3 nhân vật tham gia thi đấu.\n"
            f"🔹 `{prefix}anime inv` (hoặc `inventory`) — Xem kho đồ cá nhân (vật phẩm, đá nâng cấp, mảnh nhân vật).\n\n"
            f"💪 **Nuôi dưỡng & Huấn luyện:**\n"
            f"🔹 `{prefix}anime feed [ID_vật_phẩm] [số_lượng]` — Sử dụng vật phẩm/đá nâng cấp cho nhân vật (ID 1-15).\n"
            f"🔹 `{prefix}anime train` — Huấn luyện nhân vật chính tăng chỉ số ngẫu nhiên (Hồi chiêu 1 giờ).\n"
            f"🔹 `{prefix}anime dotpha` — Đột phá nâng sao tăng giới hạn cấp và sức mạnh cho nhân vật.\n"
            f"🔹 `{prefix}anime craft [tên_nhân_vật]` — Ghép mảnh nhân vật nhận nhân vật S/SS tự chọn.\n\n"
            f"⚔️ **Thi đấu & Bảng xếp hạng:**\n"
            f"🔹 `{prefix}anime fight @người_chơi [tiền_cược]` — Thách đấu PvP đội hình 3v3 KOF-style đặt cược.\n"
            f"🔹 `{prefix}anime pve` — Leo Tháp Đại Chiến 50 tầng thử thách nhận quà khủng.\n"
            f"🔹 `{prefix}anime top` — Xem bảng xếp hạng Bậc Thầy có nhiều trận thắng nhất.\n"
        )
        
        embed = make_embed(
            title="🎮 HỆ THỐNG ĐẠI CHIẾN ANIME - CASINO BOT 🎮",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @daga_group.command(name="rate", brief="Xem tỷ lệ độ hiếm của thẻ triệu hồi, hòm và danh sách nhân vật, trang bị.")
    async def daga_rate(self, ctx: commands.Context):
        view = DagaRateView(ctx.author)
        embeds = view.get_embeds()
        msg = await ctx.send(embed=embeds[0], view=view)
        view.message = msg

    @daga_group.command(name="inventory", brief="Xem kho đồ cá nhân (vật phẩm, đá nâng cấp, mảnh nhân vật).", aliases=["inv"])
    async def daga_inventory(self, ctx: commands.Context):
        inventory = self.economy.get_inventory(ctx.author.id)
        
        # Filter items
        shard_list = []
        stone_list = []
        food_list = []
        gear_list = []
        
        for item_id, qty in inventory:
            if qty <= 0:
                continue
            if item_id == "item_character_shard":
                name = INVENTORY_FOOD_NAMES.get(item_id, "Mảnh nhân vật")
                shard_list.append((name, qty))
            elif item_id.startswith("item_stone_"):
                name = INVENTORY_FOOD_NAMES.get(item_id, item_id)
                stone_list.append((name, qty))
            elif item_id.startswith("food_"):
                name = INVENTORY_FOOD_NAMES.get(item_id, item_id)
                food_list.append((name, qty))
            elif item_id in INVENTORY_GEAR_NAMES:
                name = INVENTORY_GEAR_NAMES.get(item_id, item_id)
                gear_list.append((name, qty))
                
        embed = make_embed(
            title=f"🎒 KHO ĐỒ ANIME - {ctx.author.name.upper()}",
            color=discord.Color.purple()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        
        has_items = False
        
        if shard_list:
            has_items = True
            desc = ""
            for name, qty in shard_list:
                desc += f"• {name}: **{qty}** mảnh\n"
            embed.add_field(name="🔮 Mảnh Nhân Vật", value=desc, inline=False)
            
        if stone_list:
            has_items = True
            desc = ""
            for name, qty in stone_list:
                desc += f"• {name}: **{qty}** viên\n"
            embed.add_field(name="💎 Đá Nâng Cấp & Đột Phá", value=desc, inline=False)
            
        if food_list:
            has_items = True
            desc = ""
            for name, qty in food_list:
                desc += f"• {name}: **{qty}** cái\n"
            embed.add_field(name="📕 Vật Phẩm Kinh Nghiệm", value=desc, inline=False)
            
        if gear_list:
            has_items = True
            desc = ""
            for name, qty in gear_list:
                desc += f"• {name}: **{qty}** chiếc\n"
            embed.add_field(name="⚔️ Trang Bị", value=desc, inline=False)
            
        if not has_items:
            embed.description = "Kho đồ Anime của bạn hiện đang trống rỗng. Hãy mua vật phẩm nâng cấp bằng lệnh `i?anime shop` hoặc tham gia PVE/PVP để nhận quà nhé!"
            
        embed.set_footer(text=f"Sử dụng vật phẩm bằng lệnh: i?anime feed <ID_vật_phẩm> <số_lượng>")
        await ctx.send(embed=embed)

    @daga_group.command(name="shop", brief="Xem các thẻ triệu hồi, gacha banner và vật phẩm nâng cấp cho nhân vật.")
    async def daga_shop(self, ctx: commands.Context):
        prefix = self.client.command_prefix
        if isinstance(prefix, list):
            prefix = prefix[0]
            
        desc = (
            "🔮 **CỬA HÀNG TRIỆU HỒI ANIME (GACHA BANNER)**\n"
            f"🛒 Triệu hồi bằng lệnh: `{prefix}anime buy banner <ID>`\n"
            "🔹 **[1] Banner Thường:** `1.000.000 VND` (60% C | 30% B | 9% A | 0.8% S | 0.2% SS)\n"
            "🔹 **[2] Banner Xịn:** `5.000.000 VND` (40% B | 45% A | 12% S | 3% SS | Bảo hiểm 50 lượt cho SS)\n\n"
            "🧪 **CỬA HÀNG VẬT PHẨM NÂNG CẤP (EXP SHOP)**\n"
            f"🛒 Mua vật phẩm nâng cấp bằng lệnh: `{prefix}anime buy food <ID> <số_lượng>`\n"
            "📕 **[1] Sách EXP Sơ Cấp:** `20.000 VND` (+10 EXP)\n"
            "📘 **[2] Sách EXP Trung Cấp:** `54.000 VND` (+30 EXP)\n"
            "📙 **[3] Sách EXP Cao Cấp:** `128.000 VND` (+80 EXP)\n"
            "📓 **[4] Sách EXP Cực Phẩm:** `280.000 VND` (+200 EXP)\n"
            "🟢 **[5] Tụ Khí Đan:** `600.000 VND` (+500 EXP)\n"
            "💎 **[6] Linh Hồn Thạch:** `1.000.000 VND` (+1.000 EXP)\n"
            "🧪 **[7] Thần Thú Huyết:** `2.250.000 VND` (+2.500 EXP)\n"
            "💊 **[8] Tẩy Tủy Đan:** `4.000.000 VND` (+5.000 EXP)\n"
            "🍄 **[9] Linh Chi Vạn Năm:** `7.000.000 VND` (+10.000 EXP)\n"
            "🍯 **[10] Hỗn Độn Linh Dịch:** `30.000.000 VND` (+50.000 EXP)\n"
            "⚔️ **[11] Đá nâng ATK:** `5.000.000 VND` (+5 ATK vĩnh viễn)\n"
            "🛡️ **[12] Đá nâng DEF:** `4.000.000 VND` (+5 DEF vĩnh viễn)\n"
            "⚡ **[13] Đá nâng SPD:** `4.000.000 VND` (+3 SPD vĩnh viễn)\n"
            "💎 **[14] Đá đột phá giới hạn cấp:** `50.000.000 VND` (+1 Sao Đột Phá)\n"
            "🔮 **[15] Mảnh nhân vật:** `15.000.000 VND` (Ghép S/SS tự chọn: `i?anime craft`)\n"
        )
        embed = make_embed(
            title="⚔️ CỬA HÀNG ĐẠI CHIẾN ANIME ⚔️",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @daga_group.group(name="buy", brief="Mua lượt triệu hồi banner gacha hoặc vật phẩm nâng cấp EXP.")
    async def daga_buy(self, ctx: commands.Context):
        if ctx.invoked_subcommand is None:
            await ctx.send("Vui lòng chọn triệu hồi banner hoặc mua vật phẩm nâng cấp EXP. Ví dụ:\n"
                           "`i?anime buy banner 1` (Triệu hồi banner thường)\n"
                           "`i?anime buy food 1 10` (Mua vật phẩm nâng cấp EXP)")

    @daga_buy.command(name="banner", brief="Triệu hồi nhân vật gacha từ banner.", aliases=["summon", "egg"])
    async def buy_banner(self, ctx: commands.Context, banner_type: str):
        banner_type = banner_type.lower().strip()
        banner_id_mapping = {
            "1": "thuong",
            "2": "xin"
        }
        if banner_type in banner_id_mapping:
            banner_type = banner_id_mapping[banner_type]

        prices = {"thuong": 1_000_000, "xin": 5_000_000}
        
        if banner_type not in prices:
            await ctx.send("❌ **Lỗi:** Loại banner không hợp lệ! Hãy chọn ID: `1` (Thường) hoặc `2` (Xịn).")
            return

        price = prices[banner_type]
        # Validate balance
        try:
            validate_money_bet(self.economy, ctx.author.id, price)
        except Exception as exc:
            await ctx.send(str(exc))
            return

        pity = self.economy.get_pity_golden(ctx.author.id)

        # Roll secret SSS first
        r_secret = random.random() * 100
        is_secret_sss = False
        if banner_type == "thuong" and r_secret < 0.02:
            is_secret_sss = True
        elif banner_type == "xin" and r_secret < 0.1:
            is_secret_sss = True

        rarity = "Thường"
        is_reset_pity = False

        if is_secret_sss:
            rarity = "Thần Kê"
            if banner_type == "xin":
                self.economy.set_pity_golden(ctx.author.id, pity + 1)
        else:
            # Roll rarity normally
            r = random.random() * 100
            if banner_type == "thuong":
                if r < 60.0:
                    rarity = "Thường"
                elif r < 90.0:
                    rarity = "Hiếm"
                elif r < 99.0:
                    rarity = "Quý"
                elif r < 99.8:
                    rarity = "Sử Thi"
                else:
                    rarity = "Huyền Thoại"
            elif banner_type == "xin":
                # pity logic (only applies to Huyền Thoại)
                if pity >= 49: # 50th roll guarantee
                    rarity = "Huyền Thoại"
                    is_reset_pity = True
                else:
                    if r < 40.0:
                        rarity = "Hiếm"
                    elif r < 85.0:
                        rarity = "Quý"
                    elif r < 97.0:
                        rarity = "Sử Thi"
                    else:
                        rarity = "Huyền Thoại"
                        is_reset_pity = True

                if is_reset_pity:
                    self.economy.set_pity_golden(ctx.author.id, 0)
                else:
                    self.economy.set_pity_golden(ctx.author.id, pity + 1)

        # Generate stats and breed
        breed = random.choice(BREEDS[rarity])
        ranges = STAT_RANGES[rarity]
        hp = random.randint(*ranges["hp"])
        atk = random.randint(*ranges["atk"])
        df = random.randint(*ranges["df"])
        spd = random.randint(*ranges["spd"])
        luk = random.randint(*ranges["luk"])

        # Deduct money
        self.economy.add_money(ctx.author.id, -price)
        
        # Add cock to DB
        cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = self.economy.add_cock(
            ctx.author.id, breed, rarity, hp, atk, df, spd, luk
        )

        log_wallet_change(
            logger,
            event="buy_banner_gacha",
            user_id=ctx.author.id,
            money_delta=-price,
            egg_type=banner_type,
            cock_id=cock_id,
            rarity=rarity,
        )

        pity_str = ""
        if banner_type == "xin":
            new_pity = 0 if is_reset_pity else pity + 1
            pity_str = f"\n🛡️ **Số lần tích bảo hiểm (Pity SS):** `{new_pity}/50`"

        rarity_emojis = {
            "Thường": "<:698204c:1515422780370190377>",
            "Hiếm": "<:759990b:1515423304620703905>",
            "Quý": "<:780661a:1515423318587609224>",
            "Sử Thi": "<:429893s:1515423348014715091>",
            "Huyền Thoại": "<:915638ss:1515423361310785536>",
            "Thần Kê": "<:886814sss:1515423524167225415>",
            "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
        }

        display_banner_name = "Banner Thường" if banner_type == "thuong" else "Banner Xịn"
        display_rarity = RARITY_DISPLAY.get(rarity, rarity)
        if is_duplicate:
            needed = new_stars + 1
            if new_shards >= needed:
                tip_msg = f"*(🎉 Đã tích đủ mảnh trùng! Hãy gõ `{ctx.prefix}anime dotpha` để tiến hành đột phá!)*"
            else:
                tip_msg = f"*(Nhận thêm `{needed - new_shards}` bản trùng nữa để lên {new_stars + 1} Sao)*"
            desc = (
                f"Bạn đã triệu hồi từ **{display_banner_name}** với giá **{price:,} VND**...\n"
                f"🔄 **BẠN NHẬN TRÙNG NHÂN VẬT!** (Tích luỹ mảnh)\n\n"
                f"⚔️ **Nhân vật:** `{breed}`\n"
                f"⭐ **Độ hiếm:** {rarity_emojis[rarity]} `{display_rarity}`\n"
                f"📊 **Tiến trình đột phá:** `[ {new_shards} / {needed} ]` mảnh trùng\n"
                f"{tip_msg}"
                f"{pity_str}"
            )
        else:
            desc = (
                f"Bạn đã triệu hồi từ **{display_banner_name}** với giá **{price:,} VND**...\n"
                f"✨ **Triệu hồi thành công!**\n\n"
                f"⚔️ **Nhân vật:** `{breed}`\n"
                f"⭐ **Độ hiếm:** {rarity_emojis[rarity]} `{display_rarity}`\n"
                f"❤️ **Máu (HP):** `{final_stats['hp']}`\n"
                f"⚔️ **Sát thương (ATK):** `{final_stats['atk']}`\n"
                f"🛡️ **Phòng thủ (DEF):** `{final_stats['df']}`\n"
                f"⚡ **Tốc độ (SPD):** `{final_stats['spd']}`\n"
                f"🍀 **May mắn (LUK):** `{final_stats['luk']}`"
                f"{pity_str}"
            )

        anim_embed = make_embed(
            title="🔮 ĐANG TRIỆU HỒI ANIME... 🔮",
            description=f"⏳ **{ctx.author.display_name}** đang triệu hồi từ **{display_banner_name}**...\nHãy chờ xem bạn nhận được nhân vật nào nhé! 🍀",
            color=discord.Color.gold()
        )
        gif_path = ABS_PATH / "modules" / "daga" / "mo_trung.gif"
        file_gif = discord.File(gif_path, filename="mo_trung.gif")
        anim_embed.set_image(url="attachment://mo_trung.gif")

        msg = await ctx.send(embed=anim_embed, file=file_gif)

        await asyncio.sleep(3)

        embed = make_embed(
            title="🔮 TRIỆU HỒI THÀNH CÔNG 🔮",
            description=desc,
            color=discord.Color.green(),
        )
        img_name = get_cock_image_file(breed)
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_thumbnail(url=f"attachment://{img_name}")
            await msg.edit(embed=embed, attachments=[file])
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await msg.edit(embed=embed, attachments=[])

    @daga_buy.command(name="food", brief="Mua vật phẩm nâng cấp EXP cho nhân vật.", aliases=["exp", "item"])
    async def buy_food(self, ctx: commands.Context, food_id: str, quantity: int = 1):
        food_id = str(food_id).strip()
        if quantity <= 0:
            await ctx.send("❌ **Lỗi:** Số lượng mua phải lớn hơn 0.")
            return
            
        if food_id not in FOOD_DETAILS:
            await ctx.send("❌ **Lỗi:** ID vật phẩm không hợp lệ! Vui lòng chọn từ `1` đến `15` trong shop.")
            return
            
        food = FOOD_DETAILS[food_id]
        total_price = food["price"] * quantity
        
        try:
            validate_money_bet(self.economy, ctx.author.id, total_price)
        except Exception as exc:
            await ctx.send(str(exc))
            return
            
        # Deduct money
        self.economy.add_money(ctx.author.id, -total_price)
        
        # Add to inventory
        self.economy.add_inventory_item(ctx.author.id, food["item_id"], quantity)
        
        log_wallet_change(
            logger,
            event="buy_food_daga",
            user_id=ctx.author.id,
            money_delta=-total_price,
            food_id=food_id,
            quantity=quantity
        )
        
        await ctx.send(f"✅ Đã mua thành công `{quantity}` **{food['name']}** với tổng giá **{total_price:,} VND**! Vật phẩm đã được cất vào kho đồ.")

    @daga_group.command(name="list", brief="Xem danh sách nhân vật anime của bạn.")
    async def daga_list(self, ctx: commands.Context):
        cocks_rows = self.economy.get_cocks(ctx.author.id)
        if not cocks_rows:
            await ctx.send("🔮 Bạn chưa sở hữu nhân vật anime nào cả. Hãy vào shop chiêu mộ nhân vật nhé!")
            return

        view = CockListView(ctx.author, cocks_rows)
        embed = view.get_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @daga_group.command(name="active", brief="Chọn nhân vật chính để huấn luyện/thi đấu.")
    async def daga_active(self, ctx: commands.Context, cock_id: int):
        cock_row = self.economy.get_cock(cock_id)
        if not cock_row:
            await ctx.send(f"❌ Không tìm thấy nhân vật với ID `{cock_id}`.")
            return

        if cock_row[1] != ctx.author.id:
            await ctx.send("❌ Nhân vật này không thuộc sở hữu của bạn!")
            return

        self.economy.set_active_cock(ctx.author.id, cock_id)
        await ctx.send(f"✅ Đã chọn **{cock_row[2]}** (ID: {cock_id}) làm nhân vật chính xuất trận!")

    @daga_group.group(
        name="team",
        brief="Quản lý đội hình 3 nhân vật tham gia thi đấu.",
        usage="team [subcommand]",
        invoke_without_command=True,
    )
    async def anime_team(self, ctx: commands.Context):
        team_rows = self.economy.get_team_cocks(ctx.author.id)
        embed = discord.Embed(title=f"⚔️ ĐỘI HÌNH CỦA {ctx.author.display_name}", color=discord.Color.gold())
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        team_cocks = {pos: Cock(row) if row else None for pos, row in team_rows.items()}
        pos_labels = {1: "1️⃣", 2: "2️⃣", 3: "3️⃣"}
        rarity_colors = {"Thường": "⚪", "Hiếm": "🟢", "Quý": "🔵", "Sử Thi": "🟣", "Huyền Thoại": "🟡", "Thần Kê": "🔴", "Exclusive": "👑"}
        desc_lines = ["━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"]
        total_power = 0
        cocks_list = []
        for pos in (1, 2, 3):
            c = team_cocks[pos]
            if c:
                cocks_list.append(c)
                power = c.get_max_hp() + c.get_atk() + c.get_df() + c.get_spd() + c.get_luk()
                total_power += power
                rarity_emoji = rarity_colors.get(c.rarity, "⚪")
                desc_lines.append(f"{pos_labels[pos]} {rarity_emoji} **{c.display_name}** — Lv.{c.level}")
                desc_lines.append(f"   ❤️ {c.get_max_hp()} | ⚔️ {c.get_atk()} | 🛡️ {c.get_df()} | ⚡ {c.get_spd()}")
            else:
                desc_lines.append(f"{pos_labels[pos]} 🔲 _Trống_ — Chưa xếp nhân vật")
        desc_lines.append("━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━")
        atk_mult, def_mult, syn_series, syn_count = get_team_synergy(cocks_list)
        if syn_series:
            desc_lines.append(f"🔥 **Đồng bộ:** {syn_series} ({syn_count}/3)")
            if atk_mult > 1.0: desc_lines.append(f"   ⚔️ +{int((atk_mult-1)*100)}% ATK")
            if def_mult > 1.0: desc_lines.append(f"   🛡️ +{int((def_mult-1)*100)}% DEF")
        desc_lines.append(f"\n💪 **Tổng Chiến Lực:** `{total_power:,}`")
        prefix = ctx.prefix or "i?"
        desc_lines.append(f"*{prefix}anime team set <vị_trí> <ID> để thay đổi*")
        embed.description = "\n".join(desc_lines)
        await ctx.send(embed=embed)

    @anime_team.command(name="set", brief="Đặt nhân vật vào vị trí 1/2/3 trong đội hình.")
    async def anime_team_set(self, ctx: commands.Context, position: int, cock_id: int):
        if position not in (1, 2, 3):
            await ctx.send("❌ Vị trí phải là 1, 2 hoặc 3!")
            return
        cock_row = self.economy.get_cock(cock_id)
        if not cock_row:
            await ctx.send(f"❌ Không tìm thấy nhân vật với ID `{cock_id}`.")
            return
        if cock_row[1] != ctx.author.id:
            await ctx.send("❌ Nhân vật này không thuộc sở hữu của bạn!")
            return
        old_team = self.economy.get_team_cocks(ctx.author.id)
        target_occupant_row = old_team[position]
        cock_old_pos = None
        for p, r in old_team.items():
            if r and r[0] == cock_id:
                cock_old_pos = p
                break
        self.economy.set_team_position(ctx.author.id, cock_id, position)
        cock_name = cock_row[2]
        if cock_old_pos is not None and target_occupant_row:
            occ_name = target_occupant_row[2]
            await ctx.send(f"🔄 Hoán đổi vị trí! **{cock_name}**: Vị trí {cock_old_pos} → Vị trí {position}; **{occ_name}**: Vị trí {position} → Vị trí {cock_old_pos}")
        elif target_occupant_row:
            occ_name = target_occupant_row[2]
            await ctx.send(f"✅ Đã đặt **{cock_name}** vào Vị trí {position}! ⚠️ Lưu ý: **{occ_name}** đã bị đẩy ra khỏi đội.")
        else:
            await ctx.send(f"✅ Đã đặt **{cock_name}** vào Vị trí {position}!")

    @anime_team.command(name="remove", brief="Rút nhân vật khỏi vị trí đã chọn trong đội hình.", aliases=["rm"])
    async def anime_team_remove(self, ctx: commands.Context, position: int):
        if position not in (1, 2, 3):
            await ctx.send("❌ Vị trí phải là 1, 2 hoặc 3!")
            return
        team_rows = self.economy.get_team_cocks(ctx.author.id)
        target_row = team_rows[position]
        if not target_row:
            await ctx.send(f"❌ Vị trí {position} hiện đang trống, không có gì để rút!")
            return
        cock_name = target_row[2]
        self.economy.remove_from_team(ctx.author.id, position)
        remaining_rows = self.economy.get_team_cocks(ctx.author.id)
        remaining_count = sum(1 for r in remaining_rows.values() if r)
        await ctx.send(f"❌ Đã rút **{cock_name}** khỏi Vị trí {position}. Vị trí {position} hiện đang trống — đội chỉ còn {remaining_count} người! ⚠️ Đội thiếu người sẽ yếu hơn khi đánh Tower/PvP.")

    @anime_team.command(name="auto", brief="Tự động xếp đội hình gồm 3 nhân vật mạnh nhất.")
    async def anime_team_auto(self, ctx: commands.Context):
        all_cocks = self.economy.get_cocks(ctx.author.id)
        if not all_cocks or len(all_cocks) < 1:
            await ctx.send("❌ Bạn chưa có nhân vật nào!")
            return
        sorted_cocks = sorted(all_cocks, key=lambda r: Cock(r).get_max_hp() + Cock(r).get_atk() + Cock(r).get_df() + Cock(r).get_spd() + Cock(r).get_luk(), reverse=True)
        proposed = sorted_cocks[:3]
        proposed_ids = [r[0] for r in proposed]

        desc = "📋 **Đề xuất đội hình mới:**\n"
        for i, row in enumerate(proposed):
            c = Cock(row)
            power = c.get_max_hp() + c.get_atk() + c.get_df() + c.get_spd() + c.get_luk()
            desc += f"  {i+1}️⃣ **{c.display_name}** (ID: {c.id}) — Chiến lực: `{power:,}`\n"
        desc += "\n✅ Bấm nút bên dưới để áp dụng!"

        class AutoTeamView(discord.ui.View):
            def __init__(self, author, economy, ids):
                super().__init__(timeout=60)
                self.author = author
                self.economy = economy
                self.ids = ids

            @discord.ui.button(label="✅ Áp dụng", style=discord.ButtonStyle.green)
            async def accept(self, interaction: discord.Interaction, _):
                if interaction.user.id != self.author.id:
                    await interaction.response.send_message("❌ Bạn không phải chủ đội hình này!", ephemeral=True)
                    return
                self.economy.clear_team(self.author.id)
                for i, cid in enumerate(self.ids):
                    self.economy.set_team_position(self.author.id, cid, i + 1)
                await interaction.response.send_message("✅ Đã áp dụng đội hình mới thành công!")
                self.stop()

            @discord.ui.button(label="❌ Giữ đội cũ", style=discord.ButtonStyle.red)
            async def decline(self, interaction: discord.Interaction, _):
                if interaction.user.id != self.author.id:
                    await interaction.response.send_message("❌ Bạn không phải chủ đội hình này!", ephemeral=True)
                    return
                await interaction.response.send_message("❌ Đã hủy. Giữ nguyên đội hình cũ.")
                self.stop()

        view = AutoTeamView(ctx.author, self.economy, proposed_ids)
        embed = make_embed(title="🤖 TỰ ĐỘNG XẾP ĐỘI", description=desc, color=discord.Color.blue())
        await ctx.send(embed=embed, view=view)

    @anime_team.command(name="power", brief="Xem tổng chiến lực đội hình.")
    async def anime_team_power(self, ctx: commands.Context):
        team_rows = self.economy.get_team_cocks(ctx.author.id)
        team_cocks = [Cock(r) for r in team_rows.values() if r]
        if not team_cocks:
            await ctx.send("❌ Đội hình trống!")
            return
        total_power = sum(c.get_max_hp() + c.get_atk() + c.get_df() + c.get_spd() + c.get_luk() for c in team_cocks)
        await ctx.send(f"💪 **Tổng Chiến Lực đội hình:** `{total_power:,}`")

    @daga_group.command(name="skill", brief="Xem thông tin chi tiết kỹ năng của các nhân vật.", aliases=["skills", "kynang"])
    async def anime_skill(self, ctx: commands.Context, *, character_name: str | None = None):
        if not character_name:
            prefix = ctx.prefix or "i?"
            char_list = ", ".join(f"`{k}`" for k in CHARACTER_INFO_MAP.keys())
            embed = make_embed(
                title="📜 DANH SÁCH CHIẾN BINH ANIME 📜",
                description=(
                    f"Để xem chi tiết kỹ năng của một nhân vật, hãy dùng lệnh:\n"
                    f"`{prefix}anime skill <tên_nhân_vật>`\n\n"
                    f"**Các nhân vật hiện có:**\n{char_list}"
                ),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        character_name = character_name.strip()
        found_key = None
        for k in CHARACTER_INFO_MAP.keys():
            if character_name.lower() in k.lower() or k.lower() in character_name.lower():
                found_key = k
                break

        if not found_key:
            await ctx.send(f"❌ Không tìm thấy nhân vật nào có tên tương tự như `{character_name}`.")
            return

        info = CHARACTER_INFO_MAP[found_key]
        upgraded_skill = UPGRADED_SKILL_MAP.get(found_key, "Chưa rõ")

        # Compile battle bonus descriptions based on code mechanics
        combat_bonus = "Chỉ số cơ bản."
        if "Krillin" in found_key:
            combat_bonus = "➕ Tăng **8% HP tối đa** khi vào trận."
        elif "Levi" in found_key:
            combat_bonus = "➕ Tăng **15% Tốc độ (SPD)** và **10% Tỷ lệ né tránh (Dodge)**."
        elif "Zoro" in found_key:
            combat_bonus = "➕ Tăng **10% Sát thương (ATK)** và **10% Phòng thủ (DEF)**."
        elif "Akame" in found_key:
            combat_bonus = "➕ Tăng **15% Tỷ lệ chí mạng (Crit Chance)**."
        elif "Gojo" in found_key:
            combat_bonus = "➕ Tăng **20% Tỷ lệ né tránh (Dodge)** và **15% Tỷ lệ chí mạng (Crit Chance)**."
        elif "Meliodas" in found_key:
            combat_bonus = "➕ Tăng **20% Sát thương (ATK)**."
        elif "Goku" in found_key:
            combat_bonus = "➕ Tăng **35% Tỷ lệ né tránh (Dodge)**."

        desc = (
            f"📺 **Series:** `{info['series']}`\n\n"
            f"🔥 **Kỹ năng chủ động (Active):** `{info['active']}`\n"
            f"⭐ *Chiêu thức đặc trưng kích hoạt khi tấn công đối thủ.*\n\n"
            f"✨ **Kỹ năng bị động (Passive):** `{info['passive']}`\n"
            f"🛡️ *Bổ trợ tự động giúp tăng cường sức mạnh chiến đấu.*\n\n"
            f"🌟 **Kỹ năng tối thượng (Đột Phá):** `{upgraded_skill}`\n"
            f"👑 *Mở khóa khi nâng cấp sao cho nhân vật.*\n\n"
            f"⚔️ **Hiệu ứng thực chiến:**\n{combat_bonus}"
        )

        embed = make_embed(
            title=f"⚔️ KỸ NĂNG NHÂN VẬT: {found_key} ⚔️",
            description=desc,
            color=discord.Color.gold()
        )
        
        img_name = get_cock_image_file(found_key)
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_thumbnail(url=f"attachment://{img_name}")
            await ctx.send(embed=embed, file=file)
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)


    @daga_group.command(name="feed", brief="Sử dụng vật phẩm nâng cấp từ kho đồ để tăng EXP cho nhân vật.", aliases=["upgrade_exp", "use"])
    async def daga_feed(self, ctx: commands.Context, food_id: str | None = None, quantity: int = 1):
        active_row = self.economy.get_active_cock(ctx.author.id)
        if not active_row:
            await ctx.send("❌ **Lỗi:** Bạn chưa chọn nhân vật xuất trận nào.")
            return
            
        cock = Cock(active_row)
        max_lvl = cock.max_level
        if cock.level >= max_lvl:
            await ctx.send(f"❌ **Lỗi:** Nhân vật đã đạt giới hạn cấp độ của Bậc Đột Phá này (`{max_lvl}`)! Hãy sử dụng lệnh `i?anime dotpha` để nâng giới hạn cấp độ.")
            return
            
        if food_id is None:
            # List food available in player's inventory
            inventory = self.economy.get_inventory(ctx.author.id)
            available_foods = []
            for fid, details in FOOD_DETAILS.items():
                item_qty = 0
                for inv_item, qty in inventory:
                    if inv_item == details["item_id"]:
                        item_qty = qty
                        break
                if item_qty > 0:
                    available_foods.append(f"🔹 **[{fid}] {details['name']}** — Số lượng: `{item_qty}` cái (Mỗi cái +{details['exp']} EXP)")
            
            food_list_str = "\n".join(available_foods) if available_foods else "Hiện tại bạn không có vật phẩm nâng cấp nào trong kho đồ. Hãy dùng `i?anime shop` để mua!"
            desc = (
                "🧪 **KHO VẬT PHẨM NÂNG CẤP CỦA BẠN** 🧪\n\n"
                f"{food_list_str}\n\n"
                f"👉 Dùng lệnh: `{ctx.prefix}anime feed <ID_vật_phẩm> [số_lượng]` để nâng cấp EXP nhân vật."
            )
            embed = make_embed(
                title="✨ NÂNG CẤP NHÂN VẬT ANIME ✨",
                description=desc,
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        food_id = str(food_id).strip()
        if food_id not in FOOD_DETAILS:
            await ctx.send("❌ **Lỗi:** ID vật phẩm không hợp lệ! Vui lòng chọn từ `1` đến `15`.")
            return
            
        if quantity <= 0:
            await ctx.send("❌ **Lỗi:** Số lượng sử dụng phải lớn hơn 0.")
            return

        if food_id == "15":
            await ctx.send(f"❌ **Lỗi:** Mảnh nhân vật không thể sử dụng trực tiếp để bồi dưỡng. Hãy tích lũy đủ 10 mảnh và dùng lệnh `{ctx.prefix}anime craft <tên_nhân_vật>` để ghép nhân vật SSR tự chọn!")
            return
            
        food = FOOD_DETAILS[food_id]
        
        # Check stock quantity
        inventory = self.economy.get_inventory(ctx.author.id)
        stock_qty = 0
        for inv_item, qty in inventory:
            if inv_item == food["item_id"]:
                stock_qty = qty
                break
                
        if stock_qty < quantity:
            await ctx.send(f"❌ **Lỗi:** Bạn chỉ có `{stock_qty}` cái **{food['name']}** trong kho đồ, không đủ để sử dụng `{quantity}` cái!")
            return
            
        # Deduct from inventory
        self.economy.add_inventory_item(ctx.author.id, food["item_id"], -quantity)
        
        # Handle specific stone item effects
        if food_id == "11":
            # ATK Stone: +5 ATK per stone
            atk_gain = 5 * quantity
            self.economy.update_cock(cock.id, atk=cock.atk + atk_gain)
            await ctx.send(f"⚔️ Bạn sử dụng `{quantity}` **{food['name']}** cho **{cock.name}**, tăng vĩnh viễn **+{atk_gain} ATK**!")
            return
            
        elif food_id == "12":
            # DEF Stone: +5 DEF per stone
            df_gain = 5 * quantity
            self.economy.update_cock(cock.id, df=cock.df + df_gain)
            await ctx.send(f"🛡️ Bạn sử dụng `{quantity}` **{food['name']}** cho **{cock.name}**, tăng vĩnh viễn **+{df_gain} DEF**!")
            return
            
        elif food_id == "13":
            # SPD Stone: +3 SPD per stone
            spd_gain = 3 * quantity
            self.economy.update_cock(cock.id, spd=cock.spd + spd_gain)
            await ctx.send(f"⚡ Bạn sử dụng `{quantity}` **{food['name']}** cho **{cock.name}**, tăng vĩnh viễn **+{spd_gain} SPD**!")
            return
            
        elif food_id == "14":
            # Breakthrough Stone: +1 star breakthrough per stone
            new_stars = cock.stars
            new_hp = cock.hp
            new_atk = cock.atk
            new_df = cock.df
            new_spd = cock.spd
            new_luk = cock.luk
            new_name = cock.name
            
            for _ in range(quantity):
                new_stars += 1
                if new_name == "Luffy" and new_stars == 6:
                    new_name = "Luffy Gear 4"
                    new_hp = int(new_hp * 2.0)
                    new_atk = int(new_atk * 2.0)
                    new_df = int(new_df * 2.0)
                    new_spd = int(new_spd * 2.0)
                    new_luk = int(new_luk * 2.0)
                else:
                    new_hp = int(new_hp * 1.3)
                    new_atk = int(new_atk * 1.3)
                    new_df = int(new_df * 1.3)
                    new_spd = int(new_spd * 1.3)
                    new_luk = int(new_luk * 1.3)

            kwargs = {
                "stars": new_stars,
                "hp": new_hp,
                "atk": new_atk,
                "df": new_df,
                "spd": new_spd,
                "luk": new_luk
            }
            if new_name != cock.name:
                kwargs["name"] = new_name
                
            self.economy.update_cock(cock.id, **kwargs)
            star_emoji_str = "⭐" * new_stars if new_stars <= 5 else f"⭐x{new_stars}"
            await ctx.send(
                f"💎 Bạn sử dụng `{quantity}` **{food['name']}** cho **{cock.name}**!\n"
                f"🎉 **ĐỘT PHÁ THÀNH CÔNG!** Nhân vật đã đột phá giới hạn cấp độ!\n"
                f"⭐ **Cấp sao mới:** {star_emoji_str}\n"
                f"📈 **Chỉ số mới:** ❤️ HP: `{new_hp}` | ⚔️ ATK: `{new_atk}` | 🛡️ DEF: `{new_df}` | ⚡ SPD: `{new_spd}`"
            )
            return
            
        # Default: normal EXP items (1-10)
        exp_gain = food["exp"] * quantity
        self.economy.update_cock(cock.id, exp=cock.exp + exp_gain)
        
        # Reload stats for level up check
        cock_row = self.economy.get_cock(cock.id)
        lvl_up_msg = ""
        if cock_row:
            lvl_up, start_lvl, end_lvl = self._level_up_cock(Cock(cock_row))
            if lvl_up:
                lvl_up_msg = f"\n🎉 **NHÂN VẬT ĐÃ TĂNG TỪ CẤP {start_lvl} LÊN CẤP {end_lvl}!**"
                
        await ctx.send(f"⚡ Bạn sử dụng `{quantity}` **{food['name']}** cho **{cock.name}**, nhận ngay **+{exp_gain} EXP**!{lvl_up_msg}")

    @daga_group.command(name="craft", brief="Ghép mảnh nhân vật để nhận nhân vật S/SS tự chọn.", aliases=["ghep", "exchange"])
    async def daga_craft(self, ctx: commands.Context, *, character_name: str | None = None):
        user_id = ctx.author.id
        # Check shards count
        inventory = self.economy.get_inventory(user_id)
        shard_qty = 0
        for inv_item, qty in inventory:
            if inv_item == "item_character_shard":
                shard_qty = qty
                break
                
        if not character_name:
            # S (Sử Thi): Kakashi, Meliodas, Ichigo
            # SS (Huyền Thoại): Gojo Satoru, Itachi Uchiha, Vegeta
            valid_list = [
                "Kakashi (Rarity S)",
                "Meliodas (Rarity S)",
                "Ichigo (Rarity S)",
                "Gojo Satoru (Rarity SS)",
                "Itachi Uchiha (Rarity SS)",
                "Vegeta (Rarity SS)"
            ]
            chars_list = "\n".join(f"• **{val}**" for val in valid_list)
            await ctx.send(
                f"🔮 **HỆ THỐNG GHÉP NHÂN VẬT TỰ CHỌN** 🔮\n\n"
                f"Bạn đang có: `{shard_qty}`/`10` mảnh nhân vật.\n"
                f"Hãy gõ lệnh: `{ctx.prefix}anime craft <tên_nhân_vật>` để nhận nhân vật mong muốn!\n\n"
                f"**Danh sách nhân vật có thể ghép (Yêu cầu 10 mảnh):**\n"
                f"{chars_list}"
            )
            return

        if shard_qty < 10:
            await ctx.send(f"❌ **Lỗi:** Bạn cần tối thiểu `10` **🔮 Mảnh nhân vật** để ghép nhân vật tự chọn. (Hiện tại bạn chỉ có `{shard_qty}` mảnh)")
            return
            
        valid_characters = {
            "kakashi": ("Kakashi", "Sử Thi"),
            "meliodas": ("Meliodas", "Sử Thi"),
            "ichigo": ("Ichigo", "Sử Thi"),
            "gojo": ("Gojo Satoru", "Huyền Thoại"),
            "gojo satoru": ("Gojo Satoru", "Huyền Thoại"),
            "itachi": ("Itachi Uchiha", "Huyền Thoại"),
            "itachi uchiha": ("Itachi Uchiha", "Huyền Thoại"),
            "vegeta": ("Vegeta", "Huyền Thoại"),
        }
        
        norm_name = character_name.strip().lower()
        if norm_name not in valid_characters:
            await ctx.send(f"❌ **Lỗi:** Nhân vật `{character_name}` không nằm trong danh sách ghép (hoặc sai tên). Hãy gõ `{ctx.prefix}anime craft` để xem danh sách.")
            return
            
        breed, rarity = valid_characters[norm_name]
        
        # Deduct 10 shards
        self.economy.add_inventory_item(user_id, "item_character_shard", -10)
        
        # Generate stats
        ranges = STAT_RANGES[rarity]
        hp = random.randint(*ranges["hp"])
        atk = random.randint(*ranges["atk"])
        df = random.randint(*ranges["df"])
        spd = random.randint(*ranges["spd"])
        luk = random.randint(*ranges["luk"])
        
        # Add character to DB
        cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = self.economy.add_cock(
            user_id, breed, rarity, hp, atk, df, spd, luk
        )
        
        display_rarity = RARITY_DISPLAY.get(rarity, rarity)
        rarity_emojis = {
            "Thường": "<:698204c:1515422780370190377>",
            "Hiếm": "<:759990b:1515423304620703905>",
            "Quý": "<:780661a:1515423318587609224>",
            "Sử Thi": "<:429893s:1515423348014715091>",
            "Huyền Thoại": "<:915638ss:1515423361310785536>",
            "Thần Kê": "<:886814sss:1515423524167225415>",
            "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
        }
        
        desc = (
            f"Bạn đã tiêu hao **10x 🔮 Mảnh nhân vật**...\n"
            f"✨ **Ghép thành công nhân vật tự chọn!**\n\n"
            f"⚔️ **Nhân vật:** `{breed}`\n"
            f"⭐ **Độ hiếm:** {rarity_emojis[rarity]} `{display_rarity}`\n"
            f"❤️ **Máu (HP):** `{final_stats['hp']}`\n"
            f"⚔️ **Sát thương (ATK):** `{final_stats['atk']}`\n"
            f"🛡️ **Phòng thủ (DEF):** `{final_stats['df']}`\n"
            f"⚡ **Tốc độ (SPD):** `{final_stats['spd']}`\n"
            f"🍀 **May mắn (LUK):** `{final_stats['luk']}`"
        )
        
        embed = make_embed(
            title="🔮 GHÉP NHÂN VẬT THÀNH CÔNG 🔮",
            description=desc,
            color=discord.Color.green()
        )
        
        img_name = get_cock_image_file(breed)
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_thumbnail(url=f"attachment://{img_name}")
            await ctx.send(embed=embed, file=file)
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @daga_group.command(name="info", brief="Xem thông tin chi tiết của nhân vật.")
    async def daga_info(self, ctx: commands.Context, cock_id: int | None = None):
        if cock_id is None:
            cock_row = self.economy.get_active_cock(ctx.author.id)
            if not cock_row:
                await ctx.send("❌ Bạn chưa chọn nhân vật chính xuất trận nào.")
                return
        else:
            cock_row = self.economy.get_cock(cock_id)
            if not cock_row:
                await ctx.send(f"❌ Không tìm thấy nhân vật ID `{cock_id}`.")
                return
            if cock_row[1] != ctx.author.id:
                await ctx.send("❌ Nhân vật này không thuộc sở hữu của bạn.")
                return

        c = Cock(cock_row)
        rarity_emojis = {
            "Thường": "⚪",
            "Hiếm": "🟢",
            "Quý": "🔵",
            "Sử Thi": "🟣",
            "Huyền Thoại": "🟡",
            "Thần Kê": "💠",
            "Exclusive": "👑"
        }

        stars_display = "0 Sao" if c.stars == 0 else ("⭐" * c.stars if c.stars <= 5 else f"⭐x{c.stars}")
        needed = c.stars + 1
        shards_display = f" (`{c.shards}/{needed}` mảnh nâng sao)"

        display_rarity = RARITY_DISPLAY.get(c.rarity, c.rarity)
        emoji_rarity = rarity_emojis.get(c.rarity, "⚪")

        info = {"series": "Unknown", "active": "Chưa rõ", "passive": "Chưa rõ"}
        for k, v in CHARACTER_INFO_MAP.items():
            if k.lower() in c.name.lower() or c.name.lower() in k.lower():
                info = v
                break

        # Format stats with thousand separators
        hp_str = f"{c.get_max_hp():,}"
        atk_str = f"{c.get_atk():,}"
        df_str = f"{c.get_df():,}"
        spd_str = f"{c.get_spd():,}"

        desc = (
            f"╔══════════════════════════════\n"
            f"║  {emoji_rarity} **{display_rarity}**\n"
            f"║\n"
            f"║  ⚔️ **{c.display_name}**\n"
            f"║  📺 **{info['series']}**\n"
            f"║\n"
            f"║  ❤️ HP: **{hp_str}**\n"
            f"║  ⚔️ ATK: **{atk_str}**\n"
            f"║  🛡️ DEF: **{df_str}**\n"
            f"║  ⚡ SPD: **{spd_str}**\n"
            f"║\n"
            f"║  💫 Kỹ năng: **{info['active']}**\n"
            f"║  ✨ Passive: **{info['passive']}**\n"
            f"╚══════════════════════════════\n\n"
            f"🆔 **ID Nhân vật:** `{c.id}`\n"
            f"⭐ **Cấp Sao:** `{stars_display}`{shards_display}\n"
            f"📈 **Cấp độ:** `{c.level}/100` (EXP: `{c.exp}/{c.level*100}`)\n"
            f"🏆 **Thành tích:** `{c.wins}` Thắng | `{c.losses}` Thua (Chuỗi: `{c.streak}`)"
        )

        embed = make_embed(
            title="📊 THÔNG TIN NHÂN VẬT 📊",
            description=desc,
            color=discord.Color.blue(),
        )
        img_name = get_cock_image_file(c.name)
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_image(url=f"attachment://{img_name}")
            await ctx.send(embed=embed, file=file)
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @daga_group.command(name="train", brief="Huấn luyện nhân vật tăng chỉ số ngẫu nhiên (cooldown 1 tiếng).")
    async def daga_train(self, ctx: commands.Context):
        active_row = self.economy.get_active_cock(ctx.author.id)
        if not active_row:
            await ctx.send("❌ Bạn chưa chọn nhân vật chính xuất trận nào.")
            return

        cock = Cock(active_row)
        now = int(time.time())
        cooldown = 3600 # 1 tiếng

        if now - cock.last_train < cooldown:
            seconds_left = cooldown - (now - cock.last_train)
            minutes = seconds_left // 60
            seconds = seconds_left % 60
            await ctx.send(f"⏳ **{cock.name}** đang mệt mỏi sau giáo trình huấn luyện trước. Hãy quay lại sau `{minutes} phút {seconds} giây`.")
            return

        # Train and increase random stat
        stats = ["hp", "atk", "df", "spd", "luk"]
        chosen_stat = random.choice(stats)
        stat_gain = random.randint(1, 3)

        current_val = getattr(cock, chosen_stat)
        new_val = current_val + stat_gain

        self.economy.update_cock(cock.id, last_train=now, **{chosen_stat: new_val})

        stat_names_vn = {
            "hp": "Máu (HP)",
            "atk": "Sát thương (ATK)",
            "df": "Phòng thủ (DEF)",
            "spd": "Tốc độ (SPD)",
            "luk": "May mắn (LUK)"
        }

        await ctx.send(f"🏋️‍♂️ Bạn cho **{cock.name}** tập luyện bài tập thể lực. Nhân vật tăng thêm **+{stat_gain} {stat_names_vn[chosen_stat]}**!")

        # Trigger random event check after training
        await self._trigger_random_event(ctx, cock)

    @daga_group.command(
        name="fight",
        brief="Thách đấu đá gà PvP đặt cược với người chơi khác.",
        usage="fight @user <tiền_cược>",
    )
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def daga_fight(self, ctx: commands.Context, opponent: discord.Member, bet: int = config.bot.default_bet):
        if opponent.bot:
            await ctx.send("❌ Bạn không thể thách đấu với bot!")
            return
        if opponent.id == ctx.author.id:
            await ctx.send("❌ Bạn không thể tự thách đấu với chính mình!")
            return

        author_team_rows = self.economy.get_team_cocks(ctx.author.id)
        author_team = [Cock(r) for r in author_team_rows.values() if r]
        if not author_team:
            await ctx.send("❌ Bạn chưa có nhân vật nào trong đội hình! Hãy dùng `i?anime team set <vt> <ID>` để sắp xếp đội hình.")
            return

        opponent_team_rows = self.economy.get_team_cocks(opponent.id)
        opponent_team = [Cock(r) for r in opponent_team_rows.values() if r]
        if not opponent_team:
            await ctx.send(f"❌ Đối thủ {opponent.mention} chưa có nhân vật nào trong đội hình để thi đấu.")
            return

        if len(author_team) < 3:
            await ctx.send(f"⚠️ **Cảnh báo:** Đội hình của bạn chưa đủ 3 nhân vật, sức mạnh sẽ yếu hơn!")
        if len(opponent_team) < 3:
            await ctx.send(f"⚠️ **Cảnh báo đối thủ:** Đội hình của {opponent.mention} chưa đủ 3 nhân vật, sức mạnh sẽ yếu hơn!")

        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
        except Exception as exc:
            await ctx.send(f"❌ **Bạn không đủ tiền cược:** {exc}")
            return
        try:
            validate_money_bet(self.economy, opponent.id, bet)
        except Exception:
            await ctx.send(f"❌ Đối thủ {opponent.mention} không có đủ tiền cược ({bet:,} VND).")
            return

        view = AcceptFightView(opponent, ctx.author, bet)
        await ctx.send(f"🥊 {opponent.mention}, bạn có đồng ý lời thách đấu đá gà mức cược **{bet:,} VND** từ {ctx.author.mention} không?", view=view)
        await view.wait()
        if not view.accepted:
            return

        author_team_rows = self.economy.get_team_cocks(ctx.author.id)
        author_team = [Cock(r) for r in author_team_rows.values() if r]
        opponent_team_rows = self.economy.get_team_cocks(opponent.id)
        opponent_team = [Cock(r) for r in opponent_team_rows.values() if r]

        if not author_team or not opponent_team:
            await ctx.send("❌ Trận đấu bị hủy: Một trong hai người chơi không còn nhân vật nào trong đội hình.")
            return
        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
            validate_money_bet(self.economy, opponent.id, bet)
        except Exception:
            await ctx.send("❌ Trận đấu bị hủy: Một trong hai người chơi không còn đủ tiền đặt cược.")
            return

        won_a, battle_logs = await self._run_team_pvp_battle(ctx, author_team, opponent_team, ctx.author, opponent, bet)

        if won_a is None:
            return

        winner = ctx.author if won_a else opponent
        loser = opponent if won_a else ctx.author
        winner_team = author_team if won_a else opponent_team
        loser_team = opponent_team if won_a else author_team

        self.economy.add_money(winner.id, bet)
        self.economy.add_money(loser.id, -bet)
        log_wallet_change(logger, event="daga_pvp_winner", user_id=winner.id, money_delta=bet, ctx=ctx, opponent_id=loser.id)
        log_wallet_change(logger, event="daga_pvp_loser", user_id=loser.id, money_delta=-bet, ctx=ctx, opponent_id=winner.id)

        for p_cock in winner_team:
            self.economy.update_cock(p_cock.id, wins=p_cock.wins + 1, streak=p_cock.streak + 1, exp=p_cock.exp + 150)
            updated_row = self.economy.get_cock(p_cock.id)
            if updated_row:
                lvl_up, start_lvl, end_lvl = self._level_up_cock(Cock(updated_row))
                if lvl_up:
                    await ctx.send(f"🎉 **{p_cock.name}** đã tăng từ cấp {start_lvl} lên cấp {end_lvl}!")

        for p_cock in loser_team:
            self.economy.update_cock(p_cock.id, losses=p_cock.losses + 1, streak=0, exp=p_cock.exp + 20)
            updated_row = self.economy.get_cock(p_cock.id)
            if updated_row:
                lvl_up, start_lvl, end_lvl = self._level_up_cock(Cock(updated_row))
                if lvl_up:
                    await ctx.send(f"🎉 **{p_cock.name}** đã tăng từ cấp {start_lvl} lên cấp {end_lvl}!")

        winner_row = self.economy.get_cock(winner_team[0].id)
        if winner_row:
            await self._trigger_random_event(ctx, Cock(winner_row))
        loser_row = self.economy.get_cock(loser_team[0].id)
        if loser_row:
            await self._trigger_random_event(ctx, Cock(loser_row))

    @daga_group.command(name="top", brief="Xem bảng xếp hạng sư kê giỏi nhất.")
    async def daga_top(self, ctx: commands.Context):
        self.economy.cur.execute("SELECT user_id, name, wins, level FROM user_cocks ORDER BY wins DESC LIMIT 10")
        rows = self.economy.cur.fetchall()
        
        if not rows:
            await ctx.send("Bảng xếp hạng đang trống.")
            return

        desc = ""
        for i, row in enumerate(rows):
            user = self.client.get_user(row[0])
            user_name = user.name if user else f"Người chơi {row[0]}"
            desc += f"{i+1}. **{user_name}** — Chiến kê: **{row[1]}** (Cấp {row[3]}) — **{row[2]}** Trận thắng\n"

        embed = make_embed(
            title="🏅 BẢNG XẾP HẠNG ĐẠI SƯ KÊ 🏅",
            description=desc,
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @daga_group.command(name="nangsao", brief="Đột phá nâng sao cho nhân vật bằng cách tiêu thụ bản trùng.", aliases=["dotpha", "upgrade", "breakthrough"])
    async def daga_nangsao(self, ctx: commands.Context, main_id: int | None = None):
        if main_id is not None:
            row = self.economy.get_cock(main_id)
            if not row:
                await ctx.send(f"❌ Không tìm thấy chiến kê ID `{main_id}`.")
                return
            if row[1] != ctx.author.id:
                await ctx.send("❌ Chiến kê này không thuộc sở hữu của bạn!")
                return
            c_main = Cock(row)
        else:
            c_main = None

        view = NangSaoInteractiveView(ctx.author, self.economy, c_main)
        embed = view.get_embed()
        
        # Check if we should attach image
        img_name = get_cock_image_file(c_main.name) if c_main else None
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_thumbnail(url=f"attachment://{img_name}")
            msg = await ctx.send(embed=embed, view=view, file=file)
        else:
            msg = await ctx.send(embed=embed, view=view)
        
        view.message = msg

    @daga_group.command(name="sell", brief="Bán chiến kê lấy tiền mặt (sell <id> hoặc sell all <độ_hiếm>).")
    async def daga_sell(self, ctx: commands.Context, target: str, rarity_arg: str | None = None):
        target = target.strip().lower()
        
        # Mapping base prices
        SELL_PRICES = {
            "Thường": 100000,
            "Hiếm": 200000,
            "Quý": 500000,
            "Sử Thi": 1500000,
            "Huyền Thoại": 4000000,
            "Thần Kê": 10000000,
            "Exclusive": 500000000
        }
        
        rarity_map = {
            "thường": "Thường", "common": "Thường", "c": "Thường",
            "hiếm": "Hiếm", "rare": "Hiếm", "b": "Hiếm",
            "quý": "Quý", "noble": "Quý", "precious": "Quý", "a": "Quý",
            "sử thi": "Sử Thi", "epic": "Sử Thi", "s": "Sử Thi",
            "huyền thoại": "Huyền Thoại", "legendary": "Huyền Thoại", "ss": "Huyền Thoại",
            "thần kê": "Thần Kê", "mythic": "Thần Kê", "sss": "Thần Kê",
            "exclusive": "Exclusive"
        }

        if target == "all":
            if not rarity_arg:
                await ctx.send("❌ Vui lòng nhập độ hiếm muốn bán hàng loạt! Ví dụ: `i?daga sell all C` hoặc `i?daga sell all common`")
                return
                
            rarity_clean = rarity_arg.strip().lower()
            viet_rarity = rarity_map.get(rarity_clean)
            if not viet_rarity:
                await ctx.send(f"❌ Độ hiếm `{rarity_arg}` không hợp lệ! Hãy chọn: `C`/`common`, `B`/`rare`, `A`/`noble`, `S`/`epic`, `SS`/`legendary`, `SSS`/`mythic`, `exclusive`")
                return
                
            cocks_rows = self.economy.get_cocks(ctx.author.id)
            if not cocks_rows:
                await ctx.send("🥚 Bạn chưa sở hữu chiến kê nào.")
                return
                
            to_sell = []
            for row in cocks_rows:
                if row[3] == viet_rarity and row[14] == 0:
                    to_sell.append(row)
                    
            if not to_sell:
                await ctx.send(f"❌ Bạn không có chiến kê nào ở độ hiếm `{viet_rarity}` đang nhàn rỗi để bán.")
                return
                
            total_earned = 0
            for row in to_sell:
                cid = row[0]
                cstars = row[19] if len(row) > 19 else 0
                base_price = SELL_PRICES.get(row[3], 100000)
                price = int(base_price + base_price * 0.5 * cstars)
                
                total_earned += price
                self.economy.delete_cock(cid)
                
            self.economy.add_money(ctx.author.id, total_earned)
            
            log_wallet_change(
                logger,
                event="sell_cocks_all",
                user_id=ctx.author.id,
                money_delta=total_earned,
                rarity=viet_rarity,
                count=len(to_sell)
            )
            
            await ctx.send(f"✅ Đã bán thành công **{len(to_sell)}** chiến kê độ hiếm **{viet_rarity}**, thu về **+{total_earned:,} VND**! 💰")
            
        else:
            try:
                cock_id = int(target)
            except ValueError:
                await ctx.send("❌ Cú pháp sai! Vui lòng dùng: `i?daga sell <ID>` hoặc `i?daga sell all <độ_hiếm>`")
                return
                
            row = self.economy.get_cock(cock_id)
            if not row:
                await ctx.send(f"❌ Không tìm thấy chiến kê ID `{cock_id}`.")
                return
                
            if row[1] != ctx.author.id:
                await ctx.send("❌ Chiến kê này không thuộc sở hữu của bạn!")
                return
                
            if row[14] == 1:
                await ctx.send("❌ Không thể bán chiến kê đang xuất trận chính! Hãy đổi gà xuất trận khác trước.")
                return
                
            cstars = row[19] if len(row) > 19 else 0
            base_price = SELL_PRICES.get(row[3], 100000)
            price = int(base_price + base_price * 0.5 * cstars)
            
            self.economy.delete_cock(cock_id)
            self.economy.add_money(ctx.author.id, price)
            
            log_wallet_change(
                logger,
                event="sell_cock_single",
                user_id=ctx.author.id,
                money_delta=price,
                cock_id=cock_id,
                breed=row[2],
                rarity=row[3],
                stars=cstars
            )
            
            stars_str = f" ({cstars}⭐)" if cstars > 0 else ""
            await ctx.send(f"✅ Đã bán chiến kê **{row[2]}**{stars_str} (ID: `{cock_id}`) thành công, nhận được **+{price:,} VND**! 💰")

    @daga_group.command(name="giveexclusive", brief="[ADMIN] Tặng nhân vật độc quyền Luffy cho người chơi.", hidden=True)
    @commands.is_owner()
    async def give_exclusive_cock(self, ctx: commands.Context, member: discord.Member):
        from app.discord_bot.cogs.daga import BREEDS, STAT_RANGES
        
        breed = "Luffy"
        rarity = "Exclusive"
        
        ranges = STAT_RANGES[rarity]
        hp = random.randint(*ranges["hp"])
        atk = random.randint(*ranges["atk"])
        df = random.randint(*ranges["df"])
        spd = random.randint(*ranges["spd"])
        luk = random.randint(*ranges["luk"])
        
        cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = self.economy.add_cock(
            member.id, breed, rarity, hp, atk, df, spd, luk
        )
        
        embed = make_embed(
            title="🔥 NHÂN VẬT ĐỘC QUYỀN ADMIN 🔥",
            description=(
                f"Admin đã ban tặng nhân vật huyền thoại siêu cấp cho **{member.mention}**!\n\n"
                f"⚔️ **Nhân vật:** `{breed}` (ID: `{cock_id}`)\n"
                f"👑 **Độ hiếm:** `Exclusive`\n"
                f"❤️ **Máu (HP):** `{hp}`\n"
                f"⚔️ **Sức mạnh (ATK):** `{atk}`\n"
                f"🛡️ **Phòng thủ (DEF):** `{df}`\n"
                f"⚡ **Tốc độ (SPD):** `{spd}`\n"
                f"🍀 **May mắn (LUK):** `{luk}`\n\n"
                f"👉 *Hãy gõ `i?anime active {cock_id}` để cho nhân vật này xuất trận!*"
            ),
            color=discord.Color.purple()
        )
        await ctx.send(embed=embed)


    async def _execute_pve_fight(self, ctx: commands.Context, floor: int):
        team_rows = self.economy.get_team_cocks(ctx.author.id)
        team_cocks = [Cock(r) for r in team_rows.values() if r]

        if not team_cocks:
            await ctx.send("❌ **Bạn chưa có nhân vật nào trong đội hình!** Hãy dùng `i?anime team set <vt> <ID>` để sắp xếp đội hình.")
            return
        if len(team_cocks) < 3:
            await ctx.send("⚠️ **Cảnh báo:** Đội hình của bạn chưa đủ 3 nhân vật, sức mạnh sẽ yếu hơn!")

        if floor > 50:
            now = int(time.time())
            last_claim = self.economy.get_pve_cooldown(ctx.author.id, "tower_daily_claim")
            last_date = time.strftime('%Y-%m-%d', time.localtime(last_claim)) if last_claim else ""
            current_date = time.strftime('%Y-%m-%d', time.localtime(now))
            embed = make_embed(
                title="🏰 THÁP ĐẠI CHIẾN ANIME — HOÀN THÀNH 🏰",
                description=(
                    f"🏆 **Xin chúc mừng!** Bạn đã chinh phục toàn bộ 50 tầng của Tháp Đại Chiến.\n"
                    f"👑 **Danh hiệu:** `Người Chinh Phục Tháp`\n\n"
                    f"🔁 **Phần thưởng lặp lại hàng ngày:** `2,000,000 VND / ngày`"
                ),
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)
            if last_date == current_date:
                await ctx.send("❌ **Bạn đã nhận phần thưởng lặp lại hôm nay rồi!** Hãy quay lại vào ngày mai nhé. 🌟")
            else:
                self.economy.add_money(ctx.author.id, 2000000)
                self.economy.set_pve_cooldown(ctx.author.id, "tower_daily_claim", now)
                log_wallet_change(logger, event="pve_tower_daily_repeat_reward", user_id=ctx.author.id, money_delta=2000000)
                await ctx.send("🎁 **Nhận thưởng lặp lại:** Bạn đã nhận **+2,000,000 VND** thành công! 💰")
            return

        boss_data = PVE_STAGES["tower"][floor - 1]
        team_names = ", ".join(c.name for c in team_cocks)
        start_embed = make_embed(
            title=f"🏰 THÁP ĐẠI CHIẾN — TẦNG {floor} / 50 🏰",
            description=(
                f"👤 **Đội hình khiêu chiến:** {team_names}\n"
                f"👹 **Đối thủ:** `{boss_data['name']}` ({boss_data['series']})\n"
                f"📊 **Chỉ số:** HP `{boss_data['hp']:,}` | ATK `{boss_data['atk']}` | DEF `{boss_data['df']}`\n\n"
                f"⚔️ **Chuẩn bị vào trận...**"
            ),
            color=discord.Color.blue()
        )
        await ctx.send(embed=start_embed)

        won, damage_dealt = await self._run_team_pve_battle(ctx, team_cocks, boss_data, "tower")

        if won:
            money_won = boss_data["reward_money"]
            exp_won = boss_data["reward_exp"]
            self.economy.add_money(ctx.author.id, money_won)
            log_wallet_change(logger, event=f"pve_tower_floor_{floor}_win", user_id=ctx.author.id, money_delta=money_won)
            
            current_db_floor = self.economy.get_pve_cooldown(ctx.author.id, "tower_floor")
            if current_db_floor == floor:
                self.economy.set_pve_cooldown(ctx.author.id, "tower_floor", floor + 1)
                unlocked_floor = floor + 1
            else:
                unlocked_floor = current_db_floor

            for p_cock in team_cocks:
                self.economy.update_cock(p_cock.id, exp=p_cock.exp + exp_won)
                updated_row = self.economy.get_cock(p_cock.id)
                if updated_row:
                    lvl_up, start_lvl, end_lvl = self._level_up_cock(Cock(updated_row))
                    if lvl_up:
                        await ctx.send(f"🎉 **NHÂN VẬT ĐÃ TĂNG CẤP!** `{p_cock.name}` tăng từ cấp `{start_lvl}` lên cấp `{end_lvl}`! 🐓")

            shards_won = boss_data.get("reward_shards", 0)
            if shards_won > 0:
                self.economy.add_inventory_item(ctx.author.id, "item_character_shard", shards_won)

            view = PvePostBattleView(self, ctx.author.id, floor, unlocked_floor)

            if floor == 50:
                breed = random.choice(BREEDS["Thần Kê"])
                ranges = STAT_RANGES["Thần Kê"]
                hp = random.randint(*ranges["hp"])
                atk = random.randint(*ranges["atk"])
                df = random.randint(*ranges["df"])
                spd = random.randint(*ranges["spd"])
                luk = random.randint(*ranges["luk"])
                self.economy.add_cock(ctx.author.id, breed, "Thần Kê", hp, atk, df, spd, luk)
                self.economy.add_inventory_item(ctx.author.id, "item_character_shard", 15)
                victory_embed = make_embed(
                    title="🎉 CHIẾN TÍCH THẦN THOẠI — CHINH PHỤC THÁP 🎉",
                    description=(
                        f"🏆 **Xin chúc mừng {ctx.author.mention}!** Bạn đã chinh phục Tháp Đại Chiến!\n\n"
                        f"🔮 **Mảnh nhân vật:** `+15 Mảnh`\n"
                        f"🐓 **Nhân vật Thần Kê đặc biệt:** `{breed}`\n\n"
                        f"🔁 Kể từ ngày mai, bạn có thể nhận **+2,000,000 VND / ngày** làm phần thưởng lặp lại!"
                    ),
                    color=discord.Color.gold()
                )
                msg = await ctx.send(embed=victory_embed, view=view)
                view.message = msg
            else:
                success_embed = make_embed(
                    title=f"🎉 VƯỢT TẦNG {floor} THÀNH CÔNG! 🎉",
                    description=(
                        f"Bạn đã vượt qua tầng **{floor}** thành công và mở khóa tầng **{floor+1}**!\n\n"
                        f"🏆 **Phần thưởng nhận được:**\n"
                        f"💰 `+{money_won:,} VND`\n"
                        f"🔰 `+{exp_won} EXP`"
                    ),
                    color=discord.Color.green()
                )
                if shards_won > 0:
                    success_embed.description += f"\n🔮 `+{shards_won} Mảnh nhân vật`"
                msg = await ctx.send(embed=success_embed, view=view)
                view.message = msg
        else:
            unlocked_floor = self.economy.get_pve_cooldown(ctx.author.id, "tower_floor")
            exp_won = int(boss_data["reward_exp"] * 0.2)
            for p_cock in team_cocks:
                self.economy.update_cock(p_cock.id, exp=p_cock.exp + exp_won)
                updated_row = self.economy.get_cock(p_cock.id)
                if updated_row:
                    self._level_up_cock(Cock(updated_row))
            
            view = PvePostBattleView(self, ctx.author.id, floor, unlocked_floor)
            msg = await ctx.send(f"💀 **Thất bại ở tầng {floor}!** Hãy nâng cấp đội hình và thử lại.", view=view)
            view.message = msg

    @daga_group.command(name="pve", brief="Tham gia Tháp Đại Chiến Anime — leo tháp 50 tầng!", aliases=["tower", "climb"])
    @commands.cooldown(1, 5, type=commands.BucketType.user)
    async def anime_pve(self, ctx: commands.Context):
        floor = self.economy.get_pve_cooldown(ctx.author.id, "tower_floor")
        if floor <= 0:
            floor = 1
            self.economy.set_pve_cooldown(ctx.author.id, "tower_floor", 1)
        await self._execute_pve_fight(ctx, floor)

async def setup(client: commands.Bot):
    await client.add_cog(Daga(client))
