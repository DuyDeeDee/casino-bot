"""
Body Refining & Dao Domain Fusion Engines.
"""

from typing import Tuple, Dict, Any, Optional
from app.discord_bot.modules.tutien.constants import BODY_REALMS, DAO_FUSION_MATRIX
from app.discord_bot.modules.tutien.models import CultivatorProfile


def upgrade_body_refining(player: CultivatorProfile, linh_thach_cost: int = 500) -> Tuple[bool, str, CultivatorProfile]:
    """
    Upgrades player Body Refining realm (`!luyen-the`).
    Consumes Linh Thạch. Boosts Max HP.
    """
    if player.linh_thach < linh_thach_cost:
        return False, f"Không đủ Linh Thạch! Cần `{linh_thach_cost:,}` Linh Thạch.", player

    if player.body_realm_index >= len(BODY_REALMS) - 1:
        return False, "Bạn đã đạt cấp độ Luyện Thể tối cao: **Bất Diệt Thể**!", player

    player.linh_thach -= linh_thach_cost
    player.body_realm_index += 1
    player.body_realm_name = BODY_REALMS[player.body_realm_index]
    
    # Boost HP by +25% per realm
    hp_gain = int(player.max_hp * 0.25) + 500
    player.max_hp += hp_gain
    player.hp += hp_gain

    return True, f"💪 **Tôi Thể Thành Công!** Bạn đã đột phá Luyện Thể lên **[{player.body_realm_name}]**, nhận `+{hp_gain:,}` Max HP!", player


def fuse_dao_domains(dao_1: str, dao_2: str) -> Optional[Dict[str, str]]:
    """
    Fuse two Dao branches into a Complex Domain (`!ngo-dao`).
    """
    pair_1 = (dao_1, dao_2)
    pair_2 = (dao_2, dao_1)
    if pair_1 in DAO_FUSION_MATRIX:
        return DAO_FUSION_MATRIX[pair_1]
    elif pair_2 in DAO_FUSION_MATRIX:
        return DAO_FUSION_MATRIX[pair_2]
    return None
