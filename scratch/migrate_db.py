import sqlite3
import sys
from pathlib import Path

# Try to set stdout to UTF-8 to prevent console printing issues on Windows
try:
    sys.stdout.reconfigure(encoding='utf-8')
except AttributeError:
    pass

DB_PATH = Path("data/economy.db")

MAPPING = {
    "Gà Tre Vườn": "Usopp",
    "Gà Ri": "Krillin",
    "Gà Mía": "Zenitsu",
    "Gà Nòi": "Killua",
    "Gà Hồ": "Sakura",
    "Gà Tàu Vàng": "Trunks",
    "Gà Peru": "Levi Ackerman",
    "Gà Asil": "Zoro",
    "Gà Kelso": "Akame",
    "Gà Hatch": "Kakashi",
    "Gà Sweater": "Meliodas",
    "Gà Shamo": "Ichigo",
    "Gà Bạch Hổ": "Gojo Satoru",
    "Gà Hắc Kê": "Itachi Uchiha",
    "Gà Kim Ô": "Vegeta",
    "Gà Xích Long": "Goku (Ultra Instinct)",
    "Gà Thanh Long": "Luffy (Gear 5)",
    "Gà Chu Tước": "Naruto (Baryon Mode)",
    "Gà Huyền Vũ": "Saitama",
    "Gà Luffy": "Luffy",
    "Gà Luffy Gear 4": "Luffy Gear 4"
}

def migrate():
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH.resolve()}")
        return

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='user_cocks'")
        if not cur.fetchone():
            print("Table 'user_cocks' does not exist in the database.")
            return

        print("Checking existing chickens in database...")
        cur.execute("SELECT id, name, user_id FROM user_cocks")
        rows = cur.fetchall()
        print(f"Found {len(rows)} entries in user_cocks.")

        updated_count = 0
        for row_id, name, user_id in rows:
            # Handle possible encoding issues from DB text
            try:
                decoded_name = name
            except Exception:
                decoded_name = str(name)

            if decoded_name in MAPPING:
                new_name = MAPPING[decoded_name]
                cur.execute("UPDATE user_cocks SET name = ? WHERE id = ?", (new_name, row_id))
                try:
                    print(f"Updated Cock ID {row_id} (User {user_id}): name updated to '{new_name}'")
                except Exception:
                    print(f"Updated Cock ID {row_id} (User {user_id})")
                updated_count += 1

        if updated_count > 0:
            conn.commit()
            print(f"Successfully migrated {updated_count} chicken names to anime characters!")
        else:
            print("No matching chicken names found to migrate.")

    except Exception as e:
        conn.rollback()
        print(f"Error during migration: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
