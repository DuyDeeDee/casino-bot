import asyncio
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

from app.discord_bot.cogs.masoi import ReplayView
from app.discord_bot.modules.masoi_delivery import deliver_night, NightDeliveryError
from app.discord_bot.modules.masoi_engine import ActionKind, Faction, GamePhase, ReplayLog, Role
from tests.test_masoi_engine import make_game, submit
from tests.test_masoi_cog import make_cog, interaction


class SoloEndgameTests(unittest.TestCase):
    def test_white_wolf_vs_village_does_not_end_as_team_win(self):
        game = make_game(Role.WHITE_WOLF, Role.VILLAGER)
        self.assertIsNone(game.check_win_condition())
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        game.resolve_night()
        self.assertEqual(game.check_win_condition(), Faction.WHITE_WOLF)
        self.assertEqual(game.calculate_rank_points(), {1: 30, 2: -15})

    def test_live_white_wolf_blocks_regular_wolf_parity_win(self):
        game = make_game(Role.WHITE_WOLF, Role.WOLF, Role.VILLAGER)
        self.assertIsNone(game.check_win_condition())
        game.players[1].is_alive = False
        self.assertEqual(game.check_win_condition(), Faction.WEREWOLF)

    def test_serial_killer_requires_sole_survival(self):
        game = make_game(Role.SERIAL_KILLER, Role.VILLAGER)
        self.assertIsNone(game.check_win_condition())
        submit(game, 1, ActionKind.SERIAL_KILL, 2)
        game.resolve_night()
        self.assertEqual(game.check_win_condition(), Faction.SERIAL_KILLER)

    def test_piper_is_a_live_threat_until_charmed_or_eliminated(self):
        for other in (Role.VILLAGER, Role.WOLF):
            game = make_game(Role.PIPER, other)
            self.assertIsNone(game.check_win_condition())
            submit(game, 1, ActionKind.PIPER, 2)
            game.resolve_night()
            self.assertEqual(game.check_win_condition(), Faction.PIPER)

    def test_everyone_dead_is_draw_with_zero_rank(self):
        game = make_game(Role.VILLAGER, Role.WOLF)
        game.apply_deaths((1, 2), "TEST_DEATH")
        self.assertEqual(game.check_win_condition(), Faction.DRAW)
        self.assertEqual(game.calculate_rank_points(), {1: 0, 2: 0})


class ReplayAndDeliveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_day_execution_and_first_night_grouped_correctly(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.record_log("NIGHT_DEATH", target_id=2, result="night")
        game.phase = GamePhase.DAY_RESOLVE
        game.day_count = 1
        game.record_log("DAY_EXECUTION", target_id=2, result="day")
        view = ReplayView(game)
        titles = [page["title"] for page in view.pages]
        self.assertIn("🌙 Đêm 1", titles)
        self.assertIn("☀️ Ngày 1", titles)
        view.stop()

    async def test_legacy_day_phase_also_groups_correctly(self):
        game = make_game(Role.VILLAGER)
        game.replay_logs = [ReplayLog(2, GamePhase.DAY_RESOLVE.value, "DAY_EXECUTION", result="day")]
        view = ReplayView(game)
        self.assertEqual(view.pages[1]["title"], "☀️ Ngày 2")
        view.stop()

    async def test_long_replay_is_split_without_dropping_text(self):
        game = make_game(Role.VILLAGER)
        for index in range(150):
            game.record_log("EXAMPLE", result=f"event-{index}: " + "x" * 100)
        view = ReplayView(game)
        self.assertGreater(len(view.pages), 2)
        self.assertTrue(all(len(page["content"]) <= 3800 for page in view.pages))
        self.assertIn("event-149", "".join(page["content"] for page in view.pages))
        view.stop()

    async def test_concurrent_delivery_does_not_open_clock_early(self):
        game = make_game(Role.WOLF, Role.SEER, Role.VILLAGER)
        game.prepare_night_delivery()
        cog = make_cog(game)
        entered = set()
        both_entered = asyncio.Event()
        release = asyncio.Event()
        async def fetch(uid):
            async def send(**kwargs):
                entered.add(uid)
                if len(entered) == 2:
                    both_entered.set()
                await release.wait()
                return SimpleNamespace(embeds=[kwargs["embed"]], edit=AsyncMock())
            return SimpleNamespace(send=send)
        cog.get_or_fetch_user.side_effect = fetch
        task = asyncio.create_task(deliver_night(cog, game))
        try:
            await asyncio.wait_for(both_entered.wait(), 1)
            self.assertFalse(game.accepts_night_actions(game.night_count))
            view = game.night_views[0]
            event = interaction(view.actor_id)
            self.assertFalse(await view.interaction_check(event))
            self.assertEqual(game.night_deadline, 0)
        finally:
            release.set()
            await task
        game.open_night_actions()
        self.assertTrue(game.accepts_night_actions(game.night_count))
        game.stop_night_views()

    async def test_missing_user_or_failed_dm_aborts_and_stops_views(self):
        game = make_game(Role.WOLF, Role.SEER)
        game.prepare_night_delivery()
        cog = make_cog(game)
        cog.get_or_fetch_user.return_value = None
        with self.assertLogs("app.discord_bot.modules.masoi_delivery", level="WARNING"):
            with self.assertRaises(NightDeliveryError):
                await deliver_night(cog, game)
        self.assertFalse(game.night_views)
        self.assertFalse(game._night_intents)
        self.assertIsNone(game.winner_faction)

    async def test_dm_timeout_cancels_delivery_and_keeps_window_closed(self):
        game = make_game(Role.WOLF)
        game.prepare_night_delivery()
        cog = make_cog(game)
        async def forever(**kwargs):
            await asyncio.Event().wait()
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=forever)
        with self.assertLogs("app.discord_bot.modules.masoi_delivery", level="WARNING"):
            with self.assertRaises(NightDeliveryError):
                await deliver_night(cog, game, timeout=0.01)
        self.assertFalse(game.accepts_night_actions(game.night_count))
        self.assertFalse(game.night_views)

    async def test_hunter_fetches_user_when_not_cached(self):
        game = make_game(Role.HUNTER, Role.WOLF)
        game.players[1].is_alive = False
        game.settings.night_time = 0
        cog = make_cog(game)
        cog.bot.get_user.return_value = None
        user = SimpleNamespace(send=AsyncMock())
        cog.get_or_fetch_user.return_value = user
        await cog.check_and_trigger_hunter(game, SimpleNamespace(send=AsyncMock()))
        cog.get_or_fetch_user.assert_awaited_once_with(1)
        user.send.assert_awaited_once()
        self.assertTrue(game.players[1].hunter_shot_used)

    async def test_missing_hunter_dm_is_not_treated_as_skipping_the_shot(self):
        game = make_game(Role.HUNTER, Role.WOLF)
        game.players[1].is_alive = False
        cog = make_cog(game)
        cog.get_or_fetch_user.return_value = None
        with self.assertRaises(NightDeliveryError):
            await cog.check_and_trigger_hunter(game, SimpleNamespace(send=AsyncMock()))
        self.assertFalse(game.players[1].hunter_shot_used)
        self.assertIsNone(game.winner_faction)

    async def test_failed_mayor_dm_aborts_instead_of_silently_losing_succession(self):
        game = make_game(Role.VILLAGER, Role.WOLF)
        game.mayor_id = 1
        game.players[1].is_alive = False
        cog = make_cog(game)
        cog.get_or_fetch_user.return_value = SimpleNamespace(send=AsyncMock(side_effect=RuntimeError("DM unavailable")))
        with self.assertRaises(NightDeliveryError):
            await cog.check_and_trigger_mayor_succession(game, SimpleNamespace(send=AsyncMock()))
        self.assertIsNone(game.winner_faction)
