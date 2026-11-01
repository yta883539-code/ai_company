# アクセスURL再送フローのHTTPエントリポイント設計(フェーズ43)

access-url-resend-api-design.md(フェーズ42)の残課題5節(1)「HTTPエントリポイント
(`receive_resend_request()`相当、`request.form.get("email")`からの値取り出し配線)の
コード化」に対応する(README.mdフェーズ42「次回候補(2)」対応)。forklift-pashaの
`access-url-reissue-http-entry-point-design.md`(フェーズ136)と同じ位置づけ
(「処理本体〈`handle_resend_request()`〉はフェーズ42で先に机上実装済み、HTTP配線を
本フェーズで設計する」)だが、本人特定の方式が異なるため404分岐が無く、常に同一レスポンスを
返す点が最大の差分である。

## 1. forklift-pashaとの差分: 404分岐が存在しない

forklift-pashaの`receive_reissue_request()`は、`access_token`が無効・失効済みの場合に
`status_code=404`(`error="unknown_access_token"`)を返す(access-url-reissue-http-entry-
point-design.md 2節)。これは`accessToken`方式では「無効なトークン」という明確な異常系が
存在するためである。

本venture(oshien-pasha)の再送フローは`email`入力を起点とするため、「このメールアドレスは
登録されていない」をHTTPレスポンスで区別するとユーザー列挙(enumeration)のリスクがある
(access-url-resend-api-design.md 4節で確定済みの方針)。したがって本エントリポイントには
404相当の分岐は設けず、`handle_resend_request()`が返す`found`の値にかかわらず常に同一の
`status_code=200`を返す。

## 2. `ResendHttpResult`・`receive_resend_request()`

```python
@dataclass(frozen=True)
class ResendHttpResult:
    status_code: int
    error: Optional[str] = None


def receive_resend_request(
    fan_pass_store: _FanPassLookupAndReissueProtocol,
    stripe_lookup: StripeSubscriptionLookupProtocol,
    email: Optional[str],
    *,
    new_access_token_factory: Callable[[], str],
) -> ResendHttpResult:
```

処理順序:

1. `email`が空(`None`・空文字列・空白のみ)の場合は、`handle_resend_request()`を呼ばずに
   `status_code=400`(`error="missing_email"`)を返す。これは「メールアドレス自体を
   入力していない」という本人特定の試み以前の入力エラーであり、`found`の真偽とは無関係
   なため、enumeration対策の対象外として扱ってよい(forklift-pashaの
   `missing_access_token`分岐と同じ位置づけ)。
2. `email`が入力されている場合は`handle_resend_request()`を呼ぶ。
3. `found`の値にかかわらず(内部の`ResendRequestResult.found`は呼び出し側で参照しない)、
   `status_code=200`のみを返す(`result`フィールドは設けない。4節参照)。

`ResendHttpResult`に`result: ResendRequestResult`を含めない点がforklift-pashaの
`ReissueHttpResult`(`result`フィールドを持つ)との差分である。forklift-pashaは
`accessToken`方式のため、どのパスで開かれたページ向けの応答かという文脈上、レスポンス本文に
`new_access_token`等の内部状態が混ざっても本人以外には届かない前提がある。一方、本venture
の再送フォームは不特定多数からの入力を受け付ける公開エンドポイントであるため、呼び出し側
(Webフォーム)に内部状態を一切渡さず、常に同じ画面遷移(「ご入力いただいたメールアドレス宛に
ご案内をお送りします」)に固定する設計とする。

## 3. 異常系(`MultipleActiveSubscriptionsError`・`FanPassNotFoundForSubscriptionError`)の扱い

`handle_resend_request()`が送出するこれら2つの例外は、いずれも「Stripe側とFirestore側の
整合性が崩れている」運用上のアラート対象(access-url-resend-api-design.md 3節)であり、
利用者の入力ミスではない。forklift-pashaの`receive_reissue_request()`が
`ReissueRequestRejected`(利用者のメールアドレス形式不正)を捕捉して400に変換するのとは
性質が異なるため、本エントリポイントではこれらを**捕捉しない**。Cloud Functions側で
未捕捉例外は500として扱われ、将来のCloud Monitoringアラート設定(forklift-pashaの
`cloud-monitoring-alert-policy-design.md`と同種のものを本ventureでも整備する必要がある、
次回以降の残課題とする)で検知する運用を想定する。500が返ること自体は「このメール
アドレスが登録されているかどうか」の情報を含まないため、enumeration対策の方針とは矛盾しない。

## 4. レスポンス本文を持たない理由

forklift-pashaは`new_access_url`をレスポンス本文に含めない設計(新URLはメール送信でのみ
伝える)だったが、`result`フィールド自体は保持していた(将来呼び出し側がログ目的で使う
余地を残すため)。本ventureはenumeration対策上、`found`の真偽すら呼び出し側に見せたくない
ため、`ResendHttpResult`自体に`result`を持たせず、設計をさらに一段絞り込む。

- 成功時(`missing_email`以外の全ケース、`found`の真偽を問わない): `"OK", 200`
- `missing_email`: `(error文字列), 400`

## 5. 残課題

- `StripeSubscriptionLookupProtocol`の実Stripe接続実装、実際のメール送信実装・接続は
  いずれもオーナー承認が必要なアクション(既存の承認待ち事項の範囲内)のため本フェーズでは
  行わない。
- Cloud Functionsの実エントリポイント`main(request)`(`request.form.get("email")`からの
  値取り出し配線自体)は、Webフォーム側のバックエンド実装(オーナー承認待ち事項)確定後に
  行う。
- 本venture用のCloud Monitoringアラート設定(3節で触れた未捕捉例外の検知)は未整備のまま
  次回以降の課題として残す。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成・
メール送信実装自体はオーナー承認が必要なアクションに該当するため、本メモは設計・仮説の検討と
インメモリでの机上コード化に留める(外部サービスへの接続は一切行っていない)。承認が必要な
アクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは発生していないため
pending-approval.mdへの新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

最終更新: 2026-11-01 00:00 UTC(フェーズ43: アクセスURL再送フローのHTTPエントリポイント
`receive_resend_request()`を設計し、prototype/access_url_resend_handler.pyにコード化した)
