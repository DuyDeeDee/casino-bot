import sys
import os
from PIL import Image, ImageDraw, ImageFont

# Add root folder to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

def test_render():
    print("Testing emoji rendering...")
    # Create a test image
    img = Image.new("RGBA", (400, 100), (30, 30, 35, 255))
    draw = ImageDraw.Draw(img)
    
    # Try loading Segoe UI Emoji font
    font_path = "C:/Windows/Fonts/seguiemj.ttf"
    try:
        font = ImageFont.truetype(font_path, 32)
        print("Loaded Segoe UI Emoji font!")
    except Exception as e:
        print(f"Failed to load Segoe UI Emoji: {e}")
        font = ImageFont.load_default()
        
    # Draw emojis
    try:
        draw.text((50, 30), "🐎 🦄 🐴 ⚡ 🐢", font=font, embedded_color=True)
        print("Successfully called draw.text with color emojis!")
    except Exception as e:
        print(f"Error drawing emojis: {e}")
        
    img.save("scratch/test_emoji_out.png")
    print("Saved output to scratch/test_emoji_out.png")

if __name__ == "__main__":
    test_render()
