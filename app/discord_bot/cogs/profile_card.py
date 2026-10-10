"""Profile Card Cog - Customizable personal profile cards with pagination, shortcuts, and custom fonts.
Ported from Ilis_Farm.
"""
import logging
import os
import re
import time
from pathlib import Path
from typing import Optional

import aiohttp
import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.profile_card_db import (
    add_image,
    add_shortcut,
    find_shortcut,
    get_card,
    is_keyword_taken,
    load_shortcuts,
    remove_all_shortcuts,
    remove_image,
    remove_shortcut,
    upsert_card,
)
from app.discord_bot.modules.profile_card_fonts import (
    FONTS,
    apply_font,
    display_len,
)

logger = logging.getLogger(__name__)

PICS_DIR = Path(config.storage.data_dir) / "profile_pics"
PICS_DIR.mkdir(parents=True, exist_ok=True)


async def is_bot_admin_or_owner(ctx: commands.Context) -> bool:
    """Check if the user is a Bot Owner or Bot Admin (excludes server admins)."""
    bot_owner_ids = set(getattr(config.bot, "owner_ids", []) or [])
    bot_admin_ids = set(getattr(config.bot, "admin_ids", []) or [])
    if ctx.author.id in bot_owner_ids or ctx.author.id in bot_admin_ids:
        return True
    try:
        if await ctx.bot.is_owner(ctx.author):
            return True
    except Exception:
        pass
    return False


def is_admin_or_owner(user: discord.Member | discord.User) -> bool:
    """Check if the user is a Bot Owner or Bot Admin (excludes server admins)."""
    bot_owner_ids = set(getattr(config.bot, "owner_ids", []) or [])
    bot_admin_ids = set(getattr(config.bot, "admin_ids", []) or [])
    return user.id in bot_owner_ids or user.id in bot_admin_ids



def build_profile_embed(
    card: dict, member: discord.Member, img_index: int = 0
) -> tuple[discord.Embed, list[discord.File]]:
    """Build the profile card embed and attachment for the specified image index."""
    images = card.get("images") or []
    avatar_url = member.display_avatar.url

    title = card.get("title") or ""
    content = card.get("content") or ""
    footer = card.get("footer") or ""

    if title:
        title = apply_font(title, card.get("font_title"))
    if content:
        content = apply_font(content, card.get("font_content"))
    if footer:
        footer = apply_font(footer, card.get("font_footer"))

    color_val = card.get("color")
    if color_val is None:
        color = discord.Color.from_rgb(253, 215, 223)  # Pastel pink default #FDD7DF
    else:
        color = discord.Color(color_val)

    embed = discord.Embed(color=color)
    embed.set_author(name=member.display_name, icon_url=avatar_url)
    embed.set_thumbnail(url=avatar_url)

    desc_parts = []
    if title:
        desc_parts.append(f"# {title}\n")
    if content:
        desc_parts.append(content)

    if desc_parts:
        embed.description = "\n".join(desc_parts)
    else:
        embed.description = "*Chưa có nội dung mô tả.*"

    files = []
    idx = 0
    if images:
        idx = max(0, min(img_index, len(images) - 1))
        filename = images[idx]
        filepath = PICS_DIR / filename
        if filepath.exists():
            files.append(discord.File(str(filepath), filename=filename))
            embed.set_image(url=f"attachment://{filename}")

    footer_parts = []
    if footer:
        footer_parts.append(footer)
    if len(images) > 1:
        footer_parts.append(f"{idx + 1} / {len(images)}")

    if footer_parts:
        embed.set_footer(text="  ·  ".join(footer_parts))

    return embed, files


class ProfilePaginationView(discord.ui.View):
    """View with Prev / Next buttons to navigate multi-image profile cards."""

    def __init__(self, target_member: discord.Member, current_index: int, total_images: int):
        super().__init__(timeout=180.0)
        self.target_member = target_member
        self.current_index = current_index
        self.total_images = total_images

    @discord.ui.button(emoji="<:zh_trai:1558495370588327976>", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = (self.current_index - 1 + self.total_images) % self.total_images
        await self._update(interaction)

    @discord.ui.button(emoji="<:zh_phai:1558495389487861860>", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_index = (self.current_index + 1) % self.total_images
        await self._update(interaction)

    async def _update(self, interaction: discord.Interaction):
        card = get_card(self.target_member.id, self.target_member.guild.id)
        if not card or not card.get("images"):
            await interaction.response.send_message("❌ Profile không còn ảnh!", ephemeral=True)
            return

        self.total_images = len(card["images"])
        self.current_index %= self.total_images

        embed, files = build_profile_embed(card, self.target_member, self.current_index)
        await interaction.response.edit_message(embed=embed, attachments=files, view=self)


class FontListPaginationView(discord.ui.View):
    """View with Prev / Next buttons to browse font list pages."""

    def __init__(self, author_id: int, embeds: list[discord.Embed]):
        super().__init__(timeout=180.0)
        self.author_id = author_id
        self.embeds = embeds
        self.current_page = 0
        self._update_buttons()

    def _update_buttons(self):
        self.prev_button.disabled = self.current_page == 0
        self.next_button.disabled = self.current_page == len(self.embeds) - 1

    @discord.ui.button(emoji="<:zh_trai:1558495370588327976>", style=discord.ButtonStyle.secondary)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ Bạn không phải người dùng lệnh này!", ephemeral=True)
        if self.current_page > 0:
            self.current_page -= 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)

    @discord.ui.button(emoji="<:zh_phai:1558495389487861860>", style=discord.ButtonStyle.secondary)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            return await interaction.response.send_message("❌ Bạn không phải người dùng lệnh này!", ephemeral=True)
        if self.current_page < len(self.embeds) - 1:
            self.current_page += 1
            self._update_buttons()
            await interaction.response.edit_message(embed=self.embeds[self.current_page], view=self)


class ProfileCard(commands.Cog, name="ProfileCard"):
    """Cog managing personal customizable profile cards."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot
        load_shortcuts()

    # ── pr5 command ──────────────────────────────────────────────────────────
    @commands.command(name="pr5", aliases=["profilecard", "pcard"])
    async def show_profile_card(
        self, ctx: commands.Context, target: Optional[discord.Member] = None
    ):
        """View a user's customized profile card."""
        member = target or ctx.author
        card = get_card(member.id, ctx.guild.id)

        is_empty = not card or (
            not card.get("title")
            and not card.get("content")
            and not card.get("footer")
            and not card.get("images")
        )

        p = config.bot.prefix or "i?"
        if is_empty:
            if member.id == ctx.author.id:
                return await ctx.reply(
                    f"❌ Bạn chưa setup profile! Nhờ Admin Bot dùng `{p}set` để tạo hoặc `{p}mau` để xem mẫu.",
                    mention_author=False,
                )
            else:
                return await ctx.reply(
                    f"❌ {member.display_name} chưa có profile.",
                    mention_author=False,
                )

        images = card.get("images") or []
        embed, files = build_profile_embed(card, member, 0)
        view = ProfilePaginationView(member, 0, len(images)) if len(images) > 1 else None

        if view:
            await ctx.reply(embed=embed, files=files, view=view, mention_author=False)
        else:
            await ctx.reply(embed=embed, files=files, mention_author=False)

    # ── mau command ──────────────────────────────────────────────────────────
    @commands.command(name="mau", aliases=["profilemau"])
    async def show_sample_card(self, ctx: commands.Context):
        """Show sample profile card layout and instructions (Bot Admin only)."""
        if not await is_bot_admin_or_owner(ctx):
            return await ctx.reply("❌ Lệnh này chỉ dành cho Admin Bot!", mention_author=False)

        bot_member = ctx.guild.me
        avatar_url = bot_member.display_avatar.url
        p = config.bot.prefix or "i?"

        embed = discord.Embed(color=discord.Color.from_rgb(253, 215, 223))
        embed.set_author(name="✦ Tên trong server", icon_url=avatar_url)
        embed.set_thumbnail(url=avatar_url)
        embed.description = "\n".join(
            [
                "# Tiêu đề mẫu ✨\n",
                "Đây là phần nội dung tự do.",
                "Viết gì cũng được — hỗ trợ **bold**, *italic*, emoji 🎀",
                "và nhiều dòng văn bản (dùng `/n` để xuống dòng).\n",
                "─────────────────────────────",
                "**Cách setup profile card (Admin Bot):**",
                f"`{p}set title <text>` — tiêu đề *(tối đa 50 ký tự)*",
                f"`{p}set content <text>` — nội dung *(dùng `/n` để xuống dòng)*",
                f"`{p}set img <url / đính kèm>` — thêm ảnh *(tối đa 10 ảnh)*",
                f"`{p}set footer <text>` — chữ chân trang",
                f"`{p}set theme <mã hex>` — màu viền embed *(VD: `#FF69B4`)*",
                f"`{p}set font <title|content|footer|all> <tên font>` — đổi font chữ",
                f"`{p}set font list` — xem danh sách font",
                f"`{p}set short <từ khoá>` — gõ từ khoá tự động hiện profile",
                f"`{p}set remove img <n>` — xoá ảnh thứ n",
                f"`{p}set remove <field>` — xoá trường dữ liệu *(title/content/footer/theme/font/short)*\n",
                f"**Set hộ người khác:** `{p}set @user title/content/img/short ...`",
                f"**Xem profile:** `{p}pr5` hoặc `{p}pr5 @user`",
            ]
        )
        embed.set_footer(text="Nội dung footer mẫu  ·  (◀ ▶ để đổi ảnh khi album có nhiều ảnh)")

        await ctx.reply(embed=embed, mention_author=False)

    # ── pset / set command ────────────────────────────────────────────────────
    @commands.command(name="pset", aliases=["setprofile", "profile-set", "pcardset"])
    async def set_profile_card(self, ctx: commands.Context, *, raw_args: str = ""):
        """Setup/customize a profile card (Bot Admin only)."""
        if not await is_bot_admin_or_owner(ctx):
            return await ctx.reply("❌ Lệnh này chỉ dành cho Admin Bot!", mention_author=False)

        p = config.bot.prefix or "i?"
        parts = raw_args.strip().split()
        if not parts:
            help_lines = [
                "**Cách setup profile card (Admin Bot):**",
                f"`{p}set title <text>` — tiêu đề (tối đa 50 ký tự, emoji = 2 ký tự)",
                f"`{p}set content <text>` — nội dung (dùng `/n` để xuống dòng)",
                f"`{p}set img <url>` hoặc đính kèm ảnh — thêm ảnh (tối đa 10)",
                f"`{p}set footer <text>` — footer",
                f"`{p}set theme <mã màu>` — màu viền embed (VD: `#FF69B4`)",
                f"`{p}set font <title|content|footer|all> <tên font>` — đổi font chữ",
                f"`{p}set font list` — xem danh sách font",
                f"`{p}set short <từ khoá>` — gõ từ khoá thay vì `{p}pr5 @user`",
                f"`{p}set remove <field>` — xoá trường (title/content/footer/theme/font/short)",
                f"`{p}set remove img <số>` — xoá ảnh thứ n",
                "",
                f"**Set hộ người khác:** `{p}set @user title/content/img/short ...`",
                f"**Xem kết quả:** `{p}pr5` | **Xem mẫu:** `{p}mau`",
            ]
            return await ctx.reply("\n".join(help_lines), mention_author=False)

        target = ctx.author
        cmd_tokens = []
        found_target = False

        for token in parts:
            mention_match = re.match(r"^<@!?(\d+)>$", token)
            if not found_target and mention_match:
                uid = int(mention_match.group(1))
                mem = ctx.guild.get_member(uid) or await self._fetch_member_safe(ctx.guild, uid)
                if mem:
                    target = mem
                    found_target = True
                    continue
            elif not found_target and token.isdigit() and len(token) >= 17:
                uid = int(token)
                mem = ctx.guild.get_member(uid) or await self._fetch_member_safe(ctx.guild, uid)
                if mem:
                    target = mem
                    found_target = True
                    continue
            cmd_tokens.append(token)

        cmd_args = cmd_tokens

        if not target:
            return await ctx.reply("❌ Không tìm thấy thành viên được chỉ định!", mention_author=False)

        if not cmd_args:
            return await ctx.reply(
                f"❌ Thiếu subcommand! Ví dụ: `{p}set {target.mention} title Xin chào` hoặc `{p}set {target.mention} shortcut zh28`",
                mention_author=False,
            )

        for_str = f" cho {target.display_name}" if target.id != ctx.author.id else ""
        sub = cmd_args[0].lower()

        # ── sub: title / name ──
        if sub in ["title", "name"]:
            text = " ".join(cmd_args[1:]).strip()
            if not text:
                return await ctx.reply("❌ Thiếu nội dung tiêu đề!", mention_author=False)
            if display_len(text) > 50:
                return await ctx.reply(
                    f"❌ Tiêu đề quá dài ({display_len(text)} ký tự, tối đa 50 — emoji tính 2 ký tự)!",
                    mention_author=False,
                )
            upsert_card(target.id, ctx.guild.id, title=text)
            return await ctx.reply(f"✅ Đã set tiêu đề{for_str}: **{text}**", mention_author=False)

        # ── sub: content / bio / desc ──
        if sub in ["content", "desc", "description", "bio", "text"]:
            text = " ".join(cmd_args[1:]).strip().replace("/n", "\n")
            if not text:
                return await ctx.reply("❌ Thiếu nội dung!", mention_author=False)
            upsert_card(target.id, ctx.guild.id, content=text)
            return await ctx.reply(f"✅ Đã cập nhật nội dung{for_str}!", mention_author=False)

        # ── sub: footer ──
        if sub == "footer":
            text = " ".join(cmd_args[1:]).strip()
            if not text:
                return await ctx.reply("❌ Thiếu nội dung footer!", mention_author=False)
            upsert_card(target.id, ctx.guild.id, footer=text)
            return await ctx.reply(f"✅ Đã set footer{for_str}: **{text}**", mention_author=False)

        # ── sub: img / image / pic ──
        if sub in ["img", "image", "images", "pic", "pics", "photo"]:
            attachment = ctx.message.attachments[0] if ctx.message.attachments else None
            url = attachment.url if attachment else (cmd_args[1] if len(cmd_args) > 1 else None)

            if not url:
                return await ctx.reply(
                    f"❌ Đính kèm ảnh hoặc cung cấp URL! VD: `{p}set img https://...`",
                    mention_author=False,
                )

            card = get_card(target.id, ctx.guild.id)
            if card and len(card.get("images") or []) >= 10:
                return await ctx.reply("❌ Tối đa 10 ảnh!", mention_author=False)

            # Determine extension
            ext = ".png"
            clean_url = url.split("?")[0].lower()
            for possible_ext in [".gif", ".webp", ".jpg", ".jpeg", ".png"]:
                if clean_url.endswith(possible_ext):
                    ext = possible_ext
                    break

            filename = f"{target.id}_{int(time.time() * 1000)}{ext}"
            dest = PICS_DIR / filename

            try:
                await self._download_file(url, dest)
            except Exception as e:
                return await ctx.reply(f"❌ Không tải được ảnh: {e}", mention_author=False)

            total = add_image(target.id, ctx.guild.id, filename)
            return await ctx.reply(f"✅ Đã thêm ảnh{for_str} ({total} ảnh)!", mention_author=False)

        # ── sub: theme / color ──
        if sub in ["theme", "color"]:
            if len(cmd_args) < 2:
                return await ctx.reply(
                    f"❌ Thiếu mã màu! VD: `{p}set theme #FF0088` hoặc `{p}set theme FF0088`",
                    mention_author=False,
                )
            hex_str = cmd_args[1].lstrip("#")
            if not re.match(r"^[0-9A-Fa-f]{6}$", hex_str):
                return await ctx.reply(
                    "❌ Mã màu không hợp lệ! Dùng mã HEX 6 ký tự. VD: `#FF0088`",
                    mention_author=False,
                )
            color_int = int(hex_str, 16)
            upsert_card(target.id, ctx.guild.id, color=color_int)
            return await ctx.reply(
                f"✅ Đã set màu embed{for_str}: **#{hex_str.upper()}**",
                mention_author=False,
            )

        # ── sub: font / fonttitle / fontcontent / fontfooter ──
        if sub in ["font", "fonttitle", "fontcontent", "fontfooter"]:
            if len(cmd_args) > 1 and cmd_args[1].lower() == "list":
                items = list(FONTS.items())
                page_size = 8
                total_pages = (len(items) + page_size - 1) // page_size
                embeds = []

                for page_idx in range(total_pages):
                    chunk = items[page_idx * page_size : (page_idx + 1) * page_size]
                    embed = discord.Embed(
                        title=f"🎨 Danh Sách Font Chữ Nghệ Thuật ({page_idx + 1}/{total_pages})",
                        color=discord.Color.from_rgb(253, 215, 223),
                    )
                    lines = []
                    for k, v in chunk:
                        sample = apply_font("Hello 123", k)
                        lines.append(f"• **`{k}`** ({v['label']}):\n  ↳ {sample}")

                    lines.append("\n─────────────────────────────")
                    lines.append(f"**Cú pháp:** `{p}set font all <tên font>` hoặc `{p}set font content <tên font>`")
                    lines.append(f"**Đặt lại:** `{p}set font all none` (hoặc `normal`)")

                    embed.description = "\n".join(lines)
                    embed.set_footer(
                        text=f"Trang {page_idx + 1}/{total_pages} (Tổng {len(items)} fonts)  ·  Bấm nút bên dưới để chuyển trang"
                    )
                    embeds.append(embed)

                view = FontListPaginationView(ctx.author.id, embeds)
                return await ctx.reply(embed=embeds[0], view=view, mention_author=False)

            target_field = "all"
            font_key = ""
            if sub == "font":
                if len(cmd_args) >= 3 and cmd_args[1].lower() in [
                    "title",
                    "content",
                    "footer",
                    "all",
                ]:
                    target_field = cmd_args[1].lower()
                    font_key = cmd_args[2].lower()
                elif len(cmd_args) >= 2:
                    target_field = "all"
                    font_key = cmd_args[1].lower()
                else:
                    return await ctx.reply(
                        f"❌ Thiếu tên font! Dùng `{p}set font list` để xem danh sách.",
                        mention_author=False,
                    )
            else:
                target_field = sub.replace("font", "")
                font_key = cmd_args[1].lower() if len(cmd_args) > 1 else ""

            if not font_key:
                return await ctx.reply(
                    f"❌ Thiếu tên font! Dùng `{p}set font list` để xem danh sách.",
                    mention_author=False,
                )

            if font_key in ["none", "normal", "off", "macdinh", "reset"]:
                if target_field == "all":
                    upsert_card(target.id, ctx.guild.id, font_title="", font_content="", font_footer="")
                    field_label = "tất cả"
                elif target_field == "title":
                    upsert_card(target.id, ctx.guild.id, font_title="")
                    field_label = "tiêu đề"
                elif target_field == "content":
                    upsert_card(target.id, ctx.guild.id, font_content="")
                    field_label = "nội dung"
                elif target_field == "footer":
                    upsert_card(target.id, ctx.guild.id, font_footer="")
                    field_label = "footer"
                else:
                    return await ctx.reply("❌ Trường không hợp lệ! Dùng: `title`, `content`, `footer`, hoặc `all`.", mention_author=False)
                return await ctx.reply(f"✅ Đã đặt lại font về mặc định cho {field_label}{for_str}!", mention_author=False)

            if font_key not in FONTS:
                return await ctx.reply(
                    f"❌ Font **{font_key}** không tồn tại! Dùng `{p}set font list` để xem danh sách.",
                    mention_author=False,
                )

            if target_field == "all":
                upsert_card(
                    target.id,
                    ctx.guild.id,
                    font_title=font_key,
                    font_content=font_key,
                    font_footer=font_key,
                )
                field_label = "tất cả"
            elif target_field == "title":
                upsert_card(target.id, ctx.guild.id, font_title=font_key)
                field_label = "tiêu đề"
            elif target_field == "content":
                upsert_card(target.id, ctx.guild.id, font_content=font_key)
                field_label = "nội dung"
            elif target_field == "footer":
                upsert_card(target.id, ctx.guild.id, font_footer=font_key)
                field_label = "footer"
            else:
                field_label = target_field

            preview = apply_font("Hello World", font_key)
            return await ctx.reply(
                f"✅ Đã set font ({field_label}){for_str}: **{font_key}** — {preview}",
                mention_author=False,
            )

        # ── sub: short / shortcut ──
        if sub in ["short", "shortcut", "shortcuts"]:
            kw = " ".join(cmd_args[1:]).strip().lower()
            if not kw:
                return await ctx.reply(
                    f"❌ Thiếu từ khoá! VD: `{p}set short huyn`",
                    mention_author=False,
                )
            if is_keyword_taken(kw, ctx.guild.id, target.id):
                return await ctx.reply(
                    f"❌ Từ khoá **{kw}** đã được người khác dùng!",
                    mention_author=False,
                )
            card = get_card(target.id, ctx.guild.id) or {}
            existing_shorts = card.get("shorts") or []
            if kw in [s.lower() for s in existing_shorts]:
                return await ctx.reply(
                    f"❌ Từ khoá **{kw}** đã tồn tại rồi!",
                    mention_author=False,
                )
            add_shortcut(target.id, ctx.guild.id, kw)
            return await ctx.reply(
                f"✅ Đã thêm từ khoá{for_str}: **{kw}**\nGiờ ai gõ **{kw}** là bot tự hiện profile!",
                mention_author=False,
            )

        # ── sub: remove / delete / del ──
        if sub in ["remove", "delete", "del", "rem"]:
            if len(cmd_args) < 2:
                return await ctx.reply(
                    f"❌ Dùng: `{p}set remove <title|content|footer|theme|font|short|img>`",
                    mention_author=False,
                )
            field = cmd_args[1].lower()

            if field in ["img", "image", "images", "pic", "pics"]:
                if len(cmd_args) < 3 or not cmd_args[2].isdigit():
                    return await ctx.reply(
                        f"❌ Thiếu số thứ tự ảnh! VD: `{p}set remove img 1`",
                        mention_author=False,
                    )
                n = int(cmd_args[2])
                removed = remove_image(target.id, ctx.guild.id, n)
                if not removed:
                    card = get_card(target.id, ctx.guild.id) or {}
                    total = len(card.get("images") or [])
                    return await ctx.reply(
                        f"❌ Số ảnh không hợp lệ! Có {total} ảnh (1–{total})",
                        mention_author=False,
                    )
                try:
                    (PICS_DIR / removed).unlink(missing_ok=True)
                except Exception:
                    pass
                return await ctx.reply(f"✅ Đã xoá ảnh thứ {n}{for_str}!", mention_author=False)

            if field == "font":
                upsert_card(
                    target.id,
                    ctx.guild.id,
                    font_title=None,
                    font_content=None,
                    font_footer=None,
                )
                return await ctx.reply(
                    f"✅ Đã xoá font (tất cả){for_str}!", mention_author=False
                )

            if field in ["fonttitle", "fontcontent", "fontfooter"]:
                key = (
                    "font_title"
                    if field == "fonttitle"
                    else "font_content"
                    if field == "fontcontent"
                    else "font_footer"
                )
                upsert_card(target.id, ctx.guild.id, **{key: None})
                return await ctx.reply(f"✅ Đã xoá {field}{for_str}!", mention_author=False)

            if field in ["short", "shortcut", "shortcuts"]:
                if len(cmd_args) > 2:
                    kw = " ".join(cmd_args[2:]).strip().lower()
                    ok = remove_shortcut(target.id, ctx.guild.id, kw)
                    if not ok:
                        return await ctx.reply(
                            f"❌ Không tìm thấy từ khoá **{kw}**!",
                            mention_author=False,
                        )
                    return await ctx.reply(
                        f"✅ Đã xoá từ khoá **{kw}**{for_str}!", mention_author=False
                    )
                else:
                    remove_all_shortcuts(target.id, ctx.guild.id)
                    return await ctx.reply(
                        f"✅ Đã xoá tất cả từ khoá{for_str}!", mention_author=False
                    )

            if field in ["theme", "color", "colour"]:
                upsert_card(target.id, ctx.guild.id, color=None)
                return await ctx.reply(f"✅ Đã xoá màu theme{for_str}!", mention_author=False)

            if field in ["title", "name", "content", "desc", "footer"]:
                key = "title" if field in ["title", "name"] else "content" if field in ["content", "desc"] else "footer"
                upsert_card(target.id, ctx.guild.id, **{key: ""})
                return await ctx.reply(f"✅ Đã xoá {field}{for_str}!", mention_author=False)

            return await ctx.reply(
                f"❌ Trường không hợp lệ! Dùng: `{p}set remove <title|content|footer|theme|font|short|img>`",
                mention_author=False,
            )

        return await ctx.reply(
            f"❌ Subcommand không hợp lệ! Dùng `{p}set` để xem hướng dẫn.",
            mention_author=False,
        )

    # ── Listener for shortcut keywords ───────────────────────────────────────
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        """Auto-display user's profile card if a registered shortcut keyword is sent."""
        if message.author.bot or not message.guild:
            return

        content = message.content.strip().lower()
        p = (config.bot.prefix or "i?").lower()
        if content.startswith(p):
            return

        target_uid = find_shortcut(content, message.guild.id)
        if not target_uid:
            return

        card = get_card(target_uid, message.guild.id) or {}

        try:
            target_member = message.guild.get_member(int(target_uid)) or await self._fetch_member_safe(
                message.guild, int(target_uid)
            )
        except Exception:
            return

        if not target_member:
            return

        images = card.get("images") or []
        embed, files = build_profile_embed(card, target_member, 0)
        view = (
            ProfilePaginationView(target_member, 0, len(images))
            if len(images) > 1
            else None
        )

        try:
            if view:
                await message.reply(
                    embed=embed, files=files, view=view, mention_author=False
                )
            else:
                await message.reply(
                    embed=embed, files=files, mention_author=False
                )
        except Exception as e:
            logger.error("Error replying with shortcut profile card: %s", e)

    @staticmethod
    async def _fetch_member_safe(
        guild: discord.Guild, user_id: int
    ) -> Optional[discord.Member]:
        try:
            return await guild.fetch_member(user_id)
        except Exception:
            return None

    @staticmethod
    async def _download_file(url: str, dest: Path) -> None:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=30)) as resp:
                if resp.status != 200:
                    raise ValueError(f"HTTP code {resp.status}")
                data = await resp.read()
                with open(dest, "wb") as f:
                    f.write(data)


async def setup(bot: commands.Bot):
    await bot.add_cog(ProfileCard(bot))
