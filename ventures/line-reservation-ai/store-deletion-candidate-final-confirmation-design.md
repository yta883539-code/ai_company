# 店舗レコード削除候補の選定・最終確認送信設計

作成日: 2026-10-13(フェーズ続き317)

## 1. 背景・欠落の発見

data-retention-policy.md「店舗レコード(`stores/{storeId}`)の保存期間の考え方」節は、
休止モード4通目の再通知(dormant-mode-renotification-design.md、移行から90日後)から
さらに1年間オーナーの反応が一切ない場合に「削除候補として洗い出す」方針、および削除候補化後は
LINE push(主経路)・メール(代替経路、送信サービスのアカウント作成が必要でオーナー承認待ち)
による最終確認を試みる方針を、いずれも**方針として**定めている。

一方、course-set-pasha(フェーズ292、2026-10-12 18:00 UTC)はaircon-pashaの
`deletion_candidate_final_confirmation.py`・`cloud_function_send_deletion_candidate_
final_confirmations.py`パターンを自ventureの2store構成に適応させて実装済みであり、
同種の「削除候補の選定ロジック・最終確認送信配線」は4venture中3つ(aircon-pasha・
course-set-pasha・kura-pasha)で実装済みという横並びの状態にある。本ventureは
data-retention-policy.mdで方針のみ確定させた(2026-08-03作成)まま、`list_deletion_
candidates()`相当の選定ロジック・送信配線のコードがいずれも未着手であることを確認した
(`prototype/`配下を`deletion_candidate`で検索した結果、該当ファイルは存在しなかった)。
本フェーズはこの欠落を埋めるための設計を行う(コード実装は次フェーズ以降の次回候補とする)。

## 2. 本ventureのデータモデル上の位置づけ

course-set-pashaは削除候補状態(`deletion_candidate_at`等)と`is_following`を別々のstore
オブジェクトで扱う2store構成だが、本ventureは店舗情報を単一の`stores/{storeId}`ドキュメント
に集約する構成(firestore-data-model.md)であり、aircon-pashaの単一`UserProfile`統合構成に
近い。したがって選定・送信関数は単一のstore(`StoreProfileStoreProtocol`相当)のみを引数に
取れば足り、course-set-pashaのような2store適応は不要と判断する。

## 3. 新規フィールド(firestore-data-model.mdへの追加が必要)

現行の`stores/{storeId}`スキーマには`dormantRenotifyCount`(0〜3の整数、何通送信済みかの
カウンタ)はあるが、**3通目(final)を実際に送信した時刻**を保持するフィールドが無い。
data-retention-policy.mdの「90日後からさらに1年」を起点として測るには、カウンタだけでは
不十分なため、以下3フィールドの追加が必要と判断する(dormant_mode_scheduler.pyの改修を
伴うが、既存の`DormantScheduleState`・`select_due_dormant_events()`のシグネチャ変更は
本フェーズの設計対象外とし、次回候補とする)。

- `dormantFinalRenotifySentAt`: Timestamp | null。3通目(final、90日後)送信済み時刻。
  `dormantRenotifyCount`が3に達した送信と同一トランザクションで設定する。
- `storeDeletionConfirmationSentAt`: Timestamp | null。削除候補化後の最終確認(LINE push)
  送信済み時刻。再送を防ぐ冪等性フラグ(course-set-pasha/aircon-pashaの同名フィールドに
  相当)。
- `storeDeletionConfirmationUnreachableAt`: Timestamp | null。LINE push送信が失敗し、
  かつメール代替経路も利用不可(未接続、またはオンボーディング時の連絡先メール未収集)で
  連絡不能と判定された時刻。data-retention-policy.mdが定める「連絡不能フラグ」に対応する。

## 4. 選定ロジックの設計(`list_store_deletion_candidates()`、実装済み:
フェーズ続き318以降`prototype/store_deletion_candidate.py`)

対象: 以下をすべて満たす店舗。

1. `dormantRenotifyCount == 3`(4通目=最終再通知まで送信済み)。
2. `dormantFinalRenotifySentAt`が設定済みで、`now - dormantFinalRenotifySentAt >= 365日`。
3. `storeDeletionConfirmationSentAt`が未設定(最終確認を未送信、冪等性ガード)。
4. 最終再通知送信後に「反応」があったとみなせる状態になっていないこと。本ventureが
   機械的に判定できる反応の代理指標は、dormant_mode_scheduler.pyの既存ガード(2〜4通目を
   対象外とする条件)と同じく、(a)`stripeCustomerId`が設定された(決済完了によるプラン
   選択)、(b)`suspensionReason`が`null`に戻った(復旧、`cloud_function_subscription_
   activated_webhook.py`参照)のいずれか。

既知の限界として、data-retention-policy.mdが「反応」の例に挙げる「トークルームでの操作」
(予約確認・FAQ問い合わせ等、決済に至らない会話)は、本venture現行スキーマでは店舗単位の
最終操作時刻として永続化されていない(`ConversationFlowStateMachine`はセッション単位の
一時状態のみ保持し、`archivedAt`後は保存期間ポリシーに従って1年で削除される)ため、
機械的な「反応」判定からは対象外になる。これは既存のdormant再通知の送信要否判定
(`select_due_dormant_events()`)自体が抱える既存の限界と同一であり、本フェーズで新たに
生じたものではないが、削除候補への「洗い出し」が最終判断ではなく人間(オーナー自身の
運営者)による確認を経る設計(次節)である以上、実害は限定的と判断する。

## 5. 最終確認送信の設計(`send_store_deletion_confirmations()`、実装済み:
フェーズ続き318以降`prototype/cloud_function_send_store_deletion_confirmations.py`)

- 主経路: `owner-notification-channel-design.md`が定めるLINE公式アカウントからの
  `owner_user_id`宛push送信とする(data-retention-policy.md既定どおり)。
- 送信失敗時の代替経路判定: 直近4回の休止モード再通知ログ(dormant-mode-renotification-
  design.mdの送信試行)が継続して失敗していたかどうかを判定材料とする設計を
  data-retention-policy.mdは想定しているが、本venture現行実装は送信試行の成否を
  店舗ドキュメントに永続化していない(送信関数は呼び出し元に例外/戻り値を返すのみ)。
  本フェーズでは、送信失敗の都度`storeDeletionConfirmationUnreachableAt`を仮に設定し
  メール代替経路の接続判定(連絡先メールアドレスの有無、メール送信サービス接続有無)に
  進む設計とし、「直近4回の履歴を遡る」判定は行わない簡略化方針とする(過剰設計を避ける
  ため、1回の送信失敗で連絡不能とみなす簡略化は、削除候補という低頻度・低リスクの事象に
  対しては許容範囲と判断)。
- メール送信自体は送信用サービス(SendGrid等)のアカウント作成が必要でオーナー承認待ちの
  ため(data-retention-policy.md既定どおり)、本フェーズの設計・次回実装候補のコードでは
  メール送信を行う関数のシグネチャ・呼び出し箇所のみを用意し、実送信はモック
  (`InMemoryEmailClient`等)にとどめる。
- Cloud Functionsエントリポイントは、aircon-pasha/course-set-pashaと同じ「本体は依存注入で
  テスト可能、`main(request)`だけが実`functions_framework`リクエストオブジェクトを扱う
  薄い配線」構成を踏襲する(`cloud_function_send_store_deletion_confirmations.py`として
  新設する想定)。

## 6. 本フェーズのスコープ

本フェーズは設計文書化のみとし、コード変更は行わない(firestore-data-model.mdへの
新規3フィールド追加も次回候補とし、本文書内で先行して定義した)。コード変更が無いため
回帰テストの実行対象もない。承認が必要なアクション(支払い・アカウント作成・外部公開・
送信等)は本フェーズでは発生していないためpending-approval.mdへの追記なし(実LINE/
メール送信・実Firestore接続自体は既存の承認待ち事項の範囲内であり、新たな承認待ち事項
ではない)。

## 7. 次回候補

1. 承認待ち事項(顧客ヒアリングの実連絡・実Firestore/GCPプロジェクト等)がオーナーから
   承認された場合は本venture既存設計一式の実装着手を最優先。
2. 解消済み(フェーズ続き318・2026-10-15 23:00 UTC追記): 本文書3節のfirestore-data-
   model.mdへの新規フィールド追加(`dormantFinalRenotifySentAt`等)と、4節・5節のコード
   実装(`store_deletion_candidate.py`・`cloud_function_send_store_deletion_
   confirmations.py`・テスト追加)はいずれもフェーズ続き318で完了済みだったが、本文書の
   4節・5節見出し・本節がいずれも「次回実装候補」のまま更新されていなかった記載漏れを
   2026-10-15 23:00 UTC(定例更新)で発見し訂正した。
3. 他venture・アイデア領域の前進。
