import py_compile

file_path = "app/discord_bot/cogs/daga.py"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Replace aliases
old_aliases = 'aliases=["daga", "dg"],'
new_aliases = 'aliases=["am", "daga", "dg"],'

if old_aliases in text:
    text = text.replace(old_aliases, new_aliases)
    print("SUCCESS: Aliases updated.")
else:
    print("WARNING: aliases pattern not found.")

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

try:
    py_compile.compile(file_path, doraise=True)
    print("SUCCESS: Compiled successfully!")
except Exception as e:
    print("ERROR:", e)
