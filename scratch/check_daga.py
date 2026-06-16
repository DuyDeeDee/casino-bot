with open("app/discord_bot/cogs/daga.py", "rb") as f:
    data = f.read()

# Position is 79721
start = max(0, 79721 - 40)
end = min(len(data), 79721 + 40)
snippet = data[start:end]
print("Snippet bytes:", snippet)
print("Snippet decoded with latin-1:", snippet.decode("latin-1"))
print("Snippet decoded with utf-8 (ignore):", snippet.decode("utf-8", errors="ignore"))
print("Snippet decoded with utf-8 (replace):", snippet.decode("utf-8", errors="replace"))
