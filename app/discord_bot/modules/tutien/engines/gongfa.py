"""
Gongfa Engine: Gongfa Double-Edged Sword Attributes & Slot Management.
"""

from typing import Dict, Any, List
from app.discord_bot.modules.tutien.models import GongfaEquipment

GONGFA_DATABASE: Dict[str, Dict[str, Any]] = {
    "《Phàm Nhân Quyết》": {
        "type": "Chủ Tu",
        "alignment": "Trung Lập",
        "desc": "Công pháp căn bản của tu sĩ nhập môn. Tốc độ tích lũy tu vi bình thường.",
        "exp_mult": 1.0
    },
    "《Thanh Tâm Đạo Kinh》": {
        "type": "Chủ Tu",
        "alignment": "Chính Đạo",
        "desc": "Tốc độ tu vi -30%, Tâm cảnh +50%, Đột phá +20%, Nghiệp lực tự giảm 1/ngày.",
        "exp_mult": 0.7,
        "tam_canh_buff": 50,
        "breakthrough_buff": 20,
        "daily_karma_reduction": 1
    },
    "《Thôn Thiên Ma Công》": {
        "type": "Chủ Tu",
        "alignment": "Ma Đạo",
        "desc": "Tốc độ tu vi +150%, Tâm cảnh -40%, Nghiệp lực +10 mỗi lần tu luyện, Lôi Kiếp x2 sát thương, ATK +35%.",
        "exp_mult": 2.5,
        "tam_canh_penalty": -40,
        "karma_gain": 10,
        "tribulation_damage_mult": 2.0,
        "atk_mult": 1.35
    },
    "《Thái Huyền Kim Thân Quyết》": {
        "type": "Chủ Tu (Luyện Thể)",
        "alignment": "Trung Lập",
        "desc": "Chuyển hóa 50% Linh lực nhận được thành Khí huyết (Luyện thể), trâu bò nhưng công pháp phép thuật kém.",
        "exp_mult": 1.0,
        "hp_convert": 0.5
    },
    "《Thái Huyền Đạo Kinh》": {
        "type": "Chủ Tu (Thiên Cấp)",
        "alignment": "Chính Đạo",
        "desc": "Đạo pháp tự nhiên, tăng +30% EXP tu luyện, +15% ATK và +15% Tâm Cảnh.",
        "exp_mult": 1.3,
        "tam_canh_buff": 15,
        "atk_mult": 1.15
    },
    "《Thái Hư Kiếm Điển》": {
        "type": "Chủ Tu (Thiên Cấp)",
        "alignment": "Chính Đạo",
        "desc": "Bí kíp Kiếm Đạo tối thượng, tăng +25% Sát Thương Kiếm Đạo & +10% Bạo Kích PVP.",
        "exp_mult": 1.15,
        "sword_dmg_buff": 0.25,
        "crit_buff": 0.10
    },
    "《Bất Diệt Chân Kinh》": {
        "type": "Chủ Tu Luyện Thể (Đế Cấp)",
        "alignment": "Thần Đạo",
        "desc": "Công pháp rèn luyện Bất Diệt Thần Thể, tăng +5,000 Max HP và giảm 15% Sát Thương PVP gánh chịu.",
        "exp_mult": 1.2,
        "max_hp_bonus": 5000,
        "pvp_dmg_reduction": 0.15
    }
}
