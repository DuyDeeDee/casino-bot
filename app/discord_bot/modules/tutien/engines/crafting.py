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

    # Thành công: có tỉ lệ nhận thêm Ngộ Tính
    if random.random() < 0.30:
        player.ngo_tinh += 1

    msg = f"💊 **LUYỆN ĐAN THÀNH CÔNG!** Đan lò ngưng tụ thành công **[{recipe['name']}]**! (Tỷ lệ đan thành: `{int(success_rate*100)}%`)"
    return True, msg, recipe, player

