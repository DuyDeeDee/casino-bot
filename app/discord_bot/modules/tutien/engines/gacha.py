"""
Gacha Engine: 3 Banner System («THIÊN ĐỊA DUYÊN CƠ»), Soft Pity (60+), Hard Pity (80), Wishlist & Shard Shop.
"""

import random
from typing import Tuple, List, Dict, Any, Optional
from app.discord_bot.modules.tutien.constants import (
    GACHA_BANNERS, GACHA_ITEMS_PREMIUM, LINH_BUI_SHOP, SPIRITUAL_ROOT_QUALITIES, ELEMENTS_NGU_HANH, ELEMENTS_DI_LINH_CAN
)
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.db import TuTienDB


def roll_single_item(player: CultivatorProfile, banner_type: str) -> Tuple[Dict[str, Any], CultivatorProfile]:
    """
    Executes a single roll on banner `banner_type`.
    Applies Soft Pity (pull 60+), Hard Pity (pull 80), Wishlist, and Linh Bụi conversion.
    """
    player.soft_pity_count += 1
    
    # Calculate UR probability
    # Base = 0.7% (0.007)
    base_ur_rate = 0.007
    if player.soft_pity_count >= 80:
        ur_rate = 1.0  # Hard Pity
    elif player.soft_pity_count >= 60:
        ur_rate = base_ur_rate + (player.soft_pity_count - 59) * 0.05  # Soft Pity +5%/pull
    else:
        ur_rate = base_ur_rate

    rand_val = random.random()
    is_ur = rand_val < ur_rate

    if is_ur:
        player.soft_pity_count = 0
        grade = "🔴 Đế Cấp (UR)"

        # Ưu tiên Wishlist (Định Hướng Đạo Vận) nếu có — áp dụng cả khi pity lẫn khi ra rate thường
        if player.wishlist_item:
            # Tìm item trùng tên wishlist trong pool UR
            matched = [x for x in GACHA_ITEMS_PREMIUM if "Đế Cấp" in x[2] and player.wishlist_item.lower() in x[0].lower()]
            if matched:
                item_name = matched[0][0]
                player.wishlist_item = None  # Xóa wishlist sau khi đã trúng
            else:
                # Wishlist không match → random UR pool
                ur_options = [x for x in GACHA_ITEMS_PREMIUM if "Đế Cấp" in x[2]]
                item_name = random.choice(ur_options if ur_options else GACHA_ITEMS_PREMIUM)[0]
        else:
            # Không có wishlist → random trong toàn bộ UR pool
            ur_options = [x for x in GACHA_ITEMS_PREMIUM if "Đế Cấp" in x[2]]
            item_name = random.choice(ur_options if ur_options else GACHA_ITEMS_PREMIUM)[0]

    else:
        # Roll SR (4.3%) vs Địa/Phàm
        if rand_val < (ur_rate + 0.043):
            grade = "🟡 Thiên Cấp (SR)"
            sr_options = [x for x in GACHA_ITEMS_PREMIUM if "Thiên Cấp" in x[2]]
            item_name = random.choice(sr_options if sr_options else GACHA_ITEMS_PREMIUM)[0]
        elif rand_val < (ur_rate + 0.293):
            grade = "🟣 Địa Cấp"
            dia_options = [x for x in GACHA_ITEMS_PREMIUM if "Địa Cấp" in x[2]]
            item_name = random.choice(dia_options if dia_options else GACHA_ITEMS_PREMIUM)[0]
        else:
            grade = "🟢 Phàm/Huyền Cấp"
            other_options = [x for x in GACHA_ITEMS_PREMIUM if not any(k in x[2] for k in ["Đế Cấp", "Thiên Cấp", "Địa Cấp"])]
            item_name = random.choice(other_options if other_options else GACHA_ITEMS_PREMIUM)[0]

    res = {
        "item_name": item_name,
        "grade": grade,
        "is_ur": is_ur,
        "pity_count": player.soft_pity_count
    }
    return res, player


def process_gacha_rolls(
    db: TuTienDB,
    player: CultivatorProfile,
    banner_key: str = "tiencac",
    roll_count: int = 1
) -> Tuple[bool, str, List[Dict[str, Any]], CultivatorProfile]:
    """
    Processes 1x or 10x Gacha rolls for specified banner.
    Deducts currency / tickets, adds items to inventory, converts duplicates to Linh Bụi.
    """
    if banner_key not in GACHA_BANNERS:
        return False, f"❌ Banner **[{banner_key}]** không tồn tại!", [], player

    banner_info = GACHA_BANNERS[banner_key]
    cost_total = banner_info["cost_1x"] * roll_count

    # Check Ticket or Currency
    if banner_key == "tubao":
        if player.linh_duyen_phu >= roll_count:
            player.linh_duyen_phu -= roll_count
        elif player.linh_thach >= cost_total:
            player.linh_thach -= cost_total
        else:
            return False, f"❌ Không đủ Linh Thạch hoặc Linh Duyên Phù! Cần `{cost_total:,}` Linh Thạch.", [], player

    elif banner_key == "tiencac":
        if player.tien_duyen_phu >= roll_count:
            player.tien_duyen_phu -= roll_count
        elif player.tien_ngoc >= cost_total:
            player.tien_ngoc -= cost_total
        else:
            return False, f"❌ Không đủ Tiên Ngọc hoặc Tiên Duyên Phù! Cần `{cost_total}` Tiên Ngọc.", [], player

    elif banner_key == "caimenh":
        if player.tay_tuy_phu >= roll_count:
            player.tay_tuy_phu -= roll_count
        elif player.tien_ngoc >= (100 * roll_count):
            player.tien_ngoc -= (100 * roll_count)
        else:
            return False, f"❌ Không đủ Tẩy Tủy Phù hoặc Tiên Ngọc!", [], player

    # Special handling for Thái Cổ Cải Mệnh Đài (Reroll Spiritual Root / Tiên Thể)
    if banner_key == "caimenh":
        results = []
        for _ in range(roll_count):
            # Roll high quality root
            quality_roll = random.choice(["Thượng Phẩm", "Cực Phẩm / Thiên Phẩm", "Tiên Phẩm", "Thánh Phẩm", "Hỗn Độn"])
            element_roll = random.choice(["⚡ Lôi", "❄️ Băng", "🌪️ Phong", "🌌 Không Gian / Thời Gian"])
            player.linh_can_quality = quality_roll
            player.linh_can_element = element_roll
            player.is_di_linh_can = True
            results.append({"item_name": f"✨ [CẢI MỆNH] {quality_roll} ({element_roll})", "grade": "🔴 Tiên Thể", "is_ur": True})
        
        db.update_player(player)
        return True, "✨ **THÁI CỔ CẢI MỆNH THÀNH CÔNG!** Đã tẩy lại Linh Căn & Thể Chất Thượng Cổ!", results, player

    # Roll standard / premium items
    results = []
    has_ur = False
    for r in range(roll_count):
        roll_res, player = roll_single_item(player, banner_key)
        results.append(roll_res)
        if roll_res["is_ur"]:
            has_ur = True

        # Check duplicate conversion to Linh Bụi
        item_name = roll_res["item_name"]
        if db.has_item(player.user_id, item_name):
            linh_bui_gain = 100 if roll_res["is_ur"] else 20
            player.linh_bui += linh_bui_gain
            roll_res["duplicate_converted"] = linh_bui_gain
        else:
            db.add_item(player.user_id, item_name, "Gacha Result", 1)

    db.update_player(player)

    return True, "✨ **KHAI MỞ THẦN CỰC THÀNH CÔNG!**", results, player
