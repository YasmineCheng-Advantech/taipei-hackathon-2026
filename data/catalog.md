# 資料目錄

Oct 20, 2026 · 給 10/24 選題用：每個推測題目有哪些資料、拿不拿得到。題目推測見 [`HANDOVER.md`](../HANDOVER.md#題目推測與賽前準備)，公布後怎麼用見 [`SOP.md`](SOP.md)。

**驗證狀態**

- ✅ 已下載驗證：實際抓過，欄位確認過。
- ⚠️ 待驗證：連結或關鍵字還沒實際下載。10/20 這份目錄是在雲端環境整理的，那裡連不到 data.taipei 與 tcgbusfs，所以大多還沒驗證。有直接網址或 data.gov.tw 編號的（共 11 個），在自己電腦跑 `python3 data/fetch/check_catalog.py`（步驟見 [`LOCAL.md`](LOCAL.md)）會逐一下載樣本到 `data/raw/catalog/`（不進 git）並印出欄位，跑完把這裡改成 ✅。
- ⏳ 卡住：需要金鑰或主辦方提供。
- ❌ 不能用。

沒有寫網址、只寫「關鍵字」的，到 [data.taipei](https://data.taipei/) 搜尋該關鍵字；確認後把網址補進來。

## 一眼看完：哪些題目有可直接下載的資料

| 題目 | 已驗證的資料 | 判斷 |
| --- | --- | --- |
| #4 內科晨峰、A1 晚尖峰 | 臺北市 VD（即時、靜態） | **有**，而且已經在收 |
| A2 機車通勤 | 臺北市 VD 有分車種 | 有一部分；事故資料待驗證 |
| A3 最後一哩路 | 無 | YouBike 即時資料應該拿得到，待驗證 |
| A5 停車 | 無 | 停車場即時車位應該拿得到，待驗證 |
| A6 文湖線 | 無 | 捷運分時進出量是月檔，待驗證 |
| A4 人行、B 類其他題 | 無 | 都待驗證；B1 陳情要看主辦方 Day 1 提供什麼 |

## A. 交通類

### #4 內科晨峰 ／ A1 晚尖峰

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 臺北市 VD 即時資料 | [VDLive.xml](https://tcgbusfs.blob.core.windows.net/blobtisv/VDLive.xml) | XML，約 1.7 MB | 每分鐘，值為 5 分鐘統計 | 無，要自己收（`data/fetch/collect_vd.py`） | VDID、LinkID、車道、車種（M／S／L／T）、流量、車速、佔有率 | ✅ 10/19 抓 3 次，見 `processed/entrances_detail.csv` |
| 臺北市 VD 靜態資料 | [VD.xml](https://tcgbusfs.blob.core.windows.net/blobtisv/VD.xml)（[data.taipei](https://data.taipei/dataset/detail?id=47cb9090-e1c9-4b1d-b299-b11c375c5ee2)） | XML | 不定期 | — | VDID、座標、路段、方向、車道數 | ✅ 10/19，604 支 |
| 臺北市 VD 路段彙總（舊格式） | [GetVD.xml.gz](https://tcgbusfs.blob.core.windows.net/blobtisv/GetVD.xml.gz) | XML（gzip） | 每分鐘 | 無 | 路段名（如「環東進城 前方」） | ✅ 10/19，用來對照位置 |
| 國道 VD（TDX） | [TDX](https://tdx.transportdata.tw/) `Road/Traffic/Live/VD/Freeway` | JSON | 每分鐘 | 無 | VDID、車道、流量、車速 | ⏳ 要金鑰，目前回 401 |
| 國道 VD（高公局交通資料庫） | [tisvcloud](https://tisvcloud.freeway.gov.tw/history/motc20/) | XML（gzip） | 每分鐘 | **有**，可以事後補抓 | 同上 | ⚠️ 雲端環境連線逾時，在自己電腦用 `fetch/fetch_freeway_vd.py --probe` 試 |
| 交工處 2025 年路口 15 分鐘流量調查 | 臺北市交工處 PDF | PDF | 單日 | — | 路口、轉向、15 分鐘流量 | ⚠️ 待取得，用來校準到達曲線 |
| 縣市即時路況（data.gov.tw 166031） | [data.gov.tw](https://data.gov.tw/dataset/166031) | — | — | — | — | ❌ 已下架，改用上面的臺北市 VD |

晚尖峰要另外盤點**出城方向**的偵測器（`entrances.csv` 只有往內湖方向）；麥帥二橋的 V7230E0 正好是出城方向。

### A2 機車通勤

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 臺北市 VD（機車車種） | 同上 VDLive.xml，`VehicleType=M` | XML | 每分鐘 | 自己收 | 機車流量 | ✅ 機車混在一般車道計數，可能漏數 |
| 交通事故資料 | [交通局統計 135546](https://data.gov.tw/dataset/135546)、[警察局 A3 135091](https://data.gov.tw/dataset/135091)；逐筆資料用關鍵字「交通事故」 | CSV | 月或年 | 有 | 時間、地點、車種、傷亡 | ⚠️ |

### A3 最後一哩路（公車、接駁、YouBike）

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| YouBike 2.0 即時車位 | [youbike_immediate.json](https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json) | JSON | 每分鐘 | 無，要自己收 | 站號、站名、總車位、可借、可還、座標 | ⚠️ |
| 公車路線與站位 | TDX `Bus` | JSON | 不定期 | — | 路線、站序、座標 | ⏳ 要金鑰 |
| 捷運車站出入口 | [data.gov.tw 128428](https://data.gov.tw/dataset/128428) | CSV | 不定期 | — | 站名、出口、座標 | ⚠️ |

### A4 人行空間與行人安全

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 交通事故資料（行人） | 同 A2 | CSV | 月或年 | 有 | 當事者為行人的事故 | ⚠️ |
| 人行道 | 關鍵字「人行道」 | SHP／CSV | 不定期 | — | 路段、寬度 | ⚠️ |

### A5 停車供需

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 停車場即時剩餘車位 | [TCMSV_allavailable.json](https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_allavailable.json) | JSON（可能是 gzip） | 每分鐘 | 無，要自己收 | 停車場 id、剩餘車位 | ⚠️ |
| 停車場基本資料 | [TCMSV_alldesc.json](https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_alldesc.json) | JSON（可能是 gzip） | 不定期 | — | 停車場 id、名稱、總車位、座標、費率 | ⚠️ |

### A6 文湖線擁擠

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 臺北捷運各站分時進出量 | [data.taipei](https://data.taipei/dataset/detail?id=63f31c7e-7fc3-418b-bd82-b95158755b4d)、[data.gov.tw 128506](https://data.gov.tw/dataset/128506) | CSV 月檔 | 每月 | 有（先前查到至 2026-07） | 日期、時段、進站、出站、人次 | ⚠️ 檔案大，先下載一個月看欄位 |

## B. 其他市政題

| 題目 | 資料集 | 連結 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- |
| B1 1999 陳情熱區與處理效率 | 臺北市 1999 派工資料 | 關鍵字「1999」 | 案件類別、行政區、受理時間、結案時間、承辦機關 | ⚠️ 模擬版已做好（`mock/b1-1999.json`），正式版需要這幾個欄位 |
| B1 | 「市長，你給我聽好了」陳情資料 | 主辦方提供 | 待確認 | ⏳ Day 1 確認；不得反推身分、原文不進 repo。到手後用 `fetch/aggregate_petitions.py` 只輸出彙總 |
| 環境衛生／病媒 | 登革熱病例、病媒孳生源 | 關鍵字「登革熱」「病媒」 | 日期、行政區或里 | ⚠️ |
| 行道樹與綠化 | 行道樹 | 關鍵字「行道樹」 | 樹種、座標、所在道路 | ⚠️ |
| 淹水與韌性城市 | 雨量站、抽水站、積淹水紀錄 | 關鍵字「雨量」「抽水站」「積淹水」 | 時間、地點、雨量或水位 | ⚠️ |
| 青年住宅／社宅 | 實價登錄（內政部） | [plvr.land.moi.gov.tw](https://plvr.land.moi.gov.tw/DownloadOpenData) | 交易日期、行政區、租金或總價、面積 | ⚠️ |
| 青年住宅／社宅 | 社會住宅 | 關鍵字「社會住宅」 | 名稱、戶數、座標 | ⚠️ |
| 幼托與延托 | 幼兒園、托嬰中心 | 關鍵字「幼兒園」「托嬰」 | 名稱、行政區、收托人數、收托時間 | ⚠️ 收托時間不一定有 |
| 商圈與傳統市場 | 市場、商圈 | 關鍵字「市場」「商圈」 | 名稱、座標、攤位數 | ⚠️ |
| 吸菸熱點 | 吸菸區 | 關鍵字「吸菸區」 | 地點、座標 | ⚠️ |
