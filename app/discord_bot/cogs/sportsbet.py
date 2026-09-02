import asyncio
import logging
import random
import time
from typing import Any

import discord
from discord.ext import commands, tasks

from app.config import config
from app.discord_bot.modules import betting
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.sports_ai import (
    AI_BETTOR_PERSONAS,
    COMMENTATOR_PERSONAS,
    decide_ai_bet,
    generate_ai_post_match_reaction,
    generate_fulltime_commentary,
    generate_goal_commentary,
    generate_halftime_commentary,
    generate_var_commentary,
    get_random_commentator,
)
from app.discord_bot.modules.sports_engine import (
    OUTCOME_LABELS,
    TEAMS,
    calculate_base_odds,
    calculate_cashout_value,
    calculate_match_probabilities,
    evaluate_market_results,
    generate_momentum_bar,
    get_drifted_team,
    simulate_tick,
)

logger = logging.getLogger(__name__)

TICK_SECONDS = 30  # Real seconds per 15-minute game tick
TICK_MINUTES = 15  # 6 ticks = 90 minutes
DEFAULT_MIN_BET = 10_000
DEFAULT_MAX_BET = 50_000_000


# --- DISCORD UI COMPONENTS ---

class SportsBetModal(discord.ui.Modal):
    def __init__(self, cog: "SportsBet", match_id: int, outcome: str, base_odds: float, market: str = "1X2"):
        self.cog = cog
        self.match_id = match_id
        self.outcome = outcome
        self.base_odds = base_odds
        self.market = market
        outcome_name = OUTCOME_LABELS.get(outcome, outcome)
        super().__init__(title=f"Đặt cược trận #{match_id} — {outcome_name[:20]}")

        self.amount_input = discord.ui.TextInput(
            label=f"Số tiền cược ({outcome_name[:25]})",
            placeholder="Vd: 500k, 1.5m, 2tr, all, tất tay...",
            min_length=1,
            max_length=25,
            required=True,
        )
        self.add_item(self.amount_input)

    async def on_submit(self, interaction: discord.Interaction):
        user_id = interaction.user.id
        raw_val = self.amount_input.value

        match = self.cog.economy.get_sports_match(self.match_id)
        if not match or match["status"] != "upcoming" or match["kickoff"] <= time.time():
            await interaction.response.send_message("❌ Trận đấu này đã bắt đầu hoặc không còn nhận cược!", ephemeral=True)
            return

        current_money = self.cog.economy.get_entry(user_id)[1]
        amount = betting.parse_bet_amount(raw_val, current_money)
        if amount <= 0:
            await interaction.response.send_message("❌ Số tiền cược không hợp lệ!", ephemeral=True)
            return

        try:
            parsed_bet, _ = betting.validate_money_bet(self.cog.economy, user_id, amount, max_bet=DEFAULT_MAX_BET)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        if parsed_bet < DEFAULT_MIN_BET:
            await interaction.response.send_message(f"❌ Tiền cược tối thiểu là `{DEFAULT_MIN_BET:,} VND`.", ephemeral=True)
            return

        try:
            ticket_id = self.cog.economy.place_sports_bet(
                match_id=self.match_id,
                user_id=user_id,
                outcome=self.outcome,
                amount=parsed_bet,
                base_odds=self.base_odds,
                market=self.market,
            )
        except Exception as e:
            await interaction.response.send_message(f"❌ Không thể đặt cược: {e}", ephemeral=True)
            return

        t1 = TEAMS.get(match["t1"], {"name": match["t1"], "emoji": "⚽"})
        t2 = TEAMS.get(match["t2"], {"name": match["t2"], "emoji": "⚽"})
        pool = self.cog.economy.get_sports_pool(self.match_id)
        total_pool = sum(pool.values())

        embed = make_embed(
            title="🎟️ VÉ CƯỢC ĐÃ ĐƯỢC GHI NHẬN",
            description=(
                f"📋 **Mã vé:** `#{ticket_id}` | **Trận:** `#{self.match_id}`\n"
                f"🏟️ **Cặp đấu:** {t1['emoji']} **{t1['name']}** vs **{t2['name']}** {t2['emoji']}\n"
                f"🎯 **Thị trường / Cửa:** `{OUTCOME_LABELS.get(self.outcome, self.outcome)}`\n"
                f"💵 **Tiền cược:** `{parsed_bet:,} VND`\n"
                f"📊 **Kèo cơ sở (Base Odds):** `x{self.base_odds:.2f}`\n"
                f"💰 **Tổng pool hiện tại:** `{total_pool:,} VND`\n\n"
                f"⏰ **Bóng lăn:** <t:{int(match['kickoff'])}:R> — Theo dõi tại `i?sports live`!"
            ),
            color=discord.Color.gold(),
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class SportsCashoutButton(discord.ui.Button):
    def __init__(self, cog: "SportsBet", ticket_id: int, user_id: int, cashout_val: int):
        super().__init__(
            label=f"Xả kèo ngay (+{cashout_val:,} VND)",
            style=discord.ButtonStyle.green,
            emoji="💸",
            custom_id=f"cashout_{ticket_id}_{user_id}",
        )
        self.cog = cog
        self.ticket_id = ticket_id
        self.user_id = user_id
        self.cashout_val = cashout_val

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.user_id:
            await interaction.response.send_message("❌ Đây không phải vé cược của bạn!", ephemeral=True)
            return

        res = self.cog.economy.cashout_sports_ticket(self.ticket_id, self.user_id, self.cashout_val)
        if not res["success"]:
            await interaction.response.send_message(f"❌ {res['error']}", ephemeral=True)
            return

        embed = make_embed(
            title="💸 XẢ KÈO THÀNH CÔNG (CASHOUT)",
            description=(
                f"📋 **Mã vé:** `#{self.ticket_id}`\n"
                f"💵 **Số tiền đã thu về:** `+{self.cashout_val:,} VND` vào ví của bạn!\n"
                f"🔒 Vé cược đã được chốt và không bị ảnh hưởng bởi kết quả chung cuộc."
            ),
            color=discord.Color.green(),
        )
        self.disabled = True
        await interaction.response.edit_message(view=self.view)
        await interaction.followup.send(embed=embed, ephemeral=True)


class SportsMatchView(discord.ui.View):
    def __init__(self, cog: "SportsBet", match_id: int):
        super().__init__(timeout=180)
        self.cog = cog
        self.match_id = match_id

        match = self.cog.economy.get_sports_match(match_id)
        if match:
            t1 = TEAMS.get(match["t1"], {"name": match["t1"], "emoji": "👑"})
            t2 = TEAMS.get(match["t2"], {"name": match["t2"], "emoji": "🦅"})
            probs = calculate_match_probabilities(t1, t2)
            odds = calculate_base_odds(probs)

            e1 = t1.get("emoji", "👑")
            if not e1 or len(e1) > 2:
                e1 = "👑"
            e2 = t2.get("emoji", "🦅")
            if not e2 or len(e2) > 2:
                e2 = "🦅"

            btn_1 = discord.ui.Button(
                label=f"1 ({t1['name'][:10]}) x{odds['1']:.2f}",
                style=discord.ButtonStyle.primary,
                emoji=e1,
                row=0,
            )
            btn_1.callback = self._make_callback("1", odds["1"], "1X2")
            self.add_item(btn_1)

            btn_x = discord.ui.Button(
                label=f"X (Hòa) x{odds['X']:.2f}",
                style=discord.ButtonStyle.secondary,
                emoji="🤝",
                row=0,
            )
            btn_x.callback = self._make_callback("X", odds["X"], "1X2")
            self.add_item(btn_x)

            btn_2 = discord.ui.Button(
                label=f"2 ({t2['name'][:10]}) x{odds['2']:.2f}",
                style=discord.ButtonStyle.primary,
                emoji=e2,
                row=0,
            )
            btn_2.callback = self._make_callback("2", odds["2"], "1X2")
            self.add_item(btn_2)

            btn_over = discord.ui.Button(
                label=f"Tài 2.5 x{odds['OU_OVER']:.2f}",
                style=discord.ButtonStyle.success,
                emoji="📈",
                row=1,
            )
            btn_over.callback = self._make_callback("OU_OVER", odds["OU_OVER"], "OU")
            self.add_item(btn_over)

            btn_under = discord.ui.Button(
                label=f"Xỉu 2.5 x{odds['OU_UNDER']:.2f}",
                style=discord.ButtonStyle.danger,
                emoji="📉",
                row=1,
            )
            btn_under.callback = self._make_callback("OU_UNDER", odds["OU_UNDER"], "OU")
            self.add_item(btn_under)

            btn_refresh = discord.ui.Button(
                label="Làm mới",
                style=discord.ButtonStyle.gray,
                emoji="🔄",
                row=1,
            )
            btn_refresh.callback = self._refresh_callback
            self.add_item(btn_refresh)

    def _make_callback(self, outcome: str, base_odds: float, market: str):
        async def callback(interaction: discord.Interaction):
            modal = SportsBetModal(self.cog, self.match_id, outcome, base_odds, market)
            await interaction.response.send_modal(modal)
        return callback

    async def _refresh_callback(self, interaction: discord.Interaction):
        match = self.cog.economy.get_sports_match(self.match_id)
        if not match:
            await interaction.response.send_message("❌ Trận đấu không tồn tại.", ephemeral=True)
            return
        embed = self.cog._build_single_match_embed(match)
        await interaction.response.edit_message(embed=embed, view=self)


# --- MAIN COG CLASS ---

class SportsBet(commands.Cog):
    """Vũ trụ Bóng đá & Cá cược Thể thao AI Universe chuyên nghiệp."""

    def __init__(self, client: commands.Bot):
        self.client = client
        self.bot = client
        self.economy: Economy = getattr(client, "economy", None) or Economy()
        self.live_cache: dict[int, dict[str, Any]] = {}
        self.match_loop.start()

    def cog_unload(self):
        self.match_loop.cancel()

    # ---------- Match Lifecycle & Helpers ----------

    def _ensure_schedule(self) -> list[dict]:
        """Ensures at least 4 upcoming matches are scheduled and populated with AI bets."""
        upcoming = self.economy.get_upcoming_sports_matches(limit=10)
        now = int(time.time())
        last_kickoff = max([m["kickoff"] for m in upcoming], default=now + 600)

        all_team_codes = list(TEAMS.keys())
        while len(upcoming) < 4:
            kickoff = max(last_kickoff + random.randint(1800, 3600), now + 600)
            t1, t2 = random.sample(all_team_codes, 2)
            t1_data, t2_data = TEAMS[t1], TEAMS[t2]
            sim_seed = f"seed_{int(time.time())}_{random.randint(1000, 9999)}"
            mid = self.economy.create_sports_match(
                t1=t1,
                t2=t2,
                kickoff=kickoff,
                t1_rating=t1_data["att"],
                t2_rating=t2_data["att"],
                sim_seed=sim_seed,
            )
            created = self.economy.get_sports_match(mid)
            if created:
                upcoming.append(created)
                # Spawn 1-2 AI Bettors to populate initial liquidity
                self._spawn_ai_bettors(created)
            last_kickoff = kickoff

        return upcoming

    def _spawn_ai_bettors(self, match: dict):
        """Spawns AI Bettors to place initial smart bets into the match pool."""
        ai_enabled = self.economy.get_setting("sports_ai_enabled", "1")
        if ai_enabled == "0":
            return

        mid = match["id"]
        t1, t2 = TEAMS[match["t1"]], TEAMS[match["t2"]]
        probs = calculate_match_probabilities(t1, t2)
        odds = calculate_base_odds(probs)
        table = self.economy.get_sports_league_table(season_id=1)

        # Pick 1-3 distinct AI personas
        chosen_ais = random.sample(list(AI_BETTOR_PERSONAS.keys()), k=random.randint(1, 3))
        for ai_id in chosen_ais:
            outcome, amount, quote = decide_ai_bet(ai_id, match, odds, table)
            self.economy.place_sports_bet(
                match_id=mid,
                user_id=ai_id,
                outcome=outcome,
                amount=amount,
                base_odds=odds.get(outcome, 1.50),
            )
            logger.info("AI Bettor %s placed bet on match #%s: %s (%s VND)", ai_id, mid, outcome, amount)

    def _get_channel(self) -> discord.TextChannel | None:
        channel_id = self.economy.get_setting("event_announce_channel", "")
        if channel_id:
            try:
                ch = self.bot.get_channel(int(channel_id))
                if isinstance(ch, discord.TextChannel):
                    return ch
            except Exception:
                pass
        return None

    def _build_single_match_embed(self, match: dict) -> discord.Embed:
        t1 = TEAMS.get(match["t1"], {"name": match["t1"], "emoji": "👑", "att": 4.0, "def": 4.0, "coach": "HLV", "tactic": "Cân bằng"})
        t2 = TEAMS.get(match["t2"], {"name": match["t2"], "emoji": "🦅", "att": 4.0, "def": 4.0, "coach": "HLV", "tactic": "Cân bằng"})
        probs = calculate_match_probabilities(t1, t2)
        odds = calculate_base_odds(probs)
        pool = self.economy.get_sports_pool(match["id"])
        total_pool = sum(pool.values())

        kickoff_str = f"<t:{int(match['kickoff'])}:R> (<t:{int(match['kickoff'])}:t>)"

        # List active AI bets
        tickets = self.economy.get_sports_tickets_for_match(match["id"])
        ai_bets = [t for t in tickets if t["user_id"] < 0]
        ai_lines = []
        for t in ai_bets:
            p = AI_BETTOR_PERSONAS.get(t["user_id"], {})
            ai_lines.append(f"• {p.get('emoji', '🤖')} **{p.get('name', 'AI')}**: Cửa `{t['outcome']}` (`{t['amount']:,} VND`)")

        ai_section = "\n".join(ai_lines) if ai_lines else "• Chưa có chuyên gia nào chốt kèo"

        desc = (
            f"🏟️ **#{match['id']}** {t1['emoji']} **{t1['name']}** vs **{t2['name']}** {t2['emoji']}\n"
            f"👔 **HLV:** `{t1.get('coach')}` ({t1.get('tactic')}) vs `{t2.get('coach')}` ({t2.get('tactic')})\n"
            f"⏰ **Bóng lăn:** {kickoff_str}\n\n"
            f"📊 **KÈO CƠ SỞ & XÁC SUẤT:**\n"
            f"• `[1]` {t1['name']}: **x{odds['1']:.2f}** ({probs['1']*100:.1f}%) | Pool: `{pool.get('1', 0):,} VND`\n"
            f"• `[X]` Hòa: **x{odds['X']:.2f}** ({probs['X']*100:.1f}%) | Pool: `{pool.get('X', 0):,} VND`\n"
            f"• `[2]` {t2['name']}: **x{odds['2']:.2f}** ({probs['2']*100:.1f}%) | Pool: `{pool.get('2', 0):,} VND`\n"
            f"• `[OU]` Tài 2.5: **x{odds['OU_OVER']:.2f}** | Xỉu 2.5: **x{odds['OU_UNDER']:.2f}**\n\n"
            f"🤖 **DÒNG TIỀN AI BETTORS:**\n{ai_section}\n\n"
            f"💰 **Tổng quỹ Pool:** `{total_pool:,} VND`"
        )

        return make_embed(
            title=f"⚽ CHI TIẾT TRẬN ĐẤU #{match['id']}",
            description=desc,
            color=discord.Color.green(),
        )

    # ---------- Background Loop & Recovery ----------

    @tasks.loop(seconds=TICK_SECONDS)
    async def match_loop(self):
        now = int(time.time())
        fixtures = self._ensure_schedule()

        # 1. Start upcoming matches
        for m in fixtures:
            if m["status"] == "upcoming" and m["kickoff"] <= now:
                await self._start_match(m)

        # 2. Advance live matches
        live_matches = self.economy.get_live_sports_matches()
        for m in live_matches:
            mid = m["id"]
            await self._advance_match(mid, m)

    @match_loop.before_loop
    async def before_match_loop(self):
        await self.bot.wait_until_ready()
        live_in_db = self.economy.get_live_sports_matches()
        for m in live_in_db:
            mid = m["id"]
            if mid not in self.live_cache:
                t1 = get_drifted_team(m["t1"])
                t2 = get_drifted_team(m["t2"])
                events = self.economy.get_sports_events(mid, limit=10)
                self.live_cache[mid] = {
                    "match": m,
                    "t1": t1,
                    "t2": t2,
                    "score": [m["score_t1"], m["score_t2"]],
                    "minute": m["minute"],
                    "xg": [0.6, 0.4],
                    "shots": [4, 3],
                    "sot": [2, 1],
                    "commentator": get_random_commentator(),
                    "timeline": [e["text"] for e in events],
                    "message": None,
                }
                logger.info("Recovered live match #%s at minute %s' (%s-%s)", mid, m["minute"], m["score_t1"], m["score_t2"])

    async def _start_match(self, m: dict):
        mid = m["id"]
        t1 = get_drifted_team(m["t1"])
        t2 = get_drifted_team(m["t2"])
        comm_key = get_random_commentator()
        comm = COMMENTATOR_PERSONAS[comm_key]

        self.live_cache[mid] = {
            "match": m,
            "t1": t1,
            "t2": t2,
            "score": [0, 0],
            "minute": 0,
            "xg": [0.0, 0.0],
            "shots": [0, 0],
            "sot": [0, 0],
            "commentator": comm_key,
            "timeline": [f"{comm['emoji']} **{comm['name']}**: Trận đấu chính thức bắt đầu! Chúc hai đội cống hiến 90 phút mãn nhãn!"],
            "message": None,
        }

        channel = self._get_channel()
        msg_id = 0
        ch_id = channel.id if channel else 0
        if channel:
            embed = make_embed(
                title=f"⚽ KICK OFF — #{mid} {t1['emoji']} {t1['name']} vs {t2['name']} {t2['emoji']}",
                description=(
                    f"{comm['emoji']} **BLV {comm['name']} ({comm['title']})** đồng hành cùng quý vị khán giả!\n"
                    f"👔 **HLV:** {t1['coach']} vs {t2['coach']}\n"
                    f"🚨 Cửa cược đã chính thức **ĐÓNG**! Theo dõi diễn biến trực tiếp bên dưới!"
                ),
                color=discord.Color.green(),
            )
            try:
                msg = await channel.send(embed=embed)
                self.live_cache[mid]["message"] = msg
                msg_id = msg.id
            except Exception:
                logger.exception("Failed to send kickoff message")

        self.economy.update_sports_match_live(
            match_id=mid,
            minute=0,
            score_t1=0,
            score_t2=0,
            message_id=msg_id,
            channel_id=ch_id,
            status="live",
        )
        self.economy.add_sports_event(mid, 0, "kickoff", "", "Trận đấu bắt đầu!")

    def _build_live_embed(self, mid: int) -> discord.Embed:
        state = self.live_cache[mid]
        t1, t2 = state["t1"], state["t2"]
        score = state["score"]
        minute = state["minute"]
        xg1, xg2 = state["xg"]
        shots1, shots2 = state["shots"]
        sot1, sot2 = state["sot"]
        comm = COMMENTATOR_PERSONAS.get(state["commentator"], COMMENTATOR_PERSONAS["tactician"])

        momentum = generate_momentum_bar(score[0], score[1], xg1, xg2)
        recent_events = "\n".join(state["timeline"][-6:]) if state["timeline"] else "— Đang thi đấu giằng co —"

        desc = (
            f"⏱️ **Thời gian:** Phút `{minute}'` / `90'` | {comm['emoji']} **BLV:** {comm['name']}\n"
            f"📊 **Thế trận (Momentum):** {t1['emoji']} {momentum} {t2['emoji']}\n"
            f"📈 **xG kỳ vọng:** `{xg1:.2f}` vs `{xg2:.2f}` | **Sút (trúng đích):** `{shots1}({sot1})` - `{shots2}({sot2})`\n\n"
            f"**Diễn biến mới nhất:**\n{recent_events}\n\n"
            f"💡 *Gợi ý: Dùng `i?sports cashout <id>` để xả kèo chốt lời trước phút 80'!*"
        )

        return make_embed(
            title=f"⚽ LIVE: {t1['emoji']} {t1['name']} {score[0]} - {score[1]} {t2['name']} {t2['emoji']}",
            description=desc,
            color=discord.Color.gold(),
        )

    async def _advance_match(self, mid: int, m: dict):
        if mid not in self.live_cache:
            t1 = get_drifted_team(m["t1"])
            t2 = get_drifted_team(m["t2"])
            self.live_cache[mid] = {
                "match": m,
                "t1": t1,
                "t2": t2,
                "score": [m["score_t1"], m["score_t2"]],
                "minute": m["minute"],
                "xg": [0.5, 0.5],
                "shots": [3, 3],
                "sot": [1, 1],
                "commentator": get_random_commentator(),
                "timeline": [],
                "message": None,
            }

        state = self.live_cache[mid]
        new_minute = state["minute"] + TICK_MINUTES
        state["minute"] = new_minute

        s1, s2, xg1, xg2, shots1, sot1, shots2, sot2, events = simulate_tick(
            minute=new_minute,
            score_t1=state["score"][0],
            score_t2=state["score"][1],
            t1=state["t1"],
            t2=state["t2"],
            xg1_prev=state["xg"][0],
            xg2_prev=state["xg"][1],
            shots1_prev=state["shots"][0],
            shots2_prev=state["shots"][1],
        )

        state["score"] = [s1, s2]
        state["xg"] = [xg1, xg2]
        state["shots"] = [shots1, shots2]
        state["sot"] = [sot1, sot2]

        comm_key = state["commentator"]

        # Check for major events & inject AI Commentator quotes
        for ev in events:
            ev_text = ev["text"]
            if ev["type"] == "goal":
                comm_quote = generate_goal_commentary(comm_key, ev["team"], ev["minute"], s1, s2, xg1)
                ev_text += f"\n└ {comm_quote}"
            elif ev["type"] == "var_overturn":
                comm_quote = generate_var_commentary(comm_key, "TỪ CHỐI BÀN THẮNG")
                ev_text += f"\n└ {comm_quote}"

            state["timeline"].append(ev_text)
            self.economy.add_sports_event(mid, ev["minute"], ev["type"], ev["team"], ev_text)

        # Halftime analysis at 45'
        if new_minute == 45:
            ht_quote = generate_halftime_commentary(comm_key, s1, s2, state["t1"]["name"], state["t2"]["name"], xg1=xg1, xg2=xg2)
            state["timeline"].append(ht_quote)
            self.economy.add_sports_event(mid, 45, "halftime", "", ht_quote)

        # Update DB
        self.economy.update_sports_match_live(
            match_id=mid,
            minute=new_minute,
            score_t1=s1,
            score_t2=s2,
            status="live",
        )

        # Update Discord Live Embed Message
        msg = state.get("message")
        if not msg and m.get("message_id") and m.get("channel_id"):
            try:
                ch = self.bot.get_channel(m["channel_id"])
                if ch:
                    msg = await ch.fetch_message(m["message_id"])
                    state["message"] = msg
            except Exception:
                pass

        if msg:
            try:
                await msg.edit(embed=self._build_live_embed(mid))
            except Exception:
                pass

        # Full time reached (>=90)
        if new_minute >= 90:
            await self._settle_match(mid)

    async def _settle_match(self, mid: int):
        state = self.live_cache[mid]
        s1, s2 = state["score"]
        t1, t2 = state["t1"], state["t2"]
        comm_key = state["commentator"]

        market_results = evaluate_market_results(s1, s2)
        result_1x2 = market_results["1X2"]

        settle_res = self.economy.settle_sports_match(mid, result_1x2, s1, s2)
        total_pool = settle_res["total_pool"]
        total_payout = settle_res["total_payout"]
        user_payouts = settle_res["payouts"]

        # Commentator Full-time recap
        ft_quote = generate_fulltime_commentary(comm_key, s1, s2, t1["name"], t2["name"], state["xg"][0], state["xg"][1])

        # AI Bettor Reactions
        ai_reactions = []
        tickets = self.economy.get_sports_tickets_for_match(mid)
        for t in tickets:
            if t["user_id"] < 0:
                won = (t["outcome"] == result_1x2)
                payout = int(user_payouts.get(t["user_id"], 0))
                react = generate_ai_post_match_reaction(t["user_id"], won, result_1x2, t["amount"], payout)
                ai_reactions.append(react)

        payout_lines = []
        for uid, amount in sorted(user_payouts.items(), key=lambda x: x[1], reverse=True)[:10]:
            if uid > 0:
                payout_lines.append(f"• <@{uid}>: nhận thưởng **`{amount:,} VND`**")
            else:
                p = AI_BETTOR_PERSONAS.get(uid, {})
                payout_lines.append(f"• {p.get('emoji', '🤖')} **{p.get('name', 'AI')}**: thắng `{amount:,} VND` *(chuyển về quỹ Jackpot)*")

        if not payout_lines:
            payout_lines.append("*(Không ai trúng thưởng — toàn bộ tiền cược nạp vào Jackpot)*")

        ai_react_section = "\n".join(ai_reactions[:3]) if ai_reactions else ""

        desc = (
            f"**{t1['emoji']} {t1['name']} {s1} - {s2} {t2['name']} {t2['emoji']}**\n\n"
            f"{ft_quote}\n\n"
            f"🏆 **Cửa thắng (1X2):** `{result_1x2}` ({OUTCOME_LABELS.get(result_1x2, '')})\n"
            f"📈 **Tài/Xỉu:** `{market_results['OU']}` | **BTTS:** `{market_results['BTTS']}`\n"
            f"💰 **Tổng Pool:** `{total_pool:,} VND` | **Tổng trả:** `{total_payout:,} VND`\n\n"
            f"**Danh sách trả thưởng:**\n" + "\n".join(payout_lines)
        )

        if ai_react_section:
            desc += f"\n\n**🗣️ PHẢN ỨNG CỦA CÁC CHUYÊN GIA AI:**\n{ai_react_section}"

        embed = make_embed(
            title=f"🏁 KẾT THÚC TRẬN ĐẤU #{mid}",
            description=desc,
            color=discord.Color.blurple(),
        )

        channel = self._get_channel()
        if channel:
            try:
                await channel.send(embed=embed)
            except Exception:
                logger.exception("Failed to send match settlement embed")

        if mid in self.live_cache:
            del self.live_cache[mid]

    # ---------- User Commands ----------

    @commands.group(name="sports", aliases=["match", "bongda", "football"], invoke_without_command=True)
    async def sports(self, ctx: commands.Context, match_id: int = None):
        """Xem lịch thi đấu thể thao, tỷ lệ kèo và sàn cá cược bóng đá."""
        fixtures = self._ensure_schedule()

        if match_id is not None:
            m = self.economy.get_sports_match(match_id)
            if not m:
                await ctx.send("❌ Không tìm thấy trận đấu này!")
                return
            embed = self._build_single_match_embed(m)
            view = SportsMatchView(self, match_id) if m["status"] == "upcoming" else None
            await ctx.send(embed=embed, view=view)
            return

        now = time.time()
        upcoming = [m for m in fixtures if m["status"] == "upcoming" and m["kickoff"] > now][:6]
        live = self.economy.get_live_sports_matches()

        sections = []

        if live:
            live_lines = []
            for m in live:
                t1 = TEAMS.get(m["t1"], {"name": m["t1"], "emoji": "⚽"})
                t2 = TEAMS.get(m["t2"], {"name": m["t2"], "emoji": "⚽"})
                live_lines.append(f"🔴 **#{m['id']}** {t1['emoji']} {t1['name']} `{m['score_t1']} - {m['score_t2']}` {t2['name']} {t2['emoji']} (Phút {m['minute']}')")
            sections.append("🔥 **ĐANG DIỄN RA (LIVE):**\n" + "\n".join(live_lines))

        upcoming_lines = []
        for m in upcoming:
            t1 = TEAMS.get(m["t1"], {"name": m["t1"], "emoji": "👑"})
            t2 = TEAMS.get(m["t2"], {"name": m["t2"], "emoji": "🦅"})
            probs = calculate_match_probabilities(t1, t2)
            odds = calculate_base_odds(probs)
            kickoff = f"<t:{int(m['kickoff'])}:R>"
            pool = self.economy.get_sports_pool(m["id"])
            total = sum(pool.values())

            upcoming_lines.append(
                f"🏟️ **#{m['id']}** {t1['emoji']} **{t1['name']}** vs **{t2['name']}** {t2['emoji']}\n"
                f"└ ⏰ {kickoff} | Kèo 1X2: `1` x{odds['1']:.2f} — `X` x{odds['X']:.2f} — `2` x{odds['2']:.2f}\n"
                f"└ Tài 2.5: x{odds['OU_OVER']:.2f} — Xỉu 2.5: x{odds['OU_UNDER']:.2f} | Pool: `{total:,} VND`"
            )

        if upcoming_lines:
            sections.append("📅 **TRẬN ĐẤU SẮP DIỄN RA:**\n" + "\n\n".join(upcoming_lines))
        else:
            sections.append("📅 Hiện tại chưa có trận đấu mới.")

        desc = (
            "\n\n".join(sections)
            + "\n\n━━━━━━━━━━━━━━━━━━━━\n"
            + "➡️ **Đặt cược:** `i?sports bet <id> <1|X|2|OU_OVER|OU_UNDER> <tiền>`\n"
            + "➡️ **Xả kèo sớm:** `i?sports cashout <mã_vé>` (trước phút 80')\n"
            + "➡️ **Xem vé của tôi:** `i?sports mybets` | **BXH Tipster:** `i?sports tipsters`"
        )

        view = None
        if upcoming:
            view = SportsMatchView(self, upcoming[0]["id"])

        embed = make_embed(
            title="⚽ SÀN CÁ CƯỢC BÓNG ĐÁ QUỐC TẾ (AI UNIVERSE)",
            description=desc,
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed, view=view)

    @sports.command(name="bet", brief="Đặt cược: i?sports bet <id> <cửa> <tiền>")
    async def sports_bet_cmd(self, ctx: commands.Context, match_id: int = None, outcome: str = None, amount_str: str = None):
        """Đặt vé cược bóng đá (Hỗ trợ 1X2, Tài Xỉu, BTTS)."""
        if match_id is None or outcome is None or amount_str is None:
            await ctx.send("❌ Cú pháp: `i?sports bet <mã_trận> <cửa> <số_tiền>`\nVí dụ: `i?sports bet 1 1 500k` hoặc `i?sports bet 1 OU_OVER 1.5m`")
            return

        outcome = outcome.upper().strip()
        # Shortcut aliases
        alias_map = {
            "OVER": "OU_OVER", "TAI": "OU_OVER", "TÀI": "OU_OVER",
            "UNDER": "OU_UNDER", "XIU": "OU_UNDER", "XỈU": "OU_UNDER",
            "BTTS": "BTTS_YES", "YES": "BTTS_YES", "NO": "BTTS_NO",
        }
        outcome = alias_map.get(outcome, outcome)

        if outcome not in OUTCOME_LABELS:
            await ctx.send(f"❌ Cửa cược không hợp lệ! Các cửa nhận: `1`, `X`, `2`, `OU_OVER` (Tài), `OU_UNDER` (Xỉu), `BTTS_YES`, `BTTS_NO`.")
            return

        match = self.economy.get_sports_match(match_id)
        if not match or match["status"] != "upcoming" or match["kickoff"] <= time.time():
            await ctx.send("❌ Trận đấu này đã bắt đầu hoặc không tồn tại!")
            return

        current_money = self.economy.get_entry(ctx.author.id)[1]
        amount = betting.parse_bet_amount(amount_str, current_money)
        if amount <= 0:
            await ctx.send("❌ Số tiền cược không hợp lệ!")
            return

        try:
            parsed_bet, _ = betting.validate_money_bet(self.economy, ctx.author.id, amount, max_bet=DEFAULT_MAX_BET)
        except Exception as e:
            await ctx.send(f"❌ {e}")
            return

        if parsed_bet < DEFAULT_MIN_BET:
            await ctx.send(f"❌ Tiền cược tối thiểu là `{DEFAULT_MIN_BET:,} VND`.")
            return

        t1 = TEAMS.get(match["t1"], {"name": match["t1"], "emoji": "👑", "att": 4.0, "def": 4.0})
        t2 = TEAMS.get(match["t2"], {"name": match["t2"], "emoji": "🦅", "att": 4.0, "def": 4.0})
        probs = calculate_match_probabilities(t1, t2)
        odds = calculate_base_odds(probs)
        base_odds = odds.get(outcome, 1.50)

        market = "OU" if "OU_" in outcome else ("BTTS" if "BTTS_" in outcome else "1X2")

        ticket_id = self.economy.place_sports_bet(
            match_id=match_id,
            user_id=ctx.author.id,
            outcome=outcome,
            amount=parsed_bet,
            base_odds=base_odds,
            market=market,
        )

        pool = self.economy.get_sports_pool(match_id)
        total_pool = sum(pool.values())

        embed = make_embed(
            title="🎟️ ĐẶT CƯỢC THÀNH CÔNG",
            description=(
                f"📋 **Mã vé:** `#{ticket_id}` | **Trận:** `#{match_id}`\n"
                f"🏟️ **Trận:** {t1['emoji']} **{t1['name']}** vs **{t2['name']}** {t2['emoji']}\n"
                f"🎯 **Cửa chọn:** `{OUTCOME_LABELS.get(outcome, outcome)}`\n"
                f"💵 **Tiền cược:** `{parsed_bet:,} VND`\n"
                f"📊 **Kèo cơ sở (Base Odds):** `x{base_odds:.2f}`\n"
                f"💰 **Tổng pool:** `{total_pool:,} VND`\n\n"
                f"⏰ **Bóng lăn:** <t:{int(match['kickoff'])}:R> — Theo dõi tại `i?sports live`!"
            ),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @sports.command(name="cashout", brief="Xả kèo sớm trước phút 80': i?sports cashout <ticket_id>")
    async def sports_cashout_cmd(self, ctx: commands.Context, ticket_id: int = None):
        """Xả kèo chốt lời / cắt lỗ sớm khi trận đang thi đấu."""
        if ticket_id is None:
            await ctx.send("❌ Cú pháp: `i?sports cashout <mã_vé>` — Xem mã vé tại `i?sports mybets`.")
            return

        tickets = self.economy.get_user_sports_tickets(ctx.author.id, limit=50)
        target = next((t for t in tickets if t["id"] == ticket_id), None)
        if not target:
            await ctx.send("❌ Không tìm thấy vé cược này trong tài khoản của bạn!")
            return

        if target["status"] != "pending":
            await ctx.send(f"❌ Vé này đã ở trạng thái `{target['status']}`, không thể xả kèo!")
            return

        if target["match_status"] != "live":
            await ctx.send("❌ Tính năng xả kèo chỉ mở khi trận đấu đang diễn ra trực tiếp (Live)!")
            return

        match = self.economy.get_sports_match(target["match_id"])
        if not match or match["minute"] >= 80:
            await ctx.send("❌ Trận đấu đã qua phút 80', thị trường xả kèo đã đóng!")
            return

        cashout_val = calculate_cashout_value(
            stake=target["amount"],
            base_odds=target["base_odds"],
            outcome=target["outcome"],
            minute=match["minute"],
            score_t1=match["score_t1"],
            score_t2=match["score_t2"],
        )

        if cashout_val <= 0:
            await ctx.send("❌ Hiện tại không có giá trị xả kèo khả dụng cho vé này.")
            return

        res = self.economy.cashout_sports_ticket(ticket_id, ctx.author.id, cashout_val)
        if not res["success"]:
            await ctx.send(f"❌ {res['error']}")
            return

        embed = make_embed(
            title="💸 XẢ KÈO THÀNH CÔNG (CASHOUT)",
            description=(
                f"📋 **Mã vé:** `#{ticket_id}` | Trận #{target['match_id']}\n"
                f"💵 **Tiền cược ban đầu:** `{target['amount']:,} VND`\n"
                f"💰 **Số tiền đã thu về ví:** `+{cashout_val:,} VND`\n"
                f"⏱️ **Thời điểm chốt:** Phút `{match['minute']}'` (Tỉ số: `{match['score_t1']}-{match['score_t2']}`)\n\n"
                f"🔒 *Vé đã được khóa an toàn, kết quả sau này không ảnh hưởng đến tiền của bạn.*"
            ),
            color=discord.Color.green(),
        )
        await ctx.send(embed=embed)

    @sports.command(name="mybets", aliases=["my", "tickets"], brief="Xem danh sách vé cược của bạn.")
    async def mybets(self, ctx: commands.Context, page: int = 1):
        """Xem lịch sử vé cược cá nhân."""
        limit = 5
        offset = max(0, (page - 1) * limit)
        tickets = self.economy.get_user_sports_tickets(ctx.author.id, limit=limit, offset=offset)

        if not tickets:
            await ctx.send("🎟️ Bạn chưa đặt vé cược thể thao nào!")
            return

        lines = []
        view = discord.ui.View(timeout=120)

        for t in tickets:
            t1_name = TEAMS.get(t["t1"], {}).get("name", t["t1"] or "Đội 1")
            t2_name = TEAMS.get(t["t2"], {}).get("name", t["t2"] or "Đội 2")

            status_icon = {
                "pending": "⏳ **Chờ đá**",
                "won": f"🏆 **Thắng** (+`{t['payout']:,} VND`)",
                "lost": "❌ **Thua**",
                "cashed_out": f"💸 **Đã xả kèo** (+`{t['payout']:,} VND`)",
                "refunded": f"🔄 **Hoàn tiền** (`{t['payout']:,} VND`)",
            }.get(t["status"], t["status"])

            cashout_btn_str = ""
            if t["status"] == "pending" and t["match_status"] == "live":
                match = self.economy.get_sports_match(t["match_id"])
                if match and match["minute"] < 80:
                    c_val = calculate_cashout_value(t["amount"], t["base_odds"], t["outcome"], match["minute"], match["score_t1"], match["score_t2"])
                    if c_val > 0:
                        cashout_btn_str = f" | 💸 Xả kèo: `i?sports cashout {t['id']}` (`{c_val:,} VND`)"
                        view.add_item(SportsCashoutButton(self, t["id"], ctx.author.id, c_val))

            lines.append(
                f"🎟️ **Vé #{t['id']}** — Trận #{t['match_id']} ({t1_name} vs {t2_name})\n"
                f"└ Cửa: `{OUTCOME_LABELS.get(t['outcome'], t['outcome'])}` | Cược: `{t['amount']:,} VND` | Kèo: `x{t['base_odds']:.2f}`\n"
                f"└ Trạng thái: {status_icon}{cashout_btn_str}"
            )

        embed = make_embed(
            title=f"📋 VÉ CƯỢC CỦA {ctx.author.display_name.upper()} (Trang {page})",
            description="\n\n".join(lines),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed, view=view if len(view.children) > 0 else None)

    @sports.command(name="history", brief="Xem lịch sử các trận đấu đã kết thúc.")
    async def sports_history(self, ctx: commands.Context, limit: int = 8):
        """Xem kết quả các trận đấu gần đây."""
        limit = min(20, max(1, limit))
        history = self.economy.get_sports_history(limit=limit)

        if not history:
            await ctx.send("📜 Chưa có trận đấu nào kết thúc trong hệ thống.")
            return

        lines = []
        for m in history:
            t1 = TEAMS.get(m["t1"], {"name": m["t1"], "emoji": "⚽"})
            t2 = TEAMS.get(m["t2"], {"name": m["t2"], "emoji": "⚽"})
            lines.append(
                f"🏁 **#{m['id']}** {t1['emoji']} **{t1['name']}** `{m['score_t1']} - {m['score_t2']}` **{t2['name']}** {t2['emoji']}\n"
                f"└ Kết quả: `{m['result']}` | Tổng Pool: `{m['total_pool']:,} VND` | Tổng trả: `{m['total_payout']:,} VND`"
            )

        embed = make_embed(
            title="📜 LỊCH SỬ KẾT QUẢ CÁC TRẬN ĐẤU GẦN ĐÂY",
            description="\n\n".join(lines),
            color=discord.Color.purple(),
        )
        await ctx.send(embed=embed)

    @sports.command(name="live", brief="Xem các trận đấu đang phát trực tiếp.")
    async def sports_live(self, ctx: commands.Context):
        """Xem các trận đấu đang live."""
        live_matches = self.economy.get_live_sports_matches()
        if not live_matches:
            await ctx.send("📺 Hiện tại không có trận đấu nào đang đá! Dùng `i?sports` để xem lịch sắp tới.")
            return

        for m in live_matches:
            mid = m["id"]
            if mid in self.live_cache:
                await ctx.send(embed=self._build_live_embed(mid))
            else:
                t1 = TEAMS.get(m["t1"], {"name": m["t1"], "emoji": "⚽"})
                t2 = TEAMS.get(m["t2"], {"name": m["t2"], "emoji": "⚽"})
                embed = make_embed(
                    title=f"⚽ LIVE: {t1['emoji']} {t1['name']} {m['score_t1']} - {m['score_t2']} {t2['name']} {t2['emoji']}",
                    description=f"⏱️ Phút: `{m['minute']}'` / `90'`",
                    color=discord.Color.gold(),
                )
                await ctx.send(embed=embed)

    @sports.command(name="standings", aliases=["bxh", "table"], brief="Bảng xếp hạng giải đấu.")
    async def sports_standings(self, ctx: commands.Context):
        """Xem Bảng xếp hạng 20 CLB hàng đầu."""
        table = self.economy.get_sports_league_table(season_id=1)
        if not table:
            for code in TEAMS.keys():
                self.economy.cur.execute(
                    "INSERT OR IGNORE INTO sports_league_table(season_id, team_code) VALUES(1, ?)",
                    (code,),
                )
            self.economy.conn.commit()
            table = self.economy.get_sports_league_table(season_id=1)

        lines = [
            "`# ` | `Đội bóng             ` | `Trận` | `T-H-B ` | `HS ` | `Điểm` | `Phong độ`",
            "─────────────────────────────────────────────────────────────",
        ]

        for i, row in enumerate(table[:15], 1):
            t_data = TEAMS.get(row["team_code"], {"name": row["team_code"], "emoji": "⚽"})
            t_name = f"{t_data['emoji']} {t_data['name']}"[:20].ljust(20)
            thb = f"{row['won']}-{row['drawn']}-{row['lost']}".center(7)
            gd_str = f"{row['gd']:+d}".rjust(4)
            form_str = row["form"] or "—"
            lines.append(f"`{i:2d}` | `{t_name}` | `{row['played']:4d}` | `{thb}` | `{gd_str}` | `{row['points']:4d}` | `{form_str}`")

        embed = make_embed(
            title="🏆 BẢNG XẾP HẠNG CHAMPIONS SUPER LEAGUE",
            description="\n".join(lines),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @sports.command(name="tipsters", aliases=["top"], brief="Xem BXH Chuyên gia dự đoán xuất sắc nhất.")
    async def sports_tipsters(self, ctx: commands.Context):
        """Xem BXH Tipsters và huy hiệu người chơi."""
        top_tipsters = self.economy.get_top_tipsters(limit=10)

        lines = []
        for i, tip in enumerate(top_tipsters, 1):
            badge = "👑" if i == 1 else ("🥈" if i == 2 else ("🥉" if i == 3 else "⭐"))
            profit_str = f"+{tip['net_profit']:,} VND" if tip["net_profit"] >= 0 else f"{tip['net_profit']:,} VND"
            lines.append(
                f"{badge} **Top {i}:** <@{tip['user_id']}>\n"
                f"└ Tỷ lệ thắng: **`{tip['win_rate']}%`** ({tip['won_bets']}/{tip['total_bets']} vé) | Lợi nhuận: `{profit_str}`"
            )

        if not lines:
            lines.append("Chưa có dữ liệu tipster nào được ghi nhận.")

        embed = make_embed(
            title="🏆 BẢNG VINH DANH CHUYÊN GIA DỰ ĐOÁN (TOP TIPSTERS)",
            description="\n\n".join(lines),
            color=discord.Color.gold(),
        )
        await ctx.send(embed=embed)

    @sports.command(name="team", brief="Xem hồ sơ CLB: i?sports team <mã_đội>")
    async def sports_team(self, ctx: commands.Context, team_code: str = None):
        """Xem thông tin chi tiết một câu lạc bộ."""
        if not team_code:
            teams_list = ", ".join([f"`{k}` ({v['name']})" for k, v in list(TEAMS.items())[:10]])
            await ctx.send(f"❌ Vui lòng nhập mã đội bóng! Ví dụ: `RMA`, `MCI`, `ARS`, `LIV`, `BAR`...\nDanh sách mẫu: {teams_list}")
            return

        team_code = team_code.upper().strip()
        if team_code not in TEAMS:
            await ctx.send(f"❌ Không tìm thấy đội `{team_code}`. Các mã hợp lệ: {', '.join(TEAMS.keys())}")
            return

        t = TEAMS[team_code]
        embed = make_embed(
            title=f"{t['emoji']} HỒ SƠ CLB: {t['name'].upper()} ({team_code})",
            description=(
                f"🏟️ **Sân vận động:** {t.get('stadium', 'Chưa cập nhật')}\n"
                f"👔 **HLV Trưởng:** **{t.get('coach', 'Chưa rõ')}**\n"
                f"🎯 **Triết lý lối chơi:** `{t.get('tactic', 'Cân bằng')}`\n\n"
                f"⚡ **CHỈ SỐ SỨC MẠNH:**\n"
                f"• ⚔️ Tấn công (Attack): `{'⭐' * int(t['att'])}` **{t['att']:.1f}/5.0**\n"
                f"• 🛡️ Phòng ngự (Defence): `{'⭐' * int(t['def'])}` **{t['def']:.1f}/5.0**\n"
                f"• 🎯 Tuyến giữa (Midfield): `{'⭐' * int(t.get('mid', 4.0))}` **{t.get('mid', 4.0):.1f}/5.0**"
            ),
            color=discord.Color.blue(),
        )
        await ctx.send(embed=embed)

    # ---------- Admin Commands ----------

    @sports.group(name="admin", invoke_without_command=True)
    @commands.has_permissions(administrator=True)
    async def sports_admin(self, ctx: commands.Context):
        """Menu quản trị hệ thống cá cược thể thao."""
        embed = make_embed(
            title="⚙️ SPORTS BETTING ADMIN CONTROL",
            description=(
                "Các lệnh quản trị viên:\n"
                "• `i?sports admin stats` — Dashboard thống kê tổng quan\n"
                "• `i?sports admin ai <on|off>` — Bật / tắt chế độ AI Bettors\n"
                "• `i?sports admin cancel <match_id> [lý do]` — Hủy trận & tự động hoàn tiền 100%\n"
                "• `i?sports admin channel <#kênh>` — Đặt kênh thông báo trận đấu\n"
                "• `i?sports admin addmatch <t1> <t2> <phút>` — Lên lịch trận đấu tùy chỉnh\n"
            ),
            color=discord.Color.dark_red(),
        )
        await ctx.send(embed=embed)

    @sports_admin.command(name="ai")
    @commands.has_permissions(administrator=True)
    async def sports_admin_ai(self, ctx: commands.Context, state: str = None):
        """Bật / Tắt chế độ AI Bettors tham gia cược."""
        if state not in ("on", "off"):
            cur = self.economy.get_setting("sports_ai_enabled", "1")
            status_text = "BẬT" if cur == "1" else "TẮT"
            await ctx.send(f"🤖 Trạng thái AI Bettor hiện tại: **{status_text}**. Dùng `i?sports admin ai on` hoặc `i?sports admin ai off` để đổi.")
            return

        val = "1" if state == "on" else "0"
        self.economy.set_setting("sports_ai_enabled", val)
        await ctx.send(f"✅ Đã {'BẬT' if val == '1' else 'TẮT'} tính năng AI Bettors!")

    @sports_admin.command(name="stats")
    @commands.has_permissions(administrator=True)
    async def sports_admin_stats(self, ctx: commands.Context):
        """Xem thống kê sàn cược."""
        stats = self.economy.get_sports_stats_dashboard()
        jackpot = int(self.economy.get_setting("jackpot_pool", "0"))

        embed = make_embed(
            title="📊 BÁO CÁO TỔNG QUAN SPORTS BETTING",
            description=(
                f"🏟️ **Trận đã kết thúc:** `{stats['settled_matches']:,}`\n"
                f"⏳ **Trận sắp đá:** `{stats['upcoming_matches']:,}` | **Đang live:** `{stats['live_matches']:,}`\n"
                f"🎟️ **Vé đang chờ kết quả:** `{stats['pending_tickets']:,}` (Tổng tiền: `{stats['pending_tickets_volume']:,} VND`)\n"
                f"💵 **Tổng Volume cược lịch sử:** `{stats['total_volume']:,} VND`\n"
                f"🏆 **Tổng tiền đã trả thưởng:** `{stats['total_payout']:,} VND`\n"
                f"🎰 **Tổng Rake đã nạp Jackpot:** `{stats['total_rake_to_jackpot']:,} VND`\n"
                f"💎 **Quỹ Jackpot hiện tại:** `{jackpot:,} VND`"
            ),
            color=discord.Color.dark_green(),
        )
        await ctx.send(embed=embed)

    @sports_admin.command(name="cancel")
    @commands.has_permissions(administrator=True)
    async def sports_admin_cancel(self, ctx: commands.Context, match_id: int, *, reason: str = "Trận đấu bị hủy bởi Quản trị viên"):
        """Hủy trận đấu và hoàn tiền 100%."""
        match = self.economy.get_sports_match(match_id)
        if not match:
            await ctx.send("❌ Không tìm thấy trận đấu!")
            return
        if match["status"] == "finished":
            await ctx.send("❌ Trận đấu này đã kết thúc và trả thưởng xong, không thể hủy!")
            return

        res = self.economy.refund_sports_match(match_id, reason=reason)
        if match_id in self.live_cache:
            del self.live_cache[match_id]

        await ctx.send(f"✅ Đã hủy trận **#{match_id}**! Hoàn lại `{res['refunded_total']:,} VND` cho `{res['refunded_count']}` vé cược.")

    @sports_admin.command(name="channel")
    @commands.has_permissions(administrator=True)
    async def sports_admin_channel(self, ctx: commands.Context, channel: discord.TextChannel):
        """Đặt kênh thông báo thể thao."""
        self.economy.set_setting("event_announce_channel", str(channel.id))
        await ctx.send(f"✅ Đã đặt kênh phát trực tiếp thể thao thành: {channel.mention}")

    @sports_admin.command(name="addmatch")
    @commands.has_permissions(administrator=True)
    async def sports_admin_addmatch(self, ctx: commands.Context, t1: str, t2: str, minutes_from_now: int = 15):
        """Tạo trận đấu tùy chỉnh."""
        t1, t2 = t1.upper().strip(), t2.upper().strip()
        if t1 not in TEAMS or t2 not in TEAMS:
            await ctx.send(f"❌ Mã đội không hợp lệ! Danh sách: {', '.join(TEAMS.keys())}")
            return
        if t1 == t2:
            await ctx.send("❌ Hai đội bóng phải khác nhau!")
            return

        kickoff = int(time.time()) + max(1, minutes_from_now) * 60
        mid = self.economy.create_sports_match(
            t1=t1,
            t2=t2,
            kickoff=kickoff,
            t1_rating=TEAMS[t1]["att"],
            t2_rating=TEAMS[t2]["att"],
        )
        created = self.economy.get_sports_match(mid)
        if created:
            self._spawn_ai_bettors(created)

        await ctx.send(f"✅ Đã tạo trận đấu **#{mid}**: {TEAMS[t1]['emoji']} **{TEAMS[t1]['name']}** vs **{TEAMS[t2]['name']}** {TEAMS[t2]['emoji']} — Bóng lăn <t:{kickoff}:R>!")

    # ---------- Legacy Bridge ----------

    @commands.command(name="bet", brief="Đặt cược thể thao: i?bet <id> <cửa> <tiền>")
    async def legacy_bet(self, ctx: commands.Context, match_id: int = None, outcome: str = None, amount_str: str = None):
        """Lệnh cược nhanh tương thích ngược."""
        await self.sports_bet_cmd(ctx, match_id, outcome, amount_str)


async def setup(client: commands.Bot):
    await client.add_cog(SportsBet(client))
