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
    REALMS, REALM_REQUIRED_EXP, SPIRITUAL_ROOT_QUALITY_BUFF, ELEMENTS_NGU_HANH, ELEMENTS_DI_LINH_CAN,
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
from app.discord_bot.modules.tutien.renderers.profile_renderer import render_tutien_profile_card
from app.discord_bot.modules.tutien.ui.tribulation_ui import TribulationWaveView, HeartDemonQuizView

GIF_CHEST_PATH = "pictures/open_chest.gif"


class TuTienCog(commands.Cog, name="TuTien"):
    """
    Hệ thống Tu Tiên: «ĐẠI ĐẠO TRANH PHONG» (Prefix Commands + Gacha Engine)
    """

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.db = TuTienDB()
        self.ho_phap_registry = {}  # {target_user_id: guardian_user_id}
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
    @tasks.loop(minutes=60)
    async def bg_recovery_task(self):
        """Phục hồi Tinh Lực (+10/h) & Linh Khí Kênh (+5000/h) mỗi giờ."""
        await self.bot.wait_until_ready()
        try:
            self.db.recover_all_players_tinh_luc(10)
            self.db.recover_all_channels_linh_khi(5000)
        except Exception as e:
            print(f"[TuTien] Error in recovery task: {e}")

    @tasks.loop(minutes=2)
    async def bg_retention_guard(self):
        """Check AFK meditation retention guard (ảo giác Tâm Ma) & Auto-Định Tâm cho VIP Thẻ Tháng."""
        await self.bot.wait_until_ready()
        try:
            now = time.time()
            with self.db.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT user_id, meditate_start_time, is_vip_pass FROM tutien_players WHERE is_meditating = 1")
                meditating_players = cursor.fetchall()

                for row in meditating_players:
                    u_id = row["user_id"]
                    start_t = row["meditate_start_time"]
                    is_vip_pass = row["is_vip_pass"]

                    if is_vip_pass:
                        conn.execute("UPDATE tutien_players SET dao_tam = dao_tam + 5 WHERE user_id = ?", (u_id,))
                        continue

                    if start_t and (now - start_t > 900) and random.random() < 0.10:
                        user = self.bot.get_user(u_id)
                        if user:
                            try:
                                await user.send("⚠️ **Tâm trí bạn xuất hiện ảo giác Tâm Ma khi bế quan!** Hãy gõ `!tuluyen` để định tâm duy trì nhập định!")
                            except Exception:
                                pass
        except Exception as e:
            print(f"[TuTien] Retention guard error: {e}")

    # --- 🔮 GACHA 3 BANNERS COMMANDS ---

    @commands.command(name="quay-gacha", aliases=["gacha", "quaygacha"])
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

    @commands.command(name="xienquach", aliases=["quere", "bocque"])
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

    @commands.command(name="wishlist", aliases=["dinh-huong"])
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

    @commands.command(name="linhbui-shop", aliases=["doilinhbui", "shard-shop"])
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

    @commands.command(name="nap-tien", aliases=["naptutien", "napngoc"])
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

    @commands.command(name="tiencac", aliases=["tiencac-shop", "tiên-các"])
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

    @commands.command(name="mua", aliases=["muatiencac", "mua-tiencac"])
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

    @commands.command(name="vip", aliases=["the-thang", "thethang"])
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

    @commands.command(name="nhapmon", aliases=["taonhanvat", "nhap-mon"])
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

    @commands.command(name="tutien-huongdan", aliases=["huongdan", "tutienhelp", "tuhds"])
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
            name="6️⃣ Bước 6: Shop Tiên Các & Giao Dịch",
            value="> Gõ `!tiencac` xem shop bảo hiểm độ kiếp, bùa chống cướp, Thẻ Tháng VIP. Gõ `!gacha` quay bảo vật Tiên Cấp (có bảo hiểm Pity 80 lượt).",
            inline=False
        )
        embed.set_footer(text="Gõ !tutien-profile để bắt đầu kiểm tra thông tin nhân vật của bạn!")
        await ctx.send(embed=embed)

    @commands.command(name="tutien-profile", aliases=["tutienprofile", "hoso-tutien", "nhanvat-tutien"])
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

    @commands.command(name="tamcanh", aliases=["can-co", "tam-canh"])
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

    @commands.command(name="phe-tu-vi", aliases=["phetuvi"])
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

    @commands.command(name="tu-luyen", aliases=["tuluyen", "train"])
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

    @commands.command(name="nhap-dinh", aliases=["nhapdinh", "bequan"])
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

    @commands.command(name="luyen-the", aliases=["luyenthe"])
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

    @commands.command(name="dot-pha", aliases=["dotpha", "breakthrough"])
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

    @commands.command(name="cuop", aliases=["cuop-dong-phu"])
    async def cuop_cmd(self, ctx: commands.Context, target: discord.Member):
        """Đột nhập Động Phủ cướp Linh Thạch (Bị chặn 100% nếu mục tiêu bật Bùa Phòng Thủ)."""
        attacker = self.db.get_player(ctx.author.id)
        victim = self.db.get_player(target.id)

        if not attacker or not victim:
            await ctx.send("❌ Cả 2 tu sĩ đều phải nhập môn Tu Tiên!")
            return

        if is_array_protected(victim):
            await ctx.send(f"🛡️ **TRẬN PHÁP BẤT XÂM PHẠM!** Động Phủ của **{victim.dao_hieu}** đang được bảo vệ bởi Bùa Tiên Các, cướp phá thất bại!")
            return

        if victim.linh_thach < 100:
            await ctx.send(f"❌ Động phủ của **{victim.dao_hieu}** nghèo xơ xác, không có gì để cướp!")
            return

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
