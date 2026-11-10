# 決済結果ポーリングのHTTPエントリポイント設計

作成日: 2026-11-08(フェーズ100)

checkout_result_page_handler.py(フェーズ98)が机上実装した`resolve_checkout_result()`の
先にある残課題、「結果ページ(フロントエンド)が決済完了直後に呼び出すHTTPエンドポイント
自体の配線」を設計する(stripe-webhook-entry-point-design.md 6節・次回候補4、README.md
フェーズ99「次回候補(1)」対応)。forklift-pashaの`access-url-reissue-http-entry-point-
design.md`(フェーズ136、`accessToken`方式で本人特定し例外→ステータスコード変換を行う形)
と同じ位置づけだが、本人特定の鍵が`checkout_session_id`であり、かつ正常系のレスポンス本文に
`access_token`を含める点が差分である。

## 1. 前提: `checkout_session_id`のenumeration耐性

access-url-resend-http-entry-point-design.md(フェーズ43)4節が確定させた「`email`方式は
enumerationリスクがあるためレスポンス本文を持たない」方針は、本エンドポイントには適用
されない。`checkout_session_id`はStripeが発行する高エントロピーな乱数的ID(`cs_...`)で
あり、Stripeの`return_url`機能によってブラウザのクエリ文字列(`?session_id=
{CHECKOUT_SESSION_ID}`)としてのみ利用者本人に渡る。利用者が自分の`email`を知っているのと
異なり、第三者が他人の`checkout_session_id`を推測・総当たりすることは実務上不可能であり、
forklift-pashaが`accessToken`方式を「enumeration対策の対象外」として扱った考え方
(access-url-reissue-http-entry-point-design.md 1節)と同じ信頼レベルに置ける。したがって
本エンドポイントは`found`の真偽(=`status`)および`access_token`そのものをレスポンス本文に
含めてよい。

## 2. 方針: `CheckoutResultHttpResult`・`receive_checkout_result_request()`

```python
@dataclass(frozen=True)
class CheckoutResultHttpResult:
    status_code: int
    result: Optional[CheckoutResultPageResult] = None
    error: Optional[str] = None


def receive_checkout_result_request(
    stripe_lookup: StripeCheckoutSessionLookupProtocol,
    fan_pass_store: _FanPassLookupProtocol,
    checkout_session_id: Optional[str],
    *,
    sleep: Callable[[float], None] = lambda _seconds: None,
    max_attempts: int = MAX_POLL_ATTEMPTS,
    interval_seconds: float = POLL_INTERVAL_SECONDS,
) -> CheckoutResultHttpResult:
```

処理順序(forklift-pashaの`receive_reissue_request()`と同型の「空入力→400」「例外→404」
「成功→200」の3段構成):

1. `checkout_session_id`が空(`None`・空文字列・空白のみ)の場合は、`resolve_checkout_
   result()`を呼ばずに`status_code=400`(`error="missing_checkout_session_id"`)を返す。
   これはURLクエリ文字列の組み立て自体が壊れている場合(Stripe側の`return_url`設定ミス等)
   の入力エラーであり、本人特定の試み以前の問題のため、1節のenumeration非対象方針とは
   無関係に常に発生し得る。
2. `checkout_session_id`が入力されている場合は`resolve_checkout_result()`を呼ぶ。
   `CheckoutSessionNotFoundError`(design.md 3-2節の「ポーリング対象外」の異常系、URL
   改ざん・期限切れ等)が送出された場合は捕捉し、`status_code=404`
   (`error="unknown_checkout_session_id"`)を返す。forklift-pashaの`receive_reissue_
   request()`が`access_token`解決失敗を404に変換するのと同じ位置づけである。
3. 成功時(`status`が`"ready"`・`"pending"`いずれの場合も、ポーリングの結果自体は
   クライアントが知るべき正常な状態遷移であり異常系ではない)は`status_code=200`、
   `result`に`CheckoutResultPageResult`(1節の理由により`access_token`を含めたまま)を
   格納する。

## 3. レスポンス本文の扱い

- 成功時: `status_code=200`、本文は`result`(`status`・`access_token`・
  `poll_attempts_used`)をそのままJSON化したもの。結果ページのJavaScriptは`status`で
  表示を分岐し(`"ready"`なら`access_token`を使って次の画面へ、`"pending"`なら「準備中」
  表示と再ポーリング案内)、`access_token`自体は画面遷移にのみ用いて永続化しない(Cookie・
  localStorage等への保存はdata-retention-policy.mdの対象範囲外として本フェーズでは
  踏み込まない、次回以降の課題とする)。
- `missing_checkout_session_id`: `(error文字列), 400`
- `unknown_checkout_session_id`: `(error文字列), 404`

## 4. 残課題

- (フェーズ108追記)都度プラン対応版(`receive_checkout_result_request_combined()`、
  フェーズ106)への移行方針はcheckout-result-combined-migration-decision.mdで決定済み。
  本番側の呼び出し元は現時点で存在しないため、将来`main(request)`を配線する際はcombined版
  のみを直接使う(本関数を経由する実装は行わない)。

- 実Stripe API呼び出し(`StripeCheckoutSessionLookupProtocol`の実装)・実Cloud
  Functionsデプロイ・実スリープ(本番では`time.sleep()`またはクライアント側の再ポーリング
  に置き換える判断自体)はいずれもオーナー承認が必要なアクション(既存の承認待ち事項の範囲内)
  のため本フェーズでは行わない。
- Cloud Functionsの実エントリポイント`main(request)`(`request.args.get(
  "checkout_session_id")`からの値取り出し配線自体)は、結果ページのフロントエンド実装
  (オーナー承認待ち事項)確定後に行う。
- `access_token`をレスポンス本文に含めたままクライアント側でどう保持するか(3節)は、
  data-retention-policy.mdの観点からの再検討を次回以降の課題として残す。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成・
実際のHTTPデプロイ自体はオーナー承認が必要なアクションに該当するため、本メモは設計・仮説の
検討とインメモリでの机上コード化に留める(外部サービスへの接続は一切行っていない)。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは発生していない
ためpending-approval.mdへの新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

最終更新: 2026-11-08 19:00 UTC(フェーズ100: 決済結果ポーリングのHTTPエントリポイント
`receive_checkout_result_request()`を設計し、prototype/checkout_result_page_handler.py
にコード化した)
