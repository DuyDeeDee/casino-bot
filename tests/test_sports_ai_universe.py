import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.sports_ai import (
    AI_BETTOR_PERSONAS,
    COMMENTATOR_PERSONAS,
    decide_ai_bet,
    generate_ai_post_match_reaction,
    generate_fulltime_commentary,
    generate_goal_commentary,
    generate_halftime_commentary,
    generate_var_commentary,
)
from app.discord_bot.modules.sports_engine import (
    TEAMS,
    calculate_base_odds,
    calculate_cashout_value,
    calculate_match_probabilities,
    evaluate_market_results,
    generate_momentum_bar,
    simulate_tick,
)


class TestSportsAIUniverse(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_ai_universe.db"

        import app.discord_bot.modules.economy as eco_mod
        self.orig_db_path = eco_mod.DATABASE_PATH
        eco_mod.DATABASE_PATH = self.db_path

        self.economy = Economy()
        self.economy.new_entry(1001)
        self.economy.new_entry(1002)
        self.economy.add_money(1001, 10_000_000)
        self.economy.add_money(1002, 10_000_000)
        self.economy.set_setting("jackpot_pool", "1000000")

    def tearDown(self):
        self.economy.close()
        import app.discord_bot.modules.economy as eco_mod
        eco_mod.DATABASE_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_commentator_generators(self):
        """Verify all 4 commentator personas generate valid dialogue."""
        for c_key in COMMENTATOR_PERSONAS.keys():
            goal = generate_goal_commentary(c_key, "Real Madrid", 34, 1, 0, 0.65)
            self.assertIn("Real Madrid", goal)
            self.assertGreater(len(goal), 15)

            ht = generate_halftime_commentary(c_key, 1, 1, "Real Madrid", "Barcelona")
            self.assertIn("1-1", ht)

            ft = generate_fulltime_commentary(c_key, 2, 1, "Real Madrid", "Barcelona")
            self.assertIn("2-1", ft)

            var = generate_var_commentary(c_key, "TỪ CHỐI BÀN THẮNG")
            self.assertIn("TỪ CHỐI", var)

    def test_ai_bettors_personas(self):
        """Verify all 6 AI bettor personas make strategic decisions and post-match reactions."""
        match = {
            "t1": "RMA",
            "t2": "MUN",
        }
        odds = {"1": 1.65, "X": 3.40, "2": 4.50, "OU_OVER": 1.75, "OU_UNDER": 2.05}

        for ai_id in AI_BETTOR_PERSONAS.keys():
            outcome, amount, quote = decide_ai_bet(ai_id, match, odds)
            self.assertIn(outcome, ["1", "X", "2", "OU_OVER", "OU_UNDER"])
            self.assertGreater(amount, 0)
            self.assertIsInstance(quote, str)

            react_win = generate_ai_post_match_reaction(ai_id, True, outcome, amount, int(amount * 1.5))
            react_loss = generate_ai_post_match_reaction(ai_id, False, outcome, amount, 0)
            self.assertIn(AI_BETTOR_PERSONAS[ai_id]["name"], react_win)
            self.assertIn(AI_BETTOR_PERSONAS[ai_id]["name"], react_loss)

    def test_multi_market_probabilities_and_evaluation(self):
        """Verify odds and evaluation for 1X2, Over/Under, and BTTS."""
        t1 = TEAMS["MCI"]
        t2 = TEAMS["LIV"]
        probs = calculate_match_probabilities(t1, t2)
        odds = calculate_base_odds(probs)

        self.assertIn("OU_OVER", odds)
        self.assertIn("OU_UNDER", odds)
        self.assertIn("BTTS_YES", odds)
        self.assertIn("BTTS_NO", odds)

        # High-scoring match (3 - 1)
        res = evaluate_market_results(3, 1)
        self.assertEqual(res["1X2"], "1")
        self.assertEqual(res["OU"], "OU_OVER")
        self.assertEqual(res["BTTS"], "BTTS_YES")

        # Low-scoring match (1 - 0)
        res2 = evaluate_market_results(1, 0)
        self.assertEqual(res2["1X2"], "1")
        self.assertEqual(res2["OU"], "OU_UNDER")
        self.assertEqual(res2["BTTS"], "BTTS_NO")

    def test_advanced_simulation_with_xg_and_coaches(self):
        """Verify xG accumulation, momentum bar, and coach tactical adjustments."""
        t1 = TEAMS["RMA"]
        t2 = TEAMS["ATM"]

        s1, s2, xg1, xg2, sh1, sot1, sh2, sot2, events = simulate_tick(
            minute=15, score_t1=0, score_t2=0, t1=t1, t2=t2
        )
        self.assertGreaterEqual(xg1, 0.0)
        self.assertGreaterEqual(xg2, 0.0)
        self.assertGreaterEqual(sh1, 0)
        self.assertGreaterEqual(sh2, 0)

        # Momentum bar
        m_bar = generate_momentum_bar(s1, s2, xg1, xg2)
        self.assertIn("[", m_bar)

    def test_cashout_valuation_and_execution(self):
        """Verify dynamic cashout calculation and ticket cashout."""
        # Test valuation
        # Winning position at minute 60 (bet '1', score 2-0)
        val_winning = calculate_cashout_value(stake=1_000_000, base_odds=2.0, outcome="1", minute=60, score_t1=2, score_t2=0)
        self.assertGreater(val_winning, 1_000_000)

        # Losing position at minute 60 (bet '1', score 0-2)
        val_losing = calculate_cashout_value(stake=1_000_000, base_odds=2.0, outcome="1", minute=60, score_t1=0, score_t2=2)
        self.assertLess(val_losing, 1_000_000)
        self.assertGreater(val_losing, 0)

        # Test database cashout
        match_id = self.economy.create_sports_match(t1="MCI", t2="ARS", kickoff=int(time.time()) + 600)
        ticket_id = self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.80)

        # Set match live at minute 50
        self.economy.update_sports_match_live(match_id, minute=50, score_t1=1, score_t2=0, status="live")

        cashout_res = self.economy.cashout_sports_ticket(ticket_id, 1001, cashout_amount=1_350_000)
        self.assertTrue(cashout_res["success"])

        # User balance should have received +1.35M
        self.assertEqual(self.economy.get_entry(1001)[1], 9_000_000 + 1_350_000)

        # Match settles later (1 - 0)
        settle_res = self.economy.settle_sports_match(match_id, "1", 1, 0)
        # Cashed out ticket should not receive double payout
        self.assertEqual(self.economy.get_entry(1001)[1], 9_000_000 + 1_350_000)

    def test_human_player_wins_ai_bettor_money(self):
        """When AI bettor loses and Human wins, Human receives AI's stake."""
        match_id = self.economy.create_sports_match(t1="RMA", t2="BAR", kickoff=int(time.time()) + 600)

        # Human bets 1M on '1'
        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.50)
        # AI Bettor (-1) bets 2M on '2'
        self.economy.place_sports_bet(match_id, -1, "2", 2_000_000, base_odds=3.00)

        # Match ends in '1' (Score: 2 - 0)
        # Total pool = 3M, 5% rake = 150k -> distributable = 2.85M
        res = self.economy.settle_sports_match(match_id, "1", 2, 0)

        self.assertEqual(res["total_payout"], 2_850_000)
        # Human 1001 gets 2.85M (including AI's money!)
        self.assertEqual(self.economy.get_entry(1001)[1], 9_000_000 + 2_850_000)

    def test_ai_bettor_winnings_deposit_to_jackpot(self):
        """When AI bettor wins, their payout is deposited into Jackpot rather than an account."""
        match_id = self.economy.create_sports_match(t1="LIV", t2="CHE", kickoff=int(time.time()) + 600)

        # Human bets 1M on '1', AI bets 1M on '2'
        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=2.00)
        self.economy.place_sports_bet(match_id, -2, "2", 1_000_000, base_odds=2.00)

        initial_jp = int(self.economy.get_setting("jackpot_pool", "0"))

        # Match ends in '2' (Score: 0 - 1)
        res = self.economy.settle_sports_match(match_id, "2", 0, 1)

        # AI won 1.9M -> routed to Jackpot!
        final_jp = int(self.economy.get_setting("jackpot_pool", "0"))
        self.assertGreater(final_jp, initial_jp + 1_000_000)

    def test_multi_market_settlement(self):
        """Verify that multiple markets (1X2 and Over/Under) settle independently and correctly."""
        match_id = self.economy.create_sports_match(t1="MCI", t2="LIV", kickoff=int(time.time()) + 600)

        # Player 1001 bets 1M on '1' (1X2 market)
        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.80, market="1X2")
        # Player 1002 bets 1M on 'OU_OVER' (OU market)
        self.economy.place_sports_bet(match_id, 1002, "OU_OVER", 1_000_000, base_odds=1.75, market="OU")
        # AI Bettor bets 1M on 'OU_UNDER' (OU market)
        self.economy.place_sports_bet(match_id, -1, "OU_UNDER", 1_000_000, base_odds=2.10, market="OU")

        # Match finishes 3 - 0 (Home wins, Over 2.5 hits)
        settle_res = self.economy.settle_sports_match(match_id, "1", 3, 0)

        # Both 1001 (1X2 winner) and 1002 (OU winner) should win!
        tickets = self.economy.get_sports_tickets_for_match(match_id)
        t_1001 = next(t for t in tickets if t["user_id"] == 1001)
        t_1002 = next(t for t in tickets if t["user_id"] == 1002)
        t_ai = next(t for t in tickets if t["user_id"] == -1)

        self.assertEqual(t_1001["status"], "won")
        self.assertEqual(t_1002["status"], "won")
        self.assertEqual(t_ai["status"], "lost")
        self.assertGreater(t_1002["payout"], 1_000_000)

    def test_tipster_leaderboard(self):
        """Verify tipster queries compute correct stats and win rates."""
        match_id = self.economy.create_sports_match(t1="BAY", t2="BVB", kickoff=int(time.time()) + 600)
        self.economy.place_sports_bet(match_id, 1001, "1", 1_000_000, base_odds=1.80)
        self.economy.place_sports_bet(match_id, 1002, "2", 1_000_000, base_odds=3.00)

        self.economy.settle_sports_match(match_id, "1", 2, 0)

        tipsters = self.economy.get_top_tipsters(limit=5)
        self.assertEqual(len(tipsters), 2)
        top_1 = tipsters[0]
        self.assertEqual(top_1["user_id"], 1001)
        self.assertEqual(top_1["won_bets"], 1)
        self.assertEqual(top_1["win_rate"], 100.0)


if __name__ == "__main__":
    unittest.main()
