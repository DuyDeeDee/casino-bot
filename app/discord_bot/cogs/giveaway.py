import asyncio
import inspect
import json
import logging
import re
import secrets
import time
from typing import Optional, Union

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
    
    # 1. Mention format <@&123456> or <@123456>
    match = re.match(r"<@&?(\d+)>", text)
    if match:
        return int(match.group(1))
    
    # 2. Pure digits
    if text.isdigit():
        return int(text)
    
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


_secure_rng = secrets.SystemRandom()


def is_giveaway_emoji(emoji: Union[discord.PartialEmoji, discord.Emoji, str]) -> bool:
    """Checks if an emoji matches supported giveaway entry reactions."""
    if isinstance(emoji, str):
        return emoji == "🎉"
    if getattr(emoji, "is_custom_emoji", lambda: False)():
        return emoji.id in (1544913759297085440, 1526238405061640272)
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


# ==============================================================================
# UI MODALS FOR INTERACTIVE GIVEAWAY EDITOR (MIMU STYLE)
# ==============================================================================

class GiveawayBasicInfoModal(discord.ui.Modal, title="🎨 Thông Tin Cơ Bản"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.custom_title = discord.ui.TextInput(
            label="Tiêu đề Embed",
            placeholder="VD: 🎉 EVENT ĐẶC BIỆT 🎉",
            default=cfg.get("title", ""),
            max_length=256,
            required=False
        )
        self.color_input = discord.ui.TextInput(
            label="Màu viền Embed (Hex hoặc Tên màu)",
            placeholder="VD: #FFD700, gold, purple, red, cyan",
            default=cfg.get("color", ""),
            max_length=25,
            required=False
        )
        self.ping_content = discord.ui.TextInput(
            label="Nội dung Ping / Header trên Embed",
            placeholder="VD: @everyone hoặc # 🎁 GIVEAWAY {guild_name}",
            default=cfg.get("ping_content", ""),
            max_length=200,
            required=False
        )
        self.custom_desc = discord.ui.TextInput(
            label="Bố Cục Mô Tả / Ghi Chú (Placeholders)",
            style=discord.TextStyle.paragraph,
            placeholder="Dùng biến: {prize}, {host}, {winner_count}, {ends_at}, {prize_bonus}... Hoặc ghi chú.",
            default=cfg.get("custom_desc", ""),
            max_length=1500,
            required=False
        )

        self.add_item(self.custom_title)
        self.add_item(self.color_input)
        self.add_item(self.ping_content)
        self.add_item(self.custom_desc)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["title"] = self.custom_title.value.strip() or None
        cfg["color"] = self.color_input.value.strip() or None
        cfg["ping_content"] = self.ping_content.value.strip() or None
        cfg["custom_desc"] = self.custom_desc.value.strip() or None

        self.editor_view.giveaway['embed_config'] = cfg
        await self.editor_view.refresh_preview(interaction)


class GiveawayAuthorModal(discord.ui.Modal, title="👤 Chỉnh Sửa Author"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.author_name = discord.ui.TextInput(
            label="Tên Author",
            placeholder="VD: 👑 Host: {host_name} (để trống để ẩn)",
            default=cfg.get("author_name", ""),
            max_length=100,
            required=False
        )
        self.author_icon = discord.ui.TextInput(
            label="Author Icon URL",
            placeholder="Link ảnh hoặc {host_avatar}",
            default=cfg.get("author_icon", ""),
            max_length=400,
            required=False
        )
        self.author_url = discord.ui.TextInput(
            label="Author URL (Link khi bấm)",
            placeholder="https://...",
            default=cfg.get("author_url", ""),
            max_length=400,
            required=False
        )

        self.add_item(self.author_name)
        self.add_item(self.author_icon)
        self.add_item(self.author_url)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["author_name"] = self.author_name.value.strip() or None
        cfg["author_icon"] = self.author_icon.value.strip() or None
        cfg["author_url"] = self.author_url.value.strip() or None

        self.editor_view.giveaway['embed_config'] = cfg
        await self.editor_view.refresh_preview(interaction)


class GiveawayFooterModal(discord.ui.Modal, title="📄 Chỉnh Sửa Footer"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.footer_text = discord.ui.TextInput(
            label="Chân trang (Footer Text)",
            placeholder="VD: Sylus Meow • Giveaway System",
            default=cfg.get("footer_text", ""),
            max_length=150,
            required=False
        )
        self.footer_icon = discord.ui.TextInput(
            label="Footer Icon URL",
            placeholder="Link icon nhỏ góc footer",
            default=cfg.get("footer_icon", ""),
            max_length=400,
            required=False
        )

        self.add_item(self.footer_text)
        self.add_item(self.footer_icon)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["footer_text"] = self.footer_text.value.strip() or None
        cfg["footer_icon"] = self.footer_icon.value.strip() or None

        self.editor_view.giveaway['embed_config'] = cfg
        await self.editor_view.refresh_preview(interaction)


class GiveawayImagesModal(discord.ui.Modal, title="🖼️ Chỉnh Sửa Banner & Thumbnail"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.banner_url = discord.ui.TextInput(
            label="Banner Image URL (Ảnh lớn thân embed)",
            placeholder="Link ảnh https://... (để trống để xóa)",
            default=cfg.get("banner", ""),
            max_length=500,
            required=False
        )
        self.thumbnail_url = discord.ui.TextInput(
            label="Thumbnail URL (Ảnh nhỏ góc phải)",
            placeholder="host (mặc định), server, none, hoặc link ảnh",
            default=cfg.get("thumbnail", "host"),
            max_length=500,
            required=False
        )

        self.add_item(self.banner_url)
        self.add_item(self.thumbnail_url)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["banner"] = self.banner_url.value.strip() or None
        cfg["thumbnail"] = self.thumbnail_url.value.strip() or "host"

        self.editor_view.giveaway['embed_config'] = cfg
        await self.editor_view.refresh_preview(interaction)


class GiveawayPrizeTimeModal(discord.ui.Modal, title="⚙️ Giải Thưởng & Thời Gian"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        ga = self.editor_view.giveaway

        self.prize_input = discord.ui.TextInput(
            label="Tên Phần Thưởng",
            placeholder="Nhập giải thưởng mới...",
            default=str(ga.get("prize", "")),
            max_length=256,
            required=True
        )
        self.winner_count_input = discord.ui.TextInput(
            label="Số Người Thắng",
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
        try:
            win_count = int(self.winner_count_input.value.strip())
            if win_count <= 0:
                win_count = 1
        except ValueError:
            win_count = 1

        self.editor_view.giveaway['prize'] = prize_val
        self.editor_view.giveaway['winner_count'] = win_count

        time_adj = self.time_adjust_input.value.strip().lower()
        if time_adj:
            now = int(time.time())
            if time_adj.startswith("+"):
                sec = parse_time(time_adj[1:])
                if sec:
                    self.editor_view.giveaway['ends_at'] = max(now + 10, self.editor_view.giveaway['ends_at'] + sec)
            elif time_adj.startswith("-"):
                sec = parse_time(time_adj[1:])
                if sec:
                    self.editor_view.giveaway['ends_at'] = max(now + 10, self.editor_view.giveaway['ends_at'] - sec)
            else:
                sec = parse_time(time_adj)
                if sec:
                    self.editor_view.giveaway['ends_at'] = now + sec

        await self.editor_view.refresh_preview(interaction)


class GiveawayRequirementsModal(discord.ui.Modal, title="🔒 Cài Đặt Điều Kiện & Role"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        ga = self.editor_view.giveaway
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
            placeholder="VD: @Member, @VIP hoặc 123456789 (cách nhau dấu phẩy hoặc khoảng trắng)",
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
        req_raw = self.required_roles_input.value.strip()
        req_list = []
        if req_raw:
            tokens = [t.strip() for t in re.split(r"[,;\n]+|\s+", req_raw) if t.strip()]
            for tok in tokens:
                rid = resolve_role_input(interaction.guild, tok)
                if rid and rid not in req_list:
                    req_list.append(rid)

        bonus_raw = self.bonus_roles_input.value.strip()
        bonus_dict = {}
        if bonus_raw:
            tokens = [t.strip() for t in re.split(r"[,;\n]+", bonus_raw) if t.strip()]
            for tok in tokens:
                if ":" in tok:
                    parts = tok.split(":", 1)
                    rid = resolve_role_input(interaction.guild, parts[0].strip())
                    multiplier_str = parts[1].strip().lstrip("+")
                    if rid and multiplier_str.isdigit():
                        bonus_dict[rid] = int(multiplier_str)
                else:
                    rid = resolve_role_input(interaction.guild, tok)
                    if rid:
                        bonus_dict[rid] = 1

        if req_list and bonus_dict:
            await interaction.response.send_message(
                "❌ Bạn không thể cấu hình giới hạn role và cộng lượt cùng lúc trong một giveaway!",
                ephemeral=True
            )
            return

        self.editor_view.giveaway['required_roles'] = req_list
        self.editor_view.giveaway['bonus_roles'] = bonus_dict

        await self.editor_view.refresh_preview(interaction)


class GiveawayPrizeBonusModal(discord.ui.Modal, title="🎁 Đặc Quyền Bonus Phần Thưởng"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        ga = self.editor_view.giveaway
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
        raw = self.bonus_prizes_input.value.strip()
        parsed_dict = {}
        if raw:
            for line in raw.split("\n"):
                line = line.strip()
                if not line or ":" not in line:
                    continue
                parts = line.split(":", 1)
                role_query = parts[0].strip()
                bonus_desc = parts[1].strip()
                rid = resolve_role_input(interaction.guild, role_query)
                if rid and bonus_desc:
                    parsed_dict[str(rid)] = bonus_desc

        self.editor_view.giveaway['role_bonus_prizes'] = parsed_dict
        await self.editor_view.refresh_preview(interaction)


class GiveawayStateConfigModal(discord.ui.Modal, title="⚙️ Tiêu Đề & Mô Tả Theo Trạng Thái"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.active_title = discord.ui.TextInput(
            label="Tiêu Đề Đang Chạy (Active Title)",
            placeholder="Để trống để dùng tiêu đề chung...",
            default=cfg.get("active_title", "") or "",
            max_length=256,
            required=False
        )
        self.ended_title = discord.ui.TextInput(
            label="Tiêu Đề Kết Thúc (Ended Title)",
            placeholder="VD: 🎉 Giveaway Kết Thúc 🎉",
            default=cfg.get("ended_title", "") or "",
            max_length=256,
            required=False
        )
        self.ended_desc = discord.ui.TextInput(
            label="Mô Tả Kết Thúc (Ended Desc)",
            style=discord.TextStyle.paragraph,
            placeholder="Dùng biến: {prize}, {winners}, {result}, {status_note}... Để trống dùng layout chuẩn.",
            default=cfg.get("ended_desc", "") or "",
            max_length=1500,
            required=False
        )
        self.cancelled_title = discord.ui.TextInput(
            label="Tiêu Đề Hủy (Cancelled Title)",
            placeholder="VD: 🛑 Giveaway Đã Bị Hủy 🛑",
            default=cfg.get("cancelled_title", "") or "",
            max_length=256,
            required=False
        )
        self.rerolled_title = discord.ui.TextInput(
            label="Tiêu Đề Reroll (Rerolled Title)",
            placeholder="VD: 🔄 Giveaway Đã Reroll Kết Quả 🔄",
            default=cfg.get("rerolled_title", "") or "",
            max_length=256,
            required=False
        )

        self.add_item(self.active_title)
        self.add_item(self.ended_title)
        self.add_item(self.ended_desc)
        self.add_item(self.cancelled_title)
        self.add_item(self.rerolled_title)

    async def on_submit(self, interaction: discord.Interaction):
        cfg = self.editor_view.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        cfg["active_title"] = self.active_title.value.strip() or None
        cfg["ended_title"] = self.ended_title.value.strip() or None
        cfg["ended_desc"] = self.ended_desc.value.strip() or None
        cfg["cancelled_title"] = self.cancelled_title.value.strip() or None
        cfg["rerolled_title"] = self.rerolled_title.value.strip() or None

        self.editor_view.giveaway['embed_config'] = cfg
        await self.editor_view.refresh_preview(interaction)


# ==============================================================================
# INTERACTIVE GIVEAWAY EDITOR VIEW
# ==============================================================================

class GiveawayEditorView(discord.ui.View):
    def __init__(self, cog, giveaway: dict, user: discord.Member, guild: discord.Guild):
        super().__init__(timeout=300)
        self.cog = cog
        self.giveaway = giveaway
        self.user = user
        self.guild = guild
        self.preview_mode = "active"
        self.loaded_version = giveaway.get('version', 0)
        self.initial_ended = giveaway.get('ended', 0)

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
            participants = self.giveaway.get('participants') or {}
            if isinstance(participants, str):
                participants = json.loads(participants)
            p_count = len(participants) if isinstance(participants, dict) else (len(participants) if isinstance(participants, list) else 0)
        except Exception:
            p_count = 0

        sample_winners = [self.user.id] if self.preview_mode in ("ended", "rerolled") else None
        sample_note = "Giveaway này đã bị huỷ bởi Host." if self.preview_mode == "cancelled" else None

        return self.cog.build_giveaway_embed(
            self.giveaway,
            status=self.preview_mode,
            participants_count=p_count,
            winners=sample_winners,
            status_note=sample_note
        )

    def _update_preview_button_styles(self):
        self.btn_preview_active.style = discord.ButtonStyle.primary if self.preview_mode == "active" else discord.ButtonStyle.secondary
        self.btn_preview_ended.style = discord.ButtonStyle.primary if self.preview_mode == "ended" else discord.ButtonStyle.secondary
        self.btn_preview_cancelled.style = discord.ButtonStyle.primary if self.preview_mode == "cancelled" else discord.ButtonStyle.secondary
        self.btn_preview_rerolled.style = discord.ButtonStyle.primary if self.preview_mode == "rerolled" else discord.ButtonStyle.secondary

    async def refresh_preview(self, interaction: discord.Interaction):
        embed = self.build_preview_embed()
        cfg = self.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        ping_header = cfg.get("ping_content") or f"# <a:w1:1526231439425667093> Giveaway {self.guild.name} <a:w2:1526231455422877798>"
        is_template = (self.giveaway.get('id') == 0)
        mode_title = "THIẾT KẾ MẪU EMBED GIVEAWAY TOÀN SERVER" if is_template else f"BẢNG ĐIỀU KHIỂN CHỈNH SỬA GIVEAWAY (ID: `{self.giveaway.get('id')}`)"
        preview_state_label = {
            "active": "🟢 ĐANG CHẠY",
            "ended": "🏁 ĐÃ KẾT THÚC",
            "cancelled": "🛑 ĐÃ HỦY",
            "rerolled": "🔄 REROLL"
        }.get(self.preview_mode, "🟢 ĐANG CHẠY")

        await interaction.response.edit_message(
            content=f"🛠️ **[LIVE PREVIEW - {preview_state_label} - {mode_title}]**\n{ping_header}",
            embed=embed,
            view=self
        )

    @discord.ui.button(label="Basic Info", style=discord.ButtonStyle.secondary, emoji="🎨", row=0)
    async def btn_basic_info(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayBasicInfoModal(self))

    @discord.ui.button(label="Author", style=discord.ButtonStyle.secondary, emoji="👤", row=0)
    async def btn_author(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayAuthorModal(self))

    @discord.ui.button(label="Footer", style=discord.ButtonStyle.secondary, emoji="📄", row=0)
    async def btn_footer(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayFooterModal(self))

    @discord.ui.button(label="Images", style=discord.ButtonStyle.secondary, emoji="🖼️", row=0)
    async def btn_images(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayImagesModal(self))

    @discord.ui.button(label="Prize & Time", style=discord.ButtonStyle.secondary, emoji="⚙️", row=1)
    async def btn_prize_time(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayPrizeTimeModal(self))

    @discord.ui.button(label="Requirements", style=discord.ButtonStyle.secondary, emoji="🔒", row=1)
    async def btn_requirements(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayRequirementsModal(self))

    @discord.ui.button(label="Prize Bonus", style=discord.ButtonStyle.secondary, emoji="🎁", row=1)
    async def btn_prize_bonus(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayPrizeBonusModal(self))

    @discord.ui.button(label="Trạng Thái", style=discord.ButtonStyle.secondary, emoji="📑", row=1)
    async def btn_state_config(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(GiveawayStateConfigModal(self))

    @discord.ui.button(label="Lưu Mẫu Server", style=discord.ButtonStyle.secondary, emoji="💾", row=2)
    async def btn_save_default(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.cog.can_manage_server_template(interaction.user, self.guild):
            await interaction.response.send_message(
                "❌ Bạn không có quyền quản lý Mẫu Giveaway của Server. (Yêu cầu quyền Administrator, Quản lý Server hoặc Role `Giveaway Manager`)",
                ephemeral=True
            )
            return

        cfg = self.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        save_ok = self.cog.save_template(self.guild.id, "default", cfg, updated_by=interaction.user.id)
        if not save_ok:
            await interaction.response.send_message("❌ Lỗi khi lưu Mẫu Giveaway vào cơ sở dữ liệu.", ephemeral=True)
            return

        embed = self.build_preview_embed()
        ping_header = cfg.get("ping_content") or f"# <a:w1:1526231439425667093> Giveaway {self.guild.name} <a:w2:1526231455422877798>"
        if self.giveaway.get('id', 0) == 0:
            await interaction.response.edit_message(
                content=f"💾 **[ĐÃ LƯU MẪU GIVEAWAY CHO TOÀN SERVER!]**\n{ping_header}\n\n*(Mẫu thiết kế này sẽ tự động áp dụng cho **tất cả Giveaway mới** được tạo trong server!)*",
                embed=embed
            )
        else:
            await interaction.response.send_message(
                "💾 **Đã lưu cấu hình làm Mẫu Mặc Định cho toàn Server!**\n*(Lưu ý: Giveaway đang chạy này chưa bị thay đổi. Nhấn nút 'Áp Dụng Cho GA Này' nếu muốn cập nhật tin nhắn hiện tại).* ",
                ephemeral=True
            )

    @discord.ui.button(label="Áp Dụng Cho GA Này", style=discord.ButtonStyle.primary, emoji="✅", row=2)
    async def btn_apply_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = self.giveaway.get('id', 0)
        if msg_id == 0:
            await interaction.response.send_message(
                "❌ Bạn đang ở chế độ chỉnh sửa Mẫu Server (không có Giveaway cụ thể nào). Hãy nhấn nút **'Lưu Mẫu Server'** để lưu lại mẫu thiết kế!",
                ephemeral=True
            )
            return

        prize = self.giveaway['prize']
        winner_count = self.giveaway['winner_count']
        ends_at = self.giveaway['ends_at']
        required_roles = self.giveaway.get('required_roles', [])
        bonus_roles = self.giveaway.get('bonus_roles', {})
        embed_config = self.giveaway.get('embed_config', {})
        role_bonus_prizes = self.giveaway.get('role_bonus_prizes', {})

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

        # Single pipeline update & sync (giveaway only, does not alter server template)
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

        # Disable buttons
        for item in self.children:
            item.disabled = True

        embed = self.build_preview_embed()
        await interaction.response.edit_message(
            content=f"✅ **Đã áp dụng và cập nhật thành công tin nhắn Giveaway trên kênh <#{self.giveaway['channel_id']}>!** *(Không thay đổi Mẫu Mặc Định của Server)*",
            embed=embed,
            view=self
        )

    @discord.ui.button(label="Lưu & Áp Dụng Cả 2", style=discord.ButtonStyle.success, emoji="🌟", row=2)
    async def btn_save_and_apply(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = self.giveaway.get('id', 0)
        if msg_id == 0:
            await self.btn_save_default.callback(interaction)
            return

        # Check server template management permission first
        if not self.cog.can_manage_server_template(interaction.user, self.guild):
            await interaction.response.send_message(
                "❌ Bạn không có quyền lưu Mẫu Giveaway của Server. (Yêu cầu quyền Administrator, Quản lý Server hoặc Role `Giveaway Manager`).\n👉 Bạn vẫn có thể nhấn nút **'Áp Dụng Cho GA Này'** để cập nhật riêng cho Giveaway hiện tại.",
                ephemeral=True
            )
            return

        prize = self.giveaway['prize']
        winner_count = self.giveaway['winner_count']
        ends_at = self.giveaway['ends_at']
        required_roles = self.giveaway.get('required_roles', [])
        bonus_roles = self.giveaway.get('bonus_roles', {})
        embed_config = self.giveaway.get('embed_config', {})
        role_bonus_prizes = self.giveaway.get('role_bonus_prizes', {})

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

        # 1. Update & Sync Giveaway first
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

        # 2. If giveaway sync succeeded, save Server Template
        save_ok = self.cog.save_template(self.guild.id, "default", embed_config, updated_by=interaction.user.id)
        if not save_ok:
            await interaction.response.send_message("⚠️ Đã cập nhật Giveaway nhưng không thể lưu làm Mẫu Server.", ephemeral=True)
            return

        # Disable buttons
        for item in self.children:
            item.disabled = True

        embed = self.build_preview_embed()
        await interaction.response.edit_message(
            content=f"🌟 **Đã lưu làm Mẫu Mặc Định của Server VÀ cập nhật thành công tin nhắn Giveaway trên kênh <#{self.giveaway['channel_id']}>!**",
            embed=embed,
            view=self
        )

    @discord.ui.button(label="🟢 Đang chạy", style=discord.ButtonStyle.primary, row=3)
    async def btn_preview_active(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.preview_mode = "active"
        self._update_preview_button_styles()
        await self.refresh_preview(interaction)

    @discord.ui.button(label="🏁 Kết thúc", style=discord.ButtonStyle.secondary, row=3)
    async def btn_preview_ended(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.preview_mode = "ended"
        self._update_preview_button_styles()
        await self.refresh_preview(interaction)

    @discord.ui.button(label="🛑 Đã hủy", style=discord.ButtonStyle.secondary, row=3)
    async def btn_preview_cancelled(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.preview_mode = "cancelled"
        self._update_preview_button_styles()
        await self.refresh_preview(interaction)

    @discord.ui.button(label="🔄 Reroll", style=discord.ButtonStyle.secondary, row=3)
    async def btn_preview_rerolled(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.preview_mode = "rerolled"
        self._update_preview_button_styles()
        await self.refresh_preview(interaction)


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
        cfg = self.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        ping_header = cfg.get("ping_content") or f"# <a:w1:1526231439425667093> Giveaway {self.guild.name} <a:w2:1526231455422877798>"

        is_template = (self.giveaway.get('id', 0) == 0)
        mode_title = "THIẾT KẾ MẪU EMBED GIVEAWAY TOÀN SERVER" if is_template else f"BẢNG ĐIỀU KHIỂN CHỈNH SỬA GIVEAWAY (ID: `{self.giveaway.get('id')}`)"

        await interaction.response.send_message(
            content=f"🛠️ **[LIVE PREVIEW - {mode_title}]**\n{ping_header}",
            embed=preview_embed,
            view=editor_view,
            ephemeral=True
        )


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
            winners_mentions = "Chưa có" if status == "active" else "Không có"

        status_names = {
            "active": "Đang diễn ra",
            "ended": "Đã kết thúc",
            "cancelled": "Đã bị huỷ",
            "rerolled": "Đã quay lại kết quả"
        }
        status_display = status_names.get(status, "Đang diễn ra")

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
            "rerolled": "🎉 GIVEAWAY ĐÃ QUAY LẠI KẾT QUẢ 🎉"
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

        # Description resolution:
        # 1. State-specific desc ({status}_desc)
        # 2. General custom_desc
        state_desc = embed_cfg.get(f"{status}_desc")
        general_desc = embed_cfg.get('custom_desc')
        template_to_use = state_desc if state_desc is not None else general_desc

        has_placeholders = template_to_use and any(
            ph in template_to_use for ph in [
                "{prize}", "{host}", "{winner_count}", "{win}", "{ends_at}", "{end}",
                "{role_req}", "{roles}", "{bonus_roles}", "{prize_bonus}", "{winners}",
                "{result}", "{status}", "{status_note}", "{participants}", "{reroll_history}"
            ]
        )

        if state_desc is not None or has_placeholders:
            embed.description = self.format_embed_description(
                template_to_use or "",
                giveaway,
                participants_count=participants_count,
                status=status,
                winners=winners,
                status_note=status_note
            )
        else:
            # Default structured layout
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
            elif status in ("ended", "rerolled"):
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

            if general_desc:
                desc_lines.append(f"\n📝 *Ghi chú:* {general_desc}")

            embed.description = "\n".join(desc_lines)

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

        # Perform DB update
        db_success = self.update_giveaway_full(message_id, expected_version=expected_version, **changes)
        if not db_success:
            return False, "Lỗi khi cập nhật cơ sở dữ liệu (xung đột phiên bản hoặc dữ liệu không hợp lệ)."

        updated = self.get_giveaway(message_id, guild_id=guild_id)
        if not updated:
            return False, "Không thể tải lại dữ liệu giveaway sau khi cập nhật."

        # Determine status string
        if not status:
            ended_code = updated.get('ended', 0)
            if ended_code == 0 or ended_code == 3:
                status = "active"
            elif ended_code == 1:
                status = "ended"
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
            self._rollback_giveaway_db(message_id, previous_state)
            return False, "Bot không tìm thấy server của giveaway này."

        channel = guild.get_channel(updated['channel_id'])
        if not channel:
            self._rollback_giveaway_db(message_id, previous_state)
            return False, "Bot không tìm thấy kênh của giveaway này."

        try:
            message = await channel.fetch_message(message_id)
        except Exception as e:
            logger.warning(f"Could not fetch message {message_id} to sync: {e}")
            self._rollback_giveaway_db(message_id, previous_state)
            return False, f"Không thể lấy tin nhắn Discord: {e}"

        try:
            if status == "active" and updated['ended'] == 0:
                cfg_raw = updated.get('embed_config') or {}
                cfg = json.loads(cfg_raw) if isinstance(cfg_raw, str) else (cfg_raw or {})
                ping_content = cfg.get('ping_content') or f"# <a:w1:1526231439425667093> Giveaway {guild.name} <a:w2:1526231455422877798>"
                await message.edit(content=ping_content, embed=embed, allowed_mentions=discord.AllowedMentions.none())
            else:
                await message.edit(embed=embed, view=None, allowed_mentions=discord.AllowedMentions.none())
        except Exception as e:
            logger.error(f"Failed to edit message {message_id} on Discord: {e}")
            self._rollback_giveaway_db(message_id, previous_state)
            return False, f"Lỗi cập nhật tin nhắn Discord: {e}"

        return True, None

    def _rollback_giveaway_db(self, msg_id: int, snapshot: dict):
        """Rolls back the database state of a giveaway to a previous snapshot."""
        try:
            self.economy.cur.execute(
                """UPDATE giveaways SET
                       prize = ?, winner_count = ?, ends_at = ?, ended = ?,
                       required_roles = ?, bonus_roles = ?, embed_config = ?,
                       extra_reqs = ?, role_bonus_prizes = ?, winners = ?,
                       participants = ?, updated_at = ?, version = ?
                   WHERE id = ?""",
                (
                    snapshot.get('prize'),
                    snapshot.get('winner_count'),
                    snapshot.get('ends_at'),
                    snapshot.get('ended'),
                    json.dumps(snapshot.get('required_roles')) if isinstance(snapshot.get('required_roles'), (list, dict)) else snapshot.get('required_roles'),
                    json.dumps(snapshot.get('bonus_roles')) if isinstance(snapshot.get('bonus_roles'), dict) else snapshot.get('bonus_roles'),
                    json.dumps(snapshot.get('embed_config')) if isinstance(snapshot.get('embed_config'), dict) else snapshot.get('embed_config'),
                    json.dumps(snapshot.get('extra_reqs')) if isinstance(snapshot.get('extra_reqs'), dict) else snapshot.get('extra_reqs'),
                    json.dumps(snapshot.get('role_bonus_prizes')) if isinstance(snapshot.get('role_bonus_prizes'), dict) else snapshot.get('role_bonus_prizes'),
                    json.dumps(snapshot.get('winners')) if isinstance(snapshot.get('winners'), list) else snapshot.get('winners'),
                    json.dumps(snapshot.get('participants')) if isinstance(snapshot.get('participants'), dict) else snapshot.get('participants'),
                    snapshot.get('updated_at', 0),
                    snapshot.get('version', 0),
                    msg_id
                )
            )
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to rollback giveaway {msg_id}: {e}", exc_info=True)

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

        ping_raw = embed_config.get("ping_content", "")
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

        ping_header = embed_config.get("ping_content") or f"# <a:w1:1526231439425667093> Giveaway {ctx.guild.name} <a:w2:1526231455422877798>"

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
                    success, err = await self.update_and_sync_giveaway(
                        message_id,
                        guild_id=giveaway['guild_id'],
                        ended=1,
                        winners=[],
                        status="ended",
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
                    await channel.send(f" Không có ai tham gia giveaway **{prize}**.")
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
