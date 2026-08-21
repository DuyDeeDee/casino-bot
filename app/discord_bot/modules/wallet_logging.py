import json
import logging
import sqlite3
import time
from pathlib import Path
from typing import Any

from discord.ext import commands

from app.config import config

DATABASE_PATH = Path(config.storage.database_path)


def log_wallet_change(
    logger: logging.Logger,
    *,
    event: str,
    user_id: int,
    money_delta: int = 0,
    credits_delta: int = 0,
    ctx: commands.Context | None = None,
    **metadata: Any,
) -> None:
    payload: dict[str, Any] = {
        "event": event,
        "user_id": user_id,
        "money_delta": money_delta,
        "credits_delta": credits_delta,
        "command": ctx.command.qualified_name if ctx and ctx.command else None,
        "guild_id": ctx.guild.id if ctx and ctx.guild else None,
        "channel_id": ctx.channel.id if ctx and ctx.channel else None,
    }
    payload.update(metadata)
    logger.info("wallet_change %s", json.dumps(payload, sort_keys=True))

    try:
        conn = sqlite3.connect(str(DATABASE_PATH), timeout=10)
        cur = conn.cursor()
        cur.execute(
            """CREATE TABLE IF NOT EXISTS wallet_transactions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                event TEXT NOT NULL,
                money_delta INTEGER NOT NULL DEFAULT 0,
                credits_delta INTEGER NOT NULL DEFAULT 0,
                command TEXT,
                details TEXT,
                created_at INTEGER NOT NULL
            )"""
        )
        cur.execute(
            """INSERT INTO wallet_transactions(user_id, event, money_delta, credits_delta, command, details, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                event,
                money_delta,
                credits_delta,
                payload.get("command"),
                json.dumps(metadata, ensure_ascii=False),
                int(time.time()),
            ),
        )
        conn.commit()
        conn.close()
    except Exception:
        pass

