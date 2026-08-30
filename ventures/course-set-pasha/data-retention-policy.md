# 個人情報の保存期間・削除方針

作成日: 2026-08-21(フェーズ85)

## 目的

unfollow-event-handling-design.md(フェーズ84)の「今後の課題」で「`user_profile`・
`usage_counter`等の長期保存期間の上限は、line-reservation-aiのdata-retention-policy.mdに
相当する文書が本ventureにまだ無いため未整理」として残っていた点に対応する。
line-reservation-ai/data-retention-policy.mdの構成・考え方を踏襲しつつ、本ventureの
データ構造(会話状態を持たない単方向バッチ処理、tech-stack.md参照)に合わせて整理する。

本文書は個人情報保護法の一般的な考え方を踏まえた設計方針の整理であり、法的助言そのものでは
ない。最終的な妥当性の確認は引き続き法律専門家への確認が必要な事項として残す
(legal-notices-draft.mdと同様の位置づけ)。

## 前提の整理: 本ventureが持つ永続データは3種類のみ

tech-stack.md「想定コンポーネント」のとおり、本ventureはline-reservation-aiと異なり
会話状態・予約履歴・通知ログのような継続的に積み上がるコレクションを持たない
(履歴記録`history_rows`はLINE返信メッセージ本文としてその場で返すのみで、サーバー側には
永続化しない、tech-stack.md「5. 履歴記録の保存先」参照)。永続データストア(Firestore)に
存在するのは以下の3種類のみ。

| コレクション | 用途 | 既存の期限方針 |
|---|---|---|
| `pending_links/{code}` | 連携コード(申込フォーム提出までの一時トークン) | 発行から24時間で自然失効(line-user-id-linking-design.md)。unfollow時は即時削除(unfollow-event-handling-design.md、フェーズ84で決定済み) |
| `user_profile/{user_id}` | ジム名・地域名設定(`gym_area_pairs`) | 未整理(本文書で整理する) |
| `usage_counter/{user_id}` | 月間生成回数カウント(`month`・`count`・`first_generation_notice_sent`) | 未整理(本文書で整理する) |

`pending_links`は既に期限方針が確定済みのため、本文書が新たに整理するのは
`user_profile`・`usage_counter`の2コレクションのみとなる。

## `user_profile`・`usage_counter`の性質

- いずれも「サービス利用者(ジムオーナー・セッター本人)自身」に関する記録であり、
  line-reservation-aiの`stores/{storeId}`(店舗オーナー向け設定)と同じ位置づけ。
  顧客(第三者)の会話履歴・予約履歴のような、事業者が第三者について保有するデータとは
  性質が異なる。
- `usage_counter`はtech-stack.md「6. 月間生成回数カウントの保存先」のとおり
  「ユーザー1人=1ドキュメント、フィールドは`month`・`count`のみ」の最小構成であり、
  月をまたぐたびに上書きされる(line-reservation-aiのようなアーカイブ・履歴の蓄積構造では
  ない)。そのため「何年分溜まっているか」という蓄積量の観点での期限設定は不要で、
  「ドキュメント自体をいつ削除するか(=`user_profile`と運命を共にするか)」だけが論点になる。
- unfollow-event-handling-design.md(フェーズ84)は「unfollow(ブロック)時点では
  `user_profile`・`usage_counter`を一切削除・変更しない」と決定済み(再フォロー時に
  設定し直す手間を省くため)。本文書はこれを覆さず、「では無期限に保有し続けてよいのか」
  という一段上の論点を扱う。

## 保存期間ポリシー(案)

契約関係(Stripeサブスクリプションの状態)を基準に整理する。line-reservation-aiの
`stores/{storeId}`と同様、「契約関係が続く限りは利用目的の範囲内として保有し続けることに
合理性がある」という考え方を踏襲する。

| 状態 | `user_profile`・`usage_counter`の扱い |
|---|---|
| トライアル中・有料プラン中(Stripeサブスクリプションが active/trialing) | 保有継続(現行どおり、変更なし) |
| unfollow(LINEブロック)のみ、Stripe解約はしていない | 保有継続(フェーズ84の決定どおり、課金が続く限り利用目的内) |
| Stripeカスタマーポータルで解約済み(subscription-cancellation-flow-design.md起点) | 解約日から**1年**保有した後、削除候補として洗い出す |
| 解約済み、かつunfollowも発生している | 上記と同じ(解約日起点の1年。unfollowの有無で扱いを変えない) |

1年という値は、line-reservation-ai/data-retention-policy.mdが採用したアーカイブ済み会話履歴・
店舗レコードの保存期間(いずれも1年基準)と揃えた暫定値であり、実測データに基づくものでは
ない。「解約後の問い合わせ対応(再契約希望・過去の設定内容の確認等)に必要な期間」を目安と
した想定で、実運用開始後に見直す。

トライアル中・有料プラン中は削除対象にしない(利用目的の範囲内)ため、削除の起点は
常に「Stripe解約日」であり、unfollow単独では削除の起点にならない
(フェーズ84の決定どおり、ブロックと解約は別レイヤーの事象のため)。

## 削除候補化後の最終確認

line-reservation-ai/data-retention-policy.mdの「最終確認の連絡経路」と同じ考え方を採用する。
削除候補として洗い出した後も即座には削除せず、オーナー(ジム・セッター本人)へ最終確認を
試みることが望ましい。

- 主経路: LINE公式アカウントからのpush送信。ただしunfollow(ブロック)済みの場合は
  送達できない(unfollow-event-handling-design.md「決定のまとめ」表のとおり、ブロック中は
  LINEへの返信自体を行わない方針のため、この経路は使えない)。
- 代替経路: onboarding-guide.mdの申込フォーム提出時に収集した連絡先情報(メールアドレス等、
  実際の収集項目はapplication-form-submission-flow-design.md側の実装確定後に確認)を用いた
  最終確認。実際のメール送信には送信用サービスのアカウント作成が別途必要であり、これは
  「アカウント作成」に該当するためオーナー承認待ちの範囲として残る(現時点では「どの宛先を
  使うか」の方針決定にとどめる)。
- LINE・代替経路のいずれも通じない「連絡不能」ケースは自動削除には進まず、削除候補リストに
  「連絡不能」フラグを付けたまま保持し、オーナー(本リポジトリの運営者)が対話セッションで
  個別に削除可否を判断する運用とする(pending-approval.mdと同様、機械的な自動実行はしない
  という本リポジトリ全体の方針に合わせる)。

## 削除の実行方法(MVP)

- MVPでは専用の削除バッチジョブは実装せず、line-reservation-aiと同様、実際のFirestore接続・
  Stripe Webhook(解約イベント受信)確定後にCloud Schedulerによる低頻度バッチ(月次程度、
  対象件数が少ないため日次・週次ほどの頻度は不要と想定)として実装する方針とする
  (実装自体はオーナー承認待ちの範囲)。
- `user_profile/{user_id}`・`usage_counter/{user_id}`はいずれも同じ`user_id`をキーとする
  ため、削除時は2ドキュメントをまとめて対象にできる(line-reservation-aiの
  `stores/{storeId}`のような親子コレクション構造ではなく、いずれもトップレベルの単独
  ドキュメントのため削除順序の論点自体が生じない)。

## 顧客からの開示・削除依頼への対応(方針のみ)

- 個人情報保護法上、本人からの保有個人データの開示・利用停止等の請求に対応できる体制を
  整えておくことが望ましい。本ventureはLINEの`user_id`を手がかりにオーナー(本リポジトリの
  運営者)が該当レコード(`user_profile`・`usage_counter`・未使用`pending_links`)を検索・
  削除できれば足りる想定で、専用の自動化機能(セルフサービス削除画面等)はスコープ外とする。
- legal-notices-draft.mdのプライバシーポリシー草案に、本方針の要旨(保存期間の目安、
  開示・削除請求への対応窓口がオーナーであること)を反映することを今後の課題とする。

## 今後の課題

- (解消済み 2026-08-22 03:00 UTC: legal-notices-draft.mdの2.4節に本方針の要旨(保存期間の
  基準・削除候補化後の最終確認手順・開示削除請求への対応窓口)を反映した。詳細は
  legal-notices-draft.md 2.4節参照)
- (解消済み 2026-08-22 11:00 UTC: Stripe解約イベント(webhook)起点の削除候補洗い出し
  トリガー設計を stripe-cancellation-deletion-candidate-trigger-design.md(フェーズ91)で
  行った。`deletion_candidate_at`フィールドの設計・解約時のマーク付け/再契約時の取り消し/
  月次バッチ用の読み出し関数を整理済み。残るのは実Stripe Webhook受信エンドポイント自体の
  設計で、実Stripeアカウント接続後(オーナー承認待ち)の課題として残る)
- 削除候補化後の連絡先(代替経路)は、申込フォームの実際の収集項目が
  application-form-submission-flow-design.mdの実装確定時点でまだ「メールアドレス」と
  確定していないため、実装確定後に本文書の「代替経路」記述を見直す必要がある。
- (解消済み 2026-08-21 18:00 UTC・フェーズ86: unfollow-event-handling-design.mdが別途
  今後の課題として残した「ブロックしたのに課金だけ続く」状態へのオーナー向けFAQ・
  問い合わせ対応文言整備は、本文書のスコープ外(削除方針ではなく問い合わせ対応文言の課題)
  として一旦切り出したうえで、同日中の後続フェーズ86・unfollow-billing-faq.mdで対応済み
  だった。本節が「引き続き未着手」のまま更新されていなかった記載漏れであり、
  フェーズ133で解消した。残るのは同ドキュメント「今後の課題」に記載のとおり、
  プロアクティブな検知・通知バッチの要否判断(実LINE・実Stripe接続後)のみ。
