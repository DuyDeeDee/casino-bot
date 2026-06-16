# -*- coding: utf-8 -*-
import os

daga_path = r"app/discord_bot/cogs/daga.py"

with open(daga_path, "r", encoding="utf-8") as f:
    code = f.read()

# Locate body of daga_info
info_start = code.find("    async def daga_info(self, ctx: commands.Context, cock_id: int | None = None):")
if info_start == -1:
    print("Error: def daga_info not found!")
    exit(1)

target_start_str = "        c = Cock(cock_row)"
target_end_str = "    @daga_group.command(name=\"train\""

target_start_idx = code.find(target_start_str, info_start)
target_end_idx = code.find(target_end_str, target_start_idx)

if target_start_idx == -1 or target_end_idx == -1:
    print("Error: Could not locate replace markers in daga_info!")
    exit(1)

new_daga_info_body = """        c = Cock(cock_row)
        rarity_emojis = {
            "Thường": "⚪",
            "Hiếm": "🟢",
            "Quý": "🔵",
            "Sử Thi": "🟣",
            "Huyền Thoại": "🟡",
            "Thần Kê": "💠",
            "Exclusive": "👑"
        }

        stars_display = "0 Sao" if c.stars == 0 else ("⭐" * c.stars if c.stars <= 5 else f"⭐x{c.stars}")
        needed = c.stars + 1
        shards_display = f" (`{c.shards}/{needed}` mảnh nâng sao)"

        display_rarity = RARITY_DISPLAY.get(c.rarity, c.rarity)
        emoji_rarity = rarity_emojis.get(c.rarity, "⚪")

        info = {"series": "Unknown", "active": "Chưa rõ", "passive": "Chưa rõ"}
        for k, v in CHARACTER_INFO_MAP.items():
            if k.lower() in c.name.lower() or c.name.lower() in k.lower():
                info = v
                break

        # Format stats with thousand separators
        hp_str = f"{c.get_max_hp():,}"
        atk_str = f"{c.get_atk():,}"
        df_str = f"{c.get_df():,}"
        spd_str = f"{c.get_spd():,}"

        desc = (
            f"╔══════════════════════════════\\n"
            f"║  {emoji_rarity} **{display_rarity}**\\n"
            f"║\\n"
            f"║  ⚔️ **{c.display_name}**\\n"
            f"║  📺 **{info['series']}**\\n"
            f"║\\n"
            f"║  ❤️ HP: **{hp_str}**\\n"
            f"║  ⚔️ ATK: **{atk_str}**\\n"
            f"║  🛡️ DEF: **{df_str}**\\n"
            f"║  ⚡ SPD: **{spd_str}**\\n"
            f"║\\n"
            f"║  💫 Kỹ năng: **{info['active']}**\\n"
            f"║  ✨ Passive: **{info['passive']}**\\n"
            f"╚══════════════════════════════\\n\\n"
            f"🆔 **ID Nhân vật:** `{c.id}`\\n"
            f"⭐ **Cấp Sao:** `{stars_display}`{shards_display}\\n"
            f"📈 **Cấp độ:** `{c.level}/100` (EXP: `{c.exp}/{c.level*100}`)\\n"
            f"🏆 **Thành tích:** `{c.wins}` Thắng | `{c.losses}` Thua (Chuỗi: `{c.streak}`)"
        )

        embed = make_embed(
            title="📊 THÔNG TIN NHÂN VẬT 📊",
            description=desc,
            color=discord.Color.blue(),
        )
        img_name = get_cock_image_file(c.name)
        if img_name:
            file = discord.File(ABS_PATH / "modules" / "daga" / img_name, filename=img_name)
            embed.set_image(url=f"attachment://{img_name}")
            await ctx.send(embed=embed, file=file)
        else:
            embed.set_thumbnail(url=ctx.author.display_avatar.url)
            await ctx.send(embed=embed)

    """

# Reconstruct code
replaced_code = code[:target_start_idx] + new_daga_info_body + code[target_end_idx:]

with open(daga_path, "w", encoding="utf-8") as f:
    f.write(replaced_code)

print("Successfully updated daga_info body (no equipment, enlarged image, left borders)!")
