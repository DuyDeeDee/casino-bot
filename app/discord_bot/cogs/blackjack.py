import asyncio
import logging
import random
from contextlib import suppress
from dataclasses import dataclass
from typing import Union
from uuid import uuid4

import discord
from discord.ext import commands

from app.config import config
from app.discord_bot.modules.betting import validate_money_bet
from app.discord_bot.modules.card import Card
from app.discord_bot.modules.card_table import render_card_table_bytes
from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import make_embed
from app.discord_bot.modules.wallet_logging import log_wallet_change

logger = logging.getLogger(__name__)


@dataclass
class PlayerHand:
    cards: list[Card]
    bet: int
    finished: bool = False
    surrendered: bool = False
    forfeited: bool = False
    split_aces: bool = False


class BlackjackActionView(discord.ui.View):
    def __init__(
        self,
        author: discord.User | discord.Member,
        emoji_to_action: dict[str, str],
        timeout: float = 60.0,
    ):
        super().__init__(timeout=timeout)
        self.author = author
        self.chosen_action: str | None = None

        # Map actions to button attributes: (style, label)
        action_styles = {
            "buy": (discord.ButtonStyle.success, "Mua bảo hiểm"),
            "skip": (discord.ButtonStyle.secondary, "Bỏ qua"),
            "hit": (discord.ButtonStyle.primary, "Rút bài"),
            "stand": (discord.ButtonStyle.danger, "Dừng bài"),
            "double": (discord.ButtonStyle.success, "Gấp đôi"),
            "split": (discord.ButtonStyle.primary, "Tách bài"),
            "surrender": (discord.ButtonStyle.secondary, "Đầu hàng"),
        }

        for emoji, action in emoji_to_action.items():
            style = discord.ButtonStyle.primary
            label = action.title()
            
            if action in action_styles:
                style, label = action_styles[action]

            button = discord.ui.Button(
                label=label,
                style=style,
                emoji=emoji,
                custom_id=f"bj_{action}_{uuid4().hex[:6]}",
            )
            button.callback = self.make_callback(action)
            self.add_item(button)

    def make_callback(self, action: str):
        async def callback(interaction: discord.Interaction):
            self.chosen_action = action
            self.stop()
            with suppress(discord.HTTPException):
                await interaction.response.defer()
        return callback

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if not interaction.user or interaction.user.id != self.author.id:
            await interaction.response.send_message(
                "Đây không phải là bàn chơi của bạn! Vui lòng tự tạo bàn chơi riêng nhé.",
                ephemeral=True,
            )
            return False
        return True


class Blackjack(commands.Cog):
    ACTION_EMOJIS = {
        "hit": "👆",
        "stand": "🛑",
        "double": "💵",
        "split": "✂️",
        "surrender": "🏳️",
    }
    MAX_PLAYER_HANDS = 4
    DEALER_HITS_SOFT_17 = False

    def __init__(self, client: commands.Bot):
        self.client = client
        self.economy = getattr(client, "economy", Economy())

    def check_bet(
        self,
        ctx: commands.Context,
        bet: int = config.bot.default_bet,
    ) -> int:
        _, current = validate_money_bet(self.economy, ctx.author.id, bet)
        return current

    @staticmethod
    def hand_value(hand: list[Card], include_down: bool = False) -> tuple[int, bool]:
        """Returns (total, soft) while accounting for aces."""
        total = 0
        aces = 0
        for card in hand:
            if card.down and not include_down:
                continue
            if card.symbol == "A":
                aces += 1
            elif card.symbol in "JQK":
                total += 10
            else:
                total += card.value

        total += aces
        soft = False
        if aces and total + 10 <= 21:
            total += 10
            soft = True

        return total, soft

    @classmethod
    def calc_hand(cls, hand: list[Card], include_down: bool = False) -> int:
        return cls.hand_value(hand, include_down=include_down)[0]

    @classmethod
    def is_blackjack(cls, hand: list[Card], include_down: bool = False) -> bool:
        visible_cards = sum(1 for card in hand if include_down or not card.down)
        return visible_cards == 2 and cls.calc_hand(hand, include_down=include_down) == 21

    @staticmethod
    def is_ten_value(card: Card) -> bool:
        return card.value == 10 or card.symbol in "JQK"

    @staticmethod
    def can_split(hand: PlayerHand) -> bool:
        return len(hand.cards) == 2 and hand.cards[0].value == hand.cards[1].value

    @staticmethod
    def format_delta(amount: int) -> str:
        if amount > 0:
            return f"+{amount:,} VND"
        if amount < 0:
            return f"-{abs(amount):,} VND"
        return "0 VND"

    @commands.command(
        aliases=["bj"],
        brief="Chơi blackjack (xì dách) với các luật casino phổ biến.\nTiền cược phải lớn hơn 0 VND",
        usage=f"blackjack [tiền_cược - mặc định={config.bot.default_bet:,} VND]",
    )
    @commands.max_concurrency(1, per=commands.BucketType.user, wait=False)
    async def blackjack(
        self,
        ctx: commands.Context,
        bet: int = config.bot.default_bet,
    ):
        bankroll = self.check_bet(ctx, bet)
        base_bet = int(bet)

        deck = [Card(suit, num) for num in range(2, 15) for suit in Card.suits]
        random.shuffle(deck)

        player_cards = [deck.pop()]
        dealer_hand: list[Card] = [deck.pop()]
        player_cards.append(deck.pop())

        dealer_hand.append(deck.pop().flip())

        player_hands: list[PlayerHand] = [PlayerHand(cards=player_cards, bet=base_bet)]

        table_filename = f"blackjack-{ctx.author.id}-{uuid4().hex}.png"

        total_exposure = base_bet
        insurance_bet = 0
        insurance_delta = 0
        timed_out = False

        def can_commit(extra: int) -> bool:
            return total_exposure + extra <= bankroll

        async def out_table(
            *,
            title: str,
            description: str,
            color: discord.Color | None = None,
            active_hand_index: int | None = None,
            view: discord.ui.View | None = None,
        ) -> discord.Message:
            table_buffer = await asyncio.to_thread(
                render_card_table_bytes,
                dealer_hand,
                [hand.cards for hand in player_hands],
                active_hand_index=active_hand_index,
            )
            try:
                embed = make_embed(title=title, description=description, color=color)
                file = discord.File(fp=table_buffer, filename=table_filename)
                embed.set_image(url=f"attachment://{table_filename}")
                msg: discord.Message = await ctx.send(file=file, embed=embed, view=view)
                return msg
            finally:
                table_buffer.close()

        async def prompt_action(
            *,
            title: str,
            description: str,
            emoji_to_action: dict[str, str],
            timeout: int = 60,
            active_hand_index: int | None = None,
        ) -> str | None:
            highlight_active_hand = active_hand_index is not None and len(player_hands) > 1
            
            view = BlackjackActionView(ctx.author, emoji_to_action, timeout=timeout)
            
            msg = await out_table(
                title=title,
                description=description,
                color=discord.Color.gold() if highlight_active_hand else None,
                active_hand_index=active_hand_index if highlight_active_hand else None,
                view=view,
            )

            try:
                is_timeout = await view.wait()
            except Exception:
                is_timeout = True

            with suppress(discord.HTTPException):
                await msg.delete()

            if is_timeout:
                return None

            return view.chosen_action

        try:
            dealer_upcard = dealer_hand[0]

            if dealer_upcard.symbol == "A":
                max_insurance = base_bet // 2
                if max_insurance > 0 and can_commit(max_insurance):
                    insurance_choice = await prompt_action(
                        title="Mua bảo hiểm?",
                        description=(
                            f"Nhà cái lật được lá A. Phí bảo hiểm là {max_insurance:,} VND.\n"
                            "Trả thưởng tỉ lệ 2:1 nếu nhà cái có blackjack."
                        ),
                        emoji_to_action={"✅": "buy", "❌": "skip"},
                        timeout=30,
                    )
                    if insurance_choice == "buy":
                        insurance_bet = max_insurance
                        total_exposure += insurance_bet

            dealer_checks_blackjack = dealer_upcard.symbol == "A" or self.is_ten_value(dealer_upcard)
            dealer_blackjack = (
                self.is_blackjack(dealer_hand, include_down=True) if dealer_checks_blackjack else False
            )
            player_blackjack = self.is_blackjack(player_hands[0].cards, include_down=True)

            if dealer_blackjack:
                if dealer_hand[1].down:
                    dealer_hand[1].flip()

                net_change = 0
                summary: list[str] = []

                if player_blackjack:
                    summary.append(f"Cược chính: hòa ({base_bet:,} VND)")
                else:
                    net_change -= base_bet
                    summary.append(f"Cược chính: nhà cái blackjack ({self.format_delta(-base_bet)})")

                if insurance_bet:
                    insurance_win = insurance_bet * 2
                    net_change += insurance_win
                    summary.append(f"Bảo hiểm: thắng ({self.format_delta(insurance_win)})")

                if net_change:
                    self.economy.add_money(ctx.author.id, net_change)
                    if net_change >= 1_000_000:
                        from app.discord_bot.modules.betting import reward_spouse_share
                        await reward_spouse_share(self.bot, ctx.author.id, net_change, ctx.channel)
                log_wallet_change(
                    logger,
                    event="blackjack_round_settlement",
                    user_id=ctx.author.id,
                    money_delta=net_change,
                    ctx=ctx,
                    result="dealer_blackjack",
                    base_bet=base_bet,
                    insurance_bet=insurance_bet,
                    hands=len(player_hands),
                )

                color = (
                    discord.Color.green()
                    if net_change > 0
                    else discord.Color.red()
                    if net_change < 0
                    else discord.Color.blue()
                )
                await out_table(
                    title="Nhà cái có Blackjack",
                    color=color,
                    description=(
                        f"**Lợi nhuận ròng: {self.format_delta(net_change)}**\n"
                        + "\n".join(summary)
                        + f"\nTổng điểm nhà cái: {self.calc_hand(dealer_hand, include_down=True)}"
                    ),
                )
                return

            if insurance_bet:
                insurance_delta = -insurance_bet

            if player_blackjack:
                if dealer_hand[1].down:
                    dealer_hand[1].flip()

                blackjack_win = int(base_bet * 1.5)
                net_change = blackjack_win + insurance_delta
                if net_change:
                    self.economy.add_money(ctx.author.id, net_change)
                    if net_change >= 1_000_000:
                        from app.discord_bot.modules.betting import reward_spouse_share
                        await reward_spouse_share(self.bot, ctx.author.id, net_change, ctx.channel)
                log_wallet_change(
                    logger,
                    event="blackjack_round_settlement",
                    user_id=ctx.author.id,
                    money_delta=net_change,
                    ctx=ctx,
                    result="player_blackjack",
                    base_bet=base_bet,
                    insurance_bet=insurance_bet,
                    hands=len(player_hands),
                )

                summary = [f"Blackjack trả thưởng 3:2 ({self.format_delta(blackjack_win)})"]
                if insurance_bet:
                    summary.append(f"Bảo hiểm: thua ({self.format_delta(insurance_delta)})")

                color = discord.Color.green() if net_change >= 0 else discord.Color.red()
                await out_table(
                    title="Blackjack!",
                    color=color,
                    description=(
                        f"**Lợi nhuận ròng: {self.format_delta(net_change)}**\n"
                        + "\n".join(summary)
                        + f"\nTổng điểm nhà cái: {self.calc_hand(dealer_hand, include_down=True)}"
                    ),
                )
                return

            active_hand_index = 0
            initial_action_pending = True

            while active_hand_index < len(player_hands):
                hand = player_hands[active_hand_index]

                if hand.finished:
                    active_hand_index += 1
                    continue

                hand_total = self.calc_hand(hand.cards)
                if hand_total >= 21:
                    hand.finished = True
                    active_hand_index += 1
                    continue

                actions = ["hit", "stand"]

                if len(hand.cards) == 2 and can_commit(hand.bet):
                    actions.append("double")

                if (
                    len(hand.cards) == 2
                    and len(player_hands) < self.MAX_PLAYER_HANDS
                    and self.can_split(hand)
                    and can_commit(hand.bet)
                    and not hand.split_aces
                ):
                    actions.append("split")

                if (
                    initial_action_pending
                    and active_hand_index == 0
                    and len(player_hands) == 1
                    and len(hand.cards) == 2
                ):
                    actions.append("surrender")

                emoji_to_action = {
                    self.ACTION_EMOJIS[action]: action
                    for action in actions
                }

                multiple_hands = len(player_hands) > 1
                lines = [f"**Nhà cái**: hiển thị `{self.calc_hand(dealer_hand)}`"]
                if multiple_hands:
                    lines.append(f"**Đang chơi**: Tụ **{active_hand_index + 1}**")
                lines.append("")
                lines.append("**Các tụ bài**")
                for i, current_hand in enumerate(player_hands):
                    current_total = self.calc_hand(current_hand.cards)
                    is_active = multiple_hands and i == active_hand_index and not current_hand.finished
                    marker = ">>" if is_active else "  "

                    if current_hand.surrendered:
                        status = "Đã đầu hàng"
                    elif current_hand.forfeited:
                        status = "Đã bỏ cuộc"
                    elif current_total > 21:
                        status = "Quắc"
                    elif current_hand.finished:
                        status = "Đã dằn"
                    elif is_active:
                        status = "Đang chơi"
                    elif multiple_hands:
                        status = "Đang chờ"
                    else:
                        status = "Đang chơi"

                    if current_hand.split_aces:
                        status += ", tách đôi Ace"

                    lines.append(
                        f"{marker} Tụ {i + 1}: tổng điểm `{current_total}` | cược `{current_hand.bet:,} VND` | {status}"
                    )

                lines.append("")
                lines.append("**Hãy chọn hành động của bạn bằng các nút bấm bên dưới:**")

                chosen_action = await prompt_action(
                    title="Đến lượt bạn",
                    description="\n".join(lines),
                    emoji_to_action=emoji_to_action,
                    active_hand_index=active_hand_index if len(player_hands) > 1 else None,
                )

                if chosen_action is None:
                    timed_out = True
                    for unresolved in player_hands[active_hand_index:]:
                        if not unresolved.finished and not unresolved.surrendered:
                            unresolved.forfeited = True
                            unresolved.finished = True
                    break

                if chosen_action == "hit":
                    initial_action_pending = False
                    hand.cards.append(deck.pop())
                    if self.calc_hand(hand.cards) >= 21:
                        hand.finished = True
                        active_hand_index += 1
                    continue

                if chosen_action == "stand":
                    initial_action_pending = False
                    hand.finished = True
                    active_hand_index += 1
                    continue

                if chosen_action == "double":
                    initial_action_pending = False
                    total_exposure += hand.bet
                    hand.bet *= 2
                    hand.cards.append(deck.pop())
                    hand.finished = True
                    active_hand_index += 1
                    continue

                if chosen_action == "split":
                    initial_action_pending = False
                    total_exposure += hand.bet

                    split_was_aces = hand.cards[0].symbol == "A" and hand.cards[1].symbol == "A"
                    moved_card = hand.cards.pop()
                    new_hand = PlayerHand(cards=[moved_card], bet=hand.bet)

                    hand.cards.append(deck.pop())
                    new_hand.cards.append(deck.pop())

                    if split_was_aces:
                        hand.split_aces = True
                        new_hand.split_aces = True
                        hand.finished = True
                        new_hand.finished = True
                    else:
                        if self.calc_hand(hand.cards) >= 21:
                            hand.finished = True
                        if self.calc_hand(new_hand.cards) >= 21:
                            new_hand.finished = True

                    player_hands.insert(active_hand_index + 1, new_hand)
                    if hand.finished:
                        active_hand_index += 1
                    continue

                if chosen_action == "surrender":
                    initial_action_pending = False
                    hand.surrendered = True
                    hand.finished = True
                    active_hand_index += 1
                    continue

            if dealer_hand[1].down:
                dealer_hand[1].flip()

            hands_requiring_dealer = [
                hand
                for hand in player_hands
                if (
                    not hand.surrendered
                    and not hand.forfeited
                    and self.calc_hand(hand.cards) <= 21
                )
            ]

            dealer_score, dealer_soft = self.hand_value(dealer_hand, include_down=True)
            if hands_requiring_dealer:
                while dealer_score < 17 or (
                    self.DEALER_HITS_SOFT_17 and dealer_score == 17 and dealer_soft
                ):
                    dealer_hand.append(deck.pop())
                    dealer_score, dealer_soft = self.hand_value(dealer_hand, include_down=True)

            net_change = insurance_delta
            result_lines: list[str] = []

            if insurance_bet:
                result_lines.append(f"Bảo hiểm: thua ({self.format_delta(insurance_delta)})")

            for i, hand in enumerate(player_hands):
                hand_total = self.calc_hand(hand.cards)

                if hand.forfeited:
                    delta = -hand.bet
                    outcome = "Bỏ cuộc (hết giờ)"
                elif hand.surrendered:
                    surrender_loss = (hand.bet + 1) // 2
                    delta = -surrender_loss
                    outcome = "Đầu hàng"
                elif hand_total > 21:
                    delta = -hand.bet
                    outcome = "Quắc"
                elif dealer_score > 21:
                    delta = hand.bet
                    outcome = "Thắng"
                elif hand_total > dealer_score:
                    delta = hand.bet
                    outcome = "Thắng"
                elif hand_total < dealer_score:
                    delta = -hand.bet
                    outcome = "Thua"
                else:
                    delta = 0
                    outcome = "Hòa"

                net_change += delta
                result_lines.append(
                    f"Tụ {i + 1}: {outcome} (tổng {hand_total}, {self.format_delta(delta)})"
                )

            if net_change:
                self.economy.add_money(ctx.author.id, net_change)
                if net_change >= 1_000_000:
                    from app.discord_bot.modules.betting import reward_spouse_share
                    await reward_spouse_share(self.bot, ctx.author.id, net_change, ctx.channel)
            log_wallet_change(
                logger,
                event="blackjack_round_settlement",
                user_id=ctx.author.id,
                money_delta=net_change,
                ctx=ctx,
                result="timed_out" if timed_out else "resolved",
                base_bet=base_bet,
                insurance_bet=insurance_bet,
                hands=len(player_hands),
                dealer_total=dealer_score,
            )

            if timed_out:
                title = "Hết giờ"
            elif net_change > 0:
                title = "Bạn đã thắng!"
            elif net_change < 0:
                title = "Bạn đã thua!"
            else:
                title = "Hòa"

            color = (
                discord.Color.red()
                if net_change < 0
                else discord.Color.green()
                if net_change > 0
                else discord.Color.blue()
            )

            await out_table(
                title=title,
                color=color,
                description=(
                    f"**Lợi nhuận ròng: {self.format_delta(net_change)}**\n"
                    f"Tổng điểm nhà cái: {dealer_score}\n"
                    + "\n".join(result_lines)
                ),
            )
        finally:
            pass


async def setup(client: commands.Bot):
    await client.add_cog(Blackjack(client))
