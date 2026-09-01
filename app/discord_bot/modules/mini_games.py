"""Mini games nhỏ cho phần simulator, giúp khoảnh khắc nhận quà bớt nhàm chán.

Gồm 3 mini game:
- DungeonCrawlView  : Hầm mộ 5 phòng (gắn vào i?explore) — chọn cửa, né bẫy, nâng bậc cổ vật.
- ChestPuzzleView   : Giải mật mã cổ (câu đố vui 12 giây, gửi dạng ephemeral) — dùng độc lập
                      hoặc được DungeonCrawlView gọi khi mở phòng mật mã.
- WorkRushView      : Bốc hàng đúng nhịp (gắn vào i?work) — bấm nút khi xe đẩy chạy vào
                      vùng xanh để nhận thêm 15-25% lương.

Nguyên tắc: phần thưởng nền giữ nguyên như cơ chế cũ; mini game chỉ thêm biến động bậc
độ hiếm (±1 bậc) hoặc thưởng kỹ năng có trần. Timeout/rời giữa chừng vẫn nhận đủ phần
thưởng nền, không phạt.

Module này KHÔNG import từ package cogs để tránh circular import — mọi dữ liệu
(TREASURES, economy, logger của cog...) được truyền vào qua constructor.
"""

import asyncio
import logging
import random
import time
from typing import Awaitable, Callable, Optional
from uuid import uuid4

import discord

from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Cấu hình cân bằng (tùy chỉnh được mà không phải sửa logic)
# ─────────────────────────────────────────────────────────────────────────────
DUNGEON_ROOMS = 5
DUNGEON_TIMEOUT = 120.0          # tổng thời gian thám hiểm (giây)
RIDDLE_SECONDS = 12.0            # thời gian giải mật mã
RUSH_STEPS = 5                   # số bước chạy của xe đẩy
RUSH_STEP_SECONDS = 1.2          # thời gian mỗi bước (giữ ~1.2s/edit để tránh 429)
RUSH_WINDOW_SECONDS = 0.7        # cửa sổ bấm tính từ lúc vùng xanh hiển thị
RUSH_VIEW_TIMEOUT = 25.0         # timeout của view (lớn hơn tổng thời gian chạy)

TIER_ORDER = ["Thường", "Hiếm", "Quý hiếm", "Huyền thoại", "Thần thoại"]

# Trọng số kết quả của mỗi cánh cửa, theo cấp bản đồ.
# LƯU Ý CÂN BẰNG: giá trị cổ vật giữa các bậc chênh ~4 lần nên phần thưởng theo BẬC
# chỉ được phép chạy qua shrine (+1) và trap (−1, kẹp sàn Thường) với tần suất đã được
# mô phỏng để EV cổ vật lệch < ±5% so với luồng cũ. Riddle/perfect dùng VND phẳng.
DOOR_OUTCOME_WEIGHTS = {
    "normal": {"safe": 58, "loot": 24, "trap": 10, "shrine": 2, "riddle": 6},
    "rare":   {"safe": 54, "loot": 27, "trap": 8, "shrine": 2, "riddle": 9},
    "legend": {"safe": 50, "loot": 30, "trap": 8, "shrine": 2, "riddle": 10},
}

# Thưởng VND phẳng (tuyến tính theo cấp bản đồ, không nhân bậc => không lạm phát EV)
RIDDLE_BONUS_VND = {
    "normal": (300_000, 800_000),
    "rare": (1_000_000, 3_000_000),
    "legend": (4_000_000, 12_000_000),
}
PERFECT_BONUS_VND = {
    "normal": (800_000, 2_000_000),
    "rare": (3_000_000, 8_000_000),
    "legend": (8_000_000, 20_000_000),
}

# Phần thưởng rương phụ (loot) theo cấp bản đồ
LOOT_VND_RANGE = {
    "normal": (50_000, 300_000),
    "rare": (150_000, 900_000),
    "legend": (500_000, 2_500_000),
}
LOOT_GOLD_RANGE = {
    "normal": (0.0, 0.0),      # bản đồ thường chỉ rơi VND
    "rare": (0.01, 0.04),
    "legend": (0.03, 0.10),
}
LOOT_GOLD_CHANCE = {            # xác suất rơi vàng thay vì VND (khi cấp bản đồ có vàng)
    "normal": 0.0,
    "rare": 0.35,
    "legend": 0.45,
}

DOOR_LABELS = [
    ("⚰️", "Quan Tài"),
    ("🕳️", "Cống Ngầm"),
    ("🗿", "Tượng Đá"),
]

# Câu đố vui cho Giải mật mã: đúng = không phạt, sai = mất cơ hội cộng bậc
RIDDLES = [
    {"q": "Con gì đi thì nằm, đứng cũng nằm, nhưng nằm lại đứng?",
     "correct": "Bàn chân", "wrong": ["Bàn tay", "Cái gối"]},
    {"q": "Con gì đầu dê mình ốc?",
     "correct": "Con dốc", "wrong": ["Con dê", "Con ốc sên"]},
    {"q": "Cái gì càng đào càng to?",
     "correct": "Cái hố", "wrong": ["Cái giếng", "Cái nồi"]},
    {"q": "Tháng nào có 28 ngày?",
     "correct": "Tháng nào cũng có", "wrong": ["Tháng Hai", "Tháng Sáu"]},
    {"q": "Con gì không cánh mà bay?",
     "correct": "Con cầu", "wrong": ["Con gà", "Con vịt"]},
    {"q": "Cái gì trong trắng ngoài xanh, trồng đậu trồng hành rồi thả heo vào?",
     "correct": "Cái bể nước", "wrong": ["Cái ao", "Cái vườn"]},
    {"q": "Mèo nào không biết bắt chuột?",
     "correct": "Mèo con", "wrong": ["Mèo đen", "Mèo mướp"]},
    {"q": "Cái gì càng cháy càng ngắn?",
     "correct": "Cây nến", "wrong": ["Cái lò", "Đèn dầu"]},
    {"q": "Cái gì là của bạn nhưng người khác lại dùng nhiều hơn bạn?",
     "correct": "Tên của bạn", "wrong": ["Cái ví", "Chiếc điện thoại"]},
    {"q": "Cái gì miệng rộng, bụng rỗng, cả làng cùng ăn mà vẫn no?",
     "correct": "Cái giếng", "wrong": ["Cái chợ", "Cái lò"]},
]


def pick_riddle() -> tuple[str, list[str], str]:
    """Chọn ngẫu nhiên 1 câu đố, trộn vị trí đáp án. Trả về (câu hỏi, các lựa chọn, đáp án đúng)."""
    r = random.choice(RIDDLES)
    options = [r["correct"], *r["wrong"]][:3]
    random.shuffle(options)
    return r["q"], options, r["correct"]


async def _refuse_other(interaction: discord.Interaction, message: str) -> None:
    try:
        await interaction.response.send_message(message, ephemeral=True)
    except Exception:
        pass


async def _safe_defer(interaction: discord.Interaction) -> None:
    try:
        await interaction.response.defer()
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────────────────────
# 🔓 Giải mật mã rương (Chest Puzzle)
# ─────────────────────────────────────────────────────────────────────────────
class RiddleAnswerButton(discord.ui.Button):
    def __init__(self, answer: str):
        super().__init__(
            label=answer[:80],
            style=discord.ButtonStyle.primary,
            custom_id=f"riddle_answer_{uuid4().hex[:6]}",
        )
        self.answer = answer

    async def callback(self, interaction: discord.Interaction):
        await self.view.answer(interaction, self.answer)


class ChestPuzzleView(discord.ui.View):
    """Mini game giải mật mã dạng câu đố. Gắn được vào bất kỳ interaction nào.

    on_result: coroutine nhận True/False khi người chơi trả lời hoặc hết giờ.
    Nên gửi kèm view bằng followup ephemeral để đáp án không lộ ra kênh chung.
    """

    def __init__(self, on_result: Callable[[bool], Awaitable[None]], user_id: int, timeout: float = RIDDLE_SECONDS):
        super().__init__(timeout=timeout)
        self.on_result = on_result
        self.user_id = user_id
        self.finished = False
        self.lock = asyncio.Lock()
        self.message: Optional[discord.Message] = None
        self.question, self.options, self.correct = pick_riddle()
        for opt in self.options:
            self.add_item(RiddleAnswerButton(opt))

    def build_embed(self) -> discord.Embed:
        return make_embed(
            title="🔐 GIẢI MẬT MÃ CỔ 🔐",
            description=(
                f"**Câu đố:** {self.question}\n\n"
                f"⏰ Bạn có **{int(RIDDLE_SECONDS)} giây** để chọn đáp án.\n"
                f"🎉 Đúng: lục thêm **kho báu phụ** bằng VND (theo cấp bản đồ).\n"
                f"❌ Sai: không bị phạt, chỉ mất cơ hội thôi."
            ),
            color=discord.Color.blurple(),
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await _refuse_other(interaction, "❌ Đây không phải câu đố của bạn!")
            return False
        return True

    async def answer(self, interaction: discord.Interaction, answer: str):
        async with self.lock:
            if self.finished:
                await _safe_defer(interaction)
                return
            self.finished = True
            self.stop()
            correct = (answer == self.correct)
            if correct:
                result_embed = make_embed(
                    title="🔓 GIẢI MÃ THÀNH CÔNG!",
                    description=f"🎉 **CHÍNH XÁC!** Mật mã cổ đã được mở.",
                    color=discord.Color.green(),
                )
            else:
                result_embed = make_embed(
                    title="🔒 GIẢI MÃ THẤT BẠI",
                    description=f"❌ **SAI RỒI!** Đáp án đúng là: **{self.correct}**",
                    color=discord.Color.red(),
                )
            try:
                await interaction.response.edit_message(embed=result_embed, view=None)
            except Exception:
                pass
        try:
            await self.on_result(correct)
        except Exception:
            logger.exception("ChestPuzzleView.on_result lỗi")

    async def on_timeout(self):
        async with self.lock:
            if self.finished:
                return
            self.finished = True
        if self.message:
            try:
                embed = make_embed(
                    title="⏰ HẾT GIỜ GIẢI MÃ",
                    description=f"⏰ Hết giờ! Đáp án đúng là: **{self.correct}**",
                    color=discord.Color.red(),
                )
                await self.message.edit(embed=embed, view=None)
            except Exception:
                pass
        try:
            await self.on_result(False)
        except Exception:
            logger.exception("ChestPuzzleView.on_result lỗi (timeout)")


# ─────────────────────────────────────────────────────────────────────────────
# 🗺️ Hầm mộ 5 phòng (Dungeon Crawl) — gắn vào i?explore
# ─────────────────────────────────────────────────────────────────────────────
class DungeonDoorButton(discord.ui.Button):
    def __init__(self, index: int, emoji: str, label: str):
        super().__init__(
            label=label,
            emoji=emoji,
            style=discord.ButtonStyle.secondary,
            custom_id=f"dungeon_door_{index}_{uuid4().hex[:6]}",
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        await self.view.open_door(interaction, self.index)


class DungeonLeaveButton(discord.ui.Button):
    def __init__(self):
        super().__init__(
            label="Rời hầm ngay",
            emoji="🚪",
            style=discord.ButtonStyle.danger,
            custom_id=f"dungeon_leave_{uuid4().hex[:6]}",
        )

    async def callback(self, interaction: discord.Interaction):
        await self.view.leave_dungeon(interaction)


class DungeonCrawlView(discord.ui.View):
    """Thám hiểm hầm mộ 5 phòng thay cho phần nhận cổ vật tức thì của i?explore.

    - Độ hiếm nền được roll TRƯỚC bằng đúng bảng cũ của lệnh explore (EV nền không đổi).
    - Kết quả từng cánh cửa được pre-roll lúc tạo view.
    - Bẫy: −1 bậc cổ vật cuối. Đền thờ: +1 bậc. Giải mật mã đúng: +1 bậc.
      Đi qua cả 5 phòng không dính bẫy: +1 bậc.
    - Rời hầm/timeout: vẫn resolve cổ vật theo tiến độ hiện tại (bản đồ đã trừ).
    """

    def __init__(
        self,
        cog,
        user: discord.User | discord.Member,
        economy,
        map_type: str,
        map_name: str,
        base_rarity: str,
        treasures: dict,
        ctx=None,
    ):
        super().__init__(timeout=DUNGEON_TIMEOUT)
        self.cog = cog
        self.economy = economy
        self.user = user
        self.user_id = user.id
        self.map_type = map_type
        self.map_name = map_name
        self.base_rarity = base_rarity
        self.treasures = treasures
        self.ctx = ctx
        self.message: Optional[discord.Message] = None

        self.finished = False
        self.awaiting_riddle = False
        self.lock = asyncio.Lock()

        self.room_index = 0
        self.score = 0            # điểm sạch: phòng qua được mà không dính bẫy
        self.trap_hits = 0
        self.shrine_hits = 0
        self.riddle_success = False
        self.riddle_bonus = 0
        self.path_log: list[str] = []
        self.rooms = [self._roll_room_outcomes() for _ in range(DUNGEON_ROOMS)]

        self.door_buttons = [
            DungeonDoorButton(i, emoji, label) for i, (emoji, label) in enumerate(DOOR_LABELS)
        ]
        self.leave_button = DungeonLeaveButton()
        for btn in self.door_buttons:
            self.add_item(btn)
        self.add_item(self.leave_button)

    # ── Sinh dữ liệu ──
    def _roll_room_outcomes(self) -> list[str]:
        weights = DOOR_OUTCOME_WEIGHTS.get(self.map_type, DOOR_OUTCOME_WEIGHTS["normal"])
        keys = list(weights.keys())
        w = [weights[k] for k in keys]
        outcomes = [random.choices(keys, weights=w, k=1)[0] for _ in range(3)]
        if all(o == "trap" for o in outcomes):
            outcomes[random.randrange(3)] = "safe"
        random.shuffle(outcomes)
        return outcomes

    # ── Render ──
    def render_embed(self, result_line: str | None = None) -> discord.Embed:
        room_no = min(self.room_index + 1, DUNGEON_ROOMS)
        desc = (
            f"🧭 **Thám hiểm:** {self.user.mention}\n"
            f"📜 **Bản đồ:** {self.map_name}\n"
            f"🎁 **Cổ vật nền:** `{self.base_rarity}` (bậc cuối phụ thuộc hành trình)\n"
            f"🚪 **Tiến độ:** `Phòng {room_no}/{DUNGEON_ROOMS}` • 🎯 **Điểm sạch:** `{self.score}/{DUNGEON_ROOMS}`\n"
        )
        if result_line:
            desc += f"\n{result_line}\n"
        if self.path_log:
            desc += "\n📝 **Nhật ký hành trình:**\n" + "\n".join(self.path_log[-8:])
        desc += (
            "\n\n⚙️ **Luật chơi:** 💥 Bẫy → cổ vật **−1 bậc** • 🛕 Đền thờ → **+1 bậc** "
            "• 🔓 Giải mã đúng → **thưởng VND** • Đi hết 5 phòng không dính bẫy → **thưởng hoàn hảo**."
        )
        embed = make_embed(
            title="🗺️ THÁM HIỆM HẦM MỘ CỔ ĐẠI 🗺️",
            description=desc,
            color=discord.Color.dark_purple(),
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        return embed

    async def _safe_edit(self, **kwargs):
        if not self.message:
            return
        try:
            await self.message.edit(**kwargs)
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await _refuse_other(interaction, "❌ Đây không phải chuyến thám hiểm của bạn!")
            return False
        return True

    # ── Tương tác ──
    async def open_door(self, interaction: discord.Interaction, index: int):
        async with self.lock:
            if self.finished:
                await _safe_defer(interaction)
                return
            if self.awaiting_riddle:
                try:
                    await interaction.response.send_message(
                        "🔐 Bạn đang giải mật mã! Hoàn thành ở tin nhắn riêng đã.",
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return
            await _safe_defer(interaction)

            outcome = self.rooms[self.room_index][index]
            door_emoji, door_label = DOOR_LABELS[index]
            door_name = f"{door_emoji} {door_label}"

            if outcome == "riddle":
                self.awaiting_riddle = True
                self.path_log.append(f"`P{self.room_index + 1}` {door_name} → 🔐 Phòng mật mã")
                await self._safe_edit(embed=self.render_embed(
                    "🔐 Cánh cửa khắc mật mã cổ! **Câu đố đã gửi qua tin nhắn riêng** — giải trong "
                    f"{int(RIDDLE_SECONDS)} giây!"
                ))
                asyncio.create_task(self._send_riddle(interaction))
                return

            result_line = self._apply_outcome(outcome, door_name)
            self.room_index += 1
            if self.room_index >= DUNGEON_ROOMS:
                await self._resolve_locked(result_line)
            else:
                await self._safe_edit(embed=self.render_embed(result_line))

    async def leave_dungeon(self, interaction: discord.Interaction):
        async with self.lock:
            if self.finished:
                await _safe_defer(interaction)
                return
            if self.awaiting_riddle:
                try:
                    await interaction.response.send_message(
                        "🔐 Đang giải mật mã, không thể rời giữa chừng!",
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return
            await _safe_defer(interaction)
            await self._resolve_locked("🚪 Bạn quyết định rời hầm ngay với những gì đang có...")

    # ── Xử lý kết quả từng phòng ──
    def _apply_outcome(self, outcome: str, door_name: str) -> str:
        room_no = self.room_index + 1
        if outcome == "trap":
            self.trap_hits += 1
            self.path_log.append(f"`P{room_no}` {door_name} → 💥 Dính bẫy (−1 bậc)")
            return (
                f"💥 **{door_name}:** SẬP BẪY! Bạn lăn ra ngoài trong đường tơ kẽ tóc nhưng cổ vật "
                f"bị va đập mạnh. (Cổ vật cuối **−1 bậc**) *Tiếp tục đi phòng sau...*"
            )
        if outcome == "shrine":
            self.shrine_hits += 1
            self.score += 1
            self.path_log.append(f"`P{room_no}` {door_name} → 🛕 Đền thờ (+1 bậc, +1 điểm)")
            return (
                f"🛕 **{door_name}:** Bàn thờ cổ vẫn còn linh thiêng. Bạn khấn vái một câu và được "
                f"phù hộ! (Cổ vật cuối **+1 bậc**) *Tiếp tục đi phòng sau...*"
            )
        if outcome == "loot":
            self.score += 1
            text = self._grant_side_loot(room_no, door_name)
            return text

        # safe
        self.score += 1
        self.path_log.append(f"`P{room_no}` {door_name} → 🧹 Trống trơn (+1 điểm)")
        return (
            f"🧹 **{door_name}:** Hành lang trống trơn, chỉ có gió lạnh thổi qua. Bạn lẻn qua an toàn. "
            f"(+1 điểm sạch) *Tiếp tục đi phòng sau...*"
        )

    def _grant_side_loot(self, room_no: int, door_name: str) -> str:
        """Rương phụ: VND hoặc vàng lẻ (tích lũy phân số rồi đúc thành thỏi như cơ chế đào mỏ)."""
        min_vnd, max_vnd = LOOT_VND_RANGE.get(self.map_type, LOOT_VND_RANGE["normal"])
        gold_chance = LOOT_GOLD_CHANCE.get(self.map_type, 0.0)
        use_gold = gold_chance > 0 and random.random() < gold_chance

        if use_gold:
            min_g, max_g = LOOT_GOLD_RANGE.get(self.map_type, (0.0, 0.0))
            gold = round(random.uniform(min_g, max_g), 3)
            stats = self.economy.get_simulator_stats(self.user_id)
            new_frac = stats[3] + gold
            int_gold = int(new_frac)
            self.economy.set_simulator_stats(self.user_id, fractional_gold=round(new_frac - int_gold, 4))
            if int_gold > 0:
                self.economy.add_credits(self.user_id, int_gold)
            log_wallet_change(
                logger,
                event="dungeon_side_loot_gold",
                user_id=self.user_id,
                credits_delta=int_gold,
                ctx=self.ctx,
                room=room_no,
                gold=gold,
            )
            cast_note = f" (tự động đúc `{int_gold}` thỏi vào két)" if int_gold > 0 else ""
            self.path_log.append(f"`P{room_no}` {door_name} → ✨ Vàng +{gold:.2f}")
            return (
                f"✨ **{door_name}:** Trong góc phòng có mạch vàng nhỏ `+{gold:.2f} Vàng`{cast_note}! "
                f"(+1 điểm sạch) *Tiếp tục đi phòng sau...*"
            )

        vnd = random.randint(min_vnd, max_vnd)
        self.economy.add_money(self.user_id, vnd)
        log_wallet_change(
            logger,
            event="dungeon_side_loot",
            user_id=self.user_id,
            money_delta=vnd,
            ctx=self.ctx,
            room=room_no,
        )
        self.path_log.append(f"`P{room_no}` {door_name} → 💰 +{vnd:,} VND")
        return (
            f"💰 **{door_name}:** Rương phụ chứa `+{vnd:,} VND`! "
            f"(+1 điểm sạch) *Tiếp tục đi phòng sau...*"
        )

    async def _send_riddle(self, interaction: discord.Interaction):
        """Gửi câu đố ephemeral (chạy ngoài lock của view)."""

        async def on_result(correct: bool):
            await self._on_riddle_result(correct)

        puzzle = ChestPuzzleView(on_result, self.user_id)
        try:
            msg = await interaction.followup.send(embed=puzzle.build_embed(), view=puzzle, ephemeral=True)
            puzzle.message = msg
        except Exception:
            logger.exception("Không gửi được câu đố hầm mộ, bỏ qua phòng mật mã")
            await self._on_riddle_result(False)

    async def _on_riddle_result(self, correct: bool):
        async with self.lock:
            if self.finished or not self.awaiting_riddle:
                return
            self.awaiting_riddle = False
            if correct:
                self.riddle_success = True
                r0, r1 = RIDDLE_BONUS_VND.get(self.map_type, RIDDLE_BONUS_VND["normal"])
                self.riddle_bonus = random.randint(r0, r1)
                self.economy.add_money(self.user_id, self.riddle_bonus)
                log_wallet_change(
                    logger,
                    event="dungeon_riddle_bonus",
                    user_id=self.user_id,
                    money_delta=self.riddle_bonus,
                    ctx=self.ctx,
                )
            self.score += 1
            room_no = self.room_index + 1
            self.path_log.append(
                f"`P{room_no}` 🔐 Mật mã → {'✅ mở được' if correct else '❌ sai mã'}"
            )
            if correct:
                result_line = (
                    f"🔓 **Giải mã thành công!** Cánh cửa hé mở, bạn còn lục được kho báu phụ "
                    f"`+{self.riddle_bonus:,} VND`! *Tiếp tục đi phòng sau...*"
                )
            else:
                result_line = (
                    "🔒 **Sai mật mã!** Cánh cửa từ chối bạn, nhưng may thay hành lang bên cạnh vẫn thông. "
                    "(Không bị phạt) *Tiếp tục đi phòng sau...*"
                )
            self.room_index += 1
            if self.room_index >= DUNGEON_ROOMS:
                await self._resolve_locked(result_line)
            else:
                await self._safe_edit(embed=self.render_embed(result_line))

    # ── Kết thúc ──
    async def _resolve_locked(self, intro_line: str):
        if self.finished:
            return
        self.finished = True
        self.awaiting_riddle = False
        self.stop()

        explorers = getattr(self.cog, "active_explorers", None) if self.cog else None
        if explorers is not None:
            explorers.discard(self.user_id)

        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True

        # Tính bậc cuối: nền → trừ bẫy (kẹp sàn Thường) → cộng đền thờ.
        # Riddle/hoàn hảo KHÔNG nâng bậc — thang giá trị bậc là cấp số nhân (~x4/bậc), nâng
        # bậc theo kỹ năng sẽ làm EV lệch hàng trăm % (đã mô phỏng); chúng trả VND phẳng.
        tier_idx = TIER_ORDER.index(self.base_rarity) if self.base_rarity in TIER_ORDER else 0
        tier_idx = max(0, tier_idx - self.trap_hits) + self.shrine_hits
        tier_idx = min(tier_idx, len(TIER_ORDER) - 1)
        final_rarity = TIER_ORDER[tier_idx]

        pool = [k for k, v in self.treasures.items() if v.get("rarity") == final_rarity]
        while not pool and tier_idx > 0:
            tier_idx -= 1
            final_rarity = TIER_ORDER[tier_idx]
            pool = [k for k, v in self.treasures.items() if v.get("rarity") == final_rarity]

        treasure = None
        chosen_id = None
        if pool:
            chosen_id = random.choice(pool)
            treasure = self.treasures[chosen_id]
            self.economy.add_inventory_item(self.user_id, chosen_id, 1)
            log_wallet_change(
                logger,
                event="dungeon_exploration_success",
                user_id=self.user_id,
                item_id=chosen_id,
                quantity=1,
                ctx=self.ctx,
                base_rarity=self.base_rarity,
                final_rarity=final_rarity,
                score=self.score,
                trap_hits=self.trap_hits,
                shrine_hits=self.shrine_hits,
                riddle_success=self.riddle_success,
            )
        else:
            logger.error("DungeonCrawlView: không tìm thấy cổ vật cho bậc %s", final_rarity)

        changes = []
        if self.trap_hits:
            changes.append(f"💥 Bẫy x{self.trap_hits} (−{self.trap_hits} bậc)")
        if self.shrine_hits:
            changes.append(f"🛕 Đền thờ x{self.shrine_hits} (+{self.shrine_hits} bậc)")
        changes_str = " • ".join(changes) if changes else "không có biến động"

        bonus_lines = []
        if self.riddle_bonus > 0:
            bonus_lines.append(f"🔓 Giải mã đúng: `+{self.riddle_bonus:,} VND`")
        if self.score >= DUNGEON_ROOMS:
            p0, p1 = PERFECT_BONUS_VND.get(self.map_type, PERFECT_BONUS_VND["normal"])
            perfect_bonus = random.randint(p0, p1)
            self.economy.add_money(self.user_id, perfect_bonus)
            log_wallet_change(
                logger,
                event="dungeon_perfect_bonus",
                user_id=self.user_id,
                money_delta=perfect_bonus,
                ctx=self.ctx,
                score=self.score,
            )
            bonus_lines.append(f"⭐ Hoàn hảo {self.score}/{DUNGEON_ROOMS}: `+{perfect_bonus:,} VND`")

        path_str = "\n".join(self.path_log) if self.path_log else "*Không đi phòng nào...*"
        desc = (
            f"{intro_line}\n\n"
            f"📝 **Nhật ký hành trình:**\n{path_str}\n\n"
            f"🎯 **Điểm sạch:** `{self.score}/{DUNGEON_ROOMS}`\n"
            f"⚖️ **Biến động bậc:** {changes_str}\n"
            f"🎁 **Cổ vật nền:** `{self.base_rarity}` → **Kết quả:** `{final_rarity}`\n"
        )
        if bonus_lines:
            desc += "🏅 **Thưởng hành trình:**\n" + "\n".join(bonus_lines) + "\n"
        desc += "\n"
        if treasure:
            desc += (
                f"🏺 **Cổ vật nhận được:** {treasure['name']} (ID: `{chosen_id}`)\n"
                f"✨ **Độ hiếm:** `{treasure['rarity']}`\n"
                f"💰 **Giá trị:** `{treasure['value']:,} VND`\n\n"
                f"💡 *Dùng `i?sellitem {chosen_id}` để bán cho viện bảo tàng, hoặc giữ lại sưu tầm & trưng bày.*"
            )
        else:
            desc += "🫥 Chuyến đi không để lại cổ vật nào..."

        embed = make_embed(
            title="🏆 KẾT QUẢ THÁM HIỆM HẦM MỘ 🏆",
            description=desc,
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=self.user.display_avatar.url)
        await self._safe_edit(embed=embed, view=self)

    async def on_timeout(self):
        async with self.lock:
            if self.finished:
                return
            await self._resolve_locked("⏰ Hết thời gian! Đoàn thám hiểm đành rời hầm với những gì đang có...")


# ─────────────────────────────────────────────────────────────────────────────
# 💼 Bốc hàng đúng nhịp (Work Rush) — gắn vào i?work
# ─────────────────────────────────────────────────────────────────────────────
class WorkRushView(discord.ui.View):
    """Mini game phản xạ sau ca làm: xe đẩy chạy qua 5 ô, 1 ô là vùng xanh.

    Bấm nút 📦 khi xe đẩy đang ở vùng xanh (trong ~0.7s) → được cộng 15-25% lương
    qua callback grant_bonus. Bấm sớm → được nhắc, không phạt. Bấm trượt/hết giờ →
    giữ nguyên lương gốc.
    """

    def __init__(
        self,
        grant_bonus: Callable[[discord.User | discord.Member, int], Awaitable[int]],
        user: discord.User | discord.Member,
        base_reward: int,
        base_embed: discord.Embed,
        ctx=None,
    ):
        super().__init__(timeout=RUSH_VIEW_TIMEOUT)
        self.grant_bonus = grant_bonus
        self.user = user
        self.user_id = user.id
        self.base_reward = base_reward
        self.base_embed = base_embed
        self.ctx = ctx
        self.message: Optional[discord.Message] = None

        self.finished = False
        self.lock = asyncio.Lock()
        self.step = -1
        self.green_index = random.randint(1, RUSH_STEPS - 2)
        self.green_shown_at: Optional[float] = None
        self.animate_task: Optional[asyncio.Task] = None
        self.original_description = base_embed.description or ""

    # ── Render ──
    def _render_bar(self, step: int) -> str:
        line1 = "".join("[▓▓▓]" if i == self.green_index else "[   ]" for i in range(RUSH_STEPS))
        line2 = " " * (step * 5 + 2) + "▲"
        return f"```\n{line1}\n{line2}\n```"

    def _embed_with(self, description: str) -> discord.Embed:
        embed = self.base_embed
        embed.description = description
        return embed

    def _animated_description(self, step: int) -> str:
        header = (
            "🚚 **BỐC HÀNG ĐÚNG NHỊP!** Bấm nút 📦 khi xe đẩy chạy vào **vùng xanh** "
            f"để nhận thêm **15%~25% lương**!\n{self._render_bar(step)}"
        )
        return f"{self.original_description}\n\n{header}"

    async def _safe_edit(self, **kwargs):
        if not self.message:
            return
        try:
            await self.message.edit(**kwargs)
        except Exception:
            pass

    # ── Vòng đời ──
    def start(self):
        if self.animate_task is None:
            self.animate_task = asyncio.create_task(self._animate())

    async def _animate(self):
        try:
            for step in range(RUSH_STEPS):
                async with self.lock:
                    if self.finished:
                        return
                    self.step = step
                    if step == self.green_index:
                        self.green_shown_at = time.monotonic()
                    await self._safe_edit(embed=self._embed_with(self._animated_description(step)))
                await asyncio.sleep(RUSH_STEP_SECONDS)
            async with self.lock:
                if not self.finished:
                    await self._finish_locked(None, cancel_anim=False)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("WorkRushView animation lỗi")

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await _refuse_other(interaction, "❌ Đây không phải ca làm việc của bạn!")
            return False
        return True

    @discord.ui.button(label="Bốc Hàng!", emoji="📦", style=discord.ButtonStyle.success)
    async def rush_click(self, interaction: discord.Interaction, button: discord.ui.Button):
        async with self.lock:
            if self.finished:
                await _safe_defer(interaction)
                return
            now = time.monotonic()
            if self.step < self.green_index or self.green_shown_at is None:
                # Bấm sớm: nhắc nhẹ, không phạt, trò chơi vẫn tiếp tục
                try:
                    await interaction.response.send_message(
                        "⏳ Chưa tới nhịp! Đợi xe đẩy chạy vào **vùng xanh** đã.",
                        ephemeral=True,
                    )
                except Exception:
                    pass
                return
            in_window = (
                self.step == self.green_index
                and (now - self.green_shown_at) <= RUSH_WINDOW_SECONDS
            )
            await _safe_defer(interaction)
            await self._finish_locked(in_window)

    async def _finish_locked(self, success: Optional[bool], cancel_anim: bool = True):
        if self.finished:
            return
        self.finished = True
        for item in self.children:
            if isinstance(item, discord.ui.Button):
                item.disabled = True
        if cancel_anim and self.animate_task and self.animate_task is not asyncio.current_task():
            self.animate_task.cancel()
        self.stop()

        if success is True:
            try:
                bonus = await self.grant_bonus(self.user, self.base_reward, self.ctx)
            except Exception:
                logger.exception("grant_bonus lỗi trong WorkRushView")
                bonus = 0
            if bonus > 0:
                result = (
                    f"\n\n🎉 **CA LÀM HIỆU SUẤT CAO!** Bạn bốc hàng trúng nhịp, nhận thêm "
                    f"**`+{bonus:,} VND`** tiền thưởng gánh hàng!"
                )
            else:
                result = "\n\n🎉 **CA LÀM HIỆU SUẤT CAO!** (Không tính được thưởng, hẹn ca sau!)"
        elif success is False:
            result = "\n\n😅 **Trượt nhịp!** Xe hàng đã qua mất rồi — không có thưởng lần này, hẹn ca sau."
        else:
            result = "\n\n😴 **Bỏ phí dịp tốt!** Xe tải rời bãi khi bạn còn đang ngẩn ngơ..."

        self.base_embed.description = f"{self.original_description}{result}"
        await self._safe_edit(embed=self._embed_with(self.base_embed.description), view=self)

    async def on_timeout(self):
        async with self.lock:
            if self.finished:
                return
            await self._finish_locked(None)
