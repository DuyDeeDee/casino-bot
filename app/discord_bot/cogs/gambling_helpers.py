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
        brief=f"Nhận {(config.bot.default_bet*config.bot.bonus_multiplier):,} VND miễn phí mỗi {config.bot.bonus_cooldown} giờ",
        usage="add",
    )
    @commands.cooldown(1, config.bot.bonus_cooldown * 3600, type=commands.BucketType.user)
    async def add(self, ctx: commands.Context):
        amount = config.bot.default_bet * config.bot.bonus_multiplier
        self.economy.add_money(ctx.author.id, amount)
        log_wallet_change(
            logger,
            event="bonus_add",
            user_id=ctx.author.id,
            money_delta=amount,
            ctx=ctx,
        )
        await ctx.send(f"Đã cộng thêm {amount:,} VND! Quay lại sau {config.bot.bonus_cooldown} giờ nhé.")

    @commands.command(
        brief="Xem số tiền bạn hoặc người khác đang có",
        usage="money [@thành_viên]",
        aliases=["credits", "vang", "gold"],
    )
    async def money(self, ctx: commands.Context, user: discord.Member | None = None):
        target_user = user or ctx.author
        profile = self.economy.get_entry(target_user.id)
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
        brief="Làm việc để kiếm tiền (hoặc bị mất tiền nếu gặp xui xẻo)",
        usage="work",
    )
    @commands.cooldown(1, 3600, type=commands.BucketType.user)  # 1 tiếng cooldown (3600 giây)
    async def work(self, ctx: commands.Context):
        # Lấy thông tin tài khoản người chơi
        profile = self.economy.get_entry(ctx.author.id)
        current_money = profile[1]

        # Kiểm tra bằng cấp công nghệ
        inventory = self.economy.get_inventory(ctx.author.id)
        has_degree = any(item == 'bang_cap' and qty > 0 for item, qty in inventory)
        
        if has_degree:
            # Kỹ thuật công nghệ (Kiếm nhiều VND, có rủi ro hỏng hóc)
            # Rủi ro 10%
            if random.random() < 0.10:
                penalty = 500_000
                actual_deduction = min(current_money, penalty)
                self.economy.add_money(ctx.author.id, -penalty)
                
                log_wallet_change(
                    logger,
                    event="work_tech_badluck",
                    user_id=ctx.author.id,
                    money_delta=-actual_deduction,
                    ctx=ctx,
                )
                new_balance = self.economy.get_entry(ctx.author.id)[1]
                embed = make_embed(
                    title="🔥 SỰ CỐ CÔNG NGHỆ! 🔥",
                    description=(
                        f"**{ctx.author.name}** gặp sự cố kỹ thuật:\n"
                        f"👉 *\"Bạn làm chập cháy mạch, phải đền bù 500,000 VND.\"*\n\n"
                        f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                        f"💳 **Số dư mới:** `{new_balance:,} VND`"
                     ),
                     color=discord.Color.red(),
                )
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
                await ctx.send(embed=embed)
                return
            else:
                # Thành công (90%)
                tech_jobs = [
                    ("Thiết kế cho công ty khởi nghiệp 🛠️", 1_500_000),
                    ("Setup thành công server cho khách hàng 🎮", 800_000),
                    ("Phát triển ứng dụng Mobile mini cho shop quần áo 📱", 1_200_000),
                    ("Khắc phục sự cố mạng doanh nghiệp trong đêm 🌐", 1_000_000)
                ]
                job_desc, reward = random.choice(tech_jobs)
                self.economy.add_money(ctx.author.id, reward)
                
                log_wallet_change(
                    logger,
                    event="work_tech_success",
                    user_id=ctx.author.id,
                    money_delta=reward,
                    ctx=ctx,
                )
                new_balance = self.economy.get_entry(ctx.author.id)[1]
                embed = make_embed(
                    title="💻 DỰ ÁN CÔNG NGHỆ THÀNH CÔNG! 💻",
                    description=(
                        f"**{ctx.author.name}** đã hoàn thành dự án:\n"
                        f"👉 *\"{job_desc}\"*\n\n"
                        f"💰 **Thu nhập:** `+{reward:,} VND`\n"
                        f"💳 **Số dư mới:** `{new_balance:,} VND`"
                    ),
                    color=discord.Color.blue(),
                )
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
                await ctx.send(embed=embed)
                return

        # Quay ngẫu nhiên tỉ lệ phần trăm
        rand_val = random.random()

        if rand_val < 0.10:
            # 1. Sự kiện đặc biệt (10%)
            special_scenarios = [
                "Làm trai bao được phú bà bao nuôi 💖",
                "Làm sugar baby ngoan ngoãn 🧸",
                "Vô tình cứu được chủ tịch giả danh và cái kết 🤵"
            ]
            scenario = random.choice(special_scenarios)
            reward = random.randint(1_000_000, 5_000_000)
            
            # Cộng tiền vào tài khoản
            self.economy.add_money(ctx.author.id, reward)
            
            log_wallet_change(
                logger,
                event="work_special_event",
                user_id=ctx.author.id,
                money_delta=reward,
                ctx=ctx,
            )

            new_balance = self.economy.get_entry(ctx.author.id)[1]

            embed = make_embed(
                title="🎰 SỰ KIỆN ĐẶC BIỆT! 🎰",
                description=(
                    f"**{ctx.author.name}** đã trúng sự kiện đặc biệt:\n"
                    f"👉 *\"{scenario}\"*\n\n"
                    f"💰 **Phần thưởng:** `+{reward:,} VND`\n"
                    f"💳 **Số dư mới:** `{new_balance:,} VND`"
                ),
                color=discord.Color.gold(), # Màu vàng
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

        else:
            # 90% Làm việc bình thường
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
                self.economy.add_money(ctx.author.id, reward)
                
                log_wallet_change(
                    logger,
                    event="work_normal_success",
                    user_id=ctx.author.id,
                    money_delta=reward,
                    ctx=ctx,
                )

                new_balance = self.economy.get_entry(ctx.author.id)[1]

                embed = make_embed(
                    title="💼 Đi làm chăm chỉ 💼",
                    description=(
                        f"**{ctx.author.name}** đã đi làm: *{job}*\n\n"
                        f"💰 **Thu nhập:** `+{reward:,} VND`\n"
                        f"💳 **Số dư mới:** `{new_balance:,} VND`"
                    ),
                    color=discord.Color.green(), # Màu xanh lá
                )
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
                await ctx.send(embed=embed)
                
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
                self.economy.add_money(ctx.author.id, -penalty)
                
                log_wallet_change(
                    logger,
                    event="work_normal_badluck",
                    user_id=ctx.author.id,
                    money_delta=-actual_deduction,
                    ctx=ctx,
                )

                new_balance = self.economy.get_entry(ctx.author.id)[1]

                embed = make_embed(
                    title="❌ Hôm nay quá xui xẻo! ❌",
                    description=(
                        f"**{ctx.author.name}** gặp vận xui:\n"
                        f"👉 *{scenario}*\n\n"
                        f"💸 **Thất thoát:** `-{actual_deduction:,} VND`\n"
                        f"💳 **Số dư mới:** `{new_balance:,} VND`"
                    ),
                    color=discord.Color.red(), # Màu đỏ
                )
                embed.set_thumbnail(url=ctx.author.display_avatar.url)
                await ctx.send(embed=embed)

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
            title="🟡 CHUYỂN VÀNG THÀNH CÔNG 🟡",
            description=(
                f"**{ctx.author.mention}** đã chuyển thành công **{amount:,}** thỏi vàng cho **{target.mention}**!\n\n"
                f"💳 **Số dư mới của bạn:** `{self.economy.get_entry(ctx.author.id)[2]:,}` thỏi vàng"
            ),
            color=discord.Color.gold(),
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(client: commands.Bot):
    await client.add_cog(GamblingHelpers(client))
