import asyncio
from contextlib import suppress
from dataclasses import dataclass
from io import BytesIO
import logging
from pathlib import Path
import random
import ssl
import time
from uuid import uuid4

import aiohttp
import discord
from discord.ext import commands, tasks
from PIL import Image

from app.config import config
from app.discord_bot.modules.betting import (
    validate_credits_available,
    validate_credits_bet,
    validate_money_available,
    validate_positive_amount,
)
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import (
    ABS_PATH,
    make_embed,
)
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SlotRenderSettings:
    frame_count: int
    frame_duration_ms: int
    delays: tuple[float, float, float]


class Slots(commands.Cog):
    # Symbol id (0-5) payouts using the table on the slot machine image.
    # 0=lemon, 1=seven, 2=diamond, 3=coin, 4=bell, 5=cherry
    TRIPLE_PAYOUTS = [4, 80, 40, 25, 10, 5]
    JOKER_SYMBOL = 1  # seven
    ITEM_HEIGHT = 180
    REEL_LEFT_OFFSET = 25
    REEL_TOP_OFFSET = 100
    # Slots GIF tuning knobs.
    # Increase frame_count / decrease frame_duration_ms for smoother animation.
    RENDER_SETTINGS = SlotRenderSettings(
        frame_count=48,
        frame_duration_ms=32,
        delays=(0.0, 0.1, 0.2),
    )

    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())
        self._assets_path = Path(ABS_PATH) / "modules"
        self._slot_facade = Image.open(self._assets_path / "slot-face.png").convert("RGBA")
        self._slot_reel = Image.open(self._assets_path / "slot-reel.png").convert("RGBA")
        self._slot_base = Image.new("RGBA", self._slot_facade.size, color=(255, 255, 255, 255))
        self._reel_width, self._reel_height = self._slot_reel.size
        self._reel_items = self._reel_height // self.ITEM_HEIGHT
        self._reel_x_positions = tuple(
            self.REEL_LEFT_OFFSET + (self._reel_width * index)
            for index in range(3)
        )

        self._progress_table = self._build_progress_table(self.RENDER_SETTINGS)
        self.update_gold_price.start()

    def cog_unload(self) -> None:
        self.update_gold_price.cancel()
        for image in (self._slot_facade, self._slot_reel, self._slot_base):
            with suppress(Exception):
                image.close()

    def check_bet(self, ctx: commands.Context, bet: int = config.bot.default_bet):
        return validate_credits_bet(self.economy, ctx.author.id, bet, max_bet=3)[0]

    @staticmethod
    def _is_retryable_send_error(exc: Exception) -> bool:
        if isinstance(exc, (aiohttp.ClientError, ssl.SSLError, TimeoutError, ConnectionResetError)):
            return True
        if isinstance(exc, discord.HTTPException):
            return exc.status >= 500 or exc.status == 0
        return False

    @staticmethod
    def _eased_progress(raw_progress: float, delay: float) -> float:
        if raw_progress <= delay:
            return 0.0
        scaled = (raw_progress - delay) / (1.0 - delay)
        if scaled >= 1.0:
            return 1.0
        # Ease-out cubic.
        return 1.0 - ((1.0 - scaled) ** 3)

    @classmethod
    def _build_progress_table(
        cls,
        settings: SlotRenderSettings,
    ) -> list[tuple[float, float, float]]:
        table: list[tuple[float, float, float]] = []
        for frame_index in range(1, settings.frame_count + 1):
            raw = frame_index / settings.frame_count
            table.append(
                tuple(cls._eased_progress(raw, delay) for delay in settings.delays)
            )
        return table

    def _render_slots_gif(
        self,
        *,
        s1: int,
        s2: int,
        s3: int,
    ) -> BytesIO:
        images: list[Image.Image] = []
        try:
            for p1, p2, p3 in self._progress_table:
                frame = self._slot_base.copy()
                frame.paste(
                    self._slot_reel,
                    (
                        self._reel_x_positions[0],
                        self.REEL_TOP_OFFSET - int(self.ITEM_HEIGHT * s1 * p1),
                    ),
                )
                frame.paste(
                    self._slot_reel,
                    (
                        self._reel_x_positions[1],
                        self.REEL_TOP_OFFSET - int(self.ITEM_HEIGHT * s2 * p2),
                    ),
                )
                frame.paste(
                    self._slot_reel,
                    (
                        self._reel_x_positions[2],
                        self.REEL_TOP_OFFSET - int(self.ITEM_HEIGHT * s3 * p3),
                    ),
                )
                frame.alpha_composite(self._slot_facade)
                images.append(frame)

            output = BytesIO()
            images[0].save(
                output,
                format="GIF",
                save_all=True,
                append_images=images[1:],
                duration=self.RENDER_SETTINGS.frame_duration_ms,
                optimize=False,
                disposal=2,
            )
            output.seek(0)
            return output
        finally:
            for image in images:
                image.close()

    async def _send_slots_embed(
        self,
        *,
        ctx: commands.Context,
        embed: discord.Embed,
        filename: str,
        primary_gif: bytes,
    ) -> None:
        attachment_url = f"attachment://{filename}"
        for attempt in range(1, 3):
            try:
                with BytesIO(primary_gif) as payload:
                    embed_payload = embed.copy()
                    embed_payload.set_image(url=attachment_url)
                    file = discord.File(fp=payload, filename=filename)
                    await ctx.send(file=file, embed=embed_payload)
                return
            except Exception as exc:
                if not self._is_retryable_send_error(exc):
                    raise
                if attempt == 2:
                    logger.warning(
                        "slots_send_retry_exhausted user_id=%s",
                        ctx.author.id,
                        exc_info=exc,
                    )
                    raise
                await asyncio.sleep(0.5 * attempt)

    @staticmethod
    def _symbol_id(stop_position: int) -> int:
        return (1 + stop_position) % 6

    @classmethod
    def _evaluate_spin(cls, s1: int, s2: int, s3: int, bet: int) -> tuple[str, int]:
        symbols = [
            cls._symbol_id(s1),
            cls._symbol_id(s2),
            cls._symbol_id(s3),
        ]

        # Exact triple (including 7-7-7).
        if symbols[0] == symbols[1] == symbols[2]:
            return "triple", cls.TRIPLE_PAYOUTS[symbols[0]] * bet

        # Joker rules:
        # - Pair only pays when the third symbol is 7.
        # - 2x7 + 1xsymbol pays as 3x that non-7 symbol.
        non_jokers = [symbol for symbol in symbols if symbol != cls.JOKER_SYMBOL]
        joker_count = len(symbols) - len(non_jokers)

        # One 7 + two identical non-7 symbols.
        if joker_count == 1 and len(non_jokers) == 2 and non_jokers[0] == non_jokers[1]:
            return "joker_pair", cls.TRIPLE_PAYOUTS[non_jokers[0]] * bet

        # Two 7s + one non-7 symbol.
        if joker_count == 2 and len(non_jokers) == 1:
            return "joker_pair", cls.TRIPLE_PAYOUTS[non_jokers[0]] * bet

        return "none", 0


    @commands.command(
        brief="Mua thỏi vàng theo tỷ giá thị trường hiện tại.",
        usage="muavang <số_lượng>",
        aliases=["buyc", "buy", "b"],
    )
    async def muavang(self, ctx: commands.Context, amount_to_buy: int):
        user_id = ctx.author.id
        normalized_amount = validate_positive_amount(amount_to_buy)
        gold_price = self.economy.get_gold_price()
        cost = normalized_amount * gold_price
        validate_money_available(self.economy, user_id, cost)
        self.economy.add_money(user_id, cost * -1)
        self.economy.add_credits(user_id, normalized_amount)
        log_wallet_change(
            logger,
            event="buy_credits",
            user_id=user_id,
            money_delta=cost * -1,
            credits_delta=normalized_amount,
            ctx=ctx,
            credits_bought=normalized_amount,
            unit_price=gold_price,
        )
        embed = make_embed(
            title="<:32100goldbarsfortnite:1514192020921651251> MUA THỎI VÀNG THÀNH CÔNG <:32100goldbarsfortnite:1514192020921651251>",
            description=(
                f"Bạn đã mua thành công **{normalized_amount:,}** thỏi vàng với giá **{gold_price:,} VND** / thỏi.\n"
                f"💸 **Tổng chi phí:** `-{cost:,} VND`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await ctx.invoke(self.client.get_command("money"))

    @commands.command(
        brief="Bán thỏi vàng theo tỷ giá thị trường hiện tại.",
        usage="banvang <số_lượng>",
        aliases=["sellc", "sell", "s"],
    )
    async def banvang(self, ctx: commands.Context, amount_to_sell: int):
        user_id = ctx.author.id
        normalized_amount = validate_credits_available(
            self.economy, user_id, amount_to_sell
        )[0]
        gold_price = self.economy.get_gold_price()
        money_delta = normalized_amount * gold_price
        self.economy.add_credits(user_id, normalized_amount * -1)
        self.economy.add_money(user_id, money_delta)
        log_wallet_change(
            logger,
            event="sell_credits",
            user_id=user_id,
            money_delta=money_delta,
            credits_delta=normalized_amount * -1,
            ctx=ctx,
            credits_sold=normalized_amount,
            unit_price=gold_price,
        )
        embed = make_embed(
            title="<:32100goldbarsfortnite:1514192020921651251> BÁN THỎI VÀNG THÀNH CÔNG <:32100goldbarsfortnite:1514192020921651251>",
            description=(
                f"Bạn đã bán thành công **{normalized_amount:,}** thỏi vàng với giá **{gold_price:,} VND** / thỏi.\n"
                f"💰 **Nhận được:** `+{money_delta:,} VND`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)
        await ctx.invoke(self.client.get_command("money"))

    @commands.command(
        brief="Xem giá vàng hiện tại trên thị trường thế giới",
        usage="giavang",
        aliases=["goldprice", "price", "gia"],
    )
    async def giavang(self, ctx: commands.Context):
        current = self.economy.get_gold_price()
        prev = self.economy.get_prev_gold_price()
        
        diff = current - prev
        percent = (diff / prev) * 100 if prev > 0 else 0
        
        if diff > 0:
            trend = "📈 TĂNG"
            color = discord.Color.green()
            desc = f"📈 Giá vàng vừa tăng **{percent:+.2f}%** (**+{diff:,} VND**) so với chu kỳ trước!"
        elif diff < 0:
            trend = "📉 GIẢM"
            color = discord.Color.red()
            desc = f"📉 Giá vàng vừa giảm **{percent:+.2f}%** (**{diff:,} VND**) so với chu kỳ trước!"
        else:
            trend = "↔️ KHÔNG ĐỔI"
            color = discord.Color.light_grey()
            desc = "↔️ Giá vàng ổn định so với chu kỳ trước."

        current_time = int(time.time())
        last_update_str = self.economy.get_setting("gold_price_last_update")
        if last_update_str:
            next_update = int(last_update_str) + 7 * 24 * 3600
            diff_time = next_update - current_time
            if diff_time > 0:
                days = diff_time // (24 * 3600)
                hours = (diff_time % (24 * 3600)) // 3600
                next_update_str = f"Cập nhật tiếp theo sau {days} ngày {hours} giờ"
            else:
                next_update_str = "Cập nhật tiếp theo: Đang chờ chu kỳ mới"
        else:
            next_update_str = "Cập nhật tiếp theo sau 7 ngày"

        embed = make_embed(
            title=f"<:32100goldbarsfortnite:1514192020921651251> BẢNG GIÁ THỎI VÀNG THẾ GIỚI ({trend}) <:32100goldbarsfortnite:1514192020921651251>",
            description=(
                f"{desc}\n\n"
                f"💰 **Giá mua/bán hiện tại:** `{current:,} VND` / thỏi\n"
                f"🕒 *Tỷ giá biến động tự động mỗi tuần một lần.*\n"
                f"📅 *{next_update_str}*"
            ),
            color=color
        )
        embed.set_footer(text="Gõ i?muavang <số lượng> hoặc i?banvang <số lượng> để giao dịch")
        await ctx.send(embed=embed)

    @tasks.loop(minutes=10)
    async def update_gold_price(self):
        current_time = int(time.time())
        last_update_str = self.economy.get_setting("gold_price_last_update")
        
        if last_update_str is None:
            self.economy.set_setting("gold_price_last_update", str(current_time))
            return
            
        last_update = int(last_update_str)
        one_week = 7 * 24 * 3600
        
        if current_time >= last_update + one_week:
            current_price = self.economy.get_gold_price()
            
            # Mean-reverting random walk
            base_price = 10_000_000
            drift = 0.05 * (base_price - current_price) / base_price
            
            # High volatility: random shock up to 25%
            random_shock = random.uniform(-0.25, 0.25)
            
            new_price = int(current_price * (1 + drift + random_shock))
            # Clamp between 1,000,000 and 50,000,000
            new_price = max(1_000_000, min(50_000_000, new_price))
            # Round to nearest 1,000
            new_price = (new_price // 1000) * 1000
            
            self.economy.set_gold_prices(new_price, current_price)
            # Update timestamp to the expected schedule boundary to prevent time drift
            self.economy.set_setting("gold_price_last_update", str(last_update + one_week))
            logger.info(f"Gold price updated in background (weekly update): {current_price:,} -> {new_price:,} VND")


async def setup(client: commands.Bot):
    await client.add_cog(Slots(client))
