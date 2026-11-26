import asyncio
import re
import time
from random import choice

import discord
from discord.ext import commands

from app.discord_bot.modules.farm import art
from app.discord_bot.modules.farm.rules import (
    ACHIEVEMENTS, ALL_WORDS, CATALOG, CROPS, DAILY_STREAK_BONUSES, FISH, INVENTORY_CAPACITY, JUNK, NORMAL_GACHA, PETS, QUALITY_NAMES,
    QUESTS, SHOP, SHOP_IDS, START_COINS, daily_quests, day_at, event_at, inventory_size, pet_bonus, pet_key, season_at,
    vnd, xp_required,
)
from app.discord_bot.modules.farm.service import FarmError, FarmSession, FarmStore, plot_limit
from app.discord_bot.modules.farm.views import FarmChoices, FarmPages


def shop_icon(emojis, ctx, key: str) -> str:
    item = SHOP[key]
    return emojis.emoji(ctx, f"pet_{item['petId']}" if item["category"] == "pets" else key, item.get("emoji", ""))


def shop_description(text: str) -> str:
    def convert(match):
        parts = match.group(1).split("–")
        return "–".join(f"{vnd(int(part.replace('.', '').replace(',', ''))):,}" for part in parts) + " VND"

    return re.sub(r"(?<![\d%+])([\d.,]+(?:–[\d.,]+)?) xu", convert, text).replace("xu", "VND").replace("coin", "VND")


def inventory_name(emojis, ctx, entry: str) -> str:
    category, key = entry.split(":", 1)
    if category == "crop":
        crop, _, quality = key.rpartition("_")
        return f"{emojis.emoji(ctx, crop)} {CROPS[crop]['name']} ({QUALITY_NAMES[quality]})"
    if category == "junk":
        return f"{JUNK[key]['emoji']} {JUNK[key]['name']} (`{key}`)"
    return f"{shop_icon(emojis, ctx, key)} {SHOP[key]['name']}"


def progress_bar(value, total: int, width: int = 10) -> str:
    count = min(width, max(0, int(value * width / total + 0.5)))
    return f"`{'█' * count}{'░' * (width - count)}`"


def format_pet(emojis, ctx, key: str, pet: dict) -> str:
    icon = emojis.emoji(ctx, f"pet_{key}")
    def bar(value):
        return f"{progress_bar(value, 100)} {value:.0f}/100"

    return (
        f"{icon} **{PETS[key]['name']}** · Cấp {pet['level']} · C{pet['stars']}\n\n"
        f"🍖 **Độ no** {bar(pet['hunger'])}\n"
        f"💗 **Hạnh phúc** {bar(pet['happiness'])}\n"
        f"❤️ **Sức khỏe** {bar(pet['health'])}"
    )


def pet_album_page(ctx, emojis, state: dict, key: str) -> discord.Embed:
    pet = PETS[key]
    rarity, color = art.PET_RARITY[pet["rarity"]]
    number = tuple(PETS).index(key) + 1
    owned = state["pets"].get(key)
    collected = len(state["pets"])
    filled = int(collected * 12 / len(PETS) + 0.5)
    season = "🌹 Mùa 2" if key in {"tuat", "thaothiet", "kuromi", "melody", "satou", "shio"} else "📖 Mùa 1"
    lines = [
        f"**{rarity}** · {season}",
        f"{'🌸' * filled}{'🤍' * (12 - filled)} **{collected}/{len(PETS)}** pet đã sưu tầm",
    ]
    icon = emojis.emoji(ctx, f"pet_{key}")
    embed = discord.Embed(
        title=f"{emojis.emoji(ctx, 'ui_muong')} {icon} #{number:02} · {pet['name']}", description="\n".join(lines), color=color,
    )
    max_level = 10
    bonuses = pet_bonus(key, {"level": max_level, "stars": 0})
    bonus_lines = [
        f"**+{(bonuses[stat] - 1):.1%}** {label}"
        for stat, label in (
            ("xpBonus", "XP"), ("yieldBonus", "sản lượng"), ("coinBonus", "VND"),
            ("fishingXpBonus", "XP câu cá"), ("fishingCoinBonus", "VND câu cá"),
        )
        if bonuses.get(stat, 1) > 1
    ]
    bonus_lines.extend(
        f"**+{bonuses[stat]:.1%}** {label}"
        for stat, label in (("rareChanceBonus", "cơ hội nông sản hiếm"), ("doubleHarvestChance", "cơ hội thu hoạch gấp đôi"))
        if bonuses.get(stat, 0) > 0
    )
    if bonuses.get("fishingWeightBonus"):
        bonus_lines.append(f"**+{bonuses['fishingWeightBonus']:g} kg** khi câu cá")
    if bonus_lines:
        embed.add_field(name="✨ Hiệu ứng cấp 10", value="\n".join(bonus_lines), inline=False)
    constellations = CATALOG["CONSTELLATION_BONUSES"].get(pet["id"], [])
    if constellations:
        embed.add_field(name="🌟 Tiềm năng cung mệnh", value="\n".join(
            f"**C{index}** · {shop_description(entry['label'])}" for index, entry in enumerate(constellations, 1)
        ), inline=False)
    portrait = art.image(f"pet_{key}")
    if portrait:
        embed.set_thumbnail(url=portrait)
    prefix = f"{ctx.clean_prefix}farm"
    if owned:
        active = " · 🟢 Đang hoạt động" if key == state["active_pet"] else ""
        embed.add_field(
            name="📊 Pet của bạn", value=f"{progress_bar(owned['level'], 10)} **{owned['level']}/10**{active}\n"
            f"⭐ Cung mệnh **C{owned['stars']}/C6**", inline=False,
        )
    else:
        embed.add_field(name="🔒 Trạng thái", value=f"**Chưa sưu tầm**\nDùng `{prefix} gacha` để nhận pet.", inline=False)
    embed.set_footer(text=f"🥀 {prefix} pet <id> · {prefix} gacha · {prefix} selectpet · {prefix} petinfo")
    return embed


class IlisFarm(commands.Cog):
    """Nông trại Ilis Farm trong Casino Bot."""

    def __init__(self, bot):
        self.store = FarmStore(bot.economy)
        self.emojis = art.FarmEmojis(bot)
        self.last_huyn_line = {}

    @commands.Cog.listener()
    async def on_connect(self) -> None:
        await self.emojis.sync()

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        if ctx.author.bot:
            return
        try:
            await ctx.send(
                f"{self.emojis.emoji(ctx, 'ui_farm')} **Nông trại mới!** Gõ `{ctx.clean_prefix}farm` để chơi.",
                delete_after=5,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound):
            return
        if ctx.cog is not self or self.store.economy.get_setting("farm_huyn", "1") != "1":
            return
        try:
            state = self.store.get(ctx.author.id)
        except FarmError:
            return
        if state.get("huyn_active") and state["active_pet"] == "hr":
            lines = art.ART["huyn_lines"]
            last = self.last_huyn_line.get(ctx.author.id)
            line = choice([line for line in lines if line != last])
            self.last_huyn_line[ctx.author.id] = line
            try:
                await ctx.send(f"{self.emojis.emoji(ctx, 'pet_hr')} **Huyn:** {line}",
                               allowed_mentions=discord.AllowedMentions.none())
            except (discord.Forbidden, discord.NotFound):
                pass

    async def _send(
        self, ctx, title: str, description: str, *,
        badge: str = "ui_muong", thumbnail: str | None = None, image: str | None = None,
        color: int = art.COLOR, fields: tuple = (), view=None, footer: str = art.FOOTER,
        timestamp=None,
    ) -> None:
        if not description:
            description = "Chưa có dữ liệu."
        heading = f"{self.emojis.emoji(ctx, badge)} {title}"[:256]
        while description:
            split = len(description) if len(description) <= 4000 else description.rfind("\n", 0, 4000)
            if split <= 0:
                split = 4000
            embed = discord.Embed(title=heading, description=description[:split], color=color, timestamp=timestamp)
            embed.set_footer(text=footer)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            if image:
                embed.set_image(url=image)
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)
            if view:
                view.message = await ctx.reply(embed=embed, view=view, allowed_mentions=discord.AllowedMentions.none())
            else:
                await ctx.reply(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            fields, image = (), None
            view = None
            description = description[split:].lstrip("\n")

    async def _pages(self, ctx, pages, *, start=0, rate_pages=False) -> None:
        if not rate_pages:
            for index, page in enumerate(pages, 1):
                footer = page.footer.text
                stamp = f"Trang {index} / {len(pages)}"
                page.set_footer(text=f"{footer} · {stamp}" if footer else stamp)
        if len(pages) == 1:
            await ctx.reply(embed=pages[0], allowed_mentions=discord.AllowedMentions.none())
            return
        view = FarmPages(ctx.author.id, pages, start=start, rate_pages=rate_pages)
        view.message = await ctx.reply(embed=view.current, view=view, allowed_mentions=discord.AllowedMentions.none())

    async def _choice_message(self, interaction, text: str, title: str = "Ilis Farm") -> None:
        embed = discord.Embed(title=title, description=text, color=art.COLOR)
        embed.set_footer(text=art.FOOTER)
        await interaction.edit_original_response(content=None, embed=embed, view=None)

    async def _error(self, ctx, error: FarmError) -> None:
        message = str(error).replace("`farm ", f"`{ctx.clean_prefix}farm ")
        await ctx.send(f"❌ {message}", allowed_mentions=discord.AllowedMentions.none())

    async def _player(self, ctx) -> dict | None:
        try:
            return self.store.get(ctx.author.id)
        except FarmError as error:
            await self._error(ctx, error)
            return None

    async def _play(self, ctx, action, *args, render, title="Ilis Farm", badge="ui_muong", media=None, fields=None) -> None:
        try:
            with self.store.action(ctx.author.id, ctx.command.name) as session:
                result = action(session, *args)
        except FarmError as error:
            await self._error(ctx, error)
            return
        description = render(result)
        if session.unlocked:
            description += "\n🏅 " + " · ".join(session.unlocked)
        if session.wallet_delta:
            description += f"\n{self.emojis.emoji(ctx, 'ui_coin')} Ví Casino **{session.wallet_delta:+,} VND**"
        thumbnail, image = media(result) if media else (None, None)
        await self._send(
            ctx, title, description, badge=badge, thumbnail=thumbnail, image=image,
            fields=fields(result) if fields else (),
        )

    async def _show_plots(self, ctx, player, state: dict, *, view=None) -> None:
        level = state["level"]
        plots = state["plots"]
        now = time.time()
        capacity = plot_limit(level)
        width = int(capacity**0.5)
        tiles, growing = [], []
        for index in range(1, capacity + 1):
            plot = plots.get(str(index))
            if plot is None:
                tiles.append("⬜")
            else:
                crop = plot["crop"]
                icon = self.emojis.emoji(ctx, crop)
                ready = plot["ready"] <= now
                tiles.append("🌹" if ready else icon)
                status = "Sẵn sàng thu hoạch" if ready else f"<t:{int(plot['ready'])}:R>"
                growing.append(f"`#{index}` {icon} **{CROPS[crop]['name']}** · {status}")
        grid = ["　".join(tiles[i:i + width]) for i in range(0, capacity, width)]
        prefix = f"{ctx.clean_prefix}farm"
        progress = growing or [f"Trồng luống đầu tiên với `{prefix} plant 1`."]
        description = "\n".join(["╭──────────────────────────╮", *grid, "╰──────────────────────────╯"])
        fields = [
            ("🌸 Chú thích", "⬜ Trống　🌱 Đang lớn　🌹 Sẵn sàng", False),
            *(("⏳ Tiến độ cây trồng", "\n".join(progress[index:index + 12]), False)
              for index in range(0, len(progress), 12)),
            ("🗺️ Kích thước", f"`{width}×{width}`", True),
            ("🌱 Ô đã dùng", f"`{len(plots)}/{capacity}`", True),
            ("🏡 Trạng thái", "🌹 Đầy rồi" if len(plots) == capacity else "🌱 Còn trống", True),
            (f"{self.emojis.emoji(ctx, 'ui_xp')} Cấp độ", f"🌹 Lv.**{level}**", True),
            ("✨ Kinh nghiệm", f"`{state['xp']:,} XP`", True),
        ]
        if player.id == ctx.author.id:
            wallet = self.store.economy.get_entry(player.id)[1]
            fields.append((f"{self.emojis.emoji(ctx, 'ui_coin')} Ví Casino", f"`{wallet:,} VND`", True))
        next_level = next((int(level_key) for level_key in CATALOG["FARM_EXPANSION"] if int(level_key) > level), None)
        if next_level is not None:
            size = CATALOG["FARM_EXPANSION"][str(next_level)]
            fields.append(("🎀 Mở rộng tiếp theo", f"Cấp {next_level} · {size['rows']}×{size['cols']}", False))
        await self._send(
            ctx, f"₊˚🌸 NÔNG TRẠI — {player.display_name} 🌸˚₊", description,
            thumbnail=player.display_avatar.url, fields=tuple(fields), view=view,
            footer=f"🥀 {prefix} plant · {prefix} water · {prefix} harvest · {prefix} fer",
            timestamp=discord.utils.utcnow(),
        )

    @commands.group(name="farm", case_insensitive=True, invoke_without_command=True, brief="Xem nông trại Ilis Farm")
    async def farm(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            await self._show_plots(ctx, ctx.author, state)

    @farm.command(name="help", aliases=["hp"], brief="Xem danh sách lệnh Farm")
    async def farm_help(self, ctx):
        prefix = f"{ctx.clean_prefix}farm"
        sections = (
            (
                ("📅 Hằng ngày", ("daily", "quest", "update")),
                (f"{self.emojis.emoji(ctx, 'ui_gacha')} Gacha", ("gacha", "gacharates")),
                ("🌾 Nông trại", ("start", "plant", "harvest", "water", "fertilize", "friend")),
                ("🎣 Câu cá", ("fish", "equip", "sellfish")),
                ("📦 Kho và giao dịch", ("inventory", "sell", "shop", "buy", "balance", "give", "discard")),
            ),
            (
                ("🐾 Pet", ("pet", "petlist", "petinfo", "selectpet", "feed", "play", "cuddle", "kiss", "exercise", "killpet")),
                ("👤 Hồ sơ và thành tích", ("profile", "leaderboard", "achievements")),
                ("🌍 Thế giới", ("season", "events")),
                ("❓ Trợ giúp", ("help", "coche", "vt", "hdsd", "ping")),
                (f"{self.emojis.emoji(ctx, 'ui_xp')} Cấp độ và mở rộng đất", ("levelreward", "evolve")),
            ),
        )
        pages = []
        for index, page_sections in enumerate(sections, 1):
            page = discord.Embed(
                title=f"{self.emojis.emoji(ctx, 'ui_muong')} 🌸 ILYS FARM — Lệnh ({index}/2)",
                description=f"Tiền tố **`{prefix}`** · Dùng `{prefix} vt` để xem tên viết tắt.",
                color=art.COLOR if index == 1 else 0xA50018,
            )
            for name, names in page_sections:
                commands_in_section = [self.farm.get_command(command_name) for command_name in names]
                lines = [f"꒰ ✦ ꒱ `{command.name}` — {command.brief}" for command in commands_in_section]
                if names[0] == "start":
                    lines.insert(0, f"꒰ 🏡 ꒱ `{prefix}` — Xem nông trại.")
                if names[0] == "levelreward":
                    lines.extend(
                        f"꒰ 🌸 ꒱ Cấp {level}+ · {size['rows']}×{size['cols']} = **{size['maxPlots']} ô**"
                        for level, size in CATALOG["FARM_EXPANSION"].items()
                    )
                page.add_field(name=name, value="\n".join(lines), inline=False)
            page.set_footer(text=art.FOOTER)
            pages.append(page)
        await self._pages(ctx, pages)

    @farm.command(name="vt", aliases=["viettăt", "vittat", "shortcuts", "alias"], brief="Xem tên viết tắt của lệnh Farm")
    async def shortcuts(self, ctx):
        prefix = f"{ctx.clean_prefix}farm"
        await self._send(ctx, "Viết tắt lệnh Farm", "\n".join(
            f"`{prefix} {cmd.name}` · " + " · ".join(f"`{alias}`" for alias in cmd.aliases)
            for cmd in sorted(self.farm.commands, key=lambda item: item.name) if cmd.aliases and not cmd.hidden
        ))

    @farm.command(name="hdsd", aliases=["guide", "tutorial", "huongdan"], brief="Hướng dẫn chơi Farm theo từng bước")
    async def guide(self, ctx):
        prefix = f"{ctx.clean_prefix}farm"
        chapters = (
            ("🌸 ₊˚⊹ KHỞI ĐẦU HÀNH TRÌNH ⊹˚₊ 🌸", f"`{prefix} start` · Mở nông trại và nhận {vnd(START_COINS):,} VND.\n`{prefix}` · Xem đất và thời gian thu hoạch."),
            ("🎀 ₊˚⊹ DAILY & GACHA ⊹˚₊ 🎀", f"`{prefix} daily` và `{prefix} quest` · Nhận thưởng.\n`{prefix} gacha` · Quay 1 hoặc 10 lượt."),
            ("🌹 ₊˚⊹ NÔNG TRẠI ⊹˚₊ 🌹", f"`{prefix} plant 1 all` · Trồng rau muống.\n`{prefix} plant all` · Trồng hạt từ kho.\n`{prefix} water`, `{prefix} fer` và `{prefix} harvest` · Chăm sóc và thu hoạch."),
            ("📦 ₊˚ KHO & GIAO DỊCH ˚₊", f"`{prefix} shop farm` · Xem hạt giống và cần câu.\n`{prefix} inv` · Xem kho.\n`{prefix} sell all` · Bán nông sản."),
            ("₊˚🐾 PET 🐾˚₊", f"`{prefix} pet` · Mở sách sưu tầm.\n`{prefix} selectpet` · Chọn pet.\n`{prefix} feed`, `{prefix} play`, `{prefix} nung` · Chăm sóc pet."),
            ("₊˚🌍 THẾ GIỚI & MẸO 🌍˚₊", f"`{prefix} season` và `{prefix} events` · Xem hiệu ứng hôm nay.\n`{prefix} friend @người` · Ghé thăm nông trại bạn bè."),
        )
        await self._pages(ctx, [
            discord.Embed(title=f"{title} ({index}/6)", description=description, color=art.COLOR if index % 2 else 0xA50018).set_footer(text=art.FOOTER)
            for index, (title, description) in enumerate(chapters, 1)
        ])

    @farm.command(name="coche", aliases=["co_che", "mechanism", "mecanic", "rules"], brief="Xem cơ chế gacha, pet, câu cá, mùa và sự kiện")
    async def mechanics(self, ctx):
        prefix = f"{ctx.clean_prefix}farm"
        descriptions = (
            ("🎀 ୨୧ GACHA BAKERY ୨୧ 🎀", f"Vé từ điểm danh, nhiệm vụ, thưởng cấp và cập nhật Mùa 2. Ưu tiên dùng đủ vé, hoặc trừ {vnd(10_000):,} VND mỗi lượt. Tỷ lệ thần thoại tăng từ lượt 80, bảo đảm ở lượt 100. Dùng `{prefix} gachrates` để xem bảng tỷ lệ."),
            ("🐟 ୨୧ GÓC CÂU CÁ ୨୧ 🐟", f"Trang bị cần câu đã mua. Mỗi lượt tốn {vnd(100):,} VND và chờ 6 giây. Xem cá với `{prefix} inv f`, bán bằng `{prefix} selff <số|all>`."),
            ("🐰 ୨୧ PET & BẠN ĐỒNG HÀNH ୨୧ 🐰", f"Cho pet ăn để tăng độ no, chơi hoặc nựng để tăng hạnh phúc. Sức khỏe thấp làm giảm hiệu ứng. Dùng `{prefix} pet` để xem ảnh, độ hiếm và cung mệnh."),
            ("🍃 ୨୧ MÙA VỤ ILYS ୨୧ 🍃", f"Mỗi mùa kéo dài 14 ngày. Dùng `{prefix} season` để xem cây trồng được hưởng hiệu ứng."),
            ("✨ ୨୧ SỰ KIỆN HÔM NAY ୨୧ ✨", f"Sự kiện đổi mỗi ngày. Dùng `{prefix} events` để xem hiệu ứng hiện tại."),
        )
        pages = [discord.Embed(title=title, description=description, color=art.COLOR).set_footer(text=art.FOOTER)
                 for title, description in descriptions]
        await self._pages(ctx, pages)

    @farm.command(
        name="start", aliases=["dangky", "register", "taotaikhoan", "batdau", "bat_dau"],
        brief="Tạo nông trại và nhận vốn một lần",
    )
    async def start(self, ctx):
        try:
            balance = self.store.start(ctx.author.id)
        except FarmError as error:
            await self._error(ctx, error)
            return
        await self._send(
            ctx, "Nông trại mới",
            f"Đã cộng **{vnd(START_COINS):,} VND** vào ví Casino. Số dư **{balance:,} VND**.\n"
            f"Dùng `{ctx.clean_prefix}farm plant 1` để trồng rau muống.",
            thumbnail=ctx.author.display_avatar.url,
        )

    @farm.command(name="balance", aliases=["bal", "bl", "cash", "cs"], brief="Xem ví Casino, đá quý và vé Farm")
    async def balance(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            balance = self.store.economy.get_entry(ctx.author.id)[1]
            await self._send(
                ctx, f"🌸 VÍ TIỀN — {ctx.author.display_name}",
                "╭─────────────────────────╮\n꒰ ✦ ꒱ Đây là ví tiền của bạn~\n╰─────────────────────────╯",
                thumbnail=ctx.author.display_avatar.url,
                fields=(
                    (f"{self.emojis.emoji(ctx, 'ui_coin')} Ví Casino", f"`{balance:,} VND`", True),
                    (f"{self.emojis.emoji(ctx, 'ui_gem')} Đá quý", f"`{state['gems']}`", True),
                    (f"{self.emojis.emoji(ctx, 'ui_gacha')} Vé gacha", f"`{state['tickets']} vé`", True),
                    (f"{self.emojis.emoji(ctx, 'ui_xp')} Cấp độ", f"`Lv.{state['level']}`", True),
                    ("✨ Kinh nghiệm", f"`{state['xp']:,} XP`", True),
                ),
                timestamp=discord.utils.utcnow(),
            )

    @farm.command(name="give", aliases=["transfer", "send"], brief="Xác nhận chuyển VND bằng ví Casino")
    @commands.guild_only()
    async def give(self, ctx, member: discord.Member, amount: str, pet: str | None = None):
        try:
            if member.bot or member.id == ctx.author.id:
                raise FarmError("Chọn một người chơi khác để nhận.")
            self.store.get(ctx.author.id)
            self.store.get(member.id)
            if amount.lower() == "pet":
                if not pet or not await ctx.bot.is_owner(ctx.author):
                    raise FarmError("Chỉ chủ bot có thể tặng pet.")
                with self.store.action(member.id, "give pet") as session:
                    name, stars = session.grant_pet(pet)
                await self._send(ctx, "Tặng pet", f"<@{member.id}> nhận **{name} · C{stars}**.")
                return
            if not amount.isascii() or not amount.isdecimal() or len(amount) > 19 or not 0 < int(amount) < 2**63:
                raise FarmError("Nhập số VND nguyên dương.")
            value = int(amount)
        except FarmError as error:
            await self._error(ctx, error)
            return

        async def choose(interaction, selection):
            if selection == "cancel":
                await self._choice_message(interaction, "Đã hủy chuyển VND.")
                return
            if self.store.economy.is_banned(ctx.author.id) or self.store.economy.is_in_jail(ctx.author.id):
                await self._choice_message(interaction, "❌ Tài khoản của bạn đang bị hạn chế chuyển tiền.")
                return
            pay = ctx.bot.get_command("pay")
            await interaction.edit_original_response(view=None)
            await ctx.invoke(pay, target=member, amount=value)

        view = FarmChoices(ctx.author.id, (
            ("accept", "✅ Xác nhận", discord.ButtonStyle.success, False),
            ("cancel", "❌ Hủy", discord.ButtonStyle.danger, False),
        ), choose, timeout=30)
        await self._send(ctx, "Xác nhận chuyển VND", f"Chuyển **{value:,} VND** cho <@{member.id}>?", view=view)

    @farm.command(name="profile", brief="Xem tiến trình Farm")
    async def profile(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            level = state["level"]
            cap = 70 if state["evolutions"] else 50
            required = xp_required(level, state["evolutions"])
            xp = f"`{state['xp']:,}/{required:,} XP`" if level < cap else "✨ MAX"
            bar = progress_bar(state["xp"] if level < cap else required, required, 15)
            pet = state["active_pet"]
            wallet = self.store.economy.get_entry(ctx.author.id)[1]
            level_label = f"Lv.{level}" + (f" v{state['evolutions'] + 1}" if state["evolutions"] else "")
            await self._send(
                ctx, f"🌸 HỒ SƠ — {ctx.author.display_name}",
                f"╭─────────────────────────╮\n꒰ ✦ ꒱ Nông dân **{level_label}** đây~\n╰─────────────────────────╯",
                thumbnail=ctx.author.display_avatar.url, timestamp=discord.utils.utcnow(),
                fields=(
                    (f"{self.emojis.emoji(ctx, 'ui_xp')} Cấp độ và kinh nghiệm", f"**{level_label}** · {bar}\n{xp}", False),
                    (f"{self.emojis.emoji(ctx, 'ui_coin')} Ví Casino", f"`{wallet:,} VND`", True),
                    (f"{self.emojis.emoji(ctx, 'ui_gem')} Đá quý", f"`{state['gems']}`", True),
                    ("🐾 Pet", f"{self.emojis.emoji(ctx, 'pet_' + pet)} {PETS[pet]['name']}" if pet else "Chưa có pet", True),
                    ("📈 Thống kê nông trại", f"🌱 Đã trồng · `{state['planted']:,}`\n🌹 Đã thu hoạch · `{state['harvested']:,}`\n"
                     f"🛒 Đã bán · `{state['sold']:,}`\n💰 Tổng thu nhập · `{vnd(state['earned']):,} VND`", False),
                    ("📅 Chuỗi đăng nhập", f"🔥 `{state['streak']} ngày`", True),
                ),
            )

    @farm.command(name="daily", aliases=["dl", "d", "nhận", "nhan"], brief="Điểm danh nhận VND và vé gacha")
    async def daily(self, ctx):
        def fields(result):
            reward, streak = result
            bonus = DAILY_STREAK_BONUSES.get(streak, 0)
            coin = self.emojis.emoji(ctx, "ui_coin")
            result_fields = [
                (f"{coin} Thưởng cơ bản", f"`+{vnd(reward - bonus):,} VND`", True),
                (f"{coin} Tổng thưởng", f"`+{vnd(reward):,} VND`", True),
                ("📅 Chuỗi đăng nhập", f"`{streak} ngày liên tiếp`", True),
                (f"{self.emojis.emoji(ctx, 'ui_gacha')} Vé gacha", "**+1 vé gacha**", False),
            ]
            if bonus:
                result_fields.append(("🎉 Thưởng mốc hôm nay", f"**+{vnd(bonus):,} VND**", False))
            result_fields.append(("🎯 Các mốc thưởng", "\n".join(
                f"Ngày {day} · **+{vnd(amount):,} VND**" for day, amount in DAILY_STREAK_BONUSES.items()
            ), False))
            return tuple(result_fields)

        await self._play(
            ctx, FarmSession.daily, title="🎁 NHẬN THƯỞNG HẰNG NGÀY",
            render=lambda r: f"꒰ ✦ ꒱ **{ctx.author.display_name}** đã điểm danh ngày thứ **{r[1]}**!",
            media=lambda _: (ctx.author.display_avatar.url, None), fields=fields,
        )

    @farm.command(name="shop", aliases=["sh", "hang", "hàng", "cửahàng"], brief="Xem cửa hàng Farm theo danh mục")
    async def shop(self, ctx, category: str = ""):
        state = await self._player(ctx)
        if state is None:
            return
        categories = {
            "seeds": "🌱 Hạt giống", "pets": "🐾 Pet", "food": "🍖 Thức ăn",
            "fertilizer": "🧺 Phân bón", "fishing": "🎣 Cần câu", "weapon": "🔪 Vũ khí",
        }
        filters = {"farm": ("seeds", "fertilizer", "fishing"), "pet": ("pets", "food")}
        key = {"dao": "weapon", "vukhi": "weapon", "nôngtrại": "farm", "food": "pet"}.get(category.lower(), category.lower())
        selected = filters.get(key, (key,) if key in categories else ())
        prefix = f"{ctx.clean_prefix}farm"
        balance = self.store.economy.get_entry(ctx.author.id)[1]
        header = f"{self.emojis.emoji(ctx, 'ui_coin')} **{balance:,} VND**　{self.emojis.emoji(ctx, 'ui_xp')} **Lv.{state['level']}**"
        if not selected:
            await self._send(
                ctx, "Cửa hàng Ilis Farm", header, badge="ui_coin",
                fields=tuple(
                    (label, f"`{prefix} shop {name}`", True)
                    for name, label in (("farm", "🌱 Nông trại"), ("pet", "🐾 Pet và thức ăn"), ("weapon", "🔪 Vũ khí"))
                ),
            )
            return
        items = []
        for number, key in SHOP_IDS.items():
            item = SHOP[key]
            if item["category"] in selected:
                items.append((number, key, item))
        pages = []
        for first in range(0, len(items), 6):
            title = f"{self.emojis.emoji(ctx, 'ui_muong')} 🛒 CỬA HÀNG ILIS FARM"
            color = art.COLOR if (first // 6) % 2 == 0 else 0xA50018
            embed = discord.Embed(title=title, description=f"{header}\n꒰ 🛒 ꒱ Mua với `{prefix} buy <#số> [số lượng]`", color=color)
            grouped = {}
            for number, key, item in items[first:first + 6]:
                detail = shop_description(item["description"]).replace("`il kill pet`", f"`{prefix} kill pet`")
                grouped.setdefault(item["category"], []).append(
                    f"`#{number}` {shop_icon(self.emojis, ctx, key)} **{item['name']}** · **{vnd(item['coin']):,} VND**\n꒰ ✦ ꒱ _{detail}_"
                )
            for section, lines in grouped.items():
                embed.add_field(name=categories[section], value="\n".join(lines), inline=False)
            embed.set_footer(text=f"🥀 {prefix} buy <#số> [số lượng]")
            pages.append(embed)
        await self._pages(ctx, pages)

    @farm.command(name="buy", aliases=["by", "mua"], brief="Mua theo mã hàng trong shop")
    async def buy(self, ctx, item: str, quantity: int = 1):
        await self._play(ctx, FarmSession.buy, item, quantity, render=lambda r: f"Đã mua **{r[0]} ×{quantity}** với giá **{vnd(r[1]):,} VND**.")

    @farm.command(name="plant", aliases=["pl", "trồng", "trong"], brief="Trồng theo mã cây hoặc trồng all từ kho")
    async def plant(self, ctx, crop: str | None = None, quantity: str = "1"):
        if crop is None:
            await self._send(ctx, "Cây trồng", "\n".join(
                f"`#{number}` {data['emoji']} **{data['name']}** · {vnd(data['seedCost']):,} VND"
                for number, data in enumerate(CROPS.values(), 1)
            ))
            return
        value = quantity.lower()
        amount = "all" if value in ALL_WORDS else int(value) if value.isascii() and value.isdecimal() and len(value) <= 9 else 0
        await self._play(
            ctx, FarmSession.plant, crop, amount, title="Đã trồng",
            render=lambda r: "\n".join(
                f"{CROPS[key]['emoji']} **{CROPS[key]['name']} ×{count}** · <t:{int(ready)}:R>"
                for key, count, ready in r[0]
            ) + (f"\nMua thêm hạt giống **{vnd(r[1]):,} VND**" if r[1] else ""),
        )

    @farm.command(name="water", aliases=["wt", "tuoi", "tưới"], brief="Tưới tất cả ô đủ điều kiện")
    async def water(self, ctx):
        await self._play(ctx, FarmSession.tend, render=lambda r: f"Đã tưới **{r[0]} ô** · Giảm {r[1]}% thời gian còn lại.")

    @farm.command(name="friend", brief="Thăm nông trại người khác, tưới giúp hoặc lấy một cây chín")
    async def friend(self, ctx, member: discord.Member, activity: str | None = None):
        try:
            if member.id == ctx.author.id or member.bot:
                raise FarmError("Chọn nông trại của một người chơi khác.")
            if activity:
                result = self.store.visit(ctx.author.id, member.id, activity.lower())
                await self._send(ctx, "Ghé nông trại", result)
                return
            visitor = self.store.get(ctx.author.id)
            try:
                target = self.store.get(member.id)
            except FarmError as error:
                raise FarmError("Người này chưa có nông trại.") from error
        except FarmError as error:
            await self._error(ctx, error)
            return
        today = day_at(time.time()).isoformat()
        watered = set(visitor["watered_friends"]) if visitor["visits_day"] == today else set()
        robbed = set(visitor["robbed_friends"]) if visitor["visits_day"] == today else set()
        visited = watered | robbed
        at_limit = len(visited) >= 3 and member.id not in visited
        now = time.time()
        growing = any(plot["ready"] > now for plot in target["plots"].values())
        ready = any(plot["ready"] <= now for plot in target["plots"].values())

        async def choose(interaction, selection):
            if self.store.economy.is_banned(ctx.author.id):
                await self._choice_message(interaction, "❌ Tài khoản Casino đang bị khóa.")
                return
            try:
                result = self.store.visit(ctx.author.id, member.id, selection)
            except FarmError as error:
                result = f"❌ {error}"
            await self._choice_message(interaction, result, "Ghé nông trại")

        choices = FarmChoices(ctx.author.id, (
            ("water", "💧 Tưới nước", discord.ButtonStyle.primary, at_limit or not growing or member.id in watered),
            ("rob", "🌾 Cướp mùa vụ", discord.ButtonStyle.danger, at_limit or not ready or member.id in robbed),
        ), choose, timeout=30)
        await self._show_plots(ctx, member, target, view=choices)

    @farm.command(name="fertilize", aliases=["fer", "fert", "ft", "bon", "bón"], brief="Bón phân thường, cao cấp hoặc đặc biệt")
    async def fertilize(self, ctx, fertilizer: str | None = None):
        if fertilizer is None:
            await self._send(ctx, "Phân bón", "\n".join(
                f"`{kind}` · Giảm {int(factor * 100)}% thời gian còn lại"
                for kind, factor in CATALOG["FERTILIZER_TIME_REDUCTION"].items()
            ))
            return
        await self._play(ctx, FarmSession.tend, fertilizer, render=lambda r: f"Đã bón phân cho **{r[0]} ô** · Giảm {r[1]}% thời gian còn lại.")

    @farm.command(name="harvest", aliases=["hv", "h", "gặt", "gat", "thu"], brief="Thu hoạch theo số ô hoặc all")
    async def harvest(self, ctx, plot: str = "all"):
        await self._play(
            ctx, FarmSession.harvest, plot.lower().lstrip("#"),
            render=lambda r: "\n".join(f"{inventory_name(self.emojis, ctx, f'crop:{key}')} **×{qty}**" for key, qty in r[0].items()) + f"\n+{r[1]} XP",
        )

    @farm.command(name="sell", aliases=["sl", "bán", "ban"], brief="Bán nông sản theo mã cây hoặc all")
    async def sell(self, ctx, crop: str | None = None, quantity: int = 1):
        if crop is None:
            await self._send(ctx, "Bán nông sản", "\n".join(
                f"`#{index}` {data['emoji']} {data['name']} · {vnd(data['sellValue']):,} VND giá cơ sở"
                for index, data in enumerate(CROPS.values(), 1)
            ))
            return
        await self._play(
            ctx, FarmSession.sell, "all" if crop.lower() in ALL_WORDS else crop, quantity,
            render=lambda r: f"Đã bán **{r[0]} nông sản** với giá **{vnd(r[1]):,} VND**.",
        )

    @farm.command(name="inventory", aliases=["inv", "i", "kho"], brief="Xem kho đồ hoặc kho cá với tham số fish")
    async def inventory(self, ctx, category: str = "items"):
        state = await self._player(ctx)
        if state is None:
            return
        if category.lower() in {"fish", "f"}:
            lines = [
                f"`#{key}` {self.emojis.emoji(ctx, 'fish_' + fish['type'])} {FISH[fish['type']]['name']} · {fish['weight']} kg · {vnd(fish['price']):,} VND giá gốc"
                for key, fish in sorted(state["fish"].items(), key=lambda item: int(item[0]))
            ]
            title = "🎣 Kho thủy sản"
            total = f"**{len(lines)} cá**"
        else:
            title = f"📦 KHO ĐỒ — {ctx.author.display_name}"
            inventory = state["inventory"]
            total = f"**{inventory_size(inventory)}/{INVENTORY_CAPACITY}** vật phẩm"
            lines = []
            for kind, name in (("crop", "🌾 Nông sản"), ("seed", "🌱 Hạt giống"), ("food", "🍖 Thức ăn"),
                               ("fertilizer", "🥄 Phân bón"), ("fishing", "🎣 Cần câu"),
                               ("weapon", "🔪 Vũ khí"), ("junk", "📦 Đồ vớt được")):
                items = [(key, qty) for key, qty in inventory.items() if key.startswith(f"{kind}:")]
                if items:
                    lines.append(f"**{name}**")
                    lines.extend(f"{inventory_name(self.emojis, ctx, entry)} ×{qty}" for entry, qty in items)
        if not lines:
            lines = ["Kho trống."]
        pages = [discord.Embed(title=title, description=f"{total}\n\n" + "\n".join(lines[index:index + 12]), color=art.COLOR)
                 for index in range(0, len(lines), 12)]
        prefix = f"{ctx.clean_prefix}farm"
        for page in pages:
            if category.lower() not in {"fish", "f"}:
                page.add_field(name="🌸 Chất lượng", value="⚪ Thường　🟢 Hiếm nhẹ　🔵 Hiếm　🟣 Sử thi　🟡 Huyền thoại", inline=False)
            page.set_footer(text=f"🥀 {prefix} sell <cây> · {prefix} inv f · {prefix} selff <id>")
        await self._pages(ctx, pages)

    @farm.command(name="discard", brief="Bỏ rác câu cá khỏi kho")
    async def discard(self, ctx, item: str, quantity: int = 1):
        await self._play(ctx, FarmSession.discard_junk, item.lower(), quantity, render=lambda _: f"Đã bỏ **{quantity} vật phẩm**.")

    @farm.command(name="equip", aliases=["eq", "use"], brief="Trang bị cần câu đã mua")
    async def equip(self, ctx, rod: str):
        await self._play(ctx, FarmSession.equip, rod, render=lambda name: f"Đã trang bị **{name}**.")

    @farm.command(name="fish", aliases=["fishing", "câu"], brief="Câu cá với cần đang trang bị hoặc mã cần chỉ định")
    async def fish(self, ctx, rod: str | None = None):
        await self._play(
            ctx, FarmSession.fishing, rod, title="Kết quả câu cá", badge="rod_common",
            render=lambda r: f"{self.emojis.emoji(ctx, r[2], '🎣')} {r[0]}\n{self.emojis.emoji(ctx, 'ui_xp')} **+{r[1]} XP**",
            media=lambda r: (art.thumbnail(r[2]), None),
        )

    @farm.command(name="sellfish", aliases=["selff", "self", "sf"], brief="Bán cá theo ID hoặc all")
    async def sellfish(self, ctx, fish: str):
        await self._play(
            ctx, FarmSession.sell_fish, fish.lower(),
            render=lambda r: f"Đã bán **{r[0]} cá** với giá **{vnd(r[1]):,} VND**.",
        )

    @farm.command(name="pet", aliases=["p", "pets"], brief="Mở album pet, chọn theo số hoặc mã pet")
    async def pet(self, ctx, pet_id: str | None = None):
        state = await self._player(ctx)
        if state is None:
            return
        roster = tuple(PETS)
        selected = roster[0]
        if pet_id:
            value = pet_id.lower().lstrip("#")
            selected = value
            if value.isascii() and value.isdecimal() and len(value) <= 2:
                index = int(value) - 1
                selected = roster[index] if 0 <= index < len(roster) else ""
            if selected not in PETS:
                await self._error(ctx, FarmError(f"Chọn số pet từ 1 đến {len(roster)} hoặc nhập mã pet."))
                return
        pages = [pet_album_page(ctx, self.emojis, state, key) for key in roster]
        await self._pages(ctx, pages, start=roster.index(selected))

    @farm.command(name="petinfo", aliases=["pi"], brief="Xem độ no, hạnh phúc và sức khỏe pet đã sở hữu")
    async def petinfo(self, ctx, pet_id: str | None = None):
        try:
            with self.store.action(ctx.author.id, "petinfo") as farm:
                key, pet = farm.pet_status(pet_id)
        except FarmError as error:
            await self._error(ctx, error)
            return
        await self._send(
            ctx, "Thông tin pet", format_pet(self.emojis, ctx, key, pet),
            badge=f"pet_{key}", thumbnail=art.thumbnail(f"pet_{key}"),
        )

    @farm.command(name="petlist", aliases=["ptl", "petinfo_all"], brief="Xem danh sách pet đã sở hữu")
    async def petlist(self, ctx, order: str = "rarity"):
        state = await self._player(ctx)
        if state is None:
            return
        pets = state["pets"]
        if not pets:
            await self._error(ctx, FarmError("Bạn chưa có pet. Dùng `farm gacha` để nhận pet."))
            return
        rarity = {name: index for index, name in enumerate(("common", "uncommon", "rare", "epic", "mythic", "legendary"))}
        order = order.lower()
        if order == "name":
            keys = sorted(pets, key=lambda key: PETS[key]["name"].casefold())
        elif order == "level":
            keys = sorted(pets, key=lambda key: (-pets[key]["level"], -pets[key]["stars"]))
        else:
            keys = sorted(pets, key=lambda key: (-rarity[PETS[key]["rarity"]], -pets[key]["level"]))
        pages = []
        for start in range(0, len(keys), 5):
            lines = []
            for key in keys[start:start + 5]:
                pet = pets[key]
                lines.append(
                    f"`#{tuple(PETS).index(key) + 1}` {self.emojis.emoji(ctx, f'pet_{key}')} **{PETS[key]['name']}**"
                    f" · Cấp {pet['level']} · C{pet['stars']}"
                    + (" · Đang hoạt động" if key == state["active_pet"] else "")
                )
            embed = discord.Embed(title="🐾 Kho pet", description="\n".join(lines), color=art.COLOR)
            embed.set_footer(text=f"{art.FOOTER} · {len(keys)} pet")
            pages.append(embed)
        await self._pages(ctx, pages)

    @farm.command(name="selectpet", aliases=["switchpet", "activatepet", "sp"], brief="Chọn pet đang hoạt động theo số hoặc mã")
    async def selectpet(self, ctx, pet: str | None = None):
        if pet is None:
            await self.petlist.callback(self, ctx)
            return
        key = f"pet_{pet_key(pet)}"
        await self._play(
            ctx, FarmSession.select_pet, pet,
            render=lambda name: f"{self.emojis.emoji(ctx, key)} Đã chọn **{name}**.",
            media=lambda _: (art.thumbnail(key), None),
        )

    async def _care(self, ctx, activity: str, title: str, food: str = "") -> None:
        await self._play(
            ctx, FarmSession.care, activity, food, title=title,
            render=lambda r: format_pet(self.emojis, ctx, r[0], r[1]) + ("\n\n🥀 **Huyn đã thức dậy.**" if r[2] else ""),
            media=lambda r: (art.thumbnail(f"pet_{r[0]}"), art.image("pet_hr") if r[2] else art.action_image(activity)),
        )

    @farm.command(name="feed", aliases=["fd"], brief="Cho pet ăn bằng thức ăn từ kho")
    async def feed(self, ctx, food: str | None = None):
        if food is None:
            await self.shop.callback(self, ctx, "food")
            return
        await self._care(ctx, "feed", "Cho pet ăn", food)

    @farm.command(name="play", aliases=["py", "chơi", "choi"], brief="Chơi với pet")
    async def play(self, ctx):
        await self._care(ctx, "play", "Chơi với pet")

    @farm.command(name="cuddle", aliases=["nung", "ng", "nựng", "nứng"], brief="Nựng pet")
    async def cuddle(self, ctx):
        await self._care(ctx, "cuddle", "Nựng pet")

    @farm.command(name="kiss", aliases=["hon", "hôn", "k"], brief="Hôn pet để tăng hạnh phúc")
    async def kiss(self, ctx):
        await self._care(ctx, "kiss", "Hôn pet")

    @farm.command(name="exercise", aliases=["td"], brief="Cho pet tập luyện")
    async def exercise(self, ctx):
        await self._care(ctx, "exercise", "Tập luyện với pet")

    @farm.command(name="killpet", aliases=["kill", "kp"], brief="Dùng dao giảm một cung mệnh pet khi đang dùng Satou")
    async def killpet(self, ctx, kind: str, pet: str | None = None):
        if kind.lower() != "pet" or not pet:
            await self._error(ctx, FarmError("Dùng `farm kill pet <mã pet>`. Cần Satou đang hoạt động, dao #400 và pet từ C1."))
            return
        await self._play(
            ctx, FarmSession.kill_pet, pet, title="🔪 Cơ chế Satou",
            render=lambda r: f"**{r[0]}** · C{r[1] + 1} → **C{r[1]}**\n"
            + ("Đã mở cơ chế khóa pet 24 giờ mỗi lần chọn Satou." if r[2] >= 5 else f"Tiến độ **{r[2]}/5**."),
        )

    @farm.command(name="update", aliases=["upd"], brief="Nhận 10 vé gacha cập nhật Mùa 2 một lần")
    async def update(self, ctx):
        await self._play(
            ctx, FarmSession.update_reward, title="🌹 Cập nhật Mùa 2", badge="ui_gacha",
            render=lambda tickets: f"Đã nhận **10 vé gacha**. Vé hiện tại **{tickets}**.\nKuromi · Melody · Satou · Shio · Tuất · Thao Thiết",
        )

    @farm.command(name="cheat", aliases=["cht"], hidden=True)
    @commands.is_owner()
    async def cheat(self, ctx, member: discord.Member, action: str = "info", *args: str):
        if action.lower() in {"clearall", "reset"}:
            async def choose(interaction, selection):
                if selection == "cancel":
                    await self._choice_message(interaction, "Đã hủy thao tác quản trị.")
                    return
                if not await ctx.bot.is_owner(interaction.user):
                    await self._choice_message(interaction, "❌ Thiếu quyền quản trị.")
                    return
                try:
                    with self.store.action(member.id, "cheat") as session:
                        result = session.farm_admin(action.lower(), args)
                except FarmError as error:
                    result = str(error)
                await self._choice_message(interaction, result, "Quản trị Farm")

            view = FarmChoices(ctx.author.id, (
                ("accept", "Xác nhận", discord.ButtonStyle.danger, False),
                ("cancel", "Hủy", discord.ButtonStyle.secondary, False),
            ), choose, timeout=30)
            what = "kho đồ" if action.lower() == "clearall" else "các ô đất"
            await self._send(ctx, "Xác nhận quản trị Farm", f"Dọn trống {what} của <@{member.id}>?", view=view)
            return
        try:
            with self.store.action(member.id, "cheat") as session:
                result = session.farm_admin(action.lower(), args)
        except FarmError as error:
            await self._error(ctx, error)
            return
        except (IndexError, ValueError):
            await self._error(ctx, FarmError("Thiếu tham số hoặc tham số không hợp lệ. Xem `farm adhelp`."))
            return
        await self._send(ctx, "Quản trị Farm", f"<@{member.id}>\n{result}")

    @farm.command(name="hr", hidden=True)
    @commands.is_owner()
    async def hr(self, ctx, state: str = ""):
        if state.lower() in {"on", "off"}:
            self.store.economy.set_setting("farm_huyn", "1" if state.lower() == "on" else "0")
        enabled = self.store.economy.get_setting("farm_huyn", "1") == "1"
        await self._send(ctx, "Huyn", "Đang bật lời thoại Huyn." if enabled else "Đang tắt lời thoại Huyn.", badge="pet_hr")

    @farm.command(name="adhelp", hidden=True)
    @commands.is_owner()
    async def farm_adhelp(self, ctx):
        prefix = f"{ctx.clean_prefix}farm"
        await self._send(ctx, "Quản trị Farm", "\n".join((
            f"`{prefix} cheat @người <info|coin|setcoin|xp|setlevel|pull>`",
            f"`{prefix} cheat @người <seed|food|rod|item|pet|takepet> <mã> [số lượng]`",
            f"`{prefix} cheat @người gachapet <pet> <số lượt>`",
            f"`{prefix} cheat @người <ready|reset|resync|clear|clearall|cleanup|fishcd|unlockpet>`",
            f"`{prefix} hr <on|off>` · Bật hoặc tắt lời thoại Huyn.",
        )))

    @farm.command(name="cheatcoin", hidden=True)
    @commands.is_owner()
    async def cheatcoin(self, ctx, amount: int):
        await self._play(ctx, FarmSession.farm_admin, "setcoin", (str(amount),), title="Quản trị Farm", render=str)

    @farm.command(name="cheatlevel", hidden=True)
    @commands.is_owner()
    async def cheatlevel(self, ctx, level: int):
        await self._play(ctx, FarmSession.farm_admin, "setlevel", (str(level),), title="Quản trị Farm", render=str)

    @farm.command(name="cheatxp", hidden=True)
    @commands.is_owner()
    async def cheatxp(self, ctx, amount: int):
        await self._play(ctx, FarmSession.farm_admin, "xp", (str(amount),), title="Quản trị Farm", render=str)

    @farm.command(name="cheatplant", hidden=True)
    @commands.is_owner()
    async def cheatplant(self, ctx, crop: str = "lua"):
        await self._play(ctx, FarmSession.admin_plant, crop, title="Quản trị Farm", render=str)

    @farm.command(name="cheatharvest", hidden=True)
    @commands.is_owner()
    async def cheatharvest(self, ctx):
        await self._play(ctx, FarmSession.admin_harvest, title="Quản trị Farm", render=str)

    @farm.command(name="cheatskip", aliases=["csk"], hidden=True)
    @commands.is_owner()
    async def cheatskip(self, ctx, member: discord.Member, kind: str):
        try:
            with self.store.action(member.id, "cheatskip") as farm:
                result = farm.admin_skip(kind.lower())
        except FarmError as error:
            await self._error(ctx, error)
            return
        await self._send(ctx, "Quản trị Farm", f"<@{member.id}> · {result}")

    @farm.command(name="ping", brief="Xem độ trễ bot")
    async def ping(self, ctx):
        await self._send(ctx, "🏓 Pong", f"Độ trễ Discord **{ctx.bot.latency * 1000:.0f} ms**.")

    @farm.command(name="gacha", aliases=["gachapull", "pull", "gp"], brief="Mở nút Roll 1, Roll 10 hoặc quay bằng lệnh")
    async def gacha(self, ctx, count: int | None = None):
        if count is None:
            state = await self._player(ctx)
            if state is not None:
                async def choose(interaction, selection):
                    if selection == "cancel":
                        await self._choice_message(interaction, "Đã hủy lượt quay.", "Gacha Farm")
                        return
                    if self.store.economy.is_banned(ctx.author.id):
                        await self._choice_message(interaction, "❌ Tài khoản Casino đang bị khóa.")
                        return
                    count = int(selection)
                    try:
                        with self.store.action(ctx.author.id, "gacha") as session:
                            result = session.gacha(count)
                    except FarmError as error:
                        await self._choice_message(interaction, f"❌ {error}", "Gacha Farm")
                        return
                    _, gif = self._gacha_media(result)
                    animation = discord.Embed(color=art.COLOR).set_image(url=gif)
                    await interaction.edit_original_response(embed=animation, view=None)
                    await asyncio.sleep(4.8 if gif == art.image("gacha_gif_mythic") else 3.8)
                    await interaction.edit_original_response(embed=self._gacha_card(ctx, count, result, session), view=None)

                view = FarmChoices(ctx.author.id, (
                    ("1", "Roll 1", discord.ButtonStyle.primary, False),
                    ("10", "Roll 10", discord.ButtonStyle.success, False),
                    ("cancel", "Hủy", discord.ButtonStyle.danger, False),
                ), choose, timeout=30)
                tickets = state["tickets"]
                cost = lambda n: f"{n} vé" if tickets >= n else f"{vnd(10_000 * n):,} VND"
                await self._send(
                    ctx, f"{self.emojis.emoji(ctx, 'ui_gacha')} GACHA", "꒰ ✦ ꒱ Thử vận may nào~!",
                    view=view, footer=f"🥀 Chọn trong 30 giây · {ctx.clean_prefix}farm gachrates",
                    fields=(
                        ("🎫 Roll 1", cost(1), True),
                        ("✨ Roll 10", cost(10), True),
                        ("⏳ Pity hiện tại", f"{progress_bar(state['pity'], 100)} **{state['pity']}/100**", False),
                        ("🎯 Bảo hiểm", "Lần thần thoại tới chắc chắn giới hạn." if state["limited"] else "Lần thần thoại tới có 40% cơ hội pet giới hạn.", False),
                    ),
                )
            return

        try:
            with self.store.action(ctx.author.id, "gacha") as session:
                result = session.gacha(count)
        except FarmError as error:
            await self._error(ctx, error)
            return
        card = self._gacha_card(ctx, count, result, session)
        card.set_image(url=self._gacha_media(result)[1])
        await ctx.reply(embed=card, allowed_mentions=discord.AllowedMentions.none())

    def _gacha_card(self, ctx, count, result, session):
        charge = "Đã dùng vé gacha." if result[1] else f"Chi phí **{vnd(10_000 * count):,} VND**."
        key = result[0][0][0]
        if count == 10:
            title = "KẾT QUẢ ROLL 10"
        elif key.startswith("pet_"):
            title = "QUAY GACHA~!"
        elif key == "ui_coin":
            title = "Nhận được VND~!"
        elif key in CROPS:
            title = "Nhận được hạt giống~!"
        else:
            title = "Nhận được vật phẩm~!"
        thumbnail, gif = self._gacha_media(result)
        embed = discord.Embed(
            title=f"{self.emojis.emoji(ctx, 'ui_muong')} {self.emojis.emoji(ctx, 'ui_gacha')} {title}",
            description="\n".join(f"{self.emojis.emoji(ctx, item)} **{label}**" for item, label in result[0]),
            color=0xC2185B if gif == art.image("gacha_gif_mythic") else art.COLOR,
        ).set_footer(text=f"🥀 {ctx.clean_prefix}farm gacha · {ctx.clean_prefix}farm gachrates")
        if thumbnail:
            embed.set_thumbnail(url=thumbnail)
        embed.add_field(name="🎫 Lượt quay", value=charge)
        embed.add_field(name="⏳ Pity", value=f"`{session.state['pity']}/100`")
        embed.add_field(name="🎟️ Vé còn lại", value=f"`{session.state['tickets']}`")
        if session.wallet_delta:
            embed.add_field(name="💰 Thay đổi ví", value=f"`{session.wallet_delta:+,} VND`")
        if session.unlocked:
            embed.add_field(name="🏅 Thành tích mới", value=" · ".join(session.unlocked), inline=False)
        return embed

    @staticmethod
    def _gacha_media(result):
        pets = [key for key, _ in result[0] if key.startswith("pet_")]
        mythic = next((key for key in pets if PETS[key[4:]].get("isMythic")), None)
        thumbnail = art.thumbnail(mythic or (pets[0] if pets else "ui_gacha"))
        return thumbnail, art.image("gacha_gif_mythic" if mythic else "gacha_gif_normal")

    @farm.command(name="quest", aliases=["quests", "qt", "q"], brief="Xem nhiệm vụ hôm nay và phần thưởng tự động")
    async def quest(self, ctx):
        state = await self._player(ctx)
        if state is None:
            return
        today = day_at(time.time())
        quests = state["quests"] if state["quest_day"] == today.isoformat() else daily_quests(ctx.author.id, today)
        lines = []
        total_coins, total_xp, completed = 0, 0, 0
        difficulty = {"easy": "🟢 Dễ", "medium": "🟡 Vừa", "hard": "🔴 Khó"}
        for key, progress in quests.items():
            quest = QUESTS[key]
            target = quest["target"]
            tally = f"{vnd(progress):,}/{vnd(target):,} VND" if quest["type"] == "earn_coin" else f"{progress}/{target}"
            done = progress >= target
            completed += done
            total_coins += quest["coin"]
            total_xp += quest["xp"]
            lines.append(
                f"{'🌸' if done else '🤍'} **{quest['name']}** · {difficulty[quest['diff']]}\n"
                f"{progress_bar(progress, target)} `[{tally}]`\n"
                f"{self.emojis.emoji(ctx, 'ui_coin')} `+{vnd(quest['coin']):,} VND`"
                f"  {self.emojis.emoji(ctx, 'ui_xp')} `+{quest['xp']} XP`"
            )
        await self._send(
            ctx, "🌸 NHIỆM VỤ HẰNG NGÀY", "\n\n".join(lines),
            thumbnail=ctx.author.display_avatar.url, timestamp=discord.utils.utcnow(),
            fields=(
                ("🌹 Tiến trình", f"Hoàn thành `{completed}/{len(quests)}`", True),
                ("🎁 Tổng phần thưởng", f"`{vnd(total_coins):,} VND`\n`{total_xp} XP`", True),
            ), footer="🥀 Đổi lúc 07:00 giờ Việt Nam · Tự nhận thưởng khi hoàn thành",
        )

    @farm.command(name="gacharates", aliases=["gachrates", "gr"], brief="Xem tỷ lệ gacha và mốc bảo hiểm")
    async def gacharates(self, ctx):
        player = await self._player(ctx)
        if player is None:
            return
        total = sum(entry["rate"] for entry in NORMAL_GACHA)
        groups = {}
        for entry in NORMAL_GACHA:
            kind = entry["type"]
            key = f"pet_{entry['id']}" if kind == "pet" else entry["id"]
            icon = self.emojis.emoji(ctx, key, entry.get("emoji", ""))
            rate = entry["rate"] / total * 0.997
            groups.setdefault(entry.get("rarity", kind), []).append(f"{icon} {entry['name']} · **{rate:.2%}**")
        groups["mythic"] = [
            f"{self.emojis.emoji(ctx, 'pet_' + key)} {PETS[key]['name']} · **{rate:.3%}**"
            for key, rate in (("kuromi", .0009), ("melody", .0009), ("satou", .0006), ("shio", .0006))
        ]
        prefix = f"{ctx.clean_prefix}farm"
        title = f"{self.emojis.emoji(ctx, 'ui_gacha')} TỈ LỆ GACHA — Mùa 2"
        pets = discord.Embed(title=f"{title} · Trang 1/2", color=art.COLOR)
        for label, rarities in (("🐾 Pet thường", ("common", "uncommon", "rare", "epic")),
                                ("✨ Season 2", ("legendary", "mythic"))):
            lines = []
            for rarity in rarities:
                lines.extend([f"**{art.PET_RARITY[rarity][0]}**", *groups.get(rarity, [])])
            pets.add_field(name=label, value="\n".join(lines), inline=False)
        pets.set_footer(text="🥀 Pity tăng từ lượt 80 · bảo đảm ở lượt 100")
        items = discord.Embed(title=f"{title} · Trang 2/2", color=art.COLOR)
        for kind, name in (("seed", "🌱 Hạt giống"), ("fertilizer", "🥄 Phân bón"), ("food", "🍖 Thức ăn"), ("coin", "💰 VND")):
            items.add_field(name=name, value="\n".join(groups[kind]), inline=False)
        items.add_field(name="Quay bằng vé", value=f"`{prefix} gacha` · {player['tickets']} vé đang có", inline=True)
        items.add_field(name="Quay có phí", value=f"`{vnd(10_000):,} VND` mỗi lượt", inline=True)
        items.set_footer(text=f"🥀 Ví Casino · {self.store.economy.get_entry(ctx.author.id)[1]:,} VND")
        await self._pages(ctx, [pets, items], rate_pages=True)

    @farm.command(name="levelreward", aliases=["lr", "level_reward", "lvreward"], brief="Nhận vé gacha theo các cấp đã đạt")
    async def levelreward(self, ctx):
        await self._play(ctx, FarmSession.level_reward, render=lambda tickets: f"Đã nhận **{tickets} vé gacha**.")

    @farm.command(name="evolve", aliases=["evo"], brief="Tiến hóa cấp 50 bằng tham số confirm")
    async def evolve(self, ctx, confirm: str = ""):
        if confirm.lower() not in {"confirm", "xácnhận", "xacnhan"}:
            await self._send(
                ctx, "Tiến hóa Farm",
                f"Khi đạt cấp 50, dùng `{ctx.clean_prefix}farm evolve confirm`. "
                "Tiến hóa đưa Farm về cấp 1, xóa cây đang trồng, mở giới hạn cấp 70, "
                "thưởng 10 vé gacha, tăng 20% giá bán nông sản và giảm 10% thời gian trồng.",
            )
            return
        await self._play(ctx, FarmSession.evolve, render=lambda _: "Đã tiến hóa và nhận **10 vé gacha**.")

    @farm.command(name="achievements", aliases=["ach"], brief="Xem toàn bộ thành tích và tiến trình mở khóa")
    async def achievements(self, ctx):
        state = await self._player(ctx)
        if state is None:
            return
        unlocked = set(state["achievements"])
        keys = sorted((key for key in ACHIEVEMENTS if "day_streak" not in key), key=lambda key: key not in unlocked)
        pages = []
        for start in range(0, len(keys), 6):
            entries = []
            for key in keys[start:start + 6]:
                info = ACHIEVEMENTS[key]
                line = f"{'✅' if key in unlocked else '🔒'} **{info['name']}**\n{shop_description(info['desc'])}"
                if key not in unlocked and info["reward"]:
                    line += f" · +{vnd(info['reward']):,} VND khi mở khóa"
                entries.append(line)
            embed = discord.Embed(title="Thành tích Farm", description="\n\n".join(entries), color=0x9B59B6)
            embed.add_field(name="Tiến trình", value=f"{sum(key in unlocked for key in keys)}/{len(keys)} đã mở khóa")
            pages.append(embed)
        await self._pages(ctx, pages)

    @farm.command(name="leaderboard", aliases=["top", "lb"], brief="Bảng xếp hạng ví, cấp, thu nhập Farm và thu hoạch")
    async def leaderboard(self, ctx, metric: str = "coin"):
        metric = metric.lower()
        try:
            scores, rank = self.store.leaderboard(metric, ctx.author.id)
        except FarmError as error:
            await self._error(ctx, error)
            return
        titles = {"coin": "Top ví Casino", "level": "Top cấp độ", "farm": "Top nông dân",
                  "earned": "Top nông dân", "harvested": "Top thu hoạch"}
        lines = []
        for index, (user_id, score, extra, _) in enumerate(scores, 1):
            medal = ["🥇", "🥈", "🥉"][index - 1] if index <= 3 else f"**#{index}**"
            if metric == "coin":
                summary = f"{score:,} VND"
            elif metric in {"earned", "farm"}:
                summary = f"{vnd(score):,} VND"
            elif metric == "level":
                summary = f"Cấp {score}" + (f" v{extra + 1}" if extra else "")
            else:
                summary = f"{score:,}"
            lines.append(f"{medal} <@{user_id}> · {summary}")
        await self._send(
            ctx, titles[metric], "\n".join(lines),
            fields=(("Xếp hạng của bạn", f"**#{rank}**" if rank else "Chưa có hạng", False),),
        )

    @farm.command(name="season", aliases=["sn"], brief="Xem mùa hiện tại và cây được tăng giá")
    async def season(self, ctx):
        season, remaining = season_at(day_at(time.time()))
        await self._send(
            ctx, f"{season['emoji']} {season['name']}",
            f"{season['desc']}\n{season['bonusText']}\nCòn **{remaining} ngày**.", color=season["color"],
        )

    @farm.command(name="events", aliases=["event", "ev"], brief="Xem sự kiện hôm nay")
    async def events(self, ctx):
        event = event_at(day_at(time.time()))
        await self._send(
            ctx, event["name"], f"{event['desc']}\n**{event['effect'].replace('Xu kiếm được', 'VND kiếm được')}**",
            badge="ui_quest", color=event["color"],
        )
