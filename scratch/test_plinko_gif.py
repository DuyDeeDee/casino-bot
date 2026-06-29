import os
import sys
import random
from io import BytesIO
from datetime import datetime

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from PIL import Image, ImageDraw, ImageFont
from app.discord_bot.modules.profile_renderer import load_font

BIN_LAYOUTS = {
    "low": [1.5, 1.2, 1.0, 0.8, 1.0, 1.2, 1.5],
    "medium": [5.0, 2.0, 1.0, 0.5, 0.2, 0.5, 1.0, 2.0, 5.0],
    "high": [100.0, 25.0, 10.0, 5.0, 2.0, 0.0, 0.2, 0.5, 1.0, 3.0, 100.0]
}

def render_plinko_gif(
    risk: str,
    multiplier: float,
    target_index: int,
    directions: list[str],
) -> BytesIO:
    # 1. Determine size
    width = 412
    height = 250
    
    # 2. Get configuration
    N = len(directions) # 6, 8, or 10
    
    frames = []
    
    for f in range(N + 1):
        # Panel bg #161a2e
        img = Image.new("RGBA", (width, height), (22, 26, 46, 255))
        draw = ImageDraw.Draw(img)
        
        # Load fonts
        font_small = load_font("regular", 10)
        
        # Title box
        draw.text((width/2 - 45, 12), "ĐƯỜNG BÓNG RƠI", font=font_small, fill=(143, 148, 168, 255))
        
        cx = width / 2
        y0 = 35
        
        if N == 6:
            dy, dx = 26, 34
        elif N == 8:
            dy, dx = 20, 26
        else:
            dy, dx = 16, 20
            
        # Draw pegs
        for r in range(N):
            num_pegs = r + 1
            peg_xs = [cx + (i - r / 2) * dx for i in range(num_pegs)]
            y_peg = y0 + r * dy
            for px in peg_xs:
                draw.ellipse([px - 2, y_peg - 2, px + 2, y_peg + 2], fill=(71, 85, 105, 255))
                
        # Draw bins
        y_bin = y0 + N * dy
        bin_layout = BIN_LAYOUTS[risk]
        w_bin = dx - 4
        h_bin = 22
        
        for i, val in enumerate(bin_layout):
            bx_center = cx + (i - N / 2) * dx
            bx1 = bx_center - w_bin / 2
            bx2 = bx_center + w_bin / 2
            by1 = y_bin
            by2 = y_bin + h_bin
            
            is_active = (f == N and i == target_index)
            bin_text = f"{val:.1f}x" if val % 1 != 0 else f"{int(val)}x"
            
            if is_active:
                draw.rounded_rectangle([bx1, by1, bx2, by2], radius=4, fill=(45, 212, 191, 255), outline=(20, 184, 166, 255), width=1)
                try:
                    btn_w = font_small.getlength(bin_text)
                except AttributeError:
                    btn_w = len(bin_text) * 5
                draw.text((bx_center - btn_w/2, by1 + 5), bin_text, font=font_small, fill=(15, 19, 34, 255))
            else:
                draw.rounded_rectangle([bx1, by1, bx2, by2], radius=4, fill=(17, 21, 36, 255), outline=(34, 40, 62, 255), width=1)
                try:
                    btn_w = font_small.getlength(bin_text)
                except AttributeError:
                    btn_w = len(bin_text) * 5
                draw.text((bx_center - btn_w/2, by1 + 5), bin_text, font=font_small, fill=(52, 211, 153, 100))
                
        # Draw path
        path_coords = [(cx, y0 - 15)]
        offset = 0
        for s in range(1, f + 1):
            bounce = directions[s - 1]
            if bounce == "↘":
                offset += 1
            y_ball = y0 + (s - 0.5) * dy
            x_ball = cx + (offset - s / 2) * dx
            path_coords.append((x_ball, y_ball))
            
        if len(path_coords) > 1:
            draw.line(path_coords, fill=(246, 196, 69, 150), width=2)
            for px, py in path_coords[1:-1]:
                draw.ellipse([px - 3, py - 3, px + 3, py + 3], fill=(246, 196, 69, 255))
                
        bx, by = path_coords[-1]
        draw.ellipse([bx - 7, by - 7, bx + 7, by + 7], fill=(239, 68, 68, 100))
        draw.ellipse([bx - 5, by - 5, bx + 5, by + 5], fill=(239, 68, 68, 255))
        draw.ellipse([bx - 2, by - 4, bx, by - 2], fill=(255, 255, 255, 200))
        
        frames.append(img)
        
    out = BytesIO()
    durations = [400] * N + [6000]
    frames[0].save(
        out,
        format="GIF",
        save_all=True,
        append_images=frames[1:],
        duration=durations,
        loop=0
    )
    out.seek(0)
    
    # Close resources
    for frame in frames:
        frame.close()
        
    return out

if __name__ == "__main__":
    risk = "medium"
    layout = BIN_LAYOUTS[risk]
    multiplier = 2.0
    matching = [i for i, v in enumerate(layout) if abs(v - multiplier) < 0.01]
    target_index = random.choice(matching)
    
    N = len(layout) - 1
    k = target_index
    choices = [1] * k + [-1] * (N - k)
    random.shuffle(choices)
    directions = ["↘" if c == 1 else "↙" for c in choices]
    
    gif_buf = render_plinko_gif(
        risk=risk,
        multiplier=multiplier,
        target_index=target_index,
        directions=directions
    )
    
    with open("scratch/plinko_test.gif", "wb") as f:
        f.write(gif_buf.read())
    print("Success: saved scratch/plinko_test.gif")
