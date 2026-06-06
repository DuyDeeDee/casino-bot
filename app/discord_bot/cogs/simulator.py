import asyncio
import logging
import random
import time
from uuid import uuid4
import discord
from discord.ext import commands, tasks

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.profile_renderer import render_profile_banner
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

# Business configs
BUSINESSES = {
    "iot": {
        "name": "Nha May",
        "base_cost": 50_000_000,
        "base_revenue": 500_000, # per hour
        "currency": "money"
    },
    "gym": {
        "name": "Phòng Gym Thể hình 🏋️",
        "base_cost": 100_000_000,
        "base_revenue": 1_200_000, # per hour
        "currency": "money",
        "buff": "Sinh ra 1.2M VND/giờ + Tặng giáp sức khỏe tinh thần chống nản."
    },
    "gold_shop": {
        "name": "Chuỗi Tiệm Vàng 🪙",
        "base_cost": 10, # 10 Gold (credits)
        "base_revenue": 0.1 / 24, # 0.1 Gold per day (approx 0.00416 Gold per hour)
        "currency": "gold"
    }
}

# Shop items config
SHOP_ITEMS = {
    "bang_cap": {
        "name": "Bằng cấp công nghệ 🎓",
        "cost": 10_000_000,
        "currency": "money",
        "description": "Mở khóa công việc Công nghệ trong lệnh $work để nhận dự án lớn."
    },
    "the_tho_mo": {
        "name": "Thẻ thợ mỏ VIP 🪪",
        "cost": 5,
        "currency": "gold",
        "description": "Mở khóa lệnh $mine đào quặng kiếm VND và có cơ hội nhận Vàng."
    }
}

class Simulator(commands.Cog):
    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())
        self.update_stock_prices_task.start()

    def cog_unload(self) -> None:
        self.update_stock_prices_task.cancel()

    @tasks.loop(minutes=5)
    async def update_stock_prices_task(self):
        """Fluctuates the virtual stock/crypto prices every 5 minutes."""
        try:
            prices = self.economy.get_stock_prices()
            for symbol, current_price, _, _ in prices:
                # Random walk parameters
                if symbol == "BTC":
                    # High volatility (crypto vibe)
                    change = random.uniform(-0.15, 0.15)
                    new_price = int(current_price * (1 + change))
                    new_price = max(100_000, min(10_000_000, new_price))
                elif symbol == "CASINO":
                    # Medium volatility
                    change = random.uniform(-0.08, 0.08)
                    new_price = int(current_price * (1 + change))
                    new_price = max(10_000, min(1_000_000, new_price))
                else:  # AGV
                    # Low volatility / steady
                    change = random.uniform(-0.03, 0.03)
                    new_price = int(current_price * (1 + change))
                    new_price = max(1_000, min(100_000, new_price))

                change_percent = ((new_price - current_price) / current_price) * 100
                self.economy.update_stock_price(symbol, new_price, current_price, change_percent)
            logger.info("Stock/crypto prices updated.")
        except Exception as e:
            logger.error(f"Error updating stock prices: {e}")

    @commands.command(
        brief="Hiển thị profile sành điệu dạng banner của bạn.",
        usage="profile / pf",
        aliases=["pf"]
    )
    async def profile(self, ctx: commands.Context, member: discord.Member | None = None):
        target = member or ctx.author
        if target.bot:
            await ctx.send("❌ Không thể xem profile của bot.")
            return

        async with ctx.typing():
            try:
                # Fetch data
                user_id = target.id
                profile_entry = self.economy.get_entry(user_id)
                money = profile_entry[1]
                gold = profile_entry[2]
                
                gold_price = self.economy.get_gold_price()
                loan_amount, _ = self.economy.get_loan(user_id)
                
                businesses = self.economy.get_businesses(user_id)
                biz_count = sum(lvl for biz, lvl in businesses)
                
                inventory = self.economy.get_inventory(user_id)
                inv_count = sum(qty for item, qty in inventory)
                
                # Render banner
                avatar_url = target.display_avatar.with_format("png").url
                img_buffer = await render_profile_banner(
                    username=target.name,
                    avatar_url=avatar_url,
                    money=money,
                    gold=gold,
                    gold_price=gold_price,
                    loan_amount=loan_amount,
                    biz_count=biz_count,
                    inv_count=inv_count
                )
                
                filename = f"profile-{user_id}-{uuid4().hex[:6]}.png"
                file = discord.File(fp=img_buffer, filename=filename)
                
                # Build simple embed to hold the image
                embed = make_embed(
                    title=f"💳 PROFILE CỦA {target.name.upper()}",
                    color=discord.Color.dark_theme()
                )
                embed.set_image(url=f"attachment://{filename}")
                await ctx.send(file=file, embed=embed)
                img_buffer.close()
            except Exception as e:
                logger.error(f"Failed to generate profile: {e}", exc_info=True)
                await ctx.send(f"❌ Có lỗi xảy ra khi tạo profile: {e}")

    @commands.command(
        brief="Xem cửa hàng bán bằng cấp và công cụ bổ trợ.",
        usage="shop"
    )
    async def shop(self, ctx: commands.Context):
        embed = make_embed(
            title="🛒 CỬA HÀNG CÔNG CỤ & BẰNG CẤP 🛒",
            description="Hãy trang bị thêm các thẻ hoặc bằng cấp để nâng cấp bản thân!",
            color=discord.Color.gold()
        )
        
        for item_id, details in SHOP_ITEMS.items():
            cost_str = f"{details['cost']:,} VND" if details['currency'] == "money" else f"{details['cost']} thỏi vàng"
            embed.add_field(
                name=f"📦 {details['name']} (ID: `{item_id}`)",
                value=f"💵 **Giá:** `{cost_str}`\n📝 **Mô tả:** {details['description']}",
                inline=False
            )
        embed.set_footer(text="Gõ !buyitem <item_id> để mua đồ.")
        await ctx.send(embed=embed)

    @commands.command(
        brief="Mua một vật phẩm từ cửa hàng bằng ID.",
        usage="buyitem <item_id>"
    )
    async def buyitem(self, ctx: commands.Context, item_id: str):
        if item_id not in SHOP_ITEMS:
            await ctx.send(f"❌ Vật phẩm ID `{item_id}` không tồn tại. Gõ `!shop` để xem danh sách.")
            return

        user_id = ctx.author.id
        item = SHOP_ITEMS[item_id]
        
        # Check current balance
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        gold = profile[2]
        
        if item['currency'] == "money":
            if money < item['cost']:
                await ctx.send(f"❌ Bạn không đủ tiền mặt! Cần `{item['cost']:,} VND` nhưng bạn chỉ có `{money:,} VND`.")
                return
            # Deduct VND
            self.economy.add_money(user_id, -item['cost'])
            log_wallet_change(logger, event="buy_shop_item", user_id=user_id, money_delta=-item['cost'], item_id=item_id, ctx=ctx)
        else:
            if gold < item['cost']:
                await ctx.send(f"❌ Bạn không đủ Vàng! Cần `{item['cost']}` thỏi vàng nhưng bạn chỉ có `{gold}` thỏi vàng.")
                return
            # Deduct gold
            self.economy.add_credits(user_id, -item['cost'])
            log_wallet_change(logger, event="buy_shop_item", user_id=user_id, credits_delta=-item['cost'], item_id=item_id, ctx=ctx)

        # Add item to inventory
        self.economy.add_inventory_item(user_id, item_id, 1)
        
        embed = make_embed(
            title="🎁 MUA HÀNG THÀNH CÔNG 🎁",
            description=f"Chúc mừng bạn đã sở hữu **{item['name']}**!\nĐã trừ thành công chi phí mua hàng.",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Xem các vật phẩm bạn đang sở hữu trong túi đồ.",
        usage="inventory / inv",
        aliases=["inv"]
    )
    async def inventory(self, ctx: commands.Context):
        inventory = self.economy.get_inventory(ctx.author.id)
        if not inventory or sum(qty for _, qty in inventory) == 0:
            await ctx.send("🎒 Túi đồ của bạn hiện đang trống rỗng.")
            return

        embed = make_embed(
            title=f"🎒 TÚI ĐỒ CỦA {ctx.author.name.upper()}",
            color=discord.Color.blue()
        )
        
        for item_id, qty in inventory:
            if qty > 0 and item_id in SHOP_ITEMS:
                item = SHOP_ITEMS[item_id]
                embed.add_field(
                    name=f"{item['name']}",
                    value=f"• Số lượng: **{qty}**\n• Chức năng: *{item['description']}*",
                    inline=False
                )
        await ctx.send(embed=embed)

    @commands.command(
        brief="Đào mỏ khai thác khoáng sản (Yêu cầu Thẻ thợ mỏ VIP). Cooldown 5 tiếng.",
        usage="mine"
    )
    async def mine(self, ctx: commands.Context):
        user_id = ctx.author.id
        
        # Check VIP Miner Card
        inventory = self.economy.get_inventory(user_id)
        has_card = any(item == 'the_tho_mo' and qty > 0 for item, qty in inventory)
        if not has_card:
            await ctx.send("❌ **Lỗi:** Lệnh này yêu cầu **Thẻ thợ mỏ VIP**! Hãy gõ `!shop` để mua thẻ bằng Vàng trước.")
            return

        # Check cooldown
        stats = self.economy.get_simulator_stats(user_id)
        last_mine = stats[1]
        now = int(time.time())
        cooldown = 5 * 3600 # 5 hours
        
        if now - last_mine < cooldown:
            time_left = cooldown - (now - last_mine)
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            await ctx.send(f"⏳ **Bạn đang mệt:** Hãy nghỉ ngơi! Bạn có thể tiếp tục đào mỏ sau **{hours} giờ {minutes} phút**.")
            return

        # Calculate rewards
        # Dig up scraps (VND)
        ore_money = random.randint(20_000, 100_000)
        
        # 5% chance of getting Gold (0.1 - 0.5 Gold)
        dropped_gold = 0.0
        gold_message = ""
        
        if random.random() < 0.05:
            dropped_gold = round(random.uniform(0.1, 0.5), 2)
            gold_message = f"\n✨ **ĐẶC BIỆT:** Bạn đào trúng mạch vàng và thu về **{dropped_gold}** Vàng!"

        # Process money reward
        self.economy.add_money(user_id, ore_money)
        
        # Process fractional gold reward
        total_gold_frac = stats[3] + dropped_gold
        int_gold = int(total_gold_frac)
        new_frac = round(total_gold_frac - int_gold, 4)
        
        if int_gold > 0:
            self.economy.add_credits(user_id, int_gold)
            gold_message += f" (Đã quy đổi cộng thêm `{int_gold}` thỏi vàng vào két sắt)"

        # Save stats
        self.economy.set_simulator_stats(user_id, last_mine=now, fractional_gold=new_frac)
        
        log_wallet_change(
            logger,
            event="mine_ore",
            user_id=user_id,
            money_delta=ore_money,
            credits_delta=int_gold,
            ctx=ctx,
            dropped_gold_frac=dropped_gold
        )

        embed = make_embed(
            title="⛏️ CUỘC KHAI THÁC KHOÁNG SẢN ⛏️",
            description=(
                f"Bạn đã vác cuốc vào hầm mỏ VIP làm việc cật lực...\n\n"
                f"💰 **Bán quặng sắt vụn:** `+{ore_money:,} VND`"
                f"{gold_message}\n"
                f"💳 **Vàng lẻ đang tích lũy:** `{new_frac} Vàng` (Đủ `1.0` sẽ tự đổi ra thỏi)"
            ),
            color=discord.Color.dark_green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.group(
        brief="Hệ thống quản lý tài sản và kinh doanh thụ động.",
        usage="business / biz [mua/nangcap/id]",
        aliases=["biz"],
        invoke_without_command=True
    )
    async def business(self, ctx: commands.Context):
        user_id = ctx.author.id
        owned = dict(self.economy.get_businesses(user_id))
        
        embed = make_embed(
            title="🏢 DANH SÁCH DOANH NGHIỆP CỦA BẠN 🏢",
            description="Sở hữu doanh nghiệp để nhận thu nhập thụ động mỗi giờ (Cần gõ `!collect` để thu hoạch).",
            color=discord.Color.teal()
        )
        
        # Calculate current passive yields
        stats = self.economy.get_simulator_stats(user_id)
        last_collect = stats[0]
        now = int(time.time())
        
        for biz_id, details in BUSINESSES.items():
            lvl = owned.get(biz_id, 0)
            
            # calculate upgrade costs & yields
            cost = int(details['base_cost'] * (1.5 ** lvl))
            cost_str = f"{cost:,} VND" if details['currency'] == "money" else f"{cost} thỏi vàng"
            
            revenue = details['base_revenue'] * (lvl + 1) if lvl > 0 else details['base_revenue']
            
            if details['currency'] == "money":
                rev_str = f"{revenue:,} VND/giờ"
            else:
                rev_str = f"{revenue * 24:.2f} Vàng/ngày"
                
            status = f"🟢 Đang hoạt động (Cấp {lvl})\n📈 Doanh thu hiện tại: `{rev_str}`" if lvl > 0 else "🔴 Chưa sở hữu"
            
            buff_desc = f"\n🌟 **Đặc quyền:** {details['buff']}" if 'buff' in details else ""
            
            embed.add_field(
                name=f"{details['name']}",
                value=(
                    f"• Trạng thái: {status}\n"
                    f"• Chi phí mua/nâng cấp: `{cost_str}`\n"
                    f"• Doanh thu cấp tiếp theo: "
                    f"`{details['base_revenue'] * (lvl + 1 + (1 if lvl > 0 else 0)):,} VND/giờ`" if details['currency'] == "money"
                    else f"`{(details['base_revenue'] * (lvl + 2 if lvl > 0 else 1)) * 24:.2f} Vàng/ngày`"
                    f"{buff_desc}"
                ),
                inline=False
            )
            
        # Show time elapsed
        if last_collect > 0:
            elapsed = (now - last_collect) // 60
            embed.set_footer(text=f"Đã tích lũy doanh thu trong {elapsed} phút qua. Gõ !collect để nhận.")
        else:
            embed.set_footer(text="Gõ !biz buy <id> hoặc !biz upgrade <id> để mua/nâng cấp.")
            
        await ctx.send(embed=embed)

    @business.command(name="buy", aliases=["mua", "upgrade", "up", "nangcap"])
    async def biz_buy(self, ctx: commands.Context, biz_id: str):
        if biz_id not in BUSINESSES:
            await ctx.send(f"❌ Doanh nghiệp ID `{biz_id}` không tồn tại. Các ID hợp lệ: `iot`, `gym`, `gold_shop`.")
            return

        user_id = ctx.author.id
        biz = BUSINESSES[biz_id]
        
        owned = dict(self.economy.get_businesses(user_id))
        current_lvl = owned.get(biz_id, 0)
        
        # Calculate cost
        cost = int(biz['base_cost'] * (1.5 ** current_lvl))
        
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        gold = profile[2]
        
        if biz['currency'] == "money":
            if money < cost:
                await ctx.send(f"❌ Bạn không đủ VND! Chi phí nâng cấp cấp {current_lvl + 1} là `{cost:,} VND`.")
                return
            self.economy.add_money(user_id, -cost)
            log_wallet_change(logger, event="buy_business", user_id=user_id, money_delta=-cost, biz_id=biz_id, ctx=ctx)
        else:
            if gold < cost:
                await ctx.send(f"❌ Bạn không đủ Vàng! Chi phí nâng cấp cấp {current_lvl + 1} là `{cost}` thỏi vàng.")
                return
            self.economy.add_credits(user_id, -cost)
            log_wallet_change(logger, event="buy_business", user_id=user_id, credits_delta=-cost, biz_id=biz_id, ctx=ctx)

        # Set level
        new_lvl = current_lvl + 1
        self.economy.set_business_level(user_id, biz_id, new_lvl)
        
        # If buying the first business ever, initialize last_collect
        stats = self.economy.get_simulator_stats(user_id)
        if stats[0] == 0:
            self.economy.set_simulator_stats(user_id, last_collect=int(time.time()))

        embed = make_embed(
            title="🏢 GIAO DỊCH DOANH NGHIỆP THÀNH CÔNG 🏢",
            description=f"Bạn đã nâng cấp thành công **{biz['name']}** lên **Cấp {new_lvl}**!",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Thu hoạch doanh thu thụ động từ các doanh nghiệp của bạn.",
        usage="collect / thuhoach",
        aliases=["thuhoach"]
    )
    async def collect(self, ctx: commands.Context):
        user_id = ctx.author.id
        owned = dict(self.economy.get_businesses(user_id))
        
        if not owned or sum(lvl for lvl in owned.values()) == 0:
            await ctx.send("❌ Bạn chưa sở hữu doanh nghiệp nào! Hãy dùng `!biz` để mua.")
            return

        stats = self.economy.get_simulator_stats(user_id)
        last_collect = stats[0]
        now = int(time.time())
        
        if last_collect == 0:
            self.economy.set_simulator_stats(user_id, last_collect=now)
            await ctx.send("⏱️ Đã bắt đầu tính doanh thu cho doanh nghiệp của bạn từ bây giờ.")
            return

        # Calculate time elapsed in hours
        elapsed_sec = now - last_collect
        if elapsed_sec < 60:
            await ctx.send("⏳ **Doanh thu quá nhỏ:** Hãy đợi ít nhất 1 phút để tích lũy doanh thu.")
            return
            
        # Idle cap: max 24 hours
        hours = elapsed_sec / 3600.0
        hours = min(24.0, hours)
        
        # Calculate revenue
        earned_money = 0
        earned_gold_frac = 0.0
        
        for biz_id, lvl in owned.items():
            if lvl <= 0:
                continue
            biz = BUSINESSES[biz_id]
            revenue = biz['base_revenue'] * lvl
            
            if biz['currency'] == "money":
                earned_money += int(hours * revenue)
            else:
                earned_gold_frac += hours * revenue

        total_gold_frac = stats[3] + earned_gold_frac
        int_gold = int(total_gold_frac)
        new_frac = round(total_gold_frac - int_gold, 4)
        
        if earned_money == 0 and int_gold == 0:
            await ctx.send(f"⏳ Doanh thu tích lũy hiện tại quá ít. Hãy đợi thêm (Đã trôi qua {elapsed_sec // 60} phút).")
            return

        # Distribute earnings
        if earned_money > 0:
            self.economy.add_money(user_id, earned_money)
        if int_gold > 0:
            self.economy.add_credits(user_id, int_gold)

        # Update collect stats
        # To avoid time drift, update last_collect to current time
        self.economy.set_simulator_stats(user_id, last_collect=now, fractional_gold=new_frac)
        
        log_wallet_change(
            logger,
            event="collect_passive_income",
            user_id=user_id,
            money_delta=earned_money,
            credits_delta=int_gold,
            ctx=ctx,
            elapsed_sec=elapsed_sec
        )

        gold_str = f"\n🟡 **Vàng nhận:** `+{int_gold} thỏi vàng`" if int_gold > 0 else ""
        
        embed = make_embed(
            title="🏢 BÁO CÁO DOANH THU DOANH NGHIỆP 🏢",
            description=(
                f"Sau **{elapsed_sec // 60} phút** làm việc chăm chỉ, các doanh nghiệp của bạn đã báo cáo thu hoạch:\n\n"
                f"💰 **VND nhận:** `+{earned_money:,} VND`"
                f"{gold_str}\n"
                f"💳 **Vàng lẻ tích lũy thêm:** `+{earned_gold_frac:.4f} Vàng` (Số dư dư: `{new_frac} Vàng`)"
            ),
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @commands.command(
        brief="Cướp tiền VND từ ví của người khác. Có tỷ lệ thất bại bị phạt tiền.",
        usage="rob @user"
    )
    async def rob(self, ctx: commands.Context, target: discord.Member):
        if target.bot:
            await ctx.send("❌ Không thể cướp tiền của bot!")
            return
        if target.id == ctx.author.id:
            await ctx.send("❌ Bạn không thể tự cướp tiền của chính mình!")
            return
            
        user_id = ctx.author.id
        now = int(time.time())
        cooldown = 2 * 3600 # 2 hours
        
        # Check robber cooldown
        stats = self.economy.get_simulator_stats(user_id)
        last_rob = stats[2]
        
        if now - last_rob < cooldown:
            time_left = cooldown - (now - last_rob)
            hours = time_left // 3600
            minutes = (time_left % 3600) // 60
            await ctx.send(f"⏳ **Cảnh sát đang tuần tra:** Bạn cần lẩn trốn thêm **{hours} giờ {minutes} phút** trước khi đi cướp tiếp.")
            return

        # Check target money
        target_profile = self.economy.get_entry(target.id)
        target_money = target_profile[1]
        
        if target_money < 50_000:
            await ctx.send(f"❌ **Mục tiêu quá nghèo:** {target.name} chỉ có `{target_money:,} VND` trong ví. Hãy để họ yên!")
            return

        # 40% success rate
        robber_profile = self.economy.get_entry(user_id)
        robber_money = robber_profile[1]
        
        if random.random() < 0.40:
            # Success: steal 10% - 30% of target wallet VND
            steal_pct = random.uniform(0.10, 0.30)
            steal_amount = int(target_money * steal_pct)
            
            self.economy.add_money(target.id, -steal_amount)
            self.economy.add_money(user_id, steal_amount)
            self.economy.set_simulator_stats(user_id, last_rob=now)
            
            log_wallet_change(logger, event="rob_success", user_id=user_id, money_delta=steal_amount, victim_id=target.id, ctx=ctx)
            log_wallet_change(logger, event="rob_victim", user_id=target.id, money_delta=-steal_amount, actor_id=user_id, ctx=ctx)
            
            embed = make_embed(
                title="🥷 VỤ CƯỚP THÀNH CÔNG 🥷",
                description=(
                    f"Bạn đã áp sát **{target.mention}** và giật phăng ví tiền mặt thành công!\n\n"
                    f"💰 **Số tiền cướp được:** `+{steal_amount:,} VND`\n"
                    f"🛡️ *Mẹo: Hãy đổi VND sang Vàng gấp để tránh bị người khác cướp lại!*"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)
        else:
            # Failure: get caught and fined 5% of robber money (min 50,000 VND)
            fine = int(robber_money * 0.05)
            fine = max(50_000, fine)
            fine = min(robber_money, fine) # cannot deduct more than they have
            
            if fine > 0:
                self.economy.add_money(user_id, -fine)
                self.economy.add_money(target.id, fine)
                
            self.economy.set_simulator_stats(user_id, last_rob=now)
            log_wallet_change(logger, event="rob_failed", user_id=user_id, money_delta=-fine, victim_id=target.id, ctx=ctx)
            
            embed = make_embed(
                title="🚨 VỤ CƯỚP THẤT BẠI 🚨",
                description=(
                    f"Bạn đã bị cảnh sát tóm gọn hoặc bị **{target.name}** phản kháng dữ dội!\n\n"
                    f"💸 **Bồi thường thiệt hại cho nạn nhân:** `-{fine:,} VND`"
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    @commands.group(
        brief="Đầu tư cổ phiếu & tiền điện tử biến động.",
        usage="invest [list/buy/sell]",
        invoke_without_command=True
    )
    async def invest(self, ctx: commands.Context):
        prices = self.economy.get_stock_prices()
        
        embed = make_embed(
            title="📈 THỊ TRƯỜNG CHỨNG KHOÁN & CRYPTO 📈",
            description="Tỷ giá biến động tự động mỗi 5 phút một lần. Đầu tư bằng tiền mặt VND.",
            color=discord.Color.blue()
        )
        
        user_portfolio = dict(self.economy.get_portfolio(ctx.author.id))
        
        for symbol, price, prev, change in prices:
            trend_str = "📈 TĂNG" if change > 0 else "📉 GIẢM" if change < 0 else "↔️ ỔN ĐỊNH"
            owned_shares = user_portfolio.get(symbol, 0.0)
            value = int(owned_shares * price)
            
            embed.add_field(
                name=f"{symbol} ({trend_str})",
                value=(
                    f"💵 **Giá hiện tại:** `{price:,} VND` / cổ\n"
                    f"📊 **Biến động:** `{change:+.2f}%`\n"
                    f"🎒 **Bạn đang sở hữu:** `{owned_shares:.2f}` cổ (`{value:,} VND`)"
                ),
                inline=False
            )
            
        embed.set_footer(text="Gõ !invest buy <ticker> <số lượng> hoặc !invest sell <ticker> <số lượng>")
        await ctx.send(embed=embed)

    @invest.command(name="buy", aliases=["mua"])
    async def invest_buy(self, ctx: commands.Context, symbol: str, shares: float):
        symbol = symbol.upper()
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        
        if symbol not in prices:
            await ctx.send(f"❌ Mã đầu tư `{symbol}` không tồn tại. Các mã hợp lệ: `BTC`, `CASINO`, `AGV`.")
            return
            
        if shares <= 0:
            await ctx.send("❌ Số lượng cổ phiếu mua phải lớn hơn 0.")
            return

        user_id = ctx.author.id
        price = prices[symbol]
        total_cost = int(shares * price)
        
        # Check wallet money
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        
        if money < total_cost:
            await ctx.send(f"❌ Bạn không đủ tiền mặt! Mua `{shares:.2f}` {symbol} cần `{total_cost:,} VND` nhưng bạn chỉ có `{money:,} VND`.")
            return
            
        # Process transaction
        self.economy.add_money(user_id, -total_cost)
        
        portfolio = dict(self.economy.get_portfolio(user_id))
        current_shares = portfolio.get(symbol, 0.0)
        self.economy.set_portfolio_shares(user_id, symbol, current_shares + shares)
        
        log_wallet_change(
            logger,
            event="invest_buy_shares",
            user_id=user_id,
            money_delta=-total_cost,
            symbol=symbol,
            shares_bought=shares,
            ctx=ctx
        )
        
        embed = make_embed(
            title="🟢 ĐẦU TƯ THÀNH CÔNG 🟢",
            description=(
                f"Bạn đã khớp lệnh mua thành công **{shares:.2f} {symbol}**!\n\n"
                f"💸 **Tổng chi phí:** `-{total_cost:,} VND`\n"
                f"🎒 **Số dư cổ phiếu hiện tại:** `{current_shares + shares:.2f} {symbol}`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @invest.command(name="sell", aliases=["ban"])
    async def invest_sell(self, ctx: commands.Context, symbol: str, shares: float):
        symbol = symbol.upper()
        prices = dict((row[0], row[1]) for row in self.economy.get_stock_prices())
        
        if symbol not in prices:
            await ctx.send(f"❌ Mã đầu tư `{symbol}` không tồn tại. Các mã hợp lệ: `BTC`, `CASINO`, `AGV`.")
            return
            
        if shares <= 0:
            await ctx.send("❌ Số lượng cổ phiếu bán phải lớn hơn 0.")
            return

        user_id = ctx.author.id
        portfolio = dict(self.economy.get_portfolio(user_id))
        current_shares = portfolio.get(symbol, 0.0)
        
        if current_shares < shares:
            await ctx.send(f"❌ Bạn không đủ cổ phiếu để bán! Bạn chỉ có `{current_shares:.2f} {symbol}`.")
            return
            
        # Process transaction
        price = prices[symbol]
        total_payout = int(shares * price)
        
        self.economy.set_portfolio_shares(user_id, symbol, current_shares - shares)
        self.economy.add_money(user_id, total_payout)
        
        log_wallet_change(
            logger,
            event="invest_sell_shares",
            user_id=user_id,
            money_delta=total_payout,
            symbol=symbol,
            shares_sold=shares,
            ctx=ctx
        )
        
        embed = make_embed(
            title="🔴 BÁN ĐẦU TƯ THÀNH CÔNG 🔴",
            description=(
                f"Bạn đã bán thành công **{shares:.2f} {symbol}**!\n\n"
                f"💰 **Nhận về ví:** `+{total_payout:,} VND`\n"
                f"🎒 **Số dư cổ phiếu còn lại:** `{current_shares - shares:.2f} {symbol}`"
            ),
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

async def setup(client: commands.Bot):
    await client.add_cog(Simulator(client))
