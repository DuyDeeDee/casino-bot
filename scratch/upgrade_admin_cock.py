import os
import sys

# Ensure project root is in python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.discord_bot.modules.economy import Economy

def main():
    economy = Economy()
    admin_id = 756026481020239874
    cock_id = 410
    
    # 1. Fetch current cock info
    economy.cur.execute("SELECT id, name, hp, atk, df, spd, luk FROM user_cocks WHERE id=? AND user_id=?", (cock_id, admin_id))
    row = economy.cur.fetchone()
    
    if not row:
        print("Admin's cock with ID 410 was not found in the database.")
        return
        
    print(f"Current Admin Cock Info - ID: {row[0]}, Name: {row[1]}, HP: {row[2]}, ATK: {row[3]}, DEF: {row[4]}, SPD: {row[5]}, LUK: {row[6]}")
    
    # 2. Calculate 6-star stats with the 2.0x Gear 4 boost
    # Starting stats: HP=556, ATK=114, DEF=85, SPD=98, LUK=60
    # From 0 to 5 stars, stats grow by 10% on each star upgrade: stats * (1.1^5)
    # At 6 stars, stats double (2.0x boost)
    
    multiplier = (1.1 ** 5) * 2.0  # ~3.221x the base stats
    
    new_hp = int(row[2] * multiplier)
    new_atk = int(row[3] * multiplier)
    new_df = int(row[4] * multiplier)
    new_spd = int(row[5] * multiplier)
    new_luk = int(row[6] * multiplier)
    
    new_name = "Gà Luffy Gear 4"
    
    # 3. Equip full Mythic gear
    weapon = "cua_diet_than"
    armor = "giap_than_thu"
    charm = "linh_chau"
    
    # 4. Update the DB row
    economy.cur.execute(
        """UPDATE user_cocks 
           SET name=?, stars=6, shards=0, hp=?, atk=?, df=?, spd=?, luk=?, 
               weapon=?, armor=?, charm=?
           WHERE id=? AND user_id=?""",
        (new_name, new_hp, new_atk, new_df, new_spd, new_luk, weapon, armor, charm, cock_id, admin_id)
    )
    economy.conn.commit()
    
    print("Successfully upgraded admin's cock to 6-star Gà Luffy Gear 4 with full Mythic gear!")
    print(f"New Stats - HP: {new_hp}, ATK: {new_atk}, DEF: {new_df}, SPD: {new_spd}, LUK: {new_luk}")
    print(f"Equipped: Weapon={weapon}, Armor={armor}, Charm={charm}")

if __name__ == "__main__":
    main()
