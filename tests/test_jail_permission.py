import asyncio
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import discord
from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.jail import Jail, has_jail_permission


class TestJailPermission(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_jail.db"

        import app.discord_bot.modules.economy as eco_mod
        self.orig_db_path = eco_mod.DATABASE_PATH
        eco_mod.DATABASE_PATH = self.db_path

        self.economy = Economy()

        # Configure bot owners and admins
        self.orig_owners = getattr(config.bot, "owner_ids", [])
        self.orig_admins = getattr(config.bot, "admin_ids", [])
        config.bot.owner_ids = [9999]
        config.bot.admin_ids = [8888]

        self.bot = MagicMock()
        self.bot.economy = self.economy
        self.bot.is_owner = AsyncMock(return_value=False)
        self.bot.add_check = MagicMock()
        self.bot.remove_check = MagicMock()

        self.cog = Jail(self.bot)

    async def asyncTearDown(self):
        self.economy.close()
        import app.discord_bot.modules.economy as eco_mod
        eco_mod.DATABASE_PATH = self.orig_db_path
        config.bot.owner_ids = self.orig_owners
        config.bot.admin_ids = self.orig_admins
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def _create_mock_context(self, author_id: int, guild_id: int = 12345):
        ctx = MagicMock()
        ctx.guild = MagicMock()
        ctx.guild.id = guild_id
        ctx.guild.owner_id = 7777
        ctx.guild.roles = []
        ctx.guild.get_role = MagicMock(return_value=None)
        ctx.guild.get_channel = MagicMock(return_value=None)
        ctx.author = MagicMock(spec=discord.Member)
        ctx.author.id = author_id
        ctx.author.bot = False
        ctx.reply = AsyncMock()
        ctx.send = AsyncMock()
        ctx.channel = MagicMock()
        return ctx


    def _create_mock_member(self, member_id: int, is_bot: bool = False):
        m = MagicMock(spec=discord.Member)
        m.id = member_id
        m.bot = is_bot
        m.name = f"User_{member_id}"
        m.mention = f"<@{member_id}>"
        m.roles = []
        return m

    async def test_phattu_rejected_for_normal_user(self):
        """Normal user cannot use phattu."""
        ctx = self._create_mock_context(author_id=1111)  # Neither owner nor admin
        target = self._create_mock_member(2222)

        await self.cog.phattu.callback(self.cog, ctx, target, count=50, reason="test")

        # Must send denial emoji
        ctx.reply.assert_called_once()
        self.assertIn("1545378962992009217", ctx.reply.call_args[0][0])
        # Must not be added to jail
        self.assertFalse(self.economy.is_in_jail(2222, ctx.guild.id))

    async def test_phattu_rejected_for_server_admin_who_is_not_bot_admin(self):
        """Server administrator who is not bot admin cannot use phattu."""
        ctx = self._create_mock_context(author_id=7777)  # Guild owner / server admin
        target = self._create_mock_member(2222)

        await self.cog.phattu.callback(self.cog, ctx, target, count=50, reason="test")

        # Must send denial emoji
        ctx.reply.assert_called_once()
        self.assertIn("1545378962992009217", ctx.reply.call_args[0][0])
        # Must not be added to jail
        self.assertFalse(self.economy.is_in_jail(2222, ctx.guild.id))

    async def test_phattu_allowed_for_bot_admin(self):
        """Bot admin can use phattu on normal users."""
        ctx = self._create_mock_context(author_id=8888)  # in admin_ids
        target = self._create_mock_member(2222)

        await self.cog.phattu.callback(self.cog, ctx, target, count=50, reason="test")

        # Target should be in jail
        self.assertTrue(self.economy.is_in_jail(2222, ctx.guild.id))
        jail_info = self.economy.get_jail_info(2222, ctx.guild.id)
        self.assertEqual(jail_info["clean_count"], 50)

    async def test_phattu_allowed_for_bot_owner(self):
        """Bot owner can use phattu on normal users."""
        ctx = self._create_mock_context(author_id=9999)  # in owner_ids
        target = self._create_mock_member(3333)

        await self.cog.phattu.callback(self.cog, ctx, target, count=80, reason="test owner")

        self.assertTrue(self.economy.is_in_jail(3333, ctx.guild.id))
        jail_info = self.economy.get_jail_info(3333, ctx.guild.id)
        self.assertEqual(jail_info["clean_count"], 80)

    async def test_phattu_admin_cannot_jail_bot_owner(self):
        """Bot admin cannot jail bot owner."""
        ctx = self._create_mock_context(author_id=8888)  # Bot admin
        target = self._create_mock_member(9999)  # Bot owner

        await self.cog.phattu.callback(self.cog, ctx, target, count=50)

        # Denied
        ctx.reply.assert_called_once()
        self.assertIn("1545378962992009217", ctx.reply.call_args[0][0])
        self.assertFalse(self.economy.is_in_jail(9999, ctx.guild.id))

    async def test_phattu_admin_cannot_jail_other_admin(self):
        """Bot admin cannot jail another bot admin."""
        config.bot.admin_ids = [8888, 8889]
        ctx = self._create_mock_context(author_id=8888)  # Bot admin
        target = self._create_mock_member(8889)  # Another bot admin

        await self.cog.phattu.callback(self.cog, ctx, target, count=50)

        # Denied
        ctx.reply.assert_called_once()
        self.assertIn("1545378962992009217", ctx.reply.call_args[0][0])
        self.assertFalse(self.economy.is_in_jail(8889, ctx.guild.id))


    async def test_has_jail_permission_predicate(self):
        """has_jail_permission predicate only returns True for bot admin/owner."""
        check = has_jail_permission()
        predicate = check.predicate

        # Normal user with server administrator perms
        ctx_normal = self._create_mock_context(author_id=1111)
        ctx_normal.author.guild_permissions = discord.Permissions(administrator=True)
        ctx_normal.channel.permissions_for = MagicMock(return_value=discord.Permissions(administrator=True))
        self.assertFalse(await predicate(ctx_normal))

        # Bot admin
        ctx_admin = self._create_mock_context(author_id=8888)
        self.assertTrue(await predicate(ctx_admin))

        # Bot owner
        ctx_owner = self._create_mock_context(author_id=9999)
        self.assertTrue(await predicate(ctx_owner))


if __name__ == "__main__":
    unittest.main()
