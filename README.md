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
quét, 15–20 giá (bỏ lệnh nếu cần rộng hơn 20 giá); giá đi được 1:1 thì dời dừng lỗ về giá vào; chốt lời ở R:R 1:3.
Chọn sau khi so khoảng 60 cách trên 2 năm nến M15 PAXG/USDT: 197 lệnh, +0,21R mỗi lệnh, hệ số lợi nhuận 1,48, sụt giảm lớn nhất 9R (bản 1:4: +0,31R nhưng dồn lãi vào nửa đầu; 1:3 đều hơn và tốt hơn trên 60 ngày gần nhất).
Workflow tính lại mỗi 15 phút từ tối Chủ nhật đến tối thứ 6 (giờ UTC). Giá trực tiếp trên trang lấy từ gold-api.com.
Khi trang đang mở, tín hiệu được tính **realtime** ngay trong trình duyệt: 5 giây sau mỗi nến M15 đóng, trang tải nến
M15/H1/H4 PAXG/USDT từ Binance (dời theo giá XAU giao ngay) và chạy cùng quy tắc với `engine/gold.py`, rồi báo ngay.
`engine/rt_check.js` chạy phần tính đó bằng Node để so khớp với engine Python (đã khớp 100% tín hiệu và lệnh).

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
