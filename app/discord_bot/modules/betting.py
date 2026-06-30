import discord
from discord.ext import commands

from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import (
    InsufficientCreditsException,
    InsufficientFundsException,
)


def validate_positive_amount(amount: int) -> int:
    try:
        parsed = int(amount)
    except (TypeError, ValueError):
        raise commands.errors.BadArgument()
    if parsed <= 0:
        raise commands.errors.BadArgument()
    return parsed


def get_capped_all_in_amount(current_money: int) -> int:
    try:
        from app.discord_bot.modules.economy import Economy
        eco = Economy()
        global_max_str = eco.get_setting("global_max_bet")
        if global_max_str:
            max_val = int(global_max_str)
            return min(current_money, max_val)
    except Exception:
        pass
    return current_money


def validate_money_bet(
    economy: Economy,
    user_id: int,
    bet: int,
    *,
    max_bet: int | None = None,
) -> tuple[int, int]:
    parsed_bet = validate_positive_amount(bet)
    
    # Check global limits
    global_min = economy.get_setting("global_min_bet")
    if global_min:
        try:
            min_val = int(global_min)
            if parsed_bet < min_val:
                from app.discord_bot.modules.helpers import BetLimitViolationException
                raise BetLimitViolationException(f"Tiền cược tối thiểu được cấu hình là {min_val:,} VND.")
        except ValueError:
            pass

    global_max = economy.get_setting("global_max_bet")
    if global_max:
        try:
            max_val = int(global_max)
            if parsed_bet > max_val:
                from app.discord_bot.modules.helpers import BetLimitViolationException
                raise BetLimitViolationException(f"Tiền cược tối đa được cấu hình là {max_val:,} VND.")
        except ValueError:
            pass

    if max_bet is not None and parsed_bet > max_bet:
        raise commands.errors.BadArgument()

    current_money = economy.get_entry(user_id)[1]
    if parsed_bet > current_money:
        raise InsufficientFundsException(current_money, parsed_bet)

    return parsed_bet, current_money


def validate_credits_bet(
    economy: Economy,
    user_id: int,
    bet: int,
    *,
    max_bet: int | None = None,
) -> tuple[int, int]:
    parsed_bet = validate_positive_amount(bet)
    if max_bet is not None and parsed_bet > max_bet:
        raise commands.errors.BadArgument()

    current_credits = economy.get_entry(user_id)[2]
    if parsed_bet > current_credits:
        raise InsufficientCreditsException(current_credits, parsed_bet)

    return parsed_bet, current_credits


def validate_money_available(
    economy: Economy,
    user_id: int,
    amount: int,
) -> tuple[int, int]:
    parsed_amount = validate_positive_amount(amount)
    current_money = economy.get_entry(user_id)[1]
    if parsed_amount > current_money:
        raise InsufficientFundsException(current_money, parsed_amount)
    return parsed_amount, current_money


def validate_credits_available(
    economy: Economy,
    user_id: int,
    amount: int,
) -> tuple[int, int]:
    parsed_amount = validate_positive_amount(amount)
    current_credits = economy.get_entry(user_id)[2]
    if parsed_amount > current_credits:
        raise InsufficientCreditsException(current_credits, parsed_amount)
    return parsed_amount, current_credits


async def reward_spouse_share(bot, user_id: int, win_amount: int, channel) -> None:
    """If user is married and wins >= 1M VND in a casino game, reward the spouse with 2% bonus."""
    if win_amount < 1_000_000:
        return
        
    try:
        eco = Economy()
        marriage = eco.get_marriage(user_id)
        if not marriage:
            return
            
        user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
        spouse_id = user_two if user_id == user_one else user_one
        
        # Calculate 2% bonus
        bonus = int(win_amount * 0.02)
        if bonus <= 0:
            return
            
        eco.add_money(spouse_id, bonus)
        
        # Send celebratory message
        embed = discord.Embed(
            title="💖 CHIA SẺ PHẦN THƯỞNG PHU THÊ 💖",
            description=(
                f"🎉 Người bạn đời của bạn là <@{user_id}> vừa thắng lớn `{win_amount:,} VND`!\n"
                f"🎁 Bạn nhận được **2% tiền chia vui** ngọt ngào: `+{bonus:,} VND` vào ví của mình!"
            ),
            color=discord.Color.magenta()
        )
        if channel:
            await channel.send(content=f"<@{spouse_id}>", embed=embed)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error in reward_spouse_share: {e}")

