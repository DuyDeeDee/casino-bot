import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy

def main():
    economy = Economy()
    test_user_id = 888888888
    
    # 1. Clean previous test cocks for test user
    economy.cur.execute("DELETE FROM user_cocks WHERE user_id=?", (test_user_id,))
    economy.conn.commit()
    
    # 2. Add first Gà Luffy (0 stars)
    print("Granting first Luffy...")
    cock_id, is_dup, is_up, old_s, new_s, new_sh, stats = economy.add_cock(
        test_user_id, "Gà Luffy", "Exclusive", 500, 100, 80, 80, 60
    )
    print(f"Granted: ID={cock_id}, Name=Gà Luffy, Stars={new_s}, Shards={new_sh}, Stats={stats}\n")
    
    # 3. Simulate getting duplicates to upgrade stars from 0 to 5
    # To reach 6 stars:
    # 0 -> 1 star (needs 1 shard)
    # 1 -> 2 stars (needs 2 shards)
    # 2 -> 3 stars (needs 3 shards)
    # 3 -> 4 stars (needs 4 shards)
    # 4 -> 5 stars (needs 5 shards)
    # 5 -> 6 stars (needs 6 shards)
    # Total duplicates needed = 1 + 2 + 3 + 4 + 5 + 6 = 21 duplicates.
    
    print("Simulating adding 20 duplicates to reach 5 stars...")
    for i in range(20):
        cock_id, is_dup, is_up, old_s, new_s, new_sh, stats = economy.add_cock(
            test_user_id, "Gà Luffy", "Exclusive", 500, 100, 80, 80, 60
        )
    
    row = economy.get_cock(cock_id)
    print(f"Before evolution - Name: {row[2]}, Stars: {row[19]}, Shards: {row[20]}, HP: {row[6]}, ATK: {row[7]}\n")
    
    # 4. Add the 21st duplicate to trigger the 6-star evolution!
    print("Adding 21st duplicate to trigger 6-star evolution...")
    cock_id, is_dup, is_up, old_s, new_s, new_sh, stats = economy.add_cock(
        test_user_id, "Gà Luffy", "Exclusive", 500, 100, 80, 80, 60
    )
    
    row = economy.get_cock(cock_id)
    print(f"After evolution - Name: {row[2]}, Stars: {row[19]}, Shards: {row[20]}, HP: {row[6]}, ATK: {row[7]}")
    
    # Clean up test user data
    economy.cur.execute("DELETE FROM user_cocks WHERE user_id=?", (test_user_id,))
    economy.conn.commit()

if __name__ == "__main__":
    main()
