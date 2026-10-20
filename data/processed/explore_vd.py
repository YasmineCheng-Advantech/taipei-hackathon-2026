"""探索用的 VD 圖表：每張圖回答一個問題，圖下附一句從資料算出的結論。找靈感用，不是作品畫面。

用法：python3 data/processed/explore_vd.py [data/raw/vd_taipei_targets.csv ...]
輸出：data/raw/explore.html（含真實資料，不進 git），接著執行 open data/raw/explore.html

圖表
 什麼時候塞：塞車時刻表、一整天的車速、每小時多少車、早上 vs 傍晚
 哪裡最塞：各入口最慢時的車速
 早一點經過有差嗎：每 15 分鐘的平均車速（可切換入口）
 每天都一樣嗎：每天塞了幾分鐘、最塞的 15 分鐘每天的車速
 都是什麼車：每 10 輛車的車種、機車和汽車幾點最多
 塞住的時候路能放多少車：每天塞住時每 15 分鐘通過的汽車數，對照順的時候最多通過多少
「塞」的定義：車速低於 20 km/h；塞車時刻表另要求連續至少 2 筆讀數。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from preview_vd import DEFAULT_CSV, MAIN, ROOT, STYLE, VEH, load

OUT = ROOT / "raw" / "explore.html"
BAD = 20
AM, PM = (6 * 60, 11 * 60), (15 * 60, 21 * 60)
CARS = ("vol_S", "vol_L", "vol_T")  # 放行量只算汽車：排隊模型以汽車計，機車在混合車道可能漏數
MODEL_VD, MODEL_CAP = "VPMSV40", 1000  # 排隊模型的瓶頸與目前假設的容量（輛／15 分鐘），見 data/mock/gen_t4_morning.py
BARS = (6 * 60, 10 * 60 + 30)  # 「早一點經過有差嗎」的時段


def median(xs):
    xs = sorted(xs)
    return xs[len(xs) // 2]


def runs(points):
    """連續低於 BAD 的時段（至少 2 筆、間隔不超過 10 分鐘）→ [[開始, 結束], ...]。"""
    out, cur = [], None
    for m, s in points:
        if s < BAD:
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

    # 塞車時刻表：每天第一段開始、最後一段結束取中位數；每天平均塞幾分鐘
    timetable, minutes = {}, {}
    for v in ents:
        row = {}
        for key, (lo, hi) in (("am", AM), ("pm", PM)):
            spans = []
            for pts in by[v].values():
                rs = runs([(m, s) for m, s, _ in pts if lo <= m < hi])
                if rs:
                    spans.append((rs[0][0], rs[-1][1], sum(b - a for a, b in rs)))
            n = len(by[v])
            row[key] = dict(days=n, jam_days=len(spans), start=median([s[0] for s in spans]) if spans else None,
                            end=median([s[1] for s in spans]) if spans else None,
                            minutes=round(sum(s[2] for s in spans) / n) if n else 0)
        timetable[v] = row
        minutes[v] = [row["am"]["minutes"], row["pm"]["minutes"]]

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

    worst = max(ents, key=lambda v: (minutes[v][0], -min((s for _, s in bars[v]), default=99)))
    wb = min(bars[worst], key=lambda x: x[1])[0] if bars[worst] else None

    # 每天塞了幾分鐘（每筆讀數算 5 分鐘），各入口分開
    jam_by_day = {d: {v: 5 * sum(1 for _, s, _ in by[v].get(d, []) if s < BAD) for v in ents} for d in days}

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

    # 塞住的時候路能放多少車：每天每 15 分鐘通過的汽車數（少於 2 筆讀數的格子不算，缺 1 筆時按比例補成 15 分鐘）。
    # 順的時候最多通過多少，是這條路的上限；塞住時（車速低於 BAD）的通過量，是排隊實際消化的速度
    flow = {}
    for v in ents:
        top, jam = None, {}
        for d, pts in sorted(by[v].items()):
            for b, ps in sorted(by_bin(pts).items()):
                if len(ps) < 2:
                    continue
                n = round(sum(c[k] for _, _, c in ps for k in CARS) * 3 / len(ps))
                if weighted(ps) < BAD:
                    jam.setdefault(d, []).append(n)
                elif not top or n > top[0]:
                    top = [n, d, b]
        flow[v] = dict(top=top, days=[[d, round(sum(ns) / len(ns)), len(ns), min(ns), max(ns)] for d, ns in jam.items()],
                       avg=round(sum(sum(ns) for ns in jam.values()) / sum(len(ns) for ns in jam.values())) if jam else None)

    return dict(names=names, ents=ents, worst=worst, worst_bin=wb, bad=BAD, days=days, timetable=timetable,
                minutes=minutes, curve=curve, bars=bars, daily={v: dict(x) for v, x in daily.items()},
                jam_by_day=jam_by_day, hourly=hourly, mix=mix, flow=flow, model_vd=MODEL_VD, model_cap=MODEL_CAP)


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
.pict{display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 8px}.pict i{width:34px;height:34px;border-radius:8px;display:block}</style></head><body><main>
<h1>這幾天的路況</h1><p class="sub" id="sub"></p>

<p class="grp">什麼時候塞</p>
<section class="card"><h2>每個入口幾點塞？</h2><div class="scroll"><svg id="c1"></svg></div><p class="say" id="s1"></p></section>
<section class="card"><h2>一整天的車速</h2><div class="multi" id="c2"></div><p class="say" id="s2"></p></section>
<section class="card"><h2>每小時有多少車經過？</h2><div class="scroll"><svg id="c3"></svg></div><p class="say" id="s3"></p></section>
<section class="card"><h2>早上還是傍晚比較塞？</h2><div class="scroll"><svg id="c4"></svg></div><div class="legend"><span><i class="sw" style="background:var(--s1)"></i>早上</span><span><i class="sw" style="background:var(--s2)"></i>傍晚</span></div><p class="say" id="s4"></p></section>

<p class="grp">哪裡最塞</p>
<section class="card"><h2>各入口最慢的時候有多慢？</h2><div class="scroll"><svg id="c5"></svg></div><p class="say" id="s5"></p></section>

<p class="grp">早一點經過有差嗎</p>
<section class="card"><h2>每 15 分鐘的平均車速</h2><div class="ctl">入口 <select id="pick"></select></div><div class="scroll"><svg id="c6"></svg></div><p class="say" id="s6"></p></section>

<p class="grp">每天都一樣嗎</p>
<section class="card"><h2>每天塞了幾分鐘？</h2><div class="scroll"><svg id="c7"></svg></div><div class="legend" id="l7"></div><p class="say" id="s7"></p></section>
<section class="card"><h2 id="h8">最塞的 15 分鐘，每天的車速</h2><div class="scroll"><svg id="c8"></svg></div><p class="say" id="s8"></p></section>

<p class="grp">都是什麼車</p>
<section class="card"><h2>每 10 輛車裡有幾輛機車？</h2><div class="pict" id="c9"></div><div class="legend" id="l9"></div><p class="say" id="s9"></p></section>
<section class="card"><h2>機車和汽車幾點最多？</h2><div class="scroll"><svg id="c10"></svg></div><p class="say" id="s10"></p></section>

<p class="grp">塞住的時候路能放多少車</p>
<section class="card"><h2>塞住時，每 15 分鐘放行幾台汽車？</h2><div class="ctl">入口 <select id="pick11"></select></div><div class="scroll"><svg id="c11"></svg></div><div class="legend"><span><i class="sw" style="background:var(--s2)"></i>塞住時平均每 15 分鐘通過</span><span>虛線：順的時候 15 分鐘最多通過</span></div><p class="say" id="s11"></p></section>

<p class="note">「塞」＝車速低於 20 km/h。機車混在一般車道計數，可能漏數；環東大道禁行機車；放行量只算汽車。資料來源：臺北市交工處 VDLive.xml。探索用，不是正式結果。</p>
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

// 1. 塞車時刻表
(function () {
  const svg = $('c1'), w = W(svg), L = 140, R = 110, rh = 34, x0 = 5 * 60, x1 = 21 * 60, H = D.ents.length * rh + 26;
  const X = m => L + (m - x0) / (x1 - x0) * (w - L - R);
  let g = '', jam = 0;
  for (let m = x0; m <= x1; m += 120) g += `<line x1="${X(m)}" x2="${X(m)}" y1="0" y2="${H - 20}" stroke="var(--grid)"/><text x="${X(m)}" y="${H - 4}" text-anchor="middle">${hhmm(m)}</text>`;
  D.ents.forEach((v, i) => { const y = i * rh + 4, t = D.timetable[v], txt = [];
    g += `<text class="lab" x="0" y="${y + 17}">${N[v]}</text><line x1="${L}" x2="${w - R}" y1="${y + 13}" y2="${y + 13}" stroke="var(--axis)"/>`;
    for (const k of ['am', 'pm']) { const p = t[k]; if (!p.jam_days) continue; if (k === 'am') jam++;
      g += `<rect x="${X(p.start)}" y="${y + 3}" width="${Math.max(4, X(p.end) - X(p.start))}" height="20" rx="4" fill="var(--s2)" data-t="${N[v]}｜通常 ${hhmm(p.start)}–${hhmm(p.end)}<br>${p.days} 天裡有 ${p.jam_days} 天"/>`;
      txt.push(`${hhmm(p.start)}–${hhmm(p.end)}`); }
    g += `<text class="lab" x="${w - R + 8}" y="${y + 17}">${txt.join('、') || '沒有明顯塞車'}</text>`; });
  svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg);
  const t = D.timetable[D.worst].am;
  say('s1', t.jam_days ? `${D.ents.length} 個入口裡有 ${jam} 個早上會塞，最嚴重的是「${N[D.worst]}」，通常 ${hhmm(t.start)}–${hhmm(t.end)}，${t.days} 天裡有 ${t.jam_days} 天。` : '這幾天早上沒有明顯塞車。');
})();

// 2. 一整天的車速（每個入口一張小圖，同一個刻度）
(function () {
  const box = $('c2'); let deepest = null;
  box.innerHTML = D.ents.map((v, i) => `<div>${N[v]}<svg id="m${i}"></svg></div>`).join('');
  const all = D.ents.flatMap(v => D.curve[v]), x0 = Math.min(...all.map(p => p[0])), x1 = Math.max(...all.map(p => p[0])) + 15;
  D.ents.forEach((v, i) => { const svg = $('m' + i), p = D.curve[v], w = Math.max(280, svg.parentElement.clientWidth), H = 120, L = 26, B = 18;
    const X = m => L + (m - x0) / (x1 - x0) * (w - L - 4), Y = s => 4 + (1 - Math.min(s, 70) / 70) * (H - 4 - B);
    const lo = minOf(p); if (!deepest || lo[1] < deepest[2]) deepest = [v, lo[0], lo[1]];
    let g = `<line x1="${L}" x2="${w}" y1="${Y(D.bad)}" y2="${Y(D.bad)}" stroke="var(--muted)" stroke-dasharray="3 3"/><text x="${L - 4}" y="${Y(D.bad) + 4}" text-anchor="end">20</text>`;
    for (let m = Math.ceil(x0 / 240) * 240; m < x1; m += 240) g += `<text x="${X(m)}" y="${H - 4}" text-anchor="middle">${hhmm(m)}</text>`;
    g += `<polyline fill="none" stroke="var(--s1)" stroke-width="2" points="${p.map(q => X(q[0] + 7.5) + ',' + Y(q[1])).join(' ')}"/>`;
    g += `<circle cx="${X(lo[0] + 7.5)}" cy="${Y(lo[1])}" r="4" fill="var(--s2)"/><text class="lab" x="${X(lo[0] + 7.5) + 7}" y="${Y(lo[1]) + 4}">${Math.round(lo[1])}</text>`;
    for (const q of p) g += `<rect x="${X(q[0])}" y="0" width="${X(q[0] + 15) - X(q[0])}" height="${H - B}" fill="transparent" data-t="${N[v]} ${hhmm(q[0])}｜${q[1]} km/h"/>`;
    svg.setAttribute('width', w); svg.setAttribute('height', H); svg.innerHTML = g; hover(svg); });
  say('s2', `每個入口都在早上出現一個低谷，最深的是「${N[deepest[0]]}」${hhmm(deepest[1])}，只剩 ${Math.round(deepest[2])} km/h（虛線是 20 km/h）。`);
})();

// 3. 每小時有多少車
(function () {
  const p = D.hourly, top = maxOf(p);
  vbars($('c3'), p.map(([h, t]) => [String(h / 60), t, h === top[0] ? '--s2' : '--s1', `${hhmm(h)}–${hhmm(h + 60)}｜每天平均 ${t.toLocaleString()} 輛`]),
    { unit: '輛／小時', labels: [p.indexOf(top)] });
  say('s3', `車最多的是 ${hhmm(top[0])}–${hhmm(top[0] + 60)}，5 個入口合計每天平均 ${top[1].toLocaleString()} 輛。`);
})();

// 4. 早上 vs 傍晚（每個入口兩根）
(function () {
  const items = [];
  D.ents.forEach(v => { const [a, p] = D.minutes[v];
    items.push([N[v], a, '--s1', `${N[v]}｜早上每天平均塞 ${a} 分鐘`], ['', p, '--s2', `${N[v]}｜傍晚每天平均塞 ${p} 分鐘`]); });
  vbars($('c4'), items, { unit: '分鐘／天', every: 2, pair: true, labels: items.map((_, i) => i), ymax: Math.max(10, ...items.map(i => i[1])) * 1.15 });
  const am = D.ents.reduce((s, v) => s + D.minutes[v][0], 0), pm = D.ents.reduce((s, v) => s + D.minutes[v][1], 0);
  say('s4', am === pm ? '早上和傍晚差不多。' : `${am > pm ? '早上' : '傍晚'}比較塞：5 個入口合計每天平均塞 ${Math.max(am, pm)} 分鐘，${am > pm ? '傍晚' : '早上'}只有 ${Math.min(am, pm)} 分鐘。`);
})();

// 5. 各入口最慢的時候
(function () {
  const rows = D.ents.map(v => { const lo = minOf(D.curve[v]); return [N[v], lo[1], lo[0]]; }).sort((a, b) => a[1] - b[1]);
  hbars($('c5'), rows.map(([n, s, m]) => [n, s, step(s), `${Math.round(s)} km/h（${hhmm(m)}）`, `${n}｜最慢在 ${hhmm(m)}，${s} km/h`]), 70);
  say('s5', `「${rows[0][0]}」最慢時只剩 ${Math.round(rows[0][1])} km/h；「${rows[rows.length - 1][0]}」最慢也還有 ${Math.round(rows[rows.length - 1][1])} km/h。條越短越慢。`);
})();

// 6. 每 15 分鐘的平均車速
$('pick').innerHTML = D.ents.map(v => `<option value="${v}"${v === D.worst ? ' selected' : ''}>${N[v]}</option>`).join('');
function c6() {
  const v = $('pick').value, p = D.bars[v] || [];
  if (!p.length) { $('c6').innerHTML = ''; say('s6', '還沒有這個時段的資料。'); return; }
  const lo = minOf(p), hi = maxOf(p), early = p.find(q => q[0] === lo[0] - 60);
  vbars($('c6'), p.map(([b, s]) => [b % 60 === 0 ? hhmm(b) : '', s, step(s), `${hhmm(b)}–${hhmm(b + 15)} 經過｜平均 ${s} km/h`]),
    { unit: 'km/h', ymax: 70, ref: D.bad, labels: [p.indexOf(lo), p.indexOf(hi)].concat(early ? [p.indexOf(early)] : []) });
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
  vbars($('c8'), ks.map(k => [md(k), d[k], step(d[k]), `${md(k)}｜${d[k]} km/h`]), { unit: 'km/h', ymax: 70, ref: D.bad, labels: ks.map((_, i) => i), H: 200 });
  const bad = ks.filter(k => d[k] < D.bad).length;
  say('s8', `${ks.length} 天裡有 ${bad} 天低於 20 km/h（虛線）` + (bad >= ks.length - 1 && bad ? '，幾乎每天都塞，可以預期。' : '，不是每天都塞，比較難預期。'));
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

// 11. 塞住時每 15 分鐘放行幾台汽車（一天一根），虛線是順的時候最多通過多少
$('pick11').innerHTML = D.ents.map(v => `<option value="${v}"${v === (D.ents.includes(D.model_vd) ? D.model_vd : D.worst) ? ' selected' : ''}>${N[v]}</option>`).join('');
function c11() {
  const v = $('pick11').value, f = D.flow[v], top = f.top, model = v === D.model_vd ? `排隊模型目前假設這裡的容量是 ${D.model_cap.toLocaleString()} 輛／15 分鐘，可以用這兩個數字校正。` : '';
  if (!f.days.length) { $('c11').innerHTML = '';
    say('s11', `這幾天${N[v]}沒有塞住（低於 20 km/h）的 15 分鐘，量不到塞車時放行多少` + (top ? `；順的時候 15 分鐘最多通過 ${top[0].toLocaleString()} 輛汽車。` : '。') + model); return; }
  vbars($('c11'), f.days.map(([d, n, k, lo, hi]) => [md(d), n, '--s2', `${md(d)}｜塞住的 ${k} 個 15 分鐘，平均 ${n.toLocaleString()} 輛（${lo.toLocaleString()}–${hi.toLocaleString()}）`]),
    { unit: '輛／15 分鐘', labels: f.days.map((_, i) => i), ref: top ? top[0] : null, ymax: Math.max(top ? top[0] : 0, ...f.days.map(x => x[1])) * 1.15, H: 200 });
  const ns = f.days.map(x => x[1]), lo = Math.min(...ns), hi = Math.max(...ns), drop = top ? Math.round((1 - f.avg / top[0]) * 100) : null;
  say('s11', (top ? `${N[v]}順的時候，15 分鐘最多通過 ${top[0].toLocaleString()} 輛汽車（${md(top[1])} ${hhmm(top[2])}）；` : `${N[v]}`) +
    `塞住時平均只放 ${f.avg.toLocaleString()} 輛` + (drop > 0 ? `，少了 ${drop}%` : '') +
    (ns.length > 1 ? `，每天在 ${lo.toLocaleString()}–${hi.toLocaleString()} 輛之間${hi > lo * 1.1 ? '：同樣在塞，有的天放得比較慢' : ''}。` : '。') + model);
}
$('pick11').onchange = c11; c11();
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
    OUT.write_text(PAGE.replace("__STYLE__", STYLE).replace("__DATA__", data.replace("</", "<\\/")), encoding="utf-8")
    print(f"wrote {OUT}（{len(rows):,} 筆讀數）。執行 open {OUT.relative_to(ROOT.parent)} 用瀏覽器打開")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
