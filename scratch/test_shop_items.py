import sys
import os
import asyncio
from pathlib import Path
import shutil

# Setup path
sys.path.append(os.getcwd())

# Monkeypatch DB path
import app.discord_bot.modules.economy as eco
eco.DATABASE_PATH = Path("data/economy_test.db")

# Copy DB for testing
if Path("data/economy.db").exists():
    shutil.copy2("data/economy.db", "data/economy_test.db")

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.daga import Daga, Cock, FOOD_DETAILS
import discord

class DummyBot:
    def __init__(self):
        self.economy = Economy()
        self.command_prefix = "i?"

class DummyUser:
    def __init__(self, id, name):
        self.id = id
        self.display_name = name
        self.mention = f"<@{id}>"
        self.display_avatar = self

    @property
    def url(self):
        return "http://dummy.url"

class DummyContext:
    def __init__(self, author, prefix="i?"):
        self.author = author
        self.prefix = prefix
        self.sent_messages = []

    async def send(self, content=None, *args, **kwargs):
        msg = f"SEND: {content or ''}"
        if 'embed' in kwargs:
            embed = kwargs['embed']
            msg += f" EMBED[title={embed.title}, desc={embed.description}]"
        self.sent_messages.append(msg)
        print(msg)
        # return a dummy message object that can be edited
        class DummyMessage:
            async def edit(self, *args, **kwargs):
                print(f"EDIT MESSAGE: {kwargs}")
        return DummyMessage()

async def run_tests():
    bot = DummyBot()
    cog = Daga(bot)
    user = DummyUser(999999, "TestUser")
    ctx = DummyContext(user)

    # 1. Reset user balance
    bot.economy.set_money(user.id, 200_000_000)
    print(f"Set balance to {bot.economy.get_entry(user.id)[1]:,} VND")

    # 2. Buy items 11 to 15
    print("\n--- Testing Buy Items ---")
    for item_id in ["11", "12", "13", "14", "15"]:
        await cog.buy_food.callback(cog, ctx, item_id, 2)
    
    # Check inventory
    inventory = bot.economy.get_inventory(user.id)
    print("Inventory after purchase:", inventory)

    # 3. Add a test character (e.g. Gojo Satoru)
    print("\n--- Testing Add Character ---")
    # Add character Gojo Satoru
    bot.economy.cur.execute("DELETE FROM user_cocks WHERE user_id=?", (user.id,))
    bot.economy.conn.commit()
    
    # Let's add Gojo
    hp, atk, df, spd, luk = 200, 40, 35, 35, 30
    cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = bot.economy.add_cock(
        user.id, "Gojo Satoru", "Huyền Thoại", hp, atk, df, spd, luk
    )
    # Set as active character
    bot.economy.set_active_cock(user.id, cock_id)
    print(f"Added Gojo Satoru (ID: {cock_id}) and set active.")

    # Get active cock details
    row = bot.economy.get_active_cock(user.id)
    c = Cock(row)
    print(f"Initial Gojo: HP={c.hp}, ATK={c.atk}, DEF={c.df}, SPD={c.spd}, Stars={c.stars}")

    # 4. Use (feed) items 11 to 14
    print("\n--- Testing Use ATK Stone ---")
    await cog.daga_feed.callback(cog, ctx, "11", 1) # ATK Stone
    row = bot.economy.get_active_cock(user.id)
    c = Cock(row)
    print(f"After +1 ATK Stone: ATK={c.atk} (expected: 45)")

    print("\n--- Testing Use DEF Stone ---")
    await cog.daga_feed.callback(cog, ctx, "12", 1) # DEF Stone
    row = bot.economy.get_active_cock(user.id)
    c = Cock(row)
    print(f"After +1 DEF Stone: DEF={c.df} (expected: 40)")

    print("\n--- Testing Use SPD Stone ---")
    await cog.daga_feed.callback(cog, ctx, "13", 1) # SPD Stone
    row = bot.economy.get_active_cock(user.id)
    c = Cock(row)
    print(f"After +1 SPD Stone: SPD={c.spd} (expected: 38)")

    print("\n--- Testing Use Breakthrough Stone ---")
    await cog.daga_feed.callback(cog, ctx, "14", 1) # Breakthrough Stone
    row = bot.economy.get_active_cock(user.id)
    c = Cock(row)
    print(f"After +1 Breakthrough Stone: Stars={c.stars} (expected: 1), HP={c.hp}, ATK={c.atk}, DEF={c.df}")

    # 5. Try using character shard (15) -> should fail
    print("\n--- Testing Use Character Shard (Should Fail) ---")
    await cog.daga_feed.callback(cog, ctx, "15", 1)

    # 6. Test Craft Command
    print("\n--- Testing Craft Character (Not enough shards) ---")
    # We bought 2 shards. Need 10.
    await cog.daga_craft.callback(cog, ctx, character_name="gojo")

    print("\n--- Testing Craft Character (Enough shards) ---")
    # Grant 8 more shards to reach 10
    bot.economy.add_inventory_item(user.id, "item_character_shard", 8)
    inventory = bot.economy.get_inventory(user.id)
    print("Inventory before craft:", inventory)
    await cog.daga_craft.callback(cog, ctx, character_name="gojo")
    
    # Check inventory and characters
    inventory = bot.economy.get_inventory(user.id)
    print("Inventory after craft:", inventory)
    cocks = bot.economy.get_cocks(user.id)
    print(f"Characters owned now: {len(cocks)}")
    for ck in cocks:
        print(f" - ID: {ck[0]}, Name: {ck[2]}, Rarity: {ck[3]}, Shards: {ck[20] if len(ck) > 20 else 0}")

    # Clean up test DB
    bot.economy.conn.close()
    if eco.DATABASE_PATH.exists():
        os.remove(eco.DATABASE_PATH)
    print("\nAll tests completed!")

if __name__ == "__main__":
    asyncio.run(run_tests())
