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
        }
        return emojis.get(self, "❓")

    @property
    def faction(self) -> Faction:
        if self in (Role.WOLF, Role.WOLF_SEER):
            return Faction.WEREWOLF
        elif self == Role.TANNER:
            return Faction.INDEPENDENT
        elif self == Role.SERIAL_KILLER:
            return Faction.SERIAL_KILLER
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
        }
        return descriptions.get(self, "")


class Faction(Enum):
    WEREWOLF = "Phe Sói 🐺"
    VILLAGER = "Phe Dân Làng 👥"
    INDEPENDENT = "Phe Độc Lập 🃏"
    LOVERS = "Phe Tình Nhân 💘"
    SERIAL_KILLER = "Phe Sát Thủ 🔪"


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


class MasoiSettings:
    """Cấu hình ván Ma Sói có thể chỉnh ở Lobby."""
    def __init__(self):
        self.reveal_roles_on_death: bool = True  # True: Hiện ngay / False: Ẩn tới cuối ván
        self.enable_tanner: bool = False  # Bật/Tắt Kẻ Phản Bội
        self.vote_display: str = "REALTIME"  # REALTIME / END_ONLY
        self.dead_can_chat: bool = False  # False: Bị cấm chat / True: Được chat
        self.discussion_time: int = 120  # 60, 120, 180, 300 giây
        self.night_time: int = 45  # 30, 45, 60 giây
        self.enable_rank: bool = True  # Có/Không tính rank
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
        idx = times.index(self.night_time) if self.night_time in times else 1
        self.night_time = times[(idx + 1) % len(times)]

    def cycle_rank(self):
        self.enable_rank = not self.enable_rank

    def to_dict(self) -> dict:
        return {
            "reveal_roles_on_death": self.reveal_roles_on_death,
            "enable_tanner": self.enable_tanner,
            "vote_display": self.vote_display,
            "dead_can_chat": self.dead_can_chat,
            "discussion_time": self.discussion_time,
            "night_time": self.night_time,
            "enable_rank": self.enable_rank,
            "role_setup_mode": self.role_setup_mode,
            "custom_wolf_count": self.custom_wolf_count,
            "custom_special_roles": self.custom_special_roles,
        }

    @classmethod
    def from_dict(cls, data: dict) -> MasoiSettings:
        s = cls()
        s.reveal_roles_on_death = data.get("reveal_roles_on_death", True)
        s.enable_tanner = data.get("enable_tanner", False)
        s.vote_display = data.get("vote_display", "REALTIME")
        s.dead_can_chat = data.get("dead_can_chat", False)
        s.discussion_time = data.get("discussion_time", 120)
        s.night_time = data.get("night_time", 45)
        s.enable_rank = data.get("enable_rank", True)
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
        self.elder_lives: int = 2  # Già Làng có 2 mạng trước đòn cắn của Sói

        # Metrics cho rank bonus
        self.seer_found_wolf: bool = False
        self.guard_saved_count: int = 0
        self.witch_useful_use_count: int = 0

    @property
    def is_wolf(self) -> bool:
        return self.role in (Role.WOLF, Role.WOLF_SEER) or self.is_cursed_converted


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
        self.witch_dm_message: Optional[any] = None
        self.witch_view: Optional[any] = None
        self.mayor_id: Optional[int] = None

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
        self.night_guard_target = None
        self.night_wolf_votes.clear()
        self.night_seer_target = None
        self.night_seer_result = None
        self.night_wolf_seer_target = None
        self.night_wolf_seer_result = None
        self.night_serial_killer_target = None
        self.night_witch_save = None
        self.night_witch_poison = None
        self.witch_dm_message = None
        self.witch_view = None

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

    def resolve_wolf_target(self) -> Optional[int]:
        """Tính đa số phiếu cắn của bầy Sói (nếu hòa phiếu -> chọn ngẫu nhiên)."""
        if not self.night_wolf_votes:
            return None
        counts: Dict[int, int] = {}
        for target in self.night_wolf_votes.values():
            counts[target] = counts.get(target, 0) + 1
        max_votes = max(counts.values())
        top_targets = [t for t, cnt in counts.items() if cnt == max_votes]
        return random.choice(top_targets)

    def resolve_night(self) -> List[int]:
        """Tính toán ai chết ban đêm và cập nhật trạng thái."""
        deaths: Set[int] = set()

        wolf_target_id = self.resolve_wolf_target()

        if wolf_target_id:
            self.record_log("WOLF_KILL", target_id=wolf_target_id, result="Bầy Sói chọn cắn")

            is_protected = (self.night_guard_target == wolf_target_id)
            is_saved = (self.night_witch_save is True)

            if is_protected:
                guard_p = self.get_player_by_role(Role.GUARD)
                if guard_p:
                    guard_p.guard_saved_count += 1
                self.record_log("GUARD_PROTECT", target_id=wolf_target_id, result="Bảo vệ thành công")

            if is_saved:
                witch_p = self.get_player_by_role(Role.WITCH)
                if witch_p:
                    witch_p.witch_useful_use_count += 1
                self.record_log("WITCH_SAVE", target_id=wolf_target_id, result="Phù thủy dùng bình cứu")

            if not is_protected and not is_saved:
                target_p = self.players.get(wolf_target_id)
                if target_p:
                    # Kẻ Bị Nguyền: Bị cắn biến thành Sói, không chết
                    if target_p.role == Role.CURSED and not target_p.is_cursed_converted:
                        target_p.is_cursed_converted = True
                        self.record_log("CURSED_CONVERT", target_id=wolf_target_id, result="Kẻ Bị Nguyền bị Sói cắn và biến thành Sói!")
                    # Già Làng: Có 2 mạng trước đòn cắn của Sói
                    elif target_p.role == Role.ELDER and target_p.elder_lives > 1:
                        target_p.elder_lives -= 1
                        self.record_log("ELDER_SAVED", target_id=wolf_target_id, result="Già Làng sống sót lần 1 trước nanh nanh Sói")
                    # Sát Thủ: Miễn nhiễm cắn của Sói
                    elif target_p.role == Role.SERIAL_KILLER:
                        self.record_log("SK_IMMUNE", target_id=wolf_target_id, result="Sát Thủ miễn nhiễm đòn cắn của Sói")
                    else:
                        deaths.add(wolf_target_id)

        # Xử lý Phù thủy dùng độc
        if self.night_witch_poison:
            poison_target = self.night_witch_poison
            deaths.add(poison_target)
            witch_p = self.get_player_by_role(Role.WITCH)
            target_p = self.players.get(poison_target)
            if witch_p and target_p and target_p.is_wolf:
                witch_p.witch_useful_use_count += 1
            self.record_log("WITCH_POISON", target_id=poison_target, result="Phù thủy dùng bình độc")

        # Xử lý Sát Thủ Hàng Loạt giết người
        if self.night_serial_killer_target:
            sk_target = self.night_serial_killer_target
            is_sk_target_saved = (sk_target == wolf_target_id and self.night_witch_save is True)
            if sk_target != self.night_guard_target and not is_sk_target_saved:
                deaths.add(sk_target)
                self.record_log("SERIAL_KILLER_KILL", target_id=sk_target, result="Sát Thủ hạ gục nạn nhân ban đêm")
            elif is_sk_target_saved:
                self.record_log("WITCH_SAVE_SK", target_id=sk_target, result="Phù Thủy dùng bình cứu khỏi tay Sát Thủ")
            else:
                self.record_log("GUARD_PROTECT_SK", target_id=sk_target, result="Bảo vệ cứu sống khỏi tay Sát Thủ")

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
                self.players[uid].is_alive = False
                self.record_log("NIGHT_DEATH", target_id=uid, result="Qua đời ban đêm")

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
        """Tính phiếu bầu treo cổ ban ngày (Thị Trưởng vote x2). Trả về user_id bị xử tử (hoặc None nếu hòa phiếu)."""
        counts: Dict[Optional[int], int] = {}
        for voter_id, target_id in self.day_votes.items():
            weight = 2 if (self.mayor_id and voter_id == self.mayor_id) else 1
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
            # Hòa phiếu -> Không ai bị treo cổ
            self.record_log("VOTE_RESULT", result=f"Hòa phiếu ({max_votes} phiếu), không ai bị treo cổ")
            return None

        executed_id = top_candidates[0]
        self.players[executed_id].is_alive = False
        self.executed_player_id = executed_id

        self.record_log("DAY_EXECUTION", target_id=executed_id, result=f"Bị treo cổ với {max_votes} phiếu")

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
            if self.winner_faction == Faction.INDEPENDENT:
                if uid == self.tanner_winner_id:
                    pts += 25
                else:
                    pts += 2
            elif player.role.faction == self.winner_faction:
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
