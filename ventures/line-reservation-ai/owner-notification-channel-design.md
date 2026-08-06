# オーナー通知の配信先・配信方法 設計

作成日: 2026-08-06

## 背景

これまでの設計・実装(escalation-notification-templates.md・EscalationConsolidator・
first-booking-self-check-notification-design.md等)は、いずれも「オーナーへ通知する」
という判断ロジック・文面までは詳細に詰めてきたが、その通知を**実際にどの宛先へ・
どの経路で届けるか**は一度も決めていなかった。

`prototype/cloud_function_process_event.py`を実際に読むと、`self._push.send_message()`
(LINE Push Message API送信)は`_send()`ヘルパー経由で常に顧客の`user_id`宛にしか
呼ばれておらず、`EscalationConsolidator.on_event()`はあくまで「いつ・何を送るべきか」を
返すだけで、それを実際にどこかへ送信するコードは存在しない。オーナー通知は概念上の
プレースホルダーのまま残っていた。

first-booking-self-check-notification-design.mdの残課題
「オーナー向け送信先(LINE以外の経路も含めて未確定)自体が...未着手」を解消するため、
本ドキュメントで配信先・配信方法を決定する。

## 検討した選択肢

1. **同一LINE公式アカウントのpush APIをオーナー宛にも使う(採用)**
   店舗の公式LINEアカウントから、顧客への送信と全く同じMessaging API・全く同じ
   `push_client`実装を使い、宛先の`userId`だけをオーナー自身のLINEアカウントの
   userIdに差し替えて送る。
   - 追加のアカウント作成・外部サービス契約が不要(オーナー承認待ちの新規発生なし)。
   - onboarding-guide.mdのステップ4(接続テスト)で「オーナー自身のLINEアカウントから
     店舗の公式LINEアカウントへテストメッセージを送る」手順が既にあり、この時点で
     店舗の公式LINEアカウントはオーナーのLINEアカウントを友だち(=push可能な相手)として
     既に認識している。このuserIdをそのまま`owner_user_id`として店舗設定に保存すれば、
     新たな連携手順を増やさずに済む。
   - 欠点: 顧客向けメッセージ通数と同じ課金枠(line-api-pricing.md)を消費する。
     ただしオーナー通知は件数として少数(エスカレーション・初回予約セルフチェック程度)と
     見込まれ、影響は軽微と判断。
2. **メール通知**
   非エンジニアオーナーには馴染みやすいが、メール送信用の別サービス(SendGrid等)の
   アカウント作成・APIキー取得が新たに必要になり、オーナー承認待ちの項目を増やすだけで
   MVPの前進にならない。将来の選択肢として保留。
3. **LINE Notify**
   2025年3月末でLINE社によるサービス終了が既に案内されており(新規発行・既存トークン
   ともに廃止)、新規採用先として選択できない。
4. **店舗専用の管理者向けLINEグループ(Messaging APIのグループ送信)**
   複数店舗スタッフへ同時通知できる利点はあるが、グループ作成手順が増え、
   オーナー1人の個人事業主が主要ターゲット(customer-interview-design.md想定顧客)である
   MVP規模には過剰。将来、スタッフ複数名体制の店舗に対応する際の拡張候補として保留。

## 採用方針

- 店舗設定(owner-settings-wireframe.mdの「営業情報設定」に相当)に`owner_user_id`
  (オーナー自身のLINE userId)を1件保持する。
- 取得方法は、onboarding-guide.mdステップ4「オーナー自身のLINEアカウントから店舗の
  公式LINEアカウントへテストメッセージを送る」を流用する。このテストメッセージの
  Webhookイベント(`event.source.userId`)を、通常の会話処理とは別に「オーナー登録用の
  特別な発言」として扱い、`owner_user_id`として保存する運用を想定する
  (具体的な判別方法(合言葉/専用QRコードのLINEログイン等)は実LINE API接続時の
  実装課題として残す。今回は「どの経路でuserIdを得るか」の方針決定まで)。
- `ConversationEventProcessor`に`owner_user_id: Optional[str] = None`を追加し、
  first-booking-self-check-notification-design.mdの`consume_first_booking_self_check()`が
  Trueを返した場合に限り、`_send()`(既存の即時1回リトライ+失敗時`line_push_failed`記録の
  仕組みをそのまま流用)で`owner_user_id`宛に送信する。`owner_user_id`が未設定
  (店舗がまだオーナー登録用テストメッセージを送っていない、またはMVP初期でオンボーディング未完了)
  の場合は何もしない(例外を出さず静かにスキップする、通知を諦めるだけで会話処理自体は
  失敗させない)。

## スコープ外(今回の残課題)

- `EscalationConsolidator.on_event()`/`flush_due_windows()`が返す「送るべき通知」を
  実際に`owner_user_id`へpushする配線(escalation-notification-templates.mdの各文面を
  組み立てて送る処理)は、対象イベント数・呼び出し元(Cloud Scheduler経由の
  `flush_due_windows()`呼び出し元がまだ未実装)が多く本ドキュメントの範囲を超えるため、
  次回以降の課題として残す。今回は範囲を先行して未着手だったfirst-booking-self-check
  (単発・呼び出し元が`_handle_details()`1箇所のみ)に絞って配線した。
- 合言葉/専用QRコード等、`owner_user_id`を安全に特定する具体的な実装方式の設計。
- 複数スタッフでの通知先グループ化(選択肢4)は将来課題。
