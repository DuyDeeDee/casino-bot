"""
Crafting Engine: Fail-rate Alchemy & Smithing, Global Auction House.
"""

import random
from typing import Tuple, Dict, Any
from app.discord_bot.modules.tutien.models import CultivatorProfile


def craft_alchemy_pill(player: CultivatorProfile, pill_name: str) -> Tuple[bool, str, CultivatorProfile]:
    """
    Attempts to craft pill (`!luyen-dan`).
    40% chance of Nổ Lò (explosion / phế đan).
    """
    roll = random.random()
    if roll < 0.40:
        # Nổ Lò
        hp_loss = int(player.max_hp * 0.15)
        player.hp = max(1, player.hp - hp_loss)
        player.can_co = max(0.0, player.can_co - 2.0)
        return False, f"💥 **NỔ LÒ!** Luyện đan thất bại, bị linh hỏa thương tổn `-{hp_loss}` HP và `-2%` Căn Cơ!", player

    player.ngo_tinh += 1
    return True, f"💊 **Luyện Đan Thành Công!** Đan lò ngưng tụ thành công **[{pill_name}]**! Nhận `+1` Ngộ Tính!", player
