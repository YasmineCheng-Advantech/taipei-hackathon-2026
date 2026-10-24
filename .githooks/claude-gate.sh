#!/usr/bin/env bash
# Claude Code 的 PreToolUse 閘門：Claude 要執行 git commit / git push 之前先掃一遍。
#
# 從 stdin 讀 hook 的 JSON，判斷這次的 Bash 指令是不是 commit 或 push：
#   commit → 掃 staged 內容（.githooks/scan-staged.sh）
#   push   → 掃已追蹤的檔案清單（commit 當下沒擋到的，推出去之前最後一道）
# 其餘指令一律放行。
#
# 輸出：放行時不輸出；要擋時輸出 PreToolUse 的 deny JSON。
# 刻意永遠 exit 0：用 JSON 表達決定，exit code 非 0 會被當成 hook 自己壞掉。
set -uo pipefail

root="${CLAUDE_PROJECT_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
cd "$root" 2>/dev/null || exit 0

cmd=$(jq -r '.tool_input.command // ""' 2>/dev/null) || exit 0
[ -z "$cmd" ] && exit 0

deny() {
  jq -nc --arg r "$1" '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
  exit 0
}

case "$cmd" in
  *git*commit*)
    out=$(bash .githooks/scan-staged.sh 2>&1)
    [ $? -ne 0 ] && deny "資安閘門擋下這次 commit：

${out}

處理方式見 SECURITY.md。不要用 --no-verify 繞過。"
    ;;
  *git*push*)
    bad=$(git ls-files | grep -iE '(^|/)\.env($|\.)|^data/raw/|\.DS_Store$|(^|/)\.venv/|\.pem$|\.key$' | head -5)
    [ -n "$bad" ] && deny "資安閘門擋下這次 push：repo 裡有不該被追蹤的檔案

${bad}

先用 git rm --cached 移除並 commit。若其中含金鑰，先去 TDX 後台重新產生金鑰。詳見 SECURITY.md。"
    ;;
esac
exit 0
