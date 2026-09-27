import asyncio
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import discord
from app.discord_bot.cogs import masoi
from app.discord_bot.modules.masoi_engine import ActionKind, GamePhase, MasoiGame, Role
from tests.test_masoi_engine import make_game, submit


def interaction(uid):
    return SimpleNamespace(
        user=SimpleNamespace(id=uid),
        response=SimpleNamespace(send_message=AsyncMock(), edit_message=AsyncMock(), defer=AsyncMock()),
        message=SimpleNamespace(embeds=[discord.Embed(title="Night")], edit=AsyncMock()),
    )


def make_cog(game):
    cog = object.__new__(masoi.Masoi)
    cog.active_games = {f"{game.guild_id}-{game.channel_id}": game}
    cog.bot = SimpleNamespace(get_user=Mock(return_value=None))
    cog.get_economy = Mock(return_value=None)
    cog.get_or_fetch_user = AsyncMock(return_value=SimpleNamespace(send=AsyncMock()))
    return cog


class NightViewTests(unittest.IsolatedAsyncioTestCase):
    async def test_all_night_confirmations_record_intents_without_effects(self):
        cases = (
            (masoi.NightGuardView, Role.GUARD, ActionKind.GUARD, (2,)),
            (masoi.NightWolfView, Role.WOLF, ActionKind.WOLF_VOTE, (2,)),
            (masoi.NightSeerView, Role.SEER, ActionKind.SEER, (2,)),
            (masoi.NightHarlotView, Role.HARLOT, ActionKind.HARLOT, (2,)),
            (masoi.NightInvestigatorView, Role.INVESTIGATOR, ActionKind.INVESTIGATE, (2, 3)),
            (masoi.NightWolfSeerView, Role.WOLF_SEER, ActionKind.WOLF_SEER, (2,)),
            (masoi.NightSerialKillerView, Role.SERIAL_KILLER, ActionKind.SERIAL_KILL, (2,)),
            (masoi.NightWhiteWolfView, Role.WHITE_WOLF, ActionKind.WHITE_WOLF, (3,)),
            (masoi.NightPhantomWolfView, Role.PHANTOM_WOLF, ActionKind.PHANTOM, (2,)),
            (masoi.NightPiperView, Role.PIPER, ActionKind.PIPER, (2, 3)),
            (masoi.NightCupidView, Role.CUPID, ActionKind.CUPID, (2, 3)),
        )
        for cls, role, kind, targets in cases:
            with self.subTest(view=cls.__name__):
                game = make_game(role, Role.VILLAGER, Role.WOLF)
                if role == Role.WHITE_WOLF:
                    game.start_night()
                view = cls(game, 1)
                view.selected_target_id = targets[0]
                view.select._values = [str(uid) for uid in targets]
                event = interaction(1)
                await view.confirm_callback(event)
                self.assertEqual(game._night_intents[(1, kind)].targets, targets)
                self.assertTrue(all(p.is_alive and not p.piper_charmed and p.lover_id is None for p in game.players.values()))
                self.assertIsNone(game.night_seer_result)
                event.response.edit_message.assert_awaited_once()
                view.stop()

    async def test_wrong_owner_and_stale_view_cannot_submit(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        view = masoi.NightWolfView(game, 1)
        view.selected_target_id = 2
        await view.confirm_callback(interaction(2))
        self.assertFalse(game._night_intents)
        game.start_night()
        await view.confirm_callback(interaction(1))
        self.assertFalse(game._night_intents)
        view.stop()

    async def test_locked_deadline_blocks_direct_callback(self):
        game = make_game(Role.SEER, Role.WOLF)
        view = masoi.NightSeerView(game, 1)
        view.selected_target_id = 2
        game.lock_night()
        event = interaction(1)
        await view.confirm_callback(event)
        self.assertFalse(game._night_intents)
        event.response.send_message.assert_awaited_once()
        view.stop()

    async def test_witch_second_step_keeps_night_deadline(self):
        game = make_game(Role.WITCH, Role.VILLAGER, Role.WOLF)
        game.night_deadline = time.monotonic() + 10
        view = masoi.NightWitchView(game, 1, 2)
        game.witch_view = view
        game.witch_dm_message = interaction(1).message
        event = interaction(1)
        await view.save_callback(event)
        event.response.defer.assert_awaited_once()
        poison_view = event.message.edit.call_args.kwargs["view"]
        self.assertIs(game.witch_view, poison_view)
        self.assertTrue(view.is_finished())
        self.assertLessEqual(poison_view.timeout, 10)
        self.assertFalse(game.players[1].witch_save_used)
        self.assertEqual(game._night_intents[(1, ActionKind.WITCH_SAVE)].targets, (2,))
        cog = make_cog(game)
        await cog.update_witch_dm(game)
        game.witch_dm_message.edit.assert_not_awaited()
        game.start_night()
        poison_view.selected_target_id = 3
        await poison_view.confirm_callback(interaction(1))
        self.assertFalse(game._night_intents)
        poison_view.stop()

    async def test_girl_records_no_random_or_death_in_callback(self):
        game = make_game(Role.THE_GIRL, Role.WOLF)
        view = masoi.NightGirlView(game, 1)
        with patch("random.random", side_effect=AssertionError("No callback RNG")):
            await view.peek_callback(interaction(1))
        self.assertIn((1, ActionKind.GIRL), game._night_intents)
        self.assertTrue(game.players[1].is_alive)
        self.assertFalse(game.girl_caught)

    async def test_hunter_confirmed_target_only_after_shot(self):
        game = make_game(Role.HUNTER, Role.WOLF)
        game.players[1].is_alive = False
        view = masoi.NightHunterView(game, 1)
        view.selected_target_id = 2
        self.assertIsNone(view.confirmed_target_id)
        await view.confirm_callback(interaction(1))
        self.assertEqual(view.confirmed_target_id, 2)
        self.assertFalse(game.players[2].is_alive)
        await view.confirm_callback(interaction(1))
        self.assertEqual(sum(log.event_type == "HUNTER_SHOOT" for log in game.replay_logs), 1)

    async def test_expired_hunter_does_not_shoot(self):
        game = make_game(Role.HUNTER, Role.WOLF)
        game.players[1].is_alive = False
        view = masoi.NightHunterView(game, 1)
        view.selected_target_id = 2
        view.deadline = 0
        await view.confirm_callback(interaction(1))
        self.assertTrue(game.players[2].is_alive)
        view.stop()

    async def test_stale_day_vote_does_not_change_next_day(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.DAY_VOTE
        view = masoi.DayVoteView(game, make_cog(game))
        game.day_count += 1
        event = interaction(1)
        event.data = {"values": ["2"]}
        await view.vote_callback(event)
        self.assertFalse(game.day_votes)
        view.stop()

    async def test_settings_locked_after_lobby(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        cog = make_cog(game)
        view = masoi.SettingsView(game, cog, None)
        self.assertFalse(await view.interaction_check(interaction(1)))
        view.stop()


class PreflightAndPermissionsTests(unittest.IsolatedAsyncioTestCase):
    def lobby(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.phase = GamePhase.LOBBY
        game.assign_roles = Mock(wraps=game.assign_roles)
        cog = make_cog(game)
        cog.game_loop = AsyncMock()
        message = SimpleNamespace(edit=AsyncMock(), channel=SimpleNamespace(send=AsyncMock()))
        return game, cog, message

    async def test_dm_failure_returns_lobby_without_assigning(self):
        game, cog, message = self.lobby()
        cog.get_or_fetch_user.return_value = None
        await cog.start_game(game, message)
        self.assertEqual(game.phase, GamePhase.LOBBY)
        game.assign_roles.assert_not_called()
        cog.game_loop.assert_not_awaited()
        message.channel.send.assert_awaited_once()
        message.edit.call_args.kwargs["view"].stop()

    async def test_concurrent_start_and_join_blocked_in_preflight(self):
        game, cog, message = self.lobby()
        async def send(*args, **kwargs):
            self.assertFalse(game.add_player(99, "Late"))
            await cog.start_game(game, message)
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=AsyncMock(side_effect=send))
        await cog.start_game(game, message)
        game.assign_roles.assert_called_once()
        cog.game_loop.assert_awaited_once()

    async def test_cancelled_preflight_cannot_assign_or_start(self):
        game, cog, message = self.lobby()
        async def send(*args, **kwargs):
            game.phase = GamePhase.GAME_END
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=AsyncMock(side_effect=send))
        await cog.start_game(game, message)
        game.assign_roles.assert_not_called()
        cog.game_loop.assert_not_awaited()

    async def test_permission_flags_preserved_and_restored(self):
        game = make_game(Role.VILLAGER)
        game.players[1].is_alive = False
        cog = make_cog(game)
        member = object()
        original = discord.PermissionOverwrite(view_channel=False, attach_files=True, send_messages=True)
        channel = Mock(spec=discord.TextChannel)
        channel.guild = SimpleNamespace(get_member=Mock(return_value=member))
        channel.overwrites = {member: original}
        channel.set_permissions = AsyncMock()
        await cog.sync_channel_permissions(game, channel)
        muted = channel.set_permissions.call_args.kwargs["overwrite"]
        self.assertFalse(muted.send_messages)
        self.assertFalse(muted.view_channel)
        self.assertTrue(muted.attach_files)
        self.assertTrue(original.send_messages)
        channel.overwrites[member] = muted
        await cog.sync_channel_permissions(game, channel)
        await cog.restore_channel_permissions(game, channel)
        self.assertEqual(channel.set_permissions.call_args.kwargs["overwrite"], original)
        self.assertFalse(game.channel_permission_snapshots)

    async def test_absent_permission_overwrite_restores_none(self):
        game = make_game(Role.VILLAGER)
        game.players[1].is_alive = False
        cog = make_cog(game)
        channel = Mock(spec=discord.TextChannel)
        channel.guild = SimpleNamespace(get_member=Mock(return_value=object()))
        channel.overwrites = {}
        channel.set_permissions = AsyncMock()
        await cog.sync_channel_permissions(game, channel)
        await cog.restore_channel_permissions(game, channel)
        self.assertIsNone(channel.set_permissions.call_args.kwargs["overwrite"])

    async def test_permission_restore_failure_keeps_snapshot_for_retry(self):
        game = make_game(Role.VILLAGER)
        game.channel_permission_snapshots[1] = None
        cog = make_cog(game)
        channel = Mock(spec=discord.TextChannel)
        channel.guild = SimpleNamespace(get_member=Mock(return_value=object()))
        channel.set_permissions = AsyncMock(side_effect=RuntimeError("offline"))
        with self.assertLogs(masoi.logger, level="WARNING"):
            await cog.restore_channel_permissions(game, channel)
        self.assertIn(1, game.channel_permission_snapshots)
        channel.set_permissions.side_effect = None
        await cog.restore_channel_permissions(game, channel)
        self.assertFalse(game.channel_permission_snapshots)

    async def test_cancelled_game_loop_does_not_settle_rank(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.GAME_END
        cog = make_cog(game)
        cog.end_game = AsyncMock()
        cog.restore_channel_permissions = AsyncMock()
        message = SimpleNamespace(channel=SimpleNamespace())
        await cog.game_loop(game, message)
        cog.end_game.assert_not_awaited()
        cog.restore_channel_permissions.assert_awaited_once()

    async def test_force_stop_during_night_cleanup_cannot_resolve(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.settings.night_time = 0
        cog = make_cog(game)
        cog.end_game = AsyncMock()
        cog.restore_channel_permissions = AsyncMock()
        game.resolve_night = Mock(wraps=game.resolve_night)
        async def delete():
            game.phase = GamePhase.GAME_END
        msg = SimpleNamespace(delete=AsyncMock(side_effect=delete))
        message = SimpleNamespace(channel=SimpleNamespace(send=AsyncMock(return_value=msg)))
        with patch.object(masoi, "_safe_send", AsyncMock(return_value=msg)):
            await cog.game_loop(game, message)
        game.resolve_night.assert_not_called()
        cog.end_game.assert_not_awaited()

    async def test_full_night_to_win_loop_uses_result_snapshot(self):
        game = make_game(Role.WOLF, Role.WITCH, Role.VILLAGER)
        game.settings.night_time = 0
        original_start = game.start_night
        def start_with_actions():
            original_start()
            game.night_deadline = time.monotonic() + 10
            submit(game, 1, ActionKind.WOLF_VOTE, 2)
            game.night_deadline = 0
        game.start_night = start_with_actions
        cog = make_cog(game)
        cog.end_game = AsyncMock()
        cog.restore_channel_permissions = AsyncMock()
        cog.sync_channel_permissions = AsyncMock()
        cog.check_and_trigger_hunter = AsyncMock()
        cog.check_and_trigger_mayor_succession = AsyncMock()
        message = SimpleNamespace(channel=SimpleNamespace(send=AsyncMock()))
        msg = SimpleNamespace(delete=AsyncMock())
        with patch.object(masoi, "_safe_send", AsyncMock(return_value=msg)):
            await cog.game_loop(game, message)
        self.assertEqual(game.phase, GamePhase.GAME_END)
        cog.end_game.assert_awaited_once()
        self.assertEqual(game._night_result.night, 2)
        self.assertEqual(game._night_result.deaths, (2,))
