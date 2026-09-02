import os
import shutil
import sqlite3
import tempfile
import time
import unittest

from pathlib import Path

from app.discord_bot.modules.betting import parse_bet_amount
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.sports_engine import (
    TEAMS,
    calculate_base_odds,
    calculate_hybrid_payout,
    calculate_match_probabilities,
    simulate_tick,
)


class TestSportsEngineAndSettlement(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_economy.db"

        # Monkey patch db path for test instance
        import app.discord_bot.modules.economy as eco_mod
        self.orig_db_path = eco_mod.DATABASE_PATH
        eco_mod.DATABASE_PATH = self.db_path

        self.economy = Economy()

        # Seed initial test users
        self.economy.new_entry(1001)
        self.economy.new_entry(1002)
        self.economy.new_entry(1003)
        self.economy.add_money(1001, 10_000_000)
        self.economy.add_money(1002, 10_000_000)
        self.economy.add_money(1003, 10_000_000)
        self.economy.set_setting("jackpot_pool", "1000000")

    def tearDown(self):
        self.economy.close()
        import app.discord_bot.modules.economy as eco_mod
        eco_mod.DATABASE_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_odds_and_probabilities(self):
        t1 = TEAMS["RMA"]
        t2 = TEAMS["SPO"]
        probs = calculate_match_probabilities(t1, t2)
        odds = calculate_base_odds(probs)

        # Probabilities sum to 1.0
        total_p = probs["1"] + probs["X"] + probs["2"]
        self.assertAlmostEqual(total_p, 1.0, places=2)

        # Stronger team at home (Real Madrid vs Sporting CP) should have highest win prob
        self.assertGreater(probs["1"], probs["2"])
        self.assertLess(odds["1"], odds["2"])

    def test_one_sided_pool_hybrid_guarantee(self):
        """When 100% of bettors bet on 1 side and win, they must NOT lose 5%."""
        match_id = self.economy.create_sports_match(
            t1="RMA",
            t2="BAR",
            kickoff=int(time.time()) + 3600,
        )

        # Both users bet on '1'
        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.50)
        self.economy.place_sports_bet(match_id, 1002, "1", 2_000_000, base_odds=1.50)

        # Balances after bet
        self.assertEqual(self.economy.get_entry(1001)[1], 9_000_000)
        self.assertEqual(self.economy.get_entry(1002)[1], 8_000_000)

        # Settle with '1' winning (Score: 2 - 1)
        res = self.economy.settle_sports_match(match_id, "1", 2, 1)

        self.assertFalse(res["already_settled"])
        # User 1001 bet 1M -> should receive at least 1.5M (500k profit)
        bal_1001 = self.economy.get_entry(1001)[1]
        bal_1002 = self.economy.get_entry(1002)[1]

        self.assertEqual(bal_1001, 9_000_000 + 1_500_000)
        self.assertEqual(bal_1002, 8_000_000 + 3_000_000)

        # Tickets should be marked 'won'
        tickets = self.economy.get_sports_tickets_for_match(match_id)
        for t in tickets:
            self.assertEqual(t["status"], "won")
            self.assertGreater(t["payout"], t["amount"])

    def test_multi_sided_pool_settlement(self):
        """Pari-mutuel distribution when multiple sides have bets."""
        match_id = self.economy.create_sports_match(
            t1="MCI",
            t2="LIV",
            kickoff=int(time.time()) + 3600,
        )

        # User 1001 bets 1M on '1', User 1002 bets 1M on 'X', User 1003 bets 2M on '2'
        # Total pool = 4M
        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=2.10)
        self.economy.place_sports_bet(match_id, 1002, "X", 1_000_000, base_odds=3.20)
        self.economy.place_sports_bet(match_id, 1003, "2", 2_000_000, base_odds=3.00)

        # Match ends in '1' (3 - 1)
        res = self.economy.settle_sports_match(match_id, "1", 3, 1)

        # Total pool = 4M, 5% rake = 200k, prize = 3.8M
        self.assertEqual(res["total_pool"], 4_000_000)
        self.assertEqual(res["rake_amount"], 200_000)
        self.assertEqual(res["total_payout"], 3_800_000)

        # User 1001 won the entire prize pool (3.8M)
        bal_1001 = self.economy.get_entry(1001)[1]
        self.assertEqual(bal_1001, 9_000_000 + 3_800_000)

        # Jackpot pool should have received 200k rake
        jp = int(self.economy.get_setting("jackpot_pool", "0"))
        self.assertEqual(jp, 1_000_000 + 200_000)

    def test_no_winners_pool_to_jackpot(self):
        """If no one picked the winning outcome, whole pot goes to Jackpot."""
        match_id = self.economy.create_sports_match(
            t1="ARS",
            t2="CHE",
            kickoff=int(time.time()) + 3600,
        )

        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.80)
        self.economy.place_sports_bet(match_id, 1002, "2", 1_000_000, base_odds=3.50)

        # Match ends in Draw 'X' (1 - 1)
        res = self.economy.settle_sports_match(match_id, "X", 1, 1)

        self.assertEqual(res["total_payout"], 0)
        jp = int(self.economy.get_setting("jackpot_pool", "0"))
        self.assertEqual(jp, 1_000_000 + 2_000_000)

    def test_idempotent_settlement_prevents_double_payout(self):
        """Settling twice must not credit users twice."""
        match_id = self.economy.create_sports_match(
            t1="BAY",
            t2="BVB",
            kickoff=int(time.time()) + 3600,
        )

        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.60)
        res1 = self.economy.settle_sports_match(match_id, "1", 2, 0)
        bal_after_first = self.economy.get_entry(1001)[1]

        # Settle again
        res2 = self.economy.settle_sports_match(match_id, "1", 2, 0)
        self.assertTrue(res2["already_settled"])

        bal_after_second = self.economy.get_entry(1001)[1]
        self.assertEqual(bal_after_first, bal_after_second)

    def test_refund_sports_match(self):
        """Admin cancelling a match must refund 100% of stakes."""
        match_id = self.economy.create_sports_match(
            t1="INT",
            t2="JUV",
            kickoff=int(time.time()) + 3600,
        )

        self.economy.place_sports_bet(match_id, 1001, "1", 2_000_000)
        self.economy.place_sports_bet(match_id, 1002, "X", 1_500_000)

        res = self.economy.refund_sports_match(match_id, reason="Bad Weather")

        self.assertEqual(res["refunded_count"], 2)
        self.assertEqual(res["refunded_total"], 3_500_000)
        self.assertEqual(self.economy.get_entry(1001)[1], 10_000_000)
        self.assertEqual(self.economy.get_entry(1002)[1], 10_000_000)

        match = self.economy.get_sports_match(match_id)
        self.assertEqual(match["status"], "cancelled")

    def test_bet_parser_and_formats(self):
        """Validate bet amount parser with shortcuts."""
        self.assertEqual(parse_bet_amount("500k", 10_000_000), 500_000)
        self.assertEqual(parse_bet_amount("1.5m", 10_000_000), 1_500_000)
        self.assertEqual(parse_bet_amount("2tr", 10_000_000), 2_000_000)
        self.assertEqual(parse_bet_amount("all", 5_000_000), 5_000_000)
        self.assertEqual(parse_bet_amount("tất tay", 3_000_000), 3_000_000)

    def test_league_standings(self):
        """Verify standings updates correctly after a match."""
        self.economy.update_sports_league_match(season_id=1, t1="RMA", t2="BAR", s1=3, s2=1)
        table = self.economy.get_sports_league_table(season_id=1)

        rma = next(r for r in table if r["team_code"] == "RMA")
        bar = next(r for r in table if r["team_code"] == "BAR")

        self.assertEqual(rma["points"], 3)
        self.assertEqual(rma["won"], 1)
        self.assertEqual(rma["gd"], 2)
        self.assertEqual(rma["form"], "W")

        self.assertEqual(bar["points"], 0)
        self.assertEqual(bar["lost"], 1)
        self.assertEqual(bar["gd"], -2)
        self.assertEqual(bar["form"], "L")


    def test_zero_bets_match_settlement(self):
        """A match with 0 bets settles gracefully without errors."""
        match_id = self.economy.create_sports_match(
            t1="PSG",
            t2="ATM",
            kickoff=int(time.time()) + 3600,
        )
        res = self.economy.settle_sports_match(match_id, "2", 0, 1)
        self.assertEqual(res["total_pool"], 0)
        self.assertEqual(res["total_payout"], 0)
        self.assertEqual(res["payouts"], {})

        match = self.economy.get_sports_match(match_id)
        self.assertEqual(match["status"], "finished")
        self.assertEqual(match["result"], "2")

    def test_multiple_tickets_same_user(self):
        """User placing multiple bets on the same match receives combined payouts."""
        match_id = self.economy.create_sports_match(
            t1="RMA",
            t2="LIV",
            kickoff=int(time.time()) + 3600,
        )
        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.50)
        self.economy.place_sports_bet(match_id, 1001, "1", 2_000_000, base_odds=1.50)
        self.economy.place_sports_bet(match_id, 1002, "2", 1_000_000, base_odds=3.00)

        res = self.economy.settle_sports_match(match_id, "1", 2, 0)
        # Total pool = 4M, 5% rake = 200k, prize = 3.8M.
        # User 1001 owns 100% of winning pool:
        # Ticket 1 share = 1,266,666, Ticket 2 share = 2,533,333 -> Total payout = 3,799,999 (+1 VND rounding to jackpot)
        self.assertIn(res["total_payout"], (3_799_999, 3_800_000))
        self.assertEqual(res["rake_amount"], 200_000)
        self.assertEqual(self.economy.get_entry(1001)[1], 7_000_000 + res["total_payout"])

    def test_simulation_tick_progression(self):
        """Simulate tick advances minutes, scores, and events."""
        t1 = TEAMS["MCI"]
        t2 = TEAMS["MUN"]
        s1, s2, xg1, xg2, sh1, sot1, sh2, sot2, events = simulate_tick(15, 0, 0, t1, t2)
        self.assertIsInstance(s1, int)
        self.assertIsInstance(s2, int)
        self.assertIsInstance(events, list)


if __name__ == "__main__":
    unittest.main()
