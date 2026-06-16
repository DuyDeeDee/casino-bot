import os
import sys
import unittest
from unittest.mock import MagicMock

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# Reroute database path for unit testing to avoid SQLite locks with the running bot
import app.discord_bot.modules.economy as economy_mod
economy_mod.DATABASE_PATH = economy_mod.Path("data/test_economy.db")

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.roulette import (
    parse_bet_amount,
    parse_bet_choice,
    check_win,
    get_payout_multiplier,
    get_vietnamese_bet_name,
    VIP_TIERS,
    get_user_vip
)

class TestRouletteMultiBetLogic(unittest.TestCase):
    def setUp(self):
        self.economy = Economy()
        self.user_id = 999999902
        # Clear mock data
        self.economy.cur.execute("DELETE FROM user_roulette WHERE user_id = ?", (self.user_id,))
        self.economy.cur.execute("DELETE FROM economy WHERE user_id = ?", (self.user_id,))
        self.economy.conn.commit()

    def test_parse_bet_amount(self):
        self.assertEqual(parse_bet_amount("10k", 500000), 10000)
        self.assertEqual(parse_bet_amount("2.5m", 5000000), 2500000)
        self.assertEqual(parse_bet_amount("all", 9999), 9999)
        self.assertEqual(parse_bet_amount("1,000", 5000), 1000)

    def test_parse_bet_choice(self):
        self.assertEqual(parse_bet_choice("đỏ"), ("color", "red"))
        self.assertEqual(parse_bet_choice("black"), ("color", "black"))
        self.assertEqual(parse_bet_choice("even"), ("even_odd", "even"))
        self.assertEqual(parse_bet_choice("lẻ"), ("even_odd", "odd"))
        self.assertEqual(parse_bet_choice("low"), ("low_high", "low"))
        self.assertEqual(parse_bet_choice("high"), ("low_high", "high"))
        self.assertEqual(parse_bet_choice("col1"), ("column", "col1"))
        self.assertEqual(parse_bet_choice("tá2"), ("dozen", "dozen2"))
        self.assertEqual(parse_bet_choice("17"), ("number", "17"))
        self.assertEqual(parse_bet_choice("7 11 15 20"), ("number", "7 11 15 20"))
        self.assertIsNone(parse_bet_choice("invalid"))

    def test_check_win_conditions(self):
        # Color red / black / green (0)
        self.assertTrue(check_win("color", "red", 1)) # 1 is red
        self.assertFalse(check_win("color", "red", 2)) # 2 is black
        self.assertTrue(check_win("color", "green", 0))
        self.assertFalse(check_win("color", "green", 5))

        # Even / odd
        self.assertTrue(check_win("even_odd", "even", 2))
        self.assertFalse(check_win("even_odd", "even", 3))
        self.assertFalse(check_win("even_odd", "even", 0)) # 0 is green, not even/odd

        # Low / high
        self.assertTrue(check_win("low_high", "low", 10))
        self.assertTrue(check_win("low_high", "high", 25))
        self.assertFalse(check_win("low_high", "low", 0))

        # Column / dozen
        self.assertTrue(check_win("column", "col1", 1))
        self.assertTrue(check_win("dozen", "dozen1", 12))
        self.assertFalse(check_win("dozen", "dozen3", 12))

        # Specific number / multiple numbers
        self.assertTrue(check_win("number", "17", 17))
        self.assertTrue(check_win("number", "7 11 15 20", 11))
        self.assertFalse(check_win("number", "7 11 15 20", 12))

    def test_payout_multipliers(self):
        # Standard payouts
        self.assertEqual(get_payout_multiplier("color", "red", 7), 2)
        self.assertEqual(get_payout_multiplier("color", "green", 7), 36)
        self.assertEqual(get_payout_multiplier("even_odd", "even", 7), 2)
        self.assertEqual(get_payout_multiplier("column", "col1", 7), 3)
        self.assertEqual(get_payout_multiplier("dozen", "dozen1", 7), 3)
        self.assertEqual(get_payout_multiplier("number", "17", 7), 36)
        
        # Lucky number payout bonus (x40)
        self.assertEqual(get_payout_multiplier("number", "7", 7), 40)
        # Multiple numbers payout
        self.assertEqual(get_payout_multiplier("number", "7 11 15 20", 7), 9)

    def test_vietnamese_bet_names(self):
        self.assertEqual(get_vietnamese_bet_name("color", "red"), "🔴 Đỏ (Red)")
        self.assertEqual(get_vietnamese_bet_name("even_odd", "even"), "⚪ Chẵn (Even)")
        self.assertEqual(get_vietnamese_bet_name("number", "17"), "🔢 Số 17")
        self.assertEqual(get_vietnamese_bet_name("number", "7 11 15 20"), "🎲 Nhiều số: 7, 11, 15, 20")

    def test_database_multi_spin_flow(self):
        # Ensure user has enough money initially
        self.economy._ensure_entry(self.user_id)
        self.economy.add_money(self.user_id, 1_000_000)
        
        profile = self.economy.get_entry(self.user_id)
        self.assertEqual(profile[1], 1_000_000)

        # Simulate placing multiple bets:
        # 1. Red: 100k
        # 2. Even: 50k
        # 3. Number 17: 10k
        bets = [
            {"type": "color", "choice": "red", "amount": 100_000},
            {"type": "even_odd", "choice": "even", "amount": 50_000},
            {"type": "number", "choice": "17", "amount": 10_000},
        ]
        
        total_bet = sum(b["amount"] for b in bets)
        self.assertEqual(total_bet, 160_000)

        # Deduct total bet money
        self.economy.add_money(self.user_id, -total_bet)
        profile = self.economy.get_entry(self.user_id)
        self.assertEqual(profile[1], 840_000)

        # Let's say rolled number is 14 (which is Red, Even, not 17)
        rolled_num = 14
        lucky_number = 17 # Suppose 17 is daily lucky number
        
        stats = self.economy.get_roulette(self.user_id)
        self.assertEqual(stats["chips"], 0) # starting chips = 0

        # Calculate outcomes
        total_payout = 0
        total_profit = 0
        any_won = False
        
        for b in bets:
            won = check_win(b["type"], b["choice"], rolled_num)
            if won:
                any_won = True
                multiplier = get_payout_multiplier(b["type"], b["choice"], lucky_number)
                base_payout = b["amount"] * multiplier
                # Chip bonus (0.5% per chip)
                chip_bonus_percent = stats["chips"] * 0.005
                chip_bonus = int(base_payout * chip_bonus_percent)
                payout = base_payout + chip_bonus
                p_profit = payout - b["amount"]
                
                total_payout += payout
                total_profit += p_profit
            else:
                p_profit = -b["amount"]
                total_profit += p_profit

        # Expected calculations:
        # Red: 100k * 2 = 200k payout. Profit = +100k. (Won)
        # Even: 50k * 2 = 100k payout. Profit = +50k. (Won)
        # 17: Lost. Profit = -10k. (Lost)
        # Total payout: 300k. Total profit: +140k.
        self.assertTrue(any_won)
        self.assertEqual(total_payout, 300_000)
        self.assertEqual(total_profit, 140_000)

        # Handle chips
        new_chips_count = stats["chips"]
        if any_won:
            new_chips_count = 0
            self.economy.add_money(self.user_id, total_payout)
        else:
            if stats["chips"] < 10:
                new_chips_count = stats["chips"] + 1

        profile = self.economy.get_entry(self.user_id)
        self.assertEqual(profile[1], 1_140_000) # 840k + 300k payout

        # Update stats in DB
        plays_delta = 1
        won_round = total_profit > 0
        wins_delta = 1 if won_round else 0
        losses_delta = 0 if won_round else 1
        
        new_streak = stats["streak"] + 1 if won_round else 0
        new_max_streak = max(stats["max_streak"], new_streak)
        
        num_stats = stats.get("number_stats", {})
        num_str = str(rolled_num)
        num_stats[num_str] = num_stats.get(num_str, 0) + 1

        self.economy.update_roulette(
            self.user_id,
            plays=plays_delta,
            wins=wins_delta,
            losses=losses_delta,
            profit=total_profit,
            streak=new_streak,
            max_streak=new_max_streak,
            chips=new_chips_count,
            number_stats=num_stats,
            achievements=[]
        )

        updated_stats = self.economy.get_roulette(self.user_id)
        self.assertEqual(updated_stats["plays"], 1)
        self.assertEqual(updated_stats["wins"], 1)
        self.assertEqual(updated_stats["losses"], 0)
        self.assertEqual(updated_stats["profit"], 140_000)
        self.assertEqual(updated_stats["streak"], 1)
        self.assertEqual(updated_stats["max_streak"], 1)
        self.assertEqual(updated_stats["chips"], 0)
        self.assertEqual(updated_stats["number_stats"][str(rolled_num)], 1)

    def test_run_multi_spin_engine(self):
        import asyncio
        from unittest.mock import AsyncMock, MagicMock
        from app.discord_bot.cogs.roulette import Roulette

        # Setup mock bot client
        client_mock = MagicMock()
        client_mock.get_user = MagicMock(return_value=None)
        
        # Instantiate Roulette cog
        cog = Roulette(client_mock)
        cog.economy = self.economy
        
        # Setup 2 users with money
        user1_id = 999999911
        user2_id = 999999922
        
        self.economy.cur.execute("DELETE FROM user_roulette WHERE user_id IN (?, ?)", (user1_id, user2_id))
        self.economy.cur.execute("DELETE FROM economy WHERE user_id IN (?, ?)", (user1_id, user2_id))
        self.economy.conn.commit()
        
        self.economy._ensure_entry(user1_id)
        self.economy.add_money(user1_id, 100_000)
        self.economy._ensure_entry(user2_id)
        self.economy.add_money(user2_id, 200_000)
        
        # Lobby object
        lobby = {
            "message": AsyncMock(),
            "host_id": user1_id,
            "bets": {
                user1_id: [{"type": "color", "choice": "red", "amount": 50_000}],
                user2_id: [{"type": "number", "choice": "17", "amount": 30_000}]
            }
        }
        
        # Mock interaction / ctx
        msg_mock = AsyncMock()
        ctx_mock = AsyncMock()
        ctx_mock.send = AsyncMock(return_value=msg_mock)
        ctx_mock.followup.send = AsyncMock(return_value=msg_mock)
        
        # Run async spin resolution
        try:
            asyncio.run(cog.run_multi_spin(ctx_mock, MagicMock(id=user1_id), lobby))
        except Exception as e:
            import traceback
            traceback.print_exc()
            raise e
        
        # Check that stats were updated in DB!
        stats1 = self.economy.get_roulette(user1_id)
        stats2 = self.economy.get_roulette(user2_id)
        
        self.assertEqual(stats1["plays"], 1)
        self.assertEqual(stats2["plays"], 1)
        
        # Clean up database records
        self.economy.cur.execute("DELETE FROM user_roulette WHERE user_id IN (?, ?)", (user1_id, user2_id))
        self.economy.cur.execute("DELETE FROM economy WHERE user_id IN (?, ?)", (user1_id, user2_id))
        self.economy.conn.commit()

if __name__ == "__main__":
    unittest.main()
