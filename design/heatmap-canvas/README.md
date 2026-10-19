# 熱力圖與 App 畫面範本（設計稿）

給團隊討論視覺設計與分工用的設計範本，**所有數字皆為模擬資料**，方括號（如 `[路口 A]`、`[$]`）為待填欄位。專案整體說明見[根目錄 README](../../README.md)。

線上畫布（可互動預覽）：https://claude.ai/artifact/SfUezmGAepBdbfkgcbWaiH

## 檔案格式

每個 `*.dc.html` 是一張畫板，`canvas.json` 記錄畫板在畫布上的位置與標題。這些檔案需要畫布的執行環境（`support.js`）才能完整呈現互動，直接用瀏覽器打開只能看到靜態結構。

## 畫板清單

### 1. 內科車流熱力圖（議題 #4）

| 檔案 | 內容 |
| --- | --- |
| `Main.dc.html` | 熱力儀表板：入口 × 15 分鐘矩陣，與示意地圖聯動；車速／流量圖層 |
| `Scenario.dc.html` | 錯峰情境：移出比例滑桿、排隊累積曲線、前後差異 |
| `Tokens.dc.html` | 視覺規範：色階、資料標籤、格子狀態、字體 |
| `Mobile.dc.html` | 第一版民眾入口「我的通勤」 |
| `ShareCard.dc.html` | 分享卡 1200×630 |

### 2. V2 結果導向流程

| 檔案 | 內容 |
| --- | --- |
| `V2Setup.dc.html` | 第一次設定：入口、打卡時間、彈性限制 |
| `V2Today.dc.html` | 今天：鎖定建議、時段認領、「如果大家都這樣」 |
| `V2City.dc.html` | 城市：認領進度、城市行動清單 |
| `V2Brief.dc.html` | 給市府與企業的協商一頁紙 |

### 3. 交通類其他推測題目

| 題目 | 熱力圖規劃 | 民眾畫面 | 城市畫面 |
| --- | --- | --- | --- |
| A1 晚尖峰 | `TopicEvening.dc.html` | `A1App.dc.html` | `A1City.dc.html` |
| A2 機車 | `TopicScooter.dc.html` | `A2App.dc.html` | `A2City.dc.html` |
| A3 最後一哩路 | `TopicLastMile.dc.html` | `A3App.dc.html` | `A3City.dc.html` |
| A4 人行空間 | `TopicWalk.dc.html` | `A4App.dc.html` | `A4City.dc.html` |
| A5 停車 | `TopicParking.dc.html` | `A5App.dc.html` | `A5City.dc.html` |
| A6 文湖線 | `TopicMetro.dc.html` | `A6App.dc.html` | `A6City.dc.html` |

## 共通結構

每題都依同一個結構：

1. 熱力圖：問題在哪裡、什麼時候。
2. 幫你決定：給民眾一個具體建議（幾點走、走哪條、停哪裡）。
3. 如果大家都這樣：處理大家都照建議做的集體效應（名額、分散推薦、容量檢核）。
4. 城市行動：民眾的認領與回報彙總成給市府的證據，附負責局處，並註明為作品建議、不代表市府承諾。

## 資料標示

每張圖、每個數字標示「真實觀測／程式計算／情境假設／AI 生成」之一；模擬資料加斜線紋路。正式版須將模擬數字換成真實資料，並在專案 README 列出資料來源與 AI 工具。
