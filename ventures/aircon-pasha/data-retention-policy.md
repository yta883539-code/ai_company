# 個人情報の保存期間・削除方針

作成日: 2026-08-23(フェーズ108)

## 目的

legal-notices-draft.md 2.4節で「契約終了後の入力メモ・作業履歴記録の保存期間は未確定。
データ保存方式の確定と合わせて検討する必要がある」として保留していた課題、および
user-account-linking-design.md(フェーズ107)「未検証・残課題」で「`user_profile`新設に
伴い、data-retention-policy.md相当のドキュメントに着手できる前提が整った」としていた点に
対応する。course-set-pasha/data-retention-policy.mdの構成・考え方を踏襲しつつ、本venture
固有の前提(申込フォーム→LINE友だち追加という紐付けの向き、unfollow時の扱いが
未設計であること)に合わせて整理する。

本文書は個人情報保護法の一般的な考え方を踏まえた設計方針の整理であり、法的助言そのものでは
ない。最終的な妥当性の確認は引き続き法律専門家への確認が必要な事項として残す
(legal-notices-draft.mdと同様の位置づけ)。

## 前提の整理: 本ventureが持つ永続データは3種類

user-account-linking-design.md「5. `user_profile`コレクションの確定」で確定した3コレクション
のみが対象となる。course-set-pashaと同様、作業履歴記録(mvp-flow-draft.mdの出力(3))は
LINE返信メッセージ本文としてその場で返すのみでサーバー側には永続化しない前提のため、
legal-notices-draft.md 2.4節が懸念していた「入力メモ・作業履歴記録」自体の長期保存という
論点は生じない(そもそも保存していない)。

| コレクション | 用途 | 既存の期限方針 |
|---|---|---|
| `pending_links/{code}` | 連携コード(フォーム送信〜LINE連携完了までの一時トークン) | 発行から24時間で自然失効(user-account-linking-design.md 3節、course-set-pashaと同じ方針) |
| `user_profile/{user_id}` | 屋号・事業形態・メールアドレス・`stripe_customer_id`・`current_plan_id` | 未整理(本文書で整理する) |
| `usage_counter/{user_id}` | 月間生成回数カウント(`month`・`count`) | 未整理(本文書で整理する) |

`pending_links`は既に期限方針が確定済みのため、本文書が新たに整理するのは
`user_profile`・`usage_counter`の2コレクションのみとなる。

## `user_profile`・`usage_counter`の性質

- いずれも「サービス利用者(業者本人)自身」に関する記録であり、course-set-pashaの
  `user_profile`・`usage_counter`と同じ位置づけ(業者が依頼者について保有する完了報告・
  お手入れ案内の内容そのものは、上記のとおり永続化しない)。
- `usage_counter`は`month`・`count`のみの最小構成であり、月をまたぐたびに上書きされる
  (蓄積型のアーカイブ構造ではない)ため、「ドキュメント自体をいつ削除するか
  (`user_profile`と運命を共にするか)」だけが論点になる点もcourse-set-pashaと同じ。
- 本venture固有の相違点: course-set-pashaはunfollow-event-handling-design.mdで
  「unfollow時点では`user_profile`・`usage_counter`を一切削除・変更しない」と決定済みだが、
  本ventureはunfollowイベントの処理設計自体が未着手(該当ドキュメントなし)。本文書では
  unfollow時の扱いをいったん「未決定」と明示し、Stripe解約を起点とする保存期間ポリシーのみ
  先行して整理する(unfollow時の扱いはfollow/unfollowイベント処理設計時に別途検討する
  残課題として切り出す)。

## 保存期間ポリシー(案)

契約関係(Stripeサブスクリプションの状態)を基準に整理する。course-set-pasha/
data-retention-policy.mdと同じ考え方(「契約関係が続く限りは利用目的の範囲内として
保有し続けることに合理性がある」)を踏襲する。

| 状態 | `user_profile`・`usage_counter`の扱い |
|---|---|
| トライアル中・有料プラン中(Stripeサブスクリプションが active/trialing、`current_plan_id`が設定済み) | 保有継続(現行どおり、変更なし) |
| Stripeカスタマーポータルで解約済み(subscription-cancellation-flow-design.md「解約確定Webhook受信時」起点、`customer.subscription.deleted`受信) | 解約日から**1年**保有した後、削除候補として洗い出す |
| LINEをブロック(unfollow)したが、Stripe解約はしていない | 未決定(上記のとおりunfollowイベント処理自体が未設計のため、本文書では扱わない) |

1年という値は、line-reservation-ai・course-set-pashaのdata-retention-policy.mdが採用した
保存期間と揃えた暫定値であり、実測データに基づくものではない。「解約後の問い合わせ対応
(再契約希望・過去の設定内容の確認等)に必要な期間」を目安とした想定で、実運用開始後に
見直す。

トライアル中・有料プラン中は削除対象にしないため、削除の起点は常に「Stripe解約日」
(`customer.subscription.deleted`受信日)である。

## 削除候補化後の最終確認

line-reservation-ai・course-set-pashaの「最終確認の連絡経路」と同じ考え方を採用する。
削除候補として洗い出した後も即座には削除せず、業者へ最終確認を試みることが望ましい。

- 主経路: LINE公式アカウントからのpush送信。ただしブロック(unfollow)済みの場合は
  送達できない可能性があるが、前述のとおり本ventureはunfollow検知自体が未実装のため、
  現時点では「送達できたかどうかの判定」自体ができない(unfollow処理設計時にあわせて
  対応する残課題)。
- 代替経路: 申込フォーム(onboarding-guide.mdステップ1)で収集した`email`
  (`user_profile.email`、user-account-linking-design.md 5節で確定済みのフィールド)を
  用いた最終確認。実際のメール送信には送信用サービスのアカウント作成が別途必要であり、
  これは「アカウント作成」に該当するためオーナー承認待ちの範囲として残る(現時点では
  「どの宛先を使うか」の方針決定にとどめる)。
- LINE・代替経路のいずれも通じない「連絡不能」ケースは自動削除には進まず、削除候補リストに
  「連絡不能」フラグを付けたまま保持し、オーナー(本リポジトリの運営者)が対話セッションで
  個別に削除可否を判断する運用とする(course-set-pashaと同じ、本リポジトリ全体の
  「機械的な自動実行はしない」という方針に合わせる)。

## 削除の実行方法(MVP)

- MVPでは専用の削除バッチジョブは実装せず、実Firestore接続・Stripe Webhook(解約イベント
  受信)確定後にCloud Schedulerによる低頻度バッチ(月次程度)として実装する方針とする
  (実装自体はオーナー承認待ちの範囲)。
- `user_profile/{user_id}`・`usage_counter/{user_id}`はいずれも同じ`user_id`をキーとする
  ため、削除時は2ドキュメントをまとめて対象にできる(course-set-pashaと同じ、親子
  コレクション構造ではないため削除順序の論点自体が生じない)。

## 顧客からの開示・削除依頼への対応(方針のみ)

- 個人情報保護法上、本人からの保有個人データの開示・利用停止等の請求に対応できる体制を
  整えておくことが望ましい。本ventureはLINEの`user_id`を手がかりにオーナー(本リポジトリの
  運営者)が該当レコード(`user_profile`・`usage_counter`・未使用`pending_links`)を検索・
  削除できれば足りる想定で、専用の自動化機能(セルフサービス削除画面等)はスコープ外とする。
- legal-notices-draft.mdのプライバシーポリシー草案(2.4節)に、本方針の要旨(保存期間の
  目安、開示・削除請求への対応窓口がオーナーであること)を反映することを今後の課題とする。

## 今後の課題

- legal-notices-draft.md 2.4節への本方針の要旨反映(未着手、次回以降の候補)。
- unfollow(LINEブロック)時の`user_profile`・`usage_counter`の扱いは、本文書では
  「未決定」のまま残した。course-set-pashaのunfollow-event-handling-design.mdに相当する
  ドキュメントを本ventureでも新規作成し、その中で本文書の「LINEをブロックしたが、Stripe
  解約はしていない」行を確定させる必要がある。
- 削除候補化後の連絡先(代替経路)は`user_profile.email`を用いる想定としたが、実際の
  Googleフォーム作成(pending-approval.md記載事項、オーナー承認待ち)が完了するまでは
  `email`フィールドの実データ収集自体が発生しないため、フォーム作成後に本節の想定を
  再確認する必要がある。
- 削除候補化トリガー(Stripe解約Webhook受信時の`deletion_candidate_at`マーク付け等、
  course-set-pashaのstripe-cancellation-deletion-candidate-trigger-design.md相当の設計)は
  本ventureでは未着手。次回以降の候補とする。
