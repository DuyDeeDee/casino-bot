import os
import sys
import unittest
import random

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.tower import (
    TOWER_MULTIPLIERS,
    FLOOR_PROBABILITIES,
    check_and_unlock_tower_achievements,
    parse_bet_amount
)

class TestTowerLogic(unittest.TestCase):
    def setUp(self):
        self.economy = Economy()
        self.user_id = 999999903
        self.economy.cur.execute("DELETE FROM user_tower WHERE user_id = ?", (self.user_id,))
        self.economy.conn.commit()

    def test_multipliers(self):
        self.assertEqual(TOWER_MULTIPLIERS[1], 1.25)
        self.assertEqual(TOWER_MULTIPLIERS[3], 2.40)
        self.assertEqual(TOWER_MULTIPLIERS[6], 8.50)

    def test_parse_bet_amount(self):
        # Setup mock economy values or use simple mock current money
        money = 500000
        self.assertEqual(parse_bet_amount("100k", money), 100000)
        self.assertEqual(parse_bet_amount("15m", money), 15000000)
        self.assertEqual(parse_bet_amount("5000", money), 5000)
        self.assertEqual(parse_bet_amount("abc", money), 0)

    def test_achievements(self):
        stats = {
            "plays": 0,
            "wins": 0,
            "achievements": []
        }
        # First play
        unlocked = check_and_unlock_tower_achievements(stats, {"win": False})
        self.assertEqual(unlocked, ["first_play"])

        # Cashout 2x, lucky escape, survive 3 eggs
        stats_complete = {
            "plays": 5,
            "wins": 3,
            "achievements": ["first_play"]
        }
        game_info = {
            "cashout": True,
            "multiplier": 2.40,
            "floors_cleared": 3,
            "survived_3_eggs": True,
            "multi_egg_floors_count": 2
        }
        unlocked = check_and_unlock_tower_achievements(stats_complete, game_info)
        self.assertIn("cashout_2x", unlocked)
        self.assertNotIn("cashout_5x", unlocked)
        self.assertNotIn("perfect_clear", unlocked)
        self.assertIn("survive_3_eggs", unlocked)
        self.assertIn("lucky_escape", unlocked)

        # Perfect game
        game_info_perfect = {
            "win": True,
            "multiplier": 8.50,
            "floors_cleared": 6,
            "survived_3_eggs": False,
            "multi_egg_floors_count": 1
        }
        unlocked_perfect = check_and_unlock_tower_achievements(stats_complete, game_info_perfect)
        self.assertIn("cashout_2x", unlocked_perfect)
        self.assertIn("cashout_5x", unlocked_perfect)
        self.assertIn("perfect_clear", unlocked_perfect)
        self.assertNotIn("survive_3_eggs", unlocked_perfect)
        self.assertNotIn("lucky_escape", unlocked_perfect)

    def test_database_integration(self):
        stats = self.economy.get_tower_stats(self.user_id)
        self.assertEqual(stats["plays"], 0)
        self.assertEqual(stats["wins"], 0)
        self.assertEqual(stats["streak"], 0)

        # Update plays, wins, profit, streak, achievements
        self.economy.update_tower_stats(
            self.user_id,
            plays=1,
            wins=1,
            profit=75000,
            streak=1,
            max_streak=1,
            achievements=["first_play"]
        )

        updated_stats = self.economy.get_tower_stats(self.user_id)
        self.assertEqual(updated_stats["plays"], 1)
        self.assertEqual(updated_stats["wins"], 1)
        self.assertEqual(updated_stats["profit"], 75000)
        self.assertEqual(updated_stats["streak"], 1)
        self.assertEqual(updated_stats["achievements"], ["first_play"])

    def test_floor_probabilities(self):
        # We check the weight distributions of floor probabilities configuration
        for floor_idx, probs in FLOOR_PROBABILITIES.items():
            total_prob = sum(p[1] for p in probs)
            self.assertAlmostEqual(total_prob, 1.0)
            
            # Floor 1 (0) and 2 (1) should have 0% chance of 3 eggs
            if floor_idx in [0, 1]:
                self.assertEqual(probs[2][0], 3)
                self.assertEqual(probs[2][1], 0.0)

if __name__ == "__main__":
    unittest.main()
