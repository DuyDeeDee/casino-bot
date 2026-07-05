import os
import sys
import unittest
import time
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.bot import CasinoBot
from discord.ext import commands
import discord

class TestBotCooldown(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Create a light client/bot instance or mock
        self.bot = CasinoBot()
        self.user_id = 999999909
        self.owner_id = 999999901
        
        # Mock owner check
        self.bot.is_owner = AsyncMock(side_effect=lambda user: user.id == self.owner_id)
        
        # Clean test setting from DB
        self.bot.economy.set_setting("global_cooldown", "")

    async def asyncTearDown(self):
        self.bot.economy.close()

    async def test_owner_bypass_cooldown(self):
        # Setup context
        ctx = MagicMock()
        ctx.author.id = self.owner_id
        ctx.message.author = ctx.author
        
        # Enable cooldown to 5.0 seconds in DB
        self.bot.economy.set_setting("global_cooldown", "5.0")
        
        # Owner should bypass successfully twice without raising errors
        res1 = await self.bot.global_cooldown_check(ctx)
        self.assertTrue(res1)
        
        res2 = await self.bot.global_cooldown_check(ctx)
        self.assertTrue(res2)

    async def test_user_rate_limiting(self):
        # Setup context for a normal user
        ctx = MagicMock()
        ctx.author.id = self.user_id
        ctx.message.author = ctx.author
        
        # Set cooldown to 2.0 seconds
        self.bot.economy.set_setting("global_cooldown", "2.0")
        self.bot.cooldown_tracker.clear()
        
        # First call succeeds
        res1 = await self.bot.global_cooldown_check(ctx)
        self.assertTrue(res1)
        
        # Second call immediately should raise CommandOnCooldown
        with self.assertRaises(commands.CommandOnCooldown) as cm:
            await self.bot.global_cooldown_check(ctx)
            
        self.assertGreater(cm.exception.retry_after, 0.0)
        self.assertLessEqual(cm.exception.retry_after, 2.0)

    async def test_disabled_cooldown(self):
        # Setup context for normal user
        ctx = MagicMock()
        ctx.author.id = self.user_id
        ctx.message.author = ctx.author
        
        # Disable cooldown (set to 0.0)
        self.bot.economy.set_setting("global_cooldown", "0.0")
        self.bot.cooldown_tracker.clear()
        
        # Multiple calls should succeed immediately
        res1 = await self.bot.global_cooldown_check(ctx)
        self.assertTrue(res1)
        res2 = await self.bot.global_cooldown_check(ctx)
        self.assertTrue(res2)

if __name__ == "__main__":
    unittest.main()
