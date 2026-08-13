"""
Comprehensive Prefix Commands Cog for Tu Tien System: «ĐẠI ĐẠO TRANH PHONG»
Includes Monetization Commands, VIP Progression, Gacha 3 Banners with open_chest.gif animation & Server Flex.
"""

import asyncio
import io
import os
import random
import time
import discord
from discord.ext import commands, tasks

from app.discord_bot.modules.tutien.db import TuTienDB
from app.discord_bot.modules.tutien.models import CultivatorProfile
from app.discord_bot.modules.tutien.constants import (
    REALMS, REALM_REQUIRED_EXP, REALM_REQUIRED_TAM_CANH, SPIRITUAL_ROOT_QUALITY_BUFF, ELEMENTS_NGU_HANH, ELEMENTS_DI_LINH_CAN,
    TIEN_CAC_SHOP, VIP_LEVELS, GACHA_BANNERS, LINH_BUI_SHOP
)
from app.discord_bot.modules.tutien.engines.cultivation import (
    roll_spiritual_root, process_active_cultivation
)
from app.discord_bot.modules.tutien.engines.tribulation import (
    calculate_breakthrough_chance, calculate_tribulation_damage, calculate_kim_dan_quality, HEART_DEMON_QUESTIONS
)
from app.discord_bot.modules.tutien.engines.body_refining import upgrade_body_refining, fuse_dao_domains
from app.discord_bot.modules.tutien.engines.crafting import craft_alchemy_pill
from app.discord_bot.modules.tutien.engines.monetization import (
    grant_topup_and_vip_exp, buy_tiencac_item, is_array_protected
)
from app.discord_bot.modules.tutien.engines.gacha import process_gacha_rolls
from app.discord_bot.modules.tutien.engines.pve import (
    generate_pve_monster, process_turn_action, process_quick_sweep_10x, check_elemental_advantage, calculate_player_pve_atk,
    generate_mirror_phantom_boss, generate_roguelike_dungeon_matrix, process_hardcore_defeat
)
from app.discord_bot.modules.tutien.renderers.profile_renderer import render_tutien_profile_card
from app.discord_bot.modules.tutien.ui.tribulation_ui import TribulationWaveView, HeartDemonQuizView
from app.discord_bot.modules.tutien.ui.pve_ui import (
    PveBattleView, PartyLobbyView, RevivePromptView, QteOneShotView, TrapSacrificeView, DungeonMerchantView
)

GIF_CHEST_PATH = "pictures/open_chest.gif"


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
        self.world_boss_max_hp = 10000000
        self.world_boss_hp = 10000000
        self.world_boss_name = "👹 Ma Vương Cổ Đại — Vô Cực Thi Cụ"
        self.active_party_rooms = {}  # {channel_id: PartyLobbyView}
        self.bg_recovery_task.start()
        self.bg_retention_guard.start()

    def cog_unload(self):
        self.bg_recovery_task.cancel()
        self.bg_retention_guard.cancel()

    async def cog_command_error(self, ctx: commands.Context, error: Exception):
        if isinstance(error, commands.MissingRequiredArgument):
            await ctx.send(f"❌ Thiếu tham số bắt buộc! Cú pháp đúng: `{ctx.prefix}{ctx.command.signature}`")
        elif isinstance(error, commands.BadArgument):
            await ctx.send("❌ Tham số nhập vào không hợp lệ!")
        elif isinstance(error, commands.NotOwner):
            await ctx.send("❌ Lệnh này chỉ dành cho Chủ Bot!")

    # --- BACKGROUND TASKS ---
    @tasks.loop(minutes=5)
    async def bg_recovery_task(self):
        """Phục hồi Tinh Lực (+5/5p = +60/h) & Linh Khí Kênh (+416/5p = +5000/h) định kỳ."""
        await self.bot.wait_until_ready()
        try:
            self.db.recover_all_players_tinh_luc(5)
            self.db.recover_all_channels_linh_khi(416)
        except Exception as e:
            print(f"[TuTien] Error in recovery task: {e}")

    @tasks.loop(minutes=5)
    async def bg_retention_guard(self):
        """Check AFK meditation completion & retention guard (ảo giác Tâm Ma) cho tu sĩ bế quan."""
        await self.bot.wait_until_ready()
        try:
            now = time.time()
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, meditate_start_time, meditate_duration_hours, is_vip_pass, realm_index FROM tutien_players WHERE is_meditating = 1")
                meditating_players = cursor.fetchall()

                for row in meditating_players:
                    u_id = row["user_id"]
                    start_t = row["meditate_start_time"]
                    duration_h = row["meditate_duration_hours"] or 1
                    is_vip_pass = row["is_vip_pass"]
                    realm_idx = row["realm_index"]

                    # 1. Kiểm tra hoàn thành bế quan AFK khi đủ thời gian
                    if start_t and (now - start_t >= duration_h * 3600):
                        exp_gain = int(5000 * duration_h * (1 + realm_idx * 0.1))
                        linh_thach_gain = int(500 * duration_h)
                        tam_canh_gain = min(100.0, duration_h * 2.0)

                        conn.execute(
                            "UPDATE tutien_players SET is_meditating = 0, meditate_start_time = NULL, meditate_duration_hours = 0, "
                            "exp = exp + ?, linh_thach = linh_thach + ?, tam_canh = MIN(100.0, tam_canh + ?) WHERE user_id = ?",
                            (exp_gain, linh_thach_gain, tam_canh_gain, u_id)
                        )
                        user = self.bot.get_user(u_id)
                        if user:
                            try:
                                await user.send(
                                    f"🎉 **VIÊN MÃN XUẤT QUAN!** Bạn đã hoàn tất **{duration_h} Giờ** bế quan nhập định!\n"
                                    f"🎁 Phần thưởng AFK: `+{exp_gain:,}` Tu Vi | `+{linh_thach_gain:,}` Linh Thạch | `+{tam_canh_gain:.1f}%` Tâm Cảnh!"
                                )
                            except Exception:
                                pass
                        continue

                    # 2. Tu sĩ đang bế quan được thưởng thêm +5 Tinh Lực mỗi 5 phút
                    conn.execute(
                        "UPDATE tutien_players SET tinh_luc = CASE WHEN (tinh_luc + 5) > max_tinh_luc THEN max_tinh_luc ELSE (tinh_luc + 5) END WHERE user_id = ?",
                        (u_id,)
                    )

                    if is_vip_pass:
                        conn.execute("UPDATE tutien_players SET dao_tam = dao_tam + 5 WHERE user_id = ?", (u_id,))
                        continue

                    last_notice = self.last_tam_ma_notice.get(u_id, 0)
                    # Giới hạn thông báo: Ít nhất 1 tiếng mới gửi 1 lần (nếu dính tỉ lệ 15%)
                    if start_t and (now - start_t > 900) and (now - last_notice > 3600) and random.random() < 0.15:
                        user = self.bot.get_user(u_id)
                        if user:
                            try:
                                await user.send("⚠️ **Tâm trí bạn xuất hiện ảo giác Tâm Ma khi bế quan!** Hãy gõ `!tuluyen` để định tâm duy trì nhập định!")
                                self.last_tam_ma_notice[u_id] = now
                            except Exception:
                                pass
        except Exception as e:
            print(f"[TuTien] Retention guard error: {e}")

    # --- 🔮 GACHA 3 BANNERS COMMANDS ---

    @commands.command(
        name="quay-gacha",
        aliases=["gacha", "quaygacha"],
        brief="Quay Gacha 3 Đại Banners để nhận bảo vật & linh dược.",
        usage="quay-gacha [tiencac|caimenh|bg] [1x|10x]"
    )
    async def quay_gacha_cmd(self, ctx: commands.Context, banner: str = "tiencac", rolls: str = "1x"):
        """Quay Gacha Ba Đại Banners (Dùng open_chest.gif animation & Server Flex khi ra Đế Cấp)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        roll_count = 10 if "10" in rolls else 1
        banner_key = banner.lower()

        success, title_msg, roll_results, updated_player = process_gacha_rolls(self.db, player, banner_key, roll_count)
        if not success:
            await ctx.send(title_msg)
            return

        # Send animation GIF if file exists
        if os.path.exists(GIF_CHEST_PATH):
            file_gif = discord.File(fp=GIF_CHEST_PATH, filename="open_chest.gif")
            anim_msg = await ctx.send("🔮 **Đang vận chuyển Đạo Luật... Linh khí hội tụ!**", file=file_gif)
            await asyncio.sleep(2.0)
            try:
                await anim_msg.delete()
            except Exception:
                pass

        # Format Result Embed
        embed = discord.Embed(
            title=f"✨ KẾT QUẢ QUAY GACHA — {GACHA_BANNERS.get(banner_key, {}).get('name', 'Banner')}",
            description=f"Tu sĩ **[{updated_player.dao_hieu}]** vừa mở rương thần cực! (Lượt Pity: `{updated_player.soft_pity_count}/80`)",
            color=discord.Color.gold()
        )

        has_ur = False
        ur_items = []
        for idx, res in enumerate(roll_results, 1):
            val_str = f"> Phẩm cấp: `{res['grade']}`"
            if res.get("duplicate_converted"):
                val_str += f" *(Trùng! Chuyển thành +{res['duplicate_converted']} Linh Bụi)*"

            embed.add_field(name=f"[{idx}] {res['item_name']}", value=val_str, inline=False)
            if res.get("is_ur"):
                has_ur = True
                ur_items.append(res["item_name"])

        embed.set_footer(text="Gõ !wishlist để chọn vật phẩm bảo hiểm hoặc !linhbui-shop để đổi đồ!")
        await ctx.send(embed=embed)

        # Server-wide Flex Notification if UR pulled
        if has_ur:
            flex_msg = f"💥 **[THIÊN ĐẠO DIỆU BIẾN]**: Tu sĩ **{ctx.author.mention}** vừa gặp đại cơ duyên tại Tiên Các rút thành công **{', '.join(ur_items)}**! Toàn thể tu sĩ bái phục!"
            await ctx.send(flex_msg)

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
        if success:
            self.db.update_player(updated_player)
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

        embed = discord.Embed(
            title="☯ THIÊN ĐẠO CHỨNG GIÁM: NHẬP MÔN THÀNH CÔNG! ☯",
            description=f"Chúc mừng Đạo hữu **[{dao_hieu}]** đã bước chân vào con đường trường sinh!",
            color=discord.Color.gold()
        )
        embed.add_field(name="⚡ Phẩm Cấp Linh Căn", value=f"**{quality}**", inline=True)
        embed.add_field(name="🔮 Thuộc Tính", value=f"**{element}**", inline=True)
        embed.add_field(name="💰 Tài Bảo Nhập Môn", value="`500` Linh Thạch | `100` Tinh Lực", inline=False)
        embed.set_footer(text="Gõ !tutien-profile để xem hồ sơ PNG hoặc gõ !huongdan để xem cẩm nang tân thủ!")
        await ctx.send(embed=embed)

    @commands.command(
        name="tutien-huongdan",
        aliases=["huongdan", "tutienhelp", "tuhds"],
        brief="Xem Cẩm Nang Hướng Dẫn Tân Thủ Tu Tiên 6 bước.",
        usage="tutien-huongdan"
    )
    async def huongdan_cmd(self, ctx: commands.Context):
        """Cẩm Nang Hướng Dẫn Tân Thủ Tu Tiên: «ĐẠI ĐẠO TRANH PHONG»."""
        embed = discord.Embed(
            title="📜 CẨM NANG HƯỚNG DẪN TÂN THỦ TU TIÊN 📜",
            description="Chào mừng đến với thế giới **«ĐẠI ĐẠO TRANH PHONG»**! Dưới đây là quy trình 6 bước nhập môn dành cho Tân Thủ:",
            color=discord.Color.gold()
        )
        embed.add_field(
            name="1️⃣ Bước 1: Nhập Môn & Khởi Tạo Linh Căn",
            value="> Gõ `!nhapmon [Đạo Hiệu]` để bước vào giới tu tiên, quay Linh Căn ngẫu nhiên (từ Phàm Phẩm 45% đến Hỗn Độn 0.01%) & nhận 500 Linh Thạch tân thủ.",
            inline=False
        )
        embed.add_field(
            name="2️⃣ Bước 2: Kiểm Tra 18 Thuộc Tính",
            value="> Gõ `!profile` xem Thẻ Hình Ảnh PNG thuộc tính. Gõ `!tamcanh` để kiểm tra tỷ lệ độ kiếp & độ vững chắc của Căn Cơ.",
            inline=False
        )
        embed.add_field(
            name="3️⃣ Bước 3: Tích Lũy Tu Vi & Tinh Lực",
            value="> Gõ `!tuluyen` (tốn 15 Tinh lực/lần, hồi 10 Tinh lực/h) để tích lũy tu vi. Gõ `!nhapdinh [1h|4h|8h]` để bế quan AFK khi không online.",
            inline=False
        )
        embed.add_field(
            name="4️⃣ Bước 4: Luyện Thể & Lĩnh Ngộ Công Pháp",
            value="> Gõ `!luyenthe` rèn luyện thân thể (Tôi Thể -> Bất Diệt Thể). Gõ `!trangbi [Tên_Công_Pháp]` chọn lối tu (Chính Đạo / Ma Đạo). Gõ `!ngodao` để ghép Đạo Vực.",
            inline=False
        )
        embed.add_field(
            name="5️⃣ Bước 5: Xung Kích Bình Cảnh & Độ Kiếp",
            value="> Khi Tu Vi đạt 100%, gõ `!dotpha` để nghênh đón Lôi Kiếp thời gian thực (10s/đợt chọn nút Đỡ Pháp Bảo / Đan Dược / Nghênh Đón) & vượt Thử Thách Tâm Ma.",
            inline=False
        )
        embed.add_field(
            name="6️⃣ Bước 6: Chinh Phục PVE (Săn Yêu, Leo Tháp, Bí Cảnh, Boss)",
            value="> Gõ `!san-yeu` đánh quái lượt (VIP 2+ `!san-yeu quet` 10x). Gõ `!leo-thap` leo 100 Tầng Tháp. Gõ `!bi-canh` lập đội 3-5 người. Gõ `!diet-boss` đánh Boss Server.",
            inline=False
        )
        embed.add_field(
            name="7️⃣ Bước 7: Shop Tiên Các & Gacha",
            value="> Gõ `!tiencac` xem shop bảo hiểm độ kiếp, bùa chống cướp, Thẻ VIP. Gõ `!gacha` quay bảo vật Tiên Cấp (có bảo hiểm Pity 80 lượt).",
            inline=False
        )
        embed.set_footer(text="Gõ !tutien-profile để xem hồ sơ nhân vật | Gõ !san-yeu để chiến đấu PVE!")
        await ctx.send(embed=embed)

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

        img_buf = render_tutien_profile_card(player, avatar_bytes)
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
        player.can_co = 90.0
        player.tam_canh = 80.0
        self.db.update_player(player)

        await ctx.send(f"💥 **PHẾ VỊ THÀNH CÔNG!** Tu sĩ **{player.dao_hieu}** đã tự phế tu vi, quay về Luyện Khí Tầng 1 để đúc lại Căn Cơ!")

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

        gongfa = self.db.get_gongfa(ctx.author.id)
        channel_id = ctx.channel.id
        channel_linh_khi = self.db.get_channel_linh_khi(channel_id)

        res, updated_player = process_active_cultivation(player, gongfa, channel_linh_khi)
        if not res["success"]:
            await ctx.send(f"❌ {res['reason']}")
            return

        self.db.consume_channel_linh_khi(channel_id, 50)
        self.db.update_player(updated_player)

        msg = f"🧘 **[{player.dao_hieu}]** tiến hành bế quan vận công...\n> {res['message']}\n"
        msg += f"📊 **Tu Vi:** `{updated_player.exp:,}` / `{res['required_exp']:,}` | 🔥 **Tinh Lực còn:** `{updated_player.tinh_luc}/100`"
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
        """Bế quan AFK tích lũy tài nguyên (1h, 4h, 8h)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        if hours not in [1, 4, 8, 12, 16, 24]:
            await ctx.send("❌ Thời gian bế quan hợp lệ chỉ gồm: `1`h, `4`h, `8`h, `12`h, `16`h hoặc `24`h.")
            return

        player.is_meditating = True
        player.meditate_start_time = time.time()
        player.meditate_duration_hours = hours
        self.db.update_player(player)

        await ctx.send(f"🧘 Tu sĩ **{player.dao_hieu}** đã bắt đầu nhập định bế quan trong **{hours} Giờ**! Hệ thống sẽ tự động bảo vệ nếu sở hữu Thẻ Tháng VIP.")

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
        actual_hours = max(0.05, min(elapsed_hours, float(player.meditate_duration_hours or 1)))

        exp_gain = int(5000 * actual_hours * (1 + player.realm_index * 0.1))
        linh_thach_gain = int(500 * actual_hours)
        tam_canh_gain = round(actual_hours * 2.0, 1)

        req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
        player.exp = min(req_exp, player.exp + exp_gain)
        player.linh_thach += linh_thach_gain
        player.tam_canh = min(100.0, player.tam_canh + tam_canh_gain)
        player.is_meditating = False
        player.meditate_start_time = None
        player.meditate_duration_hours = 0

        self.db.update_player(player)

        embed = discord.Embed(
            title=f"🧘 XUẤT QUAN THÀNH CÔNG — {player.dao_hieu}",
            description=f"Tu sĩ **{player.dao_hieu}** đã thu công xuất quan sau **{actual_hours:.1f} Giờ** nhập định!",
            color=discord.Color.green()
        )
        embed.add_field(
            name="🎁 Phần Thưởng Tích Lũy",
            value=f"> ✨ Tu Vi: `+{exp_gain:,}`\n> 💰 Linh Thạch: `+{linh_thach_gain:,}`\n> 🧘 Tâm Cảnh: `+{tam_canh_gain}%`",
            inline=False
        )
        await ctx.send(embed=embed)

    @commands.command(
        name="luyen-the",
        aliases=["luyenthe"],
        brief="Rèn luyện Thân Thể tiêu hao Linh Thạch để đột phá Tôi Thể.",
        usage="luyen-the"
    )
    async def luyenthe_cmd(self, ctx: commands.Context):
        """Rèn luyện Thân Thể tiêu hao Linh Thạch để đột phá Tôi Thể."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        cost = 500 * (player.body_realm_index + 1)
        success, msg, updated_player = upgrade_body_refining(player, cost)
        if success:
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

        req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
        if player.exp < req_exp:
            await ctx.send(f"❌ Tu vi chưa đạt 100%! Hiện tại: `{player.exp:,}` / `{req_exp:,}`.")
            return

        chance = calculate_breakthrough_chance(player)
        if chance <= 0:
            await ctx.send("❌ **TÂM CẢNH KHÔNG ĐỦ!** Tỷ lệ đột phá thành công của bạn hiện là `0%`! Hãy thiền định tăng Tâm Cảnh!")
            return

        total_waves = 3 + (player.realm_index // 3)
        current_hp = player.hp

        embed = discord.Embed(
            title="⚡⚡⚡ THIÊN KIẾP GIÁNG LÂM ⚡⚡⚡",
            description=f"Tu sĩ **[{player.dao_hieu}]** bắt đầu xung kích bình cảnh đột phá lên **[{REALMS[min(player.realm_index + 1, len(REALMS) - 1)]}]**!\n"
                        f"📊 Tỷ lệ thành công cơ bản: **{chance:.1f}%** | Mật độ: **{total_waves} Đạo Lôi Kiếp**",
            color=discord.Color.dark_red()
        )
        msg_obj = await ctx.send(embed=embed)

        failed = False
        for wave in range(1, total_waves + 1):
            dmg = calculate_tribulation_damage(player, wave)

            if player.user_id in self.ho_phap_registry:
                dmg = int(dmg * 0.7)

            wave_embed = discord.Embed(
                title=f"⚡ LÔI KIẾP ĐỢT [{wave}/{total_waves}] GIỘI XU XUỐNG!",
                description=f"💥 Sát thương dự kiến: `{dmg:,}` Lôi Thuộc Tính.\n⏱️ Bạn có **10 Giây** để chọn phương án phòng thủ!",
                color=discord.Color.gold()
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

        if failed or random.uniform(0, 100) > chance:
            has_insurance = self.db.consume_item(player.user_id, "Thần Phù Bảo Mệnh", 1)
            if has_insurance:
                fail_embed = discord.Embed(
                    title="🛡️ KÍCH HOẠT THẦN PHÙ BẢO MỆNH!",
                    description=f"Độ kiếp thất bại nhưng **Thần Phù Bảo Mệnh** đã kích hoạt! Tu sĩ **{player.dao_hieu}** giữ nguyên 100% Tu Vi và Căn Cơ!",
                    color=discord.Color.gold()
                )
            else:
                player.exp = int(player.exp * 0.7)
                player.can_co = max(0.0, player.can_co - 20.0)
                self.db.update_player(player)
                fail_embed = discord.Embed(
                    title="💀 ĐỘ KIẾP THẤT BẠI!",
                    description=f"Thiên lôi oanh kích tan tành! Tu sĩ **{player.dao_hieu}** bị rớt tu vi và tổn hại `-20%` Căn Cơ!\n"
                                f"🔥 *Gói Phục Hồi Thánh Đan đang giảm giá 70% trong Shop !tiencac!*",
                    color=discord.Color.red()
                )
            await msg_obj.edit(embed=fail_embed, view=None)
        else:
            player.realm_index = min(len(REALMS) - 1, player.realm_index + 1)
            player.realm_name = REALMS[player.realm_index]
            player.exp = 0
            player.can_co = min(100.0, player.can_co + 5.0)
            self.db.update_player(player)
            win_embed = discord.Embed(
                title="🎉 ĐỘ KIẾP THÀNH CÔNG!",
                description=f"Chúc mừng Tu sĩ **[{player.dao_hieu}]** đã vượt qua Thiên Kiếp, chính thức tiến cấp lên **[{player.realm_name}]**!",
                color=discord.Color.green()
            )
            await msg_obj.edit(embed=win_embed, view=None)

    # --- 📂 NHÓM LỆNH [/tu-si-tuong-tac] ---

    @commands.command(
        name="cuop",
        aliases=["cuop-dong-phu"],
        brief="Đột nhập Động Phủ tu sĩ khác để cướp Linh Thạch.",
        usage="cuop @user"
    )
    async def cuop_cmd(self, ctx: commands.Context, target: discord.Member):
        """Đột nhập Động Phủ cướp Linh Thạch (Bị chặn 100% nếu mục tiêu bật Bùa Phòng Thủ)."""
        attacker = self.db.get_player(ctx.author.id)
        victim = self.db.get_player(target.id)

        if not attacker or not victim:
            await ctx.send("❌ Cả 2 tu sĩ đều phải nhập môn Tu Tiên!")
            return

        now = time.time()
        last_c = self.last_cuop_time.get(attacker.user_id, 0)
        cd_seconds = 43200  # 12 Giờ
        if now - last_c < cd_seconds:
            remain_sec = int(cd_seconds - (now - last_c))
            remain_h = remain_sec // 3600
            remain_m = (remain_sec % 3600) // 60
            time_str = f"{remain_h} giờ {remain_m} phút" if remain_h > 0 else f"{remain_m} phút"
            await ctx.send(f"⏱️ Bạn vừa đột nhập cướp động phủ gần đây! Hãy tĩnh dưỡng `{time_str}` nữa rồi tiếp tục.")
            return

        if is_array_protected(victim):
            await ctx.send(f"🛡️ **TRẬN PHÁP BẤT XÂM PHẠM!** Động Phủ của **{victim.dao_hieu}** đang được bảo vệ bởi Bùa Tiên Các, cướp phá thất bại!")
            return

        if victim.linh_thach < 100:
            await ctx.send(f"❌ Động phủ của **{victim.dao_hieu}** nghèo xơ xác, không có gì để cướp!")
            return

        self.last_cuop_time[attacker.user_id] = now

        if random.random() < 0.50:
            stolen = int(victim.linh_thach * 0.20)
            victim.linh_thach -= stolen
            attacker.linh_thach += stolen
            attacker.nghiep_luc += 10
            self.db.update_player(attacker)
            self.db.update_player(victim)
            await ctx.send(f"🗡️ **CƯỚP ĐỘNG PHỦ THÀNH CÔNG!** **{attacker.dao_hieu}** cướp được `{stolen:,}` Linh Thạch từ **{victim.dao_hieu}** (+10 Nghiệp Lực)!")
        else:
            attacker.hp = max(1, attacker.hp - 300)
            self.db.update_player(attacker)
            await ctx.send(f"🛡️ **CƯỚP THẤT BẠI!** Trận pháp Động Phủ của **{victim.dao_hieu}** phản phệ, **{attacker.dao_hieu}** bị thương `-300` HP!")

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

                req_exp = REALM_REQUIRED_EXP.get(player.realm_index, 1000000000)
                player.exp = min(req_exp, player.exp + exp_gain)
                player.linh_thach += lt_gain
                player.linh_duyen_phu += ticket_drop
                self.db.update_player(player)

                win_embed = discord.Embed(
                    title="🎉 TRẢM YÊU THÀNH CÔNG!",
                    description=f"Tu sĩ **{player.dao_hieu}** đã kết liễu **{monster['name']}**!\n"
                                f"🎁 Phần thưởng: `+{exp_gain:,}` EXP | `+{lt_gain:,}` Linh Thạch"
                                + (f" | `+1` Linh Duyên Phù 🎟️" if ticket_drop else ""),
                    color=discord.Color.green()
                )
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
                await ctx.send(embed=fail_embed)
                return

            await asyncio.sleep(1.0)

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

        log, monster = process_turn_action(player, monster, "GONGFA")
        if monster["current_hp"] <= 0:
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
                title=f"🎉 VƯỢT THÁP THÀNH CÔNG TẦNG {floor}!",
                description=f"Chúc mừng tu sĩ **{player.dao_hieu}** đã vượt qua Tầng {floor}, mở khóa **Tầng {new_floor}**!{bonus_str}",
                color=discord.Color.gold()
            )
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
                description=f"Trưởng đội: **{player.dao_hieu}**\nBấm nút bên dưới để chọn vai trò gia nhập đội!",
                color=discord.Color.blue()
            )
            await ctx.send(embed=embed, view=lobby_view)

        elif action in ["bat-dau", "start"]:
            lobby = self.active_party_rooms.get(ch_id)
            if not lobby:
                await ctx.send("❌ Không có phòng Bí Cảnh nào đang chờ trong kênh này! Gõ `!bi-canh tao-phong`.")
                return

            mem_count = len(lobby.members)
            total_dps = mem_count * (3000 + player.realm_index * 2000)
            exp_per_mem = 10000 + (player.realm_index * 5000)
            lt_per_mem = 2000 + (player.realm_index * 1000)

            for uid in lobby.members.keys():
                p = self.db.get_player(uid)
                if p:
                    req_exp = REALM_REQUIRED_EXP.get(p.realm_index, 1000000000)
                    p.exp = min(req_exp, p.exp + exp_per_mem)
                    p.linh_thach += lt_per_mem
                    self.db.update_player(p)

            embed = discord.Embed(
                title="🐉 ĐỘT PHÁ BÍ CẢNH MA LONG ĐỘNG THÀNH CÔNG!",
                description=f"Tổ đội **{mem_count} Tu Sĩ** phối hợp nhịp nhàng, gây `{total_dps:,}` Sát thương tiêu diệt Ma Long!\n"
                            f"🎁 Mỗi thành viên nhận: `+{exp_per_mem:,}` EXP | `+{lt_per_mem:,}` Linh Thạch!",
                color=discord.Color.green()
            )
            await ctx.send(embed=embed)
            del self.active_party_rooms[ch_id]

    @commands.command(
        name="diet-boss",
        aliases=["boss-server", "worldboss"],
        brief="Xông vào Ma Vương Giáng Lâm (World Boss Server).",
        usage="diet-boss"
    )
    async def dietboss_cmd(self, ctx: commands.Context):
        """Xông vào Ma Vương Giáng Lâm (World Boss Toàn Server)."""
        player = self.db.get_player(ctx.author.id)
        if not player:
            await ctx.send("❌ Vui lòng gõ `!nhapmon` trước!")
            return

        p_atk, crit_chance = calculate_player_pve_atk(player)
        dmg = int(p_atk * random.uniform(2.5, 4.0))

        self.world_boss_hp = max(0, self.world_boss_hp - dmg)
        self.db.update_world_boss_dps(player.user_id, dmg)

        embed = discord.Embed(
            title=f"🔥 THÁI CỔ MA VƯƠNG GIÁNG LÂM 🔥",
            description=f"⚔️ Tu sĩ **{player.dao_hieu}** dốc toàn lực tung ra đòn chí mạng gây **`{dmg:,}` Sát Thương** lên **{self.world_boss_name}**!\n"
                        f"> 🐍 Máu Ma Vương còn: `{self.world_boss_hp:,} / {self.world_boss_max_hp:,}` HP",
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
                dmg_trap = int(player.max_hp * 0.20)
                player.hp = max(1, player.hp - dmg_trap)
                r_embed.add_field(name="🩸 Bẫy Cổ Trận", value=f"Bẫy cổ kích hoạt, tổn thất `-{dmg_trap:,}` HP!", inline=False)

            elif room["type"] == "MIMIC":
                if random.random() < 0.50:
                    player.tien_ngoc += 30
                    r_embed.add_field(name="✨ Rương Thần", value="Mở rương thật! Nhận `+30` Tiên Ngọc 🌟!", inline=False)
                else:
                    m_dmg = int(player.max_hp * 0.25)
                    player.hp = max(1, player.hp - m_dmg)
                    r_embed.add_field(name="🐍 Rương Mimic Giả", value=f"Rương giả cắn chí mạng `-{m_dmg:,}` HP!", inline=False)

            elif room["type"] == "MERCHANT":
                merchant_view = DungeonMerchantView(ctx.author.id)
                await msg_obj.edit(embed=r_embed, view=merchant_view)
                await merchant_view.wait()

            elif room["type"] == "BOSS":
                boss = generate_pve_monster(player.realm_index, floor_offset=3)
                boss["name"] = "🐉 THÁI CỔ MÃNG HOÀNG (BOSS CẤM ĐỊA)"
                log, boss = process_turn_action(player, boss, "GONGFA")
                r_embed.add_field(name="🐉 Trảm Boss Cấm Địa", value=f"> {log['message']}", inline=False)

            self.db.update_player(player)
            await msg_obj.edit(embed=r_embed, view=None)

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
        brief="Tẩy trừ hiệu ứng Độc Tố Thấu Cốt / Ô Nhiễm Tâm Ma.",
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

        player.lingering_debuff = None
        self.db.update_player(player)
        await ctx.send(f"✨ **TẨY TRỪ THÀNH CÔNG!** Tu sĩ **{player.dao_hieu}** đã giải trừ toàn bộ Độc Tố & Ô Nhiễm Tâm Ma!")
