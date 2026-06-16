import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy

def main():
    economy = Economy()
    economy.cur.execute("SELECT id, user_id, name, rarity, hp, atk, df, spd, luk FROM user_cocks WHERE rarity='Exclusive'")
    rows = economy.cur.fetchall()
    
    print(f"Total Exclusive cocks found: {len(rows)}")
    for row in rows:
        # Avoid printing name directly to avoid Unicode cp1252 print errors on Windows console, print ASCII fallback
        ascii_name = row[2].encode('ascii', errors='replace').decode('ascii')
        print(f"ID: {row[0]}, UserID: {row[1]}, Name: {ascii_name}, Rarity: {row[3]}, HP: {row[4]}, ATK: {row[5]}, DEF: {row[6]}, SPD: {row[7]}, LUK: {row[8]}")

if __name__ == "__main__":
    main()
