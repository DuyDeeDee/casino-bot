import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock
import discord
from discord.ext import commands

from app.discord_bot.cogs.voice_afk import VoiceAfk


class TestVoiceAfk(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.bot = MagicMock(spec=commands.Bot)
        self.bot.user = MagicMock()
        self.bot.user.id = 999999
        self.bot.latency = 0.05
        
        # Mock economy
        self.bot.economy = MagicMock()
        self.storage = {}
        self.bot.economy.get_setting.side_effect = lambda k, d="": self.storage.get(k, d)
        self.bot.economy.set_setting.side_effect = lambda k, v: self.storage.update({k: v})

        self.cog = VoiceAfk(self.bot)

    async def asyncTearDown(self):
        self.cog.cog_unload()

    def test_targets_storage(self):
        guild_id = 123456
        channel_id = 789012
        
        self.cog.set_target(guild_id, channel_id)
        self.assertEqual(self.cog.targets.get(guild_id), channel_id)
        
        # Verify persistence
        reloaded = VoiceAfk(self.bot)
        self.assertEqual(reloaded.targets.get(guild_id), channel_id)
        
        # Clear target
        self.cog.clear_target(guild_id)
        self.assertNotIn(guild_id, self.cog.targets)

    async def test_join_cmd_no_channel(self):
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = MagicMock()
        ctx.author.voice = None
        ctx.send = AsyncMock()

        await self.cog._execute_join(ctx, channel=None)
        ctx.send.assert_called_once()
        self.assertIn("Bạn cần vào một voice channel", ctx.send.call_args[0][0])

    async def test_join_cmd_success(self):
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = MagicMock()
        ctx.guild.id = 1111
        ctx.guild.voice_client = None
        
        voice_chan = MagicMock(spec=discord.VoiceChannel)
        voice_chan.id = 2222
        voice_chan.name = "General Voice"
        perms = MagicMock()
        perms.connect = True
        perms.speak = True
        voice_chan.permissions_for.return_value = perms
        voice_chan.connect = AsyncMock()

        ctx.author.voice = MagicMock()
        ctx.author.voice.channel = voice_chan
        ctx.send = AsyncMock()

        await self.cog._execute_join(ctx)
        voice_chan.connect.assert_called_once()
        self.assertEqual(self.cog.targets.get(1111), 2222)
        ctx.send.assert_called_once()
        self.assertIn("General Voice", ctx.send.call_args[0][0])

    async def test_leave_cmd(self):
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = MagicMock()
        ctx.guild.id = 1111
        self.cog.set_target(1111, 2222)

        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.disconnect = AsyncMock()
        ctx.guild.voice_client = vc
        ctx.send = AsyncMock()

        await self.cog._execute_leave(ctx)
        vc.disconnect.assert_called_once()
        self.assertNotIn(1111, self.cog.targets)
        ctx.send.assert_called_once()
        self.assertIn("Đã rời khỏi voice channel", ctx.send.call_args[0][0])

    async def test_ping_cmd(self):
        ctx = MagicMock(spec=commands.Context)
        ctx.guild = MagicMock()
        vc = MagicMock()
        vc.is_connected.return_value = True
        vc.channel.name = "General"
        vc.latency = 0.025
        ctx.guild.voice_client = vc
        ctx.send = AsyncMock()

        await self.cog._execute_ping(ctx)
        ctx.send.assert_called_once()
        self.assertIn("API", ctx.send.call_args[0][0])
        self.assertIn("Voice", ctx.send.call_args[0][0])

    async def test_on_voice_state_update_admin_kick(self):
        guild = MagicMock()
        guild.id = 1111
        guild.name = "Test Guild"
        self.cog.set_target(1111, 2222)

        bot_member = MagicMock()
        bot_member.id = self.bot.user.id
        bot_member.guild = guild

        before = MagicMock()
        before.channel = MagicMock()
        before.channel.id = 2222
        after = MagicMock()
        after.channel = None

        # Simulate audit log entry for kick
        audit_entry = MagicMock()
        audit_entry.target.id = self.bot.user.id
        audit_entry.user.id = 55555  # Admin
        audit_entry.created_at = discord.utils.utcnow()

        async def mock_audit_logs(*args, **kwargs):
            yield audit_entry

        guild.audit_logs = mock_audit_logs

        await self.cog.on_voice_state_update(bot_member, before, after)
        self.assertNotIn(1111, self.cog.targets)


if __name__ == "__main__":
    unittest.main()
