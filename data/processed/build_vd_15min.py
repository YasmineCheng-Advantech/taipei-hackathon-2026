"""把收集程式的 VD 讀數彙整成熱力圖要的 15 分鐘格子。

用法：python3 data/processed/build_vd_15min.py data/raw/vd_taipei_targets.csv [更多 csv]
      預設只取平日 07:00–10:30（#4 晨峰）；全天收集的資料可以改時段，例如晚尖峰：
      python3 data/processed/build_vd_15min.py --start 17:00 --end 19:30 --out data/processed/vd_15min_evening.json data/raw/*.csv
      電腦與 GitHub Actions 收到的 csv 可以一起傳入，重複的讀數會自動去掉。
輸出：data/processed/vd_15min.json（每支偵測器 × 每個 15 分鐘：多天的平均、最小、最大、天數、塞的天數）
接著：python3 data/mock/gen_t4_morning.py --real data/processed/vd_15min.json

規則
- 只用 status = 0（正常）且有車速的讀數；同一支偵測器同一個 DataCollectTime 只算一次（收集程式可能抓到同一筆）。
- 同一支偵測器常同時回報兩個方向：入口只用往內湖的路段（entrances_detail.csv 的 LinkID，見 preview_vd.keep）。
- preview_vd.SKIP_DAYS 列的日子（颱風假）不算，記在輸出的 skipped_days。
- 每筆讀數是 5 分鐘的車數（build_all.py 合併時已把自己收的 1 分鐘車數 ×5），依 DataCollectTime 落在哪個 15 分鐘格。
- 一格的流量 = 該格各筆的車輛數加總；不滿 3 筆時按比例補成 15 分鐘，並記在 samples。
- 一格的車速 = 各筆車速依車輛數加權平均。
- 多天彙整：平均（v）、最小（lo）、最大（hi）、天數（days）；車速另記低於 BAD_SPEED 的天數（bad_days）。
"""
import argparse
import csv
import datetime as dt
import json
import sys
from collections import defaultdict
from pathlib import Path

from preview_vd import SKIP_DAYS, inbound_links, keep

OUT = Path(__file__).with_name("vd_15min.json")
BAD_SPEED = 20  # 與 gen_t4_morning.py 的 BAD_SPEED 相同
START, END = dt.time(7, 0), dt.time(10, 30)


def bin_of(t):
    m = t.hour * 60 + t.minute
    m -= m % 15
    return f"{m // 60:02d}:{m % 60:02d}"


def summarize(values, bad=None):
    o = dict(v=round(sum(values) / len(values)), lo=round(min(values)), hi=round(max(values)), days=len(values))
    if bad is not None:
        o["bad_days"] = sum(bad(x) for x in values)
    return o


def main(argv):
    ap = argparse.ArgumentParser(description="把 VD 讀數彙整成 15 分鐘格子")
    ap.add_argument("csv", nargs="*")
    ap.add_argument("--start", type=dt.time.fromisoformat, default=START)
    ap.add_argument("--end", type=dt.time.fromisoformat, default=END)
    ap.add_argument("--weekends", action="store_true", help="也納入週末（預設只取平日）")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    paths = args.csv
    if not paths:
        print(__doc__.strip())
        return 2
    seen, entrance = set(), {}
    links = inbound_links()
    # (vdid, 日期, 格) -> [(車速, 車輛數)]
    reads = defaultdict(list)
    skipped = 0
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if not keep(r, links) or r["collect_time"][:10] in SKIP_DAYS:
                    continue
                key = (r["vdid"], r["collect_time"])
                if key in seen:
                    continue
                seen.add(key)
                if r["status"] != "0" or r["speed"] == "":
                    skipped += 1
                    continue
                t = dt.datetime.fromisoformat(r["collect_time"])
                if not (args.start <= t.time() < args.end) or (t.weekday() >= 5 and not args.weekends):
                    continue
                n = sum(int(r[k] or 0) for k in ("vol_M", "vol_S", "vol_L", "vol_T"))
                reads[(r["vdid"], t.date().isoformat(), bin_of(t))].append((float(r["speed"]), n))
                entrance[r["vdid"]] = r["entrance"]

    # 每天每格先算一個值，再跨天彙整
    per_bin = defaultdict(lambda: {"speed": [], "flow": [], "samples": []})
    days = set()
    for (vid, day, b), rs in reads.items():
        cars = sum(n for _, n in rs)
        speed = sum(s * n for s, n in rs) / cars if cars else sum(s for s, _ in rs) / len(rs)
        x = per_bin[(vid, b)]
        x["speed"].append(speed)
        x["flow"].append(cars * 3 / min(len(rs), 3))
        x["samples"].append(len(rs))
        days.add(day)

    detectors = defaultdict(lambda: {"cells": {}})
    for (vid, b), x in sorted(per_bin.items()):
        detectors[vid]["entrance"] = entrance[vid]
        detectors[vid]["cells"][b] = {
            "speed": summarize(x["speed"], lambda s: s < BAD_SPEED),
            "flow": summarize(x["flow"]),
            "samples": min(x["samples"]),
        }
    doc = {
        "source": "臺北市交工處 VDLive.xml，經 data/fetch/collect_vd.py 收集",
        "built_at": dt.datetime.now(dt.timezone(dt.timedelta(hours=8))).isoformat(timespec="seconds"),
        "window": f"{'每天' if args.weekends else '平日'} {args.start:%H:%M}–{args.end:%H:%M}",
        "days": sorted(days),
        "skipped_days": SKIP_DAYS,
        "bad_speed": BAD_SPEED,
        "skipped_reads": skipped,
        "detectors": detectors,
    }
    args.out.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.out}：{len(detectors)} 支偵測器、{len(days)} 天（{', '.join(sorted(days))}），略過 {skipped} 筆異常讀數；"
          f"不算的日子：{'、'.join(f'{d}（{why}）' for d, why in SKIP_DAYS.items()) or '無'}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
