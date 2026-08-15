"""
Crafting Engine: Fail-rate Alchemy & Smithing, Global Auction House.
"""

import random
from typing import Tuple, Dict, Any, Optional
from app.discord_bot.modules.tutien.models import CultivatorProfile

# Danh Mục Công Thức Luyện Đan
ALCHEMY_RECIPES: Dict[str, Dict[str, Any]] = {
    "Vạn Linh Đan": {
        "name": "Vạn Linh Đan",
        "herbs": 3,
        "linh_thach": 100,
        "base_rate": 0.75,
        "type": "Linh Dược",
        "desc": "Cứu chữa tu sĩ bị Kinh Mạch Đoạn Tuyệt (!cuu-thuong)."
    },
    "Định Thần Đan": {
        "name": "Định Thần Đan",
        "herbs": 5,
        "linh_thach": 300,
        "base_rate": 0.70,
        "type": "Linh Dược",
        "desc": "Thanh lọc cơ thể, xóa bỏ Chấn Thương và Tẩu Hỏa Nhập Ma."
    },
    "Tẩy Tủy Phù": {
        "name": "Tẩy Tủy Phù",
        "herbs": 10,
        "linh_thach": 500,
        "base_rate": 0.60,
        "type": "Thần Phù",
        "desc": "Tẩy rửa căn cốt, quay lại phẩm cấp và thuộc tính Linh Căn."
    },
    "Cửu Chuyển Tái Tạo Đan": {
        "name": "Cửu Chuyển Tái Tạo Đan",
        "herbs": 15,
        "linh_thach": 1000,
        "base_rate": 0.50,
        "type": "Tiên Đan",
        "desc": "Phục hồi 100% HP, Mana, 100% Căn Cơ và xóa toàn bộ debuff nguy kịch (!dung-dan)."
    }
}


def craft_alchemy_pill(player: CultivatorProfile, recipe_key: str) -> Tuple[bool, str, Optional[Dict[str, Any]], CultivatorProfile]:
    """
    Attempts to craft a pill using ALCHEMY_RECIPES.
    Considers fire element bonus (+15% success) & Ngo Tinh (+1% per point).
    """
    recipe = ALCHEMY_RECIPES.get(recipe_key)
    if not recipe:
        return False, f"❌ Công thức đan dược **[{recipe_key}]** không tồn tại!", None, player

    if player.linh_thach < recipe["linh_thach"]:
        return False, f"❌ Không đủ Linh Thạch! Cần `{recipe['linh_thach']:,}` Linh Thạch (Hiện có: `{player.linh_thach:,}`).", None, player

    # Calculate success rate
    success_rate = recipe["base_rate"] + (player.ngo_tinh * 0.01)
    if "Hỏa" in player.linh_can_element:
        success_rate += 0.15  # Hỏa: +15% Tốc độ & Thành công Luyện Đan

    success_rate = min(0.95, max(0.20, success_rate))

    # Deduct Linh Thạch
    player.linh_thach -= recipe["linh_thach"]

    roll = random.random()
    if roll > success_rate:
        # Nổ Lò (Explosion)
        hp_loss = int(player.max_hp * 0.15)
        player.hp = max(1, player.hp - hp_loss)
        player.can_co = max(0.0, player.can_co - 2.0)
        msg = f"💥 **NỔ LÒ LUYỆN ĐAN!** Hỏa hầu mất kiểm soát! Đan dược hóa tro tàn, bạn bị linh hỏa phản phệ `- {hp_loss:,}` HP và `-2%` Căn Cơ!"
        return False, msg, recipe, player

# Danh Mục Công Thức Luyện Khí (Đúc Trang Bị & Pháp Bảo)
FORGING_RECIPES: Dict[str, Dict[str, Any]] = {
    "Hộ Thân Phù": {
        "name": "Hộ Thân Phù",
        "ore": 3,
        "linh_thach": 500,
        "base_rate": 0.75,
        "type": "Pháp Bảo Phòng Thủ",
        "desc": "Thần phù hộ thể, gia tăng +500 Khí Huyết Tối Đa."
    },
    "Tụ Linh Kỳ": {
        "name": "Tụ Linh Kỳ",
        "ore": 5,
        "linh_thach": 1000,
        "base_rate": 0.70,
        "type": "Trận Kỳ",
        "desc": "Kỳ trận tụ hội thiên địa linh khí, tăng +20% EXP khi bế quan tu luyện."
    },
    "Thái Ất Hộ Tâm Kính": {
        "name": "Thái Ất Hộ Tâm Kính",
        "ore": 8,
        "linh_thach": 2500,
        "base_rate": 0.60,
        "type": "Pháp Bảo Thượng Phẩm",
        "desc": "Gương báu hộ tâm thượng cổ, giảm 10% toàn bộ Sát Thương nhận vào trong PVE & PVP."
    },
    "Xích Lôi Tiên Kiếm": {
        "name": "Xích Lôi Tiên Kiếm",
        "ore": 15,
        "linh_thach": 5000,
        "base_rate": 0.50,
        "type": "Thần Binh",
        "desc": "Thần kiếm lôi đình, tăng +400 Sức Mạnh Công Kích & +15% Tỷ Lệ Bạo Kích."
    }
}


def craft_equipment_item(player: CultivatorProfile, recipe_key: str) -> Tuple[bool, str, Optional[Dict[str, Any]], CultivatorProfile]:
    """
    Attempts to forge equipment using FORGING_RECIPES.
    Considers metal/fire element bonus & Ngo Tinh.
    """
    recipe = FORGING_RECIPES.get(recipe_key)
    if not recipe:
        return False, f"❌ Bản vẽ đúc tạo **[{recipe_key}]** không tồn tại trong Luyện Khí Các!", None, player

    if player.linh_thach < recipe["linh_thach"]:
        return False, f"❌ Không đủ Linh Thạch! Cần `{recipe['linh_thach']:,}` Linh Thạch (Hiện có: `{player.linh_thach:,}`).", None, player

    # Calculate success rate (Kim +15%, Hỏa +10%, Ngộ Tính +1%/pt)
    success_rate = recipe["base_rate"] + (player.ngo_tinh * 0.01)
    if "Kim" in player.linh_can_element:
        success_rate += 0.15
    elif "Hỏa" in player.linh_can_element:
        success_rate += 0.10

    success_rate = min(0.95, max(0.20, success_rate))

    # Deduct Linh Thạch
    player.linh_thach -= recipe["linh_thach"]

    roll = random.random()
    if roll > success_rate:
        msg = f"💥 **ĐÚC KHÍ THẤT BẠI!** Thần Thiết bị nung chảy quá độ, linh khí phân tán! Mất trắng nguyên liệu và `{recipe['linh_thach']:,}` Linh Thạch!"
        return False, msg, recipe, player

    if random.random() < 0.25:
        player.ngo_tinh += 1

    msg = f"⚔️ **ĐÚC KHÍ THÀNH CÔNG!** Đã rèn đúc thành công bảo vật **[{recipe['name']}]**! (Tỷ lệ thành công: `{int(success_rate*100)}%`)"
    return True, msg, recipe, player

