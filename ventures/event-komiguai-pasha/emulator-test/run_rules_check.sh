#!/bin/bash
# firestore-security-rules-draft.md 4節の残課題(実Firestoreプロジェクト無しでの検証)を
# Firebase Local Emulator Suite(デモプロジェクトID、実GCPプロジェクト・課金設定は一切不要)
# で解消するための検証スクリプト。emulators:exec から呼び出される前提。
# aircon-pashaのfirestore-security-rules-emulator-verification.md(forklift-pashaフェーズ174
# と同じ手法)を本venture向けに横展開したもの。対象コレクションはone_time_draft・inquiry・
# idempotency_key_indexの3種。idempotency_key_indexはexpireAtを持つドキュメントと持たない
# ドキュメントが同一コレクション内に混在する設計(idempotency-key-write-conflict-control-
# design.mdフェーズ68)のため、本venture固有の残課題として両パターンを個別に検証する。
set -euo pipefail

PROJECT="demo-event-komiguai-pasha"
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

# 1. one_time_draft/{draftId} への未認証直接書き込み
check_denied "one_time_draft/{draftId} 書き込み" POST \
  "${BASE}/one_time_draft?documentId=testDraft" '{"fields":{"status":{"stringValue":"awaiting_payment"}}}'

# 2. inquiry/{inquiryId} への未認証直接書き込み
check_denied "inquiry/{inquiryId} 書き込み" POST \
  "${BASE}/inquiry?documentId=testInquiry" '{"fields":{"category":{"stringValue":"resend"}}}'

# 3. idempotency_key_index/{idempotencyKey} への未認証直接書き込み(expireAtあり、
#    one_time_draft側24時間TTLパターン)
check_denied "idempotency_key_index/{idempotencyKey} 書き込み(expireAtあり)" POST \
  "${BASE}/idempotency_key_index?documentId=testKeyWithTtl" '{"fields":{"expireAt":{"timestampValue":"2026-11-07T03:00:00Z"}}}'

# 4. idempotency_key_index/{idempotencyKey} への未認証直接書き込み(expireAtなし、
#    inquiry側永続保存パターン)
check_denied "idempotency_key_index/{idempotencyKey} 書き込み(expireAtなし)" POST \
  "${BASE}/idempotency_key_index?documentId=testKeyNoTtl" '{"fields":{"source":{"stringValue":"inquiry"}}}'

# 5. 対象外トップレベルコレクション(document=** のdeny-all catch-all)への書き込み
check_denied "想定外トップレベルコレクション書き込み(document=** catch-all)" POST \
  "${BASE}/unexpectedCollection?documentId=testDoc" '{"fields":{"x":{"stringValue":"y"}}}'

# 6. one_time_draft/{draftId} への未認証読み取り
check_denied "one_time_draft/{draftId} 読み取り" GET \
  "${BASE}/one_time_draft/testDraft"

echo "ALL CHECKS PASSED: firestore.rules (deny-all) をFirebase Local Emulator Suiteで検証、未認証クライアントアクセスは全てPERMISSION_DENIEDを確認した(idempotency_key_indexはexpireAtの有無両パターンを確認)。"
