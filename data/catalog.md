# 資料目錄

Oct 20, 2026 · 給 10/24 選題用：每個推測題目有哪些資料、拿不拿得到。題目推測見 [`HANDOVER.md`](../HANDOVER.md#題目推測與賽前準備)，公布後怎麼用見 [`SOP.md`](SOP.md)。

**驗證狀態**

- ✅ 已下載驗證：實際抓過，欄位確認過。
- ⚠️ 待驗證：連結或關鍵字還沒實際下載。10/20 這份目錄是在雲端環境整理的，那裡連不到 data.taipei 與 tcgbusfs，所以大多還沒驗證。有直接網址或 data.gov.tw 編號的（共 17 個），在自己電腦跑 `python3 data/fetch/check_catalog.py`（步驟見 [`LOCAL.md`](LOCAL.md)）會逐一下載樣本到 `data/raw/catalog/`（不進 git）並印出欄位，跑完把這裡改成 ✅。data.gov.tw、高公局的網站在 Python 3.13 以後會出現 `CERTIFICATE_VERIFY_FAILED: Missing Subject Key Identifier`，10/23 起腳本已處理。
- ⏳ 卡住：需要金鑰或主辦方提供。
- ❌ 不能用。

沒有寫網址、只寫「關鍵字」的，到 [data.taipei](https://data.taipei/) 搜尋該關鍵字；確認後把網址補進來。

## 一眼看完：哪些題目有可直接下載的資料

| 題目 | 已驗證的資料 | 判斷 |
| --- | --- | --- |
| #4 內科晨峰、A1 晚尖峰 | 臺北市 VD（即時、靜態） | **有**，而且已經在收 |
| A2 機車通勤 | 臺北市 VD 有分車種 | 有一部分；事故逐案資料見下一列 |
| 車禍／交通安全（A2、A4 共用） | 傷亡事故逐案資料（zip）、臺北市年度統計 | **有**，10/23 下載得到；逐案檔的欄位要用 `fetch/fetch_accidents.py` 抓完整的 zip 才看得到。做法見 [`docs/topics/crash.md`](../docs/topics/crash.md) |
| A3 最後一哩路 | YouBike 即時車位 | **有**，10/23 下載得到 |
| 公車設點（A3 延伸） | 公車站牌、站位、路線；里人口按年齡 | **有**，10/23 下載得到，免金鑰。做法見 [`docs/topics/transit.md`](../docs/topics/transit.md) |
| A5 停車 | 停車場即時車位、基本資料 | **有**，10/23 下載得到 |
| A6 文湖線 | 無 | 捷運分時進出量是月檔，待驗證 |
| A4 人行、B 類其他題 | 無 | 都待驗證；B1 陳情要看主辦方 Day 1 提供什麼 |

## A. 交通類

### #4 內科晨峰 ／ A1 晚尖峰

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 臺北市 VD 即時資料 | [VDLive.xml](https://tcgbusfs.blob.core.windows.net/blobtisv/VDLive.xml) | XML，約 1.7 MB | 每分鐘，車數是最近 1 分鐘的車數 | 這個網址沒有，要自己收（`data/fetch/collect_vd.py`）；歷史資料見下一列 TDX | VDID、LinkID、車道、車種（M／S／L／T）、流量、車速、佔有率 | ✅ 10/19 抓 3 次，見 `processed/entrances_detail.csv` |
| 臺北市 VD 歷史資料（TDX） | [TDX](https://tdx.transportdata.tw/) `historical/v2/Historical/Road/Traffic/Live/VD/City/Taipei?Dates=YYYY-MM-DD` | NDJSON，每天約 1.1 GB | 前一天的資料隔天清晨發布 | **有**，最早到哪天待確認 | 同 VDLive，每 1 分鐘一筆 | ⏳ 要 TDX 金鑰；`fetch/fetch_tdx_vd_hist.py` 補抓一整個月，只留目標偵測器 |
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
| 臺北市交通事故統計 | [data.gov.tw 135546](https://data.gov.tw/dataset/135546)（檔案在 data.taipei） | CSV（Big5） | 每年 | 有 | 西元年、民國年、數量（件數）、死亡人數、受傷人數 | ✅ 10/23；只有全市每年的總數，當背景數字用 |
| 交通事故件數（含 A3） | [data.gov.tw 135091](https://data.gov.tw/dataset/135091)（檔案在 data.taipei） | CSV（Big5） | 每年 | 有 | 年度、縣市、縣市代碼、交通事故類別、筆數 | ✅ 10/23；**是彙總，不是逐筆**，沒有地點與時間 |
| 傷亡道路交通事故逐案資料（全國） | [114 年 177136](https://data.gov.tw/dataset/177136)；歷年：[112 年 167905](https://data.gov.tw/dataset/167905)、[111 年 161199](https://data.gov.tw/dataset/161199)、[110 年 158865](https://data.gov.tw/dataset/158865)、[109 年 158864](https://data.gov.tw/dataset/158864) | zip（下載點在內政部 opdadm.moi.gov.tw），裡面是 UTF-8 CSV：A1 一個檔、A2 每月一個檔 | 每年 | 有，107 年起 | 52 欄：發生日期、發生時間、事故類別名稱（A1／A2）、發生地點、經度、緯度、天候、光線、速限、道路型態、事故位置、號誌、事故類型及型態、肇因研判、死亡受傷人數、當事者順位、當事者車種（大類別、子類別）、性別、年齡、保護裝備、行動電話、肇事逃逸、外送平台。**沒有案件編號**，一列是一個當事者 | ✅ 10/23 114 年完整下載（41 MB），臺北市 A1 137 列、A2 約 52,900 列；112 年只確認抓得到。用 `fetch/fetch_accidents.py` 下載、`processed/build_crash.py` 彙整 |

### A3 最後一哩路（公車、接駁、YouBike）

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| YouBike 2.0 即時車位 | [youbike_immediate.json](https://tcgbusfs.blob.core.windows.net/dotapp/youbike/v2/youbike_immediate.json) | JSON | 每分鐘 | 無，要自己收 | 站號、站名、總車位、可借、可還、座標 | ✅ 10/23 下載得到（930 KB）；確認有 `sno` 站號、`sna` 站名、`sarea` 行政區、`mday` 更新時間；車位與座標在第 12 欄之後，重跑會印出來 |
| 公車路線與站位 | TDX `Bus` | JSON | 不定期 | — | 路線、站序、座標 | ⏳ 要金鑰 |
| 臺北市公車站牌、站位、路線 | [GetStop.gz](https://tcgbusfs.blob.core.windows.net/blobbus/GetStop.gz)、[GetStopLocation.gz](https://tcgbusfs.blob.core.windows.net/blobbus/GetStopLocation.gz)、[GetRoute.gz](https://tcgbusfs.blob.core.windows.net/blobbus/GetRoute.gz) | JSON（gzip） | 不定期 | — | 站牌：`Id`、`routeId`、`nameZh`、`seqNo`、`goBack`、`longitude`、`latitude`、`stopLocationId`、`address`。站位：`id`、`name`、`lon`、`lat`、`address`、`bearing`。路線：`nameZh`、`providerName`、`departureZh`、`destinationZh`、`distance`、首末班（`goFirstBusTime` 等）、班距 `peakHeadway`、`offPeakHeadway`、`headwayDesc`，假日另有一組 | ✅ 10/23，免金鑰（站牌 9 MB、站位 0.9 MB、路線 0.9 MB） |
| 臺北市各里人口數按年齡分 | [data.gov.tw 136896](https://data.gov.tw/dataset/136896)（檔案在 data.taipei） | CSV（Big5） | 每月 | 有 | 年份、月份、區域代碼、區域別、性別、總計、0歲數量…（逐歲） | ✅ 10/23；從 110 年 1 月起逐月，第一列是全市（`區域代碼` 63000000）；後面依序是區（8 碼）與里（11 碼，例如 `63000010002` 莊敬里），有里的列；要最新月份得下載完整檔 |
| 村里界圖 | [data.gov.tw 7438](https://data.gov.tw/dataset/7438)（內政部國土測繪中心） | SHP（推測） | 不定期 | — | `VILLCODE`、`COUNTYNAME`、`TOWNNAME`、`VILLNAME`、里的範圍 | ⚠️ 網路搜尋得知，公車設點算覆蓋率要用 |
| 捷運車站出入口 | [data.gov.tw 128428](https://data.gov.tw/dataset/128428) | CSV | 不定期 | — | 站名、出口、座標 | ⚠️ |

### A4 人行空間與行人安全

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 交通事故資料（行人） | 同 A2 | CSV | 月或年 | 有 | 當事者為行人的事故 | ⚠️ |
| 人行道 | 關鍵字「人行道」 | SHP／CSV | 不定期 | — | 路段、寬度 | ⚠️ |

### A5 停車供需

| 資料集 | 連結 | 格式 | 更新 | 歷史 | 關鍵欄位 | 驗證 |
| --- | --- | --- | --- | --- | --- | --- |
| 停車場即時剩餘車位 | [TCMSV_allavailable.json](https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_allavailable.json) | JSON（可能是 gzip） | 每分鐘 | 無，要自己收 | 停車場 id、剩餘車位 | ✅ 10/23 下載得到（478 KB）；欄位包在 `data` 底下，重跑會印出來 |
| 停車場基本資料 | [TCMSV_alldesc.json](https://tcgbusfs.blob.core.windows.net/blobtcmsv/TCMSV_alldesc.json) | JSON（可能是 gzip） | 不定期 | — | 停車場 id、名稱、總車位、座標、費率 | ✅ 10/23 下載得到（2.8 MB）；欄位包在 `data` 底下，重跑會印出來 |

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
