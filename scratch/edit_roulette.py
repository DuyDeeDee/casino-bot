import os

filepath = "app/discord_bot/cogs/roulette.py"
with open(filepath, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update RouletteBetModal.on_submit
old_modal_submit = """    async def on_submit(self, interaction: discord.Interaction):
        # Handle queueing the bet
        await interaction.response.defer()
        
        user = interaction.user
        val_str = self.amount_input.value
        
        profile = self.roulette_cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.followup.send(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).",
                ephemeral=True,
            )
            return
            
        total_queued = sum(b["amount"] for b in self.roulette_cog.pending_bets.get(user.id, []))
        if total_queued + amount > current_money:
            await interaction.followup.send(
                f"❌ Bạn không đủ tiền! Số tiền hiện có: {current_money:,} VNĐ, đã cược trước đó: {total_queued:,} VNĐ, muốn cược thêm: {amount:,} VNĐ.",
                ephemeral=True,
            )
            return
            
        if user.id not in self.roulette_cog.pending_bets:
            self.roulette_cog.pending_bets[user.id] = []
        self.roulette_cog.pending_bets[user.id].append({
            "type": self.bet_type,
            "choice": self.bet_choice,
            "amount": amount
        })
        
        viet_choice = get_vietnamese_bet_name(self.bet_type, self.bet_choice)
        await interaction.followup.send(
            f"✅ Đã thêm cược **{amount:,} VNĐ** vào cửa **{viet_choice}**!",
            ephemeral=True,
        )
        await self.roulette_cog.update_lobby(user.id)"""

new_modal_submit = """    async def on_submit(self, interaction: discord.Interaction):
        # Handle queueing the bet
        await interaction.response.defer()
        
        user = interaction.user
        val_str = self.amount_input.value
        
        profile = self.roulette_cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.followup.send(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).",
                ephemeral=True,
            )
            return
            
        channel_id = interaction.channel_id
        lobby = self.roulette_cog.active_lobbies.get(channel_id)
        if not lobby:
            await interaction.followup.send(
                "❌ Bàn cược này đã hết hạn hoặc bị hủy.",
                ephemeral=True,
            )
            return
            
        user_bets = lobby["bets"].get(user.id, [])
        total_queued = sum(b["amount"] for b in user_bets)
        if total_queued + amount > current_money:
            await interaction.followup.send(
                f"❌ Bạn không đủ tiền! Số tiền hiện có: {current_money:,} VNĐ, đã cược trước đó: {total_queued:,} VNĐ, muốn cược thêm: {amount:,} VNĐ.",
                ephemeral=True,
            )
            return
            
        if user.id not in lobby["bets"]:
            lobby["bets"][user.id] = []
        lobby["bets"][user.id].append({
            "type": self.bet_type,
            "choice": self.bet_choice,
            "amount": amount
        })
        
        viet_choice = get_vietnamese_bet_name(self.bet_type, self.bet_choice)
        await interaction.followup.send(
            f"✅ Đã thêm cược **{amount:,} VNĐ** vào cửa **{viet_choice}**!",
            ephemeral=True,
        )
        await self.roulette_cog.update_lobby(channel_id)"""

# 2. Update RouletteNumberBetModal.on_submit
old_number_submit = """    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user = interaction.user
        numbers_str = self.numbers_input.value
        val_str = self.amount_input.value
        
        parsed = parse_bet_choice(numbers_str)
        if not parsed or parsed[0] != "number":
            await interaction.followup.send(
                "❌ Lựa chọn số không hợp lệ! Hãy nhập từ 1 đến 4 số từ 0 đến 36.",
                ephemeral=True,
            )
            return
            
        bet_type, bet_choice = parsed
        
        profile = self.roulette_cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.followup.send(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).",
                ephemeral=True,
            )
            return
            
        total_queued = sum(b["amount"] for b in self.roulette_cog.pending_bets.get(user.id, []))
        if total_queued + amount > current_money:
            await interaction.followup.send(
                f"❌ Bạn không đủ tiền! Số tiền hiện có: {current_money:,} VNĐ, đã cược trước đó: {total_queued:,} VNĐ, muốn cược thêm: {amount:,} VNĐ.",
                ephemeral=True,
            )
            return
            
        if user.id not in self.roulette_cog.pending_bets:
            self.roulette_cog.pending_bets[user.id] = []
        self.roulette_cog.pending_bets[user.id].append({
            "type": bet_type,
            "choice": bet_choice,
            "amount": amount
        })
        
        viet_choice = get_vietnamese_bet_name(bet_type, bet_choice)
        await interaction.followup.send(
            f"✅ Đã thêm cược **{amount:,} VNĐ** vào cửa **{viet_choice}**!",
            ephemeral=True,
        )
        await self.roulette_cog.update_lobby(user.id)"""

new_number_submit = """    async def on_submit(self, interaction: discord.Interaction):
        await interaction.response.defer()
        
        user = interaction.user
        numbers_str = self.numbers_input.value
        val_str = self.amount_input.value
        
        parsed = parse_bet_choice(numbers_str)
        if not parsed or parsed[0] != "number":
            await interaction.followup.send(
                "❌ Lựa chọn số không hợp lệ! Hãy nhập từ 1 đến 4 số từ 0 đến 36.",
                ephemeral=True,
            )
            return
            
        bet_type, bet_choice = parsed
        
        profile = self.roulette_cog.economy.get_entry(user.id)
        current_money = profile[1]
        
        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.followup.send(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 10000, 50k).",
                ephemeral=True,
            )
            return
            
        channel_id = interaction.channel_id
        lobby = self.roulette_cog.active_lobbies.get(channel_id)
        if not lobby:
            await interaction.followup.send(
                "❌ Bàn cược này đã hết hạn hoặc bị hủy.",
                ephemeral=True,
            )
            return
            
        user_bets = lobby["bets"].get(user.id, [])
        total_queued = sum(b["amount"] for b in user_bets)
        if total_queued + amount > current_money:
            await interaction.followup.send(
                f"❌ Bạn không đủ tiền! Số tiền hiện có: {current_money:,} VNĐ, đã cược trước đó: {total_queued:,} VNĐ, muốn cược thêm: {amount:,} VNĐ.",
                ephemeral=True,
            )
            return
            
        if user.id not in lobby["bets"]:
            lobby["bets"][user.id] = []
        lobby["bets"][user.id].append({
            "type": bet_type,
            "choice": bet_choice,
            "amount": amount
        })
        
        viet_choice = get_vietnamese_bet_name(bet_type, bet_choice)
        await interaction.followup.send(
            f"✅ Đã thêm cược **{amount:,} VNĐ** vào cửa **{viet_choice}**!",
            ephemeral=True,
        )
        await self.roulette_cog.update_lobby(channel_id)"""

# 3. Update the lobby command invocation in `rl`
old_rl_lobby = """        # If no arguments are provided, open the interactive lobby
        if bet_choice_raw is None:
            # Clear previous pending bets to start fresh when opening lobby
            if user_id in self.pending_bets:
                del self.pending_bets[user_id]
            lucky_number = get_daily_lucky_number(user_id)
            desc = (
                f"Chào mừng bạn đến với **Roulette Châu Âu** 🎡\\n\\n"
                f"🍀 Số may mắn của bạn hôm nay: **{lucky_number}** (Thưởng x40 khi cược đơn trúng!)\\n"
                f"👑 VIP Rank của bạn: {vip['emoji']} **{vip['title']}**\\n"
                f"💰 Giới hạn cược: Không giới hạn\\n"
                f"⚡ Chip May Mắn hiện tại: **{stats['chips']}/10**\\n\\n"
                f"Hãy chọn nút cược bên dưới hoặc đặt cược nhanh bằng lệnh:\\n"
                f"`{ctx.prefix}rl đỏ 10k`\\n"
                f"`{ctx.prefix}rl 17 50k`\\n"
                f"`{ctx.prefix}rl 7 11 15 20 100k`"
            )
            embed = make_embed(
                title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰",
                description=desc,
                color=discord.Color.dark_theme(),
            )
            view = RouletteLobbyView(user_id, self)
            msg = await ctx.send(embed=embed, view=view)
            self.active_lobbies[user_id] = msg
            return"""

# Quick replacement string for raw embed
old_rl_lobby_clean = """        # If no arguments are provided, open the interactive lobby
        if bet_choice_raw is None:
            # Clear previous pending bets to start fresh when opening lobby
            if user_id in self.pending_bets:
                del self.pending_bets[user_id]
            lucky_number = get_daily_lucky_number(user_id)
            desc = (
                f"Chào mừng bạn đến với **Roulette Châu Âu** 🎡\\n\\n"
                f"🍀 Số may mắn của bạn hôm nay: **{lucky_number}** (Thưởng x40 khi cược đơn trúng!)\\n"
                f"👑 VIP Rank của bạn: {vip['emoji']} **{vip['title']}**\\n"
                f"💰 Giới hạn cược: Không giới hạn\\n"
                f"⚡ Chip May Mắn hiện tại: **{stats['chips']}/10**\\n\\n"
                f"Hãy chọn nút cược bên dưới hoặc đặt cược nhanh bằng lệnh:\\n"
                f"`{ctx.prefix}rl đỏ 10k`\\n"
                f"`{ctx.prefix}rl 17 50k`\\n"
                f"`{ctx.prefix}rl 7 11 15 20 100k`"
            )
            embed = make_embed(
                title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰",
                description=desc,
                color=discord.Color.dark_theme(),
            )
            view = RouletteLobbyView(user_id, self)
            msg = await ctx.send(embed=embed, view=view)
            self.active_lobbies[user_id] = msg
            return"""

new_rl_lobby = """        # If no arguments are provided, open the interactive lobby
        if bet_choice_raw is None:
            channel_id = ctx.channel.id
            if channel_id in self.active_lobbies:
                existing_msg = self.active_lobbies[channel_id].get("message")
                url = existing_msg.jump_url if existing_msg else ""
                await ctx.send(f"❌ Đã có một bàn Roulette đang hoạt động trong kênh này! {url}")
                return
                
            lucky_number = get_daily_lucky_number(user_id)
            desc = (
                f"Chào mừng bạn đến với **Roulette Châu Âu (Bàn Multiplayer)** 🎡\\n\\n"
                f"🍀 Số may mắn của bạn hôm nay: **{lucky_number}** (Thưởng x40 khi cược đơn trúng!)\\n"
                f"👑 VIP Rank của bạn: {vip['emoji']} **{vip['title']}**\\n"
                f"💰 Giới hạn cược: Không giới hạn\\n"
                f"⚡ Chip May Mắn hiện tại: **{stats['chips']}/10**\\n\\n"
                f"Mọi người hãy chọn nút cược bên dưới hoặc đặt cược nhanh bằng lệnh:\\n"
                f"`{ctx.prefix}rl add đỏ 10k`\\n"
                f"`{ctx.prefix}rl add 17 50k`\\n"
                f"`{ctx.prefix}rl add 7 11 15 20 100k`"
            )
            embed = make_embed(
                title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰",
                description=desc,
                color=discord.Color.dark_theme(),
            )
            view = RouletteLobbyView(channel_id, user_id, self)
            msg = await ctx.send(embed=embed, view=view)
            self.active_lobbies[channel_id] = {
                "message": msg,
                "host_id": user_id,
                "bets": {}
            }
            return"""

# 4. Replace from add_command to end of file
old_commands_block_start = '    @commands.command(name="add", brief="Thêm một cược vào phiếu cược hiện tại", usage="add [cửa_cược] [tiền_cược]")'
# Let's find the old block start index
idx = content.find(old_commands_block_start)
if idx == -1:
    print("Error: Could not find commands block start!")
    exit(1)

content_before_commands = content[:idx]

new_commands_block = """    @commands.command(name="add", brief="Thêm một cược vào phiếu cược hiện tại", usage="add [cửa_cược] [tiền_cược]")
    async def add_command(self, ctx: commands.Context, bet_choice_raw: str, bet_amount_raw: str, *extra_numbers):
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        
        lobby = self.active_lobbies.get(channel_id)
        if not lobby:
            await ctx.send("❌ **Lỗi:** Không có bàn cược Roulette nào đang mở trong kênh này. Hãy dùng `i?rl` để mở bàn.")
            return

        all_args = [bet_choice_raw, bet_amount_raw] + list(extra_numbers)
        bet_amount_str = all_args[-1]
        bet_choices_str = " ".join(all_args[:-1])
        
        parsed = parse_bet_choice(bet_choices_str)
        if not parsed:
            # try swapping
            bet_amount_str = all_args[0]
            bet_choices_str = " ".join(all_args[1:])
            parsed = parse_bet_choice(bet_choices_str)
            if not parsed:
                await ctx.send("❌ **Lỗi:** Cửa cược không hợp lệ!")
                return
                
        bet_type, bet_choice = parsed
        profile = self.economy.get_entry(user_id)
        current_money = profile[1]
        
        amount = parse_bet_amount(bet_amount_str, current_money)
        if amount <= 0:
            await ctx.send("❌ **Lỗi:** Số tiền cược không hợp lệ!")
            return
            
        user_bets = lobby["bets"].get(user_id, [])
        total_queued = sum(b["amount"] for b in user_bets)
        if total_queued + amount > current_money:
            await ctx.send(f"❌ Bạn không đủ tiền! Số tiền hiện có: {current_money:,} VNĐ, đã cược trước đó: {total_queued:,} VNĐ.")
            return
            
        if user_id not in lobby["bets"]:
            lobby["bets"][user_id] = []
        lobby["bets"][user_id].append({
            "type": bet_type,
            "choice": bet_choice,
            "amount": amount
        })
        
        viet_choice = get_vietnamese_bet_name(bet_type, bet_choice)
        await ctx.send(f"✅ Đã thêm cược **{amount:,} VNĐ** vào cửa **{viet_choice}**!")
        
        # Update lobby if active
        await self.update_lobby(channel_id)

    @commands.command(name="spin", brief="Quay bàn Roulette với các cược đã đặt", aliases=["quay"])
    async def spin_command(self, ctx: commands.Context):
        channel_id = ctx.channel.id
        lobby = self.active_lobbies.get(channel_id)
        if not lobby:
            await ctx.send("❌ **Lỗi:** Không có bàn cược Roulette nào đang mở trong kênh này. Hãy dùng `i?rl` để mở bàn.")
            return
            
        if ctx.author.id != lobby["host_id"]:
            await ctx.send("❌ **Lỗi:** Chỉ chủ bàn mới có thể quay bàn xoay!")
            return
            
        if not lobby["bets"] or not any(len(b) > 0 for b in lobby["bets"].values()):
            await ctx.send("❌ **Lỗi:** Chưa có ai đặt cược trên bàn này!")
            return
            
        await self.run_multi_spin(ctx, ctx.author, lobby)

    @commands.command(name="clear", brief="Hủy toàn bộ cược của bạn trong phiếu cược", aliases=["huy", "huycuoc"])
    async def clear_command(self, ctx: commands.Context):
        user_id = ctx.author.id
        channel_id = ctx.channel.id
        lobby = self.active_lobbies.get(channel_id)
        if not lobby:
            await ctx.send("❌ **Lỗi:** Không có bàn cược Roulette nào đang mở trong kênh này.")
            return
            
        if user_id in lobby["bets"]:
            del lobby["bets"][user_id]
            await ctx.send("🧹 Đã hủy toàn bộ cược của bạn tại bàn này.")
            await self.update_lobby(channel_id)
        else:
            await ctx.send("❌ Bạn chưa đặt cược nào tại bàn này để hủy.")

    async def update_lobby(self, channel_id: int):
        lobby = self.active_lobbies.get(channel_id)
        if not lobby:
            return
            
        msg = lobby["message"]
        if not msg:
            return
            
        # Build description showing all bets
        host_id = lobby["host_id"]
        bets_dict = lobby["bets"]
        
        # Check if there are any bets overall
        has_any_bets = any(len(b) > 0 for b in bets_dict.values())
        
        if not has_any_bets:
            stats = self.economy.get_roulette(host_id)
            vip = get_user_vip(stats)
            lucky_number = get_daily_lucky_number(host_id)
            
            desc = (
                f"Chào mừng bạn đến với **Roulette Châu Âu (Bàn Multiplayer)** 🎡\\n\\n"
                f"🍀 Số may mắn của chủ bàn hôm nay: **{lucky_number}**\\n"
                f"👑 VIP Rank của chủ bàn: {vip['emoji']} **{vip['title']}**\\n"
                f"💰 Giới hạn cược: Không giới hạn\\n"
                f"⚡ Chip May Mắn chủ bàn: **{stats['chips']}/10**\\n\\n"
                f"Mọi người hãy chọn nút cược bên dưới hoặc đặt cược nhanh bằng lệnh:\\n"
                f"`i?rl add đỏ 10k`\\n"
                f"`i?rl add 17 50k`\\n"
                f"`i?rl add 7 11 15 20 100k`"
            )
        else:
            bet_list_str = ""
            total_table_bet = 0
            for u_id, u_bets in bets_dict.items():
                if not u_bets:
                    continue
                user_total = sum(b["amount"] for b in u_bets)
                total_table_bet += user_total
                
                # Fetch user name or mention
                user_mention = f"<@{u_id}>"
                
                user_bets_strs = []
                for b in u_bets:
                    viet_choice = get_vietnamese_bet_name(b["type"], b["choice"])
                    user_bets_strs.append(f"{viet_choice} (`{b['amount']:,}` VNĐ)")
                
                bet_list_str += f"• {user_mention}: {', '.join(user_bets_strs)} — **Tổng: `{user_total:,}` VNĐ**\\n"
                
            desc = (
                f"🎡 **Roulette Châu Âu - BÀN CƯỢC MULTIPLAYER** 🎡\\n\\n"
                f"🎟️ **CÁC CỬA CƯỢC ĐÃ ĐẶT:**\\n"
                f"{bet_list_str}\\n"
                f"💰 **Tổng tiền cược cả bàn:** `{total_table_bet:,} VNĐ`\\n\\n"
                f"Chủ bàn bấm nút **Quay Bàn Xoay 🎡** để bắt đầu quay, hoặc người chơi bấm **Hủy Cược Của Tôi ❌** để rút cược."
            )
            
        view = RouletteLobbyView(channel_id, host_id, self)
        embed = make_embed(
            title="🎰 BÀN QUAY ROULETTE CHÂU ÂU 🎰",
            description=desc,
            color=discord.Color.dark_theme() if not has_any_bets else discord.Color.green(),
        )
        try:
            await msg.edit(embed=embed, view=view)
        except Exception as e:
            logger.error(f"Error updating lobby message: {e}")

    async def run_multi_spin(self, ctx_or_interaction, host, lobby: dict):
        channel_id = lobby["message"].channel.id if lobby["message"] else ctx_or_interaction.channel.id
        
        # Calculate valid participants and their bets
        valid_bets_by_user = {}
        users_to_warn = []
        total_table_bet = 0
        
        for u_id, u_bets in list(lobby["bets"].items()):
            if not u_bets:
                continue
            u_total = sum(b["amount"] for b in u_bets)
            
            # Check player's money at spin time
            u_profile = self.economy.get_entry(u_id)
            current_money = u_profile[1] if u_profile else 0
            
            if current_money < u_total:
                users_to_warn.append(u_id)
            else:
                valid_bets_by_user[u_id] = u_bets
                total_table_bet += u_total
                
                # Deduct money
                self.economy.add_money(u_id, -u_total)
                log_wallet_change(
                    logger,
                    event="roulette_place_multi_bet",
                    user_id=u_id,
                    money_delta=-u_total,
                    total_bet=u_total,
                )

        if not valid_bets_by_user:
            if isinstance(ctx_or_interaction, discord.Interaction):
                await ctx_or_interaction.followup.send("❌ Không có người chơi nào đủ tiền để quay bàn xoay!", ephemeral=True)
            else:
                await ctx_or_interaction.send("❌ Không có người chơi nào đủ tiền để quay bàn xoay!")
            # Clean up the lobby since it can't proceed
            if channel_id in self.active_lobbies:
                del self.active_lobbies[channel_id]
            return

        # Spin animation setup
        participants_mentions = ", ".join(f"<@{u_id}>" for u_id in valid_bets_by_user.keys())
        spinning_embed = make_embed(
            title="🎡 ROULETTE ĐANG QUAY... 🎡",
            description=(
                f"👥 Người chơi: {participants_mentions}\\n"
                f"🎟️ Đang quay bàn cược với **{len(valid_bets_by_user)}** người chơi...\\n"
                f"💰 Tổng cược toàn bàn: **{total_table_bet:,} VNĐ**\\n\\n"
                f"⚡ *Bàn xoay đang quay tròn...*\\n"
                f"⚫🔴⚫🔴🟢⚫🔴⚫🔴⚫🔴🟢⚫🔴"
            ),
            color=discord.Color.dark_theme(),
        )
        
        if isinstance(ctx_or_interaction, discord.Interaction):
            msg = await ctx_or_interaction.followup.send(embed=spinning_embed)
        else:
            msg = await ctx_or_interaction.send(embed=spinning_embed)

        await asyncio.sleep(1.5)
        
        # Slowing down animation
        slowing_embed = make_embed(
            title="🎡 VÒNG QUAY ĐANG CHẬM DẦN... 🎡",
            description=(
                f"👥 Người chơi: {participants_mentions}\\n"
                f"🎟️ Đang quay bàn cược với **{len(valid_bets_by_user)}** người chơi...\\n"
                f"💰 Tổng cược toàn bàn: **{total_table_bet:,} VNĐ**\\n\\n"
                f"⚡ *Bóng đang nhảy quanh các ô...*\\n"
                f"🟢⚫🔴⚫🔴🟢⚫🔴"
            ),
            color=discord.Color.dark_theme(),
        )
        await msg.edit(embed=slowing_embed)
        
        await asyncio.sleep(1.5)
        
        # Final result calculation
        rolled_num = random.randint(0, 36)
        desc_rolled = describe_number(rolled_num)
        
        # Process payouts for each player
        results_desc_parts = []
        overall_net_profit = 0
        
        for u_id, u_bets in valid_bets_by_user.items():
            user = self.client.get_user(u_id)
            user_display = user.display_name if user else f"ID: {u_id}"
            
            stats = self.economy.get_roulette(u_id)
            lucky_number = get_daily_lucky_number(u_id)
            
            u_total_bet = sum(b["amount"] for b in u_bets)
            u_total_payout = 0
            u_total_profit = 0
            any_won = False
            details_logs = []
            
            for b in u_bets:
                won = check_win(b["type"], b["choice"], rolled_num)
                viet_choice = get_vietnamese_bet_name(b["type"], b["choice"])
                
                if won:
                    any_won = True
                    multiplier = get_payout_multiplier(b["type"], b["choice"], lucky_number)
                    base_payout = b["amount"] * multiplier
                    
                    # Chip bonus
                    chip_bonus_percent = stats["chips"] * 0.005
                    chip_bonus = int(base_payout * chip_bonus_percent)
                    
                    payout = base_payout + chip_bonus
                    p_profit = payout - b["amount"]
                    
                    u_total_payout += payout
                    u_total_profit += p_profit
                    
                    bonus_str = f" (+{chip_bonus:,} VNĐ từ {stats['chips']} Chip)" if chip_bonus > 0 else ""
                    details_logs.append(f"  🟢 **{viet_choice}** (Cược: `{b['amount']:,}`): **Thắng!** +`{payout:,}` VNĐ{bonus_str}")
                else:
                    p_profit = -b["amount"]
                    u_total_profit += p_profit
                    details_logs.append(f"  🔴 **{viet_choice}** (Cược: `{b['amount']:,}`): **Thua!**")
            
            overall_net_profit += u_total_profit
            
            # Update chip count
            new_chips_count = stats["chips"]
            if any_won:
                new_chips_count = 0
                if u_total_payout > 0:
                    self.economy.add_money(u_id, u_total_payout)
                    log_wallet_change(
                        logger,
                        event="roulette_multi_payout_win",
                        user_id=u_id,
                        money_delta=u_total_payout,
                        payout=u_total_payout,
                        profit=u_total_profit,
                    )
            else:
                if stats["chips"] < 10:
                    new_chips_count = stats["chips"] + 1
                log_wallet_change(
                    logger,
                    event="roulette_multi_payout_lose",
                    user_id=u_id,
                    money_delta=0,
                    profit=u_total_profit,
                )
                
            # Update database stats
            plays_delta = 1
            won_round = u_total_profit > 0
            wins_delta = 1 if won_round else 0
            losses_delta = 0 if won_round else 1
            
            new_streak = stats["streak"] + 1 if won_round else 0
            new_max_streak = max(stats["max_streak"], new_streak)
            
            num_stats = stats.get("number_stats", {})
            num_str = str(rolled_num)
            num_stats[num_str] = num_stats.get(num_str, 0) + 1
            
            temp_stats_for_check = {
                "plays": stats["plays"] + plays_delta,
                "wins": stats["wins"] + wins_delta,
                "losses": stats["losses"] + losses_delta,
                "streak": new_streak,
                "max_streak": new_max_streak,
                "achievements": stats["achievements"],
            }
            
            all_ach, newly_unlocked = check_achievements(
                temp_stats_for_check,
                "multi",
                "multi",
                u_total_bet,
                rolled_num,
                lucky_number,
                won_round,
            )
            
            self.economy.update_roulette(
                u_id,
                plays=plays_delta,
                wins=wins_delta,
                losses=losses_delta,
                profit=u_total_profit,
                streak=new_streak,
                max_streak=new_max_streak,
                chips=new_chips_count,
                number_stats=num_stats,
                achievements=all_ach,
            )
            
            # Format results for this player
            user_res_str = f"👤 **{user_display}**:\\n" + "\\n".join(details_logs) + "\\n"
            if u_total_profit > 0:
                user_res_str += f"  💰 **Tổng thực nhận:** `+{u_total_profit:,} VNĐ`"
            elif u_total_profit < 0:
                user_res_str += f"  💸 **Tổng thực nhận:** `{u_total_profit:,} VNĐ` (Tích lũy 1 chip, hiện có: **{new_chips_count}/10**)"
            else:
                user_res_str += f"  ⚖️ **Tổng thực nhận:** `0 VNĐ`"
                
            if newly_unlocked:
                user_res_str += f"\\n  🏆 *Thành tựu mới:* {', '.join(newly_unlocked)}"
            
            results_desc_parts.append(user_res_str)

        # Append warnings for skipped players
        if users_to_warn:
            warn_mentions = ", ".join(f"<@{u_id}>" for u_id in users_to_warn)
            results_desc_parts.append(f"\\n⚠️ **Bị bỏ qua do không đủ tiền:** {warn_mentions}")

        embed_color = discord.Color.green() if overall_net_profit > 0 else (discord.Color.red() if overall_net_profit < 0 else discord.Color.light_grey())
        emoji_title = "🎉 KẾT QUẢ VÒNG QUAY 🎉"
        
        results_str = "\\n".join(results_desc_parts)
        desc = (
            f"🎡 **Bóng đã dừng tại ô:** {desc_rolled}\\n\\n"
            f"📋 **BẢNG KẾT QUẢ CHI TIẾT:**\\n"
            f"{results_str}\\n\\n"
            f"--- \\n"
            f"💰 **Tổng cược bàn:** `{total_table_bet:,} VNĐ`\\n"
            f"📈 **Tổng lợi nhuận cả bàn:** `{overall_net_profit:+,} VNĐ`\\n"
        )
        
        embed = make_embed(
            title=f"{emoji_title} ROULETTE MULTIPLAYER {emoji_title}",
            description=desc,
            color=embed_color,
        )
        
        await msg.edit(embed=embed)
        
        # Clear queued state
        if channel_id in self.active_lobbies:
            del self.active_lobbies[channel_id]


async def setup(client: commands.Bot):
    await client.add_cog(Roulette(client))
"""

# Let's perform replacements in the first part:
content_before_commands = content_before_commands.replace(old_modal_submit, new_modal_submit)
content_before_commands = content_before_commands.replace(old_number_submit, new_number_submit)
content_before_commands = content_before_commands.replace(old_rl_lobby, new_rl_lobby)
content_before_commands = content_before_commands.replace(old_rl_lobby_clean, new_rl_lobby)

new_content = content_before_commands + new_commands_block

# Let's verify compilation
try:
    compile(new_content, filepath, "exec")
    print("Compilation check: OK")
except Exception as e:
    print("Compilation error:", e)
    exit(1)

with open(filepath, "w", encoding="utf-8") as f:
    f.write(new_content)
print("File written successfully!")
