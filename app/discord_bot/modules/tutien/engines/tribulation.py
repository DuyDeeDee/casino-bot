"""
Tribulation, Breakthrough, Kim Dan & Heart Demon Engine.
"""

import random
from typing import Dict, Any, List, Tuple
from app.discord_bot.modules.tutien.constants import (
    REALM_BASE_CHANCE,
    REALM_REQUIRED_TAM_CANH,
    REALM_BASE_DAMAGE,
    REALMS
)
from app.discord_bot.modules.tutien.models import CultivatorProfile


def calculate_breakthrough_chance(player: CultivatorProfile) -> float:
    """
    Calculates breakthrough success chance % according to developer spec:
    - Tam Canh < required -> 0%
    - Tam Canh bonus = (tam_canh - required) * 0.5
    - Can Co bonus = (can_co - 50) * 0.3
    - Nghiep Luc penalty = -(nghiep_luc - 20) * 0.2 if nghiep_luc > 20
    """
    req_tam_canh = REALM_REQUIRED_TAM_CANH.get(player.realm_index, 50)
    if player.tam_canh < req_tam_canh:
        return 0.0

    base_chance = REALM_BASE_CHANCE.get(player.realm_index, 50.0)
    tam_canh_bonus = (player.tam_canh - req_tam_canh) * 0.5
    can_co_bonus = (player.can_co - 50.0) * 0.3 if player.can_co > 50.0 else 0.0

    total_chance = base_chance + tam_canh_bonus + can_co_bonus

    if player.nghiep_luc > 20:
        total_chance -= (player.nghiep_luc - 20) * 0.2

    return max(5.0, min(total_chance, 95.0))


def calculate_tribulation_damage(player: CultivatorProfile, current_wave: int) -> int:
    """
    Calculates Tribulation Damage for wave `current_wave`:
    - Base = REALM_BASE_DAMAGE[realm] * (1 + current_wave * 0.15)
    - If Nghiep Luc > 50 (Ma Tu): damage *= 2.0 (Huyết Lôi Cửu Thiên)
    - If Linh Can is Lôi: damage *= 0.8
    """
    base = REALM_BASE_DAMAGE.get(player.realm_index, 1000) * (1.0 + (current_wave * 0.15))

    if player.nghiep_luc > 50:
        base *= 2.0

    if "Lôi" in player.linh_can_element:
        base *= 0.8

    return int(base)


def calculate_kim_dan_quality(player: CultivatorProfile, pill_quality: int = 0) -> int:
    """
    Calculates Kim Dan quality grade from 1 (Nhất Phẩm) to 9 (Cửu Phẩm).
    Formula: Linh Luc Purity + Pill Quality + Can Co + Dong Phu Level
    """
    purity = min(30, int((player.tam_canh / 100.0) * 30))
    can_co_pts = min(40, int((player.can_co / 100.0) * 40))
    dong_phu_pts = min(20, player.dong_phu_level * 2)

    total_pts = purity + pill_quality + can_co_pts + dong_phu_pts

    if total_pts >= 85:
        return 9  # Cửu Phẩm (Thượng Thừa)
    elif total_pts >= 75:
        return 8
    elif total_pts >= 65:
        return 7
    elif total_pts >= 55:
        return 6
    elif total_pts >= 45:
        return 5  # Ngũ Phẩm
    elif total_pts >= 35:
        return 4
    elif total_pts >= 25:
        return 3
    elif total_pts >= 15:
        return 2
    else:
        return 1  # Nhất Phẩm (Thấp nhất)


# HEART DEMON QUIZ DATABASE
HEART_DEMON_QUESTIONS: List[Dict[str, Any]] = [
    {
        "question": "🌑 TÂM MA: 'Năm xưa ngươi vì tranh đoạt một cọng Linh Thảo mà ra tay sát hại đồng môn. Ngươi có hối hận không?'",
        "options": [
            {"label": "A. Ta không hối hận! Cạnh tranh sinh tồn là quy luật Thiên Đạo!", "req": "dao_tam > 50", "correct": True},
            {"label": "B. Ta vô cùng hối hận, xin Thiên Đạo thứ tội...", "req": "tam_canh > 60", "correct": True},
            {"label": "C. Kẻ yếu làm mồi cho kẻ mạnh, câm miệng cho ta!", "req": "nghiep_luc > 30", "correct": True}
        ]
    },
    {
        "question": "🌑 TÂM MA: 'Nếu bằng hữu chí thân của ngươi đứng trước bờ vực diệt vong, ngươi sẵn sàng đánh đổi Đạo Tâm để cứu lấy họ không?'",
        "options": [
            {"label": "A. Chân Đạo không thể lùi bước, vạn vật có số mệnh riêng!", "req": "dao_tam > 40", "correct": True},
            {"label": "B. Thà phụ cả thiên hạ chứ quyết không phụ tri kỷ!", "req": "tam_canh > 50", "correct": True},
            {"label": "C. Tiện tay diệt luôn bằng hữu để cướp tài nguyên!", "req": "nghiep_luc > 50", "correct": True}
        ]
    }
]
