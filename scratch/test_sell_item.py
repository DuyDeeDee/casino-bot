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

# Copy DB for testing if original exists
if Path("data/economy.db").exists():
    shutil.copy2("data/economy.db", "data/economy_test.db")

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.simulator import Simulator
import discord

class DummyBot:
    def __init__(self):
        self.economy = Economy()
        self.command_prefix = "i?"

class DummyUser:
    def __init__(self, id, name):
        self.id = id
        self.name = name
        self.display_name = name
        self.mention = f"<@{id}>"
        self.display_avatar = self

    @property
    def url(self):
        return "http://dummy.url"

class DummyCommand:
    def __init__(self, name):
        self.qualified_name = name

class DummyContext:
    def __init__(self, author, prefix="i?"):
        self.author = author
        self.prefix = prefix
        self.command = DummyCommand("sellitem")
        self.guild = None
        self.channel = None
        self.sent_messages = []

    async def send(self, content=None, *args, **kwargs):
        msg = f"SEND: {content or ''}"
        if 'embed' in kwargs:
            embed = kwargs['embed']
            msg += f" EMBED[title={embed.title}, desc={embed.description}]"
        self.sent_messages.append(msg)
        try:
            print(msg)
        except UnicodeEncodeError:
            print(msg.encode('utf-8', errors='ignore').decode('ascii', errors='ignore'))
        return None

async def run_tests():
    bot = DummyBot()
    cog = Simulator(bot)
    user = DummyUser(888888, "TestUser")
    ctx = DummyContext(user)

    # 1. Reset user balances and inventory
    bot.economy.set_money(user.id, 100_000_000)
    bot.economy.set_credits(user.id, 500)
    # Clear user inventory for user.id
    bot.economy.cur.execute("DELETE FROM user_inventory WHERE user_id=?", (user.id,))
    bot.economy.conn.commit()
    
    print(f"Initial Balance: {bot.economy.get_entry(user.id)[1]:,} VND, {bot.economy.get_entry(user.id)[2]} Gold")

    # 2. Buy a degree (VND)
    print("\n--- Test 1: Buying and Selling 'bang_cap' (10M VND, should refund 7.5M VND) ---")
    bot.economy.add_inventory_item(user.id, "bang_cap", 1)
    # Deduct cost to simulate buy
    bot.economy.add_money(user.id, -10_000_000)
    print(f"Balance after purchase: {bot.economy.get_entry(user.id)[1]:,} VND")
    
    # Sell it
    await cog.sellitem.callback(cog, ctx, "bang_cap", 1)
    
    # Check balance and inventory
    entry = bot.economy.get_entry(user.id)
    inv = bot.economy.get_inventory(user.id)
    print(f"Final Balance: {entry[1]:,} VND. Inventory: {inv}")
    assert entry[1] == 97_500_000, "Refunding 7.5M VND failed"
    assert next((qty for iid, qty in inv if iid == "bang_cap"), 0) == 0, "Item deduction failed"

    # 3. Buy a degree (Gold)
    print("\n--- Test 2: Buying and Selling 'the_tho_san' (300 Gold, should refund 225 Gold) ---")
    bot.economy.add_inventory_item(user.id, "the_tho_san", 1)
    bot.economy.add_credits(user.id, -300)
    print(f"Gold after purchase: {bot.economy.get_entry(user.id)[2]} Gold")
    
    # Sell it
    await cog.sellitem.callback(cog, ctx, "the_tho_san", 1)
    
    # Check balance and inventory
    entry = bot.economy.get_entry(user.id)
    inv = bot.economy.get_inventory(user.id)
    print(f"Final Gold: {entry[2]} Gold. Inventory: {inv}")
    assert entry[2] == 425, "Refunding 225 Gold failed"
    assert next((qty for iid, qty in inv if iid == "the_tho_san"), 0) == 0, "Item deduction failed"

    # 4. Sell a treasure (VND)
    print("\n--- Test 3: Selling Treasure 't_lop_xe' ---")
    bot.economy.add_inventory_item(user.id, "t_lop_xe", 2)
    # Sell 2 items
    await cog.sellitem.callback(cog, ctx, "t_lop_xe", 2)
    entry = bot.economy.get_entry(user.id)
    inv = bot.economy.get_inventory(user.id)
    print(f"Final Balance: {entry[1]:,} VND. Inventory: {inv}")
    # 97.5M + (50k * 2) = 97.6M VND
    assert entry[1] == 97_600_000, "Refunding treasure failed"

    # 5. Sell a banner (Should fail)
    print("\n--- Test 4: Selling a Banner (Should Fail) ---")
    bot.economy.add_inventory_item(user.id, "banner_hr", 1)
    await cog.sellitem.callback(cog, ctx, "banner_hr", 1)
    inv = bot.economy.get_inventory(user.id)
    assert next((qty for iid, qty in inv if iid == "banner_hr"), 0) == 1, "Banner was sold but it shouldn't be"

    # 6. Sell an item not owned (Should fail)
    print("\n--- Test 5: Selling unowned degree (Should Fail) ---")
    await cog.sellitem.callback(cog, ctx, "bang_kien_truc", 1)

    # Clean up test DB
    bot.economy.conn.close()
    if eco.DATABASE_PATH.exists():
        os.remove(eco.DATABASE_PATH)
    print("\nAll tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
