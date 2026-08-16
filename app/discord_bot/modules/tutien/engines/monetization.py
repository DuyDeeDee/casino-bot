"""
Monetization Engine: Top-Up processing, VIP progression, Tiên Các Shop & Gacha Pity Banner.
"""

import time
import random
from typing import Tuple, Dict, Any, Optional
from app.discord_bot.modules.tutien.constants import TIEN_CAC_SHOP, VIP_LEVELS, GACHA_ITEMS_PREMIUM
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.db import TuTienDB


def grant_topup_and_vip_exp(player: CultivatorProfile, tien_ngoc_amount: int) -> Tuple[CultivatorProfile, bool]:
    """
    Grants Tiên Ngọc top-up and calculates VIP level progression.
    """
    player.tien_ngoc += tien_ngoc_amount
    player.vip_exp += tien_ngoc_amount

    # Recalculate VIP Level
    old_vip = player.vip_level
    new_vip = old_vip
    for lvl in range(10, -1, -1):
        if player.vip_exp >= VIP_LEVELS[lvl]["req_exp"]:
            new_vip = lvl
            break

    player.vip_level = new_vip
    vip_upgraded = new_vip > old_vip

    # VIP 8: Tụ Linh Trận Động Phủ tự động tăng Cấp +10 khi lần đầu đạt VIP 8
    if vip_upgraded and new_vip >= 8 and old_vip < 8:
        player.dong_phu_level = min(50, player.dong_phu_level + 10)

    return player, vip_upgraded


def is_array_protected(player: CultivatorProfile) -> bool:
    """
    Checks if player has active anti-robbery array (Trận Pháp Bất Xâm Phạm).
    """
    if not player.array_protection_until:
        return False
    return player.array_protection_until > time.time()


def buy_tiencac_item(db: TuTienDB, player: CultivatorProfile, item_name: str) -> Tuple[bool, str, CultivatorProfile]:
    """
    Purchases items from Tiên Các Shop using Tiên Ngọc.
    """
    # Find matching key in TIEN_CAC_SHOP
    target_key = None
    if item_name in TIEN_CAC_SHOP:
        target_key = item_name
    else:
        for name in TIEN_CAC_SHOP.keys():
            if item_name.lower().strip() in name.lower():
                target_key = name
                break

    if not target_key:
        return False, f"❌ Vật phẩm **[{item_name}]** không tồn tại trong Tiên Các! Gõ `!tiencac` để xem danh sách.", player

    item_info = TIEN_CAC_SHOP[target_key]
    price = item_info["price"]
    item_name = target_key

    if player.tien_ngoc < price:
        return False, f"❌ Không đủ Tiên Ngọc! Vật phẩm **[{item_name}]** giá `{price}` Tiên Ngọc (Hiện có: `{player.tien_ngoc}` Tiên Ngọc).", player

    player.tien_ngoc -= price

    # Handle immediate effects
    if item_name == "Thẻ Tháng Đạo Tâm Tôn Giả":
        player.is_vip_pass = True
        now = time.time()
        player.vip_pass_expires = (player.vip_pass_expires or now) + (30 * 86400)
        player.tien_ngoc += 500  # Bonus immediate Tiên Ngọc
        db.update_player(player)
        return True, "📜 **KÍCH HOẠT THẺ THÁNG ĐẠO TÂM TÔN GIẢ!** Nhận ngay 500 Tiên Ngọc, kích hoạt Auto-Định Tâm AFK & Khung Vàng Kim!", player

    elif item_name == "Tiên Mật Hồi Tinh Lực":
        player.tinh_luc = player.max_tinh_luc
        db.update_player(player)
        return True, "🍾 **SỬ DỤNG TIÊN MẬT!** Khôi phục ngay `100%` Tinh Lực!", player

    elif item_name == "Trận Pháp Bất Xâm Phạm":
        now = time.time()
        player.array_protection_until = max(now, player.array_protection_until or 0) + 86400
        db.update_player(player)
        return True, "🛡️ **KÍCH HOẠT TRẬN PHÁP BẤT XÂM PHẠM!** Động Phủ của bạn an toàn 100% khỏi các lệnh cướp phá trong 24 Giờ!", player

    elif item_name == "Thất Nhật Miễn Chiến Phù":
        now = time.time()
        player.mien_chien_until = max(now, player.mien_chien_until or 0) + (7 * 86400)
        db.update_player(player)
        return True, "🛡️ **KÍCH HOẠT THẤT NHẬT MIỄN CHIẾN PHÙ!** Bạn đã được bảo hộ an toàn khỏi PK Dã Ngoại và Cướp Động Phủ trong 7 Ngày (168 Giờ)!", player

    elif item_name == "Gói Phục Hồi Cấp Tốc":
        player.hp = player.max_hp
        player.chan_thuong_until = None
        player.tau_hoa_nhap_ma_until = None
        player.lingering_debuff = None
        db.update_player(player)
        return True, "💊 **SỬ DỤNG GÓI PHỤC HỒI CẤP TỐC!** Phục hồi 100% HP, xóa sạch Chấn Thương Kinh Mạch và Tẩu Hỏa Nhập Ma! Sẵn sàng phục thù!", player

    else:
        # Save insurance items to inventory
        db.add_item(player.user_id, item_name, item_info["category"], 1)
        db.update_player(player)
        return True, f"🛍️ **MUA THÀNH CÔNG!** Đã nhận **[{item_name}]** vào Túi Đồ của bạn!", player





def roll_gacha_banner(db, player: CultivatorProfile):
    """
    ⚠️  DEPRECATED — Hàm này đã bị vô hiệu hóa.
    Toàn bộ logic gacha đã được thống nhất vào:
        engines/gacha.py :: process_gacha_rolls()
    Hàm đó sử dụng soft_pity_count (duy nhất), soft pity tại 60, hard pity tại 80,
    và áp dụng đầy đủ Wishlist Định Hướng Đạo Vận.
    """
    raise RuntimeError(
        "[TuTien] roll_gacha_banner() đã bị deprecated! "
        "Hãy dùng engines.gacha.process_gacha_rolls() thay thế."
    )

