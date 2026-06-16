with open("scratch/train_fight_original.py", "r", encoding="utf-8") as f:
    text = f.read()

print("Huyen Vu and Hac Ke lines:")
for i, line in enumerate(text.split("\n"), 1):
    if "Huyền Vũ" in line or "Hắc Kê" in line:
        print(f"Line {i}: {ascii(line.strip())}")
