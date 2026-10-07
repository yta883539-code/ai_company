# 個人情報・記録の保存期間・削除方針

作成日: 2026-10-07 05:00 UTC(フェーズ100)

## 目的

legal-notices-draft.md 2.4節(旧)で初期メモに留めていた保存期間・削除方針を、他venture
(aircon-pasha・course-set-pasha・kura-pasha・line-reservation-ai)と同様に本ファイルへ
切り出す(legal-notices-draft.md次回候補(2))。あわせて、同節が未検討のまま残していた
「annual区分(特定自主検査)の点検記録に関する法定保存義務との整合」(次回候補(1))も
本フェーズで整理する。

本文書は個人情報保護法・労働安全衛生法令の一般的な考え方を踏まえた設計方針の整理であり、
法的助言そのものではない。最終的な妥当性の確認は引き続き法律専門家への確認が必要な事項
として残す(legal-notices-draft.mdと同様の位置づけ)。

## 1. annual区分(特定自主検査)の法定保存義務との整合

labor safety (安衛則)上、フォークリフトの特定自主検査を実施した場合、検査年月日・検査方法・
検査箇所・検査の結果・検査を実施した者の氏名・補修等の措置内容を記録し、**3年間保存**しなければ
ならない(労働安全衛生規則第151条の23・第169条等。WebSearchでmhlw.go.jp等の情報源により確認)。

本サービス(forklift-pasha)はfirestore-data-model.md(フェーズ11)の設計方針どおり、入力された
点検メモ・LLMが生成した整形済みテキストのいずれもサーバー側に永続化せず、点検担当者への返却
(整形済みテキストの返却)のみを行う。したがって:

- **3年間の法定保存義務は、本サービス運営者ではなく利用事業者(fleet_operator)自身が負う。**
  本サービスはannual区分の検査記録を法令が求める期間保管する「記録保管システム」としては
  機能しない(そもそも記録原本を保存しないため)。
- この前提を利用者が誤解しないよう、annual区分の出力画面・利用規約の双方に「返却された
  整形済みテキストは利用者自身が画面のコピー・ダウンロード等により保存する必要がある」旨を
  明記する(legal-notices-draft.md 2.5節、実際の画面文言確定はweb-form-ui-design.mdの
  次回課題)。
- 「記録原本を保存しない」設計自体を変更する必要はない(他venture同様、法定保存義務は
  サービス提供者側に転嫁されるものではなく、サービスが記録を代理保管すると誤認させる
  表示をしないことで足りると判断した)。daily/monthly区分には同種の法令上の保存義務の
  明記はないため、本注意事項はannual区分に限定する。

## 2. 永続データ3種類の保存期間

firestore-data-model.md(フェーズ11、フェーズ95〜99で`internal_id`/`accessToken`分離等を
反映)が定義する3コレクションが対象となる。点検記録本文自体は上記1節のとおりそもそも
永続化しないため、本節の論点にはならない。

| コレクション | 用途 | 保存期間方針 |
|---|---|---|
| `fleet_operator/{internal_id}` | 事業者単位の契約・課金情報(`accessToken`・`email`・`planId`・`stripeCustomerId`・`subscriptionStatus`等) | 下記「3. 保存期間ポリシー」参照 |
| `vehicle/{vehicle_id}` | 車両マスタ(`operatorInternalId`参照・`vehicleLabel`のみの最小構成) | `fleet_operator`と運命を共にする(親ドキュメント削除時に合わせて削除) |
| `usage_counter/{internal_id}` | 月間生成回数カウント(`month`・`count`) | `fleet_operator`と運命を共にする(aircon-pasha等の既存方針と同じ) |

## 3. 保存期間ポリシー(案)

他venture(aircon-pasha・course-set-pasha・kura-pasha)と同じ考え方(「契約関係が続く限りは
利用目的の範囲内として保有し続けることに合理性がある」)を踏襲する。本ventureはLINE友だち
関係を持たないため、他venture特有の「ブロック(unfollow)」という事象自体が存在しない点が
相違点であり、削除の起点はStripe解約のみとなる(より単純)。

| 状態 | `fleet_operator`・`vehicle`・`usage_counter`の扱い |
|---|---|
| トライアル中・有料プラン中(`subscriptionStatus`が`trialing`/`active`/`past_due`) | 保有継続(現行どおり、変更なし) |
| Stripeで解約済み(`subscriptionStatus`が`canceled`、`customer.subscription.deleted`受信) | 解約日から**1年**保有した後、削除候補として洗い出す |

1年という値は、line-reservation-ai・course-set-pasha・aircon-pashaのdata-retention-policy.md
が採用した保存期間と揃えた暫定値であり、実測データに基づくものではない。「解約後の問い合わせ
対応(再契約希望・過去のプラン設定内容の確認等)に必要な期間」を目安とした想定で、実運用開始後
に見直す。

## 4. 削除候補化後の最終確認

本ventureは、他venture(LINE公式アカウント経由のpush送信を主経路とする)と異なり、そもそも
LINEを前提としない(汎用Webフォーム、payment-identity-verification-design.md)。したがって
主経路は`fleet_operator.email`宛のメール送信となる。

- 実際のメール送信には送信用サービスのアカウント作成が別途必要であり、これは「アカウント
  作成」に該当するためオーナー承認待ちの範囲として残る(現時点では「どの宛先を使うか」の
  方針決定にとどめる。他venture同様の扱い)。
- メールが不達(バウンス等)の場合、他venture同様に「連絡不能」フラグを付けたまま削除候補
  リストに保持し、自動削除には進まない。最終的な削除可否はオーナー(本リポジトリの運営者)が
  対話セッションで個別に判断する運用とする(本リポジトリ全体の「機械的な自動実行はしない」
  方針に合わせる)。
- 本ventureはLINEのブロック相当の概念を持たないため、他venture(aircon-pasha等)が設計した
  「フォロー中/ブロック中での経路分岐」自体は不要であり、メール送達可否の二択のみで足りる
  (本venture固有の簡略化点)。

## 5. 削除の実行方法(MVP)

- MVPでは専用の削除バッチジョブは実装せず、実Firestore接続・Stripe Webhook(解約イベント
  受信)確定後にCloud Schedulerによる低頻度バッチ(月次程度)として実装する方針とする
  (実装自体はオーナー承認待ちの範囲、2026-10-06 22:00 UTC記載のStripeアカウント開設と
  同じ承認待ち事項に含まれる)。
- `fleet_operator/{internal_id}`・`vehicle/{vehicle_id}`(`operatorInternalId`参照)・
  `usage_counter/{internal_id}`はいずれも`internal_id`を手がかりに特定できるため、削除時は
  3ドキュメント(`vehicle`は該当事業者の台数分)をまとめて対象にできる。

## 6. 顧客からの開示・削除依頼への対応(方針のみ)

- 個人情報保護法上、本人からの保有個人データの開示・利用停止等の請求に対応できる体制を
  整えておくことが望ましい。本ventureは`accessToken`を手がかりにオーナー(本リポジトリの
  運営者)が該当レコード(`fleet_operator`・`vehicle`・`usage_counter`)を検索・削除できれば
  足りる想定で、専用の自動化機能(セルフサービス削除画面等)はスコープ外とする。
- legal-notices-draft.mdのプライバシーポリシー草案(2.4節)には、本方針の要旨(annual区分の
  法定保存義務が利用者自身にあること・保存期間の目安・開示・削除請求への対応窓口がオーナー
  であること)を反映済み(本フェーズで対応)。

## 今後の課題

- annual区分の出力画面・利用規約への具体的な注意文言の反映(web-form-ui-design.mdの次回課題、
  legal-notices-draft.md 2.5節参照)。
- メール送信経路の実装自体は、送信用サービスのアカウント作成(オーナー承認待ち)完了後の
  着手事項として残る。
- 削除候補化トリガー・削除実行バッチの実装は、実Firestore接続・Stripe Webhook確定後の
  着手事項として残る(他venture〈aircon-pasha等〉が先行実装した`deletion_candidate.py`等の
  設計を参考にできる見込み)。
