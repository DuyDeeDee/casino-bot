import os
import sys
import unittest
import time
from unittest.mock import AsyncMock, MagicMock

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.marry import Marry
from discord.ext import commands
import discord

class TestMultiMarry(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        # Initialize Economy and Bot mock
        self.economy = Economy()
        self.bot = MagicMock()
        self.bot.economy = self.economy
        self.bot.owner_ids = {999999901}

        self.bot.is_owner = AsyncMock(side_effect=lambda u: u.id in self.bot.owner_ids)
        self.cog = Marry(self.bot)
        
        # Test IDs
        self.admin_id = 999999901
        self.user1_id = 999999902
        self.user2_id = 999999903
        self.user3_id = 999999904
        self.user4_id = 999999905
        self.user5_id = 999999906
        self.user6_id = 999999907
        
        # Clean existing test entries from SQLite
        self.economy.cur.execute("DELETE FROM user_marry WHERE user_one = ? OR user_two = ?", (self.admin_id, self.admin_id))
        self.economy.cur.execute("DELETE FROM user_marry WHERE user_one = ? OR user_two = ?", (self.user1_id, self.user1_id))
        self.economy.cur.execute("DELETE FROM user_marry WHERE user_one = ? OR user_two = ?", (self.user2_id, self.user2_id))
        self.economy.conn.commit()

    async def asyncTearDown(self):
        # Clean up
        self.economy.cur.execute("DELETE FROM user_marry WHERE user_one = ? OR user_two = ?", (self.admin_id, self.admin_id))
        self.economy.cur.execute("DELETE FROM user_marry WHERE user_one = ? OR user_two = ?", (self.user1_id, self.user1_id))
        self.economy.cur.execute("DELETE FROM user_marry WHERE user_one = ? OR user_two = ?", (self.user2_id, self.user2_id))
        self.economy.conn.commit()
        self.economy.close()

    async def test_admin_is_recognized(self):
        admin_user = MagicMock()
        admin_user.id = self.admin_id
        is_admin = await self.cog.is_admin_user(admin_user)
        self.assertTrue(is_admin)

        regular_user = MagicMock()
        regular_user.id = self.user1_id
        is_admin_reg = await self.cog.is_admin_user(regular_user)
        self.assertFalse(is_admin_reg)

    async def test_admin_multiple_marriages_limit(self):
        # Admin can marry up to 5 people
        # Regular user can marry up to 1 person
        
        # Let's create marriages
        self.economy.create_marriage(self.admin_id, self.user1_id, "ring_grass")
        self.economy.create_marriage(self.admin_id, self.user2_id, "ring_quartz")
        self.economy.create_marriage(self.admin_id, self.user3_id, "ring_emerald")
        self.economy.create_marriage(self.admin_id, self.user4_id, "ring_amethyst")
        self.economy.create_marriage(self.admin_id, self.user5_id, "ring_sapphire")
        
        marriages = self.economy.get_marriages(self.admin_id)
        self.assertEqual(len(marriages), 5)
        
        # Regular user 1 is married to admin, so they have 1 marriage
        reg_marriages = self.economy.get_marriages(self.user1_id)
        self.assertEqual(len(reg_marriages), 1)

    async def test_get_marriage_multiplier_max(self):
        # If admin is married with multiple ring buffs, it should return the maximum multiplier
        # ring_grass: 1.0
        # ring_divine: 1.40
        self.economy.create_marriage(self.admin_id, self.user1_id, "ring_grass")
        self.economy.create_marriage(self.admin_id, self.user2_id, "ring_divine")
        
        mult = self.economy.get_marriage_multiplier(self.admin_id)
        self.assertEqual(mult, 1.40)

    async def test_update_specific_marriage_properties(self):
        # Create marriages
        self.economy.create_marriage(self.admin_id, self.user1_id, "ring_grass")
        self.economy.create_marriage(self.admin_id, self.user2_id, "ring_divine")
        
        # Update marriage 1 status to "Thương nhau"
        self.economy.update_marriage_status(self.admin_id, self.user1_id, "Thương nhau")
        # Update marriage 2 status to "Vợ chồng son"
        self.economy.update_marriage_status(self.admin_id, self.user2_id, "Vợ chồng son")
        
        # Verify specific entries
        status1 = self.economy.get_marriage_status(self.admin_id, self.user1_id)
        status2 = self.economy.get_marriage_status(self.admin_id, self.user2_id)
        
        self.assertEqual(status1, "Thương nhau")
        self.assertEqual(status2, "Vợ chồng son")

    async def test_resolve_marriage_and_args(self):
        # Create marriages
        self.economy.create_marriage(self.admin_id, self.user1_id, "ring_grass") # Index 1
        self.economy.create_marriage(self.admin_id, self.user2_id, "ring_divine") # Index 2
        
        # Resolve index 2
        m, args = self.cog._resolve_marriage_and_args(self.admin_id, ["2", "hello"])
        self.assertIsNotNone(m)
        self.assertEqual(m[1], self.user2_id)
        self.assertEqual(args, ["hello"])
        
        # Resolve default (no index)
        m, args = self.cog._resolve_marriage_and_args(self.admin_id, ["hello"])
        self.assertIsNotNone(m)
        self.assertEqual(m[1], self.user1_id)
        self.assertEqual(args, ["hello"])

if __name__ == "__main__":
    unittest.main()
