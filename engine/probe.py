"""Kiểm tra nhanh các API dữ liệu từ máy chạy GitHub Actions (chỉ in ra, không ghi gì)."""
import json
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from sources import HEADERS, VCI_HEADERS  # noqa: E402


def call(name, url, body=None, extra=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {**HEADERS, **(extra or {}), **({"Content-Type": "application/json"} if data else {})}
    try:
        with urllib.request.urlopen(urllib.request.Request(url, data=data, headers=h), timeout=25) as r:
            txt = r.read().decode("utf-8", "replace")
            print(f"== {name}: HTTP {r.status}, {len(txt)} ký tự")
    except urllib.error.HTTPError as e:
        txt = e.read().decode("utf-8", "replace")
        print(f"== {name}: HTTP {e.code}")
    except Exception as e:
        print(f"== {name}: LỖI {e}")
        return None
    print(txt[:700].replace("\n", " "))
    try:
        return json.loads(txt)
    except Exception:
        return None


j = call("vci getAll", "https://trading.vietcap.com.vn/api/price/symbols/getAll", extra=VCI_HEADERS)
if isinstance(j, list):
    print("types:", sorted({str(r.get("type")) for r in j}), "boards:", sorted({str(r.get("board")) for r in j}))
    print("keys:", list(j[0].keys()))
call("vci graphql", "https://trading.vietcap.com.vn/data-mt/graphql",
     {"query": "{ CompaniesListingInfo { ticker organName icbName2 icbName3 } }", "variables": {}}, VCI_HEADERS)
call("vci graphql full", "https://trading.vietcap.com.vn/data-mt/graphql",
     {"query": "{\n  CompaniesListingInfo {\n    ticker\n    organName\n    enOrganName\n    icbName3\n    enIcbName3\n    icbName2\n    enIcbName2\n    icbName4\n    enIcbName4\n    comTypeCode\n    icbCode1\n    icbCode2\n    icbCode3\n    icbCode4\n    __typename\n  }\n}\n", "variables": {}},
     VCI_HEADERS)
g = call("vci gap-chart 3 mã", "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
         {"timeFrame": "ONE_DAY", "symbols": ["FPT", "HPG", "VCB"], "to": int(time.time()) + 86400, "countBack": 5}, VCI_HEADERS)
if isinstance(g, list):
    for d in g:
        print(" ", {k: (v[:2] if isinstance(v, list) else v) for k, v in d.items()})
call("vci gap-chart 1 mã", "https://trading.vietcap.com.vn/api/chart/OHLCChart/gap-chart",
     {"timeFrame": "ONE_DAY", "symbols": ["FPT"], "to": int(time.time()) + 86400, "countBack": 3}, VCI_HEADERS)
call("vndirect stocks", "https://api-finfo.vndirect.com.vn/v4/stocks?q=type:stock~status:listed&size=5")
call("vndirect industry", "https://api-finfo.vndirect.com.vn/v4/industry_classification?q=industryLevel:2&size=5")
call("tcbs overview", "https://apipubaws.tcbs.com.vn/tcanalysis/v1/ticker/FPT/overview")
call("ssi hose", "https://iboard-query.ssi.com.vn/stock/exchange/hose")
