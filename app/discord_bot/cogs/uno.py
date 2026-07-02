# coding: utf-8
"""
UNO Discord Cog - with Combo/Stacking Rule
Khi bi danh +2 hoac +4, co the chong la tuong ung de cong don.
Nguoi khong chong duoc phai rut tong so la da don.
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
#  Views
# ==============================================================================

class LobbyView(discord.ui.View):
    def __init__(self, game: UnoGame, cog: "Uno"):
        super().__init__(timeout=90.0)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="Tham Gia", style=discord.ButtonStyle.success, custom_id="uno_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        balance = self.cog.economy.get_entry(user.id)[1]
        if balance < self.game.bet:
            await interaction.response.send_message(
                f"Khong du tien! Can {self.game.bet:,} VND.", ephemeral=True
            )
            return
        added = self.game.add_player(user.id, user.display_name)
        if not added:
            await interaction.response.send_message(
                "Ban da trong phong hoac phong da day!", ephemeral=True
            )
            return
        self.cog.economy.add_money(user.id, -self.game.bet)
        await interaction.response.send_message(
            f"Da tham gia! Tru {self.game.bet:,} VND coc.", ephemeral=True
        )
        await self.cog._update_lobby_embed(interaction.message)

    @discord.ui.button(label="Bat Dau", style=discord.ButtonStyle.primary, custom_id="uno_start")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("Chi chu phong moi duoc bat dau!", ephemeral=True)
            return
        if len(self.game.players) < 2:
            await interaction.response.send_message("Can it nhat 2 nguoi choi!", ephemeral=True)
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
            (Color.RED,    "Do",         discord.ButtonStyle.danger),
            (Color.YELLOW, "Vang",       discord.ButtonStyle.secondary),
            (Color.GREEN,  "Xanh La",    discord.ButtonStyle.success),
            (Color.BLUE,   "Xanh Duong", discord.ButtonStyle.primary),
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
            await interaction.response.send_message("Khong phai luot ban!", ephemeral=True)
            return False
        return True


class UnoCallView(discord.ui.View):
    def __init__(self, target_id: int, timeout: float = UNO_CALL_TIMEOUT):
        super().__init__(timeout=timeout)
        self.target_id = target_id
        self.accuser_id: Optional[int] = None

    @discord.ui.button(label="To Cao!", style=discord.ButtonStyle.danger, custom_id="uno_accuse")
    async def accuse_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id == self.target_id:
            await interaction.response.send_message("Khong the to cao chinh minh!", ephemeral=True)
            return
        self.accuser_id = interaction.user.id
        self.stop()
        await interaction.response.defer()


# ==============================================================================
#  Cog
# ==============================================================================

class Uno(commands.Cog, name="UNO"):
    """Tro choi UNO nhieu nguoi voi ephemeral messages va luat combo."""

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
        brief="Choi UNO nhieu nguoi",
    )
    async def uno(self, ctx: commands.Context):
        embed = make_embed(
            title="UNO",
            description=(
                "**Lenh:**\n"
                "`uno create <cuoc>` - Tao phong\n"
                "`uno join`          - Tham gia\n"
                "`uno hand`          - Xem bai (chi ban thay)\n"
                "`uno play <ma>`     - Danh bai (R7, BD2, WD4...)\n"
                "`uno draw`          - Rut bai / chiu phat combo\n"
                "`uno uno`           - Ho UNO!\n"
                "`uno leave`         - Roi phong\n\n"
                "**Ma bai:** R=Do, Y=Vang, G=XanhLa, B=XanhDuong\n"
                "S=Skip, RV=Reverse, D2=+2, W=Wild, WD4=Wild+4\n\n"
                "**Luat Combo:**\n"
                "Bi danh +2 -> phai chong +2 hoac rut tong so la\n"
                "Bi danh +4 -> phai chong +4 hoac rut tong so la"
            ),
            color=discord.Color.purple(),
        )
        await ctx.send(embed=embed)

    @uno.command(name="create", brief="Tao phong UNO")
    @commands.max_concurrency(1, per=commands.BucketType.channel, wait=False)
    async def uno_create(self, ctx: commands.Context, bet: int = 50_000):
        if ctx.channel.id in self.active_games:
            await ctx.send("Kenh nay da co phong UNO!", delete_after=5)
            return
        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
        except Exception as e:
            await ctx.send(str(e), delete_after=8)
            return
        self.economy.add_money(ctx.author.id, -bet)
        game = UnoGame(channel_id=ctx.channel.id, host_id=ctx.author.id, bet=bet)
        game.add_player(ctx.author.id, ctx.author.display_name)
        self.active_games[ctx.channel.id] = game
        view = LobbyView(game, self)
        msg = await ctx.send(embed=self._make_lobby_embed(game), view=view)
        game.lobby_msg_id = msg.id
        asyncio.create_task(self._lobby_timeout(ctx.channel.id, msg, 90))

    @uno.command(name="join", brief="Tham gia phong UNO")
    async def uno_join(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.LOBBY:
            await ctx.send("Khong co phong UNO dang cho!", delete_after=5)
            return
        if self.economy.get_entry(ctx.author.id)[1] < game.bet:
            await ctx.send(f"Khong du tien! Can {game.bet:,} VND.", delete_after=5)
            return
        if not game.add_player(ctx.author.id, ctx.author.display_name):
            await ctx.send("Ban da trong phong hoac phong day!", delete_after=5)
            return
        self.economy.add_money(ctx.author.id, -game.bet)
        await ctx.send(f"{ctx.author.display_name} da tham gia UNO!", delete_after=5)

    @uno.command(name="hand", aliases=["bai"], brief="Xem bai (ephemeral)")
    async def uno_hand(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            await ctx.send("Khong co game UNO dang chay!", delete_after=5)
            return
        player = game.get_player(ctx.author.id)
        if not player:
            await ctx.send("Ban khong trong game nay!", delete_after=5)
            return
        await ctx.send(embed=self._make_hand_embed(player, game), ephemeral=True)

    @uno.command(name="play", aliases=["p"], brief="Danh bai")
    async def uno_play(self, ctx: commands.Context, card_code: str = ""):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            await ctx.send("Khong co game UNO dang chay!", delete_after=5)
            return
        player = game.get_player(ctx.author.id)
        if not player:
            await ctx.send("Ban khong trong game nay!", delete_after=5)
            return
        if game.current_player.user_id != ctx.author.id:
            await ctx.send("Chua den luot ban!", delete_after=5, ephemeral=True)
            return

        card = self._parse_card_code(card_code.upper(), player.hand)
        if card is None:
            await ctx.send(
                f"Ma bai '{card_code}' khong hop le hoac ban khong co la nay!\n"
                "Dung `uno hand` de xem bai.",
                ephemeral=True, delete_after=10,
            )
            return

        # Kiem tra luat combo
        is_stacking = False
        if game.pending_draw > 0:
            type_label = "+2" if game.pending_draw_type == "draw2" else "+4"
            can_stack = (
                (game.pending_draw_type == "draw2" and card.value == Value.DRAW2) or
                (game.pending_draw_type == "wild4" and card.value == Value.WILD4)
            )
            if not can_stack:
                await ctx.send(
                    f"Dang bi don **{game.pending_draw} la**!\n"
                    f"Phai danh {type_label} de chong, hoac `uno draw` de rut "
                    f"**{game.pending_draw} la**.",
                    ephemeral=True, delete_after=12,
                )
                return
            is_stacking = True

        # Chon mau Wild
        chosen_color = None
        if card.value in {Value.WILD, Value.WILD4}:
            chosen_color = await self._prompt_color(ctx, player)
            if chosen_color is None:
                await ctx.send("Het gio chon mau - luot bi bo qua.", delete_after=5)
                return

        success, msg = game.play_card(player, card, chosen_color, stacking=is_stacking)
        if not success:
            await ctx.send(msg, ephemeral=True, delete_after=10)
            return

        await ctx.message.delete(delay=1)

        if msg == "WIN":
            await self._handle_win(ctx, game, player)
            return

        effect = game.apply_card_effect(card)
        await self._broadcast_card_played(ctx, game, player, card, effect, chosen_color)
        await self._update_board(ctx.channel, game)
        if game.uno_pending_user_id:
            await self._handle_uno_call(ctx.channel, game)

    @uno.command(name="draw", aliases=["rut"], brief="Rut bai / chiu phat combo")
    async def uno_draw(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            await ctx.send("Khong co game UNO dang chay!", delete_after=5)
            return
        player = game.get_player(ctx.author.id)
        if not player:
            await ctx.send("Ban khong trong game nay!", delete_after=5)
            return
        if game.current_player.user_id != ctx.author.id:
            await ctx.send("Chua den luot ban!", delete_after=5)
            return

        # Chiu phat combo: rut tat ca la dang don
        if game.pending_draw > 0:
            count = game.pending_draw
            type_label = "+2" if game.pending_draw_type == "draw2" else "+4"
            game.resolve_pending_draw(player)
            game.advance_turn()
            await ctx.send(embed=make_embed(
                title=f"{ctx.author.display_name} chiu phat combo!",
                description=(
                    f"Khong co la {type_label} de chong!\n"
                    f"Rut **{count} la** va mat luot."
                ),
                color=discord.Color.red(),
            ))
            await self._update_board(ctx.channel, game)
            if game.uno_pending_user_id:
                await self._handle_uno_call(ctx.channel, game)
            return

        # Rut 1 la binh thuong
        drawn = game.draw_cards(player, 1)
        if not drawn:
            await ctx.send("Bo bai da het!", delete_after=5)
            return
        card = drawn[0]
        can_play = card.can_play_on(game.top_card, game.current_color)
        await ctx.send(
            f"Rut duoc: **{card.display()}**\n" + (
                f"Co the danh! Dung `uno play {self._card_to_code(card)}`"
                if can_play else "Khong the danh. Luot ket thuc."
            ),
            ephemeral=True,
        )
        if not can_play:
            game.advance_turn()
            await self._update_board(ctx.channel, game)

    @uno.command(name="uno", brief="Ho UNO!")
    async def uno_call(self, ctx: commands.Context):
        game = self.active_games.get(ctx.channel.id)
        if not game or game.phase != GamePhase.PLAYING:
            return
        player = game.get_player(ctx.author.id)
        if not player:
            return
        success, msg = game.call_uno(ctx.author.id)
        if success:
            await ctx.send(f"**{ctx.author.display_name}**: **\"UNO!\"** !!!")
        else:
            await ctx.send(msg, ephemeral=True, delete_after=5)

    @uno.command(name="leave", brief="Roi game UNO")
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
                f"{ctx.author.display_name} da roi phong. Hoan {game.bet:,} VND.",
                delete_after=8,
            )
            if ctx.author.id == game.host_id and game.players:
                game.host_id = game.players[0].user_id
            elif not game.players:
                self.active_games.pop(ctx.channel.id, None)
        else:
            await ctx.send("Khong the roi khi game dang chay!", delete_after=8)

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
                    title="Phong UNO da dong",
                    description="Khong du nguoi trong 90 giay. Tien coc da hoan.",
                    color=discord.Color.red(),
                ), view=None)

    def _make_lobby_embed(self, game: UnoGame) -> discord.Embed:
        lines = "\n".join(
            f"[Host] {p.username}" if p.user_id == game.host_id else f"[Player] {p.username}"
            for p in game.players
        )
        return make_embed(
            title="PHONG UNO MOI",
            description=(
                f"Coc: {game.bet:,} VND/nguoi\n"
                f"Nguoi choi ({len(game.players)}/8):\n{lines}\n\n"
                "Phong tu dong sau 90 giay"
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
            f"{len(game.players)} nguoi choi | Coc: {game.bet:,} VND/nguoi\n"
            f"La mo dau: **{game.top_card.display()}**\n\n"
            "Dung `uno hand` de xem bai cua ban!"
        )
        if game.pending_draw > 0:
            tl = "+2" if game.pending_draw_type == "draw2" else "+4"
            desc += (
                f"\n\nCHU Y: La mo dau gay ra **{game.pending_draw} la combo**! "
                f"{game.current_player.username} phai chong {tl} hoac rut!"
            )
        await channel.send(embed=make_embed(
            title="UNO BAT DAU!",
            description=desc,
            color=DISCORD_COLOR.get(game.current_color, discord.Color.purple()),
        ))
        for p in game.players:
            await self._send_hand_to_player(channel, p, game)
        await self._update_board(channel, game)

    async def _send_hand_to_player(self, channel, player: UnoPlayer, game: UnoGame):
        embed = self._make_hand_embed(player, game)
        try:
            user = await self.client.fetch_user(player.user_id)
            await user.send(embed=embed)
        except (discord.Forbidden, discord.HTTPException):
            with suppress(discord.HTTPException):
                await channel.send(
                    f"<@{player.user_id}> DM bi chan! Dung `uno hand` de xem bai.",
                    delete_after=10,
                )

    def _make_hand_embed(self, player: UnoPlayer, game: UnoGame) -> discord.Embed:
        top = game.top_card
        current_color = game.current_color
        combo_note = ""

        # Neu dang bi don combo, chi hien thi la chong duoc
        if game.pending_draw > 0 and game.current_player.user_id == player.user_id:
            sv = Value.DRAW2 if game.pending_draw_type == "draw2" else Value.WILD4
            playable = [c for c in player.hand if c.value == sv]
            not_playable = [c for c in player.hand if c.value != sv]
            tl = "+2" if game.pending_draw_type == "draw2" else "+4"
            combo_note = (
                f"\n\nCOMBO DON: **{game.pending_draw} la**! "
                f"Chi co the chong {tl} hoac `uno draw`!"
            )
        else:
            playable = [c for c in player.hand if c.can_play_on(top, current_color)]
            not_playable = [c for c in player.hand if not c.can_play_on(top, current_color)]

        playable_str = "  ".join(c.display() for c in playable) if playable else "_Khong co_"
        notplay_str = "  ".join(c.display() for c in not_playable) if not_playable else "_Khong co_"
        is_my_turn = game.current_player.user_id == player.user_id
        turn_note = "DEN LUOT BAN!" if is_my_turn else f"Cho luot {game.current_player.username}"

        embed = make_embed(
            title=f"Bai Cua {player.username}",
            description=(
                f"{turn_note}{combo_note}\n\n"
                f"La tren ban: {top.display()} - mau {COLOR_EMOJI[current_color]}\n\n"
                f"Co the danh ({len(playable)} la):\n{playable_str}\n\n"
                f"Khong the danh ({len(not_playable)} la):\n{notplay_str}\n\n"
                "Dung `uno play` de danh" + ("\nDung `uno draw` de rut" if not playable else "")
            ),
            color=DISCORD_COLOR.get(current_color, discord.Color.purple()),
        )
        embed.set_footer(text=f"Tong: {len(player.hand)} la  |  Chi ban thay")
        return embed

    async def _update_board(self, channel, game: UnoGame):
        summary = game.get_board_summary()
        player_lines = []
        for p in summary["players"]:
            ind = ">>>" if p["is_current"] else "   "
            uno = " [UNO!]" if p["uno"] else ""
            player_lines.append(f"{ind} {p['username']} - {p['card_count']} la{uno}")

        combo_warn = ""
        if game.pending_draw > 0:
            tl = "+2" if game.pending_draw_type == "draw2" else "+4"
            combo_warn = (
                f"\n\n*** COMBO DANG DON: {game.pending_draw} LA *** "
                f"{game.current_player.username} phai danh {tl} hoac rut!"
            )

        embed = make_embed(
            title=f"UNO - Luot cua {summary['current_player']}",
            description=(
                f"La Tren Ban: {summary['top_card']}\n"
                f"Mau: {COLOR_EMOJI[summary['current_color']]} "
                f"{COLOR_LABEL.get(summary['current_color'], '')}\n"
                f"Chieu: {summary['direction']}\n"
                f"Bo bai con: {summary['deck_count']} la"
                f"{combo_warn}\n\n"
                "Nguoi choi:\n" + "\n".join(player_lines) + "\n\n"
                f"<@{summary['current_player_id']}> co {TURN_TIMEOUT}s!\n"
                "Dung `uno play` hoac `uno draw`"
            ),
            color=DISCORD_COLOR.get(summary["current_color"], discord.Color.purple()),
        )

        with suppress(discord.HTTPException):
            if game.board_msg_id:
                try:
                    old = await channel.fetch_message(game.board_msg_id)
                    await old.delete()
                except Exception:
                    pass
            msg = await channel.send(embed=embed)
            game.board_msg_id = msg.id

    async def _prompt_color(self, ctx: commands.Context, player: UnoPlayer) -> Optional[Color]:
        view = ColorPickView(player.user_id, timeout=15.0)
        msg = await ctx.send("Chon mau moi:", view=view, ephemeral=True)
        timed_out = await view.wait()
        with suppress(discord.HTTPException):
            await msg.delete()
        return None if timed_out else view.chosen_color

    async def _broadcast_card_played(
        self, ctx: commands.Context, game: UnoGame,
        player: UnoPlayer, card: UnoCard, effect: dict, chosen_color: Optional[Color],
    ):
        parts = [f"**{player.username}** danh **{card.display()}**"]
        if effect.get("reversed"):
            parts.append("REVERSE! Dao chieu!")
        if effect.get("skipped"):
            parts.append("SKIP! Bo qua luot!")
        if effect.get("draw") and card.value == Value.DRAW2:
            total = effect["draw"]
            nxt = game.current_player.username
            if effect.get("stacking"):
                parts.append(f"+2 COMBO! Tong: **{total} la**! {nxt} phai chong hoac rut!")
            else:
                parts.append(f"+2 **{nxt}** phai rut {total} la hoac chong +2!")
        if card.value == Value.WILD4:
            total = effect["draw"]
            nxt = game.current_player.username
            clr = COLOR_EMOJI[game.current_color]
            clr_name = COLOR_LABEL.get(game.current_color, "")
            parts.append(f"Wild+4 Mau moi: {clr} **{clr_name}**")
            if effect.get("stacking"):
                parts.append(f"COMBO! Tong: **{total} la**! {nxt} phai chong hoac rut!")
            else:
                parts.append(f"**{nxt}** phai rut {total} la hoac chong +4!")
        elif card.value == Value.WILD:
            clr = COLOR_EMOJI[game.current_color]
            clr_name = COLOR_LABEL.get(game.current_color, "")
            parts.append(f"Wild Mau moi: {clr} **{clr_name}**")
        await ctx.send(embed=make_embed(
            title="Bai Duoc Danh",
            description="\n".join(parts),
            color=DISCORD_COLOR.get(game.current_color, discord.Color.purple()),
        ))

    async def _handle_uno_call(self, channel, game: UnoGame):
        target_id = game.uno_pending_user_id
        if not target_id:
            return
        target = game.get_player(target_id)
        if not target:
            return
        view = UnoCallView(target_id=target_id, timeout=UNO_CALL_TIMEOUT)
        msg = await channel.send(embed=make_embed(
            title=f"{target.username} con 1 LA!",
            description=(
                f"**{target.username}** co {UNO_CALL_TIMEOUT}s de ho `uno uno`!\n"
                "Nguoi khac co the To Cao neu ho khong ho kip!"
            ),
            color=discord.Color.gold(),
        ), view=view)
        await view.wait()
        with suppress(discord.HTTPException):
            await msg.delete()
        if view.accuser_id:
            result, count = game.accuse_uno(view.accuser_id, target_id)
            accuser = game.get_player(view.accuser_id)
            aname = accuser.username if accuser else "Ai do"
            if result == "success":
                await channel.send(embed=make_embed(
                    title="To Cao Thanh Cong!",
                    description=f"{target.username} quen ho UNO!\n**{target.username}** bi phat rut **2 la**!",
                    color=discord.Color.red(),
                ))
            elif result == "fail":
                await channel.send(embed=make_embed(
                    title="To Cao That Bai!",
                    description=f"{target.username} da ho UNO roi!\n**{aname}** bi phat rut **1 la**!",
                    color=discord.Color.orange(),
                ))

    async def _handle_win(self, ctx: commands.Context, game: UnoGame, winner: UnoPlayer):
        rewards = game.calculate_rewards()
        for uid, delta in rewards.items():
            if delta > 0:
                self.economy.add_money(uid, delta + game.bet)
        log_wallet_change(
            logger, event="uno_win", user_id=winner.user_id,
            money_delta=rewards.get(winner.user_id, 0), ctx=ctx,
            players=len(game.players), bet=game.bet,
        )
        result_lines = []
        for p in game.players:
            delta = rewards.get(p.user_id, 0)
            icon = "[WIN]" if p.user_id == winner.user_id else "[LOSE]"
            sign = f"+{delta:,}" if delta > 0 else f"{delta:,}"
            result_lines.append(f"{icon} **{p.username}**: `{sign} VND`")
        losers = [
            f"**{p.username}**: {len(p.hand)} la"
            for p in game.players if p.user_id != winner.user_id
        ]
        await ctx.send(embed=make_embed(
            title=f"UNO! {winner.username} CHIEN THANG!",
            description=(
                "**Ket Qua:**\n" + "\n".join(result_lines) + "\n\n"
                f"Tong luot: `{game.turn_count}`\n"
                + ("**Bai con lai:**\n" + "\n".join(losers) if losers else "")
            ),
            color=discord.Color.gold(),
        ))
        self.active_games.pop(ctx.channel.id, None)

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

    # --------------------------------------------------------------------------
    #  Error handler
    # --------------------------------------------------------------------------

    @uno.error
    async def uno_error(self, ctx: commands.Context, error):
        if isinstance(error, commands.MaxConcurrencyReached):
            await ctx.send("Kenh nay da co phong UNO!", delete_after=8)
        elif isinstance(error, commands.MissingRequiredArgument):
            await ctx.send("Dung `uno create <tien_cuoc>`.", delete_after=8)
        else:
            logger.error(f"UNO error: {error}", exc_info=True)


async def setup(client: commands.Bot):
    await client.add_cog(Uno(client))
