#!/usr/bin/env bash
# 掃描「即將進 git」的內容，擋下金鑰、原始資料與雜物。
#
# 用法：bash .githooks/scan-staged.sh
# 回傳：0 = 通過（警告也算通過）；1 = 擋下，訊息說明是哪一條
#
# 兩個地方會呼叫它：
#   .githooks/pre-commit        手動 commit（需先跑 git config core.hooksPath .githooks）
#   .claude/settings.json 的 hook   Claude Code 執行 git commit / git push 之前
#
# 設計原則：寧可漏判也不要誤判到讓人習慣用 --no-verify。
# 真正的全面掃描交給 gitleaks（見 SECURITY.md 第六節），這支只擋最常見、最致命的幾種。
set -uo pipefail

fail=0
warn=0
say_fail() { printf '\033[31m✗ %s\033[0m\n' "$1" >&2; fail=1; }
say_warn() { printf '\033[33m⚠ %s\033[0m\n' "$1" >&2; warn=1; }

# 只看「新增或修改」的檔案；刪除的不用檢查
files=$(git diff --cached --name-only --diff-filter=ACMR)
[ -z "$files" ] && exit 0

# ---------- 1. 不該進 git 的路徑 ----------
while IFS= read -r f; do
  [ -z "$f" ] && continue
  case "$f" in
    .env.example|*/.env.example) ;;                       # 只有 KEY 名稱，允許
    .env|*/.env|.env.*|*/.env.*)
      say_fail "${f}：環境變數檔不進 git（金鑰只走 .env 本機檔與 GitHub Secrets）" ;;
    *.pem|*.key|*.p12|*.pfx|*id_rsa*|*id_ed25519*)
      say_fail "${f}：看起來是私鑰或憑證" ;;
    data/raw/*)
      say_fail "${f}：data/raw/ 是原始抓取資料，不進 git（CLAUDE.md 隱私與合規）" ;;
    .venv/*|*/__pycache__/*|node_modules/*|*/node_modules/*|*/dist/*|dist/*)
      say_fail "${f}：建置產物或虛擬環境，不該進 git" ;;
    *.DS_Store|*.log)
      say_fail "${f}：雜物檔，不該進 git" ;;
  esac
  # 陳情原文：不直接擋（data/mock/b1-1999.json 是合法的模擬資料），但要人看一眼
  case "$f" in
    data/mock/*|data/schema/*|docs/*|*.md) ;;
    *1999*|*陳情*|*complaint*)
      say_warn "${f}：路徑看起來和陳情資料有關。確認只有彙總統計、沒有原文，且無法反推身分" ;;
  esac
done <<< "$files"

# ---------- 2. 新增內容裡的金鑰 ----------
# 只看新增的行（+ 開頭），排除合法寫法：
#   ${{ secrets.X }}  GitHub Actions
#   os.environ / process.env / getenv   讀環境變數
#   值是空的、<redacted>、your-...、xxx、...  範例與說明
added=$(git diff --cached --diff-filter=ACMR -U0 -- $(printf '%s\n' "$files" | grep -vE '\.env\.example$') 2>/dev/null \
        | grep '^+' | grep -v '^+++' || true)

if [ -n "$added" ]; then
  legit='\$\{\{|os\.environ|process\.env|getenv|<redacted>|your-|xxxx|\.\.\.|example|EXAMPLE'
  suspect=$(printf '%s\n' "$added" \
    | grep -vE "$legit" \
    | grep -nEi '(client_secret|api_key|auth_token|access_token|payload_secret|ecpay_hash_(key|iv)|postgres_password|password|secret_key)[[:space:]]*[=:][[:space:]]*["'"'"']?[A-Za-z0-9_/+.-]{8,}' \
    || true)
  [ -n "$suspect" ] && say_fail "新增的內容裡有疑似金鑰的設定值：
$(printf '%s\n' "$suspect" | head -5)"

  # 私鑰區塊。要求前導的 5 個破折號：真正的 PEM 一定有，而這支腳本自己的樣式字串沒有。
  # 不加這個限制，掃描腳本進 git 時會擋到自己（10/24 實際發生過）。
  printf '%s\n' "$added" | grep -q -- '-----BEGIN [A-Z ]*PRIVATE KEY' \
    && say_fail "新增的內容裡有私鑰區塊（-----BEGIN ... PRIVATE KEY）"

  # 寫死的 Bearer token
  printf '%s\n' "$added" | grep -vE "$legit" | grep -qE 'Bearer[[:space:]]+[A-Za-z0-9_.-]{20,}' \
    && say_fail "新增的內容裡有寫死的 Bearer token"
fi

# ---------- 結果 ----------
if [ "$fail" -eq 1 ]; then
  cat >&2 <<'EOF'

被擋下了。請移除上面列出的內容再 commit。
規則與例外的處理方式見 SECURITY.md。
不要用 --no-verify 硬推：如果確定是誤判，把例外加進 .githooks/scan-staged.sh 並寫清楚原因。
若金鑰已經推上遠端，先去 TDX 後台重新產生金鑰，再處理 git 歷史。
EOF
  exit 1
fi

[ "$warn" -eq 1 ] && printf '\033[33m（有警告，但不擋。確認過就繼續）\033[0m\n' >&2
exit 0
