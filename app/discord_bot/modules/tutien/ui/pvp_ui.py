"""
Interactive Discord UI Views and Embed Renderers for Tu Tien PVP System
Includes Sinh Tử Đài Confirmation, Luận Đạo Đài, Bảng Truy Nã Huyết Sát & Tàng Kinh Các Shop.
"""

import math
import time
import discord
from typing import Dict, Any, List, Optional
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.constants import (
    PVP_RANKS, get_pvp_rank, TANG_KINH_CAC_SHOP, REALMS
)
from app.discord_bot.modules.tutien.db import TuTienDB


def render_progress_bar(current: int, max_val: int, length: int = 14, fill_char: str = "█", empty_char: str = "░") -> str:
    """
    Renders an ASCII/Emoji progress bar like `[████████░░░░]`.
    """
    if max_val <= 0:
        return f"[{empty_char * length}]"
    ratio = max(0.0, min(1.0, float(current) / float(max_val)))
    fill_len = int(round(ratio * length))
    empty_len = length - fill_len
    return f"[{fill_char * fill_len}{empty_char * empty_len}]"


class SinhTuDaiConfirmView(discord.ui.View):
    """
    Confirmation dialog for Sinh Tử Đài (High-Stakes PVP Bet).
    Only the challenged user (target_id) can accept or reject.
    """
    def __init__(self, challenger: CultivatorProfile, target: CultivatorProfile, bet_type: str, bet_amount: int, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.challenger = challenger
        self.target = target
        self.bet_type = bet_type          # "LINH_THACH", "TU_VI", "PHAP_BAO"
        self.bet_amount = bet_amount
        self.accepted: Optional[bool] = None

    @discord.ui.button(label="⚔️ Chấp Nhận Sinh Tử (Quyết Đấu)", style=discord.ButtonStyle.danger, emoji="💀")
    async def accept_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.user_id:
            await interaction.response.send_message("❌ Chỉ có đạo hữu được khiêu chiến mới có quyền tiếp nhận chiến thư!", ephemeral=True)
            return

        self.accepted = True
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="💥 **ĐÃ TIẾP NHẬN SINH TỬ ĐÀI! TRẬN CHIẾN BẮT ĐẦU!**", view=self)

    @discord.ui.button(label="🏳️ Cự Tuyệt (Hủy Kèo)", style=discord.ButtonStyle.secondary, emoji="🛡️")
    async def reject_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.target.user_id and interaction.user.id != self.challenger.user_id:
            await interaction.response.send_message("❌ Bạn không liên quan đến trận chiến này!", ephemeral=True)
            return

        self.accepted = False
        self.stop()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content=f"🏳️ **Chiến thư Sinh Tử Đài đã bị hủy bỏ!**", view=self)


class BountyBoardView(discord.ui.View):
    """
    Bảng Lệnh Truy Nã Huyết Sát Paginator View.
    """
    def __init__(self, db: TuTienDB, bounties: List[Dict[str, Any]], current_page: int = 1, per_page: int = 5, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.db = db
        self.bounties = bounties
        self.current_page = current_page
        self.per_page = per_page
        self.total_pages = max(1, math.ceil(len(bounties) / per_page))
        self.update_buttons()

    def update_buttons(self):
        self.prev_btn.disabled = (self.current_page <= 1)
        self.next_btn.disabled = (self.current_page >= self.total_pages)

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🩸 BẢNG LỆNH TRUY NÃ HUYẾT SÁT TOÀN SERVER 🩸",
            description="*Danh sách các Ma Đầu tội ác tày trời đang bị truy nã gắt gao!*\n"
                        "> Gõ `!tram-ma @User` để săn Ma Đầu và nhận trọn tiền thưởng!",
            color=discord.Color.dark_red()
        )

        if not self.bounties:
            embed.add_field(name="🕊️ Thiên Hạ Thái Bình", value="Hiện không có Ma Đầu nào trên Bảng Truy Nã.", inline=False)
            embed.set_footer(text=f"Trang {self.current_page}/{self.total_pages}")
            return embed

        start_idx = (self.current_page - 1) * self.per_page
        page_items = self.bounties[start_idx : start_idx + self.per_page]

        for idx, b in enumerate(page_items, start=start_idx + 1):
            lt = b.get("reward_linh_thach", 0)
            ngoc = b.get("reward_tien_ngoc", 0)
            reward_str = f"`{lt:,}` Linh Thạch" + (f" + `{ngoc}` Tiên Ngọc" if ngoc else "")
            
            target_name = b.get("target_dao_hieu", "Ma Đầu")
            realm = b.get("target_realm_name", "Ẩn Tích")
            nghiep = b.get("target_nghiep_luc", 0)
            issuer = b.get("issuer_dao_hieu", "Đồng Đạo")
            reason = b.get("reason", "Treo thưởng trảm ma!")

            val = (
                f"> 💀 **Ma Đầu:** **[{target_name}]** (`{realm}`)\n"
                f"> 🔥 **Nghiệp Lực:** `{nghiep}` điểm\n"
                f"> 💰 **Tiền Thưởng Headshot:** 🌟 **{reward_str}**\n"
                f"> 📜 *Lý do: {reason}* (Người phát lệnh: `{issuer}`)"
            )
            embed.add_field(name=f"[{idx}] LỆNH TRUY NÃ #{b['bounty_id']}", value=val, inline=False)

        embed.set_footer(text=f"Trang {self.current_page}/{self.total_pages} • Cú pháp săn: !tram-ma @User")
        return embed

    @discord.ui.button(label="◀️ Trang Trước", style=discord.ButtonStyle.secondary, custom_id="bounty_prev")
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page > 1:
            self.current_page -= 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Trang Sau ▶️", style=discord.ButtonStyle.secondary, custom_id="bounty_next")
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.current_page < self.total_pages:
            self.current_page += 1
            self.update_buttons()
            await interaction.response.edit_message(embed=self.build_embed(), view=self)


class TangKinhCacShopView(discord.ui.View):
    """
    Shop Tàng Kinh Các đổi Điểm Danh Vọng.
    """
    def __init__(self, db: TuTienDB, player: CultivatorProfile, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.db = db
        self.player = player

    def build_embed(self) -> discord.Embed:
        embed = discord.Embed(
            title="🏯 TÀNG KINH CÁC — DANH VỌNG BẢO ĐIỂN 🏯",
            description=f"Tu sĩ: **[{self.player.dao_hieu}]** (ELO: `{self.player.pvp_elo}`) | 🏆 **`{self.player.danh_vong:,}` Danh Vọng**\n"
                        f"> Cú pháp đổi vật phẩm: `!tang-kinh-cac [Tên_Vật_Phẩm]`",
            color=discord.Color.gold()
        )

        for name, item in TANG_KINH_CAC_SHOP.items():
            req_info = f" | Yêu cầu: `{item.get('req_rank', 'Tất Cả')}`" if item.get("req_rank") else ""
            embed.add_field(
                name=f"📜 {name} — 🏆 {item['cost']:,} Danh Vọng",
                value=f"> Loại: `{item['type']}`{req_info}\n> *{item['desc']}*",
                inline=False
            )

        embed.set_footer(text="Tham gia Luận Đạo Đài (!luan-dao) để tích lũy Danh Vọng (Tối đa 150 DV/ngày)!")
        return embed

