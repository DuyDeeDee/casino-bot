# -*- coding: utf-8 -*-
import sys

sim_path = "app/discord_bot/cogs/simulator.py"

with open(sim_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Update ChestSelect options
old_options = """        options = [
            discord.SelectOption(label="Trứng Thường - 500k", value="egg_thuong", description="Triệu hồi nhân vật Thường -> Quý", emoji="🥚"),
            discord.SelectOption(label="Trứng Cao Cấp - 2M", value="egg_caocap", description="Triệu hồi nhân vật R Rare -> Huyền Thoại", emoji="🥚"),
            discord.SelectOption(label="Trứng Hoàng Kim - 10M", value="egg_hoangkim", description="Triệu hồi nhân vật SR Super Rare -> Thần Kê", emoji="🥚"),
            
            discord.SelectOption(label="Rương Vật Phẩm Thường - 100k", value="chest_thuong", description="Mở trang bị nhân vật Thường -> Quý", emoji="📦"),
            discord.SelectOption(label="Rương Vật Phẩm Cao Cấp - 1M", value="chest_caocap", description="Mở trang bị nhân vật Hiếm -> Huyền Thoại", emoji="📦"),
            discord.SelectOption(label="Rương Vật Phẩm Hoàng Kim - 5M", value="chest_hoangkim", description="Mở trang bị nhân vật Quý -> Thần Kê", emoji="📦"),
            
            discord.SelectOption(label="Garage Box Xe - 100k", value="box_garage", description="Mở xe Common -> Epic", emoji="🏎️"),
            discord.SelectOption(label="Premium Box Xe - 1M", value="box_premium", description="Mở xe Rare -> Mythic", emoji="🏎️"),
            discord.SelectOption(label="Luxury Box Xe - 10M", value="box_luxury", description="Mở xe Epic -> Exclusive", emoji="🏎️"),
        ]"""

new_options = """        options = [
            discord.SelectOption(label="Banner Thường - 1M", value="banner_thuong", description="Triệu hồi nhân vật C -> SS", emoji="🔮"),
            discord.SelectOption(label="Banner Xịn - 5M", value="banner_xin", description="Triệu hồi nhân vật B -> SS (Bảo hiểm 50)", emoji="🔮"),
            
            discord.SelectOption(label="Garage Box Xe - 100k", value="box_garage", description="Mở xe Common -> Epic", emoji="🏎️"),
            discord.SelectOption(label="Premium Box Xe - 1M", value="box_premium", description="Mở xe Rare -> Mythic", emoji="🏎️"),
            discord.SelectOption(label="Luxury Box Xe - 10M", value="box_luxury", description="Mở xe Epic -> Exclusive", emoji="🏎️"),
        ]"""

if old_options not in content:
    # Try with different line breaks or spaces
    old_options_clean = old_options.replace(" ", "").replace("\n", "")
    content_clean = content.replace(" ", "").replace("\n", "")
    if old_options_clean not in content_clean:
        print("Error: Could not locate old ChestSelect options!")
        sys.exit(1)
else:
    content = content.replace(old_options, new_options)

# 2. Update default selected option in ChestOpenView
content = content.replace('self.selected_option = "egg_thuong"', 'self.selected_option = "banner_thuong"')

# 3. Update ChestOpenView.get_embed details
old_details = """        details = {
            "egg_thuong": ("🔮 Thẻ Triệu Hồi Thường", 500_000, "Triệu hồi nhân vật. Tỷ lệ: N Common (70%), R Rare (24.8%), SR Super Rare (5%), UR (0.19%), LR Legend (0.01%)."),
            "egg_caocap": ("🔮 Thẻ Triệu Hồi Cao Cấp", 2_000_000, "Triệu hồi nhân vật. Tỷ lệ: R Rare (50%), SR Super Rare (35%), SSR (13.9%), UR (1%), LR Legend (0.1%)."),
            "egg_hoangkim": ("🔮 Thẻ Triệu Hồi Hoàng Kim", 10_000_000, "Triệu hồi nhân vật. Tỷ lệ: SR Super Rare (45%), SSR (40%), UR (12%), LR Legend (3%). Hỗ trợ bảo hiểm (pity) 30 lần."),

            "chest_thuong": ("📦 Rương Vật Phẩm Thường", 100_000, "Mở trang bị Anime. Cơ hội nhận trang bị từ Common đến Noble."),
            "chest_caocap": ("📦 Rương Vật Phẩm Cao Cấp", 1_000_000, "Mở trang bị Anime. Cơ hội nhận trang bị từ Rare đến Legend."),
            "chest_hoangkim": ("📦 Rương Vật Phẩm Hoàng Kim", 5_000_000, "Mở trang bị Anime. Cơ hội nhận trang bị từ Noble đến Mythic."),"""

new_details = """        details = {
            "banner_thuong": ("🔮 Banner Thường", 1_000_000, "Triệu hồi nhân vật. Tỷ lệ: C (60%), B (30%), A (9%), S (0.8%), SS (0.2%)."),
            "banner_xin": ("🔮 Banner Xịn", 5_000_000, "Triệu hồi nhân vật. Tỷ lệ: B (40%), A (45%), S (12%), SS (3%). Có bảo hiểm (pity) 50 lần."),"""

if old_details not in content:
    print("Error: Could not locate old ChestOpenView.get_embed details!")
    sys.exit(1)
content = content.replace(old_details, new_details)

# 4. Overwrite process_chest_open
process_start_str = "    async def process_chest_open(self, interaction: discord.Interaction, view: discord.ui.View, selected_option: str, quantity: int):"
process_idx = content.find(process_start_str)
if process_idx == -1:
    print("Error: Could not locate process_chest_open start!")
    sys.exit(1)

# Let's locate the next function in simulator.py
next_func_str = "    @commands.command("
next_func_idx = content.find(next_func_str, process_idx + len(process_start_str))
if next_func_idx == -1:
    print("Error: Could not locate next command in simulator.py after process_chest_open!")
    sys.exit(1)

new_process_code = """    async def process_chest_open(self, interaction: discord.Interaction, view: discord.ui.View, selected_option: str, quantity: int):
        user_id = interaction.user.id
        
        details = {
            "banner_thuong": ("🔮 Banner Thường", 1_000_000, "banner", "thuong"),
            "banner_xin": ("🔮 Banner Xịn", 5_000_000, "banner", "xin"),
            
            "box_garage": ("🏎️ Garage Box Xe", 100_000, "box", "1"),
            "box_premium": ("🏎️ Premium Box Xe", 1_000_000, "box", "2"),
            "box_luxury": ("🏎️ Luxury Box Xe", 10_000_000, "box", "3"),
        }
        
        name, price_per_one, item_type, tier_id = details[selected_option]
        total_price = price_per_one * quantity
        
        # Check money
        profile = self.economy.get_entry(user_id)
        money = profile[1]
        if money < total_price:
            await interaction.response.send_message(
                f"❌ **Lỗi:** Bạn không đủ tiền! Cần `{total_price:,} VND` nhưng bạn chỉ có `{money:,} VND`.",
                ephemeral=True
            )
            return

        # Defer interaction first to acknowledge and allow editing with files
        await interaction.response.defer()

        # Deduct money
        self.economy.add_money(user_id, -total_price)
        log_wallet_change(logger, event="open_chest_menu", user_id=user_id, money_delta=-total_price, chest_type=selected_option, quantity=quantity)

        # Show opening animation
        anim_embed = make_embed(
            title="📦 ĐANG MỞ RƯƠNG... 📦",
            description=f"⏳ **{interaction.user.display_name}** đang mở **{quantity}x {name}** với tổng giá **{total_price:,} VNĐ**...\\nHãy chờ xem bạn nhận được gì nhé! 🍀",
            color=discord.Color.gold()
        )
        
        gif_path = ABS_PATH / "modules" / "daga" / "open_chest.gif"
        if item_type == "banner":
            gif_path = ABS_PATH / "modules" / "daga" / "mo_trung.gif"

        file_gif = None
        if gif_path.exists():
            file_gif = discord.File(gif_path, filename=gif_path.name)
            anim_embed.set_image(url=f"attachment://{gif_path.name}")
        
        if file_gif:
            await interaction.message.edit(content=None, embed=anim_embed, view=None, attachments=[file_gif])
        else:
            await interaction.message.edit(content=None, embed=anim_embed, view=None, attachments=[])
        
        await asyncio.sleep(3)

        results = []
        if item_type == "banner":
            from app.discord_bot.cogs.daga import BREEDS, STAT_RANGES, get_cock_image_file
            rarity_emojis = {
                "Thường": "<:698204c:1515422780370190377>",
                "Hiếm": "<:759990b:1515423304620703905>",
                "Quý": "<:780661a:1515423318587609224>",
                "Sử Thi": "<:429893s:1515423348014715091>",
                "Huyền Thoại": "<:915638ss:1515423361310785536>",
                "Thần Kê": "<:886814sss:1515423524167225415>",
                "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
            }
            
            pity = self.economy.get_pity_golden(user_id)
            final_pity = pity

            for _ in range(quantity):
                # Roll secret SSS first
                r_secret = random.random() * 100
                is_secret_sss = False
                if tier_id == "thuong" and r_secret < 0.02:
                    is_secret_sss = True
                elif tier_id == "xin" and r_secret < 0.1:
                    is_secret_sss = True

                rarity = "Thường"
                is_reset_pity = False

                if is_secret_sss:
                    rarity = "Thần Kê"
                    if tier_id == "xin":
                        final_pity += 1
                else:
                    r = random.random() * 100
                    if tier_id == "thuong":
                        if r < 60.0:
                            rarity = "Thường"
                        elif r < 90.0:
                            rarity = "Hiếm"
                        elif r < 99.0:
                            rarity = "Quý"
                        elif r < 99.8:
                            rarity = "Sử Thi"
                        else:
                            rarity = "Huyền Thoại"
                    elif tier_id == "xin":
                        if final_pity >= 49:
                            rarity = "Huyền Thoại"
                            is_reset_pity = True
                        else:
                            if r < 40.0:
                                rarity = "Hiếm"
                            elif r < 85.0:
                                rarity = "Quý"
                            elif r < 97.0:
                                rarity = "Sử Thi"
                            else:
                                rarity = "Huyền Thoại"
                                is_reset_pity = True

                        if is_reset_pity:
                            final_pity = 0
                        else:
                            final_pity += 1

                breed = random.choice(BREEDS[rarity])
                ranges = STAT_RANGES[rarity]
                hp = random.randint(*ranges["hp"])
                atk = random.randint(*ranges["atk"])
                df = random.randint(*ranges["df"])
                spd = random.randint(*ranges["spd"])
                luk = random.randint(*ranges["luk"])
                
                cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = self.economy.add_cock(
                    user_id, breed, rarity, hp, atk, df, spd, luk
                )
                results.append({
                    "id": cock_id,
                    "breed": breed,
                    "rarity": rarity,
                    "hp": final_stats["hp"],
                    "atk": final_stats["atk"],
                    "df": final_stats["df"],
                    "spd": final_stats["spd"],
                    "luk": final_stats["luk"],
                    "is_duplicate": is_duplicate,
                    "is_upgraded": is_upgraded,
                    "old_stars": old_stars,
                    "new_stars": new_stars,
                    "new_shards": new_shards
                })

            if tier_id == "xin":
                self.economy.set_pity_golden(user_id, final_pity)

            from app.discord_bot.cogs.daga import RARITY_DISPLAY
            # Build result message
            if quantity == 1:
                res = results[0]
                pity_str = f"\\n🛡️ **Số lần tích bảo hiểm (Pity SS):** `{final_pity}/50`" if tier_id == "xin" else ""
                display_rarity = RARITY_DISPLAY.get(res['rarity'], res['rarity'])
                if res.get("is_duplicate"):
                    if res.get("is_upgraded"):
                        star_emoji_str = "⭐" * res["new_stars"] if res["new_stars"] <= 5 else f"⭐x{res['new_stars']}"
                        desc = (
                            f"🎉 **BẠN NHẬN TRÙNG VÀ ĐÃ NÂNG CẤP NHÂN VẬT!** 🎉\\n\\n"
                            f"⚔️ **Nhân vật:** `{res['breed']}` ({star_emoji_str})\\n"
                            f"⭐ **Độ hiếm:** {rarity_emojis[res['rarity']]} `{display_rarity}`\\n"
                            f"❤️ **Máu (HP):** `{res['hp']}` *(Tăng lên {res['new_stars']} Sao)*\\n"
                            f"⚔️ **Sát thương (ATK):** `{res['atk']}`\\n"
                            f"🛡️ **Phòng thủ (DEF):** `{res['df']}`\\n"
                            f"⚡ **Tốc độ (SPD):** `{res['spd']}`\\n"
                            f"🍀 **May mắn (LUK):** `{res['luk']}`"
                            f"{pity_str}"
                        )
                    else:
                        needed = res["new_stars"] + 1
                        desc = (
                            f"🔄 **BẠN NHẬN TRÙNG NHÂN VẬT!** (Tích luỹ mảnh)\\n\\n"
                            f"⚔️ **Nhân vật:** `{res['breed']}`\\n"
                            f"⭐ **Độ hiếm:** {rarity_emojis[res['rarity']]} `{display_rarity}`\\n"
                            f"📊 **Tiến trình nâng sao:** `[ {res['new_shards']} / {needed} ]` mảnh trùng\\n"
                            f"*(Nhận thêm `{needed - res['new_shards']}` bản trùng nữa để lên {res['new_stars'] + 1} Sao)*"
                            f"{pity_str}"
                        )
                else:
                    desc = (
                        f"⚔️ **Nhân vật:** `{res['breed']}`\\n"
                        f"⭐ **Độ hiếm:** {rarity_emojis[res['rarity']]} `{display_rarity}`\\n"
                        f"❤️ **Máu (HP):** `{res['hp']}`\\n"
                        f"⚔️ **Sát thương (ATK):** `{res['atk']}`\\n"
                        f"🛡️ **Phòng thủ (DEF):** `{res['df']}`\\n"
                        f"⚡ **Tốc độ (SPD):** `{res['spd']}`\\n"
                        f"🍀 **May mắn (LUK):** `{res['luk']}`"
                        f"{pity_str}"
                    )
                embed = make_embed(
                    title="🔮 TRIỆU HỒI THÀNH CÔNG 🔮",
                    description=desc,
                    color=discord.Color.green(),
                )
                img_name = get_cock_image_file(res['breed'])
                file_img = None
                if img_name:
                    file_img = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
                    embed.set_thumbnail(url=f"attachment://{img_name}")
                
                if file_img:
                    await interaction.message.edit(embed=embed, view=view, attachments=[file_img])
                else:
                    await interaction.message.edit(embed=embed, view=view, attachments=[])
            else:
                list_str = ""
                for res in results:
                    emoji = rarity_emojis[res['rarity']]
                    display_rarity = RARITY_DISPLAY.get(res['rarity'], res['rarity'])
                    if res.get("is_duplicate"):
                        if res.get("is_upgraded"):
                            star_emoji_str = "⭐" * res["new_stars"] if res["new_stars"] <= 5 else f"⭐x{res['new_stars']}"
                            list_str += f"• `[ID: {res['id']}]` {emoji} **{res['breed']}** ({display_rarity}) ({star_emoji_str}) | HP: `{res['hp']}` | ATK: `{res['atk']}` | DEF: `{res['df']}` (Trùng - Nâng Sao! ⭐)\\n"
                        else:
                            needed = res["new_stars"] + 1
                            list_str += f"• `[ID: {res['id']}]` {emoji} **{res['breed']}** ({display_rarity}) | HP: `{res['hp']}` | ATK: `{res['atk']}` | DEF: `{res['df']}` (Trùng - Mảnh: `{res['new_shards']}/{needed}`)\\n"
                    else:
                        list_str += f"• `[ID: {res['id']}]` {emoji} **{res['breed']}** ({display_rarity}) | HP: `{res['hp']}` | ATK: `{res['atk']}` | DEF: `{res['df']}`\\n"
                
                pity_str = f"\\n🛡️ **Bảo hiểm hiện tại (Pity SS):** `{final_pity}/50`" if tier_id == "xin" else ""
                embed = make_embed(
                    title=f"🔮 KẾT QUẢ TRIỆU HỒI {quantity} LƯỢT 🔮",
                    description=f"Chúc mừng bạn đã sở hữu thêm các nhân vật mới:\\n\\n{list_str}{pity_str}",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.message.edit(embed=embed, view=view, attachments=[])

        elif item_type == "box":
            from app.discord_bot.cogs.xe import BOX_DETAILS, CAR_RARITIES, CAR_EDITIONS, COLLECTIONS, RARITY_INFO, get_car_image_file, roll_rarity, CAR_QUOTES
            rarity_emojis = {
                "Common": "⚪", "Rare": "🟢", "Epic": "🔵", "Legendary": "🟣", "Mythic": "🟡", "Exclusive": "🔴"
            }
            
            box = BOX_DETAILS[tier_id]
            for _ in range(quantity):
                rarity = roll_rarity(box["rates"])
                
                models = [name for name, r_name in CAR_RARITIES.items() if r_name == rarity]
                model = random.choice(models)
                
                edition = CAR_EDITIONS.get(model, "Standard")
                self.economy.add_car(user_id, model)
                results.append({
                    "model": model,
                    "rarity": rarity,
                    "edition": edition,
                    "emoji": rarity_emojis[rarity]
                })

            if quantity == 1:
                res = results[0]
                desc = (
                    f"🏎️ **Xe:** **{res['model']}**\\n"
                    f"⭐ **Độ hiếm:** {res['emoji']} `{res['rarity']}`\\n"
                    f"✨ **Phiên bản:** `{res['edition']}`\\n\\n"
                    f"*\\\"{CAR_QUOTES.get(res['model'], 'Một chiếc xe tuyệt vời!')}\\\"*\\n\\n"
                    f"Đã được chuyển vào Garage của bạn (`i?xe garage`)!"
                )
                embed = make_embed(
                    title="🏎️ MỞ BOX XE THÀNH CÔNG 🏎️",
                    description=desc,
                    color=discord.Color.green(),
                )
                img_name = get_car_image_file(res['model'])
                file_img = None
                if img_name:
                    file_img = discord.File(ABS_PATH / "modules" / "duaxe" / img_name, filename=img_name)
                    embed.set_thumbnail(url=f"attachment://{img_name}")
                
                if file_img:
                    await interaction.message.edit(embed=embed, view=view, attachments=[file_img])
                else:
                    await interaction.message.edit(embed=embed, view=view, attachments=[])
            else:
                list_str = ""
                for res in results:
                    list_str += f"• {res['emoji']} **{res['model']}** ({res['rarity']}) - `{res['edition']}`\\n"
                
                embed = make_embed(
                    title=f"🏎️ KẾT QUẢ MỞ {quantity} BOX XE 🏎️",
                    description=f"Chúc mừng bạn đã nhận được các xe sau:\\n\\n{list_str}",
                    color=discord.Color.green()
                )
                embed.set_thumbnail(url=interaction.user.display_avatar.url)
                await interaction.message.edit(embed=embed, view=view, attachments=[])

"""

# Reconstruct process_chest_open
content = content[:process_idx] + new_process_code + content[next_func_idx:]

with open(sim_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Quick opening moruong fixes applied successfully!")
