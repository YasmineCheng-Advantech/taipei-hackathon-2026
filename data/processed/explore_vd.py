"""探索用的 VD 圖表：從收集到的資料多看幾個角度，找靈感用，不是作品畫面。

用法：python3 data/processed/explore_vd.py [data/raw/vd_taipei_targets.csv ...]
輸出：data/raw/explore.html（含真實資料，不進 git），接著執行 open data/raw/explore.html

六張圖
1. 車速與流量：每個點是一筆 5 分鐘讀數。流量增加到某個點後車速突然崩掉，那個轉折點大約就是道路容量
2. 每天幾點開始塞、幾點恢復：車速連續低於 20 km/h 的時段
3. 塞車怎麼往後傳：堤頂大道前後 3 支偵測器，看哪一支先變慢
4. 每天差多少：同一個時段，最快、平均、最慢的一天
5. 車種隨時間變化：機車比例、大車比例
6. 早上 vs 傍晚：每天低於 20 km/h 的分鐘數
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from preview_vd import DEFAULT_CSV, MAIN, ROOT, STYLE, load

OUT = ROOT / "raw" / "explore.html"
BAD = 20
TIDING = ["VPMSV40", "VRPSV00", "VRHT600"]  # 堤頂大道北向，依車流方向由上游到下游
AM, PM = (6 * 60, 11 * 60), (15 * 60, 21 * 60)


def minute(t):
    return t.hour * 60 + t.minute


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


def build(rows):
    names = {r["vdid"]: r["name"] for r in rows}
    order = [v for v in MAIN if v in names] + sorted(v for v in names if v not in MAIN)
    by = defaultdict(lambda: defaultdict(list))  # vdid -> 日期 -> [(分鐘, 車速, 車輛)]
    for r in sorted(rows, key=lambda r: r["t"]):
        by[r["vdid"]][r["t"].date().isoformat()].append((minute(r["t"]), r["speed"], r["cars"]))
    days = sorted({d for v in by.values() for d in v})

    scatter = {v: [[sum(c.values()), round(s, 1), m] for d in by[v].values() for m, s, c in d] for v in order}
    jams = {v: {d: runs([(m, s) for m, s, _ in by[v][d]]) for d in by[v]} for v in order}
    chain = {d: {v: [[m, round(s, 1)] for m, s, _ in by[v].get(d, [])] for v in TIDING if v in by} for d in days}

    # 每天差多少：每個 15 分鐘格先算每天的加權車速，再取最慢、平均、最快
    spread = {}
    for v in order:
        per = defaultdict(list)
        for d, pts in by[v].items():
            acc = defaultdict(lambda: [0.0, 0, []])
            for m, s, c in pts:
                n = sum(c.values())
                a = acc[m - m % 15]
                a[0] += s * n
                a[1] += n
                a[2].append(s)
            for b, (sw, n, ss) in acc.items():
                per[b].append(sw / n if n else sum(ss) / len(ss))
        spread[v] = [[b, round(min(x), 1), round(sum(x) / len(x), 1), round(max(x), 1), len(x)]
                     for b, x in sorted(per.items())]

    # 車種隨時間：有機車的偵測器（快速道路禁行機車，排除）合計
    mix = defaultdict(lambda: [0, 0, 0])
    for v in order:
        if not any(c["vol_M"] for d in by[v].values() for _, _, c in d):
            continue
        for d in by[v].values():
            for m, _, c in d:
                x = mix[m - m % 15]
                x[0] += c["vol_M"]
                x[1] += c["vol_L"] + c["vol_T"]
                x[2] += sum(c.values())
    mix = [[b, round(m_ / t * 100, 1), round(l / t * 100, 1)] for b, (m_, l, t) in sorted(mix.items()) if t]

    # 早上 vs 傍晚：每天平均有幾分鐘低於 BAD（每筆讀數算 5 分鐘）
    ampm = {}
    for v in order:
        a = p = 0
        for d in by[v].values():
            a += 5 * sum(1 for m, s, _ in d if s < BAD and AM[0] <= m < AM[1])
            p += 5 * sum(1 for m, s, _ in d if s < BAD and PM[0] <= m < PM[1])
        n = len(by[v]) or 1
        ampm[v] = [round(a / n), round(p / n)]

    return dict(order=order, names=names, main=[v for v in MAIN if v in names], days=days, bad=BAD,
                scatter=scatter, jams=jams, chain=chain, tiding=[v for v in TIDING if v in by], spread=spread,
                mix=mix, ampm=ampm)


PAGE = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VD 探索圖表</title>
__STYLE__
<style>.ctl{display:flex;flex-wrap:wrap;gap:8px;align-items:center;margin-bottom:8px;font-size:13px;color:var(--ink2)}
.ctl select{font:inherit;padding:4px 8px;border-radius:8px;border:1px solid var(--axis);background:var(--surface);color:var(--ink)}
.ask{color:var(--ink2);font-size:13px;margin:8px 0 0;padding-left:12px;border-left:3px solid var(--grid)}</style></head><body><main>
<h1>VD 探索圖表</h1><p class="sub">從收集到的資料多看幾個角度，找靈感用。每張圖下方是看圖時可以問的問題。</p>

<section class="card"><h2>1. 車速與流量</h2><p class="note">每個點是一筆 5 分鐘讀數。橘色是 07:00–10:00，藍色是其他時段。</p>
<div class="ctl">偵測器 <select id="sc"></select></div><div class="scroll"><svg id="g1"></svg></div>
<div class="legend"><span><i class="sw" style="background:var(--s2)"></i>07:00–10:00</span><span><i class="sw" style="background:var(--s1)"></i>其他時段</span></div>
<p class="ask">流量增加到哪裡時車速開始崩？崩掉之後，流量是不是反而變少（車子卡住，偵測器數到的車變少）？那個轉折點大約就是這條路一次能過多少車。</p></section>

<section class="card"><h2>2. 每天幾點開始塞、幾點恢復</h2><p class="note">每一列是一個偵測器的一天，色塊是車速連續低於 20 km/h 的時段。</p>
<div class="scroll"><svg id="g2"></svg></div>
<p class="ask">每天開始塞的時間很固定，還是差很多？哪個入口最早開始塞、最晚恢復？傍晚也會塞嗎？</p></section>

<section class="card"><h2>3. 塞車怎麼往後傳（堤頂大道北向）</h2><p class="note">由上到下是車流方向的前後 3 支偵測器，越慢顏色越醒目。</p>
<div class="ctl">日期 <select id="cd"></select></div><div class="scroll"><svg id="g3"></svg></div><div class="legend" id="l3"></div>
<p class="ask">哪一支最先變慢？如果是下游先慢、上游晚一點才慢，代表車隊從下游的路口一路排回來，真正卡住的地方在下游。</p></section>

<section class="card"><h2>4. 每天差多少</h2><p class="note">每 15 分鐘：色帶是最快到最慢的一天，線是平均。</p>
<div class="ctl">偵測器 <select id="vs"></select></div><div class="scroll"><svg id="g4"></svg></div>
<p class="ask">哪個時段色帶最寬？那就是「同樣時間出門，有時候順、有時候塞」的時段。開車的人怕的通常不是平均慢，是不知道今天會不會特別慢。</p></section>

<section class="card"><h2>5. 車種隨時間變化</h2><p class="note">有機車的偵測器合計（快速道路禁行機車，不算在內）。機車混在一般車道計數，可能有漏數。</p>
<div class="scroll"><svg id="g5a"></svg></div><div class="scroll"><svg id="g5b"></svg></div>
<p class="ask">機車是不是比汽車更早出門？尖峰時大車（大型車、聯結車）多不多？如果不少，限制大車尖峰時段行駛會不會比說服上班族錯峰更容易？</p></section>

<section class="card"><h2>6. 早上 vs 傍晚</h2><p class="note">每天平均有幾分鐘車速低於 20 km/h。早上算 06:00–11:00，傍晚算 15:00–21:00。</p>
<div id="g6"></div><div class="legend"><span><i class="sw" style="background:var(--s1)"></i>早上</span><span><i class="sw" style="background:var(--s2)"></i>傍晚</span></div>
<p class="ask">早上和傍晚哪個比較嚴重？上班時間通常比下班時間集中，如果早上明顯比較塞，錯峰從「上班」下手最有效。</p></section>

<p class="note">資料來源：臺北市交工處 VDLive.xml，由 data/fetch/collect_vd.py 收集。探索用，不是正式結果。</p>
</main><div id="tip"></div>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id), tip = $('tip');
const hhmm = m => String(Math.floor(m/60)).padStart(2,'0') + ':' + String(m%60).padStart(2,'0');
const show = (e, html) => { tip.innerHTML = html; tip.style.display = 'block';
  tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; };
const hide = () => tip.style.display = 'none';
const STEPS = [[50,'--q0','50 以上'],[40,'--q1','40–50'],[30,'--q2','30–40'],[20,'--q3','20–30'],[10,'--q4','10–20'],[-1,'--q5','10 以下']];
const step = v => STEPS.find(s => v >= s[0])[1];
const opts = (id, list, label) => { $(id).innerHTML = list.map(v => `<option value="${v}">${label(v)}</option>`).join(''); };
const width = svg => Math.max(640, svg.parentElement.clientWidth);
// 共用座標軸：回傳 x、y 比例與格線
function frame(svg, H, x0, x1, y0, y1, xs, ys, xf, yf, L = 44, R = 16, T = 10, B = 26) {
  const W = width(svg); svg.setAttribute('width', W); svg.setAttribute('height', H);
  const X = v => L + (v - x0) / (x1 - x0) * (W - L - R), Y = v => T + (1 - (v - y0) / (y1 - y0)) * (H - T - B);
  let g = '';
  for (let v = y0; v <= y1 + 1e-9; v += ys) g += `<line x1="${L}" x2="${W-R}" y1="${Y(v)}" y2="${Y(v)}" stroke="var(--grid)"/><text x="${L-6}" y="${Y(v)+4}" text-anchor="end">${yf(v)}</text>`;
  for (let v = Math.ceil(x0 / xs) * xs; v <= x1; v += xs) g += `<text x="${X(v)}" y="${H-8}" text-anchor="middle">${xf(v)}</text>`;
  return { W, X, Y, g, L, R, T, B };
}
const span = (pts, f) => [Math.min(...pts.map(f)), Math.max(...pts.map(f))];

// 1. 車速與流量
opts('sc', D.order, v => D.names[v]);
function g1() {
  const svg = $('g1'), pts = D.scatter[$('sc').value] || [];
  if (!pts.length) { svg.innerHTML = ''; return; }
  const xmax = Math.ceil(Math.max(...pts.map(p => p[0]), 10) / 20) * 20;
  const f = frame(svg, 300, 0, xmax, 0, 80, Math.max(20, xmax / 8), 20, v => v + ' 輛', v => v);
  f.g += `<line x1="${f.L}" x2="${f.W-f.R}" y1="${f.Y(D.bad)}" y2="${f.Y(D.bad)}" stroke="var(--muted)" stroke-dasharray="4 4"/>`;
  for (const [n, s, m] of pts) { const peak = m >= 420 && m < 600;
    f.g += `<circle cx="${f.X(n)}" cy="${f.Y(Math.min(s, 80))}" r="3" fill="var(${peak ? '--s2' : '--s1'})" fill-opacity="${peak ? .8 : .35}" data-t="${hhmm(m)}｜${n} 輛／5 分鐘｜${s} km/h"/>`; }
  svg.innerHTML = f.g + `<text x="${f.L}" y="${f.T + 10}">車速 km/h</text>`;
}
$('sc').onchange = g1; $('g1').onmousemove = e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide(); $('g1').onmouseleave = hide;

// 2. 每天幾點開始塞
function g2() {
  const svg = $('g2'), rows = [];
  for (const v of D.order) for (const d of D.days) rows.push([v, d, (D.jams[v] || {})[d] || []]);
  const all = Object.values(D.scatter).flat().map(p => p[2]);
  const x0 = Math.floor(Math.min(...all) / 60) * 60, x1 = Math.ceil((Math.max(...all) + 5) / 60) * 60, rh = 14;
  const H = rows.length * rh + 40, L = 210;
  const f = frame(svg, H, x0, x1, 0, 1, 60, 2, hhmm, () => '', L);
  let g = f.g.replace(/<line[^>]*\/><text[^>]*><\/text>/g, '');
  for (let m = x0; m <= x1; m += 60) g += `<line x1="${f.X(m)}" x2="${f.X(m)}" y1="10" y2="${H-26}" stroke="var(--grid)"/>`;
  rows.forEach(([v, d, rs], i) => { const y = 12 + i * rh;
    if (D.days.indexOf(d) === 0) g += `<text class="lab" x="8" y="${y + 10}">${D.names[v]}</text>`;
    g += `<text x="${L - 8}" y="${y + 10}" text-anchor="end">${d.slice(5).replace('-', '/')}</text>`;
    for (const [a, b] of rs) g += `<rect x="${f.X(a)}" y="${y + 2}" width="${Math.max(2, f.X(b) - f.X(a))}" height="${rh - 4}" rx="2" fill="var(--s2)" data-t="${D.names[v]} ${d.slice(5)}｜${hhmm(a)}–${hhmm(b)} 低於 ${D.bad} km/h"/>`; });
  svg.innerHTML = g;
}
$('g2').onmousemove = e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide(); $('g2').onmouseleave = hide;

// 3. 塞車怎麼往後傳
opts('cd', D.days, d => d.slice(5).replace('-', '/')); $('cd').value = D.days[D.days.length - 1];
function g3() {
  const svg = $('g3'), ser = D.chain[$('cd').value] || {}, all = Object.values(ser).flat();
  if (!all.length || !D.tiding.length) { svg.innerHTML = '<text x="8" y="20">這天沒有堤頂大道的資料</text>'; svg.setAttribute('height', 30); return; }
  const [x0, x1] = span(all, p => p[0]), rh = 30, L = 210, W = width(svg), H = D.tiding.length * rh + 34;
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  const X = m => L + (m - x0) / (x1 + 5 - x0) * (W - L - 16), cw = Math.max(1, X(x0 + 5) - X(x0) - 1);
  let g = '';
  for (let m = Math.ceil(x0 / 60) * 60; m <= x1; m += 60) g += `<text x="${X(m)}" y="${H - 8}" text-anchor="middle">${hhmm(m)}</text>`;
  D.tiding.forEach((v, i) => { const y = 6 + i * rh;
    g += `<text class="lab" x="8" y="${y + 19}">${i + 1}. ${D.names[v]}</text>`;
    for (const [m, s] of ser[v] || []) g += `<rect x="${X(m)}" y="${y}" width="${cw}" height="${rh - 6}" fill="var(${step(s)})" data-t="${D.names[v]}｜${hhmm(m)}｜${s} km/h"/>`; });
  svg.innerHTML = g;
}
$('l3').innerHTML = '車速 km/h：' + STEPS.map(s => `<span><i class="sw" style="background:var(${s[1]})"></i>${s[2]}</span>`).join('');
$('cd').onchange = g3; $('g3').onmousemove = e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide(); $('g3').onmouseleave = hide;

// 4. 每天差多少
opts('vs', D.order, v => D.names[v]); if (D.order.includes('VPMSV40')) $('vs').value = 'VPMSV40';
function g4() {
  const svg = $('g4'), p = D.spread[$('vs').value] || [];
  if (!p.length) { svg.innerHTML = ''; return; }
  const [x0, x1] = span(p, q => q[0]);
  const f = frame(svg, 260, x0, x1 + 15, 0, 80, 60, 20, hhmm, v => v);
  const band = p.map(q => `${f.X(q[0] + 7.5)},${f.Y(Math.min(q[3], 80))}`).concat(p.slice().reverse().map(q => `${f.X(q[0] + 7.5)},${f.Y(q[1])}`)).join(' ');
  f.g += `<polygon points="${band}" fill="var(--s1)" fill-opacity=".22"/>`;
  f.g += `<polyline fill="none" stroke="var(--s1)" stroke-width="2" points="${p.map(q => `${f.X(q[0] + 7.5)},${f.Y(Math.min(q[2], 80))}`).join(' ')}"/>`;
  f.g += `<line x1="${f.L}" x2="${f.W-f.R}" y1="${f.Y(D.bad)}" y2="${f.Y(D.bad)}" stroke="var(--muted)" stroke-dasharray="4 4"/>`;
  for (const q of p) f.g += `<rect x="${f.X(q[0])}" y="${f.T}" width="${f.X(q[0] + 15) - f.X(q[0])}" height="${260 - f.T - f.B}" fill="transparent" data-t="${hhmm(q[0])}–${hhmm(q[0] + 15)}<br>最慢 ${q[1]}・平均 ${q[2]}・最快 ${q[3]} km/h（${q[4]} 天）"/>`;
  svg.innerHTML = f.g;
}
$('vs').onchange = g4; $('g4').onmousemove = e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide(); $('g4').onmouseleave = hide;

// 5. 車種隨時間
function line5(id, idx, label, color) {
  const svg = $(id), p = D.mix;
  if (!p.length) { svg.innerHTML = ''; return; }
  const [x0, x1] = span(p, q => q[0]), ymax = Math.max(5, Math.ceil(Math.max(...p.map(q => q[idx])) / 5) * 5);
  const f = frame(svg, 190, x0, x1 + 15, 0, ymax, 60, ymax / 4, hhmm, v => v + '%', 44, 16, 26);
  f.g += `<text x="${f.L}" y="14" class="lab">${label}</text>`;
  f.g += `<polyline fill="none" stroke="var(${color})" stroke-width="2" points="${p.map(q => `${f.X(q[0] + 7.5)},${f.Y(q[idx])}`).join(' ')}"/>`;
  for (const q of p) f.g += `<rect x="${f.X(q[0])}" y="${f.T}" width="${f.X(q[0] + 15) - f.X(q[0])}" height="${190 - f.T - f.B}" fill="transparent" data-t="${hhmm(q[0])}｜${label} ${q[idx]}%"/>`;
  svg.innerHTML = f.g; svg.onmousemove = e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide(); svg.onmouseleave = hide;
}

// 6. 早上 vs 傍晚
function g6() {
  const max = Math.max(1, ...Object.values(D.ampm).flat());
  $('g6').innerHTML = D.order.map(v => { const [a, p] = D.ampm[v];
    return `<div class="brow"><span class="n">${D.names[v]}</span><span style="flex:1">` +
      `<span class="bar" style="height:10px;margin-bottom:2px"><span style="width:${a / max * 100}%;background:var(--s1)"></span></span>` +
      `<span class="bar" style="height:10px"><span style="width:${p / max * 100}%;background:var(--s2)"></span></span></span>` +
      `<span class="m" style="width:110px">${a}／${p} 分鐘</span></div>`; }).join('');
}

const all = () => { g1(); g2(); g3(); g4(); line5('g5a', 1, '機車比例', '--s1'); line5('g5b', 2, '大車比例', '--s2'); g6(); };
all(); addEventListener('resize', all);
</script></body></html>
"""


def main(argv):
    paths = argv or [DEFAULT_CSV]
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print(f"找不到 {', '.join(map(str, missing))}；收集程式至少要成功抓過一次")
        return 1
    rows, _ = load(paths)
    if not rows:
        print("檔案裡還沒有有效讀數")
        return 1
    data = json.dumps(build(rows), ensure_ascii=False)
    OUT.write_text(PAGE.replace("__STYLE__", STYLE).replace("__DATA__", data.replace("</", "<\\/")), encoding="utf-8")
    print(f"wrote {OUT}（{len(rows):,} 筆讀數）。執行 open {OUT.relative_to(ROOT.parent)} 用瀏覽器打開")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
