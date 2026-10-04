import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from app.discord_bot.modules import economy as economy_module
from app.discord_bot.modules.economy import Economy


class MasoiRankResetTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / "rank.db"
        sqlite3.connect(self.path).close()
        self.path_patch = patch.object(economy_module, "DATABASE_PATH", self.path)
        self.path_patch.start()
        self.eco = Economy()

    def tearDown(self):
        self.eco.conn.close()
        self.path_patch.stop()
        self.temp.cleanup()

    def test_reset_one_player_preserves_badge_and_match_idempotency(self):
        result = [(101, 20, True, "WOLF")]
        self.eco.settle_masoi_match("match-one", result)
        self.eco.set_masoi_custom_badge(101, "🔥")

        self.eco.reset_masoi_rank(101)

        self.assertEqual(self.eco.get_masoi_rank_stats(101, "WOLF")["plays"], 0)
        self.assertEqual(self.eco.get_masoi_stats(101)["points"], 0)
        self.assertEqual(self.eco.get_masoi_custom_badge(101), "🔥")
        self.assertFalse(self.eco.settle_masoi_match("match-one", result))
        self.assertEqual(self.eco.get_masoi_rank_stats(101, "WOLF")["plays"], 0)

    def test_reset_all_players_preserves_badges(self):
        self.eco.add_masoi_points(101, 20, True, "WOLF")
        self.eco.add_masoi_points(202, 30, True, "SOLO")
        self.eco.set_masoi_custom_badge(101, "🔥")

        self.eco.reset_masoi_rank()

        self.assertEqual(self.eco.get_masoi_rank_stats(101, "WOLF")["plays"], 0)
        self.assertEqual(self.eco.get_masoi_rank_stats(202, "SOLO")["plays"], 0)
        self.assertEqual(self.eco.get_masoi_stats(101)["plays"], 0)
        self.assertEqual(self.eco.get_masoi_stats(202)["plays"], 0)
        self.assertEqual(self.eco.get_masoi_custom_badge(101), "🔥")


if __name__ == "__main__":
    unittest.main()
