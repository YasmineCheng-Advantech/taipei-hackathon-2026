"""逐一下載 data/catalog.md 裡有直接網址的資料集，存一份樣本並印出欄位，用來把目錄的「待驗證」改成「已下載驗證」。

用法（在自己的電腦，雲端環境連不到這些網站）：
    python3 data/fetch/check_catalog.py          # Windows：py data/fetch/check_catalog.py
輸出：data/raw/catalog/<id>.<副檔名>（不進 git），以及每個資料集的狀態、大小、前幾個欄位。
每個網址只抓一次；即時資料的網址不要重複狂跑。

兩種來源
- URLS：直接下載的網址。
- GOV_TW：data.gov.tw 的資料集編號。先查 data.gov.tw 的 API 拿到下載網址，再抓第一個 CSV／JSON 的開頭
  （月檔可能上百 MB，只讀前 MAX_BYTES）。API 格式若變了，會印出資料集頁面，改用瀏覽器手動下載。
"""
import csv
import gzip
import io
import json
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

OUT = Path(__file__).resolve().parents[1] / "raw" / "catalog"

URLS = [
    ("vd-live", "https://tcgbusfs.blob.core.windows.net/blobtisv/VDLive.xml"),
    ("vd-static", "https://tcgbusfs.blob.core.windows.net/blobtisv/VD.xml"),
    ("vd-getvd", "https://tcgbusfs.blob.core.windows.net/blobtisv/GetVD.xml.gz"),
    ("youbike", "https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json"),
    ("parking-available", "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_allavailable.json"),
    ("parking-desc", "https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_alldesc.json"),
    ("freeway-history", "https://tisvcloud.freeway.gov.tw/history/motc20/"),
]

# data.gov.tw 資料集編號（catalog.md 對應的題目寫在註解）
GOV_TW = [
    ("mrt-hourly", "128506"),      # A6 臺北捷運各站分時進出量統計（月檔）
    ("mrt-exits", "128428"),       # A3 臺北捷運車站出入口座標
    ("accident-stats", "135546"),  # A2／A4 臺北市交通事故統計（交通局）
    ("accident-a3", "135091"),     # A2／A4 臺北市 A3 交通事故資料（警察局）
]
GOV_TW_API = "https://data.gov.tw/api/v2/rest/dataset/{}"
MAX_BYTES = 2 * 1024 * 1024


def fetch(url, limit=None):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "taipei-hackathon-2026 catalog check"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read(limit) if limit else r.read()
        ctype = r.headers.get("Content-Type", "")
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body) if not limit else gzip.GzipFile(fileobj=io.BytesIO(body)).read1(limit)
    return body, ctype


def gov_tw_urls(dataset_id):
    """從 data.gov.tw API 找出這個資料集所有的下載網址，CSV 與 JSON 排前面。"""
    body, _ = fetch(GOV_TW_API.format(dataset_id))
    found = []

    def walk(x):
        if isinstance(x, dict):
            for k, v in x.items():
                if isinstance(v, str) and v.startswith("http") and "url" in k.lower() and "download" in k.lower():
                    found.append((str(x.get("resourceFormat", "")).lower(), v))
                else:
                    walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk(json.loads(body.decode("utf-8")))
    found.sort(key=lambda f: (f[0] not in ("csv", "json"), 0))
    return [u for _, u in found]


def describe(body):
    """回傳格式與前幾個欄位名稱。"""
    body = body.removeprefix(b"\xef\xbb\xbf").lstrip()
    head = body[:1]
    if head in (b"[", b"{"):
        d = json.loads(body.decode("utf-8"))
        if isinstance(d, dict):
            inner = next((v for v in d.values() if isinstance(v, list) and v and isinstance(v[0], dict)), None)
            return "json", list((inner[0] if inner else d).keys())[:12]
        return "json", list(d[0].keys())[:12] if d and isinstance(d[0], dict) else []
    if head == b"<":
        try:
            root = ET.fromstring(body)
        except ET.ParseError:
            return "html", []
        return "xml", [e.tag.split("}")[-1] for e in root.iter() if len(e) == 0][:12]
    for enc in ("utf-8", "cp950"):  # 市府的 CSV 常是 Big5
        try:
            first = body.decode(enc, errors="strict" if enc == "utf-8" else "replace").splitlines()[0]
        except (UnicodeDecodeError, IndexError):
            continue
        row = next(csv.reader([first]))
        if len(row) > 1:
            return "csv", row[:12]
    return "other", []


def save(name, url, limit=None):
    body, ctype = fetch(url, limit)
    kind, fields = describe(body)
    path = OUT / f"{name}.{kind}"
    path.write_bytes(body)
    part = "（只抓開頭）" if limit and len(body) >= limit else ""
    print(f"✓ {name}：{len(body) // 1024:,} KB{part}，{kind}（{ctype}）\n  欄位：{', '.join(fields) or '（請打開樣本看）'}\n  樣本：{path}\n  網址：{url}")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 命令列預設 cp950，印 ✓ 會出錯
    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, url in URLS:
        try:
            save(name, url)
            ok += 1
        except Exception as e:
            print(f"✗ {name}：{e}\n  {url}")
    for name, dataset_id in GOV_TW:
        page = f"https://data.gov.tw/dataset/{dataset_id}"
        try:
            urls = gov_tw_urls(dataset_id)
            if not urls:
                raise ValueError("API 回應裡找不到下載網址")
            save(name, urls[0], MAX_BYTES)
            ok += 1
        except Exception as e:
            print(f"✗ {name}：{e}\n  改用瀏覽器打開 {page}，下載一個檔案看欄位")
    total = len(URLS) + len(GOV_TW)
    print(f"\n{ok}/{total} 個抓得到。抓得到的，把 data/catalog.md 的「⚠️」改成「✅ 日期」，欄位不對就改關鍵欄位。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
