import discord
from discord.ext import commands

from app.discord_bot.modules.economy import Economy
from app.discord_bot.modules.helpers import (
    EMOJI_VND,
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


from decimal import Decimal, InvalidOperation


def parse_bet_amount(val_str: str | int | float, current_money: int) -> int:
    if isinstance(val_str, (int, float)):
        if isinstance(val_str, float) and (val_str != val_str or val_str == float("inf") or val_str == float("-inf")):
            return 0
        return max(0, int(val_str))

    if not val_str:
        return 0

    val_str = str(val_str).strip().lower()
    if val_str in ["all", "allin", "all-in", "tất tay", "tat tay", "tattay"]:
        return max(0, get_capped_all_in_amount(current_money))

    # Remove any extra internal spaces
    val_str = val_str.replace(" ", "")

    # Multipliers
    multiplier = Decimal(1)
    suffix_found = False

    if val_str.endswith(("b", "tỷ", "ty")):
        multiplier = Decimal(1_000_000_000)
        for s in ("tỷ", "ty", "b"):
            if val_str.endswith(s):
                val_str = val_str[:-len(s)].strip()
                break
        suffix_found = True
    elif val_str.endswith(("m", "tr", "triệu", "trieu")):
        multiplier = Decimal(1_000_000)
        for s in ("triệu", "trieu", "tr", "m"):
            if val_str.endswith(s):
                val_str = val_str[:-len(s)].strip()
                break
        suffix_found = True
    elif val_str.endswith(("k", "nghìn", "nghin")):
        multiplier = Decimal(1_000)
        for s in ("nghìn", "nghin", "k"):
            if val_str.endswith(s):
                val_str = val_str[:-len(s)].strip()
                break
        suffix_found = True

    if suffix_found:
        # Suffix present: comma is likely a decimal separator (e.g. 1,5m -> 1.5m)
        val_str = val_str.replace(",", ".")
    else:
        # No suffix: handle thousand separators and decimal points
        if "," in val_str and "." in val_str:
            if val_str.rfind(",") > val_str.rfind("."):
                # 1.000,50 -> 1000.50
                val_str = val_str.replace(".", "").replace(",", ".")
            else:
                # 1,000.50 -> 1000.50
                val_str = val_str.replace(",", "")
        elif "," in val_str:
            parts = val_str.split(",")
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                # 1,000,000 -> 1000000
                val_str = "".join(parts)
            elif len(parts) == 2 and len(parts[1]) != 3:
                # 1,5 -> 1.5
                val_str = f"{parts[0]}.{parts[1]}"
            else:
                val_str = val_str.replace(",", "")
        elif "." in val_str:
            parts = val_str.split(".")
            if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
                # 1.000.000 -> 1000000
                val_str = "".join(parts)
            elif len(parts) == 2 and len(parts[1]) != 3:
                # 1.5 -> 1.5
                val_str = f"{parts[0]}.{parts[1]}"
            else:
                val_str = val_str.replace(".", "")

    try:
        dec = Decimal(val_str)
        if dec.is_nan() or dec.is_infinite():
            return 0
        return max(0, int(dec * multiplier))
    except (InvalidOperation, ValueError, TypeError):
        return 0


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
                raise BetLimitViolationException(f"Tiền cược tối thiểu được cấu hình là {min_val:,} {EMOJI_VND}.")
        except ValueError:
            pass

    global_max = economy.get_setting("global_max_bet")
    if global_max:
        try:
            max_val = int(global_max)
            if parsed_bet > max_val:
                from app.discord_bot.modules.helpers import BetLimitViolationException
                raise BetLimitViolationException(f"Tiền cược tối đa được cấu hình là {max_val:,} {EMOJI_VND}.")
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
        marriages = eco.get_marriages(user_id)
        if not marriages:
            return
            
        bonus = int(win_amount * 0.02)
        if bonus <= 0:
            return
            
        for marriage in marriages:
            user_one, user_two, ring_type, love_points, joint_wallet, married_at, _, _ = marriage
            spouse_id = user_two if user_id == user_one else user_one
            eco.add_money(spouse_id, bonus)
            # Send notification message if needed, wait, the original doesn't send message here, it just adds money

        
        # Send celebratory message
        embed = discord.Embed(
            title="💖 CHIA SẺ PHẦN THƯỞNG PHU THÊ 💖",
            description=(
                f"🎉 Người bạn đời của bạn là <@{user_id}> vừa thắng lớn `{win_amount:,}` {EMOJI_VND}!\n"
                f"🎁 Bạn nhận được **2% tiền chia vui** ngọt ngào: `+{bonus:,}` {EMOJI_VND} vào ví của mình!"
            ),
            color=discord.Color.magenta()
        )
        if channel:
            await channel.send(content=f"<@{spouse_id}>", embed=embed)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(f"Error in reward_spouse_share: {e}")

