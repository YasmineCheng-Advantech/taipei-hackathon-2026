#!/usr/bin/env python3
"""檢查題目 JSON 是否符合資料契約。

用法：python3 data/schema/validate.py data/mock/*.json
需要 jsonschema（pip install jsonschema）。全部通過時結束碼為 0。
"""
import json
import re
import sys
from pathlib import Path

from jsonschema import Draft202012Validator
from jsonschema.exceptions import best_match

SCHEMA = Path(__file__).with_name("topic.schema.json")


def walk(node, path="$"):
    """逐一走過所有物件，回傳 (路徑, 物件)。"""
    if isinstance(node, dict):
        yield path, node
        for k, v in node.items():
            yield from walk(v, f"{path}.{k}")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            yield from walk(v, f"{path}[{i}]")


def cross_checks(d):
    """JSON Schema 表達不了的檢查：數量對齊、id 參照、sim 一致。"""
    errs = []
    hm, dc, co, sc, br = d["heatmap"], d["decide"], d["collective"], d["scenario"], d["brief"]
    rows = [r["id"] for r in hm["rows"]]
    cols = [c["id"] for c in hm["cols"]]
    layers = [l["id"] for l in hm["layers"]]
    sources = [s["id"] for s in d["meta"]["sources"]]

    def need(cond, msg):
        if not cond:
            errs.append(msg)

    def unique(ids, where):
        need(len(ids) == len(set(ids)), f"{where}：id 重複")

    unique(rows, "heatmap.rows")
    unique(cols, "heatmap.cols")
    unique(layers, "heatmap.layers")
    unique(sources, "meta.sources")

    need(hm["default_layer"] in layers, f"heatmap.default_layer「{hm['default_layer']}」不在 layers 裡")
    for l in hm["layers"]:
        need(len(l["cells"]) == len(rows), f"heatmap.layers[{l['id']}].cells 有 {len(l['cells'])} 列，rows 有 {len(rows)} 列")
        for i, line in enumerate(l["cells"]):
            need(len(line) == len(cols), f"heatmap.layers[{l['id']}].cells[{i}] 有 {len(line)} 格，cols 有 {len(cols)} 格")
        t = l["thresholds"]
        need(t == sorted(t) or t == sorted(t, reverse=True), f"heatmap.layers[{l['id']}].thresholds 必須依序排列")
    if "aux" in hm:
        need(len(hm["aux"]["values"]) == len(cols), "heatmap.aux.values 數量要等於 cols")

    for k in d["kpis"]:
        ref = k.get("ref", {})
        need(ref.get("row", rows[0]) in rows and ref.get("col", cols[0]) in cols, f"kpis[{k['id']}].ref 指到不存在的格子")

    for r in dc["setup"]["rows"]:
        need(r in rows, f"decide.setup.rows：「{r}」不在 heatmap.rows 裡")
    for i, p in enumerate(dc["plans"]):
        opts = [o["id"] for o in p["options"]]
        unique(opts, f"decide.plans[{i}].options")
        need(p["row"] in rows, f"decide.plans[{i}].row「{p['row']}」不在 heatmap.rows 裡")
        need(p["recommended"] in opts, f"decide.plans[{i}].recommended 不在 options 裡")
        need(p["baseline"] in opts, f"decide.plans[{i}].baseline 不在 options 裡")
    deadlines = dc["setup"].get("deadlines")
    for r in dc["setup"]["rows"]:
        for dl in deadlines or [None]:
            need(any(p["row"] == r and p.get("deadline") == dl for p in dc["plans"]),
                 f"decide.plans 缺少 {r}" + (f" × {dl}" if dl else "") + " 的那一份")

    ccols = co.get("cols", cols)
    for c in ccols:
        need(c in cols, f"collective.cols：「{c}」不在 heatmap.cols 裡")
    if "layer" in co:
        need(co["layer"] in layers, "collective.layer 不在 heatmap.layers 裡")
    need(sorted(m["id"] for m in co["modes"]) == ["same", "solo", "split"], "collective.modes 必須剛好是 solo、same、split 各一")
    for m in co["modes"]:
        need(len(m["curve"]) == len(ccols), f"collective.modes[{m['id']}].curve 數量要等於 collective.cols")
        for h in m.get("highlight", []):
            need(h in ccols, f"collective.modes[{m['id']}].highlight：「{h}」不在 collective.cols 裡")

    scols = [c["id"] for c in sc["cols"]]
    unique(scols, "scenario.cols")
    for c in sc.get("peak_cols", []):
        need(c in scols, f"scenario.peak_cols：「{c}」不在 scenario.cols 裡")
    targets = [t["id"] for t in sc["targets"]]
    for t in sc["targets"]:
        for c in t["cols"]:
            need(c in scols, f"scenario.targets[{t['id']}].cols：「{c}」不在 scenario.cols 裡")
    s = sc["slider"]
    steps = []
    v = s["min"]
    while v <= s["max"] + 1e-9:
        steps.append(round(v, 6))
        v += s["step"]
    have = {(r["target"], round(r["shift"], 6)) for r in sc["results"]}
    missing = [f"{t}:{x}" for t in targets for x in steps if (t, x) not in have]
    need(not missing, f"scenario.results 缺少 {len(missing)} 組：{', '.join(missing[:6])}{' …' if len(missing) > 6 else ''}")
    need(s["default"] in steps, "scenario.slider.default 不在滑桿刻度上")
    for name, r in [("baseline", sc["baseline"])] + [(f"results[{r.get('target')}:{r.get('shift')}]", r) for r in sc["results"]]:
        for key in ("cum_arrive", "cum_depart", "queue", "queue_diff"):
            if key in r:
                need(len(r[key]) == len(scols), f"scenario.{name}.{key} 數量要等於 scenario.cols")
        if r.get("new_peak") is not None:
            need(r["new_peak"] in scols, f"scenario.{name}.new_peak 不在 scenario.cols 裡")

    ex = br.get("exposure")
    if ex:
        for c in ex["cols"]:
            need(c in cols, f"brief.exposure.cols：「{c}」不在 heatmap.cols 裡")
        for r in ex["rows"]:
            need(r["row"] in rows, f"brief.exposure.rows：「{r['row']}」不在 heatmap.rows 裡")
            need(len(r["cells"]) == len(ex["cols"]), f"brief.exposure.rows[{r['row']}].cells 數量要等於 exposure.cols")

    for l in hm["layers"]:
        for i, line in enumerate(l["cells"]):
            for j, c in enumerate(line):
                where = f"heatmap.layers[{l['id']}].cells[{i}][{j}]"
                if "lo" in c:
                    need(c["lo"] <= c["v"] <= c["hi"], f"{where}：v 要介於 lo 與 hi 之間")
                if "bad_days" in c:
                    need("bad_at" in l, f"{where}：有 bad_days，但圖層沒有 bad_at")
                    need(c["bad_days"] <= c.get("days", 0), f"{where}：bad_days 不能大於 days")

    setup = dc["setup"]
    action_ids = [a["id"] for a in d["city"]["actions"]]
    unique(action_ids, "city.actions")
    # rows 也能當彙總來源（「從哪裡進內湖」），用 setup.rows 的 id 當作選項
    groups = {"origins": setup.get("origins", []), "constraints": setup.get("constraints", []),
              "rows": [{"id": r} for r in setup.get("rows", [])]}
    for name, items in groups.items():
        unique([x["id"] for x in items], f"decide.setup.{name}")
    for o in groups["origins"]:
        for r in o["rows"]:
            need(r in setup["rows"], f"decide.setup.origins[{o['id']}].rows：「{r}」不在 setup.rows 裡")
    for c in groups["constraints"]:
        for a in c.get("actions", []):
            need(a in action_ids, f"decide.setup.constraints[{c['id']}].actions：「{a}」不在 city.actions 裡")
    for b in d["city"].get("breakdowns", []):
        keys = [x["id"] for x in groups[b["source"]]]
        for it in b["items"]:
            # 自己取 id 的彙總欄（「其他」「沒填」）要用 label 寫出畫面要顯示的字
            need(it["key"] in keys or it.get("label"),
                 f"city.breakdowns[{b['id']}]：「{it['key']}」不在 decide.setup.{b['source']} 裡，也沒有 label")

    sh = d.get("share")
    if sh:
        for pl in sh.get("places", []):
            if "row" in pl:
                need(pl["row"] in rows, f"share.places[{pl['id']}].row「{pl['row']}」不在 heatmap.rows 裡")
        for t in sh["templates"]:
            used = set(re.findall(r"\{(\w+)\}", t["text"]))
            need(used == set(t["needs"]), f"share.templates[{t['id']}]：text 用到 {sorted(used)}，needs 寫的是 {sorted(t['needs'])}")
            need("origin" not in used or groups["origins"], f"share.templates[{t['id']}]：用到 origin，但沒有 decide.setup.origins")
            need("constraint" not in used or groups["constraints"],
                 f"share.templates[{t['id']}]：用到 constraint，但沒有 decide.setup.constraints")

    # 人數不放模擬值：截圖會讓斜線紋路消失，看起來像真的民意
    heads = [("city.claimed", d["city"]["claimed"]), ("collective.claims.total", co["claims"].get("total"))]
    heads += [(f"city.breakdowns[{b['id']}][{it['key']}]", it["count"])
              for b in d["city"].get("breakdowns", []) for it in b["items"]]
    heads += [(f"city.actions[{a['id']}].support", a["support"]) for a in d["city"]["actions"]]
    heads += [(f"brief.public[{i}].value", x["value"]) for i, x in enumerate(br.get("public", []))]
    for p, v in heads:
        if v and v.get("unit") == "人":
            need(v.get("pending") or not v.get("sim"), f"{p}：人數不能放模擬值，請改成 pending: true（網站顯示「尚無資料」）")

    for p, obj in walk(d):
        if "src" in obj and isinstance(obj["src"], str):
            need(obj["src"] in sources, f"{p}.src「{obj['src']}」不在 meta.sources 裡")
        if d["meta"]["sim"] and obj.get("sim") is False:
            need(False, f"{p}：meta.sim 為 true，這裡的 sim 卻是 false")
    return errs


def describe(e):
    """oneOf 失敗時改報最接近的那個原因，例如缺 label。"""
    if e.validator == "oneOf" and e.context:
        e = best_match(e.context)
    return f"{e.json_path}：{e.message}"


def main(paths):
    if not paths:
        print(__doc__.strip())
        return 2
    validator = Draft202012Validator(json.loads(SCHEMA.read_text(encoding="utf-8")))
    failed = 0
    for path in paths:
        try:
            data = json.loads(Path(path).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"✗ {path}\n  讀不到或不是合法 JSON：{e}")
            failed += 1
            continue
        errs = [describe(e) for e in validator.iter_errors(data)]
        if not errs:
            errs = cross_checks(data)
        if errs:
            failed += 1
            print(f"✗ {path}（{len(errs)} 個問題）")
            for e in errs[:30]:
                print(f"  - {e}")
        else:
            print(f"✓ {path}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
