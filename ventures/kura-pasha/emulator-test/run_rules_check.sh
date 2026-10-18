#!/bin/bash
# firestore-security-rules-draft.md 4節の残課題(実Firestoreプロジェクト無しでの検証)を
# Firebase Local Emulator Suite(デモプロジェクトID、実GCPプロジェクト・課金設定は一切不要)
# で解消するための検証スクリプト。emulators:exec から呼び出される前提。
set -euo pipefail

PROJECT="demo-kura-pasha"
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

# 1. craftsman_workshop/{workshopId} への未認証直接書き込み
check_denied "craftsman_workshop/{workshopId} 書き込み" POST \
  "${BASE}/craftsman_workshop?documentId=testWorkshop" '{"fields":{"plan":{"stringValue":"test"}}}'

# 2. stripe_customer_index/{customerId} への未認証直接書き込み
check_denied "stripe_customer_index/{customerId} 書き込み" POST \
  "${BASE}/stripe_customer_index?documentId=testCustomer" '{"fields":{"workshopId":{"stringValue":"test"}}}'

# 3. user_profile/{userId} への未認証直接書き込み
check_denied "user_profile/{userId} 書き込み" POST \
  "${BASE}/user_profile?documentId=testUser" '{"fields":{"linked":{"booleanValue":true}}}'

# 4. pending_workshop_invites/{inviteCode} への未認証直接書き込み
check_denied "pending_workshop_invites/{inviteCode} 書き込み" POST \
  "${BASE}/pending_workshop_invites?documentId=testInvite" '{"fields":{"status":{"stringValue":"pending"}}}'

# 5. pending_links/{linkingCode} への未認証直接書き込み
check_denied "pending_links/{linkingCode} 書き込み" POST \
  "${BASE}/pending_links?documentId=testLink" '{"fields":{"status":{"stringValue":"pending"}}}'

# 6. usage_counter/{workshopId} への未認証直接書き込み
check_denied "usage_counter/{workshopId} 書き込み" POST \
  "${BASE}/usage_counter?documentId=testWorkshop" '{"fields":{"count":{"integerValue":"1"}}}'

# 7. 対象外トップレベルコレクション(document=** のdeny-all catch-all)への書き込み
check_denied "想定外トップレベルコレクション書き込み(document=** catch-all)" POST \
  "${BASE}/unexpectedCollection?documentId=testDoc" '{"fields":{"x":{"stringValue":"y"}}}'

# 8. craftsman_workshop/{workshopId} への未認証読み取り
check_denied "craftsman_workshop/{workshopId} 読み取り" GET \
  "${BASE}/craftsman_workshop/testWorkshop"

echo "ALL CHECKS PASSED: firestore.rules (deny-all) をFirebase Local Emulator Suiteで検証、未認証クライアントアクセスは全てPERMISSION_DENIEDを確認した。"
