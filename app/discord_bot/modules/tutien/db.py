"""
Database Manager for Tu Tien System (`tutien.db`)
Includes Monetization Schema, VIP Progression, Gacha Tickets & Safe Connection Context Management.
"""

import os
import json
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any, List
from app.discord_bot.modules.tutien.constants import REALMS, REALM_REQUIRED_EXP, BODY_REALMS
from app.discord_bot.modules.tutien.models import CultivatorProfile, GongfaEquipment, SectModel

DB_PATH = "tutien.db"


class TuTienDB:
    def __init__(self, db_path: str = DB_PATH):
        self.db_path = db_path
        self._init_db()

    @contextmanager
    def get_connection(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self):
        with self.get_connection() as conn:
            # Table: Players (With Monetization & Gacha Schema)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_players (
                    user_id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    dao_hieu TEXT NOT NULL,
                    realm_index INTEGER DEFAULT 0,
                    exp INTEGER DEFAULT 0,
                    linh_can_quality TEXT DEFAULT 'Phàm Phẩm',
                    linh_can_element TEXT DEFAULT '🔥 Hỏa',
                    is_di_linh_can INTEGER DEFAULT 0,
                    can_co REAL DEFAULT 80.0,
                    tam_canh REAL DEFAULT 70.0,
                    dao_tam INTEGER DEFAULT 10,
                    ngo_tinh INTEGER DEFAULT 10,
                    hp INTEGER DEFAULT 1000,
                    max_hp INTEGER DEFAULT 1000,
                    mana INTEGER DEFAULT 500,
                    max_mana INTEGER DEFAULT 500,
                    than_thuc INTEGER DEFAULT 50,
                    nghiep_luc INTEGER DEFAULT 0,
                    co_duyen INTEGER DEFAULT 10,
                    thien_dao_diem INTEGER DEFAULT 0,
                    tinh_luc INTEGER DEFAULT 100,
                    body_realm_index INTEGER DEFAULT 0,
                    dong_phu_level INTEGER DEFAULT 1,
                    sect_id INTEGER,
                    sect_role TEXT,
                    linh_thach INTEGER DEFAULT 500,
                    tien_ngoc INTEGER DEFAULT 0,
                    linh_duyen_phu INTEGER DEFAULT 0,
                    tien_duyen_phu INTEGER DEFAULT 0,
                    tay_tuy_phu INTEGER DEFAULT 0,
                    linh_bui INTEGER DEFAULT 0,
                    soft_pity_count INTEGER DEFAULT 0,
                    wishlist_item TEXT,
                    last_daily_fortune REAL,
                    vip_level INTEGER DEFAULT 0,
                    vip_exp INTEGER DEFAULT 0,
                    is_vip_pass INTEGER DEFAULT 0,
                    vip_pass_expires REAL,
                    array_protection_until REAL,
                    gacha_pity_count INTEGER DEFAULT 0,
                    is_meditating INTEGER DEFAULT 0,
                    meditate_start_time REAL,
                    meditate_duration_hours INTEGER DEFAULT 0,
                    tau_hoa_nhap_ma_until REAL,
                    active_dao_domain TEXT
                )
            """)

            # Ensure column migration for existing tables
            existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(tutien_players)").fetchall()]
            new_cols = {
                "tien_ngoc": "INTEGER DEFAULT 0",
                "linh_duyen_phu": "INTEGER DEFAULT 0",
                "tien_duyen_phu": "INTEGER DEFAULT 0",
                "tay_tuy_phu": "INTEGER DEFAULT 0",
                "linh_bui": "INTEGER DEFAULT 0",
                "soft_pity_count": "INTEGER DEFAULT 0",
                "wishlist_item": "TEXT",
                "last_daily_fortune": "REAL",
                "vip_level": "INTEGER DEFAULT 0",
                "vip_exp": "INTEGER DEFAULT 0",
                "is_vip_pass": "INTEGER DEFAULT 0",
                "vip_pass_expires": "REAL",
                "array_protection_until": "REAL",
                "gacha_pity_count": "INTEGER DEFAULT 0"
            }
            for col_name, col_type in new_cols.items():
                if col_name not in existing_cols:
                    conn.execute(f"ALTER TABLE tutien_players ADD COLUMN {col_name} {col_type}")

            # Table: Gongfa
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_gongfa (
                    user_id INTEGER PRIMARY KEY,
                    chu_tu TEXT DEFAULT '《Phàm Nhân Quyết》',
                    tam_phap TEXT,
                    luyen_the TEXT,
                    than_phap TEXT,
                    bi_thuat_json TEXT DEFAULT '[]'
                )
            """)

            # Table: Inventory
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_inventory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    item_type TEXT NOT NULL,
                    quantity INTEGER DEFAULT 1
                )
            """)

            # Table: Sects
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_sects (
                    sect_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT UNIQUE NOT NULL,
                    leader_id INTEGER NOT NULL,
                    treasury_linh_thach INTEGER DEFAULT 0,
                    level INTEGER DEFAULT 1,
                    occupied_channel_id INTEGER
                )
            """)

            # Table: Dynamic Channel Linh Khi
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_channel_energy (
                    channel_id INTEGER PRIMARY KEY,
                    current_linh_khi INTEGER DEFAULT 100000,
                    max_linh_khi INTEGER DEFAULT 100000
                )
            """)

            # Table: Causality NPC Memory
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_causality (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    flag_name TEXT NOT NULL,
                    flag_value INTEGER DEFAULT 1,
                    created_at REAL
                )
            """)

            # Table: Sàn Đấu Giá (Auction House)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_auctions (
                    auction_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    seller_id INTEGER NOT NULL,
                    item_name TEXT NOT NULL,
                    quantity INTEGER DEFAULT 1,
                    price INTEGER NOT NULL,
                    expires_at REAL NOT NULL
                )
            """)

    # --- PLAYER METHODS ---
    def get_player(self, user_id: int) -> Optional[CultivatorProfile]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tutien_players WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return None
            
            d = dict(row)
            d["realm_name"] = REALMS[min(d["realm_index"], len(REALMS) - 1)]
            d["required_exp"] = REALM_REQUIRED_EXP.get(d["realm_index"], 1000000000)
            d["body_realm_name"] = BODY_REALMS[min(d["body_realm_index"], len(BODY_REALMS) - 1)]
            
            if d.get("sect_id"):
                cursor.execute("SELECT name FROM tutien_sects WHERE sect_id = ?", (d["sect_id"],))
                sect_row = cursor.fetchone()
                if sect_row:
                    d["sect_name"] = sect_row["name"]
            
            return CultivatorProfile(**d)

    def create_player(self, user_id: int, guild_id: int, dao_hieu: str, quality: str, element: str, is_di: bool) -> CultivatorProfile:
        with self.get_connection() as conn:
            conn.execute("""
                INSERT INTO tutien_players (user_id, guild_id, dao_hieu, linh_can_quality, linh_can_element, is_di_linh_can)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (user_id, guild_id, dao_hieu, quality, element, 1 if is_di else 0))
            
            conn.execute("""
                INSERT INTO tutien_gongfa (user_id, chu_tu)
                VALUES (?, '《Phàm Nhân Quyết》')
            """, (user_id,))

        return self.get_player(user_id)

    def update_player(self, player: CultivatorProfile):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE tutien_players SET
                    dao_hieu = ?, realm_index = ?, exp = ?,
                    linh_can_quality = ?, linh_can_element = ?, is_di_linh_can = ?,
                    can_co = ?, tam_canh = ?, dao_tam = ?, ngo_tinh = ?,
                    hp = ?, max_hp = ?, mana = ?, max_mana = ?, than_thuc = ?,
                    nghiep_luc = ?, co_duyen = ?, thien_dao_diem = ?, tinh_luc = ?,
                    body_realm_index = ?, dong_phu_level = ?, sect_id = ?, sect_role = ?,
                    linh_thach = ?, tien_ngoc = ?, linh_duyen_phu = ?, tien_duyen_phu = ?,
                    tay_tuy_phu = ?, linh_bui = ?, soft_pity_count = ?, wishlist_item = ?,
                    last_daily_fortune = ?, vip_level = ?, vip_exp = ?,
                    is_vip_pass = ?, vip_pass_expires = ?, array_protection_until = ?,
                    gacha_pity_count = ?, is_meditating = ?, meditate_start_time = ?,
                    meditate_duration_hours = ?, tau_hoa_nhap_ma_until = ?, active_dao_domain = ?
                WHERE user_id = ?
            """, (
                player.dao_hieu, player.realm_index, player.exp,
                player.linh_can_quality, player.linh_can_element, 1 if player.is_di_linh_can else 0,
                player.can_co, player.tam_canh, player.dao_tam, player.ngo_tinh,
                player.hp, player.max_hp, player.mana, player.max_mana, player.than_thuc,
                player.nghiep_luc, player.co_duyen, player.thien_dao_diem, player.tinh_luc,
                player.body_realm_index, player.dong_phu_level, player.sect_id, player.sect_role,
                player.linh_thach, player.tien_ngoc, player.linh_duyen_phu, player.tien_duyen_phu,
                player.tay_tuy_phu, player.linh_bui, player.soft_pity_count, player.wishlist_item,
                player.last_daily_fortune, player.vip_level, player.vip_exp,
                1 if player.is_vip_pass else 0, player.vip_pass_expires, player.array_protection_until,
                player.gacha_pity_count, 1 if player.is_meditating else 0, player.meditate_start_time,
                player.meditate_duration_hours, player.tau_hoa_nhap_ma_until, player.active_dao_domain,
                player.user_id
            ))

    # --- INVENTORY METHODS ---
    def add_item(self, user_id: int, item_name: str, item_type: str, quantity: int = 1):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, quantity FROM tutien_inventory WHERE user_id = ? AND item_name = ?", (user_id, item_name))
            row = cursor.fetchone()
            if row:
                conn.execute("UPDATE tutien_inventory SET quantity = quantity + ? WHERE id = ?", (quantity, row["id"]))
            else:
                conn.execute("INSERT INTO tutien_inventory (user_id, item_name, item_type, quantity) VALUES (?, ?, ?, ?)",
                             (user_id, item_name, item_type, quantity))

    def has_item(self, user_id: int, item_name: str) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT quantity FROM tutien_inventory WHERE user_id = ? AND item_name = ?", (user_id, item_name))
            row = cursor.fetchone()
            return row is not None and row["quantity"] > 0

    def consume_item(self, user_id: int, item_name: str, quantity: int = 1) -> bool:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, quantity FROM tutien_inventory WHERE user_id = ? AND item_name = ?", (user_id, item_name))
            row = cursor.fetchone()
            if not row or row["quantity"] < quantity:
                return False
            if row["quantity"] == quantity:
                conn.execute("DELETE FROM tutien_inventory WHERE id = ?", (row["id"],))
            else:
                conn.execute("UPDATE tutien_inventory SET quantity = quantity - ? WHERE id = ?", (quantity, row["id"]))
            return True

    # --- GONGFA METHODS ---
    def get_gongfa(self, user_id: int) -> GongfaEquipment:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tutien_gongfa WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                return GongfaEquipment(user_id=user_id)
            d = dict(row)
            d["bi_thuat"] = json.loads(d.get("bi_thuat_json") or "[]")
            return GongfaEquipment(**d)

    def update_gongfa(self, gongfa: GongfaEquipment):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE tutien_gongfa SET
                    chu_tu = ?, tam_phap = ?, luyen_the = ?, than_phap = ?, bi_thuat_json = ?
                WHERE user_id = ?
            """, (
                gongfa.chu_tu, gongfa.tam_phap, gongfa.luyen_the, gongfa.than_phap,
                json.dumps(gongfa.bi_thuat), gongfa.user_id
            ))

    # --- CHANNEL LINH KHI METHODS ---
    def get_channel_linh_khi(self, channel_id: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_linh_khi FROM tutien_channel_energy WHERE channel_id = ?", (channel_id,))
            row = cursor.fetchone()
            if row:
                return row["current_linh_khi"]
            else:
                conn.execute("INSERT INTO tutien_channel_energy (channel_id, current_linh_khi) VALUES (?, 100000)", (channel_id,))
                return 100000

    def consume_channel_linh_khi(self, channel_id: int, amount: int = 50) -> int:
        current = self.get_channel_linh_khi(channel_id)
        new_val = max(0, current - amount)
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_channel_energy SET current_linh_khi = ? WHERE channel_id = ?", (new_val, channel_id))
        return new_val

    def recover_all_channels_linh_khi(self, amount: int = 5000):
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_channel_energy SET current_linh_khi = MIN(max_linh_khi, current_linh_khi + ?)", (amount,))

    def recover_all_players_tinh_luc(self, amount: int = 10):
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_players SET tinh_luc = MIN(max_tinh_luc, tinh_luc + ?)", (amount,))
