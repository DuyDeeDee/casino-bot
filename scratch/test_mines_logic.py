import os
import sys
import unittest

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.mines import (
    index_to_coordinate,
    check_and_unlock_mines_achievements,
    parse_bet_amount,
    MINES_MULTIPLIERS
)

class TestMinesLogic(unittest.TestCase):
    def setUp(self):
        self.economy = Economy()
        self.user_id = 999999902
        self.economy.cur.execute("DELETE FROM user_mines WHERE user_id = ?", (self.user_id,))
        self.economy.conn.commit()

    def test_coordinate_parsing(self):
        self.assertEqual(index_to_coordinate(0), "A1")
        self.assertEqual(index_to_coordinate(4), "B2")
        self.assertEqual(index_to_coordinate(8), "C3")

    def test_multipliers(self):
        # 3 bombs
        self.assertEqual(MINES_MULTIPLIERS[3][0], 1.25)
        self.assertEqual(MINES_MULTIPLIERS[3][5], 10.80)

    def test_achievements(self):
        stats = {
            "plays": 0,
            "wins": 0,
            "achievements": []
        }
        # First play
        unlocked = check_and_unlock_mines_achievements(stats, {"win": False, "bombs": 3})
        self.assertEqual(unlocked, ["first_play"])

        # Perfect game, cashout 10x, survive 7 bombs
        stats_complete = {
            "plays": 5,
            "wins": 3,
            "achievements": ["first_play"]
        }
        game_info = {
            "win": True,
            "multiplier": 11.50,
            "bombs": 7,
            "opened_cells": 2
        }
        unlocked = check_and_unlock_mines_achievements(stats_complete, game_info)
        self.assertIn("cashout_3x", unlocked)
        self.assertIn("cashout_5x", unlocked)
        self.assertIn("cashout_10x", unlocked)
        self.assertIn("survive_7_bombs", unlocked)
        self.assertIn("clear_all_safe", unlocked)

    def test_database_integration(self):
        stats = self.economy.get_mines_stats(self.user_id)
        self.assertEqual(stats["plays"], 0)
        self.assertEqual(stats["wins"], 0)
        self.assertEqual(stats["streak"], 0)

        # Update plays & wins
        self.economy.update_mines_stats(
            self.user_id,
            plays=1,
            wins=1,
            profit=20000,
            streak=1,
            max_streak=1,
            achievements=["first_play"]
        )

        updated_stats = self.economy.get_mines_stats(self.user_id)
        self.assertEqual(updated_stats["plays"], 1)
        self.assertEqual(updated_stats["wins"], 1)
        self.assertEqual(updated_stats["profit"], 20000)
        self.assertEqual(updated_stats["streak"], 1)
        self.assertEqual(updated_stats["achievements"], ["first_play"])

if __name__ == "__main__":
    unittest.main()
