# 屋号・連絡先メールアドレス・想定利用形態の収集経路設計(フェーズ続き316)

onboarding-guide.md 2節(フェーズ続き314是正)が「未確定」として持ち越していた、
屋号(工房名)・連絡先メールアドレス・想定利用形態(個人利用/複数職人での共同利用)の
実際の収集経路を本ドキュメントで決定する。

**本ドキュメントは収集経路の設計決定のみを行うものであり、実装(Firestoreフィールド追加・
Webhookハンドラへの配線)自体は次フェーズ以降の課題として残す。実LINE公式アカウントとの
接続・実際の職人への送信は一切行わない。**

## 1. 決定: 別途フォーム新設ではなく、LINEトーク上の追加質問応答で収集する

craftsman-account-linking-design.md 1節は、本ventureがcourse-set-pashaの
「LINE友だち追加が先」方式を踏襲した積極的理由を「低頻度・高単価の受注特性〈月数件〜
十数件〉では、フォーム入力よりLINE上で完結する導線の方が職人にとって手数が少ないと
考えられるため」と明記している。この理由は、連携コード交換そのものだけでなく、
その直後に必要になる屋号・連絡先メール・想定利用形態の収集にも等しく当てはまる。
別途Webフォームを新設する案は、

- 本venture唯一の顧客接点であるLINEトークに加えて新たなWeb資産(フォームページの作成・
  ホスティング・URL配布)を要し、aircon-pashaの「申込フォーム先行」方式との混同を招きうる
  (フェーズ続き314で是正した「存在しない申込フォームへの言及」の再発リスク)、
- 低頻度・高単価の職人顧客にとって、LINEトークを一度離れて別のフォームを開く手間は、
  連携コード交換に次ぐ二度目の「導線の分岐」になり、course-set-pasha/aircon-pashaが
  申込フォーム方式を採る前提(フォームが唯一の入口で導線が一本道)とは異なり、本venture
  では逆に手数を増やす、

という2点でcraftsman-account-linking-design.md 1節の採用理由と整合しない。
したがって、**連携コード解決〈`create_workshop_from_linking_code()`〉成功直後、LINEトーク上で
3問を順に尋ねる追加質問応答方式**を採用する。

## 2. 全体フロー(案)

1. `create_workshop_from_linking_code()`成功時(workshop新規作成直後)、ウェルカムメッセージに
   続けて「工房名(屋号)を教えてください。個人で活動されている場合はお名前で構いません」
   という質問メッセージを送る。
2. 職人がテキストで返信すると、その内容を`workshop_name`として保存し(既存の
   `set_workshop_name()`をそのまま使う、新規フィールドは不要)、続けて「連絡先メール
   アドレスを教えてください(納品案内等の控えが必要な場合のみで構いません。不要な場合は
   「なし」とお送りください)」と尋ねる。
3. 返信を`contact_email`(新規フィールド、未設定時`None`)として保存し、「複数の職人で
   ご利用される予定はありますか?(「個人のみ」/「複数人で利用予定」のいずれかで
   お答えください)」と尋ねる。
4. 返信を`expected_usage_type`(新規フィールド、`"solo"` / `"multiple"` / 未分類時は
   自由記述をそのまま保存)として保存し、「ありがとうございます。続けて手順3(接続
   テスト)にお進みください」で手順3(onboarding-guide.md)へ案内する。

## 3. 状態管理の方針(本venture固有の注意点)

tech-stack.md・mvp-flow-draft.mdが明記する「本ventureの中核機能(受注内容整理メモ等の
生成)は会話状態を持たない単方向バッチ処理」という設計方針は、**本オンボーディング専用の
3問シーケンスには適用しない**。両者はスコープが異なる独立した状態である:

- 中核機能(メモ生成)は、入力メモ1件ごとに完結する決定的な処理であり、過去の会話履歴を
  LLMへの入力に含めない(プロンプト肥大化・文脈混線を避けるための設計)。
- 本オンボーディング質問応答は、LLMを介さない固定3問の進行管理(「どの質問を送った
  直後か」を`workshop_id`単位で1フィールド保持するだけ)であり、course-set-pasha/
  aircon-pashaの連携コード方式(`pending_links/{code}`)と同種の、ごく小さい決定的な
  状態機械にすぎない。

具体的には、新規フィールド`profile_collection_step`
(`"awaiting_name"` → `"awaiting_email"` → `"awaiting_usage_type"` → `"completed"`、
workshop新規作成時に`"awaiting_name"`で初期化)を`WorkshopStoreProtocol`に追加し、
Webhookハンドラが受信メッセージを「通常の受注メモ」として処理する前に、まず
`profile_collection_step`が`"completed"`以外かどうかを確認する分岐を設ける想定とする
(具体的な関数名・配線は次フェーズで設計)。

## 4. 残課題(次フェーズ候補)

- [フェーズ続き317で実装済み] `profile_collection_step`・`contact_email`・
  `expected_usage_type`の`WorkshopStoreProtocol`への追加、`InMemoryWorkshopStore`・
  `firestore_workshop_adapter.py`両方への実装。`set_members`(workshop新規作成の唯一の
  地点)が`profile_collection_step`を`"awaiting_name"`で初期化する。
  `test_firestore_workshop_adapter.py`に新規テスト8件追加(ロールバック・初期化・
  fail-closed〈未作成workshop_idはKeyError〉・既存フィールドとのmerge非衝突確認)、
  既存テストと合わせて325件・schema検証32件いずれもパス(回帰なし)。
- [フェーズ続き318で実装済み] Webhookハンドラ(`cloud_function_webhook.py`)への分岐配線。
  `process_memo_event()`冒頭(0.、1.のtext判定の前)で`user_profile_store`・
  `workshop_store`の両方が渡され、かつ`user_id`が既存workshopへ連携済みの場合に
  `profile_collection_step`を確認し、`"completed"`以外であれば`_process_profile_collection_
  reply()`(新設、LLM呼び出しなしの決定的な状態機械)へ即座に委譲する設計で実装した。
  連絡先メールアドレスを「なし」で回答された場合の取り扱い(`None`のまま、再質問しない、
  完全一致判定)も本フェーズであわせて文面確定・実装した(2節手順3の2択「個人のみ」/
  「複数人で利用予定」も同様に完全一致で`"solo"`/`"multiple"`へ正規化、それ以外は
  自由記述のまま保存)。この分岐配線により、`set_members`で新規作成される全workshopが
  デフォルトで`profile_collection_step="awaiting_name"`から始まる(フェーズ続き317)以上、
  既存テスト(process_memo_event()にuser_profile_store・workshop_storeの両方を渡す
  テスト、test_cloud_function_webhook.py内56箇所)は全て「3問シーケンス完了済み」の
  状態を前提としていたことが判明したため、各テストに`workshops.set_profile_collection_
  step(workshop_id, "completed")`を追加して前提を明示化した(実オンボーディング経路
  〈`create_workshop_from_linking_code()`〉を使う1テストも同様に是正)。新規テスト8件
  (3問シーケンス各ステップの正常遷移・「なし」回答・自由記述保存・completed後の通常
  フロー復帰・未連携user_idでの分岐スキップ)を追加し、既存テストの是正と合わせて
  test_cloud_function_webhook.py内446件・プロジェクト全体26ファイル・schema検証32件
  いずれもパス(回帰なし)を確認した。
- [フェーズ続き319で実装済み] 本節(2節)手順1「`create_workshop_from_linking_code()`
  成功時、ウェルカムメッセージ(=`LINKING_SUCCESS_MESSAGE`)に続けて『工房名(屋号)を
  教えてください。個人で活動されている場合はお名前で構いません』という質問メッセージを
  送る」が、フェーズ続き318のWebhook配線実装時に実装されていなかった(`LINKING_SUCCESS_
  MESSAGE`の文言が旧来の「依頼内容の簡単なメモを送ってください」のまま据え置かれていた)
  設計・実装間の食い違いを発見・是正した。新設の`PROFILE_COLLECTION_ASK_NAME_MESSAGE`
  定数(本節の質問文言をそのまま採用)を`LINKING_SUCCESS_MESSAGE`に連結した。既存テストは
  いずれも`LINKING_SUCCESS_MESSAGE`定数参照での比較だったため追加修正は不要だった。
  既存テスト全26ファイル・schema検証32件いずれもパス(回帰なし)。
- [フェーズ続き320で対応済み] 上記Webhook配線・文言修正を踏まえ、ステップ1(本設計に基づく
  収集フロー)・ステップ4(本番運用時のメモ送信)のモックスクリプト作成(onboarding-guide.md
  フェーズ続き314以来の次回候補(3))。`step1-2-linking-and-profile-collection-mock-script.md`・
  `step4-production-usage-mock-script.md`として新規作成した。
- 本設計決定をonboarding-guide.md 2節に反映(フェーズ続き316で実施済み)。
