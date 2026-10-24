"""收集結束後一次彙整：合併所有 VD 讀數，產生涵蓋摘要、熱力圖格子、排隊模型輸入、正式資料檔、Demo 台詞檢查與探索圖表。

用法：python3 data/processed/build_all.py [更多 vd_taipei_targets.csv ...]

自動找的讀數（重複的只留一筆）
- 自己電腦：data/raw/vd_taipei_targets.csv
- GitHub Actions 下載的：~/Downloads/vd-raw-*（還沒解壓縮的 .zip 會先解壓縮到同名資料夾）、data/raw/actions/
- TDX 歷史資料：data/raw/tdx_vd_hist/vd_tdx_targets.csv（data/fetch/fetch_tdx_vd_hist.py 產生）。
  TDX 是完整的官方紀錄，某支偵測器某一天有 TDX 資料時，就不用自己收的那天（兩邊的 5 分鐘切法不同，混用會重複算）

車數的單位：VDLive.xml 的車數是「最近 1 分鐘」的車數，自己收的是每 5 分鐘抓一次，所以每筆只有 5 分鐘裡的 1 分鐘。
TDX 是每分鐘都有，彙整成 5 分鐘的車數。合併時把自己收的車數 ×5，估成 5 分鐘的車數，兩邊單位才一致
（10/20 08:00–10:00 同一支偵測器比對，TDX 每筆平均是自己收的 5.0 倍，車速兩邊相同）。

輸出
- data/processed/vd_readings.csv   全部讀數合併、去重、依時間排序（臺北市公開資料，可以進 git 給隊友用）
- data/processed/COLLECTION.md     每天收到哪些時段、各偵測器幾筆、資料來自哪些檔案
- data/processed/vd_15min.json、model_input.json、t4-morning.json（真實資料版）
- data/raw/explore.html            探索圖表（含路況地圖），用瀏覽器打開
"""
import csv
import datetime as dt
import subprocess
import sys
import zipfile
from collections import defaultdict
from pathlib import Path

from calendar_tw import HOLIDAYS, is_workday
from preview_vd import SKIP_DAYS

HERE = Path(__file__).resolve().parent
DATA = HERE.parent
REPO = DATA.parent
OUT = HERE / "vd_readings.csv"
SUMMARY = HERE / "COLLECTION.md"
TDX = DATA / "raw" / "tdx_vd_hist" / "vd_tdx_targets.csv"
LIVE_SCALE = 5  # 自己收的每筆是 1 分鐘車數 → ×5 估成 5 分鐘車數
FIELDS = ['poll_time', 'entrance', 'vdid', 'link_id', 'status', 'collect_time',
          'lanes', 'vol_M', 'vol_S', 'vol_L', 'vol_T', 'speed', 'occupancy']
AM, PM = (7 * 60, 10 * 60 + 30), (16 * 60 + 30, 20 * 60 + 30)
WEEK = "一二三四五六日"


def sources(extra):
    downloads = Path.home() / "Downloads"
    for z in sorted(downloads.glob("vd-raw-*.zip")):
        target = downloads / z.stem
        if not target.exists():
            with zipfile.ZipFile(z) as f:
                f.extractall(target)
            print(f"解壓縮 {z.name} → {target}")
    found = [TDX, DATA / "raw" / "vd_taipei_targets.csv"]
    for base in (downloads, DATA / "raw" / "actions"):
        if base.exists():
            found += sorted(p for d in base.glob("vd-raw-*") if d.is_dir() for p in d.rglob("vd_taipei_targets.csv"))
    found += [Path(p) for p in extra]
    seen, out = set(), []
    for p in found:
        if p.exists() and p.resolve() not in seen:
            seen.add(p.resolve())
            out.append(p)
    return out


def merge(paths):
    rows, keys, contrib = [], set(), {}
    # TDX 某支偵測器某天有 2/3 以上的 5 分鐘（288 格的 192 格）才算涵蓋那天；頭尾那天常只有一部分，自己收的要留著
    per_day = defaultdict(int)
    if TDX in paths:
        with open(TDX, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                per_day[(r["vdid"], r["collect_time"][:10])] += 1
    tdx_days = {k for k, n in per_day.items() if n >= 192}
    for p in paths:
        n, is_tdx = 0, p.resolve() == TDX.resolve()
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                k = (r["vdid"], r["link_id"], r["collect_time"])
                if not is_tdx and (r["vdid"], r["collect_time"][:10]) in tdx_days:
                    continue
                if k in keys:
                    continue
                keys.add(k)
                row = {f: r.get(f, "") for f in FIELDS}
                if not is_tdx:
                    for c in ("vol_M", "vol_S", "vol_L", "vol_T"):
                        row[c] = int(row[c] or 0) * LIVE_SCALE
                rows.append(row)
                n += 1
        contrib[p] = n
    rows.sort(key=lambda r: (r["collect_time"], r["vdid"], r["link_id"]))
    with open(OUT, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)
    return rows, contrib


def summary(rows, contrib):
    names = {}
    per_day = defaultdict(lambda: defaultdict(set))  # 日期 → vdid → {分鐘（取到 5 分鐘）}
    for r in rows:
        if r["status"] != "0" or r["speed"] == "":
            continue
        t = dt.datetime.fromisoformat(r["collect_time"])
        m = t.hour * 60 + t.minute
        per_day[t.date()][r["vdid"]].add(m - m % 5)
        names[r["vdid"]] = r["entrance"]
    main = ["VTXQJ20", "VPMSV40", "VQBUL20", "VMLXB00", "V6310G0"]

    def cover(day, lo, hi):
        need = len(main) * (hi - lo) // 5
        got = sum(1 for v in main for m in per_day[day].get(v, ()) if lo <= m < hi)
        return round(got / need * 100)

    lines = ["# VD 收集紀錄", "",
             f"{dt.datetime.now():%b %d, %Y %H:%M} 由 `data/processed/build_all.py` 產生，資料在 [`vd_readings.csv`](vd_readings.csv)。", "",
             "臺北市交工處 VDLive.xml（自己收）與 TDX 歷史資料，每 5 分鐘一筆；自己收的車數是 1 分鐘的車數，已 ×5 估成 5 分鐘。收完整＝5 個入口的讀數到齊 80% 以上。", "",
             "## 每天收到哪些時段", "",
             "| 日期 | 早上 07:00–10:30 | 傍晚 16:30–20:30 | 有資料的時間 | 讀數 |", "| --- | --- | --- | --- | --- |"]
    full_am, full_pm = [], []
    for day in sorted(per_day):
        a, b = cover(day, *AM), cover(day, *PM)
        mins = sorted({m for v in per_day[day].values() for m in v})
        span = f"{mins[0] // 60:02d}:{mins[0] % 60:02d}–{(mins[-1] + 5) // 60:02d}:{(mins[-1] + 5) % 60:02d}" if mins else "—"
        n = sum(len(v) for v in per_day[day].values())
        mark = lambda c: f"{'✅' if c >= 80 else '⚠️' if c else '—'} {c}%"
        # 兩個條件都要過：is_workday 排除週末與國定假日，SKIP_DAYS 排除颱風假
        skip = SKIP_DAYS.get(day.isoformat())
        off = HOLIDAYS.get(day, "")
        note = ("，" + off if off else "") + (f"・{skip}，不算" if skip else "")
        lines.append(f"| {day:%m/%d}（{WEEK[day.weekday()]}{note}） | {mark(a)} | {mark(b)} | {span} | {n:,} |")
        if a >= 80 and is_workday(day) and not skip:
            full_am.append(f"{day:%m/%d}")
        if b >= 80 and is_workday(day) and not skip:
            full_pm.append(f"{day:%m/%d}")
    skipped = "、".join(f"{d[5:].replace('-', '/')}（{why}）" for d, why in SKIP_DAYS.items())
    lines += ["", f"**上班日早上收完整：{len(full_am)} 天**（{'、'.join(full_am) or '無'}）；"
                  f"**上班日傍晚收完整：{len(full_pm)} 天**（{'、'.join(full_pm) or '無'}）。"
                  + (f"另外不算的日子：{skipped}。" if skipped else ""), "",
              "熱力圖、排隊模型與探索圖表，每個入口只用往內湖方向的路段（`entrances_detail.csv` 的 LinkID）。", "",
              "## 各偵測器的讀數", "", "| 偵測器 | 名稱 | 筆數 |", "| --- | --- | --- |"]
    for v in sorted(names, key=lambda v: (v not in main, main.index(v) if v in main else 0, v)):
        lines.append(f"| {v} | {names[v]} | {sum(len(per_day[d].get(v, ())) for d in per_day):,} |")
    lines += ["", "## 資料來源檔案", "", "| 檔案 | 新增的讀數 |", "| --- | --- |"]
    for p, n in contrib.items():
        shown = str(p.resolve()).replace(str(REPO) + "/", "").replace(str(Path.home()), "~")
        lines.append(f"| `{shown}` | {n:,} |")
    lines += ["", "同一支偵測器、同一個時間的讀數只留一筆，所以後面的檔案和前面重疊的部分不會重複算。", ""]
    SUMMARY.write_text("\n".join(lines), encoding="utf-8")
    return full_am, full_pm


def run(title, *args):
    print(f"\n== {title}")
    r = subprocess.run([sys.executable, *map(str, args)], cwd=REPO)
    if r.returncode:
        print(f"（{title} 沒有成功，結束碼 {r.returncode}；其他步驟繼續）")
    return r.returncode == 0


def main(argv):
    paths = sources(argv)
    if not paths:
        print("找不到任何 vd_taipei_targets.csv：確認 data/raw/ 或 ~/Downloads/vd-raw-* 裡有資料")
        return 1
    rows, contrib = merge(paths)
    am, pm = summary(rows, contrib)
    print(f"合併 {len(paths)} 個檔案，共 {len(rows):,} 筆讀數 → {OUT.relative_to(REPO)}")
    print(f"上班日早上收完整 {len(am)} 天（{'、'.join(am) or '無'}），傍晚 {len(pm)} 天（{'、'.join(pm) or '無'}）；細節見 {SUMMARY.relative_to(REPO)}")
    run("熱力圖格子", HERE / "build_vd_15min.py", OUT)
    ok = run("排隊模型輸入（容量與到達曲線）", HERE / "build_model_input.py", OUT)
    model = ["--model", HERE / "model_input.json"] if ok else []
    if run("正式資料檔 t4-morning（真實資料版）", DATA / "mock" / "gen_t4_morning.py", "--real", HERE / "vd_15min.json", *model):
        run("資料契約驗證", DATA / "schema" / "validate.py", HERE / "t4-morning.json")
        run("Demo 台詞檢查", HERE / "check_demo.py", HERE / "t4-morning.json")
    run("探索圖表（含路況地圖）", HERE / "explore_vd.py", OUT)
    print(f"\n完成。打開 data/raw/explore.html 看圖表；要給隊友用，把 data/processed/ 的變更 commit 並 push。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
