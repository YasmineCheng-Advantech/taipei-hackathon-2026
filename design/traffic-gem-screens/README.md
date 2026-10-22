# Traffic Gem 手機畫面延伸

依視覺設計稿（首頁、設定頁兩張）的風格，延伸出其他手機畫面。原本的畫布 [內科車流熱力圖範本](https://claude.ai/artifact/SfUezmGAepBdbfkgcbWaiH) 沒有改動，這是另一份新畫布：

**線上畫布：** https://claude.ai/artifact/33DGPD3cyaKRYHUvUx1TE9 （可以點、可以按 Play 一路點下去）

一張畫板一個 `.dc.html`，大小都是 390 寬（iPhone 14）。數字取自 [`data/mock/t4-morning.json`](../../data/mock/t4-morning.json)，**全部是模擬資料**。插畫用的是沒有機車的原版（`design/landing/hero-toy-road.webp` 加機車之前的版本），圖片放在畫布的素材區，`/_blob/...` 網址只在畫布裡有效。

| 畫板 | 檔案 | 內容 |
| --- | --- | --- |
| 01 首頁 | `Main.dc.html` | 照設計稿第一張 |
| 02 從哪裡出發 | `Origin.dc.html` | 設定第 1 步；選汐止／基隆會走到 14 |
| 03 入口・最晚到・彈性 | `Setup.dc.html` | 照設計稿第二張，可以點 |
| 04 為什麼沒辦法錯峰 | `Reasons.dc.html` | 可複選、可跳過 |
| 05 產生中 | `Loading.dc.html` | 等待畫面 |
| 06 今日推薦 | `Today.dc.html` | 建議時段、格子、自己挑時段 |
| 07 認領成功 | `Claimed.dc.html` | |
| 08 如果大家都這樣 | `Collective.dc.html` | 三種情境切換 |
| 09 城市 | `City.dc.html` | 目標、認領分布、7 項城市行動 |
| 10 分享卡 | `Share.dc.html` | 三種卡片 |
| 11 設定分頁 | `Settings.dc.html` | 我的通勤、清除設定 |
| 12 選單展開 | `Menu.dc.html` | 右上角漢堡選單 |
| 13 今天照平常走就好 | `NoPlan.dc.html` | 選「不能調整」或今天沒有划算時段 |
| 14 這個地區還沒有資料 | `NoData.dc.html` | 汐止／基隆 |
| 15 熱力圖 | `Heatmap.dc.html` | 8 個入口 × 10 個時段，車速／流量切換；點格子看每天範圍；文湖線負載 |
| 16 錯峰情境 | `Scenario.dc.html` | 提早／延後、拉滑桿看排隊、消散時間、新尖峰警示 |
| 17 哪個假設最影響結論 | `Sensitivity.dc.html` | 敏感度分析的範圍長條，點一項看要補什麼資料 |

15–17 是桌機版熱力儀表板、錯峰情境的手機版，從選單的「給市府與企業」進入。

## 和設計稿不一樣的地方

- 按鈕上的字改成深藍 `#0B3A4A`、主文案改成深咖啡：設計稿的白字在青色、桃橘色上對比不夠（理由同 [`design/landing/README.md`](../landing/README.md)）。
- 「幫你找出更好的出門時間」改成「幫你挑一個比較不塞的時段」：我們給的是經過入口的時間，不是出門時間。
- 「不能調整」的說明改成「我們只告訴你今天哪個時段比較順」：目前沒有路線資料（見 `SCREENS.md` 待決定 2）。
