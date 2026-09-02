from collections.abc import Callable
import functools
import json
import logging
import random
import shutil
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Tuple, List

from app.config import config

Entry = Tuple[int, int, int]
DATABASE_PATH = Path(config.storage.database_path)
LEGACY_DATABASE_PATH = Path(__file__).resolve().parents[3] / "economy.db"
SCHEMA_VERSION = 52


logger = logging.getLogger(__name__)


# Daily quest templates: 3 random quests per day, progress tracked by event hooks.
DAILY_QUEST_POOL: list[dict] = [
    {"id": "mine", "event": "mine", "desc": "Đào mỏ {target} lần", "target": 2, "reward_money": 250_000, "reward_gold": 0.2, "emoji": "⛏️"},
    {"id": "work", "event": "work", "desc": "Làm việc {target} lần", "target": 3, "reward_money": 150_000, "reward_gold": 0.0, "emoji": "💼"},
    {"id": "casino", "event": "casino_win", "desc": "Thắng {target} ván cờ bạc", "target": 3, "reward_money": 400_000, "reward_gold": 0.1, "emoji": "🎰"},
    {"id": "buy", "event": "buyitem", "desc": "Mua {target} vật phẩm ở cửa hàng", "target": 1, "reward_money": 100_000, "reward_gold": 0.0, "emoji": "🛒"},
    {"id": "rob", "event": "rob", "desc": "Cướp thành công {target} lần", "target": 1, "reward_money": 250_000, "reward_gold": 0.0, "emoji": "🔪"},
    {"id": "collect", "event": "collect", "desc": "Thu hoạch doanh nghiệp {target} lần", "target": 1, "reward_money": 150_000, "reward_gold": 0.1, "emoji": "🏭"},
]


def _migration_1_create_economy(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS economy (
        user_id INTEGER NOT NULL PRIMARY KEY,
        money INTEGER NOT NULL DEFAULT 0,
        credits INTEGER NOT NULL DEFAULT 0
    )"""
    )


def _migration_2_add_indexes(cur: sqlite3.Cursor) -> None:
    cur.execute("CREATE INDEX IF NOT EXISTS idx_economy_money ON economy(money DESC)")


def _migration_3_add_claimed_start(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN claimed_start INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_4_add_loan_columns(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN loan_amount INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN loan_due INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_5_add_market_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS system_settings (
            key TEXT NOT NULL PRIMARY KEY,
            value TEXT NOT NULL
        )"""
        )
        cur.execute(
            "INSERT OR IGNORE INTO system_settings(key, value) VALUES('gold_price', '10000000')"
        )
        cur.execute(
            "INSERT OR IGNORE INTO system_settings(key, value) VALUES('gold_price_prev', '10000000')"
        )
    except sqlite3.OperationalError:
        pass


def _migration_6_add_simulator_tables(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_businesses (
            user_id INTEGER NOT NULL,
            biz_id TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, biz_id)
        )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_portfolio (
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            shares REAL NOT NULL DEFAULT 0.0,
            PRIMARY KEY (user_id, symbol)
        )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS stock_prices (
            symbol TEXT NOT NULL PRIMARY KEY,
            price INTEGER NOT NULL,
            prev_price INTEGER NOT NULL,
            change_percent REAL NOT NULL DEFAULT 0.0
        )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_inventory (
            user_id INTEGER NOT NULL,
            item_id TEXT NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, item_id)
        )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_simulator_stats (
            user_id INTEGER PRIMARY KEY,
            last_collect INTEGER DEFAULT 0,
            last_mine INTEGER DEFAULT 0,
            last_rob INTEGER DEFAULT 0,
            fractional_gold REAL DEFAULT 0.0
        )"""
        )
        
        # Populate initial stock prices
        cur.execute("INSERT OR IGNORE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES('BTC', 1000000, 1000000, 0.0)")
        cur.execute("INSERT OR IGNORE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES('CASINO', 100000, 100000, 0.0)")
        cur.execute("INSERT OR IGNORE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES('AGV', 10000, 10000, 0.0)")
        
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_topups (
            user_id INTEGER NOT NULL PRIMARY KEY,
            total_vnd INTEGER NOT NULL DEFAULT 0,
            total_gold INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_7_add_daily_columns(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN last_daily INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN daily_streak INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_8_add_daga_tables(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN pity_golden INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_cocks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            rarity TEXT NOT NULL,
            level INTEGER NOT NULL DEFAULT 1,
            exp INTEGER NOT NULL DEFAULT 0,
            hp INTEGER NOT NULL,
            atk INTEGER NOT NULL,
            df INTEGER NOT NULL,
            spd INTEGER NOT NULL,
            luk INTEGER NOT NULL,
            weapon TEXT DEFAULT 'None',
            armor TEXT DEFAULT 'None',
            charm TEXT DEFAULT 'None',
            is_active INTEGER DEFAULT 0,
            wins INTEGER DEFAULT 0,
            losses INTEGER DEFAULT 0,
            streak INTEGER DEFAULT 0,
            last_train INTEGER DEFAULT 0,
            stars INTEGER DEFAULT 0,
            shards INTEGER DEFAULT 0
        )"""
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cocks_user ON user_cocks(user_id)")
    except sqlite3.OperationalError:
        pass



def _migration_9_add_equipped_banner(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN equipped_banner TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass


def _migration_10_add_garage_tables(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_cars (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            model TEXT NOT NULL,
            rarity TEXT NOT NULL,
            serial INTEGER NOT NULL,
            edition TEXT NOT NULL,
            collection TEXT NOT NULL,
            is_favorite INTEGER DEFAULT 0
        )"""
        )
        cur.execute("CREATE INDEX IF NOT EXISTS idx_cars_user ON user_cars(user_id)")
        
        cur.execute(
            """CREATE TABLE IF NOT EXISTS car_market (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            car_id INTEGER NOT NULL,
            seller_id INTEGER NOT NULL,
            price INTEGER NOT NULL,
            created_at INTEGER NOT NULL
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_11_update_car_names(cur: sqlite3.Cursor) -> None:
    try:
        updates = {
            "Mazda RX7 FD": "Mazda 3",
            "Mitsubishi Lancer Evolution IX": "Mitsubishi Outlander",
            "Lamborghini Huracan": "Lamborghini",
            "Ferrari F8": "Ferrari SF90 Stradale",
            "Subaru WRX STI": "Hyundai Elantra",
            "McLaren P1": "Aston Martin",
            "Porsche 918 Spyder": "Chevrolet Corvette",
            "Venom F5": "Dodge Challenger",
            "Pagani Huayra": "Rolls-Royce Phantom",
            "Koenigsegg Regera": "Tesla Model S"
        }
        for old_name, new_name in updates.items():
            cur.execute("UPDATE user_cars SET model = ? WHERE model = ?", (new_name, old_name))
            
        cur.execute("UPDATE user_cars SET collection = 'JDM' WHERE model IN ('Mazda 3', 'Mitsubishi Outlander', 'Hyundai Elantra')")
        cur.execute("UPDATE user_cars SET collection = 'Hypercar' WHERE model IN ('Aston Martin', 'Lamborghini', 'Chevrolet Corvette', 'Dodge Challenger', 'Ferrari SF90 Stradale', 'Rolls-Royce Phantom', 'Tesla Model S')")
    except sqlite3.OperationalError:
        pass


def _migration_12_add_last_work(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_simulator_stats ADD COLUMN last_work INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_13_add_cock_stars_and_shards(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_cocks ADD COLUMN stars INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE user_cocks ADD COLUMN shards INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_14_add_roulette_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_roulette (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            chips INTEGER NOT NULL DEFAULT 0,
            number_stats TEXT NOT NULL DEFAULT '{}',
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_15_add_coinflip_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_coinflip (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            max_win_amount INTEGER NOT NULL DEFAULT 0,
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_16_add_showcase_treasure(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE economy ADD COLUMN showcase_treasure TEXT DEFAULT NULL")
    except sqlite3.OperationalError:
        pass


def _migration_17_add_bkb_tables(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_bkb (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            draws INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0
        )"""
        )
        cur.execute(
            """CREATE TABLE IF NOT EXISTS bkb_h2h (
            player_one INTEGER NOT NULL,
            player_two INTEGER NOT NULL,
            player_one_wins INTEGER NOT NULL DEFAULT 0,
            player_two_wins INTEGER NOT NULL DEFAULT 0,
            draws INTEGER NOT NULL DEFAULT 0,
            profit_transfer INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (player_one, player_two)
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_18_add_baito_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_baito (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            point_9_wins INTEGER NOT NULL DEFAULT 0,
            batay_wins INTEGER NOT NULL DEFAULT 0,
            bacao_wins INTEGER NOT NULL DEFAULT 0,
            baat_wins INTEGER NOT NULL DEFAULT 0,
            all_in_plays INTEGER NOT NULL DEFAULT 0,
            blind_plays INTEGER NOT NULL DEFAULT 0,
            blind_wins INTEGER NOT NULL DEFAULT 0,
            max_blind_win_amount INTEGER NOT NULL DEFAULT 0,
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_19_add_pve_tables(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_pve_cooldowns (
            user_id INTEGER NOT NULL,
            stage_type TEXT NOT NULL,
            last_fight INTEGER DEFAULT 0,
            PRIMARY KEY (user_id, stage_type)
        )"""
        )
    except sqlite3.OperationalError:
        pass

    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_world_boss_damage (
            user_id INTEGER NOT NULL PRIMARY KEY,
            damage INTEGER DEFAULT 0,
            fights_today INTEGER DEFAULT 0,
            last_fight_time INTEGER DEFAULT 0
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_20_add_banned_users_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS banned_users (
            user_id INTEGER PRIMARY KEY,
            banned_at INTEGER NOT NULL
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_21_add_mines_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_mines (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_22_add_plinko_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_plinko (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            jackpots INTEGER NOT NULL DEFAULT 0,
            max_multiplier REAL NOT NULL DEFAULT 0.0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_23_add_highlow_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_highlow (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            max_multiplier REAL NOT NULL DEFAULT 0.0,
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_24_add_stock_history_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS stock_price_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            price INTEGER NOT NULL,
            timestamp INTEGER NOT NULL
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_25_add_limit_orders(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS limit_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            symbol TEXT NOT NULL,
            order_type TEXT NOT NULL,
            target_price INTEGER NOT NULL,
            shares REAL NOT NULL,
            created_at INTEGER NOT NULL
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_26_add_simulator_upgrades(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_simulator_stats ADD COLUMN manager_expiry INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE user_simulator_stats ADD COLUMN insurance_expiry INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE user_simulator_stats ADD COLUMN bodyguard_expiry INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE user_simulator_stats ADD COLUMN pickaxe_level INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_27_initialize_all_cryptos(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("INSERT OR IGNORE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES('USDT', 25000, 25000, 0.0)")
        cur.execute("INSERT OR IGNORE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES('ETH', 500000, 500000, 0.0)")
        cur.execute("INSERT OR IGNORE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES('SOL', 80000, 80000, 0.0)")
        cur.execute("INSERT OR IGNORE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES('DOGE', 5000, 5000, 0.0)")
    except sqlite3.OperationalError:
        pass


def _migration_28_add_marry_tables(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("""CREATE TABLE IF NOT EXISTS user_marry (
            user_one INTEGER NOT NULL,
            user_two INTEGER NOT NULL,
            ring_type TEXT NOT NULL,
            love_points INTEGER DEFAULT 0,
            joint_wallet INTEGER DEFAULT 0,
            married_at INTEGER NOT NULL,
            last_interact_time INTEGER DEFAULT 0,
            interacts_today INTEGER DEFAULT 0,
            PRIMARY KEY (user_one, user_two)
        )""")
        cur.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_marry_users ON user_marry(user_one, user_two)")
    except sqlite3.OperationalError:
        pass


def _migration_29_add_marry_custom_columns(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_marry ADD COLUMN user_one_ig TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE user_marry ADD COLUMN user_two_ig TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE user_marry ADD COLUMN status TEXT DEFAULT 'Vợ Chồng'")
    except sqlite3.OperationalError:
        pass


def _migration_30_add_marry_saying_column(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_marry ADD COLUMN saying TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass


def _migration_31_add_tower_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_tower (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_32_add_user_titles_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_titles (
            user_id INTEGER NOT NULL,
            title TEXT NOT NULL,
            PRIMARY KEY (user_id, title)
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_33_add_achievements_log_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_achievements_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            game TEXT NOT NULL,
            achievement_key TEXT NOT NULL,
            unlocked_at INTEGER NOT NULL
        )"""
        )
        # Seed the achievements log table from existing game stats
        import json
        import time
        now = int(time.time())
        tables = {
            'user_roulette': 'Roulette',
            'user_coinflip': 'Coinflip',
            'user_highlow': 'Highlow',
            'user_mines': 'Mines',
            'user_plinko': 'Plinko',
            'user_tower': 'Tower'
        }
        idx = 0
        for table, game_name in tables.items():
            try:
                cur.execute(f"SELECT user_id, achievements FROM {table}")
                rows = cur.fetchall()
                for user_id, ach_str in rows:
                    try:
                        ach_list = json.loads(ach_str)
                        for ach in ach_list:
                            # Stagger the insertion timestamp slightly to preserve a stable sequence
                            cur.execute(
                                "SELECT 1 FROM user_achievements_log WHERE user_id = ? AND game = ? AND achievement_key = ?",
                                (user_id, game_name, ach)
                            )
                            if not cur.fetchone():
                                cur.execute(
                                    "INSERT INTO user_achievements_log (user_id, game, achievement_key, unlocked_at) VALUES (?, ?, ?, ?)",
                                    (user_id, game_name, ach, now + idx)
                                )
                                idx += 1
                    except Exception:
                        pass
            except sqlite3.OperationalError:
                pass
    except sqlite3.OperationalError:
        pass


def _migration_34_add_marry_interest_and_wish_columns(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_marry ADD COLUMN last_interest_time INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass
    try:
        cur.execute("ALTER TABLE user_marry ADD COLUMN last_wish_time INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_35_add_giaima_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_giaima (
            user_id INTEGER NOT NULL PRIMARY KEY,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            profit INTEGER NOT NULL DEFAULT 0,
            streak INTEGER NOT NULL DEFAULT 0,
            max_streak INTEGER NOT NULL DEFAULT 0,
            last_free_play INTEGER NOT NULL DEFAULT 0,
            achievements TEXT NOT NULL DEFAULT '[]'
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_36_add_couple_assets(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS couple_assets (
            user_one INTEGER NOT NULL,
            user_two INTEGER NOT NULL,
            estate_id TEXT DEFAULT NULL,
            estate_price INTEGER DEFAULT 0,
            estate_bought_by INTEGER DEFAULT 0,
            vehicle_id TEXT DEFAULT NULL,
            vehicle_price INTEGER DEFAULT 0,
            vehicle_bought_by INTEGER DEFAULT 0,
            pet_id TEXT DEFAULT NULL,
            pet_price INTEGER DEFAULT 0,
            pet_bought_by INTEGER DEFAULT 0,
            PRIMARY KEY (user_one, user_two)
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_37_update_gold_price_to_30m(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("UPDATE system_settings SET value = '30000000' WHERE key IN ('gold_price', 'gold_price_prev')")
    except sqlite3.OperationalError:
        pass


def _migration_38_reset_gold_price_prev_to_30m(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("UPDATE system_settings SET value = '30000000' WHERE key IN ('gold_price', 'gold_price_prev')")
    except sqlite3.OperationalError:
        pass



def _migration_39_add_user_topups_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_topups (
            user_id INTEGER NOT NULL PRIMARY KEY,
            total_vnd INTEGER NOT NULL DEFAULT 0,
            total_gold INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL DEFAULT 0
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_41_add_masoi_vip_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS masoi_vip (
            user_id INTEGER NOT NULL PRIMARY KEY,
            expires_at INTEGER NOT NULL DEFAULT 0,
            last_words TEXT DEFAULT ''
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_42_add_masoi_custom_badge(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_masoi_stats ADD COLUMN custom_badge TEXT DEFAULT ''")
    except sqlite3.OperationalError:
        pass


def _migration_40_add_masoi_tables(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_masoi_stats (
            user_id INTEGER NOT NULL PRIMARY KEY,
            points INTEGER NOT NULL DEFAULT 0,
            plays INTEGER NOT NULL DEFAULT 0,
            wins INTEGER NOT NULL DEFAULT 0,
            losses INTEGER NOT NULL DEFAULT 0,
            wolf_wins INTEGER NOT NULL DEFAULT 0,
            villager_wins INTEGER NOT NULL DEFAULT 0,
            tanner_wins INTEGER NOT NULL DEFAULT 0,
            custom_badge TEXT DEFAULT ''
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_43_add_jail_table(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("PRAGMA table_info(user_jail)")
        columns = cur.fetchall()
        if columns:
            pk_cols = [col for col in columns if col[5] > 0]
            if len(pk_cols) < 2:
                cur.execute("DROP TABLE user_jail")

        cur.execute(
            """CREATE TABLE IF NOT EXISTS user_jail (
            user_id INTEGER NOT NULL,
            guild_id INTEGER NOT NULL DEFAULT 0,
            jailer_id INTEGER NOT NULL DEFAULT 0,
            clean_count INTEGER NOT NULL DEFAULT 0,
            total_clean_count INTEGER NOT NULL DEFAULT 0,
            reason TEXT DEFAULT 'Không có lý do',
            jailed_at INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY (user_id, guild_id)
        )"""
        )
    except sqlite3.OperationalError:
        pass


def _migration_44_add_missing_indexes(cur: sqlite3.Cursor) -> None:
    cur.execute("CREATE INDEX IF NOT EXISTS idx_portfolio_symbol ON user_portfolio(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_stock_history_symbol ON stock_price_history(symbol, id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_limit_orders_symbol ON limit_orders(symbol)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_marry_user_one ON user_marry(user_one)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_marry_user_two ON user_marry(user_two)")


def _migration_45_add_daily_quests(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS user_daily_quests (
        user_id INTEGER PRIMARY KEY,
        quest_date TEXT NOT NULL,
        quests_json TEXT NOT NULL
    )"""
    )

def _migration_46_add_work_xp(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_simulator_stats ADD COLUMN work_xp INTEGER DEFAULT 0")
    except sqlite3.OperationalError:
        pass

def _migration_47_add_bank_and_sports_tables(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS user_bank_deposits (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        amount INTEGER NOT NULL,
        term_days INTEGER NOT NULL,
        rate REAL NOT NULL,
        deposit_at INTEGER NOT NULL,
        FOREIGN KEY(user_id) REFERENCES economy(user_id)
    )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS match_bets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        outcome TEXT NOT NULL,
        amount INTEGER NOT NULL
    )"""
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_bank_deposits_user ON user_bank_deposits(user_id)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_match_bets_match ON match_bets(match_id, outcome)")


def _migration_48_add_gift_code_tables(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS gift_codes (
        code TEXT PRIMARY KEY,
        reward_money INTEGER DEFAULT 0,
        reward_credits REAL DEFAULT 0,
        max_uses INTEGER DEFAULT 0,
        used_count INTEGER DEFAULT 0,
        expires_at INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL
    )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS gift_code_claims (
        code TEXT NOT NULL,
        user_id INTEGER NOT NULL,
        claimed_at INTEGER NOT NULL,
        PRIMARY KEY (code, user_id)
    )"""
    )





def _migration_49_add_member_levels(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS member_levels (
        user_id INTEGER PRIMARY KEY,
        xp INTEGER NOT NULL DEFAULT 0,
        level INTEGER NOT NULL DEFAULT 0,
        last_chat_xp REAL NOT NULL DEFAULT 0
    )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS give_daily (
        user_id INTEGER NOT NULL,
        day TEXT NOT NULL,
        sent_money INTEGER NOT NULL DEFAULT 0,
        received_money INTEGER NOT NULL DEFAULT 0,
        sent_gold INTEGER NOT NULL DEFAULT 0,
        received_gold INTEGER NOT NULL DEFAULT 0,
        PRIMARY KEY (user_id, day)
    )"""
    )


def _migration_50_portfolio_avg_cost(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("ALTER TABLE user_portfolio ADD COLUMN avg_cost REAL NOT NULL DEFAULT 0")
    except sqlite3.OperationalError:
        pass


def _migration_51_update_gold_price_to_10m(cur: sqlite3.Cursor) -> None:
    try:
        cur.execute("UPDATE system_settings SET value = '10000000' WHERE key IN ('gold_price', 'gold_price_prev')")
    except sqlite3.OperationalError:
        pass


def _migration_52_add_sports_engine_v2(cur: sqlite3.Cursor) -> None:
    cur.execute(
        """CREATE TABLE IF NOT EXISTS sports_matches (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        season_id INTEGER DEFAULT 1,
        round_num INTEGER DEFAULT 1,
        t1 TEXT NOT NULL,
        t2 TEXT NOT NULL,
        t1_rating REAL DEFAULT 4.0,
        t2_rating REAL DEFAULT 4.0,
        kickoff INTEGER NOT NULL,
        status TEXT NOT NULL DEFAULT 'upcoming',
        score_t1 INTEGER DEFAULT 0,
        score_t2 INTEGER DEFAULT 0,
        minute INTEGER DEFAULT 0,
        result TEXT DEFAULT NULL,
        sim_seed TEXT DEFAULT NULL,
        channel_id INTEGER DEFAULT 0,
        message_id INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        settled_at INTEGER DEFAULT 0
    )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS sports_bet_tickets (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        user_id INTEGER NOT NULL,
        market TEXT NOT NULL DEFAULT '1X2',
        outcome TEXT NOT NULL,
        amount INTEGER NOT NULL,
        base_odds REAL NOT NULL DEFAULT 1.0,
        status TEXT NOT NULL DEFAULT 'pending',
        payout INTEGER DEFAULT 0,
        created_at INTEGER NOT NULL,
        settled_at INTEGER DEFAULT 0,
        FOREIGN KEY(match_id) REFERENCES sports_matches(id)
    )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS sports_match_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL,
        minute INTEGER NOT NULL,
        event_type TEXT NOT NULL,
        team TEXT,
        text TEXT NOT NULL,
        created_at INTEGER NOT NULL,
        FOREIGN KEY(match_id) REFERENCES sports_matches(id)
    )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS sports_settlements (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        match_id INTEGER NOT NULL UNIQUE,
        total_pool INTEGER NOT NULL,
        rake_amount INTEGER NOT NULL,
        rounding_to_jackpot INTEGER NOT NULL,
        total_payout INTEGER NOT NULL,
        house_contribution INTEGER NOT NULL DEFAULT 0,
        result TEXT NOT NULL,
        settled_at INTEGER NOT NULL,
        FOREIGN KEY(match_id) REFERENCES sports_matches(id)
    )"""
    )
    cur.execute(
        """CREATE TABLE IF NOT EXISTS sports_league_table (
        season_id INTEGER NOT NULL,
        team_code TEXT NOT NULL,
        played INTEGER DEFAULT 0,
        won INTEGER DEFAULT 0,
        drawn INTEGER DEFAULT 0,
        lost INTEGER DEFAULT 0,
        gf INTEGER DEFAULT 0,
        ga INTEGER DEFAULT 0,
        points INTEGER DEFAULT 0,
        form TEXT DEFAULT '',
        PRIMARY KEY (season_id, team_code)
    )"""
    )
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sports_matches_status ON sports_matches(status, kickoff)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sports_tickets_match ON sports_bet_tickets(match_id, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sports_tickets_user ON sports_bet_tickets(user_id, status)")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_sports_events_match ON sports_match_events(match_id, minute)")


MIGRATIONS: dict[int, Callable[[sqlite3.Cursor], None]] = {
    1: _migration_1_create_economy,
    2: _migration_2_add_indexes,
    3: _migration_3_add_claimed_start,
    4: _migration_4_add_loan_columns,
    5: _migration_5_add_market_table,
    6: _migration_6_add_simulator_tables,
    7: _migration_7_add_daily_columns,
    8: _migration_8_add_daga_tables,
    9: _migration_9_add_equipped_banner,
    10: _migration_10_add_garage_tables,
    11: _migration_11_update_car_names,
    12: _migration_12_add_last_work,
    13: _migration_13_add_cock_stars_and_shards,
    14: _migration_14_add_roulette_table,
    15: _migration_15_add_coinflip_table,
    16: _migration_16_add_showcase_treasure,
    17: _migration_17_add_bkb_tables,
    18: _migration_18_add_baito_table,
    19: _migration_19_add_pve_tables,
    20: _migration_20_add_banned_users_table,
    21: _migration_21_add_mines_table,
    22: _migration_22_add_plinko_table,
    23: _migration_23_add_highlow_table,
    24: _migration_24_add_stock_history_table,
    25: _migration_25_add_limit_orders,
    26: _migration_26_add_simulator_upgrades,
    27: _migration_27_initialize_all_cryptos,
    28: _migration_28_add_marry_tables,
    29: _migration_29_add_marry_custom_columns,
    30: _migration_30_add_marry_saying_column,
    31: _migration_31_add_tower_table,
    32: _migration_32_add_user_titles_table,
    33: _migration_33_add_achievements_log_table,
    34: _migration_34_add_marry_interest_and_wish_columns,
    35: _migration_35_add_giaima_table,
    36: _migration_36_add_couple_assets,
    37: _migration_37_update_gold_price_to_30m,
    38: _migration_38_reset_gold_price_prev_to_30m,
    39: _migration_39_add_user_topups_table,
    40: _migration_40_add_masoi_tables,
    41: _migration_41_add_masoi_vip_table,
    42: _migration_42_add_masoi_custom_badge,
    43: _migration_43_add_jail_table,
    44: _migration_44_add_missing_indexes,
    45: _migration_45_add_daily_quests,
    46: _migration_46_add_work_xp,
    47: _migration_47_add_bank_and_sports_tables,
    48: _migration_48_add_gift_code_tables,
    49: _migration_49_add_member_levels,
    50: _migration_50_portfolio_avg_cost,
    51: _migration_51_update_gold_price_to_10m,
    52: _migration_52_add_sports_engine_v2,
}


class Economy:
    """A wrapper for the economy database"""

    def __init__(self):
        self._lock = threading.RLock()
        self._txn_depth = 0
        self.open()

    @contextmanager
    def transaction(self):
        """Groups multiple statements into one atomic commit.

        Usage:
            with economy.transaction():
                economy.add_money(a, -100)
                economy.add_money(b, 100)
        Nested calls reuse the outer transaction; only the outermost
        block commits.
        """
        with self._lock:
            self._txn_depth += 1
            try:
                yield self
                if self._txn_depth == 1:
                    self.conn.commit()
            except Exception:
                if self._txn_depth == 1:
                    self.conn.rollback()
                raise
            finally:
                self._txn_depth -= 1

    def open(self):
        """Initializes the database"""
        if (
            DATABASE_PATH != LEGACY_DATABASE_PATH
            and not DATABASE_PATH.exists()
            and LEGACY_DATABASE_PATH.exists()
        ):
            DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(LEGACY_DATABASE_PATH, DATABASE_PATH)
            logger.info(
                "Copied legacy economy database from %s to %s",
                LEGACY_DATABASE_PATH,
                DATABASE_PATH,
            )
        self.conn = sqlite3.connect(str(DATABASE_PATH), timeout=30, check_same_thread=False)
        self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.execute("PRAGMA synchronous=NORMAL")
        self.conn.execute("PRAGMA cache_size=-64000")  # 64MB cache
        self.conn.execute("PRAGMA busy_timeout=10000")  # 10s busy timeout
        self.cur = self.conn.cursor()
        self._run_migrations()
        self.conn.commit()

    def _run_migrations(self) -> None:
        self.cur.execute(
            """CREATE TABLE IF NOT EXISTS schema_version (
            id INTEGER PRIMARY KEY CHECK (id = 1),
            version INTEGER NOT NULL
        )"""
        )
        self.cur.execute(
            "INSERT OR IGNORE INTO schema_version(id, version) VALUES(1, 0)"
        )
        self.cur.execute("SELECT version FROM schema_version WHERE id=1")
        row = self.cur.fetchone()
        current_version = int(row[0]) if row else 0

        if current_version > SCHEMA_VERSION:
            raise RuntimeError(
                f"Database schema version {current_version} is newer than supported {SCHEMA_VERSION}."
            )

        for target_version in range(current_version + 1, SCHEMA_VERSION + 1):
            migration = MIGRATIONS.get(target_version)
            if migration is None:
                raise RuntimeError(
                    f"Missing migration for schema version {target_version}."
                )
            migration(self.cur)
            self.cur.execute(
                "UPDATE schema_version SET version=? WHERE id=1",
                (target_version,),
            )
            logger.info("Applied economy database migration version=%s", target_version)

    def close(self):
        """Safely closes the database"""
        if getattr(self, "conn", None):
            self.conn.commit()
            if getattr(self, "cur", None):
                self.cur.close()
            self.conn.close()
            self.cur = None
            self.conn = None

    def __del__(self):
        try:
            self.close()
        except Exception:
            pass

    def _ensure_entry(self, user_id: int) -> None:
        self.cur.execute(
            "INSERT OR IGNORE INTO economy(user_id, money, credits) VALUES(?, ?, ?)",
            (user_id, 0, 0),
        )

    def _fetch_entry(self, user_id: int) -> Entry:
        self.cur.execute(
            "SELECT user_id, money, credits FROM economy WHERE user_id=?",
            (user_id,),
        )
        result = self.cur.fetchone()
        if result is None:
            raise RuntimeError(f"failed to fetch economy entry for user_id={user_id}")
        return result

    def get_entry(self, user_id: int) -> Entry:
        self._ensure_entry(user_id)
        self.conn.commit()
        return self._fetch_entry(user_id)

    def new_entry(self, user_id: int) -> Entry:
        self._ensure_entry(user_id)
        self.conn.commit()
        return self._fetch_entry(user_id)

    def remove_entry(self, user_id: int) -> None:
        self.cur.execute("DELETE FROM economy WHERE user_id=?", (user_id,))
        self.conn.commit()

    def reset_all_data(self) -> None:
        """Reset toàn bộ dữ liệu kinh tế, ví tiền, tài sản và tiến trình của tất cả người chơi."""
        tables_to_clear = [
            "economy",
            "user_businesses",
            "user_portfolio",
            "limit_orders",
            "stock_price_history",
            "user_inventory",
            "user_simulator_stats",
            "user_baito",
            "user_bank_deposits",
            "user_topups",
            "user_cars",
            "car_market",
            "user_cocks",
            "user_marry",
            "couple_assets",
            "user_jail",
            "user_daily_quests",
            "match_bets",
            "sports_matches",
            "sports_bet_tickets",
            "sports_match_events",
            "sports_settlements",
            "sports_league_table",
            "gift_code_claims",
            "member_levels",
            "give_daily",
            "user_titles",
            "user_achievements_log",
            "user_roulette",
            "user_tower",
            "user_giaima",
            "user_mines",
            "user_plinko",
            "user_highlow",
            "user_coinflip",
            "user_bkb",
            "bkb_h2h",
            "user_pve_cooldowns",
            "user_world_boss_damage",
            "masoi_vip",
            "user_masoi_stats",
            "wallet_transactions",
        ]
        for tbl in tables_to_clear:
            try:
                self.cur.execute(f"DELETE FROM {tbl}")
            except sqlite3.OperationalError:
                pass

        # Reset giá vàng, giá cổ phiếu và lượt dùng giftcode về mức cơ sở
        try:
            self.cur.execute("UPDATE system_settings SET value='10000000' WHERE key IN ('gold_price', 'gold_price_prev')")
            self.cur.execute("UPDATE stock_prices SET price=1000000, prev_price=1000000, change_percent=0.0 WHERE symbol='BTC'")
            self.cur.execute("UPDATE stock_prices SET price=100000, prev_price=100000, change_percent=0.0 WHERE symbol='CASINO'")
            self.cur.execute("UPDATE stock_prices SET price=10000, prev_price=10000, change_percent=0.0 WHERE symbol='AGV'")
            self.cur.execute("UPDATE gift_codes SET used_count=0")
        except sqlite3.OperationalError:
            pass

        self.conn.commit()

    def has_claimed_start(self, user_id: int) -> bool:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT claimed_start FROM economy WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return bool(row[0]) if row else False

    def set_claimed_start(self, user_id: int) -> None:
        self._ensure_entry(user_id)
        self.cur.execute("UPDATE economy SET claimed_start=1 WHERE user_id=?", (user_id,))
        self.conn.commit()

    def get_daily(self, user_id: int) -> Tuple[int, int]:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT last_daily, daily_streak FROM economy WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row if row else (0, 0)

    def set_daily(self, user_id: int, last_daily: int, daily_streak: int) -> None:
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET last_daily=?, daily_streak=? WHERE user_id=?",
            (int(last_daily), int(daily_streak), user_id),
        )
        self.conn.commit()

    def get_loan(self, user_id: int) -> Tuple[int, int]:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT loan_amount, loan_due FROM economy WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row if row else (0, 0)

    def set_loan(self, user_id: int, amount: int, due_timestamp: int) -> None:
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET loan_amount=?, loan_due=? WHERE user_id=?",
            (int(amount), int(due_timestamp), user_id),
        )
        self.conn.commit()

    def clear_loan(self, user_id: int) -> None:
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET loan_amount=0, loan_due=0 WHERE user_id=?",
            (user_id,),
        )
        self.conn.commit()

    def set_money(self, user_id: int, money: int) -> Entry:
        money = max(0, int(money))
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET money=? WHERE user_id=?",
            (money, user_id),
        )
        self.conn.commit()
        return self._fetch_entry(user_id)

    def set_credits(self, user_id: int, credits: int) -> Entry:
        credits = max(0, int(credits))
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET credits=? WHERE user_id=?",
            (credits, user_id),
        )
        self.conn.commit()
        return self._fetch_entry(user_id)

    def add_money(self, user_id: int, money_to_add: int) -> Entry:
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET money=MAX(0, money + ?) WHERE user_id=?",
            (int(money_to_add), user_id),
        )
        self.conn.commit()
        return self._fetch_entry(user_id)

    def _record_gold_flow(self, delta: int) -> None:
        """Tracks weekly gold supply/demand used by the gold price updater."""
        if not delta:
            return
        key = "gold_mined_week" if delta > 0 else "gold_spent_week"
        self.cur.execute(
            "UPDATE system_settings SET value = CAST(CAST(value AS INTEGER) + ? AS TEXT) WHERE key = ?",
            (abs(delta), key),
        )
        if self.cur.rowcount == 0:
            self.cur.execute(
                "INSERT INTO system_settings(key, value) VALUES(?, ?)",
                (key, str(abs(delta))),
            )

    def payout_winnings(self, user_id: int, gross_winnings: int, stake: int = 0) -> int:
        """Credits gambling winnings after the global casino tax.

        Tax only applies to net profit (gross - stake); the returned stake
        is never taxed. Deducted tax goes into the shared jackpot pool
        (system_settings key 'jackpot_pool'). Returns the net amount paid.
        """
        gross_winnings = max(0, int(gross_winnings))
        profit = max(0, gross_winnings - max(0, int(stake)))
        if profit == 0:
            self.add_money(user_id, gross_winnings)
            return gross_winnings

        rate = float(self.get_setting("casino_tax_rate", "0.05"))
        tax = min(int(profit * rate), profit)
        net = gross_winnings - tax

        with self.transaction():
            self.add_money(user_id, net)
            pool = int(self.get_setting("jackpot_pool", "0"))
            self.set_setting("jackpot_pool", str(pool + tax))
        self.bump_quest(user_id, "casino_win")
        return net

    def get_jackpot_pool(self) -> int:
        return int(self.get_setting("jackpot_pool", "0"))

    # --- BANK DEPOSITS ---
    def get_bank_deposits(self, user_id: int) -> list:
        self.cur.execute(
            "SELECT id, amount, term_days, rate, deposit_at FROM user_bank_deposits WHERE user_id=? ORDER BY deposit_at",
            (user_id,),
        )
        return self.cur.fetchall()

    def get_bank_total(self, user_id: int) -> int:
        self.cur.execute("SELECT COALESCE(SUM(amount), 0) FROM user_bank_deposits WHERE user_id=?", (user_id,))
        return int(self.cur.fetchone()[0])

    def add_bank_deposit(self, user_id: int, amount: int, term_days: int, rate: float) -> int:
        self._ensure_entry(user_id)
        self.cur.execute(
            "INSERT INTO user_bank_deposits(user_id, amount, term_days, rate, deposit_at) VALUES(?, ?, ?, ?, ?)",
            (user_id, int(amount), int(term_days), float(rate), int(time.time())),
        )
        self.conn.commit()
        return self.cur.lastrowid

    def get_bank_deposit(self, deposit_id: int) -> tuple | None:
        self.cur.execute("SELECT id, user_id, amount, term_days, rate, deposit_at FROM user_bank_deposits WHERE id=?", (deposit_id,))
        return self.cur.fetchone()

    def remove_bank_deposit(self, deposit_id: int) -> None:
        self.cur.execute("DELETE FROM user_bank_deposits WHERE id=?", (deposit_id,))
        self.conn.commit()

    def get_bank_stats(self) -> tuple[int, int]:
        self.cur.execute("SELECT COALESCE(SUM(amount), 0), COUNT(*) FROM user_bank_deposits")
        row = self.cur.fetchone()
        return (int(row[0]), int(row[1]))

    # --- SPORTS MATCHES & TICKETS V2 ---
    def create_sports_match(
        self,
        t1: str,
        t2: str,
        kickoff: int,
        t1_rating: float = 4.0,
        t2_rating: float = 4.0,
        season_id: int = 1,
        round_num: int = 1,
        sim_seed: str = "",
    ) -> int:
        self.cur.execute(
            """INSERT INTO sports_matches(season_id, round_num, t1, t2, t1_rating, t2_rating, kickoff, status, sim_seed, created_at)
            VALUES(?, ?, ?, ?, ?, ?, ?, 'upcoming', ?, ?)""",
            (int(season_id), int(round_num), t1, t2, float(t1_rating), float(t2_rating), int(kickoff), sim_seed, int(time.time())),
        )
        self.conn.commit()
        return self.cur.lastrowid

    def get_sports_match(self, match_id: int) -> dict | None:
        self.cur.execute(
            """SELECT id, season_id, round_num, t1, t2, t1_rating, t2_rating, kickoff, status,
                      score_t1, score_t2, minute, result, sim_seed, channel_id, message_id, created_at, settled_at
            FROM sports_matches WHERE id=?""",
            (int(match_id),),
        )
        row = self.cur.fetchone()
        if not row:
            return None
        return {
            "id": row[0], "season_id": row[1], "round_num": row[2], "t1": row[3], "t2": row[4],
            "t1_rating": row[5], "t2_rating": row[6], "kickoff": row[7], "status": row[8],
            "score_t1": row[9], "score_t2": row[10], "minute": row[11], "result": row[12],
            "sim_seed": row[13], "channel_id": row[14], "message_id": row[15],
            "created_at": row[16], "settled_at": row[17],
        }

    def get_upcoming_sports_matches(self, limit: int = 10) -> list[dict]:
        self.cur.execute(
            """SELECT id, season_id, round_num, t1, t2, t1_rating, t2_rating, kickoff, status,
                      score_t1, score_t2, minute, result, sim_seed, channel_id, message_id, created_at, settled_at
            FROM sports_matches
            WHERE status='upcoming'
            ORDER BY kickoff ASC LIMIT ?""",
            (int(limit),),
        )
        rows = self.cur.fetchall()
        return [
            {
                "id": r[0], "season_id": r[1], "round_num": r[2], "t1": r[3], "t2": r[4],
                "t1_rating": r[5], "t2_rating": r[6], "kickoff": r[7], "status": r[8],
                "score_t1": r[9], "score_t2": r[10], "minute": r[11], "result": r[12],
                "sim_seed": r[13], "channel_id": r[14], "message_id": r[15],
                "created_at": r[16], "settled_at": r[17],
            }
            for r in rows
        ]

    def get_live_sports_matches(self) -> list[dict]:
        self.cur.execute(
            """SELECT id, season_id, round_num, t1, t2, t1_rating, t2_rating, kickoff, status,
                      score_t1, score_t2, minute, result, sim_seed, channel_id, message_id, created_at, settled_at
            FROM sports_matches
            WHERE status='live'
            ORDER BY kickoff ASC""",
        )
        rows = self.cur.fetchall()
        return [
            {
                "id": r[0], "season_id": r[1], "round_num": r[2], "t1": r[3], "t2": r[4],
                "t1_rating": r[5], "t2_rating": r[6], "kickoff": r[7], "status": r[8],
                "score_t1": r[9], "score_t2": r[10], "minute": r[11], "result": r[12],
                "sim_seed": r[13], "channel_id": r[14], "message_id": r[15],
                "created_at": r[16], "settled_at": r[17],
            }
            for r in rows
        ]

    def update_sports_match_live(
        self,
        match_id: int,
        minute: int,
        score_t1: int,
        score_t2: int,
        message_id: int = 0,
        channel_id: int = 0,
        status: str = "live",
    ) -> None:
        params = [int(minute), int(score_t1), int(score_t2), status]
        query = "UPDATE sports_matches SET minute=?, score_t1=?, score_t2=?, status=?"
        if message_id > 0:
            query += ", message_id=?"
            params.append(int(message_id))
        if channel_id > 0:
            query += ", channel_id=?"
            params.append(int(channel_id))
        query += " WHERE id=?"
        params.append(int(match_id))
        self.cur.execute(query, tuple(params))
        self.conn.commit()

    def add_sports_event(self, match_id: int, minute: int, event_type: str, team: str, text: str) -> int:
        self.cur.execute(
            """INSERT INTO sports_match_events(match_id, minute, event_type, team, text, created_at)
            VALUES(?, ?, ?, ?, ?, ?)""",
            (int(match_id), int(minute), event_type, team, text, int(time.time())),
        )
        self.conn.commit()
        return self.cur.lastrowid

    def get_sports_events(self, match_id: int, limit: int = 20) -> list[dict]:
        self.cur.execute(
            """SELECT id, match_id, minute, event_type, team, text, created_at
            FROM sports_match_events
            WHERE match_id=?
            ORDER BY minute ASC, id ASC LIMIT ?""",
            (int(match_id), int(limit)),
        )
        rows = self.cur.fetchall()
        return [
            {
                "id": r[0], "match_id": r[1], "minute": r[2], "event_type": r[3],
                "team": r[4], "text": r[5], "created_at": r[6],
            }
            for r in rows
        ]

    def place_sports_bet(
        self,
        match_id: int,
        user_id: int,
        outcome: str,
        amount: int,
        base_odds: float = 1.0,
        market: str = "1X2",
    ) -> int:
        amount = int(amount)
        if amount <= 0:
            raise ValueError("Bet amount must be positive")
        with self.transaction():
            if user_id > 0:
                self._ensure_entry(user_id)
                bal = self._fetch_entry(user_id)[1]
                if bal < amount:
                    raise ValueError("Insufficient funds")
                self.add_money(user_id, -amount)
            self.cur.execute(
                """INSERT INTO sports_bet_tickets(match_id, user_id, market, outcome, amount, base_odds, status, created_at)
                VALUES(?, ?, ?, ?, ?, ?, 'pending', ?)""",
                (int(match_id), int(user_id), market, outcome, amount, float(base_odds), int(time.time())),
            )
            ticket_id = self.cur.lastrowid
            self.cur.execute(
                "INSERT INTO match_bets(match_id, user_id, outcome, amount) VALUES(?, ?, ?, ?)",
                (int(match_id), int(user_id), outcome, amount),
            )
        return ticket_id

    def get_sports_tickets_for_match(self, match_id: int) -> list[dict]:
        self.cur.execute(
            """SELECT id, match_id, user_id, market, outcome, amount, base_odds, status, payout, created_at, settled_at
            FROM sports_bet_tickets
            WHERE match_id=?""",
            (int(match_id),),
        )
        rows = self.cur.fetchall()
        return [
            {
                "id": r[0], "match_id": r[1], "user_id": r[2], "market": r[3],
                "outcome": r[4], "amount": r[5], "base_odds": r[6], "status": r[7],
                "payout": r[8], "created_at": r[9], "settled_at": r[10],
            }
            for r in rows
        ]

    def get_sports_pool(self, match_id: int) -> dict[str, int]:
        self.cur.execute(
            """SELECT outcome, COALESCE(SUM(amount), 0)
            FROM sports_bet_tickets
            WHERE match_id=? AND status NOT IN ('refunded', 'cashed_out')
            GROUP BY outcome""",
            (int(match_id),),
        )
        return {row[0]: int(row[1]) for row in self.cur.fetchall()}

    def get_user_sports_tickets(self, user_id: int, limit: int = 10, offset: int = 0) -> list[dict]:
        self.cur.execute(
            """SELECT t.id, t.match_id, t.user_id, t.market, t.outcome, t.amount, t.base_odds,
                      t.status, t.payout, t.created_at, t.settled_at,
                      m.t1, m.t2, m.score_t1, m.score_t2, m.status, m.result
            FROM sports_bet_tickets t
            LEFT JOIN sports_matches m ON t.match_id = m.id
            WHERE t.user_id=?
            ORDER BY t.id DESC LIMIT ? OFFSET ?""",
            (int(user_id), int(limit), int(offset)),
        )
        rows = self.cur.fetchall()
        return [
            {
                "id": r[0], "match_id": r[1], "user_id": r[2], "market": r[3],
                "outcome": r[4], "amount": r[5], "base_odds": r[6], "status": r[7],
                "payout": r[8], "created_at": r[9], "settled_at": r[10],
                "t1": r[11], "t2": r[12], "score_t1": r[13], "score_t2": r[14],
                "match_status": r[15], "match_result": r[16],
            }
            for r in rows
        ]

    def get_sports_history(self, limit: int = 15) -> list[dict]:
        self.cur.execute(
            """SELECT m.id, m.season_id, m.t1, m.t2, m.score_t1, m.score_t2, m.result, m.kickoff, m.settled_at,
                      COALESCE(s.total_pool, 0), COALESCE(s.total_payout, 0), COALESCE(s.rake_amount, 0)
            FROM sports_matches m
            LEFT JOIN sports_settlements s ON m.id = s.match_id
            WHERE m.status='finished'
            ORDER BY m.settled_at DESC, m.id DESC LIMIT ?""",
            (int(limit),),
        )
        rows = self.cur.fetchall()
        return [
            {
                "id": r[0], "season_id": r[1], "t1": r[2], "t2": r[3],
                "score_t1": r[4], "score_t2": r[5], "result": r[6],
                "kickoff": r[7], "settled_at": r[8],
                "total_pool": r[9], "total_payout": r[10], "rake_amount": r[11],
            }
            for r in rows
        ]

    def get_sports_league_table(self, season_id: int = 1) -> list[dict]:
        self.cur.execute(
            """SELECT team_code, played, won, drawn, lost, gf, ga, points, form
            FROM sports_league_table
            WHERE season_id=?
            ORDER BY points DESC, (gf - ga) DESC, gf DESC, team_code ASC""",
            (int(season_id),),
        )
        rows = self.cur.fetchall()
        return [
            {
                "team_code": r[0], "played": r[1], "won": r[2], "drawn": r[3],
                "lost": r[4], "gf": r[5], "ga": r[6], "gd": r[5] - r[6],
                "points": r[7], "form": r[8] or "",
            }
            for r in rows
        ]

    def update_sports_league_match(self, season_id: int, t1: str, t2: str, s1: int, s2: int) -> None:
        for t_code in (t1, t2):
            self.cur.execute(
                "INSERT OR IGNORE INTO sports_league_table(season_id, team_code) VALUES(?, ?)",
                (int(season_id), t_code),
            )
        
        if s1 > s2:
            res1, res2 = "W", "L"
            pts1, pts2 = 3, 0
            w1, d1, l1 = 1, 0, 0
            w2, d2, l2 = 0, 0, 1
        elif s1 < s2:
            res1, res2 = "L", "W"
            pts1, pts2 = 0, 3
            w1, d1, l1 = 0, 0, 1
            w2, d2, l2 = 1, 0, 0
        else:
            res1, res2 = "D", "D"
            pts1, pts2 = 1, 1
            w1, d1, l1 = 0, 1, 0
            w2, d2, l2 = 0, 1, 0

        self.cur.execute(
            """UPDATE sports_league_table
            SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                gf = gf + ?, ga = ga + ?, points = points + ?,
                form = SUBSTR(? || form, 1, 5)
            WHERE season_id = ? AND team_code = ?""",
            (w1, d1, l1, int(s1), int(s2), pts1, res1, int(season_id), t1),
        )
        self.cur.execute(
            """UPDATE sports_league_table
            SET played = played + 1, won = won + ?, drawn = drawn + ?, lost = lost + ?,
                gf = gf + ?, ga = ga + ?, points = points + ?,
                form = SUBSTR(? || form, 1, 5)
            WHERE season_id = ? AND team_code = ?""",
            (w2, d2, l2, int(s2), int(s1), pts2, res2, int(season_id), t2),
        )

    def settle_sports_match(self, match_id: int, result: str, score_t1: int, score_t2: int) -> dict:
        from app.discord_bot.modules.sports_engine import calculate_hybrid_payout, evaluate_market_results

        with self.transaction():
            self.cur.execute("SELECT id, status FROM sports_matches WHERE id=?", (int(match_id),))
            m_row = self.cur.fetchone()
            if not m_row:
                raise ValueError(f"Match {match_id} not found")
            if m_row[1] == "finished":
                self.cur.execute(
                    "SELECT total_pool, rake_amount, rounding_to_jackpot, total_payout, house_contribution, result FROM sports_settlements WHERE match_id=?",
                    (int(match_id),),
                )
                s_row = self.cur.fetchone()
                return {
                    "already_settled": True,
                    "match_id": match_id,
                    "result": s_row[5] if s_row else result,
                    "total_pool": s_row[0] if s_row else 0,
                    "total_payout": s_row[3] if s_row else 0,
                    "payouts": {},
                }

            tickets = self.get_sports_tickets_for_match(match_id)
            # Filter out cashed out and refunded tickets
            active_tickets = [t for t in tickets if t["status"] == "pending"]
            now = int(time.time())

            market_results = evaluate_market_results(score_t1, score_t2)
            result_1x2 = market_results.get("1X2", result)

            markets = set(t.get("market", "1X2") for t in active_tickets)
            if not markets:
                markets = {"1X2"}

            combined_user_payouts: dict[int, int] = {}
            total_match_pool = 0
            total_match_payout = 0
            total_rake_amount = 0
            total_rounding_to_jackpot = 0
            total_house_contribution = 0

            for m_key in markets:
                m_tickets = [t for t in active_tickets if t.get("market", "1X2") == m_key]
                win_outcome = market_results.get(m_key, result_1x2)

                m_pool: dict[str, int] = {}
                for t in m_tickets:
                    m_pool[t["outcome"]] = m_pool.get(t["outcome"], 0) + t["amount"]

                m_total_pool = sum(m_pool.values())
                total_match_pool += m_total_pool

                user_payouts, total_payout, rake_amount, rounding_to_jackpot, house_contribution = calculate_hybrid_payout(
                    m_pool, win_outcome, m_tickets
                )

                total_match_payout += total_payout
                total_rake_amount += rake_amount
                total_rounding_to_jackpot += rounding_to_jackpot
                total_house_contribution += house_contribution

                # Mark tickets for this market
                for ticket in m_tickets:
                    tid = ticket["id"]
                    uid = ticket["user_id"]
                    if ticket["outcome"] == win_outcome:
                        payout_amt = int(user_payouts.get(uid, 0) * (ticket["amount"] / max(1, m_pool.get(win_outcome, 1))))
                        payout_amt = max(int(ticket["amount"] * 1.05), payout_amt)
                        self.cur.execute(
                            "UPDATE sports_bet_tickets SET status='won', payout=?, settled_at=? WHERE id=?",
                            (payout_amt, now, tid),
                        )
                    else:
                        self.cur.execute(
                            "UPDATE sports_bet_tickets SET status='lost', payout=0, settled_at=? WHERE id=?",
                            (now, tid),
                        )

                for uid, amt in user_payouts.items():
                    combined_user_payouts[uid] = combined_user_payouts.get(uid, 0) + amt

            # Credit winnings directly to players (AI winners deposit into jackpot pool instead of wallet)
            ai_winnings_to_jackpot = 0
            for uid, net_win in combined_user_payouts.items():
                if net_win > 0:
                    if uid > 0:
                        self.add_money(uid, net_win)
                        self.bump_quest(uid, "casino_win")
                    else:
                        ai_winnings_to_jackpot += net_win

            # Update jackpot pool
            jackpot_addition = total_rake_amount + total_rounding_to_jackpot + ai_winnings_to_jackpot
            if jackpot_addition > 0:
                cur_jp = int(self.get_setting("jackpot_pool", "0"))
                self.set_setting("jackpot_pool", str(cur_jp + jackpot_addition))

            # Mark match finished
            self.cur.execute(
                """UPDATE sports_matches
                SET status='finished', score_t1=?, score_t2=?, result=?, minute=90, settled_at=?
                WHERE id=?""",
                (int(score_t1), int(score_t2), result_1x2, now, int(match_id)),
            )

            # Record settlement
            self.cur.execute(
                """INSERT OR REPLACE INTO sports_settlements(
                    match_id, total_pool, rake_amount, rounding_to_jackpot, total_payout, house_contribution, result, settled_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)""",
                (int(match_id), total_match_pool, total_rake_amount, total_rounding_to_jackpot, total_match_payout, total_house_contribution, result_1x2, now),
            )

            # Update Standings
            self.cur.execute("SELECT t1, t2, season_id FROM sports_matches WHERE id=?", (int(match_id),))
            t_info = self.cur.fetchone()
            if t_info:
                self.update_sports_league_match(t_info[2], t_info[0], t_info[1], score_t1, score_t2)

            self.cur.execute("DELETE FROM match_bets WHERE match_id=?", (int(match_id),))

        return {
            "already_settled": False,
            "match_id": match_id,
            "result": result_1x2,
            "score_t1": score_t1,
            "score_t2": score_t2,
            "total_pool": total_match_pool,
            "total_payout": total_match_payout,
            "rake_amount": total_rake_amount,
            "rounding_to_jackpot": total_rounding_to_jackpot,
            "house_contribution": total_house_contribution,
            "payouts": combined_user_payouts,
        }

    def cashout_sports_ticket(self, ticket_id: int, user_id: int, cashout_amount: int) -> dict:
        """Processes an early cash-out for a pending bet ticket before minute 80."""
        with self.transaction():
            self.cur.execute(
                """SELECT t.id, t.match_id, t.user_id, t.amount, t.status, m.status, m.minute
                FROM sports_bet_tickets t
                LEFT JOIN sports_matches m ON t.match_id = m.id
                WHERE t.id=? AND t.user_id=?""",
                (int(ticket_id), int(user_id)),
            )
            row = self.cur.fetchone()
            if not row:
                return {"success": False, "error": "Vé cược không tồn tại hoặc không thuộc về bạn."}
            if row[4] != "pending":
                return {"success": False, "error": f"Vé này đã ở trạng thái {row[4]}, không thể xả kèo."}
            if row[5] != "live" or row[6] >= 80:
                return {"success": False, "error": "Tính năng xả kèo chỉ mở khi trận đấu đang live và trước phút 80'."}

            now = int(time.time())
            cashout_amount = max(1000, int(cashout_amount))
            self.add_money(user_id, cashout_amount)
            self.cur.execute(
                "UPDATE sports_bet_tickets SET status='cashed_out', payout=?, settled_at=? WHERE id=?",
                (cashout_amount, now, int(ticket_id)),
            )

        return {
            "success": True,
            "ticket_id": ticket_id,
            "cashout_amount": cashout_amount,
        }

    def get_top_tipsters(self, limit: int = 10) -> list[dict]:
        self.cur.execute(
            """SELECT user_id,
                      COUNT(*) as total_bets,
                      SUM(CASE WHEN status='won' THEN 1 ELSE 0 END) as won_bets,
                      SUM(CASE WHEN status='won' THEN payout - amount ELSE -amount END) as net_profit,
                      SUM(amount) as total_staked
            FROM sports_bet_tickets
            WHERE user_id > 0 AND status IN ('won', 'lost')
            GROUP BY user_id
            HAVING total_bets >= 1
            ORDER BY net_profit DESC, won_bets DESC LIMIT ?""",
            (int(limit),),
        )
        rows = self.cur.fetchall()
        return [
            {
                "user_id": r[0],
                "total_bets": r[1],
                "won_bets": r[2],
                "win_rate": round((r[2] / max(1, r[1])) * 100, 1),
                "net_profit": r[3],
                "total_staked": r[4],
            }
            for r in rows
        ]

    def refund_sports_match(self, match_id: int, reason: str = "") -> dict:
        with self.transaction():
            tickets = self.get_sports_tickets_for_match(match_id)
            refunded_count = 0
            refunded_total = 0
            now = int(time.time())
            for t in tickets:
                if t["status"] == "pending":
                    if t["user_id"] > 0:
                        self.add_money(t["user_id"], t["amount"])
                    self.cur.execute(
                        "UPDATE sports_bet_tickets SET status='refunded', payout=?, settled_at=? WHERE id=?",
                        (t["amount"], now, t["id"]),
                    )
                    refunded_count += 1
                    refunded_total += t["amount"]

            self.cur.execute(
                "UPDATE sports_matches SET status='cancelled', settled_at=? WHERE id=?",
                (now, int(match_id)),
            )
            self.cur.execute("DELETE FROM match_bets WHERE match_id=?", (int(match_id),))

        return {
            "match_id": match_id,
            "refunded_count": refunded_count,
            "refunded_total": refunded_total,
            "reason": reason,
        }

    def get_sports_stats_dashboard(self) -> dict:
        self.cur.execute("SELECT COUNT(*), COALESCE(SUM(total_pool), 0), COALESCE(SUM(total_payout), 0), COALESCE(SUM(rake_amount), 0) FROM sports_settlements")
        s_row = self.cur.fetchone()
        self.cur.execute("SELECT COUNT(*) FROM sports_matches WHERE status='upcoming'")
        upcoming_count = self.cur.fetchone()[0]
        self.cur.execute("SELECT COUNT(*) FROM sports_matches WHERE status='live'")
        live_count = self.cur.fetchone()[0]
        self.cur.execute("SELECT COUNT(*), COALESCE(SUM(amount), 0) FROM sports_bet_tickets WHERE status='pending'")
        t_row = self.cur.fetchone()
        return {
            "settled_matches": s_row[0] or 0,
            "total_volume": s_row[1] or 0,
            "total_payout": s_row[2] or 0,
            "total_rake_to_jackpot": s_row[3] or 0,
            "upcoming_matches": upcoming_count or 0,
            "live_matches": live_count or 0,
            "pending_tickets": t_row[0] or 0,
            "pending_tickets_volume": t_row[1] or 0,
        }

    # --- Legacy Match Bet Compatibility ---
    def add_match_bet(self, match_id: int, user_id: int, outcome: str, amount: int) -> int:
        return self.place_sports_bet(match_id, user_id, outcome, amount)

    def get_match_bets(self, match_id: int) -> list:
        tickets = self.get_sports_tickets_for_match(match_id)
        return [(t["id"], t["user_id"], t["outcome"], t["amount"]) for t in tickets]

    def get_match_pool(self, match_id: int) -> dict[str, int]:
        return self.get_sports_pool(match_id)

    def clear_match_bets(self, match_id: int) -> None:
        self.cur.execute("DELETE FROM sports_bet_tickets WHERE match_id=?", (int(match_id),))
        self.cur.execute("DELETE FROM match_bets WHERE match_id=?", (int(match_id),))
        self.conn.commit()

    # --- WORK XP ---
    def get_work_xp(self, user_id: int) -> int:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT work_xp FROM user_simulator_stats WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row[0] if row and row[0] else 0

    def set_work_xp(self, user_id: int, xp: int) -> None:
        self._ensure_entry(user_id)
        self.cur.execute(
            "INSERT OR IGNORE INTO user_simulator_stats(user_id, work_xp) VALUES(?, ?)",
            (user_id, int(xp)),
        )
        self.cur.execute("UPDATE user_simulator_stats SET work_xp=? WHERE user_id=?", (int(xp), user_id))
        self.conn.commit()

    # --- MEMBER CHAT LEVELS & GIVE DAILY LIMITS ---
    def get_member_level(self, user_id: int) -> tuple[int, int, float]:
        """Returns (level, xp, last_chat_xp); users never seen chat as (0, 0, 0.0)."""
        self.cur.execute(
            "SELECT level, xp, last_chat_xp FROM member_levels WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if not row:
            return (0, 0, 0.0)
        return (int(row[0]), int(row[1]), float(row[2]))

    def set_member_level(self, user_id: int, level: int, xp: int, last_chat_xp: float) -> None:
        self.cur.execute(
            """INSERT INTO member_levels(user_id, level, xp, last_chat_xp)
            VALUES(?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                level=excluded.level, xp=excluded.xp, last_chat_xp=excluded.last_chat_xp""",
            (user_id, int(level), int(xp), float(last_chat_xp)),
        )
        self.conn.commit()

    def get_give_daily(self, user_id: int, day: str) -> tuple[int, int, int, int]:
        """Returns (sent_money, received_money, sent_gold, received_gold) for the day key."""
        self.cur.execute(
            "SELECT sent_money, received_money, sent_gold, received_gold "
            "FROM give_daily WHERE user_id=? AND day=?",
            (user_id, day),
        )
        row = self.cur.fetchone()
        if not row:
            return (0, 0, 0, 0)
        return (int(row[0]), int(row[1]), int(row[2]), int(row[3]))

    def add_give_daily(
        self,
        user_id: int,
        day: str,
        sent_money: int = 0,
        received_money: int = 0,
        sent_gold: int = 0,
        received_gold: int = 0,
    ) -> None:
        self.cur.execute(
            """INSERT INTO give_daily(user_id, day, sent_money, received_money, sent_gold, received_gold)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, day) DO UPDATE SET
                sent_money = sent_money + excluded.sent_money,
                received_money = received_money + excluded.received_money,
                sent_gold = sent_gold + excluded.sent_gold,
                received_gold = received_gold + excluded.received_gold""",
            (user_id, day, int(sent_money), int(received_money), int(sent_gold), int(received_gold)),
        )
        self.conn.commit()

    # --- DAILY QUESTS ---
    def get_daily_quests(self, user_id: int) -> list[dict]:
        """Returns today's 3 quests, rolling new ones on a new day (UTC+7)."""
        import datetime
        today = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
        self.cur.execute("SELECT quest_date, quests_json FROM user_daily_quests WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        if row and row[0] == today:
            return json.loads(row[1])

        quests = random.sample(DAILY_QUEST_POOL, 3)
        quests = [dict(q, progress=0, claimed=False) for q in quests]
        self.cur.execute(
            "INSERT OR REPLACE INTO user_daily_quests(user_id, quest_date, quests_json) VALUES(?, ?, ?)",
            (user_id, today, json.dumps(quests, ensure_ascii=False)),
        )
        self.conn.commit()
        return quests

    def bump_quest(self, user_id: int, event: str, amount: int = 1) -> None:
        """Increments progress of today's unclaimed quests matching event."""
        import datetime
        today = (datetime.datetime.utcnow() + datetime.timedelta(hours=7)).strftime("%Y-%m-%d")
        self.cur.execute("SELECT quest_date, quests_json FROM user_daily_quests WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        if not row or row[0] != today:
            return
        quests = json.loads(row[1])
        changed = False
        for q in quests:
            if q.get("event") == event and not q["claimed"] and q["progress"] < q["target"]:
                q["progress"] = min(q["target"], q["progress"] + amount)
                changed = True
        if changed:
            self.cur.execute(
                "UPDATE user_daily_quests SET quests_json=? WHERE user_id=?",
                (json.dumps(quests, ensure_ascii=False), user_id),
            )
            self.conn.commit()

    def claim_daily_quest(self, user_id: int, index: int) -> dict | None:
        """Claims quest at index (0-2) if complete. Returns the quest or None."""
        quests = self.get_daily_quests(user_id)
        if index < 0 or index >= len(quests):
            return None
        q = quests[index]
        if q["claimed"] or q["progress"] < q["target"]:
            return None
        q["claimed"] = True
        self.cur.execute("UPDATE user_daily_quests SET quests_json=? WHERE user_id=?",
                         (json.dumps(quests, ensure_ascii=False), user_id))
        self.conn.commit()
        self.add_money(user_id, q["reward_money"])
        if q.get("reward_gold"):
            self.add_credits(user_id, q["reward_gold"])
        return q

    def add_credits(self, user_id: int, credits_to_add: int) -> Entry:
        self._ensure_entry(user_id)
        self._record_gold_flow(int(credits_to_add))
        self.cur.execute(
            "UPDATE economy SET credits=MAX(0, credits + ?) WHERE user_id=?",
            (int(credits_to_add), user_id),
        )
        self.conn.commit()
        return self._fetch_entry(user_id)

    def random_entry(self) -> Entry:
        self.cur.execute("SELECT * FROM economy")
        entries = self.cur.fetchall()
        if not entries:
            raise RuntimeError("economy has no entries")
        return random.choice(entries)

    def top_entries(self, n: int = 0) -> List[Entry]:
        self.cur.execute("SELECT * FROM economy ORDER BY money DESC")
        return (self.cur.fetchmany(n) if n else self.cur.fetchall())

    def get_gold_price(self) -> int:
        self.cur.execute("SELECT value FROM system_settings WHERE key='gold_price'")
        row = self.cur.fetchone()
        return int(row[0]) if row else 10_000_000

    def get_prev_gold_price(self) -> int:
        self.cur.execute("SELECT value FROM system_settings WHERE key='gold_price_prev'")
        row = self.cur.fetchone()
        return int(row[0]) if row else 10_000_000

    def set_gold_prices(self, current_price: int, prev_price: int) -> None:
        self.cur.execute(
            "INSERT OR REPLACE INTO system_settings(key, value) VALUES('gold_price', ?)",
            (str(current_price),),
        )
        self.cur.execute(
            "INSERT OR REPLACE INTO system_settings(key, value) VALUES('gold_price_prev', ?)",
            (str(prev_price),),
        )
        self.conn.commit()

    def get_businesses(self, user_id: int) -> list[tuple[str, int]]:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT biz_id, level FROM user_businesses WHERE user_id=?", (user_id,))
        return self.cur.fetchall()

    def set_business_level(self, user_id: int, biz_id: str, level: int) -> None:
        self._ensure_entry(user_id)
        self.cur.execute(
            "INSERT OR REPLACE INTO user_businesses(user_id, biz_id, level) VALUES(?, ?, ?)",
            (user_id, biz_id, level),
        )
        self.conn.commit()

    def add_user_topup(self, user_id: int, amount_vnd: int, gold_gained: int) -> int:
        """Adds topup amount in VND and Gold to user_topups table. Returns new total VND."""
        self._ensure_entry(user_id)
        now = int(time.time())
        self.cur.execute(
            """INSERT INTO user_topups(user_id, total_vnd, total_gold, updated_at)
               VALUES(?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
               total_vnd = total_vnd + EXCLUDED.total_vnd,
               total_gold = total_gold + EXCLUDED.total_gold,
               updated_at = EXCLUDED.updated_at""",
            (user_id, amount_vnd, gold_gained, now),
        )
        self.conn.commit()
        self.cur.execute("SELECT total_vnd FROM user_topups WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row[0] if row else amount_vnd

    def get_user_topup(self, user_id: int) -> tuple[int, int]:
        """Returns (total_vnd, total_gold) for user."""
        self.cur.execute("SELECT total_vnd, total_gold FROM user_topups WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return (row[0], row[1]) if row else (0, 0)

    def get_topup_leaderboard(self, limit: int = 10) -> list[tuple[int, int, int]]:
        """Returns list of (user_id, total_vnd, total_gold) ordered by total_vnd DESC."""
        self.cur.execute(
            "SELECT user_id, total_vnd, total_gold FROM user_topups ORDER BY total_vnd DESC LIMIT ?",
            (limit,),
        )
        return self.cur.fetchall()

    def remove_user_topup(self, user_id: int) -> bool:
        """Removes user entry from user_topups table. Returns True if a row was deleted."""
        self.cur.execute("DELETE FROM user_topups WHERE user_id=?", (user_id,))
        self.conn.commit()
        return self.cur.rowcount > 0


    def get_inventory(self, user_id: int) -> list[tuple[str, int]]:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT item_id, quantity FROM user_inventory WHERE user_id=?", (user_id,))
        return self.cur.fetchall()

    def add_inventory_item(self, user_id: int, item_id: str, amount: int) -> int:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT quantity FROM user_inventory WHERE user_id=? AND item_id=?",
            (user_id, item_id),
        )
        row = self.cur.fetchone()
        current_qty = row[0] if row else 0
        new_qty = max(0, current_qty + amount)
        self.cur.execute(
            "INSERT OR REPLACE INTO user_inventory(user_id, item_id, quantity) VALUES(?, ?, ?)",
            (user_id, item_id, new_qty),
        )
        self.conn.commit()
        return new_qty

    def get_equipped_banner(self, user_id: int) -> str | None:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT equipped_banner FROM economy WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row[0] if row else None

    def set_equipped_banner(self, user_id: int, banner_id: str | None) -> None:
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET equipped_banner=? WHERE user_id=?",
            (banner_id, user_id),
        )
        self.conn.commit()

    def get_showcase_treasure(self, user_id: int) -> str | None:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT showcase_treasure FROM economy WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row[0] if row else None

    def set_showcase_treasure(self, user_id: int, treasure_id: str | None) -> None:
        self._ensure_entry(user_id)
        self.cur.execute(
            "UPDATE economy SET showcase_treasure=? WHERE user_id=?",
            (treasure_id, user_id),
        )
        self.conn.commit()

    def get_simulator_stats(self, user_id: int) -> tuple[int, int, int, float, int]:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT last_collect, last_mine, last_rob, fractional_gold, last_work FROM user_simulator_stats WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO user_simulator_stats(user_id, last_collect, last_mine, last_rob, fractional_gold, last_work) VALUES(?, 0, 0, 0, 0.0, 0)",
                (user_id,),
            )
            self.conn.commit()
            return (0, 0, 0, 0.0, 0)
        return row

    def set_simulator_stats(
        self,
        user_id: int,
        last_collect: int | None = None,
        last_mine: int | None = None,
        last_rob: int | None = None,
        fractional_gold: float | None = None,
        last_work: int | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        # ensure row exists
        self.get_simulator_stats(user_id)
        
        updates = []
        params = []
        if last_collect is not None:
            updates.append("last_collect=?")
            params.append(last_collect)
        if last_mine is not None:
            updates.append("last_mine=?")
            params.append(last_mine)
        if last_rob is not None:
            updates.append("last_rob=?")
            params.append(last_rob)
        if fractional_gold is not None:
            updates.append("fractional_gold=?")
            params.append(fractional_gold)
        if last_work is not None:
            updates.append("last_work=?")
            params.append(last_work)
        
        if updates:
            params.append(user_id)
            query = f"UPDATE user_simulator_stats SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_portfolio(self, user_id: int) -> list[tuple[str, float]]:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT symbol, shares FROM user_portfolio WHERE user_id=?", (user_id,))
        return self.cur.fetchall()

    def set_portfolio_shares(self, user_id: int, symbol: str, shares: float) -> None:
        self._ensure_entry(user_id)
        if shares <= 0:
            self.cur.execute("DELETE FROM user_portfolio WHERE user_id=? AND symbol=?", (user_id, symbol.upper()))
        else:
            # ON CONFLICT giữ nguyên avg_cost (chỉ INSERT OR REPLACE mới reset nó)
            self.cur.execute(
                """INSERT INTO user_portfolio(user_id, symbol, shares, avg_cost) VALUES(?, ?, ?, 0)
                   ON CONFLICT(user_id, symbol) DO UPDATE SET shares=excluded.shares""",
                (user_id, symbol.upper(), float(shares)),
            )
        self.conn.commit()

    def apply_stock_buy(self, user_id: int, symbol: str, shares: float, price: float) -> float:
        """Cộng cổ phiếu mua vào portfolio và cập nhật giá vốn bình quân gia quyền.

        Trả về giá vốn trung bình mới. Giá vốn chỉ có ý nghĩa khi shares > 0.
        """
        self._ensure_entry(user_id)
        symbol = symbol.upper()
        self.cur.execute(
            "SELECT shares, avg_cost FROM user_portfolio WHERE user_id=? AND symbol=?",
            (user_id, symbol),
        )
        row = self.cur.fetchone()
        old_shares = float(row[0]) if row and row[0] > 0 else 0.0
        old_avg = float(row[1]) if row else 0.0
        total_shares = old_shares + float(shares)
        new_avg = ((old_shares * old_avg) + (float(shares) * float(price))) / total_shares if total_shares else 0.0
        self.cur.execute(
            """INSERT INTO user_portfolio(user_id, symbol, shares, avg_cost) VALUES(?, ?, ?, ?)
               ON CONFLICT(user_id, symbol) DO UPDATE SET shares=excluded.shares, avg_cost=excluded.avg_cost""",
            (user_id, symbol, total_shares, new_avg),
        )
        self.conn.commit()
        return new_avg

    def get_portfolio_with_cost(self, user_id: int) -> list[tuple[str, float, float]]:
        """(symbol, shares, avg_cost) cho các mã đang nắm giữ thực tế (shares > 0)."""
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT symbol, shares, avg_cost FROM user_portfolio WHERE user_id=? AND shares > 0",
            (user_id,),
        )
        return self.cur.fetchall()

    def get_stock_holders(self, symbol: str) -> list[tuple[int, float]]:
        self.cur.execute("SELECT user_id, shares FROM user_portfolio WHERE symbol=? AND shares > 0.0", (symbol.upper(),))
        return self.cur.fetchall()


    def get_stock_prices(self) -> list[tuple[str, int, int, float]]:
        self.cur.execute("SELECT symbol, price, prev_price, change_percent FROM stock_prices")
        return self.cur.fetchall()

    def get_portfolio_value(self, user_id: int) -> int:
        """Current market value of the user's whole stock portfolio."""
        self.cur.execute(
            """SELECT COALESCE(SUM(p.shares * s.price), 0)
               FROM user_portfolio p
               LEFT JOIN stock_prices s ON s.symbol = p.symbol
               WHERE p.user_id = ?""",
            (user_id,),
        )
        row = self.cur.fetchone()
        return int(row[0]) if row else 0

    def get_economy_totals(self) -> dict:
        """Server-wide money stats for the admin overview."""
        self.cur.execute("SELECT COALESCE(SUM(money), 0), COUNT(*) FROM economy")
        total_money, user_count = self.cur.fetchone()
        self.cur.execute("SELECT user_id, money FROM economy ORDER BY money DESC LIMIT 10")
        top = [(r[0], r[1]) for r in self.cur.fetchall()]
        return {
            "total_money": int(total_money),
            "user_count": int(user_count),
            "top": top,
            "jackpot_pool": self.get_jackpot_pool(),
            "gold_mined_week": int(self.get_setting("gold_mined_week", "0")),
            "gold_spent_week": int(self.get_setting("gold_spent_week", "0")),
            "gold_price": self.get_gold_price(),
        }

    def get_rich_rank(self, user_id: int) -> int:
        """1-based rank of the user by wallet money (-1 if unranked)."""
        money = self.get_entry(user_id)[1]
        self.cur.execute("SELECT COUNT(*) + 1 FROM economy WHERE money > ?", (money,))
        return int(self.cur.fetchone()[0])

    def adjust_stock_price(self, symbol: str, pct: float) -> int | None:
        """Applies a lasting market-impact nudge from player trades (clamped ±10%)."""
        self.cur.execute("SELECT price, prev_price FROM stock_prices WHERE symbol=?", (symbol,))
        row = self.cur.fetchone()
        if not row:
            return None
        price, prev_price = row
        clamped = max(-0.10, min(0.10, pct))
        new_price = max(1, int(price * (1 + clamped)))
        change = ((new_price - prev_price) / prev_price * 100) if prev_price else 0.0
        self.update_stock_price(symbol, new_price, prev_price, change)
        return new_price

    def update_stock_price(self, symbol: str, price: int, prev_price: int, change_percent: float) -> None:
        self.cur.execute(
            "INSERT OR REPLACE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES(?, ?, ?, ?)",
            (symbol, price, prev_price, change_percent),
        )
        # Also record price history
        import time
        self.cur.execute(
            "INSERT INTO stock_price_history(symbol, price, timestamp) VALUES(?, ?, ?)",
            (symbol, price, int(time.time())),
        )
        # Keep only the last 30 entries per symbol to limit database size
        self.cur.execute(
            """DELETE FROM stock_price_history WHERE symbol = ? AND id NOT IN (
                SELECT id FROM stock_price_history WHERE symbol = ? ORDER BY id DESC LIMIT 30
            )""",
            (symbol, symbol)
        )
        self.conn.commit()

    def get_stock_price_history(self, symbol: str, limit: int = 10) -> list[tuple[int, int]]:
        self.cur.execute(
            "SELECT price, timestamp FROM stock_price_history WHERE symbol = ? ORDER BY id DESC LIMIT ?",
            (symbol, limit),
        )
        rows = self.cur.fetchall()
        return [(row[0], row[1]) for row in reversed(rows)]

    # --- GARAGE SYSTEMS ---
    def add_user_car(self, user_id: int, model: str, rarity: str, serial: int, edition: str, collection: str) -> int:
        self.cur.execute(
            """INSERT INTO user_cars(user_id, model, rarity, serial, edition, collection, is_favorite)
               VALUES(?, ?, ?, ?, ?, ?, 0)""",
            (user_id, model, rarity, serial, edition, collection)
        )
        self.conn.commit()
        return self.cur.lastrowid

    def get_user_cars(self, user_id: int) -> list:
        self.cur.execute("SELECT * FROM user_cars WHERE user_id=?", (user_id,))
        return self.cur.fetchall()

    def get_user_car(self, car_id: int) -> tuple | None:
        self.cur.execute("SELECT * FROM user_cars WHERE id=?", (car_id,))
        return self.cur.fetchone()

    def delete_user_car(self, car_id: int) -> None:
        self.cur.execute("DELETE FROM user_cars WHERE id=?", (car_id,))
        self.conn.commit()

    def transfer_user_car(self, car_id: int, new_owner_id: int) -> None:
        self.cur.execute("UPDATE user_cars SET user_id=?, is_favorite=0 WHERE id=?", (new_owner_id, car_id))
        self.conn.commit()

    def set_favorite_car(self, user_id: int, car_id: int) -> None:
        self.cur.execute("UPDATE user_cars SET is_favorite=0 WHERE user_id=?", (user_id,))
        self.cur.execute("UPDATE user_cars SET is_favorite=1 WHERE user_id=? AND id=?", (user_id, car_id))
        self.conn.commit()

    def get_favorite_car(self, user_id: int) -> tuple | None:
        self.cur.execute("SELECT * FROM user_cars WHERE user_id=? AND is_favorite=1", (user_id,))
        return self.cur.fetchone()

    def add_market_listing(self, car_id: int, seller_id: int, price: int) -> int:
        import time
        self.cur.execute(
            "INSERT INTO car_market(car_id, seller_id, price, created_at) VALUES(?, ?, ?, ?)",
            (car_id, seller_id, price, int(time.time()))
        )
        self.conn.commit()
        return self.cur.lastrowid

    def get_market_listings(self) -> list:
        self.cur.execute("SELECT * FROM car_market ORDER BY created_at DESC")
        return self.cur.fetchall()

    def get_market_listing(self, listing_id: int) -> tuple | None:
        self.cur.execute("SELECT * FROM car_market WHERE id=?", (listing_id,))
        return self.cur.fetchone()

    def get_market_listing_by_car(self, car_id: int) -> tuple | None:
        self.cur.execute("SELECT * FROM car_market WHERE car_id=?", (car_id,))
        return self.cur.fetchone()

    def delete_market_listing(self, listing_id: int) -> None:
        self.cur.execute("DELETE FROM car_market WHERE id=?", (listing_id,))
        self.conn.commit()

    def get_roulette(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT plays, wins, losses, profit, streak, max_streak, chips, number_stats, achievements FROM user_roulette WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO user_roulette(user_id, plays, wins, losses, profit, streak, max_streak, chips, number_stats, achievements) VALUES(?, 0, 0, 0, 0, 0, 0, 0, '{}', '[]')",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
                "chips": 0,
                "number_stats": {},
                "achievements": [],
            }
        
        import json
        try:
            num_stats = json.loads(row[7])
        except Exception:
            num_stats = {}
            
        try:
            achievements = json.loads(row[8])
        except Exception:
            achievements = []
            
        return {
            "user_id": user_id,
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "profit": row[3],
            "streak": row[4],
            "max_streak": row[5],
            "chips": row[6],
            "number_stats": num_stats,
            "achievements": achievements,
        }

    def update_roulette(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
        chips: int | None = None,
        number_stats: dict | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_roulette(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
        if chips is not None:
            updates.append("chips = ?")
            params.append(chips)
            
        import json
        if number_stats is not None:
            updates.append("number_stats = ?")
            params.append(json.dumps(number_stats))
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "Roulette", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_roulette SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_coinflip(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT plays, wins, losses, profit, streak, max_streak, max_win_amount, achievements FROM user_coinflip WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO user_coinflip(user_id, plays, wins, losses, profit, streak, max_streak, max_win_amount, achievements) VALUES(?, 0, 0, 0, 0, 0, 0, 0, '[]')",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
                "max_win_amount": 0,
                "achievements": [],
            }
        
        import json
        try:
            achievements = json.loads(row[7])
        except Exception:
            achievements = []
            
        return {
            "user_id": user_id,
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "profit": row[3],
            "streak": row[4],
            "max_streak": row[5],
            "max_win_amount": row[6],
            "achievements": achievements,
        }

    def update_coinflip(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
        max_win_amount: int | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_coinflip(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
        if max_win_amount is not None:
            updates.append("max_win_amount = ?")
            params.append(max_win_amount)
            
        import json
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "Coinflip", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_coinflip SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_bkb_stats(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT plays, wins, losses, draws, profit, streak, max_streak FROM user_bkb WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO user_bkb(user_id, plays, wins, losses, draws, profit, streak, max_streak) VALUES(?, 0, 0, 0, 0, 0, 0, 0)",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "draws": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
            }
        return {
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "draws": row[3],
            "profit": row[4],
            "streak": row[5],
            "max_streak": row[6],
        }

    def update_bkb_stats(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        draws: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_bkb_stats(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if draws != 0:
            updates.append("draws = draws + ?")
            params.append(draws)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_bkb SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_bkb_h2h(self, p1: int, p2: int) -> dict:
        player_one, player_two = min(p1, p2), max(p1, p2)
        self.cur.execute(
            "SELECT player_one_wins, player_two_wins, draws, profit_transfer FROM bkb_h2h WHERE player_one=? AND player_two=?",
            (player_one, player_two),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO bkb_h2h(player_one, player_two, player_one_wins, player_two_wins, draws, profit_transfer) VALUES(?, ?, 0, 0, 0, 0)",
                (player_one, player_two),
            )
            self.conn.commit()
            return {
                "player_one_wins": 0,
                "player_two_wins": 0,
                "draws": 0,
                "profit_transfer": 0,
            }
        return {
            "player_one_wins": row[0],
            "player_two_wins": row[1],
            "draws": row[2],
            "profit_transfer": row[3],
        }

    def update_bkb_h2h(
        self,
        p1: int,
        p2: int,
        *,
        p1_win: bool = False,
        p2_win: bool = False,
        draw: bool = False,
        profit_delta: int = 0,
    ) -> None:
        player_one, player_two = min(p1, p2), max(p1, p2)
        self.get_bkb_h2h(player_one, player_two)
        
        updates = []
        params = []
        
        if p1_win:
            if p1 == player_one:
                updates.append("player_one_wins = player_one_wins + 1")
            else:
                updates.append("player_two_wins = player_two_wins + 1")
        elif p2_win:
            if p2 == player_one:
                updates.append("player_one_wins = player_one_wins + 1")
            else:
                updates.append("player_two_wins = player_two_wins + 1")
        elif draw:
            updates.append("draws = draws + 1")
            
        if profit_delta != 0:
            if p1 == player_one:
                updates.append("profit_transfer = profit_transfer + ?")
                params.append(profit_delta)
            else:
                updates.append("profit_transfer = profit_transfer - ?")
                params.append(profit_delta)
                
        if updates:
            params.append(player_one)
            params.append(player_two)
            query = f"UPDATE bkb_h2h SET {', '.join(updates)} WHERE player_one=? AND player_two=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_baito_stats(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            """SELECT plays, wins, profit, streak, max_streak, point_9_wins, batay_wins, bacao_wins, baat_wins, 
                      all_in_plays, blind_plays, blind_wins, max_blind_win_amount, achievements 
               FROM user_baito WHERE user_id=?""",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                """INSERT OR IGNORE INTO user_baito(user_id, plays, wins, profit, streak, max_streak, point_9_wins, 
                                                    batay_wins, bacao_wins, baat_wins, all_in_plays, blind_plays, 
                                                    blind_wins, max_blind_win_amount, achievements) 
                   VALUES(?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '[]')""",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
                "point_9_wins": 0,
                "batay_wins": 0,
                "bacao_wins": 0,
                "baat_wins": 0,
                "all_in_plays": 0,
                "blind_plays": 0,
                "blind_wins": 0,
                "max_blind_win_amount": 0,
                "achievements": [],
            }
        
        import json
        try:
            achievements = json.loads(row[13])
        except Exception:
            achievements = []
            
        return {
            "plays": row[0],
            "wins": row[1],
            "profit": row[2],
            "streak": row[3],
            "max_streak": row[4],
            "point_9_wins": row[5],
            "batay_wins": row[6],
            "bacao_wins": row[7],
            "baat_wins": row[8],
            "all_in_plays": row[9],
            "blind_plays": row[10],
            "blind_wins": row[11],
            "max_blind_win_amount": row[12],
            "achievements": achievements,
        }

    def update_baito_stats(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
        point_9_wins: int = 0,
        batay_wins: int = 0,
        bacao_wins: int = 0,
        baat_wins: int = 0,
        all_in_plays: int = 0,
        blind_plays: int = 0,
        blind_wins: int = 0,
        max_blind_win_amount: int | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_baito_stats(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
        if point_9_wins != 0:
            updates.append("point_9_wins = point_9_wins + ?")
            params.append(point_9_wins)
        if batay_wins != 0:
            updates.append("batay_wins = batay_wins + ?")
            params.append(batay_wins)
        if bacao_wins != 0:
            updates.append("bacao_wins = bacao_wins + ?")
            params.append(bacao_wins)
        if baat_wins != 0:
            updates.append("baat_wins = baat_wins + ?")
            params.append(baat_wins)
        if all_in_plays != 0:
            updates.append("all_in_plays = all_in_plays + ?")
            params.append(all_in_plays)
        if blind_plays != 0:
            updates.append("blind_plays = blind_plays + ?")
            params.append(blind_plays)
        if blind_wins != 0:
            updates.append("blind_wins = blind_wins + ?")
            params.append(blind_wins)
        if max_blind_win_amount is not None:
            updates.append("max_blind_win_amount = ?")
            params.append(max_blind_win_amount)
            
        import json
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "Baito", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_baito SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_pve_cooldown(self, user_id: int, stage_type: str) -> int:
        self.cur.execute(
            "SELECT last_fight FROM user_pve_cooldowns WHERE user_id=? AND stage_type=?",
            (user_id, stage_type),
        )
        row = self.cur.fetchone()
        return row[0] if row else 0

    def set_pve_cooldown(self, user_id: int, stage_type: str, timestamp: int) -> None:
        self.cur.execute(
            "INSERT OR REPLACE INTO user_pve_cooldowns(user_id, stage_type, last_fight) VALUES(?, ?, ?)",
            (user_id, stage_type, int(timestamp)),
        )
        self.conn.commit()

    def get_world_boss_stats(self, user_id: int) -> tuple[int, int, int]:
        self.cur.execute(
            "SELECT damage, fights_today, last_fight_time FROM user_world_boss_damage WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO user_world_boss_damage(user_id, damage, fights_today, last_fight_time) VALUES(?, 0, 0, 0)",
                (user_id,),
            )
            self.conn.commit()
            return (0, 0, 0)
        return row

    def update_world_boss_damage(self, user_id: int, damage_dealt: int, now_ts: int) -> None:
        stats = self.get_world_boss_stats(user_id)
        
        # check if it's a new day
        import time
        last_date = time.strftime('%Y-%m-%d', time.localtime(stats[2]))
        current_date = time.strftime('%Y-%m-%d', time.localtime(now_ts))
        
        if last_date != current_date:
            fights_today = 1
        else:
            fights_today = stats[1] + 1
            
        new_damage = stats[0] + damage_dealt
        self.cur.execute(
            "INSERT OR REPLACE INTO user_world_boss_damage(user_id, damage, fights_today, last_fight_time) VALUES(?, ?, ?, ?)",
            (user_id, new_damage, fights_today, int(now_ts)),
        )
        self.conn.commit()

    def get_all_world_boss_contributors(self) -> list[tuple[int, int]]:
        self.cur.execute("SELECT user_id, damage FROM user_world_boss_damage WHERE damage > 0 ORDER BY damage DESC")
        return self.cur.fetchall()

    def reset_world_boss_stats(self) -> None:
        self.cur.execute("DELETE FROM user_world_boss_damage")
        self.conn.commit()

    def is_banned(self, user_id: int) -> bool:
        self.cur.execute("SELECT 1 FROM banned_users WHERE user_id=?", (user_id,))
        return self.cur.fetchone() is not None

    def ban_user(self, user_id: int) -> None:
        import time
        self.cur.execute(
            "INSERT OR IGNORE INTO banned_users(user_id, banned_at) VALUES(?, ?)",
            (user_id, int(time.time())),
        )
        self.conn.commit()

    def unban_user(self, user_id: int) -> None:
        self.cur.execute("DELETE FROM banned_users WHERE user_id=?", (user_id,))
        self.conn.commit()

    def get_mines_stats(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT plays, wins, losses, profit, streak, max_streak, achievements FROM user_mines WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO user_mines(user_id, plays, wins, losses, profit, streak, max_streak, achievements) VALUES(?, 0, 0, 0, 0, 0, 0, '[]')",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
                "achievements": [],
            }
        
        import json
        try:
            achievements = json.loads(row[6])
        except Exception:
            achievements = []
            
        return {
            "user_id": user_id,
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "profit": row[3],
            "streak": row[4],
            "max_streak": row[5],
            "achievements": achievements,
        }

    def update_mines_stats(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_mines_stats(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
            
        import json
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "Mines", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_mines SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_plinko_stats(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            """SELECT plays, wins, losses, profit, jackpots, max_multiplier, streak, max_streak, achievements 
               FROM user_plinko WHERE user_id=?""",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                """INSERT OR IGNORE INTO user_plinko(user_id, plays, wins, losses, profit, jackpots, max_multiplier, streak, max_streak, achievements) 
                   VALUES(?, 0, 0, 0, 0, 0, 0.0, 0, 0, '[]')""",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "jackpots": 0,
                "max_multiplier": 0.0,
                "streak": 0,
                "max_streak": 0,
                "achievements": [],
            }
        
        import json
        try:
            achievements = json.loads(row[8])
        except Exception:
            achievements = []
            
        return {
            "user_id": user_id,
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "profit": row[3],
            "jackpots": row[4],
            "max_multiplier": row[5],
            "streak": row[6],
            "max_streak": row[7],
            "achievements": achievements,
        }

    def update_plinko_stats(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        profit: int = 0,
        jackpots: int = 0,
        max_multiplier: float | None = None,
        streak: int | None = None,
        max_streak: int | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_plinko_stats(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if jackpots != 0:
            updates.append("jackpots = jackpots + ?")
            params.append(jackpots)
        if max_multiplier is not None:
            updates.append("max_multiplier = ?")
            params.append(max_multiplier)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
            
        import json
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "Plinko", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_plinko SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_highlow_stats(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            """SELECT plays, wins, losses, profit, streak, max_streak, max_multiplier, achievements 
               FROM user_highlow WHERE user_id=?""",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                """INSERT OR IGNORE INTO user_highlow(user_id, plays, wins, losses, profit, streak, max_streak, max_multiplier, achievements) 
                   VALUES(?, 0, 0, 0, 0, 0, 0, 0.0, '[]')""",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
                "max_multiplier": 0.0,
                "achievements": [],
            }
        
        import json
        try:
            achievements = json.loads(row[7])
        except Exception:
            achievements = []
            
        return {
            "user_id": user_id,
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "profit": row[3],
            "streak": row[4],
            "max_streak": row[5],
            "max_multiplier": row[6],
            "achievements": achievements,
        }

    def update_highlow_stats(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
        max_multiplier: float | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_highlow_stats(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
        if max_multiplier is not None:
            updates.append("max_multiplier = ?")
            params.append(max_multiplier)
            
        import json
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "Highlow", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_highlow SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_tower_stats(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            """SELECT plays, wins, losses, profit, streak, max_streak, achievements 
               FROM user_tower WHERE user_id=?""",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                """INSERT OR IGNORE INTO user_tower(user_id, plays, wins, losses, profit, streak, max_streak, achievements) 
                   VALUES(?, 0, 0, 0, 0, 0, 0, '[]')""",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
                "achievements": [],
            }
        
        import json
        try:
            achievements = json.loads(row[6])
        except Exception:
            achievements = []
            
        return {
            "user_id": user_id,
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "profit": row[3],
            "streak": row[4],
            "max_streak": row[5],
            "achievements": achievements,
        }

    def update_tower_stats(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_tower_stats(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
            
        import json
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "Tower", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_tower SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_giaima_stats(self, user_id: int) -> dict:
        self._ensure_entry(user_id)
        self.cur.execute(
            """SELECT plays, wins, losses, profit, streak, max_streak, last_free_play, achievements 
               FROM user_giaima WHERE user_id=?""",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                """INSERT OR IGNORE INTO user_giaima(user_id, plays, wins, losses, profit, streak, max_streak, last_free_play, achievements) 
                   VALUES(?, 0, 0, 0, 0, 0, 0, 0, '[]')""",
                (user_id,),
            )
            self.conn.commit()
            return {
                "plays": 0,
                "wins": 0,
                "losses": 0,
                "profit": 0,
                "streak": 0,
                "max_streak": 0,
                "last_free_play": 0,
                "achievements": [],
            }
        
        import json
        try:
            achievements = json.loads(row[7])
        except Exception:
            achievements = []
            
        return {
            "user_id": user_id,
            "plays": row[0],
            "wins": row[1],
            "losses": row[2],
            "profit": row[3],
            "streak": row[4],
            "max_streak": row[5],
            "last_free_play": row[6],
            "achievements": achievements,
        }

    def update_giaima_stats(
        self,
        user_id: int,
        *,
        plays: int = 0,
        wins: int = 0,
        losses: int = 0,
        profit: int = 0,
        streak: int | None = None,
        max_streak: int | None = None,
        last_free_play: int | None = None,
        achievements: list | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_giaima_stats(user_id)
        
        updates = []
        params = []
        
        if plays != 0:
            updates.append("plays = plays + ?")
            params.append(plays)
        if wins != 0:
            updates.append("wins = wins + ?")
            params.append(wins)
        if losses != 0:
            updates.append("losses = losses + ?")
            params.append(losses)
        if profit != 0:
            updates.append("profit = profit + ?")
            params.append(profit)
        if streak is not None:
            updates.append("streak = ?")
            params.append(streak)
        if max_streak is not None:
            updates.append("max_streak = ?")
            params.append(max_streak)
        if last_free_play is not None:
            updates.append("last_free_play = ?")
            params.append(last_free_play)
            
        import json
        if achievements is not None:
            updates.append("achievements = ?")
            params.append(json.dumps(achievements))
            for ach in achievements:
                self.log_achievement_unlock(user_id, "GiaiMa", ach)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_giaima SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    # === Limit Orders ===
    def get_limit_orders(self, user_id: int) -> list[tuple[int, str, str, int, float, int]]:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT id, symbol, order_type, target_price, shares, created_at FROM limit_orders WHERE user_id=? ORDER BY id ASC",
            (user_id,),
        )
        return self.cur.fetchall()

    def add_limit_order(self, user_id: int, symbol: str, order_type: str, target_price: int, shares: float) -> int:
        self._ensure_entry(user_id)
        import time
        self.cur.execute(
            "INSERT INTO limit_orders(user_id, symbol, order_type, target_price, shares, created_at) VALUES(?, ?, ?, ?, ?, ?)",
            (user_id, symbol.upper(), order_type.upper(), target_price, shares, int(time.time())),
        )
        self.conn.commit()
        return self.cur.lastrowid

    def remove_limit_order(self, order_id: int) -> None:
        self.cur.execute("DELETE FROM limit_orders WHERE id=?", (order_id,))
        self.conn.commit()

    def get_limit_order(self, order_id: int) -> tuple[int, int, str, str, int, float, int] | None:
        self.cur.execute(
            "SELECT id, user_id, symbol, order_type, target_price, shares, created_at FROM limit_orders WHERE id=?",
            (order_id,),
        )
        return self.cur.fetchone()

    def get_all_active_limit_orders(self) -> list[tuple[int, int, str, str, int, float, int]]:
        self.cur.execute(
            "SELECT id, user_id, symbol, order_type, target_price, shares, created_at FROM limit_orders ORDER BY id ASC"
        )
        return self.cur.fetchall()

    # === Simulator Upgrades (Manager, Insurance, Bodyguard, Pickaxe) ===
    def get_upgrades(self, user_id: int) -> tuple[int, int, int, int]:
        self._ensure_entry(user_id)
        self.get_simulator_stats(user_id)
        self.cur.execute(
            "SELECT manager_expiry, insurance_expiry, bodyguard_expiry, pickaxe_level FROM user_simulator_stats WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            return (0, 0, 0, 0)
        return row

    def set_upgrades(
        self,
        user_id: int,
        manager_expiry: int | None = None,
        insurance_expiry: int | None = None,
        bodyguard_expiry: int | None = None,
        pickaxe_level: int | None = None,
    ) -> None:
        self._ensure_entry(user_id)
        self.get_simulator_stats(user_id)
        
        updates = []
        params = []
        if manager_expiry is not None:
            updates.append("manager_expiry=?")
            params.append(manager_expiry)
        if insurance_expiry is not None:
            updates.append("insurance_expiry=?")
            params.append(insurance_expiry)
        if bodyguard_expiry is not None:
            updates.append("bodyguard_expiry=?")
            params.append(bodyguard_expiry)
        if pickaxe_level is not None:
            updates.append("pickaxe_level=?")
            params.append(pickaxe_level)
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_simulator_stats SET {', '.join(updates)} WHERE user_id=?"
            self.cur.execute(query, tuple(params))
            self.conn.commit()

    def get_all_active_managers(self) -> list[tuple[int, int, int]]:
        """Returns list of (user_id, last_collect, manager_expiry) for active managers"""
        import time
        self.cur.execute(
            "SELECT user_id, last_collect, manager_expiry FROM user_simulator_stats WHERE manager_expiry > ?",
            (int(time.time()),),
        )
        return self.cur.fetchall()

    def get_marriage(self, user_id: int) -> tuple | None:
        """Returns marriage details if user is married: (user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today)"""
        self.cur.execute(
            "SELECT user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        return self.cur.fetchone()

    def get_marriages(self, user_id: int) -> list[tuple]:
        """Returns list of all marriages for a user"""
        self.cur.execute(
            "SELECT user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        return self.cur.fetchall()


    def create_marriage(self, user_one: int, user_two: int, ring_type: str) -> bool:
        """Registers a new marriage in the database.

        Returns False without touching the existing row when this exact pair is
        already married (INSERT OR IGNORE protects their joint wallet/points).
        """
        import time
        now = int(time.time())
        self.cur.execute(
            "INSERT OR IGNORE INTO user_marry (user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today) VALUES (?, ?, ?, 0, 0, ?, 0, 0)",
            (user_one, user_two, ring_type, now)
        )
        self.conn.commit()
        return self.cur.rowcount > 0

    def delete_marriage(self, user_one: int, user_two: int) -> None:
        """Deletes a marriage registration"""
        self.cur.execute(
            "DELETE FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        self.conn.commit()

    def add_love_points(self, user_one: int, user_two: int, points: int, current_time: int, daily_limit: int = None) -> tuple[int, bool]:
        """Adds love points. Resets daily counter if calendar date changed. Caps at limit points/day."""
        import time
        self.cur.execute(
            "SELECT love_points, last_interact_time, interacts_today, ring_type FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if not row:
            return (0, False)
            
        love_points, last_interact_time, interacts_today, ring_type = row
        
        # Check calendar day reset
        now_struct = time.localtime(current_time)
        last_struct = time.localtime(last_interact_time)
        if now_struct.tm_yday != last_struct.tm_yday or now_struct.tm_year != last_struct.tm_year:
            interacts_today = 0
            
        if daily_limit is not None:
            limit = daily_limit
        else:
            limit = 30 if ring_type == "ring_eternal_butterfly" else 20

        if interacts_today >= limit:
            return (love_points, False)
            
        points_to_add = min(points, limit - interacts_today)
        new_love_points = love_points + points_to_add
        new_interacts = interacts_today + points_to_add
        
        self.cur.execute(
            "UPDATE user_marry SET love_points = ?, last_interact_time = ?, interacts_today = ? WHERE user_one = ? AND user_two = ?",
            (new_love_points, current_time, new_interacts, user_one, user_two)
        )
        self.conn.commit()
        return (new_love_points, True)

    def deduct_love_points(self, user_one: int, user_two: int, points: int) -> int:
        """Deducts love points, floor at 0. Returns new love points."""
        self.cur.execute(
            "SELECT love_points FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if not row:
            return 0
        love_points = row[0]
        new_love_points = max(0, love_points - points)
        self.cur.execute(
            "UPDATE user_marry SET love_points = ? WHERE user_one = ? AND user_two = ?",
            (new_love_points, user_one, user_two)
        )
        self.conn.commit()
        return new_love_points

    def update_joint_wallet(self, user_one: int, user_two: int, delta: int) -> int:
        """Updates joint wallet balance and returns new balance"""
        self.cur.execute(
            "SELECT joint_wallet FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if not row:
            return 0

        if row[0] + delta < 0:
            logger.warning(
                "update_joint_wallet clamped negative balance for marriage (%s, %s): %s + %s -> 0",
                user_one, user_two, row[0], delta,
            )
        new_balance = max(0, row[0] + delta)
        self.cur.execute(
            "UPDATE user_marry SET joint_wallet = ? WHERE user_one = ? AND user_two = ?",
            (new_balance, user_one, user_two)
        )
        self.conn.commit()
        return new_balance

    def apply_marriage_interest(self, user_one: int, user_two: int) -> tuple[int, int]:
        """Accrues pending joint-wallet interest (3%/ngày, trần 15M/ngày, tối đa 30 ngày) for a marriage.

        Only meaningful for ring_eternal_butterfly couples. Interest accrues strictly
        forward from last_interest_time; a compare-and-swap on that timestamp makes
        concurrent callers apply the same window exactly once.
        Returns (total_interest, new_joint_balance).
        """
        self.cur.execute(
            "SELECT joint_wallet, married_at, last_interest_time FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if not row:
            return (0, 0)
        joint_wallet, married_at, last_interest = row[0], row[1], row[2] or 0
        if joint_wallet <= 0:
            return (0, joint_wallet)
        if last_interest == 0:
            last_interest = married_at

        import datetime
        last_date = datetime.date.fromtimestamp(last_interest)
        now_date = datetime.date.fromtimestamp(int(time.time()))
        days_passed = (now_date - last_date).days
        if days_passed <= 0:
            return (0, joint_wallet)

        now = int(time.time())
        # Claim the interest window first: only one concurrent caller wins the CAS,
        # so the interest is computed and paid exactly once.
        self.cur.execute(
            "UPDATE user_marry SET last_interest_time = ? WHERE user_one = ? AND user_two = ? AND last_interest_time = ?",
            (now, user_one, user_two, last_interest)
        )
        if self.cur.rowcount == 0:
            return (0, joint_wallet)

        total_interest = 0
        temp_wallet = joint_wallet
        for _ in range(min(days_passed, 30)):  # Cap at 30 days of inactivity to prevent overflow
            day_interest = min(15_000_000, int(temp_wallet * 0.03))
            total_interest += day_interest
            temp_wallet += day_interest

        if total_interest > 0:
            self.cur.execute(
                "UPDATE user_marry SET joint_wallet = joint_wallet + ? WHERE user_one = ? AND user_two = ?",
                (total_interest, user_one, user_two)
            )
        self.conn.commit()
        return (total_interest, joint_wallet + total_interest)

    def couple_deposit_joint(self, user_id: int, user_one: int, user_two: int, amount: int) -> tuple[bool, int]:
        """Atomically moves `amount` cash from the user's wallet into the couple's joint wallet.

        Returns (success, new_joint_balance)."""
        if amount <= 0:
            return (False, 0)
        self._ensure_entry(user_id)
        try:
            self.cur.execute("SELECT money FROM economy WHERE user_id=?", (user_id,))
            row = self.cur.fetchone()
            if not row or row[0] < amount:
                return (False, 0)

            self.cur.execute(
                "SELECT joint_wallet FROM user_marry WHERE user_one = ? AND user_two = ?",
                (user_one, user_two)
            )
            marriage_row = self.cur.fetchone()
            if not marriage_row:
                return (False, 0)

            self.cur.execute("UPDATE economy SET money = MAX(0, money - ?) WHERE user_id=?", (amount, user_id))
            self.cur.execute(
                "UPDATE user_marry SET joint_wallet = joint_wallet + ? WHERE user_one = ? AND user_two = ?",
                (amount, user_one, user_two)
            )
            new_joint = marriage_row[0] + amount
            self.conn.commit()
            return (True, new_joint)
        except Exception:
            self.conn.rollback()
            raise

    def couple_withdraw_joint(self, requester_id: int, user_one: int, user_two: int, amount: int) -> tuple[bool, int]:
        """Atomically moves `amount` from the couple's joint wallet into the requester's cash.

        Returns (success, new_joint_balance)."""
        if amount <= 0:
            return (False, 0)
        self._ensure_entry(requester_id)
        try:
            self.cur.execute(
                "SELECT joint_wallet FROM user_marry WHERE user_one = ? AND user_two = ?",
                (user_one, user_two)
            )
            row = self.cur.fetchone()
            if not row or row[0] < amount:
                return (False, row[0] if row else 0)

            self.cur.execute(
                "UPDATE user_marry SET joint_wallet = joint_wallet - ? WHERE user_one = ? AND user_two = ?",
                (amount, user_one, user_two)
            )
            self.cur.execute("UPDATE economy SET money = MAX(0, money + ?) WHERE user_id=?", (amount, requester_id))
            new_joint = row[0] - amount
            self.conn.commit()
            return (True, new_joint)
        except Exception:
            self.conn.rollback()
            raise

    def purchase_couple_asset(self, buyer_id: int, user_one: int, user_two: int, kind: str, item_id: str, price: int) -> tuple[str, int, int, str | None]:
        """Atomically buys a couple asset (kind: 'estate' | 'vehicle' | 'pet') with the buyer's gold.

        The replaced asset in the same slot is liquidated: 25% of its recorded price is
        refunded to its original buyer. Everything commits once or not at all.
        Returns (status, refund_amount, refund_target_id, replaced_item_id) where status is
        "ok" | "insufficient" | "owned"."""
        column = {"estate": "estate", "vehicle": "vehicle", "pet": "pet"}.get(kind)
        if not column or price <= 0:
            return ("insufficient", 0, 0, None)
        self._ensure_entry(buyer_id)
        try:
            self.cur.execute("SELECT credits FROM economy WHERE user_id=?", (buyer_id,))
            row = self.cur.fetchone()
            if not row or row[0] < price:
                return ("insufficient", 0, 0, None)

            self.cur.execute(
                "SELECT estate_id, estate_price, estate_bought_by, vehicle_id, vehicle_price, vehicle_bought_by, pet_id, pet_price, pet_bought_by FROM couple_assets WHERE (user_one = ? AND user_two = ?) OR (user_one = ? AND user_two = ?)",
                (user_one, user_two, user_two, user_one)
            )
            assets = self.cur.fetchone()

            col_index = {"estate": 0, "vehicle": 3, "pet": 6}[column]
            refund_amount = 0
            refund_target = 0
            replaced_id = None
            if assets and assets[col_index] and assets[col_index + 1] > 0 and assets[col_index + 2] > 0:
                replaced_id = assets[col_index]
                refund_amount = int(assets[col_index + 1] * 0.25)
                refund_target = assets[col_index + 2]
            if replaced_id == item_id:
                return ("owned", 0, 0, None)

            self.cur.execute("UPDATE economy SET credits = MAX(0, credits - ?) WHERE user_id=?", (price, buyer_id))
            self._record_gold_flow(-price)
            if refund_amount > 0 and refund_target > 0:
                self.cur.execute("UPDATE economy SET credits = MAX(0, credits + ?) WHERE user_id=?", (refund_amount, refund_target))
                self._record_gold_flow(refund_amount)

            id_col, price_col, buyer_col = f"{column}_id", f"{column}_price", f"{column}_bought_by"
            if assets:
                self.cur.execute(
                    f"UPDATE couple_assets SET {id_col} = ?, {price_col} = ?, {buyer_col} = ? WHERE (user_one = ? AND user_two = ?) OR (user_one = ? AND user_two = ?)",
                    (item_id, price, buyer_id, user_one, user_two, user_two, user_one)
                )
            else:
                self.cur.execute(
                    f"INSERT INTO couple_assets (user_one, user_two, {id_col}, {price_col}, {buyer_col}) VALUES (?, ?, ?, ?, ?)",
                    (user_one, user_two, item_id, price, buyer_id)
                )
            self.conn.commit()
            return ("ok", refund_amount, refund_target, replaced_id)
        except Exception:
            self.conn.rollback()
            raise

    def add_marriage_love_points_raw(self, user_one: int, user_two: int, points: int) -> int:
        """Adds love points bypassing the daily cap (e.g. wish blessings). Returns the new total."""
        self.cur.execute(
            "UPDATE user_marry SET love_points = love_points + ? WHERE user_one = ? AND user_two = ?",
            (points, user_one, user_two)
        )
        if self.cur.rowcount == 0:
            return 0
        self.cur.execute(
            "SELECT love_points FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        self.conn.commit()
        return row[0] if row else 0

    def get_marriage_multiplier(self, user_id: int) -> float:
        """Calculates the wage/work multiplier for a user based on their marriage ring type.

        Multipliers are flat per ring and no longer scale with intimacy points."""
        marriages = self.get_marriages(user_id)
        if not marriages:
            return 1.0

        ring_buffs = {
            "ring_grass": 1.0,
            "ring_quartz": 1.02,
            "ring_aquamarine": 1.03,
            "ring_emerald": 1.04,
            "ring_amethyst": 1.05,
            "ring_cupid": 1.07,
            "ring_nhankat": 1.30,
            "ring_citrine": 1.09,
            "ring_ruby": 1.12,
            "ring_sapphire": 1.15,
            "ring_sunburst": 1.20,
            "ring_gothic": 1.25,
            "ring_angel": 1.30,
            "ring_divine": 1.40,
            "ring_eternal_butterfly": 1.12,
            "ring_silver": 1.02,   # legacy ring types
            "ring_gold": 1.05,
        }

        max_mult = 1.0
        for marriage in marriages:
            mult = ring_buffs.get(marriage[2], 1.0)
            if mult > max_mult:
                max_mult = mult

        return max_mult

    def get_marriage_times(self, user_one: int, user_two: int) -> tuple[int, int]:
        """Returns (last_interest_time, last_wish_time) for a marriage"""
        self.cur.execute(
            "SELECT last_interest_time, last_wish_time FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if row:
            return (row[0] or 0, row[1] or 0)
        return (0, 0)

    def update_marriage_times(self, user_one: int, user_two: int, last_interest_time: int | None = None, last_wish_time: int | None = None) -> None:
        """Updates timestamps for a marriage"""
        updates = []
        params = []
        if last_interest_time is not None:
            updates.append("last_interest_time = ?")
            params.append(last_interest_time)
        if last_wish_time is not None:
            updates.append("last_wish_time = ?")
            params.append(last_wish_time)
            
        if updates:
            params.extend([user_one, user_two])
            self.cur.execute(
                f"UPDATE user_marry SET {', '.join(updates)} WHERE user_one = ? AND user_two = ?",
                tuple(params)
            )
            self.conn.commit()


    def get_marriage_ig(self, user_one: int, user_two: int) -> tuple[str, str]:
        """Returns (user_one_ig, user_two_ig) for a specific marriage entry"""
        self.cur.execute(
            "SELECT user_one_ig, user_two_ig FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if row:
            return (row[0] or "", row[1] or "")
        return ("", "")

    def update_marriage_ig(self, user_one: int, user_two: int, target_user_id: int, ig_handle: str) -> None:
        """Updates the Instagram handle for the target_user_id in marriage entry (user_one, user_two)"""
        if target_user_id == user_one:
            self.cur.execute(
                "UPDATE user_marry SET user_one_ig = ? WHERE user_one = ? AND user_two = ?",
                (ig_handle, user_one, user_two)
            )
        else:
            self.cur.execute(
                "UPDATE user_marry SET user_two_ig = ? WHERE user_one = ? AND user_two = ?",
                (ig_handle, user_one, user_two)
            )
        self.conn.commit()

    def get_marriage_status(self, user_one: int, user_two: int) -> str:
        """Returns the custom relationship status for a specific marriage entry"""
        self.cur.execute(
            "SELECT status FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if row:
            return row[0] or "Vợ Chồng"
        return "Vợ Chồng"

    def update_marriage_status(self, user_one: int, user_two: int, status_text: str) -> None:
        """Updates the custom relationship status for a specific marriage entry"""
        self.cur.execute(
            "UPDATE user_marry SET status = ? WHERE user_one = ? AND user_two = ?",
            (status_text, user_one, user_two)
        )
        self.conn.commit()

    def get_marriage_saying(self, user_one: int, user_two: int) -> str:
        """Returns the custom saying for a specific marriage entry"""
        self.cur.execute(
            "SELECT saying FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if row:
            return row[0] or ""
        return ""

    def update_marriage_saying(self, user_one: int, user_two: int, saying_text: str) -> None:
        """Updates the custom saying for a specific marriage entry"""
        self.cur.execute(
            "UPDATE user_marry SET saying = ? WHERE user_one = ? AND user_two = ?",
            (saying_text, user_one, user_two)
        )
        self.conn.commit()

    def update_marriage_ring(self, user_one: int, user_two: int, ring_type: str) -> None:
        """Updates the marriage ring type for a specific marriage entry"""
        self.cur.execute(
            "UPDATE user_marry SET ring_type = ? WHERE user_one = ? AND user_two = ?",
            (ring_type, user_one, user_two)
        )
        self.conn.commit()

    def update_marriage_date(self, user_one: int, user_two: int, timestamp: int) -> None:
        """Updates the married_at timestamp for a specific marriage entry"""
        self.cur.execute(
            "UPDATE user_marry SET married_at = ? WHERE user_one = ? AND user_two = ?",
            (timestamp, user_one, user_two)
        )
        self.conn.commit()


    def get_top_marriages(self, sort_by: str, limit: int = 10) -> list[tuple]:
        """Returns list of top marriages ordered by the given criteria: love_points, joint_wallet, or married_at (ascending/longest)."""
        if sort_by == "love_points":
            query = "SELECT user_one, user_two, ring_type, love_points, joint_wallet, married_at FROM user_marry ORDER BY love_points DESC LIMIT ?"
        elif sort_by == "joint_wallet":
            query = "SELECT user_one, user_two, ring_type, love_points, joint_wallet, married_at FROM user_marry ORDER BY joint_wallet DESC LIMIT ?"
        elif sort_by == "married_at":
            query = "SELECT user_one, user_two, ring_type, love_points, joint_wallet, married_at FROM user_marry ORDER BY married_at ASC LIMIT ?"
        else:
            query = "SELECT user_one, user_two, ring_type, love_points, joint_wallet, married_at FROM user_marry ORDER BY love_points DESC LIMIT ?"

        self.cur.execute(query, (limit,))
        return self.cur.fetchall()

    def get_user_titles(self, user_id: int) -> list[str]:
        """Gets all custom/exclusive titles of a user from user_titles table."""
        self.cur.execute("SELECT title FROM user_titles WHERE user_id = ?", (user_id,))
        return [row[0] for row in self.cur.fetchall()]

    def add_user_title(self, user_id: int, title: str) -> None:
        """Adds a custom/exclusive title for a user."""
        self.cur.execute("INSERT OR IGNORE INTO user_titles (user_id, title) VALUES (?, ?)", (user_id, title))
        self.conn.commit()

    def remove_user_title(self, user_id: int, title: str) -> None:
        """Removes a custom/exclusive title from a user."""
        self.cur.execute("DELETE FROM user_titles WHERE user_id = ? AND title = ?", (user_id, title))
        self.conn.commit()

    def log_achievement_unlock(self, user_id: int, game: str, achievement_key: str) -> bool:
        """Logs an achievement unlock. Returns True if successfully logged (was not logged before)."""
        self.cur.execute(
            "SELECT 1 FROM user_achievements_log WHERE user_id = ? AND game = ? AND achievement_key = ?",
            (user_id, game, achievement_key)
        )
        if self.cur.fetchone():
            return False
        import time
        self.cur.execute(
            "INSERT INTO user_achievements_log (user_id, game, achievement_key, unlocked_at) VALUES (?, ?, ?, ?)",
            (user_id, game, achievement_key, int(time.time()))
        )
        self.conn.commit()
        return True

    def get_all_logged_achievements(self) -> list[tuple[int, int, str, str, int]]:
        """Gets all achievements log ordered by earliest (id ASC)."""
        self.cur.execute("SELECT id, user_id, game, achievement_key, unlocked_at FROM user_achievements_log ORDER BY id ASC")
        return self.cur.fetchall()

    def get_couple_assets(self, user_one: int, user_two: int) -> tuple | None:
        """
        Returns (estate_id, estate_price, estate_bought_by, vehicle_id, vehicle_price, vehicle_bought_by, pet_id, pet_price, pet_bought_by)
        or None if no assets record exists.
        """
        self.cur.execute(
            "SELECT estate_id, estate_price, estate_bought_by, vehicle_id, vehicle_price, vehicle_bought_by, pet_id, pet_price, pet_bought_by FROM couple_assets WHERE (user_one = ? AND user_two = ?) OR (user_one = ? AND user_two = ?)",
            (user_one, user_two, user_two, user_one)
        )
        return self.cur.fetchone()

    def set_couple_estate(self, user_one: int, user_two: int, estate_id: str, price: int, bought_by: int) -> None:
        row = self.get_couple_assets(user_one, user_two)
        if row:
            self.cur.execute(
                "UPDATE couple_assets SET estate_id = ?, estate_price = ?, estate_bought_by = ? WHERE (user_one = ? AND user_two = ?) OR (user_one = ? AND user_two = ?)",
                (estate_id, price, bought_by, user_one, user_two, user_two, user_one)
            )
        else:
            self.cur.execute(
                "INSERT INTO couple_assets (user_one, user_two, estate_id, estate_price, estate_bought_by) VALUES (?, ?, ?, ?, ?)",
                (user_one, user_two, estate_id, price, bought_by)
            )
        self.conn.commit()

    def set_couple_vehicle(self, user_one: int, user_two: int, vehicle_id: str, price: int, bought_by: int) -> None:
        row = self.get_couple_assets(user_one, user_two)
        if row:
            self.cur.execute(
                "UPDATE couple_assets SET vehicle_id = ?, vehicle_price = ?, vehicle_bought_by = ? WHERE (user_one = ? AND user_two = ?) OR (user_one = ? AND user_two = ?)",
                (vehicle_id, price, bought_by, user_one, user_two, user_two, user_one)
            )
        else:
            self.cur.execute(
                "INSERT INTO couple_assets (user_one, user_two, vehicle_id, vehicle_price, vehicle_bought_by) VALUES (?, ?, ?, ?, ?)",
                (user_one, user_two, vehicle_id, price, bought_by)
            )
        self.conn.commit()

    def set_couple_pet(self, user_one: int, user_two: int, pet_id: str, price: int, bought_by: int) -> None:
        row = self.get_couple_assets(user_one, user_two)
        if row:
            self.cur.execute(
                "UPDATE couple_assets SET pet_id = ?, pet_price = ?, pet_bought_by = ? WHERE (user_one = ? AND user_two = ?) OR (user_one = ? AND user_two = ?)",
                (pet_id, price, bought_by, user_one, user_two, user_two, user_one)
            )
        else:
            self.cur.execute(
                "INSERT INTO couple_assets (user_one, user_two, pet_id, pet_price, pet_bought_by) VALUES (?, ?, ?, ?, ?)",
                (user_one, user_two, pet_id, price, bought_by)
            )
        self.conn.commit()

    def clear_couple_assets(self, user_one: int, user_two: int) -> None:
        self.cur.execute(
            "DELETE FROM couple_assets WHERE (user_one = ? AND user_two = ?) OR (user_one = ? AND user_two = ?)",
            (user_one, user_two, user_two, user_one)
        )
        self.conn.commit()

    def get_setting(self, key: str, default: str = "") -> str:
        """Gets a string setting from system_settings table."""
        self.cur.execute("SELECT value FROM system_settings WHERE key = ?", (key,))
        row = self.cur.fetchone()
        return row[0] if row and row[0] is not None else default

    def set_setting(self, key: str, value: str) -> None:
        """Sets or updates a string setting in system_settings table."""
        self.cur.execute(
            """INSERT INTO system_settings (key, value) VALUES (?, ?)
               ON CONFLICT(key) DO UPDATE SET value = EXCLUDED.value""",
            (key, str(value))
        )
        self.conn.commit()

    def get_masoi_stats(self, user_id: int) -> dict:
        """Returns dict of user's Ma Sói rank stats."""
        self.cur.execute(
            "SELECT points, plays, wins, losses, wolf_wins, villager_wins, tanner_wins FROM user_masoi_stats WHERE user_id = ?",
            (user_id,)
        )
        row = self.cur.fetchone()
        if not row:
            return {
                "user_id": user_id, "points": 0, "plays": 0, "wins": 0,
                "losses": 0, "wolf_wins": 0, "villager_wins": 0, "tanner_wins": 0
            }
        return {
            "user_id": user_id, "points": row[0], "plays": row[1], "wins": row[2],
            "losses": row[3], "wolf_wins": row[4], "villager_wins": row[5], "tanner_wins": row[6]
        }

    def add_masoi_points(self, user_id: int, points_delta: int, is_win: bool, faction: str = "VILLAGER") -> None:
        """Updates Ma Sói rank points and game stats for a player."""
        stats = self.get_masoi_stats(user_id)
        new_points = max(0, stats["points"] + points_delta)
        new_plays = stats["plays"] + 1
        new_wins = stats["wins"] + (1 if is_win else 0)
        new_losses = stats["losses"] + (0 if is_win else 1)
        
        wolf_wins = stats["wolf_wins"] + (1 if is_win and faction == "WEREWOLF" else 0)
        villager_wins = stats["villager_wins"] + (1 if is_win and faction == "VILLAGER" else 0)
        tanner_wins = stats["tanner_wins"] + (1 if is_win and faction == "INDEPENDENT" else 0)

        self.cur.execute(
            """INSERT INTO user_masoi_stats (user_id, points, plays, wins, losses, wolf_wins, villager_wins, tanner_wins)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET
                 points = EXCLUDED.points,
                 plays = EXCLUDED.plays,
                 wins = EXCLUDED.wins,
                 losses = EXCLUDED.losses,
                 wolf_wins = EXCLUDED.wolf_wins,
                 villager_wins = EXCLUDED.villager_wins,
                 tanner_wins = EXCLUDED.tanner_wins""",
            (user_id, new_points, new_plays, new_wins, new_losses, wolf_wins, villager_wins, tanner_wins)
        )
        self.conn.commit()

    def get_masoi_leaderboard(self, limit: int = 10) -> list[tuple[int, int, int, int]]:
        """Returns list of (user_id, points, plays, wins) ordered by points DESC."""
        self.cur.execute(
            "SELECT user_id, points, plays, wins FROM user_masoi_stats ORDER BY points DESC, wins DESC LIMIT ?",
            (limit,)
        )
        return self.cur.fetchall()

    def is_masoi_vip(self, user_id: int) -> bool:
        """Kiểm tra người chơi có đang sở hữu gói VIP Ma Sói hay không."""
        now = int(time.time())
        self.cur.execute("SELECT expires_at FROM masoi_vip WHERE user_id = ?", (user_id,))
        row = self.cur.fetchone()
        return bool(row and row[0] > now)

    def add_masoi_vip(self, user_id: int, days: int) -> int:
        """Cấp hoặc gia hạn thêm số ngày VIP Ma Sói cho người chơi."""
        now = int(time.time())
        seconds = days * 86400
        self.cur.execute("SELECT expires_at FROM masoi_vip WHERE user_id = ?", (user_id,))
        row = self.cur.fetchone()
        if row and row[0] > now:
            new_expires = row[0] + seconds
        else:
            new_expires = now + seconds

        self.cur.execute(
            """INSERT INTO masoi_vip (user_id, expires_at) VALUES (?, ?)
               ON CONFLICT(user_id) DO UPDATE SET expires_at = EXCLUDED.expires_at""",
            (user_id, new_expires)
        )
        self.conn.commit()
        return new_expires

    def set_masoi_last_words(self, user_id: int, text: str) -> bool:
        """Cập nhật Lời trăn trối cá nhân cho người chơi VIP."""
        text = text.strip()[:150]
        now = int(time.time())
        self.cur.execute("SELECT expires_at FROM masoi_vip WHERE user_id = ?", (user_id,))
        row = self.cur.fetchone()
        expires = row[0] if (row and row[0] > now) else (now + 86400 * 30)
        self.cur.execute(
            """INSERT INTO masoi_vip (user_id, expires_at, last_words) VALUES (?, ?, ?)
               ON CONFLICT(user_id) DO UPDATE SET last_words = EXCLUDED.last_words""",
            (user_id, expires, text)
        )
        self.conn.commit()
        return True

    def get_masoi_vip_info(self, user_id: int) -> dict:
        """Lấy đầy đủ thông tin VIP của người chơi."""
        now = int(time.time())
        self.cur.execute("SELECT expires_at, last_words FROM masoi_vip WHERE user_id = ?", (user_id,))
        row = self.cur.fetchone()
        if not row:
            return {"is_vip": False, "expires_at": 0, "last_words": ""}
        is_vip = bool(row[0] > now)
        return {"is_vip": is_vip, "expires_at": row[0], "last_words": row[1] or ""}

    def remove_masoi_vip(self, user_id: int) -> bool:
        """Hủy gói VIP Ma Sói của người chơi ngay lập tức."""
        self.cur.execute("UPDATE masoi_vip SET expires_at = 0 WHERE user_id = ?", (user_id,))
        self.conn.commit()
        return True

    def get_all_masoi_vip(self) -> list:
        """Lấy danh sách tất cả tài khoản VIP Ma Sói còn hạn, sắp xếp theo ngày hết hạn."""
        now = int(time.time())
        self.cur.execute(
            "SELECT user_id, expires_at, last_words FROM masoi_vip WHERE expires_at > ? ORDER BY expires_at ASC",
            (now,)
        )
        return self.cur.fetchall()

    def _ensure_custom_badge_column(self):
        try:
            self.cur.execute("ALTER TABLE user_masoi_stats ADD COLUMN custom_badge TEXT DEFAULT ''")
            self.conn.commit()
        except sqlite3.OperationalError:
            pass

    def set_masoi_custom_badge(self, user_id: int, badge: str) -> bool:
        """Cài đặt huy hiệu tự chọn hiển thị cho người chơi trong game Ma Sói."""
        self._ensure_custom_badge_column()
        self.cur.execute("SELECT points FROM user_masoi_stats WHERE user_id = ?", (user_id,))
        if not self.cur.fetchone():
            self.cur.execute("INSERT INTO user_masoi_stats (user_id, custom_badge) VALUES (?, ?)", (user_id, badge))
        else:
            self.cur.execute("UPDATE user_masoi_stats SET custom_badge = ? WHERE user_id = ?", (badge, user_id))
        self.conn.commit()
        return True

    def get_masoi_custom_badge(self, user_id: int) -> str:
        """Lấy huy hiệu tự chọn của người chơi trong game Ma Sói."""
        try:
            self.cur.execute("SELECT custom_badge FROM user_masoi_stats WHERE user_id = ?", (user_id,))
            row = self.cur.fetchone()
            return row[0] if row and row[0] else ""
        except sqlite3.OperationalError:
            self._ensure_custom_badge_column()
            return ""

    def remove_masoi_custom_badge(self, user_id: int) -> bool:
        """Xóa huy hiệu tự chọn của người chơi trong game Ma Sói."""
        self._ensure_custom_badge_column()
        try:
            self.cur.execute("UPDATE user_masoi_stats SET custom_badge = '' WHERE user_id = ?", (user_id,))
            self.conn.commit()
        except sqlite3.OperationalError:
            pass
        return True

    # --- Jail System Methods ---
    def _ensure_jail_table(self) -> None:
        try:
            self.cur.execute("PRAGMA table_info(user_jail)")
            columns = self.cur.fetchall()
            if columns:
                pk_cols = [col for col in columns if col[5] > 0]
                if len(pk_cols) < 2:
                    self.cur.execute("DROP TABLE user_jail")
            self.cur.execute(
                """CREATE TABLE IF NOT EXISTS user_jail (
                user_id INTEGER NOT NULL,
                guild_id INTEGER NOT NULL DEFAULT 0,
                jailer_id INTEGER NOT NULL DEFAULT 0,
                clean_count INTEGER NOT NULL DEFAULT 0,
                total_clean_count INTEGER NOT NULL DEFAULT 0,
                reason TEXT DEFAULT 'Không có lý do',
                jailed_at INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY (user_id, guild_id)
            )"""
            )
            self.conn.commit()
        except sqlite3.OperationalError:
            pass

    def set_jail_channel(self, guild_id: int, channel_id: int) -> None:
        key = f"jail_channel_{guild_id}"
        self.set_setting(key, str(channel_id))

    def get_jail_channel(self, guild_id: int) -> int:
        key = f"jail_channel_{guild_id}"
        val = self.get_setting(key)
        return int(val) if val and val.isdigit() else 0

    def set_jail_role(self, guild_id: int, role_id: int) -> None:
        key = f"jail_role_{guild_id}"
        self.set_setting(key, str(role_id))

    def get_jail_role(self, guild_id: int) -> int:
        key = f"jail_role_{guild_id}"
        val = self.get_setting(key)
        return int(val) if val and val.isdigit() else 0

    # --- Channel Control Settings ---
    def get_blocked_channels(self, guild_id: int) -> list[int]:
        key = f"blocked_channels_{guild_id}"
        val = self.get_setting(key)
        if not val:
            return []
        try:
            return [int(x) for x in json.loads(val)]
        except Exception:
            return []

    def set_blocked_channels(self, guild_id: int, channels: list[int]) -> None:
        key = f"blocked_channels_{guild_id}"
        self.set_setting(key, json.dumps(channels))

    def toggle_blocked_channel(self, guild_id: int, channel_id: int) -> bool:
        current = self.get_blocked_channels(guild_id)
        if channel_id in current:
            current.remove(channel_id)
            is_blocked = False
        else:
            current.append(channel_id)
            is_blocked = True
        self.set_blocked_channels(guild_id, current)
        return is_blocked

    def remove_blocked_channel(self, guild_id: int, channel_id: int) -> bool:
        current = self.get_blocked_channels(guild_id)
        if channel_id in current:
            current.remove(channel_id)
            self.set_blocked_channels(guild_id, current)
            return True
        return False

    def get_allowed_channels(self, guild_id: int) -> list[int]:
        key = f"allowed_channels_{guild_id}"
        val = self.get_setting(key)
        if not val:
            return []
        try:
            return [int(x) for x in json.loads(val)]
        except Exception:
            return []

    def set_allowed_channels(self, guild_id: int, channels: list[int]) -> None:
        key = f"allowed_channels_{guild_id}"
        self.set_setting(key, json.dumps(channels))

    def toggle_allowed_channel(self, guild_id: int, channel_id: int) -> bool:
        current = self.get_allowed_channels(guild_id)
        if channel_id in current:
            current.remove(channel_id)
            is_allowed = False
        else:
            current.append(channel_id)
            is_allowed = True
        self.set_allowed_channels(guild_id, current)
        return is_allowed

    def add_to_jail(
        self, user_id: int, guild_id: int, jailer_id: int, clean_count: int, reason: str = "Không có lý do"
    ) -> None:
        self._ensure_jail_table()
        now = int(time.time())
        self.cur.execute(
            """INSERT OR REPLACE INTO user_jail 
               (user_id, guild_id, jailer_id, clean_count, total_clean_count, reason, jailed_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (user_id, guild_id, jailer_id, clean_count, clean_count, reason, now),
        )
        self.conn.commit()

    def get_jail_info(self, user_id: int, guild_id: int = 0) -> dict | None:
        self._ensure_jail_table()
        if guild_id > 0:
            self.cur.execute(
                "SELECT user_id, guild_id, jailer_id, clean_count, total_clean_count, reason, jailed_at FROM user_jail WHERE user_id = ? AND guild_id = ?",
                (user_id, guild_id),
            )
        else:
            self.cur.execute(
                "SELECT user_id, guild_id, jailer_id, clean_count, total_clean_count, reason, jailed_at FROM user_jail WHERE user_id = ?",
                (user_id,),
            )
        row = self.cur.fetchone()
        if not row:
            return None
        return {
            "user_id": row[0],
            "guild_id": row[1],
            "jailer_id": row[2],
            "clean_count": row[3],
            "total_clean_count": row[4],
            "reason": row[5],
            "jailed_at": row[6],
        }

    def update_jail_clean_count(self, user_id: int, guild_id: int = 0, amount: int = 1) -> int:
        info = self.get_jail_info(user_id, guild_id)
        if not info:
            return 0
        target_guild_id = info["guild_id"] if guild_id == 0 else guild_id
        new_count = max(0, info["clean_count"] - amount)
        if new_count <= 0:
            self.remove_from_jail(user_id, target_guild_id)
            return 0
        else:
            self.cur.execute(
                "UPDATE user_jail SET clean_count = ? WHERE user_id = ? AND guild_id = ?",
                (new_count, user_id, target_guild_id),
            )
            self.conn.commit()
            return new_count

    def remove_from_jail(self, user_id: int, guild_id: int = 0) -> None:
        self._ensure_jail_table()
        if guild_id > 0:
            self.cur.execute("DELETE FROM user_jail WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        else:
            self.cur.execute("DELETE FROM user_jail WHERE user_id = ?", (user_id,))
        self.conn.commit()

    def is_in_jail(self, user_id: int, guild_id: int = 0) -> bool:
        self._ensure_jail_table()
        if guild_id > 0:
            self.cur.execute("SELECT 1 FROM user_jail WHERE user_id = ? AND guild_id = ?", (user_id, guild_id))
        else:
            self.cur.execute("SELECT 1 FROM user_jail WHERE user_id = ?", (user_id,))
        return self.cur.fetchone() is not None

    def get_all_prisoners(self, guild_id: int = 0) -> list[dict]:
        self._ensure_jail_table()
        if guild_id > 0:
            self.cur.execute(
                "SELECT user_id, guild_id, jailer_id, clean_count, total_clean_count, reason, jailed_at FROM user_jail WHERE guild_id = ?",
                (guild_id,),
            )
        else:
            self.cur.execute(
                "SELECT user_id, guild_id, jailer_id, clean_count, total_clean_count, reason, jailed_at FROM user_jail"
            )
        rows = self.cur.fetchall()
        result = []
        for r in rows:
            result.append(
                {
                    "user_id": r[0],
                    "guild_id": r[1],
                    "jailer_id": r[2],
                    "clean_count": r[3],
                    "total_clean_count": r[4],
                    "reason": r[5],
                    "jailed_at": r[6],
                }
            )
        return result


    # --- GIFT CODE SYSTEM ---

    def create_gift_code(
        self, code: str, reward_money: int = 0, reward_credits: float = 0.0,
        max_uses: int = 0, expires_at: int = 0,
    ) -> bool:
        """Tạo gift code mới. Trả về True nếu tạo thành công, False nếu code đã tồn tại."""
        try:
            self.cur.execute(
                "INSERT INTO gift_codes(code, reward_money, reward_credits, max_uses, used_count, expires_at, created_at) "
                "VALUES(?, ?, ?, ?, 0, ?, ?)",
                (code.upper(), int(reward_money), float(reward_credits), int(max_uses), int(expires_at), int(time.time())),
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def redeem_gift_code(self, user_id: int, code: str) -> tuple[bool, str, int, float]:
        """Nhập gift code. Trả về (success, message, money_reward, credits_reward)."""
        code = code.upper()
        self.cur.execute("SELECT reward_money, reward_credits, max_uses, used_count, expires_at FROM gift_codes WHERE code=?", (code,))
        row = self.cur.fetchone()
        if not row:
            return (False, "❌ Mã code không hợp lệ hoặc không tồn tại.", 0, 0.0)

        reward_money, reward_credits, max_uses, used_count, expires_at = row

        # Kiểm tra đã nhập chưa
        self.cur.execute("SELECT 1 FROM gift_code_claims WHERE code=? AND user_id=?", (code, user_id))
        if self.cur.fetchone():
            return (False, "⚠️ Bạn đã nhập mã code này rồi.", 0, 0.0)

        # Kiểm tra hết hạn
        if expires_at > 0 and int(time.time()) > expires_at:
            return (False, "⏰ Mã code này đã hết hạn.", 0, 0.0)

        # Kiểm tra hết lượt
        if max_uses > 0 and used_count >= max_uses:
            return (False, "📛 Mã code này đã hết lượt sử dụng.", 0, 0.0)

        # Cộng thưởng
        self._ensure_entry(user_id)
        if reward_money > 0:
            self.cur.execute("UPDATE economy SET money=MAX(0, money + ?) WHERE user_id=?", (int(reward_money), user_id))
        if reward_credits > 0:
            self.cur.execute("UPDATE economy SET credits=MAX(0, credits + ?) WHERE user_id=?", (reward_credits, user_id))

        # Ghi nhận claim
        self.cur.execute(
            "INSERT INTO gift_code_claims(code, user_id, claimed_at) VALUES(?, ?, ?)",
            (code, user_id, int(time.time())),
        )
        self.cur.execute("UPDATE gift_codes SET used_count=used_count+1 WHERE code=?", (code,))
        self.conn.commit()
        return (True, "✅ Nhập code thành công!", reward_money, reward_credits)

    def delete_gift_code(self, code: str) -> bool:
        """Xóa gift code. Trả về True nếu xóa thành công."""
        code = code.upper()
        self.cur.execute("DELETE FROM gift_codes WHERE code=?", (code,))
        self.cur.execute("DELETE FROM gift_code_claims WHERE code=?", (code,))
        deleted = self.cur.rowcount > 0
        self.conn.commit()
        return deleted

    def list_gift_codes(self) -> list[tuple]:
        """Liệt kê tất cả gift codes."""
        self.cur.execute(
            "SELECT code, reward_money, reward_credits, max_uses, used_count, expires_at, created_at FROM gift_codes ORDER BY created_at DESC"
        )
        return self.cur.fetchall()


def _locked(method):
    """Serializes public Economy methods behind the shared reentrant lock."""
    @functools.wraps(method)
    def wrapper(self, *args, **kwargs):
        with self._lock:
            return method(self, *args, **kwargs)
    return wrapper


for _name, _member in list(vars(Economy).items()):
    if _name.startswith("_") or _name == "transaction":
        continue
    if callable(_member) and not isinstance(_member, (classmethod, staticmethod)):
        setattr(Economy, _name, _locked(_member))
