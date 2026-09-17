import json
import sqlite3
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord

from app.discord_bot.cogs.giveaway import Giveaway, GiveawayEditorView, GiveawayPrizeBonusView
from app.discord_bot.modules.giveaway_bonus import BonusCatalog, BonusPages, CatalogEditor, CatalogBenefitModal, matching_benefits


class CatalogTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = sqlite3.connect(':memory:')
        self.bot = MagicMock()
        self.bot.economy.conn = self.conn
        self.bot.economy.cur = self.conn.cursor()
        self.bot.wait_until_ready = AsyncMock()
        self.cog = Giveaway(self.bot)
        self.store = self.cog.bonus_catalog
        self.roles = {10: SimpleNamespace(id=10, name='VIP Member'), 20: SimpleNamespace(id=20, name='Booster')}
        self.guild = MagicMock(spec=discord.Guild)
        self.guild.id = 100
        self.guild.name = 'Server A'
        self.guild.get_role.side_effect = self.roles.get
        self.admin = SimpleNamespace(id=123, guild=self.guild, guild_permissions=discord.Permissions(manage_guild=True))
        self.entries = {
            '10': dict(text='+50k khi thắng', enabled=True, order=1),
            '20': dict(text='+1 skin khi thắng', enabled=True, order=2),
        }

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.conn.close()

    def test_atomic_versioned_save_and_guild_isolation(self):
        self.assertEqual(self.store.save(self.guild, self.admin, 0, self.entries), 1)
        with self.assertRaisesRegex(ValueError, 'Admin khác'):
            self.store.save(self.guild, self.admin, 0, {})
        version, saved = self.store.load(100)
        self.assertEqual(version, 1)
        self.assertEqual(saved, self.entries)
        self.assertEqual(self.store.load(200), (0, {}))
        # Re-opening storage must preserve the catalog/version.
        self.assertEqual(BonusCatalog(self.conn).load(100), (1, self.entries))

    def test_permission_deleted_and_disabled_roles(self):
        normal = SimpleNamespace(id=456, guild=self.guild, guild_permissions=discord.Permissions.none())
        with self.assertRaises(ValueError):
            self.store.save(self.guild, normal, 0, self.entries)
        other_admin = SimpleNamespace(id=123, guild=SimpleNamespace(id=200), guild_permissions=discord.Permissions(administrator=True))
        with self.assertRaises(ValueError):
            self.store.save(self.guild, other_admin, 0, self.entries)
        self.store.save(self.guild, self.admin, 0, self.entries)
        del self.roles[10]
        self.assertEqual(self.store.active(self.guild), {'20': '+1 skin khi thắng'})
        with self.assertRaisesRegex(ValueError, 'role đã bị xóa'):
            self.store.save(self.guild, self.admin, 1, self.entries)
        self.entries['10']['enabled'] = False
        self.store.save(self.guild, self.admin, 1, self.entries)
        self.assertEqual(self.store.load(100)[0], 2)

    def test_matches_multiple_roles_and_preserves_text(self):
        member = SimpleNamespace(get_role=self.roles.get)
        self.store.save(self.guild, self.admin, 0, self.entries)
        self.assertEqual(matching_benefits(member, self.store.active(self.guild)),
            {'10': '+50k khi thắng', '20': '+1 skin khi thắng'})

    async def test_message_manager_setup_and_save(self):
        manager = SimpleNamespace(id=456, guild=self.guild, guild_permissions=discord.Permissions(manage_messages=True))
        ctx = SimpleNamespace(author=manager, guild=self.guild, send=AsyncMock())
        await self.cog.giveaway_bonus_setup.callback(self.cog, ctx)
        view = ctx.send.call_args.kwargs['view']
        self.assertIsInstance(view, CatalogEditor)
        view.entries = self.entries.copy()
        event = SimpleNamespace(user=manager, response=SimpleNamespace(edit_message=AsyncMock(), send_message=AsyncMock()))
        await view.save.callback(event)
        self.assertEqual(self.store.load(100)[1], self.entries)
        manager.guild_permissions = discord.Permissions.none()
        self.assertFalse(await view.interaction_check(event))

    async def test_compact_editor_controls_and_help(self):
        view = CatalogEditor(self.store, self.guild, self.admin)
        view.embed()
        for button in (view.save, view.discard, view.toggle, view.delete, view.edit_entry, view.previous, view.next_page):
            self.assertTrue(button.disabled)
        self.assertTrue(all(child.row <= 3 for child in view.children))
        view.entries = self.entries.copy()
        view.selected = '10'
        view.embed()
        self.assertFalse(view.save.disabled)
        self.assertFalse(view.edit_entry.disabled)
        self.assertEqual(view.toggle.label, 'Tắt mục')
        event = SimpleNamespace(response=SimpleNamespace(edit_message=AsyncMock()))
        await view.discard.callback(event)
        self.assertEqual(view.entries, {})
        self.assertTrue(view.save.disabled)
        ctx = SimpleNamespace(prefix='i?', send=AsyncMock())
        await self.cog.send_giveaway_help(ctx)
        embed = ctx.send.call_args.kwargs['embed']
        self.assertLessEqual(len(embed.description), 4096)
        self.assertLessEqual(len(embed), 6000)
        self.assertIn('Quản lý tin nhắn', embed.description)
        self.assertIn('i?ga bonus setup', embed.description)

    async def test_new_giveaway_freezes_catalog_and_explicit_override(self):
        self.store.save(self.guild, self.admin, 0, self.entries)
        ctx = MagicMock()
        ctx.guild = self.guild
        ctx.author = self.admin
        ctx.channel.id = 300
        ctx.message.attachments = []
        ctx.message.delete = AsyncMock()
        message = MagicMock(id=777)
        message.add_reaction = AsyncMock()
        ctx.channel.send = AsyncMock(return_value=message)
        ctx.send = AsyncMock()
        self.cog.can_manage_giveaway = MagicMock(return_value=True)
        self.cog.parse_giveaway_args = MagicMock(return_value=('Nitro', [], {}, {'10': 'Quà riêng'}, None, {}))
        await self.cog.giveaway_group.callback(self.cog, ctx, '1h', 1, args_str='Nitro')
        saved = self.cog.get_giveaway(777, guild_id=100)
        self.assertIsNotNone(saved)
        self.assertEqual(json.loads(saved['role_bonus_prizes']), {'10': 'Quà riêng', '20': '+1 skin khi thắng'})
        self.store.save(self.guild, self.admin, 1, {})
        self.assertEqual(json.loads(self.cog.get_giveaway(777)['role_bonus_prizes']),
            {'10': 'Quà riêng', '20': '+1 skin khi thắng'})

    async def test_member_lookup_failure_is_not_no_bonus(self):
        ctx = MagicMock()
        ctx.guild = self.guild
        ctx.author.id = 456
        ctx.send = AsyncMock()
        self.guild.fetch_member.side_effect = discord.HTTPException(MagicMock(status=503), 'Unavailable')
        await self.cog.giveaway_bonus_check.callback(self.cog, ctx)
        self.assertIn('Chưa thể tải role', ctx.send.call_args.args[0])

    async def test_draw_snapshot_survives_role_removal(self):
        self.cog.save_giveaway(777, 100, 300, 'Nitro', 123, 1, int(time.time())-1, [], {},
            role_bonus_prizes={'10': '+50k khi thắng'})
        member = MagicMock(spec=discord.Member)
        member.id, member.bot = 456, False
        member.get_role.side_effect = self.roles.get
        self.guild.get_member.return_value = member
        self.bot.get_guild.return_value = self.guild
        channel = MagicMock()
        message = MagicMock()
        message.edit = AsyncMock()
        reaction = MagicMock()
        reaction.emoji = discord.PartialEmoji(name='coin', id=1544913759297085440)
        async def users(limit=None):
            yield member
        reaction.users = users
        message.reactions = [reaction]
        channel.fetch_message = AsyncMock(return_value=message)
        channel.send = AsyncMock()
        self.guild.get_channel.return_value = channel
        self.cog.get_env_bonus_roles = MagicMock(return_value={})
        await self.cog.end_giveaway(777)
        saved = self.cog.get_giveaway(777)
        self.assertEqual(json.loads(saved['extra_reqs'])['winner_benefits']['456'], {'10': '+50k khi thắng'})
        del self.roles[10]
        ctx = MagicMock()
        ctx.guild = self.guild
        ctx.author.id = 123
        ctx.message.reference = None
        ctx.send = AsyncMock()
        await self.cog.giveaway_check.callback(self.cog, ctx, '777', '<@456>')
        description = ctx.send.call_args.kwargs['embed'].description
        self.assertIn('+50k khi thắng', description)
        self.assertIn('thời điểm trúng giải', description)
        self.guild.fetch_member.assert_not_called()

    async def test_editor_draft_and_pagination(self):
        self.store.save(self.guild, self.admin, 0, self.entries)
        view = CatalogEditor(self.store, self.guild, self.admin)
        view.entries['10']['text'] = 'Changed draft'
        self.assertEqual(self.store.active(self.guild)['10'], '+50k khi thắng')
        self.assertIn('chưa lưu', view.embed().title)
        viewer = BonusPages(123, 'Many roles', ['x' * 350] * 100)
        for page in range(20):
            viewer.page = page
            self.assertLess(len(viewer.embed().description), 4096)

    async def test_modal_to_save_and_revoked_permission(self):
        view = CatalogEditor(self.store, self.guild, self.admin)
        event = MagicMock()
        event.user = self.admin
        event.response.edit_message = AsyncMock()
        event.response.send_message = AsyncMock()
        modal = CatalogBenefitModal(view, self.roles[10])
        modal.benefit._value = '+50k khi thắng'
        modal.order._value = '2'
        await modal.on_submit(event)
        self.assertEqual(self.store.load(100), (0, {}))
        await view.save.callback(event)
        self.assertEqual(self.store.active(self.guild), {'10': '+50k khi thắng'})
        view.entries['10']['text'] = 'Not authorized'
        self.admin.guild_permissions = discord.Permissions.none()
        await view.save.callback(event)
        self.assertEqual(self.store.active(self.guild), {'10': '+50k khi thắng'})

    async def test_catalog_import_requires_confirmation_and_only_changes_draft(self):
        self.store.save(self.guild, self.admin, 0, self.entries)
        self.cog.save_giveaway(777, 100, 300, 'Nitro', 123, 1, int(time.time())+3600, [], {},
            role_bonus_prizes={'10': 'Old', '30': 'Giveaway only'})
        editor = GiveawayEditorView(self.cog, self.cog.get_giveaway(777), self.admin, self.guild)
        view = GiveawayPrizeBonusView(editor)
        event = MagicMock()
        event.user = self.admin
        event.response.edit_message = AsyncMock()
        await view._on_load_catalog(event)
        self.assertEqual(view.role_prizes['10'], 'Old')
        confirm = event.response.edit_message.call_args.kwargs['view']
        await confirm.children[0].callback(event)
        self.assertEqual(view.role_prizes['10'], '+50k khi thắng')
        self.assertEqual(view.role_prizes['30'], 'Giveaway only')
        self.assertEqual(json.loads(self.cog.get_giveaway(777)['role_bonus_prizes'])['10'], 'Old')

    async def test_check_nonwinner_does_not_claim_reward(self):
        self.cog.save_giveaway(777, 100, 300, 'Nitro', 123, 1, int(time.time())+3600, [], {},
            role_bonus_prizes={'10': '+50k khi thắng'})
        self.guild.fetch_member.return_value = SimpleNamespace(get_role=self.roles.get)
        ctx = MagicMock()
        ctx.guild = self.guild
        ctx.author.id = 123
        ctx.message.reference = None
        ctx.send = AsyncMock()
        await self.cog.giveaway_check.callback(self.cog, ctx, '777', '<@456>')
        description = ctx.send.call_args.kwargs['embed'].description
        self.assertIn('Không phải người thắng', description)
        self.assertNotIn('Tổng nhận', description)
