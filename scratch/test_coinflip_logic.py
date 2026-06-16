import os
import sys
import unittest
from datetime import datetime

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.coinflip import (
    get_user_vip,
    get_user_lucky_side,
    check_and_unlock_achievements,
    parse_bet_amount
)

class TestCoinFlipLogic(unittest.TestCase):
    def setUp(self):
        self.economy = Economy()
        self.user_id = 999999901
        # Clear mock data
        self.economy.cur.execute("DELETE FROM user_coinflip WHERE user_id = ?", (self.user_id,))
        self.economy.conn.commit()

    def test_vip_tiers(self):
        stats_bronze = {"plays": 5}
        self.assertEqual(get_user_vip(stats_bronze)["name"], "Bronze")
        self.assertEqual(get_user_vip(stats_bronze)["title"], "🪙 Người Tung Xu")

        stats_silver = {"plays": 15}
        self.assertEqual(get_user_vip(stats_silver)["name"], "Silver")

        stats_gold = {"plays": 75}
        self.assertEqual(get_user_vip(stats_gold)["name"], "Gold")

        stats_diamond = {"plays": 200}
        self.assertEqual(get_user_vip(stats_diamond)["name"], "Diamond")

    def test_lucky_side(self):
        # Lucky side is heads or tails
        lucky = get_user_lucky_side(self.user_id)
        self.assertIn(lucky, ["heads", "tails"])
        
        # Test consistency within the same day
        lucky_again = get_user_lucky_side(self.user_id)
        self.assertEqual(lucky, lucky_again)

    def test_achievements_unlock(self):
        stats = {
            "plays": 1,
            "wins": 0,
            "streak": 0,
            "achievements": []
        }
        # First play
        unlocked = check_and_unlock_achievements(stats, 1000)
        self.assertEqual(unlocked, ["first_flip"])

        # High bet and wins
        stats_win_10 = {
            "plays": 10,
            "wins": 10,
            "streak": 5,
            "achievements": ["first_flip"]
        }
        unlocked = check_and_unlock_achievements(stats_win_10, 1_500_000)
        # Should unlock wins_10, streak_5, and bet_1m
        self.assertIn("wins_10", unlocked)
        self.assertIn("streak_5", unlocked)
        self.assertIn("bet_1m", unlocked)

    def test_parse_bet_amount(self):
        self.assertEqual(parse_bet_amount("100k", 500000), 100000)
        self.assertEqual(parse_bet_amount("2.5m", 5000000), 2500000)
        self.assertEqual(parse_bet_amount("all", 9999), 9999)
        self.assertEqual(parse_bet_amount("1,000", 5000), 1000)

    def test_database_integration(self):
        stats = self.economy.get_coinflip(self.user_id)
        self.assertEqual(stats["plays"], 0)
        self.assertEqual(stats["wins"], 0)
        self.assertEqual(stats["streak"], 0)

        # Update plays & wins
        self.economy.update_coinflip(
            self.user_id,
            plays=1,
            wins=1,
            profit=10000,
            streak=1,
            max_streak=1,
            max_win_amount=10000,
            achievements=["first_flip"]
        )

        updated_stats = self.economy.get_coinflip(self.user_id)
        self.assertEqual(updated_stats["plays"], 1)
        self.assertEqual(updated_stats["wins"], 1)
        self.assertEqual(updated_stats["profit"], 10000)
        self.assertEqual(updated_stats["achievements"], ["first_flip"])

if __name__ == "__main__":
    unittest.main()
