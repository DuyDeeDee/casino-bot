# Ma Sói — hợp đồng xử lý đêm (Giai đoạn 2)

> Đây là tài liệu lịch sử của giai đoạn 2. Vũ Nữ phong tỏa và các role đã gỡ không còn áp dụng cho ván mới. Xem [Ma Sói: role hiện hành](masoi-roles.md).

## Luồng dữ liệu

`NightActionView → ActionIntent → submit_night_action → lock_night → resolve_night → NightResult`

- Callback chỉ ghi nhận lựa chọn và giữ tham chiếu tin nhắn để cập nhật giao diện; không giết người, dùng bình thuốc hoặc tiết lộ kết quả ngay.
- Engine kiểm tra người hành động, vai trò, mục tiêu còn sống, số mục tiêu, điều kiện kỹ năng, số đêm và hạn chót. Mỗi kỹ năng được xác nhận một lần/đêm; Sói có thể xác nhận vote và kỹ năng riêng biệt.
- Luồng Discord chuyển sang `NIGHT_PREPARE`, gửi DM đồng thời với giới hạn 6 tác vụ và timeout 15 giây/tác vụ. Trong lúc chuẩn bị, mọi nút hành động đều bị chặn. Chỉ sau khi gửi xong và thông báo mở đêm, `open_night_actions()` mới bắt đầu deadline monotonic chung cho mọi view và bước độc của Phù Thủy. Gửi DM thất bại làm hủy ván không tính rank. Nút cũ không tác động được đêm/ngày mới.
- `lock_night()` chạy trước khi chờ Discord xóa thông báo. Resolver đồng bộ không có `await`, chốt hiệu ứng một lần và lưu kết quả. Gọi lại trả về cùng đối tượng, không dùng thêm bình thuốc hoặc gây thêm sát thương.
- `NightResult` là snapshot bất biến: đêm, seed, người chết, mục tiêu bầy Sói, kết quả thông tin, Thợ Săn/Thị Trưởng cần xử lý tiếp.

## Thứ tự và luật tương tác

1. Vũ Nữ phong tỏa kỹ năng, kể cả vote của Sói.
2. Ghép đôi, ảo ảnh, mê hoặc, nhìn trộm và thiết lập bảo vệ.
3. Chốt vote Sói, đòn đánh độc lập và lựa chọn bình thuốc.
4. Phân giải bảo vệ, miễn nhiễm, chuyển phe, bình độc và lời nguyền.
5. Áp dụng chết và chết dây chuyền; kích hoạt Sói Cuồng Sát, kế thừa Tiên Tri.
6. Trả kết quả soi dựa trên hành động đã chốt, sau khi biết trạng thái phong tỏa.
7. Cog xử lý lượt Thợ Săn và truyền quyền Thị Trưởng; sau đó mới xét thắng.

Người còn sống tại thời điểm chốt vẫn hành động trong đêm họ chết. Sói Ảo Ảnh chết cùng đêm không xóa hiệu ứng đã thực hiện. Soi Bán Nguyệt hoặc ảo ảnh không cộng thưởng tìm ra Sói thật.

Bảo vệ và bình cứu chặn đòn đánh trực tiếp (Sói/Sát Thủ/Sói Trắng), không chặn bình độc, lời nguyền, chết vì tình nhân hoặc bị phát hiện khi nhìn trộm. Bình cứu chỉ bảo vệ đúng một người; xác nhận dùng sẽ tiêu hao bình dù người đó cuối cùng không bị tấn công. Nếu Vũ Nữ phong tỏa Phù Thủy thì bình không tiêu hao. Điểm cứu/bảo vệ tính theo số mục tiêu, không nhân lên khi cùng người bị nhiều đòn đánh.

Chuỗi chết ban đêm, xử tử và Thợ Săn dùng chung `apply_deaths()`. Event và Boss đã được gỡ khỏi ván mới; không còn thẻ sự kiện, HP/khiên Boss hoặc phiếu x3. Sói Cuồng Sát vẫn kích hoạt cắn hai người ở đêm sau khi chết.

Vote Sói hòa được phân xử theo user ID tăng dần để không phụ thuộc thứ tự callback. Cuồng nộ chọn hai mục tiêu nhiều phiếu nhất; nếu chỉ có một mục tiêu, chọn nạn nhân thứ hai bằng RNG của đêm. Preview cho Phù Thủy chỉ tính mục tiêu chính, không dùng RNG hoặc ghi replay. Seed được lưu trong kết quả và replay; để tái hiện cần cùng trạng thái đầu đêm và danh sách intent.

## Kiểm tra

Chạy từ thư mục dự án:

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_masoi_engine tests.test_masoi_cog -v
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py' -q
```

Test UI dùng mock Discord, không gọi API hoặc gửi DM thật. Cần smoke test trên server thử nghiệm trước khi đưa vào production, nhất là DM, quyền kênh và tương tác nhiều người. Bản sửa sau đánh giá đã tách UI, điều phối, gửi DM, rank và phục hồi thành các module riêng; xem [phục hồi và kiểm tra](masoi-recovery.md).
