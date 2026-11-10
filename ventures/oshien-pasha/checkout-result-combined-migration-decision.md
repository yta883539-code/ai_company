# 結果ページHTTPハンドラーのcombined版移行方針

作成日: 2026-11-10(フェーズ108)

フェーズ107次回候補(1)「結果ページ側のHTTPハンドラーを実際に
`receive_checkout_result_request_combined()`へ切り替える移行手順の検討(既存の月額
フリーパス専用呼び出し元がどこにあるか棚卸しが必要、フェーズ106次回候補(2)から持ち越し)」
に対応する。

## 1. 棚卸し結果: 本番側の呼び出し元は存在しない

`grep -rn "receive_checkout_result_request\b" prototype/`で`prototype/`配下を確認した
結果、`receive_checkout_result_request()`(月額フリーパス専用、フェーズ100)の呼び出し元は
`prototype/test_checkout_result_page_handler.py`(自身の回帰テスト)のみであり、それ以外の
呼び出し元(本番相当のコード)は存在しなかった。

これはcheckout-result-http-entry-point-design.md(フェーズ100)4節の残課題に明記されている
とおり、Cloud Functionsの実エントリポイント`main(request)`自体が「結果ページのフロントエンド
実装(オーナー承認待ち事項)確定後に行う」とされ、本フェーズ時点でもまだ着手されていない
(`prototype/`配下にCloud Functions用の`main(request)`相当のファイルが無い)ためである。
つまり「既存の月額フリーパス専用呼び出し元」という前提自体が、フェーズ106次回候補(2)を
書いた時点での推測であり、実際には存在しなかった(フェーズ107の`receive_generation_
request()`棚卸しで判明した「次回候補の前提が実際にはまだ存在していなかった」パターンと
同型)。

## 2. 決定: 新規`main(request)`配線時はcombined版のみを直接使う

本番呼び出し元が存在しない以上、「段階的な切り替え」自体が不要である。将来
`main(request)`(実Stripe API接続・実Cloud Functionsデプロイを伴う、いずれもオーナー承認
待ち)を配線する際は、最初から`receive_checkout_result_request_combined()`
(`CombinedPassLookup`経由、都度プラン・月額フリーパス両対応)のみを呼び出す設計とし、
`receive_checkout_result_request()`(月額フリーパス専用)を経由する実装は行わない。

- `receive_checkout_result_request()`・`resolve_checkout_result()`(フェーズ98・100)は
  削除しない。既存の回帰テスト(`ReceiveCheckoutResultRequestTests`・
  `ResolveCheckoutResultTests`)が、月額フリーパス専用の分岐ロジック自体(Webhook未到達時の
  ポーリング・リトライ回数・404変換)の仕様書として機能しており、combined版の内部実装
  (`resolve_checkout_result_combined`)も同じポーリング構造を再利用しているため、regression
  検知の価値を保つ。
- 本venture他文書(access-url-resend-http-entry-point-design.md等)が踏襲してきた
  「既存の呼び出し元への破壊的変更を避ける」方針と矛盾しない。呼び出し元が存在しない
  レガシー関数は「使われていないので削除する」でも「使われる前提で互換性を保つ」でもなく、
  「テストの仕様書として保持しつつ、新規配線では参照しない」という第三の扱いとする。

## 3. 両関数の位置づけの明文化

`prototype/checkout_result_page_handler.py`の各関数のdocstringに、上記決定を反映した
一文を追記する(4節参照)。`CombinedPassLookupProtocol`・`CombinedPassLookup`・
`resolve_checkout_result_combined`・`receive_checkout_result_request_combined`側の
docstringは変更しない(フェーズ106時点の記述がすでに「こちらを新規導入する」という方針を
明記済みのため)。

## 4. 残課題

- `main(request)`自体の新規実装は、結果ページのフロントエンド実装確定後(オーナー承認待ち
  事項の範囲内)に行う。実装時は本フェーズの決定(2節)に従い、combined版のみを呼び出す。
- 入力フォーム自体のUI/UX設計(フェーズ106次回候補(2)から持ち越し)。
- 実Stripeアカウント・実GCPプロジェクト・実Firestore接続はオーナー承認待ち
  (pending-approval.md参照)のため引き続き着手不可。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成・
実際のHTTPデプロイ自体はオーナー承認が必要なアクションに該当するため、本メモは調査結果の
記録と今後の設計方針の決定に留める(外部サービスへの接続は一切行っていない)。承認が必要な
アクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは発生していないため
pending-approval.mdへの新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

最終更新: 2026-11-10 16:00 UTC(フェーズ108: 新規作成。`receive_checkout_result_request()`
の本番側呼び出し元が実際には存在しないことを確認し、将来`main(request)`配線時はcombined版
のみを直接使う方針を決定した)
