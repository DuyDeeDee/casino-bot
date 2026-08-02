# coding: utf-8
"""
Ma Sói (Werewolf) Discord Cog
Xử lý toàn bộ UI (Buttons, Embeds, Dropdowns, Ephemeral) và Luồng Ván đấu (State Machine).
"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.masoi_engine import (
    Faction,
    GamePhase,
    MasoiGame,
    MasoiPlayer,
    MasoiSettings,
    Role,
    get_rank_tier,
)

logger = logging.getLogger(__name__)


# ==============================================================================
#  Lobby & Settings Views
# ==============================================================================

class LobbyView(discord.ui.View):
    def __init__(self, game: MasoiGame, cog: "Masoi"):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="Tham gia", style=discord.ButtonStyle.success, emoji="🐾", custom_id="masoi_join")
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if not self.game.add_player(user.id, user.display_name):
            if user.id in self.game.players:
                await interaction.response.send_message("❌ Bạn đã ở trong phòng chờ rồi!", ephemeral=True)
            elif len(self.game.players) >= 20:
                await interaction.response.send_message("❌ Phòng chờ đã đầy (tối đa 20 người)!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Không thể tham gia lúc này.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Bạn đã tham gia ván Ma Sói!", ephemeral=True)
        await self.cog.update_lobby_embed(self.game, interaction.message)

    @discord.ui.button(label="Rời đi", style=discord.ButtonStyle.secondary, emoji="🚪", custom_id="masoi_leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if not self.game.remove_player(user.id):
            await interaction.response.send_message("❌ Bạn chưa tham gia phòng chờ!", ephemeral=True)
            return

        await interaction.response.send_message("👋 Bạn đã rời khỏi phòng chờ.", ephemeral=True)
        await self.cog.update_lobby_embed(self.game, interaction.message)

    @discord.ui.button(label="Bắt đầu", style=discord.ButtonStyle.primary, emoji="⚔️", custom_id="masoi_start")
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ Host mới được bấm bắt đầu!", ephemeral=True)
            return

        if len(self.game.players) < 5:
            await interaction.response.send_message(
                f"❌ Cần tối thiểu **5 người** để bắt đầu! Hiện có {len(self.game.players)} người.",
                ephemeral=True
            )
            return

        self.stop()
        await interaction.response.defer()
        asyncio.create_task(self.cog.start_game(self.game, interaction.message))

    @discord.ui.button(label="Cài đặt", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="masoi_settings")
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ Host mới có quyền truy cập Cài Đặt!", ephemeral=True)
            return

        view = SettingsView(self.game, self.cog, interaction.message)
        embed = self.cog.build_settings_embed(self.game)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Hủy ván", style=discord.ButtonStyle.danger, emoji="⭕", custom_id="masoi_cancel")
    async def cancel_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ Host mới được bấm hủy ván!", ephemeral=True)
            return

        self.stop()
        await interaction.response.defer()
        await self.cog.force_stop_game(self.game, interaction.channel, interaction.user.display_name)


class SettingsView(discord.ui.View):
    def __init__(self, game: MasoiGame, cog: "Masoi", lobby_message: discord.Message):
        super().__init__(timeout=120)
        self.game = game
        self.cog = cog
        self.lobby_message = lobby_message
        self.update_button_labels()

    def update_button_labels(self):
        s = self.game.settings
        self.btn_reveal.label = f"Hiện vai trò: {'Hiện ngay ✅' if s.reveal_roles_on_death else 'Ẩn tới cuối'}"
        self.btn_tanner.label = f"Kẻ Ngốc: {'Bật ✅' if s.enable_tanner else 'Tắt'}"
        self.btn_vote.label = f"Hiện phiếu: {'Real-time ✅' if s.vote_display == 'REALTIME' else 'Ẩn tới hết giờ'}"
        self.btn_chat.label = f"Người chết chat: {'Được' if s.dead_can_chat else 'Bị cấm ✅'}"
        self.btn_disc_time.label = f"Thời gian thảo luận: {s.discussion_time // 60} phút"
        self.btn_night_time.label = f"Thời gian đêm: {s.night_time}s"
        self.btn_rank.label = f"Tính rank: {'Có ✅' if s.enable_rank else 'Không'}"

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=0)
    async def btn_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_reveal_roles()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=0)
    async def btn_tanner(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_tanner()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=1)
    async def btn_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_vote_display()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=1)
    async def btn_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_dead_chat()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def btn_disc_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_discussion_time()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def btn_night_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_night_time()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=3)
    async def btn_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_rank()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(label="Lưu & Quay Lại Lobby", style=discord.ButtonStyle.success, emoji="💾", row=3)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(content="✅ Đã lưu cài đặt!", embed=None, view=None)
        await self.cog.update_lobby_embed(self.game, self.lobby_message)


# ==============================================================================
#  Night Ephemeral Views
# ==============================================================================

class NightGuardView(discord.ui.View):
    """View Ephemeral chọn mục tiêu bảo vệ cho Bảo Vệ."""
    def __init__(self, game: MasoiGame, guard_id: int):
        super().__init__(timeout=game.settings.night_time)
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
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        self.game.night_guard_target = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Người đã chọn"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** bảo vệ **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightWolfView(discord.ui.View):
    """View Ephemeral cho từng Sói bỏ phiếu cắn."""
    def __init__(self, game: MasoiGame, wolf_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.wolf_id = wolf_id
        self.selected_target_id: Optional[int] = None

        options = []
        for p in game.get_alive_players():
            options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🎯"))

        if options:
            self.select = discord.ui.Select(placeholder="🎯 Chọn 1 người...", options=options[:25], row=0)
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
        self.game.night_wolf_votes[self.wolf_id] = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** cắn **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightSeerView(discord.ui.View):
    """View Ephemeral chọn người để soi phe cho Tiên Tri."""
    def __init__(self, game: MasoiGame, seer_id: int):
        super().__init__(timeout=game.settings.night_time)
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
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        self.game.night_seer_target = target_id
        target_p = self.game.players.get(target_id)
        
        if target_p:
            if target_p.is_wolf:
                res_str = f"🐺 **{target_p.display_name}** là **SÓI**!"
                seer_p = self.game.players.get(self.seer_id)
                if seer_p:
                    seer_p.seer_found_wolf = True
            else:
                res_str = f"👤 **{target_p.display_name}** là **DÂN LÀNG** (không phải Sói)."
            self.game.night_seer_result = res_str
            name = target_p.display_name
        else:
            res_str = "Không tìm thấy thông tin."
            name = "Mục tiêu"

        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** soi **{name}**\n🔮 **Kết quả:** {res_str}", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightCupidView(discord.ui.View):
    """View Ephemeral chọn 2 người làm Cặp Đôi Tình Nhân cho Thần Tình Yêu."""
    def __init__(self, game: MasoiGame, cupid_id: int):
        super().__init__(timeout=game.settings.night_time)
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
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not hasattr(self, "select") or not self.select.values or len(self.select.values) < 2:
            await interaction.response.send_message("❌ Vui lòng chọn đúng 2 người từ danh sách trước!", ephemeral=True)
            return

        id1, id2 = int(self.select.values[0]), int(self.select.values[1])
        p1, p2 = self.game.players.get(id1), self.game.players.get(id2)
        if p1 and p2:
            p1.lover_id = id2
            p2.lover_id = id1
            name1, name2 = p1.display_name, p2.display_name
        else:
            name1, name2 = "Người 1", "Người 2"

        self.stop()
        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n💘 **Đã ghi nhận:** Ghép đôi **{name1}** 💞 **{name2}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

        # Gửi DM thông báo cho 2 người tình nhân
        for p_target, p_other in [(p1, p2), (p2, p1)]:
            if p_target and hasattr(self.game, "cog"):
                user = self.game.cog.bot.get_user(p_target.user_id)
                if user:
                    try:
                        await user.send(
                            f"> 💘 **BẠN ĐÃ ĐƯỢC THẦN TÌNH YÊU GHÉP ĐÔI!**\n"
                            f"> Bạn và **{p_other.display_name}** hiện là **CẶP ĐÔI TÌNH NHÂN**.\n"
                            f"> ⚠️ *Nếu 1 trong 2 người chết, người còn lại sẽ tự sát chết theo!*"
                        )
                    except Exception:
                        pass


class NightWitchView(discord.ui.View):
    """View Ephemeral cho Phù Thủy (Cứu & Độc)."""
    def __init__(self, game: MasoiGame, witch_id: int, victim_id: Optional[int]):
        super().__init__(timeout=game.settings.night_time)
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
        witch_p = self.game.players.get(self.witch_id)
        if witch_p:
            witch_p.witch_save_used = True
        self.game.night_witch_save = True
        victim_p = self.game.players.get(self.victim_id) if self.victim_id else None
        v_name = victim_p.display_name if victim_p else "nạn nhân"
        await self.show_poison_step(interaction, f"✅ **Đã ghi nhận:** CỨU **{v_name}**")

    async def no_save_callback(self, interaction: discord.Interaction):
        self.game.night_witch_save = False
        await self.show_poison_step(interaction, "👌 Bạn không dùng bình cứu đêm nay.")

    async def show_poison_step(self, interaction: discord.Interaction, prefix_msg: str):
        witch_p = self.game.players.get(self.witch_id)
        if not witch_p or witch_p.witch_poison_used:
            self.stop()
            embed = interaction.message.embeds[0] if interaction.message.embeds else None
            if embed:
                divider = "──────────────────────────────────────"
                embed.add_field(name="\u200b", value=f"{divider}\n{prefix_msg}\n*(Bạn đã hết bình độc)*", inline=False)
            await interaction.response.edit_message(embed=embed, view=None)
            return

        embed_poison = discord.Embed(
            title=f"🌙 Đêm {self.game.night_count} — Lượt của Phù Thủy",
            description=f"Bạn có muốn dùng **BÌNH ĐỘC** hạ độc ai không?\nCòn **{self.game.settings.night_time} giây** để quyết định.",
            color=discord.Color(0xE0A638)
        )
        embed_poison.add_field(name="\u200b", value=f"──────────────────────────────────────\n{prefix_msg}", inline=False)

        view = NightWitchPoisonView(self.game, self.witch_id, prefix_msg)
        await interaction.response.edit_message(embed=embed_poison, view=view)


class NightWitchPoisonView(discord.ui.View):
    def __init__(self, game: MasoiGame, witch_id: int, prefix_msg: str):
        super().__init__(timeout=game.settings.night_time)
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
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        witch_p = self.game.players.get(self.witch_id)
        if witch_p:
            witch_p.witch_poison_used = True
        self.game.night_witch_poison = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n☠️ **Đã ghi nhận:** hạ độc **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    async def skip_poison_callback(self, interaction: discord.Interaction):
        self.game.night_witch_poison = None
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
        if target_p and target_p.is_alive:
            target_p.is_alive = False
            self.game.record_log("HUNTER_SHOOT", actor_id=self.hunter_id, target_id=target_id, result="Thợ Săn kéo theo bắn gục")
            if target_p.lover_id and target_p.lover_id in self.game.players:
                lover_p = self.game.players[target_p.lover_id]
                if lover_p.is_alive:
                    lover_p.is_alive = False
                    self.game.record_log("LOVER_DEATH", target_id=lover_p.user_id, result="Chết vì đau thương do tình nhân bị Thợ Săn bắn")

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
    def __init__(self, game: MasoiGame, cog: "Masoi"):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="Yêu cầu bỏ phiếu sớm (0)", style=discord.ButtonStyle.primary, emoji="⏩", custom_id="masoi_early_vote")
    async def early_vote_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        p = self.game.players.get(user_id)
        if not p or not p.is_alive:
            await interaction.response.send_message("❌ Chỉ người chơi còn sống mới được yêu cầu bỏ phiếu sớm!", ephemeral=True)
            return

        self.game.early_vote_requests.add(user_id)
        alive_count = len(self.game.get_alive_players())
        req_count = len(self.game.early_vote_requests)
        button.label = f"Yêu cầu bỏ phiếu sớm ({req_count}/{alive_count})"

        await interaction.response.edit_message(view=self)

        # Nếu đa số người sống đồng ý bỏ phiếu sớm -> Chuyển bước
        if req_count >= (alive_count // 2 + 1):
            self.stop()


class DayVoteView(discord.ui.View):
    """View bỏ phiếu treo cổ ban ngày."""
    def __init__(self, game: MasoiGame, cog: "Masoi"):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog

        options = [discord.SelectOption(label="Bỏ phiếu trắng (Không treo cổ ai)", value="white", emoji="🏳️")]
        for p in game.get_alive_players():
            options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="⚖️"))

        select = discord.ui.Select(placeholder="⚖️ Chọn người bạn nghi ngờ để bỏ phiếu...", options=options[:25], custom_id="masoi_vote_select")
        select.callback = self.vote_callback
        self.add_item(select)

    async def vote_callback(self, interaction: discord.Interaction):
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
            self.game.day_votes[user_id] = target_id
            target_p = self.game.players.get(target_id)
            target_name = target_p.display_name if target_p else "Người chơi"

        await interaction.response.send_message(f"✅ Đã ghi nhận phiếu của bạn cho: **{target_name}**.", ephemeral=True)

        if self.game.settings.vote_display == "REALTIME":
            await self.cog.update_vote_embed(self.game, interaction.message)


# ==============================================================================
#  End Game & Replay Views
# ==============================================================================

class GameEndView(discord.ui.View):
    """View ở embed kết thúc ván."""
    def __init__(self, game: MasoiGame, cog: "Masoi"):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="Xem Lại", style=discord.ButtonStyle.secondary, emoji="📼", custom_id="masoi_replay")
    async def replay_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = ReplayView(self.game)
        embed = view.get_embed()
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Bảng Xếp Hạng", style=discord.ButtonStyle.primary, emoji="🏆", custom_id="masoi_rankboard")
    async def rank_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.cog.build_rankboard_embed()
        await interaction.response.send_message(embed=embed, ephemeral=True)


class ReplayView(discord.ui.View):
    """View phân trang xem lại diễn biến từng Đêm/Ngày."""
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
            key = f"Ngày {log.day}" if "Ban ngày" in log.phase else f"Đêm {log.day}"
            grouped.setdefault(key, []).append(log)

        for title, logs in grouped.items():
            lines = []
            for log in logs:
                t_str = f" -> **{log.target_name}**" if log.target_name else ""
                a_str = f"**{log.actor_name}**: " if log.actor_name else ""
                lines.append(f"• [{log.event_type}] {a_str}{log.result}{t_str}")
            pages.append({"title": title, "content": "\n".join(lines) if lines else "Không có sự kiện."})

        if not pages:
            pages.append({"title": "Thông Tin Replay", "content": "Không ghi nhận được diễn biến ván đấu."})
        return pages

    def update_buttons(self):
        self.btn_prev.disabled = (self.current_page == 0)
        self.btn_next.disabled = (self.current_page == len(self.pages) - 1)

    def get_embed(self) -> discord.Embed:
        page = self.pages[self.current_page]
        embed = make_embed(
            title=f"📼 XEM LẠI — {page['title']} ({self.current_page + 1}/{len(self.pages)})",
            description=page["content"],
            color=discord.Color.dark_purple(),
        )
        embed.set_footer(text=f"Ván ID: {self.game.guild_id}-{self.game.channel_id}")
        return embed

    @discord.ui.button(label="Trước", style=discord.ButtonStyle.secondary, emoji="⬅️")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 0:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)

    @discord.ui.button(label="Sau", style=discord.ButtonStyle.secondary, emoji="➡️")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.get_embed(), view=self)


# ==============================================================================
#  Main Cog Implementation
# ==============================================================================

SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "masoi_settings.json"


MASOI_CREATE_FEE = 1  # 1 Thỏi vàng (Credits)


class Masoi(commands.Cog):
    """Cog Ma Sói (Werewolf) cho Discord Bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games: Dict[str, MasoiGame] = {}  # key: f"{guild_id}-{channel_id}"
        self.saved_settings: Dict[str, MasoiSettings] = {}
        self.load_all_saved_settings()

    def load_all_saved_settings(self):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, val in data.items():
                        self.saved_settings[key] = MasoiSettings.from_dict(val)
        except Exception as e:
            logger.warning("Không thể đọc file masoi_settings.json: %s", e)

    def save_settings_to_file(self):
        try:
            SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {key: s.to_dict() for key, s in self.saved_settings.items()}
            with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            logger.warning("Không thể lưu file masoi_settings.json: %s", e)

    def save_game_settings(self, game: MasoiGame):
        key_channel = f"{game.guild_id}-{game.channel_id}"
        key_guild = str(game.guild_id)
        saved = game.settings.copy()
        self.saved_settings[key_channel] = saved
        self.saved_settings[key_guild] = saved
        self.save_settings_to_file()

    def get_saved_settings(self, guild_id: int, channel_id: int) -> MasoiSettings:
        key_channel = f"{guild_id}-{channel_id}"
        key_guild = str(guild_id)
        if key_channel in self.saved_settings:
            return self.saved_settings[key_channel].copy()
        if key_guild in self.saved_settings:
            return self.saved_settings[key_guild].copy()
        return MasoiSettings()

    def get_economy(self):
        return getattr(self.bot, "economy", None)

    # ──────────────────────────────────────────────
    #  Commands
    # ──────────────────────────────────────────────

    @commands.command(
        name="masoi",
        aliases=["werewolf", "ma-soi"],
        brief="Tạo phòng chờ chơi game Ma Sói (Werewolf). Phí tạo phòng: 1 thỏi vàng.",
        usage="masoi",
    )
    async def masoi_cmd(self, ctx: commands.Context):
        key = f"{ctx.guild.id}-{ctx.channel.id}"
        if key in self.active_games:
            await ctx.send("❌ Đã có một ván Ma Sói đang diễn ra hoặc trong phòng chờ ở kênh này!")
            return

        eco = self.get_economy()
        if eco:
            balance = eco.get_entry(ctx.author.id)[2]  # Index 2 là số thỏi Vàng
            if balance < MASOI_CREATE_FEE:
                await ctx.send(
                    f"❌ **{ctx.author.display_name}**, bạn cần tối thiểu **1 thỏi vàng** để tạo phòng chờ Ma Sói!\n"
                    f"🏆 Số dư Vàng hiện tại của bạn: **{balance:,} thỏi**"
                )
                return
            # Trừ phí 1 thỏi Vàng khi tạo phòng
            eco.add_credits(ctx.author.id, -MASOI_CREATE_FEE)

        game = MasoiGame(ctx.guild.id, ctx.channel.id, ctx.author.id, ctx.author.display_name)
        game.settings = self.get_saved_settings(ctx.guild.id, ctx.channel.id)
        game.add_player(ctx.author.id, ctx.author.display_name)
        self.active_games[key] = game

        embed = self.build_lobby_embed(game)
        view = LobbyView(game, self)
        msg = await ctx.send(
            content=f"<a:yay:1533444499827851505> **{ctx.author.display_name}** đã trả **1 thỏi vàng** phí tạo phòng Ma Sói!",
            embed=embed,
            view=view
        )
        game.message_id = msg.id

    @commands.command(
        name="masoirank",
        aliases=["masoirankboard", "masoi-rank"],
        brief="Xem Bảng Xếp Hạng Rank Ma Sói.",
        usage="masoirank",
    )
    async def masoirank_cmd(self, ctx: commands.Context):
        embed = self.build_rankboard_embed()
        await ctx.send(embed=embed)

    @commands.command(
        name="stopmasoi",
        aliases=["endmasoi", "masoiend", "masoistop", "masoi-stop", "masoi-end", "cancelmasoi"],
        brief="Hủy / Kết thúc ván Ma Sói ở kênh hiện tại ngay lập tức.",
        usage="stopmasoi",
    )
    async def stopmasoi_cmd(self, ctx: commands.Context):
        key = f"{ctx.guild.id}-{ctx.channel.id}"
        game = self.active_games.get(key)
        if not game:
            await ctx.send("❌ Không có ván Ma Sói nào đang diễn ra hoặc trong phòng chờ ở kênh này!")
            return

        is_host = (ctx.author.id == game.host_id)
        is_admin = False
        if hasattr(ctx.author, "guild_permissions"):
            perms = ctx.author.guild_permissions
            is_admin = perms.administrator or perms.manage_guild
        is_owner = await self.bot.is_owner(ctx.author)

        if not (is_host or is_admin or is_owner):
            await ctx.send("❌ Chỉ Host ván đấu hoặc Quản trị viên mới có quyền hủy ván Ma Sói!")
            return

        await self.force_stop_game(game, ctx.channel, ctx.author.display_name)

    async def force_stop_game(self, game: MasoiGame, channel, stopped_by_name: str):
        """Hủy ván game đang diễn ra hoặc phòng chờ ép buộc."""
        key = f"{game.guild_id}-{game.channel_id}"
        was_in_lobby = (game.phase == GamePhase.LOBBY)
        game.phase = GamePhase.GAME_END
        if key in self.active_games:
            del self.active_games[key]
        await self.restore_channel_permissions(game, channel)

        refund_text = ""
        if was_in_lobby:
            eco = self.get_economy()
            if eco:
                eco.add_credits(game.host_id, MASOI_CREATE_FEE)
                refund_text = f"\n<a:muiten:1533428497098473623> Đã hoàn lại **1 thỏi vàng** cho Host **{game.host_name}**."

        embed = make_embed(
            title="<a:luuy:1533429265293508888> ĐÃ HỦY VÁN MA SÓI",
            description=f"Ván Ma Sói ở kênh này đã bị hủy ép buộc bởi **{stopped_by_name}**.{refund_text}",
            color=discord.Color.red()
        )
        await channel.send(embed=embed)

    async def update_lobby_embed(self, game: MasoiGame, message: discord.Message):
        """Cập nhật real-time embed phòng chờ."""
        if not message:
            return
        embed = self.build_lobby_embed(game)
        try:
            await message.edit(embed=embed)
        except Exception as e:
            logger.warning("Không thể cập nhật lobby embed: %s", e)

    async def update_vote_embed(self, game: MasoiGame, message: discord.Message):
        """Cập nhật real-time embed diễn biến bỏ phiếu."""
        if not message:
            return
        embed = self.build_vote_embed(game, is_final=False)
        try:
            await message.edit(embed=embed)
        except Exception as e:
            logger.warning("Không thể cập nhật vote embed: %s", e)

    async def check_and_trigger_hunter(self, game: MasoiGame, channel: discord.TextChannel):
        """Kiểm tra và kích hoạt lượt bắn kéo theo của Thợ Săn khi bị loại."""
        for p in list(game.players.values()):
            if p.role == Role.HUNTER and not p.is_alive and not getattr(p, "hunter_shot_used", False):
                p.hunter_shot_used = True
                h_user = self.bot.get_user(p.user_id)
                if h_user:
                    embed_hunter = discord.Embed(
                        title="🏹 Lượt của Thợ Săn — Kéo theo 1 người",
                        description=f"Bạn đã bị loại! Hãy chọn 1 người để kéo theo chết cùng. Còn **{game.settings.night_time} giây** để quyết định.",
                        color=discord.Color(0xE0A638)
                    )
                    view = NightHunterView(game, p.user_id)
                    try:
                        await h_user.send(embed=embed_hunter, view=view)
                        await asyncio.sleep(game.settings.night_time)
                    except Exception:
                        pass

    # ──────────────────────────────────────────────
    #  Embed Builders
    # ──────────────────────────────────────────────

    def build_lobby_embed(self, game: MasoiGame) -> discord.Embed:
        embed = discord.Embed(
            title="<a:blink:1526231036231680082> Ma Sói — Phòng chờ ván đấu",
            color=discord.Color(0xE0A638)
        )
        embed.add_field(name="CHỦ PHÒNG", value=f"<a:key:1526234974150459593> **{game.host_name}**", inline=True)
        embed.add_field(name="SỐ NGƯỜI", value=f"**{len(game.players)} / 20**", inline=True)

        player_lines = []
        for p in game.players.values():
            if p.user_id == game.host_id:
                player_lines.append(f"<a:wing:1526230985987981393> **{p.display_name}** *(chủ phòng)*")
            else:
                player_lines.append(f"<a:wing:1526230985987981393> **{p.display_name}**")

        players_str = "\n".join(player_lines) if player_lines else "_Chưa có người chơi nào._"
        divider = "──────────────────────────────────────"

        embed.add_field(name="\u200b", value=divider, inline=False)
        embed.add_field(name="NGƯỜI CHƠI", value=players_str, inline=False)
        embed.add_field(
            name="\u200b",
            value=f"{divider}\n<a:muiten:1533428497098473623> *Bấm **Tham gia** để vào ván, chủ phòng bấm **Bắt đầu** khi đủ 5 người trở lên.*",
            inline=False
        )
        embed.set_footer(text=" Phí tạo phòng: 1 thỏi vàng")
        return embed

    def build_settings_embed(self, game: MasoiGame) -> discord.Embed:
        s = game.settings
        desc = (
            f"⚙️ **Cấu Hình Ván Ma Sói**\n\n"
            f"• **Hiện vai trò người chết:** `{'Hiện ngay' if s.reveal_roles_on_death else 'Ẩn tới cuối ván'}`\n"
            f"• **Kẻ Ngốc (Tanner):** `{'Bật' if s.enable_tanner else 'Tắt'}`\n"
            f"• **Hiển thị số phiếu:** `{'Real-time' if s.vote_display == 'REALTIME' else 'Ẩn tới hết giờ'}`\n"
            f"• **Người chết chat ở thread:** `{'Cho phép' if s.dead_can_chat else 'Bị cấm chat'}`\n"
            f"• **Thời gian thảo luận:** `{s.discussion_time // 60} phút`\n"
            f"• **Thời gian hành động đêm:** `{s.night_time} giây`\n"
            f"• **Tính điểm rank:** `{'Có' if s.enable_rank else 'Không'}`\n\n"
            "_Bấm các nút dưới đây để thay đổi giá trị cấu hình._"
        )
        return make_embed(title="⚙️ Cài Đặt Ván Ma Sói", description=desc, color=discord.Color.purple())

    def build_vote_embed(self, game: MasoiGame, is_final: bool = False) -> discord.Embed:
        counts: Dict[int, int] = {}
        white_votes = 0
        total_votes = len(game.day_votes)

        for tid in game.day_votes.values():
            if tid is None:
                white_votes += 1
            else:
                counts[tid] = counts.get(tid, 0) + 1

        def make_bar(cnt: int, total: int) -> str:
            if total <= 0:
                return "▒▒▒▒▒▒▒▒"
            filled = int((cnt / total) * 8)
            filled = min(8, max(0, filled))
            return "█" * filled + "▒" * (8 - filled)

        lines = []
        for p in game.get_alive_players():
            c = counts.get(p.user_id, 0)
            bar = make_bar(c, total_votes) if total_votes > 0 else "▒▒▒▒▒▒▒▒"
            lines.append(f"• ⚖️ **{p.display_name}**: `{bar}` **({c} phiếu)**")

        white_bar = make_bar(white_votes, total_votes) if total_votes > 0 else "▒▒▒▒▒▒▒▒"
        lines.append(f"• 🏳️ **Phiếu trắng**: `{white_bar}` **({white_votes} phiếu)**")

        divider = "──────────────────────────────────────"

        if not is_final and game.settings.vote_display == "END_ONLY":
            desc = f"⚖️ **Đang diễn ra bỏ phiếu...**\n_(Số phiếu hiện đang ẩn tới khi kết thúc giờ bỏ phiếu)_\n\n{divider}\n<:ghim:1526238405061640272> *Bấm menu bên dưới để chọn người bạn nghi ngờ.*"
        else:
            header_str = "⚖️ **KẾT QUẢ BỎ PHIẾU TREO CỔ**" if is_final else "⚖️ **DIỄN BIẾN BỎ PHIẾU REAL-TIME**"
            desc = f"{header_str}\n\n" + "\n".join(lines) + f"\n\n{divider}\n<:ghim:1526238405061640272> *Bấm menu bên dưới để bỏ phiếu người nghi ngờ là Sói.*"

        embed = discord.Embed(
            title=f"⚖️ Bỏ Phiếu Treo Cổ — Ngày {game.day_count}",
            description=desc,
            color=discord.Color(0xE0A638)
        )
        return embed

    def build_rankboard_embed(self) -> discord.Embed:
        eco = self.get_economy()
        if not eco:
            return make_embed(title="🏆 BẢNG XẾP HẠNG MA SÓI", description="Không kết nối được cơ sở dữ liệu.")

        rows = eco.get_masoi_leaderboard(limit=10)
        if not rows:
            return make_embed(title="🏆 BẢNG XẾP HẠNG MA SÓI", description="_Chưa có dữ liệu xếp hạng._")

        lines = []
        for idx, (uid, pts, plays, wins) in enumerate(rows, 1):
            icon, tier_name = get_rank_tier(pts)
            user = self.bot.get_user(uid)
            name = user.display_name if user else f"User {uid}"
            win_rate = (wins / plays * 100) if plays > 0 else 0
            lines.append(f"`#{idx}` {icon} **{name}** — **{pts} pts** ({tier_name}) | 🎮 {plays} ván ({win_rate:.0f}% thắng)")

        return make_embed(
            title="🏆 BẢNG XẾP HẠNG MA SÓI (TOP 10)",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )

    # ──────────────────────────────────────────────
    #  Helper Updates
    # ──────────────────────────────────────────────

    async def update_lobby_embed(self, game: MasoiGame, message: discord.Message):
        embed = self.build_lobby_embed(game)
        try:
            await message.edit(embed=embed)
        except Exception as e:
            logger.warning("Không thể edit lobby embed: %s", e)

    async def update_vote_embed(self, game: MasoiGame, message: discord.Message):
        embed = self.build_vote_embed(game, is_final=False)
        try:
            await message.edit(embed=embed)
        except Exception as e:
            logger.warning("Không thể edit vote embed: %s", e)

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Tự động xoá tin nhắn của người chơi đã chết nếu cài đặt cấm chat."""
        if message.author.bot or not message.guild:
            return
        key = f"{message.guild.id}-{message.channel.id}"
        game = self.active_games.get(key)
        if not game or game.phase in (GamePhase.LOBBY, GamePhase.GAME_END):
            return

        if not game.settings.dead_can_chat:
            player = game.players.get(message.author.id)
            if player and not player.is_alive:
                try:
                    await message.delete()
                    await message.channel.send(
                        f"<a:luuy:1533429265293508888> {message.author.mention}, bạn đã qua đời nên không thể chat trong ván Ma Sói!",
                        delete_after=4
                    )
                except Exception:
                    pass

    async def sync_channel_permissions(self, game: MasoiGame, channel: discord.TextChannel):
        """Cập nhật quyền cấm chat ở kênh chính cho người đã chết."""
        if game.settings.dead_can_chat or not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild
        for p in game.players.values():
            if not p.is_alive:
                member = guild.get_member(p.user_id)
                if member:
                    try:
                        await channel.set_permissions(member, send_messages=False)
                    except Exception:
                        pass

    async def restore_channel_permissions(self, game: MasoiGame, channel: discord.TextChannel):
        """Khôi phục lại quyền chat bình thường khi ván đấu kết thúc."""
        if not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild
        for p in game.players.values():
            member = guild.get_member(p.user_id)
            if member:
                try:
                    await channel.set_permissions(member, overwrite=None)
                except Exception:
                    pass

    # ──────────────────────────────────────────────
    #  Core State Machine Flow
    # ──────────────────────────────────────────────

    async def start_game(self, game: MasoiGame, message: discord.Message):
        game.phase = GamePhase.ROLE_ASSIGN
        game.cog = self
        game.assign_roles()

        # DM vai trò riêng cho từng người
        for p in game.players.values():
            user = self.bot.get_user(p.user_id)
            if user:
                extra_info = ""
                if p.is_wolf:
                    wolves = [other.display_name for other in game.players.values() if other.is_wolf and other.user_id != p.user_id]
                    if wolves:
                        extra_info = f" · Đồng đội Sói: {', '.join(wolves)}"
                    else:
                        extra_info = " · Bạn là Sói duy nhất ván này"

                faction_name = p.role.faction.value.replace(" 🐺", "").replace(" 👥", "").replace(" 🃏", "").replace(" 💘", "")

                dm_text = (
                    f"> {p.role.emoji} **Vai trò của bạn: {p.role.value}**\n"
                    f"> {faction_name} · {p.role.description}{extra_info}"
                )
                try:
                    await user.send(dm_text)
                except Exception:
                    logger.warning("Không thể DM riêng cho user %s", p.user_id)

        # Chạy vòng lặp game
        await self.game_loop(game, message)

    async def game_loop(self, game: MasoiGame, message: discord.Message):
        key = f"{game.guild_id}-{game.channel_id}"
        divider = "──────────────────────────────────────"

        try:
            while game.phase != GamePhase.GAME_END:
                # ── BƯỚC 1: ĐÊM ──
                game.start_night()
                game.phase = GamePhase.NIGHT_GUARD

                # Gửi DM riêng cho Thần Tình Yêu ở Đêm 1
                if game.night_count == 1:
                    cupid_p = game.get_player_by_role(Role.CUPID)
                    if cupid_p:
                        c_user = self.bot.get_user(cupid_p.user_id)
                        if c_user:
                            embed_cupid = discord.Embed(
                                title=f"🌙 Đêm 1 — Lượt của Thần Tình Yêu",
                                description=f"Chọn đúng 2 người để ghép đôi Cặp Đôi Tình Nhân. Còn **{game.settings.night_time} giây** để quyết định.",
                                color=discord.Color(0xE0A638)
                            )
                            view_cupid = NightCupidView(game, cupid_p.user_id)
                            try:
                                await c_user.send(embed=embed_cupid, view=view_cupid)
                            except Exception:
                                pass

                # Gửi DM riêng cho các vai trò ban đêm
                # 1. Bảo Vệ
                guard_p = game.get_player_by_role(Role.GUARD)
                if guard_p:
                    g_user = self.bot.get_user(guard_p.user_id)
                    if g_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Bảo Vệ",
                            description=f"Chọn 1 người để bảo vệ đêm nay. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightGuardView(game, guard_p.user_id)
                        try:
                            await g_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 2. Bầy Sói
                for w in game.get_alive_wolves():
                    w_user = self.bot.get_user(w.user_id)
                    if w_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Sói",
                            description=f"Chọn 1 người để cắn đêm nay. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightWolfView(game, w.user_id)
                        try:
                            await w_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 3. Tiên Tri
                seer_p = game.get_player_by_role(Role.SEER)
                if seer_p:
                    s_user = self.bot.get_user(seer_p.user_id)
                    if s_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Tiên Tri",
                            description=f"Chọn 1 người để soi phe đêm nay. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightSeerView(game, seer_p.user_id)
                        try:
                            await s_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 4. Phù Thủy
                witch_p = game.get_player_by_role(Role.WITCH)
                if witch_p:
                    wt_user = self.bot.get_user(witch_p.user_id)
                    if wt_user:
                        victim_id = game.resolve_wolf_target()
                        victim_p = game.players.get(victim_id) if victim_id else None
                        v_name = victim_p.display_name if victim_p else "Không ai"
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Phù Thủy",
                            description=f"Đêm nay, bầy Sói nhắm cắn: **{v_name}**.\nBạn có muốn dùng **BÌNH CỨU** không? Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightWitchView(game, witch_p.user_id, victim_id)
                        try:
                            await wt_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                embed_night = discord.Embed(
                    title=f"<a:moon:1533444241596874792> Ban Đêm — Đêm {game.night_count}",
                    description=(
                        f"Màn đêm đã buông xuống làng...\n"
                        f"Bot đã gửi tin nhắn riêng (DM) tới các vai trò ban đêm để hành động!\n\n"
                        f"{divider}\n⏱️ **Thời gian đêm:** `{game.settings.night_time}s`"
                    ),
                    color=discord.Color(0xE0A638)
                )
                night_msg = await message.channel.send(embed=embed_night)

                await asyncio.sleep(game.settings.night_time)

                try:
                    await night_msg.delete()
                except Exception:
                    pass

                # 1.5 Tính toán đêm
                game.phase = GamePhase.NIGHT_RESOLVE
                night_deaths = game.resolve_night()
                await self.check_and_trigger_hunter(game, message.channel)

                # ── BƯỚC 2: CÔNG BỐ BAN NGÀY ──
                game.phase = GamePhase.DAY_ANNOUNCE
                game.start_day()
                await self.sync_channel_permissions(game, message.channel)

                if night_deaths:
                    death_names = []
                    for uid in night_deaths:
                        p = game.players[uid]
                        if game.settings.reveal_roles_on_death:
                            death_names.append(f"<:die:1533444731000848415> **{p.display_name}** *({p.role.emoji} {p.role.value})*")
                        else:
                            death_names.append(f"<:die:1533444731000848415> **{p.display_name}**")
                    day_msg_text = "Đêm qua trôi qua đầy đau thương... Các nạn nhân đã ra đi:\n" + "\n".join(death_names)
                else:
                    day_msg_text = "<a:yay:1533444499827851505> Đêm qua trôi qua thật bình yên, không có ai qua đời!"

                embed_announce = discord.Embed(
                    title=f"<a:yay:1533444499827851505> Ban Ngày — Ngày {game.day_count}",
                    description=f"{day_msg_text}\n\n{divider}\n💬 Mọi người hãy cùng trao đổi và thảo luận tại kênh này!",
                    color=discord.Color(0xE0A638)
                )
                await message.channel.send(embed=embed_announce)

                # Kiểm tra thắng ngay sau đêm
                if game.check_win_condition():
                    game.phase = GamePhase.GAME_END
                    break

                # ── BƯỚC 3: THẢO LUẬN BAN NGÀY ──
                game.phase = GamePhase.DAY_DISCUSSION
                disc_embed = discord.Embed(
                    title=f"💬 Ban Ngày — Thảo Luận (Ngày {game.day_count})",
                    description=f"<a:time:1533445134522384536> **Thời gian thảo luận:** `{game.settings.discussion_time // 60} phút`.\n"
                                f"Bấm **Yêu cầu bỏ phiếu sớm** nếu muốn dồn phiếu ngay!\n\n"
                                f"{divider}\n💬 Mọi người hãy trao đổi ý kiến để tìm ra bầy Sói!",
                    color=discord.Color(0xE0A638)
                )
                disc_view = DayDiscussionView(game, self)
                disc_msg = await message.channel.send(embed=disc_embed, view=disc_view)

                # Chờ thảo luận
                elapsed = 0
                while elapsed < game.settings.discussion_time:
                    if disc_view.is_finished():
                        break
                    await asyncio.sleep(2)
                    elapsed += 2

                try:
                    await disc_msg.delete()
                except Exception:
                    pass

                # ── BƯỚC 4: BỎ PHIẾU TREO CỔ ──
                game.phase = GamePhase.DAY_VOTE
                vote_embed = self.build_vote_embed(game, is_final=False)
                vote_view = DayVoteView(game, self)
                vote_msg = await message.channel.send(embed=vote_embed, view=vote_view)

                await asyncio.sleep(game.settings.night_time)

                # ── BƯỚC 5: XỬ LÝ BỎ PHIẾU ──
                game.phase = GamePhase.DAY_RESOLVE
                vote_final_embed = self.build_vote_embed(game, is_final=True)
                try:
                    await vote_msg.edit(embed=vote_final_embed, view=None)
                except Exception:
                    pass

                executed_id = game.resolve_day_vote()
                await self.check_and_trigger_hunter(game, message.channel)
                await self.sync_channel_permissions(game, message.channel)

                if executed_id:
                    p = game.players[executed_id]
                    if game.settings.reveal_roles_on_death:
                        exec_text = f"<a:huyay:1533445376563089448> **{p.display_name}** đã bị dân làng xử tử trên giàn treo cổ! *(Vai trò: **{p.role.emoji} {p.role.value}**)*"
                    else:
                        exec_text = f"<a:huyay:1533445376563089448> **{p.display_name}** đã bị dân làng xử tử trên giàn treo cổ!"
                else:
                    exec_text = "<a:huyay:1533445376563089448> Lượt bỏ phiếu kết thúc hòa phiếu, không ai bị xử tử."

                embed_exec = discord.Embed(
                    title="<a:huyay:1533445376563089448> Kết Quả Xử Tử",
                    description=f"{exec_text}\n\n{divider}",
                    color=discord.Color(0xE0A638)
                )
                await message.channel.send(embed=embed_exec)

                # Kiểm tra thắng sau bỏ phiếu
                if game.check_win_condition():
                    game.phase = GamePhase.GAME_END
                    break

            # ── BƯỚC 6: KẾT THÚC GAME ──
            await self.end_game(game, message)

        finally:
            if key in self.active_games:
                del self.active_games[key]

    async def end_game(self, game: MasoiGame, message: discord.Message):
        game.phase = GamePhase.GAME_END
        game.end_time = float(asyncio.get_event_loop().time())

        # Cộng điểm rank
        rank_pts = game.calculate_rank_points()
        eco = self.get_economy()
        if eco and game.settings.enable_rank:
            for uid, pts in rank_pts.items():
                p = game.players[uid]
                is_win = (p.role.faction == game.winner_faction) or (uid == game.tanner_winner_id)
                faction_str = p.role.faction.name
                eco.add_masoi_points(uid, pts, is_win, faction_str)

        # Tổng kết vai trò
        role_lines = []
        for p in game.players.values():
            status = "<a:key:1526234974150459593> Sống" if p.is_alive else "<:die:1533444731000848415> Chết"
            pts_str = f" (+{rank_pts.get(p.user_id, 0)} pts)" if game.settings.enable_rank else ""
            role_lines.append(f"• **{p.display_name}** — {p.role.emoji} **{p.role.value}** [{status}]{pts_str}")

        winner_str = game.winner_faction.value if game.winner_faction else "Không có"

        end_embed = make_embed(
            title=f"<a:w1:1526231439425667093> VÁN BÀN CỜ MA SÓI KẾT THÚC <a:w1:1526231439425667093> {winner_str}",
            description=(
                f"<a:w1:1526231439425667093> **{winner_str} đã giành chiến thắng!**<a:w1:1526231439425667093>\n\n"
                f"**Vai trò tất cả người chơi:**\n" + "\n".join(role_lines) + "\n\n"
                f" **Tổng thời gian ván:** {game.night_count} Đêm, {game.day_count} Ngày"
            ),
            color=discord.Color.green(),
        )

        end_view = GameEndView(game, self)
        await message.channel.send(embed=end_embed, view=end_view)
        await self.restore_channel_permissions(game, message.channel)
