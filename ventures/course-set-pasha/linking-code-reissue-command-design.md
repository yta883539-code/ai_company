# 連携コード再発行コマンド設計(フェーズ388)

line-user-id-linking-design.md 3節・line-user-id-linking-design.md フェーズ387是正箇所が残した
「連携コードの有効期限(24時間)切れ・使用済み後に再取得するには、一度LINE公式アカウントを
ブロックしてから再度『友だち追加』する必要がある」という運用は、契約者にとって手間が大きい。
follow-event-welcome-message-design.md フェーズ387の次回候補(2)で将来の選択肢として挙げられた
「テキストコマンド(例:「コード再発行」)での再発行機能」を具体化する。

## 1. 核心のポイント: 実は`follow`イベントは不要

`issue_linking_code_on_follow()`という関数名が示すとおり、これまでの設計は「コードの発行は
`follow`イベントの中でしか行えない」ことを前提にしていた。しかし実際には、連携コードの発行に
必要なのは`user_id`だけであり、LINEの通常の`message`イベント(テキストメッセージ送信)の
webhookペイロードにも送信者の`user_id`は常に含まれている(`event["source"]["userId"]`)。

つまり「ブロック→再追加」で`follow`イベントを再発火させる必要はなく、契約者が友だち追加済みの
トーク画面から単に「コード再発行」とテキストを送るだけで、同じ`issue_linking_code_on_follow()`を
`message`イベントのハンドラ内から呼び出せば再発行が完結する。これはowner-faq-routing-design.mdが
「FAQ」「Q1」〜「Q6」というテキストコマンドをprocess_memo_event()内でLLM呼び出し前に直接処理する
のと同じパターンであり、新規のイベント種別・外部API呼び出しは一切不要である。

## 2. コマンド仕様

- トリガー文言: 「コード再発行」(全角)。owner-faq-routing-design.md 6節と同じ理由(日本語入力
  端末のIME既定が全角モードであることが多い)で、`unicodedata.normalize("NFKC", text)`を
  `strip()`の前段に適用してから比較する。半角「ｺｰﻄﻟ再発行」のような入力や前後の空白も
  これで吸収する。大文字小文字の区別は対象文字列が日本語のため実質的に影響しない。
- 一致判定は完全一致(owner_faq_router.pyの`is_owner_faq_menu_trigger()`と同じ方式)とし、
  「コード再発行して」のような部分一致・自然文は対象にしない(2.6節のintent_classifier経由の
  自由文対応はスコープ外、本コマンドは厳密なキーワード一致のみを扱う)。

## 3. 処理フロー

1. 受信した`message`イベントの本文が上記トリガーと一致した場合、
   `delete_pending_links_for_user(user_id, linking_store)`で、そのユーザー宛に発行済み・
   未使用の古いコードを(あれば)先に削除する。これにより古いコードが使用済みコードと紐づく
   `user_id`に対して複数同時に有効な状態になるのを防ぐ(design上は複数同時発行を禁止する
   要件はないが、「どのコードが最新か」を契約者・運営者双方が混乱しないよう1人1コードに保つ)。
2. `issue_linking_code_on_follow(user_id, linking_store, now, rng)`で新しいコードを発行する
   (既存ロジックをそのまま再利用、follow-event-welcome-message-design.mdのウェルカムメッセージ
   発行経路と全く同じ関数)。
3. `render_linking_code_reissue_message(code)`で返信文を組み立てて返信する。
   「新しい連携コードを発行しました: {code}(24時間有効)申込フォームにこのコードを
   入力してください。」という趣旨とし、follow時のウェルカムメッセージと文体を揃える。

## 4. process_memo_event()への組み込み方針(フェーズ389で配線完了)

cloud_function_webhook.pyのprocess_memo_event()に、2.5節(FAQコマンド判定)より手前の
「2.45節」として本コマンドの判定を追加した。`linking_store`が渡されており(未接続時は
既存の呼び出し元の挙動を変えず素通りする安全側フォールバック)、かつ本文が「コード再発行」
(NFKC正規化+strip()後の完全一致)、かつ`source.userId`が取得できる場合のみ、LLM呼び出し・
月間カウント増分を一切行わず、`reissue_linking_code()`(3節で追加済みの純粋関数、
`delete_pending_links_for_user()`→`issue_linking_code_on_follow()`の内部再利用)で新しい
コードを発行し、`render_linking_code_reissue_message()`の案内文を返信して処理を終える。
`rng`は`process_follow_event()`と同じパターン(`rng if rng is not None else random.Random()`)
で解決し、新規の引数`rng: Optional[RandomChoiceSource] = None`をprocess_memo_event()の
シグネチャに追加した(既存呼び出し元は省略時は従来通りの既定動作のまま、挙動は変わらない)。
結果は`MemoProcessResult.reissued_linking_code`(新規フィールド、Optional[str])に発行済み
コードを設定する。

既存テスト910件に加え、`ProcessMemoEventLinkingCodeReissueCommandTest`として8件
(通常発行・NFKC正規化・古いコードの削除・`linking_store`未接続時のフォールスルー・
`userId`欠落時のフォールスルー・無関係テキストのフォールスルー・月間カウント非増分・
生成一時停止判定への優先)を追加し、`python3 -m unittest discover -s prototype -p
"test_*.py"`で全927件パス、`python3 schema/validate_test_cases.py`22件もいずれもパス
(回帰なし)を確認した。

## 5. 既存ドキュメントとの整合

line-user-id-linking-design.md 3節の「期限切れの場合は『一度このアカウントをブロックのうえ
再度「友だち追加」していただくと新しいコードが届きます』という趣旨の案内」は、本設計により
不要になる可能性が高い(本コマンドの配線後は「『コード再発行』と送信してください」という
案内に差し替えられる)。ただし実際の案内文言の差し替えは4節の配線完了後に行うべきため、
本フェーズでは3節に本ドキュメントへの参照のみを追記し、文言自体の差し替えは次回候補とした。

## 残課題

- フォーム提出エラーメッセージ(Googleフォーム側、実フォーム未作成のため文言自体は未確定)
  にも「コード再発行とトークに送信」という案内を反映する(フォーム実設定自体はオーナー承認待ち)。
- line-user-id-linking-design.md 3節の案内文言の差し替え(配線完了、次回候補)。
- 実LINE Messaging API接続・実Firestore接続はいずれもオーナー承認待ち(pending-approval.md参照)
  のため、本フェーズ(389)で行ったのはprocess_memo_event()への配線とその単体テストのみ。
