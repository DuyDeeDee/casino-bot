import logging
import random
import time
from contextlib import suppress

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)


class ConfirmResetView(discord.ui.View):
    def __init__(self, author: discord.User | discord.Member, timeout: float = 60.0):
        super().__init__(timeout=timeout)
        self.author = author
        self.confirmed = False

    @discord.ui.button(label="Xác nhận Reset", style=discord.ButtonStyle.danger, emoji="⚠️")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = True
        self.stop()
        try:
            await interaction.response.edit_message(content="⏳ Đang tiến hành reset ví của tất cả người chơi...", view=None)
        except Exception:
            pass

    @discord.ui.button(label="Hủy bỏ", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.confirmed = False
        self.stop()
        try:
            await interaction.response.edit_message(content="❌ Đã hủy yêu cầu reset ví.", view=None)
        except Exception:
            pass

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author.id:
            await interaction.response.send_message("Bạn không phải admin thực hiện hành động này!", ephemeral=True)
            return False
        return True


async def get_user_name(client: commands.Bot, user_id: int) -> str:
    user = client.get_user(user_id)
    if user:
        return user.name
    try:
        user = await client.fetch_user(user_id)
        return user.name
    except Exception:
        return f"Người chơi {user_id}"


class PaginatorView(discord.ui.View):
    def __init__(self, ctx: commands.Context, total_pages: int, get_page_content_func, timeout: float = 120.0):
        super().__init__(timeout=timeout)
        self.ctx = ctx
        self.total_pages = total_pages
        self.get_page_content_func = get_page_content_func
        self.current_page = 1
        self.message = None

    async def update_message(self):
        embed = await self.get_page_content_func(self.current_page)
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                if child.label == "◀️ Trước":
                    child.disabled = self.current_page == 1
                elif child.label == "Sau ▶️":
                    child.disabled = self.current_page == self.total_pages
        
        await self.message.edit(embed=embed, view=self)

    @discord.ui.button(label="◀️ Trước", style=discord.ButtonStyle.primary)
    async def prev_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.current_page > 1:
            self.current_page -= 1
            await self.update_message()

    @discord.ui.button(label="Sau ▶️", style=discord.ButtonStyle.primary)
    async def next_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.defer()
        if self.current_page < self.total_pages:
            self.current_page += 1
            await self.update_message()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.ctx.author.id:
            await interaction.response.send_message("Bạn không phải admin yêu cầu lệnh này!", ephemeral=True)
            return False
        return True

    async def on_timeout(self):
        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await self.message.edit(view=self)
        except Exception:
            pass


class GamblingHelpers(commands.Cog, name="General"):
    def __init__(self, client: commands.Bot) -> None:
        self.client = client
        self.economy = getattr(client, "economy", Economy())
        self.client.add_check(self.check_user_loans_check)

    def cog_unload(self) -> None:
        self.client.remove_check(self.check_user_loans_check)

    async def check_user_loans_check(self, ctx: commands.Context) -> bool:
        if not self.economy or (ctx.author and ctx.author.bot):
            return True
            
        user_id = ctx.author.id
        loan_amount, loan_due = self.economy.get_loan(user_id)
        if loan_amount > 0 and int(time.time()) > loan_due:
            total_penalty = int(loan_amount * 1.7)
            self.economy.add_money(user_id, -total_penalty)
            self.economy.clear_loan(user_id)
            
            log_wallet_change(
                logger,
                event="loan_overdue_penalty",
                user_id=user_id,
                money_delta=-total_penalty,
                ctx=ctx,
                loan_amount=loan_amount,
            )
            
            new_balance = self.economy.get_entry(user_id)[1]
            
            embed = make_embed(
                title="☠️ XÃ HỘI ĐEN ĐÒI NỢ ☠️",
                description=(
                    f"⚠️ **{ctx.author.mention} đã quá hạn trả nợ 1 tuần!**\n"
                    f"Giang hồ xã hội đen đã tìm đến bạn để xiết nợ cưỡng chế!\n\n"
                    f"💸 **Số tiền cưỡng chế tịch thu:** `-{total_penalty:,} VND` (Gốc {loan_amount:,} VND + 70% lãi)\n"
                    f"💳 **Số dư còn lại của bạn:** `{new_balance:,} VND`"
                ),
                color=discord.Color.red(),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            try:
                await ctx.send(embed=embed)
            except Exception:
                pass
        return True

    @commands.command(hidden=True)
    @commands.is_owner()
    async def set(
        self,
        ctx: commands.Context,
        user_id: int | None = None,
        money: int | None = None,
        credits: int | None = None,
    ):
        if user_id is None:
            user_id = ctx.author.id
        before = self.economy.get_entry(user_id)
        if money is not None:
            self.economy.set_money(user_id, money)
        if credits is not None:
            self.economy.set_credits(user_id, credits)
        after = self.economy.get_entry(user_id)
        log_wallet_change(
            logger,
            event="admin_set_wallet",
            user_id=user_id,
            money_delta=after[1] - before[1],
            credits_delta=after[2] - before[2],
            ctx=ctx,
            actor_user_id=ctx.author.id,
        )

    @commands.command(hidden=True)
    @commands.is_owner()
    async def resetall(self, ctx: commands.Context):
        """Reset tiền (VND), vàng (Gold) và toàn bộ dữ liệu khởi nghiệp của tất cả người chơi."""
        view = ConfirmResetView(ctx.author)
        msg = await ctx.send(
            "⚠️ **CẢNH BÁO:** Bạn có chắc chắn muốn reset toàn bộ tiền (VND), vàng (Gold), và dữ liệu khởi nghiệp (doanh nghiệp, túi đồ, cổ phiếu...) của **TẤT CẢ** người chơi không?\nHành động này không thể hoàn tác!",
            view=view
        )
        
        await view.wait()
        
        if view.confirmed:
            self.economy.reset_all_data()
            log_wallet_change(
                logger,
                event="admin_reset_all_data",
                user_id=0,
                money_delta=0,
                ctx=ctx,
                actor_user_id=ctx.author.id,
            )
            try:
                await msg.edit(content="✅ **Thành công:** Đã reset toàn bộ tiền, vàng và dữ liệu khởi nghiệp của tất cả người chơi về mặc định!")
            except Exception:
                await ctx.send("✅ **Thành công:** Đã reset toàn bộ tiền, vàng và dữ liệu khởi nghiệp của tất cả người chơi về mặc định!")

    @commands.command(
        brief="Xem số tiền bạn hoặc người khác đang có",
        usage="money [@thành_viên]",
        aliases=["credits", "vang", "gold"],
    )
    async def money(self, ctx: commands.Context, user: discord.Member | None = None):
        target_user = user or ctx.author
        profile = self.economy.get_entry(target_user.id)
        
        try:
            from app.discord_bot.modules.profile_renderer import render_money_card
            from uuid import uuid4
            
            # Determine role text dynamically
            if isinstance(target_user, discord.Member):
                if target_user.guild.owner_id == target_user.id:
                    role_text = "CHỦ SỞ HỮU • CẤP TỐI CAO"
                elif target_user.guild_permissions.administrator:
                    role_text = "QUẢN TRỊ VIÊN • CẤP CAO"
                elif target_user.guild_permissions.manage_guild or target_user.guild_permissions.kick_members:
                    role_text = "ĐIỀU HÀNH VIÊN • CẤP TRUNG"
                else:
                    role_text = "THÀNH VIÊN • CẤP THƯỜNG"
            else:
                role_text = "THÀNH VIÊN • CẤP THƯỜNG"
                
            avatar_url = target_user.display_avatar.with_format("png").url
            img_buffer = await render_money_card(
                username=target_user.name,
                avatar_url=avatar_url,
                money=profile[1],
                gold=profile[2],
                role_text=role_text
            )
            
            filename = f"money-{target_user.id}-{uuid4().hex[:6]}.png"
            file = discord.File(fp=img_buffer, filename=filename)
            
            embed = make_embed(
                color=discord.Color.purple()
            )
            embed.set_image(url=f"attachment://{filename}")
            
            await ctx.send(file=file, embed=embed)
            img_buffer.close()
        except Exception as e:
            logger.error(f"Failed to render money card: {e}", exc_info=True)
            embed = make_embed(
                title=target_user.name,
                description=(
                    "**{:,} VND**".format(profile[1]) + "\n**{:,}** thỏi vàng".format(profile[2])
                ),
            )
            embed.set_thumbnail(url=target_user.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.command(
        brief="Hiển thị bảng xếp hạng những người giàu nhất",
        usage="leaderboard",
        aliases=["top"],
    )
    async def leaderboard(self, ctx: commands.Context):
        entries = self.economy.top_entries(5)
        embed = make_embed(title="Bảng xếp hạng đại gia:", color=discord.Color.gold())
        for i, entry in enumerate(entries):
            user = self.client.get_user(entry[0])
            name = user.name if user else f"Người chơi {entry[0]}"
            embed.add_field(
                name=f"{i+1}. {name}",
                value="{:,} VND".format(entry[1]),
                inline=False,
            )
        await ctx.send(embed=embed)

    @commands.command(
        brief="Điểm danh hàng ngày để nhận tiền miễn phí",
        usage="daily",
        aliases=["diemdanh"],
    )
    async def daily(self, ctx: commands.Context):
        embed = await self.process_daily(ctx.author, ctx)
        await ctx.send(embed=embed)

    async def process_daily(self, user: discord.User | discord.Member, ctx: commands.Context | None = None) -> discord.Embed:
        user_id = user.id
        last_daily, streak = self.economy.get_daily(user_id)
        now = int(time.time())
        cooldown = 86400  # 24 hours
        
        # Check cooldown
        if now - last_daily < cooldown:
            remaining = cooldown - (now - last_daily)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            
            embed = make_embed(
                title="⏳ ĐIỂM DANH HÀNG NGÀY",
                description=(
                    f"**{user.name}** ơi, bạn đã điểm danh hôm nay rồi!\n"
                    f"Vui lòng quay lại sau **{hours:02d} giờ {minutes:02d} phút {seconds:02d} giây**."
                ),
                color=discord.Color.red(),
            )
            if hasattr(user, "display_avatar"):
                embed.set_thumbnail(url=user.display_avatar.url)
            return embed
            
        # Cooldown passed. Calculate streak.
        # If last daily was within 48 hours, keep streak. Otherwise reset to 1.
        if now - last_daily < 172800:  # 48 hours
            streak += 1
        else:
            streak = 1
            
        # Reward: 100k base + 20k per streak day (up to 7 days, max bonus 140k).
        # Plus if streak is a multiple of 7, give 1 thỏi vàng (credits) as a special milestone!
        base_reward = 100_000
        streak_bonus = 20_000 * min(streak, 7)
        total_money = base_reward + streak_bonus
        
        self.economy.add_money(user_id, total_money)
        
        bonus_gold = 0
        gold_text = ""
        if streak > 0 and streak % 7 == 0:
            bonus_gold = 1
            self.economy.add_credits(user_id, bonus_gold)
            gold_text = f"\n🌟 **Quà cột mốc 7 ngày:** `+1 thỏi vàng` <:32100goldbarsfortnite:1514192020921651251>"
            
        self.economy.set_daily(user_id, now, streak)
        
        log_wallet_change(
            logger,
            event="daily_claim",
            user_id=user_id,
            money_delta=total_money,
            credits_delta=bonus_gold,
            ctx=ctx,
            streak=streak,
        )
        
        new_balance = self.economy.get_entry(user_id)[1]
        new_gold = self.economy.get_entry(user_id)[2]
        
        embed = make_embed(
            title="🎁 ĐIỂM DANH HÀNG NGÀY THÀNH CÔNG 🎁",
            description=(
                f"Chúc mừng **{user.name}** đã điểm danh ngày thứ **{streak}** liên tiếp!\n\n"
                f"💰 **Tiền thưởng nhận:** `+{total_money:,} VND`"
                f"{gold_text}\n"
                f"💳 **Số dư VND hiện tại:** `{new_balance:,} VND`\n"
                f"<:32100goldbarsfortnite:1514192020921651251> **Số dư Vàng hiện tại:** `{new_gold:,} thỏi vàng`"
            ),
            color=discord.Color.green(),
        )
        if hasattr(user, "display_avatar"):
            embed.set_thumbnail(url=user.display_avatar.url)
        return embed

    @commands.command(
        brief="Làm việc để kiếm tiền (hoặc bị mất tiền nếu gặp xui xẻo)",
        usage="work",
    )
    async def work(self, ctx: commands.Context):
        embed = await self.process_work(ctx.author, ctx)
        await ctx.send(embed=embed)

    async def process_work(self, user: discord.User | discord.Member, ctx: commands.Context | None = None) -> discord.Embed:
        user_id = user.id
        
        # Kiểm tra cooldown dựa trên database
        stats = self.economy.get_simulator_stats(user_id)
        last_work = stats[4] if len(stats) > 4 else 0
        now = int(time.time())
        cooldown = 3600  # Cooldown 1 tiếng (3600 giây)
        
        if now - last_work < cooldown:
            remaining = cooldown - (now - last_work)
            hours = remaining // 3600
            minutes = (remaining % 3600) // 60
            seconds = remaining % 60
            
            if hours > 0:
                time_str = f"**{hours} giờ {minutes} phút {seconds} giây**"
            elif minutes > 0:
                time_str = f"**{minutes} phút {seconds} giây**"
            else:
                time_str = f"**{seconds} giây**"
                
            embed = make_embed(
                title="⏳ BẠN ĐANG MỆT ⏳",
                description=(
                    f"**{user.name}** ơi, bạn đã làm việc gần đây rồi!\n"
                    f"Vui lòng quay lại sau {time_str}."
                ),
                color=discord.Color.red(),
            )
            if hasattr(user, "display_avatar"):
                embed.set_thumbnail(url=user.display_avatar.url)
            return embed

        # Cập nhật thời gian làm việc mới nhất trước khi thực hiện công việc
        self.economy.set_simulator_stats(user_id, last_work=now)

        # Lấy thông tin tài khoản người chơi
        profile = self.economy.get_entry(user_id)
        current_money = profile[1]

        # 1. 10% cơ hội xảy ra sự kiện đặc biệt (sugar baby, phú bà, cứu chủ tịch) cho TẤT CẢ mọi người
        if random.random() < 0.10:
            special_scenarios = [
                "Làm trai bao được phú bà bao nuôi 💖",
                "Làm sugar baby ngoan ngoãn 🧸",
                "Vô tình cứu được chủ tịch giả danh và cái kết 🤵"
            ]
            scenario = random.choice(special_scenarios)
            reward = random.randint(1_000_000, 5_000_000)
            
            # Cộng tiền vào tài khoản
            self.economy.add_money(user_id, reward)
            
            log_wallet_change(
                logger,
                event="work_special_event",
                user_id=user_id,
                money_delta=reward,
                ctx=ctx,
            )

            new_balance = self.economy.get_entry(user_id)[1]

            embed = make_embed(
                title="🎰 SỰ KIỆN ĐẶC BIỆT! 🎰",
                description=(
                    f"**{user.name}** đã trúng sự kiện đặc biệt:\n"
                    f"👉 *\"{scenario}\"*\n\n"
                    f"💰 **Phần thưởng:** `+{reward:,} VND`\n"
                    f"💳 **Số dư mới:** `{new_balance:,} VND`"
                ),
                color=discord.Color.gold(), # Màu vàng
            )
            if hasattr(user, "display_avatar"):
                embed.set_thumbnail(url=user.display_avatar.url)
            return embed

        # 2. Nếu không trúng sự kiện đặc biệt (90% còn lại):
        # Lấy túi đồ của người chơi để kiểm tra các bằng cấp / nghề nghiệp sở hữu
        inventory = self.economy.get_inventory(user_id)
        owned_careers = []
        for item, qty in inventory:
            if qty > 0 and item in ['bang_cap', 'bang_kien_truc', 'bang_phi_hanh', 'bang_bac_si', 'the_tho_san']:
                owned_careers.append(item)

        if owned_careers:
            # Chọn ngẫu nhiên một trong các nghề nghiệp đang sở hữu
            chosen_career = random.choice(owned_careers)
            
            if chosen_career == 'bang_cap':
                # Kỹ thuật công nghệ (Rủi ro 10%)
                if random.random() < 0.10:
                    penalty = 500_000
                    actual_deduction = min(current_money, penalty)
                    self.economy.add_money(user_id, -penalty)
                    
                    log_wallet_change(
                        logger,
                        event="work_tech_badluck",
                        user_id=user_id,
                        money_delta=-actual_deduction,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="🔥 SỰ CỐ CÔNG NGHỆ! 🔥",
                        description=(
                            f"**{user.name}** gặp sự cố kỹ thuật:\n"
                            f"👉 *\"Bạn làm chập cháy mạch, phải đền bù 500,000 VND.\"*\n\n"
                            f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.red(),
                    )
                else:
                    tech_jobs = [
                        ("Thiết kế cho công ty khởi nghiệp 🛠️", 1_500_000),
                        ("Setup thành công server cho khách hàng 🎮", 800_000),
                        ("Phát triển ứng dụng Mobile mini cho shop quần áo 📱", 1_200_000),
                        ("Khắc phục sự cố mạng doanh nghiệp trong đêm 🌐", 1_000_000)
                    ]
                    job_desc, reward = random.choice(tech_jobs)
                    self.economy.add_money(user_id, reward)
                    
                    log_wallet_change(
                        logger,
                        event="work_tech_success",
                        user_id=user_id,
                        money_delta=reward,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="💻 DỰ ÁN CÔNG NGHỆ THÀNH CÔNG! 💻",
                        description=(
                            f"**{user.name}** đã hoàn thành dự án:\n"
                            f"👉 *\"{job_desc}\"*\n\n"
                            f"💰 **Thu nhập:** `+{reward:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.blue(),
                    )
                    
            elif chosen_career == 'bang_kien_truc':
                # Kiến trúc sư (Rủi ro 10%)
                if random.random() < 0.10:
                    penalty = 800_000
                    actual_deduction = min(current_money, penalty)
                    self.economy.add_money(user_id, -penalty)
                    
                    log_wallet_change(
                        logger,
                        event="work_arch_badluck",
                        user_id=user_id,
                        money_delta=-actual_deduction,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="🔥 SỰ CỐ THIẾT KẾ! 🔥",
                        description=(
                            f"**{user.name}** gặp lỗi kỹ thuật bản vẽ:\n"
                            f"👉 *\"Bạn thiết kế sai kết cấu móng nhà, bị phạt đền bù 800,000 VND.\"*\n\n"
                            f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.red(),
                    )
                else:
                    arch_jobs = [
                        ("Vẽ bản thiết kế biệt thự nghỉ dưỡng ở Đà Lạt 📐", 2_400_000),
                        ("Tư vấn quy hoạch đô thị cho tập đoàn bất động sản 🏙️", 1_800_000),
                        ("Thiết kế nội thất căn hộ Penthouse sang trọng 🛋️", 3_000_000)
                    ]
                    job_desc, reward = random.choice(arch_jobs)
                    self.economy.add_money(user_id, reward)
                    
                    log_wallet_change(
                        logger,
                        event="work_arch_success",
                        user_id=user_id,
                        money_delta=reward,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="📐 DỰ ÁN KIẾN TRÚC THÀNH CÔNG! 📐",
                        description=(
                            f"**{user.name}** đã hoàn thành bản vẽ:\n"
                            f"👉 *\"{job_desc}\"*\n\n"
                            f"💰 **Thu nhập:** `+{reward:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.teal(),
                    )

            elif chosen_career == 'bang_phi_hanh':
                # Phi hành gia (Rủi ro 10%)
                if random.random() < 0.10:
                    penalty = 1_500_000
                    actual_deduction = min(current_money, penalty)
                    self.economy.add_money(user_id, -penalty)
                    
                    log_wallet_change(
                        logger,
                        event="work_astro_badluck",
                        user_id=user_id,
                        money_delta=-actual_deduction,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="🔥 SỰ CỐ KHÔNG GIAN! 🔥",
                        description=(
                            f"**{user.name}** gặp sự cố ngoài không gian:\n"
                            f"👉 *\"Gặp sự cố rò rỉ oxy trên trạm ISS, phải bồi thường phí xử lý khẩn cấp 1,500,000 VND.\"*\n\n"
                            f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.red(),
                    )
                else:
                    astro_jobs = [
                        ("Thực hiện chuyến đi bộ ngoài không gian sửa tấm pin mặt trời 🚀", 6_000_000),
                        ("Nghiên cứu mẫu đất đá quý từ Sao Hỏa gửi về Trái Đất ☄️", 4_500_000),
                        ("Huấn luyện phi hành đoàn kế cận tại trung tâm vũ trụ 🌌", 8_000_000)
                    ]
                    job_desc, reward = random.choice(astro_jobs)
                    self.economy.add_money(user_id, reward)
                    
                    log_wallet_change(
                        logger,
                        event="work_astro_success",
                        user_id=user_id,
                        money_delta=reward,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="🚀 DỰ ÁN VŨ TRỤ THÀNH CÔNG! 🚀",
                        description=(
                            f"**{user.name}** đã hoàn thành sứ mệnh:\n"
                            f"👉 *\"{job_desc}\"*\n\n"
                            f"💰 **Thu nhập:** `+{reward:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.dark_blue(),
                    )

            elif chosen_career == 'bang_bac_si':
                # Bác sĩ (Rủi ro 10%)
                if random.random() < 0.10:
                    penalty = 3_000_000
                    actual_deduction = min(current_money, penalty)
                    self.economy.add_money(user_id, -penalty)
                    
                    log_wallet_change(
                        logger,
                        event="work_doc_badluck",
                        user_id=user_id,
                        money_delta=-actual_deduction,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="🔥 TAI NẠN Y KHOA! 🔥",
                        description=(
                            f"**{user.name}** gặp sự cố chuyên môn:\n"
                            f"👉 *\"Kê nhầm đơn thuốc bổ đắt đỏ cho khách VIP, bị bệnh viện trừ lương đền bù 3,000,000 VND.\"*\n\n"
                            f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.red(),
                    )
                else:
                    doc_jobs = [
                        ("Phẫu thuật thành công ca ghép tim phức tạp 🩺", 18_000_000),
                        ("Điều trị phục hồi sức khỏe VIP cho tỷ phú 🏥", 12_000_000),
                        ("Nghiên cứu lâm sàng vắc-xin thế hệ mới 🧪", 20_000_000)
                    ]
                    job_desc, reward = random.choice(doc_jobs)
                    self.economy.add_money(user_id, reward)
                    
                    log_wallet_change(
                        logger,
                        event="work_doc_success",
                        user_id=user_id,
                        money_delta=reward,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="🩺 CA PHẪU THUẬT THÀNH CÔNG! 🩺",
                        description=(
                            f"**{user.name}** đã hoàn thành nhiệm vụ y khoa:\n"
                            f"👉 *\"{job_desc}\"*\n\n"
                            f"💰 **Thu nhập:** `+{reward:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.dark_green(),
                    )

            else: # the_tho_san
                # Thợ săn kho báu (Rủi ro 10%)
                if random.random() < 0.10:
                    penalty = 5_000_000
                    actual_deduction = min(current_money, penalty)
                    self.economy.add_money(user_id, -penalty)
                    
                    log_wallet_change(
                        logger,
                        event="work_hunter_badluck",
                        user_id=user_id,
                        money_delta=-actual_deduction,
                        ctx=ctx,
                    )
                    new_balance = self.economy.get_entry(user_id)[1]
                    embed = make_embed(
                        title="🔥 BẪY CỔ ĐẠI KÍCH HOẠT! 🔥",
                        description=(
                            f"**{user.name}** bị sập bẫy trong hầm mộ:\n"
                            f"👉 *\"Bị sập bẫy đá cổ trong hầm mộ, phải chi tiền viện phí điều trị vết thương 5,000,000 VND.\"*\n\n"
                            f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                            f"💳 **Số dư mới:** `{new_balance:,} VND`"
                        ),
                        color=discord.Color.red(),
                    )
                else:
                    from app.discord_bot.cogs.simulator import TREASURES
                    
                    r = random.random()
                    if r < 0.35:
                        rarity_pool = [k for k, v in TREASURES.items() if v["rarity"] == "Rác thải"]
                    elif r < 0.70:
                        rarity_pool = [k for k, v in TREASURES.items() if v["rarity"] == "Thường"]
                    elif r < 0.85:
                        rarity_pool = [k for k, v in TREASURES.items() if v["rarity"] == "Hiếm"]
                    elif r < 0.95:
                        rarity_pool = [k for k, v in TREASURES.items() if v["rarity"] == "Quý hiếm"]
                    elif r < 0.99:
                        rarity_pool = [k for k, v in TREASURES.items() if v["rarity"] == "Huyền thoại"]
                    else:
                        rarity_pool = [k for k, v in TREASURES.items() if v["rarity"] == "Thần thoại"]
                    
                    chosen_id = random.choice(rarity_pool)
                    treasure = TREASURES[chosen_id]
                    
                    # Add to inventory
                    self.economy.add_inventory_item(user_id, chosen_id, 1)
                    
                    # Log finding item
                    log_wallet_change(
                        logger,
                        event="work_hunter_success_item",
                        user_id=user_id,
                        money_delta=0,
                        item_id=chosen_id,
                        quantity=1,
                        ctx=ctx,
                    )
                    
                    embed = make_embed(
                        title="🗺️ KHAI QUẬT ĐƯỢC KHO BÁU CỔ! 🗺️",
                        description=(
                            f"**{user.name}** đã thám hiểm hầm mộ cổ và tìm thấy:\n\n"
                            f"🏺 **Kho báu:** {treasure['name']} (ID: `{chosen_id}`)\n"
                            f"✨ **Độ hiếm:** `{treasure['rarity']}`\n"
                            f"💰 **Giá trị ước tính:** `{treasure['value']:,} VND`\n\n"
                            f"💡 *Bạn có thể giữ lại để sưu tầm hoặc dùng lệnh `i?sellitem {chosen_id}` để bán cho viện bảo tàng.*"
                        ),
                        color=discord.Color.orange(),
                    )
            
            if hasattr(user, "display_avatar"):
                embed.set_thumbnail(url=user.display_avatar.url)
            return embed

        # 3. Làm việc bình thường (cafe, grab...)
        normal_rand = random.random()
        
        if normal_rand < 0.80:
            # A. Kịch bản làm việc suôn sẻ (80% của 90%)
            jobs = [
                "Phục vụ quán cafe ☕",
                "Bảo vệ ca đêm 👮",
                "Chạy xe ôm công nghệ (Grab/Be) 🛵",
                "Nhân viên pha chế (Barista) 🍹",
                "Phát tờ rơi ngoài ngã tư 📄",
                "Streamer part-time 🎮"
            ]
            job = random.choice(jobs)
            reward = random.randint(20_000, 50_000)
            
            # Cộng tiền vào tài khoản
            self.economy.add_money(user_id, reward)
            
            log_wallet_change(
                logger,
                event="work_normal_success",
                user_id=user_id,
                money_delta=reward,
                ctx=ctx,
            )

            new_balance = self.economy.get_entry(user_id)[1]

            embed = make_embed(
                title="💼 Đi làm chăm chỉ 💼",
                description=(
                    f"**{user.name}** đã đi làm: *{job}*\n\n"
                    f"💰 **Thu nhập:** `+{reward:,} VND`\n"
                    f"💳 **Số dư mới:** `{new_balance:,} VND`"
                ),
                color=discord.Color.green(), # Màu xanh lá
            )
            if hasattr(user, "display_avatar"):
                embed.set_thumbnail(url=user.display_avatar.url)
            return embed
            
        else:
            # B. Kịch bản xui xẻo/bị trừ tiền (20% của 90%)
            bad_scenarios = [
                "Bị vấp té làm vỡ ly của quán và phải đền tiền 😢",
                "Chạy xe ôm bị thủng lốp dọc đường 🛞",
                "Bị khách hàng boom đơn hàng đồ ăn lớn 😭",
                "Ngủ gật trong lúc làm bảo vệ ca đêm bị trừ lương 😴"
            ]
            scenario = random.choice(bad_scenarios)
            penalty = random.randint(10_000, 30_000)
            
            # Trừ tiền (add_money với số âm, SQLite MAX(0, money + ?) tự động lo việc không để tiền âm)
            actual_deduction = min(current_money, penalty)
            self.economy.add_money(user_id, -penalty)
            
            log_wallet_change(
                logger,
                event="work_normal_badluck",
                user_id=user_id,
                money_delta=-actual_deduction,
                ctx=ctx,
            )

            new_balance = self.economy.get_entry(user_id)[1]

            embed = make_embed(
                title="❌ Hôm nay quá xui xẻo! ❌",
                description=(
                    f"**{user.name}** gặp vận xui:\n"
                    f"👉 *{scenario}*\n\n"
                    f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                    f"💳 **Số dư mới:** `{new_balance:,} VND`"
                ),
                color=discord.Color.red(), # Màu đỏ
            )
            if hasattr(user, "display_avatar"):
                embed.set_thumbnail(url=user.display_avatar.url)
            return embed

    @commands.command(
        brief="Nhận quà khởi nghiệp lần đầu tiên đặt chân lên thành phố",
        usage="khoinghiep",
        aliases=["batdau", "startup", "firsttime"],
    )
    async def khoinghiep(self, ctx: commands.Context):
        user_id = ctx.author.id
        
        # Kiểm tra xem người chơi đã nhận quà khởi nghiệp chưa
        if self.economy.has_claimed_start(user_id):
            embed = make_embed(
                title="Khởi nghiệp thất bại? 💸",
                description=(
                    f"**{ctx.author.name}** ơi, bạn đã nhận quà khởi nghiệp từ bố mẹ trước đó rồi!\n"
                    "Hãy tự đi làm kiếm tiền bằng lệnh `!work` hoặc tham gia các sòng bạc nhé."
                ),
                color=discord.Color.red(),
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
            return

        # Thực hiện tặng tiền và đánh dấu đã nhận
        amount = 1_000_000 # 1 triệu VND
        self.economy.add_money(user_id, amount)
        self.economy.set_claimed_start(user_id)
        
        log_wallet_change(
            logger,
            event="claim_firsttime_bonus",
            user_id=user_id,
            money_delta=amount,
            ctx=ctx,
        )

        new_balance = self.economy.get_entry(user_id)[1]

        embed = make_embed(
            title="🎒 Khởi nghiệp thành phố! 🎒",
            description=(
                f"**{ctx.author.name}** vừa từ quê lên thành phố lập nghiệp.\n"
                f"Bố mẹ ở quê đã gom góp và gửi cho bạn **1,000,000 VND** làm vốn khởi nghiệp! 💸🏡\n\n"
                f"💰 **Nhận được:** `+1,000,000 VND`\n"
                f"💳 **Số dư hiện tại:** `{new_balance:,} VND`"
            ),
            color=discord.Color.purple(), # Màu tím/hồng
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Vay tiền xã hội đen. Lãi suất 70%, thời hạn 1 tuần.",
        usage="vay <số_tiền>",
        aliases=["loan"],
    )
    async def vay(self, ctx: commands.Context, amount: int):
        user_id = ctx.author.id
        
        # Kiểm tra xem có khoản vay cũ chưa trả không
        existing_loan_amount, _ = self.economy.get_loan(user_id)
        if existing_loan_amount > 0:
            await ctx.send("❌ **Lỗi:** Bạn đang có một khoản vay chưa trả! Hãy gõ `!travay` để thanh toán trước khi vay thêm.")
            return
            
        # Kiểm tra số tiền vay hợp lệ
        MAX_LOAN = 10_000_000
        if amount <= 0:
            await ctx.send("❌ **Lỗi:** Số tiền vay phải lớn hơn 0 VND.")
            return
            
        if amount > MAX_LOAN:
            await ctx.send(f"❌ **Lỗi:** Hạn mức vay tối đa của xã hội đen là **{MAX_LOAN:,} VND**.")
            return

        # Thực hiện vay trong 7 ngày
        due_time = int(time.time()) + (7 * 24 * 3600)
        
        self.economy.add_money(user_id, amount)
        self.economy.set_loan(user_id, amount, due_time)
        
        log_wallet_change(
            logger,
            event="borrow_loan",
            user_id=user_id,
            money_delta=amount,
            ctx=ctx,
            loan_amount=amount,
            due_time=due_time,
        )
        
        new_balance = self.economy.get_entry(user_id)[1]
        repay_amount = int(amount * 1.7)
        due_date_str = time.strftime("%d/%m/%Y %H:%M:%S", time.localtime(due_time))
        
        embed = make_embed(
            title="💸 HỢP ĐỒNG VAY XÃ HỘI ĐEN 💸",
            description=(
                f"**{ctx.author.name}** đã ký giấy vay tiền xã hội đen thành công!\n\n"
                f"💰 **Số tiền nhận:** `+{amount:,} VND`\n"
                f"📈 **Lãi suất:** `70%`\n"
                f"💵 **Tổng tiền cần trả:** `{repay_amount:,} VND`\n"
                f"⏱️ **Hạn chót trả nợ:** `{due_date_str}` (1 tuần)\n\n"
                f"💳 **Số dư hiện tại:** `{new_balance:,} VND`"
            ),
            color=discord.Color.dark_purple(),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Trả nợ xã hội đen (Cả gốc lẫn lãi 70%)",
        usage="travay",
        aliases=["repay", "tra"],
    )
    async def travay(self, ctx: commands.Context):
        user_id = ctx.author.id
        
        # Kiểm tra xem có khoản vay không
        loan_amount, _ = self.economy.get_loan(user_id)
        if loan_amount <= 0:
            await ctx.send("❌ **Lỗi:** Bạn không có khoản nợ nào cần trả!")
            return
            
        repay_amount = int(loan_amount * 1.7)
        current_money = self.economy.get_entry(user_id)[1]
        
        if current_money < repay_amount:
            await ctx.send(f"❌ **Thất bại:** Bạn không có đủ tiền để trả nợ. Cần **{repay_amount:,} VND** nhưng bạn chỉ có **{current_money:,} VND**.")
            return

        # Thực hiện trả nợ: trừ tiền và xóa nợ
        self.economy.add_money(user_id, -repay_amount)
        self.economy.clear_loan(user_id)
        
        log_wallet_change(
            logger,
            event="repay_loan",
            user_id=user_id,
            money_delta=-repay_amount,
            ctx=ctx,
            loan_amount=loan_amount,
        )
        
        new_balance = self.economy.get_entry(user_id)[1]
        
        embed = make_embed(
            title="✅ THANH TOÁN NỢ THÀNH CÔNG ✅",
            description=(
                f"**{ctx.author.name}** đã thanh toán xong nợ nần với xã hội đen!\n"
                f"Từ nay bạn đã là một người tự do.\n\n"
                f"💸 **Số tiền đã trả:** `-{repay_amount:,} VND` (Gốc {loan_amount:,} VND + 70% lãi)\n"
                f"💳 **Số dư tài khoản:** `{new_balance:,} VND`"
            ),
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Tặng tiền VND cho người khác",
        usage="pay @thành_viên <số_tiền>",
        aliases=["chotien", "give", "givemoney", "tangtien"],
    )
    async def pay(self, ctx: commands.Context, target: discord.Member, amount: int):
        if target.bot:
            await ctx.send("❌ **Lỗi:** Bạn không thể chuyển tiền cho bot!")
            return
        if target.id == ctx.author.id:
            await ctx.send("❌ **Lỗi:** Bạn không thể tự chuyển tiền cho chính mình!")
            return
        if amount <= 0:
            await ctx.send("❌ **Lỗi:** Số tiền chuyển phải lớn hơn 0 VND.")
            return
            
        sender_money = self.economy.get_entry(ctx.author.id)[1]
        if sender_money < amount:
            await ctx.send(f"❌ **Lỗi:** Bạn không có đủ tiền. Số dư hiện tại của bạn là **{sender_money:,} VND**.")
            return

        self.economy.add_money(ctx.author.id, -amount)
        self.economy.add_money(target.id, amount)

        log_wallet_change(
            logger,
            event="transfer_money_send",
            user_id=ctx.author.id,
            money_delta=-amount,
            ctx=ctx,
            recipient_id=target.id,
        )
        log_wallet_change(
            logger,
            event="transfer_money_receive",
            user_id=target.id,
            money_delta=amount,
            ctx=ctx,
            sender_id=ctx.author.id,
        )

        embed = make_embed(
            title="💸 CHUYỂN TIỀN THÀNH CÔNG 💸",
            description=(
                f"**{ctx.author.mention}** đã chuyển thành công **{amount:,} VND** cho **{target.mention}**!\n\n"
                f"💳 **Số dư mới của bạn:** `{self.economy.get_entry(ctx.author.id)[1]:,} VND`"
            ),
            color=discord.Color.green(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Tặng thỏi vàng cho người khác",
        usage="paygold @thành_viên <số_vàng>",
        aliases=["chotienvang", "givegold", "givevang", "tangvang"],
    )
    async def paygold(self, ctx: commands.Context, target: discord.Member, amount: int):
        if target.bot:
            await ctx.send("❌ **Lỗi:** Bạn không thể chuyển vàng cho bot!")
            return
        if target.id == ctx.author.id:
            await ctx.send("❌ **Lỗi:** Bạn không thể tự chuyển vàng cho chính mình!")
            return
        if amount <= 0:
            await ctx.send("❌ **Lỗi:** Số thỏi vàng chuyển phải lớn hơn 0.")
            return
            
        sender_gold = self.economy.get_entry(ctx.author.id)[2]
        if sender_gold < amount:
            await ctx.send(f"❌ **Lỗi:** Bạn không có đủ thỏi vàng. Số dư hiện tại của bạn là **{sender_gold:,}** thỏi vàng.")
            return

        self.economy.add_credits(ctx.author.id, -amount)
        self.economy.add_credits(target.id, amount)

        log_wallet_change(
            logger,
            event="transfer_gold_send",
            user_id=ctx.author.id,
            credits_delta=-amount,
            ctx=ctx,
            recipient_id=target.id,
        )
        log_wallet_change(
            logger,
            event="transfer_gold_receive",
            user_id=target.id,
            credits_delta=amount,
            ctx=ctx,
            sender_id=ctx.author.id,
        )

        embed = make_embed(
            title="<:32100goldbarsfortnite:1514192020921651251> CHUYỂN VÀNG THÀNH CÔNG <:32100goldbarsfortnite:1514192020921651251>",
            description=(
                f"**{ctx.author.mention}** đã chuyển thành công **{amount:,}** thỏi vàng cho **{target.mention}**!\n\n"
                f"💳 **Số dư mới của bạn:** `{self.economy.get_entry(ctx.author.id)[2]:,}` thỏi vàng"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Liệt kê danh sách tất cả người chơi trong cơ sở dữ liệu.",
        usage="botplayers",
        aliases=["players", "users"],
        hidden=True,
    )
    @commands.is_owner()
    async def botplayers(self, ctx: commands.Context):
        all_entries = self.economy.top_entries(0)
        if not all_entries:
            await ctx.send("❌ Không có người chơi nào trong cơ sở dữ liệu.")
            return

        entries_per_page = 15
        total_pages = (len(all_entries) + entries_per_page - 1) // entries_per_page

        async def get_page_embed(page_num: int) -> discord.Embed:
            start_idx = (page_num - 1) * entries_per_page
            end_idx = min(start_idx + entries_per_page, len(all_entries))
            page_entries = all_entries[start_idx:end_idx]

            desc_lines = []
            for idx, entry in enumerate(page_entries, start=start_idx + 1):
                uid, money, credits = entry[0], entry[1], entry[2]
                name = await get_user_name(self.client, uid)
                desc_lines.append(
                    f"`{idx:02d}.` **{name}** (ID: `{uid}`)\n"
                    f"   └ 💸 `{money:,} VND` | <:32100goldbarsfortnite:1514192020921651251> `{credits:,}` thỏi vàng"
                )

            embed = make_embed(
                title="📋 DANH SÁCH NGƯỜI CHƠI BOT",
                description="\n".join(desc_lines),
                color=discord.Color.blue(),
            )
            embed.set_footer(text=f"Trang {page_num}/{total_pages} | Tổng số: {len(all_entries)} người chơi | Chỉ Admin")
            return embed

        embed = await get_page_embed(1)
        if total_pages <= 1:
            await ctx.send(embed=embed)
            return

        view = PaginatorView(ctx, total_pages, get_page_embed)
        # Disable prev button on load
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label == "◀️ Trước":
                child.disabled = True
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(
        brief="Liệt kê danh sách tất cả các server bot đang tham gia.",
        usage="botservers",
        aliases=["servers"],
        hidden=True,
    )
    @commands.is_owner()
    async def botservers(self, ctx: commands.Context):
        guilds = sorted(list(self.client.guilds), key=lambda g: g.member_count or 0, reverse=True)
        if not guilds:
            await ctx.send("❌ Bot chưa tham gia server nào.")
            return

        entries_per_page = 10
        total_pages = (len(guilds) + entries_per_page - 1) // entries_per_page

        async def get_page_embed(page_num: int) -> discord.Embed:
            start_idx = (page_num - 1) * entries_per_page
            end_idx = min(start_idx + entries_per_page, len(guilds))
            page_guilds = guilds[start_idx:end_idx]

            desc_lines = []
            for idx, guild in enumerate(page_guilds, start=start_idx + 1):
                owner_name = guild.owner.name if guild.owner else f"ID: {guild.owner_id}"
                desc_lines.append(
                    f"`{idx:02d}.` **{guild.name}** (ID: `{guild.id}`)\n"
                    f"   └ 👥 `{guild.member_count:,}` thành viên | 👑 Owner: **{owner_name}**"
                )

            embed = make_embed(
                title="🌐 DANH SÁCH SERVER BOT THAM GIA",
                description="\n".join(desc_lines),
                color=discord.Color.gold(),
            )
            total_members = sum(g.member_count or 0 for g in guilds)
            embed.set_footer(text=f"Trang {page_num}/{total_pages} | Tổng: {len(guilds)} server, {total_members:,} mem | Chỉ Admin")
            return embed

        embed = await get_page_embed(1)
        if total_pages <= 1:
            await ctx.send(embed=embed)
            return

        view = PaginatorView(ctx, total_pages, get_page_embed)
        # Disable prev button on load
        for child in view.children:
            if isinstance(child, discord.ui.Button) and child.label == "◀️ Trước":
                child.disabled = True
        view.message = await ctx.send(embed=embed, view=view)

    @commands.command(name="setrl", hidden=True)
    @commands.is_owner()
    async def set_roulette_stats(
        self,
        ctx: commands.Context,
        user: discord.Member,
        plays: int,
        achievements_count: int = 3,
    ):
        """[ADMIN] Thiết lập trực tiếp plays và số lượng danh hiệu roulette cho một user."""
        user_id = user.id
        
        # Ensure user entry exists in user_roulette table
        self.economy.get_roulette(user_id)
        
        # Update plays
        self.economy.cur.execute("UPDATE user_roulette SET plays = ? WHERE user_id = ?", (plays, user_id))
        
        # Update achievements to match count
        stats = self.economy.get_roulette(user_id)
        current_ach = stats.get("achievements", [])
        if len(current_ach) != achievements_count:
            new_ach = []
            for i in range(achievements_count):
                new_ach.append(f"gifted_ach_{i}")
            import json
            self.economy.cur.execute("UPDATE user_roulette SET achievements = ? WHERE user_id = ?", (json.dumps(new_ach), user_id))
            
        self.economy.conn.commit()
        await ctx.send(f"✅ Đã cập nhật roulette stats cho **{user.name}**: plays={plays}, achievements={achievements_count}.")

    @commands.command(name="setcf", hidden=True)
    @commands.is_owner()
    async def set_coinflip_stats(
        self,
        ctx: commands.Context,
        user: discord.Member,
        plays: int,
    ):
        """[ADMIN] Thiết lập trực tiếp số lượt chơi coinflip cho một user."""
        user_id = user.id
        
        # Ensure user entry exists in user_coinflip table
        self.economy.get_coinflip(user_id)
        
        self.economy.cur.execute("UPDATE user_coinflip SET plays = ? WHERE user_id = ?", (plays, user_id))
        self.economy.conn.commit()
        await ctx.send(f"✅ Đã cập nhật coinflip plays cho **{user.name}** thành {plays}.")

    @commands.command(name="settxconfig", hidden=True, aliases=["txconfig"])
    @commands.is_owner()
    async def set_taixiu_config(
        self,
        ctx: commands.Context,
        key: str = "status",
        value: str | None = None,
    ):
        """[ADMIN] Cấu hình tỷ lệ siết (rig_rate), ngưỡng chống sập (threshold), tỷ lệ nổ hũ (jackpot_rate), cược tối thiểu nổ hũ (jackpot_min_bet), tỷ lệ thuế (tax_rate) và giá trị hũ (jackpot_value) của Tài Xỉu."""
        key = key.lower().strip()
        
        if key in ("status", "info", "view"):
            # Display current config
            rig_rate_str = self.economy.get_setting("taixiu_rig_rate")
            rig_rate = float(rig_rate_str) if rig_rate_str is not None else 0.0
            
            threshold_str = self.economy.get_setting("taixiu_anti_bankruptcy_threshold")
            threshold = int(threshold_str) if threshold_str is not None else 10000000
            
            jackpot_rate_str = self.economy.get_setting("taixiu_jackpot_rate")
            jackpot_rate = float(jackpot_rate_str) if jackpot_rate_str is not None else 1.0
            overall_jackpot_rate = jackpot_rate * (2.0 / 216.0)
            
            min_bet_str = self.economy.get_setting("taixiu_jackpot_min_bet")
            jackpot_min_bet = int(min_bet_str) if min_bet_str is not None else 50000
            
            tax_rate_str = self.economy.get_setting("taixiu_tax_rate")
            tax_rate = float(tax_rate_str) if tax_rate_str is not None else 0.0
            
            jackpot_val_str = self.economy.get_setting("taixiu_jackpot")
            jackpot_val = int(jackpot_val_str) if jackpot_val_str is not None else 0
            
            embed = make_embed(
                title="⚙️ CẤU HÌNH TÀI XỈU (ADMIN ONLY)",
                description=(
                    f"• **Tỷ lệ siết kết quả (rig_rate):** `{rig_rate * 100}%` (Cơ hội bẻ cầu để bot trả thưởng ít nhất)\n"
                    f"• **Ngưỡng chống sập (threshold):** `{threshold:,} VND` (Tự động bẻ cầu nếu bot bị lỗ vượt quá mức này ở 1 phiên)\n"
                    f"• **Tỷ lệ nổ hũ tổng thể (jackpot_rate):** `{overall_jackpot_rate * 100:.6f}%` (Cơ hội nổ hũ ở mỗi phiên chơi)\n"
                    f"  *(Tỷ lệ kích hoạt khi xúc xắc ra bão 1 hoặc 6: {jackpot_rate * 100:.4f}%)\n"
                    f"• **Cược tối thiểu tham gia nổ hũ (jackpot_min_bet):** `{jackpot_min_bet:,} VND` (Mức cược tối thiểu ở cửa thắng để được chia hũ)\n"
                    f"• **Tỷ lệ thuế cược thắng (tax_rate):** `{tax_rate * 100}%` (Số tiền thắng được trích đưa vào hũ jackpot)\n"
                    f"• **Giá trị hũ hiện tại (jackpot_value):** `{jackpot_val:,} VND` (Số tiền đang tích lũy trong hũ)\n\n"
                    f"💡 *Để thay đổi, hãy gõ:*\n"
                    f"• `{ctx.prefix}settxconfig rig_rate <0.0 - 1.0>`\n"
                    f"• `{ctx.prefix}settxconfig threshold <số_tiền_VND>`\n"
                    f"• `{ctx.prefix}settxconfig jackpot_rate <tỷ_lệ_%, vd: 0.001%>`\n"
                    f"• `{ctx.prefix}settxconfig jackpot_min_bet <số_tiền_VND>`\n"
                    f"• `{ctx.prefix}settxconfig tax_rate <tỷ_lệ_%, vd: 5%>`\n"
                    f"• `{ctx.prefix}settxconfig jackpot_value <số_tiền_VND>`"
                ),
                color=discord.Color.dark_red()
            )
            await ctx.send(embed=embed)
            return

        if value is None:
            await ctx.send(f"❌ **Lỗi:** Vui lòng cung cấp giá trị cần thiết lập cho khóa `{key}`.")
            return

        if key in ("rig_rate", "rigrate", "rate"):
            try:
                rate = float(value)
                if not (0.0 <= rate <= 1.0):
                    raise ValueError()
                self.economy.set_setting("taixiu_rig_rate", str(rate))
                await ctx.send(f"✅ Đã thiết lập tỷ lệ siết Tài Xỉu thành **{rate * 100}%**.")
            except ValueError:
                await ctx.send("❌ **Lỗi:** Tỷ lệ siết phải là số thập phân nằm trong khoảng từ `0.0` đến `1.0` (ví dụ: `0.3` đại diện cho 30%).")
                
        elif key in ("threshold", "anti_bankruptcy", "limit", "loss"):
            try:
                val = int(value)
                self.economy.set_setting("taixiu_anti_bankruptcy_threshold", str(val))
                await ctx.send(f"✅ Đã thiết lập ngưỡng chống sập Tài Xỉu thành **{val:,} VND**.")
            except ValueError:
                await ctx.send("❌ **Lỗi:** Ngưỡng chống sập phải là một số nguyên đại diện cho số tiền VND.")
                
        elif key in ("jackpot_rate", "jackpotrate", "jackpot", "nohu"):
            try:
                # Parse rate (support percentage representation like '0.001%')
                val_str = value.strip()
                if val_str.endswith("%"):
                    target_rate = float(val_str[:-1].strip()) / 100.0
                else:
                    target_rate = float(val_str)
                
                if target_rate < 0.0:
                    raise ValueError()
                
                # Convert overall rate to triplet trigger rate
                # triplet_rate = target_rate / (2/216)
                triplet_rate = target_rate * 108.0
                triplet_rate = min(1.0, max(0.0, triplet_rate))
                
                self.economy.set_setting("taixiu_jackpot_rate", str(triplet_rate))
                
                overall_computed = triplet_rate * (2.0 / 216.0)
                await ctx.send(
                    f"✅ Đã thiết lập tỷ lệ nổ hũ thành công:\n"
                    f"• Tỷ lệ tổng thể mỗi phiên: **{overall_computed * 100:.6f}%**\n"
                    f"• Tỷ lệ kích hoạt khi ra bão 1 hoặc 6: **{triplet_rate * 100:.4f}%**"
                )
            except ValueError:
                await ctx.send("❌ **Lỗi:** Tỷ lệ nổ hũ phải là số thập phân dương hoặc tỷ lệ phần trăm (ví dụ: `0.001%` hoặc `0.00001`).")
                
        elif key in ("jackpot_min_bet", "min_bet", "minbet", "cuoctoithieu"):
            try:
                val = int(value)
                if val < 0:
                    raise ValueError()
                self.economy.set_setting("taixiu_jackpot_min_bet", str(val))
                await ctx.send(f"✅ Đã thiết lập mức cược tối thiểu để tham gia nổ hũ thành **{val:,} VND**.")
            except ValueError:
                await ctx.send("❌ **Lỗi:** Mức cược tối thiểu phải là một số nguyên dương đại diện cho số tiền VND.")
                
        elif key in ("jackpot_value", "jackpotval", "pool", "set_jackpot", "value", "hũ", "hu"):
            try:
                val = int(value)
                if val < 0:
                    raise ValueError()
                self.economy.set_setting("taixiu_jackpot", str(val))
                await ctx.send(f"✅ Đã thiết lập giá trị hũ Tài Xỉu thành **{val:,} VND**.")
            except ValueError:
                await ctx.send("❌ **Lỗi:** Giá trị hũ phải là một số nguyên dương hoặc bằng 0.")
                
        elif key in ("tax_rate", "taxrate", "tax", "phe", "phế"):
            try:
                val_str = value.strip()
                if val_str.endswith("%"):
                    rate = float(val_str[:-1].strip()) / 100.0
                else:
                    rate = float(val_str)
                
                if not (0.0 <= rate <= 1.0):
                    raise ValueError()
                    
                self.economy.set_setting("taixiu_tax_rate", str(rate))
                await ctx.send(f"✅ Đã thiết lập tỷ lệ thuế cược thắng Tài Xỉu thành **{rate * 100}%**.")
            except ValueError:
                await ctx.send("❌ **Lỗi:** Tỷ lệ thuế phải là số thập phân nằm trong khoảng từ `0.0` đến `1.0` hoặc dạng phần trăm (ví dụ: `5%` hoặc `0.05`).")
        else:
            await ctx.send(f"❌ **Lỗi:** Không hỗ trợ cấu hình cho khóa `{key}`. Chỉ hỗ trợ: `rig_rate`, `threshold`, `jackpot_rate`, `jackpot_min_bet`, `tax_rate`, `jackpot_value`, `status`.")


async def setup(client: commands.Bot):
    await client.add_cog(GamblingHelpers(client))
