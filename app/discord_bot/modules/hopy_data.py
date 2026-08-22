# coding: utf-8
"""
Ngân hàng 100 câu hỏi và công cụ chuẩn hóa chuỗi cho minigame HỢP Ý (Tâm Đầu Ý Hợp)
Bao gồm:
- 50 câu DỄ (easy) - Đáp án dễ hội tụ
- 50 câu KHÓ (hard) - Đáp án dễ phân tán, thử thách sự thấu hiểu
"""
import re
import unicodedata
from typing import Optional, Dict, List

def normalize_answer(text: str) -> str:
    """
    Chuẩn hóa câu trả lời:
    - Chuyển về chữ thường (lowercase)
    - Chuẩn hóa Unicode (NFC)
    - Loại bỏ dấu câu thừa, ký tự đặc biệt
    - Giữ lại chữ cái tiếng Việt có dấu, chữ số và khoảng trắng
    - Rút gọn nhiều khoảng trắng thành 1 khoảng trắng
    """
    if not text:
        return ""
    text = unicodedata.normalize("NFC", text.strip().lower())
    text = re.sub(r"[!?,.:;\"'`~@#$%^&*()_\-+=\[\]{}|<>/\\—–]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def resolve_canonical_key(normalized_ans: str, synonyms: Optional[Dict[str, List[str]]] = None) -> str:
    """
    Nếu câu hỏi có bảng từ đồng nghĩa (synonyms), tìm key chuẩn hóa.
    Nếu không có hoặc không khớp, trả về chính chuỗi đã chuẩn hóa.
    """
    if not normalized_ans:
        return ""
    if not synonyms:
        return normalized_ans

    for canonical, variants in synonyms.items():
        can_norm = normalize_answer(canonical)
        if normalized_ans == can_norm:
            return can_norm
        for v in variants:
            if normalized_ans == normalize_answer(v):
                return can_norm

    return normalized_ans


QUESTIONS: List[Dict] = [
    # =========================================================================
    # 🟢 DỄ — 50 CÂU (ĐÁP ÁN DỄ HỘI TỤ)
    # =========================================================================
    {
        "id": "e_01",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật nuôi phổ biến nhất?",
        "synonyms": {
            "chó": ["cún", "chó con", "cún con", "dog", "gâu gâu"],
            "mèo": ["mèo con", "cat", "meo meo", "hoàng thượng"],
            "cá cảnh": ["cá vàng", "cá"],
            "chim cảnh": ["chim"],
            "chuột hamster": ["hamster", "chuột"]
        }
    },
    {
        "id": "e_02",
        "difficulty": "easy",
        "category": "Thiên Nhiên",
        "question": "Màu sắc của bầu trời?",
        "synonyms": {
            "xanh dương": ["xanh da trời", "xanh biếc", "màu xanh dương", "xanh lam", "blue", "màu xanh"],
            "xanh lơ": ["xanh nhạt"],
            "xám": ["màu xám", "u ám"]
        }
    },
    {
        "id": "e_03",
        "difficulty": "easy",
        "category": "Trái Cây",
        "question": "Trái cây có vị chua?",
        "synonyms": {
            "chanh": ["quả chanh", "trái chanh", "chanh chua"],
            "xoài chua": ["xoài xanh", "xoài"],
            "cóc": ["trái cóc", "quả cóc"],
            "me": ["trái me", "quả me", "me chua"],
            "khế": ["quả khế", "khế chua"],
            "bưởi": ["quả bưởi"]
        }
    },
    {
        "id": "e_04",
        "difficulty": "easy",
        "category": "Đồ Uống",
        "question": "Đồ uống giải khát mùa hè?",
        "synonyms": {
            "nước mía": ["mía đá", "ly nước mía"],
            "trà đá": ["nước trà đá", "trà"],
            "nước dừa": ["dừa tươi", "trái dừa"],
            "nước chanh": ["chanh đá", "nước chanh đường"],
            "trà chanh": ["trà chanh giã tay"],
            "trà tắc": ["trà quất"],
            "nước ngọt": ["coca", "pepsi", "nước ngọt có ga"],
            "bia": ["bia hơi"]
        }
    },
    {
        "id": "e_05",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Món ăn sáng phổ biến ở Việt Nam?",
        "synonyms": {
            "phở": ["phở bò", "phở gà", "ăn phở"],
            "bánh mì": ["bánh mỳ", "bánh mì thịt", "bánh mì pate"],
            "cơm tấm": ["cơm sườn", "cơm tấm sườn"],
            "xôi": ["xôi xéo", "xôi gà", "xôi mặn"],
            "bún bò": ["bún bò huế"],
            "bánh cuốn": ["bánh ướt"]
        }
    },
    {
        "id": "e_06",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật kêu 'gâu gâu'?",
        "synonyms": {
            "chó": ["con chó", "cún", "chó con", "dog", "cún con"]
        }
    },
    {
        "id": "e_07",
        "difficulty": "easy",
        "category": "Thời Tiết",
        "question": "Mùa nóng nhất trong năm?",
        "synonyms": {
            "mùa hè": ["mùa hạ", "hè", "mùa nóng"]
        }
    },
    {
        "id": "e_08",
        "difficulty": "easy",
        "category": "Đời Sống",
        "question": "Phương tiện đi học phổ biến?",
        "synonyms": {
            "xe đạp": ["xe đạp điện", "xe điện"],
            "xe máy": ["xe gắn máy", "xe honda"],
            "xe buýt": ["xe bus", "bus"],
            "đi bộ": ["bộ"]
        }
    },
    {
        "id": "e_09",
        "difficulty": "easy",
        "category": "Ngày Lễ",
        "question": "Loại bánh ăn vào dịp Trung Thu?",
        "synonyms": {
            "bánh trung thu": ["bánh nướng", "bánh dẻo", "bánh nướng bánh dẻo", "bánh thập cẩm", "bánh dẻo bánh nướng"]
        }
    },
    {
        "id": "e_10",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật biết bay?",
        "synonyms": {
            "chim": ["chim bồ câu", "con chim", "chim sẻ", "đại bàng"],
            "bướm": ["con bướm", "bươm bướm"],
            "dơi": ["con dơi"],
            "ong": ["con ong"]
        }
    },
    {
        "id": "e_11",
        "difficulty": "easy",
        "category": "Thiên Nhiên",
        "question": "Màu của lá cây?",
        "synonyms": {
            "xanh lá": ["xanh lá cây", "màu xanh lá", "màu xanh", "green", "xanh lục"]
        }
    },
    {
        "id": "e_12",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Món ăn nhanh phổ biến?",
        "synonyms": {
            "gà rán": ["kfc", "jollibee", "lotteria", "gà chiên"],
            "khoai tây chiên": ["khoai chiên", "french fries"],
            "pizza": ["bánh pizza"],
            "hamburger": ["burger", "bánh burger"],
            "mì tôm": ["mì gói", "mì ăn liền"]
        }
    },
    {
        "id": "e_13",
        "difficulty": "easy",
        "category": "Đồ Vật",
        "question": "Đồ vật dùng để viết?",
        "synonyms": {
            "bút": ["bút bi", "cây bút", "bút mực", "viết", "cây viết", "pen"],
            "bút chì": ["cây bút chì", "pencil"],
            "phấn": ["viên phấn"]
        }
    },
    {
        "id": "e_14",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật sống dưới nước?",
        "synonyms": {
            "cá": ["con cá", "cá mập", "cá heo", "cá voi", "cá cảnh"],
            "tôm": ["con tôm"],
            "cua": ["con cua"],
            "mực": ["con mực"],
            "bạch tuộc": ["con bạch tuộc"],
            "rùa": ["rùa biển"]
        }
    },
    {
        "id": "e_15",
        "difficulty": "easy",
        "category": "Ngày Lễ",
        "question": "Ngày lễ lớn nhất trong năm?",
        "synonyms": {
            "tết": ["tết nguyên đán", "tết âm lịch", "tết cổ truyền", "năm mới", "tết tây"],
            "giáng sinh": ["noel", "lễ noel", "christmas"],
            "quốc khánh": ["2 9", "ngày 2 9"]
        }
    },
    {
        "id": "e_16",
        "difficulty": "easy",
        "category": "Trái Cây",
        "question": "Loại trái cây màu vàng?",
        "synonyms": {
            "chuối": ["quả chuối", "trái chuối", "banana"],
            "xoài": ["quả xoài", "trái xoài", "xoài chín"],
            "dứa": ["quả dứa", "trái thơm", "thơm", "khóm"],
            "chanh vàng": ["chanh"],
            "cam": ["quả cam"],
            "đu đủ": ["đu đủ chín"]
        }
    },
    {
        "id": "e_17",
        "difficulty": "easy",
        "category": "Đời Sống",
        "question": "Vật dụng đội trên đầu khi trời nắng?",
        "synonyms": {
            "mũ": ["mũ lưỡi trai", "nón", "nón lá", "mũ rộng vành", "nón kết", "cái mũ", "cái nón"]
        }
    },
    {
        "id": "e_18",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật kêu 'meo meo'?",
        "synonyms": {
            "mèo": ["con mèo", "mèo con", "cat", "hoàng thượng"]
        }
    },
    {
        "id": "e_19",
        "difficulty": "easy",
        "category": "Đồ Uống",
        "question": "Thức uống buổi sáng phổ biến?",
        "synonyms": {
            "cà phê": ["cafe", "cà phê sữa", "cf", "coffee", "bạc xỉu"],
            "sữa": ["sữa tươi", "sữa nóng", "sữa bò"],
            "trà": ["trà xanh", "trà nóng", "nước chè"],
            "nước ấm": ["nước lọc", "nước"]
        }
    },
    {
        "id": "e_20",
        "difficulty": "easy",
        "category": "Giáo Dục",
        "question": "Địa điểm học tập?",
        "synonyms": {
            "trường học": ["trường", "lớp học", "lớp", "ngôi trường"],
            "thư viện": ["phòng đọc"],
            "bàn học": ["phòng học", "ở nhà"],
            "quán cà phê": ["quán cafe"]
        }
    },
    {
        "id": "e_21",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Món ăn có vị cay?",
        "synonyms": {
            "mì cay": ["mì cay 7 cấp độ", "mì koreno"],
            "lẩu thái": ["lẩu cay"],
            "bún bò": ["bún bò huế"],
            "kim chi": ["kimchi"],
            "ớt": ["trái ớt"]
        }
    },
    {
        "id": "e_22",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật to lớn nhất trên cạn?",
        "synonyms": {
            "voi": ["con voi", "chú voi", "elephant"]
        }
    },
    {
        "id": "e_23",
        "difficulty": "easy",
        "category": "Thời Tiết",
        "question": "Mùa có lá rụng?",
        "synonyms": {
            "mùa thu": ["thu", "mùa lá rụng", "autumn", "fall"]
        }
    },
    {
        "id": "e_24",
        "difficulty": "easy",
        "category": "Đồ Chơi",
        "question": "Đồ chơi trẻ em phổ biến?",
        "synonyms": {
            "gấu bông": ["thú bông", "gấu"],
            "lego": ["xếp hình", "đồ chơi lego"],
            "ô tô đồ chơi": ["xe ô tô", "xe điều khiển", "xe hơi"],
            "búp bê": ["barbie"],
            "bóng": ["quả bóng"]
        }
    },
    {
        "id": "e_25",
        "difficulty": "easy",
        "category": "Đồ Vật",
        "question": "Vật dụng để xem giờ?",
        "synonyms": {
            "đồng hồ": ["đồng hồ đeo tay", "đồng hồ treo tường", "cái đồng hồ", "watch", "clock"],
            "điện thoại": ["smartphone", "đt"]
        }
    },
    {
        "id": "e_26",
        "difficulty": "easy",
        "category": "Thực Phẩm",
        "question": "Loại rau xanh phổ biến?",
        "synonyms": {
            "rau muống": ["rau muống luộc", "rau muống xào"],
            "rau cải": ["cải thìa", "cải ngọt", "bắp cải"],
            "xà lách": ["rau sống", "rau diếp"],
            "rau ngót": ["bồ ngót"]
        }
    },
    {
        "id": "e_27",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật có vằn đen trắng?",
        "synonyms": {
            "ngựa vằn": ["con ngựa vằn", "zebra"]
        }
    },
    {
        "id": "e_28",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Món tráng miệng phổ biến?",
        "synonyms": {
            "kem": ["ăn kem", "ly kem", "cây kem", "ice cream"],
            "chè": ["chè thái", "chè bưởi", "ly chè"],
            "trái cây": ["hoa quả", "dưa hấu"],
            "sữa chua": ["yaourt", "sữa chua nếp cẩm"],
            "bánh flan": ["flan", "caramel", "bánh caramen"]
        }
    },
    {
        "id": "e_29",
        "difficulty": "easy",
        "category": "Âm Nhạc",
        "question": "Nhạc cụ có dây?",
        "synonyms": {
            "guitar": ["đàn guitar", "ghi ta", "đàn ghi ta"],
            "violin": ["đàn violin", "đàn vĩ cầm", "vĩ cầm"],
            "đàn tranh": ["đàn bầu", "đàn đáy"],
            "piano": ["đàn piano", "đàn dương cầm", "dương cầm"],
            "ukulele": ["đàn ukulele"]
        }
    },
    {
        "id": "e_30",
        "difficulty": "easy",
        "category": "Công Nghệ",
        "question": "Đồ vật dùng để nghe nhạc?",
        "synonyms": {
            "tai nghe": ["headphone", "earphone", "airpod", "tai nghe bluetooth"],
            "loa": ["loa bluetooth", "cái loa", "loa thùng"],
            "điện thoại": ["smartphone", "máy nghe nhạc", "mp3"]
        }
    },
    {
        "id": "e_31",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật sống trong rừng?",
        "synonyms": {
            "hổ": ["con hổ", "cọp", "chúa sơn lâm", "con cọp"],
            "sư tử": ["con sư tử", "lion"],
            "khỉ": ["con khỉ"],
            "gấu": ["con gấu"],
            "hươu": ["con hươu", "nai"],
            "voi": ["con voi"]
        }
    },
    {
        "id": "e_32",
        "difficulty": "easy",
        "category": "Thời Tiết",
        "question": "Thời tiết mùa đông?",
        "synonyms": {
            "lạnh": ["lạnh giá", "rét", "giá rét", "buốt", "lạnh buốt", "thời tiết lạnh"],
            "có tuyết": ["tuyết rơi", "tuyết"],
            "sương mù": ["sương"]
        }
    },
    {
        "id": "e_33",
        "difficulty": "easy",
        "category": "Trái Cây",
        "question": "Trái cây có gai bên ngoài?",
        "synonyms": {
            "sầu riêng": ["trái sầu riêng", "quả sầu riêng", "durian"],
            "mít": ["trái mít", "quả mít"],
            "chôm chôm": ["trái chôm chôm"],
            "dứa": ["quả dứa", "trái thơm"]
        }
    },
    {
        "id": "e_34",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Vật nuôi trong nhà phổ biến?",
        "synonyms": {
            "chó": ["cún", "con chó", "dog"],
            "mèo": ["con mèo", "mèo con", "cat"],
            "chim": ["chim cảnh"],
            "cá": ["cá cảnh", "cá vàng"]
        }
    },
    {
        "id": "e_35",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Đồ ăn vặt phổ biến ở Việt Nam?",
        "synonyms": {
            "bánh tráng trộn": ["bánh tráng", "bánh tráng nướng", "bánh tráng cuộn"],
            "nem chua rán": ["nem chua", "nem rán"],
            "cá viên chiên": ["xiên bẩn", "xiên que", "đồ viên chiên"],
            "chè": ["ly chè"],
            "trà sữa": ["trà sữa trân châu"],
            "khoai tây lắc": ["khoai lang kén"]
        }
    },
    {
        "id": "e_36",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật kêu 'ò ó o'?",
        "synonyms": {
            "gà trống": ["con gà", "gà", "chú gà trống", "con gà trống"]
        }
    },
    {
        "id": "e_37",
        "difficulty": "easy",
        "category": "Loài Hoa",
        "question": "Loại hoa tượng trưng cho tình yêu?",
        "synonyms": {
            "hoa hồng": ["hồng", "rose", "hoa hồng đỏ", "bông hồng"]
        }
    },
    {
        "id": "e_38",
        "difficulty": "easy",
        "category": "Đồ Gia Dụng",
        "question": "Vật dụng để nấu cơm?",
        "synonyms": {
            "nồi cơm điện": ["nồi cơm", "nồi", "cái nồi cơm điện"]
        }
    },
    {
        "id": "e_39",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật biết leo trèo giỏi?",
        "synonyms": {
            "khỉ": ["con khỉ", "vượn", "chú khỉ"],
            "mèo": ["con mèo"],
            "sóc": ["con sóc"]
        }
    },
    {
        "id": "e_40",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Món ăn ngày Tết?",
        "synonyms": {
            "bánh chưng": ["bánh trưng"],
            "bánh tét": ["đòn bánh tét"],
            "thịt kho hột vịt": ["thịt kho tàu", "thịt kho trứng", "thịt kho"],
            "dưa hành": ["củ kiệu", "hành muối"],
            "nem rán": ["chả giò"]
        }
    },
    {
        "id": "e_41",
        "difficulty": "easy",
        "category": "Đồ Vật",
        "question": "Đồ vật dùng để chiếu sáng?",
        "synonyms": {
            "đèn": ["bóng đèn", "đèn pin", "đèn điện", "cái đèn", "đèn led"],
            "nến": ["cây nến", "đèn cầy"],
            "mặt trời": ["lửa"]
        }
    },
    {
        "id": "e_42",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật có cổ dài nhất?",
        "synonyms": {
            "hươu cao cổ": ["con hươu cao cổ", "hươu", "giraffe"]
        }
    },
    {
        "id": "e_43",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Loại kem phổ biến?",
        "synonyms": {
            "kem socola": ["socola", "chocolate"],
            "kem vani": ["vani", "vanilla"],
            "kem dâu": ["dâu tây", "dâu"],
            "kem matcha": ["trà xanh", "kem trà xanh"],
            "kem ốc quế": ["kem que"]
        }
    },
    {
        "id": "e_44",
        "difficulty": "easy",
        "category": "Giao Thông",
        "question": "Phương tiện di chuyển trên biển?",
        "synonyms": {
            "thuyền": ["tàu", "tàu thủy", "con tàu", "du thuyền", "ca nô", "cano", "phà", "con thuyền"]
        }
    },
    {
        "id": "e_45",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật đại diện cho sự khôn ngoan?",
        "synonyms": {
            "cú mèo": ["con cú", "chim cú", "cú", "chim cú mèo"],
            "cáo": ["con cáo", "hồ ly"],
            "cá heo": ["khỉ"]
        }
    },
    {
        "id": "e_46",
        "difficulty": "easy",
        "category": "Đồ Gia Dụng",
        "question": "Vật dụng để lau nhà?",
        "synonyms": {
            "cây lau nhà": ["chổi lau nhà", "giẻ lau", "cây lau", "khăn lau", "robot hút bụi"]
        }
    },
    {
        "id": "e_47",
        "difficulty": "easy",
        "category": "Ẩm Thực",
        "question": "Món ăn có nước lèo?",
        "synonyms": {
            "phở": ["phở bò", "phở gà"],
            "bún bò": ["bún bò huế"],
            "hủ tiếu": ["hủ tiếu nam vang"],
            "bún riêu": ["bún riêu cua"],
            "mì": ["mì quảng", "mì ramen"],
            "bánh canh": ["lẩu"]
        }
    },
    {
        "id": "e_48",
        "difficulty": "easy",
        "category": "Động Vật",
        "question": "Con vật sống ở Nam Cực?",
        "synonyms": {
            "chim cánh cụt": ["cánh cụt", "penguin"],
            "gấu bắc cực": ["hải cẩu", "chó biển"]
        }
    },
    {
        "id": "e_49",
        "difficulty": "easy",
        "category": "Trái Cây",
        "question": "Trái cây có vỏ màu đỏ?",
        "synonyms": {
            "táo": ["quả táo", "trái táo", "táo đỏ", "apple"],
            "dâu tây": ["trái dâu", "quả dâu"],
            "dưa hấu": ["trái dưa hấu"],
            "vải": ["quả vải", "trái vải"],
            "mận": ["quả mận", "trái mận"],
            "chôm chôm": ["trái chôm chôm"],
            "lựu": ["quả lựu"]
        }
    },
    {
        "id": "e_50",
        "difficulty": "easy",
        "category": "Đời Sống",
        "question": "Đồ vật không thể thiếu khi đi mưa?",
        "synonyms": {
            "áo mưa": ["bộ áo mưa", "áo đi mưa", "áo cánh dơi"],
            "ô": ["dù", "cái ô", "cây dù", "cây ô"]
        }
    },

    # =========================================================================
    # 🔴 KHÓ — 50 CÂU (ĐÁP ÁN DỄ PHÂN TÁN, THỬ THÁCH)
    # =========================================================================
    {
        "id": "h_01",
        "difficulty": "hard",
        "category": "Trí Tưởng Tượng",
        "question": "Nếu được một điều ước, bạn ước gì?",
        "synonyms": {
            "nhiều tiền": ["giàu có", "tiền", "thật nhiều tiền", "tỷ phú", "tiền bạc", "vô số tiền"],
            "sức khỏe": ["khoẻ mạnh", "khỏe mạnh", "bình an", "không bệnh tật"],
            "hạnh phúc": ["vui vẻ", "an nhiên", "bình yên"],
            "bất tử": ["sống lâu", "trường sinh bất lão", "sống mãi"],
            "thêm điều ước": ["vô hạn điều ước", "thêm 100 điều ước", "ước thêm"]
        }
    },
    {
        "id": "h_02",
        "difficulty": "hard",
        "category": "Nghề Nghiệp",
        "question": "Nghề nghiệp bạn ghét nhất?",
        "synonyms": {
            "bán hàng đa cấp": ["đa cấp", "lừa đảo"],
            "công an": ["cảnh sát giao thông", "cảnh sát", "csgt"],
            "thu hồi nợ": ["đòi nợ", "đòi nợ thuê"],
            "tele sale": ["telesale", "nhân viên telesale", "gọi điện chào hàng"],
            "lao công": ["quét rác", "dọn rác"],
            "bác sĩ": ["nha sĩ"],
            "giáo viên": ["thầy giáo"]
        }
    },
    {
        "id": "h_03",
        "difficulty": "hard",
        "category": "Âm Nhạc",
        "question": "Nhạc cụ bạn muốn học?",
        "synonyms": {
            "piano": ["đàn piano", "đàn dương cầm", "dương cầm"],
            "guitar": ["đàn guitar", "ghi ta", "đàn ghi ta"],
            "trống": ["bộ trống", "đánh trống", "drums"],
            "violin": ["đàn vĩ cầm", "vĩ cầm", "đàn violin"],
            "sáo": ["thổi sáo", "sáo trúc"],
            "ukulele": ["đàn ukulele"]
        }
    },
    {
        "id": "h_04",
        "difficulty": "hard",
        "category": "Tâm Lý",
        "question": "Nỗi sợ lớn nhất của bạn là gì?",
        "synonyms": {
            "sợ ma": ["ma", "quỷ", "con ma"],
            "sợ chết": ["cái chết", "chết"],
            "sợ gián": ["con gián", "gián bay"],
            "sợ rắn": ["con rắn"],
            "sợ độ cao": ["độ cao"],
            "sợ nghèo": ["hết tiền", "nghèo khó", "thiếu tiền"],
            "sợ cô đơn": ["cô đơn", "bị bỏ rơi"],
            "sợ bóng tối": ["bóng tối"]
        }
    },
    {
        "id": "h_05",
        "difficulty": "hard",
        "category": "Trí Tưởng Tượng",
        "question": "Siêu năng lực bạn muốn có?",
        "synonyms": {
            "tàng hình": ["vô hình", "biến mất"],
            "dịch chuyển tức thời": ["teleport", "dịch chuyển", "bay đến mọi nơi"],
            "bay": ["biết bay", "khả năng bay"],
            "đọc suy nghĩ": ["đọc tâm trí", "thao túng tâm lý", "thần giao cách cảm"],
            "quay ngược thời gian": ["du hành thời gian", "ngưng đọng thời gian", "dừng thời gian", "kiểm soát thời gian"],
            "bất tử": ["sống mãi"]
        }
    },
    {
        "id": "h_06",
        "difficulty": "hard",
        "category": "Du Lịch",
        "question": "Nơi bạn muốn đi du lịch nhất?",
        "synonyms": {
            "nhật bản": ["japan", "nhật", "tokyo"],
            "hàn quốc": ["korea", "hàn", "seoul"],
            "đà lạt": ["da lat"],
            "phú quốc": ["phu quoc"],
            "châu âu": ["pháp", "paris", "anh", "thụy sĩ"],
            "mỹ": ["usa", "hoa kỳ"],
            "thái lan": ["thailand", "bangkok"]
        }
    },
    {
        "id": "h_07",
        "difficulty": "hard",
        "category": "Đời Sống",
        "question": "Điều khiến bạn mất ngủ?",
        "synonyms": {
            "lướt điện thoại": ["dùng điện thoại", "chơi game", "xem tiktok", "xem phim"],
            "suy nghĩ linh tinh": ["overthinking", "nghĩ lung tung", "lo lắng", "stress", "áp lực"],
            "uống cà phê": ["cà phê", "cafe", "uống trà"],
            "nóng": ["nóng nực", "muỗi"],
            "tiếng ồn": ["ồn ào"],
            "nhớ người yêu": ["thất tình", "tương tư"]
        }
    },
    {
        "id": "h_08",
        "difficulty": "hard",
        "category": "Giao Tiếp",
        "question": "Từ bạn dùng nhiều nhất khi nhắn tin?",
        "synonyms": {
            "ok": ["oke", "oki", "uk", "uh", "ừ", "ukm"],
            "haha": ["hehe", "kkk", "kiki", "hihi", "cười"],
            "vcl": ["vl", "vcll", "vlon"],
            "clgt": ["cái gì", "gì vậy", "sao"],
            "dạ": ["vâng"],
            "ơi": ["alo", "ê"]
        }
    },
    {
        "id": "h_09",
        "difficulty": "hard",
        "category": "Sinh Tồn",
        "question": "Thứ bạn sẽ mang theo nếu lạc trên đảo hoang?",
        "synonyms": {
            "dao": ["con dao", "dao găm", "rựa"],
            "bật lửa": ["hộp quẹt", "hạt quẹt", "diêm", "lửa"],
            "nước": ["nước ngọt", "bình nước", "nước uống"],
            "thuyền": ["cano", "bè"],
            "điện thoại": ["smartphone"],
            "lương khô": ["đồ ăn", "thức ăn"]
        }
    },
    {
        "id": "h_10",
        "difficulty": "hard",
        "category": "Cảm Xúc",
        "question": "Điều bạn hối tiếc nhất?",
        "synonyms": {
            "không học chăm": ["bỏ học", "chểnh mảng học hành", "không học bài"],
            "bỏ lỡ tình yêu": ["không tỏ tình", "chia tay người yêu", "đánh mất người yêu", "bỏ lỡ người ấy"],
            "tiêu hoang": ["mất tiền", "không tiết kiệm"],
            "cãi lời bố mẹ": ["làm buồn lòng cha mẹ", "cãi bố mẹ"],
            "chọn sai ngành": ["chọn sai trường", "chọn sai nghề"]
        }
    },
    {
        "id": "h_11",
        "difficulty": "hard",
        "category": "Giao Tiếp",
        "question": "Câu nói bạn ghét nghe nhất?",
        "synonyms": {
            "tùy": ["sao cũng được", "sao chả được"],
            "bao giờ lấy chồng": ["bao giờ cưới", "bao giờ lấy vợ", "có người yêu chưa"],
            "con nhà người ta": ["nhìn con nhà người ta xem"],
            "đã bảo rồi mà": ["ai bảo không nghe"],
            "mượn tiền": ["cho vay tiền"],
            "chia tay đi": ["chúng ta không hợp"]
        }
    },
    {
        "id": "h_12",
        "difficulty": "hard",
        "category": "Tính Cách",
        "question": "Con vật đại diện cho tính cách bạn?",
        "synonyms": {
            "mèo": ["con mèo", "lười như mèo", "chảnh"],
            "chó": ["con chó", "trung thành", "cún"],
            "lợn": ["con heo", "heo", "ăn ngủ"],
            "hổ": ["con hổ", "cọp", "mạnh mẽ"],
            "rùa": ["con rùa", "chậm chạp"],
            "cáo": ["ranh mãnh"],
            "đại bàng": ["tự do"]
        }
    },
    {
        "id": "h_13",
        "difficulty": "hard",
        "category": "Thói Quen",
        "question": "Thói quen xấu bạn muốn bỏ?",
        "synonyms": {
            "thức khuya": ["ngủ muộn", "cú đêm", "ngủ trễ"],
            "trì hoãn": ["lười biếng", "lười", "nước đến chân mới nhảy"],
            "lướt điện thoại": ["nghiện điện thoại", "dùng đt nhiều"],
            "tiêu tiền": ["hoang phí", "mua sắm linh tinh"],
            "hút thuốc": ["uống rượu"],
            "nóng tính": ["cáu gắt"]
        }
    },
    {
        "id": "h_14",
        "difficulty": "hard",
        "category": "Kỹ Năng",
        "question": "Kỹ năng bạn muốn thành thạo?",
        "synonyms": {
            "tiếng anh": ["ngoại ngữ", "giao tiếp tiếng anh", "bắn tiếng anh"],
            "kiếm tiền": ["kinh doanh", "đầu tư", "làm giàu"],
            "nấu ăn": ["nấu ăn ngon", "làm bánh"],
            "giao tiếp": ["thuyết trình", "ăn nói"],
            "lập trình": ["code", "coding"],
            "lái xe": ["lái ô tô"]
        }
    },
    {
        "id": "h_15",
        "difficulty": "hard",
        "category": "Kỷ Niệm",
        "question": "Món quà ý nghĩa nhất bạn từng nhận?",
        "synonyms": {
            "tiền": ["tiền mặt", "phong bao lì xì", "ting ting"],
            "điện thoại": ["iphone", "smartphone"],
            "bức thư": ["thiệp chúc mừng", "thư tay"],
            "đồng hồ": ["cái đồng hồ"],
            "sách": ["quyển sách"],
            "hoa": ["bó hoa"],
            "lời chúc": ["sự hiện diện"]
        }
    },
    {
        "id": "h_16",
        "difficulty": "hard",
        "category": "Tính Cách",
        "question": "Điều làm bạn khó chịu nhất ở người khác?",
        "synonyms": {
            "giả tạo": ["hai mặt", "thảo mai", "dối trá", "nói dối"],
            "nói xấu": ["nói xấu sau lưng", "buôn chuyện"],
            "vô duyên": ["bất lịch sự", "thiếu tôn trọng"],
            "chậm trễ": ["không đúng giờ", "trễ hẹn", "cao su"],
            "kiêu ngạo": ["tự cao", "khinh người"],
            "mượn tiền không trả": ["quỵt tiền"]
        }
    },
    {
        "id": "h_17",
        "difficulty": "hard",
        "category": "Điện Ảnh",
        "question": "Bộ phim thay đổi cách nhìn của bạn?",
        "synonyms": {
            "interstellar": ["hố đen tử thần"],
            "titanic": ["chìm tàu titanic"],
            "3 idiots": ["ba chàng ngốc", "3 chàng ngốc"],
            "avengers": ["marvel", "endgame"],
            "doraemon": ["nobita"],
            "naruto": ["one piece"]
        }
    },
    {
        "id": "h_18",
        "difficulty": "hard",
        "category": "Tâm Lý",
        "question": "Câu hỏi bạn sợ bị hỏi nhất?",
        "synonyms": {
            "bao giờ lấy chồng": ["bao giờ cưới", "bao giờ lấy vợ", "khi nào cưới"],
            "lương bao nhiêu": ["tháng kiếm được bao nhiêu", "thu nhập bao nhiêu"],
            "có người yêu chưa": ["người yêu đâu"],
            "điểm thi bao nhiêu": ["xếp thứ mấy", "học lực thế nào"],
            "bao giờ giảm cân": ["sao dạo này béo thế"]
        }
    },
    {
        "id": "h_19",
        "difficulty": "hard",
        "category": "Bản Thân",
        "question": "Điều bạn tự hào nhất về bản thân?",
        "synonyms": {
            "độc lập": ["tự lập", "tự kiếm tiền", "kiếm ra tiền"],
            "chăm chỉ": ["nỗ lực", "cố gắng không ngừng", "kiên trì"],
            "ngoan ngoãn": ["hiếu thảo", "thương gia đình"],
            "ngoại hình": ["xinh đẹp", "đẹp trai", "dễ thương"],
            "thật thà": ["tốt bụng", "luôn giúp đỡ mọi người"]
        }
    },
    {
        "id": "h_20",
        "difficulty": "hard",
        "category": "Đời Sống",
        "question": "Thứ bạn sẽ làm nếu trúng số?",
        "synonyms": {
            "mua nhà": ["mua biệt thự", "xây nhà cho bố mẹ"],
            "mua xe": ["mua ô tô", "mua siêu xe"],
            "nghỉ việc": ["bỏ việc", "nghỉ hưu sớm"],
            "đi du lịch": ["du lịch vòng quanh thế giới", "du lịch"],
            "gửi tiết kiệm": ["gửi ngân hàng", "tiết kiệm"],
            "làm từ thiện": ["chia cho người nghèo"]
        }
    },
    {
        "id": "h_21",
        "difficulty": "hard",
        "category": "Cảm Xúc",
        "question": "Cảm xúc khó kiểm soát nhất?",
        "synonyms": {
            "tức giận": ["nổi giận", "sự tức giận", "nóng giận", "bực bội", "cáu"],
            "buồn bã": ["nỗi buồn", "đau lòng", "tuyệt vọng"],
            "ghen tuông": ["ghen", "đố kỵ"],
            "lo sợ": ["sợ hãi", "hoảng loạn"],
            "tình yêu": ["rung động", "thích một người"]
        }
    },
    {
        "id": "h_22",
        "difficulty": "hard",
        "category": "Bản Thân",
        "question": "Điều bạn muốn nói với chính mình 5 năm trước?",
        "synonyms": {
            "mua bitcoin": ["mua btc", "đầu tư coin", "mua vàng"],
            "cố gắng lên": ["đừng từ bỏ", "mày làm được mà", "kiên trì lên"],
            "học hành chăm chỉ": ["chăm học hơn", "học tiếng anh đi"],
            "tiết kiệm tiền": ["đừng tiêu hoang", "giữ tiền"],
            "đừng yêu nó": ["chọn sai người rồi", "yêu bản thân hơn"]
        }
    },
    {
        "id": "h_23",
        "difficulty": "hard",
        "category": "Văn Học",
        "question": "Câu chuyện cổ tích bạn thích nhất?",
        "synonyms": {
            "tấm cám": ["cổ tích tấm cám"],
            "thạch sanh": ["thạch sanh chém chằn tinh"],
            "cây khế": ["ăn khế trả vàng"],
            "sọ dừa": ["chuyện sọ dừa"],
            "cô bé lọ lem": ["lọ lem", "cinderella"],
            "bạch tuyết": ["nàng bạch tuyết", "bạch tuyết và bảy chú lùn"]
        }
    },
    {
        "id": "h_24",
        "difficulty": "hard",
        "category": "Cảm Xúc",
        "question": "Điều khiến bạn cảm thấy an toàn?",
        "synonyms": {
            "nhà": ["ở nhà", "về nhà", "phòng ngủ", "giường ngủ"],
            "gia đình": ["bên bố mẹ", "ở cạnh gia đình", "người thân"],
            "nhiều tiền": ["có tiền", "tiền trong tài khoản", "tài chính vững"],
            "người yêu": ["ở bên người ấy", "vòng tay người yêu"],
            "bạn thân": ["bạn bè"]
        }
    },
    {
        "id": "h_25",
        "difficulty": "hard",
        "category": "Kỷ Niệm",
        "question": "Món ăn gợi nhớ tuổi thơ?",
        "synonyms": {
            "mì tôm trẻ em": ["mì trẻ em", "mì tôm sống"],
            "kẹo mút": ["kẹo kéo", "kẹo cao su con vẹt"],
            "kem que": ["kem ống", "kem túi"],
            "bột sắn": ["cơm cháy", "khoai lang nướng"],
            "cơm mẹ nấu": ["canh rau muống", "cá kho của mẹ"]
        }
    },
    {
        "id": "h_26",
        "difficulty": "hard",
        "category": "Đời Sống",
        "question": "Thứ bạn không thể sống thiếu?",
        "synonyms": {
            "điện thoại": ["smartphone", "đt", "máy tính"],
            "tiền": ["tiền bạc", "rất nhiều tiền"],
            "wifi": ["mạng internet", "internet", "3g 4g"],
            "nước": ["nước uống", "không khí", "oxy"],
            "gia đình": ["bố mẹ", "người yêu"],
            "thức ăn": ["đồ ăn"]
        }
    },
    {
        "id": "h_27",
        "difficulty": "hard",
        "category": "Bản Thân",
        "question": "Điều bạn ghét nhất ở bản thân?",
        "synonyms": {
            "lười": ["lười biếng", "sự lười biếng", "trì hoãn"],
            "nóng tính": ["hay cáu", "dễ nổi giận"],
            "overthinking": ["suy nghĩ nhiều", "nghĩ lung tung", "nhạy cảm"],
            "ngoại hình": ["béo", "mập", "xấu", "tự ti"],
            "tiêu xài hoang": ["không biết tiết kiệm"],
            "nhút nhát": ["rụt rè", "ngại giao tiếp"]
        }
    },
    {
        "id": "h_28",
        "difficulty": "hard",
        "category": "Cảm Hứng",
        "question": "Câu nói truyền cảm hứng cho bạn?",
        "synonyms": {
            "cố gắng lên": ["mọi chuyện sẽ ổn thôi", "vạn sự tùy duyên"],
            "thất bại là mẹ thành công": ["không gì là không thể"],
            "có làm mới có ăn": ["muốn ngồi ở vị trí không ai ngồi được"],
            "just do it": ["hãy cứ khát khao hãy cứ dại khờ", "never give up"]
        }
    },
    {
        "id": "h_29",
        "difficulty": "hard",
        "category": "Trí Tưởng Tượng",
        "question": "Nếu là một loại thời tiết, bạn sẽ là gì?",
        "synonyms": {
            "mưa": ["ngày mưa", "mưa rào", "mưa bay"],
            "nắng": ["ngày nắng", "nắng ấm", "ánh nắng"],
            "se lạnh": ["mát mẻ", "gió heo may"],
            "bão": ["giông bão", "sấm sét"],
            "tuyết": ["tuyết rơi"]
        }
    },
    {
        "id": "h_30",
        "difficulty": "hard",
        "category": "Thế Giới",
        "question": "Điều bạn muốn thay đổi ở thế giới?",
        "synonyms": {
            "hết chiến tranh": ["hòa bình", "không còn chiến tranh", "thế giới hòa bình"],
            "hết nghèo đói": ["xóa đói giảm nghèo", "không ai bị đói"],
            "hết bệnh tật": ["không còn ung thư", "chữa khỏi mọi bệnh"],
            "môi trường xanh": ["hết ô nhiễm", "chống biến đổi khí hậu"],
            "con người yêu thương nhau": ["không còn dối trá", "hết lừa lọc"]
        }
    },
    {
        "id": "h_31",
        "difficulty": "hard",
        "category": "Hoạt Hình",
        "question": "Nhân vật hoạt hình bạn thấy giống mình nhất?",
        "synonyms": {
            "nobita": ["nobi nobita"],
            "doraemon": ["mèo máy doraemon"],
            "shin": ["shin cậu bé bút chì"],
            "conan": ["kudo shinichi"],
            "tom": ["tom và jerry", "mèo tom"],
            "luffy": ["vua hải tặc"],
            "gấu pooh": ["gấu trúc po"]
        }
    },
    {
        "id": "h_32",
        "difficulty": "hard",
        "category": "Kỷ Niệm",
        "question": "Kỷ niệm đáng nhớ nhất thời học sinh?",
        "synonyms": {
            "bị phạt": ["viết bản kiểm điểm", "đứng góc lớp", "gọi phụ huynh"],
            "bế giảng": ["lễ tốt nghiệp", "chia tay mái trường", "ngày bế giảng"],
            "quay cóp": ["chép phao", "quay cóp bài"],
            "tỏ tình": ["yêu thầm", "mối tình đầu"],
            "đi chơi cùng lớp": ["cắm trại", "du lịch lớp"]
        }
    },
    {
        "id": "h_33",
        "difficulty": "hard",
        "category": "Cảm Xúc",
        "question": "Điều khiến bạn khóc gần đây nhất?",
        "synonyms": {
            "xem phim": ["phim cảm động", "phim buồn"],
            "thất tình": ["chia tay", "bị từ chối", "nhớ người yêu cũ"],
            "áp lực công việc": ["stress", "áp lực học tập", "mệt mỏi"],
            "bị mắng": ["bố mẹ mắng", "sếp chửi"],
            "bụi bay vào mắt": ["cắt hành tây"],
            "hết tiền": ["thiếu tiền"]
        }
    },
    {
        "id": "h_34",
        "difficulty": "hard",
        "category": "Lịch Sử",
        "question": "Nếu được sống ở thời đại khác, bạn chọn thời nào?",
        "synonyms": {
            "thời phong kiến": ["thời cổ đại", "thời vua chúa", "thời xưa", "tam quốc"],
            "tương lai": ["thế kỷ 22", "thời đại vũ trụ", "thời công nghệ"],
            "thập niên 90": ["thời 8x 9x", "thời bao cấp"],
            "thời tiền sử": ["thời khủng long"]
        }
    },
    {
        "id": "h_35",
        "difficulty": "hard",
        "category": "Tâm Lý",
        "question": "Điều bạn sợ mất nhất?",
        "synonyms": {
            "gia đình": ["bố mẹ", "người thân", "mất người thân"],
            "tiền": ["tiền bạc", "tài sản"],
            "sức khỏe": ["mạng sống", "sự sống"],
            "người yêu": ["người mình yêu"],
            "bản thân": ["chính mình", "tự do"],
            "bạn bè": ["bạn thân"]
        }
    },
    {
        "id": "h_36",
        "difficulty": "hard",
        "category": "Triết Học",
        "question": "Câu hỏi triết học bạn từng tự hỏi?",
        "synonyms": {
            "mình là ai": ["tôi là ai", "ta là ai"],
            "sống để làm gì": ["ý nghĩa cuộc sống là gì", "mục đích sống"],
            "sau khi chết đi về đâu": ["chết rồi đi đâu", "có kiếp sau không"],
            "vũ trụ từ đâu ra": ["có người ngoài hành tinh không"],
            "tiền có mua được hạnh phúc": ["hạnh phúc là gì"]
        }
    },
    {
        "id": "h_37",
        "difficulty": "hard",
        "category": "Âm Thanh",
        "question": "Thứ âm thanh khiến bạn dễ chịu?",
        "synonyms": {
            "tiếng mưa": ["tiếng mưa rơi", "mưa rơi tí tách"],
            "tiếng sóng biển": ["sóng vỗ", "tiếng biển"],
            "tiếng suối": ["tiếng nước chảy", "tiếng suối reo"],
            "tiếng chim hót": ["chim hót"],
            "tiếng nhạc nhẹ": ["nhạc lofi", "nhạc không lời", "tiếng piano"],
            "tiếng tiền về": ["ting ting"]
        }
    },
    {
        "id": "h_38",
        "difficulty": "hard",
        "category": "Triết Lý",
        "question": "Điều bạn nghĩ là ý nghĩa cuộc sống?",
        "synonyms": {
            "hạnh phúc": ["sống hạnh phúc", "bình yên", "vui vẻ"],
            "yêu thương": ["giúp đỡ mọi người", "chia sẻ", "cống hiến"],
            "kiếm tiền": ["thành công", "làm giàu"],
            "trải nghiệm": ["khám phá thế giới", "học hỏi"],
            "gia đình": ["ở bên người thân"]
        }
    },
    {
        "id": "h_39",
        "difficulty": "hard",
        "category": "Ẩm Thực",
        "question": "Nếu chỉ được ăn một món cả đời, bạn chọn gì?",
        "synonyms": {
            "cơm": ["cơm trắng", "cơm sườn", "cơm tấm"],
            "phở": ["phở bò", "phở gà"],
            "bánh mì": ["bánh mỳ thịt"],
            "mì tôm": ["mì gói"],
            "thịt bò": ["bò bít tết"],
            "trứng rán": ["trứng chiên"]
        }
    },
    {
        "id": "h_40",
        "difficulty": "hard",
        "category": "Học Tập",
        "question": "Điều bạn muốn học nhưng chưa có cơ hội?",
        "synonyms": {
            "đàn piano": ["học đàn", "học guitar", "chơi nhạc cụ"],
            "ngoại ngữ mới": ["tiếng trung", "tiếng nhật", "tiếng hàn"],
            "lái máy bay": ["lái ô tô"],
            "bơi lội": ["học bơi"],
            "nhảy múa": ["học nhảy", "vũ đạo"],
            "nấu ăn": ["học làm bánh"]
        }
    },
    {
        "id": "h_41",
        "difficulty": "hard",
        "category": "Kỷ Niệm",
        "question": "Câu chuyện bạn kể đi kể lại nhiều nhất?",
        "synonyms": {
            "chuyện thất tình": ["mối tình đầu", "chia tay người yêu cũ", "người yêu cũ"],
            "chuyện thời đi học": ["kỷ niệm cấp 3", "chuyện lớp học"],
            "chuyện suýt chết": ["tai nạn suýt chết", "pha thoát chết"],
            "chuyện làm giàu hụt": ["bỏ lỡ cơ hội kiếm tiền"],
            "chuyện hài hước": ["pha làm trò cười", "pha quê độ"]
        }
    },
    {
        "id": "h_42",
        "difficulty": "hard",
        "category": "Niềm Tin",
        "question": "Điều khiến bạn tin vào phép màu?",
        "synonyms": {
            "trúng số": ["trúng độc đắc"],
            "thoát chết thần kỳ": ["tai qua nạn khỏi", "qua cơn nguy kịch"],
            "gặp đúng người": ["định mệnh", "gặp được chân ái"],
            "sự nỗ lực được đền đáp": ["kỳ tích xuất hiện"],
            "tình mẫu tử": ["tình yêu thương"]
        }
    },
    {
        "id": "h_43",
        "difficulty": "hard",
        "category": "Tính Cách",
        "question": "Nếu là màu sắc, tính cách bạn là màu gì?",
        "synonyms": {
            "màu đen": ["đen", "huyền bí", "black"],
            "màu trắng": ["trắng", "thuần khiết", "white"],
            "màu đỏ": ["đỏ", "nhiệt huyết", "red"],
            "màu xanh dương": ["xanh dương", "bình yên", "blue"],
            "màu vàng": ["vàng", "năng động", "yellow"],
            "màu hồng": ["hồng", "mộng mơ", "pink"]
        }
    },
    {
        "id": "h_44",
        "difficulty": "hard",
        "category": "Tâm Lý",
        "question": "Điều bạn nghĩ mọi người hiểu lầm về bạn?",
        "synonyms": {
            "chảnh": ["khó gần", "kiêu", "lạnh lùng"],
            "giàu có": ["nhiều tiền", "tiểu thư", "công tử"],
            "vui vẻ": ["không có chuyện buồn", "luôn lạc quan"],
            "yếu đuối": ["dễ bắt nạt"],
            "ngây thơ": ["khờ khạo"]
        }
    },
    {
        "id": "h_45",
        "difficulty": "hard",
        "category": "Tương Lai",
        "question": "Câu hỏi bạn muốn hỏi tương lai của mình?",
        "synonyms": {
            "tôi có giàu không": ["tương lai có nhiều tiền không", "khi nào giàu"],
            "chồng tôi là ai": ["vợ tôi là ai", "tôi cưới ai", "khi nào lấy chồng"],
            "tôi có hạnh phúc không": ["cuộc sống sau này thế nào"],
            "bố mẹ có khỏe mạnh không": ["gia đình có bình an không"],
            "tôi sống được bao lâu": ["khi nào tôi chết"]
        }
    },
    {
        "id": "h_46",
        "difficulty": "hard",
        "category": "Nhân Vật",
        "question": "Nếu được gặp một người nổi tiếng đã mất, bạn chọn ai?",
        "synonyms": {
            "bác hồ": ["chủ tịch hồ chí minh", "hồ chí minh", "bác"],
            "steve jobs": ["apple steve jobs"],
            "michael jackson": ["ông hoàng nhạc pop"],
            "albert einstein": ["einstein", "anhxtanh"],
            "đại tướng võ nguyên giáp": ["võ nguyên giáp", "tướng giáp"]
        }
    },
    {
        "id": "h_47",
        "difficulty": "hard",
        "category": "Cảm Xúc",
        "question": "Điều bạn nghĩ là dấu hiệu của hạnh phúc thật sự?",
        "synonyms": {
            "bình yên": ["tâm hồn thanh thản", "không lo âu", "an yên"],
            "nụ cười chân thật": ["cười nhiều", "luôn mỉm cười"],
            "ngủ ngon": ["đặt lưng là ngủ", "không mất ngủ"],
            "ở bên người mình yêu": ["gia đình hòa thuận", "được yêu thương"],
            "tự do tài chính": ["không phải lo nghĩ về tiền"]
        }
    },
    {
        "id": "h_48",
        "difficulty": "hard",
        "category": "Tâm Lý",
        "question": "Nỗi ám ảnh kỳ lạ của bạn là gì?",
        "synonyms": {
            "sợ lỗ": ["hội chứng sợ lỗ", "sợ lỗ tròn"],
            "sợ số chẵn": ["sợ số lẻ", "ám ảnh cưỡng chế", "ocd"],
            "sợ tiếng nhai nhóp nhép": ["tiếng nhai cơm"],
            "sợ soi gương ban đêm": ["nhìn vào gương lúc tối"],
            "sợ chạm vào vật lạ": ["sợ vi khuẩn", "sợ bẩn"]
        }
    },
    {
        "id": "h_49",
        "difficulty": "hard",
        "category": "Triết Lý",
        "question": "Điều bạn nghĩ định nghĩa 'trưởng thành'?",
        "synonyms": {
            "tự chịu trách nhiệm": ["biết chịu trách nhiệm", "có trách nhiệm"],
            "tự kiếm tiền": ["tự lập tài chính", "không xin tiền bố mẹ"],
            "biết kiềm chế cảm xúc": ["bớt nóng tính", "ít than vãn", "trầm lặng hơn"],
            "thương bố mẹ hơn": ["biết lo cho gia đình", "chăm lo cho cha mẹ"],
            "biết chấp nhận": ["không tranh cãi đúng sai"]
        }
    },
    {
        "id": "h_50",
        "difficulty": "hard",
        "category": "Điện Ảnh",
        "question": "Nếu cuộc đời là một bộ phim, thể loại nào phù hợp nhất?",
        "synonyms": {
            "hài kịch": ["phim hài", "comedy", "trò cười"],
            "chính kịch": ["drama", "tâm lý tình cảm"],
            "hành động": ["phiêu lưu", "action", "mạo hiểm"],
            "kinh dị": ["phim ma", "thriller"],
            "lãng mạn": ["tình cảm", "romance", "ngôn tình"],
            "hoạt hình": ["anime"]
        }
    }
]
