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
    username: str,
    avatar_img: Image.Image | None,
    bet_amount: int,
    risk: str,
    multiplier: float,
    payout: int,
    profit: int,
    newly_unlocked: list[str] | None,
    timestamp_str: str,
    target_index: int,
    directions: list[str],
) -> BytesIO:
    # 1. Determine size
    width = 460
    height = 680 if newly_unlocked else 600
    
    # 2. Get configuration
    N = len(directions) # 6, 8, or 10
    
    frames = []
    
    for f in range(N + 1):
        img = Image.new("RGBA", (width, height), (15, 19, 34, 255)) # Dark navy background #0f1322
        draw = ImageDraw.Draw(img)
        
        # Draw vertical yellow stripe on the left edge
        draw.line([(2, 0), (2, height)], fill=(246, 196, 69, 255), width=4)
        
        # Load fonts
        font_title = load_font("bold", 18)
        font_subtitle = load_font("regular", 11)
        font_text = load_font("regular", 13)
        font_bold = load_font("bold", 13)
        font_small = load_font("regular", 10)
        
        # --- HEADER ---
        # Yellow icon box
        draw.rounded_rectangle([24, 20, 64, 60], radius=8, fill=(246, 196, 69, 255))
        # Draw a diamond indicator
        draw.polygon([(44, 28), (54, 38), (44, 48), (34, 38)], fill=(255, 255, 255, 255))
        
        # Title text
        draw.text((76, 22), "PLINKO", font=font_title, fill=(246, 196, 69, 255))
        draw.text((76, 44), "Casino · Trò chơi ngẫu nhiên", font=font_subtitle, fill=(143, 148, 168, 255))
        
        # Risk Badge
        risk_colors = {
            "low": (16, 185, 129), # green
            "medium": (246, 196, 69), # yellow
            "high": (239, 68, 68) # red
        }
        r_color = risk_colors.get(risk, (246, 196, 69))
        draw.rounded_rectangle([350, 24, 436, 52], radius=6, outline=r_color, width=2)
        
        risk_text = risk.upper()
        try:
            tw = font_bold.getlength(risk_text)
        except AttributeError:
            tw = len(risk_text) * 8
        draw.text((393 - tw/2, 31), risk_text, font=font_bold, fill=r_color)
        
        # --- PLAYER ROW ---
        # Avatar placeholder
        ax, ay = 24, 88
        avatar_size = 36
        draw.ellipse([ax, ay, ax + avatar_size, ay + avatar_size], fill=(59, 130, 246, 255))
        initial = username[0].upper() if username else "U"
        draw.text((ax + 12, ay + 8), initial, font=font_bold, fill=(255, 255, 255, 255))
            
        # Mention / Name
        draw.text((72, 88), "NGƯỜI CHƠI", font=font_small, fill=(143, 148, 168, 255))
        draw.text((72, 104), f"@{username}", font=font_bold, fill=(255, 255, 255, 255))
        
        # Bet amount
        bet_txt = f"{bet_amount:,} VNĐ"
        try:
            bw = font_bold.getlength(bet_txt)
        except AttributeError:
            bw = len(bet_txt) * 8
        draw.text((436 - bw, 96), bet_txt, font=font_bold, fill=(52, 211, 153, 255))
        
        # --- BOARD PANEL ---
        # Panel bg
        draw.rounded_rectangle([24, 140, 436, 410], radius=12, fill=(22, 26, 46, 255))
        draw.text((230 - 45, 152), "ĐƯỜNG BÓNG RƠI", font=font_small, fill=(143, 148, 168, 255))
        
        cx = 230
        y0 = 180
        
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
        
        # --- DETAILS PANEL ---
        draw.rounded_rectangle([24, 425, 436, 545], radius=12, fill=(22, 26, 46, 255))
        
        draw.text((40, 440), "🎯 Nhận hệ số", font=font_text, fill=(143, 148, 168, 255))
        mult_str = f"{multiplier:.1f}x" if multiplier % 1 != 0 else f"{int(multiplier)}x"
        draw.rounded_rectangle([360, 436, 420, 458], radius=6, fill=(16, 185, 129, 255) if multiplier >= 1.0 else (239, 68, 68, 255))
        try:
            mw = font_bold.getlength(mult_str)
        except AttributeError:
            mw = len(mult_str) * 8
        draw.text((390 - mw/2, 440), mult_str, font=font_bold, fill=(255, 255, 255, 255))
        
        draw.text((40, 475), "💰 Nhận về", font=font_text, fill=(143, 148, 168, 255))
        payout_str = f"{payout:,} VNĐ"
        try:
            pw = font_bold.getlength(payout_str)
        except AttributeError:
            pw = len(payout_str) * 8
        draw.text((420 - pw, 475), payout_str, font=font_bold, fill=(255, 255, 255, 255))
        
        draw.text((40, 510), "📈 Lợi nhuận", font=font_text, fill=(143, 148, 168, 255))
        profit_sign = "+" if profit > 0 else "-" if profit < 0 else "±"
        profit_color = (52, 211, 153, 255) if profit > 0 else (239, 68, 68, 255) if profit < 0 else (143, 148, 168, 255)
        profit_str = f"{profit_sign}{abs(profit):,} VNĐ" if profit != 0 else "±0 VNĐ"
        try:
            prw = font_bold.getlength(profit_str)
        except AttributeError:
            prw = len(profit_str) * 8
        draw.text((420 - prw, 510), profit_str, font=font_bold, fill=profit_color)
        
        # --- ACHIEVEMENT PANEL ---
        if newly_unlocked:
            draw.rounded_rectangle([24, 555, 436, 620], radius=12, fill=(27, 34, 60, 255))
            draw.text((40, 565), "🏆  ✦ THÀNH TỰU MỚI", font=font_bold, fill=(246, 196, 69, 255))
            ach_text = ", ".join(newly_unlocked)
            draw.text((40, 588), ach_text, font=font_text, fill=(255, 255, 255, 255))
            
        # --- FOOTER ---
        footer_y = height - 25
        draw.text((24, footer_y), timestamp_str, font=font_small, fill=(143, 148, 168, 255))
        draw.ellipse([346, footer_y + 3, 352, footer_y + 9], fill=(16, 185, 129, 255))
        draw.text((360, footer_y), "Sylus Meow", font=font_small, fill=(143, 148, 168, 255))
        
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
        username="nho ems",
        avatar_img=None,
        bet_amount=100000,
        risk=risk,
        multiplier=multiplier,
        payout=100000,
        profit=0,
        newly_unlocked=["Thả bóng đầu tiên"],
        timestamp_str=datetime.now().strftime("%d/%m/%Y · %H:%M:%S"),
        target_index=target_index,
        directions=directions
    )
    
    with open("scratch/plinko_test.gif", "wb") as f:
        f.write(gif_buf.read())
    print("Success: saved scratch/plinko_test.gif")
