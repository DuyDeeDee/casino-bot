# -*- coding: utf-8 -*-
import sys

daga_path = "app/discord_bot/cogs/daga.py"

with open(daga_path, "r", encoding="utf-8", errors="replace") as f:
    content = f.read()

# Locate the first train trigger
train_trigger_str = "await self._trigger_random_event(ctx, cock)"
first_train_idx = content.find(train_trigger_str)
if first_train_idx == -1:
    print("Error: train_trigger_str not found!")
    sys.exit(1)
end_of_train = first_train_idx + len(train_trigger_str)

# Locate the correct fight command
correct_fight_str = "Thách đấu đá gà PvP đặt cược với người chơi khác."
fight_text_idx = content.find(correct_fight_str)
if fight_text_idx == -1:
    print("Error: correct fight string not found!")
    sys.exit(1)

# Find the decorator @daga_group.command starting before this text
decorator_idx = content.rfind("@daga_group.command", 0, fight_text_idx)
if decorator_idx == -1:
    print("Error: decorator before fight not found!")
    sys.exit(1)

print(f"End of train index: {end_of_train}")
print(f"Start of fight index: {decorator_idx}")
print("\n--- CORRUPTED BLOCK TO BE DELETED ---")
print(content[end_of_train:decorator_idx])
print("-------------------------------------\n")
