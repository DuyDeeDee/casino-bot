import asyncio
import logging
import math
import random
import time
from typing import Optional

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)


def parse_bet_amount(val_str: str, current_money: int) -> int:
    val_str = val_str.strip().lower()
    if val_str in ["all", "allin", "all-in", "tất tay"]:
        return current_money

    # Remove separators like commas or dots
    val_str = val_str.replace(",", "").replace(".", "")

    multiplier = 1
    if val_str.endswith("k"):
        multiplier = 1_000
        val_str = val_str[:-1].strip()
    elif val_str.endswith("m"):
        multiplier = 1_000_000
        val_str = val_str[:-1].strip()

    try:
        return int(float(val_str) * multiplier)
    except ValueError:
        return 0


class CrashBetModal(discord.ui.Modal):
    def __init__(self, lobby_view):
        super().__init__(title="Đặt Cược Vào Vòng Crash")
        self.lobby_view = lobby_view

        self.bet_input = discord.ui.TextInput(
            label="Số tiền muốn cược (VND)",
            placeholder="Ví dụ: 10k, 500k, 2m, all",
            required=True,
            max_length=20,
        )
        self.add_item(self.bet_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.lobby_view.is_closed:
            await interaction.response.send_message(
                "❌ Vòng chơi đã bắt đầu! Bạn không thể đặt cược nữa.", ephemeral=True
            )
            return

        user = interaction.user
        val_str = self.bet_input.value

        if user.id in self.lobby_view.participants:
            await interaction.response.send_message(
                "❌ Bạn đã đặt cược trong vòng này rồi! Nếu muốn đổi số tiền, vui lòng hủy cược rồi đặt lại.",
                ephemeral=True,
            )
            return

        profile = self.lobby_view.cog.economy.get_entry(user.id)
        current_money = profile[1]

        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 50k, 100000).",
                ephemeral=True,
            )
            return

        if amount < 1000:
            await interaction.response.send_message(
                "❌ Số tiền cược tối thiểu là **1,000 VND**.", ephemeral=True
            )
            return

        if amount > current_money:
            await interaction.response.send_message(
                f"❌ Bạn không đủ tiền! Số dư ví hiện tại của bạn là **{current_money:,} VND**.",
                ephemeral=True,
            )
            return

        # Deduct money immediately to prevent double spend exploit
        self.lobby_view.cog.economy.add_money(user.id, -amount)

        self.lobby_view.participants[user.id] = {
            "user": user,
            "bet": amount,
            "cashed_out": False,
            "multiplier": 0.0,
        }

        log_wallet_change(
            logger,
            event="crash_place_bet",
            user_id=user.id,
            money_delta=-amount,
            bet_amount=amount,
        )

        await interaction.response.send_message(
            f"✅ Đã đặt cược thành công **{amount:,} VND** vào vòng chơi!",
            ephemeral=True,
        )
        await self.lobby_view.update_message()


class CrashLobbyView(discord.ui.View):
    def __init__(self, cog, session_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.session_id = session_id
        self.participants = {}
        self.is_closed = False
        self.message = None
        self.seconds_remaining = 20
        self.start_time = 0.0
        self.current_multiplier = 1.00
        self.crash_point = 1.00
        self.game_crashed = False

    async def update_message(self):
        if self.message:
            embed = self.create_embed()
            try:
                await self.message.edit(embed=embed, view=self)
            except discord.HTTPException:
                pass

    def create_embed(self) -> discord.Embed:
        embed = make_embed(
            title=f"🚀 CRASH GAME LOBBY — Vòng #{self.session_id} 🚀",
            description=(
                f"⏳ **Thời gian chuẩn bị:** `{self.seconds_remaining} giây`\n"
                f"📈 **Hệ số nhân:** Tăng dần từ `1.00×`\n"
                f"💥 Máy bay có thể nổ bất cứ lúc nào! Hãy nhanh tay rút tiền trước khi nổ để bảo toàn tiền cược.\n\n"
                f"👉 Nhấp vào nút bên dưới để chọn mức cược và tham gia."
            ),
            color=discord.Color.blurple(),
        )

        player_list = []
        total_bet = 0
        for uid, p in self.participants.items():
            player_list.append(f"• **{p['user'].display_name}**: `{p['bet']:,} VND`")
            total_bet += p["bet"]

        player_str = "\n".join(player_list) if player_list else "*Chưa có ai tham gia*"

        embed.add_field(
            name=f"👥 Người chơi đã cược ({len(self.participants)})",
            value=f"💰 Tổng tiền cược: **{total_bet:,} VND**\n{player_str}",
            inline=False,
        )
        embed.set_footer(text="Gõ i?crash để bắt đầu phòng cược")
        return embed

    @discord.ui.button(label="ĐẶT CƯỢC", style=discord.ButtonStyle.primary, emoji="💸")
    async def place_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message(
                "❌ Vòng chơi đã bắt đầu hoặc kết thúc!", ephemeral=True
            )
            return
        modal = CrashBetModal(lobby_view=self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="HỦY CƯỢC", style=discord.ButtonStyle.danger, emoji="❌")
    async def cancel_bet(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.is_closed:
            await interaction.response.send_message(
                "❌ Vòng chơi đã bắt đầu! Không thể hủy cược.", ephemeral=True
            )
            return

        user = interaction.user
        if user.id not in self.participants:
            await interaction.response.send_message(
                "❌ Bạn chưa đặt cược trong phòng này!", ephemeral=True
            )
            return

        refund = self.participants.pop(user.id)["bet"]
        self.cog.economy.add_money(user.id, refund)

        log_wallet_change(
            logger,
            event="crash_cancel_bet",
            user_id=user.id,
            money_delta=refund,
            refund_amount=refund,
        )

        await interaction.response.send_message(
            f"✅ Đã hủy cược thành công! Hoàn lại **{refund:,} VND** vào ví.",
            ephemeral=True,
        )
        await self.update_message()

    @discord.ui.button(label="LỊCH SỬ", style=discord.ButtonStyle.secondary, emoji="📜")
    async def view_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        history = self.cog.crash_history
        if not history:
            await interaction.response.send_message(
                "📜 Chưa có lịch sử trận đấu nào trong phiên làm việc này.", ephemeral=True
            )
            return

        history_lines = []
        for idx, item in enumerate(reversed(history)):
            session_id, cp = item
            history_lines.append(
                f"`#{idx+1}` 🚀 **Vòng #{session_id}** ➔ nổ ở **{cp:.2f}×**"
            )

        embed = discord.Embed(
            title="📜 LỊCH SỬ 10 TRẬN CRASH GẦN NHẤT 📜",
            description="\n".join(history_lines),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class CrashActiveView(discord.ui.View):
    def __init__(self, lobby_view: CrashLobbyView):
        super().__init__(timeout=120.0)
        self.lobby_view = lobby_view

    @discord.ui.button(label="RÚT TIỀN NGAY", style=discord.ButtonStyle.success, emoji="💸")
    async def cashout(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if user.id not in self.lobby_view.participants:
            await interaction.response.send_message(
                "❌ Bạn không tham gia vòng chơi này!", ephemeral=True
            )
            return

        p = self.lobby_view.participants[user.id]
        if p["cashed_out"]:
            await interaction.response.send_message(
                f"❌ Bạn đã rút tiền thành công ở `{p['multiplier']:.2f}x` từ trước rồi!",
                ephemeral=True,
            )
            return

        if self.lobby_view.game_crashed:
            await interaction.response.send_message(
                f"💥 Quá trễ rồi! Game đã crash ở `{self.lobby_view.crash_point:.2f}x`!",
                ephemeral=True,
            )
            return

        # Double check crash to prevent latency/exploit issues
        elapsed = time.time() - self.lobby_view.start_time
        temp_mult = round(math.exp(0.065 * elapsed), 2)
        if temp_mult >= self.lobby_view.crash_point:
            self.lobby_view.game_crashed = True
            await interaction.response.send_message(
                f"💥 Quá trễ rồi! Game đã crash ở `{self.lobby_view.crash_point:.2f}x`!",
                ephemeral=True,
            )
            return

        # Success cash out
        mult = self.lobby_view.current_multiplier
        p["cashed_out"] = True
        p["multiplier"] = mult

        winnings = int(p["bet"] * mult)
        self.lobby_view.cog.economy.add_money(user.id, winnings)

        log_wallet_change(
            logger,
            event="crash_payout_win",
            user_id=user.id,
            money_delta=winnings,
            bet=p["bet"],
            multiplier=mult,
        )

        await interaction.response.send_message(
            f"✅ Rút tiền thành công ở **{mult:.2f}x**! Nhận **+{winnings:,} VND**.",
            ephemeral=True,
        )


class Crash(commands.Cog, name="Crash"):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())
        self.active_sessions = set()
        self.crash_history = []

    def generate_crash_point(self, house_edge: float = 0.04) -> float:
        r = random.random()
        if r < house_edge:
            return 1.00  # crash immediately
        return round(1 / (1 - r), 2)

    @commands.command(
        brief="Trò chơi Crash Game (Multiplier tăng dần liên tục, bấm rút tiền trước khi nổ).",
        usage="crash",
        aliases=["cr"],
    )
    async def crash(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        if channel_id in self.active_sessions:
            await ctx.send(
                "❌ **Lỗi:** Đang có một phiên Crash Game đang diễn ra ở kênh này. Vui lòng đợi phiên cược kết thúc!"
            )
            return

        self.active_sessions.add(channel_id)
        session_id = random.randint(100000, 999999)

        try:
            # Setup lobby
            lobby = CrashLobbyView(self, session_id=session_id)
            embed = lobby.create_embed()
            message = await ctx.send(embed=embed, view=lobby)
            lobby.message = message

            # Lobby countdown loop
            while lobby.seconds_remaining > 0:
                await asyncio.sleep(5)
                lobby.seconds_remaining -= 5
                if lobby.seconds_remaining <= 0:
                    break
                await lobby.update_message()

            lobby.is_closed = True

            # Disable lobby buttons
            for child in lobby.children:
                if isinstance(child, discord.ui.Button):
                    child.disabled = True
            try:
                await message.edit(view=lobby)
            except discord.HTTPException:
                pass

            # Check if there are participants
            if not lobby.participants:
                embed = make_embed(
                    title=f"🚀 CRASH GAME LOBBY — Vòng #{session_id} 🚀",
                    description="❌ **HỦY VÒNG CHƠI:** Không có ai đặt cược trong thời gian chuẩn bị.",
                    color=discord.Color.red(),
                )
                await message.edit(embed=embed, view=None)
                return

            # Start the game loop
            crash_point = self.generate_crash_point()
            lobby.crash_point = crash_point
            lobby.start_time = time.time()

            active_view = CrashActiveView(lobby)

            # Check for instant crash (1.00x)
            if crash_point == 1.00:
                lobby.game_crashed = True
                lobby.current_multiplier = 1.00
                await self.end_game(message, lobby, session_id)
                return

            # Keep editing the message until crash
            while not lobby.game_crashed:
                # Check if all players cashed out early to save performance
                all_cashed_out = all(p["cashed_out"] for p in lobby.participants.values())
                if all_cashed_out:
                    break

                elapsed = time.time() - lobby.start_time
                calc_mult = round(math.exp(0.065 * elapsed), 2)

                if calc_mult >= crash_point:
                    lobby.current_multiplier = crash_point
                    lobby.game_crashed = True
                    break

                lobby.current_multiplier = calc_mult

                # Update the active embed
                active_embed = self.create_active_embed(lobby, session_id)
                try:
                    await message.edit(embed=active_embed, view=active_view)
                except discord.HTTPException:
                    pass

                await asyncio.sleep(1.5)

            # Game is over
            lobby.game_crashed = True
            await self.end_game(message, lobby, session_id)

        finally:
            self.active_sessions.discard(channel_id)

    def create_active_embed(self, lobby: CrashLobbyView, session_id: int) -> discord.Embed:
        embed = make_embed(
            title=f"🚀 CRASH GAME — Vòng #{session_id} 🚀",
            description=(
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **Multiplier:** **`{lobby.current_multiplier:.2f}×`**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
                f"👉 Bấm nút **[ 💸 Rút Tiền Ngay ]** phía dưới để rút tiền!"
            ),
            color=discord.Color.green(),
        )

        player_status = []
        for uid, p in lobby.participants.items():
            if p["cashed_out"]:
                payout = int(p["bet"] * p["multiplier"])
                player_status.append(
                    f"✅ **{p['user'].display_name}**: Đã rút cược ở `{p['multiplier']:.2f}x` ➔ nhận **+{payout:,} VND**"
                )
            else:
                current_value = int(p["bet"] * lobby.current_multiplier)
                player_status.append(
                    f"• **{p['user'].display_name}**: `{p['bet']:,} VND` ➔ `💰 {current_value:,} VND` nếu rút ngay"
                )

        status_str = "\n".join(player_status)
        embed.add_field(name="👥 Danh Sách Đang Chơi", value=status_str, inline=False)
        return embed

    async def end_game(self, message: discord.Message, lobby: CrashLobbyView, session_id: int):
        # Add to history
        self.crash_history.append((session_id, lobby.crash_point))
        self.crash_history = self.crash_history[-10:]

        embed = make_embed(
            title=f"💥 CRASH GAME KẾT THÚC — Vòng #{session_id} 💥",
            description=(
                f"━━━━━━━━━━━━━━━━━━━━━━\n"
                f"📈 **Hệ số nhân nổ:** **`{lobby.crash_point:.2f}×`**\n"
                f"━━━━━━━━━━━━━━━━━━━━━━"
            ),
            color=discord.Color.red(),
        )

        player_results = []
        for uid, p in lobby.participants.items():
            if p["cashed_out"]:
                payout = int(p["bet"] * p["multiplier"])
                net = payout - p["bet"]
                player_results.append(
                    f"🟢 **{p['user'].display_name}**: Rút thành công ở `{p['multiplier']:.2f}x` ➔ Nhận `{payout:,} VND` (Lời `+{net:,} VND`)"
                )
            else:
                player_results.append(
                    f"🔴 **{p['user'].display_name}**: Không kịp rút ở `{lobby.crash_point:.2f}x` ➔ Mất sạch `-{p['bet']:,} VND`"
                )
                log_wallet_change(
                    logger,
                    event="crash_payout_lose",
                    user_id=uid,
                    money_delta=0,
                    bet=p["bet"],
                    multiplier=lobby.crash_point,
                )

        result_str = "\n".join(player_results)
        embed.add_field(name="🏁 Kết Quả Vòng Đấu", value=result_str, inline=False)

        try:
            await message.edit(embed=embed, view=None)
        except discord.HTTPException:
            pass


async def setup(client: commands.Bot):
    await client.add_cog(Crash(client))
