# Ma Sói — phục hồi và kiểm tra sau đánh giá

## Phạm vi

Sửa điều kiện thắng Solo, đồng hồ hành động đêm, lượt Thợ Săn/Thị Trưởng, replay và phục hồi dữ liệu. Không thay đổi lệnh VIP, cấu hình VIP, phí tạo ván hoặc chính sách hoàn phí. Vấn đề hoàn phí VIP được giữ nguyên theo yêu cầu.

Event và Boss đã ngừng hỗ trợ: gỡ lệnh/alias, nút cài đặt, nút hướng dẫn chế độ và dòng chế độ trên lobby. Chỉ giữ phân vai Tự động/Tùy chỉnh. Cấu hình cũ có `enable_events`, `enable_boss_mode` được bỏ qua và không ghi lại; `ALPHA_WOLF` bị loại khỏi cấu hình ván mới. Các tên vai trò/sự kiện và trường HP cũ chỉ còn phục vụ đọc snapshot/lịch sử, không kích hoạt cơ chế chơi đã bỏ. Không cần reset database hoặc xóa rank cũ; ván gián đoạn vẫn được phục hồi theo chính sách hủy an toàn bên dưới.

## Cấu trúc

- `cogs/masoi.py`: lệnh, lobby, cấu hình, quyền kênh và các thành phần VIP được giữ nguyên.
- `modules/masoi_engine.py`: luật, intent, resolver, điều kiện thắng và điểm cá nhân; không gọi Discord.
- `modules/masoi_ui.py`: giao diện hành động, thảo luận, bỏ phiếu, rank và replay.
- `modules/masoi_delivery.py`: gửi hành động đêm đồng thời, có timeout; không mở deadline sớm.
- `modules/masoi_flow.py`: điều phối ván, các lượt tiếp nối và kết thúc.
- `modules/masoi_rank.py`: chốt rank theo ID ván, không ghi hai lần.
- `modules/masoi_state.py` và `masoi_recovery.py`: snapshot JSON và phục hồi.

## Chính sách restart

Migration 55 thêm `masoi_sessions` và `masoi_match_history`. Snapshot lưu vai trò, hành động, kết quả đêm, replay, trạng thái rank và bản gốc permission overwrite; không lưu đối tượng Discord hoặc callback. Quyền gốc được ghi vào SQLite trước khi bot cấm chat.

Ván đang chơi khi bị gián đoạn được **hủy an toàn**, không tiếp tục từ giữa đêm và không cộng/trừ rank. Ván đã chốt người thắng được ghi rank đúng một lần theo ID cũ nếu chưa ghi xong. Ván hòa không ghi rank. Phục hồi không gọi logic hoàn phí hay VIP.

Khi khởi động, kênh có snapshot chưa xử lý bị chặn tạo ván mới. Bot khôi phục từng permission overwrite; giữ lại những mục thất bại và thử lại mỗi 30 giây. Snapshot lỗi định dạng hoặc lỗi database không bị xóa. Kênh đã bị xóa không cần khôi phục quyền. Sau khi hoàn tất, snapshot được chuyển sang lịch sử và xóa khỏi hàng đợi trong cùng transaction.

Không phục hồi đè lên ván đang sở hữu kênh trong RAM. Khi unload, bot lưu checkpoint, dừng view và hủy tác vụ; lần load sau xử lý phần còn lại. Thông báo phục hồi đã gửi được đánh dấu để tránh gửi lại khi một bước dọn dẹp sau đó thất bại; sự cố đúng giữa gửi Discord và ghi dấu SQLite vẫn có thể khiến thông báo lặp, nhưng rank vẫn không bị cộng hai lần.

## Kiểm tra

```powershell
.\venv\Scripts\python.exe -m unittest tests.test_masoi_engine tests.test_masoi_cog tests.test_masoi_rank tests.test_masoi_fixes tests.test_masoi_recovery tests.test_masoi_standard -q
.\venv\Scripts\python.exe -m unittest discover -s tests -p 'test*.py' -q
```

Test dùng mock Discord và database tạm: Solo, hòa, replay ngày/đêm và phân trang, DM đồng thời/timeout, người không nằm trong cache, snapshot roundtrip, restart, lỗi khôi phục quyền, ghi rank lỗi rồi thử lại, vòng đời cog và luồng đêm đến kết thúc có persistence.

Trước khi chạy thật: sao lưu database, không nâng cấp khi còn ván đang chơi và smoke test trên server riêng. Kiểm tra DM của nhiều người, quyền chat sau người chết/kết thúc, restart giữa ván và restart sau khi chốt rank. Chưa có kiểm chứng bằng Discord thật trong lần sửa này.
