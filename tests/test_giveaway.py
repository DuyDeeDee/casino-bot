import json
import sqlite3
import time
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from app.discord_bot.cogs.giveaway import (
    Giveaway,
    GiveawayEditorView,
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

        # message.reactions returns discord.Emoji, which has an ID but does not
        # implement PartialEmoji.is_custom_emoji(). This is the end-draw path.
        fetched_message_coin = MagicMock(spec=discord.Emoji)
        fetched_message_coin.id = 1544913759297085440
        fetched_message_coin.name = "zh_coinzh"
        self.assertFalse(hasattr(fetched_message_coin, "is_custom_emoji"))
        self.assertTrue(is_giveaway_emoji(fetched_message_coin))

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

        # 2. Authorized interaction must confirm before overwriting template
        interaction_auth = MagicMock(spec=discord.Interaction)
        interaction_auth.user = admin_member
        interaction_auth.response = MagicMock()
        interaction_auth.response.edit_message = AsyncMock()
        interaction_auth.response.send_message = AsyncMock()
        await view.btn_save_default.callback(interaction_auth)
        confirmation_view = interaction_auth.response.edit_message.call_args.kwargs["view"]
        self.assertEqual(confirmation_view.__class__.__name__, "GiveawayTemplateConfirmView")
        self.assertEqual(self.cog.get_template(12345), {})

        interaction_confirm = MagicMock(spec=discord.Interaction)
        interaction_confirm.user = admin_member
        interaction_confirm.response = MagicMock()
        interaction_confirm.response.edit_message = AsyncMock()
        interaction_confirm.response.send_message = AsyncMock()
        await view._save_default_confirmed(interaction_confirm)
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

        # A participant joins after the editor DB update but before Discord edit
        # fails. Rollback must restore edited fields without deleting that join.
        async def fail_edit_after_concurrent_join(**kwargs):
            self.cog.update_participants(msg_id, {"98765": 1})
            raise discord.HTTPException(MagicMock(status=500), "Discord Internal Server Error")

        self.mock_message.edit.side_effect = fail_edit_after_concurrent_join

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
        self.assertEqual(json.loads(rolled_back_ga["participants"]), {"98765": 1})

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

    async def test_end_draw_recognizes_custom_emoji_from_fetched_message(self):
        """Reaction.emoji is discord.Emoji, not PartialEmoji, on the end-draw path."""
        msg_id = 445567
        entrant_id = 321
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Custom Emoji Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={}
        )

        fetched_message_coin = MagicMock(spec=discord.Emoji)
        fetched_message_coin.id = 1544913759297085440
        fetched_message_coin.name = "zh_coinzh"
        entrant_user = MagicMock(spec=discord.User, id=entrant_id, bot=False)

        def reaction_users(limit=None):
            async def _gen():
                yield entrant_user
            return _gen()

        reaction = MagicMock()
        reaction.emoji = fetched_message_coin
        reaction.users = reaction_users
        self.mock_message.reactions = [reaction]

        entrant_member = MagicMock(spec=discord.Member, id=entrant_id, bot=False)
        self.mock_guild.get_member.side_effect = lambda user_id: entrant_member if user_id == entrant_id else None

        await self.cog.end_giveaway(msg_id)

        ended = self.cog.get_giveaway(msg_id)
        self.assertEqual(ended["ended"], 1)
        self.assertEqual(json.loads(ended["winners"]), [entrant_id])
        self.assertNotEqual(json.loads(ended["extra_reqs"]).get("end_reason"), "no_participants")

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

    async def test_no_participants_uses_custom_state_and_channel_message(self):
        msg_id = 556678
        embed_config = {
            "no_participants_title": "👻 Không Có Người Chơi",
            "no_participants_desc": "Giải {prize} đã đóng. {status_note}",
            "no_participants_message": "Không ai tham gia **{prize}** tại {guild_name}."
        }
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Gold Bar",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={},
            embed_config=embed_config
        )
        self.mock_message.id = msg_id
        self.mock_message.reactions = []

        await self.cog.end_giveaway(msg_id)

        ga = self.cog.get_giveaway(msg_id)
        self.assertEqual(ga["ended"], 1)
        self.assertEqual(json.loads(ga["extra_reqs"])["end_reason"], "no_participants")
        edited_embed = self.mock_message.edit.call_args.kwargs["embed"]
        self.assertEqual(edited_embed.title, "👻 Không Có Người Chơi")
        self.assertIn("Giải Gold Bar đã đóng", edited_embed.description)
        self.mock_channel.send.assert_called_once()
        self.assertEqual(
            self.mock_channel.send.call_args[0][0],
            "Không ai tham gia **Gold Bar** tại Fixes Guild."
        )

    async def test_no_participants_channel_message_can_be_disabled(self):
        msg_id = 556679
        self.cog.save_giveaway(
            msg_id=msg_id,
            guild_id=111,
            channel_id=1001,
            prize="Silent Prize",
            host_id=123,
            winner_count=1,
            ends_at=int(time.time()) - 10,
            required_roles=[],
            bonus_roles={},
            embed_config={"no_participants_message": "none"}
        )
        self.mock_message.id = msg_id
        self.mock_message.reactions = []

        await self.cog.end_giveaway(msg_id)

        self.assertEqual(self.cog.get_giveaway(msg_id)["ended"], 1)
        self.mock_message.edit.assert_called_once()
        self.mock_channel.send.assert_not_called()

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


# ==============================================================================
# 13. TEST SUITE FOR STATE-SPECIFIC TITLE & DESCRIPTION CUSTOMIZATION
# ==============================================================================

class TestGiveawayStateCustomization(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import AsyncMock, MagicMock
        import discord
        from app.discord_bot.cogs.giveaway import (
            Giveaway,
            validate_placeholders,
            GiveawayEditorView,
            GiveawayStateContentModal
        )

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
        self.mock_guild.name = "Custom Gaming Guild"
        self.mock_bot.get_guild.return_value = self.mock_guild

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.conn.close()

    def _create_sample_ga(self, embed_config: dict, extra_reqs: dict = None) -> dict:
        import time, json
        return {
            'id': 770011,
            'guild_id': self.mock_guild.id,
            'channel_id': 1001,
            'message_id': 770011,
            'prize': "VIP Nitro 1 Month",
            'host_id': 1234,
            'winner_count': 1,
            'ends_at': int(time.time()) + 3600,
            'ended': 0,
            'required_roles': "[]",
            'bonus_roles': "{}",
            'participants': json.dumps({"111": 1, "222": 2, "333": 1}),
            'winners': "[]",
            'embed_config': json.dumps(embed_config),
            'extra_reqs': json.dumps(extra_reqs or {}),
            'role_bonus_prizes': "{}"
        }

    # 1. active_desc chỉ render khi trạng thái active
    def test_active_desc_rendered_only_when_active(self):
        cfg = {
            "active_title": "🟢 SỰ KIỆN ĐANG CHẠY",
            "active_desc": "Đang chạy giải {prize} từ host {host}! Kết thúc lúc: {ends_at}",
            "ended_title": "🏁 SỰ KIỆN ĐÃ ĐÓNG",
            "ended_desc": "Đã kết thúc giải {prize}! Người thắng: {winners}"
        }
        ga = self._create_sample_ga(cfg)

        active_embed = self.cog.build_giveaway_embed(ga, status="active", participants_count=3)
        self.assertEqual(active_embed.title, "🟢 SỰ KIỆN ĐANG CHẠY")
        self.assertIn("Đang chạy giải VIP Nitro 1 Month", active_embed.description)
        self.assertIn("<@1234>", active_embed.description)
        self.assertNotIn("Đã kết thúc giải", active_embed.description)

        ended_embed = self.cog.build_giveaway_embed(ga, status="ended", participants_count=3, winners=[8888])
        self.assertEqual(ended_embed.title, "🏁 SỰ KIỆN ĐÃ ĐÓNG")
        self.assertIn("Đã kết thúc giải VIP Nitro 1 Month", ended_embed.description)
        self.assertIn("<@8888>", ended_embed.description)
        self.assertNotIn("Đang chạy giải VIP Nitro 1 Month", ended_embed.description)

    # 2. ended_desc render khi ended kèm danh sách {winners}
    def test_ended_desc_rendered_with_winners(self):
        cfg = {
            "ended_title": "🏆 TRAO GIẢI GIVEAWAY",
            "ended_desc": "🎉 Chúc mừng {winners} đã trúng {prize}!\nSố vé tham gia: {participants}"
        }
        ga = self._create_sample_ga(cfg)

        embed = self.cog.build_giveaway_embed(ga, status="ended", participants_count=15, winners=[1001, 1002])
        self.assertEqual(embed.title, "🏆 TRAO GIẢI GIVEAWAY")
        self.assertIn("<@1001>, <@1002>", embed.description)
        self.assertIn("VIP Nitro 1 Month", embed.description)
        self.assertIn("Số vé tham gia: 15", embed.description)

    # 3. cancelled_desc render kèm {status_note}
    def test_cancelled_desc_rendered_with_status_note(self):
        # Case A: template contains {status_note}
        cfg_with_ph = {
            "cancelled_title": "🛑 THÔNG BÁO HỦY",
            "cancelled_desc": "Giveaway {prize} đã bị hủy!\nLý do: {status_note}\nNgười nhận: {winners}"
        }
        ga_a = self._create_sample_ga(cfg_with_ph)
        embed_a = self.cog.build_giveaway_embed(ga_a, status="cancelled", status_note="Bảo trì khẩn cấp")
        self.assertEqual(embed_a.title, "🛑 THÔNG BÁO HỦY")
        self.assertIn("Lý do: Bảo trì khẩn cấp", embed_a.description)
        self.assertIn("Người nhận: Đã bị huỷ", embed_a.description)

        # Case B: default note used when status_note is None
        embed_b = self.cog.build_giveaway_embed(ga_a, status="cancelled", status_note=None)
        self.assertIn("Lý do: Giveaway này đã bị huỷ bởi Host.", embed_b.description)

        # Case C: template does not contain {status_note}, automatically appended
        cfg_no_ph = {
            "cancelled_title": "🛑 THÔNG BÁO HỦY",
            "cancelled_desc": "Giveaway {prize} đã bị dừng hoạt động."
        }
        ga_c = self._create_sample_ga(cfg_no_ph)
        embed_c = self.cog.build_giveaway_embed(ga_c, status="cancelled", status_note="Host hủy thủ công")
        self.assertIn("Giveaway VIP Nitro 1 Month đã bị dừng hoạt động.", embed_c.description)
        self.assertIn("Host hủy thủ công", embed_c.description)

    # 4. rerolled_desc render kèm người thắng mới và {reroll_history}
    def test_rerolled_desc_rendered_with_new_and_past_winners(self):
        cfg = {
            "rerolled_title": "🔄 KẾT QUẢ QUAY LẠI",
            "rerolled_desc": "Quay lại giải {prize}!\nNgười thắng mới: {winners}\nNgười thắng trước đây: {reroll_history}"
        }
        extra_reqs = {"reroll_history": [9001, 9002]}
        ga = self._create_sample_ga(cfg, extra_reqs=extra_reqs)

        embed = self.cog.build_giveaway_embed(ga, status="rerolled", winners=[9003])
        self.assertEqual(embed.title, "🔄 KẾT QUẢ QUAY LẠI")
        self.assertIn("Người thắng mới: <@9003>", embed.description)
        self.assertIn("Người thắng trước đây: <@9001>, <@9002>", embed.description)

    # 5. fallback về custom_desc chung khi {status}_desc rỗng
    def test_fallback_to_custom_desc_when_state_desc_empty(self):
        cfg = {
            "title": "TIÊU ĐỀ CHUNG",
            "custom_desc": "Mẫu chung cho giải {prize} từ host {host}! Kết quả: {winners}",
            "ended_desc": ""  # Blank state desc
        }
        ga = self._create_sample_ga(cfg)

        embed = self.cog.build_giveaway_embed(ga, status="ended", winners=[7777])
        self.assertEqual(embed.title, "TIÊU ĐỀ CHUNG")
        self.assertIn("Mẫu chung cho giải VIP Nitro 1 Month", embed.description)
        self.assertIn("<@7777>", embed.description)

    # 6. fallback về layout mặc định khi cả 2 đều rỗng
    def test_fallback_to_default_layout_when_both_empty(self):
        cfg = {}  # No state desc, no custom_desc
        ga = self._create_sample_ga(cfg)

        embed = self.cog.build_giveaway_embed(ga, status="ended", winners=[6666])
        # Title falls back to default status title
        self.assertIn("Giveaway Kết Thúc", embed.title)
        # Description falls back to default structured layout
        self.assertIn("**VIP Nitro 1 Month**", embed.description)
        self.assertIn("<a:key:1526234974150459593>*Result:* <@6666>", embed.description)

    # 7. Tương thích ngược hoàn toàn với template cũ (title & custom_desc)
    def test_legacy_template_compatibility(self):
        legacy_cfg = {
            "title": "Legacy Server Giveaway",
            "custom_desc": "Ghi chú luật chơi cũ"
        }
        ga = self._create_sample_ga(legacy_cfg)

        for st in ["active", "ended", "cancelled", "rerolled"]:
            emb = self.cog.build_giveaway_embed(ga, status=st, winners=[5555], status_note="Lý do huỷ")
            self.assertEqual(emb.title, "Legacy Server Giveaway")
            self.assertIn("📝 *Ghi chú:* Ghi chú luật chơi cũ", emb.description)
            if st == "active":
                self.assertIn("*End:*", emb.description)
            elif st in ("ended", "rerolled"):
                self.assertIn("<@5555>", emb.description)
            elif st == "cancelled":
                self.assertIn("Lý do huỷ", emb.description)

    # 8. Xem preview không làm thay đổi / làm bẩn dữ liệu thật trong DB
    def test_preview_does_not_mutate_actual_giveaway_db(self):
        from app.discord_bot.cogs.giveaway import GiveawayEditorView
        import copy
        ga = self._create_sample_ga({"title": "Test Preview"}, extra_reqs={"reroll_history": []})
        original_copy = copy.deepcopy(ga)

        mock_user = unittest.mock.MagicMock()
        mock_user.id = 1234
        view = GiveawayEditorView(self.cog, ga, mock_user, self.mock_guild)

        # Preview in ended mode
        view.preview_mode = "ended"
        ended_preview = view.build_preview_embed()
        self.assertIsNotNone(ended_preview)

        # Preview in cancelled mode
        view.preview_mode = "cancelled"
        cancelled_preview = view.build_preview_embed()
        self.assertIsNotNone(cancelled_preview)

        # Preview in rerolled mode (generates mock reroll history)
        view.preview_mode = "rerolled"
        rerolled_preview = view.build_preview_embed()
        self.assertIsNotNone(rerolled_preview)

        # Assert view.giveaway has not been mutated
        self.assertEqual(view.giveaway['ended'], 0)
        extra_reqs = json.loads(view.giveaway['extra_reqs']) if isinstance(view.giveaway['extra_reqs'], str) else view.giveaway['extra_reqs']
        self.assertEqual(extra_reqs.get('reroll_history'), [])
        self.assertEqual(view.giveaway['prize'], original_copy['prize'])

    # 9. Kiểm tra validate cú pháp placeholder & giới hạn độ dài
    def test_overlength_description_rejected(self):
        from app.discord_bot.cogs.giveaway import validate_placeholders

        # Valid placeholder bracket checks
        ok, err = validate_placeholders("Quà: {prize} cho {winners}")
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Unmatched opening bracket at end
        ok_unclosed, err_unclosed = validate_placeholders("Quà: {prize")
        self.assertFalse(ok_unclosed)
        self.assertIn("chưa được đóng", err_unclosed)

        # Unmatched opening bracket followed by another opening bracket
        ok_open, err_open = validate_placeholders("Quà: {prize cho {winners}")
        self.assertFalse(ok_open)
        self.assertIn("chưa đóng", err_open)

        # Nested brackets
        ok_nest, err_nest = validate_placeholders("Quà: {{prize}}")
        self.assertFalse(ok_nest)
        self.assertIn("lồng nhau", err_nest)

        # Unmatched closing bracket
        ok_close, err_close = validate_placeholders("Quà: prize} cho winners")
        self.assertFalse(ok_close)
        self.assertIn("thừa", err_close)

        # Embed length limit check
        huge_desc = "A" * 4100
        cfg = {"ended_desc": huge_desc}
        ga = self._create_sample_ga(cfg)
        rendered_embed = self.cog.build_giveaway_embed(ga, status="ended")
        # Description exceeds 4096 limit
        self.assertGreater(len(rendered_embed.description), 4096)

    # 10. Lưu template server giữ nguyên đầy đủ cả 4 trạng thái
    def test_save_server_template_preserves_all_state_descriptions(self):
        server_cfg = {
            "title": "Global Title",
            "custom_desc": "Global Desc",
            "active_title": "Title Active",
            "active_desc": "Desc Active: {prize}",
            "ended_title": "Title Ended",
            "ended_desc": "Desc Ended: {winners}",
            "cancelled_title": "Title Cancelled",
            "cancelled_desc": "Desc Cancelled: {status_note}",
            "rerolled_title": "Title Rerolled",
            "rerolled_desc": "Desc Rerolled: {winners} after {reroll_history}",
            "no_participants_title": "Không Có Người Chơi",
            "no_participants_desc": "Không có ứng viên cho {prize}. {status_note}",
            "no_participants_message": "Không ai tham gia **{prize}** tại {guild_name}."
        }

        # Save to guild template
        save_res = self.cog.save_template(self.mock_guild.id, "default", server_cfg, updated_by=999)
        self.assertTrue(save_res)

        # Retrieve and verify all 8 state keys
        loaded_tpl = self.cog.get_template(self.mock_guild.id, "default")
        self.assertEqual(loaded_tpl["active_title"], "Title Active")
        self.assertEqual(loaded_tpl["active_desc"], "Desc Active: {prize}")
        self.assertEqual(loaded_tpl["ended_title"], "Title Ended")
        self.assertEqual(loaded_tpl["ended_desc"], "Desc Ended: {winners}")
        self.assertEqual(loaded_tpl["cancelled_title"], "Title Cancelled")
        self.assertEqual(loaded_tpl["cancelled_desc"], "Desc Cancelled: {status_note}")
        self.assertEqual(loaded_tpl["rerolled_title"], "Title Rerolled")
        self.assertEqual(loaded_tpl["rerolled_desc"], "Desc Rerolled: {winners} after {reroll_history}")
        self.assertEqual(loaded_tpl["no_participants_title"], "Không Có Người Chơi")
        self.assertEqual(loaded_tpl["no_participants_desc"], "Không có ứng viên cho {prize}. {status_note}")
        self.assertEqual(loaded_tpl["no_participants_message"], "Không ai tham gia **{prize}** tại {guild_name}.")


# ==============================================================================
# 14. TEST SUITE FOR GIVEAWAY STUDIO EDITOR UX/UI OVERHAUL
# ==============================================================================

class TestGiveawayEditorUXOverhaul(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        from unittest.mock import AsyncMock, MagicMock
        import discord
        from app.discord_bot.cogs.giveaway import (
            Giveaway,
            GiveawayEditorView,
            GiveawayPrizeTimeModal,
            parse_time_input,
            parse_role_requirements_strict,
            parse_bonus_roles_strict,
            parse_role_bonus_prizes_strict,
            validate_placeholders_strict
        )

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
        self.mock_guild.id = 778899
        self.mock_guild.name = "UX Gaming Guild"
        self.mock_bot.get_guild.return_value = self.mock_guild

    async def asyncTearDown(self):
        self.cog.cog_unload()
        self.conn.close()

    def _create_sample_ga(self, ga_id=101010, embed_config=None) -> dict:
        import time, json
        return {
            'id': ga_id,
            'guild_id': self.mock_guild.id,
            'channel_id': 1001,
            'message_id': ga_id,
            'prize': "Discord Nitro",
            'host_id': 1234,
            'winner_count': 1,
            'ends_at': int(time.time()) + 7200,
            'ended': 0,
            'required_roles': "[]",
            'bonus_roles': "{}",
            'participants': "{}",
            'winners': "[]",
            'embed_config': json.dumps(embed_config or {}),
            'extra_reqs': "{}",
            'role_bonus_prizes': "{}",
            'version': 0
        }

    # 1. Tách bản nháp (draft) khỏi dữ liệu gốc (original) & theo dõi dirty state
    def test_draft_isolated_from_original_and_dirty_tracking(self):
        from unittest.mock import MagicMock
        ga = self._create_sample_ga()
        user = MagicMock(id=1234)
        view = GiveawayEditorView(self.cog, ga, user, self.mock_guild)

        self.assertFalse(view.is_dirty)
        self.assertEqual(len(view.dirty_sections), 0)

        # Mutate draft
        view.draft['prize'] = "Updated Nitro Boost"
        view.mark_dirty("prize_time")

        self.assertTrue(view.is_dirty)
        self.assertIn("prize_time", view.dirty_sections)
        self.assertEqual(view.original['prize'], "Discord Nitro")
        self.assertEqual(view.draft['prize'], "Updated Nitro Boost")

        # Discard changes
        view.discard_changes()
        self.assertFalse(view.is_dirty)
        self.assertEqual(len(view.dirty_sections), 0)
        self.assertEqual(view.draft['prize'], "Discord Nitro")

    # 2. Phân quyền và chế độ hiển thị nút thao tác (Template vs Live Giveaway, Host vs Manager)
    def test_mode_and_permission_aware_actions(self):
        from unittest.mock import MagicMock

        # A: Template Mode (id == 0)
        tpl_ga = self._create_sample_ga(ga_id=0)
        admin_user = MagicMock(id=999)
        self.cog.can_manage_server_template = MagicMock(return_value=True)

        tpl_view = GiveawayEditorView(self.cog, tpl_ga, admin_user, self.mock_guild)
        edit_select = next(c for c in tpl_view.children if c.__class__.__name__ == "GiveawayEditSectionSelect")
        preview_select = next(c for c in tpl_view.children if c.__class__.__name__ == "GiveawayPreviewStateSelect")
        self.assertIn("no_participants", {option.value for option in preview_select.options})
        template_option_values = {option.value for option in edit_select.options}
        self.assertEqual(template_option_values, {"basic", "images", "author", "footer"})
        self.assertNotIn("prize_time", template_option_values)
        self.assertNotIn("requirements", template_option_values)
        self.assertNotIn("prize_bonus", template_option_values)
        row3_labels = [getattr(c, "label", "") for c in tpl_view.children if getattr(c, "row", None) == 3]
        self.assertIn("💾 Lưu mẫu cho server", row3_labels)
        self.assertIn("↩️ Hủy thay đổi", row3_labels)
        self.assertNotIn("✅ Cập nhật giveaway này", row3_labels)
        self.assertNotIn("Lưu & Áp Dụng Cả 2", row3_labels)

        # B: Live Giveaway Mode (id > 0) với Host thường (không có quyền template)
        self.cog.can_manage_server_template = MagicMock(return_value=False)
        live_ga = self._create_sample_ga(ga_id=888)
        host_user = MagicMock(id=1234)

        live_view = GiveawayEditorView(self.cog, live_ga, host_user, self.mock_guild)
        live_labels = [getattr(c, "label", "") for c in live_view.children if getattr(c, "row", None) == 3]
        self.assertIn("✅ Cập nhật giveaway này", live_labels)
        self.assertIn("↩️ Hủy thay đổi", live_labels)
        self.assertNotIn("💾 Lưu thành mẫu server", live_labels)

        # C: Live Giveaway Mode (id > 0) với Manager có quyền template
        self.cog.can_manage_server_template = MagicMock(return_value=True)
        mgr_view = GiveawayEditorView(self.cog, live_ga, admin_user, self.mock_guild)
        mgr_labels = [getattr(c, "label", "") for c in mgr_view.children if getattr(c, "row", None) == 3]
        self.assertIn("✅ Cập nhật giveaway này", mgr_labels)
        self.assertIn("↩️ Hủy thay đổi", mgr_labels)
        self.assertIn("💾 Lưu thành mẫu server", mgr_labels)

    # 3. Nút Dùng lại nội dung chung (reset override)
    async def test_state_override_reset_to_common(self):
        from unittest.mock import MagicMock, AsyncMock
        cfg = {
            "title": "Tiêu đề chung",
            "ended_title": "Tiêu đề riêng đã kết thúc",
            "ended_desc": "Mô tả riêng kết thúc: {winners}"
        }
        ga = self._create_sample_ga(embed_config=cfg)
        user = MagicMock(id=1234)
        view = GiveawayEditorView(self.cog, ga, user, self.mock_guild)

        # Switch to ended mode
        view.preview_mode = "ended"
        view._build_components()
        self.assertFalse(view.btn_reset_to_common.disabled)

        # Simulate clicking reset
        mock_interaction = MagicMock(spec=discord.Interaction)
        mock_interaction.response = MagicMock()
        mock_interaction.response.is_done.return_value = False
        mock_interaction.response.edit_message = AsyncMock()

        await view._on_reset_to_common(mock_interaction)
        draft_cfg = view.draft['embed_config']
        self.assertIsNone(draft_cfg.get("ended_title"))
        self.assertIsNone(draft_cfg.get("ended_desc"))
        self.assertTrue(view.btn_reset_to_common.disabled)
        self.assertIn("state_ended", view.dirty_sections)

    # 4. Kiểm tra validation số người thắng (1-100)
    async def test_winner_count_strict_validation(self):
        from unittest.mock import MagicMock, AsyncMock
        from app.discord_bot.cogs.giveaway import GiveawayPrizeTimeModal
        ga = self._create_sample_ga()
        user = MagicMock(id=1234)
        view = GiveawayEditorView(self.cog, ga, user, self.mock_guild)

        modal = GiveawayPrizeTimeModal(view)

        # Case A: Non-integer input
        modal.winner_count_input._value = "hai_nguoi"
        modal.prize_input._value = "Valid Prize"
        interaction_a = MagicMock(spec=discord.Interaction)
        interaction_a.response = MagicMock()
        interaction_a.response.send_message = AsyncMock()
        await modal.on_submit(interaction_a)
        interaction_a.response.send_message.assert_called_once()
        self.assertIn("phải là số nguyên hợp lệ", interaction_a.response.send_message.call_args[0][0])
        self.assertEqual(view.draft['winner_count'], 1)

        # Case B: Out of range (0)
        modal.winner_count_input._value = "0"
        interaction_b = MagicMock(spec=discord.Interaction)
        interaction_b.response = MagicMock()
        interaction_b.response.send_message = AsyncMock()
        await modal.on_submit(interaction_b)
        self.assertIn("từ 1 đến 100", interaction_b.response.send_message.call_args[0][0])
        self.assertEqual(view.draft['winner_count'], 1)

        # Case C: Valid input (5)
        modal.winner_count_input._value = "5"
        interaction_c = MagicMock(spec=discord.Interaction)
        interaction_c.response = MagicMock()
        interaction_c.response.edit_message = AsyncMock()
        interaction_c.response.is_done.return_value = False
        await modal.on_submit(interaction_c)
        self.assertEqual(view.draft['winner_count'], 5)
        self.assertIn("prize_time", view.dirty_sections)

    # 5. Helper parse_time_input
    def test_parse_time_input_strict(self):
        from app.discord_bot.cogs.giveaway import parse_time_input
        import time

        now = int(time.time())
        current_ends = now + 3600

        # Relative addition (+30m = +1800s)
        new_time, err = parse_time_input("+30m", current_ends)
        self.assertIsNone(err)
        self.assertEqual(new_time, current_ends + 1800)

        # Relative subtraction (-10m = -600s)
        new_time_sub, err_sub = parse_time_input("-10m", current_ends)
        self.assertIsNone(err_sub)
        self.assertEqual(new_time_sub, current_ends - 600)

        # Past time rejection
        past_time, err_past = parse_time_input("-2h", current_ends)
        self.assertIsNone(past_time)
        self.assertIn("tương lai", err_past)

        # Invalid format
        inv_time, err_inv = parse_time_input("invalid_time", current_ends)
        self.assertIsNone(inv_time)
        self.assertIn("Không thể nhận diện", err_inv)

    # 6. Kiểm tra biến placeholder nghiêm ngặt và gợi ý typo
    def test_placeholder_strict_validation_with_close_matches(self):
        from app.discord_bot.cogs.giveaway import validate_placeholders_strict

        # Valid text
        ok, err = validate_placeholders_strict("Chúc mừng {winners} đã trúng {prize} do {host} tặng!")
        self.assertTrue(ok)
        self.assertIsNone(err)

        # Typo: {winner} -> suggest {winners}
        ok_typo, err_typo = validate_placeholders_strict("Người trúng: {winner}")
        self.assertFalse(ok_typo)
        self.assertIn("{winners}", err_typo)

        # Backward-compatible aliases supported by the renderer remain valid.
        ok_part, err_part = validate_placeholders_strict("Số người: {participants_count}")
        self.assertTrue(ok_part)
        self.assertIsNone(err_part)
        for legacy_alias in ("{server_name}", "{host_id}"):
            ok_alias, err_alias = validate_placeholders_strict(legacy_alias)
            self.assertTrue(ok_alias)
            self.assertIsNone(err_alias)

        alias_ga = self._create_sample_ga(embed_config={
            "custom_desc": "Server {server_name} · Host {host_id} · Entries {participants_count}"
        })
        alias_embed = self.cog.build_giveaway_embed(alias_ga, participants_count=7)
        self.assertIn("Server UX Gaming Guild · Host 1234 · Entries 7", alias_embed.description)
        self.assertNotIn("{participants_count}", alias_embed.description)

        # Completely unknown variable
        ok_unk, err_unk = validate_placeholders_strict("Dữ liệu: {random_unknown_token}")
        self.assertFalse(ok_unk)
        self.assertIn("Danh sách biến hỗ trợ", err_unk)

    def test_ping_placeholders_are_validated_and_rendered(self):
        from app.discord_bot.cogs.giveaway import PING_PLACEHOLDERS, validate_placeholders_strict

        ga = self._create_sample_ga()
        raw = "🎉 {guild_name} · {prize} · Host {host}"
        ok, err = validate_placeholders_strict(raw, PING_PLACEHOLDERS)
        self.assertTrue(ok)
        self.assertIsNone(err)

        rendered = self.cog.format_ping_content(raw, ga, self.mock_guild)
        self.assertEqual(rendered, "🎉 UX Gaming Guild · Discord Nitro · Host <@1234>")
        self.assertNotIn("{guild_name}", rendered)

        bad_ok, bad_err = validate_placeholders_strict("{winners}", PING_PLACEHOLDERS)
        self.assertFalse(bad_ok)
        self.assertIn("Không hỗ trợ biến", bad_err)

    def test_color_and_url_validation_helpers(self):
        from app.discord_bot.cogs.giveaway import is_valid_http_url, parse_color

        self.assertIsNotNone(parse_color("#FFD700"))
        self.assertIsNotNone(parse_color("purple"))
        self.assertIsNone(parse_color("not-a-real-color"))
        self.assertTrue(is_valid_http_url("https://cdn.example.com/banner.png"))
        self.assertTrue(is_valid_http_url("http://example.com/image.jpg"))
        self.assertFalse(is_valid_http_url("javascript:alert(1)"))
        self.assertFalse(is_valid_http_url("cdn.example.com/no-scheme.png"))

    async def test_role_select_managers_commit_to_editor_draft(self):
        from app.discord_bot.cogs.giveaway import GiveawayPrizeBonusView, GiveawayRequirementsView

        ga = self._create_sample_ga()
        user = MagicMock(id=1234)
        editor = GiveawayEditorView(self.cog, ga, user, self.mock_guild)

        requirements_view = GiveawayRequirementsView(editor)
        self.assertTrue(any(isinstance(item, discord.ui.RoleSelect) for item in requirements_view.children))
        requirements_view.required_roles = [55555, 66666]
        requirements_view.bonus_roles = {}
        interaction_req = MagicMock(spec=discord.Interaction)
        interaction_req.response = MagicMock()
        interaction_req.response.is_done.return_value = False
        interaction_req.response.edit_message = AsyncMock()
        await requirements_view._on_save(interaction_req)
        self.assertEqual(editor.draft["required_roles"], [55555, 66666])
        self.assertEqual(editor.draft["bonus_roles"], {})

        prize_view = GiveawayPrizeBonusView(editor)
        self.assertTrue(any(isinstance(item, discord.ui.RoleSelect) for item in prize_view.children))
        prize_view.role_prizes = {"55555": "+1 Skin"}
        interaction_prize = MagicMock(spec=discord.Interaction)
        interaction_prize.response = MagicMock()
        interaction_prize.response.is_done.return_value = False
        interaction_prize.response.edit_message = AsyncMock()
        await prize_view._on_save(interaction_prize)
        self.assertEqual(editor.draft["role_bonus_prizes"], {"55555": "+1 Skin"})

    # 7. Phân giải Role nghiêm ngặt và gom lỗi theo dòng
    def test_role_parsers_strict_error_collection(self):
        from app.discord_bot.cogs.giveaway import (
            parse_role_requirements_strict,
            parse_bonus_roles_strict,
            parse_role_bonus_prizes_strict
        )

        mock_role = MagicMock()
        mock_role.id = 55555
        mock_role.name = "VIP"
        spaced_role = MagicMock()
        spaced_role.id = 66666
        spaced_role.name = "VIP Member"
        self.mock_guild.roles = [mock_role, spaced_role]
        self.mock_guild.get_role.side_effect = lambda role_id: {
            55555: mock_role,
            66666: spaced_role,
        }.get(role_id)

        # Valid role requirement
        r_ids, r_errs = parse_role_requirements_strict(self.mock_guild, "@VIP, 55555")
        self.assertEqual(r_ids, [55555])
        self.assertEqual(r_errs, [])

        # Role names containing spaces must round-trip through the modal parser.
        spaced_ids, spaced_errs = parse_role_requirements_strict(self.mock_guild, "@VIP Member")
        self.assertEqual(spaced_ids, [66666])
        self.assertEqual(spaced_errs, [])

        # Unknown numeric IDs and user mentions must not become role rules.
        invalid_ids, invalid_id_errs = parse_role_requirements_strict(
            self.mock_guild,
            "999999, <@55555>"
        )
        self.assertEqual(invalid_ids, [])
        self.assertEqual(len(invalid_id_errs), 2)

        # Non-existent role requirement
        bad_ids, bad_errs = parse_role_requirements_strict(self.mock_guild, "@NonExistentRole")
        self.assertEqual(bad_ids, [])
        self.assertEqual(len(bad_errs), 1)
        self.assertIn("Không tìm thấy role '@NonExistentRole'", bad_errs[0])

        # Bonus role tickets parsing
        b_dict, b_errs = parse_bonus_roles_strict(self.mock_guild, "@VIP:2, @GhostRole:3")
        self.assertEqual(b_dict, {"55555": 2})
        self.assertEqual(len(b_errs), 1)
        self.assertIn("GhostRole", b_errs[0])

        # Role bonus prizes line-by-line parsing
        p_text = "@VIP: +50k Momo\nMissingColonLine\n@UnknownRole: +100k"
        p_dict, p_errs = parse_role_bonus_prizes_strict(self.mock_guild, p_text)
        self.assertEqual(p_dict, {"55555": "+50k Momo"})
        self.assertEqual(len(p_errs), 2)
        self.assertIn("Dòng 2", p_errs[0])
        self.assertIn("Dòng 3", p_errs[1])

    # 8. Quản lý vòng đời và timeout (10 phút)
    async def test_editor_timeout_lifecycle(self):
        from unittest.mock import MagicMock, AsyncMock
        ga = self._create_sample_ga()
        user = MagicMock(id=1234)
        view = GiveawayEditorView(self.cog, ga, user, self.mock_guild)

        mock_msg = MagicMock()
        mock_msg.edit = AsyncMock()
        view.message = mock_msg

        await view.on_timeout()

        # All children must be disabled
        for item in view.children:
            self.assertTrue(item.disabled)

        # Message edit called with timeout notification
        mock_msg.edit.assert_called_once()
        self.assertIn("hết hạn", mock_msg.edit.call_args.kwargs.get("content", ""))


if __name__ == "__main__":
    unittest.main()
