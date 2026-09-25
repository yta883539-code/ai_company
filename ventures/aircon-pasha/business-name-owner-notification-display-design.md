# オーナー向け能動通知の業者識別子表示方式 設計(フェーズ262)

payment-suspension-owner-notification-design.md(フェーズ255)8節が「今後の課題」として
残していた「業者識別子として`user_id`をそのまま通知に載せる案で暫定としたが、実運用では
`business_name`(UserProfile既存フィールド)を使った方がオーナーにとって分かりやすい
可能性がある(course-set-pasha版7節と同じ課題)」を検討する。フェーズ256〜261では毎回
「次回候補」に残しつつ他の作業を優先してきたが、本フェーズで着手する。

## 1. course-set-pasha版との違いの確認

course-set-pashaのpayment-suspension-owner-notification-design.md 7節は、同種の課題を
「本ventureの範囲外(オーナーが手元の顧客管理手段で行う想定)」として`user_id`表示までを
設計範囲とし、対応を見送った。これは、course-set-pashaの通知対象が個々の受講生(消費者)
であり、LINEのuserIdに対応する「店舗名」相当のフィールドをそもそもUserProfileが
持っていないためである。

一方、本ventureの通知対象は「業者」(エアコンクリーニング事業者)であり、
`user_id_linking.py`のUserProfileは`business_name: str`をオンボーディング完了時の
必須フィールドとして既に保持している(`link_user()`の必須引数、フェーズ初期から存在)。
したがって本ventureはcourse-set-pasha版とは前提が異なり、「顧客管理シートとの突合」を
要さずbusiness_nameを直接使える状況にあるため、`user_id`表示のみで見送るのではなく
実際に採用を検討する価値がある。

## 2. 対象範囲

`business_name`が既にUserProfileの必須フィールドとして存在するにもかかわらず、オーナー
向け能動通知のうちbusiness_nameを表示していないものは以下の2件。

- `payment_suspension_owner_notification.py`(フェーズ255、本フェーズで対応)
- `blocked_but_billing_owner_notification.py`(フェーズ174、「顧客ID: {user_id}」表示。
  本ドキュメントの設計範囲外とし、次回候補に残す。理由は3節)

## 3. 表示形式

以下の理由から、「業者名(ID: user_id)」の併記形式を採用する(business_nameのみに
差し替えるのではない)。

- オーナーが一見して業者を識別できることを優先する(business_nameを主表示にする理由)。
- 個別フォロー(お支払い方法の案内等)の際、実際のシステム操作(問い合わせ対応・
  Firestoreでのレコード特定等)にはuser_idが必要になる場面が残るため、user_idも併記して
  失わないようにする(business_nameのみにすると、オーナーがuser_idを別途調べ直す
  手間が生じる)。

`business_name`が未設定(空文字列・None)の場合は、従来通り「業者ID: {user_id}」のみの
表示にフォールバックする。UserProfile本体ではbusiness_nameは必須フィールドのため実運用で
空になることは想定していないが、本モジュールの`PaymentSuspensionOwnerNotificationUserState`
はテスト容易性のためUserProfileと独立した薄いdataclassであり、フィールドの取り違え等の
防御的措置として許容する。

## 4. 実装

`payment_suspension_owner_notification.py`の`PaymentSuspensionOwnerNotificationUserState`に
`business_name: Optional[str] = None`を追加し、新規`_format_business_identifier_line()`が
2節の表示形式を組み立てる。`build_payment_suspension_owner_notification_flex_message()`は
従来の`f"業者ID: {user.user_id}"`を`_format_business_identifier_line(user)`の呼び出しに
差し替えた。既存呼び出し元(`_demo()`、テスト)は`business_name`を省略した場合デフォルトの
`None`で従来通り動作するため、後方互換性は維持される。実際のCloud Function配線(Firestoreの
UserProfileから`PaymentSuspensionOwnerNotificationUserState`を組み立てる箇所)はまだ実装
されていない(design 5節の通りFirestore接続自体がオーナー承認待ちの範囲であるため)。実装時
には`UserProfile.business_name`をそのまま渡すのみで対応できる。

テストとして、business_name設定時に「業者名: {business_name}(ID: {user_id})」が含まれる
こと、business_nameがNone・空文字列いずれの場合も「業者ID: {user_id}」のみで「業者名:」を
含まないことを検証する3件を追加した(test_payment_suspension_owner_notification.py)。

## 5. 今後の課題

- `blocked_but_billing_owner_notification.py`(フェーズ174)への横展開はフェーズ263で
  対応済み(6節参照)。
- kura-pasha側の同種オーナー通知モジュールが同じ課題を抱えているかは、kura-pasha側
  フェーズ177(workshop-name-owner-notification-display-design.md)で確認・対応済み。
  同ventureは本ventureと同じく`business_name`相当の値(屋号・工房名)を申込フォームで
  取得済みだったため、`payment_suspension_owner_notification.py`・`blocked_but_billing_
  owner_notification.py`の両方に同種の併記表示(表示用語は「屋号」)を実装している。

## 6. blocked_but_billing_owner_notification.pyへの横展開(フェーズ263で実装済み)

5節が次回候補として残していた`blocked_but_billing_owner_notification.py`(フェーズ174)への
横展開に対応した。同モジュールの`build_blocked_but_billing_owner_notification_flex_message
(user_id: str)`は`user_id`単体を引数に取る形だったため、5節で予告した通り
`business_name: Optional[str] = None`引数を追加する形(dataclass化は行わない、最小限の
シグネチャ変更)で対応した。

- 表示形式は本モジュール既存の「顧客ID: {user_id}」という語(2節「業者名/業者ID」とは
  異なり「顧客」という語を使っている)を踏襲し、`_format_customer_identifier_line()`が
  business_name設定時「顧客名: {business_name}(ID: {user_id})」・未設定時は従来通り
  「顧客ID: {user_id}」のみを返す(表示形式の考え方自体は2節と同一)。
- `candidate_user_ids: Sequence[str]`(user_id単体のリスト)からbusiness_nameを引くため、
  新規Protocol`BlockedButBillingBusinessNameReader`(`get_business_name(user_id) ->
  Optional[str]`)を追加し、`send_blocked_but_billing_owner_notifications()`に省略可能引数
  `business_name_reader: Optional[BlockedButBillingBusinessNameReader] = None`として追加した
  (未指定時は全件`user_id`のみの表示となり後方互換を維持する)。
- テスト5件追加(`build_...`のbusiness_name設定時・None時・空文字列時の3件、
  `send_...`のbusiness_name_reader経由での反映確認・reader未指定時のフォールバック確認の
  2件)。
- payment_suspension版と同じく、`cloud_function_webhook.py`からの実結線はまだ実装して
  いない(Firestore接続自体がオーナー承認待ちの範囲であるため)。`UserProfileStoreProtocol`
  への`get_business_name`追加自体はフェーズ264で対応済み(7節参照)。

## 7. UserProfileStoreProtocolへのget_business_name追加(フェーズ264で実装済み)

6節が残していた配線ギャップ(`UserProfileStoreProtocol`に`get_business_name`が無く、
`InMemoryUserProfileStore`を`BlockedButBillingBusinessNameReader`としてそのまま渡せ
なかった)に対応した。`user_id_linking.py`の`UserProfileStoreProtocol`に
`get_business_name(self, user_id: str) -> Optional[str]`を追加し、
`InMemoryUserProfileStore`に`UserProfile.business_name`をそのまま返す実装(未知の
`user_id`には他のgetterと同じく`None`を返す安全側方針)を追加した。これにより
`send_blocked_but_billing_owner_notifications(..., business_name_reader=store)`のように
`InMemoryUserProfileStore`インスタンス自身を`business_name_reader`引数へそのまま渡せる
ことを構造的型付け(duck typing)で確認済み(テスト
`InMemoryUserProfileStoreBusinessNameReaderTest.
test_satisfies_blocked_but_billing_business_name_reader_protocol`)。

新規テスト3件追加(`get_business_name`が保存済みのbusiness_nameを返すこと・未知の
user_idにNoneを返すこと・`BlockedButBillingBusinessNameReader`Protocolを構造的に
満たすことの確認、`test_user_id_linking.py`)、venture全体576件(既存573件+新規3件)・
schema検証25件いずれもパス。

実際に`cloud_function_webhook.py`(または該当スケジューラのエントリポイント)から
`business_name_reader=store`を渡す配線自体は、当該スケジューラ関数の呼び出し口が
Firestore接続(オーナー承認待ちの範囲)を前提とするため、まだ行っていない。次回候補として
残す。
