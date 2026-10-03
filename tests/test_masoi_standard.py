import unittest
from collections import Counter
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

from app.discord_bot.cogs.masoi import Masoi, LobbyView, SettingsView, CustomRolesConfigView
from app.discord_bot.cogs import masoi
from app.discord_bot.modules.masoi_delivery import deliver_night
from app.discord_bot.modules.masoi_engine import (
    ActionKind, Faction, GamePhase, MasoiSettings, NightEvent, RankFaction, Role,
)
from app.discord_bot.modules.masoi_state import restore_game, snapshot_game
from app.discord_bot.modules.masoi_ui import DayVoteView
from tests.test_masoi_cog import make_cog
from tests.test_masoi_engine import make_game, submit


class StandardRulesTests(unittest.TestCase):
    def test_event_settings_are_restored_but_boss_is_not(self):
        settings = MasoiSettings.from_dict({
            "enable_events": True, "enable_boss_mode": True,
            "custom_special_roles": ["ALPHA_WOLF", "SEER", "GUARD"],
        })
        self.assertTrue(settings.enable_events)
        self.assertFalse(hasattr(settings, "enable_boss_mode"))
        self.assertTrue(settings.to_dict()["enable_events"])
        self.assertNotIn("enable_boss_mode", settings.to_dict())
        self.assertEqual(settings.custom_special_roles, ["SEER", "GUARD"])

    def test_boss_flag_cannot_create_boss_when_events_are_off(self):
        for count in (5, 8, 12, 16, 20):
            game = make_game(*([Role.VILLAGER] * count))
            # Even obsolete in-memory attributes must have no effect.
            game.settings.enable_events = False
            game.settings.enable_boss_mode = True
            preview = Counter(game.preview_roles())
            game.assign_roles()
            self.assertEqual(Counter(p.role for p in game.players.values()), preview)
            self.assertNotIn(Role.ALPHA_WOLF, preview)
            game.start_night()
            self.assertIsNone(game.current_night_event)
            self.assertFalse(game.wolf_fury_active)
            self.assertFalse(any(log.event_type == "NIGHT_EVENT" for log in game.replay_logs))

    def test_custom_setup_cannot_assign_retired_boss(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_wolf_count = 1
        game.settings.custom_special_roles = ["ALPHA_WOLF", "SEER"]
        self.assertTrue(game.validate_role_setup())
        self.assertNotIn(Role.ALPHA_WOLF, game.preview_roles())
        game.assign_roles()
        self.assertFalse(any(p.role == Role.ALPHA_WOLF for p in game.players.values()))

    def test_legacy_event_metadata_cannot_affect_night_actions(self):
        for event in NightEvent:
            with self.subTest(event=event):
                game = make_game(Role.WOLF, Role.WITCH, Role.SEER, Role.THE_GIRL, Role.VILLAGER)
                game.current_night_event = event
                game.night_seed = 1
                submit(game, 1, ActionKind.WOLF_VOTE, 5)
                submit(game, 2, ActionKind.WITCH_SAVE, 5)
                submit(game, 2, ActionKind.WITCH_POISON, 1)
                submit(game, 3, ActionKind.SEER, 1)
                submit(game, 4, ActionKind.GIRL)
                result = game.resolve_night()
                self.assertEqual(result.deaths, (1, 4))
                self.assertTrue(game.players[5].is_alive)
                self.assertTrue(game.players[2].witch_save_used)
                self.assertTrue(game.players[2].witch_poison_used)
                self.assertEqual(game.players[2].witch_useful_use_count, 2)
                self.assertTrue(game.players[3].seer_found_wolf)

    def test_legacy_eclipse_does_not_skip_day_vote(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.current_night_event = NightEvent.SOLAR_ECLIPSE
        game.phase = GamePhase.DAY_RESOLVE
        game.day_votes = {2: 1}
        self.assertEqual(game.resolve_day_vote(), 1)
        self.assertFalse(game.players[1].is_alive)

    def test_white_wolf_even_night_still_works_without_event_modifier(self):
        game = make_game(Role.WHITE_WOLF, Role.WOLF, Role.VILLAGER)
        game.start_night()
        game.current_night_event = NightEvent.WANING_MOON
        submit(game, 1, ActionKind.WHITE_WOLF, 2)
        self.assertEqual(game.resolve_night().deaths, (2,))

    def test_old_boss_snapshot_remains_readable_for_recovery_and_rank(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.winner_faction = Faction.WEREWOLF
        state = snapshot_game(game)
        state["settings"].update(enable_events=True, enable_boss_mode=True)
        state["event"] = "BLOOD_MOON"
        state["players"][0].update(role="ALPHA_WOLF", boss_lives=2, boss_poison_shield=False)
        restored = restore_game(state)
        self.assertEqual(restored.rank_match_id, game.rank_match_id)
        self.assertEqual(restored.players[1].role, Role.ALPHA_WOLF)
        self.assertEqual(restored.players[1].boss_lives, 2)
        self.assertEqual(restored.get_rank_faction(1), RankFaction.WOLF)
        self.assertEqual(restored.calculate_rank_points(), {1: 20, 2: -15})
        self.assertFalse(restored.accepts_night_actions(restored.night_count))
        self.assertTrue(restored.settings.enable_events)
        self.assertTrue(restored.settings.to_dict()["enable_events"])


class StandardUITests(unittest.IsolatedAsyncioTestCase):
    async def test_event_commands_return_but_boss_commands_do_not(self):
        names = {name for cmd in Masoi.__cog_commands__ for name in (cmd.name, *cmd.aliases)}
        for retired in ("masoiboss", "masoi-boss", "werewolfboss", "masoi_boss"):
            self.assertNotIn(retired, names)
        for active in ("masoievent", "masoi-event", "werewolfevent", "masoi_event"):
            self.assertIn(active, names)
        self.assertIn("masoi", names)
        self.assertIn("masoivip", names)

    async def test_lobby_has_no_mode_line_but_settings_show_events(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.phase = GamePhase.LOBBY
        cog = make_cog(game)
        lobby, settings = LobbyView(game, cog), SettingsView(game, cog, None)
        try:
            self.assertNotIn("masoi_mode_info", {item.custom_id for item in lobby.children})
            self.assertTrue(hasattr(settings, "btn_events"))
            self.assertFalse(hasattr(settings, "btn_boss"))
            lobby_data = str(cog.build_lobby_embed(game).to_dict()).casefold()
            settings_data = str(cog.build_settings_embed(game).to_dict()).casefold()
            self.assertNotIn("chế độ", lobby_data)
            self.assertNotIn("thẻ sự kiện", lobby_data)
            self.assertNotIn("trùm", lobby_data)
            self.assertIn("thẻ sự kiện", settings_data)
            self.assertNotIn("trùm", settings_data)
        finally:
            lobby.stop()
            settings.stop()

    async def test_custom_role_picker_remains_available_without_mode_label(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.phase = GamePhase.LOBBY
        cog = make_cog(game)
        parent = SettingsView(game, cog, None)
        view = CustomRolesConfigView(game, cog, parent, None)
        try:
            self.assertTrue(view.btn_toggle_mode.label.startswith("Phân vai:"))
            self.assertNotIn("ALPHA_WOLF", {option.value for option in view.select_roles.options})
            self.assertNotIn("chế độ", view.get_embed().description.casefold())
        finally:
            parent.stop()
            view.stop()

    async def test_boss_arguments_are_rejected_before_fees(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        cog = make_cog(game)
        ctx = SimpleNamespace(prefix="!", send=AsyncMock())
        for argument in ("boss", "raid", "b", "unknown"):
            await Masoi.masoi_cmd.callback(cog, ctx, sub_command=argument)
        self.assertEqual(ctx.send.await_count, 4)
        cog.get_economy.assert_not_called()

    async def test_vip_command_route_is_unchanged(self):
        cog = make_cog(make_game(Role.WOLF, Role.VILLAGER))
        cog.masoivip_cmd = AsyncMock()
        ctx = SimpleNamespace()
        await Masoi.masoi_cmd.callback(cog, ctx, sub_command="vip")
        cog.masoivip_cmd.assert_awaited_once_with(ctx)

    async def test_legacy_seal_metadata_does_not_hide_witch_action_ui(self):
        game = make_game(Role.WITCH, Role.VILLAGER)
        game.prepare_night_delivery()
        game.current_night_event = NightEvent.SEAL_NIGHT
        cog = make_cog(game)
        user = SimpleNamespace(send=AsyncMock())
        cog.get_or_fetch_user.return_value = user
        try:
            await deliver_night(cog, game)
            user.send.assert_awaited_once()
            self.assertIsNotNone(user.send.call_args.kwargs["view"])
            self.assertIsNotNone(game.witch_view)
        finally:
            game.stop_night_views()

    async def test_standard_creation_preserves_existing_fee_policy(self):
        for vip in (False, True):
            game = make_game(Role.WOLF, Role.VILLAGER)
            cog = make_cog(game)
            cog.active_games = {}
            cog._recovery_ready = True
            cog.get_saved_settings = Mock(return_value=MasoiSettings.from_dict({"enable_events": True, "enable_boss_mode": True}))
            eco = Mock()
            eco.is_masoi_vip.return_value = vip
            eco.get_entry.return_value = (1, 20000)
            eco.get_masoi_custom_badge.return_value = ""
            cog.get_economy.return_value = eco
            ctx = SimpleNamespace(guild=SimpleNamespace(id=1), channel=SimpleNamespace(id=2),
                                  author=SimpleNamespace(id=1, display_name="Host"), prefix="!",
                                  send=AsyncMock(return_value=SimpleNamespace(id=42)))
            await Masoi.masoi_cmd.callback(cog, ctx)
            created = cog.active_games["1-2"]
            self.assertNotIn("enable_boss_mode", created.settings.to_dict())
            self.assertFalse(created.settings.enable_events)
            if vip:
                eco.add_money.assert_not_called()
            else:
                eco.add_money.assert_called_once_with(1, -10000)
            for item in ctx.send.call_args.kwargs["view"].children:
                self.assertNotEqual(item.custom_id, "masoi_mode_info")
            ctx.send.call_args.kwargs["view"].stop()

    async def test_standard_loop_always_reaches_day_vote_and_execution(self):
        game = make_game(Role.WOLF, *([Role.VILLAGER] * 4))
        game.settings.night_time = 0
        game.settings.discussion_time = 0
        game.settings.enable_events = True
        game.settings.enable_boss_mode = True
        cog = make_cog(game)
        cog.end_game = AsyncMock()
        channel = SimpleNamespace(send=AsyncMock())
        notice = SimpleNamespace(delete=AsyncMock(), edit=AsyncMock())
        titles = []
        async def send(*args, **kwargs):
            titles.append(kwargs["embed"].title)
            view = kwargs.get("view")
            if isinstance(view, DayVoteView):
                game.day_votes = {2: 1, 3: 1, 4: 1, 5: 1}
                view.stop()
            return notice
        with patch.object(masoi, "_safe_send", side_effect=send):
            await cog.game_loop(game, SimpleNamespace(channel=channel))
        self.assertEqual(game.winner_faction, Faction.VILLAGER)
        self.assertEqual(game.executed_player_id, 1)
        self.assertTrue(any("Bỏ Phiếu" in title for title in titles))
        self.assertFalse(any("THẺ SỰ KIỆN" in title or "NHẬT THỰC" in title for title in titles))
        cog.end_game.assert_awaited_once()
