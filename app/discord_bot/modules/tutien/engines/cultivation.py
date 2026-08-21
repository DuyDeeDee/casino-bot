"""
Cultivation Logic Engine: Spiritual root creation, active cultivation formula, AFK meditation.
"""

import random
import time
from typing import Tuple, Dict, Any, Optional
from app.discord_bot.modules.tutien.constants import (
    SPIRITUAL_ROOT_QUALITIES,
    SPIRITUAL_ROOT_QUALITY_BUFF,
    ELEMENTS_NGU_HANH,
    ELEMENTS_DI_LINH_CAN,
    REALM_REQUIRED_EXP
)
from app.discord_bot.modules.tutien.models import CultivatorProfile, GongfaEquipment


def roll_spiritual_root() -> Tuple[str, str, bool]:
    """
    Roll random spiritual root quality & element according to specification probabilities:
    Qualities: 45% Phàm -> 25% Hạ -> 15% Trung -> 8% Thượng -> 1.5% Cực/Thiên -> 0.4% Tiên -> 0.09% Thánh -> 0.01% Hỗn Độn
    Elements: 95% Ngũ Hành (Hỏa, Thủy, Mộc, Kim, Thổ), 5% Dị Linh Căn (Lôi, Băng, Phong, Không Gian/Thời Gian)
    """
    # Roll quality
    rand_q = random.uniform(0, 100)
    cumulative = 0.0
    quality = "Phàm Phẩm"
    for q_name, weight in SPIRITUAL_ROOT_QUALITIES:
        cumulative += weight
        if rand_q <= cumulative:
            quality = q_name
            break

    # Roll element (5% Di Linh Can, 95% Ngu Hanh)
    is_di = random.random() < 0.05
    if is_di:
        # Special roll for Space/Time (0.05%) vs others
        if random.random() < 0.01:
            element = "🌌 Không Gian / Thời Gian"
        else:
            di_keys = ["⚡ Lôi", "❄️ Băng", "🌪️ Phong"]
            element = random.choice(di_keys)
    else:
        ngu_keys = list(ELEMENTS_NGU_HANH.keys())
        element = random.choice(ngu_keys)

    return quality, element, is_di


def calculate_cultivation_gain(
    player: CultivatorProfile,
    gongfa: GongfaEquipment,
    channel_linh_khi_percent: float = 1.0
) -> int:
    """
    Calculates Cultivation EXP gain based on formula:
    Tu Vi = Base * CP_Chủ_tu * Bonus_Linh_Căn * Buff_Động_Phủ * Nồng_Độ_Channel * Hệ_Số_Tâm_Cảnh * Bonus_Ngộ_Tính
    """
    # Exponential scaling: EXP gain tăng theo cảnh giới, tránh late-game bị vỡ
    # Formula: 200 × 1.4^realm → realm 0=200, realm 10=5782, realm 20=167k, realm 27=2.1M
    base_exp = int(200 * (1.4 ** player.realm_index))

    # Gongfa multiplier (default 1.0, Ma Dao +1.5, Chinh Dao 0.7)
    gongfa_mult = 1.0
    if gongfa.chu_tu and "Ma" in gongfa.chu_tu:
        gongfa_mult = 2.5  # +150%
    elif gongfa.chu_tu and "Thanh Tâm" in gongfa.chu_tu:
        gongfa_mult = 0.7  # -30%

    # Linh Can quality multiplier
    root_mult = SPIRITUAL_ROOT_QUALITY_BUFF.get(player.linh_can_quality, 1.0)
    if player.is_di_linh_can:
        root_mult *= 1.3

    # Dong Phu Level buff
    dong_phu_mult = 1.0 + (player.dong_phu_level - 1) * 0.15

    # Channel Linh Khi ratio (smooth gradient min 0.2 to max 1.0)
    channel_mult = max(0.2, min(1.0, channel_linh_khi_percent))

    # Tam Canh coefficient (0.5 to 1.5)
    tam_canh_mult = max(0.5, min(1.5, player.tam_canh / 70.0))

    # Ngo Tinh bonus
    ngo_tinh_mult = 1.0 + (player.ngo_tinh * 0.02)

    # VIP 1: +10% Thần Thức → tăng hiệu suất tu luyện thêm 10%
    vip1_bonus = 1.10 if player.vip_level >= 1 else 1.0

    # Linh Lực Tạp Chất debuff: Giảm 50% hiệu suất tu vi
    tap_chat_penalty = 0.50 if getattr(player, 'linh_luc_tap_chat', False) else 1.0

    total_exp = int(
        base_exp * gongfa_mult * root_mult * dong_phu_mult * channel_mult * tam_canh_mult * ngo_tinh_mult * vip1_bonus * tap_chat_penalty
    )
    return max(10, total_exp)


def process_active_cultivation(
    player: CultivatorProfile,
    gongfa: GongfaEquipment,
    channel_linh_khi: int
) -> Tuple[Dict[str, Any], CultivatorProfile]:
    """
    Processes active cultivation action (`!tu-luyen`).
    Costs 15 Tinh Lực.
    Returns result metadata dictionary and updated player object.
    """
    if player.tinh_luc < 15:
        return {"success": False, "reason": "Không đủ Tinh Lực! Cần 15 Tinh Lực (Hồi 2 điểm mỗi 5 phút)."}, player

    # Deduct Stamina
    player.tinh_luc -= 15

    # Check Tau Hoa Nhap Ma debuff
    now = time.time()
    is_tau_hoa = player.tau_hoa_nhap_ma_until and player.tau_hoa_nhap_ma_until > now

    channel_percent = channel_linh_khi / 100000.0
    gained_exp = calculate_cultivation_gain(player, gongfa, channel_percent)

    if is_tau_hoa:
        gained_exp = int(gained_exp * 0.5)

    # Roll random cultivation outcome event
    # 70% Normal, 15% Tieu Thanh, 5% Don Ngo, 10% Tau Hoa
    roll = random.random()
    event_type = "Bình Thường"
    message = ""

    if roll < 0.70:
        event_type = "Bình Thường"
        message = f"Vận công chuyển hóa linh khí, tích lũy `+{gained_exp:,}` Tu Vi."
    elif roll < 0.85:
        event_type = "Tiểu Thành"
        gained_exp = int(gained_exp * 1.5)
        player.tam_canh = min(100.0, player.tam_canh + 2.0)
        message = f"🌟 **Tiểu Thành!** Linh lực đột nhiên thanh thoát, nhận `+{gained_exp:,}` Tu Vi và `+2%` Tâm Cảnh!"
    elif roll < 0.90:
        event_type = "Đốn Ngộ"
        gained_exp = int(gained_exp * 5.0)
        player.ngo_tinh += 1
        message = f"🌀 **ĐỐN NGỘ!** Linh quang lóe sáng, ngộ ra chân lý! Nhận `+{gained_exp:,}` Tu Vi và `+1` Ngộ Tính!"
    else:
        event_type = "Tẩu Hỏa Nhập Ma"
        gained_exp = max(0, int(gained_exp * 0.3))
        hp_loss = int(player.max_hp * 0.10)
        player.hp = max(1, player.hp - hp_loss)
        player.tam_canh = max(0.0, player.tam_canh - 5.0)
        player.tau_hoa_nhap_ma_until = now + 1800  # Debuff Tẩu Hỏa Nhập Ma trong 30 phút (-50% EXP)
        message = f"⚠️ **Linh Khí Bạo Động!** Mạch máu tắc nghẽn, bị trừ `{hp_loss}` HP, `-5%` Tâm Cảnh, dính Tẩu Hỏa Nhập Ma (30p) và chỉ nhận `+{gained_exp:,}` Tu Vi."

    # Add EXP (cap at max 100% required exp until breakthrough)
    req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
    player.exp = min(req_exp, player.exp + gained_exp)

    res = {
        "success": True,
        "event_type": event_type,
        "gained_exp": gained_exp,
        "message": message,
        "current_exp": player.exp,
        "required_exp": req_exp,
        "can_breakthrough": player.exp >= req_exp
    }
    return res, player
