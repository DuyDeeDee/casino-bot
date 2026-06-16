with open("app/discord_bot/cogs/daga.py", "rb") as f:
    data = f.read()

lines = data.split(b'\n')
for idx in range(1770, 1819):
    print(f"Line {idx}: {repr(lines[idx-1])}")
