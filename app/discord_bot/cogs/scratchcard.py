import asyncio
from datetime import datetime
import logging
import random
from typing import Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# ── Card Configurations (prices in VND) ──────────────────────────────────────
CARDS_CONFIG = {
    "bronze": {
        "id": "bronze",
        "name": "🥉 Thẻ Cào Đồng",
        "price": 500_000,
        "win_rate": 0.10,
        "symbols": ["🍀", "⭐", "💰", "🎰", "💎"],
        "multipliers": {"🍀": 2, "⭐": 3, "💰": 4, "🎰": 5, "💎": 8},
    },
    "silver": {
        "id": "silver",
        "name": "🥈 Thẻ Cào Bạc",
        "price": 2_000_000,
        "win_rate": 0.07,
        "symbols": ["🍀", "⭐", "💰", "🎰", "💎"],
        "multipliers": {"🍀": 3, "⭐": 4, "💰": 5, "🎰": 8, "💎": 15},
    },
    "gold": {
        "id": "gold",
        "name": "🥇 Thẻ Cào Vàng",
        "price": 10_000_000,
        "win_rate": 0.04,
        "symbols": ["🍀", "⭐", "💰", "🎰", "💎"],
        "multipliers": {"🍀": 5, "⭐": 8, "💰": 10, "🎰": 15, "💎": 25},
    },
    "diamond": {
        "id": "diamond",
        "name": "💎 Thẻ Cào Kim Cương",
        "price": 50_000_000,
        "win_rate": 0.015,
        "symbols": ["🍀", "⭐", "💰", "🎰", "💎"],
        "multipliers": {"🍀": 8, "⭐": 15, "💰": 20, "🎰": 30, "💎": 50},
    },
}

# ── Event Cards ──────────────────────────────────────────────────────────────
EVENT_CARDS = {
    "halloween": {
        "id": "halloween",
        "name": "🎃 Thẻ Halloween",
        "price": 15_000_000,
        "win_rate": 0.05,
        "symbols": ["🍬", "🦇", "👻", "🎃", "💀"],
        "multipliers": {"🍬": 2, "🦇": 4, "👻": 6, "🎃": 10, "💀": 20},
    },
    "christmas": {
        "id": "christmas",
        "name": "🎄 Thẻ Giáng Sinh",
        "price": 40_000_000,
        "win_rate": 0.03,
        "symbols": ["❄️", "🔔", "🎄", "🦌", "🎅"],
        "multipliers": {"❄️": 3, "🔔": 5, "🎄": 8, "🦌": 12, "🎅": 25},
    },
    "tet": {
        "id": "tet",
        "name": "🧧 Thẻ Tết",
        "price": 75_000_000,
        "win_rate": 0.015,
        "symbols": ["🍊", "🦁", "🧧", "🪙", "🌸"],
        "multipliers": {"🍊": 3, "🦁": 5, "🧧": 10, "🪙": 15, "🌸": 30},
    },
}

# Winning symbol selection weights (lower-value symbols more common)
WINNING_SYMBOL_WEIGHTS = [0.50, 0.28, 0.14, 0.06, 0.02]


# ── Helpers ──────────────────────────────────────────────────────────────────

def get_active_event_card() -> Optional[dict]:
    """Returns the currently active event card based on date rules."""
    now = datetime.now()
    if now.month in (1, 2):
        return EVENT_CARDS["tet"]
    if now.month == 12:
        return EVENT_CARDS["christmas"]
    if now.weekday() in (4, 5, 6):  # Fri, Sat, Sun
        return EVENT_CARDS["halloween"]
    return None


def get_all_available_cards() -> dict:
    """Returns standard cards + any currently active event card."""
    cards = dict(CARDS_CONFIG)
    event = get_active_event_card()
    if event:
        cards[event["id"]] = event
    return cards


def generate_scratch_grid(card_cfg: dict) -> tuple[list[str], bool, Optional[str], bool]:
    """
    Generates a 3×3 grid (9 cells).

    Returns (grid, is_win, winning_symbol, has_bonus).
    - Winning grids contain exactly 3 of the winning symbol.
    - Losing grids have no symbol appearing 3+ times.
    - 2% chance one cell is the 🎁 bonus cell.
    """
    is_win = random.random() < card_cfg["win_rate"]
    has_bonus = random.random() < 0.02

    grid: list[str] = [""] * 9
    symbols = card_cfg["symbols"]

    # Optionally place a bonus cell
    if has_bonus:
        grid[random.randint(0, 8)] = "🎁"

    # Place winning triplet
    winning_symbol: Optional[str] = None
    if is_win:
        winning_symbol = random.choices(symbols, weights=WINNING_SYMBOL_WEIGHTS, k=1)[0]
        placed = 0
        while placed < 3:
            idx = random.randint(0, 8)
            if grid[idx] == "":
                grid[idx] = winning_symbol
                placed += 1

    # Fill remaining cells — no other symbol may reach 3 copies
    for idx in range(9):
        if grid[idx] != "":
            continue

        for _ in range(200):
            candidate = random.choice(symbols)
            if is_win and candidate == winning_symbol:
                continue
            if grid.count(candidate) < 2:
                grid[idx] = candidate
                break
        else:
            # Deterministic fallback
            for s in symbols:
                if is_win and s == winning_symbol:
                    continue
                if grid.count(s) < 2:
                    grid[idx] = s
                    break

    return grid, is_win, winning_symbol, has_bonus


# ── UI Components (proper subclassed buttons) ───────────────────────────────

class ScratchCellButton(discord.ui.Button):
    """One of the 9 grid cells."""

    def __init__(self, index: int):
        super().__init__(
            label=str(index + 1),
            style=discord.ButtonStyle.secondary,
            row=index // 3,
        )
        self.index = index

    async def callback(self, interaction: discord.Interaction):
        view: ScratchCardPlayView = self.view
        if view.revealed[self.index]:
            await interaction.response.defer()
            return

        view.revealed[self.index] = True
        view.revealed_count += 1

        self.label = view.grid[self.index]
        self.style = (
            discord.ButtonStyle.primary
            if view.grid[self.index] == "🎁"
            else discord.ButtonStyle.success
        )
        self.disabled = True

        await interaction.response.defer()
        await view.update_display()


class ScratchAllButton(discord.ui.Button):
    """Instantly scratches every remaining cell."""

    def __init__(self):
        super().__init__(
            label="Cào Hết",
            style=discord.ButtonStyle.primary,
            emoji="🎴",
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        view: ScratchCardPlayView = self.view
        for child in view.children:
            if isinstance(child, ScratchCellButton) and not view.revealed[child.index]:
                view.revealed[child.index] = True
                view.revealed_count += 1
                child.label = view.grid[child.index]
                child.style = (
                    discord.ButtonStyle.primary
                    if view.grid[child.index] == "🎁"
                    else discord.ButtonStyle.success
                )
                child.disabled = True

        await interaction.response.defer()
        await view.update_display()


class CancelCardButton(discord.ui.Button):
    """Cancels the card (refund only if no cells scratched)."""

    def __init__(self):
        super().__init__(
            label="Hủy Thẻ",
            style=discord.ButtonStyle.danger,
            emoji="❌",
            row=3,
        )

    async def callback(self, interaction: discord.Interaction):
        view: ScratchCardPlayView = self.view

        if view.revealed_count == 0:
            # Full refund
            view.cog.economy.add_money(view.author.id, view.card_cfg["price"])
            log_wallet_change(
                logger,
                event="scratch_refund",
                user_id=view.author.id,
                money_delta=view.card_cfg["price"],
                card_type=view.card_cfg["id"],
            )
            embed = make_embed(
                title=f"❌ ĐÃ HỦY THẺ — {view.card_cfg['name'].upper()}",
                description=(
                    f"Bạn đã hủy cào thẻ. Hoàn lại "
                    f"**{view.card_cfg['price']:,} VND** vào tài khoản."
                ),
                color=discord.Color.red(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
            view.stop()
        else:
            for child in view.children:
                child.disabled = True
            embed = make_embed(
                title=f"🔒 THẺ CÀO ĐÃ ĐÓNG",
                description="Bạn không thể hoàn tiền vì đã cào dở thẻ.",
                color=discord.Color.greyple(),
            )
            await interaction.response.edit_message(embed=embed, view=None)
            view.stop()


# ── Main Play View ───────────────────────────────────────────────────────────

class ScratchCardPlayView(discord.ui.View):
    def __init__(
        self,
        cog: "ScratchCard",
        author: discord.Member,
        card_cfg: dict,
        grid: list[str],
        is_win: bool,
        win_sym: Optional[str],
        has_bonus: bool,
    ):
        super().__init__(timeout=120.0)
        self.cog = cog
        self.author = author
        self.card_cfg = card_cfg
        self.grid = grid
        self.is_win = is_win
        self.win_sym = win_sym
        self.has_bonus = has_bonus
        self.revealed = [False] * 9
        self.revealed_count = 0
        self.message: Optional[discord.Message] = None

        # Build the button layout
        for i in range(9):
            self.add_item(ScratchCellButton(i))
        self.add_item(ScratchAllButton())
        self.add_item(CancelCardButton())

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Đây không phải thẻ cào của bạn!", ephemeral=True
            )
            return False
        return True

    # ── Display helpers ──────────────────────────────────────────────────

    def _render_grid_text(self, reveal_all: bool = False) -> str:
        rows = []
        for r in range(3):
            cells = []
            for c in range(3):
                idx = r * 3 + c
                if self.revealed[idx] or reveal_all:
                    cells.append(f" {self.grid[idx]} ")
                else:
                    cells.append(f"[{idx + 1}]")
            rows.append("  ".join(cells))
        return "\n".join(rows)

    def create_embed(self) -> discord.Embed:
        grid_text = self._render_grid_text()
        desc = (
            f"### {self.card_cfg['name']}\n"
            f"💵 **Giá mua:** `{self.card_cfg['price']:,} VND`\n\n"
            f"```\n{grid_text}\n```\n"
            f"👉 Nhấn nút số `[1-9]` để cào từng ô.\n"
            f"👉 Cào được **3 ô giống nhau** ➔ **THẮNG** nhân giá trị thẻ!\n"
            f"👉 Tìm thấy ô `🎁` ẩn ➔ Tặng ngay thẻ miễn phí cùng loại."
        )
        return make_embed(
            title=f"🎴 THẺ CÀO MAY MẮN — {self.author.display_name.upper()}",
            description=desc,
            color=discord.Color.gold(),
        )

    async def update_display(self):
        if self.revealed_count >= 9:
            self.stop()
            embed = self._evaluate_payout()
            post_view = ScratchCardPostView(self.cog, self.author, self.card_cfg)
            try:
                await self.message.edit(embed=embed, view=post_view)
            except discord.HTTPException:
                pass
        else:
            try:
                await self.message.edit(embed=self.create_embed(), view=self)
            except discord.HTTPException:
                pass

    # ── Payout logic ─────────────────────────────────────────────────────

    def _evaluate_payout(self) -> discord.Embed:
        grid_text = self._render_grid_text(reveal_all=True)

        payout = 0
        result_lines = []
        is_jackpot = False

        if self.is_win and self.win_sym:
            mult = self.card_cfg["multipliers"][self.win_sym]
            payout = int(self.card_cfg["price"] * mult)
            self.cog.economy.add_money(self.author.id, payout)
            log_wallet_change(
                logger,
                event="scratch_win",
                user_id=self.author.id,
                money_delta=payout,
                card_type=self.card_cfg["id"],
                multiplier=mult,
                symbol=self.win_sym,
            )
            result_lines.append(
                f"🎉 **THẮNG x{mult}!** 3× {self.win_sym} ➔ **+{payout:,} VND**"
            )
            if self.win_sym == self.card_cfg["symbols"][-1]:
                is_jackpot = True
        else:
            result_lines.append("😔 Không có 3 ô trùng khớp. Chúc may mắn lần sau!")

        if self.has_bonus:
            self.cog.economy.add_money(self.author.id, self.card_cfg["price"])
            log_wallet_change(
                logger,
                event="scratch_bonus",
                user_id=self.author.id,
                money_delta=self.card_cfg["price"],
                card_type=self.card_cfg["id"],
            )
            result_lines.append(
                f"🎁 **BONUS!** Tìm thấy ô ẩn `🎁` ➔ Tặng thẻ Free "
                f"(hoàn `+{self.card_cfg['price']:,} VND`)"
            )

        balance = self.cog.economy.get_entry(self.author.id)[1]
        result_lines.append(f"\n💳 Số dư ví: **{balance:,} VND**")

        if is_jackpot:
            title = "💥💥💥 JACKPOT SCRATCH CARD! 💥💥💥"
            color = discord.Color.gold()
            asyncio.create_task(self._announce_jackpot(payout))
        elif payout > 0 or self.has_bonus:
            title = "🎉 CHIẾN THẮNG THẺ CÀO! 🎉"
            color = discord.Color.green()
        else:
            title = "😔 THẤT BẠI THẺ CÀO"
            color = discord.Color.red()

        return make_embed(
            title=title,
            description=f"```\n{grid_text}\n```\n" + "\n".join(result_lines),
            color=color,
        )

    async def _announce_jackpot(self, payout: int):
        try:
            if self.message and self.message.channel:
                await self.message.channel.send(
                    f"💥💥💥 **JACKPOT TRÚNG LỚN!** 💥💥💥\n"
                    f"Chúc mừng {self.author.mention} vừa cào trúng **JACKPOT** "
                    f"của {self.card_cfg['name']}! 🎉\n"
                    f"Nhận về **+{payout:,} VND**! 🏆🔥"
                )
        except Exception:
            pass

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ── Post-Game View ───────────────────────────────────────────────────────────

class ScratchCardPostView(discord.ui.View):
    def __init__(self, cog: "ScratchCard", author: discord.Member, card_cfg: dict):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.author = author
        self.card_cfg = card_cfg

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Đây không phải lượt chơi của bạn!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Mua Thẻ Mới", style=discord.ButtonStyle.success, emoji="🎴")
    async def buy_new(self, interaction: discord.Interaction, button: discord.ui.Button):
        profile = self.cog.economy.get_entry(self.author.id)
        if profile[1] < self.card_cfg["price"]:
            await interaction.response.send_message(
                f"❌ Không đủ tiền! Cần **{self.card_cfg['price']:,} VND**.",
                ephemeral=True,
            )
            return

        self.cog.economy.add_money(self.author.id, -self.card_cfg["price"])
        log_wallet_change(
            logger,
            event="scratch_buy",
            user_id=self.author.id,
            money_delta=-self.card_cfg["price"],
            card_type=self.card_cfg["id"],
        )

        grid, is_win, win_sym, has_bonus = generate_scratch_grid(self.card_cfg)
        play_view = ScratchCardPlayView(
            self.cog, self.author, self.card_cfg, grid, is_win, win_sym, has_bonus
        )
        embed = play_view.create_embed()
        await interaction.response.edit_message(embed=embed, view=play_view)
        play_view.message = interaction.message
        self.stop()

    @discord.ui.button(label="Xem Ví", style=discord.ButtonStyle.secondary, emoji="💰")
    async def view_wallet(self, interaction: discord.Interaction, button: discord.ui.Button):
        balance = self.cog.economy.get_entry(self.author.id)[1]
        await interaction.response.send_message(
            f"💰 Số dư ví: **{balance:,} VND**.", ephemeral=True
        )

class ScratchBulkPostView(discord.ui.View):
    def __init__(self, cog: "ScratchCard", author: discord.Member, card_cfg: dict, quantity: int):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.author = author
        self.card_cfg = card_cfg
        self.quantity = quantity
        self.message: Optional[discord.Message] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "❌ Đây không phải lượt chơi của bạn!", ephemeral=True
            )
            return False
        return True

    @discord.ui.button(label="Mua Lại", style=discord.ButtonStyle.success, emoji="🔄")
    async def buy_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Calculate price (10% discount for ≥ 5)
        total_price = self.card_cfg["price"] * self.quantity
        if self.quantity >= 5:
            total_price = int(total_price * 0.9)

        profile = self.cog.economy.get_entry(self.author.id)
        current_money = profile[1]

        if current_money < total_price:
            await interaction.response.send_message(
                f"❌ Không đủ tiền! Cần **{total_price:,} VND**.",
                ephemeral=True,
            )
            return

        # Deduct money
        self.cog.economy.add_money(self.author.id, -total_price)
        log_wallet_change(
            logger,
            event="scratch_buy_bulk",
            user_id=self.author.id,
            money_delta=-total_price,
            card_type=self.card_cfg["id"],
            quantity=self.quantity,
        )

        # Defer and run process_bulk
        await interaction.response.defer()
        
        embed, jackpot_count = self.cog._process_bulk_calculation(self.author, self.card_cfg, self.quantity, total_price)

        if jackpot_count > 0:
            try:
                await interaction.channel.send(
                    f"💥💥💥 **JACKPOT TỪ COMBO!** 💥💥💥\n"
                    f"{self.author.mention} trúng **JACKPOT** ({jackpot_count} lần) "
                    f"từ combo {self.quantity}× {self.card_cfg['name']}! 🎉🏆"
                )
            except Exception:
                pass

        await interaction.message.edit(embed=embed, view=self)

    @discord.ui.button(label="Xem Ví", style=discord.ButtonStyle.secondary, emoji="💰")
    async def view_wallet(self, interaction: discord.Interaction, button: discord.ui.Button):
        balance = self.cog.economy.get_entry(self.author.id)[1]
        await interaction.response.send_message(
            f"💰 Số dư ví: **{balance:,} VND**.", ephemeral=True
        )

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                await self.message.edit(view=self)
        except Exception:
            pass


# ── Cog ──────────────────────────────────────────────────────────────────────

class ScratchCard(commands.Cog, name="ScratchCard"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy: Economy = getattr(client, "economy", Economy())

    @commands.command(
        brief="Chơi Thẻ Cào May Mắn.",
        usage="scratch [buy <loại> [x<số>]]",
        aliases=["sc", "scratchcard", "caothe"],
    )
    async def scratch(
        self,
        ctx: commands.Context,
        action: Optional[str] = None,
        card_type: Optional[str] = None,
        qty_str: Optional[str] = None,
    ):
        user_id = ctx.author.id
        available = get_all_available_cards()

        # Direct card name shortcut: i?scratch silver
        if action and action.lower() not in ("buy", "mua") and action.lower() in available:
            qty_str = card_type  # shift args
            card_type = action.lower()
            action = "buy"

        # Show catalog
        if not action or action.lower() not in ("buy", "mua"):
            await ctx.send(embed=self._catalog_embed(available))
            return

        # Validate card type
        if not card_type:
            await ctx.send("❌ Vui lòng điền loại thẻ! Ví dụ: `i?scratch buy silver`")
            return

        card_type = card_type.lower()
        if card_type not in available:
            names = ", ".join(f"`{k}`" for k in available)
            await ctx.send(
                f"❌ Loại thẻ `{card_type}` không hợp lệ.\n👉 Đang bán: {names}"
            )
            return

        card_cfg = available[card_type]

        # Parse quantity
        quantity = 1
        if qty_str:
            cleaned = qty_str.lower().replace("x", "").replace("*", "")
            try:
                quantity = max(1, int(cleaned))
            except ValueError:
                quantity = 1
        if quantity > 10:
            await ctx.send("❌ Tối đa 10 thẻ cùng lúc.")
            return

        # Calculate price (10% discount for ≥ 5)
        total_price = card_cfg["price"] * quantity
        if quantity >= 5:
            total_price = int(total_price * 0.9)

        # Check balance
        current_money = self.economy.get_entry(user_id)[1]
        if current_money < total_price:
            await ctx.send(
                f"❌ Không đủ tiền! Cần **{total_price:,} VND** "
                f"để mua {quantity}× `{card_cfg['name']}`."
            )
            return

        # Deduct
        self.economy.add_money(user_id, -total_price)
        log_wallet_change(
            logger,
            event="scratch_buy_bulk" if quantity > 1 else "scratch_buy",
            user_id=user_id,
            money_delta=-total_price,
            card_type=card_cfg["id"],
            quantity=quantity,
        )

        # Bulk mode
        if quantity > 1:
            await self._process_bulk(ctx, card_cfg, quantity, total_price)
            return

        # Single interactive card
        grid, is_win, win_sym, has_bonus = generate_scratch_grid(card_cfg)
        view = ScratchCardPlayView(
            self, ctx.author, card_cfg, grid, is_win, win_sym, has_bonus
        )
        msg = await ctx.send(embed=view.create_embed(), view=view)
        view.message = msg

    # ── Catalog embed ────────────────────────────────────────────────────

    def _catalog_embed(self, available: dict) -> discord.Embed:
        embed = make_embed(
            title="🎴 THẺ CÀO MAY MẮN — DANH MỤC 🎴",
            description=(
                "Cào ô tìm **3 biểu tượng giống nhau** để nhận thưởng nhân gấp bội!\n\n"
                "👉 `i?scratch buy <tên>` — mua 1 thẻ\n"
                "👉 `i?scratch buy <tên> x5` — combo (giảm 10%)\n"
                "🎁 *2% cơ hội tìm thấy ô ẩn `🎁` tặng thẻ Free!*"
            ),
            color=discord.Color.blurple(),
        )

        for cid, cfg in available.items():
            event_tag = " ⚡ *SỰ KIỆN*" if cid in EVENT_CARDS else ""
            payouts = " | ".join(
                f"{sym} ×{mult}" for sym, mult in cfg["multipliers"].items()
            )
            embed.add_field(
                name=f"{cfg['name']} (ID: `{cid}`){event_tag}",
                value=(
                    f"💵 Giá: `{cfg['price']:,} VND` • "
                    f"Tỷ lệ thắng: `{int(cfg['win_rate'] * 100)}%`\n"
                    f"✨ {payouts}"
                ),
                inline=False,
            )
        return embed

    # ── Bulk scratch ─────────────────────────────────────────────────────

    def _process_bulk_calculation(
        self,
        author: discord.User | discord.Member,
        card_cfg: dict,
        quantity: int,
        total_price: int,
    ) -> tuple[discord.Embed, int]:
        user_id = author.id
        lines = []
        total_payout = 0
        bonus_count = 0
        jackpot_count = 0

        for i in range(1, quantity + 1):
            grid, is_win, win_sym, has_bonus = generate_scratch_grid(card_cfg)
            payout = 0
            desc = ""

            if is_win and win_sym:
                mult = card_cfg["multipliers"][win_sym]
                payout = int(card_cfg["price"] * mult)
                total_payout += payout
                if win_sym == card_cfg["symbols"][-1]:
                    jackpot_count += 1
                    desc = f"🏆 **JACKPOT** 3× {win_sym} (`+{payout:,}`)"
                else:
                    desc = f"🟢 3× {win_sym} (`+{payout:,}`)"
            else:
                desc = "🔴 Thua"

            if has_bonus:
                bonus_count += 1
                total_payout += card_cfg["price"]
                desc += " + 🎁 Free"

            lines.append(f"• **#{i:02d}**: {desc}")

        if total_payout > 0:
            self.economy.add_money(user_id, total_payout)

        net = total_payout - total_price
        sign = "+" if net >= 0 else ""
        color = discord.Color.green() if net >= 0 else discord.Color.red()

        discount_note = " *(Đã giảm 10%)*" if quantity >= 5 else ""

        embed = make_embed(
            title="🎴 KẾT QUẢ COMBO CÀO THẺ 🎴",
            description=(
                f"👤 {author.mention}\n"
                f"🛒 **{quantity}×** `{card_cfg['name']}`{discount_note}\n"
                f"💸 Chi phí: `-{total_price:,} VND`\n"
                f"💰 Thu về: `+{total_payout:,} VND`\n"
                f"📈 Lợi nhuận: **`{sign}{net:,} VND`**\n"
                f"🎁 Thẻ Free: `{bonus_count}`\n\n"
                + "\n".join(lines)
            ),
            color=color,
        )
        return embed, jackpot_count

    async def _process_bulk(
        self,
        ctx: commands.Context,
        card_cfg: dict,
        quantity: int,
        total_price: int,
    ):
        embed, jackpot_count = self._process_bulk_calculation(ctx.author, card_cfg, quantity, total_price)
        view = ScratchBulkPostView(self, ctx.author, card_cfg, quantity)
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

        if jackpot_count > 0:
            try:
                await ctx.send(
                    f"💥💥💥 **JACKPOT TỪ COMBO!** 💥💥💥\n"
                    f"{ctx.author.mention} trúng **JACKPOT** ({jackpot_count} lần) "
                    f"từ combo {quantity}× {card_cfg['name']}! 🎉🏆"
                )
            except Exception:
                pass


async def setup(client: commands.Bot):
    await client.add_cog(ScratchCard(client))
