with open("app/discord_bot/cogs/daga.py", "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

extracted = lines[2100:2450]
with open("scratch/battle_loop.py", "w", encoding="utf-8") as out:
    out.writelines(extracted)

print("Battle loop lines extracted to scratch/battle_loop.py")
