# 自動再送が効かないエントリポイントのエラー表示・再試行導線設計(フェーズ65)

runtime-dependency-switching-design.md(フェーズ64)5.3節が指摘した残課題「自動再送が効かない
エントリポイントのエラー表示・再試行導線の設計(web-form-ui-design.md相当文書の新規作成)」に
対応する。机上設計であり実際のフォーム実装・操作感検証は未着手。

## 1. 前提の整理

- 本venture全体のCloud Run functions境界は4関数(runtime-dependency-switching-design.md
  3節で確定): `submit_event_form`・`handle_stripe_webhook`・`get_result_page`・`submit_inquiry`。
- `handle_stripe_webhook`はStripe側の自動再送機構に委ねるため、ブラウザ向けのエラー表示・
  再試行導線は対象外(runtime-dependency-switching-design.md 5.3節)。
- 本文書が対象とするのは残り3関数で、いずれもエンドユーザーのブラウザから直接呼ばれる
  HTTPSトリガーであり、例外伝播時は5xxがそのままブラウザに返る。送信元側の自動再送が
  無いため、申込者・問い合わせ者が自力で再試行できる導線をフロントエンド側に用意する
  必要がある。

## 2. 3関数共通の方針: 「状態を残さない操作は即時再試行、状態を変える操作は確認してから再試行」

3関数は失敗時の意味合いが異なるため、一律の「再試行ボタン」ではなく関数ごとに導線を分ける。

- **`get_result_page`(結果ページ表示、読み取りのみ)**: 失敗しても`one_time_draft`側の状態は
  変化しない単純な読み取り操作のため、ページ下部に「再読み込み」ボタンを常設し、押すと
  同一URLへの再アクセスを即時に行う。二重実行の懸念自体が存在しない。
- **`submit_inquiry`(問い合わせ送信、`inquiry/{inquiry_id}`への新規書き込み)**: 失敗時に
  「もう一度送信」をそのまま許すと、実際にはサーバー側で書き込みが成功していたのに
  ブラウザ側がタイムアウト等で5xx相当の表示になったケースで二重送信(同一内容の
  `inquiry`ドキュメントが2件作成される)が起こり得る。inquiry-form-ui-draft.md(フェーズ52)
  の送信フォームに、送信ボタン押下時にクライアント側で生成する`idempotency_key`
  (UUID4、ボタン押下ごとに1つ)を追加し、再試行時は同じキーを使い回す設計とする
  (バックエンド側で`idempotency_key`の重複を検知した場合の扱いは4節で後述)。エラー表示は
  「送信に失敗しました。もう一度送信しますか?」の確認付きボタンとし、即時の無確認再送は
  行わない。
- **`submit_event_form`(主催者の申込フォーム送信、`one_time_draft/{draft_id}`への新規作成
  +Stripe Checkout Sessionの発行)**: 3関数のうち最も再試行の扱いが難しい。one-time-checkout-
  no-account-design.md(フェーズ10)2節の処理フローにより、この関数は(a)`draft_id`発行・
  `one_time_draft`への保存、(b)Stripe Checkout Session発行、の2段階を内部で行うため、
  (a)が成功し(b)で失敗した場合、ブラウザには5xxが返るが`one_time_draft`には
  `awaiting_payment`状態のドキュメントが既に存在する「孤立ドラフト」が生まれ得る。素朴な
  「もう一度送信」は、同じ入力内容でもう1件`draft_id`を発行してしまい、孤立ドラフトが
  増え続ける。これを避けるため、`submit_inquiry`と同様にクライアント側で`idempotency_key`
  を発行し送信する設計とする。

## 3. エラー表示文言の方針

- 3関数共通で、技術的なエラーコード(5xx等)をそのまま表示せず、「送信できませんでした。
  通信状況をご確認のうえ、もう一度お試しください」という利用者向けの汎用文言を表示する
  (厳守事項として他`llm-system-prompt-draft.md`等で確立済みの「推測で埋めない」方針とは
  別論点だが、技術詳細の露出を避ける点は本ventureの他文書と同じ設計姿勢)。
- `submit_event_form`のみ、孤立ドラフトが疑われる場合(同一`idempotency_key`での再送が
  バックエンド側で検知された場合、4節)に、「前回の送信が処理中の可能性があります」という
  追加の注意文言を表示し、二重課金の不安を利用者に抱かせたまま再送させない。

## 4. バックエンド側の`idempotency_key`重複検知(方針のみ、実装は次回以降)

- `submit_event_form`・`submit_inquiry`はいずれも、受信した`idempotency_key`を
  `one_time_draft`/`inquiry`の各ドキュメントのフィールドとして保存し、新規作成前に
  同一`idempotency_key`を持つ既存ドキュメントの有無を確認する(存在する場合は新規作成を
  スキップし、既存ドキュメントの`draft_id`/`inquiry_id`をそのまま応答する)設計とする。
- 本フェーズは設計のみであり、Firestoreクエリ実装(`idempotency_key`に対する検索、複合
  インデックスの要否含む)は、runtime-dependency-switching-design.md同様、実
  `google-cloud-firestore`ライブラリ導入とセットで行う結合実装フェーズに持ち越す。

## 5. 未検証・残課題

- `idempotency_key`の有効期間(いつまで重複とみなすか)を`one_time_draft`のTTL(24時間、
  result-page-ttl-access-design.md)と揃えるかどうかは次回検討課題とする。
- 実際のフォーム実装(ボタン配置・確認ダイアログの具体的なUI)・操作感検証は未着手。
- 3関数いずれも、ネットワーク完全切断(リクエスト自体がサーバーに到達しない場合)と
  サーバー側5xx(到達したが処理失敗)をブラウザ側で区別できないため、表示文言は両者を
  区別せず統一する前提とした。この前提の妥当性は次回検討課題とする。

最終更新: 2026-10-26 23:00 UTC(フェーズ65: runtime-dependency-switching-design.mdフェーズ64
次回候補(1)「自動再送が効かないエントリポイントのエラー表示・再試行導線の設計」に対応し、
本文書を新規作成。本venture固有の3関数(`get_result_page`・`submit_inquiry`・
`submit_event_form`)について、読み取りのみ/新規書き込みのみ/2段階処理という性質の違いに
応じた再試行導線を設計し、`submit_event_form`の孤立ドラフトリスクに対する`idempotency_key`
方式を提案した。コード変更なし、回帰確認として`python3 -m unittest discover -s prototype -p
"test_*.py"`(50件、変更なし)・`python3 schema/validate_test_cases.py`(22件、変更なし)を
実行しいずれも変更なしでパスすることを確認した(回帰なし)。承認が必要なアクション(支払い・
アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。
次回候補: (1)`idempotency_key`の重複検知ロジックのFirestoreクエリ設計(複合インデックスの
要否含む)、(2)承認待ち事項(候補1〈奈良NEVER LAND〉への連絡等)がオーナーから承認された
場合はその着手、(3)他venture・アイデア領域の前進。)
