import unittest
from dataclasses import FrozenInstanceError
from unittest.mock import patch
from app.discord_bot.modules.masoi_engine import (
    ActionIntent, ActionKind, GamePhase, MasoiGame, Role, Faction,
)


def make_game(*roles):
    game = MasoiGame(1, 2, 1, "Host")
    for uid, role in enumerate(roles, 1):
        game.add_player(uid, f"Player {uid}")
        game.players[uid].role = role
    game.start_night()
    return game


def submit(game, actor, kind, *targets):
    game.submit_night_action(ActionIntent(game.night_count, actor, kind, tuple(targets)))


class StageOneRegressionTests(unittest.TestCase):
    def test_save_only_one_fury_victim(self):
        game = make_game(Role.WOLF, Role.WOLF, Role.WITCH, Role.VILLAGER, Role.VILLAGER)
        game.wolf_fury_active = True
        submit(game, 1, ActionKind.WOLF_VOTE, 4)
        submit(game, 2, ActionKind.WOLF_VOTE, 5)
        submit(game, 3, ActionKind.WITCH_SAVE, 4)
        self.assertEqual(set(game.resolve_night().deaths), {5})
        self.assertTrue(game.players[3].witch_save_used)

    def test_blocked_witch_does_not_spend_potion(self):
        game = make_game(Role.WOLF, Role.WITCH, Role.HARLOT, Role.VILLAGER)
        submit(game, 1, ActionKind.WOLF_VOTE, 4)
        submit(game, 3, ActionKind.HARLOT, 2)
        submit(game, 2, ActionKind.WITCH_SAVE, 4)
        self.assertEqual(set(game.resolve_night().deaths), {4})
        self.assertFalse(game.players[2].witch_save_used)

    def test_blocked_seer_gets_no_information(self):
        game = make_game(Role.SEER, Role.HARLOT, Role.WOLF)
        submit(game, 2, ActionKind.HARLOT, 1)
        submit(game, 1, ActionKind.SEER, 3)
        game.resolve_night()
        self.assertIn("phong tỏa", game.night_seer_result)
        self.assertFalse(game.players[1].seer_found_wolf)

    def test_lycan_is_not_rank_bonus_for_finding_real_wolf(self):
        game = make_game(Role.SEER, Role.LYCAN, Role.WOLF)
        submit(game, 1, ActionKind.SEER, 2)
        game.resolve_night()
        self.assertFalse(game.players[1].seer_found_wolf)

    def test_converted_cursed_does_not_win_with_village(self):
        game = make_game(Role.CURSED, Role.VILLAGER)
        game.players[1].is_cursed_converted = True
        game.winner_faction = Faction.VILLAGER
        self.assertFalse(game.did_player_win(1))

    def test_white_wolf_solo_win(self):
        game = make_game(Role.WHITE_WOLF)
        self.assertEqual(game.check_win_condition(), Faction.WHITE_WOLF)
        self.assertTrue(game.did_player_win(1))

    def test_lovers_win_only_surviving_couple(self):
        game = make_game(Role.WOLF, Role.VILLAGER, Role.CUPID)
        game.players[1].lover_id = 2
        game.players[2].lover_id = 1
        game.players[3].is_alive = False
        self.assertEqual(game.check_win_condition(), Faction.LOVERS)
        self.assertTrue(game.did_player_win(1))
        self.assertTrue(game.did_player_win(2))
        self.assertFalse(game.did_player_win(3))

    def test_invalid_custom_setup(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_special_roles = ["SEER", "SEER", "UNKNOWN"]
        self.assertTrue(game.validate_role_setup())

    def test_malformed_custom_setup_rejected_without_exception(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_special_roles = None
        self.assertTrue(game.validate_role_setup())
        game.settings.custom_special_roles = []
        game.settings.custom_wolf_count = True
        self.assertTrue(game.validate_role_setup())


class NightPipelineTests(unittest.TestCase):
    def test_submission_only_records_intent(self):
        game = make_game(Role.WITCH, Role.VILLAGER)
        submit(game, 1, ActionKind.WITCH_POISON, 2)
        self.assertTrue(game.players[2].is_alive)
        self.assertFalse(game.players[1].witch_poison_used)
        self.assertIsNone(game.night_witch_poison)
        self.assertEqual(game.resolve_night().deaths, (2,))

    def test_repeated_resolution_returns_same_frozen_snapshot(self):
        game = make_game(Role.WITCH, Role.WOLF)
        submit(game, 1, ActionKind.WITCH_POISON, 2)
        result = game.resolve_night()
        logs = len(game.replay_logs)
        self.assertIs(game.resolve_night(), result)
        self.assertEqual(len(game.replay_logs), logs)
        self.assertEqual(result.deaths, (2,))
        self.assertTrue(game.players[1].witch_poison_used)
        with self.assertRaises(FrozenInstanceError):
            result.deaths = (2,)

    def test_late_locked_duplicate_and_previous_night_rejected(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        first = ActionIntent(game.night_count, 1, ActionKind.WOLF_VOTE, (2,))
        game.submit_night_action(first)
        with self.assertRaises(ValueError):
            game.submit_night_action(first)
        game.lock_night()
        with self.assertRaises(ValueError):
            game.submit_night_action(first)
        game.start_night()
        with self.assertRaises(ValueError):
            game.submit_night_action(first)
        game.night_deadline = 0
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WOLF_VOTE, 2)

    def test_wrong_phase_rejected(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        game.phase = GamePhase.DAY_VOTE
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WOLF_VOTE, 2)

    def test_force_stopped_game_cannot_resolve(self):
        game = make_game(Role.WOLF, Role.VILLAGER)
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        game.phase = GamePhase.GAME_END
        with self.assertRaises(ValueError):
            game.resolve_night()
        self.assertTrue(game.players[2].is_alive)

    def test_bad_actor_role_target_and_self_rejected(self):
        game = make_game(Role.WOLF, Role.VILLAGER, Role.SEER)
        for actor, kind, targets in (
            (99, ActionKind.WOLF_VOTE, (2,)),
            (2, ActionKind.WOLF_VOTE, (3,)),
            (1, ActionKind.WOLF_VOTE, (1,)),
            (1, ActionKind.WOLF_VOTE, (99,)),
            (3, ActionKind.SEER, (3,)),
            (3, ActionKind.SEER, (1, 2)),
        ):
            with self.subTest(actor=actor, kind=kind, targets=targets), self.assertRaises(ValueError):
                game.submit_night_action(ActionIntent(game.night_count, actor, kind, targets))
        game.players[2].is_alive = False
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WOLF_VOTE, 2)

    def test_guard_cannot_repeat_previous_target(self):
        game = make_game(Role.GUARD, Role.VILLAGER)
        game.players[1].protected_last_night = 2
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.GUARD, 2)

    def test_cupid_requires_distinct_targets_and_first_night(self):
        game = make_game(Role.CUPID, Role.VILLAGER, Role.WOLF)
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.CUPID, 2, 2)
        game.start_night()
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.CUPID, 2, 3)

    def test_white_wolf_even_night_and_wolf_target_only(self):
        game = make_game(Role.WHITE_WOLF, Role.WOLF, Role.VILLAGER)
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WHITE_WOLF, 2)
        game.start_night()
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WHITE_WOLF, 3)
        submit(game, 1, ActionKind.WHITE_WOLF, 2)
        self.assertEqual(game.resolve_night().deaths, (2,))

    def test_spent_potions_rejected(self):
        game = make_game(Role.WITCH, Role.VILLAGER)
        game.players[1].witch_poison_used = True
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WITCH_POISON, 2)
        game.players[1].witch_save_used = True
        with self.assertRaises(ValueError):
            submit(game, 1, ActionKind.WITCH_SAVE, 2)

    def test_wolf_preview_pure_and_tie_independent_of_submission_order(self):
        one = make_game(Role.WOLF, Role.WOLF, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER)
        two = make_game(Role.WOLF, Role.WOLF, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER)
        for game, votes in ((one, ((1, 4), (2, 3))), (two, ((2, 3), (1, 4)))):
            for actor, target in votes:
                submit(game, actor, ActionKind.WOLF_VOTE, target)
            before = len(game.replay_logs)
            with patch("app.discord_bot.modules.masoi_engine.random.choice", side_effect=AssertionError("preview draws RNG")):
                self.assertEqual(game.resolve_wolf_targets(), [3])
                self.assertEqual(game.resolve_wolf_targets(), [3])
            self.assertEqual(len(game.replay_logs), before)
        self.assertEqual(one.resolve_night().deaths, two.resolve_night().deaths)

    def test_fury_replay_same_seed_and_cached_targets(self):
        games = [make_game(Role.WOLF, Role.VILLAGER, Role.VILLAGER, Role.VILLAGER) for _ in range(2)]
        for game in games:
            game.night_seed = 1234
            game.wolf_fury_active = True
            submit(game, 1, ActionKind.WOLF_VOTE, 2)
            self.assertEqual(game.resolve_wolf_targets(), [2])
        results = [game.resolve_night() for game in games]
        self.assertEqual(results[0], results[1])
        self.assertEqual(len(results[0].deaths), 2)
        self.assertEqual(games[0].resolve_wolf_targets(), list(results[0].wolf_targets))

    def test_blocked_wolf_vote_removed_before_tally(self):
        game = make_game(Role.WOLF, Role.WOLF, Role.HARLOT, Role.VILLAGER, Role.VILLAGER)
        submit(game, 1, ActionKind.WOLF_VOTE, 4)
        submit(game, 2, ActionKind.WOLF_VOTE, 5)
        submit(game, 3, ActionKind.HARLOT, 1)
        self.assertEqual(game.resolve_night().deaths, (5,))

    def test_blocked_guard_does_not_save(self):
        game = make_game(Role.WOLF, Role.GUARD, Role.HARLOT, Role.VILLAGER)
        submit(game, 1, ActionKind.WOLF_VOTE, 4)
        submit(game, 2, ActionKind.GUARD, 4)
        submit(game, 3, ActionKind.HARLOT, 2)
        self.assertEqual(game.resolve_night().deaths, (4,))
        self.assertEqual(game.players[2].guard_saved_count, 0)

    def test_blocked_piper_and_cupid_have_no_effect(self):
        for role, kind, targets in (
            (Role.CUPID, ActionKind.CUPID, (2, 3)),
            (Role.PIPER, ActionKind.PIPER, (2, 3)),
        ):
            game = make_game(role, Role.HARLOT, Role.WOLF)
            submit(game, 1, kind, *targets)
            submit(game, 2, ActionKind.HARLOT, 1)
            game.resolve_night()
            self.assertIsNone(game.players[2].lover_id)
            self.assertFalse(game.players[2].piper_charmed)
            self.assertFalse(game.players[3].piper_charmed)

    def test_dying_seer_and_phantom_actions_still_apply(self):
        game = make_game(Role.SEER, Role.PHANTOM_WOLF, Role.WITCH, Role.VILLAGER)
        submit(game, 1, ActionKind.SEER, 4)
        submit(game, 2, ActionKind.PHANTOM, 4)
        submit(game, 2, ActionKind.WOLF_VOTE, 1)
        submit(game, 3, ActionKind.WITCH_POISON, 2)
        result = game.resolve_night()
        self.assertEqual(result.deaths, (1, 2))
        self.assertIn("SÓI", game.night_seer_result)
        self.assertFalse(game.players[1].seer_found_wolf)

    def test_dying_witch_can_poison_and_save(self):
        game = make_game(Role.WOLF, Role.WITCH, Role.VILLAGER)
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        submit(game, 2, ActionKind.WITCH_POISON, 1)
        self.assertEqual(game.resolve_night().deaths, (1, 2))

    def test_guard_blocks_independent_attack_without_double_bonus(self):
        game = make_game(Role.WOLF, Role.SERIAL_KILLER, Role.GUARD, Role.VILLAGER)
        submit(game, 1, ActionKind.WOLF_VOTE, 4)
        submit(game, 2, ActionKind.SERIAL_KILL, 4)
        submit(game, 3, ActionKind.GUARD, 4)
        self.assertEqual(game.resolve_night().deaths, ())
        self.assertEqual(game.players[3].guard_saved_count, 1)

    def test_poison_not_cancelled_by_guard(self):
        game = make_game(Role.WITCH, Role.GUARD, Role.VILLAGER)
        submit(game, 1, ActionKind.WITCH_POISON, 3)
        submit(game, 2, ActionKind.GUARD, 3)
        self.assertEqual(game.resolve_night().deaths, (3,))

    def test_lover_cub_death_triggers_fury_and_hunter_continuation(self):
        game = make_game(Role.WOLF, Role.HUNTER, Role.WOLF_CUB, Role.VILLAGER)
        game.players[2].lover_id = 3
        game.players[3].lover_id = 2
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        result = game.resolve_night()
        self.assertEqual(result.deaths, (2, 3))
        self.assertEqual(result.pending_hunters, (2,))
        self.assertTrue(game.wolf_fury_pending)
        self.assertIsNone(game.check_win_condition())
        self.assertEqual(game.resolve_hunter_shot(2, 1), (1,))
        self.assertEqual(game.check_win_condition(), Faction.VILLAGER)
        self.assertEqual(result.deaths, (2, 3))  # Base night snapshot remains unchanged.
        with self.assertRaises(ValueError):
            game.resolve_hunter_shot(2, 4)

    def test_hunter_kill_promotes_apprentice(self):
        other = make_game(Role.HUNTER, Role.SEER, Role.APPRENTICE_SEER)
        other.players[1].is_alive = False
        self.assertEqual(other.resolve_hunter_shot(1, 2), (2,))
        self.assertTrue(other.players[3].apprentice_promoted)

    def test_day_lover_death_promotes_apprentice(self):
        game = make_game(Role.VILLAGER, Role.SEER, Role.APPRENTICE_SEER, Role.WOLF)
        game.players[1].lover_id = 2
        game.players[2].lover_id = 1
        game.day_votes = {3: 1}
        self.assertEqual(game.resolve_day_vote(), 1)
        self.assertTrue(game.players[3].apprentice_promoted)

    def test_elder_cursed_and_sk_wolf_immunities(self):
        for role in (Role.ELDER, Role.CURSED, Role.SERIAL_KILLER):
            with self.subTest(role=role):
                game = make_game(Role.WOLF, role)
                submit(game, 1, ActionKind.WOLF_VOTE, 2)
                self.assertEqual(game.resolve_night().deaths, ())
                if role == Role.ELDER:
                    self.assertEqual(game.players[2].elder_lives, 1)
                if role == Role.CURSED:
                    self.assertTrue(game.players[2].is_wolf)

    def test_rusty_curse_delayed_one_night(self):
        game = make_game(Role.WOLF, Role.RUSTY_KNIGHT, Role.VILLAGER)
        submit(game, 1, ActionKind.WOLF_VOTE, 2)
        self.assertEqual(game.resolve_night().deaths, (2,))
        game.start_night()
        self.assertEqual(game.resolve_night().deaths, (1,))

    def test_girl_detection_uses_night_seed(self):
        for seed, caught in ((0, False), (1, True)):
            with self.subTest(seed=seed):
                game = make_game(Role.WOLF, Role.THE_GIRL, Role.VILLAGER)
                game.night_seed = seed
                submit(game, 2, ActionKind.GIRL)
                result = game.resolve_night()
                self.assertEqual(game.girl_caught, caught)
                self.assertEqual(result.deaths, (2,) if caught else ())

    def test_custom_immediate_wolf_majority_rejected(self):
        game = make_game(*([Role.VILLAGER] * 5))
        game.settings.role_setup_mode = "CUSTOM"
        game.settings.custom_wolf_count = 3
        self.assertTrue(game.validate_role_setup())

