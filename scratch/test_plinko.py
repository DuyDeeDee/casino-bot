import os
import sys
import unittest

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.plinko import (
    parse_bet_amount,
    check_and_unlock_plinko_achievements,
    RISK_SETTINGS
)

class TestPlinkoLogic(unittest.TestCase):
    def setUp(self):
        self.economy = Economy()
        self.user_id = 999999902
        # Clear mock data
        self.economy.cur.execute("DELETE FROM user_plinko WHERE user_id = ?", (self.user_id,))
        self.economy.conn.commit()

    def test_parse_bet_amount(self):
        self.assertEqual(parse_bet_amount("100k", 500000), 100000)
        self.assertEqual(parse_bet_amount("2.5m", 5000000), 2500000)
        self.assertEqual(parse_bet_amount("all", 9999), 9999)
        self.assertEqual(parse_bet_amount("1,000", 5000), 1000)
        self.assertEqual(parse_bet_amount("1.5k", 5000), 1500)

    def test_risk_settings_sum_weights(self):
        for risk, cfg in RISK_SETTINGS.items():
            self.assertEqual(len(cfg["multipliers"]), len(cfg["weights"]))
            self.assertAlmostEqual(sum(cfg["weights"]), 1.0, places=4)

    def test_achievements_unlock(self):
        # 1. first drop
        stats = {
            "plays": 1,
            "wins": 0,
            "losses": 1,
            "profit": -1000,
            "streak": 0,
            "achievements": []
        }
        unlocked = check_and_unlock_plinko_achievements(stats, 0.5, -1000)
        self.assertEqual(unlocked, ["first_drop"])

        # 2. hit 10x
        stats = {
            "plays": 5,
            "wins": 3,
            "losses": 2,
            "profit": 15000,
            "streak": 2,
            "achievements": ["first_drop"]
        }
        unlocked = check_and_unlock_plinko_achievements(stats, 10.0, 15000)
        self.assertEqual(unlocked, ["hit_10x"])

        # 3. hit 100x
        stats = {
            "plays": 10,
            "wins": 6,
            "losses": 4,
            "profit": 99000,
            "streak": 3,
            "achievements": ["first_drop", "hit_10x"]
        }
        unlocked = check_and_unlock_plinko_achievements(stats, 100.0, 99000)
        self.assertEqual(unlocked, ["hit_100x"])

        # 4. streak 5
        stats = {
            "plays": 12,
            "wins": 8,
            "losses": 4,
            "profit": 50000,
            "streak": 5,
            "achievements": ["first_drop"]
        }
        unlocked = check_and_unlock_plinko_achievements(stats, 1.2, 50000)
        self.assertEqual(unlocked, ["win_streak_5"])

        # 5. profit 10m
        stats = {
            "plays": 100,
            "wins": 60,
            "losses": 40,
            "profit": 12000000,
            "streak": 2,
            "achievements": ["first_drop", "hit_10x", "win_streak_5"]
        }
        unlocked = check_and_unlock_plinko_achievements(stats, 2.0, 12000000)
        self.assertEqual(unlocked, ["profit_10m"])

    def test_database_integration(self):
        stats = self.economy.get_plinko_stats(self.user_id)
        self.assertEqual(stats["plays"], 0)
        self.assertEqual(stats["wins"], 0)
        self.assertEqual(stats["streak"], 0)
        self.assertEqual(stats["profit"], 0)
        self.assertEqual(stats["max_multiplier"], 0.0)

        # Update stats
        self.economy.update_plinko_stats(
            self.user_id,
            plays=1,
            wins=1,
            losses=0,
            profit=9000,
            jackpots=0,
            max_multiplier=10.0,
            streak=1,
            max_streak=1,
            achievements=["first_drop"]
        )

        updated_stats = self.economy.get_plinko_stats(self.user_id)
        self.assertEqual(updated_stats["plays"], 1)
        self.assertEqual(updated_stats["wins"], 1)
        self.assertEqual(updated_stats["profit"], 9000)
        self.assertEqual(updated_stats["max_multiplier"], 10.0)
        self.assertEqual(updated_stats["streak"], 1)
        self.assertEqual(updated_stats["max_streak"], 1)
        self.assertEqual(updated_stats["achievements"], ["first_drop"])

if __name__ == "__main__":
    unittest.main()
