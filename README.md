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

## Đưa lên mạng miễn phí (GitHub Pages)

1. Tạo repo GitHub, đẩy toàn bộ thư mục này lên.
2. Settings → Pages → Source: **GitHub Actions**.
3. Actions → "Cập nhật tín hiệu" → Run workflow. Sau đó nó tự chạy 15:45 mỗi ngày giao dịch.

Lưu ý: máy chủ GitHub đặt ở nước ngoài, một số nguồn dữ liệu VN đôi khi chặn IP nước ngoài.
Nếu workflow lỗi khi lấy dữ liệu, chạy `build.py` trên máy ở VN rồi commit `web/data/signals.json`.

## Hướng phát triển

- Cảnh báo realtime qua Telegram/Zalo khi có tín hiệu mới (cần một máy chủ chạy liên tục).
- Khung giờ (H1) cho động lượng đa khung, cần dữ liệu intraday.
- Danh mục mẫu theo chủ đề, tín hiệu phái sinh VN30F.
