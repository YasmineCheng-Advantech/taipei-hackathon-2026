# 資安與隱私守則

Oct 24, 2026 · 給所有在這個 repo 工作的人與 AI（兩個 Claude 帳號都要先讀這份）

> 這份把 [`CLAUDE.md`](CLAUDE.md) 的「隱私與合規」變成**可以逐條檢查**的規則。交件要求公開 GitHub 網址，所以 repo 會轉成 public：**只要進了 git，就當作全世界看得到，而且刪不掉。**

## 一頁摘要

| 問題 | 答案 |
| --- | --- |
| 金鑰放哪裡？ | 本機 `.env`（已 gitignore）、GitHub Actions Secrets。**不進 repo、不進前端 bundle** |
| 哪些檔案永遠不進 git？ | `.env`、`data/raw/`、陳情原文、`.venv/`、`dist/`、`node_modules/`、`.DS_Store` |
| 網站可以送使用者資料出去嗎？ | 不行。設定只留在使用者的瀏覽器（localStorage） |
| 可以多常抓市府資料？ | **每 5 分鐘最多一次**，而且不能被 query string 繞過 |
| 轉 public 前要做什麼？ | 跑完[轉公開前檢查清單](#轉公開前檢查清單)，每一項都要過 |

## 一、金鑰

- TDX 金鑰只走環境變數：本機放 repo 根目錄的 `.env`（已 gitignore），CI 放 GitHub Actions Secrets（`TDX_CLIENT_ID`、`TDX_CLIENT_SECRET`）。
- **不要把金鑰寫進任何 `.py`、`.js`、`.json`、`.md`、commit 訊息或 PR 描述。**
- 要讓別人知道需要哪些變數，改 `.env.example`（只有 KEY 名稱，值留空）。
- 前端是純靜態單檔 bundle，**任何寫進前端的東西使用者都看得到**，所以前端永遠不放金鑰。
- 萬一不小心 commit 了金鑰：**先去 TDX 後台重新產生金鑰**，再處理 git 歷史。順序不能反——金鑰一旦推上去就視為已外洩，改歷史不會讓它變回秘密。

## 二、不進 git 的東西

| 路徑 | 為什麼 |
| --- | --- |
| `.env`、`.env.*` | 金鑰 |
| `data/raw/` | 原始抓取資料，量大且含第三方原始內容 |
| 陳情原文（「市長，你給我聽好了」） | CLAUDE.md 明訂：原文不進 repo、不放公開頁面，只放彙總統計，不得反推身分 |
| `.venv/`、`__pycache__/`、`node_modules/`、`dist/` | 建置產物與環境 |
| `.DS_Store`、`*.log` | 雜物 |

`data/processed/vd_readings.csv` **可以**進 git：那是臺北市公開的偵測器讀數（欄位只有時間、入口、偵測器代碼、車數、車速、佔有率），沒有個資。

## 三、使用者資料

- **不收集個資。** 設定（入口、最晚到、彈性、原因）只存在使用者自己的瀏覽器 localStorage，不上傳。
- 前端**不得**出現 `fetch`／`sendBeacon`／`XMLHttpRequest` 把使用者的設定或行為送出去。唯一允許的對外呼叫是**讀取**公開路況（`/api/live`）。
- 若之後有後端（例如時段認領）：
  - 只存「日期、入口、時段、匿名裝置代碼」，**不存姓名、帳號、位置、IP**
  - 匿名裝置代碼用前端產生的隨機 UUID 存 localStorage，**不可**由 IP／User-Agent 推導
  - 關閉 access log 的 IP 欄位
  - 加上每裝置頻率限制；CORS 只允許正式網域
  - 現場 Demo 用獨立的 demo 房間，不計入正式統計
- 人數一律顯示後端的真實數字；沒有就顯示「尚無資料」，**不得**用模擬值填充（CLAUDE.md：不用模擬人數當民意）。

## 四、對外部系統要客氣

抓市府與第三方資料時：

- **每 5 分鐘最多一次。** 不只是「我們的程式這樣寫」，要確保**別人也沒辦法逼它更頻繁**：
  - 伺服器端代理（`web/api/live.js`）要**忽略 query string**。CDN 的快取鍵包含 query string，所以 `/api/live?x=1`、`?x=2`⋯ 每一個都是 cache miss，會變成對市府系統的放大器。
  - 除了 CDN 快取，另外加**伺服器端節流**（記住上次抓取時間與結果，間隔內一律回快取值）。
  - 限定 HTTP method 為 `GET`／`HEAD`。
- 不對市府或第三方系統做掃描、壓測、爬整站。
- 錯誤訊息不要把上游的原始錯誤回給前端（可能洩漏內部資訊），詳情寫 server log 就好。

## 五、開發期的自動偵測

兩層閘門，兩個都會隨 repo 一起走：

1. **Claude Code hook**（`.claude/settings.json`）：攔截 `git commit` / `git push`，掃描 staged diff，命中就擋下。兩個 Claude 帳號都自動生效。
2. **git pre-commit hook**：覆蓋手動 commit。每個人 clone 後執行一次：

   ```bash
   git config core.hooksPath .githooks
   ```

兩者跑的是同一支 [`.githooks/scan-staged.sh`](.githooks/scan-staged.sh)。

**被擋下時不要用 `--no-verify` 硬推。** 先確認那真的是誤判，再把例外加進腳本並說明原因。

## 六、轉公開前檢查清單

交件要公開網址，轉 public **之前**逐項確認。轉成 public 之後，歷史與所有分支一次全公開，而且不可逆。

- [ ] `gitleaks detect --redact --log-opts="--all"` 回報 0 筆
- [ ] `git ls-files | grep -iE '\.env|data/raw/|\.DS_Store|\.venv'` 無輸出
- [ ] 已合併或封存所有還有獨有內容的分支，刪掉其餘 `claude/*` 遠端分支
- [ ] 前端斷網可完整操作（沒有外部請求）
- [ ] `.env.example` 只有 KEY 名稱、沒有值
- [ ] 轉 public **之後立刻**開啟 GitHub secret scanning 與 push protection：

  ```bash
  gh api -X PATCH repos/<owner>/<repo> \
    -f security_and_analysis='{"secret_scanning":{"status":"enabled"},"secret_scanning_push_protection":{"status":"enabled"}}'
  ```

- [ ] 用無痕視窗以登出狀態開 repo 與作品網址，確認看到的內容符合預期

## 七、目前已知、還沒處理的

誠實記錄，不假裝都做完了：

| 項目 | 狀態 |
| --- | --- |
| **TDX 金鑰已失效** | 10/24 08:07 起，token 端點回 `unauthorized_client`／`Invalid client credentials`。**不是流量限制**（那會是 429／403）。先前成功 744 次，所以是在 TDX 那端被撤銷或重新產生。要到 <https://tdx.transportdata.tw/> 重新產生、更新 `.env`、**重啟 `collect_vd.py`**。<br>**影響範圍小**：臺北市 VDLive 不需金鑰，5 個入口的真實資料照常；國 1 內湖交流道本來就是 `assumed`／`sim: true`；一個月歷史資料已抓完存在 `data/raw/tdx_vd_hist/` |
| ~~`web/api/live.js` 的 query string 繞過快取~~ | **10/24 已修**：加了模組層節流（TTL 5 分鐘）＋ inflight 共用，忽略 query string；限定 `GET`／`HEAD`，其餘回 405；錯誤訊息不再把上游原始錯誤回給前端 |
| ~~`web/src/shell.html` 外連 Google Fonts~~ | **10/24 已修**：Grandstander 800 內嵌成 data URI（22 KB），中文改系統字；18 個畫面的 `<link>` 也一併移除。`dist/index.html` 現在**零外部請求** |
| repo 仍為 private | 交件前才轉 public，照第六節清單 |
| `~/Downloads/traffic-gem` 舊副本 | 已停用、**不要再改**。正本是本 repo 的 [`web/`](web/) |
