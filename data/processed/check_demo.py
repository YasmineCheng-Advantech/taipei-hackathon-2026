"""檢查 PRODUCT.md「兩分鐘 Demo」的台詞，和資料檔算出來的數字對不對得上，並印出照資料改寫的台詞。

用法：python3 data/processed/check_demo.py [資料檔]
      預設讀 data/processed/t4-morning.json（真實資料版）；還沒產生時讀 data/mock/t4-morning.json。
      真實資料版的產生方式見 data/mock/README.md「換成真實資料時」。

台詞寫在下面的 SCRIPT，是 10/19 依模擬資料寫的；PRODUCT.md 的台詞改了，這裡也要一起改。
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT = [ROOT / "processed" / "t4-morning.json", ROOT / "mock" / "t4-morning.json"]

# PRODUCT.md 的台詞裡用到的數字
SCRIPT = dict(worst_row="minquan-br", worst_col="07:00", bad_days=1, days=18, need=(4, 13),
              shift_window="08:30–09:15", top_assumptions={"尖峰有多高", "道路容量（一次能過多少車）"})


def main(argv):
    path = Path(argv[0]) if argv else next((p for p in DEFAULT if p.exists()), DEFAULT[-1])
    d = json.loads(path.read_text(encoding="utf-8"))
    hm, sc, city = d["heatmap"], d["scenario"], d["city"]
    rows = {r["id"]: r for r in hm["rows"]}
    cols = {c["id"]: c["label"] for c in hm["cols"]}
    speed = next(l for l in hm["layers"] if l["id"] == "speed")
    kp = {k["id"]: k for k in d["kpis"]}
    worst = kp["worst-cell"]
    wr, wc = worst["ref"]["row"], cols[worst["ref"]["col"]]
    wcell = speed["cells"][list(rows).index(wr)][list(cols).index(worst["ref"]["col"])]
    real_cells = sum(1 for line in speed["cells"] for c in line if c.get("sim") is False)
    all_cells = sum(1 for line in speed["cells"] for c in line if not c.get("gap"))
    need = city["goal"]["need"]
    shift = f"{sc['cols'][[c['id'] for c in sc['cols']].index(sc['peak_cols'][0])]['label']}–" \
            f"{sc['cols'][[c['id'] for c in sc['cols']].index(sc['peak_cols'][-1])]['label']}"
    top2 = {i["name"] for i in sc["sensitivity"]["items"][:2]}
    new_peak = [r["shift"] for r in sc["results"] if r["target"] == "early" and r.get("new_peak")]
    name = rows[wr]["name"]
    qsim = need.get("sim") is not False  # 排隊模型的數字是不是模擬
    tag = "（模擬）" if qsim else ""

    checks = [
        ("最塞的一格", f"{rows[SCRIPT['worst_row']]['name']} {SCRIPT['worst_col']}", f"{name} {wc}（{worst['value']} km/h）",
         (wr, wc) == (SCRIPT["worst_row"], SCRIPT["worst_col"])),
        ("那一格幾天會塞", f"{SCRIPT['days']} 天裡有 {SCRIPT['bad_days']} 天", f"{wcell.get('days', '?')} 天裡有 {wcell.get('bad_days', '?')} 天",
         (wcell.get("days"), wcell.get("bad_days")) == (SCRIPT["days"], SCRIPT["bad_days"])),
        ("那一格是真實資料", "是", "是" if wcell.get("sim") is False else "否（模擬）", wcell.get("sim") is False),
        ("排隊減半要移出", f"{SCRIPT['need'][0]}–{SCRIPT['need'][1]}%", f"{need.get('lo')}–{need.get('hi')}%{tag}",
         (need.get("lo"), need.get("hi")) == SCRIPT["need"]),
        ("移出哪個時段的車", SCRIPT["shift_window"], shift, shift == SCRIPT["shift_window"]),
        ("最影響結論的兩個假設", "、".join(sorted(SCRIPT["top_assumptions"])), "、".join(sorted(top2)), top2 == SCRIPT["top_assumptions"]),
        ("全擠到同一時段會形成新尖峰", "會", f"會（移出 {min(new_peak)}% 起）" if new_peak else "不會", bool(new_peak)),
    ]
    print(f"資料檔：{path}（{'含真實資料' if not d['meta']['sim'] else '全部是模擬'}；熱力圖車速 {real_cells}/{all_cells} 格是真實觀測）\n")
    w = max(len(c[0]) for c in checks)
    for title, said, got, ok in checks:
        print(f"{'✓' if ok else '✗'} {title:{w}}  台詞：{said}　資料：{got}")
    bad = sum(not c[3] for c in checks)
    print(f"\n{len(checks) - bad}/{len(checks)} 項對得上。" + ("台詞照資料改成：" if bad else "台詞不用改。"))
    if qsim and not d["meta"]["sim"]:
        print("\n注意：排隊減半、移出時段、最影響的假設、新尖峰這 4 項的數字來自模擬的排隊模型（真實資料算不出排隊，"
              "見 build_model_input.py 的警告）。對得上只代表台詞和模擬一致，不代表真實數據支持；Demo 講到時要說是模擬。")
    if bad:
        src = "這些格子是臺北市偵測器的真實資料" if wcell.get("sim") is False else "這一格目前還是模擬資料"
        print(f"\n1. 熱力圖：「早上 {wc}，{name} {wcell.get('days')} 天裡有 {wcell.get('bad_days')} 天低於 20 km/h。"
              f"{src}；沒有偵測器的地方我們留白，不補數字。」")
        tops = "』和『".join(i["name"].split("（")[0] for i in sc["sensitivity"]["items"][:2])
        why = "區間這麼寬，是因為結論" if need.get("hi", 0) - need.get("lo", 0) >= 5 else "這個數字"
        print(f"2. 錯峰情境：「{'（以下是模擬）' if qsim else ''}要讓排隊減半，{shift} 經過的車要移出約 {need.get('lo')}–{need.get('hi')}%。"
              f"{why}最受『{tops}』影響，這張圖把它攤開來。"
              + ("如果大家全擠到同一個時段，那裡就會變成新尖峰。」" if new_peak else "」"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
