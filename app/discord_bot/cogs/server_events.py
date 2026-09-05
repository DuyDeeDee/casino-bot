import logging
import random
import time

import discord
from discord.ext import commands, tasks

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import EMOJI_VND, make_embed, ABS_PATH

logger = logging.getLogger(__name__)

RAIN_COLLECTORS = 15
RAIN_MIN, RAIN_MAX = 50_000, 500_000
BOSS_ATTACK_COST = 100_000
BOSS_DAMAGE_RANGE = (5, 15)
BOSS_TIMEOUT_SECONDS = 30 * 60

EVENT_NAMES = {
    "rain": "💰 Mưa Vàng",
    "gold": "⏰ Giờ Vàng",
    "storm": "🌨️ Bão Tuyết",
    "sale": "🎉 Flash Sale",
    "boss": "👹 Cướp Phố",
}


# --- Multiplier helpers (imported by work/mine/shop hooks) ---
def _until_active(economy: Economy, key: str) -> bool:
    try:
        until = int(economy.get_setting(key, "0"))
    except (TypeError, ValueError):
        return False
    return time.time() < until


def get_active_work_mult(economy: Economy) -> float:
    """x2 salary during Giờ Vàng."""
    return 2.0 if _until_active(economy, "event_work_mult_until") else 1.0


def get_active_mine_mult(economy: Economy) -> float:
    """x2 ore rewards during Giờ Vàng."""
    return 2.0 if _until_active(economy, "event_work_mult_until") else 1.0


def get_mine_slow_factor(economy: Economy) -> float:
    """x2 cooldown during Bão Tuyết."""
    return 2.0 if _until_active(economy, "event_mine_slow_until") else 1.0


def get_sale_factor(economy: Economy) -> float:
    """0.8 price during Flash Sale."""
    return 0.8 if _until_active(economy, "event_sale_until") else 1.0


class RainView(discord.ui.View):
    """First N clickers grab random money from a pot."""

    def __init__(self, cog: "ServerEvents", pot: int):
        super().__init__(timeout=60)
        self.cog = cog
        self.pot = pot
        self.collectors: dict[int, int] = {}

    @discord.ui.button(label="🌧️ Hứng Vàng!", style=discord.ButtonStyle.success)
    async def grab(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id in self.collectors:
            await interaction.response.send_message("🙈 Bạn đã hứng vàng rồi, nhường người khác đi!", ephemeral=True)
            return
        if len(self.collectors) >= RAIN_COLLECTORS:
            button.disabled = True
            await interaction.response.edit_message(view=self)
            await interaction.followup.send("💸 Vàng đã rơi hết mất rồi!", ephemeral=True)
            return

        share = random.randint(RAIN_MIN, RAIN_MAX)
        share = min(share, max(0, self.pot - sum(self.collectors.values())))
        self.collectors[interaction.user.id] = share
        self.cog.economy.add_money(interaction.user.id, share)
        await interaction.response.send_message(f"💸 Bạn hứng được **{share:,}** {EMOJI_VND} rơi từ trời!", ephemeral=True)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True
        try:
            if self.message:
                total = sum(self.collectors.values())
                names = " ".join(f"<@{uid}>" for uid in list(self.collectors)[:10])
                embed = make_embed(
                    title="🌧️ MƯA VÀNG KẾT THÚC",
                    description=(
                        f"💰 **Tổng số tiền đã rơi:** `{total:,}` {EMOJI_VND}\n"
                        f"🙌 **Số người hứng được:** `{len(self.collectors)}`\n\n{names}"
                    ),
                    color=discord.Color.gold()
                )
                await self.message.edit(embed=embed, view=self)
        except Exception:
            logger.exception("Rain summary failed")


class ServerEvents(commands.Cog):
    """Thời sự server: sự kiện ngẫu nhiên định kỳ cho toàn bộ thành viên."""

    def __init__(self, client: commands.Bot):
        self.client = client
        self.bot = client
        self.economy: Economy = getattr(client, "economy", None) or Economy()
        # In-memory boss state: {"hp": int, "max_hp": int, "channel_id": int, "message_id": int, "attackers": {uid: dmg}, "spawned_at": int}
        self.boss = None
        self.event_loop.start()
        self.boss_watchdog.start()

    def cog_unload(self):
        self.event_loop.cancel()
        self.boss_watchdog.cancel()

    # --- helpers ---
    def _announce_channel(self) -> discord.TextChannel | None:
        channel_id = self.economy.get_setting("event_announce_channel", "")
        if channel_id:
            channel = self.bot.get_channel(int(channel_id))
            if isinstance(channel, discord.TextChannel):
                return channel
        return None

    async def _announce(self, embed: discord.Embed, view: discord.ui.View | None = None):
        channel = self._announce_channel()
        if channel:
            msg = await channel.send(embed=embed, view=view)
            if view:
                view.message = msg
            return msg
        logger.info("Event announce skipped (event_announce_channel not set): %s", embed.title)
        return None

    def _clear_all(self):
        for key in ("event_work_mult_until", "event_mine_slow_until", "event_sale_until"):
            self.economy.set_setting(key, "0")
        self.boss = None

    # --- scheduler ---
    @tasks.loop(minutes=60)
    async def event_loop(self):
        if random.random() > 0.60:
            return
        if self.boss:
            return  # one event at a time while a boss is raging
        choice = random.choices(
            list(EVENT_NAMES.keys()),
            weights=[25, 25, 15, 20, 15],
            k=1,
        )[0]
        try:
            await self.trigger_event(choice)
        except Exception:
            logger.exception("Event %s failed", choice)

    @event_loop.before_loop
    async def before_event_loop(self):
        await self.bot.wait_until_ready()

    # --- boss expiry watch (30 min timeout) ---
    @tasks.loop(minutes=1)
    async def boss_watchdog(self):
        if self.boss and time.time() > self.boss["spawned_at"] + BOSS_TIMEOUT_SECONDS:
            await self._resolve_boss(victory=False)

    @boss_watchdog.before_loop
    async def before_boss_watchdog(self):
        await self.bot.wait_until_ready()

    # --- event implementations ---
    async def trigger_event(self, name: str):
        now = int(time.time())
        if name == "rain":
            pot = 3_000_000
            view = RainView(self, pot)
            embed = make_embed(
                title="🌧️ MƯA VÀNG 🌧️",
                description=(
                    f"Trời bất chợt đổ mưa **{pot:,}** {EMOJI_VND} tiền lẻ!\n\n"
                    f"🏆 **{RAIN_COLLECTORS} người đầu tiên** bấm nút sẽ hứng được "
                    f"`{RAIN_MIN:,}–{RAIN_MAX:,}` {EMOJI_VND} mỗi người!\n"
                    f"⏱️ Mưa kéo dài **60 giây** — nhanh tay!"
                ),
                color=discord.Color.gold()
            )
            await self._announce(embed, view)
        elif name == "gold":
            self.economy.set_setting("event_work_mult_until", str(now + 3600))
            embed = make_embed(
                title="⏰ GIỜ VÀNG ⏰",
                description=(
                    "Thị trường bùng nổ! Trong **1 giờ tới**:\n"
                    "• 💼 `$work` cho lương **x2**\n"
                    "• ⛏️ `i?mine` cho quặng **x2 giá trị**\n\n"
                    "Tận dụng ngay kẻo lỡ!"
                ),
                color=discord.Color.gold()
            )
            await self._announce(embed)
        elif name == "storm":
            self.economy.set_setting("event_mine_slow_until", str(now + 3600))
            embed = make_embed(
                title="🌨️ BÃO TUYẾT 🌨️",
                description=(
                    "Bão lớn đổ bộ, hầm mỏ bị ngập!\n"
                    "• ⛏️ Cooldown `i?mine` **gấp đôi** trong 1 giờ.\n"
                    "• 💼 `$work` vẫn bình thường — ở nhà làm việc đi!"
                ),
                color=discord.Color.light_grey()
            )
            await self._announce(embed)
        elif name == "sale":
            self.economy.set_setting("event_sale_until", str(now + 1800))
            embed = make_embed(
                title="🎉 FLASH SALE 🎉",
                description=(
                    "Cửa hàng xả kho! Mọi vật phẩm trong `i?shop` **giảm 20%** trong 30 phút.\n"
                    "🛒 Vào mua ngay kẻo hết!"
                ),
                color=discord.Color.green()
            )
            await self._announce(embed)
        elif name == "boss":
            await self.spawn_boss()

    async def spawn_boss(self):
        max_hp = random.randint(50, 150)
        self.boss = {
            "hp": max_hp,
            "max_hp": max_hp,
            "attackers": {},
            "spawned_at": time.time(),
        }
        embed = make_embed(
            title="👹 ĐỘI CƯỚP ĐÃ ĐẾN PHỐ! 👹",
            description=(
                f"Một băng cướp khét tiếng đang càn phá khu mua sắm!\n\n"
                f"❤️ **Sức khỏe băng cướp:** `{max_hp}`\n"
                f"⚔️ Gõ `i?boss attack` để tham gia chiến đấu "
                f"(tốn `{BOSS_ATTACK_COST:,}` {EMOJI_VND} phí vũ khí, gây **{BOSS_DAMAGE_RANGE[0]}–{BOSS_DAMAGE_RANGE[1]}** sát thương)\n"
                f"🎁 Hạ được: mỗi người tham gia nhận `200k` + top 1-2-3 sát thương nhận thêm `1M/500k/300k`!\n"
                f"💀 Nếu **30 phút** không hạ được: băng cướp cướp **5% ví** (tối đa 2M) của tối đa 10 người đã tham chiến!"
            ),
            color=discord.Color.red()
        )
        msg = await self._announce(embed)
        if msg:
            self.boss["channel_id"] = msg.channel.id
            self.boss["message_id"] = msg.id
            self.boss["message"] = msg

    async def _boss_progress_embed(self) -> discord.Embed:
        hp = self.boss["hp"]
        max_hp = self.boss["max_hp"]
        bar_len = 14
        filled = max(0, int(bar_len * hp / max_hp))
        bar = "█" * filled + "░" * (bar_len - filled)
        remain = max(0, int(self.boss["spawned_at"] + BOSS_TIMEOUT_SECONDS - time.time()))
        return make_embed(
            title="👹 BĂNG CƯỚP ĐANG GIAO TRANH",
            description=(
                f"❤️ HP: `{hp}/{max_hp}`\n`{bar}`\n\n"
                f"⚔️ **{len(self.boss['attackers'])} người** đã tham chiến\n"
                f"⏱️ Hết thời gian sau: `{remain // 60} phút {remain % 60} giây`\n\n"
                f"Gõ `i?boss attack` để tham gia!"
            ),
            color=discord.Color.red()
        )

    async def _update_boss_message(self):
        msg = self.boss.get("message")
        if msg:
            try:
                await msg.edit(embed=self._boss_progress_embed())
            except Exception:
                pass

    @commands.command(name="boss", brief="Tấn công băng cướp đang càn phá phố.", usage="boss attack")
    async def boss(self, ctx: commands.Context, action: str = None):
        if action and action.lower() == "attack":
            await self.boss_attack(ctx)
        else:
            if self.boss:
                await ctx.send(embed=self._boss_progress_embed())
            else:
                await ctx.send("🌇 Phố đang yên bình... Không có băng cướp nào hoạt động.")

    async def boss_attack(self, ctx: commands.Context):
        if not self.boss:
            await ctx.send("🌇 Phố đang yên bình... Không có băng cướp nào để đánh!")
            return
        user_id = ctx.author.id
        if user_id in self.boss["attackers"]:
            await ctx.send("⚔️ Bạn đã chém một lượt rồi! Nghỉ đi, đừng tham!")
            return

        money = self.economy.get_entry(user_id)[1]
        if money < BOSS_ATTACK_COST:
            await ctx.send(f"❌ Cần `{BOSS_ATTACK_COST:,}` {EMOJI_VND} phí vũ khí mà ví bạn chỉ có `{money:,}` {EMOJI_VND}!")
            return

        damage = random.randint(*BOSS_DAMAGE_RANGE)
        crit = random.random() < 0.1
        if crit:
            damage *= 2

        self.economy.add_money(user_id, -BOSS_ATTACK_COST)
        self.economy.update_world_boss_damage(user_id, damage, int(time.time()))
        self.economy.set_pve_cooldown(user_id, "cityboss", int(time.time()))
        self.boss["attackers"][user_id] = self.boss["attackers"].get(user_id, 0) + damage
        self.boss["hp"] = max(0, self.boss["hp"] - damage)

        crit_text = " 🔥**CHÍ MẠNG!**" if crit else ""
        await ctx.send(f"⚔️ {ctx.author.mention} chém trúng **{damage}** sát thương!{crit_text}")

        if self.boss["hp"] <= 0:
            await self._resolve_boss(victory=True)
        else:
            await self._update_boss_message()

    async def _resolve_boss(self, victory: bool):
        boss = self.boss
        self.boss = None
        if not boss:
            return
        attackers = boss["attackers"]
        channel = self.bot.get_channel(boss.get("channel_id", 0)) if boss.get("channel_id") else None
        if not attackers:
            return

        if victory:
            for uid in attackers:
                self.economy.add_money(uid, 200_000)
            top = sorted(attackers.items(), key=lambda kv: kv[1], reverse=True)[:3]
            bonuses = [1_000_000, 500_000, 300_000]
            for i, (uid, _) in enumerate(top):
                self.economy.add_money(uid, bonuses[i])
            podium = "\n".join(
                f"🥇🥈🥉"[i] + f" <@{uid}> — `{dmg}` sát thương (+{bonuses[i]:,} {EMOJI_VND})"
                for i, (uid, dmg) in enumerate(top)
            )
            embed = make_embed(
                title="🎉 BĂNG CƯỚP ĐÃ BỊ QUẪN SẠCH!",
                description=(
                    f"Cả phố cùng nhau đánh đuổi băng cướp!\n\n"
                    f"💰 **{len(attackers)} người** tham chiến mỗi người nhận `200,000` {EMOJI_VND}.\n\n"
                    f"**Bảng vàng sát thương:**\n{podium}"
                ),
                color=discord.Color.green()
            )
        else:
            victims = random.sample(list(attackers), min(10, len(attackers)))
            stolen_total = 0
            lines = []
            for uid in victims:
                wallet = self.economy.get_entry(uid)[1]
                stolen = min(int(wallet * 0.05), 2_000_000)
                if stolen > 0:
                    self.economy.add_money(uid, -stolen)
                    stolen_total += stolen
                    lines.append(f"• <@{uid}> mất `{stolen:,}` {EMOJI_VND}")
            embed = make_embed(
                title="💀 BĂNG CƯỚP THOÁT THÀNH CÔNG!",
                description=(
                    f"Không ai hạ được băng cướp kịp giờ...\n\n"
                    f"💸 Chúng đã cướp tổng `{stolen_total:,}` {EMOJI_VND}:\n" + "\n".join(lines) +
                    f"\n\n*Lần sau hãy đừng để chúng thoát!*"
                ),
                color=discord.Color.dark_red()
            )

        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Boss result announce failed")

    # --- admin ---
    @commands.group(name="event", brief="Quản lý sự kiện server (Admin).", invoke_without_command=True, hidden=True)
    async def event(self, ctx: commands.Context):
        await self._event_status(ctx)

    async def _event_status(self, ctx: commands.Context):
        now = time.time()
        lines = []
        for key, label in (("event_work_mult_until", "⏰ Giờ Vàng"), ("event_mine_slow_until", "🌨️ Bão Tuyết"), ("event_sale_until", "🎉 Flash Sale")):
            until = int(self.economy.get_setting(key, "0"))
            if until > now:
                lines.append(f"{label}: còn `{int(until - now) // 60}` phút")
        if self.boss:
            lines.append(f"👹 Cướp Phố: HP `{self.boss['hp']}/{self.boss['max_hp']}`")
        if not lines:
            lines.append("Không có sự kiện nào đang chạy.")
        channel_id = self.economy.get_setting("event_announce_channel", "")
        embed = make_embed(
            title="📡 TRẠNG THÁI THỜI SỰ SERVER",
            description="\n".join(lines) + f"\n\n📢 Kênh thông báo: <#{channel_id}>" if channel_id else "\n".join(lines) + "\n\n📢 Chưa đặt kênh thông báo (`i?event channel #kênh`)",
            color=discord.Color.blurple()
        )
        await ctx.send(embed=embed)

    @event.command(name="channel")
    async def event_channel(self, ctx: commands.Context, channel: discord.TextChannel = None):
        if ctx.author.id not in config.bot.owner_ids and not await ctx.bot.is_owner(ctx.author):
            await ctx.send("❌ Chỉ Admin/Owner mới dùng được lệnh này!")
            return
        if not channel:
            await ctx.send("❌ Dùng: `i?event channel #kênh`")
            return
        self.economy.set_setting("event_announce_channel", str(channel.id))
        await ctx.send(f"✅ Đã đặt kênh thông báo sự kiện: {channel.mention}")

    @event.command(name="trigger")
    async def event_trigger(self, ctx: commands.Context, name: str = None):
        if ctx.author.id not in config.bot.owner_ids and not await ctx.bot.is_owner(ctx.author):
            await ctx.send("❌ Chỉ Admin/Owner mới dùng được lệnh này!")
            return
        if name not in EVENT_NAMES:
            await ctx.send(f"❌ Sự kiện hợp lệ: {', '.join(f'`{k}`' for k in EVENT_NAMES)}")
            return
        if self.boss:
            await ctx.send("❌ Đang có băng cướp hoạt động, hãy xử lý xong đã!")
            return
        await self.trigger_event(name)
        await ctx.send(f"✅ Đã kích sự kiện **{EVENT_NAMES[name]}**!")

    @event.command(name="off")
    async def event_off(self, ctx: commands.Context):
        if ctx.author.id not in config.bot.owner_ids and not await ctx.bot.is_owner(ctx.author):
            await ctx.send("❌ Chỉ Admin/Owner mới dùng được lệnh này!")
            return
        self._clear_all()
        await ctx.send("✅ Đã tắt toàn bộ sự kiện đang chạy.")


async def setup(client: commands.Bot):
    await client.add_cog(ServerEvents(client))
