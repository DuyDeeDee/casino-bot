import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.sportsbet import (
    MATCH_INTERVAL_SECONDS,
    MATCH_SCHEDULE_LIMIT,
    SportsBet,
)


class TestSportsSchedule(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.db_path = Path(self.test_dir) / "test_schedule.db"

        import app.discord_bot.modules.economy as eco_mod
        self.orig_db_path = eco_mod.DATABASE_PATH
        eco_mod.DATABASE_PATH = self.db_path

        self.economy = Economy()
        self.economy.set_setting("jackpot_pool", "1000000")
        self.economy.set_setting("sports_ai_enabled", "1")

        # Mock discord Bot client
        self.bot = MagicMock()
        self.bot.wait_until_ready = MagicMock()
        self.cog = SportsBet(self.bot)
        self.cog.economy = self.economy

    def tearDown(self):
        self.cog.cog_unload()
        self.economy.close()
        import app.discord_bot.modules.economy as eco_mod
        eco_mod.DATABASE_PATH = self.orig_db_path
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_get_latest_sports_match_empty(self):
        """When no matches exist, get_latest_sports_match returns None."""
        latest = self.economy.get_latest_sports_match()
        self.assertIsNone(latest)

    def test_get_latest_sports_match_returns_newest(self):
        """get_latest_sports_match should return the most recently inserted match."""
        m1 = self.economy.create_sports_match("RMA", "BAR", kickoff=1000)
        m2 = self.economy.create_sports_match("MCI", "ARS", kickoff=2000)

        latest = self.economy.get_latest_sports_match()
        self.assertIsNotNone(latest)
        self.assertEqual(latest["id"], m2)
        self.assertEqual(latest["t1"], "MCI")
        self.assertEqual(latest["t2"], "ARS")
        self.assertEqual(latest["kickoff"], 2000)

    def test_initial_schedule_creates_one_match_8_hours_later(self):
        """When no matches exist, _ensure_schedule creates 1 match kicking off in ~8 hours."""
        now = int(time.time())
        fixtures = self.cog._ensure_schedule()

        self.assertEqual(len(fixtures), MATCH_SCHEDULE_LIMIT)
        match = fixtures[0]
        self.assertEqual(match["status"], "upcoming")
        # Kickoff should be now + 8*3600 (allow 5 seconds delta for execution time)
        self.assertAlmostEqual(match["kickoff"], now + MATCH_INTERVAL_SECONDS, delta=5)

        # Calling _ensure_schedule again should not create duplicate matches
        fixtures_again = self.cog._ensure_schedule()
        self.assertEqual(len(fixtures_again), MATCH_SCHEDULE_LIMIT)
        self.assertEqual(fixtures_again[0]["id"], match["id"])

        # Check that AI bettors were spawned
        tickets = self.economy.get_sports_tickets_for_match(match["id"])
        self.assertGreater(len(tickets), 0)

    def test_next_match_scheduled_8_hours_after_previous_finished_match(self):
        """After a match finishes, next match kickoff is scheduled 8 hours after previous match kickoff."""
        now = int(time.time())
        t1_kickoff = now - 180  # Started 3 minutes ago
        mid = self.economy.create_sports_match("RMA", "BAR", kickoff=t1_kickoff)
        # Mark match as finished
        self.economy.settle_sports_match(mid, "1", 2, 1)

        fixtures = self.cog._ensure_schedule()
        self.assertEqual(len(fixtures), 1)
        next_match = fixtures[0]
        # Target kickoff should be t1_kickoff + 8*3600
        expected_kickoff = t1_kickoff + MATCH_INTERVAL_SECONDS
        self.assertAlmostEqual(next_match["kickoff"], expected_kickoff, delta=5)

    def test_next_match_when_bot_was_offline_long(self):
        """If the previous match finished long ago (>8 hours), schedule 8 hours from now."""
        now = int(time.time())
        long_ago = now - 12 * 3600  # 12 hours ago
        mid = self.economy.create_sports_match("RMA", "BAR", kickoff=long_ago)
        self.economy.settle_sports_match(mid, "1", 2, 1)

        fixtures = self.cog._ensure_schedule()
        self.assertEqual(len(fixtures), 1)
        next_match = fixtures[0]
        # Since target_kickoff was in the past, it resets to now + 8 hours
        self.assertAlmostEqual(next_match["kickoff"], now + MATCH_INTERVAL_SECONDS, delta=5)

    def test_no_upcoming_created_while_match_is_live(self):
        """While a match is live, _ensure_schedule does not create a new upcoming match."""
        now = int(time.time())
        mid = self.economy.create_sports_match("RMA", "BAR", kickoff=now)
        self.economy.update_sports_match_live(mid, minute=30, score_t1=1, score_t2=0, status="live")

        fixtures = self.cog._ensure_schedule()
        self.assertEqual(len(fixtures), 0)
        upcoming = self.economy.get_upcoming_sports_matches()
        self.assertEqual(len(upcoming), 0)

    def test_custom_interval_setting(self):
        """Admin can configure custom interval via sports_interval_hours setting."""
        self.economy.set_setting("sports_interval_hours", "4")
        interval = self.cog.get_match_interval()
        self.assertEqual(interval, 4 * 3600)

        now = int(time.time())
        fixtures = self.cog._ensure_schedule()
        self.assertEqual(len(fixtures), 1)
        self.assertAlmostEqual(fixtures[0]["kickoff"], now + 4 * 3600, delta=5)


if __name__ == "__main__":
    unittest.main()
