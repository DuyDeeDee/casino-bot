"""Regression coverage for the rebalanced Ma Sói roster and its win conditions."""
import unittest
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.discord_bot.modules.masoi_engine import (
    ActionIntent, ActionKind, Faction, GamePhase, MasoiGame,
    MasoiSettings, RankFaction, RETIRED_ROLES, Role,
)
from app.discord_bot.modules.masoi_state import restore_game, snapshot_game
from app.discord_bot.modules.masoi_rank import MasoiRankService
from app.discord_bot.modules.masoi_ui import NightArsonistView, NightDoctorView, DayDiscussionView
from tests.test_masoi_cog import interaction, make_cog


def game_with(*roles):
    game = MasoiGame(1, 2, 1, "Host")
    for uid, role in enumerate(roles, 1):
        game.add_player(uid, f"Player {uid}")
        game.players[uid].role = role
    game.start_night()
    return game


def submit(game, uid, kind, *targets):
    game.submit_night_action(ActionIntent(game.night_count, uid, kind, tuple(targets)))


class NewRoleRulesTests(unittest.TestCase):
    def test_retired_roles_never_enter_new_roster(self):
        for count in range(5, 21):
            game = MasoiGame(1, 2, 1, "Host")
            for uid in range(1, count + 1):
                game.add_player(uid, str(uid))
            self.assertFalse(set(game.preview_roles()) & RETIRED_ROLES)
            self.assertEqual(len(game.preview_roles()), count)
            self.assertEqual(game.validate_role_setup(), [])
        settings = MasoiSettings.from_dict({"custom_special_roles": ["WHITE_WOLF", "THE_GIRL", "DOCTOR"]})
        self.assertEqual(settings.custom_special_roles, ["DOCTOR"])
        custom = MasoiGame(1, 2, 1, "Host")
        for uid in range(1, 11):
            custom.add_player(uid, str(uid))
        custom.settings.role_setup_mode = "CUSTOM"
        custom.settings.custom_wolf_count = 1
        for retired in RETIRED_ROLES:
            custom.settings.custom_special_roles = [retired.name]
            self.assertTrue(custom.validate_role_setup())
            self.assertNotIn(retired, custom.preview_roles())

    def test_small_custom_room_cannot_start_with_two_wolves(self):
        game = game_with(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_wolf_count = 2
        self.assertTrue(game.validate_role_setup())
        game.settings.custom_wolf_count = 1
        game.settings.custom_special_roles = ["DOCTOR", "YOUNG_WOLF"]
        self.assertTrue(game.validate_role_setup())

    def test_auto_roster_progressively_uses_new_roles(self):
        for count, expected in ((10, Role.DOCTOR), (12, Role.YOUNG_WOLF),
                                (13, Role.ARSONIST), (15, Role.GUNNER),
                                (17, Role.HUMAN_HUNTER)):
            game = MasoiGame(1, 2, 1, "Host")
            for uid in range(1, count + 1):
                game.add_player(uid, str(uid))
            self.assertIn(expected, game.preview_roles())

    def test_human_hunter_gets_village_target_and_personal_win(self):
        game = MasoiGame(1, 2, 1, "Host")
        for uid in range(1, 17):
            game.add_player(uid, str(uid))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_wolf_count = 2
        game.settings.custom_special_roles = ["HUMAN_HUNTER", "DOCTOR"]
        self.assertEqual(game.validate_role_setup(), [])
        with patch("random.shuffle", lambda values: None):
            game.assign_roles()
        hunter = game.get_player_by_role(Role.HUMAN_HUNTER)
        self.assertEqual(game.players[hunter.human_hunter_target_id].role.faction, Faction.VILLAGER)
        game.phase = GamePhase.DAY_VOTE
        game.day_votes = {uid: hunter.human_hunter_target_id for uid in game.players if uid != hunter.human_hunter_target_id}
        game.resolve_day_vote()
        self.assertTrue(hunter.human_hunter_succeeded)
        game.winner_faction = Faction.VILLAGER
        self.assertTrue(game.did_player_win(hunter.user_id))
        self.assertEqual(game.get_rank_faction(hunter.user_id), RankFaction.SOLO)
        self.assertEqual(game.calculate_rank_points()[hunter.user_id], 30)

    def test_human_hunter_target_dies_elsewhere_joins_wolves(self):
        game = game_with(Role.HUMAN_HUNTER, Role.WOLF, Role.VILLAGER, Role.VILLAGER)
        game.players[1].human_hunter_target_id = 3
        game.apply_deaths((3,), "NIGHT_DEATH")
        self.assertTrue(game.players[1].human_hunter_joined_wolves)
        self.assertTrue(game.players[1].is_wolf)
        self.assertEqual(game.get_rank_faction(1), RankFaction.WOLF)
        game.winner_faction = Faction.WEREWOLF
        self.assertTrue(game.did_player_win(1))

    def test_personal_win_survives_a_draw_without_penalizing_others(self):
        game = game_with(Role.HUMAN_HUNTER, Role.VILLAGER, Role.WOLF)
        game.players[1].human_hunter_succeeded = True
        game.winner_faction = Faction.DRAW
        self.assertEqual(MasoiRankService.results(game), [(1, 30, True, "SOLO")])

    def test_distinct_solo_roles_have_distinct_cupid_objectives(self):
        game = game_with(Role.ARSONIST, Role.HUMAN_HUNTER, Role.TANNER)
        self.assertNotEqual(game.personal_objective(game.players[1]), game.personal_objective(game.players[2]))
        self.assertNotEqual(game.personal_objective(game.players[2]), game.personal_objective(game.players[3]))

    def test_doctor_blocks_direct_attacks_but_not_dousing(self):
        game = game_with(Role.DOCTOR, Role.WOLF, Role.ARSONIST, Role.VILLAGER, Role.VILLAGER)
        submit(game, 1, ActionKind.DOCTOR, 4)
        submit(game, 2, ActionKind.WOLF_VOTE, 4)
        submit(game, 3, ActionKind.ARSON_DOUSE, 4, 5)
        self.assertEqual(game.resolve_night().deaths, ())
        self.assertTrue(game.players[4].is_doused)
        self.assertEqual(game.players[4].doctor_protection_count, 1)
        game.start_night()
        submit(game, 1, ActionKind.DOCTOR, 4)
        submit(game, 3, ActionKind.ARSON_IGNITE)
        self.assertEqual(game.resolve_night().deaths, (5,))
        self.assertFalse(game.players[4].is_doused)
        game.start_night()
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.DOCTOR, 4)
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.DOCTOR, 1)

    def test_harlot_away_and_dangerous_visit(self):
        game = game_with(Role.HARLOT, Role.WOLF, Role.VILLAGER, Role.VILLAGER)
        submit(game, 1, ActionKind.HARLOT, 3)
        submit(game, 2, ActionKind.WOLF_VOTE, 1)
        self.assertEqual(game.resolve_night().deaths, ())
        game.start_night()
        submit(game, 1, ActionKind.HARLOT, 2)
        self.assertEqual(game.resolve_night().deaths, (1,))
        another = game_with(Role.HARLOT, Role.WOLF, Role.VILLAGER, Role.VILLAGER)
        submit(another, 1, ActionKind.HARLOT, 3)
        submit(another, 2, ActionKind.WOLF_VOTE, 3)
        self.assertEqual(another.resolve_night().deaths, (1, 3))

    def test_arsonist_can_finish_with_one_remaining_target(self):
        game = game_with(Role.ARSONIST, Role.VILLAGER)
        self.assertEqual(game.required_target_count(ActionKind.ARSON_DOUSE), 1)
        submit(game, 1, ActionKind.ARSON_DOUSE, 2)
        self.assertEqual(game.resolve_night().deaths, ())
        game.start_night()
        submit(game, 1, ActionKind.ARSON_IGNITE)
        self.assertEqual(game.resolve_night().deaths, (2,))
        self.assertEqual(game.check_win_condition(), Faction.ARSONIST)

    def test_investigator_compares_true_alignment(self):
        game = game_with(Role.INVESTIGATOR, Role.LYCAN, Role.VILLAGER, Role.WOLF, Role.ARSONIST)
        submit(game, 1, ActionKind.INVESTIGATE, 2, 3)
        game.resolve_night()
        self.assertIn("CÙNG PHE", game.night_investigator_result)
        game.start_night()
        submit(game, 1, ActionKind.INVESTIGATE, 2, 4)
        game.resolve_night()
        self.assertIn("KHÁC PHE", game.night_investigator_result)

    def test_young_wolf_revenge_and_gunner_day_limits(self):
        game = game_with(Role.YOUNG_WOLF, Role.GUNNER, Role.WOLF, Role.VILLAGER, Role.VILLAGER)
        game.apply_deaths((1,), "DAY_DEATH")
        self.assertIsNone(game.check_win_condition())
        with self.assertRaises(ValueError):
            game.resolve_young_wolf_revenge(1, 3)
        self.assertEqual(game.resolve_young_wolf_revenge(1, 4), (4,))
        game.phase = GamePhase.DAY_DISCUSSION
        game.day_count = 1
        with self.assertRaises(ValueError):
            game.resolve_gunner_shot(2, 3)
        game.day_count = 2
        self.assertEqual(game.resolve_gunner_shot(2, 3), (3,))
        with self.assertRaises(ValueError):
            game.resolve_gunner_shot(2, 5)
        game.day_count = 3
        self.assertEqual(game.resolve_gunner_shot(2, 5), (5,))
        self.assertEqual(game.players[2].gunner_bullets_used, 2)

    def test_snapshot_roundtrip_keeps_new_role_state(self):
        game = game_with(Role.ARSONIST, Role.HUMAN_HUNTER, Role.DOCTOR, Role.GUNNER, Role.YOUNG_WOLF)
        game.players[3].doctor_protection_count = 2
        game.players[4].gunner_bullets_used = 1
        game.players[2].human_hunter_target_id = 3
        game.players[1].is_doused = True
        restored = restore_game(snapshot_game(game))
        self.assertEqual(restored.players[1].role, Role.ARSONIST)
        self.assertTrue(restored.players[1].is_doused)
        self.assertEqual(restored.players[2].human_hunter_target_id, 3)
        self.assertEqual(restored.players[3].doctor_protection_count, 2)
        self.assertEqual(restored.players[4].gunner_bullets_used, 1)


class NewRoleUITests(unittest.IsolatedAsyncioTestCase):
    async def test_doctor_and_arsonist_dm_controls_submit_actions(self):
        game = game_with(Role.DOCTOR, Role.ARSONIST, Role.VILLAGER, Role.VILLAGER)
        doctor = NightDoctorView(game, 1)
        doctor.select._values = ["3"]
        await doctor.confirm_callback(interaction(1))
        self.assertEqual(game._night_intents[(1, ActionKind.DOCTOR)].targets, (3,))
        arson = NightArsonistView(game, 2)
        arson.select._values = ["3", "4"]
        await arson.douse_callback(interaction(2))
        self.assertEqual(game._night_intents[(2, ActionKind.ARSON_DOUSE)].targets, (3, 4))
        game.resolve_night()
        game.start_night()
        ignition = NightArsonistView(game, 2)
        await ignition.ignite_callback(interaction(2))
        self.assertIn((2, ActionKind.ARSON_IGNITE), game._night_intents)

    async def test_gunner_public_button_and_target_control(self):
        game = game_with(Role.GUNNER, Role.VILLAGER, Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.DAY_DISCUSSION
        game.day_count = 2
        cog = make_cog(game)
        cog.check_and_trigger_hunter = AsyncMock()
        cog.check_and_trigger_mayor_succession = AsyncMock()
        cog.sync_channel_permissions = AsyncMock()
        discussion = DayDiscussionView(game, cog)
        discussion.deadline = time.monotonic() + 30
        event = interaction(1)
        await discussion.gunner_btn.callback(event)
        target_view = event.response.send_message.call_args.kwargs["view"]
        target_view.select._values = ["2"]
        event.channel = SimpleNamespace(send=AsyncMock())
        await target_view.select_callback(event)
        self.assertFalse(game.players[2].is_alive)
        self.assertEqual(game.players[1].gunner_bullets_used, 1)
        event.channel.send.assert_awaited_once()
        discussion.stop()


if __name__ == "__main__":
    unittest.main()
