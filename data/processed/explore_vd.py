"""探索用的 VD 圖表：先講結論，圖只回答一個問題，找靈感用，不是作品畫面。

用法：python3 data/processed/explore_vd.py [data/raw/vd_taipei_targets.csv ...]
輸出：data/raw/explore.html（含真實資料，不進 git），接著執行 open data/raw/explore.html

內容（每張圖的標題都是從資料算出來的一句話）
1. 這幾天的重點：最塞的入口與時段、早一點經過差多少、每天穩不穩、早上 vs 傍晚、機車比例
2. 塞車時刻表：每個入口通常幾點開始塞、幾點恢復
3. 早一點經過有差嗎：選一個入口，看每 15 分鐘的平均車速
4. 每天都一樣塞嗎：最塞的那 15 分鐘，每一天的車速
5. 早上 vs 傍晚：每天平均塞幾分鐘
6. 路上都是什麼車：每 10 輛車裡有幾輛機車
「塞」的定義：車速連續低於 20 km/h（至少 2 筆讀數）。
"""
import json
import sys
from collections import defaultdict
from pathlib import Path

from preview_vd import DEFAULT_CSV, MAIN, ROOT, STYLE, VEH, load

OUT = ROOT / "raw" / "explore.html"
BAD = 20
AM, PM = (6 * 60, 11 * 60), (15 * 60, 21 * 60)
BARS = (6 * 60, 10 * 60 + 30)  # 「早一點經過有差嗎」的時段


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


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


def build(rows):
    names = {r["vdid"]: r["name"] for r in rows}
    ents = [v for v in MAIN if v in names]
    by = defaultdict(lambda: defaultdict(list))  # vdid -> 日期 -> [(分鐘, 車速, 車輛)]
    for r in sorted(rows, key=lambda r: r["t"]):
        by[r["vdid"]][r["t"].date().isoformat()].append((r["t"].hour * 60 + r["t"].minute, r["speed"], r["cars"]))

    # 塞車時刻表：每天的第一段開始、最後一段結束，取中位數
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

    # 早一點經過有差嗎：每 15 分鐘的平均車速，以及每一天的
    bars, daily = {}, {}
    for v in ents:
        acc, per_day = defaultdict(list), defaultdict(dict)
        for d, pts in by[v].items():
            day_bins = defaultdict(list)
            for p in pts:
                if BARS[0] <= p[0] < BARS[1]:
                    acc[p[0] - p[0] % 15].append(p)
                    day_bins[p[0] - p[0] % 15].append(p)
            for b, ps in day_bins.items():
                per_day[b][d] = round(weighted(ps), 1)
        bars[v] = [[b, round(weighted(ps), 1)] for b, ps in sorted(acc.items())]
        daily[v] = {b: per_day[b] for b in per_day}

    worst = max(ents, key=lambda v: (minutes[v][0], -min((s for _, s in bars[v]), default=99)))
    wb = min(bars[worst], key=lambda x: x[1]) if bars[worst] else None
    earlier = next((x for x in bars[worst] if wb and x[0] == wb[0] - 60), None)
    wdays = daily[worst].get(wb[0], {}) if wb else {}

    # 路上都是什麼車：有機車的偵測器合計（快速道路禁行機車，排除）
    tot = {k: 0 for k, _ in VEH}
    for v in names:
        if any(c["vol_M"] for pts in by[v].values() for _, _, c in pts):
            for pts in by[v].values():
                for _, _, c in pts:
                    for k in tot:
                        tot[k] += c[k]
    allc = sum(tot.values()) or 1
    mix = [[label, round(tot[k] / allc * 100, 1)] for k, label in VEH]

    # 重點句
    t = timetable[worst]["am"]
    am_all, pm_all = sum(m[0] for m in minutes.values()), sum(m[1] for m in minutes.values())
    facts = []
    if t["jam_days"]:
        facts.append(f"最塞的是「{names[worst]}」：通常 {hhmm(t['start'])}–{hhmm(t['end'])} 塞車，"
                     f"{t['days']} 天裡有 {t['jam_days']} 天。")
    else:
        facts.append("這幾天早上沒有明顯塞車（車速都在 20 km/h 以上）。")
    if wb and earlier and earlier[1] > wb[1]:
        facts.append(f"{names[worst]}最慢在 {hhmm(wb[0])}，平均 {wb[1]:.0f} km/h；提早 1 小時（{hhmm(earlier[0])}）經過約 "
                     f"{earlier[1]:.0f} km/h，快 {earlier[1] / max(wb[1], 1):.1f} 倍。")
    if wdays:
        bad = sum(s < BAD for s in wdays.values())
        facts.append(f"{names[worst]} {hhmm(wb[0])}：{len(wdays)} 天裡有 {bad} 天低於 {BAD} km/h"
                     + ("，幾乎每天都塞。" if bad >= len(wdays) - 1 and bad else "，不是每天都塞。"))
    if am_all or pm_all:
        more = "早上" if am_all >= pm_all else "傍晚"
        facts.append(f"{more}比較塞：5 個入口加起來，早上每天平均塞 {am_all} 分鐘，傍晚 {pm_all} 分鐘。")
    facts.append(f"每 10 輛車裡，約有 {round(mix[0][1] / 10)} 輛是機車（不含禁行機車的環東大道）。")

    return dict(names=names, ents=ents, worst=worst, bad=BAD, timetable=timetable, bars=bars, daily=daily,
                worst_bin=wb[0] if wb else None, minutes=minutes, mix=mix, facts=facts,
                days=sorted({d for v in by.values() for d in v}))


PAGE = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>這幾天的路況</title>
__STYLE__
<style>.facts{margin:0;padding:0;list-style:none}.facts li{font-size:17px;line-height:1.6;padding:10px 0;border-bottom:1px solid var(--grid)}.facts li:last-child{border:0}
.facts b{font-variant-numeric:tabular-nums}.ctl{display:flex;gap:8px;align-items:center;margin:8px 0;font-size:13px;color:var(--ink2)}
.ctl select{font:inherit;padding:4px 8px;border-radius:8px;border:1px solid var(--axis);background:var(--surface);color:var(--ink)}
h2{font-size:18px}.q{color:var(--muted);font-size:13px;margin:0 0 2px}
.pict{display:flex;gap:8px;flex-wrap:wrap;margin:12px 0}.pict i{width:34px;height:34px;border-radius:8px;display:block}</style></head><body><main>
<h1>這幾天的路況</h1><p class="sub" id="sub"></p>
<section class="card"><p class="q">先講結論</p><ul class="facts" id="facts"></ul></section>

<section class="card"><p class="q">每個入口幾點塞？</p><h2 id="h1"></h2>
<p class="note">橘色是通常塞車的時段（每天開始與結束時間的中間值）。「塞」是車速連續低於 20 km/h。</p><div class="scroll"><svg id="g1"></svg></div></section>

<section class="card"><p class="q">早一點經過有差嗎？</p><h2 id="h2"></h2>
<div class="ctl">入口 <select id="s2"></select></div><p class="note">每根是那 15 分鐘的平均車速，越短越慢。虛線是 20 km/h。</p><div class="scroll"><svg id="g2"></svg></div></section>

<section class="card"><p class="q">每天都一樣塞嗎？</p><h2 id="h3"></h2>
<p class="note">最塞的那 15 分鐘，每一天的平均車速。</p><div id="g3"></div></section>

<section class="card"><p class="q">早上還是傍晚比較塞？</p><h2 id="h4"></h2>
<p class="note">每天平均塞幾分鐘。早上算 06:00–11:00，傍晚算 15:00–21:00。</p><div id="g4"></div></section>

<section class="card"><p class="q">路上都是什麼車？</p><h2 id="h5"></h2>
<div class="pict" id="g5"></div><div class="legend" id="l5"></div>
<p class="note">不含禁行機車的環東大道。機車混在一般車道計數，可能有漏數。</p></section>

<p class="note">資料來源：臺北市交工處 VDLive.xml，由 data/fetch/collect_vd.py 收集。探索用，不是正式結果。</p>
</main><div id="tip"></div>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id), tip = $('tip');
const hhmm = m => String(Math.floor(m/60)).padStart(2,'0') + ':' + String(m%60).padStart(2,'0');
const show = (e, html) => { tip.innerHTML = html; tip.style.display = 'block';
  tip.style.left = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8) + 'px'; tip.style.top = (e.clientY + 14) + 'px'; };
const hide = () => tip.style.display = 'none';
const hover = el => { el.onmousemove = e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide(); el.onmouseleave = hide; };
const STEPS = [[50,'--q0'],[40,'--q1'],[30,'--q2'],[20,'--q3'],[10,'--q4'],[-1,'--q5']];
const step = v => STEPS.find(s => v >= s[0])[1];
const W = el => Math.max(560, el.parentElement.clientWidth);
const N = D.names;
$('sub').textContent = `${D.days.length} 天的資料（${D.days.map(d => d.slice(5).replace('-', '/')).join('、')}）`;
$('facts').innerHTML = D.facts.map(f => `<li>${f.replace(/(\d[\d.:–]*)/g, '<b>$1</b>')}</li>`).join('');

// 1. 塞車時刻表
function g1() {
  const svg = $('g1'), w = W(svg), L = 140, R = 110, rh = 36, x0 = 5 * 60, x1 = 21 * 60, H = D.ents.length * rh + 30;
  svg.setAttribute('width', w); svg.setAttribute('height', H);
  const X = m => L + (m - x0) / (x1 - x0) * (w - L - R);
  let g = '';
  for (let m = x0; m <= x1; m += 120) g += `<line x1="${X(m)}" x2="${X(m)}" y1="0" y2="${H - 22}" stroke="var(--grid)"/><text x="${X(m)}" y="${H - 6}" text-anchor="middle">${hhmm(m)}</text>`;
  let worstRow = null;
  D.ents.forEach((v, i) => { const y = i * rh + 6, t = D.timetable[v];
    g += `<text class="lab" x="0" y="${y + 18}">${N[v]}</text><line x1="${L}" x2="${w - R}" y1="${y + 14}" y2="${y + 14}" stroke="var(--axis)"/>`;
    let txt = [];
    for (const k of ['am', 'pm']) { const p = t[k]; if (!p.jam_days) continue;
      g += `<rect x="${X(p.start)}" y="${y + 4}" width="${Math.max(4, X(p.end) - X(p.start))}" height="20" rx="4" fill="var(--s2)" data-t="${N[v]}｜通常 ${hhmm(p.start)}–${hhmm(p.end)} 塞<br>${p.days} 天裡有 ${p.jam_days} 天"/>`;
      txt.push(`${hhmm(p.start)}–${hhmm(p.end)}`); }
    g += `<text class="lab" x="${w - R + 8}" y="${y + 18}">${txt.length ? txt.join('、') : '沒有明顯塞車'}</text>`; });
  svg.innerHTML = g; hover(svg);
  const t = D.timetable[D.worst].am;
  $('h1').textContent = t.jam_days ? `${N[D.worst]}最塞，通常 ${hhmm(t.start)}–${hhmm(t.end)}` : '這幾天早上沒有明顯塞車';
}

// 2. 早一點經過有差嗎
$('s2').innerHTML = D.ents.map(v => `<option value="${v}"${v === D.worst ? ' selected' : ''}>${N[v]}</option>`).join('');
function g2() {
  const v = $('s2').value, p = D.bars[v] || [], svg = $('g2'), w = W(svg), H = 260, L = 36, B = 26, T = 22;
  svg.setAttribute('width', w); svg.setAttribute('height', H);
  if (!p.length) { svg.innerHTML = '<text x="0" y="20">還沒有這個時段的資料</text>'; $('h2').textContent = ''; return; }
  const ymax = 70, bw = (w - L) / p.length, Y = s => T + (1 - Math.min(s, ymax) / ymax) * (H - T - B);
  const lo = p.reduce((a, b) => b[1] < a[1] ? b : a), hi = p.reduce((a, b) => b[1] > a[1] ? b : a);
  let g = '';
  for (let s = 0; s <= ymax; s += 20) g += `<text x="${L - 6}" y="${Y(s) + 4}" text-anchor="end">${s}</text>`;
  p.forEach(([b, s], i) => { const x = L + i * bw + 2;
    g += `<rect x="${x}" y="${Y(s)}" width="${bw - 4}" height="${Y(0) - Y(s)}" rx="3" fill="var(${step(s)})" data-t="${hhmm(b)}–${hhmm(b + 15)} 經過｜平均 ${s} km/h"/>`;
    if (b % 60 === 0) g += `<text x="${x + bw / 2}" y="${H - 8}" text-anchor="middle">${hhmm(b)}</text>`;
    if (b === lo[0] || b === hi[0]) g += `<text class="lab" x="${x + bw / 2 - 2}" y="${Y(s) - 6}" text-anchor="middle">${Math.round(s)}</text>`; });
  g += `<line x1="${L}" x2="${w}" y1="${Y(D.bad)}" y2="${Y(D.bad)}" stroke="var(--muted)" stroke-dasharray="4 4"/><text x="${L}" y="12">km/h</text>`;
  svg.innerHTML = g; hover(svg);
  $('h2').textContent = `${hhmm(lo[0])} 最慢（${Math.round(lo[1])} km/h），${hhmm(hi[0])} 最快（${Math.round(hi[1])} km/h），差 ${(hi[1] / Math.max(lo[1], 1)).toFixed(1)} 倍`;
}
$('s2').onchange = g2;

// 3. 每天都一樣塞嗎
function g3() {
  const b = D.worst_bin, d = b == null ? {} : D.daily[D.worst][b] || {}, ks = Object.keys(d).sort();
  if (!ks.length) { $('h3').textContent = '資料還不夠'; $('g3').innerHTML = ''; return; }
  const bad = ks.filter(k => d[k] < D.bad).length;
  $('h3').textContent = `${N[D.worst]} ${hhmm(b)}：${ks.length} 天裡有 ${bad} 天低於 ${D.bad} km/h`;
  $('g3').innerHTML = ks.map(k => `<div class="brow"><span class="n">${k.slice(5).replace('-', '/')}</span><span class="bar"><span style="width:${Math.min(d[k], 70) / 70 * 100}%;background:var(${step(d[k])})"></span></span><span class="m" style="width:120px">${d[k]} km/h${d[k] < D.bad ? '・塞' : ''}</span></div>`).join('');
}

// 4. 早上 vs 傍晚
function g4() {
  const max = Math.max(1, ...Object.values(D.minutes).flat());
  const am = D.ents.reduce((a, v) => a + D.minutes[v][0], 0), pm = D.ents.reduce((a, v) => a + D.minutes[v][1], 0);
  $('h4').textContent = am === pm ? '早上和傍晚差不多' : `${am > pm ? '早上' : '傍晚'}比較塞（每天平均 ${Math.max(am, pm)} 分鐘 vs ${Math.min(am, pm)} 分鐘）`;
  $('g4').innerHTML = D.ents.map(v => { const [a, p] = D.minutes[v];
    return `<div class="brow"><span class="n">${N[v]}</span><span style="flex:1">` +
      `<span class="bar" style="height:12px;margin-bottom:3px"><span style="width:${a / max * 100}%;background:var(--s1)"></span></span>` +
      `<span class="bar" style="height:12px"><span style="width:${p / max * 100}%;background:var(--s2)"></span></span></span>` +
      `<span class="m" style="width:130px">早上 ${a}・傍晚 ${p} 分</span></div>`; }).join('') +
    '<div class="legend"><span><i class="sw" style="background:var(--s1)"></i>早上</span><span><i class="sw" style="background:var(--s2)"></i>傍晚</span></div>';
}

// 5. 路上都是什麼車
function g5() {
  const cols = ['--s1', '--s2', '--s3', '--s4'];
  let left = 10, cells = [];
  const counts = D.mix.map(([, p]) => Math.round(p / 10));
  counts[1] += 10 - counts.reduce((a, b) => a + b, 0);
  D.mix.forEach(([label], i) => { for (let k = 0; k < Math.max(0, counts[i]) && left > 0; k++, left--) cells.push(`<i style="background:var(${cols[i]})" title="${label}"></i>`); });
  $('g5').innerHTML = cells.join('');
  $('l5').innerHTML = D.mix.map(([label, p], i) => `<span><i class="sw" style="background:var(${cols[i]})"></i>${label} ${p}%</span>`).join('');
  $('h5').textContent = `每 10 輛車裡，約 ${counts[0]} 輛是機車`;
}

const all = () => { g1(); g2(); g3(); g4(); g5(); };
all(); addEventListener('resize', () => { g1(); g2(); });
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
