import asyncio
import copy
import difflib
import inspect
import json
import logging
import re
import secrets
import time
from typing import Optional, Union
from urllib.parse import urlparse

import discord
from discord.ext import commands, tasks

from app.discord_bot.modules.economy import Economy

logger = logging.getLogger(__name__)


def parse_role_mention(text: str) -> Optional[int]:
    """Parses role mention or ID to get integer ID."""
    match = re.match(r"<@&?(\d+)>", text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        return int(text)
    return None


def resolve_role_input(guild: Optional[discord.Guild], text: str) -> Optional[int]:
    """Resolves role from mention (<@&123>), digits (123), @RoleName, or RoleName."""
    if not text:
        return None
    text = text.strip()
    
    # 1. Only accept an actual role mention. A user mention (<@123>) must not
    # accidentally become a role requirement.
    match = re.fullmatch(r"<@&(\d+)>", text)
    if match:
        role_id = int(match.group(1))
        if guild is None:
            return role_id
        return role_id if guild.get_role(role_id) is not None else None
    
    # 2. Pure digits
    if text.isdigit():
        role_id = int(text)
        if guild is None:
            return role_id
        return role_id if guild.get_role(role_id) is not None else None
    
    # 3. Role Name lookup in guild
    if guild:
        clean_name = text.lstrip("@").strip().lower()
        for role in guild.roles:
            if role.name.lower() == clean_name:
                return role.id
            if role.name.lower() == text.lower():
                return role.id
    return None


def parse_user_mention(text: str) -> Optional[int]:
    """Parses user mention or ID to get integer ID."""
    match = re.match(r"<@!?(\d+)>", text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        return int(text)
    return None


def parse_channel_mention(text: str) -> Optional[int]:
    """Parses channel mention or ID to get integer ID."""
    match = re.match(r"<#(\d+)>", text)
    if match:
        return int(match.group(1))
    if text.isdigit():
        return int(text)
    return None


def parse_time(time_str: str) -> Optional[int]:
    """Parses a time string like '30m', '1h', '2d' and returns the duration in seconds."""
    match = re.match(r"^(\d+)([smhd])$", time_str.strip().lower())
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    if unit == 's':
        return amount
    elif unit == 'm':
        return amount * 60
    elif unit == 'h':
        return amount * 3600
    elif unit == 'd':
        return amount * 86400
    return None


def parse_color(color_val: Optional[str]) -> Optional[discord.Color]:
    """Parses a color string into a discord.Color object."""
    if not color_val:
        return None
    val = str(color_val).strip().lower()
    color_map = {
        "purple": discord.Color.purple(),
        "tim": discord.Color.purple(),
        "gold": discord.Color.gold(),
        "vang": discord.Color.gold(),
        "red": discord.Color.red(),
        "do": discord.Color.red(),
        "blue": discord.Color.blue(),
        "xanh": discord.Color.blue(),
        "green": discord.Color.green(),
        "xanhla": discord.Color.green(),
        "orange": discord.Color.orange(),
        "cam": discord.Color.orange(),
        "dark": discord.Color.dark_theme(),
        "blurple": discord.Color.blurple(),
        "magenta": discord.Color.magenta(),
        "pink": discord.Color.from_rgb(255, 105, 180),
        "cyan": discord.Color.from_rgb(0, 255, 255),
        "white": discord.Color.from_rgb(255, 255, 255),
        "black": discord.Color(0x010101),
        "den": discord.Color(0x010101),
        "max": discord.Color(0xFFFFFF),
        "max hex": discord.Color(0xFFFFFF),
    }
    if val in color_map:
        return color_map[val]
    clean_hex = val
    while clean_hex.startswith("#") or clean_hex.startswith("0x"):
        if clean_hex.startswith("#"):
            clean_hex = clean_hex[1:]
        elif clean_hex.startswith("0x"):
            clean_hex = clean_hex[2:]

    if len(clean_hex) == 3:
        clean_hex = "".join([c * 2 for c in clean_hex])

    if len(clean_hex) in (6, 8):
        try:
            int_val = int(clean_hex[:6], 16)
            if int_val == 0:
                return discord.Color(0x010101)
            return discord.Color(int_val)
        except ValueError:
            pass
    return None


def is_valid_http_url(value: Optional[str]) -> bool:
    """Returns True for an empty value or an absolute HTTP(S) URL."""
    if not value:
        return True
    try:
        parsed = urlparse(str(value).strip())
        return parsed.scheme.lower() in {"http", "https"} and bool(parsed.netloc)
    except (TypeError, ValueError):
        return False


_secure_rng = secrets.SystemRandom()


def is_giveaway_emoji(emoji: Union[discord.PartialEmoji, discord.Emoji, str]) -> bool:
    """Checks if an emoji matches supported giveaway entry reactions."""
    if isinstance(emoji, str):
        return emoji == "🎉"
    # Raw reaction payloads use PartialEmoji, while Reaction.emoji from a
    # fetched message commonly uses Emoji. discord.Emoji does not implement
    # is_custom_emoji(), so compare IDs directly for both object types.
    emoji_id = getattr(emoji, "id", None)
    if emoji_id is not None:
        return emoji_id in (1544913759297085440, 1526238405061640272)
    return getattr(emoji, "name", "") == "🎉"


def pick_weighted_winners(candidates_dict: dict[int, int], k: int, exclude: Optional[set[int]] = None) -> list[int]:
    """
    Selects k unique winners from candidates_dict {user_id: weight} without replacement.
    Uses secrets.SystemRandom for cryptographic randomness and O(N) memory to prevent OOM.
    """
    if exclude is None:
        exclude = set()
    available = [[uid, max(1, int(weight))] for uid, weight in candidates_dict.items() if uid not in exclude]
    if not available or k <= 0:
        return []

    k = min(k, len(available))
    winners = []

    for _ in range(k):
        total_weight = sum(item[1] for item in available)
        if total_weight <= 0:
            break
        pick = _secure_rng.randrange(total_weight)
        current = 0
        for idx, item in enumerate(available):
            current += item[1]
            if current > pick:
                winners.append(item[0])
                available.pop(idx)
                break
    return winners


AVAILABLE_PLACEHOLDERS = {
    "prize",
    "host",
    "host_id",
    "host_name",
    "winners",
    "winner_count",
    "win",
    "participants",
    "participants_count",
    "ends_at",
    "end",
    "end_time",
    "status",
    "status_note",
    "reroll_history",
    "result",
    "role_req",
    "roles",
    "bonus_roles",
    "prize_bonus",
    "guild_name",
    "server_name"
}

PING_PLACEHOLDERS = {
    "guild_name",
    "server_name",
    "prize",
    "host",
    "host_name",
}

STATE_CONFIG = {
    "active": {
        "label": "Đang chạy",
        "title_key": "active_title",
        "desc_key": "active_desc",
    },
    "ended": {
        "label": "Kết thúc",
        "title_key": "ended_title",
        "desc_key": "ended_desc",
    },
    "cancelled": {
        "label": "Đã hủy",
        "title_key": "cancelled_title",
        "desc_key": "cancelled_desc",
    },
    "rerolled": {
        "label": "Reroll",
        "title_key": "rerolled_title",
        "desc_key": "rerolled_desc",
    },
    "no_participants": {
        "label": "Không có người tham gia",
        "title_key": "no_participants_title",
        "desc_key": "no_participants_desc",
        "message_key": "no_participants_message",
    },
}


def validate_placeholders_strict(
    text: str,
    allowed_placeholders: Optional[set[str]] = None
) -> tuple[bool, Optional[str]]:
    """Checks for unclosed or mismatched curly brackets and validates variable names."""
    if not text:
        return True, None
    depth = 0
    for ch in text:
        if ch == '{':
            if depth > 0:
                return False, "Có dấu '{' lồng nhau hoặc chưa đóng dấu ngoặc trước đó."
            depth += 1
        elif ch == '}':
            if depth == 0:
                return False, "Có dấu '}' thừa mà không có dấu '{' mở trước đó."
            depth -= 1
    if depth != 0:
        return False, "Có dấu '{' chưa được đóng bằng '}'."

    allowed = allowed_placeholders or AVAILABLE_PLACEHOLDERS
    tokens = re.findall(r"\{([^{}]+)\}", text)
    for tok in tokens:
        var_name = tok.strip()
        if var_name not in allowed:
            close = difflib.get_close_matches(var_name, list(allowed), n=1, cutoff=0.55)
            if close:
                return False, f"Không hỗ trợ biến '{{{var_name}}}'. Có thể bạn muốn dùng '{{{close[0]}}}'?"
            valid_str = ", ".join(f"{{{p}}}" for p in sorted(allowed))
            return False, f"Không hỗ trợ biến '{{{var_name}}}'. Danh sách biến hỗ trợ: {valid_str}"

    return True, None

validate_placeholders = validate_placeholders_strict


def parse_time_input(value: str, current_ends_at: int) -> tuple[Optional[int], Optional[str]]:
    """
    Parses user input for time adjustment (+30m, -10m) or duration (30m, 2h, 1d).
    Returns (new_timestamp, error_message).
    """
    val = value.strip().lower()
    if not val:
        return None, "Vui lòng nhập khoảng thời gian (VD: +30m, -10m, 2h)."

    now = int(time.time())
    if val.startswith("+"):
        sec = parse_time(val[1:])
        if not sec:
            return None, f"Không thể nhận diện khoảng thời gian '{val}'."
        target_base = max(now, current_ends_at)
        new_time = target_base + sec
    elif val.startswith("-"):
        sec = parse_time(val[1:])
        if not sec:
            return None, f"Không thể nhận diện khoảng thời gian '{val}'."
        new_time = current_ends_at - sec
    else:
        sec = parse_time(val)
        if not sec:
            return None, f"Không thể nhận diện khoảng thời gian '{val}'."
        new_time = now + sec

    if new_time <= now:
        return None, "Thời gian kết thúc mới phải ở tương lai (lớn hơn thời điểm hiện tại)."

    return new_time, None


def parse_role_requirements_strict(guild: Optional[discord.Guild], raw_text: str) -> tuple[list[int], list[str]]:
    """Parses required role inputs and collects line-by-line errors."""
    if not raw_text.strip():
        return [], []
    # Do not split on whitespace: role names such as "@Giveaway Manager"
    # must remain a single token. Use comma, semicolon, or newline separators.
    tokens = [t.strip() for t in re.split(r"[,;\n]+", raw_text.strip()) if t.strip()]
    role_ids = []
    errors = []
    for tok in tokens:
        rid = resolve_role_input(guild, tok)
        if rid is None:
            errors.append(f"Không tìm thấy role '{tok}'.")
        elif rid not in role_ids:
            role_ids.append(rid)
    return role_ids, errors


def parse_bonus_roles_strict(guild: Optional[discord.Guild], raw_text: str) -> tuple[dict[str, int], list[str]]:
    """Parses bonus role inputs (@Role:Tickets) and collects errors."""
    if not raw_text.strip():
        return {}, []
    tokens = [t.strip() for t in re.split(r"[,;\n]+", raw_text.strip()) if t.strip()]
    bonus_dict = {}
    errors = []
    for tok in tokens:
        if ":" in tok:
            parts = tok.split(":", 1)
            role_part = parts[0].strip()
            ticket_part = parts[1].strip().lstrip("+")
            rid = resolve_role_input(guild, role_part)
            if rid is None:
                errors.append(f"Không tìm thấy role '{role_part}'.")
                continue
            if not ticket_part.isdigit() or int(ticket_part) <= 0:
                errors.append(f"Số vé cộng thêm cho '{role_part}' phải là số nguyên dương.")
                continue
            bonus_dict[str(rid)] = int(ticket_part)
        else:
            rid = resolve_role_input(guild, tok)
            if rid is None:
                errors.append(f"Không tìm thấy role '{tok}'.")
            else:
                bonus_dict[str(rid)] = 1
    return bonus_dict, errors


def parse_role_bonus_prizes_strict(guild: Optional[discord.Guild], raw_text: str) -> tuple[dict[str, str], list[str]]:
    """Parses role bonus prizes line by line and collects errors."""
    if not raw_text.strip():
        return {}, []
    parsed_dict = {}
    errors = []
    lines = raw_text.strip().split("\n")
    for idx, line in enumerate(lines, 1):
        line = line.strip()
        if not line:
            continue
        if ":" not in line:
            errors.append(f"Dòng {idx}: Thiếu dấu hai chấm ':' ngăn cách role và quà ('{line}').")
            continue
        parts = line.split(":", 1)
        role_part = parts[0].strip()
        prize_part = parts[1].strip()
        if not prize_part:
            errors.append(f"Dòng {idx}: Chưa nhập nội dung quà cho role '{role_part}'.")
            continue
        rid = resolve_role_input(guild, role_part)
        if rid is None:
            errors.append(f"Dòng {idx}: Không tìm thấy role '{role_part}'.")
            continue
        parsed_dict[str(rid)] = prize_part
    return parsed_dict, errors


# ==============================================================================
# UI MODALS FOR INTERACTIVE GIVEAWAY EDITOR (MIMU STYLE)
# ==============================================================================

class GiveawayBasicInfoModal(discord.ui.Modal, title="🎨 Chỉnh Sửa Nội Dung Chung"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.custom_title = discord.ui.TextInput(
            label="Tiêu đề chung",
            placeholder="VD: 🎉 EVENT ĐẶC BIỆT 🎉 (Dùng khi trạng thái chưa có tiêu đề riêng)",
            default=cfg.get("title", "") or "",
            max_length=256,
            required=False
        )
        self.color_input = discord.ui.TextInput(
            label="Màu viền Embed (Hex hoặc Tên màu)",
            placeholder="VD: #FFD700, gold, purple, red, cyan",
            default=cfg.get("color", "") or "",
            max_length=25,
            required=False
        )
        self.ping_content = discord.ui.TextInput(
            label="Nội dung Ping / Header trên Embed",
            placeholder="VD: @everyone hoặc # 🎁 GIVEAWAY {guild_name}",
            default=cfg.get("ping_content", "") or "",
            max_length=200,
            required=False
        )
        self.custom_desc = discord.ui.TextInput(
            label="Mô tả chung (Placeholders)",
            style=discord.TextStyle.paragraph,
            placeholder="Dùng khi trạng thái chưa có nội dung riêng.\nHỗ trợ: {prize}, {host}, {winners}...",
            default=cfg.get("custom_desc", "") or "",
            max_length=1500,
            required=False
        )

        self.add_item(self.custom_title)
        self.add_item(self.color_input)
        self.add_item(self.ping_content)
        self.add_item(self.custom_desc)

    async def on_submit(self, interaction: discord.Interaction):
        desc_val = self.custom_desc.value.strip() or None
        if desc_val:
            ok, err = validate_placeholders_strict(desc_val)
            if not ok:
                await interaction.response.send_message(f"❌ Lỗi cú pháp placeholder: {err}", ephemeral=True)
                return

        ping_val = self.ping_content.value.strip() or None
        if ping_val:
            ok, err = validate_placeholders_strict(ping_val, PING_PLACEHOLDERS)
            if not ok:
                await interaction.response.send_message(f"❌ Lỗi nội dung Ping/Header: {err}", ephemeral=True)
                return

        color_val = self.color_input.value.strip() or None
        if color_val and parse_color(color_val) is None:
            await interaction.response.send_message(
                "❌ Màu không hợp lệ. Hãy nhập mã Hex như `#FFD700` hoặc tên màu như `gold`, `purple`, `red`.",
                ephemeral=True
            )
            return

        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["title"] = self.custom_title.value.strip() or None
        cfg["color"] = color_val
        cfg["ping_content"] = ping_val
        cfg["custom_desc"] = desc_val

        self.editor_view.draft['embed_config'] = cfg
        self.editor_view.mark_dirty("basic")
        await self.editor_view.refresh_preview(interaction)


class GiveawayAuthorModal(discord.ui.Modal, title="👤 Chỉnh Sửa Người Tổ Chức (Author)"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.author_name = discord.ui.TextInput(
            label="Tên Author",
            placeholder="VD: 👑 Host: {host_name} (để trống để ẩn)",
            default=cfg.get("author_name", "") or "",
            max_length=100,
            required=False
        )
        self.author_icon = discord.ui.TextInput(
            label="Author Icon URL",
            placeholder="Link ảnh hoặc {host_avatar}",
            default=cfg.get("author_icon", "") or "",
            max_length=400,
            required=False
        )
        self.author_url = discord.ui.TextInput(
            label="Author URL (Link khi bấm)",
            placeholder="https://...",
            default=cfg.get("author_url", "") or "",
            max_length=400,
            required=False
        )

        self.add_item(self.author_name)
        self.add_item(self.author_icon)
        self.add_item(self.author_url)

    async def on_submit(self, interaction: discord.Interaction):
        author_icon = self.author_icon.value.strip() or None
        author_url = self.author_url.value.strip() or None
        if author_icon and author_icon != "{host_avatar}" and not is_valid_http_url(author_icon):
            await interaction.response.send_message(
                "❌ Author Icon phải là URL `http(s)://...` hoặc `{host_avatar}`.",
                ephemeral=True
            )
            return
        if author_url and not is_valid_http_url(author_url):
            await interaction.response.send_message("❌ Author URL phải là URL `http(s)://...` hợp lệ.", ephemeral=True)
            return

        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["author_name"] = self.author_name.value.strip() or None
        cfg["author_icon"] = author_icon
        cfg["author_url"] = author_url

        self.editor_view.draft['embed_config'] = cfg
        self.editor_view.mark_dirty("author")
        await self.editor_view.refresh_preview(interaction)


class GiveawayFooterModal(discord.ui.Modal, title="📄 Chỉnh Sửa Chân Trang (Footer)"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.footer_text = discord.ui.TextInput(
            label="Chân trang (Footer Text)",
            placeholder="VD: Sylus Meow • Giveaway System",
            default=cfg.get("footer_text", "") or "",
            max_length=150,
            required=False
        )
        self.footer_icon = discord.ui.TextInput(
            label="Footer Icon URL",
            placeholder="Link icon nhỏ góc footer",
            default=cfg.get("footer_icon", "") or "",
            max_length=400,
            required=False
        )

        self.add_item(self.footer_text)
        self.add_item(self.footer_icon)

    async def on_submit(self, interaction: discord.Interaction):
        footer_icon = self.footer_icon.value.strip() or None
        if footer_icon and not is_valid_http_url(footer_icon):
            await interaction.response.send_message("❌ Footer Icon phải là URL `http(s)://...` hợp lệ.", ephemeral=True)
            return

        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["footer_text"] = self.footer_text.value.strip() or None
        cfg["footer_icon"] = footer_icon

        self.editor_view.draft['embed_config'] = cfg
        self.editor_view.mark_dirty("footer")
        await self.editor_view.refresh_preview(interaction)


class GiveawayImagesModal(discord.ui.Modal, title="🖼️ Chỉnh Sửa Banner & Thumbnail"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.banner_url = discord.ui.TextInput(
            label="Banner Image URL (Ảnh lớn thân embed)",
            placeholder="Link ảnh https://... (để trống để xóa)",
            default=cfg.get("banner", "") or "",
            max_length=500,
            required=False
        )
        self.thumbnail_url = discord.ui.TextInput(
            label="Thumbnail URL (Ảnh nhỏ góc phải)",
            placeholder="host (mặc định), server, none, hoặc link ảnh",
            default=cfg.get("thumbnail", "host") or "host",
            max_length=500,
            required=False
        )

        self.add_item(self.banner_url)
        self.add_item(self.thumbnail_url)

    async def on_submit(self, interaction: discord.Interaction):
        banner = self.banner_url.value.strip() or None
        thumbnail_raw = self.thumbnail_url.value.strip() or "host"
        thumbnail = thumbnail_raw.lower() if thumbnail_raw.lower() in {"host", "server", "none"} else thumbnail_raw
        if banner and not is_valid_http_url(banner):
            await interaction.response.send_message("❌ Banner phải là URL `http(s)://...` hợp lệ.", ephemeral=True)
            return
        if thumbnail not in {"host", "server", "none"} and not is_valid_http_url(thumbnail):
            await interaction.response.send_message(
                "❌ Thumbnail phải là `host`, `server`, `none` hoặc URL `http(s)://...` hợp lệ.",
                ephemeral=True
            )
            return

        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["banner"] = banner
        cfg["thumbnail"] = thumbnail

        self.editor_view.draft['embed_config'] = cfg
        self.editor_view.mark_dirty("images")
        await self.editor_view.refresh_preview(interaction)


class GiveawayPrizeTimeModal(discord.ui.Modal, title="🎁 Giải Thưởng & Thời Gian"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        ga = self.editor_view.draft

        self.prize_input = discord.ui.TextInput(
            label="Tên Phần Thưởng",
            placeholder="Nhập giải thưởng mới...",
            default=str(ga.get("prize", "")),
            max_length=256,
            required=True
        )
        self.winner_count_input = discord.ui.TextInput(
            label="Số Người Thắng (1 - 100)",
            placeholder="VD: 1, 2, 3...",
            default=str(ga.get("winner_count", 1)),
            max_length=5,
            required=True
        )
        self.time_adjust_input = discord.ui.TextInput(
            label="Điều Chỉnh Thời Gian",
            placeholder="VD: +30m, +1h, -10m hoặc 2h (đặt lại), để trống nếu giữ nguyên",
            default="",
            max_length=20,
            required=False
        )

        self.add_item(self.prize_input)
        self.add_item(self.winner_count_input)
        self.add_item(self.time_adjust_input)

    async def on_submit(self, interaction: discord.Interaction):
        prize_val = self.prize_input.value.strip()
        if not prize_val:
            await interaction.response.send_message("❌ Tên phần thưởng không được để trống.", ephemeral=True)
            return

        try:
            win_count = int(self.winner_count_input.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Số người thắng phải là số nguyên hợp lệ.", ephemeral=True)
            return

        if not (1 <= win_count <= 100):
            await interaction.response.send_message("❌ Số người thắng phải nằm trong khoảng từ 1 đến 100.", ephemeral=True)
            return

        time_adj = self.time_adjust_input.value.strip()
        new_ends = None
        if time_adj:
            new_ends, err_time = parse_time_input(time_adj, self.editor_view.draft.get('ends_at', int(time.time())))
            if err_time:
                await interaction.response.send_message(f"❌ Lỗi điều chỉnh thời gian: {err_time}", ephemeral=True)
                return

        self.editor_view.draft['prize'] = prize_val
        self.editor_view.draft['winner_count'] = win_count
        if new_ends is not None:
            self.editor_view.draft['ends_at'] = new_ends

        self.editor_view.mark_dirty("prize_time")
        await self.editor_view.refresh_preview(interaction)


class GiveawayRequirementsModal(discord.ui.Modal, title="🔒 Cài Đặt Điều Kiện & Role"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        ga = self.editor_view.draft
        guild = self.editor_view.guild

        req_roles = ga.get("required_roles") or []
        if isinstance(req_roles, str):
            try:
                req_roles = json.loads(req_roles)
            except Exception:
                req_roles = []

        req_names = []
        for r in req_roles:
            r_str = str(r)
            if guild and r_str.isdigit():
                role_obj = guild.get_role(int(r_str))
                if role_obj:
                    req_names.append(f"@{role_obj.name}")
                    continue
            req_names.append(r_str)
        req_str = ", ".join(req_names)

        bonus_roles = ga.get("bonus_roles") or {}
        if isinstance(bonus_roles, str):
            try:
                bonus_roles = json.loads(bonus_roles)
            except Exception:
                bonus_roles = {}

        bonus_names = []
        for r, extra in bonus_roles.items():
            r_str = str(r)
            if guild and r_str.isdigit():
                role_obj = guild.get_role(int(r_str))
                if role_obj:
                    bonus_names.append(f"@{role_obj.name}:{extra}")
                    continue
            bonus_names.append(f"{r}:{extra}")
        bonus_str = ", ".join(bonus_names)

        self.required_roles_input = discord.ui.TextInput(
            label="Role Bắt Buộc (@Role hoặc Role ID)",
            placeholder="VD: @Member, @VIP Member hoặc 123456789 (cách nhau bằng dấu phẩy)",
            default=req_str,
            max_length=300,
            required=False
        )
        self.bonus_roles_input = discord.ui.TextInput(
            label="Role Cộng Vé Bonus (Role:Vé)",
            placeholder="VD: @Booster:2, @VIP:3 hoặc 123456789:2",
            default=bonus_str,
            max_length=300,
            required=False
        )

        self.add_item(self.required_roles_input)
        self.add_item(self.bonus_roles_input)

    async def on_submit(self, interaction: discord.Interaction):
        req_list, req_errs = parse_role_requirements_strict(interaction.guild, self.required_roles_input.value)
        bonus_dict, bonus_errs = parse_bonus_roles_strict(interaction.guild, self.bonus_roles_input.value)
        all_errs = req_errs + bonus_errs
        if all_errs:
            err_msg = "❌ Không thể lưu điều kiện Role:\n" + "\n".join(f"• {e}" for e in all_errs)
            await interaction.response.send_message(err_msg, ephemeral=True)
            return

        if req_list and bonus_dict:
            await interaction.response.send_message(
                "❌ Bạn không thể cấu hình giới hạn role và cộng lượt cùng lúc trong một giveaway!",
                ephemeral=True
            )
            return

        self.editor_view.draft['required_roles'] = req_list
        self.editor_view.draft['bonus_roles'] = bonus_dict
        self.editor_view.mark_dirty("requirements")
        await self.editor_view.refresh_preview(interaction)


class GiveawayPrizeBonusModal(discord.ui.Modal, title="🎁 Đặc Quyền Bonus Phần Thưởng"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        ga = self.editor_view.draft
        guild = self.editor_view.guild

        role_prizes = ga.get("role_bonus_prizes") or {}
        if isinstance(role_prizes, str):
            try:
                role_prizes = json.loads(role_prizes)
            except Exception:
                role_prizes = {}

        lines = []
        for rid_str, prize_text in role_prizes.items():
            role_label = rid_str
            if guild and str(rid_str).isdigit():
                role_obj = guild.get_role(int(rid_str))
                if role_obj:
                    role_label = f"@{role_obj.name}"
            lines.append(f"{role_label}: {prize_text}")
        default_val = "\n".join(lines)

        self.bonus_prizes_input = discord.ui.TextInput(
            label="Bonus Phần Thưởng Cho Role (@Role: Quà)",
            style=discord.TextStyle.paragraph,
            placeholder="Mỗi dòng một role:\n@Booster: +50k Momo\n@VIP: +1 Skin Hiếm",
            default=default_val,
            max_length=1000,
            required=False
        )
        self.add_item(self.bonus_prizes_input)

    async def on_submit(self, interaction: discord.Interaction):
        parsed_dict, errs = parse_role_bonus_prizes_strict(interaction.guild, self.bonus_prizes_input.value)
        if errs:
            err_msg = "❌ Không thể lưu quà bonus theo role:\n" + "\n".join(f"• {e}" for e in errs)
            await interaction.response.send_message(err_msg, ephemeral=True)
            return

        self.editor_view.draft['role_bonus_prizes'] = parsed_dict
        self.editor_view.mark_dirty("prize_bonus")
        await self.editor_view.refresh_preview(interaction)


class GiveawayBonusTicketsModal(discord.ui.Modal):
    def __init__(self, manager_view: "GiveawayRequirementsView", role: discord.Role):
        self.manager_view = manager_view
        self.role = role
        super().__init__(title=f"🎟️ Vé bonus: {role.name[:30]}")
        current = manager_view.bonus_roles.get(str(role.id), 1)
        self.ticket_count = discord.ui.TextInput(
            label="Số vé cộng thêm (0 để xóa)",
            placeholder="Từ 1 đến 50",
            default=str(current),
            min_length=1,
            max_length=2,
            required=True
        )
        self.add_item(self.ticket_count)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            count = int(self.ticket_count.value.strip())
        except ValueError:
            await interaction.response.send_message("❌ Số vé phải là số nguyên từ 0 đến 50.", ephemeral=True)
            return
        if not 0 <= count <= 50:
            await interaction.response.send_message("❌ Số vé phải nằm trong khoảng từ 0 đến 50.", ephemeral=True)
            return
        role_id = str(self.role.id)
        if count == 0:
            self.manager_view.bonus_roles.pop(role_id, None)
        else:
            self.manager_view.bonus_roles[role_id] = count
        self.manager_view.required_roles = []
        await self.manager_view.refresh(interaction)


class GiveawayRoleModeSelect(discord.ui.Select):
    def __init__(self, mode: str):
        options = [
            discord.SelectOption(
                label="Role bắt buộc",
                value="required",
                emoji="🔒",
                description="Người dùng cần có ít nhất một role đã chọn",
                default=(mode == "required")
            ),
            discord.SelectOption(
                label="Role cộng vé bonus",
                value="bonus",
                emoji="🎟️",
                description="Mỗi role được cộng thêm số vé riêng",
                default=(mode == "bonus")
            ),
        ]
        super().__init__(placeholder="Chọn loại điều kiện role", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.view.mode = self.values[0]
        if self.view.mode == "required":
            self.view.bonus_roles = {}
        else:
            self.view.required_roles = []
        await self.view.refresh(interaction)


class GiveawayManagedRoleSelect(discord.ui.RoleSelect):
    def __init__(self, mode: str):
        is_required = mode == "required"
        super().__init__(
            placeholder=(
                "Chọn toàn bộ role được phép tham gia"
                if is_required else
                "Chọn một role để đặt số vé bonus"
            ),
            min_values=1,
            max_values=25 if is_required else 1,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        if self.view.mode == "required":
            self.view.required_roles = [role.id for role in self.values]
            self.view.bonus_roles = {}
            await self.view.refresh(interaction)
            return
        role = self.values[0]
        await interaction.response.send_modal(GiveawayBonusTicketsModal(self.view, role))


class GiveawayRequirementsView(discord.ui.View):
    """RoleSelect-based editor for mutually exclusive role requirements/bonuses."""
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__(timeout=600)
        self.editor_view = editor_view
        self.user = editor_view.user
        required = editor_view.draft.get("required_roles") or []
        bonus = editor_view.draft.get("bonus_roles") or {}
        if isinstance(required, str):
            try:
                required = json.loads(required)
            except Exception:
                required = []
        if isinstance(bonus, str):
            try:
                bonus = json.loads(bonus)
            except Exception:
                bonus = {}
        self.required_roles = []
        for role_id in required:
            try:
                self.required_roles.append(int(role_id))
            except (TypeError, ValueError):
                continue
        self.bonus_roles = {}
        for role_id, count in bonus.items():
            try:
                parsed_count = int(count)
            except (TypeError, ValueError):
                continue
            if 1 <= parsed_count <= 50:
                self.bonus_roles[str(role_id)] = parsed_count
        self.mode = "bonus" if self.bonus_roles else "required"
        self._build_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Đây không phải bảng điều khiển của bạn.", ephemeral=True)
            return False
        return True

    def _build_components(self):
        self.clear_items()
        self.add_item(GiveawayRoleModeSelect(self.mode))
        self.add_item(GiveawayManagedRoleSelect(self.mode))

        save_button = discord.ui.Button(label="✅ Áp dụng điều kiện", style=discord.ButtonStyle.primary, row=2)
        save_button.callback = self._on_save
        clear_button = discord.ui.Button(label="🧹 Xóa điều kiện", style=discord.ButtonStyle.secondary, row=2)
        clear_button.callback = self._on_clear
        back_button = discord.ui.Button(label="↩️ Quay lại", style=discord.ButtonStyle.secondary, row=2)
        back_button.callback = self._on_back
        self.add_item(save_button)
        self.add_item(clear_button)
        self.add_item(back_button)

    def build_content(self) -> str:
        if self.mode == "required":
            summary = ", ".join(f"<@&{role_id}>" for role_id in self.required_roles) or "Chưa chọn role nào"
            instruction = "Chọn một hoặc nhiều role; lần chọn mới sẽ thay thế danh sách hiện tại."
            title = "🔒 **ROLE BẮT BUỘC THAM GIA**"
        else:
            summary = ", ".join(
                f"<@&{role_id}>: **+{count} vé**"
                for role_id, count in self.bonus_roles.items()
            ) or "Chưa có role bonus"
            instruction = "Chọn từng role để đặt số vé. Nhập `0` trong modal để xóa role đó."
            title = "🎟️ **ROLE CỘNG VÉ BONUS**"
        return (
            f"{title}\n{instruction}\n\n"
            f"**Cấu hình bản nháp:** {summary}\n\n"
            "Hai chế độ loại trừ nhau. Chuyển chế độ sẽ xóa cấu hình của chế độ còn lại trong bản nháp này."
        )

    async def refresh(self, interaction: discord.Interaction):
        self._build_components()
        await interaction.response.edit_message(content=self.build_content(), embed=None, view=self)

    async def _on_save(self, interaction: discord.Interaction):
        self.editor_view.draft["required_roles"] = list(self.required_roles)
        self.editor_view.draft["bonus_roles"] = dict(self.bonus_roles)
        self.editor_view.mark_dirty("requirements")
        await self.editor_view.refresh_preview(interaction)

    async def _on_clear(self, interaction: discord.Interaction):
        self.required_roles = []
        self.bonus_roles = {}
        await self.refresh(interaction)

    async def _on_back(self, interaction: discord.Interaction):
        await self.editor_view.refresh_preview(interaction)


class GiveawayRolePrizeModal(discord.ui.Modal):
    def __init__(self, manager_view: "GiveawayPrizeBonusView", role: discord.Role):
        self.manager_view = manager_view
        self.role = role
        super().__init__(title=f"🎁 Quà cho role: {role.name[:27]}")
        self.prize_text = discord.ui.TextInput(
            label="Nội dung quà (để trống để xóa)",
            style=discord.TextStyle.paragraph,
            placeholder="VD: +50k Momo hoặc +1 Skin hiếm",
            default=manager_view.role_prizes.get(str(role.id), ""),
            max_length=300,
            required=False
        )
        self.add_item(self.prize_text)

    async def on_submit(self, interaction: discord.Interaction):
        role_id = str(self.role.id)
        prize = self.prize_text.value.strip()
        if prize:
            self.manager_view.role_prizes[role_id] = prize
        else:
            self.manager_view.role_prizes.pop(role_id, None)
        await self.manager_view.refresh(interaction)


class GiveawayPrizeRoleSelect(discord.ui.RoleSelect):
    def __init__(self):
        super().__init__(
            placeholder="Chọn một role để thêm, sửa hoặc xóa quà",
            min_values=1,
            max_values=1,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GiveawayRolePrizeModal(self.view, self.values[0]))


class GiveawayPrizeBonusView(discord.ui.View):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__(timeout=600)
        self.editor_view = editor_view
        self.user = editor_view.user
        prizes = editor_view.draft.get("role_bonus_prizes") or {}
        if isinstance(prizes, str):
            try:
                prizes = json.loads(prizes)
            except Exception:
                prizes = {}
        self.role_prizes = {str(role_id): str(prize) for role_id, prize in prizes.items()}
        self._build_components()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message("❌ Đây không phải bảng điều khiển của bạn.", ephemeral=True)
            return False
        return True

    def _build_components(self):
        self.clear_items()
        self.add_item(GiveawayPrizeRoleSelect())
        save_button = discord.ui.Button(label="✅ Áp dụng quà theo role", style=discord.ButtonStyle.primary, row=1)
        save_button.callback = self._on_save
        clear_button = discord.ui.Button(label="🧹 Xóa tất cả", style=discord.ButtonStyle.secondary, row=1)
        clear_button.callback = self._on_clear
        back_button = discord.ui.Button(label="↩️ Quay lại", style=discord.ButtonStyle.secondary, row=1)
        back_button.callback = self._on_back
        self.add_item(save_button)
        self.add_item(clear_button)
        self.add_item(back_button)

    def build_content(self) -> str:
        summary = "\n".join(
            f"• <@&{role_id}>: {prize}"
            for role_id, prize in self.role_prizes.items()
        ) or "Chưa cấu hình quà thêm cho role nào."
        return (
            "🎁 **QUÀ THÊM THEO ROLE**\n"
            "Chọn một role để thêm hoặc sửa quà. Để trống nội dung trong modal để xóa role đó.\n\n"
            f"{summary}"
        )

    async def refresh(self, interaction: discord.Interaction):
        self._build_components()
        await interaction.response.edit_message(content=self.build_content(), embed=None, view=self)

    async def _on_save(self, interaction: discord.Interaction):
        self.editor_view.draft["role_bonus_prizes"] = dict(self.role_prizes)
        self.editor_view.mark_dirty("prize_bonus")
        await self.editor_view.refresh_preview(interaction)

    async def _on_clear(self, interaction: discord.Interaction):
        self.role_prizes = {}
        await self.refresh(interaction)

    async def _on_back(self, interaction: discord.Interaction):
        await self.editor_view.refresh_preview(interaction)


class GiveawayStateContentModal(discord.ui.Modal):
    def __init__(self, editor_view: "GiveawayEditorView", state: str = "active"):
        self.editor_view = editor_view
        self.state = state if state in STATE_CONFIG else "active"
        cfg_info = STATE_CONFIG.get(self.state, STATE_CONFIG["active"])
        self.label = cfg_info["label"]
        self.title_key = cfg_info["title_key"]
        self.desc_key = cfg_info["desc_key"]
        self.message_key = cfg_info.get("message_key")

        super().__init__(title=f"✏️ Sửa Trạng Thái: {self.label}")

        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.state_title = discord.ui.TextInput(
            label=f"Tiêu Đề Riêng [{self.label}]",
            placeholder="Để trống để dùng tiêu đề chung...",
            default=cfg.get(self.title_key, "") or "",
            max_length=256,
            required=False
        )
        self.state_desc = discord.ui.TextInput(
            label=f"Mô Tả Riêng [{self.label}] (Placeholders)",
            style=discord.TextStyle.paragraph,
            placeholder="Hỗ trợ: {prize}, {host}, {winners}, {ends_at}, {result}... Để trống dùng mô tả chung.",
            default=cfg.get(self.desc_key, "") or "",
            max_length=3500,
            required=False
        )

        self.add_item(self.state_title)
        self.add_item(self.state_desc)
        self.channel_message = None
        if self.message_key:
            self.channel_message = discord.ui.TextInput(
                label="Tin Nhắn Gửi Thêm Vào Kênh",
                style=discord.TextStyle.paragraph,
                placeholder="VD: Không có ai tham gia **{prize}**. Để trống dùng mặc định; nhập none để tắt.",
                default=cfg.get(self.message_key, "") or "",
                max_length=1000,
                required=False
            )
            self.add_item(self.channel_message)

    async def on_submit(self, interaction: discord.Interaction):
        new_title = self.state_title.value.strip() or None
        new_desc = self.state_desc.value.strip() or None
        new_channel_message = self.channel_message.value.strip() or None if self.channel_message else None

        # 1. Validation: check placeholder bracket syntax & supported variables
        if new_desc:
            is_valid, err = validate_placeholders_strict(new_desc)
            if not is_valid:
                await interaction.response.send_message(f"❌ Lỗi cú pháp placeholder: {err}", ephemeral=True)
                return
        if new_channel_message and new_channel_message.lower() != "none":
            is_valid, err = validate_placeholders_strict(new_channel_message, PING_PLACEHOLDERS)
            if not is_valid:
                await interaction.response.send_message(f"❌ Lỗi tin nhắn gửi vào kênh: {err}", ephemeral=True)
                return

        # 2. Validation: render trial embed to verify Discord length limitations
        cfg = self.editor_view.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        trial_cfg = dict(cfg)
        trial_cfg[self.title_key] = new_title
        trial_cfg[self.desc_key] = new_desc
        if self.message_key:
            trial_cfg[self.message_key] = new_channel_message

        trial_ga = dict(self.editor_view.draft)
        trial_ga['embed_config'] = trial_cfg

        trial_embed = self.editor_view.cog.build_giveaway_embed(
            trial_ga,
            status=self.state,
            participants_count=10,
            winners=[interaction.user.id],
            status_note="Ghi chú mẫu kiểm tra độ dài."
        )

        if len(trial_embed.description or "") > 4096:
            await interaction.response.send_message(
                f"❌ Nội dung mô tả sau khi áp dụng ({len(trial_embed.description)} ký tự) vượt quá giới hạn 4096 ký tự của Discord!",
                ephemeral=True
            )
            return

        if len(trial_embed) > 6000:
            await interaction.response.send_message(
                f"❌ Tổng độ dài Embed sau khi áp dụng ({len(trial_embed)} ký tự) vượt quá giới hạn 6000 ký tự của Discord!",
                ephemeral=True
            )
            return

        # Save to editor draft state
        cfg[self.title_key] = new_title
        cfg[self.desc_key] = new_desc
        if self.message_key:
            cfg[self.message_key] = new_channel_message
        self.editor_view.draft['embed_config'] = cfg
        self.editor_view.mark_dirty(f"state_{self.state}")
        await self.editor_view.refresh_preview(interaction)


GiveawayStateConfigModal = GiveawayStateContentModal


class GiveawayEditSectionSelect(discord.ui.Select):
    def __init__(self, is_template: bool = False):
        options = [
            discord.SelectOption(
                label="Nội dung chung",
                value="basic",
                emoji="🎨",
                description="Tiêu đề chung, màu viền, ping header, mô tả chung"
            ),
            discord.SelectOption(
                label="Giải thưởng & thời gian",
                value="prize_time",
                emoji="🎁",
                description="Tên giải thưởng, số người thắng, điều chỉnh thời gian"
            ),
            discord.SelectOption(
                label="Banner & Thumbnail",
                value="images",
                emoji="🖼️",
                description="Link ảnh banner lớn và icon thumbnail nhỏ"
            ),
            discord.SelectOption(
                label="Người tổ chức (Author)",
                value="author",
                emoji="👤",
                description="Tên tác giả và avatar hiển thị trên đầu embed"
            ),
            discord.SelectOption(
                label="Chân trang (Footer)",
                value="footer",
                emoji="📄",
                description="Văn bản và icon ở chân trang embed"
            ),
            discord.SelectOption(
                label="Điều kiện & Role bắt buộc",
                value="requirements",
                emoji="🔒",
                description="Role bắt buộc tham gia và role cộng vé bonus"
            ),
            discord.SelectOption(
                label="Quà thêm theo role",
                value="prize_bonus",
                emoji="🎁",
                description="Phần thưởng phụ kèm theo cho từng role cụ thể"
            ),
        ]
        if is_template:
            # Server templates currently persist embed_config only. Do not offer
            # prize/time/role controls whose values would be silently discarded.
            template_sections = {"basic", "images", "author", "footer"}
            options = [option for option in options if option.value in template_sections]
        super().__init__(
            placeholder="👉 Bạn muốn chỉnh sửa phần nào? (Chọn menu bên dưới)",
            min_values=1,
            max_values=1,
            options=options,
            row=0
        )

    async def callback(self, interaction: discord.Interaction):
        choice = self.values[0]
        if choice == "basic":
            await interaction.response.send_modal(GiveawayBasicInfoModal(self.view))
        elif choice == "prize_time":
            await interaction.response.send_modal(GiveawayPrizeTimeModal(self.view))
        elif choice == "images":
            await interaction.response.send_modal(GiveawayImagesModal(self.view))
        elif choice == "author":
            await interaction.response.send_modal(GiveawayAuthorModal(self.view))
        elif choice == "footer":
            await interaction.response.send_modal(GiveawayFooterModal(self.view))
        elif choice == "requirements":
            manager = GiveawayRequirementsView(self.view)
            await interaction.response.edit_message(content=manager.build_content(), embed=None, view=manager)
        elif choice == "prize_bonus":
            manager = GiveawayPrizeBonusView(self.view)
            await interaction.response.edit_message(content=manager.build_content(), embed=None, view=manager)


class GiveawayPreviewStateSelect(discord.ui.Select):
    def __init__(self, current_mode: str = "active"):
        options = [
            discord.SelectOption(
                label="Giveaway đang chạy",
                value="active",
                emoji="🟢",
                default=(current_mode == "active"),
                description="Xem trước giao diện khi sự kiện đang mở nhận vé"
            ),
            discord.SelectOption(
                label="Giveaway đã kết thúc",
                value="ended",
                emoji="🏁",
                default=(current_mode == "ended"),
                description="Xem trước giao diện khi đã bốc thăm và có người thắng"
            ),
            discord.SelectOption(
                label="Giveaway đã bị hủy",
                value="cancelled",
                emoji="🛑",
                default=(current_mode == "cancelled"),
                description="Xem trước giao diện khi sự kiện bị hủy bỏ"
            ),
            discord.SelectOption(
                label="Giveaway đã reroll",
                value="rerolled",
                emoji="🔄",
                default=(current_mode == "rerolled"),
                description="Xem trước giao diện khi quay lại kết quả tìm người thắng mới"
            ),
            discord.SelectOption(
                label="Không có người tham gia",
                value="no_participants",
                emoji="👻",
                default=(current_mode == "no_participants"),
                description="Xem trước khi giveaway kết thúc mà không có ứng viên hợp lệ"
            ),
        ]
        super().__init__(
            placeholder="👁️ Xem trước giao diện theo trạng thái...",
            min_values=1,
            max_values=1,
            options=options,
            row=1
        )

    async def callback(self, interaction: discord.Interaction):
        self.view.preview_mode = self.values[0]
        await self.view.refresh_preview(interaction)


class GiveawayTemplateConfirmView(discord.ui.View):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__(timeout=60)
        self.editor_view = editor_view
        confirm = discord.ui.Button(
            label="⚠️ Xác nhận ghi đè mẫu server",
            style=discord.ButtonStyle.danger,
            row=0
        )
        confirm.callback = self._on_confirm
        cancel = discord.ui.Button(label="↩️ Quay lại", style=discord.ButtonStyle.secondary, row=0)
        cancel.callback = self._on_cancel
        self.add_item(confirm)
        self.add_item(cancel)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.editor_view.user.id:
            await interaction.response.send_message("❌ Đây không phải bảng điều khiển của bạn.", ephemeral=True)
            return False
        return True

    def build_content(self) -> str:
        if self.editor_view.is_template:
            source = "bản nháp đang chỉnh"
        else:
            source = "giao diện của giveaway hiện tại"
        return (
            "⚠️ **XÁC NHẬN GHI ĐÈ MẪU GIAO DIỆN SERVER**\n"
            f"Bạn sắp dùng **{source}** làm mẫu mặc định mới.\n\n"
            "• Tất cả giveaway tạo sau khi lưu sẽ dùng mẫu này.\n"
            "• Giveaway đang chạy và giveaway đã kết thúc không tự thay đổi.\n"
            "• Mẫu server hiện tại sẽ bị thay thế."
        )

    async def _on_confirm(self, interaction: discord.Interaction):
        await self.editor_view._save_default_confirmed(interaction)

    async def _on_cancel(self, interaction: discord.Interaction):
        await self.editor_view.refresh_preview(interaction)

    async def on_timeout(self):
        if not self.editor_view.message:
            return
        try:
            await self.editor_view.message.edit(
                content=self.editor_view.build_editor_content(),
                embed=self.editor_view.build_preview_embed(),
                view=self.editor_view
            )
        except discord.HTTPException:
            pass


# ==============================================================================
# INTERACTIVE GIVEAWAY EDITOR VIEW
# ==============================================================================

class GiveawayEditorView(discord.ui.View):
    def __init__(self, cog, giveaway: dict, user: discord.Member, guild: discord.Guild):
        super().__init__(timeout=600)
        self.cog = cog
        self.original = copy.deepcopy(giveaway)
        self.draft = copy.deepcopy(giveaway)
        self.dirty_sections = set()
        self.user = user
        self.guild = guild
        self.preview_mode = "active"
        self.loaded_version = giveaway.get('version', 0)
        self.initial_ended = giveaway.get('ended', 0)
        self.is_template = (giveaway.get('id', 0) == 0)
        self.can_save_template = cog.can_manage_server_template(user, guild)
        self.message = None

        self.btn_apply_sync = discord.ui.Button(
            label="✅ Cập nhật giveaway này",
            style=discord.ButtonStyle.primary,
            disabled=(not self.is_dirty),
            row=3
        )
        self.btn_apply_sync.callback = self._on_apply_sync

        self._build_components()

    @property
    def giveaway(self) -> dict:
        return self.draft

    @giveaway.setter
    def giveaway(self, value: dict):
        self.draft = value

    def mark_dirty(self, section: str):
        self.dirty_sections.add(section)

    @property
    def is_dirty(self) -> bool:
        return bool(self.dirty_sections)

    def discard_changes(self):
        self.draft = copy.deepcopy(self.original)
        self.dirty_sections.clear()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.user.id:
            await interaction.response.send_message(
                "❌ Bạn không có quyền thao tác trên bảng điều khiển này.",
                ephemeral=True
            )
            return False
        return True

    def build_preview_embed(self) -> discord.Embed:
        try:
            participants = self.draft.get('participants') or {}
            if isinstance(participants, str):
                participants = json.loads(participants)
            p_count = len(participants) if isinstance(participants, dict) else (len(participants) if isinstance(participants, list) else 0)
        except Exception:
            p_count = 0

        sample_ga = dict(self.draft)
        sample_winners = None
        sample_note = None

        if self.preview_mode == "ended":
            sample_winners = [self.user.id]
        elif self.preview_mode == "cancelled":
            sample_note = "Giveaway này đã bị huỷ bởi Host."
        elif self.preview_mode == "no_participants":
            sample_note = "Không có ai tham gia giveaway này."
        elif self.preview_mode == "rerolled":
            sample_winners = [self.user.id]
            extra_reqs = sample_ga.get('extra_reqs') or {}
            if isinstance(extra_reqs, str):
                try:
                    extra_reqs = json.loads(extra_reqs)
                except Exception:
                    extra_reqs = {}
            extra_reqs = dict(extra_reqs)
            if not extra_reqs.get('reroll_history'):
                extra_reqs['reroll_history'] = [999999999999999999]
            sample_ga['extra_reqs'] = extra_reqs

        return self.cog.build_giveaway_embed(
            sample_ga,
            status=self.preview_mode,
            participants_count=p_count,
            winners=sample_winners,
            status_note=sample_note
        )

    def _build_components(self):
        self.clear_items()
        self.add_item(GiveawayEditSectionSelect(is_template=self.is_template))
        self.add_item(GiveawayPreviewStateSelect(self.preview_mode))
        self._add_row2_items()
        self.configure_actions()

    def _add_row2_items(self):
        state_label = STATE_CONFIG.get(self.preview_mode, {}).get("label", "Đang chạy")
        self.btn_edit_current_state = discord.ui.Button(
            label=f"✏️ Sửa [{state_label}]",
            style=discord.ButtonStyle.primary,
            row=2
        )
        self.btn_edit_current_state.callback = self._on_edit_current_state

        cfg = self.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        state_cfg = STATE_CONFIG.get(self.preview_mode, STATE_CONFIG["active"])
        title_key = state_cfg["title_key"]
        desc_key = state_cfg["desc_key"]
        message_key = state_cfg.get("message_key")
        has_override = bool(
            cfg.get(title_key) or cfg.get(desc_key) or (message_key and cfg.get(message_key))
        )

        self.btn_reset_to_common = discord.ui.Button(
            label=("🔄 Khôi phục mặc định" if message_key else "🔄 Dùng lại nội dung chung"),
            style=discord.ButtonStyle.secondary,
            disabled=(not has_override),
            row=2
        )
        self.btn_reset_to_common.callback = self._on_reset_to_common

        self.btn_placeholder_help = discord.ui.Button(
            label="❔ Hướng dẫn biến",
            style=discord.ButtonStyle.secondary,
            row=2
        )
        self.btn_placeholder_help.callback = self._on_placeholder_help

        self.add_item(self.btn_edit_current_state)
        self.add_item(self.btn_reset_to_common)
        self.add_item(self.btn_placeholder_help)

    def configure_actions(self):
        for c in [item for item in list(self.children) if getattr(item, "row", None) == 3]:
            self.remove_item(c)

        if not self.is_template:
            self.btn_apply_sync = discord.ui.Button(
                label="✅ Cập nhật giveaway này",
                style=discord.ButtonStyle.primary,
                disabled=(not self.is_dirty),
                row=3
            )
            self.btn_apply_sync.callback = self._on_apply_sync
            self.add_item(self.btn_apply_sync)

            self.btn_discard = discord.ui.Button(
                label="↩️ Hủy thay đổi",
                style=discord.ButtonStyle.secondary,
                disabled=(not self.is_dirty),
                row=3
            )
            self.btn_discard.callback = self._on_discard
            self.add_item(self.btn_discard)

            if self.can_save_template:
                self.btn_save_default = discord.ui.Button(
                    label="💾 Lưu thành mẫu server",
                    style=discord.ButtonStyle.secondary,
                    row=3
                )
                self.btn_save_default.callback = self._on_save_default
                self.add_item(self.btn_save_default)
        else:
            self.btn_save_default = discord.ui.Button(
                label="💾 Lưu mẫu cho server",
                style=discord.ButtonStyle.success,
                disabled=(not self.is_dirty),
                row=3
            )
            self.btn_save_default.callback = self._on_save_default
            self.add_item(self.btn_save_default)

            self.btn_discard = discord.ui.Button(
                label="↩️ Hủy thay đổi",
                style=discord.ButtonStyle.secondary,
                disabled=(not self.is_dirty),
                row=3
            )
            self.btn_discard.callback = self._on_discard
            self.add_item(self.btn_discard)

    def build_editor_content(self) -> str:
        """Builds the editor header used for both the initial view and refreshes."""
        cfg = self.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        prize = self.draft.get('prize', 'Chưa đặt')
        winner_count = self.draft.get('winner_count', 1)
        ends_at = self.draft.get('ends_at', int(time.time()))

        preview_state_label = {
            "active": "🟢 Giveaway đang chạy",
            "ended": "🏁 Giveaway đã kết thúc",
            "cancelled": "🛑 Giveaway đã bị hủy",
            "rerolled": "🔄 Giveaway đã reroll",
            "no_participants": "👻 Không có người tham gia"
        }.get(self.preview_mode, "🟢 Giveaway đang chạy")

        state_cfg = STATE_CONFIG.get(self.preview_mode, STATE_CONFIG["active"])
        title_key = state_cfg["title_key"]
        desc_key = state_cfg["desc_key"]
        message_key = state_cfg.get("message_key")
        has_override = bool(
            cfg.get(title_key) or cfg.get(desc_key) or (message_key and cfg.get(message_key))
        )
        override_indicator = "✏️ *Trạng thái này đang có nội dung riêng.*" if has_override else "ℹ️ *Trạng thái này đang dùng nội dung chung.*"

        if self.is_template:
            mode_header = "🎨 **THIẾT KẾ MẪU GIAO DIỆN GIVEAWAY TOÀN SERVER**"
            scope_desc = "*(Chỉ lưu giao diện embed và áp dụng cho Giveaway mới tạo sau khi lưu)*"
        else:
            mode_header = f"🛠️ **BẢNG ĐIỀU KHIỂN GIVEAWAY** (ID: `{self.draft.get('id')}`)"
            scope_desc = f"🎁 **{prize}** · 👥 **{winner_count} người thắng** · ⏰ **Kết thúc <t:{ends_at}:R>**"

        if self.is_dirty:
            section_names = {
                "basic": "nội dung chung",
                "prize_time": "giải thưởng & thời gian",
                "images": "hình ảnh",
                "author": "author",
                "footer": "footer",
                "requirements": "điều kiện role",
                "prize_bonus": "quà bonus",
                "state_active": "giao diện đang chạy",
                "state_ended": "giao diện kết thúc",
                "state_cancelled": "giao diện đã hủy",
                "state_rerolled": "giao diện reroll",
                "state_no_participants": "giao diện không có người tham gia"
            }
            sections_str = ", ".join(section_names.get(s, s) for s in sorted(self.dirty_sections))
            status_line = f"🟡 *Bản nháp có {len(self.dirty_sections)} phần chưa lưu ({sections_str})*"
        else:
            status_line = "🟢 *Dữ liệu đang đồng bộ với bản gốc*"

        preview_disclaimer = "\n*(Dữ liệu người thắng / lý do hủy ở chế độ Preview chỉ là mô phỏng thử nghiệm)*" if self.preview_mode != "active" else ""
        channel_message_preview = ""
        if self.preview_mode == "no_participants":
            message_template = cfg.get("no_participants_message") or "Không có ai tham gia giveaway **{prize}**."
            if str(message_template).strip().lower() == "none":
                channel_message_preview = "\n🔕 Tin nhắn gửi thêm vào kênh: **Đã tắt**"
            else:
                rendered_message = self.cog.format_ping_content(message_template, self.draft, self.guild)
                channel_message_preview = f"\n📣 Tin nhắn gửi thêm: {rendered_message}"

        return (
            f"{mode_header}\n"
            f"👁️ Xem trước: **{preview_state_label}** | {override_indicator}\n"
            f"{status_line}\n"
            f"{scope_desc}\n"
            f"────────────────────────────────────────────"
            f"{preview_disclaimer}"
            f"{channel_message_preview}"
        )

    async def refresh_preview(self, interaction: discord.Interaction):
        self._build_components()
        embed = self.build_preview_embed()
        content = self.build_editor_content()

        if interaction.response.is_done():
            self.message = await interaction.edit_original_response(content=content, embed=embed, view=self)
        else:
            await interaction.response.edit_message(content=content, embed=embed, view=self)
            self.message = interaction.message

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True
        if self.message:
            try:
                await self.message.edit(
                    content="⌛ **Bảng điều khiển đã hết hạn.** Các thay đổi chưa lưu không được áp dụng.",
                    view=self
                )
            except discord.HTTPException:
                pass

    async def _on_edit_current_state(self, interaction: discord.Interaction):
        await interaction.response.send_modal(GiveawayStateContentModal(self, self.preview_mode))

    async def _on_reset_to_common(self, interaction: discord.Interaction):
        cfg = self.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        state_cfg = STATE_CONFIG.get(self.preview_mode, STATE_CONFIG["active"])
        title_key = state_cfg["title_key"]
        desc_key = state_cfg["desc_key"]
        message_key = state_cfg.get("message_key")
        cfg[title_key] = None
        cfg[desc_key] = None
        if message_key:
            cfg[message_key] = None
        self.draft['embed_config'] = cfg
        self.mark_dirty(f"state_{self.preview_mode}")
        await self.refresh_preview(interaction)

    async def _on_placeholder_help(self, interaction: discord.Interaction):
        help_embed = discord.Embed(
            title="❔ Hướng Dẫn Biến (Placeholders) Cho Embed Giveaway",
            color=discord.Color.blue(),
            description=(
                "Bạn có thể sử dụng các biến dưới đây trong **Mô tả chung** hoặc **Mô tả riêng của từng trạng thái**.\n"
                "Khi hiển thị, hệ thống sẽ tự động thay thế bằng dữ liệu thực tế tương ứng."
            )
        )
        help_embed.add_field(
            name="🎁 Thông Tin Cơ Bản",
            value=(
                "• `{prize}`: Tên phần thưởng của Giveaway\n"
                "• `{host}`: Mention người tổ chức (`<@Host>`)\n"
                "• `{host_name}`: Tên hiển thị người tổ chức (text thuần)\n"
                "• `{guild_name}`: Tên server Discord hiện tại"
            ),
            inline=False
        )
        help_embed.add_field(
            name="👥 Kết Quả & Người Thắng",
            value=(
                "• `{winner_count}` hoặc `{win}`: Số lượng người thắng\n"
                "• `{winners}` hoặc `{result}`: Mention người thắng (nếu đang chạy: 'Chưa có', nếu hủy: 'Đã bị huỷ')\n"
                "• `{participants}`: Tổng số người / vé tham gia hợp lệ\n"
                "• `{reroll_history}`: Lịch sử mention những người từng thắng trước khi reroll"
            ),
            inline=False
        )
        help_embed.add_field(
            name="⏰ Thời Gian & Trạng Thái",
            value=(
                "• `{ends_at}` hoặc `{end}`: Thời gian kết thúc dạng đếm ngược (`<t:timestamp:R>`)\n"
                "• `{end_time}`: Thời gian kết thúc dạng ngày giờ đầy đủ (`<t:timestamp:f>`)\n"
                "• `{status}`: Trạng thái hiển thị (Đang diễn ra, Đã kết thúc...)\n"
                "• `{status_note}`: Lý do hủy sự kiện hoặc ghi chú kết thúc"
            ),
            inline=False
        )
        help_embed.add_field(
            name="🔒 Role & Điều Kiện",
            value=(
                "• `{role_req}` hoặc `{roles}`: Danh sách role bắt buộc\n"
                "• `{bonus_roles}`: Danh sách role được cộng thêm vé\n"
                "• `{prize_bonus}`: Danh sách phần thưởng tặng kèm theo role"
            ),
            inline=False
        )
        await interaction.response.send_message(embed=help_embed, ephemeral=True)

    async def _on_discard(self, interaction: discord.Interaction):
        self.discard_changes()
        await self.refresh_preview(interaction)

    async def _on_apply_sync(self, interaction: discord.Interaction):
        msg_id = self.draft.get('id', 0)
        if msg_id == 0:
            await interaction.response.send_message(
                "❌ Bạn đang ở chế độ chỉnh sửa Mẫu Server (không có Giveaway cụ thể nào).",
                ephemeral=True
            )
            return

        prize = self.draft['prize']
        winner_count = self.draft['winner_count']
        ends_at = self.draft['ends_at']
        required_roles = self.draft.get('required_roles', [])
        bonus_roles = self.draft.get('bonus_roles', {})
        embed_config = self.draft.get('embed_config', {})
        role_bonus_prizes = self.draft.get('role_bonus_prizes', {})

        if isinstance(embed_config, str):
            try:
                embed_config = json.loads(embed_config)
            except Exception:
                embed_config = {}

        # Re-fetch latest giveaway state from DB
        fresh = self.cog.get_giveaway(msg_id, guild_id=self.guild.id)
        if not fresh:
            await interaction.response.send_message("❌ Không tìm thấy Giveaway này trong server.", ephemeral=True)
            return
        if fresh['guild_id'] != self.guild.id:
            await interaction.response.send_message("❌ Giveaway thuộc server khác, không thể chỉnh sửa.", ephemeral=True)
            return
        if fresh['ended'] != 0:
            await interaction.response.send_message("❌ Giveaway này đã kết thúc hoặc đã bị hủy trước đó, không thể chỉnh sửa.", ephemeral=True)
            return
        if not self.cog.can_manage_giveaway(interaction.user, fresh):
            await interaction.response.send_message("❌ Bạn không có quyền quản lý để áp dụng thay đổi cho Giveaway này.", ephemeral=True)
            return
        if fresh.get('version', 0) != self.loaded_version:
            await interaction.response.send_message("❌ Một editor khác đã cập nhật phiên bản mới hơn. Vui lòng mở lại bảng điều khiển để lấy dữ liệu mới nhất.", ephemeral=True)
            return
        if ends_at <= int(time.time()):
            await interaction.response.send_message("❌ Thời gian kết thúc phải ở tương lai.", ephemeral=True)
            return

        if required_roles and bonus_roles:
            await interaction.response.send_message("❌ Bạn không thể cấu hình giới hạn role và cộng lượt cùng lúc trong một giveaway!", ephemeral=True)
            return

        success, err = await self.cog.update_and_sync_giveaway(
            message_id=msg_id,
            guild_id=self.guild.id,
            expected_status=0,
            expected_version=self.loaded_version,
            prize=prize,
            winner_count=winner_count,
            ends_at=ends_at,
            required_roles=required_roles,
            bonus_roles=bonus_roles,
            embed_config=embed_config,
            role_bonus_prizes=role_bonus_prizes
        )
        if not success:
            await interaction.response.send_message(f"❌ {err or 'Lỗi khi cập nhật và đồng bộ tin nhắn Giveaway.'}", ephemeral=True)
            return

        # Synchronize original to draft and clear dirty state
        self.original = copy.deepcopy(self.draft)
        self.dirty_sections.clear()

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        embed = self.build_preview_embed()
        await interaction.response.edit_message(
            content=f"✅ **Đã áp dụng và cập nhật thành công tin nhắn Giveaway trên kênh <#{self.draft['channel_id']}>!** *(Không thay đổi Mẫu Mặc Định của Server)*",
            embed=embed,
            view=self
        )
        self.stop()

    async def _on_save_default(self, interaction: discord.Interaction):
        if not self.cog.can_manage_server_template(interaction.user, self.guild):
            await interaction.response.send_message(
                "❌ Bạn không có quyền quản lý Mẫu Giveaway của Server. (Yêu cầu quyền Administrator, Quản lý Server hoặc Role `Giveaway Manager`)",
                ephemeral=True
            )
            return
        confirm_view = GiveawayTemplateConfirmView(self)
        await interaction.response.edit_message(
            content=confirm_view.build_content(),
            embed=self.build_preview_embed(),
            view=confirm_view
        )

    async def _save_default_confirmed(self, interaction: discord.Interaction):
        if not self.cog.can_manage_server_template(interaction.user, self.guild):
            await interaction.response.send_message(
                "❌ Bạn không có quyền quản lý Mẫu Giveaway của Server. (Yêu cầu quyền Administrator, Quản lý Server hoặc Role `Giveaway Manager`)",
                ephemeral=True
            )
            return

        cfg = self.draft.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        save_ok = self.cog.save_template(self.guild.id, "default", cfg, updated_by=interaction.user.id)
        if not save_ok:
            await interaction.response.send_message("❌ Lỗi khi lưu Mẫu Giveaway vào cơ sở dữ liệu.", ephemeral=True)
            return

        if self.is_template:
            self.original = copy.deepcopy(self.draft)
            self.dirty_sections.clear()
            for item in self.children:
                item.disabled = True
            embed = self.build_preview_embed()
            await interaction.response.edit_message(
                content=f"💾 **[ĐÃ LƯU MẪU GIVEAWAY CHO TOÀN SERVER!]**\n\n*(Mẫu thiết kế này sẽ tự động áp dụng cho **tất cả Giveaway mới** được tạo trong server!)*",
                embed=embed,
                view=self
            )
            self.stop()
        else:
            self._build_components()
            await interaction.response.edit_message(
                content=(
                    "💾 **Đã lưu giao diện làm mẫu mặc định cho toàn server.**\n"
                    "Giveaway đang chạy này chưa bị thay đổi.\n\n"
                    f"{self.build_editor_content()}"
                ),
                embed=self.build_preview_embed(),
                view=self
            )


class OpenEditorTriggerView(discord.ui.View):
    """Temporary prompt with an interactive button so prefix commands can open Ephemeral Editor."""
    def __init__(self, cog: "Giveaway", giveaway: dict, author: discord.Member, guild: discord.Guild):
        super().__init__(timeout=60)
        self.cog = cog
        self.giveaway = giveaway
        self.author = author
        self.guild = guild
        if giveaway.get('id', 0) == 0:
            self.open_editor_btn.label = "🎨 Mở Trình Thiết Kế Mẫu Server (Riêng Tư)"

    @discord.ui.button(label="🛠️ Mở Trình Chỉnh Sửa Giveaway (Riêng Tư)", style=discord.ButtonStyle.primary)
    async def open_editor_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.giveaway.get('id', 0) == 0:
            if not self.cog.can_manage_server_template(interaction.user, self.guild):
                await interaction.response.send_message(
                    "❌ Bạn không có quyền quản lý Mẫu Giveaway của Server. (Yêu cầu quyền Administrator, Quản lý Server hoặc Role `Giveaway Manager`)",
                    ephemeral=True
                )
                return
        else:
            if not self.cog.can_manage_giveaway(interaction.user, self.giveaway):
                await interaction.response.send_message(
                    "❌ Bạn không có quyền quản lý để chỉnh sửa Giveaway này. (Yêu cầu quyền Quản lý Server hoặc là Host của Giveaway)",
                    ephemeral=True
                )
                return

        editor_view = GiveawayEditorView(self.cog, self.giveaway, interaction.user, self.guild)
        preview_embed = editor_view.build_preview_embed()
        await interaction.response.send_message(
            content=editor_view.build_editor_content(),
            embed=preview_embed,
            view=editor_view,
            ephemeral=True
        )
        try:
            editor_view.message = await interaction.original_response()
        except Exception:
            pass


# ==============================================================================
# MAIN GIVEAWAY COG
# ==============================================================================

class Giveaway(commands.Cog, name="Giveaway"):
    """Cog for managing Discord server giveaways."""
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None) or Economy()
        self.join_locks = {}
        self.end_locks = {}
        self.pending_embed_updates = {}
        self.update_tasks = {}
        self.init_db()
        try:
            loop = asyncio.get_running_loop()
            if loop and loop.is_running():
                self.giveaway_check_loop.start()
        except RuntimeError:
            # Handles synchronous unit test runner without active event loop
            pass

    def cog_unload(self) -> None:
        try:
            if self.giveaway_check_loop.is_running():
                self.giveaway_check_loop.cancel()
        except Exception:
            pass
        for task in self.update_tasks.values():
            task.cancel()
        self.join_locks.clear()
        self.end_locks.clear()

    def init_db(self):
        """Initializes the SQLite database table for giveaways and templates."""
        try:
            self.economy.cur.execute("""
                CREATE TABLE IF NOT EXISTS giveaways (
                    id INTEGER PRIMARY KEY,
                    guild_id INTEGER NOT NULL,
                    channel_id INTEGER NOT NULL,
                    message_id INTEGER NOT NULL,
                    prize TEXT NOT NULL,
                    host_id INTEGER NOT NULL,
                    winner_count INTEGER NOT NULL DEFAULT 1,
                    ends_at INTEGER NOT NULL,
                    ended INTEGER NOT NULL DEFAULT 0, -- 0 = Active, 1 = Ended, 2 = Cancelled
                    required_roles TEXT,            -- JSON array of role IDs (Private mode)
                    participants TEXT NOT NULL,     -- JSON array of participant user IDs
                    winners TEXT NOT NULL           -- JSON array of winner user IDs
                )
            """)
            self.economy.conn.commit()

            self.economy.cur.execute("PRAGMA table_info(giveaways)")
            columns = [col[1] for col in self.economy.cur.fetchall()]
            if 'bonus_roles' not in columns:
                self.economy.cur.execute("ALTER TABLE giveaways ADD COLUMN bonus_roles TEXT")
            if 'embed_config' not in columns:
                self.economy.cur.execute("ALTER TABLE giveaways ADD COLUMN embed_config TEXT DEFAULT '{}'")
            if 'extra_reqs' not in columns:
                self.economy.cur.execute("ALTER TABLE giveaways ADD COLUMN extra_reqs TEXT DEFAULT '{}'")
            if 'role_bonus_prizes' not in columns:
                self.economy.cur.execute("ALTER TABLE giveaways ADD COLUMN role_bonus_prizes TEXT DEFAULT '{}'")
            if 'updated_at' not in columns:
                self.economy.cur.execute("ALTER TABLE giveaways ADD COLUMN updated_at INTEGER DEFAULT 0")
            if 'version' not in columns:
                self.economy.cur.execute("ALTER TABLE giveaways ADD COLUMN version INTEGER DEFAULT 0")

            # Auto-recover any giveaways stuck in ended = 3 from a prior crash/restart
            self.economy.cur.execute("UPDATE giveaways SET ended = 0 WHERE ended = 3")
            self.economy.conn.commit()

            # Index for fast loop polling on active giveaways
            self.economy.cur.execute("""
                CREATE INDEX IF NOT EXISTS idx_giveaways_active_ends 
                ON giveaways(ends_at) WHERE ended = 0
            """)
            self.economy.conn.commit()

            # Templates table for saving default server preferences permanently
            self.economy.cur.execute("PRAGMA table_info(giveaway_templates)")
            tpl_cols = [col[1] for col in self.economy.cur.fetchall()]
            if tpl_cols and 'user_id' in tpl_cols:
                # Migration: backup old table first
                self.economy.cur.execute("CREATE TABLE IF NOT EXISTS giveaway_templates_old_backup AS SELECT * FROM giveaway_templates")
                # Create v2 table
                self.economy.cur.execute("""
                    CREATE TABLE giveaway_templates_v2 (
                        guild_id INTEGER NOT NULL,
                        template_name TEXT NOT NULL DEFAULT 'default',
                        embed_config TEXT NOT NULL,
                        updated_by INTEGER,
                        updated_at INTEGER NOT NULL,
                        PRIMARY KEY (guild_id, template_name)
                    )
                """)
                # Migrate existing data: priority to user_id = 0, else most recent personal template
                self.economy.cur.execute("SELECT DISTINCT guild_id, template_name FROM giveaway_templates")
                distinct_pairs = self.economy.cur.fetchall()
                now_ts = int(time.time())
                for g_id, t_name in distinct_pairs:
                    self.economy.cur.execute(
                        "SELECT embed_config, user_id FROM giveaway_templates WHERE guild_id = ? AND template_name = ? AND (user_id = 0 OR user_id IS NULL) ORDER BY id DESC LIMIT 1",
                        (g_id, t_name)
                    )
                    row = self.economy.cur.fetchone()
                    if not row:
                        self.economy.cur.execute(
                            "SELECT embed_config, user_id FROM giveaway_templates WHERE guild_id = ? AND template_name = ? ORDER BY id DESC LIMIT 1",
                            (g_id, t_name)
                        )
                        row = self.economy.cur.fetchone()
                    if row:
                        cfg_str, u_by = row[0], row[1]
                        self.economy.cur.execute(
                            "INSERT OR REPLACE INTO giveaway_templates_v2 (guild_id, template_name, embed_config, updated_by, updated_at) VALUES (?, ?, ?, ?, ?)",
                            (g_id, t_name, cfg_str, u_by or 0, now_ts)
                        )
                self.economy.cur.execute("DROP TABLE giveaway_templates")
                self.economy.cur.execute("ALTER TABLE giveaway_templates_v2 RENAME TO giveaway_templates")
                self.economy.conn.commit()
            elif not tpl_cols:
                self.economy.cur.execute("""
                    CREATE TABLE IF NOT EXISTS giveaway_templates (
                        guild_id INTEGER NOT NULL,
                        template_name TEXT NOT NULL DEFAULT 'default',
                        embed_config TEXT NOT NULL,
                        updated_by INTEGER,
                        updated_at INTEGER NOT NULL,
                        PRIMARY KEY (guild_id, template_name)
                    )
                """)
                self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to create/update giveaways table: {e}", exc_info=True)

    def save_template(self, guild_id: int, template_name: str = "default", embed_config: Optional[dict] = None, updated_by: Optional[int] = None, **kwargs) -> bool:
        """Saves a server-wide giveaway embed template.
        Supports both modern signature (guild_id, template_name, embed_config, updated_by)
        and legacy signature (guild_id, user_id, template_name, embed_config) safely.
        """
        try:
            if isinstance(template_name, int) or (template_name is None and isinstance(embed_config, str)):
                # Legacy call: (guild_id, user_id, template_name, embed_config)
                actual_updated_by = template_name
                actual_template_name = str(embed_config or "default")
                actual_cfg = updated_by if isinstance(updated_by, dict) else kwargs.get("embed_config", {})
            else:
                actual_template_name = str(template_name or "default")
                actual_cfg = embed_config or {}
                actual_updated_by = updated_by

            now_ts = int(time.time())
            cfg_json = json.dumps(actual_cfg)
            self.economy.cur.execute(
                """INSERT INTO giveaway_templates (guild_id, template_name, embed_config, updated_by, updated_at)
                   VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT(guild_id, template_name) DO UPDATE SET
                       embed_config = excluded.embed_config,
                       updated_by = excluded.updated_by,
                       updated_at = excluded.updated_at""",
                (guild_id, actual_template_name, cfg_json, actual_updated_by, now_ts)
            )
            self.economy.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save giveaway template: {e}", exc_info=True)
            return False

    def get_template(self, guild_id: int, template_name: str = "default", user_id: Optional[int] = None) -> dict:
        """Gets the server-wide default giveaway embed template."""
        try:
            # If user_id was passed as 2nd positional parameter in legacy calls
            if isinstance(template_name, int):
                actual_name = "default"
            else:
                actual_name = str(template_name or "default")

            self.economy.cur.execute(
                "SELECT embed_config FROM giveaway_templates WHERE guild_id = ? AND template_name = ?",
                (guild_id, actual_name)
            )
            row = self.economy.cur.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to get giveaway template: {e}", exc_info=True)
        return {}

    def save_giveaway(self, msg_id, guild_id, channel_id, prize, host_id, winner_count, ends_at, required_roles, bonus_roles, embed_config=None, extra_reqs=None, role_bonus_prizes=None) -> bool:
        try:
            cfg_json = json.dumps(embed_config) if embed_config else '{}'
            reqs_json = json.dumps(extra_reqs) if extra_reqs else '{}'
            role_prizes_json = json.dumps(role_bonus_prizes) if role_bonus_prizes else '{}'
            self.economy.cur.execute(
                """INSERT INTO giveaways (id, guild_id, channel_id, message_id, prize, host_id, winner_count, ends_at, ended, required_roles, bonus_roles, participants, winners, embed_config, extra_reqs, role_bonus_prizes, updated_at, version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, '{}', '[]', ?, ?, ?, ?, 0)""",
                (msg_id, guild_id, channel_id, msg_id, prize, host_id, winner_count, ends_at, json.dumps(required_roles), json.dumps(bonus_roles), cfg_json, reqs_json, role_prizes_json, int(time.time()))
            )
            self.economy.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to save giveaway: {e}", exc_info=True)
            return False

    def get_giveaway(self, msg_id: int, guild_id: Optional[int] = None):
        try:
            if guild_id is not None:
                self.economy.cur.execute(
                    """SELECT id, guild_id, channel_id, message_id, prize, host_id, winner_count, ends_at, ended, required_roles, bonus_roles, participants, winners, embed_config, extra_reqs, role_bonus_prizes, updated_at, version 
                       FROM giveaways WHERE id = ? AND guild_id = ?""", 
                    (msg_id, guild_id)
                )
            else:
                self.economy.cur.execute(
                    """SELECT id, guild_id, channel_id, message_id, prize, host_id, winner_count, ends_at, ended, required_roles, bonus_roles, participants, winners, embed_config, extra_reqs, role_bonus_prizes, updated_at, version 
                       FROM giveaways WHERE id = ?""", 
                    (msg_id,)
                )
            row = self.economy.cur.fetchone()
            if row:
                return {
                    'id': row[0],
                    'guild_id': row[1],
                    'channel_id': row[2],
                    'message_id': row[3],
                    'prize': row[4],
                    'host_id': row[5],
                    'winner_count': row[6],
                    'ends_at': row[7],
                    'ended': row[8],
                    'required_roles': row[9],
                    'bonus_roles': row[10] or '{}',
                    'participants': row[11],
                    'winners': row[12],
                    'embed_config': row[13] or '{}',
                    'extra_reqs': row[14] or '{}',
                    'role_bonus_prizes': row[15] or '{}',
                    'updated_at': row[16] if len(row) > 16 and row[16] is not None else 0,
                    'version': row[17] if len(row) > 17 and row[17] is not None else 0
                }
        except Exception as e:
            logger.error(f"Failed to get giveaway: {e}", exc_info=True)
        return None

    def update_giveaway_full(self, msg_id: int, prize=None, winner_count=None, ends_at=None, required_roles=None, bonus_roles=None, embed_config=None, extra_reqs=None, role_bonus_prizes=None, winners=None, participants=None, ended=None, expected_version=None) -> bool:
        try:
            fields = []
            params = []
            if prize is not None:
                fields.append("prize = ?")
                params.append(prize)
            if winner_count is not None:
                fields.append("winner_count = ?")
                params.append(winner_count)
            if ends_at is not None:
                fields.append("ends_at = ?")
                params.append(ends_at)
            if ended is not None:
                fields.append("ended = ?")
                params.append(ended)
            if required_roles is not None:
                fields.append("required_roles = ?")
                params.append(json.dumps(required_roles) if not isinstance(required_roles, str) else required_roles)
            if bonus_roles is not None:
                fields.append("bonus_roles = ?")
                params.append(json.dumps(bonus_roles) if not isinstance(bonus_roles, str) else bonus_roles)
            if embed_config is not None:
                fields.append("embed_config = ?")
                params.append(json.dumps(embed_config) if not isinstance(embed_config, str) else embed_config)
            if extra_reqs is not None:
                fields.append("extra_reqs = ?")
                params.append(json.dumps(extra_reqs) if not isinstance(extra_reqs, str) else extra_reqs)
            if role_bonus_prizes is not None:
                fields.append("role_bonus_prizes = ?")
                params.append(json.dumps(role_bonus_prizes) if not isinstance(role_bonus_prizes, str) else role_bonus_prizes)
            if winners is not None:
                fields.append("winners = ?")
                params.append(json.dumps(winners) if not isinstance(winners, str) else winners)
            if participants is not None:
                fields.append("participants = ?")
                params.append(json.dumps(participants) if not isinstance(participants, str) else participants)

            fields.append("updated_at = ?")
            params.append(int(time.time()))
            fields.append("version = COALESCE(version, 0) + 1")

            if fields:
                params.append(msg_id)
                query = f"UPDATE giveaways SET {', '.join(fields)} WHERE id = ?"
                if expected_version is not None:
                    query += " AND version = ?"
                    params.append(expected_version)
                self.economy.cur.execute(query, tuple(params))
                if self.economy.cur.rowcount <= 0:
                    return False
                self.economy.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to update giveaway full: {e}", exc_info=True)
            return False

    def update_participants(self, msg_id: int, participants: dict):
        try:
            self.economy.cur.execute("UPDATE giveaways SET participants = ? WHERE id = ?", (json.dumps(participants), msg_id))
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to update participants: {e}", exc_info=True)

    def update_winners(self, msg_id: int, winners: list):
        try:
            self.economy.cur.execute("UPDATE giveaways SET winners = ? WHERE id = ?", (json.dumps(winners), msg_id))
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to update winners: {e}", exc_info=True)

    def mark_ended(self, msg_id: int, ended: int = 1, winners: Optional[list] = None):
        if winners is None:
            winners = []
        try:
            self.economy.cur.execute("UPDATE giveaways SET ended = ?, winners = ? WHERE id = ?", (ended, json.dumps(winners), msg_id))
            self.economy.conn.commit()
            self.join_locks.pop(msg_id, None)
            self.pending_embed_updates.pop(msg_id, None)
            task = self.update_tasks.pop(msg_id, None)
            if task:
                task.cancel()
        except Exception as e:
            logger.error(f"Failed to mark giveaway as ended: {e}", exc_info=True)

    def can_manage_giveaway(self, user_or_member: discord.User, giveaway: Optional[dict] = None) -> bool:
        """Checks if a user has management permissions (Administrator, Manage Guild, Manage Messages, Bot Owner/Admin, or Giveaway Host)."""
        if not user_or_member:
            return False
        from app.config import config
        # Bot Owner or Bot Admin can manage globally across all guilds
        if user_or_member.id in (getattr(config.bot, "owner_ids", []) or []) or user_or_member.id in (getattr(config.bot, "admin_ids", []) or []):
            return True

        # Guild check: If giveaway has a specific guild_id, make sure the member belongs to that same guild
        if giveaway and giveaway.get('guild_id'):
            user_guild_id = getattr(getattr(user_or_member, "guild", None), "id", None)
            if user_guild_id is not None and user_guild_id != giveaway.get('guild_id'):
                return False

        # Discord Permissions within that guild
        if hasattr(user_or_member, "guild_permissions"):
            perms = user_or_member.guild_permissions
            if perms.administrator or perms.manage_guild or perms.manage_messages:
                return True

        # Giveaway Host (only for the specific giveaway in their guild)
        if giveaway and giveaway.get('id', 0) != 0 and user_or_member.id == giveaway.get('host_id'):
            return True
        return False

    def is_host_or_admin(self, ctx: commands.Context, giveaway: dict) -> bool:
        return self.can_manage_giveaway(ctx.author, giveaway)

    def can_manage_server_template(self, member_or_user: Union[discord.User, discord.Member], guild: Optional[discord.Guild] = None) -> bool:
        """Checks if a user has permission to manage the server-wide giveaway template.
        Allowed: Bot Owner/Admin, Administrator, Manage Server (manage_guild), or 'Giveaway Manager' role.
        Manage Messages or Host status alone is NOT sufficient.
        """
        if not member_or_user:
            return False
        from app.config import config
        # Global Bot Owner / Admin
        if member_or_user.id in (getattr(config.bot, "owner_ids", []) or []) or member_or_user.id in (getattr(config.bot, "admin_ids", []) or []):
            return True

        # Check guild permissions
        if hasattr(member_or_user, "guild_permissions"):
            perms = member_or_user.guild_permissions
            if getattr(perms, "administrator", False) or getattr(perms, "manage_guild", False):
                return True

        # Check for 'Giveaway Manager' role
        if hasattr(member_or_user, "roles"):
            for role in member_or_user.roles:
                rname = getattr(role, "name", "").lower()
                if rname in ("giveaway manager", "giveaway-manager", "giveaway_manager"):
                    return True

        # If guild is provided and member_or_user is NOT already a Member (e.g. User), try to resolve to Member
        if not hasattr(member_or_user, "guild_permissions") and guild and hasattr(guild, "get_member"):
            m = guild.get_member(member_or_user.id)
            if m and m != member_or_user:
                return self.can_manage_server_template(m, guild)

        return False

    def get_env_bonus_roles(self) -> dict[int, int]:
        from app.config import config
        raw = config.bot.giveaway_bonus_roles
        if not raw:
            return {}
        
        bonus_map = {}
        parts = raw.split(",")
        for part in parts:
            part = part.strip()
            if not part:
                continue
            if ":" in part:
                subparts = part.split(":")
                try:
                    r_id = int(subparts[0].strip())
                    extra = int(subparts[1].strip())
                    bonus_map[r_id] = extra
                except ValueError:
                    pass
            else:
                try:
                    r_id = int(part)
                    bonus_map[r_id] = 1
                except ValueError:
                    pass
        return bonus_map

    def set_embed_host_thumbnail(self, embed: discord.Embed, host_id: int):
        host = self.bot.get_user(host_id)
        if not host:
            for guild in self.bot.guilds:
                member = guild.get_member(host_id)
                if member:
                    host = member
                    break
        if host and host.display_avatar:
            embed.set_thumbnail(url=host.display_avatar.url)

    def format_ping_content(self, content: str, giveaway: dict, guild: discord.Guild) -> str:
        """Formats the small, explicitly supported placeholder set for message content."""
        if not content:
            return content
        host_id = giveaway.get('host_id', 0)
        host_user = self.bot.get_user(host_id)
        host_name = str(host_user.name) if host_user and getattr(host_user, "name", None) else str(host_id)
        guild_name = str(getattr(guild, "name", ""))
        replacements = {
            "{guild_name}": guild_name,
            "{server_name}": guild_name,
            "{prize}": str(giveaway.get('prize', '')),
            "{host}": f"<@{host_id}>",
            "{host_name}": host_name,
        }
        formatted = content
        for placeholder, value in replacements.items():
            formatted = formatted.replace(placeholder, value)
        return formatted

    def format_embed_description(
        self,
        template_str: str,
        giveaway: dict,
        participants_count: int,
        status: str = "active",
        winners: Optional[list] = None,
        status_note: Optional[str] = None,
        is_ended: bool = False
    ) -> str:
        if is_ended and status == "active":
            status = "ended"

        prize = giveaway.get('prize', '')
        host_id = giveaway.get('host_id', 0)
        winner_count = giveaway.get('winner_count', 1)
        ends_at = giveaway.get('ends_at', int(time.time()))
        guild_id = giveaway.get('guild_id', 0)
        guild = self.bot.get_guild(guild_id)
        server_name = str(guild.name) if (guild and hasattr(guild, "name") and isinstance(guild.name, str)) else ""

        # Required roles
        req_roles_raw = giveaway.get('required_roles')
        required_roles = json.loads(req_roles_raw) if isinstance(req_roles_raw, str) else (req_roles_raw or [])
        req_str = ", ".join(f"<@&{r_id}>" for r_id in required_roles) if required_roles else "Không có"

        # Bonus tickets
        bonus_roles_raw = giveaway.get('bonus_roles') or {}
        bonus_roles = json.loads(bonus_roles_raw) if isinstance(bonus_roles_raw, str) else (bonus_roles_raw or {})
        bonus_ticket_str = ", ".join(f"<@&{r_id}> (+{extra} vé)" for r_id, extra in bonus_roles.items()) if bonus_roles else "Không có"

        # Role bonus prizes
        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})
        role_prize_str = ", ".join(f"<@&{r_id}>: **{b_text}**" for r_id, b_text in role_prizes.items()) if role_prizes else "Không có"

        if winners:
            winners_mentions = ", ".join(f"<@{w_id}>" for w_id in winners)
        else:
            if status == "active":
                winners_mentions = "Chưa có"
            elif status == "cancelled":
                winners_mentions = "Đã bị huỷ"
            elif status == "no_participants":
                winners_mentions = "Không có người tham gia"
            else:
                winners_mentions = "Không có"

        status_names = {
            "active": "Đang diễn ra",
            "ended": "Đã kết thúc",
            "cancelled": "Đã bị huỷ",
            "rerolled": "Đã quay lại kết quả",
            "no_participants": "Kết thúc — không có người tham gia"
        }
        status_display = status_names.get(status, "Đang diễn ra")

        if status == "cancelled" and not status_note:
            status_note = "Giveaway này đã bị huỷ bởi Host."
        elif status == "no_participants" and not status_note:
            status_note = "Không có ai tham gia giveaway này."

        extra_reqs_raw = giveaway.get('extra_reqs') or {}
        extra_reqs = json.loads(extra_reqs_raw) if isinstance(extra_reqs_raw, str) else (extra_reqs_raw or {})
        reroll_hist = extra_reqs.get('reroll_history', [])
        reroll_hist_str = ", ".join(f"<@{w_id}>" for w_id in reroll_hist) if reroll_hist else "Không có"

        host_user = self.bot.get_user(host_id)
        host_name = str(host_user.name) if (host_user and hasattr(host_user, "name") and isinstance(host_user.name, str)) else str(host_id)

        res = template_str
        res = res.replace("{prize}", str(prize))
        res = res.replace("{host}", f"<@{host_id}>")
        res = res.replace("{host_name}", host_name)
        res = res.replace("{host_id}", str(host_id))
        res = res.replace("{winner_count}", str(winner_count))
        res = res.replace("{win}", str(winner_count))
        res = res.replace("{winners}", winners_mentions)
        res = res.replace("{result}", winners_mentions)
        res = res.replace("{ends_at}", f"<t:{ends_at}:R>")
        res = res.replace("{end}", f"<t:{ends_at}:R>")
        res = res.replace("{end_time}", f"<t:{ends_at}:F>")
        res = res.replace("{role_req}", req_str)
        res = res.replace("{roles}", req_str)
        res = res.replace("{bonus_roles}", bonus_ticket_str)
        res = res.replace("{prize_bonus}", role_prize_str)
        res = res.replace("{server_name}", server_name)
        res = res.replace("{guild_name}", server_name)
        res = res.replace("{participants_count}", str(participants_count))
        res = res.replace("{participants}", str(participants_count))
        res = res.replace("{status}", status_display)
        res = res.replace("{status_note}", str(status_note or ""))
        res = res.replace("{reroll_history}", reroll_hist_str)

        if status_note and "{status_note}" not in template_str:
            prefix = "🛑" if status == "cancelled" else "⚠️"
            res = f"{res}\n\n{prefix} {status_note}"

        return res

    def build_default_description(
        self,
        giveaway: dict,
        status: str = "active",
        participants_count: int = 0,
        winners: Optional[list] = None,
        status_note: Optional[str] = None,
        custom_note: Optional[str] = None
    ) -> str:
        prize = giveaway.get('prize', '')
        host_id = giveaway.get('host_id', 0)
        winner_count = giveaway.get('winner_count', 1)
        ends_at = giveaway.get('ends_at', int(time.time()))

        req_roles_raw = giveaway.get('required_roles')
        required_roles = json.loads(req_roles_raw) if isinstance(req_roles_raw, str) else (req_roles_raw or [])

        bonus_roles_raw = giveaway.get('bonus_roles') or {}
        bonus_roles = json.loads(bonus_roles_raw) if isinstance(bonus_roles_raw, str) else (bonus_roles_raw or {})

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        desc_lines = [
            f"**{prize}**",
            f"<a:timden:1526230943478845450> *host:* <@{host_id}>",
            f"<:ss:1526230022787043348>*Win:* {winner_count}"
        ]

        if required_roles:
            req_lines = ", ".join(f"<@&{r_id}>" for r_id in required_roles)
            desc_lines.append(f"<a:kcden:1526231212887380108> *Giới hạn:* {req_lines}")

        if bonus_roles:
            ticket_lines = [f"<@&{r_id}> (+{extra} vé)" for r_id, extra in bonus_roles.items()]
            desc_lines.append(f"<:ss:1526230022787043348>*Cộng vé:* " + ", ".join(ticket_lines))

        if role_prizes:
            prize_bonus_lines = [f"<@&{r_id}>: **{b_text}**" for r_id, b_text in role_prizes.items()]
            desc_lines.append(f"🎁 *Bonus role:* " + ", ".join(prize_bonus_lines))

        if status == "active":
            desc_lines.append(f"<:ss:1526230022787043348>*End:* <t:{ends_at}:R>")
        elif status in ("ended", "rerolled", "no_participants"):
            if winners:
                winners_mentions = ", ".join(f"<@{w_id}>" for w_id in winners)
                desc_lines.append(f"<a:key:1526234974150459593>*Result:* {winners_mentions}")
            if status == "rerolled":
                extra_reqs_raw = giveaway.get('extra_reqs') or {}
                extra_reqs = json.loads(extra_reqs_raw) if isinstance(extra_reqs_raw, str) else (extra_reqs_raw or {})
                reroll_hist = extra_reqs.get('reroll_history', [])
                if reroll_hist:
                    hist_mentions = ", ".join(f"<@{w_id}>" for w_id in reroll_hist)
                    desc_lines.append(f"📜 *Lịch sử trúng:* {hist_mentions}")
            if status_note:
                desc_lines.append(f"\n⚠️ {status_note}")
            elif not winners:
                desc_lines.append(f"\n*Không có người tham gia hợp lệ.*")
        elif status == "cancelled":
            desc_lines.append(f"\n🛑 *Trạng thái:* {status_note or 'Giveaway này đã bị huỷ bởi Host.'}")

        if custom_note:
            desc_lines.append(f"\n📝 *Ghi chú:* {custom_note}")

        return "\n".join(desc_lines)

    def build_giveaway_embed(
        self,
        giveaway: dict,
        status: str = "active",
        participants_count: int = 0,
        winners: Optional[list] = None,
        status_note: Optional[str] = None
    ) -> discord.Embed:
        prize = giveaway.get('prize', '')
        host_id = giveaway.get('host_id', 0)
        winner_count = giveaway.get('winner_count', 1)
        ends_at = giveaway.get('ends_at', int(time.time()))

        req_roles_raw = giveaway.get('required_roles')
        required_roles = json.loads(req_roles_raw) if isinstance(req_roles_raw, str) else (req_roles_raw or [])

        bonus_roles_raw = giveaway.get('bonus_roles') or {}
        bonus_roles = json.loads(bonus_roles_raw) if isinstance(bonus_roles_raw, str) else (bonus_roles_raw or {})

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        embed_cfg_raw = giveaway.get('embed_config') or {}
        embed_cfg = json.loads(embed_cfg_raw) if isinstance(embed_cfg_raw, str) else (embed_cfg_raw or {})

        default_titles = {
            "active": "<a:thanhgia:1526231085221023845> Giveaway Bắt Đầu <a:thanhgia:1526231085221023845>",
            "ended": "<a:thanhgia:1526231085221023845> **Giveaway Kết Thúc** <a:thanhgia:1526231085221023845>",
            "cancelled": "🎉 GIVEAWAY ĐÃ BỊ HUỶ 🎉",
            "rerolled": "🎉 GIVEAWAY ĐÃ QUAY LẠI KẾT QUẢ 🎉",
            "no_participants": "👻 GIVEAWAY KẾT THÚC — KHÔNG CÓ NGƯỜI THAM GIA"
        }

        # Resolution: {status}_title -> title -> default_titles[status]
        title = embed_cfg.get(f"{status}_title") or embed_cfg.get('title') or default_titles.get(status, default_titles["active"])
        color = parse_color(embed_cfg.get('color')) or discord.Color.purple()

        embed = discord.Embed(title=title, color=color)

        # Author
        author_name = embed_cfg.get('author_name')
        if author_name:
            host_user = self.bot.get_user(host_id)
            formatted_name = author_name.replace("{host_name}", host_user.name if host_user else str(host_id))
            author_icon = embed_cfg.get('author_icon')
            if author_icon and "{host_avatar}" in author_icon and host_user and host_user.display_avatar:
                author_icon = host_user.display_avatar.url
            author_url = embed_cfg.get('author_url')
            author_kwargs = {"name": formatted_name}
            if author_icon:
                author_kwargs["icon_url"] = author_icon
            if author_url:
                author_kwargs["url"] = author_url
            embed.set_author(**author_kwargs)

        # Description resolution order:
        # {status}_desc -> custom_desc -> build_default_description
        state_desc = embed_cfg.get(f"{status}_desc")
        general_desc = embed_cfg.get('custom_desc')

        if state_desc and state_desc.strip():
            embed.description = self.format_embed_description(
                state_desc.strip(),
                giveaway,
                participants_count=participants_count,
                status=status,
                winners=winners,
                status_note=status_note
            )
        elif general_desc and general_desc.strip():
            has_placeholders = any(
                f"{{{placeholder}}}" in general_desc
                for placeholder in AVAILABLE_PLACEHOLDERS
            )
            if has_placeholders:
                embed.description = self.format_embed_description(
                    general_desc.strip(),
                    giveaway,
                    participants_count=participants_count,
                    status=status,
                    winners=winners,
                    status_note=status_note
                )
            else:
                embed.description = self.build_default_description(
                    giveaway,
                    status=status,
                    participants_count=participants_count,
                    winners=winners,
                    status_note=status_note,
                    custom_note=general_desc.strip()
                )
        else:
            embed.description = self.build_default_description(
                giveaway,
                status=status,
                participants_count=participants_count,
                winners=winners,
                status_note=status_note
            )

        # Footer
        footer_text = embed_cfg.get('footer_text') or "Sylus Meow • Giveaway System"
        footer_icon = embed_cfg.get('footer_icon')
        if footer_icon:
            embed.set_footer(text=footer_text, icon_url=footer_icon)
        else:
            embed.set_footer(text=footer_text)

        # Thumbnail
        thumb = embed_cfg.get('thumbnail', 'host')
        if thumb == 'host' or not thumb:
            self.set_embed_host_thumbnail(embed, host_id)
        elif thumb == 'server':
            guild = self.bot.get_guild(giveaway.get('guild_id', 0))
            if guild and guild.icon:
                embed.set_thumbnail(url=guild.icon.url)
        elif thumb != 'none':
            embed.set_thumbnail(url=thumb)

        # Banner / Image
        banner = embed_cfg.get('banner')
        if banner:
            embed.set_image(url=banner)

        return embed

    def build_active_embed(self, giveaway: dict, participants_count: int) -> discord.Embed:
        """Backwards compatibility wrapper for active giveaway embed."""
        return self.build_giveaway_embed(giveaway, status="active", participants_count=participants_count)

    def build_ended_embed(self, giveaway: dict, winners: list, status_note: Optional[str] = None) -> discord.Embed:
        """Backwards compatibility wrapper for ended giveaway embed."""
        return self.build_giveaway_embed(giveaway, status="ended", winners=winners, status_note=status_note)

    async def update_and_sync_giveaway(
        self,
        message_id: int,
        guild_id: Optional[int] = None,
        expected_status: Optional[int] = None,
        expected_version: Optional[int] = None,
        status: Optional[str] = None,
        status_note: Optional[str] = None,
        **changes
    ) -> tuple[bool, Optional[str]]:
        """Single pipeline for updating database and synchronizing live Discord message.
        
        Only returns (True, None) if BOTH database update and Discord message edit succeed.
        If Discord message edit fails, automatically rolls back database changes to previous state.
        """
        giveaway = self.get_giveaway(message_id, guild_id=guild_id)
        if not giveaway:
            return False, "Không tìm thấy Giveaway này trong server."

        if guild_id is not None and giveaway['guild_id'] != guild_id:
            return False, "Giveaway không thuộc server này."

        if expected_status is not None and giveaway['ended'] != expected_status:
            return False, f"Trạng thái giveaway đã thay đổi (hiện tại: {giveaway['ended']})."

        if expected_version is not None and giveaway.get('version', 0) != expected_version:
            return False, "Giveaway đã bị chỉnh sửa bởi một phiên khác (Version mismatch)."

        # Validate ends_at
        if 'ends_at' in changes and changes.get('ended', giveaway['ended']) == 0:
            if changes['ends_at'] <= int(time.time()):
                return False, "Thời gian kết thúc phải ở tương lai."

        # Validate mutual exclusion between required roles and bonus roles
        if 'required_roles' in changes or 'bonus_roles' in changes:
            req = changes.get('required_roles', giveaway.get('required_roles'))
            bon = changes.get('bonus_roles', giveaway.get('bonus_roles'))
            if isinstance(req, str):
                try:
                    req = json.loads(req)
                except Exception:
                    req = []
            if isinstance(bon, str):
                try:
                    bon = json.loads(bon)
                except Exception:
                    bon = {}
            if req and bon:
                return False, "Không thể vừa cấu hình role bắt buộc vừa cấu hình cộng vé bonus."

        # Keep snapshot of current state for rollback if Discord sync fails
        previous_state = giveaway.copy()
        rollback_fields = set(changes)
        updated_version = int(previous_state.get('version', 0) or 0) + 1

        # Perform DB update
        db_success = self.update_giveaway_full(message_id, expected_version=expected_version, **changes)
        if not db_success:
            return False, "Lỗi khi cập nhật cơ sở dữ liệu (xung đột phiên bản hoặc dữ liệu không hợp lệ)."

        updated = self.get_giveaway(message_id, guild_id=guild_id)
        if not updated:
            self._rollback_giveaway_db(
                message_id,
                previous_state,
                changed_fields=rollback_fields,
                expected_current_version=updated_version
            )
            return False, "Không thể tải lại dữ liệu giveaway sau khi cập nhật."

        # Determine status string
        if not status:
            ended_code = updated.get('ended', 0)
            if ended_code == 0 or ended_code == 3:
                status = "active"
            elif ended_code == 1:
                extra_reqs_raw = updated.get('extra_reqs') or {}
                try:
                    extra_reqs = json.loads(extra_reqs_raw) if isinstance(extra_reqs_raw, str) else extra_reqs_raw
                except Exception:
                    extra_reqs = {}
                status = "no_participants" if extra_reqs.get("end_reason") == "no_participants" else "ended"
            elif ended_code == 2:
                status = "cancelled"
            else:
                status = "active"

        # Resolve participants count
        raw_p = updated.get('participants', '{}')
        try:
            p_dict = json.loads(raw_p) if isinstance(raw_p, str) else raw_p
            p_count = len(p_dict)
        except Exception:
            p_count = 0

        # Resolve winners
        if 'winners' in changes:
            winners_list = changes['winners']
        else:
            raw_w = updated.get('winners', '[]')
            try:
                winners_list = json.loads(raw_w) if isinstance(raw_w, str) else raw_w
            except Exception:
                winners_list = []

        # Build embed
        embed = self.build_giveaway_embed(
            updated,
            status=status,
            participants_count=p_count,
            winners=winners_list,
            status_note=status_note
        )

        guild = self.bot.get_guild(updated['guild_id'])
        if not guild:
            self._rollback_giveaway_db(message_id, previous_state, rollback_fields, updated_version)
            return False, "Bot không tìm thấy server của giveaway này."

        channel = guild.get_channel(updated['channel_id'])
        if not channel:
            self._rollback_giveaway_db(message_id, previous_state, rollback_fields, updated_version)
            return False, "Bot không tìm thấy kênh của giveaway này."

        try:
            message = await channel.fetch_message(message_id)
        except Exception as e:
            logger.warning(f"Could not fetch message {message_id} to sync: {e}")
            self._rollback_giveaway_db(message_id, previous_state, rollback_fields, updated_version)
            return False, f"Không thể lấy tin nhắn Discord: {e}"

        try:
            if status == "active" and updated['ended'] == 0:
                cfg_raw = updated.get('embed_config') or {}
                cfg = json.loads(cfg_raw) if isinstance(cfg_raw, str) else (cfg_raw or {})
                ping_content = cfg.get('ping_content') or f"# <a:w1:1526231439425667093> Giveaway {guild.name} <a:w2:1526231455422877798>"
                ping_content = self.format_ping_content(ping_content, updated, guild)
                await message.edit(content=ping_content, embed=embed, allowed_mentions=discord.AllowedMentions.none())
            else:
                await message.edit(embed=embed, view=None, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} on Discord: {e}")
            self._rollback_giveaway_db(message_id, previous_state, rollback_fields, updated_version)
            return False, f"Lỗi cập nhật tin nhắn Discord: {e}"

        return True, None

    def _rollback_giveaway_db(
        self,
        msg_id: int,
        snapshot: dict,
        changed_fields: Optional[set[str]] = None,
        expected_current_version: Optional[int] = None
    ) -> bool:
        """Rolls back only fields changed by the failed sync, guarded by OCC version."""
        try:
            rollbackable = {
                'prize', 'winner_count', 'ends_at', 'ended', 'required_roles',
                'bonus_roles', 'embed_config', 'extra_reqs', 'role_bonus_prizes',
                'winners', 'participants'
            }
            json_fields = {
                'required_roles', 'bonus_roles', 'embed_config', 'extra_reqs',
                'role_bonus_prizes', 'winners', 'participants'
            }
            fields_to_restore = rollbackable if changed_fields is None else (rollbackable & set(changed_fields))
            assignments = []
            params = []
            for field in sorted(fields_to_restore):
                value = snapshot.get(field)
                if field in json_fields and isinstance(value, (list, dict)):
                    value = json.dumps(value)
                assignments.append(f"{field} = ?")
                params.append(value)

            assignments.extend(["updated_at = ?", "version = ?"])
            params.extend([snapshot.get('updated_at', 0), snapshot.get('version', 0)])
            params.append(msg_id)

            query = f"UPDATE giveaways SET {', '.join(assignments)} WHERE id = ?"
            if expected_current_version is not None:
                query += " AND version = ?"
                params.append(expected_current_version)

            self.economy.cur.execute(query, tuple(params))
            if self.economy.cur.rowcount <= 0:
                logger.warning(
                    "Skipped rollback for giveaway %s because its version changed concurrently.",
                    msg_id
                )
                return False
            self.economy.conn.commit()
            return True
        except Exception as e:
            logger.error(f"Failed to rollback giveaway {msg_id}: {e}", exc_info=True)
            return False

    async def sync_giveaway_message(self, message_id: int):
        """Immediately syncs changes to the live giveaway message on Discord."""
        await self.update_and_sync_giveaway(message_id)

    async def update_giveaway_embed_msg(self, message: discord.Message, giveaway: dict, participants_count: int):
        embed = self.build_active_embed(giveaway, participants_count)
        try:
            await message.edit(embed=embed)
        except Exception as e:
            logger.warning(f"Could not edit giveaway message {message.id}: {e}")

    def schedule_embed_update(self, message: discord.Message, giveaway: dict, participants_count: int):
        message_id = message.id
        self.pending_embed_updates[message_id] = (message, giveaway, participants_count)
        if message_id in self.update_tasks:
            return
        
        loop = asyncio.get_running_loop()
        self.update_tasks[message_id] = loop.create_task(self.run_debounced_embed_update(message_id))

    async def run_debounced_embed_update(self, message_id: int):
        await asyncio.sleep(2.0)
        info = self.pending_embed_updates.pop(message_id, None)
        self.update_tasks.pop(message_id, None)
        if info:
            message, giveaway, count = info
            fresh = self.get_giveaway(message_id)
            if fresh and fresh['ended'] == 0:
                await self.update_giveaway_embed_msg(message, fresh, count)

    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if not is_giveaway_emoji(payload.emoji):
            return

        message_id = payload.message_id
        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            return

        guild = self.bot.get_guild(payload.guild_id)
        if not guild:
            return

        member = payload.member
        if not member:
            try:
                member = await guild.fetch_member(payload.user_id)
            except discord.HTTPException:
                return

        if member.bot:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        message = channel.get_partial_message(message_id)

        lock = self.join_locks.setdefault(message_id, asyncio.Lock())
        async with lock:
            giveaway = self.get_giveaway(message_id)
            if not giveaway or giveaway['ended'] != 0:
                try:
                    await message.remove_reaction(payload.emoji, member)
                except discord.HTTPException:
                    pass
                return

            user_id = member.id
            try:
                participants = json.loads(giveaway['participants'])
            except Exception:
                participants = {}

            if isinstance(participants, list):
                participants = {str(uid): 1 for uid in participants}

            if str(user_id) in participants:
                return

            # Check required roles (Private mode)
            required_roles_raw = giveaway.get('required_roles')
            required_roles = json.loads(required_roles_raw) if isinstance(required_roles_raw, str) else (required_roles_raw or [])
            if required_roles:
                has_role = False
                for r_id in required_roles:
                    if member.get_role(r_id) is not None:
                        has_role = True
                        break
                if not has_role:
                    try:
                        await message.remove_reaction(payload.emoji, member)
                    except discord.HTTPException:
                        pass
                    
                    roles_mentions = ", ".join(f"<@&{r_id}>" for r_id in required_roles)
                    try:
                        embed = discord.Embed(
                            title="❌ Tham gia Giveaway thất bại",
                            description=f"Bạn không thể tham gia giveaway **{giveaway['prize']}** vì không có role yêu cầu.\nVai trò yêu cầu: {roles_mentions}",
                            color=discord.Color.red()
                        )
                        await member.send(embed=embed)
                    except discord.Forbidden:
                        pass
                    return

            # Calculate entries
            bonus_roles_str = giveaway.get('bonus_roles', '{}')
            bonus_roles = json.loads(bonus_roles_str) if isinstance(bonus_roles_str, str) else (bonus_roles_str or {})
            entries = 1
            if bonus_roles:
                for r_id_str, extra in bonus_roles.items():
                    try:
                        r_id = int(r_id_str)
                        if member.get_role(r_id) is not None:
                            entries += int(extra)
                    except ValueError:
                        pass
            else:
                env_bonus = self.get_env_bonus_roles()
                if env_bonus:
                    for r_id, extra in env_bonus.items():
                        if member.get_role(r_id) is not None:
                            entries += int(extra)

            entries = min(max(1, entries), 100)
            participants[str(user_id)] = entries
            self.update_participants(message_id, participants)
            participants_count = len(participants)

        self.schedule_embed_update(message, giveaway, participants_count)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if not is_giveaway_emoji(payload.emoji):
            return

        message_id = payload.message_id
        giveaway = self.get_giveaway(message_id)
        if not giveaway or giveaway['ended'] != 0:
            return

        channel = self.bot.get_channel(payload.channel_id)
        if not channel:
            return

        message = channel.get_partial_message(message_id)
        user_id = payload.user_id

        lock = self.join_locks.setdefault(message_id, asyncio.Lock())
        async with lock:
            giveaway = self.get_giveaway(message_id)
            if not giveaway or giveaway['ended'] != 0:
                return

            # Check if the user still has another valid giveaway reaction on the message
            try:
                full_msg = await channel.fetch_message(message_id)
                still_has_reaction = False
                for r in full_msg.reactions:
                    if is_giveaway_emoji(r.emoji):
                        async for u in r.users(limit=None):
                            if u.id == user_id:
                                still_has_reaction = True
                                break
                    if still_has_reaction:
                        break
                if still_has_reaction:
                    return
            except Exception:
                pass

            try:
                participants = json.loads(giveaway['participants'])
            except Exception:
                participants = {}

            if isinstance(participants, list):
                participants = {str(uid): 1 for uid in participants}

            if str(user_id) not in participants:
                return

            participants.pop(str(user_id), None)
            self.update_participants(message_id, participants)
            participants_count = len(participants)

        self.schedule_embed_update(message, giveaway, participants_count)

    def parse_giveaway_args(self, args_str: str):
        """Parses arguments string to extract the prize description, flags, and role bonus prizes."""
        all_flags = [
            "--banner", "-banner", "--image", "-image",
            "--thumb", "-thumb", "--thumbnail", "-thumbnail",
            "--color", "-color", "--mau", "-mau",
            "--title", "-title", "--tieude", "-tieude",
            "--desc", "-desc", "--note", "-note", "--mota", "-mota",
            "--ping", "-ping", "--msg", "-msg",
            "--footer", "-footer",
            "--role", "-role",
            "--bonus", "-bonus",
            "--bonus-prize", "-bonus-prize", "--prizebonus", "-prizebonus", "--thuongthem", "-thuongthem",
            "--channel", "-channel"
        ]
        
        min_index = len(args_str)
        for flag in all_flags:
            idx = args_str.lower().find(flag)
            if idx != -1 and idx < min_index:
                min_index = idx

        prize = args_str[:min_index].strip()
        flags_part = args_str[min_index:].strip()

        required_roles = []
        bonus_roles = {}
        role_bonus_prizes = {}
        target_channel = None
        embed_config = {}

        if flags_part:
            tokens = flags_part.split()
            i = 0
            while i < len(tokens):
                tok = tokens[i].lower()
                if tok in ["--banner", "-banner", "--image", "-image"]:
                    i += 1
                    if i < len(tokens):
                        embed_config["banner"] = tokens[i]
                        i += 1
                elif tok in ["--thumb", "-thumb", "--thumbnail", "-thumbnail"]:
                    i += 1
                    if i < len(tokens):
                        embed_config["thumbnail"] = tokens[i]
                        i += 1
                elif tok in ["--color", "-color", "--mau", "-mau"]:
                    i += 1
                    if i < len(tokens):
                        embed_config["color"] = tokens[i]
                        i += 1
                elif tok in ["--title", "-title", "--tieude", "-tieude"]:
                    i += 1
                    val_parts = []
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        val_parts.append(tokens[i])
                        i += 1
                    if val_parts:
                        embed_config["title"] = " ".join(val_parts)
                elif tok in ["--desc", "-desc", "--note", "-note", "--mota", "-mota"]:
                    i += 1
                    val_parts = []
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        val_parts.append(tokens[i])
                        i += 1
                    if val_parts:
                        embed_config["custom_desc"] = " ".join(val_parts)
                elif tok in ["--ping", "-ping", "--msg", "-msg"]:
                    i += 1
                    val_parts = []
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        val_parts.append(tokens[i])
                        i += 1
                    if val_parts:
                        embed_config["ping_content"] = " ".join(val_parts)
                elif tok in ["--footer", "-footer"]:
                    i += 1
                    val_parts = []
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        val_parts.append(tokens[i])
                        i += 1
                    if val_parts:
                        embed_config["footer_text"] = " ".join(val_parts)
                elif tok in ["--role", "-role"]:
                    i += 1
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        role_id = parse_role_mention(tokens[i])
                        if role_id:
                            required_roles.append(role_id)
                        i += 1
                elif tok in ["--bonus", "-bonus"]:
                    i += 1
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        role_id = parse_role_mention(tokens[i])
                        if role_id:
                            if i + 1 < len(tokens) and tokens[i+1].isdigit():
                                bonus_roles[role_id] = int(tokens[i+1])
                                i += 2
                            else:
                                bonus_roles[role_id] = 1
                                i += 1
                        else:
                            i += 1
                elif tok in ["--bonus-prize", "-bonus-prize", "--prizebonus", "-prizebonus", "--thuongthem", "-thuongthem"]:
                    i += 1
                    while i < len(tokens) and not tokens[i].startswith("-"):
                        role_id = parse_role_mention(tokens[i])
                        if role_id:
                            i += 1
                            prize_parts = []
                            while i < len(tokens) and not tokens[i].startswith("-") and parse_role_mention(tokens[i]) is None:
                                prize_parts.append(tokens[i])
                                i += 1
                            bonus_str = " ".join(prize_parts).strip().strip('"').strip("'")
                            if bonus_str:
                                role_bonus_prizes[str(role_id)] = bonus_str
                        else:
                            i += 1
                elif tok in ["--channel", "-channel"]:
                    i += 1
                    if i < len(tokens):
                        target_channel = parse_channel_mention(tokens[i])
                        i += 1
                else:
                    i += 1

        return prize, required_roles, bonus_roles, role_bonus_prizes, target_channel, embed_config

    @commands.group(
        name="giveaway",
        aliases=["ga"],
        brief="Quản lý hệ thống giveaway chuyên nghiệp",
        invoke_without_command=True
    )
    async def giveaway_group(
        self,
        ctx: commands.Context,
        time_str: str = None,
        winners_count: int = None,
        *,
        args_str: str = None
    ):
        if time_str is None or winners_count is None or args_str is None:
            await self.send_giveaway_help(ctx)
            return

        # Permission check: Only users with management perms can create giveaways
        if not self.can_manage_giveaway(ctx.author):
            await ctx.send(
                "❌ Bạn không có quyền tạo Giveaway trên server (Yêu cầu quyền Quản lý Server / Manage Server hoặc Quản trị viên).",
                delete_after=10
            )
            return

        # Parse args_str
        prize, required_roles, bonus_roles, role_bonus_prizes, target_channel, embed_config = self.parse_giveaway_args(args_str)

        # Check attached images
        if not embed_config.get("banner") and ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    embed_config["banner"] = att.url
                    break

        # Check default template for guild
        saved_template = self.get_template(ctx.guild.id, template_name="default")
        if saved_template:
            for k, v in saved_template.items():
                if k not in embed_config and v:
                    embed_config[k] = v

        # Delete command message
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Check mutual exclusion of private mode and custom bonus roles
        if required_roles and bonus_roles:
            await ctx.send("❌ Bạn không thể cấu hình giới hạn role và cộng lượt cùng lúc trong một giveaway!", delete_after=10)
            return

        # Validate arguments
        duration_seconds = parse_time(time_str)
        if duration_seconds is None or duration_seconds < 10 or duration_seconds > 30 * 86400:
            await ctx.send("❌ Định dạng thời gian không hợp lệ (tối thiểu 10 giây, tối đa 30 ngày). Ví dụ: `30m`, `1h`, `2d`.", delete_after=10)
            return

        if winners_count <= 0 or winners_count > 50:
            await ctx.send("❌ Số người thắng phải từ 1 đến 50.", delete_after=10)
            return

        if not prize or len(prize) > 500:
            await ctx.send("❌ Phần thưởng không được để trống và không vượt quá 500 ký tự.", delete_after=10)
            return

        # Cap bonus entries per role to prevent abuse
        for r_id, extra in list(bonus_roles.items()):
            if extra <= 0:
                bonus_roles.pop(r_id, None)
            elif extra > 50:
                bonus_roles[r_id] = 50

        # Target channel
        channel = ctx.channel
        if target_channel:
            channel = ctx.guild.get_channel(target_channel)
            if not channel:
                await ctx.send("❌ Không tìm thấy kênh được chỉ định.", delete_after=10)
                return

        # Calculate ends_at
        now = int(time.time())
        ends_at = now + duration_seconds

        # Temporary giveaway object
        giveaway_temp = {
            'guild_id': ctx.guild.id,
            'channel_id': channel.id,
            'prize': prize,
            'host_id': ctx.author.id,
            'winner_count': winners_count,
            'ends_at': ends_at,
            'required_roles': required_roles,
            'bonus_roles': bonus_roles,
            'role_bonus_prizes': role_bonus_prizes,
            'embed_config': embed_config
        }
        embed = self.build_active_embed(giveaway_temp, 0)

        # Validate and sanitize ping mentions
        allowed_roles = []
        allow_everyone = False
        author_perms = ctx.author.guild_permissions if hasattr(ctx.author, "guild_permissions") else None
        can_mention_everyone = author_perms.mention_everyone or author_perms.administrator if author_perms else False

        ping_raw = self.format_ping_content(embed_config.get("ping_content", ""), giveaway_temp, ctx.guild)
        if ping_raw:
            if "@everyone" in ping_raw or "@here" in ping_raw:
                if can_mention_everyone:
                    allow_everyone = True
                else:
                    ping_raw = ping_raw.replace("@everyone", "@\u200beveryone").replace("@here", "@\u200bhere")
                    embed_config["ping_content"] = ping_raw

            role_matches = re.findall(r"<@&(\d+)>", ping_raw)
            for rid_str in role_matches:
                role_obj = ctx.guild.get_role(int(rid_str))
                if role_obj:
                    if role_obj.mentionable or can_mention_everyone:
                        allowed_roles.append(role_obj)
                    else:
                        ping_raw = ping_raw.replace(f"<@&{rid_str}>", f"@{role_obj.name}")
                        embed_config["ping_content"] = ping_raw

        allowed_mentions = discord.AllowedMentions(
            roles=allowed_roles,
            everyone=allow_everyone,
            users=False
        )

        ping_header = ping_raw or f"# <a:w1:1526231439425667093> Giveaway {ctx.guild.name} <a:w2:1526231455422877798>"

        try:
            msg = await channel.send(content=ping_header, embed=embed, allowed_mentions=allowed_mentions)
            try:
                await msg.add_reaction("<a:zh_coinzh:1544913759297085440>")
            except (discord.HTTPException, discord.NotFound):
                try:
                    await msg.add_reaction("🎉")
                except Exception:
                    pass
        except discord.Forbidden:
            await ctx.send(f"❌ Bot không có quyền gửi tin nhắn hoặc embed ở kênh {channel.mention}.", delete_after=10)
            return

        # Save to database
        saved = self.save_giveaway(
            msg.id,
            ctx.guild.id,
            channel.id,
            prize,
            ctx.author.id,
            winners_count,
            ends_at,
            required_roles,
            bonus_roles,
            embed_config=embed_config,
            role_bonus_prizes=role_bonus_prizes
        )
        if not saved:
            try:
                await msg.delete()
            except Exception:
                pass
            await ctx.send("❌ Không thể lưu Giveaway vào cơ sở dữ liệu. Vui lòng thử lại sau.", delete_after=10)
            return

    async def send_giveaway_help(self, ctx: commands.Context):
        prefix = ctx.prefix
        embed = discord.Embed(
            title="<a:thanhgia:1526231085221023845> HƯỚNG DẪN HỆ THỐNG GIVEAWAY CHUYÊN NGHIỆP <a:thanhgia:1526231085221023845>",
            color=discord.Color.purple()
        )
        embed.description = (
            f"### 📌 1. Tạo Giveaway Nhanh\n"
            f"`{prefix}ga <thời_gian> <số_người_thắng> <phần_thưởng> [flags]`\n"
            f"👉 *Ví dụ cơ bản:* `{prefix}ga 10m 1 100k Xu`\n"
            f"👉 *Ví dụ có Banner & Màu:* `{prefix}ga 1h 1 Skin VIP --banner https://... --color gold`\n"
            f"👉 *Ví dụ có Role Bonus Quà Thêm:* `{prefix}ga 2h 1 100k --bonus-prize @Booster \"+50k Momo\" @VIP \"+1 Skin\"`\n"
            f"👉 *Ví dụ Giới hạn Role:* `{prefix}ga 2h 2 Skin VIP --role @Donator @VIP`\n"
            f"👉 *Ví dụ Kênh khác:* `{prefix}ga 1d 1 Nitro --channel #giveaways`\n\n"
            f"### 🎨 2. Danh Sách Cờ Lệnh (Flags) Tùy Chỉnh\n"
            f"• `--banner <link_ảnh>` : Thêm ảnh banner lớn ở thân embed *(hoặc đính kèm file ảnh)*\n"
            f"• `--color <mã_màu>` : Đổi màu viền embed (`#FFD700`, `gold`, `purple`, `cyan`...)\n"
            f"• `--thumb <loại>` : Đổi thumbnail góc phải (`host`, `server`, `none`, hoặc url ảnh)\n"
            f"• `--title <tiêu_đề>` : Đặt tiêu đề Embed theo ý muốn\n"
            f"• `--desc <ghi_chú>` : Lời nhắn, thể lệ của Host\n"
            f"• `--ping <role/all>` : Tag `@everyone` hoặc role bên trên embed\n"
            f"• `--footer <text>` : Ghi đè chữ chân trang\n"
            f"• `--bonus-prize @Role <quà>` : Cấu hình quà tặng thêm khi role trúng giải\n"
            f"• `--role @Role` : Chỉ cho phép role chỉ định tham gia\n"
            f"• `--bonus @Role <vé>` : Cộng thêm vé quay may mắn cho role\n"
            f"• `--channel #kênh` : Phát giveaway sang kênh chỉ định\n\n"
            f"### 🔍 3. Kiểm Tra Role Bonus Người Thắng (Dành Cho Host)\n"
            f"`{prefix}ga check <id_tin_nhắn> [@NgườiThắng]` *(hoặc reply tin nhắn GA và gõ `{prefix}ga check [@User]`)*\n"
            f"👉 Bot sẽ gửi một **dòng/tin nhắn riêng biệt** tổng kết quà gốc + các bonus role người đó có, **không làm thay đổi Embed gốc của Giveaway**.\n\n"
            f"### 🎁 4. Quản Lý Role Bonus Phần Thưởng\n"
            f"• Thêm bonus: `{prefix}ga setbonus <id_tin_nhắn> @Role <quà_thêm>`\n"
            f"• Xóa bonus: `{prefix}ga delbonus <id_tin_nhắn> @Role`\n"
            f"• Xem danh sách: `{prefix}ga listbonus <id_tin_nhắn>`\n\n"
            f"### 🛠️ 5. Bảng Điều Khiển Nút Bấm (`{prefix}ga edit`)\n"
            f"`{prefix}ga edit <id_tin_nhắn>` : Mở bảng điều khiển Ẩn (Ephemeral) sửa Banner, Màu, Prize Bonus, Thời gian, v.v.\n\n"
            f"### 🎮 6. Các Lệnh Quản Lý Khác\n"
            f"• Kết thúc sớm: `{prefix}ga ketthuc <id_tin_nhắn>`\n"
            f"• Quay lại (Reroll): `{prefix}ga quaylai <id_tin_nhắn> [số_lượng]`\n"
            f"• Hủy bỏ: `{prefix}ga huy <id_tin_nhắn>`"
        )
        embed.set_footer(text="Sylus Meow • Giveaway System")
        await ctx.send(embed=embed)

    @giveaway_group.command(name="edit", aliases=["sua", "chinhsua", "custom", "studio"], brief="Mở bảng điều khiển tương tác (Mimu-style) để chỉnh sửa Giveaway hoặc Mẫu Mặc Định")
    async def giveaway_edit(self, ctx: commands.Context, message_id: Optional[int] = None):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # 1. Nếu không có message_id, thử lấy từ tin nhắn đang Reply
        if message_id is None:
            if ctx.message.reference and ctx.message.reference.message_id:
                message_id = ctx.message.reference.message_id

        # 2. Nếu vẫn không có message_id, tự động tìm Giveaway đang chạy trong kênh / server của Host
        if message_id is None:
            self.economy.cur.execute(
                "SELECT id FROM giveaways WHERE guild_id = ? AND channel_id = ? AND ended = 0 ORDER BY id DESC LIMIT 1",
                (ctx.guild.id, ctx.channel.id)
            )
            row = self.economy.cur.fetchone()
            if not row:
                self.economy.cur.execute(
                    "SELECT id FROM giveaways WHERE guild_id = ? AND host_id = ? AND ended = 0 ORDER BY id DESC LIMIT 1",
                    (ctx.guild.id, ctx.author.id)
                )
                row = self.economy.cur.fetchone()
            if not row:
                self.economy.cur.execute(
                    "SELECT id FROM giveaways WHERE guild_id = ? AND ended = 0 ORDER BY id DESC LIMIT 1",
                    (ctx.guild.id,)
                )
                row = self.economy.cur.fetchone()
            
            if row:
                message_id = row[0]

        # 3. Nếu tìm thấy Giveaway đang chạy -> Kiểm tra quyền và mở bảng chỉnh sửa Giveaway đó
        if message_id is not None:
            giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
            if giveaway:
                if giveaway['ended'] != 0:
                    await ctx.send("❌ Giveaway này đã kết thúc hoặc đã bị huỷ.", delete_after=10)
                    return
                if not self.can_manage_giveaway(ctx.author, giveaway):
                    await ctx.send(
                        "❌ Bạn không có quyền quản lý để chỉnh sửa Giveaway này. (Yêu cầu quyền Quản lý Server hoặc là Host của Giveaway)",
                        delete_after=10
                    )
                    return

                trigger_view = OpenEditorTriggerView(self, giveaway, ctx.author, ctx.guild)
                await ctx.send(
                    f"🛠️ **Bảng Chỉnh Sửa Giveaway ID `{message_id}`** (Dành riêng cho <@{ctx.author.id}>):\n"
                    f"👉 *Nhấn nút bên dưới để mở Bảng Điều Khiển Riêng Tư (Live Preview & Tùy chỉnh Embed)*:",
                    view=trigger_view,
                    delete_after=60
                )
                return

        # 4. Nếu không có Giveaway nào đang chạy
        if not self.can_manage_giveaway(ctx.author):
            await ctx.send("❌ Bạn không có quyền quản lý hoặc không có Giveaway nào của bạn đang chạy để chỉnh sửa.", delete_after=10)
            return

        await ctx.send(
            f"❌ Không tìm thấy Giveaway nào đang chạy trong server.\n"
            f"👉 Để thiết kế Mẫu Giveaway Mặc Định cho Server, vui lòng dùng lệnh `{ctx.prefix}ga template`.\n"
            f"👉 Để sửa một Giveaway cụ thể, vui lòng cung cấp Message ID: `{ctx.prefix}ga edit <message_id>`.",
            delete_after=15
        )

    @giveaway_group.command(name="template", brief="Thiết lập mẫu Embed Giveaway mặc định cho toàn server")
    async def giveaway_template(self, ctx: commands.Context):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if not self.can_manage_server_template(ctx.author, ctx.guild):
            await ctx.send(
                "❌ Bạn không có quyền quản lý Mẫu Giveaway của Server. (Yêu cầu quyền Administrator, Quản lý Server hoặc Role `Giveaway Manager`)",
                delete_after=10
            )
            return

        saved_template = self.get_template(ctx.guild.id, "default") or {}
        now = int(time.time())
        giveaway_template_obj = {
            'id': 0,
            'guild_id': ctx.guild.id,
            'channel_id': ctx.channel.id,
            'prize': "🎁 100.000 Xu / Discord Nitro (Mẫu Server Mặc Định)",
            'host_id': ctx.author.id,
            'winner_count': 1,
            'ends_at': now + 3600,
            'ended': 0,
            'required_roles': [],
            'bonus_roles': {},
            'role_bonus_prizes': {},
            'embed_config': saved_template
        }
        trigger_view = OpenEditorTriggerView(self, giveaway_template_obj, ctx.author, ctx.guild)
        await ctx.send(
            f"🎨 **Bảng Thiết Kế Mẫu Embed Giveaway Toàn Server** (Dành riêng cho <@{ctx.author.id}>):\n"
            f"👉 *Nhấn nút bên dưới để mở Bảng Tùy Chỉnh Mẫu Server (Thay đổi sẽ áp dụng cho tất cả Giveaway mới trong server)*:",
            view=trigger_view,
            delete_after=60
        )

    @giveaway_group.command(name="setbonus", brief="Thiết lập phần thưởng thêm cho Role trong Giveaway")
    async def giveaway_setbonus(self, ctx: commands.Context, message_id_or_role: str, role_or_text: str, *, bonus_text: Optional[str] = None):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        # Check if replying to a giveaway message
        message_id = None
        role_target = None
        actual_bonus = None

        if ctx.message.reference and ctx.message.reference.message_id:
            message_id = ctx.message.reference.message_id
            role_target = parse_role_mention(message_id_or_role)
            actual_bonus = f"{role_or_text} {bonus_text}".strip() if bonus_text else role_or_text.strip()
        else:
            if message_id_or_role.isdigit():
                message_id = int(message_id_or_role)
                role_target = parse_role_mention(role_or_text)
                actual_bonus = bonus_text.strip() if bonus_text else ""
            else:
                role_target = parse_role_mention(message_id_or_role)
                actual_bonus = f"{role_or_text} {bonus_text}".strip() if bonus_text else role_or_text.strip()

        if not message_id or not role_target or not actual_bonus:
            await ctx.send(
                f"❌ Cú pháp: `{ctx.prefix}ga setbonus <id_tin_nhắn> @Role <nội_dung_quà_thêm>` (hoặc reply tin nhắn GA và gõ `{ctx.prefix}ga setbonus @Role <quà>`)",
                delete_after=10
            )
            return

        giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này trong server.", delete_after=10)
            return

        if not self.can_manage_giveaway(ctx.author, giveaway):
            await ctx.send("❌ Bạn không có quyền quản lý Giveaway này.", delete_after=10)
            return

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        role_prizes[str(role_target)] = actual_bonus
        success, err = await self.update_and_sync_giveaway(message_id, guild_id=ctx.guild.id, role_bonus_prizes=role_prizes)
        if not success:
            await ctx.send(f"❌ {err or 'Lỗi khi cập nhật Role Bonus cho giveaway.'}", delete_after=10)
            return

        await ctx.send(
            f"✅ **Đã thiết lập Role Bonus thành công cho Giveaway `{message_id}`:**\n"
            f"• Role: <@&{role_target}>\n"
            f"• Phần thưởng thêm: **{actual_bonus}**",
            delete_after=15
        )

    @giveaway_group.command(name="delbonus", brief="Xóa phần thưởng thêm của Role trong Giveaway")
    async def giveaway_delbonus(self, ctx: commands.Context, message_id_or_role: str, role_opt: Optional[str] = None):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        message_id = None
        role_target = None

        if ctx.message.reference and ctx.message.reference.message_id:
            message_id = ctx.message.reference.message_id
            role_target = parse_role_mention(message_id_or_role)
        else:
            if message_id_or_role.isdigit() and role_opt:
                message_id = int(message_id_or_role)
                role_target = parse_role_mention(role_opt)
            else:
                role_target = parse_role_mention(message_id_or_role)

        if not message_id or not role_target:
            await ctx.send(
                f"❌ Cú pháp: `{ctx.prefix}ga delbonus <id_tin_nhắn> @Role` (hoặc reply tin nhắn GA và gõ `{ctx.prefix}ga delbonus @Role`)",
                delete_after=10
            )
            return

        giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này trong server.", delete_after=10)
            return

        if not self.can_manage_giveaway(ctx.author, giveaway):
            await ctx.send("❌ Bạn không có quyền quản lý Giveaway này.", delete_after=10)
            return

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        if str(role_target) in role_prizes:
            role_prizes.pop(str(role_target))
            success, err = await self.update_and_sync_giveaway(message_id, guild_id=ctx.guild.id, role_bonus_prizes=role_prizes)
            if not success:
                await ctx.send(f"❌ {err or 'Lỗi khi cập nhật xóa Role Bonus.'}", delete_after=10)
                return
            await ctx.send(f"✅ Đã xóa Role Bonus cho role <@&{role_target}> trong Giveaway `{message_id}`.", delete_after=10)
        else:
            await ctx.send(f"ℹ️ Role <@&{role_target}> chưa được cấu hình bonus trong Giveaway `{message_id}`.", delete_after=10)

    @giveaway_group.command(name="listbonus", brief="Xem danh sách Role Bonus đã cấu hình cho Giveaway")
    async def giveaway_listbonus(self, ctx: commands.Context, message_id_opt: Optional[int] = None):
        message_id = message_id_opt
        if message_id is None and ctx.message.reference and ctx.message.reference.message_id:
            message_id = ctx.message.reference.message_id

        if message_id is None:
            await ctx.send(f"❌ Vui lòng cung cấp ID tin nhắn: `{ctx.prefix}ga listbonus <id_tin_nhắn>`", delete_after=10)
            return

        giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này trong server.", delete_after=10)
            return

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        embed = discord.Embed(
            title=f"Danh Sách Role Bonus (ID: `{message_id}`)",
            color=discord.Color.dark_embed()
        )
        embed.description = f"**Giải thưởng chính:** {giveaway['prize']}\n\n"
        if role_prizes:
            lines = []
            for rid_str, prize_text in role_prizes.items():
                lines.append(f"• <@&{rid_str}>: **{prize_text}**")
            embed.description += "**Đặc quyền Role:**\n" + "\n".join(lines)
        else:
            embed.description += "*Chưa có Role nào được cấu hình bonus cho giveaway này.*"

        embed.set_footer(text="Sylus Meow • Giveaway System")
        await ctx.send(embed=embed)

    @giveaway_group.command(name="check", aliases=["checkbonus", "kiemtra", "checkrole"], brief="Kiểm tra Role và Bonus phần thưởng của người thắng")
    async def giveaway_check(self, ctx: commands.Context, arg1: Optional[str] = None, arg2: Optional[str] = None):
        """Checks role bonuses for specific winner(s). Does NOT alter original giveaway embed."""
        message_id = None
        target_user_id = None

        # Check reply
        if ctx.message.reference and ctx.message.reference.message_id:
            message_id = ctx.message.reference.message_id
            if arg1:
                target_user_id = parse_user_mention(arg1)
        else:
            if arg1 and arg1.isdigit():
                message_id = int(arg1)
                if arg2:
                    target_user_id = parse_user_mention(arg2)
            elif arg1:
                target_user_id = parse_user_mention(arg1)
                if arg2 and arg2.isdigit():
                    message_id = int(arg2)

        if not message_id:
            await ctx.send(
                f"❌ Vui lòng chỉ định ID tin nhắn hoặc Reply vào tin nhắn Giveaway: `{ctx.prefix}ga check <id_tin_nhắn> [@NgườiThắng]`",
                delete_after=10
            )
            return

        giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này trong server.", delete_after=10)
            return

        guild = ctx.guild
        prize = giveaway['prize']
        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        # Determine target members to check
        target_ids = []
        if target_user_id:
            target_ids.append(target_user_id)
        else:
            try:
                winners = json.loads(giveaway.get('winners', '[]'))
            except Exception:
                winners = []
            if winners:
                target_ids.extend(winners)
            else:
                await ctx.send("ℹ️ Giveaway này chưa có người thắng. Bạn có thể tag trực tiếp người chơi để kiểm tra: `i?ga check <id> @User`.", delete_after=12)
                return

        # Build clean, minimal embed
        lines = []
        for uid in target_ids:
            member = guild.get_member(uid)
            if not member:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None

            matched_bonuses = []
            if member:
                for rid_str, bonus_desc in role_prizes.items():
                    try:
                        rid = int(rid_str)
                        if member.get_role(rid) is not None:
                            matched_bonuses.append((rid, bonus_desc))
                    except ValueError:
                        pass

            if matched_bonuses:
                bonus_str = ", ".join(f"<@&{r_id}> (**{b_desc}**)" for r_id, b_desc in matched_bonuses)
                all_rewards = [prize] + [b[1] for b in matched_bonuses]
                total_str = " + ".join(f"**{r}**" for r_id, r in enumerate(all_rewards))
                lines.append(
                    f"**Người chơi:** <@{uid}>\n"
                    f"• **Bonus Role:** {bonus_str}\n"
                    f"• **Tổng nhận:** {total_str}"
                )
            else:
                lines.append(
                    f"**Người chơi:** <@{uid}>\n"
                    f"• **Bonus Role:** Không có\n"
                    f"• **Tổng nhận:** **{prize}**"
                )

        embed = discord.Embed(
            title=f"Kết Quả Kiểm Tra Bonus (ID: `{message_id}`)",
            description="\n\n───────────────────\n\n".join(lines),
            color=discord.Color.dark_embed()
        )
        embed.set_footer(text=f"Giải gốc: {prize}")
        await ctx.send(embed=embed)

    @giveaway_group.command(name="ketthuc", aliases=["end"], brief="Kết thúc sớm một giveaway đang chạy")
    async def giveaway_end(self, ctx: commands.Context, message_id: int):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này trong server.", delete_after=10)
            return

        if giveaway['ended'] != 0:
            await ctx.send("❌ Giveaway này đã kết thúc hoặc đã bị huỷ trước đó.", delete_after=10)
            return

        if not self.is_host_or_admin(ctx, giveaway):
            await ctx.send("❌ Bạn không có quyền kết thúc giveaway này.", delete_after=10)
            return

        await self.end_giveaway(message_id)

    @giveaway_group.command(name="huy", aliases=["cancel"], brief="Huỷ một giveaway đang chạy")
    async def giveaway_cancel(self, ctx: commands.Context, message_id: int):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này trong server.", delete_after=10)
            return

        if giveaway['ended'] != 0:
            await ctx.send("❌ Giveaway này đã kết thúc hoặc đã bị huỷ trước đó.", delete_after=10)
            return

        if not self.is_host_or_admin(ctx, giveaway):
            await ctx.send("❌ Bạn không có quyền huỷ giveaway này.", delete_after=10)
            return

        guild = self.bot.get_guild(giveaway['guild_id'])
        if not guild:
            return

        channel = guild.get_channel(giveaway['channel_id'])
        if not channel:
            return

        success, err = await self.update_and_sync_giveaway(
            message_id,
            guild_id=ctx.guild.id,
            expected_status=0,
            ended=2,
            status="cancelled",
            status_note="Giveaway này đã bị huỷ bởi Host."
        )
        if not success:
            await ctx.send(f"❌ {err or 'Lỗi khi huỷ giveaway.'}", delete_after=10)
            return

        self.end_locks.pop(message_id, None)
        self.join_locks.pop(message_id, None)

        await channel.send(f"🛑 Giveaway giải **{giveaway['prize']}** đã bị huỷ bởi <@{ctx.author.id}>.")

    @giveaway_group.command(name="quaylai", aliases=["reroll"], brief="Quay lại người thắng mới cho giveaway đã kết thúc")
    async def giveaway_reroll(self, ctx: commands.Context, message_id: int, count: int = 1):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này trong server.", delete_after=10)
            return

        if giveaway['ended'] != 1:
            await ctx.send("❌ Chỉ có thể quay lại (reroll) cho giveaway đã kết thúc thành công.", delete_after=10)
            return

        if not self.is_host_or_admin(ctx, giveaway):
            await ctx.send("❌ Bạn không có quyền quay lại giveaway này.", delete_after=10)
            return

        if count <= 0 or count > 50:
            await ctx.send("❌ Số người thắng quay lại phải từ 1 đến 50.", delete_after=10)
            return

        guild = self.bot.get_guild(giveaway['guild_id'])
        if not guild:
            return

        channel = guild.get_channel(giveaway['channel_id'])
        if not channel:
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            await ctx.send("❌ Không tìm thấy tin nhắn giveaway gốc.", delete_after=10)
            return
        except Exception as e:
            await ctx.send(f"❌ Lỗi khi lấy tin nhắn: {e}", delete_after=10)
            return

        lock = self.end_locks.setdefault(message_id, asyncio.Lock())
        try:
            async with lock:
                # Re-fetch state inside lock to prevent concurrent reroll race conditions
                giveaway = self.get_giveaway(message_id, guild_id=ctx.guild.id)
                if not giveaway or giveaway.get('ended') != 1:
                    await ctx.send("❌ Giveaway không còn hợp lệ hoặc chưa kết thúc.", delete_after=10)
                    return

                # Read historical winners to prevent any repeat wins across all rerolls
                extra_reqs_raw = giveaway.get('extra_reqs') or {}
                extra_reqs = json.loads(extra_reqs_raw) if isinstance(extra_reqs_raw, str) else (extra_reqs_raw or {})
                try:
                    old_winners = json.loads(giveaway['winners'])
                except Exception:
                    old_winners = []

                original_winners = extra_reqs.get('original_winners', [])
                reroll_history = extra_reqs.get('reroll_history', [])
                all_excluded = set(old_winners) | set(original_winners) | set(reroll_history)

                # Candidate pool: use eligible_candidates snapshot saved at giveaway end time
                saved_candidates = extra_reqs.get('eligible_candidates')
                if saved_candidates and isinstance(saved_candidates, dict):
                    candidate_pool = {int(uid): int(cnt) for uid, cnt in saved_candidates.items()}
                else:
                    # Fallback for legacy giveaways
                    try:
                        raw_p = json.loads(giveaway.get('participants', '{}'))
                        if isinstance(raw_p, list):
                            candidate_pool = {int(uid): 1 for uid in raw_p}
                        elif isinstance(raw_p, dict):
                            candidate_pool = {int(uid): int(cnt) for uid, cnt in raw_p.items()}
                        else:
                            candidate_pool = {}
                    except Exception:
                        candidate_pool = {}

                # Filter candidate pool: exclude past winners and verify current guild membership only
                valid_candidates = {}
                for uid, entries in candidate_pool.items():
                    if uid in all_excluded:
                        continue

                    member = guild.get_member(uid)
                    if not member:
                        try:
                            member = await guild.fetch_member(uid)
                        except Exception:
                            continue
                    if not member or member.bot:
                        continue

                    valid_candidates[uid] = min(max(1, entries), 100)

                new_winners = pick_weighted_winners(valid_candidates, count, exclude=all_excluded)
                if not new_winners:
                    await ctx.send("❌ Không còn người tham gia hợp lệ nào khác chưa từng thắng để quay lại (reroll).", delete_after=10)
                    return

                # Append current winners into history before updating
                for w in old_winners:
                    if w not in reroll_history:
                        reroll_history.append(w)
                extra_reqs['reroll_history'] = reroll_history

                success, err = await self.update_and_sync_giveaway(
                    message_id,
                    guild_id=ctx.guild.id,
                    expected_status=1,
                    winners=new_winners,
                    extra_reqs=extra_reqs,
                    status="rerolled"
                )
                if not success:
                    await ctx.send(f"❌ {err or 'Lỗi khi cập nhật reroll và đồng bộ tin nhắn.'}", delete_after=10)
                    return

                prize = giveaway['prize']
                host_id = giveaway['host_id']
                new_winners_mentions = ", ".join(f"<@{w_id}>" for w_id in new_winners)
                await channel.send(f"🎉 **Reroll:** Chúc mừng {new_winners_mentions} đã thắng giải **{prize}**! Liên hệ <@{host_id}> để nhận thưởng.")
        finally:
            if message_id in self.end_locks and not lock.locked():
                self.end_locks.pop(message_id, None)

    async def end_giveaway(self, message_id: int):
        lock = self.end_locks.setdefault(message_id, asyncio.Lock())
        try:
            async with lock:
                # Atomic CAS: State transition 0 (active) -> 3 (drawing in-progress) with updated_at timestamp
                now = int(time.time())
                try:
                    self.economy.cur.execute(
                        "UPDATE giveaways SET ended = 3, updated_at = ? WHERE id = ? AND ended = 0",
                        (now, message_id)
                    )
                    if self.economy.cur.rowcount == 0:
                        return
                    self.economy.conn.commit()
                except Exception as e:
                    logger.error(f"Failed atomic CAS for giveaway {message_id}: {e}")
                    return

                giveaway = self.get_giveaway(message_id)
                if not giveaway:
                    return

                guild = self.bot.get_guild(giveaway['guild_id'])
                if not guild:
                    self.mark_ended(message_id, ended=1, winners=[])
                    return

                channel = guild.get_channel(giveaway['channel_id'])
                if not channel:
                    self.mark_ended(message_id, ended=1, winners=[])
                    return

                try:
                    message = await channel.fetch_message(message_id)
                except discord.NotFound:
                    self.mark_ended(message_id, ended=1, winners=[])
                    return
                except Exception as e:
                    logger.error(f"Error fetching message {message_id} to end: {e}")
                    # Revert state back to active so it can be retried
                    try:
                        self.economy.cur.execute("UPDATE giveaways SET ended = 0 WHERE id = ? AND ended = 3", (message_id,))
                        self.economy.conn.commit()
                    except Exception:
                        pass
                    return

                # Reconcile participants from live Discord reactions
                # Distinguish API errors (abort and retry) from genuinely 0 reactions
                reacted_uids = set()
                api_error = False
                for r in message.reactions:
                    if is_giveaway_emoji(r.emoji):
                        try:
                            async for u in r.users(limit=None):
                                if not u.bot:
                                    reacted_uids.add(u.id)
                        except Exception as e:
                            logger.warning(f"Error fetching live reaction users on {message_id}: {e}")
                            api_error = True
                            break

                if api_error:
                    logger.error(f"API error fetching live reactions for giveaway {message_id}; aborting draw and reverting state to retry")
                    try:
                        self.economy.cur.execute("UPDATE giveaways SET ended = 0 WHERE id = ? AND ended = 3", (message_id,))
                        self.economy.conn.commit()
                    except Exception:
                        pass
                    return

                all_candidate_uids = reacted_uids
                winner_count = giveaway['winner_count']
                prize = giveaway['prize']
                host_id = giveaway['host_id']

                # Dynamic revalidation of roles and entries at draw time
                required_roles_raw = giveaway.get('required_roles')
                required_roles = json.loads(required_roles_raw) if isinstance(required_roles_raw, str) else (required_roles_raw or [])
                bonus_roles_raw = giveaway.get('bonus_roles')
                bonus_roles = json.loads(bonus_roles_raw) if isinstance(bonus_roles_raw, str) else (bonus_roles_raw or {})
                env_bonus = self.get_env_bonus_roles()

                valid_candidates = {}
                for uid in all_candidate_uids:
                    member = guild.get_member(uid)
                    if not member:
                        try:
                            member = await guild.fetch_member(uid)
                        except Exception:
                            continue
                    if not member or member.bot:
                        continue

                    if required_roles:
                        if not any(member.get_role(r_id) is not None for r_id in required_roles):
                            continue

                    entries = 1
                    if bonus_roles:
                        for r_id_str, extra in bonus_roles.items():
                            try:
                                r_id = int(r_id_str)
                                if member.get_role(r_id) is not None:
                                    entries += int(extra)
                            except ValueError:
                                pass
                    elif env_bonus:
                        for r_id, extra in env_bonus.items():
                            if member.get_role(r_id) is not None:
                                entries += int(extra)

                    entries = min(max(1, entries), 100)
                    valid_candidates[uid] = entries

                if not valid_candidates:
                    extra_reqs_raw = giveaway.get('extra_reqs') or {}
                    try:
                        extra_reqs = json.loads(extra_reqs_raw) if isinstance(extra_reqs_raw, str) else dict(extra_reqs_raw)
                    except Exception:
                        extra_reqs = {}
                    extra_reqs["end_reason"] = "no_participants"
                    success, err = await self.update_and_sync_giveaway(
                        message_id,
                        guild_id=giveaway['guild_id'],
                        ended=1,
                        winners=[],
                        extra_reqs=extra_reqs,
                        status="no_participants",
                        status_note="Không có ai tham gia giveaway này."
                    )
                    if not success:
                        logger.error(f"Failed to sync ended giveaway {message_id} (no participants): {err}")
                        try:
                            self.economy.cur.execute("UPDATE giveaways SET ended = 0 WHERE id = ? AND ended = 3", (message_id,))
                            self.economy.conn.commit()
                        except Exception:
                            pass
                        return
                    cfg_raw = giveaway.get('embed_config') or {}
                    try:
                        cfg = json.loads(cfg_raw) if isinstance(cfg_raw, str) else cfg_raw
                    except Exception:
                        cfg = {}
                    message_template = cfg.get("no_participants_message") or "Không có ai tham gia giveaway **{prize}**."
                    if str(message_template).strip().lower() != "none":
                        announcement = self.format_ping_content(message_template, giveaway, guild)
                        await channel.send(announcement, allowed_mentions=discord.AllowedMentions.none())
                    return

                winners = pick_weighted_winners(valid_candidates, winner_count)
                if not winners:
                    success, err = await self.update_and_sync_giveaway(
                        message_id,
                        guild_id=giveaway['guild_id'],
                        ended=1,
                        winners=[],
                        status="ended",
                        status_note="Không có người tham gia hợp lệ (người tham gia đã rời server)."
                    )
                    if not success:
                        logger.error(f"Failed to sync ended giveaway {message_id} (no valid winners): {err}")
                        try:
                            self.economy.cur.execute("UPDATE giveaways SET ended = 0 WHERE id = ? AND ended = 3", (message_id,))
                            self.economy.conn.commit()
                        except Exception:
                            pass
                        return
                    await channel.send(f" Không có ai thắng giveaway **{prize}** vì tất cả người tham gia đã rời server.")
                    return

                # Save original winners, reroll history, and eligible_candidates snapshot
                extra_reqs_raw = giveaway.get('extra_reqs') or {}
                extra_reqs = json.loads(extra_reqs_raw) if isinstance(extra_reqs_raw, str) else (extra_reqs_raw or {})
                extra_reqs["original_winners"] = winners
                extra_reqs["reroll_history"] = []
                extra_reqs["eligible_candidates"] = valid_candidates

                self.update_participants(message_id, valid_candidates)
                success, err = await self.update_and_sync_giveaway(
                    message_id,
                    guild_id=giveaway['guild_id'],
                    ended=1,
                    winners=winners,
                    extra_reqs=extra_reqs,
                    status="ended"
                )
                if not success:
                    logger.error(f"Failed to sync ended giveaway {message_id}: {err}")
                    try:
                        self.economy.cur.execute("UPDATE giveaways SET ended = 0 WHERE id = ? AND ended = 3", (message_id,))
                        self.economy.conn.commit()
                    except Exception:
                        pass
                    return

                winners_mentions = ", ".join(f"<@{w_id}>" for w_id in winners)
                await channel.send(f" <a:wing:1526230985987981393>*Chúc mừng {winners_mentions} đã thắng giải **{prize}**<a:key:1526234974150459593> Liên hệ <@{host_id}> để nhận thưởng.*")
        finally:
            if message_id in self.end_locks and not lock.locked():
                self.end_locks.pop(message_id, None)
            self.join_locks.pop(message_id, None)

    @commands.command(name="sync_giveaway", hidden=True)
    @commands.is_owner()
    async def sync_giveaway(self, ctx: commands.Context):
        """Owner-only command to sync command tree if needed."""
        await self.bot.tree.sync()
        await ctx.send("Synced giveaway slash/hybrid commands!")

    @tasks.loop(seconds=5)
    async def giveaway_check_loop(self):
        try:
            now = int(time.time())
            # Auto-recover giveaways stuck in ended = 3 for more than 60 seconds
            self.economy.cur.execute("UPDATE giveaways SET ended = 0 WHERE ended = 3 AND (? - updated_at > 60)", (now,))
            self.economy.conn.commit()

            self.economy.cur.execute("SELECT id FROM giveaways WHERE ended = 0 AND ends_at <= ?", (now,))
            rows = self.economy.cur.fetchall()
            for row in rows:
                msg_id = row[0]
                await self.end_giveaway(msg_id)
        except Exception as e:
            logger.error(f"Error in giveaway_check_loop: {e}", exc_info=True)

    @giveaway_check_loop.before_loop
    async def before_giveaway_check_loop(self):
        if hasattr(self.bot, "wait_until_ready"):
            try:
                res = self.bot.wait_until_ready()
                if inspect.isawaitable(res):
                    await res
            except Exception:
                pass


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
