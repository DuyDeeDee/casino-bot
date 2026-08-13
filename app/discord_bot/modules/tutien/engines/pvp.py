"""
Tu Tiên Advanced PVP Combat Engine («Tu Sĩ Tranh Phong / Sát Lục - Luận Đạo»)
5-Tier Depth Combat Matrix:
  1. Áp Lực Cảnh Giới (Realm Oppression)
  2. Độ Tinh Thuần Chân Nguyên (Purity vs Low Can Co - Anti P2W)
  3. Cuộc Chiến Thần Thức (Soul Consciousness Advantage & Dodge)
  4. Tương Khắc Đạo Vực & Ngũ Hành (Dao Domains & Elements)
  5. Công Pháp & Thần Binh (Gongfa, Equipment, Mana consumption)
"""

import math
import random
import time
from typing import Dict, Any, List, Tuple, Optional

from app.discord_bot.modules.tutien.models import CultivatorProfile, GongfaEquipment
from app.discord_bot.modules.tutien.constants import (
    REALMS, BODY_REALMS, PVP_RANKS, get_pvp_rank, ELEMENTS_NGU_HANH, ELEMENTS_DI_LINH_CAN
)
from app.discord_bot.modules.tutien.engines.pve import check_elemental_advantage, clean_element_name


def calculate_elo_change(winner_elo: int, loser_elo: int, k: int = 32) -> Tuple[int, int]:
    """
    Standard Elo rating calculation formula (FIDE standard).
    Returns (winner_gain, loser_loss).
    """
    expected_winner = 1.0 / (1.0 + 10.0 ** ((loser_elo - winner_elo) / 400.0))
    gain = int(round(k * (1.0 - expected_winner)))
    gain = max(5, min(gain, 60))
    return gain, gain


def calculate_realm_oppression(p1: CultivatorProfile, p2: CultivatorProfile) -> Tuple[float, float, float, str]:
    """
    Tier 1: Realm Oppression (Uy Áp Cảnh Giới).
    Returns (p1_dmg_mult, p1_def_mult, p1_crit_bonus, oppression_desc).
    """
    diff = p1.realm_index - p2.realm_index
    if diff > 0:
        dmg_mult = 1.0 + min(0.6, diff * 0.15)
        def_mult = 1.0 - min(0.4, diff * 0.10)
        crit_bonus = min(0.3, diff * 0.10)
        desc = f"👑 **Uy Áp Cảnh Giới (+{int((dmg_mult - 1.0)*100)}% Sát thương, +{int(crit_bonus*100)}% Bạo kích)**"
        return dmg_mult, def_mult, crit_bonus, desc
    elif diff < 0:
        diff_abs = abs(diff)
        dmg_mult = max(0.5, 1.0 - diff_abs * 0.10)
        def_mult = 1.0 + min(0.4, diff_abs * 0.08)
        desc = f"⚠️ **Chịu Uy Áp Cảnh Giới (-{int((1.0 - dmg_mult)*100)}% Sát thương)**"
        return dmg_mult, def_mult, 0.0, desc
    return 1.0, 1.0, 0.0, "Cân bằng Cảnh Giới"


def calculate_chan_nguyen_purity(attacker: CultivatorProfile, defender: CultivatorProfile) -> Tuple[float, str]:
    """
    Tier 2: Anti-P2W Rẻ Tiền (Độ Tinh Thuần Chân Nguyên).
    If attacker has solid Can Cơ (>= 80%) and defender rushed with low Căn Cơ (< 50%),
    Attacker ignores 30% of defender's armor/defense!
    """
    if attacker.can_co >= 80.0 and defender.can_co < 50.0:
        return 0.30, "✨ **Chân Nguyên Tinh Thuần Kích Hoạt (Bỏ Qua 30% Giáp & Kháng của kẻ ép cấp)!**"
    elif attacker.can_co >= 95.0:
        return 0.15, "✨ **Căn Cơ Viên Mãn (+15% Xuyên Giáp Chân Nguyên)!**"
    return 0.0, ""


def calculate_than_thuc_battle(attacker: CultivatorProfile, defender: CultivatorProfile) -> Tuple[float, float, str]:
    """
    Tier 3: Cuộc Chiến Thần Thức.
    Returns (attacker_dodge_bonus, defender_dodge_bonus, desc).
    """
    if attacker.than_thuc >= defender.than_thuc * 1.3:
        return 0.30, 0.0, f"🧠 **Thần Thức Áp Chế (+30% Né Tránh & Nhìn Thấu Bí Thuật)!**"
    elif defender.than_thuc >= attacker.than_thuc * 1.3:
        return 0.0, 0.30, f"🧠 **Đối thủ Thần Thức Áp Đảo (+30% Né Tránh)!**"
    return 0.0, 0.0, ""


def calculate_dao_domain_matchup(d1: Optional[str], d2: Optional[str]) -> Tuple[float, float, str]:
    """
    Tier 4: Tương Khắc Đạo Vực (Dao Domains).
    """
    if not d1 and not d2:
        return 1.0, 1.0, ""
    
    d1_str = d1 or ""
    d2_str = d2 or ""

    # Lôi Kiếm vs Niết Bàn
    if "Lôi Kiếm" in d1_str and "Niết Bàn" in d2_str:
        return 0.85, 1.15, "⚡⚔️ Lôi Kiếm bị 🔥💖 Niết Bàn Đạo trì hoãn kéo dài hao mòn chân nguyên!"
    if "Niết Bàn" in d1_str and "Lôi Kiếm" in d2_str:
        return 1.15, 0.85, "🔥💖 Niết Bàn Đạo hồi phục sức bền khắc chế Lôi Kiếm Đạo!"

    # U Hồn vs Phật Ma / Thanh Tâm
    if "U Hồn" in d1_str and ("Phật" in d2_str or "Thanh Tâm" in d2_str):
        return 0.70, 1.20, "💀🧠 U Hồn Đạo bị Phật Quang / Đạo Tâm thanh tẩy (-30% Sát thương)!"
    if ("Phật" in d1_str or "Thanh Tâm" in d1_str) and "U Hồn" in d2_str:
        return 1.30, 0.80, "☯️ Đạo Tâm Thanh Tịnh khắc chế tà thuật U Hồn (+30% Sát thương)!"

    # Trảm Không Kiếm Đạo
    if "Trảm Không" in d1_str:
        return 1.25, 0.90, "🌌⚔️ Trảm Không Kiếm Đạo chém rách Hư Không xuyên thấu phòng ngự!"

    return 1.0, 1.0, ""


def calculate_player_pvp_atk(player: CultivatorProfile, gongfa: Optional[GongfaEquipment] = None) -> Tuple[int, float]:
    """
    Calculates PVP Attack Power & Crit Chance.
    """
    base_atk = 300 + (player.realm_index * 250) + (player.body_realm_index * 150) + (player.ngo_tinh * 15)
    crit_chance = 0.10 + (player.co_duyen * 0.005)

    # Lingering debuff / Chấn thương
    now = time.time()
    if player.chan_thuong_until and player.chan_thuong_until > now:
        base_atk = int(base_atk * 0.70)
        crit_chance = max(0.02, crit_chance - 0.05)

    # Element perks
    elem = player.linh_can_element
    if "Hỏa" in elem:
        crit_chance += 0.20
        base_atk = int(base_atk * 1.10)
    elif "Kim" in elem:
        base_atk = int(base_atk * 1.20)
    elif "Lôi" in elem:
        crit_chance += 0.15
        base_atk = int(base_atk * 1.25)
    elif "Phong" in elem:
        base_atk = int(base_atk * 1.15)
    elif "Không Gian" in elem:
        base_atk = int(base_atk * 1.30)

    # Gongfa boost
    if gongfa and gongfa.chu_tu:
        if "Thôn Thiên" in gongfa.chu_tu:
            base_atk = int(base_atk * 1.35)
            crit_chance += 0.10
        elif "Thái Huyền" in gongfa.chu_tu:
            base_atk = int(base_atk * 1.15)

    # VIP boost
    if player.vip_level >= 3:
        base_atk = int(base_atk * (1.0 + player.vip_level * 0.02))

    return base_atk, min(0.75, crit_chance)


def simulate_pvp_turn(
    attacker: CultivatorProfile,
    defender: CultivatorProfile,
    turn: int,
    gongfa_a: Optional[GongfaEquipment] = None,
    gongfa_d: Optional[GongfaEquipment] = None
) -> Dict[str, Any]:
    """
    Executes a single turn in a PVP match using the 5-tier combat matrix.
    """
    # 1. Tier 1: Realm Oppression
    r_dmg, r_def, r_crit, r_desc = calculate_realm_oppression(attacker, defender)

    # 2. Tier 2: Purity vs Low Can Co
    armor_pen, purity_desc = calculate_chan_nguyen_purity(attacker, defender)

    # 3. Tier 3: Than Thuc Battle
    a_dodge, d_dodge, than_thuc_desc = calculate_than_thuc_battle(attacker, defender)

    # 4. Tier 4: Elements & Dao Domains
    elem_dmg, elem_def, elem_desc = check_elemental_advantage(attacker.linh_can_element, defender.linh_can_element)
    dao_dmg, dao_def, dao_desc = calculate_dao_domain_matchup(attacker.active_dao_domain, defender.active_dao_domain)

    # 5. Base ATK & Crit
    atk_val, crit_chance = calculate_player_pvp_atk(attacker, gongfa_a)
    crit_chance += r_crit

    # Check Dodge
    base_dodge = 0.05 + (0.15 if "Phong" in defender.linh_can_element else 0.0) + d_dodge
    is_dodged = (random.random() < min(0.40, base_dodge))

    if is_dodged:
        return {
            "turn": turn,
            "attacker": attacker.dao_hieu,
            "defender": defender.dao_hieu,
            "is_dodged": True,
            "is_crit": False,
            "damage": 0,
            "message": f"💨 **{defender.dao_hieu}** thi triển Thân Pháp hư ảo, né tránh hoàn toàn đòn đánh!",
            "flavor": than_thuc_desc or "Thân pháp siêu phàm né đòn"
        }

    # Calculate final damage
    is_crit = (random.random() < crit_chance)
    crit_mult = 2.0 if is_crit else 1.0

    raw_dmg = atk_val * r_dmg * elem_dmg * dao_dmg * crit_mult * random.uniform(0.9, 1.15)
    
    # Defense reduction factoring armor penetration
    def_reduction = (1.0 - armor_pen) * (0.85 if defender.body_realm_index >= 4 else 1.0)
    final_dmg = max(100, int(raw_dmg * def_reduction))

    # Skill name flavor
    skills = [
        "Vạn Kiếm Quy Tông", "Cửu U Ma Chưởng", "Thái Cực Bát Quái Chưởng",
        "Chấn Thiên Lôi Kích", "Băng Phong Tuyệt Sát", "Đại Diệt Tuyệt Thần Quang"
    ]
    skill_used = random.choice(skills)

    crit_tag = "💥 **BẠO KÍCH!** " if is_crit else ""
    msg = f"⚡ **{attacker.dao_hieu}** thi triển 《{skill_used}》! {crit_tag}Gây `{final_dmg:,}` Sát thương!"

    extra_notes = []
    if r_desc and "Uy Áp" in r_desc:
        extra_notes.append(r_desc)
    if purity_desc:
        extra_notes.append(purity_desc)
    if elem_desc and ("khắc" in elem_desc or "Bộc Phá" in elem_desc):
        extra_notes.append(f"🔮 {elem_desc}")
    if dao_desc:
        extra_notes.append(f"☯️ {dao_desc}")

    return {
        "turn": turn,
        "attacker": attacker.dao_hieu,
        "defender": defender.dao_hieu,
        "is_dodged": False,
        "is_crit": is_crit,
        "damage": final_dmg,
        "message": msg,
        "flavor": " | ".join(extra_notes) if extra_notes else ""
    }


def simulate_full_pvp_match(
    p1: CultivatorProfile,
    p2: CultivatorProfile,
    gongfa_1: Optional[GongfaEquipment] = None,
    gongfa_2: Optional[GongfaEquipment] = None,
    max_turns: int = 10
) -> Dict[str, Any]:
    """
    Simulates a full turn-based PVP duel between p1 and p2.
    Includes Niết Bàn Đạo resurrection mechanics.
    """
    hp1 = p1.hp
    hp2 = p2.hp
    mana1 = p1.mana
    mana2 = p2.mana

    niet_ban_used_1 = False
    niet_ban_used_2 = False

    combat_logs: List[Dict[str, Any]] = []

    # Determine first striker (Speed based on Than Thuc & Phong element)
    speed1 = p1.than_thuc + (50 if "Phong" in p1.linh_can_element else 0)
    speed2 = p2.than_thuc + (50 if "Phong" in p2.linh_can_element else 0)
    p1_first = speed1 >= speed2

    for turn in range(1, max_turns + 1):
        # 1st strike
        attacker = p1 if p1_first else p2
        defender = p2 if p1_first else p1
        gf_a = gongfa_1 if p1_first else gongfa_2
        gf_d = gongfa_2 if p1_first else gongfa_1

        t_res = simulate_pvp_turn(attacker, defender, turn, gf_a, gf_d)
        
        if p1_first:
            hp2 -= t_res["damage"]
        else:
            hp1 -= t_res["damage"]

        t_res["hp1_after"] = max(0, hp1)
        t_res["hp2_after"] = max(0, hp2)
        combat_logs.append(t_res)

        # Check Niết Bàn Đạo revive for Defender
        if p1_first and hp2 <= 0 and not niet_ban_used_2 and p2.active_dao_domain and "Niết Bàn" in p2.active_dao_domain:
            hp2 = int(p2.max_hp * 0.30)
            niet_ban_used_2 = True
            combat_logs.append({
                "turn": turn,
                "attacker": p2.dao_hieu,
                "defender": p1.dao_hieu,
                "is_dodged": False,
                "is_crit": False,
                "damage": 0,
                "message": f"🔥💖 **NIẾT BÀN TRÙNG SINH!** {p2.dao_hieu} dục hỏa trùng sinh, hồi sinh tại chỗ với `{hp2:,}` HP!",
                "flavor": "Niết Bàn Đạo Thần Thông"
            })

        elif not p1_first and hp1 <= 0 and not niet_ban_used_1 and p1.active_dao_domain and "Niết Bàn" in p1.active_dao_domain:
            hp1 = int(p1.max_hp * 0.30)
            niet_ban_used_1 = True
            combat_logs.append({
                "turn": turn,
                "attacker": p1.dao_hieu,
                "defender": p2.dao_hieu,
                "is_dodged": False,
                "is_crit": False,
                "damage": 0,
                "message": f"🔥💖 **NIẾT BÀN TRÙNG SINH!** {p1.dao_hieu} dục hỏa trùng sinh, hồi sinh tại chỗ với `{hp1:,}` HP!",
                "flavor": "Niết Bàn Đạo Thần Thông"
            })

        if hp1 <= 0 or hp2 <= 0:
            break

        # 2nd strike
        t_res_2 = simulate_pvp_turn(defender, attacker, turn, gf_d, gf_a)
        if p1_first:
            hp1 -= t_res_2["damage"]
        else:
            hp2 -= t_res_2["damage"]

        t_res_2["hp1_after"] = max(0, hp1)
        t_res_2["hp2_after"] = max(0, hp2)
        combat_logs.append(t_res_2)

        # Check Niết Bàn Đạo revive for Attacker
        if p1_first and hp1 <= 0 and not niet_ban_used_1 and p1.active_dao_domain and "Niết Bàn" in p1.active_dao_domain:
            hp1 = int(p1.max_hp * 0.30)
            niet_ban_used_1 = True
            combat_logs.append({
                "turn": turn,
                "attacker": p1.dao_hieu,
                "defender": p2.dao_hieu,
                "is_dodged": False,
                "is_crit": False,
                "damage": 0,
                "message": f"🔥💖 **NIẾT BÀN TRÙNG SINH!** {p1.dao_hieu} dục hỏa trùng sinh, hồi sinh tại chỗ với `{hp1:,}` HP!",
                "flavor": "Niết Bàn Đạo Thần Thông"
            })

        elif not p1_first and hp2 <= 0 and not niet_ban_used_2 and p2.active_dao_domain and "Niết Bàn" in p2.active_dao_domain:
            hp2 = int(p2.max_hp * 0.30)
            niet_ban_used_2 = True
            combat_logs.append({
                "turn": turn,
                "attacker": p2.dao_hieu,
                "defender": p1.dao_hieu,
                "is_dodged": False,
                "is_crit": False,
                "damage": 0,
                "message": f"🔥💖 **NIẾT BÀN TRÙNG SINH!** {p2.dao_hieu} dục hỏa trùng sinh, hồi sinh tại chỗ với `{hp2:,}` HP!",
                "flavor": "Niết Bàn Đạo Thần Thông"
            })

        if hp1 <= 0 or hp2 <= 0:
            break

    # Determine Winner
    if hp1 > 0 and hp2 <= 0:
        winner = p1
        loser = p2
    elif hp2 > 0 and hp1 <= 0:
        winner = p2
        loser = p1
    else:
        # Timeout tie-break by highest remaining HP %
        pct1 = max(0, hp1) / max(1, p1.max_hp)
        pct2 = max(0, hp2) / max(1, p2.max_hp)
        if pct1 >= pct2:
            winner = p1
            loser = p2
        else:
            winner = p2
            loser = p1


    return {
        "winner": winner,
        "loser": loser,
        "winner_id": winner.user_id,
        "loser_id": loser.user_id,
        "final_hp1": max(0, hp1),
        "final_hp2": max(0, hp2),
        "total_turns": len(combat_logs),
        "combat_logs": combat_logs
    }
