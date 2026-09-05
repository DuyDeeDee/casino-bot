"""Cấp độ thành viên (tăng bằng cách chat) và giới hạn cho/nhận tiền theo cấp.

Mục tiêu: chặn acc giàu bơm quá nhiều tiền cho acc nghèo/acc phụ.
- Mỗi lần chuyển: tối đa min(transfer_cap(cấp người cho), transfer_cap(cấp người nhận)).
- Mỗi ngày: tổng cho ≤ daily_cap(cấp người cho) và tổng nhận ≤ daily_cap(cấp người nhận).
Hạn mức áp dụng cho pay (VND), paygold (thỏi vàng) và nút "Cho tiền" của lệnh beg.
"""

from __future__ import annotations

import json
import random
import time
from datetime import datetime, timedelta, timezone
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from app.discord_bot.modules.economy import Economy

# --- CẤP ĐỘ CHAT ---
MAX_MEMBER_LEVEL: int = 50
CHAT_XP_MIN: int = 10
CHAT_XP_MAX: int = 20
CHAT_XP_COOLDOWN_SECONDS: int = 60

# --- GIỚI HẠN CHO/NHẬN THEO CẤP ---
# Bảng hạn mức theo khung 10 cấp: từ cấp `start` trở lên (đến trước khung kế) dùng `cap`.
# Giá trị khung vừa là hạn mức MỖI LẦN chuyển, vừa là tổng CHO tối đa MỖI NGÀY;
# tổng NHẬN tối đa mỗi ngày = 1.5x giá trị khung.
GIVE_CAP_BANDS: list[tuple[int, int]] = [
    (0, 1_000_000),
    (10, 5_000_000),
    (20, 20_000_000),
    (30, 50_000_000),
    (40, 100_000_000),
]
RECEIVE_CAP_MULTIPLIER: float = 1.5
GIVE_LIMIT_OVERRIDES_KEY = "give_limit_overrides"


def today_key() -> str:
    """Day key 'YYYY-MM-DD' theo giờ Việt Nam (UTC+7), trùng convention daily quests."""
    return datetime.now(timezone(timedelta(hours=7))).strftime("%Y-%m-%d")


def xp_to_next_level(level: int) -> int:
    """XP cần để lên từ `level` lên `level + 1`; 0 khi đã đạt cấp tối đa."""
    if level >= MAX_MEMBER_LEVEL:
        return 0
    return 100 * (level + 1) ** 2


def grant_chat_xp(economy: "Economy", user_id: int) -> tuple[bool, int, int]:
    """Cộng XP chat nếu user đã hết cooldown.

    Trả về (leveled_up, level_mới, xp_mới). Level-up được xử lý tại đây
    (trường hợp XP dư nhiều do đổi công thức cũng được trượt đúng).
    """
    now = time.time()
    level, xp, last_ts = economy.get_member_level(user_id)

    if now - last_ts < CHAT_XP_COOLDOWN_SECONDS:
        return (False, level, xp)

    xp += random.randint(CHAT_XP_MIN, CHAT_XP_MAX)
    leveled_up = False
    while level < MAX_MEMBER_LEVEL:
        need = xp_to_next_level(level)
        if xp < need:
            break
        xp -= need
        level += 1
        leveled_up = True
    if level >= MAX_MEMBER_LEVEL:
        xp = 0

    economy.set_member_level(user_id, level, xp, now)
    return (leveled_up, level, xp)


# --- OVERRIDE HẠN MỨC THEO CẤP (lưu trong system_settings) ---
def _get_overrides(economy: "Economy") -> dict[str, dict[str, int]]:
    raw = economy.get_setting(GIVE_LIMIT_OVERRIDES_KEY, "")
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def _get_override(economy: "Economy", kind: str, level: int) -> Optional[int]:
    bucket = _get_overrides(economy).get(kind, {})
    value = bucket.get(str(level)) if isinstance(bucket, dict) else None
    return int(value) if value is not None else None


def set_override(economy: "Economy", kind: str, level: int, amount: Optional[int]) -> None:
    """Lưu override cho một cấp; amount=None để xoá override (dùng lại công thức)."""
    if kind not in ("transfer", "daily", "transfer_gold", "daily_gold"):
        raise ValueError("kind must be 'transfer', 'daily', 'transfer_gold' or 'daily_gold'")
    data: dict[str, Any] = _get_overrides(economy)
    bucket = data.setdefault(kind, {})
    if amount is None:
        bucket.pop(str(level), None)
    else:
        bucket[str(level)] = int(amount)
    if not bucket:
        data.pop(kind, None)
    economy.set_setting(GIVE_LIMIT_OVERRIDES_KEY, json.dumps(data) if data else "")


def transfer_cap(level: int, economy: Optional["Economy"] = None, currency: str = "money") -> int:
    """Hạn mức tối đa MỖI LẦN chuyển với cấp `level` (tra theo khung 10 cấp)."""
    level = max(0, int(level))
    if currency == "gold":
        if economy is not None:
            override = _get_override(economy, "transfer_gold", level)
            if override is not None:
                return override
        money_cap = transfer_cap(level, economy, "money")
        gold_price = economy.get_gold_price() if economy is not None else 10_000_000
        gold_price = max(1, int(gold_price))
        return max(1, int(round(money_cap / gold_price)))

    if economy is not None:
        override = _get_override(economy, "transfer", level)
        if override is not None:
            return override
    cap = GIVE_CAP_BANDS[0][1]
    for start, value in GIVE_CAP_BANDS:
        if level >= start:
            cap = value
    return cap


def daily_give_cap(level: int, economy: Optional["Economy"] = None, currency: str = "money") -> int:
    """Tổng CHO tối đa MỖI NGÀY với cấp `level`."""
    level = max(0, int(level))
    if currency == "gold":
        if economy is not None:
            override = _get_override(economy, "daily_gold", level)
            if override is not None:
                return override
        return transfer_cap(level, economy, "gold")
    if economy is not None:
        override = _get_override(economy, "daily", level)
        if override is not None:
            return override
    return transfer_cap(level, economy, "money")


def daily_receive_cap(level: int, economy: Optional["Economy"] = None, currency: str = "money") -> int:
    """Tổng NHẬN tối đa MỖI NGÀY với cấp `level` = 1.5x quỹ cho."""
    return max(1, int(round(daily_give_cap(level, economy, currency) * RECEIVE_CAP_MULTIPLIER)))


# --- KIỂM TRA & GHI NHẬN SỬ DỤNG ---
def check_give_limit(
    economy: "Economy",
    sender_id: int,
    receiver_id: int,
    amount: int,
    currency: str = "money",
) -> tuple[bool, Optional[str]]:
    """Kiểm tra hạn mức cho/nhận giữa hai member theo cấp độ.

    Trả về (True, None) nếu hợp lệ, ngược lại (False, thông báo lỗi tiếng Việt).
    currency: "money" (VND) hoặc "gold" (thỏi vàng).
    """
    amount = int(amount)
    if amount <= 0:
        return (False, "❌ **Lỗi:** Số lượng chuyển phải lớn hơn 0.")

    unit = "<:VND:1545815183589511370>" if currency == "money" else "<:GOLD:1545815236035219637>"
    sender_level, _, _ = economy.get_member_level(sender_id)
    receiver_level, _, _ = economy.get_member_level(receiver_id)

    sender_tcap = transfer_cap(sender_level, economy, currency)
    receiver_tcap = transfer_cap(receiver_level, economy, currency)
    max_transfer = min(sender_tcap, receiver_tcap)
    if amount > max_transfer:
        return (
            False,
            (
                f"❌ **Giới hạn theo cấp độ:** Mỗi lần chỉ có thể chuyển tối đa **{max_transfer:,} {unit}**.\n"
                f"> Cấp của bạn: **{sender_level}** (hạn mức {sender_tcap:,} {unit}/lần) — "
                f"Cấp của người nhận: **{receiver_level}** (hạn mức {receiver_tcap:,} {unit}/lần).\n"
                f"> Chat nhiều để tăng cấp và nâng hạn mức! Dùng `i?capdo` để xem tiến độ."
            ),
        )

    sender_scap = daily_give_cap(sender_level, economy, currency)
    receiver_scap = daily_receive_cap(receiver_level, economy, currency)
    day = today_key()
    s_sent, _, s_sent_gold, _ = economy.get_give_daily(sender_id, day)
    _, r_received, _, r_received_gold = economy.get_give_daily(receiver_id, day)
    sender_used = s_sent if currency == "money" else s_sent_gold
    receiver_used = r_received if currency == "money" else r_received_gold

    if sender_used + amount > sender_scap:
        remaining = max(0, sender_scap - sender_used)
        return (
            False,
            (
                f"❌ **Giới hạn theo cấp độ:** Bạn chỉ có thể cho tối đa **{sender_scap:,} {unit}** mỗi ngày (cấp {sender_level}).\n"
                f"> Hôm nay bạn đã cho **{sender_used:,} {unit}**, còn lại **{remaining:,} {unit}**."
            ),
        )

    if receiver_used + amount > receiver_scap:
        remaining = max(0, receiver_scap - receiver_used)
        return (
            False,
            (
                f"❌ **Giới hạn theo cấp độ:** Người nhận chỉ có thể nhận tối đa **{receiver_scap:,} {unit}** mỗi ngày (cấp {receiver_level}).\n"
                f"> Hôm nay người nhận đã nhận **{receiver_used:,} {unit}**, còn lại **{remaining:,} {unit}**.\n"
                f"> Người nhận cần chat nhiều để tăng cấp và nâng hạn mức!"
            ),
        )

    return (True, None)


def record_give(
    economy: "Economy",
    sender_id: int,
    receiver_id: int,
    amount: int,
    currency: str = "money",
) -> None:
    """Ghi nhận một lần chuyển vào quỹ ngày của cả hai bên (gọi sau khi chuyển thành công)."""
    amount = int(amount)
    if amount <= 0:
        return
    day = today_key()
    if currency == "money":
        economy.add_give_daily(sender_id, day, sent_money=amount)
        economy.add_give_daily(receiver_id, day, received_money=amount)
    else:
        economy.add_give_daily(sender_id, day, sent_gold=amount)
        economy.add_give_daily(receiver_id, day, received_gold=amount)


def remaining_daily(economy: "Economy", user_id: int, currency: str = "money") -> dict:
    """Tổng hợp hạn mức hôm nay của một user để hiển thị ở $level."""
    level, xp, _ = economy.get_member_level(user_id)
    day = today_key()
    s_sent, r_received, s_sent_gold, r_received_gold = economy.get_give_daily(user_id, day)
    sent, received = (s_sent, r_received) if currency == "money" else (s_sent_gold, r_received_gold)
    tcap = transfer_cap(level, economy, currency)
    gcap = daily_give_cap(level, economy, currency)
    rcap = daily_receive_cap(level, economy, currency)
    return {
        "level": level,
        "xp": xp,
        "transfer_cap": tcap,
        "give_cap": gcap,
        "receive_cap": rcap,
        "sent": sent,
        "received": received,
        "sent_remaining": max(0, gcap - sent),
        "received_remaining": max(0, rcap - received),
    }
