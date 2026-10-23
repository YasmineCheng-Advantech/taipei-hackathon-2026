"""下載傷亡道路交通事故逐案資料（全國，zip），解壓後印出每個檔的欄位與筆數，並把臺北市的列另存一份。

check_catalog.py 只抓開頭 2 MB，zip 打不開，所以另外用這支抓完整的檔。做法見 docs/topics/crash.md。

用法（在自己的電腦）：
    python3 data/fetch/fetch_accidents.py                  # 預設 114 年（data.gov.tw 177136）
    python3 data/fetch/fetch_accidents.py 177136 167905    # 多個年度
    python3 data/fetch/fetch_accidents.py ~/Downloads/xxx.zip   # 用瀏覽器下載好的檔
輸出（都在 data/raw/accident/，不進 git）：
    <編號>_<n>.zip 或 .csv          原始檔；已經下載過的不會重抓
    taipei_<原始檔名>_<k>.csv       臺北市的列（任一欄以「臺北市」或「台北市」開頭），UTF-8，一個 CSV 一份
注意
- 檔案可能上百 MB，下載要幾分鐘。
- 逐案資料可能一個當事者一列，同一件事故有好幾列；算件數前要先依案件編號（或時間＋地點）合併。
- 臺北市的列只放在 data/raw/，不進 git；畫面上只放彙總到路口的件數（見 docs/topics/README.md「隱私」）。
"""
import csv
import io
import shutil
import sys
import urllib.request
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from check_catalog import SSL_CTX, gov_tw_urls  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "raw" / "accident"
TAIPEI = ("臺北市", "台北市")
SHOW = ("時間", "日期", "地點", "經度", "緯度")  # 範例只印這幾類欄位，用來看路口文字長什麼樣子


def download(url, stem):
    """下載到 OUT/<stem>.zip（或 .csv）；已經有就跳過。"""
    done = [p for p in OUT.glob(f"{stem}.*") if p.suffix != ".part"]
    if done:
        print(f"  已下載過：{done[0].name}")
        return done[0]
    req = urllib.request.Request(url, headers={"User-Agent": "taipei-hackathon-2026 accident fetch"})
    tmp = OUT / f"{stem}.part"
    with urllib.request.urlopen(req, timeout=120, context=SSL_CTX) as r, open(tmp, "wb") as f:
        shutil.copyfileobj(r, f, 1024 * 1024)
    path = OUT / f"{stem}.{'zip' if zipfile.is_zipfile(tmp) else 'csv'}"
    tmp.rename(path)
    print(f"  下載完成：{path.name}，{path.stat().st_size / 1024 / 1024:,.1f} MB")
    return path


def member_name(info):
    """zip 裡的中文檔名常是 Big5，沒標 UTF-8 時 Python 會當成 cp437 解成亂碼，換回來。"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("cp950")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return info.filename


def csv_files(path):
    """回傳 [(顯示名稱, 開檔函式)]：zip 裡的每個 CSV，或檔案本身就是 CSV。"""
    if zipfile.is_zipfile(path):
        z = zipfile.ZipFile(path)
        return [(member_name(i), lambda i=i: z.open(i)) for i in z.infolist() if i.filename.lower().endswith(".csv")]
    return [(path.name, lambda: open(path, "rb"))]


def encoding_of(head):
    """政府的 CSV 常是 Big5（cp950），也可能是 UTF-8 加 BOM。只看到最後一個換行，避免切到半個中文字。"""
    head = head[: head.rfind(b"\n") + 1] or head
    try:
        head.decode("utf-8-sig")
        return "utf-8-sig"
    except UnicodeDecodeError:
        return "cp950"


def scan(name, opener, out):
    with opener() as f:
        enc = encoding_of(f.read(65536))
    total = kept = 0
    examples = []
    with opener() as f, open(out, "w", newline="", encoding="utf-8") as o:
        rows = csv.reader(io.TextIOWrapper(f, encoding=enc, errors="replace", newline=""))
        header = next(rows, [])
        w = csv.writer(o)
        w.writerow(header)
        show = [i for i, h in enumerate(header) if any(k in h for k in SHOW)]
        for row in rows:
            total += 1
            if any(c.strip().startswith(TAIPEI) for c in row):
                kept += 1
                w.writerow(row)
                if len(examples) < 3:
                    examples.append(" | ".join(row[i] for i in show if i < len(row)))
    print(f"  {name}（{enc}）：{total:,} 列，臺北市 {kept:,} 列")
    print(f"    欄位（{len(header)}）：{', '.join(header)}")
    if kept:
        print(f"    臺北市存在：{out}")
        for e in examples:
            print(f"    範例：{e}")
    else:
        out.unlink()
        print("    沒有任何一欄以「臺北市」開頭：縣市可能是代碼，看上面的欄位找出縣市欄，再告訴 Claude 怎麼篩")


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")  # Windows 命令列預設 cp950
    csv.field_size_limit(10 * 1024 * 1024)
    OUT.mkdir(parents=True, exist_ok=True)
    files = []
    for arg in sys.argv[1:] or ["177136"]:
        if Path(arg).expanduser().exists():
            files.append(Path(arg).expanduser())
            continue
        print(f"資料集 {arg}：https://data.gov.tw/dataset/{arg}")
        try:
            urls = gov_tw_urls(arg)
        except Exception as e:
            print(f"✗ 查不到下載網址：{e}\n  改用瀏覽器下載，再把檔案路徑傳給這支程式")
            continue
        for n, url in enumerate(urls, 1):
            try:
                files.append(download(url, f"{arg}_{n}"))
            except Exception as e:
                print(f"✗ 下載失敗：{e}\n  {url}")
    for path in files:
        print(f"\n{path.name}")
        for k, (name, opener) in enumerate(csv_files(path), 1):
            try:
                scan(name, opener, OUT / f"taipei_{path.stem}_{k}.csv")
            except Exception as e:
                print(f"✗ {name}：{e}")
    print("\n把上面的輸出（欄位與範例）貼給 Claude，下一步是彙總成路口 × 時段。")
    return 0 if files else 1


if __name__ == "__main__":
    sys.exit(main())
