# coding: utf-8
"""
Ma Sói (Werewolf) Game Engine Module
Quản lý logic, state machine, vai trò, phiếu bầu, replay log và tính điểm rank.
"""

from __future__ import annotations

import random
import time
from enum import Enum
from typing import Dict, List, Optional, Set, Tuple


class Role(Enum):
    WOLF = "Sói Thường"
    VILLAGER = "Dân Thường"
    SEER = "Tiên Tri"
    GUARD = "Bảo Vệ"
    WITCH = "Phù Thủy"
    CUPID = "Thần Tình Yêu"
    HUNTER = "Thợ Săn"
    TANNER = "Kẻ Ngốc"
    MAYOR = "Thị Trưởng"
    WOLF_SEER = "Sói Tiên Tri"
    CURSED = "Kẻ Bị Nguyền"
    ELDER = "Già Làng"
    SERIAL_KILLER = "Sát Thủ"
    WOLF_CUB = "Sói Cuồng Sát"
    HARLOT = "Vũ Nữ"
    APPRENTICE_SEER = "Tiên Tri Tập Sự"
    LYCAN = "Bán Nguyệt"
    INVESTIGATOR = "Thám Tử"
    WHITE_WOLF = "Sói Trắng"
    PHANTOM_WOLF = "Sói Ảo Ảnh"
    MUTE_WOLF = "Sói Câm"
    THE_GIRL = "Cô Bé"
    RUSTY_KNIGHT = "Hiệp Sĩ Kiếm Gỉ"
    PIPER = "Người Thổi Sáo"
    SCAPEGOAT = "Dê Tế Thần"
    ALPHA_WOLF = "Chúa Tể Sói"

    @property
    def emoji(self) -> str:
        emojis = {
            Role.WOLF: "🐺",
            Role.VILLAGER: "👤",
            Role.SEER: "🔮",
            Role.GUARD: "🛡️",
            Role.WITCH: "🧪",
            Role.CUPID: "💘",
            Role.HUNTER: "🏹",
            Role.TANNER: "🃏",
            Role.MAYOR: "🎩",
            Role.WOLF_SEER: "🐺🔮",
            Role.CURSED: "🌕",
            Role.ELDER: "👴",
            Role.SERIAL_KILLER: "🔪",
            Role.WOLF_CUB: "🐺🩸",
            Role.HARLOT: "💃",
            Role.APPRENTICE_SEER: "🔮✨",
            Role.LYCAN: "🐺👤",
            Role.INVESTIGATOR: "👁️",
            Role.WHITE_WOLF: "🐺⭐",
            Role.PHANTOM_WOLF: "🐺👻",
            Role.MUTE_WOLF: "🔇🐺",
            Role.THE_GIRL: "👧",
            Role.RUSTY_KNIGHT: "⚔️",
            Role.PIPER: "🎵",
            Role.SCAPEGOAT: "🐐",
            Role.ALPHA_WOLF: "👑🐺",
        }
        return emojis.get(self, "❓")

    @property
    def faction(self) -> Faction:
        if self in (Role.WOLF, Role.WOLF_SEER, Role.WOLF_CUB, Role.WHITE_WOLF, Role.PHANTOM_WOLF, Role.MUTE_WOLF, Role.ALPHA_WOLF):
            return Faction.WEREWOLF
        elif self == Role.TANNER:
            return Faction.INDEPENDENT
        elif self == Role.SERIAL_KILLER:
            return Faction.SERIAL_KILLER
        elif self == Role.PIPER:
            return Faction.PIPER
        else:
            return Faction.VILLAGER

    @property
    def description(self) -> str:
        descriptions = {
            Role.WOLF: "Mỗi đêm cùng bầy Sói bỏ phiếu cắn 1 người. Đừng để lộ thân phận ban ngày!",
            Role.VILLAGER: "Không có kỹ năng đêm. Hãy dùng trí tuệ và tranh luận để tìm ra bầy Sói!",
            Role.SEER: "Mỗi đêm chọn 1 người để soi phe (Sói hay Dân).",
            Role.GUARD: "Mỗi đêm chọn 1 người để bảo vệ khỏi bị Sói cắn (không chọn trùng 2 đêm liền).",
            Role.WITCH: "Có 1 bình Cứu (hồi sinh người bị cắn) và 1 bình Độc (giết 1 người), mỗi bình dùng 1 lần/ván.",
            Role.CUPID: "Đêm 1 chọn 2 người làm Cặp Đôi Tình Nhân. Nếu 1 trong 2 người chết, người kia sẽ chết theo.",
            Role.HUNTER: "Khi bị loại (bị Sói cắn hoặc bị treo cổ), bạn được chọn 1 người chơi để kéo theo cùng.",
            Role.TANNER: "Bạn thuộc phe Độc Lập. Bạn THẮNG NGAY LẬP TỨC nếu bị dân làng treo cổ ban ngày!",
            Role.MAYOR: "Phiếu bầu ban ngày tính x2. Khi qua đời, bạn được chỉ định 1 người kế nhiệm làm Thị Trưởng mới!",
            Role.WOLF_SEER: "Mỗi đêm cùng bầy Sói cắn người và được soi 1 người để biết chính xác vai trò của họ!",
            Role.CURSED: "Ban đầu là Dân. Nếu bị Sói cắn ban đêm, bạn không chết mà biến thành Sói từ đêm sau!",
            Role.ELDER: "Có 2 mạng trước đòn cắn của Sói (lần 1 bị cắn không chết). Tuy nhiên bị treo cổ/độc sẽ chết ngay!",
            Role.SERIAL_KILLER: "Thuộc phe Độc Lập. Mỗi đêm giết 1 người, miễn nhiễm đòn cắn của Sói. Thắng khi sống sót duy nhất!",
            Role.WOLF_CUB: "Khi bị loại (bị cắn hoặc treo cổ), bầy Sói sẽ phẫn nộ và được cắn liền 2 người ở đêm tiếp theo!",
            Role.HARLOT: "Mỗi đêm chọn 1 người để 'thăm' (phong tỏa). Người đó sẽ bị chặn toàn bộ kỹ năng đêm!",
            Role.APPRENTICE_SEER: "Ban đầu chưa có kỹ năng. Khi Tiên Tri chính qua đời, bạn sẽ kế thừa làm Tiên Tri mới từ đêm tiếp theo!",
            Role.LYCAN: "Thuộc Phe Dân và thắng cùng Dân. Tuy nhiên nếu Tiên Tri soi vào bạn, kết quả trả về sẽ là 'SÓI'!",
            Role.INVESTIGATOR: "Mỗi đêm chọn 2 người chơi để kiểm tra xem trong 2 người đó có ít nhất 1 Sói hay không.",
            Role.WHITE_WOLF: "Thuộc Phe Sói. Mỗi 2 đêm chẵn được bí mật cắn thêm 1 con Sói khác trong bầy. Thắng một mình nếu là sinh vật cuối cùng còn sống!",
            Role.PHANTOM_WOLF: "Mỗi đêm chọn 1 người dân để 'giả dạng'. Nếu Tiên Tri soi người đó trong đêm đó, kết quả trả về là 'SÓI'.",
            Role.MUTE_WOLF: "Thuộc Phe Sói. Ban ngày không được phép chat, chỉ được bỏ phiếu — tạo áp lực tâm lý và nghi ngờ cho dân làng!",
            Role.THE_GIRL: "Mỗi đêm có thể 'nhìn trộm' để xem bầy Sói đang cắn ai. Nhưng nếu bị phát hiện (50% cơ hội) — chết ngay đêm đó!",
            Role.RUSTY_KNIGHT: "Nếu bị Sói cắn chết, đêm kế tiếp 1 con Sói ngẫu nhiên sẽ bị 'lời nguyền' hạ gục. Cái chết có giá trị!",
            Role.PIPER: "Phe Độc Lập. Mỗi đêm mê hoặc 2 người. Thắng khi toàn bộ người chơi còn sống (kể cả Sói) đều đã bị mê hoặc!",
            Role.SCAPEGOAT: "Nếu bỏ phiếu ban ngày bị hòa (tie vote), Dê Tế Thần tự động bị treo cổ thay thế. Không công bằng — đó là số phận!",
            Role.ALPHA_WOLF: "Trùm Cuối ván đấu Raid Boss! Sở hữu 3 Mạng Vương Giả, kháng 1 Bình Độc, phiếu bầu ban ngày tính x3 và cắn 2 người/đêm!",
        }
        return descriptions.get(self, "")


class Faction(Enum):
    WEREWOLF = "Phe Sói 🐺"
    VILLAGER = "Phe Dân Làng 👥"
    INDEPENDENT = "Phe Độc Lập 🃏"
    LOVERS = "Phe Tình Nhân 💘"
    SERIAL_KILLER = "Phe Sát Thủ 🔪"
    PIPER = "Phe Người Thổi Sáo 🎵"


class GamePhase(Enum):
    LOBBY = "Đang chờ người chơi"
    ROLE_ASSIGN = "Đang chia vai trò"
    NIGHT_GUARD = "Đêm — Lượt Bảo Vệ"
    NIGHT_WOLF = "Đêm — Lượt Sói"
    NIGHT_SEER = "Đêm — Lượt Tiên Tri"
    NIGHT_WITCH = "Đêm — Lượt Phù Thủy"
    NIGHT_RESOLVE = "Xử lý kết quả đêm"
    DAY_ANNOUNCE = "Công bố kết quả đêm"
    DAY_DISCUSSION = "Ban ngày — Thảo luận"
    DAY_VOTE = "Ban ngày — Bỏ phiếu treo cổ"
    DAY_RESOLVE = "Xử lý kết quả bỏ phiếu"
    CHECK_WIN = "Kiểm tra kết quả ván"
    GAME_END = "Kết thúc ván đấu"


class NightEvent(Enum):
    BLOOD_MOON = "Trăng Máu 🩸"
    DENSE_FOG = "Sương Mù Dày Đặc 🌫️"
    SOLAR_ECLIPSE = "Nhật Thực ☀️"
    SEAL_NIGHT = "Phong Ấn Dược Liệu 🧪"
    HOLY_LIGHT = "Thánh Quang Bảo Hộ 🛡️"
    THUNDERSTORM = "Bão Sấm Sét 🌩️"
    WANING_MOON = "Trăng Khuyết 🌘"
    SILENT_NIGHT = "Đêm Câm Lặng 🔇"

    @property
    def title(self) -> str:
        names = {
            NightEvent.BLOOD_MOON: "🩸 TRĂNG MÁU (BLOOD MOON)",
            NightEvent.DENSE_FOG: "🌫️ SƯƠNG MÙ DÀY ĐẶC (DENSE FOG)",
            NightEvent.SOLAR_ECLIPSE: "☀️ NHẬT THỰC BÓNG TỐI (SOLAR ECLIPSE)",
            NightEvent.SEAL_NIGHT: "🧪 PHONG ẤN DƯỢC LIỆU (SEALED POTIONS)",
            NightEvent.HOLY_LIGHT: "🛡️ THÁNH QUANG BẢO HỘ (HOLY LIGHT)",
            NightEvent.THUNDERSTORM: "🌩️ BÃO SẤM SÉT (THUNDERSTORM)",
            NightEvent.WANING_MOON: "🌘 TRĂNG KHUYẾT SUY YẾU (WANING MOON)",
            NightEvent.SILENT_NIGHT: "🔇 ĐÊM CÂM LẶNG (SILENT NIGHT)",
        }
        return names.get(self, self.value)

    @property
    def description(self) -> str:
        descs = {
            NightEvent.BLOOD_MOON: "Sức mạnh bầy Sói bùng nổ! Đêm nay Bầy Sói được cắn liền **2 người**!",
            NightEvent.DENSE_FOG: "Tầm nhìn bị che khuất! Kết quả bói toán soi phe đêm nay có **50% tỷ lệ bị nhiễu sai lệch**!",
            NightEvent.SOLAR_ECLIPSE: "Bóng tối bao trùm ban ngày! Ban ngày tiếp theo **không thể bỏ phiếu treo cổ**!",
            NightEvent.SEAL_NIGHT: "Ma thuật bị phong ấn! Phù Thủy **không thể dùng Bình Cứu hay Bình Độc** đêm nay!",
            NightEvent.HOLY_LIGHT: "Hào quang thánh bảo vệ ngôi làng! Đêm nay tất cả mọi người được **kháng đòn cắn** của Bầy Sói!",
            NightEvent.THUNDERSTORM: "Tiếng sấm át tiếng bước chân! Cô Bé đêm nay nhìn trộm **an toàn 100% không bị phát hiện**!",
            NightEvent.WANING_MOON: "Bầy Sói bị suy yếu! Sói Trắng **không thể cắn đồng bọn** đêm nay!",
            NightEvent.SILENT_NIGHT: "Thời gian thảo luận ngày tiếp theo bị rút ngắn xuống còn **30 giây**!",
        }
        return descs.get(self, "")


class MasoiSettings:
    """Cấu hình ván Ma Sói có thể chỉnh ở Lobby."""
    def __init__(self):
        self.reveal_roles_on_death: bool = False  # False: Ẩn tới cuối ván (Mặc định) / True: Hiện ngay
        self.enable_tanner: bool = False  # Bật/Tắt Kẻ Phản Bội
        self.vote_display: str = "REALTIME"  # REALTIME / END_ONLY
        self.dead_can_chat: bool = False  # False: Bị cấm chat / True: Được chat
        self.discussion_time: int = 120  # 120 giây (2 phút)
        self.night_time: int = 60  # 60 giây (1 phút)
        self.enable_rank: bool = True  # Có/Không tính rank
        self.enable_events: bool = False  # Bật/Tắt Chế độ Thẻ Sự Kiện Đêm
        self.enable_boss_mode: bool = False  # Bật/Tắt Chế độ Trùm Cuối (Raid Boss)
        self.role_setup_mode: str = "AUTO"  # AUTO / CUSTOM
        self.custom_wolf_count: int = 2
        self.custom_special_roles: List[str] = []

    def cycle_reveal_roles(self):
        self.reveal_roles_on_death = not self.reveal_roles_on_death

    def cycle_tanner(self):
        self.enable_tanner = not self.enable_tanner

    def cycle_vote_display(self):
        self.vote_display = "END_ONLY" if self.vote_display == "REALTIME" else "REALTIME"

    def cycle_dead_chat(self):
        self.dead_can_chat = not self.dead_can_chat

    def cycle_discussion_time(self):
        times = [60, 120, 180, 300]
        idx = times.index(self.discussion_time) if self.discussion_time in times else 1
        self.discussion_time = times[(idx + 1) % len(times)]

    def cycle_night_time(self):
        times = [30, 45, 60]
        idx = times.index(self.night_time) if self.night_time in times else 2
        self.night_time = times[(idx + 1) % len(times)]

    def cycle_rank(self):
        self.enable_rank = not self.enable_rank

    def cycle_events(self):
        self.enable_events = not self.enable_events

    def cycle_boss_mode(self):
        self.enable_boss_mode = not self.enable_boss_mode

    def to_dict(self) -> dict:
        return {
            "reveal_roles_on_death": self.reveal_roles_on_death,
            "enable_tanner": self.enable_tanner,
            "vote_display": self.vote_display,
            "dead_can_chat": self.dead_can_chat,
            "discussion_time": self.discussion_time,
            "night_time": self.night_time,
            "enable_rank": self.enable_rank,
            "enable_events": self.enable_events,
            "enable_boss_mode": self.enable_boss_mode,
            "role_setup_mode": self.role_setup_mode,
            "custom_wolf_count": self.custom_wolf_count,
            "custom_special_roles": self.custom_special_roles,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MasoiSettings:
        s = cls()
        s.reveal_roles_on_death = data.get("reveal_roles_on_death", False)
        s.enable_tanner = data.get("enable_tanner", False)
        s.vote_display = data.get("vote_display", "REALTIME")
        s.dead_can_chat = data.get("dead_can_chat", False)
        s.discussion_time = data.get("discussion_time", 120)
        s.night_time = data.get("night_time", 60)
        s.enable_rank = data.get("enable_rank", True)
        s.enable_events = data.get("enable_events", False)
        s.enable_boss_mode = data.get("enable_boss_mode", False)
        s.role_setup_mode = data.get("role_setup_mode", "AUTO")
        s.custom_wolf_count = data.get("custom_wolf_count", 2)
        s.custom_special_roles = data.get("custom_special_roles", [])
        return s

    def copy(self) -> MasoiSettings:
        return MasoiSettings.from_dict(self.to_dict())


class MasoiPlayer:
    """Thông tin người chơi trong ván."""
    def __init__(self, user_id: int, display_name: str):
        self.user_id: int = user_id
        self.display_name: str = display_name
        self.role: Role = Role.VILLAGER
        self.is_alive: bool = True
        
        # Trạng thái kỹ năng
        self.witch_save_used: bool = False
        self.witch_poison_used: bool = False
        self.protected_last_night: Optional[int] = None  # user_id người được bảo vệ đêm trước
        self.lover_id: Optional[int] = None  # user_id tình nhân (Thần tình yêu ghép đôi)
        self.hunter_shot_used: bool = False  # Thợ săn đã dùng phát bắn kéo theo chưa
        self.is_cursed_converted: bool = False  # Kẻ Bị Nguyền đã biến thành Sói chưa
        self.cursed_notified: bool = False  # Đã gửi DM thông báo biến thành Sói chưa
        self.elder_lives: int = 2  # Già Làng có 2 mạng trước đòn cắn của Sói
        self.is_roleblocked: bool = False  # Bị Vũ Nữ phong tỏa kỹ năng đêm
        self.apprentice_promoted: bool = False  # Tiên Tri Tập Sự đã kế thừa vị trí Tiên Tri
        self.rusty_knight_curse_triggered: bool = False  # Hiệp Sĩ đã kích hoạt nguyền chưa
        self.piper_charmed: bool = False  # Bị Người Thổi Sáo mê hoặc
        self.boss_lives: int = 3  # HP Mạng sống của Chúa Tể Sói (Trùm Cuối)
        self.boss_poison_shield: bool = True  # Khiên kháng 1 lần Bình Độc Phù Thủy của Trùm

        # Metrics cho rank bonus
        self.seer_found_wolf: bool = False
        self.guard_saved_count: int = 0
        self.witch_useful_use_count: int = 0

    @property
    def is_wolf(self) -> bool:
        return self.role in (Role.WOLF, Role.WOLF_SEER, Role.WOLF_CUB, Role.WHITE_WOLF, Role.PHANTOM_WOLF, Role.MUTE_WOLF, Role.ALPHA_WOLF) or self.is_cursed_converted


class ReplayLog:
    """Một mục sự kiện replay."""
    def __init__(
        self,
        day: int,
        phase: str,
        event_type: str,
        actor_id: Optional[int] = None,
        actor_name: Optional[str] = None,
        target_id: Optional[int] = None,
        target_name: Optional[str] = None,
        result: str = "",
    ):
        self.day: int = day
        self.phase: str = phase
        self.event_type: str = event_type
        self.actor_id: Optional[int] = actor_id
        self.actor_name: Optional[str] = actor_name
        self.target_id: Optional[int] = target_id
        self.target_name: Optional[str] = target_name
        self.result: str = result
        self.timestamp: float = time.time()


def get_rank_tier(points: int) -> Tuple[str, str]:
    """Trả về (Icon, Tên Tier) dựa trên điểm rank."""
    if points >= 700:
        return "💎", "Kim Cương"
    elif points >= 300:
        return "🥇", "Vàng"
    elif points >= 100:
        return "🥈", "Bạc"
    else:
        return "🥉", "Đồng"


class MasoiGame:
    """State Machine chính quản lý ván chơi Ma Sói."""
    def __init__(self, guild_id: int, channel_id: int, host_id: int, host_name: str):
        self.guild_id: int = guild_id
        self.channel_id: int = channel_id
        self.host_id: int = host_id
        self.host_name: str = host_name
        self.thread_id: Optional[int] = None
        self.message_id: Optional[int] = None

        self.phase: GamePhase = GamePhase.LOBBY
        self.settings: MasoiSettings = MasoiSettings()
        self.players: Dict[int, MasoiPlayer] = {}
        self.join_order: List[int] = []

        self.night_count: int = 0
        self.day_count: int = 0
        self.start_time: float = time.time()
        self.end_time: Optional[float] = None

        # Dữ liệu tạm trong đêm
        self.night_guard_target: Optional[int] = None
        self.night_wolf_votes: Dict[int, int] = {}  # wolf_id -> target_id
        self.night_seer_target: Optional[int] = None
        self.night_seer_result: Optional[str] = None
        self.night_wolf_seer_target: Optional[int] = None
        self.night_wolf_seer_result: Optional[str] = None
        self.night_serial_killer_target: Optional[int] = None
        self.night_witch_save: Optional[bool] = None
        self.night_witch_poison: Optional[int] = None
        self.night_harlot_target: Optional[int] = None
        self.night_investigator_targets: Optional[Tuple[int, int]] = None
        self.night_investigator_result: Optional[str] = None
        self.night_white_wolf_target: Optional[int] = None  # Sói Trắng cắn thêm 1 Sói (mỗi 2 đêm chẵn)
        self.night_phantom_wolf_target: Optional[int] = None  # Sói Ảo Ảnh giả dạng người dân
        self.night_piper_targets: List[int] = []  # Người Thổi Sáo mê hoặc 2 người
        self.piper_charmed_players: Set[int] = set()  # Tất cả người đã bị mê hoặc qua các đêm
        self.girl_caught: bool = False  # Cô Bé bị Sói bắt gặp đêm nay
        self.girl_peeking_user_id: Optional[int] = None  # Cô Bé chọn nhìn trộm đêm nay
        self.girl_dm_message: Optional[any] = None
        self.seer_dm_message: Optional[any] = None
        self.rusty_knight_curse_pending: bool = False  # Nguyền Hiệp Sĩ chờ kích hoạt đêm sau
        self.rusty_knight_curse_active: bool = False  # Nguyền Hiệp Sĩ đang kích hoạt đêm này
        self.wolf_fury_pending: bool = False
        self.wolf_fury_active: bool = False
        self.witch_dm_message: Optional[any] = None
        self.witch_view: Optional[any] = None
        self.mayor_id: Optional[int] = None
        self.current_night_event: Optional[NightEvent] = None  # Thẻ sự kiện đêm hiện tại

        # Dữ liệu ban ngày
        self.day_votes: Dict[int, Optional[int]] = {}  # voter_id -> target_id (None = White vote)
        self.early_vote_requests: Set[int] = set()  # set user_id đã xin bỏ phiếu sớm

        # Logs & Results
        self.replay_logs: List[ReplayLog] = []
        self.night_deaths: List[int] = []
        self.executed_player_id: Optional[int] = None
        self.winner_faction: Optional[Faction] = None
        self.tanner_winner_id: Optional[int] = None

    def add_player(self, user_id: int, display_name: str) -> bool:
        if self.phase != GamePhase.LOBBY:
            return False
        if user_id in self.players:
            return False
        if len(self.players) >= 20:
            return False
        self.players[user_id] = MasoiPlayer(user_id, display_name)
        self.join_order.append(user_id)
        return True

    def remove_player(self, user_id: int) -> bool:
        if self.phase != GamePhase.LOBBY:
            return False
        if user_id not in self.players:
            return False
        del self.players[user_id]
        if user_id in self.join_order:
            self.join_order.remove(user_id)
        return True

    def get_alive_players(self) -> List[MasoiPlayer]:
        return [p for p in self.players.values() if p.is_alive]

    def get_alive_wolves(self) -> List[MasoiPlayer]:
        return [p for p in self.players.values() if p.is_alive and p.is_wolf]

    def get_player_by_role(self, role: Role) -> Optional[MasoiPlayer]:
        for p in self.players.values():
            if p.role == role and p.is_alive:
                return p
        return None

    def assign_roles(self):
        """Phân chia vai trò ngẫu nhiên cho người chơi."""
        user_ids = list(self.players.keys())
        random.shuffle(user_ids)
        n = len(user_ids)

        if self.settings.enable_boss_mode:
            boss_idx = random.randint(0, n - 1)
            boss_uid = user_ids[boss_idx]
            raid_roles = [Role.SEER, Role.GUARD, Role.WITCH, Role.HUNTER, Role.ELDER, Role.RUSTY_KNIGHT, Role.INVESTIGATOR, Role.APPRENTICE_SEER]
            random.shuffle(raid_roles)

            for uid in user_ids:
                if uid == boss_uid:
                    self.players[uid].role = Role.ALPHA_WOLF
                    self.players[uid].boss_lives = 3
                else:
                    role = raid_roles.pop(0) if raid_roles else Role.VILLAGER
                    self.players[uid].role = role
            return

        if self.settings.role_setup_mode == "CUSTOM":
            role_pool: List[Role] = [Role.WOLF] * max(1, self.settings.custom_wolf_count)
            for role_name in self.settings.custom_special_roles:
                try:
                    r = Role[role_name]
                    if len(role_pool) < n:
                        role_pool.append(r)
                except KeyError:
                    pass
        else:
            if n <= 6:
                role_pool = [Role.WOLF, Role.SEER, Role.GUARD, Role.MAYOR]
            elif n <= 9:
                role_pool = [Role.WOLF, Role.WOLF, Role.SEER, Role.GUARD, Role.WITCH, Role.MAYOR, Role.CURSED]
            elif n <= 12:
                role_pool = [Role.WOLF, Role.WOLF_SEER, Role.MAYOR, Role.SEER, Role.GUARD, Role.WITCH, Role.HUNTER, Role.CURSED, Role.ELDER]
                if n >= 12:
                    role_pool.append(Role.WOLF)
            else:
                role_pool = [Role.WOLF, Role.WOLF, Role.WOLF_SEER, Role.MAYOR, Role.SEER, Role.GUARD, Role.WITCH, Role.HUNTER, Role.CURSED, Role.ELDER, Role.SERIAL_KILLER]
                if n >= 15:
                    role_pool.append(Role.WOLF)

            if self.settings.enable_tanner and Role.TANNER not in role_pool and len(role_pool) < n:
                role_pool.append(Role.TANNER)

        while len(role_pool) < n:
            role_pool.append(Role.VILLAGER)

        role_pool = role_pool[:n]
        random.shuffle(role_pool)

        for uid, role in zip(user_ids, role_pool):
            self.players[uid].role = role
            if role == Role.MAYOR:
                self.mayor_id = uid

    def preview_roles(self) -> List[Role]:
        """Xem trước các vai trò xuất hiện theo số lượng người chơi hiện tại."""
        n = max(5, len(self.players))
        if self.settings.enable_boss_mode:
            role_pool = [Role.ALPHA_WOLF, Role.SEER, Role.GUARD, Role.WITCH, Role.HUNTER, Role.ELDER, Role.RUSTY_KNIGHT, Role.INVESTIGATOR]
            while len(role_pool) < n:
                role_pool.append(Role.VILLAGER)
            return role_pool[:n]

        if self.settings.role_setup_mode == "CUSTOM":
            role_pool: List[Role] = [Role.WOLF] * max(1, self.settings.custom_wolf_count)
            for role_name in self.settings.custom_special_roles:
                try:
                    r = Role[role_name]
                    if len(role_pool) < n:
                        role_pool.append(r)
                except KeyError:
                    pass
        else:
            if n <= 6:
                role_pool = [Role.WOLF, Role.SEER, Role.GUARD, Role.MAYOR]
            elif n <= 9:
                role_pool = [Role.WOLF, Role.WOLF, Role.SEER, Role.GUARD, Role.WITCH, Role.MAYOR, Role.CURSED]
            elif n <= 12:
                role_pool = [Role.WOLF, Role.WOLF_SEER, Role.MAYOR, Role.SEER, Role.GUARD, Role.WITCH, Role.HUNTER, Role.CURSED, Role.ELDER]
                if n >= 12:
                    role_pool.append(Role.WOLF)
            else:
                role_pool = [Role.WOLF, Role.WOLF, Role.WOLF_SEER, Role.MAYOR, Role.SEER, Role.GUARD, Role.WITCH, Role.HUNTER, Role.CURSED, Role.ELDER, Role.SERIAL_KILLER]
                if n >= 15:
                    role_pool.append(Role.WOLF)

            if self.settings.enable_tanner and Role.TANNER not in role_pool and len(role_pool) < n:
                role_pool.append(Role.TANNER)

        while len(role_pool) < n:
            role_pool.append(Role.VILLAGER)

        return role_pool[:n]

    def start_night(self):
        """Reset dữ liệu chuẩn bị vào Đêm mới."""
        self.night_count += 1
        for p in self.players.values():
            p.is_roleblocked = False
        self.night_guard_target = None
        self.night_wolf_votes.clear()
        self.night_seer_target = None
        self.night_seer_result = None
        self.night_wolf_seer_target = None
        self.night_wolf_seer_result = None
        self.night_serial_killer_target = None
        self.night_witch_save = None
        self.night_witch_poison = None
        self.night_harlot_target = None
        self.night_investigator_targets = None
        self.night_investigator_result = None
        self.witch_dm_message = None
        self.witch_view = None

        # Thẻ sự kiện đêm
        self.current_night_event = None
        if self.settings.enable_events:
            self.current_night_event = random.choice(list(NightEvent))
            self.record_log("NIGHT_EVENT", result=f"Thẻ Sự Kiện: {self.current_night_event.title}")

        if self.settings.enable_boss_mode:
            self.wolf_fury_active = True
        elif self.current_night_event == NightEvent.BLOOD_MOON:
            self.wolf_fury_active = True
        elif self.wolf_fury_pending:
            self.wolf_fury_active = True
            self.wolf_fury_pending = False
        else:
            self.wolf_fury_active = False

        # Hiệp Sĩ Kiếm Gỉ: nguyền kích hoạt đêm sau (tương tự wolf_fury)
        if self.rusty_knight_curse_pending:
            self.rusty_knight_curse_active = True
            self.rusty_knight_curse_pending = False
        else:
            self.rusty_knight_curse_active = False

        # Reset trạng thái đêm cho các vai trò mới
        self.night_white_wolf_target = None
        self.night_phantom_wolf_target = None
        self.night_piper_targets = []
        self.girl_caught = False
        self.girl_peeking_user_id = None
        self.girl_dm_message = None
        self.seer_dm_message = None

    def record_log(
        self,
        event_type: str,
        actor_id: Optional[int] = None,
        target_id: Optional[int] = None,
        result: str = "",
    ):
        actor_name = self.players[actor_id].display_name if actor_id and actor_id in self.players else None
        target_name = self.players[target_id].display_name if target_id and target_id in self.players else None
        log = ReplayLog(
            day=self.day_count,
            phase=self.phase.value,
            event_type=event_type,
            actor_id=actor_id,
            actor_name=actor_name,
            target_id=target_id,
            target_name=target_name,
            result=result,
        )
        self.replay_logs.append(log)

    def resolve_wolf_targets(self) -> List[int]:
        """Tính phiếu cắn của bầy Sói (1 hoặc 2 mục tiêu nếu wolf_fury_active).
        Bỏ qua phiếu của Sói bị Vũ Nữ phong tỏa (is_roleblocked).
        """
        if not self.night_wolf_votes:
            return []
        counts: Dict[int, int] = {}
        for wolf_id, target in self.night_wolf_votes.items():
            wolf_p = self.players.get(wolf_id)
            if wolf_p and wolf_p.is_roleblocked:
                # Sói bị Vũ Nữ phong tỏa -> phiếu không có hiệu lực
                self.record_log("WOLF_ROLEBLOCKED", actor_id=wolf_id, result="Sói bị Vũ Nữ phong tỏa, không thể cắn đêm nay")
                continue
            counts[target] = counts.get(target, 0) + 1
        sorted_targets = sorted(counts.items(), key=lambda x: x[1], reverse=True)
        if not sorted_targets:
            return []
        if self.wolf_fury_active:
            if len(sorted_targets) >= 2:
                # Hai mục tiêu khác nhau -> cắn cả 2
                return [sorted_targets[0][0], sorted_targets[1][0]]
            else:
                # Cả bầy đồng thuận 1 người -> chọn ngẫu nhiên nạn nhân thứ 2
                first_target = sorted_targets[0][0]
                possible_second = [
                    p.user_id for p in self.players.values()
                    if p.is_alive and not p.is_wolf and p.user_id != first_target
                ]
                if possible_second:
                    second_target = random.choice(possible_second)
                    self.record_log(
                        "WOLF_FURY_RANDOM",
                        target_id=second_target,
                        result="Sói Cuồng Sát: bầy sói chọn ngẫu nhiên mục tiêu thứ 2 do đồng thuận"
                    )
                    return [first_target, second_target]
                return [first_target]
        return [sorted_targets[0][0]]

    def resolve_wolf_target(self) -> Optional[int]:
        targets = self.resolve_wolf_targets()
        return targets[0] if targets else None

    def resolve_night(self) -> List[int]:
        """Tính toán ai chết ban đêm và cập nhật trạng thái."""
        deaths: Set[int] = set()

        # 0. Hiệp Sĩ Kiếm Gỉ Nguyền (kích hoạt từ đêm trước)
        if self.rusty_knight_curse_active:
            alive_wolves_rk = [p for p in self.players.values() if p.is_alive and p.is_wolf]
            if alive_wolves_rk:
                cursed_wolf = random.choice(alive_wolves_rk)
                deaths.add(cursed_wolf.user_id)
                self.record_log("RUSTY_KNIGHT_CURSE", target_id=cursed_wolf.user_id, result="Lời nguyền của Hiệp Sĩ Kiếm Gỉ hạ gục 1 Sói ngẫu nhiên!")

        # 1. Vũ Nữ "thăm" mục tiêu -> Phong tỏa kỹ năng
        if self.night_harlot_target:
            harlot_p = self.get_player_by_role(Role.HARLOT)
            if harlot_p and not harlot_p.is_roleblocked:
                target_p = self.players.get(self.night_harlot_target)
                if target_p:
                    target_p.is_roleblocked = True
                    self.record_log("HARLOT_VISIT", actor_id=harlot_p.user_id, target_id=target_p.user_id, result="Vũ Nữ phong tỏa kỹ năng đêm")

        wolf_targets = self.resolve_wolf_targets()

        # Hiệu ứng Thẻ Sự Kiện Đêm
        if self.current_night_event == NightEvent.HOLY_LIGHT and wolf_targets:
            for wolf_target_id in wolf_targets:
                self.record_log("HOLY_LIGHT_SAVED", target_id=wolf_target_id, result="Thánh Quang Bảo Hộ đã hóa giải đòn cắn của Bầy Sói đêm nay!")
            wolf_targets = []

        if self.current_night_event == NightEvent.WANING_MOON:
            self.night_white_wolf_target = None

        if self.current_night_event == NightEvent.THUNDERSTORM:
            self.girl_caught = False

        for wolf_target_id in wolf_targets:
            self.record_log("WOLF_KILL", target_id=wolf_target_id, result="Bầy Sói chọn cắn")

            guard_p = self.get_player_by_role(Role.GUARD)
            is_protected = (self.night_guard_target == wolf_target_id) and bool(guard_p and not guard_p.is_roleblocked)

            witch_p = self.get_player_by_role(Role.WITCH)
            is_saved = (self.night_witch_save is True) and bool(witch_p and not witch_p.is_roleblocked)

            if is_protected and guard_p:
                guard_p.guard_saved_count += 1
                self.record_log("GUARD_PROTECT", target_id=wolf_target_id, result="Bảo vệ thành công")

            if is_saved and witch_p:
                witch_p.witch_useful_use_count += 1
                self.record_log("WITCH_SAVE", target_id=wolf_target_id, result="Phù thủy dùng bình cứu")

            if not is_protected and not is_saved:
                target_p = self.players.get(wolf_target_id)
                if target_p:
                    if target_p.role == Role.CURSED and not target_p.is_cursed_converted:
                        target_p.is_cursed_converted = True
                        self.record_log("CURSED_CONVERT", target_id=wolf_target_id, result="Kẻ Bị Nguyền bị Sói cắn và biến thành Sói!")
                    elif target_p.role == Role.ELDER and target_p.elder_lives > 1:
                        target_p.elder_lives -= 1
                        self.record_log("ELDER_SAVED", target_id=wolf_target_id, result="Già Làng sống sót lần 1 trước nanh nanh Sói")
                    elif target_p.role == Role.SERIAL_KILLER:
                        self.record_log("SK_IMMUNE", target_id=wolf_target_id, result="Sát Thủ miễn nhiễm đòn cắn của Sói")
                    else:
                        deaths.add(wolf_target_id)
                        # Hiệp Sĩ Kiếm Gỉ bị Sói cắn → kích hoạt nguyền đêm sau
                        if target_p.role == Role.RUSTY_KNIGHT:
                            self.rusty_knight_curse_pending = True
                            self.record_log("RUSTY_KNIGHT_DYING", target_id=wolf_target_id, result="Hiệp Sĩ Kiếm Gỉ bị Sói cắn — lời nguyền sẽ giáng 1 Sói đêm sau!")

        # Xử lý Phù thủy dùng độc
        witch_p = self.get_player_by_role(Role.WITCH)
        if self.night_witch_poison and witch_p and not witch_p.is_roleblocked:
            poison_target = self.night_witch_poison
            target_p = self.players.get(poison_target)
            if target_p and target_p.role == Role.ALPHA_WOLF:
                if target_p.boss_poison_shield:
                    target_p.boss_poison_shield = False
                    self.record_log("BOSS_SHIELD_SAVED", target_id=poison_target, result="Chúa Tể Sói dùng Khiên Vương Giả hóa giải Bình Độc của Phù Thủy!")
                else:
                    target_p.boss_lives -= 1
                    if target_p.boss_lives > 0:
                        self.record_log("BOSS_DAMAGE", target_id=poison_target, result=f"Chúa Tể Sói dính Bình Độc tổn hại 1 Mạng! (Còn {target_p.boss_lives}/3 HP)")
                    else:
                        deaths.add(poison_target)
                        self.record_log("BOSS_KILLED", target_id=poison_target, result="Chúa Tể Sói đã bị Bình Độc kết liễu!")
            else:
                deaths.add(poison_target)
                if target_p and target_p.is_wolf:
                    witch_p.witch_useful_use_count += 1
                self.record_log("WITCH_POISON", target_id=poison_target, result="Phù thủy dùng bình độc")

        # Xử lý Sát Thủ Hàng Loạt giết người
        sk_p = self.get_player_by_role(Role.SERIAL_KILLER)
        if self.night_serial_killer_target and sk_p and not sk_p.is_roleblocked:
            sk_target = self.night_serial_killer_target
            is_sk_target_saved = (sk_target in wolf_targets and self.night_witch_save is True and witch_p and not witch_p.is_roleblocked)
            guard_p = self.get_player_by_role(Role.GUARD)
            is_sk_protected = (sk_target == self.night_guard_target and guard_p and not guard_p.is_roleblocked)
            if not is_sk_protected and not is_sk_target_saved:
                deaths.add(sk_target)
                self.record_log("SERIAL_KILLER_KILL", target_id=sk_target, result="Sát Thủ hạ gục nạn nhân ban đêm")
            elif is_sk_target_saved:
                self.record_log("WITCH_SAVE_SK", target_id=sk_target, result="Phù Thủy dùng bình cứu khỏi tay Sát Thủ")
            else:
                self.record_log("GUARD_PROTECT_SK", target_id=sk_target, result="Bảo vệ cứu sống khỏi tay Sát Thủ")

        # Xử lý Sói Trắng cắn thêm Sói (mỗi 2 đêm chẵn)
        if self.night_white_wolf_target:
            ww_p = self.get_player_by_role(Role.WHITE_WOLF)
            if ww_p and ww_p.is_alive and not ww_p.is_roleblocked:
                ww_target = self.players.get(self.night_white_wolf_target)
                if ww_target and ww_target.is_alive and ww_target.is_wolf:
                    deaths.add(self.night_white_wolf_target)
                    self.record_log("WHITE_WOLF_BITE", actor_id=ww_p.user_id, target_id=self.night_white_wolf_target, result="Sói Trắng bí mật hạ gục 1 đồng bọn Sói trong bầy!")

        # Xử lý Cô Bé bị bầy Sói phát hiện
        if self.girl_caught:
            girl_p = self.get_player_by_role(Role.THE_GIRL)
            if girl_p and girl_p.is_alive:
                deaths.add(girl_p.user_id)
                self.record_log("GIRL_CAUGHT", target_id=girl_p.user_id, result="Cô Bé bị bầy Sói phát hiện khi nhìn trộm và bị giết!")

        # Xử lý Người Thổi Sáo mê hoặc
        piper_p = self.get_player_by_role(Role.PIPER)
        if piper_p and piper_p.is_alive and not piper_p.is_roleblocked and self.night_piper_targets:
            charmed_names = []
            for t_id in self.night_piper_targets:
                t_p = self.players.get(t_id)
                if t_p and t_p.is_alive:
                    t_p.piper_charmed = True
                    self.piper_charmed_players.add(t_id)
                    charmed_names.append(t_p.display_name)
            if charmed_names:
                self.record_log("PIPER_CHARM", actor_id=piper_p.user_id, result=f"Người Thổi Sáo mê hoặc: {', '.join(charmed_names)}")

        # Cập nhật Lover chết theo
        lover_deaths = set()
        for uid in list(deaths):
            p = self.players.get(uid)
            if p and getattr(p, "lover_id", None) and getattr(p, "lover_id", None) in self.players:
                lover_p = self.players[p.lover_id]
                if lover_p.is_alive and lover_p.user_id not in deaths:
                    lover_deaths.add(lover_p.user_id)
                    self.record_log("LOVER_DEATH", target_id=lover_p.user_id, result="Chết vì đau thương do tình nhân qua đời")

        deaths.update(lover_deaths)

        # Cập nhật trạng thái sống/chết
        final_deaths = list(deaths)
        for uid in final_deaths:
            if uid in self.players:
                p = self.players[uid]
                p.is_alive = False
                self.record_log("NIGHT_DEATH", target_id=uid, result="Qua đời ban đêm")
                if p.role == Role.WOLF_CUB:
                    self.wolf_fury_pending = True
                    self.record_log("WOLF_CUB_RAGE", actor_id=uid, result="Sói Cuồng Sát qua đời, bầy Sói sục sôi cuồng nộ cho đêm sau!")

        # Kế thừa Tiên Tri Tập Sự nếu Tiên Tri chính qua đời
        seer_p = self.get_player_by_role(Role.SEER)
        if not seer_p or not seer_p.is_alive:
            app_p = self.get_player_by_role(Role.APPRENTICE_SEER)
            if app_p and not app_p.apprentice_promoted:
                app_p.apprentice_promoted = True
                self.record_log("APPRENTICE_PROMOTED", actor_id=app_p.user_id, result="Tiên Tri Tập Sự kế thừa vị trí Tiên Tri mới!")

        # Chốt kết quả soi cho Tiên Tri (tính toán lại để áp dụng Sói Ảo Ảnh / Vũ Nữ phong tỏa chính xác)
        if self.night_seer_target:
            active_seer_p = self.get_player_by_role(Role.SEER) or self.get_player_by_role(Role.APPRENTICE_SEER)
            t_p = self.players.get(self.night_seer_target)
            if t_p:
                if active_seer_p and active_seer_p.is_roleblocked:
                    self.night_seer_result = "❌ **Kỹ năng của bạn đã bị phong tỏa đêm nay!** (Do bị Vũ Nữ ghé thăm)"
                elif self.current_night_event == NightEvent.DENSE_FOG and random.random() < 0.5:
                    self.night_seer_result = f"🌫️ **Do Sương Mù Dày Đặc**, kết quả bói toán bị nhiễu! Không thể soi chính xác phe của {t_p.display_name}!"
                elif t_p.is_wolf or t_p.role == Role.LYCAN:
                    self.night_seer_result = f"🐺 **{t_p.display_name}** là **SÓI**!"
                    if active_seer_p:
                        active_seer_p.seer_found_wolf = True
                else:
                    phantom_deception = (
                        self.night_phantom_wolf_target == t_p.user_id
                        and any(
                            p.role == Role.PHANTOM_WOLF and p.is_alive and not p.is_roleblocked
                            for p in self.players.values()
                        )
                    )
                    if phantom_deception:
                        self.night_seer_result = f"🐺 **{t_p.display_name}** là **SÓI**!"
                    else:
                        self.night_seer_result = f"👤 **{t_p.display_name}** là **DÂN LÀNG** (không phải Sói)."

        # Lưu vết bảo vệ cho đêm sau của Bảo Vệ
        guard_p = self.get_player_by_role(Role.GUARD)
        if guard_p and self.night_guard_target:
            guard_p.protected_last_night = self.night_guard_target

        self.night_deaths = final_deaths
        return final_deaths

    def start_day(self):
        """Bắt đầu ngày mới."""
        self.day_count += 1
        self.day_votes.clear()
        self.early_vote_requests.clear()
        self.executed_player_id = None

    def resolve_day_vote(self) -> Optional[int]:
        """Tính phiếu bầu treo cổ ban ngày (Thị Trưởng vote x2, Chúa Tể Sói vote x3). Trả về user_id bị xử tử (hoặc None nếu hòa phiếu)."""
        if self.current_night_event == NightEvent.SOLAR_ECLIPSE:
            self.record_log("SOLAR_ECLIPSE_SKIP", result="Do ảnh hưởng của Nhật Thực Bóng Tối, ban ngày không thể bỏ phiếu treo cổ!")
            return None

        counts: Dict[Optional[int], int] = {}
        for voter_id, target_id in self.day_votes.items():
            voter_p = self.players.get(voter_id)
            if voter_p and voter_p.role == Role.ALPHA_WOLF:
                weight = 3
            elif self.mayor_id and voter_id == self.mayor_id:
                weight = 2
            else:
                weight = 1
            counts[target_id] = counts.get(target_id, 0) + weight

        if not counts:
            self.record_log("VOTE_RESULT", result="Không ai bị dồn phiếu")
            return None

        max_votes = max(counts.values())
        top_candidates = [tid for tid, cnt in counts.items() if cnt == max_votes]

        if None in top_candidates:
            self.record_log("VOTE_RESULT", result=f"Phiếu trắng/bỏ qua ({max_votes} phiếu) chiếm đa số hoặc hòa, không ai bị treo cổ")
            return None

        if len(top_candidates) > 1:
            # Hòa phiếu → kiểm tra Dê Tế Thần
            scapegoat_p = self.get_player_by_role(Role.SCAPEGOAT)
            if scapegoat_p and scapegoat_p.is_alive:
                executed_id = scapegoat_p.user_id
                self.record_log("SCAPEGOAT_EXECUTED", target_id=executed_id, result=f"Hòa phiếu ({max_votes} phiếu)! Dê Tế Thần tự động bị treo cổ thay thế!")
            else:
                self.record_log("VOTE_RESULT", result=f"Hòa phiếu ({max_votes} phiếu), không ai bị treo cổ")
                return None
        else:
            executed_id = top_candidates[0]

        ex_p = self.players[executed_id]
        if ex_p.role == Role.ALPHA_WOLF:
            ex_p.boss_lives -= 1
            if ex_p.boss_lives > 0:
                ex_p.is_alive = True
                self.record_log("BOSS_DAMAGE", target_id=executed_id, result=f"Chúa Tể Sói chịu đòn treo cổ nhưng còn {ex_p.boss_lives}/3 Mạng!")
                return executed_id

        ex_p.is_alive = False
        self.executed_player_id = executed_id

        self.record_log("DAY_EXECUTION", target_id=executed_id, result=f"Bị treo cổ với {max_votes} phiếu")

        if ex_p.role == Role.WOLF_CUB:
            self.wolf_fury_pending = True
            self.record_log("WOLF_CUB_RAGE", actor_id=executed_id, result="Sói Cuồng Sát bị treo cổ, bầy Sói sục sôi cuồng nộ cho đêm sau!")

        # Kế thừa Tiên Tri Tập Sự nếu Tiên Tri chính bị treo cổ
        seer_p = self.get_player_by_role(Role.SEER)
        if not seer_p or not seer_p.is_alive:
            app_p = self.get_player_by_role(Role.APPRENTICE_SEER)
            if app_p and not app_p.apprentice_promoted:
                app_p.apprentice_promoted = True
                self.record_log("APPRENTICE_PROMOTED", actor_id=app_p.user_id, result="Tiên Tri Tập Sự kế thừa vị trí Tiên Tri mới!")

        # Kiểm tra Kẻ Ngốc (Tanner)
        if self.players[executed_id].role == Role.TANNER:
            self.tanner_winner_id = executed_id
            self.winner_faction = Faction.INDEPENDENT
            self.record_log("GAME_WIN", actor_id=executed_id, result="Kẻ Ngốc thắng vì bị xử tử!")

        # Cập nhật Lover chết theo khi bị treo cổ
        ex_p = self.players[executed_id]
        if getattr(ex_p, "lover_id", None) and ex_p.lover_id in self.players:
            lover_p = self.players[ex_p.lover_id]
            if lover_p.is_alive:
                lover_p.is_alive = False
                self.record_log("LOVER_DEATH", target_id=lover_p.user_id, result="Chết vì đau thương do tình nhân bị treo cổ")
                if lover_p.role == Role.WOLF_CUB:
                    self.wolf_fury_pending = True
                    self.record_log("WOLF_CUB_RAGE", actor_id=lover_p.user_id, result="Sói Cuồng Sát qua đời do tình nhân bị treo cổ, bầy Sói sục sôi cuồng nộ cho đêm sau!")

        return executed_id

    def check_win_condition(self) -> Optional[Faction]:
        """Kiểm tra xem ván đấu đã có phe chiến thắng hay chưa."""
        if self.winner_faction:
            return self.winner_faction

        alive_players = self.get_alive_players()
        if len(alive_players) == 2:
            p1, p2 = alive_players[0], alive_players[1]
            if getattr(p1, "lover_id", None) == p2.user_id and p1.role.faction != p2.role.faction:
                self.winner_faction = Faction.LOVERS
                self.record_log("GAME_WIN", result="Phe Tình Nhân chiến thắng (cặp đôi sống sót cuối cùng)!")
                return Faction.LOVERS

        # Người Thổi Sáo thắng khi mê hoặc toàn bộ người sống (trừ bản thân)
        piper_alive_list = [p for p in alive_players if p.role == Role.PIPER]
        if piper_alive_list:
            piper_check = piper_alive_list[0]
            other_alive = [p for p in alive_players if p.user_id != piper_check.user_id]
            if other_alive and all(op.piper_charmed for op in other_alive):
                self.winner_faction = Faction.PIPER
                self.record_log("GAME_WIN", result="Người Thổi Sáo thắng — đã mê hoặc toàn bộ người chơi còn sống!")
                return Faction.PIPER

        # Sát Thủ Hàng Loạt độc chiếm chiến thắng
        sk_alive = [p for p in alive_players if p.role == Role.SERIAL_KILLER]
        if len(sk_alive) == 1 and len(alive_players) <= 2:
            self.winner_faction = Faction.SERIAL_KILLER
            self.record_log("GAME_WIN", result="Sát Thủ Hàng Loạt độc chiếm chiến thắng!")
            return Faction.SERIAL_KILLER

        alive_wolves = [p for p in alive_players if p.is_wolf]
        alive_non_wolves = [p for p in alive_players if not p.is_wolf and p.role != Role.SERIAL_KILLER]

        if len(alive_wolves) == 0 and len(sk_alive) == 0:
            self.winner_faction = Faction.VILLAGER
            self.record_log("GAME_WIN", result="Phe Dân Làng chiến thắng (tiêu diệt hết Sói và Sát Thủ)!")
            return Faction.VILLAGER

        if len(alive_wolves) >= len(alive_non_wolves) + len(sk_alive) and len(sk_alive) == 0:
            self.winner_faction = Faction.WEREWOLF
            self.record_log("GAME_WIN", result="Phe Sói chiến thắng (số Sói >= số Dân)!")
            return Faction.WEREWOLF

        return None

    def calculate_rank_points(self) -> Dict[int, int]:
        """Tính toán điểm rank cộng thêm cho từng người chơi."""
        points: Dict[int, int] = {}
        if not self.settings.enable_rank:
            return {uid: 0 for uid in self.players}

        for uid, player in self.players.items():
            pts = 0
            # Điểm thắng/thua theo phe
            # Kẻ Bị Nguyền đã convert thành Sói -> tính là thắng cùng phe Sói
            is_cursed_wolf_win = (
                player.is_cursed_converted
                and self.winner_faction == Faction.WEREWOLF
            )
            if self.winner_faction == Faction.INDEPENDENT:
                if uid == self.tanner_winner_id:
                    pts += 25
                else:
                    pts += 2
            elif self.winner_faction == Faction.PIPER:
                if player.role == Role.PIPER:
                    pts += 25
                else:
                    pts += 2
            elif player.role.faction == self.winner_faction or is_cursed_wolf_win:
                pts += 10
            else:
                pts += 2

            # Bonus sống sót
            if player.is_alive:
                pts += 3

            # Bonus kỹ năng cá nhân
            if player.seer_found_wolf:
                pts += 5
            if player.guard_saved_count > 0:
                pts += 5 * player.guard_saved_count
            if player.witch_useful_use_count > 0:
                pts += 5 * player.witch_useful_use_count

            points[uid] = pts

        return points
