# Rank Ma Sói theo phe

## Điểm ván đấu

| Kết quả cá nhân | Điểm |
| --- | ---: |
| Thắng Sói hoặc Dân | +20 |
| Thắng Solo | +30 |
| Thua bất kỳ phe nào | −15 |
| Thưởng kỹ năng khi thắng | +5/mốc, tổng thưởng tối đa +10 |

Mốc thưởng: Tiên Tri soi ra Sói thật; mục tiêu được Bảo Vệ, Bác Sĩ (chặn Sói cắn) hoặc Lực Sĩ cứu thành công; bình Phù Thủy dùng có ích; Pháp Y hoàn tất điều tra; Mục Sư giết Sói bằng nước thánh; và Cậu Bé Mồm To tiết lộ vai trò thuộc phe Sói hoặc Solo khi chết. Tiết lộ vai trò Dân không được thưởng mốc này. Mỗi mốc cho +5 và toàn bộ thưởng kỹ năng cộng lại vẫn tối đa +10. Không thưởng chỉ vì sống sót hay chỉ chọn hành động nếu không tạo ra kết quả. Người chết vẫn được tính thắng nếu mục tiêu đội được hoàn thành. Người thua luôn nhận −15, không được thưởng kỹ năng để bù thành điểm dương. Điểm tích lũy có thể âm, không chặn tại 0. Ván bị hủy, hòa không có thắng cá nhân hoặc tắt rank thì không ghi kết quả xếp hạng.

Kẻ Phóng Hỏa chỉ thắng khi là người sống cuối cùng. Không chốt thắng đội Sói hoặc Dân khi Kẻ Phóng Hỏa còn sống. Thợ Săn Người nhận thắng cá nhân nếu mục tiêu bị treo cổ khi mình còn sống, nhưng ván vẫn tiếp tục; nếu mục tiêu chết cách khác, role này gia nhập phe Sói. Cặp tình nhân khác phe thắng khi còn đúng hai người liên kết với nhau. Nếu ván hòa sau khi Thợ Săn Người đã đạt mục tiêu, chỉ thắng cá nhân đó được ghi rank; người khác không bị trừ điểm.

## Ba bảng độc lập

- **Sói (`WOLF`)**: các vai Sói chơi theo đội, Kẻ Bị Nguyền đã hóa Sói và Thợ Săn Người đã gia nhập phe Sói.
- **Solo (`SOLO`)**: Kẻ Ngốc, Kẻ Phóng Hỏa, Thợ Săn Người chưa gia nhập phe Sói và cặp tình nhân khác phe. Các mục tiêu độc lập phải thật sự thắng; không được nhận thắng theo phe gốc.
- **Dân (`VILLAGER`)**: các vai còn lại, bao gồm Bán Nguyệt và Kẻ Bị Nguyền chưa hóa Sói. Cặp tình nhân cùng phe vẫn tính rank theo đội.

Mỗi người có điểm, số ván, thắng, thua riêng ở từng bảng. Hạng Đồng/Bạc/Vàng/Kim Cương vẫn dùng các mốc 0/100/300/700; điểm âm thuộc Đồng.

`masoirank` hiển thị cả ba bảng. `masoirank soi`, `masoirank solo`, `masoirank dan` hiển thị riêng; có nút chuyển bảng. Giữ các alias lệnh cũ và nhận tên phe có dấu. Bảng được sắp theo điểm giảm dần, số thắng giảm dần, rồi user ID tăng dần.

## Lưu trữ và nâng cấp

Migration **54** tạo `user_masoi_faction_stats` và `masoi_rank_matches`. Dữ liệu rank cũ không có lịch sử từng ván/vai nên không được suy đoán để chia phe: các bảng mới bắt đầu từ 0. `user_masoi_stats` cùng huy hiệu và lịch sử tổng cũ được giữ nguyên khi nâng cấp; thống kê tổng tiếp tục tích lũy kết quả mới, nhưng không dùng cho bảng rank mới. Counter cũ `tanner_wins` là dữ liệu lịch sử; thắng Solo mới nằm trong thống kê `SOLO`.

Khi bot khởi động, cơ chế migration hiện có tự nâng schema lên phiên bản hiện tại **55**: migration 54 tạo rank theo phe, migration 55 thêm checkpoint và lịch sử ván phục vụ phục hồi. Không cần xóa/reset database. Thay đổi này đã được thử trên database tạm, chưa chạy migration trực tiếp trên database đang dùng.

Một ván có ID riêng. `settle_masoi_match()` lưu tất cả người chơi trong một transaction, rollback toàn bộ nếu lỗi. Cùng ID ván chỉ được tính điểm một lần. Rank Sói/Dân/Solo không ảnh hưởng lẫn nhau.

Đây là bảng điểm tích lũy, chưa phải MMR dựa trên độ mạnh đối thủ; bản sửa giữ nguyên công thức điểm đã thống nhất.

## Test

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_masoi_rank -v
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py' -q
```
