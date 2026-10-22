"""把主辦方的陳情資料（「市長，你給我聽好了」）彙總成統計數字。只輸出件數，原文不寫進任何輸出檔。

用法
    python3 data/fetch/aggregate_petitions.py data/raw/petitions/<檔名>.csv
    python3 data/fetch/aggregate_petitions.py data/raw/petitions/<檔名>.json --text-col 內容 --area-col 行政區
    python3 data/fetch/aggregate_petitions.py <檔案> --list-cols      # 先看有哪些欄位，不輸出任何內容
    python3 data/fetch/aggregate_petitions.py <檔案> --region "" --themes all   # 不限內湖、全部主題

輸入：CSV（UTF-8 或 Big5）、JSON（物件陣列，或包著一個陣列的物件）、XLSX（要裝 openpyxl）。
      檔案一定要放在 data/raw/ 底下（不進 git）；放在別處會拒絕執行，避免原文被 commit。
輸出：data/processed/petitions_summary.json（可以進 git），內容只有：
      - 篩選條件與總件數
      - 依主題、依月份、依行政區、依原始類別的件數
      - 少於 MIN_CELL 件的格子寫成 "<3"，不寫實際數字，避免從少數案件反推身分
      `brief.public` 的「內湖交通陳情則數」直接用 total。

規則（主辦方要求）：不得反推身分、不得使用真實個資、僅限本活動使用、原文不放進 repo 或公開頁面。
所以這支程式不輸出任何原文、摘要、例句或關鍵字出現的位置；要看原文請直接開 data/raw/ 裡的檔案，不要貼到 issue 或聊天。

欄位：預設依常見欄名自動判斷（見 GUESS），對不上就用 --text-col 等參數指定。
"""
import argparse
import csv
import datetime as dt
import json
import re
import sys
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "data" / "raw"
OUT = REPO / "data" / "processed" / "petitions_summary.json"
MIN_CELL = 3

GUESS = {
    "text": ["內容", "陳情內容", "陳情事項", "案件內容", "描述", "content", "text", "body", "description"],
    "title": ["標題", "主旨", "案由", "title", "subject"],
    "date": ["日期", "陳情日期", "受理日期", "建立時間", "時間", "date", "created_at", "time"],
    "area": ["行政區", "區域", "地區", "區", "district", "area"],
    "category": ["類別", "案件類別", "分類", "主類別", "category", "type"],
}

# 地區篩選：內文或行政區欄出現任一詞就算
REGION = ["內湖", "內科", "南港", "汐止", "堤頂", "成美橋", "民權大橋", "麥帥", "康寧路", "環東", "舊宗路", "瑞光路", "港墘", "文湖線"]

# 主題：一件可以同時屬於多個主題；對應作品裡的入口、城市行動與「我們可能錯在哪」
THEMES = {
    "congestion": ("塞車、壅塞", ["塞車", "壅塞", "堵車", "回堵", "車流", "車陣", "尖峰", "交通黑暗"]),
    "bus": ("公車、接駁車", ["公車", "接駁", "客運", "班次", "擠不上", "站牌"]),
    "mrt": ("捷運、文湖線", ["捷運", "文湖線", "月台", "車廂"]),
    "scooter": ("機車", ["機車", "摩托車", "待轉"]),
    "parking": ("停車", ["停車", "車位", "違停", "違規停車", "臨停"]),
    "signal": ("號誌、路口", ["號誌", "紅綠燈", "秒數", "路口", "左轉", "迴轉"]),
    "walk": ("行人、人行道", ["行人", "人行道", "斑馬線", "騎樓", "過馬路"]),
    "bike": ("自行車、YouBike", ["YouBike", "Ubike", "自行車", "腳踏車", "單車"]),
    "care": ("托育、接送小孩", ["幼兒園", "托嬰", "托育", "接送", "小孩", "延托"]),
    "flex": ("上班時間、彈性上班", ["彈性上班", "上班時間", "錯峰", "分流", "遠距", "在家工作"]),
}


def load(path):
    suf = path.suffix.lower()
    if suf == ".csv":
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "cp950"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        else:
            sys.exit("CSV 不是 UTF-8 也不是 Big5，請另存成 UTF-8")
        return list(csv.DictReader(text.splitlines()))
    if suf == ".json":
        d = json.loads(path.read_text(encoding="utf-8-sig"))
        if isinstance(d, dict):
            d = next((v for v in d.values() if isinstance(v, list)), [])
        return [r for r in d if isinstance(r, dict)]
    if suf in (".xlsx", ".xlsm"):
        try:
            import openpyxl
        except ImportError:
            sys.exit("讀 Excel 要先 pip install openpyxl，或另存成 CSV")
        ws = openpyxl.load_workbook(path, read_only=True, data_only=True).active
        rows = ws.iter_rows(values_only=True)
        head = [str(h or "").strip() for h in next(rows)]
        return [dict(zip(head, r)) for r in rows]
    sys.exit(f"不支援的格式：{suf}（可用 .csv、.json、.xlsx）")


def pick(cols, key, given):
    if given is not None:
        if given and given not in cols:
            sys.exit(f"找不到欄位「{given}」。有的欄位：{', '.join(cols)}")
        return given or None
    low = {c.lower().strip(): c for c in cols}
    return next((low[g.lower()] for g in GUESS[key] if g.lower() in low), None)


def month_of(v):
    if v is None or v == "":
        return None
    if isinstance(v, (dt.date, dt.datetime)):
        return f"{v.year:04d}-{v.month:02d}"
    s = str(v).strip()
    m = re.match(r"(\d{2,4})[-/.年](\d{1,2})", s)
    if not m:
        return None
    y, mo = int(m.group(1)), int(m.group(2))
    if y < 1911:  # 民國年
        y += 1911
    return f"{y:04d}-{mo:02d}" if 1 <= mo <= 12 else None


def suppress(counter):
    """依件數由多到少；少於 MIN_CELL 的寫 "<3"。"""
    return {k: (v if v >= MIN_CELL else f"<{MIN_CELL}") for k, v in counter.most_common()}


def main(argv):
    ap = argparse.ArgumentParser(description="陳情資料只輸出彙總統計")
    ap.add_argument("file", type=Path)
    for k in GUESS:
        ap.add_argument(f"--{k}-col", dest=k, help=f"{k} 欄位名稱；空字串代表沒有這欄")
    ap.add_argument("--region", default=",".join(REGION), help="地區關鍵字，逗號分隔；空字串代表不篩地區")
    ap.add_argument("--themes", default="all", help="要算的主題 id，逗號分隔，或 all")
    ap.add_argument("--list-cols", action="store_true", help="只印欄位名稱與筆數")
    ap.add_argument("--out", type=Path, default=OUT)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    path = args.file.resolve()
    if RAW.resolve() not in path.parents:
        sys.exit(f"陳情原檔要放在 {RAW}（不進 git），目前是 {path}")
    rows = load(path)
    if not rows:
        sys.exit("檔案裡沒有資料")
    cols = list(rows[0].keys())
    if args.list_cols:
        print(f"{len(rows):,} 筆；欄位：{', '.join(cols)}")
        return 0

    col = {k: pick(cols, k, getattr(args, k)) for k in GUESS}
    if not col["text"] and not col["title"]:
        sys.exit(f"找不到內文欄位，請用 --text-col 指定。有的欄位：{', '.join(cols)}")
    print("使用欄位：" + "、".join(f"{k}={v}" for k, v in col.items() if v))

    region = [w for w in args.region.split(",") if w]
    themes = THEMES if args.themes == "all" else {t: THEMES[t] for t in args.themes.split(",")}

    def field(r, k):
        return str(r.get(col[k]) or "") if col[k] else ""

    by_theme, by_month, by_area, by_cat = Counter(), Counter(), Counter(), Counter()
    total = untagged = 0
    for r in rows:
        text = field(r, "title") + " " + field(r, "text")
        if region and not any(w in text or w in field(r, "area") for w in region):
            continue
        total += 1
        hit = [t for t, (_, words) in themes.items() if any(w.lower() in text.lower() for w in words)]
        by_theme.update(hit)
        untagged += not hit
        if col["date"]:
            by_month[month_of(r.get(col["date"])) or "未知"] += 1
        if col["area"]:
            by_area[field(r, "area").strip() or "未填"] += 1
        if col["category"]:
            by_cat[field(r, "category").strip() or "未填"] += 1

    summary = {
        "source": "「市長，你給我聽好了」陳情資料（主辦方提供，已去識別化）",
        "generated_at": dt.datetime.now().isoformat(timespec="minutes"),
        "input_rows": len(rows),
        "filter": {"region_keywords": region, "note": "內文、標題或行政區出現任一關鍵字就算"},
        "total": total,
        "min_cell": MIN_CELL,
        "note": f"只含件數；少於 {MIN_CELL} 件寫成 \"<{MIN_CELL}\"。一件可以屬於多個主題，主題件數加總會大於 total。原文不在此檔。",
        "by_theme": [{"id": t, "label": themes[t][0], "count": c} for t, c in suppress(by_theme).items()],
        "no_theme": untagged if untagged >= MIN_CELL else f"<{MIN_CELL}",
        "by_month": dict(sorted(suppress(by_month).items())),
        "by_area": suppress(by_area),
        "by_category": suppress(by_cat),
        "theme_keywords": {t: words for t, (_, words) in themes.items()},
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    print(f"\n{len(rows):,} 筆中，符合地區條件的有 {total:,} 筆")
    for x in summary["by_theme"]:
        print(f"  {x['label']}：{x['count']}")
    print(f"  沒有對到主題：{summary['no_theme']}")
    print(f"\n寫到 {args.out}")
    print(f"一頁紙「內湖交通陳情則數」填 {total}（label: observed）；主題件數可以放進 limits 或城市行動的「為什麼」。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
