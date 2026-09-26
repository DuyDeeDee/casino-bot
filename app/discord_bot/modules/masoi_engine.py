# coding: utf-8
"""
Ma Sói (Werewolf) Game Engine Module
Quản lý logic, state machine, vai trò, phiếu bầu, replay log và tính điểm rank.
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass
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
    WHITE_WOLF = "Sói Trắng ⭐"
    DRAW = "Hòa — không còn người sống"


class RankFaction(Enum):
    WOLF = "WOLF"
    SOLO = "SOLO"
    VILLAGER = "VILLAGER"

    @property
    def label(self) -> str:
        return {RankFaction.WOLF: "🐺 Sói", RankFaction.SOLO: "🃏 Solo", RankFaction.VILLAGER: "👥 Dân"}[self]


RANK_TEAM_WIN = 20
RANK_SOLO_WIN = 30
RANK_LOSS = -15
RANK_BONUS_CAP = 10


class GamePhase(Enum):
    LOBBY = "Đang chờ người chơi"
    ROLE_ASSIGN = "Đang chia vai trò"
    NIGHT_PREPARE = "Đang chuẩn bị hành động đêm"
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


class ActionKind(Enum):
    GUARD = "guard"
    WOLF_VOTE = "wolf_vote"
    SEER = "seer"
    HARLOT = "harlot"
    INVESTIGATE = "investigate"
    WOLF_SEER = "wolf_seer"
    SERIAL_KILL = "serial_kill"
    WHITE_WOLF = "white_wolf"
    PHANTOM = "phantom"
    GIRL = "girl"
    PIPER = "piper"
    CUPID = "cupid"
    WITCH_SAVE = "witch_save"
    WITCH_POISON = "witch_poison"


@dataclass(frozen=True)
class ActionIntent:
    night: int
    actor_id: int
    kind: ActionKind
    targets: Tuple[int, ...] = ()


@dataclass(frozen=True)
class NightResult:
    """Committed snapshot; resolving the same night returns this exact object."""
    night: int
    seed: int
    deaths: Tuple[int, ...]
    wolf_targets: Tuple[int, ...]
    outcomes: Tuple[Tuple[int, str, str], ...]
    pending_hunters: Tuple[int, ...]
    pending_mayor: Optional[int]


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
        night: int = 0,
        period: Optional[str] = None,
    ):
        self.day: int = day
        self.night: int = night
        self.period: Optional[str] = period
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
        self.rank_match_id: str = uuid.uuid4().hex
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
        # Channel permission overwrites changed for dead players, keyed by user ID.
        self.channel_permission_snapshots: Dict[int, object] = {}

        self._night_intents: Dict[Tuple[int, ActionKind], ActionIntent] = {}
        self._locked_intents: Optional[Tuple[ActionIntent, ...]] = None
        self._night_result: Optional[NightResult] = None
        self.night_deadline: float = 0.0
        self.night_seed: int = 0
        self.night_views: List[object] = []

        # Dữ liệu tạm trong đêm
        self.night_guard_target: Optional[int] = None
        self.night_wolf_votes: Dict[int, int] = {}  # wolf_id -> target_id
        self.night_resolved_wolf_targets: List[int] = []
        self.night_seer_target: Optional[int] = None
        self.night_seer_actor_id: Optional[int] = None
        self.night_seer_result: Optional[str] = None
        self.night_wolf_seer_target: Optional[int] = None
        self.night_wolf_seer_result: Optional[str] = None
        self.night_wolf_seer_dm_message: Optional[any] = None
        self.night_serial_killer_target: Optional[int] = None
        self.night_witch_save_target: Optional[int] = None
        self.night_witch_poison: Optional[int] = None
        self.night_harlot_target: Optional[int] = None
        self.night_cupid_actor_id: Optional[int] = None
        self.night_cupid_targets: Optional[Tuple[int, int]] = None
        self.night_cupid_result: Optional[str] = None
        self.night_cupid_dm_message: Optional[any] = None
        self.night_investigator_targets: Optional[Tuple[int, int]] = None
        self.night_investigator_result: Optional[str] = None
        self.night_investigator_dm_message: Optional[any] = None
        self.night_white_wolf_target: Optional[int] = None  # Sói Trắng cắn thêm 1 Sói (mỗi 2 đêm chẵn)
        self.night_phantom_wolf_target: Optional[int] = None  # Sói Ảo Ảnh giả dạng người dân
        self.night_piper_targets: List[int] = []  # Người Thổi Sáo mê hoặc 2 người
        self.piper_charmed_players: Set[int] = set()  # Tất cả người đã bị mê hoặc qua các đêm
        self.girl_caught: bool = False  # Cô Bé bị Sói bắt gặp đêm nay
        self.girl_peeking_user_id: Optional[int] = None  # Cô Bé chọn nhìn trộm đêm nay
        self.girl_dm_message: Optional[any] = None
        self.girl_result: Optional[str] = None
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
        self.checkpoint_hook = None
        self.rank_settled = False

    def checkpoint(self):
        if self.checkpoint_hook is not None:
            self.checkpoint_hook(self)

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

    def validate_role_setup(self) -> List[str]:
        """Return configuration errors that would create an unwinnable or invalid setup."""
        n = len(self.players)
        errors: List[str] = []
        if n < 5:
            errors.append("Cần tối thiểu 5 người chơi.")
            return errors

        if self.settings.enable_boss_mode:
            return errors

        if self.settings.role_setup_mode != "CUSTOM":
            return errors

        wolf_count = self.settings.custom_wolf_count
        if type(wolf_count) is not int or wolf_count < 1:
            errors.append("Số lượng Sói phải ít nhất là 1.")
            return errors

        special_roles: List[Role] = []
        if not isinstance(self.settings.custom_special_roles, list):
            errors.append("Danh sách vai trò đặc biệt phải là một danh sách hợp lệ.")
            return errors
        for role_name in self.settings.custom_special_roles:
            try:
                special_roles.append(Role[role_name])
            except (KeyError, TypeError):
                errors.append(f"Vai trò không hợp lệ: {role_name!r}.")

        if len(special_roles) != len(set(special_roles)):
            errors.append("Không thể chọn trùng một vai trò đặc biệt.")

        if any(role in (Role.WOLF, Role.VILLAGER, Role.ALPHA_WOLF) for role in special_roles):
            errors.append("Sói Thường/Dân Thường không phải vai trò đặc biệt; Boss cần dùng chế độ Boss.")

        total_roles = wolf_count + len(special_roles)
        if total_roles > n:
            errors.append(
                f"Cấu hình có {total_roles} vai trò cho {n} người; hãy bỏ bớt vai trò đặc biệt hoặc giảm số Sói."
            )

        wolves = wolf_count + sum(role.faction == Faction.WEREWOLF for role in special_roles)
        if wolves >= n - wolves:
            errors.append("Số Sói phải ít hơn số người không thuộc phe Sói khi bắt đầu.")

        if Role.APPRENTICE_SEER in special_roles and Role.SEER not in special_roles:
            errors.append("Tiên Tri Tập Sự cần có Tiên Tri chính trong đội hình.")

        return errors

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
        self.stop_night_views()
        self.night_count += 1
        self.phase = GamePhase.NIGHT_GUARD

        self._night_intents.clear()
        self._locked_intents = None
        self._night_result = None
        self.night_seed = random.getrandbits(64)
        self.night_deadline = time.monotonic() + self.settings.night_time
        for p in self.players.values():
            p.is_roleblocked = False
        self.night_guard_target = None
        self.night_wolf_votes.clear()
        self.night_resolved_wolf_targets = []
        self.night_seer_target = None
        self.night_seer_actor_id = None
        self.night_seer_result = None
        self.night_wolf_seer_target = None
        self.night_wolf_seer_result = None
        self.night_wolf_seer_dm_message = None
        self.night_serial_killer_target = None
        self.night_witch_save_target = None
        self.night_witch_poison = None
        self.night_harlot_target = None
        self.night_cupid_actor_id = None
        self.night_cupid_targets = None
        self.night_cupid_result = None
        self.night_cupid_dm_message = None
        self.night_investigator_targets = None
        self.night_investigator_result = None
        self.night_investigator_dm_message = None
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
        self.girl_result = None
        self.seer_dm_message = None

    def prepare_night_delivery(self):
        self.phase = GamePhase.NIGHT_PREPARE
        self.night_deadline = 0.0
        self.checkpoint()

    def open_night_actions(self):
        if self.phase != GamePhase.NIGHT_PREPARE:
            raise ValueError("Đêm chưa ở giai đoạn chuẩn bị.")
        self.night_deadline = time.monotonic() + self.settings.night_time
        self.phase = GamePhase.NIGHT_GUARD
        self.checkpoint()

    def stop_night_views(self):
        for view in self.night_views:
            view.stop()
        self.night_views.clear()

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
            night=self.night_count,
            period="DAY" if self.phase in (GamePhase.DAY_ANNOUNCE, GamePhase.DAY_DISCUSSION, GamePhase.DAY_VOTE, GamePhase.DAY_RESOLVE) else "NIGHT",
            phase=self.phase.value,
            event_type=event_type,
            actor_id=actor_id,
            actor_name=actor_name,
            target_id=target_id,
            target_name=target_name,
            result=result,
        )
        self.replay_logs.append(log)
        self.checkpoint()

    def accepts_night_actions(self, night: int) -> bool:
        return (
            night == self.night_count and self._locked_intents is None
            and time.monotonic() < self.night_deadline
            and self.phase in (
                GamePhase.NIGHT_GUARD, GamePhase.NIGHT_WOLF,
                GamePhase.NIGHT_SEER, GamePhase.NIGHT_WITCH,
            )
        )

    def submit_night_action(self, intent: ActionIntent):
        """Validate synchronously before storing; never apply gameplay effects here."""
        if not self.accepts_night_actions(intent.night):
            raise ValueError("Lượt đêm đã hết hạn hoặc đã được khóa.")
        actor = self.players.get(intent.actor_id)
        if not actor or not actor.is_alive:
            raise ValueError("Bạn không còn quyền hành động trong ván này.")
        roles = {
            ActionKind.GUARD: Role.GUARD, ActionKind.SEER: Role.SEER,
            ActionKind.HARLOT: Role.HARLOT, ActionKind.INVESTIGATE: Role.INVESTIGATOR,
            ActionKind.WOLF_SEER: Role.WOLF_SEER, ActionKind.SERIAL_KILL: Role.SERIAL_KILLER,
            ActionKind.WHITE_WOLF: Role.WHITE_WOLF, ActionKind.PHANTOM: Role.PHANTOM_WOLF,
            ActionKind.GIRL: Role.THE_GIRL, ActionKind.PIPER: Role.PIPER,
            ActionKind.CUPID: Role.CUPID,
            ActionKind.WITCH_SAVE: Role.WITCH, ActionKind.WITCH_POISON: Role.WITCH,
        }
        if intent.kind == ActionKind.WOLF_VOTE:
            authorized = actor.is_wolf
        else:
            authorized = intent.kind in roles and (
                actor.role == roles[intent.kind] or (
                    intent.kind == ActionKind.SEER and actor.role == Role.APPRENTICE_SEER
                    and actor.apprentice_promoted
                )
            )
        if not authorized:
            raise ValueError("Vai trò của bạn không có kỹ năng này.")
        key = (intent.actor_id, intent.kind)
        if key in self._night_intents:
            raise ValueError("Bạn đã xác nhận kỹ năng này trong đêm.")
        targets = intent.targets
        if not isinstance(targets, tuple) or len(set(targets)) != len(targets):
            raise ValueError("Danh sách mục tiêu không hợp lệ.")
        if intent.kind == ActionKind.GIRL:
            expected = 0
        elif intent.kind == ActionKind.CUPID:
            expected = 2
        elif intent.kind in (ActionKind.PIPER, ActionKind.INVESTIGATE):
            expected = min(2, len(self.get_alive_players()) - 1)
        else:
            expected = 1
        optional = intent.kind in (
            ActionKind.WHITE_WOLF, ActionKind.WITCH_SAVE, ActionKind.WITCH_POISON,
        )
        if len(targets) != expected and not (optional and not targets):
            raise ValueError("Số lượng mục tiêu không hợp lệ.")
        for uid in targets:
            target = self.players.get(uid)
            if not target or not target.is_alive:
                raise ValueError("Mục tiêu không còn sống trong ván.")
            if uid == actor.user_id and intent.kind not in (
                ActionKind.GUARD, ActionKind.CUPID, ActionKind.WITCH_SAVE,
            ):
                raise ValueError("Không thể chọn bản thân cho kỹ năng này.")
            if intent.kind == ActionKind.WOLF_VOTE and target.is_wolf:
                raise ValueError("Bầy Sói không thể cắn đồng đội.")
            if intent.kind == ActionKind.WHITE_WOLF and not target.is_wolf:
                raise ValueError("Sói Trắng chỉ được cắn thêm một Sói.")
            if intent.kind == ActionKind.PHANTOM and target.is_wolf:
                raise ValueError("Sói Ảo Ảnh chỉ được giả dạng người không thuộc bầy Sói.")
        if intent.kind == ActionKind.GUARD and targets[0] == actor.protected_last_night:
            raise ValueError("Không thể bảo vệ cùng người hai đêm liên tiếp.")
        if intent.kind == ActionKind.CUPID and self.night_count != 1:
            raise ValueError("Thần Tình Yêu chỉ ghép đôi trong đêm đầu.")
        if intent.kind == ActionKind.WHITE_WOLF and (
            self.night_count % 2 or self.current_night_event == NightEvent.WANING_MOON
        ):
            raise ValueError("Sói Trắng không thể cắn thêm trong đêm này.")
        if intent.kind in (ActionKind.WITCH_SAVE, ActionKind.WITCH_POISON):
            used = actor.witch_save_used if intent.kind == ActionKind.WITCH_SAVE else actor.witch_poison_used
            if self.current_night_event == NightEvent.SEAL_NIGHT or (targets and used):
                raise ValueError("Bình thuốc không còn khả dụng trong đêm này.")
        self._night_intents[key] = intent
        self.checkpoint()

    def lock_night(self):
        """Freeze before the first awaited announcement/cleanup at the deadline."""
        if self.night_count == 0 or self.phase not in (
            GamePhase.NIGHT_GUARD, GamePhase.NIGHT_WOLF,
            GamePhase.NIGHT_SEER, GamePhase.NIGHT_WITCH, GamePhase.NIGHT_RESOLVE,
        ):
            raise ValueError("Không thể xử lý đêm ngoài giai đoạn ban đêm.")
        if self._locked_intents is None:
            self._locked_intents = tuple(sorted(
                self._night_intents.values(), key=lambda a: (a.kind.value, a.actor_id)
            ))
        self.phase = GamePhase.NIGHT_RESOLVE
        self.stop_night_views()


    def resolve_wolf_targets(self, *, include_fury: bool = False, rng=None) -> List[int]:
        """Pure preview by default; only committed resolution draws the extra victim."""
        if self._night_result is not None:
            return list(self._night_result.wolf_targets)
        actions = self._locked_intents if self._locked_intents is not None else tuple(self._night_intents.values())
        counts: Dict[int, int] = {}
        for action in actions:
            if action.kind != ActionKind.WOLF_VOTE or not action.targets:
                continue
            wolf = self.players.get(action.actor_id)
            target = self.players.get(action.targets[0])
            if not wolf or not wolf.is_alive or not wolf.is_wolf or wolf.is_roleblocked:
                continue
            if target and target.is_alive and not target.is_wolf:
                counts[target.user_id] = counts.get(target.user_id, 0) + 1
        ranked = sorted(counts, key=lambda uid: (-counts[uid], uid))
        if not ranked:
            return []
        if not include_fury or not self.wolf_fury_active:
            return ranked[:1]
        if len(ranked) >= 2:
            return ranked[:2]
        candidates = sorted(p.user_id for p in self.get_alive_players() if not p.is_wolf and p.user_id != ranked[0])
        return ranked[:1] + ([rng.choice(candidates)] if candidates else [])

    def resolve_wolf_target(self) -> Optional[int]:
        targets = self.resolve_wolf_targets()
        return targets[0] if targets else None

    def apply_deaths(self, victims, event_type: str) -> Tuple[int, ...]:
        """One death pipeline for night, execution and hunter continuations."""
        pending = set(victims)
        died = set()
        while pending:
            uid = min(pending)
            pending.remove(uid)
            player = self.players.get(uid)
            if not player or not player.is_alive:
                continue
            player.is_alive = False
            died.add(uid)
            self.record_log(event_type, target_id=uid, result="Người chơi qua đời")
            if player.role == Role.WOLF_CUB:
                self.wolf_fury_pending = True
                self.record_log("WOLF_CUB_RAGE", actor_id=uid, result="Sói Cuồng Sát qua đời: cuồng nộ đêm sau")
            partner = self.players.get(player.lover_id)
            if partner and partner.is_alive and partner.user_id not in pending:
                pending.add(partner.user_id)
                self.record_log("LOVER_DEATH", target_id=partner.user_id, result="Chết vì tình nhân qua đời")
        if not self.get_player_by_role(Role.SEER):
            apprentice = self.get_player_by_role(Role.APPRENTICE_SEER)
            if apprentice and not apprentice.apprentice_promoted:
                apprentice.apprentice_promoted = True
                self.record_log("APPRENTICE_PROMOTED", actor_id=apprentice.user_id, result="Kế thừa Tiên Tri")
        return tuple(sorted(died))

    def _damage(self, target_id: int, source: str, deaths: Set[int]):
        target = self.players[target_id]
        if target.role == Role.ALPHA_WOLF:
            if source == "poison" and target.boss_poison_shield:
                target.boss_poison_shield = False
                self.record_log("BOSS_SHIELD_SAVED", target_id=target_id, result="Khiên hóa giải bình độc")
                return
            target.boss_lives = max(0, target.boss_lives - 1)
            self.record_log("BOSS_DAMAGE", target_id=target_id, result=f"Còn {target.boss_lives}/3 HP")
            if target.boss_lives:
                return
        deaths.add(target_id)

    def resolve_hunter_shot(self, hunter_id: int, target_id: int) -> Tuple[int, ...]:
        hunter, target = self.players.get(hunter_id), self.players.get(target_id)
        if not hunter or hunter.role != Role.HUNTER or hunter.is_alive:
            raise ValueError("Thợ Săn chưa được phép bắn.")
        if hunter.hunter_shot_used or not target or not target.is_alive or self.phase == GamePhase.GAME_END:
            raise ValueError("Phát bắn không còn hợp lệ.")
        hunter.hunter_shot_used = True
        deaths: Set[int] = set()
        self.record_log("HUNTER_SHOOT", actor_id=hunter_id, target_id=target_id, result="Thợ Săn bắn")
        self._damage(target_id, "hunter", deaths)
        return self.apply_deaths(deaths, "HUNTER_DEATH")

    def resolve_night(self) -> NightResult:
        """Roleblock → effects/protection → attacks/potions → damage → deaths → information.

        Actors alive at the deadline act simultaneously, even if they die this night.
        All randomness uses one seed; repeated calls cannot spend items or kill twice.
        """
        if self._night_result is not None:
            return self._night_result
        self.lock_night()
        rng = random.Random(self.night_seed)
        alive = {p.user_id: p for p in self.get_alive_players()}
        actions = self._locked_intents
        def action(kind):
            return next((a for a in actions if a.kind == kind), None)
        def active(kind):
            a = action(kind)
            return a if a and a.actor_id in alive and not alive[a.actor_id].is_roleblocked else None
        def project(kind, attr):
            a = active(kind)
            setattr(self, attr, a.targets[0] if a and a.targets else None)
            return a

        # Resolve block before consulting any other action.
        visit = action(ActionKind.HARLOT)
        if visit and visit.actor_id in alive and visit.targets[0] in alive:
            alive[visit.targets[0]].is_roleblocked = True
            self.record_log("HARLOT_VISIT", actor_id=visit.actor_id, target_id=visit.targets[0], result="Phong tỏa kỹ năng")
        project(ActionKind.HARLOT, "night_harlot_target")
        guard = project(ActionKind.GUARD, "night_guard_target")
        if guard:
            alive[guard.actor_id].protected_last_night = guard.targets[0]
        cupid = active(ActionKind.CUPID)
        if cupid:
            one, two = (alive[uid] for uid in cupid.targets)
            one.lover_id, two.lover_id = two.user_id, one.user_id
            self.night_cupid_targets = cupid.targets
            self.night_cupid_result = f"💘 Đã ghép đôi **{one.display_name}** và **{two.display_name}**."
            self.record_log("CUPID_PAIR", actor_id=cupid.actor_id, target_id=one.user_id, result=self.night_cupid_result)
        elif action(ActionKind.CUPID):
            self.night_cupid_result = "❌ Kỹ năng của bạn đã bị phong tỏa đêm nay."

        phantom = project(ActionKind.PHANTOM, "night_phantom_wolf_target")
        piper = active(ActionKind.PIPER)
        if piper:
            for uid in piper.targets:
                alive[uid].piper_charmed = True
                self.piper_charmed_players.add(uid)
            self.record_log("PIPER_CHARM", actor_id=piper.actor_id, result="Mê hoặc các mục tiêu đã chọn")
        girl = active(ActionKind.GIRL)
        if girl:
            self.girl_peeking_user_id = girl.actor_id
            self.girl_caught = self.current_night_event != NightEvent.THUNDERSTORM and rng.random() < 0.5
            self.girl_result = "😱 Bạn bị phát hiện và sẽ chết đêm nay!" if self.girl_caught else "👀 Nhìn trộm thành công."
        elif action(ActionKind.GIRL):
            self.girl_result = "❌ Kỹ năng nhìn trộm đã bị phong tỏa đêm nay."

        wolf_targets = self.resolve_wolf_targets(include_fury=True, rng=rng)
        self.night_resolved_wolf_targets = list(wolf_targets)
        self.night_wolf_votes = {a.actor_id: a.targets[0] for a in actions if a.kind == ActionKind.WOLF_VOTE}
        sk = project(ActionKind.SERIAL_KILL, "night_serial_killer_target")
        white = project(ActionKind.WHITE_WOLF, "night_white_wolf_target")
        save = project(ActionKind.WITCH_SAVE, "night_witch_save_target")
        poison = project(ActionKind.WITCH_POISON, "night_witch_poison")
        # Recheck potion resources/events at commit, not just at submission.
        if self.current_night_event == NightEvent.SEAL_NIGHT:
            save = poison = None
        if save and (not save.targets or alive[save.actor_id].witch_save_used):
            save = None
        if poison and (not poison.targets or alive[poison.actor_id].witch_poison_used):
            poison = None
        if save:
            alive[save.actor_id].witch_save_used = True
        if poison:
            alive[poison.actor_id].witch_poison_used = True
        if self.current_night_event == NightEvent.WANING_MOON:
            white = None
        deaths: Set[int] = set()
        if self.rusty_knight_curse_active:
            wolves = sorted(uid for uid, p in alive.items() if p.is_wolf)
            if wolves:
                uid = rng.choice(wolves)
                self._damage(uid, "curse", deaths)
                self.record_log("RUSTY_KNIGHT_CURSE", target_id=uid, result="Lời nguyền Hiệp Sĩ")
        attacks = [(uid, "wolf") for uid in wolf_targets if self.current_night_event != NightEvent.HOLY_LIGHT]
        if sk and sk.targets:
            attacks.append((sk.targets[0], "serial_killer"))
        if white and white.targets:
            attacks.append((white.targets[0], "white_wolf"))
        saved_targets, protected_targets = set(), set()
        for uid, source in attacks:
            target = alive[uid]
            event = {"wolf": "WOLF_KILL", "serial_killer": "SERIAL_KILLER_KILL", "white_wolf": "WHITE_WOLF_BITE"}[source]
            actor_id = sk.actor_id if source == "serial_killer" else white.actor_id if source == "white_wolf" else None
            self.record_log(event, actor_id=actor_id, target_id=uid, result="Tấn công đêm")
            if guard and uid == guard.targets[0]:
                protected_targets.add(uid)
                self.record_log("GUARD_PROTECT", target_id=uid, result="Bảo vệ thành công")
                continue
            if save and uid == save.targets[0]:
                saved_targets.add(uid)
                self.record_log("WITCH_SAVE", target_id=uid, result="Bình cứu bảo vệ mục tiêu")
                continue
            if source == "wolf":
                if target.role == Role.CURSED and not target.is_cursed_converted:
                    target.is_cursed_converted = True
                    self.record_log("CURSED_CONVERT", target_id=uid, result="Biến thành Sói")
                    continue
                if target.role == Role.ELDER and target.elder_lives > 1:
                    target.elder_lives -= 1
                    self.record_log("ELDER_SAVED", target_id=uid, result="Già Làng chống chịu đòn cắn đầu tiên")
                    continue
                if target.role == Role.SERIAL_KILLER:
                    self.record_log("SK_IMMUNE", target_id=uid, result="Sát Thủ miễn nhiễm đòn cắn của Sói")
                    continue
                if target.role == Role.RUSTY_KNIGHT:
                    self.rusty_knight_curse_pending = True
                    self.record_log("RUSTY_KNIGHT_DYING", target_id=uid, result="Lời nguyền kích hoạt đêm sau")
            self._damage(uid, source, deaths)
        if guard:
            alive[guard.actor_id].guard_saved_count += len(protected_targets)
        if save:
            alive[save.actor_id].witch_useful_use_count += len(saved_targets)
        if poison:
            uid = poison.targets[0]
            self._damage(uid, "poison", deaths)
            if alive[uid].is_wolf and uid in deaths:
                alive[poison.actor_id].witch_useful_use_count += 1
            self.record_log("WITCH_POISON", target_id=uid, result="Dùng bình độc")
        if self.girl_caught and girl:
            deaths.add(girl.actor_id)
            self.record_log("GIRL_CAUGHT", target_id=girl.actor_id, result="Cô Bé bị phát hiện khi nhìn trộm")
        final_deaths = self.apply_deaths(deaths, "NIGHT_DEATH")

        # Use deadline actors, not alive-role lookups, after applying deaths.
        outcomes = []
        blocked = "❌ Kỹ năng của bạn đã bị phong tỏa đêm nay."
        for kind, attr in (
            (ActionKind.SEER, "night_seer_result"),
            (ActionKind.INVESTIGATE, "night_investigator_result"),
            (ActionKind.WOLF_SEER, "night_wolf_seer_result"),
        ):
            submitted = action(kind)
            if not submitted:
                continue
            actor = alive[submitted.actor_id]
            targets = [alive[uid] for uid in submitted.targets]
            if actor.is_roleblocked:
                result = blocked
            elif kind == ActionKind.SEER:
                target = targets[0]
                deceptive = bool(phantom and phantom.targets[0] == target.user_id)
                if self.current_night_event == NightEvent.DENSE_FOG and rng.random() < 0.5:
                    result = f"🌫️ Không thể soi chính xác phe của **{target.display_name}** do Sương Mù."
                elif target.is_wolf or target.role == Role.LYCAN or deceptive:
                    result = f"🐺 **{target.display_name}** là **SÓI**!"
                    if target.is_wolf:
                        actor.seer_found_wolf = True
                else:
                    result = f"👤 **{target.display_name}** là **DÂN LÀNG** (không phải Sói)."
            elif kind == ActionKind.INVESTIGATE:
                names = " & ".join(f"**{p.display_name}**" for p in targets)
                found = any(p.is_wolf or p.role == Role.LYCAN for p in targets)
                result = f"⚠️ Trong {names} — **CÓ ÍT NHẤT 1 SÓI**!" if found else f"✅ Trong {names} — **KHÔNG CÓ SÓI NÀO**!"
            else:
                target = targets[0]
                result = f"🔮 **{target.display_name}** có vai trò: {target.role.emoji} **{target.role.value}**"
            setattr(self, attr, result)
            outcomes.append((actor.user_id, kind.value, result))
            event = {ActionKind.SEER: "SEER_INSPECT", ActionKind.INVESTIGATE: "INVESTIGATOR_CHECK", ActionKind.WOLF_SEER: "WOLF_SEER_INSPECT"}[kind]
            self.record_log(event, actor_id=actor.user_id, target_id=submitted.targets[0] if submitted.targets else None, result=result)
        for kind, result in ((ActionKind.CUPID, self.night_cupid_result), (ActionKind.GIRL, self.girl_result)):
            a = action(kind)
            if a and result:
                outcomes.append((a.actor_id, kind.value, result))
        self.night_deaths = list(final_deaths)
        self.record_log("NIGHT_RESOLVED", result=f"Đêm {self.night_count}; RNG seed={self.night_seed}")
        self._night_result = NightResult(
            self.night_count, self.night_seed, final_deaths, tuple(wolf_targets),
            tuple(outcomes),
            tuple(sorted(p.user_id for p in self.players.values() if p.role == Role.HUNTER and not p.is_alive and not p.hunter_shot_used)),
            self.mayor_id if self.mayor_id in self.players and not self.players[self.mayor_id].is_alive else None,
        )
        self.checkpoint()
        return self._night_result

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

        self.apply_deaths((executed_id,), "DAY_DEATH")
        self.executed_player_id = executed_id

        self.record_log("DAY_EXECUTION", target_id=executed_id, result=f"Bị treo cổ với {max_votes} phiếu")

        # Kiểm tra Kẻ Ngốc (Tanner)
        if self.players[executed_id].role == Role.TANNER:
            self.tanner_winner_id = executed_id
            self.winner_faction = Faction.INDEPENDENT
            self.record_log("GAME_WIN", actor_id=executed_id, result="Kẻ Ngốc thắng vì bị xử tử!")

        return executed_id

    def check_win_condition(self) -> Optional[Faction]:
        """Kiểm tra xem ván đấu đã có phe chiến thắng hay chưa."""
        if self.winner_faction:
            return self.winner_faction

        if any(p.role == Role.HUNTER and not p.is_alive and not p.hunter_shot_used for p in self.players.values()):
            return None
        alive_players = self.get_alive_players()
        if not alive_players:
            self.winner_faction = Faction.DRAW
            self.record_log("GAME_DRAW", result="Không còn người sống; không tính rank.")
            return Faction.DRAW
        if len(alive_players) == 1 and alive_players[0].role == Role.WHITE_WOLF:
            self.winner_faction = Faction.WHITE_WOLF
            self.record_log("GAME_WIN", actor_id=alive_players[0].user_id, result="Sói Trắng là người cuối cùng còn sống và chiến thắng một mình!")
            return Faction.WHITE_WOLF
        if len(alive_players) == 2:
            p1, p2 = alive_players[0], alive_players[1]
            if p1.lover_id == p2.user_id and p2.lover_id == p1.user_id and (Faction.WEREWOLF if p1.is_wolf else p1.role.faction) != (Faction.WEREWOLF if p2.is_wolf else p2.role.faction):
                self.winner_faction = Faction.LOVERS
                self.record_log("GAME_WIN", result="Phe Tình Nhân chiến thắng (cặp đôi sống sót cuối cùng)!")
                return Faction.LOVERS

        # Người Thổi Sáo thắng khi mê hoặc toàn bộ người sống (trừ bản thân)
        piper_alive_list = [p for p in alive_players if p.role == Role.PIPER]
        if piper_alive_list:
            piper_check = piper_alive_list[0]
            other_alive = [p for p in alive_players if p.user_id != piper_check.user_id]
            if all(op.piper_charmed for op in other_alive):
                self.winner_faction = Faction.PIPER
                self.record_log("GAME_WIN", result="Người Thổi Sáo thắng — đã mê hoặc toàn bộ người chơi còn sống!")
                return Faction.PIPER

        # Sát Thủ Hàng Loạt độc chiếm chiến thắng
        sk_alive = [p for p in alive_players if p.role == Role.SERIAL_KILLER]
        if len(sk_alive) == 1 and len(alive_players) == 1:
            self.winner_faction = Faction.SERIAL_KILLER
            self.record_log("GAME_WIN", result="Sát Thủ Hàng Loạt độc chiếm chiến thắng!")
            return Faction.SERIAL_KILLER

        alive_wolves = [p for p in alive_players if p.is_wolf]
        alive_non_wolves = [p for p in alive_players if not p.is_wolf and p.role != Role.SERIAL_KILLER]

        if len(alive_wolves) == 0 and len(sk_alive) == 0 and not piper_alive_list:
            self.winner_faction = Faction.VILLAGER
            self.record_log("GAME_WIN", result="Phe Dân Làng chiến thắng (tiêu diệt hết Sói và Sát Thủ)!")
            return Faction.VILLAGER

        white_wolf_alive = any(p.role == Role.WHITE_WOLF for p in alive_players)
        if (len(alive_wolves) >= len(alive_non_wolves) + len(sk_alive)
                and not sk_alive and not white_wolf_alive and not piper_alive_list):
            self.winner_faction = Faction.WEREWOLF
            self.record_log("GAME_WIN", result="Phe Sói chiến thắng (số Sói >= số Dân)!")
            return Faction.WEREWOLF

        return None

    def calculate_rank_points(self) -> Dict[int, int]:
        """Signed result: losses always subtract; performance only rewards wins."""
        points: Dict[int, int] = {}
        if not self.settings.enable_rank or not self.winner_faction or self.winner_faction == Faction.DRAW:
            return {uid: 0 for uid in self.players}

        for uid, player in self.players.items():
            if not self.did_player_win(uid):
                points[uid] = RANK_LOSS
                continue
            base = RANK_SOLO_WIN if self.get_rank_faction(uid) == RankFaction.SOLO else RANK_TEAM_WIN
            bonus = 5 * (int(player.seer_found_wolf) + max(0, player.guard_saved_count) + max(0, player.witch_useful_use_count))
            points[uid] = base + min(RANK_BONUS_CAP, bonus)

        return points

    def get_rank_faction(self, user_id: int) -> RankFaction:
        """Rank follows the personal objective, not the winner of the match."""
        player = self.players[user_id]
        if player.role in (Role.TANNER, Role.SERIAL_KILLER, Role.PIPER, Role.WHITE_WOLF):
            return RankFaction.SOLO
        partner = self.players.get(player.lover_id)
        if partner and partner.lover_id == user_id:
            team = Faction.WEREWOLF if player.is_wolf else player.role.faction
            partner_team = Faction.WEREWOLF if partner.is_wolf else partner.role.faction
            if team != partner_team:
                return RankFaction.SOLO
        return RankFaction.WOLF if player.is_wolf else RankFaction.VILLAGER

    def did_player_win(self, user_id: int) -> bool:
        """Whether this player's personal win condition was met."""
        player = self.players.get(user_id)
        if not player or not self.winner_faction:
            return False
        if self.winner_faction == Faction.INDEPENDENT:
            return user_id == self.tanner_winner_id
        if self.winner_faction == Faction.PIPER:
            return player.role == Role.PIPER
        if self.winner_faction == Faction.SERIAL_KILLER:
            return player.role == Role.SERIAL_KILLER
        if self.winner_faction == Faction.WHITE_WOLF:
            return player.role == Role.WHITE_WOLF and player.is_alive
        if self.winner_faction == Faction.LOVERS:
            partner = self.players.get(player.lover_id) if player.lover_id else None
            return bool(player.is_alive and partner and partner.is_alive and partner.lover_id == user_id)
        if self.get_rank_faction(user_id) == RankFaction.SOLO:
            return False
        if player.is_cursed_converted:
            return self.winner_faction == Faction.WEREWOLF
        return player.role.faction == self.winner_faction
