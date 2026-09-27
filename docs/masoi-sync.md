# Đồng bộ Ma Sói: hiển thị và luật chơi

## Các thay đổi

- Badge đọc trực tiếp từ dữ liệu hiện tại khi dựng bảng phiếu, menu bỏ phiếu,
  thông báo chết/xử tử/Thợ Săn/kế nhiệm và tổng kết vai trò. Set/xóa badge làm mới
  phòng chờ hoặc bảng phiếu đang hoạt động ngay, không cần tạo ván khác.
  Tin nhắn lịch sử không bị sửa ngược. Badge dạng chữ vẫn hiện ở embed;
  menu dùng emoji mặc định nếu badge không phải emoji hợp lệ.
- REALTIME vẫn hiện số phiếu; END_ONLY hiện người chơi và badge nhưng không
  lộ số phiếu. Cập nhật badge và cập nhật phiếu được tuần tự hóa với đóng lượt,
  tránh ghi đè bảng kết quả bằng bảng đang bỏ phiếu. Bảng kết quả không còn
  hướng dẫn bấm menu đã bị gỡ.
- Hướng dẫn Vai Trò dùng chính `Role.description` như DM chia vai, chia theo
  bầy Sói/Dân/Solo. Sói Trắng ở mục Solo nhưng vẫn tham gia bầy Sói ban đêm.
  Hướng dẫn làm rõ Bảo Vệ, Phù Thủy (không hồi sinh), Thợ Săn, Sói Cuồng Sát,
  Bán Nguyệt, Sói Ảo Ảnh, Thám Tử, Người Thổi Sáo và Dê Tế Thần.
- Tiên Tri chỉ kết luận Sói/không thuộc bầy Sói, không gọi Sát Thủ, Người Thổi
  Sáo hay Kẻ Ngốc là Dân. Ảo ảnh/Bán Nguyệt vẫn gây kết quả đánh lừa theo luật.
- Thám Tử và Người Thổi Sáo dùng chung số mục tiêu bắt buộc với engine:
  đúng 2 người, hoặc 1 khi chỉ còn một người khác. DM và menu dùng cùng con số.
- Tanner ở CUSTOM được quyết định bởi danh sách vai trò đã chọn. Nút bật/tắt
  thêm/xóa Tanner khỏi danh sách đó, nhãn cài đặt phản ánh trạng thái thực tế.
  Chia vai dùng chính đội hình preview; đổi cấu hình vai trò cập nhật cả lobby.
  Sao chép cài đặt không dùng chung danh sách vai trò với cấu hình gốc.
- Thông báo sáng và kết quả xử tử tổng hợp toàn bộ người vừa chết, kể cả chuỗi
  Thợ Săn/Tình Nhân. `NightResult` vẫn là kết quả đêm gốc bất biến; thông báo
  tổng hợp lấy chênh lệch người sống sau khi các lượt tiếp nối hoàn tất.
- Menu cứu/độc của Phù Thủy và cập nhật mục tiêu Sói dùng chung khóa chỉnh DM.
  Chuyển bước xác nhận interaction trước khi chờ khóa; không khôi phục menu
  cứu sau bước độc, không cập nhật từ đêm cũ sang đêm mới. Refresh thất bại
  giữ menu đã gửi còn dùng được. DM hiện số giây còn lại và kết quả dùng bình
  thực sự sau phân giải, kể cả phong tỏa không mất bình.
- Kết quả điều tra vẫn gửi được khi tin nhắn DM chưa có field xác nhận.
  Kết quả Cô Bé chứa tất cả mục tiêu cắn đã chốt trong engine; DM và replay
  cùng đọc kết quả này, thay vì DM tự thêm một mục tiêu khác với log.
- Thảo luận/bỏ phiếu chỉ mở đồng hồ sau khi gửi tin nhắn thành công, dùng
  deadline monotonic chung với callback. Các cập nhật yêu cầu bỏ phiếu sớm
  cũng tuần tự hóa; các view ban ngày được dừng khi kết thúc/hủy ván.
- Kế nhiệm Thị Trưởng được thông báo công khai và gửi DM cho người nhận,
  hiện Thị Trưởng hiện tại/phiếu x2 trên bảng phiếu. Giữ nguyên vai trò gốc.
  Không chọn người kế nhiệm thì bỏ chức và thông báo các phiếu còn lại x1.
- Replay phân biệt tấn công với qua đời đã chốt; không kể mục tiêu được bảo
  vệ là đã chết hoặc được hồi sinh. Kết quả soi/phong tỏa được ghi rõ.
  Ván hòa không còn được kể là có phe giành chiến thắng.
- Nhãn chat người chết ghi đúng kênh chơi, không còn ghi thread. Danh sách
  phòng 20 người có badge dài được chia field để không vượt giới hạn Discord.

## Luật Tình Nhân thống nhất với rank

Mục tiêu riêng là mục tiêu thắng, không phải tư cách tham gia bầy Sói:
Sói Trắng có mục tiêu Solo dù có quyền bỏ phiếu cắn cùng Sói.

Khi Cupid ghép hai người khác mục tiêu, cặp nhận mục tiêu Tình Nhân:
phải là hai người sống cuối cùng, cả hai xếp rank Solo. Bao gồm Sói Trắng +
Sói thường, Sói + Dân, và Solo + người có mục tiêu khác. Không kết thúc sớm
bằng ưu thế quân số Sói/Dân trong lúc cặp này còn sống. Sói Trắng/Sát Thủ/
Người Thổi Sáo trong cặp không thắng riêng bỏ lại người kia. Kẻ Ngốc bị
treo cổ vẫn có ưu tiên thắng tức thì; Người Thổi Sáo ngoài cặp vẫn có quyền
thắng nếu hoàn thành mê hoặc. Khi cặp chết, các mục tiêu còn lại tiếp tục.

Mục tiêu cặp được chốt lúc ghép và lưu snapshot, không bị đổi lại khi Kẻ
Bị Nguyền biến thành Sói. Cặp cùng mục tiêu lúc ghép vẫn giữ mục tiêu gốc
và xếp rank cá nhân. Hai người nhận DM giải thích mục tiêu; các DM hành động
đêm tiếp theo nhắc lại mục tiêu cặp, không tiết lộ vai trò của người kia.

Điểm giữ nguyên: thắng phe +20, thắng Solo +30, thua -15, thưởng khi thắng
tối đa +10; ván hòa không cộng/trừ rank.

## Phạm vi giữ nguyên

Không sửa quyền, đăng ký, thời hạn, đặc quyền, lời trăn trối, biểu tượng VIP,
phí tạo phòng hay hoàn phí. Không khôi phục Event/Boss đã bị loại bỏ.
Các chuỗi replay/enum cũ vẫn được giữ để đọc lịch sử và phục hồi an toàn.

## Kiểm thử và áp dụng

Các test dùng Discord giả lập; dữ liệu rank/recovery dùng database tạm của
bộ test, không thay đổi database live. Có test cho badge set/xóa giữa ván,
END_ONLY không lộ phiếu, race chỉnh DM/bảng phiếu, các trường hợp thắng/rank
Tình Nhân, chuỗi chết thực tế qua game loop, kế nhiệm và giới hạn embed.

Chạy: `venv/Scripts/python.exe -m unittest discover -s tests -q`.

Chưa xác nhận trên Discord thật. Cần khởi động lại bot khi không có ván
đang chạy để nạp code mới; không reload giữa ván vì luồng recovery sẽ hủy
ván gián đoạn, không tính rank. Sau đó kiểm tra trực tiếp set/xóa badge trong
lượt bỏ phiếu của một ván mới và các DM trong một ván thử không tính rank.
