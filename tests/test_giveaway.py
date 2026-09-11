import json
import sqlite3
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from app.discord_bot.cogs.giveaway import (
    Giveaway,
    is_giveaway_emoji,
    pick_weighted_winners,
)


class TestGiveawayFixes(unittest.TestCase):
    def setUp(self):
        # Create an in-memory SQLite economy mock
        self.conn = sqlite3.connect(":memory:")
        self.cur = self.conn.cursor()
        
        self.mock_economy = MagicMock()
        self.mock_economy.conn = self.conn
        self.mock_economy.cur = self.cur

        self.mock_bot = MagicMock()
        self.mock_bot.economy = self.mock_economy

        # Initialize Giveaway cog
        self.cog = Giveaway(self.mock_bot)

    def tearDown(self):
        self.cog.cog_unload()
        self.conn.close()

    # -------------------------------------------------------------------------
    # Issue 1: Cross-guild management security (P0)
    # -------------------------------------------------------------------------
    def test_cross_guild_access_prevention(self):
        """Admin of Guild A cannot manage or access giveaways in Guild B."""
        # Setup Guild A member with admin perms
        member_guild_a = MagicMock()
        member_guild_a.id = 12345
        member_guild_a.guild = MagicMock(id=111)
        member_guild_a.guild_permissions.administrator = True
        member_guild_a.guild_permissions.manage_guild = True

        giveaway_guild_b = {
            "id": 999,
            "guild_id": 222,  # Different guild!
            "host_id": 99999,
        }

        # can_manage_giveaway should return False because guild_ids don't match
        self.assertFalse(self.cog.can_manage_giveaway(member_guild_a, giveaway_guild_b))

        # Same guild: should return True
        giveaway_guild_a = {
            "id": 888,
            "guild_id": 111,
            "host_id": 99999,
        }
        self.assertTrue(self.cog.can_manage_giveaway(member_guild_a, giveaway_guild_a))

    def test_get_giveaway_guild_isolation(self):
        """get_giveaway with guild_id filter returns None if queried from another guild."""
        self.cog.save_giveaway(
            msg_id=5001,
            guild_id=111,
            channel_id=1001,
            prize="VIP Nitro",
            host_id=123,
            winner_count=1,
            ends_at=9999999999,
            required_roles=[],
            bonus_roles={}
        )

        # Query with matching guild_id
        ga_found = self.cog.get_giveaway(5001, guild_id=111)
        self.assertIsNotNone(ga_found)
        self.assertEqual(ga_found["id"], 5001)

        # Query with different guild_id (Server B trying to inspect Server A)
        ga_cross = self.cog.get_giveaway(5001, guild_id=222)
        self.assertIsNone(ga_cross)

    # -------------------------------------------------------------------------
    # Issue 2: Creation permissions (P0)
    # -------------------------------------------------------------------------
    def test_regular_member_cannot_manage_giveaway(self):
        """Regular user without admin / manage_guild / manage_messages cannot manage/create."""
        regular_member = MagicMock()
        regular_member.id = 77777
        regular_member.guild = MagicMock(id=111)
        regular_member.guild_permissions.administrator = False
        regular_member.guild_permissions.manage_guild = False
        regular_member.guild_permissions.manage_messages = False

        self.assertFalse(self.cog.can_manage_giveaway(regular_member))

    # -------------------------------------------------------------------------
    # Issue 3: Race condition with atomic CAS (P1)
    # -------------------------------------------------------------------------
    def test_atomic_cas_prevents_duplicate_end(self):
        """Atomic UPDATE giveaways SET ended = 3 WHERE id = ? AND ended = 0 prevents race condition."""
        self.cog.save_giveaway(
            msg_id=6001,
            guild_id=111,
            channel_id=1001,
            prize="Gold Key",
            host_id=123,
            winner_count=1,
            ends_at=9999999999,
            required_roles=[],
            bonus_roles={}
        )

        # First concurrent worker tries to claim the giveaway
        self.cur.execute("UPDATE giveaways SET ended = 3 WHERE id = ? AND ended = 0", (6001,))
        first_rowcount = self.cur.rowcount
        self.conn.commit()
        self.assertEqual(first_rowcount, 1)

        # Second concurrent worker tries to claim the giveaway at the same time
        self.cur.execute("UPDATE giveaways SET ended = 3 WHERE id = ? AND ended = 0", (6001,))
        second_rowcount = self.cur.rowcount
        self.conn.commit()
        self.assertEqual(second_rowcount, 0, "Second worker must not be able to claim already ending giveaway")

    # -------------------------------------------------------------------------
    # Issue 6: Weighted sampling with secrets.SystemRandom & OOM prevention (P1)
    # -------------------------------------------------------------------------
    def test_pick_weighted_winners_oom_safe(self):
        """Large bonus ticket values do not cause OOM / excessive memory usage."""
        candidates = {
            1001: 5_000_000,  # 5 million tickets
            1002: 10_000_000, # 10 million tickets
            1003: 1,
        }
        # Must execute swiftly without creating a 15-million element array
        winners = pick_weighted_winners(candidates, k=2)
        self.assertEqual(len(winners), 2)
        self.assertEqual(len(set(winners)), 2, "Winners must be unique")

    def test_pick_weighted_winners_excludes_users(self):
        """pick_weighted_winners strictly excludes users in the exclude set."""
        candidates = {1: 10, 2: 10, 3: 10}
        exclude = {2, 3}
        winners = pick_weighted_winners(candidates, k=2, exclude=exclude)
        self.assertEqual(winners, [1])

    # -------------------------------------------------------------------------
    # Issue 7: Database error handling (P1)
    # -------------------------------------------------------------------------
    def test_save_giveaway_returns_boolean(self):
        """save_giveaway returns True on success and False on failure."""
        res = self.cog.save_giveaway(
            msg_id=7001,
            guild_id=111,
            channel_id=1001,
            prize="Prize",
            host_id=123,
            winner_count=1,
            ends_at=9999999999,
            required_roles=[],
            bonus_roles={}
        )
        self.assertTrue(res)

        # Attempt duplicate insert with same primary key
        res_dup = self.cog.save_giveaway(
            msg_id=7001,
            guild_id=111,
            channel_id=1001,
            prize="Prize",
            host_id=123,
            winner_count=1,
            ends_at=9999999999,
            required_roles=[],
            bonus_roles={}
        )
        self.assertFalse(res_dup, "Duplicate primary key insert should return False without crashing")

    # -------------------------------------------------------------------------
    # Issue 8: Reroll history preservation (P2)
    # -------------------------------------------------------------------------
    def test_reroll_history_exclusion(self):
        """Reroll tracks past winners and prevents them from winning again."""
        candidates = {101: 1, 102: 1, 103: 1, 104: 1}
        original_winners = [101]
        reroll_history = [102]

        all_excluded = set(original_winners) | set(reroll_history)
        new_winners = pick_weighted_winners(candidates, k=1, exclude=all_excluded)
        self.assertNotIn(new_winners[0], all_excluded)
        self.assertIn(new_winners[0], [103, 104])

    # -------------------------------------------------------------------------
    # Emoji fallback validation
    # -------------------------------------------------------------------------
    def test_is_giveaway_emoji(self):
        """Checks that custom giveaway coins and unicode 🎉 are accepted, others rejected."""
        # Unicode party popper
        self.assertTrue(is_giveaway_emoji("🎉"))

        # Custom coin emoji mock
        mock_coin = MagicMock()
        mock_coin.is_custom_emoji.return_value = True
        mock_coin.id = 1544913759297085440
        self.assertTrue(is_giveaway_emoji(mock_coin))

        # Unrelated emoji
        mock_other = MagicMock()
        mock_other.is_custom_emoji.return_value = True
        mock_other.id = 999999999
        self.assertFalse(is_giveaway_emoji(mock_other))

        mock_unicode_other = MagicMock()
        mock_unicode_other.is_custom_emoji.return_value = False
        mock_unicode_other.name = "👍"
        self.assertFalse(is_giveaway_emoji(mock_unicode_other))

    # -------------------------------------------------------------------------
    # Partial Index validation
    # -------------------------------------------------------------------------
    def test_partial_index_created(self):
        """Verifies that the partial index idx_giveaways_active_ends exists in SQLite."""
        self.cur.execute("SELECT name FROM sqlite_master WHERE type='index' AND name='idx_giveaways_active_ends'")
        row = self.cur.fetchone()
        self.assertIsNotNone(row, "idx_giveaways_active_ends partial index must exist")

    # -------------------------------------------------------------------------
    # Issue 9: Modal and Editor Invariants (P2)
    # -------------------------------------------------------------------------
    def test_modal_rejects_both_required_and_bonus_roles(self):
        """GiveawayRequirementsModal rejects submitting both required roles and bonus roles."""
        import asyncio
        from app.discord_bot.cogs.giveaway import GiveawayRequirementsModal

        mock_editor_view = MagicMock()
        mock_editor_view.giveaway = {"required_roles": [], "bonus_roles": {}}
        mock_editor_view.guild = MagicMock()

        modal = GiveawayRequirementsModal(mock_editor_view)
        modal.required_roles_input._value = "123456789"
        modal.bonus_roles_input._value = "987654321:2"

        from unittest.mock import AsyncMock

        mock_interaction = MagicMock()
        mock_interaction.guild = mock_editor_view.guild
        mock_interaction.response.send_message = AsyncMock()

        # Execute on_submit
        asyncio.run(modal.on_submit(mock_interaction))

        mock_interaction.response.send_message.assert_called_once()
        args, kwargs = mock_interaction.response.send_message.call_args
        self.assertIn("không thể cấu hình giới hạn role và cộng lượt cùng lúc", args[0])
        self.assertTrue(kwargs.get("ephemeral"))
        # Editor view giveaway must NOT have been updated
        self.assertEqual(mock_editor_view.giveaway["required_roles"], [])
        self.assertEqual(mock_editor_view.giveaway["bonus_roles"], {})


# =============================================================================
# 5-STEP FULL SYNCHRONIZATION PIPELINE TESTS
# =============================================================================

class TestGiveawaySyncPlan(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        import time
        self.conn = sqlite3.connect(":memory:")
        self.cur = self.conn.cursor()

        self.mock_economy = MagicMock()
        self.mock_economy.conn = self.conn
        self.mock_economy.cur = self.cur

        self.mock_bot = MagicMock()
        self.mock_bot.economy = self.mock_economy

        # Setup mock guild, channel, and message
        self.mock_guild = MagicMock()
        self.mock_guild.id = 111
        self.mock_guild.name = "Test Guild"
        self.mock_guild.icon = None

        self.mock_channel = MagicMock()
        self.mock_channel.id = 1001

        self.mock_message = MagicMock()
        self.mock_message.id = 7777
        from unittest.mock import AsyncMock
        self.mock_message.edit = AsyncMock()

        self.mock_channel.fetch_message = AsyncMock(return_value=self.mock_message)
        self.mock_guild.get_channel = MagicMock(return_value=self.mock_channel)
        self.mock_bot.get_guild = MagicMock(return_value=self.mock_guild)
        self.mock_bot.get_user = MagicMock(return_value=None)
        self.mock_bot.wait_until_ready = AsyncMock()

        self.cog = Giveaway(self.mock_bot)

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.conn.close()

    # 1. Edit màu/banner/footer/title rồi kết thúc
    async def test_edit_styling_and_end(self):
        """Editing styling (color, banner, footer, title, ended_desc) retains all styling at end."""
        import json, time
        self.cog.save_giveaway(
            msg_id=7777,
            guild_id=111,
            channel_id=1001,
            prize="VIP Nitro",
            host_id=123,
            winner_count=2,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )

        embed_config = {
            "color": "#FF0000",
            "banner": "https://example.com/banner.png",
            "footer_text": "Custom Footer Text",
            "active_title": "Custom Active Title",
            "ended_title": "Custom Ended Title",
            "ended_desc": "🏁 Prize: {prize} | Winners: {winners}"
        }

        success, err = await self.cog.update_and_sync_giveaway(
            7777,
            guild_id=111,
            expected_status=0,
            embed_config=embed_config
        )
        self.assertTrue(success, f"Failed to edit styling: {err}")

        # Now end giveaway
        success_end, err_end = await self.cog.update_and_sync_giveaway(
            7777,
            guild_id=111,
            ended=1,
            winners=[1001, 1002],
            status="ended"
        )
        self.assertTrue(success_end, f"Failed to end: {err_end}")

        # Check edited embed on Discord message
        _, kwargs = self.mock_message.edit.call_args
        embed = kwargs.get("embed")
        self.assertIsNotNone(embed)
        self.assertEqual(embed.title, "Custom Ended Title")
        self.assertEqual(embed.color.value, 0xFF0000)
        self.assertEqual(embed.image.url, "https://example.com/banner.png")
        self.assertEqual(embed.footer.text, "Custom Footer Text")
        self.assertIn("🏁 Prize: VIP Nitro | Winners: <@1001>, <@1002>", embed.description)

    # 2. Edit prize và winner count rồi kết thúc
    async def test_edit_prize_and_winner_count_then_end(self):
        """Editing prize and winner_count synchronizes live and reflects accurately upon end."""
        import time
        self.cog.save_giveaway(
            msg_id=7777,
            guild_id=111,
            channel_id=1001,
            prize="Old Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )

        success, err = await self.cog.update_and_sync_giveaway(
            7777,
            guild_id=111,
            expected_status=0,
            prize="1,000,000 Xu",
            winner_count=3
        )
        self.assertTrue(success, f"Failed to update prize and winner_count: {err}")

        # End giveaway with 3 winners
        success_end, err_end = await self.cog.update_and_sync_giveaway(
            7777,
            guild_id=111,
            ended=1,
            winners=[201, 202, 203],
            status="ended"
        )
        self.assertTrue(success_end, f"Failed to end giveaway: {err_end}")

        _, kwargs = self.mock_message.edit.call_args
        embed = kwargs.get("embed")
        self.assertIn("1,000,000 Xu", embed.description)
        self.assertIn("Win:* 3", embed.description)
        self.assertIn("<@201>, <@202>, <@203>", embed.description)

    # 3. Cancel dùng đúng toàn bộ giao diện
    async def test_cancel_retains_full_styling(self):
        """Cancelling a giveaway preserves color, banner, footer, and uses cancelled title & status note."""
        import time
        embed_config = {
            "color": "#00FF00",
            "banner": "https://example.com/cancelled_banner.png",
            "footer_text": "Secure GA System",
            "cancelled_title": "🛑 GIVEAWAY ĐÃ HỦY THEO YÊU CẦU 🛑"
        }
        self.cog.save_giveaway(
            msg_id=7777,
            guild_id=111,
            channel_id=1001,
            prize="Special Badge",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={},
            embed_config=embed_config
        )

        success, err = await self.cog.update_and_sync_giveaway(
            7777,
            guild_id=111,
            expected_status=0,
            ended=2,
            status="cancelled",
            status_note="Sự kiện bị hủy do bảo trì hệ thống."
        )
        self.assertTrue(success, f"Failed to cancel giveaway: {err}")

        # Verify DB state
        fresh = self.cog.get_giveaway(7777)
        self.assertEqual(fresh["ended"], 2)

        # Verify embed styling
        _, kwargs = self.mock_message.edit.call_args
        embed = kwargs.get("embed")
        self.assertEqual(embed.title, "🛑 GIVEAWAY ĐÃ HỦY THEO YÊU CẦU 🛑")
        self.assertEqual(embed.color.value, 0x00FF00)
        self.assertEqual(embed.image.url, "https://example.com/cancelled_banner.png")
        self.assertEqual(embed.footer.text, "Secure GA System")
        self.assertIn("Sự kiện bị hủy do bảo trì hệ thống.", embed.description)

    # 4. Reroll giữ giao diện và lịch sử winners
    async def test_reroll_retains_styling_and_history(self):
        """Reroll retains all embed appearance while showing new winners and past winner history."""
        import time
        embed_config = {
            "color": "#9900FF",
            "banner": "https://example.com/reroll_banner.png",
            "footer_text": "Casino Bot GA"
        }
        self.cog.save_giveaway(
            msg_id=7777,
            guild_id=111,
            channel_id=1001,
            prize="100 USDT",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 100,
            required_roles=[],
            bonus_roles={},
            embed_config=embed_config
        )
        self.cog.update_giveaway_full(7777, ended=1, winners=[301])

        extra_reqs = {"original_winners": [301], "reroll_history": [301]}
        success, err = await self.cog.update_and_sync_giveaway(
            7777,
            guild_id=111,
            expected_status=1,
            winners=[302],
            extra_reqs=extra_reqs,
            status="rerolled"
        )
        self.assertTrue(success, f"Failed to reroll: {err}")

        _, kwargs = self.mock_message.edit.call_args
        embed = kwargs.get("embed")
        self.assertEqual(embed.color.value, 0x9900FF)
        self.assertEqual(embed.image.url, "https://example.com/reroll_banner.png")
        self.assertIn("<@302>", embed.description)
        self.assertIn("Lịch sử trúng:* <@301>", embed.description)

    # 5. setbonus / delbonus sync ngay
    async def test_setbonus_and_delbonus_sync(self):
        """setbonus and delbonus immediately update DB and sync the Discord message."""
        import time
        from unittest.mock import AsyncMock
        self.cog.save_giveaway(
            msg_id=7777,
            guild_id=111,
            channel_id=1001,
            prize="Grand Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )

        ctx = MagicMock()
        ctx.guild = self.mock_guild
        ctx.author = MagicMock(id=123)
        ctx.author.guild = self.mock_guild
        ctx.author.guild_permissions.administrator = True
        ctx.send = AsyncMock()
        ctx.message.delete = AsyncMock()
        ctx.message.reference = None

        # Call setbonus
        await self.cog.giveaway_setbonus.callback(self.cog, ctx, message_id_or_role="7777", role_or_text="<@&8888>", bonus_text="50k Momo")
        fresh = self.cog.get_giveaway(7777)
        import json
        prizes = json.loads(fresh["role_bonus_prizes"])
        self.assertIn("8888", prizes)
        self.assertEqual(prizes["8888"], "50k Momo")

        # Verify Discord message edit was called with bonus
        _, kwargs = self.mock_message.edit.call_args
        embed = kwargs.get("embed")
        self.assertIn("<@&8888>: **50k Momo**", embed.description)

        # Call delbonus
        await self.cog.giveaway_delbonus.callback(self.cog, ctx, message_id_or_role="7777", role_opt="<@&8888>")
        fresh2 = self.cog.get_giveaway(7777)
        prizes2 = json.loads(fresh2["role_bonus_prizes"])
        self.assertNotIn("8888", prizes2)

        # Verify Discord message edit was called without bonus
        _, kwargs2 = self.mock_message.edit.call_args
        embed2 = kwargs2.get("embed")
        self.assertNotIn("<@&8888>: **50k Momo**", embed2.description)

    # 6. Editor cũ không ghi đè giveaway đã kết thúc
    async def test_stale_editor_cannot_overwrite_ended(self):
        """GiveawayEditorView rejects applying changes to an already ended giveaway."""
        import time
        from unittest.mock import AsyncMock
        from app.discord_bot.cogs.giveaway import GiveawayEditorView

        self.cog.save_giveaway(
            msg_id=7777,
            guild_id=111,
            channel_id=1001,
            prize="Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )
        initial_ga = self.cog.get_giveaway(7777)
        user = MagicMock(id=123)
        user.guild_permissions.administrator = True

        editor_view = GiveawayEditorView(self.cog, initial_ga, user, self.mock_guild)

        # Giveaway ends in DB concurrently
        self.cog.update_giveaway_full(7777, ended=1)

        mock_interaction = MagicMock()
        mock_interaction.user = user
        mock_interaction.response.send_message = AsyncMock()
        mock_interaction.response.edit_message = AsyncMock()

        # Editor attempts to apply changes
        await editor_view.btn_apply_sync.callback(mock_interaction)

        mock_interaction.response.send_message.assert_called_once()
        msg = mock_interaction.response.send_message.call_args[0][0]
        self.assertIn("đã kết thúc hoặc đã bị hủy", msg)

        # Confirm DB is still ended and was not overwritten
        self.assertEqual(self.cog.get_giveaway(7777)["ended"], 1)

    # 7. Discord edit thất bại không được báo thành công
    async def test_discord_edit_failure_reports_error(self):
        """update_and_sync_giveaway returns (False, error) if Discord message edit fails."""
        import time
        from unittest.mock import AsyncMock
        self.cog.save_giveaway(
            msg_id=7777,
            guild_id=111,
            channel_id=1001,
            prize="Unsynced Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )

        # Force message edit to fail with Discord exception
        import discord
        self.mock_message.edit = AsyncMock(side_effect=discord.HTTPException(response=MagicMock(status=403), message="Forbidden edit"))

        success, err = await self.cog.update_and_sync_giveaway(7777, guild_id=111, prize="New Prize")
        self.assertFalse(success, "Must return False when Discord message edit fails")
        self.assertIsNotNone(err)
        self.assertIn("Lỗi cập nhật tin nhắn Discord", err)

    # 8. Cấu hình / template cũ vẫn render đúng
    def test_legacy_template_backward_compatibility(self):
        """Legacy embed configurations without {status}_title or {status}_desc render without errors."""
        import json, time
        legacy_config = {
            "color": "gold",
            "banner": "https://example.com/legacy.png",
            "title": "Old Style Title",
            "custom_desc": "Legacy simple note"
        }
        legacy_ga = {
            'id': 9999,
            'guild_id': 111,
            'channel_id': 1001,
            'message_id': 9999,
            'prize': "Legacy Steam Key",
            'host_id': 123,
            'winner_count': 1,
            'ends_at': int(time.time()) + 3600,
            'ended': 0,
            'required_roles': "[]",
            'bonus_roles': "{}",
            'participants': "{}",
            'winners': "[]",
            'embed_config': json.dumps(legacy_config),
            'extra_reqs': "{}",
            'role_bonus_prizes': "{}"
        }

        # Active render
        active_embed = self.cog.build_giveaway_embed(legacy_ga, status="active")
        self.assertEqual(active_embed.title, "Old Style Title")
        self.assertEqual(active_embed.image.url, "https://example.com/legacy.png")
        self.assertIn("Legacy simple note", active_embed.description)

        # Ended render
        ended_embed = self.cog.build_giveaway_embed(legacy_ga, status="ended", winners=[8888])
        self.assertEqual(ended_embed.title, "Old Style Title")
        self.assertEqual(ended_embed.image.url, "https://example.com/legacy.png")
        self.assertIn("<@8888>", ended_embed.description)

        # Cancelled render
        cancelled_embed = self.cog.build_giveaway_embed(legacy_ga, status="cancelled", status_note="Bị huỷ")
        self.assertEqual(cancelled_embed.title, "Old Style Title")
        self.assertEqual(cancelled_embed.image.url, "https://example.com/legacy.png")
        self.assertIn("Bị huỷ", cancelled_embed.description)

        # Rerolled render
        rerolled_embed = self.cog.build_giveaway_embed(legacy_ga, status="rerolled", winners=[7777])
        self.assertEqual(rerolled_embed.title, "Old Style Title")
        self.assertEqual(rerolled_embed.image.url, "https://example.com/legacy.png")
        self.assertIn("<@7777>", rerolled_embed.description)


# ==============================================================================
# 10. TEST SUITE FOR SERVER-WIDE TEMPLATES (NO PERSONAL TEMPLATES)
# ==============================================================================

class TestServerGiveawayTemplate(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import AsyncMock, MagicMock
        import discord
        self.conn = sqlite3.connect(":memory:")
        self.cur = self.conn.cursor()

        self.mock_economy = MagicMock()
        self.mock_economy.conn = self.conn
        self.mock_economy.cur = self.cur

        self.mock_bot = MagicMock()
        self.mock_bot.economy = self.mock_economy
        self.mock_bot.user = MagicMock(id=999999)
        self.mock_bot.wait_until_ready = AsyncMock()

        self.cog = Giveaway(self.mock_bot)

        self.mock_guild = MagicMock(spec=discord.Guild)
        self.mock_guild.id = 12345
        self.mock_guild.name = "Test Gaming Guild"
        self.mock_bot.get_guild.return_value = self.mock_guild

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.conn.close()

    # 1. Hai thành viên tạo giveaway đều nhận cùng một template server
    def test_server_template_used_by_all_creators(self):
        server_config = {
            "color": "gold",
            "title": "Default Server Giveaway",
            "banner": "https://example.com/server_banner.png"
        }
        self.cog.save_template(12345, "default", server_config, updated_by=111)

        # Creator A reads template
        tpl_a = self.cog.get_template(12345)
        self.assertEqual(tpl_a["title"], "Default Server Giveaway")
        self.assertEqual(tpl_a["color"], "gold")

        # Creator B reads template
        tpl_b = self.cog.get_template(12345)
        self.assertEqual(tpl_b["title"], "Default Server Giveaway")
        self.assertEqual(tpl_b["color"], "gold")
        self.assertEqual(tpl_a, tpl_b)

    # 2. Admin A save, Admin B mở template thấy đúng bản mới nhất
    def test_admin_save_and_other_admin_read(self):
        new_config = {
            "title": "Summer Event 2026",
            "banner": "https://example.com/summer.png"
        }
        success = self.cog.save_template(12345, "default", new_config, updated_by=1001)
        self.assertTrue(success)

        # Admin B gets template
        tpl = self.cog.get_template(12345, "default")
        self.assertEqual(tpl["title"], "Summer Event 2026")
        self.assertEqual(tpl["banner"], "https://example.com/summer.png")

        # Verify DB metadata columns
        self.cur.execute("SELECT updated_by, updated_at FROM giveaway_templates WHERE guild_id = 12345 AND template_name = 'default'")
        row = self.cur.fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row[0], 1001)
        self.assertGreater(row[1], 0)

    # 3. Không còn template cá nhân ghi đè template server
    def test_no_personal_template_override(self):
        # Set server template
        self.cog.save_template(12345, "default", {"title": "Official Guild Theme"}, updated_by=111)

        # Legacy call with user_id or getting with user_id should always return guild default
        res_user_a = self.cog.get_template(12345, user_id=9999)
        res_user_b = self.cog.get_template(12345, user_id=8888)
        self.assertEqual(res_user_a["title"], "Official Guild Theme")
        self.assertEqual(res_user_b["title"], "Official Guild Theme")

        # Table schema must not contain user_id column
        self.cur.execute("PRAGMA table_info(giveaway_templates)")
        cols = [c[1] for c in self.cur.fetchall()]
        self.assertNotIn("user_id", cols, "user_id column must NOT exist in giveaway_templates")
        self.assertIn("guild_id", cols)
        self.assertIn("template_name", cols)

    # 4. Đổi template không ảnh hưởng giveaway đang chạy
    def test_updating_server_template_does_not_affect_running_giveaway(self):
        import time
        self.cog.save_template(12345, "default", {"color": "blue", "title": "Old Blue Theme"}, updated_by=111)

        # Create giveaway 5001 with original template
        self.cog.save_giveaway(
            5001, 12345, 1001, "Discord Nitro", 111, 1,
            int(time.time()) + 3600, [], {},
            embed_config={"color": "blue", "title": "Old Blue Theme"}
        )

        # Now server changes template to Red Theme
        self.cog.save_template(12345, "default", {"color": "red", "title": "New Red Theme"}, updated_by=222)

        # Check giveaway 5001 - its stored embed_config must remain blue
        ga = self.cog.get_giveaway(5001, guild_id=12345)
        cfg = json.loads(ga["embed_config"])
        self.assertEqual(cfg["color"], "blue")
        self.assertEqual(cfg["title"], "Old Blue Theme")

    # 5. End/cancel/reroll vẫn dùng cấu hình riêng của giveaway
    async def test_end_cancel_reroll_use_giveaway_own_config(self):
        import time
        mock_channel = MagicMock(spec=discord.TextChannel)
        mock_channel.id = 1001
        mock_msg = AsyncMock(spec=discord.Message)
        mock_msg.id = 5002
        mock_channel.fetch_message = AsyncMock(return_value=mock_msg)
        self.mock_guild.get_channel = MagicMock(return_value=mock_channel)

        unique_banner = "https://example.com/unique_isolated.png"
        self.cog.save_giveaway(
            5002, 12345, 1001, "Steam Code", 111, 1,
            int(time.time()) + 3600, [], {},
            embed_config={"banner": unique_banner, "title": "Isolated Giveaway"}
        )

        # Server template updated
        self.cog.save_template(12345, "default", {"banner": "https://example.com/different.png", "title": "Different"}, updated_by=111)

        # Cancel giveaway
        success, err = await self.cog.update_and_sync_giveaway(
            5002, guild_id=12345, expected_status=0, ended=2, status="cancelled", status_note="Bị huỷ bởi Host"
        )
        self.assertTrue(success)
        mock_msg.edit.assert_called_once()
        call_kwargs = mock_msg.edit.call_args[1]
        cancelled_embed = call_kwargs["embed"]
        self.assertEqual(cancelled_embed.image.url, unique_banner, "Must preserve giveaway's own banner")
        self.assertEqual(cancelled_embed.title, "Isolated Giveaway", "Must preserve giveaway's own title")

    # 6. Người không có quyền không thể thay đổi template server
    def test_permission_checks_for_template_management(self):
        # 1. Regular Member
        normal = MagicMock(spec=discord.Member)
        normal.id = 101
        normal.roles = []
        normal.guild_permissions = discord.Permissions(send_messages=True)
        self.assertFalse(self.cog.can_manage_server_template(normal))

        # 2. Member with Manage Messages ONLY -> Not allowed
        mod_msg = MagicMock(spec=discord.Member)
        mod_msg.id = 102
        mod_msg.roles = []
        mod_msg.guild_permissions = discord.Permissions(manage_messages=True)
        self.assertFalse(self.cog.can_manage_server_template(mod_msg), "Manage Messages alone must NOT manage server template")

        # 3. Member with Manage Guild -> Allowed
        mgr_guild = MagicMock(spec=discord.Member)
        mgr_guild.id = 103
        mgr_guild.roles = []
        mgr_guild.guild_permissions = discord.Permissions(manage_guild=True)
        self.assertTrue(self.cog.can_manage_server_template(mgr_guild))

        # 4. Member with Administrator -> Allowed
        admin = MagicMock(spec=discord.Member)
        admin.id = 104
        admin.roles = []
        admin.guild_permissions = discord.Permissions(administrator=True)
        self.assertTrue(self.cog.can_manage_server_template(admin))

        # 5. Member with 'Giveaway Manager' role -> Allowed
        role_ga = MagicMock(spec=discord.Role)
        role_ga.name = "Giveaway Manager"
        role_user = MagicMock(spec=discord.Member)
        role_user.id = 105
        role_user.roles = [role_ga]
        role_user.guild_permissions = discord.Permissions(send_messages=True)
        self.assertTrue(self.cog.can_manage_server_template(role_user))

    # 7. Migration từ bảng cũ có user_id
    def test_legacy_migration_from_old_table(self):
        conn = sqlite3.connect(":memory:")
        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE giveaway_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                guild_id INTEGER NOT NULL,
                user_id INTEGER,
                template_name TEXT NOT NULL,
                embed_config TEXT NOT NULL,
                UNIQUE(guild_id, user_id, template_name)
            )
        """)
        # Guild 1: has user_id = 0 and personal user_id = 100
        cur.execute("INSERT INTO giveaway_templates (guild_id, user_id, template_name, embed_config) VALUES (1, 0, 'default', '{\"title\": \"Guild 1 Server Default\"}')")
        cur.execute("INSERT INTO giveaway_templates (guild_id, user_id, template_name, embed_config) VALUES (1, 100, 'default', '{\"title\": \"Guild 1 Personal Old\"}')")
        # Guild 2: has only personal templates (id 1: 201, id 2: 202)
        cur.execute("INSERT INTO giveaway_templates (guild_id, user_id, template_name, embed_config) VALUES (2, 201, 'default', '{\"title\": \"Guild 2 First Personal\"}')")
        cur.execute("INSERT INTO giveaway_templates (guild_id, user_id, template_name, embed_config) VALUES (2, 202, 'default', '{\"title\": \"Guild 2 Latest Personal\"}')")
        conn.commit()

        # Run init_db on this connection
        test_cog = Giveaway(self.mock_bot)
        mock_eco = MagicMock()
        mock_eco.conn = conn
        mock_eco.cur = cur
        test_cog.economy = mock_eco
        test_cog.init_db()

        # Check backup exists
        cur.execute("SELECT COUNT(*) FROM giveaway_templates_old_backup")
        self.assertEqual(cur.fetchone()[0], 4)

        # Check new table has no user_id
        cur.execute("PRAGMA table_info(giveaway_templates)")
        cols = [c[1] for c in cur.fetchall()]
        self.assertNotIn("user_id", cols)
        self.assertIn("updated_by", cols)
        self.assertIn("updated_at", cols)

        # Guild 1 took user_id = 0
        cur.execute("SELECT embed_config FROM giveaway_templates WHERE guild_id = 1")
        self.assertIn("Guild 1 Server Default", cur.fetchone()[0])

        # Guild 2 took the latest personal template (User 202)
        cur.execute("SELECT embed_config FROM giveaway_templates WHERE guild_id = 2")
        self.assertIn("Guild 2 Latest Personal", cur.fetchone()[0])

        conn.close()

    # 8. Kiểm tra nút Save Mẫu Server và Apply trong Editor
    async def test_editor_save_template_and_apply_buttons(self):
        from app.discord_bot.cogs.giveaway import GiveawayEditorView

        # Setup authorized admin
        admin_member = MagicMock(spec=discord.Member)
        admin_member.id = 888
        admin_member.roles = []
        admin_member.guild_permissions = discord.Permissions(administrator=True)

        # Unauthorized member
        normal_member = MagicMock(spec=discord.Member)
        normal_member.id = 999
        normal_member.roles = []
        normal_member.guild_permissions = discord.Permissions(send_messages=True)

        ga_data = {
            'id': 0, # Template Mode
            'guild_id': 12345,
            'channel_id': 1001,
            'prize': "Nitro",
            'host_id': 888,
            'winner_count': 1,
            'ends_at': int(time.time()) + 3600,
            'ended': 0,
            'required_roles': [],
            'bonus_roles': {},
            'role_bonus_prizes': {},
            'embed_config': {"title": "Studio Created Template"}
        }

        view = GiveawayEditorView(self.cog, ga_data, admin_member, self.mock_guild)

        # 1. Unauthorized interaction check
        interaction_unauth = MagicMock(spec=discord.Interaction)
        interaction_unauth.user = normal_member
        interaction_unauth.response = MagicMock()
        interaction_unauth.response.send_message = AsyncMock()
        await view.btn_save_default.callback(interaction_unauth)
        interaction_unauth.response.send_message.assert_called_with(
            "❌ Bạn không có quyền quản lý Mẫu Giveaway của Server. (Yêu cầu quyền Administrator, Quản lý Server hoặc Role `Giveaway Manager`)",
            ephemeral=True
        )

        # 2. Authorized interaction saves template
        interaction_auth = MagicMock(spec=discord.Interaction)
        interaction_auth.user = admin_member
        interaction_auth.response = MagicMock()
        interaction_auth.response.edit_message = AsyncMock()
        interaction_auth.response.send_message = AsyncMock()
        await view.btn_save_default.callback(interaction_auth)
        tpl = self.cog.get_template(12345)
        self.assertEqual(tpl.get("title"), "Studio Created Template")

        # 3. In Template mode (id=0), clicking Apply & Sync warns that there is no specific giveaway
        interaction_apply = MagicMock(spec=discord.Interaction)
        interaction_apply.user = admin_member
        interaction_apply.response = MagicMock()
        interaction_apply.response.send_message = AsyncMock()
        await view.btn_apply_sync.callback(interaction_apply)
        interaction_apply.response.send_message.assert_called_once()
        self.assertIn("chế độ chỉnh sửa Mẫu Server", interaction_apply.response.send_message.call_args[0][0])


class TestGiveawayResidualFixes(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.conn = sqlite3.connect(":memory:")
        self.cur = self.conn.cursor()

        self.mock_economy = MagicMock()
        self.mock_economy.conn = self.conn
        self.mock_economy.cur = self.cur

        self.mock_bot = MagicMock()
        self.mock_bot.economy = self.mock_economy
        self.mock_bot.user = MagicMock(id=999999)
        self.mock_bot.wait_until_ready = AsyncMock()

        self.mock_guild = MagicMock(spec=discord.Guild)
        self.mock_guild.id = 111
        self.mock_guild.name = "Fixes Guild"
        self.mock_bot.get_guild = MagicMock(return_value=self.mock_guild)

        self.mock_channel = MagicMock(spec=discord.TextChannel)
        self.mock_channel.id = 1001
        self.mock_channel.send = AsyncMock()
        self.mock_guild.get_channel = MagicMock(return_value=self.mock_channel)

        self.mock_message = MagicMock(spec=discord.Message)
        self.mock_message.id = 112233
        self.mock_message.reactions = []
        self.mock_message.edit = AsyncMock()
        self.mock_channel.fetch_message = AsyncMock(return_value=self.mock_message)

        self.cog = Giveaway(self.mock_bot)

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.conn.close()

    async def test_update_and_sync_rollback_on_discord_failure(self):
        """If Discord API fails during update_and_sync_giveaway, DB state is completely rolled back."""
        msg_id = 112233
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Original Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )
        original_ga = self.cog.get_giveaway(msg_id)
        self.assertEqual(original_ga["prize"], "Original Prize")

        # Mock Discord edit to raise an error
        self.mock_message.edit.side_effect = discord.HTTPException(MagicMock(status=500), "Discord Internal Server Error")

        success, err = await self.cog.update_and_sync_giveaway(
            msg_id,
            guild_id=111,
            prize="Modified Prize",
            ended=2
        )
        self.assertFalse(success)
        self.assertIn("Lỗi cập nhật tin nhắn Discord", err)

        # Confirm DB state was rolled back to original
        rolled_back_ga = self.cog.get_giveaway(msg_id)
        self.assertEqual(rolled_back_ga["prize"], "Original Prize")
        self.assertEqual(rolled_back_ga["ended"], 0)

        # Restore mock_message.edit
        self.mock_message.edit.side_effect = None

    async def test_end_giveaway_sync_failure_reverts_state_and_suppresses_announcement(self):
        """If update_and_sync_giveaway fails when ending, end_giveaway reverts state to ended=0 and sends no winner message."""
        msg_id = 223344
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Diamond",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={}
        )

        # Mock reaction with 1 user
        mock_user = MagicMock(id=555, bot=False)
        mock_reaction = MagicMock()
        mock_reaction.emoji = "🎉"
        async def mock_users(limit=None):
            yield mock_user
        mock_reaction.users = mock_users
        self.mock_message.reactions = [mock_reaction]

        # Make Discord message edit fail during sync
        self.mock_message.edit.side_effect = discord.HTTPException(MagicMock(status=503), "Service Unavailable")

        await self.cog.end_giveaway(msg_id)

        # Confirm DB state reverted to 0 so loop can retry
        ga = self.cog.get_giveaway(msg_id)
        self.assertEqual(ga["ended"], 0)

        # Confirm winner announcement was NOT sent to channel
        self.mock_channel.send.assert_not_called()

        self.mock_message.edit.side_effect = None

    async def test_stuck_ended_3_auto_recovery(self):
        """Giveaways stuck in ended=3 recover on startup (init_db) and in giveaway_check_loop after 60s."""
        # 1. Test startup recovery in init_db
        msg_id_1 = 334455
        self.cog.save_giveaway(
            msg_id=msg_id_1,
            guild_id=111,
            channel_id=1001,
            prize="Prize 1",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )
        self.cog.economy.cur.execute("UPDATE giveaways SET ended = 3 WHERE id = ?", (msg_id_1,))
        self.cog.economy.conn.commit()
        self.assertEqual(self.cog.get_giveaway(msg_id_1)["ended"], 3)

        self.cog.init_db()
        self.assertEqual(self.cog.get_giveaway(msg_id_1)["ended"], 0)

        # 2. Test loop recovery for giveaways stuck > 60s
        msg_id_2 = 334456
        self.cog.save_giveaway(
            msg_id=msg_id_2,
            guild_id=111,
            channel_id=1001,
            prize="Prize 2",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )
        now = int(time.time())
        # Set ended = 3 with updated_at 70 seconds ago
        self.cog.economy.cur.execute("UPDATE giveaways SET ended = 3, updated_at = ? WHERE id = ?", (now - 70, msg_id_2))
        self.cog.economy.conn.commit()

        # Run one iteration of giveaway_check_loop
        await self.cog.giveaway_check_loop.coro(self.cog)
        self.assertEqual(self.cog.get_giveaway(msg_id_2)["ended"], 0)

    async def test_reaction_error_aborts_and_reverts(self):
        """API error during reaction fetching causes end_giveaway to abort and revert CAS state to 0."""
        msg_id = 445566
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Ruby",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={}
        )

        mock_reaction = MagicMock()
        mock_reaction.emoji = "🎉"
        def failing_users(limit=None):
            async def _gen():
                raise discord.HTTPException(MagicMock(status=500), "Reaction fetch error")
                yield None
            return _gen()
        mock_reaction.users = failing_users
        self.mock_message.reactions = [mock_reaction]

        await self.cog.end_giveaway(msg_id)

        # Verify state was reverted to ended=0
        ga = self.cog.get_giveaway(msg_id)
        self.assertEqual(ga["ended"], 0)
        self.mock_channel.send.assert_not_called()

    async def test_reaction_zero_participants_does_not_use_stale_db(self):
        """When reaction fetch succeeds with 0 reactions, end_giveaway does not fall back to stale DB participants."""
        msg_id = 556677
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Gold Bar",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={}
        )
        # Seed DB with stale participant
        self.cog.update_participants(msg_id, {999: 1})

        # No reactions on Discord message
        self.mock_message.reactions = []

        await self.cog.end_giveaway(msg_id)

        # Should end with 0 winners and announce no participants
        ga = self.cog.get_giveaway(msg_id)
        self.assertEqual(ga["ended"], 1)
        self.assertEqual(json.loads(ga["winners"]), [])
        self.mock_channel.send.assert_called_once()
        self.assertIn("Không có ai tham gia giveaway", self.mock_channel.send.call_args[0][0])

    async def test_reroll_uses_eligible_candidates_snapshot(self):
        """Reroll draws only from eligible_candidates snapshot and validates guild membership."""
        msg_id = 667788
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Special Car",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={}
        )

        # Set ended=1 with eligible_candidates snapshot: candidate 100 (in guild) and candidate 200 (left guild)
        extra_reqs = {
            "original_winners": [100],
            "reroll_history": [],
            "eligible_candidates": {"100": 1, "200": 1, "300": 5}
        }
        self.cog.update_giveaway_full(
            msg_id,
            ended=1,
            winners=[100],
            extra_reqs=extra_reqs
        )

        # Member 300 is present in guild, 200 is not in guild
        m300 = MagicMock(spec=discord.Member, id=300, bot=False)
        def get_member_mock(uid):
            if uid == 300:
                return m300
            return None
        self.mock_guild.get_member.side_effect = get_member_mock
        self.mock_guild.fetch_member.side_effect = discord.NotFound(MagicMock(status=404), "Member not found")

        ctx = MagicMock()
        ctx.guild = self.mock_guild
        ctx.author = MagicMock(id=123)
        ctx.author.guild = self.mock_guild
        ctx.author.guild_permissions.administrator = True
        ctx.send = AsyncMock()
        ctx.message.delete = AsyncMock()

        await self.cog.giveaway_reroll.callback(self.cog, ctx, message_id=msg_id, count=1)

        # Confirm member 300 won reroll (100 excluded as original winner, 200 excluded as left guild)
        ga = self.cog.get_giveaway(msg_id)
        new_winners = json.loads(ga["winners"])
        self.assertEqual(new_winners, [300])

        updated_reqs = json.loads(ga["extra_reqs"])
        self.assertIn(100, updated_reqs["reroll_history"])

    async def test_host_without_admin_can_edit_own_giveaway(self):
        """A giveaway host without administrator or manage_guild permissions can open the editor for their giveaway."""
        msg_id = 778899
        host_user_id = 456
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Host's Prize",
            host_id=host_user_id,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )

        ctx = MagicMock()
        ctx.guild = self.mock_guild
        ctx.author = MagicMock(spec=discord.Member, id=host_user_id)
        ctx.author.guild = self.mock_guild
        # Non-admin, non-manager
        ctx.author.guild_permissions = discord.Permissions(send_messages=True)
        ctx.send = AsyncMock()
        ctx.message.delete = AsyncMock()
        ctx.message.reference = None

        await self.cog.giveaway_edit.callback(self.cog, ctx, message_id=msg_id)

        ctx.send.assert_called_once()
        call_content = ctx.send.call_args[0][0]
        self.assertIn("Bảng Chỉnh Sửa Giveaway", call_content)
        self.assertIn(f"<@{host_user_id}>", call_content)

    async def test_occ_version_increment_and_conflict(self):
        """OCC version increments on successful update and rejects updates with mismatched expected_version."""
        msg_id = 889900
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Version Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) + 3600,
            required_roles=[],
            bonus_roles={}
        )
        ga = self.cog.get_giveaway(msg_id)
        self.assertEqual(ga.get("version", 0), 0)

        # Successful update with expected_version = 0 increments version to 1
        ok = self.cog.update_giveaway_full(msg_id, prize="Version Prize V1", expected_version=0)
        self.assertTrue(ok)
        ga1 = self.cog.get_giveaway(msg_id)
        self.assertEqual(ga1["version"], 1)

        # Stale update with expected_version = 0 fails
        ok_stale = self.cog.update_giveaway_full(msg_id, prize="Version Prize Stale", expected_version=0)
        self.assertFalse(ok_stale)
        ga_unchanged = self.cog.get_giveaway(msg_id)
        self.assertEqual(ga_unchanged["prize"], "Version Prize V1")

    async def test_locks_cleaned_up_after_end_and_cancel(self):
        """Locks in end_locks and join_locks are popped upon end_giveaway and giveaway_cancel."""
        msg_id = 990011
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Lock Test",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={}
        )
        self.mock_message.reactions = []

        await self.cog.end_giveaway(msg_id)

        # Check that locks dictionary has no residual entry
        self.assertNotIn(msg_id, self.cog.end_locks)
        self.assertNotIn(msg_id, self.cog.join_locks)


if __name__ == "__main__":
    unittest.main()


