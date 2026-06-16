import os
from PIL import Image, ImageDraw, ImageFont

def format_money_shorthand(amount: int) -> str:
    if amount == 0:
        return "0"
    if amount >= 1_000_000:
        val = amount / 1_000_000
        if val == int(val):
            return f"{int(val)}M"
        return f"{val:.1f}M"
    if amount >= 1_000:
        val = amount / 1_000
        if val == int(val):
            return f"{int(val)}K"
        return f"{val:.1f}K"
    return f"{amount}"

def draw_bet_box(draw: ImageDraw.Draw, x: int, y: int, amount: int, font: ImageFont.FreeTypeFont):
    # Box dimensions
    w, h = 120, 34
    x1, y1 = x - w // 2, y - h // 2
    x2, y2 = x + w // 2, y + h // 2
    
    # Draw dark background box
    draw.rounded_rectangle(
        [(x1, y1), (x2, y2)],
        radius=6,
        fill="#0d0e15",
        outline="#ffcc00",
        width=2
    )
    
    # Draw shorthand text inside the box
    text = format_money_shorthand(amount)
    draw.text((x, y), text, fill="#ffcc00", font=font, anchor="mm")

def main():
    img_path = "pictures/baucua_bg.png"
    if not os.path.exists(img_path):
        print("Error: pictures/baucua_bg.png not found")
        return
        
    img = Image.open(img_path).convert("RGBA")
    draw = ImageDraw.Draw(img)
    
    # Load fonts
    font_large = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 60)
    font_medium = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 32)
    font_small = ImageFont.truetype("data/fonts/Roboto-Bold.ttf", 18)
    
    # Coordinates of cards:
    # X centers: 256, 512, 768
    # Top Row box Y center: 290
    # Bottom Row box Y center: 580
    
    draw_bet_box(draw, 256, 290, 10000, font_small)
    draw_bet_box(draw, 512, 290, 0, font_small)
    draw_bet_box(draw, 768, 290, 50000, font_small)
    
    draw_bet_box(draw, 256, 580, 0, font_small)
    draw_bet_box(draw, 512, 580, 2500000, font_small)
    draw_bet_box(draw, 768, 580, 0, font_small)
    
    # Center Display Box (centered at x=512, y=150)
    box_w, box_h = 320, 54
    bx1, by1 = 512 - box_w // 2, 150 - box_h // 2
    bx2, by2 = 512 + box_w // 2, 150 + box_h // 2
    
    # Draw dark display box
    draw.rounded_rectangle(
        [(bx1, by1), (bx2, by2)],
        radius=8,
        fill="#0d0e15",
        outline="#ffcc00",
        width=2
    )
    
    # Draw result text inside the box
    draw.text((512, 150), "BẦU • BẦU • CÁ", fill="#ffd700", font=font_medium, anchor="mm")
    
    # Save the draft
    img.save("pictures/baucua_draft.png")
    print("Saved pictures/baucua_draft.png")

if __name__ == "__main__":
    main()
