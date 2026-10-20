# 資料來源清單

Oct 20, 2026 · 交件 README 的「資料來源」「AI 工具與開源套件」直接引用這份。題目換了就照 [`SOP.md`](SOP.md) 更新。

競賽規則要求：README 註明真實開放資料與模擬資料，Demo 時口頭說明；可以用 AI 工具與開源套件，但要在 README 註明。畫面上每個數字另外標「真實觀測／程式計算／情境假設／AI 生成」，模擬資料加斜線紋路。

## 一、真實開放資料

| 資料 | 提供單位 | 連結 | 用在哪裡 | 期間 | 現況 |
| --- | --- | --- | --- | --- | --- |
| 臺北市車輛偵測器（VD）即時資料 | 臺北市交通管制工程處 | [VDLive.xml](https://tcgbusfs.blob.core.windows.net/blobtisv/VDLive.xml) | 熱力圖 5 個入口的車速與流量；錯峰情境的容量與到達曲線（`model_input.json`） | 2026-10-20～10-23 平日 07:00–10:30，每 5 分鐘收一次 | 收集中 |
| 臺北市車輛偵測器（VD）靜態資料 | 臺北市交通管制工程處 | [VD.xml](https://tcgbusfs.blob.core.windows.net/blobtisv/VD.xml)、[data.taipei](https://data.taipei/dataset/detail?id=47cb9090-e1c9-4b1d-b299-b11c375c5ee2) | 偵測器與入口的對照（`processed/entrances.csv`） | 2026-10-19 下載 | 已使用 |
| 國道車輛偵測器 | 交通部 TDX／高速公路局 | [TDX](https://tdx.transportdata.tw/) | 國 1 內湖交流道 | — | 未使用：TDX 金鑰還沒下來，該入口目前是模擬 |

收集方式與頻率：`data/fetch/collect_vd.py`，每 5 分鐘一次，不更頻繁（行為準則：不對市府系統做壓測）。原始檔不進 git。

## 二、調查、統計與文獻（引用的數字）

| 數字 | 出處 | 性質 | 用在哪裡 |
| --- | --- | --- | --- |
| 內科員工上班時間 82% 集中在上午 9 時；壅塞 8:30–9:30、18:00–19:00 | [交通局 2015 年調查](https://dot.gov.taipei/News_Content.aspx?n=42F54DDC552218AD&sms=051295A13C5CC507&s=6B82592FD161ADB6) | 官方原文，已逾十年 | 模擬資料的尖峰時段與到達曲線形狀 |
| 檀香山錯峰試辦：目標 18%，實際參與 6–7% | [Giuliano & Golob，TRR 1280（1990）](https://onlinepubs.trb.org/Onlinepubs/trr/1990/1280/1280-006.pdf) | 學術文獻 | 錯峰情境的參考線 |
| 下午尖峰旅行時間較 111 年下降約 6.3% | [交通局 115 年 4 月議會工作報告](https://www-ws.gov.taipei/001/Upload/390/relfile/10199/9555383/333e42c6-6815-48f6-befb-7989603a7433.pdf) | 官方原文 | 背景說明 |
| 內科就業人數 177,574 人（2024） | 產業發展局統計 | 官方統計；媒體常用 21 萬 | 背景說明 |
| 機車約佔進出內科私人運具四成 | 柯市府初期統計 | 新聞轉述，未核實 | 「我們可能錯在哪」 |
| 文湖線尖峰每小時約 13,000 人次 | 北捷說法 | 新聞轉述，未核實 | 背景說明 |

其他未經核實的數字（例如「7 條幹道下降 6.07%」）不放在畫面上，清單見 [`HANDOVER.md`](../HANDOVER.md#背景數據與來源)。

## 三、模擬資料

全部由腳本產生，沒有手填的數字，重跑結果相同；畫面上加斜線紋路，用到模擬數字的分享卡印「含模擬資料」。方法寫在每個檔案的 `meta.mock_method`，說明見 [`mock/README.md`](mock/README.md)。

| 檔案 | 產生腳本 | 模擬了什麼 | 換成真實資料的方式 |
| --- | --- | --- | --- |
| `mock/t4-morning.json` | `mock/gen_t4_morning.py` | 熱力圖的車速與流量、文湖線負載、個人建議的路上時間、時段名額比例、「如果大家都這樣」的三種結果 | 熱力圖 5 個入口與錯峰情境已接好真實 VD（`--real`、`--model`）；國 1 等 TDX；麥帥二橋、康寧路是缺口，不補值 |
| `mock/inputs/model_input.json` | `processed/build_model_input.py --mock` | 堤頂大道的容量（1,000 輛／15 分鐘 ±10%）與到達曲線 | `build_model_input.py` 讀收集到的 VD，輸出 `processed/model_input.json` |
| `mock/a1-evening.json` | `mock/gen_a1_evening.py` | 晚尖峰版本，換題演練用 | 盤點出城方向的偵測器後收傍晚資料 |
| `mock/b1-1999.json` | `mock/gen_b1_1999.py` | 1999 陳情的件數、結案天數、管道回覆天數、積案，換題演練用 | 臺北市 1999 派工資料 |

**不放模擬值的數字：** 意向登記人數、「我也需要」人數、陳情則數。畫面上只放真實數字，沒有資料時顯示「尚無資料」。

## 四、使用者產生的資料

| 資料 | 存什麼 | 不存什麼 |
| --- | --- | --- |
| 時段認領（意向登記） | 日期、入口、時段、匿名裝置代碼 | 姓名、帳號、位置、IP |
| 設定（出發地區、為什麼沒辦法錯峰） | 只存在使用者的瀏覽器；城市頁只顯示彙總 | 個別使用者的答案 |

人數標「意向登記，未經驗證」，起算日 2026-10-24。

## 五、AI 工具與開源套件

| 名稱 | 用途 | 授權 |
| --- | --- | --- |
| Claude、Claude Code（Anthropic） | 規劃文件、設計稿畫布、資料腳本與網站程式的撰寫與審查 | 商業服務 |
| Python 3 標準函式庫 | 資料收集與處理腳本 | PSF License |
| [jsonschema](https://github.com/python-jsonschema/jsonschema) | 驗證資料契約 | MIT |
| GitHub Actions（`actions/checkout`、`actions/setup-python`、`actions/upload-artifact`） | 平日早上自動收集 VD | MIT |
| [待網站工程師補] | 網站框架、圖表、部署平台、認領後端 | |

網站若有即時呼叫 LLM 的功能，要補上模型服務的名稱、用途與流量上限。
