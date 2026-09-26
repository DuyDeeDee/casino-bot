import asyncio
import json
import time
import sqlite3
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from app.discord_bot.modules import economy as economy_module
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.masoi_engine import ActionKind, Faction, GamePhase, Role
from app.discord_bot.modules.masoi_state import restore_game, snapshot_game
from app.discord_bot.modules.masoi_rank import MasoiRankService
from app.discord_bot.cogs import masoi
from tests.test_masoi_cog import make_cog
from tests.test_masoi_engine import make_game, submit


class SnapshotTests(unittest.TestCase):
    def test_json_roundtrip_preserves_actions_results_roles_and_permissions(self):
        game = make_game(Role.WOLF, Role.WITCH, Role.VILLAGER)
        game.channel_permission_snapshots = {1: None, 2: discord.PermissionOverwrite(view_channel=False, send_messages=True)}
        submit(game, 1, ActionKind.WOLF_VOTE, 3)
        game.resolve_night()
        restored = restore_game(json.loads(json.dumps(snapshot_game(game))))
        self.assertEqual(restored.rank_match_id, game.rank_match_id)
        self.assertEqual(restored._night_result, game._night_result)
        self.assertEqual(restored.players[1].role, Role.WOLF)
        self.assertFalse(restored.players[3].is_alive)
        self.assertEqual(restored.channel_permission_snapshots, game.channel_permission_snapshots)
        self.assertEqual(restored.replay_logs[-1].night, game.night_count)
        self.assertEqual(restored.night_deadline, 0)
        self.assertFalse(restored.accepts_night_actions(restored.night_count))

    def test_snapshot_does_not_include_live_discord_objects(self):
        game = make_game(Role.WITCH)
        game.witch_dm_message = object()
        game.witch_view = object()
        game.cog = object()
        payload = json.dumps(snapshot_game(game))
        self.assertNotIn("witch_dm_message", payload)
        self.assertNotIn("witch_view", payload)

    def test_unknown_version_fails_closed(self):
        with self.assertRaises(ValueError):
            restore_game({"version": 999})


class RecoveryTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        path = Path(self.temp.name) / "recovery.db"
        sqlite3.connect(path).close()
        self.patch = patch.object(economy_module, "DATABASE_PATH", path)
        self.patch.start()
        self.eco = Economy()
        self.game = make_game(Role.WOLF, Role.VILLAGER)
        self.cog = make_cog(self.game)
        self.cog.active_games = {}
        self.cog.get_economy.return_value = self.eco
        self.cog._persistence_enabled = True
        self.cog._recovering_channels = set()
        self.channel = Mock(spec=discord.TextChannel)
        self.channel.guild = SimpleNamespace(id=1, get_member=Mock(return_value=object()))
        self.channel.set_permissions = AsyncMock()
        self.channel.send = AsyncMock()
        self.channel.fetch_message = AsyncMock(return_value=SimpleNamespace(edit=AsyncMock()))
        self.cog.bot.get_channel = Mock(return_value=self.channel)

    def tearDown(self):
        self.eco.conn.close()
        self.patch.stop()
        self.temp.cleanup()

    async def test_interrupted_game_restores_permissions_without_changing_rank(self):
        self.game.channel_permission_snapshots[2] = discord.PermissionOverwrite(send_messages=True, attach_files=False)
        self.cog.checkpoint_game(self.game)
        await self.cog.recover_pending_games()
        self.channel.set_permissions.assert_awaited_once()
        overwrite = self.channel.set_permissions.call_args.kwargs["overwrite"]
        self.assertTrue(overwrite.send_messages)
        self.assertFalse(overwrite.attach_files)
        self.assertEqual(self.eco.get_masoi_sessions(), [])
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 0)
        self.eco.cur.execute("SELECT count(*) FROM masoi_match_history")
        self.assertEqual(self.eco.cur.fetchone()[0], 1)
        self.assertFalse(self.cog._recovering_channels)

    async def test_load_blocks_pending_channels_before_worker_can_start(self):
        self.cog.checkpoint_game(self.game)
        gate = asyncio.Event()
        self.cog.bot.wait_until_ready = AsyncMock(side_effect=gate.wait)
        await self.cog.cog_load()
        try:
            self.assertTrue(self.cog._recovery_ready)
            self.assertIn("1-2", self.cog._recovering_channels)
            await asyncio.sleep(0)
            self.channel.send.assert_not_awaited()
        finally:
            await self.cog.cog_unload()
        self.assertTrue(self.cog._recovery_task.cancelled())
        self.assertEqual(len(self.eco.get_masoi_sessions()), 1)

    async def test_unload_checkpoints_and_cancels_running_match_task(self):
        self.cog.active_games["1-2"] = self.game
        task = asyncio.create_task(asyncio.Event().wait())
        self.cog._game_tasks = {self.game.rank_match_id: task}
        await self.cog.cog_unload()
        self.assertTrue(task.cancelled())
        self.assertEqual(len(self.eco.get_masoi_sessions()), 1)
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 0)

    async def test_complete_loop_settles_once_restores_permissions_and_archives(self):
        game = make_game(Role.WOLF, Role.WITCH, Role.VILLAGER)
        game.settings.night_time = 0
        original_start = game.start_night
        def start_with_actions():
            original_start()
            game.night_deadline = time.monotonic() + 10
            submit(game, 1, ActionKind.WOLF_VOTE, 2)
            game.night_deadline = 0
        game.start_night = start_with_actions
        self.cog.active_games["1-2"] = game
        self.cog.attach_checkpoint(game)
        self.channel.overwrites = {}
        message = SimpleNamespace(channel=self.channel)
        notice = SimpleNamespace(delete=AsyncMock())
        with patch.object(masoi, "_safe_send", AsyncMock(return_value=notice)):
            await self.cog.game_loop(game, message)
        self.assertTrue(game.rank_settled)
        self.assertTrue(game.result_announced)
        self.assertFalse(game.channel_permission_snapshots)
        self.assertEqual(self.eco.get_masoi_sessions(), [])
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["plays"], 1)
        self.assertEqual(self.eco.get_masoi_rank_stats(2, "VILLAGER")["points"], -15)
        self.eco.cur.execute("SELECT count(*) FROM masoi_match_history")
        self.assertEqual(self.eco.cur.fetchone()[0], 1)
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["plays"], 1)
        self.assertFalse(self.cog._recovering_channels)

    async def test_completed_result_retries_once_with_original_match_id(self):
        self.game.winner_faction = Faction.WEREWOLF
        self.cog.checkpoint_game(self.game)
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["points"], 20)
        self.assertEqual(self.eco.get_masoi_rank_stats(2, "VILLAGER")["points"], -15)
        # Simulate a crash after commit but before retiring the original snapshot.
        self.cog.checkpoint_game(self.game)
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_rank_stats(1, "WOLF")["plays"], 1)
        self.assertEqual(self.eco.get_masoi_sessions(), [])

    async def test_restore_failure_keeps_snapshot_and_blocks_channel_until_retry(self):
        self.game.channel_permission_snapshots[2] = None
        self.cog.checkpoint_game(self.game)
        self.channel.set_permissions.side_effect = RuntimeError("missing permissions")
        with self.assertLogs("app.discord_bot.cogs.masoi", level="WARNING"):
            await self.cog.recover_pending_games()
        self.assertEqual(len(self.eco.get_masoi_sessions()), 1)
        self.assertIn("1-2", self.cog._recovering_channels)
        self.channel.set_permissions.side_effect = None
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_sessions(), [])

    async def test_partial_restore_persists_only_unrestored_members(self):
        self.game.channel_permission_snapshots = {1: None, 2: None}
        self.cog.checkpoint_game(self.game)
        self.channel.set_permissions.side_effect = [None, RuntimeError("offline")]
        with self.assertLogs("app.discord_bot.cogs.masoi", level="WARNING"):
            await self.cog.recover_pending_games()
        state = json.loads(self.eco.get_masoi_sessions()[0]["state_json"])
        self.assertEqual([entry["user_id"] for entry in state["permissions"]], [2])

    async def test_active_owner_is_never_recovered_underneath_live_match(self):
        self.cog.checkpoint_game(self.game)
        self.cog.active_games["1-2"] = self.game
        await self.cog.recover_pending_games()
        self.channel.send.assert_not_awaited()
        self.assertEqual(len(self.eco.get_masoi_sessions()), 1)

    async def test_bad_snapshot_is_retained_and_channel_stays_blocked(self):
        state = snapshot_game(self.game)
        state["version"] = 999
        self.eco.save_masoi_session(state)
        with self.assertLogs("app.discord_bot.modules.masoi_recovery", level="ERROR"):
            await self.cog.recover_pending_games()
        self.assertEqual(len(self.eco.get_masoi_sessions()), 1)
        self.assertIn("1-2", self.cog._recovering_channels)
        self.channel.send.assert_not_awaited()

    async def test_deleted_channel_does_not_block_recovery_forever(self):
        self.game.channel_permission_snapshots[1] = None
        self.cog.checkpoint_game(self.game)
        self.cog.bot.get_channel.return_value = None
        self.cog.bot.fetch_channel = AsyncMock(side_effect=discord.NotFound(SimpleNamespace(status=404, reason="Not found"), "deleted"))
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_sessions(), [])
        self.assertFalse(self.cog._recovering_channels)

    async def test_rank_commit_failure_keeps_completed_result_for_retry(self):
        self.game.winner_faction = Faction.WEREWOLF
        self.cog.checkpoint_game(self.game)
        with patch.object(self.eco, "settle_masoi_match", side_effect=RuntimeError("offline")):
            with self.assertLogs("app.discord_bot.modules.masoi_recovery", level="ERROR"):
                await self.cog.recover_pending_games()
        self.assertEqual(len(self.eco.get_masoi_sessions()), 1)
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 0)
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 1)

    async def test_checkpoint_is_written_before_discord_mute(self):
        self.game.players[2].is_alive = False
        self.channel.overwrites = {}
        async def verify_persisted(*args, **kwargs):
            state = json.loads(self.eco.get_masoi_sessions()[0]["state_json"])
            self.assertEqual(state["permissions"], [{"user_id": 2, "overwrite": None}])
        self.channel.set_permissions.side_effect = verify_persisted
        await self.cog.sync_channel_permissions(self.game, self.channel)
        self.channel.set_permissions.assert_awaited_once()

    async def test_db_failure_prevents_mutating_discord_permissions(self):
        self.game.players[2].is_alive = False
        self.channel.overwrites = {}
        with patch.object(self.eco, "save_masoi_session", side_effect=RuntimeError("disk full")):
            with self.assertLogs("app.discord_bot.cogs.masoi", level="WARNING"):
                await self.cog.sync_channel_permissions(self.game, self.channel)
        self.channel.set_permissions.assert_not_awaited()

    async def test_missing_result_message_is_not_announced_twice_on_retry(self):
        self.game.message_id = 42
        self.cog.checkpoint_game(self.game)
        self.channel.fetch_message.side_effect = RuntimeError("temporary failure")
        with self.assertLogs("app.discord_bot.modules.masoi_recovery", level="ERROR"):
            await self.cog.recover_pending_games()
        self.assertEqual(len(self.eco.get_masoi_sessions()), 1)
        self.channel.fetch_message.side_effect = None
        await self.cog.recover_pending_games()
        self.channel.send.assert_awaited_once()
        self.assertEqual(self.eco.get_masoi_sessions(), [])

    async def test_draw_recovery_never_updates_rank(self):
        self.game.winner_faction = Faction.DRAW
        self.cog.checkpoint_game(self.game)
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 0)
        self.assertEqual(self.eco.get_masoi_sessions(), [])

    async def test_persisted_state_survives_database_reopen(self):
        self.cog.attach_checkpoint(self.game)
        submit(self.game, 1, ActionKind.WOLF_VOTE, 2)
        self.eco.conn.close()
        self.eco = Economy()
        self.cog.get_economy.return_value = self.eco
        rows = self.eco.get_masoi_sessions()
        state = json.loads(rows[0]["state_json"])
        self.assertEqual(state["intents"][0]["targets"], [2])
        await self.cog.recover_pending_games()
        self.assertEqual(self.eco.get_masoi_stats(1)["plays"], 0)
