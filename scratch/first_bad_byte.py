with open("app/discord_bot/cogs/daga.py", "rb") as f:
    data = f.read()

lines = data.split(b'\n')
target_line = 1819

for idx in range(max(1, target_line - 5), min(len(lines) + 1, target_line + 10)):
    line_bytes = lines[idx - 1]
    print(f"Line {idx}: {repr(line_bytes)}")
