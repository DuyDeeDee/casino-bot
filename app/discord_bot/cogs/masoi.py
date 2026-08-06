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
        task = asyncio.create_task(self.cog.start_game(self.game, interaction.message))
        # Đảm bảo exception từ task không bị nuốt im lặng
        task.add_done_callback(
            lambda t: logger.error("Lỗi nghiêm trọng khi khởi động ván Ma Sói: %s", t.exception(), exc_info=t.exception())
            if not t.cancelled() and t.exception() else None
        )

    @discord.ui.button(label="Cài đặt", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="masoi_settings")
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ Host mới có quyền truy cập Cài Đặt!", ephemeral=True)
            return

        view = SettingsView(self.game, self.cog, interaction.message)
        embed = self.cog.build_settings_embed(self.game)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Vai Trò", style=discord.ButtonStyle.secondary, emoji="🎭", custom_id="masoi_roles_info")
    async def roles_info_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        desc = (
            "🎭 **HƯỚNG DẪN CHI TIẾT CÁC VAI TRÒ TRONG MA SÓI**\n\n"
            "🐺 **PHE SÓI (WEREWOLF TEAM)**\n"
            "• 🐺 **Sói Thường**: Mỗi đêm bỏ phiếu cắn 1 người. Đừng để lộ thân phận ban ngày!\n"
            "• 🐺🔮 **Sói Tiên Tri**: Cùng cắn với bầy Sói và được soi 1 người để biết chính xác vai trò.\n"
            "• 🐺🩸 **Sói Cuồng Sát**: Khi bị loại, bầy Sói phẫn nộ và cắn liền 2 người ở đêm tiếp theo.\n\n"
            "👥 **PHE DÂN LÀNG (VILLAGER TEAM)**\n"
            "• 👤 **Dân Thường**: Dùng trí tuệ và tranh luận ban ngày để tìm ra bầy Sói.\n"
            "• 🎩 **Thị Trưởng**: Phiếu bầu ban ngày tính x2. Khi qua đời được chọn người kế nhiệm.\n"
            "• 🔮 **Tiên Tri**: Mỗi đêm chọn 1 người để soi phe (Sói hay Dân).\n"
            "• 🔮✨ **Tiên Tri Tập Sự**: Khi Tiên Tri chính qua đời, kế thừa trở thành Tiên Tri mới từ đêm sau.\n"
            "• 🛡️ **Bảo Vệ**: Mỗi đêm chọn 1 người để bảo vệ khỏi bị Sói cắn (không chọn trùng 2 đêm liền).\n"
            "• 🧪 **Phù Thủy**: Có 1 bình Cứu (hồi sinh) và 1 bình Độc (giết người), mỗi bình dùng 1 lần/ván.\n"
            "• 💃 **Vũ Nữ**: Mỗi đêm 'thăm' 1 người để phong tỏa (roleblock) toàn bộ kỹ năng đêm của người đó.\n"
            "• 🏹 **Thợ Săn**: Khi bị loại (bị cắn hoặc treo cổ), được chọn kéo theo 1 người bắn gục.\n"
            "• 👁️ **Thám Tử**: Mỗi đêm chọn 2 người chơi để kiểm tra xem có ít nhất 1 Sói hay không.\n"
            "• 🐺👤 **Bán Nguyệt**: Thuộc phe Dân và thắng cùng Dân, nhưng bị Tiên Tri soi ra là 'SÓI'.\n"
            "• 🌕 **Kẻ Bị Nguyền**: Ban đầu là Dân. Nếu bị Sói cắn ban đêm, biến thành Sói từ đêm sau.\n"
            "• 👴 **Già Làng**: Có 2 mạng trước đòn cắn của Sói (lần 1 bị cắn không chết).\n"
            "• 💘 **Thần Tình Yêu**: Đêm 1 ghép 2 Tình Nhân (1 người chết, người kia chết theo).\n\n"
            "🃏 **PHE ĐỘC LẬP (INDEPENDENT TEAM)**\n"
            "• 🃏 **Kẻ Ngốc**: Thắng ngay lập tức nếu bị dân làng treo cổ ban ngày!\n"
            "• 🔪 **Sát Thủ**: Mỗi đêm giết 1 người, miễn nhiễm cắn ban đêm. Thắng khi độc chiếm bàn cờ!\n\n"
            "──────────────────────────────────────\n"
            "_Danh sách vai trò xuất hiện sẽ tự động điều chỉnh theo số lượng người chơi._"
        )
        embed = make_embed(title="🎭 Các Vai Trò Ma Sói", description=desc, color=discord.Color.purple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        logger.error("LobbyView error on %s: %s", item, error, exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi. Vui lòng thử lại!", ephemeral=True)
            else:
                await interaction.followup.send("❌ Đã xảy ra lỗi. Vui lòng thử lại!", ephemeral=True)
        except Exception:
            pass

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
        self.btn_custom_roles.label = f"Phân vai: {'Tự động ✅' if s.role_setup_mode == 'AUTO' else 'Tùy chỉnh ⚙️'}"

    async def check_vip_host(self, interaction: discord.Interaction, feature_name: str) -> bool:
        eco = self.cog.get_economy()
        if eco and not eco.is_masoi_vip(interaction.user.id):
            await interaction.response.send_message(
                f"❌ **TÍNH NĂNG CHỈ DÀNH CHO VIP HOST!**\n"
                f"Thay đổi **{feature_name}** chỉ dành cho Host có gói VIP Ma Sói.\n"
                f"👉 Dùng lệnh **`!masoi vip`** để nâng cấp gói VIP!",
                ephemeral=True
            )
            return False
        return True

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=0)
    async def btn_reveal(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_vip_host(interaction, "Hiện vai trò người chết"):
            return
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
        if not await self.check_vip_host(interaction, "Thời gian thảo luận"):
            return
        self.game.settings.cycle_discussion_time()
        self.cog.save_game_settings(self.game)
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def btn_night_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self.check_vip_host(interaction, "Thời gian đêm"):
            return
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

    @discord.ui.button(style=discord.ButtonStyle.primary, emoji="🎭", row=3)
    async def btn_custom_roles(self, interaction: discord.Interaction, button: discord.ui.Button):
        view = CustomRolesConfigView(self.game, self.cog, self, self.lobby_message)
        embed = view.get_embed()
        await interaction.response.edit_message(embed=embed, view=view)

    @discord.ui.button(label="Lưu & Quay Lại Lobby", style=discord.ButtonStyle.success, emoji="💾", row=4)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
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
            (Role.MAYOR, "Thị Trưởng"),
            (Role.SEER, "Tiên Tri"),
            (Role.APPRENTICE_SEER, "Tiên Tri Tập Sự"),
            (Role.GUARD, "Bảo Vệ"),
            (Role.WITCH, "Phù Thủy"),
            (Role.HARLOT, "Vũ Nữ"),
            (Role.HUNTER, "Thợ Săn"),
            (Role.CURSED, "Kẻ Bị Nguyền"),
            (Role.ELDER, "Già Làng"),
            (Role.CUPID, "Thần Tình Yêu"),
            (Role.LYCAN, "Bán Nguyệt"),
            (Role.INVESTIGATOR, "Thám Tử"),
            (Role.TANNER, "Kẻ Ngốc"),
            (Role.SERIAL_KILLER, "Sát Thủ"),
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
        btn_mode_label = f"Chế độ hiện tại: {'Tự Động (AUTO) ✅' if s.role_setup_mode == 'AUTO' else 'Tùy Chỉnh (CUSTOM) ⚙️'}"
        self.btn_toggle_mode = discord.ui.Button(label=btn_mode_label, style=discord.ButtonStyle.primary, row=2)
        self.btn_toggle_mode.callback = self.toggle_mode_callback
        self.add_item(self.btn_toggle_mode)

        # Button Quay lại Settings
        btn_back = discord.ui.Button(label="Quay lại Cài Đặt", style=discord.ButtonStyle.secondary, emoji="⬅️", row=2)
        btn_back.callback = self.back_callback
        self.add_item(btn_back)

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
            f"• **Chế độ phân vai:** `{mode_str}`\n"
            f"• **Số lượng Sói cài đặt:** `{s.custom_wolf_count} Sói`\n"
            f"• **Các vai trò đặc biệt đã chọn:**\n{roles_text}\n\n"
            f"📌 *Lưu ý: Nếu số vai trò cài đặt ít hơn số người chơi trong phòng, các vị trí còn lại sẽ tự động là **Dân Thường**.*"
        )
        return make_embed(title="⚙️ Tùy Chỉnh Vai Trò Ván Đấu", description=desc, color=discord.Color.purple())

    async def check_vip_host(self, interaction: discord.Interaction) -> bool:
        eco = self.cog.get_economy()
        if eco and not eco.is_masoi_vip(interaction.user.id):
            await interaction.response.send_message(
                "❌ **TÍNH NĂNG CHỈ DÀNH CHO VIP HOST!**\n"
                "Tính năng **Tùy Chỉnh Vai Trò (`CUSTOM`)** chỉ dành cho Host có gói VIP Ma Sói.\n"
                "👉 Dùng lệnh **`!masoi vip`** để nâng cấp gói VIP!",
                ephemeral=True
            )
            self.game.settings.role_setup_mode = "AUTO"
            return False
        return True

    async def wolves_callback(self, interaction: discord.Interaction):
        if not await self.check_vip_host(interaction):
            return
        val = int(self.select_wolves.values[0])
        self.game.settings.custom_wolf_count = val
        self.game.settings.role_setup_mode = "CUSTOM"
        self.btn_toggle_mode.label = "Chế độ hiện tại: Tùy Chỉnh (CUSTOM) ⚙️"
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def roles_callback(self, interaction: discord.Interaction):
        if not await self.check_vip_host(interaction):
            return
        selected = self.select_roles.values
        self.game.settings.custom_special_roles = selected
        self.game.settings.role_setup_mode = "CUSTOM"
        self.btn_toggle_mode.label = "Chế độ hiện tại: Tùy Chỉnh (CUSTOM) ⚙️"
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def toggle_mode_callback(self, interaction: discord.Interaction):
        if not await self.check_vip_host(interaction):
            return
        s = self.game.settings
        s.role_setup_mode = "CUSTOM" if s.role_setup_mode == "AUTO" else "AUTO"
        self.btn_toggle_mode.label = f"Chế độ hiện tại: {'Tự Động (AUTO) ✅' if s.role_setup_mode == 'AUTO' else 'Tùy Chỉnh (CUSTOM) ⚙️'}"
        self.cog.save_game_settings(self.game)
        await interaction.response.edit_message(embed=self.get_embed(), view=self)

    async def back_callback(self, interaction: discord.Interaction):
        self.parent_view.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self.parent_view)


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

        if hasattr(self.game, "cog") and self.game.cog:
            await self.game.cog.update_witch_dm(self.game)


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
            seer_p = self.game.players.get(self.seer_id)
            if seer_p and seer_p.is_roleblocked:
                res_str = "❌ **Kỹ năng của bạn đã bị phong tỏa đêm nay!** (Do bị Vũ Nữ ghé thăm)"
            elif target_p.is_wolf or target_p.role == Role.LYCAN:
                res_str = f"🐺 **{target_p.display_name}** là **SÓI**!"
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


class NightHarlotView(discord.ui.View):
    """View Ephemeral chọn 1 người để phong tỏa kỹ năng cho Vũ Nữ."""
    def __init__(self, game: MasoiGame, harlot_id: int):
        super().__init__(timeout=game.settings.night_time)
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
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        self.game.night_harlot_target = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Đã ghi nhận:** 'thăm' **{name}** (chặn kỹ năng đêm)", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightInvestigatorView(discord.ui.View):
    """View Ephemeral chọn 2 người chơi để kiểm tra có Sói không cho Thám Tử."""
    def __init__(self, game: MasoiGame, inv_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.inv_id = inv_id

        options = []
        for p in game.get_alive_players():
            if p.user_id != inv_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="👁️"))

        if options:
            self.select = discord.ui.Select(
                placeholder="👁️ Chọn đúng 2 người chơi để kiểm tra...",
                min_values=min(2, len(options)),
                max_values=min(2, len(options)),
                options=options[:25],
                row=0
            )
            self.select.callback = self.select_callback
            self.add_item(self.select)

            self.confirm_btn = discord.ui.Button(label="Xác nhận kiểm tra", style=discord.ButtonStyle.primary, row=1)
            self.confirm_btn.callback = self.confirm_callback
            self.add_item(self.confirm_btn)

    async def select_callback(self, interaction: discord.Interaction):
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not hasattr(self, "select") or not self.select.values or len(self.select.values) < 2:
            await interaction.response.send_message("❌ Vui lòng chọn đúng 2 người từ danh sách trước!", ephemeral=True)
            return

        inv_p = self.game.players.get(self.inv_id)
        if inv_p and inv_p.is_roleblocked:
            res_str = "❌ **Kỹ năng của bạn đã bị phong tỏa đêm nay!** (Do bị Vũ Nữ ghé thăm)"
            name1, name2 = "Người 1", "Người 2"
        else:
            id1, id2 = int(self.select.values[0]), int(self.select.values[1])
            p1, p2 = self.game.players.get(id1), self.game.players.get(id2)
            name1 = p1.display_name if p1 else "Người 1"
            name2 = p2.display_name if p2 else "Người 2"

            has_wolf = bool(
                (p1 and (p1.is_wolf or p1.role == Role.LYCAN))
                or (p2 and (p2.is_wolf or p2.role == Role.LYCAN))
            )
            if has_wolf:
                res_str = f"⚠️ Trong **{name1}** và **{name2}** — **CÓ ÍT NHẤT 1 SÓI**!"
            else:
                res_str = f"✅ Trong **{name1}** và **{name2}** — **KHÔNG CÓ SÓI NÀO**!"

        self.game.night_investigator_result = res_str
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n✅ **Kiểm tra ({name1} & {name2}):**\n{res_str}", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class NightWolfSeerView(discord.ui.View):
    """View Ephemeral chọn người để soi vai trò chính xác cho Sói Tiên Tri."""
    def __init__(self, game: MasoiGame, wolf_seer_id: int):
        super().__init__(timeout=game.settings.night_time)
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
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        self.game.night_wolf_seer_target = target_id
        target_p = self.game.players.get(target_id)
        ws_p = self.game.players.get(self.wolf_seer_id)

        if ws_p and ws_p.is_roleblocked:
            res_str = "❌ **Kỹ năng của bạn đã bị phong tỏa đêm nay!** (Do bị Vũ Nữ ghé thăm)"
            name = target_p.display_name if target_p else "Mục tiêu"
        elif target_p:
            res_str = f"🔮 **{target_p.display_name}** có vai trò: {target_p.role.emoji} **{target_p.role.value}**"
            self.game.night_wolf_seer_result = res_str
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


class NightSerialKillerView(discord.ui.View):
    """View Ephemeral chọn mục tiêu hạ gục cho Sát Thủ Hàng Loạt."""
    def __init__(self, game: MasoiGame, sk_id: int):
        super().__init__(timeout=game.settings.night_time)
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
        self.selected_target_id = int(self.select.values[0])
        await interaction.response.defer()

    async def confirm_callback(self, interaction: discord.Interaction):
        if not self.selected_target_id and hasattr(self, "select") and self.select.values:
            self.selected_target_id = int(self.select.values[0])

        if not self.selected_target_id:
            await interaction.response.send_message("❌ Vui lòng chọn 1 người từ danh sách trước!", ephemeral=True)
            return

        target_id = self.selected_target_id
        self.game.night_serial_killer_target = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()

        embed = interaction.message.embeds[0] if interaction.message.embeds else None
        if embed:
            divider = "──────────────────────────────────────"
            embed.add_field(name="\u200b", value=f"{divider}\n🔪 **Đã ghi nhận:** nhắm hạ gục **{name}**", inline=False)

        await interaction.response.edit_message(embed=embed, view=None)


class MayorSuccessionView(discord.ui.View):
    """View Ephemeral cho Thị Trưởng qua đời chọn người kế nhiệm."""
    def __init__(self, game: MasoiGame, mayor_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.mayor_id = mayor_id
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
            if target_p.role == Role.WOLF_CUB:
                self.game.wolf_fury_pending = True
                self.game.record_log("WOLF_CUB_RAGE", actor_id=target_p.user_id, result="Sói Cuồng Sát bị Thợ Săn bắn gục, bầy Sói sục sôi cuồng nộ cho đêm sau!")
            if getattr(target_p, "lover_id", None) and target_p.lover_id in self.game.players:
                lover_p = self.game.players[target_p.lover_id]
                if lover_p.is_alive:
                    lover_p.is_alive = False
                    self.game.record_log("LOVER_DEATH", target_id=lover_p.user_id, result="Chết vì đau thương do tình nhân bị Thợ Săn bắn")
                    if lover_p.role == Role.WOLF_CUB:
                        self.game.wolf_fury_pending = True
                        self.game.record_log("WOLF_CUB_RAGE", actor_id=lover_p.user_id, result="Sói Cuồng Sát qua đời do tình nhân bị Thợ Săn bắn, bầy Sói sục sôi cuồng nộ cho đêm sau!")

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

    async def on_error(self, interaction: discord.Interaction, error: Exception, item) -> None:
        logger.error("DayDiscussionView error on %s: %s", item, error, exc_info=error)
        try:
            if not interaction.response.is_done():
                await interaction.response.send_message("❌ Đã xảy ra lỗi. Vui lòng thử lại!", ephemeral=True)
        except Exception:
            pass


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


MASOI_CREATE_FEE = 2  # 2 Thỏi vàng (Credits)


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
        brief="Tạo phòng chờ chơi game Ma Sói (Werewolf). Phí tạo phòng: 2 thỏi vàng (Miễn phí cho VIP).",
        usage="masoi",
    )
    async def masoi_cmd(self, ctx: commands.Context):
        key = f"{ctx.guild.id}-{ctx.channel.id}"
        if key in self.active_games:
            await ctx.send("❌ Đã có một ván Ma Sói đang diễn ra hoặc trong phòng chờ ở kênh này!")
            return

        eco = self.get_economy()
        is_vip = eco.is_masoi_vip(ctx.author.id) if eco else False
        if eco and not is_vip:
            balance = eco.get_entry(ctx.author.id)[2]  # Index 2 là số thỏi Vàng
            if balance < MASOI_CREATE_FEE:
                await ctx.send(
                    f"❌ **{ctx.author.display_name}**, bạn cần tối thiểu **2 thỏi vàng** để tạo phòng chờ Ma Sói!\n"
                    f"🏆 Số dư Vàng hiện tại của bạn: **{balance:,} thỏi**\n"
                    f"💡 *Mẹo: Sở hữu gói VIP Ma Sói (`!masoi vip`) để được miễn phí tạo phòng 100%!*"
                )
                return
            # Trừ phí 2 thỏi Vàng khi tạo phòng
            eco.add_credits(ctx.author.id, -MASOI_CREATE_FEE)
            msg_text = f"<a:yay:1533444499827851505> **{ctx.author.display_name}** đã trả **2 thỏi vàng** phí tạo phòng Ma Sói!"
        elif is_vip:
            msg_text = f"<a:2336vipgif:1534596901834592286> **{ctx.author.display_name}** *(<a:2336vipgif:1534596901834592286> VIP Ma Sói)* được **miễn phí tạo phòng**!"
        else:
            msg_text = f"<a:yay:1533444499827851505> **{ctx.author.display_name}** đã tạo phòng Ma Sói!"

        game = MasoiGame(ctx.guild.id, ctx.channel.id, ctx.author.id, ctx.author.display_name)
        game.settings = self.get_saved_settings(ctx.guild.id, ctx.channel.id)
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
            await ctx.send("❌ **Tính năng Lời trăn trối chỉ dành cho VIP Ma Sói!**\nHãy dùng lệnh `!masoi vip` để nâng cấp gói VIP.")
            return

        if not text:
            await ctx.send("❌ Vui lòng nhập nội dung lời trăn trối! VD: `!setquote Vĩnh biệt dân làng!`")
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
                refund_text = f"\n<a:muiten:1533428497098473623> Đã hoàn lại **2 thỏi vàng** cho Host **{game.host_name}**."

        embed = make_embed(
            title="<a:luuy:1533429265293508888> ĐÃ HỦY VÁN MA SÓI",
            description=f"Ván Ma Sói ở kênh này đã bị hủy ép buộc bởi **{stopped_by_name}**.{refund_text}",
            color=discord.Color.red()
        )
        await channel.send(embed=embed)


    async def check_and_trigger_hunter(self, game: MasoiGame, channel: discord.TextChannel):
        """Kiểm tra và kích hoạt lượt bắn kéo theo của Thợ Săn khi bị loại (hỗ trợ bắn dây chuyền)."""
        while True:
            pending_hunters = [
                p for p in game.players.values()
                if p.role == Role.HUNTER and not p.is_alive and not getattr(p, "hunter_shot_used", False)
            ]
            if not pending_hunters:
                break

            for p in pending_hunters:
                p.hunter_shot_used = True
                h_user = self.bot.get_user(p.user_id)
                view = NightHunterView(game, p.user_id)
                hunter_shot_target_id = None

                if h_user:
                    embed_hunter = discord.Embed(
                        title="🏹 Lượt của Thợ Săn — Kéo theo 1 người",
                        description=f"Bạn đã bị loại! Hãy chọn 1 người để kéo theo chết cùng. Còn **{game.settings.night_time} giây** để quyết định.",
                        color=discord.Color(0xE0A638)
                    )
                    try:
                        await h_user.send(embed=embed_hunter, view=view)
                        elapsed = 0
                        while elapsed < game.settings.night_time:
                            if view.is_finished() or game.phase == GamePhase.GAME_END:
                                break
                            await asyncio.sleep(1)
                            elapsed += 1
                        if view.is_finished():
                            hunter_shot_target_id = view.selected_target_id
                    except Exception:
                        pass

                # Thông báo kết quả ra channel chính
                if hunter_shot_target_id:
                    shot_p = game.players.get(hunter_shot_target_id)
                    if shot_p:
                        role_str = f" *({shot_p.role.emoji} {shot_p.role.value})*" if game.settings.reveal_roles_on_death else ""
                        embed_announce = discord.Embed(
                            title="🏹 Thợ Săn Kéo Theo!",
                            description=(
                                f"🏹 **{p.display_name}** dùng phát bắn cuối cùng kéo theo "
                                f"**{shot_p.display_name}**{role_str} cùng ra đi!"
                            ),
                            color=discord.Color(0xE0A638)
                        )
                        await _safe_send(channel, embed=embed_announce)
                else:
                    embed_announce = discord.Embed(
                        title="🏹 Thợ Săn",
                        description=f"🏹 **{p.display_name}** đã không dùng phát bắn cuối cùng.",
                        color=discord.Color(0xE0A638)
                    )
                    await _safe_send(channel, embed=embed_announce)


    async def check_and_trigger_mayor_succession(self, game: MasoiGame, channel: discord.TextChannel):
        """Kiểm tra nếu Thị Trưởng vừa qua đời -> Gửi DM cho Thị Trưởng chọn người kế nhiệm."""
        if game.mayor_id:
            mayor_p = game.players.get(game.mayor_id)
            if mayor_p and not mayor_p.is_alive and not getattr(mayor_p, "mayor_passed_succession", False):
                mayor_p.mayor_passed_succession = True
                m_user = await self.get_or_fetch_user(mayor_p.user_id)
                if m_user:
                    embed_mayor = discord.Embed(
                        title="🎩 Thị Trưởng Qua Đời — Truyền Ngôi Kế Nhiệm",
                        description=f"Bạn đã qua đời! Hãy chọn 1 người chơi còn sống để trao lại chiếc mũ **Thị Trưởng (Vote x2)**. Còn **{game.settings.night_time} giây** để quyết định.",
                        color=discord.Color.gold()
                    )
                    view = MayorSuccessionView(game, mayor_p.user_id)
                    try:
                        await m_user.send(embed=embed_mayor, view=view)
                        elapsed = 0
                        while elapsed < game.settings.night_time:
                            if view.is_finished() or game.phase == GamePhase.GAME_END:
                                break
                            await asyncio.sleep(1)
                            elapsed += 1
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
        eco = self.get_economy()
        for p in game.players.values():
            vip_tag = "<a:2336vipgif:1534596901834592286> " if (eco and eco.is_masoi_vip(p.user_id)) else ""
            if p.user_id == game.host_id:
                player_lines.append(f"<a:wing:1526230985987981393> {vip_tag}**{p.display_name}** *(chủ phòng)*")
            else:
                player_lines.append(f"<a:wing:1526230985987981393> {vip_tag}**{p.display_name}**")

        players_str = "\n".join(player_lines) if player_lines else "_Chưa có người chơi nào._"
        divider = "──────────────────────────────────────"

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

        n_players = len(game.players)
        role_header = f"🎭 VAI TRÒ DỰ KIẾN ({n_players} người)" if n_players >= 5 else f"🎭 VAI TRÒ DỰ KIẾN (Tính mẫu 5 người)"

        embed.add_field(name="\u200b", value=divider, inline=False)
        embed.add_field(name="NGƯỜI CHƠI", value=players_str, inline=False)
        embed.add_field(name=role_header, value=roles_str, inline=False)
        embed.add_field(
            name="\u200b",
            value=f"{divider}\n<a:muiten:1533428497098473623> *Bấm **Tham gia** để vào ván, chủ phòng bấm **Bắt đầu** khi đủ 5 người trở lên.*",
            inline=False
        )
        embed.set_footer(text=" Phí tạo phòng: 2 thỏi vàng (Miễn phí cho VIP)")
        return embed

    def build_settings_embed(self, game: MasoiGame) -> discord.Embed:
        s = game.settings
        mode_text = f"Tùy Chỉnh ({s.custom_wolf_count} Sói, {len(s.custom_special_roles)} Chức năng)" if s.role_setup_mode == "CUSTOM" else "Tự Động (Theo số người)"
        desc = (
            f"⚙️ **Cấu Hình Ván Ma Sói**\n\n"
            f"• **Phân chia vai trò:** `{mode_text}`\n"
            f"• **Hiện vai trò người chết (<a:2336vipgif:1534596901834592286> VIP):** `{'Hiện ngay' if s.reveal_roles_on_death else 'Ẩn tới cuối ván'}`\n"
            f"• **Kẻ Ngốc (Tanner):** `{'Bật' if s.enable_tanner else 'Tắt'}`\n"
            f"• **Hiển thị số phiếu:** `{'Real-time' if s.vote_display == 'REALTIME' else 'Ẩn tới hết giờ'}`\n"
            f"• **Người chết chat ở thread:** `{'Cho phép' if s.dead_can_chat else 'Bị cấm chat'}`\n"
            f"• **Thời gian thảo luận (<a:2336vipgif:1534596901834592286> VIP):** `{s.discussion_time // 60} phút`\n"
            f"• **Thời gian hành động đêm (<a:2336vipgif:1534596901834592286> VIP):** `{s.night_time} giây`\n"
            f"• **Tính điểm rank:** `{'Có' if s.enable_rank else 'Không'}`\n\n"
            "_Bấm các nút dưới đây để thay đổi giá trị cấu hình._"
        )
        return make_embed(title="⚙️ Cài Đặt Ván Ma Sói", description=desc, color=discord.Color.purple())

    def build_vote_embed(self, game: MasoiGame, is_final: bool = False) -> discord.Embed:
        counts: Dict[int, int] = {}
        white_votes = 0
        total_votes = 0

        for voter_id, tid in game.day_votes.items():
            w = 2 if (game.mayor_id and voter_id == game.mayor_id) else 1
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
            lines.append(f"• ⚖️ {vip_tag}**{p.display_name}**: `{bar}` **({c} phiếu)**")

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
            f"1. 🆓 **Miễn phí 100% Phí Tạo Phòng** (Không tốn 2 Thỏi Vàng khi mở bàn).\n"
            f"2. ⚙️ **Tùy chỉnh Cài Đặt Ván Premium** (Thời gian Thảo Luận, Thời gian Đêm & Hiện vai trò người chết).\n"
            f"3. 🎭 **Đặc quyền Phân Vai Tùy Chỉnh** (Mở khóa menu Custom Roles trong Cài Đặt).\n"
            f"4. <a:2336vipgif:1534596901834592286> **Huy hiệu VIP [<a:2336vipgif:1534596901834592286> VIP]** hiển thị lộng lẫy bên cạnh tên.\n"
            f"5. 💬 **Lời trăn trối cá nhân** tự động phát khi qua đời.\n\n"
            f"📌 *Liên hệ Ban Quản Trị để đăng ký kích hoạt gói VIP Ma Sói.*"
        )
        return make_embed(title="<a:2336vipgif:1534596901834592286> Thẻ VIP Ma Sói", description=desc, color=discord.Color.gold())

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
        """Cập nhật real-time embed phòng chờ."""
        if not message:
            return
        embed = self.build_lobby_embed(game)
        try:
            await _safe_edit(message, embed=embed)
        except Exception as e:
            logger.warning("Không thể edit lobby embed: %s", e)

    async def update_vote_embed(self, game: MasoiGame, message: discord.Message):
        """Cập nhật real-time embed diễn biến bỏ phiếu."""
        if not message:
            return
        embed = self.build_vote_embed(game, is_final=False)
        try:
            await _safe_edit(message, embed=embed)
        except Exception as e:
            logger.warning("Không thể edit vote embed: %s", e)

    async def update_witch_dm(self, game: MasoiGame):
        """Cập nhật real-time tin nhắn DM của Phù Thủy khi Sói chọn mục tiêu cắn."""
        if not game.witch_dm_message or (game.witch_view and game.witch_view.is_finished()):
            return

        witch_p = game.get_player_by_role(Role.WITCH)
        if not witch_p or witch_p.witch_save_used:
            return

        victim_id = game.resolve_wolf_target()
        victim_p = game.players.get(victim_id) if victim_id else None
        v_name = victim_p.display_name if victim_p else "Không ai"

        embed = discord.Embed(
            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Phù Thủy",
            description=f"Đêm nay, bầy Sói nhắm cắn: **{v_name}**.\nBạn có muốn dùng **BÌNH CỨU** không? Còn **{game.settings.night_time} giây** để quyết định.",
            color=discord.Color(0xE0A638)
        )
        view = NightWitchView(game, witch_p.user_id, victim_id)
        game.witch_view = view
        try:
            await game.witch_dm_message.edit(embed=embed, view=view)
        except Exception as e:
            logger.warning("Không thể cập nhật Witch DM: %s", e)

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
                        await channel.set_permissions(member, send_messages=False)
                    except discord.Forbidden:
                        logger.warning("Bot thiếu quyền 'Manage Permissions' để cấm chat người chết!")
                    except Exception as e:
                        logger.warning("Không thể set_permissions cho người chết: %s", e)

    async def restore_channel_permissions(self, game: MasoiGame, channel: discord.TextChannel):
        """Khôi phục lại quyền chat bình thường khi ván đấu kết thúc."""
        if not isinstance(channel, discord.TextChannel):
            return

        guild = channel.guild
        for p in game.players.values():
            member = guild.get_member(p.user_id)
            if not member:
                try:
                    member = await guild.fetch_member(p.user_id)
                except Exception:
                    member = None
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
                # Guard: Kiểm tra xem game có bị force-stop từ bên ngoài không
                if key not in self.active_games:
                    logger.info("Game %s đã bị dừng từ bên ngoài, thoát game_loop.", key)
                    return

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
                    g_user = await self.get_or_fetch_user(guard_p.user_id)
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
                    w_user = await self.get_or_fetch_user(w.user_id)
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
                    s_user = await self.get_or_fetch_user(seer_p.user_id)
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
                    wt_user = await self.get_or_fetch_user(witch_p.user_id)
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
                        game.witch_view = view
                        try:
                            msg = await wt_user.send(embed=embed, view=view)
                            game.witch_dm_message = msg
                        except Exception:
                            pass

                # 5. Sói Tiên Tri
                wolf_seer_p = game.get_player_by_role(Role.WOLF_SEER)
                if wolf_seer_p:
                    ws_user = await self.get_or_fetch_user(wolf_seer_p.user_id)
                    if ws_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Sói Tiên Tri",
                            description=f"Chọn 1 người để soi chính xác vai trò cá nhân đêm nay. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightWolfSeerView(game, wolf_seer_p.user_id)
                        try:
                            await ws_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 6. Sát Thủ Hàng Loạt
                sk_p = game.get_player_by_role(Role.SERIAL_KILLER)
                if sk_p:
                    sk_user = await self.get_or_fetch_user(sk_p.user_id)
                    if sk_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Sát Thủ",
                            description=f"Chọn 1 nạn nhân để ra tay hạ gục đêm nay. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightSerialKillerView(game, sk_p.user_id)
                        try:
                            await sk_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 7. Vũ Nữ
                harlot_p = game.get_player_by_role(Role.HARLOT)
                if harlot_p:
                    h_user = await self.get_or_fetch_user(harlot_p.user_id)
                    if h_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Vũ Nữ",
                            description=f"Chọn 1 người để 'thăm' và phong tỏa kỹ năng đêm. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightHarlotView(game, harlot_p.user_id)
                        try:
                            await h_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 8. Thám Tử
                inv_p = game.get_player_by_role(Role.INVESTIGATOR)
                if inv_p:
                    inv_user = await self.get_or_fetch_user(inv_p.user_id)
                    if inv_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Thám Tử",
                            description=f"Chọn 2 người để kiểm tra xem có Sói hay không. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightInvestigatorView(game, inv_p.user_id)
                        try:
                            await inv_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 9. Tiên Tri Tập Sự (khi đã kế thừa)
                app_p = game.get_player_by_role(Role.APPRENTICE_SEER)
                if app_p and app_p.apprentice_promoted:
                    app_user = await self.get_or_fetch_user(app_p.user_id)
                    if app_user:
                        embed = discord.Embed(
                            title=f"<a:moon:1533444241596874792> Đêm {game.night_count} — Lượt của Tiên Tri Tập Sự (Kế Thừa)",
                            description=f"Bạn đã trở thành Tiên Tri mới! Chọn 1 người để soi phe đêm nay. Còn **{game.settings.night_time} giây** để quyết định.",
                            color=discord.Color(0xE0A638)
                        )
                        view = NightSeerView(game, app_p.user_id)
                        try:
                            await app_user.send(embed=embed, view=view)
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
                night_msg = await _safe_send(message.channel, embed=embed_night)

                # Chờ hết thời gian ban đêm
                elapsed = 0
                while elapsed < game.settings.night_time:
                    if key not in self.active_games or game.phase == GamePhase.GAME_END:
                        break
                    await asyncio.sleep(1)
                    elapsed += 1

                if key not in self.active_games or game.phase == GamePhase.GAME_END:
                    break

                try:
                    await night_msg.delete()
                except Exception:
                    pass

                # 1.5 Tính toán đêm
                game.phase = GamePhase.NIGHT_RESOLVE
                night_deaths = game.resolve_night()
                await self.check_and_trigger_hunter(game, message.channel)
                await self.check_and_trigger_mayor_succession(game, message.channel)

                # Thông báo DM cho Kẻ Bị Nguyền vừa biến thành Sói đêm này
                for p in game.players.values():
                    if (
                        p.is_alive
                        and p.role == Role.CURSED
                        and p.is_cursed_converted
                        and not p.cursed_notified
                    ):
                        p.cursed_notified = True
                        cursed_user = await self.get_or_fetch_user(p.user_id)
                        if cursed_user:
                            wolf_teammates = [
                                w.display_name
                                for w in game.get_alive_wolves()
                                if w.user_id != p.user_id
                            ]
                            teammates_str = (
                                ", ".join(f"**{n}**" for n in wolf_teammates)
                                if wolf_teammates else "*Bạn là Sói duy nhất còn sống!*"
                            )
                            try:
                                await cursed_user.send(
                                    f"🌕🐺 **Bạn đã bị Nguyền và biến thành SÓI!**\n"
                                    f"> Bầy Sói đã cắn bạn đêm qua \u2014 từ đêm sau bạn là **SÓI** rồi!\n"
                                    f"> 👥 Đồng đội Sói: {teammates_str}"
                                )
                            except Exception:
                                pass

                # ── BƯỚC 2: CÔNG BỐ BAN NGÀY ──
                game.phase = GamePhase.DAY_ANNOUNCE
                game.start_day()
                await self.sync_channel_permissions(game, message.channel)

                if night_deaths:
                    death_names = []
                    quotes = []
                    eco = self.get_economy()
                    for uid in night_deaths:
                        p = game.players[uid]
                        if game.settings.reveal_roles_on_death:
                            death_names.append(f"<:die:1533444731000848415> **{p.display_name}** *({p.role.emoji} {p.role.value})*")
                        else:
                            death_names.append(f"<:die:1533444731000848415> **{p.display_name}**")

                        if eco:
                            vip_info = eco.get_masoi_vip_info(p.user_id)
                            if vip_info["is_vip"] and vip_info["last_words"]:
                                quotes.append(f"💬 *Lời trăn trối của <a:2336vipgif:1534596901834592286> **{p.display_name}**: \"{vip_info['last_words']}\"*")

                    quote_str = ("\n\n" + "\n".join(quotes)) if quotes else ""
                    day_msg_text = "Đêm qua trôi qua đầy đau thương... Các nạn nhân đã ra đi:\n" + "\n".join(death_names) + quote_str
                else:
                    day_msg_text = "<a:yay:1533444499827851505> Đêm qua trôi qua thật bình yên, không có ai qua đời!"

                embed_announce = discord.Embed(
                    title=f"<a:yay:1533444499827851505> Ban Ngày — Ngày {game.day_count}",
                    description=f"{day_msg_text}\n\n{divider}\n💬 Mọi người hãy cùng trao đổi và thảo luận tại kênh này!",
                    color=discord.Color(0xE0A638)
                )
                await _safe_send(message.channel, embed=embed_announce)

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
                disc_msg = await _safe_send(message.channel, embed=disc_embed, view=disc_view)

                # Chờ thảo luận
                elapsed = 0
                while elapsed < game.settings.discussion_time:
                    if disc_view.is_finished() or key not in self.active_games or game.phase == GamePhase.GAME_END:
                        break
                    await asyncio.sleep(1)
                    elapsed += 1

                if key not in self.active_games or game.phase == GamePhase.GAME_END:
                    break

                try:
                    await disc_msg.delete()
                except Exception:
                    pass

                # ── BƯỚC 4: BỎ PHIẾU TREO CỔ ──
                game.phase = GamePhase.DAY_VOTE
                vote_embed = self.build_vote_embed(game, is_final=False)
                vote_view = DayVoteView(game, self)
                vote_msg = await _safe_send(message.channel, embed=vote_embed, view=vote_view)

                # Chờ tất cả mọi người bỏ phiếu xong hoặc hết thời gian đếm ngược
                elapsed = 0
                while elapsed < game.settings.night_time:
                    if vote_view.is_finished() or len(game.day_votes) >= len(game.get_alive_players()) or key not in self.active_games or game.phase == GamePhase.GAME_END:
                        break
                    await asyncio.sleep(1)
                    elapsed += 1

                if key not in self.active_games or game.phase == GamePhase.GAME_END:
                    break

                # ── BƯỚC 5: XỬ LÝ BỎ PHIẾU ──
                game.phase = GamePhase.DAY_RESOLVE
                vote_final_embed = self.build_vote_embed(game, is_final=True)
                try:
                    await vote_msg.edit(embed=vote_final_embed, view=None)
                except Exception:
                    pass

                executed_id = game.resolve_day_vote()
                await self.check_and_trigger_hunter(game, message.channel)
                await self.check_and_trigger_mayor_succession(game, message.channel)
                await self.sync_channel_permissions(game, message.channel)

                if executed_id:
                    p = game.players[executed_id]
                    if game.settings.reveal_roles_on_death:
                        exec_text = f"<a:huyay:1533445376563089448> **{p.display_name}** đã bị dân làng xử tử trên giàn treo cổ! *(Vai trò: **{p.role.emoji} {p.role.value}**)*"
                    else:
                        exec_text = f"<a:huyay:1533445376563089448> **{p.display_name}** đã bị dân làng xử tử trên giàn treo cổ!"

                    eco = self.get_economy()
                    if eco:
                        vip_info = eco.get_masoi_vip_info(p.user_id)
                        if vip_info["is_vip"] and vip_info["last_words"]:
                            exec_text += f"\n\n💬 *Lời trăn trối của <a:2336vipgif:1534596901834592286> **{p.display_name}**: \"{vip_info['last_words']}\"*"
                else:
                    last_log = game.replay_logs[-1] if game.replay_logs else None
                    if last_log and last_log.event_type == "VOTE_RESULT":
                        exec_text = f"<a:huyay:1533445376563089448> Lượt bỏ phiếu kết thúc: **{last_log.result}**."
                    else:
                        exec_text = "<a:huyay:1533445376563089448> Lượt bỏ phiếu kết thúc, không ai bị xử tử."

                embed_exec = discord.Embed(
                    title="<a:huyay:1533445376563089448> Kết Quả Xử Tử",
                    description=f"{exec_text}\n\n{divider}",
                    color=discord.Color(0xE0A638)
                )
                await _safe_send(message.channel, embed=embed_exec)

                # Kiểm tra thắng sau bỏ phiếu
                if game.check_win_condition():
                    game.phase = GamePhase.GAME_END
                    break

            # ── BƯỚC 6: KẾT THÚC GAME ──
            await self.end_game(game, message)

        except asyncio.CancelledError:
            # Game bị cancel chủ động (thường do force_stop_game)
            logger.info("Game loop %s bị cancel.", key)
        except discord.HTTPException as e:
            logger.error("Discord API error trong game loop %s: %s", key, e, exc_info=True)
            try:
                embed_err = make_embed(
                    title="<a:luuy:1533429265293508888> ĐÃ XẢY RA LỖI KẾT NỐI",
                    description=(
                        f"Ván Ma Sói gặp sự cố kết nối với Discord và đã bị hủy!\n"
                        f"*(Lỗi: {e.status} — {e.text})*\n\n"
                        f"Dùng `!masoi` để tạo ván mới."
                    ),
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed_err)
            except Exception:
                pass
        except Exception as e:
            logger.exception("Lỗi không xác định trong game loop (Guild %s, Channel %s):", game.guild_id, game.channel_id)
            try:
                embed_err = make_embed(
                    title="<a:luuy:1533429265293508888> ĐÃ XẢY RA LỖI HỆ THỐNG",
                    description=(
                        f"Ván Ma Sói gặp sự cố không mong muốn và đã bị hủy!\n"
                        f"`Chi tiết lỗi: {type(e).__name__}: {e}`\n\n"
                        f"Dùng `!masoi` để tạo ván mới."
                    ),
                    color=discord.Color.red()
                )
                await message.channel.send(embed=embed_err)
            except Exception:
                pass
        finally:
            # Luôn dọn sạch active_games để kênh không bị lock
            if key in self.active_games:
                del self.active_games[key]
                logger.info("Đã dọn sạch active_games cho key %s.", key)

    async def end_game(self, game: MasoiGame, message: discord.Message):
        game.phase = GamePhase.GAME_END
        game.end_time = float(asyncio.get_event_loop().time())

        # Cộng điểm rank
        rank_pts = game.calculate_rank_points()
        eco = self.get_economy()
        if eco and game.settings.enable_rank:
            for uid, pts in rank_pts.items():
                p = game.players[uid]
                is_win = (
                    (p.role.faction == game.winner_faction)
                    or (uid == game.tanner_winner_id)
                    or (p.is_cursed_converted and game.winner_faction == Faction.WEREWOLF)
                )
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
