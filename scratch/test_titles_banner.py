import os
import sys
import asyncio
from pathlib import Path
from io import BytesIO

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.profile_renderer import render_profile_banner

async def test_rendering_titles():
    print("Testing rendering titles on profile banner...")
    
    username = "nguoidungnhurua"
    avatar_url = "https://cdn.discordapp.com/embed/avatars/0.png"
    
    # VIP levels and Titles
    # Roulette: 🎰 Tân Binh Roulette
    # Daga: Huyền Thoại 👑
    # Wealth: Tỷ Phú Đô La
    money = 899218004
    gold = 7500
    gold_price = 9690000
    loan_amount = 500000000 # 500M VND to trigger loan badge wrap test
    biz_count = 3
    inv_count = 27
    
    rl_title = "🎰 Tân Binh Roulette"
    daga_title = "Huyền Thoại 👑"
    
    print("\nRendering profile banner with titles...")
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
            banner_path=None,
            rl_title=rl_title,
            daga_title=daga_title
        )
        output_png = Path("data") / "test_profile_titles_loan.png"
        output_png.parent.mkdir(parents=True, exist_ok=True)
        with open(output_png, "wb") as f:
            f.write(png_buffer.read())
        print(f"  Success! Saved test PNG to {output_png.resolve()}")
    except Exception as e:
        print(f"  FAILED: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_rendering_titles())
