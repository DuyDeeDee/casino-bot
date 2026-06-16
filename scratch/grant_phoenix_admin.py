import os
import sys
import random

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.daga import STAT_RANGES

def main():
    economy = Economy()
    admin_id = 756026481020239874
    breed = "Ga Phuong Hoang Lua"  # plain ascii representation for console
    real_breed = "Gà Phượng Hoàng Lửa"
    rarity = "Exclusive"
    
    # Check if admin already has this cock
    economy.cur.execute("SELECT id, hp, atk, df, spd, luk FROM user_cocks WHERE user_id=? AND name=?", (admin_id, real_breed))
    row = economy.cur.fetchone()
    
    if row:
        print(f"Admin (ID: {admin_id}) ALREADY has a '{breed}' (ID: {row[0]}) in their inventory!")
        print(f"Stats - HP: {row[1]}, ATK: {row[2]}, DEF: {row[3]}, SPD: {row[4]}, LUK: {row[5]}")
    else:
        # Roll high stats within ranges
        ranges = STAT_RANGES[rarity]
        hp = random.randint(*ranges["hp"])
        atk = random.randint(*ranges["atk"])
        df = random.randint(*ranges["df"])
        spd = random.randint(*ranges["spd"])
        luk = random.randint(*ranges["luk"])
        
        # Grant it!
        cock_id, is_duplicate, is_upgraded, old_stars, new_stars, new_shards, final_stats = economy.add_cock(
            admin_id, real_breed, rarity, hp, atk, df, spd, luk
        )
        print(f"Successfully granted '{breed}' (ID: {cock_id}) to Admin (ID: {admin_id})!")
        print(f"Stats - HP: {hp}, ATK: {atk}, DEF: {df}, SPD: {spd}, LUK: {luk}")

if __name__ == "__main__":
    main()
