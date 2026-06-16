import py_compile

file_path = "app/discord_bot/cogs/simulator.py"

with open(file_path, "r", encoding="utf-8") as f:
    text = f.read()

# Locate the details dictionary block
start_pattern = 'details = {'
end_pattern = 'name, price, desc = details[self.selected_option]'

start_idx = text.find(start_pattern)
end_idx = text.find(end_pattern)

if start_idx != -1 and end_idx != -1:
    new_details = """details = {
            "egg_thuong": ("🔮 Thẻ Triệu Hồi Thường", 500_000, "Triệu hồi nhân vật. Tỷ lệ: N Common (70%), R Rare (24.8%), SR Super Rare (5%), UR (0.19%), LR Legend (0.01%)."),
            "egg_caocap": ("🔮 Thẻ Triệu Hồi Cao Cấp", 2_000_000, "Triệu hồi nhân vật. Tỷ lệ: R Rare (50%), SR Super Rare (35%), SSR (13.9%), UR (1%), LR Legend (0.1%)."),
            "egg_hoangkim": ("🔮 Thẻ Triệu Hồi Hoàng Kim", 10_000_000, "Triệu hồi nhân vật. Tỷ lệ: SR Super Rare (45%), SSR (40%), UR (12%), LR Legend (3%). Hỗ trợ bảo hiểm (pity) 30 lần."),

            "chest_thuong": ("📦 Rương Vật Phẩm Thường", 100_000, "Mở trang bị Anime. Cơ hội nhận trang bị từ Common đến Noble."),
            "chest_caocap": ("📦 Rương Vật Phẩm Cao Cấp", 1_000_000, "Mở trang bị Anime. Cơ hội nhận trang bị từ Rare đến Legend."),
            "chest_hoangkim": ("📦 Rương Vật Phẩm Hoàng Kim", 5_000_000, "Mở trang bị Anime. Cơ hội nhận trang bị từ Noble đến Mythic."),

            "box_garage": ("🏎️ Garage Box Xe", 100_000, "Mở xe / siêu xe. Tỷ lệ: Common (70%), Rare (25%), Epic (5%)."),
            "box_premium": ("🏎️ Premium Box Xe", 1_000_000, "Mở xe / siêu xe. Tỷ lệ: Rare (50%), Epic (35%), Legendary (13%), Mythic (2%)."),
            "box_luxury": ("🏎️ Luxury Box Xe", 10_000_000, "Mở xe / siêu xe. Tỷ lệ: Epic (40%), Legendary (35%), Mythic (20%), Exclusive (5%)."),
        }
        """
    text = text[:start_idx] + new_details + text[end_idx:]
    print("SUCCESS: details dictionary updated.")
else:
    print("ERROR: details dictionary not found.")

# Let's replace the tab option emoji from 🐓 to ⚔️
text = text.replace('emoji="🐓"', 'emoji="⚔️"')

with open(file_path, "w", encoding="utf-8") as f:
    f.write(text)

try:
    py_compile.compile(file_path, doraise=True)
    print("SUCCESS: Compiled successfully!")
except Exception as e:
    print("ERROR:", e)
