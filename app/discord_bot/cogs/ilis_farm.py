import time

import discord
from discord.ext import commands

from app.discord_bot.modules.farm import art
from app.discord_bot.modules.farm.rules import (
    ACHIEVEMENTS, CROPS, FISH, INVENTORY_CAPACITY, JUNK, NORMAL_GACHA, PETS, QUALITY_NAMES,
    QUESTS, SHOP, SHOP_IDS, START_COINS, daily_quests, day_at, event_at, pet_bonus, season_at,
    update_pet, vnd, xp_required,
)
from app.discord_bot.modules.farm.service import FarmError, FarmSession, FarmStore, plot_limit


def shop_icon(ctx, key: str) -> str:
    item = SHOP[key]
    return art.emoji(ctx, f"pet_{item['petId']}" if item["category"] == "pets" else key)


def inventory_name(ctx, entry: str) -> str:
    category, key = entry.split(":", 1)
    if category == "crop":
        crop, _, quality = key.rpartition("_")
        return f"{art.emoji(ctx, crop)} {CROPS[crop]['name']} ({QUALITY_NAMES[quality]})"
    if category == "junk":
        return f"{JUNK[key]['emoji']} {JUNK[key]['name']} (`{key}`)"
    return f"{shop_icon(ctx, key)} {SHOP[key]['name']}"


def format_pet(ctx, key: str, pet: dict) -> str:
    icon = art.emoji(ctx, f"pet_{key}")
    return (
        f"{icon} **{PETS[key]['name']}** · Cấp {pet['level']} · C{pet['stars']}\n\n"
        f"🍖 **Độ no** {pet['hunger']:.0f}%\n"
        f"💗 **Hạnh phúc** {pet['happiness']:.0f}%\n"
        f"❤️ **Sức khỏe** {pet['health']:.0f}%"
    )


class IlisFarm(commands.Cog):
    """Nông trại Ilis Farm trong Casino Bot."""

    def __init__(self, bot):
        self.store = FarmStore(bot.economy)

    @commands.Cog.listener()
    async def on_command_completion(self, ctx: commands.Context) -> None:
        if ctx.author.bot:
            return
        try:
            await ctx.send(
                f"{art.emoji(ctx, 'ui_farm')} **Nông trại mới!** Gõ `{ctx.clean_prefix}farm` để chơi.",
                delete_after=5,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound):
            return

    async def _send(
        self, ctx, title: str, description: str, *,
        badge: str = "ui_muong", thumbnail: str | None = None, image: str | None = None,
        color: int = art.COLOR, fields: tuple = (),
    ) -> None:
        if not description:
            description = "Chưa có dữ liệu."
        heading = f"{art.emoji(ctx, badge)} {title}"[:256]
        while description:
            split = len(description) if len(description) <= 4000 else description.rfind("\n", 0, 4000)
            if split <= 0:
                split = 4000
            embed = discord.Embed(title=heading, description=description[:split], color=color)
            embed.set_footer(text=art.FOOTER)
            if thumbnail:
                embed.set_thumbnail(url=thumbnail)
            if image:
                embed.set_image(url=image)
            for name, value, inline in fields:
                embed.add_field(name=name, value=value, inline=inline)
            await ctx.send(embed=embed, allowed_mentions=discord.AllowedMentions.none())
            fields, image = (), None
            description = description[split:].lstrip("\n")

    async def _error(self, ctx, error: FarmError) -> None:
        message = str(error).replace("`farm ", f"`{ctx.clean_prefix}farm ")
        await ctx.send(f"❌ {message}", allowed_mentions=discord.AllowedMentions.none())

    async def _player(self, ctx) -> dict | None:
        try:
            return self.store.get(ctx.author.id)
        except FarmError as error:
            await self._error(ctx, error)
            return None

    async def _play(self, ctx, action, *args, render, title="Ilis Farm", badge="ui_muong", media=None) -> None:
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
            description += f"\n{art.emoji(ctx, 'ui_coin')} Ví Casino **{session.wallet_delta:+,} VND**"
        thumbnail, image = media(result) if media else (None, None)
        await self._send(ctx, title, description, badge=badge, thumbnail=thumbnail, image=image)

    async def _show_plots(self, ctx, player, state: dict) -> None:
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
                icon = art.emoji(ctx, crop)
                ready = plot["ready"] <= now
                tiles.append("🌹" if ready else icon)
                status = "Sẵn sàng thu hoạch" if ready else f"<t:{int(plot['ready'])}:R>"
                growing.append(f"`#{index}` {icon} **{CROPS[crop]['name']}** · {status}")
        grid = ["　".join(tiles[i:i + width]) for i in range(0, capacity, width)]
        prefix = f"{ctx.clean_prefix}farm"
        progress = growing or [f"Trồng luống đầu tiên với `{prefix} plant 1`."]
        description = "\n".join([
            "╭───────────────╮", *grid, "╰───────────────╯",
            "⬜ Ô trống　🌱 Đang lớn　🌹 Sẵn sàng", "", *progress,
        ])
        fields = [
            ("🗺️ Ô đất", f"**{len(plots)}/{capacity}** · {width}×{width}", True),
            (f"{art.emoji(ctx, 'ui_xp')} Cấp độ", f"**{level}** · {state['xp']:,} XP", True),
        ]
        if player.id == ctx.author.id:
            wallet = self.store.economy.get_entry(player.id)[1]
            fields.append((f"{art.emoji(ctx, 'ui_coin')} Ví Casino", f"**{wallet:,} VND**", True))
        await self._send(
            ctx, f"Nông trại · {player.display_name}", description,
            thumbnail=player.display_avatar.url, fields=tuple(fields),
        )

    @commands.group(name="farm", invoke_without_command=True, brief="Xem nông trại Ilis Farm")
    async def farm(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            await self._show_plots(ctx, ctx.author, state)

    @farm.command(name="help", brief="Xem danh sách lệnh Farm")
    async def farm_help(self, ctx):
        prefix = f"{ctx.clean_prefix}farm"
        lines = [f"**`{prefix}`** xem nông trại"]
        for cmd in sorted(self.farm.commands, key=lambda item: item.name):
            if cmd.name == "help":
                continue
            signature = cmd.signature
            syntax = f"{prefix} {cmd.name} {signature}".strip()
            lines.append(f"`{syntax}` · {cmd.brief}")
        lines.append(f"`{ctx.clean_prefix}give` · Chuyển VND qua lệnh ví Casino.")
        await self._send(ctx, "Lệnh Ilis Farm", "\n".join(lines), badge="ui_farm")

    @farm.command(name="start", brief="Tạo nông trại và nhận vốn một lần")
    async def start(self, ctx):
        try:
            balance = self.store.start(ctx.author.id)
        except FarmError as error:
            await self._error(ctx, error)
            return
        await self._send(
            ctx, "Nông trại mới",
            f"Đã tạo nông trại và cộng **{vnd(START_COINS):,} VND** vào ví Casino.\n"
            f"Số dư **{balance:,} VND**\n"
            f"Dùng `{ctx.clean_prefix}farm plant 1` để trồng rau muống.",
            thumbnail=ctx.author.display_avatar.url,
        )

    @farm.command(name="balance", aliases=["bal"], brief="Xem ví Casino, đá quý và vé Farm")
    async def balance(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            balance = self.store.economy.get_entry(ctx.author.id)[1]
            await self._send(
                ctx, "Ví và tài sản Farm",
                f"{art.emoji(ctx, 'ui_coin')} **Ví Casino** · {balance:,} VND\n"
                f"{art.emoji(ctx, 'ui_gem')} **Đá quý** · {state['gems']}\n"
                f"{art.emoji(ctx, 'ui_gacha')} **Vé gacha** · {state['tickets']}",
                thumbnail=ctx.author.display_avatar.url,
            )

    @farm.command(name="profile", brief="Xem tiến trình Farm")
    async def profile(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            level = state["level"]
            cap = 70 if state["evolutions"] else 50
            xp = f"{state['xp']:,}/{xp_required(level, state['evolutions']):,} XP" if level < cap else "Cấp tối đa"
            await self._send(
                ctx, "Tiến trình Farm",
                f"**Cấp {level}** · {xp} · Tiến hóa {state['evolutions']}\n"
                f"Đã trồng {state['planted']:,} · Đã thu hoạch {state['harvested']:,} · Đã bán {state['sold']:,}\n"
                f"Tổng thu nhập ghi nhận **{vnd(state['earned']):,} VND** · Chuỗi điểm danh {state['streak']} ngày",
                badge="ui_xp", thumbnail=ctx.author.display_avatar.url,
            )

    @farm.command(name="daily", brief="Điểm danh nhận VND và vé gacha")
    async def daily(self, ctx):
        await self._play(
            ctx, FarmSession.daily, title="Quà điểm danh", badge="ui_coin",
            render=lambda r: (
                f"Chuỗi điểm danh **{r[1]} ngày**\n"
                f"{art.emoji(ctx, 'ui_coin')} **{vnd(r[0]):,} VND**\n"
                f"{art.emoji(ctx, 'ui_gacha')} **1 vé gacha**"
            ),
            media=lambda _: (ctx.author.display_avatar.url, None),
        )

    @farm.command(name="shop", brief="Xem giá hạt giống, pet, thức ăn, phân bón và cần câu")
    async def shop(self, ctx):
        categories = {
            "seeds": "🌱 Hạt giống", "pets": "🐾 Pet", "food": "🍖 Thức ăn",
            "fertilizer": "🧺 Phân bón", "fishing": "🎣 Cần câu",
        }
        sections = {category: [] for category in categories}
        for number, key in SHOP_IDS.items():
            item = SHOP[key]
            sections[item["category"]].append(
                f"`#{number}` {shop_icon(ctx, key)} {item['name']} · **{vnd(item['coin']):,} VND**"
            )
        fields = tuple(
            (categories[category], "\n".join(items), False) for category, items in sections.items()
        )
        await self._send(
            ctx, "Cửa hàng Farm", f"`{ctx.clean_prefix}farm buy <mã> [số lượng]`",
            badge="ui_coin", fields=fields,
        )

    @farm.command(name="buy", brief="Mua theo mã hàng trong shop")
    async def buy(self, ctx, item: str, quantity: int = 1):
        await self._play(ctx, FarmSession.buy, item, quantity, render=lambda r: f"Đã mua **{r[0]} ×{quantity}** với giá **{vnd(r[1]):,} VND**.")

    @farm.command(name="plant", brief="Trồng theo mã hạt giống trong shop")
    async def plant(self, ctx, crop: str, quantity: int = 1):
        await self._play(
            ctx, FarmSession.plant, crop, quantity,
            render=lambda r: f"Đã trồng **{r[0]} ×{quantity}** · Thu hoạch <t:{int(r[1])}:R>"
            + (f" · Mua thêm hạt giống **{vnd(r[2]):,} VND**" if r[2] else ""),
        )

    @farm.command(name="water", brief="Tưới tất cả ô đủ điều kiện")
    async def water(self, ctx):
        await self._play(ctx, FarmSession.tend, render=lambda r: f"Đã tưới **{r[0]} ô** · Giảm {r[1]}% thời gian còn lại.")

    @farm.command(name="friend", brief="Thăm nông trại người khác, tưới giúp hoặc lấy một cây chín")
    async def friend(self, ctx, member: discord.Member, activity: str | None = None):
        try:
            if activity:
                result = self.store.visit(ctx.author.id, member.id, activity.lower())
                await self._send(ctx, "Ghé nông trại", result)
                return
            self.store.get(ctx.author.id)
            try:
                target = self.store.get(member.id)
            except FarmError as error:
                raise FarmError("Người này chưa có nông trại.") from error
        except FarmError as error:
            await self._error(ctx, error)
            return
        await self._show_plots(ctx, member, target)

    @farm.command(name="fertilize", brief="Bón phân thường, cao cấp hoặc đặc biệt")
    async def fertilize(self, ctx, fertilizer: str):
        await self._play(ctx, FarmSession.tend, fertilizer, render=lambda r: f"Đã bón phân cho **{r[0]} ô** · Giảm {r[1]}% thời gian còn lại.")

    @farm.command(name="harvest", brief="Thu hoạch theo số ô hoặc all")
    async def harvest(self, ctx, plot: str = "all"):
        await self._play(
            ctx, FarmSession.harvest, plot.lower().lstrip("#"),
            render=lambda r: "\n".join(f"{inventory_name(ctx, f'crop:{key}')} **×{qty}**" for key, qty in r[0].items()) + f"\n+{r[1]} XP",
        )

    @farm.command(name="sell", brief="Bán nông sản theo mã cây hoặc all")
    async def sell(self, ctx, crop: str, quantity: int = 1):
        await self._play(
            ctx, FarmSession.sell, crop, quantity,
            render=lambda r: f"Đã bán **{r[0]} nông sản** với giá **{vnd(r[1]):,} VND**.",
        )

    @farm.command(name="inventory", aliases=["inv"], brief="Xem kho đồ hoặc kho cá với tham số fish")
    async def inventory(self, ctx, category: str = "items"):
        state = await self._player(ctx)
        if state is None:
            return
        if category.lower() in {"fish", "f"}:
            lines = [
                f"`#{key}` {art.emoji(ctx, 'fish_' + fish['type'])} {FISH[fish['type']]['name']} · {fish['weight']} kg · {vnd(fish['price']):,} VND giá gốc"
                for key, fish in state["fish"].items()
            ]
            await self._send(ctx, "Kho cá", "\n".join(lines))
            return
        inventory = state["inventory"]
        lines = [f"**{sum(inventory.values())}/{INVENTORY_CAPACITY}** vật phẩm"]
        lines.extend(f"{inventory_name(ctx, entry)} ×{quantity}" for entry, quantity in sorted(inventory.items()))
        await self._send(ctx, "Kho đồ Farm", "\n".join(lines))

    @farm.command(name="discard", brief="Bỏ rác câu cá khỏi kho")
    async def discard(self, ctx, item: str, quantity: int = 1):
        await self._play(ctx, FarmSession.discard_junk, item.lower(), quantity, render=lambda _: f"Đã bỏ **{quantity} vật phẩm**.")

    @farm.command(name="equip", brief="Trang bị cần câu đã mua")
    async def equip(self, ctx, rod: str):
        await self._play(ctx, FarmSession.equip, rod, render=lambda name: f"Đã trang bị **{name}**.")

    @farm.command(name="fish", aliases=["fishing"], brief="Câu cá với cần đang trang bị hoặc mã cần chỉ định")
    async def fish(self, ctx, rod: str | None = None):
        await self._play(
            ctx, FarmSession.fishing, rod, title="Kết quả câu cá", badge="rod_common",
            render=lambda r: f"{art.emoji(ctx, r[2], '🎣')} {r[0]}\n{art.emoji(ctx, 'ui_xp')} **+{r[1]} XP**",
            media=lambda r: (art.thumbnail(r[2]), None),
        )

    @farm.command(name="sellfish", aliases=["selff"], brief="Bán cá theo ID hoặc all")
    async def sellfish(self, ctx, fish: str):
        await self._play(
            ctx, FarmSession.sell_fish, fish.lower(),
            render=lambda r: f"Đã bán **{r[0]} cá** với giá **{vnd(r[1]):,} VND**.",
        )

    @farm.command(name="pet", aliases=["petlist"], brief="Xem danh sách pet hoặc chi tiết theo mã")
    async def pet(self, ctx, pet_id: str | None = None):
        state = await self._player(ctx)
        if state is None:
            return
        pets = state["pets"]
        if pet_id:
            key = pet_id.lower()
            if key not in pets:
                await self._error(ctx, FarmError("Bạn chưa sở hữu pet có mã này."))
                return
            pet = pets[key]
            update_pet(pet, pet_bonus(key, pet), time.time())
            await self._send(
                ctx, "Thông tin pet", format_pet(ctx, key, pet),
                badge=f"pet_{key}", thumbnail=art.thumbnail(f"pet_{key}"),
            )
            return
        lines = [
            f"{art.emoji(ctx, f'pet_{key}')} `{key}` **{PETS[key]['name']}** · Cấp {pet['level']} · C{pet['stars']}"
            + (" · Đang hoạt động" if key == state["active_pet"] else "")
            for key, pet in pets.items()
        ]
        active = state["active_pet"]
        await self._send(
            ctx, "Pet Farm", "\n".join(lines),
            thumbnail=art.thumbnail(f"pet_{active}") if active else None,
        )

    @farm.command(name="selectpet", brief="Chọn pet đang hoạt động")
    async def selectpet(self, ctx, pet: str):
        key = f"pet_{pet.lower()}"
        await self._play(
            ctx, FarmSession.select_pet, pet,
            render=lambda name: f"{art.emoji(ctx, key)} Đã chọn **{name}**.",
            media=lambda _: (art.thumbnail(key), None),
        )

    async def _care(self, ctx, activity: str, title: str, food: str = "") -> None:
        await self._play(
            ctx, FarmSession.care, activity, food, title=title,
            render=lambda r: format_pet(ctx, *r),
            media=lambda r: (art.thumbnail(f"pet_{r[0]}"), art.action_image(activity)),
        )

    @farm.command(name="feed", brief="Cho pet ăn bằng thức ăn từ kho")
    async def feed(self, ctx, food: str):
        await self._care(ctx, "feed", "Cho pet ăn", food)

    @farm.command(name="play", brief="Chơi với pet")
    async def play(self, ctx):
        await self._care(ctx, "play", "Chơi với pet")

    @farm.command(name="cuddle", aliases=["nung"], brief="Nựng pet")
    async def cuddle(self, ctx):
        await self._care(ctx, "cuddle", "Nựng pet")

    @farm.command(name="exercise", brief="Cho pet tập luyện")
    async def exercise(self, ctx):
        await self._care(ctx, "exercise", "Tập luyện với pet")

    @farm.command(name="gacha", brief="Xem giá và vé, hoặc quay 1 hay 10 lượt")
    async def gacha(self, ctx, count: int | None = None):
        if count is None:
            state = await self._player(ctx)
            if state is not None:
                await self._send(
                    ctx, "Gacha Farm",
                    f"**{state['tickets']} vé** · Bảo hiểm **{state['pity']}/100**\n"
                    f"Dùng `{ctx.clean_prefix}farm gacha 1` hoặc `{ctx.clean_prefix}farm gacha 10`. "
                    f"Mỗi lượt dùng **1 vé** hoặc **{vnd(10_000):,} VND**.",
                    badge="ui_gacha", thumbnail=art.thumbnail("ui_gacha"),
                )
            return

        def gacha_media(result):
            pets = [key for key, _ in result[0] if key.startswith("pet_")]
            mythic = next((key for key in pets if PETS[key[4:]].get("isMythic")), None)
            thumbnail = art.thumbnail(mythic or (pets[0] if pets else "ui_gacha"))
            return thumbnail, art.image("gacha_gif_mythic" if mythic else "gacha_gif_normal")

        await self._play(
            ctx, FarmSession.gacha, count, title="Kết quả gacha", badge="ui_gacha",
            render=lambda r: (
                ("Đã dùng vé gacha.\n" if r[1] else f"Chi phí **{vnd(10_000 * count):,} VND**.\n")
                + "\n".join(f"{art.emoji(ctx, key)} **{label}**" for key, label in r[0])
            ),
            media=gacha_media,
        )

    @farm.command(name="quest", aliases=["quests"], brief="Xem nhiệm vụ hôm nay và phần thưởng tự động")
    async def quest(self, ctx):
        state = await self._player(ctx)
        if state is None:
            return
        today = day_at(time.time())
        quests = state["quests"] if state["quest_day"] == today.isoformat() else daily_quests(ctx.author.id, today)
        lines = []
        for key, progress in quests.items():
            quest = QUESTS[key]
            target = quest["target"]
            tally = f"{vnd(progress):,}/{vnd(target):,} VND" if quest["type"] == "earn_coin" else f"{progress}/{target}"
            detail = "Kiếm VND từ bán hàng" if quest["type"] == "earn_coin" else quest["desc"]
            lines.append(
                f"{'✅' if progress >= target else '▫️'} **{quest['name']}** · {detail} ({tally})"
                f" · {vnd(quest['coin']):,} VND + {quest['xp']} XP"
            )
        await self._send(ctx, "Nhiệm vụ Farm · Đổi lúc 07:00 giờ Việt Nam", "\n".join(lines), badge="ui_quest")

    @farm.command(name="gacharates", brief="Xem tỷ lệ gacha và mốc bảo hiểm")
    async def gacharates(self, ctx):
        total = sum(entry["rate"] for entry in NORMAL_GACHA)
        lines = [
            "Pet thần thoại có tỷ lệ cơ bản **0,3%**, tăng từ lượt 80 và chắc chắn ở lượt 100.",
            "Sau một pet thần thoại thường, pet thần thoại tiếp theo sẽ là loại giới hạn.",
            "",
            "**Tỷ lệ phần thưởng nếu lượt quay thuộc nhóm thường**",
        ]
        for entry in NORMAL_GACHA:
            key = entry["id"]
            icon = art.emoji(ctx, f"pet_{key}" if entry["type"] == "pet" else key, entry.get("emoji", ""))
            lines.append(f"{icon} {entry['name']} · {entry['rate'] / total:.2%}")
        await self._send(ctx, "Tỷ lệ gacha Farm", "\n".join(lines), badge="ui_gacha")

    @farm.command(name="levelreward", brief="Nhận vé gacha theo các cấp đã đạt")
    async def levelreward(self, ctx):
        await self._play(ctx, FarmSession.level_reward, render=lambda tickets: f"Đã nhận **{tickets} vé gacha**.")

    @farm.command(name="evolve", brief="Tiến hóa cấp 50 bằng tham số confirm")
    async def evolve(self, ctx, confirm: str = ""):
        if confirm.lower() != "confirm":
            await self._send(
                ctx, "Tiến hóa Farm",
                f"Khi đạt cấp 50, dùng `{ctx.clean_prefix}farm evolve confirm`. "
                "Tiến hóa đưa Farm về cấp 1, xóa cây đang trồng, mở giới hạn cấp 70, "
                "thưởng 10 vé gacha, tăng 20% giá bán nông sản và giảm 10% thời gian trồng.",
            )
            return
        await self._play(ctx, FarmSession.evolve, render=lambda _: "Đã tiến hóa và nhận **10 vé gacha**.")

    @farm.command(name="achievements", brief="Xem thành tích Farm đã mở khóa")
    async def achievements(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            await self._send(ctx, "Thành tích Farm", "\n".join(ACHIEVEMENTS[key]["name"] for key in state["achievements"]))

    @farm.command(name="leaderboard", aliases=["top"], brief="Xếp hạng Farm theo level, harvested hoặc earned")
    async def leaderboard(self, ctx, metric: str = "level"):
        try:
            scores = self.store.leaderboard(metric.lower())
        except FarmError as error:
            await self._error(ctx, error)
            return
        lines = [
            f"**{index}.** <@{user_id}> · {f'{vnd(score):,} VND' if metric.lower() == 'earned' else f'{score:,}'}"
            for index, (user_id, score) in enumerate(scores, 1)
        ]
        await self._send(ctx, "Xếp hạng Farm", "\n".join(lines))

    @farm.command(name="season", brief="Xem mùa hiện tại và cây được tăng giá")
    async def season(self, ctx):
        season, remaining = season_at(day_at(time.time()))
        await self._send(
            ctx, f"{season['emoji']} {season['name']}",
            f"{season['desc']}\n{season['bonusText']}\nCòn **{remaining} ngày**.", color=season["color"],
        )

    @farm.command(name="events", aliases=["event"], brief="Xem sự kiện hôm nay")
    async def events(self, ctx):
        event = event_at(day_at(time.time()))
        await self._send(
            ctx, event["name"], f"{event['desc']}\n**{event['effect'].replace('Xu kiếm được', 'VND kiếm được')}**",
            badge="ui_quest", color=event["color"],
        )
