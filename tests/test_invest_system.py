import unittest
import sqlite3
import tempfile
import os
import shutil
from pathlib import Path
from app.discord_bot.modules.economy import Economy


class TestInvestSystem(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_economy.db"
        import app.discord_bot.modules.economy as eco_mod
        self.orig_db_path = eco_mod.DATABASE_PATH
        eco_mod.DATABASE_PATH = self.db_path

        self.economy = Economy()
        self.user_id = 999001
        self.user_id_2 = 999002
        self.economy.new_entry(self.user_id)
        self.economy.new_entry(self.user_id_2)
        # Give user funds
        self.economy.add_money(self.user_id, 10_000_000)
        self.economy.add_money(self.user_id_2, 10_000_000)

    def tearDown(self):
        try:
            self.economy.conn.close()
        except Exception:
            pass
        import app.discord_bot.modules.economy as eco_mod
        eco_mod.DATABASE_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_buy_stock_avg_cost_with_fee(self):
        """Kiểm tra mua cổ phiếu tính gộp 2% phí vào giá vốn trung bình."""
        market_price = 100_000
        shares = 10.0
        liquidity = 10_000.0  # Slippage = (10 / 10000) * 1% = 0.001% -> eff_price ~ 100001
        
        receipt = self.economy.execute_invest_buy(
            user_id=self.user_id,
            symbol="CASINO",
            shares=shares,
            market_price=market_price,
            liquidity=liquidity,
            buy_fee_pct=0.02
        )
        
        self.assertTrue(receipt["success"])
        self.assertEqual(receipt["shares"], 10.0)
        eff_price = receipt["effective_price"]
        expected_base = int(shares * eff_price)
        expected_fee = int(expected_base * 0.02)
        expected_total = expected_base + expected_fee
        expected_avg_cost = expected_total / shares
        
        self.assertEqual(receipt["total_cost"], expected_total)
        self.assertAlmostEqual(receipt["avg_cost"], expected_avg_cost, places=2)
        
        # Check wallet balance
        entry = self.economy.get_entry(self.user_id)
        self.assertEqual(entry[1], 10_000_000 - expected_total)
        
        # Check portfolio
        portfolio = self.economy.get_portfolio_with_cost(self.user_id)
        self.assertEqual(len(portfolio), 1)
        sym, sh, avg_cost = portfolio[0]
        self.assertEqual(sym, "CASINO")
        self.assertEqual(sh, 10.0)
        self.assertAlmostEqual(avg_cost, expected_avg_cost, places=2)

    def test_second_buy_updates_weighted_avg_cost(self):
        """Kiểm tra mua lần 2 cập nhật đúng giá vốn bình quân gia quyền đã gồm 2% phí."""
        # Buy 1: 10 shares @ 100k
        r1 = self.economy.execute_invest_buy(self.user_id, "CASINO", 10.0, 100_000, 10000.0)
        # Buy 2: 10 shares @ 200k
        r2 = self.economy.execute_invest_buy(self.user_id, "CASINO", 10.0, 200_000, 10000.0)
        
        total_spent = r1["total_cost"] + r2["total_cost"]
        expected_avg = total_spent / 20.0
        
        self.assertAlmostEqual(r2["avg_cost"], expected_avg, places=2)
        portfolio = self.economy.get_portfolio_with_cost(self.user_id)
        self.assertEqual(portfolio[0][1], 20.0)
        self.assertAlmostEqual(portfolio[0][2], expected_avg, places=2)

    def test_buy_insufficient_funds_rollback(self):
        """Kiểm tra mua khi không đủ tiền thì rollback nguyên tử, không trừ tiền/cổ."""
        with self.assertRaises(ValueError) as ctx:
            self.economy.execute_invest_buy(self.user_id, "CASINO", 200.0, 1_000_000, 10000.0)
        
        self.assertTrue(str(ctx.exception).startswith("insufficient_funds"))
        entry = self.economy.get_entry(self.user_id)
        self.assertEqual(entry[1], 10_000_000)
        portfolio = self.economy.get_portfolio_with_cost(self.user_id)
        self.assertEqual(len(portfolio), 0)

    def test_buy_max_holding_exceeded(self):
        """Kiểm tra vượt quá giới hạn sở hữu tối đa bị từ chối."""
        with self.assertRaises(ValueError) as ctx:
            self.economy.execute_invest_buy(
                self.user_id, "CASINO", 50.0, 100_000, 10000.0, max_holding=30.0
            )
        self.assertTrue(str(ctx.exception).startswith("max_holding_exceeded"))

    def test_volume_cap_exceeded(self):
        """Kiểm tra vượt volume cap 20% thanh khoản mỗi lệnh bị từ chối."""
        with self.assertRaises(ValueError) as ctx:
            self.economy.execute_invest_buy(
                self.user_id, "CASINO", 2500.0, 100, 10000.0, max_order_shares=2000.0
            )
        self.assertTrue(str(ctx.exception).startswith("max_order_exceeded"))

    def test_partial_sell_preserves_avg_cost(self):
        """Kiểm tra bán 1 phần giữ nguyên giá vốn bình quân."""
        # Buy 10 shares @ 100k
        r_buy = self.economy.execute_invest_buy(self.user_id, "CASINO", 10.0, 100_000, 10000.0)
        orig_avg = r_buy["avg_cost"]
        
        # Sell 4 shares @ 150k
        r_sell = self.economy.execute_invest_sell(self.user_id, "CASINO", 4.0, 150_000, 10000.0)
        self.assertTrue(r_sell["success"])
        self.assertEqual(r_sell["remaining_shares"], 6.0)
        
        # Check portfolio retains same avg_cost
        portfolio = self.economy.get_portfolio_with_cost(self.user_id)
        self.assertEqual(portfolio[0][1], 6.0)
        self.assertAlmostEqual(portfolio[0][2], orig_avg, places=2)

    def test_full_sell_removes_portfolio_entry(self):
        """Kiểm tra bán hết 100% thì xóa bản ghi khỏi portfolio."""
        self.economy.execute_invest_buy(self.user_id, "CASINO", 10.0, 100_000, 10000.0)
        r_sell = self.economy.execute_invest_sell(self.user_id, "CASINO", 10.0, 100_000, 10000.0)
        self.assertEqual(r_sell["remaining_shares"], 0.0)
        
        portfolio = self.economy.get_portfolio_with_cost(self.user_id)
        self.assertEqual(len(portfolio), 0)

    def test_limit_order_lifecycle(self):
        """Kiểm tra toàn bộ chu kỳ đặt, hủy và khớp Limit Order nguyên tử."""
        # 1. Place Limit BUY (Locks VND)
        r_place = self.economy.execute_place_limit_order(
            user_id=self.user_id,
            symbol="CASINO",
            order_type="BUY",
            target_price=80_000,
            shares=5.0,
            liquidity=10000.0
        )
        order_id = r_place["order_id"]
        locked_funds = r_place["locked_funds"]
        self.assertGreater(locked_funds, 0)
        
        entry = self.economy.get_entry(self.user_id)
        self.assertEqual(entry[1], 10_000_000 - locked_funds)
        
        # 2. Cancel and verify refund
        r_cancel = self.economy.execute_cancel_limit_order(order_id, user_id=self.user_id, liquidity=10000.0)
        self.assertEqual(r_cancel["refund_amount"], locked_funds)
        entry = self.economy.get_entry(self.user_id)
        self.assertEqual(entry[1], 10_000_000)
        
        # 3. Place Limit BUY again and Fill
        r_place2 = self.economy.execute_place_limit_order(
            user_id=self.user_id,
            symbol="CASINO",
            order_type="BUY",
            target_price=80_000,
            shares=5.0,
            liquidity=10000.0
        )
        order_id2 = r_place2["order_id"]
        
        # Market price drops to 75,000 <= target 80,000
        fill_res = self.economy.execute_fill_limit_buy(order_id2, curr_price=75_000, liquidity=10000.0)
        self.assertEqual(fill_res["status"], "filled")
        self.assertGreater(fill_res["refund"], 0)  # Refunded price diff
        
        # Check user has 5 shares and updated avg_cost
        portfolio = self.economy.get_portfolio_with_cost(self.user_id)
        self.assertEqual(len(portfolio), 1)
        self.assertEqual(portfolio[0][1], 5.0)

    def test_bankruptcy_restructuring(self):
        """Kiểm tra tái cấu trúc phá sản: đền bù 40% cho cổ đông và mở lại ở 30% giá gốc."""
        # User 1 has 10 shares
        self.economy.execute_invest_buy(self.user_id, "CASINO", 10.0, 100_000, 10000.0)
        # User 2 places limit order
        self.economy.execute_place_limit_order(self.user_id_2, "CASINO", "BUY", 90_000, 5.0, 10000.0)
        
        u1_money_before = self.economy.get_entry(self.user_id)[1]
        
        # Execute bankruptcy restructuring
        default_price = 100_000
        rep = self.economy.execute_bankruptcy_restructuring(
            symbol="CASINO",
            default_price=default_price,
            compensation_rate=0.40,
            restart_discount_rate=0.30,
            liquidity=10000.0
        )
        
        self.assertEqual(rep["compensation_price"], 40_000)
        self.assertEqual(rep["restructured_price"], 30_000)
        
        # User 1 was liquidated and received 10 * 40,000 = 400,000 VND
        u1_money_after = self.economy.get_entry(self.user_id)[1]
        self.assertEqual(u1_money_after, u1_money_before + 400_000)
        
        # User 1 has 0 shares
        self.assertEqual(len(self.economy.get_portfolio_with_cost(self.user_id)), 0)
        # User 2 limit buy was refunded
        self.assertEqual(self.economy.get_entry(self.user_id_2)[1], 10_000_000)
        
        # Stock price is now 30,000
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        self.assertEqual(prices["CASINO"], 30_000)

    def test_metrics_and_trade_flow(self):
        """Kiểm tra ghi nhận net trade flow và metrics tích lũy."""
        self.economy.execute_invest_buy(self.user_id, "CASINO", 10.0, 100_000, 10000.0)
        self.economy.execute_invest_sell(self.user_id, "CASINO", 3.0, 100_000, 10000.0)
        
        flow = self.economy.get_and_reset_invest_trade_flow()
        self.assertAlmostEqual(flow.get("CASINO", 0.0), 7.0, places=2)
        
        # Reset flow should now be empty
        flow_after = self.economy.get_and_reset_invest_trade_flow()
        self.assertEqual(flow_after.get("CASINO", 0.0), 0.0)
        
        # Metrics
        metrics = self.economy.get_invest_metrics()
        self.assertGreater(metrics["fee_burned"], 0)
        self.assertGreater(metrics["volume_vnd"], 0)


if __name__ == "__main__":
    unittest.main()
