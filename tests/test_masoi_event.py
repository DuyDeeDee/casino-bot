"""Night-event regression tests; Boss remains unavailable."""
import time
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.discord_bot.cogs import masoi
from app.discord_bot.modules.masoi_delivery import deliver_night
from app.discord_bot.modules.masoi_engine import ActionKind, GamePhase, NightEvent, Role
from app.discord_bot.modules.masoi_ui import DayDiscussionView, DayVoteView
from tests.test_masoi_cog import interaction, make_cog
from tests.test_masoi_engine import make_game, submit


class EventRulesTests(unittest.TestCase):
    def test_only_playable_cards_are_drawn_and_no_immediate_repeat(self):
        game = make_game(Role.WOLF, Role.WITCH, Role.SEER, *([Role.VILLAGER] * 7))
        game.settings.enable_events = True
        game.start_night()
        self.assertNotIn(NightEvent.THUNDERSTORM, game.eligible_night_events())
        self.assertNotIn(NightEvent.WANING_MOON, game.eligible_night_events())
        previous = game.current_night_event
        game.start_night()
        self.assertNotEqual(game.current_night_event, previous)
        self.assertEqual(len([log for log in game.replay_logs if log.event_type == "NIGHT_EVENT"]), 2)

    def test_blood_moon_adds_exactly_one_wolf_victim(self):
        game = make_game(Role.WOLF, *([Role.VILLAGER] * 9))
        game.settings.enable_events = True
        with patch("random.choice", return_value=NightEvent.BLOOD_MOON):
            game.start_night()
        self.assertTrue(game.wolf_fury_active)
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        result = game.resolve_night()
        self.assertEqual(len(result.deaths), 2)
        self.assertIn(2, result.deaths)

    def test_holy_light_blocks_wolf_bite_not_arson_fire(self):
        game = make_game(Role.WOLF, Role.ARSONIST, Role.VILLAGER, Role.VILLAGER)
        game.settings.enable_events = True
        game.current_night_event = NightEvent.HOLY_LIGHT
        game.players[3].is_doused = True
        submit(game, 1, ActionKind.WOLF_VOTE, 3)
        submit(game, 2, ActionKind.ARSON_IGNITE, 3)
        self.assertEqual(game.resolve_night().deaths, (3,))
        self.assertTrue(any(log.event_type == "HOLY_LIGHT_SAVED" for log in game.replay_logs))

    def test_fog_can_hide_seer_and_investigator_without_false_rank_bonus(self):
        for role, kind, targets in ((Role.SEER, ActionKind.SEER, (2,)),
                                    (Role.INVESTIGATOR, ActionKind.INVESTIGATE, (2, 3))):
            game = make_game(role, Role.WOLF, Role.VILLAGER)
            game.settings.enable_events = True
            game.current_night_event = NightEvent.DENSE_FOG
            game.night_seed = 1
            submit(game, 1, kind, *targets)
            game.resolve_night()
            result = game.night_seer_result if role == Role.SEER else game.night_investigator_result
            self.assertIn("không thể xác định", result)
            self.assertFalse(game.players[1].seer_found_wolf)

    def test_seal_blocks_potions_without_spending_them(self):
        game = make_game(Role.WITCH, Role.WOLF, Role.VILLAGER)
        game.settings.enable_events = True
        game.current_night_event = NightEvent.SEAL_NIGHT
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WITCH_SAVE, 3)
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WITCH_POISON, 2)
        game.resolve_night()
        self.assertFalse(game.players[1].witch_save_used)
        self.assertFalse(game.players[1].witch_poison_used)

    def test_disabled_event_metadata_is_inert(self):
        game = make_game(Role.WOLF, Role.VILLAGER, Role.VILLAGER)
        game.current_night_event = NightEvent.HOLY_LIGHT
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        self.assertEqual(game.resolve_night().deaths, (2,))


class EventUITests(unittest.IsolatedAsyncioTestCase):
    async def test_settings_toggle_is_not_vip_gated(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.phase = GamePhase.LOBBY
        cog = make_cog(game)
        cog.save_game_settings = Mock()
        view = masoi.SettingsView(game, cog, None)
        try:
            await view.btn_events.callback(interaction(game.host_id))
            self.assertTrue(game.settings.enable_events)
            cog.save_game_settings.assert_called_once_with(game)
            self.assertIn("Bật", view.btn_events.label)
        finally:
            view.stop()

    async def test_sealed_witch_has_no_action_dm(self):
        game = make_game(Role.WITCH, Role.VILLAGER)
        game.settings.enable_events = True
        game.current_night_event = NightEvent.SEAL_NIGHT
        game.prepare_night_delivery()
        cog = make_cog(game)
        await deliver_night(cog, game)
        cog.get_or_fetch_user.assert_not_awaited()
        self.assertIsNone(game.witch_view)

    async def test_silent_night_uses_shorter_deadline(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.DAY_DISCUSSION
        game.day_count = 1
        view = DayDiscussionView(game, make_cog(game), prepare=True, duration=30)
        try:
            before = time.monotonic()
            view.open_actions()
            self.assertGreaterEqual(view.deadline, before + 30)
            self.assertLess(view.deadline, before + 31)
        finally:
            view.stop()

    async def test_event_command_enables_event_without_changing_fee(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        cog = make_cog(game)
        cog.active_games = {}
        cog._recovery_ready = True
        eco = Mock()
        eco.is_masoi_vip.return_value = False
        eco.get_entry.return_value = (1, 20000)
        eco.get_masoi_custom_badge.return_value = ""
        cog.get_economy.return_value = eco
        cog.get_saved_settings = Mock(return_value=masoi.MasoiSettings())
        ctx = SimpleNamespace(guild=SimpleNamespace(id=1), channel=SimpleNamespace(id=2),
                              author=SimpleNamespace(id=1, display_name="Host"), prefix="!",
                              send=AsyncMock(return_value=SimpleNamespace(id=42)))
        await masoi.Masoi.masoievent_cmd.callback(cog, ctx)
        self.assertTrue(cog.active_games["1-2"].settings.enable_events)
        eco.add_money.assert_called_once_with(1, -10000)
        ctx.send.call_args.kwargs["view"].stop()

    async def test_eclipse_skips_vote_in_live_loop(self):
        game = make_game(Role.WOLF, *([Role.VILLAGER] * 7))
        game.settings.enable_events = True
        game.settings.night_time = 0
        game.settings.discussion_time = 0
        game.night_count = 1
        cog = make_cog(game)
        cog.end_game = AsyncMock()
        notice = SimpleNamespace(delete=AsyncMock(), edit=AsyncMock())
        titles = []
        async def send(*args, **kwargs):
            embed = kwargs.get("embed")
            titles.append(embed.title if embed else "")
            self.assertNotIsInstance(kwargs.get("view"), DayVoteView)
            if embed and embed.title == "☀️ Nhật Thực — Không treo cổ":
                game.phase = GamePhase.GAME_END
            return notice
        with patch("random.choice", return_value=NightEvent.SOLAR_ECLIPSE), patch.object(masoi, "_safe_send", side_effect=send):
            await cog.game_loop(game, SimpleNamespace(channel=SimpleNamespace(send=AsyncMock())))
        self.assertIn("☀️ Nhật Thực — Không treo cổ", titles)
        self.assertTrue(any(log.event_type == "SOLAR_ECLIPSE_SKIP" for log in game.replay_logs))


if __name__ == "__main__":
    unittest.main()
