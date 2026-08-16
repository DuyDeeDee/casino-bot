from __future__ import annotations

import asyncio
import io
import os
import random
import time
from typing import Optional, Dict, Any, List, Tuple
import discord
from discord.ext import commands, tasks

from app.discord_bot.modules.tutien.db import TuTienDB
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.constants import (
    REALMS, REALM_REQUIRED_EXP, REALM_REQUIRED_TAM_CANH, SPIRITUAL_ROOT_QUALITY_BUFF, ELEMENTS_NGU_HANH, ELEMENTS_DI_LINH_CAN,
    TIEN_CAC_SHOP, VIP_LEVELS, GACHA_BANNERS, LINH_BUI_SHOP, PVP_RANKS, get_pvp_rank, TANG_KINH_CAC_SHOP
)
from app.discord_bot.modules.tutien.engines.cultivation import (
    roll_spiritual_root, process_active_cultivation
)
from app.discord_bot.modules.tutien.engines.tribulation import (
    calculate_breakthrough_chance, calculate_tribulation_damage, calculate_kim_dan_quality, HEART_DEMON_QUESTIONS
)
from app.discord_bot.modules.tutien.engines.body_refining import upgrade_body_refining, fuse_dao_domains
from app.discord_bot.modules.tutien.engines.crafting import (
    craft_alchemy_pill, ALCHEMY_RECIPES, craft_equipment_item, FORGING_RECIPES
)
from app.discord_bot.modules.tutien.engines.gongfa import GONGFA_DATABASE
from app.discord_bot.modules.tutien.engines.monetization import (
    grant_topup_and_vip_exp, buy_tiencac_item, is_array_protected
)
from app.discord_bot.modules.tutien.engines.gacha import process_gacha_rolls
from app.discord_bot.modules.tutien.engines.pve import (
    generate_pve_monster, process_turn_action, process_quick_sweep_10x, check_elemental_advantage, calculate_player_pve_atk,
    generate_mirror_phantom_boss, generate_roguelike_dungeon_matrix, process_hardcore_defeat
)
from app.discord_bot.modules.tutien.engines.pvp import (
    simulate_full_pvp_match, calculate_elo_change, calculate_realm_oppression, calculate_chan_nguyen_purity,
    calculate_than_thuc_battle, calculate_dao_domain_matchup, calculate_player_pvp_atk
)
from app.discord_bot.modules.tutien.renderers.profile_renderer import render_tutien_profile_card
from app.discord_bot.modules.tutien.ui.tribulation_ui import TribulationWaveView, HeartDemonQuizView
from app.discord_bot.modules.tutien.ui.pve_ui import (
    PveBattleView, PartyLobbyView, RevivePromptView, QteOneShotView, TrapSacrificeView, DungeonMerchantView, TutienTopLeaderboardView, TutienGuidePaginatorView
)
from app.discord_bot.modules.tutien.ui.pvp_ui import (
    render_progress_bar, SinhTuDaiConfirmView, BountyBoardView, TangKinhCacShopView
)

GIF_CHEST_PATH = "pictures/open_chest.gif"
BANNER_IMAGES = {
    "tubao": "pictures/banner_tubao.jpg",
    "tiencac": "pictures/banner_tiencac.jpg",
    "caimenh": "pictures/banner_caimenh.jpg"
}


class GachaInteractiveView(discord.ui.View):
    """
    Interactive View for Gacha Banners:
    - Switch between 3 banners: Tụ Bảo Các (F2P), Tiên Các (VIP), Cải Mệnh Đài (Special)
    - Instant Roll buttons: [Quay 1x] and [Quay 10x]
    - Dynamic update of remaining tickets, currency, pity count and items.
    """
    def __init__(self, bot_cog, user_id: int, db, initial_banner: str = "tubao", timeout: float = 180.0):
        super().__init__(timeout=timeout)
        self.bot_cog = bot_cog
        self.user_id = user_id
        self.db = db
        self.current_banner = initial_banner
        self._update_button_styles()

    def _update_button_styles(self):
        self.btn_tubao.style = discord.ButtonStyle.success if self.current_banner == "tubao" else discord.ButtonStyle.secondary
        self.btn_tiencac.style = discord.ButtonStyle.success if self.current_banner == "tiencac" else discord.ButtonStyle.secondary
        self.btn_caimenh.style = discord.ButtonStyle.success if self.current_banner == "caimenh" else discord.ButtonStyle.secondary

    def get_embed(self) -> discord.Embed:
        player = self.db.get_player(self.user_id)
        if not player:
            return discord.Embed(title="❌ Lỗi", description="Không tìm thấy dữ liệu tu sĩ!", color=discord.Color.red())

        pity_str = f"`{player.soft_pity_count}/80` (Soft Pity: 60+)"
        wish_str = f"🎯 Wishlist: **[{player.wishlist_item or 'Chưa cài đặt (!wishlist)'}]**"

        if self.current_banner == "tubao":
            embed = discord.Embed(
                title="🏮 TỤ BẢO CÁC — BANNER THƯỜNG (F2P)",
                description=f"Tu sĩ: **[{player.dao_hieu}]** | Lượt Bảo Hiểm (Pity): {pity_str}\n\n"
                            f"🎟️ **Vé Linh Duyên Phù:** `{player.linh_duyen_phu}` vé\n"
                            f"💰 **Linh Thạch có sẵn:** `{player.linh_thach:,}`\n\n"
                            f"📜 **Chi phí:** `1x Linh Duyên Phù` hoặc `10,000 Linh Thạch` / lượt\n"
                            f"🎁 **Vật phẩm:** Đan Dược Cực Phẩm, Thảo Dược, Linh Bụi, Pháp Bảo Huyền Cấp, Vé Tiên Duyên...",
                color=discord.Color.teal()
            )
        elif self.current_banner == "tiencac":
            embed = discord.Embed(
                title="🌟 CỬU THIÊN TIÊN CÁC — BANNER VIP (PREMIUM)",
                description=f"Tu sĩ: **[{player.dao_hieu}]** | Lượt Bảo Hiểm (Pity): {pity_str}\n"
                            f"> {wish_str}\n\n"
                            f"🌟 **Vé Tiên Duyên Phù:** `{player.tien_duyen_phu}` vé\n"
                            f"💎 **Tiên Ngọc có sẵn:** `{player.tien_ngoc:,}`\n\n"
                            f"📜 **Chi phí:** `1x Tiên Duyên Phù` hoặc `50 Tiên Ngọc` / lượt\n"
                            f"🎁 **Bảo vật:** **Đế Cấp (UR 0.7%)** (《Thôn Thiên Ma Công》, Trảm Tiên Kiếm, Cửu Vĩ Thiên Hồ), **Thiên Cấp (SR 4.3%)**\n"
                            f"🛡️ **Cơ chế:** Soft Pity 60 lượt (+5%/lượt) | Hard Pity 80 lượt chắc chắn ra UR!",
                color=discord.Color.gold()
            )
        else:
            embed = discord.Embed(
                title="☯ THÁI CỔ CẢI MỆNH ĐÀI — BANNER CẢI MỆNH",
                description=f"Tu sĩ: **[{player.dao_hieu}]**\n"
                            f"⚡ **Linh Căn Hiện Tại:** `{player.linh_can_quality}` ({player.linh_can_element})\n\n"
                            f"☯ **Vé Tẩy Tủy Phù:** `{player.tay_tuy_phu}` vé\n"
                            f"💎 **Tiên Ngọc có sẵn:** `{player.tien_ngoc:,}`\n\n"
                            f"📜 **Chi phí:** `1x Tẩy Tủy Phù` hoặc `100 Tiên Ngọc` / lượt\n"
                            f"🎁 **Hiệu quả:** Tẩy lại Linh Căn Phẩm Cấp (Tiên/Thánh/Hỗn Độn) & Dị Linh Căn (⚡ Lôi, ❄️ Băng, 🌪️ Phong, 🌌 Không Gian)!",
                color=discord.Color.purple()
            )

        embed.set_footer(text="Chọn nút Banner bên dưới để đổi xem banner khác | Bấm Quay 1x hoặc Quay 10x để mở rương!")
        return embed

    def get_banner_file_and_embed(self) -> Tuple[Optional[discord.File], discord.Embed]:
        embed = self.get_embed()
        img_path = BANNER_IMAGES.get(self.current_banner)
        if img_path and os.path.exists(img_path):
            filename = f"banner_{self.current_banner}.jpg"
            file = discord.File(img_path, filename=filename)
            embed.set_image(url=f"attachment://{filename}")
            return file, embed
        return None, embed

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Bạn không thể thao tác trên bảng Gacha của người khác!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🏮 Tụ Bảo Các (Thường)", style=discord.ButtonStyle.success, row=0)
    async def btn_tubao(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_banner = "tubao"
        self._update_button_styles()
        file, embed = self.get_banner_file_and_embed()
        if file:
            await interaction.response.edit_message(embed=embed, view=self, attachments=[file])
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🌟 Tiên Các (VIP)", style=discord.ButtonStyle.secondary, row=0)
    async def btn_tiencac(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_banner = "tiencac"
        self._update_button_styles()
        file, embed = self.get_banner_file_and_embed()
        if file:
            await interaction.response.edit_message(embed=embed, view=self, attachments=[file])
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="☯ Cải Mệnh Đài", style=discord.ButtonStyle.secondary, row=0)
    async def btn_caimenh(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_banner = "caimenh"
        self._update_button_styles()
        file, embed = self.get_banner_file_and_embed()
        if file:
            await interaction.response.edit_message(embed=embed, view=self, attachments=[file])
        else:
            await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🎲 Quay 1 Lần (1x)", style=discord.ButtonStyle.primary, row=1)
    async def btn_roll_1x(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_roll(interaction, 1)

    @discord.ui.button(label="⚡ Quay 10 Lần (10x)", style=discord.ButtonStyle.danger, row=1)
    async def btn_roll_10x(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self._execute_roll(interaction, 10)

    async def _execute_roll(self, interaction: discord.Interaction, roll_count: int):
        player = self.db.get_player(self.user_id)
        if not player:
            await interaction.response.send_message("❌ Vui lòng gõ `!nhapmon` trước!", ephemeral=True)
            return

        success, msg, roll_results, updated_player = process_gacha_rolls(self.db, player, self.current_banner, roll_count)
        if not success:
            await interaction.response.send_message(msg, ephemeral=True)
            return

        # Format Result Embed
        banner_name = GACHA_BANNERS.get(self.current_banner, {}).get("name", "Banner")
        res_embed = discord.Embed(
            title=f"✨ KẾT QUẢ QUAY GACHA — {banner_name}",
            description=f"Tu sĩ **[{updated_player.dao_hieu}]** vừa mở rương! (Pity: `{updated_player.soft_pity_count}/80`)",
            color=discord.Color.gold()
        )

        has_ur = False
        ur_items = []
        for idx, res in enumerate(roll_results, 1):
            val_str = f"> Phẩm cấp: `{res['grade']}`"
            if res.get("duplicate_converted"):
                val_str += f" *(Trùng! Chuyển thành +{res['duplicate_converted']} Linh Bụi)*"

            res_embed.add_field(name=f"[{idx}] {res['item_name']}", value=val_str, inline=False)
            if res.get("is_ur"):
                has_ur = True
                ur_items.append(res["item_name"])

        # Update the main gacha status embed
        file, embed = self.get_banner_file_and_embed()
        if file:
            await interaction.response.edit_message(embed=embed, view=self, attachments=[file])
        else:
            await interaction.response.edit_message(embed=embed, view=self)

        await interaction.followup.send(embed=res_embed)

        if has_ur:
            flex_msg = f"💥 **[THIÊN ĐẠO DIỆU BIẾN]**: Tu sĩ <@{self.user_id}> vừa gặp đại cơ duyên tại Tiên Các rút thành công **{', '.join(ur_items)}**! Toàn thể tu sĩ bái phục!"
            await interaction.followup.send(flex_msg)


class TuTienCog(commands.Cog, name="TuTien"):

    """
    Hệ thống Tu Tiên: «ĐẠI ĐẠO TRANH PHONG» (Prefix Commands + Gacha Engine + PVE System)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = TuTienDB()
        self.ho_phap_registry = {}  # {target_user_id: guardian_user_id}
        self.last_tam_ma_notice = {}  # {user_id: last_notification_timestamp}
        self.last_cuop_time = {}  # {user_id: last_cuop_timestamp}
        
        wb = self.db.get_world_boss()
        self.world_boss_max_hp = wb.get("max_hp", 10000000)
        self.world_boss_hp = wb.get("hp", 10000000)
        self.world_boss_name = wb.get("name", "👹 Ma Vương Cổ Đại — Vô Cực Thi Cụ")
        self.active_party_rooms = {}  # {channel_id: PartyLobbyView}
        self.bg_recovery_task.start()
        self.bg_retention_guard.start()

    def cog_unload(self):
        self.bg_recovery_task.cancel()
        self.bg_retention_guard.cancel()

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        orig = getattr(error, 'original', error)
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Thiếu tham số bắt buộc! Cú pháp đúng: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(f"❌ Tham số nhập vào không hợp lệ! Cú pháp: `{ctx.prefix}{ctx.command.name} {ctx.command.signature}`")
        elif isinstance(error, commands.NotOwner):
            await ctx.send("❌ Lệnh này chỉ dành cho Chủ Bot!")
        elif isinstance(error, commands.CommandOnCooldown):
            await ctx.send(f"⏳ Vui lòng chờ `{error.retry_after:.1f}s` trước khi tiếp tục dùng lệnh này.")
        elif isinstance(orig, commands.CheckFailure):
            return
        else:
            print(f"[TuTien] Command error in {ctx.command}: {orig}")
            await ctx.send(f"⚠️ **Lỗi thực thi lệnh:** `{orig}`")

    # --- BACKGROUND TASKS ---
    @tasks.loop(minutes=5)
    async def bg_recovery_task(self):
        """Phục hồi Tinh Lực (+2/5p = +24/h) & Linh Khí Kênh (+416/5p = +5000/h) định kỳ."""
        await self.bot.wait_until_ready()
        try:
            self.db.recover_all_players_tinh_luc(2)
            self.db.recover_all_channels_linh_khi(416)
        except Exception as e:
            print(f"[TuTien] Error in recovery task: {e}")

    @tasks.loop(minutes=5)
    async def bg_retention_guard(self):
        """Check AFK meditation completion cho tu sĩ bế quan."""
        await self.bot.wait_until_ready()
        try:
            now = time.time()
            finished_notifications = []

            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, meditate_start_time, meditate_duration_hours, is_vip_pass, realm_index FROM tutien_players WHERE is_meditating = 1")
                meditating_players = [dict(r) for r in cursor.fetchall()]

                for row in meditating_players:
                    u_id = row["user_id"]
                    start_t = row["meditate_start_time"]
                    duration_h = row["meditate_duration_hours"] or 1
                    is_vip_pass = row["is_vip_pass"]
                    realm_idx = row["realm_index"]

                    # 1. Kiểm tra hoàn thành bế quan AFK khi đủ thời gian
                    if start_t and (now - start_t >= duration_h * 3600):
                        # AFK EXP scale cùng formula exponential với active cultivation
                        # ~30 lần tu luyện/giờ, có bonus VIP 7 (+30%) sẽ apply sau
                        base_afk_per_hour = int(200 * (1.4 ** realm_idx) * 30)
                        exp_gain = int(base_afk_per_hour * duration_h)
                        linh_thach_gain = int(800 * duration_h * (1 + realm_idx * 0.05))
                        tam_canh_gain = min(100.0, duration_h * 2.0)
                        can_co_gain = round(duration_h * 10.0, 1)
                        hp_ratio = min(1.0, duration_h / 4.0)

                        res_cursor = conn.execute(
                            "UPDATE tutien_players SET is_meditating = 0, meditate_start_time = NULL, meditate_duration_hours = 0, "
                            "last_meditation_end = ?, continuous_cultivation_count = 0, linh_luc_tap_chat = 0, "
                            "hp = MIN(max_hp, hp + CAST(max_hp * ? AS INTEGER)), mana = MIN(max_mana, mana + CAST(max_mana * ? AS INTEGER)), "
                            "can_co = MIN(100.0, can_co + ?), exp = exp + ?, linh_thach = linh_thach + ?, tam_canh = MIN(100.0, tam_canh + ?) "
                            "WHERE user_id = ? AND is_meditating = 1",
                            (now, hp_ratio, hp_ratio, can_co_gain, exp_gain, linh_thach_gain, tam_canh_gain, u_id)
                        )
                        if res_cursor.rowcount > 0:
                            finished_notifications.append((u_id, duration_h, exp_gain, linh_thach_gain, tam_canh_gain))
                        continue

                    # 2. Tu sĩ đang bế quan được thưởng thêm +5 Tinh Lực mỗi 5 phút
                    conn.execute(
                        "UPDATE tutien_players SET tinh_luc = CASE WHEN (tinh_luc + 5) > max_tinh_luc THEN max_tinh_luc ELSE (tinh_luc + 5) END WHERE user_id = ?",
                        (u_id,)
                    )

                    if is_vip_pass:
                        conn.execute("UPDATE tutien_players SET dao_tam = dao_tam + 5 WHERE user_id = ?", (u_id,))

            # DB context closed and committed here BEFORE async network calls

            # Send finished meditation DMs
            for u_id, duration_h, exp_gain, linh_thach_gain, tam_canh_gain in finished_notifications:
                try:
                    user = self.bot.get_user(u_id) or await self.bot.fetch_user(u_id)
                    if user:
                        await user.send(
                            f"🎉 **VIÊN MÃN XUẤT QUAN!** Bạn đã hoàn tất **{duration_h} Giờ** bế quan nhập định!\n"
                            f"🎁 Phần thưởng AFK: `+{exp_gain:,}` Tu Vi | `+{linh_thach_gain:,}` Linh Thạch | `+{tam_canh_gain:.1f}%` Tâm Cảnh!"
                        )
                except Exception:
                    pass

        except Exception as e:
            print(f"[TuTien] Retention guard error: {e}")

    # --- 🔮 GACHA 3 BANNERS COMMANDS ---

    @commands.command(
        name="banner",
        aliases=["banners", "ds-banner", "gacha-info", "cac-banner"],
        brief="Xem danh sách 3 Đại Banners Gacha («THIÊN ĐỊA DUYÊN CƠ») tương tác nút bấm.",
        usage="banner"
    )
    async def banner_cmd(self, ctx: commands.Context):
        """Xem danh sách 3 Đại Banners Gacha & tương tác quay qua nút bấm."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        view = GachaInteractiveView(self, ctx.author.id, self.db, initial_banner="tubao")
        file, embed = view.get_banner_file_and_embed()
        if file:
            await ctx.send(file=file, embed=embed, view=view)
        else:
            await ctx.send(embed=embed, view=view)

    @commands.command(
        name="quay-gacha",
        aliases=["gacha", "quaygacha"],
        brief="Mở giao diện quay Gacha tương tác nút bấm (Chọn Banner, Quay 1x/10x).",
        usage="quay-gacha [tubao|tiencac|caimenh] [1x|10x]"
    )
    async def quay_gacha_cmd(self, ctx: commands.Context, banner: str = "tubao", rolls: str = None):
        """Quay Gacha Ba Đại Banners (Giao diện tương tác nút bấm)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        # Normalize banner name if provided
        b_raw = banner.lower().strip() if banner else "tubao"
        if b_raw in ["tubao", "thuong", "f2p", "linh-duyen", "linhduyen", "1", "tu-bao"]:
            banner_key = "tubao"
        elif b_raw in ["tiencac", "vip", "premium", "tien-duyen", "tienduyen", "2", "tien-cac"]:
            banner_key = "tiencac"
        elif b_raw in ["caimenh", "taytuy", "tay-tuy", "reroll", "3", "cai-menh"]:
            banner_key = "caimenh"
        elif b_raw in ["10x", "10", "1x", "1"]:
            rolls = b_raw
            banner_key = "tubao"
        else:
            banner_key = "tubao"

        # If rolls is specified (e.g. !gacha tiencac 10x), execute directly
        if rolls:
            roll_count = 10 if "10" in rolls else 1
            success, title_msg, roll_results, updated_player = process_gacha_rolls(self.db, player, banner_key, roll_count)
            if not success:
                await ctx.send(title_msg)
                return

            embed = discord.Embed(
                title=f"✨ KẾT QUẢ QUAY GACHA — {GACHA_BANNERS.get(banner_key, {}).get('name', 'Banner')}",
                description=f"Tu sĩ **[{updated_player.dao_hieu}]** vừa mở rương! (Pity: `{updated_player.soft_pity_count}/80`)",
                color=discord.Color.gold()
            )
            has_ur = False
            ur_items = []
            for idx, res in enumerate(roll_results, 1):
                val_str = f"> Phẩm cấp: `{res['grade']}`"
                if res.get("duplicate_converted"):
                    val_str += f" *(Trùng! +{res['duplicate_converted']} Linh Bụi)*"
                embed.add_field(name=f"[{idx}] {res['item_name']}", value=val_str, inline=False)
                if res.get("is_ur"):
                    has_ur = True
                    ur_items.append(res["item_name"])

            await ctx.send(embed=embed)
            if has_ur:
                flex_msg = f"💥 **[THIÊN ĐẠO DIỆU BIẾN]**: Tu sĩ {ctx.author.mention} vừa gặp đại cơ duyên tại Tiên Các rút thành công **{', '.join(ur_items)}**! Toàn thể tu sĩ bái phục!"
                await ctx.send(flex_msg)
            return

        # Default: Open Interactive View with selected banner
        view = GachaInteractiveView(self, ctx.author.id, self.db, initial_banner=banner_key)
        file, embed = view.get_banner_file_and_embed()
        if file:
            await ctx.send(file=file, embed=embed, view=view)
        else:
            await ctx.send(embed=embed, view=view)

    @commands.command(
        name="xienquach",
        aliases=["quere", "bocque"],
        brief="Bốc quẻ Khí Vận hàng ngày nhận Linh Duyên Phù & Tiên Ngọc.",
        usage="xienquach"
    )
    async def xienquach_cmd(self, ctx: commands.Context):
        """Bốc quẻ Khí Vận hàng ngày, nhận vé quay chay (Linh Duyên Phù & Tiên Duyên Phù)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.last_daily_fortune and (now - player.last_daily_fortune < 86400):
            remain_h = int((86400 - (now - player.last_daily_fortune)) / 3600)
            await ctx.send(f"❌ Hôm nay bạn đã bốc quẻ rồi! Vui lòng chờ `{remain_h}` giờ nữa.")
            return

        player.last_daily_fortune = now
        player.linh_duyen_phu += 1
        player.tien_ngoc += 20
        self.db.update_player(player)

        embed = discord.Embed(title="🔮 BỐC QUẺ KHÍ VẬN HÀNG NGÀY 🔮", color=discord.Color.purple())
        embed.add_field(name="📜 Quẻ Số", value="**ĐẠI CÁT** — *Linh quang hội tụ, hành trình tu tiên vạn sự như ý!*", inline=False)
        embed.add_field(name="🎁 Phần Thưởng", value="`+1` Linh Duyên Phù (Vé quay Gacha F2P) | `+20` Tiên Ngọc", inline=False)
        await ctx.send(embed=embed)

    @commands.command(
        name="wishlist",
        aliases=["dinh-huong"],
        brief="Thiết lập Định Hướng Đạo Vận (Wishlist UR) cho Banner Tiên Các.",
        usage="wishlist [tên_vật_phẩm]"
    )
    async def wishlist_cmd(self, ctx: commands.Context, *, item_name: str = None):
        """Thiết lập Định Hướng Đạo Vận (Wishlist) cho Banner Tiên Các."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if not item_name:
            current_w = player.wishlist_item if player.wishlist_item else "Chưa thiết lập"
            await ctx.send(f"🎯 **ĐỊNH HƯỚNG ĐẠO VẬN HIỆN TẠI:** **[{current_w}]**\nCú pháp đổi: `!wishlist [Tên_Vật_Phẩm]`.")
            return

        player.wishlist_item = item_name
        self.db.update_player(player)
        await ctx.send(f"🎯 **ĐÃ THIẾT LẬP WISH LIST!** Lượt Đế Cấp (UR) tiếp theo nếu bị lệch rate chắc chắn 100% sẽ ra **[{item_name}]**!")

    @commands.command(
        name="linhbui-shop",
        aliases=["doilinhbui", "shard-shop"],
        brief="Xem & Đổi Linh Bụi Tiên Các lấy vật phẩm UR/SR tự chọn.",
        usage="linhbui-shop [tên_vật_phẩm]"
    )
    async def linhbui_shop_cmd(self, ctx: commands.Context, item_name: str = None):
        """Xem & Đổi Linh Bụi Tiên Các lấy vật phẩm UR/SR tự chọn."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if not item_name:
            embed = discord.Embed(
                title="✨ SHOP LINH BỤI TIÊN CÁC (SHARD SHOP) ✨",
                description=f"Điểm Linh Bụi hiện có: `✨ {player.linh_bui}` Linh Bụi\nCú pháp đổi: `!linhbui-shop [Tên_Item]`",
                color=discord.Color.blue()
            )
            for name, info in LINH_BUI_SHOP.items():
                embed.add_field(name=f"✨ {name} — {info['cost']} Linh Bụi", value=f"> *{info['desc']}*", inline=False)
            await ctx.send(embed=embed)
            return

        if item_name not in LINH_BUI_SHOP:
            await ctx.send(f"❌ Vật phẩm **[{item_name}]** không có trong Shop Linh Bụi!")
            return

        info = LINH_BUI_SHOP[item_name]
        if player.linh_bui < info["cost"]:
            await ctx.send(f"❌ Không đủ Linh Bụi! Cần `{info['cost']}` Linh Bụi (Hiện có: `{player.linh_bui}`).")
            return

        player.linh_bui -= info["cost"]
        self.db.add_item(player.user_id, item_name, info["type"], 1)
        self.db.update_player(player)

        await ctx.send(f"✨ **ĐỔI LINH BỤI THÀNH CÔNG!** Đã đổi thành công **[{item_name}]** vào Túi Đồ!")

    # --- 📂 MONETIZATION & SHOP TIÊN CÁC COMMANDS ---

    @commands.command(
        name="nap-tien",
        aliases=["naptutien", "napngoc"],
        brief="[Admin/Owner] Nạp Tiên Ngọc & Tích Nạp VIP cho người chơi.",
        usage="nap-tien @user <số_lượng>"
    )
    @commands.is_owner()
    async def naptien_cmd(self, ctx: commands.Context, target: discord.Member, amount: int):
        """[Admin/Owner Only] Nạp Tiên Ngọc & Tích Nạp VIP cho người chơi."""
        player = self.db.get_player(target.id)
        if not player:
            await ctx.send("❌ Người chơi chưa nhập môn Tu Tiên!")
            return

        updated_player, vip_upgraded = grant_topup_and_vip_exp(player, amount)
        self.db.update_player(updated_player)

        msg = f"💳 **NẠP TIÊN NGỌC THÀNH CÔNG!** Đã nạp `{amount:,}` Tiên Ngọc cho tu sĩ **[{target.display_name}]**!"
        if vip_upgraded:
            msg += f"\n🎉 **THẮNG CẤP VIP!** Đã thăng cấp lên **[VIP {updated_player.vip_level}]** ({VIP_LEVELS[updated_player.vip_level]['name']})!"

        await ctx.send(msg)

    @commands.command(
        name="tutien-reset",
        aliases=["ttreset", "reset-tutien", "reset-player"],
        brief="[Admin/Owner] Reset toàn bộ dữ liệu Tu Tiên của 1 người chơi.",
        usage="tutien-reset @user"
    )
    @commands.is_owner()
    async def reset_player_cmd(self, ctx: commands.Context, target: discord.Member):
        """[Owner Admin] Reset toàn bộ hồ sơ Tu Tiên của người chơi."""
        player = self.db.get_player(target.id)
        if not player:
            await ctx.send(f"❌ Tu sĩ **{target.display_name}** chưa từng nhập môn Tu Tiên!")
            return

        self.db.delete_player(target.id)
        embed = discord.Embed(
            title="🧹 [OWNER ADMIN] RESET DỮ LIỆU THÀNH CÔNG!",
            description=f"Đã phế bỏ và xóa sạch 100% dữ liệu Tu Tiên của tu sĩ **[{player.dao_hieu}]** (`{target.display_name}`).\n"
                        f"> 📜 Người chơi có thể gõ `!nhapmon` để khởi tạo lại nhân vật từ đầu.",
            color=discord.Color.red()
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="set-linh-thach",
        aliases=["setlt", "setlinhthach"],
        brief="[Admin/Owner] Thay đổi số Linh Thạch của người chơi.",
        usage="set-linh-thach @user [số_lượng]"
    )
    @commands.is_owner()
    async def set_linh_thach_cmd(self, ctx: commands.Context, target: discord.Member, amount: int):
        """[Owner Admin] Set Linh Thạch cho người chơi."""
        player = self.db.get_player(target.id)
        if not player:
            await ctx.send(f"❌ Tu sĩ **{target.display_name}** chưa nhập môn!")
            return

        player.linh_thach = max(0, amount)
        self.db.update_player(player)

        embed = discord.Embed(
            title="💰 [OWNER ADMIN] SET LINH THẠCH THÀNH CÔNG!",
            description=f"Đã đặt Linh Thạch của tu sĩ **[{player.dao_hieu}]** thành **`{player.linh_thach:,}` Linh Thạch**!",
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="set-tien-ngoc",
        aliases=["setngoc", "settienngoc"],
        brief="[Admin/Owner] Thay đổi số Tiên Ngọc (Nạp) của người chơi.",
        usage="set-tien-ngoc @user [số_lượng]"
    )
    @commands.is_owner()
    async def set_tien_ngoc_cmd(self, ctx: commands.Context, target: discord.Member, amount: int):
        """[Owner Admin] Set Tiên Ngọc cho người chơi."""
        player = self.db.get_player(target.id)
        if not player:
            await ctx.send(f"❌ Tu sĩ **{target.display_name}** chưa nhập môn!")
            return

        player.tien_ngoc = max(0, amount)
        self.db.update_player(player)

        embed = discord.Embed(
            title="💎 [OWNER ADMIN] SET TIÊN NGỌC THÀNH CÔNG!",
            description=f"Đã đặt Tiên Ngọc của tu sĩ **[{player.dao_hieu}]** thành **`{player.tien_ngoc:,}` Tiên Ngọc**!",
            color=discord.Color.blue()
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="give-item",
        aliases=["chodo", "chovatpham", "additem"],
        brief="[Admin/Owner] Ban tặng vật phẩm / bùa cho người chơi.",
        usage="give-item @user [tên_item] [số_lượng]"
    )
    @commands.is_owner()
    async def give_item_cmd(self, ctx: commands.Context, target: discord.Member, item_name: str, amount: int = 1):
        """[Owner Admin] Ban tặng vật phẩm cho người chơi."""
        player = self.db.get_player(target.id)
        if not player:
            await ctx.send(f"❌ Tu sĩ **{target.display_name}** chưa nhập môn!")
            return

        name_lower = item_name.lower()
        if "van linh" in name_lower or "vanlinh" in name_lower:
            player.van_linh_dan += amount
            self.db.update_player(player)
            item_desc = f"x{amount} Vạn Linh Đan"
        elif "thanh the" in name_lower or "thanhthe" in name_lower:
            player.thanh_the_phu += amount
            self.db.update_player(player)
            item_desc = f"x{amount} Thánh Thể Phù"
        elif "cuu chuyen" in name_lower or "cuuchuyen" in name_lower:
            player.cuu_chuyen_dan += amount
            self.db.update_player(player)
            item_desc = f"x{amount} Cửu Chuyển Tái Tạo Đan"
        elif "linh duyen" in name_lower:
            player.linh_duyen_phu += amount
            self.db.update_player(player)
            item_desc = f"x{amount} Linh Duyên Phù"
        elif "tien duyen" in name_lower:
            player.tien_duyen_phu += amount
            self.db.update_player(player)
            item_desc = f"x{amount} Tiên Duyên Phù"
        else:
            self.db.add_item(target.id, item_name, "Bảo Vật Admin Ban Tặng", amount)
            item_desc = f"x{amount} {item_name}"

        embed = discord.Embed(
            title="🎁 [OWNER ADMIN] BAN TẶNG VẬT PHẨM THÀNH CÔNG!",
            description=f"Đã ban tặng **{item_desc}** cho tu sĩ **[{player.dao_hieu}]**!",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="tiencac",
        aliases=["tiencac-shop", "tiên-các"],
        brief="Xem danh mục Shop Tiên Các (mua bằng Tiên Ngọc).",
        usage="tiencac"
    )
    async def tiencac_cmd(self, ctx: commands.Context):
        """Xem danh mục Shop Tiên Các (Mua bằng Tiên Ngọc)."""
        player = self.db.get_player(ctx.author.id)
        tien_ngoc_str = f"{player.tien_ngoc:,}" if player else "0"

        embed = discord.Embed(
            title="🌌 TIÊN CÁC THIÊN BẢO SHOP 🌌",
            description=f"Số Tiên Ngọc hiện có: 🌟 **{tien_ngoc_str} Tiên Ngọc**\nCú pháp mua: `!mua [Tên_Vật_Phẩm]`",
            color=discord.Color.gold()
        )

        for item_name, item_info in TIEN_CAC_SHOP.items():
            embed.add_field(
                name=f"🛍️ {item_name} — 🌟 {item_info['price']} Tiên Ngọc",
                value=f"> *{item_info['desc']}*\n> Loại: `{item_info['category']}`",
                inline=False
            )

        embed.set_footer(text="Nạp Tiên Ngọc liên hệ Admin Server! Gõ !gacha để quay bảo vật.")
        await ctx.send(embed=embed)

    @commands.command(
        name="mua",
        aliases=["muatiencac", "mua-tiencac"],
        brief="Mua vật phẩm từ Shop Tiên Các bằng Tiên Ngọc.",
        usage="mua <tên_vật_phẩm>"
    )
    async def mua_cmd(self, ctx: commands.Context, *, item_name: str):
        """Mua vật phẩm từ Tiên Các Shop bằng Tiên Ngọc."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        success, msg, updated_player = buy_tiencac_item(self.db, player, item_name)
        await ctx.send(msg)

    @commands.command(
        name="vip",
        aliases=["the-thang", "thethang"],
        brief="Xem Cấp độ VIP & Trạng thái Thẻ Tháng Đạo Tâm Tôn Giả.",
        usage="vip"
    )
    async def vip_cmd(self, ctx: commands.Context):
        """Xem Cấp độ VIP & Trạng thái Thẻ Tháng Đạo Tâm Tôn Giả."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        vip_info = VIP_LEVELS.get(player.vip_level, VIP_LEVELS[0])
        next_vip_exp = VIP_LEVELS.get(min(10, player.vip_level + 1), VIP_LEVELS[10])["req_exp"]

        embed = discord.Embed(title=f"👑 VIP & ĐẶC QUYỀN — {player.dao_hieu}", color=discord.Color.gold())
        embed.add_field(name="👑 Cấp Đội VIP", value=f"**{vip_info['name']}** (Điểm Tích Nạp: `{player.vip_exp}/{next_vip_exp}`)", inline=False)
        embed.add_field(name="✨ Đặc Quyền VIP", value=f"> {vip_info['benefits']}", inline=False)
        
        pass_status = "✅ Đang Kích Hoạt (Auto-Định Tâm AFK)" if player.is_vip_pass else "❌ Chưa Kích Hoạt (Mua tại !tiencac)"
        embed.add_field(name="📜 Thẻ Tháng Đạo Tâm Tôn Giả", value=pass_status, inline=False)

        await ctx.send(embed=embed)

    # --- 📂 NHÓM LỆNH [/nhan-vat] ---

    @commands.command(
        name="nhapmon",
        aliases=["taonhanvat", "nhap-mon"],
        brief="Nhập môn Tu Tiên, khởi tạo Linh Căn ngẫu nhiên.",
        usage="nhapmon [đạo_hiệu]"
    )
    async def nhapmon_cmd(self, ctx: commands.Context, *, dao_hieu: str = None):
        """Nhập môn Tu Tiên, khởi tạo Linh Căn ngẫu nhiên."""
        player = self.db.get_player(ctx.author.id)
        if player:
            await ctx.send(f"❌ Khái niệm Nhân Quả đã định! Đạo hữu **{player.dao_hieu}** đã gia nhập giới Tu Tiên rồi!")
            return

        if not dao_hieu:
            dao_hieu = ctx.author.display_name

        quality, element, is_di = roll_spiritual_root()
        player = self.db.create_player(ctx.author.id, ctx.guild.id if ctx.guild else 0, dao_hieu, quality, element, is_di)

        # --- Apply Element Buff ngay khi nhập môn ---
        elem_bonuses = []
        if "Ộc" in element or "Moc" in element:
            # Mộc: +25% Max HP ngay từ đầu
            bonus_hp = int(player.max_hp * 0.25)
            player.max_hp += bonus_hp
            player.hp += bonus_hp
            self.db.update_player(player)
            elem_bonuses.append(f"🌳 **Mộc Hệ:** +{bonus_hp} Max HP (tổng: {player.max_hp})")
        elif "Thủy" in element:
            elem_bonuses.append("💧 **Thủy Hệ:** +10% Tâm Cảnh khi Nhập Định AFK, +15% Hồi Phục HP/MP mỗi lượt PVE")

        embed = discord.Embed(
            title="☯ THIÊN ĐẠO CHỨNG GIÁM: NHẬP MÔN THÀNH CÔNG! ☯",
            description=f"Chúc mừng Đạo hữu **[{dao_hieu}]** đã bước chân vào con đường trường sinh!",
            color=discord.Color.gold()
        )
        embed.add_field(name="⚡ Phẩm Cấp Linh Căn", value=f"**{quality}**", inline=True)
        embed.add_field(name="🔮 Thuộc Tính", value=f"**{element}**", inline=True)
        embed.add_field(name="💰 Tài Bảo Nhập Môn", value="`500` Linh Thạch | `100` Tinh Lực", inline=False)
        if elem_bonuses:
            embed.add_field(name="✨ Hiệu Ứng Linh Căn Kích Hoạt", value="\n".join(elem_bonuses), inline=False)
        embed.set_footer(text="Gõ !tutien-profile để xem hồ sơ PNG hoặc gõ !huongdan để xem cẩm nang tân thủ!")
        await ctx.send(embed=embed)

    @commands.command(
        name="tutien-huongdan",
        aliases=["huongdan", "tutienhelp", "tuhds"],
        brief="Xem Cẩm Nang Hướng Dẫn Tu Tiên Toàn Tập (Nút bấm sang trang 1/7 - 7/7).",
        usage="tutien-huongdan [trang]"
    )
    async def huongdan_cmd(self, ctx: commands.Context, page: int = 1):
        """Cẩm Nang Hướng Dẫn Tu Tiên Chi Tiết Toàn Tập với nút bấm sang trang (!huongdan)."""
        page = max(1, min(7, page))
        view = TutienGuidePaginatorView(current_page=page, timeout=180.0)
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(
        name="tutien-profile",
        aliases=["tutienprofile", "hoso-tutien", "nhanvat-tutien"],
        brief="Xem 18 thuộc tính nhân vật dạng Thẻ Hình Ảnh PNG Nghệ Thuật.",
        usage="tutien-profile [@user]"
    )
    async def profile_cmd(self, ctx: commands.Context, target: discord.Member = None):
        """Xem 18 thuộc tính nhân vật dạng Thẻ Hình Ảnh PNG Nghệ Thuật (Pillow)."""
        target_user = target or ctx.author
        player = self.db.get_player(target_user.id)
        if not player:
            await ctx.send(f"❌ Người dùng {target_user.mention} chưa nhập môn Tu Tiên! (Gõ `!nhapmon [Đạo Hiệu]`)")
            return

        avatar_bytes = None
        try:
            avatar_bytes = await target_user.display_avatar.with_format("png").read()
        except Exception:
            pass

        gf = self.db.get_gongfa(target_user.id)
        gongfa_name = getattr(gf, "chu_tu", None) if gf else None
        img_buf = render_tutien_profile_card(player, avatar_bytes, gongfa_name=gongfa_name)
        file = discord.File(fp=img_buf, filename=f"profile_{player.user_id}.png")
        await ctx.send(file=file)

    @commands.command(
        name="tamcanh",
        aliases=["can-co", "tam-canh"],
        brief="Kiểm tra trạng thái Tâm Cảnh & độ vững chắc Căn Cơ.",
        usage="tamcanh"
    )
    async def tamcanh_cmd(self, ctx: commands.Context):
        """Kiểm tra trạng thái Tâm Cảnh & Căn Cơ."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        req_tc = REALM_REQUIRED_TAM_CANH.get(player.realm_index, 50)
        chance = calculate_breakthrough_chance(player)

        embed = discord.Embed(title=f"🧘 TÂM CẢNH & CĂN CƠ — {player.dao_hieu}", color=discord.Color.purple())
        embed.add_field(name="🧘 Tâm Cảnh Hiện Tại", value=f"`{player.tam_canh:.1f}%` / Cần: `{req_tc}%`", inline=True)
        embed.add_field(name="🛡️ Điểm Căn Cơ", value=f"`{player.can_co:.1f}%` (Vững Chắc)", inline=True)
        embed.add_field(name="⚡ Tỷ Lệ Đột Phá Dự Kiến", value=f"**{chance:.1f}%**", inline=False)
        await ctx.send(embed=embed)

    @commands.command(
        name="phe-tu-vi",
        aliases=["phetuvi"],
        brief="Phế bỏ toàn bộ tu vi hiện tại để tu luyện lại từ đầu.",
        usage="phe-tu-vi"
    )
    async def phe_tu_vi_cmd(self, ctx: commands.Context):
        """Phế bỏ toàn bộ tu vi hiện tại để tu luyện lại từ đầu."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        player.realm_index = 0
        player.exp = 0
        player.body_realm_index = 0
        player.can_co = 80.0
        player.tam_canh = 70.0
        player.max_hp = 1000
        player.hp = 1000
        player.max_mana = 500
        player.mana = 500
        player.than_thuc = 50
        player.active_dao_domain = None
        self.db.update_player(player)

        await ctx.send(f"💥 **PHẾ VỊ THÀNH CÔNG!** Tu sĩ **{player.dao_hieu}** đã phế sạch Tu Vi & Thân Thể, quay về Luyện Khí Tầng 1 để đúc lại Căn Cơ!")

    # --- 📂 NHÓM LỆNH [/tu-luyen] ---

    @commands.command(
        name="tu-luyen",
        aliases=["tuluyen", "train"],
        brief="Tu luyện chủ động tiêu hao 15 Tinh Lực.",
        usage="tu-luyen"
    )
    async def tuluyen_cmd(self, ctx: commands.Context):
        """Tu luyện chủ động (Tiêu hao 15 Tinh Lực)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon [Đạo Hiệu]` trước!")
            return

        now = time.time()
        if player.kinh_mach_doan_tuyet_until and player.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy nhờ đạo hữu dùng `!cuu-thuong @user` hoặc mua Cửu Chuyển Tái Tạo Đan tại `!tiencac` để phục hồi trước khi tu luyện!")
            return

        if player.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG BẾ QUAN!** Vui lòng gõ `!xuat-quan` trước khi tu luyện chủ động.")
            return

        gongfa = self.db.get_gongfa(ctx.author.id)
        channel_id = ctx.channel.id
        channel_linh_khi = self.db.get_channel_linh_khi(channel_id)

        res, updated_player = process_active_cultivation(player, gongfa, channel_linh_khi)
        if not res["success"]:
            await ctx.send(f"❌ {res['reason']}")
            return

        # Tiêu hao 1,000 Linh Khí Kênh (Khai thác địa mạch)
        self.db.consume_channel_linh_khi(channel_id, 1000)

        # Tích tụ Tạp Chất Linh Lực nếu tu luyện liên tục > 10 lần không bế quan
        updated_player.continuous_cultivation_count = getattr(updated_player, 'continuous_cultivation_count', 0) + 1
        is_new_tap_chat = False
        if updated_player.continuous_cultivation_count >= 10 and not updated_player.linh_luc_tap_chat:
            updated_player.linh_luc_tap_chat = True
            is_new_tap_chat = True

        self.db.update_player(updated_player)

        # --- Quest Tracking: Chuyên Tâm Tu Đạo ---
        completed_q = self.db.increment_quest_progress(ctx.author.id, "tu_luyen")
        if completed_q:
            await ctx.send(
                f"🏆 **ĐẠO VỤ HOÀN THÀNH!** `{completed_q['quest_name']}` — Gõ `!dao-vu` để nhận thưởng!"
            )

        msg = f"🧘 **[{player.dao_hieu}]** tiến hành bế quan vận công...\n> {res['message']}\n"
        msg += f"📊 **Tu Vi:** `{updated_player.exp:,}` / `{res['required_exp']:,}` | 🔥 **Tinh Lực còn:** `{updated_player.tinh_luc}/100`"

        if updated_player.linh_luc_tap_chat:
            msg += "\n⚠️ **LINH LỰC TẠP CHẤT!** Bạn đã tu luyện quá nhiều liên tục mà chưa bế quan thanh lọc (-50% EXP, -20% Đột Phá)! Hãy gõ `!nhap-dinh` để bài trừ tạp chất."
        elif is_new_tap_chat:
            msg += "\n⚠️ **CẢNH BÁO:** Cơ thể bắt đầu tích tụ **Linh Lực Tạp Chất**! Hãy bế quan hoặc dùng đan dược để thanh lọc."

        if res["can_breakthrough"]:
            msg += "\n⚡ **TU VI ĐÃ MÃN!** Hãy gõ `!dotpha` để xung kích bình cảnh!"

        await ctx.send(msg)


    @commands.command(
        name="nhap-dinh",
        aliases=["nhapdinh", "bequan"],
        brief="Bế quan AFK tích lũy tài nguyên (1h, 4h, 8h, 12h, 24h).",
        usage="nhap-dinh [số_giờ]"
    )
    async def nhapdinh_cmd(self, ctx: commands.Context, hours: int = 1):
        """Bế quan AFK tích lũy tài nguyên (1h, 4h, 8h, 12h, 16h, 24h)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.kinh_mach_doan_tuyet_until and player.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy phục hồi trước khi bế quan!")
            return

        if player.is_meditating:
            await ctx.send("⚠️ **BẠN ĐANG TRONG TRẠNG THÁI BẾ QUAN!** Vui lòng gõ `!xuat-quan` để thu công nhận quà AFK trước khi bắt đầu lượt bế quan mới!")
            return

        # Cooldown 10 phút giữa các lần bế quan
        MEDITATION_COOLDOWN = 600
        if player.last_meditation_end and (now - player.last_meditation_end) < MEDITATION_COOLDOWN:
            remain_min = int((MEDITATION_COOLDOWN - (now - player.last_meditation_end)) // 60) + 1
            await ctx.send(f"⏳ **CHƯA HỒI PHỤC ĐẠO TÂM!** Bạn vừa xuất quan, cần nghỉ ngơi `{remain_min} phút` nữa mới có thể nhập định tiếp.")
            return

        if hours not in [1, 4, 8, 12, 16, 24]:
            await ctx.send("❌ Thời gian bế quan hợp lệ chỉ gồm: `1`h, `4`h, `8`h, `12`h, `16`h hoặc `24`h.")
            return

        player.is_meditating = True
        player.meditate_start_time = now
        player.meditate_duration_hours = hours
        self.db.update_player(player)

        await ctx.send(f"🧘 Tu sĩ **{player.dao_hieu}** đã bắt đầu nhập định bế quan trong **{hours} Giờ**! (Tối thiểu 30 phút để nhận thưởng xuất quan).")

    @commands.command(
        name="xuat-quan",
        aliases=["xuatquan", "xuatdinh"],
        brief="Thu công xuất quan sớm & nhận thưởng tài nguyên tích lũy.",
        usage="xuat-quan"
    )
    async def xuatquan_cmd(self, ctx: commands.Context):
        """Thu công xuất quan sớm & nhận thưởng tài nguyên tích lũy."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if not player.is_meditating:
            await ctx.send("❌ Bạn hiện tại không ở trong trạng thái bế quan!")
            return

        now = time.time()
        start_t = player.meditate_start_time or now
        elapsed_hours = (now - start_t) / 3600.0

        # Anti-exploit: Yêu cầu bế quan tối thiểu 30 phút (0.5 giờ)
        MIN_MEDITATION_HOURS = 0.5
        if elapsed_hours < MIN_MEDITATION_HOURS:
            player.is_meditating = False
            player.meditate_start_time = None
            player.meditate_duration_hours = 0
            player.last_meditation_end = now
            self.db.update_player(player)

            elapsed_mins = int(elapsed_hours * 60)
            remain_mins = int((MIN_MEDITATION_HOURS - elapsed_hours) * 60) + 1
            await ctx.send(
                f"⚠️ **XUẤT QUAN QUÁ SỚM!** Bạn mới bế quan được **{elapsed_mins} phút**.\n"
                f"> Cần bế quan tối thiểu **30 phút** để hấp thu linh khí và nhận phần thưởng!\n"
                f"> ⏳ Lần nhập định này đã hủy bỏ mà không nhận được tu vi hay hồi máu."
            )
            return

        actual_hours = min(elapsed_hours, float(player.meditate_duration_hours or 1))

        # AFK EXP scale cùng formula exponential với active cultivation
        # VIP 7 nhận thêm +30% tốc độ AFK (thêm 30% EXP)
        base_afk_per_hour = int(200 * (1.4 ** player.realm_index) * 30)
        vip7_bonus = 1.30 if player.vip_level >= 7 else 1.0
        exp_gain = int(base_afk_per_hour * actual_hours * vip7_bonus)
        linh_thach_gain = int(800 * actual_hours * (1 + player.realm_index * 0.05))
        tam_canh_gain = round(actual_hours * 2.0, 1)
        # Thủy element: +10% Tâm Cảnh hiệu quả khi AFK (bonus thêm 10%)
        if "Thủy" in player.linh_can_element:
            tam_canh_gain = round(tam_canh_gain * 1.10, 1)
        can_co_gain = round(actual_hours * 10.0, 1)

        # Hồi phục HP/Mana tỷ lệ theo số giờ bế quan thực tế (4 giờ thật mới full 100%)
        FULL_HP_HOURS = 4.0
        hp_ratio = min(1.0, actual_hours / FULL_HP_HOURS)
        hp_gain = int(player.max_hp * hp_ratio)
        mana_gain = int(player.max_mana * hp_ratio)
        player.hp = min(player.max_hp, player.hp + hp_gain)
        player.mana = min(player.max_mana, player.mana + mana_gain)

        req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
        player.exp = min(req_exp, player.exp + exp_gain)
        player.linh_thach += linh_thach_gain
        player.tam_canh = min(100.0, player.tam_canh + tam_canh_gain)
        player.can_co = min(100.0, player.can_co + can_co_gain)
        player.is_meditating = False
        player.meditate_start_time = None
        player.meditate_duration_hours = 0
        player.last_meditation_end = now
        player.continuous_cultivation_count = 0
        player.linh_luc_tap_chat = False

        self.db.update_player(player)

        hp_pct = int(hp_ratio * 100)
        embed = discord.Embed(
            title=f"🧘 XUẤT QUAN THÀNH CÔNG — {player.dao_hieu}",
            description=f"Tu sĩ **{player.dao_hieu}** đã thu công xuất quan sau **{actual_hours:.1f} Giờ** nhập định!\n"
                        f"✨ Khí Huyết & Chân Nguyên hồi phục **+{hp_pct}%** (`+{hp_gain:,}` HP | `+{mana_gain:,}` MP)!",
            color=discord.Color.green()
        )
        embed.add_field(
            name="🎁 Phần Thưởng Tích Lũy",
            value=f"> ✨ Tu Vi: `+{exp_gain:,}`\n> 💰 Linh Thạch: `+{linh_thach_gain:,}`\n> 🧘 Tâm Cảnh: `+{tam_canh_gain}%`\n> ◈ Căn Cơ: `+{can_co_gain}%`",
            inline=False
        )
        embed.set_footer(text="Nghỉ ngơi 10 phút trước khi bắt đầu lượt bế quan tiếp theo.")
        await ctx.send(embed=embed)

    @commands.command(
        name="nhapdinh-nhanh",
        aliases=["nhapdinhnhanh", "beequan-nhanh", "vip-afk"],
        brief="[VIP 5] Nhận ngay phần thưởng tương đương 4 Giờ Bế Quan AFK tức thì.",
        usage="nhapdinh-nhanh"
    )
    async def nhapdinh_nhanh_cmd(self, ctx: commands.Context):
        """[VIP 5+] Nhập Định Nhanh — Nhận tức thì phần thưởng tương đương 4 Giờ Bế Quan."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if player.vip_level < 5:
            await ctx.send(
                f"🔒 **[VIP 5 YÊU CẦU]** Lệnh `!nhapdinh-nhanh` chỉ dành cho tu sĩ **VIP 5 (Tôn Giả)** trở lên!\n"
                f"> 👑 VIP hiện tại của bạn: **VIP {player.vip_level}** | Nạp thêm Tiên Ngọc để thăng VIP!"
            )
            return

        if player.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG TRONG TRẠNG THÁI BẾ QUAN!** Gõ `!xuat-quan` trước!")
            return

        # Cooldown 24h persistent trong DB
        now = time.time()
        if player.last_nhapdinh_nhanh and (now - player.last_nhapdinh_nhanh < 86400):
            remain_h = int((86400 - (now - player.last_nhapdinh_nhanh)) / 3600) + 1
            await ctx.send(f"⏳ **ĐÃ DÙNG HÔM NAY!** Lệnh `!nhapdinh-nhanh` hồi trong `{remain_h}` giờ nữa.")
            return

        # Trao phần thưởng tương đương 4h AFK
        afk_hours = 4.0
        base_afk_per_hour = int(200 * (1.4 ** player.realm_index) * 30)
        exp_gain = int(base_afk_per_hour * afk_hours * 1.30)  # VIP 5+ tự động có VIP 7 bonus spirit
        linh_thach_gain = int(800 * afk_hours * (1 + player.realm_index * 0.05))
        tam_canh_gain = round(afk_hours * 2.0, 1)
        can_co_gain = round(afk_hours * 10.0, 1)

        req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
        player.exp = min(req_exp, player.exp + exp_gain)
        player.linh_thach += linh_thach_gain
        player.tam_canh = min(100.0, player.tam_canh + tam_canh_gain)
        player.can_co = min(100.0, player.can_co + can_co_gain)
        player.last_nhapdinh_nhanh = now
        self.db.update_player(player)

        embed = discord.Embed(
            title="⚡ [VIP 5] NHẬP ĐỊNH NHANH — TỨC THÌ THU CÔNG!",
            description=f"Tu sĩ **{player.dao_hieu}** kích hoạt bí thuật **Thời Không Định Tâm** của Tôn Giả!\n"
                        f"Nhận tức thì phần thưởng tương đương **4 Giờ Bế Quan AFK**!",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="🎁 Phần Thưởng",
            value=f"> ✨ Tu Vi: `+{exp_gain:,}`\n> 💰 Linh Thạch: `+{linh_thach_gain:,}`\n> 🧘 Tâm Cảnh: `+{tam_canh_gain}%`\n> ◈ Căn Cơ: `+{can_co_gain}%`",
            inline=False
        )
        embed.set_footer(text="Lệnh này hồi lại sau 24 Giờ. VIP 5 đặc quyền!")
        await ctx.send(embed=embed)

    @commands.command(
        name="luyen-the",
        aliases=["luyenthe"],
        brief="Rèn luyện Thân Thể tiêu hao Linh Thạch để đột phá Tôi Thể.",
        usage="luyen-the"
    )
    async def luyenthe_cmd(self, ctx: commands.Context):
        """Rèn luyện Thân Thể tiêu hao Linh Thạch & 5 Tinh Lực để đột phá Tôi Thể."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.kinh_mach_doan_tuyet_until and player.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy phục hồi trước khi Tôi Thể!")
            return

        if player.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG BẾ QUAN!** Vui lòng gõ `!xuat-quan` trước khi Luyện Thể.")
            return

        if player.tinh_luc < 5:
            await ctx.send(f"❌ Không đủ Tinh Lực! Cần `5` Tinh Lực để Tôi Thể (Hiện có: `{player.tinh_luc}/100`).")
            return

        cost = 500 * (player.body_realm_index + 1)
        success, msg, updated_player = upgrade_body_refining(player, cost)
        if success:
            updated_player.tinh_luc -= 5
            self.db.update_player(updated_player)
        await ctx.send(msg)


    # --- 📂 NHÓM LỆNH [/dot-pha] ---

    @commands.command(
        name="dot-pha",
        aliases=["dotpha", "breakthrough"],
        brief="Xung kích bình cảnh & nghênh đón Lôi Kiếp thời gian thực.",
        usage="dot-pha"
    )
    async def dotpha_cmd(self, ctx: commands.Context):
        """Xung kích bình cảnh & Lôi Kiếp (Tự động kích hoạt Thần Phù Bảo Mệnh nếu thất bại)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.kinh_mach_doan_tuyet_until and player.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy nhờ đạo hữu dùng `!cuu-thuong @user` hoặc mua Cửu Chuyển Tái Tạo Đan tại `!tiencac` để phục hồi trước khi Đột Phá!")
            return

        if player.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG BẾ QUAN!** Vui lòng gõ `!xuat-quan` để xuất quan trước khi Đột Phá.")
            return

        req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
        if player.exp < req_exp:
            await ctx.send(f"❌ Tu vi chưa đạt 100%! Hiện tại: `{player.exp:,}` / `{req_exp:,}`.")
            return

        chance = calculate_breakthrough_chance(player)
        if chance <= 0:
            await ctx.send("❌ **TÂM CẢNH KHÔNG ĐỦ!** Tỷ lệ đột phá thành công của bạn hiện là `0%`! Hãy thiền định tăng Tâm Cảnh!")
            return

        from app.discord_bot.modules.tutien.constants import REALM_BREAKTHROUGH_PILLS
        bottleneck_info = REALM_BREAKTHROUGH_PILLS.get(player.realm_index)
        has_breakthrough_pill = False
        pill_status_msg = ""

        if bottleneck_info:
            req_pill = bottleneck_info["pill_name"]
            has_breakthrough_pill = self.db.consume_item(player.user_id, req_pill, 1)
            if has_breakthrough_pill:
                pill_status_msg = f"\n💊 **Dược Lực Hộ Trì:** Đã tự động dùng **[{req_pill}]** để bảo vệ đan điền!"
            else:
                chance = max(5.0, chance - 50.0)
                pill_status_msg = (
                    f"\n⚠️ **BÌNH CẢNH ĐẠI CẢNH GIỚI!** Bạn chưa có **[{req_pill}]**!\n"
                    f"> *Cưỡng ép đột phá không đan dược: Tỷ lệ thành công bị phạt `-50%` & nguy cơ rạn nứt đan điền tụt cảnh giới!*"
                )

        is_blood_tribulation = (player.nghiep_luc > 100)
        total_waves = 3 + (player.realm_index // 3)
        current_hp = player.hp

        tribulation_title = "⚡🩸 HUYẾT LÔI CỬU THIÊN GIÁNG LÂM 🩸⚡" if is_blood_tribulation else "⚡⚡⚡ THIÊN KIẾP GIÁNG LÂM ⚡⚡⚡"
        tribulation_desc = (
            f"⚠️ **CƠN THỊNH NỘ CỦA THIÊN ĐẠO!** Nghiệp Lực quá cao (`{player.nghiep_luc}` điểm), Ma Đầu **[{player.dao_hieu}]** bị giáng Huyết Lôi uy lực gấp 3 lần!\n"
            if is_blood_tribulation else
            f"Tu sĩ **[{player.dao_hieu}]** bắt đầu xung kích bình cảnh đột phá lên **[{REALMS[min(player.realm_index + 1, len(REALMS) - 1)]}]**!\n"
        )
        tribulation_desc += f"📊 Tỷ lệ thành công cơ bản: **{chance:.1f}%** | Mật độ: **{total_waves} Đạo Lôi Kiếp**{pill_status_msg}"

        embed = discord.Embed(
            title=tribulation_title,
            description=tribulation_desc,
            color=discord.Color.dark_purple() if is_blood_tribulation else discord.Color.dark_red()
        )
        msg_obj = await ctx.send(embed=embed)

        failed = False
        for wave in range(1, total_waves + 1):
            dmg = calculate_tribulation_damage(player, wave)
            if is_blood_tribulation:
                dmg *= 3

            if player.user_id in self.ho_phap_registry:
                dmg = int(dmg * 0.7)

            wave_embed = discord.Embed(
                title=f"⚡ {'HUYẾT ' if is_blood_tribulation else ''}LÔI KIẾP ĐỢT [{wave}/{total_waves}] GIỘI XUỐNG!",
                description=f"💥 Sát thương dự kiến: `{dmg:,}` Lôi Thuộc Tính.\n⏱️ Bạn có **10 Giây** để chọn phương án phòng thủ!",
                color=discord.Color.red() if is_blood_tribulation else discord.Color.gold()
            )
            view = TribulationWaveView(player, wave, total_waves, dmg)
            await msg_obj.edit(embed=wave_embed, view=view)

            await view.wait()
            if not view.chosen_action:
                actual_dmg = dmg
            elif view.chosen_action == "SHIELD":
                actual_dmg = int(dmg * 0.4)
            elif view.chosen_action == "PILL":
                actual_dmg = int(dmg * 0.6)
            else:
                actual_dmg = dmg

            current_hp -= actual_dmg
            if current_hp <= 0:
                failed = True
                break
            await asyncio.sleep(1.5)

        # Sync HP sau kiếp lôi
        player.hp = max(0, current_hp)

        if failed or random.uniform(0, 100) > chance:
            has_insurance = self.db.consume_item(player.user_id, "Thần Phù Bảo Mệnh", 1)
            reason_msg = "🩸 **Máu (HP) bị tụt về 0 do sát thương Lôi Kiếp quá lớn!**" if failed else f"☯️ **Sống sót qua lôi kiếp nhưng Khí Vận / Tâm Cảnh chưa đủ!** (Tỷ lệ thành công: `{chance:.1f}%`)"
            if has_insurance:
                player.hp = max(1, player.hp)  # Giữ sống nếu có bảo hiểm
                self.db.update_player(player)
                fail_embed = discord.Embed(
                    title="🛡️ KÍCH HOẠT THẦN PHÙ BẢO MỆNH!",
                    description=f"Độ kiếp thất bại nhưng **Thần Phù Bảo Mệnh** đã kích hoạt! Tu sĩ **{player.dao_hieu}** giữ nguyên 100% Tu Vi và Căn Cơ!\n> {reason_msg}",
                    color=discord.Color.gold()
                )
            else:
                realm_drop_msg = ""
                # Phạt rơi 1 tiểu cảnh giới nếu Căn Cơ < 40%
                if player.can_co < 40.0 and player.realm_index > 0:
                    old_realm = player.realm_name
                    player.realm_index -= 1
                    player.realm_name = REALMS[player.realm_index]
                    player.exp = 0
                    player.can_co = max(0.0, player.can_co - 15.0)
                    realm_drop_msg = f"\n📉 **CĂN CƠ QUÁ YẾU (<40%) — ĐAN ĐIỀN NỨT VỠ!** Bạn bị **tụt cảnh giới** từ `{old_realm}` xuống **`{player.realm_name}`**!"
                else:
                    player.exp = int(player.exp * 0.7)
                    player.can_co = max(0.0, player.can_co - 20.0)

                player.hp = max(1, player.hp)
                if failed:
                    player.kinh_mach_doan_tuyet_until = time.time() + 600
                    realm_drop_msg += "\n🩸 **Kinh Mạch Đoạn Tuyệt (10 Phút)** do Lôi Kiếp phá hủy!"

                loss_extra_msg = ""
                if is_blood_tribulation:
                    lost_lt = int(player.linh_thach * 0.50)
                    player.linh_thach -= lost_lt
                    loss_extra_msg = f"\n🩸 **Huyết Lôi xé rách túi trữ vật!** Bị hủy diệt `{lost_lt:,}` Linh Thạch!"

                self.db.update_player(player)
                fail_embed = discord.Embed(
                    title="💀 ĐỘ KIẾP THẤT BẠI!",
                    description=f"Thiên lôi oanh kích tan tành! Tu sĩ **{player.dao_hieu}** độ kiếp thất bại!\n> {reason_msg}{realm_drop_msg}{loss_extra_msg}\n"
                                f"🔥 *Hãy luyện chế Đan Dược Phá Cảnh tại `!luyen-dan` hoặc mua Thần Phù Bảo Mệnh tại `!tiencac`!*",
                    color=discord.Color.red()
                )
            await msg_obj.edit(embed=fail_embed, view=None)
        else:
            player.realm_index = min(len(REALMS) - 1, player.realm_index + 1)
            player.realm_name = REALMS[player.realm_index]
            player.exp = 0
            player.can_co = min(100.0, player.can_co + 5.0)

            # Tăng stats khi lên cảnh giới mới
            hp_gain = 500 + (player.realm_index * 200)
            mana_gain = 200 + (player.realm_index * 100)
            player.max_hp += hp_gain
            player.max_mana += mana_gain
            player.hp = player.max_hp  # Hồi phục toàn bộ HP
            player.mana = player.max_mana  # Hồi phục toàn bộ Mana
            player.than_thuc += 5 + (player.realm_index // 3)  # Tăng Thần Thức

            self.db.update_player(player)
            win_embed = discord.Embed(
                title="🎉 ĐỘ KIẾP THÀNH CÔNG!",
                description=f"Chúc mừng Tu sĩ **[{player.dao_hieu}]** đã vượt qua Thiên Kiếp, chính thức tiến cấp lên **[{player.realm_name}]**!\n"
                            f"💪 Nhận: `+{hp_gain:,}` Max HP | `+{mana_gain:,}` Max Mana | `+{5 + (player.realm_index // 3)}` Thần Thức\n"
                            f"✨ HP & Mana đã được hồi phục hoàn toàn!",
                color=discord.Color.green()
            )
            await msg_obj.edit(embed=win_embed, view=None)

    # --- ⚔️ HỆ THỐNG PVP («TU SĨ TRANH PHONG / SÁT LỤC - LUẬN ĐẠO») ---

    @commands.command(
        name="luan-dao",
        aliases=["luandao", "pvp", "arena", "dautruong"],
        brief="Vào Luận Đạo Đài PVP Xếp Hạng 1v1 (Không mất đồ, cày ELO & Điểm Danh Vọng).",
        usage="luan-dao [@đối_thủ]"
    )
    async def luan_dao_cmd(self, ctx: commands.Context, target: discord.Member = None):
        """Luận Đạo Đài PVP 1v1 Ranked (Ma trận tính toán 5 tầng)."""
        player1 = self.db.get_player(ctx.author.id)
        if not player1:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player1.kinh_mach_doan_tuyet_until and player1.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player1.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy phục hồi trước khi tham gia Luận Đạo Đài!")
            return

        if player1.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG BẾ QUAN!** Vui lòng gõ `!xuat-quan` trước khi Luận Đạo.")
            return

        if target and target.bot:
            await ctx.send("❌ Không thể luận đạo với Bot!")
            return

        if target and target.id == ctx.author.id:
            await ctx.send("❌ Không thể tự luận đạo với chính mình!")
            return

        if player1.tinh_luc < 5:
            await ctx.send(f"❌ Không đủ Tinh Lực! Cần `5` Tinh Lực để tham gia Luận Đạo Đài (Hiện có: `{player1.tinh_luc}/100`).")
            return

        is_auto_matched = (target is None)

        # Target opponent or find random in leaderboard
        if target:
            player2 = self.db.get_player(target.id)
            if not player2:
                await ctx.send(f"❌ Tu sĩ **{target.display_name}** chưa gia nhập giới Tu Tiên!")
                return
            if player2.is_meditating:
                await ctx.send(f"🧘 Tu sĩ **{player2.dao_hieu}** đang bế quan nhập định, không thể tiếp chiến!")
                return
            if player2.mien_chien_until and player2.mien_chien_until > now:
                await ctx.send(f"🛡️ **THẤT NHẬT MIỄN CHIẾN!** Tu sĩ **{player2.dao_hieu}** đang được bảo vệ bởi Miễn Chiến Phù!")
                return
        else:
            # Auto matchmaker from DB
            top_players = self.db.get_pvp_leaderboard(20)
            eligible = [p for p in top_players if p["user_id"] != ctx.author.id and not p.get("is_meditating", 0)]
            if not eligible:
                await ctx.send("❌ Chưa có đủ đạo hữu trên Luận Đạo Đài để tự động ghép cặp! Hãy chỉ định `@user` đối thủ.")
                return
            matched_row = random.choice(eligible)
            player2 = self.db.get_player(matched_row["user_id"])

        player1.tinh_luc -= 5

        gf1 = self.db.get_gongfa(player1.user_id)
        gf2 = self.db.get_gongfa(player2.user_id)

        # Start match embed
        p1_rank = get_pvp_rank(player1.pvp_elo)
        p2_rank = get_pvp_rank(player2.pvp_elo)

        start_embed = discord.Embed(
            title="🥋 LUẬN ĐẠO ĐÀI: TRANH PHONG BẢNG XẾP HẠNG 🥋",
            description=f"🔴 **[{player1.dao_hieu}]** ({p1_rank['badge']} `{player1.pvp_elo}` ELO | `{player1.realm_name}`)\n"
                        f"⚔️ **VS** ⚔️\n"
                        f"🔵 **[{player2.dao_hieu}]** ({p2_rank['badge']} `{player2.pvp_elo}` ELO | `{player2.realm_name}`)\n\n"
                        f"> 📜 *Luận Đạo văn minh, bảo toàn tính mạng & tài sản, quy đổi Điểm Danh Vọng.*",
            color=discord.Color.gold()
        )
        msg_obj = await ctx.send(embed=start_embed)
        await asyncio.sleep(1.5)

        # Simulate full match with 5-tier depth
        match_res = simulate_full_pvp_match(player1, player2, gf1, gf2)
        winner_id = match_res["winner_id"]
        is_p1_win = (winner_id == player1.user_id)

        # Calculate ELO and Fame Points
        if is_p1_win:
            elo_gain, elo_loss = calculate_elo_change(player1.pvp_elo, player2.pvp_elo)
            if is_auto_matched:
                elo_loss = 0  # Bảo vệ đối thủ auto-match không bị trừ ELO
            player1.pvp_elo += elo_gain
            player2.pvp_elo = max(100, player2.pvp_elo - elo_loss)
            player1.pvp_wins += 1
            player1.pvp_streak += 1
            if not is_auto_matched:
                player2.pvp_losses += 1
                player2.pvp_streak = 0
            
            p1_dv_gain = p1_rank["win_danh_vong"]
            p2_dv_gain = 0 if is_auto_matched else p2_rank["loss_danh_vong"]
            player1.danh_vong += p1_dv_gain
            player2.danh_vong += p2_dv_gain
            
            w_player, l_player = player1, player2
            w_gain_str, l_loss_str = f"+{elo_gain}", f"-{elo_loss}"
        else:
            elo_gain, elo_loss = calculate_elo_change(player2.pvp_elo, player1.pvp_elo)
            if is_auto_matched:
                elo_gain = 0  # Ngăn chặn farm ELO bằng cách cho alt account thua auto-match
            player2.pvp_elo += elo_gain
            player1.pvp_elo = max(100, player1.pvp_elo - elo_loss)
            if not is_auto_matched:
                player2.pvp_wins += 1
                player2.pvp_streak += 1
            player1.pvp_losses += 1
            player1.pvp_streak = 0
            
            p2_dv_gain = 0 if is_auto_matched else p2_rank["win_danh_vong"]
            p1_dv_gain = p1_rank["loss_danh_vong"]
            player2.danh_vong += p2_dv_gain
            player1.danh_vong += p1_dv_gain
            
            w_player, l_player = player2, player1
            w_gain_str, l_loss_str = f"+{elo_gain}", f"-{elo_loss}"

        self.db.update_player(player1)
        self.db.update_player(player2)

        # --- Quest Tracking: Thiên Kiêu Tranh Phong (PVP Wins) ---
        winner_id = player1.user_id if is_p1_win else player2.user_id
        completed_pvp_q = self.db.increment_quest_progress(winner_id, "pvp_wins")
        if completed_pvp_q:
            try:
                winner_user = self.bot.get_user(winner_id)
                if winner_user:
                    await ctx.send(
                        f"🏆 **ĐẠO VỤ HOÀN THÀNH!** Tu sĩ **{w_player.dao_hieu}** hoàn tất `{completed_pvp_q['quest_name']}`! Gõ `!dao-vu` để nhận thưởng!"
                    )
            except Exception:
                pass


        p1_bar = render_progress_bar(match_res["final_hp1"], player1.max_hp)
        p2_bar = render_progress_bar(match_res["final_hp2"], player2.max_hp)

        log_lines = []
        for log in match_res["combat_logs"][-4:]:
            log_lines.append(f"> ⚡ {log['message']}")
            if log.get("flavor"):
                log_lines.append(f"> *{log['flavor']}*")

        result_embed = discord.Embed(
            title=f"🏆 KẾT QUẢ LUẬN ĐẠO: [{w_player.dao_hieu}] TOÀN THẮNG!",
            description=f"🔴 **[{player1.dao_hieu}]**\nHP: `{p1_bar}` `{match_res['final_hp1']:,}/{player1.max_hp:,}`\n"
                        f"🔵 **[{player2.dao_hieu}]**\nHP: `{p2_bar}` `{match_res['final_hp2']:,}/{player2.max_hp:,}`\n\n"
                        f"📜 **CHIẾN BÁO DIỄN BIẾN:**\n" + "\n".join(log_lines),
            color=discord.Color.green() if is_p1_win else discord.Color.blue()
        )

        result_embed.add_field(
            name=f"🎉 Thắng Lợi: [{w_player.dao_hieu}]",
            value=f"> ELO: `{w_player.pvp_elo}` ({w_gain_str})\n> Danh Vọng: `+{p1_dv_gain if is_p1_win else p2_dv_gain}` 🏆 (Chuỗi Thắng: `{w_player.pvp_streak}`)",
            inline=True
        )
        result_embed.add_field(
            name=f"🛡️ Thất Bại: [{l_player.dao_hieu}]",
            value=f"> ELO: `{l_player.pvp_elo}` ({l_loss_str})\n> Danh Vọng Tích Lũy: `+{p2_dv_gain if is_p1_win else p1_dv_gain}` 🏆",
            inline=True
        )
        result_embed.set_footer(text="Gõ !tang-kinh-cac để đổi điểm Danh Vọng lấy Công Pháp hiếm!")
        await msg_obj.edit(embed=result_embed)

    @commands.command(
        name="bxh-pvp",
        aliases=["top-elo", "toppvp", "pvp-top"],
        brief="Xem Bảng Xếp Hạng ELO & Danh Vọng Luận Đạo Đài Server.",
        usage="bxh-pvp"
    )
    async def bxh_pvp_cmd(self, ctx: commands.Context):
        """Xem Bảng Xếp Hạng ELO Luận Đạo Đài Top 10 Server."""
        top_list = self.db.get_pvp_leaderboard(10)
        embed = discord.Embed(title="🏆 BẢNG XẾP HẠNG LUẬN ĐẠO ĐÀI TOP 10 🏆", color=discord.Color.gold())

        if not top_list:
            embed.description = "Chưa có tu sĩ nào tham gia Luận Đạo Đài."
        else:
            for rank_idx, row in enumerate(top_list, 1):
                icon = "🥇" if rank_idx == 1 else "🥈" if rank_idx == 2 else "🥉" if rank_idx == 3 else f"[{rank_idx}]"
                r_info = get_pvp_rank(row["pvp_elo"])
                streak_str = f"🔥 Streak: `{row['pvp_streak']}`" if row.get("pvp_streak", 0) > 1 else ""
                val = f"> Hạng: {r_info['badge']} **{r_info['tier']}** | ELO: **`{row['pvp_elo']}`** | 🏆 Danh Vọng: `{row['danh_vong']:,}`\n" \
                      f"> Thắng/Thua: `{row['pvp_wins']}/{row['pvp_losses']}` {streak_str}"
                embed.add_field(name=f"{icon} {row['dao_hieu']} ({row['realm_name']})", value=val, inline=False)

        embed.set_footer(text="Top 3 cuối tuần nhận Danh Hiệu Mạ Vàng + Tiên Ngọc! Gõ !luan-dao để leo rank.")
        await ctx.send(embed=embed)

    @commands.command(
        name="tang-kinh-cac",
        aliases=["tangkinhcac", "shop-danh-vong", "danhvong-shop"],
        brief="Xem & Đổi Điểm Danh Vọng lấy Công Pháp, Thần Binh hiếm.",
        usage="tang-kinh-cac [tên_vật_phẩm]"
    )
    async def tang_kinh_cac_cmd(self, ctx: commands.Context, *, item_name: str = None):
        """Xem & Đổi Điểm Danh Vọng tại Tàng Kinh Các."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if not item_name:
            view = TangKinhCacShopView(self.db, player)
            await ctx.send(embed=view.build_embed())
            return

        target_item = None
        for name, item in TANG_KINH_CAC_SHOP.items():
            if item_name.lower() in name.lower():
                target_item = (name, item)
                break

        if not target_item:
            await ctx.send(f"❌ Vật phẩm **[{item_name}]** không có trong Tàng Kinh Các! Gõ `!tang-kinh-cac` để xem danh sách.")
            return

        real_name, item_info = target_item
        cost = item_info["cost"]
        if player.danh_vong < cost:
            await ctx.send(f"❌ Không đủ Điểm Danh Vọng! Cần `{cost}` Danh Vọng (Hiện có: `{player.danh_vong:,}`).")
            return

        player.danh_vong -= cost
        if "Định Thần" in real_name:
            player.chan_thuong_until = None
            player.tau_hoa_nhap_ma_until = None
        elif "Bảo Rương" in real_name:
            lt_bonus = random.randint(10000, 50000)
            tien_duyen_bonus = random.randint(1, 3)
            player.linh_thach += lt_bonus
            player.tien_duyen_phu += tien_duyen_bonus
        else:
            self.db.add_item(player.user_id, real_name, item_info["type"], 1)

        self.db.update_player(player)
        await ctx.send(f"✨ **ĐỔI DANH VỌNG THÀNH CÔNG!** Đã đổi thành công **[{real_name}]** (Trừ `{cost}` Danh Vọng)!")

    @commands.command(
        name="sinh-tu-dai",
        aliases=["sinhtudai", "quyetchien", "pvp-bet"],
        brief="Khai mở Sinh Tử Đài Đặt Cược Sinh Tử (Kẻ thua mất sạch cược & chấn thương kinh mạch).",
        usage="sinh-tu-dai @user <số_linh_thạch>"
    )
    async def sinh_tu_dai_cmd(self, ctx: commands.Context, target: discord.Member, amount: int):
        """Khai mở Sinh Tử Đài Đặt Cược (High-Stakes PVP Bet)."""
        challenger = self.db.get_player(ctx.author.id)
        victim = self.db.get_player(target.id)

        if target.bot:
            await ctx.send("❌ Không thể khiêu chiến sinh tử với Bot!")
            return

        if not challenger or not victim:
            await ctx.send("❌ Cả 2 tu sĩ đều phải nhập môn Tu Tiên!")
            return

        if challenger.user_id == victim.user_id:
            await ctx.send("❌ Không thể khiêu chiến sinh tử với chính mình!")
            return

        if amount <= 0:
            await ctx.send("❌ Mức cược Linh Thạch phải lớn hơn 0!")
            return

        if challenger.linh_thach < amount:
            await ctx.send(f"❌ Bạn không đủ Linh Thạch để đặt cược! Hiện có: `{challenger.linh_thach:,}` Linh Thạch.")
            return

        if victim.linh_thach < amount:
            await ctx.send(f"❌ Tu sĩ **{victim.dao_hieu}** không đủ `{amount:,}` Linh Thạch để đối ứng cược!")
            return

        # Check Miễn Chiến Phù
        now = time.time()
        if victim.mien_chien_until and victim.mien_chien_until > now:
            await ctx.send(f"🛡️ **THẤT NHẬT MIỄN CHIẾN!** Tu sĩ **{victim.dao_hieu}** đang được bảo vệ bởi Miễn Chiến Phù!")
            return

        view = SinhTuDaiConfirmView(challenger, victim, "LINH_THACH", amount, timeout=60.0)
        confirm_embed = discord.Embed(
            title="💀 CHIẾN THƯ SINH TỬ ĐÀI — QUYẾT CHIẾN ĐOẠT BẢO 💀",
            description=f"⚔️ Tu sĩ **[{challenger.dao_hieu}]** chính thức phát chiến thư khiêu chiến **[{victim.dao_hieu}]**!\n\n"
                        f"> 💰 **Mức Cược Sinh Tử:** 🌟 **`{amount:,}` Linh Thạch**\n"
                        f"> 🩸 **Hậu Quả Kẻ Thua:** Mất sạch toàn bộ tiền cược + Dính **Chấn Thương Kinh Mạch (-30% Sát thương trong 12 Giờ)**!\n\n"
                        f"⏱️ Đạo hữu **{target.mention}** có **60 Giây** để bấm nút chấp nhận hoặc cự tuyệt!",
            color=discord.Color.dark_red()
        )
        msg_obj = await ctx.send(embed=confirm_embed, view=view)
        await view.wait()

        if view.accepted is None:
            try:
                await msg_obj.edit(content="⏱️ **Chiến thư Sinh Tử Đài đã hết hạn sau 60 giây mà không được phản hồi!**", view=None)
            except Exception:
                pass
            return

        if not view.accepted:
            return

        # Double check funds
        challenger = self.db.get_player(challenger.user_id)
        victim = self.db.get_player(victim.user_id)
        if challenger.linh_thach < amount or victim.linh_thach < amount:
            await ctx.send("❌ Một trong hai bên không còn đủ Linh Thạch sau khi xác nhận!")
            return

        # Deduct bet upfront
        challenger.linh_thach -= amount
        victim.linh_thach -= amount

        # Execute PVP match with 5-tier matrix
        gf1 = self.db.get_gongfa(challenger.user_id)
        gf2 = self.db.get_gongfa(victim.user_id)
        match_res = simulate_full_pvp_match(challenger, victim, gf1, gf2)
        winner_id = match_res["winner_id"]
        is_p1_win = (winner_id == challenger.user_id)

        winner = challenger if is_p1_win else victim
        loser = victim if is_p1_win else challenger

        # Settle bet and injury
        total_pot = amount * 2
        winner.linh_thach += total_pot
        loser.chan_thuong_until = time.time() + 43200  # 12 Hours
        loser.hp = max(1, int(loser.max_hp * 0.10))

        self.db.update_player(challenger)
        self.db.update_player(victim)

        # Format visual bars
        p1_bar = render_progress_bar(match_res["final_hp1"], challenger.max_hp)
        p2_bar = render_progress_bar(match_res["final_hp2"], victim.max_hp)

        log_lines = []
        for log in match_res["combat_logs"][-4:]:
            log_lines.append(f"> ⚡ {log['message']}")
            if log.get("flavor"):
                log_lines.append(f"> *{log['flavor']}*")

        duel_embed = discord.Embed(
            title=f"💀 KẾT QUẢ SINH TỬ ĐÀI: [{winner.dao_hieu}] TOÀN THẮNG TRẢM SÁT! 💀",
            description=f"🔴 **[{challenger.dao_hieu}]**\nHP: `{p1_bar}` `{match_res['final_hp1']:,}/{challenger.max_hp:,}`\n"
                        f"🔵 **[{victim.dao_hieu}]**\nHP: `{p2_bar}` `{match_res['final_hp2']:,}/{victim.max_hp:,}`\n\n"
                        f"📜 **CHIẾN BÁO SINH TỬ:**\n" + "\n".join(log_lines),
            color=discord.Color.dark_red()
        )
        duel_embed.add_field(
            name="🏆 Kẻ Thắng Đoạt Bảo",
            value=f"> Tu sĩ: **[{winner.dao_hieu}]**\n> Thu hoạch: `+{total_pot:,}` Linh Thạch!",
            inline=True
        )
        duel_embed.add_field(
            name="💀 Kẻ Bại Chấn Thương",
            value=f"> Tu sĩ: **[{loser.dao_hieu}]**\n> Mất: `-{amount:,}` Linh Thạch\n> Trạng thái: **Chấn Thương Kinh Mạch (12h)**",
            inline=True
        )
        await ctx.send(embed=duel_embed)

        # Server-wide Flex Notification for big stakes
        if amount >= 100000:
            flex_msg = f"💥 **[SINH TỬ ĐẠI QUYẾT CHIẾN]**: Tu sĩ **{winner.dao_hieu}** vừa đánh bại **{loser.dao_hieu}**, chém rơi đầu đoạt lấy **{total_pot:,} Linh Thạch**! Toàn cõi tu chân chấn động!"
            await ctx.send(flex_msg)

    @commands.command(
        name="cuop",
        aliases=["cuop-dong-phu", "cuopdongphu"],
        brief="Đột nhập Động Phủ tu sĩ khác cướp bóc & phá bế quan AFK.",
        usage="cuop @user"
    )
    async def cuop_cmd(self, ctx: commands.Context, target: discord.Member):
        """Đột nhập Động Phủ cướp bóc (Ma Tu Open World PK)."""
        attacker = self.db.get_player(ctx.author.id)
        victim = self.db.get_player(target.id)

        if target.bot:
            await ctx.send("❌ Không thể cướp Động Phủ của Bot!")
            return

        if not attacker or not victim:
            await ctx.send("❌ Cả 2 tu sĩ đều phải nhập môn Tu Tiên!")
            return

        if attacker.user_id == victim.user_id:
            await ctx.send("❌ Không thể tự cướp Động Phủ của chính mình!")
            return

        now = time.time()
        last_c = attacker.last_cuop_time or 0
        cd_seconds = 7200  # 2 Giờ Cooldown
        if now - last_c < cd_seconds:
            remain_sec = int(cd_seconds - (now - last_c))
            remain_h = remain_sec // 3600
            remain_m = (remain_sec % 3600) // 60
            time_str = f"{remain_h} giờ {remain_m} phút" if remain_h > 0 else f"{remain_m} phút"
            await ctx.send(f"⏱️ Bạn vừa đột nhập cướp động phủ gần đây! Hãy tĩnh dưỡng `{time_str}` nữa rồi tiếp tục.")
            return

        # Check Protection Scrolls & Buffer Protection
        if victim.mien_chien_until and victim.mien_chien_until > now:
            await ctx.send(f"🛡️ **THẤT NHẬT MIỄN CHIẾN!** Động Phủ của **{victim.dao_hieu}** đang được phong ấn an toàn bởi Miễn Chiến Phù!")
            return

        if is_array_protected(victim):
            await ctx.send(f"🛡️ **TRẬN PHÁP BẤT XÂM PHẠM!** Động Phủ của **{victim.dao_hieu}** đang được bảo vệ, cướp phá thất bại!")
            return

        if victim.linh_thach < 100:
            await ctx.send(f"❌ Động phủ của **{victim.dao_hieu}** nghèo xơ xác, không có gì để cướp!")
            return

        attacker.last_cuop_time = now

        # 5-Tier Combat Matrix: Attacker vs Home Defender
        gf_att = self.db.get_gongfa(attacker.user_id)
        gf_vic = self.db.get_gongfa(victim.user_id)
        match_res = simulate_full_pvp_match(attacker, victim, gf_att, gf_vic)
        attacker_won = (match_res["winner_id"] == attacker.user_id)

        if attacker_won:
            stolen = int(victim.linh_thach * random.uniform(0.10, 0.20))
            victim.linh_thach -= stolen
            attacker.linh_thach += stolen
            attacker.nghiep_luc += 15

            # Anti-griefing: Grant victim 4 hours temporary buffer protection against further raids
            victim.array_protection_until = max(now + 14400, victim.array_protection_until or 0)

            # If victim is meditating AFK, disrupt and cause Tẩu Hỏa Nhập Ma
            afk_msg = ""
            if victim.is_meditating:
                victim.is_meditating = False
                victim.meditate_start_time = None
                victim.meditate_duration_hours = 0
                victim.tau_hoa_nhap_ma_until = now + 14400  # 4 Giờ
                victim.tam_canh = max(0.0, victim.tam_canh - 15.0)
                afk_msg = f"\n⚠️ **PHÁ VỠ BẾ QUAN!** Tu sĩ **{victim.dao_hieu}** bị đứt đoạn nhập định, rơi vào trạng thái **TẨU HỎA NHẬP MA (4h)** (-15% Tâm Cảnh)!"

            self.db.update_player(attacker)
            self.db.update_player(victim)

            embed = discord.Embed(
                title="🗡️ CƯỚP ĐỘNG PHỦ THÀNH CÔNG! (MA ĐẠO HOÀNH HÀNH)",
                description=f"Tu sĩ **[{attacker.dao_hieu}]** đã đánh sập Trận Pháp Động Phủ của **[{victim.dao_hieu}]**!\n"
                            f"> 💰 Cướp đoạt được: **`{stolen:,}` Linh Thạch**\n"
                            f"> 🔥 Nhận thêm: **`+15` Điểm Nghiệp Lực** (Ma Điểm)\n"
                            f"> 🛡️ *Động Phủ nạn nhân tự động kích hoạt Hộ Phủ 4 giờ chống bị cướp dồn!*{afk_msg}",
                color=discord.Color.purple()
            )
            await ctx.send(embed=embed)

            # Send Instant Revenge DM to victim
            try:
                user_obj = self.bot.get_user(victim.user_id)
                if user_obj:
                    await user_obj.send(
                        f"🩸 **CẢNH BÁO ĐỘNG PHỦ BỊ TẬP KÍCH!**\n"
                        f"Tu sĩ **[{attacker.dao_hieu}]** vừa đột nhập cướp mất `{stolen:,}` Linh Thạch của bạn!\n"
                        f"> 💊 Gõ `!tiencac` để mua **Gói Phục Hồi Cấp Tốc** (+20% Sát thương phục thù trong 15p) hoặc `!truy-na-ma-tu` để treo thưởng săn đầu kẻ thù!"
                    )
            except Exception:
                pass
        else:
            attacker.hp = max(1, int(attacker.hp * 0.50))
            self.db.update_player(attacker)
            embed = discord.Embed(
                title="🛡️ CƯỚP ĐỘNG PHỦ THẤT BẠI! BỊ TRẬN PHÁP PHẢN PHỆ",
                description=f"Tu sĩ **[{attacker.dao_hieu}]** đột nhập thất bại! Bị Trận Pháp Hộ Phủ của **[{victim.dao_hieu}]** phản phệ trọng thương `-50%` HP!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(
        name="truy-na-ma-tu",
        aliases=["truyna", "treothuong", "bounty"],
        brief="Treo Thưởng Lệnh Truy Nã Huyết Sát trảm trừ Ma Đầu.",
        usage="truy-na-ma-tu @Ma_Đầu <tiền_thưởng_linh_thạch>"
    )
    async def truy_na_cmd(self, ctx: commands.Context, target: discord.Member, amount: int, *, reason: str = "Treo thưởng trảm trừ Ma Đầu!"):
        """Treo Thưởng Lệnh Truy Nã Huyết Sát."""
        issuer = self.db.get_player(ctx.author.id)
        victim = self.db.get_player(target.id)

        if target.bot:
            await ctx.send("❌ Không thể treo thưởng truy nã Bot!")
            return

        if not issuer or not victim:
            await ctx.send("❌ Cả 2 tu sĩ đều phải nhập môn Tu Tiên!")
            return

        if issuer.user_id == victim.user_id:
            await ctx.send("❌ Không thể tự treo thưởng truy nã chính mình!")
            return

        if victim.nghiep_luc < 10:
            await ctx.send(f"❌ Tu sĩ **{victim.dao_hieu}** là người lương thiện (Nghiệp Lực: `{victim.nghiep_luc}` < 10)! Chỉ có thể treo thưởng Ma Tu tích tụ Nghiệp Lực!")
            return

        if amount < 1000:
            await ctx.send("❌ Mức tiền thưởng truy nã tối thiểu là `1,000` Linh Thạch!")
            return

        if issuer.linh_thach < amount:
            await ctx.send(f"❌ Không đủ Linh Thạch! Bạn hiện có `{issuer.linh_thach:,}` Linh Thạch.")
            return

        issuer.linh_thach -= amount
        self.db.update_player(issuer)

        bounty_id = self.db.add_bounty(victim.user_id, issuer.user_id, amount, 0, reason)

        embed = discord.Embed(
            title="🩸 PHÁT LỆNH TRUY NÃ HUYẾT SÁT THÀNH CÔNG! 🩸",
            description=f"Tu sĩ **[{issuer.dao_hieu}]** đã treo thưởng Headshot Ma Đầu **[{victim.dao_hieu}]**!\n"
                        f"> 💰 **Tiền Thưởng:** 🌟 **`{amount:,}` Linh Thạch**\n"
                        f"> 📜 *Lý do: {reason}*\n"
                        f"> ⚔️ Toàn thể tu sĩ gõ `!tram-ma {target.mention}` để đi săn Ma Đầu và nhận thưởng!",
            color=discord.Color.dark_red()
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="bang-truy-na",
        aliases=["bounties", "ds-truyna", "bounty-board"],
        brief="Xem Bảng Lệnh Truy Nã Huyết Sát toàn server.",
        usage="bang-truy-na"
    )
    async def bang_truy_na_cmd(self, ctx: commands.Context):
        """Xem Bảng Lệnh Truy Nã Huyết Sát Server."""
        bounties = self.db.get_active_bounties(50)
        view = BountyBoardView(self.db, bounties)
        await ctx.send(embed=view.build_embed(), view=view)

    @commands.command(
        name="tram-ma",
        aliases=["tramma", "san-ma", "hunt-bounty"],
        brief="Trảm Ma Đầu theo Lệnh Truy Nã để nhận trọn tiền thưởng Headshot.",
        usage="tram-ma @Ma_Đầu"
    )
    async def tram_ma_cmd(self, ctx: commands.Context, target: discord.Member):
        """Trảm Ma Đầu theo Lệnh Truy Nã."""
        hunter = self.db.get_player(ctx.author.id)
        target_p = self.db.get_player(target.id)

        if target.bot:
            await ctx.send("❌ Không thể trảm Bot!")
            return

        if not hunter or not target_p:
            await ctx.send("❌ Cả 2 tu sĩ đều phải nhập môn Tu Tiên!")
            return

        if hunter.user_id == target_p.user_id:
            await ctx.send("❌ Không thể tự trảm chính mình!")
            return

        bounty = self.db.get_bounty_for_target(target_p.user_id)
        if not bounty:
            await ctx.send(f"❌ Tu sĩ **{target_p.dao_hieu}** hiện không có tên trên Bảng Truy Nã!")
            return

        # Check Miễn Chiến
        now = time.time()
        if target_p.mien_chien_until and target_p.mien_chien_until > now:
            await ctx.send(f"🛡️ **THẤT NHẬT MIỄN CHIẾN!** Tu sĩ **{target_p.dao_hieu}** đang được phong ấn an toàn bởi Miễn Chiến Phù!")
            return

        # Execute 5-Tier PVP Duel
        gf_h = self.db.get_gongfa(hunter.user_id)
        gf_t = self.db.get_gongfa(target_p.user_id)
        match_res = simulate_full_pvp_match(hunter, target_p, gf_h, gf_t)
        hunter_won = (match_res["winner_id"] == hunter.user_id)

        if hunter_won:
            reward_lt = bounty["reward_linh_thach"]
            hunter.linh_thach += reward_lt
            hunter.danh_vong += 50
            target_p.chan_thuong_until = now + 43200  # 12h
            target_p.nghiep_luc = max(0, target_p.nghiep_luc - 20)

            self.db.complete_bounty(bounty["bounty_id"])
            self.db.update_player(hunter)
            self.db.update_player(target_p)

            embed = discord.Embed(
                title="⚔️ TRẢM MA THÀNH CÔNG! THU HOẠCH TIỀN THƯỞNG ⚔️",
                description=f"Chính Đạo Tu Sĩ **[{hunter.dao_hieu}]** đã xuất thủ trảm rơi đầu Ma Đầu **[{target_p.dao_hieu}]**!\n"
                            f"> 💰 **Nhận Tiền Thưởng Truy Nã:** 🌟 **`+{reward_lt:,}` Linh Thạch**\n"
                            f"> 🏆 **Nhận Điểm Danh Vọng:** `+50` Danh Vọng!\n"
                            f"> 🩸 Ma Đầu bị trọng thương Kinh Mạch Đoạn Tuyệt (12h).",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
        else:
            hunter.hp = max(1, int(hunter.hp * 0.30))
            self.db.update_player(hunter)
            embed = discord.Embed(
                title="💀 TRẢM MA THẤT BẠI! MA ĐẦU QUÁ HUNG HÃN",
                description=f"Tu sĩ **[{hunter.dao_hieu}]** không địch lại tà công của **[{target_p.dao_hieu}]**, bị trọng thương `-70%` HP!",
                color=discord.Color.red()
            )
            await ctx.send(embed=embed)

    @commands.command(
        name="mien-chien",
        aliases=["mienchien", "baove-dongphu"],
        brief="Xem & Kích hoạt Thất Nhật Miễn Chiến Phù (Khóa tính năng bị PK 7 ngày).",
        usage="mien-chien"
    )
    async def mien_chien_cmd(self, ctx: commands.Context):
        """Xem & Kích hoạt Thất Nhật Miễn Chiến Phù."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.mien_chien_until and player.mien_chien_until > now:
            remain_sec = int(player.mien_chien_until - now)
            remain_d = remain_sec // 86400
            remain_h = (remain_sec % 86400) // 3600
            await ctx.send(f"🛡️ **THẤT NHẬT MIỄN CHIẾN ĐANG KÍCH HOẠT!**\n> Thời gian bảo vệ còn lại: **`{remain_d} Ngày {remain_h} Giờ`**.")
            return

        await ctx.send("❌ Bạn chưa kích hoạt **Thất Nhật Miễn Chiến Phù**!\n> 🛍️ Mua ngay tại `!tiencac` với giá `300` Tiên Ngọc để an tâm tu luyện không lo bị cướp!")


    # --- ⚔️ HỆ THỐNG PVE (SĂN YÊU, THÁP THIÊN CỰC, BÍ CẢNH, BOSS SERVER) ---


    @commands.command(
        name="san-yeu",
        aliases=["sanyeu", "hunt"],
        brief="Săn Yêu Quái theo Cảnh Giới (Tiêu 10 Tinh Lực). VIP 2+: !san-yeu quet (10x).",
        usage="san-yeu [quet]"
    )
    async def sanyeu_cmd(self, ctx: commands.Context, option: str = None):
        """Săn Yêu Quái theo Cảnh Giới. VIP 2+ mở tính năng Quét Nhanh 10x (!san-yeu quet)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.kinh_mach_doan_tuyet_until and player.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy nhờ đạo hữu dùng `!cuu-thuong @user` hoặc mua Cửu Chuyển Tái Tạo Đan tại `!tiencac` để phục hồi trước khi đi Săn Yêu!")
            return

        if player.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG BẾ QUAN!** Vui lòng gõ `!xuat-quan` để xuất quan trước khi đi Săn Yêu.")
            return

        # 1. VIP 2+ Quick Sweep 10x
        if option and option.lower() in ["quet", "10x", "sweep"]:
            if player.vip_level < 2:
                await ctx.send("❌ Tính năng **Quét Nhanh 10x** yêu cầu **[VIP 2]** trở lên! Vui lòng tích nạp hoặc tăng VIP tại `!tiencac`!")
                return

            res = process_quick_sweep_10x(player, self.db)
            if not res["success"]:
                await ctx.send(f"❌ {res['reason']}")
                return

            embed = discord.Embed(
                title="⚡⚡ QUÉT NHANH SĂN YÊU 10X (VIP 2+) ⚡⚡",
                description=f"Tu sĩ **[{player.dao_hieu}]** thi triển thần thông càn quét 10 ổ Yêu Quái!",
                color=discord.Color.gold()
            )
            embed.add_field(name="🎁 Tu Vi Tích Lũy", value=f"`+{res['total_exp']:,}` EXP", inline=True)
            embed.add_field(name="💰 Linh Thạch Thu Được", value=f"`+{res['total_linh_thach']:,}` Linh Thạch", inline=True)
            embed.add_field(name="🎟️ Vé Quay Gacha Drop", value=f"`+{res['tickets_dropped']}` Linh Duyên Phù", inline=True)
            embed.add_field(name="🌿 Thảo Dược Luyện Đan", value=f"`+{res['herbs_dropped']}` Thảo Dược Thô", inline=True)
            # --- Quest Tracking: Diệt Yêu Trừ Ma ---
            completed_pve_q = self.db.increment_quest_progress(player.user_id, "pve_kills", 10)
            if completed_pve_q:
                embed.add_field(name="🏆 Đạo Vụ Hoàn Thành", value=f"> `{completed_pve_q['quest_name']}`! Gõ `!dao-vu` nhận quà!", inline=False)

            embed.set_footer(text="Tinh Lực còn lại: " + f"{player.tinh_luc}/100")
            await ctx.send(embed=embed)
            return

        # 2. Interactive Turn-Based Battle
        if player.tinh_luc < 10:
            await ctx.send("❌ Không đủ Tinh Lực! Cần 10 Tinh Lực để đi Săn Yêu.")
            return

        player.tinh_luc -= 10
        self.db.update_player(player)

        is_mutant = (random.random() < 0.15)
        monster = generate_pve_monster(player.realm_index, is_mutant=is_mutant)
        dmg_m, def_m, adv_desc = check_elemental_advantage(player.linh_can_element, monster["element"])

        embed = discord.Embed(
            title=f"⚔️ CHIẾN TRƯỜNG PVE HARDCORE: {monster['name']}",
            description=f"☯ Tu sĩ **[{player.dao_hieu}]** ({player.linh_can_element}) nghênh chiến **{monster['name']}** ({monster['element']})!\n"
                        f"> 📜 *{adv_desc}*",
            color=discord.Color.dark_red()
        )
        embed.add_field(name=f"🐍 {monster['name']} HP", value=f"`{monster['current_hp']:,} / {monster['max_hp']:,}`", inline=True)
        embed.add_field(name="🛡️ Giáp Phòng Thủ", value=f"`{monster['current_shield']:,} / {monster['max_shield']:,}`", inline=True)
        embed.add_field(name=f"👤 {player.dao_hieu} HP", value=f"`{player.hp:,} / {player.max_hp:,}`", inline=False)

        msg_obj = await ctx.send(embed=embed)

        for turn in range(1, 10):
            view = PveBattleView(ctx.author.id, timeout=30.0)
            await msg_obj.edit(view=view)
            await view.wait()

            action = view.chosen_action or "ATTACK"
            log, monster = process_turn_action(player, monster, action)

            if log["fled"]:
                await ctx.send(log["message"])
                return

            # Check 5-Second Real-Time QTE One-Shot Prompt
            if log.get("trigger_qte"):
                qte_view = QteOneShotView(ctx.author.id, timeout=5.0)
                qte_msg = await ctx.send("⚡⚡ **QTE CẢNH BÁO 5 GIÂY!** Yêu Thú tụ khí đòn One-Shot 3,000%! Bấm nút gấp:", view=qte_view)
                await qte_view.wait()

                if not qte_view.success:
                    qte_dmg = int(player.max_hp * 0.95)
                    player.hp = max(0, player.hp - qte_dmg)
                    await ctx.send(f"💥 **QTE THẤT BẠI!** Bạn chậm chân dính trọn đòn One-Shot bị trừ `{qte_dmg:,}` HP!")
                try:
                    await qte_msg.delete()
                except Exception:
                    pass

            # Update Battle Status Embed
            embed.description = f"📜 **LƯỢT {turn}:**\n> {log['message']}\n> *{log['advantage_desc']}*"
            embed.set_field_at(0, name=f"🐍 {monster['name']} HP", value=f"`{monster['current_hp']:,} / {monster['max_hp']:,}`", inline=True)
            embed.set_field_at(1, name="🛡️ Giáp Phòng Thủ", value=f"`{monster['current_shield']:,} / {monster['max_shield']:,}`", inline=True)
            embed.set_field_at(2, name=f"👤 {player.dao_hieu} HP", value=f"`{player.hp:,} / {player.max_hp:,}`", inline=False)

            await msg_obj.edit(embed=embed)
            self.db.update_player(player)

            # Check Victory
            if monster["current_hp"] <= 0:
                mult = 2.5 if is_mutant else 1.0
                exp_gain = int((1500 + (player.realm_index * 800)) * mult)
                lt_gain = int((300 + (player.realm_index * 150)) * mult)
                ticket_drop = 1 if random.random() < 0.08 else 0

                # Thảo dược & Khoáng thạch drop để Luyện Đan (!luyen-dan) & Luyện Khí (!luyen-khi)
                herb_drop = random.randint(1, 3) if is_mutant else (1 if random.random() < 0.40 else 0)
                if herb_drop > 0:
                    self.db.add_item(player.user_id, "Thảo Dược Thô", "Nguyên Liệu Luyện Đan", herb_drop)

                ore_drop = random.randint(1, 2) if is_mutant else (1 if random.random() < 0.35 else 0)
                if ore_drop > 0:
                    self.db.add_item(player.user_id, "Thần Thiết Thô", "Khoáng Thạch Luyện Khí", ore_drop)

                tien_ngoc_drop = random.randint(10, 30) if (is_mutant and random.random() < 0.35) else 0
                linh_bui_drop = random.randint(10, 40) if (is_mutant and random.random() < 0.25) else 0

                req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
                player.exp = min(req_exp, player.exp + exp_gain)
                player.linh_thach += lt_gain
                player.linh_duyen_phu += ticket_drop
                player.tien_ngoc += tien_ngoc_drop
                player.linh_bui += linh_bui_drop
                self.db.update_player(player)

                # Format loot description
                loot_items = [f"`+{exp_gain:,}` EXP", f"`+{lt_gain:,}` Linh Thạch"]
                if ticket_drop:
                    loot_items.append("`+1` Linh Duyên Phù 🎟️")
                if herb_drop:
                    loot_items.append(f"`+{herb_drop}` Thảo Dược Thô 🌿")
                if ore_drop:
                    loot_items.append(f"`+{ore_drop}` Thần Thiết Thô ⛏️")
                if tien_ngoc_drop:
                    loot_items.append(f"`+{tien_ngoc_drop}` Tiên Ngọc 🌟")
                if linh_bui_drop:
                    loot_items.append(f"`+{linh_bui_drop}` Linh Bụi ✨")

                win_embed = discord.Embed(
                    title=f"🎉 TRẢM YÊU THÀNH CÔNG — {monster['name']}!",
                    description=f"Tu sĩ **[{player.dao_hieu}]** đã xuất thủ kết liễu **{monster['name']}**!\n\n"
                                f"🎁 **Chiến Lợi Phẩm:** " + " | ".join(loot_items),
                    color=discord.Color.green()
                )

                # --- Quest Tracking: Diệt Yêu Trừ Ma ---
                completed_pve_q = self.db.increment_quest_progress(player.user_id, "pve_kills", 1)
                if completed_pve_q:
                    win_embed.add_field(name="🏆 Đạo Vụ Hoàn Thành", value=f"> `{completed_pve_q['quest_name']}`! Gõ `!dao-vu` để nhận thưởng!", inline=False)

                await ctx.send(embed=win_embed)
                return

            # Check Defeat & Permadeath Injury
            if player.hp <= 0:
                hardcore_res = process_hardcore_defeat(player, self.db, "Săn Yêu Thường")
                fail_embed = discord.Embed(
                    title="💀 BẠN ĐÃ TỬ TRẬN & KINHMẠCH ĐOẠN TUYỆT!",
                    description=f"Tu sĩ **{player.dao_hieu}** bị đánh bại! Rơi vào trạng thái **Kinh Mạch Đoạn Tuyệt (10 Phút)**.\n"
                                f"> ⚠️ Nếu không nhờ đạo hữu dùng `!cuu-thuong @user` trong 10 phút, bạn sẽ bị **giảm 20% Căn Cơ vĩnh viễn**!\n"
                                f"> 🐍 Độc Tố Thấu Cốt / Ô Nhiễm Tâm Ma đã xâm nhập cơ thể!",
                    color=discord.Color.dark_purple()
                )
                if hardcore_res["stolen_lt"] > 0:
                    fail_embed.add_field(name="💸 Tổn Thất Linh Thạch", value=f"Bị rơi mất `{hardcore_res['stolen_lt']:,}` Linh Thạch!", inline=False)
                if hardcore_res.get("dropped_herbs", 0) > 0 or hardcore_res.get("dropped_ores", 0) > 0:
                    loss_mats = []
                    if hardcore_res.get("dropped_herbs", 0) > 0:
                        loss_mats.append(f"`{hardcore_res['dropped_herbs']}` Thảo Dược Thô 🌿")
                    if hardcore_res.get("dropped_ores", 0) > 0:
                        loss_mats.append(f"`{hardcore_res['dropped_ores']}` Thần Thiết Thô ⛏️")
                    fail_embed.add_field(name="🎒 Tổn Thất Túi Đồ", value=f"Túi trữ vật rách toang, rơi mất: " + " | ".join(loss_mats), inline=False)
                await ctx.send(embed=fail_embed)
                return

            await asyncio.sleep(1.0)

    @commands.command(
        name="leo-thap",
        aliases=["leothap", "thap-thien-cuc", "thap"],
        brief="Thử thách Tháp Thiên Cực (100 Tầng PVE Bảng Xếp Hạng).",
        usage="leo-thap"
    )
    async def leothap_cmd(self, ctx: commands.Context):
        """Thử thách Tháp Thiên Cực (100 Tầng, 3 lượt miễn phí/ngày)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.kinh_mach_doan_tuyet_until and player.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy phục hồi trước khi Leo Tháp!")
            return

        if player.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG BẾ QUAN!** Vui lòng gõ `!xuat-quan` trước khi Leo Tháp.")
            return

        if player.hp <= 0:
            await ctx.send("💀 **BẠN ĐANG TRỌNG THƯƠNG (0 HP)!** Vui lòng hồi phục HP trước khi Leo Tháp!")
            return

        pve = self.db.get_pve_progress(player.user_id)
        if pve["daily_tower_keys"] <= 0:
            await ctx.send("❌ Bạn đã dùng hết `3/3` lượt leo tháp hôm nay! Hãy quay lại vào ngày mai hoặc mua thêm Thiên Cực Lệnh!")
            return

        # Deduct 1 key
        self.db.update_pve_progress(player.user_id, daily_tower_keys=pve["daily_tower_keys"] - 1)

        floor = pve["tower_floor"]
        monster = generate_pve_monster(player.realm_index, floor_offset=floor // 2)
        monster["name"] = f"🗿 Thủ Vệ Tầng {floor} — {monster['name']}"

        embed = discord.Embed(
            title=f"🏛️ THÁP THIÊN CỰC — TẦNG [{floor}/100]",
            description=f"Tu sĩ **[{player.dao_hieu}]** khiêu chiến **{monster['name']}**!\n"
                        f"> Lượt miễn phí còn lại: `{pve['daily_tower_keys'] - 1}/3`",
            color=discord.Color.purple()
        )
        msg_obj = await ctx.send(embed=embed)

        # Auto-combat 5 lượt (thay vì chỉ 1 đòn)
        tower_won = False
        for t_turn in range(1, 6):
            action = "GONGFA" if t_turn % 2 == 1 else "ATTACK"
            log, monster = process_turn_action(player, monster, action)
            if monster["current_hp"] <= 0:
                tower_won = True
                break
            if player.hp <= 0:
                break

        self.db.update_player(player)

        if tower_won:
            new_floor = floor + 1
            self.db.update_pve_progress(player.user_id, tower_floor=new_floor)

            is_milestone = (floor % 5 == 0)
            bonus_str = ""
            if is_milestone:
                player.tien_duyen_phu += 1
                player.tien_ngoc += 50
                self.db.update_player(player)
                bonus_str = "\n🎉 **MỐC TẦNG ĐẶC BIỆT!** Nhận ngay `+1` Tiên Duyên Phù 🎟️ + `50` Tiên Ngọc 🌟!"

            win_embed = discord.Embed(
                title=f"🏛️ VƯỢT THÁP THÀNH CÔNG — TẦNG [{floor}/100]!",
                description=f"Tu sĩ **[{player.dao_hieu}]** đã đánh bại **{monster['name']}** và bước lên **Tầng {new_floor}**!{bonus_str}",
                color=discord.Color.green()
            )

            # --- Quest Tracking: Diệt Yêu Trừ Ma (Vượt Tháp) ---
            completed_tower_q = self.db.increment_quest_progress(player.user_id, "pve_kills", 1)
            if completed_tower_q:
                win_embed.add_field(name="🏆 Đạo Vụ Hoàn Thành", value=f"> `{completed_tower_q['quest_name']}`! Gõ `!dao-vu` để nhận thưởng!", inline=False)

            await ctx.send(embed=win_embed)
        else:
            await ctx.send(f"❌ Khiêu chiến Tầng {floor} thất bại! {monster['name']} quá mạnh mẽ.")

    @commands.command(
        name="top-thap",
        aliases=["topthap", "tower-leaderboard"],
        brief="Xem Bảng Xếp Hạng Leo Tháp Thiên Cực Server.",
        usage="top-thap"
    )
    async def topthap_cmd(self, ctx: commands.Context):
        """Xem Bảng Xếp Hạng Leo Tháp Thiên Cực Top 10 Server."""
        top_list = self.db.get_tower_leaderboard(10)
        embed = discord.Embed(title="🏆 BẢNG XẾP HẠNG LEOT HÁP THIÊN CỰC 🏆", color=discord.Color.gold())

        if not top_list:
            embed.description = "Chưa có tu sĩ nào leo tháp."
        else:
            for rank, row in enumerate(top_list, 1):
                icon = "🥇" if rank == 1 else "🥈" if rank == 2 else "🥉" if rank == 3 else f"[{rank}]"
                embed.add_field(name=f"{icon} {row['dao_hieu']}", value=f"> Tầng Tháp: **Tầng {row['tower_floor']}**", inline=False)

        await ctx.send(embed=embed)

    @commands.command(
        name="bi-canh",
        aliases=["bicanh", "dungeon"],
        brief="Tổ đội 3-5 Tu Sĩ chinh phục Bí Cảnh Cổ Đại.",
        usage="bi-canh [tao-phong|gia-nhap|bat-dau]"
    )
    async def bicanh_cmd(self, ctx: commands.Context, action: str = "tao-phong"):
        """Tổ đội 3-5 Tu Sĩ chinh phục Bí Cảnh Cổ Đại nhận Đan Dược & Công Pháp Cực Phẩm."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        ch_id = ctx.channel.id
        if action in ["tao-phong", "create"]:
            lobby_view = PartyLobbyView(ctx.author.id, "Bí Cảnh Cổ Đại — Ma Long Động")
            self.active_party_rooms[ch_id] = lobby_view
            embed = discord.Embed(
                title="🏰 LẬP ĐỘI BÍ CẢNH CỔ ĐẠI — MA LONG ĐỘNG",
                description=f"Trưởng đội: **{player.dao_hieu}**\nBấm nút bên dưới để chọn vai trò gia nhập đội!\nTrưởng đội bấm **🚀 Bắt Đầu Đột Phá** khi đã sẵn sàng.",
                color=discord.Color.blue()
            )
            msg_obj = await ctx.send(embed=embed, view=lobby_view)
            await lobby_view.wait()

            if not lobby_view.is_started:
                if ch_id in self.active_party_rooms:
                    del self.active_party_rooms[ch_id]
                try:
                    await msg_obj.edit(content="⏱️ **Phòng Bí Cảnh đã hết hạn chờ sau 2 phút!**", view=None)
                except Exception:
                    pass
                return

            mem_count = len(lobby_view.members)
            total_realm_sum = 0
            for uid in lobby_view.members.keys():
                p = self.db.get_player(uid)
                if p:
                    total_realm_sum += p.realm_index
            avg_realm = total_realm_sum / max(1, mem_count)
            total_dps = int(mem_count * (3000 + avg_realm * 2000))
            exp_per_mem = int(10000 + (avg_realm * 5000))
            lt_per_mem = int(2000 + (avg_realm * 1000))

            for uid in lobby_view.members.keys():
                p = self.db.get_player(uid)
                if p:
                    req_exp = REALM_REQUIRED_EXP.get(p.realm_index, 1000000000)
                    p.exp = min(req_exp, p.exp + exp_per_mem)
                    p.linh_thach += lt_per_mem
                    self.db.update_player(p)

            embed_res = discord.Embed(
                title="🐉 ĐỘT PHÁ BÍ CẢNH MA LONG ĐỘNG THÀNH CÔNG!",
                description=f"Tổ đội **{mem_count} Tu Sĩ** phối hợp nhịp nhàng, gây `{total_dps:,}` Sát thương tiêu diệt Ma Long!\n"
                            f"🎁 Mỗi thành viên nhận: `+{exp_per_mem:,}` EXP | `+{lt_per_mem:,}` Linh Thạch!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed_res)
            if ch_id in self.active_party_rooms:
                del self.active_party_rooms[ch_id]

    @commands.command(
        name="diet-boss",
        aliases=["boss-server", "worldboss"],
        brief="Xông vào Ma Vương Giáng Lâm (World Boss Server).",
        usage="diet-boss"
    )
    async def dietboss_cmd(self, ctx: commands.Context):
        """Xông vào Ma Vương Giáng Lâm (World Boss Toàn Server, tiêu 10 Tinh Lực, hồi 10 phút)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        now = time.time()
        if player.kinh_mach_doan_tuyet_until and player.kinh_mach_doan_tuyet_until > now:
            remain_min = int((player.kinh_mach_doan_tuyet_until - now) // 60) + 1
            await ctx.send(f"🩸 **BẠN ĐANG BỊ KINH MẠCH ĐOẠN TUYỆT!** (`{remain_min} phút` nữa)\n"
                           f"> 💊 Hãy phục hồi trước khi khiêu chiến Ma Vương!")
            return

        if player.is_meditating:
            await ctx.send("🧘 **BẠN ĐANG BẾ QUAN!** Vui lòng gõ `!xuat-quan` trước khi khiêu chiến Ma Vương.")
            return

        if player.hp <= 0:
            await ctx.send("💀 **BẠN ĐANG TRỌNG THƯƠNG (0 HP)!** Vui lòng hồi phục HP trước khi khiêu chiến Ma Vương!")
            return

        BOSS_COOLDOWN = 600  # 10 phút
        if player.last_boss_attack and (now - player.last_boss_attack < BOSS_COOLDOWN):
            remain_min = int((BOSS_COOLDOWN - (now - player.last_boss_attack)) // 60) + 1
            await ctx.send(f"⏳ **CHƯA THỂ KHIÊU CHIẾN!** Cần tĩnh dưỡng `{remain_min} phút` nữa mới có thể tiếp tục công kích Ma Vương.")
            return

        if player.tinh_luc < 10:
            await ctx.send(f"❌ Không đủ Tinh Lực! Cần `10` Tinh Lực để khiêu chiến Ma Vương (Hiện có: `{player.tinh_luc}/100`).")
            return

        player.tinh_luc -= 10
        player.last_boss_attack = now
        self.db.update_player(player)

        p_atk, crit_chance = calculate_player_pve_atk(player)
        dmg = int(p_atk * random.uniform(2.5, 4.0))

        self.world_boss_hp = max(0, self.world_boss_hp - dmg)
        self.db.update_world_boss_hp(self.world_boss_hp)
        self.db.update_world_boss_dps(player.user_id, dmg)

        embed = discord.Embed(
            title=f"🔥 THÁI CỔ MA VƯƠNG GIÁNG LÂM 🔥",
            description=f"⚔️ Tu sĩ **{player.dao_hieu}** dốc toàn lực tung ra đòn chí mạng gây **`{dmg:,}` Sát Thương** lên **{self.world_boss_name}**!\n"
                        f"> 🐍 Máu Ma Vương còn: `{self.world_boss_hp:,} / {self.world_boss_max_hp:,}` HP\n"
                        f"> ⚡ Tinh Lực còn lại: `{player.tinh_luc}/100` | Hồi lượt sau: `10 phút`",
            color=discord.Color.dark_purple()
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="bi-canh-cam-dia",
        aliases=["camdia", "roguelike"],
        brief="Vào Thái Cổ Cấm Địa Roguelike (Mê Cung 5 Phòng Sinh Tồn).",
        usage="bi-canh-cam-dia"
    )
    async def camdia_cmd(self, ctx: commands.Context):
        """Khám phá Mê Cung Sinh Tồn Roguelike — Thái Cổ Cấm Địa."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        rooms = generate_roguelike_dungeon_matrix()
        embed = discord.Embed(
            title="🕸️ THÁI CỔ CẤM ĐỊA — MÊ CUNG SINH TỒN (ROGUELIKE)",
            description=f"Tu sĩ **[{player.dao_hieu}]** chính thức bước vào cấm địa! (HP: `{player.hp:,}/{player.max_hp:,}`)\n"
                        f"⚠️ *Lưu ý: Khí huyết không tự phục hồi giữa các phòng!*",
            color=discord.Color.dark_red()
        )
        msg_obj = await ctx.send(embed=embed)

        dungeon_failed = False
        for idx, room in enumerate(rooms, 1):
            await asyncio.sleep(1.5)
            r_embed = discord.Embed(
                title=f"🏛️ PHÒNG [{idx}/5]: {room['title']}",
                description=f"> *{room['desc']}*",
                color=discord.Color.gold()
            )

            if room["type"] == "MONSTER":
                monster = generate_pve_monster(player.realm_index)
                log, monster = process_turn_action(player, monster, "ATTACK")
                r_embed.add_field(name="⚔️ Trận Chiến Yêu Thú", value=f"> {log['message']}", inline=False)

            elif room["type"] == "TRAP":
                trap_view = TrapSacrificeView(ctx.author.id)
                await msg_obj.edit(embed=r_embed, view=trap_view)
                await trap_view.wait()
                trap_mult = 0.80 if trap_view.choice == "ONE" else 0.20
                dmg_trap = int(player.max_hp * trap_mult)
                player.hp = max(1, player.hp - dmg_trap)
                choice_desc = "Hi sinh cá nhân (-80% HP)" if trap_view.choice == "ONE" else "Cùng gánh vác (-20% HP)"
                r_embed.add_field(name=f"🩸 Bẫy Cổ Trận ({choice_desc})", value=f"Bẫy cổ kích hoạt, tổn thất `-{dmg_trap:,}` HP!", inline=False)

            elif room["type"] == "MIMIC":
                if random.random() < 0.50:
                    player.tien_ngoc += 30
                    r_embed.add_field(name="✨ Rương Thần", value="Mở rương thật! Nhận `+30` Tiên Ngọc 🌟!", inline=False)
                else:
                    m_dmg = int(player.max_hp * 0.25)
                    player.hp = max(1, player.hp - m_dmg)
                    r_embed.add_field(name="🐍 Rương Mimic Giả", value=f"Rương giả cắn chí mạng `-{m_dmg:,}` HP!", inline=False)

            elif room["type"] == "MERCHANT":
                merchant_view = DungeonMerchantView(ctx.author.id, db=self.db)
                await msg_obj.edit(embed=r_embed, view=merchant_view)
                await merchant_view.wait()

            elif room["type"] == "BOSS":
                boss = generate_pve_monster(player.realm_index, floor_offset=3)
                boss["name"] = "🐉 THÁI CỔ MÃNG HOÀNG (BOSS CẤM ĐỊA)"
                log, boss = process_turn_action(player, boss, "GONGFA")
                r_embed.add_field(name="🐉 Trảm Boss Cấm Địa", value=f"> {log['message']}", inline=False)

            self.db.update_player(player)
            await msg_obj.edit(embed=r_embed, view=None)

            # Kiểm tra player chết giữa dungeon
            if player.hp <= 0:
                dungeon_failed = True
                hardcore_res = process_hardcore_defeat(player, self.db, "Thái Cổ Cấm Địa")
                death_embed = discord.Embed(
                    title="💀 TỬ TRẬN TRONG CẤM ĐỊA!",
                    description=f"Tu sĩ **{player.dao_hieu}** đã gục ngã tại Phòng [{idx}/5]!\n"
                                f"> ⚠️ Kinh Mạch Đoạn Tuyệt (10 phút)! Nhờ đạo hữu `!cuu-thuong @user` hoặc mua đan dược tại `!tiencac`!",
                    color=discord.Color.dark_red()
                )
                if hardcore_res["stolen_lt"] > 0:
                    death_embed.add_field(name="💸 Tổn Thất", value=f"Bị rơi mất `{hardcore_res['stolen_lt']:,}` Linh Thạch!", inline=False)
                if hardcore_res.get("dropped_herbs", 0) > 0 or hardcore_res.get("dropped_ores", 0) > 0:
                    loss_mats = []
                    if hardcore_res.get("dropped_herbs", 0) > 0:
                        loss_mats.append(f"`{hardcore_res['dropped_herbs']}` Thảo Dược Thô 🌿")
                    if hardcore_res.get("dropped_ores", 0) > 0:
                        loss_mats.append(f"`{hardcore_res['dropped_ores']}` Thần Thiết Thô ⛏️")
                    death_embed.add_field(name="🎒 Tổn Thất Túi Đồ", value=f"Túi trữ vật rách toang, rơi mất: " + " | ".join(loss_mats), inline=False)
                await ctx.send(embed=death_embed)
                break

        if not dungeon_failed:
            win_embed = discord.Embed(
                title="🏆 VIÊN MÃN THÔNG QUAN THÁI CỔ CẤM ĐỊA!",
                description=f"Chúc mừng Tu sĩ **{player.dao_hieu}** đã sinh tồn thành công qua 5 phòng Cấm Địa!",
                color=discord.Color.green()
            )
            await ctx.send(embed=win_embed)

    @commands.command(
        name="cuu-thuong",
        aliases=["cuuthuong", "rescue"],
        brief="Dùng Vạn Linh Đan hoặc Tiên Ngọc cứu đạo hữu bị Kinh Mạch Đoạn Tuyệt.",
        usage="cuu-thuong @user"
    )
    async def cuuthuong_cmd(self, ctx: commands.Context, target: discord.Member):
        """Cứu đạo hữu khỏi nạn Kinh Mạch Đoạn Tuyệt (Hại Căn Cơ)."""
        saver = self.db.get_player(ctx.author.id)
        victim = self.db.get_player(target.id)

        if not saver or not victim:
            await ctx.send("❌ Cả 2 tu sĩ đều phải nhập môn Tu Tiên!")
            return

        now = time.time()
        if not victim.kinh_mach_doan_tuyet_until or victim.kinh_mach_doan_tuyet_until <= now:
            await ctx.send(f"❌ Tu sĩ **{victim.dao_hieu}** kinh mạch bình thường, không ở trong trạng thái nguy cấp!")
            return

        if saver.van_linh_dan > 0:
            saver.van_linh_dan -= 1
            used_str = "1x Vạn Linh Đan"
        elif saver.tien_ngoc >= 20:
            saver.tien_ngoc -= 20
            used_str = "20 Tiên Ngọc"
        else:
            await ctx.send("❌ Bạn không sở hữu **Vạn Linh Đan** hoặc **20 Tiên Ngọc** để thực hiện cứu chữa đạo hữu!")
            return

        victim.kinh_mach_doan_tuyet_until = None
        victim.hp = int(victim.max_hp * 0.50)
        self.db.update_player(saver)
        self.db.update_player(victim)

        await ctx.send(f"✨ **CỨU THƯƠNG THÀNH CÔNG!** **{saver.dao_hieu}** đã dùng `{used_str}` cứu **{victim.dao_hieu}** khỏi nạn Kinh Mạch Đoạn Tuyệt (Phục hồi 50% HP)!")

    @commands.command(
        name="giai-doc",
        aliases=["giaidoc", "cleanse"],
        brief="Tẩy trừ hiệu ứng Độc Tố Thấu Cốt / Ô Nhiễm Tâm Ma (Tiêu tốn 500 Linh Thạch).",
        usage="giai-doc"
    )
    async def giaidoc_cmd(self, ctx: commands.Context):
        """Tẩy trừ hiệu ứng Độc Tố Thấu Cốt / Ô Nhiễm Tâm Ma."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if not player.lingering_debuff:
            await ctx.send("✅ Cơ thể bạn thanh sạch, không bị dính độc tố hay tâm ma ô nhiễm!")
            return

        if player.linh_thach < 500:
            await ctx.send("❌ Chi phí giải độc tẩy tâm ma là `500` Linh Thạch! Bạn không đủ Linh Thạch.")
            return

        player.linh_thach -= 500
        player.lingering_debuff = None
        self.db.update_player(player)
        await ctx.send(f"✨ **TẨY TRỪ THÀNH CÔNG!** Tu sĩ **{player.dao_hieu}** đã tốn `500` Linh Thạch giải trừ toàn bộ Độc Tố & Ô Nhiễm Tâm Ma!")

    @commands.command(
        name="dung-dan",
        aliases=["dungdan", "use-pill", "su-dung-dan"],
        brief="Sử dụng Cửu Chuyển Tái Tạo Đan để hồi 100% HP/Mana và xóa sạch chấn thương, độc tố.",
        usage="dung-dan"
    )
    async def dungdan_cmd(self, ctx: commands.Context):
        """Sử dụng Cửu Chuyển Tái Tạo Đan."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        consumed = False
        if player.cuu_chuyen_dan > 0:
            player.cuu_chuyen_dan -= 1
            consumed = True
        elif self.db.consume_item(player.user_id, "Cửu Chuyển Tái Tạo Đan", 1):
            consumed = True

        if not consumed:
            await ctx.send("❌ Bạn không sở hữu **Cửu Chuyển Tái Tạo Đan**! Mua tại `!tiencac` với 150 Tiên Ngọc hoặc luyện tại `!luyen-dan`.")
            return

        player.hp = player.max_hp
        player.mana = player.max_mana
        player.can_co = 100.0
        player.chan_thuong_until = None
        player.tau_hoa_nhap_ma_until = None
        player.kinh_mach_doan_tuyet_until = None
        player.lingering_debuff = None
        player.continuous_cultivation_count = 0
        player.linh_luc_tap_chat = False
        self.db.update_player(player)

        await ctx.send(f"💊 **SỬ DỤNG CỬU CHUYỂN TÁI TẠO ĐAN THÀNH CÔNG!** Tu sĩ **{player.dao_hieu}** đã hồi phục 100% HP, Mana, 100% Căn Cơ và tẩy sạch toàn bộ Chấn Thương, Tạp Chất Linh Lực, Tẩu Hỏa Nhập Ma & Độc Tố!")

    @commands.command(
        name="su-dung",
        aliases=["sudung", "use", "dung-item", "dung"],
        brief="Sử dụng vật phẩm/đan dược có trong Túi Trữ Vật (!ttinv).",
        usage="su-dung [tên_vật_phẩm]"
    )
    async def sudung_cmd(self, ctx: commands.Context, *, item_name: str = None):
        """Sử dụng vật phẩm/đan dược trong Túi Trữ Vật."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if not item_name:
            await ctx.send(
                "❌ Vui lòng nhập tên vật phẩm muốn dùng!\n"
                "> 💡 Cú pháp: `!su-dung <Tên Vật Phẩm>` (Ví dụ: `!su-dung Dinh Than Dan`, `!su-dung Cuu Chuyen Tai Tao Dan`)\n"
                "> 🎒 Gõ `!ttinv` hoặc `!tui-do` để kiểm tra túi đồ."
            )
            return

        item_name_clean = item_name.strip().lower()

        # 1. Cửu Chuyển Tái Tạo Đan
        if "cửu chuyển" in item_name_clean or "cuu chuyen" in item_name_clean or "tái tạo đan" in item_name_clean or "tai tao dan" in item_name_clean:
            await self.dungdan_cmd(ctx)
            return

        # 2. Định Thần Đan
        if "định thần" in item_name_clean or "dinh than" in item_name_clean:
            if not self.db.consume_item(player.user_id, "Định Thần Đan", 1):
                await ctx.send("❌ Bạn không có **Định Thần Đan** trong túi đồ! Luyện tại `!luyen-dan`.")
                return
            player.chan_thuong_until = None
            player.tau_hoa_nhap_ma_until = None
            player.lingering_debuff = None
            player.continuous_cultivation_count = 0
            player.linh_luc_tap_chat = False
            heal_hp = int(player.max_hp * 0.30)
            heal_mana = int(player.max_mana * 0.30)
            player.hp = min(player.max_hp, player.hp + heal_hp)
            player.mana = min(player.max_mana, player.mana + heal_mana)
            self.db.update_player(player)
            await ctx.send(f"💊 **SỬ DỤNG ĐỊNH THẦN ĐAN THÀNH CÔNG!** Đã hồi `+{heal_hp:,}` HP, `+{heal_mana:,}` Mana và xóa bỏ toàn bộ Chấn Thương, Tẩu Hỏa & Tạp Chất Linh Lực!")
            return

        # 3. Vạn Linh Đan (Tự dùng cứu thân)
        if "vạn linh" in item_name_clean or "van linh" in item_name_clean:
            consumed = False
            if player.van_linh_dan > 0:
                player.van_linh_dan -= 1
                consumed = True
            elif self.db.consume_item(player.user_id, "Vạn Linh Đan", 1):
                consumed = True

            if not consumed:
                await ctx.send("❌ Bạn không có **Vạn Linh Đan** trong túi đồ! Luyện tại `!luyen-dan`.")
                return

            player.kinh_mach_doan_tuyet_until = None
            player.hp = max(player.hp, int(player.max_hp * 0.50))
            self.db.update_player(player)
            await ctx.send(f"✨ **SỬ DỤNG VẠN LINH ĐAN THÀNH CÔNG!** Đã cứu chữa Kinh Mạch Đoạn Tuyệt và hồi phục 50% HP!")
            return

        # 4. Tẩy Tủy Phù
        if "tẩy tủy" in item_name_clean or "tay tuy" in item_name_clean:
            if player.tay_tuy_phu > 0 or self.db.consume_item(player.user_id, "Tẩy Tủy Phù", 1):
                from app.discord_bot.modules.tutien.engines.gacha import process_gacha_rolls
                ok, msg, res, updated_player = process_gacha_rolls(self.db, player, "caimenh", 1)
                await ctx.send(f"{msg}\n> 🔮 **Linh Căn mới:** `{updated_player.linh_can_quality}` ({updated_player.linh_can_element})")
            else:
                await ctx.send("❌ Bạn không có **Tẩy Tủy Phù** trong túi đồ! Luyện tại `!luyen-dan` hoặc quay gacha.")
            return

        # 5. Niết Bàn Đan
        if "niết bàn" in item_name_clean or "niet ban" in item_name_clean:
            if not self.db.consume_item(player.user_id, "Niết Bàn Đan", 1):
                await ctx.send("❌ Bạn không có **Niết Bàn Đan** trong túi đồ!")
                return
            player.hp = player.max_hp
            player.mana = player.max_mana
            player.can_co = min(100.0, player.can_co + 5.0)
            self.db.update_player(player)
            await ctx.send(f"🔥 **SỬ DỤNG NIẾT BÀN ĐAN THÀNH CÔNG!** Toàn thân dục hỏa trùng sinh, hồi đầy 100% HP/Mana và tăng `+5%` Căn Cơ!")
            return

        # 6. Các loại Đan Phá Cảnh (Trúc Cơ Đan, Kim Đan Sa, Ngưng Anh Đan...)
        if any(w in item_name_clean for w in ["trúc cơ", "truc co", "kim đan", "kim dan", "ngưng anh", "ngung anh", "hóa thần", "hoa than", "phá hư", "pha hu"]):
            await ctx.send(
                f"💊 **{item_name.title()}** là **Đan Dược Phá Cảnh**!\n"
                f"> ✨ Đan dược này sẽ **tự động kích hoạt & tiêu thụ** khi bạn gõ `!dotpha` lúc Tu Vi đã đạt 100% để bảo vệ đan điền khỏi nổ tung!"
            )
            return

        # 7. Các loại Bùa Bảo Hiểm Bị Động
        if any(w in item_name_clean for w in ["bảo mệnh", "bao menh", "thánh thể", "thanh the", "hộ thân", "ho than"]):
            await ctx.send(
                f"🛡️ **{item_name.title()}** là **Pháp Bảo/Bùa Hộ Thân Tự Động**!\n"
                f"> ✨ Vật phẩm này sẽ tự động kích hoạt bảo vệ tính mạng khi bạn Độ Kiếp thất bại hoặc tử trận PVE mà không cần dùng thủ công!"
            )
            return

        # 8. Vật phẩm khác hoặc không hỗ trợ
        inv = self.db.get_inventory(player.user_id)
        matched_item = next((i for i in inv if item_name_clean in i["item_name"].lower()), None)
        if matched_item:
            await ctx.send(
                f"📦 Bạn đang sở hữu `{matched_item['quantity']}x` **{matched_item['item_name']}** ({matched_item['item_type']}).\n"
                f"> ℹ️ Đây là vật phẩm nguyên liệu hoặc trang bị bị động. Hãy dùng trong `!luyen-dan`, `!luyen-khi` hoặc đăng bán tại `!cho-troi`!"
            )
        else:
            await ctx.send(f"❌ Không tìm thấy vật phẩm **[{item_name}]** trong túi đồ! Gõ `!ttinv` để xem danh sách.")

    @commands.command(
        name="luyen-dan",
        aliases=["luyendan", "alchemy", "che-dan"],
        brief="Luyện chế Linh Đan, Thần Phù từ Thảo Dược Thô và Linh Thạch.",
        usage="luyen-dan [tên_đan_dược]"
    )
    async def luyendan_cmd(self, ctx: commands.Context, *, pill_name: str = None):
        """Luyện chế Linh Đan, Thần Phù (!luyen-dan)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        inv = self.db.get_inventory(ctx.author.id)
        herb_item = next((item for item in inv if "Thảo Dược" in item["item_name"]), None)
        herb_count = herb_item["quantity"] if herb_item else 0

        # Nếu không truyền tên đan: hiển thị Đan Phổ (Danh mục công thức)
        if not pill_name:
            embed = discord.Embed(
                title="🧪 THIÊN ĐỊA ĐAN LÒ — ĐAN PHỔ LUYỆN DƯỢC 🧪",
                description=f"Tu sĩ: **[{player.dao_hieu}]** ({player.linh_can_element})\n"
                            f"🌿 **Thảo Dược Thô có sẵn:** `{herb_count:,}` cây | 💰 **Linh Thạch:** `{player.linh_thach:,}`\n"
                            f"> Cú pháp luyện chế: `!luyen-dan <Tên Đan Dược>` (Ví dụ: `!luyen-dan Van Linh Dan`)\n"
                            f"> 🔥 *Linh Căn Hỏa được +15% Tỷ lệ thành công khi Luyện Đan!*",
                color=discord.Color.dark_teal()
            )
            for key, rec in ALCHEMY_RECIPES.items():
                fire_bonus = " *(+15% Hỏa)*" if "Hỏa" in player.linh_can_element else ""
                rate_pct = int(min(95, rec['base_rate'] + (player.ngo_tinh * 0.01) + (0.15 if "Hỏa" in player.linh_can_element else 0.0)) * 100)
                val = (
                    f"> 🌿 Nguyên liệu: `{rec['herbs']}` Thảo Dược Thô + `{rec['linh_thach']:,}` Linh Thạch\n"
                    f"> ⚡ Tỷ lệ đan thành: **{rate_pct}%**{fire_bonus}\n"
                    f"> 📜 *{rec['desc']}*"
                )
                embed.add_field(name=f"💊 {rec['name']} [{rec['type']}]", value=val, inline=False)

            embed.set_footer(text="Săn quái (!sanyeu) để nhặt thêm Thảo Dược Thô!")
            await ctx.send(embed=embed)
            return

        # Tìm công thức match
        target_recipe_key = None
        for key in ALCHEMY_RECIPES.keys():
            if pill_name.lower() in key.lower():
                target_recipe_key = key
                break

        if not target_recipe_key:
            await ctx.send(f"❌ Không tìm thấy công thức đan dược **[{pill_name}]** trong Đan Phổ! Gõ `!luyen-dan` để xem danh sách.")
            return

        recipe = ALCHEMY_RECIPES[target_recipe_key]
        req_herbs = recipe["herbs"]
        req_lt = recipe["linh_thach"]

        # Kiểm tra thảo dược
        if herb_count < req_herbs:
            await ctx.send(
                f"❌ Không đủ **Thảo Dược Thô**! Cần `{req_herbs}` cây (Hiện có: `{herb_count}`).\n"
                f"> 🌿 Hãy đi Săn Yêu (`!sanyeu`) để thu thập thêm thảo dược!"
            )
            return

        # Kiểm tra Linh Thạch trước khi trừ thảo dược
        if player.linh_thach < req_lt:
            await ctx.send(
                f"❌ Không đủ **Linh Thạch**! Cần `{req_lt:,}` Linh Thạch (Hiện có: `{player.linh_thach:,}`)."
            )
            return

        # Trừ thảo dược
        self.db.consume_item(player.user_id, herb_item["item_name"], req_herbs)

        # Tiến hành luyện đan
        success, msg, rec_data, updated_player = craft_alchemy_pill(player, target_recipe_key)
        if success and rec_data:
            # Cộng vật phẩm đan dược vào túi
            if target_recipe_key == "Vạn Linh Đan":
                updated_player.van_linh_dan += 1
            elif target_recipe_key == "Tẩy Tủy Phù":
                updated_player.tay_tuy_phu += 1
            elif target_recipe_key == "Cửu Chuyển Tái Tạo Đan":
                updated_player.cuu_chuyen_dan += 1
            else:
                self.db.add_item(player.user_id, rec_data["name"], rec_data["type"], 1)

        self.db.update_player(updated_player)
        await ctx.send(msg)

    @commands.command(
        name="luyen-khi",
        aliases=["luyenkhi", "che-tao", "duc-khi", "smithing"],
        brief="Rèn đúc Thần Binh, Trận Kỳ, Pháp Bảo từ Thần Thiết Thô và Linh Thạch.",
        usage="luyen-khi [tên_trang_bị]"
    )
    async def luyenkhi_cmd(self, ctx: commands.Context, *, equip_name: str = None):
        """Rèn đúc Thần Binh, Trận Kỳ, Pháp Bảo (!luyen-khi)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        inv = self.db.get_inventory(ctx.author.id)
        ore_item = next((item for item in inv if "Thần Thiết" in item["item_name"] or "Khoáng Thạch" in item.get("item_type", "")), None)
        ore_count = ore_item["quantity"] if ore_item else 0

        # Nếu không truyền tên: hiển thị Khí Phổ (Danh mục công thức)
        if not equip_name:
            embed = discord.Embed(
                title="⚒️ THIÊN CÔNG LÒ — KHÍ PHỔ LUYỆN KHÍ ⚒️",
                description=f"Tu sĩ: **[{player.dao_hieu}]** ({player.linh_can_element})\n"
                            f"⛏️ **Thần Thiết Thô có sẵn:** `{ore_count:,}` khối | 💰 **Linh Thạch:** `{player.linh_thach:,}`\n"
                            f"> Cú pháp đúc tạo: `!luyen-khi <Tên Bảo Vật>` (Ví dụ: `!luyen-khi Ho Than Phu`)\n"
                            f"> ⚡ *Linh Căn Kim (+15%) & Hỏa (+10%) tăng Tỷ lệ Đúc Khí thành công!*",
                color=discord.Color.dark_gold()
            )
            for key, rec in FORGING_RECIPES.items():
                kim_bonus = " *(+15% Kim)*" if "Kim" in player.linh_can_element else (" *(+10% Hỏa)*" if "Hỏa" in player.linh_can_element else "")
                bonus_pct = 0.15 if "Kim" in player.linh_can_element else (0.10 if "Hỏa" in player.linh_can_element else 0.0)
                rate_pct = int(min(95, rec['base_rate'] + (player.ngo_tinh * 0.01) + bonus_pct) * 100)
                val = (
                    f"> ⛏️ Nguyên liệu: `{rec['ore']}` Thần Thiết Thô + `{rec['linh_thach']:,}` Linh Thạch\n"
                    f"> ⚡ Tỷ lệ đúc thành: **{rate_pct}%**{kim_bonus}\n"
                    f"> 📜 *{rec['desc']}*"
                )
                embed.add_field(name=f"🛡️ {rec['name']} [{rec['type']}]", value=val, inline=False)

            embed.set_footer(text="Săn quái (!sanyeu) để đào thêm Thần Thiết Thô!")
            await ctx.send(embed=embed)
            return

        # Tìm công thức match
        target_recipe_key = None
        for key in FORGING_RECIPES.keys():
            if equip_name.lower() in key.lower():
                target_recipe_key = key
                break

        if not target_recipe_key:
            await ctx.send(f"❌ Không tìm thấy bản vẽ bảo vật **[{equip_name}]** trong Khí Phổ! Gõ `!luyen-khi` để xem danh sách.")
            return

        recipe = FORGING_RECIPES[target_recipe_key]
        req_ore = recipe["ore"]
        req_lt = recipe["linh_thach"]

        if ore_count < req_ore:
            await ctx.send(
                f"❌ Không đủ **Thần Thiết Thô**! Cần `{req_ore}` khối (Hiện có: `{ore_count}`).\n"
                f"> ⛏️ Hãy đi Săn Yêu (`!sanyeu`) để khai thác thêm khoáng thạch!"
            )
            return

        if player.linh_thach < req_lt:
            await ctx.send(
                f"❌ Không đủ **Linh Thạch**! Cần `{req_lt:,}` Linh Thạch (Hiện có: `{player.linh_thach:,}`)."
            )
            return

        # Trừ khoáng thạch trước
        self.db.consume_item(player.user_id, ore_item["item_name"], req_ore)

        # Tiến hành đúc khí
        success, msg, rec_data, updated_player = craft_equipment_item(player, target_recipe_key)
        if success and rec_data:
            self.db.add_item(player.user_id, rec_data["name"], rec_data["type"], 1)

        self.db.update_player(updated_player)
        await ctx.send(msg)

    # --- 🏪 SÀN ĐẤU GIÁ & CHỢ TU TIÊN (AUCTION HOUSE) ---

    @commands.command(
        name="cho-troi",
        aliases=["chotroi", "dau-gia", "daugia", "market", "san-dau-gia"],
        brief="Xem các vật phẩm, đan dược, pháp bảo đang bày bán trên Sàn Đấu Giá.",
        usage="cho-troi"
    )
    async def chotroi_cmd(self, ctx: commands.Context):
        """Xem Sàn Đấu Giá Chợ Trời Tu Tiên (!cho-troi)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        auctions = self.db.get_active_auctions(limit=15)
        embed = discord.Embed(
            title="🏪 SÀN ĐẤU GIÁ — VẠN BẢO CÁC 🏪",
            description=f"Tu sĩ: **[{player.dao_hieu}]** | 💰 **Linh Thạch của bạn:** `{player.linh_thach:,}`\n"
                        f"> 💡 Mua hàng: `!mua-hang <Mã_Số>` (Ví dụ: `!mua-hang 1`)\n"
                        f"> 💡 Đăng bán: `!dang-ban <Tên_Vật_Phẩm> <Số_Lượng> <Giá_Linh_Thạch>`\n"
                        f"> 💡 Rút hàng: `!huy-ban <Mã_Số>`",
            color=discord.Color.gold()
        )

        if not auctions:
            embed.add_field(name="📦 Hiện Tại Chưa Có Vật Phẩm Nào", value="> Hãy là người đầu tiên đăng bán vật phẩm từ Túi Đồ bằng lệnh `!dang-ban`!", inline=False)
        else:
            now = time.time()
            for auc in auctions:
                remain_h = max(0, int((auc['expires_at'] - now) / 3600))
                remain_m = max(0, int(((auc['expires_at'] - now) % 3600) / 60))
                seller_str = auc.get('seller_name') or f"Đạo hữu ({auc['seller_id']})"
                val = (
                    f"> 👤 Người bán: **{seller_str}**\n"
                    f"> 💰 Giá bán: `{auc['price']:,}` Linh Thạch\n"
                    f"> ⏳ Hết hạn sau: `{remain_h}h {remain_m}m`\n"
                    f"> 👉 Mua nhanh: `!mua-hang {auc['auction_id']}`"
                )
                embed.add_field(name=f"🏷️ [Mã #{auc['auction_id']}] {auc['quantity']}x {auc['item_name']}", value=val, inline=False)

        embed.set_footer(text="Mọi giao dịch áp dụng thuế 5% Linh Thạch thiêu đốt bảo hộ kinh tế.")
        await ctx.send(embed=embed)

    @commands.command(
        name="dang-ban",
        aliases=["dangban", "sell-item", "rao-ban"],
        brief="Đăng bán vật phẩm từ Túi Đồ lên Sàn Đấu Giá.",
        usage="dang-ban [tên_vật_phẩm] [số_lượng] [giá_linh_thạch]"
    )
    async def dangban_cmd(self, ctx: commands.Context, item_name: str, quantity: int, price: int):
        """Đăng bán vật phẩm từ Túi Đồ lên Sàn Đấu Giá (!dang-ban)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if quantity <= 0 or price <= 0:
            await ctx.send("❌ Số lượng và giá bán phải lớn hơn 0!")
            return

        if price > 100000000:
            await ctx.send("❌ Giá bán không được vượt quá 100,000,000 Linh Thạch!")
            return

        inv = self.db.get_inventory(ctx.author.id)
        matched_item = None
        for it in inv:
            if item_name.lower() in it["item_name"].lower():
                matched_item = it
                break

        if not matched_item or matched_item["quantity"] < quantity:
            avail = matched_item["quantity"] if matched_item else 0
            await ctx.send(f"❌ Bạn không đủ vật phẩm **[{item_name}]** trong Túi Đồ! (Hiện có: `{avail}`). Gõ `!ttinv` để kiểm tra.")
            return

        auction_id = self.db.create_auction(player.user_id, matched_item["item_name"], quantity, price, duration_hours=24)
        if not auction_id:
            await ctx.send("❌ Không thể đăng bán vật phẩm! Vui lòng thử lại sau.")
            return

        await ctx.send(
            f"✅ **ĐĂNG BÁN THÀNH CÔNG!**\n"
            f"> 🏷️ **Mã Phiên:** `#{auction_id}`\n"
            f"> 📦 **Vật phẩm:** `{quantity}x` **[{matched_item['item_name']}]**\n"
            f"> 💰 **Giá bán:** `{price:,}` Linh Thạch\n"
            f"> ⏳ Thời hạn bày bán: **24 Giờ** (Xem tại `!cho-troi`)."
        )

    @commands.command(
        name="mua-hang",
        aliases=["muahang", "mua-dau-gia", "buy-market"],
        brief="Mua vật phẩm từ Sàn Đấu Giá theo Mã Số Phiên.",
        usage="mua-hang [mã_số_phiên]"
    )
    async def muahang_cmd(self, ctx: commands.Context, auction_id: int):
        """Mua vật phẩm từ Sàn Đấu Giá (!mua-hang <Mã_Số>)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        success, msg = self.db.buy_auction_item(player.user_id, auction_id)
        await ctx.send(msg)

    @commands.command(
        name="huy-ban",
        aliases=["huyban", "cancel-sell", "rut-hang"],
        brief="Hủy phiên đăng bán và nhận lại vật phẩm về Túi Đồ.",
        usage="huy-ban [mã_số_phiên]"
    )
    async def huyban_cmd(self, ctx: commands.Context, auction_id: int):
        """Hủy phiên đăng bán (!huy-ban <Mã_Số>)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        success, msg = self.db.cancel_auction(player.user_id, auction_id)
        await ctx.send(msg)

    # --- 🏡 ĐỘNG PHỦ & NÂNG CẤP TỤ LINH TRẬN (LINH THẠCH SINK) ---

    @commands.command(
        name="dong-phu",
        aliases=["dongphu", "nang-cap-dong-phu", "tu-gia", "dong-phu-tu-luyen"],
        brief="Xem thông tin Động Phủ & Nâng Cấp Tụ Linh Trận bằng Linh Thạch.",
        usage="dong-phu [nangcap]"
    )
    async def dongphu_cmd(self, ctx: commands.Context, action: str = None):
        """Xem & Nâng Cấp Động Phủ (!dong-phu [nangcap])."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        current_lvl = player.dong_phu_level
        upgrade_cost = int(15000 * (current_lvl ** 1.4))

        if action and action.lower() in ["nangcap", "upgrade", "up", "nang-cap"]:
            if current_lvl >= 50:
                await ctx.send("👑 Động Phủ của bạn đã đạt Cấp Tối Đa (Cấp 50 - Tiên Đế Tiên Phủ)!")
                return

            if player.linh_thach < upgrade_cost:
                await ctx.send(f"❌ Không đủ Linh Thạch để nâng cấp Động Phủ! Cần `{upgrade_cost:,}` Linh Thạch (Hiện có: `{player.linh_thach:,}`).")
                return

            player.linh_thach -= upgrade_cost
            player.dong_phu_level += 1
            self.db.update_player(player)

            new_lvl = player.dong_phu_level
            new_exp_buff = int((new_lvl - 1) * 15)
            await ctx.send(
                f"🏰 **NÂNG CẤP ĐỘNG PHỦ THÀNH CÔNG!**\n"
                f"> 🏡 Động Phủ đã thăng cấp lên: **Cấp {new_lvl}**!\n"
                f"> ⚡ Hiệu suất Tụ Linh Trận: **+{new_exp_buff}% EXP Bế Quan & Tu Luyện**!\n"
                f"> 🛡️ Tăng thêm +2 Điểm Hộ Trận Đột Phá Lôi Kiếp!"
            )
            return

        # View Động Phủ status
        exp_buff = int((current_lvl - 1) * 15)
        embed = discord.Embed(
            title=f"🏰 TIÊN GIA ĐỘNG PHỦ — [{player.dao_hieu}]",
            description=f"Cấp độ Động Phủ: **Cấp {current_lvl} / 50**\n"
                        f"💰 **Linh Thạch hiện có:** `{player.linh_thach:,}`\n\n"
                        f"✨ **Hiệu Quả Tụ Linh Trận:**\n"
                        f"> ⚡ Gia tăng tốc độ Tu Luyện & Bế Quan: **+{exp_buff}% EXP**\n"
                        f"> 🛡️ Hộ Thân Đột Phá: **+{min(20, current_lvl * 2)} Điểm Kháng Kiếp**\n\n"
                        f"🛠️ **Nâng cấp lên Cấp {current_lvl + 1}:**\n"
                        f"> 💰 Chi phí: `{upgrade_cost:,}` Linh Thạch\n"
                        f"> 👉 Gõ `!dong-phu nangcap` để tiến hành nâng cấp!",
            color=discord.Color.green()
        )
        embed.set_footer(text="Nâng cấp Động Phủ giúp tối đa hóa thu nhập tu vi khi bế quan AFK!")
        await ctx.send(embed=embed)

    @commands.command(
        name="doi-cong-phap",
        aliases=["doicongphap", "trang-bi-cong-phap", "cong-phap"],
        brief="Trang bị / Thay đổi Công Pháp Chủ Tu từ Túi Đồ.",
        usage="doi-cong-phap [tên_công_pháp]"
    )
    async def doicongphap_cmd(self, ctx: commands.Context, *, gongfa_name: str = None):
        """Trang bị / Thay đổi Công Pháp Chủ Tu từ Túi Đồ (!doi-cong-phap)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        gongfa = self.db.get_gongfa(ctx.author.id)

        if not gongfa_name:
            inv = self.db.get_inventory(ctx.author.id)
            available = [item["item_name"] for item in inv if "Công Pháp" in item.get("item_type", "") or "《" in item.get("item_name", "")]
            available_str = "\n".join([f"> 📜 `{name}`" for name in available]) if available else "> *(Chưa sở hữu bí kíp Công Pháp nào khác, quay Gacha `!quay-gacha` hoặc đổi tại `!linhbui-shop`)*"
            
            embed = discord.Embed(
                title="📜 CÔNG PHÁP CHỦ TU HIỆN TẠI",
                description=f"Công Pháp đang tu luyện: **{gongfa.chu_tu}**\n\n"
                            f"**📚 Sách Công Pháp Trong Túi Đồ:**\n{available_str}\n\n"
                            f"> 💡 Gõ `!doi-cong-phap <Tên Công Pháp>` để chuyển đổi (Ví dụ: `!doi-cong-phap Thôn Thiên Ma Công` hoặc `!doi-cong-phap Phàm Nhân Quyết`).",
                color=discord.Color.gold()
            )
            await ctx.send(embed=embed)
            return

        # Find matching gongfa in database or inventory
        target_name = None
        for key in GONGFA_DATABASE.keys():
            if gongfa_name.lower() in key.lower() or key.lower().strip("《》") in gongfa_name.lower():
                target_name = key
                break

        if not target_name:
            await ctx.send(f"❌ Không tìm thấy Công Pháp **[{gongfa_name}]** trong ma trận bí kíp! Hãy gõ `!doi-cong-phap` để xem danh sách.")
            return

        if target_name != "《Phàm Nhân Quyết》":
            inv = self.db.get_inventory(ctx.author.id)
            clean_kw = target_name.replace("《", "").replace("》", "").strip().lower()
            has_book = any(clean_kw in item["item_name"].lower() for item in inv)
            if not has_book:
                await ctx.send(f"❌ Bạn không sở hữu bí kíp **[{target_name}]** trong Túi Đồ! Hãy quay Gacha `!quay-gacha` hoặc đổi tại `!tang-kinh-cac` / `!linhbui-shop`!")
                return

        gongfa.chu_tu = target_name
        self.db.update_gongfa(gongfa)

        info = GONGFA_DATABASE.get(target_name, {})
        await ctx.send(f"✨ **ĐỔI CÔNG PHÁP THÀNH CÔNG!** Tu sĩ **{player.dao_hieu}** đã chuyển sang chủ tu **[{target_name}]**!\n> 📜 *{info.get('desc', '')}*")

    @commands.command(
        name="tutien-inventory",
        aliases=["ttinv", "tutieninv", "tuitu", "tuidotutien", "inv-tutien"],
        brief="Xem Túi Trữ Vật Tu Tiên (Linh Thạch, Tiên Ngọc, Vé Gacha, Bùa bảo hiểm, Đan dược).",
        usage="tutien-inventory"
    )
    async def inventory_cmd(self, ctx: commands.Context):
        """Xem Túi Trữ Vật Tu Tiên (!ttinv)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        inv_items = self.db.get_inventory(ctx.author.id)

        embed = discord.Embed(
            title=f"🎒 TÚI TRỮ VẬT TU TIÊN — [{player.dao_hieu}]",
            description=f"☯ Tu sĩ: **[{player.dao_hieu}]** | Cảnh giới: **{player.realm_name}**",
            color=discord.Color.purple()
        )

        # 1. Currencies
        currencies_text = (
            f"> 💰 **Linh Thạch:** `{player.linh_thach:,}`\n"
            f"> 💎 **Tiên Ngọc (Nạp):** `{player.tien_ngoc:,}`\n"
            f"> 🔮 **Linh Bụi Tiên Các:** `{player.linh_bui:,}`"
        )
        embed.add_field(name="💰 Tài Bảo & Tiền Tệ", value=currencies_text, inline=False)

        # 2. Gacha Tickets
        tickets_text = (
            f"> 🎟️ **Linh Duyên Phù (Banner Thường):** `{player.linh_duyen_phu}` vé\n"
            f"> 🌟 **Tiên Duyên Phù (Banner VIP):** `{player.tien_duyen_phu}` vé\n"
            f"> ☯️ **Tẩy Tủy Phù (Cải Mệnh):** `{player.tay_tuy_phu}` vé"
        )
        embed.add_field(name="🎟️ Vé Quay Gacha", value=tickets_text, inline=False)

        # 3. Protections & Rescue Consumables
        consumables_text = (
            f"> 💊 **Vạn Linh Đan (Cứu Thương):** `{player.van_linh_dan}` viên\n"
            f"> 🛡️ **Thánh Thể Phù (Bảo Hiểm Rớt Đồ):** `{player.thanh_the_phu}` lá\n"
            f"> ✨ **Cửu Chuyển Tái Tạo Đan (Hồi Sinh):** `{player.cuu_chuyen_dan}` viên"
        )
        embed.add_field(name="🛡️ Bùa Bảo Hiểm & Cứu Thương", value=consumables_text, inline=False)

        # 4. Inventory items from DB
        if inv_items:
            lines = [f"> 📦 **{item['item_name']}** ({item['item_type']}): x`{item['quantity']}`" for item in inv_items]
            chunks = []
            curr_chunk = []
            curr_len = 0
            for line in lines:
                if curr_len + len(line) + 1 > 950:
                    chunks.append("\n".join(curr_chunk))
                    curr_chunk = [line]
                    curr_len = len(line)
                else:
                    curr_chunk.append(line)
                    curr_len += len(line) + 1
            if curr_chunk:
                chunks.append("\n".join(curr_chunk))

            # Limit to at most 10 chunks (Discord max 25 fields total)
            for idx, chunk in enumerate(chunks[:10], 1):
                field_title = "🎒 Bảo Vật & Nguyên Liệu Khác" if len(chunks) == 1 else f"🎒 Bảo Vật & Nguyên Liệu ({idx}/{min(len(chunks), 10)})"
                embed.add_field(name=field_title, value=chunk, inline=False)
            if len(chunks) > 10:
                embed.add_field(name="⚠️ Lưu ý", value=f"> *Và còn {len(chunks) - 10} nhóm vật phẩm khác...*", inline=False)
        else:
            embed.add_field(name="🎒 Bảo Vật & Nguyên Liệu Khác", value="> _Chưa có thêm vật phẩm đặc biệt trong túi đồ._", inline=False)

        embed.set_footer(text="Gõ !tiencac để mua thêm bùa & vé quay | Gõ !profile để xem hồ sơ nhân vật")
        await ctx.send(embed=embed)

    @commands.command(
        name="tutien-top",
        aliases=["toptuvi", "bxh-tutien", "top-tutien", "toptutien", "toprank"],
        brief="Xem Bảng Xếp Hạng Top Tu Sĩ Server (Nút bấm chuyển tab thời gian thực).",
        usage="tutien-top"
    )
    async def top_cmd(self, ctx: commands.Context, category: str = "tu-vi"):
        """Xem Bảng Xếp Hạng Top Tu Sĩ Server với nút bấm chuyển tab (!tutien-top)."""
        cat_clean = category.lower()
        if cat_clean in ["gia-tai", "giatai", "tien", "giau"]:
            init_tab = "gia-tai"
        elif cat_clean in ["thap", "leothap"]:
            init_tab = "thap"
        elif cat_clean in ["boss", "dietboss"]:
            init_tab = "boss"
        else:
            init_tab = "tu-vi"

        view = TutienTopLeaderboardView(self.db, current_tab=init_tab, timeout=120.0)
        embed = view.build_embed()
        await ctx.send(embed=embed, view=view)

    @commands.command(
        name="khai-dao",
        aliases=["khaidao", "ngo-dao", "ngodao", "dao-domain"],
        brief="Khai ngộ hoặc hợp nhất Đạo Vực để thức tỉnh sức mạnh ẩn.",
        usage="khai-dao [đạo_1] [đạo_2]"
    )
    async def khai_dao_cmd(self, ctx: commands.Context, dao_1: str = None, dao_2: str = None):
        """
        Khai ngộ Đạo Vực cá nhân hoặc hợp nhất 2 Đạo thành Đạo Phức Hợp.
        - Dùng `!khai-dao` để xem các Đạo Vực có thể mở khóa & fusion matrix.
        - Dùng `!khai-dao <Đạo A> <Đạo B>` để hợp nhất 2 Đạo thành Đạo Phức Hợp.
        - Hợp nhất đơn: `!khai-dao <Đạo>` để khai ngộ và gán Đạo Vực cơ bản.
        """
        from app.discord_bot.modules.tutien.constants import DAO_FUSION_MATRIX
        from app.discord_bot.modules.tutien.engines.body_refining import fuse_dao_domains

        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        # Hiển thị thông tin Đạo Vực nếu không có args
        if not dao_1:
            embed = discord.Embed(
                title="☯ HỆ THỐNG ĐẠO VỰC — KHAI NGỘ THẦN THÔNG",
                description=f"**Đạo Vực Hiện Tại:** `{player.active_dao_domain or 'Chưa khai ngộ'}`\n\n"
                            f"Khai ngộ Đạo Vực đơn hoặc hợp nhất 2 Đạo để tạo **Đạo Phức Hợp** siêu việt!\n"
                            f"Cú pháp: `!khai-dao <Đạo>` hoặc `!khai-dao <Đạo A> <Đạo B>`",
                color=discord.Color.dark_purple()
            )
            embed.add_field(
                name="📋 Đạo Cơ Bản (Tự Khai Ngộ)",
                value="> `Kiếm Đạo` | `Hỏa Đạo` | `Tử Vong Đạo` | `Không Gian`\n> `Lôi Đạo` | `Sinh Mệnh Đạo` | `Thần Thức` | `Phong Đạo`",
                inline=False
            )
            embed.add_field(
                name="✨ Đạo Phức Hợp (Hợp Nhất 2 Đạo)",
                value="".join([
                    f"> `{k[0]}` + `{k[1]}` → **{v['name']}**\n> *{v['effect']}*\n\n"
                    for k, v in DAO_FUSION_MATRIX.items()
                ]),
                inline=False
            )
            embed.add_field(
                name="⚠️ Yêu Cầu",
                value="> Khai ngộ cơ bản: Cảnh giới **Trúc Cơ** trở lên (Realm ≥ 9)\n"
                      "> Hợp nhất Đạo Phức Hợp: Cảnh giới **Kim Đan** trở lên (Realm ≥ 13) + `200` Danh Vọng",
                inline=False
            )
            await ctx.send(embed=embed)
            return

        # Yêu cầu tối thiểu cảnh giới Trúc Cơ (realm_index >= 9)
        if player.realm_index < 9:
            await ctx.send(
                f"❌ **CẢNH GIỚI KHÔNG ĐỦ!** Cần đạt **Trúc Cơ Sơ Kỳ** (Realm 9) mới có thể khai ngộ Đạo Vực!\n"
                f"> Cảnh giới hiện tại: `{player.realm_name}` (Realm {player.realm_index})"
            )
            return

        # Fusion 2 Đạo thành Đạo Phức Hợp
        if dao_2:
            if player.realm_index < 13:
                await ctx.send(
                    f"❌ **CẢNH GIỚI KHÔNG ĐỦ!** Hợp nhất Đạo Vực cần đạt **Kim Đan Sơ Kỳ** (Realm 13)!\n"
                    f"> Cảnh giới hiện tại: `{player.realm_name}`"
                )
                return

            fusion_cost_dv = 200
            if player.danh_vong < fusion_cost_dv:
                await ctx.send(
                    f"❌ **THIẾU DANH VỌNG!** Hợp nhất Đạo Vực cần `{fusion_cost_dv}` Danh Vọng!\n"
                    f"> Danh Vọng hiện có: `{player.danh_vong}`"
                )
                return

            fused = fuse_dao_domains(dao_1, dao_2)
            if not fused:
                await ctx.send(
                    f"❌ **HỢP NHẤT THẤT BẠI!** Không tìm thấy Đạo Phức Hợp từ `{dao_1}` + `{dao_2}`!\n"
                    f"> Gõ `!khai-dao` để xem Fusion Matrix hợp lệ."
                )
                return

            player.danh_vong -= fusion_cost_dv
            player.active_dao_domain = fused["name"]
            self.db.update_player(player)

            embed = discord.Embed(
                title=f"✨ ĐẠO VỰC HỢP NHẤT — {fused['name']}",
                description=f"Tu sĩ **{player.dao_hieu}** đã khai ngộ thành công Đạo Phức Hợp tối thượng!\n"
                            f"`{dao_1}` + `{dao_2}` ⟶ **{fused['name']}**",
                color=discord.Color.gold()
            )
            embed.add_field(name="⚡ Hiệu Ứng Đạo Vực", value=f"> {fused['effect']}", inline=False)
            embed.add_field(name="💎 Chi Phí", value=f"> `-{fusion_cost_dv}` Danh Vọng", inline=True)
            embed.add_field(name="☯ Đạo Vực Kích Hoạt", value=f"> **{player.active_dao_domain}**", inline=True)
            await ctx.send(embed=embed)

        else:
            # Khai ngộ Đạo đơn (cơ bản)
            basic_domains = [
                "Kiếm Đạo", "Hỏa Đạo", "Tử Vong Đạo", "Không Gian",
                "Lôi Đạo", "Sinh Mệnh Đạo", "Thần Thức", "Phong Đạo"
            ]
            # Kiểm tra match (không phân biệt hoa thường)
            matched_domain = next((d for d in basic_domains if dao_1.lower() in d.lower() or d.lower() in dao_1.lower()), None)
            if not matched_domain:
                await ctx.send(
                    f"❌ **ĐẠO VỰC KHÔNG HỢP LỆ!** `{dao_1}` không phải Đạo Vực cơ bản.\n"
                    f"> Gõ `!khai-dao` để xem danh sách Đạo hợp lệ."
                )
                return

            old_domain = player.active_dao_domain
            player.active_dao_domain = matched_domain
            self.db.update_player(player)

            embed = discord.Embed(
                title=f"☯ KHAI NGỘ ĐẠO VỰC — {matched_domain}",
                description=f"Tu sĩ **{player.dao_hieu}** đã khai ngộ **{matched_domain}**!\n"
                            f"Đạo Vực sẽ ảnh hưởng trực tiếp đến chiến đấu PVP và Đột Phá!",
                color=discord.Color.purple()
            )
            if old_domain:
                embed.add_field(name="🔄 Thay Thế", value=f"> `{old_domain}` → **{matched_domain}**", inline=False)
            embed.add_field(
                name="💡 Nâng Cấp",
                value=f"> Dùng `!khai-dao {matched_domain} <Đạo khác>` để hợp nhất thành Đạo Phức Hợp khi đạt **Kim Đan**!",
                inline=False
            )
            await ctx.send(embed=embed)

    # --- 📂 NHÓM LỆNH [/dao-vu] (DAILY QUESTS) ---

    @commands.command(
        name="dao-vu",
        aliases=["nhiem-vu", "nhiemvu", "daovu", "quest", "dailyquest", "nv"],
        brief="Xem danh sách Đạo Vụ Hàng Ngày (Nhiệm vụ nhận Linh Thạch, Tiên Ngọc, Vé quay).",
        usage="dao-vu"
    )
    async def daovu_cmd(self, ctx: commands.Context):
        """Xem danh sách Đạo Vụ Hàng Ngày với giao diện nút bấm nhận thưởng tức thì (!dao-vu)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        quests = self.db.get_or_generate_daily_quests(ctx.author.id, player.realm_index)
        view = DailyQuestView(self.db, ctx.author.id, player.realm_index, timeout=120.0)
        embed = view.build_embed(player.dao_hieu, quests)
        await ctx.send(embed=embed, view=view)

    @commands.command(
        name="nhan-dao-vu",
        aliases=["nhandaovu", "nhannv", "claim-quest", "claimquest", "nhan-nv"],
        brief="Nhận thưởng Đạo Vụ Hàng Ngày đã hoàn thành.",
        usage="nhan-dao-vu [tất_cả | tu_luyen | pve_kills | pvp_wins]"
    )
    async def nhan_daovu_cmd(self, ctx: commands.Context, target: str = "tat_ca"):
        """Nhận phần thưởng Đạo Vụ đã hoàn thành."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        quests = self.db.get_or_generate_daily_quests(ctx.author.id, player.realm_index)
        target_lower = target.lower()

        claimed_rewards = []
        if target_lower in ["tat_ca", "all", "tatca", "het"]:
            for q in quests:
                if not q["is_claimed"] and q["current_count"] >= q["target_count"]:
                    claimed = self.db.claim_quest_reward(ctx.author.id, q["quest_type"])
                    if claimed:
                        unit = "Linh Thạch" if claimed["reward_type"] == "linh_thach" else ("Tiên Ngọc" if claimed["reward_type"] == "tien_ngoc" else "Linh Duyên Phù")
                        claimed_rewards.append(f"• **{claimed['quest_name']}**: `+{claimed['reward_amount']}` {unit}")
        else:
            # Match specific quest type
            match_type = None
            if "tu" in target_lower or "luyen" in target_lower:
                match_type = "tu_luyen"
            elif "pve" in target_lower or "yeu" in target_lower or "quai" in target_lower or "thap" in target_lower:
                match_type = "pve_kills"
            elif "pvp" in target_lower or "tranh" in target_lower or "dau" in target_lower:
                match_type = "pvp_wins"

            if match_type:
                claimed = self.db.claim_quest_reward(ctx.author.id, match_type)
                if claimed:
                    unit = "Linh Thạch" if claimed["reward_type"] == "linh_thach" else ("Tiên Ngọc" if claimed["reward_type"] == "tien_ngoc" else "Linh Duyên Phù")
                    claimed_rewards.append(f"• **{claimed['quest_name']}**: `+{claimed['reward_amount']}` {unit}")
                else:
                    await ctx.send("❌ Nhiệm vụ này chưa hoàn thành hoặc bạn đã nhận thưởng rồi!")
                    return
            else:
                await ctx.send("❌ Không nhận diện được loại nhiệm vụ! Dùng `!nhan-dao-vu all` để nhận tất cả.")
                return

        if not claimed_rewards:
            await ctx.send("⚠️ Bạn chưa có Đạo Vụ nào hoàn thành để nhận thưởng! Hãy gõ `!dao-vu` để xem tiến độ.")
            return

        embed = discord.Embed(
            title="🎁 NHẬN THƯỞNG ĐẠO VỤ THÀNH CÔNG! 🎁",
            description=f"Chúc mừng tu sĩ **[{player.dao_hieu}]** đã hoàn thành Đạo Vụ Thiên Đình!\n\n" + "\n".join(claimed_rewards),
            color=discord.Color.gold()
        )
        embed.set_footer(text="Đạo Vụ làm mới mỗi ngày vào 00:00 UTC!")
        await ctx.send(embed=embed)


class DailyQuestView(discord.ui.View):
    """Interactive Discord View for Daily Quests (!dao-vu)."""
    def __init__(self, db, user_id: int, realm_index: int, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.db = db
        self.user_id = user_id
        self.realm_index = realm_index

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải sổ Đạo Vụ của bạn!", ephemeral=True)
            return False
        return True

    def build_embed(self, dao_hieu: str, quests: list) -> discord.Embed:
        from datetime import datetime
        today_str = datetime.utcnow().strftime("%d/%m/%Y")

        embed = discord.Embed(
            title="📜 THIÊN ĐÌNH ĐẠO VỤ — NHIỆM VỤ HÀNG NGÀY",
            description=f"Tu sĩ **[{dao_hieu}]** | Ngày: `{today_str} (UTC)`\n"
                        f"*Hoàn thành Đạo Vụ mỗi ngày để nhận Linh Thạch, Tiên Ngọc & Vé Quay F2P!*\n",
            color=discord.Color.teal()
        )

        all_completed = True
        has_claimable = False

        for q in quests:
            curr = q["current_count"]
            target = q["target_count"]
            pct = min(100, int((curr / target) * 100)) if target > 0 else 100

            # Progress bar
            filled = int(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)

            # Unit name
            unit = "Linh Thạch" if q["reward_type"] == "linh_thach" else ("Tiên Ngọc 🌟" if q["reward_type"] == "tien_ngoc" else "Linh Duyên Phù 🎟️")

            if q["is_claimed"]:
                status_str = "✅ **ĐÃ NHẬN THƯỞNG**"
            elif curr >= target:
                status_str = "✨ **HOÀN THÀNH — CÓ THỂ NHẬN!**"
                has_claimable = True
                all_completed = False
            else:
                status_str = f"⏳ **ĐANG THỰC HIỆN** (`{pct}%`)"
                all_completed = False

            field_val = (
                f"> Tiến độ: `[{bar}]` **{curr}/{target}**\n"
                f"> Phần thưởng: `+{q['reward_amount']}` {unit}\n"
                f"> Trạng thái: {status_str}"
            )
            embed.add_field(name=f"📌 {q['quest_name']}", value=field_val, inline=False)

        if all_completed and len(quests) > 0:
            embed.set_footer(text="🎉 Bạn đã hoàn thành xuất sắc tất cả Đạo Vụ hôm nay! Hãy quay lại vào ngày mai.")
        elif has_claimable:
            embed.set_footer(text="💡 Bấm nút '🎁 Nhận Tất Cả Thưởng' bên dưới để thu nhận tài bảo!")
        else:
            embed.set_footer(text="Gõ !tuluyen, !sanquai, !thap, !pvp để tăng tiến độ Đạo Vụ!")

        return embed

    @discord.ui.button(label="🎁 Nhận Tất Cả Thưởng", style=discord.ButtonStyle.success, custom_id="btn_claim_all_quests")
    async def claim_all(self, interaction: discord.Interaction, button: discord.ui.Button):
        quests = self.db.get_or_generate_daily_quests(self.user_id, self.realm_index)
        claimed_rewards = []

        for q in quests:
            if not q["is_claimed"] and q["current_count"] >= q["target_count"]:
                claimed = self.db.claim_quest_reward(self.user_id, q["quest_type"])
                if claimed:
                    unit = "Linh Thạch" if claimed["reward_type"] == "linh_thach" else ("Tiên Ngọc" if claimed["reward_type"] == "tien_ngoc" else "Linh Duyên Phù")
                    claimed_rewards.append(f"• **{claimed['quest_name']}**: `+{claimed['reward_amount']}` {unit}")

        if not claimed_rewards:
            await interaction.response.send_message("❌ Chưa có Đạo Vụ nào hoàn thành để nhận thưởng!", ephemeral=True)
            return

        # Refresh embed
        player = self.db.get_player(self.user_id)
        updated_quests = self.db.get_or_generate_daily_quests(self.user_id, self.realm_index)
        new_embed = self.build_embed(player.dao_hieu, updated_quests)

        reward_msg = "🎁 **ĐÃ NHẬN THƯỞNG ĐẠO VỤ!**\n" + "\n".join(claimed_rewards)
        await interaction.response.edit_message(embed=new_embed, view=self)
        await interaction.followup.send(reward_msg, ephemeral=True)

    @discord.ui.button(label="🔄 Làm Mới Tiến Độ", style=discord.ButtonStyle.secondary, custom_id="btn_refresh_quests")
    async def refresh_view(self, interaction: discord.Interaction, button: discord.ui.Button):
        player = self.db.get_player(self.user_id)
        quests = self.db.get_or_generate_daily_quests(self.user_id, self.realm_index)
        new_embed = self.build_embed(player.dao_hieu, quests)
        await interaction.response.edit_message(embed=new_embed, view=self)


