# Bot Bàn Giao Nhóm (Telegram + Google Sheets)

Bot cho nhóm 4 người: **Quý** (người giao cố định), **Tân**, **Hương**, **Thịnh**.

- **📋 Giao nhiệm vụ** — chỉ Quý dùng được. Nhập tên nhiệm vụ, chọn 1-4 người thực hiện. Ghi vào sheet `GiaoNhiemVu`.
- **📦 Bàn giao vật chất** — chỉ Quý tạo. Cả 4 người bấm nút riêng của mình để xác nhận đã nhận. Ghi vào sheet `BanGiaoVatChat`, mỗi người 1 cột, ai bấm nút của người đó thì mới tính (bot kiểm tra đúng Telegram ID).

Làm theo đúng thứ tự các bước dưới đây — tổng cộng khoảng 20-30 phút, không cần biết lập trình.

---

## Bước 1 — Tạo bot trên Telegram (lấy BOT_TOKEN)

1. Mở Telegram, tìm **@BotFather**, bấm Start.
2. Gửi lệnh `/newbot`.
3. Đặt tên hiển thị (VD: `Bot Bàn Giao Nhóm`).
4. Đặt username, phải kết thúc bằng `bot` (VD: `bangiaonhom_bot`).
5. BotFather trả về một chuỗi dạng `123456789:AAxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx` — đây là **BOT_TOKEN**, lưu lại.

## Bước 2 — Lấy User ID của 4 thành viên

Mỗi người (Quý, Tân, Hương, Thịnh) tự làm việc này:
1. Mở Telegram, tìm **@userinfobot**, bấm Start.
2. Bot trả về `Id: 123456789` — gửi số này cho Quý để điền vào cấu hình.

## Bước 3 — Tạo Google Sheet lưu dữ liệu

1. Vào [sheets.google.com](https://sheets.google.com), tạo sheet mới, đặt tên VD `Bàn Giao Nhóm`.
2. Nhìn trên URL: `https://docs.google.com/spreadsheets/d/ĐOẠN_NÀY_LÀ_ID/edit` — copy đoạn ID đó, đây là **SPREADSHEET_ID**.
3. Bot sẽ tự tạo 2 tab `GiaoNhiemVu` và `BanGiaoVatChat` khi chạy lần đầu, không cần tạo tay.

## Bước 4 — Tạo Google Service Account (để bot ghi được vào Sheet)

1. Vào [console.cloud.google.com](https://console.cloud.google.com), tạo project mới (hoặc dùng project có sẵn).
2. Vào **APIs & Services → Library**, tìm **Google Sheets API**, bấm **Enable**.
3. Vào **APIs & Services → Credentials → Create Credentials → Service account**.
4. Đặt tên tuỳ ý (VD `bangiao-bot`), bấm **Create and Continue** → **Done**.
5. Trong danh sách Service Accounts, bấm vào account vừa tạo → tab **Keys → Add Key → Create new key → JSON** → tải file `.json` về máy.
6. Mở file `.json` đó bằng Notepad, copy **toàn bộ nội dung** — đây là **GOOGLE_CREDENTIALS_JSON**.
7. Trong file JSON có dòng `"client_email": "xxx@xxx.iam.gserviceaccount.com"` — copy email này.
8. Quay lại Google Sheet đã tạo ở Bước 3, bấm **Share**, dán email service account vào, chọn quyền **Editor**, bấm Send/Share.

## Bước 5 — Đưa code lên GitHub

1. Tạo tài khoản [github.com](https://github.com) nếu chưa có.
2. Tạo một repository mới (VD `bangiao-bot`), để **Private** cho an toàn.
3. Upload toàn bộ các file trong thư mục `telegram-bot/` này lên repo (kéo-thả trên giao diện web GitHub cũng được, mục "Add file → Upload files"). **Không upload file `.env`** nếu bạn có tạo nó — chỉ upload `.env.example`.

## Bước 6 — Deploy lên Render (miễn phí)

1. Vào [render.com](https://render.com), đăng ký bằng tài khoản GitHub.
2. Bấm **New → Web Service**, chọn repo `bangiao-bot` vừa tạo.
3. Render tự nhận diện `render.yaml` — nếu không, điền tay:
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python bot.py`
   - **Plan:** Free
4. Ở mục **Environment Variables**, thêm từng biến (lấy giá trị từ các bước trên):
   - `BOT_TOKEN`
   - `QUY_ID`, `TAN_ID`, `HUONG_ID`, `THINH_ID`
   - `GOOGLE_CREDENTIALS_JSON` (dán nguyên nội dung file JSON)
   - `SPREADSHEET_ID`
   - `WEBHOOK_URL` — điền tạm `https://ten-app-cua-ban.onrender.com` (Render cho biết tên chính xác sau khi tạo xong, quay lại sửa nếu khác)
5. Bấm **Create Web Service**, chờ Render build (~2-3 phút).
6. Sau khi trạng thái là **Live**, kiểm tra lại URL thật của app (góc trên bên trái Render), nếu khác với `WEBHOOK_URL` bạn điền tạm thì sửa lại biến này cho đúng rồi **Manual Deploy → Deploy latest commit**.

> **Lưu ý gói miễn phí của Render:** app sẽ "ngủ" sau ~15 phút không có ai nhắn tin, lần nhắn đầu tiên sau đó bot phản hồi chậm khoảng 30-50 giây do phải "thức dậy". Nếu nhóm cần bot phản hồi tức thì mọi lúc, có thể nâng cấp lên gói trả phí thấp nhất của Render (~7 USD/tháng) sau này — không cần đổi code.

## Bước 7 — Thêm bot vào nhóm và dùng thử

1. Mở nhóm Telegram của 4 người, thêm bot vào (tìm theo username đã đặt ở Bước 1).
2. Ai cũng có thể gõ `/start` để hiện menu.
3. Đ/c Quý bấm **📋 Giao nhiệm vụ**, nhập tên nhiệm vụ, chọn người thực hiện, bấm Xong.
4. Đ/c Quý bấm **📦 Bàn giao vật chất**, nhập tên vật cần giao — 4 nút hiện ra, mỗi người tự bấm nút tên mình để xác nhận (bot chặn nếu bấm nhầm nút của người khác).
5. Mở lại Google Sheet để xem dữ liệu được ghi tự động vào 2 tab.

---

## Chạy thử ở máy tính cá nhân trước khi deploy (tuỳ chọn)

```bash
pip install -r requirements.txt
cp .env.example .env
# rồi điền các giá trị thật vào file .env
python -c "from dotenv import load_dotenv; load_dotenv()" # hoặc thêm load_dotenv() đầu bot.py khi test local
python bot.py
```

Khi chạy local và **không** đặt `WEBHOOK_URL`, bot tự chạy ở chế độ polling — dùng để test nhanh trước khi đưa lên Render.
