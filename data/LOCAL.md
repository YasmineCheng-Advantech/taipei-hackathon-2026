# 在自己的電腦上做資料

Oct 22, 2026 · 雲端環境連不到政府網站，還沒做完的資料工作要在自己的電腦上跑。以 Mac 為主；Windows 的差異寫在最後。

## 先講結論：資料收集沒有中斷

收集程式是在 **GitHub Actions** 上跑的，換電腦不影響。目前收到：

| 日期 | 從幾點開始收 | 狀態 |
| --- | --- | --- |
| 10/20（一） | 07:21 | ✅ 有資料（07:00–07:20 沒收到） |
| 10/21（二） | 07:11 | ✅ 有資料 |
| 10/22（三） | 06:46 | ✅ 有資料 |
| 10/23（四） | — | ⚠️ **明天早上 07:00 前要啟動**（見下面） |

10/19 是盤點日，只抓了 3 次。所以真實資料最多是 **4 個平日**（10/20–10/23），不是 5 個。

**為什麼要手動啟動：** GitHub 的排程常常延遲 1–2 小時（10/21、10/22 的排程都到 07:50 左右才開始），前幾天能從 07:00 前開始收，都是因為有人手動按了啟動。明天沒人按的話，07:00–08:00 的資料會缺。

明天兩件都做，互為備援（同一筆讀數重複收到，彙整時會自動去掉）：

1. **GitHub 手動啟動**（手機就能按）：repo → **Actions** → 左邊選 **collect-vd** → 右邊 **Run workflow** → 分支選 `master` → **Run workflow**。10:30 後那次執行的 **Artifacts** 有一個約 6 MB 的 `vd-raw-…` 就是成功。
2. **Mac 本機也收一份**：今晚睡前在 repo 資料夾執行，Mac 接上電源、不要闔上螢幕：
   ```
   caffeinate -is python3 data/fetch/collect_vd.py --today
   ```
   `--today` 會等到 07:00 才開始抓，10:30 後自己結束。資料寫在 `data/raw/vd_taipei_targets.csv`，進度看 `data/raw/collect.log`。

## 0. 先看 Mac 上原本的資料還在不在

這台電腦之前跑過收集程式，`data/raw/` 裡可能已經有幾天的資料：

```
ls data/raw/
tail -3 data/raw/collect.log
ps aux | grep collect_vd | grep -v grep
```

- `ps` 有印出東西：收集程式還在跑，不用動它。
- `data/raw/vd_taipei_targets.csv` 存在：下面第 2 步會自動一起讀進來，和 GitHub 的資料合併。

## 1. 準備（只要做一次）

```
python3 -m pip install jsonschema
```

## 2. 把真實資料接進熱力圖（10/23 10:30 之後，約 15 分鐘）

1. **下載資料：** GitHub → Actions → collect-vd，把 10/20–10/23 每天**成功**的那次執行點開，在最下面的 **Artifacts** 下載 `vd-raw-…`（每個約 6 MB 的 zip），放在「下載項目」就好，**不用解壓**。

   | 日期 | 下載這次執行 |
   | --- | --- |
   | 10/20 | 10/20 07:21 啟動的那次（`workflow_dispatch`） |
   | 10/21 | 10/21 07:11 啟動的那次 |
   | 10/22 | 10/22 06:46 啟動的那次 |
   | 10/23 | 明天手動啟動的那次 |

   同一天其他的執行（標 `cancelled`，或啟動後立刻結束、只有 1 KB 的）不用下載。Safari 會自動解壓 zip；解壓了也沒關係，程式會找資料夾裡的 csv。
2. **一行跑完：**
   ```
   python3 data/processed/build_real.py ~/Downloads --dry-run
   python3 data/processed/build_real.py ~/Downloads
   ```
   第一行只列出找到哪些 zip 與 csv，確認 4 天都在；第二行會解壓到 `data/raw/actions/`，連同 `data/raw/` 裡本機收的資料一起，依序跑完彙整、估容量、產生 `data/processed/t4-morning.json`、驗證格式，最後比對 Demo 台詞。
3. **看結果：**
   - 第 2 步會印「容量 … 輛/15 分鐘」與「塞／不塞對上 N 格」。如果警告「收集期間都沒塞住」，情境的數字就不能拿來講，要跟團隊說。
   - 最後一步會列出 Demo 台詞哪幾項對不上，並印出照資料改寫的台詞。把改寫的台詞貼給設計，一起更新 `PRODUCT.md`。
4. **commit：** `data/processed/` 底下的 `t4-morning.json`、`vd_15min.json`、`model_input.json` 三個檔。`data/raw/` 不進 git（已在 `.gitignore`）。

## 3. 驗證資料目錄（約 10 分鐘，隨時可以做）

```
python3 data/fetch/check_catalog.py
```

會逐一下載 11 個資料集的樣本到 `data/raw/catalog/`，印出欄位。目錄的完成標準是 **8 個已驗證**；目前 VD 即時、VD 靜態、VD 路段彙總 3 個已驗證，這次再多 8 個機會（YouBike、停車即時、停車基本資料、國道歷史、捷運分時進出量、捷運出入口、交通事故統計、A3 事故）。

抓得到的，把 [`catalog.md`](catalog.md) 該列的「⚠️」改成「✅ 10/2x」，欄位不對就順手改。抓不到的，程式會印出資料集頁面，用瀏覽器手動下載一個檔案看欄位。

## 4. 補缺口入口（麥帥二橋、康寧路三段）

這兩個入口沒有偵測器，熱力圖上是 `{gap: true}`（留白，不補值）。**這是對的，不用硬補。** Demo 時講「沒有偵測器的地方我們留白，不補數字」，反而是可信度的加分。

想補的話，有兩條路，都不影響 10/24 交件：

| 做法 | 要做什麼 | 補完是什麼標籤 |
| --- | --- | --- |
| 交工處的路口交通量調查 | 到臺北市交工處網站或 data.taipei 搜尋「路口交通量調查」，找康寧路三段、麥帥二橋附近路口的 15 分鐘流量 PDF。只有一天的資料，只能補「流量」圖層，不能補車速 | `observed`，但 `note` 寫「單日調查，非收集期間」 |
| 國道歷史資料（高公局） | `python3 data/fetch/fetch_freeway_vd.py --probe` 試看看連不連得到；連得到就能補**國 1 內湖交流道**（不是這兩個缺口，但能讓 8 個入口裡多 1 個是真的） | `observed` |

## 5. 換題演練

見 [`DRILL.md`](DRILL.md)。要三個人一起，計時 2 小時。

## Windows 的差異

- 指令裡的 `python3` 換成 `py`，路徑裡的 `/` 不用改；`~/Downloads` 換成 `$HOME\Downloads`。
- 沒有 `caffeinate`：本機收集改用 `py data/fetch/collect_vd.py --today`，並把電源設定改成不睡眠。
- 安裝 Python 時要勾 **Add python.exe to PATH**。
- 印出亂碼或 `UnicodeEncodeError`：先執行 `$env:PYTHONUTF8=1` 再跑一次。
