import math
import random
from typing import Any

# 20 world-class football clubs with attack, defence, midfield ratings and AI Coaches
TEAMS: dict[str, dict[str, Any]] = {
    "RMA": {
        "name": "Real Madrid",
        "emoji": "👑",
        "att": 4.8,
        "def": 4.6,
        "mid": 4.7,
        "stadium": "Santiago Bernabéu",
        "coach": "Carlo Ancelotti",
        "tactic": "DNA Ngược Dòng & Phản Công Tốc Độ",
        "perk": "comeback_dna",  # +25% late xG if trailing
    },
    "MCI": {
        "name": "Manchester City",
        "emoji": "🔵",
        "att": 4.8,
        "def": 4.5,
        "mid": 4.9,
        "stadium": "Etihad Stadium",
        "coach": "Pep Guardiola",
        "tactic": "Tiki-Taka Kiểm Soát Toàn Diện",
        "perk": "possession_master",  # +15% possession, +10% xG
    },
    "ARS": {
        "name": "Arsenal",
        "emoji": "🔴",
        "att": 4.6,
        "def": 4.6,
        "mid": 4.6,
        "stadium": "Emirates Stadium",
        "coach": "Mikel Arteta",
        "tactic": "Pressing Tầm Cao & Tình Huống Cố Định",
        "perk": "set_piece_king",  # +15% set piece goal chance
    },
    "LIV": {
        "name": "Liverpool",
        "emoji": "🦅",
        "att": 4.7,
        "def": 4.4,
        "mid": 4.6,
        "stadium": "Anfield",
        "coach": "Arne Slot",
        "tactic": "Gegenpressing Chuyển Trạng Thái",
        "perk": "counter_press",
    },
    "BAR": {
        "name": "Barcelona",
        "emoji": "🔵",
        "att": 4.7,
        "def": 4.2,
        "mid": 4.7,
        "stadium": "Camp Nou",
        "coach": "Hansi Flick",
        "tactic": "Dâng Cao Bẫy Việt Vị & Tấn Công Áp Đảo",
        "perk": "high_line_attack",
    },
    "BAY": {
        "name": "Bayern Munich",
        "emoji": "⭐",
        "att": 4.7,
        "def": 4.3,
        "mid": 4.5,
        "stadium": "Allianz Arena",
        "coach": "Vincent Kompany",
        "tactic": "Bóng Đá Tổng Lực & Tốc Độ Cánh",
        "perk": "heavy_metal",
    },
    "PSG": {
        "name": "Paris Saint-Germain",
        "emoji": "🗼",
        "att": 4.5,
        "def": 4.1,
        "mid": 4.4,
        "stadium": "Parc des Princes",
        "coach": "Luis Enrique",
        "tactic": "Kiểm Soát Vị Trí & Đột Phá Cá Nhân",
        "perk": "possession_master",
    },
    "INT": {
        "name": "Inter Milan",
        "emoji": "🐍",
        "att": 4.4,
        "def": 4.6,
        "mid": 4.5,
        "stadium": "San Siro",
        "coach": "Simone Inzaghi",
        "tactic": "Sơ Đồ 3-5-2 Phản Công Kỷ Luật",
        "perk": "counter_press",
    },
    "LEV": {
        "name": "Bayer Leverkusen",
        "emoji": "⚡",
        "att": 4.4,
        "def": 4.3,
        "mid": 4.5,
        "stadium": "BayArena",
        "coach": "Xabi Alonso",
        "tactic": "Neverkusen Magic (Bùng Nổ Phút Bù Giờ)",
        "perk": "comeback_dna",
    },
    "ATM": {
        "name": "Atletico Madrid",
        "emoji": "🛡️",
        "att": 4.1,
        "def": 4.6,
        "mid": 4.3,
        "stadium": "Metropolitano",
        "coach": "Diego Simeone",
        "tactic": "Cholismo Đổ Bê Tông Phòng Ngự Phản Công",
        "perk": "park_the_bus",  # -25% match xG
    },
    "BVB": {
        "name": "Borussia Dortmund",
        "emoji": "🟡",
        "att": 4.3,
        "def": 4.0,
        "mid": 4.2,
        "stadium": "Signal Iduna Park",
        "coach": "Nuri Sahin",
        "tactic": "Cơn Lốc Vàng Rực Lửa",
        "perk": "heavy_metal",
    },
    "CHE": {
        "name": "Chelsea",
        "emoji": "🦁",
        "att": 4.2,
        "def": 4.0,
        "mid": 4.3,
        "stadium": "Stamford Bridge",
        "coach": "Enzo Maresca",
        "tactic": "Phối Hợp Nhỏ & Kiểm Soát Khu Vực",
        "perk": "possession_master",
    },
    "MUN": {
        "name": "Manchester United",
        "emoji": "😈",
        "att": 4.1,
        "def": 3.9,
        "mid": 4.1,
        "stadium": "Old Trafford",
        "coach": "Ruben Amorim",
        "tactic": "Sơ Đồ 3-4-3 Tốc Độ & Trực Diện",
        "perk": "high_line_attack",
    },
    "JUV": {
        "name": "Juventus",
        "emoji": "🦓",
        "att": 4.1,
        "def": 4.4,
        "mid": 4.2,
        "stadium": "Allianz Stadium",
        "coach": "Thiago Motta",
        "tactic": "Bọc Lót Khu Vực Chắc Chắn",
        "perk": "park_the_bus",
    },
    "MIL": {
        "name": "AC Milan",
        "emoji": "🔴",
        "att": 4.2,
        "def": 4.1,
        "mid": 4.1,
        "stadium": "San Siro",
        "coach": "Paulo Fonseca",
        "tactic": "Tấn Công Biên & Tốc Độ",
        "perk": "counter_press",
    },
    "TOT": {
        "name": "Tottenham Hotspur",
        "emoji": "🐓",
        "att": 4.2,
        "def": 3.8,
        "mid": 4.1,
        "stadium": "Tottenham Stadium",
        "coach": "Ange Postecoglou",
        "tactic": "Ange-ball Tấn Công Liều Mạng",
        "perk": "high_line_attack",
    },
    "NAP": {
        "name": "Napoli",
        "emoji": "🌋",
        "att": 4.2,
        "def": 4.1,
        "mid": 4.2,
        "stadium": "Diego Maradona",
        "coach": "Antonio Conte",
        "tactic": "Kỷ Luật Thép & Thể Lực Sung Mãn",
        "perk": "counter_press",
    },
    "AVL": {
        "name": "Aston Villa",
        "emoji": "🟣",
        "att": 4.1,
        "def": 4.0,
        "mid": 4.2,
        "stadium": "Villa Park",
        "coach": "Unai Emery",
        "tactic": "Bẫy Việt Vị Tinh Quái",
        "perk": "set_piece_king",
    },
    "NEW": {
        "name": "Newcastle United",
        "emoji": "⬛",
        "att": 4.1,
        "def": 4.1,
        "mid": 4.1,
        "stadium": "St James' Park",
        "coach": "Eddie Howe",
        "tactic": "Tranh Chấp Quyết Liệt & Bóng Dài",
        "perk": "heavy_metal",
    },
    "SPO": {
        "name": "Sporting CP",
        "emoji": "🟢",
        "att": 4.2,
        "def": 4.0,
        "mid": 4.1,
        "stadium": "José Alvalade",
        "coach": "João Pereira",
        "tactic": "Tấn Công Trực Diện Khung Thành",
        "perk": "counter_press",
    },
}

OUTCOME_LABELS: dict[str, str] = {
    "1": "Đội nhà thắng",
    "X": "Hòa",
    "2": "Đội khách thắng",
    "OU_OVER": "Tài 2.5 (≥ 3 bàn)",
    "OU_UNDER": "Xỉu 2.5 (≤ 2 bàn)",
    "BTTS_YES": "Cả hai đội ghi bàn (Có)",
    "BTTS_NO": "Cả hai đội ghi bàn (Không)",
    "HDP_1": "Kèo chấp (Đội nhà)",
    "HDP_2": "Kèo chấp (Đội khách)",
}

FLAVOR_COMMENTARY = [
    "⚡ {team} tổ chức phản công thần tốc nhưng hậu vệ đối phương can thiệp kịp thời!",
    "🟨 Thẻ vàng cho cầu thủ {team} sau pha vào bóng quyết liệt ở khu vực giữa sân.",
    "🎯 {team} tung cú sút phạt hàng rào cực kỳ hiểm hóc — bóng dội xà ngang bật ra!",
    "🔄 Ban huấn luyện {team} chỉ đạo thay đổi chiến thuật nhằm tìm kiếm bàn thắng.",
    "🧱 Hàng thủ {team} bọc lót kiên cường, hóa giải đợt hãm thành liên tiếp.",
    "😱 Cơ hội mười mươi cho {team} nhưng tiền đạo lại đệm bóng ra ngoài trong gang tấc!",
    "🧤 Thủ môn {team} có pha bay người đổ người cản phá xuất thần!",
    "🚀 Tiền vệ {team} tung cú nã đại bác từ cự ly 25m khiến khung gỗ rung chuyển!",
    "🚩 Trọng tài biên căng cờ báo việt vị trong một pha thoát xuống nguy hiểm của {team}.",
    "📺 Trọng tài tham khảo VAR và quyết định không có quả phạt đền nào cho {team}!",
]


def get_drifted_team(team_code: str, rng: random.Random | None = None) -> dict[str, Any]:
    """Applies a slight form drift (-10% to +10%) for match unpredictability."""
    r = rng if rng is not None else random
    base = TEAMS.get(team_code, {
        "name": team_code, "emoji": "⚽", "att": 4.0, "def": 4.0, "mid": 4.0,
        "stadium": "Stadium", "coach": "HLV Trưởng", "tactic": "Cân bằng", "perk": "none"
    })
    t = dict(base)
    t["code"] = team_code
    t["att"] = round(base["att"] * r.uniform(0.90, 1.10), 2)
    t["def"] = round(base["def"] * r.uniform(0.90, 1.10), 2)
    t["mid"] = round(base["mid"] * r.uniform(0.90, 1.10), 2)
    return t


def calculate_match_probabilities(t1: dict[str, Any], t2: dict[str, Any]) -> dict[str, Any]:
    """
    Calculates expected goal rates (xG / lambda) and probabilities for:
    - 1X2 (Win / Draw / Loss)
    - Over / Under 2.5
    - Both Teams to Score (BTTS)
    - Asian Handicap
    """
    att1 = t1["att"] + 0.20  # Home advantage
    def1 = t1["def"] + 0.10
    mid1 = t1.get("mid", 4.0)

    att2 = t2["att"]
    def2 = t2["def"]
    mid2 = t2.get("mid", 4.0)

    # Tactical perk adjustments
    perk1 = t1.get("perk", "")
    perk2 = t2.get("perk", "")
    mod_lambda_1 = 1.0
    mod_lambda_2 = 1.0

    if perk1 == "possession_master":
        mod_lambda_1 += 0.08
    elif perk1 == "park_the_bus":
        mod_lambda_1 -= 0.15
        mod_lambda_2 -= 0.20
    elif perk1 == "high_line_attack":
        mod_lambda_1 += 0.15
        mod_lambda_2 += 0.10

    if perk2 == "possession_master":
        mod_lambda_2 += 0.08
    elif perk2 == "park_the_bus":
        mod_lambda_2 -= 0.15
        mod_lambda_1 -= 0.20
    elif perk2 == "high_line_attack":
        mod_lambda_2 += 0.15
        mod_lambda_1 += 0.10

    base_lambda_1 = 1.35 * (att1 / max(1.0, def2)) * (mid1 / max(1.0, mid2)) ** 0.5 * mod_lambda_1
    base_lambda_2 = 1.15 * (att2 / max(1.0, def1)) * (mid2 / max(1.0, mid1)) ** 0.5 * mod_lambda_2

    lambda_1 = max(0.4, min(3.8, base_lambda_1))
    lambda_2 = max(0.3, min(3.5, base_lambda_2))

    max_goals = 7
    p_matrix = [[0.0] * (max_goals + 1) for _ in range(max_goals + 1)]
    for g1 in range(max_goals + 1):
        p1 = (lambda_1**g1 * math.exp(-lambda_1)) / math.factorial(g1)
        for g2 in range(max_goals + 1):
            p2 = (lambda_2**g2 * math.exp(-lambda_2)) / math.factorial(g2)
            p_matrix[g1][g2] = p1 * p2

    prob_1 = 0.0
    prob_x = 0.0
    prob_2 = 0.0
    prob_over_25 = 0.0
    prob_under_25 = 0.0
    prob_btts_yes = 0.0
    prob_btts_no = 0.0

    for g1 in range(max_goals + 1):
        for g2 in range(max_goals + 1):
            p = p_matrix[g1][g2]
            # 1X2
            if g1 > g2:
                prob_1 += p
            elif g1 == g2:
                prob_x += p
            else:
                prob_2 += p

            # Over/Under 2.5
            if (g1 + g2) >= 3:
                prob_over_25 += p
            else:
                prob_under_25 += p

            # BTTS
            if g1 > 0 and g2 > 0:
                prob_btts_yes += p
            else:
                prob_btts_no += p

    total_1x2 = prob_1 + prob_x + prob_2
    return {
        "1": round(prob_1 / total_1x2, 4),
        "X": round(prob_x / total_1x2, 4),
        "2": round(prob_2 / total_1x2, 4),
        "OU_OVER": round(prob_over_25, 4),
        "OU_UNDER": round(prob_under_25, 4),
        "BTTS_YES": round(prob_btts_yes, 4),
        "BTTS_NO": round(prob_btts_no, 4),
        "lambda_1": round(lambda_1, 2),
        "lambda_2": round(lambda_2, 2),
    }


def calculate_base_odds(probs: dict[str, Any], margin: float = 0.06) -> dict[str, float]:
    """
    Converts probabilities into fair Decimal Base Odds across all markets with a bookmaker margin.
    """
    odds = {}
    for outcome in ("1", "X", "2", "OU_OVER", "OU_UNDER", "BTTS_YES", "BTTS_NO"):
        p = max(0.02, float(probs.get(outcome, 0.33)))
        raw_odds = (1.0 - margin) / p
        odds[outcome] = round(max(1.15, min(15.0, raw_odds)), 2)
    return odds


def generate_momentum_bar(score_t1: int, score_t2: int, xg1: float, xg2: float) -> str:
    """Generates a visual momentum pressure bar [🟦🟦🟦🟦⬜⬜⬜🟥🟥]"""
    power_1 = xg1 + score_t1 * 1.5
    power_2 = xg2 + score_t2 * 1.5
    total = power_1 + power_2
    if total <= 0:
        return "`[🟦🟦🟦🟦⬜⬜⬜🟥🟥]`"

    ratio_1 = int(round((power_1 / total) * 10))
    ratio_1 = max(1, min(9, ratio_1))
    ratio_2 = 10 - ratio_1

    bar_1 = "🟦" * (ratio_1 // 2)
    neutral = "⬜" * max(1, 5 - (ratio_1 // 2) - (ratio_2 // 2))
    bar_2 = "🟥" * (ratio_2 // 2)
    return f"`[{bar_1}{neutral}{bar_2}]`"


def simulate_tick(
    minute: int,
    score_t1: int,
    score_t2: int,
    t1: dict[str, Any],
    t2: dict[str, Any],
    xg1_prev: float = 0.0,
    xg2_prev: float = 0.0,
    shots1_prev: int = 0,
    shots2_prev: int = 0,
    rng: random.Random | None = None,
) -> tuple[int, int, float, float, int, int, int, int, list[dict[str, Any]]]:
    """
    Advanced state machine simulating a 15-minute game interval.
    Returns:
    (score_t1, score_t2, xg1, xg2, shots1, sot1, shots2, sot2, events)
    """
    r = rng if rng is not None else random
    events: list[dict[str, Any]] = []

    t1_code = t1.get("code", t1.get("name", "T1"))
    t2_code = t2.get("code", t2.get("name", "T2"))

    # Tactical Coach adjustment at 60'
    perk1 = t1.get("perk", "")
    perk2 = t2.get("perk", "")
    boost1 = 1.0
    boost2 = 1.0

    if minute >= 60:
        if score_t1 < score_t2:
            boost1 = 1.35 if perk1 == "comeback_dna" else 1.20
            if minute == 60:
                events.append({
                    "type": "tactic", "minute": 60, "team": t1_code,
                    "text": f"👔 **HLV {t1.get('coach', 'Trưởng')} ({t1_code})**: Chỉ đạo học trò dâng cao tổng lực tấn công tìm bàn gỡ!",
                })
        elif score_t2 < score_t1:
            boost2 = 1.35 if perk2 == "comeback_dna" else 1.20
            if minute == 60:
                events.append({
                    "type": "tactic", "minute": 60, "team": t2_code,
                    "text": f"👔 **HLV {t2.get('coach', 'Trưởng')} ({t2_code})**: Tung tiền đạo vào sân, kích hoạt phương án tấn công nghẹt thở!",
                })

    # Expected xG per 15 min
    base_xg1_tick = 0.28 * (t1["att"] + 0.15) / (t1["att"] + t2["def"]) * boost1
    base_xg2_tick = 0.25 * t2["att"] / (t2["att"] + t1["def"] + 0.10) * boost2

    xg1 = round(xg1_prev + base_xg1_tick * r.uniform(0.7, 1.3), 2)
    xg2 = round(xg2_prev + base_xg2_tick * r.uniform(0.7, 1.3), 2)

    shots1 = shots1_prev + r.randint(1, 3)
    shots2 = shots2_prev + r.randint(1, 3)
    sot1 = shots1_prev + (1 if r.random() < 0.6 else 0)
    sot2 = shots2_prev + (1 if r.random() < 0.6 else 0)

    # Home team attempt
    if r.random() < base_xg1_tick:
        event_min = max(1, minute - r.randint(0, 14))
        # 8% chance of VAR review
        if r.random() < 0.08:
            events.append({
                "type": "var_overturn", "minute": event_min, "team": t1_code,
                "text": f"📺 **VAR CAN THIỆP {event_min}'**: Bàn thắng của {t1.get('emoji', '⚽')} **{t1['name']}** bị TỪ CHỐI vì lỗi việt vị trong gang tấc!",
            })
        else:
            score_t1 += 1
            sot1 += 1
            events.append({
                "type": "goal", "minute": event_min, "team": t1_code,
                "text": f"⚽ **BÀN THẮNG {event_min}'** — {t1.get('emoji', '⚽')} **{t1['name']}** ghi bàn xuất sắc! (xG: `{xg1:.2f}`)",
            })
    elif r.random() < 0.35:
        flavor = r.choice(FLAVOR_COMMENTARY).format(team=t1["name"])
        events.append({
            "type": "flavor", "minute": minute, "team": t1_code, "text": f"`{minute}'` {flavor}",
        })

    # Away team attempt
    if r.random() < base_xg2_tick:
        event_min = max(1, minute - r.randint(0, 14))
        if r.random() < 0.08:
            events.append({
                "type": "var_overturn", "minute": event_min, "team": t2_code,
                "text": f"📺 **VAR CAN THIỆP {event_min}'**: Bàn thắng của {t2.get('emoji', '⚽')} **{t2['name']}** bị TỪ CHỐI do phạm lỗi trước đó!",
            })
        else:
            score_t2 += 1
            sot2 += 1
            events.append({
                "type": "goal", "minute": event_min, "team": t2_code,
                "text": f"⚽ **BÀN THẮNG {event_min}'** — {t2.get('emoji', '⚽')} **{t2['name']}** dứt điểm tung lưới đối phương! (xG: `{xg2:.2f}`)",
            })
    elif r.random() < 0.30 and not events:
        flavor = r.choice(FLAVOR_COMMENTARY).format(team=t2["name"])
        events.append({
            "type": "flavor", "minute": minute, "team": t2_code, "text": f"`{minute}'` {flavor}",
        })

    return score_t1, score_t2, xg1, xg2, shots1, sot1, shots2, sot2, events


def calculate_cashout_value(
    stake: int,
    base_odds: float,
    outcome: str,
    minute: int,
    score_t1: int,
    score_t2: int,
) -> int:
    """
    Calculates dynamic real-time cashout value for an active bet ticket across all markets.
    Locked (returns 0) after minute 80.
    """
    if minute >= 80 or minute <= 0:
        return 0

    potential_payout = int(stake * max(1.20, base_odds))
    time_factor = (80 - minute) / 80.0
    total_goals = score_t1 + score_t2

    is_winning = False
    is_decided_won = False
    is_decided_lost = False

    if outcome in ("1", "X", "2"):
        if score_t1 > score_t2:
            current_leading = "1"
        elif score_t1 < score_t2:
            current_leading = "2"
        else:
            current_leading = "X"
        is_winning = (outcome == current_leading)

    elif outcome == "OU_OVER":
        if total_goals >= 3:
            is_decided_won = True
            is_winning = True
        elif total_goals == 2:
            is_winning = (minute < 65)
        else:
            is_winning = False

    elif outcome == "OU_UNDER":
        if total_goals >= 3:
            is_decided_lost = True
            is_winning = False
        else:
            is_winning = True

    elif outcome == "BTTS_YES":
        if score_t1 > 0 and score_t2 > 0:
            is_decided_won = True
            is_winning = True
        elif score_t1 > 0 or score_t2 > 0:
            is_winning = (minute < 65)
        else:
            is_winning = False

    elif outcome == "BTTS_NO":
        if score_t1 > 0 and score_t2 > 0:
            is_decided_lost = True
            is_winning = False
        else:
            is_winning = True

    elif outcome in ("HDP_1", "HDP_2"):
        is_winning = (outcome == "HDP_1" and score_t1 > score_t2) or (outcome == "HDP_2" and score_t2 >= score_t1)

    if is_decided_lost:
        return 0
    if is_decided_won:
        return int(potential_payout * 0.92)

    if is_winning:
        # Winning position: offer 70% to 90% of potential payout
        rate = 0.70 + (0.20 * (minute / 80.0))
        return int(potential_payout * rate)
    else:
        # Losing position: offer 15% to 35% cut-loss refund
        rate = max(0.10, 0.35 * time_factor)
        return int(stake * rate)


def evaluate_market_results(score_t1: int, score_t2: int) -> dict[str, str]:
    """Evaluates the winning outcome for all supported markets."""
    total_goals = score_t1 + score_t2
    if score_t1 > score_t2:
        res_1x2 = "1"
        res_hdp = "HDP_1"
    elif score_t1 < score_t2:
        res_1x2 = "2"
        res_hdp = "HDP_2"
    else:
        res_1x2 = "X"
        res_hdp = "HDP_2"  # Draw favors away with +0.5 handicap

    res_ou = "OU_OVER" if total_goals >= 3 else "OU_UNDER"
    res_btts = "BTTS_YES" if (score_t1 > 0 and score_t2 > 0) else "BTTS_NO"

    return {
        "1X2": res_1x2,
        "OU": res_ou,
        "BTTS": res_btts,
        "HDP": res_hdp,
    }


def calculate_hybrid_payout(
    match_pool: dict[str, int],
    winning_outcome: str,
    tickets: list[dict[str, Any]],
    rake_rate: float = 0.05,
) -> tuple[dict[int, int], int, int, int, int]:
    """
    Calculates fair Hybrid / Pari-mutuel payout.
    """
    total_pool = sum(match_pool.values())
    winning_tickets = [t for t in tickets if t["outcome"] == winning_outcome]

    if not winning_tickets or total_pool == 0:
        return {}, 0, total_pool, 0, 0

    active_outcomes_count = sum(1 for v in match_pool.values() if v > 0)
    winning_pool = match_pool.get(winning_outcome, 0)

    user_payouts: dict[int, int] = {}
    total_payout = 0
    rake_amount = 0
    rounding_to_jackpot = 0
    house_contribution = 0

    if active_outcomes_count <= 1:
        # One-sided pool guarantee
        for ticket in winning_tickets:
            uid = ticket["user_id"]
            stake = ticket["amount"]
            base_multiplier = max(1.20, ticket.get("base_odds", 1.30))
            payout = int(stake * base_multiplier)
            user_payouts[uid] = user_payouts.get(uid, 0) + payout
            total_payout += payout

        if total_payout > total_pool:
            house_contribution = total_payout - total_pool
        else:
            rake_amount = int(total_pool * rake_rate)
            rounding_to_jackpot = max(0, total_pool - total_payout - rake_amount)
    else:
        # Multi-sided pool pari-mutuel with 1.05x floor
        rake_amount = int(total_pool * rake_rate)
        distributable_pot = total_pool - rake_amount

        sum_distributed = 0
        for ticket in winning_tickets:
            uid = ticket["user_id"]
            stake = ticket["amount"]
            raw_share = int(distributable_pot * stake / winning_pool) if winning_pool > 0 else stake
            share = max(int(stake * 1.05), raw_share)
            user_payouts[uid] = user_payouts.get(uid, 0) + share
            total_payout += share
            sum_distributed += share

        if total_payout > (total_pool - rake_amount):
            house_contribution = max(0, total_payout - (total_pool - rake_amount))
            rounding_to_jackpot = 0
        else:
            rounding_to_jackpot = max(0, distributable_pot - sum_distributed)

    return user_payouts, total_payout, rake_amount, rounding_to_jackpot, house_contribution
