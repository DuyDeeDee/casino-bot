import asyncio
import logging
import random
import time
import json
from io import BytesIO
from uuid import uuid4

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed, InsufficientFundsException
from app.discord_bot.modules.wallet_logging import log_wallet_change
from app.discord_bot.modules.card import Card
from app.discord_bot.modules.card_table import render_card_table_bytes

logger = logging.getLogger(__name__)

# --- HELPERS ---
def card_to_emoji_str(card: Card) -> str:
    if card.down:
        return "🎴"
    emoji_suits = {
        "clubs": "♣️",
        "diamonds": "♦️",
        "hearts": "♥️",
        "spades": "♠️"
    }
    val_names = {
        "jack": "J",
        "queen": "Q",
        "king": "K",
        "ace": "A",
    }
    val = val_names.get(card.name, card.name)
    return f"{val}{emoji_suits[card.suit]}"

def get_card_strength(card: Card) -> tuple[int, int]:
    val_map = {
        "2": 2, "3": 3, "4": 4, "5": 5, "6": 6, "7": 7, "8": 8, "9": 9, "10": 10,
        "J": 11, "Q": 12, "K": 13, "A": 14
    }
    suit_map = {
        "spades": 1, "clubs": 2, "diamonds": 3, "hearts": 4
    }
    val_char = "10" if card.name == "10" else card.symbol
    return (val_map[val_char], suit_map[card.suit])

def evaluate_hand(hand: list[Card]) -> tuple[int, str, tuple[int, int]]:
    strongest_card = max(hand, key=get_card_strength)
    strongest_key = get_card_strength(strongest_card)

    symbols = ["10" if c.name == "10" else c.symbol for c in hand]
    
    # Check Ba Át (AAA)
    if all(s == "A" for s in symbols):
        return (12, "Ba Át", strongest_key)

    # Check Ba Cào (Three of a Kind)
    if symbols[0] == symbols[1] == symbols[2]:
        return (11, f"Ba Cào ({symbols[0]})", strongest_key)

    # Check Ba Tây (Three Picture Cards)
    if all(s in ["J", "Q", "K"] for s in symbols):
        return (10, "Ba Tây", strongest_key)

    # Calculate Normal Points
    total_score = 0
    for card in hand:
        s = "10" if card.name == "10" else card.symbol
        if s in ["J", "Q", "K"]:
            total_score += 10
        elif s == "A":
            total_score += 1
        else:
            total_score += int(s)
    
    nut = total_score % 10
    return (nut, f"{nut} nút", strongest_key)


class Deck:
    def __init__(self):
        suits = ["clubs", "diamonds", "hearts", "spades"]
        self.cards = [Card(suit, value) for suit in suits for value in range(2, 15)]
        random.shuffle(self.cards)

    def draw(self) -> Card | None:
        return self.cards.pop() if self.cards else None


# --- GAME VIEWS & MODALS ---
class BaitoRaiseModal(discord.ui.Modal, title="Tố bài"):
    raise_input = discord.ui.TextInput(
        label="Số tiền tố thêm (VND)",
        placeholder="Ví dụ: 100000",
        min_length=1,
        max_length=15,
        required=True
    )

    def __init__(self, game_view):
        super().__init__()
        self.game_view = game_view

    async def on_submit(self, interaction: discord.Interaction):
        try:
            val = int(self.raise_input.value.strip().replace(",", "").replace(".", ""))
            if val <= 0:
                raise ValueError("Số tiền phải lớn hơn 0")
        except ValueError:
            await interaction.response.send_message("❌ Số tiền nhập vào không hợp lệ!", ephemeral=True)
            return

        await self.game_view.process_raise(interaction, val)


class PlayerPrivateHandView(discord.ui.View):
    def __init__(self, player, hand, session):
        super().__init__(timeout=180)
        self.player = player
        self.hand = hand
        self.session = session
        self.revealed = False

    @discord.ui.button(label="👁️ Xem bài", style=discord.ButtonStyle.primary)
    async def reveal_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.revealed:
            await interaction.response.send_message("Bài của bạn đã được xem rồi!", ephemeral=True)
            return
            
        self.revealed = True
        button.disabled = True
        
        # Mark seen in session
        p_id = interaction.user.id
        if p_id in self.session.player_states:
            self.session.player_states[p_id]["has_seen_cards"] = True
            
            # Sync main channel view if it exists
            if self.session.game_view and self.session.game_msg:
                self.session.game_view.update_buttons()
                embed_main = self.session.game_view.get_embed()
                try:
                    await self.session.game_msg.edit(embed=embed_main, view=self.session.game_view)
                except Exception as e:
                    logger.error(f"Failed to edit game message on hand reveal: {e}")
            
        # Get hand rank
        rank_val, rank_name, _ = evaluate_hand(self.hand)
        cards_str = " ".join(card_to_emoji_str(c) for c in self.hand)
        
        desc = (
            f"🃏 **Bài của bạn:** {cards_str}\n"
            f"📊 **Tổ hợp:** `{rank_name}`\n\n"
            f"*(⚠️ Bạn đã xem bài nên không thể Tố Mù trong lượt này nữa!)*"
        )
        
        embed = discord.Embed(
            title="🃏 BÀI TỐ - BÀI CỦA BẠN",
            description=desc,
            color=discord.Color.blue()
        )
        await interaction.response.edit_message(embed=embed, view=self)


class BaitoGameView(discord.ui.View):
    def __init__(self, session):
        super().__init__(timeout=60)
        self.session = session
        self.message = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        current_player = self.session.get_current_player()
        if not current_player or interaction.user.id != current_player.id:
            await interaction.response.send_message("❌ Không phải lượt của bạn!", ephemeral=True)
            return False
        return True

    async def on_timeout(self) -> None:
        # Auto fold current player
        current_player = self.session.get_current_player()
        if current_player:
            await self.session.process_fold_action(current_player)

    def get_embed(self) -> discord.Embed:
        curr_p = self.session.get_current_player()
        curr_p_mention = curr_p.mention if curr_p else "Không có"
        
        needed = self.session.current_bet - self.session.player_states[curr_p.id]["contribution"] if curr_p else 0
        
        history_str = "\n".join(self.session.action_history[-8:]) if self.session.action_history else "Chưa có hành động nào."
        
        players_status = []
        for p in self.session.players:
            state = self.session.player_states[p.id]
            status_emoji = "🟢 Đang chờ"
            if state["status"] == "folded":
                status_emoji = "🛑 Đã Úp"
            elif state["status"] == "all_in":
                status_emoji = "💎 Tất Tay"
            elif p.id == (curr_p.id if curr_p else 0):
                status_emoji = "👉 Lượt"
            
            seen_str = "😎 Tố Mù" if not state["has_seen_cards"] else "👁️ Đã xem"
            players_status.append(
                f"- {p.display_name}: **{state['contribution']:,} VND** ({status_emoji} | {seen_str})"
            )
            
        players_list_str = "\n".join(players_status)
        
        desc = (
            f"👉 **Lượt của:** {curr_p_mention}\n"
            f"💰 **Số tiền cần theo:** `{needed:,} VND` (Mức cược sàn: `{self.session.bet_amount:,} VND`)\n"
            f"🏆 **Tổng Pot:** `{self.session.pot:,} VND`\n\n"
            f"👥 **Danh sách người chơi:**\n"
            f"{players_list_str}\n\n"
            f"📜 **Nhật ký ván bài:**\n"
            f"```\n{history_str}\n```"
        )
        
        embed = discord.Embed(
            title=f"🃏 PHÒNG BÀI TỐ #{self.session.room_id}",
            description=desc,
            color=discord.Color.gold()
        )
        return embed

    def update_buttons(self):
        curr_p = self.session.get_current_player()
        if not curr_p:
            return
            
        state = self.session.player_states[curr_p.id]
        needed = self.session.current_bet - state["contribution"]
        user_bal = self.session.economy.get_entry(curr_p.id)[1]
        
        # Check / Call button label
        for child in self.children:
            if child.custom_id == "call_btn":
                if needed == 0:
                    child.label = "Nhường (Check)"
                    child.style = discord.ButtonStyle.success
                else:
                    child.label = f"Theo (Call) {needed:,}"
                    child.style = discord.ButtonStyle.primary
                
                # Disable call if they can't afford
                child.disabled = (needed > user_bal)
            
            elif child.custom_id == "raise_btn":
                # Disable raise if they can't afford at least minimum bet more
                min_raise_cost = needed + self.session.bet_amount
                child.disabled = (min_raise_cost > user_bal)
                if not state["has_seen_cards"]:
                    child.label = "Tố Mù (Blind)"
                else:
                    child.label = "Tố (Raise)"

    @discord.ui.button(label="Theo", style=discord.ButtonStyle.primary, custom_id="call_btn")
    async def call_click(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()
        await self.session.process_call_action(interaction.user)

    @discord.ui.button(label="Tố", style=discord.ButtonStyle.secondary, custom_id="raise_btn")
    async def raise_click(self, interaction: discord.Interaction, _: discord.ui.Button):
        modal = BaitoRaiseModal(self)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="Úp bài", style=discord.ButtonStyle.danger, custom_id="fold_btn")
    async def fold_click(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()
        await self.session.process_fold_action(interaction.user)

    @discord.ui.button(label="Tất tay", style=discord.ButtonStyle.secondary, emoji="💎", custom_id="allin_btn")
    async def allin_click(self, interaction: discord.Interaction, _: discord.ui.Button):
        await interaction.response.defer()
        await self.session.process_allin_action(interaction.user)

    async def process_raise(self, interaction: discord.Interaction, raise_amt: int):
        await interaction.response.defer()
        await self.session.process_raise_action(interaction.user, raise_amt)


class LobbyView(discord.ui.View):
    def __init__(self, bet_amount, host, economy: Economy, cog):
        super().__init__(timeout=120)
        self.bet_amount = bet_amount
        self.host = host
        self.economy = economy
        self.cog = cog
        self.players = [host]
        self.message = None

    def get_embed(self) -> discord.Embed:
        desc = (
            f"**Chủ sảnh:** {self.host.mention}\n"
            f"**Mức cược sàn:** `{self.bet_amount:,} VND`\n\n"
            f"👥 **Người chơi đã tham gia ({len(self.players)}/6):**\n"
            + "\n".join(f"- {p.mention} ({self.economy.get_entry(p.id)[1]:,} VND)" for p in self.players)
            + "\n\n👉 Bấm nút để tham gia vào sảnh Bài Tố."
        )
        embed = discord.Embed(
            title=f"🃏 PHÒNG CHỜ BÀI TỐ",
            description=desc,
            color=discord.Color.gold()
        )
        return embed

    @discord.ui.button(label="🎟️ Tham gia", style=discord.ButtonStyle.green)
    async def join_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user in self.players:
            await interaction.response.send_message("Bro đã tham gia phòng này rồi!", ephemeral=True)
            return

        if len(self.players) >= 6:
            await interaction.response.send_message("Phòng đã đầy! (Tối đa 6 người chơi)", ephemeral=True)
            return

        # Check funds
        try:
            validate_money_bet(self.economy, interaction.user.id, self.bet_amount)
        except InsufficientFundsException as e:
            await interaction.response.send_message(str(e), ephemeral=True)
            return

        self.players.append(interaction.user)
        embed = self.get_embed()
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="🃏 Bắt đầu", style=discord.ButtonStyle.primary)
    async def start_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("Bạn không phải chủ phòng!", ephemeral=True)
            return

        if len(self.players) < 2:
            await interaction.response.send_message("Cần tối thiểu 2 người chơi để bắt đầu!", ephemeral=True)
            return

        # Validate everyone's funds again
        for p in self.players:
            try:
                validate_money_bet(self.economy, p.id, self.bet_amount)
            except InsufficientFundsException:
                await interaction.response.send_message(f"❌ Không thể bắt đầu: {p.mention} không đủ tiền cược sàn!", ephemeral=True)
                return

        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)
        self.stop()

        # Launch Game Session
        session = GameSession(self.cog, interaction.channel, self.players, self.bet_amount)
        await session.start()

    @discord.ui.button(label="❌ Hủy phòng", style=discord.ButtonStyle.danger)
    async def cancel_btn(self, interaction: discord.Interaction, _: discord.ui.Button):
        if interaction.user != self.host:
            await interaction.response.send_message("Bạn không phải chủ phòng!", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        embed = discord.Embed(
            title="🃏 PHÒNG CHỜ BÀI TỐ",
            description="❌ Phòng chờ đã bị chủ phòng hủy bỏ.",
            color=discord.Color.red()
        )
        await interaction.response.edit_message(embed=embed, view=self)
        self.stop()


# --- GAME SESSION ENGINE ---
class GameSession:
    def __init__(self, cog, channel, players, bet_amount):
        self.cog = cog
        self.channel = channel
        self.players = players
        self.bet_amount = bet_amount
        self.economy = cog.economy
        self.room_id = random.randint(1000, 9999)
        self.pot = 0
        self.deck = Deck()
        self.player_states = {}
        self.active_player_sequence = []
        self.current_turn_index = 0
        self.current_bet = bet_amount
        self.action_history = []
        self.game_view = None
        self.game_msg = None
        self.blind_winners = set()
        
    def get_current_player(self) -> discord.Member | None:
        if not self.active_player_sequence:
            return None
        return self.active_player_sequence[self.current_turn_index]

    async def start(self):
        # 1. Deduct minimum bet (cược sàn) from all players
        for p in self.players:
            self.economy.add_money(p.id, -self.bet_amount)
            log_wallet_change(
                logger,
                event="baito_initial_bet",
                user_id=p.id,
                money_delta=-self.bet_amount,
                bet=self.bet_amount,
                room_id=self.room_id
            )
            
            # Deal cards
            hand = [self.deck.draw(), self.deck.draw(), self.deck.draw()]
            self.player_states[p.id] = {
                "hand": hand,
                "contribution": self.bet_amount,
                "status": "active",
                "has_seen_cards": False,
                "went_allin": False
            }
            self.pot += self.bet_amount
            
        self.active_player_sequence = list(self.players)
        self.action_history.append(f"Ván bài bắt đầu! Mỗi người đóng cược sàn {self.bet_amount:,} VND.")
        
        # Send private hands in DM
        for p in self.players:
            hand = self.player_states[p.id]["hand"]
            view = PlayerPrivateHandView(p, hand, self)
            embed = discord.Embed(
                title=f"🃏 BÀI TỐ - PHÒNG #{self.room_id}",
                description="Bấm nút bên dưới để xem 3 lá bài của bạn. Nếu bạn Tố khi chưa xem bài, hành động sẽ được tính là **Tố Mù**!",
                color=discord.Color.gold()
            )
            try:
                await p.send(embed=embed, view=view)
            except discord.Forbidden:
                await self.channel.send(f"⚠️ {p.mention}, vui lòng mở DM với bot để nhận bài!")

        # Send main game view to channel
        self.game_view = BaitoGameView(self)
        self.game_view.update_buttons()
        embed = self.game_view.get_embed()
        self.game_msg = await self.channel.send(embed=embed, view=self.game_view)
        self.game_view.message = self.game_msg

    async def process_call_action(self, user: discord.Member):
        state = self.player_states[user.id]
        needed = self.current_bet - state["contribution"]
        
        if needed > 0:
            self.economy.add_money(user.id, -needed)
            log_wallet_change(
                logger,
                event="baito_call",
                user_id=user.id,
                money_delta=-needed,
                room_id=self.room_id
            )
            state["contribution"] = self.current_bet
            self.pot += needed
            self.action_history.append(f"🟢 {user.display_name} đã Theo {needed:,} VND.")
        else:
            self.action_history.append(f"🟢 {user.display_name} đã Nhường (Check).")
            
        await self.advance_turn()

    async def process_raise_action(self, user: discord.Member, raise_amt: int):
        state = self.player_states[user.id]
        call_needed = self.current_bet - state["contribution"]
        total_cost = call_needed + raise_amt
        
        self.economy.add_money(user.id, -total_cost)
        log_wallet_change(
            logger,
            event="baito_raise",
            user_id=user.id,
            money_delta=-total_cost,
            room_id=self.room_id
        )
        
        self.current_bet += raise_amt
        state["contribution"] = self.current_bet
        self.pot += total_cost
        
        blind_tag = " MÙ" if not state["has_seen_cards"] else ""
        self.action_history.append(f"🔺 {user.display_name} đã TỐ{blind_tag} thêm {raise_amt:,} VND (Cược hiện tại: {self.current_bet:,} VND).")
        
        await self.advance_turn()

    async def process_fold_action(self, user: discord.Member):
        state = self.player_states[user.id]
        state["status"] = "folded"
        self.action_history.append(f"🛑 {user.display_name} đã Úp bài (Fold).")
        
        await self.advance_turn()

    async def process_allin_action(self, user: discord.Member):
        state = self.player_states[user.id]
        user_bal = self.economy.get_entry(user.id)[1]
        
        self.economy.add_money(user.id, -user_bal)
        log_wallet_change(
            logger,
            event="baito_allin",
            user_id=user.id,
            money_delta=-user_bal,
            room_id=self.room_id
        )
        
        state["contribution"] += user_bal
        self.pot += user_bal
        state["status"] = "all_in"
        state["went_allin"] = True
        
        if state["contribution"] > self.current_bet:
            self.current_bet = state["contribution"]
            
        self.action_history.append(f"💎 {user.display_name} đã TẤT TAY toàn bộ {user_bal:,} VND!")
        await self.advance_turn()

    async def advance_turn(self):
        # Filter remaining players
        non_folded = [p for p in self.players if self.player_states[p.id]["status"] != "folded"]
        
        # If only 1 player remains, they win immediately
        if len(non_folded) == 1:
            await self.end_game(winner_override=non_folded[0])
            return

        # Check if betting round is complete
        # A round is complete if all active (non-folded, non-all_in) players have contribution == current_bet
        active_players = [p for p in non_folded if self.player_states[p.id]["status"] == "active"]
        
        # If no active players left (everyone is either folded or all-in), showdown!
        if not active_players:
            await self.end_game()
            return
            
        # Check if everyone has matched the current bet
        is_complete = True
        for p in active_players:
            if self.player_states[p.id]["contribution"] != self.current_bet:
                is_complete = False
                break
                
        # If complete, showdown!
        if is_complete and len(self.action_history) >= len(self.players):
            await self.end_game()
            return
            
        # Otherwise, move to next active player
        while True:
            self.current_turn_index = (self.current_turn_index + 1) % len(self.active_player_sequence)
            next_p = self.active_player_sequence[self.current_turn_index]
            if self.player_states[next_p.id]["status"] == "active":
                break
                
        # Update view
        self.game_view.update_buttons()
        embed = self.game_view.get_embed()
        try:
            await self.game_msg.edit(embed=embed, view=self.game_view)
        except Exception:
            self.game_msg = await self.channel.send(embed=embed, view=self.game_view)
            self.game_view.message = self.game_msg

    async def end_game(self, winner_override=None):
        if self.game_view:
            self.game_view.stop()
            
        embed = discord.Embed(title="🃏 KẾT QUẢ VÁN BÀI TỐ", color=discord.Color.gold())
        
        non_folded = [p for p in self.players if self.player_states[p.id]["status"] != "folded"]
        
        winner_p = None
        if winner_override:
            winner_p = winner_override
            rank_val, rank_name, _ = evaluate_hand(self.player_states[winner_p.id]["hand"])
            desc = f"🏆 **{winner_p.mention}** thắng cuộc do tất cả đối thủ khác đã Úp bài!\n💰 **Tiền thưởng nhận:** `+{self.pot:,} VND`"
            embed.description = desc
        else:
            # Showdown comparison
            results = []
            for p in non_folded:
                hand = self.player_states[p.id]["hand"]
                rank_val, rank_name, strongest_key = evaluate_hand(hand)
                results.append((p, rank_val, rank_name, strongest_key))
                
            # Sort by rank_val DESC, then strongest_key (value_rank DESC, suit_rank DESC)
            # Python sort is stable, we sort by secondary key then primary key
            results.sort(key=lambda x: (x[1], x[3]), reverse=True)
            
            # Check for split pot ties (if rank and strongest card strength are identical)
            best = results[0]
            winners = [best[0]]
            for r in results[1:]:
                if r[1] == best[1] and r[3] == best[3]:
                    winners.append(r[0])
                else:
                    break
                    
            payout = self.pot // len(winners)
            
            winner_p = winners[0] # primary winner for logging single stats
            
            winners_str = ", ".join(w.mention for w in winners)
            desc = f"🏆 Người thắng cuộc: {winners_str}\n📊 Bài mạnh nhất: `{best[2]}`\n💰 Tiền thưởng: `+{payout:,} VND` mỗi người\n\n"
            
            # Build hands log
            hands_log = []
            for p, r_val, r_name, _ in results:
                hand = self.player_states[p.id]["hand"]
                cards_str = " ".join(card_to_emoji_str(c) for c in hand)
                hands_log.append(f"- {p.display_name}: {cards_str} ➔ **{r_name}**")
                
            desc += "\n".join(hands_log)
            embed.description = desc
            
            # Render card table image
            hands_to_render = []
            for p in self.players:
                state = self.player_states[p.id]
                if state["status"] == "folded":
                    hands_to_render.append([Card(c.suit, c.value, down=True) for c in state["hand"]])
                else:
                    hands_to_render.append(state["hand"])
            
            table_buffer = render_card_table_bytes(None, hands_to_render)
            filename = f"baito-showdown-{uuid4().hex}.png"
            file = discord.File(fp=table_buffer, filename=filename)
            embed.set_image(url=f"attachment://{filename}")
            
            # Settlement payout
            for w in winners:
                self.economy.add_money(w.id, payout)
                log_wallet_change(
                    logger,
                    event="baito_payout",
                    user_id=w.id,
                    money_delta=payout,
                    room_id=self.room_id
                )
                
        # 2. Update stats and achievements in Database
        for p in self.players:
            state = self.player_states[p.id]
            is_winner = (p.id == winner_p.id) if not winner_override else (p == winner_p)
            winnings = self.pot if is_winner else 0
            if not winner_override and not winner_p: # split pot
                winnings = payout if p in winners else 0
                
            net_profit = winnings - state["contribution"]
            
            # Retrieve stats
            stats = self.economy.get_baito_stats(p.id)
            
            # Calculate new streak
            if winnings > 0:
                new_streak = stats["streak"] + 1
            else:
                new_streak = 0
            new_max_streak = max(stats["max_streak"], new_streak)
            
            hand_rank, _, _ = evaluate_hand(state["hand"])
            
            # Blind state check
            was_blind = not state["has_seen_cards"]
            
            update_payload = {
                "plays": 1,
                "wins": 1 if winnings > 0 else 0,
                "profit": net_profit,
                "streak": new_streak,
                "max_streak": new_max_streak,
                "point_9_wins": 1 if (winnings > 0 and hand_rank == 9) else 0,
                "batay_wins": 1 if (winnings > 0 and hand_rank == 10) else 0,
                "bacao_wins": 1 if (winnings > 0 and hand_rank == 11) else 0,
                "baat_wins": 1 if (winnings > 0 and hand_rank == 12) else 0,
                "all_in_plays": 1 if state["went_allin"] else 0,
                "blind_plays": 1 if was_blind else 0,
                "blind_wins": 1 if (winnings > 0 and was_blind) else 0,
            }
            
            if winnings > 0 and was_blind:
                cur_max_blind = stats["max_blind_win_amount"]
                update_payload["max_blind_win_amount"] = max(cur_max_blind, net_profit)
                
            # Reload stats with updates to check achievements
            simulated_stats = {
                "plays": stats["plays"] + 1,
                "wins": stats["wins"] + (1 if winnings > 0 else 0),
                "streak": new_streak,
                "achievements": stats["achievements"]
            }
            
            new_ach_list, unlocks = check_and_update_achievements(
                simulated_stats, 
                won=(winnings > 0), 
                went_allin=state["went_allin"], 
                was_blind=was_blind, 
                hand_rank=hand_rank
            )
            
            if unlocks:
                update_payload["achievements"] = new_ach_list
                # Send achievements unlocked notification
                unlocks_str = ", ".join(unlocks)
                await self.channel.send(f"🏆 **{p.mention} đã mở khóa thành tựu:** {unlocks_str}!")
                
            self.economy.update_baito_stats(p.id, **update_payload)
            
        if not winner_override:
            await self.channel.send(file=file, embed=embed)
        else:
            await self.channel.send(embed=embed)


def check_and_update_achievements(stats: dict, won: bool, went_allin: bool, was_blind: bool, hand_rank: int) -> tuple[list[str], list[str]]:
    unlocked = list(stats.get("achievements", []))
    new_unlocks = []
    
    rules = {
        "first_play": ("🃏 Chơi lần đầu", lambda s: s["plays"] >= 1),
        "wins_10": ("🥉 Thắng 10 ván", lambda s: s["wins"] >= 10),
        "wins_100": ("🥈 Thắng 100 ván", lambda s: s["wins"] >= 100),
        "point_9_win": ("🔥 Có 9 nút", lambda s: won and hand_rank == 9),
        "batay_win": ("👑 Có Ba Tây", lambda s: won and hand_rank == 10),
        "bacao_win": ("💎 Có Ba Cào", lambda s: won and hand_rank == 11),
        "baat_win": ("🌟 Có Ba Át", lambda s: won and hand_rank == 12),
        "allin_win": ("💰 All In thành công", lambda s: won and went_allin),
        "blind_win": ("🎭 Tố mù thắng cuộc", lambda s: won and was_blind),
        "streak_5": ("🔥 Thắng 5 ván liên tiếp", lambda s: s["streak"] >= 5)
    }
    
    for key, (name, cond) in rules.items():
        if key not in unlocked and cond(stats):
            unlocked.append(key)
            new_unlocks.append(name)
            
    return unlocked, new_unlocks


class Baito(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.economy = getattr(bot, "economy", Economy())

    @commands.group(name="baito", brief="Bài Tố kiểu Bài Cào 3 lá.", usage="baito [subcommand]", invoke_without_command=True)
    async def baito_group(self, ctx: commands.Context):
        prefix = ctx.prefix
        desc = (
            "🃏 **HỆ THỐNG BÀI TỐ (BÀI CÀO TỐ)** 🃏\n\n"
            f"🔹 `{prefix}baito create [tiền_cược]` — Tạo phòng Bài Tố cược sàn mong muốn (mặc định: 100.000 VNĐ).\n"
            f"🔹 `{prefix}baito join` — Tham gia vào phòng Bài Tố đang mở.\n"
            f"🔹 `{prefix}baito stats [người_chơi]` — Xem bảng thống kê và thành tựu Bài Tố của người chơi.\n\n"
            "📖 **Luật chơi đơn giản:**\n"
            "- Mỗi người nhận 3 lá bài mặt úp (xem trong DM).\n"
            "- Có thể chọn Tố Mù (Blind Raise) khi chưa xem bài để ăn hũ Blind Win cực chất.\n"
            "- Tổng điểm modulo 10 (J, Q, K = 10; A = 1). Mạnh nhất là 9 nút, tiếp đó là các tổ hợp đặc biệt:\n"
            "  👉 **Ba Tây** (3 lá hình J Q K) ➔ **Ba Cào** (3 lá giống nhau) ➔ **Ba Át** (AAA - vô địch).\n"
        )
        embed = discord.Embed(
            title="🎮 HỆ THỐNG BÀI TỐ - CASINO BOT 🎮",
            description=desc,
            color=discord.Color.gold()
        )
        embed.set_thumbnail(url=ctx.author.display_avatar.url)
        await ctx.send(embed=embed)

    @baito_group.command(name="create", brief="Tạo phòng Bài Tố mới.")
    async def baito_create(self, ctx: commands.Context, bet: int = config.bot.default_bet):
        if bet < 1000:
            await ctx.send("❌ Cược sàn tối thiểu phải từ 1,000 VND trở lên!")
            return
            
        try:
            validate_money_bet(self.economy, ctx.author.id, bet)
        except InsufficientFundsException as e:
            await ctx.send(str(e))
            return

        view = LobbyView(bet, ctx.author, self.economy, self)
        embed = view.get_embed()
        msg = await ctx.send(embed=embed, view=view)
        view.message = msg

    @baito_group.command(name="join", brief="Tham gia phòng Bài Tố đang mở.")
    async def baito_join(self, ctx: commands.Context):
        # We search active LobbyViews in open messages
        await ctx.send("👉 Để tham gia phòng bài tố, vui lòng nhấp vào nút **🎟️ Tham gia** trên tin nhắn phòng chờ đang mở!")

    @baito_group.command(name="stats", brief="Xem thống kê thành tích Bài Tố.")
    async def baito_stats(self, ctx: commands.Context, member: discord.Member | None = None):
        target = member or ctx.author
        stats = self.economy.get_baito_stats(target.id)
        
        plays = stats["plays"]
        wins = stats["wins"]
        winrate = (wins / plays * 100) if plays > 0 else 0.0
        profit = stats["profit"]
        
        # Determine Title
        title = "🃏 Tân Binh Bài Cào"
        ach_unlocked = stats["achievements"]
        
        if wins >= 10 and winrate >= 50.0:
            title = "🍀 Thần Bài"
        if profit >= 50_000_000:
            title = "💰 Bá Chủ Sòng Bài"
        if wins >= 100:
            title = "👑 Vua Bài Tố"
        if stats["baat_wins"] >= 1 or "streak_5" in ach_unlocked:
            title = "🏆 Huyền Thoại Casino"
            
        # Format stats embed
        desc = (
            f"👑 **Danh hiệu:** `{title}`\n\n"
            f"📊 **Tổng quan số liệu:**\n"
            f"- Đã chơi: `{plays}` ván\n"
            f"- Thắng: `{wins}` ván\n"
            f"- Winrate: `{winrate:.1f}%`\n"
            f"- Lợi nhuận: **{profit:+,} VND**\n"
            f"- Chuỗi thắng hiện tại: `{stats['streak']}` (Lớn nhất: `{stats['max_streak']}`)\n\n"
            f"💎 **Số lần thắng bài đặc biệt:**\n"
            f"- 9 Nút: `{stats['point_9_wins']}` lần\n"
            f"- Ba Tây: `{stats['batay_wins']}` lần\n"
            f"- Ba Cào: `{stats['bacao_wins']}` lần\n"
            f"- Ba Át: `{stats['baat_wins']}` lần\n\n"
            f"🎭 **Thống kê Tố Mù (Blind Bets):**\n"
            f"- Đã Tố Mù: `{stats['blind_plays']}` lần\n"
            f"- Tố Mù Thắng (Blind Wins): `{stats['blind_wins']}` lần\n"
            f"- Thắng Tố Mù lớn nhất: `{stats['max_blind_win_amount']:,} VND`\n\n"
            f"🏆 **Thành tựu đã mở khóa ({len(ach_unlocked)}/10):**\n"
        )
        
        ach_names = {
            "first_play": "🃏 Chơi lần đầu",
            "wins_10": "🥉 Thắng 10 ván",
            "wins_100": "🥈 Thắng 100 ván",
            "point_9_win": "🔥 Có 9 nút",
            "batay_win": "👑 Có Ba Tây",
            "bacao_win": "💎 Có Ba Cào",
            "baat_win": "🌟 Có Ba Át",
            "allin_win": "💰 All In thành công",
            "blind_win": "🎭 Tố mù thắng cuộc",
            "streak_5": "🔥 Thắng 5 ván liên tiếp"
        }
        
        if ach_unlocked:
            desc += "\n".join(f"✅ {ach_names.get(ach, ach)}" for ach in ach_unlocked)
        else:
            desc += "*Chưa có thành tựu nào được mở khóa.*"
            
        embed = discord.Embed(
            title=f"📊 THỐNG KÊ BÀI TỐ — {target.display_name}",
            description=desc,
            color=discord.Color.blue()
        )
        embed.set_thumbnail(url=target.display_avatar.url)
        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Baito(bot))
