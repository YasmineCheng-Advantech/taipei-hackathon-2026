"""一行把收集到的 VD 接進熱力圖與錯峰情境：解壓 GitHub Actions 的 artifact、找出所有 csv、依序跑 4 個步驟。

用法（Mac／Linux 用 python3，Windows 用 py）
    python3 data/processed/build_real.py               # 讀 data/raw/ 底下所有 vd_taipei_targets.csv 與 vd-raw-*.zip
    python3 data/processed/build_real.py ~/Downloads   # 另外再找這個資料夾（例如瀏覽器下載的 artifact zip）
    python3 data/processed/build_real.py --dry-run     # 只列出找到哪些檔、幾天，不產生檔案

做的事（和 data/mock/README.md「換成真實資料時」的 4 行指令相同，外加 Demo 台詞檢查）
    0. 把 vd-raw-*.zip 解壓到 data/raw/actions/<zip 名稱>/（已解壓過就跳過）
    1. build_vd_15min.py     → data/processed/vd_15min.json
    2. build_model_input.py  → data/processed/model_input.json
    3. gen_t4_morning.py --real --model → data/processed/t4-morning.json
    4. validate.py           → 驗證契約
    5. check_demo.py         → 比對 PRODUCT.md 的 Demo 台詞
每一步失敗就停下來，印出是哪一步。

為什麼要這支：Windows 的命令列不會展開 data/raw/*/*.csv 這種萬用字元，手打很容易漏檔。
"""
import argparse
import csv
import subprocess
import sys
import zipfile
from pathlib import Path

DATA = Path(__file__).resolve().parents[1]
RAW = DATA / "raw"
NAME = "vd_taipei_targets.csv"


def unzip_all(dirs):
    for d in dirs:
        for z in sorted(d.glob("vd-raw-*.zip")):
            dest = RAW / "actions" / z.stem
            if dest.exists():
                continue
            dest.mkdir(parents=True)
            with zipfile.ZipFile(z) as f:
                for m in f.namelist():  # 只解出在 dest 底下的檔，不跟著 ../ 跑出去
                    if Path(m).is_absolute() or ".." in Path(m).parts:
                        continue
                    f.extract(m, dest)
            print(f"解壓 {z.name} → {dest.relative_to(DATA.parent)}")


def find_csvs(dirs):
    seen, out = set(), []
    for d in dirs:
        for p in sorted(d.rglob(NAME)):
            if p.resolve() not in seen:
                seen.add(p.resolve())
                out.append(p)
    return out


def days_in(paths):
    days = set()
    for p in paths:
        with open(p, encoding="utf-8") as f:
            for r in csv.DictReader(f):
                if r.get("collect_time"):
                    days.add(r["collect_time"][:10])
    return sorted(days)


def run(step, args):
    print(f"\n== {step} ==", flush=True)
    r = subprocess.run([sys.executable, *map(str, args)], cwd=DATA.parent)
    if r.returncode:
        sys.exit(f"\n✗ 停在「{step}」（結束碼 {r.returncode}）。上面是錯誤訊息。")


def main(argv):
    ap = argparse.ArgumentParser(description="把收集到的 VD 一次接進熱力圖")
    ap.add_argument("dirs", nargs="*", type=Path, help="另外要找 csv 與 zip 的資料夾")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    RAW.mkdir(exist_ok=True)
    dirs = [RAW, *(d.resolve() for d in args.dirs)]
    if args.dry_run:
        for d in dirs:
            for z in sorted(d.glob("vd-raw-*.zip")):
                done = "已解壓" if (RAW / "actions" / z.stem).exists() else "還沒解壓，正式執行時會解壓"
                print(f"zip：{z}（{done}）")
    else:
        unzip_all(dirs)
    csvs = find_csvs(dirs)
    if not csvs and not args.dry_run:
        sys.exit(f"找不到 {NAME}。先從 GitHub Actions 下載 vd-raw-*.zip 放進 data/raw/，步驟見 data/LOCAL.md")
    if not csvs:
        print(f"還沒有解壓好的 {NAME}")
        return 0
    days = days_in(csvs)
    print(f"找到 {len(csvs)} 個 csv，涵蓋 {len(days)} 天：{', '.join(days)}")
    for p in csvs:
        print(f"  {p}")
    if args.dry_run:
        return 0

    proc = DATA / "processed"
    run("1. 彙整成 15 分鐘格子", [proc / "build_vd_15min.py", *csvs])
    run("2. 估容量與到達曲線", [proc / "build_model_input.py", *csvs])
    run("3. 產生真實資料版 t4-morning.json",
        [DATA / "mock" / "gen_t4_morning.py", "--real", proc / "vd_15min.json", "--model", proc / "model_input.json"])
    run("4. 驗證契約", [DATA / "schema" / "validate.py", proc / "t4-morning.json"])
    run("5. 比對 Demo 台詞", [proc / "check_demo.py", proc / "t4-morning.json"])
    print(f"\n✓ 完成：data/processed/t4-morning.json（{len(days)} 天真實資料）。commit 這份與 vd_15min.json、model_input.json，原始檔不進 git。")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
