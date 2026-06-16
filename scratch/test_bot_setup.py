import os
import sys
import asyncio

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.bot import client, register_cogs

async def test_bot_setup():
    print("Testing registration of all Cogs in CasinoBot...")
    try:
        await register_cogs(client)
        print("Success! Cogs registered successfully:")
        for name, cog in client.cogs.items():
            print(f"  - {name}")
    except Exception as e:
        print(f"FAILED: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(test_bot_setup())
