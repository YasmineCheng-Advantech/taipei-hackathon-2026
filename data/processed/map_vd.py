"""路況地圖：把 VD 讀數畫在真實地圖上，用時間捲軸看每個偵測器一整天的變化。
explore_vd.py 會把這張地圖放進 data/raw/explore.html（最上面的「在地圖上看」），不另外產生檔案。
打開時需要網路：地圖底圖（OpenStreetMap、Esri 衛星）與 Leaflet 套件從網路載入。

- 位置：5 個入口用 entrances_detail.csv 的座標；其他偵測器（堤頂大道下游等）從臺北市 VD 靜態資料 VD.xml 找，
  先找 data/raw/VD.xml，沒有就下載一次存在那裡。
- 路段：從 OpenStreetMap（Overpass API）抓偵測器所在那條路的形狀，畫出偵測器前後約 400 公尺，跟著時間變色。
  抓一次存在 data/raw/roads.json，之後直接用；要重抓就刪掉那個檔。抓不到時只畫點。
- 顏色：服務水準 A–F（E、F 算塞），可以切換兩把尺，定義與 explore_vd.py 相同；5 分鐘不到 5 輛車的讀數不判斷。
"""
import csv
import json
import math
import sys
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from collections import defaultdict
from pathlib import Path

from explore_vd import LIMIT, MIN_CARS, threshold
from preview_vd import MAIN, ROOT

STATIC = ROOT / "raw" / "VD.xml"
STATIC_URL = "https://tcgbusfs.blob.core.windows.net/blobtisv/VD.xml"
NS = "{http://traffic.transportdata.tw/standard/traffic/schema/}"
DETAIL = Path(__file__).with_name("entrances_detail.csv")
ROADS = ROOT / "raw" / "roads.json"
OVERPASS = "https://overpass-api.de/api/interpreter"
REACH = 400  # 偵測器前後各畫多少公尺
DIRS = {"N": 0, "E": 90, "S": 180, "W": 270}  # 偵測方向 → 箭頭角度
NOTE = {"VRPSV00": "堤頂大道下游（舊宗路–港墘路）", "VRHT600": "堤頂大道下游（港墘路）", "V6120C0": "環東大道西端（備用）"}


def positions(vdids):
    """{VDID: (緯度, 經度, 方向, 道路名)}：入口用 entrances_detail.csv，其餘查 VD.xml。"""
    pos = {}
    with open(DETAIL, encoding="utf-8") as f:
        for r in csv.DictReader(f):
            if r["VD編號"]:
                pos[r["VD編號"]] = (float(r["緯度"]), float(r["經度"]), r["偵測方向"], r["道路"])
    rest = [v for v in vdids if v not in pos]
    if not rest:
        return pos
    if not STATIC.exists():
        try:
            STATIC.write_bytes(urllib.request.urlopen(STATIC_URL, timeout=60).read())
        except Exception as e:
            print(f"下載不到 VD.xml（{e}），{', '.join(rest)} 不會出現在地圖上")
            return pos
    for v in ET.parse(STATIC).getroot().iter(NS + "VD"):
        vid = v.findtext(NS + "VDID")
        if vid in rest:
            link = v.find(f".//{NS}DetectionLink")
            pos[vid] = (float(v.findtext(NS + "PositionLat")), float(v.findtext(NS + "PositionLon")),
                        link.findtext(NS + "RoadDirection") if link is not None else "", v.findtext(NS + "RoadName") or "")
    return pos


def meters(a, b):
    dy = (a[0] - b[0]) * 111320
    dx = (a[1] - b[1]) * 111320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


def bearing(a, b):
    """a → b 的方位角（北 0、東 90）。"""
    dy = b[0] - a[0]
    dx = (b[1] - a[1]) * math.cos(math.radians(a[0]))
    return math.degrees(math.atan2(dx, dy)) % 360


def overpass(q):
    body = urllib.request.urlopen(urllib.request.Request(
        OVERPASS, data=urllib.parse.urlencode({"data": q}).encode(), headers={"User-Agent": "taipei-hackathon-2026"}), timeout=60).read()
    return json.loads(body).get("elements", [])


def road_shape(lat, lng, road, deg):
    """問 Overpass：偵測器 80 公尺內、名稱相同的道路，取偵測器前後 REACH 公尺。
    名稱對不上時（例如偵測器在橋的引道，OSM 上叫「民權大橋」），改找 40 公尺內的主要道路。
    雙向分隔的道路在 OSM 是兩條單行線，只留和偵測方向相同的那條。回傳 [[(緯度, 經度), ...], ...]。"""
    base = road.split("段")[0][:-1] if road.endswith("段") else road  # 內湖路一段 → 內湖路
    lines = clip(overpass(f'[out:json][timeout:25];way(around:80,{lat},{lng})[highway]["name"~"{base}"];out geom;'), lat, lng, deg)
    if not lines:
        time.sleep(1)
        lines = clip(overpass(f'[out:json][timeout:25];way(around:40,{lat},{lng})'
                              f'[highway~"^(motorway|trunk|primary|secondary|tertiary)(_link)?$"];out geom;'), lat, lng, deg)
    return lines


def clip(ways, lat, lng, deg):
    lines = []
    for w in ways:
        pts = [(g["lat"], g["lon"]) for g in w.get("geometry", [])]
        if len(pts) < 2:
            continue
        if deg is not None and w.get("tags", {}).get("oneway") in ("yes", "1"):
            diff = abs((bearing(pts[0], pts[-1]) - deg + 180) % 360 - 180)
            if diff > 90:
                continue
        run = []
        for pt in pts:  # 只留離偵測器 REACH 公尺內、連續的點
            if meters(pt, (lat, lng)) <= REACH:
                run.append(pt)
            else:
                if len(run) > 1:
                    lines.append(run)
                run = []
        if len(run) > 1:
            lines.append(run)
    return lines


def road_shapes(vds):
    """{VDID: 路段}，存在 ROADS；只問還沒抓過的偵測器，每次間隔 1 秒，不對 Overpass 造成負擔。"""
    cache = json.loads(ROADS.read_text(encoding="utf-8")) if ROADS.exists() else {}
    todo = [v for v in vds if not cache.get(v["id"])]  # 沒抓過或上次沒抓到的
    for i, v in enumerate(todo):
        try:
            cache[v["id"]] = road_shape(v["lat"], v["lng"], v["road"], v["deg"])
            print(f"路段 {v['id']} {v['road']}：{len(cache[v['id']])} 段")
        except Exception as e:
            print(f"路段 {v['id']} 抓不到（{e}），這支只畫點")
            continue
        if i < len(todo) - 1:
            time.sleep(1)
    if todo:
        ROADS.parent.mkdir(parents=True, exist_ok=True)
        ROADS.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
    return {v["id"]: cache.get(v["id"], []) for v in vds}


def build(rows):
    names = {r["vdid"]: r["name"] for r in rows}
    vdids = [v for v in MAIN if v in names] + sorted(v for v in names if v not in MAIN)
    pos = positions(vdids)
    vdids = [v for v in vdids if v in pos]
    # 每支偵測器每天每 5 分鐘：[車速, 車輛數, 佔有率]
    data = defaultdict(lambda: defaultdict(dict))
    pts = defaultdict(list)
    for r in rows:
        if r["vdid"] in pos:
            m = r["t"].hour * 60 + r["t"].minute
            n = sum(r["cars"].values())
            data[r["vdid"]][r["t"].date().isoformat()][m - m % 5] = [r["speed"], n, r.get("occ")]
            pts[r["vdid"]].append((r["speed"], n))
    free = {v: threshold(pts[v])[0] for v in vdids}
    vds = [dict(id=v, name=NOTE.get(v, names[v]), main=v in MAIN, lat=pos[v][0], lng=pos[v][1], road=pos[v][3],
                deg=DIRS.get(pos[v][2]), free=free[v], limit=LIMIT.get(v, 50)) for v in vdids]
    shapes = road_shapes(vds)
    for v in vds:
        v["lines"] = [[[round(a, 6), round(b, 6)] for a, b in ln] for ln in shapes[v["id"]]]
    days = sorted({d for v in vdids for d in data[v]})
    return dict(vds=vds, days=days, data={v: {d: x for d, x in data[v].items()} for v in vdids}, min_cars=MIN_CARS // 3)


PAGE = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>入口路況地圖</title>
<link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css">
<script src="https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js"></script>
<style>
:root{--page:#f5f4ef;--surface:#fff;--ink:#1d1d1b;--ink2:#55554f;--muted:#8a8a82;--grid:#e6e5df;--axis:#cfcec7;
--A:#2e9e57;--B:#8cc63f;--C:#f2c12e;--D:#f28c28;--E:#e0452b;--F:#8e1b1b;--none:#9a9a94}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--muted:#8f8e86;--grid:#2c2c2a;--axis:#3a3a37}}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 -apple-system,"Noto Sans TC","PingFang TC",sans-serif}
main{max-width:1200px;margin:0 auto;padding:4px}h1{font-size:20px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 12px;font-size:14px}
#map{height:520px;border-radius:12px;border:1px solid var(--grid)}
.bar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0;font-size:14px;color:var(--ink2)}
.bar select,.bar button{font:inherit;padding:5px 10px;border-radius:8px;border:1px solid var(--axis);background:var(--surface);color:var(--ink);cursor:pointer}
#t{flex:1;min-width:200px}#clock{font-variant-numeric:tabular-nums;font-size:22px;font-weight:600;color:var(--ink);min-width:64px}
.legend{display:flex;flex-wrap:wrap;gap:12px;font-size:13px;color:var(--ink2)}.sw{display:inline-block;width:12px;height:12px;border-radius:50%;margin-right:4px;vertical-align:-1px}
.card{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:12px 16px;margin:12px 0}
.card h2{font-size:16px;margin:0 0 6px}svg text{fill:var(--muted);font-size:11px}.note{color:var(--muted);font-size:13px}
.vd{position:relative;display:flex;flex-direction:column;align-items:center;pointer-events:auto}
.dot{width:26px;height:26px;border-radius:50%;border:3px solid #fff;box-shadow:0 1px 4px rgba(0,0,0,.5);display:flex;align-items:center;justify-content:center;color:#fff;font:700 12px sans-serif}
.dot.small{width:14px;height:14px;border-width:2px;font-size:0}.nolab .lab,.nolab .arrow{display:none}.dot.sel{outline:3px solid #2a78d6;outline-offset:2px}.arrow{position:absolute;top:-13px;width:0;height:0;border-left:7px solid transparent;border-right:7px solid transparent;border-bottom:12px solid #fff;filter:drop-shadow(0 0 2px rgba(0,0,0,.8));margin-bottom:-2px}
.vd.left .lab{transform:translateX(-58%)}.vd.right .lab{transform:translateX(58%)}.lab{margin-top:3px;background:rgba(20,20,20,.78);color:#fff;font:600 12px sans-serif;padding:2px 6px;border-radius:6px;white-space:nowrap}
</style></head><body><main>
<p class="sub" id="sub"></p>
<div id="map"></div>
<div class="bar"><span id="clock">--:--</span><button id="play">▶ 播放</button><input type="range" id="t" min="0" max="0" step="1">
日期 <select id="day"></select> 尺 <select id="ruler"><option value="hcm">跟平常比（HCM）</option><option value="tw">依速限（臺灣公路容量手冊）</option></select>
<label><input type="checkbox" id="labels" checked> 顯示標籤</label> 速度 <select id="spd"><option value="400">慢</option><option value="150" selected>中</option><option value="50">快</option></select></div>
<div class="legend" id="legend"></div>
<div class="card"><h2 id="h2"></h2><svg id="chart" width="100%" height="150"></svg><p class="note" id="info"></p></div>
<p class="note">點地圖上的偵測器，下方會畫出它這一天的車速；箭頭是偵測方向。「塞」＝服務水準 E、F 級：跟平常比是車速不到平常的 40%（HCM 市區道路），依速限是速限 50 的道路低於 20 km/h（臺灣公路容量手冊）；快速道路不適用依速限那把尺。5 分鐘不到 __MIN__ 輛車的讀數不判斷：車太少時，幾台車剛好停紅燈車速就會很低。偵測器量的是單點車速，不是整段路的旅行速率。資料來源：臺北市交工處 VDLive.xml、VD.xml。底圖：OpenStreetMap、Esri。路段形狀來自 OpenStreetMap，顏色代表偵測器那一點的路況，不是整段路都量過。</p>
</main><script>
const D = __DATA__;
const $ = id => document.getElementById(id), hhmm = m => String(Math.floor(m / 60)).padStart(2, '0') + ':' + String(m % 60).padStart(2, '0');
const HCM = [[85, 'A'], [67, 'B'], [50, 'C'], [40, 'D'], [30, 'E']], TW = { 50: [[35, 'A'], [30, 'B'], [25, 'C'], [20, 'D'], [15, 'E']] };
const grade = (x, t) => (t.find(r => x >= r[0]) || [0, 'F'])[1], css = n => getComputedStyle(document.documentElement).getPropertyValue(n).trim();
$('sub').textContent = `${D.days.length} 天的資料（${D.days.map(d => d.slice(5).replace('-', '/')).join('、')}）· ${D.vds.length} 支偵測器`;
$('legend').innerHTML = 'ABCDEF'.split('').map(k => `<span><i class="sw" style="background:var(--${k})"></i>${k}${'EF'.includes(k) ? '（塞）' : ''}</span>`).join('') +
  '<span><i class="sw" style="background:var(--none)"></i>沒有資料／車太少／尺不適用</span><span>粗線：偵測器前後約 400 公尺的路段（OpenStreetMap）</span>';

// 底圖：街道、衛星（加道路名稱）、淺色
const map = L.map('map', { zoomControl: true });
const osm = L.tileLayer('https://tile.openstreetmap.org/{z}/{x}/{y}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' });
const sat = L.layerGroup([
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19, attribution: 'Imagery &copy; Esri' }),
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Transportation/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 }),
  L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Reference/World_Boundaries_and_Places/MapServer/tile/{z}/{y}/{x}', { maxZoom: 19 })]);
const light = L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', { maxZoom: 19, attribution: '&copy; OpenStreetMap &copy; CARTO' });
sat.addTo(map); L.control.layers({ '衛星＋道路': sat, '街道圖': osm, '淺色': light }).addTo(map);
map.fitBounds(L.latLngBounds(D.vds.map(v => [v.lat, v.lng])).pad(0.12));

let sel = D.vds.find(v => v.id === 'VPMSV40') || D.vds[0], times = [];
const marks = {}, lines = {};
// 標籤放哪一邊：右邊 1 公里內有別的偵測器就放左邊，左邊有就放右邊，免得疊在一起
const near = (v, dir) => D.vds.some(o => o !== v && Math.abs(o.lat - v.lat) < .006 && dir * (o.lng - v.lng) > 0 && dir * (o.lng - v.lng) < .012);
const side = v => near(v, 1) ? ' left' : near(v, -1) ? ' right' : '';
function state(v, rec) {  // 回傳 [等級或 null, 說明]
  if (!rec) return [null, '沒有資料'];
  const [s, n] = rec;
  if (n < D.min_cars) return [null, `${s} km/h，只有 ${n} 輛車，不判斷`];
  if ($('ruler').value === 'tw') return TW[v.limit] ? [grade(s, TW[v.limit]), `${s} km/h`] : [null, `${s} km/h（快速道路，依速限不適用）`];
  return [grade(s / v.free * 100, HCM), `${s} km/h，平常的 ${Math.round(s / v.free * 100)}%`];
}
function draw() {
  const d = $('day').value, m = times[+$('t').value];
  $('clock').textContent = m == null ? '--:--' : hhmm(m);
  for (const v of D.vds) {
    const rec = ((D.data[v.id] || {})[d] || {})[m], [k, txt] = state(v, rec);
    const col = k ? css('--' + k) : css('--none');
    const html = `<div class="vd${side(v)}">${v.deg != null ? `<div class="arrow" style="transform:rotate(${v.deg}deg)"></div>` : ''}` +
      `<div class="dot${v === sel ? ' sel' : ''}${v.lines && v.lines.length ? ' small' : ''}" style="background:${col}">${k || '–'}</div><div class="lab">${v.name.split('（')[0]}${rec ? ' ' + Math.round(rec[0]) : ''}</div></div>`;
    const small = v.lines && v.lines.length;  // 圓點中心對準偵測器位置：大圓 26px、小圓 14px
    const icon = L.divIcon({ className: '', html, iconSize: [120, 64], iconAnchor: [60, small ? 7 : 13] });
    if (v.lines && v.lines.length) {
      if (!lines[v.id]) lines[v.id] = v.lines.map(ln => [L.polyline(ln, { color: '#111', weight: 13, opacity: .55, interactive: false }).addTo(map),
        L.polyline(ln, { weight: 8, opacity: .95 }).addTo(map).bindTooltip('', { sticky: true }).on('click', () => { sel = v; draw(); chart(); })]);
      for (const [, top] of lines[v.id]) { top.setStyle({ color: col, dashArray: rec ? null : '6 8' }); top.setTooltipContent(`<b>${v.name}</b>｜${m == null ? '' : hhmm(m) + '｜'}${txt}`); }
    }
    if (!marks[v.id]) { marks[v.id] = L.marker([v.lat, v.lng], { icon }).addTo(map).on('click', () => { sel = v; draw(); chart(); });
      marks[v.id].bindTooltip('', { direction: 'top', offset: [0, -24] }); } else marks[v.id].setIcon(icon);
    marks[v.id].setTooltipContent(`<b>${v.name}</b>（${v.id}）<br>${m == null ? '' : hhmm(m) + '｜'}${txt}${rec && rec[2] != null ? `<br>佔有率 ${rec[2]}%` : ''}${rec ? `<br>${rec[1]} 輛／5 分鐘` : ''}`);
  }
  const line = document.querySelector('#chart .now'); if (line && m != null) { const x = X(m); line.setAttribute('x1', x); line.setAttribute('x2', x); }
}
let X = () => 0;
function chart() {
  const d = $('day').value, rec = (D.data[sel.id] || {})[d] || {}, svg = $('chart'), w = svg.clientWidth || 800, H = 150, L = 40, R = 10, T = 8, B = 20;
  const x0 = times[0], x1 = times[times.length - 1] + 5; X = m => L + (m - x0) / Math.max(5, x1 - x0) * (w - L - R);
  const smax = Math.ceil(Math.max(60, sel.free, ...Object.values(rec).map(r => r[0])) / 10) * 10, Y = s => T + (1 - s / smax) * (H - T - B);
  let g = '';
  for (let s = 0; s <= smax; s += 20) g += `<line x1="${L}" x2="${w - R}" y1="${Y(s)}" y2="${Y(s)}" stroke="${css('--grid')}"/><text x="${L - 4}" y="${Y(s) + 4}" text-anchor="end">${s}</text>`;
  for (let m = Math.ceil(x0 / 60) * 60; m <= x1; m += 120) g += `<text x="${X(m)}" y="${H - 4}" text-anchor="middle">${hhmm(m)}</text>`;
  const jam = $('ruler').value === 'tw' ? (TW[sel.limit] ? 20 : null) : sel.free * 0.4;
  if (jam) g += `<line x1="${L}" x2="${w - R}" y1="${Y(jam)}" y2="${Y(jam)}" stroke="${css('--E')}" stroke-dasharray="4 4"/><text x="${w - R}" y="${Y(jam) - 3}" text-anchor="end">塞車線 ${Math.round(jam)}</text>`;
  for (const m of times) { const r = rec[m]; if (!r) continue; const [k] = state(sel, r);
    g += `<rect x="${X(m)}" y="${Y(r[0])}" width="${Math.max(1, X(m + 5) - X(m) - .5)}" height="${Y(0) - Y(r[0])}" fill="${k ? css('--' + k) : css('--none')}"/>`; }
  g += `<line class="now" x1="0" x2="0" y1="${T}" y2="${H - B}" stroke="${css('--ink')}" stroke-width="1.5"/>`;
  svg.setAttribute('viewBox', `0 0 ${w} ${H}`); svg.innerHTML = g;
  $('h2').textContent = `${sel.name}（${sel.id}）· ${d.slice(5).replace('-', '/')} 每 5 分鐘的車速`;
  const slow = times.filter(m => rec[m] && 'EF'.includes(state(sel, rec[m])[0] || ''));
  $('info').textContent = `平常車速 ${sel.free} km/h。` + (slow.length ? `這一天有 ${slow.length * 5} 分鐘在 E 級以下，從 ${hhmm(slow[0])} 到 ${hhmm(slow[slow.length - 1] + 5)} 之間。` : '這一天沒有讀數在 E 級以下。');
  draw();
}
function setDay() {
  const d = $('day').value, all = new Set();
  for (const v of D.vds) for (const m of Object.keys((D.data[v.id] || {})[d] || {})) all.add(+m);
  times = [...all].sort((a, b) => a - b);
  $('t').max = Math.max(0, times.length - 1);
  const i = times.findIndex(m => m >= 8 * 60 + 30); $('t').value = i < 0 ? 0 : i;
  chart();
}
$('day').innerHTML = D.days.map((d, i) => `<option value="${d}"${i === D.days.length - 1 ? ' selected' : ''}>${d.slice(5).replace('-', '/')}</option>`).join('');
$('labels').onchange = () => $('map').classList.toggle('nolab', !$('labels').checked);
$('day').onchange = setDay; $('t').oninput = draw; $('ruler').onchange = chart;
let timer = null;
$('play').onclick = () => { if (timer) { clearInterval(timer); timer = null; $('play').textContent = '▶ 播放'; return; }
  $('play').textContent = '❚❚ 暫停'; timer = setInterval(() => { const t = $('t'); t.value = (+t.value + 1) % (+t.max + 1); draw(); }, +$('spd').value); };
$('spd').onchange = () => { if (timer) { $('play').click(); $('play').click(); } };
addEventListener('resize', chart);
// 放在 explore.html 的 iframe 裡時，告訴外層要多高
const tell = () => parent !== window && parent.postMessage({ mapHeight: document.documentElement.scrollHeight }, '*');
new ResizeObserver(tell).observe(document.body);
setDay();
</script></body></html>
"""


def render(rows):
    """地圖頁的完整 HTML；沒有找得到位置的偵測器時回傳 None。"""
    doc = build(rows)
    if not doc["vds"]:
        return None
    data = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
    return PAGE.replace("__DATA__", data).replace("__MIN__", str(doc["min_cars"]))


if __name__ == "__main__":
    print("地圖已經放進探索圖表：python3 data/processed/explore_vd.py && open data/raw/explore.html")
