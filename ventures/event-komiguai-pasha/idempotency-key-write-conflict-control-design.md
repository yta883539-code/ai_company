# `idempotency_key`書き込み時の競合制御方式の確定(フェーズ67)

idempotency-key-duplicate-detection-firestore-query-design.md(フェーズ66)5節・6節の
残課題「書き込み時の競合制御方式(決定的`draft_id`導出 vs. クエリ結果への依存)の確定」に
対応する。机上設計であり、実`google-cloud-firestore`導入・結合実装は実GCPプロジェクト
作成(オーナー承認待ち)後に行う。

## 1. 結論: 専用インデックスコレクションによる原子的衝突検知を採用する

`draft_id`自体を`idempotencyKey`から決定的に導出する案(フェーズ66 5節の前者案)は採用
しない。代わりに、`idempotencyKey`をドキュメントIDとする専用インデックスコレクション
`idempotency_key_index/{idempotencyKey}`を新設し、`draft_id`/`inquiry_id`はこれまでの
方針(draft-id-last4-collision-design.mdフェーズ53で確定したUUID4ランダム生成)を維持
したまま、インデックスドキュメントの作成をFirestoreの「存在しない場合のみ作成」操作
(`create()`相当、既存ドキュメントがあれば`ALREADY_EXISTS`で失敗する)に委ねることで
衝突を検知する。

## 2. 決定的`draft_id`導出案を採用しない理由

draft-id-last4-collision-design.md(フェーズ53 1節)は、`draft_id`の生成方式をUUID4に
確定した理由として「`draft_id`がTTL内の結果アクセスキーを兼ねる(result-page-ttl-
access-design.md、`/result/{draft_id}`として顧客に直接URLで渡される)ため、第三者が
推測できない値である必要がある」ことを明示している。`idempotencyKey`はクライアント
(ブラウザ側のWebフォーム)が生成する値であり、その生成方式・ランダム性の強度はサーバー側
で保証できない。`draft_id`を`idempotencyKey`から決定的に導出する(そのまま採用、または
ハッシュ化)と、`idempotencyKey`の生成が弱い実装(例: タイムスタンプ+連番等)だった場合に
`draft_id`の推測可能性がそれに引き下げられ、結果アクセスキーとしての安全性要件(フェーズ
53)を損なう。したがって決定的導出案は`one_time_draft`側には採用できないと判断する。
`inquiry_id`はURLとして顧客に渡されない(2節)ためこの制約を直接は受けないが、2種類の
コレクションで異なる衝突制御方式を採用すると実装・レビューの複雑性が増すため、両者に
同一の方式(3節)を適用する。

## 3. 採用方式の詳細

- 新設コレクション`idempotency_key_index`のドキュメントID = `idempotencyKey`そのもの。
  フィールドは`collection`(`"one_time_draft"`または`"inquiry"`)・`documentId`(実際に
  発行した`draft_id`/`inquiry_id`)・`createdAt`の3つのみ。
- 書き込みフロー(`submit_event_form`・`submit_inquiry`共通):
  1. `draft_id`/`inquiry_id`をUUID4で新規生成する(既存方針を維持)。
  2. Firestoreトランザクション内で、`idempotency_key_index/{idempotencyKey}`に対して
     「存在しなければ作成、存在すれば失敗」する原子的操作を試みる。
  3. 作成に成功した場合のみ、同一トランザクション内で`one_time_draft/{draft_id}`
     (または`inquiry/{inquiry_id}`)本体ドキュメントを作成する。
  4. 作成が`ALREADY_EXISTS`で失敗した場合は、既存のインデックスドキュメントから
     `documentId`を読み取り、新規作成をスキップして既存の`draft_id`/`inquiry_id`を
     呼び出し元に返す(フェーズ66時点の既存方針=クエリ結果への依存、と同じ返り値)。
- フェーズ66の「クエリ結果に依存する案」との違いは、読み取り(クエリ)と書き込み
  (ドキュメント作成)の間に時間差が生じる2ステップ処理ではなく、Firestoreの
  ドキュメントID一意性保証とトランザクションの原子性を利用する点のみであり、
  同時2リクエストが同一`idempotencyKey`で競合してもどちらか一方のみが本体ドキュメント
  作成に成功することを保証できる。フェーズ66で設計した読み取り専用クエリ
  (`WHERE idempotencyKey == X`)は、インデックスコレクション新設後は冗長になるため、
  今後の結合実装では`idempotency_key_index`へのドキュメントID指定取得(`get()`)に
  置き換える想定とする(クエリそのものを廃止するわけではなく、インデックスドキュメント
  へのポイントルックアップに変える)。

## 4. 複合インデックスへの影響: なし

`idempotency_key_index`はドキュメントIDによる等価参照(`get()`)のみで運用するため、
フェーズ66 2節の結論(複合インデックス不要)に変更はない。`firestore.indexes.json`への
追記は本フェーズでも不要と判断する。

## 5. 未検証・残課題

- `idempotency_key_index`ドキュメントのTTL方針は未確定。`one_time_draft`側は24時間TTL
  (フェーズ66 3節)に合わせてインデックス側も24時間TTLとするのが自然だが、`inquiry`側は
  永続保存(フェーズ66 4節)のため、1コレクションに2つの異なるTTL方針を共存させる設計
  (`collection`フィールドでTTLポリシーを分岐できるか)の確認が次回候補として残る。
- 実Firestore接続後、トランザクション内での「存在しない場合のみ作成」操作の実装方法
  (Python SDKでの具体的なAPI呼び出し)の確認は、他venture同様、GCPプロジェクト作成
  (オーナー承認待ち)後の検証課題として残る。

最終更新: 2026-10-27 01:00 UTC(フェーズ67: idempotency-key-duplicate-detection-
firestore-query-design.mdフェーズ66の残課題に対応し、`idempotency_key_index`専用
コレクションによる原子的衝突検知方式を確定。決定的`draft_id`導出案は結果アクセスキーの
安全性要件(フェーズ53)を損なうため不採用とした。コード変更なし、回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(50件、変更なし)・
`python3 schema/validate_test_cases.py`(22件、変更なし)を実行しいずれも変更なしで
パスすることを確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。)
