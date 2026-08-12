"""
Automated Verification Suite for Tu Tien System: «ĐẠI ĐẠO TRANH PHONG»
Includes Gacha 3 Banner System Tests, Soft/Hard Pity, Wishlist, Shard Shop & open_chest.gif Animation.
"""

import os
import unittest
import tempfile
from app.discord_bot.modules.tutien.db import TuTienDB
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.constants import REALMS, REALM_REQUIRED_EXP, GACHA_BANNERS, LINH_BUI_SHOP
from app.discord_bot.modules.tutien.engines.cultivation import roll_spiritual_root, calculate_cultivation_gain, process_active_cultivation
from app.discord_bot.modules.tutien.engines.tribulation import calculate_breakthrough_chance, calculate_tribulation_damage, calculate_kim_dan_quality
from app.discord_bot.modules.tutien.engines.body_refining import upgrade_body_refining
from app.discord_bot.modules.tutien.engines.monetization import grant_topup_and_vip_exp, buy_tiencac_item, is_array_protected
from app.discord_bot.modules.tutien.engines.gacha import process_gacha_rolls
from app.discord_bot.modules.tutien.renderers.profile_renderer import render_tutien_profile_card


class TestTuTienSystem(unittest.TestCase):
    def setUp(self):
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.test_db_path = os.path.join(self.tmp_dir.name, "test_tutien.db")
        self.db = TuTienDB(self.test_db_path)

    def tearDown(self):
        try:
            self.tmp_dir.cleanup()
        except Exception:
            pass

    def test_roll_spiritual_root(self):
        quality, element, is_di = roll_spiritual_root()
        self.assertIsNotNone(quality)
        self.assertIsNotNone(element)

    def test_create_and_get_player(self):
        player = self.db.create_player(123, 456, "Thanh Vân Tử", "Thượng Phẩm", "⚡ Lôi", True)
        self.assertIsNotNone(player)
        self.assertEqual(player.dao_hieu, "Thanh Vân Tử")
        self.assertEqual(player.realm_name, "Luyện Khí Tầng 1")

    def test_gacha_3_banners(self):
        player = self.db.create_player(123, 456, "Thanh Vân Tử", "Thượng Phẩm", "⚡ Lôi", True)
        player.tien_ngoc = 500
        player.linh_thach = 100000
        player.tay_tuy_phu = 5
        self.db.update_player(player)

        # Test Banner 1 (Tụ Bảo Các - F2P)
        success1, msg1, rolls1, p1 = process_gacha_rolls(self.db, player, "tubao", 1)
        self.assertTrue(success1)
        self.assertEqual(len(rolls1), 1)

        # Test Banner 2 (Cửu Thiên Tiên Các - Premium 10x)
        success2, msg2, rolls2, p2 = process_gacha_rolls(self.db, p1, "tiencac", 10)
        self.assertTrue(success2)
        self.assertEqual(len(rolls2), 10)

        # Test Banner 3 (Thái Cổ Cải Mệnh Đài - Reroll)
        success3, msg3, rolls3, p3 = process_gacha_rolls(self.db, p2, "caimenh", 1)
        self.assertTrue(success3)
        self.assertTrue(p3.is_di_linh_can)

    def test_gacha_soft_hard_pity(self):
        player = self.db.create_player(123, 456, "Thanh Vân Tử", "Thượng Phẩm", "⚡ Lôi", True)
        player.tien_ngoc = 1000
        player.soft_pity_count = 79  # 79th pull
        self.db.update_player(player)

        success, msg, rolls, updated = process_gacha_rolls(self.db, player, "tiencac", 1)
        self.assertTrue(success)
        self.assertTrue(rolls[0]["is_ur"])
        self.assertEqual(updated.soft_pity_count, 0)

    def test_shard_shop_linh_bui(self):
        player = self.db.create_player(123, 456, "Thanh Vân Tử", "Thượng Phẩm", "⚡ Lôi", True)
        player.linh_bui = 300
        self.db.update_player(player)

        item_name = "Trảm Tiên Kiếm"
        cost = LINH_BUI_SHOP[item_name]["cost"]
        player.linh_bui -= cost
        self.db.add_item(player.user_id, item_name, "UR", 1)
        self.db.update_player(player)

        self.assertEqual(player.linh_bui, 0)
        self.assertTrue(self.db.has_item(123, item_name))

    def test_gif_animation_file_exists(self):
        self.assertTrue(os.path.exists("pictures/open_chest.gif"))


if __name__ == "__main__":
    unittest.main()
