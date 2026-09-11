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
    STARTING = "starting"
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
    matched_groups: List[Dict]  # Nhóm liên thông bởi đáp án trùng hoặc có ít nhất 1 từ chung
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
        - Hai đáp án khớp nếu giống canonical hoặc có ít nhất 1 từ chuẩn hóa chung
        - Tính điểm:
          + Khớp với >= 1 người: +10đ cơ bản + 2đ/người khớp thêm
          + Đại Hợp Ý (100% phòng cùng trùng 1 từ): +20đ bonus mỗi người
          + Lẻ loi (không trùng): 0đ
          + Không trả lời: 0đ
        """
        # Việc reveal có thể bị gọi lặp do interaction/race. Không được cộng điểm lần hai.
        if self.phase == GamePhase.ROUND_END and self.last_evaluation is not None:
            return self.last_evaluation
        if self.phase not in (GamePhase.QUESTION, GamePhase.REVEALING):
            raise RuntimeError("Chỉ được tính điểm khi vòng vừa kết thúc nhận câu trả lời")

        self.phase = GamePhase.ROUND_END
        synonyms = self.current_question.get("synonyms") if self.current_question else None

        # Chuẩn hóa đáp án trước khi so khớp. Chỉ token có chữ/số mới được coi là
        # một "chữ" để emoji hoặc ký hiệu đơn lẻ không vô tình tạo điểm.
        answer_entries: List[Tuple[HopyPlayer, str, str, set[str]]] = []
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
            tokens = {
                token
                for token in key.split()
                if any(char.isalnum() for char in token)
            }
            answer_entries.append((player, raw, key, tokens))

        matched_groups: List[Dict] = []
        solos: List[Dict] = []

        total_active_count = len(self.active_players)
        is_dai_hop_y = False

        # Kiểm tra Đại Hợp Ý: Duy nhất 1 nhóm khớp từ chứa toàn bộ active_players (ít nhất 2 người)
        if len(canonical_map) == 1 and len(no_answers) == 0 and total_active_count >= 2:
            is_dai_hop_y = True

        # Lập đồ thị khớp ý. Tính điểm theo số đối thủ thực sự có đáp án khớp với
        # từng người; cách này xử lý đúng cả chuỗi như "trà sữa" - "trà đá" -
        # "đá xay" mà không cộng điểm hai lần cho người ở giữa.
        neighbors: Dict[int, set[int]] = {
            player.user_id: set() for player, _, _, _ in answer_entries
        }
        edge_terms: Dict[Tuple[int, int], set[str]] = {}

        for idx, (left_player, _, left_key, left_tokens) in enumerate(answer_entries):
            for right_player, _, right_key, right_tokens in answer_entries[idx + 1:]:
                shared_tokens = left_tokens & right_tokens
                is_exact = left_key == right_key
                if not is_exact and not shared_tokens:
                    continue

                left_id = left_player.user_id
                right_id = right_player.user_id
                neighbors[left_id].add(right_id)
                neighbors[right_id].add(left_id)
                edge_terms[(min(left_id, right_id), max(left_id, right_id))] = (
                    {left_key} if is_exact else shared_tokens
                )

        points_by_player: Dict[int, int] = {}
        for player, raw, _, _ in answer_entries:
            peer_count = len(neighbors[player.user_id])
            if peer_count == 0:
                player.round_scores[self.current_round] = 0
                solos.append({"player": player, "raw_answer": raw})
                continue

            points = 10 + (peer_count - 1) * 2
            if is_dai_hop_y:
                points += 20
            player.score += points
            player.match_count += 1
            player.round_scores[self.current_round] = points
            points_by_player[player.user_id] = points

        # Gom các cặp khớp thành component chỉ để trình bày kết quả. Điểm vẫn dựa
        # trên neighbors ở trên, nên một liên kết bắc cầu không tạo điểm giả.
        entries_by_id = {
            player.user_id: (player, raw, key)
            for player, raw, key, _ in answer_entries
        }
        visited: set[int] = set()
        for player, _, _, _ in answer_entries:
            root_id = player.user_id
            if root_id in visited or not neighbors[root_id]:
                continue

            stack = [root_id]
            component_ids: List[int] = []
            while stack:
                current_id = stack.pop()
                if current_id in visited:
                    continue
                visited.add(current_id)
                component_ids.append(current_id)
                stack.extend(neighbors[current_id] - visited)

            component_set = set(component_ids)
            shared_terms: set[str] = set()
            for (left_id, right_id), terms in edge_terms.items():
                if left_id in component_set and right_id in component_set:
                    shared_terms.update(terms)

            group_players = [entries_by_id[user_id][0] for user_id in component_ids]
            raw_answers = {
                user_id: entries_by_id[user_id][1] for user_id in component_ids
            }
            canonical_keys = {entries_by_id[user_id][2] for user_id in component_ids}
            group_points = {
                user_id: points_by_player[user_id] for user_id in component_ids
            }
            matched_groups.append({
                "canonical": next(iter(canonical_keys)) if len(canonical_keys) == 1 else "",
                "display_word": raw_answers[component_ids[0]],
                "shared_words": sorted(shared_terms),
                "players": group_players,
                "raw_answers": raw_answers,
                "player_points": group_points,
                "points_each": (
                    next(iter(group_points.values()))
                    if len(set(group_points.values())) == 1
                    else None
                ),
            })

        is_all_solos = (
            total_active_count > 0
            and len(solos) == total_active_count
            and len(no_answers) == 0
        )

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
