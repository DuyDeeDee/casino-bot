# -*- coding: utf-8 -*-
import sys
import re

daga_path = "app/discord_bot/cogs/daga.py"

with open(daga_path, "r", encoding="utf-8") as f:
    content = f.read()

# 1. Delete buy_chest command
# Locate daga_buy.command(name="chest")
chest_start = content.find('    @daga_buy.command(name="chest"')
food_start = content.find('    @daga_buy.command(name="food"')
if chest_start == -1 or food_start == -1:
    print("Error: Could not locate buy_chest/buy_food command markers!")
    sys.exit(1)

content = content[:chest_start] + content[food_start:]

# 2. Delete buy_equip, unequip, and equip commands
# In the updated content, locate from buy_equip to daga_list
equip_start = content.find('    @daga_buy.command(name="equip"')
list_start = content.find('    @daga_group.command(name="list"')
if equip_start == -1 or list_start == -1:
    print("Error: Could not locate buy_equip/daga_list command markers!")
    sys.exit(1)

content = content[:equip_start] + content[list_start:]

# 3. Modify daga_shop command (remove Gear Chest and update Banner text)
shop_start_str = "        desc = (\n            \"🔮 **CỬA HÀNG THẺ TRIỆU HỒI ANIME**\\n\""
shop_end_str = "        embed = make_embed("

shop_start_idx = content.find(shop_start_str)
shop_end_idx = content.find(shop_end_str, shop_start_idx)

if shop_start_idx == -1 or shop_end_idx == -1:
    print("Error: Could not locate daga_shop description markers!")
    sys.exit(1)

new_shop_desc = """        desc = (
            "🔮 **CỬA HÀNG TRIỆU HỒI ANIME (GACHA BANNER)**\\n"
            f"🛒 Triệu hồi bằng lệnh: `{prefix}anime buy banner <ID>`\\n"
            "🔹 **[1] Banner Thường:** `1.000.000 VND` (60% C | 30% B | 9% A | 0.8% S | 0.2% SS)\\n"
            "🔹 **[2] Banner Xịn:** `5.000.000 VND` (40% B | 45% A | 12% S | 3% SS | Bảo hiểm 50 lượt cho SS)\\n\\n"
            "🌾 **CỬA HÀNG THỨC ĂN (FOOD SHOP)**\\n"
            f"🛒 Mua thức ăn bằng lệnh: `{prefix}anime buy food <ID> <số_lượng>`\\n"
            "🌾 **[1] Thóc:** `20.000 VND` (+10 EXP)\\n"
            "🌽 **[2] Ngô:** `54.000 VND` (+30 EXP)\\n"
            "🐛 **[3] Côn Trùng:** `128.000 VND` (+80 EXP)\\n"
            "🐟 **[4] Cá Nhỏ:** `280.000 VND` (+200 EXP)\\n"
            "🥩 **[5] Thịt Bò:** `600.000 VND` (+500 EXP)\\n"
            "🦐 **[6] Hải Sản:** `1.000.000 VND` (+1.000 EXP)\\n"
            "🥚 **[7] Trứng Dinh Dưỡng:** `2.250.000 VND` (+2.500 EXP)\\n"
            "💊 **[8] Vitamin:** `4.000.000 VND` (+5.000 EXP)\\n"
            "🌿 **[9] Nhân Sâm:** `7.000.000 VND` (+10.000 EXP)\\n"
            "🍯 **[10] Linh Dược:** `30.000.000 VND` (+50.000 EXP)\\n"
        )
"""
content = content[:shop_start_idx] + new_shop_desc + content[shop_end_idx:]

# 4. Replace buy_egg with buy_banner implementation
egg_cmd_start = content.find('    @daga_buy.command(name="egg"')
next_cmd_after_egg = content.find('    @daga_buy.command(name="food"')

if egg_cmd_start == -1 or next_cmd_after_egg == -1:
    print("Error: Could not locate buy_egg/buy_food command boundaries!")
    sys.exit(1)

new_buy_banner_code = """    @daga_buy.command(name="banner", brief="Triệu hồi nhân vật gacha từ banner.", aliases=["summon", "egg"])
    async def buy_banner(self, ctx: commands.Context, banner_type: str):
        banner_type = banner_type.lower().strip()
        banner_id_mapping = {
            "1": "thuong",
            "2": "xin"
        }
        if banner_type in banner_id_mapping:
            banner_type = banner_id_mapping[banner_type]

        prices = {"thuong": 1_000_000, "xin": 5_000_000}
        
        if banner_type not in prices:
            await ctx.send("❌ **Lỗi:** Loại banner không hợp lệ! Hãy chọn ID: `1` (Thường) hoặc `2` (Xịn).")
            return

        price = prices[banner_type]
        # Validate balance
        try:
            validate_money_bet(self.economy, ctx.author.id, price)
        except Exception as exc:
            await ctx.send(str(exc))
            return

        pity = self.economy.get_pity_golden(ctx.author.id)

        # Roll secret SSS first
        r_secret = random.random() * 100
        is_secret_sss = False
        if banner_type == "thuong" and r_secret < 0.02:
            is_secret_sss = True
        elif banner_type == "xin" and r_secret < 0.1:
            is_secret_sss = True

        rarity = "Thường"
        is_reset_pity = False

        if is_secret_sss:
            rarity = "Thần Kê"
            if banner_type == "xin":
                self.economy.set_pity_golden(ctx.author.id, pity + 1)
        else:
            # Roll rarity normally
            r = random.random() * 100
            if banner_type == "thuong":
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
            elif banner_type == "xin":
                # pity logic (only applies to Huyền Thoại)
                if pity >= 49: # 50th roll guarantee
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
                    self.economy.set_pity_golden(ctx.author.id, 0)
                else:
                    self.economy.set_pity_golden(ctx.author.id, pity + 1)

        # Generate stats and breed
        breed = random.choice(BREEDS[rarity])
        ranges = STAT_RANGES[rarity]
        hp = random.randint(*ranges["hp"])
        atk = random.randint(*ranges["atk"])
        df = random.randint(*ranges["df"])
        spd = random.randint(*ranges["spd"])
        luk = random.randint(*ranges["luk"])

        # Deduct money
        self.economy.add_money(ctx.author.id, -price)
        
        # Add cock to DB
        cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = self.economy.add_cock(
            ctx.author.id, breed, rarity, hp, atk, df, spd, luk
        )

        log_wallet_change(
            logger,
            event="buy_banner_gacha",
            user_id=ctx.author.id,
            money_delta=-price,
            egg_type=banner_type,
            cock_id=cock_id,
            rarity=rarity,
        )

        pity_str = ""
        if banner_type == "xin":
            new_pity = 0 if is_reset_pity else pity + 1
            pity_str = f"\\n🛡️ **Số lần tích bảo hiểm (Pity SS):** `{new_pity}/50`"

        rarity_emojis = {
            "Thường": "<:698204c:1515422780370190377>",
            "Hiếm": "<:759990b:1515423304620703905>",
            "Quý": "<:780661a:1515423318587609224>",
            "Sử Thi": "<:429893s:1515423348014715091>",
            "Huyền Thoại": "<:915638ss:1515423361310785536>",
            "Thần Kê": "<:886814sss:1515423524167225415>",
            "Exclusive": "<a:869826sparklyrainbow:1515427348516831404>"
        }

        display_banner_name = "Banner Thường" if banner_type == "thuong" else "Banner Xịn"
        display_rarity = RARITY_DISPLAY.get(rarity, rarity)
        if is_duplicate:
            if is_upgraded:
                star_emoji_str = "⭐" * new_stars if new_stars <= 5 else f"⭐x{new_stars}"
                desc = (
                    f"Bạn đã triệu hồi từ **{display_banner_name}** với giá **{price:,} VND**...\\n"
                    f"🎉 **BẠN NHẬN TRÙNG VÀ ĐÃ NÂNG CẤP NHÂN VẬT!** 🎉\\n\\n"
                    f"⚔️ **Nhân vật:** `{breed}` ({star_emoji_str})\\n"
                    f"⭐ **Độ hiếm:** {rarity_emojis[rarity]} `{display_rarity}`\\n"
                    f"❤️ **Máu (HP):** `{final_stats['hp']}` *(Tăng lên {new_stars} Sao)*\\n"
                    f"⚔️ **Sát thương (ATK):** `{final_stats['atk']}`\\n"
                    f"🛡️ **Phòng thủ (DEF):** `{final_stats['df']}`\\n"
                    f"⚡ **Tốc độ (SPD):** `{final_stats['spd']}`\\n"
                    f"🍀 **May mắn (LUK):** `{final_stats['luk']}`"
                    f"{pity_str}"
                )
            else:
                needed = new_stars + 1
                desc = (
                    f"Bạn đã triệu hồi từ **{display_banner_name}** với giá **{price:,} VND**...\\n"
                    f"🔄 **BẠN NHẬN TRÙNG NHÂN VẬT!** (Tích luỹ mảnh)\\n\\n"
                    f"⚔️ **Nhân vật:** `{breed}`\\n"
                    f"⭐ **Độ hiếm:** {rarity_emojis[rarity]} `{display_rarity}`\\n"
                    f"📊 **Tiến trình nâng sao:** `[ {new_shards} / {needed} ]` mảnh trùng\\n"
                    f"*(Nhận thêm `{needed - new_shards}` bản trùng nữa để lên {new_stars + 1} Sao)*"
                    f"{pity_str}"
                )
        else:
            desc = (
                f"Bạn đã triệu hồi từ **{display_banner_name}** với giá **{price:,} VND**...\\n"
                f"✨ **Triệu hồi thành công!**\\n\\n"
                f"⚔️ **Nhân vật:** `{breed}`\\n"
                f"⭐ **Độ hiếm:** {rarity_emojis[rarity]} `{display_rarity}`\\n"
                f"❤️ **Máu (HP):** `{final_stats['hp']}`\\n"
                f"⚔️ **Sát thương (ATK):** `{final_stats['atk']}`\\n"
                f"🛡️ **Phòng thủ (DEF):** `{final_stats['df']}`\\n"
                f"⚡ **Tốc độ (SPD):** `{final_stats['spd']}`\\n"
                f"🍀 **May mắn (LUK):** `{final_stats['luk']}`"
                f"{pity_str}"
            )

        anim_embed = make_embed(
            title="🔮 ĐANG TRIỆU HỒI ANIME... 🔮",
            description=f"⏳ **{ctx.author.display_name}** đang triệu hồi từ **{display_banner_name}**...\\nHãy chờ xem bạn nhận được nhân vật nào nhé! 🍀",
            color=discord.Color.gold()
        )
        gif_path = ABS_PATH / "modules" / "daga" / "mo_trung.gif"
        file_gif = discord.File(gif_path, filename="mo_trung.gif")
        anim_embed.set_image(url="attachment://mo_trung.gif")

        msg = await ctx.send(embed=anim_embed, file=file_gif)

        await asyncio.sleep(3)

        embed = make_embed(
            title="🔮 TRIỆU HỒI THÀNH CÔNG 🔮",
            description=desc,
            color=discord.Color.green(),
        )
        img_name = get_cock_image_file(breed)
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_thumbnail(url=f"attachment://{img_name}")
            await msg.edit(embed=embed, attachments=[file])
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await msg.edit(embed=embed, attachments=[])

"""

content = content[:egg_cmd_start] + new_buy_banner_code + content[next_cmd_after_egg:]

with open(daga_path, "w", encoding="utf-8") as f:
    f.write(content)

print("Banner updates applied successfully!")
