# -*- coding: utf-8 -*-

# Mock values
emoji_rarity = "🟣"
display_rarity = "SSR"
display_name = "Gojo Satoru"
series = "Jujutsu Kaisen"
hp_str = "9,500"
atk_str = "8,200"
df_str = "6,100"
spd_str = "7,800"
active_skill = "Vô Hạn"
passive_skill = "Lục Nhãn"

desc = (
    f"╔══════════════════════════════╗\n"
    f"║  {emoji_rarity} {display_rarity:<23}║\n"
    f"║                              ║\n"
    f"║  ⚔️ {display_name:<24}║\n"
    f"║  📺 {series:<24}║\n"
    f"║                              ║\n"
    f"║  ❤️ HP:    {hp_str:<18}║\n"
    f"║  ⚔️ ATK:   {atk_str:<18}║\n"
    f"║  🛡️ DEF:   {df_str:<18}║\n"
    f"║  ⚡ SPD:   {spd_str:<18}║\n"
    f"║                              ║\n"
    f"║  💫 Kỹ năng: {active_skill:<17}║\n"
    f"║  ✨ Passive: {passive_skill:<17}║\n"
    f"╚══════════════════════════════╝"
)

with open("scratch/test_info_output.txt", "w", encoding="utf-8") as f:
    f.write(desc)
print("Wrote output successfully!")
