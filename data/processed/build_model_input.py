"""產生排隊模型的輸入 model_input.json：堤頂大道北向（VPMSV40）的容量，與 07:00–10:30 每 15 分鐘的到達曲線。

用法
  python3 data/processed/build_model_input.py data/raw/vd_taipei_targets.csv [更多 csv]  # 真實 VD → data/processed/model_input.json
  python3 data/processed/build_model_input.py --mock                                   # 目前的假設 → data/mock/inputs/model_input.json
  電腦與 GitHub Actions 收到的 csv 可以一起傳入，重複的讀數會自動去掉。
接著
  python3 data/mock/gen_t4_morning.py --real data/processed/vd_15min.json --model data/processed/model_input.json
  情境、城市目標、一頁紙的結論與做法比較、敏感度分析都會改用這份容量與到達曲線重算。

方法（只算汽車：小客車＋大車＋聯結車。機車混在一般車道常漏數，排隊模型以汽車計）
- 每天每 15 分鐘：汽車數加總（讀數少於 2 筆的格子不用，缺 1 筆時按比例補成 15 分鐘）；車速依車輛數加權。
- 塞住：車速低於這支偵測器的塞車線＝平常車速（車少時讀數的第 85 百分位）的 40%，也就是服務水準 E 級以下，
  和 explore_vd.py 相同（出處見該檔說明）。不用固定的 20 km/h：路段中間的偵測器在塞車時車速常常不會低於 20。
  --jam 可以指定固定值。
- 容量：塞住的格子裡，偵測器數到的是排隊實際放行的速度，所以取這些格子汽車數的中位數；上下限取四分位數。
  收集期間都沒塞住時，只知道容量至少是最大的 15 分鐘汽車數，改標「情境假設」並警告。
- 到達曲線：塞住時偵測器只數得到放行的車，數不到還在排隊的車，所以不能直接拿流量當到達。
  改成找一條鐘形曲線（離峰量 + 尖峰高度 × 鐘形），丟進同一個排隊模型後，跑出來的「每格放行車數」和「哪幾格塞住」
  最接近 VD 實測。塞住那一段的形狀資料看不出來（高而窄、低而寬都可能讓排隊在同一時間消散），
  所以寬度只在分不出來時偏向 2015 年調查推出的 1.8 格。全部天數一起找出主曲線；每天各找一次，作為每格的上下限。
- 尖峰時段：主曲線最高的連續 4 格（1 小時），情境就是把這 4 格的車移到其他時段。
"""
import argparse
import datetime as dt
import json
import math
import sys
from collections import defaultdict
from pathlib import Path

from explore_vd import threshold
from preview_vd import load

HERE = Path(__file__).resolve().parent
OUT_REAL = HERE / "model_input.json"
OUT_MOCK = HERE.parent / "mock" / "inputs" / "model_input.json"

VD, PLACE = "VPMSV40", "堤頂大道北向"
CARS = ("vol_S", "vol_L", "vol_T")
JAM = None  # 塞車線（km/h），build_real 依資料設定：預設是平常車速的 40%（E 級以下），或 --jam 指定的固定值
MIN_READS = 2
MIN_JAM = 3  # 塞住的格子少於這麼多，就不從資料估容量
TIMES = [f"{(7 * 60 + 15 * i) // 60:02d}:{(7 * 60 + 15 * i) % 60:02d}" for i in range(14)]  # 07:00–10:15
PEAK_LEN = 4
PEAK_START = (4, 8)  # 尖峰窗起點的範圍：前面要留提早的 2 格、後面要留延後的 2 格

# 寬度分不出來時偏向的值，以及這個偏好有多弱（只在誤差幾乎一樣時起作用）
PRIOR_WIDTH, PRIOR_WEIGHT = 1.8, 0.002
JAM_WEIGHT = 0.02  # 一格「塞／不塞」對不上，等於放行車數差了約 14% 容量

# 目前的假設，與 data/mock/gen_t4_morning.py 原本寫死的數字相同
MOCK_CAP, MOCK_BASE, MOCK_AMP, MOCK_PEAK, MOCK_WIDTH = 1000, 500, 780, 7, 1.8


def g(t, p, w):
    return math.exp(-((t - p) ** 2) / (2 * w * w))


def arrivals(base, amp, peak, width):
    return [max(0, round(base + amp * g(t, peak, width))) for t in range(len(TIMES))]


def run(arr, cap):
    """排隊模型：回傳每格放行車數，與每格瓶頸是否滿載（塞住）。"""
    q, dep, jam = 0.0, [], []
    for a in arr:
        jam.append(q + a > cap)
        nq = max(0.0, q + a - cap)
        dep.append(q + a - nq)
        q = nq
    return dep, jam


def pct(xs, p):
    xs = sorted(xs)
    k = (len(xs) - 1) * p
    lo, hi = math.floor(k), math.ceil(k)
    return xs[lo] + (xs[hi] - xs[lo]) * (k - lo)


def read_bins(paths):
    """回傳 ({日期: {格: (汽車數/15 分鐘, 車速)}}, 略過的讀數, 這支偵測器全部讀數的 (車速, 車輛數))；格子只取平日 07:00–10:30。"""
    rows, skipped = load(paths)
    reads = defaultdict(list)
    speeds = [(r["speed"], sum(r["cars"].values())) for r in rows if r["vdid"] == VD]
    for r in rows:
        t = r["t"]
        if r["vdid"] != VD or t.weekday() >= 5:
            continue
        i = (t.hour * 60 + t.minute - 7 * 60) // 15
        if 0 <= i < len(TIMES):
            reads[(t.date().isoformat(), i)].append(r)
    days = defaultdict(dict)
    for (d, i), rs in reads.items():
        if len(rs) < MIN_READS:
            continue
        cars = sum(r["cars"][k] for r in rs for k in CARS)
        n = sum(sum(r["cars"].values()) for r in rs)
        speed = sum(r["speed"] * sum(r["cars"].values()) for r in rs) / n if n else sum(r["speed"] for r in rs) / len(rs)
        days[d][i] = (cars * 3 / min(len(rs), 3), speed)
    return dict(sorted(days.items())), skipped, speeds


def capacity(days):
    jam = [f for bins in days.values() for f, s in bins.values() if s < JAM]
    free = max((f for bins in days.values() for f, s in bins.values() if s >= JAM), default=0)
    if len(jam) >= MIN_JAM:
        return dict(value=round(pct(jam, 0.5)), lo=round(pct(jam, 0.25)), hi=round(pct(jam, 0.75)),
                    unit="輛/15 分鐘", label="computed", sim=False, src="vd-live", n=len(jam),
                    note=f"塞住（車速低於 {JAM} km/h）的 {len(jam)} 個 15 分鐘，實際放行汽車數的中位數；區間為四分位數",
                    free_max=round(free))
    top = round(max(free, max(jam, default=0)))
    print(f"警告：{VD} 收集期間只有 {len(jam)} 個塞住的 15 分鐘，量不到排隊時的放行速度；容量先用最大的 15 分鐘汽車數 {top}",
          file=sys.stderr)
    return dict(value=top, lo=top, hi=round(top * 1.1), unit="輛/15 分鐘", label="assumed", sim=False, src="vd-live",
                n=len(jam), note=f"收集期間幾乎沒有塞住，只知道容量至少是 {top} 輛；上限先假設多 10%", free_max=round(free))


def loss_of(dep, jam, obs, cap):
    e = 0.0
    for i, (f, s) in obs.items():
        e += ((dep[i] - f) / cap) ** 2 + (JAM_WEIGHT if jam[i] != (s < JAM) else 0)
    return e


def grid(lo, hi, step):
    n = int(round((hi - lo) / step))
    return [lo + step * k for k in range(n + 1)]


def search(days, cap, keys, coarse=True, around=None):
    """在參數格點上找誤差最小的曲線；keys 是要算的對象（每一天，或 'all' 代表全部天數一起）。"""
    if coarse:
        bases = grid(0.1 * cap, 1.2 * cap, 0.05 * cap)
        amps = grid(0, 1.6 * cap, 0.05 * cap)
        peaks, widths = grid(0, 13, 0.5), grid(0.5, 4, 0.5)
    else:
        b0, a0, p0, w0 = around
        bases = [x for x in grid(b0 - 0.05 * cap, b0 + 0.05 * cap, 0.01 * cap) if x >= 0]
        amps = [x for x in grid(a0 - 0.05 * cap, a0 + 0.05 * cap, 0.01 * cap) if x >= 0]
        peaks = grid(p0 - 0.5, p0 + 0.5, 0.1)
        widths = [x for x in grid(w0 - 0.5, w0 + 0.5, 0.1) if x >= 0.3]
    best = {k: (math.inf, None) for k in keys}
    for w in widths:
        prior = PRIOR_WEIGHT * ((w - PRIOR_WIDTH) / PRIOR_WIDTH) ** 2
        for p in peaks:
            shape = [g(t, p, w) for t in range(len(TIMES))]
            for b in bases:
                for a in amps:
                    arr = [max(0.0, b + a * s) for s in shape]
                    dep, jam = run(arr, cap)
                    per = {d: loss_of(dep, jam, obs, cap) for d, obs in days.items()}
                    for k in keys:
                        e = (sum(per.values()) if k == "all" else per[k]) + prior
                        if e < best[k][0]:
                            best[k] = (e, (b, a, p, w))
    return best


def fit(days, cap):
    keys = ["all"] + list(days)
    best = search(days, cap, keys)
    out = {}
    for k in keys:
        sub = days if k == "all" else {k: days[k]}
        out[k] = search(sub, cap, [k], coarse=False, around=best[k][1])[k][1]
    return out


def peak_window(arr):
    starts = range(PEAK_START[0], PEAK_START[1] + 1)
    s = max(starts, key=lambda i: (sum(arr[i:i + PEAK_LEN]), i))  # 一樣大時取較晚的
    best = max(range(len(arr) - PEAK_LEN + 1), key=lambda i: (sum(arr[i:i + PEAK_LEN]), i))
    if best != s:
        print(f"警告：到達最多的 1 小時是 {TIMES[best]} 起，但情境要在前後留時段給人移過去，尖峰窗改用 {TIMES[s]} 起",
              file=sys.stderr)
    return list(range(s, s + PEAK_LEN))


def params(b, a, p, w):
    """曲線參數：base 離峰量、amp 尖峰高度（輛/15 分鐘）、peak 最高點在第幾格（07:00 為 0）、width 寬度（格）。"""
    return dict(base=round(b), amp=round(a), peak=round(p, 2), width=round(w, 2),
                peak_time=f"{(7 * 60 + round(p * 15)) // 60:02d}:{(7 * 60 + round(p * 15)) % 60:02d}")


def curve(p):
    return arrivals(p["base"], p["amp"], p["peak"], p["width"])


def build_real(paths, jam=None):
    global JAM
    days, skipped, speeds = read_bins(paths)
    if not days:
        sys.exit(f"沒有 {VD} 在平日 07:00–10:30 的讀數，請確認 csv 路徑")
    free_speed, line = threshold(speeds)
    JAM = jam or line
    jam_why = "指定的固定值" if jam else f"平常車速 {free_speed} km/h（{len(speeds):,} 筆讀數中車少時的第 85 百分位）的 40%，服務水準 E 級以下"
    print(f"{VD} 的塞車線：{JAM} km/h（{jam_why}）")
    cap = capacity(days)
    fits = {k: params(*f) for k, f in fit(days, cap["value"]).items()}
    main = fits.pop("all")
    arr = curve(main)
    each = {d: curve(f) for d, f in fits.items()}
    dep, jam = run(arr, cap["value"])
    n_bins = sum(len(b) for b in days.values())
    match = sum(jam[i] == (s < JAM) for b in days.values() for i, (_, s) in b.items())
    rmse = math.sqrt(sum((dep[i] - f) ** 2 for b in days.values() for i, (f, _) in b.items()) / n_bins)
    obs_flow = [sorted(b[i][0] for b in days.values() if i in b) for i in range(len(TIMES))]
    win = peak_window(arr)
    doc = dict(
        version="1.0", place=PLACE, detector=VD, src="vd-live", sim=False,
        built_at=dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        days=list(days), bin_minutes=15, cols=TIMES,
        unit="輛/15 分鐘（汽車：小客車＋大車＋聯結車，不含機車）",
        jam_line=dict(value=JAM, free_speed=free_speed, unit="km/h", note=f"車速低於這個值算塞住：{jam_why}"),
        capacity=cap,
        arrival=dict(
            values=arr,
            lo=[min(v[i] for v in each.values()) for i in range(len(TIMES))],
            hi=[max(v[i] for v in each.values()) for i in range(len(TIMES))],
            label="computed", sim=False, src="vd-live", fit=main,
            note="排隊模型反推：這條曲線丟進排隊模型後，放行車數與塞住的時段最接近 VD 實測；lo／hi 是每天各自反推的範圍"),
        peak_window=dict(cols=[TIMES[i] for i in win], note="主曲線到達最多的連續 1 小時；情境把這段的車移到其他時段"),
        observed=dict(
            flow=[round(pct(x, 0.5)) if x else None for x in obs_flow],
            jam_days=[sum(1 for b in days.values() if i in b and b[i][1] < JAM) for i in range(len(TIMES))],
            days=[sum(1 for b in days.values() if i in b) for i in range(len(TIMES))],
            note=f"VD 實測：每格汽車數的中位數、車速低於 {JAM} km/h 的天數、有資料的天數"),
        fit_quality=dict(rmse=round(rmse), jam_match=f"{match}/{n_bins}",
                         note="主曲線跑出的放行車數與實測差多少（均方根，輛/15 分鐘），以及塞／不塞對上的格數"),
        per_day=[dict(day=d, fit=f, jam=[TIMES[i] for i, (_, s) in sorted(days[d].items()) if s < JAM])
                 for d, f in fits.items()],
        skipped_reads=skipped,
        assumptions=[
            "瓶頸只有一個：堤頂大道北向，以 VPMSV40（民權東路–舊宗路）代表；下游 VRPSV00、VRHT600 未納入。",
            f"塞住＝車速低於 {JAM} km/h（{jam_why}）；塞住時偵測器數到的就是瓶頸的放行速度。",
            "到達曲線是一條鐘形曲線；塞住那段的形狀資料看不出來，寬度分不出來時偏向 2015 年調查推出的 1.8 格。",
            "只算汽車，不含機車；排隊模型的結果只適合解讀汽車。",
            f"資料只有 {len(days)} 個平日早上，不代表長期的平常日。",
        ],
    )
    return doc


def build_mock():
    p = params(MOCK_BASE, MOCK_AMP, MOCK_PEAK, MOCK_WIDTH)
    arr = curve(p)
    return dict(
        version="1.0", place=PLACE, detector=VD, src="mock", sim=True,
        built_at="2026-10-19T12:00:00+08:00", days=[], bin_minutes=15, cols=TIMES,
        unit="輛/15 分鐘",
        capacity=dict(value=MOCK_CAP, lo=round(MOCK_CAP * 0.9), hi=round(MOCK_CAP * 1.1), unit="輛/15 分鐘",
                      label="assumed", sim=True, src="mock", note="假設值，上下限 ±10%；收集到真實資料後由塞住時的放行車數估計"),
        arrival=dict(values=arr, lo=arr, hi=arr, label="assumed", sim=True, src="mock", fit=p,
                     note="容量 × (0.5 + 0.78 × 鐘形曲線)，最高點在 08:45；形狀依交通局 2015 年「82% 集中在 9 時」"),
        peak_window=dict(cols=TIMES[6:10], note="依交通局 2015 年調查的壅塞時段 8:30–9:30"),
        assumptions=["全部是假設值，與 data/mock/gen_t4_morning.py 原本寫死的數字相同。"],
    )


def main(argv):
    ap = argparse.ArgumentParser(description="產生排隊模型的輸入 model_input.json")
    ap.add_argument("csv", nargs="*", help="收集程式的 vd_taipei_targets.csv")
    ap.add_argument("--mock", action="store_true", help="不讀資料，輸出目前的假設值")
    ap.add_argument("--jam", type=float, help="塞車線改用固定值（km/h），預設是平常車速的 40%")
    ap.add_argument("--out", type=Path)
    args = ap.parse_args(argv)
    if not args.mock and not args.csv:
        print(__doc__.strip())
        return 2
    doc = build_mock() if args.mock else build_real(args.csv, args.jam)
    out = args.out or (OUT_MOCK if args.mock else OUT_REAL)
    out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    c, a = doc["capacity"], doc["arrival"]
    print(f"wrote {out}：容量 {c['value']}（{c['lo']}–{c['hi']}）輛/15 分鐘，到達最高 {max(a['values'])}，"
          f"尖峰 {doc['peak_window']['cols'][0]}–{doc['peak_window']['cols'][-1]}"
          + (f"，{len(doc['days'])} 天，誤差 {doc['fit_quality']['rmse']} 輛、塞／不塞對上 {doc['fit_quality']['jam_match']} 格"
             if not args.mock else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
