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
    HUNTER = "Thợ Săn"
    TANNER = "Kẻ Ngốc"

    @property
    def emoji(self) -> str:
        emojis = {
            Role.WOLF: "🐺",
            Role.VILLAGER: "👤",
            Role.SEER: "🔮",
            Role.GUARD: "🛡️",
            Role.WITCH: "🧪",
            Role.HUNTER: "🏹",
            Role.TANNER: "🃏",
        }
        return emojis.get(self, "❓")

    @property
    def faction(self) -> Faction:
        if self == Role.WOLF:
            return Faction.WEREWOLF
        elif self == Role.TANNER:
            return Faction.INDEPENDENT
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
            Role.HUNTER: "Khi bị loại (bị Sói cắn hoặc bị treo cổ), bạn được chọn 1 người chơi để kéo theo cùng.",
            Role.TANNER: "Bạn thuộc phe Độc Lập. Bạn THẮNG NGAY LẬP TỨC nếu bị dân làng treo cổ ban ngày!",
        }
        return descriptions.get(self, "")


class Faction(Enum):
    WEREWOLF = "Phe Sói 🐺"
    VILLAGER = "Phe Dân Làng 👥"
    INDEPENDENT = "Phe Độc Lập 🃏"


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

        # Metrics cho rank bonus
        self.seer_found_wolf: bool = False
        self.guard_saved_count: int = 0
        self.witch_useful_use_count: int = 0

    @property
    def is_wolf(self) -> bool:
        return self.role == Role.WOLF


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
        self.night_witch_save: Optional[bool] = None
        self.night_witch_poison: Optional[int] = None

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

        # Số lượng Sói
        if n <= 7:
            wolf_count = 1
        elif n <= 10:
            wolf_count = 2
        elif n <= 14:
            wolf_count = 3
        else:
            wolf_count = 4

        role_pool: List[Role] = [Role.WOLF] * wolf_count

        # Tanner
        if self.settings.enable_tanner:
            role_pool.append(Role.TANNER)

        # Kỹ năng Dân Làng
        special_villagers = [Role.SEER, Role.GUARD, Role.WITCH, Role.HUNTER]
        for r in special_villagers:
            if len(role_pool) < n:
                role_pool.append(r)

        # Dân thường cho phần còn lại
        while len(role_pool) < n:
            role_pool.append(Role.VILLAGER)

        random.shuffle(role_pool)

        for uid, role in zip(user_ids, role_pool):
            self.players[uid].role = role

    def start_night(self):
        """Reset dữ liệu chuẩn bị vào Đêm mới."""
        self.night_count += 1
        self.night_guard_target = None
        self.night_wolf_votes.clear()
        self.night_seer_target = None
        self.night_seer_result = None
        self.night_witch_save = None
        self.night_witch_poison = None

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
        """Tính phiếu bầu treo cổ ban ngày. Trả về user_id bị xử tử (hoặc None nếu hòa phiếu)."""
        counts: Dict[int, int] = {}
        for target_id in self.day_votes.values():
            if target_id is not None:  # Bỏ qua phiếu trắng
                counts[target_id] = counts.get(target_id, 0) + 1

        if not counts:
            self.record_log("VOTE_RESULT", result="Không ai bị dồn phiếu")
            return None

        max_votes = max(counts.values())
        top_candidates = [tid for tid, cnt in counts.items() if cnt == max_votes]

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

        return executed_id

    def check_win_condition(self) -> Optional[Faction]:
        """Kiểm tra xem ván đấu đã có phe chiến thắng hay chưa."""
        if self.winner_faction:
            return self.winner_faction

        alive_players = self.get_alive_players()
        alive_wolves = [p for p in alive_players if p.is_wolf]
        alive_non_wolves = [p for p in alive_players if not p.is_wolf]

        if len(alive_wolves) == 0:
            self.winner_faction = Faction.VILLAGER
            self.record_log("GAME_WIN", result="Phe Dân Làng chiến thắng (tiêu diệt hết Sói)!")
            return Faction.VILLAGER

        if len(alive_wolves) >= len(alive_non_wolves):
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
