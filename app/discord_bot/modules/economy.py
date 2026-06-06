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
SCHEMA_VERSION = 6

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


MIGRATIONS: dict[int, Callable[[sqlite3.Cursor], None]] = {
    1: _migration_1_create_economy,
    2: _migration_2_add_indexes,
    3: _migration_3_add_claimed_start,
    4: _migration_4_add_loan_columns,
    5: _migration_5_add_market_table,
    6: _migration_6_add_simulator_tables,
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
        self.conn = sqlite3.connect(str(DATABASE_PATH), timeout=30)
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
        self.cur.execute("UPDATE economy SET money=0, credits=0, loan_amount=0, loan_due=0")
        self.cur.execute("DELETE FROM user_businesses")
        self.cur.execute("DELETE FROM user_portfolio")
        self.cur.execute("DELETE FROM user_inventory")
        self.cur.execute("DELETE FROM user_simulator_stats")
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

    def get_simulator_stats(self, user_id: int) -> tuple[int, int, int, float]:
        self._ensure_entry(user_id)
        self.cur.execute(
            "SELECT last_collect, last_mine, last_rob, fractional_gold FROM user_simulator_stats WHERE user_id=?",
            (user_id,),
        )
        row = self.cur.fetchone()
        if row is None:
            self.cur.execute(
                "INSERT OR IGNORE INTO user_simulator_stats(user_id, last_collect, last_mine, last_rob, fractional_gold) VALUES(?, 0, 0, 0, 0.0)",
                (user_id,),
            )
            self.conn.commit()
            return (0, 0, 0, 0.0)
        return row

    def set_simulator_stats(
        self,
        user_id: int,
        last_collect: int | None = None,
        last_mine: int | None = None,
        last_rob: int | None = None,
        fractional_gold: float | None = None,
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

    def get_stock_prices(self) -> list[tuple[str, int, int, float]]:
        self.cur.execute("SELECT symbol, price, prev_price, change_percent FROM stock_prices")
        return self.cur.fetchall()

    def update_stock_price(self, symbol: str, price: int, prev_price: int, change_percent: float) -> None:
        self.cur.execute(
            "INSERT OR REPLACE INTO stock_prices(symbol, price, prev_price, change_percent) VALUES(?, ?, ?, ?)",
            (symbol, price, prev_price, change_percent),
        )
        self.conn.commit()
