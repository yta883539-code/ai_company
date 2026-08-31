# オンボーディング完了メッセージ設計(残課題(b): 常設セルフサービスアップグレードリンク)

作成日: 2026-08-29(フェーズ続き140)

checkout-initiation-flow-design.md 1節「トリガーのタイミング」(b)で
「オンボーディング完了メッセージ等に常設する、いつでも有料プランへ切り替えられる
セルフサービスリンク(現時点では該当メッセージ自体が未設計。次の課題として残す)」として
残っていた課題に着手する。course-set-pasha/checkout-initiation-flow-design.mdでも同種の
項目(b)が「本ドキュメントの範囲外」として未設計のまま残っており、姉妹ventureにも
流用可能な先例が無いため、本ドキュメントで新規に設計する。

## 1. 送信タイミングの選定

onboarding-guide.mdの6ステップのうち、システムが自動的にイベントとして検知できるのは
ステップ3(営業情報・メニューの初期設定)の完了のみである。ステップ2(LINE公式アカウント
連携)・ステップ4(接続テスト)・ステップ5(本番公開)はいずれもオーナーの手動判断や
LINE Developersコンソール等の外部システム操作を伴い、本システム側のイベントとしては
検知できない。

**結論**: onboarding-guide.mdの「MVPの最低限必須項目」(営業曜日・営業時間・予約枠の間隔・
同時受付可能数・メニュー一覧最低1件)が**初めて全て入力された時点**を「オンボーディング
完了」とみなし、その直後に本メッセージを送信する。

- 発火は店舗全体で1回のみ。2回目以降の設定変更(既に必須項目が揃った状態での再編集・
  メニュー追加等)では発火しない。first-booking-self-check-notification-design.mdが採用した
  「店舗全体で最初の1回のみ」という既存パターンを踏襲する(理由も同じ: 毎回送ると煩わしい
  通知になるため)。
- 送信対象はオーナー本人(=決済導線の`user_id`と同一人物)。

## 2. トライアル起算点・トライアル終了レポートとの関係(スコープの整理)

pricing-plan.mdのトライアル条件(14日間 or 予約20件到達のいずれか早い方、カード登録なし)の
起算点自体は、本メッセージの送信有無とは独立している。起算点は「店舗全体で最初の予約確定時」
(申込〈ステップ1〉でもオンボーディング完了〈ステップ3完了、本メッセージの送信時点〉でも
ない)として、trial-start-anchor-decision.mdで別途確定した。

本メッセージは「トライアル終了を待たずに、いつでも能動的にアップグレードできる案内」で
あり、トライアル終了時に`trial_end_report_scheduler.py`が送る利用実績レポート+プラン案内
(checkout-initiation-flow-design.md 1節のトリガー(a))とは独立した経路(b)として並存する。
(a)は「終了したので選んでください」という受動的な案内、(b)は「気が向いたらいつでもどうぞ」
という常設リンクという役割分担であり、文言のトーンもそれに合わせて変える。

## 3. メッセージ文言(3トーン)

message-tone-variants.mdの出し分けルールに従い、`trial_end_report_scheduler.py`と同じ構造
(固定の案内文+決済ページURLのプレースホルダ、`{決済ページURL}`)で設計する。(a)の
トライアル終了レポートと違い、利用実績の集計値は持たない(まだトライアル開始直後で
実績が薄いため、実績を見せる文脈ではなく「準備が整った」ことを伝える文脈にする)。

- フォーマル:
  ```
  【予約とれる君】設定が完了いたしました

  営業情報・メニューのご登録、お疲れさまでございました。
  これで顧客対応の準備が整いましたので、このままトライアルをお試しくださいませ。

  なお、トライアル期間中でも、いつでも下記より有料プランへお切り替えいただけます。
  ご登録いただくまでは自動課金されませんのでご安心ください。

  ▼ プランを見る・登録する
  {決済ページURL}

  ご不明点はこのトークルームにご返信くださいませ。
  ```
- standard(既定):
  ```
  【予約とれる君】設定が完了しました

  営業情報・メニューのご登録、お疲れさまでした。
  これで顧客対応の準備が整いましたので、このままトライアルをお試しください。

  なお、トライアル期間中でも、いつでも下記から有料プランへ切り替えられます。
  ご登録いただくまでは自動課金されませんのでご安心ください。

  ▼ プランを見る・登録する
  {決済ページURL}

  ご不明点はこのトークルームにご返信ください。
  ```
- カジュアル:
  ```
  【予約とれる君】設定完了しました🎉

  営業情報・メニューの登録、おつかれさまでした!
  これで顧客対応の準備はバッチリです。このままトライアルを試してみてくださいね。

  トライアル中でも、いつでも下記から有料プランに切り替えられます。
  登録するまでは自動課金されないので安心してください。

  ▼ プランを見る・登録する
  {決済ページURL}

  わからないことがあれば、このトークルームに返信してください!
  ```

3トーン共通で変えないもの(message-tone-variants.md準拠): 「トライアル」「有料プラン」の
語は言い換えない、決済ページURLはそのまま埋め込む、1メッセージ1用件。

## 4. プロトタイプ実装方針

`trial_end_report_scheduler.py`の`render_trial_end_report_message()`と同じ考え方で、
`prototype/onboarding_completion_message.py`に純粋関数として実装する。

- `render_onboarding_completion_message(payment_page_url, tone="standard") -> str`
  - `payment_page_url`が空文字列・Noneの場合は`ValueError`。
  - 未知の`tone`はstandardにフォールバックする(既存の`_render_by_tone`と同じ安全側挙動)。
- 発火判定(「MVPの最低限必須項目が初めて全て揃ったか」の判定・1回のみ発火の制御)は、
  `ConversationFlowStateMachine`側ではなく店舗設定の保存処理側の責務になるため、
  `first_booking_self_check`の`consume_*()`パターンとは別に、店舗プロフィールストア側
  (`store_profile_store.py`)に判定ロジックを追加するのが自然と考えられるが、店舗設定の
  保存処理自体(owner-settings-wireframe.mdのフォーム保存)がまだ実装されていないため、
  発火判定の実装は本ドキュメントのスコープ外とし、メッセージ文言の組み立て部分のみを
  先行して実装する。

`payment_page_url`には、checkout-initiation-flow-design.md 5節の
`build_checkout_session_params()`が組み立てるCheckout Session作成エンドポイントを呼び出す
LIFFページのURLを渡す想定(実LIFF登録後に確定する値のプレースホルダ)。

## 残課題

- (解消済み 2026-08-31定例更新・フェーズ続き158: 前項の残課題だった
  「owner-settings-wireframe.mdのフォーム保存処理自体からの実呼び出し配線」に、
  MVP必須項目の判定に必要な最小範囲で着手した(store-settings-save-flow-design.md
  新規作成)。GAS Webhookペイロード(営業時間の生値・定休日・予約枠の間隔/同時受付
  可能数の表示文字列・メニュー一覧)を検証・正規化し、`stores/{storeId}`への書き込みと
  `handle_onboarding_completion_message_dispatch()`呼び出しまでを結線する
  `prototype/store_settings_save_flow.py`の`handle_store_settings_submission()`を
  新規実装した。曜日別営業時間の複数区間バリデーション・臨時休業日・メッセージトーン・
  常連客閾値・FAQ情報の保存処理は別課題として明示的に対象外とした
  (store-settings-save-flow-design.md 2節)。テスト10件追加、venture全体422件全件パス・
  schema検証25件パスを確認した。残る課題はGoogleフォーム自体の作成・GAS配置
  (外部サービスへの実設定、オーナー承認待ち)と、対象外とした各項目の保存処理設計。
  承認不要な設計・実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は
  今回発生していないためpending-approval.mdへの追記なし。)
- (解消済み 2026-08-31定例更新・フェーズ続き157: 上記「firestore-data-model.md 1節に
  `slotIntervalMinutes`・`concurrentCapacity`がまだ定義されていない」という記載は、
  実際には同じフェーズ続き155の中で追加済みだった記載漏れと判明したため訂正した
  (firestore-data-model.md 92・97行目参照)。あわせて、`evaluate_onboarding_completion_
  message_dispatch()`(判定)と`render_onboarding_completion_message()`(整形)を
  実際につなぎ、`LinePushClient`での送信呼び出しまで結線する配線本体
  `prototype/cloud_function_send_onboarding_completion_message.py`の
  `handle_onboarding_completion_message_dispatch()`を新規実装した。送信失敗
  (`LinePushDeliveryError`)時も判定側の送信済みフラグは既に立っているため再送されない
  制約は、`consume_first_booking_self_check()`と同じMVPスコープの割り切りとして
  そのまま踏襲する方針とした。テスト5件追加、venture全体412件全件パス・schema検証25件
  パスを確認した。残る課題はowner-settings-wireframe.mdのフォーム保存処理自体
  (実Firestore書き込み・実UI、ホスティング基盤確定後・オーナー承認待ち)からの実呼び出し
  配線のみ。承認不要な実装・テスト追加・ドキュメント整理のみで、外部サービスへの公開・
  アカウント作成・支払い等は今回発生していないためpending-approval.mdへの追記なし。)
- (解消済み 2026-08-30定例更新・フェーズ続き155: 「MVPの最低限必須項目が初めて全て
  揃ったか」を判定し1回だけ発火させる処理本体を実装した
  (`prototype/store_profile_store.py`の`evaluate_onboarding_completion_message_dispatch()`)。
  `InMemoryStoreProfileStore`に`is_onboarding_completion_message_sent()`/
  `mark_onboarding_completion_message_sent()`を追加し、`first_booking_self_check`の
  `consume_*()`と同じ「店舗全体で最初の1回のみ」冪等性パターンを踏襲した。owner-settings-
  wireframe.mdのフォーム保存処理自体(実Firestore書き込み)はまだ実装されていないため、
  呼び出し元は「保存後の最新設定値(営業時間の有無・予約枠の間隔・同時受付可能数・
  メニュー件数)を渡して判定結果を受け取る」という結線点までを先行して用意した形。
  テスト11件追加、venture全体407件全件パス・schema検証25件パスを確認した。承認不要な
  実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い等は今回発生
  していないためpending-approval.mdへの追記なし。)
- (解消済み 2026-08-29定例更新: トライアル起算点は「店舗全体で最初の予約確定時」として
  `trial-start-anchor-decision.md`で確定した。)
- `payment_page_url`の実URLへの差し替えは、他のプレースホルダ(`success_url`・`basic_id`等)と
  同様、実LIFF登録・LINE公式アカウント開設(オーナー承認待ち)後に行う。
- firestore-data-model.md 1節`stores/{storeId}`ドキュメントには、owner-settings-
  wireframe.mdで言及されている「予約枠の間隔」「同時受付可能数」に対応するフィールド
  (`slotIntervalMinutes`・`concurrentCapacity`)がまだ定義されていないことが今回の実装で
  判明した。`evaluate_onboarding_completion_message_dispatch()`はこれらを呼び出し元から
  渡される値として受け取る設計にしたため実装自体はブロックされないが、実際のフォーム
  保存処理(owner-settings-wireframe.md)実装時にはこの2フィールドをFirestoreスキーマへ
  追加する必要がある。次回以降の課題として残す。
