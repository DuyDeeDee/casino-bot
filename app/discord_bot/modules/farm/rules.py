"""Ilis Farm rules. Catalog prices and rewards use the original Farm unit."""

import json
from datetime import UTC, date, datetime
from math import floor
from pathlib import Path
from random import Random

with Path(__file__).with_name("catalog.json").open(encoding="utf-8") as source:
    CATALOG = json.load(source)

VND_PER_COIN = 10_000
START_COINS = 100
INVENTORY_CAPACITY = 200
CROPS = CATALOG["CROPS"]
SHOP = CATALOG["SHOP_ITEMS"]
SHOP_IDS = CATALOG["SHOP_ID_MAP"]
QUALITIES = CATALOG["QUALITY_RATES"]
PETS = {entry["id"].lower(): entry for entry in CATALOG["GACHA_POOL"] if entry["type"] == "pet"}
NORMAL_GACHA = tuple(
    entry for entry in CATALOG["GACHA_POOL"]
    if entry["rate"] > 0 and not entry.get("isMythic") and not entry.get("isHidden")
)
FISH = CATALOG["FISH_TYPES"]
JUNK = CATALOG["JUNK_ITEMS"]
RODS = CATALOG["ROD_INFO"]
QUESTS = CATALOG["QUESTS"]
ACHIEVEMENTS = CATALOG["ACHIEVEMENTS"]
PET_MULTIPLIERS = ("xpBonus", "coinBonus", "yieldBonus", "fishingXpBonus", "fishingCoinBonus")
PET_CAPS = {
    "doubleHarvestChance": 0.80,
    "fishingRareBonus": 0.80,
    "hungerDecayReduction": 0.70,
    "happinessDecayReduction": 0.70,
    "exerciseHpReduction": 0.80,
}
QUALITY_NAMES = dict(zip(QUALITIES, ("Thường", "Khá", "Hiếm", "Sử thi", "Huyền thoại")))


def vnd(coins: int) -> int:
    return coins * VND_PER_COIN


def round_reward(value: float) -> int:
    return floor(value + 0.5)


def item_id(value: str) -> str:
    value = value.lower().lstrip("#")
    return SHOP_IDS.get(value, value)


def day_at(now: float) -> date:
    return datetime.fromtimestamp(now, UTC).date()


def season_at(day: date) -> tuple[dict, int]:
    days = (day - date(2025, 1, 6)).days
    return CATALOG["SEASONS"][(days // 14) % 4], 14 - days % 14


def event_at(day: date) -> dict:
    events = CATALOG["EVENT_POOL"]
    return events[sum(map(ord, day.isoformat())) % len(events)]


def daily_quests(user_id: int, day: date) -> dict[str, int]:
    rng = Random(f"{user_id}:{day.isoformat()}")
    return {
        rng.choice([key for key, rule in QUESTS.items() if rule["diff"] == difficulty]): 0
        for difficulty in ("easy", "medium", "hard")
    }


def xp_required(level: int, evolutions: int) -> int:
    for ceiling, xp in ((10, 100), (25, 250), (40, 500), (50, 1000), (70, 1500)):
        if level <= ceiling:
            return xp * 10**evolutions
    raise ValueError("Farm level out of range")


def pet_bonus(pet_id: str, pet: dict) -> dict:
    definition = PETS[pet_id]["id"]
    base = CATALOG["PET_BASE_BONUSES"].get(definition, {})
    level_scale = 1 + (pet["level"] - 1) / 9
    bonus = {key: 1 + (base.get(key, 1) - 1) * level_scale for key in PET_MULTIPLIERS}
    for key, value in base.items():
        if key not in bonus:
            bonus[key] = value if key == "hungerDecayBoost" else min(PET_CAPS.get(key, value * level_scale), value * level_scale)
    for change in CATALOG["CONSTELLATION_BONUSES"].get(definition, [])[:pet["stars"]]:
        key, delta = change["key"], change["delta"]
        if key in PET_MULTIPLIERS:
            bonus[key] += delta * level_scale
        elif key == "_sc4":
            bonus["coinBonus"] *= 1 + delta
        elif key == "_sc6":
            bonus["doubleHarvestChance"] = min(0.80, bonus.get("doubleHarvestChance", 0) + delta)
        elif key in ("_hr4", "_hr6"):
            bonus["flatXpBonus" if key == "_hr4" else "bonusHarvestYield"] = delta
        elif key == "_tt3":
            for stat in PET_MULTIPLIERS:
                bonus[stat] = 1 + (bonus[stat] - 1) * (1 + delta)
        elif not key.startswith("_"):
            value = bonus.get(key, 0) + delta * level_scale
            bonus[key] = min(PET_CAPS.get(key, value), value)
    return bonus


def update_pet(pet: dict, bonus: dict, now: float) -> None:
    hours = max(0, now - pet["updated"]) / 3600
    hunger = pet["hunger"]
    hunger_rate = 7 * (1 - bonus.get("hungerDecayReduction", 0)) * bonus.get("hungerDecayBoost", 1)
    happy_rate = 10.5 * (1 - bonus.get("happinessDecayReduction", 0))
    pet["hunger"] = max(0, hunger - hunger_rate * hours)
    pet["happiness"] = max(0, pet["happiness"] - happy_rate * hours)
    fed_hours = min(hours, max(0, (hunger - 70) / hunger_rate))
    hungry_hours = max(0, hours - hunger / hunger_rate)
    pet["health"] = max(0, min(100, pet["health"] + 5 * fed_hours) - 2 * hungry_hours)
    pet["updated"] = now


def active_pet_bonus(pets: dict, active: str | None, now: float) -> dict:
    if not active:
        return {}
    pet = pets[active]
    bonus = pet_bonus(active, pet)
    update_pet(pet, bonus, now)
    partner = {"satou": "shio", "shio": "satou"}.get(active)
    if partner in pets:
        synergy = pet_bonus(partner, pets[partner])
        for key in PET_MULTIPLIERS:
            bonus[key] *= 1 + (synergy[key] - 1) * 0.30
        for key in ("rareChanceBonus", "doubleHarvestChance", "fishingRareBonus"):
            bonus[key] = bonus.get(key, 0) + synergy.get(key, 0) * 0.30
    health = pet["health"]
    scale = 1 if health > 70 else 0.7 if health > 50 else 0.5 if health > 30 else 0.3 if health > 0 else 0
    for key in PET_MULTIPLIERS:
        bonus[key] = 1 + (bonus[key] - 1) * scale
    for key in ("rareChanceBonus", "doubleHarvestChance", "fishingWeightBonus", "fishingRareBonus"):
        bonus[key] = bonus.get(key, 0) * scale
    bonus["flatXpBonus"] = round_reward(bonus.get("flatXpBonus", 0) * scale)
    bonus["bonusHarvestYield"] = floor(bonus.get("bonusHarvestYield", 0) * scale)
    return bonus
