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
    WOLF_GUARD = "Ác Sói"
    CURSED = "Kẻ Bị Nguyền"
    ELDER = "Già Làng"
    SERIAL_KILLER = "Sát Thủ"
    WOLF_CUB = "Sói Cuồng Sát"
    HARLOT = "Kĩ Nữ"
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
    ALPHA_WOLF = "Chúa Tể Sói"  # Legacy snapshots only; never assigned to a new match.
    ARSONIST = "Kẻ Phóng Hỏa"
    HUMAN_HUNTER = "Thợ Săn Người"
    DOCTOR = "Bác Sĩ"
    YOUNG_WOLF = "Sói Trẻ"
    GUNNER = "Xạ Thủ"
    FORENSIC = "Pháp Y"
    STRONGMAN = "Lực Sĩ"
    PRIEST = "Mục Sư"
    BIGMOUTH = "Cậu Bé Mồm To"

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
            Role.WOLF_GUARD: "🐺🛡️",
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
            Role.ARSONIST: "🔥",
            Role.HUMAN_HUNTER: "🎯",
            Role.DOCTOR: "🩺",
            Role.YOUNG_WOLF: "🐺🧸",
            Role.GUNNER: "🔫",
            Role.FORENSIC: "🧬",
            Role.STRONGMAN: "💪",
            Role.PRIEST: "✝️",
            Role.BIGMOUTH: "📣",
        }
        return emojis.get(self, "❓")

    @property
    def faction(self) -> Faction:
        if self in (Role.WOLF, Role.WOLF_SEER, Role.WOLF_GUARD, Role.WOLF_CUB, Role.WHITE_WOLF, Role.PHANTOM_WOLF, Role.MUTE_WOLF, Role.ALPHA_WOLF, Role.YOUNG_WOLF):
            return Faction.WEREWOLF
        elif self in (Role.TANNER, Role.ARSONIST, Role.HUMAN_HUNTER):
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
            Role.SEER: "Mỗi đêm soi 1 người: Sói hay không thuộc bầy Sói; không xác định phe Solo/Dân.",
            Role.GUARD: "Bảo vệ 1 người khỏi đòn Sói và lửa; không chặn độc, lời nguyền hay chết theo. Không chọn trùng 2 đêm liền.",
            Role.WITCH: "Có 1 bình Cứu chặn đòn tấn công trực tiếp vào 1 người còn sống (không hồi sinh), và 1 bình Độc; mỗi bình dùng 1 lần/ván. Xác nhận dùng cứu vẫn mất bình dù mục tiêu không bị tấn công.",
            Role.CUPID: "Đêm 1 ghép 2 Tình Nhân: 1 người chết thì người kia chết theo. Cặp khác mục tiêu lúc ghép phải sống sót cuối cùng cùng nhau, cả hai tính rank Solo. Cặp cùng mục tiêu giữ mục tiêu gốc. Kẻ Ngốc bị treo cổ vẫn thắng ngay.",
            Role.HUNTER: "Khi chết bởi bất kỳ nguyên nhân nào, được bắn 1 người còn sống, kể cả chết do độc hoặc tình nhân. Ngoại lệ: ván kết thúc ngay khi Kẻ Ngốc bị treo cổ.",
            Role.TANNER: "Bạn thuộc phe Độc Lập. Bạn THẮNG NGAY LẬP TỨC nếu bị dân làng treo cổ ban ngày!",
            Role.MAYOR: "Phiếu bầu ban ngày tính x2. Khi qua đời, bạn được chỉ định 1 người kế nhiệm làm Thị Trưởng mới!",
            Role.WOLF_SEER: "Mỗi đêm cùng bầy Sói cắn người và được soi 1 người để biết chính xác vai trò của họ!",
            Role.WOLF_GUARD: "Mỗi đêm chọn một người được che chở khỏi kỹ năng giết của Dân và treo cổ trong ngày và đêm kế tiếp. Sau một lần cứu thành công, mất khả năng bảo vệ.",
            Role.CURSED: "Ban đầu là Dân. Nếu bị Sói cắn ban đêm, bạn không chết mà biến thành Sói từ đêm sau!",
            Role.ELDER: "Có 2 mạng trước đòn cắn của Sói (lần 1 bị cắn không chết). Tuy nhiên bị treo cổ/độc sẽ chết ngay!",
            Role.SERIAL_KILLER: "Thuộc phe Độc Lập. Mỗi đêm giết 1 người, miễn nhiễm đòn cắn của Sói. Thắng khi sống sót duy nhất, trừ mục tiêu Tình Nhân khác phe!",
            Role.WOLF_CUB: "Khi chết bởi bất kỳ nguyên nhân nào, bầy Sói sẽ phẫn nộ và được cắn liền 2 người ở đêm tiếp theo!",
            Role.HARLOT: "Kĩ Nữ ghé thăm 1 người mỗi đêm hoặc ở nhà. Khi vắng nhà, đòn tấn công nhắm vào bạn hụt; bạn chết nếu ghé thăm Sói/Kẻ Phóng Hỏa hoặc người thực sự bị giết đêm đó.",
            Role.APPRENTICE_SEER: "Ban đầu chưa có kỹ năng. Khi Tiên Tri chính qua đời, bạn sẽ kế thừa làm Tiên Tri mới từ đêm tiếp theo!",
            Role.LYCAN: "Thuộc phe Dân, nhưng Tiên Tri nhận diện bạn là Sói. Thám Tử so phe thật: Dân.",
            Role.INVESTIGATOR: "Mỗi đêm chọn đúng 2 người để biết họ cùng hay khác phe thật (Dân, Sói, Solo). Không tiết lộ phe cụ thể.",
            Role.WHITE_WOLF: "Ở trong bầy Sói nhưng mục tiêu và rank Solo. Đêm chẵn được cắn thêm 1 Sói. Thắng khi sống sót duy nhất, trừ mục tiêu Tình Nhân khác phe.",
            Role.PHANTOM_WOLF: "Mỗi đêm chọn 1 người không thuộc bầy Sói để 'giả dạng'. Nếu Tiên Tri soi người đó trong đêm đó, kết quả trả về là 'SÓI'.",
            Role.MUTE_WOLF: "Thuộc Phe Sói. Ban ngày không được phép chat, chỉ được bỏ phiếu — tạo áp lực tâm lý và nghi ngờ cho dân làng!",
            Role.THE_GIRL: "Mỗi đêm có thể 'nhìn trộm' để xem bầy Sói đang cắn ai. Nhưng nếu bị phát hiện (50% cơ hội) — chết ngay đêm đó!",
            Role.RUSTY_KNIGHT: "Nếu bị Sói cắn chết, đêm kế tiếp 1 con Sói ngẫu nhiên sẽ bị 'lời nguyền' hạ gục. Cái chết có giá trị!",
            Role.PIPER: "Phe Solo. Mê hoặc đúng 2 người mỗi đêm (1 nếu chỉ còn 1 người khác). Thắng khi mọi người còn sống trừ bản thân đều bị mê hoặc, trừ mục tiêu Tình Nhân khác phe.",
            Role.SCAPEGOAT: "Tự bị treo cổ khi hòa phiếu cao nhất giữa các ứng viên. Nếu phiếu trắng cao nhất hoặc hòa cao nhất thì không ai bị treo cổ.",
            Role.ALPHA_WOLF: "Vai trò cũ đã ngừng hỗ trợ; chỉ giữ để đọc lịch sử ván đấu.",
            Role.ARSONIST: "Phe Solo. Mỗi đêm tẩm xăng 2 người khác (1 nếu chỉ còn 1 mục tiêu; xuyên bảo vệ) hoặc thiêu toàn bộ người đang dính xăng. Lửa có thể được bảo vệ/cứu. Thắng khi là người sống cuối cùng.",
            Role.HUMAN_HUNTER: "Phe Solo. Được giao 1 mục tiêu Dân lúc bắt đầu; nếu người đó bị treo cổ khi bạn còn sống, bạn thắng cá nhân nhưng ván vẫn tiếp diễn. Nếu mục tiêu chết cách khác, bạn chuyển sang phe Sói.",
            Role.DOCTOR: "Mỗi đêm cứu 1 người khác khỏi các đòn giết trực tiếp, kể cả lửa/độc/lời nguyền. Không tự cứu; tối đa 2 lần cứu cùng một người trong ván. Không cứu chết theo hay Kĩ Nữ thăm nhầm.",
            Role.YOUNG_WOLF: "Thuộc bầy Sói. Khi chết, được chọn 1 người không thuộc bầy Sói còn sống chết theo.",
            Role.GUNNER: "Phe Dân. Có 2 viên đạn, bắn tối đa 1 người mỗi ngày trong giờ thảo luận từ Ngày 2. Vai trò lộ ra sau phát bắn đầu.",
            Role.FORENSIC: "Mỗi đêm chọn một người chết đêm trước. Nhận 2 nghi phạm có thể đã giết họ; nếu hung thủ thuộc phe Solo, nhận 3 nghi phạm.",
            Role.STRONGMAN: "Mỗi đêm bảo vệ một người khác. Nếu bạn hoặc người đó bị tấn công, cả hai sống sót và bạn cùng kẻ tấn công biết vai trò của nhau. Bạn chết khi đêm kế tiếp bắt đầu.",
            Role.PRIEST: "Mỗi ván một lần, vẩy nước thánh lên một người: nếu họ là Sói, họ chết; nếu không, bạn chết.",
            Role.BIGMOUTH: "Mỗi đêm chọn một người (có thể đổi lựa chọn). Khi bạn chết, vai trò người đó được công khai.",
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
    ARSONIST = "Kẻ Phóng Hỏa 🔥"
    HUMAN_HUNTER = "Thợ Săn Người 🎯"
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
    """Night cards; obsolete role-specific names remain readable in old replays."""
    BLOOD_MOON = "Trăng Máu 🩸"
    DENSE_FOG = "Sương Mù Dày Đặc 🌫️"
    SOLAR_ECLIPSE = "Nhật Thực ☀️"
    SEAL_NIGHT = "Phong Ấn Dược Liệu 🧪"
    HOLY_LIGHT = "Thánh Quang Bảo Hộ 🛡️"
    THUNDERSTORM = "Bão Sấm Sét 🌩️"
    WANING_MOON = "Trăng Khuyết 🌘"
    SILENT_NIGHT = "Đêm Câm Lặng 🔇"

    @property
    def description(self) -> str:
        return {
            NightEvent.BLOOD_MOON: "🩸 Bầy Sói có thể cắn **2 người** trong đêm nay.",
            NightEvent.DENSE_FOG: "🌫️ Kết quả của Tiên Tri và Thám Tử có **50% khả năng không xác định được**.",
            NightEvent.SOLAR_ECLIPSE: "☀️ Sau đêm này vẫn thảo luận, nhưng **không bỏ phiếu treo cổ**.",
            NightEvent.SEAL_NIGHT: "🧪 Phù Thủy **không dùng được bình cứu hoặc bình độc** đêm nay; không mất bình.",
            NightEvent.HOLY_LIGHT: "🛡️ Mọi đòn cắn của bầy Sói đêm nay bị chặn; các đòn giết khác vẫn có hiệu lực.",
            NightEvent.SILENT_NIGHT: "🔇 Thảo luận ngày kế tiếp rút xuống tối đa **30 giây**.",
        }.get(self, "Thẻ cũ chỉ xuất hiện trong lịch sử ván đấu.")


class ActionKind(Enum):
    GUARD = "guard"
    WOLF_GUARD = "wolf_guard"
    FORENSIC = "forensic"
    STRONGMAN = "strongman"
    HOLY_WATER = "holy_water"
    BIGMOUTH = "bigmouth"
    DOCTOR = "doctor"
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
    ARSON_DOUSE = "arson_douse"
    ARSON_IGNITE = "arson_ignite"


RETIRED_ROLES = frozenset({
    Role.WHITE_WOLF, Role.PIPER, Role.THE_GIRL,
    Role.SERIAL_KILLER, Role.MUTE_WOLF, Role.ALPHA_WOLF,
})

MASOI_MIN_PLAYER_COUNT = 8
MASOI_MAX_PLAYER_COUNT = 16
MASOI_PLAYER_COUNT = 16  # Special fixed roster is used only at exactly 16 players.


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
        self.enable_events: bool = False  # Thẻ sự kiện đêm; độc lập với Boss đã gỡ.
        self.role_setup_mode: str = "AUTO"  # AUTO / CUSTOM
        self.custom_wolf_count: int = 2
        self.custom_special_roles: List[str] = []

    def cycle_reveal_roles(self):
        self.reveal_roles_on_death = not self.reveal_roles_on_death

    @property
    def tanner_enabled(self) -> bool:
        return isinstance(self.custom_special_roles, list) and "TANNER" in self.custom_special_roles if self.role_setup_mode == "CUSTOM" else self.enable_tanner

    def cycle_tanner(self):
        enabled = not self.tanner_enabled
        if self.role_setup_mode == "CUSTOM":
            self.custom_special_roles = [name for name in self.custom_special_roles if name != "TANNER"]
            if enabled:
                self.custom_special_roles.append("TANNER")
        self.enable_tanner = enabled

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
            "role_setup_mode": self.role_setup_mode,
            "custom_wolf_count": self.custom_wolf_count,
            "custom_special_roles": list(self.custom_special_roles) if isinstance(self.custom_special_roles, list) else self.custom_special_roles,
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
        s.enable_events = bool(data.get("enable_events", False))
        s.role_setup_mode = data.get("role_setup_mode", "AUTO")
        s.custom_wolf_count = data.get("custom_wolf_count", 2)
        roles = data.get("custom_special_roles", [])
        # Retired Boss roles in old configurations cannot re-enable the removed mode.
        s.custom_special_roles = [name for name in roles if not isinstance(name, str) or name not in {role.name for role in RETIRED_ROLES}] if isinstance(roles, list) else roles
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
        self.lover_objective: Optional[bool] = None  # Frozen when paired; None for legacy data.
        self.lover_id: Optional[int] = None  # user_id tình nhân (Thần tình yêu ghép đôi)
        self.hunter_shot_used: bool = False  # Thợ săn đã dùng phát bắn kéo theo chưa
        self.is_cursed_converted: bool = False  # Kẻ Bị Nguyền đã biến thành Sói chưa
        self.cursed_notified: bool = False  # Đã gửi DM thông báo biến thành Sói chưa
        self.elder_lives: int = 2  # Già Làng có 2 mạng trước đòn cắn của Sói
        self.is_roleblocked: bool = False  # Bị Vũ Nữ phong tỏa kỹ năng đêm
        self.apprentice_promoted: bool = False  # Tiên Tri Tập Sự đã kế thừa vị trí Tiên Tri
        self.rusty_knight_curse_triggered: bool = False  # Hiệp Sĩ đã kích hoạt nguyền chưa
        self.piper_charmed: bool = False  # Bị Người Thổi Sáo mê hoặc
        self.is_doused: bool = False
        self.doctor_protection_count: int = 0
        self.gunner_bullets_used: int = 0
        self.gunner_last_shot_day: int = 0
        self.wolf_guard_used: bool = False
        self.wolf_guard_shield_owner_id: Optional[int] = None
        self.wolf_guard_shield_day: int = 0
        self.wolf_guard_shield_night: int = 0
        self.holy_water_used: bool = False
        self.bigmouth_target_id: Optional[int] = None
        self.strongman_target_id: Optional[int] = None
        self.strongman_injured: bool = False
        self.strongman_death_night: int = 0
        self.last_death_source: str = ""
        self.last_death_night: int = 0
        self.human_hunter_target_id: Optional[int] = None
        self.human_hunter_succeeded: bool = False
        self.human_hunter_joined_wolves: bool = False
        self.human_hunter_notified_state: str = ""

        # Metrics cho rank bonus
        self.seer_found_wolf: bool = False
        self.guard_saved_count: int = 0
        self.witch_useful_use_count: int = 0

    @property
    def is_wolf(self) -> bool:
        return self.role in (Role.WOLF, Role.WOLF_SEER, Role.WOLF_GUARD, Role.WOLF_CUB, Role.WHITE_WOLF, Role.PHANTOM_WOLF, Role.MUTE_WOLF, Role.ALPHA_WOLF, Role.YOUNG_WOLF) or self.is_cursed_converted or self.human_hunter_joined_wolves


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
        self._auto_role_pool: Optional[List[Role]] = None

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
        self.night_wolf_guard_target: Optional[int] = None
        self.night_strongman_target: Optional[int] = None
        self.night_doctor_target: Optional[int] = None
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
        self.night_forensic_result: Optional[str] = None
        self.night_forensic_dm_message: Optional[any] = None
        self.night_priest_result: Optional[str] = None
        self.night_strongman_reveals: List[Tuple[int, int]] = []
        self.night_start_deaths: Tuple[int, ...] = ()
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
        self.current_night_event: Optional[NightEvent] = None

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

    @property
    def active_night_event(self) -> Optional[NightEvent]:
        return self.current_night_event if self.settings.enable_events else None

    def eligible_night_events(self) -> List[NightEvent]:
        """Do not draw a card without an effect in the current roster."""
        alive = self.get_alive_players()
        cards = [NightEvent.SILENT_NIGHT]
        if any(p.is_wolf for p in alive):
            cards.append(NightEvent.HOLY_LIGHT)
        if len(alive) >= 10 and any(p.is_wolf for p in alive) and sum(not p.is_wolf for p in alive) >= 2:
            cards.append(NightEvent.BLOOD_MOON)
        if len(alive) >= 8 and self.night_count >= 2:
            cards.append(NightEvent.SOLAR_ECLIPSE)
        if any(p.role == Role.SEER or p.role == Role.INVESTIGATOR or
               (p.role == Role.APPRENTICE_SEER and p.apprentice_promoted) for p in alive):
            cards.append(NightEvent.DENSE_FOG)
        if any(p.role == Role.WITCH and (not p.witch_save_used or not p.witch_poison_used) for p in alive):
            cards.append(NightEvent.SEAL_NIGHT)
        return cards

    def add_player(self, user_id: int, display_name: str) -> bool:
        if self.phase != GamePhase.LOBBY:
            return False
        if user_id in self.players:
            return False
        if len(self.players) >= MASOI_MAX_PLAYER_COUNT:
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
        errors = self.validate_role_setup()
        if errors:
            raise ValueError(" ".join(errors))
        user_ids = list(self.players.keys())
        random.shuffle(user_ids)
        n = len(user_ids)

        role_pool = self.preview_roles()[:n]
        random.shuffle(role_pool)

        for uid, role in zip(user_ids, role_pool):
            self.players[uid].role = role
            if role == Role.MAYOR:
                self.mayor_id = uid
        hunter = self.get_player_by_role(Role.HUMAN_HUNTER)
        if hunter:
            candidates = [p.user_id for p in self.players.values() if p.role.faction == Faction.VILLAGER]
            if not candidates:
                raise ValueError("Thợ Săn Người cần ít nhất 1 mục tiêu Dân.")
            hunter.human_hunter_target_id = random.choice(candidates)

    def validate_role_setup(self) -> List[str]:
        """Return configuration errors that would create an unwinnable or invalid setup."""
        n = len(self.players)
        errors: List[str] = []
        if n < MASOI_MIN_PLAYER_COUNT:
            errors.append(f"Cần ít nhất {MASOI_MIN_PLAYER_COUNT} người chơi để bắt đầu.")
            return errors
        if n > MASOI_MAX_PLAYER_COUNT:
            errors.append(f"Phòng chỉ nhận tối đa {MASOI_MAX_PLAYER_COUNT} người chơi.")
            return errors

        # Exactly 16 players use the requested fixed roster, regardless of lobby role settings.
        if n == MASOI_PLAYER_COUNT:
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
        if any(role in (Role.WOLF, Role.VILLAGER) or role in RETIRED_ROLES for role in special_roles):
            errors.append("Cấu hình chứa vai trò thường hoặc vai trò đã ngừng hỗ trợ.")

        total_roles = wolf_count + len(special_roles)
        if total_roles > n:
            errors.append(f"Cấu hình có {total_roles} vai trò cho {n} người; hãy bỏ bớt vai trò đặc biệt hoặc giảm số Sói.")

        wolves = wolf_count + sum(role.faction == Faction.WEREWOLF for role in special_roles)
        if wolves >= n - wolves:
            errors.append("Số Sói phải ít hơn số người không thuộc phe Sói khi bắt đầu.")
        max_wolves = 1 if n <= 6 else 2 if n <= 11 else 3 if n <= 14 else 4
        if wolves > max_wolves:
            errors.append(f"Bàn {n} người có tối đa {max_wolves} Sói để giữ cân bằng.")
        if Role.WOLF_CUB in special_roles and Role.YOUNG_WOLF in special_roles:
            errors.append("Sói Cuồng Sát và Sói Trẻ không được xuất hiện cùng ván.")
        minimums = {Role.YOUNG_WOLF: 7, Role.ARSONIST: 10, Role.HUMAN_HUNTER: 9, Role.GUNNER: 9}
        for role, minimum in minimums.items():
            if role in special_roles and n < minimum:
                errors.append(f"{role.value} cần tối thiểu {minimum} người chơi.")
        if Role.HUMAN_HUNTER in special_roles and n - total_roles < 1 and not any(role.faction == Faction.VILLAGER for role in special_roles):
            errors.append("Thợ Săn Người cần ít nhất 1 mục tiêu Dân.")
        return errors

    def preview_roles(self) -> List[Role]:
        """Use the fixed requested lineup at 16; retain the original lineup otherwise."""
        n = max(MASOI_MIN_PLAYER_COUNT, len(self.players))
        if n == MASOI_PLAYER_COUNT:
            if self._auto_role_pool is None:
                self._auto_role_pool = [
                    Role.WOLF, Role.WOLF_SEER, Role.WOLF_GUARD,
                    random.choice((Role.WOLF_CUB, Role.YOUNG_WOLF, Role.PHANTOM_WOLF)),
                    *random.sample((Role.GUARD, Role.DOCTOR, Role.STRONGMAN), 2),
                    *random.sample((Role.INVESTIGATOR, Role.SEER, Role.FORENSIC), 2),
                    random.choice((Role.HARLOT, Role.APPRENTICE_SEER)),
                    *random.sample((Role.WITCH, Role.HUNTER, Role.GUNNER, Role.PRIEST), 2),
                    Role.ARSONIST, random.choice((Role.TANNER, Role.HUMAN_HUNTER)),
                    *random.sample((Role.SCAPEGOAT, Role.ELDER, Role.CUPID, Role.MAYOR, Role.LYCAN, Role.BIGMOUTH), 3),
                ]
            return list(self._auto_role_pool)

        if self.settings.role_setup_mode == "CUSTOM":
            wolf_count = self.settings.custom_wolf_count if type(self.settings.custom_wolf_count) is int else 1
            role_pool: List[Role] = [Role.WOLF] * max(1, min(n, wolf_count))
            for role_name in self.settings.custom_special_roles if isinstance(self.settings.custom_special_roles, list) else []:
                try:
                    role = Role[role_name]
                    if len(role_pool) < n and role not in RETIRED_ROLES:
                        role_pool.append(role)
                except (KeyError, TypeError):
                    pass
        elif n <= 6:
            role_pool = [Role.WOLF, Role.SEER, Role.GUARD, Role.MAYOR]
        elif n <= 9:
            role_pool = [Role.WOLF, Role.WOLF, Role.SEER, Role.GUARD, Role.WITCH, Role.MAYOR, Role.CURSED]
        elif n <= 12:
            role_pool = [Role.WOLF, Role.WOLF_SEER, Role.MAYOR, Role.SEER, Role.DOCTOR, Role.WITCH, Role.HUNTER, Role.CURSED, Role.HARLOT]
            if n >= 12:
                role_pool.extend((Role.YOUNG_WOLF, Role.ELDER))
        else:
            role_pool = [Role.WOLF, Role.YOUNG_WOLF, Role.WOLF_SEER, Role.MAYOR, Role.INVESTIGATOR, Role.DOCTOR, Role.WITCH, Role.HUNTER, Role.CURSED, Role.ELDER, Role.HARLOT, Role.ARSONIST]
            if n >= 15:
                role_pool.extend((Role.WOLF, Role.GUNNER))
            if n >= 17:
                role_pool.append(Role.HUMAN_HUNTER)

        if self.settings.tanner_enabled and Role.TANNER not in role_pool and len(role_pool) < n:
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
        self.night_wolf_guard_target = None
        self.night_doctor_target = None
        self.night_wolf_votes.clear()
        self.night_resolved_wolf_targets = []
        self.night_seer_target = None
        self.night_seer_actor_id = None
        self.night_seer_result = None
        self.night_forensic_result = None
        self.night_forensic_dm_message = None
        self.night_priest_result = None
        self.night_strongman_reveals = []
        self.night_start_deaths = ()
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

        previous_event = self.current_night_event
        self.current_night_event = None
        if self.settings.enable_events:
            cards = self.eligible_night_events()
            if previous_event in cards and len(cards) > 1:
                cards.remove(previous_event)
            self.current_night_event = random.choice(cards)
            self.record_log("NIGHT_EVENT", result=f"Thẻ Sự Kiện: {self.current_night_event.value} — {self.current_night_event.description}")
        self.wolf_fury_active = self.wolf_fury_pending or self.active_night_event == NightEvent.BLOOD_MOON
        self.wolf_fury_pending = False

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
        expiring_injuries = [
            player.user_id for player in self.players.values()
            if player.is_alive and player.strongman_injured and player.strongman_death_night <= self.night_count
        ]
        for uid in expiring_injuries:
            self.players[uid].strongman_injured = False
        self.night_start_deaths = self.apply_deaths(expiring_injuries, "STRONGMAN_INJURY_DEATH") if expiring_injuries else ()

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

    def required_target_count(self, kind: ActionKind) -> int:
        if kind in (ActionKind.GIRL, ActionKind.ARSON_IGNITE):
            return 0
        if kind == ActionKind.CUPID:
            return 2
        if kind == ActionKind.ARSON_DOUSE:
            return min(2, max(0, len(self.get_alive_players()) - 1))
        if kind == ActionKind.INVESTIGATE:
            return 2
        if kind == ActionKind.PIPER:
            return min(2, max(0, len(self.get_alive_players()) - 1))
        return 1

    def submit_night_action(self, intent: ActionIntent):
        """Validate synchronously before storing; never apply gameplay effects here."""
        if not self.accepts_night_actions(intent.night):
            raise ValueError("Lượt đêm đã hết hạn hoặc đã được khóa.")
        actor = self.players.get(intent.actor_id)
        if not actor or not actor.is_alive:
            raise ValueError("Bạn không còn quyền hành động trong ván này.")
        roles = {
            ActionKind.GUARD: Role.GUARD, ActionKind.WOLF_GUARD: Role.WOLF_GUARD,
            ActionKind.FORENSIC: Role.FORENSIC, ActionKind.STRONGMAN: Role.STRONGMAN,
            ActionKind.HOLY_WATER: Role.PRIEST, ActionKind.BIGMOUTH: Role.BIGMOUTH,
            ActionKind.DOCTOR: Role.DOCTOR, ActionKind.SEER: Role.SEER,
            ActionKind.HARLOT: Role.HARLOT, ActionKind.INVESTIGATE: Role.INVESTIGATOR,
            ActionKind.WOLF_SEER: Role.WOLF_SEER, ActionKind.SERIAL_KILL: Role.SERIAL_KILLER,
            ActionKind.WHITE_WOLF: Role.WHITE_WOLF, ActionKind.PHANTOM: Role.PHANTOM_WOLF,
            ActionKind.GIRL: Role.THE_GIRL, ActionKind.PIPER: Role.PIPER,
            ActionKind.CUPID: Role.CUPID,
            ActionKind.WITCH_SAVE: Role.WITCH, ActionKind.WITCH_POISON: Role.WITCH,
            ActionKind.ARSON_DOUSE: Role.ARSONIST, ActionKind.ARSON_IGNITE: Role.ARSONIST,
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
        if intent.kind == ActionKind.WOLF_GUARD and actor.wolf_guard_used:
            raise ValueError("Ác Sói đã cứu thành công một người và hết khả năng bảo vệ.")
        if intent.kind == ActionKind.HOLY_WATER and actor.holy_water_used:
            raise ValueError("Mục Sư đã dùng nước thánh trong ván này.")
        key = (intent.actor_id, intent.kind)
        if key in self._night_intents:
            raise ValueError("Bạn đã xác nhận kỹ năng này trong đêm.")
        targets = intent.targets
        if not isinstance(targets, tuple) or len(set(targets)) != len(targets):
            raise ValueError("Danh sách mục tiêu không hợp lệ.")
        expected = self.required_target_count(intent.kind)
        optional = intent.kind in (
            ActionKind.WHITE_WOLF, ActionKind.WITCH_SAVE, ActionKind.WITCH_POISON, ActionKind.HARLOT,
        )
        if len(targets) != expected and not (optional and not targets):
            raise ValueError("Số lượng mục tiêu không hợp lệ.")
        for uid in targets:
            target = self.players.get(uid)
            if not target:
                raise ValueError("Mục tiêu không tồn tại trong ván.")
            if intent.kind == ActionKind.FORENSIC:
                if (target.is_alive or target.last_death_night != self.night_count - 1
                        or target.last_death_source not in {"wolf", "white_wolf", "serial_killer", "arson"}):
                    raise ValueError("Pháp Y chỉ được chọn người chết đêm trước bởi Sói hoặc Solo.")
            elif not target.is_alive:
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
        if intent.kind == ActionKind.DOCTOR and self.players[targets[0]].doctor_protection_count >= 2:
            raise ValueError("Bác Sĩ đã cứu người này tối đa 2 đêm trong ván.")
        if intent.kind in (ActionKind.ARSON_DOUSE, ActionKind.ARSON_IGNITE):
            other = ActionKind.ARSON_IGNITE if intent.kind == ActionKind.ARSON_DOUSE else ActionKind.ARSON_DOUSE
            if (intent.actor_id, other) in self._night_intents:
                raise ValueError("Mỗi đêm chỉ được tẩm xăng hoặc châm lửa.")
            if intent.kind == ActionKind.ARSON_IGNITE and not any(p.is_alive and p.is_doused for p in self.players.values()):
                raise ValueError("Chưa có người sống nào bị tẩm xăng.")
        if intent.kind == ActionKind.CUPID and self.night_count != 1:
            raise ValueError("Thần Tình Yêu chỉ ghép đôi trong đêm đầu.")
        if intent.kind == ActionKind.WHITE_WOLF and self.night_count % 2:
            raise ValueError("Sói Trắng không thể cắn thêm trong đêm này.")
        if intent.kind in (ActionKind.WITCH_SAVE, ActionKind.WITCH_POISON):
            if self.active_night_event == NightEvent.SEAL_NIGHT:
                raise ValueError("Thẻ Phong Ấn Dược Liệu khóa bình thuốc đêm nay.")
            used = actor.witch_save_used if intent.kind == ActionKind.WITCH_SAVE else actor.witch_poison_used
            if targets and used:
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
        direct_victims = set(pending)
        died = set()
        while pending:
            uid = min(pending)
            pending.remove(uid)
            player = self.players.get(uid)
            if not player or not player.is_alive:
                continue
            source = {
                "DAY_DEATH": "execution", "HUNTER_DEATH": "hunter",
                "GUNNER_DEATH": "gunner",
            }.get(event_type)
            if uid in direct_victims and source and self.consume_wolf_guard_shield(uid, source):
                continue
            player.is_alive = False
            died.add(uid)
            self.record_log(event_type, target_id=uid, result="Người chơi qua đời")
            if player.role == Role.BIGMOUTH and player.bigmouth_target_id in self.players:
                target = self.players[player.bigmouth_target_id]
                self.record_log(
                    "BIGMOUTH_REVEAL", actor_id=uid, target_id=target.user_id,
                    result=f"Cậu Bé Mồm To tiết lộ: {target.display_name} là {target.role.value}.",
                )
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
        for hunter in self.players.values():
            if hunter.role != Role.HUMAN_HUNTER or not hunter.is_alive or hunter.human_hunter_succeeded or hunter.human_hunter_joined_wolves:
                continue
            if hunter.human_hunter_target_id in died:
                if event_type == "DAY_DEATH" and hunter.human_hunter_target_id in set(victims):
                    hunter.human_hunter_succeeded = True
                    self.record_log("HUMAN_HUNTER_SUCCESS", actor_id=hunter.user_id, target_id=hunter.human_hunter_target_id, result="Mục tiêu bị treo cổ; thắng cá nhân")
                else:
                    hunter.human_hunter_joined_wolves = True
                    self.record_log("HUMAN_HUNTER_CONVERT", actor_id=hunter.user_id, result="Mục tiêu chết cách khác; gia nhập phe Sói")
        return tuple(sorted(died))

    def consume_wolf_guard_shield(self, target_id: int, source: str) -> bool:
        if source not in {"execution", "hunter", "gunner", "poison", "curse", "holy_water"}:
            return False
        target = self.players[target_id]
        owner = self.players.get(target.wolf_guard_shield_owner_id)
        if not owner or owner.wolf_guard_used:
            return False
        day_active = source in {"execution", "hunter", "gunner"} and self.day_count == target.wolf_guard_shield_day
        night_active = source in {"poison", "curse", "holy_water"} and self.night_count == target.wolf_guard_shield_night
        if not (day_active or night_active):
            return False
        owner.wolf_guard_used = True
        for player in self.players.values():
            if player.wolf_guard_shield_owner_id == owner.user_id:
                player.wolf_guard_shield_owner_id = None
                player.wolf_guard_shield_day = 0
                player.wolf_guard_shield_night = 0
        self.record_log("WOLF_GUARD_SAVE", actor_id=owner.user_id, target_id=target_id, result=f"Ác Sói chặn {source} và mất kỹ năng bảo vệ")
        return True

    def _damage(self, target_id: int, source: str, deaths: Set[int]):
        if target_id in deaths or self.consume_wolf_guard_shield(target_id, source):
            return
        deaths.add(target_id)
        target = self.players.get(target_id)
        if target:
            target.last_death_source = source
            target.last_death_night = self.night_count

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

    def resolve_young_wolf_revenge(self, wolf_id: int, target_id: int) -> Tuple[int, ...]:
        wolf, target = self.players.get(wolf_id), self.players.get(target_id)
        if not wolf or wolf.role != Role.YOUNG_WOLF or wolf.is_alive or wolf.hunter_shot_used:
            raise ValueError("Sói Trẻ chưa được phép kéo theo.")
        if not target or not target.is_alive or target.is_wolf or self.phase == GamePhase.GAME_END:
            raise ValueError("Chỉ được kéo theo người còn sống ngoài bầy Sói.")
        wolf.hunter_shot_used = True
        self.record_log("YOUNG_WOLF_REVENGE", actor_id=wolf_id, target_id=target_id, result="Sói Trẻ kéo theo")
        return self.apply_deaths((target_id,), "YOUNG_WOLF_DEATH")

    def resolve_gunner_shot(self, gunner_id: int, target_id: int) -> Tuple[int, ...]:
        gunner, target = self.players.get(gunner_id), self.players.get(target_id)
        if not gunner or gunner.role != Role.GUNNER or not gunner.is_alive:
            raise ValueError("Bạn không phải Xạ Thủ còn sống.")
        if self.phase != GamePhase.DAY_DISCUSSION or self.day_count < 2 or gunner.gunner_bullets_used >= 2 or gunner.gunner_last_shot_day == self.day_count:
            raise ValueError("Không thể bắn trong lượt này.")
        if not target or not target.is_alive or target_id == gunner_id:
            raise ValueError("Mục tiêu bắn không hợp lệ.")
        gunner.gunner_bullets_used += 1
        gunner.gunner_last_shot_day = self.day_count
        self.record_log("GUNNER_SHOT", actor_id=gunner_id, target_id=target_id, result="Xạ Thủ bắn công khai")
        return self.apply_deaths((target_id,), "GUNNER_DEATH")

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
            if kind in (ActionKind.WITCH_SAVE, ActionKind.WITCH_POISON) and self.active_night_event == NightEvent.SEAL_NIGHT:
                return None
            return a if a and a.actor_id in alive and not alive[a.actor_id].is_roleblocked else None
        def project(kind, attr):
            a = active(kind)
            setattr(self, attr, a.targets[0] if a and a.targets else None)
            return a

        visit = project(ActionKind.HARLOT, "night_harlot_target")
        if visit and visit.targets:
            self.record_log("HARLOT_VISIT", actor_id=visit.actor_id, target_id=visit.targets[0], result="Kĩ Nữ ghé thăm")
        guard = project(ActionKind.GUARD, "night_guard_target")
        if guard:
            alive[guard.actor_id].protected_last_night = guard.targets[0]
        wolf_guard = active(ActionKind.WOLF_GUARD)
        self.night_wolf_guard_target = wolf_guard.targets[0] if wolf_guard else None
        strongman = active(ActionKind.STRONGMAN)
        self.night_strongman_target = strongman.targets[0] if strongman else None
        forensic = active(ActionKind.FORENSIC)
        bigmouth = active(ActionKind.BIGMOUTH)
        priest = active(ActionKind.HOLY_WATER)
        if bigmouth:
            alive[bigmouth.actor_id].bigmouth_target_id = bigmouth.targets[0]
        if priest:
            alive[priest.actor_id].holy_water_used = True
        doctor = project(ActionKind.DOCTOR, "night_doctor_target")
        if doctor:
            alive[doctor.targets[0]].doctor_protection_count += 1
        cupid = active(ActionKind.CUPID)
        if cupid:
            one, two = (alive[uid] for uid in cupid.targets)
            one.lover_id, two.lover_id = two.user_id, one.user_id
            mixed = self.personal_objective(one) != self.personal_objective(two)
            one.lover_objective = two.lover_objective = mixed
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
            self.girl_caught = rng.random() < 0.5
            self.girl_result = "😱 Bạn bị phát hiện và sẽ chết đêm nay!" if self.girl_caught else "👀 Nhìn trộm thành công."
        elif action(ActionKind.GIRL):
            self.girl_result = "❌ Kỹ năng nhìn trộm đã bị phong tỏa đêm nay."

        wolf_targets = self.resolve_wolf_targets(include_fury=True, rng=rng)
        self.night_resolved_wolf_targets = list(wolf_targets)
        if girl and not self.girl_caught:
            names = ", ".join(f"**{alive[uid].display_name}**" for uid in wolf_targets)
            self.girl_result += f" Bầy Sói nhắm vào {names}." if names else " Bầy Sói không chọn được mục tiêu."
        if self.girl_result:
            self.record_log("GIRL_PEEK", actor_id=action(ActionKind.GIRL).actor_id, result=self.girl_result)
        self.night_wolf_votes = {a.actor_id: a.targets[0] for a in actions if a.kind == ActionKind.WOLF_VOTE}
        sk = project(ActionKind.SERIAL_KILL, "night_serial_killer_target")
        white = project(ActionKind.WHITE_WOLF, "night_white_wolf_target")
        douse = active(ActionKind.ARSON_DOUSE)
        ignite = active(ActionKind.ARSON_IGNITE)
        if douse:
            for uid in douse.targets:
                alive[uid].is_doused = True
                self.record_log("ARSON_DOUSE", actor_id=douse.actor_id, target_id=uid, result="Tẩm xăng xuyên bảo vệ")
        save = project(ActionKind.WITCH_SAVE, "night_witch_save_target")
        poison = project(ActionKind.WITCH_POISON, "night_witch_poison")
        # Recheck potion resources at commit, not just at submission.
        if save and (not save.targets or alive[save.actor_id].witch_save_used):
            save = None
        if poison and (not poison.targets or alive[poison.actor_id].witch_poison_used):
            poison = None
        if save:
            alive[save.actor_id].witch_save_used = True
        if poison:
            alive[poison.actor_id].witch_poison_used = True
        deaths: Set[int] = set()
        strongman_protected: Set[int] = set()
        strongman_triggered = False

        def strongman_intercepts(target_id: int, attacker_id: Optional[int], source: str) -> bool:
            nonlocal strongman_triggered
            if not strongman:
                return False
            pair = {strongman.actor_id, strongman.targets[0]}
            if target_id in strongman_protected:
                return True
            if strongman_triggered or target_id not in pair:
                return False
            strongman_triggered = True
            strongman_protected.update(pair)
            guard_player = self.players[strongman.actor_id]
            guard_player.strongman_injured = True
            guard_player.strongman_death_night = self.night_count + 1
            if attacker_id and attacker_id in self.players:
                self.night_strongman_reveals.append((strongman.actor_id, attacker_id))
            self.record_log(
                "STRONGMAN_INTERCEPT", actor_id=strongman.actor_id, target_id=target_id,
                result=f"Lực Sĩ chặn {source}; Lực Sĩ và người được bảo vệ sống sót",
            )
            return True

        if self.rusty_knight_curse_active:
            wolves = sorted(uid for uid, p in alive.items() if p.is_wolf)
            if wolves:
                uid = rng.choice(wolves)
                if doctor and uid == doctor.targets[0]:
                    self.record_log("DOCTOR_PROTECT", actor_id=doctor.actor_id, target_id=uid, result="Bác Sĩ chặn lời nguyền Hiệp Sĩ")
                elif strongman_intercepts(uid, None, "lời nguyền của Hiệp Sĩ"):
                    pass
                else:
                    self._damage(uid, "curse", deaths)
                    self.record_log("RUSTY_KNIGHT_CURSE", target_id=uid, result="Lời nguyền Hiệp Sĩ")
        attacks = [(uid, "wolf") for uid in wolf_targets]
        if sk and sk.targets:
            attacks.append((sk.targets[0], "serial_killer"))
        if white and white.targets:
            attacks.append((white.targets[0], "white_wolf"))
        if ignite:
            for uid, player in alive.items():
                if player.is_doused:
                    attacks.append((uid, "arson"))
                    player.is_doused = False
        if priest:
            holy_target = alive[priest.targets[0]]
            if holy_target.is_wolf:
                attacks.append((holy_target.user_id, "holy_water"))
                self.night_priest_result = f"✝️ **{holy_target.display_name}** thuộc bầy Sói. Nước thánh đã được vẩy lên họ."
            else:
                deaths.add(priest.actor_id)
                alive[priest.actor_id].last_death_source = "holy_water_fail"
                alive[priest.actor_id].last_death_night = self.night_count
                self.night_priest_result = "✝️ Mục tiêu không thuộc bầy Sói. Nước thánh đã giết bạn."
                self.record_log("HOLY_WATER_FAIL", actor_id=priest.actor_id, target_id=holy_target.user_id, result="Mục Sư chọn nhầm dân làng và chết")
        saved_targets, protected_targets = set(), set()
        for uid, source in attacks:
            target = alive[uid]
            event = {"wolf": "WOLF_KILL", "serial_killer": "SERIAL_KILLER_KILL", "white_wolf": "WHITE_WOLF_BITE", "arson": "ARSON_IGNITE", "holy_water": "HOLY_WATER_KILL"}[source]
            wolf_attackers = sorted(a.actor_id for a in actions if a.kind == ActionKind.WOLF_VOTE and a.targets and a.targets[0] == uid)
            actor_id = sk.actor_id if source == "serial_killer" else white.actor_id if source == "white_wolf" else ignite.actor_id if source == "arson" else priest.actor_id if source == "holy_water" else wolf_attackers[0] if source == "wolf" and wolf_attackers else None
            self.record_log(event, actor_id=actor_id, target_id=uid, result="Tấn công đêm")
            if source == "wolf" and self.active_night_event == NightEvent.HOLY_LIGHT:
                self.record_log("HOLY_LIGHT_SAVED", target_id=uid, result="Thánh Quang chặn đòn cắn của bầy Sói")
                continue
            if visit and visit.targets and uid == visit.actor_id:
                self.record_log("HARLOT_AWAY", actor_id=uid, result="Kĩ Nữ vắng nhà, thoát đòn tấn công")
                continue
            if strongman_intercepts(uid, actor_id, source):
                continue
            if doctor and uid == doctor.targets[0]:
                protected_targets.add(uid)
                self.record_log("DOCTOR_PROTECT", actor_id=doctor.actor_id, target_id=uid, result="Bác Sĩ cứu mục tiêu")
                continue
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
            if doctor and uid == doctor.targets[0]:
                self.record_log("DOCTOR_PROTECT", actor_id=doctor.actor_id, target_id=uid, result="Bác Sĩ chặn độc")
            elif visit and visit.targets and uid == visit.actor_id:
                self.record_log("HARLOT_AWAY", actor_id=uid, result="Kĩ Nữ vắng nhà, thoát độc")
            elif strongman_intercepts(uid, poison.actor_id, "độc của Phù Thủy"):
                pass
            else:
                self._damage(uid, "poison", deaths)
            if alive[uid].is_wolf and uid in deaths:
                alive[poison.actor_id].witch_useful_use_count += 1
            self.record_log("WITCH_POISON", target_id=uid, result="Dùng bình độc")
        if self.girl_caught and girl:
            deaths.add(girl.actor_id)
            self.record_log("GIRL_CAUGHT", target_id=girl.actor_id, result="Cô Bé bị phát hiện khi nhìn trộm")
        if visit and visit.targets:
            visited = alive[visit.targets[0]]
            if visited.is_wolf or visited.role in (Role.ARSONIST, Role.SERIAL_KILLER) or visited.user_id in deaths:
                deaths.add(visit.actor_id)
                self.record_log("HARLOT_DANGER", actor_id=visit.actor_id, target_id=visited.user_id, result="Kĩ Nữ chết khi ghé thăm mục tiêu nguy hiểm")
        final_deaths = self.apply_deaths(deaths, "NIGHT_DEATH")
        if forensic:
            victim = self.players[forensic.targets[0]]
            suspect_count = 3 if victim.last_death_source in {"serial_killer", "arson"} else 2
            suspects = rng.sample([p for p in self.players.values() if p.user_id != victim.user_id], suspect_count)
            names = ", ".join(f"**{p.display_name}**" for p in suspects)
            self.night_forensic_result = f"🧬 Người đã giết **{victim.display_name}** có thể nằm trong số nghi phạm: {names}."
            self.record_log("FORENSIC_RESULT", actor_id=forensic.actor_id, target_id=victim.user_id, result=self.night_forensic_result)
        if wolf_guard and not alive[wolf_guard.actor_id].wolf_guard_used:
            for player in self.players.values():
                if player.wolf_guard_shield_owner_id == wolf_guard.actor_id:
                    player.wolf_guard_shield_owner_id = None
                    player.wolf_guard_shield_day = 0
                    player.wolf_guard_shield_night = 0
            protected = self.players[wolf_guard.targets[0]]
            if protected.is_alive:
                protected.wolf_guard_shield_owner_id = wolf_guard.actor_id
                protected.wolf_guard_shield_day = self.day_count + 1
                protected.wolf_guard_shield_night = self.night_count + 1
                self.record_log("WOLF_GUARD_SHIELD", actor_id=wolf_guard.actor_id, target_id=protected.user_id, result="Bảo vệ trong ngày và đêm kế tiếp")

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
                if self.active_night_event == NightEvent.DENSE_FOG and rng.random() < 0.5:
                    result = f"🌫️ Sương Mù che khuất **{target.display_name}**; không thể xác định kết quả đêm nay."
                elif target.is_wolf or target.role == Role.LYCAN or deceptive:
                    result = f"🐺 **{target.display_name}** là **SÓI**!"
                    if target.is_wolf:
                        actor.seer_found_wolf = True
                else:
                    result = f"👤 **{target.display_name}**: **KHÔNG THUỘC BẦY SÓI** (có thể là Dân hoặc Solo)."
            elif kind == ActionKind.INVESTIGATE:
                names = " & ".join(f"**{p.display_name}**" for p in targets)
                def alignment(p):
                    return RankFaction.WOLF if p.is_wolf else RankFaction.SOLO if p.role.faction != Faction.VILLAGER else RankFaction.VILLAGER
                if self.active_night_event == NightEvent.DENSE_FOG and rng.random() < 0.5:
                    result = f"🌫️ Sương Mù che khuất {names}; không thể xác định kết quả đêm nay."
                else:
                    result = f"👁️ {names} — **CÙNG PHE**" if alignment(targets[0]) == alignment(targets[1]) else f"👁️ {names} — **KHÁC PHE**"
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
        for kind, used_action in ((ActionKind.WITCH_SAVE, save), (ActionKind.WITCH_POISON, poison)):
            submitted = action(kind)
            if submitted:
                if alive[submitted.actor_id].is_roleblocked:
                    result = blocked + " Không mất bình."
                elif used_action:
                    result = "🧪 Đã dùng bình cứu." if kind == ActionKind.WITCH_SAVE else "☠️ Đã dùng bình độc."
                else:
                    result = "👌 Không dùng bình cứu." if kind == ActionKind.WITCH_SAVE else "👌 Không dùng bình độc."
                outcomes.append((submitted.actor_id, kind.value, result))
        self.night_deaths = list(final_deaths)
        self.record_log("NIGHT_RESOLVED", result=f"Đêm {self.night_count}; RNG seed={self.night_seed}")
        self._night_result = NightResult(
            self.night_count, self.night_seed, final_deaths, tuple(wolf_targets),
            tuple(outcomes),
            tuple(sorted(p.user_id for p in self.players.values() if p.role in (Role.HUNTER, Role.YOUNG_WOLF) and not p.is_alive and not p.hunter_shot_used)),
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
        """Tính phiếu bầu treo cổ ban ngày (Thị Trưởng vote x2). Trả về user_id bị xử tử (hoặc None nếu hòa phiếu)."""
        counts: Dict[Optional[int], int] = {}
        for voter_id, target_id in self.day_votes.items():
            if self.mayor_id and voter_id == self.mayor_id:
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

        self.apply_deaths((executed_id,), "DAY_DEATH")
        if self.players[executed_id].is_alive:
            self.record_log("DAY_EXECUTION_BLOCKED", target_id=executed_id, result="Ác Sói chặn treo cổ")
            return None
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

        if any(p.role in (Role.HUNTER, Role.YOUNG_WOLF) and not p.is_alive and not p.hunter_shot_used for p in self.players.values()):
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
        if len(alive_players) == 1 and alive_players[0].role == Role.ARSONIST:
            self.winner_faction = Faction.ARSONIST
            self.record_log("GAME_WIN", actor_id=alive_players[0].user_id, result="Kẻ Phóng Hỏa sống sót duy nhất")
            return Faction.ARSONIST
        if len(alive_players) == 2:
            p1, p2 = alive_players[0], alive_players[1]
            if self.has_lovers_objective(p1.user_id) and p1.lover_id == p2.user_id:
                self.winner_faction = Faction.LOVERS
                self.record_log("GAME_WIN", result="Phe Tình Nhân chiến thắng (cặp đôi sống sót cuối cùng)!")
                return Faction.LOVERS

        # Người Thổi Sáo thắng khi mê hoặc toàn bộ người sống (trừ bản thân)
        piper_alive_list = [p for p in alive_players if p.role == Role.PIPER and not self.has_lovers_objective(p.user_id)]
        if piper_alive_list:
            piper_check = piper_alive_list[0]
            other_alive = [p for p in alive_players if p.user_id != piper_check.user_id]
            if all(op.piper_charmed for op in other_alive):
                self.winner_faction = Faction.PIPER
                self.record_log("GAME_WIN", result="Người Thổi Sáo thắng — đã mê hoặc toàn bộ người chơi còn sống!")
                return Faction.PIPER

        # Sát Thủ Hàng Loạt độc chiếm chiến thắng
        sk_alive = [p for p in alive_players if p.role == Role.SERIAL_KILLER]
        arson_alive = [p for p in alive_players if p.role == Role.ARSONIST]
        if len(sk_alive) == 1 and len(alive_players) == 1:
            self.winner_faction = Faction.SERIAL_KILLER
            self.record_log("GAME_WIN", result="Sát Thủ Hàng Loạt độc chiếm chiến thắng!")
            return Faction.SERIAL_KILLER

        # Do not end on team parity while a mixed-objective pair is still alive.
        if any(self.has_lovers_objective(p.user_id) for p in alive_players):
            return None

        alive_wolves = [p for p in alive_players if p.is_wolf]
        alive_non_wolves = [p for p in alive_players if not p.is_wolf and p.role != Role.SERIAL_KILLER]

        if len(alive_wolves) == 0 and len(sk_alive) == 0 and not piper_alive_list and not arson_alive:
            self.winner_faction = Faction.VILLAGER
            self.record_log("GAME_WIN", result="Phe Dân Làng chiến thắng (tiêu diệt hết Sói và Sát Thủ)!")
            return Faction.VILLAGER

        white_wolf_alive = any(p.role == Role.WHITE_WOLF for p in alive_players)
        if (len(alive_wolves) >= len(alive_non_wolves) + len(sk_alive)
                and not sk_alive and not white_wolf_alive and not piper_alive_list and not arson_alive):
            self.winner_faction = Faction.WEREWOLF
            self.record_log("GAME_WIN", result="Phe Sói chiến thắng (số Sói >= số Dân)!")
            return Faction.WEREWOLF

        return None

    def calculate_rank_points(self) -> Dict[int, int]:
        """Signed result: losses always subtract; performance only rewards wins."""
        points: Dict[int, int] = {}
        if not self.settings.enable_rank or not self.winner_faction:
            return {uid: 0 for uid in self.players}
        if self.winner_faction == Faction.DRAW:
            return {uid: RANK_SOLO_WIN if player.human_hunter_succeeded else 0 for uid, player in self.players.items()}

        for uid, player in self.players.items():
            if not self.did_player_win(uid):
                points[uid] = RANK_LOSS
                continue
            base = RANK_SOLO_WIN if self.get_rank_faction(uid) == RankFaction.SOLO else RANK_TEAM_WIN
            bonus = 5 * (int(player.seer_found_wolf) + max(0, player.guard_saved_count) + max(0, player.witch_useful_use_count))
            points[uid] = base + min(RANK_BONUS_CAP, bonus)

        return points

    def has_rankable_result(self) -> bool:
        return bool(self.winner_faction and (self.winner_faction != Faction.DRAW or any(
            player.human_hunter_succeeded for player in self.players.values()
        )))

    @staticmethod
    def personal_objective(player: MasoiPlayer) -> Faction:
        if player.role == Role.WHITE_WOLF:
            return Faction.WHITE_WOLF
        if player.human_hunter_joined_wolves:
            return Faction.WEREWOLF
        if player.role == Role.ARSONIST:
            return Faction.ARSONIST
        if player.role == Role.HUMAN_HUNTER:
            return Faction.HUMAN_HUNTER
        return Faction.WEREWOLF if player.is_wolf else player.role.faction

    def has_lovers_objective(self, user_id: int) -> bool:
        player = self.players[user_id]
        partner = self.players.get(player.lover_id)
        if not partner or partner.lover_id != user_id:
            return False
        if player.lover_objective is not None and partner.lover_objective is not None:
            return player.lover_objective and partner.lover_objective
        return self.personal_objective(player) != self.personal_objective(partner)

    def lover_goal_text(self, user_id: int) -> str:
        if self.has_lovers_objective(user_id):
            return "💘 Mục tiêu: hai bạn phải là 2 người sống cuối cùng; cả hai tính rank Solo. Kẻ Ngốc bị treo cổ vẫn thắng ngay."
        return "Mục tiêu: giữ điều kiện thắng gốc; vẫn chết theo nhau. Rank theo mục tiêu cá nhân."

    def get_rank_faction(self, user_id: int) -> RankFaction:
        """Rank and win checks share the same personal objective."""
        player = self.players[user_id]
        if self.has_lovers_objective(user_id) or player.human_hunter_succeeded or (player.role in (Role.TANNER, Role.SERIAL_KILLER, Role.PIPER, Role.WHITE_WOLF, Role.ARSONIST, Role.HUMAN_HUNTER) and not player.human_hunter_joined_wolves):
            return RankFaction.SOLO
        return RankFaction.WOLF if player.is_wolf else RankFaction.VILLAGER

    def did_player_win(self, user_id: int) -> bool:
        """Whether this player's personal win condition was met."""
        player = self.players.get(user_id)
        if not player or not self.winner_faction:
            return False
        if self.has_lovers_objective(user_id) and self.winner_faction not in (Faction.LOVERS, Faction.INDEPENDENT):
            return False
        if player.role == Role.HUMAN_HUNTER and player.human_hunter_succeeded:
            return True
        if self.winner_faction == Faction.INDEPENDENT:
            return user_id == self.tanner_winner_id
        if self.winner_faction == Faction.ARSONIST:
            return player.role == Role.ARSONIST and player.is_alive
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
        if player.is_cursed_converted or player.human_hunter_joined_wolves:
            return self.winner_faction == Faction.WEREWOLF
        return player.role.faction == self.winner_faction
