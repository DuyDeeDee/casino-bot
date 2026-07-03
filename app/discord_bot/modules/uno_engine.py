"""
UNO Game Engine
Quản lý toàn bộ logic game UNO: bộ bài, trạng thái game, luật chơi.
"""
from __future__ import annotations

import random
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

# ─── Đường dẫn ảnh ────────────────────────────────────────────────────────────
CARDS_DIR = Path(__file__).resolve().parent / "Uno" / "uno_cards"


# ─── Màu sắc ──────────────────────────────────────────────────────────────────
class Color(str, Enum):
    RED    = "red"
    YELLOW = "yellow"
    GREEN  = "green"
    BLUE   = "blue"
    WILD   = "wild"


COLOR_EMOJI = {
    Color.RED:    "🔴",
    Color.YELLOW: "🟡",
    Color.GREEN:  "🟢",
    Color.BLUE:   "🔵",
    Color.WILD:   "🌈",
}

COLOR_LABEL = {
    Color.RED:    "Đỏ",
    Color.YELLOW: "Vàng",
    Color.GREEN:  "Xanh Lá",
    Color.BLUE:   "Xanh Dương",
}

PLAYABLE_COLORS = [Color.RED, Color.YELLOW, Color.GREEN, Color.BLUE]

# ─── Custom Discord Emojis Mapping ────────────────────────────────────────────
DYNAMIC_EMOJIS = {}
VERIFIED_EMOJI_IDS = set()
EMOJI_SCANNED = False
UNO_EMOJIS = {
    # Vàng (Yellow)
    "yellow_skip": "<:yellow_skip_a:1522278509521666068>",
    "yellow_reverse": "<:yellow_reverse_a:1522278490467205343>",
    "yellow_draw2": "<:yellow_draw2_a:1522278458225459211>",
    "yellow_9": "<:yellow_9_a:1522278432652923101>",
    "yellow_8": "<:yellow_8_a:1522278412679381143>",
    "yellow_7": "<:yellow_7_a:1522278391875637419>",
    "yellow_6": "<:yellow_6_b:1522278363933184120>",
    "yellow_5": "<:yellow_5_a:1522278341632065607>",
    "yellow_4": "<:yellow_4_b:1522278318735495289>",
    "yellow_3": "<:yellow_3_a:1522278270694068245>",
    "yellow_2": "<:yellow_2_a:1522278247156634258>",
    "yellow_1": "<:yellow_1_a:1522278217631924365>",
    "yellow_0": "<:yellow_0_a:1522278196547031100>",
    
    # Lá Đặc Biệt (Wild)
    "wild_wild4": "<:wild_draw4_a:1522278175667916872>",
    "wild_wild": "<:wild_a:1522278156256542940>",
    
    # Đỏ (Red)
    "red_skip": "<:red_skip_a:1522278083829170299>",
    "red_reverse": "<:red_reverse_a:1522278059829479898>",
    "red_draw2": "<:red_draw2_a:1522278035578163320>",
    "red_9": "<:red_9_a:1522278007325200546>",
    "red_8": "<:red_8_a:1522277984650793071>",
    "red_7": "<:red_7_a:1522277965021581312>",
    "red_5": "<:red_5_b:1522277948328247458>",
    "red_6": "<:red_6_a:1522277925502714019>",
    "red_4": "<:red_4_a:1522277908540952667>",
    "red_3": "<:red_3_a:1522277890715025488>",
    "red_2": "<:red_2_a:1522277866291724469>",
    "red_1": "<:red_1_a:1522277851292762193>",
    "red_0": "<:red_0_a:1522277834981380176>",
    
    # Xanh Lá (Green)
    "green_skip": "<:green_skip_a:1522277818162221136>",
    "green_reverse": "<:green_reverse_a:1522277755218165891>",
    "green_draw2": "<:green_draw2_a:1522277736024899625>",
    "green_9": "<:green_9_b:1522277711261728768>",
    "green_8": "<:green_8_b:1522277691053834502>",
    "green_7": "<:green_7_a:1522277674658173048>",
    "green_6": "<:green_6_a:1522277652558516274>",
    "green_5": "<:green_5_a:1522277632387973180>",
    "green_4": "<:green_4_a:1522277609864560651>",
    "green_3": "<:green_3_a:1522277592168923288>",
    "green_2": "<:green_2_a:1522277569163038951>",
    "green_1": "<:green_1_a:1522277535604277348>",
    "green_0": "<:green_0_a:1522277505459949800>",
    
    # Xanh Dương (Blue)
    "blue_skip": "<:blue_skip_a:1522277485205782649>",
    "blue_reverse": "<:blue_reverse_a:1522277468541550723>",
    "blue_draw2": "<:blue_draw2_a:1522277442843050054>",
    "blue_9": "<:blue_9_a:1522277418520281129>",
    "blue_8": "<:blue_8_a:1522277399880929343>",
    "blue_7": "<:blue_7_a:1522277383615414382>",
    "blue_6": "<:blue_6_a:1522277368444485926>",
    "blue_5": "<:blue_5_a:1522277353638854716>",
    "blue_4": "<:blue_4_a:1522277344092618882>",
    "blue_3": "<:blue_3_a:1522277331358715924>",
    "blue_2": "<:blue_2_a:1522277319400620126>",
    "blue_1": "<:blue_1_a:1522277307400585297>",
    "blue_0": "<:blue_0_a:1522277293786140742>",
}


# ─── Giá trị bài ──────────────────────────────────────────────────────────────
class Value(str, Enum):
    ZERO    = "0"
    ONE     = "1"
    TWO     = "2"
    THREE   = "3"
    FOUR    = "4"
    FIVE    = "5"
    SIX     = "6"
    SEVEN   = "7"
    EIGHT   = "8"
    NINE    = "9"
    SKIP    = "skip"
    REVERSE = "reverse"
    DRAW2   = "draw2"
    WILD    = "wild"
    WILD4   = "wild4"


ACTION_VALUES = {Value.SKIP, Value.REVERSE, Value.DRAW2, Value.WILD, Value.WILD4}
WILD_VALUES   = {Value.WILD, Value.WILD4}


# ─── Card ─────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class UnoCard:
    color: Color
    value: Value

    # ------------------------------------------------------------------
    def display(self) -> str:
        """Hiển thị dạng emoji, ưu tiên dùng custom Discord Emojis."""
        key = f"{self.color.value}_{self.value.value}"
        if key in DYNAMIC_EMOJIS:
            return DYNAMIC_EMOJIS[key]
        if key in UNO_EMOJIS:
            return UNO_EMOJIS[key]

        # Fallback nếu không có custom emoji
        emoji = COLOR_EMOJI.get(self.color, "")
        label = self._value_label()
        return f"{emoji} {label}"

    def _value_label(self) -> str:
        labels = {
            Value.SKIP:    "Skip",
            Value.REVERSE: "Reverse",
            Value.DRAW2:   "+2",
            Value.WILD:    "Wild",
            Value.WILD4:   "Wild +4",
        }
        return labels.get(self.value, self.value.value)

    # ------------------------------------------------------------------
    def image_path(self) -> Optional[Path]:
        """Trả về đường dẫn file ảnh lá bài (tự động thử các bản copy a, b, c, d)."""
        for copy in ("a", "b", "c", "d"):
            if self.value == Value.WILD:
                name = f"wild_{copy}.png"
            elif self.value == Value.WILD4:
                name = f"wild_draw4_{copy}.png"
            elif self.value == Value.SKIP:
                name = f"{self.color.value}_skip_{copy}.png"
            elif self.value == Value.REVERSE:
                name = f"{self.color.value}_reverse_{copy}.png"
            elif self.value == Value.DRAW2:
                name = f"{self.color.value}_draw2_{copy}.png"
            else:
                name = f"{self.color.value}_{self.value.value}_{copy}.png"

            p = CARDS_DIR / name
            if p.exists():
                return p
        return None

    # ------------------------------------------------------------------
    def can_play_on(self, top: "UnoCard", current_color: Color) -> bool:
        """Kiểm tra lá này có thể đánh lên lá `top` không."""
        if self.value in WILD_VALUES:
            return True
        if self.color == current_color:
            return True
        if self.value == top.value:
            return True
        return False

    # ------------------------------------------------------------------
    def has_same_color(self, color: Color) -> bool:
        return self.color == color and self.color != Color.WILD


# ─── Deck ─────────────────────────────────────────────────────────────────────
def build_deck() -> list[UnoCard]:
    """Tạo bộ bài UNO 108 lá chuẩn."""
    deck: list[UnoCard] = []

    for color in PLAYABLE_COLORS:
        # Số 0: 1 lá/màu
        deck.append(UnoCard(color, Value.ZERO))
        # Số 1–9 + Skip + Reverse + Draw2: 2 lá/màu
        for value in [
            Value.ONE, Value.TWO, Value.THREE, Value.FOUR, Value.FIVE,
            Value.SIX, Value.SEVEN, Value.EIGHT, Value.NINE,
            Value.SKIP, Value.REVERSE, Value.DRAW2,
        ]:
            deck.append(UnoCard(color, value))
            deck.append(UnoCard(color, value))

    # Wild × 4, Wild+4 × 4
    for _ in range(4):
        deck.append(UnoCard(Color.WILD, Value.WILD))
        deck.append(UnoCard(Color.WILD, Value.WILD4))

    random.shuffle(deck)
    return deck


# ─── Player ───────────────────────────────────────────────────────────────────
@dataclass
class UnoPlayer:
    user_id: int
    username: str
    hand: list[UnoCard] = field(default_factory=list)
    uno_called: bool = False   # True nếu đã hô UNO hợp lệ
    afk_count: int = 0
    hand_msg_id: Optional[int] = None  # ID message ephemeral bài trên tay


# ─── Game State ───────────────────────────────────────────────────────────────
class GamePhase(str, Enum):
    LOBBY    = "lobby"
    PLAYING  = "playing"
    FINISHED = "finished"


@dataclass
class UnoGame:
    channel_id: int
    host_id: int
    bet: int

    players: list[UnoPlayer]          = field(default_factory=list)
    deck: list[UnoCard]               = field(default_factory=list)
    discard_pile: list[UnoCard]       = field(default_factory=list)
    current_player_index: int         = 0
    direction: int                    = 1          # 1=thuận, -1=ngược
    current_color: Color              = Color.RED
    phase: GamePhase                  = GamePhase.LOBBY

    # Trạng thái lượt hiện tại
    pending_draw: int                  = 0     # Số lá bị dồn (combo +2/+4)
    pending_draw_type: Optional[str]   = None  # "draw2" | "wild4"
    winner_id: Optional[int]          = None
    lobby_msg_id: Optional[int]       = None   # ID embed phòng chờ
    board_msg_id: Optional[int]       = None   # ID embed bàn chơi
    turn_count: int                   = 0

    # UNO call tracking
    uno_pending_user_id: Optional[int] = None  # Người đang cần hô UNO
    uno_safe: bool                     = False  # Đã hô kịp chưa
    turn_token: str                    = field(default_factory=lambda: uuid4().hex)
    last_play_info: str                = "Trò chơi vừa bắt đầu!"
    last_player_id: Optional[int]      = None

    # ------------------------------------------------------------------
    @property
    def top_card(self) -> UnoCard:
        return self.discard_pile[-1]

    @property
    def current_player(self) -> UnoPlayer:
        return self.players[self.current_player_index]

    # ------------------------------------------------------------------
    def add_player(self, user_id: int, username: str) -> bool:
        """Thêm người chơi vào phòng. Trả về False nếu đầy hoặc đã có."""
        if len(self.players) >= 8:
            return False
        if any(p.user_id == user_id for p in self.players):
            return False
        self.players.append(UnoPlayer(user_id=user_id, username=username))
        return True

    def remove_player(self, user_id: int) -> bool:
        for i, p in enumerate(self.players):
            if p.user_id == user_id:
                self.players.pop(i)
                if self.current_player_index >= len(self.players) and self.players:
                    self.current_player_index = 0
                return True
        return False

    def get_player(self, user_id: int) -> Optional[UnoPlayer]:
        return next((p for p in self.players if p.user_id == user_id), None)

    # ------------------------------------------------------------------
    def start_game(self):
        """Khởi tạo game: tạo bộ bài, chia bài, lật lá đầu."""
        self.deck = build_deck()
        self.phase = GamePhase.PLAYING

        # Chia 7 lá mỗi người
        for player in self.players:
            player.hand = [self.deck.pop() for _ in range(7)]

        # Lật lá đầu — đảm bảo không phải Wild+4
        while True:
            card = self.deck.pop()
            if card.value != Value.WILD4:
                self.discard_pile.append(card)
                break
            self.deck.insert(0, card)  # để về đáy bài

        # Xử lý lá mở đầu đặc biệt
        opening = self.discard_pile[-1]
        self.current_color = opening.color if opening.color != Color.WILD else random.choice(PLAYABLE_COLORS)
        self._apply_opening_card(opening)

        # Chọn người đi trước ngẫu nhiên
        self.current_player_index = random.randint(0, len(self.players) - 1)

    def _apply_opening_card(self, card: UnoCard):
        """Áp dụng hiệu ứng lá khởi đầu (nếu là Action card)."""
        if card.value == Value.SKIP:
            self._advance_turn()       # người đầu bị bỏ qua → người thứ 2 đi trước
        elif card.value == Value.REVERSE:
            self.direction *= -1
        elif card.value == Value.DRAW2:
            # Người đầu tiên phải xử lý pending_draw khi đến lượt
            self.pending_draw += 2
            self.pending_draw_type = "draw2"

    # ------------------------------------------------------------------
    def draw_cards(self, player: UnoPlayer, count: int) -> list[UnoCard]:
        """Rút `count` lá cho player, tự tái tạo deck nếu cạn."""
        drawn = []
        for _ in range(count):
            if not self.deck:
                self._reshuffle()
            if self.deck:
                drawn.append(self.deck.pop())
        player.hand.extend(drawn)
        player.uno_called = False  # Sau khi rút bài, UNO flag reset
        return drawn

    def _reshuffle(self):
        """Tái tạo deck từ discard pile (giữ lại lá top)."""
        if len(self.discard_pile) <= 1:
            return
        top = self.discard_pile.pop()
        random.shuffle(self.discard_pile)
        self.deck = self.discard_pile[:]
        self.discard_pile = [top]

    # ------------------------------------------------------------------
    def play_card(
        self,
        player: UnoPlayer,
        card: UnoCard,
        chosen_color: Optional[Color] = None,
        stacking: bool = False,
    ) -> tuple[bool, str]:
        """
        Người chơi đánh một lá.
        stacking=True: bỏ qua kiểm tra can_play_on (dùng khi combo +2/+4).
        Trả về (success, message).
        """
        if card not in player.hand:
            return False, "Bài không có trong tay bạn."

        if not stacking and not card.can_play_on(self.top_card, self.current_color):
            return False, (
                f"Lá {card.display()} không hợp lệ!\n"
                f"Lá trên bàn: {self.top_card.display()} — màu: {COLOR_EMOJI[self.current_color]}"
            )

        # Wild+4: có thể đánh bất cứ lúc nào

        # Thực hiện đánh bài
        player.hand.remove(card)
        self.discard_pile.append(card)
        self.turn_count += 1
        self.last_player_id = player.user_id

        # Cập nhật màu
        if card.value in WILD_VALUES:
            self.current_color = chosen_color or random.choice(PLAYABLE_COLORS)
        else:
            self.current_color = card.color

        # Reset UNO flag
        player.uno_called = False
        player.afk_count = 0

        # Kiểm tra thắng
        if not player.hand:
            self.winner_id = player.user_id
            self.phase = GamePhase.FINISHED
            return True, "WIN"

        # Đánh dấu cần hô UNO nếu còn 1 lá
        if len(player.hand) == 1:
            self.uno_pending_user_id = player.user_id
            self.uno_safe = False
        else:
            self.uno_pending_user_id = None

        return True, "OK"

    # ------------------------------------------------------------------
    def apply_card_effect(self, card: UnoCard) -> dict:
        """
        Áp dụng hiệu ứng sau khi đánh bài thành công.
        Trả về dict mô tả hiệu ứng đã xảy ra.
        """
        effect = {"skipped": False, "reversed": False, "draw": 0, "wild": False}

        if card.value == Value.SKIP:
            effect["skipped"] = True
            self._advance_turn()  # bỏ qua người kế

        elif card.value == Value.REVERSE:
            effect["reversed"] = True
            self.direction *= -1
            if len(self.players) == 2:
                # 2 người: reverse = skip
                effect["skipped"] = True
                self._advance_turn()

        elif card.value == Value.DRAW2:
            # Dồn vào pending — không rút ngay, người tiếp phải xử lý
            self.pending_draw += 2
            self.pending_draw_type = "draw2"
            effect["draw"] = self.pending_draw
            effect["stacking"] = self.pending_draw > 2

        elif card.value == Value.WILD4:
            effect["wild"] = True
            # Dồn vào pending — không rút ngay, người tiếp phải xử lý
            self.pending_draw += 4
            self.pending_draw_type = "wild4"
            effect["draw"] = self.pending_draw
            effect["stacking"] = self.pending_draw > 4

        elif card.value == Value.WILD:
            effect["wild"] = True

        # Chuyển lượt (SKIP/REVERSE đã tự advance thêm 1 lần ở trên)
        self._advance_turn()

        return effect

    # ------------------------------------------------------------------
    def resolve_pending_draw(self, player: UnoPlayer) -> list[UnoCard]:
        """
        Người chơi chịu phạt: rút toàn bộ lá đang dồn, reset pending.
        Trả về danh sách lá vừa rút.
        """
        count = self.pending_draw
        self.pending_draw = 0
        self.pending_draw_type = None
        drawn = self.draw_cards(player, count)
        return drawn

    # ------------------------------------------------------------------
    def _advance_turn(self):
        """Chuyển sang người tiếp theo theo chiều hiện tại."""
        n = len(self.players)
        self.current_player_index = (self.current_player_index + self.direction) % n
        self.turn_token = uuid4().hex() if callable(uuid4().hex) else uuid4().hex

    def _peek_next_player(self) -> UnoPlayer:
        """Xem người tiếp theo mà không chuyển lượt."""
        n = len(self.players)
        idx = (self.current_player_index + self.direction) % n
        return self.players[idx]

    def advance_turn(self):
        """Public method: chuyển lượt (dùng sau khi xử lý Wild+4)."""
        self._advance_turn()

    # ------------------------------------------------------------------
    def call_uno(self, user_id: int) -> tuple[bool, str]:
        """Người chơi hô UNO."""
        if self.uno_pending_user_id != user_id:
            return False, "Bạn không cần hô UNO lúc này!"
        player = self.get_player(user_id)
        if not player or len(player.hand) != 1:
            return False, "Bạn không còn đúng 1 lá để hô UNO."
        player.uno_called = True
        self.uno_safe = True
        return True, "OK"

    def accuse_uno(self, accuser_id: int, target_id: int) -> tuple[str, int]:
        """
        Tố cáo người chơi chưa hô UNO.
        Trả về (result, draw_count):
          - ("success", 2): tố thành công, target rút 2 lá
          - ("fail", 1): tố sai, accuser rút 1 lá
          - ("invalid", 0): không hợp lệ
        """
        if self.uno_pending_user_id != target_id:
            return "invalid", 0

        target = self.get_player(target_id)
        accuser = self.get_player(accuser_id)
        if not target or not accuser:
            return "invalid", 0

        if len(target.hand) != 1:
            return "invalid", 0

        if not self.uno_safe:  # chưa hô
            self.draw_cards(target, 2)
            self.uno_pending_user_id = None
            return "success", 2
        else:  # đã hô rồi
            self.draw_cards(accuser, 1)
            return "fail", 1

    # ------------------------------------------------------------------
    def handle_afk(self, player: UnoPlayer) -> tuple[bool, list[UnoCard]]:
        """
        Timeout một lượt: rút 1 lá, tăng AFK count.
        Trả về (kicked, drawn_cards).
        """
        player.afk_count += 1
        drawn = self.draw_cards(player, 1)

        if player.afk_count >= 3:
            self.remove_player(player.user_id)
            return True, drawn
        return False, drawn

    # ------------------------------------------------------------------
    def get_board_summary(self) -> dict:
        """Tóm tắt trạng thái bàn để hiển thị."""
        return {
            "top_card": self.top_card.display(),
            "current_color": self.current_color,
            "direction": "➡️ Thuận" if self.direction == 1 else "⬅️ Ngược",
            "deck_count": len(self.deck),
            "current_player": self.current_player.username,
            "current_player_id": self.current_player.user_id,
            "players": [
                {
                    "username": p.username,
                    "user_id": p.user_id,
                    "card_count": len(p.hand),
                    "uno": p.uno_called,
                    "is_current": p.user_id == self.current_player.user_id,
                }
                for p in self.players
            ],
            "turn_count": self.turn_count,
        }

    # ------------------------------------------------------------------
    def calculate_rewards(self) -> dict[int, int]:
        """
        Tính tiền thắng/thua.
        Người thắng nhận cược * (số người - 1).
        Người thua mất cược.
        """
        rewards: dict[int, int] = {}
        if not self.winner_id:
            return rewards

        for p in self.players:
            if p.user_id == self.winner_id:
                rewards[p.user_id] = self.bet * (len(self.players) - 1)
            else:
                rewards[p.user_id] = -self.bet

        return rewards
