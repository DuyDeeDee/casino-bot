import os
import sys
import shutil
import asyncio

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

from app.discord_bot.modules.profile_renderer import render_profile_banner

async def test_rendering():
    print("Setting up profile GIF rendering test...")
    
    from pathlib import Path
    
    # 2. Path to Anak banner
    gif_path = Path("pictures/banners/anak.gif")
    
    # Dummy values
    username = "nguoidungnhurua"
    avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
    money = 355800000
    gold = 569
    gold_price = 1000000
    loan_amount = 0
    biz_count = 3
    inv_count = 4
    
    print("\nRendering animated profile with aesthetic-banner.gif background...")
    try:
        gif_buffer = await render_profile_banner(
            username=username,
            avatar_url=avatar_url,
            money=money,
            gold=gold,
            gold_price=gold_price,
            loan_amount=loan_amount,
            biz_count=biz_count,
            inv_count=inv_count,
            banner_path=gif_path
        )
        is_gif = getattr(gif_buffer, "is_gif", False)
        print(f"  Success! Buffer is_gif: {is_gif}")
        
        output_gif = r"C:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\data\test_profile_slots.gif"
        with open(output_gif, "wb") as f:
            f.write(gif_buffer.read())
        print(f"  Saved test GIF to {output_gif}")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()
 
    print("\nRendering fallback gradient profile banner...")
    try:
        png_buffer = await render_profile_banner(
            username=username,
            avatar_url=avatar_url,
            money=money,
            gold=gold,
            gold_price=gold_price,
            loan_amount=loan_amount,
            biz_count=biz_count,
            inv_count=inv_count,
            banner_path=None # fallback
        )
        is_gif = getattr(png_buffer, "is_gif", False)
        print(f"  Success! Buffer is_gif: {is_gif}")
        
        output_png = r"C:\Users\Admin\Downloads\casino-bot-main\casino-bot-main\data\test_profile_fallback.png"
        with open(output_png, "wb") as f:
            f.write(png_buffer.read())
        print(f"  Saved test PNG to {output_png}")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_rendering())
