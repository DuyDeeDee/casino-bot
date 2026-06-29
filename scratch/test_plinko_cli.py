import random
import time

RISK_SETTINGS = {
    "low": {
        "multipliers": [1.5, 1.2, 1.0, 0.8],
        "weights": [0.10, 0.25, 0.45, 0.20],
    },
    "medium": {
        "multipliers": [5.0, 2.0, 1.0, 0.5, 0.2],
        "weights": [0.03, 0.15, 0.40, 0.27, 0.15],
    },
    "high": {
        "multipliers": [100.0, 25.0, 10.0, 5.0, 3.0, 2.0, 1.0, 0.5, 0.2, 0.0],
        "weights": [0.0005, 0.0030, 0.0100, 0.0400, 0.0800, 0.1500, 0.2500, 0.2200, 0.1500, 0.0965],
    }
}

def simulate_plinko(risk="medium"):
    cfg = RISK_SETTINGS[risk]
    multiplier = random.choices(cfg["multipliers"], weights=cfg["weights"])[0]
    directions = [random.choice(["↙", "↘"]) for _ in range(3)]
    
    frames = [
        "🔴",
        "🔴\n⬇\n🔹",
        f"🔴\n⬇\n🔹\n{directions[0]}\n🔹",
        f"🔴\n⬇\n🔹\n{directions[0]}\n🔹\n{directions[1]}\n🔹",
        f"🔴\n⬇\n🔹\n{directions[0]}\n🔹\n{directions[1]}\n🔹\n{directions[2]}\n🔹",
        f"🔴\n⬇\n🔹\n{directions[0]}\n🔹\n{directions[1]}\n🔹\n{directions[2]}\n🔹\n⬇"
    ]
    
    for i, frame in enumerate(frames):
        print(f"--- FRAME {i} ---")
        print(frame)
        print()
        time.sleep(0.1)
        
    print("--- FINAL RESULT ---")
    print(f"Bóng rơi vào ô: {multiplier}x")

if __name__ == "__main__":
    simulate_plinko("high")
