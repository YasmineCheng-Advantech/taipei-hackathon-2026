"""逐一下載 data/catalog.md 裡有直接網址的資料集，存一份樣本並印出欄位，用來把目錄的「待驗證」改成「已下載驗證」。

用法（在自己的電腦，雲端環境連不到這些網站）：
    python3 data/fetch/check_catalog.py
輸出：data/raw/catalog/<id>.<副檔名>（不進 git），以及每個資料集的狀態、大小、前幾個欄位。
每個網址只抓一次；即時資料的網址不要重複狂跑。
"""
import gzip
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


def fetch(url):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "taipei-hackathon-2026 catalog check"})
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read()
        ctype = r.headers.get("Content-Type", "")
    if body[:2] == b"\x1f\x8b":
        body = gzip.decompress(body)
    return body, ctype


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
    return "other", []


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ok = 0
    for name, url in URLS:
        try:
            body, ctype = fetch(url)
            kind, fields = describe(body)
            path = OUT / f"{name}.{kind}"
            path.write_bytes(body)
            ok += 1
            print(f"✓ {name}：{len(body) // 1024:,} KB，{kind}（{ctype}）\n  欄位：{', '.join(fields) or '（請打開樣本看）'}\n  樣本：{path}")
        except Exception as e:
            print(f"✗ {name}：{e}\n  {url}")
    print(f"\n{ok}/{len(URLS)} 個抓得到。抓得到的，把 data/catalog.md 的「⚠️」改成「✅ 日期」，欄位不對就改關鍵欄位。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
