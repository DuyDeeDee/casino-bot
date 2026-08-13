"""
Discord UI Views for Hardcore Souls-like / Roguelike PVE System:
Interactive Battle Buttons, 5-Second QTE Countdown, Trap Sacrifice Voting, Dungeon Merchant, and Rescue Prompts.
"""

import discord
from typing import Optional, Dict, Any


class PveBattleView(discord.ui.View):
    def __init__(self, user_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.chosen_action: Optional[str] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Trận chiến này không thuộc về bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="⚔️ Công Kích", style=discord.ButtonStyle.danger, custom_id="btn_pve_atk")
    async def attack_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen_action = "ATTACK"
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="📜 Bí Thuật", style=discord.ButtonStyle.primary, custom_id="btn_pve_gongfa")
    async def gongfa_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen_action = "GONGFA"
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="💊 Nạp Đan", style=discord.ButtonStyle.success, custom_id="btn_pve_heal")
    async def heal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen_action = "HEAL"
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="🏃 Độn Thổ", style=discord.ButtonStyle.secondary, custom_id="btn_pve_run")
    async def run_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.chosen_action = "RUN"
        await interaction.response.defer()
        self.stop()


class QteOneShotView(discord.ui.View):
    """5-second real-time countdown QTE buttons for Boss 3,000% One-Shot Ultimate."""
    def __init__(self, user_id: int, timeout: float = 5.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.success = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Thử thách QTE này không thuộc về bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🛡️ Mở Trận Pháp Phòng Thủ", style=discord.ButtonStyle.primary, custom_id="btn_qte_shield")
    async def qte_shield(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.success = True
        await interaction.response.send_message("🛡️ **KỊCH THỜI KÍCH HOẠT TRẬN PHÁP!** Bạn đã hóa giải 90% sát thương đòn One-Shot!", ephemeral=True)
        self.stop()

    @discord.ui.button(label="🏃 Phù Độn Thổ Cấp Tốc", style=discord.ButtonStyle.success, custom_id="btn_qte_dodge")
    async def qte_dodge(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.success = True
        await interaction.response.send_message("⚡ **ĐỘN THỔ THÀNH CÔNG!** Bạn đã né tránh đòn đánh hủy diệt!", ephemeral=True)
        self.stop()


class TrapSacrificeView(discord.ui.View):
    """Voting View for Roguelike Trap Room (Cổ Trận Thí Mạng)."""
    def __init__(self, host_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.host_id = host_id
        self.choice: Optional[str] = None

    @discord.ui.button(label="👥 Cả Đội Cùng Mất 20% HP", style=discord.ButtonStyle.primary, custom_id="btn_trap_all")
    async def trap_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Chỉ Trưởng Đội mới có quyền quyết định!", ephemeral=True)
            return
        self.choice = "ALL"
        await interaction.response.send_message("⚠️ **CẢ ĐỘI CHỊU PHẠT!** Tất cả thành viên trong đội chịu tổn hại -20% HP!", ephemeral=False)
        self.stop()

    @discord.ui.button(label="🎯 1 Người Chịu Gánh 80% HP", style=discord.ButtonStyle.danger, custom_id="btn_trap_one")
    async def trap_one(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Chỉ Trưởng Đội mới có quyền quyết định!", ephemeral=True)
            return
        self.choice = "ONE"
        await interaction.response.send_message("🩸 **HI SINH BẢO TOÀN!** Trưởng đội chọn 1 người chịu phạt -80% HP để cả đội đi tiếp!", ephemeral=False)
        self.stop()


class DungeonMerchantView(discord.ui.View):
    """Mystery Merchant View inside Roguelike Dungeon Matrix."""
    def __init__(self, user_id: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Thương nhân này đang giao dịch với tu sĩ khác!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="💊 Mua Vạn Linh Đan (50 Tiên Ngọc)", style=discord.ButtonStyle.success, custom_id="btn_buy_van_linh")
    async def buy_van_linh(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Đã mua **Vạn Linh Đan**! Dùng `!cuu-thuong @user` để cứu đạo hữu bị tổn thương!", ephemeral=True)

    @discord.ui.button(label="🛡️ Mua Thánh Thể Phù (80 Tiên Ngọc)", style=discord.ButtonStyle.secondary, custom_id="btn_buy_thanh_the")
    async def buy_thanh_the(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("✅ Đã mua **Thánh Thể Phù**! Giúp bảo vệ không bị rớt đồ và hại Căn Cơ khi tử trận!", ephemeral=True)


class PartyLobbyView(discord.ui.View):
    def __init__(self, host_id: int, dungeon_name: str, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.host_id = host_id
        self.dungeon_name = dungeon_name
        self.members: Dict[int, str] = {host_id: "Tiền Phong (Tank)"}
        self.is_started = False

    @discord.ui.button(label="🛡️ Gia Nhập (Tiền Phong)", style=discord.ButtonStyle.primary, custom_id="btn_party_tank")
    async def join_tank(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.members[interaction.user.id] = "Tiền Phong (Tank)"
        await interaction.response.send_message(f"✅ **{interaction.user.display_name}** đã tham gia đội với vai trò **Tiền Phong (Tank)**!", ephemeral=False)

    @discord.ui.button(label="⚔️ Gia Nhập (Chủ Lực DPS)", style=discord.ButtonStyle.danger, custom_id="btn_party_dps")
    async def join_dps(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.members[interaction.user.id] = "Chủ Lực (DPS)"
        await interaction.response.send_message(f"✅ **{interaction.user.display_name}** đã tham gia đội với vai trò **Chủ Lực (DPS)**!", ephemeral=False)

    @discord.ui.button(label="💖 Gia Nhập (Hỗ Trợ Healer)", style=discord.ButtonStyle.success, custom_id="btn_party_heal")
    async def join_heal(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.members[interaction.user.id] = "Hỗ Trợ (Healer)"
        await interaction.response.send_message(f"✅ **{interaction.user.display_name}** đã tham gia đội với vai trò **Hỗ Trợ (Healer)**!", ephemeral=False)

    @discord.ui.button(label="🚀 Bắt Đầu Đột Phá", style=discord.ButtonStyle.secondary, custom_id="btn_party_start")
    async def start_party(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.host_id:
            await interaction.response.send_message("❌ Chỉ Trưởng Đội mới có quyền bắt đầu!", ephemeral=True)
            return
        self.is_started = True
        await interaction.response.send_message("🚀 **ĐỘI HÌNH ĐÃ KHỞI HÀNH VÀO BÍ CẢNH!**", ephemeral=False)
        self.stop()


class RevivePromptView(discord.ui.View):
    def __init__(self, user_id: int, timeout: float = 30.0):
        super().__init__(timeout=timeout)
        self.user_id = user_id
        self.accepted = False

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Thông báo này không thuộc về bạn!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="✨ Cửu Chuyển Đan Hồi Sinh (20 Tiên Ngọc)", style=discord.ButtonStyle.primary, custom_id="btn_revive_yes")
    async def revive_yes(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = True
        await interaction.response.defer()
        self.stop()

    @discord.ui.button(label="💀 Chấp Nhận Tử Trận", style=discord.ButtonStyle.secondary, custom_id="btn_revive_no")
    async def revive_no(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.accepted = False
        await interaction.response.defer()
        self.stop()
