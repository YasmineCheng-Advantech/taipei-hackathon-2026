# Traffic Gem 手機畫面延伸 v2

Oct 23, 2026 · 方向調整：拿掉「認領時段」與「我也需要」，改成**收集數據、作為和市府與企業協商的依據**。

**線上畫布：** https://claude.ai/artifact/CiRVzoaxyWboSgCreVDiUc （可以點、可以按 Play 一路點下去）

第一版 [`../traffic-gem-screens/`](../traffic-gem-screens/) 保留不動，方便對照。數字取自 [`data/mock/t4-morning.json`](../../data/mock/t4-morning.json)，畫面上標「含模擬資料」；使用者提供的數字一律顯示「尚無資料」，不放模擬值。

## 和 v1 差在哪

| 項目 | v1 | v2 |
| --- | --- | --- |
| 今日推薦的主要按鈕 | 認領這個時段 | 走完後，回報今天的狀況 |
| 時段標籤 | 剩 N%、已滿 | 建議、平常、少 N 分、尖峰、可能遲到 |
| 認領成功（`Claimed`） | 有 | 拿掉，改成「回報今天的狀況」（`Report`）：幾點經過、路上感覺、沒照建議的原因 |
| 設定第 3 步 | 只有原因 | 加上「匿名提供我的通勤資料」勾選，並列出會送出／不會送出什麼；預設不勾，不勾也能拿到建議 |
| 城市頁（`City`） | 意向登記人數、各時段認領分布、「我也需要」按鈕 | 改成「數據依據」：資料從哪裡來（各附標籤）、大家提供的通勤資料彙總、每個城市行動附上「依據」 |
| 協商一頁紙 | 只有桌機版 | 新增手機版（`Brief`）：結論、三種做法、數據依據、需要企業提供的資料、市府配合、試辦設計 |
| 設定分頁 | 認領只送出日期、入口、時段 | 「匿名提供通勤資料」開關、刪除我提供過的資料 |
| 如果大家都這樣 | 第三種是「依名額分配」 | 改成「建議分散到各時段」 |
| 底部分頁 | 今日／城市／設定 | 今日／數據／設定 |

圖表畫面（16–24）與 v1 相同，只改了取捨散佈圖的「已滿」標示。

## 畫板

| 畫板 | 檔案 |
| --- | --- |
| 01 首頁 | `Main.dc.html` |
| 02 從哪裡出發 | `Origin.dc.html` |
| 03 入口・最晚到・彈性 | `Setup.dc.html` |
| 04 為什麼沒辦法錯峰＋匿名提供資料 | `Reasons.dc.html` |
| 05 產生中 | `Loading.dc.html` |
| 06 今日推薦 | `Today.dc.html` |
| 07 回報今天的實際狀況 | `Report.dc.html` |
| 08 如果大家都這樣 | `Collective.dc.html` |
| 09 數據依據 | `City.dc.html` |
| 10 協商一頁紙（手機版） | `Brief.dc.html` |
| 11 分享卡 | `Share.dc.html` |
| 12 設定與資料 | `Settings.dc.html` |
| 13 選單展開 | `Menu.dc.html` |
| 14 今天照平常走就好 | `NoPlan.dc.html` |
| 15 這個地區還沒有資料 | `NoData.dc.html` |
| 16–18 熱力圖、錯峰情境、敏感度分析 | `Heatmap`、`Scenario`、`Sensitivity` |
| 19–24 入口地圖、一天曲線、塞車天數、排名、累積曲線、取捨 | `EntryMap`、`DayCurve`、`Reliability`、`Ranking`、`CumCurve`、`Tradeoff` |

## 還沒跟著改的文件

`PRODUCT.md`、`SCREENS.md`、`ROLES.md`、`data/FIELDS.md` 仍寫著認領後端、意向登記人數、`slot_left`。方向定案後要一起改，網站的後端也從「認領」變成「收匿名通勤資料與每日回報」。
