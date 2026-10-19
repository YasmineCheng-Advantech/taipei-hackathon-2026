"""產生 #4 內科晨峰的模擬資料 data/mock/t4-morning.json。

用法：python3 data/mock/gen_t4_morning.py

全部數字都是模擬值（sim: true），結果固定、可重跑。方法寫在輸出 JSON 的 `_mock.method`。
入口、數字與文字沿用 design/heatmap-canvas 的 Main、V2Today、V2City、Scenario、V2Brief 畫板，
讓網站照設計稿接上時畫面一致。
"""

import json
import math
from pathlib import Path

OUT = Path(__file__).with_name("t4-morning.json")

SIM = True


def tag(label, **fields):
    """每個帶數字的最小物件都附 label 與 sim。"""
    return {**fields, "label": label, "sim": SIM}


def g(t, p, w):
    return math.exp(-((t - p) ** 2) / (2 * w * w))


def hhmm(minutes):
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


# ---------- 熱力圖 ----------

HEAT_COLS = [hhmm(7 * 60 + 15 * i) for i in range(10)]  # 07:00–09:15，每格 15 分鐘，涵蓋 07:00–09:30

# coverage: observed＝之後會換成 VD 真實觀測；sim＝無公開偵測器，正式版仍用模擬；gap＝無偵測器，不補值
# lat/lng 為大略位置；mapX/mapY 是設計稿入口示意圖的百分比座標（離線版 SVG 用）
ENTRANCES = [
    dict(id="neihu-rd-1", name="內湖路一段", direction="由大直", coverage="observed", peak=6.4, sev=0.72, cap=820, lat=25.0830, lng=121.5620, mapX=12, mapY=35),
    dict(id="tiding-n", name="堤頂大道", direction="北向", coverage="observed", peak=6.8, sev=1.0, cap=1480, lat=25.0715, lng=121.5710, mapX=24, mapY=55),
    dict(id="minquan-br", name="民權大橋", direction="往內湖", coverage="observed", peak=6.2, sev=0.88, cap=1320, lat=25.0662, lng=121.5790, mapX=30, mapY=74),
    dict(id="macarthur-2", name="麥帥二橋", direction="往內湖", coverage="gap", lat=25.0590, lng=121.5860, mapX=46, mapY=86),
    dict(id="chengmei-br", name="成美橋", direction="往內湖", coverage="observed", peak=6.5, sev=0.95, cap=1120, lat=25.0575, lng=121.6005, mapX=60, mapY=88),
    dict(id="huandong", name="環東大道", direction="往內科", coverage="sim", peak=5.9, sev=0.82, cap=1400, lat=25.0640, lng=121.6150, mapX=74, mapY=78),
    dict(id="nh1-neihu-ic", name="國1 內湖交流道", direction="下匝道", coverage="sim", peak=5.5, sev=0.9, cap=900, lat=25.0735, lng=121.5960, mapX=84, mapY=62),
    dict(id="kangning-3", name="康寧路三段", direction="由汐止", coverage="sim", peak=5.1, sev=0.6, cap=700, lat=25.0740, lng=121.6120, mapX=90, mapY=30),
]

SPEED_THRESHOLDS = [50, 40, 30, 20, 10]  # km/h，由淺到深 6 級，低於 10 為最深
FLOW_THRESHOLDS = [400, 600, 800, 1000, 1200]  # 輛/15 分鐘，由淺到深 6 級


def heat_cell(i, e, t):
    if e["coverage"] == "gap":
        return tag("observed", speed=None, flow=None, gap=True)
    k = g(t, e["peak"], 1.7)
    jitter = ((i * 7 + t * 11) % 5) - 2
    speed = max(6, round(58 - 50 * e["sev"] * k + jitter))
    flow = round(e["cap"] * (0.42 + 0.58 * k) + jitter * 8)
    label = "observed" if e["coverage"] == "observed" else "assumed"
    return tag(label, speed=speed, flow=flow, gap=False)


rows = [
    tag(
        "assumed",
        id=e["id"], name=e["name"], direction=e["direction"], coverage=e["coverage"],
        vdIds=[],  # 待「盤點哪些路口有真實資料」填入
        lat=e["lat"], lng=e["lng"], coordsApprox=True, mapX=e["mapX"], mapY=e["mapY"],
    )
    for e in ENTRANCES
]
cells = [[heat_cell(i, e, t) for t in range(len(HEAT_COLS))] for i, e in enumerate(ENTRANCES)]

# 文湖線同時段負載（%，模擬）：尖峰接近滿載
mrt_load = [tag("assumed", time=c, pct=round(55 + 40 * g(t, 6.3, 2.0))) for t, c in enumerate(HEAT_COLS)]

# ---------- 重點數字 ----------

worst = min(
    ((cells[i][t]["speed"], i, t) for i in range(len(ENTRANCES)) for t in range(len(HEAT_COLS)) if not cells[i][t]["gap"]),
)
worst_speed, wi, wt = worst
n_obs = sum(e["coverage"] == "observed" for e in ENTRANCES)

kpis = [
    tag("computed", id="worst-cell", title="最塞的一格", value=worst_speed, unit="km/h",
        caption=f"{ENTRANCES[wi]['name']} {HEAT_COLS[wt]}，平均車速最低", rowId=ENTRANCES[wi]["id"], time=HEAT_COLS[wt]),
    tag("computed", id="peak-window", title="尖峰集中時段", value="08:30–09:15", unit=None,
        caption="半數以上入口低於 20 km/h"),
    tag("observed", id="coverage", title="偵測器覆蓋", value=n_obs, unit=f"/ {len(ENTRANCES)} 個入口",
        caption="其餘為模擬或缺口，格子另有標示"),
]

# ---------- 幫你決定（堤頂大道、09:00 前到） ----------

DECIDE_OPTS = [
    ("07:15", "07:24", 9, 70),
    ("07:30", "07:41", 11, 35),
    ("07:45", "07:59", 14, 12),
    ("08:00", "08:19", 19, 0),
    ("08:15", "08:41", 26, None),  # None＝尖峰時段不開放認領
    ("08:30", "09:01", 31, None),
]
decide = tag(
    "computed",
    entranceId="tiding-n",
    arriveBy="09:00",
    options=[
        tag("computed", depart=d, minutes=m, arrive=a, slotLeftPct=s, full=(s == 0), late=(a > "09:00"))
        for d, a, m, s in DECIDE_OPTS
    ],
    recommended="07:45",
    baseline=tag("assumed", depart="08:15", minutes=26, note="平常出門時間（使用者設定）"),
    minutesSaved=26 - 14,
    reason="07:45 出門還有名額，比平常少 12 分鐘，09:00 前到得了。建議每天早上產生一次後固定，只有事故或施工才更新。",
)

# ---------- 如果大家都這樣 ----------

collective = tag(
    "assumed",
    entranceId="tiding-n",
    cols=HEAT_COLS,
    modes=[
        tag("assumed", id="only-you", name="只有你這樣做", minutesDelta=-12, summary="你省很多，但路況幾乎不變。",
            levels=[0, 0, 1, 1, 2, 3, 4, 5, 5, 4]),
        tag("assumed", id="same-advice", name="大家都照同一建議", minutesDelta=-2, summary="07:30 變成新尖峰，大家只省一點點。",
            levels=[0, 1, 4, 5, 4, 3, 3, 4, 4, 3]),
        tag("assumed", id="by-slot", name="依名額分配", minutesDelta=-7, summary="尖峰被攤平，平均每人都省到時間。",
            levels=[0, 1, 2, 2, 2, 3, 3, 3, 3, 2]),
    ],
    claims=tag(
        "assumed",
        totalThisWeek=1284,
        slots=[
            tag("assumed", time="07:15", filledPct=30, full=False),
            tag("assumed", time="07:30", filledPct=65, full=False),
            tag("assumed", time="07:45", filledPct=88, full=False),
            tag("assumed", time="08:00", filledPct=100, full=True),
        ],
        note="認領數為模擬備援值；後端正常時網站改用真實人數。",
    ),
)

# ---------- 情境（堤頂大道北向單一瓶頸，預先算好） ----------

SC_COLS = [hhmm(7 * 60 + 15 * i) for i in range(14)]  # 07:00–10:15，涵蓋 07:00–10:30
CAP = 1000  # 輛/15 分鐘，模擬容量；區間 ±10%
PEAK_IDX = [6, 7, 8, 9]  # 08:30–09:15
TARGETS = {
    "early": dict(name="提早到 07:30–08:00", idx=[2, 3]),
    "late": dict(name="延後到 09:30–10:00", idx=[10, 11]),
}
base_demand = [round(CAP * (0.5 + 0.78 * g(t, 7, 1.8))) for t in range(len(SC_COLS))]


def run_queue(arr, cap):
    q, max_q, last, sum_q = 0.0, 0.0, -1, 0.0
    qs, cum_a, cum_d, a_tot = [], [], [], 0.0
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
    return dict(queue=qs, cumArrive=cum_a, cumDepart=cum_d, maxQueue=round(max_q), last=last, sumQueue=sum_q)


def clear_time(last):
    if last < 0:
        return None  # 不排隊
    return SC_COLS[last + 1] if last + 1 < len(SC_COLS) else "10:30"


def scenario_case(share_pct, target):
    s = share_pct / 100
    after = [float(v) for v in base_demand]
    moved = 0.0
    for i in PEAK_IDX:
        m = base_demand[i] * s
        after[i] -= m
        moved += m
    for i in TARGETS[target]["idx"]:
        after[i] += moved / len(TARGETS[target]["idx"])
    mid, lo, hi = run_queue(after, CAP), run_queue(after, CAP * 1.1), run_queue(after, CAP * 0.9)
    b_mid = run_queue(base_demand, CAP)
    new_peak = next((SC_COLS[i] for i in TARGETS[target]["idx"] if after[i] > CAP), None)
    delay = 0 if b_mid["sumQueue"] == 0 else round((mid["sumQueue"] - b_mid["sumQueue"]) / b_mid["sumQueue"] * 100)
    return tag(
        "computed",
        shiftPct=share_pct,
        target=target,
        demand=[round(v) for v in after],
        queue=mid["queue"],
        cumArrive=mid["cumArrive"],
        cumDepart=mid["cumDepart"],
        maxQueue=tag("computed", mid=mid["maxQueue"], low=lo["maxQueue"], high=hi["maxQueue"]),
        clearTime=tag("computed", mid=clear_time(mid["last"]), low=clear_time(lo["last"]), high=clear_time(hi["last"])),
        totalDelayChangePct=delay,
        newPeak=new_peak,
    )


baseline_run = run_queue(base_demand, CAP)
scenario = tag(
    "assumed",
    bottleneck=tag("assumed", entranceId="tiding-n", name="堤頂大道北向", capacityPer15min=CAP, capacityRangePct=10),
    cols=SC_COLS,
    slider=tag("assumed", min=0, max=50, step=5, default=5, unit="%"),
    targets=[{"id": k, "name": v["name"], "cols": [SC_COLS[i] for i in v["idx"]]} for k, v in TARGETS.items()],
    shiftFrom=[SC_COLS[i] for i in PEAK_IDX],
    reference=tag("observed", name="檀香山 1988 實際參與", low=6, high=7, unit="%", source="Giuliano & Golob，TRR 1280（1990）"),
    baseline=tag(
        "computed",
        demand=base_demand,
        queue=baseline_run["queue"],
        cumArrive=baseline_run["cumArrive"],
        cumDepart=baseline_run["cumDepart"],
        maxQueue=baseline_run["maxQueue"],
        clearTime=clear_time(baseline_run["last"]),
    ),
    cases=[scenario_case(p, t) for t in TARGETS for p in range(0, 51, 5)],
)

# ---------- 城市行動 ----------

city = tag(
    "assumed",
    target=tag("computed", low=3000, high=4500, unit="人", goal="讓堤頂大道早上排隊減半",
               note="由排隊模型推估的區間，不是保證值；正式值由排隊模型腳本產出"),
    claimed=tag("assumed", value=1284, unit="人", period="本週"),
    slots=collective["claims"]["slots"],
    slotNote="08:00 已滿，系統開始把人推薦到 07:15 和 07:30，避免形成新尖峰。",
    actions=[
        tag("assumed", id="flex", title="企業彈性上班誘因", depts=["交通局", "產發局"],
            why="要讓排隊減半，光靠個人不夠，需要整間公司一起調整上班時間。",
            forYou="你的公司加入，你才真的能每天錯峰。", cost=None, costNote="誘因預算，待推估", supporters=412),
        tag("assumed", id="care", title="幼兒園提早到 07:30 收托", depts=["教育局"],
            why="設定中選「只能延後」的人，最常見的原因是早上要送小孩。",
            forYou="要接送小孩的家長也能提早出門。", cost=None, costNote="人力成本，待推估", supporters=268),
        tag("assumed", id="shuttle", title="捷運站接駁車 07:15 起加班", depts=["公運處"],
            why="提早出門的人改搭捷運後，最後一段到公司的接駁車還沒開。",
            forYou="提早出門也有車可以搭。", cost=None, costNote="加班車成本，待推估", supporters=193),
        tag("assumed", id="signal", title="堤頂大道路口早上號誌調整", depts=["交工處"],
            why="熱力圖上 08:30–09:00 最深的格子集中在這裡。",
            forYou="就算不能改時間，也少塞一點。", cost=None, costNote="低（調整既有號誌時制）", supporters=157),
    ],
    disclaimer="以上是本作品依資料提出的建議，不代表市府已經承諾。",
)

# ---------- 協商一頁紙 ----------

brief = tag(
    "assumed",
    company="[企業名稱]",
    entranceShare=[
        tag("assumed", entranceId="tiding-n", pct=42),
        tag("assumed", entranceId="minquan-br", pct=31),
        tag("assumed", entranceId="chengmei-br", pct=27),
    ],
    entranceShareNote="員工經過各入口的比例為假設，正式版用員工通勤調查或認領資料。",
    conclusion=tag(
        "computed",
        text="貴公司若讓一半員工改 08:00 前到，員工平均每天通勤少 6–10 分鐘，堤頂大道 08:30 的排隊可縮短約 15–25%。",
        minutesSavedLow=6, minutesSavedHigh=10, queueCutLowPct=15, queueCutHighPct=25,
    ),
    options=[
        tag("computed", id="A", name="維持現況", minutesSavedLow=0, minutesSavedHigh=0, queueChangeLowPct=None, queueChangeHighPct=None, opsCost="無"),
        tag("computed", id="B", name="三成員工改 08:00 前到", minutesSavedLow=3, minutesSavedHigh=5, queueChangeLowPct=-12, queueChangeHighPct=-8,
            opsCost="共同會議時段由 09:00–18:00 縮為 09:30–17:00"),
        tag("computed", id="C", name="分兩批：一半 08:00、一半 09:30", minutesSavedLow=6, minutesSavedHigh=10, queueChangeLowPct=-25, queueChangeHighPct=-15,
            opsCost="共同會議時段 10:00–16:30；對外客服需排班"),
    ],
    cityRoles=[
        {"depts": ["交通局", "產發局"], "offer": "參與企業的錯峰成果可計入綠運輸 ESG 指標；[誘因方案待定]"},
        {"depts": ["教育局"], "offer": "內科周邊幼兒園提早到 07:30 收托，讓有接送需求的員工也能參與"},
        {"depts": ["公運處"], "offer": "07:15 起加開捷運站接駁車"},
        {"depts": ["交工處"], "offer": "試辦期間調整堤頂大道早上號誌時制"},
    ],
    pilot=tag(
        "assumed",
        weeks=4, baselineWeeks=2,
        control="參與企業 vs. 同入口未參與企業",
        metrics=["門禁刷卡到達時間分布", "入口 VD 排隊消散時間", "員工通勤時間自評"],
        interference="記錄施工、連假、颱風、開學日，分析時排除",
        stopRule="第 2 週參與率低於 [門檻]，或新時段排隊比基準期更長",
    ),
    publicOpinion=[
        tag("assumed", id="claims", value=1284, caption="本週認領錯峰時段的人數"),
        tag("assumed", id="flex-supporters", value=412, caption="支持「企業彈性上班誘因」的人數"),
        tag("observed", id="petitions", value=None, caption="「市長，你給我聽好了」內湖交通陳情則數（彙總，不含原文）", note="待主辦方資料"),
    ],
    disclaimer="本文件為黑客松作品之建議，不代表市府立場。",
)

# ---------- 組合 ----------

doc = {
    "topicId": "t4-morning",
    "_mock": {
        "sim": SIM,
        "generatedBy": "data/mock/gen_t4_morning.py",
        "method": [
            "全部數字為模擬，沿用 design/heatmap-canvas 設計稿的入口與數字，方便網站照稿接上。",
            "熱力圖：每個入口以高斯曲線組出車速與流量，尖峰設在 08:30–08:45（依交通局 2015 年「82% 集中在 9 時」、壅塞 8:30–9:30），再加固定擾動；同參數重跑結果相同。",
            "label 依正式版的資料性質標：有 VD 的入口標 observed、無偵測器的入口標 assumed，但全部 sim: true，網站應加斜線紋路。",
            "麥帥二橋為缺口（gap: true），值為 null，不補值。",
            "情境：堤頂大道北向單一瓶頸，容量 1,000 輛/15 分鐘（±10%）為假設；把 08:30–09:15 的需求按比例移到提早或延後時段，用確定性排隊模型算排隊長度、消散時間與總延誤。正式版由網站工程師的排隊模型腳本以 model_input.json 重算。",
            "認領人數、支持數為模擬備援值。",
        ],
    },
    "meta": tag(
        "assumed",
        title="內科晨峰車流",
        subtitle="平日 07:00–09:30 · 每 15 分鐘 · 流入內湖",
        region="臺北市內湖區（內湖科技園區聯外入口）",
        timeRange={"start": "07:00", "end": "09:30", "days": "平日"},
        binMinutes=15,
        units={"speed": "km/h", "flow": "輛/15 分鐘"},
        sources=[
            {"name": "縣市即時路況（VD 每 5 分鐘統計）", "url": "https://data.gov.tw/dataset/166031", "kind": "observed", "used": False},
            {"name": "臺北市車輛偵測器（VD）靜態資料", "url": "https://data.taipei/dataset/detail?id=47cb9090-e1c9-4b1d-b299-b11c375c5ee2", "kind": "observed", "used": False},
            {"name": "交通局 2015 年內湖上班時間調查", "url": "https://dot.gov.taipei/News_Content.aspx?n=42F54DDC552218AD&sms=051295A13C5CC507&s=6B82592FD161ADB6", "kind": "observed", "used": True},
            {"name": "本作品模擬資料", "url": None, "kind": "sim", "used": True},
        ],
        updatedAt="2026-10-19T12:00:00+08:00",
    ),
    "heatmap": tag(
        "assumed",
        rows=rows,
        cols=HEAT_COLS,
        layers=[
            tag("assumed", id="speed", name="壅塞（車速）", unit="km/h", thresholds=SPEED_THRESHOLDS, worse="lower"),
            tag("assumed", id="flow", name="需求（流量）", unit="輛/15 分鐘", thresholds=FLOW_THRESHOLDS, worse="higher"),
        ],
        defaultLayer="speed",
        cells=cells,
        mrtLoad=tag("assumed", name="文湖線負載", unit="%", values=mrt_load),
    ),
    "kpis": kpis,
    "decide": decide,
    "collective": collective,
    "scenario": scenario,
    "city": city,
    "brief": brief,
}

OUT.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
print(f"wrote {OUT} ({OUT.stat().st_size:,} bytes)")
