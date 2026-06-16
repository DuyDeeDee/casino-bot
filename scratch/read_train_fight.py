with open("app/discord_bot/cogs/daga.py", "r", encoding="utf-8", errors="replace") as f:
    lines = f.readlines()

# Extract lines from index 2110 to 2862 (0-indexed: 2110 to 2862)
# Line 2111 is index 2110. Line 2862 is index 2861.
extracted = lines[2110:2862]

with open("scratch/train_fight_original.py", "w", encoding="utf-8") as out:
    out.writelines(extracted)

print(f"Extracted {len(extracted)} lines to scratch/train_fight_original.py")
