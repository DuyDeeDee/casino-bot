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
        "desc": "Tốc độ tu vi +150%, Tâm cảnh -40%, Nghiệp lực +10 mỗi lần tu luyện, Lôi Kiếp x2 sát thương.",
        "exp_mult": 2.5,
        "tam_canh_penalty": -40,
        "karma_gain": 10,
        "tribulation_damage_mult": 2.0
    },
    "《Thái Huyền Kim Thân Quyết》": {
        "type": "Chủ Tu",
        "alignment": "Trung Lập",
        "desc": "Chuyển hóa 50% Linh lực nhận được thành Khí huyết (Luyện thể), trâu bò nhưng công pháp phép thuật kém.",
        "exp_mult": 1.0,
        "hp_convert": 0.5
    }
}
