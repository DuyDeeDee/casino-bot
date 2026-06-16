import py_compile

file_path = "app/discord_bot/cogs/daga.py"

# Read as UTF-8
with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Let's perform these additional rebranding replacements
extra_replacements = {
    # Gacha / Egg results
    "**Chiến kê:**": "**Nhân vật:**",
    "Chiến kê phôi": "Nhân vật phôi",
    "mảnh trùng chiến kê": "mảnh trùng nhân vật",
    "CHIẾN KÊ ĐÃ TĂNG TỪ CẤP": "NHÂN VẬT ĐÃ TĂNG TỪ CẤP",
    "Chiến kê của bạn nhặt được thức ăn ngon": "Nhân vật của bạn nhặt được thức ăn ngon",
    "Chiến kê tăng thêm": "Nhân vật tăng thêm",
    
    # Commands
    'brief="Mua thức ăn cho chiến kê."': 'brief="Mua thức ăn cho nhân vật."',
    'Tháo toàn bộ trang bị của chiến kê': 'Tháo toàn bộ trang bị của nhân vật',
    'Bạn chưa chọn chiến kê xuất trận nào. Vui lòng truyền ID chiến kê': 'Bạn chưa chọn nhân vật xuất trận nào. Vui lòng truyền ID nhân vật',
    'Bạn chưa có chiến kê chính xuất trận.': 'Bạn chưa chọn nhân vật chính xuất trận.',
    'chưa có chiến kê chính xuất trận để thi đấu.': 'chưa chọn nhân vật chính xuất trận để thi đấu.',
    'Chiến kê {winner_cock.name} đã tăng': 'Nhân vật {winner_cock.name} đã tăng',
    'Chiến kê {loser_cock.name} đã tăng': 'Nhân vật {loser_cock.name} đã tăng',
    'Chiến kê: **{row[1]}**': 'Nhân vật: **{row[1]}**',
    'Bạn chưa sở hữu chiến kê nào.': 'Bạn chưa sở hữu nhân vật nào.',
    'Bạn không có chiến kê nào ở độ hiếm': 'Bạn không có nhân vật nào ở độ hiếm',
    'chiến kê độ hiếm **{viet_rarity}**': 'nhân vật độ hiếm **{viet_rarity}**',
    'nâng sao cho chiến kê': 'nâng sao cho nhân vật',
    'bán chiến kê': 'chuyển nhượng nhân vật',
    'bán chiến kê': 'chuyển nhượng nhân vật',
    
    # Subcommands
    'brief="Mua và mở hòm trang bị Đá Gà."': 'brief="Mua và mở hòm trang bị Đại Chiến Anime."',
    'SÂN ĐẤU ĐÁ GÀ TRỰC TIẾP': 'SÂN ĐẤU ĐẠI CHIẾN ANIME',
    'ĐÁ GÀ TRỰC TIẾP': 'ĐẠI CHIẾN ANIME TRỰC TIẾP',
    'BẢNG XẾP HẠNG ĐẠI SƯ KÊ': 'BẢNG XẾP HẠNG ĐẠI SƯ TRIỆU HỒI',
    
    # Capitalization & cases
    "thành công chiến kê": "thành công nhân vật",
    "tổng số chiến kê": "tổng số nhân vật",
    "bán tất cả chiến kê": "chuyển nhượng tất cả nhân vật",
    "chỉ số chiến kê": "chỉ số nhân vật",
}

for src, dst in extra_replacements.items():
    text = text.replace(src, dst)

# Save
with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

print("daga.py extra replacements applied.")

# Try compiling
try:
    py_compile.compile(file_path, doraise=True)
    print("SUCCESS: Compiled successfully!")
except py_compile.PyCompileError as e:
    print("ERROR:", e)
