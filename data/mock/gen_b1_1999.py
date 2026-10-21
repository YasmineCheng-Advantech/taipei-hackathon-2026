"""產生 B1「1999 陳情熱區與處理效率」的模擬資料 data/mock/b1-1999.json。

用法：python3 data/mock/gen_b1_1999.py
驗證：python3 data/schema/validate.py data/mock/b1-1999.json

換題演練用：確認資料契約裝得下非交通題。全部數字都是模擬值（sim: true），結果固定、可重跑。
熱力圖的欄不是時段而是陳情類別；情境的欄是週。和交通題不合的地方記在 data/mock/README.md「b1-1999」。
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).with_name("b1-1999.json")
SIM = True

MOCK_METHOD = (
    "全部數字為模擬。熱力圖：12 個行政區 × 8 類陳情，每月件數 = 1,800 × 行政區權重 × 類別比例 × (1 + 固定擾動)；"
    "平均結案天數 = 類別基準天數 × (0.8 + 0.4 × 該格件數 ÷ 同類別平均件數)，件數越多越慢。行政區權重與類別比例為假設值，"
    "正式版改用臺北市 1999 派工資料（案件類別、行政區、受理與結案時間）計算。"
    "幫你決定：4 種陳情管道的預估回覆天數 = 管道基準 × 行政區負荷係數，區間 ±25%，全部是假設。"
    "情境：環境髒亂類 14 週的到達件數為鐘形曲線（第 8–9 週最高，平常每週約 550 件），每週可結案 1,000 件（±10%）為假設；"
    "把旺季 4 週的案件按比例提前到旺季前（主動巡查）或延後（非緊急案件），用確定性排隊模型算積案與消化時間。"
    "人數類欄位一律 pending，由認領後端提供。"
)


def tag(label, **fields):
    return {**fields, "label": label, "sim": SIM}


def num(label, value=None, lo=None, hi=None, unit=None, note=None):
    o = {}
    if value is not None:
        o["value"] = value
    if lo is not None:
        o["lo"], o["hi"] = lo, hi
    if unit is not None:
        o["unit"] = unit
    if note is not None:
        o["note"] = note
    return tag(label, **o)


def cell(label, v):
    return tag(label, v=v)


def headcount(note="意向登記，未經驗證"):
    return tag("observed", pending=True, unit="人", note=note)


def g(t, p, w):
    return math.exp(-((t - p) ** 2) / (2 * w * w))


def jitter(i, j):
    return ((i * 7 + j * 11) % 5 - 2) / 2  # −1 到 +1 之間的固定值，不是亂數


# ---------- 熱力圖：行政區 × 陳情類別 ----------

# 中心點為大略位置；權重是件數多寡的假設
DISTRICTS = [
    ("zhongzheng", "中正區", 25.0324, 121.5199, 0.9), ("datong", "大同區", 25.0633, 121.5130, 0.8),
    ("zhongshan", "中山區", 25.0685, 121.5333, 1.3), ("songshan", "松山區", 25.0497, 121.5578, 1.0),
    ("daan", "大安區", 25.0264, 121.5436, 1.5), ("wanhua", "萬華區", 25.0285, 121.4979, 1.1),
    ("xinyi", "信義區", 25.0330, 121.5654, 1.2), ("shilin", "士林區", 25.0928, 121.5246, 1.3),
    ("beitou", "北投區", 25.1321, 121.4987, 1.1), ("neihu", "內湖區", 25.0695, 121.5888, 1.4),
    ("nangang", "南港區", 25.0383, 121.6070, 0.7), ("wenshan", "文山區", 24.9897, 121.5701, 1.2),
]
# id、名稱、佔全部陳情的比例、基準結案天數、主管機關（假設）
CATEGORIES = [
    ("parking", "違規停車", 0.22, 2.0, "警察局"), ("road", "道路與人行道", 0.16, 6.0, "工務局新工處"),
    ("noise", "噪音", 0.12, 3.0, "環保局"), ("litter", "環境髒亂", 0.15, 4.0, "環保局"),
    ("light", "路燈", 0.08, 3.5, "工務局公燈處"), ("pests", "病媒蚊蟲", 0.06, 5.0, "環保局"),
    ("trees", "行道樹", 0.07, 9.0, "工務局公園處"), ("parks", "公園與綠地", 0.05, 8.0, "工務局公園處"),
]
CNAME = {c[0]: c[1] for c in CATEGORIES}
DNAME = {d[0]: d[1] for d in DISTRICTS}

COUNT = {(d[0], c[0]): round(1800 * d[4] * c[2] * (1 + 0.15 * jitter(i, j)))
         for i, d in enumerate(DISTRICTS) for j, c in enumerate(CATEGORIES)}
CAT_MEAN = {c[0]: sum(COUNT[(d[0], c[0])] for d in DISTRICTS) / len(DISTRICTS) for c in CATEGORIES}
DAYS = {(d[0], c[0]): round(c[3] * (0.8 + 0.4 * COUNT[(d[0], c[0])] / CAT_MEAN[c[0]]) + 0.3 * jitter(j, i), 1)
        for i, d in enumerate(DISTRICTS) for j, c in enumerate(CATEGORIES)}


def xy(lat, lng):
    return round((lng - 121.49) / 0.13 * 100), round((25.14 - lat) / 0.16 * 100)


rows = []
for did, name, lat, lng, _ in DISTRICTS:
    x, y = xy(lat, lng)
    rows.append({"id": did, "name": name, "kind": "observed", "lat": lat, "lng": lng, "x": x, "y": y})
cols = [{"id": cid, "label": name} for cid, name, *_ in CATEGORIES]

heatmap = {
    "title": "哪一區、哪一類陳情最多？",
    "subtitle": "12 個行政區 × 8 類陳情 · 每月平均",
    "days_label": "模擬的每月平均（正式版用 1999 派工資料的最近 12 個月）",
    "rows": rows,
    "cols": cols,
    "layers": [
        {"id": "count", "name": "陳情件數", "unit": "件／月", "direction": "high_is_bad",
         "thresholds": [100, 200, 300, 400, 500],
         "legend": ["<100", "100–200", "200–300", "300–400", "400–500", "500+"], "legend_ends": ["少", "多 件"],
         "level_text": ["很少。", "偏少。", "中等。", "偏多。", "很多。", "最多的一群。"],
         "cells": [[cell("observed", COUNT[(d[0], c[0])]) for c in CATEGORIES] for d in DISTRICTS]},
        {"id": "days", "name": "平均結案天數", "unit": "天", "direction": "high_is_bad",
         "thresholds": [2, 4, 6, 8, 10], "bad_at": 8,
         "legend": ["<2", "2–4", "4–6", "6–8", "8–10", "10+"], "legend_ends": ["快", "慢 天"],
         "level_text": ["很快結案。", "幾天內結案。", "要等快一週。", "要等一週以上。", "要等很久。", "最慢的一群。"],
         "cells": [[cell("computed", DAYS[(d[0], c[0])]) for c in CATEGORIES] for d in DISTRICTS]},
    ],
    "default_layer": "count",
    "landmarks": [{"name": "基隆河", "x": 55, "y": 45}, {"name": "淡水河", "x": 5, "y": 60}],
}

# ---------- 重點數字 ----------

top_n, top_d, top_c = max((v, d, c) for (d, c), v in COUNT.items())
slow = max(CATEGORIES, key=lambda c: sum(DAYS[(d[0], c[0])] for d in DISTRICTS))
slow_avg = round(sum(DAYS[(d[0], slow[0])] for d in DISTRICTS) / len(DISTRICTS), 1)
kpis = [
    tag("computed", id="top-cell", title="陳情最多的一格", value=top_n, unit="件／月",
        note=f"{DNAME[top_d]}的{CNAME[top_c]}", ref={"row": top_d, "col": top_c}),
    tag("computed", id="slowest", title="最慢結案的類別", value=slow_avg, unit="天", note=f"{slow[1]}，12 區平均"),
    tag("observed", id="coverage", title="資料涵蓋", value="12 / 12", unit="個行政區", note="正式版為 1999 派工資料的最近 12 個月"),
]

# ---------- 幫你決定：用哪個管道反映最快有回覆 ----------

CHANNELS = [  # id、名稱、基準天數、負荷敏感度（越高代表越多人用、越容易塞）、補充
    ("phone", "1999 電話", 3.0, 0.1, "24 小時有人接，但要口述地點"),
    ("app", "臺北通 APP", 2.6, 0.7, "可附照片與定位，系統直接分類"),
    ("mail", "市長信箱", 4.2, 0.2, "適合需要說明背景的問題"),
    ("office", "區公所臨櫃", 3.6, 0.3, "上班時間才有人"),
]
MIN_SAVE = 0.5  # 少不到半天就不推薦換管道


def reply_days(ch, w):
    base, sens = ch[2], ch[3]
    return base * (1 - sens + sens * w / 1.5)


def plan(did, w):
    opts = []
    for ch in CHANNELS:
        m = reply_days(ch, w)
        opts.append(dict(ch=ch, m=round(m, 1), rng=(round(m * 0.75, 1), round(m * 1.25, 1))))
    base = opts[0]
    best = min(opts[1:], key=lambda o: o["m"])
    rec = best if base["m"] - best["m"] >= MIN_SAVE else base
    options = []
    for o in opts:
        s = [round(b - x, 1) for b, x in zip(base["rng"], o["rng"])]
        options.append({
            "id": o["ch"][0], "key": o["ch"][1], "detail": o["ch"][4],
            "cost": num("assumed", o["m"], lo=o["rng"][0], hi=o["rng"][1], unit="天", note="從送出到第一次回覆；區間是不同類別的差異"),
            "saved": num("assumed", round(base["m"] - o["m"], 1), lo=min(s), hi=max(s), unit="天", note="和打 1999 相比；假設只有你換管道"),
            "status": "open",
        })
    if rec is base:
        reason = f"在{DNAME[did]}，各管道的回覆時間差不到半天，用你習慣的方式反映就好。"
    else:
        reason = f"在{DNAME[did]}用{best['ch'][1]}，大約比打 1999 早 {round(base['m'] - best['m'], 1)} 天收到回覆：{best['ch'][4]}。"
    return {"row": did, "recommended": rec["ch"][0], "baseline": "phone", "reason": reason, "options": options}


decide = {
    "title": "想反映問題，用哪個管道最快有回覆",
    "metric": {"name": "預估回覆天數", "unit": "天"},
    "setup": {"rows": [d[0] for d in DISTRICTS]},
    "plans": [plan(d[0], d[4]) for d in DISTRICTS],
}

# ---------- 如果大家都這樣 ----------

CITY_DAYS = {c[0]: sum(DAYS[(d[0], c[0])] for d in DISTRICTS) / len(DISTRICTS) for c in CATEGORIES}


def mode_curve(f):
    return [cell("assumed", round(CITY_DAYS[c[0]] * f, 1)) for c in CATEGORIES]


collective = {
    "title": "如果大家都改用同一個管道呢？",
    "place": "全市",
    "cols": [c[0] for c in CATEGORIES],
    "layer": "days",
    "modes": [
        {"id": "solo", "title": "只有你換管道", "delta": num("assumed", -0.6, unit="天"),
         "text": "你早一點收到回覆，其他人不受影響。", "curve": mode_curve(1.0)},
        {"id": "same", "title": "大家都改用 APP", "delta": num("assumed", -0.1, unit="天"),
         "text": "APP 的案件暴增，承辦人一樣多，大家只快一點點。", "curve": mode_curve(1.1), "highlight": ["litter", "parking"]},
        {"id": "split", "title": "依各管道負荷分流", "delta": num("assumed", -0.4, unit="天"),
         "text": "案件平均分散到各管道，每件都快一點。", "curve": mode_curve(0.93)},
    ],
    "claims": {
        "total": headcount(),
        "note": "APP 已滿載，系統開始建議改用市長信箱或臨櫃。",
        "slots": [{"key": ch[1], "filled": num("assumed", p, unit="%"), "full": p >= 100}
                  for ch, p in zip(CHANNELS, (72, 100, 45, 60))],
    },
}

# ---------- 情境：環境髒亂類的積案（14 週，預先算好） ----------

WEEKS = list(range(14))
SC_COLS = [{"id": f"w{t + 1:02d}", "label": f"第 {t + 1} 週"} for t in WEEKS]
CAP = 1000  # 每週可結案件數（假設）
CAPS = (CAP * 1.1, CAP, CAP * 0.9)
PEAK_IDX = [6, 7, 8, 9]  # 旺季第 7–10 週
TARGETS = [("early", "旺季前主動巡查（第 3–4 週）", [2, 3]), ("late", "非緊急案件延後（第 11–12 週）", [10, 11])]
PEAK_AMP, PEAK_WIDTH = 0.7, 1.2


def demand(amp=PEAK_AMP, width=PEAK_WIDTH):
    return [round(CAP * (0.55 + amp * g(t, 7.5, width))) for t in WEEKS]


base_demand = demand()


def run_queue(arr, cap):
    q, max_q, last, sum_q, a_tot = 0.0, 0.0, -1, 0.0, 0.0
    qs, cum_a, cum_d = [], [], []
    for t, a in enumerate(arr):
        q = max(0.0, q + a - cap)
        a_tot += a
        qs.append(round(q))
        cum_a.append(round(a_tot))
        cum_d.append(round(a_tot - q))
        max_q = max(max_q, q)
        if q > 0:
            last = t
        sum_q += q
    return dict(queue=qs, cum_arrive=cum_a, cum_depart=cum_d, max=round(max_q), last=last, sum=sum_q)


BASE = run_queue(base_demand, CAP)


def clear_col(last):
    """積案消化完的那一週。契約的 clear_time 只能寫時刻（hhmm），週裝不下，所以另放 clear_col（提案中的新欄位）。"""
    if last < 0:
        return None
    return SC_COLS[last + 1]["id"] if last + 1 < len(SC_COLS) else SC_COLS[-1]["id"]


def result(arr, extra=None, new_peak=None):
    mid, lo, hi = run_queue(arr, CAP), run_queue(arr, CAPS[0]), run_queue(arr, CAPS[2])
    delay = 0 if BASE["sum"] == 0 else round((mid["sum"] - BASE["sum"]) / BASE["sum"] * 100)
    r = tag("computed", **(extra or {}),
            queue_max=num("computed", mid["max"], lo=lo["max"], hi=hi["max"], unit="件", note="lo／hi 對應每週結案量 +10%／−10%"),
            clear_time=None, clear_col=clear_col(mid["last"]),
            delay_change=num("computed", delay, unit="%"), new_peak=new_peak,
            cum_arrive=mid["cum_arrive"], cum_depart=mid["cum_depart"], queue=mid["queue"])
    if extra:
        r["queue_diff"] = [a - b for a, b in zip(mid["queue"], BASE["queue"])]
    return r


def shifted(share_pct, idx, base=None):
    base = base or base_demand
    after = [float(v) for v in base]
    moved = 0.0
    for i in PEAK_IDX:
        after[i] -= base[i] * share_pct / 100
        moved += base[i] * share_pct / 100
    for i in idx:
        after[i] += moved / len(idx)
    return after


results = []
for tid, _, idx in TARGETS:
    for p in range(0, 51, 5):
        after = shifted(p, idx)
        np_ = next((SC_COLS[i]["id"] for i in idx if after[i] > CAP), None)
        results.append(result(after, {"target": tid, "shift": p}, np_))


def first_share(ok):
    return next((p10 / 10 for p10 in range(501) if ok(p10 / 10)), None)


def half_share(cap=CAP, base=None):
    base = base or base_demand
    target = run_queue(base, cap)["max"] / 2
    return first_share(lambda p: run_queue(shifted(p, TARGETS[0][2], base), cap)["max"] <= target)


HALF = [half_share(c) for c in CAPS]


def sens(id_, name, low_text, high_text, low, high, needs):
    lo, hi = sorted((low, high))
    return tag("computed", id=id_, name=name, low_text=low_text, high_text=high_text,
               low=num("computed", round(low, 1), unit="%"), high=num("computed", round(high, 1), unit="%"),
               spread=round(hi - lo, 1), needs=needs)


SENSITIVITY = sorted([
    sens("capacity", "每週能結案多少件", "每週 1,100 件", "每週 900 件", HALF[0], HALF[2], "環保局各區清潔隊的每週結案量"),
    sens("peak-height", "旺季有多高", "旺季低 20%", "旺季高 20%",
         half_share(base=demand(amp=PEAK_AMP * 0.8)), half_share(base=demand(amp=PEAK_AMP * 1.2)), "過去 3 年同期的每週案件數"),
], key=lambda x: -x["spread"])

scenario = {
    "title": "旺季前先處理，積案會少多少？",
    "intro": "拉動滑桿，把旺季（第 7–10 週）的一部分環境髒亂案件，提前到旺季前主動巡查，或把非緊急案件延後。結果用區間表示（每週結案量 ±10%）。",
    "place": "環境髒亂（全市）",
    "cols": SC_COLS,
    "slider": {"name": "旺季案件提前或延後處理的比例", "unit": "%", "min": 0, "max": 50, "step": 5, "default": 10},
    "peak_cols": [SC_COLS[i]["id"] for i in PEAK_IDX],
    "targets": [{"id": tid, "label": lab, "cols": [SC_COLS[i]["id"] for i in idx]} for tid, lab, idx in TARGETS],
    "capacity": num("assumed", CAP, lo=round(CAP * 0.9), hi=round(CAP * 1.1), unit="件／週"),
    "baseline": result(base_demand),
    "results": results,
    "sensitivity": {
        "title": "哪個假設最影響結論？",
        "question": "旺季最高積案減半，要提前處理幾 % 的旺季案件",
        "base": num("computed", round(HALF[1], 1), unit="%", note="每週結案 1,000 件時"),
        "items": SENSITIVITY,
        "note": f"目前最影響的是「{SENSITIVITY[0]['name']}」，最需要補的資料是：{SENSITIVITY[0]['needs']}。",
    },
}

# ---------- 城市行動 ----------

city = {
    "title": "大家的陳情，變成改善的證據",
    "goal": {"text": "要讓環境髒亂的旺季積案減半，旺季的案件大約要提前處理",
             "need": num("computed", value=round(HALF[1]), lo=round(HALF[0]), hi=round(HALF[2]), unit="% 提前處理",
                         note="區間對應每週結案量 ±10%；由排隊模型反推")},
    "claimed": headcount(),
    "claimed_since": "2026-10-24",
    "claimed_caption": "意向登記，未經驗證：同一支手機每天只算一次，但同一人仍可能重複登記，也不代表全體市民。",
    "note": "目標比例由排隊模型反推（程式計算），不是保證值；人數只計真實登記，沒有資料時顯示「尚無資料」。",
    "actions": [
        {"id": "patrol", "title": "旺季前主動巡查髒亂熱點", "depts": ["環保局"],
         "why": "熱力圖上件數最多的格子集中在少數行政區，旺季前先清，可以少接很多陳情。",
         "you": "你家附近的髒亂點在被投訴前就先處理。", "cost": "清潔隊加班費，待推估", "support": headcount()},
        {"id": "progress", "title": "陳情處理進度公開查詢", "depts": ["研考會"],
         "why": "很多重複陳情是因為不知道案子處理到哪裡。",
         "you": "送出後可以查到現在由誰處理、預計幾天。", "cost": "系統擴充，待推估", "support": headcount()},
        {"id": "routing", "title": "陳情自動分類，直接派到承辦單位", "depts": ["研考會", "資訊局"],
         "why": "類別分錯會轉來轉去，拉長結案天數。",
         "you": "案子少轉一手，早一點有人處理。", "cost": "低（既有分類規則調整）", "support": headcount()},
        {"id": "trees", "title": "行道樹修剪排程公開", "depts": ["工務局公園處"],
         "why": f"行道樹是平均結案最久的類別之一（約 {round(CITY_DAYS['trees'], 1)} 天，模擬值）。",
         "you": "知道你家門口的樹什麼時候會修。", "cost": "低（公開既有排程）", "support": headcount()},
        {"id": "border", "title": "臺北新北交界的髒亂點共同處理", "depts": ["臺北市環保局", "新北市環保局"], "cross_agency": True,
         "why": "交界處常互相認為是對方的轄區，案子容易卡住。",
         "you": "住在交界的人反映一次就有人處理。", "cost": "協調成本，待推估", "support": headcount()},
    ],
    "disclaimer": "以上是本作品依資料提出的建議，不代表市府已經承諾。人數只計真實登記，未經驗證；成本欄位待填。",
}

# ---------- 協商一頁紙（給局處） ----------


def avg_wait(arr, cap):
    """每件案子平均多等幾天（積案 × 7 天 ÷ 總件數）。"""
    return run_queue(arr, cap)["sum"] * 7 / sum(arr)


def effect(share, idx):
    after = shifted(share, idx)
    save = [avg_wait(base_demand, c) - avg_wait(after, c) for c in CAPS]
    change = [(run_queue(after, c)["max"] / run_queue(base_demand, c)["max"] - 1) * 100 for c in CAPS]
    return (num("computed", lo=round(min(save), 1), hi=round(max(save), 1), unit="天", note="每件案子平均少等的天數"),
            num("computed", lo=round(min(change)), hi=round(max(change)), unit="%", note="旺季最高積案的變化"))


EXPO_COLS = ["litter", "pests", "noise"]
top3 = sorted(DISTRICTS, key=lambda d: -COUNT[(d[0], "litter")])[:3]
brief = {
    "title": "[局處名稱]：旺季前主動巡查可以改善什麼",
    "org": "[局處名稱]",
    "date": "[產出日期]",
    "exposure": {
        "title": "貴局負責的類別，哪幾區最慢結案",
        "cols": EXPO_COLS,
        "layer": "days",
        "rows": [{"row": d[0], "share": num("computed", round(COUNT[(d[0], "litter")] / sum(COUNT[(x[0], "litter")] for x in DISTRICTS) * 100), unit="%"),
                  "cells": [cell("computed", DAYS[(d[0], c)]) for c in EXPO_COLS]} for d in top3],
        "note": "百分比為該區佔全市環境髒亂陳情的比例。顏色越深結案越慢。",
    },
    "conclusion": tag(
        "computed",
        text=(f"環境髒亂旺季的案件若有約 {round(HALF[0])}–{round(HALF[2])}% 改在旺季前主動處理，旺季最高積案可減半；"
              "但全部擠到旺季前也會形成新的積案高峰，所以要搭配非緊急案件延後。"),
        note="情境假設 · 程式計算 · 區間反映每週結案量 ±10%",
    ),
    "options": [
        {"id": "a", "name": "維持現況", "saving": num("computed", 0, unit="天"),
         "queue_change": num("computed", 0, unit="%", note="基準"), "cost_text": "無"},
        {"id": "b", "name": "旺季案件 10% 改在旺季前主動巡查", **dict(zip(("saving", "queue_change"), effect(10, TARGETS[0][2]))),
         "cost_text": "旺季前 2 週清潔隊加班"},
        {"id": "c", "name": "旺季案件 20%：一半主動巡查、一半非緊急延後",
         **dict(zip(("saving", "queue_change"), effect(20, TARGETS[0][2] + TARGETS[1][2]))),
         "cost_text": "需訂出「非緊急」的分類標準，並告知陳情人預計處理時間"},
    ],
    "support": [
        {"dept": "研考會", "text": "提供各類別每週案件數與結案時間，作為排班依據"},
        {"dept": "民政局", "text": "區公所協助回報轄區內的髒亂熱點"},
    ],
    "pilot": [
        {"key": "對照", "text": "主動巡查的行政區 vs. 未巡查的行政區；試辦前 4 週為基準期"},
        {"key": "指標", "text": "每週新案件數、平均結案天數、重複陳情比例"},
        {"key": "干擾", "text": "記錄颱風、連假、大型活動，分析時排除"},
        {"key": "停止條件", "text": "第 4 週新案件數沒有下降，或其他類別結案明顯變慢"},
    ],
    "public": [
        {"value": headcount(), "text": "表示需要「陳情處理進度公開查詢」的人數（未經驗證）"},
    ],
    "sources_text": "資料來源：[1999 派工資料，期間待填]。標示：真實觀測／程式計算／情境假設／AI 生成。本文件為黑客松作品之建議，不代表市府立場。",
}

# ---------- 我們可能錯在哪 ----------

limits = {
    "title": "我們可能錯在哪",
    "intro": "陳情資料反映的是「有人反映」，不一定等於「問題最嚴重」。以下是最可能推翻結論的地方。",
    "items": [
        {"id": "reporting", "title": "件數多不等於問題多",
         "why": "人口多、通勤人口多、習慣用 APP 的區，件數自然比較多；有些區的人不習慣反映。",
         "handling": "正式版同時顯示每萬人件數，並標出人口與通勤人口的差異。", "status": "partial"},
        {"id": "closed", "title": "結案不等於解決",
         "why": "結案可能只是回覆「已轉知」或「非本局權責」。",
         "handling": "需要結案方式欄位；目前沒有，尚未處理。", "status": "open"},
        {"id": "duplicates", "title": "同一個問題被很多人反映",
         "why": "熱門地點會被重複陳情，件數看起來很多，但其實是同一件事。",
         "handling": "正式版依地點與時間合併重複案件後再算。", "status": "partial"},
        {"id": "category", "title": "類別可能分錯",
         "why": "受理人員依描述分類，同一件事可能被分到不同類別。",
         "handling": "只用大類，不用細類。", "status": "partial"},
        {"id": "privacy", "title": "陳情內容可能含個資",
         "why": "原文可能有姓名、住址或可辨識的描述。",
         "handling": "只用類別、行政區、時間做彙總，原文不進 repo、不上網站。", "status": "handled"},
    ],
}

# ---------- 組合 ----------

doc = {
    "meta": {
        "contract_version": "1.0",
        "id": "b1-1999",
        "title": "1999 陳情熱區與處理效率",
        "subtitle": "12 個行政區 × 8 類陳情 · 每月平均",
        "region": "臺北市 12 個行政區",
        "days": "每月平均",
        "time_range": {"start": "00:00", "end": "23:59"},  # 契約要求時刻，但這題是全天的月資料，見 README
        "bin_minutes": 1440,
        "sources": [
            {"id": "tp-1999", "name": "臺北市 1999 派工資料（資料集待確認）", "kind": "real", "note": "本檔未使用；正式版需要案件類別、行政區、受理與結案時間"},
            {"id": "mock", "name": "本作品模擬資料（data/mock/gen_b1_1999.py）", "kind": "mock"},
        ],
        "updated_at": "2026-10-20T12:00:00+08:00",
        "sim": True,
        "mock_method": MOCK_METHOD,
        "disclaimer": "本頁所有數字皆為模擬資料，行政區位置為示意。本作品之建議不代表市府立場。",
    },
    "heatmap": heatmap,
    "kpis": kpis,
    "decide": decide,
    "collective": collective,
    "scenario": scenario,
    "city": city,
    "brief": brief,
    "limits": limits,
}

OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
