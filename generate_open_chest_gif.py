"""
Generates pictures/open_chest.gif: Xianxia Treasure Chest Opening GIF for Gacha Banner.
"""

import os
import math
from PIL import Image, ImageDraw, ImageFont

FONT_PATH = "test.ttf"

def get_font(size: int):
    if os.path.exists(FONT_PATH):
        try:
            return ImageFont.truetype(FONT_PATH, size)
        except Exception:
            pass
    return ImageFont.load_default()

def draw_rounded_rect(draw, coords, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(coords, radius=radius, fill=fill, outline=outline, width=width)

def generate_open_chest_gif(output_path="pictures/open_chest.gif"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    WIDTH, HEIGHT = 400, 300
    frames = []
    font_title = get_font(20)
    font_sparkle = get_font(28)

    num_frames = 12
    for i in range(num_frames):
        img = Image.new("RGBA", (WIDTH, HEIGHT), (14, 12, 24, 255))
        draw = ImageDraw.Draw(img)

        # Border
        draw_rounded_rect(draw, (8, 8, WIDTH - 8, HEIGHT - 8), radius=12, fill=(22, 20, 36, 255), outline=(210, 165, 75, 255), width=2)
        
        # Header text
        draw.text((WIDTH // 2, 30), "✨ THIÊN ĐỊA DUYÊN CƠ ✨", font=font_title, fill=(255, 215, 0, 255), anchor="mm")

        # Progress of opening (0.0 closed to 1.0 fully open)
        open_ratio = min(1.0, max(0.0, (i - 2) / 6.0))

        # Glowing Light Beams
        cx, cy = WIDTH // 2, HEIGHT // 2 + 20
        if open_ratio > 0:
            beam_count = int(12 * open_ratio)
            for b in range(beam_count):
                angle = (b / 12.0) * math.pi - math.pi / 2 + (i * 0.1)
                bx = cx + int(math.cos(angle) * 180)
                by = cy + int(math.sin(angle) * 180)
                beam_color = (255, 215, 0, int(180 * open_ratio)) if b % 2 == 0 else (255, 80, 80, int(180 * open_ratio))
                draw.line([(cx, cy), (bx, by)], fill=beam_color, width=int(3 + 4 * open_ratio))

        # Chest Base
        chest_w, chest_h = 140, 80
        chest_x = cx - chest_w // 2
        chest_y = cy
        draw_rounded_rect(draw, (chest_x, chest_y, chest_x + chest_w, chest_y + chest_h), radius=8, fill=(120, 75, 25, 255), outline=(255, 215, 0, 255), width=2)
        # Lock ornament
        draw_rounded_rect(draw, (cx - 12, chest_y + 15, cx + 12, chest_y + 40), radius=4, fill=(255, 215, 0, 255))

        # Chest Lid (opens upwards)
        lid_offset = int(open_ratio * 45)
        lid_y1 = chest_y - 25 - lid_offset
        lid_y2 = chest_y - lid_offset
        draw_rounded_rect(draw, (chest_x - 5, lid_y1, chest_x + chest_w + 5, lid_y2), radius=6, fill=(160, 100, 35, 255), outline=(255, 230, 120, 255), width=2)

        # Sparkles when fully opening
        if open_ratio > 0.5:
            draw.text((cx - 60, cy - 60), "✨", font=font_sparkle, fill=(255, 255, 200, 255))
            draw.text((cx + 40, cy - 70), "🌟", font=font_sparkle, fill=(255, 200, 100, 255))
            draw.text((cx, cy - 80), "🔴", font=font_title, fill=(255, 50, 50, 255), anchor="mm")

        # Convert to P mode for GIF
        p_frame = img.convert("RGB").convert("P", palette=Image.ADAPTIVE)
        frames.append(p_frame)

    frames[0].save(
        output_path,
        save_all=True,
        append_images=frames[1:],
        optimize=False,
        duration=120,
        loop=0
    )
    print(f"Generated {output_path} successfully!")

if __name__ == "__main__":
    generate_open_chest_gif()
