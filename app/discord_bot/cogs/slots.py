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
            desc = f"↔️ Giá vàng ổn định ở mức cân bằng **{current:,} VND**."

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

    @commands.command(
        brief="Xem tỷ giá nạp Thỏi Vàng bằng tiền VND thực tế ngoài đời và tính toán ưu đãi chiết khấu.",
        usage="nap [số_tiền_VND/số_k]",
        aliases=["topup", "napgold", "naptien"]
    )
    async def nap(self, ctx: commands.Context, amount_str: str = None):
        """
        Base rate: 1k VND (1,000 VND) = 3 Gold
        Discount / Bonus: Every 100k VND grants +2% bonus Gold (capped at 40%).
        """
        def parse_amount(s: str) -> int | None:
            if not s:
                return None
            s = s.lower().strip().replace(".", "").replace(",", "")
            try:
                if s.endswith("k"):
                    return int(float(s[:-1]) * 1000)
                elif s.endswith("m"):
                    return int(float(s[:-1]) * 1_000_000)
                else:
                    return int(s)
            except ValueError:
                return None

        def calc_gold(vnd: int) -> tuple[int, int, int, int]:
            base_gold = (vnd // 1000) * 3
            bonus_tier = vnd // 100_000
            discount_pct = min(40, bonus_tier * 2)
            bonus_gold = int(base_gold * (discount_pct / 100))
            total_gold = base_gold + bonus_gold
            return base_gold, bonus_gold, discount_pct, total_gold

        vnd_amount = parse_amount(amount_str)

        if vnd_amount is None or vnd_amount <= 0:
            sample_amounts = [10_000, 50_000, 100_000, 200_000, 500_000, 1_000_000, 2_000_000]
            table_rows = []
            for amt in sample_amounts:
                base_g, bonus_g, disc_p, tot_g = calc_gold(amt)
                amt_k = f"{amt // 1000:,}k" if amt < 1_000_000 else f"{amt / 1_000_000:.1f}M".replace(".0", "")
                disc_str = f" (+{disc_p}%)" if disc_p > 0 else ""
                table_rows.append(f"• **`{amt_k:>6}` VND** ➔ **`{tot_g:,}`** Gold {disc_str}")

            table_text = "\n".join(table_rows)

            embed = make_embed(
                title="💳 BẢNG GIÁ NẠP THỎI VÀNG (TIỀN MẶT NGOÀI ĐỜI) 💳",
                description=(
                    f"✨ **Tỷ giá cơ bản:** `1,000 VND (1k)` = **`3 Thỏi Vàng`** <:32100goldbarsfortnite:1514192020921651251>\n"
                    f"🎁 **Ưu đãi nạp lớn:** Cứ mỗi **`100,000 VND (100k)`** nạp vào ➔ **Tặng thêm +2% Gold** (tối đa 40%).\n\n"
                    f"### 📋 BẢNG GIÁ QUY ĐỔI MẪU:\n"
                    f"{table_text}\n\n"
                    f"💡 **Tính số Gold cho mốc nạp tùy chỉnh:**\n"
                    f"Gõ: `i?nap <số_tiền>` (Ví dụ: `i?nap 100k`, `i?nap 250k`, `i?nap 500000`)"
                ),
                color=discord.Color.gold()
            )
            embed.set_footer(text="Liên hệ Admin / Owner máy chủ để thực hiện giao dịch nạp.")
            await ctx.send(embed=embed)
        else:
            base_g, bonus_g, disc_p, tot_g = calc_gold(vnd_amount)
            vnd_formatted = f"{vnd_amount:,} VND"

            desc = (
                f"💵 **Số tiền nạp:** `{vnd_formatted}`\n"
                f"🪙 **Số Gold gốc (1k = 3 Gold):** `{base_g:,}` Thỏi Vàng\n"
                f"🎁 **Ưu đãi chiết khấu (+{disc_p}%):** `+{bonus_g:,}` Thỏi Vàng\n"
                f"─────────────────────────────\n"
                f"👑 **TỔNG GOLD NHẬN ĐƯỢC:** **`{tot_g:,}` Thỏi Vàng** <:32100goldbarsfortnite:1514192020921651251>"
            )

            embed = make_embed(
                title="💳 TÍNH TOÁN GIÁ NẠP GOLD 💳",
                description=desc,
                color=discord.Color.green()
            )
            embed.set_footer(text="Liên hệ Admin / Owner máy chủ để hoàn tất chuyển khoản nạp.")
            await ctx.send(embed=embed)

    @commands.command(
        brief="Xem bảng xếp hạng Top Nạp Tiền (Top VIP) của máy chủ.",
        usage="topnap",
        aliases=["naptop", "topupboard", "bxhnap"]
    )
    async def topnap(self, ctx: commands.Context):
        top_list = self.economy.get_topup_leaderboard(10)
        
        rank_emojis = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        
        if not top_list:
            embed = make_embed(
                title="🏆 BẢNG XẾP HẠNG TOP NẠP VÀNG (TOP VIP) 🏆",
                description="✨ Chưa có dữ liệu nạp tiền trên hệ thống.\nGõ `i?nap` để xem bảng giá quy đổi Gold!",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)
            return

        lines = []
        author_rank = None
        
        for idx, (uid, total_vnd, total_gold) in enumerate(top_list):
            emoji = rank_emojis[idx] if idx < len(rank_emojis) else f"`#{idx+1}`"
            
            user = self.bot.get_user(uid)
            user_name = user.display_name if user else f"User ID {uid}"
            
            if uid == ctx.author.id:
                author_rank = idx + 1
                lines.append(f"{emoji} **{user_name}** *(Bạn)* — **`{total_vnd:,}` VND** (`{total_gold:,}` Gold)")
            else:
                lines.append(f"{emoji} **{user_name}** — **`{total_vnd:,}` VND** (`{total_gold:,}` Gold)")

        user_vnd, user_gold = self.economy.get_user_topup(ctx.author.id)
        user_rank_str = f"thứ #{author_rank}" if author_rank else "chưa xếp hạng"

        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG TOP NẠP VÀNG (TOP VIP) 🏆",
            description="\n".join(lines),
            color=discord.Color.gold()
        )
        embed.set_footer(
            text=f"Thứ hạng của bạn: {user_rank_str} | Tổng nạp: {user_vnd:,} VND ({user_gold:,} Gold)"
        )
        await ctx.send(embed=embed)

    @commands.command(
        brief="[ADMIN] Cộng tiền nạp VND và tự động quy đổi Gold cho người chơi.",
        usage="addtopup @user <số_tiền_VND/số_k>",
        aliases=["addtop", "congnap"],
        hidden=True
    )
    async def addtopup(self, ctx: commands.Context, target: discord.Member, amount_str: str):
        if ctx.author.id not in config.bot.owner_ids and ctx.author.id not in config.bot.admin_ids:
            await ctx.send("❌ Lệnh này chỉ dành cho Admin / Owner!")
            return

        def parse_amount(s: str) -> int | None:
            if not s:
                return None
            s = s.lower().strip().replace(".", "").replace(",", "")
            try:
                if s.endswith("k"):
                    return int(float(s[:-1]) * 1000)
                elif s.endswith("m"):
                    return int(float(s[:-1]) * 1_000_000)
                else:
                    return int(s)
            except ValueError:
                return None

        vnd_amount = parse_amount(amount_str)
        if not vnd_amount or vnd_amount <= 0:
            await ctx.send("❌ Số tiền nạp không hợp lệ! Ví dụ: `i?addtopup @user 100k` hoặc `i?addtopup @user 500000`.")
            return

        base_gold = (vnd_amount // 1000) * 3
        bonus_tier = vnd_amount // 100_000
        discount_pct = min(40, bonus_tier * 2)
        bonus_gold = int(base_gold * (discount_pct / 100))
        total_gold = base_gold + bonus_gold

        self.economy.add_credits(target.id, total_gold)
        new_total_vnd = self.economy.add_user_topup(target.id, vnd_amount, total_gold)
        
        log_wallet_change(logger, event="admin_add_topup", user_id=target.id, credits_delta=total_gold, actor_id=ctx.author.id, ctx=ctx)

        embed = make_embed(
            title="🎉 NẠP THỎI VÀNG THÀNH CÔNG 🎉",
            description=(
                f"ADMIN **{ctx.author.mention}** đã xác nhận nạp tiền cho **{target.mention}**!\n\n"
                f"💵 **Số tiền nạp:** `{vnd_amount:,} VND`\n"
                f"✨ **Số Gold nhận được (+{discount_pct}%):** `+{total_gold:,}` Thỏi Vàng <:32100goldbarsfortnite:1514192020921651251>\n"
                f"🏆 **Tổng nạp tích lũy (Top Nạp):** `{new_total_vnd:,} VND`"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="[ADMIN] Đặt thủ công giá vàng thế giới.",
        usage="setgoldprice <số_tiền_VND/số_m>",
        aliases=["setgiavang", "doigiavang"],
        hidden=True
    )
    async def setgoldprice(self, ctx: commands.Context, price_str: str):
        if ctx.author.id not in config.bot.owner_ids and ctx.author.id not in config.bot.admin_ids:
            await ctx.send("❌ Lệnh này chỉ dành cho Admin / Owner!")
            return

        def parse_amount(s: str) -> int | None:
            if not s:
                return None
            s = s.lower().strip().replace(".", "").replace(",", "")
            try:
                if s.endswith("k"):
                    return int(float(s[:-1]) * 1000)
                elif s.endswith("m"):
                    return int(float(s[:-1]) * 1_000_000)
                else:
                    return int(s)
            except ValueError:
                return None

        new_price = parse_amount(price_str)
        if not new_price or new_price < 1_000_000:
            await ctx.send("❌ Giá vàng không hợp lệ! Mức tối thiểu là 1,000,000 VND. Ví dụ: `i?setgoldprice 30m` hoặc `i?setgoldprice 30000000`.")
            return

        current_price = self.economy.get_gold_price()
        # Set both current and prev to new_price so baseline comparison resets cleanly
        self.economy.set_gold_prices(new_price, new_price)
        self.economy.set_setting("gold_price_last_update", str(int(time.time())))

        embed = make_embed(
            title="<:32100goldbarsfortnite:1514192020921651251> ĐÃ CẬP NHẬT GIÁ VÀNG THẾ GIỚI <:32100goldbarsfortnite:1514192020921651251>",
            description=(
                f"ADMIN **{ctx.author.mention}** đã cập nhật giá vàng thế giới thành công!\n\n"
                f"📈 **Giá cũ:** `{current_price:,} VND` / thỏi\n"
                f"💰 **Giá mới:** `{new_price:,} VND` / thỏi"
            ),
            color=discord.Color.gold()
        )
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
            base_price = 30_000_000
            drift = 0.05 * (base_price - current_price) / base_price
            
            # High volatility: random shock up to 25%
            random_shock = random.uniform(-0.25, 0.25)
            
            new_price = int(current_price * (1 + drift + random_shock))
            # Clamp between 3,000,000 and 150,000,000
            new_price = max(3_000_000, min(150_000_000, new_price))
            # Round to nearest 1,000
            new_price = (new_price // 1000) * 1000
            
            self.economy.set_gold_prices(new_price, current_price)
            # Update timestamp to the expected schedule boundary to prevent time drift
            self.economy.set_setting("gold_price_last_update", str(last_update + one_week))
            logger.info(f"Gold price updated in background (weekly update): {current_price:,} -> {new_price:,} VND")

    @commands.command(
        name="adhelp",
        hidden=True,
        aliases=["adminhelp", "ownerhelp"]
    )
    async def adhelp(self, ctx: commands.Context):
        """Lệnh ẩn: Danh sách các lệnh chỉ dành cho Owner / Admin."""
        if ctx.author.id not in config.bot.owner_ids and ctx.author.id not in config.bot.admin_ids:
            return  # Không phản hồi gì hết, tàng hình hoàn toàn

        embed = make_embed(
            title="👑 DANH SÁCH LỆNH OWNER / ADMIN 👑",
            description="Các lệnh ẩn chỉ dành cho Owner và Admin của bot.",
            color=discord.Color.from_rgb(255, 215, 0)
        )

        # --- TIỀN / GOLD ---
        embed.add_field(
            name="💰 Tiền & Vàng",
            value=(
                "`i?addtopup @user <số_tiền>` — Cộng tiền nạp VND và tự động quy đổi Gold cho người chơi.\n"
                "`i?setgoldprice <số>` — Đặt thủ công giá vàng thế giới (vd: `30m`).\n"
                "`i?giveall <loại> <số>` — Tặng tiền/vàng cho tất cả người chơi trong DB.\n"
            ),
            inline=False
        )

        # --- BAN / UNBAN ---
        embed.add_field(
            name="🔨 Ban / Unban",
            value=(
                "`i?ban @user [lý do]` — Cấm người chơi sử dụng bot.\n"
                "`i?unban @user` — Bỏ cấm người chơi.\n"
            ),
            inline=False
        )

        # --- BANNER / ITEM ---
        embed.add_field(
            name="🖼️ Banner & Item",
            value=(
                "`i?adminshop` — Xem danh sách banner độc quyền (Admin Only).\n"
                "`i?givebanner @user <banner_id>` — Tặng banner đặc biệt cho người chơi.\n"
                "`i?setbannerother @user <banner_id>` — Đặt banner trực tiếp cho người chơi.\n"
                "`i?giveitem @user <item_id> [số]` — Tặng item từ shop cho người chơi.\n"
            ),
            inline=False
        )

        # --- HÔN NHÂN ---
        embed.add_field(
            name="💍 Hôn Nhân",
            value=(
                "`i?admindelmarriage @user` — Xóa cưỡng chế hôn nhân của người chơi.\n"
            ),
            inline=False
        )

        # --- CÁ CƯỢC ---
        embed.add_field(
            name="🎰 Cờ Bạc",
            value=(
                "`i?setbetlimit <min> <max>` — Đặt giới hạn cược tối thiểu/tối đa toàn bot.\n"
                "`i?set_taixiu_config <tham số>` — Cấu hình tài xỉu.\n"
                "`i?set_baucua_config <tham số>` — Cấu hình bầu cua.\n"
                "`i?set_roulette_stats @user <tham số>` — Chỉnh số liệu roulette của người chơi.\n"
                "`i?set_coinflip_stats @user <tham số>` — Chỉnh số liệu coinflip của người chơi.\n"
                "`i?anxin @user` — Làm mới số dư / fix trạng thái người chơi.\n"
            ),
            inline=False
        )

        # --- DANH HIỆU ---
        embed.add_field(
            name="🏅 Danh Hiệu",
            value=(
                "`i?give_danh_hieu @user <danh_hiệu>` — Tặng danh hiệu cho người chơi.\n"
                "`i?remove_danh_hieu @user <danh_hiệu>` — Thu hồi danh hiệu của người chơi.\n"
            ),
            inline=False
        )

        # --- HỆ THỐNG ---
        embed.add_field(
            name="⚙️ Hệ Thống",
            value=(
                "`i?kill` — Tắt bot (chỉ Owner).\n"
                "`i?botplayers` — Xem tổng số người chơi trong DB.\n"
                "`i?botservers` — Xem tổng số server bot đang hoạt động.\n"
                "`i?trungbay` — Khai hàng trúng bầy (gift toàn server).\n"
                "`i?reply_feedback <id>` — Trả lời feedback từ người chơi.\n"
            ),
            inline=False
        )

        embed.set_footer(text="Lệnh này hoàn toàn ẩn. Chỉ bạn mới thấy nó!")
        await ctx.send(embed=embed)


async def setup(client: commands.Bot):
    await client.add_cog(Slots(client))
