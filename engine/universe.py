"""Danh sách mã. Bản đầy đủ lấy tự động từ sources.listing(); danh sách dưới đây
chỉ dùng khi không lấy được danh sách trực tuyến và cho chế độ --demo."""

INDEX = "VNINDEX"

FALLBACK = {
    "Ngân hàng": ["VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "HDB", "STB", "TPB", "SHB", "VIB"],
    "Bất động sản": ["VHM", "VIC", "VRE", "NVL", "KDH", "DXG", "NLG", "PDR", "KBC"],
    "Dịch vụ tài chính": ["SSI", "VND", "HCM", "VCI", "SHS"],
    "Tài nguyên cơ bản": ["HPG", "HSG", "NKG"],
    "Hóa chất": ["DGC"],
    "Bán lẻ": ["MWG", "PNJ", "FRT", "DGW"],
    "Thực phẩm và đồ uống": ["MSN", "VNM", "SAB"],
    "Công nghệ Thông tin": ["FPT", "CMG"],
    "Dầu khí": ["GAS", "PLX", "PVD", "PVS", "BSR"],
    "Điện, nước & xăng dầu khí đốt": ["POW", "REE"],
    "Hàng & Dịch vụ Công nghiệp": ["GVR", "GMD", "BCM"],
    "Du lịch và Giải trí": ["VJC", "HVN"],
}
FALLBACK_EXCHANGE = {s: "HOSE" for syms in FALLBACK.values() for s in syms}
FALLBACK_EXCHANGE.update({"SHS": "HNX", "PVS": "HNX", "BSR": "UPCOM"})


def fallback_listing():
    return [{"sym": s, "exchange": FALLBACK_EXCHANGE[s], "sector": sec, "industry": sec, "name": ""}
            for sec, syms in FALLBACK.items() for s in syms]
