"""產生 #4 內科晨峰的模擬資料 data/mock/t4-morning.json。

用法：python3 data/mock/gen_t4_morning.py
驗證：python3 data/schema/validate.py data/mock/t4-morning.json

全部數字都是模擬值（sim: true），結果固定、可重跑。方法寫在輸出 JSON 的 meta.mock_method。
入口、數字與文字沿用 design/heatmap-canvas 的 Main、V2Setup、V2Today、V2City、Scenario、V2Brief 畫板，
讓網站照設計稿接上時畫面一致；城市目標與一頁紙的結論、做法比較改由下面的排隊模型反推，不再照抄設計稿。
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).with_name("t4-morning.json")
SIM = True

MOCK_METHOD = (
    "全部數字為模擬，入口與數字沿用 design/heatmap-canvas 設計稿。"
    "熱力圖：每個入口以高斯曲線組出車速與流量，尖峰設在 08:30–08:45（依交通局 2015 年「82% 集中在 9 時」、壅塞 8:30–9:30），再加固定擾動，重跑結果相同。"
    "入口標示依 entrances.csv 盤點：有 VD 的入口（內湖路一段、堤頂大道、民權大橋、成美橋、環東大道）標 observed，其中民權大橋、成美橋用引道 VD 代替；國1 內湖交流道待 TDX，標 assumed；麥帥二橋（只有出城方向 VD）與康寧路三段（無 VD）為缺口，不補值。"
    "幫你決定：選項是經過入口的時間（不是出門時間，因為不知道使用者從哪裡出發）；入口到公司的路上時間 = 自由車流分鐘 ×（1 + 壅塞係數 × 高斯曲線），尖峰 08:40，壅塞係數 ±20% 當作每天路況差異的區間；同時算出比平常早到公司幾分鐘；名額比例為假設值。"
    "情境：堤頂大道北向單一瓶頸，容量 1,000 輛/15 分鐘（±10%）為假設；把 08:30–09:15 的需求按比例移到提早或延後時段，用確定性排隊模型算排隊長度、消散時間與總延誤。正式版由排隊模型腳本以 model_input.json 重算。"
    "城市目標（排隊減半要移出幾 %）與一頁紙的結論、做法比較，由同一個排隊模型反推。"
    "熱力圖每格另有 4 個平日的最小值、最大值與低於 20 km/h 的天數（模擬的每天偏移）。"
    "設定的出發地區與入口的對應是依路網推測的假設。"
    "人數類欄位（意向登記人數、「我也需要」人數）不放模擬值，一律 pending，由認領後端提供；後端沒有資料時網站顯示「尚無資料」。"
)


def tag(label, **fields):
    """帶數字的最小物件都附 label 與 sim。"""
    return {**fields, "label": label, "sim": SIM}


def num(label, value=None, lo=None, hi=None, unit=None, note=None, src=None):
    o = {}
    if value is not None:
        o["value"] = value
    if lo is not None:
        o["lo"], o["hi"] = lo, hi
    if unit is not None:
        o["unit"] = unit
    if note is not None:
        o["note"] = note
    if src is not None:
        o["src"] = src
    return tag(label, **o)


def cell(label, v, **extra):
    return tag(label, v=v, **extra)


GAP = {"gap": True, "note": "無偵測器，不補值"}

CLAIMS_SINCE = "2026-10-24"  # 意向登記起算日（票選開始）


def headcount(note="意向登記，未經驗證"):
    """人數一律等後端的真實數字，JSON 不放模擬值；網站沒拿到數字時顯示「尚無資料」。"""
    return tag("observed", pending=True, unit="人", note=note)


def g(t, p, w):
    return math.exp(-((t - p) ** 2) / (2 * w * w))


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def mins(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def col(prefix, start):
    return {"id": f"{prefix}{start.replace(':', '')}", "label": start, "start": start, "end": hhmm(mins(start) + 15)}


# ---------- 熱力圖 ----------

HEAT_TIMES = [hhmm(7 * 60 + 15 * i) for i in range(10)]  # 07:00–09:15，涵蓋 07:00–09:30
HEAT_COLS = [col("t", t) for t in HEAT_TIMES]
CID = {c["label"]: c["id"] for c in HEAT_COLS}

# kind：observed＝正式版用 VD 真實觀測；sim＝無公開偵測器，正式版仍用模擬；gap＝無偵測器
# lat/lng 為大略位置；x/y 是設計稿入口示意圖座標
ENTRANCES = [
    dict(id="neihu-rd-1", name="內湖路一段", sub="由大直", kind="observed", peak=6.4, sev=0.72, cap=820, lat=25.08487, lng=121.5586, x=12, y=35,
         detector="VTXQJ20"),
    dict(id="tiding-n", name="堤頂大道", sub="北向", kind="observed", peak=6.8, sev=1.0, cap=1480, lat=25.06689, lng=121.57246, x=24, y=55,
         detector="VPMSV40"),
    dict(id="minquan-br", name="民權大橋", sub="往內湖", kind="observed", peak=6.2, sev=0.88, cap=1320, lat=25.06674, lng=121.57845, x=30, y=74,
         detector="VQBUL20（橋上無 VD，以橋東端民權東路六段代替）"),
    dict(id="macarthur-2", name="麥帥二橋", sub="往內湖", kind="gap", lat=25.0590, lng=121.5860, x=46, y=86),  # 唯一 VD 只測出城方向
    dict(id="chengmei-br", name="成美橋", sub="往內湖", kind="observed", peak=6.5, sev=0.95, cap=1120, lat=25.05537, lng=121.59419, x=60, y=88,
         detector="VMLXB00（橋上無 VD，以南岸引道向陽路代替）"),
    dict(id="huandong", name="環東大道", sub="往內科", kind="observed", peak=5.9, sev=0.82, cap=1400, lat=25.05829, lng=121.62187, x=74, y=78,
         detector="V6310G0"),
    dict(id="nh1-neihu-ic", name="國1 內湖交流道", sub="下匝道", kind="sim", peak=5.5, sev=0.9, cap=900, lat=25.0735, lng=121.5960, x=84, y=62),  # 待 TDX
    dict(id="kangning-3", name="康寧路三段", sub="由汐止", kind="gap", lat=25.0740, lng=121.6120, x=90, y=30),  # 無 VD
]
EBY = {e["id"]: e for e in ENTRANCES}


def speed_flow(i, e, t):
    k = g(t, e["peak"], 1.7)
    jitter = ((i * 7 + t * 11) % 5) - 2
    return max(6, round(58 - 50 * e["sev"] * k + jitter)), round(e["cap"] * (0.42 + 0.58 * k) + jitter * 8)


def cell_label(e):
    return "observed" if e["kind"] == "observed" else "assumed"


# 每天的變動：收集期間 10/20–10/23 共 4 個平日。各天相對平均的偏移加總為 0，越塞的格子變動越大
DAY_F = (-0.25, -0.05, 0.1, 0.2)
BAD_SPEED = 20  # 車速低於這個值算「塞」


def speed_days(v):
    return [max(5, round(v - (58 - v) * f)) for f in DAY_F]


def flow_days(v):
    return [round(v * (1 + 0.2 * f)) for f in DAY_F]


def spread(days, bad=None):
    o = dict(lo=min(days), hi=max(days), days=len(days))
    if bad is not None:
        o["bad_days"] = sum(bad(x) for x in days)
    return o


SPEED = {}  # (row id, col index) -> km/h，給 KPI 與一頁紙用
speed_cells, flow_cells = [], []
for i, e in enumerate(ENTRANCES):
    srow, frow = [], []
    for t in range(len(HEAT_COLS)):
        if e["kind"] == "gap":
            srow.append(GAP)
            frow.append(GAP)
            continue
        sp, fl = speed_flow(i, e, t)
        SPEED[(e["id"], t)] = sp
        srow.append(cell(cell_label(e), sp, **spread(speed_days(sp), lambda x: x < BAD_SPEED)))
        frow.append(cell(cell_label(e), fl, **spread(flow_days(fl))))
    speed_cells.append(srow)
    flow_cells.append(frow)

rows = []
for e in ENTRANCES:
    r = {k: e[k] for k in ("id", "name", "sub", "kind", "x", "y", "lat", "lng")}
    if e["kind"] == "observed":
        r["src"] = "vd-live"
        r["detector"] = e["detector"]
    rows.append(r)

heatmap = {
    "title": "早上八點半，車都卡在哪裡？",
    "subtitle": "平日 07:00–09:30 · 每 15 分鐘 · 流入內湖",
    "days_label": f"{len(DAY_F)} 個平日（模擬，對應 10/20–10/23 收集期間）",
    "rows": rows,
    "cols": HEAT_COLS,
    "layers": [
        {
            "id": "speed", "name": "壅塞（車速）", "unit": "平均車速 km/h", "direction": "low_is_bad",
            "thresholds": [50, 40, 30, 20, 10],
            "bad_at": BAD_SPEED,
            "legend": ["50+", "40–50", "30–40", "20–30", "10–20", "<10"],
            "legend_ends": ["順", "塞 km/h"],
            "level_text": ["車流順暢。", "略有車多。", "開始變慢。", "明顯壅塞。", "嚴重壅塞，走走停停。", "幾乎停滯。"],
            "cells": speed_cells,
        },
        {
            "id": "flow", "name": "需求（流量）", "unit": "輛 / 15 分鐘", "direction": "high_is_bad",
            "thresholds": [400, 600, 800, 1000, 1200],
            "legend": ["<400", "400–600", "600–800", "800–1000", "1000–1200", "1200+"],
            "legend_ends": ["少", "多 輛"],
            "level_text": ["車很少。", "車流偏少。", "車流中等。", "車流偏多。", "車流很多。", "車流接近上限。"],
            "cells": flow_cells,
        },
    ],
    "default_layer": "speed",
    "landmarks": [{"name": "內湖科技園區", "x": 62, "y": 30}, {"name": "基隆河", "x": 40, "y": 94}],
    "aux": {
        "title": "文湖線負載",
        "subtitle": "改搭捷運吃得下嗎？",
        "unit": "%",
        "alert_at": 90,
        "values": [cell("assumed", round(55 + 40 * g(t, 6.3, 2.0))) for t in range(len(HEAT_COLS))],
    },
}

# ---------- 重點數字 ----------

worst_speed, wrow, wt = min((v, r, t) for (r, t), v in SPEED.items())
n_obs = sum(e["kind"] == "observed" for e in ENTRANCES)
kpis = [
    tag("computed", id="worst-cell", title="最塞的一格", value=worst_speed, unit="km/h",
        note=(f"{EBY[wrow]['name']} {HEAT_TIMES[wt]}，平均車速最低；{len(DAY_F)} 天裡有 "
              f"{sum(x < BAD_SPEED for x in speed_days(worst_speed))} 天低於 {BAD_SPEED} km/h"),
        ref={"row": wrow, "col": HEAT_COLS[wt]["id"]}),
    tag("computed", id="peak-window", title="尖峰集中時段", value="08:30–09:15", note="半數以上入口低於 20 km/h"),
    tag("observed", id="coverage", title="偵測器覆蓋", value=f"{n_obs} / {len(ENTRANCES)}", unit="個入口有真實資料",
        note="其餘為模擬或缺口，格子另有標示"),
]

# ---------- 幫你決定：每個 入口 × 最晚到達 一份 ----------

SETUP_ROWS = ["tiding-n", "minquan-br", "chengmei-br", "huandong"]
DEADLINES = ["08:30", "09:00", "09:30", "10:00"]
FREE_FLOW = {"tiding-n": 8, "minquan-br": 9, "chengmei-br": 10, "huandong": 7}  # 自由車流分鐘
CONGEST = {"tiding-n": 3.0, "minquan-br": 2.6, "chengmei-br": 2.8, "huandong": 2.4}
PEAK_DEPART = mins("08:40")
SLOT_PCT = {"07:00": 85, "07:15": 70, "07:30": 35, "07:45": 12, "08:00": 0, "09:15": 40, "09:30": 60, "09:45": 75}
PEAK_DEPARTS = {"08:15", "08:30", "08:45", "09:00"}  # 尖峰時段不開放認領


DAY_SPREAD = (0.8, 1.2)  # 每天路況不同：壅塞係數 ±20%，給個人分鐘數的區間
MAX_EARLY = 30  # 比平常早到超過這麼多分鐘就不推薦：早到的時間比省下的路上時間還多，多數人不會照做


def travel(row, t, k=1.0):
    """t 是經過入口的時間；回傳從入口到公司的分鐘。不含入口之前的路段，因為不知道使用者從哪裡出發。"""
    return round(FREE_FLOW[row] * (1 + CONGEST[row] * k * g(mins(t), PEAK_DEPART, 35)))


def plan(row, deadline):
    dl = mins(deadline)
    times = [hhmm(m) for m in range(dl - 120, dl, 15) if m >= 7 * 60]
    opts = []
    for d in times:
        m = travel(row, d)
        arrive = hhmm(mins(d) + m)
        late = mins(arrive) > dl
        slot = None if d in PEAK_DEPARTS else SLOT_PCT.get(d)
        status = "late" if late else "peak" if slot is None else "full" if slot == 0 else "open"
        opts.append(dict(d=d, m=m, rng=[travel(row, d, k) for k in DAY_SPREAD], arrive=arrive, slot=slot, status=status))
    on_time = [o for o in opts if o["status"] != "late"]
    # 平常：最晚到達前 45 分鐘經過入口（設計稿 09:00 到 → 08:15）；來不及就往前找
    base = next((o for o in reversed(on_time) if mins(o["d"]) <= dl - 45), on_time[0])
    # 推薦：比平常省時間、還有名額、早到不超過 MAX_EARLY 分鐘的時段中，離平常時間最近的，改變最少
    better = [o for o in on_time if o["status"] == "open" and o["m"] < base["m"]
              and mins(base["arrive"]) - mins(o["arrive"]) <= MAX_EARLY]
    rec = min(better, key=lambda o: abs(mins(o["d"]) - mins(base["d"]))) if better else base

    def saved_of(o):
        s = [b - x for b, x in zip(base["rng"], o["rng"])]
        return num("assumed", base["m"] - o["m"], lo=min(s), hi=max(s), unit="分",
                   note="假設只有你改時間、其他車不變；區間是每天路況的差異")

    options = []
    for o in opts:
        x = {"id": "d" + o["d"].replace(":", ""), "key": o["d"], "arrive": o["arrive"],
             "cost": num("computed", o["m"], lo=min(o["rng"]), hi=max(o["rng"]), unit="分",
                         note="從入口到公司；區間是每天路況的差異"),
             "saved": saved_of(o),
             "arrive_early": num("computed", mins(base["arrive"]) - mins(o["arrive"]), unit="分",
                                 note="正數＝比平常早到公司幾分鐘，負數＝晚到"),
             "status": o["status"]}
        if o["slot"] is not None:
            x["slot_left"] = num("assumed", o["slot"], unit="%")
        options.append(x)
    place = EBY[row]["name"]
    if rec is base:
        too_early = any(o["status"] == "open" and o["m"] < base["m"] for o in on_time)
        why = (f"還有名額的時段都要比平常早到 {MAX_EARLY} 分鐘以上，省下的路上時間不夠多" if too_early
               else "來得及、又比較不塞的時段都沒有名額")
        reason = f"今天沒有划算的時段，照平常 {base['d']} 經過{place}就好（{why}）。"
    else:
        s = saved_of(rec)
        early = mins(base["arrive"]) - mins(rec["arrive"])
        when = f"會比平常早 {early} 分到公司" if early > 0 else f"會比平常晚 {-early} 分到公司" if early < 0 else "到公司的時間和平常差不多"
        reason = (f"{rec['d']} 經過{place}還有名額，路上比平常（{base['d']}）少 {s['lo']}–{s['hi']} 分，"
                  f"但{when}；{deadline} 前到得了。")
    return {"row": row, "deadline": deadline, "recommended": "d" + rec["d"].replace(":", ""),
            "baseline": "d" + base["d"].replace(":", ""), "reason": reason, "options": options}


decide = {
    "title": "今天幾點經過入口最好",
    "metric": {"name": "入口到公司的路上時間", "unit": "分"},
    "setup": {
        "rows": SETUP_ROWS,
        "deadlines": DEADLINES,
        "flex": [
            {"id": "both", "label": "可以提早或延後", "note": "前後 45 分鐘都可以", "allows": "both"},
            {"id": "earlier", "label": "只能提早", "note": "例如晚上要早點離開", "allows": "earlier"},
            {"id": "later", "label": "只能延後", "note": "例如早上要先送小孩", "allows": "later"},
            {"id": "none", "label": "不能調整", "note": "我們會告訴你最不塞的路線，不會叫你改時間", "allows": "none"},
        ],
        # 出發地區對應的入口是依路網推測的假設，正式版用設定答案與 VD 資料校正
        "origins": [
            {"id": "xindian-wenshan", "label": "新店／文山", "region": "新北市・臺北市", "rows": ["huandong"],
             "note": "多半走國 3 接南港系統、環東大道。走基隆路接麥帥橋的人：麥帥二橋往內湖方向沒有偵測器，目前無法給建議。"},
            {"id": "songshan-nangang", "label": "松山／信義／南港", "region": "臺北市", "rows": ["chengmei-br", "minquan-br"]},
            {"id": "zhongshan-dazhi", "label": "中山／大直／士林", "region": "臺北市", "rows": ["tiding-n", "minquan-br"]},
            {"id": "ntpc-west", "label": "三重／蘆洲／板橋等新北西側", "region": "新北市", "rows": ["tiding-n"]},
            {"id": "xizhi-keelung", "label": "汐止／基隆", "region": "新北市・基隆市", "rows": [],
             "note": "多半走國 1 內湖交流道或康寧路：國 1 的資料還在等 TDX，康寧路沒有偵測器，目前無法給建議。"},
            {"id": "other", "label": "其他", "rows": SETUP_ROWS},
        ],
        "constraints": [
            {"id": "kids", "label": "要接送小孩", "actions": ["care", "care-ntpc"], "share_text": "要先送小孩去幼兒園"},
            {"id": "shift", "label": "輪班或排班，時間不是自己決定", "actions": ["flex"], "share_text": "我的班表不是我能決定的"},
            {"id": "company", "label": "公司規定固定的上班時間", "actions": ["flex"], "share_text": "公司規定幾點一定要到"},
            {"id": "meeting", "label": "早上固定開會，主管期待準時", "actions": ["flex"], "share_text": "早上一到公司就要開會"},
            {"id": "transit", "label": "改時段後沒有接駁或大眾運輸可搭", "actions": ["shuttle", "ntpc-bus"],
             "share_text": "那個時段沒有車可以搭"},
        ],
    },
    "plans": [plan(r, d) for r in SETUP_ROWS for d in DEADLINES],
}

# ---------- 如果大家都這樣（堤頂大道北向） ----------

LEVEL_SPEED = [55, 45, 35, 25, 15, 8]  # 色階等級對應的代表車速


def curve(levels):
    return [cell("assumed", LEVEL_SPEED[lv]) for lv in levels]


SLOTS = [("07:15", 30, False), ("07:30", 65, False), ("07:45", 88, False), ("08:00", 100, True)]
collective = {
    "title": "如果大家都這樣做呢？",
    "place": "堤頂大道北向",
    "cols": [c["id"] for c in HEAT_COLS],
    "layer": "speed",
    "modes": [
        {"id": "solo", "title": "只有你這樣做", "delta": num("assumed", -12, unit="分"), "text": "你省很多，但路況幾乎不變。",
         "curve": curve([0, 0, 1, 1, 2, 3, 4, 5, 5, 4])},
        {"id": "same", "title": "大家都照同一建議", "delta": num("assumed", -2, unit="分"), "text": "07:30 變成新尖峰，大家只省一點點。",
         "curve": curve([0, 1, 4, 5, 4, 3, 3, 4, 4, 3]), "highlight": [CID["07:30"]]},
        {"id": "split", "title": "依名額分配", "delta": num("assumed", -7, unit="分"), "text": "尖峰被攤平，平均每人都省到時間。",
         "curve": curve([0, 1, 2, 2, 2, 3, 3, 3, 3, 2])},
    ],
    "claims": {
        "total": headcount(),
        "note": "08:00 已滿，系統開始把人推薦到 07:15 和 07:30，避免形成新尖峰。",
        "slots": [{"key": k, "filled": num("assumed", p, unit="%"), "full": f} for k, p, f in SLOTS],
    },
}

# ---------- 情境（堤頂大道北向單一瓶頸，預先算好） ----------

SC_TIMES = [hhmm(7 * 60 + 15 * i) for i in range(14)]  # 07:00–10:15，涵蓋 07:00–10:30
SC_COLS = [col("s", t) for t in SC_TIMES]
CAP = 1000
PEAK_IDX = [6, 7, 8, 9]  # 08:30–09:15
TARGETS = [("early", "提早到 07:30–08:00", [2, 3]), ("late", "延後到 09:30–10:00", [10, 11])]
base_demand = [round(CAP * (0.5 + 0.78 * g(t, 7, 1.8))) for t in range(len(SC_TIMES))]


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


def clear_time(last):
    if last < 0:
        return None
    return SC_TIMES[last + 1] if last + 1 < len(SC_TIMES) else "10:30"


BASE = run_queue(base_demand, CAP)


def result(arr, extra=None, new_peak=None):
    mid, lo, hi = run_queue(arr, CAP), run_queue(arr, CAP * 1.1), run_queue(arr, CAP * 0.9)
    delay = 0 if BASE["sum"] == 0 else round((mid["sum"] - BASE["sum"]) / BASE["sum"] * 100)
    r = tag(
        "computed",
        **(extra or {}),
        queue_max=num("computed", mid["max"], lo=lo["max"], hi=hi["max"], unit="輛", note="lo／hi 對應容量 +10%／−10%"),
        clear_time=clear_time(mid["last"]),
        delay_change=num("computed", delay, unit="%"),
        new_peak=new_peak,
        cum_arrive=mid["cum_arrive"],
        cum_depart=mid["cum_depart"],
        queue=mid["queue"],
    )
    if extra:
        r["queue_diff"] = [a - b for a, b in zip(mid["queue"], BASE["queue"])]
    return r


def shifted(share_pct, idx):
    s = share_pct / 100
    after = [float(v) for v in base_demand]
    moved = 0.0
    for i in PEAK_IDX:
        after[i] -= base_demand[i] * s
        moved += base_demand[i] * s
    for i in idx:
        after[i] += moved / len(idx)
    return after


results = []
for tid, _, idx in TARGETS:
    for p in range(0, 51, 5):
        after = shifted(p, idx)
        np_ = next((SC_COLS[i]["id"] for i in idx if after[i] > CAP), None)
        results.append(result(after, {"target": tid, "shift": p}, np_))

scenario = {
    "title": "要多少人換時段，才不會塞？",
    "intro": "拉動滑桿，把 08:30–09:15 的一部分車流移到其他時段。結果用區間表示（容量 ±10%），也會標出移過去之後是否形成新的尖峰。",
    "place": "堤頂大道北向",
    "cols": SC_COLS,
    "slider": {"name": "移出尖峰的比例", "unit": "%", "min": 0, "max": 50, "step": 5, "default": 5},
    "references": [{"value": 6.5, "text": "檀香山 1988 實際參與 6–7%", "src": "honolulu-1988"}],
    "peak_cols": [SC_COLS[i]["id"] for i in PEAK_IDX],
    "targets": [{"id": tid, "label": lab, "cols": [SC_COLS[i]["id"] for i in idx]} for tid, lab, idx in TARGETS],
    "capacity": num("assumed", CAP, lo=round(CAP * 0.9), hi=round(CAP * 1.1), unit="輛/15 分鐘"),
    "baseline": result(base_demand),
    "results": results,
}

# ---------- 從排隊模型反推：城市目標與一頁紙共用 ----------

CAPS = (CAP * 1.1, CAP, CAP * 0.9)  # 容量高→低，結果由小到大
EARLY = TARGETS[0][2]
SPLIT = TARGETS[0][2] + TARGETS[1][2]  # 一半提早、一半延後
PEAK_TOTAL = sum(base_demand[i] for i in PEAK_IDX)


def first_share(ok):
    """移出比例從 0% 往上找，每 0.1% 一次，回傳第一個讓 ok(p) 成立的比例。"""
    return next((p10 / 10 for p10 in range(501) if ok(p10 / 10)), None)


# 最長排隊減半：和同一容量下的現況比。提早或延後算出來一樣，因為排隊只發生在尖峰
HALF = [first_share(lambda p, c=c: run_queue(shifted(p, EARLY), c)["max"] <= run_queue(base_demand, c)["max"] / 2)
        for c in CAPS]
# 新尖峰：移入的時段需求超過容量
NEW_PEAK = [first_share(lambda p, c=c: any(v > c for i, v in enumerate(shifted(p, EARLY)) if i in EARLY))
            for c in CAPS]


def avg_delay(arr, cap):
    """經過瓶頸的車，平均每輛排隊幾分鐘。"""
    return run_queue(arr, cap)["sum"] * 15 / sum(arr)


def effect(share, idx):
    """移出 share% 後：平均每輛少排幾分鐘、最長排隊變化 %，區間對應容量 ±10%。"""
    after = shifted(share, idx)
    save = [avg_delay(base_demand, c) - avg_delay(after, c) for c in CAPS]
    change = [(run_queue(after, c)["max"] / run_queue(base_demand, c)["max"] - 1) * 100 for c in CAPS]
    return (num("computed", lo=round(min(save), 1), hi=round(max(save), 1), unit="分", note="經過瓶頸的車平均每輛少排的分鐘"),
            num("computed", lo=round(min(change)), hi=round(max(change)), unit="%", note="最長排隊的變化"))


def veh(p):
    return round(PEAK_TOTAL * p / 100, -1)


# ---------- 城市行動 ----------

city = {
    "title": "大家的選擇，變成改善的證據",
    "goal": {"text": "要讓堤頂大道早上最長排隊減半，08:30–09:15 經過的車大約要移出",
             "need": num("computed", value=round(HALF[1]), lo=round(HALF[0]), hi=round(HALF[2]), unit="% 改時段",
                         note=f"約 {veh(HALF[0]):,.0f}–{veh(HALF[2]):,.0f} 輛車；區間對應容量 ±10%；由排隊模型反推，不換算成人數")},
    "claimed": headcount(),
    "claimed_since": CLAIMS_SINCE,
    "claimed_caption": "意向登記，未經驗證：同一支手機每天每個入口只算一次，但同一人仍可能重複登記，也不代表全體通勤者。",
    "note": "目標比例由排隊模型反推（程式計算），不是保證值；人數只計真實登記，沒有資料時顯示「尚無資料」。",
    "actions": [
        {"id": "flex", "title": "企業彈性上班誘因", "depts": ["交通局", "產發局"],
         "why": "要讓排隊減半，光靠個人不夠，需要整間公司一起調整上班時間。",
         "you": "你的公司加入，你才真的能每天錯峰。", "cost": "誘因預算，待推估", "support": headcount()},
        {"id": "care", "title": "幼兒園提早到 07:30 收托", "depts": ["教育局"],
         "why": "設定中選「只能延後」的人，最常見的原因是早上要送小孩。",
         "you": "要接送小孩的家長也能提早出門。", "cost": "人力成本，待推估", "support": headcount()},
        {"id": "shuttle", "title": "捷運站接駁車 07:15 起加班", "depts": ["公運處"],
         "why": "提早出門的人改搭捷運後，最後一段到公司的接駁車還沒開。",
         "you": "提早出門也有車可以搭。", "cost": "加班車成本，待推估", "support": headcount()},
        {"id": "signal", "title": "堤頂大道路口早上號誌調整", "depts": ["交工處"],
         "why": "熱力圖上 08:30–09:00 最深的格子集中在這裡。",
         "you": "就算不能改時間，也少塞一點。", "cost": "低（調整既有號誌時制）", "support": headcount()},
        {"id": "care-ntpc", "title": "新北的幼兒園早上提早收托", "depts": ["新北市教育局"], "cross_agency": True,
         "why": "從新北來的家長，小孩多半讀新北的幼兒園，臺北市的托育政策管不到。",
         "you": "住新北、要先送小孩的人也能錯峰。", "cost": "人力成本，待推估", "support": headcount()},
        {"id": "ntpc-bus", "title": "新店／文山直達內科的通勤車", "depts": ["新北市交通局", "臺北市公運處"], "cross_agency": True,
         "why": "從新店到內科搭捷運要轉乘，門到門的時間沒有比開車短，開車的人很難改搭大眾運輸。",
         "you": "不開車也能在差不多的時間到內科。", "cost": "營運補貼，待推估", "support": headcount()},
        {"id": "freeway", "title": "國 3 往內湖路段與市區入口的路況放在同一張圖", "depts": ["交通部高速公路局", "臺北市交工處"],
         "cross_agency": True,
         "why": "從新店、文山來的人，最不穩的常是國 3 這段（使用者回饋），但它不歸臺北市管，兩邊的資料沒有放在一起。",
         "you": "出門前能一起看到國道和入口的路況。", "cost": "資料介接，待推估", "support": headcount()},
    ],
    "breakdowns": [
        {"id": "origin", "title": "大家從哪裡來", "source": "origins", "note": "依設定時選的出發地區彙總，未經驗證",
         "items": [{"key": o, "count": headcount()} for o in
                   ("xindian-wenshan", "songshan-nangang", "zhongshan-dazhi", "ntpc-west", "xizhi-keelung", "other")]},
        {"id": "why-not", "title": "為什麼沒辦法錯峰", "source": "constraints", "note": "可複選；自願填答，不代表全體通勤者",
         "items": [{"key": c, "count": headcount()} for c in ("kids", "shift", "company", "meeting", "transit")]},
    ],
    "disclaimer": "以上是本作品依資料提出的建議，不代表市府已經承諾。「我也需要」人數只計真實登記，未經驗證；成本欄位待填。",
}

# ---------- 協商一頁紙 ----------

EXPO_T = list(range(0, 9))  # 07:00–09:00
brief = {
    "title": "[企業名稱]：分批上班可以改善什麼",
    "org": "[企業名稱]",
    "date": "[產出日期]",
    "exposure": {
        "title": "貴公司員工經過的入口，什麼時候最塞",
        "cols": [HEAT_COLS[t]["id"] for t in EXPO_T],
        "layer": "speed",
        "rows": [
            {"row": r, "share": num("assumed", p, unit="%"),
             "cells": [cell(cell_label(EBY[r]), SPEED[(r, t)]) for t in EXPO_T]}
            for r, p in [("tiding-n", 42), ("minquan-br", 31), ("chengmei-br", 27)]
        ],
        "note": "百分比為員工經過各入口的比例（假設，正式版用員工通勤調查或認領資料）。顏色越深車速越慢。",
    },
    "conclusion": tag(
        "computed",
        text=(f"內科整體若讓 08:30–09:15 經過堤頂大道的車移出約 {round(HALF[0])}–{round(HALF[2])}% 改時段，"
              f"最長排隊可縮短一半；但如果全部改到 07:30–08:00，移出超過約 {round(NEW_PEAK[2])}–{round(NEW_PEAK[0])}% "
              "就會在那裡形成新尖峰，所以要分散到提早與延後。貴公司員工約佔這段車流的 [待填]%。"),
        note="情境假設 · 程式計算 · 區間反映容量估計 ±10%",
    ),
    "options": [
        {"id": "a", "name": "維持現況", "saving": num("computed", 0, unit="分"),
         "queue_change": num("computed", 0, unit="%", note="基準"), "cost_text": "無"},
        {"id": "b", "name": "尖峰車流移出 10%，改到 07:30–08:00", **dict(zip(("saving", "queue_change"), effect(10, EARLY))),
         "cost_text": "改時段的員工共同會議時段縮短（例如 09:30–17:00）"},
        {"id": "c", "name": "尖峰車流移出 20%，一半提早到 07:30–08:00、一半延後到 09:30–10:00",
         **dict(zip(("saving", "queue_change"), effect(20, SPLIT))),
         "cost_text": "共同會議時段 10:00–16:30；對外客服需排班"},
    ],
    "support": [
        {"dept": "交通局 · 產發局", "text": "參與企業的錯峰成果可計入綠運輸 ESG 指標；[誘因方案待定]"},
        {"dept": "教育局", "text": "內科周邊幼兒園提早到 07:30 收托，讓有接送需求的員工也能參與"},
        {"dept": "公運處", "text": "07:15 起加開捷運站接駁車"},
        {"dept": "交工處", "text": "試辦期間調整堤頂大道早上號誌時制"},
    ],
    "pilot": [
        {"key": "對照", "text": "參與企業 vs. 同入口未參與企業；試辦前 2 週為基準期"},
        {"key": "指標", "text": "門禁刷卡到達時間分布、入口 VD 排隊消散時間、員工通勤時間自評"},
        {"key": "干擾", "text": "記錄施工、連假、颱風、開學日，分析時排除"},
        {"key": "停止條件", "text": "第 2 週參與率低於 [門檻]，或新時段排隊比基準期更長"},
    ],
    "public": [
        {"value": headcount(), "text": f"意向登記錯峰時段的人數（未經驗證，{CLAIMS_SINCE[5:7]}/{CLAIMS_SINCE[8:]} 起）"},
        {"value": headcount(), "text": "表示需要「企業彈性上班誘因」的人數（未經驗證）"},
        {"value": tag("observed", pending=True, unit="則", note="待主辦方提供陳情資料"),
         "text": "「市長，你給我聽好了」內湖交通陳情則數（彙總，不含原文）"},
    ],
    "sources_text": "資料來源：[VD 偵測器資料集與期間] · [捷運分時進出量] · [認領彙總，不含個資]。標示：真實觀測／程式計算／情境假設／AI 生成。本文件為黑客松作品之建議，不代表市府立場。",
}

# ---------- 分享卡 ----------

share = {
    "title": "分享你卡在哪裡",
    "places": [{"id": r["id"], "label": f"{r['name']}（{r['sub']}）", "row": r["id"]} for r in rows] + [
        {"id": "nh3-muzha", "label": "國 3 木柵隧道到南港系統", "note": "不在我們的資料範圍，卡片只顯示你選的地點"},
        {"id": "keelung-rd-macarthur", "label": "基隆路接麥帥橋", "note": "不在我們的資料範圍，卡片只顯示你選的地點"},
        {"id": "other", "label": "其他"},
    ],
    "templates": [
        {"id": "save", "title": "錯峰可以少塞多久", "text": "我每天 {time} 卡在{place}。提早經過，路上可以少 {saved} 分鐘。",
         "needs": ["time", "place", "saved"], "note": "{saved} 用今天建議的區間；今天沒有推薦時不能選這張"},
        {"id": "cant", "title": "我想錯峰，但是…", "text": "我想錯峰，但{constraint}。內科通勤需要的不只是早點出門。",
         "needs": ["constraint"]},
        {"id": "from", "title": "我從哪裡來", "text": "我從{origin}開車到內科，每天卡在{place}。你卡在哪裡？",
         "needs": ["origin", "place"]},
    ],
    "sim_badge": "含模擬資料",
    "footer": "[作品網址]",
    "note": "只放使用者自己選的內容與已標示的數字；用到模擬數字時，卡片角落一定印上 sim_badge。",
}

# ---------- 組合 ----------

doc = {
    "meta": {
        "contract_version": "1.0",
        "id": "t4-morning",
        "title": "內科晨峰車流",
        "subtitle": "平日 07:00–09:30 · 每 15 分鐘 · 流入內湖",
        "region": "內湖科技園區聯外入口",
        "days": "平日",
        "time_range": {"start": "07:00", "end": "09:30"},
        "bin_minutes": 15,
        "sources": [
            {"id": "vd-live", "name": "臺北市交工處 VD 即時資料（VDLive.xml）", "kind": "real",
             "url": "https://tcgbusfs.blob.core.windows.net/blobtisv/VDLive.xml", "period": "2026-10-19～10-23 07:00–10:30（收集中，本檔未使用）"},
            {"id": "vd-static", "name": "臺北市交工處 VD 靜態資料（VD.xml）", "kind": "real",
             "url": "https://tcgbusfs.blob.core.windows.net/blobtisv/VD.xml", "note": "入口與 VD 對照見 entrances.csv"},
            {"id": "dot-2015", "name": "交通局 2015 年內湖上班時間調查", "kind": "survey",
             "url": "https://dot.gov.taipei/News_Content.aspx?n=42F54DDC552218AD&sms=051295A13C5CC507&s=6B82592FD161ADB6",
             "note": "82% 集中在上午 9 時；資料已逾十年"},
            {"id": "honolulu-1988", "name": "Giuliano & Golob，TRR 1280（1990）檀香山錯峰試辦", "kind": "survey",
             "url": "https://onlinepubs.trb.org/Onlinepubs/trr/1990/1280/1280-006.pdf"},
            {"id": "mock", "name": "本作品模擬資料（data/mock/gen_t4_morning.py）", "kind": "mock"},
        ],
        "updated_at": "2026-10-19T12:00:00+08:00",
        "sim": SIM,
        "mock_method": MOCK_METHOD,
        "disclaimer": "本頁所有數字皆為模擬資料，入口位置為示意。本作品之建議不代表市府立場。",
    },
    "heatmap": heatmap,
    "kpis": kpis,
    "decide": decide,
    "collective": collective,
    "scenario": scenario,
    "city": city,
    "brief": brief,
    "share": share,
}

OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
