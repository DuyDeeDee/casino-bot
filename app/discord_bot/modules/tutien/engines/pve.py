"""
Tu Tiên Hardcore PVE Engine: Săn Yêu, Tháp Thiên Cực, Bí Cảnh Cổ Đại, Boss Server & Thái Cổ Cấm Địa (Roguelike).
Includes Smart Enemy AI, Permadeath Injury, Loot Loss, Lingering Debuffs, and QTE One-Shot mechanics.
"""

import random
import time
from typing import Dict, Any, Tuple, List, Optional
from app.discord_bot.modules.tutien.constants import REALMS, REALM_REQUIRED_EXP
from app.discord_bot.modules.tutien.models import CultivatorProfile, GongfaEquipment


# --- ELEMENT COUNTER MATRIX ---
ELEMENT_COUNTERS = {
    ("🔥 Hỏa", "⚡ Kim"): {"dmg_mult": 1.5, "defense_mult": 0.8, "desc": "🔥 Hỏa khắc ⚡ Kim (+50% Sát thương)"},
    ("⚡ Kim", "🌳 Mộc"): {"dmg_mult": 1.5, "defense_mult": 0.8, "desc": "⚡ Kim khắc 🌳 Mộc (+50% Sát thương)"},
    ("🌳 Mộc", "🪨 Thổ"): {"dmg_mult": 1.5, "defense_mult": 0.8, "desc": "🌳 Mộc khắc 🪨 Thổ (+50% Sát thương)"},
    ("🪨 Thổ", "💧 Thủy"): {"dmg_mult": 1.5, "defense_mult": 0.8, "desc": "🪨 Thổ khắc 💧 Thủy (+50% Sát thương)"},
    ("💧 Thủy", "🔥 Hỏa"): {"dmg_mult": 1.5, "defense_mult": 0.8, "desc": "💧 Thủy khắc 🔥 Hỏa (+50% Sát thương)"},
}

# --- POOL YÊU THÚ THEO 10 ĐẠI CẢNH GIỚI TU TIÊN (30+ LOÀI YÊU MA THẦN THÚ) ---
MONSTER_NAMES_BY_REALM = {
    # 0. Luyện Khí (Realm 0 - 8)
    0: ["Xà Thú", "Dã Lang", "Hồ Tinh", "Hắc Phong Hùng", "Bạch Ngược Hổ", "Độc Giác Tê", "Thực Cốt Xà", "Quỷ Diện Chu"],
    # 1. Trúc Cơ (Realm 9 - 12)
    1: ["Xích Huyết Cự Mãng", "Băng Sương Cự Lang", "Thiềm Thừ Yêu Vương", "Đoạt Phách Ma Tinh", "Kim Sí Điêu Vương", "Địa Ngục Huyết Khôi"],
    # 2. Kim Đan (Realm 13 - 16)
    2: ["Cửu U Độc Long Mãng", "Tử Diễm Cuồng Sư", "Bạch Cốt Yêu Tôn", "Thiên Ma Dạ Xoa", "Hám Thiên Ma Hùng", "Thái Cổ Chu Tước Tàn Hồn"],
    # 3. Nguyên Anh (Realm 17 - 20)
    3: ["Thôn Thiên Ma Côn", "Vô Cực Cửu Đầu Xà", "Hắc Ám Kỳ Lân", "U Minh Ma Thần", "Bát Hoang Cự Thú", "Vạn Cổ Thi Vương"],
    # 4. Hóa Thần (Realm 21 - 24)
    4: ["Thái Cổ Chân Long Hóa Thân", "Thần Ma Bất Diệt Thi", "Hư Không Thôn Phệ Giả", "Hỗn Độn Ma Viên", "Cửu U Minh Vương"],
    # 5. Luyện Hư (Realm 25)
    5: ["Thái Cổ Thần Hoàng", "Vô Nhai Huyết Hải Chi Chủ", "Hư Không Chân Long", "Cửu Giới Ma Tôn"],
    # 6. Hợp Thể (Realm 26)
    6: ["Thái Hư Cổ Thần", "Hỗn Độn Đạo Tôn Tàn Linh", "Diệt Thế Hắc Long", "Vạn Giới Ma Hoàng"],
    # 7. Đại Thừa (Realm 27)
    7: ["Thiên Đạo Trảm Tội Giả", "Hỗn Độn Đệ Nhất Thần Ma", "Vĩnh Hằng Cấm Kỵ Thú", "Bất Hủ Chân Linh"],
    # 8. Độ Kiếp (Realm 28)
    8: ["Cửu Trọng Thiên Kiếp Chi Linh", "Đế Thi Phục Sinh", "Thiên Đạo Pháp Thân", "Thái Cổ Tru Thần Giả"],
    # 9. Tiên Đế (Realm 29)
    9: ["Vô Thượng Tiên Đế Tàn Ảnh", "Cực Đạo Chí Tôn Chi Thần", "Khởi Nguyên Ma Thần", "Vạn Cổ Độc Tôn Chi Linh"]
}

# Tuyệt Kỹ Độc Bản Của Yêu Thú (Signature Monster Skills)
MONSTER_SIGNATURE_SKILLS = [
    {"name": "《Thôn Thiên Thực Địa》", "dmg_mult": 1.4, "flavor": "há miệng như hắc động hút cạn linh khí xung quanh!"},
    {"name": "《Cửu U Huyết Trảo》", "dmg_mult": 1.35, "flavor": "móng vuốt rực huyết quang xé toạc hộ thể chân nguyên!"},
    {"name": "《Thiên Ma Đoạt Hồn》", "dmg_mult": 1.5, "flavor": "hóa thành ma ảnh oanh kích thẳng vào Thần Thức!"},
    {"name": "《Thái Cổ Long Tức》", "dmg_mult": 1.6, "flavor": "phun ra long tức hủy diệt nung chảy vạn vật!"},
    {"name": "《Hỗn Độn Diệt Thế Quang》", "dmg_mult": 1.7, "flavor": "phóng thích thần quang hỗn độn chấn động thiên địa!"},
    {"name": "《Hư Không Đoạt Mệnh Kích》", "dmg_mult": 1.45, "flavor": "xuyên qua khe nứt hư không tập kích chí mạng!"}
]

# Danh Hiệu Đột Biến Của Yêu Thú
MUTATION_TYPES = [
    {"prefix": "🔥 [CUỒNG BẠO] ", "hp_mult": 2.2, "atk_mult": 2.5, "tag": "Cuồng Bạo (+150% ATK)"},
    {"prefix": "⚡ [LÔI ĐÌNH] ", "hp_mult": 2.5, "atk_mult": 2.2, "tag": "Lôi Đình (Kháng Lôi, Sát thương giật)"},
    {"prefix": "💀 [TỬ LINH] ", "hp_mult": 2.8, "atk_mult": 2.0, "tag": "Tử Linh (Hấp thụ tinh huyết)"},
    {"prefix": "👑 [LÃNH CHÚA] ", "hp_mult": 3.5, "atk_mult": 2.4, "tag": "Lãnh Chúa (Bá vương một cõi, Phần thưởng x3)"}
]


def clean_element_name(element_raw: str) -> str:
    """Normalize element string for counter checks."""
    if not element_raw:
        return "🔥 Hỏa"
    for el in ["🔥 Hỏa", "💧 Thủy", "🌳 Mộc", "⚡ Kim", "🪨 Thổ", "⚡ Lôi", "❄️ Băng", "🌪️ Phong", "🌌 Không Gian / Thời Gian"]:
        if el in element_raw or el.split()[-1] in element_raw:
            return el
    return "🔥 Hỏa"


def check_elemental_advantage(attacker_elem: str, defender_elem: str) -> Tuple[float, float, str]:
    """Check element multiplier: Returns (dmg_mult, incoming_damage_mult, description)"""
    a_clean = clean_element_name(attacker_elem)
    d_clean = clean_element_name(defender_elem)

    if (a_clean, d_clean) in ELEMENT_COUNTERS:
        res = ELEMENT_COUNTERS[(a_clean, d_clean)]
        return res["dmg_mult"], res["defense_mult"], res["desc"]

    if a_clean == d_clean:
        return 0.6, 1.0, f"Kháng thuộc tính đồng hệ ({a_clean}) (-40% Sát thương)"

    if "Lôi" in a_clean:
        return 1.3, 0.9, "⚡ Lôi Hệ Bộc Phá (+30% Sát thương & Tê Liệt)"
    if "Băng" in a_clean:
        return 1.25, 0.85, "❄️ Băng Hệ Đóng Băng (-15% Sát thương nhận vào)"
    if "Phong" in a_clean:
        return 1.2, 0.8, "🌪️ Phong Hệ Thân Pháp (+20% Né Tránh)"
    if "Không Gian" in a_clean:
        return 1.4, 0.8, "🌌 Không Gian Diễn Biến (+40% Sát thương Đột Phá)"

    return 1.0, 1.0, "Giao tranh thuộc tính bình thường"


def generate_pve_monster(player_realm_index: int, floor_offset: int = 0, is_mutant: bool = False) -> Dict[str, Any]:
    """Generate monster scaled to player realm or tower floor. Has 15% chance to be Biến Dị Yêu Thú với danh hiệu riêng."""
    lvl = max(0, player_realm_index + floor_offset)
    
    # Map realm level (0-29) into 10 realm groups (0-9)
    if lvl <= 8:
        group_idx = 0   # Luyện Khí (0-8)
    elif lvl <= 12:
        group_idx = 1   # Trúc Cơ (9-12)
    elif lvl <= 16:
        group_idx = 2   # Kim Đan (13-16)
    elif lvl <= 20:
        group_idx = 3   # Nguyên Anh (17-20)
    elif lvl <= 24:
        group_idx = 4   # Hóa Thần (21-24)
    elif lvl == 25:
        group_idx = 5   # Luyện Hư
    elif lvl == 26:
        group_idx = 6   # Hợp Thể
    elif lvl == 27:
        group_idx = 7   # Đại Thừa
    elif lvl == 28:
        group_idx = 8   # Độ Kiếp
    else:
        group_idx = 9   # Tiên Đế

    names = MONSTER_NAMES_BY_REALM.get(group_idx, MONSTER_NAMES_BY_REALM[0])
    m_name = random.choice(names)
    
    elements = ["🔥 Hỏa", "💧 Thủy", "🌳 Mộc", "⚡ Kim", "🪨 Thổ", "⚡ Lôi", "❄️ Băng", "🌪️ Phong"]
    m_elem = random.choice(elements)

    if is_mutant:
        mutation = random.choice(MUTATION_TYPES)
        prefix = mutation["prefix"]
        hp_mult = mutation["hp_mult"]
        atk_mult = mutation["atk_mult"]
        mutant_tag = mutation["tag"]
    else:
        prefix = ""
        hp_mult = 1.0
        atk_mult = 1.0
        mutant_tag = None

    base_hp = int((2000 + (lvl * 1500)) * hp_mult)
    base_atk = int((150 + (lvl * 120)) * atk_mult)
    shield_max = int(base_hp * 0.35)

    return {
        "name": f"{prefix}{m_name} [{REALMS[min(lvl, len(REALMS)-1)]}]",
        "raw_name": m_name,
        "element": m_elem,
        "max_hp": base_hp,
        "current_hp": base_hp,
        "max_shield": shield_max,
        "current_shield": shield_max,
        "atk": base_atk,
        "is_broken": False,
        "stun_turns": 0,
        "is_mutant": is_mutant,
        "mutant_tag": mutant_tag,
        "is_raging": False,
        "action_history": []
    }


def generate_mirror_phantom_boss(player: CultivatorProfile) -> Dict[str, Any]:
    """Floor 10/20/30... Boss: Ảo Ảnh Của Chính Mình (Copies 100% stats & Gongfa of player)."""
    base_hp = player.max_hp * 2
    base_atk = 250 + (player.realm_index * 200) + (player.body_realm_index * 120)
    
    return {
        "name": f"🪞 ẢO ẢNH CỦA CHÍNH MÌNH — [{player.dao_hieu}]",
        "element": player.linh_can_element,
        "max_hp": base_hp,
        "current_hp": base_hp,
        "max_shield": int(base_hp * 0.40),
        "current_shield": int(base_hp * 0.40),
        "atk": base_atk,
        "is_broken": False,
        "stun_turns": 0,
        "is_mirror": True,
        "is_raging": False,
        "action_history": []
    }


def generate_roguelike_dungeon_matrix() -> List[Dict[str, Any]]:
    """Generate 5 procedural rooms for Thái Cổ Cấm Địa Roguelike dungeon."""
    rooms = [
        {"type": "MONSTER", "title": "Phòng 1: Cảnh Vực Yêu Thú", "desc": "Ổ dịch Yêu Quái canh giữ lối vào Cấm Địa."},
        {"type": "TRAP", "title": "Phòng 2: Bẫy Cổ Trận Thí Mạng", "desc": "Cổ Trận Ma Âm nguy hiểm! Cả đội chịu phạt 20% HP hoặc 1 người gánh 80% HP!"},
        {"type": "MIMIC", "title": "Phòng 3: Rương Thần Giả (Mimic)", "desc": "Rương báu phát ra ma khí u ám! Có 50% cơ hội chứa Tiên Ngọc hoặc Bị Cắn Chí Mạng!"},
        {"type": "MERCHANT", "title": "Phòng 4: Thương Nhân Cấm Địa Ẩn", "desc": "Lão già ẩn danh bán Đan Dược & Phù Cứu Thương với giá Tiên Ngọc."},
        {"type": "BOSS", "title": "Phòng 5: THÁI CỔ MÃNG HOÀNG (BOSS)", "desc": "Trùm Cấm Địa thức tỉnh tung chiêu Tụ Khí Cửu Thiên!"}
    ]
    return rooms


def calculate_player_pve_atk(player: CultivatorProfile) -> Tuple[int, float]:
    """Calculate player PVE attack and crit chance. Applies elemental ATK bonuses."""
    base_atk = 250 + (player.realm_index * 180) + (player.body_realm_index * 100)
    crit_chance = min(0.75, 0.15 + (player.ngo_tinh * 0.02) + (player.vip_level * 0.02))
    if player.is_di_linh_can:
        crit_chance += 0.10

    # --- NGŨ HÀNH ATK BONUSES (apply trong PVE) ---
    elem = player.linh_can_element
    if "Hỏa" in elem:
        # Hỏa: +20% Bạo kích (cờ chế độ crit)
        crit_chance = min(0.75, crit_chance + 0.20)
    elif "Kim" in elem:
        # Kim: +20% Sát thương Kiếm Đạo (ATK)
        base_atk = int(base_atk * 1.20)
    elif "Mộc" in elem:
        # Mộc: +25% Max HP → dẫn đến ATK bonus nhỏ thông qua sinh mệnh
        # (HP bonus được apply lúc tạo nhân vật / luỳen thể, ở đây cấp thêm +10% base ATK)
        base_atk = int(base_atk * 1.10)
    # Thổ: no ATK bonus, chỉ DEF — xử lý trong process_turn_action
    # Thủy: no ATK bonus, chỉ regen — xử lý trong AFK

    # --- DỊ LINH CĂN ATK BONUSES ---
    if "Lôi" in elem:
        crit_chance = min(0.75, crit_chance + 0.15)
        base_atk = int(base_atk * 1.20)
    elif "Phong" in elem:
        base_atk = int(base_atk * 1.15)
    elif "Không Gian" in elem:
        base_atk = int(base_atk * 1.30)

    return base_atk, crit_chance


def process_turn_action(
    player: CultivatorProfile,
    monster: Dict[str, Any],
    action: str  # "ATTACK", "GONGFA", "HEAL", "RUN"
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Process 1 Hardcore combat turn with Smart Enemy AI (Read Bar & Rage Mode)."""
    p_atk, crit_chance = calculate_player_pve_atk(player)
    dmg_mult, def_mult, advantage_desc = check_elemental_advantage(player.linh_can_element, monster["element"])

    # Smart AI Read Bar: If player spams same action > 2 times, monster gains +50% resistance
    history = monster.get("action_history", [])
    history.append(action)
    monster["action_history"] = history
    same_count = history.count(action)
    read_bar_penalty = 0.50 if same_count >= 3 else 1.0

    log = {
        "player_action": action,
        "damage_dealt": 0,
        "is_crit": False,
        "shield_broken_this_turn": False,
        "advantage_desc": advantage_desc,
        "monster_damage": 0,
        "player_healed": 0,
        "fled": False,
        "trigger_qte": False,
        "message": ""
    }

    if read_bar_penalty < 1.0:
        log["message"] += f"⚠️ **Yêu Thú Đọc Bài!** Bạn sử dụng `{action}` quá 3 lần, Boss tăng +50% Kháng Sát Thương!\n"

    # 1. Player Action
    if action == "RUN":
        if random.random() < 0.50:
            log["fled"] = True
            log["message"] += "🏃 Bạn thi triển Độn Thổ Thuật đào tẩu thành công!"
            return log, monster
        else:
            log["message"] += "❌ Độn Thổ thất bại! Yêu thú đã phong tỏa đường lui!"

    elif action == "HEAL":
        heal_amt = int(player.max_hp * 0.30)
        player.hp = min(player.max_hp, player.hp + heal_amt)
        log["player_healed"] = heal_amt
        log["message"] += f"💊 Bạn uống Khí Huyết Đan, phục hồi `+{heal_amt:,}` HP!"

    else:
        mult = 1.6 if action == "GONGFA" else 1.0
        is_crit = random.random() < crit_chance
        crit_mult = 2.0 if is_crit else 1.0
        if monster["is_broken"]:
            crit_mult *= 2.0

        final_dmg = int(p_atk * mult * dmg_mult * crit_mult * read_bar_penalty)
        log["damage_dealt"] = final_dmg
        log["is_crit"] = is_crit

        if monster["current_shield"] > 0:
            shield_dmg = int(final_dmg * 1.2)
            monster["current_shield"] = max(0, monster["current_shield"] - shield_dmg)
            if monster["current_shield"] == 0:
                monster["is_broken"] = True
                monster["stun_turns"] = 2
                log["shield_broken_this_turn"] = True
                log["message"] += f"💥 **VỠ GIÁP (BREAK)!** Đòn bạo kích đánh tan Pháp Trận! Yêu thú bị CHOÁNG 2 lượt!"
            else:
                log["message"] += f"⚔️ Đòn đánh gây `{final_dmg:,}` Sát thương lên Giáp phòng thủ!"
        else:
            monster["current_hp"] = max(0, monster["current_hp"] - final_dmg)
            crit_str = " **(BẠO KÍCH!)**" if is_crit else ""
            log["message"] += f"💥 Đòn đánh trúng đích gây `{final_dmg:,}` Sát thương{crit_str}!"

    # 2. Smart AI Rage Mode Trigger (< 20% HP)
    if monster["current_hp"] > 0 and (monster["current_hp"] / float(monster["max_hp"]) < 0.20) and not monster.get("is_raging"):
        monster["is_raging"] = True
        monster["atk"] = int(monster["atk"] * 2.0)
        monster["stun_turns"] = 0
        monster["is_broken"] = False
        log["message"] += "\n🔥 **CUỒNG BẠO!** Yêu Thú dưới 20% HP phát điên! Sát thương x2, Miễn nhiễm khống chế!"

    # 3. Monster Counter-Attack
    if monster["current_hp"] > 0 and not log["fled"]:
        if monster["stun_turns"] > 0 and not monster.get("is_raging"):
            monster["stun_turns"] -= 1
            if monster["stun_turns"] == 0:
                monster["is_broken"] = False
                monster["current_shield"] = monster["max_shield"] // 2
            log["message"] += "\n🌀 Yêu thú đang bị choáng, bỏ mất lượt tấn công!"
        else:
            # 15% chance to trigger 5s QTE One-Shot Ultimate
            if random.random() < 0.15:
                log["trigger_qte"] = True
                log["message"] += f"\n⚡⚡ **CẢNH BÁO TỤ KHÍ CỬU THIÊN!** {monster['name']} chuẩn bị tung đòn One-Shot 3,000% Sát Thương!"
            else:
                rage_bonus = 1.8 if monster.get("is_raging") else 1.0
                skill_mult = 1.0
                skill_desc = ""

                # 35% chance monster unleashes Signature Skill
                if random.random() < 0.35:
                    skill = random.choice(MONSTER_SIGNATURE_SKILLS)
                    skill_mult = skill["dmg_mult"]
                    skill_desc = f"\n👹 **TUYỆT KỸ YÊU MA!** {monster['name']} thi triển **{skill['name']}**, {skill['flavor']}"

                m_dmg = int(monster["atk"] * def_mult * rage_bonus * skill_mult * random.uniform(0.85, 1.15))

                # --- Thổ element: +30% Phòng thủ → giảm 30% damage nhận ---
                elem = player.linh_can_element
                if "Thổ" in elem:
                    m_dmg = int(m_dmg * 0.70)
                    if not log["message"].endswith("[Thổ]"):
                        log["message"] += " 🪨 **[Thổ Hệ Phòng Thủ -30% DMG]**"
                # Thủy: +15% HP hồi phục mỗi lượt nếu đủ HP
                elif "Thủy" in elem and player.hp < player.max_hp:
                    regen = int(player.max_hp * 0.05)
                    player.hp = min(player.max_hp, player.hp + regen)
                    log["message"] += f" 💧 **[Thủy Hệ Hồi Sinh +{regen:,} HP]**"

                player.hp = max(0, player.hp - m_dmg)
                log["monster_damage"] = m_dmg
                log["message"] += skill_desc + f"\n🐍 {monster['name']} phản công gây `{m_dmg:,}` Sát thương!"

    return log, monster


def process_quick_sweep_10x(player: CultivatorProfile, db) -> Dict[str, Any]:
    """VIP 2+ Quick Raid 10x Săn Yêu."""
    if player.tinh_luc < 100:
        return {"success": False, "reason": "Không đủ 100 Tinh Lực để thực hiện Quét Nhanh 10x (Hồi Tinh Lực hoặc dùng Tiên Mật)."}

    player.tinh_luc -= 100
    total_exp = 0
    total_linh_thach = 0
    tickets_dropped = 0
    herbs_dropped = 0

    for _ in range(10):
        monster = generate_pve_monster(player.realm_index)
        base_exp = 1500 + (player.realm_index * 800)
        base_lt = 100 + (player.realm_index * 50)
        
        total_exp += base_exp
        total_linh_thach += base_lt
        
        if random.random() < 0.05:
            tickets_dropped += 1
            player.linh_duyen_phu += 1
        herbs_dropped += random.randint(1, 3)
        ores_dropped = random.randint(1, 2) if random.random() < 0.60 else 0

    req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
    player.exp = min(req_exp, player.exp + total_exp)
    player.linh_thach += total_linh_thach

    if herbs_dropped > 0:
        db.add_item(player.user_id, "Thảo Dược Thô", "Nguyên Liệu Luyện Đan", herbs_dropped)
    if ores_dropped > 0:
        db.add_item(player.user_id, "Thần Thiết Thô", "Khoáng Thạch Luyện Khí", ores_dropped)

    db.update_player(player)

    return {
        "success": True,
        "total_exp": total_exp,
        "total_linh_thach": total_linh_thach,
        "tickets_dropped": tickets_dropped,
        "herbs_dropped": herbs_dropped,
        "ores_dropped": ores_dropped,
        "player": player
    }


def process_hardcore_defeat(player: CultivatorProfile, db, location_name: str = "Bí Cảnh Cấm Địa") -> Dict[str, Any]:
    """
    Process Permadeath Injury & Loot Loss on defeat.
    - Kinh Mạch Đoạn Tuyệt (10-minute timer).
    - 20% Spirit Stones dropped if no Thánh Thể Phù.
    - 15-25% Raw Materials (Herbs & Ore) dropped if no Thánh Thể Phù.
    - Applies Lingering Debuffs.
    """
    now = time.time()
    
    # Check insurance item (Thánh Thể Phù)
    has_protection = False
    if getattr(player, "thanh_the_phu", 0) > 0:
        player.thanh_the_phu -= 1
        has_protection = True

    stolen_lt = 0
    dropped_herbs = 0
    dropped_ores = 0

    if not has_protection:
        if player.linh_thach > 0:
            stolen_lt = int(player.linh_thach * 0.20)
            player.linh_thach -= stolen_lt

        inv = db.get_inventory(player.user_id)
        herb_item = next((i for i in inv if "Thảo Dược" in i["item_name"]), None)
        if herb_item and herb_item["quantity"] > 0:
            dropped_herbs = max(1, int(herb_item["quantity"] * random.uniform(0.15, 0.25)))
            db.consume_item(player.user_id, herb_item["item_name"], dropped_herbs)

        ore_item = next((i for i in inv if "Thần Thiết" in i["item_name"]), None)
        if ore_item and ore_item["quantity"] > 0:
            dropped_ores = max(1, int(ore_item["quantity"] * random.uniform(0.15, 0.25)))
            db.consume_item(player.user_id, ore_item["item_name"], dropped_ores)

    # Apply Kinh Mạch Đoạn Tuyệt (10 minutes)
    player.kinh_mach_doan_tuyet_until = now + 600

    # Apply random lingering debuff
    debuff_type = "DOC_TO" if random.random() < 0.50 else "TAM_MA_ONHIEM"
    player.lingering_debuff = debuff_type

    player.hp = int(player.max_hp * 0.05)
    db.update_player(player)

    return {
        "has_protection": has_protection,
        "stolen_lt": stolen_lt,
        "dropped_herbs": dropped_herbs,
        "dropped_ores": dropped_ores,
        "debuff_type": debuff_type,
        "timer_minutes": 10,
        "player": player
    }
