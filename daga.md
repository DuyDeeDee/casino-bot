# ⚔️ ĐẠI CHIẾN ANIME (ANIME SHOWDOWN)

## Tổng quan

Người chơi sẽ chiêu mộ và sưu tập các nhân vật Anime với nhiều độ hiếm và sức mạnh khác nhau.

Có thể:

* Mua thẻ triệu hồi.
* Triệu hồi nhân vật (Gacha).
* Bồi dưỡng nhân vật (Cho ăn tăng EXP).
* Huấn luyện tăng chỉ số.
* Trang bị vật phẩm.
* Thách đấu PvP đặt cược.
* Leo bảng xếp hạng (BXH).

---

# 🔮 Hệ thống Thẻ Triệu Hồi

Người chơi có thể mua thẻ triệu hồi trong Shop.

Ví dụ:

```
/anime shop
/anime buy egg <ID>
```

## 🔮 Thẻ Triệu Hồi Thường

Giá:
500.000 VNĐ

Tỷ lệ:

70% N Common

24.8% R Rare

5% SR Super Rare

0.19% UR

0.01% LR Legend

---

## 🔮 Thẻ Triệu Hồi Cao Cấp

Giá:
2.000.000 VNĐ

Tỷ lệ:

50% R Rare

35% SR Super Rare

13.9% SSR

1% UR

0.1% LR Legend

---

## 🔮 Thẻ Triệu Hồi Hoàng Kim

Giá:
10.000.000 VNĐ

Tỷ lệ:

45% SR Super Rare

40% SSR

12% UR

3% LR Legend

---

# ⭐ Độ hiếm và Chỉ số gốc

## ⚪ N Common (HP 80-100 | ATK 10-15 | DEF 8-12 | SPD 8-12 | CRIT 5-15)
* **Usopp** (One Piece)
* **Krillin** (Dragon Ball)
* **Zenitsu** (Kimetsu no Yaiba)

---

## 🟢 R Rare (HP 100-120 | ATK 15-20 | DEF 12-18 | SPD 12-18 | CRIT 10-20)
* **Killua** (Hunter x Hunter)
* **Sakura** (Naruto)
* **Trunks** (Dragon Ball)

---

## 🔵 SR Super Rare (HP 120-140 | ATK 20-28 | DEF 18-25 | SPD 18-25 | CRIT 15-25)
* **Levi Ackerman** (Attack on Titan)
* **Zoro** (One Piece)
* **Akame** (Akame ga Kill)

---

## 🟣 SSR (HP 140-170 | ATK 28-36 | DEF 25-32 | SPD 25-32 | CRIT 20-30)
* **Kakashi** (Naruto)
* **Meliodas** (Seven Deadly Sins)
* **Ichigo** (Bleach)

---

## 🟡 UR (HP 170-210 | ATK 36-48 | DEF 32-40 | SPD 32-40 | CRIT 25-35)
* **Gojo Satoru** (Jujutsu Kaisen)
* **Itachi Uchiha** (Naruto)
* **Vegeta** (Dragon Ball)

---

## 🔴 LR Legend (HP 210-260 | ATK 48-60 | DEF 40-50 | SPD 40-50 | CRIT 30-40)
* **Goku (Ultra Instinct)** (Dragon Ball)
* **Luffy (Gear 5)** (One Piece)
* **Naruto (Baryon Mode)** (Naruto)
* **Saitama** (One Punch Man)

---

## 👑 Exclusive
* **Luffy** (Nhân vật đặc quyền)

---

# 📊 Chỉ số Nhân Vật

Mỗi nhân vật sở hữu các chỉ số:

❤️ Máu (HP)

⚔️ Sức mạnh (ATK)

🛡️ Phòng thủ (DEF)

⚡ Tốc độ (SPD)

🍀 May mắn (LUK)

Ví dụ:

```
⚔️ Nhân vật: Gojo Satoru
⭐ Độ hiếm: UR
❤️ Máu: 188
⚔️ Sức mạnh: 42
🛡️ Phòng thủ: 36
⚡ Tốc độ: 34
🍀 May mắn: 28
```

---

# 🍚 Nuôi Dưỡng & Huấn Luyện

## Bồi dưỡng (Cho ăn)

```
/anime feed <ID_thức_ăn> <số_lượng>
```

Tăng EXP giúp nhân vật lên cấp.

---

## Huấn luyện

```
/anime train
```

Ngẫu nhiên tăng một chỉ số (HP, ATK, DEF, SPD, LUK). Cooldown: 1 tiếng.

---

# 🎒 Trang Bị (Gear Shop)

Mua hòm trang bị trong Shop để nhận vũ khí, giáp, bùa hộ mệnh giúp tăng thêm chỉ số sức mạnh:

* **Vũ khí**: Cựa Gỗ, Cựa Sắt, Cựa Thép, Cựa Dao, Cựa Thiên Lôi, Cựa Diệt Thần.
* **Giáp**: Giáp Da, Giáp Đồng, Giáp Thép, Giáp Hổ, Giáp Kim Cang, Giáp Thần Thú.
* **Bùa**: Khăn Đỏ, Chuông Bạc, Bùa Ngọc, Dây Chuyền Phượng, Ngọc Long, Linh Châu.

---

# ⚔️ Cơ Chế Chiến Đấu PvP

```
/anime fight @user <tiền_cược>
```

Hai bên đặt cược và tham gia trận chiến mô phỏng tự động theo lượt:

* **Lượt đánh trước**: Quyết định bởi chỉ số Tốc độ (SPD). Nếu bằng nhau, chỉ số May mắn (LUK) sẽ quyết định.
* **Sát thương gây ra**: `Sát thương = Sức mạnh - (Phòng thủ / 2)` (dao động ngẫu nhiên ±10%).
* **Đòn chí mạng**: Dựa trên chỉ số May mắn (LUK), gây 200% sát thương.
* **Né đòn, Phản công, Lá chắn**: Được kích hoạt tự động dựa trên chỉ số Tốc độ, May mắn và các Kỹ năng đặc biệt của nhân vật.

---

# 📜 Log Trận Đấu

```
⚔️ Gojo Satoru ra đòn!
💥 Chí mạng! Gây 56 sát thương!
✨ Itachi Uchiha né đòn thành công và kích hoạt [Tsukuyomi]!
⚔️ Itachi Uchiha phản công gây 35 sát thương!
🏆 Gojo Satoru chiến thắng!
💰 +100.000 VND
🔰 +150 EXP
```

---

# 📈 Level & Nâng Sao

* **Lên cấp**: Khi đạt đủ EXP, nhân vật tự động tăng cấp, nhận thêm chỉ số ngẫu nhiên. Cấp độ tối đa là 100.
* **Nâng sao**: Triệu hồi bản trùng sẽ nhận được Mảnh nhân vật. Dùng mảnh nhân vật phôi để nâng sao giúp gia tăng chỉ số vượt trội. Luffy đạt từ 6 sao trở lên sẽ tiến hóa thành Luffy Gear 4 với chỉ số tăng 100%!

---

# 🏅 Danh Hiệu Nhà Triệu Hồi

* **10 trận thắng**: Tân Binh 🔰
* **50 trận thắng**: Nhà Lữ Hành 🛡️
* **100 trận thắng**: Bậc Thầy Triệu Hồi ⚔️
* **500 trận thắng**: Đại Sư Triệu Hồi 🏆
* **1000 trận thắng**: Huyền Thoại Anime 👑

---

# 🎁 Sự Kiện Ngẫu Nhiên

Sau khi hoàn thành huấn luyện hoặc chiến đấu:

🍀 Nhặt được vật phẩm bồi dưỡng.

🎁 Nhận trang bị ngẫu nhiên.

💰 Được nhà sưu tầm trả giá mua lại nhân vật với số tiền lớn.

⚡ Nhân vật bộc phát tiềm năng, nhận thêm EXP đột biến.
