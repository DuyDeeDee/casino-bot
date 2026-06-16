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