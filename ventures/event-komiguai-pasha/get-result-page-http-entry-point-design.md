# get_result_page Cloud Run functionの実HTTPSトリガー配線 設計(フェーズ112)

フェーズ111次回候補(2)に対応する。本venture全体の4 Cloud Run functions
(`submit_event_form`・`submit_inquiry`・`handle_stripe_webhook`・`get_result_page`)の
うち最後の1関数。結果ページ`/result/{draft_id}`(result-page-ttl-access-design.md
フェーズ14・runtime-dependency-switching-design.mdフェーズ63)のHTTPSトリガー配線を
実コード化する。

## 1. 前提として発見したギャップ: 生成結果本体が永続化されていなかった

設計に着手する前に`generation_retry_and_refund.process_generation_after_payment()`
(フェーズ100前後)を確認したところ、生成成功時に呼んでいた
`draft_store.mark_generation_result(draft_id, status=output.get("status", "generated"))`
は`status`のみを書き込み、LLMの構造化出力本体(schema/output.schema.json準拠の
`checklist`/`staffing_plan`/`notice_board_text`/`near_miss_record_template`/
`fee_inquiry_note`等)自体を`OneTimeDraft`側に保存していなかった。結果ページが
`status="generated"`時に表示すべき内容が、これでは参照先が存在しないことになる
(mvp-flow-draft.md・result-page-ttl-access-design.mdいずれも「結果を表示する」ことを
前提としており、本ギャップはいずれの既存設計文書でも「残課題」として明示されていな
かった、暗黙の前提漏れ)。

本フェーズでまず以下の対応を行った(get_result_page自体の設計に先行する前提整備):

- `stripe_webhook.OneTimeDraft`に`generated_output: Optional[dict] = None`フィールドを
  追加。
- `OneTimeDraftStoreProtocol.mark_generation_result()`・`InMemoryOneTimeDraftStore.
  mark_generation_result()`に`output: Optional[dict] = None`引数を追加し、指定時は
  `generated_output`へそのまま保存する(省略時は既存値を変更しない、既存呼び出し元との
  後方互換を維持)。
- `generation_retry_and_refund.process_generation_after_payment()`の生成成功分岐で
  `mark_generation_result(draft_id, status=..., output=output)`と出力dict本体も渡すよう
  修正した。

## 2. `get_result_page`の処理方針

既出3関数(`submit_inquiry`・`submit_event_form`・`handle_stripe_webhook`)と異なり、
本関数はGET(`/result/{draft_id}`、ブラウザが直接開く結果ページ)であり、JSON POST
本文を持たない。`draft_id`はURLパス末尾のセグメントとして渡される
(checkout-session-success-cancel-url-design.mdフェーズ48の`success_url`構成どおり)。

- `receive_result_page_request(request_path, *, draft_store)`が、
  (1) `request_path`から`draft_id`を抽出し、(2) `draft_store.get(draft_id)`を呼び、
  (3) result-page-ttl-access-design.md 3節の3状態分岐に沿ってレスポンスを組み立てる。
- 3状態分岐(design 3節の番号と対応):
  1. ドキュメントが存在し`status="generated"`: `page_state="generated"`、
     `output=draft.generated_output`を返す。
  2. ドキュメントが存在するが`status`が以下のいずれか:
     - `"out_of_scope"` / `"insufficient_input"`: LLM出力自体は正常系の分岐結果
       (`output.schema.json`どおり当該ステータス時は`generated_output`に
       `out_of_scope_message`/`missing_fields_request`が入っている)であるため、
       `page_state`をそのままstatus値とし、`output=draft.generated_output`を返す
       (`submit_event_form`のinsufficient_input応答と同じ「主催者側の入力・対象外の
       問い合わせであり異常ではない」という位置づけを結果ページ側でも踏襲する)。
     - `"awaiting_payment"`: 決済Webhook受信前、またはWebhook受信済みだがLLM生成が
       未完了(`handle_stripe_webhook`が`mark_payment_confirmed()`のみを呼び`status`
       自体は変更しない設計、stripe_webhook.py参照)の両方を指す。本フェーズでは両者を
       区別する追加フィールドを設計しない(次回候補4節参照)。`page_state="generating"`
       を返す。
     - `"generation_failed"`: リトライを尽くして失敗し返金処理待ちの状態。
       `page_state="generation_failed"`を返す(操作上は「生成に失敗し返金対応中」の
       案内を主催者に表示する想定、文面自体の確定はoperational-message-templates-
       draft.md側の次回候補とする)。
     - `"refunded"`: 返金完了。`page_state="refunded"`を返す。
     - `"expired_after_payment"`: `mark_expired_after_payment()`が呼ばれた状態
       (呼び出し元は現時点で未実装、tech-stack.md参照)。`page_state=
       "expired_after_payment"`を返す。
  3. ドキュメントが存在しない(TTL失効済み、または`draft_id`自体が無効):
     `page_state="ttl_expired_or_invalid"`を返す。design 3節(3)の案内文言
     (「保存期間〈24時間〉が終了したため閲覧できません」+問い合わせフォーム導線)は
     文言自体の最終的な表示はフロントエンド側の責務とし、本関数は`page_state`のみを
     返す(`submit_inquiry`・`submit_event_form`と同じ「レスポンスの意味分岐までが
     バックエンドの責務、文言はクライアント側テンプレートに委ねる」構成を踏襲)。
- HTTPステータスコードはいずれの`page_state`でも200を返す(design 3節(3)が「通常の
  404ではなく専用の案内を表示する」ことを明示的に要求しているため、ドキュメント
  不存在時も404にはしない。`draft_id`がURLパスから全く抽出できない場合〈空文字列等、
  想定外の呼び出し〉のみ400を返す)。

## 3. 実装

- `prototype/result_page_entry.py`:
  - `ResultPageResult`(dataclass、`status_code: int`・`body: dict`・
    `to_json_body() -> str`、既出エントリポイントと同型)。
  - `_extract_draft_id_from_path(request_path: str) -> Optional[str]`:
    `/result/{draft_id}`形式のパスから末尾セグメントを取り出す。先頭・末尾の`/`の
    有無を吸収し、セグメントが空文字列の場合は`None`を返す。
  - `receive_result_page_request(request_path, *, draft_store) -> ResultPageResult`:
    2節の分岐を実装する。
- `prototype/cloud_function_get_result_page.py`:
  - `get_get_result_page_runtime_dependencies()`: 他3関数と同じ位置づけで、実Firestore
    接続前は`InMemoryOneTimeDraftStore()`を返す(runtime-dependency-switching-design.md
    フェーズ63が確定した、本venture共通の「常にInMemoryを返す」既定方針どおり)。
  - `main(request)`: `request.path`を取り出し`receive_result_page_request()`へ委譲する
    薄い配線(`functions_framework`のFlask Request互換オブジェクトは`.path`属性を持つ
    ため、他3関数の`request.get_data()`に相当する最小限の取り出しのみ)。

## 4. 残課題・次回候補

- 2節の`"awaiting_payment"`が「決済待ち」と「決済済み生成中」の2意味を兼ねている点は、
  本フェーズでは`page_state="generating"`に統合したままとした。両者を主催者向けの
  表示上区別する必要が具体的に生じた場合(例: 決済自体が完了していないのに結果ページ
  URLが開かれるケースが実際に想定されるか)に、`mark_payment_confirmed()`側で
  `status`自体を`"awaiting_payment"`から`"payment_confirmed"`等へ遷移させる設計変更を
  検討する(stripe_webhook.py・handle-stripe-webhook-http-entry-point-design.mdフェーズ
  111双方への影響があるため、本フェーズでは着手しない)。
- `page_state`ごとの実際の表示文言(日本語の案内文・問い合わせフォームへのリンク)は
  本フェーズでは返さず、`page_state`の値のみを返す設計とした。フロントエンド
  (landing-page/配下、または別途のテンプレート)側での文言当て込みは次回候補とする。
- 本venture全体の4 Cloud Run functionsが本フェーズで全て実HTTPSトリガー配線済みに
  なった。承認待ち事項(実GCPプロジェクト作成等、pending-approval.md参照)が
  オーナーから承認された場合、4関数いずれも`get_*_runtime_dependencies()`の中身を
  実Firestore/実Stripe接続に差し替えるだけで接続できる状態にある。

最終更新: 2026-11-10 23:00 UTC(フェーズ112: 生成結果本体の永続化ギャップを発見・
解消〈`OneTimeDraft.generated_output`・`mark_generation_result(output=...)`新設〉した
上で、`get_result_page`Cloud Run functionの実HTTPSトリガー配線を実コード化。本venture
全4 Cloud Run functionsが全て配線済みとなった)
