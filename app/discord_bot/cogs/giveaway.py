import asyncio
import json
import logging
import re
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
        "black": discord.Color.from_rgb(0, 0, 0),
    }
    if val in color_map:
        return color_map[val]
    clean_hex = val
    if clean_hex.startswith("#"):
        clean_hex = clean_hex[1:]
    elif clean_hex.startswith("0x"):
        clean_hex = clean_hex[2:]

    if len(clean_hex) in (6, 8):
        try:
            return discord.Color(int(clean_hex[:6], 16))
        except ValueError:
            pass
    return None


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
            label="Mô tả phụ / Ghi chú của Host",
            style=discord.TextStyle.paragraph,
            placeholder="Nhập ghi chú thể lệ, nhà tài trợ, lời nhắn...",
            default=cfg.get("custom_desc", ""),
            max_length=1000,
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

        req_roles = ga.get("required_roles") or []
        if isinstance(req_roles, str):
            try:
                req_roles = json.loads(req_roles)
            except Exception:
                req_roles = []

        req_str = " ".join(str(r) for r in req_roles)

        bonus_roles = ga.get("bonus_roles") or {}
        if isinstance(bonus_roles, str):
            try:
                bonus_roles = json.loads(bonus_roles)
            except Exception:
                bonus_roles = {}

        bonus_str = " ".join(f"{r}:{extra}" for r, extra in bonus_roles.items())

        self.required_roles_input = discord.ui.TextInput(
            label="Role Bắt Buộc (@Role hoặc Role ID)",
            placeholder="VD: 123456789 987654321 (cách nhau khoảng trắng)",
            default=req_str,
            max_length=300,
            required=False
        )
        self.bonus_roles_input = discord.ui.TextInput(
            label="Role Cộng Vé Bonus (RoleID:Vé)",
            placeholder="VD: 123456789:2 987654321:3",
            default=bonus_str,
            max_length=300,
            required=False
        )

        self.add_item(self.required_roles_input)
        self.add_item(self.bonus_roles_input)

    async def on_submit(self, interaction: discord.Interaction):
        req_tokens = self.required_roles_input.value.strip().split()
        req_list = []
        for tok in req_tokens:
            rid = parse_role_mention(tok)
            if rid:
                req_list.append(rid)

        bonus_tokens = self.bonus_roles_input.value.strip().split()
        bonus_dict = {}
        for tok in bonus_tokens:
            if ":" in tok:
                parts = tok.split(":")
                rid = parse_role_mention(parts[0])
                if rid and parts[1].isdigit():
                    bonus_dict[rid] = int(parts[1])
            else:
                rid = parse_role_mention(tok)
                if rid:
                    bonus_dict[rid] = 1

        self.editor_view.giveaway['required_roles'] = req_list
        self.editor_view.giveaway['bonus_roles'] = bonus_dict

        await self.editor_view.refresh_preview(interaction)


class GiveawayPrizeBonusModal(discord.ui.Modal, title="🎁 Đặc Quyền Bonus Phần Thưởng"):
    def __init__(self, editor_view: "GiveawayEditorView"):
        super().__init__()
        self.editor_view = editor_view
        ga = self.editor_view.giveaway

        role_prizes = ga.get("role_bonus_prizes") or {}
        if isinstance(role_prizes, str):
            try:
                role_prizes = json.loads(role_prizes)
            except Exception:
                role_prizes = {}

        lines = []
        for rid_str, prize_text in role_prizes.items():
            lines.append(f"{rid_str}: {prize_text}")
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
                rid = parse_role_mention(parts[0].strip())
                bonus_desc = parts[1].strip()
                if rid and bonus_desc:
                    parsed_dict[str(rid)] = bonus_desc

        self.editor_view.giveaway['role_bonus_prizes'] = parsed_dict
        await self.editor_view.refresh_preview(interaction)


# ==============================================================================
# INTERACTIVE GIVEAWAY EDITOR VIEW (ACTION ROW BUTTONS)
# ==============================================================================

class GiveawayEditorView(discord.ui.View):
    def __init__(self, cog: "Giveaway", giveaway: dict, user: discord.User, guild: discord.Guild):
        super().__init__(timeout=600)
        self.cog = cog
        self.giveaway = giveaway.copy()
        self.user = user
        self.guild = guild

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
        return self.cog.build_active_embed(self.giveaway, p_count)

    async def refresh_preview(self, interaction: discord.Interaction):
        embed = self.build_preview_embed()
        cfg = self.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}
        ping_header = cfg.get("ping_content") or f"# <a:w1:1526231439425667093> Giveaway {self.guild.name} <a:w2:1526231455422877798>"

        await interaction.response.edit_message(
            content=f"🛠️ **[LIVE PREVIEW - BẢNG ĐIỀU KHIỂN CHỈNH SỬA GIVEAWAY]**\n{ping_header}",
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

    @discord.ui.button(label="Save as Default", style=discord.ButtonStyle.success, emoji="💾", row=2)
    async def btn_save_default(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = self.giveaway.get('embed_config') or {}
        if isinstance(cfg, str):
            try:
                cfg = json.loads(cfg)
            except Exception:
                cfg = {}

        self.cog.save_template(self.guild.id, self.user.id, "default", cfg)
        await interaction.response.send_message(
            "💾 **Đã lưu thành công phong cách này làm mẫu mặc định của bạn!**\n"
            "👉 Từ nay, mỗi khi bạn tạo Giveaway mới trong Server, bot sẽ **tự động áp dụng** giao diện này mà không cần chỉnh lại từ đầu.",
            ephemeral=True
        )

    @discord.ui.button(label="Apply & Sync", style=discord.ButtonStyle.primary, emoji="✅", row=2)
    async def btn_apply_sync(self, interaction: discord.Interaction, button: discord.ui.Button):
        msg_id = self.giveaway['id']
        prize = self.giveaway['prize']
        winner_count = self.giveaway['winner_count']
        ends_at = self.giveaway['ends_at']
        required_roles = self.giveaway.get('required_roles', [])
        bonus_roles = self.giveaway.get('bonus_roles', {})
        embed_config = self.giveaway.get('embed_config', {})
        role_bonus_prizes = self.giveaway.get('role_bonus_prizes', {})

        self.cog.update_giveaway_full(
            msg_id=msg_id,
            prize=prize,
            winner_count=winner_count,
            ends_at=ends_at,
            required_roles=required_roles,
            bonus_roles=bonus_roles,
            embed_config=embed_config,
            role_bonus_prizes=role_bonus_prizes
        )

        # Sync live to message
        await self.cog.sync_giveaway_message(msg_id)

        # Disable buttons
        for item in self.children:
            item.disabled = True

        embed = self.build_preview_embed()
        await interaction.response.edit_message(
            content=f"✅ **Đã áp dụng và cập nhật thành công tin nhắn Giveaway trên kênh <#{self.giveaway['channel_id']}>!**",
            embed=embed,
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

    @discord.ui.button(label="🛠️ Mở Trình Chỉnh Sửa Giveaway (Riêng Tư)", style=discord.ButtonStyle.primary)
    async def open_editor_btn(self, interaction: discord.Interaction, button: discord.ui.Button):
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

        await interaction.response.send_message(
            content=f"🛠️ **[LIVE PREVIEW - BẢNG ĐIỀU KHIỂN CHỈNH SỬA GIVEAWAY]**\n{ping_header}",
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
        self.pending_embed_updates = {}
        self.update_tasks = {}
        self.init_db()
        self.giveaway_check_loop.start()

    def cog_unload(self) -> None:
        self.giveaway_check_loop.cancel()
        for task in self.update_tasks.values():
            task.cancel()

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
            self.economy.conn.commit()

            # Templates table for saving default preferences permanently
            self.economy.cur.execute("""
                CREATE TABLE IF NOT EXISTS giveaway_templates (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER NOT NULL,
                    user_id INTEGER,
                    template_name TEXT NOT NULL,
                    embed_config TEXT NOT NULL,
                    UNIQUE(guild_id, user_id, template_name)
                )
            """)
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to create/update giveaways table: {e}", exc_info=True)

    def save_template(self, guild_id: int, user_id: Optional[int], template_name: str, embed_config: dict):
        try:
            cfg_json = json.dumps(embed_config)
            self.economy.cur.execute(
                """INSERT INTO giveaway_templates (guild_id, user_id, template_name, embed_config)
                   VALUES (?, ?, ?, ?)
                   ON CONFLICT(guild_id, user_id, template_name) DO UPDATE SET embed_config = excluded.embed_config""",
                (guild_id, user_id, template_name, cfg_json)
            )
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save giveaway template: {e}", exc_info=True)

    def get_template(self, guild_id: int, user_id: Optional[int] = None, template_name: str = "default") -> dict:
        try:
            if user_id is not None:
                self.economy.cur.execute(
                    "SELECT embed_config FROM giveaway_templates WHERE guild_id = ? AND user_id = ? AND template_name = ?",
                    (guild_id, user_id, template_name)
                )
                row = self.economy.cur.fetchone()
                if row and row[0]:
                    return json.loads(row[0])
            # Fallback to guild-wide template
            self.economy.cur.execute(
                "SELECT embed_config FROM giveaway_templates WHERE guild_id = ? AND user_id IS NULL AND template_name = ?",
                (guild_id, template_name)
            )
            row = self.economy.cur.fetchone()
            if row and row[0]:
                return json.loads(row[0])
        except Exception as e:
            logger.error(f"Failed to get giveaway template: {e}", exc_info=True)
        return {}

    def save_giveaway(self, msg_id, guild_id, channel_id, prize, host_id, winner_count, ends_at, required_roles, bonus_roles, embed_config=None, extra_reqs=None, role_bonus_prizes=None):
        try:
            cfg_json = json.dumps(embed_config) if embed_config else '{}'
            reqs_json = json.dumps(extra_reqs) if extra_reqs else '{}'
            role_prizes_json = json.dumps(role_bonus_prizes) if role_bonus_prizes else '{}'
            self.economy.cur.execute(
                """INSERT INTO giveaways (id, guild_id, channel_id, message_id, prize, host_id, winner_count, ends_at, ended, required_roles, bonus_roles, participants, winners, embed_config, extra_reqs, role_bonus_prizes)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, 0, ?, ?, '{}', '[]', ?, ?, ?)""",
                (msg_id, guild_id, channel_id, msg_id, prize, host_id, winner_count, ends_at, json.dumps(required_roles), json.dumps(bonus_roles), cfg_json, reqs_json, role_prizes_json)
            )
            self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to save giveaway: {e}", exc_info=True)

    def get_giveaway(self, msg_id: int):
        try:
            self.economy.cur.execute(
                """SELECT id, guild_id, channel_id, message_id, prize, host_id, winner_count, ends_at, ended, required_roles, bonus_roles, participants, winners, embed_config, extra_reqs, role_bonus_prizes 
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
                    'role_bonus_prizes': row[15] or '{}'
                }
        except Exception as e:
            logger.error(f"Failed to get giveaway: {e}", exc_info=True)
        return None

    def update_giveaway_full(self, msg_id: int, prize=None, winner_count=None, ends_at=None, required_roles=None, bonus_roles=None, embed_config=None, extra_reqs=None, role_bonus_prizes=None):
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

            if fields:
                params.append(msg_id)
                query = f"UPDATE giveaways SET {', '.join(fields)} WHERE id = ?"
                self.economy.cur.execute(query, tuple(params))
                self.economy.conn.commit()
        except Exception as e:
            logger.error(f"Failed to update giveaway full: {e}", exc_info=True)

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
        """Checks if a user has management permissions (Administrator, Manage Guild, Bot Owner, or Giveaway Host)."""
        if not user_or_member:
            return False
        if hasattr(user_or_member, "guild_permissions"):
            if user_or_member.guild_permissions.administrator or user_or_member.guild_permissions.manage_guild:
                return True
        if user_or_member.id in (getattr(self.bot, "owner_ids", None) or []):
            return True
        if giveaway and user_or_member.id == giveaway.get('host_id'):
            return True
        return False

    def is_host_or_admin(self, ctx: commands.Context, giveaway: dict) -> bool:
        return self.can_manage_giveaway(ctx.author, giveaway)

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

    def build_active_embed(self, giveaway: dict, participants_count: int) -> discord.Embed:
        prize = giveaway['prize']
        host_id = giveaway['host_id']
        winner_count = giveaway['winner_count']
        ends_at = giveaway['ends_at']
        
        req_roles_raw = giveaway.get('required_roles')
        required_roles = json.loads(req_roles_raw) if isinstance(req_roles_raw, str) else (req_roles_raw or [])
        
        embed_cfg_raw = giveaway.get('embed_config') or {}
        embed_cfg = json.loads(embed_cfg_raw) if isinstance(embed_cfg_raw, str) else (embed_cfg_raw or {})

        title = embed_cfg.get('title') or "<a:thanhgia:1526231085221023845> Giveaway Bắt Đầu <a:thanhgia:1526231085221023845>"
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
            embed.set_author(name=formatted_name, icon_url=author_icon or discord.Embed.Empty, url=author_url or discord.Embed.Empty)

        desc_lines = [
            f"**{prize}**",
            f"<a:timden:1526230943478845450> *host:* <@{host_id}>",
            f"<:ss:1526230022787043348>*Win:* {winner_count}"
        ]

        if required_roles:
            req_lines = ", ".join(f"<@&{r_id}>" for r_id in required_roles)
            desc_lines.append(f"<a:kcden:1526231212887380108> *Giới hạn:* {req_lines}")

        desc_lines.append(f"<:ss:1526230022787043348>*End:* <t:{ends_at}:R>")

        custom_desc = embed_cfg.get('custom_desc')
        if custom_desc:
            desc_lines.append(f"\n📝 *Ghi chú:* {custom_desc}")

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

    def build_ended_embed(self, giveaway: dict, winners: list, status_note: Optional[str] = None) -> discord.Embed:
        prize = giveaway['prize']
        host_id = giveaway['host_id']
        winner_count = giveaway['winner_count']

        embed_cfg_raw = giveaway.get('embed_config') or {}
        embed_cfg = json.loads(embed_cfg_raw) if isinstance(embed_cfg_raw, str) else (embed_cfg_raw or {})

        color = parse_color(embed_cfg.get('color')) or discord.Color.purple()
        embed = discord.Embed(title="<a:thanhgia:1526231085221023845> **Giveaway Kết Thúc** <a:thanhgia:1526231085221023845>", color=color)

        if status_note:
            embed.description = f"### {prize}\n\n{status_note}"
        elif winners:
            winners_mentions = ", ".join(f"<@{w_id}>" for w_id in winners)
            desc_lines = [
                f"**{prize}**",
                f"<a:timden:1526230943478845450> *host:* <@{host_id}>",
                f"<:ss:1526230022787043348>*Win:* {winner_count}",
                f"<a:key:1526234974150459593>*Result:* {winners_mentions}"
            ]
            embed.description = "\n".join(desc_lines)
        else:
            embed.description = f"### {prize}\n\n Không có người tham gia hợp lệ."

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

        # Banner
        banner = embed_cfg.get('banner')
        if banner:
            embed.set_image(url=banner)

        return embed

    async def sync_giveaway_message(self, message_id: int):
        """Immediately syncs changes to the live giveaway message on Discord."""
        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            return
        guild = self.bot.get_guild(giveaway['guild_id'])
        if not guild:
            return
        channel = guild.get_channel(giveaway['channel_id'])
        if not channel:
            return
        try:
            message = await channel.fetch_message(message_id)
        except Exception as e:
            logger.warning(f"Could not fetch message {message_id} to sync: {e}")
            return

        try:
            participants = json.loads(giveaway['participants'])
        except Exception:
            participants = {}
        if isinstance(participants, list):
            participants = {str(uid): 1 for uid in participants}

        embed_cfg_raw = giveaway.get('embed_config') or {}
        embed_cfg = json.loads(embed_cfg_raw) if isinstance(embed_cfg_raw, str) else (embed_cfg_raw or {})
        ping_content = embed_cfg.get('ping_content') or f"# <a:w1:1526231439425667093> Giveaway {guild.name} <a:w2:1526231455422877798>"

        if giveaway['ended'] == 0:
            embed = self.build_active_embed(giveaway, len(participants))
            try:
                await message.edit(content=ping_content, embed=embed)
            except Exception as e:
                logger.warning(f"Failed to sync active giveaway message {message_id}: {e}")

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

        if not payload.emoji.is_custom_emoji() or payload.emoji.id != 1526238405061640272:
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
                    r_id = int(r_id_str)
                    if member.get_role(r_id) is not None:
                        entries += extra
            else:
                env_bonus = self.get_env_bonus_roles()
                if env_bonus:
                    for r_id, extra in env_bonus.items():
                        if member.get_role(r_id) is not None:
                            entries += extra

            participants[str(user_id)] = entries
            self.update_participants(message_id, participants)
            participants_count = len(participants)

        self.schedule_embed_update(message, giveaway, participants_count)

    @commands.Cog.listener()
    async def on_raw_reaction_remove(self, payload: discord.RawReactionActionEvent):
        if payload.user_id == self.bot.user.id:
            return

        if not payload.emoji.is_custom_emoji() or payload.emoji.id != 1526238405061640272:
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

        # Parse args_str
        prize, required_roles, bonus_roles, role_bonus_prizes, target_channel, embed_config = self.parse_giveaway_args(args_str)

        # Check attached images
        if not embed_config.get("banner") and ctx.message.attachments:
            for att in ctx.message.attachments:
                if att.content_type and att.content_type.startswith("image/"):
                    embed_config["banner"] = att.url
                    break

        # Check default template for user/guild
        saved_template = self.get_template(ctx.guild.id, ctx.author.id)
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
        if duration_seconds is None or duration_seconds <= 0:
            await ctx.send("❌ Định dạng thời gian không hợp lệ. Ví dụ: `30m`, `1h`, `2d`.", delete_after=10)
            return

        if winners_count <= 0:
            await ctx.send("❌ Số người thắng phải lớn hơn 0.", delete_after=10)
            return

        if not prize:
            await ctx.send("❌ Vui lòng nhập phần thưởng.", delete_after=10)
            return

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
        ping_header = embed_config.get("ping_content") or f"# <a:w1:1526231439425667093> Giveaway {ctx.guild.name} <a:w2:1526231455422877798>"

        try:
            msg = await channel.send(content=ping_header, embed=embed)
            await msg.add_reaction("<:ghim:1526238405061640272>")
        except discord.Forbidden:
            await ctx.send(f"❌ Bot không có quyền gửi tin nhắn hoặc embed ở kênh {channel.mention}.", delete_after=10)
            return

        # Save to database
        self.save_giveaway(
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

    @giveaway_group.command(name="edit", aliases=["sua", "chinhsua"], brief="Mở bảng điều khiển tương tác (Mimu-style) để chỉnh sửa Giveaway")
    async def giveaway_edit(self, ctx: commands.Context, message_id: Optional[int] = None):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        if message_id is None:
            if ctx.message.reference and ctx.message.reference.message_id:
                message_id = ctx.message.reference.message_id

        if message_id is None:
            await ctx.send(
                f"❌ Vui lòng nhập ID tin nhắn Giveaway hoặc Reply vào tin nhắn Giveaway cần sửa: `{ctx.prefix}ga edit <id_tin_nhắn>`",
                delete_after=10
            )
            return

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy dữ liệu giveaway với ID tin nhắn này.", delete_after=10)
            return

        if giveaway['ended'] != 0:
            await ctx.send("❌ Không thể chỉnh sửa giveaway đã kết thúc hoặc đã bị hủy.", delete_after=10)
            return

        if not self.can_manage_giveaway(ctx.author, giveaway):
            await ctx.send(
                "❌ Bạn không có quyền quản lý để chỉnh sửa Giveaway này. (Yêu cầu quyền Quản lý Server hoặc là Host của Giveaway)",
                delete_after=10
            )
            return

        trigger_view = OpenEditorTriggerView(self, giveaway, ctx.author, ctx.guild)
        prompt_msg = await ctx.send(
            f"🛠️ **Bảng Chỉnh Sửa Giveaway ID `{message_id}`** (Dành riêng cho <@{ctx.author.id}>):\n"
            f"*Nhấn nút bên dưới để mở Bảng Điều Khiển Riêng Tư (Ephemeral):*",
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

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này.", delete_after=10)
            return

        if not self.can_manage_giveaway(ctx.author, giveaway):
            await ctx.send("❌ Bạn không có quyền quản lý Giveaway này.", delete_after=10)
            return

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        role_prizes[str(role_target)] = actual_bonus
        self.update_giveaway_full(message_id, role_bonus_prizes=role_prizes)

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

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này.", delete_after=10)
            return

        if not self.can_manage_giveaway(ctx.author, giveaway):
            await ctx.send("❌ Bạn không có quyền quản lý Giveaway này.", delete_after=10)
            return

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        if str(role_target) in role_prizes:
            role_prizes.pop(str(role_target))
            self.update_giveaway_full(message_id, role_bonus_prizes=role_prizes)
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

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này.", delete_after=10)
            return

        role_prizes_raw = giveaway.get('role_bonus_prizes') or {}
        role_prizes = json.loads(role_prizes_raw) if isinstance(role_prizes_raw, str) else (role_prizes_raw or {})

        embed = discord.Embed(
            title=f"🎁 Danh Sách Role Bonus - Giveaway `{message_id}`",
            color=discord.Color.gold()
        )
        embed.description = f"**Giải thưởng chính:** {giveaway['prize']}\n\n"
        if role_prizes:
            lines = []
            for rid_str, prize_text in role_prizes.items():
                lines.append(f"• <@&{rid_str}>: **{prize_text}**")
            embed.description += "### 🌟 Đặc quyền phần thưởng Role:\n" + "\n".join(lines)
        else:
            embed.description += "*Chưa có Role nào được cấu hình bonus phần thưởng thêm cho giveaway này.*"

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

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy Giveaway này trong hệ thống.", delete_after=10)
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

        # Build separate response embed
        embed = discord.Embed(
            title="🔍 KẾT QUẢ KIỂM TRA ROLE BONUS GIVEAWAY",
            color=discord.Color.blue()
        )
        embed.description = f"📌 **Giveaway:** {prize} (ID: `{message_id}`)\n👑 **Tổ chức bởi:** <@{giveaway['host_id']}>\n\n"

        for uid in target_ids:
            member = guild.get_member(uid)
            if not member:
                try:
                    member = await guild.fetch_member(uid)
                except Exception:
                    member = None

            member_name = member.display_name if member else f"User ID {uid}"
            
            matched_bonuses = []
            if member:
                for rid_str, bonus_desc in role_prizes.items():
                    try:
                        rid = int(rid_str)
                        if member.get_role(rid) is not None:
                            matched_bonuses.append((rid, bonus_desc))
                    except ValueError:
                        pass

            block_lines = [
                f"👤 **Người chơi:** <@{uid}> (`{member_name}`)",
                f"🎁 **Giải thưởng gốc:** {prize}"
            ]

            if matched_bonuses:
                block_lines.append("🌟 **Đặc quyền Role hợp lệ:**")
                for r_id, b_desc in matched_bonuses:
                    block_lines.append(f"  ├─ 💎 <@&{r_id}>: **{b_desc}**")
                
                all_rewards = [prize] + [b[1] for b in matched_bonuses]
                total_str = " + ".join(f"**{r}**" for r in all_rewards)
                block_lines.append(f"\n📦 **TỔNG PHẦN THƯỞNG CẦN TRAO:**\n👉 {total_str}")
            else:
                block_lines.append("🌟 **Đặc quyền Role:** Không có bonus thêm.")
                block_lines.append(f"\n📦 **TỔNG PHẦN THƯỞNG CẦN TRAO:**\n👉 **{prize}**")

            embed.add_field(
                name=f"🏆 Kiểm tra: {member_name}",
                value="\n".join(block_lines),
                inline=False
            )

        embed.set_footer(text="Sylus Meow • Giveaway System (Embed GA gốc không bị thay đổi)")
        await ctx.send(embed=embed)

    @giveaway_group.command(name="ketthuc", aliases=["end"], brief="Kết thúc sớm một giveaway đang chạy")
    async def giveaway_end(self, ctx: commands.Context, message_id: int):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này.", delete_after=10)
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

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này.", delete_after=10)
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

        try:
            message = await channel.fetch_message(message_id)
        except Exception:
            message = None

        self.mark_ended(message_id, ended=2) # 2 = Cancelled

        if message:
            embed_cfg_raw = giveaway.get('embed_config') or {}
            embed_cfg = json.loads(embed_cfg_raw) if isinstance(embed_cfg_raw, str) else (embed_cfg_raw or {})
            color = parse_color(embed_cfg.get('color')) or discord.Color.purple()

            embed = discord.Embed(title="🎉 GIVEAWAY ĐÃ BỊ HUỶ 🎉", color=color)
            embed.description = f"### {giveaway['prize']}\n\n🛑 Giveaway này đã bị huỷ bởi Host."
            embed.add_field(name="Tổ chức bởi", value=f"<@{giveaway['host_id']}>", inline=True)
            embed.set_footer(text=embed_cfg.get('footer_text') or "Sylus Meow • Giveaway System")
            self.set_embed_host_thumbnail(embed, giveaway['host_id'])
            if embed_cfg.get('banner'):
                embed.set_image(url=embed_cfg['banner'])
            await message.edit(embed=embed, view=None)

        await channel.send(f"🛑 Giveaway giải **{giveaway['prize']}** đã bị huỷ bởi <@{ctx.author.id}>.")

    @giveaway_group.command(name="quaylai", aliases=["reroll"], brief="Quay lại người thắng mới cho giveaway đã kết thúc")
    async def giveaway_reroll(self, ctx: commands.Context, message_id: int, count: int = 1):
        try:
            await ctx.message.delete()
        except Exception:
            pass

        giveaway = self.get_giveaway(message_id)
        if not giveaway:
            await ctx.send("❌ Không tìm thấy giveaway này.", delete_after=10)
            return

        if giveaway['ended'] != 1:
            await ctx.send("❌ Chỉ có thể quay lại (reroll) cho giveaway đã kết thúc thành công.", delete_after=10)
            return

        if not self.is_host_or_admin(ctx, giveaway):
            await ctx.send("❌ Bạn không có quyền quay lại giveaway này.", delete_after=10)
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

        try:
            participants = json.loads(giveaway['participants'])
        except Exception:
            participants = {}

        if isinstance(participants, list):
            participants = {str(uid): 1 for uid in participants}

        try:
            old_winners = json.loads(giveaway['winners'])
        except Exception:
            old_winners = []

        prize = giveaway['prize']
        host_id = giveaway['host_id']

        ticket_pool = []
        for user_id_str, entries in participants.items():
            try:
                user_id = int(user_id_str)
            except ValueError:
                continue
            if user_id in old_winners:
                continue
            for _ in range(entries):
                ticket_pool.append(user_id)

        import random
        random.shuffle(ticket_pool)

        new_winners = []
        failed_users = set()
        while len(new_winners) < count and len(ticket_pool) > 0:
            candidate = ticket_pool.pop()
            if candidate in new_winners or candidate in failed_users:
                continue
            
            member = guild.get_member(candidate)
            if not member:
                try:
                    member = await guild.fetch_member(candidate)
                except discord.NotFound:
                    failed_users.add(candidate)
                    continue
                except Exception:
                    failed_users.add(candidate)
                    continue
            new_winners.append(candidate)

        if not new_winners:
            await ctx.send("❌ Không còn người tham gia hợp lệ nào khác để quay lại (reroll).", delete_after=10)
            return

        self.update_winners(message_id, new_winners)

        new_winners_mentions = ", ".join(f"<@{w_id}>" for w_id in new_winners)

        embed_cfg_raw = giveaway.get('embed_config') or {}
        embed_cfg = json.loads(embed_cfg_raw) if isinstance(embed_cfg_raw, str) else (embed_cfg_raw or {})
        color = parse_color(embed_cfg.get('color')) or discord.Color.purple()

        embed = discord.Embed(title="🎉 GIVEAWAY ĐÃ QUAY LẠI KẾT QUẢ 🎉", color=color)
        desc_lines = [
            f"**{prize}**",
            f"<a:timden:1526230943478845450> *host:* <@{host_id}>",
            f"<:ss:1526230022787043348>*Win:* {len(new_winners)}",
            f"<a:key:1526234974150459593>*Result:* {new_winners_mentions}"
        ]
        embed.description = "\n".join(desc_lines)
        embed.set_footer(text=embed_cfg.get('footer_text') or "Sylus Meow • Giveaway System")
        self.set_embed_host_thumbnail(embed, host_id)
        if embed_cfg.get('banner'):
            embed.set_image(url=embed_cfg['banner'])

        await message.edit(embed=embed, view=None)
        await channel.send(f"🎉 **Reroll:** Chúc mừng {new_winners_mentions} đã thắng giải **{prize}**! Liên hệ <@{host_id}> để nhận thưởng.")

    async def end_giveaway(self, message_id: int):
        giveaway = self.get_giveaway(message_id)
        if not giveaway or giveaway['ended'] != 0:
            return

        guild = self.bot.get_guild(giveaway['guild_id'])
        if not guild:
            self.mark_ended(message_id, ended=1)
            return

        channel = guild.get_channel(giveaway['channel_id'])
        if not channel:
            self.mark_ended(message_id, ended=1)
            return

        try:
            message = await channel.fetch_message(message_id)
        except discord.NotFound:
            self.mark_ended(message_id, ended=1)
            return
        except Exception:
            return

        try:
            participants = json.loads(giveaway['participants'])
        except Exception:
            participants = {}

        if isinstance(participants, list):
            participants = {str(uid): 1 for uid in participants}

        winner_count = giveaway['winner_count']
        prize = giveaway['prize']
        host_id = giveaway['host_id']

        if not participants:
            self.mark_ended(message_id, ended=1)
            embed = self.build_ended_embed(giveaway, [], status_note=" Không có ai tham gia giveaway này.")
            await message.edit(embed=embed, view=None)
            await channel.send(f" Không có ai tham gia giveaway **{prize}**.")
            return

        ticket_pool = []
        for user_id_str, entries in participants.items():
            try:
                user_id = int(user_id_str)
                for _ in range(entries):
                    ticket_pool.append(user_id)
            except ValueError:
                continue

        import random
        random.shuffle(ticket_pool)

        winners = []
        failed_users = set()
        while len(winners) < winner_count and len(ticket_pool) > 0:
            candidate = ticket_pool.pop()
            if candidate in winners or candidate in failed_users:
                continue

            member = guild.get_member(candidate)
            if not member:
                try:
                    member = await guild.fetch_member(candidate)
                except discord.NotFound:
                    failed_users.add(candidate)
                    continue
                except Exception:
                    failed_users.add(candidate)
                    continue
            winners.append(candidate)

        if not winners:
            self.mark_ended(message_id, ended=1)
            embed = self.build_ended_embed(giveaway, [], status_note=" Không có người tham gia hợp lệ (người tham gia đã rời server).")
            await message.edit(embed=embed, view=None)
            await channel.send(f" Không có ai thắng giveaway **{prize}** vì tất cả người tham gia đã rời server.")
            return

        self.mark_ended(message_id, ended=1, winners=winners)

        winners_mentions = ", ".join(f"<@{w_id}>" for w_id in winners)

        embed = self.build_ended_embed(giveaway, winners)
        await message.edit(embed=embed, view=None)

        await channel.send(f" <a:wing:1526230985987981393>*Chúc mừng {winners_mentions} đã thắng giải **{prize}**<a:key:1526234974150459593> Liên hệ <@{host_id}> để nhận thưởng.*")

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
            self.economy.cur.execute("SELECT id FROM giveaways WHERE ended = 0 AND ends_at <= ?", (now,))
            rows = self.economy.cur.fetchall()
            for row in rows:
                msg_id = row[0]
                await self.end_giveaway(msg_id)
        except Exception as e:
            logger.error(f"Error in giveaway_check_loop: {e}", exc_info=True)

    @giveaway_check_loop.before_loop
    async def before_giveaway_check_loop(self):
        await self.bot.wait_until_ready()


async def setup(bot: commands.Bot):
    await bot.add_cog(Giveaway(bot))
