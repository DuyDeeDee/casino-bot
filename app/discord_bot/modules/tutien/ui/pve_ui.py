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


class TutienTopLeaderboardView(discord.ui.View):
    """Interactive Tab-switching View for Tu Tiên Leaderboards (!tutien-top)."""
    def __init__(self, db, current_tab: str = "tu-vi", timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.db = db
        self.current_tab = current_tab
        self._update_button_styles()

    def _update_button_styles(self):
        self.btn_tuvi.style = discord.ButtonStyle.primary if self.current_tab == "tu-vi" else discord.ButtonStyle.secondary
        self.btn_giatai.style = discord.ButtonStyle.primary if self.current_tab == "gia-tai" else discord.ButtonStyle.secondary
        self.btn_thap.style = discord.ButtonStyle.primary if self.current_tab == "thap" else discord.ButtonStyle.secondary
        self.btn_boss.style = discord.ButtonStyle.primary if self.current_tab == "boss" else discord.ButtonStyle.secondary

    def build_embed(self) -> discord.Embed:
        medals = ["🥇", "🥈", "🥉", "4️⃣", "5️⃣", "6️⃣", "7️⃣", "8️⃣", "9️⃣", "🔟"]
        if self.current_tab == "gia-tai":
            rows = self.db.get_top_wealthy(10)
            embed = discord.Embed(
                title="💰 BẢNG XẾP HẠNG TOP TRÚC THẠCH TRONG THỜI (GIA TÀI)",
                description="Top 10 Đại Phú Hào sở hữu Linh Thạch & Tiên Ngọc khủng nhất Server:",
                color=discord.Color.gold()
            )
            if not rows:
                embed.description += "\n\n_Chưa có dữ liệu tu sĩ nào._"
            else:
                for idx, r in enumerate(rows):
                    m = medals[idx] if idx < len(medals) else f"`{idx+1}`"
                    vip_str = f" `[VIP {r['vip_level']}]`" if r['vip_level'] > 0 else ""
                    embed.add_field(
                        name=f"{m} {r['dao_hieu']}{vip_str}",
                        value=f"> 💰 `{r['linh_thach']:,}` Linh Thạch | 💎 `{r['tien_ngoc']:,}` Tiên Ngọc\n> ☯️ {r['realm_name']}",
                        inline=False
                    )

        elif self.current_tab == "thap":
            rows = self.db.get_tower_leaderboard(10)
            embed = discord.Embed(
                title="🏛️ BẢNG XẾP HẠNG THÁP THIÊN CỰC (LEO THÁP)",
                description="Top 10 Cao Thủ leo tầng cao nhất Tháp Thiên Cực:",
                color=discord.Color.purple()
            )
            if not rows:
                embed.description += "\n\n_Chưa có dữ liệu leo tháp._"
            else:
                for idx, r in enumerate(rows):
                    m = medals[idx] if idx < len(medals) else f"`{idx+1}`"
                    embed.add_field(
                        name=f"{m} {r['dao_hieu']}",
                        value=f"> 🏆 **Tầng {r['tower_floor']}** | ☯️ {r['realm_name']}",
                        inline=False
                    )

        elif self.current_tab == "boss":
            rows = self.db.get_world_boss_rankings(10)
            embed = discord.Embed(
                title="🔥 BẢNG XẾP HẠNG SÁT THƯƠNG MA VƯƠNG (WORLD BOSS)",
                description="Top 10 Dũng Sĩ gây nhiều DPS nhất lên Thái Cổ Ma Vương hôm nay:",
                color=discord.Color.dark_red()
            )
            if not rows:
                embed.description += "\n\n_Chưa có tu sĩ nào khiêu chiến Boss hôm nay._"
            else:
                for idx, r in enumerate(rows):
                    m = medals[idx] if idx < len(medals) else f"`{idx+1}`"
                    embed.add_field(
                        name=f"{m} {r['dao_hieu']}",
                        value=f"> ⚔️ Sát Thương tích lũy: `{r['boss_dps_today']:,}` DPS | ☯️ {r['realm_name']}",
                        inline=False
                    )

        else:
            # Default: Tu Vi
            rows = self.db.get_top_cultivators(10)
            embed = discord.Embed(
                title="🏆 BẢNG XẾP HẠNG TOP TU SĨ SERVER (CẢNH GIỚI & TU VI)",
                description="Top 10 Đại Năng có Cảnh Giới & Tu Vi cao nhất Server:",
                color=discord.Color.gold()
            )
            if not rows:
                embed.description += "\n\n_Chưa có tu sĩ nào gia nhập._"
            else:
                for idx, r in enumerate(rows):
                    m = medals[idx] if idx < len(medals) else f"`{idx+1}`"
                    vip_str = f" `[VIP {r['vip_level']}]`" if r['vip_level'] > 0 else ""
                    embed.add_field(
                        name=f"{m} **{r['dao_hieu']}**{vip_str}",
                        value=f"> ☯️ Cảnh giới: **{r['realm_name']}** | `{r['exp']:,}` EXP\n> ⚡ Linh căn: `{r['linh_can_quality']}` ({r['linh_can_element']})",
                        inline=False
                    )

        embed.set_footer(text="Bấm nút sang trang phía dưới để xem các Bảng Xếp Hạng khác")
        return embed

    @discord.ui.button(label="🏆 Top Tu Vi", style=discord.ButtonStyle.primary, custom_id="btn_top_tuvi")
    async def btn_tuvi(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "tu-vi"
        self._update_button_styles()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="💰 Top Gia Tài", style=discord.ButtonStyle.secondary, custom_id="btn_top_giatai")
    async def btn_giatai(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "gia-tai"
        self._update_button_styles()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="🏛️ Top Leo Tháp", style=discord.ButtonStyle.secondary, custom_id="btn_top_thap")
    async def btn_thap(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "thap"
        self._update_button_styles()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="🔥 Top Boss Server", style=discord.ButtonStyle.secondary, custom_id="btn_top_boss")
    async def btn_boss(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_tab = "boss"
        self._update_button_styles()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)


class TutienGuidePaginatorView(discord.ui.View):
    """Interactive Multi-Page Guide Paginator for Tu Tiên (!huongdan)."""
    def __init__(self, current_page: int = 1, timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.current_page = current_page
        self.total_pages = 4
        self._update_buttons()

    def _update_buttons(self):
        self.btn_prev.disabled = (self.current_page <= 1)
        self.btn_next.disabled = (self.current_page >= self.total_pages)
        self.btn_page_indicator.label = f"Trang {self.current_page}/{self.total_pages}"

    def build_embed(self) -> discord.Embed:
        if self.current_page == 1:
            embed = discord.Embed(
                title="📜 CẨM NANG TU TIÊN — TRANG 1/4: LINH CĂN & THUỘC TÍNH",
                description="Chào mừng đến với **«ĐẠI ĐẠO TRANH PHONG»**! Dưới đây là thông tin chi tiết về Linh Căn & Thuộc Tính:",
                color=discord.Color.gold()
            )
            embed.add_field(
                name="1️⃣ Nhập Môn & Khởi Tạo Linh Căn (!nhapmon)",
                value="> Gõ `!nhapmon [Đạo Hiệu]` để nhập môn, quay Linh Căn ngẫu nhiên & nhận `500` Linh Thạch + `100` Tinh Lực.",
                inline=False
            )
            embed.add_field(
                name="🔮 6 Cấp Độ Linh Căn (Rarity & Buff)",
                value="> 🟢 **Phàm Phẩm (45%)**: Căn cơ tiêu chuẩn, 100% EXP speed.\n"
                      "> 🔵 **Linh Phẩm (30%)**: +15% Tốc độ tu vi.\n"
                      "> 🟣 **Địa Phẩm (15%)**: +30% Tốc độ tu vi, +5% Tỷ lệ Đột Phá.\n"
                      "> 🟡 **Thiên Phẩm (7.5%)**: +50% Tốc độ tu vi, +10% Đột Phá, +10% Bạo Kích.\n"
                      "> 🔴 **Tiên Phẩm (2.49%)**: +80% Tốc độ tu vi, +15% Đột Phá, +15% Bạo Kích.\n"
                      "> 🌟 **Hỗn Độn Linh Căn (0.01% - Siêu Hiếm)**: +150% Tốc độ tu vi, +30% Đột Phá, +25% Bạo Kích & Kháng 30% Lôi Kiếp!",
                inline=False
            )
            embed.add_field(
                name="⚡ Thuộc Tính Ngũ Hành & Dị Linh Căn",
                value="> ☯️ **Ngũ Hành**: 🔥 Hỏa, 💧 Thủy, 🌳 Mộc, ⚡ Kim, 🪨 Thổ (Khắc chế lẫn nhau +50% DMG).\n"
                      "> ⚡ **Lôi Hệ**: Bộc phát Sát Thương & Tê liệt Yêu Thú.\n"
                      "> ❄️ **Băng Hệ**: Đóng băng mục tiêu & Giảm 15% Sát thương nhận vào.\n"
                      "> 🌪️ **Phong Hệ**: Thân pháp linh hoạt, +20% Né Tránh.\n"
                      "> 🌌 **Không Gian**: Diễn biến vi diệu, +40% Sát thương Đột Phá.",
                inline=False
            )

        elif self.current_page == 2:
            embed = discord.Embed(
                title="📜 CẨM NANG TU TIÊN — TRANG 2/4: TU LUYỆN & ĐỘT PHÁ CẢNH GIỚI",
                description="Hướng dẫn quy trình tích lũy Tu Vi, Bế Quan AFK và Đột Phá Đội Kiếp:",
                color=discord.Color.purple()
            )
            embed.add_field(
                name="🧘 Tu Luyện Chủ Động (!tuluyen)",
                value="> Tiêu 15 Tinh Lực/lần (Hồi `+5` Tinh Lực mỗi 5 phút). Tích lũy EXP Tu Vi theo Cảnh Giới.",
                inline=False
            )
            embed.add_field(
                name="🛌 Bế Quan AFK & Xuất Quan (!nhapdinh & !xuat-quan)",
                value="> Gõ `!nhapdinh [1h|4h|8h|12h|16h|24h]` bế quan tích lũy tài nguyên khi offline.\n"
                      "> Gõ `!xuat-quan` để xuất quan sớm & nhận quà tích lũy.",
                inline=False
            )
            embed.add_field(
                name="💪 Luyện Thể & Căn Cơ (!luyenthe & !tamcanh)",
                value="> Gõ `!luyenthe` tiêu Linh Thạch nâng cấp Tôi Thể -> Bất Diệt Thể tăng HP & Giáp.\n"
                      "> Gõ `!tamcanh` kiểm tra độ vững Căn Cơ & tỷ lệ thành công Đột Phá.",
                inline=False
            )
            embed.add_field(
                name="⚡ Quy Trình Độ Kiếp Lôi Kiếp (!dotpha)",
                value="> Khi Tu Vi đạt 100%, gõ `!dotpha` nghênh đón Lôi Kiếp thời gian thực 10s/đợt.\n"
                      "> Chọn `[🛡️ Trận Pháp]` hoặc `[💊 Uống Đan Dược]` để hóa giải Sát Thương Lôi Kiếp!",
                inline=False
            )

        elif self.current_page == 3:
            embed = discord.Embed(
                title="📜 CẨM NANG TU TIÊN — TRANG 3/4: CHINH PHỤC HARDCORE PVE",
                description="Tổng quan 4 Chế độ PVE Souls-like & Cơ chế Sinh tồn Nguy hiểm:",
                color=discord.Color.red()
            )
            embed.add_field(
                name="⚔️ Săn Yêu Thường (!san-yeu)",
                value="> Đánh quái theo Cảnh Giới (VIP 2+ gõ `!san-yeu quet` 10x). Có 15% quái Biến Dị 3x stats & Boss Smart AI.",
                inline=False
            )
            embed.add_field(
                name="🏛️ Tháp Thiên Cực (!leo-thap & !top-thap)",
                value="> Chinh phục 100 Tầng Tháp nhận Tiên Duyên Phù & Tiên Ngọc. Tầng 10, 20... xuất hiện Ảo Ảnh Bản Thân!",
                inline=False
            )
            embed.add_field(
                name="🏰 Bí Cảnh Cổ Đại (!bi-canh)",
                value="> Lập đội 3-5 Tu Sĩ với 3 vai trò (**Tiền Phong Tank**, **Chủ Lực DPS**, **Hỗ Trợ Healer**).",
                inline=False
            )
            embed.add_field(
                name="🕸️ Mê Cung Roguelike Thái Cổ Cấm Địa (!bi-canh-cam-dia)",
                value="> Đột phá Mê Cung 5 Phòng Sinh Tồn (HP không tự hồi). Bẫy Thí Mạng chọn 1 người gánh 80% HP!",
                inline=False
            )
            embed.add_field(
                name="🩸 Kinh Mạch Đoạn Tuyệt & Cứu Thương (!cuu-thuong & !giai-doc)",
                value="> Tử trận PVE gây trạng thái Kinh Mạch Đoạn Tuyệt (10 phút). Nhờ bạn gõ `!cuu-thuong @user` để cứu!\n"
                      "> Gõ `!giai-doc` để giải trừ Độc Tố Thấu Cốt / Ô Nhiễm Tâm Ma.",
                inline=False
            )

        else:
            embed = discord.Embed(
                title="📜 CẨM NANG TU TIÊN — TRANG 4/4: GACHA, TIÊN CÁC & VIP",
                description="Hệ thống Tiên Các, Định Hướng Đạo Vận Wishlist và Đặc Quyền VIP:",
                color=discord.Color.blue()
            )
            embed.add_field(
                name="🔮 Gacha 3 Banner (!gacha)",
                value="> Banner Thường (Linh Duyên Phù), Banner VIP (Tiên Duyên Phù - UR 0.7%), Banner Cải Mệnh (Tẩy Tủy Phù). Pity bảo hiểm 80 lượt.",
                inline=False
            )
            embed.add_field(
                name="🎯 Định Hướng Đạo Vận Wishlist (!wishlist)",
                value="> Gõ `!wishlist [Tên_Item]` cấu hình bảo báu mơ ước. Lượt nổ hũ UR tiếp theo chắc chắn 100% ra món chọn!",
                inline=False
            )
            embed.add_field(
                name="🛍️ Shop Tiên Các (!tiencac & !mua)",
                value="> Mua Thần Phù Bảo Mệnh (Bảo hiểm độ kiếp), Vạn Linh Đan (Cứu thương PVE), Thánh Thể Phù (Bảo vệ rớt đồ), Thẻ Tháng VIP.",
                inline=False
            )
            embed.add_field(
                name="🌟 Hệ Thống VIP & Thẻ Tháng (!vip)",
                value="> Tích nạp mở khóa VIP 1 -> VIP 10 (+Tốc độ Tinh Lực, Quét 10x, Thẻ Tháng Bế Quan 24h).",
                inline=False
            )

        embed.set_footer(text="Bấm nút sang trang ◀ ▶ bên dưới để chuyển các trang cẩm nang!")
        return embed

    @discord.ui.button(label="◀ Trang Trước", style=discord.ButtonStyle.primary, custom_id="btn_guide_prev")
    async def btn_prev(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Trang 1/4", style=discord.ButtonStyle.secondary, disabled=True, custom_id="btn_guide_indicator")
    async def btn_page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        pass

    @discord.ui.button(label="Trang Sau ▶", style=discord.ButtonStyle.primary, custom_id="btn_guide_next")
    async def btn_next(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)
