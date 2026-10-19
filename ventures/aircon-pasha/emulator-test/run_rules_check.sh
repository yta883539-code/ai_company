#!/bin/bash
# firestore-security-rules-draft.md 4節の残課題(実Firestoreプロジェクト無しでの検証)を
# Firebase Local Emulator Suite(デモプロジェクトID、実GCPプロジェクト・課金設定は一切不要)
# で解消するための検証スクリプト。emulators:exec から呼び出される前提。
# forklift-pashaフェーズ174(emulator-test/run_rules_check.sh)と同じ手法を本venture向けに
# 横展開したもの(対象コレクションはuser_profile・pending_links・usage_counterの3種)。
set -euo pipefail

PROJECT="demo-aircon-pasha"
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

# 1. user_profile/{userId} への未認証直接書き込み
check_denied "user_profile/{userId} 書き込み" POST \
  "${BASE}/user_profile?documentId=testUser" '{"fields":{"name":{"stringValue":"test"}}}'

# 2. pending_links/{linkingCode} への未認証直接書き込み
check_denied "pending_links/{linkingCode} 書き込み" POST \
  "${BASE}/pending_links?documentId=testCode" '{"fields":{"userId":{"stringValue":"test"}}}'

# 3. usage_counter/{userId} への未認証直接書き込み
check_denied "usage_counter/{userId} 書き込み" POST \
  "${BASE}/usage_counter?documentId=testUser" '{"fields":{"count":{"integerValue":"1"}}}'

# 4. 対象外トップレベルコレクション(document=** のdeny-all catch-all)への書き込み
check_denied "想定外トップレベルコレクション書き込み(document=** catch-all)" POST \
  "${BASE}/unexpectedCollection?documentId=testDoc" '{"fields":{"x":{"stringValue":"y"}}}'

# 5. user_profile/{userId} への未認証読み取り
check_denied "user_profile/{userId} 読み取り" GET \
  "${BASE}/user_profile/testUser"

echo "ALL CHECKS PASSED: firestore.rules (deny-all) をFirebase Local Emulator Suiteで検証、未認証クライアントアクセスは全てPERMISSION_DENIEDを確認した。"
