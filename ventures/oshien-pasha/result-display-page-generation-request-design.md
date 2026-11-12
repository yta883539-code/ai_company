# 生成物表示ページ(次画面)の入力受付・生成リクエスト設計

作成日: 2026-11-09(フェーズ102)

access-token-client-storage-design.md(フェーズ101)の次回候補(1)「次画面(生成物表示
ページ)自体の設計(sessionStorageから取り出したaccess_tokenで何を取得するか、既存
レスポンスで足りるか別エンドポイントが必要かを含む)」に対応する。

## 1. 次画面の役割の確定

checkout-result-http-entry-point-design.md(フェーズ100)が返す`access_token`はあくまで
本人確認の鍵であり、生成物(itinerary_draft等)そのものではない。次画面の役割は、
(a)入力フォーム(README.md記載の入力: 会場・日時・枚数・予算感・物販希望・ハシゴ有無等)の
提示、(b)access_tokenを添えた生成リクエストの送信、(c)schema/output.schema.jsonの
`status`分岐に応じた4出力(itinerary_draft/day_timetable/cost_estimate/hashigo_check)の
表示、の3つである。checkout-result-http-entry-point-design.mdのレスポンス本文
(`status`/`access_token`/`poll_attempts_used`)だけではこれらを満たせないため、別エンド
ポイントが必要と結論する。

## 2. 新規エンドポイント `receive_generation_request()`

checkout-result側の`receive_checkout_result_request()`(フェーズ100)・forklift-pashaの
`receive_reissue_request()`と同型の「空入力→400」「本人特定失敗→404/403」「成功→200」の
構成を踏襲する。

```python
def receive_generation_request(
    fan_pass_store: FanPassStoreProtocol,
    generation_logger: _GenerationLogProtocol,  # generation-count-design.md 2節
    llm_client: _LlmGenerationClientProtocol,
    access_token: Optional[str],
    raw_input: dict,
) -> GenerationHttpResult:
```

処理順序:

1. `access_token`が空(None・空文字列)の場合は`status_code=400`
   (`error="missing_access_token"`)を返す。sessionStorageが何らかの理由で空になっている
   ケース(別タブで開いた・ブラウザのプライベートモード等)を想定。
2. `fan_pass_store.get_by_access_token(access_token)`が`None`の場合は`status_code=404`
   (`error="unknown_access_token"`)を返す。checkout-result-http-entry-point-design.mdの
   `unknown_checkout_session_id`と同じ「URL/状態の前提が崩れている」異常系。
3. 見つかった場合、`subscriptionStatus`を確認する(月額フリーパスのケース)。
   `"canceled"`であればfan-pass-canceled-access-block-design.mdの方針に従い
   `status_code=403`(`error="subscription_canceled"`)を返し、生成リクエストは実行しない。
4. `raw_input`の必須項目(会場・日時・予算感等)が欠落している場合でも、サーバー側で
   事前バリデーションして弾くのではなく、そのままLLM呼び出しに渡し
   `status=insufficient_input`の判定自体をLLMに行わせる(llm-system-prompt-draft.md既定の
   方針を踏襲し、入力検証ロジックの二重実装を避ける)。
5. LLM呼び出しが成功した場合、月額フリーパスのケースのみ
   `generation_log`への1件追記・`currentMonthGenerationCount`加算(generation-count-design.md
   2節)を行い、`schema/output.schema.json`形式のレスポンスをそのまま`status_code=200`で
   返す。LLM呼び出し自体が例外を送出した場合の扱い(リトライ・エラーレスポンス)は
   `llm-quality-verification-plan.md`側の既存論点であり本フェーズでは再設計しない。

## 3. 都度プラン(one-time)側の未解決ギャップ

本設計は月額フリーパス(`subscriptionStatus`を持つ`fan_pass`ドキュメント)を前提にしており、
都度プラン(mode=payment、1決済=1回)の`access_token`がどのストアに保存され、1回使用後に
どう失効させるかは未設計のまま残っている。`fan-pass-store-protocol-design.md`の`create()`は
`stripe_subscription_id`を必須パラメータとしており、現状のFanPassStoreProtocolは月額フリーパス
専用の形になっている。都度プランを同じ`fan_pass`コレクションに「単発フラグ付きドキュメント」
として混在させるか、別コレクション(例: `one_time_pass/{internal_id}`)に分離するかは
monthly-pass-identity-design.md(フェーズ7)時点から統合を後回しにされてきた論点であり、
本designの`receive_generation_request()`は現時点では月額フリーパスのみを正として扱う
暫定実装とし、都度プラン対応は次回候補とする。

## 4. 残課題

- 3節の都度プラン用access_tokenの永続化・1回使用後の失効設計。
- 入力フォーム自体のUI/UX(HTML/JS、実デプロイはオーナー承認待ち)。
- (対応済み・フェーズ111)LLM呼び出し失敗時(タイムアウト・Structured Outputs不整合等)の
  処理方針はllm-generation-failure-handling-design.mdで確定し、generation_request_handler.py
  に`status_code=502`・`error="llm_generation_failed"`分岐を実装済み(リトライは行わず、
  fan_passはgeneration_log.record()、one_time_passはmark_consumed()をいずれも呼ばない)。
  実LLM接続後の実際のタイムアウト秒数・リトライ可能な例外種別の精査は引き続き次回候補。
- `_GenerationLogProtocol`・`_LlmGenerationClientProtocol`の具体的なメソッド定義(本フェーズは
  呼び出し順序の確定のみで、プロトコル自体の詳細設計は次回以降)。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成自体は
オーナー承認が必要なアクションに該当するため、本メモは設計の検討に留める(コード実装・外部
サービスへの接続は一切行っていない)。承認が必要なアクション(支払い・アカウント作成・外部
公開・送信等)は本フェーズでは発生していないためpending-approval.mdへの新規追記は不要
(既存の承認待ち事項〈Stripe/GCPアカウント開設等〉の範囲内で扱う)。

最終更新: 2026-11-09 04:00 UTC(フェーズ102: 次画面〈生成物表示ページ〉の役割を確定し、
新規エンドポイント`receive_generation_request()`の処理順序を設計。都度プラン側の
access_token設計が未解決のまま残っていることを明記)
