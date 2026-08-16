"""
Constants, formulas, and configuration matrices for Tu Tien: «ĐẠI ĐẠO TRANH PHONG»
Includes Gacha 3 Banner System, Soft/Hard Pity Rates, Shard Shop & Monetization Catalog.
"""

from typing import Dict, List, Tuple, Any

# --- CẢNH GIỚI (REALMS) ---
REALMS: List[str] = [
    "Luyện Khí Tầng 1", "Luyện Khí Tầng 2", "Luyện Khí Tầng 3",
    "Luyện Khí Tầng 4", "Luyện Khí Tầng 5", "Luyện Khí Tầng 6",
    "Luyện Khí Tầng 7", "Luyện Khí Tầng 8", "Luyện Khí Tầng 9",
    "Trúc Cơ Sơ Kỳ", "Trúc Cơ Trung Kỳ", "Trúc Cơ Hậu Kỳ", "Trúc Cơ Viên Mãn",
    "Kim Đan Sơ Kỳ", "Kim Đan Trung Kỳ", "Kim Đan Hậu Kỳ", "Kim Đan Viên Mãn",
    "Nguyên Anh Sơ Kỳ", "Nguyên Anh Trung Kỳ", "Nguyên Anh Hậu Kỳ", "Nguyên Anh Viên Mãn",
    "Hóa Thần Sơ Kỳ", "Hóa Thần Trung Kỳ", "Hóa Thần Hậu Kỳ", "Hóa Thần Viên Mãn",
    "Luyện Hư", "Hợp Thể", "Đại Thừa", "Độ Kiếp", "Tiên Đế"
]

# Base Required EXP per realm index
REALM_REQUIRED_EXP: Dict[int, int] = {
    0: 1000, 1: 2500, 2: 5000, 3: 10000, 4: 18000, 5: 30000, 6: 50000, 7: 80000, 8: 120000,
    9: 200000, 10: 320000, 11: 500000, 12: 800000,
    13: 1200000, 14: 1800000, 15: 2600000, 16: 3800000,
    17: 5500000, 18: 8000000, 19: 12000000, 20: 18000000,
    21: 26000000, 22: 38000000, 23: 55000000, 24: 80000000,
    25: 120000000, 26: 200000000, 27: 350000000, 28: 600000000, 29: 1000000000
}

# Required Tâm Cảnh for safe breakthrough
REALM_REQUIRED_TAM_CANH: Dict[int, int] = {
    idx: min(95, 10 + idx * 3) for idx in range(len(REALMS))
}

# Base Tribulation Damage per realm
REALM_BASE_DAMAGE: Dict[int, int] = {
    idx: 500 * (idx + 1) * (1 + idx * 0.25) for idx in range(len(REALMS))
}

# Base breakthrough chance %
REALM_BASE_CHANCE: Dict[int, float] = {
    idx: max(15.0, 95.0 - idx * 2.5) for idx in range(len(REALMS))
}

# Đan Dược Đột Phá Bắt Buộc cho các mốc Đại Cảnh Giới (Major Bottlenecks)
REALM_BREAKTHROUGH_PILLS: Dict[int, Dict[str, Any]] = {
    8: {
        "pill_name": "Trúc Cơ Đan",
        "from_realm": "Luyện Khí Tầng 9",
        "to_realm": "Trúc Cơ Sơ Kỳ",
        "desc": "Thanh tẩy phàm căn, đúc tạo Tiên Thiên Đạo Thể."
    },
    12: {
        "pill_name": "Kim Đan Sa",
        "from_realm": "Trúc Cơ Viên Mãn",
        "to_realm": "Kim Đan Sơ Kỳ",
        "desc": "Ngưng kết Cửu Chuyển Kim Đan, bất hủ bất diệt."
    },
    16: {
        "pill_name": "Ngưng Anh Đan",
        "from_realm": "Kim Đan Viên Mãn",
        "to_realm": "Nguyên Anh Sơ Kỳ",
        "desc": "Phá đan hóa anh, thần thức xuất khiếu."
    },
    20: {
        "pill_name": "Hóa Thần Đan",
        "from_realm": "Nguyên Anh Viên Mãn",
        "to_realm": "Hóa Thần Sơ Kỳ",
        "desc": "Dung hợp thiên địa quy tắc, chân thân hóa thần."
    },
    24: {
        "pill_name": "Phá Hư Đan",
        "from_realm": "Hóa Thần Viên Mãn",
        "to_realm": "Luyện Hư",
        "desc": "Xuyên phá hư không, lĩnh ngộ đại đạo pháp tắc."
    }
}


# --- LINH CĂN (SPIRITUAL ROOTS) ---
SPIRITUAL_ROOT_QUALITIES: List[Tuple[str, float]] = [
    ("Phàm Phẩm", 45.0),
    ("Hạ Phẩm", 25.0),
    ("Trung Phẩm", 15.0),
    ("Thượng Phẩm", 8.0),
    ("Cực Phẩm / Thiên Phẩm", 1.5),
    ("Tiên Phẩm", 0.4),
    ("Thánh Phẩm", 0.09),
    ("Hỗn Độn", 0.01)
]

SPIRITUAL_ROOT_QUALITY_BUFF: Dict[str, float] = {
    "Phàm Phẩm": 1.0,
    "Hạ Phẩm": 1.2,
    "Trung Phẩm": 1.5,
    "Thượng Phẩm": 2.0,
    "Cực Phẩm / Thiên Phẩm": 3.0,
    "Tiên Phẩm": 5.0,
    "Thánh Phẩm": 8.0,
    "Hỗn Độn": 15.0
}

# Linh Căn Types & Mechanics
ELEMENTS_NGU_HANH: Dict[str, Dict[str, str]] = {
    "🔥 Hỏa": {"desc": "+20% Bạo kích, +15% Tốc độ Luyện Đan, tăng uy lực Hỏa Pháp.", "crit_bonus": 0.20, "alchemy_speed": 0.15},
    "💧 Thủy": {"desc": "+15% Hồi phục HP/MP, Tăng 10% Tâm cảnh khi thiền định, Thủy Pháp khống chế.", "regen_bonus": 0.15, "tam_canh_buff": 0.10},
    "🌳 Mộc": {"desc": "+25% Sinh mệnh tối đa, tăng hiệu quả trồng Linh dược, Độc thuật gây DOT.", "hp_bonus": 0.25},
    "⚡ Kim": {"desc": "+20% Sát thương Kiếm Đạo, xuyên 15% Giáp/Pháp bảo đối phương.", "sword_dmg": 0.20, "armor_pen": 0.15},
    "🪨 Thổ": {"desc": "+30% Phòng thủ, giảm sát thương Lôi Kiếp 10%, tăng hiệu quả Trận pháp Động phủ.", "def_bonus": 0.30, "lôi_kiếp_res": 0.10}
}

ELEMENTS_DI_LINH_CAN: Dict[str, Dict[str, str]] = {
    "⚡ Lôi": {"desc": "+30% Tốc độ tu luyện Lôi Hệ, Kháng 20% sát thương Thiên Kiếp, +15% Bạo kích.", "exp_bonus": 0.30, "lôi_kiếp_res": 0.20, "crit_bonus": 0.15},
    "❄️ Băng": {"desc": "Khống chế tuyệt đối (Đóng băng lượt đánh đối thủ), giảm 10% Tẩu Hỏa Nhập Ma.", "freeze_chance": 0.25, "tau_hoa_res": 0.10},
    "🌪️ Phong": {"desc": "+40% Tốc độ Thân pháp, Né tránh đòn tấn công +15%, cướp tài nguyên dễ thoát ẩn.", "speed_bonus": 0.40, "dodge_bonus": 0.15},
    "🌌 Không Gian / Thời Gian": {"desc": "Tự do di chuyển đến các Bí cảnh bị khóa, tua nhanh thời gian Bế Quan.", "afk_speedup": 0.50}
}


# --- LUYỆN THỂ (BODY REFINING REALMS & CONFIG) ---
BODY_REALMS: List[str] = [
    "Phàm Thân", "Tôi Thể", "Luyện Bì", "Luyện Nhục", "Luyện Cốt",
    "Luyện Tủy", "Luyện Huyết", "Kim Thân", "Bất Diệt Thể"
]

BODY_REALM_CONFIG: Dict[int, Dict[str, Any]] = {
    1: {  # Phàm Thân -> Tôi Thể
        "to_realm": "Tôi Thể",
        "req_realm_index": 2,      # Luyện Khí Tầng 3
        "req_realm_name": "Luyện Khí Tầng 3",
        "linh_thach": 5000,
        "herbs": 5,
        "tinh_luc": 10,
        "base_rate": 0.95,
        "hp_gain_flat": 500,
        "hp_gain_pct": 0.05,
        "desc": "Cường hóa gân cốt cơ bản, bài trừ phàm trần tạp chất."
    },
    2: {  # Tôi Thể -> Luyện Bì
        "to_realm": "Luyện Bì",
        "req_realm_index": 5,      # Luyện Khí Tầng 6
        "req_realm_name": "Luyện Khí Tầng 6",
        "linh_thach": 15000,
        "herbs": 10,
        "tinh_luc": 15,
        "base_rate": 0.85,
        "hp_gain_flat": 1000,
        "hp_gain_pct": 0.08,
        "desc": "Làn da cứng như da đồng, chống đỡ đòn đánh ngoại lực."
    },
    3: {  # Luyện Bì -> Luyện Nhục
        "to_realm": "Luyện Nhục",
        "req_realm_index": 8,      # Luyện Khí Tầng 9
        "req_realm_name": "Luyện Khí Tầng 9",
        "linh_thach": 35000,
        "herbs": 18,
        "tinh_luc": 15,
        "base_rate": 0.75,
        "hp_gain_flat": 2000,
        "hp_gain_pct": 0.10,
        "desc": "Cơ bắp dẻo dai như thép, khí huyết cuồn cuộn dâng trào."
    },
    4: {  # Luyện Nhục -> Luyện Cốt
        "to_realm": "Luyện Cốt",
        "req_realm_index": 9,      # Trúc Cơ Sơ Kỳ
        "req_realm_name": "Trúc Cơ Sơ Kỳ",
        "linh_thach": 80000,
        "herbs": 25,
        "tinh_luc": 20,
        "base_rate": 0.65,
        "hp_gain_flat": 3500,
        "hp_gain_pct": 0.12,
        "desc": "Xương cốt cứng cáp, bắt đầu kích hoạt giảm 15% Sát Thương nhận vào trong PVP."
    },
    5: {  # Luyện Cốt -> Luyện Tủy
        "to_realm": "Luyện Tủy",
        "req_realm_index": 13,     # Kim Đan Sơ Kỳ
        "req_realm_name": "Kim Đan Sơ Kỳ",
        "linh_thach": 180000,
        "herbs": 40,
        "tinh_luc": 25,
        "base_rate": 0.55,
        "hp_gain_flat": 6000,
        "hp_gain_pct": 0.15,
        "desc": "Tủy biến thành vàng óng, tái sinh huyết khí nhanh chóng."
    },
    6: {  # Luyện Tủy -> Luyện Huyết
        "to_realm": "Luyện Huyết",
        "req_realm_index": 17,     # Nguyên Anh Sơ Kỳ
        "req_realm_name": "Nguyên Anh Sơ Kỳ",
        "linh_thach": 400000,
        "herbs": 60,
        "tinh_luc": 30,
        "base_rate": 0.50,
        "hp_gain_flat": 10000,
        "hp_gain_pct": 0.18,
        "desc": "Máu hóa thành huyết tinh đậm đặc, sinh cơ vô cùng vô tận."
    },
    7: {  # Luyện Huyết -> Kim Thân
        "to_realm": "Kim Thân",
        "req_realm_index": 21,     # Hóa Thần Sơ Kỳ
        "req_realm_name": "Hóa Thần Sơ Kỳ",
        "linh_thach": 800000,
        "herbs": 90,
        "tinh_luc": 30,
        "base_rate": 0.45,
        "hp_gain_flat": 16000,
        "hp_gain_pct": 0.20,
        "desc": "Đúc thành Kim Thân Bất Hoại, vạn pháp bất xâm, lực áp quần hùng."
    },
    8: {  # Kim Thân -> Bất Diệt Thể
        "to_realm": "Bất Diệt Thể",
        "req_realm_index": 25,     # Luyện Hư
        "req_realm_name": "Luyện Hư",
        "linh_thach": 2000000,
        "herbs": 150,
        "tinh_luc": 35,
        "base_rate": 0.40,
        "hp_gain_flat": 25000,
        "hp_gain_pct": 0.25,
        "desc": "Nhục thân sánh ngang trời đất, Bất Diệt Thể cực hạn cảnh giới tối thượng!"
    }
}



# --- ĐẠO PHỨC HỢP (DAO DOMAINS) ---
DAO_FUSION_MATRIX: Dict[Tuple[str, str], Dict[str, str]] = {
    ("Kiếm Đạo", "Lôi Đạo"): {
        "name": "⚡⚔️ Lôi Kiếm Đạo",
        "effect": "Bỏ qua 30% Giáp, gây Bạo kích Lôi Tê Liệt."
    },
    ("Hỏa Đạo", "Sinh Mệnh Đạo"): {
        "name": "🔥💖 Niết Bàn Đạo",
        "effect": "Khi bị hạ gục, tự động hồi sinh với 30% HP (1 lần/trận)."
    },
    ("Tử Vong Đạo", "Thần Thức"): {
        "name": "💀🧠 U Hồn Đạo",
        "effect": "Triệu hồi linh hồn kẻ thù bị giết để chiến đấu cùng."
    },
    ("Không Gian", "Kiếm Đạo"): {
        "name": "🌌⚔️ Trảm Không Kiếm Đạo",
        "effect": "Đánh xuyên qua Trận Pháp Phòng Thủ Động Phủ."
    }
}


# --- 🔮 GACHA 3 ĐẠI BANNERS («THIÊN ĐỊA DUYÊN CƠ») ---

GACHA_BANNERS: Dict[str, Dict[str, Any]] = {
    "tubao": {
        "name": "1. TỤ BẢO CÁC (Banner Thường - F2P)",
        "currency": "Linh Thạch",
        "cost_1x": 25000,
        "ticket_item": "Linh Duyên Phù",
        "desc": "Quay đan dược phổ thông, nguyên liệu luyện đan, pháp bảo Hoàng/Huyền Cấp."
    },
    "tiencac": {
        "name": "2. CỬU THIÊN TIÊN CÁC (Premium Banner - P2W)",
        "currency": "Tiên Ngọc",
        "cost_1x": 50,
        "ticket_item": "Tiên Duyên Phù",
        "desc": "Quay Đế Cấp (UR 0.7%), Thiên Cấp (SR 4.3%), Thần Binh, Thần Thú Cưỡi Thượng Cổ."
    },
    "caimenh": {
        "name": "3. THÁI CỔ CẢI MỆNH ĐÀI (Special Banner)",
        "currency": "Tẩy Tủy Phù",
        "cost_1x": 1,
        "ticket_item": "Tẩy Tủy Phù",
        "desc": "Gacha quay lại Linh Căn Phẩm Cấp & Tiên Thể / Thánh Thể Thượng Cổ."
    }
}

# Gacha Pool Items per Banner

# 1. Pool Banner Thường (Tụ Bảo Các - F2P)
GACHA_ITEMS_TUBAO: List[Tuple[str, str, str, float]] = [
    # Thiên Cấp / SR (1.5%)
    ("🟡 [THIÊN CẤP] Công Pháp: 《Thái Hư Kiếm Điển》", "Công Pháp", "Thiên Cấp (SR)", 0.5),
    ("🟡 [THIÊN CẤP] Thần Binh: Thái Cổ Linh Thuẫn", "Pháp Bảo", "Thiên Cấp (SR)", 0.5),
    ("🟡 [THIÊN CẤP] Thần Thú: Huyết Lang Cổ Xưa", "Thú Cưỡi", "Thiên Cấp (SR)", 0.5),
    
    # Địa Cấp (11.0%)
    ("🟣 [ĐỊA CẤP] Đan Dược: Trúc Cơ Đan x1", "Đan Dược", "Địa Cấp", 10.0),
    ("🟣 [ĐỊA CẤP] Thần Phù: Tẩy Tủy Phù x1", "Thần Phù", "Địa Cấp", 1.0),
    
    # Huyền Cấp (35.0%)
    ("🔵 [HUYỀN CẤP] Khoáng Thạch: Thần Thiết Thô x5", "Nguyên Liệu", "Huyền Cấp", 20.0),
    ("🔵 [HUYỀN CẤP] Thảo Dược: Thảo Dược Thô x10", "Nguyên Liệu", "Huyền Cấp", 15.0),
    
    # Phàm Cấp (52.5%)
    ("🟢 [PHÀM CẤP] Thảo Dược: Thảo Dược Thô x3", "Nguyên Liệu", "Phàm Cấp", 28.5),
    ("🟢 [PHÀM CẤP] Khoáng Thạch: Thần Thiết Thô x2", "Nguyên Liệu", "Phàm Cấp", 24.0)
]

# 2. Pool Banner VIP (Cửu Thiên Tiên Các - Premium)
GACHA_ITEMS_PREMIUM: List[Tuple[str, str, str, float]] = [
    # Đế Cấp / UR (0.7%)
    ("🔴 [ĐẾ CẤP] Công Pháp: 《Thôn Thiên Ma Công》", "Công Pháp", "Đế Cấp (UR)", 0.2),
    ("🔴 [ĐẾ CẤP] Thần Binh: Trảm Tiên Kiếm", "Pháp Bảo", "Đế Cấp (UR)", 0.2),
    ("🔴 [ĐẾ CẤP] Thần Thú: Cửu Vĩ Thiên Hồ", "Thú Cưỡi", "Đế Cấp (UR)", 0.3),
    
    # Thiên Cấp / SR (4.3%)
    ("🟡 [THIÊN CẤP] Công Pháp: 《Thái Huyền Đạo Kinh》", "Công Pháp", "Thiên Cấp (SR)", 1.5),
    ("🟡 [THIÊN CẤP] Thần Binh: Bát Quái Cửu Đỉnh", "Pháp Bảo", "Thiên Cấp (SR)", 1.5),
    ("🟡 [THIÊN CẤP] Thần Thú: Bạch Hổ Thượng Cổ", "Thú Cưỡi", "Thiên Cấp (SR)", 1.3),
    
    # Địa Cấp (25.0%)
    ("🟣 [ĐỊA CẤP] Đan Dược: Niết Bàn Đan x2", "Đan Dược", "Địa Cấp", 10.0),
    ("🟣 [ĐỊA CẤP] Đan Dược: Cửu Chuyển Tái Tạo Đan x1", "Tiên Đan", "Địa Cấp", 5.0),
    ("🟣 [ĐỊA CẤP] Đan Dược: Trúc Cơ Đan x2", "Đan Dược", "Địa Cấp", 10.0),
    
    # Huyền Cấp (70.0%)
    ("🔵 [HUYỀN CẤP] Tài Bảo: 25,000 Linh Thạch", "Tài Bảo", "Huyền Cấp", 20.0),
    ("🔵 [HUYỀN CẤP] Tiên Bụi: 10x Linh Bụi Tiên Các", "Vật Phẩm", "Huyền Cấp", 50.0)
]

# Shop Linh Bụi Tiên Các (Shard Shop)
LINH_BUI_SHOP: Dict[str, Dict[str, Any]] = {
    "《Thôn Thiên Ma Công》": {"cost": 600, "type": "Công Pháp UR", "desc": "Công pháp Đế Cấp cựu thượng cổ."},
    "Trảm Tiên Kiếm": {"cost": 600, "type": "Pháp Bảo UR", "desc": "Thần binh Đế Cấp chém rách hư không."},
    "Cửu Vĩ Thiên Hồ": {"cost": 600, "type": "Thú Cưỡi UR", "desc": "Linh thú Thượng Cổ buff +50% EXP."},
    "Thần Phù Bảo Mệnh x5": {"cost": 100, "type": "Vật Phẩm", "desc": "Bảo hiểm Độ Kiếp chống rớt cảnh giới."}
}

# Tiên Các Shop Catalog (Nạp Tiền)
TIEN_CAC_SHOP: Dict[str, Dict[str, Any]] = {
    "Thần Phù Bảo Mệnh": {
        "price": 100,
        "desc": "Bảo hiểm Độ Kiếp. Giữ nguyên 100% Tu Vi & Căn Cơ khi đột phá thất bại.",
        "category": "Bảo Hiểm"
    },
    "Cửu Trùng Thiên Đan": {
        "price": 80,
        "desc": "Tăng trực tiếp +20% Tỷ lệ Độ Kiếp thành công.",
        "category": "Bảo Hiểm"
    },
    "Tái Tạo Đan": {
        "price": 150,
        "desc": "Khôi phục 100% Căn Cơ bị tổn hại hoặc tẩy Phẩm Cấp Kim Đan.",
        "category": "Bảo Hiểm"
    },
    "Thẻ Tháng Đạo Tâm Tôn Giả": {
        "price": 500,
        "desc": "Tự động Định Tâm 100% khi Bế Quan AFK, Mở rộng AFK lên 16h, +20% Tinh Lực, Khung Vàng Kim.",
        "category": "Đặc Quyền VIP"
    },
    "Tiên Mật Hồi Tinh Lực": {
        "price": 50,
        "desc": "Khôi phục ngay 100% Tinh Lực (Stamina) để tu luyện không giới hạn.",
        "category": "Tiện Ích"
    },
    "Trận Pháp Bất Xâm Phạm": {
        "price": 200,
        "desc": "Kích hoạt bùa bảo vệ Động Phủ 24h. Chặn 100% lệnh cướp phá từ tu sĩ khác.",
        "category": "An Toàn"
    },
    "Vạn Linh Đan": {
        "price": 50,
        "desc": "Đan dược cứu chữa đạo hữu bị Kinh Mạch Đoạn Tuyệt khi tử trận PVE (!cuu-thuong).",
        "category": "Cứu Thương PVE"
    },
    "Thánh Thể Phù": {
        "price": 80,
        "desc": "Phù bảo vệ. Chống rớt Linh Thạch và hại Căn Cơ khi tử trận trong Cấm Địa.",
        "category": "Bảo Hiểm PVE"
    },
    "Cửu Chuyển Tái Tạo Đan": {
        "price": 150,
        "desc": "Hồi sinh ngay lập tức tại chỗ với 100% HP và xóa sạch Độc Tố / Ô Nhiễm Tâm Ma.",
        "category": "Cứu Thương PVE"
    },
    "Thất Nhật Miễn Chiến Phù": {
        "price": 300,
        "desc": "Khóa tính năng bị PK dã ngoại và cướp phá Động Phủ an toàn trong 7 ngày (168 Giờ)!",
        "category": "Bảo Hiểm PVP"
    },
    "Gói Phục Hồi Cấp Tốc": {
        "price": 100,
        "desc": "Xóa sạch Chấn Thương Kinh Mạch ngay lập tức, hồi 100% HP và +20% Sát Thương Phục Thù trong 15 phút!",
        "category": "Cứu Thương PVP"
    }
}

# --- 🥋 PVP LUẬN ĐẠO ĐÀI & TÀNG KINH CÁC CONSTANTS ---

PVP_DAILY_FAME_CAP: int = 150              # Tối đa 150 Danh Vọng mỗi ngày từ Luận Đạo Đài
PVP_MAX_FAME_PER_OPPONENT: int = 2        # Tối đa 2 lần nhận Danh Vọng từ cùng 1 đối thủ mỗi ngày
PVP_COOLDOWN_SECONDS: int = 45             # Cooldown 45s giữa 2 trận PVP
PVP_MAX_REALM_GAP_FOR_FAME: int = 5        # Chênh lệch > 5 cảnh giới không nhận Danh Vọng

PVP_RANKS: List[Dict[str, Any]] = [
    {"tier": "Đế Cấp (Chí Cao)", "min_elo": 2000, "badge": "👑", "color": 0xFFD700, "win_danh_vong": 30, "loss_danh_vong": 0},
    {"tier": "Chí Tôn (Đỉnh Phong)", "min_elo": 1600, "badge": "💎", "color": 0x9B59B6, "win_danh_vong": 20, "loss_danh_vong": 0},
    {"tier": "Tiên Đạo (Thành Thục)", "min_elo": 1200, "badge": "⚔️", "color": 0x3498DB, "win_danh_vong": 15, "loss_danh_vong": 0},
    {"tier": "Sơ Nhập (Tân Thủ)", "min_elo": 0, "badge": "🥋", "color": 0x2ECC71, "win_danh_vong": 10, "loss_danh_vong": 0}
]

def get_pvp_rank(elo: int) -> Dict[str, Any]:
    for rank in PVP_RANKS:
        if elo >= rank["min_elo"]:
            return rank
    return PVP_RANKS[-1]

# Shop Tàng Kinh Các (Đổi Điểm Danh Vọng)
TANG_KINH_CAC_SHOP: Dict[str, Dict[str, Any]] = {
    "《Thái Hư Kiếm Điển》": {
        "cost": 1200,
        "type": "Công Pháp (Thiên Cấp)",
        "min_elo": 1200,
        "req_rank": "Tiên Đạo (ELO ≥ 1200)",
        "unique": True,
        "desc": "Bí kíp Kiếm Đạo tối thượng, tăng +25% Sát Thương Kiếm Đạo & +10% Bạo Kích PVP."
    },
    "《Bất Diệt Chân Kinh》": {
        "cost": 2500,
        "type": "Công Pháp Luyện Thể (Đế Cấp)",
        "min_elo": 1600,
        "req_rank": "Chí Tôn (ELO ≥ 1600)",
        "unique": True,
        "desc": "Công pháp rèn luyện Thần Thể, tăng +5,000 Max HP và giảm 15% Sát Thương PVP gánh chịu."
    },
    "Mảnh Thần Binh Thượng Cổ": {
        "cost": 450,
        "type": "Nguyên Liệu Hiếm",
        "min_elo": 0,
        "req_rank": "Tất Cả Tu Sĩ",
        "unique": False,
        "desc": "Tích lũy 3 mảnh để hợp thành Thần Khí Đế Cấp tự chọn."
    },
    "Định Thần Hoàn": {
        "cost": 120,
        "type": "Đan Dược Đặc Biệt",
        "min_elo": 0,
        "req_rank": "Tất Cả Tu Sĩ",
        "unique": False,
        "desc": "Tẩy trừ trạng thái Chấn Thương Kinh Mạch hoặc Tẩu Hỏa Nhập Ma tức thì."
    },
    "Bảo Rương Danh Vọng": {
        "cost": 200,
        "type": "Bảo Rương",
        "min_elo": 0,
        "req_rank": "Tất Cả Tu Sĩ",
        "unique": False,
        "desc": "Mở nhận ngẫu nhiên 10,000 - 50,000 Linh Thạch và 1-3 Vé Tiên Duyên Phù."
    }
}

# VIP Progression Matrix
VIP_LEVELS: Dict[int, Dict[str, Any]] = {
    0: {"req_exp": 0, "name": "F2P Tu Sĩ", "benefits": "Không có đặc quyền VIP."},
    1: {"req_exp": 100, "name": "VIP 1 - Sơ Cấp", "benefits": "Mở rộng Túi đồ +50 Slot, Thần Thức +10%."},
    2: {"req_exp": 300, "name": "VIP 2 - Trung Cấp", "benefits": "Tốc độ hồi Tinh Lực +15%."},
    3: {"req_exp": 600, "name": "VIP 3 - Thượng Cấp", "benefits": "Thêm +1 Slot Bí Thuật Công Pháp."},
    4: {"req_exp": 1000, "name": "VIP 4 - Chân Đạo", "benefits": "Tỷ lệ Đột Phá +5% vĩnh viễn."},
    5: {"req_exp": 2000, "name": "VIP 5 - Tôn Giả", "benefits": "Mở khóa lệnh !nhapdinh-nhanh (Nhận ngay 4h Tu vi)."},
    6: {"req_exp": 3500, "name": "VIP 6 - Tiên Vương", "benefits": "Tự động né 5% sát thương Lôi Kiếp."},
    7: {"req_exp": 5000, "name": "VIP 7 - Tiên Tôn", "benefits": "Tốc độ Bế Quan AFK +30%."},
    8: {"req_exp": 8000, "name": "VIP 8 - Đại Thiên Tôn", "benefits": "Tụ Linh Trận Động Phủ tự động tăng Cấp 10."},
    9: {"req_exp": 12000, "name": "VIP 9 - Thượng Cổ", "benefits": "Khung Thẻ Profile Cửu Long Phản Quang Vàng Kim."},
    10: {"req_exp": 20000, "name": "VIP 10 - Tiên Đế", "benefits": "Tự động né 10% sát thương Lôi Kiếp vĩnh viễn, Khung Tiên Đế Độc Quyền."}
}

