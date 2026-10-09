"""Database and shortcut management for Profile Cards."""
import json
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any, Optional

from app.config import config

logger = logging.getLogger(__name__)

DB_PATH = Path(config.storage.database_path)
_db_lock = threading.Lock()

from contextlib import contextmanager

# In-memory shortcuts cache: (str(guild_id), keyword.lower()) -> str(user_id)
_shortcuts: dict[tuple[str, str], str] = {}


@contextmanager
def _get_connection():
    conn = sqlite3.connect(str(DB_PATH), timeout=20.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def init_db() -> None:
    """Initialize profile_cards table in SQLite."""
    with _db_lock, _get_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS profile_cards (
                user_id TEXT NOT NULL,
                guild_id TEXT NOT NULL,
                title TEXT DEFAULT '',
                content TEXT DEFAULT '',
                footer TEXT DEFAULT '',
                images TEXT DEFAULT '[]',
                color INTEGER DEFAULT NULL,
                shorts TEXT DEFAULT '[]',
                font_title TEXT DEFAULT NULL,
                font_content TEXT DEFAULT NULL,
                font_footer TEXT DEFAULT NULL,
                PRIMARY KEY (user_id, guild_id)
            )
            """
        )
        conn.execute(
            "CREATE INDEX IF NOT EXISTS idx_profile_cards_guild ON profile_cards(guild_id)"
        )
        conn.commit()


def load_shortcuts() -> int:
    """Load all shortcuts into memory cache from DB."""
    init_db()
    with _db_lock, _get_connection() as conn:
        cur = conn.execute("SELECT user_id, guild_id, shorts FROM profile_cards")
        rows = cur.fetchall()

    _shortcuts.clear()
    count = 0
    for row in rows:
        uid = str(row["user_id"])
        gid = str(row["guild_id"])
        try:
            shorts_list = json.loads(row["shorts"] or "[]")
        except Exception:
            shorts_list = []
        for kw in shorts_list:
            if kw and isinstance(kw, str):
                _shortcuts[(gid, kw.strip().lower())] = uid
                count += 1

    logger.info("Loaded %d profile shortcuts into memory cache.", count)
    return count


def find_shortcut(keyword: str, guild_id: str | int) -> Optional[str]:
    """Find user_id associated with a shortcut keyword in a guild."""
    return _shortcuts.get((str(guild_id), keyword.strip().lower()))


def is_keyword_taken(keyword: str, guild_id: str | int, exclude_user_id: str | int) -> bool:
    """Check if keyword is already used by someone else in the same guild."""
    existing_uid = _shortcuts.get((str(guild_id), keyword.strip().lower()))
    if not existing_uid:
        return False
    return existing_uid != str(exclude_user_id)


def get_card(user_id: str | int, guild_id: str | int) -> Optional[dict[str, Any]]:
    """Retrieve profile card dictionary for user in guild."""
    init_db()
    uid, gid = str(user_id), str(guild_id)
    with _db_lock, _get_connection() as conn:
        cur = conn.execute(
            "SELECT * FROM profile_cards WHERE user_id = ? AND guild_id = ?",
            (uid, gid),
        )
        row = cur.fetchone()
        if not row:
            return None

        data = dict(row)
        try:
            data["images"] = json.loads(data["images"] or "[]")
        except Exception:
            data["images"] = []
        try:
            data["shorts"] = json.loads(data["shorts"] or "[]")
        except Exception:
            data["shorts"] = []
        return data


def upsert_card(user_id: str | int, guild_id: str | int, **fields) -> dict[str, Any]:
    """Update or insert profile card fields."""
    init_db()
    uid, gid = str(user_id), str(guild_id)
    current = get_card(uid, gid)
    if current is None:
        current = {
            "user_id": uid,
            "guild_id": gid,
            "title": "",
            "content": "",
            "footer": "",
            "images": [],
            "color": None,
            "shorts": [],
            "font_title": None,
            "font_content": None,
            "font_footer": None,
        }

    for k, v in fields.items():
        if k in current:
            current[k] = v

    images_json = json.dumps(current["images"], ensure_ascii=False)
    shorts_json = json.dumps(current["shorts"], ensure_ascii=False)

    with _db_lock, _get_connection() as conn:
        conn.execute(
            """
            INSERT INTO profile_cards (
                user_id, guild_id, title, content, footer, images, color,
                shorts, font_title, font_content, font_footer
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(user_id, guild_id) DO UPDATE SET
                title = excluded.title,
                content = excluded.content,
                footer = excluded.footer,
                images = excluded.images,
                color = excluded.color,
                shorts = excluded.shorts,
                font_title = excluded.font_title,
                font_content = excluded.font_content,
                font_footer = excluded.font_footer
            """,
            (
                uid,
                gid,
                current.get("title", ""),
                current.get("content", ""),
                current.get("footer", ""),
                images_json,
                current.get("color"),
                shorts_json,
                current.get("font_title"),
                current.get("font_content"),
                current.get("font_footer"),
            ),
        )
        conn.commit()

    return current


def add_image(user_id: str | int, guild_id: str | int, filename: str) -> int:
    """Add image filename to card images list. Returns total images."""
    card = get_card(user_id, guild_id) or {
        "images": [],
    }
    images = card.get("images", [])
    images.append(filename)
    upsert_card(user_id, guild_id, images=images)
    return len(images)


def remove_image(user_id: str | int, guild_id: str | int, index: int) -> Optional[str]:
    """Remove image by 1-based index. Returns removed filename if successful."""
    card = get_card(user_id, guild_id)
    if not card:
        return None
    images = card.get("images", [])
    if index < 1 or index > len(images):
        return None

    removed = images.pop(index - 1)
    upsert_card(user_id, guild_id, images=images)
    return removed


def add_shortcut(user_id: str | int, guild_id: str | int, keyword: str) -> None:
    """Add a shortcut keyword for user in guild."""
    uid, gid = str(user_id), str(guild_id)
    kw = keyword.strip().lower()
    card = get_card(uid, gid) or {"shorts": []}
    shorts = card.get("shorts", [])
    if kw not in [s.lower() for s in shorts]:
        shorts.append(kw)
        upsert_card(uid, gid, shorts=shorts)
    _shortcuts[(gid, kw)] = uid


def remove_shortcut(user_id: str | int, guild_id: str | int, keyword: str) -> bool:
    """Remove a shortcut keyword for user in guild."""
    uid, gid = str(user_id), str(guild_id)
    kw = keyword.strip().lower()
    card = get_card(uid, gid)
    if not card:
        return False
    shorts = card.get("shorts", [])
    found = None
    for s in shorts:
        if s.lower() == kw:
            found = s
            break
    if not found:
        return False

    shorts.remove(found)
    upsert_card(uid, gid, shorts=shorts)
    _shortcuts.pop((gid, kw), None)
    return True


def remove_all_shortcuts(user_id: str | int, guild_id: str | int) -> None:
    """Remove all shortcuts for user in guild."""
    uid, gid = str(user_id), str(guild_id)
    card = get_card(uid, gid)
    if not card:
        return
    shorts = card.get("shorts", [])
    for s in shorts:
        _shortcuts.pop((gid, s.lower()), None)
    upsert_card(uid, gid, shorts=[])
