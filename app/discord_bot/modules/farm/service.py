"""Persistent Farm actions using the Casino economy connection."""

import json
import random
import time
from contextlib import contextmanager
from datetime import date, timedelta
from math import ceil
from uuid import uuid4

from .rules import (
    ACHIEVEMENTS, ALL_WORDS, CATALOG, CROPS, FISH, INVENTORY_CAPACITY, JUNK, NORMAL_GACHA,
    PETS, QUALITIES, QUESTS, RINGS, RODS, SHOP, START_COINS, VND_PER_COIN, active_pet_bonus, daily_quests,
    day_at, event_at, item_id, pet_bonus, pet_key, round_reward, season_at, update_pet, vnd,
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

    def leaderboard(self, metric: str, user_id: int) -> tuple[list[tuple], int | None]:
        metric = {"farm": "earned", "couples": "couple", "capdoi": "couple"}.get(metric, metric)
        if metric == "couple":
            rows = self.economy.conn.execute(
                """SELECT user_id,
                          json_extract(state, '$.marriage.partner') AS partner,
                          json_extract(state, '$.marriage.at') AS married_at,
                          RANK() OVER (ORDER BY json_extract(state, '$.marriage.at')) AS rank
                   FROM farm_players WHERE user_id = json_extract(state, '$.marriage.proposer')
                   ORDER BY married_at, user_id"""
            ).fetchall()
            rank = next((row[3] for row in rows if user_id in row[:2]), None)
            return rows[:10], rank
        ordering = {
            "level": "evolutions DESC, score DESC, xp DESC",
            "coin": "score DESC",
            "earned": "score DESC",
            "streak": "score DESC",
            "harvested": "score DESC",
        }.get(metric)
        if not ordering:
            raise FarmError("Chọn bảng `coin`, `level`, `farm`, `streak` hoặc `couple`.")
        score = "COALESCE(e.money, 0)" if metric == "coin" else "json_extract(p.state, ?)"
        params = (user_id,) if metric == "coin" else (f"$.{metric}", user_id)
        rows = self.economy.conn.execute(
            f"""WITH scores AS (
                    SELECT p.user_id, {score} AS score,
                           json_extract(p.state, '$.evolutions') AS evolutions,
                           json_extract(p.state, '$.xp') AS xp
                    FROM farm_players p LEFT JOIN economy e ON e.user_id = p.user_id
                ), ranks AS (
                    SELECT user_id, score, evolutions, RANK() OVER (ORDER BY {ordering}) AS rank,
                           ROW_NUMBER() OVER (ORDER BY {ordering}, user_id) AS position FROM scores
                )
                SELECT user_id, score, evolutions, rank FROM ranks
                WHERE position <= 10 OR user_id = ? ORDER BY position""",
            params,
        ).fetchall()
        return rows[:10], next((row[3] for row in rows if row[0] == user_id), None)

    def proposal_ring(self, proposer: int, target: int) -> str:
        if proposer == target:
            raise FarmError("Bạn không thể tự cầu hôn mình.")
        sender = self.get(proposer)
        receiver = self.get(target)
        if sender.get("marriage") or receiver.get("marriage"):
            raise FarmError("Một trong hai người đã kết hôn trong Farm.")
        ring = next((ring for ring in RINGS if sender["inventory"].get(f"ring:{ring}")), None)
        if not ring:
            raise FarmError("Bạn cần có nhẫn trong kho. Xem `farm shop ring`.")
        return ring

    def marry(self, proposer: int, target: int, guild_id: int, ring: str) -> None:
        with self.action(proposer, "marry") as session:
            receiver = self.get(target, now=session.now)
            if proposer == target or session.state.get("marriage") or receiver.get("marriage"):
                raise FarmError("Lời cầu hôn không còn hợp lệ.")
            if ring not in RINGS:
                raise FarmError("Nhẫn cưới không hợp lệ.")
            session.change_item("ring", ring, -1)
            wedding = {"id": uuid4().hex, "proposer": proposer, "guild": guild_id, "ring": ring, "at": session.now}
            session.state["marriage"] = dict(wedding, partner=target)
            receiver["marriage"] = dict(wedding, partner=proposer)
            self._save(target, receiver)

    def divorce(self, user_id: int, marriage_id: str) -> None:
        with self.action(user_id, "divorce") as session:
            wedding = session.state.get("marriage")
            if not wedding or wedding["id"] != marriage_id:
                raise FarmError("Hôn nhân này đã thay đổi.")
            partner = self.get(wedding["partner"], now=session.now)
            if partner.get("marriage", {}).get("id") == marriage_id:
                partner.pop("marriage")
                self._save(wedding["partner"], partner)
            session.state.pop("marriage")

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

    def balance(self) -> int:
        row = self.economy.conn.execute("SELECT money FROM economy WHERE user_id = ?", (self.user_id,)).fetchone()
        return row[0] if row else 0

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

    def plant(self, key: str, quantity: int | str) -> tuple[list[tuple[str, int, float]], int]:
        key = item_id(key)
        plots = self.state["plots"]
        free = [str(index) for index in range(1, plot_limit(self.state["level"]) + 1) if str(index) not in plots]
        if not free:
            raise FarmError("Không còn ô đất trống.")
        inventory = self.state["inventory"]
        if key in ALL_WORDS:
            orders = [
                (entry[5:], stock) for entry, stock in inventory.items()
                if entry.startswith("seed:") and entry[5:] in CROPS and stock > 0
            ]
            if not orders:
                raise FarmError("Không có hạt giống trong kho. Xem `farm shop seeds`.")
            seed_only = True
        else:
            if key not in CROPS or quantity != "all" and (not isinstance(quantity, int) or quantity < 1):
                raise FarmError("Chọn mã cây và số lượng lớn hơn 0, hoặc dùng `all`.")
            orders = [(key, len(free) if quantity == "all" else quantity)]
            seed_only = False
        batch, cost, used = [], 0, 0
        available = self.balance() // VND_PER_COIN
        grow_factor = max(0.1, 1 - 0.1 * self.state["evolutions"])
        for crop_id, requested in orders:
            if used == len(free):
                break
            crop = CROPS[crop_id]
            count = min(requested, len(free) - used)
            seeds = min(count, inventory.get(f"seed:{crop_id}", 0))
            bought = 0 if seed_only else min(count - seeds, available // crop["seedCost"])
            planted = seeds + bought
            if not planted:
                raise FarmError(f"Cần hạt giống hoặc **{vnd(crop['seedCost']):,} VND** để trồng.")
            if seeds:
                self.change_item("seed", crop_id, -seeds)
            cost += bought * crop["seedCost"]
            ready = self.now + crop["growTime"] * self.event.get("growBonus", 1) * grow_factor
            for index in free[used:used + planted]:
                plots[index] = {"crop": crop_id, "ready": ready, "watered": None, "fertilized": ""}
            used += planted
            batch.append((crop_id, planted, ready))
        self.wallet(-cost)
        self.state["planted"] += used
        self.xp(2 * used)
        self.quest_progress("plant", used)
        return batch, cost

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
        pet = active_pet_bonus(self.state["pets"], self.state["active_pet"])
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
        self.quest_progress("harvest", len(ready))
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
        if not self.state.get("fishing_bypass") and remaining > 0:
            raise FarmError(f"Chờ **{ceil(remaining)} giây** để câu tiếp.")
        inventory = self.state["inventory"]
        key = item_id(key) if key else self.state["rod"]
        if not key:
            key = next((rod for rod in RODS if inventory.get(f"fishing:{rod}")), None)
        if key not in RODS or not inventory.get(f"fishing:{key}"):
            raise FarmError("Bạn cần mua cần câu #260, #261 hoặc #262 từ shop Farm.")
        self.wallet(-100)
        rod = RODS[key]
        pet = active_pet_bonus(self.state["pets"], self.state["active_pet"])
        pools = (FISH, JUNK, CATALOG["BONUS_ITEMS"])
        pool = random.choices(pools, [sum(item["rate"] for item in pool.values()) for pool in pools])[0]
        if pool is FISH:
            fish_key = random.choices(tuple(FISH), [fish["rate"] for fish in FISH.values()])[0]
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
        self.earn(coins)
        self.quest_progress("sell", len(keys))
        self.quest_progress("earn_coin", coins)
        return len(keys), coins

    def add_pet(self, key: str) -> None:
        self.state["pets"][key] = {
            "level": 1, "xp": 0, "stars": 0, "hunger": 100, "happiness": 100, "health": 100,
            "updated": self.now, "play": 0, "cuddle": 0, "exercise": 0,
        }

    def pet_status(self, value: str | None) -> tuple[str, dict]:
        key = pet_key(value) if value else self.state["active_pet"]
        pet = self.state["pets"].get(key)
        if pet is None:
            raise FarmError("Hãy chọn pet đang hoạt động hoặc nhập mã pet đã sở hữu.")
        update_pet(pet, pet_bonus(key, pet), self.now)
        return key, pet

    def select_pet(self, key: str) -> str:
        key = pet_key(key)
        remaining = self.state.get("satou_locked_until", 0) - self.now
        if remaining > 0:
            raise FarmError(f"Satou đang khóa pet. Còn **{ceil(remaining / 3600)} giờ**.")
        if key not in self.state["pets"]:
            raise FarmError("Bạn chưa sở hữu pet có mã này.")
        self.state["active_pet"] = key
        if key == "satou" and self.state.get("satou_kills", 0) >= 5:
            self.state["satou_locked_until"] = self.now + 86400
        return PETS[key]["name"]

    def kill_pet(self, key: str) -> tuple[str, int, int]:
        if self.state["active_pet"] != "satou":
            raise FarmError("Hãy chọn Satou Matsuzaka làm pet đang hoạt động.")
        key = pet_key(key)
        target = self.state["pets"].get(key)
        if not target or target["stars"] < 1:
            raise FarmError("Pet của bạn phải ở C1 trở lên.")
        self.change_item("weapon", "dao", -1)
        target["stars"] -= 1
        self.state["satou_kills"] = self.state.get("satou_kills", 0) + 1
        return PETS[key]["name"], target["stars"], self.state["satou_kills"]

    def update_reward(self) -> int:
        if self.state.get("last_update_claim") == "S2_2025":
            raise FarmError("Bạn đã nhận phần thưởng cập nhật Mùa 2.")
        self.state["last_update_claim"] = "S2_2025"
        self.state["tickets"] += 10
        return self.state["tickets"]

    def care(self, activity: str, food_id: str = "") -> tuple[str, dict, bool]:
        key = self.state["active_pet"]
        if not key:
            raise FarmError("Hãy chọn pet đang hoạt động bằng lệnh `farm selectpet`.")
        pet = self.state["pets"][key]
        bonus = pet_bonus(key, pet)
        update_pet(pet, bonus, self.now)
        unlocked_huyn = False
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
            if food_id == "htng" and "hr" in self.state["pets"] and not self.state.get("huyn_active"):
                self.state["tea_fed"] += 1
                if self.state["tea_fed"] >= 10:
                    self.state["huyn_active"] = unlocked_huyn = True
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
        return key, pet, unlocked_huyn

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
        slots = list(range(count))
        if count > 1:
            random.shuffle(slots)
        guarantees = self.state.get("gacha_guarantees", [])
        guaranteed = {}
        for entry in guarantees:
            for _ in range(min(len(slots), entry["remaining"])):
                guaranteed[slots.pop()] = entry["pet"]
                entry["remaining"] -= 1
        if guaranteed:
            self.state["gacha_guarantees"] = [entry for entry in guarantees if entry["remaining"] > 0]
        results = []
        for slot in range(count):
            if slot in guaranteed:
                reward = PETS[guaranteed[slot]]
                self.state["pity"] = 0 if reward.get("isMythic") else self.state["pity"] + 1
            else:
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

    def arrange_gacha(self, value: str, count: int) -> tuple[str, int]:
        key = pet_key(value)
        if key not in PETS or not 1 <= count <= 10_000:
            raise FarmError("Chọn pet và số lượt hợp lệ.")
        guarantees = self.state.setdefault("gacha_guarantees", [])
        entry = next((entry for entry in guarantees if entry["pet"] == key), None)
        if entry is None:
            entry = {"pet": key, "remaining": 0}
            guarantees.append(entry)
        entry["remaining"] += count
        return PETS[key]["name"], entry["remaining"]

    def grant_pet(self, value: str) -> tuple[str, int]:
        key = pet_key(value)
        if key not in PETS:
            raise FarmError("Mã pet không hợp lệ.")
        pet = self.state["pets"].get(key)
        if pet is None:
            self.add_pet(key)
            return PETS[key]["name"], 0
        if pet["stars"] >= 6:
            raise FarmError("Pet đã đạt C6.")
        pet["stars"] += 1
        return PETS[key]["name"], pet["stars"]

    def admin_plant(self, value: str) -> str:
        key = item_id(value)
        crop = CROPS.get(key)
        if not crop:
            raise FarmError("Mã cây không hợp lệ.")
        plots = self.state["plots"]
        free = [str(n) for n in range(1, plot_limit(self.state["level"]) + 1) if str(n) not in plots]
        cost = len(free) * crop["seedCost"]
        self.wallet(-cost)
        for position in free:
            plots[position] = {"crop": key, "ready": self.now + crop["growTime"], "watered": None, "fertilized": ""}
        self.state["planted"] += len(free)
        self.xp(2 * len(free))
        return f"Đã trồng **{len(free)} {crop['name']}** · Chi phí **{vnd(cost):,} VND**."

    def admin_harvest(self) -> str:
        plots = self.state["plots"]
        weights = [quality["rate"] for quality in QUALITIES.values()]
        coins, xp = 0, 0
        for plot in plots.values():
            crop = CROPS[plot["crop"]]
            quality = random.choices(tuple(QUALITIES), weights)[0]
            coins += int(crop["sellValue"] * QUALITIES[quality]["multiplier"])
            xp += crop["xp"]
        count = len(plots)
        plots.clear()
        self.state["harvested"] += count
        self.earn(coins)
        self.xp(xp)
        return f"Đã thu hoạch **{count} ô** · **+{vnd(coins):,} VND** · **+{xp} XP**."

    def admin_skip(self, kind: str) -> str:
        if kind not in {"daily", "nung", "td", "farm", "all"}:
            raise FarmError("Chọn `daily`, `nung`, `td`, `farm` hoặc `all`.")
        if kind in {"daily", "all"}:
            self.state["daily"] = ""
        if kind in {"nung", "td", "all"}:
            pet = self.state["pets"].get(self.state["active_pet"])
            if pet is None and kind != "all":
                raise FarmError("Người chơi chưa có pet đang hoạt động.")
            if pet is not None:
                if kind in {"nung", "all"}:
                    pet["cuddle"] = 0
                if kind in {"td", "all"}:
                    pet["exercise"] = 0
        if kind in {"farm", "all"}:
            self.farm_admin("ready", ())
        return f"Đã bỏ qua thời gian chờ **{kind}**."

    def farm_admin(self, action: str, args: tuple[str, ...]) -> str:
        value = args[0] if args else ""
        if action == "info":
            return (
                f"Cấp **{self.state['level']}**, {self.state['xp']} XP\n"
                f"**{len(self.state['plots'])}/{plot_limit(self.state['level'])}** ô · **{len(self.state['pets'])}** pet\n"
                f"**{self.state['tickets']}** vé · Pity **{self.state['pity']}/100**"
            )
        if action == "gachapet":
            name, count = self.arrange_gacha(value, int(args[1]))
            return f"Đã đặt **{count}** lượt bảo đảm ra **{name}**."
        if action in {"pet", "takepet"}:
            key = pet_key(value)
            exists = key in self.state["pets"]
            if action == "pet" and key in PETS and not exists:
                self.add_pet(key)
                return f"Đã cấp **{PETS[key]['name']}**."
            if action == "takepet" and exists:
                del self.state["pets"][key]
                if self.state["active_pet"] == key:
                    self.state["active_pet"] = None
                return f"Đã thu hồi **{PETS[key]['name']}**."
            raise FarmError("Kiểm tra mã và quyền sở hữu pet.")
        if action in {"coin", "setcoin", "xp", "setlevel", "pull"}:
            amount = int(value or ("1" if action == "pull" else ""))
            if action in {"coin", "setcoin"}:
                change = amount if action == "coin" else amount - self.balance()
                if self.economy.adjust_wallet_money(self.user_id, change, event="farm", command=f"farm cheat {action}") is None:
                    raise FarmError("Điều chỉnh này vượt số dư hoặc giới hạn SQLite.")
                return f"Đã điều chỉnh ví **{change:+,} VND**."
            if action == "xp":
                self.xp(max(-self.state["xp"], amount))
            elif action == "setlevel":
                if not 1 <= amount <= (70 if self.state["evolutions"] else 50):
                    raise FarmError("Cấp đó nằm ngoài giới hạn.")
                self.state.update(level=amount, xp=0)
            elif self.state["tickets"] + amount >= 0:
                self.state["tickets"] += amount
            else:
                raise FarmError("Số vé không thể âm.")
            return f"Cấp **{self.state['level']}**, {self.state['xp']} XP, **{self.state['tickets']}** vé."
        if action in {"seed", "food", "rod", "item"}:
            key = item_id(value)
            if action == "rod" and key not in RODS:
                key = f"rod_{key}"
            item = SHOP.get(key)
            if item is None or item["category"] == "pets":
                raise FarmError("Mã vật phẩm không hợp lệ.")
            category = "seed" if item["category"] == "seeds" else item["category"]
            wanted = {"seed": "seed", "food": "food", "rod": "fishing"}.get(action, category)
            count = int(args[1]) if len(args) > 1 else 1
            if category != wanted or count < 1:
                raise FarmError("Danh mục hoặc số lượng không hợp lệ.")
            self.change_item(category, key, count)
            return f"Đã cấp **{item['name']} ×{count}**."
        if action == "unlockpet":
            self.state["satou_locked_until"] = 0
            return "Đã mở khóa đổi pet."
        if action == "fishcd":
            bypass = not self.state.get("fishing_bypass")
            self.state["fishing_bypass"] = bypass
            return "Đã tắt chờ câu cá." if bypass else "Đã bật lại thời gian chờ câu cá."
        if action in {"ready", "reset", "resync"}:
            plots = self.state["plots"]
            if action == "reset":
                plots.clear()
                return "Đã dọn trống các ô đất."
            if action == "resync":
                return f"Nông trại có {len(plots)}/{plot_limit(self.state['level'])} ô đang dùng."
            growing = [plot for plot in plots.values() if plot["ready"] > self.now]
            for plot in growing:
                plot["ready"] = self.now
            return f"Đã làm chín {len(growing)} ô đất."
        if action in {"clear", "clearall", "cleanup"}:
            inventory = self.state["inventory"]
            if action == "clear" and (not value or len(args) < 2 or args[1].lower() != "all"):
                raise FarmError("Dùng `farm cheat @người clear <mã> all`.")
            targets = [
                key for key in inventory
                if action == "clearall" or action == "clear" and key.partition(":")[2] == item_id(value)
                or action == "cleanup" and (not key.partition(":")[0] or not key.partition(":")[2])
            ]
            for key in targets:
                inventory.pop(key)
            return f"Đã xóa {len(targets)} loại vật phẩm."
        raise FarmError("Thao tác quản trị Farm không hợp lệ.")

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
