"""產生 #4 內科晨峰的模擬資料 data/mock/t4-morning.json。

用法：python3 data/mock/gen_t4_morning.py
驗證：python3 data/schema/validate.py data/mock/t4-morning.json

全部數字都是模擬值（sim: true），結果固定、可重跑。方法寫在輸出 JSON 的 meta.mock_method。
入口、數字與文字沿用 design/heatmap-canvas 的 Main、V2Setup、V2Today、V2City、Scenario、V2Brief 畫板，
讓網站照設計稿接上時畫面一致。
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).with_name("t4-morning.json")
SIM = True

MOCK_METHOD = (
    "全部數字為模擬，入口與數字沿用 design/heatmap-canvas 設計稿。"
    "熱力圖：每個入口以高斯曲線組出車速與流量，尖峰設在 08:30–08:45（依交通局 2015 年「82% 集中在 9 時」、壅塞 8:30–9:30），再加固定擾動，重跑結果相同。"
    "label 依正式版的資料性質標：有 VD 的入口標 observed，無偵測器的入口標 assumed；麥帥二橋為缺口，不補值。"
    "幫你決定：路上時間 = 自由車流分鐘 ×（1 + 壅塞係數 × 高斯曲線），尖峰 08:40；名額比例為假設值。"
    "情境：堤頂大道北向單一瓶頸，容量 1,000 輛/15 分鐘（±10%）為假設；把 08:30–09:15 的需求按比例移到提早或延後時段，用確定性排隊模型算排隊長度、消散時間與總延誤。正式版由排隊模型腳本以 model_input.json 重算。"
    "認領人數、支持數為模擬備援值。"
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


def cell(label, v):
    return tag(label, v=v)


GAP = {"gap": True, "note": "無偵測器，不補值"}


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
    dict(id="neihu-rd-1", name="內湖路一段", sub="由大直", kind="observed", peak=6.4, sev=0.72, cap=820, lat=25.0830, lng=121.5620, x=12, y=35),
    dict(id="tiding-n", name="堤頂大道", sub="北向", kind="observed", peak=6.8, sev=1.0, cap=1480, lat=25.0715, lng=121.5710, x=24, y=55),
    dict(id="minquan-br", name="民權大橋", sub="往內湖", kind="observed", peak=6.2, sev=0.88, cap=1320, lat=25.0662, lng=121.5790, x=30, y=74),
    dict(id="macarthur-2", name="麥帥二橋", sub="往內湖", kind="gap", lat=25.0590, lng=121.5860, x=46, y=86),
    dict(id="chengmei-br", name="成美橋", sub="往內湖", kind="observed", peak=6.5, sev=0.95, cap=1120, lat=25.0575, lng=121.6005, x=60, y=88),
    dict(id="huandong", name="環東大道", sub="往內科", kind="sim", peak=5.9, sev=0.82, cap=1400, lat=25.0640, lng=121.6150, x=74, y=78),
    dict(id="nh1-neihu-ic", name="國1 內湖交流道", sub="下匝道", kind="sim", peak=5.5, sev=0.9, cap=900, lat=25.0735, lng=121.5960, x=84, y=62),
    dict(id="kangning-3", name="康寧路三段", sub="由汐止", kind="sim", peak=5.1, sev=0.6, cap=700, lat=25.0740, lng=121.6120, x=90, y=30),
]
EBY = {e["id"]: e for e in ENTRANCES}


def speed_flow(i, e, t):
    k = g(t, e["peak"], 1.7)
    jitter = ((i * 7 + t * 11) % 5) - 2
    return max(6, round(58 - 50 * e["sev"] * k + jitter)), round(e["cap"] * (0.42 + 0.58 * k) + jitter * 8)


def cell_label(e):
    return "observed" if e["kind"] == "observed" else "assumed"


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
        srow.append(cell(cell_label(e), sp))
        frow.append(cell(cell_label(e), fl))
    speed_cells.append(srow)
    flow_cells.append(frow)

rows = []
for e in ENTRANCES:
    r = {k: e[k] for k in ("id", "name", "sub", "kind", "x", "y", "lat", "lng")}
    if e["kind"] == "observed":
        r["src"] = "vd-live"
        r["detector"] = "[VD 編號待盤點]"
    rows.append(r)

heatmap = {
    "title": "早上八點半，車都卡在哪裡？",
    "subtitle": "平日 07:00–09:30 · 每 15 分鐘 · 流入內湖",
    "rows": rows,
    "cols": HEAT_COLS,
    "layers": [
        {
            "id": "speed", "name": "壅塞（車速）", "unit": "平均車速 km/h", "direction": "low_is_bad",
            "thresholds": [50, 40, 30, 20, 10],
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
        note=f"{EBY[wrow]['name']} {HEAT_TIMES[wt]}，平均車速最低", ref={"row": wrow, "col": HEAT_COLS[wt]["id"]}),
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


def travel(row, depart):
    return round(FREE_FLOW[row] * (1 + CONGEST[row] * g(mins(depart), PEAK_DEPART, 35)))


def plan(row, deadline):
    dl = mins(deadline)
    departs = [hhmm(m) for m in range(dl - 120, dl, 15) if m >= 7 * 60]
    opts = []
    for d in departs:
        m = travel(row, d)
        arrive = hhmm(mins(d) + m)
        late = mins(arrive) > dl
        slot = None if d in PEAK_DEPARTS else SLOT_PCT.get(d)
        status = "late" if late else "peak" if slot is None else "full" if slot == 0 else "open"
        opts.append(dict(d=d, m=m, arrive=arrive, slot=slot, status=status))
    on_time = [o for o in opts if o["status"] != "late"]
    # 平常：最晚到達前 45 分鐘出門（設計稿 09:00 到 → 08:15 出門）；來不及就往前找
    base = next((o for o in reversed(on_time) if mins(o["d"]) <= dl - 45), on_time[0])
    # 推薦：比平常省時間、還有名額的時段中，離平常出門時間最近的，改變最少
    better = [o for o in on_time if o["status"] == "open" and o["m"] < base["m"]]
    rec = min(better, key=lambda o: abs(mins(o["d"]) - mins(base["d"]))) if better else base
    options = []
    for o in opts:
        x = {"id": "d" + o["d"].replace(":", ""), "key": o["d"], "arrive": o["arrive"],
             "cost": num("computed", o["m"], unit="分"),
             "saved": num("computed", base["m"] - o["m"], unit="分"),
             "status": o["status"]}
        if o["slot"] is not None:
            x["slot_left"] = num("assumed", o["slot"], unit="%")
        options.append(x)
    saved = base["m"] - rec["m"]
    reason = (f"{rec['d']} 出門還有名額，比平常 {base['d']} 出門路上少 {saved} 分，{deadline} 前到得了。"
              if rec is not base else f"來得及的時段都沒有名額，維持 {base['d']} 出門。")
    return {"row": row, "deadline": deadline, "recommended": "d" + rec["d"].replace(":", ""),
            "baseline": "d" + base["d"].replace(":", ""), "reason": reason, "options": options}


decide = {
    "title": "今天的出門建議",
    "metric": {"name": "路上時間", "unit": "分"},
    "setup": {
        "rows": SETUP_ROWS,
        "deadlines": DEADLINES,
        "flex": [
            {"id": "both", "label": "可以提早或延後", "note": "前後 45 分鐘都可以", "allows": "both"},
            {"id": "earlier", "label": "只能提早", "note": "例如晚上要早點離開", "allows": "earlier"},
            {"id": "later", "label": "只能延後", "note": "例如早上要先送小孩", "allows": "later"},
            {"id": "none", "label": "不能調整", "note": "我們會告訴你最不塞的路線，不會叫你改時間", "allows": "none"},
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
        "total": num("assumed", 1284, unit="人", note="本週"),
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

# ---------- 城市行動 ----------

city = {
    "title": "大家的選擇，變成改善的證據",
    "goal": {"text": "要讓堤頂大道早上排隊減半，大約需要",
             "need": num("computed", lo=3000, hi=4500, unit="人換時段", note="照抄設計稿，正式值由排隊模型腳本反推")},
    "claimed": num("assumed", 1284, unit="人", note="本週"),
    "note": "人數為模擬資料；目標區間由排隊模型推估（程式計算），不是保證值。",
    "actions": [
        {"id": "flex", "title": "企業彈性上班誘因", "depts": ["交通局", "產發局"],
         "why": "要讓排隊減半，光靠個人不夠，需要整間公司一起調整上班時間。",
         "you": "你的公司加入，你才真的能每天錯峰。", "cost": "誘因預算，待推估", "support": num("assumed", 412, unit="人")},
        {"id": "care", "title": "幼兒園提早到 07:30 收托", "depts": ["教育局"],
         "why": "設定中選「只能延後」的人，最常見的原因是早上要送小孩。",
         "you": "要接送小孩的家長也能提早出門。", "cost": "人力成本，待推估", "support": num("assumed", 268, unit="人")},
        {"id": "shuttle", "title": "捷運站接駁車 07:15 起加班", "depts": ["公運處"],
         "why": "提早出門的人改搭捷運後，最後一段到公司的接駁車還沒開。",
         "you": "提早出門也有車可以搭。", "cost": "加班車成本，待推估", "support": num("assumed", 193, unit="人")},
        {"id": "signal", "title": "堤頂大道路口早上號誌調整", "depts": ["交工處"],
         "why": "熱力圖上 08:30–09:00 最深的格子集中在這裡。",
         "you": "就算不能改時間，也少塞一點。", "cost": "低（調整既有號誌時制）", "support": num("assumed", 157, unit="人")},
    ],
    "disclaimer": "以上是本作品依資料提出的建議，不代表市府已經承諾。支持人數與成本欄位為模擬或待填。",
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
        text="貴公司若讓一半員工改 08:00 前到，員工平均每天通勤少 6–10 分鐘，堤頂大道 08:30 的排隊可縮短約 15–25%。",
        note="情境假設 · 程式計算 · 區間反映容量估計的不確定",
    ),
    "options": [
        {"id": "a", "name": "維持現況", "saving": num("computed", 0, unit="分"),
         "queue_change": num("computed", 0, unit="%", note="基準"), "cost_text": "無"},
        {"id": "b", "name": "三成員工改 08:00 前到", "saving": num("computed", lo=3, hi=5, unit="分"),
         "queue_change": num("computed", lo=-12, hi=-8, unit="%"), "cost_text": "共同會議時段由 09:00–18:00 縮為 09:30–17:00"},
        {"id": "c", "name": "分兩批：一半 08:00、一半 09:30", "saving": num("computed", lo=6, hi=10, unit="分"),
         "queue_change": num("computed", lo=-25, hi=-15, unit="%"), "cost_text": "共同會議時段 10:00–16:30；對外客服需排班"},
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
        {"value": num("assumed", 1284, unit="人"), "text": "本週在 App 認領錯峰時段的人數"},
        {"value": num("assumed", 412, unit="人"), "text": "支持「企業彈性上班誘因」的人數"},
        {"value": tag("observed", pending=True, unit="則", note="待主辦方提供陳情資料"),
         "text": "「市長，你給我聽好了」內湖交通陳情則數（彙總，不含原文）"},
    ],
    "sources_text": "資料來源：[VD 偵測器資料集與期間] · [捷運分時進出量] · [認領彙總，不含個資]。標示：真實觀測／程式計算／情境假設／AI 生成。本文件為黑客松作品之建議，不代表市府立場。",
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
            {"id": "vd-live", "name": "縣市即時路況（VD 每 5 分鐘統計）", "kind": "real",
             "url": "https://data.gov.tw/dataset/166031", "period": "2026-10-19～10-23 07:00–10:30（收集中，本檔未使用）"},
            {"id": "vd-static", "name": "臺北市車輛偵測器（VD）靜態資料", "kind": "real",
             "url": "https://data.taipei/dataset/detail?id=47cb9090-e1c9-4b1d-b299-b11c375c5ee2"},
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
}

OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
