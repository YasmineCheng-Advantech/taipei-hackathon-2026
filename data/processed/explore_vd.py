"""探索用的 VD 圖表：每張圖回答一個問題，圖下附一句從資料算出的結論。找靈感用，不是作品畫面。

用法：python3 data/processed/explore_vd.py [data/raw/vd_taipei_targets.csv ...]
輸出：data/raw/explore.html（含真實資料，不進 git），接著執行 open data/raw/explore.html

圖表
 先看尺：怎麼判斷塞不塞（兩把尺）、最慢的時候剩平常車速的幾 %
 什麼時候塞：一天裡每個入口在哪一級（可切換尺）、一整天的車速、每小時多少車
 哪裡最塞：各入口最慢時的車速
 車多還是塞住了：車速和流量放在一起看
 早一點經過有差嗎：每 15 分鐘的平均車速（可切換入口）
 每天都一樣嗎：每天塞了幾分鐘、最塞的 15 分鐘每天的車速
 都是什麼車：每 10 輛車的車種、機車和汽車幾點最多

兩把尺（服務水準 A–F，E、F 級算「塞」）
- 跟平常比：HCM（美國公路容量手冊）市區道路，車速佔自由車流速率的比例 85／67／50／40／30%。
  平常車速＝車少時（車輛數不超過中位數的讀數）的第 85 百分位，參考維吉尼亞州交通研究的做法。
- 依速限：《臺灣公路容量手冊》（交通部運輸研究所，2011 年版）速限 50 km/h 市區道路的平均旅行速率 35／30／25／20／15 km/h。
  各入口的速限暫定為臺北市市區道路的法定速限 50，待對照速限表；環東大道是快速道路，這張表不適用。
兩把尺的 E 級上限都是基準的 40%，所以「塞車線」＝平常車速的 40%。
兩個標準原本用在整段路的旅行速率；偵測器量的是單點車速，路段中間的偵測器會比旅行速率快，等級可能偏樂觀。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from preview_vd import DEFAULT_CSV, MAIN, ROOT, STYLE, VEH, load

OUT = ROOT / "raw" / "explore.html"
FREE_PCT = 85  # 平常車速：車少時讀數的第 85 百分位
RATIO = 0.4  # 低於平常車速的 40% 算塞：HCM 市區道路 E 級以下；臺灣公路容量手冊速限 50 的 E 級上限 20 km/h 也是 40%
LIMIT = {"VTXQJ20": 50, "VPMSV40": 50, "VQBUL20": 50, "VMLXB00": 50, "V6310G0": None}  # 速限，暫定；None＝快速道路
CARS = ("vol_S", "vol_L", "vol_T")  # 車速與流量圖只算汽車，和排隊模型相同
AM, PM = (6 * 60, 11 * 60), (15 * 60, 21 * 60)
BARS = (6 * 60, 10 * 60 + 30)  # 「早一點經過有差嗎」的時段


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def threshold(points):
    """[(車速, 車輛數)] → (平常車速, 塞車線)。平常車速只看車少時（車輛數不超過中位數）的讀數，免得把塞車時段算進去。"""
    ns = sorted(n for _, n in points)
    xs = sorted(s for s, n in points if n <= ns[len(ns) // 2]) or sorted(s for s, _ in points)
    free = xs[min(len(xs) - 1, len(xs) * FREE_PCT // 100)]
    return round(free, 1), round(free * RATIO, 1)


def slowest_hour(speeds, lo, hi):
    """{格: 車速} → 時段內最慢的連續 1 小時 [開始, 平均車速]；資料不夠連續 4 格時回傳 None。"""
    best = None
    for b in speeds:
        if lo <= b and b + 60 <= hi and all(b + k * 15 in speeds for k in range(4)):
            s = round(sum(speeds[b + k * 15] for k in range(4)) / 4, 1)
            if best is None or s < best[1]:
                best = [b, s]
    return best


def runs(points, bad):
    """連續低於 bad 的時段（至少 2 筆、間隔不超過 10 分鐘）→ [[開始, 結束], ...]。"""
    out, cur = [], None
    for m, s in points:
        if s < bad:
            if cur and m - cur[1] <= 10:
                cur[1], cur[2] = m, cur[2] + 1
            else:
                if cur and cur[2] >= 2:
                    out.append(cur[:2])
                cur = [m, m, 1]
    if cur and cur[2] >= 2:
        out.append(cur[:2])
    return [[a, b + 5] for a, b in out]


def weighted(pts):
    """[(分鐘, 車速, 車輛)] → 依車輛數加權的平均車速。"""
    n = sum(sum(c.values()) for _, _, c in pts)
    return sum(s * sum(c.values()) for _, s, c in pts) / n if n else sum(s for _, s, _ in pts) / len(pts)


def by_bin(pts, width=15, lo=0, hi=24 * 60):
    acc = defaultdict(list)
    for p in pts:
        if lo <= p[0] < hi:
            acc[p[0] - p[0] % width].append(p)
    return acc


def build(rows):
    names = {r["vdid"]: r["name"] for r in rows}
    ents = [v for v in MAIN if v in names]
    by = defaultdict(lambda: defaultdict(list))  # vdid -> 日期 -> [(分鐘, 車速, 車輛)]
    for r in sorted(rows, key=lambda r: r["t"]):
        by[r["vdid"]][r["t"].date().isoformat()].append((r["t"].hour * 60 + r["t"].minute, r["speed"], r["cars"]))
    days = sorted({d for v in ents for d in by[v]})
    free, bad = {}, {}
    for v in ents:
        free[v], bad[v] = threshold([(s, sum(c.values())) for pts in by[v].values() for _, s, c in pts])

    # 早上每天平均塞幾分鐘（連續 2 筆以上低於塞車線），用來挑最塞的入口
    minutes = {}
    for v in ents:
        jam = [runs([(m, s) for m, s, _ in pts if AM[0] <= m < AM[1]], bad[v]) for pts in by[v].values()]
        minutes[v] = round(sum(b - a for rs in jam for a, b in rs) / len(jam)) if jam else 0

    # 一整天的車速（每 15 分鐘，所有天合併）；早上時段另外給長條圖與每天的值
    curve, bars, daily = {}, {}, {}
    for v in ents:
        allpts = [p for pts in by[v].values() for p in pts]
        curve[v] = [[b, round(weighted(ps), 1)] for b, ps in sorted(by_bin(allpts).items())]
        bars[v] = [[b, s] for b, s in curve[v] if BARS[0] <= b < BARS[1]]
        daily[v] = defaultdict(dict)
        for d, pts in by[v].items():
            for b, ps in by_bin(pts, lo=BARS[0], hi=BARS[1]).items():
                daily[v][b][d] = round(weighted(ps), 1)

    # 一天裡每個入口在哪一級：每 15 分鐘各天的車速與中位數；早上、傍晚最慢的 1 小時（一般的一天與最慢的一天）
    strip, slow = {}, {}
    for v in ents:
        cells = defaultdict(dict)
        for d, pts in by[v].items():
            for b, ps in by_bin(pts).items():
                cells[b][d] = round(weighted(ps), 1)
        strip[v] = [[b, median(list(x.values())), x] for b, x in sorted(cells.items())]
        slow[v] = {}
        for key, (lo, hi) in (("am", AM), ("pm", PM)):
            typ = slowest_hour({b: m for b, m, _ in strip[v]}, lo, hi)
            days_ = [[d] + h for d in by[v] if (h := slowest_hour({b: x[d] for b, _, x in strip[v] if d in x}, lo, hi))]
            slow[v][key] = typ and dict(start=typ[0], speed=typ[1], worst=min(days_, key=lambda x: x[2]) if days_ else None)

    # 車速和流量：每筆讀數（5 分鐘）的汽車數換算成每小時
    scatter = {v: [[m, s, sum(c[k] for k in CARS) * 12] for pts in by[v].values() for m, s, c in pts] for v in ents}

    worst = max(ents, key=lambda v: (minutes[v], -min((s / free[v] for _, s in bars[v]), default=99)))
    wb = min(bars[worst], key=lambda x: x[1])[0] if bars[worst] else None

    # 每天塞了幾分鐘（每筆讀數算 5 分鐘），各入口分開
    jam_by_day = {d: {v: 5 * sum(1 for _, s, _ in by[v].get(d, []) if s < bad[v]) for v in ents} for d in days}

    # 每小時多少車、機車和汽車幾點最多（5 個入口合計，每天平均）
    hourly = defaultdict(lambda: [0, 0, 0])
    for v in ents:
        for pts in by[v].values():
            for m, _, c in pts:
                h = hourly[m // 60]
                h[0] += sum(c.values())
                h[1] += c["vol_M"]
                h[2] += c["vol_S"]
    nd = len(days) or 1
    hourly = [[h * 60, round(t / nd), round(mo / nd), round(car / nd)] for h, (t, mo, car) in sorted(hourly.items())]

    # 車種組成：有機車的偵測器合計（快速道路禁行機車，排除）
    tot = {k: 0 for k, _ in VEH}
    for v in names:
        if any(c["vol_M"] for pts in by[v].values() for _, _, c in pts):
            for pts in by[v].values():
                for _, _, c in pts:
                    for k in tot:
                        tot[k] += c[k]
    allc = sum(tot.values()) or 1
    mix = [[label, round(tot[k] / allc * 100, 1)] for k, label in VEH]

    return dict(names=names, ents=ents, worst=worst, worst_bin=wb, free=free, bad=bad, days=days, am=AM,
                limit={v: LIMIT.get(v) for v in ents}, strip=strip, slow=slow, scatter=scatter,
                curve=curve, bars=bars, daily={v: dict(x) for v, x in daily.items()},
                jam_by_day=jam_by_day, hourly=hourly, mix=mix)


PAGE = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>這幾天的路況</title>
__STYLE__
<style>h2{font-size:17px;margin:0 0 10px}.grp{font-size:13px;color:var(--muted);margin:28px 0 -6px;letter-spacing:.05em}
.say{margin:12px 0 0;font-size:15px;line-height:1.6;padding:8px 12px;border-radius:8px;background:var(--page)}
.say::before{content:"結論";font-size:12px;font-weight:600;color:var(--surface);background:var(--ink);border-radius:4px;padding:1px 6px;margin-right:8px;vertical-align:1px}
.ctl{display:flex;gap:8px;align-items:center;margin:0 0 8px;font-size:13px;color:var(--ink2)}
.ctl select{font:inherit;padding:4px 8px;border-radius:8px;border:1px solid var(--axis);background:var(--surface);color:var(--ink)}
.multi{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:12px}.multi div{font-size:13px;color:var(--ink2)}
.pict{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 8px}.pict i{width:34px;height:34px;border-radius:8px;display:block}
.rule{border-collapse:collapse;font-size:13px;margin:6px 0 12px;width:100%}.rule th,.rule td{border:1px solid var(--grid);padding:4px 6px;text-align:center}
.rule th{color:var(--ink2);font-weight:500}.rule td:first-child{text-align:left;color:var(--ink2)}.card p{font-size:14px;line-height:1.6;margin:6px 0}</style></head><body><main>
<h1>這幾天的路況</h1><p class="sub" id="sub"></p>

<p class="grp">先看尺</p>
<section class="card"><h2>怎麼判斷塞不塞？</h2>
<p>用服務水準 A–F 分級（A 最順、F 最塞），<b>E、F 級算「塞」</b>。這一頁有兩把尺：</p>
<table class="rule"><tr><th>尺</th><th>A</th><th>B</th><th>C</th><th>D</th><th>E</th><th>F</th></tr>
<tr><td>跟平常比：車速是平常的幾 %<br>（HCM 美國公路容量手冊，市區道路）</td><td>85% 以上</td><td>67–85%</td><td>50–67%</td><td>40–50%</td><td>30–40%</td><td>30% 以下</td></tr>
<tr><td>依速限：速限 50 的市區道路，km/h<br>（臺灣公路容量手冊，2011 年版）</td><td>35 以上</td><td>30–35</td><td>25–30</td><td>20–25</td><td>15–20</td><td>15 以下</td></tr></table>
<p>兩把尺的 E 級上限都是基準的 40%，所以這一頁的<b>塞車線＝平常車速的 40%</b>。<span id="free"></span></p>
<p class="note">平常車速＝車少時（車輛數不超過中位數的讀數）的第 85 百分位。各入口速限暫定 50（臺北市市區道路的法定速限），待對照速限表；環東大道是快速道路，「依速限」那把尺不適用。兩個標準原本用在整段路的旅行速率，偵測器量的是單點車速，路段中間的偵測器量到的會比旅行速率快，等級可能偏樂觀。</p></section>
<section class="card"><h2>最慢的時候，剩平常車速的幾 %？</h2><div class="scroll"><svg id="cr"></svg></div><div class="legend"><span><i class="sw" style="background:var(--s1)"></i>早上最慢的 1 小時</span><span><i class="sw" style="background:var(--s2)"></i>傍晚最慢的 1 小時</span><span>空心圈：最慢的那一天</span><span>底色：HCM 的 A–F</span></div><p class="say" id="sr"></p></section>

<p class="grp">什麼時候塞</p>
<section class="card"><h2>一天裡，每個入口在哪一級？</h2><div class="ctl">尺 <select id="ruler"><option value="hcm">跟平常比（HCM）</option><option value="tw">依速限（臺灣公路容量手冊）</option></select></div><div class="scroll"><svg id="c1"></svg></div><div class="legend" id="l1"></div><p class="say" id="s1"></p></section>
<section class="card"><h2>一整天的車速</h2><div class="multi" id="c2"></div><p class="say" id="s2"></p></section>
<section class="card"><h2>每小時有多少車經過？</h2><div class="scroll"><svg id="c3"></svg></div><p class="say" id="s3"></p></section>

<p class="grp">哪裡最塞</p>
<section class="card"><h2>各入口最慢的時候有多慢？</h2><div class="scroll"><svg id="c5"></svg></div><p class="say" id="s5"></p></section>

<p class="grp">車多，還是塞住了？</p>
<section class="card"><h2>車速和流量放在一起看</h2><div class="ctl">入口 <select id="pick2"></select></div><div class="scroll"><svg id="c11"></svg></div><div class="legend"><span><i class="sw" style="background:var(--s1)"></i>早上</span><span><i class="sw" style="background:var(--s2)"></i>傍晚</span><span><i class="sw" style="background:var(--muted)"></i>其他時段</span><span>虛線：平常車速、塞車線</span></div><p class="say" id="s11"></p></section>

<p class="grp">早一點經過有差嗎</p>
<section class="card"><h2>每 15 分鐘的平均車速</h2><div class="ctl">入口 <select id="pick"></select></div><div class="scroll"><svg id="c6"></svg></div><p class="say" id="s6"></p></section>

<p class="grp">每天都一樣嗎</p>
<section class="card"><h2>每天塞了幾分鐘？</h2><div class="scroll"><svg id="c7"></svg></div><div class="legend" id="l7"></div><p class="say" id="s7"></p></section>
<section class="card"><h2 id="h8">最塞的 15 分鐘，每天的車速</h2><div class="scroll"><svg id="c8"></svg></div><p class="say" id="s8"></p></section>

<p class="grp">都是什麼車</p>
<section class="card"><h2>每 10 輛車裡有幾輛機車？</h2><div class="pict" id="c9"></div><div class="legend" id="l9"></div><p class="say" id="s9"></p></section>
<section class="card"><h2>機車和汽車幾點最多？</h2><div class="scroll"><svg id="c10"></svg></div><p class="say" id="s10"></p></section>

<p class="note"><span id="def"></span>機車混在一般車道計數，可能漏數；環東大道禁行機車。資料來源：臺北市交工處 VDLive.xml。探索用，不是正式結果。</p>
</main><div id="tip"></div>
<script>
const D = __DATA__, N = D.names;
const $ = id => document.getElementById(id), tip = $('tip');
const hhmm = m => String(Math.floor(m/60)).padStart(2,'0') + ':' + String(m%60).padStart(2,'0');
const md = d => d.slice(5).replace('-', '/');
const show = (e, html) => { tip.innerHTML = html; tip.style.display = 'block';
  tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; };
const hover = el => { el.onmousemove = e => e.target.dataset.t ? show(e, e.target.dataset.t) : (tip.style.display = 'none'); el.onmouseleave = () => tip.style.display = 'none'; };
const STEPS = [[50,'--q0'],[40,'--q1'],[30,'--q2'],[20,'--q3'],[10,'--q4'],[-1,'--q5']];
const step = v => STEPS.find(s => v >= s[0])[1];
const SER = ['--s1','--s2','--s3','--s4','--s5'];
const W = el => Math.max(320, el.parentElement.clientWidth);
const say = (id, html) => $(id).innerHTML = html;
// 好讀的刻度：最大值往上取到 1、2、2.5、5 × 10ⁿ 的 4 倍
const nice = max => { const raw = Math.max(max, 1) / 4, p = 10 ** Math.floor(Math.log10(raw));
  const st = [1, 2, 2.5, 5, 10].map(k => k * p).find(k => k >= raw); return [st * 4, st]; };
const fmt = v => v >= 1000 ? v.toLocaleString() : String(+v.toFixed(1));
const minOf = (p, i = 1) => p.reduce((a, b) => b[i] < a[i] ? b : a), maxOf = (p, i = 1) => p.reduce((a, b) => b[i] > a[i] ? b : a);
$('def').textContent = '「塞」＝車速低於該入口平常車速的 40%（E 級以下）。';
$('free').textContent = '各入口的平常車速→塞車線：' + D.ents.map(v => `${N[v]} ${Math.round(D.free[v])}→${Math.round(D.bad[v])}`).join('、') + ' km/h。';
// 兩把尺：[門檻, 等級]，車速（或 %）不低於門檻就是這一級，都不到是 F
const HCM = [[85, 'A'], [67, 'B'], [50, 'C'], [40, 'D'], [30, 'E']];
const TW = { 50: [[35, 'A'], [30, 'B'], [25, 'C'], [20, 'D'], [15, 'E']] };
const GCOL = { A: '--q0', B: '--q1', C: '--q2', D: '--q3', E: '--q4', F: '--q5' };
const gradeOf = (x, tbl) => (tbl.find(t => x >= t[0]) || [0, 'F'])[1];
const jammed = k => k === 'E' || k === 'F';
const pctOf = (v, s) => s / D.free[v] * 100;
const twNote = (v, s) => TW[D.limit[v]] ? `<br>依速限（${D.limit[v]}）：${gradeOf(s, TW[D.limit[v]])} 級` : '';
const med = xs => { const a = [...xs].sort((x, y) => x - y); return a[Math.floor(a.length / 2)]; };
$('sub').textContent = `${D.days.length} 天的資料（${D.days.map(md).join('、')}）· 滑過圖表看數字`;

// 直條圖：items = [[標籤, 值, 顏色變數, 提示]]，labels = 要在柱上標數字的索引
function vbars(svg, items, { ymax, unit = '', every = 1, labels = [], ref = null, H = 220, pair = false } = {}) {
  const w = W(svg), L = 48, B = 24, T = 26, bw = Math.min((w - L) / items.length, 110);
  const [top, st] = nice(ymax || Math.max(1, ...items.map(i => i[1])) * 1.1);
  const Y = v => T + (1 - Math.min(v, top) / top) * (H - T - B);
  let g = `<text x="0" y="12">${unit}</text>`;
  for (let v = 0; v <= top + 1e-9; v += st) g += `<line x1="${L}" x2="${w}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fmt(v)}</text>`;
  items.forEach(([lab, v, col, t], i) => { const x = L + i * bw + 2;
    g += `<rect x="${x}" y="${Y(v)}" width="${Math.max(2, bw - 4)}" height="${Y(0) - Y(v)}" rx="3" fill="var(${col})" data-t="${t}"/>`;
    if (i % every === 0) g += `<text x="${pair ? x + bw - 2 : x + bw / 2 - 2}" y="${H - 6}" text-anchor="middle">${lab}</text>`;
    if (labels.includes(i)) g += `<text class="lab" x="${x + bw / 2 - 2}" y="${Y(v) - 5}" text-anchor="middle">${fmt(Math.round(v))}</text>`; });
  if (ref != null) g += `<line x1="${L}" x2="${w}" y1="${Y(ref)}" y2="${Y(ref)}" stroke="var(--muted)" stroke-dasharray="4 4"/>`;
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
}
// 橫條圖：rows = [[名稱, 值, 顏色變數, 右側文字, 提示]]
function hbars(svg, rows, max) {
  const w = W(svg), L = 140, R = 120, rh = 30, H = rows.length * rh + 4;
  let g = '';
  rows.forEach(([n, v, col, txt, t], i) => { const y = i * rh + 4;
    g += `<text class="lab" x="0" y="${y + 15}">${n}</text><rect x="${L}" y="${y + 2}" width="${Math.max(2, v / max * (w - L - R))}" height="18" rx="3" fill="var(${col})" data-t="${t}"/>`;
    g += `<text class="lab" x="${L + Math.max(2, v / max * (w - L - R)) + 8}" y="${y + 15}">${txt}</text>`; });
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
}

// R. 最慢的時候剩平常車速的幾 %（所有入口用同一把尺，底色是 HCM 的 A–F）
(function () {
  const svg = $('cr'), w = W(svg), L = 140, R = 16, rh = 40, T = 22, B = 22, H = T + D.ents.length * rh + B;
  const X = p => L + Math.min(Math.max(p, 0), 110) / 110 * (w - L - R);
  let g = '';
  for (const [a, b, k] of [[0, 30, 'F'], [30, 40, 'E'], [40, 50, 'D'], [50, 67, 'C'], [67, 85, 'B'], [85, 110, 'A']])
    g += `<rect x="${X(a)}" y="${T}" width="${X(b) - X(a)}" height="${H - T - B}" fill="var(${GCOL[k]})" opacity=".35"/><text x="${(X(a) + X(b)) / 2}" y="${T - 7}" text-anchor="middle">${k}</text>`;
  for (const q of [0, 30, 40, 50, 67, 85, 100]) g += `<text x="${X(q)}" y="${H - 6}" text-anchor="middle">${q}%</text>`;
  D.ents.forEach((v, i) => { const y = T + i * rh + rh / 2, sl = D.slow[v];
    g += `<text class="lab" x="0" y="${y + 4}">${N[v]}</text><line x1="${X(0)}" x2="${X(100)}" y1="${y}" y2="${y}" stroke="var(--axis)"/>`;
    [['am', '--s1', '早上'], ['pm', '--s2', '傍晚']].forEach(([k, col, name], j) => { const x = sl[k]; if (!x) return;
      const yy = y + (j ? 7 : -7), p = pctOf(v, x.speed);
      if (x.worst) { const wp = pctOf(v, x.worst[2]);
        g += `<circle cx="${X(wp)}" cy="${yy}" r="5" fill="none" stroke="var(${col})" stroke-width="2" data-t="${N[v]}｜${name}最慢的一天（${md(x.worst[0])}）${hhmm(x.worst[1])} 起 1 小時<br>${x.worst[2]} km/h，平常的 ${Math.round(wp)}%（${gradeOf(wp, HCM)} 級）${twNote(v, x.worst[2])}"/>`; }
      g += `<circle cx="${X(p)}" cy="${yy}" r="6" fill="var(${col})" data-t="${N[v]}｜${name}最慢的 1 小時：${hhmm(x.start)}–${hhmm(x.start + 60)}（各天的中位數）<br>${x.speed} km/h，平常 ${D.free[v]} km/h 的 ${Math.round(p)}%（${gradeOf(p, HCM)} 級）${twNote(v, x.speed)}"/>`; }); });
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
  const am = D.ents.filter(v => D.slow[v].am).map(v => [v, pctOf(v, D.slow[v].am.speed)]).sort((a, b) => a[1] - b[1]);
  const pm = D.ents.filter(v => D.slow[v].pm).map(v => [v, pctOf(v, D.slow[v].pm.speed)]).sort((a, b) => a[1] - b[1]);
  if (!am.length) { say('sr', '還沒有早上的資料。'); return; }
  const n = am.filter(([, p]) => jammed(gradeOf(p, HCM))).length, [v0, p0] = am[0];
  say('sr', `早上最慢的 1 小時，最慢的是「${N[v0]}」，剩平常的 ${Math.round(p0)}%（${gradeOf(p0, HCM)} 級）；${am.length} 個入口裡有 ${n} 個落到 E 級以下。` +
    (pm.length ? `傍晚最慢的是「${N[pm[0][0]]}」，剩 ${Math.round(pm[0][1])}%（${gradeOf(pm[0][1], HCM)} 級）。` : '這幾天沒有傍晚的資料。') +
    '點越往左越慢；空心圈離實心圈越遠，代表每天差越多。');
})();

// 1. 一天裡每個入口在哪一級（每 15 分鐘取各天的中位數，可切換兩把尺）
$('l1').innerHTML = 'ABCDEF'.split('').map(k => `<span><i class="sw" style="background:var(${GCOL[k]})"></i>${k}${jammed(k) ? '（塞）' : ''}</span>`).join('') +
  '<span><i class="sw" style="background:var(--empty)"></i>這把尺不適用</span>';
function c1() {
  const rule = $('ruler').value, svg = $('c1'), all = D.ents.flatMap(v => D.strip[v].map(c => c[0]));
  const x0 = Math.min(...all), x1 = Math.max(...all) + 15, L = 140, R = 8, rh = 28, H = D.ents.length * rh + 22;
  const w = Math.max(W(svg), L + R + (x1 - x0) / 15 * 10), X = m => L + (m - x0) / (x1 - x0) * (w - L - R);
  let g = '';
  for (let m = Math.ceil(x0 / 60) * 60; m <= x1; m += 60) g += `<text x="${X(m)}" y="${H - 4}" text-anchor="${m + 60 > x1 ? 'end' : 'middle'}">${hhmm(m)}</text>`;
  const found = [];
  D.ents.forEach((v, i) => { const y = i * rh, tbl = rule === 'tw' ? TW[D.limit[v]] : HCM, am = [];
    const val = s => rule === 'tw' ? s : pctOf(v, s), why = D.limit[v] ? `速限 ${D.limit[v]} 的分級表待補` : '快速道路，市區道路的表不適用';
    g += `<text class="lab" x="0" y="${y + 17}">${N[v]}</text>`;
    for (const [b, s, days] of D.strip[v]) {
      const k = tbl && gradeOf(val(s), tbl), ds = Object.entries(days).sort();
      const bad = tbl ? ds.filter(([, d]) => jammed(gradeOf(val(d), tbl))).length : 0;
      if (k && jammed(k) && b >= D.am[0] && b < D.am[1]) am.push(b);
      g += `<rect x="${X(b) + .5}" y="${y + 3}" width="${Math.max(1, X(b + 15) - X(b) - 1)}" height="${rh - 8}" rx="2" fill="var(${k ? GCOL[k] : '--empty'})" ` +
        `data-t="${N[v]} ${hhmm(b)}–${hhmm(b + 15)}｜${s} km/h（各天的中位數，平常的 ${Math.round(pctOf(v, s))}%）<br>` +
        (tbl ? `${k} 級；${ds.length} 天裡有 ${bad} 天在 E 級以下` : `這把尺不適用：${why}`) + `<br>${ds.map(([d, x]) => md(d) + ' ' + x).join('、')}"/>`; }
    if (am.length) found.push(`「${N[v]}」${hhmm(am[0])}–${hhmm(am[am.length - 1] + 15)}`); });
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
  const name = rule === 'tw' ? '依速限（臺灣公路容量手冊）' : '跟平常比（HCM）';
  say('s1', found.length ? `用「${name}」這把尺，早上落到 E 級以下的有：${found.join('、')}。滑過格子看每天的車速。`
    : `用「${name}」這把尺，這幾天早上沒有入口落到 E 級以下。換另一把尺看看，或看下面的車速和流量圖。`);
}
$('ruler').onchange = c1; c1();

// 2. 一整天的車速（每個入口一張小圖，同一個刻度）
(function () {
  const box = $('c2'); let deepest = null;
  box.innerHTML = D.ents.map((v, i) => `<div>${N[v]}<svg id="m${i}"></svg></div>`).join('');
  const all = D.ents.flatMap(v => D.curve[v]), x0 = Math.min(...all.map(p => p[0])), x1 = Math.max(...all.map(p => p[0])) + 15;
  const top = Math.ceil(Math.max(70, ...all.map(p => p[1])) / 10) * 10;  // 環東大道是快速道路，平常比 70 快
  D.ents.forEach((v, i) => { const svg = $('m' + i), p = D.curve[v], w = Math.max(280, svg.parentElement.clientWidth), H = 120, L = 26, B = 18;
    const X = m => L + (m - x0) / (x1 - x0) * (w - L - 4), Y = s => 4 + (1 - Math.min(s, top) / top) * (H - 4 - B);
    const lo = minOf(p); if (!deepest || lo[1] < deepest[2]) deepest = [v, lo[0], lo[1]];
    let g = `<line x1="${L}" x2="${w}" y1="${Y(D.bad[v])}" y2="${Y(D.bad[v])}" stroke="var(--muted)" stroke-dasharray="3 3"/><text x="${L - 4}" y="${Y(D.bad[v]) + 4}" text-anchor="end">${Math.round(D.bad[v])}</text>`;
    for (let m = Math.ceil(x0 / 240) * 240; m < x1; m += 240) g += `<text x="${X(m)}" y="${H - 4}" text-anchor="middle">${hhmm(m)}</text>`;
    g += `<polyline fill="none" stroke="var(--s1)" stroke-width="2" points="${p.map(q => X(q[0] + 7.5) + ',' + Y(q[1])).join(' ')}"/>`;
    g += `<circle cx="${X(lo[0] + 7.5)}" cy="${Y(lo[1])}" r="4" fill="var(--s2)"/><text class="lab" x="${X(lo[0] + 7.5) + 7}" y="${Y(lo[1]) + 4}">${Math.round(lo[1])}</text>`;
    for (const q of p) g += `<rect x="${X(q[0])}" y="0" width="${X(q[0] + 15) - X(q[0])}" height="${H - B}" fill="transparent" data-t="${N[v]} ${hhmm(q[0])}｜${q[1]} km/h"/>`;
    svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg); });
  say('s2', `最深的低谷在「${N[deepest[0]]}」${hhmm(deepest[1])}，只剩 ${Math.round(deepest[2])} km/h（虛線是各入口的塞車線，平常車速的 40%）。`);
})();

// 3. 每小時有多少車
(function () {
  const p = D.hourly, top = maxOf(p);
  vbars($('c3'), p.map(([h, t]) => [String(h / 60), t, h === top[0] ? '--s2' : '--s1', `${hhmm(h)}–${hhmm(h + 60)}｜每天平均 ${t.toLocaleString()} 輛`]),
    { unit: '輛／小時', labels: [p.indexOf(top)] });
  say('s3', `車最多的是 ${hhmm(top[0])}–${hhmm(top[0] + 60)}，5 個入口合計每天平均 ${top[1].toLocaleString()} 輛。`);
})();

// 5. 各入口最慢的時候
(function () {
  const rows = D.ents.map(v => { const lo = minOf(D.curve[v]); return [N[v], lo[1], lo[0]]; }).sort((a, b) => a[1] - b[1]);
  hbars($('c5'), rows.map(([n, s, m]) => [n, s, step(s), `${Math.round(s)} km/h（${hhmm(m)}）`, `${n}｜最慢在 ${hhmm(m)}，${s} km/h`]), 70);
  say('s5', `「${rows[0][0]}」最慢時只剩 ${Math.round(rows[0][1])} km/h；「${rows[rows.length - 1][0]}」最慢也還有 ${Math.round(rows[rows.length - 1][1])} km/h。條越短越慢。`);
})();

// 11. 車速和流量放在一起看：右上是車多但還順；車速往下掉、點又往左縮，就是排隊塞住了
$('pick2').innerHTML = D.ents.map(v => `<option value="${v}"${v === D.worst ? ' selected' : ''}>${N[v]}</option>`).join('');
function c11() {
  const v = $('pick2').value, p = D.scatter[v] || [], svg = $('c11');
  if (!p.length) { svg.innerHTML = ''; say('s11', '還沒有這個入口的資料。'); return; }
  const w = W(svg), H = 280, L = 48, B = 30, T = 18, R = 12, inAM = m => m >= D.am[0] && m < D.am[1], inPM = m => m >= 15 * 60 && m < 21 * 60;
  // 橫軸：取 1、2、2.5、5 × 10ⁿ 中，讓刻度不超過 6 格的最小間距
  const fm = Math.max(...p.map(q => q[2])), st = [1, 2, 2.5, 5].flatMap(k => [10, 100, 1000, 10000].map(e => k * e)).sort((a, b) => a - b).find(x => Math.ceil(fm / x) <= 6);
  const top = Math.ceil(fm / st) * st, smax = Math.ceil(Math.max(70, ...p.map(q => q[1])) / 10) * 10;
  const X = f => L + f / top * (w - L - R), Y = s => T + (1 - s / smax) * (H - T - B);
  let g = '<text x="0" y="12">km/h</text>';
  for (let s = 0; s <= smax; s += 10) g += `<line x1="${L}" x2="${w - R}" y1="${Y(s)}" y2="${Y(s)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(s) + 4}" text-anchor="end">${s}</text>`;
  for (let f = 0; f <= top + 1e-9; f += st) g += `<text x="${X(f)}" y="${H - 15}" text-anchor="${f + st > top + 1e-9 ? 'end' : 'middle'}">${fmt(f)}</text>`;
  g += `<text x="${L}" y="${H - 1}">橫軸：每小時通過的汽車（每 5 分鐘的讀數換算）</text>`;
  for (const [s, lab] of [[D.free[v], '平常'], [D.bad[v], '塞車線']])
    g += `<line x1="${L}" x2="${w - R}" y1="${Y(s)}" y2="${Y(s)}" stroke="var(--muted)" stroke-dasharray="4 4"/><text x="${w - R}" y="${Y(s) - 4}" text-anchor="end">${lab} ${Math.round(s)}</text>`;
  for (const [m, s, f] of p) g += `<circle cx="${X(f)}" cy="${Y(s)}" r="2.5" fill="var(${inAM(m) ? '--s1' : inPM(m) ? '--s2' : '--muted'})" opacity=".6" data-t="${hhmm(m)}｜${s} km/h，每小時 ${f.toLocaleString()} 輛汽車"/>`;
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
  // 車最多的時候：流量前 5% 讀數的中位數；塞車線以下的讀數，通過的車有沒有變少
  const fTop = med([...p].sort((a, b) => b[2] - a[2]).slice(0, Math.max(1, Math.round(p.length / 20))).map(q => q[2]));
  const jam = p.filter(q => q[1] < D.bad[v]), fJam = jam.length && med(jam.map(q => q[2])), r = Math.round(fJam / fTop * 100);
  say('s11', `「${N[v]}」車最多的時候，每小時約通過 ${fTop.toLocaleString()} 輛汽車。` + (!jam.length
    ? `這幾天沒有讀數低於塞車線（${Math.round(D.bad[v])} km/h）；看點有沒有在右邊往下彎，彎下去的地方就是快塞住了。`
    : `低於塞車線（${Math.round(D.bad[v])} km/h）的讀數有 ${jam.length} 筆，那時每小時約通過 ${fJam.toLocaleString()} 輛，是最多時的 ${r}%：` +
      (r < 95 ? '車變慢、通過的車也變少，是排隊塞住，不只是車多。' : '通過的車沒有變少，比較像是車多造成的慢，還沒有真的塞住。')));
}
$('pick2').onchange = c11; c11();

// 6. 每 15 分鐘的平均車速
$('pick').innerHTML = D.ents.map(v => `<option value="${v}"${v === D.worst ? ' selected' : ''}>${N[v]}</option>`).join('');
function c6() {
  const v = $('pick').value, p = D.bars[v] || [];
  if (!p.length) { $('c6').innerHTML = ''; say('s6', '還沒有這個時段的資料。'); return; }
  const lo = minOf(p), hi = maxOf(p), early = p.find(q => q[0] === lo[0] - 60);
  vbars($('c6'), p.map(([b, s]) => [b % 60 === 0 ? hhmm(b) : '', s, step(s), `${hhmm(b)}–${hhmm(b + 15)} 經過｜平均 ${s} km/h`]),
    { unit: 'km/h', ymax: 70, ref: D.bad[v], labels: [p.indexOf(lo), p.indexOf(hi)].concat(early ? [p.indexOf(early)] : []) });
  say('s6', `${N[v]}在 ${hhmm(lo[0])} 最慢（${Math.round(lo[1])} km/h）` + (early ? `；提早 1 小時、${hhmm(early[0])} 經過約 ${Math.round(early[1])} km/h，快 ${(early[1] / Math.max(lo[1], 1)).toFixed(1)} 倍。` : '。'));
}
$('pick').onchange = c6; c6();

// 7. 每天塞了幾分鐘（各入口疊起來）
(function () {
  const svg = $('c7'), w = W(svg), H = 220, L = 48, B = 24, T = 26, ds = D.days, bw = Math.min(110, (w - L) / ds.length);
  const tot = ds.map(d => D.ents.reduce((s, v) => s + D.jam_by_day[d][v], 0)), [top, st] = nice(Math.max(10, ...tot) * 1.1);
  const Y = v => T + (1 - v / top) * (H - T - B);
  let g = '<text x="0" y="12">分鐘</text>';
  for (let v = 0; v <= top + 1e-9; v += st) g += `<line x1="${L}" x2="${w}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fmt(v)}</text>`;
  ds.forEach((d, i) => { const x = L + i * bw + 8; let acc = 0;
    D.ents.forEach((v, j) => { const m = D.jam_by_day[d][v]; if (!m) return;
      g += `<rect x="${x}" y="${Y(acc + m)}" width="${bw - 16}" height="${Y(acc) - Y(acc + m) - 2}" fill="var(${SER[j]})" data-t="${md(d)}｜${N[v]} 塞 ${m} 分鐘"/>`; acc += m; });
    g += `<text class="lab" x="${x + (bw - 16) / 2}" y="${Y(acc) - 5}" text-anchor="middle">${acc}</text><text x="${x + (bw - 16) / 2}" y="${H - 6}" text-anchor="middle">${md(d)}</text>`; });
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
  $('l7').innerHTML = D.ents.map((v, j) => `<span><i class="sw" style="background:var(${SER[j]})"></i>${N[v]}</span>`).join('');
  const hi = tot.indexOf(Math.max(...tot)), lo = tot.indexOf(Math.min(...tot));
  say('s7', ds.length < 2 ? '目前只有 1 天，多收幾天才能比較。' : `${md(ds[hi])} 最塞（5 個入口合計 ${tot[hi]} 分鐘），${md(ds[lo])} 最順（${tot[lo]} 分鐘），差 ${tot[hi] - tot[lo]} 分鐘。`);
})();

// 8. 最塞的 15 分鐘，每天的車速
(function () {
  const b = D.worst_bin, d = b == null ? {} : (D.daily[D.worst] || {})[b] || {}, ks = Object.keys(d).sort();
  if (!ks.length) { say('s8', '資料還不夠。'); return; }
  $('h8').textContent = `${N[D.worst]} ${hhmm(b)}–${hhmm(b + 15)}，每天的車速`;
  vbars($('c8'), ks.map(k => [md(k), d[k], step(d[k]), `${md(k)}｜${d[k]} km/h`]), { unit: 'km/h', ymax: 70, ref: D.bad[D.worst], labels: ks.map((_, i) => i), H: 200 });
  const bad = ks.filter(k => d[k] < D.bad[D.worst]).length;
  say('s8', `${ks.length} 天裡有 ${bad} 天低於 ${D.bad[D.worst]} km/h（虛線，平常車速的 40%）` + (bad >= ks.length - 1 && bad ? '，幾乎每天都塞，可以預期。' : '，不是每天都塞，比較難預期。'));
})();

// 9. 每 10 輛車
(function () {
  const cols = ['--s1', '--s2', '--s3', '--s4'], counts = D.mix.map(([, p]) => Math.round(p / 10));
  counts[1] += 10 - counts.reduce((a, b) => a + b, 0);
  $('c9').innerHTML = D.mix.flatMap(([label, p], i) => Array(Math.max(0, counts[i])).fill(`<i style="background:var(${cols[i]})" title="${label} ${p}%"></i>`)).slice(0, 10).join('');
  $('l9').innerHTML = D.mix.map(([label, p], i) => `<span><i class="sw" style="background:var(${cols[i]})"></i>${label} ${p}%</span>`).join('');
  say('s9', `每 10 輛車裡約有 ${counts[0]} 輛機車、${counts[1]} 輛小客車（不含禁行機車的環東大道）。`);
})();

// 10. 機車和汽車幾點最多（各自佔全天的比例）
(function () {
  const svg = $('c10'), p = D.hourly, w = W(svg), H = 220, L = 48, R = 70, B = 24, T = 26;
  const sm = p.reduce((s, q) => s + q[2], 0) || 1, sc = p.reduce((s, q) => s + q[3], 0) || 1;
  const m = p.map(q => [q[0], q[2] / sm * 100]), c = p.map(q => [q[0], q[3] / sc * 100]);
  const [top, st] = nice(Math.max(5, ...m.map(q => q[1]), ...c.map(q => q[1])) * 1.1), x0 = p[0][0], x1 = p[p.length - 1][0];
  const X = h => L + (h - x0) / Math.max(60, x1 - x0) * (w - L - R), Y = v => T + (1 - v / top) * (H - T - B);
  let g = '<text x="0" y="12">% 佔全天</text>';
  for (let v = 0; v <= top + 1e-9; v += st) g += `<line x1="${L}" x2="${w - R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L - 6}" y="${Y(v) + 4}" text-anchor="end">${fmt(v)}</text>`;
  for (const q of p) if (q[0] % 120 === 0) g += `<text x="${X(q[0])}" y="${H - 6}" text-anchor="middle">${hhmm(q[0])}</text>`;
  let lastY = null;
  [[m, '--s1', '機車'], [c, '--s2', '小客車']].forEach(([s, col, name]) => {
    g += `<polyline fill="none" stroke="var(${col})" stroke-width="2" points="${s.map(q => X(q[0]) + ',' + Y(q[1])).join(' ')}"/>`;
    const e = s[s.length - 1]; let y = Y(e[1]) + 4; if (lastY !== null && Math.abs(y - lastY) < 14) y = lastY + 14; lastY = y;
    g += `<text class="lab" x="${X(e[0]) + 6}" y="${y}">${name}</text>`;
    for (const q of s) g += `<circle cx="${X(q[0])}" cy="${Y(q[1])}" r="6" fill="transparent" data-t="${name} ${hhmm(q[0])}–${hhmm(q[0] + 60)}｜佔全天 ${q[1].toFixed(1)}%"/>`; });
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
  const pm = maxOf(m), pc = maxOf(c);
  say('s10', pm[0] === pc[0] ? `機車和小客車都在 ${hhmm(pm[0])} 那一小時最多。` :
    `機車在 ${hhmm(pm[0])} 那一小時最多，小客車在 ${hhmm(pc[0])}；機車${pm[0] < pc[0] ? '比較早' : '比較晚'}出門。`);
})();
</script></body></html>
"""


def main(argv):
    paths = argv or [DEFAULT_CSV]
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print(f"找不到 {', '.join(map(str, missing))}；收集程式至少要成功抓過一次")
        return 1
    rows, _ = load(paths)
    if not [r for r in rows if r["vdid"] in MAIN]:
        print("檔案裡還沒有 5 個入口的有效讀數")
        return 1
    data = json.dumps(build(rows), ensure_ascii=False)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(PAGE.replace("__STYLE__", STYLE).replace("__DATA__", data.replace("</", "<\\/")), encoding="utf-8")
    print(f"wrote {OUT}（{len(rows):,} 筆讀數）。執行 open {OUT.relative_to(ROOT.parent)} 用瀏覽器打開")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
