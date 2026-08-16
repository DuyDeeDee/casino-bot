"""
Gacha Engine: 3 Banner System («THIÊN ĐỊA DUYÊN CƠ»), Soft Pity (60+), Hard Pity (80), Wishlist & Shard Shop.
"""

import random
from typing import Tuple, List, Dict, Any, Optional
from app.discord_bot.modules.tutien.constants import (
    GACHA_BANNERS, GACHA_ITEMS_TUBAO, GACHA_ITEMS_PREMIUM, LINH_BUI_SHOP, SPIRITUAL_ROOT_QUALITIES, ELEMENTS_NGU_HANH, ELEMENTS_DI_LINH_CAN
)
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.db import TuTienDB


def roll_single_item(player: CultivatorProfile, banner_type: str) -> Tuple[Dict[str, Any], CultivatorProfile]:
    """
    Executes a single roll on banner `banner_type`.
    - `tubao` (Banner Thường - F2P): Max Thiên Cấp (SR 3%), Địa Cấp (27%), Huyền (35%), Phàm (35%). Có thể rơi vé Tiên Duyên Phù.
    - `tiencac` (Banner VIP): Đế Cấp UR (0.7% + Soft/Hard Pity 60-80), Thiên Cấp SR (4.3%), Wishlist 100% & Linh Bụi.
    """
    # 1. BANNER THƯỜNG — TỤ BẢO CÁC (F2P)
    if banner_type == "tubao":
        rand_val = random.random()
        if rand_val < 0.015:  # 1.5% SR
            grade = "🟡 Thiên Cấp (SR)"
            sr_options = [x for x in GACHA_ITEMS_TUBAO if "Thiên Cấp" in x[2]]
            item_name = random.choice(sr_options)[0]
        elif rand_val < 0.20:  # 18.5% Địa Cấp
            grade = "🟣 Địa Cấp"
            dia_options = [x for x in GACHA_ITEMS_TUBAO if "Địa Cấp" in x[2]]
            item_name = random.choice(dia_options)[0]
        elif rand_val < 0.55:  # 35% Huyền Cấp
            grade = "🔵 Huyền Cấp"
            huyen_options = [x for x in GACHA_ITEMS_TUBAO if "Huyền Cấp" in x[2]]
            item_name = random.choice(huyen_options)[0]
        else:  # 45% Phàm Cấp
            grade = "🟢 Phàm Cấp"
            pham_options = [x for x in GACHA_ITEMS_TUBAO if "Phàm Cấp" in x[2]]
            item_name = random.choice(pham_options)[0]

        return {
            "item_name": item_name,
            "grade": grade,
            "is_ur": False,
            "pity_count": player.soft_pity_count
        }, player

    # 2. BANNER VIP — CỬU THIÊN TIÊN CÁC (PREMIUM)
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

        # Ưu tiên Wishlist (Định Hướng Đạo Vận) nếu có
        if player.wishlist_item:
            matched = [x for x in GACHA_ITEMS_PREMIUM if "Đế Cấp" in x[2] and player.wishlist_item.lower() in x[0].lower()]
            if matched:
                item_name = matched[0][0]
                player.wishlist_item = None
            else:
                ur_options = [x for x in GACHA_ITEMS_PREMIUM if "Đế Cấp" in x[2]]
                item_name = random.choice(ur_options)[0]
        else:
            ur_options = [x for x in GACHA_ITEMS_PREMIUM if "Đế Cấp" in x[2]]
            item_name = random.choice(ur_options)[0]

    else:
        # Roll SR (4.3%) vs Địa/Huyền
        if rand_val < (ur_rate + 0.043):
            grade = "🟡 Thiên Cấp (SR)"
            sr_options = [x for x in GACHA_ITEMS_PREMIUM if "Thiên Cấp" in x[2]]
            item_name = random.choice(sr_options)[0]
        elif rand_val < (ur_rate + 0.293):
            grade = "🟣 Địa Cấp"
            dia_options = [x for x in GACHA_ITEMS_PREMIUM if "Địa Cấp" in x[2]]
            item_name = random.choice(dia_options)[0]
        else:
            grade = "🔵 Huyền Cấp"
            other_options = [x for x in GACHA_ITEMS_PREMIUM if "Huyền Cấp" in x[2]]
            item_name = random.choice(other_options)[0]

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

    # Special handling for Thái Cổ Cải Mệnh Đài (Reroll Spiritual Root theo tỷ lệ xác suất chuẩn)
    if banner_key == "caimenh":
        results = []
        qualities, weights = zip(*SPIRITUAL_ROOT_QUALITIES)
        for _ in range(roll_count):
            # Roll quality theo đúng bảng xác suất chuẩn (0.01% Hỗn Độn ... 45% Phàm Phẩm)
            chosen_quality = random.choices(qualities, weights=weights, k=1)[0]
            
            # Chỉ có 10% cơ hội thức tỉnh Dị Linh Căn (90% là Ngũ Hành thường)
            if random.random() < 0.10:
                chosen_element = random.choice(list(ELEMENTS_DI_LINH_CAN.keys()))
                is_di = True
            else:
                chosen_element = random.choice(list(ELEMENTS_NGU_HANH.keys()))
                is_di = False

            player.linh_can_quality = chosen_quality
            player.linh_can_element = chosen_element
            player.is_di_linh_can = is_di

            is_top_tier = chosen_quality in ["Tiên Phẩm", "Thánh Phẩm", "Hỗn Độn"] or is_di
            grade_str = "🔴 Tiên Thể / Dị Căn" if is_top_tier else "🔵 Thường Căn"
            results.append({"item_name": f"✨ [CẢI MỆNH] {chosen_quality} ({chosen_element})", "grade": grade_str, "is_ur": is_top_tier})
        
        db.update_player(player)
        return True, "✨ **THÁI CỔ CẢI MỆNH THÀNH CÔNG!** Đã cải tạo lại Linh Căn & Đạo Cốt!", results, player

    # Roll standard / premium items
    results = []
    has_ur = False
    for r in range(roll_count):
        roll_res, player = roll_single_item(player, banner_key)
        results.append(roll_res)
        if roll_res["is_ur"]:
            has_ur = True

        # Check duplicate conversion to Linh Bụi (Nerfed: 50 for UR, 5 for non-UR)
        item_name = roll_res["item_name"]
        if db.has_item(player.user_id, item_name):
            linh_bui_gain = 50 if roll_res["is_ur"] else 5
            player.linh_bui += linh_bui_gain
            roll_res["duplicate_converted"] = linh_bui_gain
        else:
            db.add_item(player.user_id, item_name, "Gacha Result", 1)

    db.update_player(player)

    return True, "✨ **KHAI MỞ THẦN CỰC THÀNH CÔNG!**", results, player
