# オーナー向け能動通知の工房識別子表示方式 設計(フェーズ177)

payment-suspension-owner-notification-design.md(フェーズ116)8節が「今後の課題」として
残していた「契約者識別子として`contractor_user_id`(LINEのuserId)をそのまま通知に載せる
案で暫定としたが、実運用では工房名等に変換した方がオーナーにとって分かりやすい可能性がある
(course-set-pasha版7節と同じ、次回以降の検討課題)」を検討する。aircon-pasha版が
business-name-owner-notification-display-design.md(フェーズ262・263)で同種の課題に
着手し「kura-pasha側の同種オーナー通知モジュールが同じ課題を抱えているかは未確認」を
次回候補としていたため、本フェーズで確認・対応した。

## 1. 前提条件の確認

course-set-pashaは「顧客管理シートとの突合が必要でventure範囲外」として見送り、
aircon-pashaは`UserProfile.business_name`が既に必須フィールドとして存在するため
採用した。本ventureはどちらに近いかを確認する。

onboarding-guide.md 2節(申込フォームでの連携コード入力・工房登録)によれば、申込フォームの
入力項目には「屋号(または工房名)」が既に含まれている。したがって本ventureはaircon-pasha
と同じく、外部の顧客管理手段との突合を要さず、申込時点で取得済みの値をそのまま使える状況に
ある。

一方、実装側(`usage_counter_workshop.WorkshopStoreProtocol`・`InMemoryWorkshopStore`)には
この屋号を保持するフィールドがまだ存在しなかった(申込フォームの項目定義止まりで、データ
モデルへの反映が漏れていたcross-document parityギャップ)。本フェーズでこれを追加した。

## 2. 対象範囲

オーナー向け能動通知のうち、契約者識別子として`contractor_user_id`のみを表示している
以下の2件が対象。

- `payment_suspension_owner_notification.py`(フェーズ116)
- `blocked_but_billing_owner_notification.py`(フェーズ81)

## 3. 表示形式

aircon-pasha版と同じ考え方で、「屋号: {workshop_name}(契約者ID: {contractor_user_id})」の
併記形式を採用する(workshop_nameのみへの差し替えはしない)。

- オーナーが一見して工房を識別できることを優先する(workshop_nameを主表示にする理由)。
- 個別フォロー(お支払い方法の案内等)の際、実際のシステム操作(問い合わせ対応・
  Firestoreでのレコード特定等)には`contractor_user_id`が引き続き必要になるため、
  併記して失わないようにする。

表示用語は、aircon-pasha版の「業者名」・course-set-pasha版横展開の「顧客名」とは異なり、
onboarding-guide.mdの入力項目名に合わせて「屋号」を採用した(職人向けの「屋号(または
工房名)」という表現のうち、より短く通知文に収まる語を選んだ)。

`workshop_name`が未設定(空文字列・None)の場合は、従来通り「契約者ID: {contractor_user_id}」
のみの表示にフォールバックする。

## 4. データモデルへの追加

`usage_counter_workshop.WorkshopStoreProtocol`に`get_workshop_name(workshop_id) ->
Optional[str]`・`set_workshop_name(workshop_id, workshop_name) -> None`を追加し、
`InMemoryWorkshopStore`にも同名メソッドを実装した(`_workshop_name_by_workshop`辞書、
`set_members()`とは独立したフィールドとして管理。申込フォーム入力〈屋号〉と工房作成
〈契約者・メンバー確定〉は別ステップのため、`set_members()`の引数には含めない)。

## 5. 実装

`payment_suspension_owner_notification.py`・`blocked_but_billing_owner_notification.py`
の両モジュールに、それぞれ独立した`_format_contractor_identifier_line(contractor_user_id,
workshop_name)`ヘルパーを追加した(両モジュールとも表示用語「屋号」は共通のため中身は
同一だが、aircon-pasha版が2モジュールを独立させたまま横展開した方針〈フェーズ263、
モジュール間で共有ヘルパーを新設しない〉を踏襲し、本ventureも複製する形とした)。

- `payment_suspension_owner_notification.py`: `PaymentSuspensionOwnerNotificationWorkshopStoreProtocol`
  に`get_workshop_name`を追加し、`build_payment_suspension_owner_notification_message()`
  に`workshop_name: Optional[str] = None`引数を追加。`send_payment_suspension_owner_
  notifications()`が`workshop_store.get_workshop_name(workshop_id)`を取得して渡すよう変更。
- `blocked_but_billing_owner_notification.py`: `BlockedButBillingContractorResolver`に
  `get_workshop_name`を追加し、`build_blocked_but_billing_owner_notification_message()`に
  `workshop_name: Optional[str] = None`引数を追加。`send_blocked_but_billing_owner_
  notifications()`が`contractor_resolver.get_workshop_name(workshop_id)`を取得して渡すよう
  変更。

いずれも既存呼び出し元(`_demo()`、テスト)は`workshop_name`省略時デフォルトの`None`で
従来通り動作するため後方互換を維持する。テストとして、workshop_name設定時に「屋号:
{workshop_name}(契約者ID: {contractor_user_id})」が含まれること、workshop_nameがNone・
空文字列いずれの場合も「契約者ID: {contractor_user_id}」のみで「屋号:」を含まないことを
検証する各3件、および実送信配線がstore/resolver経由でworkshop_nameを反映することを
確認する各1件、計8件を追加した(`test_payment_suspension_owner_notification.py`4件・
`test_blocked_but_billing_owner_notification.py`4件)。

## 6. 今後の課題

- 申込フォーム送信〜`WorkshopStoreProtocol.set_workshop_name()`呼び出しの実結線
  (Googleフォーム・GAS Webhook等)はまだ実装していない。実際のGoogleフォーム作成・
  Firestore接続自体がオーナー承認待ちの範囲であるため(course-set-pasha・aircon-pashaの
  同種案件と同じ位置づけ)。
- 複数職人プランで代表者以外の職人が参加する場合の`workshop_name`は工房単位(1件)で
  変わらない前提。個々の参加職人名(`get_member_display_name()`)とは別概念であり、
  混同しないよう本ドキュメントで明記しておく。

最終更新: 2026-09-25 10:00 UTC(フェーズ177: 新規作成。payment_suspension_owner_
notification.py・blocked_but_billing_owner_notification.pyの両方にworkshop_name併記表示を
実装。`WorkshopStoreProtocol`へ`get_workshop_name`/`set_workshop_name`追加。新規テスト8件、
venture全体165件(既存157件+新規8件、`python3 -m unittest discover -s prototype -p
"test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス)
