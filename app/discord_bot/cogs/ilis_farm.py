import time

import discord
from discord.ext import commands

from app.discord_bot.modules.farm.rules import (
    ACHIEVEMENTS, CROPS, FISH, INVENTORY_CAPACITY, JUNK, NORMAL_GACHA, PETS, QUALITY_NAMES,
    QUESTS, SHOP, SHOP_IDS, START_COINS, daily_quests, day_at, event_at, pet_bonus, season_at,
    update_pet, vnd, xp_required,
)
from app.discord_bot.modules.farm.service import FarmError, FarmSession, FarmStore, plot_limit


def inventory_name(entry: str) -> str:
    category, key = entry.split(":", 1)
    if category == "crop":
        crop, _, quality = key.rpartition("_")
        return f"{CROPS[crop]['name']} ({QUALITY_NAMES[quality]})"
    if category == "junk":
        return f"{JUNK[key]['name']} (`{key}`)"
    return SHOP[key]["name"]


def format_pet(name: str, pet: dict) -> str:
    return (
        f"**{name}** • Cấp {pet['level']} • C{pet['stars']}\n"
        f"No {pet['hunger']:.0f}% · Vui {pet['happiness']:.0f}% · HP {pet['health']:.0f}%"
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
                f"🌾 **Nông trại mới!** Gõ `{ctx.clean_prefix}farm` để chơi.",
                delete_after=5,
                allowed_mentions=discord.AllowedMentions.none(),
            )
        except (discord.Forbidden, discord.NotFound):
            return

    async def _send(self, ctx, title: str, description: str) -> None:
        if not description:
            description = "Chưa có dữ liệu."
        while description:
            split = len(description) if len(description) <= 4000 else description.rfind("\n", 0, 4000)
            if split <= 0:
                split = 4000
            await ctx.send(
                embed=discord.Embed(title=title, description=description[:split], color=0x368050),
                allowed_mentions=discord.AllowedMentions.none(),
            )
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

    async def _play(self, ctx, action, *args, render) -> None:
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
            description += f"\nThay đổi ví Casino **{session.wallet_delta:+,} VND**"
        await self._send(ctx, "🌾 Ilis Farm", description)

    async def _show_plots(self, ctx, title: str, state: dict) -> None:
        level = state["level"]
        plots = state["plots"]
        now = time.time()
        lines = [f"**Cấp {level}** · **{len(plots)}/{plot_limit(level)} ô đang dùng**"]
        for index in range(1, plot_limit(level) + 1):
            plot = plots.get(str(index))
            if plot is None:
                lines.append(f"`#{index}` Ô trống")
            else:
                crop = CROPS[plot["crop"]]
                status = f"<t:{int(plot['ready'])}:R>" if plot["ready"] > now else "Sẵn sàng thu hoạch"
                lines.append(f"`#{index}` {crop['emoji']} {crop['name']} · {status}")
        lines.append(f"\n`{ctx.clean_prefix}farm help` để xem cách chơi.")
        await self._send(ctx, title, "\n".join(lines))

    @commands.group(name="farm", invoke_without_command=True, brief="Xem nông trại Ilis Farm")
    async def farm(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            await self._show_plots(ctx, "🌾 Nông trại", state)

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
        await self._send(ctx, "🌾 Lệnh Ilis Farm", "\n".join(lines))

    @farm.command(name="start", brief="Tạo nông trại và nhận vốn một lần")
    async def start(self, ctx):
        try:
            balance = self.store.start(ctx.author.id)
        except FarmError as error:
            await self._error(ctx, error)
            return
        await self._send(
            ctx, "🌱 Nông trại mới",
            f"Đã tạo nông trại và cộng **{vnd(START_COINS):,} VND** vào ví Casino.\n"
            f"Số dư **{balance:,} VND**\n"
            f"Dùng `{ctx.clean_prefix}farm plant 1` để trồng rau muống.",
        )

    @farm.command(name="balance", aliases=["bal"], brief="Xem ví Casino, đá quý và vé Farm")
    async def balance(self, ctx):
        state = await self._player(ctx)
        if state is not None:
            balance = self.store.economy.get_entry(ctx.author.id)[1]
            await self._send(ctx, "Ví và tài sản Farm", f"**{balance:,} VND** · {state['gems']} đá quý · {state['tickets']} vé gacha")

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
            )

    @farm.command(name="daily", brief="Điểm danh nhận VND và vé gacha")
    async def daily(self, ctx):
        await self._play(ctx, FarmSession.daily, render=lambda r: f"Đã điểm danh ngày **{r[1]}** · Thưởng **{vnd(r[0]):,} VND** và **1 vé gacha**.")

    @farm.command(name="shop", brief="Xem giá hạt giống, pet, thức ăn, phân bón và cần câu")
    async def shop(self, ctx):
        lines = [
            f"`#{number}` {SHOP[key]['name']} · **{vnd(SHOP[key]['coin']):,} VND**"
            for number, key in SHOP_IDS.items()
        ]
        await self._send(ctx, "Cửa hàng Farm", "\n".join(lines))

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
        await self._show_plots(ctx, f"🌾 Nông trại của {member.display_name}", target)

    @farm.command(name="fertilize", brief="Bón phân thường, cao cấp hoặc đặc biệt")
    async def fertilize(self, ctx, fertilizer: str):
        await self._play(ctx, FarmSession.tend, fertilizer, render=lambda r: f"Đã bón phân cho **{r[0]} ô** · Giảm {r[1]}% thời gian còn lại.")

    @farm.command(name="harvest", brief="Thu hoạch theo số ô hoặc all")
    async def harvest(self, ctx, plot: str = "all"):
        await self._play(
            ctx, FarmSession.harvest, plot.lower().lstrip("#"),
            render=lambda r: "\n".join(f"**{inventory_name(f'crop:{key}')} ×{qty}**" for key, qty in r[0].items()) + f"\n+{r[1]} XP",
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
                f"`#{key}` {FISH[fish['type']]['name']} · {fish['weight']} kg · {vnd(fish['price']):,} VND giá gốc"
                for key, fish in state["fish"].items()
            ]
            await self._send(ctx, "Kho cá", "\n".join(lines))
            return
        inventory = state["inventory"]
        lines = [f"**{sum(inventory.values())}/{INVENTORY_CAPACITY}** vật phẩm"]
        lines.extend(f"{inventory_name(entry)} ×{quantity}" for entry, quantity in sorted(inventory.items()))
        await self._send(ctx, "Kho đồ Farm", "\n".join(lines))

    @farm.command(name="discard", brief="Bỏ rác câu cá khỏi kho")
    async def discard(self, ctx, item: str, quantity: int = 1):
        await self._play(ctx, FarmSession.discard_junk, item.lower(), quantity, render=lambda _: f"Đã bỏ **{quantity} vật phẩm**.")

    @farm.command(name="equip", brief="Trang bị cần câu đã mua")
    async def equip(self, ctx, rod: str):
        await self._play(ctx, FarmSession.equip, rod, render=lambda name: f"Đã trang bị **{name}**.")

    @farm.command(name="fish", aliases=["fishing"], brief="Câu cá với cần đang trang bị hoặc mã cần chỉ định")
    async def fish(self, ctx, rod: str | None = None):
        await self._play(ctx, FarmSession.fishing, rod, render=lambda r: f"🎣 **{r[0]}** · +{r[1]} XP")

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
            await self._send(ctx, "Pet Farm", format_pet(PETS[key]["name"], pet))
            return
        lines = [
            f"`{key}` **{PETS[key]['name']}** · Cấp {pet['level']} · C{pet['stars']}"
            + (" · Đang hoạt động" if key == state["active_pet"] else "")
            for key, pet in pets.items()
        ]
        await self._send(ctx, "Pet Farm", "\n".join(lines))

    @farm.command(name="selectpet", brief="Chọn pet đang hoạt động")
    async def selectpet(self, ctx, pet: str):
        await self._play(ctx, FarmSession.select_pet, pet, render=lambda name: f"Đã chọn **{name}**.")

    @farm.command(name="feed", brief="Cho pet ăn bằng thức ăn từ kho")
    async def feed(self, ctx, food: str):
        await self._play(ctx, FarmSession.care, "feed", food, render=lambda r: format_pet(*r))

    @farm.command(name="play", brief="Chơi với pet")
    async def play(self, ctx):
        await self._play(ctx, FarmSession.care, "play", render=lambda r: format_pet(*r))

    @farm.command(name="cuddle", aliases=["nung"], brief="Nựng pet")
    async def cuddle(self, ctx):
        await self._play(ctx, FarmSession.care, "cuddle", render=lambda r: format_pet(*r))

    @farm.command(name="exercise", brief="Cho pet tập luyện")
    async def exercise(self, ctx):
        await self._play(ctx, FarmSession.care, "exercise", render=lambda r: format_pet(*r))

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
                )
            return

        await self._play(
            ctx, FarmSession.gacha, count,
            render=lambda r: ("Đã dùng vé gacha.\n" if r[1] else f"Chi phí **{vnd(10_000 * count):,} VND**.\n") + "\n".join(r[0]),
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
        await self._send(ctx, "Nhiệm vụ Farm · Đổi lúc 07:00 giờ Việt Nam", "\n".join(lines))

    @farm.command(name="gacharates", brief="Xem tỷ lệ gacha và mốc bảo hiểm")
    async def gacharates(self, ctx):
        total = sum(entry["rate"] for entry in NORMAL_GACHA)
        lines = [
            "Pet thần thoại có tỷ lệ cơ bản **0,3%**, tăng từ lượt 80 và chắc chắn ở lượt 100.",
            "Sau một pet thần thoại thường, pet thần thoại tiếp theo sẽ là loại giới hạn.",
            "",
            "**Tỷ lệ phần thưởng nếu lượt quay thuộc nhóm thường**",
        ]
        lines.extend(f"{entry['name']} · {entry['rate'] / total:.2%}" for entry in NORMAL_GACHA)
        await self._send(ctx, "Tỷ lệ gacha Farm", "\n".join(lines))

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
        await self._send(ctx, f"{season['emoji']} {season['name']}", f"{season['desc']}\n{season['bonusText']}\nCòn **{remaining} ngày**.")

    @farm.command(name="events", aliases=["event"], brief="Xem sự kiện hôm nay")
    async def events(self, ctx):
        event = event_at(day_at(time.time()))
        await self._send(ctx, event["name"], f"{event['desc']}\n**{event['effect'].replace('Xu kiếm được', 'VND kiếm được')}**")
