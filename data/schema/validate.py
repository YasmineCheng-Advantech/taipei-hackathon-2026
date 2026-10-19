#!/usr/bin/env python3
"""檢查題目 JSON 是否符合資料契約。

用法：python3 data/schema/validate.py data/mock/*.json
需要 jsonschema（pip install jsonschema）。全部通過時結束碼為 0。
"""
import json
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
