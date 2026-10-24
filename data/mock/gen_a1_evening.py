"""產生 A1「內科晚尖峰／下班車流」的模擬資料 data/mock/a1-evening.json。

用法：python3 data/mock/gen_t4_morning.py && python3 data/mock/gen_a1_evening.py
驗證：python3 data/schema/validate.py data/mock/a1-evening.json

換題演練用：以 t4-morning.json（模擬）為底，時間往後移 9 小時 30 分（08:30 → 18:00），入口改成出口（離開內湖），
文字改成下班的版本；「幫你決定」改成「幾點離開公司」，用同樣的公式重新計算。全部數字都是模擬值。
正式版要先盤點出城方向的偵測器（目前只知道麥帥二橋 V7230E0 是出城方向），再用
  python3 data/processed/build_vd_15min.py --start 16:30 --end 19:30 --out data/processed/vd_15min_evening.json data/raw/*.csv
彙整傍晚的資料（GitHub Actions 只收早上，傍晚要用自己的電腦 --end 21:00 收）。
"""

import copy
import json
import math
import re
from pathlib import Path

HERE = Path(__file__).parent
T4 = json.loads((HERE / "t4-morning.json").read_text(encoding="utf-8"))
OUT = HERE / "a1-evening.json"
SHIFT = 9 * 60 + 30
SIM = True

MOCK_METHOD = (
    "全部數字為模擬，用來演練換題。以 t4-morning（模擬）為底：熱力圖、情境與一頁紙的數字沿用早上的模擬值，"
    "時間往後移 9 小時 30 分，讓尖峰落在 18:00–18:45（交通局 2015 年調查的下午壅塞時段為 18:00–19:00）。"
    "入口改成離開內湖的出口；出城方向的偵測器還沒盤點，所以除了麥帥二橋（唯一的偵測器正好測出城方向）之外都標「模擬」，"
    "麥帥二橋的數字借用成美橋的模擬值。"
    "幫你決定：選項是離開公司的時間，平常下班時間前後各 1 小時；公司到出口的路上時間 = 自由車流分鐘 ×（1 + 壅塞係數 × 高斯曲線），"
    "尖峰 18:10，壅塞係數 ±20% 當作每天路況的區間；名額比例為假設值。"
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


def headcount(note="意向登記，未經驗證"):
    return tag("observed", pending=True, unit="人", note=note)


def g(t, p, w):
    return math.exp(-((t - p) ** 2) / (2 * w * w))


def mins(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def hhmm(m):
    return f"{m // 60:02d}:{m % 60:02d}"


def sh(t):
    return hhmm(mins(t) + SHIFT)


TIME = re.compile(r"(?<![\d:])([01]\d|2[0-3]):([0-5]\d)(?![\d:])")


def sh_text(s):
    """字串裡的 HH:MM 一律往後移；只用在確定是時段的文字上。"""
    return TIME.sub(lambda m: sh(m.group(0)), s)


def sh_id(cid):
    """欄 id 是 t0715、s0830 這種寫法，跟著時間一起移。"""
    return cid[0] + sh(f"{cid[1:3]}:{cid[3:5]}").replace(":", "")


def sh_col(c):
    return {"id": sh_id(c["id"]), "label": sh(c["label"]), "start": sh(c["start"]), "end": sh(c["end"])}


# ---------- 熱力圖：離開內湖的出口 ----------

SUB = {"neihu-rd-1": "往大直", "tiding-n": "南向（往市區）", "minquan-br": "往松山", "macarthur-2": "往市區",
       "chengmei-br": "往松山", "huandong": "往南港／國 3", "nh1-neihu-ic": "上匝道", "kangning-3": "往汐止"}
NAME = {"tiding-n": "堤頂大道"}
KIND = {"macarthur-2": "observed", "kangning-3": "gap"}  # 其餘出城方向的偵測器還沒盤點
ROW_IX = {r["id"]: i for i, r in enumerate(T4["heatmap"]["rows"])}


def relabel(c, label):
    return c if c.get("gap") else {**c, "label": label}


rows = []
for r in T4["heatmap"]["rows"]:
    kind = KIND.get(r["id"], "sim")
    x = {k: r[k] for k in ("id", "name", "x", "y", "lat", "lng")}
    x.update(sub=SUB[r["id"]], kind=kind)
    if r["id"] == "macarthur-2":
        x["detector"] = "V7230E0（麥帥二橋南向，出城方向）"
    rows.append(x)

layers = []
for layer in T4["heatmap"]["layers"]:
    cells = []
    for r in rows:
        src = "chengmei-br" if r["id"] == "macarthur-2" else r["id"]
        line = layer["cells"][ROW_IX[src]]
        if r["kind"] == "gap":
            cells.append([{"gap": True, "note": "無偵測器，不補值"} for _ in line])
        else:
            cells.append([relabel(c, "observed" if r["kind"] == "observed" else "assumed") for c in line])
    layers.append({**layer, "cells": cells})

cols = [sh_col(c) for c in T4["heatmap"]["cols"]]
CIX = {c["id"]: j for j, c in enumerate(cols)}
heatmap = {
    **T4["heatmap"],
    "title": "傍晚六點，車都卡在哪裡？",
    "subtitle": f"平日 {cols[0]['label']}–{cols[-1]['end']} · 每 15 分鐘 · 離開內湖",
    "days_label": "4 個平日（模擬）",
    "rows": rows,
    "cols": cols,
    "layers": layers,
    "aux": {**T4["heatmap"]["aux"], "subtitle": "改搭捷運回家吃得下嗎？"},
}

# ---------- 重點數字 ----------

speed = next(l for l in layers if l["id"] == "speed")
worst, wr, wc = min((c["v"], i, j) for i, line in enumerate(speed["cells"]) for j, c in enumerate(line) if not c.get("gap"))
wcell = speed["cells"][wr][wc]
n_obs = sum(r["kind"] == "observed" for r in rows)
live = [i for i, r in enumerate(rows) if r["kind"] != "gap"]
jam_t = [j for j in range(len(cols)) if sum(speed["cells"][i][j]["v"] < 20 for i in live) * 2 >= len(live)]
kpis = [
    tag("computed", id="worst-cell", title="最塞的一格", value=worst, unit="km/h",
        note=f"{rows[wr]['name']} {cols[wc]['label']}，平均車速最低；{wcell['days']} 天裡有 {wcell['bad_days']} 天低於 20 km/h",
        ref={"row": rows[wr]["id"], "col": cols[wc]["id"]}),
    tag("computed", id="peak-window", title="尖峰集中時段",
        value=f"{cols[jam_t[0]]['label']}–{cols[jam_t[-1]]['label']}" if jam_t else "無",
        note="半數以上出口低於 20 km/h" if jam_t else "沒有一個時段半數以上出口低於 20 km/h"),
    tag("observed", id="coverage", title="偵測器覆蓋", value=f"{n_obs} / {len(rows)}", unit="個出口有真實資料",
        note="出城方向的偵測器還沒盤點；麥帥二橋的偵測器正好是出城方向"),
]

# ---------- 幫你決定：幾點離開公司 ----------

SETUP_ROWS = ["tiding-n", "minquan-br", "chengmei-br", "huandong"]
USUAL = ["17:00", "17:30", "18:00", "18:30"]  # 平常下班時間（契約的 deadlines 欄位）
FREE_FLOW = {"tiding-n": 8, "minquan-br": 9, "chengmei-br": 10, "huandong": 7}
CONGEST = {"tiding-n": 3.0, "minquan-br": 2.6, "chengmei-br": 2.8, "huandong": 2.4}
PEAK_LEAVE = mins("18:10")
SLOT_PCT = {"16:00": 95, "16:15": 92, "16:30": 88, "16:45": 80, "17:00": 65, "17:15": 40, "17:30": 0,
            "18:45": 25, "19:00": 55, "19:15": 70, "19:30": 80, "19:45": 88, "20:00": 92}
PEAK_LEAVES = {"17:45", "18:00", "18:15", "18:30"}  # 尖峰時段不開放認領
DAY_SPREAD = (0.8, 1.2)
MAX_SHIFT = 30  # 經過出口的時間比平常早或晚超過這麼多分鐘，就不推薦


def travel(row, t, k=1.0):
    """t 是離開公司的時間；回傳公司到出口的分鐘。"""
    return round(FREE_FLOW[row] * (1 + CONGEST[row] * k * g(mins(t), PEAK_LEAVE, 35)))


def plan(row, usual):
    u = mins(usual)
    opts = []
    for m in range(u - 60, u + 61, 15):
        d = hhmm(m)
        t = travel(row, d)
        slot = None if d in PEAK_LEAVES else SLOT_PCT.get(d)
        status = "peak" if slot is None else "full" if slot == 0 else "open"
        opts.append(dict(d=d, m=t, rng=[travel(row, d, k) for k in DAY_SPREAD], arrive=hhmm(m + t), slot=slot, status=status))
    base = next(o for o in opts if o["d"] == usual)
    better = [o for o in opts if o["status"] == "open" and o["m"] < base["m"]
              and abs(mins(o["arrive"]) - mins(base["arrive"])) <= MAX_SHIFT]
    rec = min(better, key=lambda o: abs(mins(o["d"]) - u)) if better else base

    def saved_of(o):
        s = [b - x for b, x in zip(base["rng"], o["rng"])]
        return num("assumed", base["m"] - o["m"], lo=min(s), hi=max(s), unit="分",
                   note="假設只有你改時間、其他車不變；區間是每天路況的差異")

    options = []
    for o in opts:
        x = {"id": "d" + o["d"].replace(":", ""), "key": o["d"], "arrive": o["arrive"],
             "detail": "離開公司的時間",
             "cost": num("computed", o["m"], lo=min(o["rng"]), hi=max(o["rng"]), unit="分", note="從公司到出口；區間是每天路況的差異"),
             "saved": saved_of(o),
             "arrive_early": num("computed", mins(base["arrive"]) - mins(o["arrive"]), unit="分",
                                 note="正數＝比平常早經過出口幾分鐘，負數＝晚"),
             "status": o["status"]}
        if o["slot"] is not None:
            x["slot_left"] = num("assumed", o["slot"], unit="%")
        options.append(x)
    place = NAME.get(row, next(r["name"] for r in rows if r["id"] == row))
    if rec is base:
        reason = f"今天沒有划算的時段，照平常 {usual} 下班、經過{place}就好。"
    else:
        s = saved_of(rec)
        diff = mins(rec["arrive"]) - mins(base["arrive"])
        when = f"會比平常晚 {diff} 分經過出口" if diff > 0 else f"會比平常早 {-diff} 分經過出口" if diff < 0 else "經過出口的時間和平常差不多"
        less = f"{s['lo']}" if s["lo"] == s["hi"] else f"{s['lo']}–{s['hi']}"
        reason = f"{rec['d']} 離開公司還有名額，到{place}的路上比平常（{usual}）少 {less} 分，但{when}。"
    return {"row": row, "deadline": usual, "recommended": "d" + rec["d"].replace(":", ""),
            "baseline": "d" + usual.replace(":", ""), "reason": reason, "options": options}


t4_setup = T4["decide"]["setup"]
decide = {
    "title": "今天幾點離開公司最好",
    "metric": {"name": "公司到出口的路上時間", "unit": "分"},
    "setup": {
        "rows": SETUP_ROWS,
        "deadlines": USUAL,
        "flex": [
            {"id": "both", "label": "可以早走或晚走", "note": "前後 1 小時都可以", "allows": "both"},
            {"id": "earlier", "label": "只能早走", "note": "例如要去接小孩", "allows": "earlier"},
            {"id": "later", "label": "只能晚走", "note": "例如傍晚還要開會", "allows": "later"},
            {"id": "none", "label": "不能調整", "note": "我們會告訴你最不塞的出口，不會叫你改時間", "allows": "none"},
        ],
        "origins": [
            {"id": "xindian-wenshan", "label": "新店／文山", "region": "新北市・臺北市", "rows": ["huandong"],
             "note": "多半走環東大道接國 3。走麥帥橋接基隆路的人：麥帥二橋出城方向有偵測器，正式版可以給建議。"},
            {"id": "songshan-nangang", "label": "松山／信義／南港", "region": "臺北市", "rows": ["chengmei-br", "minquan-br"]},
            {"id": "zhongshan-dazhi", "label": "中山／大直／士林", "region": "臺北市", "rows": ["tiding-n", "minquan-br"]},
            {"id": "ntpc-west", "label": "三重／蘆洲／板橋等新北西側", "region": "新北市", "rows": ["tiding-n"]},
            {"id": "xizhi-keelung", "label": "汐止／基隆", "region": "新北市・基隆市", "rows": [],
             "note": "多半走國 1 或康寧路：國 1 是國道、我們拿不到它的偵測器資料，康寧路沒有偵測器，目前無法給建議。"},
            {"id": "other", "label": "其他", "rows": SETUP_ROWS},
        ],
        "constraints": [
            {"id": "kids", "label": "要在幼兒園關門前接小孩", "actions": ["care", "care-ntpc"], "share_text": "要趕在幼兒園關門前接小孩"},
            {"id": "shift", "label": "輪班或排班，時間不是自己決定", "actions": ["flex"], "share_text": "我的班表不是我能決定的"},
            {"id": "company", "label": "公司規定固定的下班時間", "actions": ["flex"], "share_text": "公司規定幾點才能走"},
            {"id": "meeting", "label": "傍晚固定開會，很難早走", "actions": ["flex"], "share_text": "傍晚還有會要開"},
            {"id": "transit", "label": "晚走就沒有接駁或大眾運輸可搭", "actions": ["shuttle", "ntpc-bus"],
             "share_text": "晚一點走就沒有車可以搭"},
        ],
    },
    "plans": [plan(r, u) for r in SETUP_ROWS for u in USUAL],
}

# ---------- 如果大家都這樣 ----------

co = copy.deepcopy(T4["collective"])
collective = {
    **co,
    "place": "堤頂大道南向",
    "cols": [sh_id(c) for c in co["cols"]],
    "modes": [{**m, "text": sh_text(m["text"]),
               **({"highlight": [sh_id(h) for h in m["highlight"]]} if "highlight" in m else {})} for m in co["modes"]],
    "claims": {**co["claims"], "note": sh_text(co["claims"]["note"]),
               "slots": [{**s, "key": sh(s["key"])} for s in co["claims"]["slots"]]},
}

# ---------- 情境：同一個排隊模型，時間往後移 ----------

sc = copy.deepcopy(T4["scenario"])


def sh_result(r):
    r = {**r, "clear_time": sh(r["clear_time"]) if r["clear_time"] else None}
    if r.get("new_peak"):
        r["new_peak"] = sh_id(r["new_peak"])
    return r


scenario = {
    **sc,
    "intro": sh_text(sc["intro"]),
    "place": "堤頂大道南向",
    "cols": [sh_col(c) for c in sc["cols"]],
    "peak_cols": [sh_id(c) for c in sc["peak_cols"]],
    "targets": [{**t, "label": sh_text(t["label"]).replace("提早到 ", "提早下班，").replace("延後到 ", "延後下班，"),
                 "cols": [sh_id(c) for c in t["cols"]]} for t in sc["targets"]],
    "baseline": sh_result(sc["baseline"]),
    "results": [sh_result(r) for r in sc["results"]],
    "sensitivity": {**sc["sensitivity"], "question": sh_text(sc["sensitivity"]["question"]),
                    "note": sh_text(sc["sensitivity"]["note"]).replace("VPMSV40", "堤頂大道南向偵測器"),
                    "items": [{**i, "needs": sh_text(i["needs"]).replace("VPMSV40", "堤頂大道南向偵測器")}
                              for i in sc["sensitivity"]["items"]]},
}

# ---------- 城市行動 ----------

ct = T4["city"]
peak_text = sh_text("08:30–09:15")
city = {
    **ct,
    "goal": {"text": f"要讓堤頂大道南向傍晚最長排隊減半，{peak_text} 經過的車大約要移出", "need": ct["goal"]["need"]},
    "actions": [
        {"id": "flex", "title": "企業彈性下班誘因", "depts": ["交通局", "產發局"],
         "why": "要讓排隊減半，光靠個人不夠，需要整間公司一起調整下班時間。",
         "you": "你的公司加入，你才真的能每天錯峰。", "cost": "誘因預算，待推估", "support": headcount()},
        {"id": "care", "title": "幼兒園延長收托到 19:00", "depts": ["教育局"],
         "why": "設定中選「只能早走」的人，最常見的原因是要趕在幼兒園關門前接小孩。",
         "you": "晚一點下班也來得及接小孩。", "cost": "人力成本，待推估", "support": headcount()},
        {"id": "shuttle", "title": "捷運站接駁車延長到 20:00", "depts": ["公運處"],
         "why": "晚走的人到捷運站時，接駁車已經收班。",
         "you": "晚一點走也有車可以搭。", "cost": "加班車成本，待推估", "support": headcount()},
        {"id": "signal", "title": "堤頂大道傍晚號誌調整", "depts": ["交工處"],
         "why": f"熱力圖上 {peak_text} 最深的格子集中在這裡。",
         "you": "就算不能改時間，也少塞一點。", "cost": "低（調整既有號誌時制）", "support": headcount()},
        {"id": "care-ntpc", "title": "新北的幼兒園延長收托", "depts": ["新北市教育局"], "cross_agency": True,
         "why": "住新北的家長，小孩多半讀新北的幼兒園，臺北市的托育政策管不到。",
         "you": "住新北、要接小孩的人也能晚一點走。", "cost": "人力成本，待推估", "support": headcount()},
        {"id": "ntpc-bus", "title": "內科直達新店／文山的下班通勤車", "depts": ["新北市交通局", "臺北市公運處"], "cross_agency": True,
         "why": "從內科回新店搭捷運要轉乘，門到門的時間沒有比開車短。",
         "you": "不開車也能在差不多的時間到家。", "cost": "營運補貼，待推估", "support": headcount()},
        {"id": "freeway", "title": "國 3 與市區出口的路況放在同一張圖", "depts": ["交通部高速公路局", "臺北市交工處"], "cross_agency": True,
         "why": "回新店、文山的人，最不穩的常是國 3 這段，但它不歸臺北市管。",
         "you": "下班前能一起看到國道和出口的路況。", "cost": "資料介接，待推估", "support": headcount()},
    ],
    "breakdowns": [{**b, "title": "大家往哪裡回家" if b["id"] == "origin" else b["title"]} for b in ct["breakdowns"]],
}

# ---------- 協商一頁紙 ----------

br = copy.deepcopy(T4["brief"])
expo_cols = [sh_id(c) for c in br["exposure"]["cols"]]
brief = {
    **br,
    "title": "[企業名稱]：分批下班可以改善什麼",
    "exposure": {**br["exposure"], "title": "貴公司員工經過的出口，什麼時候最塞", "cols": expo_cols,
                 "rows": [{**r, "cells": [relabel(speed["cells"][ROW_IX[r["row"]]][CIX[cid]], "assumed") for cid in expo_cols]}
                          for r in br["exposure"]["rows"]]},
    "conclusion": {**br["conclusion"], "text": sh_text(br["conclusion"]["text"]).replace("經過堤頂大道", "經過堤頂大道南向")},
    "options": [{**o, "name": sh_text(o["name"])} for o in br["options"]],
    "operations": [o for o in br["operations"] if o["id"] in ("commute", "meeting")] + [
        {"id": "departure", "title": f"{peak_text} 離開公司的員工比例",
         "value": tag("observed", pending=True, unit="%", note="試辦前後比較"),
         "how": "門禁刷卡（下班）時間依 15 分鐘分組，看尖峰時段離開的人有沒有變少。",
         "needs": "試辦前 2 週與試辦期間的門禁刷卡時間（去識別化）"},
        {"id": "parking", "title": "公司停車場尖峰的出場排隊",
         "value": tag("observed", pending=True, unit="分鐘", note="試辦前後比較"),
         "how": f"比較試辦前後 {peak_text} 每 15 分鐘的出場車數與排隊時間。",
         "needs": "停車場進出紀錄（每 15 分鐘的出場車數）"},
    ],
    "support": [
        {"dept": "交通局 · 產發局", "text": "參與企業的錯峰成果可計入綠運輸 ESG 指標；[誘因方案待定]"},
        {"dept": "教育局", "text": "內科周邊幼兒園延長收托到 19:00，讓要接小孩的員工也能晚一點走"},
        {"dept": "公運處", "text": "捷運站接駁車延長到 20:00"},
        {"dept": "交工處", "text": "試辦期間調整堤頂大道傍晚號誌時制"},
    ],
    "pilot": [{**p, "text": p["text"].replace("門禁刷卡到達時間分布、入口", "門禁刷卡離開時間分布、出口")} for p in br["pilot"]],
}
for o in brief["options"]:
    if o["id"] == "b":
        o["cost_text"] = "提早下班的員工，傍晚的共同會議時段縮短（例如 09:00–16:30）"
    elif o["id"] == "c":
        o["cost_text"] = "共同會議時段 10:00–16:00；傍晚的對外客服需排班"

# ---------- 我們可能錯在哪 ----------

lm = copy.deepcopy(T4["limits"])
for it in lm["items"]:
    if it["id"] == "coverage":
        it["why"] = "出城方向的偵測器還沒盤點；國 1 是國道、拿不到偵測器資料；康寧路沒有偵測器。麥帥二橋的偵測器正好是出城方向。"
    elif it["id"] == "early-arrival":
        it["title"] = "早走或晚走省下的路上時間，大多變成在公司少待或多待的時間"
        it["handling"] = "建議同時顯示「路上少幾分鐘」與「早或晚幾分鐘經過出口」；差超過 30 分鐘就不推薦。"
    elif it["id"] == "old-data":
        it["why"] = "「下午壅塞 18:00–19:00」出自 2015 年、疫情前的調查；6.3% 只指下午尖峰，都還要核對原文。"
limits = lm

# ---------- 分享卡 ----------

share = {
    **T4["share"],
    "places": [{"id": r["id"], "label": f"{r['name']}（{r['sub']}）", "row": r["id"]} for r in rows] + [
        {"id": "nh3-nangang-muzha", "label": "國 3 南港系統到木柵", "note": "不在我們的資料範圍，卡片只顯示你選的地點"},
        {"id": "keelung-rd", "label": "麥帥橋接基隆路", "note": "不在我們的資料範圍，卡片只顯示你選的地點"},
        {"id": "other", "label": "其他"},
    ],
    "templates": [
        {"id": "save", "title": "錯峰可以少塞多久", "text": "我每天 {time} 卡在{place}。早一點或晚一點走，路上可以少 {saved} 分鐘。",
         "needs": ["time", "place", "saved"], "note": "{saved} 用今天建議的區間；今天沒有推薦時不能選這張"},
        {"id": "cant", "title": "我想錯峰，但是…", "text": "我想錯峰，但{constraint}。內科通勤需要的不只是早點下班。",
         "needs": ["constraint"]},
        {"id": "from", "title": "我往哪裡回家", "text": "我從內科開車回{origin}，每天卡在{place}。你卡在哪裡？",
         "needs": ["origin", "place"]},
    ],
}

# ---------- 早上的字眼改成傍晚（沿用 t4 的文字裡） ----------

WORDS = [("入口", "出口"), ("流入內湖", "離開內湖"), ("4 個早上", "4 個傍晚"), ("彈性上班誘因", "彈性下班誘因"), ("提早出門", "提早下班")]


def evening(n):
    if isinstance(n, dict):
        return {k: evening(v) for k, v in n.items()}
    if isinstance(n, list):
        return [evening(v) for v in n]
    if isinstance(n, str):
        for a, b in WORDS:
            n = n.replace(a, b)
    return n


city, brief, limits = evening(city), evening(brief), evening(limits)

# ---------- 組合 ----------

meta = copy.deepcopy(T4["meta"])
meta.update(
    id="a1-evening", title="內科晚尖峰車流", subtitle=heatmap["subtitle"], region="內湖科技園區聯外出口",
    time_range={"start": cols[0]["label"], "end": cols[-1]["end"]}, updated_at="2026-10-20T12:00:00+08:00",
    sim=True, mock_method=MOCK_METHOD,
    disclaimer="本頁所有數字皆為模擬資料，出口位置為示意。本作品之建議不代表市府立場。",
)
for s in meta["sources"]:
    if s["id"] == "vd-live":
        s["period"] = "本檔未使用；傍晚的資料要用自己的電腦收（GitHub Actions 只收早上）"

doc = {"meta": meta, "heatmap": heatmap, "kpis": kpis, "decide": decide, "collective": collective,
       "scenario": scenario, "city": city, "brief": brief, "share": share, "limits": limits}
OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
