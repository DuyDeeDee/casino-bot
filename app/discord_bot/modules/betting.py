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
