# coding: utf-8
"""
UNO Discord Cog
Xử lý các lệnh và UI cho game UNO trên Discord.
Hỗ trợ đầy đủ tiếng Việt có dấu, hiển thị hình ảnh lá bài, và sử dụng nút bấm/dropdown tương tác ẩn.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import suppress
from typing import Optional
from uuid import uuid4

import discord
from discord.ext import commands

from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.uno_engine import (
    Color, Value, UnoCard, UnoGame, UnoPlayer,
    GamePhase, COLOR_EMOJI, COLOR_LABEL,
)

logger = logging.getLogger(__name__)

DISCORD_COLOR = {
    Color.RED:    discord.Color.from_rgb(231, 76, 60),
    Color.YELLOW: discord.Color.from_rgb(241, 196, 15),
    Color.GREEN:  discord.Color.from_rgb(39, 174, 96),
    Color.BLUE:   discord.Color.from_rgb(52, 152, 219),
    Color.WILD:   discord.Color.from_rgb(155, 89, 182),
}

TURN_TIMEOUT = 30
UNO_CALL_TIMEOUT = 15


# ==============================================================================
#  Views & Dropdowns
# ==============================================================================

class LobbyView(discord.ui.View):
    def __init__(self, game: UnoGame, cog: "Uno"):
        super().__init__(timeout=90.0)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="✅ Tham Gia", style=discord.ButtonStyle.success, custom_id="uno_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        balance = self.cog.economy.get_entry(user.id)[1]
        if balance < self.game.bet:
            await interaction.response.send_message(
                f"❌ Bạn không đủ tiền! Cần `{self.game.bet:,} VND`.", ephemeral=True
            )
            return
        added = self.game.add_player(user.id, user.display_name)
        if not added:
            await interaction.response.send_message(
                "❌ Bạn đã ở trong phòng hoặc phòng đã đầy!", ephemeral=True
            )
            return
        self.cog.economy.add_money(user.id, -self.game.bet)
        await interaction.response.send_message(
            f"✅ Đã tham gia! Đã trừ cọc `{self.game.bet:,} VND`.", ephemeral=True
        )
        await self.cog._update_lobby_embed(interaction.message)

    @discord.ui.button(label="🚀 Bắt Đầu", style=discord.ButtonStyle.primary, custom_id="uno_start")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ chủ phòng mới được bắt đầu!", ephemeral=True)
            return
        if len(self.game.players) < 2:
            await interaction.response.send_message("❌ Cần ít nhất 2 người chơi để bắt đầu!", ephemeral=True)
            return
        self.stop()
        await interaction.response.defer()
        await self.cog._start_game(interaction.message)


class ColorPickView(discord.ui.View):
    def __init__(self, player_id: int, timeout: float = 15.0):
        super().__init__(timeout=timeout)
        self.player_id = player_id
        self.chosen_color: Optional[Color] = None
        specs = [
            (Color.RED,    "🔴 Đỏ",         discord.ButtonStyle.danger),
            (Color.YELLOW, "🟡 Vàng",       discord.ButtonStyle.secondary),
            (Color.GREEN,  "🟢 Xanh Lá",     discord.ButtonStyle.success),
            (Color.BLUE,   "🔵 Xanh Dương",  discord.ButtonStyle.primary),
        ]
        for color, label, style in specs:
            uid = uuid4().hex[:4]
            btn = discord.ui.Button(label=label, style=style,
                                    custom_id=f"clr_{color.value}_{uid}")
            btn.callback = self._make_cb(color)
            self.add_item(btn)

    def _make_cb(self, color: Color):
        async def cb(interaction: discord.Interaction):
            self.chosen_color = color
            self.stop()
            await interaction.response.defer()
        return cb

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player_id:
            await interaction.response.send_message("❌ Không phải lượt của bạn!", ephemeral=True)
            return False
        return True


class HandDropdown(discord.ui.Select):
    """Dropdown chọn lá bài để đánh trực tiếp từ tin nhắn ẩn."""
    def __init__(self, player: UnoPlayer, game: UnoGame, cog: "Uno", playable_cards: list[tuple[int, UnoCard]]):
        options = []
        for idx, card in playable_cards[:25]:  # Discord giới hạn tối đa 25 options
            options.append(
                discord.SelectOption(
                    label=card.display(),
                    value=str(idx),
                    description="Đánh lá bài này"
                )
            )
        super().__init__(
            placeholder="👉 Chọn một lá bài để đánh...",
            min_values=1,
            max_values=1,
            options=options,
            custom_id="uno_select_card",
        )
        self.player = player
        self.game = game
        self.cog = cog
        self.playable_cards = playable_cards

    async def callback(self, interaction: discord.Interaction):
        if self.game.current_player.user_id != interaction.user.id:
            await interaction.response.send_message("❌ Chưa đến lượt của bạn!", ephemeral=True)
            return

        idx = int(self.values[0])
        if idx >= len(self.player.hand):
            await interaction.response.send_message("❌ Lá bài không hợp lệ!", ephemeral=True)
            return

        card = self.player.hand[idx]

        # Chọn màu khi đánh Wild / Wild+4
        chosen_color = None
        if card.value in {Value.WILD, Value.WILD4}:
            view = ColorPickView(self.player.user_id, timeout=15.0)
            await interaction.response.edit_message(
                content="🌈 **Chọn màu mới cho bộ bài:**", 
                embed=None, 
                view=view
            )
            timed_out = await view.wait()
            if timed_out or view.chosen_color is None:
                # Trả lại màn hình bài nếu huỷ bỏ
                embed = self.cog._make_hand_embed(self.player, self.game)
                playable = [(i, c) for i, c in enumerate(self.player.hand) if c.can_play_on(self.game.top_card, self.game.current_color)]
                h_view = HandView(self.player, self.game, self.cog, playable)
                try:
                    await interaction.followup.send(embed=embed, view=h_view, ephemeral=True)
                except Exception:
                    pass
                return
            chosen_color = view.chosen_color
        else:
            await interaction.response.defer()

        # Thực hiện đánh bài
        is_stacking = self.game.pending_draw > 0
        success, msg = self.game.play_card(self.player, card, chosen_color, stacking=is_stacking)
        if not success:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return

        # Cập nhật tin nhắn ẩn sau khi đánh thành công
        await interaction.edit_original_response(
            content=f"✅ Bạn đã đánh lá bài **{card.display()}** thành công!", 
            embed=None, 
            view=None
        )

        if msg == "WIN":
            await self.cog._handle_win_no_ctx(interaction.channel, self.game, self.player)
            return

        effect = self.game.apply_card_effect(card)
        await self.cog._broadcast_card_played_no_ctx(interaction.channel, self.game, self.player, card, effect, chosen_color)
        await self.cog._update_board(interaction.channel, self.game)

        if self.game.uno_pending_user_id:
            asyncio.create_task(self.cog._start_uno_timer(self.game, self.game.uno_pending_user_id, interaction.channel))


class HandDrawButton(discord.ui.Button):
    """Nút rút bài hiển thị trực tiếp trong tay bài ẩn."""
    def __init__(self, player: UnoPlayer, game: UnoGame, cog: "Uno"):
        is_my_turn = game.current_player.user_id == player.user_id
        super().__init__(
            label="📥 Rút Bài / Chịu Phạt",
            style=discord.ButtonStyle.primary if is_my_turn else discord.ButtonStyle.secondary,
            disabled=not is_my_turn,
            custom_id=f"uno_hand_dr_{uuid4().hex[:4]}",
        )
        self.player = player
        self.game = game
        self.cog = cog

    async def callback(self, interaction: discord.Interaction):
        if self.game.current_player.user_id != interaction.user.id:
            await interaction.response.send_message("❌ Chưa đến lượt của bạn!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog._perform_draw_interaction(interaction, self.player)


class HandView(discord.ui.View):
    """View hiển thị trong tin nhắn ẩn Xem Bài."""
    def __init__(self, player: UnoPlayer, game: UnoGame, cog: "Uno", playable_cards: list[tuple[int, UnoCard]]):
        super().__init__(timeout=60.0)
        self.player = player
        self.game = game
        self.cog = cog
        
        is_my_turn = game.current_player.user_id == player.user_id
        if playable_cards and is_my_turn:
            self.add_item(HandDropdown(player, game, cog, playable_cards))
        
        self.add_item(HandDrawButton(player, game, cog))


class DrawPlayView(discord.ui.View):
    """Giao diện quyết định khi vừa rút được một lá có thể đánh ngay."""
    def __init__(self, player: UnoPlayer, game: UnoGame, cog: "Uno", card: UnoCard):
        super().__init__(timeout=30.0)
        self.player = player
        self.game = game
        self.cog = cog
        self.card = card

    @discord.ui.button(label="Play / Đánh Lá Này", style=discord.ButtonStyle.success, custom_id="uno_draw_play")
    async def play_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.current_player.user_id != interaction.user.id:
            await interaction.response.send_message("❌ Chưa đến lượt của bạn!", ephemeral=True)
            return

        chosen_color = None
        if self.card.value in {Value.WILD, Value.WILD4}:
            view = ColorPickView(self.player.user_id, timeout=15.0)
            await interaction.response.edit_message(content="🌈 **Chọn màu mới cho bộ bài:**", embed=None, view=view)
            timed_out = await view.wait()
            if timed_out or view.chosen_color is None:
                # Quá giờ chọn màu -> huỷ đánh, chuyển lượt
                self.game.advance_turn()
                await self.cog._update_board(interaction.channel, self.game)
                return
            chosen_color = view.chosen_color
        else:
            await interaction.response.defer()

        is_stacking = self.game.pending_draw > 0
        success, msg = self.game.play_card(self.player, self.card, chosen_color, stacking=is_stacking)
        if not success:
            await interaction.followup.send(f"❌ {msg}", ephemeral=True)
            return

        await interaction.edit_original_response(content=f"✅ Bạn đã đánh lá bài **{self.card.display()}**!", embed=None, view=None)

        if msg == "WIN":
            await self.cog._handle_win_no_ctx(interaction.channel, self.game, self.player)
            return

        effect = self.game.apply_card_effect(self.card)
        await self.cog._broadcast_card_played_no_ctx(interaction.channel, self.game, self.player, self.card, effect, chosen_color)
        await self.cog._update_board(interaction.channel, self.game)

        if self.game.uno_pending_user_id:
            asyncio.create_task(self.cog._start_uno_timer(self.game, self.game.uno_pending_user_id, interaction.channel))

    @discord.ui.button(label="Pass / Bỏ Lượt", style=discord.ButtonStyle.secondary, custom_id="uno_draw_pass")
    async def pass_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.game.current_player.user_id != interaction.user.id:
            await interaction.response.send_message("❌ Chưa đến lượt của bạn!", ephemeral=True)
            return
        await interaction.response.defer()
        await interaction.edit_original_response(content="❌ Bạn đã chọn bỏ lượt chơi.", embed=None, view=None)
        self.game.advance_turn()
        await self.cog._update_board(interaction.channel, self.game)


class BoardView(discord.ui.View):
    """View tương tác chính ở kênh chung."""
    def __init__(self, game: UnoGame, cog: "Uno"):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="👁️ Xem Bài", style=discord.ButtonStyle.secondary, custom_id="uno_board_hand")
    async def hand_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.game.get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("❌ Bạn không tham gia trò chơi này!", ephemeral=True)
            return
        
        playable = []
        is_my_turn = self.game.current_player.user_id == player.user_id
        if is_my_turn:
            if self.game.pending_draw > 0:
                sv = Value.DRAW2 if self.game.pending_draw_type == "draw2" else Value.WILD4
                playable = [(i, c) for i, c in enumerate(player.hand) if c.value == sv]
            else:
                playable = [(i, c) for i, c in enumerate(player.hand) if c.can_play_on(self.game.top_card, self.game.current_color)]
        
        embed = self.cog._make_hand_embed(player, self.game)
        view = HandView(player, self.game, self.cog, playable)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="📥 Rút Bài", style=discord.ButtonStyle.primary, custom_id="uno_board_draw")
    async def draw_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.game.get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("❌ Bạn không tham gia trò chơi này!", ephemeral=True)
            return
        if self.game.current_player.user_id != interaction.user.id:
            await interaction.response.send_message("❌ Chưa đến lượt của bạn!", ephemeral=True)
            return
        await interaction.response.defer()
        await self.cog._perform_draw_interaction(interaction, player)

    @discord.ui.button(label="🔔 Hô UNO!", style=discord.ButtonStyle.success, custom_id="uno_board_uno")
    async def uno_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.game.get_player(interaction.user.id)
        if not player:
            await interaction.response.send_message("❌ Bạn không tham gia trò chơi này!", ephemeral=True)
            return
        success, msg = self.game.call_uno(interaction.user.id)
        if success:
            await interaction.response.send_message("🔔 Bạn đã hô UNO thành công!", ephemeral=True)
            await interaction.channel.send(f"📣 **{interaction.user.display_name}**: **\"UNO!\"** 🎉")
        else:
            await interaction.response.send_message(f"❌ {msg}", ephemeral=True)

    @discord.ui.button(label="📢 Tố Cáo", style=discord.ButtonStyle.danger, custom_id="uno_board_accuse")
    async def accuse_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        target_id = self.game.uno_pending_user_id
        if not target_id:
            await interaction.response.send_message("❌ Không có ai để tố cáo lúc này!", ephemeral=True)
            return
        if interaction.user.id == target_id:
            await interaction.response.send_message("❌ Bạn không thể tự tố cáo chính mình!", ephemeral=True)
            return
        
        result, count = self.game.accuse_uno(interaction.user.id, target_id)
        accuser_name = interaction.user.display_name
        target = self.game.get_player(target_id)
        target_name = target.username if target else "Ai đó"

        if result == "success":
            await interaction.response.send_message("📢 Tố cáo thành công!", ephemeral=True)
            await interaction.channel.send(
                embed=make_embed(
                    title="📢 Tố Cáo Thành Công!",
                    description=f"**{target_name}** đã quên hô UNO!\n😤 **{target_name}** bị phạt rút **2 lá**!",
                    color=discord.Color.red(),
                )
            )
            await self.cog._update_board(interaction.channel, self.game)
        elif result == "fail":
            await interaction.response.send_message("❌ Tố cáo thất bại!", ephemeral=True)
            await interaction.channel.send(
                embed=make_embed(
                    title="❌ Tố Cáo Thất Bại!",
                    description=f"**{target_name}** đã hô UNO rồi!\n😤 **{accuser_name}** bị phạt rút **1 lá**!",
                    color=discord.Color.orange(),
                )
            )
            await self.cog._update_board(interaction.channel, self.game)
        else:
            await interaction.response.send_message("❌ Không thể tố cáo lúc này!", ephemeral=True)


# ==============================================================================
#  Cog
# ==============================================================================

class Uno(commands.Cog, name="UNO"):
    active_games: dict[int, UnoGame] = {}

    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy: Economy = getattr(client, "economy", Economy())

    # --------------------------------------------------------------------------
    #  Commands
    # --------------------------------------------------------------------------

    @commands.group(
        name="uno", aliases=["u"],
        invoke_without_command=True,
        brief="🃏 Chơi UNO nhiều người",
    )
    async def uno(self, ctx: commands.Context):
        embed = make_embed(
            title="🃏 UNO - Hướng Dẫn",
            description=(
                "**Các lệnh chính:**\n"
                "`uno create <tiền>` - Tạo phòng mới\n"
                "`uno join`          - Tham gia phòng đang có\n"
                "`uno hand`          - Xem bài của bạn (tin nhắn ẩn)\n"
                "`uno play <mã>`     - Đánh bài (ví dụ: `R7`, `GD2`, `WD4`)\n"
                "`uno draw`          - Rút bài hoặc nhận phạt combo\n"
                "`uno uno`           - Hô UNO!\n"
                "`uno leave`         - Rời phòng chờ\n\n"
                "**Mã màu & Mã bài:**\n"
                "`R`=🔴 Đỏ, `Y`=🟡 Vàng, `G`=🟢 Xanh Lá, `B`=🔵 Xanh Dương\n"
                "`S`=Skip, `RV`=Reverse, `D2`=+2, `W`=Wild, `WD4`=Wild+4\n\n"
                "**Luật Combo / Stacking:**\n"
                "Khi bị đánh +2 hoặc +4, bạn phải chồng lá tương ứng (+2 chồng +2, +4 chồng +4) để cộng dồn, hoặc bấm nút **📥 Rút Bài** để nhận phạt rút tất cả bài và mất lượt."
            ),
            color=discord.Color.purple(),
        )
        await ctx.send(embed=embed)

    @uno.command(name="create", brief="Tạo phòng UNO")
    @commands.max_concurrency(1, per=commands.BucketType.channel, wait=False)
    async def uno_create(self, ctx: commands.Context, bet: int = 50_000):
        if ctx.channel.id in self.active_games:
            await ctx.send("❌ Kênh này hiện đã có phòng chơi UNO rồi!", delete_after=5)
            return
        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
        except Exception as e:
            await ctx.send(f"❌ {e}", delete_after=8)
            return
        self.economy.add_money(ctx.author.id, -bet)
        game = UnoGame(channel_id=ctx.channel.id, host_id=ctx.author.id, bet=bet)
        game.add_player(ctx.author.id, ctx.author.display_name)
        self.active_games[ctx.channel.id] = game
        view = LobbyView(game, self)
        msg = await ctx.send(embed=self._make_lobby_embed(game), view=view)
        game.lobby_msg_id = msg.id
        asyncio.create_task(self._lobby_timeout(ctx.channel.id, msg, 90))

    @uno.command(name="join", brief="Tham gia phòng UNO")
    async def uno_join(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.LOBBY:
            await ctx.send("❌ Không có phòng UNO nào đang chờ tham gia ở kênh này!", delete_after=5)
            return
        if self.economy.get_entry(ctx.author.id)[1] < game.bet:
            await ctx.send(f"❌ Bạn không đủ tiền! Cần `{game.bet:,} VND`.", delete_after=5)
            return
        if not game.add_player(ctx.author.id, ctx.author.display_name):
            await ctx.send("❌ Bạn đã ở trong phòng chơi này rồi hoặc phòng đã đầy!", delete_after=5)
            return
        self.economy.add_money(ctx.author.id, -game.bet)
        await ctx.send(f"✅ **{ctx.author.display_name}** đã tham gia phòng chơi UNO!", delete_after=5)

    @uno.command(name="hand", aliases=["bai"], brief="Xem bài trên tay (tin nhắn ẩn)")
    async def uno_hand(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            await ctx.send("❌ Không có game UNO nào đang chạy ở kênh này!", delete_after=5)
            return
        player = game.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Bạn không có trong trò chơi này!", delete_after=5)
            return
        
        playable = []
        is_my_turn = game.current_player.user_id == ctx.author.id
        if is_my_turn:
            if game.pending_draw > 0:
                sv = Value.DRAW2 if game.pending_draw_type == "draw2" else Value.WILD4
                playable = [(i, c) for i, c in enumerate(player.hand) if c.value == sv]
            else:
                playable = [(i, c) for i, c in enumerate(player.hand) if c.can_play_on(game.top_card, game.current_color)]
        
        embed = self._make_hand_embed(player, game)
        view = HandView(player, game, self, playable)
        await ctx.send(embed=embed, view=view, ephemeral=True)

    @uno.command(name="play", aliases=["p"], brief="Đánh bài")
    async def uno_play(self, ctx: commands.Context, card_code: str = ""):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            await ctx.send("❌ Không có game UNO nào đang chạy ở đây!", delete_after=5)
            return
        player = game.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Bạn không có trong trò chơi này!", delete_after=5)
            return
        if game.current_player.user_id != ctx.author.id:
            await ctx.send("❌ Chưa đến lượt của bạn!", delete_after=5, ephemeral=True)
            return

        card = self._parse_card_code(card_code.upper(), player.hand)
        if card is None:
            await ctx.send(
                f"❌ Mã bài `{card_code}` không hợp lệ hoặc bạn không có lá này trên tay!\n"
                "Hãy bấm nút **👁️ Xem Bài** để xem bài.",
                ephemeral=True, delete_after=10,
            )
            return

        # Kiểm tra luật combo
        is_stacking = False
        if game.pending_draw > 0:
            type_label = "➕2" if game.pending_draw_type == "draw2" else "🌈+4"
            can_stack = (
                (game.pending_draw_type == "draw2" and card.value == Value.DRAW2) or
                (game.pending_draw_type == "wild4" and card.value == Value.WILD4)
            )
            if not can_stack:
                await ctx.send(
                    f"⚠️ Bạn đang bị dồn bài phạt **{game.pending_draw} lá**!\n"
                    f"Bạn phải đánh lá {type_label} để chồng combo, hoặc bấm nút **📥 Rút Bài** để rút phạt.",
                    ephemeral=True, delete_after=12,
                )
                return
            is_stacking = True

        # Chọn màu khi đánh Wild / Wild+4
        chosen_color = None
        if card.value in {Value.WILD, Value.WILD4}:
            chosen_color = await self._prompt_color(ctx, player)
            if chosen_color is None:
                await ctx.send("⏰ Quá thời gian chọn màu - lượt chơi đã bị bỏ qua.", delete_after=5)
                return

        success, msg = game.play_card(player, card, chosen_color, stacking=is_stacking)
        if not success:
            await ctx.send(f"❌ {msg}", ephemeral=True, delete_after=10)
            return

        with suppress(discord.HTTPException):
            await ctx.message.delete(delay=1)

        if msg == "WIN":
            await self._handle_win_no_ctx(ctx.channel, game, player)
            return

        effect = game.apply_card_effect(card)
        await self._broadcast_card_played_no_ctx(ctx.channel, game, player, card, effect, chosen_color)
        await self._update_board(ctx.channel, game)

        if game.uno_pending_user_id:
            asyncio.create_task(self._start_uno_timer(game, game.uno_pending_user_id, ctx.channel))

    @uno.command(name="draw", aliases=["rut"], brief="Rút bài hoặc chịu phạt combo")
    async def uno_draw(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            await ctx.send("❌ Không có game UNO nào đang chạy ở đây!", delete_after=5)
            return
        player = game.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Bạn không có trong trò chơi này!", delete_after=5)
            return
        if game.current_player.user_id != ctx.author.id:
            await ctx.send("❌ Chưa đến lượt của bạn!", delete_after=5)
            return
        
        # We can simulate button click context by drawing directly
        # Since we don't have interaction response here, we draw normally
        if game.pending_draw > 0:
            count = game.pending_draw
            type_label = "➕2" if game.pending_draw_type == "draw2" else "🌈+4"
            game.resolve_pending_draw(player)
            game.advance_turn()
            await ctx.send(embed=make_embed(
                title=f"📦 {ctx.author.display_name} chịu phạt combo!",
                description=f"Không có lá {type_label} để chồng!\n📄 Phải rút **{count} lá** và mất lượt.",
                color=discord.Color.red(),
            ))
            await self._update_board(ctx.channel, game)
            return

        drawn = game.draw_cards(player, 1)
        if not drawn:
            await ctx.send("❌ Bộ bài đã cạn!", delete_after=5)
            return
        card = drawn[0]
        can_play = card.can_play_on(game.top_card, game.current_color)
        
        # Send ephemeral result to user
        try:
            await ctx.author.send(
                embed=make_embed(
                    title="🎴 Rút Bài",
                    description=(
                        f"Bạn đã rút được lá: **{card.display()}**\n" + (
                            f"✅ Lá bài này có thể đánh được ngay!"
                            if can_play else "❌ Lá bài này không thể đánh được. Lượt chơi kết thúc."
                        )
                    ),
                    color=DISCORD_COLOR.get(game.current_color, discord.Color.purple())
                )
            )
        except Exception:
            pass

        if not can_play:
            game.advance_turn()
        await self._update_board(ctx.channel, game)

    @uno.command(name="uno", brief="Hô UNO!")
    async def uno_call(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            return
        player = game.get_player(ctx.author.id)
        if not player:
            return
        success, msg = game.call_uno(ctx.author.id)
        if success:
            await ctx.send(f"📣 **{ctx.author.display_name}**: **\"UNO!\"** 🎉🎉🎉")
        else:
            await ctx.send(f"❌ {msg}", ephemeral=True, delete_after=5)

    @uno.command(name="leave", brief="Rời phòng chờ UNO")
    async def uno_leave(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game:
            return
        player = game.get_player(ctx.author.id)
        if not player:
            return
        if game.phase == GamePhase.LOBBY:
            self.economy.add_money(ctx.author.id, game.bet)
            game.remove_player(ctx.author.id)
            await ctx.send(
                f"🚪 **{ctx.author.display_name}** đã rời phòng. Hoàn lại `{game.bet:,} VND` cọc.",
                delete_after=8,
            )
            if ctx.author.id == game.host_id and game.players:
                game.host_id = game.players[0].user_id
            elif not game.players:
                self.active_games.pop(ctx.channel.id, None)
        else:
            await ctx.send("❌ Game đang chạy! Không thể rời bàn lúc này.", delete_after=8)

    # --------------------------------------------------------------------------
    #  Logic Thực Hiện Rút Bài từ Nút Ephemeral
    # --------------------------------------------------------------------------

    async def _perform_draw_interaction(self, interaction: discord.Interaction, player: UnoPlayer):
        game = self.active_games.get(interaction.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            return
        if game.current_player.user_id != player.user_id:
            return

        # Chịu phạt combo
        if game.pending_draw > 0:
            count = game.pending_draw
            type_label = "➕2" if game.pending_draw_type == "draw2" else "🌈+4"
            game.resolve_pending_draw(player)
            game.advance_turn()
            
            await interaction.edit_original_response(
                content=f"📦 Bạn đã nhận phạt combo rút **{count} lá**!",
                embed=None,
                view=None
            )
            
            await interaction.channel.send(embed=make_embed(
                title=f"📦 {player.username} chịu phạt combo!",
                description=f"Không có lá {type_label} để chồng!\n📄 Phải rút **{count} lá** và mất lượt.",
                color=discord.Color.red(),
            ))
            await self._update_board(interaction.channel, game)
            return

        # Rút 1 lá bình thường
        drawn = game.draw_cards(player, 1)
        if not drawn:
            await interaction.followup.send("❌ Bộ bài đã cạn!", ephemeral=True)
            return
            
        card = drawn[0]
        can_play = card.can_play_on(game.top_card, game.current_color)
        
        if can_play:
            embed = make_embed(
                title="🎴 Rút Bài",
                description=(
                    f"Bạn đã rút được lá: **{card.display()}**\n"
                    f"✅ Lá bài này **có thể đánh được ngay**!\n"
                    f"Chọn hành động bên dưới:"
                ),
                color=DISCORD_COLOR.get(game.current_color, discord.Color.purple())
            )
            view = DrawPlayView(player, game, self, card)
            await interaction.edit_original_response(embed=embed, view=view)
        else:
            await interaction.edit_original_response(
                content=f"❌ Bạn rút được lá **{card.display()}** (không thể đánh) và kết thúc lượt.",
                embed=None,
                view=None
            )
            game.advance_turn()
            await self._update_board(interaction.channel, game)

    # --------------------------------------------------------------------------
    #  Helpers
    # --------------------------------------------------------------------------

    async def _lobby_timeout(self, channel_id: int, msg: discord.Message, seconds: int):
        await asyncio.sleep(seconds)
        game = self.active_games.get(channel_id)
        if game and game.phase == GamePhase.LOBBY:
            for p in game.players:
                self.economy.add_money(p.user_id, game.bet)
            self.active_games.pop(channel_id, None)
            with suppress(discord.HTTPException):
                await msg.edit(embed=make_embed(
                    title="⏰ Phòng chơi đã tự đóng",
                    description="Không đủ người chơi tham gia trong thời gian quy định. Đã hoàn trả tiền cọc.",
                    color=discord.Color.red(),
                ), view=None)

    def _make_lobby_embed(self, game: UnoGame) -> discord.Embed:
        lines = "\n".join(
            f"👑 [Chủ Phòng] {p.username}" if p.user_id == game.host_id else f"🎮 [Người Chơi] {p.username}"
            for p in game.players
        )
        return make_embed(
            title="🃏 PHÒNG UNO MỚI ĐANG CHỜ!",
            description=(
                f"💰 **Tiền Cược:** `{game.bet:,} VND / người`\n"
                f"👥 **Danh sách ({len(game.players)}/8):**\n{lines}\n\n"
                "⏱️ Phòng chơi sẽ đóng sau 90 giây nếu không bắt đầu."
            ),
            color=discord.Color.purple(),
        )

    async def _update_lobby_embed(self, msg: discord.Message):
        game = next((g for g in self.active_games.values() if g.lobby_msg_id == msg.id), None)
        if game:
            with suppress(discord.HTTPException):
                await msg.edit(embed=self._make_lobby_embed(game))

    async def _start_game(self, lobby_msg: discord.Message):
        game = self.active_games.get(lobby_msg.channel.id)
        if not game:
            return
        game.start_game()
        with suppress(discord.HTTPException):
            await lobby_msg.delete()
        channel = lobby_msg.channel
        desc = (
            f"🎮 **Số người chơi:** {len(game.players)} | 💰 **Tiền cọc:** `{game.bet:,} VND`\n"
            f"🎴 **Lá mở đầu:** **{game.top_card.display()}**\n\n"
            "🔔 Bấm nút **👁️ Xem Bài** bên dưới bảng để xem những lá bài đang giữ!"
        )
        if game.pending_draw > 0:
            tl = "➕2" if game.pending_draw_type == "draw2" else "🌈+4"
            desc += f"\n\n⚠️ **CẢNH BÁO:** Lá bài mở đầu tạo ra **{game.pending_draw} lá combo**! **{game.current_player.username}** phải chồng {tl} hoặc rút bài!"
        
        await channel.send(embed=make_embed(
            title="🎉 TRÒ CHƠI UNO BẮT ĐẦU!", description=desc,
            color=DISCORD_COLOR.get(game.current_color, discord.Color.purple())
        ))
        await self._update_board(channel, game)

    def _make_hand_embed(self, player: UnoPlayer, game: UnoGame) -> discord.Embed:
        top = game.top_card
        current_color = game.current_color
        combo_note = ""

        if game.pending_draw > 0 and game.current_player.user_id == player.user_id:
            sv = Value.DRAW2 if game.pending_draw_type == "draw2" else Value.WILD4
            playable = [c for c in player.hand if c.value == sv]
            not_playable = [c for c in player.hand if c.value != sv]
            tl = "➕2" if game.pending_draw_type == "draw2" else "🌈+4"
            combo_note = (
                f"\n\n⚠️ **BỊ DỒN BÀI: {game.pending_draw} LÁ!**\n"
                f"Bạn chỉ được phép chồng lá {tl} hoặc rút bài!"
            )
        else:
            playable = [c for c in player.hand if c.can_play_on(top, current_color)]
            not_playable = [c for c in player.hand if not c.can_play_on(top, current_color)]

        playable_str = "  ".join(c.display() for c in playable) if playable else "_Không có_"
        notplay_str = "  ".join(c.display() for c in not_playable) if not_playable else "_Không có_"
        is_my_turn = game.current_player.user_id == player.user_id
        turn_note = "▶️ **ĐẾN LƯỢT BẠN ĐÁNH!**" if is_my_turn else f"⏳ Đang chờ lượt của **{game.current_player.username}**"

        embed = make_embed(
            title=f"🃏 Bài của bạn ({player.username})",
            description=(
                f"{turn_note}{combo_note}\n\n"
                f"🎴 **Lá bài trên bàn:** {top.display()} — màu: {COLOR_EMOJI[current_color]}\n\n"
                f"✅ **Có thể đánh ({len(playable)} lá):**\n{playable_str}\n\n"
                f"❌ **Không thể đánh ({len(not_playable)} lá):**\n{notplay_str}\n\n"
                "💡 **Cách đánh bài:** Chọn lá bài từ dropdown menu bên dưới tin nhắn ẩn này."
            ),
            color=DISCORD_COLOR.get(current_color, discord.Color.purple()),
        )
        embed.set_footer(text=f"Tổng số: {len(player.hand)} lá bài | Chỉ mình bạn nhìn thấy tin nhắn này")
        return embed

    async def _update_board(self, channel, game: UnoGame):
        summary = game.get_board_summary()
        player_lines = []
        for p in summary["players"]:
            ind = "▶️" if p["is_current"] else "   "
            uno = " 🔔 **UNO!**" if p["uno"] else ""
            player_lines.append(f"{ind} {p['username']} — `{p['card_count']}` lá{uno}")

        combo_warn = ""
        if game.pending_draw > 0:
            tl = "➕2" if game.pending_draw_type == "draw2" else "🌈+4"
            combo_warn = (
                f"\n\n⚠️ **COMBO ĐANG DỒN: {game.pending_draw} LÁ!**\n"
                f"👉 **{game.current_player.username}** phải chồng lá {tl} hoặc bấm **📥 Rút Bài**!"
            )

        embed = make_embed(
            title=f"🃏 Bàn Chơi UNO — Lượt của {summary['current_player']}",
            description=(
                f"🎴 **Lá Trên Bàn:** {summary['top_card']}\n"
                f"🎨 **Màu Hiện Tại:** {COLOR_EMOJI[summary['current_color']]} {COLOR_LABEL.get(summary['current_color'], '')}\n"
                f"🔄 **Chiều Chơi:** {summary['direction']}\n"
                f"🗂️ **Bài Trong Bộ:** `{summary['deck_count']}` lá còn lại"
                f"{combo_warn}\n\n"
                "**👥 Người Chơi:**\n" + "\n".join(player_lines) + "\n\n"
                f"⏳ **{summary['current_player']}** có `{TURN_TIMEOUT}` giây để đi bài!"
            ),
            color=DISCORD_COLOR.get(summary["current_color"], discord.Color.purple()),
        )

        file = None
        top_card = game.top_card
        img_path = top_card.image_path()
        if img_path and img_path.exists():
            file = discord.File(img_path, filename="top_card.png")
            embed.set_thumbnail(url="attachment://top_card.png")

        view = BoardView(game, self)

        with suppress(discord.HTTPException):
            if game.board_msg_id:
                try:
                    old = await channel.fetch_message(game.board_msg_id)
                    await old.delete()
                except Exception:
                    pass
            msg = await channel.send(embed=embed, file=file, view=view)
            game.board_msg_id = msg.id

    async def _prompt_color(self, ctx: commands.Context | discord.Interaction, player: UnoPlayer) -> Optional[Color]:
        view = ColorPickView(player.user_id, timeout=15.0)
        # Hỗ trợ cả Context và Interaction
        if isinstance(ctx, discord.Interaction):
            await ctx.followup.send("🌈 **Chọn màu mới cho bộ bài:**", view=view, ephemeral=True)
        else:
            msg = await ctx.send("🌈 **Chọn màu mới cho bộ bài:**", view=view, ephemeral=True)
            
        timed_out = await view.wait()
        return None if timed_out else view.chosen_color

    async def _broadcast_card_played_no_ctx(
        self, channel, game: UnoGame,
        player: UnoPlayer, card: UnoCard, effect: dict, chosen_color: Optional[Color],
    ):
        parts = [f"**{player.username}** đã đánh lá **{card.display()}**"]
        if effect.get("reversed"):
            parts.append("🔄 **REVERSE!** Đảo chiều vòng chơi!")
        if effect.get("skipped"):
            parts.append("⏩ **SKIP!** Bỏ qua lượt tiếp theo!")
        if effect.get("draw") and card.value == Value.DRAW2:
            total = effect["draw"]
            nxt = game.current_player.username
            if effect.get("stacking"):
                parts.append(f"➕2 **COMBO!** Tổng đang dồn: **{total} lá**! **{nxt}** phải chồng hoặc rút!")
            else:
                parts.append(f"➕2 **{nxt}** phải rút {total} lá hoặc chồng +2!")
        if card.value == Value.WILD4:
            total = effect["draw"]
            nxt = game.current_player.username
            clr = COLOR_EMOJI[game.current_color]
            clr_name = COLOR_LABEL.get(game.current_color, "")
            parts.append(f"🌈+4 Màu mới đổi sang: {clr} **{clr_name}**")
            if effect.get("stacking"):
                parts.append(f"💥 **COMBO!** Tổng đang dồn: **{total} lá**! **{nxt}** phải chồng hoặc rút!")
            else:
                parts.append(f"😱 **{nxt}** phải rút {total} lá hoặc chồng +4!")
        elif card.value == Value.WILD:
            clr = COLOR_EMOJI[game.current_color]
            clr_name = COLOR_LABEL.get(game.current_color, "")
            parts.append(f"🌈 Màu mới đổi sang: {clr} **{clr_name}**")

        embed = make_embed(
            title="🎴 Bài Đã Được Đánh",
            description="\n".join(parts),
            color=DISCORD_COLOR.get(game.current_color, discord.Color.purple()),
        )

        file = None
        img_path = card.image_path()
        if img_path and img_path.exists():
            file = discord.File(img_path, filename="played_card.png")
            embed.set_thumbnail(url="attachment://played_card.png")

        await channel.send(embed=embed, file=file)

    async def _handle_win_no_ctx(self, channel, game: UnoGame, winner: UnoPlayer):
        rewards = game.calculate_rewards()
        for uid, delta in rewards.items():
            if delta > 0:
                self.economy.add_money(uid, delta + game.bet)
        log_wallet_change(
            logger, event="uno_win", user_id=winner.user_id,
            money_delta=rewards.get(winner.user_id, 0),
            players=len(game.players), bet=game.bet,
        )
        result_lines = []
        for p in game.players:
            delta = rewards.get(p.user_id, 0)
            icon = "🥇 [THẮNG]" if p.user_id == winner.user_id else "😢 [THUA]"
            sign = f"+{delta:,}" if delta > 0 else f"{delta:,}"
            result_lines.append(f"{icon} **{p.username}**: `{sign} VND`")
        losers = [
            f"**{p.username}**: {len(p.hand)} lá bài"
            for p in game.players if p.user_id != winner.user_id
        ]
        await channel.send(embed=make_embed(
            title=f"🏆 UNO! {winner.username} ĐÃ CHIẾN THẮNG! 🎉",
            description=(
                "**📊 Kết Quả:**\n" + "\n".join(result_lines) + "\n\n"
                f"⏱️ Tổng số lượt chơi: `{game.turn_count}`\n"
                + ("**🃏 Bài còn lại của đối thủ:**\n" + "\n".join(losers) if losers else "")
            ),
            color=discord.Color.gold(),
        ))
        self.active_games.pop(channel.id, None)

    async def _start_uno_timer(self, game: UnoGame, target_id: int, channel):
        await asyncio.sleep(UNO_CALL_TIMEOUT)
        if game.uno_pending_user_id == target_id and not game.uno_safe:
            game.uno_pending_user_id = None
            player = game.get_player(target_id)
            if player:
                game.draw_cards(player, 2)
                await channel.send(embed=make_embed(
                    title="⏰ Hết Giờ Hô UNO!",
                    description=f"**{player.username}** đã không hô UNO kịp thời!\n😤 Bị tự động phạt rút **2 lá**!",
                    color=discord.Color.red(),
                ))
                await self._update_board(channel, game)

    # --------------------------------------------------------------------------
    #  Card code parser
    # --------------------------------------------------------------------------

    def _parse_card_code(self, code: str, hand: list) -> Optional[UnoCard]:
        code = code.strip().upper()
        if code in ("WD4", "W+4", "WILD4", "WILDDRAW4"):
            return next((c for c in hand if c.value == Value.WILD4), None)
        if code in ("W", "WILD"):
            return next((c for c in hand if c.value == Value.WILD), None)
        color_map = {"R": Color.RED, "Y": Color.YELLOW, "G": Color.GREEN, "B": Color.BLUE}
        if not code or code[0] not in color_map:
            return None
        color = color_map[code[0]]
        value_map = {
            "S": Value.SKIP, "SKIP": Value.SKIP,
            "RV": Value.REVERSE, "REV": Value.REVERSE, "REVERSE": Value.REVERSE,
            "D2": Value.DRAW2, "+2": Value.DRAW2, "DRAW2": Value.DRAW2,
            "0": Value.ZERO, "1": Value.ONE, "2": Value.TWO, "3": Value.THREE,
            "4": Value.FOUR, "5": Value.FIVE, "6": Value.SIX,
            "7": Value.SEVEN, "8": Value.EIGHT, "9": Value.NINE,
        }
        v = value_map.get(code[1:])
        if v is None:
            return None
        target = UnoCard(color, v)
        return next((c for c in hand if c == target), None)

    def _card_to_code(self, card: UnoCard) -> str:
        cc = {"red": "R", "yellow": "Y", "green": "G", "blue": "B"}
        vc = {
            Value.SKIP: "S", Value.REVERSE: "RV", Value.DRAW2: "D2",
            Value.WILD: "W", Value.WILD4: "WD4",
        }
        if card.value in vc:
            if card.color == Color.WILD:
                return vc[card.value]
            return f"{cc.get(card.color.value, '?')}{vc[card.value]}"
        return f"{cc.get(card.color.value, '?')}{card.value.value}"

    @uno.error
    async def uno_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send("❌ Kênh này hiện đã có phòng chơi UNO rồi!", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("❌ Thiếu tiền cược! Hãy gõ: `uno create <tiền_cược>`.", delete_after=8)
        else:
            logger.error(f"UNO error: {error}", exc_info=True)


async def setup(client: commands.Bot):
    await client.add_cog(Uno(client))
