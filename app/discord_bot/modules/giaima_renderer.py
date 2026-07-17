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

def render_guess_image(digits: list, colors: list) -> io.BytesIO:
    """
    Renders an image of the guess digits with their corresponding colors:
    - green: correct digit & correct position
    - yellow: correct digit wrong position
    - gray: incorrect digit
    - blue: wildcard match
    """
    length = len(digits)
    
    # Constants
    box_size = 90
    gap = 20
    margin = 40
    
    width = length * box_size + (length - 1) * gap + margin * 2
    height = 200
    
    # Base dark background #1e1e2e
    image = Image.new("RGBA", (width, height), (30, 30, 46, 255))
    draw = ImageDraw.Draw(image)
    
    # Radial purple gradient glow in the center
    cx, cy = width / 2, height / 2
    max_radius = max(width, height) * 0.75
    for r in range(int(max_radius), 0, -4):
        alpha = int(24 * (1 - (r / max_radius) ** 2))
        if alpha > 0:
            glow_layer = Image.new("RGBA", (width, height), (0, 0, 0, 0))
            glow_draw = ImageDraw.Draw(glow_layer)
            # Violet color: (139, 92, 246)
            glow_draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(139, 92, 246, alpha))
            image = Image.alpha_composite(image, glow_layer)
            
    # Re-draw on the composited image
    draw = ImageDraw.Draw(image)
    
    # Color palette
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
    
    # Load fonts
    font_digit = load_rajdhani_font(52)
    
    # Centering math
    start_x = (width - (length * box_size + (length - 1) * gap)) / 2
    y_pos = (height - box_size) / 2
    
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
