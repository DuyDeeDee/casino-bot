"""
Pydantic data models for Tu Tien: «ĐẠI ĐẠO TRANH PHONG» (Includes Gacha & Monetization Schema)
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class CultivatorProfile(BaseModel):
    user_id: int
    guild_id: int
    dao_hieu: str
    realm_index: int = 0
    realm_name: str = "Luyện Khí Tầng 1"
    exp: int = 0
    required_exp: int = 1000
    
    # Linh căn
    linh_can_quality: str = "Phàm Phẩm"
    linh_can_element: str = "🔥 Hỏa"
    is_di_linh_can: bool = False
    
    # Core statistics (18 properties)
    can_co: float = 80.0             # Căn Cơ (0-100%)
    tam_canh: float = 70.0           # Tâm Cảnh (0-100%)
    dao_tam: int = 10                # Đạo Tâm
    ngo_tinh: int = 10               # Ngộ Tính
    
    hp: int = 1000
    max_hp: int = 1000
    mana: int = 500
    max_mana: int = 500
    than_thuc: int = 50              # Thần Thức
    
    nghiep_luc: int = 0              # Nghiệp Lực
    co_duyen: int = 10               # Cơ Duyên
    thien_dao_diem: int = 0          # Thiên Đạo Điểm
    tinh_luc: int = 100              # Tinh Lực (Stamina 0-100)
    max_tinh_luc: int = 100
    
    # Body refining & Sect
    body_realm_index: int = 0
    body_realm_name: str = "Phàm Thân"
    dong_phu_level: int = 1
    sect_id: Optional[int] = None
    sect_name: Optional[str] = None
    sect_role: Optional[str] = None
    
    # Currencies (Two-Currency System)
    linh_thach: int = 500            # In-game Currency
    tien_ngoc: int = 0              # Premium Currency (Nạp Tiền)
    
    # Gacha Currency & Tickets
    linh_duyen_phu: int = 0          # Vé quay Banner Thường
    tien_duyen_phu: int = 0          # Vé quay Banner Premium
    tay_tuy_phu: int = 0            # Vé quay Banner Cải Mệnh Đài
    linh_bui: int = 0               # Điểm Linh Bụi Tiên Các (Shard Shop)
    soft_pity_count: int = 0        # Đếm lượt Pity UR (Soft at 60, Hard at 80)
    wishlist_item: Optional[str] = None # Định Hướng Đạo Vận
    last_daily_fortune: Optional[float] = None # Timestamp điểm danh !xienquach
    
    # VIP & Monetization Schema
    vip_level: int = 0               # VIP 0 -> VIP 10
    vip_exp: int = 0                 # Tích Nạp VIP
    is_vip_pass: bool = False        # Thẻ Tháng Đạo Tâm Tôn Giả
    vip_pass_expires: Optional[float] = None
    array_protection_until: Optional[float] = None # Trận Pháp Bất Xâm Phạm chống !cuop
    gacha_pity_count: int = 0        # Đếm lượt Pity Gacha
    
    # AFK & Debuff status
    is_meditating: bool = False
    meditate_start_time: Optional[float] = None
    meditate_duration_hours: int = 0
    tau_hoa_nhap_ma_until: Optional[float] = None
    
    # Hardcore PVE & Rescue schema
    kinh_mach_doan_tuyet_until: Optional[float] = None
    lingering_debuff: Optional[str] = None
    thanh_the_phu: int = 0
    van_linh_dan: int = 0
    cuu_chuyen_dan: int = 0

    # Dao Domain points
    dao_luan_points: Dict[str, int] = Field(default_factory=dict)
    active_dao_domain: Optional[str] = None


class GongfaEquipment(BaseModel):
    user_id: int
    chu_tu: Optional[str] = "《Phàm Nhân Quyết》"
    tam_phap: Optional[str] = None
    luyen_the: Optional[str] = None
    than_phap: Optional[str] = None
    bi_thuat: List[str] = Field(default_factory=list)


class SectModel(BaseModel):
    sect_id: int
    name: str
    leader_id: int
    treasury_linh_thach: int = 0
    level: int = 1
    occupied_channel_id: Optional[int] = None


class ChannelLinhKhiModel(BaseModel):
    channel_id: int
    current_linh_khi: int = 100000
    max_linh_khi: int = 100000
