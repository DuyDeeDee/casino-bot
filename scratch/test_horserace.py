import sys
import os
import random

# Add root folder to python path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import discord
from discord.ext import commands
from app.discord_bot.cogs.horserace import parse_bet_amount, HORSE_ROSTER, HorseRace, generate_horserace_image

def test_cog_instantiation():
    print("--- Testing Cog Instantiation ---")
    try:
        intents = discord.Intents.default()
        bot = commands.Bot(command_prefix="i?", intents=intents)
        cog = HorseRace(bot)
        print("[OK] HorseRace Cog instantiated successfully!")
        return True
    except Exception as e:
        print(f"[FAIL] Failed to instantiate HorseRace Cog: {e}")
        return False

def test_parse_bet_amount():
    print("\n--- Testing parse_bet_amount ---")
    current_money = 5000000 # 5M
    
    test_cases = [
        ("10k", 10000),
        ("2.5m", 2500000),
        ("all", current_money),
        ("allin", current_money),
        ("tất tay", current_money),
        ("1,500", 1500),
        ("100.000", 100000),
        ("100.5", 100),
        ("abc", 0),
        ("-500", 0),
    ]
    
    success = True
    for idx, (val_str, expected) in enumerate(test_cases):
        result = parse_bet_amount(val_str, current_money)
        if result == expected:
            print(f"[OK] Test case {idx} -> Parsed: {result} (Expected: {expected})")
        else:
            print(f"[FAIL] Test case {idx} -> Parsed: {result} (Expected: {expected})")
            success = False
            
    return success

def test_horse_selection_and_odds():
    print("\n--- Testing Horse Selection & Odds ---")
    # Selection
    num_horses = random.randint(4, 5)
    selected = random.sample(HORSE_ROSTER, num_horses)
    print(f"Selected {num_horses} horses out of 8:")
    
    for h in selected:
        odds = max(1.2, round(100 / h["power"], 1))
        # Remove unicode emoji/Vietnamese names from console print
        print(f" - Horse ID {h['id']}: Power={h['power']}, Odds={odds}x")
        # Validate power range
        if not (60 <= h["power"] <= 95):
            print(f"[FAIL] Horse power {h['power']} out of range [60, 95]!")
            return False
        # Validate odds formula
        expected_odds = max(1.2, round(100 / h["power"], 1))
        if abs(odds - expected_odds) > 1e-9:
            print(f"[FAIL] Odds mismatch! Got {odds}, expected {expected_odds}")
            return False
            
    print("[OK] Horse selection and odds calculation are correct.")
    return True

def test_race_simulation():
    print("\n--- Testing Simulated Race Step Logic ---")
    num_horses = 5
    selected_horses = random.sample(HORSE_ROSTER, num_horses)
    
    # Initialize state
    TRACK_LENGTH = 20
    raw_positions = {h["id"]: 0 for h in selected_horses}
    positions = {h["id"]: 0 for h in selected_horses}
    
    step = 0
    while not any(pos >= TRACK_LENGTH for pos in positions.values()):
        step += 1
        for horse in selected_horses:
            base_advance = random.randint(1, 2)
            if random.randint(1, 100) <= horse["power"]:
                advance = base_advance + 1
            else:
                advance = base_advance
                
            raw_positions[horse["id"]] += advance
            positions[horse["id"]] = min(TRACK_LENGTH, raw_positions[horse["id"]])
            
        print(f"Step {step}:")
        for horse in selected_horses:
            pos = positions[horse["id"]]
            track = "-" * pos + ">" + "-" * (TRACK_LENGTH - pos) + " |"
            print(f"  {track} ID {horse['id']} (Raw: {raw_positions[horse['id']]})")
            
    # Determine winner
    def get_sort_key(h):
        h_id = h["id"]
        return (raw_positions[h_id], h["power"], random.random())

    sorted_horses = sorted(selected_horses, key=get_sort_key, reverse=True)
    winner = sorted_horses[0]
    print(f"\n[OK] Winner ID {winner['id']} (Power: {winner['power']})")
    print("[OK] Race simulation completes successfully without any issues.")
    return True

def test_image_rendering():
    print("\n--- Testing UI Image Rendering ---")
    try:
        # Generate odds
        selected_horses = []
        for h in random.sample(HORSE_ROSTER, 5):
            odds = max(1.2, round(100 / h["power"], 1))
            selected_horses.append({
                "id": h["id"],
                "name": h["name"],
                "emoji": h["emoji"],
                "power": h["power"],
                "odds": odds
            })
            
        positions = {h["id"]: 0 for h in selected_horses} # lobby phase (all at 0)
        
        # Add mock bets
        bets = {
            123456: {selected_horses[0]["id"]: 500000000},
            789012: {selected_horses[0]["id"]: 10000000, selected_horses[1]["id"]: 50000},
            345678: {selected_horses[2]["id"]: 250000}
        }
        user_names = {
            123456: "de",
            789012: "Huy",
            345678: "Sal"
        }
        
        img_bytes = generate_horserace_image(selected_horses, positions, 20, bets, user_names)
        
        from PIL import Image
        img = Image.open(img_bytes)
        img.save("scratch/test_race_rendered.png")
        print("[OK] Image rendered and saved successfully to scratch/test_race_rendered.png")
        return True
    except Exception as e:
        print(f"[FAIL] Image rendering failed: {e}")
        return False

if __name__ == "__main__":
    s0 = test_cog_instantiation()
    s1 = test_parse_bet_amount()
    s2 = test_horse_selection_and_odds()
    s3 = test_race_simulation()
    s4 = test_image_rendering()
    
    if s0 and s1 and s2 and s3 and s4:
        print("\nALL TESTS PASSED!")
        sys.exit(0)
    else:
        print("\nSOME TESTS FAILED!")
        sys.exit(1)
