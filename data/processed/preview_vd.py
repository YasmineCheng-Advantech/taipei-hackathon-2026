"""把收集中的 VD 讀數畫成一頁預覽，用瀏覽器打開就能看，不需要網路。

用法：python3 data/processed/preview_vd.py [data/raw/vd_taipei_targets.csv ...]
輸出：data/raw/preview.html（含真實資料，和原始檔一樣不進 git），接著執行 open data/raw/preview.html

內容
- 熱力圖：每個偵測器 × 每 15 分鐘的平均車速（收到的每一天平均），越慢顏色越醒目
- 折線圖：選一天，看 5 個入口每 5 分鐘的車速變化
- 車種組成：各入口機車、小客車、大車、聯結車的比例
- 最新讀數表
規則和 build_vd_15min.py 相同：只用狀態正常的讀數，同一筆不重複計算，車速依車輛數加權。
"""
import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CSV = ROOT / "raw" / "vd_taipei_targets.csv"
OUT = ROOT / "raw" / "preview.html"
MAIN = ["VTXQJ20", "VPMSV40", "VQBUL20", "VMLXB00", "V6310G0"]  # 5 個入口；其餘是備用偵測器
VEH = [("vol_M", "機車"), ("vol_S", "小客車"), ("vol_L", "大車"), ("vol_T", "聯結車")]


def load(paths):
    seen, rows, skipped = set(), [], 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                key = (r["vdid"], r["collect_time"])
                if key in seen:
                    continue
                seen.add(key)
                if r["status"] != "0" or r["speed"] == "":
                    skipped += 1
                    continue
                t = dt.datetime.fromisoformat(r["collect_time"])
                rows.append(dict(vdid=r["vdid"], name=r["entrance"], t=t, speed=float(r["speed"]),
                                 cars={k: int(r[k] or 0) for k, _ in VEH}))
    return rows, skipped


def build(rows, skipped):
    names = {}
    for r in rows:
        names[r["vdid"]] = r["name"]
    order = [v for v in MAIN if v in names] + sorted(v for v in names if v not in MAIN)

    # 熱力圖：時段（一天中的 15 分鐘）× 偵測器，跨天依車輛數加權平均
    heat = defaultdict(lambda: [0.0, 0, set(), []])
    for r in rows:
        m = r["t"].hour * 60 + r["t"].minute
        b = m - m % 15
        n = sum(r["cars"].values())
        h = heat[(r["vdid"], b)]
        h[0] += r["speed"] * n
        h[1] += n
        h[2].add(r["t"].date())
        h[3].append(r["speed"])
    bins = sorted({b for _, b in heat})
    cells = {}
    for (v, b), (sw, n, days, sp) in heat.items():
        cells[f"{v}|{b}"] = dict(v=round(sw / n if n else sum(sp) / len(sp), 1), days=len(days))

    # 折線圖：每天、每支主要偵測器的 5 分鐘車速
    lines = defaultdict(lambda: defaultdict(list))
    for r in sorted(rows, key=lambda r: r["t"]):
        if r["vdid"] in MAIN:
            lines[r["t"].date().isoformat()][r["vdid"]].append(
                [r["t"].hour * 60 + r["t"].minute, round(r["speed"], 1)])

    # 車種組成
    comp = {v: {k: 0 for k, _ in VEH} for v in order}
    for r in rows:
        for k, _ in VEH:
            comp[r["vdid"]][k] += r["cars"][k]

    latest = {}
    for r in rows:
        if r["vdid"] not in latest or r["t"] > latest[r["vdid"]]["t"]:
            latest[r["vdid"]] = r
    table = [dict(vdid=v, name=names[v], time=latest[v]["t"].strftime("%m/%d %H:%M"), speed=latest[v]["speed"],
                  cars=latest[v]["cars"]) for v in order]

    times = [r["t"] for r in rows]
    return dict(
        order=order, names=names, main=[v for v in MAIN if v in names], bins=bins, cells=cells,
        lines=lines, comp=comp, veh=VEH, table=table,
        summary=dict(n=len(rows), skipped=skipped, days=len({t.date() for t in times}),
                     first=min(times).strftime("%m/%d %H:%M"), last=max(times).strftime("%m/%d %H:%M"),
                     built=dt.datetime.now().strftime("%m/%d %H:%M")),
    )


PAGE = r"""<!doctype html>
<html lang="zh-Hant"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>VD 收集預覽</title>
<style>
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--s5:#e87ba4;--empty:#f0efec;
--q0:#cde2fb;--q1:#9ec5f4;--q2:#6da7ec;--q3:#2a78d6;--q4:#1c5cab;--q5:#0d366b}
@media (prefers-color-scheme:dark){:root:where(:not([data-theme="light"])){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--empty:#262624;
--q0:#0d366b;--q1:#184f95;--q2:#256abf;--q3:#3987e5;--q4:#6da7ec;--q5:#b7d3f6}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--s5:#d55181;--empty:#262624;
--q0:#0d366b;--q1:#184f95;--q2:#256abf;--q3:#3987e5;--q4:#6da7ec;--q5:#b7d3f6}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 -apple-system,"PingFang TC","Noto Sans TC",sans-serif}
main{max-width:1100px;margin:0 auto;padding:24px 16px 48px}h1{font-size:22px;margin:0 0 4px}h2{font-size:17px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 16px}.card{background:var(--surface);border:1px solid var(--grid);border-radius:12px;padding:16px;margin:16px 0}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px}.tile .v{font-size:24px;font-weight:600;font-variant-numeric:tabular-nums}.tile .k{color:var(--ink2);font-size:13px}
.note{color:var(--muted);font-size:13px;margin:4px 0 12px}.scroll{overflow-x:auto}
.heat{display:grid;gap:2px;font-size:12px;min-width:max-content}.heat .rl{color:var(--ink2);padding-right:8px;white-space:nowrap;display:flex;align-items:center}
.heat .c{width:22px;height:26px;border-radius:3px;background:var(--empty)}.heat .cl{color:var(--muted);font-size:11px;height:16px;white-space:nowrap}
.legend{display:flex;flex-wrap:wrap;gap:12px;align-items:center;font-size:13px;color:var(--ink2);margin-top:10px}.sw{display:inline-block;width:14px;height:14px;border-radius:3px;vertical-align:-2px;margin-right:4px}
.days button{font:inherit;font-size:13px;border:1px solid var(--axis);background:var(--surface);color:var(--ink);border-radius:999px;padding:4px 12px;margin:0 6px 8px 0;cursor:pointer}
.days button[aria-pressed=true]{background:var(--ink);color:var(--surface);border-color:var(--ink)}
svg text{fill:var(--muted);font-size:11px}svg .lab{fill:var(--ink2);font-size:12px}
table{border-collapse:collapse;width:100%;font-size:13px;font-variant-numeric:tabular-nums}th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--grid)}th{color:var(--ink2);font-weight:500}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);font-size:12px;padding:6px 8px;border-radius:6px;display:none;z-index:9;max-width:260px}
.bar{display:flex;height:22px;border-radius:4px;overflow:hidden;gap:2px;flex:1}.bar span{display:block;height:100%}.brow{display:flex;align-items:center;gap:8px;margin:6px 0;font-size:13px}.brow .n{width:150px;color:var(--ink2);flex:none}.brow .m{width:70px;text-align:right;flex:none;font-variant-numeric:tabular-nums}
</style></head><body><main>
<h1>VD 收集預覽</h1><p class="sub" id="sub"></p>
<div class="tiles" id="tiles"></div>
<section class="card"><h2>哪個時段、哪個入口最慢？</h2>
<p class="note">每格是收到的每一天、同一個 15 分鐘的平均車速；越慢的格子顏色越醒目，對照下方圖例。滑過格子看數字。灰色是沒有資料。</p>
<div class="scroll"><div class="heat" id="heat"></div></div><div class="legend" id="heatLegend"></div></section>
<section class="card"><h2>一天裡車速怎麼變化</h2>
<p class="note">5 個入口每 5 分鐘的車速。虛線是 20 km/h（熱力圖「塞」的門檻）。滑過圖看各入口當下的車速。</p>
<div class="days" id="days"></div><div class="scroll"><svg id="line" role="img" aria-label="各入口車速折線圖"></svg></div><div class="legend" id="lineLegend"></div></section>
<section class="card"><h2>通過的是哪些車？</h2>
<p class="note">收集期間各偵測器累計的車種比例。機車混在一般車道計數，可能有漏數，準確度未驗證。</p>
<div id="comp"></div><div class="legend" id="compLegend"></div></section>
<section class="card"><h2>最新讀數</h2><div class="scroll"><table id="tbl"></table></div></section>
<p class="note">資料來源：臺北市交工處 VDLive.xml，由 data/fetch/collect_vd.py 收集。這是收集期間的預覽，不是正式結果。</p>
</main><div id="tip"></div>
<script>
const D = __DATA__;
const $ = id => document.getElementById(id), tip = $('tip');
const hhmm = m => String(Math.floor(m/60)).padStart(2,'0') + ':' + String(m%60).padStart(2,'0');
const css = v => getComputedStyle(document.documentElement).getPropertyValue(v).trim();
const SER = ['--s1','--s2','--s3','--s4','--s5'];
const show = (e, html) => { tip.innerHTML = html; tip.style.display = 'block';
  const x = Math.min(e.clientX + 14, innerWidth - tip.offsetWidth - 8); tip.style.left = x + 'px'; tip.style.top = (e.clientY + 14) + 'px'; };
const hide = () => tip.style.display = 'none';
const S = D.summary;
$('sub').textContent = `${S.first} 到 ${S.last}，共 ${S.days} 天 · 預覽產生於 ${S.built}`;
$('tiles').innerHTML = [[S.n.toLocaleString(), '筆有效讀數'], [S.days, '天'], [D.order.length, '支偵測器'], [S.skipped, '筆異常讀數已略過']]
  .map(([v,k]) => `<div class="card tile" style="margin:0"><div class="v">${v}</div><div class="k">${k}</div></div>`).join('');

// 熱力圖
const STEPS = [[50,'--q0','50 以上'],[40,'--q1','40–50'],[30,'--q2','30–40'],[20,'--q3','20–30'],[10,'--q4','10–20'],[-1,'--q5','10 以下']];
const step = v => STEPS.find(s => v >= s[0]);
const heat = $('heat');
heat.style.gridTemplateColumns = `auto repeat(${D.bins.length}, 22px)`;
let h = '<div></div>' + D.bins.map(b => `<div class="cl">${b % 60 === 0 ? hhmm(b) : ''}</div>`).join('');
for (const v of D.order) {
  h += `<div class="rl">${D.names[v]}</div>`;
  for (const b of D.bins) {
    const c = D.cells[v + '|' + b];
    h += c ? `<div class="c" style="background:var(${step(c.v)[1]})" data-t="${D.names[v]}｜${hhmm(b)}–${hhmm(b+15)}<br>平均車速 ${c.v} km/h（${c.days} 天）"></div>` : `<div class="c" data-t="${D.names[v]}｜${hhmm(b)}<br>沒有資料"></div>`;
  }
}
heat.innerHTML = h;
heat.addEventListener('mousemove', e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide());
heat.addEventListener('mouseleave', hide);
$('heatLegend').innerHTML = '車速 km/h：' + STEPS.map(s => `<span><i class="sw" style="background:var(${s[1]})"></i>${s[2]}</span>`).join('') + '<span><i class="sw" style="background:var(--empty)"></i>沒有資料</span>';

// 折線圖
const days = Object.keys(D.lines).sort();
let day = days[days.length - 1];
function drawDays(){ $('days').innerHTML = days.map(d => `<button aria-pressed="${d===day}" data-d="${d}">${d.slice(5).replace('-','/')}</button>`).join(''); }
$('days').addEventListener('click', e => { if (e.target.dataset.d) { day = e.target.dataset.d; drawDays(); drawLine(); } });
function drawLine(){
  const svg = $('line'), W = Math.max(640, svg.parentElement.clientWidth), H = 300, L = 40, R = 120, T = 12, B = 28;
  svg.setAttribute('width', W); svg.setAttribute('height', H);
  const ser = D.lines[day] || {}, all = Object.values(ser).flat();
  if (!all.length) { svg.innerHTML = ''; return; }
  const x0 = Math.min(...all.map(p => p[0])), x1 = Math.max(...all.map(p => p[0]), x0 + 60);
  const ymax = Math.max(60, Math.ceil(Math.max(...all.map(p => p[1])) / 20) * 20);
  const X = m => L + (m - x0) / (x1 - x0) * (W - L - R), Y = s => T + (1 - s / ymax) * (H - T - B);
  let g = '';
  for (let s = 0; s <= ymax; s += 20) g += `<line x1="${L}" x2="${W-R}" y1="${Y(s)}" y2="${Y(s)}" stroke="var(--grid)"/><text x="${L-6}" y="${Y(s)+4}" text-anchor="end">${s}</text>`;
  for (let m = Math.ceil(x0/60)*60; m <= x1; m += 60) g += `<text x="${X(m)}" y="${H-8}" text-anchor="middle">${hhmm(m)}</text>`;
  g += `<line x1="${L}" x2="${W-R}" y1="${Y(20)}" y2="${Y(20)}" stroke="var(--muted)" stroke-dasharray="4 4"/>`;
  const ends = [];
  D.main.forEach((v, i) => { const p = ser[v]; if (!p || !p.length) return;
    g += `<polyline fill="none" stroke="var(${SER[i]})" stroke-width="2" stroke-linejoin="round" points="${p.map(q => X(q[0]) + ',' + Y(q[1])).join(' ')}"/>`;
    ends.push([Y(p[p.length-1][1]), D.names[v], i]); });
  ends.sort((a, b) => a[0] - b[0]); for (let k = 1; k < ends.length; k++) ends[k][0] = Math.max(ends[k][0], ends[k-1][0] + 14);
  for (const [y, n] of ends) g += `<text class="lab" x="${W-R+8}" y="${y+4}">${n}</text>`;
  g += `<line id="xh" y1="${T}" y2="${H-B}" stroke="var(--axis)" visibility="hidden"/><rect x="${L}" y="${T}" width="${W-L-R}" height="${H-T-B}" fill="transparent" id="hit"/>`;
  svg.innerHTML = g;
  const hit = svg.querySelector('#hit'), xh = svg.querySelector('#xh');
  hit.addEventListener('mousemove', e => {
    const r = svg.getBoundingClientRect(), m = x0 + (e.clientX - r.left - L) / (W - L - R) * (x1 - x0);
    let html = '', at = null;
    D.main.forEach((v, i) => { const p = ser[v]; if (!p) return; const q = p.reduce((a, b) => Math.abs(b[0]-m) < Math.abs(a[0]-m) ? b : a);
      at = at ?? q[0]; html += `<div><i class="sw" style="background:var(${SER[i]})"></i>${D.names[v]}　${q[1]} km/h</div>`; });
    xh.setAttribute('x1', X(at)); xh.setAttribute('x2', X(at)); xh.setAttribute('visibility', 'visible');
    show(e, `<b>${hhmm(at)}</b>` + html);
  });
  hit.addEventListener('mouseleave', () => { hide(); xh.setAttribute('visibility', 'hidden'); });
}
$('lineLegend').innerHTML = D.main.map((v, i) => `<span><i class="sw" style="background:var(${SER[i]})"></i>${D.names[v]}</span>`).join('');
drawDays(); drawLine(); addEventListener('resize', drawLine);

// 車種組成
$('comp').innerHTML = D.order.map(v => { const c = D.comp[v], tot = Object.values(c).reduce((a, b) => a + b, 0) || 1;
  return `<div class="brow"><span class="n">${D.names[v]}</span><span class="bar">` + D.veh.map(([k, n], i) => c[k] ? `<span style="width:${c[k]/tot*100}%;background:var(${SER[i]})" data-t="${D.names[v]}｜${n} ${c[k].toLocaleString()} 輛（${(c[k]/tot*100).toFixed(1)}%）"></span>` : '').join('') +
  `</span><span class="m">機車 ${(c.vol_M/tot*100).toFixed(0)}%</span></div>`; }).join('');
$('comp').addEventListener('mousemove', e => e.target.dataset.t ? show(e, e.target.dataset.t) : hide());
$('comp').addEventListener('mouseleave', hide);
$('compLegend').innerHTML = D.veh.map(([, n], i) => `<span><i class="sw" style="background:var(${SER[i]})"></i>${n}</span>`).join('');

// 表格
$('tbl').innerHTML = '<tr><th>偵測器</th><th>編號</th><th>時間</th><th>車速 km/h</th>' + D.veh.map(([, n]) => `<th>${n}</th>`).join('') + '</tr>' +
  D.table.map(r => `<tr><td>${r.name}</td><td>${r.vdid}</td><td>${r.time}</td><td>${r.speed}</td>` + D.veh.map(([k]) => `<td>${r.cars[k]}</td>`).join('') + '</tr>').join('');
</script></body></html>
"""


def main(argv):
    paths = argv or [DEFAULT_CSV]
    missing = [p for p in paths if not Path(p).exists()]
    if missing:
        print(f"找不到 {', '.join(map(str, missing))}；收集程式至少要成功抓過一次")
        return 1
    rows, skipped = load(paths)
    if not rows:
        print("檔案裡還沒有有效讀數")
        return 1
    data = json.dumps(build(rows, skipped), ensure_ascii=False, default=list)
    OUT.write_text(PAGE.replace("__DATA__", data.replace("</", "<\\/")), encoding="utf-8")
    print(f"wrote {OUT}（{len(rows):,} 筆讀數）。執行 open {OUT.relative_to(ROOT.parent)} 用瀏覽器打開")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
