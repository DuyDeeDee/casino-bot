import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier
from unittest.mock import patch

from app.discord_bot.modules import economy as economy_module
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.farm.service import FarmError, FarmStore


class FarmEconomyTests(unittest.TestCase):
    user_id = 82_001

    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        root = Path(self.directory.name)
        database = root / "economy.db"
        self.database_path = database
        database_path = patch.object(economy_module, "DATABASE_PATH", database)
        legacy_path = patch.object(economy_module, "LEGACY_DATABASE_PATH", root / "missing.db")
        database_path.start()
        self.addCleanup(database_path.stop)
        legacy_path.start()
        self.addCleanup(legacy_path.stop)
        self.economy = Economy()
        self.addCleanup(self.economy.close)
        self.store = FarmStore(self.economy)

    def balance(self):
        return self.economy.get_entry(self.user_id)[1]

    def test_start_credits_existing_casino_wallet_once_and_persists(self):
        self.economy.add_money(self.user_id, 25_000)
        self.economy.set_credits(self.user_id, 7)
        self.assertEqual(self.store.start(self.user_id), 1_025_000)
        self.economy.close()
        self.economy.open()

        with self.assertRaisesRegex(FarmError, "đã có"):
            self.store.start(self.user_id)
        self.assertEqual(self.economy.get_entry(self.user_id), (self.user_id, 1_025_000, 7))
        self.assertEqual(self.store.get(self.user_id)["gems"], 0)

    def test_failed_inventory_write_rolls_back_wallet_and_audit(self):
        self.store.start(self.user_id)
        self.economy.add_money(self.user_id, 20_000_000)
        with self.store.action(self.user_id, "buy") as farm:
            farm.buy("1", 200)
        balance = self.balance()
        with self.assertRaisesRegex(FarmError, "đã đầy"):
            with self.store.action(self.user_id, "buy") as farm:
                farm.buy("1", 1)

        self.assertEqual(self.balance(), balance)
        self.assertEqual(self.store.get(self.user_id)["inventory"], {"seed:rau_muong": 200})
        audits = self.economy.conn.execute(
            "SELECT money_delta FROM wallet_transactions WHERE event = 'farm' ORDER BY id"
        ).fetchall()
        self.assertEqual(audits, [(1_000_000,), (-16_000_000,)])

    def test_harvest_and_sell_credit_spendable_casino_money(self):
        now = datetime(2026, 11, 26, tzinfo=timezone.utc).timestamp()
        self.store.start(self.user_id)
        with self.store.action(self.user_id, "plant", now=now) as farm:
            farm.plant("1", 1)
        with self.store.action(self.user_id, "harvest", now=now + 3600) as farm:
            crops, _ = farm.harvest("all")
        self.assertEqual(sum(crops.values()), 1)

        before = self.balance()
        with self.store.action(self.user_id, "sell", now=now + 3600) as farm:
            quantity, coins = farm.sell("all", 1)
        self.assertEqual(quantity, 1)
        self.assertEqual(self.balance(), before + coins * 10_000)
        receipt = self.economy.execute_invest_buy(
            user_id=self.user_id,
            symbol="CASINO",
            shares=1,
            market_price=100_000,
            liquidity=10_000,
            buy_fee_pct=0,
        )
        self.assertTrue(receipt["success"])

    def test_daily_claim_does_not_pay_twice(self):
        self.store.start(self.user_id)
        now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc).timestamp()
        with patch("app.discord_bot.modules.farm.service.random.randint", return_value=300):
            with self.store.action(self.user_id, "daily", now=now) as farm:
                self.assertEqual(farm.daily(), (300, 1))
        with self.assertRaisesRegex(FarmError, "đã điểm danh"):
            with self.store.action(self.user_id, "daily", now=now) as farm:
                farm.daily()
        self.assertEqual(self.balance(), 4_000_000)

    def test_concurrent_farm_purchases_cannot_spend_the_same_vnd(self):
        self.store.start(self.user_id)
        other = Economy()
        self.addCleanup(other.close)
        ready = Barrier(2)

        def buy(store):
            ready.wait(timeout=5)
            try:
                with store.action(self.user_id, "buy") as farm:
                    farm.buy("1", 10)
                return True
            except FarmError:
                return False

        with ThreadPoolExecutor(max_workers=2) as executor:
            first = executor.submit(buy, self.store)
            second = executor.submit(buy, FarmStore(other))
            outcomes = [first.result(timeout=10), second.result(timeout=10)]
        self.assertEqual(outcomes.count(True), 1)
        self.assertEqual(self.balance(), 200_000)
        self.assertEqual(self.store.get(self.user_id)["inventory"], {"seed:rau_muong": 10})

    def test_upgrade_from_previous_schema_preserves_wallets(self):
        self.economy.set_money(self.user_id, 900_000_001)
        with self.economy.conn:
            self.economy.conn.execute("DROP TABLE farm_players")
            self.economy.conn.execute("DROP TABLE wallet_transactions")
            self.economy.conn.execute("UPDATE schema_version SET version = 55")
        self.economy.close()
        self.economy.open()

        self.assertEqual(self.balance(), 900_000_001)
        self.assertEqual(self.store.start(self.user_id), 901_000_001)

    def test_legacy_plant_all_uses_inventory_and_partial_batch_uses_wallet(self):
        self.store.start(self.user_id)
        self.economy.set_money(self.user_id, 80_000)
        with self.store.action(self.user_id, "plant") as farm:
            farm.change_item("seed", "rau_muong", 1)
            farm.change_item("seed", "lua", 1)
        with self.store.action(self.user_id, "plant") as farm:
            batch, cost = farm.plant("all", 1)
            self.assertEqual([(key, count) for key, count, _ in batch], [("rau_muong", 1), ("lua", 1)])
            self.assertEqual(cost, 0)
        self.economy.set_money(self.user_id, 80_000)
        with self.store.action(self.user_id, "plant") as farm:
            batch, cost = farm.plant("1", "all")
            self.assertEqual(batch[0][:2], ("rau_muong", 1))
            self.assertEqual(cost, 8)
        self.assertEqual(self.store.get(self.user_id)["planted"], 3)

    def test_marriage_consumes_ring_and_records_both_players_atomically(self):
        partner = self.user_id + 1
        self.store.start(self.user_id)
        self.store.start(partner)
        with self.store.action(self.user_id, "test setup") as farm:
            farm.change_item("ring", "nhan_bac", 1)
            farm.change_item("ring", "nhan_vang", 1)
        ring = self.store.proposal_ring(self.user_id, partner)
        self.assertEqual(ring, "nhan_vang")
        self.store.marry(self.user_id, partner, 123, ring)
        wedding = self.store.get(self.user_id)["marriage"]
        self.assertEqual(wedding["id"], self.store.get(partner)["marriage"]["id"])
        self.assertEqual(self.store.get(self.user_id)["inventory"], {"ring:nhan_bac": 1})
        with self.assertRaises(FarmError):
            self.store.marry(self.user_id, partner, 123, "nhan_bac")
        self.assertEqual(self.store.leaderboard("couple", partner)[1], 1)
        self.store.divorce(partner, wedding["id"])
        self.assertNotIn("marriage", self.store.get(self.user_id))
        self.assertNotIn("marriage", self.store.get(partner))

    def test_original_leaderboard_prioritizes_evolution_then_level_then_xp(self):
        first, second, third = self.user_id, self.user_id + 1, self.user_id + 2
        for user_id, level, evolutions, xp in ((first, 50, 0, 150), (second, 3, 1, 12), (third, 3, 1, 60)):
            self.store.start(user_id)
            with self.store.action(user_id, "test setup") as farm:
                farm.state.update(level=level, evolutions=evolutions, xp=xp)
        rows, rank = self.store.leaderboard("level", second)
        self.assertEqual([row[0] for row in rows], [third, second, first])
        self.assertEqual(rank, 2)

    def test_satou_unlock_and_timed_pet_lock(self):
        self.store.start(self.user_id)
        with self.store.action(self.user_id, "test setup") as farm:
            farm.add_pet("satou")
            farm.add_pet("chick")
            farm.state["pets"]["chick"]["stars"] = 5
            farm.change_item("weapon", "dao", 5)
            farm.select_pet("18")
        now = datetime(2026, 11, 26, 12, tzinfo=timezone.utc).timestamp()
        for _ in range(5):
            with self.store.action(self.user_id, "killpet", now=now) as farm:
                farm.kill_pet("chick")
        with self.store.action(self.user_id, "selectpet", now=now) as farm:
            farm.select_pet("satou")
        with self.assertRaises(FarmError):
            with self.store.action(self.user_id, "selectpet", now=now + 1) as farm:
                farm.select_pet("chick")
        with self.store.action(self.user_id, "selectpet", now=now + 86400) as farm:
            farm.select_pet("chick")
        self.assertEqual(self.store.get(self.user_id)["active_pet"], "chick")

    def test_update_reward_and_guaranteed_draw_are_consumed_once(self):
        self.store.start(self.user_id)
        with self.store.action(self.user_id, "update") as farm:
            original_tickets = farm.state["tickets"]
            self.assertEqual(farm.update_reward(), original_tickets + 10)
            farm.arrange_gacha("kuromi", 1)
        with self.assertRaises(FarmError):
            with self.store.action(self.user_id, "update") as farm:
                farm.update_reward()
        with self.store.action(self.user_id, "gacha") as farm:
            rewards, used_tickets = farm.gacha(1)
            self.assertTrue(used_tickets)
            self.assertEqual(rewards[0][0], "pet_kuromi")
            self.assertEqual(farm.state["pity"], 0)
        self.assertEqual(self.store.get(self.user_id)["gacha_guarantees"], [])
