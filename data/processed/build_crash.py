"""把傷亡事故逐案資料（fetch_accidents.py 篩出的臺北市列）彙整成「路口 × 時段」，車禍題的熱力圖用。做法見 docs/topics/crash.md。

用法：python3 data/processed/build_crash.py                    # 預設讀 data/raw/accident/taipei_*.csv（說明檔會自動略過）
      python3 data/processed/build_crash.py data/raw/accident/taipei_177136_*.csv data/raw/accident/taipei_167905_*.csv
輸出：data/processed/crash_places.csv：每個路口或路段一列，只放 3 件以上的地點（見 docs/topics/README.md「隱私」）
      欄位：id、類型（路口／路段）、名稱、行政區、經緯度、件數、A1、行人、機車、死亡、受傷、平日 07–10 時、
      每 2 小時的件數（h00…h22）、每年的件數（y114…）
接著：把印出來的摘要貼給 Claude，決定熱力圖放哪 20 個路口、行人與機車的分類對不對。

規則
- 一列是一個當事者，同一件事故有好幾列；「事故類別、發生日期、發生時間、發生地點、經度、緯度」都相同的算同一件。
- 發生地點寫成「A路 / B路」的算路口：去掉「臺北市○○區」與結尾的「口」，兩條路名排序後當 id；兩邊相同的
  （例如「安康路 / 安康路」）算那條路的路段。其他（例如「南京東路3段8號前0.0公尺」）算路段，只留路名與段、巷。
- 行人事故：任一當事者的車種（大類別或子類別）含「行人」；機車事故：任一當事者含「機車」。
  這是依欄位名稱猜的，最後印出的「各欄最常見的值」看過之後再調。
- 死亡、受傷：從「死亡受傷人數」抓數字，格式不符就不算，並在摘要裡說抓不到幾件。
"""
import argparse
import csv
import datetime as dt
import json
import math
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
RAW = HERE.parent / "raw" / "accident"
OUT = HERE / "crash_places.csv"
T4 = HERE / "t4-morning.json"  # 有 #4 入口的經緯度，用來數入口附近的事故（角度 B）
MIN_CASES = 3        # 少於 3 件的地點不輸出，畫面上也只顯示「少於 3 件」
NEAR_M = 300         # 入口附近的半徑（公尺），假設值
BINS = [f"h{h:02d}" for h in range(0, 24, 2)]
CASE_KEY = ("事故類別名稱", "發生日期", "發生時間", "發生地點", "經度", "緯度")
PARTY = ("當事者區分-類別-大類別名稱-車種", "當事者區分-類別-子類別名稱-車種")
SHOW = ("事故類別名稱", "事故類型及型態大類別名稱", "事故類型及型態子類別名稱", "道路型態大類別名稱",
        "事故位置大類別名稱", "號誌-號誌種類名稱", "光線名稱", "天候名稱")
CITY = re.compile(r"^(?:臺北市|台北市)(\S{1,3}?區)?")


def strip_city(s):
    s = s.strip()
    m = CITY.match(s)
    return (m.group(1) or "" if m else ""), s[m.end():].strip() if m else s


def place_of(text):
    """回傳 (id, 類型, 名稱, 行政區)。"""
    parts = [p for p in re.split(r"\s*/\s*", text.strip()) if p]
    district = strip_city(parts[0])[0] if parts else ""
    if len(parts) == 2:
        roads = sorted({strip_city(p)[1].removesuffix("口") for p in parts})
        if len(roads) == 2:
            return "|".join(roads), "路口", " / ".join(roads), district
        text = roads[0]
    road = strip_city(text)[1]
    road = re.sub(r"(\d+號.*|前[\d.]+公尺.*|附近.*)$", "", road).removesuffix("口") or road
    return road, "路段", road, district


def casualties(s):
    """「死亡受傷人數」的格式還沒看過，先抓「死亡 N」「受傷 N」，只寫一個時另一個當 0；都抓不到回傳 None。"""
    d, i = re.search(r"死亡\D*(\d+)", s or ""), re.search(r"受傷\D*(\d+)", s or "")
    return (int(d.group(1)) if d else 0, int(i.group(1)) if i else 0) if d or i else None


def counts(c):
    """把 Counter 的前幾名排成「值 件數、值 件數」。"""
    return "、".join(f"{v or '（空）'} {n:,}" for v, n in c)


def meters(a, b):
    """兩個 (緯度, 經度) 的距離（公尺），haversine。"""
    la1, lo1, la2, lo2 = map(math.radians, (*a, *b))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371000 * math.asin(math.sqrt(h))


def read_cases(paths):
    cases, parties, used = {}, Counter(), []
    for path in paths:
        with open(path, encoding="utf-8", newline="") as f:
            rows = csv.DictReader(f)
            if "發生地點" not in (rows.fieldnames or []):
                continue  # zip 裡的說明檔（manifest、schema），不是事故資料
            used.append(path)
            for r in rows:
                key = tuple(r.get(k, "") for k in CASE_KEY)
                c = cases.get(key)
                if c is None:
                    c = cases[key] = {"row": r, "kinds": set()}
                for k in PARTY:
                    v = r.get(k, "")
                    parties[(k, v)] += 1
                    c["kinds"].add(v)
    return cases, parties, used


def entrances():
    """#4 的入口與經緯度（從 t4-morning.json 讀，沒有就略過角度 B 的統計）。"""
    try:
        rows = json.loads(T4.read_text(encoding="utf-8"))["heatmap"]["rows"]
    except (OSError, KeyError, ValueError):
        return []
    return [(r["name"], (r["lat"], r["lng"])) for r in rows if "lat" in r and "lng" in r]


def main(argv):
    ap = argparse.ArgumentParser(description="把傷亡事故逐案資料彙整成路口 × 時段")
    ap.add_argument("csv", nargs="*", type=Path)
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    paths = args.csv or sorted(RAW.glob("taipei_*.csv"))
    cases, parties, used = read_cases(paths)
    if not cases:
        print(f"沒有讀到事故資料：先跑 python3 data/fetch/fetch_accidents.py（找的是 {RAW}/taipei_*.csv）")
        return 1

    places = defaultdict(lambda: dict(cases=0, a1=0, ped=0, moto=0, killed=0, injured=0, peak=0,
                                      bins=Counter(), years=Counter(), lat=[], lng=[]))
    meta, by_kind, no_cas, no_time, years, peak_cases = {}, Counter(), 0, 0, Counter(), []
    for c in cases.values():
        r = c["row"]
        pid, kind, name, district = place_of(r.get("發生地點", ""))
        p = places[pid]
        meta.setdefault(pid, (kind, name, district))
        by_kind[kind] += 1
        p["cases"] += 1
        p["a1"] += "A1" in r.get("事故類別名稱", "")
        p["ped"] += any("行人" in k for k in c["kinds"])
        p["moto"] += any("機車" in k for k in c["kinds"])
        cas = casualties(r.get("死亡受傷人數"))
        if cas:
            p["killed"] += cas[0]
            p["injured"] += cas[1]
        else:
            no_cas += 1
        t = (r.get("發生時間") or "0").zfill(6)
        no_time += t == "000000"
        hour = int(t[:2]) % 24
        p["bins"][BINS[hour // 2]] += 1
        y = r.get("發生年度", "")
        p["years"][y] += 1
        years[y] += 1
        try:
            day = dt.datetime.strptime(r.get("發生日期", ""), "%Y%m%d")
            weekday_peak = day.weekday() < 5 and 7 <= hour < 10
        except ValueError:
            weekday_peak = False
        p["peak"] += weekday_peak
        try:
            lat, lng = float(r["緯度"]), float(r["經度"])
            p["lat"].append(lat)
            p["lng"].append(lng)
            if weekday_peak:
                peak_cases.append((lat, lng))
        except (KeyError, ValueError):
            pass

    ys = sorted(y for y in years if y)
    fields = ["id", "類型", "名稱", "行政區", "緯度", "經度", "件數", "A1", "行人", "機車", "死亡", "受傷",
              "平日07-10時", *BINS, *[f"y{y}" for y in ys]]
    ranked = sorted(places, key=lambda k: -places[k]["cases"])
    kept = 0
    with open(args.out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(fields)
        for pid in ranked:
            p = places[pid]
            if p["cases"] < MIN_CASES:
                continue
            kept += 1
            kind, name, district = meta[pid]
            lat = round(sum(p["lat"]) / len(p["lat"]), 6) if p["lat"] else ""
            lng = round(sum(p["lng"]) / len(p["lng"]), 6) if p["lng"] else ""
            w.writerow([pid, kind, name, district, lat, lng, p["cases"], p["a1"], p["ped"], p["moto"],
                        p["killed"], p["injured"], p["peak"], *[p["bins"][b] for b in BINS],
                        *[p["years"][y] for y in ys]])

    total = len(cases)
    cross = [k for k in ranked if meta[k][0] == "路口"]
    cross_total = sum(places[k]["cases"] for k in cross)
    print(f"讀了 {len(used)} 個檔，{sum(parties.values()) // len(PARTY):,} 列（當事者）→ {total:,} 件事故")
    print(f"  年度：{', '.join(f'{y} 年 {years[y]:,} 件' for y in ys)}")
    print(f"  A1：{sum(p['a1'] for p in places.values()):,} 件；行人：{sum(p['ped'] for p in places.values()):,} 件；"
          f"機車：{sum(p['moto'] for p in places.values()):,} 件")
    print(f"  路口 {by_kind['路口']:,} 件（{by_kind['路口'] / total:.0%}），{len(cross):,} 個路口；路段 {by_kind['路段']:,} 件")
    if no_cas:
        sample = Counter(c["row"].get("死亡受傷人數", "") for c in cases.values()).most_common(3)
        print(f"  死亡受傷人數有 {no_cas:,} 件格式不符，沒算進去。常見的值：{sample}")
    if no_time:
        print(f"  發生時間是 000000 的有 {no_time:,} 件（{no_time / total:.0%}），可能是時間不明，會灌進 00–02 時那一格")
    for n in (20, 50, 100):
        top = sum(places[k]["cases"] for k in cross[:n])
        print(f"  前 {n} 個路口：{top:,} 件，占全部事故 {top / total:.1%}、路口事故 {top / max(cross_total, 1):.1%}")
    print(f"\n輸出 {args.out}：{kept:,} 個地點（{MIN_CASES} 件以上）")

    print("\n前 20 個路口（件數｜A1｜行人｜機車｜最多的時段）")
    for i, k in enumerate(cross[:20], 1):
        p = places[k]
        b, n = p["bins"].most_common(1)[0]
        print(f"  {i:2d}. {meta[k][2]} {meta[k][1]}：{p['cases']}｜{p['a1']}｜{p['ped']}｜{p['moto']}｜"
              f"{b[1:]}–{int(b[1:]) + 2:02d} 時 {n} 件")

    ents = entrances()
    if ents:
        print(f"\n#4 入口附近 {NEAR_M} 公尺內，平日 07–10 時的事故（角度 B：多久會遇到一次）")
        for name, at in ents:
            n = sum(meters(at, c) <= NEAR_M for c in peak_cases)
            print(f"  {name}：{n} 件（{'、'.join(ys)} 年合計）")

    print("\n各欄最常見的值（確認分類規則用）")
    for k in PARTY:
        print(f"  {k}：{counts(Counter({v: n for (kk, v), n in parties.items() if kk == k}).most_common(8))}")
    for k in SHOW:
        print(f"  {k}：{counts(Counter(c['row'].get(k, '') for c in cases.values()).most_common(6))}")
    road_type = Counter(f"{place_of(c['row'].get('發生地點', ''))[1]}×{c['row'].get('道路型態大類別名稱', '') or '（空）'}"
                        for c in cases.values())
    print(f"  路口／路段 × 道路型態大類別（對照用）：{counts(road_type.most_common(6))}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
