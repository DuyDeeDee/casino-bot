import re

file_path = "app/discord_bot/cogs/simulator.py"
terms = ["đá gà", "nông trại", "chiến kê", "ấp trứng", "sư kê", "user_cocks", "daga"]

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

found_any = False
for term in terms:
    count = text.lower().count(term.lower())
    if count > 0:
        print(f"Term '{ascii(term)}' found {count} times.")
        found_any = True
        idx = 0
        while True:
            idx = text.lower().find(term.lower(), idx)
            if idx == -1:
                break
            line_num = text[:idx].count("\n") + 1
            # print surrounding line safely in ascii
            print(f"  Line {line_num}: {ascii(text[idx-40:idx+60].strip().replace('\n', ' '))}")
            idx += len(term)

if not found_any:
    print("Clean! No terms found in simulator.py.")
