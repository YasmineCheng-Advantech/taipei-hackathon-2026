"""從高公局交通資料庫（tisvcloud）抓國道 VD，補上國 1 內湖交流道的缺口。不用 TDX 金鑰，而且有歷史檔，可以事後補抓。

要在自己的電腦跑：雲端環境與 GitHub Actions 連 tisvcloud 會逾時（推測只開放國內 IP）。

用法
    python3 data/fetch/fetch_freeway_vd.py --probe
        先確認網站連得到、檔案路徑對不對
    python3 data/fetch/fetch_freeway_vd.py --list
        下載國道偵測器清單，列出離內湖交流道最近的偵測器，從中挑出國 1 內湖交流道下匝道（往內湖）的 VDID
    python3 data/fetch/fetch_freeway_vd.py --vd <VDID>[,<VDID>…] --date 2026-10-20 --date 2026-10-21 …
        下載這幾天 07:00–10:30 每分鐘的歷史檔，取出指定偵測器，輸出 data/raw/vd_freeway_targets.csv
接著（欄位和臺北市的收集程式相同，可以一起彙整）
    python3 data/processed/build_vd_15min.py data/raw/vd_taipei_targets.csv data/raw/vd_freeway_targets.csv
    再把 data/mock/gen_t4_morning.py 的 nh1-neihu-ic 改成 kind="observed"、detector="<VDID>"

注意
- 檔案路徑是依交通部即時路況標準 v2.0（motc20）的慣例寫的，還沒實際連上確認；--probe 失敗時，
  到 https://tisvcloud.freeway.gov.tw/history/motc20/ 看實際的資料夾與檔名，改下面的 URL 常數。
- 每分鐘一個檔，一天 07:00–10:30 約 210 個，每個檔之間停 0.3 秒；下載過的檔案存在 data/raw/freeway/，重跑不會再抓。
- 同一支偵測器同一個 DataCollectTime 只留一筆。國道 VD 不論是 1 分鐘或 5 分鐘統計，
  build_vd_15min.py 把一格裡不重複的讀數加總，都會得到 15 分鐘的車數。
"""
import argparse
import csv
import datetime as dt
import gzip
import math
import ssl
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = "https://tisvcloud.freeway.gov.tw/history/motc20"
STATIC_URLS = [f"{BASE}/VD.xml.gz", f"{BASE}/VD.xml"]
LIVE_URLS = [f"{BASE}/VDLive.xml.gz", f"{BASE}/VDLive.xml"]
HISTORY_URL = BASE + "/VD/{day}/VDLive_{hhmm}.xml.gz"

ROOT = Path(__file__).resolve().parents[1] / "raw"
CACHE = ROOT / "freeway"
OUT = ROOT / "vd_freeway_targets.csv"
# 欄位與 collect_vd.py 的 vd_taipei_targets.csv 相同
CSV_FIELDS = ['poll_time', 'entrance', 'vdid', 'link_id', 'status', 'collect_time',
              'lanes', 'vol_M', 'vol_S', 'vol_L', 'vol_T', 'speed', 'occupancy']
NEIHU = (25.0735, 121.5960)  # 內湖交流道的大略位置（與 gen_t4_morning.py 相同），只用來排序候選
START, END = dt.time(7, 0), dt.time(10, 30)

# Python 3.13 起預設多一項嚴格憑證檢查，data.gov.tw、freeway.gov.tw 的憑證缺 Subject Key Identifier 會被擋
# （CERTIFICATE_VERIFY_FAILED: Missing Subject Key Identifier）。只關掉這一項，憑證鏈與網域照樣驗證。
SSL_CTX = ssl.create_default_context()
SSL_CTX.verify_flags &= ~getattr(ssl, "VERIFY_X509_STRICT", 0)


def get(url, timeout=60):
    req = urllib.request.Request(url, headers={"Accept-Encoding": "gzip", "User-Agent": "taipei-hackathon-2026"})
    with urllib.request.urlopen(req, timeout=timeout, context=SSL_CTX) as r:
        body = r.read()
    return gzip.decompress(body) if body[:2] == b"\x1f\x8b" else body


def get_first(urls):
    for u in urls:
        try:
            return u, get(u)
        except Exception as e:
            print(f"  {u}：{e}", file=sys.stderr)
    return None, None


def local(tag):
    return tag.rsplit("}", 1)[-1]


def child(e, name):
    return next((c for c in e if local(c.tag) == name), None)


def text(e, *path):
    for name in path:
        e = child(e, name) if e is not None else None
    return e.text.strip() if e is not None and e.text else ""


def km(a, b):
    dy = (a[0] - b[0]) * 111.0
    dx = (a[1] - b[1]) * 111.0 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def probe():
    for name, urls in (("偵測器清單", STATIC_URLS), ("即時資料", LIVE_URLS)):
        u, body = get_first(urls)
        print(f"{'✓' if body else '✗'} {name}：" + (f"{u}（{len(body) // 1024:,} KB）" if body else "都連不到"))
    y = dt.date.today() - dt.timedelta(days=1)
    u = HISTORY_URL.format(day=f"{y:%Y%m%d}", hhmm="0800")
    try:
        body = get(u)
        print(f"✓ 歷史檔：{u}（{len(body) // 1024:,} KB）")
    except Exception as e:
        print(f"✗ 歷史檔：{u}：{e}")


def list_candidates(n=40):
    u, body = get_first(STATIC_URLS)
    if not body:
        sys.exit("下載不到偵測器清單，先跑 --probe")
    rows = []
    for v in ET.fromstring(body).iter():
        if local(v.tag) != "VD":
            continue
        road = text(v, "RoadName")
        try:
            pos = (float(text(v, "PositionLat")), float(text(v, "PositionLon")))
        except ValueError:
            continue
        sec = f"{text(v, 'RoadSection', 'Start')}→{text(v, 'RoadSection', 'End')}"
        rows.append((km(pos, NEIHU), text(v, "VDID"), road, text(v, "LocationMile"), sec,
                     text(v, "DetectionLinks", "DetectionLink", "RoadDirection"), text(v, "LocationType"), pos))
    rows.sort(key=lambda r: (("內湖" not in r[4]), r[0]))
    print(f"{u}：共 {len(rows)} 支偵測器，依「路段名有內湖」與離內湖交流道的距離排序，前 {n} 支：")
    print("距離km  VDID                          道路      里程      方向  位置類型  路段")
    for d, vid, road, mile, sec, direc, loc, _ in rows[:n]:
        print(f"{d:6.1f}  {vid:28s}  {road:8s}  {mile:8s}  {direc:4s}  {loc:8s}  {sec}")
    print("\n挑「下匝道、往內湖」的那支（路段名或 VDID 通常看得出出口匝道），再用 --vd 抓歷史資料。")


def parse_live(body, targets):
    """與 collect_vd.py 的 parse_taipei 相同的算法：每個 LinkFlow 一列，車速依各車道車輛數加權。"""
    rows = []
    for v in ET.fromstring(body).iter():
        if local(v.tag) != "VDLive" or text(v, "VDID") not in targets:
            continue
        vid = text(v, "VDID")
        for lf in (e for e in v.iter() if local(e.tag) == "LinkFlow"):
            vol, spd, occ, n = {}, [], [], 0
            for ln in (e for e in lf.iter() if local(e.tag) == "Lane"):
                n += 1
                lane_vol = 0
                for vh in (e for e in ln.iter() if local(e.tag) == "Vehicle"):
                    k = text(vh, "VehicleType")
                    c = max(0, int(float(text(vh, "Volume") or 0)))
                    vol[k] = vol.get(k, 0) + c
                    lane_vol += c
                spd.append((float(text(ln, "Speed") or -99), lane_vol))
                occ.append(float(text(ln, "Occupancy") or -99))
            ok_spd = [(s, c) for s, c in spd if s >= 0 and c > 0]
            ok_occ = [o for o in occ if o >= 0]
            w = sum(c for _, c in ok_spd)
            rows.append(dict(
                entrance=targets[vid], vdid=vid, link_id=text(lf, "LinkID"), status=text(v, "Status"),
                collect_time=text(v, "DataCollectTime"), lanes=n,
                vol_M=vol.get("M", 0), vol_S=vol.get("S", 0), vol_L=vol.get("L", 0), vol_T=vol.get("T", 0),
                speed=round(sum(s * c for s, c in ok_spd) / w, 1) if w else "",
                occupancy=round(sum(ok_occ) / len(ok_occ), 1) if ok_occ else ""))
    return rows


def fetch_history(vdids, days, start, end):
    targets = {v: "國1 內湖交流道" for v in vdids}
    seen, out, missing = set(), [], 0
    if OUT.exists():
        with open(OUT, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                seen.add((r["vdid"], r["collect_time"]))
    for day in days:
        t = dt.datetime.combine(day, start)
        while t.time() <= end:
            hhmm = f"{t:%H%M}"
            path = CACHE / f"{day:%Y%m%d}" / f"VDLive_{hhmm}.xml.gz"
            if not path.exists():
                try:
                    body = get(HISTORY_URL.format(day=f"{day:%Y%m%d}", hhmm=hhmm))
                except Exception as e:
                    missing += 1
                    print(f"  {day} {hhmm} 下載不到：{e}", file=sys.stderr)
                    t += dt.timedelta(minutes=1)
                    continue
                path.parent.mkdir(parents=True, exist_ok=True)
                with gzip.open(path, "wb") as f:
                    f.write(body)
                time.sleep(0.3)
            with gzip.open(path, "rb") as f:
                body = f.read()
            for r in parse_live(body, targets):
                key = (r["vdid"], r["collect_time"])
                if key not in seen:
                    seen.add(key)
                    out.append({"poll_time": f"{day} {t:%H:%M}", **r})
            t += dt.timedelta(minutes=1)
        print(f"{day}：累計 {len(out)} 筆新讀數")
    new = not OUT.exists()
    with open(OUT, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new:
            w.writeheader()
        w.writerows(out)
    found = {r["vdid"] for r in out}
    print(f"寫入 {OUT}：{len(out)} 筆；找到 {len(found)}/{len(vdids)} 支偵測器" + (f"；{missing} 個檔下載不到" if missing else ""))
    if out and not found >= set(vdids):
        print(f"沒找到：{', '.join(sorted(set(vdids) - found))}，檢查 VDID 是否正確（--list）")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--probe", action="store_true", help="確認網站與檔案路徑")
    ap.add_argument("--list", action="store_true", help="列出內湖交流道附近的國道偵測器")
    ap.add_argument("--vd", help="要抓的 VDID，多支用逗號分開")
    ap.add_argument("--date", action="append", type=dt.date.fromisoformat, help="日期，可重複，例如 --date 2026-10-20")
    ap.add_argument("--start", type=dt.time.fromisoformat, default=START)
    ap.add_argument("--end", type=dt.time.fromisoformat, default=END)
    args = ap.parse_args()
    if args.probe:
        probe()
    elif args.list:
        list_candidates()
    elif args.vd and args.date:
        fetch_history([v.strip() for v in args.vd.split(",") if v.strip()], args.date, args.start, args.end)
    else:
        print(__doc__.strip())
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
