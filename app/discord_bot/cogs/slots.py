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
    calc_gold,
    make_embed,
    parse_amount,
)
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

TOPUP_CONFIRM_VND_THRESHOLD = 5_000_000


class TopupConfirmView(discord.ui.View):
    """Confirmation buttons for crediting a large gold top-up via i?addtopup."""

    def __init__(self, admin: discord.Member, target: discord.Member,
                 vnd_amount: int, total_gold: int, bonus_pct: int):
        super().__init__(timeout=60)
        self.admin = admin
        self.target = target
        self.vnd_amount = vnd_amount
        self.total_gold = total_gold
        self.bonus_pct = bonus_pct
        self.confirmed: bool | None = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.admin.id:
            await interaction.response.send_message(
                "❌ Chỉ admin đã gõ lệnh mới có thể xác nhận.", ephemeral=True
            )
            return False
        return True

    async def _finish(self, interaction: discord.Interaction, confirmed: bool):
        self.confirmed = confirmed
        for item in self.children:
            item.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

    @discord.ui.button(label="✅ Xác nhận cộng Gold", style=discord.ButtonStyle.success)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finish(interaction, True)

    @discord.ui.button(label="❌ Huỷ", style=discord.ButtonStyle.danger)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._finish(interaction, False)


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
        self.bot = client
        self.economy = getattr(client, "economy", None) or Economy()
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
        self._check_and_update_gold_price()

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
                minutes = (diff_time % 3600) // 60
                if days > 0:
                    next_update_str = f"Cập nhật tiếp theo sau {days} ngày {hours} giờ"
                elif hours > 0:
                    next_update_str = f"Cập nhật tiếp theo sau {hours} giờ {minutes} phút"
                else:
                    next_update_str = f"Cập nhật tiếp theo sau {max(1, minutes)} phút"
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

            if self.economy.get_setting("bank_configured") != "1":
                embed = make_embed(
                    title="⚠️ CHƯA CẤU HÌNH TÀI KHOẢN NHẬN TIỀN",
                    description=(
                        f"Hệ thống nạp chưa có thông tin ngân hàng chính thức nên không thể tạo mã QR.\n"
                        f"Vui lòng liên hệ Admin/Owner để nạp Thỏi Vàng.\n\n"
                        f"*(Admin/Owner: cấu hình bằng lệnh `i?setbank <mã_NH> <STK> <Tên_chủ_TK>`.)*"
                    ),
                    color=discord.Color.red()
                )
                await ctx.send(embed=embed)
                return

            bank_id = self.economy.get_setting("bank_id", "MB")
            bank_account = self.economy.get_setting("bank_account", "0000000000")
            account_name = self.economy.get_setting("account_name", "ADMIN CASINO")

            from urllib.parse import quote
            add_info = f"NAP {ctx.author.id}"
            encoded_acc_name = quote(account_name)
            encoded_add_info = quote(add_info)
            vietqr_url = f"https://img.vietqr.io/image/{bank_id}-{bank_account}-compact2.png?amount={vnd_amount}&addInfo={encoded_add_info}&accountName={encoded_acc_name}"

            desc = (
                f"👤 **Người nạp:** {ctx.author.mention}\n"
                f"💵 **Số tiền nạp:** `{vnd_formatted}`\n"
                f"🪙 **Số Gold gốc (1k = 3 Gold):** `{base_g:,}` Thỏi Vàng\n"
                f"🎁 **Ưu đãi chiết khấu (+{disc_p}%):** `+{bonus_g:,}` Thỏi Vàng\n"
                f"─────────────────────────────\n"
                f"👑 **TỔNG GOLD SẼ NHẬN:** **`{tot_g:,}` Thỏi Vàng** <:32100goldbarsfortnite:1514192020921651251>\n\n"
                f"🏦 **Ngân hàng:** `{bank_id}`\n"
                f"💳 **Số tài khoản:** `{bank_account}`\n"
                f"📛 **Chủ tài khoản:** `{account_name}`\n"
                f"📝 **Nội dung chuyển khoản:** `{add_info}` *(Giữ nguyên nội dung này!)*\n\n"
                f"📲 **Quét mã VietQR bên dưới bằng app ngân hàng để chuyển khoản nhanh.**\n"
                f"📌 Sau khi chuyển khoản xong, hãy gửi ảnh biên lai cho Admin/Owner để được xác nhận cộng Gold ngay!"
            )

            embed = make_embed(
                title="💳 MÃ VIETQR NẠP THỎI VÀNG 💳",
                description=desc,
                color=discord.Color.green()
            )
            embed.set_image(url=vietqr_url)
            embed.set_footer(text="Admin sẽ dùng lệnh i?addtopup để xác nhận và cộng Gold cho bạn.")
            await ctx.send(embed=embed)

    @commands.command(
        name="setbank",
        brief="[ADMIN] Cấu hình thông tin ngân hàng hiển thị trên mã VietQR.",
        usage="setbank <bank_id> <số_tài_khoản> <tên_chủ_tài_khoản>",
        aliases=["setbankinfo", "bankset"],
        hidden=True
    )
    async def setbank(self, ctx: commands.Context, bank_id: str = None, bank_account: str = None, *, account_name: str = None):
        if ctx.author.id not in config.bot.owner_ids and ctx.author.id not in config.bot.admin_ids:
            await ctx.send("❌ Lệnh này chỉ dành cho Admin / Owner!")
            return

        if not bank_id or not bank_account or not account_name:
            curr_bank = self.economy.get_setting("bank_id", "MB")
            curr_acc = self.economy.get_setting("bank_account", "0000000000")
            curr_name = self.economy.get_setting("account_name", "ADMIN CASINO")

            embed = make_embed(
                title="🏦 THÔNG TIN NGÂN HÀNG VIETQR HIỆN TẠI 🏦",
                description=(
                    f"🏦 **Mã ngân hàng (Bank ID):** `{curr_bank}` (VD: MB, VCB, ACB, TPB, ICB, BIDV...)\n"
                    f"💳 **Số tài khoản:** `{curr_acc}`\n"
                    f"👤 **Chủ tài khoản:** `{curr_name}`\n\n"
                    f"💡 *Sử dụng cú pháp sau để thay đổi:* `i?setbank <mã_NH> <STK> <Tên_chủ_TK>`\n"
                    f"Ví dụ: `i?setbank MB 0123456789 NGUYEN VAN A`"
                ),
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed)
            return

        bank_id = bank_id.upper().strip()
        bank_account = bank_account.strip()
        account_name = account_name.strip()

        self.economy.set_setting("bank_id", bank_id)
        self.economy.set_setting("bank_account", bank_account)
        self.economy.set_setting("account_name", account_name)
        self.economy.set_setting("bank_configured", "1")

        embed = make_embed(
            title="✅ CẬP NHẬT THÔNG TIN NGÂN HÀNG THÀNH CÔNG ✅",
            description=(
                f"Đã cập nhật thông tin VietQR mới thành công:\n\n"
                f"🏦 **Ngân hàng:** `{bank_id}`\n"
                f"💳 **Số tài khoản:** `{bank_account}`\n"
                f"👤 **Chủ tài khoản:** `{account_name}`"
            ),
            color=discord.Color.green()
        )
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

        vnd_amount = parse_amount(amount_str)
        if not vnd_amount or vnd_amount <= 0:
            await ctx.send("❌ Số tiền nạp không hợp lệ! Ví dụ: `i?addtopup @user 100k` hoặc `i?addtopup @user 500000`.")
            return

        base_g, bonus_g, disc_p, total_gold = calc_gold(vnd_amount)

        if vnd_amount >= TOPUP_CONFIRM_VND_THRESHOLD:
            view = TopupConfirmView(ctx.author, target, vnd_amount, total_gold, disc_p)
            confirm_embed = make_embed(
                title="⚠️ XÁC NHẬN CỘNG GOLD NẠP LỚN",
                description=(
                    f"Bạn sắp cộng **`{total_gold:,}` Thỏi Vàng** cho **{target.mention}**:\n"
                    f"💵 Số tiền nạp: `{vnd_amount:,} VND`\n"
                    f"🪙 Gold gốc: `{base_g:,}` | Ưu đãi +{disc_p}%: `+{bonus_g:,}`\n\n"
                    f"Kiểm tra kỹ biên lai chuyển khoản trước khi xác nhận!"
                ),
                color=discord.Color.orange()
            )
            await ctx.send(embed=confirm_embed, view=view)
            await view.wait()
            if not view.confirmed:
                reason = "⏰ Hết thời gian xác nhận" if view.confirmed is None else "❌ Đã huỷ"
                await ctx.send(f"{reason} — không cộng gold cho **{target.mention}**.")
                return

        self.economy.add_credits(target.id, total_gold)
        new_total_vnd = self.economy.add_user_topup(target.id, vnd_amount, total_gold)
        
        log_wallet_change(logger, event="admin_add_topup", user_id=target.id, credits_delta=total_gold, actor_id=ctx.author.id, ctx=ctx)

        embed = make_embed(
            title="🎉 NẠP THỎI VÀNG THÀNH CÔNG 🎉",
            description=(
                f"ADMIN **{ctx.author.mention}** đã xác nhận nạp tiền cho **{target.mention}**!\n\n"
                f"💵 **Số tiền nạp:** `{vnd_amount:,} VND`\n"
                f"✨ **Số Gold nhận được (+{disc_p}%):** `+{total_gold:,}` Thỏi Vàng <:32100goldbarsfortnite:1514192020921651251>\n"
                f"🏆 **Tổng nạp tích lũy (Top Nạp):** `{new_total_vnd:,} VND`"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="[ADMIN] Xoá người chơi khỏi bảng xếp hạng top nạp.",
        usage="removetopup @user",
        aliases=["removetop", "xoatopnap", "xoatop", "deltopup"],
        hidden=True
    )
    async def removetopup(self, ctx: commands.Context, target: discord.User):
        if ctx.author.id not in config.bot.owner_ids and ctx.author.id not in config.bot.admin_ids:
            await ctx.send("❌ Lệnh này chỉ dành cho Admin / Owner!")
            return

        removed = self.economy.remove_user_topup(target.id)
        if not removed:
            await ctx.send(f"⚠️ Người chơi **{target.mention}** không có dữ liệu trong bảng xếp hạng top nạp.")
            return

        embed = make_embed(
            title="🗑️ ĐÃ XOÁ KHỎI TOP NẠP",
            description=f"ADMIN **{ctx.author.mention}** đã xoá **{target.mention}** (ID: `{target.id}`) khỏi bảng xếp hạng top nạp.",
            color=discord.Color.red()
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

    def _check_and_update_gold_price(self) -> bool:
        current_time = int(time.time())
        last_update_str = self.economy.get_setting("gold_price_last_update")
        
        if last_update_str is None:
            self.economy.set_setting("gold_price_last_update", str(current_time))
            return False
            
        last_update = int(last_update_str)
        one_week = 7 * 24 * 3600
        
        if current_time >= last_update + one_week:
            current_price = self.economy.get_gold_price()
            
            # Mean-reverting random walk
            base_price = 30_000_000
            drift = 0.05 * (base_price - current_price) / base_price
            
            # High volatility: random shock up to 25%
            random_shock = random.uniform(-0.25, 0.25)

            # Supply/demand pressure from last week's gold flows:
            # more gold mined than spent pushes the price down and vice versa.
            mined = int(self.economy.get_setting("gold_mined_week", "0"))
            spent = int(self.economy.get_setting("gold_spent_week", "0"))
            self.economy.set_setting("gold_mined_week", "0")
            self.economy.set_setting("gold_spent_week", "0")
            supply_pressure = 0.0
            if mined + spent > 0:
                net_ratio = (mined - spent) / max(mined, spent)
                supply_pressure = -0.08 * net_ratio
                logger.info(
                    "Gold flow last week: mined=%s spent=%s -> supply_pressure=%.3f",
                    mined, spent, supply_pressure,
                )

            new_price = int(current_price * (1 + drift + random_shock + supply_pressure))
            # Clamp between 3,000,000 and 150,000,000
            new_price = max(3_000_000, min(150_000_000, new_price))
            # Round to nearest 1,000
            new_price = (new_price // 1000) * 1000
            
            self.economy.set_gold_prices(new_price, current_price)
            # Update timestamp to the expected schedule boundary to prevent time drift
            self.economy.set_setting("gold_price_last_update", str(last_update + one_week))
            logger.info(f"Gold price updated (weekly update): {current_price:,} -> {new_price:,} VND")
            return True
        return False

    @tasks.loop(minutes=10)
    async def update_gold_price(self):
        self._check_and_update_gold_price()


async def setup(client: commands.Bot):
    await client.add_cog(Slots(client))
