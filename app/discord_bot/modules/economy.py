from collections.abc import Callable
import logging
import random
import shutil
import sqlite3
from pathlib import Path
from typing import Tuple, List

from app.config import config

Entry = Tuple[int, int, int]
DATABASE_PATH = Path(config.storage.database_path)
LEGACY_DATABASE_PATH = Path(__file__).resolve().parents[3] / "economy.db"
SCHEMA_VERSION = 30


logger = logging.getLogger(__name__)


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
}


class Economy:
    """A wrapper for the economy database"""

    def __init__(self):
        self.open()

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
        self.cur.execute("UPDATE economy SET money=0, credits=0, loan_amount=0, loan_due=0, last_daily=0, daily_streak=0, equipped_banner=NULL")
        self.cur.execute("DELETE FROM user_businesses")
        self.cur.execute("DELETE FROM user_portfolio")
        self.cur.execute("DELETE FROM user_inventory")
        self.cur.execute("DELETE FROM user_simulator_stats")
        self.cur.execute("DELETE FROM user_roulette")
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

    def add_credits(self, user_id: int, credits_to_add: int) -> Entry:
        self._ensure_entry(user_id)
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

    def get_setting(self, key: str) -> str | None:
        self.cur.execute("SELECT value FROM system_settings WHERE key=?", (key,))
        row = self.cur.fetchone()
        return row[0] if row else None

    def set_setting(self, key: str, value: str) -> None:
        self.cur.execute(
            "INSERT OR REPLACE INTO system_settings(key, value) VALUES(?, ?)",
            (key, value),
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
        self.cur.execute(
            "INSERT OR REPLACE INTO user_portfolio(user_id, symbol, shares) VALUES(?, ?, ?)",
            (user_id, symbol, max(0.0, shares)),
        )
        self.conn.commit()

    def get_stock_holders(self, symbol: str) -> list[tuple[int, float]]:
        self.cur.execute("SELECT user_id, shares FROM user_portfolio WHERE symbol=? AND shares > 0.0", (symbol.upper(),))
        return self.cur.fetchall()


    def get_stock_prices(self) -> list[tuple[str, int, int, float]]:
        self.cur.execute("SELECT symbol, price, prev_price, change_percent FROM stock_prices")
        return self.cur.fetchall()

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

    def get_pity_golden(self, user_id: int) -> int:
        self._ensure_entry(user_id)
        self.cur.execute("SELECT pity_golden FROM economy WHERE user_id=?", (user_id,))
        row = self.cur.fetchone()
        return row[0] if row else 0

    def set_pity_golden(self, user_id: int, pity: int) -> None:
        self._ensure_entry(user_id)
        self.cur.execute("UPDATE economy SET pity_golden=? WHERE user_id=?", (int(pity), user_id))
        self.conn.commit()

    def add_cock(self, user_id: int, name: str, rarity: str, hp: int, atk: int, df: int, spd: int, luk: int) -> tuple[int, bool, bool, int, int, int, dict]:
        # Check if the user already has a cock with this name (breed)
        breed_names = [name]
        if name in ("Luffy", "Luffy Gear 4"):
            breed_names = ["Luffy", "Luffy Gear 4"]
        
        placeholders = ", ".join("?" for _ in breed_names)
        self.cur.execute(
            f"SELECT id, name, stars, shards, hp, atk, df, spd, luk FROM user_cocks WHERE user_id=? AND name IN ({placeholders}) LIMIT 1",
            tuple([user_id] + breed_names)
        )
        row = self.cur.fetchone()
        
        if row:
            cock_id, cur_name, cur_stars, cur_shards, cur_hp, cur_atk, cur_df, cur_spd, cur_luk = row
            new_shards = cur_shards + 1
            
            self.cur.execute(
                """UPDATE user_cocks 
                   SET shards=? 
                   WHERE id=?""",
                (new_shards, cock_id)
            )
            self.conn.commit()
            return cock_id, True, False, cur_stars, cur_stars, new_shards, {"hp": cur_hp, "atk": cur_atk, "df": cur_df, "spd": cur_spd, "luk": cur_luk}
            
        else:
            self.cur.execute("SELECT count(*) FROM user_cocks WHERE user_id=?", (user_id,))
            count = self.cur.fetchone()[0]
            is_active = 1 if count == 0 else 0

            self.cur.execute(
                """INSERT INTO user_cocks(user_id, name, rarity, hp, atk, df, spd, luk, is_active, stars, shards)
                   VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0)""",
                (user_id, name, rarity, hp, atk, df, spd, luk, is_active),
            )
            self.conn.commit()
            return self.cur.lastrowid, False, False, 0, 0, 0, {"hp": hp, "atk": atk, "df": df, "spd": spd, "luk": luk}

    def get_cocks(self, user_id: int) -> list:
        self.cur.execute("SELECT * FROM user_cocks WHERE user_id=?", (user_id,))
        return self.cur.fetchall()

    def get_cock(self, cock_id: int) -> tuple | None:
        self.cur.execute("SELECT * FROM user_cocks WHERE id=?", (cock_id,))
        return self.cur.fetchone()

    def get_active_cock(self, user_id: int) -> tuple | None:
        self.cur.execute("SELECT * FROM user_cocks WHERE user_id=? AND is_active=1", (user_id,))
        return self.cur.fetchone()

    def set_active_cock(self, user_id: int, cock_id: int) -> None:
        # Check if this cock is already in position 2 or 3
        self.cur.execute("SELECT is_active FROM user_cocks WHERE user_id=? AND id=?", (user_id, cock_id))
        row = self.cur.fetchone()
        if row and row[0] in (2, 3):
            # Clear its old position
            self.cur.execute("UPDATE user_cocks SET is_active=0 WHERE user_id=? AND is_active=?", (user_id, row[0]))
        # Clear the old position 1 (set it to inactive)
        self.cur.execute("UPDATE user_cocks SET is_active=0 WHERE user_id=? AND is_active=1", (user_id,))
        # Set new cock to position 1
        self.cur.execute("UPDATE user_cocks SET is_active=1 WHERE user_id=? AND id=?", (user_id, cock_id))
        self.conn.commit()

    def get_team_cocks(self, user_id: int) -> dict:
        self.cur.execute("SELECT * FROM user_cocks WHERE user_id=? AND is_active IN (1, 2, 3)", (user_id,))
        rows = self.cur.fetchall()
        team = {1: None, 2: None, 3: None}
        for r in rows:
            pos = r[14]  # is_active column index
            if pos in (1, 2, 3):
                team[pos] = r
        return team

    def set_team_position(self, user_id: int, cock_id: int, position: int) -> None:
        if position not in (1, 2, 3):
            return
            
        # 1. Check if the cock is already in the team at some position
        self.cur.execute("SELECT is_active FROM user_cocks WHERE user_id=? AND id=?", (user_id, cock_id))
        row = self.cur.fetchone()
        if not row:
            return  # Cock not owned or doesn't exist
            
        current_pos = row[0]
        
        # 2. Check if another cock is currently in the target position
        self.cur.execute("SELECT id FROM user_cocks WHERE user_id=? AND is_active=?", (user_id, position))
        target_row = self.cur.fetchone()
        
        if current_pos in (1, 2, 3):
            # If already on the team: Swap!
            if target_row:
                # Move the occupant of the target position to the current position
                self.cur.execute("UPDATE user_cocks SET is_active=? WHERE id=?", (current_pos, target_row[0]))
            # Move the setting cock to the new target position
            self.cur.execute("UPDATE user_cocks SET is_active=? WHERE id=?", (position, cock_id))
        else:
            # If new to the team:
            if target_row:
                # Displace the occupant (set is_active to 0)
                self.cur.execute("UPDATE user_cocks SET is_active=0 WHERE id=?", (target_row[0],))
            # Set the cock to the target position
            self.cur.execute("UPDATE user_cocks SET is_active=? WHERE id=?", (position, cock_id))
            
        self.conn.commit()

    def remove_from_team(self, user_id: int, position: int) -> None:
        self.cur.execute("UPDATE user_cocks SET is_active=0 WHERE user_id=? AND is_active=?", (user_id, position))
        self.conn.commit()

    def clear_team(self, user_id: int) -> None:
        self.cur.execute("UPDATE user_cocks SET is_active=0 WHERE user_id=? AND is_active IN (1, 2, 3)", (user_id,))
        self.conn.commit()

    def update_cock(self, cock_id: int, **kwargs) -> None:
        if not kwargs:
            return
        fields = ", ".join(f"{k}=?" for k in kwargs.keys())
        params = list(kwargs.values())
        params.append(cock_id)
        self.cur.execute(f"UPDATE user_cocks SET {fields} WHERE id=?", tuple(params))
        self.conn.commit()

    def delete_cock(self, cock_id: int) -> None:
        self.cur.execute("DELETE FROM user_cocks WHERE id=?", (cock_id,))
        self.conn.commit()

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
            
        if updates:
            params.append(user_id)
            query = f"UPDATE user_highlow SET {', '.join(updates)} WHERE user_id=?"
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

    def create_marriage(self, user_one: int, user_two: int, ring_type: str) -> None:
        """Registers a new marriage in the database"""
        import time
        now = int(time.time())
        self.cur.execute(
            "INSERT OR REPLACE INTO user_marry (user_one, user_two, ring_type, love_points, joint_wallet, married_at, last_interact_time, interacts_today) VALUES (?, ?, ?, 0, 0, ?, 0, 0)",
            (user_one, user_two, ring_type, now)
        )
        self.conn.commit()

    def delete_marriage(self, user_one: int, user_two: int) -> None:
        """Deletes a marriage registration"""
        self.cur.execute(
            "DELETE FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        self.conn.commit()

    def add_love_points(self, user_one: int, user_two: int, points: int, current_time: int) -> tuple[int, bool]:
        """Adds love points. Resets daily counter if calendar date changed. Caps at 20 points/day."""
        import time
        self.cur.execute(
            "SELECT love_points, last_interact_time, interacts_today FROM user_marry WHERE user_one = ? AND user_two = ?",
            (user_one, user_two)
        )
        row = self.cur.fetchone()
        if not row:
            return (0, False)
            
        love_points, last_interact_time, interacts_today = row
        
        # Check calendar day reset
        now_struct = time.localtime(current_time)
        last_struct = time.localtime(last_interact_time)
        if now_struct.tm_yday != last_struct.tm_yday or now_struct.tm_year != last_struct.tm_year:
            interacts_today = 0
            
        if interacts_today >= 20:
            return (love_points, False)
            
        points_to_add = min(points, 20 - interacts_today)
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
            
        new_balance = max(0, row[0] + delta)
        self.cur.execute(
            "UPDATE user_marry SET joint_wallet = ? WHERE user_one = ? AND user_two = ?",
            (new_balance, user_one, user_two)
        )
        self.conn.commit()
        return new_balance

    def get_marriage_multiplier(self, user_id: int) -> float:
        """Calculates the wage/work multiplier for a user based on their marriage status and ring type."""
        marriage = self.get_marriage(user_id)
        if not marriage:
            return 1.0
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        love_level = love_points // 100
        
        ring_buffs = {
            "ring_grass": (1.01, 0.002),
            "ring_quartz": (1.02, 0.005),
            "ring_aquamarine": (1.03, 0.005),
            "ring_emerald": (1.04, 0.005),
            "ring_amethyst": (1.05, 0.007),
            "ring_cupid": (1.07, 0.008),
            "ring_citrine": (1.09, 0.010),
            "ring_ruby": (1.12, 0.012),
            "ring_sapphire": (1.15, 0.015),
            "ring_sunburst": (1.20, 0.020),
            "ring_gothic": (1.25, 0.025),
            "ring_angel": (1.30, 0.030),
            "ring_divine": (1.40, 0.040),
        }
        
        if ring_type in ring_buffs:
            base, step = ring_buffs[ring_type]
            return base + (love_level * step)
            
        # Fallback for old/unknown rings
        if ring_type == "ring_silver":
            return 1.02 + (love_level * 0.005)
        elif ring_type == "ring_gold":
            return 1.05 + (love_level * 0.01)
        elif ring_type == "ring_diamond":
            return 1.10 + (love_level * 0.015)
            
        return 1.0

    def get_marriage_ig(self, user_id: int) -> tuple[str, str]:
        """Returns (user_one_ig, user_two_ig) for the marriage entry"""
        self.cur.execute(
            "SELECT user_one_ig, user_two_ig FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        row = self.cur.fetchone()
        if row:
            return (row[0] or "", row[1] or "")
        return ("", "")

    def update_marriage_ig(self, user_id: int, ig_handle: str) -> None:
        """Updates the Instagram handle for the user's marriage entry"""
        self.cur.execute(
            "SELECT user_one, user_two FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        row = self.cur.fetchone()
        if not row:
            return
        user_one, user_two = row
        if user_id == user_one:
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

    def get_marriage_status(self, user_id: int) -> str:
        """Returns the custom relationship status for the marriage entry"""
        self.cur.execute(
            "SELECT status FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        row = self.cur.fetchone()
        if row:
            return row[0] or "Vợ Chồng"
        return "Vợ Chồng"

    def update_marriage_status(self, user_id: int, status_text: str) -> None:
        """Updates the custom relationship status for the user's marriage entry"""
        self.cur.execute(
            "SELECT user_one, user_two FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        row = self.cur.fetchone()
        if not row:
            return
        user_one, user_two = row
        self.cur.execute(
            "UPDATE user_marry SET status = ? WHERE user_one = ? AND user_two = ?",
            (status_text, user_one, user_two)
        )
        self.conn.commit()

    def get_marriage_saying(self, user_id: int) -> str:
        """Returns the custom saying for the marriage entry"""
        self.cur.execute(
            "SELECT saying FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        row = self.cur.fetchone()
        if row:
            return row[0] or ""
        return ""

    def update_marriage_saying(self, user_id: int, saying_text: str) -> None:
        """Updates the custom saying for the user's marriage entry"""
        self.cur.execute(
            "SELECT user_one, user_two FROM user_marry WHERE user_one = ? OR user_two = ?",
            (user_id, user_id)
        )
        row = self.cur.fetchone()
        if not row:
            return
        user_one, user_two = row
        self.cur.execute(
            "UPDATE user_marry SET saying = ? WHERE user_one = ? AND user_two = ?",
            (saying_text, user_one, user_two)
        )
        self.conn.commit()

