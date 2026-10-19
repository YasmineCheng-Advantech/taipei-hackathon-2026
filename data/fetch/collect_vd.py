"""收集即時 VD 資料：預設平日 07:00–10:30（台北時間），每 5 分鐘抓一次；時段、週末與結束日期可調。

來源
- 臺北市交工處 VDLive.xml（免金鑰）：市區 5 個入口的偵測器
- TDX 國道即時 VD（需金鑰）：國1 內湖交流道；讀環境變數 TDX_CLIENT_ID、TDX_CLIENT_SECRET，
  沒設就跳過 TDX，只抓臺北市。也可以寫在 repo 根目錄的 .env（已在 .gitignore，不會進 git）：
      TDX_CLIENT_ID=...
      TDX_CLIENT_SECRET=...

輸出（data/raw/，不進 git；單獨下載時為同資料夾的 vd_raw/）
- vd_taipei/YYYYMMDD/HHMM.xml.gz   每次抓到的完整原始檔
- tdx_freeway/YYYYMMDD/HHMM.json.gz
- tdx_freeway/static_YYYYMMDD.json.gz  國道偵測器清單（每天一次，用來找內湖交流道的編號）
- vd_taipei_targets.csv            目標偵測器的每次讀數（方便直接看）
- collect.log

用法
    caffeinate -i python3 data/fetch/collect_vd.py          # 一直跑，時段外自動等待
    python3 data/fetch/collect_vd.py --once                  # 不管時段，立刻抓一次（測試用）
    python3 data/fetch/collect_vd.py --today                 # 只跑今天的時段，10:30 後結束（GitHub Actions 用）

    # 自己的電腦長時間收：每天 05:00–21:00、週末也收，收到 10/31 結束
    caffeinate -is python3 data/fetch/collect_vd.py --start 05:00 --end 21:00 --weekends --until 2026-10-31
"""
import argparse, csv, datetime as dt, gzip, json, os, sys, time, urllib.parse, urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path
from zoneinfo import ZoneInfo

TPE = ZoneInfo('Asia/Taipei')
START, END = dt.time(7, 0), dt.time(10, 30)
INTERVAL = 300  # 秒；來源規定不可更頻繁

TAIPEI_URL = 'https://tcgbusfs.blob.core.windows.net/blobtisv/VDLive.xml'
TDX_TOKEN_URL = 'https://tdx.transportdata.tw/auth/realms/TDXConnect/protocol/openid-connect/token'
TDX_LIVE_URL = 'https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/Live/VD/Freeway?$format=JSON'
TDX_STATIC_URL = 'https://tdx.transportdata.tw/api/basic/v2/Road/Traffic/VD/Freeway?$format=JSON'

NS = '{http://traffic.transportdata.tw/standard/traffic/schema/}'
# 入口對照見 entrances.csv；後三支是備用與交叉驗證
TARGETS = {
    'VTXQJ20': '內湖路一段', 'VPMSV40': '堤頂大道北向', 'VQBUL20': '民權大橋',
    'VMLXB00': '成美橋', 'V6310G0': '環東大道（東端）',
    'V6120C0': '環東大道（西端，備用）', 'VRPSV00': '堤頂下游', 'VRHT600': '堤頂港墘路',
}
CSV_FIELDS = ['poll_time', 'entrance', 'vdid', 'link_id', 'status', 'collect_time',
              'lanes', 'vol_M', 'vol_S', 'vol_L', 'vol_T', 'speed', 'occupancy']

# 在 repo 裡跑就寫到 data/raw/；單獨下載這支檔案時寫到同資料夾的 vd_raw/
_HERE = Path(__file__).resolve().parent
ROOT = _HERE.parent / 'raw' if _HERE.name == 'fetch' else _HERE / 'vd_raw'


def log(msg):
    line = f"{dt.datetime.now(TPE):%Y-%m-%d %H:%M:%S} {msg}"
    print(line, flush=True)
    with open(ROOT / 'collect.log', 'a', encoding='utf-8') as f:
        f.write(line + '\n')


def get(url, headers=None, data=None, timeout=60):
    req = urllib.request.Request(url, data=data, headers={'Accept-Encoding': 'gzip', **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        body = r.read()
        if r.headers.get('Content-Encoding') == 'gzip':
            body = gzip.decompress(body)
        return body


def get_retry(url, **kw):
    try:
        return get(url, **kw)
    except Exception as e:
        log(f"重試一次（{e}）")
        time.sleep(20)
        return get(url, **kw)


def save_gz(path, body):
    path.parent.mkdir(parents=True, exist_ok=True)
    with gzip.open(path, 'wb') as f:
        f.write(body)


def parse_taipei(body):
    """回傳目標偵測器每個 LinkFlow 一列。"""
    rows = []
    for v in ET.fromstring(body).iter(NS + 'VDLive'):
        vid = v.findtext(NS + 'VDID')
        if vid not in TARGETS:
            continue
        for lf in v.iter(NS + 'LinkFlow'):
            vol, spd, occ, n = {}, [], [], 0
            for ln in lf.iter(NS + 'Lane'):
                n += 1
                lane_vol = 0
                for vh in ln.iter(NS + 'Vehicle'):
                    k = vh.findtext(NS + 'VehicleType')
                    c = max(0, int(float(vh.findtext(NS + 'Volume') or 0)))
                    vol[k] = vol.get(k, 0) + c
                    lane_vol += c
                spd.append((float(ln.findtext(NS + 'Speed') or -99), lane_vol))
                occ.append(float(ln.findtext(NS + 'Occupancy') or -99))
            # 車速用各車道的車輛數加權：沒有車的車道常回報車速 0，直接平均會把車速算低
            ok_spd = [(s, c) for s, c in spd if s >= 0 and c > 0]
            ok_occ = [o for o in occ if o >= 0]
            w = sum(c for _, c in ok_spd)
            rows.append(dict(
                entrance=TARGETS[vid], vdid=vid, link_id=lf.findtext(NS + 'LinkID'),
                status=v.findtext(NS + 'Status'), collect_time=v.findtext(NS + 'DataCollectTime'),
                lanes=n, vol_M=vol.get('M', 0), vol_S=vol.get('S', 0), vol_L=vol.get('L', 0),
                vol_T=vol.get('T', 0),
                speed=round(sum(s * c for s, c in ok_spd) / w, 1) if w else '',
                occupancy=round(sum(ok_occ) / len(ok_occ), 1) if ok_occ else ''))
    return rows


def poll_taipei(now):
    body = get_retry(TAIPEI_URL)
    save_gz(ROOT / 'vd_taipei' / f"{now:%Y%m%d}" / f"{now:%H%M}.xml.gz", body)
    rows = parse_taipei(body)
    out = ROOT / 'vd_taipei_targets.csv'
    new = not out.exists()
    with open(out, 'a', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=CSV_FIELDS)
        if new:
            w.writeheader()
        for r in rows:
            w.writerow({'poll_time': f"{now:%Y-%m-%d %H:%M}", **r})
    found = {r['vdid'] for r in rows}
    missing = [v for v in TARGETS if v not in found]
    log(f"臺北市 OK：{len(body) // 1024} KB，目標 {len(found)}/{len(TARGETS)}"
        + (f"，缺 {','.join(missing)}" if missing else ''))


class TDX:
    def __init__(self):
        self.id = os.environ.get('TDX_CLIENT_ID')
        self.secret = os.environ.get('TDX_CLIENT_SECRET')
        self.token, self.expires = None, 0
        self.static_day = None

    def enabled(self):
        return bool(self.id and self.secret)

    def auth(self):
        if self.token and time.time() < self.expires - 300:
            return self.token
        data = urllib.parse.urlencode({'grant_type': 'client_credentials', 'client_id': self.id,
                                       'client_secret': self.secret}).encode()
        r = json.loads(get_retry(TDX_TOKEN_URL, data=data,
                                 headers={'Content-Type': 'application/x-www-form-urlencoded'}))
        self.token, self.expires = r['access_token'], time.time() + r.get('expires_in', 3600)
        return self.token

    def poll(self, now):
        h = {'Authorization': f"Bearer {self.auth()}"}
        day = ROOT / 'tdx_freeway'
        if self.static_day != now.date():
            body = get_retry(TDX_STATIC_URL, headers=h)
            save_gz(day / f"static_{now:%Y%m%d}.json.gz", body)
            self.static_day = now.date()
        body = get_retry(TDX_LIVE_URL, headers=h)
        save_gz(day / f"{now:%Y%m%d}" / f"{now:%H%M}.json.gz", body)
        n = len(json.loads(body).get('VDLives', []))
        log(f"TDX 國道 OK：{len(body) // 1024} KB，{n} 支偵測器")


def poll_once(tdx):
    now = dt.datetime.now(TPE)
    try:
        poll_taipei(now)
    except Exception as e:
        log(f"臺北市失敗：{e}")
    if tdx.enabled():
        try:
            tdx.poll(now)
        except Exception as e:
            log(f"TDX 失敗：{e}")


def load_env():
    """讀 repo 根目錄的 .env（KEY=VALUE 一行一個），已經設定的環境變數優先。"""
    env = _HERE.parent.parent / '.env' if _HERE.name == 'fetch' else _HERE / '.env'
    if not env.exists():
        return
    for line in env.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def in_window(now, start, end, weekends):
    return (weekends or now.weekday() < 5) and start <= now.time() <= end


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--once', action='store_true', help='立刻抓一次就結束（不管時段）')
    ap.add_argument('--today', action='store_true', help='只跑今天的時段，時段結束後結束（給排程用）')
    ap.add_argument('--start', type=dt.time.fromisoformat, default=START, help='每天開始收的時間，預設 07:00')
    ap.add_argument('--end', type=dt.time.fromisoformat, default=END, help='每天結束收的時間，預設 10:30')
    ap.add_argument('--weekends', action='store_true', help='週末也收（預設只收平日）')
    ap.add_argument('--until', type=dt.date.fromisoformat, help='收到這一天的時段結束就停，如 2026-10-31')
    args = ap.parse_args()
    ROOT.mkdir(parents=True, exist_ok=True)
    load_env()
    tdx = TDX()
    if not tdx.enabled():
        log('沒有設定 TDX_CLIENT_ID／TDX_CLIENT_SECRET，這次只抓臺北市資料')
    if args.once:
        poll_once(tdx)
        return
    days = '每天' if args.weekends else '平日'
    log(f"開始收集，{days} {args.start:%H:%M}–{args.end:%H:%M} 每 5 分鐘一次"
        + (f"，收到 {args.until} 為止" if args.until else '') + f"；輸出到 {ROOT}。按 Ctrl+C 停止")
    waiting = False
    while True:
        now = dt.datetime.now(TPE)
        if args.until and (now.date() > args.until or (now.date() == args.until and now.time() > args.end)):
            log(f"已收到 {args.until}，收集結束")
            return
        if in_window(now, args.start, args.end, args.weekends):
            waiting = False
            poll_once(tdx)
        elif args.today and now.time() > args.end:
            log('今天的收集時段結束')
            return
        elif not waiting:
            log('不在收集時段，等待中')
            waiting = True
        # 睡到下一個整 5 分鐘
        time.sleep(INTERVAL - time.time() % INTERVAL + 1)


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(0)
