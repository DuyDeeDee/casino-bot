import logging
import os
import random
from typing import Any

logger = logging.getLogger(__name__)

# 4 Commentator Personas with unique speech styles
COMMENTATOR_PERSONAS: dict[str, dict[str, Any]] = {
    "biencuong": {
        "name": "Biên Cương",
        "title": "Bình luận viên Hào Sảng",
        "emoji": "🎙️",
        "style": "Hype cuồng nhiệt, dùng văn thơ, ví von cảm xúc mãnh liệt",
    },
    "tactician": {
        "name": "Quang Huy",
        "title": "Chuyên gia Chiến thuật",
        "emoji": "🧠",
        "style": "Điềm tĩnh, phân tích sơ đồ, xG, pressing và cự ly đội hình",
    },
    "troll": {
        "name": "Anh Ba Cà Khịa",
        "title": "Bình luận viên Meme",
        "emoji": "😈",
        "style": "Hài hước, châm chọc sai lầm cầu thủ, dùng từ lóng bóng đá",
    },
    "premier": {
        "name": "Peter Drury VN",
        "title": "Bình luận viên Quốc tế",
        "emoji": "⚡",
        "style": "Nhịp độ dồn dập, đậm chất Ngoại hạng Anh, kịch tính",
    },
}

# 6 AI Bettor Personas
AI_BETTOR_PERSONAS: dict[int, dict[str, Any]] = {
    -1: {
        "id": -1,
        "name": "GS. Thống Kê",
        "emoji": "📊",
        "title": "Value Bettor",
        "desc": "Cược dựa trên xác suất toán học & giá trị kỳ vọng (EV)",
        "min_bet": 500_000,
        "max_bet": 2_500_000,
        "strategy": "value",
    },
    -2: {
        "id": -2,
        "name": "Chiến Thần Tất Tay",
        "emoji": "🎰",
        "title": "High Roller",
        "desc": "Cược số tiền khủng ngẫu nhiên, thích kèo ăn to",
        "min_bet": 2_000_000,
        "max_bet": 8_000_000,
        "strategy": "degen",
    },
    -3: {
        "id": -3,
        "name": "Thợ Săn Kèo Dưới",
        "emoji": "🐺",
        "title": "Underdog Hunter",
        "desc": "Chuyên rình cửa khách hoặc hòa khi tỷ lệ ăn cao",
        "min_bet": 500_000,
        "max_bet": 1_500_000,
        "strategy": "underdog",
    },
    -4: {
        "id": -4,
        "name": "Madridista Hào Hoa",
        "emoji": "👑",
        "title": "Fan Real Madrid",
        "desc": "100% cược Real Madrid; trận khác ưu tiên đội nhà",
        "min_bet": 1_000_000,
        "max_bet": 3_000_000,
        "strategy": "fan_rma",
    },
    -5: {
        "id": -5,
        "name": "Quỷ Đỏ Lạc Quan",
        "emoji": "😈",
        "title": "Fan Man United",
        "desc": "Luôn tin MU thắng; thích cược Tài bàn thắng",
        "min_bet": 1_000_000,
        "max_bet": 3_000_000,
        "strategy": "fan_mun",
    },
    -6: {
        "id": -6,
        "name": "Thần Kèo Phong Độ",
        "emoji": "⚡",
        "title": "Momentum Sharp",
        "desc": "Dựa vào BXH và phong độ 5 trận để chọn đội bay cao",
        "min_bet": 800_000,
        "max_bet": 2_000_000,
        "strategy": "form",
    },
}


# --- COMMENTARY TEMPLATES ---

GOAL_TEMPLATES = {
    "biencuong": [
        "⚽ **VÀOOOOOOO!** Không thể tin được! {team} đã có một siêu phẩm xé toang mành lưới ở phút {minute}'! Quá cảm xúc!",
        "⚽ **BÀN THẮNG TUYỆT HẢO!** {team} biến cầu trường thành ngày hội! Tỉ số được nâng lên {s1}-{s2}!",
        "⚽ **VÀO!** Một pha phối hợp như vẽ tranh của {team}! Khung thành rung chuyển và người hâm mộ vỡ òa!",
    ],
    "tactician": [
        "⚽ **BÀN THẮNG {minute}'**: {team} khai thác triệt để khoảng trống sau lưng trung vệ. xG của tình huống này lên tới {xg:.2f}. Tỉ số hiện tại: {s1}-{s2}.",
        "⚽ **BÀN THẮNG**: Tình huống pressing tầm cao hiệu quả của {team} đã thu về quả ngọt. Một pha dàn xếp mẫu mực!",
        "⚽ **BÀN THẮNG {minute}'**: {team} chuyển đổi trạng thái thần tốc từ phòng ngự sang phản công. Hàng thủ đối phương hoàn toàn bị động.",
    ],
    "troll": [
        "⚽ **VÀO!** Hàng thủ đội bạn đang tàng hình à? {team} đệm bóng vào lưới trống dễ như ăn kẹo! {s1}-{s2} rồi nhé các con giời!",
        "⚽ **GOLAZO!** Tiền đạo {team} sút cháy lưới khiến thủ môn chỉ biết đứng nhìn và tự hỏi ý nghĩa cuộc sống!",
        "⚽ **VÀO!** Cầu thủ phòng ngự lại 'tấu hài', {team} trừng phạt ngay lập tức! Kèo này căng rồi!",
    ],
    "premier": [
        "⚽ **GOAL! IT'S IN!** {team} strike with surgical precision at {minute}'! The stadium erupts! ({s1}-{s2})",
        "⚽ **WHAT A FINISH!** Unstoppable strike from {team}! Absolute footballing poetry on display!",
        "⚽ **GOAL!** Dramatic breakthrough for {team}! The momentum shifts entirely!",
    ],
}

HALFTIME_TEMPLATES = {
    "biencuong": "⏱️ **HẾT HIỆP 1 ({s1}-{s2})**: 45 phút đầu tiên tràn ngập cảm xúc! {team_leader} đang chiếm thế thượng phong nhưng hiệp 2 hứa hẹn còn bùng nổ hơn nữa!",
    "tactician": "⏱️ **HALFTIME ANALYSIS ({s1}-{s2})**: Kiểm soát bóng {p1}% - {p2}%, xG lũy kế: {xg1:.2f} vs {xg2:.2f}. Cả hai ban huấn luyện chắc chắn sẽ có những điều chỉnh chiến thuật quan trọng trong giờ nghỉ.",
    "troll": "⏱️ **HẾT HIỆP 1 ({s1}-{s2})**: Ai đặt cửa dưới đang run bần bật, còn anh em ôm cửa trên thì chuẩn bị đếm tiền nào! Hiệp 2 xem có lật kèo được không!",
    "premier": "⏱️ **HALF-TIME RECAP ({s1}-{s2})**: A pulsating opening 45 minutes! Tactics, intensity, drama — second half is going to be electric!",
}

FULLTIME_TEMPLATES = {
    "biencuong": "🏁 **FULL TIME ({s1}-{s2})**: Trọng tài đã nổi hồi còi mãn cuộc! Một bữa tiệc bóng đá thịnh soạn! Xin chúc mừng những người chiến thắng!",
    "tactician": "🏁 **KẾT THÚC TRẬN ĐẤU ({s1}-{s2})**: Kết quả phản ánh đúng cục diện xG ({xg1:.2f} - {xg2:.2f}). {winner_name} đã thực thi chiến thuật xuất sắc hơn trong 90 phút.",
    "troll": "🏁 **HẾT GIỜ ({s1}-{s2})**: Xong phim! Chúc mừng các đại gia đã húp trọn pot, còn ai thua thì xin mời ra đê hóng gió mát cùng tôi!",
    "premier": "🏁 **FULL TIME WHISTLE ({s1}-{s2})**: It's all over! 90 minutes of sheer footballing drama concludes with a decisive {s1}-{s2} result!",
}

VAR_TEMPLATES = {
    "biencuong": "📺 **VAR ĐANG CAN THIỆP!** Trọng tài đang xem lại màn hình quay chậm... Quyết định: **{decision}**!",
    "tactician": "📺 **VAR REVIEW**: Tình huống kiểm tra công nghệ việt vị bán tự động... Phán quyết cuối cùng: **{decision}**.",
    "troll": "📺 **VAR TIME**: Trọng tài vẽ đường kẻ màu mè một hồi rồi chốt: **{decision}**! Phen này tim đập chân run!",
    "premier": "📺 **VAR DRAMA**: Crucial technology check underway... The official verdict: **{decision}**!",
}


# --- COMMENTARY GENERATION FUNCTIONS ---

def get_random_commentator() -> str:
    return random.choice(list(COMMENTATOR_PERSONAS.keys()))


def generate_goal_commentary(
    commentator_key: str,
    team_name: str,
    minute: int,
    s1: int,
    s2: int,
    xg: float = 0.45,
) -> str:
    c_key = commentator_key if commentator_key in GOAL_TEMPLATES else "tactician"
    tpl = random.choice(GOAL_TEMPLATES[c_key])
    return tpl.format(team=team_name, minute=minute, s1=s1, s2=s2, xg=xg)


def generate_halftime_commentary(
    commentator_key: str,
    s1: int,
    s2: int,
    t1_name: str,
    t2_name: str,
    p1: int = 50,
    p2: int = 50,
    xg1: float = 0.8,
    xg2: float = 0.8,
) -> str:
    c_key = commentator_key if commentator_key in HALFTIME_TEMPLATES else "tactician"
    tpl = HALFTIME_TEMPLATES[c_key]
    team_leader = t1_name if s1 > s2 else (t2_name if s2 > s1 else "Hai đội giằng co")
    return tpl.format(s1=s1, s2=s2, team_leader=team_leader, p1=p1, p2=p2, xg1=xg1, xg2=xg2)


def generate_fulltime_commentary(
    commentator_key: str,
    s1: int,
    s2: int,
    t1_name: str,
    t2_name: str,
    xg1: float = 1.5,
    xg2: float = 1.2,
) -> str:
    c_key = commentator_key if commentator_key in FULLTIME_TEMPLATES else "tactician"
    tpl = FULLTIME_TEMPLATES[c_key]
    winner_name = t1_name if s1 > s2 else (t2_name if s2 > s1 else "Kết quả Hòa")
    return tpl.format(s1=s1, s2=s2, winner_name=winner_name, xg1=xg1, xg2=xg2)


def generate_var_commentary(commentator_key: str, decision: str) -> str:
    c_key = commentator_key if commentator_key in VAR_TEMPLATES else "tactician"
    tpl = VAR_TEMPLATES[c_key]
    return tpl.format(decision=decision)


# --- AI BETTOR DECISION LOGIC ---

def decide_ai_bet(
    ai_id: int,
    match: dict[str, Any],
    base_odds: dict[str, float],
    table: list[dict[str, Any]] | None = None,
) -> tuple[str, int, str]:
    """
    Simulates an AI persona's betting decision.
    Returns: (outcome, amount, quote)
    """
    persona = AI_BETTOR_PERSONAS.get(ai_id, AI_BETTOR_PERSONAS[-1])
    strat = persona["strategy"]
    t1, t2 = match["t1"], match["t2"]

    # Choose stake
    amount = random.randint(persona["min_bet"] // 100_000, persona["max_bet"] // 100_000) * 100_000

    if strat == "fan_rma":
        if t1 == "RMA":
            return "1", amount, "Hala Madrid! Hoàng gia trên sân nhà không có đối thủ!"
        elif t2 == "RMA":
            return "2", amount, "Điểm tựa đẳng cấp C1, Real Madrid sẽ giành 3 điểm sân khách!"
        else:
            return "1", amount, "Trận này không có Real, tôi tin đội chủ nhà sẽ làm chủ thế trận."

    elif strat == "fan_mun":
        if t1 == "MUN":
            return "1", amount, "Trái tim tôi luôn hướng về Quỷ Đỏ! Trận này chắc chắn thắng!"
        elif t2 == "MUN":
            return "2", amount, "Dù đá sân khách nhưng MU sẽ tạo nên bất ngờ lớn!"
        else:
            choice = random.choice(["1", "X", "2"])
            return choice, amount, "Trận cầu mở, tôi đặt niềm tin vào cửa có khả năng bùng nổ bàn thắng."

    elif strat == "underdog":
        # Look for outcome with highest odds
        max_outcome = max(base_odds.keys(), key=lambda k: base_odds[k])
        return max_outcome, amount, f"Kèo cửa `{max_outcome}` (x{base_odds[max_outcome]:.2f}) quá thơm để bỏ qua! Săn lùng kỳ tích!"

    elif strat == "degen":
        choice = random.choice(["1", "X", "2"])
        high_amount = max(amount, persona["min_bet"] * 2)
        return choice, high_amount, f"Liều ăn nhiều! Tất tay vào cửa `{choice}`, tối nay đếm tiền mỏi tay!"

    elif strat == "form":
        # If standings table available, find higher ranked team
        if table:
            t1_rank = next((i for i, r in enumerate(table) if r["team_code"] == t1), 10)
            t2_rank = next((i for i, r in enumerate(table) if r["team_code"] == t2), 10)
            if t1_rank < t2_rank:
                return "1", amount, f"{t1} đang có vị trí và phong độ cao hơn {t2} trên BXH."
            elif t2_rank < t1_rank:
                return "2", amount, f"{t2} đang xếp trên {t1}, cơ hội chiến thắng rất rõ ràng."
        choice = "1" if base_odds.get("1", 2.0) <= base_odds.get("2", 2.0) else "2"
        return choice, amount, "Đội bóng phong độ ổn định hơn sẽ giành chiến thắng."

    else:
        # Default: Value Analyst - picks the mathematically lowest odds / highest prob or fair value
        best_choice = min(base_odds.keys(), key=lambda k: base_odds[k])
        return best_choice, amount, f"Mô hình xG và Poisson dự báo cửa `{best_choice}` có xác suất cao nhất."


def generate_ai_post_match_reaction(
    ai_id: int,
    won: bool,
    result: str,
    stake: int,
    payout: int,
) -> str:
    """Generates post-match trash talk / celebratory quote from AI Bettor."""
    persona = AI_BETTOR_PERSONAS.get(ai_id, AI_BETTOR_PERSONAS[-1])
    name = f"{persona['emoji']} **{persona['name']}**"

    if won:
        win_quotes = [
            f"{name}: *'Đã bảo rồi mà không nghe! Húp trọn `{payout:,} VND` nhẹ nhàng như đẩy xe hàng!'*",
            f"{name}: *'Phân tích chuẩn chỉ không lệch 1 ly! Thắng lớn `+{payout-stake:,} VND`!'*",
            f"{name}: *'Gáy lên anh em ơi! Cửa `{result}` uy tín số 1!'*",
        ]
        return random.choice(win_quotes)
    else:
        lose_quotes = [
            f"{name}: *'Trọng tài bắt thiên vị quá rõ! Quả đấy mà không vào thì chịu rồi... Lỗ `{stake:,} VND`!'*",
            f"{name}: *'Bóng đá đúng là môn thể thao nghiệt ngã... Thua keo này ta bày keo khác!'*",
            f"{name}: *'Hàng thủ đá như mơ ngủ, hỏng hết kế hoạch làm giàu của tôi!'*",
        ]
        return random.choice(lose_quotes)
