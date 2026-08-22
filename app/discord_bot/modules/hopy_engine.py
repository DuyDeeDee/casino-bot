# coding: utf-8
"""
Engine xử lý logic phòng chơi, vòng đấu, gom nhóm so khớp và tính điểm cho minigame HỢP Ý.
"""
from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

from app.discord_bot.modules.hopy_data import (
    QUESTIONS,
    normalize_answer,
    resolve_canonical_key,
)


class GamePhase(str, Enum):
    LOBBY = "lobby"
    QUESTION = "question"
    REVEALING = "revealing"
    ROUND_END = "round_end"
    GAME_OVER = "game_over"


@dataclass
class HopyPlayer:
    user_id: int
    display_name: str
    score: int = 0
    match_count: int = 0  # Số lần trùng ý thành công
    round_scores: Dict[int, int] = field(default_factory=dict)
    answers: Dict[int, str] = field(default_factory=dict)
    active: bool = True  # False nếu đã thoát phòng giữa chừng


@dataclass
class RoundEvaluation:
    matched_groups: List[Dict]  # [{"canonical": str, "display_word": str, "players": [HopyPlayer], "points_each": int}]
    solos: List[Dict]  # [{"player": HopyPlayer, "raw_answer": str}]
    no_answers: List[HopyPlayer]  # [HopyPlayer]
    is_dai_hop_y: bool = False
    is_all_solos: bool = False


class HopyGame:
    MIN_PLAYERS = 2  # Cho phép từ 2 người, tối ưu 3-8 người
    MAX_PLAYERS = 8

    def __init__(self, channel_id: int, host_id: int, host_name: str):
        self.channel_id = channel_id
        self.host_id = host_id
        self.host_name = host_name
        self.difficulty = "mix"  # "easy", "hard", "mix"
        self.total_rounds = 5  # 3, 5, 7
        self.current_round = 0
        self.phase = GamePhase.LOBBY
        self.message_id: Optional[int] = None

        self.players: Dict[int, HopyPlayer] = {}
        self.questions_queue: List[Dict] = []
        self.current_question: Optional[Dict] = None

        # Dữ liệu vòng hiện tại
        self.round_raw_answers: Dict[int, str] = {}
        self.last_evaluation: Optional[RoundEvaluation] = None

        # Thêm host vào danh sách người chơi đầu tiên
        self.add_player(host_id, host_name)

    @property
    def active_players(self) -> List[HopyPlayer]:
        return [p for p in self.players.values() if p.active]

    @property
    def player_count(self) -> int:
        return len(self.active_players)

    def add_player(self, user_id: int, display_name: str) -> bool:
        if self.phase != GamePhase.LOBBY:
            return False
        if len(self.players) >= self.MAX_PLAYERS:
            return False
        if user_id in self.players:
            # Nếu người chơi trước đó out rồi join lại trong lobby
            self.players[user_id].active = True
            self.players[user_id].display_name = display_name
            return True
        self.players[user_id] = HopyPlayer(user_id=user_id, display_name=display_name)
        return True

    def remove_player(self, user_id: int) -> bool:
        if user_id not in self.players:
            return False
        if self.phase == GamePhase.LOBBY:
            del self.players[user_id]
            # Nếu host rời phòng trong lobby, chuyển host cho người tiếp theo
            if user_id == self.host_id and self.players:
                next_host = next(iter(self.players.values()))
                self.host_id = next_host.user_id
                self.host_name = next_host.display_name
            return True
        else:
            # Trong trận, đánh dấu inactive để không bị kẹt vòng chơi
            self.players[user_id].active = False
            if user_id == self.host_id:
                active = self.active_players
                if active:
                    self.host_id = active[0].user_id
                    self.host_name = active[0].display_name
            return True

    def set_difficulty(self, diff: str) -> bool:
        if self.phase != GamePhase.LOBBY:
            return False
        if diff in ["easy", "hard", "mix"]:
            self.difficulty = diff
            return True
        return False

    def set_rounds(self, rounds: int) -> bool:
        if self.phase != GamePhase.LOBBY:
            return False
        if rounds in [3, 5, 7]:
            self.total_rounds = rounds
            return True
        return False

    def prepare_game(self) -> bool:
        """Chọn danh sách câu hỏi không trùng lặp theo độ khó"""
        if self.player_count < self.MIN_PLAYERS:
            return False

        if self.difficulty == "easy":
            pool = [q for q in QUESTIONS if q.get("difficulty") == "easy"]
        elif self.difficulty == "hard":
            pool = [q for q in QUESTIONS if q.get("difficulty") == "hard"]
        else:
            pool = list(QUESTIONS)

        # Xáo trộn và lấy đủ số câu
        random.shuffle(pool)
        if len(pool) < self.total_rounds:
            # Nếu ngân hàng câu hỏi thiếu theo bộ lọc, lấy thêm từ toàn bộ câu hỏi
            extra = [q for q in QUESTIONS if q not in pool]
            random.shuffle(extra)
            pool.extend(extra)

        self.questions_queue = pool[:self.total_rounds]
        self.current_round = 0
        return True

    def start_next_round(self) -> Optional[Dict]:
        """Bắt đầu vòng chơi tiếp theo"""
        if self.current_round >= self.total_rounds or not self.questions_queue:
            self.phase = GamePhase.GAME_OVER
            return None

        self.current_round += 1
        self.current_question = self.questions_queue[self.current_round - 1]
        self.round_raw_answers.clear()
        self.last_evaluation = None
        self.phase = GamePhase.QUESTION
        return self.current_question

    def submit_answer(self, user_id: int, answer_text: str) -> bool:
        """Nộp hoặc sửa câu trả lời cho vòng hiện tại"""
        if self.phase != GamePhase.QUESTION:
            return False
        player = self.players.get(user_id)
        if not player or not player.active:
            return False

        clean_text = answer_text.strip()
        if not clean_text:
            return False

        self.round_raw_answers[user_id] = clean_text[:35]
        player.answers[self.current_round] = self.round_raw_answers[user_id]
        return True

    def has_answered(self, user_id: int) -> bool:
        return user_id in self.round_raw_answers

    def get_answered_status(self) -> Tuple[int, int, List[str]]:
        """Trả về (số người đã nộp, tổng số người active, danh sách tên người đã nộp)"""
        answered_names = []
        for p in self.active_players:
            if p.user_id in self.round_raw_answers:
                answered_names.append(p.display_name)
        return len(answered_names), len(self.active_players), answered_names

    def have_all_answered(self) -> bool:
        """Kiểm tra toàn bộ người chơi active đã trả lời chưa"""
        active_ids = {p.user_id for p in self.active_players}
        return active_ids.issubset(set(self.round_raw_answers.keys()))

    def evaluate_round(self) -> RoundEvaluation:
        """
        Tính điểm và so khớp câu trả lời vòng hiện tại:
        - Chuẩn hóa text và phân giải từ đồng nghĩa
        - Gom nhóm các câu trả lời trùng khớp
        - Tính điểm:
          + Trùng với >= 1 người: +10đ cơ bản + 2đ/người trùng thêm
          + Đại Hợp Ý (100% phòng cùng trùng 1 từ): +20đ bonus mỗi người
          + Lẻ loi (không trùng): 0đ
          + Không trả lời: 0đ
        """
        self.phase = GamePhase.ROUND_END
        synonyms = self.current_question.get("synonyms") if self.current_question else None

        # Gom nhóm theo canonical key
        canonical_map: Dict[str, List[Tuple[HopyPlayer, str]]] = defaultdict(list)
        no_answers: List[HopyPlayer] = []

        for player in self.active_players:
            raw = self.round_raw_answers.get(player.user_id)
            if not raw:
                no_answers.append(player)
                player.round_scores[self.current_round] = 0
                continue

            norm = normalize_answer(raw)
            key = resolve_canonical_key(norm, synonyms)
            canonical_map[key].append((player, raw))

        matched_groups: List[Dict] = []
        solos: List[Dict] = []

        total_active_count = len(self.active_players)
        is_dai_hop_y = False

        # Kiểm tra Đại Hợp Ý: Duy nhất 1 nhóm khớp từ chứa toàn bộ active_players (ít nhất 2 người)
        if len(canonical_map) == 1 and len(no_answers) == 0 and total_active_count >= 2:
            is_dai_hop_y = True

        for key, members in canonical_map.items():
            group_size = len(members)
            if group_size >= 2:
                # Tính điểm nhóm: 10đ cơ bản + 2đ cho mỗi người trùng thêm từ người thứ 3 trở đi
                # 2 người -> 10đ
                # 3 người -> 10 + 2 = 12đ
                # 4 người -> 10 + 4 = 14đ
                points = 10 + (group_size - 2) * 2
                if is_dai_hop_y:
                    points += 20  # Thêm bonus Đại Hợp Ý khủng

                # Lấy từ đại diện hiển thị (lấy từ raw phổ biến nhất hoặc từ đầu tiên)
                sample_word = members[0][1]

                group_players = []
                for p, raw in members:
                    group_players.append(p)
                    p.score += points
                    p.match_count += 1
                    p.round_scores[self.current_round] = points

                matched_groups.append({
                    "canonical": key,
                    "display_word": sample_word,
                    "players": group_players,
                    "points_each": points
                })
            else:
                p, raw = members[0]
                p.round_scores[self.current_round] = 0
                solos.append({
                    "player": p,
                    "raw_answer": raw
                })

        is_all_solos = (len(matched_groups) == 0)

        # Sắp xếp nhóm trùng đông nhất lên đầu
        matched_groups.sort(key=lambda g: len(g["players"]), reverse=True)

        evaluation = RoundEvaluation(
            matched_groups=matched_groups,
            solos=solos,
            no_answers=no_answers,
            is_dai_hop_y=is_dai_hop_y,
            is_all_solos=is_all_solos
        )
        self.last_evaluation = evaluation
        return evaluation

    def get_leaderboard(self) -> List[HopyPlayer]:
        """Lấy bảng xếp hạng sắp xếp theo điểm số giảm dần, sau đó theo số lần trùng ý"""
        all_players = list(self.players.values())
        all_players.sort(key=lambda p: (p.score, p.match_count), reverse=True)
        return all_players

    def get_mvp(self) -> Optional[HopyPlayer]:
        """MVP là người có điểm cao nhất hoặc số lần trùng ý nhiều nhất"""
        board = self.get_leaderboard()
        return board[0] if board else None

    def is_game_over(self) -> bool:
        return self.current_round >= self.total_rounds
