import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy

def main():
    economy = Economy()
    old_name = "Gà Phượng Hoàng Lửa"
    new_name = "Gà Luffy"
    
    # Check how many cocks are named "Gà Phượng Hoàng Lửa"
    economy.cur.execute("SELECT count(*) FROM user_cocks WHERE name=?", (old_name,))
    count = economy.cur.fetchone()[0]
    
    if count > 0:
        economy.cur.execute("UPDATE user_cocks SET name=? WHERE name=?", (new_name, old_name))
        economy.conn.commit()
        print(f"Successfully migrated {count} chicken(s) from old name to new name.")
    else:
        print("No chickens with the old name found. Migration complete.")

if __name__ == "__main__":
    main()
