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
    if item_name not in TIEN_CAC_SHOP:
        return False, f"❌ Vật phẩm **[{item_name}]** không tồn tại trong Tiên Các!", player

    item_info = TIEN_CAC_SHOP[item_name]
    price = item_info["price"]

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



def roll_gacha_banner(db: TuTienDB, player: CultivatorProfile) -> Tuple[bool, str, CultivatorProfile]:
    """
    Executes 1 Gacha roll (Costs 50 Tiên Ngọc) with 80-pull Pity Guarantee.
    """
    gacha_cost = 50
    if player.tien_ngoc < gacha_cost:
        return False, f"❌ Cần `{gacha_cost}` Tiên Ngọc để quay Tiên Các!", player

    player.tien_ngoc -= gacha_cost
    player.gacha_pity_count += 1

    # Check Pity (80 pulls guarantee Tiên Cấp)
    if player.gacha_pity_count >= 80:
        player.gacha_pity_count = 0
        won_item = GACHA_ITEMS_PREMIUM[0]  # Pity Reward
        db.add_item(player.user_id, won_item[0], won_item[1], 1)
        db.update_player(player)
        return True, f"🌟 **CHẮC CHẮN PITY BẢO HIỂM 80 LƯỢT!** Nhận ngay **[{won_item[0]}]**!", player

    # Normal weighted roll
    rand_val = random.uniform(0, 100)
    cumulative = 0.0
    won_item = GACHA_ITEMS_PREMIUM[-1]

    for item_tuple in GACHA_ITEMS_PREMIUM:
        cumulative += item_tuple[3]
        if rand_val <= cumulative:
            won_item = item_tuple
            break

    if won_item[2] == "Tiên Cấp":
        player.gacha_pity_count = 0  # Reset Pity on legend hit

    db.add_item(player.user_id, won_item[0], won_item[1], 1)
    db.update_player(player)

    return True, f"🎲 **TIÊN CÁC QUAY SỐ:** Bạn nhận được **[{won_item[0]}]**! (Lượt Pity: `{player.gacha_pity_count}/80`)", player
