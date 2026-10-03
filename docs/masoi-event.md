# Ma Sói Event — thẻ sự kiện đêm

Dùng `!masoievent` hoặc `!masoi event` để tạo bàn Event. Host cũng có thể bật/tắt **Thẻ sự kiện** trong cài đặt khi lobby còn chờ. Event mặc định tắt và chỉ áp dụng cho lobby hiện tại; bàn `!masoi` tiếp theo vẫn là bàn thường. Phí tạo bàn, quyền VIP, rank và các cài đặt VIP không đổi. Boss không được mở lại. Lobby không thêm dòng “chế độ”; trạng thái Event hiển thị trong cài đặt và thẻ được công bố công khai trước khi mở hành động đêm.

| Thẻ | Hiệu ứng |
| --- | --- |
| 🩸 Trăng Máu | Bầy Sói cắn tối đa 2 người đêm đó. Chỉ xuất hiện từ 10 người sống; không cộng dồn vượt 2 với Sói Cuồng Sát. |
| 🌫️ Sương Mù | Kết quả Tiên Tri và Thám Tử có 50% khả năng “không xác định”; không báo sai phe hoặc cộng thưởng soi nhầm. |
| ☀️ Nhật Thực | Ban ngày vẫn thảo luận và dùng kỹ năng Xạ Thủ, nhưng bỏ lượt bỏ phiếu treo cổ. Chỉ xuất hiện từ đêm 2 khi còn ít nhất 8 người. |
| 🧪 Phong Ấn Dược Liệu | Phù Thủy không nhận menu dùng bình; không thể xác nhận cứu/độc và không mất bình. Chỉ rút thẻ nếu Phù Thủy còn sống và còn bình. |
| 🛡️ Thánh Quang | Chặn đòn cắn của bầy Sói; độc, lửa và các nguyên nhân chết khác vẫn hiệu lực. |
| 🔇 Đêm Câm Lặng | Thảo luận ngày sau tối đa 30 giây; không kéo dài một cài đặt vốn ngắn hơn. |

Hai thẻ cũ **Bão Sấm Sét** và **Trăng Khuyết** chỉ tác động đến Cô Bé/Sói Trắng, là các role đã gỡ. Tên thẻ vẫn đọc được từ lịch sử nhưng không được rút trong ván mới. Khi có nhiều thẻ hợp lệ, bot tránh lặp thẻ vừa rút. Các thẻ phụ thuộc role chỉ vào bộ rút nếu role tương ứng còn sống. Event đêm và hiệu ứng được ghi vào replay và snapshot; ván gián đoạn vẫn theo chính sách hủy an toàn khi restart.
