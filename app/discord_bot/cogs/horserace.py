import io
import asyncio
import logging
import random
from typing import Any

import discord
from discord.ext import commands
from PIL import Image, ImageDraw, ImageFont

from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.profile_renderer import load_font

logger = logging.getLogger(__name__)

# Roster of 8 horses with distinct power levels (60 - 95)
HORSE_ROSTER = [
    {"id": "1", "name": "Xích Thố", "emoji": "🐎", "power": 95},
    {"id": "2", "name": "Bạch Long", "emoji": "🦄", "power": 90},
    {"id": "3", "name": "Ô Truy", "emoji": "🐴", "power": 85},
    {"id": "4", "name": "Hãn Huyết", "emoji": "🏇", "power": 80},
    {"id": "5", "name": "Thiên Lý Mã", "emoji": "🦓", "power": 75},
    {"id": "6", "name": "Phi Bão", "emoji": "🐆", "power": 70},
    {"id": "7", "name": "Tia Chớp", "emoji": "⚡", "power": 65},
    {"id": "8", "name": "Rùa Đua", "emoji": "🐢", "power": 60},
]


def generate_horserace_image(
    selected_horses: list,
    positions: dict,
    TRACK_LENGTH: int = 20,
    bets: dict = None,
    user_names: dict = None
) -> io.BytesIO:
    num_horses = len(selected_horses)
    img_w = 750
    img_h = 20 + num_horses * 70 + 10

    # Discord dark theme background: (43, 43, 48, 255)
    bg_color = (43, 43, 48, 255)
    img = Image.new("RGBA", (img_w, img_h), bg_color)
    draw = ImageDraw.Draw(img)

    # Load fonts
    font_name = load_font("bold", 18)
    font_odds = load_font("bold", 18)

    # Emoji font fallback list
    font_emoji = None
    emoji_font_paths = [
        "C:/Windows/Fonts/seguiemj.ttf",
        "/usr/share/fonts/truetype/noto/NotoColorEmoji.ttf",
        "seguiemj.ttf",
        "NotoColorEmoji.ttf"
    ]
    for path in emoji_font_paths:
        try:
            font_emoji = ImageFont.truetype(path, 24)
            break
        except Exception:
            continue

    if font_emoji is None:
        font_emoji = load_font("regular", 24)

    for i, horse in enumerate(selected_horses):
        y_start = 20 + i * 70
        y_end = y_start + 30
        y_mid = y_start + 15

        # 1. Left text: "#i Name"
        label_text = f"#{i+1} {horse['name']}"
        try:
            draw.text((25, y_mid), label_text, font=font_name, fill=(220, 220, 225, 255), anchor="lm")
        except AttributeError:
            draw.text((25, y_mid - 10), label_text, font=font_name, fill=(220, 220, 225, 255))

        # 2. Track bar (rounded rectangle)
        draw.rounded_rectangle([210, y_start, 650, y_end], radius=6, fill=(32, 34, 37, 255))

        # 3. Dashed finish line in the track bar
        for y in range(y_start + 3, y_end - 3, 5):
            draw.line([(635, y), (635, y + 2)], fill=(255, 255, 255, 80), width=2)

        # 4. Position of horse emoji
        pos = positions.get(horse["id"], 0)
        # Scale pos from 0..20 to 0..380px of movement
        x_offset = int((pos / TRACK_LENGTH) * 380)
        x_horse = 215 + x_offset

        # Draw emoji
        emoji = horse["emoji"]
        try:
            draw.text((x_horse, y_mid), emoji, font=font_emoji, embedded_color=True, anchor="lm")
        except Exception:
            try:
                draw.text((x_horse, y_mid - 12), emoji, font=font_emoji, embedded_color=True)
            except Exception:
                # Fallback to drawing a colored shape if emoji fails completely
                draw.ellipse([(x_horse, y_mid - 12), (x_horse + 24, y_mid + 12)], fill=(255, 204, 0, 255))
                draw.text((x_horse + 6, y_mid - 10), str(i+1), font=font_name, fill=(0, 0, 0, 255))

        # 5. Odds text: "2.1x"
        odds_text = f"{horse['odds']}x"
        odds_color = (255, 204, 0, 255)  # Gold
        try:
            draw.text((670, y_mid), odds_text, font=font_odds, fill=odds_color, anchor="lm")
        except AttributeError:
            draw.text((670, y_mid - 10), odds_text, font=font_odds, fill=odds_color)

        # 6. Draw subtitle stats & bets
        total_bet = 0
        betters = []
        if bets and user_names:
            for uid, horse_bets in bets.items():
                if horse["id"] in horse_bets:
                    amt = horse_bets[horse["id"]]
                    total_bet += amt
                    name = user_names.get(uid, f"User {uid}")
                    betters.append(f"{name} ({amt:,})")

        sub_text = f"Sức mạnh: {horse['power']}"
        if total_bet > 0:
            betters_str = ", ".join(betters)
            if len(betters_str) > 45:
                betters_str = betters_str[:42] + "..."
            sub_text += f"  |  Cược: {total_bet:,} VND ({betters_str})"
        else:
            sub_text += "  |  Cược: 0 VND"

        font_sub = load_font("regular", 11)
        try:
            draw.text((210, y_start + 38), sub_text, font=font_sub, fill=(170, 172, 180, 255), anchor="lm")
        except AttributeError:
            draw.text((210, y_start + 38 - 6), sub_text, font=font_sub, fill=(170, 172, 180, 255))

    # Output bytes
    out = io.BytesIO()
    img.save(out, format="PNG")
    out.seek(0)
    return out


def parse_bet_amount(val_str: str, current_money: int) -> int:
    val_str = val_str.strip().lower()
    if val_str in ["all", "allin", "all-in", "tất tay"]:
        from app.discord_bot.modules.betting import get_capped_all_in_amount
        return get_capped_all_in_amount(current_money)

    has_suffix = val_str.endswith("k") or val_str.endswith("m")

    if has_suffix:
        val_str = val_str.replace(",", "")
        multiplier = 1000 if val_str.endswith("k") else 1000000
        val_str = val_str[:-1].strip()
    else:
        val_str = val_str.replace(",", "")
        if "." in val_str:
            parts = val_str.split(".")
            if len(parts[-1]) == 3:
                val_str = val_str.replace(".", "")
            else:
                val_str = "".join(parts[:-1]) + "." + parts[-1]
        multiplier = 1

    try:
        return max(0, int(float(val_str) * multiplier))
    except (ValueError, TypeError):
        return 0


class HorseRaceBetModal(discord.ui.Modal):
    def __init__(self, horse: dict, lobby_view: "HorseRaceLobbyView"):
        super().__init__(title=f"Cược cho {horse['name']}")
        self.horse = horse
        self.lobby_view = lobby_view

        self.bet_input = discord.ui.TextInput(
            label="Số tiền cược (Tối thiểu 1,000 VND)",
            placeholder="Ví dụ: 1000, 50k, 2.5m, all",
            required=True,
            max_length=20,
        )
        self.add_item(self.bet_input)

    async def on_submit(self, interaction: discord.Interaction):
        if self.lobby_view.is_closed:
            await interaction.response.send_message(
                "❌ Phiên cược đã kết thúc! Bạn không thể đặt cược nữa.",
                ephemeral=True,
            )
            return

        user = interaction.user
        val_str = self.bet_input.value

        # Fetch current wallet balance
        current_money = self.lobby_view.cog.economy.get_entry(user.id)[1]

        amount = parse_bet_amount(val_str, current_money)
        if amount <= 0:
            await interaction.response.send_message(
                "❌ Số tiền cược không hợp lệ! Vui lòng nhập số dương (ví dụ: 50k, 10000).",
                ephemeral=True,
            )
            return

        if amount < 1000:
            await interaction.response.send_message(
                "❌ Số tiền cược tối thiểu là **1,000 VND**.", ephemeral=True
            )
            return

        if amount > current_money:
            await interaction.response.send_message(
                f"❌ Bạn không đủ tiền! Số dư hiện tại của bạn là **{current_money:,} VND**.",
                ephemeral=True,
            )
            return

        # Deduct balance immediately
        self.lobby_view.cog.economy.add_money(user.id, -amount)

        # Record bet
        self.lobby_view.place_bet(user.id, user.display_name, self.horse["id"], amount)

        # Log wallet change
        log_wallet_change(
            logger,
            event="horserace_place_bet",
            user_id=user.id,
            money_delta=-amount,
            horse_id=self.horse["id"],
            bet_amount=amount,
        )

        await interaction.response.send_message(
            f"✅ Đã đặt cược **{amount:,} VND** cho ngựa **{self.horse['name']}** thành công!",
            ephemeral=True,
        )
        await self.lobby_view.update_message()


class HorseRaceLobbyView(discord.ui.View):
    def __init__(self, cog, guild_id: int, horses: list, timeout: float = 35.0):
        super().__init__(timeout=timeout)
        self.cog = cog
        self.guild_id = guild_id
        self.horses = horses  # list of dicts
        self.bets = {}        # user_id -> {horse_id: amount}
        self.user_names = {}  # user_id -> username
        self.is_closed = False
        self.message = None
        self.seconds_remaining = 30

        # Add buttons dynamically
        for horse in self.horses:
            btn = discord.ui.Button(
                label=horse["name"],
                style=discord.ButtonStyle.primary,
                emoji=horse["emoji"],
                custom_id=f"hr_bet_{horse['id']}",
            )
            btn.callback = self.make_callback(horse)
            self.add_item(btn)

    def make_callback(self, horse: dict):
        async def callback(interaction: discord.Interaction):
            if self.is_closed:
                await interaction.response.send_message(
                    "❌ Phiên cược đã kết thúc!", ephemeral=True
                )
                return
            await interaction.response.send_modal(
                HorseRaceBetModal(horse, self)
            )
        return callback

    def place_bet(self, user_id: int, username: str, horse_id: str, amount: int):
        if user_id not in self.bets:
            self.bets[user_id] = {}
        self.bets[user_id][horse_id] = self.bets[user_id].get(horse_id, 0) + amount
        self.user_names[user_id] = username

    def has_bets(self) -> bool:
        return len(self.bets) > 0

    def create_embed(self) -> discord.Embed:
        embed = make_embed(
            title="🏇 TRƯỜNG ĐUA NGỰA CASINO 🏇",
            description=(
                f"⏳ **Thời gian đặt cược còn lại:** `{self.seconds_remaining} giây`\n\n"
                "👉 Nhấn vào nút bên dưới để chọn ngựa chiến và đặt cược số tiền tương ứng."
            ),
            color=discord.Color.gold(),
        )
        embed.set_image(url="attachment://race.png")
        return embed

    async def update_message(self):
        if self.message:
            embed = self.create_embed()
            positions = {horse["id"]: 0 for horse in self.horses}
            img_bytes = generate_horserace_image(self.horses, positions, 20, self.bets, self.user_names)
            file = discord.File(img_bytes, filename="race.png")
            try:
                await self.message.edit(embed=embed, attachments=[file], view=self)
            except discord.HTTPException:
                pass


class HorseRaceResultView(discord.ui.View):
    def __init__(self, cog, ctx: commands.Context):
        super().__init__(timeout=60.0)
        self.cog = cog
        self.ctx = ctx

    @discord.ui.button(label="Đặt Cược Vòng Mới", style=discord.ButtonStyle.primary, emoji="🎲")
    async def new_round(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.guild_id in self.cog.active_races:
            await interaction.response.send_message("❌ Hiện đang có một cuộc đua ngựa đang diễn ra tại server này!", ephemeral=True)
            return

        for child in self.children:
            if isinstance(child, discord.ui.Button):
                child.disabled = True
        try:
            await interaction.message.edit(view=self)
        except Exception:
            pass

        await interaction.response.send_message("🎲 Đang khởi tạo vòng đua mới...", ephemeral=True)
        await self.cog.horserace_command(self.ctx)

    @discord.ui.button(label="Lịch Sử", style=discord.ButtonStyle.secondary, emoji="📜")
    async def show_history(self, interaction: discord.Interaction, button: discord.ui.Button):
        hist = self.cog.history.get(interaction.guild_id, [])
        if not hist:
            await interaction.response.send_message("📜 Chưa có lịch sử cuộc đua nào trong phiên làm việc này!", ephemeral=True)
            return

        lines = []
        for i, entry in enumerate(reversed(hist)):
            status = "🎉 Có người thắng" if entry["payouts"] else "💸 Nhà cái ăn"
            lines.append(f"Trận {i+1}: {entry['emoji']} **{entry['winner']}** ({entry['odds']}x) — {status}")

        embed = make_embed(
            title="📜 LỊCH SỬ ĐUA NGỰA (10 trận gần nhất)",
            description="\n".join(lines),
            color=discord.Color.blue()
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


class HorseRace(commands.Cog, name="HorseRace"):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", None)
        self.active_races = {}  # guild_id -> view/running state
        self.history = {}       # guild_id -> list of results

    @commands.command(
        name="horserace",
        aliases=["duangua", "race"],
        brief="Tham gia trò chơi đua ngựa cá cược.",
        usage="horserace",
    )
    async def horserace_command(self, ctx: commands.Context):
        if ctx.guild is None:
            await ctx.send("❌ Lệnh này chỉ có thể sử dụng trong Server!")
            return

        guild_id = ctx.guild.id
        if guild_id in self.active_races:
            await ctx.send("❌ Hiện đang có một cuộc đua ngựa đang diễn ra tại server này!")
            return

        # Select 4-5 horses randomly from roster
        num_horses = random.randint(4, 5)
        selected_raw = random.sample(HORSE_ROSTER, num_horses)

        # Calculate odds and clone dicts to avoid mutating global array
        selected_horses = []
        for h in selected_raw:
            odds = max(1.2, round(100 / h["power"], 1))
            selected_horses.append({
                "id": h["id"],
                "name": h["name"],
                "emoji": h["emoji"],
                "power": h["power"],
                "odds": odds,
            })

        # Set active race
        lobby = HorseRaceLobbyView(self, guild_id, selected_horses)
        self.active_races[guild_id] = lobby

        try:
            # Generate starting image for the lobby phase
            positions = {horse["id"]: 0 for horse in selected_horses}
            lobby_img = generate_horserace_image(selected_horses, positions, 20, lobby.bets, lobby.user_names)
            lobby_file = discord.File(lobby_img, filename="race.png")

            lobby_message = await ctx.send(file=lobby_file, embed=lobby.create_embed(), view=lobby)
            lobby.message = lobby_message

            # Lobby betting phase countdown
            for remaining in range(30, -1, -5):
                lobby.seconds_remaining = remaining
                await lobby.update_message()
                if remaining == 0:
                    break
                await asyncio.sleep(5)

            # Close lobby & disable buttons
            lobby.is_closed = True
            for item in lobby.children:
                if isinstance(item, discord.ui.Button):
                    item.disabled = True
            await lobby.update_message()

            # Check if there are any bets
            if not lobby.has_bets():
                await ctx.send("❌ Không có ai đặt cược, cuộc đua đã bị hủy!")
                return

            # Start the race simulation
            await ctx.send("🏁 **Thời gian đặt cược đã hết! Cuộc đua bắt đầu!** 🏁")
            
            # Race state variables
            TRACK_LENGTH = 20
            raw_positions = {horse["id"]: 0 for horse in selected_horses}
            positions = {horse["id"]: 0 for horse in selected_horses}

            # Generate initial race track image
            initial_img = generate_horserace_image(selected_horses, positions, TRACK_LENGTH, lobby.bets, lobby.user_names)
            initial_file = discord.File(initial_img, filename="race.png")

            race_embed = make_embed(
                title="🏇 CUỘC ĐUA ĐANG DIỄN RA 🏇",
                description="Đường đua kịch tính bắt đầu! Ai sẽ chạm đích trước?",
                color=discord.Color.blue(),
            )
            race_embed.set_image(url="attachment://race.png")
            race_message = await ctx.send(file=initial_file, embed=race_embed)

            while True:
                # Update positions
                for horse in selected_horses:
                    base_advance = random.randint(1, 2)
                    # Chance based on power to get extra speed
                    if random.randint(1, 100) <= horse["power"]:
                        advance = base_advance + 1
                    else:
                        advance = base_advance

                    raw_positions[horse["id"]] += advance
                    positions[horse["id"]] = min(TRACK_LENGTH, raw_positions[horse["id"]])

                finished = any(pos >= TRACK_LENGTH for pos in positions.values())

                # Generate updated race track image
                img_bytes = generate_horserace_image(selected_horses, positions, TRACK_LENGTH, lobby.bets, lobby.user_names)
                file = discord.File(img_bytes, filename="race.png")

                race_embed = make_embed(
                    title="🏇 CUỘC ĐUA ĐANG DIỄN RA 🏇",
                    description="Đường đua kịch tính! Các ngựa chiến đang tăng tốc...",
                    color=discord.Color.blue(),
                )
                race_embed.set_image(url="attachment://race.png")

                try:
                    await race_message.edit(embed=race_embed, attachments=[file])
                except discord.HTTPException:
                    pass

                if finished:
                    break

                await asyncio.sleep(1.5)

            # Sort horses to find the winner
            # Tie breakers: 1. raw position (highest first), 2. power (highest first), 3. random
            def get_sort_key(h):
                h_id = h["id"]
                return (raw_positions[h_id], h["power"], random.random())

            sorted_horses = sorted(selected_horses, key=get_sort_key, reverse=True)
            winner = sorted_horses[0]

            # Distribute payouts
            payouts = []
            winner_id = winner["id"]
            
            for user_id, horse_bets in lobby.bets.items():
                if winner_id in horse_bets:
                    bet_amount = horse_bets[winner_id]
                    payout_amount = int(bet_amount * winner["odds"])
                    # Payout consists of original bet + winnings (which is exactly bet_amount * odds)
                    self.economy.add_money(user_id, payout_amount)
                    
                    # Log wallet changes
                    log_wallet_change(
                        logger,
                        event="horserace_payout",
                        user_id=user_id,
                        money_delta=payout_amount,
                        horse_id=winner_id,
                        payout=payout_amount,
                    )
                    
                    user_mention = f"<@{user_id}>"
                    payouts.append(f"{user_mention} (+{payout_amount:,} VND)")

            # Record in history
            if guild_id not in self.history:
                self.history[guild_id] = []
            self.history[guild_id].append({
                "winner": winner["name"],
                "emoji": winner["emoji"],
                "odds": winner["odds"],
                "payouts": len(payouts) > 0
            })
            self.history[guild_id] = self.history[guild_id][-10:]

            # Generate final race track image
            final_img = generate_horserace_image(selected_horses, positions, TRACK_LENGTH, lobby.bets, lobby.user_names)
            final_file = discord.File(final_img, filename="race.png")

            # Determine track numbers of top 3
            def get_track_num(h):
                return selected_horses.index(h) + 1

            w_track = get_track_num(sorted_horses[0])
            h2_track = get_track_num(sorted_horses[1])
            h3_track = get_track_num(sorted_horses[2])

            final_desc = (
                "🏆 **Cuộc đua đã kết thúc!**\n"
                "Vòng đua đã hoàn thành. Phần thưởng đã được phân phối."
            )

            result_embed = make_embed(
                title=None,
                description=final_desc,
                color=discord.Color.gold(),
            )
            result_embed.set_image(url="attachment://race.png")

            payouts_str = ", ".join(payouts) if payouts else "Không có"
            
            result_embed.add_field(
                name=f"🏆 {winner['name']} về nhất!",
                value=(
                    f"Người thắng: {payouts_str}\n\n"
                    f"🥇 #{w_track} {winner['name']} | {winner['odds']}x → nhân {winner['odds']}\n"
                    f"🥈 #{h2_track} {sorted_horses[1]['name']} | về nhì\n"
                    f"🥉 #{h3_track} {sorted_horses[2]['name']} | về ba"
                ),
                inline=False,
            )

            view = HorseRaceResultView(self, ctx)
            await race_message.edit(embed=result_embed, attachments=[final_file], view=view)
            
            if payouts:
                # Ping winners in a follow-up message
                mentions_str = ", ".join(f"<@{uid}>" for uid in lobby.bets if winner_id in lobby.bets[uid])
                await ctx.send(f"🎉 Chúc mừng các người chơi đã đặt niềm tin vào {winner['emoji']} **{winner['name']}**: {mentions_str}!")

        except Exception as e:
            logger.exception("Error during horse race minigame")
            await ctx.send("❌ Đã xảy ra lỗi hệ thống trong lúc vận hành đường đua!")
        finally:
            self.active_races.pop(guild_id, None)


async def setup(bot: commands.Bot):
    await bot.add_cog(HorseRace(bot))
