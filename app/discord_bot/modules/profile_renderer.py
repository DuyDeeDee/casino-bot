import logging
import urllib.request
import os
import aiohttp
from io import BytesIO
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.config import config

logger = logging.getLogger(__name__)

def get_font_path(font_type: str) -> Path:
    """Gets local path to Outfit font, downloading it if not present."""
    font_dir = Path(config.storage.data_dir) / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    
    filename = f"Outfit-{font_type.capitalize()}.ttf"
    font_path = font_dir / filename
    
    if not font_path.exists():
        weight = "700" if font_type == "bold" else "400"
        url = f"https://cdn.jsdelivr.net/fontsource/fonts/outfit@latest/latin-{weight}-normal.ttf"
        try:
            logger.info(f"Downloading premium font from {url} to {font_path}...")
            urllib.request.urlretrieve(url, str(font_path))
        except Exception as e:
            logger.error(f"Failed to download font: {e}")
            
    return font_path

def load_font(font_type: str, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    """Attempts to load Outfit, falls back to system fonts, and finally default PIL font."""
    font_path = get_font_path(font_type)
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
            
    fallbacks = []
    if os.name == 'nt':  # Windows
        if font_type == 'bold':
            fallbacks.extend(["arialbd.ttf", "segoeuib.ttf"])
        else:
            fallbacks.extend(["arial.ttf", "segoeui.ttf"])
    else:  # Linux/Mac
        fallbacks.extend([
            "DejaVuSans-Bold.ttf" if font_type == 'bold' else "DejaVuSans.ttf",
            "LiberationSans-Bold.ttf" if font_type == 'bold' else "LiberationSans-Regular.ttf",
            "FreeSansBold.ttf" if font_type == 'bold' else "FreeSans.ttf"
        ])
        
    for f in fallbacks:
        try:
            return ImageFont.truetype(f, size)
        except Exception:
            try:
                if os.name == 'nt':
                    p = Path("C:/Windows/Fonts") / f
                else:
                    p = Path("/usr/share/fonts/truetype") / f
                if p.exists():
                    return ImageFont.truetype(str(p), size)
            except Exception:
                pass
                
    return ImageFont.load_default()

async def fetch_avatar(url: str) -> bytes | None:
    """Asynchronously fetches the user's avatar image bytes."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    return await response.read()
    except Exception as e:
        logger.error(f"Failed to fetch avatar: {e}")
    return None

def format_money_short(val: int) -> str:
    """Formats large money values into short forms like 1.5M, 2.3B."""
    if val >= 1_000_000_000:
        return f"{val / 1_000_000_000:.1f}B VND"
    if val >= 1_000_000:
        return f"{val / 1_000_000:.1f}M VND"
    return f"{val:,} VND"

def get_rank_info(net_worth: int) -> tuple[str, tuple[int, int, int], tuple[int, int, int]]:
    """Returns (rank_name, fill_color, text_color)."""
    if net_worth < 1_000_000:
        return "Con Nợ Quốc Dân", (139, 0, 0), (255, 255, 255) # Dark Red
    elif net_worth < 10_000_000:
        return "Dân Chơi Mới Nổi", (70, 130, 180), (255, 255, 255) # Steel Blue
    elif net_worth < 50_000_000:
        return "Thần Bài Bình Dân", (46, 139, 87), (255, 255, 255) # Sea Green
    elif net_worth < 200_000_000:
        return "Đại Gia Thành Phố", (218, 165, 32), (0, 0, 0) # Goldenrod
    elif net_worth < 1_000_000_000:
        return "Triệu Phú Sòng Bài", (186, 85, 211), (255, 255, 255) # Medium Orchid
    else:
        return "Tỷ Phú Đô La", (255, 69, 0), (255, 255, 255) # Red-Orange

async def render_profile_banner(
    username: str,
    avatar_url: str,
    money: int,
    gold: int,
    gold_price: int,
    loan_amount: int,
    biz_count: int,
    inv_count: int
) -> BytesIO:
    """Renders a beautiful profile banner card and returns it as a BytesIO buffer."""
    
    # 1. Background
    width, height = 800, 300
    gradient = Image.new("RGBA", (1, 2))
    # Elegant dark purple / gold-bordered vibe
    gradient.putpixel((0, 0), (26, 11, 46, 255))
    gradient.putpixel((0, 1), (11, 4, 16, 255))
    img = gradient.resize((width, height), Image.Resampling.BILINEAR)
    
    draw = ImageDraw.Draw(img)
    
    # Draw glowing outline border
    draw.rounded_rectangle([6, 6, width - 6, height - 6], radius=16, outline=(255, 215, 0, 80), width=3)
    
    # 2. Draw Avatar
    avatar_bytes = await fetch_avatar(avatar_url)
    avatar_size = 140
    avatar_x, avatar_y = 40, (height - avatar_size) // 2
    
    if avatar_bytes:
        try:
            avatar_img = Image.open(BytesIO(avatar_bytes)).convert("RGBA")
            avatar_img = avatar_img.resize((avatar_size, avatar_size), Image.Resampling.LANCZOS)
            
            # Make circle mask
            mask = Image.new("L", (avatar_size, avatar_size), 0)
            mask_draw = ImageDraw.Draw(mask)
            mask_draw.ellipse((0, 0, avatar_size, avatar_size), fill=255)
            
            # Paste avatar circular
            avatar_circle = Image.new("RGBA", (avatar_size, avatar_size), (0, 0, 0, 0))
            avatar_circle.paste(avatar_img, (0, 0), mask=mask)
            img.paste(avatar_circle, (avatar_x, avatar_y), mask=avatar_circle)
            avatar_img.close()
        except Exception as e:
            logger.error(f"Error drawing avatar: {e}")
            # Fallback placeholder circle
            draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill=(100, 100, 100, 255))
    else:
        # Fallback placeholder circle
        draw.ellipse([avatar_x, avatar_y, avatar_x + avatar_size, avatar_y + avatar_size], fill=(100, 100, 100, 255))
        
    # Avatar gold border
    draw.ellipse([avatar_x - 3, avatar_y - 3, avatar_x + avatar_size + 3, avatar_y + avatar_size + 3], outline=(255, 215, 0, 180), width=4)
    
    # 3. Load Fonts
    font_title = load_font("bold", 34)
    font_badge = load_font("bold", 13)
    font_widget_title = load_font("regular", 11)
    font_widget_val = load_font("bold", 15)
    
    # 4. Draw Username & Rank
    net_worth = money + (gold * gold_price) - loan_amount
    rank_name, badge_bg, badge_fg = get_rank_info(net_worth)
    
    # Draw Username
    draw.text((200, 50), username, font=font_title, fill=(255, 255, 255, 255))
    
    # Draw Rank Badge
    # Calculate badge size based on text length
    # A simple fallback for text measurement if not supported
    try:
        text_w = font_badge.getlength(rank_name)
    except AttributeError:
        # Fallback estimate
        text_w = len(rank_name) * 8
        
    badge_w = int(text_w + 20)
    badge_h = 24
    badge_x, badge_y = 200, 105
    
    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], radius=6, fill=badge_bg)
    draw.text((badge_x + 10, badge_y + 4), rank_name, font=font_badge, fill=badge_fg)
    
    # Draw Loan Warning inside badge line if active loan exists
    if loan_amount > 0:
        loan_text = f"Nợ: -{format_money_short(loan_amount)}"
        try:
            loan_w = font_badge.getlength(loan_text)
        except AttributeError:
            loan_w = len(loan_text) * 8
        draw.rounded_rectangle([badge_x + badge_w + 10, badge_y, badge_x + badge_w + 10 + int(loan_w + 20), badge_y + badge_h], radius=6, fill=(139, 0, 0))
        draw.text((badge_x + badge_w + 20, badge_y + 4), loan_text, font=font_badge, fill=(255, 255, 255))

    # 5. Draw 4 Status Widgets (Horizontal Row)
    widget_y = 155
    widget_h = 85
    widget_w = 132
    widget_gap = 12
    start_x = 200
    
    widgets = [
        ("TÀI KHOẢN (VND)", format_money_short(money), (46, 204, 113, 255)), # Green tint
        ("KÉT SẮT (VÀNG)", f"{gold} Vàng", (241, 196, 15, 255)), # Yellow tint
        ("DOANH NGHIỆP", f"{biz_count} Cơ sở", (52, 152, 219, 255)), # Blue tint
        ("TÚI ĐỒ (SHOP)", f"{inv_count} Vật phẩm", (155, 89, 182, 255)), # Purple tint
    ]
    
    for idx, (title, value, color_theme) in enumerate(widgets):
        box_x = start_x + idx * (widget_w + widget_gap)
        # frosted glass box
        draw.rounded_rectangle(
            [box_x, widget_y, box_x + widget_w, widget_y + widget_h],
            radius=10,
            fill=(255, 255, 255, 12),
            outline=(255, 255, 255, 25),
            width=1
        )
        
        # Color accent strip on left border
        draw.rounded_rectangle(
            [box_x, widget_y, box_x + 4, widget_y + widget_h],
            radius=10,
            fill=color_theme
        )
        
        # Widget title
        draw.text((box_x + 12, widget_y + 15), title, font=font_widget_title, fill=(200, 200, 200, 200))
        
        # Widget value
        draw.text((box_x + 12, widget_y + 40), value, font=font_widget_val, fill=(255, 255, 255, 255))
        
    # Save image to BytesIO
    output = BytesIO()
    img.save(output, format="PNG")
    output.seek(0)
    img.close()
    return output
