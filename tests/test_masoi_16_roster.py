"""Fixed 16-player roster and one-use Ác Sói shield."""
import unittest
from collections import Counter

from app.discord_bot.modules.masoi_engine import (
    ActionIntent, ActionKind, GamePhase, MasoiGame, Role,
)


def game_with(*roles):
    game = MasoiGame(1, 2, 1, "Host")
    for uid, role in enumerate(roles, 1):
        game.add_player(uid, str(uid))
        game.players[uid].role = role
    return game


class FixedRosterTests(unittest.TestCase):
    def test_room_requires_exactly_sixteen_players(self):
        game = game_with(*([Role.VILLAGER] * 15))
        self.assertTrue(game.validate_role_setup())
        self.assertTrue(game.add_player(16, "16"))
        self.assertFalse(game.add_player(17, "17"))
        self.assertEqual(game.validate_role_setup(), [])

    def test_roster_categories_and_assignment(self):
        for _ in range(30):
            game = game_with(*([Role.VILLAGER] * 16))
            roster = game.preview_roles()
            self.assertEqual(roster, game.preview_roles())
            self.assertEqual(len(roster), 16)
            self.assertEqual(sum(role.faction.name == "WEREWOLF" for role in roster), 4)
            for role in (Role.WOLF, Role.WOLF_SEER, Role.WOLF_GUARD, Role.ARSONIST):
                self.assertEqual(roster.count(role), 1)
            self.assertEqual(len(set(roster) & {Role.WOLF_CUB, Role.YOUNG_WOLF, Role.PHANTOM_WOLF}), 1)
            self.assertEqual(len(set(roster) & {Role.GUARD, Role.DOCTOR, Role.STRONGMAN}), 2)
            self.assertEqual(len(set(roster) & {Role.INVESTIGATOR, Role.SEER, Role.FORENSIC}), 2)
            self.assertEqual(len(set(roster) & {Role.HARLOT, Role.APPRENTICE_SEER}), 1)
            self.assertEqual(len(set(roster) & {Role.WITCH, Role.HUNTER, Role.GUNNER, Role.PRIEST}), 2)
            self.assertEqual(len(set(roster) & {Role.TANNER, Role.HUMAN_HUNTER}), 1)
            self.assertEqual(len(set(roster) & {Role.SCAPEGOAT, Role.ELDER, Role.CUPID, Role.MAYOR, Role.LYCAN, Role.BIGMOUTH}), 3)
            game.assign_roles()
            self.assertEqual(Counter(p.role for p in game.players.values()), Counter(roster))


class WolfGuardTests(unittest.TestCase):
    def submit(self, game, uid, kind, *targets):
        game.submit_night_action(ActionIntent(game.night_count, uid, kind, targets))

    def test_shield_blocks_next_day_execution_once(self):
        game = game_with(Role.WOLF_GUARD, Role.WITCH, Role.VILLAGER, Role.WOLF)
        game.start_night()
        self.submit(game, 1, ActionKind.WOLF_GUARD, 3)
        game.resolve_night()
        game.start_day()
        game.phase = GamePhase.DAY_RESOLVE
        game.day_votes = {1: 3, 2: 3}
        self.assertIsNone(game.resolve_day_vote())
        self.assertTrue(game.players[3].is_alive)
        self.assertTrue(game.players[1].wolf_guard_used)
        game.start_night()
        with self.assertRaises(ValueError):
            self.submit(game, 1, ActionKind.WOLF_GUARD, 2)
        self.submit(game, 2, ActionKind.WITCH_POISON, 3)
        self.assertIn(3, game.resolve_night().deaths)

    def test_shield_blocks_next_night_village_kill_not_solo_fire(self):
        game = game_with(Role.WOLF_GUARD, Role.WITCH, Role.VILLAGER, Role.ARSONIST)
        game.start_night()
        self.submit(game, 1, ActionKind.WOLF_GUARD, 3)
        game.resolve_night()
        game.start_day()
        game.start_night()
        self.submit(game, 2, ActionKind.WITCH_POISON, 3)
        self.assertNotIn(3, game.resolve_night().deaths)
        self.assertTrue(game.players[1].wolf_guard_used)

        other = game_with(Role.WOLF_GUARD, Role.VILLAGER, Role.ARSONIST, Role.WOLF)
        other.start_night()
        self.submit(other, 1, ActionKind.WOLF_GUARD, 2)
        self.submit(other, 3, ActionKind.ARSON_DOUSE, 2, 4)
        other.resolve_night()
        other.start_day()
        other.start_night()
        self.submit(other, 3, ActionKind.ARSON_IGNITE)
        self.assertIn(2, other.resolve_night().deaths)
        self.assertFalse(other.players[1].wolf_guard_used)

    def test_cannot_self_protect(self):
        game = game_with(Role.WOLF_GUARD, Role.VILLAGER)
        game.start_night()
        with self.assertRaises(ValueError):
            self.submit(game, 1, ActionKind.WOLF_GUARD, 1)

    def test_shield_blocks_gunner_and_expires_after_next_night(self):
        game = game_with(Role.WOLF_GUARD, Role.GUNNER, Role.VILLAGER, Role.WOLF)
        game.start_night()
        game.resolve_night()
        game.start_day()
        game.start_night()
        self.submit(game, 1, ActionKind.WOLF_GUARD, 3)
        game.resolve_night()
        game.start_day()
        game.phase = GamePhase.DAY_DISCUSSION
        self.assertEqual(game.resolve_gunner_shot(2, 3), ())
        self.assertTrue(game.players[3].is_alive)
        self.assertEqual(game.players[2].gunner_bullets_used, 1)
        self.assertTrue(game.players[1].wolf_guard_used)

        expired = game_with(Role.WOLF_GUARD, Role.VILLAGER, Role.WOLF)
        expired.start_night()
        self.submit(expired, 1, ActionKind.WOLF_GUARD, 2)
        expired.resolve_night()
        expired.start_day()
        expired.start_night()
        expired.resolve_night()
        expired.start_day()
        expired.phase = GamePhase.DAY_RESOLVE
        expired.day_votes = {1: 2, 3: 2}
        self.assertEqual(expired.resolve_day_vote(), 2)
        self.assertFalse(expired.players[1].wolf_guard_used)


if __name__ == "__main__":
    unittest.main()
