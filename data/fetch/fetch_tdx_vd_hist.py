"""從 TDX 補抓臺北市 VD 的歷史資料（每 1 分鐘一筆），整理成和 collect_vd.py 一樣格式的 5 分鐘讀數。

TDX 的歷史資料一次回一整天、全臺北約 650 支 VD，約 1.1 GB；這支程式邊下載邊過濾，只留 TARGETS 那 8 支，
存成每天一個小檔，不用存 1.1 GB。前一天的資料隔天清晨才會出現，當天抓不到當天。

需要 TDX 會員的金鑰：環境變數 TDX_CLIENT_ID、TDX_CLIENT_SECRET，或寫在 repo 根目錄的 .env（不會進 git）。

用法（在自己的電腦；雲端環境連不到 TDX）
    python3 data/fetch/fetch_tdx_vd_hist.py                            # 最近 30 天（到昨天），週末也抓
    python3 data/fetch/fetch_tdx_vd_hist.py --from 2026-09-22 --to 2026-10-23
    python3 data/fetch/fetch_tdx_vd_hist.py --all-vd                   # 全臺北的 VD 都留（每天約幾十 MB）
已經抓過的日期不會重抓，中斷了重跑就會接著抓。抓完再跑 python3 data/processed/build_all.py。

輸出（data/raw/，不進 git）
- tdx_vd_hist/minute/YYYYMMDD.csv.gz   每支偵測器、每個路段、每分鐘一列（TDX 的 Dates 那一天）
- tdx_vd_hist/vd_tdx_targets.csv       彙整成 5 分鐘讀數，欄位和 vd_taipei_targets.csv 一樣，build_all.py 會自動讀
"""
import argparse
import csv
import datetime as dt
import gzip
import io
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from collect_vd import CSV_FIELDS, ROOT, TARGETS, TDX_TOKEN_URL, TPE, load_env  # noqa: E402

HIST_URL = 'https://tdx.transportdata.tw/api/historical/v2/Historical/Road/Traffic/Live/VD/City/Taipei?Dates={}&$format=JSON'
OUT = ROOT / 'tdx_vd_hist'
MINUTE = OUT / 'minute'
EXPORT = OUT / 'vd_tdx_targets.csv'
MIN_FIELDS = ['vdid', 'link_id', 'status', 'minute', 'lanes', 'vol_M', 'vol_S', 'vol_L', 'vol_T',
              'spd_w', 'spd_n', 'occ_sum', 'occ_n']
GAP = 13  # 秒；一般會員每分鐘最多 5 次


class Token:
    def __init__(self):
        self.value, self.expires = None, 0

    def get(self):
        if self.value and time.time() < self.expires - 300:
            return self.value
        data = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': os.environ['TDX_CLIENT_ID'],
                                       'client_secret': os.environ['TDX_CLIENT_SECRET']}).encode()
        req = urllib.request.Request(TDX_TOKEN_URL, data=data,
                                     headers={'Content-Type': 'application/x-www-form-urlencoded'})
        with urllib.request.urlopen(req, timeout=60) as r:
            d = json.loads(r.read())
        self.value, self.expires = d['access_token'], time.time() + d.get('expires_in', 86400)
        return self.value


def records(stream):
    """TDX 回的是 NDJSON（一行一筆，開頭有 BOM）；也容忍 JSON 陣列一行一筆的寫法。"""
    for raw in io.TextIOWrapper(stream, encoding='utf-8-sig'):
        line = raw.strip().lstrip('[').rstrip(']').rstrip(',').strip()
        if line.startswith('{'):
            yield line


def lane_vehicles(lane, lf):
    return lane.get('Vehicles') or lf.get('Vehicles') or []


def parse(stream, keep_all):
    """→ 每支偵測器、每個路段、每分鐘一列（彙總各車道）。"""
    rows = []
    for line in records(stream):
        if not keep_all and not any(f'"{v}"' in line for v in TARGETS):
            continue  # 先用字串過濾，不用每一行都解析 JSON
        v = json.loads(line)
        vid = v.get('VDID')
        if not keep_all and vid not in TARGETS:
            continue
        t = dt.datetime.fromisoformat(v['DataCollectTime']).astimezone(TPE)
        for lf in v.get('LinkFlows') or []:
            vol = defaultdict(int)
            spd_w = spd_n = occ_sum = occ_n = 0.0
            lanes = lf.get('Lanes') or []
            for ln in lanes:
                lane_vol = 0
                for vh in lane_vehicles(ln, lf):
                    c = max(0, int(float(vh.get('Volume') or 0)))
                    vol[vh.get('VehicleType')] += c
                    lane_vol += c
                s, o = float(ln.get('Speed', -99)), float(ln.get('Occupancy', -99))
                if s >= 0 and lane_vol > 0:  # 和 collect_vd.py 一樣，車速用車輛數加權
                    spd_w += s * lane_vol
                    spd_n += lane_vol
                if o >= 0:
                    occ_sum += o
                    occ_n += 1
            rows.append(dict(vdid=vid, link_id=lf.get('LinkID', ''), status=str(v.get('Status', '')),
                             minute=t.strftime('%Y-%m-%dT%H:%M'), lanes=len(lanes),
                             vol_M=vol['M'], vol_S=vol['S'], vol_L=vol['L'], vol_T=vol['T'],
                             spd_w=round(spd_w, 1), spd_n=int(spd_n), occ_sum=round(occ_sum, 1), occ_n=int(occ_n)))
    return rows


def fetch_day(day, token, keep_all):
    path = MINUTE / f"{'all_' if keep_all else ''}{day:%Y%m%d}.csv.gz"
    if path.exists():
        print(f"{day} 已經有了，跳過")
        return None
    for attempt in range(4):
        req = urllib.request.Request(HIST_URL.format(day.isoformat()),
                                     headers={'Authorization': f'Bearer {token.get()}', 'Accept-Encoding': 'gzip'})
        t0 = time.time()
        try:
            with urllib.request.urlopen(req, timeout=600) as r:
                stream = gzip.GzipFile(fileobj=r) if r.headers.get('Content-Encoding') == 'gzip' else r
                rows = parse(stream, keep_all)
            break
        except urllib.error.HTTPError as e:
            if e.code == 429:
                print(f"{day} 太頻繁（429），等 60 秒再試")
                time.sleep(60)
                continue
            if e.code in (401, 403):
                sys.exit(f"TDX 拒絕（{e.code}）：檢查金鑰，或這個帳號有沒有歷史資料的權限。{e.read()[:300]!r}")
            print(f"{day} 抓不到（HTTP {e.code}）：可能超過 TDX 保存的範圍，或資料還沒發布")
            return 0
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            print(f"{day} 連線中斷（{e}），等 30 秒再試")
            time.sleep(30)
    else:
        print(f"{day} 試了 4 次都失敗，先跳過；重跑會再試")
        return 0
    if not rows:
        print(f"{day} 沒有資料：可能超過 TDX 保存的範圍，或資料還沒發布")
        return 0
    MINUTE.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp')
    with gzip.open(tmp, 'wt', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=MIN_FIELDS)
        w.writeheader()
        w.writerows(rows)
    tmp.rename(path)  # 寫完才改名，中斷時不會留下半個檔案被當成抓過
    print(f"{day} OK：{len(rows):,} 列，{len({r['vdid'] for r in rows})} 支偵測器，{time.time() - t0:.0f} 秒")
    return len(rows)


def export():
    """把所有分鐘檔彙整成 5 分鐘讀數（時間標在 5 分鐘的結尾，例如 08:00–08:04 → 08:05）。"""
    acc = {}
    for p in sorted(MINUTE.glob('*.csv.gz')):
        with gzip.open(p, 'rt', encoding='utf-8') as f:
            for r in csv.DictReader(f):
                if r['vdid'] not in TARGETS:
                    continue
                m = dt.datetime.fromisoformat(r['minute'])
                end = m.replace(minute=m.minute - m.minute % 5, tzinfo=TPE) + dt.timedelta(minutes=5)
                k = (r['vdid'], r['link_id'], end)
                a = acc.setdefault(k, dict(seen=set(), good=0, lanes=0, vol_M=0, vol_S=0, vol_L=0, vol_T=0,
                                           spd_w=0.0, spd_n=0, occ_sum=0.0, occ_n=0))
                if r['minute'] in a['seen']:
                    continue  # 同一分鐘出現在兩天的檔案裡（跨日）只算一次
                a['seen'].add(r['minute'])
                a['lanes'] = max(a['lanes'], int(r['lanes']))
                if r['status'] != '0':
                    continue
                a['good'] += 1
                for c in ('vol_M', 'vol_S', 'vol_L', 'vol_T', 'spd_n', 'occ_n'):
                    a[c] += int(r[c])
                a['spd_w'] += float(r['spd_w'])
                a['occ_sum'] += float(r['occ_sum'])
    OUT.mkdir(parents=True, exist_ok=True)
    with open(EXPORT, 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        w.writeheader()
        for (vid, link, end), a in sorted(acc.items(), key=lambda x: (x[0][2], x[0][0], x[0][1])):
            ok = a['good'] >= 3  # 5 分鐘裡至少 3 分鐘正常才算
            w.writerow(dict(poll_time='tdx-history', entrance=TARGETS[vid], vdid=vid, link_id=link,
                            status='0' if ok else '1', collect_time=end.isoformat(timespec='milliseconds'),
                            lanes=a['lanes'], vol_M=a['vol_M'], vol_S=a['vol_S'], vol_L=a['vol_L'], vol_T=a['vol_T'],
                            speed=round(a['spd_w'] / a['spd_n'], 1) if ok and a['spd_n'] else '',
                            occupancy=round(a['occ_sum'] / a['occ_n'], 1) if ok and a['occ_n'] else ''))
    days = sorted({k[2].date() for k in acc})
    print(f"\n彙整 {len(acc):,} 筆 5 分鐘讀數（{days[0]}–{days[-1]}，{len(days)} 天）→ {EXPORT}" if days else "\n還沒有任何資料")


def main(argv):
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    today = dt.datetime.now(TPE).date()
    ap = argparse.ArgumentParser(description='從 TDX 補抓臺北市 VD 歷史資料')
    ap.add_argument('--from', dest='start', type=dt.date.fromisoformat, default=today - dt.timedelta(days=30))
    ap.add_argument('--to', dest='end', type=dt.date.fromisoformat, default=today - dt.timedelta(days=1))
    ap.add_argument('--all-vd', action='store_true', help='全臺北的 VD 都留（另存 all_YYYYMMDD.csv.gz，不進彙整）')
    ap.add_argument('--export-only', action='store_true', help='不下載，只把已經抓到的重新彙整')
    a = ap.parse_args(argv)
    if not a.export_only:
        load_env()
        if not (os.environ.get('TDX_CLIENT_ID') and os.environ.get('TDX_CLIENT_SECRET')):
            sys.exit('找不到 TDX 金鑰：在 repo 根目錄的 .env 寫 TDX_CLIENT_ID=... 和 TDX_CLIENT_SECRET=...')
        token, day = Token(), a.start
        print(f"抓 {a.start}–{a.end}，共 {(a.end - a.start).days + 1} 天；每天約 1–2 分鐘，中斷了重跑會接著抓\n")
        while day <= a.end:
            if fetch_day(day, token, a.all_vd) is not None and day < a.end:
                time.sleep(GAP)
            day += dt.timedelta(days=1)
    export()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
