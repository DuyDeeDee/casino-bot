# -*- coding: utf-8 -*-
import os

daga_path = r"app/discord_bot/cogs/daga.py"

with open(daga_path, "r", encoding="utf-8") as f:
    code = f.read()

# Add CHARACTER_INFO_MAP before RARITY_DISPLAY or at top level
if "CHARACTER_INFO_MAP" not in code:
    rarity_display_idx = code.find("RARITY_DISPLAY = {")
    if rarity_display_idx == -1:
        print("Error: RARITY_DISPLAY not found!")
        exit(1)
        
    map_code = """CHARACTER_INFO_MAP = {
    "Usopp": {"series": "One Piece", "active": "Bắn Tỉa", "passive": "Dũng Khí"},
    "Krillin": {"series": "Dragon Ball", "active": "Kienzan", "passive": "Chiến Binh Z"},
    "Zenitsu": {"series": "Kimetsu no Yaiba", "active": "Sấm Nhất Kiếm", "passive": "Ngủ Chiến"},
    "Killua": {"series": "Hunter x Hunter", "active": "Godspeed", "passive": "Sát Thủ Zoldyck"},
    "Sakura": {"series": "Naruto", "active": "Chakra Punch", "passive": "Hồi Phục"},
    "Trunks": {"series": "Dragon Ball", "active": "Kiếm Thần", "passive": "Saiyan Lai"},
    "Levi Ackerman": {"series": "Attack on Titan", "active": "Tấn Công Xoáy", "passive": "Ackerman"},
    "Zoro": {"series": "One Piece", "active": "Santoryu", "passive": "Thám Tử Kiếm"},
    "Akame": {"series": "Akame ga Kill", "active": "Murasame", "passive": "Sát Thủ"},
    "Kakashi": {"series": "Naruto", "active": "Chidori", "passive": "Sharingan"},
    "Meliodas": {"series": "Seven Deadly Sins", "active": "Full Counter", "passive": "Tội Phẫn Nộ"},
    "Ichigo": {"series": "Bleach", "active": "Getsuga Tensho", "passive": "Shinigami Thay Thế"},
    "Gojo Satoru": {"series": "Jujutsu Kaisen", "active": "Thuật Thức Vô Hạn", "passive": "Lục Nhãn"},
    "Itachi Uchiha": {"series": "Naruto", "active": "Amaterasu", "passive": "Mangekyou Sharingan"},
    "Vegeta": {"series": "Dragon Ball", "active": "Final Flash", "passive": "Hoàng Tử Saiyan"},
    "Goku (Ultra Instinct)": {"series": "Dragon Ball", "active": "Kamehameha x10", "passive": "Bản Năng Vô Cực"},
    "Luffy (Gear 5)": {"series": "One Piece", "active": "Gomu Thunder", "passive": "Nika"},
    "Luffy": {"series": "One Piece", "active": "Gomu Thunder", "passive": "Nika"},
    "Luffy Gear 4": {"series": "One Piece", "active": "Gear 4 - Leo Bazooka", "passive": "Nika"},
    "Naruto (Baryon Mode)": {"series": "Naruto", "active": "Rasengan Siêu Lớn", "passive": "Baryon"},
    "Saitama": {"series": "One Punch Man", "active": "Serious Punch", "passive": "Một Đấm"}
}

"""
    code = code[:rarity_display_idx] + map_code + code[rarity_display_idx:]

# Now replace the body of daga_info
info_start = code.find("    async def daga_info(self, ctx: commands.Context, cock_id: int | None = None):")
if info_start == -1:
    print("Error: def daga_info not found!")
    exit(1)

target_start_str = "        c = Cock(cock_row)"
target_end_str = "        embed = make_embed("

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
            f"╔══════════════════════════════╗\\n"
            f"║  {emoji_rarity} {display_rarity:<23}║\\n"
            f"║                              ║\\n"
            f"║  ⚔️ {c.display_name:<24}║\\n"
            f"║  📺 {info['series']:<24}║\\n"
            f"║                              ║\\n"
            f"║  ❤️ HP:    {hp_str:<18}║\\n"
            f"║  ⚔️ ATK:   {atk_str:<18}║\\n"
            f"║  🛡️ DEF:   {df_str:<18}║\\n"
            f"║  ⚡ SPD:   {spd_str:<18}║\\n"
            f"║                              ║\\n"
            f"║  💫 Kỹ năng: {info['active']:<17}║\\n"
            f"║  ✨ Passive: {info['passive']:<17}║\\n"
            f"╚══════════════════════════════╝\\n\\n"
            f"🆔 **ID Nhân vật:** `{c.id}`\\n"
            f"⭐ **Cấp Sao:** `{stars_display}`{shards_display}\\n"
            f"📈 **Cấp độ:** `{c.level}/100` (EXP: `{c.exp}/{c.level*100}`)\\n"
            f"🏆 **Thành tích:** `{c.wins}` Thắng | `{c.losses}` Thua (Chuỗi: `{c.streak}`)\\n\\n"
            f"🎒 **Trang bị:** 🗡️ Vũ khí: `{c.weapon}` | 🛡️ Giáp: `{c.armor}` | 🔮 Bùa: `{c.charm}`"
        )

"""

# Reconstruct the file content
replaced_code = code[:target_start_idx] + new_daga_info_body + code[target_end_idx:]

with open(daga_path, "w", encoding="utf-8") as f:
    f.write(replaced_code)

print("Successfully redesigned daga_info!")
