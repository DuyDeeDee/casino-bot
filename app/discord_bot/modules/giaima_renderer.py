import os
import logging
import urllib.request
import io
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

from app.config import config

logger = logging.getLogger(__name__)

def get_rajdhani_font_path() -> Path:
    """Gets local path to Rajdhani font, downloading it if not present."""
    font_dir = Path(config.storage.data_dir) / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    
    font_path = font_dir / "Rajdhani-Bold.ttf"
    
    if not font_path.exists():
        url = "https://github.com/google/fonts/raw/main/ofl/rajdhani/Rajdhani-Bold.ttf"
        try:
            logger.info(f"Downloading Rajdhani-Bold font from {url} to {font_path}...")
            urllib.request.urlretrieve(url, str(font_path))
        except Exception as e:
            logger.error(f"Failed to download font Rajdhani-Bold: {e}")
            
    return font_path

def load_rajdhani_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = get_rajdhani_font_path()
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
            
    # fallbacks
    fallbacks = []
    if os.name == 'nt':  # Windows
        fallbacks.extend(["arialbd.ttf", "segoeuib.ttf"])
    else:
        fallbacks.extend(["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf"])
        
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

def get_roboto_font_path() -> Path:
    """Gets local path to Roboto font, downloading it if not present."""
    font_dir = Path(config.storage.data_dir) / "fonts"
    font_dir.mkdir(parents=True, exist_ok=True)
    
    font_path = font_dir / "Roboto-Bold.ttf"
    
    if not font_path.exists():
        url = "https://github.com/googlefonts/roboto-2/raw/main/src/hinted/Roboto-Bold.ttf"
        try:
            logger.info(f"Downloading Roboto-Bold font from {url} to {font_path}...")
            urllib.request.urlretrieve(url, str(font_path))
        except Exception as e:
            logger.error(f"Failed to download font Roboto-Bold: {e}")
            
    return font_path

def load_roboto_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    font_path = get_roboto_font_path()
    if font_path.exists():
        try:
            return ImageFont.truetype(str(font_path), size)
        except Exception:
            pass
            
    # fallbacks
    fallbacks = []
    if os.name == 'nt':  # Windows
        fallbacks.extend(["arialbd.ttf", "segoeuib.ttf"])
    else:
        fallbacks.extend(["DejaVuSans-Bold.ttf", "LiberationSans-Bold.ttf", "FreeSansBold.ttf"])
        
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

def render_guess_image(
    digits: list,
    colors: list,
    difficulty: str = "normal",
    attempt: int = 1,
    max_attempts: int = 5
) -> io.BytesIO:
    """
    Renders an image of the guess digits with their corresponding colors:
    - green: correct digit & correct position
    - yellow: correct digit wrong position
    - gray: incorrect digit
    - blue: wildcard match
    Also renders a modern cyberpunk game card layout with header information.
    """
    length = len(digits)
    
    # Constants
    box_size = 90
    gap = 20
    margin = 40
    
    width = length * box_size + (length - 1) * gap + margin * 2
    height = 250  # Increased height to fit header
    
    # Base dark background #1e1e2e
    image = Image.new("RGBA", (width, height), (30, 30, 46, 255))
    draw = ImageDraw.Draw(image)
    
    # Radial purple gradient glow in the center of digit boxes area
    cx, cy = width / 2, 65 + (height - 65) / 2
    max_radius = max(width, height - 65) * 0.8
    for r in range(int(max_radius), 0, -4):
        alpha = int(24 * (1 - (r / max_radius) ** 2))
        if alpha > 0:
            glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)
            glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(139, 92, 246, alpha))
            image = Image.alpha_composite(image, glow_layer)
            
    # Re-draw on the composited image
    draw = ImageDraw.Draw(image)
    
    # Load fonts
    font_header_left = load_roboto_font(20)   # Roboto supports Vietnamese!
    font_header_right = load_roboto_font(16)  # Roboto supports Vietnamese!
    font_digit = load_rajdhani_font(52)       # Rajdhani ONLY for digits!
    
    # Render Header Text
    # Left Header: Game Title (No emojis, avoiding boxes)
    left_title = "GIẢI MÃ BÍ MẬT"
    if difficulty == "boss":
        left_title = "BOSS SERVER"
    draw.text((40, 20), left_title, fill=(200, 168, 75, 255), font=font_header_left) # Golden Accent
    
    # Right Header: Difficulty and attempt info
    diff_name = "THƯỜNG"
    diff_color = (255, 255, 255, 255)
    if difficulty == "easy":
        diff_name = "DỄ"
        diff_color = (46, 204, 113, 255) # Green
    elif difficulty == "normal":
        diff_name = "THƯỜNG"
        diff_color = (241, 196, 15, 255) # Gold
    elif difficulty == "hard":
        diff_name = "KHÓ"
        diff_color = (230, 126, 34, 255) # Orange
    elif difficulty == "nightmare":
        diff_name = "ÁC MỘNG"
        diff_color = (231, 76, 60, 255) # Red
    elif difficulty == "boss":
        diff_name = "JACKPOT"
        diff_color = (155, 89, 182, 255) # Purple
        
    if difficulty == "boss":
        right_text = "MẬT MÃ TOÀN SERVER"
    else:
        right_text = f"{diff_name} • LƯỢT {attempt}/{max_attempts}"
        
    # Draw right text aligned to right
    try:
        draw.text((width - 40, 24), right_text, fill=diff_color, font=font_header_right, anchor="ra")
    except Exception:
        text_w = draw.textlength(right_text, font=font_header_right)
        draw.text((width - 40 - text_w, 24), right_text, fill=diff_color, font=font_header_right)
        
    # Divider line
    draw.line([(40, 58), (width - 40, 58)], fill=(69, 71, 90, 255), width=2) # #45475a
    
    # Color palette for digit boxes
    color_map = {
        "green": {
            "fill": (40, 167, 69, 255),    # #28a745
            "border": (25, 135, 84, 255)   # #198754
        },
        "yellow": {
            "fill": (212, 175, 55, 255),    # #d4af37 (Gold/Yellow)
            "border": (184, 134, 11, 255)   # #b8860b (Dark Goldenrod)
        },
        "gray": {
            "fill": (69, 71, 90, 255),     # #45475a
            "border": (30, 30, 46, 255)    # #1e1e2e
        },
        "blue": {
            "fill": (13, 110, 253, 255),   # #0d6efd
            "border": (10, 88, 202, 255)   # #0a58ca
        }
    }
    
    # Centering math for boxes in body
    start_x = (width - (length * box_size + (length - 1) * gap)) / 2
    y_pos = 58 + (height - 58 - box_size) / 2
    
    for i in range(length):
        digit = str(digits[i])
        color_name = colors[i]
        
        cfg = color_map.get(color_name, color_map["gray"])
        fill_color = cfg["fill"]
        border_color = cfg["border"]
        
        bx1 = start_x + i * (box_size + gap)
        by1 = y_pos
        bx2 = bx1 + box_size
        by2 = by1 + box_size
        
        # Draw rounded rectangle with border
        draw.rounded_rectangle([bx1, by1, bx2, by2], radius=14, fill=fill_color, outline=border_color, width=3)
        
        # Center the text
        try:
            draw.text((bx1 + box_size/2, by1 + box_size/2), digit, fill=(255, 255, 255, 255), font=font_digit, anchor="mm")
        except Exception:
            text_w = draw.textlength(digit, font=font_digit)
            text_h = 40
            draw.text((bx1 + (box_size - text_w)/2, by1 + (box_size - text_h)/2 - 5), digit, fill=(255, 255, 255, 255), font=font_digit)
            
    # Output to BytesIO
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    buf.seek(0)
    return buf
