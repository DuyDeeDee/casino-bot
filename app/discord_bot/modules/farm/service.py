"""Persistent Farm actions using the Casino economy connection."""

import json
import random
import time
from contextlib import contextmanager
from datetime import date, timedelta
from math import ceil

from .rules import (
    ACHIEVEMENTS, CATALOG, CROPS, FISH, INVENTORY_CAPACITY, JUNK, NORMAL_GACHA,
    PETS, QUALITIES, QUESTS, RODS, SHOP, START_COINS, active_pet_bonus, daily_quests,
    day_at, event_at, item_id, pet_bonus, round_reward, season_at, update_pet, vnd,
    xp_required,
)


class FarmError(ValueError):
    """An action the player can correct."""


def new_player(ticket_day: str) -> dict:
    return {
        "level": 1, "xp": 0, "gems": 0, "evolutions": 0, "last_level_reward": 1,
        "daily": "", "streak": 0, "tickets": 0, "ticket_day": ticket_day,
        "pity": 0, "limited": False,
        "inventory": {}, "plots": {}, "pets": {}, "active_pet": None,
        "fish": {}, "next_fish": 1, "last_fish": 0, "rod": None,
        "quest_day": "", "quests": {}, "achievements": [],
        "planted": 0, "harvested": 0, "sold": 0, "earned": 0, "pulls": 0,
        "tea_fed": 0,
        "visits_day": "", "watered_friends": [], "robbed_friends": [],
    }


def plot_limit(level: int) -> int:
    return max(
        value["maxPlots"] for threshold, value in CATALOG["FARM_EXPANSION"].items()
        if level >= int(threshold)
    )


class FarmStore:
    def __init__(self, economy):
        self.economy = economy

    def get(self, user_id: int, *, now: float | None = None) -> dict:
        row = self.economy.conn.execute(
            "SELECT state FROM farm_players WHERE user_id = ?", (user_id,)
        ).fetchone()
        if row is None:
            raise FarmError("Bạn chưa có nông trại. Dùng lệnh `farm start` để bắt đầu.")
        state = json.loads(row[0])
        today = day_at(time.time() if now is None else now)
        previous = date.fromisoformat(state["ticket_day"])
        if today > previous:
            state["tickets"] += (today - previous).days
            state["ticket_day"] = today.isoformat()
        return state

    def start(self, user_id: int) -> int:
        now = time.time()
        state = new_player(day_at(now).isoformat())
        with self.economy.transaction():
            inserted = self.economy.conn.execute(
                "INSERT OR IGNORE INTO farm_players (user_id, state) VALUES (?, ?)",
                (user_id, json.dumps(state, separators=(",", ":"))),
            )
            if inserted.rowcount == 0:
                raise FarmError("Bạn đã có nông trại.")
            session = FarmSession(self.economy, user_id, state, "start", now)
            return session.wallet(START_COINS)

    def _save(self, user_id: int, state: dict) -> None:
        self.economy.conn.execute(
            "UPDATE farm_players SET state = ? WHERE user_id = ?",
            (json.dumps(state, separators=(",", ":")), user_id),
        )

    @contextmanager
    def action(self, user_id: int, command: str, *, now: float | None = None):
        now = time.time() if now is None else now
        with self.economy.transaction():
            # Acquire the SQLite write lock before reading state or the wallet.
            self.economy.conn.execute(
                "UPDATE farm_players SET state = state WHERE user_id = ?", (user_id,)
            )
            state = self.get(user_id, now=now)
            session = FarmSession(self.economy, user_id, state, command, now)
            yield session
            session.check_achievements()
            self._save(user_id, state)

    def leaderboard(self, metric: str) -> list[tuple[int, int]]:
        if metric not in {"level", "harvested", "earned"}:
            raise FarmError("Chọn bảng `level`, `harvested` hoặc `earned`.")
        return self.economy.conn.execute(
            """SELECT user_id, json_extract(state, ?) AS score
               FROM farm_players ORDER BY score DESC, user_id LIMIT 10""",
            (f"$.{metric}",),
        ).fetchall()

    def visit(self, user_id: int, target_id: int, activity: str) -> str:
        if user_id == target_id or activity not in {"water", "rob"}:
            raise FarmError("Chọn nông trại người khác và thao tác `water` hoặc `rob`.")
        with self.action(user_id, "friend") as session:
            state = session.state
            day = session.day.isoformat()
            if state["visits_day"] != day:
                state.update(visits_day=day, watered_friends=[], robbed_friends=[])
            history = state["watered_friends"] if activity == "water" else state["robbed_friends"]
            visited = set(state["watered_friends"]) | set(state["robbed_friends"])
            if target_id in history:
                raise FarmError("Bạn đã dùng thao tác này trên nông trại đó hôm nay.")
            if len(visited) >= 3 and target_id not in visited:
                raise FarmError("Mỗi ngày chỉ được tương tác với nông trại của 3 người.")
            try:
                target = self.get(target_id, now=session.now)
            except FarmError as error:
                raise FarmError("Người này chưa có nông trại.") from error
            plots = target["plots"]
            if activity == "water":
                growing = [plot for plot in plots.values() if plot["ready"] > session.now]
                if not growing:
                    raise FarmError("Nông trại này hiện không có cây đang lớn.")
                for plot in growing:
                    plot["ready"] -= (plot["ready"] - session.now) * 0.10
                result = f"Đã tưới giúp **{len(growing)} ô**, giảm 10% thời gian còn lại."
            else:
                ready = [key for key, plot in plots.items() if plot["ready"] <= session.now]
                if not ready:
                    raise FarmError("Nông trại này hiện không có cây đã chín.")
                crop = plots.pop(random.choice(ready))["crop"]
                session.change_item("crop", f"{crop}_common", 1)
                result = f"Đã lấy **1 {CROPS[crop]['name']}** và đưa vào kho."
            history.append(target_id)
            self._save(target_id, target)
            return result


class FarmSession:
    def __init__(self, economy, user_id: int, state: dict, command: str, now: float):
        self.economy = economy
        self.user_id = user_id
        self.state = state
        self.command = command
        self.now = now
        self.day = day_at(now)
        self.event = event_at(self.day)
        self.season = season_at(self.day)[0]
        self.wallet_delta = 0
        self.unlocked = []

    def wallet(self, coins: int) -> int:
        delta = vnd(coins)
        if delta == 0:
            return 0
        balance = self.economy.adjust_wallet_money(
            self.user_id, delta, event="farm", command=f"farm {self.command}"
        )
        if balance is None:
            if delta < 0:
                raise FarmError(f"Ví Casino cần có ít nhất **{-delta:,} VND**.")
            raise FarmError("Ví Casino đã đạt giới hạn số dư.")
        self.wallet_delta += delta
        return balance

    def earn(self, coins: int) -> None:
        self.wallet(coins)
        self.state["earned"] += coins

    def xp(self, amount: int) -> None:
        self.state["xp"] += amount
        cap = 70 if self.state["evolutions"] else 50
        while self.state["level"] < cap:
            required = xp_required(self.state["level"], self.state["evolutions"])
            if self.state["xp"] < required:
                break
            self.state["xp"] -= required
            self.state["level"] += 1

    def change_item(self, category: str, key: str, delta: int) -> None:
        inventory = self.state["inventory"]
        entry = f"{category}:{key}"
        quantity = inventory.get(entry, 0) + delta
        if quantity < 0:
            raise FarmError("Bạn không có đủ vật phẩm trong kho.")
        if delta > 0 and sum(inventory.values()) + delta > INVENTORY_CAPACITY:
            raise FarmError(f"Kho đồ đã đầy ({INVENTORY_CAPACITY} vật phẩm).")
        if quantity:
            inventory[entry] = quantity
        else:
            inventory.pop(entry, None)

    def quest_progress(self, kind: str, amount: int) -> None:
        day = self.day.isoformat()
        if self.state["quest_day"] != day:
            self.state["quest_day"] = day
            self.state["quests"] = daily_quests(self.user_id, self.day)
        tasks = self.state["quests"]
        completed = False
        for quest, progress in tasks.items():
            rule = QUESTS[quest]
            if rule["type"] != kind or progress >= rule["target"]:
                continue
            tasks[quest] = min(rule["target"], progress + amount)
            if tasks[quest] == rule["target"]:
                self.earn(rule["coin"])
                self.xp(rule["xp"])
                completed = True
        if completed and all(progress == QUESTS[key]["target"] for key, progress in tasks.items()):
            self.state["tickets"] += 1

    def award(self, key: str) -> None:
        if key not in self.state["achievements"]:
            self.wallet(ACHIEVEMENTS[key]["reward"])
            self.state["achievements"].append(key)
            self.unlocked.append(ACHIEVEMENTS[key]["name"])

    def check_achievements(self) -> None:
        for stat, milestones in (
            ("planted", ((1, "first_plant"),)),
            ("harvested", ((1, "first_harvest"), (100, "harvest_100"), (1000, "harvest_1000"))),
            ("sold", ((50, "sell_50"), (200, "sell_200"))),
            ("earned", ((1000, "rich_1k"), (10_000, "rich_10k"), (100_000, "rich_100k"), (1_000_000, "rich_1m"))),
            ("streak", ((7, "streak_7"), (30, "streak_30"), (90, "streak_90"))),
            ("level", ((10, "reach_level_10"), (25, "reach_level_25"), (50, "reach_level_50"))),
            ("pulls", ((1, "first_gacha"),)),
        ):
            for threshold, key in milestones:
                if self.state[stat] >= threshold:
                    self.award(key)
        if self.state["pets"]:
            self.award("first_pet")

    def daily(self) -> tuple[int, int]:
        today = self.day.isoformat()
        if self.state["daily"] == today:
            raise FarmError("Bạn đã điểm danh. Quà mới mở lúc 07:00 giờ Việt Nam.")
        yesterday = (self.day - timedelta(days=1)).isoformat()
        streak = self.state["streak"] + 1 if self.state["daily"] == yesterday else 1
        reward = random.randint(200, 500) + {7: 1000, 14: 2000, 30: 5000, 60: 10_000, 90: 20_000}.get(streak, 0)
        self.state.update(daily=today, streak=streak, tickets=self.state["tickets"] + 1)
        self.earn(reward)
        return reward, streak

    def buy(self, key: str, quantity: int) -> tuple[str, int]:
        key = item_id(key)
        item = SHOP.get(key)
        if item is None or not 1 <= quantity <= INVENTORY_CAPACITY:
            raise FarmError("Chọn mã hàng hợp lệ và số lượng từ 1 đến 200.")
        cost = item["coin"] * quantity
        if item["category"] == "pets":
            if quantity != 1 or item["petId"].lower() in self.state["pets"]:
                raise FarmError("Chỉ mua một pet mỗi lần và mỗi loài chỉ được mua một lần.")
            self.wallet(-cost)
            self.add_pet(item["petId"].lower())
        else:
            category = "seed" if item["category"] == "seeds" else item["category"]
            self.wallet(-cost)
            self.change_item(category, key, quantity)
        return item["name"], cost

    def plant(self, key: str, quantity: int) -> tuple[str, float, int]:
        key = item_id(key)
        crop = CROPS.get(key)
        if crop is None or quantity < 1:
            raise FarmError("Chọn mã cây hợp lệ và số lượng lớn hơn 0.")
        plots = self.state["plots"]
        free = [str(index) for index in range(1, plot_limit(self.state["level"]) + 1) if str(index) not in plots]
        if quantity > len(free):
            raise FarmError(f"Nông trại còn **{len(free)} ô trống**.")
        seeds = min(quantity, self.state["inventory"].get(f"seed:{key}", 0))
        cost = (quantity - seeds) * crop["seedCost"]
        if seeds:
            self.change_item("seed", key, -seeds)
        self.wallet(-cost)
        grow_factor = max(0.1, 1 - 0.1 * self.state["evolutions"])
        ready = self.now + crop["growTime"] * self.event.get("growBonus", 1) * grow_factor
        for index in free[:quantity]:
            plots[index] = {"crop": key, "ready": ready, "watered": None, "fertilized": ""}
        self.state["planted"] += quantity
        self.xp(2 * quantity)
        self.quest_progress("plant", quantity)
        return crop["name"], ready, cost

    def tend(self, fertilizer: str | None = None) -> tuple[int, int]:
        today = self.day.isoformat()
        if fertilizer:
            fertilizer = item_id(fertilizer).removesuffix("_fertilizer")
            reduction = CATALOG["FERTILIZER_TIME_REDUCTION"].get(fertilizer)
            if reduction is None:
                raise FarmError("Chọn loại phân `normal`, `premium` hoặc `superior`.")
        else:
            reduction = 0.1
        count = 0
        for plot in self.state["plots"].values():
            if plot["ready"] <= self.now:
                continue
            if fertilizer:
                if plot["fertilized"] == today:
                    continue
                plot["fertilized"] = today
            else:
                if plot["watered"] is not None and self.now - plot["watered"] < 36_000:
                    continue
                plot["watered"] = self.now
            plot["ready"] -= (plot["ready"] - self.now) * reduction
            count += 1
        if not count:
            raise FarmError("Hiện chưa có ô đất nào đủ điều kiện chăm sóc.")
        if fertilizer:
            self.change_item("fertilizer", f"{fertilizer}_fertilizer", -1)
        return count, round_reward(reduction * 100)

    def harvest(self, selection: str) -> tuple[dict[str, int], int]:
        plots = self.state["plots"]
        ready = [
            key for key, plot in plots.items()
            if self.now >= plot["ready"] and selection in ("all", key)
        ]
        if not ready:
            raise FarmError("Ô đã chọn chưa có cây nào sẵn sàng thu hoạch.")
        pet = active_pet_bonus(self.state["pets"], self.state["active_pet"], self.now)
        quality_bonus = self.event.get("qualityBonus", 1) * (1 + pet.get("rareChanceBonus", 0))
        tiers = tuple(QUALITIES)
        rates = [rule["rate"] for rule in QUALITIES.values()]
        harvested, xp = {}, 0
        for position in ready:
            key = plots[position]["crop"]
            tier = random.choices(range(len(tiers)), rates)[0]
            if tier < len(tiers) - 1 and quality_bonus > 1 and random.random() < min(0.5, quality_bonus - 1):
                tier += 1
            quality = tiers[tier]
            quantity = 1 + (random.random() < pet.get("doubleHarvestChance", 0)) + pet.get("bonusHarvestYield", 0)
            crop = CROPS[key]
            xp += round_reward(
                crop["xp"] * 1.5 * self.event.get("xpBonus", 1)
                * pet.get("xpBonus", 1) * QUALITIES[quality]["multiplier"]
            ) + pet.get("flatXpBonus", 0)
            entry = f"{key}_{quality}"
            self.change_item("crop", entry, quantity)
            harvested[entry] = harvested.get(entry, 0) + quantity
            del plots[position]
            if quality == "legendary":
                self.award("legendary_crop")
        count = sum(harvested.values())
        self.state["harvested"] += count
        self.xp(xp)
        self.quest_progress("harvest", count)
        return harvested, xp

    def sale(self, coins: int, quantity: int) -> None:
        self.earn(coins)
        self.state["sold"] += quantity
        self.quest_progress("sell", quantity)
        self.quest_progress("earn_coin", coins)

    def sell(self, selection: str, quantity: int) -> tuple[int, int]:
        selection = item_id(selection)
        if selection != "all" and (selection not in CROPS or quantity < 1):
            raise FarmError("Chọn mã nông sản hợp lệ hoặc dùng `farm sell all`.")
        stacks = []
        for entry, stock in self.state["inventory"].items():
            category, key = entry.split(":", 1)
            if category != "crop":
                continue
            crop, _, quality = key.rpartition("_")
            if crop in CROPS and selection in (crop, "all"):
                stacks.append((crop, quality, key, stock))
        available = sum(stack[3] for stack in stacks)
        target = available if selection == "all" else quantity
        if not available or target > available:
            raise FarmError(f"Kho chỉ có **{available}** vật phẩm phù hợp.")
        stacks.sort(key=lambda stack: tuple(QUALITIES).index(stack[1]))
        total, remaining = 0, target
        multiplier = self.event.get("sellBonus", 1) * self.event.get("coinBonus", 1)
        for crop, quality, key, stock in stacks:
            count = min(stock, remaining)
            seasonal = self.season.get("globalSellBonus", 1)
            if crop in self.season["bonusCrops"]:
                seasonal *= self.season["multiplier"]
            price = (CROPS[crop]["sellValue"] * QUALITIES[quality]["multiplier"]
                     * seasonal * (1 + 0.2 * self.state["evolutions"]))
            total += count * round_reward(price * multiplier)
            self.change_item("crop", key, -count)
            remaining -= count
            if not remaining:
                break
        self.sale(total, target)
        return target, total

    def discard_junk(self, key: str, quantity: int) -> None:
        if key not in JUNK or quantity < 1:
            raise FarmError("Chọn mã rác trong kho và số lượng lớn hơn 0.")
        self.change_item("junk", key, -quantity)

    def equip(self, key: str) -> str:
        key = item_id(key)
        if key not in RODS or not self.state["inventory"].get(f"fishing:{key}"):
            raise FarmError("Bạn chưa có cần câu này.")
        self.state["rod"] = key
        return RODS[key]["name"]

    def fishing(self, key: str | None) -> tuple[str, int, str]:
        remaining = self.state["last_fish"] + 6 - self.now
        if remaining > 0:
            raise FarmError(f"Chờ **{ceil(remaining)} giây** để câu tiếp.")
        inventory = self.state["inventory"]
        key = item_id(key) if key else self.state["rod"]
        if not key:
            key = next((rod for rod in RODS if inventory.get(f"fishing:{rod}")), None)
        if key not in RODS or not inventory.get(f"fishing:{key}"):
            raise FarmError("Bạn cần mua cần câu #260, #261 hoặc #262 từ shop Farm.")
        self.wallet(-100)
        rod = RODS[key]
        pet = active_pet_bonus(self.state["pets"], self.state["active_pet"], self.now)
        pools = (FISH, JUNK, CATALOG["BONUS_ITEMS"])
        pool = random.choices(pools, [sum(item["rate"] for item in pool.values()) for pool in pools])[0]
        if pool is FISH:
            rarity_bonus = rod["rareChanceBonus"] + pet.get("fishingRareBonus", 0)
            fish_key = random.choices(
                tuple(FISH), [fish["rate"] + rarity_bonus * fish["rareChanceBonus"] for fish in FISH.values()]
            )[0]
            fish = FISH[fish_key]
            base_weight = max(1, min(100, round_reward(random.gauss(40, 15))))
            weight = max(1, min(100, round_reward(base_weight + rod["weightBonus"] + pet.get("fishingWeightBonus", 0))))
            price = round_reward(
                fish["basePrice"] * (1 + (weight - 40) * 0.02) * 0.7
                * self.event.get("coinBonus", 1) * self.season.get("globalSellBonus", 1)
                * pet.get("fishingCoinBonus", 1)
            )
            fish_id = str(self.state["next_fish"])
            self.state["next_fish"] += 1
            self.state["fish"][fish_id] = {"type": fish_key, "weight": weight, "price": price}
            result = f"{fish['name']} **#{fish_id}**, {weight} kg • giá gốc {vnd(price):,} VND"
            xp = fish["xp"]
            icon = f"fish_{fish_key}"
        else:
            reward_key = random.choices(tuple(pool), [item["rate"] for item in pool.values()])[0]
            reward = pool[reward_key]
            icon = reward_key
            if pool is JUNK:
                self.change_item("junk", reward_key, 1)
                result, xp = reward["name"], 5
            else:
                self.change_item(reward["type"], reward_key, reward["quantity"])
                result, xp = f"{reward['name']} ×{reward['quantity']}", 10
        earned_xp = round_reward(xp * pet.get("fishingXpBonus", 1))
        self.xp(earned_xp)
        self.state["last_fish"] = self.now
        return result, earned_xp, icon

    def sell_fish(self, selection: str) -> tuple[int, int]:
        owned = self.state["fish"]
        keys = list(owned) if selection == "all" else [selection.lstrip("#")]
        if not keys or any(key not in owned for key in keys):
            raise FarmError("Không tìm thấy cá trong kho.")
        multiplier = self.event.get("sellBonus", 1) * self.event.get("coinBonus", 1)
        coins = sum(round_reward(owned.pop(key)["price"] * multiplier) for key in keys)
        self.sale(coins, len(keys))
        return len(keys), coins

    def add_pet(self, key: str) -> None:
        self.state["pets"][key] = {
            "level": 1, "xp": 0, "stars": 0, "hunger": 100, "happiness": 100, "health": 100,
            "updated": self.now, "play": 0, "cuddle": 0, "exercise": 0,
        }

    def select_pet(self, key: str) -> str:
        key = key.lower()
        if key not in self.state["pets"]:
            raise FarmError("Bạn chưa sở hữu pet có mã này.")
        self.state["active_pet"] = key
        return PETS[key]["name"]

    def care(self, activity: str, food_id: str = "") -> tuple[str, dict]:
        key = self.state["active_pet"]
        if not key:
            raise FarmError("Hãy chọn pet đang hoạt động bằng lệnh `farm selectpet`.")
        pet = self.state["pets"][key]
        bonus = pet_bonus(key, pet)
        update_pet(pet, bonus, self.now)
        if activity == "feed":
            food_id = item_id(food_id)
            food = CATALOG["PET_FOODS"].get(food_id)
            if food is None:
                raise FarmError("Chọn mã thức ăn từ shop Farm.")
            self.change_item("food", food_id, -1)
            pet["hunger"] = min(100, pet["hunger"] + food["hunger"])
            pet["happiness"] = min(100, pet["happiness"] + food["happiness"])
            if pet["hunger"] > 70:
                pet["health"] = min(100, pet["health"] + 5)
            if food_id == "htng":
                self.state["tea_fed"] += 1
                if self.state["tea_fed"] == 10 and "hr" not in self.state["pets"]:
                    self.add_pet("hr")
            self.quest_progress("feed_pet", 1)
        elif activity == "kiss":
            wait = self.state.get("last_kiss", 0) + 1800 - self.now
            if wait > 0:
                raise FarmError(f"Hôn lại sau **{ceil(wait / 60)} phút**.")
            self.state["last_kiss"] = self.now
            pet["happiness"] = min(100, pet["happiness"] + 10)
        else:
            cooldown = {"play": 3600, "cuddle": 600, "exercise": 7200}[activity]
            if pet[activity] and self.now - pet[activity] < cooldown:
                wait = ceil((pet[activity] + cooldown - self.now) / 60)
                raise FarmError(f"Pet đang nghỉ. Thử lại sau **{wait} phút**.")
            pet[activity] = self.now
            if activity == "play":
                pet["happiness"] = min(100, pet["happiness"] + 50)
                pet["xp"] += 20
                self.xp(5)
                self.quest_progress("play_pet", 1)
            elif activity == "cuddle":
                pet["happiness"] = min(100, pet["happiness"] + 10 * self.event.get("petHappyBonus", 1))
            else:
                exercise = random.choice(CATALOG["ACTIVITIES"])
                pet["hunger"] = max(0, pet["hunger"] - exercise["hungerLoss"])
                pet["happiness"] = max(0, pet["happiness"] - exercise["happyLoss"])
                loss = round_reward(exercise["hpLoss"] * (1 - bonus.get("exerciseHpReduction", 0)))
                health = max(0, pet["health"] - loss)
                pet["health"] = min(100, health + (5 if pet["hunger"] > 70 else 0))
                pet["xp"] += exercise["xpGain"]
        if pet["level"] < 10 and pet["xp"] >= CATALOG["PET_LEVEL_XP"][pet["level"]]:
            pet["level"] += 1
            pet["xp"] = 0
        return key, pet

    def draw(self) -> dict:
        self.state["pity"] += 1
        pity = self.state["pity"]
        rate = 0.003 + max(0, pity - 79) * 0.05
        if pity >= 100 or random.random() < rate:
            limited = self.state["limited"] or random.random() < 0.40
            self.state["limited"] = not limited
            self.state["pity"] = 0
            return PETS[random.choice(("satou", "shio") if limited else ("kuromi", "melody"))]
        return random.choices(NORMAL_GACHA, [entry["rate"] for entry in NORMAL_GACHA])[0]

    def gacha(self, count: int) -> tuple[list[tuple[str, str]], bool]:
        if count not in {1, 10}:
            raise FarmError("Chọn gacha 1 hoặc 10 lượt.")
        use_tickets = self.state["tickets"] >= count
        if use_tickets:
            self.state["tickets"] -= count
        else:
            self.wallet(-10_000 * count)
        results = []
        for _ in range(count):
            reward = self.draw()
            key = reward["id"].lower()
            kind = reward["type"]
            label = reward["name"]
            icon = key
            if kind == "pet":
                icon = f"pet_{key}"
                owned = self.state["pets"].get(key)
                if owned:
                    owned["stars"] = min(6, owned["stars"] + 1)
                    coins = CATALOG["DUPLICATE_COIN_BY_RARITY"][reward["rarity"]]
                    self.wallet(coins)
                    label += f" (C{owned['stars']}, +{vnd(coins):,} VND)"
                else:
                    self.add_pet(key)
                if reward.get("isMythic"):
                    self.award("mythic_pet")
            elif kind == "coin":
                icon = "ui_coin"
                coins = random.randint(reward["min"], reward["max"])
                self.earn(coins)
                label = f"+{vnd(coins):,} VND"
            else:
                self.change_item(kind, key, reward["quantity"])
                label += f" ×{reward['quantity']}"
            results.append((icon, label))
        self.state["pulls"] += count
        self.quest_progress("gacha", count)
        return results, use_tickets

    def level_reward(self) -> int:
        previous = self.state["last_level_reward"]
        level = self.state["level"]
        if previous >= level:
            raise FarmError("Bạn đã nhận hết thưởng cấp độ hiện tại.")
        milestones = {5, 15, 25, 35, 45, 55, 60, 65, 70}
        tickets = sum(3 if rank in milestones else 1 for rank in range(previous + 1, level + 1))
        self.state["last_level_reward"] = level
        self.state["tickets"] += tickets
        return tickets

    def evolve(self) -> None:
        if self.state["evolutions"] or self.state["level"] < 50:
            raise FarmError("Cần đạt cấp 50 và chưa tiến hóa lần nào.")
        self.state.update(level=1, xp=0, evolutions=1, last_level_reward=1, plots={})
        self.state["tickets"] += 10
