import asyncio
import json
import logging
import random
import time

import discord
from discord.ext import commands, tasks

from app.config import config
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed

logger = logging.getLogger(__name__)

RAKE = 0.05
TICK_SECONDS = 45          # real seconds per simulation tick
TICK_MINUTES = 15          # game minutes per tick (6 ticks = 90')
MIN_BET = 10_000
MAX_BET = 5_000_000

# Mascot teams with attack/defence ratings (1-5). Ratings drift slightly per match.
TEAMS: dict[str, dict] = {
    "PHX": {"name": "Phượng Hoàng Xa Lộ", "emoji": "🔥", "att": 4.2, "def": 2.8},
    "SHK": {"name": "Sói Hoang Karaoke", "emoji": "🐺", "att": 3.6, "def": 3.4},
    "TCT": {"name": "Tôm Càng Tiền Tệ", "emoji": "🦐", "att": 3.0, "def": 4.0},
    "DBK": {"name": "Drake Bạo Kích", "emoji": "🐉", "att": 4.6, "def": 2.2},
    "MKC": {"name": "Mèo Kêu Cá Cược", "emoji": "🐱", "att": 2.6, "def": 3.2},
    "CTB": {"name": "Cua Tô Bio", "emoji": "🦀", "att": 2.2, "def": 4.4},
    "VTC": {"name": "Voi Trắng Cờ Bạc", "emoji": "🐘", "att": 3.8, "def": 3.0},
    "GDH": {"name": "Gà Đòn Huyền Thoại", "emoji": "🐓", "att": 3.2, "def": 2.6},
}

OUTCOME_LABELS = {"1": "Thắng đội nhà", "X": "Hòa", "2": "Thắng đội khách"}

FLAVOR_EVENTS = [
    "⚡ {team} phản công sắc lẹm, thủ môn đội bạn bay người cứu thua thần kỳ!",
    "🟨 Thẻ vàng cho cầu thủ {team} vì pha truy cản nguy hiểm.",
    "🎯 {team} sút phạt trực tiếp — bóng chạm cột dọc bật ra!",
    "🔄 {team} thay người tăng cường sức tấn công.",
    "🧱 Hàng thủ {team} đứng vững trước sức ép của đối phương.",
    "😱 Cơ hội ăn bàn VOLOĐẠI cho {team} nhưng bóng đi chọc mâm ngoài!",
]


def _load_fixtures(economy: Economy) -> list[dict]:
    raw = economy.get_setting("match_fixtures", "[]")
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return []


def _save_fixtures(economy: Economy, fixtures: list[dict]) -> None:
    economy.set_setting("match_fixtures", json.dumps(fixtures[-40:], ensure_ascii=False))


def _drifted(team: dict) -> dict:
    t = dict(team)
    t["att"] = round(t["att"] * random.uniform(0.85, 1.15), 2)
    t["def"] = round(t["def"] * random.uniform(0.85, 1.15), 2)
    return t


class SportsBet(commands.Cog):
    """Cá cược bóng đá bot-vs-bot theo mô hình pool (pari-mutuel)."""

    def __init__(self, client: commands.Bot):
        self.client = client
        self.bot = client
        self.economy: Economy = getattr(client, "economy", None) or Economy()
        self.live: dict[int, dict] = {}  # match_id -> sim state
        self.match_loop.start()

    def cog_unload(self):
        self.match_loop.cancel()

    # ---------- fixtures ----------
    def _ensure_fixtures(self) -> list[dict]:
        fixtures = [m for m in _load_fixtures(self.economy) if m["status"] != "done"]
        now = time.time()
        next_id = int(self.economy.get_setting("next_match_id", "1"))
        last_kickoff = max([m["kickoff"] for m in fixtures], default=now + 600)
        while len(fixtures) < 4:
            kickoff = max(last_kickoff + 3 * 3600, now + 900)
            t1, t2 = random.sample(list(TEAMS.keys()), 2)
            fixtures.append({"id": next_id, "t1": t1, "t2": t2, "kickoff": kickoff, "status": "upcoming"})
            next_id += 1
            last_kickoff = kickoff
        self.economy.set_setting("next_match_id", str(next_id))
        _save_fixtures(self.economy, fixtures)
        return fixtures

    def _get_match(self, match_id: int) -> dict | None:
        for m in self._ensure_fixtures():
            if m["id"] == match_id:
                return m
        return None

    def _odds(self, match_id: int) -> dict[str, float]:
        pool = self.economy.get_match_pool(match_id)
        total = sum(pool.values())
        if total == 0:
            return {o: 1.0 for o in OUTCOME_LABELS}
        prize = total * (1 - RAKE)
        return {o: max(1.0, prize / pool[o]) if o in pool else max(1.0, prize) for o in OUTCOME_LABELS}

    # ---------- commands ----------
    @commands.command(name="match", brief="Xem lịch thi đấu và tỷ lệ kèo bóng đá bot.", usage="match [live]")
    async def match(self, ctx: commands.Context, action: str = None):
        fixtures = self._ensure_fixtures()
        if action and action.lower() == "live":
            live_ids = [mid for mid, s in self.live.items() if not s["done"]]
            if not live_ids:
                await ctx.send("📺 Hiện không có trận nào đang đá! Xem lịch sắp đấu bằng `i?match`.")
                return
            for mid in live_ids:
                await ctx.send(embed=self._live_embed(mid))
            return

        now = time.time()
        upcoming = [m for m in fixtures if m["status"] == "upcoming" and m["kickoff"] > now][:6]
        lines = []
        for m in upcoming:
            t1, t2 = TEAMS[m["t1"]], TEAMS[m["t2"]]
            odds = self._odds(m["id"])
            kickoff = f"<t:{int(m['kickoff'])}:R>"
            lines.append(
                f"🏟️ **#{m['id']}** {t1['emoji']} {t1['name']} (đá nhà) vs {t2['name']} {t2['emoji']}\n"
                f"└ ⏰ Bóng lăn {kickoff} | Kèo hiện tại: `1` x{odds['1']:.2f} — `X` x{odds['X']:.2f} — `2` x{odds['2']:.2f}"
            )
        if not lines:
            lines.append("Không có trận nào sắp diễn ra.")
        embed = make_embed(
            title="⚽ SÀN CÁ CƯỢC THỂ THAO",
            description="\n\n".join(lines) + "\n\n🎲 Kèo dạng **pool**: thưởng = pot x tỷ lệ tiền bạn đóng / tổng cửa trúng (trừ rake 5%).\n➡️ Đặt kèo: `i?bet <số trận> <1|X|2> <số tiền>`",
            color=discord.Color.green()
        )
        await ctx.send(embed=embed)

    @commands.command(name="bet", brief="Đặt kèo bóng đá: i?bet <số trận> <1|X|2> <số tiền>.", usage="bet <match_id> <1|X|2> <amount>")
    async def bet(self, ctx: commands.Context, match_id: int = None, outcome: str = None, amount_str: str = None):
        if match_id is None or outcome is None or amount_str is None:
            await ctx.send("❌ Dùng: `i?bet <số trận> <1|X|2> <số tiền>` — xem lịch tại `i?match`.")
            return
        outcome = outcome.upper()
        if outcome not in OUTCOME_LABELS:
            await ctx.send("❌ Cửa cược chỉ nhận `1` (nhà thắng), `X` (hòa), `2` (khách thắng).")
            return

        m = self._get_match(match_id)
        if not m or m["status"] != "upcoming" or m["kickoff"] <= time.time():
            await ctx.send("❌ Trận này đã bắt đầu hoặc không tồn tại!")
            return

        s = amount_str.lower().strip().replace(".", "").replace(",", "")
        mult = 1
        if s.endswith("k"):
            mult, s = 1_000, s[:-1]
        elif s.endswith("m") or s.endswith("tr"):
            mult, s = 1_000_000, s[:-2] if s.endswith("tr") else s[:-1]
        try:
            amount = int(float(s) * mult)
        except ValueError:
            await ctx.send("❌ Số tiền không hợp lệ!")
            return

        if not MIN_BET <= amount <= MAX_BET:
            await ctx.send(f"❌ Mỗi kèo từ `{MIN_BET:,}` đến `{MAX_BET:,} VND`.")
            return
        money = self.economy.get_entry(ctx.author.id)[1]
        if money < amount:
            await ctx.send(f"❌ Ví bạn chỉ có `{money:,} VND`!")
            return

        self.economy.add_money(ctx.author.id, -amount)
        self.economy.add_match_bet(match_id, ctx.author.id, outcome, amount)

        odds = self._odds(match_id)
        t1, t2 = TEAMS[m["t1"]], TEAMS[m["t2"]]
        embed = make_embed(
            title="🎟️ ĐẶT KÈO THÀNH CÔNG",
            description=(
                f"🏟️ **#{match_id}** {t1['emoji']} {t1['name']} vs {t2['name']} {t2['emoji']}\n"
                f"🎯 **Cửa của bạn:** `{outcome}` ({OUTCOME_LABELS[outcome]})\n"
                f"💵 **Tiền cược:** `{amount:,} VND`\n"
                f"📊 **Kèo hiện tại:** x{odds[outcome]:.2f} (kèo sẽ biến động theo tổng tiền mỗi cửa)\n\n"
                f"⏰ Bóng lăn <t:{int(m['kickoff'])}:R> — theo dõi `i?match live`!"
            ),
            color=discord.Color.gold()
        )
        await ctx.send(embed=embed)

    # ---------- live simulation ----------
    @tasks.loop(seconds=TICK_SECONDS)
    async def match_loop(self):
        fixtures = self._ensure_fixtures()
        now = time.time()

        # kick off matches whose time has come; persist so a restart or the
        # next tick doesn't re-kickoff the same match endlessly.
        dirty = False
        for m in fixtures:
            if m["status"] == "upcoming" and m["kickoff"] <= now:
                m["status"] = "live"
                dirty = True
                await self._start_live(m)
        if dirty:
            _save_fixtures(self.economy, fixtures)

        # advance live sims
        for mid in list(self.live.keys()):
            state = self.live[mid]
            if state["done"]:
                continue
            await self._tick(mid)

    @match_loop.before_loop
    async def before_match_loop(self):
        await self.bot.wait_until_ready()

    def _channel(self):
        channel_id = self.economy.get_setting("event_announce_channel", "")
        if channel_id:
            ch = self.bot.get_channel(int(channel_id))
            if isinstance(ch, discord.TextChannel):
                return ch
        return None

    async def _start_live(self, m: dict):
        mid = m["id"]
        t1, t2 = _drifted(TEAMS[m["t1"]]), _drifted(TEAMS[m["t2"]])
        self.live[mid] = {
            "m": m, "t1": t1, "t2": t2,
            "score": [0, 0], "minute": 0, "done": False,
            "timeline": [],
        }
        channel = self._channel()
        if channel:
            embed = make_embed(
                title=f"⚽ KICKOFF — {t1['emoji']} {t1['name']} vs {t2['name']} {t2['emoji']}",
                description="Cửa cược đã ĐÓNG! Trận đấu bắt đầu — theo dõi tỉ số ngay bên dưới!",
                color=discord.Color.green()
            )
            try:
                self.live[mid]["message"] = await channel.send(embed=embed)
            except Exception:
                logger.exception("Match kickoff announce failed")

    def _live_embed(self, mid: int) -> discord.Embed:
        s = self.live[mid]
        t1, t2 = s["t1"], s["t2"]
        events = "\n".join(s["timeline"][-6:]) if s["timeline"] else "— Trận đấu đang diễn ra —"
        return make_embed(
            title=f"⚽ LIVE: {t1['emoji']} {t1['name']} {s['score'][0]} - {s['score'][1]} {t2['name']} {t2['emoji']}",
            description=f"⏱️ Phút `{s['minute']}'`\n\n{events}",
            color=discord.Color.gold()
        )

    async def _tick(self, mid: int):
        s = self.live[mid]
        s["minute"] += TICK_MINUTES
        for side, team, opp in ((0, s["t1"], s["t2"]), (1, s["t2"], s["t1"])):
            goal_p = 0.30 * team["att"] / (team["att"] + opp["def"])
            if random.random() < goal_p:
                s["score"][side] += 1
                s["timeline"].append(f"⚽ **BÀN THẮNG {s['minute']}'** — {team['emoji']} {team['name']} ghi bàn!")
            elif random.random() < 0.35:
                flavor = random.choice(FLAVOR_EVENTS).format(team=team["name"])
                s["timeline"].append(f"`{s['minute']}'` {flavor}")

        if s["minute"] >= 90:
            await self._settle(mid)
        else:
            msg = s.get("message")
            if msg:
                try:
                    await msg.edit(embed=self._live_embed(mid))
                except Exception:
                    pass

    async def _settle(self, mid: int):
        s = self.live[mid]
        s["done"] = True
        m = s["m"]
        fixtures = _load_fixtures(self.economy)
        for f in fixtures:
            if f["id"] == mid:
                f["status"] = "done"
        _save_fixtures(self.economy, fixtures)

        score = s["score"]
        if score[0] > score[1]:
            result = "1"
        elif score[0] < score[1]:
            result = "2"
        else:
            result = "X"

        bets = self.economy.get_match_bets(mid)
        pool = self.economy.get_match_pool(mid)
        total = sum(pool.values())

        result_text = f"**{s['t1']['emoji']} {s['t1']['name']} {score[0]} - {score[1]} {s['t2']['name']} {s['t2']['emoji']}**"
        if not bets or total == 0:
            embed = make_embed(
                title="🏁 FULL TIME",
                description=result_text + "\n\n*(Không ai đặt kèo trận này)*",
                color=discord.Color.blurple()
            )
        elif result == "X":
            # Pari-mutuel: X is a real outcome - X bettors split the whole pot.
            winners = [(uid, amount) for _, uid, out, amount in bets if out == result]
            prize = total * (1 - RAKE)
            outcome_total = pool.get(result, 0)
            payout_lines = []
            if winners and outcome_total > 0:
                for uid, amount in sorted(winners, key=lambda w: w[1], reverse=True)[:10]:
                    share = int(prize * amount / outcome_total)
                    net = self.economy.payout_winnings(uid, share, amount)
                    payout_lines.append(f"• <@{uid}> — cược `{amount:,}` → nhận `{net:,} VND`")
            else:
                jp = int(self.economy.get_setting("jackpot_pool", "0"))
                self.economy.set_setting("jackpot_pool", str(jp + int(prize)))
                payout_lines.append(f"*(Không ai trúng cửa này — `{int(prize):,} VND` vào quỹ jackpot)*")
            embed = make_embed(
                title="🏁 FULL TIME — HÒA",
                description=result_text + "\n\n🎯 **Cửa trúng:** `X` (Hòa)\n\n" + "\n".join(payout_lines),
                color=discord.Color.blurple()
            )
        else:
            winners = [(uid, amount) for _, uid, out, amount in bets if out == result]
            prize = total * (1 - RAKE)
            outcome_total = pool.get(result, 0)
            payout_lines = []
            if winners and outcome_total > 0:
                for uid, amount in sorted(winners, key=lambda w: w[1], reverse=True)[:10]:
                    share = int(prize * amount / outcome_total)
                    net = self.economy.payout_winnings(uid, share, amount)
                    payout_lines.append(f"• <@{uid}> — cược `{amount:,}` → nhận `{net:,} VND`")
            else:
                jp = int(self.economy.get_setting("jackpot_pool", "0"))
                self.economy.set_setting("jackpot_pool", str(jp + int(prize)))
                payout_lines.append(f"*(Không ai trúng cửa này — `{int(prize):,} VND` vào quỹ jackpot)*")
            embed = make_embed(
                title=f"🏁 FULL TIME — {'NHÀ' if result == '1' else 'KHÁCH'} THẮNG!",
                description=(
                    result_text + "\n\n"
                    f"💰 **Tổng pot:** `{total:,} VND` (rake 5% vào quỹ jackpot)\n"
                    f"🏆 **Cửa trúng:** `{result}` ({OUTCOME_LABELS[result]})\n\n" + "\n".join(payout_lines)
                ),
                color=discord.Color.green()
            )
        self.economy.clear_match_bets(mid)
        logger.info("Match %s settled: %s-%s result=%s pool=%s", mid, score[0], score[1], result, total)

        del self.live[mid]
        channel = self._channel()
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Match settle announce failed")
        else:
            old_msg = s.get("message")
            if old_msg:
                try:
                    await old_msg.edit(embed=embed)
                except Exception:
                    pass


async def setup(client: commands.Bot):
    await client.add_cog(SportsBet(client))
