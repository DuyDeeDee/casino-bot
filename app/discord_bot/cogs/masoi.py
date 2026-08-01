# coding: utf-8
"""
Ma Sói (Werewolf) Discord Cog
Xử lý toàn bộ UI (Buttons, Embeds, Dropdowns, Ephemeral) và Luồng Ván đấu (State Machine).
"""

from __future__ import annotations

import asyncio
import logging
from typing import Dict, Optional

import discord
from discord.ext import commands

from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.masoi_engine import (
    Faction,
    GamePhase,
    MasoiGame,
    MasoiPlayer,
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

    @discord.ui.button(label="Tham Gia", style=discord.ButtonStyle.success, emoji="🧑", custom_id="masoi_join")
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

    @discord.ui.button(label="Rời Đi", style=discord.ButtonStyle.danger, emoji="🚪", custom_id="masoi_leave")
    async def leave_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user = interaction.user
        if not self.game.remove_player(user.id):
            await interaction.response.send_message("❌ Bạn chưa tham gia phòng chờ!", ephemeral=True)
            return

        await interaction.response.send_message("👋 Bạn đã rời khỏi phòng chờ.", ephemeral=True)
        await self.cog.update_lobby_embed(self.game, interaction.message)

    @discord.ui.button(label="Bắt Đầu", style=discord.ButtonStyle.primary, emoji="🚀", custom_id="masoi_start")
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

    @discord.ui.button(label="Cài Đặt", style=discord.ButtonStyle.secondary, emoji="⚙️", custom_id="masoi_settings")
    async def settings_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.game.host_id:
            await interaction.response.send_message("❌ Chỉ Host mới có quyền truy cập Cài Đặt!", ephemeral=True)
            return

        view = SettingsView(self.game, self.cog, interaction.message)
        embed = self.cog.build_settings_embed(self.game)
        await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @discord.ui.button(label="Hủy Ván", style=discord.ButtonStyle.secondary, emoji="🛑", custom_id="masoi_cancel")
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
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=0)
    async def btn_tanner(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_tanner()
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=1)
    async def btn_vote(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_vote_display()
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=1)
    async def btn_chat(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_dead_chat()
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def btn_disc_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_discussion_time()
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=2)
    async def btn_night_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_night_time()
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(style=discord.ButtonStyle.secondary, row=3)
    async def btn_rank(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.game.settings.cycle_rank()
        self.update_button_labels()
        await interaction.response.edit_message(embed=self.cog.build_settings_embed(self.game), view=self)

    @discord.ui.button(label="Lưu & Quay Lại Lobby", style=discord.ButtonStyle.success, emoji="💾", row=3)
    async def btn_save(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.edit_message(content="✅ Đã lưu cài đặt!", embed=None, view=None)
        await self.cog.update_lobby_embed(self.game, self.lobby_message)


# ==============================================================================
#  Night Ephemeral Views
# ==============================================================================

class NightActionMainView(discord.ui.View):
    """View công khai trên kênh chính ban đêm có nút mở giao diện Ephemeral."""
    def __init__(self, game: MasoiGame, cog: "Masoi"):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.cog = cog

    @discord.ui.button(label="Hành Động Ban Đêm", style=discord.ButtonStyle.primary, emoji="🌙", custom_id="masoi_night_action_btn")
    async def night_action_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        user_id = interaction.user.id
        p = self.game.players.get(user_id)
        if not p or not p.is_alive:
            await interaction.response.send_message("😴 Bạn không tham gia ván đấu hoặc đã chết.", ephemeral=True)
            return

        if p.role == Role.GUARD:
            embed = make_embed(title="🛡️ Giao Diện Bảo Vệ", description="Hãy chọn 1 người chơi để bảo vệ khỏi bị Sói cắn đêm nay!")
            view = NightGuardView(self.game, user_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        elif p.role == Role.WOLF:
            embed = make_embed(title="🐺 Giao Diện Bầy Sói", description="Hãy chọn 1 người chơi để cắn đêm nay!")
            view = NightWolfView(self.game, user_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        elif p.role == Role.SEER:
            embed = make_embed(title="🔮 Giao Diện Tiên Tri", description="Hãy chọn 1 người chơi để soi phe!")
            view = NightSeerView(self.game, user_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        elif p.role == Role.WITCH:
            victim_id = self.game.resolve_wolf_target()
            victim_p = self.game.players.get(victim_id) if victim_id else None
            v_name = victim_p.display_name if victim_p else "Chưa có / Không ai"
            embed = make_embed(title="🧪 Giao Diện Phù Thủy", description=f"Đêm nay bầy Sói nhắm cắn: **{v_name}**.\nBạn muốn dùng bình cứu hay bình độc không?")
            view = NightWitchView(self.game, user_id, victim_id)
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

        else:
            await interaction.response.send_message("😴 Bạn không có kỹ năng ban đêm. Hãy nghỉ ngơi chờ ban ngày!", ephemeral=True)


class NightGuardView(discord.ui.View):
    """View Ephemeral chọn mục tiêu bảo vệ cho Bảo Vệ."""
    def __init__(self, game: MasoiGame, guard_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.guard_id = guard_id

        guard_p = game.players.get(guard_id)
        last_protected = guard_p.protected_last_night if guard_p else None

        options = []
        for p in game.get_alive_players():
            if p.user_id == last_protected:
                continue
            options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🛡️"))

        if options:
            select = discord.ui.Select(placeholder="🛡️ Chọn 1 người để bảo vệ...", options=options[:25])
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select: discord.ui.Select = interaction.data["values"][0]
        target_id = int(select)
        self.game.night_guard_target = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Người đã chọn"
        self.stop()
        await interaction.response.edit_message(content=f"✅ Bạn đã chọn bảo vệ **{name}** đêm nay.", view=None)


class NightWolfView(discord.ui.View):
    """View Ephemeral cho từng Sói bỏ phiếu cắn."""
    def __init__(self, game: MasoiGame, wolf_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.wolf_id = wolf_id

        options = []
        for p in game.get_alive_players():
            # Có thể cắn bất kỳ ai còn sống
            options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🐺"))

        if options:
            select = discord.ui.Select(placeholder="🐺 Chọn 1 người để cắn...", options=options[:25])
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select: discord.ui.Select = interaction.data["values"][0]
        target_id = int(select)
        self.game.night_wolf_votes[self.wolf_id] = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()
        await interaction.response.edit_message(
            content=f"✅ Đã ghi nhận lựa chọn của bạn: Cắn **{name}**.\n*(Nếu nhiều Sói chọn khác nhau, bot sẽ chốt theo đa số phiếu)*.",
            view=None
        )


class NightSeerView(discord.ui.View):
    """View Ephemeral chọn người để soi phe cho Tiên Tri."""
    def __init__(self, game: MasoiGame, seer_id: int):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.seer_id = seer_id

        options = []
        for p in game.get_alive_players():
            if p.user_id != seer_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="🔮"))

        if options:
            select = discord.ui.Select(placeholder="🔮 Chọn 1 người để soi phe...", options=options[:25])
            select.callback = self.select_callback
            self.add_item(select)

    async def select_callback(self, interaction: discord.Interaction):
        select: discord.ui.Select = interaction.data["values"][0]
        target_id = int(select)
        self.game.night_seer_target = target_id
        target_p = self.game.players.get(target_id)
        
        if target_p:
            if target_p.is_wolf:
                res_str = f"🐺 **{target_p.display_name}** là **SÓI**!"
                seer_p = self.game.players.get(self.seer_id)
                if seer_p:
                    seer_p.seer_found_wolf = True
            else:
                res_str = f"👤 **{target_p.display_name}** là **DÂN VÀNG** (không phải Sói)."
            self.game.night_seer_result = res_str
        else:
            res_str = "Không tìm thấy thông tin."

        self.stop()
        await interaction.response.edit_message(content=f"🔮 **Kết quả soi:** {res_str}", view=None)


class NightWitchView(discord.ui.View):
    """View Ephemeral cho Phù Thủy (Cứu & Độc)."""
    def __init__(self, game: MasoiGame, witch_id: int, victim_id: Optional[int]):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.witch_id = witch_id
        self.victim_id = victim_id

        witch_p = game.players.get(witch_id)
        has_save = witch_p and not witch_p.witch_save_used
        has_poison = witch_p and not witch_p.witch_poison_used

        victim_p = game.players.get(victim_id) if victim_id else None
        victim_name = victim_p.display_name if victim_p else "Không ai"

        # Nếu có nạn nhân & còn bình cứu -> Hiển thị nút cứu
        if victim_p and has_save:
            btn_save = discord.ui.Button(label=f"🧪 Cứu {victim_name}", style=discord.ButtonStyle.success)
            btn_save.callback = self.save_callback
            self.add_item(btn_save)

        btn_no_save = discord.ui.Button(label="Không dùng bình cứu", style=discord.ButtonStyle.secondary)
        btn_no_save.callback = self.no_save_callback
        self.add_item(btn_no_save)

    async def save_callback(self, interaction: discord.Interaction):
        witch_p = self.game.players.get(self.witch_id)
        if witch_p:
            witch_p.witch_save_used = True
        self.game.night_witch_save = True
        await self.show_poison_step(interaction, "✅ Bạn đã quyết định **CỨU** nạn nhân đêm nay.")

    async def no_save_callback(self, interaction: discord.Interaction):
        self.game.night_witch_save = False
        await self.show_poison_step(interaction, "👌 Bạn không dùng bình cứu đêm nay.")

    async def show_poison_step(self, interaction: discord.Interaction, prefix_msg: str):
        witch_p = self.game.players.get(self.witch_id)
        if not witch_p or witch_p.witch_poison_used:
            self.stop()
            await interaction.response.edit_message(content=f"{prefix_msg}\n*(Bạn không còn bình độc)*.", view=None)
            return

        view = NightWitchPoisonView(self.game, self.witch_id, prefix_msg)
        await interaction.response.edit_message(content=f"{prefix_msg}\n☠️ **Bạn có muốn dùng BÌNH ĐỘC đêm nay không?**", view=view)


class NightWitchPoisonView(discord.ui.View):
    def __init__(self, game: MasoiGame, witch_id: int, prefix_msg: str):
        super().__init__(timeout=game.settings.night_time)
        self.game = game
        self.witch_id = witch_id
        self.prefix_msg = prefix_msg

        options = []
        for p in game.get_alive_players():
            if p.user_id != witch_id:
                options.append(discord.SelectOption(label=p.display_name, value=str(p.user_id), emoji="☠️"))

        if options:
            select = discord.ui.Select(placeholder="☠️ Chọn 1 người để hạ độc...", options=options[:25])
            select.callback = self.poison_select_callback
            self.add_item(select)

        btn_skip = discord.ui.Button(label="Bỏ qua không dùng độc", style=discord.ButtonStyle.secondary)
        btn_skip.callback = self.skip_poison_callback
        self.add_item(btn_skip)

    async def poison_select_callback(self, interaction: discord.Interaction):
        select: discord.ui.Select = interaction.data["values"][0]
        target_id = int(select)
        witch_p = self.game.players.get(self.witch_id)
        if witch_p:
            witch_p.witch_poison_used = True
        self.game.night_witch_poison = target_id
        target_p = self.game.players.get(target_id)
        name = target_p.display_name if target_p else "Mục tiêu"
        self.stop()
        await interaction.response.edit_message(content=f"{self.prefix_msg}\n☠️ Bạn đã dùng bình độc lên **{name}**.", view=None)

    async def skip_poison_callback(self, interaction: discord.Interaction):
        self.game.night_witch_poison = None
        self.stop()
        await interaction.response.edit_message(content=f"{self.prefix_msg}\n👌 Bạn không dùng bình độc đêm nay.", view=None)


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

class Masoi(commands.Cog):
    """Cog Ma Sói (Werewolf) cho Discord Bot."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.active_games: Dict[str, MasoiGame] = {}  # key: f"{guild_id}-{channel_id}"

    def get_economy(self):
        return getattr(self.bot, "economy", None)

    # ──────────────────────────────────────────────
    #  Commands
    # ──────────────────────────────────────────────

    @commands.command(
        name="masoi",
        aliases=["werewolf", "ma-soi"],
        brief="Tạo phòng chờ chơi game Ma Sói (Werewolf).",
        usage="masoi",
    )
    async def masoi_cmd(self, ctx: commands.Context):
        key = f"{ctx.guild.id}-{ctx.channel.id}"
        if key in self.active_games:
            await ctx.send("❌ Đã có một ván Ma Sói đang diễn ra hoặc trong phòng chờ ở kênh này!")
            return

        game = MasoiGame(ctx.guild.id, ctx.channel.id, ctx.author.id, ctx.author.display_name)
        game.add_player(ctx.author.id, ctx.author.display_name)
        self.active_games[key] = game

        embed = self.build_lobby_embed(game)
        view = LobbyView(game, self)
        msg = await ctx.send(embed=embed, view=view)
        game.message_id = msg.id

        # Tự động tạo Thread thảo luận ngay bên dưới tin nhắn lobby
        try:
            thread = await msg.create_thread(
                name="💬 Bàn Luận — Ván Ma Sói",
                auto_archive_duration=60,
                reason="Thread thảo luận tự động cho ván Ma Sói"
            )
            game.thread_id = thread.id
            await thread.send(
                "💬 **Chào mừng các bạn đến với Thread Thảo Luận Ma Sói!**\n"
                "Khi ban ngày đến, mọi người chơi sẽ trao đổi tại thread này."
            )
        except Exception as e:
            logger.warning("Không thể tạo thread thảo luận: %s", e)

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
        game.phase = GamePhase.GAME_END
        if key in self.active_games:
            del self.active_games[key]

        if game.thread_id:
            thread = self.bot.get_channel(game.thread_id)
            if thread and isinstance(thread, discord.Thread):
                try:
                    await thread.send(f"🛑 **Ván đấu đã bị hủy bởi {stopped_by_name}.** Thread được đóng.")
                    await thread.edit(archived=True, locked=True)
                except Exception:
                    pass

        embed = make_embed(
            title="🛑 ĐÃ HỦY VÁN MA SÓI",
            description=f"Ván Ma Sói ở kênh này đã bị hủy ép buộc bởi **{stopped_by_name}**.",
            color=discord.Color.red()
        )
        await channel.send(embed=embed)

    # ──────────────────────────────────────────────
    #  Embed Builders
    # ──────────────────────────────────────────────

    def build_lobby_embed(self, game: MasoiGame) -> discord.Embed:
        players_str = "\n".join([f"• 🧑 **{p.display_name}**" for p in game.players.values()])
        if not players_str:
            players_str = "_Chưa có người chơi nào._"

        embed = make_embed(
            title="🌕 MA SÓI — Phòng Chờ Ván Đấu",
            description=(
                f"Host: **{game.host_name}**\n\n"
                f"**Danh sách người chơi ({len(game.players)}/20):**\n{players_str}\n\n"
                "📌 _Bấm **Tham Gia** để vào ván, Host bấm **Bắt Đầu** khi đủ ≥ 5 người._"
            ),
            color=discord.Color.dark_purple(),
        )
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
        for tid in game.day_votes.values():
            if tid is None:
                white_votes += 1
            else:
                counts[tid] = counts.get(tid, 0) + 1

        lines = []
        for p in game.get_alive_players():
            c = counts.get(p.user_id, 0)
            lines.append(f"• **{p.display_name}**: `{c} phiếu`")

        lines.append(f"• 🏳️ **Phiếu trắng**: `{white_votes} phiếu`")

        if not is_final and game.settings.vote_display == "END_ONLY":
            desc = "⚖️ **Đang diễn ra bỏ phiếu...**\n_(Số phiếu hiện đang ẩn tới khi kết thúc giờ bỏ phiếu)_"
        else:
            desc = "⚖️ **Kết quả lượt bỏ phiếu treo cổ:**\n\n" + "\n".join(lines)

        embed = make_embed(
            title=f"⚖️ Bỏ Phiếu Treo Cổ — Ngày {game.day_count}",
            description=desc,
            color=discord.Color.gold(),
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

    async def sync_thread_permissions(self, game: MasoiGame):
        """Cập nhật quyền chat trong thread cho người đã chết."""
        if not game.thread_id or game.settings.dead_can_chat:
            return

        thread = self.bot.get_channel(game.thread_id)
        if not thread or not isinstance(thread, discord.Thread):
            return

        guild = thread.guild
        for p in game.players.values():
            if not p.is_alive:
                member = guild.get_member(p.user_id)
                if member:
                    try:
                        await thread.set_permissions(member, send_messages=False, send_messages_in_threads=False, view_channel=True)
                    except Exception:
                        pass

    # ──────────────────────────────────────────────
    #  Core State Machine Flow
    # ──────────────────────────────────────────────

    async def start_game(self, game: MasoiGame, message: discord.Message):
        game.phase = GamePhase.ROLE_ASSIGN
        game.assign_roles()

        # DM vai trò riêng cho từng người
        for p in game.players.values():
            user = self.bot.get_user(p.user_id)
            if user:
                extra_wolf_info = ""
                if p.is_wolf:
                    wolves = [other.display_name for other in game.players.values() if other.is_wolf and other.user_id != p.user_id]
                    if wolves:
                        extra_wolf_info = f"\n🐺 **Đồng đội Sói của bạn:** {', '.join(wolves)}"
                    else:
                        extra_wolf_info = "\n🐺 Bạn là con Sói duy nhất trong ván này!"

                dm_text = (
                    f"🌕 **VÁN MA SÓI BẮT ĐẦU!**\n"
                    f"Bạn là: **{p.role.emoji} {p.role.value}**\n"
                    f"Phe: **{p.role.faction.value}**\n"
                    f"Nhiệm vụ: {p.role.description}"
                    f"{extra_wolf_info}"
                )
                try:
                    await user.send(dm_text)
                except Exception:
                    logger.warning("Không thể DM riêng cho user %s", p.user_id)

        # Chạy vòng lặp game
        await self.game_loop(game, message)

    async def game_loop(self, game: MasoiGame, message: discord.Message):
        key = f"{game.guild_id}-{game.channel_id}"

        try:
            while game.phase != GamePhase.GAME_END:
                # ── BƯỚC 1: ĐÊM ──
                game.start_night()
                game.phase = GamePhase.NIGHT_GUARD

                # Gửi DM riêng cho các vai trò ban đêm
                # 1. Bảo Vệ
                guard_p = game.get_player_by_role(Role.GUARD)
                if guard_p:
                    g_user = self.bot.get_user(guard_p.user_id)
                    if g_user:
                        embed = make_embed(title=f"🛡️ Đêm {game.night_count} — Lượt Bảo Vệ", description="Hãy chọn 1 người chơi để bảo vệ khỏi bị Sói cắn đêm nay!")
                        view = NightGuardView(game, guard_p.user_id)
                        try:
                            await g_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                # 2. Bầy Sói
                for w in game.get_alive_wolves():
                    w_user = self.bot.get_user(w.user_id)
                    if w_user:
                        embed = make_embed(title=f"🐺 Đêm {game.night_count} — Lượt Bầy Sói", description="Hãy chọn 1 người chơi để cắn đêm nay!")
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
                        embed = make_embed(title=f"🔮 Đêm {game.night_count} — Lượt Tiên Tri", description="Hãy chọn 1 người chơi để soi phe!")
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
                        embed = make_embed(title=f"🧪 Đêm {game.night_count} — Lượt Phù Thủy", description=f"Đêm nay, bầy Sói nhắm cắn: **{v_name}**.\nBạn muốn dùng bình cứu hay bình độc không?")
                        view = NightWitchView(game, witch_p.user_id, victim_id)
                        try:
                            await wt_user.send(embed=embed, view=view)
                        except Exception:
                            pass

                embed_night = make_embed(
                    title=f"🌙 Ban Đêm — Đêm {game.night_count}",
                    description=(
                        f"Màn đêm đã buông xuống làng...\n"
                        f"Bot đã gửi tin nhắn riêng (DM) cho các vai trò ban đêm để bỏ phiếu/hành động!\n"
                        f"*(Hoặc bấm nút **[ 🌙 Hành Động Ban Đêm ]** dưới đây nếu bạn bị chặn DM)*\n\n"
                        f"⏱️ **Thời gian đêm:** `{game.settings.night_time}s`"
                    ),
                    color=discord.Color.dark_purple()
                )
                night_view = NightActionMainView(game, self)
                night_msg = await message.channel.send(embed=embed_night, view=night_view)

                await asyncio.sleep(game.settings.night_time)

                try:
                    await night_msg.delete()
                except Exception:
                    pass

                # 1.5 Tính toán đêm
                game.phase = GamePhase.NIGHT_RESOLVE
                night_deaths = game.resolve_night()

                # ── BƯỚC 2: CÔNG BỐ BAN NGÀY ──
                game.phase = GamePhase.DAY_ANNOUNCE
                game.start_day()
                await self.sync_thread_permissions(game)

                if night_deaths:
                    death_names = []
                    for uid in night_deaths:
                        p = game.players[uid]
                        if game.settings.reveal_roles_on_death:
                            death_names.append(f"💀 **{p.display_name}** ({p.role.emoji} {p.role.value})")
                        else:
                            death_names.append(f"💀 **{p.display_name}**")
                    day_msg_text = "Đêm qua trôi qua đầy đau thương... Các nạn nhân đã ra đi:\n" + "\n".join(death_names)
                else:
                    day_msg_text = "🌅 Đêm qua trôi qua thật bình yên, không có ai qua đời!"

                embed_announce = make_embed(
                    title=f"☀️ Ban Ngày — Ngày {game.day_count}",
                    description=f"{day_msg_text}\n\n💬 Mọi người hãy vào **Thread Thảo Luận** để bàn luận!",
                    color=discord.Color.gold()
                )
                await message.channel.send(embed=embed_announce)

                # Kiểm tra thắng ngay sau đêm
                if game.check_win_condition():
                    game.phase = GamePhase.GAME_END
                    break

                # ── BƯỚC 3: THẢO LUẬN BAN NGÀY ──
                game.phase = GamePhase.DAY_DISCUSSION
                disc_embed = make_embed(
                    title=f"💬 Ban Ngày — Thảo Luận (Ngày {game.day_count})",
                    description=f"Thời gian thảo luận: `{game.settings.discussion_time // 60} phút`.\n"
                                f"Bấm **Yêu cầu bỏ phiếu sớm** nếu muốn dồn phiếu ngay!",
                    color=discord.Color.blue()
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
                await self.sync_thread_permissions(game)

                if executed_id:
                    p = game.players[executed_id]
                    if game.settings.reveal_roles_on_death:
                        exec_text = f"⚖️ **{p.display_name}** đã bị dân làng xử tử trên giàn treo cổ! (Vai trò: **{p.role.emoji} {p.role.value}**)"
                    else:
                        exec_text = f"⚖️ **{p.display_name}** đã bị dân làng xử tử trên giàn treo cổ!"
                else:
                    exec_text = "⚖️ Lượt bỏ phiếu kết thúc hòa phiếu, không ai bị xử tử."

                await message.channel.send(embed=make_embed(title="⚖️ Kết Quả Xử Tử", description=exec_text, color=discord.Color.red()))

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
            status = "❤️ Sống" if p.is_alive else "💀 Chết"
            pts_str = f" (+{rank_pts.get(p.user_id, 0)} pts)" if game.settings.enable_rank else ""
            role_lines.append(f"• **{p.display_name}** — {p.role.emoji} **{p.role.value}** [{status}]{pts_str}")

        winner_str = game.winner_faction.value if game.winner_faction else "Không có"

        end_embed = make_embed(
            title=f"🏆 VÁN BÀN CỜ MA SÓI KẾT THÚC — {winner_str}!",
            description=(
                f"🎉 **{winner_str} đã giành chiến thắng!**\n\n"
                f"**Vai trò tất cả người chơi:**\n" + "\n".join(role_lines) + "\n\n"
                f"⏱️ **Tổng thời gian ván:** {game.night_count} Đêm, {game.day_count} Ngày"
            ),
            color=discord.Color.green(),
        )

        end_view = GameEndView(game, self)
        await message.channel.send(embed=end_embed, view=end_view)

        # Khóa/Lưu thread thảo luận
        if game.thread_id:
            thread = self.bot.get_channel(game.thread_id)
            if thread and isinstance(thread, discord.Thread):
                try:
                    await thread.send("🔒 **Ván đấu đã kết thúc! Thread thảo luận được khóa lại.**")
                    await thread.edit(archived=True, locked=True)
                except Exception:
                    pass
