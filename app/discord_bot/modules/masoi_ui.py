"""Non-VIP Ma Sói interaction views and bounded replay rendering."""
from __future__ import annotations
import logging
import time
from typing import Dict, Optional
import discord
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.masoi_engine import (
    ActionIntent, ActionKind, Faction, GamePhase, MasoiGame, Role, RankFaction, ReplayLog,
)
from app.discord_bot.modules.masoi_presentation import ui_lock, remaining_night_seconds, select_badge
logger = logging.getLogger(__name__)

class NightActionView(discord.ui.View):
    """Buttons are bound to one actor, one night and one shared deadline."""
    def __init__(self, game: MasoiGame, actor_id: int):
        super().__init__(timeout=None if game.phase == GamePhase.NIGHT_PREPARE else max(0.1, game.night_deadline - time.monotonic()))
        game.night_views.append(self)
        self.game = game
        self.actor_id = actor_id
        self.night = game.night_count

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.actor_id:
            await interaction.response.send_message("❌ Đây không phải lượt của bạn.", ephemeral=True)
            return False
        if self.game.phase == GamePhase.NIGHT_PREPARE and self.night == self.game.night_count:
            await interaction.response.send_message("⏳ Đang chuẩn bị DM. Hãy chờ thông báo mở đêm ở kênh chơi.", ephemeral=True)
            return False
        if self.is_finished() or not self.game.accepts_night_actions(self.night):
            await interaction.response.send_message("❌ Lượt đêm này đã hết hạn.", ephemeral=True)
            return False
        return True

    async def record_action(self, interaction, kind, targets=()):
        try:
            self.game.submit_night_action(ActionIntent(self.night, self.actor_id, kind, tuple(targets)))
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return False
        return True


class NightGuardView(NightActionView):
    """View Ephemeral chọn mục tiêu bảo vệ cho Bảo Vệ."""
    def __init__(self, game: MasoiGame, guard_id: int):
        super().__init__(game, guard_id)
        self.game = game
        self.guard_id = guard_id
        self.selected_target_id: Optional[int] = None

        guard_p = game.players.get(guard_id)
        last_protected = guard_p.protected_last_night if guard_p else None

        options = []
        for p in game.get_alive_players():
            if p.user_id == last_protected:
                continue
            options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🛡️"))

        if options:
            self.select = discord.ui.Select(placeholder="🛡️ Chọn 1 người để bảo vệ...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận lựa chọn", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        if not await self.record_action(interaction, ActionKind.GUARD, (target_id,)):
            return
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Người đã chọn"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** bảo vệ **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightWolfView(NightActionView):
    """View Ephemeral cho từng Sói bỏ phiếu cắn."""
    def __init__(self, game: MasoiGame, wolf_id: int):
        super().__init__(game, wolf_id)
        self.game = game
        self.wolf_id = wolf_id
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if not p.is_wolf:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🎯"))

        if options:
            self.select = discord.ui.Select(placeholder="🎯 Chọn 1 người...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận lựa chọn", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        if not await self.record_action(interaction, ActionKind.WOLF_VOTE, (target_id,)):
            return
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** cắn **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

        if hasattr(self.game, "cog") and self.game.cog:
            await self.game.cog.update_witch_dm(self.game)


class NightSeerView(NightActionView):
    """View Ephemeral chọn người để soi phe cho Tiên Tri."""
    def __init__(self, game: MasoiGame, seer_id: int):
        super().__init__(game, seer_id)
        self.game = game
        self.seer_id = seer_id
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if p.user_id != seer_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🔮"))

        if options:
            self.select = discord.ui.Select(placeholder="🔮 Chọn 1 người để soi phe...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận lựa chọn", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        if not await self.record_action(interaction, ActionKind.SEER, (target_id,)):
            return
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"

        self.game.seer_dm_message = interaction.message
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** soi **{name}**\n⏳ Kết quả sẽ gửi sau khi đêm được xử lý.", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightHarlotView(NightActionView):
    """View Ephemeral chọn 1 người để phong tỏa kỹ năng cho Vũ Nữ."""
    def __init__(self, game: MasoiGame, harlot_id: int):
        super().__init__(game, harlot_id)
        self.game = game
        self.harlot_id = harlot_id
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if p.user_id != harlot_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="💃"))

        if options:
            self.select = discord.ui.Select(placeholder="💃 Chọn 1 người để 'thăm'...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận lựa chọn", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        if not await self.record_action(interaction, ActionKind.HARLOT, (target_id,)):
            return
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** 'thăm' **{name}** (chặn kỹ năng đêm)", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightInvestigatorView(NightActionView):
    """View Ephemeral chọn 2 người chơi để kiểm tra có Sói không cho Thám Tử."""
    def __init__(self, game: MasoiGame, inv_id: int):
        super().__init__(game, inv_id)
        self.game = game
        self.inv_id = inv_id

        options = []
        for p in game.get_alive_players():
            if p.user_id != inv_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="👁️"))

        if options:
            req_count = min(2, len(options))
            self.select = discord.ui.Select(
                placeholder=f"👁️ Chọn {req_count} người chơi để kiểm tra...",
                min_values=req_count,
                max_values=req_count,
                options=options[:25],
                row=0
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận kiểm tra", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        alive_others = [p for p in self.game.get_alive_players() if p.user_id != self.inv_id]
        req_count = min(2, len(alive_others))
        if not hasattr(self, "select") or not self.select.values or len(self.select.values) < req_count:
            await interaction.response.send_message(f"❌ Vui lòng chọn đủ {req_count} người từ danh sách trước!", ephemeral=True)
            return

        selected_ids = [int(v) for v in self.select.values]
        if not await self.record_action(interaction, ActionKind.INVESTIGATE, tuple(selected_ids[:2])):
            return
        self.game.night_investigator_dm_message = interaction.message
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận lựa chọn.**\n⏳ Kết quả sẽ gửi sau khi đêm được xử lý.", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightWolfSeerView(NightActionView):
    """View Ephemeral chọn người để soi vai trò chính xác cho Sói Tiên Tri."""
    def __init__(self, game: MasoiGame, wolf_seer_id: int):
        super().__init__(game, wolf_seer_id)
        self.game = game
        self.wolf_seer_id = wolf_seer_id
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if p.user_id != wolf_seer_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🔮"))

        if options:
            self.select = discord.ui.Select(placeholder="🐺🔮 Chọn 1 người để soi vai trò...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận lựa chọn", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        if not await self.record_action(interaction, ActionKind.WOLF_SEER, (target_id,)):
            return
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.game.night_wolf_seer_dm_message = interaction.message

        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** soi **{name}**\n⏳ Kết quả sẽ gửi sau khi đêm được xử lý.", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightSerialKillerView(NightActionView):
    """View Ephemeral chọn mục tiêu hạ gục cho Sát Thủ Hàng Loạt."""
    def __init__(self, game: MasoiGame, sk_id: int):
        super().__init__(game, sk_id)
        self.game = game
        self.sk_id = sk_id
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if p.user_id != sk_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🔪"))

        if options:
            self.select = discord.ui.Select(placeholder="🔪 Chọn 1 nạn nhân...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận hạ gục", style=discord.ButtonStyle.danger, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        if not await self.record_action(interaction, ActionKind.SERIAL_KILL, (target_id,)):
            return
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n🔪 **Đã ghi nhận:** nhắm hạ gục **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightWhiteWolfView(NightActionView):
    """View Ephemeral cho Sói Trắng bí mật cắn thêm 1 Sói (mỗi 2 đêm chẵn)."""
    def __init__(self, game: MasoiGame, ww_id: int):
        super().__init__(game, ww_id)
        self.game = game
        self.ww_id = ww_id
        self.selected_target_id: Optional[int] = None

        options = [
            discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🐺")
            for p in game.get_alive_wolves()
            if p.user_id != ww_id
        ]

        if options:
            self.select = discord.ui.Select(
                placeholder="🐺⭐ Chọn 1 Sói trong bầy để bí mật cắn...",
                options=options[:25],
                row=0
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận cắn", style=discord.ButtonStyle.danger, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

        btn_skip = discord.ui.Button(label="👌 Bỏ qua lần này", style=discord.ButtonStyle.secondary, row=1)
        btn_skip.callback = self.skip_callback
        self.add_item(btn_skip)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 Sói từ danh sách trước!", ephemeral=True)
            return

        if not await self.record_action(interaction, ActionKind.WHITE_WOLF, (self.selected_target_id,)):
            return
        target_p = self.game.players.get(self.selected_target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(name="\u200b", value=f"──────────────────────────────────────\n⭐ **Đã ghi nhận:** bí mật ra tay với Sói **{name}**", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)

    async def skip_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not await self.record_action(interaction, ActionKind.WHITE_WOLF, ()):
            return
        self.stop()
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(name="\u200b", value="──────────────────────────────────────\n👌 Bạn không dùng khả năng đặc biệt đêm nay.", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)


class NightPhantomWolfView(NightActionView):
    """View Ephemeral cho Sói Ảo Ảnh chọn 1 người dân để giả dạng."""
    def __init__(self, game: MasoiGame, phantom_id: int):
        super().__init__(game, phantom_id)
        self.game = game
        self.phantom_id = phantom_id
        self.selected_target_id: Optional[int] = None

        options = [
            discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="👻")
            for p in game.get_alive_players()
            if not p.is_wolf and p.user_id != phantom_id
        ]

        if options:
            self.select = discord.ui.Select(
                placeholder="👻 Chọn 1 người dân để giả dạng...",
                options=options[:25],
                row=0
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận giả dạng", style=discord.ButtonStyle.danger, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        phantom_p = self.game.players.get(self.phantom_id)
        if phantom_p and phantom_p.is_roleblocked:
            result_msg = "❌ **Kỹ năng bị phong tỏa đêm nay!** (Do bị Vũ Nữ ghé thăm)"
        else:
            if not await self.record_action(interaction, ActionKind.PHANTOM, (self.selected_target_id,)):
                return
            target_p = self.game.players.get(self.selected_target_id)
            name = target_p.display_name if target_p else "Mục tiêu"
            result_msg = f"👻 **Đã ghi nhận:** giả dạng **{name}** — Tiên Tri soi người này sẽ thấy 'SÓI'!"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(name="\u200b", value=f"──────────────────────────────────────\n{result_msg}", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)


class NightGirlView(NightActionView):
    """View Ephemeral cho Cô Bé nhìn trộm xem bầy Sói đang cắn ai."""
    def __init__(self, game: MasoiGame, girl_id: int):
        super().__init__(game, girl_id)
        self.game = game
        self.girl_id = girl_id

        btn_peek = discord.ui.Button(
            label="👀 Nhìn trộm (50% bị phát hiện = chết)",
            style=discord.ButtonStyle.danger,
            row=0
        )
        btn_peek.callback = self.peek_callback
        self.add_item(btn_peek)

        btn_no_peek = discord.ui.Button(
            label="🙈 Không nhìn (An toàn)",
            style=discord.ButtonStyle.secondary,
            row=0
        )
        btn_no_peek.callback = self.no_peek_callback
        self.add_item(btn_no_peek)

    async def peek_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not await self.record_action(interaction, ActionKind.GIRL, ()):
            return
        self.game.girl_dm_message = interaction.message
        self.stop()
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(
                name="\u200b",
                value="──────────────────────────────────────\n⏳ Đã ghi nhận. Kết quả sẽ gửi sau khi đêm được xử lý.",
                inline=False,
            )
        await interaction.response.edit_message(embed=embed, view=None)

    async def no_peek_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.stop()
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(name="\u200b", value="──────────────────────────────────────\n🙈 Bạn quyết định không nhìn trộm đêm nay. An toàn!", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)


class NightPiperView(NightActionView):
    """View Ephemeral cho Người Thổi Sáo chọn 2 người để mê hoặc."""
    def __init__(self, game: MasoiGame, piper_id: int):
        super().__init__(game, piper_id)
        self.game = game
        self.piper_id = piper_id

        options = []
        for p in game.get_alive_players():
            if p.user_id != piper_id:
                desc = "🎵 Đã bị mê hoặc" if p.piper_charmed else "Chưa bị mê hoặc"
                label = f"{p.display_name} {'(🎵)' if p.piper_charmed else ''}"
                options.append(discord.SelectOption(label=label[:25], value=str(p.user_id), description=desc, emoji="🎵"))

        if options:
            select_max = game.required_target_count(ActionKind.INVESTIGATE)
            self.select = discord.ui.Select(
                placeholder=f"🎵 Chọn {select_max} người để mê hoặc...",
                min_values=select_max,
                max_values=select_max,
                options=options[:25],
                row=0
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận mê hoặc", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not hasattr(self, "select") or not self.select.values:
            await interaction.response.send_message("❌ Vui lòng chọn người từ danh sách trước!", ephemeral=True)
            return

        piper_p = self.game.players.get(self.piper_id)
        if piper_p and piper_p.is_roleblocked:
            result_msg = "❌ **Kỹ năng bị phong tỏa đêm nay!** (Do bị Vũ Nữ ghé thăm)"
        else:
            targets = [int(v) for v in self.select.values]
            if not await self.record_action(interaction, ActionKind.PIPER, targets):
                return
            names = [self.game.players[t].display_name for t in targets if t in self.game.players]
            result_msg = f"🎵 **Đã ghi nhận lựa chọn mê hoặc:** {' & '.join(f'**{n}**' for n in names)}"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            embed.add_field(name="\u200b", value=f"──────────────────────────────────────\n{result_msg}", inline=False)
        await interaction.response.edit_message(embed=embed, view=None)


class MayorSuccessionView(discord.ui.View):
    """View Ephemeral cho Thị Trưởng qua đời chọn người kế nhiệm."""
    def __init__(self, game: MasoiGame, mayor_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.mayor_id = mayor_id
        self.deadline = time.monotonic() + game.settings.night_time
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if p.user_id != mayor_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🎩"))

        if options:
            self.select = discord.ui.Select(placeholder="🎩 Chọn 1 người kế nhiệm Thị Trưởng...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận truyền quyền", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        target = self.game.players.get(target_id)
        if (interaction.user.id != self.mayor_id or self.is_finished()
                or time.monotonic() >= self.deadline or self.game.phase == GamePhase.GAME_END
                or self.game.mayor_id != self.mayor_id or not target or not target.is_alive):
            await interaction.response.send_message("❌ Lượt truyền quyền không còn hợp lệ.", ephemeral=True)
            return
        self.game.mayor_id = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Người kế nhiệm"
        self.game.record_log("MAYOR_SUCCESSION", actor_id=self.mayor_id, target_id=target_id, result=f"Chỉ định Thị Trưởng kế nhiệm: {name}")
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n🎩 **Đã ghi nhận:** truyền chiếc mũ Thị Trưởng cho **{name}**!", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightCupidView(NightActionView):
    """View Ephemeral chọn 2 người làm Cặp Đôi Tình Nhân cho Thần Tình Yêu."""
    def __init__(self, game: MasoiGame, cupid_id: int):
        super().__init__(game, cupid_id)
        self.game = game
        self.cupid_id = cupid_id

        options = []
        for p in game.get_alive_players():
            options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="💘"))

        if options:
            self.select = discord.ui.Select(
                placeholder="💘 Chọn đúng 2 người làm Cặp Đôi...",
                min_values=min(2, len(options)),
                max_values=min(2, len(options)),
                options=options[:25],
                row=0
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận ghép đôi", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not hasattr(self, "select") or not self.select.values or len(self.select.values) < 2:
            await interaction.response.send_message("❌ Vui lòng chọn đúng 2 người từ danh sách trước!", ephemeral=True)
            return

        id1, id2 = int(self.select.values[0]), int(self.select.values[1])
        if not await self.record_action(interaction, ActionKind.CUPID, (id1, id2)):
            return
        self.game.night_cupid_dm_message = interaction.message

        self.stop()
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n💘 **Đã ghi nhận lựa chọn.**\n⏳ Kết quả sẽ gửi sau khi đêm được xử lý.", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightWitchView(NightActionView):
    """View Ephemeral cho Phù Thủy (Cứu & Độc)."""
    def __init__(self, game: MasoiGame, witch_id: int, victim_id: Optional[int]):
        super().__init__(game, witch_id)
        self.game = game
        self.witch_id = witch_id
        self.victim_id = victim_id

        witch_p = game.players.get(witch_id)
        has_save = witch_p and not witch_p.witch_save_used
        victim_p = game.players.get(victim_id) if victim_id else None
        victim_name = victim_p.display_name if victim_p else "Không ai"

        if victim_p and has_save:
            btn_save = discord.ui.Button(label=f"🧪 Cứu {victim_name}", style=discord.ButtonStyle.success, row=0)
            btn_save.callback = self.save_callback
            self.add_item(btn_save)

        btn_no_save = discord.ui.Button(label="👌 Không dùng bình cứu", style=discord.ButtonStyle.secondary, row=0)
        btn_no_save.callback = self.no_save_callback
        self.add_item(btn_no_save)

    async def save_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not await self.record_action(interaction, ActionKind.WITCH_SAVE, (self.victim_id,)):
            return
        victim_p = self.game.players.get(self.victim_id) if self.victim_id else None
        v_name = victim_p.display_name if victim_p else "nạn nhân"
        await self.show_poison_step(interaction, f"✅ **Đã ghi nhận:** CỨU **{v_name}**")

    async def no_save_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not await self.record_action(interaction, ActionKind.WITCH_SAVE, ()):
            return
        await self.show_poison_step(interaction, "👌 Bạn không dùng bình cứu đêm nay.")

    async def show_poison_step(self, interaction: discord.Interaction, prefix_msg: str):
        # Acknowledge before waiting for any in-flight wolf DM edit.
        await interaction.response.defer()
        async with ui_lock(self.game, "witch"):
            if not self.game.accepts_night_actions(self.night):
                self.stop()
                return
            witch_p = self.game.players.get(self.witch_id)
            self.stop()
            if not witch_p or witch_p.witch_poison_used:
                self.game.witch_view = None
                embed = discord.Embed(title="🧪 Phù Thủy", description=f"{prefix_msg}\nBạn đã hết bình độc.", color=discord.Color.gold())
                await interaction.message.edit(embed=embed, view=None)
                return
            embed_poison = discord.Embed(
                title=f"🌙 Đêm {self.night} — Lượt của Phù Thủy",
                description=f"Dùng **BÌNH ĐỘC**? Còn **{remaining_night_seconds(self.game)} giây** để quyết định.\n\n{prefix_msg}",
                color=discord.Color(0xE0A638),
            )
            view = NightWitchPoisonView(self.game, self.witch_id, prefix_msg)
            self.game.witch_view = view
            await interaction.message.edit(embed=embed_poison, view=view)


class NightWitchPoisonView(NightActionView):
    def __init__(self, game: MasoiGame, witch_id: int, prefix_msg: str):
        super().__init__(game, witch_id)
        self.game = game
        self.witch_id = witch_id
        self.prefix_msg = prefix_msg
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if p.user_id != witch_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="☠️"))

        if options:
            self.select = discord.ui.Select(placeholder="☠️ Chọn 1 người để hạ độc...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận lựa chọn", style=discord.ButtonStyle.danger, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

        btn_skip = discord.ui.Button(label="👌 Bỏ qua không dùng độc", style=discord.ButtonStyle.secondary, row=1)
        btn_skip.callback = self.skip_poison_callback
        self.add_item(btn_skip)

    async def select_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        if not await self.record_action(interaction, ActionKind.WITCH_POISON, (target_id,)):
            return
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n☠️ **Đã ghi nhận:** hạ độc **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    async def skip_poison_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not await self.record_action(interaction, ActionKind.WITCH_POISON, ()):
            return
        self.stop()
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n👌 Bạn không dùng bình độc đêm nay.", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightHunterView(discord.ui.View):
    """View Ephemeral cho Thợ Săn bắn 1 người khi chết."""
    def __init__(self, game: MasoiGame, hunter_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.hunter_id = hunter_id
        self.confirmed_target_id: Optional[int] = None
        self.deadline = time.monotonic() + game.settings.night_time
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            if p.user_id != hunter_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🏹"))

        if options:
            self.select = discord.ui.Select(placeholder="🏹 Chọn 1 người để bắn...", options=options[:25], row=0)
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận lựa chọn", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        target_p = self.game.players.get(target_id)
        if interaction.user.id != self.hunter_id or self.is_finished() or time.monotonic() >= self.deadline:
            await interaction.response.send_message("❌ Phát bắn không còn hợp lệ.", ephemeral=True)
            return
        try:
            self.game.resolve_hunter_shot(self.hunter_id, target_id)
            self.confirmed_target_id = target_id
        except ValueError as exc:
            await interaction.response.send_message(f"❌ {exc}", ephemeral=True)
            return

        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n🏹 **Đã ghi nhận:** kéo theo bắn gục **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


# ==============================================================================
#  Day Discussion & Voting Views
# ==============================================================================

class DayDiscussionView(discord.ui.View):
    """View ở kênh chính trong lúc thảo luận ban ngày."""
    def __init__(self, game: MasoiGame, cog: "Masoi", *, prepare: bool = False):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.day = game.day_count
        self.deadline = 0.0 if prepare else time.monotonic() + game.settings.discussion_time

    def open_actions(self):
        if self.game.phase == GamePhase.DAY_DISCUSSION and not self.is_finished():
            self.deadline = time.monotonic() + self.game.settings.discussion_time

    @discord.ui.button(label="Yêu cầu bỏ phiếu sớm (0)", style=discord.ButtonStyle.primary, emoji="⏩", custom_id="masoi_early_vote")
    async def early_vote_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if (self.is_finished() or self.game.phase != GamePhase.DAY_DISCUSSION
                or self.day != self.game.day_count or time.monotonic() >= self.deadline):
            await interaction.response.send_message("❌ Lượt ban ngày này đã hết hạn.", ephemeral=True)
            return
        user_id = interaction.user.id
        p = self.game.players.get(user_id)
        if not p or not p.is_alive:
            await interaction.response.send_message("❌ Chỉ người chơi còn sống mới được yêu cầu bỏ phiếu sớm!", ephemeral=True)
            return

        self.game.early_vote_requests.add(user_id)
        self.game.checkpoint()
        await interaction.response.defer()
        async with ui_lock(self.game, "discussion"):
            if self.is_finished() or self.game.phase != GamePhase.DAY_DISCUSSION or self.day != self.game.day_count:
                return
            alive_count = len(self.game.get_alive_players())
            req_count = len(self.game.early_vote_requests)
            button.label = f"Yêu cầu bỏ phiếu sớm ({req_count}/{alive_count})"
            await interaction.message.edit(view=self)
            if req_count >= (alive_count // 2 + 1):
                self.stop()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        logger.error("DayDiscussionView error on %s: %s", item, error, exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi. Vui lòng thử lại!", ephemeral=True)
        except Exception:
            pass


class DayVoteView(discord.ui.View):
    """View bỏ phiếu treo cổ ban ngày."""
    def __init__(self, game: MasoiGame, cog: "Masoi", *, prepare: bool = False):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.day = game.day_count
        self.deadline = 0.0 if prepare else time.monotonic() + game.settings.night_time

        options = [discord.SelectOption(label="Bỏ phiếu trắng (Không treo cổ ai)", value="white", emoji="🏳️")]
        for p in game.get_alive_players():
            options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="⚖️"))

        select = discord.ui.Select(placeholder="⚖️ Chọn người bạn nghi ngờ để bỏ phiếu...", options=options[:25], custom_id="masoi_vote_select")
        select.callback = self.vote_callback
        self.add_item(select)
        self.refresh_badges()

    def open_actions(self):
        if self.game.phase == GamePhase.DAY_VOTE and not self.is_finished():
            self.deadline = time.monotonic() + self.game.settings.night_time

    def refresh_badges(self):
        for option in self.children[0].options:
            if option.value != "white":
                option.emoji = select_badge(self.cog.player_badge(int(option.value), "⚖️"))

    async def vote_callback(self, interaction: discord.Interaction):
        if (self.is_finished() or self.game.phase != GamePhase.DAY_VOTE
                or self.day != self.game.day_count or time.monotonic() >= self.deadline):
            await interaction.response.send_message("❌ Lượt ban ngày này đã hết hạn.", ephemeral=True)
            return
        user_id = interaction.user.id
        p = self.game.players.get(user_id)
        if not p or not p.is_alive:
            await interaction.response.send_message("❌ Chỉ người chơi còn sống mới được bỏ phiếu!", ephemeral=True)
            return

        val = interaction.data["values"][0]
        if val == "white":
            self.game.day_votes[user_id] = None
            target_name = "Phiếu trắng"
        else:
            target_id = int(val)
            target = self.game.players.get(target_id)
            if not target or not target.is_alive:
                await interaction.response.send_message("❌ Mục tiêu không còn hợp lệ.", ephemeral=True)
                return
            self.game.day_votes[user_id] = target_id
            target_p = self.game.players.get(target_id)
            target_name = target_p.display_name if target_p else "Người chơi"

        self.game.checkpoint()
        await interaction.response.send_message(f"✅ Đã ghi nhận phiếu của bạn cho: **{target_name}**.", ephemeral=True)

        if self.game.settings.vote_display == "REALTIME":
            await self.cog.update_vote_embed(self.game, interaction.message)

        alive_count = len(self.game.get_alive_players())
        if len(self.game.day_votes) >= alive_count:
            self.stop()

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        logger.error("DayVoteView error on %s: %s", item, error, exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi khi ghi nhận phiếu. Vui lòng thử lại!", ephemeral=True)
        except Exception:
            pass


# ==============================================================================
#  End Game & Replay Views
# ==============================================================================

def format_replay_story_line(log: ReplayLog) -> str:
    """Chuyển đổi ReplayLog thành câu chuyện văn học / Nhật ký truyền cảm."""
    actor = f"**{log.actor_name}**" if log.actor_name else ""
    target = f"**{log.target_name}**" if log.target_name else ""
    event = log.event_type

    if event in ("WOLF_VOTE", "WOLF_KILL"):
        return f"🐺 **Bầy Sói** âm thầm cất bước trong đêm tối và nhắm nanh cắn {target}."
    elif event == "GUARD_PROTECT":
        return f"🛡️ **Bảo Vệ** xuất hiện kịp thời, chặn đòn tấn công trực tiếp vào {target}."
    elif event == "WITCH_SAVE":
        return f"🧪 **Phù Thủy** nhanh tay dùng **Bình Cứu** chặn đòn tấn công trực tiếp vào {target} (không hồi sinh)."
    elif event == "WITCH_POISON":
        return f"🧪 **Phù Thủy** mở hũ **Bình Độc**, hạ độc {target}; xem sự kiện qua đời để biết kết quả."
    elif event in ("SEER_ACTION", "SEER_INSPECT"):
        return f"🔮 **Tiên Tri** {actor} bói toán thi triển thần thư, soi {target}: {log.result}"
    elif event == "WOLF_SEER_INSPECT":
        return f"🐺🔮 **Sói Tiên Tri** {actor} âm thầm thấu thị, soi {target}: {log.result}"
    elif event == "CURSED_CONVERT":
        return f"🌕 **Kẻ Bị Nguyền** {target} bị cắn nhưng không chết — vết cắn phát tác biến thành **Sói Mới**!"
    elif event == "ELDER_SAVED":
        return f"👴 **Già Làng** {target} ngoan cường chống đỡ thành công đòn cắn thứ 1 của Bầy Sói!"
    elif event == "SK_IMMUNE":
        return f"🔪 **Sát Thủ** {target} với cơ thể thép đã đánh bật đòn tấn công của Bầy Sói!"
    elif event == "SERIAL_KILLER_KILL":
        return f"🔪 **Sát Thủ Hàng Loạt** {actor} vung dao tấn công {target}; chưa chắc mục tiêu đã chết."
    elif event == "WITCH_SAVE_SK":
        return f"🧪 **Phù Thủy** dùng **Bình Cứu** giải cứu {target} khỏi tay Sát Thủ!"
    elif event == "GUARD_PROTECT_SK":
        return f"🛡️ **Bảo Vệ** cứu sống {target} khỏi lưỡi dao tàn bạo của Sát Thủ!"
    elif event == "HARLOT_VISIT":
        return f"💃 **Vũ Nữ** {actor} ghé thăm {target}, phong tỏa toàn bộ kỹ năng đêm!"
    elif event == "WOLF_ROLEBLOCKED":
        return f"🔇 {actor} bị Vũ Nữ phong tỏa, đòn cắn đêm nay hoàn toàn bị vô hiệu!"
    elif event == "WHITE_WOLF_BITE":
        return f"🐺⭐ **Sói Trắng** {actor} nhắm cắn thêm đồng bọn {target}; xem kết quả qua đời."
    elif event == "GIRL_CAUGHT":
        return f"👧 **Cô Bé** {target} lỡ tay phát ra tiếng động khi nhìn trộm và bị Bầy Sói phát hiện hạ sát!"
    elif event == "PIPER_CHARM":
        return f"🎵 **Người Thổi Sáo** {actor} cất tiếng đàn mê hoặc {target or log.result}!"
    elif event == "LOVER_DEATH":
        return f"💘 **Bi kịch:** {target} u uất tự sát đi theo tình nhân vừa qua đời!"
    elif event == "RUSTY_KNIGHT_DYING":
        return f"⚔️ **Hiệp Sĩ Kiếm Gỉ** {target} ngã xuống, để lại lời nguyền giáng đòn 1 Sói vào đêm sau!"
    elif event == "RUSTY_KNIGHT_CURSE":
        return f"⚔️ Lời nguyền của **Hiệp Sĩ Kiếm Gỉ** giáng đòn hạ gục Sói {target}!"
    elif event == "WOLF_CUB_RAGE":
        return f"🐺🩸 **Sói Cuồng Sát** {actor or target} ngã xuống! Bầy Sói sục sôi cuồng nộ cắn 2 người đêm tiếp theo!"
    elif event == "APPRENTICE_PROMOTED":
        return f"🔮✨ **Tiên Tri Tập Sự** {actor} đứng lên kế thừa di chí, trở thành **Tiên Tri Mới**!"
    elif event in ("NIGHT_DEATH", "HUNTER_DEATH", "DAY_DEATH"):
        return f"💀 {target} đã qua đời."
    elif event == "MAYOR_SUCCESSION":
        return f"🎩 **Thị Trưởng** {actor} chỉ định {target} làm Thị Trưởng kế nhiệm!"
    elif event == "HUNTER_SHOOT":
        return f"🏹 **Thợ Săn** {actor} trước khi trút hơi thở cuối cùng đã giương nỏ bắn gục {target}!"
    elif event == "DAY_EXECUTION":
        return f"⚖️ **Dân Làng xử tử:** {target} bị dồn phiếu bầu và phải bước lên giàn treo cổ!"
    elif event == "SCAPEGOAT_EXECUTED":
        return f"🐐 **Hòa phiếu:** **Dê Tế Thần** {target} tự động bị kéo lên giàn treo gánh tội thay!"
    elif event == "NIGHT_EVENT":
        return f"🎴 **Thẻ Sự Kiện Đêm:** {log.result}"
    elif event == "SOLAR_ECLIPSE_SKIP":
        return f"☀️ **Nhật Thực Bóng Tối:** Ban ngày dân làng bị che mắt, không thể bỏ phiếu treo cổ!"
    elif event == "HOLY_LIGHT_SAVED":
        return f"🛡️ **Thánh Quang Bảo Hộ:** Hào quang thần thánh hóa giải đòn cắn của Bầy Sói cho {target}!"
    elif event == "BOSS_SHIELD_SAVED":
        return f"👑🐺 **Chúa Tể Sói** dùng Khiên Vương Giả hóa giải Bình Độc thành công!"
    elif event == "BOSS_DAMAGE":
        return f"👑🐺 **Chúa Tể Sói** bị giáng đòn tổn hại 1 Mạng! {log.result}"
    elif event == "BOSS_KILLED":
        return f"💥👑🐺 **Chúa Tể Sói** đã bị tiêu diệt hoàn toàn!"
    elif event == "VOTE_RESULT":
        return f"⚖️ **Bỏ phiếu ban ngày:** {log.result}."
    elif event in ("GIRL_PEEK", "INVESTIGATOR_CHECK"):
        return f"🔎 {actor}: {log.result}"
    elif event == "GAME_DRAW":
        return f"🤝 **Ván hòa:** {log.result}"
    elif event == "GAME_WIN":
        return f"🏆 **KẾT QUẢ CHUNG CUỘC:** {log.result}"
    else:
        a_str = f"**{log.actor_name}**: " if log.actor_name else ""
        t_str = f" -> **{log.target_name}**" if log.target_name else ""
        return f"• {a_str}{log.result}{t_str}"


class RankboardView(discord.ui.View):
    """Switch among the three independent rating ladders."""
    def __init__(self, cog: "Masoi"):
        super().__init__(timeout=180)
        self.cog = cog

    @discord.ui.button(label="Sói", emoji="🐺", style=discord.ButtonStyle.secondary)
    async def wolf_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_rankboard_embed(RankFaction.WOLF), view=self)

    @discord.ui.button(label="Solo", emoji="🃏", style=discord.ButtonStyle.secondary)
    async def solo_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_rankboard_embed(RankFaction.SOLO), view=self)

    @discord.ui.button(label="Dân", emoji="👥", style=discord.ButtonStyle.secondary)
    async def village_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(embed=self.cog.build_rankboard_embed(RankFaction.VILLAGER), view=self)


class GameEndView(discord.ui.View):
    """View ở embed kết thúc ván."""
    def __init__(self, game: MasoiGame, cog: "Masoi"):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="Nhật Ký Ván Đấu", style=discord.ButtonStyle.secondary, emoji="📜", custom_id="masoi_replay")
    async def replay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ReplayView(self.game)
        embed = view.get_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Bảng Xếp Hạng", style=discord.ButtonStyle.primary, emoji="🏆", custom_id="masoi_rankboard")
    async def rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.build_rankboard_embed()
        await interaction.response.send_message(embed=embed, view=RankboardView(self.cog), ephemeral=True)


class ReplayView(discord.ui.View):
    """View phân trang xem lại nhật ký diễn biến Storyline dạng Dòng Thời Gian."""
    def __init__(self, game: MasoiGame):
        super().__init__(timeout=180)
        self.game = game
        self.current_page = 0
        self.pages = self.build_pages()
        self.update_buttons()

    def build_pages(self) -> list[dict]:
        pages = []
        
        # Gom nhóm logs theo Đêm và Ngày
        grouped: Dict[str, list] = {}
        for log in self.game.replay_logs:
            period = getattr(log, "period", None)
            is_day = period == "DAY" if period else log.phase in {
                GamePhase.DAY_ANNOUNCE.value, GamePhase.DAY_DISCUSSION.value,
                GamePhase.DAY_VOTE.value, GamePhase.DAY_RESOLVE.value,
            }
            number = log.day if is_day else (getattr(log, "night", 0) or log.day)
            key = f"Ngày {number}" if is_day else f"Đêm {number}"
            grouped.setdefault(key, []).append(log)

        # ── TRANG 0: TỔNG QUAN DÒNG THỜI GIAN (STORYLINE RECAP) ──
        overview_lines = [
            f"📜 **NHẬT KÝ DÒNG THỜI GIAN VÁN ĐẤU**",
            f"──────────────────────────────────────",
        ]

        if not grouped:
            overview_lines.append("*Ván đấu kết thúc quá nhanh hoặc không ghi nhận được diễn biến.*")
        else:
            for key, logs in grouped.items():
                is_night = key.startswith("Đêm")
                icon = "🌙" if is_night else "☀️"
                overview_lines.append(f"{icon} **{key}:**")
                
                for log in logs:
                    line = format_replay_story_line(log)
                    overview_lines.append(f"  └ {line}")
                overview_lines.append("")

        if self.game.winner_faction == Faction.DRAW:
            overview_lines.append("🤝 **VÁN HÒA:** không còn người sống; không cộng/trừ rank.")
        elif self.game.winner_faction:
            overview_lines.append(f"🏆 **CHIẾN THẮNG CHUNG CUỘC:** {self.game.winner_faction.value} đã giành thắng lợi!")

        pages.append({
            "title": "📜 Tổng Quan Dòng Thời Gian",
            "content": "\n".join(overview_lines)
        })

        # ── CÁC TRANG TIẾP THEO: CHI TIẾT TỪNG ĐÊM / NGÀY ──
        for title, logs in grouped.items():
            is_night = title.startswith("Đêm")
            icon = "🌙" if is_night else "☀️"
            lines = [
                f"📖 **NHẬT KÝ CHI TIẾT — {icon} {title.upper()}**",
                "──────────────────────────────────────",
            ]
            for log in logs:
                lines.append(f"• {format_replay_story_line(log)}")
            
            pages.append({
                "title": f"{icon} {title}",
                "content": "\n".join(lines)
            })

        # Bound every page, including the overview; never silently truncate replay.
        bounded = []
        for page in pages:
            chunks = []
            current = ""
            for line in page["content"].splitlines(keepends=True):
                while line:
                    capacity = 3800 - len(current)
                    piece, line = line[:capacity], line[capacity:]
                    current += piece
                    if len(current) == 3800:
                        chunks.append(current)
                        current = ""
            if current:
                chunks.append(current)
            for index, content in enumerate(chunks or [""]):
                suffix = f" · phần {index + 1}/{len(chunks)}" if len(chunks) > 1 else ""
                bounded.append({"title": page["title"] + suffix, "content": content})
        return bounded

    def update_buttons(self):
        self.btn_overview.disabled = (self.current_page == 0)
        self.btn_prev.disabled = (self.current_page == 0)
        self.btn_next.disabled = (self.current_page == len(self.pages) - 1)

    def get_embed(self) -> discord.Embed:
        page = self.pages[self.current_page]
        
        if self.current_page == 0:
            color = discord.Color.gold()
        elif "Đêm" in page['title']:
            color = discord.Color.dark_purple()
        else:
            color = discord.Color.orange()

        embed = make_embed(
            title=f"📜 REPLAY STORYLINE — {page['title']} ({self.current_page + 1}/{len(self.pages)})",
            description=page["content"],
            color=color,
        )
        embed.set_footer(text=f"Ván ID: {self.game.guild_id}-{self.game.channel_id} · Chuyển trang để xem chi tiết")
        return embed

    @discord.ui.button(label="Tổng Quan", style=discord.ButtonStyle.primary, emoji="📜", row=0)
    async def btn_overview(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = 0
        self.update_buttons()
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Trang Trước", style=discord.ButtonStyle.secondary, emoji="⬅️", row=0)
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Trang Sau", style=discord.ButtonStyle.secondary, emoji="➡️", row=0)
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)


# ==============================================================================
#  Main Cog Implementation
# ==============================================================================
