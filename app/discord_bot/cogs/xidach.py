import logging
from contextlib import suppress
from io import BytesIO
from uuid import uuid4

import discord
import random
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.card import Card
from app.discord_bot.modules.card_table import render_card_table_bytes, render_multiplayer_table_bytes
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import InsufficientFundsException
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)

class Deck:
    def __init__(self):
        suits = ["clubs", "diamonds", "hearts", "spades"]
        self.cards = [Card(suit, value) for suit in suits for value in range(2, 15)]
        random.shuffle(self.cards)

    def draw(self):
        return self.cards.pop() if self.cards else None

    @staticmethod
    def calculate_score(hand):
        score = 0
        aces = 0
        for card in hand:
            if card.symbol in ['J', 'Q', 'K']:
                score += 10
            elif card.symbol == 'A':
                aces += 1
                score += 11
            else:
                score += card.value
        
        while score > 21 and aces:
            score -= 10
            aces -= 1
        return score

    @staticmethod
    def get_hand_rank(hand):
        """
        Ranks:
        - Bust (score > 21): 0
        - Normal points (score <= 21): score
        - Xì Dách (2 cards, score 21): 100
        - Ngũ Linh (5 cards, score <= 21): 200 + (21 - score)
        - Xì Bàng (2 cards, 2 Aces): 300
        """
        score = Deck.calculate_score(hand)
        num_cards = len(hand)
        
        # Check Xì Bàng (2 Aces)
        if num_cards == 2 and hand[0].symbol == 'A' and hand[1].symbol == 'A':
            return 300, score, "Xì Bàng"
            
        # Check Xì Dách (2 cards summing to 21)
        if num_cards == 2 and score == 21:
            return 100, score, "Xì Dách"
            
        # Check Bust
        if score > 21:
            return 0, score, "Quắc"
            
        # Check Ngũ Linh (5 cards summing to <= 21)
        if num_cards == 5 and score <= 21:
            return 200 + (21 - score), score, "Ngũ Linh"
            
        return score, score, f"{score} điểm"

# --- MODULE 4: HỆ THỐNG ĐỒNG BỘ PVP (KHÔNG NHÀ CÁI) ---
class GameSession:
    def __init__(self, channel, players, bet, deck, economy: Economy):
        self.channel = channel
        self.players = players
        self.bet = bet
        self.deck = deck
        self.economy = economy
        self.pending = len(players)
        self.results = {}
        self.player_hands = {}
        self.channel_message = None
        self.table_filename = f"xidach-lobby-{uuid4().hex}.png"

    def get_facedown_hands(self) -> list[list[Card]]:
        facedown_hands = []
        for player in self.players:
            hand = self.player_hands[player]
            facedown_hand = [Card(card.suit, card.value, down=True) for card in hand]
            facedown_hands.append(facedown_hand)
        return facedown_hands

    def render_lobby_table(self) -> discord.File:
        facedown_hands = self.get_facedown_hands()
        table_buffer = render_multiplayer_table_bytes(self.players, facedown_hands)
        return discord.File(fp=table_buffer, filename=self.table_filename)

    async def send_lobby_table(self):
        file = self.render_lobby_table()
        embed = discord.Embed(
            title="🎰 SÒNG XÌ DÁCH MULTIPLAYER",
            description="Đang phát bài và đợi các người chơi rút bài...",
            color=discord.Color.blue()
        )
        embed.set_image(url=f"attachment://{self.table_filename}")
        self.channel_message = await self.channel.send(file=file, embed=embed)

    async def update_lobby_table(self, player_action_desc: str):
        if not self.channel_message:
            return
        file = self.render_lobby_table()
        embed = discord.Embed(
            title="🎰 SÒNG XÌ DÁCH MULTIPLAYER",
            description=f"{player_action_desc}\nĐang đợi các người chơi khác...",
            color=discord.Color.blue()
        )
        embed.set_image(url=f"attachment://{self.table_filename}")
        try:
            await self.channel_message.edit(embed=embed, attachments=[file])
        except Exception:
            self.channel_message = await self.channel.send(file=file, embed=embed)

    async def player_done(self, player, hand, score, status):
        """Callback khi người chơi bốc xong"""
        rank, score, name = Deck.get_hand_rank(hand)
        self.results[player] = {'hand': hand, 'score': score, 'status': status, 'rank': rank, 'name': name}
        self.pending -= 1
        
        if self.pending == 0:
            await self.end_game()
        else:
            if rank >= 100:
                status_desc = f"trúng {name}"
            else:
                status_desc = "dằn bài"
            await self.update_lobby_table(f"🛑 {player.display_name} đã {status_desc}!")

    async def end_game(self):
        """Thuật toán so bài P2P: Tìm người có tổ hợp mạnh nhất"""
        if self.channel_message:
            with suppress(discord.HTTPException):
                await self.channel_message.delete()

        embed = discord.Embed(title="🎰 KẾT QUẢ SÒNG BÀI (PvP)", color=discord.Color.gold())
        
        # Lọc ra những người không bị Quắc (rank > 0)
        valid_results = {player: data for player, data in self.results.items() if data['rank'] > 0}
        
        if not valid_results:
            embed.description = "💥 **Tất cả đều QUẮC! Bàn này thối!**"
            max_rank = 0
        else:
            max_rank = max(data['rank'] for data in valid_results.values())
            
            # Đưa ra thông báo tổ hợp mạnh nhất bàn
            if max_rank >= 300:
                best_hand_name = "Xì Bàng"
            elif max_rank >= 200:
                best_hand_name = "Ngũ Linh"
            elif max_rank >= 100:
                best_hand_name = "Xì Dách"
            else:
                best_hand_name = f"{max_rank} điểm"
            embed.description = f"🏆 Tổ hợp mạnh nhất bàn: **{best_hand_name}**"
            
        winners: list[discord.Member | discord.User] = []
        if max_rank > 0:
            winners = [
                player
                for player, data in valid_results.items()
                if data['rank'] == max_rank
            ]

        pot = self.bet * len(self.players)
        payout_per_winner = 0
        if winners:
            payout_per_winner = pot // len(winners)

        # Chấm điểm từng người
        for player, data in self.results.items():
            p_score = data['score']
            p_rank = data['rank']
            p_name = data['name']
            money_delta = 0
            
            if p_rank == 0:
                result = "🔴 QUẮC (Thua)"
                money_delta = -self.bet
            elif p_rank == max_rank and max_rank > 0:
                if len(winners) > 1:
                    result = f"🟡 HÒA CHIA TIỀN ({p_name})"
                else:
                    result = f"👑 THẮNG CƯỢC ({p_name})"
                money_delta = payout_per_winner - self.bet
            else:
                result = f"🔴 THUA ({p_name})"
                money_delta = -self.bet

            if money_delta:
                self.economy.add_money(player.id, money_delta)
                if money_delta >= 1_000_000:
                    from app.discord_bot.modules.betting import reward_spouse_share
                    bot = self.channel.guild.me._state.client
                    await reward_spouse_share(bot, player.id, money_delta, self.channel)
            log_wallet_change(
                logger,
                event="xidach_pvp_settlement",
                user_id=player.id,
                money_delta=money_delta,
                bet=self.bet,
                score=p_score,
                status=data['status'],
                winners=len(winners),
            )

            p_hand_str = ', '.join(str(card) for card in data['hand'])
            embed.add_field(name=player.display_name, value=f"{p_hand_str} ➔ **{result}**", inline=False)

        # Render the final face up table for all player hands
        faceup_hands = [self.player_hands[player] for player in self.players]
        table_buffer = render_multiplayer_table_bytes(self.players, faceup_hands)
        file = discord.File(fp=table_buffer, filename=self.table_filename)
        embed.set_image(url=f"attachment://{self.table_filename}")

        await self.channel.send(file=file, embed=embed)


# --- MODULE 2: GIAO DIỆN BỐC BÀI (INBOX) ---
class PlayerHandView(discord.ui.View):
    def __init__(self, player, hand, deck, session):
        super().__init__(timeout=120)
        self.player = player
        self.hand = hand
        self.deck = deck
        self.session = session
        self.table_filename = f"xidach-{player.id}-{uuid4().hex}.png"

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.player.id:
            await interaction.response.send_message(
                "Đây là bài của bro, không được bấm hộ!",
                ephemeral=True,
            )
            return False
        return True

    def render_table(self) -> discord.File:
        table_buffer = render_multiplayer_table_bytes([self.player], [self.hand])
        return discord.File(fp=table_buffer, filename=self.table_filename)

    def create_embed(self, score, status="playing"):
        color = discord.Color.blue()
        desc = "Suy nghĩ kỹ trước khi bốc nhé!"
        if status == "bust":
            color = discord.Color.red()
            desc = "💥 **QUẮC RỒI! Toang!**"
        elif status == "stand":
            color = discord.Color.green()
            desc = "🛑 **Đã chốt hạ!** Đang chờ các tay chơi khác..."
            
        embed = discord.Embed(title="🎰 SÒNG XÌ DÁCH MULTIPLAYER", description=desc, color=color)
        embed.add_field(name="Điểm số", value=f"`{score}`", inline=False)
        embed.set_image(url=f"attachment://{self.table_filename}")
        return embed

    @discord.ui.button(label="Rút thêm", style=discord.ButtonStyle.primary, emoji="👆")
    async def hit_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.hand.append(self.deck.draw())
        score = Deck.calculate_score(self.hand)
        self.session.player_hands[self.player] = self.hand
        
        rank, score, name_vn = Deck.get_hand_rank(self.hand)
        num_cards = len(self.hand)
        
        if score > 21:
            for child in self.children:
                child.disabled = True
            file = self.render_table()
            await interaction.response.edit_message(
                embed=self.create_embed(score, "bust"),
                view=self,
                attachments=[file],
            )
            self.stop()
            await self.session.player_done(self.player, self.hand, score, "bust")
        elif num_cards == 5:
            for child in self.children:
                child.disabled = True
            file = self.render_table()
            embed = self.create_embed(score, "stand")
            embed.description = f"🎉 **Chúc mừng! Bạn đã đạt {name_vn}!**"
            embed.color = discord.Color.gold()
            await interaction.response.edit_message(
                embed=embed,
                view=self,
                attachments=[file],
            )
            self.stop()
            await self.session.player_done(self.player, self.hand, score, "stand")
        else:
            file = self.render_table()
            await interaction.response.edit_message(
                embed=self.create_embed(score, "playing"),
                view=self,
                attachments=[file],
            )
            await self.session.update_lobby_table(f"🔥 {self.player.display_name} đã rút thêm 1 lá bài!")

    @discord.ui.button(label="Dừng", style=discord.ButtonStyle.danger, emoji="🛑")
    async def stand_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        score = Deck.calculate_score(self.hand)
        if score < 16:
            await interaction.response.send_message(
                "❌ Bạn chưa đủ 16 điểm (điểm dằn tối thiểu) để dằn bài! Vui lòng rút thêm.",
                ephemeral=True,
            )
            return
            
        for child in self.children:
            child.disabled = True
        file = self.render_table()
        await interaction.response.edit_message(
            embed=self.create_embed(score, "stand"),
            view=self,
            attachments=[file],
        )
        self.stop()
        await self.session.player_done(self.player, self.hand, score, "stand")


# --- MODULE 3: SẢNH CHỜ GIAO DỊCH ---
class LobbyView(discord.ui.View):
    def __init__(self, bet_amount, host, economy: Economy):
        super().__init__(timeout=120)
        self.bet_amount = bet_amount
        self.host = host
        self.economy = economy
        self.players = [host]

    def _validate_player_funds(self, user: discord.Member | discord.User) -> str | None:
        try:
            validate_money_bet(self.economy, user.id, self.bet_amount)
        except InsufficientFundsException as exc:
            return str(exc)
        except Exception:
            return "Mức cược không hợp lệ."
        return None

    @discord.ui.button(label="Lên thuyền", style=discord.ButtonStyle.green, emoji="🎟️")
    async def join_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("Bro đã ngồi trong sòng rồi!", ephemeral=True)
            return

        if len(self.players) >= 6:
            await interaction.response.send_message("Sòng bài đã đầy! (Tối đa 6 người chơi)", ephemeral=True)
            return

        funds_error = self._validate_player_funds(interaction.user)
        if funds_error:
            await interaction.response.send_message(funds_error, ephemeral=True)
            return
        
        self.players.append(interaction.user)
        await interaction.response.send_message(
            f"🔥 {interaction.user.mention} đã lên thuyền với cược {self.bet_amount:,} VND!",
            ephemeral=False,
        )

    @discord.ui.button(label="Bắt đầu chia bài", style=discord.ButtonStyle.blurple, emoji="🃏")
    async def start_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("Bro không phải chủ sảnh, cất tay đi!", ephemeral=True)
            return

        if len(self.players) < 2:
            await interaction.response.send_message("Cần ít nhất 2 người mới bắt đầu được!", ephemeral=True)
            return

        if len(self.players) > 6:
            await interaction.response.send_message("Sòng bài chỉ chứa tối đa 6 người chơi!", ephemeral=True)
            return

        for player in self.players:
            funds_error = self._validate_player_funds(player)
            if funds_error:
                await interaction.response.send_message(
                    f"{player.mention} không đủ tiền ({self.bet_amount:,} VND cần thiết).",
                    ephemeral=True,
                )
                return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        
        await interaction.followup.send("🎲 **Chốt sổ! Đang phát bài vào Inbox từng người...**")
        
        game_deck = Deck()
        
        session = GameSession(
            interaction.channel,
            self.players,
            self.bet_amount,
            game_deck,
            self.economy,
        )

        for player in self.players:
            player_hand = [game_deck.draw(), game_deck.draw()]
            session.player_hands[player] = player_hand

        await session.send_lobby_table()

        for player in self.players:
            player_hand = session.player_hands[player]
            rank, score, name_vn = Deck.get_hand_rank(player_hand)
            view = PlayerHandView(player, player_hand, game_deck, session)
            
            is_special = rank >= 100
            if is_special:
                for child in view.children:
                    child.disabled = True
                view.stop()

            try:
                file = view.render_table()
                embed = view.create_embed(score, "playing")
                if is_special:
                    embed.description = f"🎉 **Chúc mừng! Bạn đã trúng {name_vn}!**"
                    embed.color = discord.Color.gold()
                await player.send(embed=embed, view=view, file=file)
            except discord.Forbidden:
                await interaction.channel.send(f"⚠️ Ê {player.mention}, mở Inbox lên bot mới chia bài được!")
                session.pending -= 1
                if session.pending == 0:
                    await session.end_game()
                continue
                
            if is_special:
                await session.player_done(player, player_hand, score, "stand")
                
        self.stop()

class MultiBlackjack(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", Economy())

    @commands.command(name="party")
    async def open_party(self, ctx, bet: int = config.bot.default_bet):
        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
        except InsufficientFundsException as exc:
            await ctx.send(str(exc))
            return

        view = LobbyView(bet, ctx.author, self.economy)
        embed = discord.Embed(
            title="🎰 SẢNH XÌ DÁCH PVP (Tối đa 6 người)",
            description=(
                f"**Chủ sảnh:** {ctx.author.mention}\n"
                f"**Mức cược:** `{bet:,} VND/người`\n\n"
                "👉 Bấm nút để góp vốn! Ai điểm cao nhất ăn tất! (Tối đa 6 người)"
            ),
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed, view=view)