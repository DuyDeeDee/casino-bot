# coding: utf-8
"""
Ma Sói (Werewolf) Discord Cog
Xử lý toàn bộ UI (Buttons, Embeds, Dropdowns, Ephemeral) và Luồng Ván đấu (State Machine).
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import random
import time
from pathlib import Path
from typing import Dict, Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.helpers import EMOJI_VND, make_embed
from app.discord_bot.modules.masoi_engine import (
    ActionIntent,
    ActionKind,
    Faction,
    GamePhase,
    MasoiGame,
    MasoiPlayer,
    MasoiSettings,
    MASOI_PLAYER_COUNT,
    RankFaction,
    ReplayLog,
    Role,
    get_rank_tier,
)

from app.discord_bot.modules.masoi_ui import (
    NightActionView, NightGuardView, NightWolfView, NightSeerView, NightHarlotView,
    NightInvestigatorView, NightWolfSeerView, NightSerialKillerView, NightWhiteWolfView,
    NightPhantomWolfView, NightGirlView, NightPiperView, MayorSuccessionView,
    NightCupidView, NightWitchView, NightWitchPoisonView, NightHunterView,
    DayDiscussionView, DayVoteView, RankboardView, GameEndView, ReplayView,
    format_replay_story_line,
)

from app.discord_bot.modules.masoi_presentation import ui_lock, remaining_night_seconds
from app.discord_bot.modules.masoi_flow import MasoiFlowMixin
from app.discord_bot.modules.masoi_recovery import MasoiRecoveryMixin

logger = logging.getLogger(__name__)


# ==============================================================================
#  Lobby & Settings Views
# ==============================================================================

async def _safe_send(channel_or_user, *args, **kwargs):
    """Gửi message với retry tự động khi gặp lỗi tạm thời của Discord API."""
    for attempt in range(3):
        try:
            return await channel_or_user.send(*args, **kwargs)
        except discord.HTTPException as e:
            if e.status >= 500 or e.status == 429:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
            raise
        except Exception:
            raise
    return None


async def _safe_edit(message, *args, **kwargs):
    """Edit message với retry tự động khi gặp lỗi tạm thời của Discord API."""
    for attempt in range(3):
        try:
            return await message.edit(*args, **kwargs)
        except discord.HTTPException as e:
            if e.status >= 500 or e.status == 429:
                if attempt < 2:
                    await asyncio.sleep(2 ** attempt)
                    continue
            raise
        except Exception:
            raise
    return None


class LobbyView(discord.ui.View):
    def __init__(self, game: MasoiGame, cog: "Masoi"):
        super().__init__(timeout=None)
        self.game = game
        self.cog = cog
        self.update_controls()

    def update_controls(self) -> None:
        """Disable starting until the lobby has the minimum number of players."""
        can_start = len(self.game.players) == MASOI_PLAYER_COUNT
        for item in self.children:
            if getattr(item, "custom_id", None) == "masoi_start":
                item.disabled = not can_start
            elif getattr(item, "custom_id", None) == "masoi_join":
                item.disabled = len(self.game.players) >= MASOI_PLAYER_COUNT

    @discord.ui.button(label="Tham gia", style=discord.ButtonStyle.success, emoji="🐾", custom_id="masoi_join", row=0)
    async def join_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if not self.game.add_player(user.id, user.display_name):
            if user.id in self.game.players:
                await interaction.response.send_message("❌ Bạn đã ở trong phòng chờ rồi!", ephemeral=True)
            elif len(self.game.players) >= MASOI_PLAYER_COUNT:
                await interaction.response.send_message(f"❌ Phòng chờ đã đầy (tối đa {MASOI_PLAYER_COUNT} người)!", ephemeral=True)
            else:
                await interaction.response.send_message("❌ Không thể tham gia lúc này.", ephemeral=True)
            return

        await interaction.response.send_message("✅ Bạn đã tham gia ván Ma Sói!", ephemeral=True)
        self.update_controls()
        await self.cog.update_lobby_embed(self.game, interaction.message, view=self)

    @discord.ui.button(label="Rời phòng", style=discord.ButtonStyle.secondary, emoji="🚪", custom_id="masoi_leave", row=0)
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if not self.game.remove_player(user.id):
            await interaction.response.send_message("❌ Bạn chưa tham gia phòng chờ!", ephemeral=True)
            return

        await interaction.response.send_message("👋 Bạn đã rời khỏi phòng chờ.", ephemeral=True)
        self.update_controls()
        await self.cog.update_lobby_embed(self.game, interaction.message, view=self)

    @discord.ui.button(label="Bắt đầu", style=discord.ButtonStyle.primary, emoji="⚔️", custom_id="masoi_start", row=0)
    async def start_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ Host mới được bấm bắt đầu!", ephemeral=True)
            return

        if len(self.game.players) != MASOI_PLAYER_COUNT:
            await interaction.response.send_message(
                f"❌ Cần đúng **{MASOI_PLAYER_COUNT} người** để bắt đầu! Hiện có {len(self.game.players)} người.",
                ephemeral=True
            )
            return

        self.stop()
        await interaction.response.defer()
        task = asyncio.create_task(self.cog.start_game(self.game, interaction.message))
        if hasattr(self.cog, "_game_tasks"):
            self.cog._game_tasks[self.game.rank_match_id] = task
            task.add_done_callback(lambda done: self.cog._game_tasks.pop(self.game.rank_match_id, None)
                                   if self.cog._game_tasks.get(self.game.rank_match_id) is done else None)
        # Đảm bảo exception từ task không bị nuốt im lặng
        task.add_done_callback(
            lambda t: logger.error("Lỗi nghiêm trọng khi khởi động ván Ma Sói: %s", t.exception(), exc_info=t.exception())
            if not t.cancelled() and t.exception() else None
        )

    @discord.ui.button(label="Cài đặt", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="masoi_settings", row=1)
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ Host mới có quyền truy cập Cài Đặt!", ephemeral=True)
            return

        view = SettingsView(self.game, self.cog, interaction.message)
        embed = self.cog.build_settings_embed(self.game)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Vai Trò", style=discord.ButtonStyle.secondary, emoji="🎭", custom_id="masoi_roles_info", row=1)
    async def roles_info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        # The role guide and role DMs use exactly the engine's descriptions.
        available = set(self.game.preview_roles())
        groups = [
            ("🐺 Bầy Sói", [r for r in Role if r in available and r.faction == Faction.WEREWOLF]),
            ("👥 Dân Làng", [r for r in Role if r in available and r.faction == Faction.VILLAGER]),
            ("🃏 Solo", [r for r in (Role.TANNER, Role.ARSONIST, Role.HUMAN_HUNTER) if r in available]),
        ]
        embeds = []
        for title, roles in groups:
            lines = [f"• {r.emoji} **{r.value}**: {r.description}" for r in roles]
            embeds.append(make_embed(title=f"🎭 Vai Trò — {title}", description="\n".join(lines), color=discord.Color.purple()))
        await interaction.response.send_message(embeds=embeds, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        logger.error("LobbyView error on %s: %s", item, error, exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi. Vui lòng thử lại!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Đã xảy ra lỗi. Vui lòng thử lại!", ephemeral=True)
        except Exception:
            pass

    @discord.ui.button(label="Hủy phòng", style=discord.ButtonStyle.danger, emoji="⭕", custom_id="masoi_cancel", row=1)
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
        self.remove_item(self.btn_tanner)
        self.remove_item(self.btn_custom_roles)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.host_id or self.game.phase != GamePhase.LOBBY:
            await interaction.response.send_message("❌ Chỉ Host được đổi cài đặt khi phòng còn chờ.", ephemeral=True)
            return False
        return True

    def update_button_labels(self):
        s = self.game.settings
        self.btn_reveal.label = f"Hiện vai trò: {'Hiện ngay ✅' if s.reveal_roles_on_death else 'Ẩn tới cuối'}"
        self.btn_tanner.label = f"Kẻ Ngốc: {'Bật ✅' if s.tanner_enabled else 'Tắt'}"
        self.btn_vote.label = f"Hiện phiếu: {'Real-time ✅' if s.vote_display == 'REALTIME' else 'Ẩn tới hết giờ'}"
        self.btn_chat.label = f"Người chết chat: {'Được' if s.dead_can_chat else 'Bị cấm ✅'}"
        self.btn_disc_time.label = f"Thời gian thảo luận: {s.discussion_time // 60} phút"
        self.btn_night_time.label = f"Thời gian đêm: {s.night_time}s"
        self.btn_rank.label = f"Tính rank: {'Có ✅' if s.enable_rank else 'Không'}"
        self.btn_events.label = f"Thẻ sự kiện: {'Bật ✅' if s.enable_events else 'Tắt'}"
        self.btn_custom_roles.label = f"Phân vai: {'Tự động ✅' if s.role_setup_mode == 'AUTO' else 'Tùy chỉnh ⚙️'}"

    async def check_vip_host(self, interaction: discord.Interaction, feature_name: str) -> bool:
        eco = self.cog.get_economy()
        if eco and not eco.is_masoi_vip(interaction.user.id):
            await interaction.response.send_message(
                f"❌ **TÍNH NĂNG CHỈ DÀNH CHO VIP HOST!**\n"
                f"Thay đổi **{feature_name}** chỉ dành cho Host có gói VIP Ma Sói.\n"
                f"👉 Dùng lệnh **`i?masoivip`** để nâng cấp gói VIP!",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=0)
    async def btn_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        if not await self.check_vip_host(interaction, "Hiện vai trò người chết"):
            return
        self.game.settings.cycle_reveal_roles()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=0)
    async def btn_tanner(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        self.game.settings.cycle_tanner()
        await self.cog.update_lobby_embed(self.game, self.lobby_message)
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=1)
    async def btn_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        self.game.settings.cycle_vote_display()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=1)
    async def btn_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        self.game.settings.cycle_dead_chat()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def btn_disc_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        if not await self.check_vip_host(interaction, "Thời gian thảo luận"):
            return
        self.game.settings.cycle_discussion_time()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def btn_night_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        if not await self.check_vip_host(interaction, "Thời gian đêm"):
            return
        self.game.settings.cycle_night_time()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=3)
    async def btn_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        self.game.settings.cycle_rank()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, emoji="🎴", row=3)
    async def btn_events(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        self.game.settings.cycle_events()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="🎭", row=3)
    async def btn_custom_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        view = CustomRolesConfigView(self.game, self.cog, self, self.lobby_message)
        embed = view.get_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Lưu & Quay Lại Lobby", style=discord.ButtonStyle.success, emoji="💾", row=4)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.interaction_check(interaction):
            return
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(content="✅ Đã lưu cài đặt!", embed=None, view=None)
        await self.cog.update_lobby_embed(self.game, self.lobby_message)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        logger.error("SettingsView error on %s: %s", item, error, exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi khi thay đổi cài đặt. Vui lòng thử lại!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Đã xảy ra lỗi khi thay đổi cài đặt. Vui lòng thử lại!", ephemeral=True)
        except Exception:
            pass


class CustomRolesConfigView(discord.ui.View):
    """View Tùy Chỉnh Vai Trò cho Host."""
    def __init__(self, game: MasoiGame, cog: "Masoi", parent_view: SettingsView, lobby_message: discord.Message):
        super().__init__(timeout=180)
        self.game = game
        self.cog = cog
        self.parent_view = parent_view
        self.lobby_message = lobby_message

        s = game.settings

        # Dropdown 1: Chọn số lượng Sói
        wolf_options = [
            discord.SelectOption(label="1 Sói", value="1", default=(s.custom_wolf_count == 1)),
            discord.SelectOption(label="2 Sói", value="2", default=(s.custom_wolf_count == 2)),
            discord.SelectOption(label="3 Sói", value="3", default=(s.custom_wolf_count == 3)),
            discord.SelectOption(label="4 Sói", value="4", default=(s.custom_wolf_count == 4)),
        ]
        self.select_wolves = discord.ui.Select(
            placeholder="🐺 Chọn số lượng Sói...",
            options=wolf_options,
            row=0
        )
        self.select_wolves.callback = self.wolves_callback
        self.add_item(self.select_wolves)

        # Dropdown 2: Chọn Vai trò Đặc biệt (Multi-select)
        special_roles_def = [
            (Role.WOLF_SEER, "Sói Tiên Tri"),
            (Role.WOLF_CUB, "Sói Cuồng Sát"),
            (Role.YOUNG_WOLF, "Sói Trẻ"),
            (Role.PHANTOM_WOLF, "Sói Ảo Ảnh"),
            (Role.MAYOR, "Thị Trưởng"),
            (Role.SEER, "Tiên Tri"),
            (Role.APPRENTICE_SEER, "Tiên Tri Tập Sự"),
            (Role.GUARD, "Bảo Vệ"),
            (Role.DOCTOR, "Bác Sĩ"),
            (Role.WITCH, "Phù Thủy"),
            (Role.HARLOT, "Kĩ Nữ"),
            (Role.HUNTER, "Thợ Săn"),
            (Role.GUNNER, "Xạ Thủ"),
            (Role.RUSTY_KNIGHT, "Hiệp Sĩ Kiếm Gỉ"),
            (Role.CURSED, "Kẻ Bị Nguyền"),
            (Role.ELDER, "Già Làng"),
            (Role.CUPID, "Thần Tình Yêu"),
            (Role.LYCAN, "Bán Nguyệt"),
            (Role.INVESTIGATOR, "Thám Tử"),
            (Role.ARSONIST, "Kẻ Phóng Hỏa"),
            (Role.HUMAN_HUNTER, "Thợ Săn Người"),
            (Role.SCAPEGOAT, "Dê Tế Thần"),
            (Role.TANNER, "Kẻ Ngốc"),
        ]

        role_options = []
        for r_enum, r_name in special_roles_def:
            is_def = (r_enum.name in s.custom_special_roles)
            role_options.append(discord.SelectOption(
                label=f"{r_enum.emoji} {r_name}",
                value=r_enum.name,
                default=is_def,
                description=r_enum.description[:50]
            ))

        self.select_roles = discord.ui.Select(
            placeholder="🎭 Chọn các vai trò đặc biệt tham gia...",
            min_values=0,
            max_values=len(role_options),
            options=role_options,
            row=1
        )
        self.select_roles.callback = self.roles_callback
        self.add_item(self.select_roles)

        # Button Chuyển đổi AUTO / CUSTOM
        btn_mode_label = f"Phân vai: {'Tự Động (AUTO) ✅' if s.role_setup_mode == 'AUTO' else 'Tùy Chỉnh (CUSTOM) ⚙️'}"
        self.btn_toggle_mode = discord.ui.Button(label=btn_mode_label, style=discord.ButtonStyle.primary, row=2)
        self.btn_toggle_mode.callback = self.toggle_mode_callback
        self.add_item(self.btn_toggle_mode)

        # Button Quay lại Settings
        btn_back = discord.ui.Button(label="Quay lại Cài Đặt", style=discord.ButtonStyle.secondary, emoji="⬅️", row=2)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

    async def interaction_check(self, interaction: discord.Interaction):
        if interaction.user.id != self.game.host_id or self.game.phase != GamePhase.LOBBY:
            await interaction.response.send_message("❌ Chỉ Host được đổi cài đặt khi phòng còn chờ.", ephemeral=True)
            return False
        return True

    def get_embed(self) -> discord.Embed:
        s = self.game.settings
        mode_str = "Tự Động (AUTO)" if s.role_setup_mode == "AUTO" else "Tùy Chỉnh (CUSTOM)"
        
        roles_str_list = []
        for r_name in s.custom_special_roles:
            try:
                r = Role[r_name]
                roles_str_list.append(f"{r.emoji} **{r.value}**")
            except KeyError:
                pass

        roles_text = " • ".join(roles_str_list) if roles_str_list else "_Chưa chọn vai trò đặc biệt nào (Mặc định Sói & Dân)_"

        desc = (
            f"🎭 **CẤU HÌNH VAI TRÒ VÁN ĐẤU**\n\n"
            f"• **Phân vai:** `{mode_str}`\n"
            f"• **Số lượng Sói cài đặt:** `{s.custom_wolf_count} Sói`\n"
            f"• **Các vai trò đặc biệt đã chọn:**\n{roles_text}\n\n"
            f"📌 *Lưu ý: Nếu số vai trò cài đặt ít hơn số người chơi trong phòng, các vị trí còn lại sẽ tự động là **Dân Thường**.*"
        )
        return make_embed(title="⚙️ Tùy Chỉnh Vai Trò Ván Đấu", description=desc, color=discord.Color.purple())

    async def check_vip_host(self, interaction: discord.Interaction) -> bool:
        eco = self.cog.get_economy()
        if not eco or not eco.is_masoi_vip(self.game.host_id):
            await interaction.response.send_message(
                "❌ **TÍNH NĂNG CHỈ DÀNH CHO VIP HOST!**\n"
                "Tính năng **Tùy Chỉnh Vai Trò (`CUSTOM`)** chỉ dành cho Host có gói VIP Ma Sói.\n"
                "👉 Dùng lệnh **`i?masoivip`** để nâng cấp gói VIP!",
                ephemeral=True
            )
            return False
        return True

    async def wolves_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not await self.check_vip_host(interaction):
            return
        val = int(self.select_wolves.values[0])
        self.game.settings.custom_wolf_count = val
        self.game.settings.role_setup_mode = "CUSTOM"
        self.btn_toggle_mode.label = "Phân vai: Tùy Chỉnh (CUSTOM) ⚙️"
        await self.cog.update_lobby_embed(self.game, self.parent_view.lobby_message)
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def roles_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        if not await self.check_vip_host(interaction):
            return
        selected = self.select_roles.values
        self.game.settings.custom_special_roles = list(selected)
        self.game.settings.role_setup_mode = "CUSTOM"
        self.btn_toggle_mode.label = "Phân vai: Tùy Chỉnh (CUSTOM) ⚙️"
        await self.cog.update_lobby_embed(self.game, self.parent_view.lobby_message)
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def toggle_mode_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        s = self.game.settings
        # Every host may leave CUSTOM; only a current VIP may enable it.
        if s.role_setup_mode == "AUTO" and not await self.check_vip_host(interaction):
            return
        s.role_setup_mode = "CUSTOM" if s.role_setup_mode == "AUTO" else "AUTO"
        self.btn_toggle_mode.label = f"Phân vai: {'Tự Động (AUTO) ✅' if s.role_setup_mode == 'AUTO' else 'Tùy Chỉnh (CUSTOM) ⚙️'}"
        await self.cog.update_lobby_embed(self.game, self.parent_view.lobby_message)
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def back_callback(self, interaction: discord.Interaction):
        if not await self.interaction_check(interaction):
            return
        self.parent_view.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self.parent_view)


# ==============================================================================
#  Night Ephemeral Views
# ==============================================================================

class VipSetQuoteModal(discord.ui.Modal, title="💬 Lời Trăn Trối VIP Ma Sói"):
    quote_input = discord.ui.TextInput(
        label="Nội dung phát biểu khi qua đời:",
        style=discord.TextStyle.paragraph,
        placeholder="VD: Vĩnh biệt dân làng, hãy trả thù cho tớ...",
        max_length=150,
        required=True
    )

    def __init__(self, cog: "Masoi"):
        super().__init__()
        self.cog = cog

    async def on_submit(self, interaction: discord.Interaction):
        eco = self.cog.get_economy()
        if not eco or not eco.is_masoi_vip(interaction.user.id):
            await interaction.response.send_message("❌ Tính năng Lời trăn trối cá nhân chỉ dành cho tài khoản VIP!", ephemeral=True)
            return

        text = self.quote_input.value
        eco.set_masoi_last_words(interaction.user.id, text)
        await interaction.response.send_message(
            f"✅ **Đã cập nhật Lời trăn trối VIP thành công!**\n> 💬 *\"{text}\"*",
            ephemeral=True
        )


class VipDashboardView(discord.ui.View):
    """View giao diện Bảng điều khiển VIP Ma Sói."""
    def __init__(self, cog: "Masoi", user_id: int):
        super().__init__(timeout=120)
        self.cog = cog
        self.user_id = user_id

    @discord.ui.button(label="Sửa Lời Trăn Trối VIP", style=discord.ButtonStyle.primary, emoji="💬", row=0)
    async def btn_set_quote(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải menu của bạn!", ephemeral=True)
            return

        eco = self.cog.get_economy()
        if not eco or not eco.is_masoi_vip(interaction.user.id):
            await interaction.response.send_message("❌ Tính năng Lời trăn trối cá nhân chỉ dành cho người chơi có VIP!", ephemeral=True)
            return

        modal = VipSetQuoteModal(self.cog)
        await interaction.response.send_modal(modal)


SETTINGS_FILE = Path(__file__).resolve().parent.parent.parent / "data" / "masoi_settings.json"


MASOI_CREATE_FEE = 10_000  # 10,000 VND


class Masoi(MasoiFlowMixin, MasoiRecoveryMixin, commands.Cog):
    """Cog Ma Sói (Werewolf) cho Discord Bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games: Dict[str, MasoiGame] = {}  # key: f"{guild_id}-{channel_id}"
        self._game_tasks = {}
        self._recovering_channels = set()
        self._recovery_ready = False
        self.saved_settings: Dict[str, MasoiSettings] = {}
        self.load_all_saved_settings()

    def load_all_saved_settings(self):
        try:
            if SETTINGS_FILE.exists():
                with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for key, val in data.items():
                        self.saved_settings[key] = self.shared_settings_only(MasoiSettings.from_dict(val))
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
        # Role customization belongs to this lobby, never to another host's room.
        saved = self.shared_settings_only(game.settings)
        self.saved_settings[key_channel] = saved
        self.saved_settings[key_guild] = saved
        self.save_settings_to_file()

    @staticmethod
    def shared_settings_only(settings: MasoiSettings) -> MasoiSettings:
        saved = settings.copy()
        defaults = MasoiSettings()
        saved.role_setup_mode = defaults.role_setup_mode
        saved.custom_wolf_count = defaults.custom_wolf_count
        saved.custom_special_roles = []
        saved.enable_events = False
        return saved

    def get_saved_settings(self, guild_id: int, channel_id: int) -> MasoiSettings:
        key_channel = f"{guild_id}-{channel_id}"
        key_guild = str(guild_id)
        if key_channel in self.saved_settings:
            return self.shared_settings_only(self.saved_settings[key_channel])
        if key_guild in self.saved_settings:
            return self.shared_settings_only(self.saved_settings[key_guild])
        return MasoiSettings()

    def get_economy(self):
        return getattr(self.bot, "economy", None)

    def player_badge(self, user_id: int, fallback: str = "") -> str:
        eco = self.get_economy()
        return (eco.get_masoi_custom_badge(user_id) if eco else "") or fallback

    def player_label(self, player) -> str:
        badge = self.player_badge(player.user_id)
        return f"{badge} **{player.display_name}**" if badge else f"**{player.display_name}**"

    async def refresh_player_badge_lobbies(self, user_id: int) -> None:
        """Refresh both waiting lobbies and the current public vote, not past messages."""
        for game in list(self.active_games.values()):
            if user_id not in game.players:
                continue
            try:
                if game.phase == GamePhase.LOBBY and game.message_id:
                    channel = self.bot.get_channel(game.channel_id)
                    if channel:
                        message = await channel.fetch_message(game.message_id)
                        if game.phase == GamePhase.LOBBY:
                            await self.update_lobby_embed(game, message)
                elif game.phase == GamePhase.DAY_VOTE:
                    await self.update_vote_embed(game, getattr(game, "day_vote_message", None))
            except Exception as e:
                logger.warning("Không thể cập nhật badge Ma Sói cho user %s: %s", user_id, e)

    # ──────────────────────────────────────────────
    #  Commands
    # ──────────────────────────────────────────────

    @commands.command(
        name="masoi",
        aliases=["werewolf", "ma-soi"],
        brief="Tạo phòng chờ chơi game Ma Sói (Werewolf). Phí tạo phòng: 10,000 VND (Miễn phí cho VIP).",
        usage="masoi [event]",
    )
    async def masoi_cmd(self, ctx: commands.Context, *, sub_command: str = ""):
        if sub_command.strip().lower() in ("vip", "v"):
            return await self.masoivip_cmd(ctx)

        sub_clean = sub_command.strip().lower()
        is_event = sub_clean in ("event", "events", "e", "masoievent")
        if sub_clean and not is_event:
            await ctx.send(f"❌ Dùng `{ctx.prefix}masoi` hoặc `{ctx.prefix}masoievent` để tạo phòng Ma Sói.")
            return

        key = f"{ctx.guild.id}-{ctx.channel.id}"
        if not getattr(self, "_recovery_ready", True) or key in getattr(self, "_recovering_channels", set()):
            await ctx.send("⏳ Kênh đang phục hồi ván Ma Sói trước. Hãy chờ khôi phục quyền chat xong.")
            return
        if key in self.active_games:
            await ctx.send("❌ Đã có một ván Ma Sói đang diễn ra hoặc trong phòng chờ ở kênh này!")
            return

        eco = self.get_economy()
        is_vip = eco.is_masoi_vip(ctx.author.id) if eco else False
        if eco and not is_vip:
            balance = eco.get_entry(ctx.author.id)[1]  # Index 1 là VND
            if balance < MASOI_CREATE_FEE:
                await ctx.send(
                    f"❌ **{ctx.author.display_name}**, bạn cần tối thiểu **{MASOI_CREATE_FEE:,}** {EMOJI_VND} để tạo phòng chờ Ma Sói!\n"
                    f"💰 Số dư hiện tại của bạn: **{balance:,}** {EMOJI_VND}\n"
                    f"💡 *Mẹo: Sở hữu gói VIP Ma Sói (`{ctx.prefix}masoivip`) để được miễn phí tạo phòng 100%!*"
                )
                return
            # Trừ phí 10,000 VND khi tạo phòng
            eco.add_money(ctx.author.id, -MASOI_CREATE_FEE)
            msg_text = f"<a:yay:1533444499827851505> **{ctx.author.display_name}** đã trả **{MASOI_CREATE_FEE:,}** {EMOJI_VND} phí tạo phòng Ma Sói!"
        elif is_vip:
            msg_text = f"<a:2336vipgif:1534596901834592286> **{ctx.author.display_name}** *(<a:2336vipgif:1534596901834592286> VIP Ma Sói)* được **miễn phí tạo phòng**!"
        else:
            msg_text = f"<a:yay:1533444499827851505> **{ctx.author.display_name}** đã tạo phòng Ma Sói!"

        game = MasoiGame(ctx.guild.id, ctx.channel.id, ctx.author.id, ctx.author.display_name)
        game.settings = self.get_saved_settings(ctx.guild.id, ctx.channel.id)
        game.settings.enable_events = is_event

        if not is_vip:
            game.settings.reveal_roles_on_death = False
            game.settings.discussion_time = 120
            game.settings.night_time = 60
        game.add_player(ctx.author.id, ctx.author.display_name)
        self.active_games[key] = game

        embed = self.build_lobby_embed(game)
        view = LobbyView(game, self)
        msg = await ctx.send(
            content=msg_text,
            embed=embed,
            view=view
        )
        game.message_id = msg.id

    @commands.command(
        name="masoievent",
        aliases=["masoi-event", "werewolfevent", "masoi_event"],
        brief="Tạo phòng Ma Sói với thẻ sự kiện đêm.",
        usage="masoievent",
    )
    async def masoievent_cmd(self, ctx: commands.Context):
        await type(self).masoi_cmd.callback(self, ctx, sub_command="event")

    @commands.command(
        name="masoivip",
        aliases=["masoi-vip", "vipmasoi"],
        brief="Xem bảng điều khiển VIP Ma Sói và mua gói VIP.",
        usage="masoivip",
    )
    async def masoivip_cmd(self, ctx: commands.Context):
        embed = self.build_vip_embed(ctx.author.id)
        view = VipDashboardView(self, ctx.author.id)
        await ctx.send(embed=embed, view=view)

    @commands.command(
        name="setquote",
        aliases=["setlastwords", "trantroi"],
        brief="Cài đặt Lời trăn trối cá nhân dành cho tài khoản VIP Ma Sói.",
        usage="setquote <nội dung lời trăn trối>",
    )
    async def setquote_cmd(self, ctx: commands.Context, *, text: str = ""):
        eco = self.get_economy()
        if not eco or not eco.is_masoi_vip(ctx.author.id):
            await ctx.send(f"❌ **Tính năng Lời trăn trối chỉ dành cho VIP Ma Sói!**\nHãy dùng lệnh `{ctx.prefix}masoivip` để nâng cấp gói VIP.")
            return

        if not text:
            await ctx.send(f"❌ Vui lòng nhập nội dung lời trăn trối! VD: `{ctx.prefix}setquote Vĩnh biệt dân làng!`")
            return

        eco.set_masoi_last_words(ctx.author.id, text)
        await ctx.send(f"✅ **Đã cập nhật Lời trăn trối VIP thành công!**\n> 💬 *\"{text[:150]}\"*")

    @commands.command(
        name="setmasoivip",
        aliases=["setvipmasoi", "addmasoivip"],
        brief="[Admin/Owner] Cấp gói VIP Ma Sói cho người chơi.",
        usage="setmasoivip @user <số_ngày>",
        hidden=True,
    )
    async def setmasoivip_cmd(self, ctx: commands.Context, member: discord.Member, days: int = 30):
        is_admin = False
        if hasattr(ctx.author, "guild_permissions"):
            perms = ctx.author.guild_permissions
            is_admin = perms.administrator or perms.manage_guild
        is_owner = await self.bot.is_owner(ctx.author)

        if not (is_admin or is_owner):
            await ctx.send("❌ Chỉ Quản trị viên hoặc Bot Owner mới có quyền dùng lệnh này!")
            return

        eco = self.get_economy()
        if not eco:
            await ctx.send("❌ Không kết nối được Database!")
            return

        new_expires = eco.add_masoi_vip(member.id, days)
        exp_str = time.strftime("%H:%M %d/%m/%Y", time.localtime(new_expires))
        await ctx.send(f"<a:2336vipgif:1534596901834592286> **Đã cấp thành công {days} ngày VIP Ma Sói cho {member.mention}!**\n📅 Hạn dùng mới: `{exp_str}`")

    @commands.command(
        name="removemasoivip",
        aliases=["delmasoivip", "cancelmasoivip", "huyvipmasoi", "removevipmasoi"],
        brief="[Admin/Owner] Hủy gói VIP Ma Sói của người chơi.",
        usage="removemasoivip @user",
        hidden=True,
    )
    async def removemasoivip_cmd(self, ctx: commands.Context, member: discord.Member):
        is_admin = False
        if hasattr(ctx.author, "guild_permissions"):
            perms = ctx.author.guild_permissions
            is_admin = perms.administrator or perms.manage_guild
        is_owner = await self.bot.is_owner(ctx.author)

        if not (is_admin or is_owner):
            await ctx.send("❌ Chỉ Quản trị viên hoặc Bot Owner mới có quyền dùng lệnh này!")
            return

        eco = self.get_economy()
        if not eco:
            await ctx.send("❌ Không kết nối được Database!")
            return

        eco.remove_masoi_vip(member.id)
        await ctx.send(f"⭕ **Đã hủy gói VIP Ma Sói của {member.mention} thành công!**")

    @commands.command(
        name="masoiviplist",
        aliases=["listvipmasoi", "vipmasoilist"],
        brief="[Admin/Owner] Xem danh sách tất cả VIP Ma Sói đang hoạt động.",
        usage="masoiviplist",
        hidden=True,
    )
    async def masoiviplist_cmd(self, ctx: commands.Context):
        is_admin = False
        if hasattr(ctx.author, "guild_permissions"):
            perms = ctx.author.guild_permissions
            is_admin = perms.administrator or perms.manage_guild
        is_owner = await self.bot.is_owner(ctx.author)

        if not (is_admin or is_owner):
            await ctx.send("❌ Chỉ Quản trị viên hoặc Bot Owner mới có quyền dùng lệnh này!")
            return

        eco = self.get_economy()
        if not eco:
            await ctx.send("❌ Không kết nối được Database!")
            return

        vip_rows = eco.get_all_masoi_vip()

        if not vip_rows:
            await ctx.send("📋 **Hiện không có tài khoản VIP Ma Sói nào đang hoạt động.**")
            return

        lines = []
        for i, (uid, expires_at, last_words) in enumerate(vip_rows, start=1):
            user = self.bot.get_user(uid)
            name = f"{user.name} ({user.id})" if user else f"User ID: {uid}"
            exp_str = time.strftime("%H:%M %d/%m/%Y", time.localtime(expires_at))
            lw = f'💬 *"{last_words[:40]}..."*' if last_words else "_Chưa có lời trăn trối_"
            lines.append(f"`{i}.` <a:2336vipgif:1534596901834592286> **{name}**\n    📅 Hết hạn: `{exp_str}` | {lw}")

        desc = "\n\n".join(lines)
        embed = make_embed(
            title=f"<a:2336vipgif:1534596901834592286> Danh Sách VIP Ma Sói ({len(vip_rows)} tài khoản)",
            description=desc,
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="setmasoibadge",
        aliases=["setbadge", "setmasoihuyhieu", "sethuyhieu"],
        brief="[Admin/Owner] Đặt huy hiệu tự chọn hiển thị cho người chơi trong Ma Sói (Không cấp quyền VIP).",
        usage="setmasoibadge @user <huy_hiệu/emoji>",
        hidden=True,
    )
    async def setmasoibadge_cmd(self, ctx: commands.Context, member: discord.Member, *, badge: str = ""):
        is_admin = False
        if hasattr(ctx.author, "guild_permissions"):
            perms = ctx.author.guild_permissions
            is_admin = perms.administrator or perms.manage_guild
        is_owner = await self.bot.is_owner(ctx.author)

        if not (is_admin or is_owner):
            await ctx.send("❌ Chỉ Quản trị viên hoặc Bot Owner mới có quyền dùng lệnh này!")
            return

        eco = self.get_economy()
        if not eco:
            await ctx.send("❌ Không kết nối được Database!")
            return

        badge = badge.strip()
        if not badge:
            await ctx.send(f"❌ Vui lòng nhập huy hiệu/emoji cần đặt! VD: `{ctx.prefix}setmasoibadge @user 🔥`")
            return

        matched_emoji = None

        # 1. Nếu người dùng nhập ID số (Ví dụ: 1534984465657364651)
        if badge.isdigit():
            emoji_id = int(badge)
            matched_emoji = self.bot.get_emoji(emoji_id)
            if not matched_emoji:
                try:
                    matched_emoji = await self.bot.fetch_emoji(emoji_id)
                except Exception:
                    pass
            if matched_emoji:
                badge = str(matched_emoji)
            else:
                # Fallback: Tự đóng gói thành mã Animated Emoji của Discord
                badge = f"<a:emoji:{emoji_id}>"

        # 2. Nếu người dùng truyền mã nguyên bản dạng <...:...:...>
        elif badge.startswith("<") and badge.endswith(">"):
            parts = badge.strip("<>").split(":")
            if len(parts) == 3 and parts[2].isdigit():
                emoji_id = int(parts[2])
                matched_emoji = self.bot.get_emoji(emoji_id)
                if not matched_emoji:
                    try:
                        matched_emoji = await self.bot.fetch_emoji(emoji_id)
                    except Exception:
                        pass
                if matched_emoji:
                    badge = str(matched_emoji)
                elif badge.startswith("<:"):
                    badge = f"<a:{parts[1]}:{parts[2]}>"

        # 3. Nếu người dùng nhập tên Emoji (Ví dụ: lacdit hoặc :lacdit:)
        else:
            clean_name = badge.strip(":").strip().lower()
            all_emojis = list(self.bot.emojis)
            matched_emoji = next((e for e in all_emojis if e.name.lower() == clean_name), None)
            if not matched_emoji:
                for guild in self.bot.guilds:
                    matched_emoji = next((e for e in guild.emojis if e.name.lower() == clean_name), None)
                    if matched_emoji:
                        break
            if matched_emoji:
                badge = str(matched_emoji)

        eco.set_masoi_custom_badge(member.id, badge)
        await self.refresh_player_badge_lobbies(member.id)
        await ctx.send(f"🎖️ **Đã cài đặt huy hiệu tự chọn thành công cho {member.mention}!**\n> Hiển thị: {badge} **{member.display_name}**")

    @commands.command(
        name="removemasoibadge",
        aliases=["delbadge", "delmasoibadge", "removebadge", "huyhuyhieu"],
        brief="[Admin/Owner] Xóa huy hiệu tự chọn của người chơi trong Ma Sói.",
        usage="removemasoibadge @user",
        hidden=True,
    )
    async def removemasoibadge_cmd(self, ctx: commands.Context, member: discord.Member):
        is_admin = False
        if hasattr(ctx.author, "guild_permissions"):
            perms = ctx.author.guild_permissions
            is_admin = perms.administrator or perms.manage_guild
        is_owner = await self.bot.is_owner(ctx.author)

        if not (is_admin or is_owner):
            await ctx.send("❌ Chỉ Quản trị viên hoặc Bot Owner mới có quyền dùng lệnh này!")
            return

        eco = self.get_economy()
        if not eco:
            await ctx.send("❌ Không kết nối được Database!")
            return

        eco.remove_masoi_custom_badge(member.id)
        await self.refresh_player_badge_lobbies(member.id)
        await ctx.send(f"⭕ **Đã xóa huy hiệu tự chọn của {member.mention} thành công!**")

    @commands.command(
        name="masoirank",
        aliases=["masoirankboard", "masoi-rank"],
        brief="Xem Bảng Xếp Hạng Rank Ma Sói.",
        usage="masoirank [soi|solo|dan]",
    )
    async def masoirank_cmd(self, ctx: commands.Context, faction: Optional[str] = None):
        aliases = {"soi": RankFaction.WOLF, "sói": RankFaction.WOLF, "wolf": RankFaction.WOLF,
                   "solo": RankFaction.SOLO, "dan": RankFaction.VILLAGER, "dân": RankFaction.VILLAGER,
                   "villager": RankFaction.VILLAGER}
        selected = aliases.get(faction.lower()) if faction else None
        if faction and selected is None:
            await ctx.send("❌ Chọn bảng rank: `masoirank soi`, `masoirank solo` hoặc `masoirank dan`.")
            return
        await ctx.send(embed=self.build_rankboard_embed(selected), view=RankboardView(self))

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
                eco.add_money(game.host_id, MASOI_CREATE_FEE)
                refund_text = f"\n<a:muiten:1533428497098473623> Đã hoàn lại **{MASOI_CREATE_FEE:,}** {EMOJI_VND} cho Host **{game.host_name}**."

        embed = make_embed(
            title="<a:luuy:1533429265293508888> ĐÃ HỦY VÁN MA SÓI",
            description=f"Ván Ma Sói ở kênh này đã bị hủy ép buộc bởi **{stopped_by_name}**.{refund_text}",
            color=discord.Color.red()
        )
        await channel.send(embed=embed)


    # ──────────────────────────────────────────────
    #  Embed Builders
    # ──────────────────────────────────────────────

    def build_lobby_embed(self, game: MasoiGame) -> discord.Embed:
        embed = discord.Embed(
            title="<a:blink:1526231036231680082> Ma Sói — Phòng chờ ván đấu",
            color=discord.Color(0xE0A638)
        )
        embed.add_field(name="CHỦ PHÒNG", value=f"<a:key:1526234974150459593> **{game.host_name}**", inline=True)
        player_count = len(game.players)
        start_status = (
            "✅ Đã đủ người bắt đầu"
            if player_count == MASOI_PLAYER_COUNT
            else f"⏳ Cần thêm **{MASOI_PLAYER_COUNT - player_count}** người"
        )
        embed.add_field(
            name="SỐ NGƯỜI",
            value=f"**{player_count}/{MASOI_PLAYER_COUNT}**\n{start_status}",
            inline=True,
        )

        player_lines = []
        eco = self.get_economy()
        for p in game.players.values():
            custom_badge = eco.get_masoi_custom_badge(p.user_id) if eco else ""
            # Badge tùy chỉnh thay đúng emoji cánh trước tên; VIP vẫn giữ emoji riêng
            # khi người chơi không có badge tùy chỉnh (như cách hiển thị cũ).
            name_emoji = custom_badge or "<a:wing:1526230985987981393>"
            vip_tag = (
                "<a:2336vipgif:1534596901834592286> "
                if (not custom_badge and eco and eco.is_masoi_vip(p.user_id))
                else ""
            )
            if p.user_id == game.host_id:
                player_lines.append(f"{name_emoji} {vip_tag}**{p.display_name}** *(chủ phòng)*")
            else:
                player_lines.append(f"{name_emoji} {vip_tag}**{p.display_name}**")


        # Thống kê danh sách vai trò dự kiến
        roles_preview = game.preview_roles()
        role_counts: Dict[Role, int] = {}
        for r in roles_preview:
            role_counts[r] = role_counts.get(r, 0) + 1

        role_items = []
        for r, cnt in role_counts.items():
            cnt_str = f" (x{cnt})" if cnt > 1 else ""
            role_items.append(f"{r.emoji} **{r.value}**{cnt_str}")
        roles_str = " • ".join(role_items)

        role_header = (
            f"🎭 ĐỘI HÌNH VÁN NÀY ({MASOI_PLAYER_COUNT} người)"
        )

        # A full room with custom emojis can exceed Discord's 1024-char field.
        chunks, chunk = [], ""
        for line in (player_lines or ["_Chưa có người chơi nào._"]):
            if chunk and len(chunk) + len(line) + 1 > 1000:
                chunks.append(chunk)
                chunk = ""
            chunk += ("\n" if chunk else "") + line
        chunks.append(chunk)
        for index, value in enumerate(chunks):
            embed.add_field(name="NGƯỜI CHƠI" if index == 0 else "NGƯỜI CHƠI (tiếp)", value=value, inline=False)
        embed.add_field(name=role_header, value=roles_str, inline=False)

        embed.add_field(
            name="\u200b",
            value=f"<a:muiten:1533428497098473623> *Bấm **Tham gia** để vào phòng. Chủ phòng có thể bắt đầu khi đủ {MASOI_PLAYER_COUNT} người.*",
            inline=False
        )
        embed.set_footer(text=f" Phí tạo phòng: {MASOI_CREATE_FEE:,} VND (Miễn phí cho VIP)")
        return embed

    def build_settings_embed(self, game: MasoiGame) -> discord.Embed:
        s = game.settings
        mode_text = f"Đội hình cố định {MASOI_PLAYER_COUNT} người"
        desc = (
            f"⚙️ **Cấu Hình Ván Ma Sói**\n\n"
            f"• **Phân chia vai trò:** `{mode_text}`\n"
            f"• **Hiện vai trò người chết (<a:2336vipgif:1534596901834592286> VIP):** `{'Hiện ngay' if s.reveal_roles_on_death else 'Ẩn tới cuối ván'}`\n"
            f"• **Hiển thị số phiếu:** `{'Real-time' if s.vote_display == 'REALTIME' else 'Ẩn tới hết giờ'}`\n"
            f"• **Người chết chat ở kênh chơi:** `{'Cho phép' if s.dead_can_chat else 'Bị cấm chat'}`\n"
            f"• **Thời gian thảo luận (<a:2336vipgif:1534596901834592286> VIP):** `{s.discussion_time // 60} phút`\n"
            f"• **Thời gian hành động đêm (<a:2336vipgif:1534596901834592286> VIP):** `{s.night_time} giây`\n"
            f"• **Tính điểm rank:** `{'Có' if s.enable_rank else 'Không'}`\n\n"
            f"• **Thẻ sự kiện đêm:** `{'Bật' if s.enable_events else 'Tắt'}`\n\n"
            f"💡 *Bấm **🎭 Vai Trò** tại phòng chờ để xem hướng dẫn.*\n"
            f"_Bấm các nút dưới đây để thay đổi giá trị cấu hình._"
        )
        return make_embed(title="⚙️ Cài Đặt Ván Ma Sói", description=desc, color=discord.Color.purple())

    def build_vote_embed(self, game: MasoiGame, is_final: bool = False) -> discord.Embed:
        counts: Dict[int, int] = {}
        white_votes = 0
        total_votes = 0

        for voter_id, tid in game.day_votes.items():
            if game.mayor_id and voter_id == game.mayor_id:
                w = 2
            else:
                w = 1
            total_votes += w
            if tid is None:
                white_votes += w
            else:
                counts[tid] = counts.get(tid, 0) + w

        def make_bar(cnt: int, total: int) -> str:
            if total <= 0:
                return "▒▒▒▒▒▒▒▒"
            filled = int((cnt / total) * 8)
            filled = min(8, max(0, filled))
            return "█" * filled + "▒" * (8 - filled)

        lines = []
        eco = self.get_economy()
        for p in game.get_alive_players():
            c = counts.get(p.user_id, 0)
            bar = make_bar(c, total_votes) if total_votes > 0 else "▒▒▒▒▒▒▒▒"
            vip_tag = "<a:2336vipgif:1534596901834592286> " if (eco and eco.is_masoi_vip(p.user_id)) else ""
            badge = self.player_badge(p.user_id, "⚖️")
            lines.append(f"• {badge} {vip_tag}**{p.display_name}**: `{bar}` **({c} phiếu)**")

        white_bar = make_bar(white_votes, total_votes) if total_votes > 0 else "▒▒▒▒▒▒▒▒"
        lines.append(f"• 🏳️ **Phiếu trắng**: `{white_bar}` **({white_votes} phiếu)**")

        divider = "──────────────────────────────────────"

        if not is_final and game.settings.vote_display == "END_ONLY":
            names = "\n".join(f"• {self.player_label(p)}" for p in game.get_alive_players())
            desc = f"⚖️ **Đang diễn ra bỏ phiếu...**\n_(Số phiếu ẩn tới khi kết thúc)_\n\n{names}\n\n{divider}\n<:ghim:1526238405061640272> *Bấm menu bên dưới để chọn người bạn nghi ngờ.*"
        else:
            header_str = "⚖️ **KẾT QUẢ BỎ PHIẾU TREO CỔ**" if is_final else "⚖️ **DIỄN BIẾN BỎ PHIẾU REAL-TIME**"
            footer = "🔒 Bỏ phiếu đã kết thúc." if is_final else "<:ghim:1526238405061640272> *Bấm menu bên dưới để bỏ phiếu người nghi ngờ là Sói.*"
            desc = f"{header_str}\n\n" + "\n".join(lines) + f"\n\n{divider}\n{footer}"

        mayor = game.players.get(game.mayor_id)
        if mayor and mayor.is_alive:
            desc += f"\n🎩 Thị Trưởng: {self.player_label(mayor)} — phiếu x2."

        embed = discord.Embed(
            title=f"⚖️ Bỏ Phiếu Treo Cổ — Ngày {game.day_count}",
            description=desc,
            color=discord.Color(0xE0A638)
        )
        return embed

    def build_vip_embed(self, user_id: int) -> discord.Embed:
        eco = self.get_economy()
        vip_info = eco.get_masoi_vip_info(user_id) if eco else {"is_vip": False, "expires_at": 0, "last_words": ""}
        
        status_str = "<a:2336vipgif:1534596901834592286> **ĐANG KÍCH HOẠT**" if vip_info["is_vip"] else "❌ **CHƯA ĐĂNG KÝ**"
        if vip_info["expires_at"] > 0:
            exp_str = time.strftime("%H:%M %d/%m/%Y", time.localtime(vip_info["expires_at"]))
        else:
            exp_str = "Chưa có"

        last_words = vip_info["last_words"] if vip_info["last_words"] else "_Chưa thiết lập (Bấm nút bên dưới để cài đặt)_"

        desc = (
            f"<a:2336vipgif:1534596901834592286> **BẢNG ĐIỀU KHIỂN VIP MA SÓI**\n\n"
            f"• **Trạng thái VIP:** {status_str}\n"
            f"• **Hạn sử dụng:** `{exp_str}`\n"
            f"• **Lời trăn trối VIP:** {last_words}\n\n"
            f"──────────────────────────────────────\n"
            f"🎁 **ĐẶC QUYỀN VIP MA SÓI:**\n"
            f"1. 🆓 **Miễn phí 100% Phí Tạo Phòng** (Không tốn {MASOI_CREATE_FEE:,} {EMOJI_VND} khi mở bàn).\n"
            f"2. ⚙️ **Tùy chỉnh Cài Đặt Ván Premium** (Thời gian Thảo Luận, Thời gian Đêm & Hiện vai trò người chết).\n"
            f"3. 🎭 **Đặc quyền Phân Vai Tùy Chỉnh** (Mở khóa menu Custom Roles trong Cài Đặt).\n"
            f"4. <a:2336vipgif:1534596901834592286> **Huy hiệu VIP [<a:2336vipgif:1534596901834592286> VIP]** hiển thị lộng lẫy bên cạnh tên.\n"
            f"5. 💬 **Lời trăn trối cá nhân** tự động phát khi qua đời.\n\n"
            f"📌 *Liên hệ Ban Quản Trị để đăng ký kích hoạt gói VIP Ma Sói.*"
        )
        return make_embed(title="<a:2336vipgif:1534596901834592286> Thẻ VIP Ma Sói", description=desc, color=discord.Color.gold())

    def build_rankboard_embed(self, faction: Optional[RankFaction] = None) -> discord.Embed:
        eco = self.get_economy()
        if not eco:
            return make_embed(title="🏆 BẢNG XẾP HẠNG MA SÓI", description="Không kết nối được cơ sở dữ liệu.")
        factions = [faction] if faction else list(RankFaction)
        embed = make_embed(
            title=f"🏆 RANK MA SÓI — {faction.label if faction else 'SÓI / SOLO / DÂN'} (TOP 10)",
            description="Ba bảng điểm độc lập, tính từ hệ thống rank mới; lịch sử cũ được giữ riêng.",
            color=discord.Color.gold(),
        )
        for group in factions:
            rows = eco.get_masoi_leaderboard(limit=10, faction=group.value)
            lines = []
            for idx, (uid, pts, plays, wins) in enumerate(rows, 1):
                icon, tier_name = get_rank_tier(pts)
                win_rate = wins / plays * 100 if plays else 0
                lines.append(f"`#{idx}` {icon} <@{uid}> — **{pts:+d} pts** · {wins}/{plays} thắng ({win_rate:.0f}%)")
            value = "\n".join(lines) if lines else "_Chưa có ván xếp hạng cho phe này._"
            if faction:
                embed.description += "\n\n" + value
            else:
                embed.add_field(name=group.label, value=value, inline=False)
        embed.set_footer(text="Sói/Dân thắng +20 · Solo +30 · Thua −15 · Bonus khi thắng ≤10 · Điểm có thể âm")
        return embed

    # ──────────────────────────────────────────────
    #  Helper Updates
    # ──────────────────────────────────────────────

    async def update_lobby_embed(
        self,
        game: MasoiGame,
        message: discord.Message,
        view: discord.ui.View | None = None,
    ):
        """Cập nhật real-time embed phòng chờ."""
        if not message:
            return
        embed = self.build_lobby_embed(game)
        try:
            edit_kwargs = {"embed": embed}
            if view is not None:
                edit_kwargs["view"] = view
            await _safe_edit(message, **edit_kwargs)
        except Exception as e:
            logger.warning("Không thể edit lobby embed: %s", e)

    async def update_vote_embed(self, game: MasoiGame, message: discord.Message):
        """Serialize live edits with badge refresh and final vote closure."""
        if not message:
            return
        day = game.day_count
        async with ui_lock(game, "vote"):
            if game.phase != GamePhase.DAY_VOTE or game.day_count != day:
                return
            view = getattr(game, "day_vote_view", None)
            if view and (view.day != day or view.is_finished()):
                return
            try:
                if view:
                    view.refresh_badges()
                    await _safe_edit(message, embed=self.build_vote_embed(game), view=view)
                else:
                    await _safe_edit(message, embed=self.build_vote_embed(game))
            except Exception as e:
                logger.warning("Không thể edit vote embed: %s", e)

    async def update_witch_dm(self, game: MasoiGame):
        """Do not let a pending wolf edit restore the save menu over poison."""
        night = game.night_count
        async with ui_lock(game, "witch"):
            if not game.accepts_night_actions(night) or not game.witch_dm_message:
                return
            if (game.witch_view and (game.witch_view.is_finished() or not isinstance(game.witch_view, NightWitchView))):
                return
            witch_p = game.get_player_by_role(Role.WITCH)
            if not witch_p or witch_p.witch_save_used or (witch_p.user_id, ActionKind.WITCH_SAVE) in game._night_intents:
                return
            victim_id = game.resolve_wolf_target()
            victim_p = game.players.get(victim_id)
            v_name = victim_p.display_name if victim_p else "Không ai"
            embed = discord.Embed(
                title=f"🌙 Đêm {night} — Lượt của Phù Thủy",
                description=f"Bầy Sói đang nhắm cắn: **{v_name}**.\nDùng **BÌNH CỨU**? Còn **{remaining_night_seconds(game)} giây**.",
                color=discord.Color(0xE0A638),
            )
            previous = game.witch_view
            view = NightWitchView(game, witch_p.user_id, victim_id)
            game.witch_view = view
            try:
                await game.witch_dm_message.edit(embed=embed, view=view)
            except Exception as e:
                # Keep the previously delivered controls usable when an optional refresh fails.
                view.stop()
                game.witch_view = previous
                logger.warning("Không thể cập nhật Witch DM: %s", e)
            else:
                if previous:
                    previous.stop()

    async def close_witch_dm(self, game: MasoiGame):
        async with ui_lock(game, "witch"):
            message = game.witch_dm_message
            result = game._night_result
            if not message or result is None:
                return
            outcomes = [text for _, kind, text in result.outcomes if kind in (ActionKind.WITCH_SAVE.value, ActionKind.WITCH_POISON.value)]
            embed = discord.Embed(title=f"🧪 Kết Quả Phù Thủy — Đêm {result.night}", description="Đêm đã kết thúc.\n" + ("\n".join(outcomes) or "Bạn không xác nhận dùng bình trong đêm này."), color=discord.Color.gold())
            try:
                await message.edit(embed=embed, view=None)
            except Exception:
                logger.warning("Không thể đóng Witch DM đêm %s", result.night)

    async def update_night_result_dm(self, message, result: Optional[str], label: str):
        if not message or not result:
            return
        try:
            embed = message.embeds[0] if message.embeds else None
            if embed is None:
                embed = discord.Embed(title=label, color=discord.Color.gold())
            if not embed.fields:
                embed.add_field(name="\u200b", value=f"{label}: {result}", inline=False)
                await message.edit(embed=embed, view=None)
            else:
                embed.set_field_at(
                    len(embed.fields) - 1,
                    name="\u200b",
                    value=f"──────────────────────────────────────\n{label}: {result}",
                    inline=False,
                )
                await message.edit(embed=embed, view=None)
        except Exception as e:
            logger.warning("Không thể gửi kết quả đêm qua DM: %s", e)

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
                except discord.Forbidden:
                    logger.warning("Bot thiếu quyền 'Manage Messages' để xoá tin nhắn của người chết!")
                except Exception as e:
                    logger.warning("Không thể xoá tin nhắn người chết: %s", e)

    async def get_or_fetch_user(self, user_id: int) -> Optional[discord.User]:
        user = self.bot.get_user(user_id)
        if not user:
            try:
                user = await self.bot.fetch_user(user_id)
            except Exception:
                user = None
        return user

    async def sync_channel_permissions(self, game: MasoiGame, channel: discord.TextChannel):
        """Cập nhật quyền cấm chat ở kênh chính cho người đã chết."""
        if game.settings.dead_can_chat or not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild
        for p in game.players.values():
            if not p.is_alive:
                member = guild.get_member(p.user_id)
                if not member:
                    try:
                        member = await guild.fetch_member(p.user_id)
                    except Exception:
                        member = None
                if member:
                    try:
                        if p.user_id not in game.channel_permission_snapshots:
                            game.channel_permission_snapshots[p.user_id] = copy.deepcopy(
                                channel.overwrites.get(member)
                            )
                        # Persist the original overwrite before touching Discord permissions.
                        self.checkpoint_game(game)
                        muted = copy.deepcopy(channel.overwrites.get(member)) or discord.PermissionOverwrite()
                        muted.send_messages = False
                        await channel.set_permissions(member, overwrite=muted)
                    except discord.Forbidden:
                        logger.warning("Bot thiếu quyền 'Manage Permissions' để cấm chat người chết!")
                    except Exception as e:
                        logger.warning("Không thể set_permissions cho người chết: %s", e)

    async def restore_channel_permissions(self, game: MasoiGame, channel: discord.TextChannel):
        """Khôi phục lại quyền chat bình thường khi ván đấu kết thúc."""
        key = f"{game.guild_id}-{game.channel_id}"
        if (game.phase == GamePhase.GAME_END and self.active_games.get(key) is not game
                and not getattr(game, "recovering", False) and not game.rank_settled):
            # Explicitly cancelled sessions must not be replayed as ranked wins on restart.
            game.winner_faction = None
            game.checkpoint()
        if not isinstance(channel, discord.TextChannel) or not game.channel_permission_snapshots:
            if game.phase == GamePhase.GAME_END and not game.winner_faction and not getattr(game, "recovering", False):
                self.retire_snapshot(game)
            return

        guild = channel.guild
        snapshots = dict(game.channel_permission_snapshots)
        for user_id, overwrite in snapshots.items():
            member = guild.get_member(user_id)
            if not member:
                try:
                    member = await guild.fetch_member(user_id)
                except Exception:
                    member = None
            if member:
                try:
                    await channel.set_permissions(member, overwrite=overwrite)
                    game.channel_permission_snapshots.pop(user_id, None)
                    self.checkpoint_game(game)
                except Exception as e:
                    logger.warning("Không thể khôi phục permission cho user %s: %s", user_id, e)

    # ──────────────────────────────────────────────
    #  Core State Machine Flow
    # ──────────────────────────────────────────────
