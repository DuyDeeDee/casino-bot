from __future__ import annotations

import os
import json
import time
import sqlite3
from contextlib import contextmanager
from typing import Optional, Dict, Any, List, Tuple
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
                    max_tinh_luc INTEGER DEFAULT 100,
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
                    is_meditating INTEGER DEFAULT 0,
                    meditate_start_time REAL,
                    meditate_duration_hours INTEGER DEFAULT 0,
                    last_meditation_end REAL,
                    last_nhapdinh_nhanh REAL,
                    last_boss_attack REAL,
                    continuous_cultivation_count INTEGER DEFAULT 0,
                    linh_luc_tap_chat INTEGER DEFAULT 0,
                    tau_hoa_nhap_ma_until REAL,
                    active_dao_domain TEXT
                )
            """)

            # Ensure column migration for existing tables safely
            existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(tutien_players)").fetchall()]
            all_cols = {
                "max_tinh_luc": "INTEGER DEFAULT 100",
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
                "gacha_pity_count": "INTEGER DEFAULT 0",
                "is_meditating": "INTEGER DEFAULT 0",
                "meditate_start_time": "REAL",
                "meditate_duration_hours": "INTEGER DEFAULT 0",
                "last_meditation_end": "REAL",
                "last_nhapdinh_nhanh": "REAL",
                "last_boss_attack": "REAL",
                "continuous_cultivation_count": "INTEGER DEFAULT 0",
                "linh_luc_tap_chat": "INTEGER DEFAULT 0",
                "tau_hoa_nhap_ma_until": "REAL",
                "active_dao_domain": "TEXT",
                "kinh_mach_doan_tuyet_until": "REAL",
                "lingering_debuff": "TEXT",
                "thanh_the_phu": "INTEGER DEFAULT 0",
                "van_linh_dan": "INTEGER DEFAULT 0",
                "cuu_chuyen_dan": "INTEGER DEFAULT 0",
                "last_cuop_time": "REAL",
                "pvp_elo": "INTEGER DEFAULT 1000",
                "danh_vong": "INTEGER DEFAULT 0",
                "pvp_wins": "INTEGER DEFAULT 0",
                "pvp_losses": "INTEGER DEFAULT 0",
                "pvp_streak": "INTEGER DEFAULT 0",
                "chan_thuong_until": "REAL",
                "mien_chien_until": "REAL",
                "body_realm_index": "INTEGER DEFAULT 0",
                "dong_phu_level": "INTEGER DEFAULT 1",
                "sect_id": "INTEGER",
                "sect_role": "TEXT",
                "can_co": "REAL DEFAULT 80.0",
                "tam_canh": "REAL DEFAULT 70.0",
                "dao_tam": "INTEGER DEFAULT 10",
                "ngo_tinh": "INTEGER DEFAULT 10",
                "hp": "INTEGER DEFAULT 1000",
                "max_hp": "INTEGER DEFAULT 1000",
                "mana": "INTEGER DEFAULT 500",
                "max_mana": "INTEGER DEFAULT 500",
                "than_thuc": "INTEGER DEFAULT 50",
                "nghiep_luc": "INTEGER DEFAULT 0",
                "co_duyen": "INTEGER DEFAULT 10",
                "thien_dao_diem": "INTEGER DEFAULT 0",
                "tinh_luc": "INTEGER DEFAULT 100"
            }
            for col_name, col_type in all_cols.items():
                if col_name not in existing_cols:
                    try:
                        conn.execute(f"ALTER TABLE tutien_players ADD COLUMN {col_name} {col_type}")
                    except Exception as e:
                        pass

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

            # Table: Bounties (Lệnh Truy Nã Huyết Sát)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_bounties (
                    bounty_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    target_user_id INTEGER NOT NULL,
                    issuer_user_id INTEGER NOT NULL,
                    reward_linh_thach INTEGER DEFAULT 0,
                    reward_tien_ngoc INTEGER DEFAULT 0,
                    reason TEXT DEFAULT 'Treo thưởng trảm trừ Ma Đầu!',
                    status TEXT DEFAULT 'OPEN',
                    created_at REAL NOT NULL
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

            # Table: World Boss Persistence
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_world_boss (
                    boss_id INTEGER PRIMARY KEY,
                    name TEXT DEFAULT '👹 Ma Vương Cổ Đại — Vô Cực Thi Cụ',
                    hp INTEGER DEFAULT 10000000,
                    max_hp INTEGER DEFAULT 10000000
                )
            """)

            # Table: PVE Progress & Tower
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_pve_progress (
                    user_id INTEGER PRIMARY KEY,
                    tower_floor INTEGER DEFAULT 1,
                    daily_tower_keys INTEGER DEFAULT 3,
                    last_tower_reset REAL,
                    boss_dps_today INTEGER DEFAULT 0,
                    phu_tai_sinh INTEGER DEFAULT 0
                )
            """)

            # Table: Daily Quests (Đạo Vụ Nhim Vụ Hàng Ngày)
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tutien_daily_quests (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    quest_date TEXT NOT NULL,
                    quest_type TEXT NOT NULL,
                    quest_name TEXT NOT NULL,
                    target_count INTEGER NOT NULL,
                    current_count INTEGER DEFAULT 0,
                    reward_type TEXT NOT NULL,
                    reward_amount INTEGER NOT NULL,
                    is_claimed INTEGER DEFAULT 0,
                    UNIQUE(user_id, quest_date, quest_type)
                )
            """)

            # Migration: thêm quest tracking columns vào tutien_players
            existing_cols = [row[1] for row in conn.execute("PRAGMA table_info(tutien_players)").fetchall()]
            quest_cols = {
                "daily_tu_luyen_count": "INTEGER DEFAULT 0",
                "daily_pve_kills": "INTEGER DEFAULT 0",
                "daily_pvp_wins": "INTEGER DEFAULT 0",
                "last_quest_reset": "REAL"
            }
            for col_name, col_type in quest_cols.items():
                if col_name not in existing_cols:
                    conn.execute(f"ALTER TABLE tutien_players ADD COLUMN {col_name} {col_type}")

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

    def get_player_by_dao_hieu(self, dao_hieu: str) -> Optional[CultivatorProfile]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT user_id FROM tutien_players WHERE LOWER(dao_hieu) = LOWER(?)", (dao_hieu.strip(),))
            row = cursor.fetchone()
            if not row:
                return None
            return self.get_player(row["user_id"])

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

    def delete_player(self, user_id: int):
        with self.get_connection() as conn:
            conn.execute("DELETE FROM tutien_players WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM tutien_gongfa WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM tutien_inventory WHERE user_id = ?", (user_id,))
            conn.execute("DELETE FROM tutien_pve_progress WHERE user_id = ?", (user_id,))

    def reset_all_players(self) -> int:
        """Xóa toàn bộ hồ sơ tu sĩ và tất cả dữ liệu liên quan (Inventory, Gongfa, PVE, Quests, Bounties, Auctions)."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) as count FROM tutien_players")
            row = cursor.fetchone()
            count = row["count"] if row else 0
            conn.execute("DELETE FROM tutien_players")
            conn.execute("DELETE FROM tutien_gongfa")
            conn.execute("DELETE FROM tutien_inventory")
            conn.execute("DELETE FROM tutien_pve_progress")
            conn.execute("DELETE FROM tutien_daily_quests")
            conn.execute("DELETE FROM tutien_bounties")
            conn.execute("DELETE FROM tutien_causality")
            conn.execute("DELETE FROM tutien_auctions")
            return count

    def get_top_cultivators(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, dao_hieu, realm_index, exp, linh_can_quality, linh_can_element, vip_level, linh_thach
                FROM tutien_players
                ORDER BY realm_index DESC, exp DESC, can_co DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["realm_name"] = REALMS[min(d["realm_index"], len(REALMS) - 1)]
                results.append(d)
            return results

    def get_top_wealthy(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, dao_hieu, realm_index, linh_thach, tien_ngoc, vip_level
                FROM tutien_players
                ORDER BY (linh_thach + (tien_ngoc * 1000)) DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["realm_name"] = REALMS[min(d["realm_index"], len(REALMS) - 1)]
                results.append(d)
            return results

    def update_player(self, player: CultivatorProfile):
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE tutien_players SET
                    dao_hieu = ?, realm_index = ?, exp = ?,
                    linh_can_quality = ?, linh_can_element = ?, is_di_linh_can = ?,
                    can_co = ?, tam_canh = ?, dao_tam = ?, ngo_tinh = ?,
                    hp = ?, max_hp = ?, mana = ?, max_mana = ?, than_thuc = ?,
                    nghiep_luc = ?, co_duyen = ?, thien_dao_diem = ?, tinh_luc = ?,
                    max_tinh_luc = ?,
                    body_realm_index = ?, dong_phu_level = ?, sect_id = ?, sect_role = ?,
                    linh_thach = ?, tien_ngoc = ?, linh_duyen_phu = ?, tien_duyen_phu = ?,
                    tay_tuy_phu = ?, linh_bui = ?, soft_pity_count = ?, wishlist_item = ?,
                    last_daily_fortune = ?, vip_level = ?, vip_exp = ?,
                    is_vip_pass = ?, vip_pass_expires = ?, array_protection_until = ?,
                    gacha_pity_count = ?, is_meditating = ?, meditate_start_time = ?,
                    meditate_duration_hours = ?, last_meditation_end = ?, last_nhapdinh_nhanh = ?, last_boss_attack = ?,
                    continuous_cultivation_count = ?, linh_luc_tap_chat = ?,
                    tau_hoa_nhap_ma_until = ?, active_dao_domain = ?,
                    kinh_mach_doan_tuyet_until = ?, lingering_debuff = ?, thanh_the_phu = ?,
                    van_linh_dan = ?, cuu_chuyen_dan = ?, last_cuop_time = ?,
                    pvp_elo = ?, danh_vong = ?, pvp_wins = ?, pvp_losses = ?,
                    pvp_streak = ?, chan_thuong_until = ?, mien_chien_until = ?
                WHERE user_id = ?
            """, (
                player.dao_hieu, player.realm_index, player.exp,
                player.linh_can_quality, player.linh_can_element, 1 if player.is_di_linh_can else 0,
                player.can_co, player.tam_canh, player.dao_tam, player.ngo_tinh,
                player.hp, player.max_hp, player.mana, player.max_mana, player.than_thuc,
                player.nghiep_luc, player.co_duyen, player.thien_dao_diem, player.tinh_luc,
                player.max_tinh_luc,
                player.body_realm_index, player.dong_phu_level, player.sect_id, player.sect_role,
                player.linh_thach, player.tien_ngoc, player.linh_duyen_phu, player.tien_duyen_phu,
                player.tay_tuy_phu, player.linh_bui, player.soft_pity_count, player.wishlist_item,
                player.last_daily_fortune, player.vip_level, player.vip_exp,
                1 if player.is_vip_pass else 0, player.vip_pass_expires, player.array_protection_until,
                player.gacha_pity_count, 1 if player.is_meditating else 0, player.meditate_start_time,
                player.meditate_duration_hours, player.last_meditation_end, player.last_nhapdinh_nhanh, player.last_boss_attack,
                player.continuous_cultivation_count, 1 if player.linh_luc_tap_chat else 0,
                player.tau_hoa_nhap_ma_until, player.active_dao_domain,
                player.kinh_mach_doan_tuyet_until, player.lingering_debuff, player.thanh_the_phu,
                player.van_linh_dan, player.cuu_chuyen_dan, player.last_cuop_time,
                player.pvp_elo, player.danh_vong, player.pvp_wins, player.pvp_losses,
                player.pvp_streak, player.chan_thuong_until, player.mien_chien_until,
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

    def get_inventory(self, user_id: int) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT item_name, item_type, quantity FROM tutien_inventory WHERE user_id = ?", (user_id,))
            return [dict(r) for r in cursor.fetchall()]

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

    # --- CHANNEL ENERGY & STAMINA RECOVERY METHODS ---
    def get_channel_linh_khi(self, channel_id: int) -> int:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT current_linh_khi FROM tutien_channel_energy WHERE channel_id = ?", (channel_id,))
            row = cursor.fetchone()
            if not row:
                conn.execute("INSERT INTO tutien_channel_energy (channel_id) VALUES (?)", (channel_id,))
                return 100000
            return row["current_linh_khi"]

    def consume_channel_linh_khi(self, channel_id: int, amount: int = 50):
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_channel_energy SET current_linh_khi = MAX(0, current_linh_khi - ?) WHERE channel_id = ?", (amount, channel_id))

    def recover_channel_linh_khi(self, amount: int = 5000):
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_channel_energy SET current_linh_khi = MIN(max_linh_khi, current_linh_khi + ?)", (amount,))

    def recover_all_players_tinh_luc(self, amount: int = 2):
        with self.get_connection() as conn:
            conn.execute(
                "UPDATE tutien_players SET tinh_luc = CASE WHEN (tinh_luc + ?) > max_tinh_luc THEN max_tinh_luc ELSE (tinh_luc + ?) END",
                (amount, amount)
            )

    # --- PVE PROGRESS & TOWER METHODS ---
    def get_pve_progress(self, user_id: int) -> dict:
        now = time.time()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tutien_pve_progress WHERE user_id = ?", (user_id,))
            row = cursor.fetchone()
            if not row:
                conn.execute(
                    "INSERT INTO tutien_pve_progress (user_id, tower_floor, daily_tower_keys, last_tower_reset, boss_dps_today, phu_tai_sinh) "
                    "VALUES (?, 1, 3, ?, 0, 0)",
                    (user_id, now)
                )
                return {
                    "user_id": user_id,
                    "tower_floor": 1,
                    "daily_tower_keys": 3,
                    "last_tower_reset": now,
                    "boss_dps_today": 0,
                    "phu_tai_sinh": 0
                }
            
            # Check daily reset for tower keys (24 hours)
            keys = row["daily_tower_keys"]
            last_reset = row["last_tower_reset"] or now
            if now - last_reset > 86400:
                keys = 3
                last_reset = now
                conn.execute("UPDATE tutien_pve_progress SET daily_tower_keys = 3, last_tower_reset = ? WHERE user_id = ?", (now, user_id))

            return {
                "user_id": row["user_id"],
                "tower_floor": row["tower_floor"],
                "daily_tower_keys": keys,
                "last_tower_reset": last_reset,
                "boss_dps_today": row["boss_dps_today"],
                "phu_tai_sinh": row["phu_tai_sinh"]
            }

    def update_pve_progress(self, user_id: int, tower_floor: int = None, daily_tower_keys: int = None, boss_dps_today: int = None, phu_tai_sinh: int = None):
        pve = self.get_pve_progress(user_id)
        new_tf = tower_floor if tower_floor is not None else pve["tower_floor"]
        new_keys = daily_tower_keys if daily_tower_keys is not None else pve["daily_tower_keys"]
        new_dps = boss_dps_today if boss_dps_today is not None else pve["boss_dps_today"]
        new_pts = phu_tai_sinh if phu_tai_sinh is not None else pve["phu_tai_sinh"]

        with self.get_connection() as conn:
            conn.execute(
                "UPDATE tutien_pve_progress SET tower_floor = ?, daily_tower_keys = ?, boss_dps_today = ?, phu_tai_sinh = ? WHERE user_id = ?",
                (new_tf, new_keys, new_dps, new_pts, user_id)
            )

    def get_tower_leaderboard(self, limit: int = 10):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT p.user_id, p.dao_hieu, pve.tower_floor FROM tutien_pve_progress pve "
                "JOIN tutien_players p ON pve.user_id = p.user_id "
                "ORDER BY pve.tower_floor DESC LIMIT ?", (limit,)
            )
            return cursor.fetchall()

    def update_world_boss_dps(self, user_id: int, damage: int):
        self.get_pve_progress(user_id)  # Ensure row exists
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_pve_progress SET boss_dps_today = boss_dps_today + ? WHERE user_id = ?", (damage, user_id))

    def get_world_boss_rankings(self, limit: int = 10):
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT p.user_id, p.dao_hieu, pve.boss_dps_today FROM tutien_pve_progress pve "
                "JOIN tutien_players p ON pve.user_id = p.user_id WHERE pve.boss_dps_today > 0 "
                "ORDER BY pve.boss_dps_today DESC LIMIT ?", (limit,)
            )
            return cursor.fetchall()

    def get_world_boss(self) -> Dict[str, Any]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tutien_world_boss WHERE boss_id = 1")
            row = cursor.fetchone()
            if not row:
                conn.execute("INSERT INTO tutien_world_boss (boss_id, name, hp, max_hp) VALUES (1, '👹 Ma Vương Cổ Đại — Vô Cực Thi Cụ', 10000000, 10000000)")
                return {"boss_id": 1, "name": "👹 Ma Vương Cổ Đại — Vô Cực Thi Cụ", "hp": 10000000, "max_hp": 10000000}
            return dict(row)

    def update_world_boss_hp(self, hp: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_world_boss SET hp = ? WHERE boss_id = 1", (hp,))

    # --- PVP & BOUNTY METHODS («Tu Sĩ Tranh Phong / Sát Lục») ---
    def get_pvp_leaderboard(self, limit: int = 10) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT user_id, dao_hieu, realm_index, pvp_elo, danh_vong, pvp_wins, pvp_losses, pvp_streak, vip_level
                FROM tutien_players
                ORDER BY pvp_elo DESC, danh_vong DESC, pvp_wins DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["realm_name"] = REALMS[min(d["realm_index"], len(REALMS) - 1)]
                results.append(d)
            return results

    def add_bounty(self, target_user_id: int, issuer_user_id: int, reward_linh_thach: int, reward_tien_ngoc: int = 0, reason: str = "Treo thưởng trảm trừ Ma Đầu!") -> int:
        now = time.time()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO tutien_bounties (target_user_id, issuer_user_id, reward_linh_thach, reward_tien_ngoc, reason, status, created_at)
                VALUES (?, ?, ?, ?, ?, 'OPEN', ?)
            """, (target_user_id, issuer_user_id, reward_linh_thach, reward_tien_ngoc, reason, now))
            return cursor.lastrowid

    def get_active_bounties(self, limit: int = 20) -> List[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT b.bounty_id, b.target_user_id, b.issuer_user_id, b.reward_linh_thach, b.reward_tien_ngoc,
                       b.reason, b.created_at, p.dao_hieu AS target_dao_hieu, p.realm_index AS target_realm_index,
                       p.nghiep_luc AS target_nghiep_luc, ip.dao_hieu AS issuer_dao_hieu
                FROM tutien_bounties b
                JOIN tutien_players p ON b.target_user_id = p.user_id
                JOIN tutien_players ip ON b.issuer_user_id = ip.user_id
                WHERE b.status = 'OPEN'
                ORDER BY b.reward_linh_thach DESC, b.created_at DESC
                LIMIT ?
            """, (limit,))
            rows = cursor.fetchall()
            results = []
            for r in rows:
                d = dict(r)
                d["target_realm_name"] = REALMS[min(d["target_realm_index"], len(REALMS) - 1)]
                results.append(d)
            return results

    def get_bounty_for_target(self, target_user_id: int) -> Optional[Dict[str, Any]]:
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT * FROM tutien_bounties WHERE target_user_id = ? AND status = 'OPEN' ORDER BY created_at DESC LIMIT 1
            """, (target_user_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def complete_bounty(self, bounty_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_bounties SET status = 'COMPLETED' WHERE bounty_id = ?", (bounty_id,))

    def cancel_bounty(self, bounty_id: int):
        with self.get_connection() as conn:
            conn.execute("UPDATE tutien_bounties SET status = 'CANCELLED' WHERE bounty_id = ?", (bounty_id,))

    # --- DAILY QUEST METHODS ---

    def get_or_generate_daily_quests(self, user_id: int, realm_index: int) -> List[Dict[str, Any]]:
        """Lấy hoặc tự sinh 3 Đạo Vụ ngày hôm nay cho người chơi."""
        import random
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")

        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tutien_daily_quests WHERE user_id = ? AND quest_date = ?",
                (user_id, today)
            )
            rows = cursor.fetchall()
            if rows:
                return [dict(r) for r in rows]

            # Sinh 3 quest ngẫu nhiên dựa theo realm_index
            tu_target = max(5, 8 + realm_index // 3)
            pve_target = max(3, 3 + realm_index // 5)
            pvp_target = max(1, 1 + realm_index // 10)

            quests_to_create = [
                {
                    "quest_type": "tu_luyen",
                    "quest_name": f"Chuyên Tâm Tu Đạo ({tu_target} lần tu luyện)",
                    "target_count": tu_target,
                    "reward_type": "linh_thach",
                    "reward_amount": 500 + realm_index * 50,
                },
                {
                    "quest_type": "pve_kills",
                    "quest_name": f"Diệt Yêu Trừ Ma ({pve_target} trận PVE thắng)",
                    "target_count": pve_target,
                    "reward_type": random.choice(["tien_ngoc", "linh_duyen_phu"]),
                    "reward_amount": 10 if "tien_ngoc" else 1,
                },
                {
                    "quest_type": "pvp_wins",
                    "quest_name": f"Thiên Kiêu Tranh Phong ({pvp_target} trận PVP thắng)",
                    "target_count": pvp_target,
                    "reward_type": "linh_thach",
                    "reward_amount": 1000 + realm_index * 100,
                },
            ]
            # Fix reward_amount cho pve_kills
            quests_to_create[1]["reward_amount"] = 10 if quests_to_create[1]["reward_type"] == "tien_ngoc" else 2

            for q in quests_to_create:
                conn.execute("""
                    INSERT OR IGNORE INTO tutien_daily_quests
                    (user_id, quest_date, quest_type, quest_name, target_count, reward_type, reward_amount)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (user_id, today, q["quest_type"], q["quest_name"],
                      q["target_count"], q["reward_type"], q["reward_amount"]))

            cursor.execute(
                "SELECT * FROM tutien_daily_quests WHERE user_id = ? AND quest_date = ?",
                (user_id, today)
            )
            return [dict(r) for r in cursor.fetchall()]

    def increment_quest_progress(self, user_id: int, quest_type: str, amount: int = 1) -> Optional[Dict[str, Any]]:
        """Tăng tiến độ quest. Trả về quest nếu vừa hoàn thành (để notify)."""
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tutien_daily_quests WHERE user_id = ? AND quest_date = ? AND quest_type = ?",
                (user_id, today, quest_type)
            )
            row = cursor.fetchone()
            if not row:
                return None
            q = dict(row)
            if q["is_claimed"] or q["current_count"] >= q["target_count"]:
                return None  # Đã đủ / đã nhận
            new_count = min(q["target_count"], q["current_count"] + amount)
            conn.execute(
                "UPDATE tutien_daily_quests SET current_count = ? WHERE id = ?",
                (new_count, q["id"])
            )
            q["current_count"] = new_count
            if new_count >= q["target_count"]:
                return q  # Vừa hoàn thành
            return None

    def claim_quest_reward(self, user_id: int, quest_type: str) -> Optional[Dict[str, Any]]:
        """Nhận phần thưởng quest đã hoàn thành. Trả về quest dict nếu thành công."""
        from datetime import datetime
        today = datetime.utcnow().strftime("%Y-%m-%d")
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT * FROM tutien_daily_quests WHERE user_id = ? AND quest_date = ? AND quest_type = ?",
                (user_id, today, quest_type)
            )
            row = cursor.fetchone()
            if not row:
                return None
            q = dict(row)
            if q["is_claimed"]:
                return None
            if q["current_count"] < q["target_count"]:
                return None
            conn.execute(
                "UPDATE tutien_daily_quests SET is_claimed = 1 WHERE id = ?",
                (q["id"],)
            )
            # Trao phần thưởng vào player
            if q["reward_type"] == "linh_thach":
                conn.execute("UPDATE tutien_players SET linh_thach = linh_thach + ? WHERE user_id = ?",
                             (q["reward_amount"], user_id))
            elif q["reward_type"] == "tien_ngoc":
                conn.execute("UPDATE tutien_players SET tien_ngoc = tien_ngoc + ? WHERE user_id = ?",
                             (q["reward_amount"], user_id))
            elif q["reward_type"] == "linh_duyen_phu":
                conn.execute("UPDATE tutien_players SET linh_duyen_phu = linh_duyen_phu + ? WHERE user_id = ?",
                             (q["reward_amount"], user_id))
            return q

    # --- 🏪 SÀN ĐẤU GIÁ & CHỢ TU TIÊN (AUCTION HOUSE) ---

    def create_auction(self, seller_id: int, item_name: str, quantity: int, price: int, duration_hours: int = 24) -> Optional[int]:
        """Tạo phiên đấu giá bán vật phẩm trên Sàn Giao Dịch."""
        expires_at = time.time() + (duration_hours * 3600)
        with self.get_connection() as conn:
            # Kiểm tra vật phẩm trong túi đồ của seller
            cursor = conn.cursor()
            cursor.execute("SELECT id, quantity, item_type FROM tutien_inventory WHERE user_id = ? AND item_name = ?", (seller_id, item_name))
            row = cursor.fetchone()
            if not row or row["quantity"] < quantity:
                return None

            item_type = row["item_type"]
            # Trừ vật phẩm từ túi đồ
            if row["quantity"] == quantity:
                conn.execute("DELETE FROM tutien_inventory WHERE id = ?", (row["id"],))
            else:
                conn.execute("UPDATE tutien_inventory SET quantity = quantity - ? WHERE id = ?", (quantity, row["id"]))

            # Thêm vào tutien_auctions
            cursor.execute(
                "INSERT INTO tutien_auctions (seller_id, item_name, quantity, price, expires_at) VALUES (?, ?, ?, ?, ?)",
                (seller_id, item_name, quantity, price, expires_at)
            )
            return cursor.lastrowid

    def get_active_auctions(self, limit: int = 20) -> List[Dict[str, Any]]:
        """Lấy danh sách các món đồ đang được bày bán trên Sàn Đấu Giá."""
        now = time.time()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                SELECT a.*, p.dao_hieu as seller_name
                FROM tutien_auctions a
                LEFT JOIN tutien_players p ON a.seller_id = p.user_id
                WHERE a.expires_at > ?
                ORDER BY a.auction_id DESC
                LIMIT ?
            """, (now, limit))
            return [dict(r) for r in cursor.fetchall()]

    def get_auction(self, auction_id: int) -> Optional[Dict[str, Any]]:
        """Lấy thông tin 1 phiên đấu giá theo ID."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tutien_auctions WHERE auction_id = ?", (auction_id,))
            row = cursor.fetchone()
            return dict(row) if row else None

    def buy_auction_item(self, buyer_id: int, auction_id: int) -> Tuple[bool, str]:
        """Mua vật phẩm từ Sàn Đấu Giá (Áp dụng 5% Phí Thuế Thiêu Đốt Linh Thạch)."""
        now = time.time()
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tutien_auctions WHERE auction_id = ?", (auction_id,))
            auc = cursor.fetchone()
            if not auc:
                return False, "❌ Phiên đấu giá không tồn tại hoặc đã bị hủy!"
            if auc["expires_at"] <= now:
                return False, "❌ Phiên đấu giá này đã hết hạn bày bán!"
            if auc["seller_id"] == buyer_id:
                return False, "❌ Bạn không thể tự mua vật phẩm do chính mình đăng bán!"

            # Kiểm tra số dư Linh Thạch của người mua
            cursor.execute("SELECT linh_thach, dao_hieu FROM tutien_players WHERE user_id = ?", (buyer_id,))
            buyer = cursor.fetchone()
            if not buyer or buyer["linh_thach"] < auc["price"]:
                return False, f"❌ Không đủ Linh Thạch! Cần `{auc['price']:,}` Linh Thạch."

            # Trừ tiền người mua
            conn.execute("UPDATE tutien_players SET linh_thach = linh_thach - ? WHERE user_id = ?", (auc["price"], buyer_id))

            # Tính phí thuế sàn 5% (Linh Thạch Sink)
            tax = int(auc["price"] * 0.05)
            seller_receive = auc["price"] - tax

            # Cộng tiền cho người bán
            conn.execute("UPDATE tutien_players SET linh_thach = linh_thach + ? WHERE user_id = ?", (seller_receive, auc["seller_id"]))

            # Thêm vật phẩm vào túi người mua
            cursor.execute("SELECT id FROM tutien_inventory WHERE user_id = ? AND item_name = ?", (buyer_id, auc["item_name"]))
            inv_row = cursor.fetchone()
            if inv_row:
                conn.execute("UPDATE tutien_inventory SET quantity = quantity + ? WHERE id = ?", (auc["quantity"], inv_row["id"]))
            else:
                conn.execute("INSERT INTO tutien_inventory (user_id, item_name, item_type, quantity) VALUES (?, ?, 'Giao Dịch', ?)",
                             (buyer_id, auc["item_name"], auc["quantity"]))

            # Xóa khỏi sàn đấu giá
            conn.execute("DELETE FROM tutien_auctions WHERE auction_id = ?", (auction_id,))

            msg = f"✨ **MUA HÀNG THÀNH CÔNG!** Đã mua `{auc['quantity']}x` **[{auc['item_name']}]** với giá `{auc['price']:,}` Linh Thạch (Phí thuế 5% `{tax:,}` LT đã bị thiêu đốt)!"
            return True, msg

    def cancel_auction(self, seller_id: int, auction_id: int) -> Tuple[bool, str]:
        """Hủy đăng bán và nhận lại vật phẩm về túi đồ."""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM tutien_auctions WHERE auction_id = ?", (auction_id,))
            auc = cursor.fetchone()
            if not auc:
                return False, "❌ Phiên đấu giá không tồn tại!"
            if auc["seller_id"] != seller_id:
                return False, "❌ Bạn không phải là người sở hữu phiên đấu giá này!"

            # Trả lại đồ về túi
            cursor.execute("SELECT id FROM tutien_inventory WHERE user_id = ? AND item_name = ?", (seller_id, auc["item_name"]))
            inv_row = cursor.fetchone()
            if inv_row:
                conn.execute("UPDATE tutien_inventory SET quantity = quantity + ? WHERE id = ?", (auc["quantity"], inv_row["id"]))
            else:
                conn.execute("INSERT INTO tutien_inventory (user_id, item_name, item_type, quantity) VALUES (?, ?, 'Vật Phẩm', ?)",
                             (seller_id, auc["item_name"], auc["quantity"]))

            conn.execute("DELETE FROM tutien_auctions WHERE auction_id = ?", (auction_id,))
            return True, f"✨ Đã hủy đăng bán phiên `#{auction_id}` và hoàn trả `{auc['quantity']}x` **[{auc['item_name']}]** vào Túi Đồ!"



