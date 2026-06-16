terms = ["chiến kê", "sư kê", "đá gà", "gà chính", "gà phôi", "gà chiến", "ấp trứng", "nông trại"]

with open("app/discord_bot/cogs/daga.py", "r", encoding="utf-8") as f:
    text = f.read()

found_any = False
for term in terms:
    count = text.lower().count(term.lower())
    if count > 0:
        print(f"Term '{ascii(term)}' found {count} times.")
        found_any = True
        # Print a few occurrences
        idx = 0
        while True:
            idx = text.lower().find(term.lower(), idx)
            if idx == -1:
                break
            line_num = text[:idx].count("\n") + 1
            print(f"  Line {line_num}: {ascii(text[idx-30:idx+50].strip().replace('\n', ' '))}")
            idx += len(term)

if not found_any:
    print("Clean! No old terms found in daga.py.")
