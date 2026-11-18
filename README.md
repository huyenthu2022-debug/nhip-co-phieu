# Nhịp Cổ Phiếu

Web tín hiệu kỹ thuật cho cổ phiếu Việt Nam: xu hướng ngắn/trung hạn, sức mạnh tương đối (RS 1–99),
điểm sức mạnh 0–10, dòng tiền, động lượng đa khung (ngày/tuần/tháng), tín hiệu mua/bán kèm dừng lỗ,
mục tiêu T1/T2, và nhật ký backtest so với mua và nắm giữ.

> Tín hiệu tính tự động từ dữ liệu giá, không phải khuyến nghị đầu tư.

## Cấu trúc

```
engine/universe.py     danh sách dự phòng (bản đầy đủ lấy tự động toàn HOSE/HNX/UPCoM kèm ngành ICB)
engine/indicators.py   chỉ báo, điểm sức mạnh, quy tắc mua/bán, backtest
engine/build.py        tính toán, ghi web/data/signals.json và web/data/charts/<MÃ>.json
engine/sources.py      lấy giá từ API công khai (DNSE, Vietcap, TCBS)
engine/gold.py         tín hiệu mua/bán vàng XAUUSD (H1 theo xu hướng H4), ghi web/data/gold.json
web/gold.js            tab Vàng XAUUSD: biểu đồ TradingView OANDA:XAUUSD, giá trực tiếp, cảnh báo
web/index.html         giao diện (một file, không cần build)
.github/workflows/     tự cập nhật hằng ngày và đăng lên GitHub Pages
```

## Chạy trên máy

```bash
pip install -r requirements.txt
python engine/build.py          # dữ liệu thật từ API công khai DNSE, Vietcap, TCBS
python engine/build.py --demo   # dữ liệu mô phỏng, không cần mạng
python engine/build.py --limit 100  # thử nhanh với 100 mã
cd web && python -m http.server 8000
# mở http://localhost:8000
```

## Vàng XAUUSD

Tab **Vàng XAUUSD** báo điểm MUA/BÁN theo hệ 3 khung: H4 xác định xu hướng (giá > EMA50 > EMA200 là tăng),
H1 xem xét vùng hồi (EMA20 > EMA50 và giá vừa chạm EMA20), M15 vào lệnh sau khi giá quét thanh khoản: chọc thủng
đáy (đỉnh) thấp nhất của 20 nến M15 trước đó rồi đóng cửa quay lại bằng nến cùng chiều lệnh. Dừng lỗ sau râu nến
quét, 15–20 giá (bỏ tín hiệu nếu cần rộng hơn 20 giá). Lọc chất lượng: MUA chỉ khi RSI M15 ≤ 50 (BÁN khi ≥ 50) và bỏ
nến mở từ 21h đến trước 3h giờ VN. Vào lệnh bằng **lệnh chờ** tại mức hồi 50% từ giá đóng cửa về râu nến quét (huỷ nếu
4 nến M15 chưa khớp). Tới 1:1 dời dừng lỗ về giá vào; từ 1:3 kéo dừng lỗ luôn cách mức lãi cao nhất 1,5R; chốt hết ở 1:8.
Kiểm định 2 năm nến M15 PAXG/USDT: 101 lệnh, thua 35%, hoà 39%, thắng 27% với lệnh thắng trung bình +3,9R; +0,70R mỗi lệnh,
hệ số lợi nhuận 3,01, sụt giảm lớn nhất 6,4R (vào ngay giá đóng cửa, chốt cố định 1:3: 148 lệnh, +0,37R, hệ số 1,93).
**Hệ 2 (song song): phá đỉnh/đáy 20 nến H1 theo H4.** Nến H1 đóng cửa trên đỉnh (dưới đáy) 20 nến H1 trước đó cùng chiều
xu hướng H4 thì vào ngay; dừng lỗ 2 ATR H1; cùng cách dời SL/kéo SL/chốt tối đa 1:8. Đứng đầu khi so 12 phương pháp:
2 năm PAXG 167 lệnh, +0,70R mỗi lệnh, hệ số 2,61; kiểm chứng 2 năm GC=F 150 lệnh, +0,53R, hệ số 2,18.
Workflow tính lại mỗi 15 phút từ tối Chủ nhật đến tối thứ 6 (giờ UTC). Giá trực tiếp trên trang lấy từ gold-api.com.
Khi trang đang mở, tín hiệu được tính **realtime** ngay trong trình duyệt: 5 giây sau mỗi nến M15 đóng, trang tải nến
M15/H1/H4 PAXG/USDT từ Binance (dời theo giá XAU giao ngay) và chạy cùng quy tắc với `engine/gold.py`, rồi báo ngay.
`engine/rt_check.js` chạy phần tính đó bằng Node để so khớp với engine Python (đã khớp 100% tín hiệu và lệnh).

Chạy thẳng trên TradingView: `tradingview/nhip-vang.pine` là cùng quy tắc viết bằng Pine Script cho OANDA:XAUUSD khung 15 phút.
Mở Pine Editor, dán file, bấm Add to chart; rồi Create alert → điều kiện "Nhịp Vàng" → "Any alert() function call" để nhận
báo vào lệnh, 1:1, dừng lỗ, chốt lời qua app/email TradingView (webhook cần gói trả phí).

Nhận tín hiệu qua Telegram (tuỳ chọn): tạo bot với @BotFather, nhắn cho bot một tin, lấy chat id, rồi thêm hai
secret `TELEGRAM_BOT_TOKEN` và `TELEGRAM_CHAT_ID` trong Settings → Secrets and variables → Actions.

```bash
python engine/gold.py          # dữ liệu thật
python engine/gold.py --demo   # dữ liệu mô phỏng
```

## Đưa lên mạng miễn phí (GitHub Pages)

1. Tạo repo GitHub, đẩy toàn bộ thư mục này lên.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → "Cập nhật tín hiệu" → Run workflow. Sau đó nó tự chạy 15:45 mỗi ngày giao dịch.

Lưu ý: máy chủ GitHub đặt ở nước ngoài, một số nguồn dữ liệu VN đôi khi chặn IP nước ngoài.
Nếu workflow lỗi khi lấy dữ liệu, chạy `build.py` trên máy ở VN rồi commit `web/data/signals.json`.

## Hướng phát triển

- Cảnh báo Telegram cho cổ phiếu (vàng đã có), Zalo.
- Khung giờ (H1) cho động lượng đa khung, cần dữ liệu intraday.
- Danh mục mẫu theo chủ đề, tín hiệu phái sinh VN30F.
