import sys
import os
import asyncio
from pathlib import Path
import shutil

# Setup path
sys.path.append(os.getcwd())

# Monkeypatch DB path
import app.discord_bot.modules.economy as eco
eco.DATABASE_PATH = Path("data/economy_test.db")

# Copy DB for testing
if Path("data/economy.db").exists():
    shutil.copy2("data/economy.db", "data/economy_test.db")

from app.discord_bot.modules.economy import Economy
from app.discord_bot.cogs.baito import Baito, GameSession, evaluate_hand
from app.discord_bot.modules.card import Card
import discord

class DummyBot:
    def __init__(self):
        self.economy = Economy()
        self.command_prefix = "i?"

class DummyUser:
    def __init__(self, id, name):
        self.id = id
        self.display_name = name
        self.mention = f"<@{id}>"
        self.display_avatar = self

    @property
    def url(self):
        return "http://dummy.url"
        
    async def send(self, *args, **kwargs):
        pass

class DummyChannel:
    async def send(self, content=None, *args, **kwargs):
        print(f"CHANNEL SEND: {content or ''} {kwargs.get('embed') or ''}")
        class DummyMsg:
            async def edit(self, *args, **kwargs):
                pass
        return DummyMsg()

async def run_tests():
    bot = DummyBot()
    cog = Baito(bot)
    
    print("--- 1. Testing Hand Evaluation & Tie-Breaking ---")
    # AAA (Ba Át)
    hand_aaa = [Card("hearts", 14), Card("diamonds", 14), Card("spades", 14)] # AAA
    r_val, r_name, _ = evaluate_hand(hand_aaa)
    print(f"AAA -> Rank Val: {r_val}, Name: {r_name} (Expected Rank: 12)")
    assert r_val == 12
    
    # 777 (Ba Cào)
    hand_777 = [Card("hearts", 7), Card("diamonds", 7), Card("spades", 7)]
    r_val, r_name, _ = evaluate_hand(hand_777)
    print(f"777 -> Rank Val: {r_val}, Name: {r_name} (Expected Rank: 11)")
    assert r_val == 11

    # J J K (Ba Tây)
    hand_jjk = [Card("hearts", 11), Card("diamonds", 11), Card("spades", 13)]
    r_val, r_name, _ = evaluate_hand(hand_jjk)
    print(f"J J K -> Rank Val: {r_val}, Name: {r_name} (Expected Rank: 10)")
    assert r_val == 10

    # 9 nút (A + 8 + Q)
    hand_9 = [Card("hearts", 14), Card("clubs", 8), Card("diamonds", 12)] # A(1) + 8 + Q(10) = 19 -> 9 nút
    r_val, r_name, _ = evaluate_hand(hand_9)
    print(f"A 8 Q -> Rank Val: {r_val}, Name: {r_name} (Expected Rank: 9)")
    assert r_val == 9
    
    # Tie-break test (Q Cơ vs Q Bích)
    # Hand A: 9 nút with Q Cơ
    hand_a = [Card("hearts", 14), Card("clubs", 8), Card("hearts", 12)] # Q Cơ ( Hearts is strongest suit )
    # Hand B: 9 nút with Q Bích
    hand_b = [Card("diamonds", 14), Card("clubs", 8), Card("spades", 12)] # Q Bích
    
    _, _, key_a = evaluate_hand(hand_a)
    _, _, key_b = evaluate_hand(hand_b)
    print(f"Hand A key: {key_a}, Hand B key: {key_b}")
    assert key_a > key_b
    print("Tie-breaking correct: Q Cơ beats Q Bích!")

    print("\n--- 2. Testing Game Session Loop ---")
    p1 = DummyUser(1001, "Duy")
    p2 = DummyUser(1002, "Nam")
    p3 = DummyUser(1003, "An")
    
    bot.economy.set_money(p1.id, 10_000_000)
    bot.economy.set_money(p2.id, 10_000_000)
    bot.economy.set_money(p3.id, 10_000_000)
    
    channel = DummyChannel()
    
    # Init game session
    session = GameSession(cog, channel, [p1, p2, p3], 100_000)
    await session.start()
    
    print(f"Initial Pot: {session.pot} VND (Expected: 300,000)")
    assert session.pot == 300_000
    
    # Turn sequence: Duy -> Nam -> An
    # Duy raises 100,000 VND
    await session.process_raise_action(p1, 100_000)
    # Nam calls (theo)
    await session.process_call_action(p2)
    # An folds (úp)
    await session.process_fold_action(p3)
    
    print(f"Current bet: {session.current_bet} VND")
    print(f"Current Pot: {session.pot} VND")
    print(f"Duy contribution: {session.player_states[p1.id]['contribution']} VND")
    print(f"Nam contribution: {session.player_states[p2.id]['contribution']} VND")
    
    assert session.current_bet == 200_000
    assert session.player_states[p1.id]["status"] == "active"
    assert session.player_states[p2.id]["status"] == "active"
    assert session.player_states[p3.id]["status"] == "folded"
    
    # Final call from Duy to complete betting? Wait, Duy was the raiser, so Nam called the raise.
    # Therefore Nam matched Duy's bet. The betting round is now stable!
    # Let's advance turn to see if showdown is automatically triggered
    print("Advancing turn to trigger showdown...")
    # The last action was An folding. Since Nam called Duy's raise, all active players (Duy and Nam)
    # have matched the current bet (200k). So the next advance_turn will showdown!
    # Let's verify by checking players in sequence.
    # We already called session.process_fold_action(p3), which calls advance_turn() internally.
    # So showdown should have executed!
    print("Action history logging:\n", "\n".join(session.action_history))
    
    # Check stats update
    print("\n--- 3. Checking Database stats updates ---")
    s1 = bot.economy.get_baito_stats(p1.id)
    s2 = bot.economy.get_baito_stats(p2.id)
    s3 = bot.economy.get_baito_stats(p3.id)
    
    print(f"Duy plays: {s1['plays']}, wins: {s1['wins']}, profit: {s1['profit']}")
    print(f"Nam plays: {s2['plays']}, wins: {s2['wins']}, profit: {s2['profit']}")
    print(f"An plays: {s3['plays']}, wins: {s3['wins']}, profit: {s3['profit']}")
    
    assert s1["plays"] == 1
    assert s2["plays"] == 1
    assert s3["plays"] == 1
    assert s3["profit"] == -100_000 # folded at cược sàn
    
    # Clean up test DB
    bot.economy.conn.close()
    if eco.DATABASE_PATH.exists():
        os.remove(eco.DATABASE_PATH)
    print("\nAll baito tests completed successfully!")

if __name__ == "__main__":
    asyncio.run(run_tests())
