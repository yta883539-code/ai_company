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

## 5. `idempotency_key_index`ドキュメントのTTL方針(フェーズ68で確定)

1節の残課題だった「`one_time_draft`側24時間TTL vs. `inquiry`側永続保存という2つの異なる
TTL方針を1コレクション(`idempotency_key_index`)内で共存させられるか」を確定する。

- Firestoreのドキュメント有効期限(TTL)ポリシーは、コレクション(またはコレクション
  グループ)に対して「どのフィールド名をTTL対象とするか」を1つ指定する仕組みであり、
  指定したフィールドにタイムスタンプ値が設定されているドキュメントのみが、その値を
  過ぎた時点で自動削除の対象になる。同じフィールド名であっても、そのフィールド自体が
  存在しない(未設定の)ドキュメントはTTL削除の対象にならない(result-page-ttl-access-
  design.mdフェーズ14が前提とする`one_time_draft`側のTTL運用と同じ仕組み)。
- この挙動を利用し、`idempotency_key_index`ドキュメントに`expireAt`(タイムスタンプ、
  任意フィールド)を追加する。
  - `collection == "one_time_draft"`のドキュメント: `expireAt`に`createdAt + 24時間`を
    設定する。`one_time_draft`本体ドキュメント自身の24時間TTL(result-page-ttl-access-
    design.mdフェーズ14)と同じ期限にすることで、本体が自動削除されるタイミングと
    インデックスドキュメントの自動削除タイミングを一致させ、本体が既に削除された後も
    インデックスだけが残存して「存在しないはずのキーが重複と誤検知される」状態を防ぐ。
  - `collection == "inquiry"`のドキュメント: `expireAt`を設定しない(フィールド自体を
    書き込まない)。`inquiry`本体はdata-retention-policy.md 3節により24時間TTLを採用
    せず、対応完了後1年保有してからオーナーが削除候補として個別に洗い出す運用(自動
    削除ではない)であるため、インデックス側も自動削除の対象外とし、本体ドキュメントの
    削除(オーナー承認後の個別対応)と同時に、同じトランザクション・バッチ処理で
    `idempotency_key_index`側の対応ドキュメントも削除する運用とする(新たな自動化
    機能は追加しない、data-retention-policy.md 4節の既存方針を踏襲)。
- Firestoreの単一TTLポリシー設定(`idempotency_key_index`コレクションに対して
  TTL対象フィールドを`expireAt`に指定する、の1回の設定のみ)で、`collection`フィールドの
  値ごとに異なる保存期間を共存させられるため、複数のTTLポリシーやコレクション分割は
  不要と判断する。

## 6. 未検証・残課題

- 実Firestore接続後、TTLポリシーの対象フィールドを`expireAt`に指定する設定作業
  (Google Cloud Console/`gcloud firestore fields ttls update`相当のコマンド)、
  および`expireAt`を持たないドキュメントがTTL削除の対象にならないことの実環境での
  確認は、他venture同様、GCPプロジェクト作成(オーナー承認待ち)後の検証課題として残る。
- `inquiry`本体ドキュメントの削除候補化フロー(data-retention-policy.md 4節、未実装)
  自体の実装時に、同一トランザクション・バッチで`idempotency_key_index`側ドキュメントも
  削除する処理を組み込み漏れしないよう、結合実装フェーズでのチェックリスト化が望ましい点を
  申し送る。
- 実Firestore接続後、トランザクション内での「存在しない場合のみ作成」操作の実装方法
  (Python SDKでの具体的なAPI呼び出し)の確認は、他venture同様、GCPプロジェクト作成
  (オーナー承認待ち)後の検証課題として残る。

最終更新: 2026-10-27 02:00 UTC(フェーズ68: 1節の残課題だった`idempotency_key_index`
ドキュメントのTTL方針を確定。`expireAt`(任意フィールド)を追加し、`one_time_draft`側は
本体と同じ24時間後の値を設定、`inquiry`側はフィールド自体を設定しないことで、Firestoreの
単一TTLポリシー設定のまま1コレクション内に2つの異なる保存期間方針を共存させられることを
整理した。コード変更なし、回帰確認として`python3 -m unittest discover -s prototype -p
"test_*.py"`(50件、変更なし)・`python3 schema/validate_test_cases.py`(22件、変更なし)
を実行しいずれも変更なしでパスすることを確認した(回帰なし)。承認が必要なアクション
(支払い・アカウント作成・外部公開・送信等)は今回発生していないためpending-approval.md
への追記なし。)
