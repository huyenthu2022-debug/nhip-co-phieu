"""Danh sách mã theo dõi và ngành. Sửa tự do để mở rộng."""

UNIVERSE = {
    "Ngân hàng": ["VCB", "BID", "CTG", "TCB", "MBB", "VPB", "ACB", "HDB", "STB", "TPB", "SHB", "VIB"],
    "Bất động sản": ["VHM", "VIC", "VRE", "NVL", "KDH", "DXG", "NLG", "PDR", "KBC"],
    "Chứng khoán": ["SSI", "VND", "HCM", "VCI", "SHS"],
    "Thép & vật liệu": ["HPG", "HSG", "NKG", "DGC"],
    "Bán lẻ & tiêu dùng": ["MWG", "PNJ", "MSN", "VNM", "SAB", "FRT", "DGW"],
    "Công nghệ": ["FPT", "CMG"],
    "Năng lượng": ["GAS", "PLX", "POW", "PVD", "PVS", "BSR"],
    "Công nghiệp & logistics": ["GVR", "VJC", "HVN", "GMD", "REE", "BCM"],
}

INDEX = "VNINDEX"


def all_symbols():
    return [s for syms in UNIVERSE.values() for s in syms]


def sector_of(symbol):
    for sector, syms in UNIVERSE.items():
        if symbol in syms:
            return sector
    return "Khác"
