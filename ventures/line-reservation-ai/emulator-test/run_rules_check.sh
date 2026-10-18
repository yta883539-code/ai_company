#!/bin/bash
# firestore-security-rules-draft.md 4節の残課題(実Firestoreプロジェクト無しでの検証)を
# Firebase Local Emulator Suite(デモプロジェクトID、実GCPプロジェクト・課金設定は一切不要)
# で解消するための検証スクリプト。emulators:exec から呼び出される前提。
set -euo pipefail

PROJECT="demo-line-reservation-ai"
BASE="http://localhost:8080/v1/projects/${PROJECT}/databases/(default)/documents"

check_denied() {
  local label="$1"
  local method="$2"
  local url="$3"
  local body="${4:-{}}"
  local http_code
  http_code=$(curl -s -o /tmp/resp_body.json -w "%{http_code}" -X "$method" "$url" -H "Content-Type: application/json" -d "$body")
  if [ "$http_code" = "403" ] && grep -q "PERMISSION_DENIED" /tmp/resp_body.json; then
    echo "PASS: ${label} -> HTTP ${http_code} PERMISSION_DENIED"
  else
    echo "FAIL: ${label} -> HTTP ${http_code} $(cat /tmp/resp_body.json)"
    exit 1
  fi
}

# 1. stores/{storeId} 本体への未認証直接書き込み
check_denied "stores/{storeId} 書き込み" POST \
  "${BASE}/stores?documentId=testStore" '{"fields":{"name":{"stringValue":"test"}}}'

# 2. stores/{storeId}/bookingSlots/{slotKey} サブコレクションへの未認証直接書き込み
check_denied "stores/{storeId}/bookingSlots サブコレクション書き込み" POST \
  "${BASE}/stores/testStore/bookingSlots?documentId=testSlot" '{"fields":{"status":{"stringValue":"held"}}}'

# 3. stores/{storeId}/conversations サブコレクションへの未認証直接書き込み
check_denied "stores/{storeId}/conversations サブコレクション書き込み" POST \
  "${BASE}/stores/testStore/conversations?documentId=testSession" '{"fields":{"state":{"stringValue":"init"}}}'

# 4. 対象外トップレベルコレクション(document=** のdeny-all catch-all)への書き込み
check_denied "想定外トップレベルコレクション書き込み(document=** catch-all)" POST \
  "${BASE}/unexpectedCollection?documentId=testDoc" '{"fields":{"x":{"stringValue":"y"}}}'

# 5. stores/{storeId} 本体への未認証読み取り
check_denied "stores/{storeId} 読み取り" GET \
  "${BASE}/stores/testStore"

echo "ALL CHECKS PASSED: firestore.rules (deny-all) をFirebase Local Emulator Suiteで検証、未認証クライアントアクセスは全てPERMISSION_DENIEDを確認した。"
