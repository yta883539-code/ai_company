# 個人情報・記録の保存期間・削除方針

作成日: 2026-10-26 16:00 UTC(フェーズ60)

## 目的

他venture(aircon-pasha・course-set-pasha・kura-pasha・forklift-pasha・line-reservation-ai)
はいずれもdata-retention-policy.mdを切り出し済みだが、本venture(event-komiguai-pasha)には
同種の文書が未作成のまま残っていた(他venture側README.mdが繰り返し指摘していた「他venture側の
同種『未作成』記載の棚卸し」候補の一環として、本venture自身の未作成を解消する)。

本文書は個人情報保護法の一般的な考え方を踏まえた設計方針の整理であり、法的助言そのものでは
ない。最終的な妥当性の確認は引き続き法律専門家への確認が必要な事項として残す(他venture同様の
位置づけ)。

## 1. 他ventureとの前提の違い

他venture5件はいずれもLINE公式アカウントの`user_id`を主キーとする継続課金(サブスクリプション)
モデルだが、本ventureはpricing-plan.md(フェーズ4)・one-time-checkout-no-account-design.md
(フェーズ10)が確定したとおり、アカウント登録自体が存在しない単発決済(500円/回)モデルである。
したがって「契約関係が続く限り保有」という他venture共通の考え方がそのまま当てはまらず、
保存期間の起点は「決済・生成が完了した1回ごとの取引」単位となる。

## 2. 永続データの種類と保存期間方針

| コレクション | 用途 | 保存期間方針 |
|---|---|---|
| `one_time_draft/{draft_id}` | 入力内容・`customer_email`・生成結果への参照(ttl-expiry-result-delivery-refund-design.md フェーズ12) | **Firestore TTLポリシーにより作成から24時間後を目安に自動削除**(result-page-ttl-access-design.md フェーズ14で確定済み。結果ページの閲覧可否自体もこの削除に委ねる設計)。未決済のまま失効したレコードも同様に24時間で失効(one-time-checkout-no-account-design.md フェーズ10・2節)。 |
| `inquiry/{inquiry_id}` | 問い合わせフォーム(メール未着・返金希望等)の内容・`customer_email`・`draft_id`参照(inquiry-handling-design.md フェーズ15) | 下記3節で新規に方針を定める(本フェーズまで未検討だった箇所)。 |

## 3. `inquiry`コレクションの保存期間(本フェーズで新規決定)

`one_time_draft`と異なり、`inquiry`は問い合わせ対応(未着再送・返金判断)が完了した後も、
苦情・返金対応の経緯を一定期間追跡できる必要があるため、24時間TTLでの即時削除は採用しない。
他venture(aircon-pasha等)の解約後データと同じ考え方(「対応完了後も、再度の問い合わせ・
返金に関する異議申し立てに備える期間は保有する合理性がある」)を踏襲し、以下の方針とする。

| 状態 | 保存期間方針 |
|---|---|
| 対応中(`status`が`open`相当) | 保有継続(対応完了まで) |
| 対応完了(`status`が`resolved`相当、未着再送完了・返金処理完了等) | 対応完了日から**1年**保有した後、削除候補として洗い出す |

1年という値は、他venture(line-reservation-ai・course-set-pasha・aircon-pasha・kura-pasha・
forklift-pasha)のdata-retention-policy.mdが揃って採用した保存期間と揃えた暫定値であり、
実測データに基づくものではない。実運用開始後に見直す。

`one_time_draft`と異なり`inquiry`には継続課金のような「解約イベント」が存在しないため、
削除候補化の起点は`inquiry.resolvedAt`(対応完了日時、inquiry-handling-design.mdのフィールド
設計を前提とする暫定名称)とする。

## 4. 削除候補化後の最終確認・削除の実行方法(MVP)

- 他venture同様、実際の削除実行には送信用メールサービスのアカウント作成(オーナー承認待ち)
  および実Firestore接続が前提となるため、MVPでは専用の削除バッチジョブは実装せず、方針決定に
  とどめる。
- (フェーズ73追記)他venture(aircon-pasha・course-set-pasha・forklift-pasha)側から
  「月次・低頻度バッチのCloud Scheduler `retry_config`(1回の起動失敗時の再試行間隔)が
  削除猶予期間の実効性に影響しうる」という横断的な申し送りがあったため、本ventureについても
  確認した。本venture(event-komiguai-pasha)の削除候補化〜削除実行バッチは、上記のとおり
  MVP時点では専用バッチジョブ自体が未実装(方針決定のみ、実Cloud Scheduler化はオーナー承認後の
  結合実装フェーズに持ち越し)であるため、現時点で`retry_config`を設定する対象ジョブが存在
  しない。line-reservation-ai(フェーズ続き357)・kura-pasha(フェーズ270)が「低頻度バッチが
  無く対応不要」と結論付けたのと同様に、本ventureも「対応不要」と判断する。ただし本venture固有の
  留意点として、将来Cloud Scheduler化する際はaircon-pashaが確定した値
  (`retry_count: 5`、指数バックオフ`min_backoff_duration: 300s`〜`max_backoff_duration: 3600s`、
  `max_doublings: 3`)をそのまま採用する方針を本節にあらかじめ記録しておく(実装時に再検討の
  手間を省く目的、deletion-candidate-final-confirmation-scheduler-design.md 4節と同一値)。
- `customer_email`宛に削除予告を送る経路(他venture同様の「連絡不能なら削除保留」運用)は、
  本venture固有の二段階照合(draft-id-last4-collision-design.md)で使う`customer_email`
  正規化ロジック(customer-email-normalization-design.md フェーズ56)をそのまま再利用できる。
- 最終的な削除可否はオーナー(本リポジトリの運営者)が対話セッションで個別に判断する運用とする
  (本リポジトリ全体の「機械的な自動実行はしない」方針に合わせる、他venture共通)。

## 5. 顧客からの開示・削除依頼への対応(方針のみ)

- 本venture固有の論点として、`one_time_draft`はそもそも24時間で自動削除されるため、開示・
  削除請求の対象として実質的に残りうるのは`inquiry`コレクションのみとなる。
- `inquiry.draft_id`の末尾4文字(`draft_id_last4`)と`customer_email`の二段階照合(既存の
  オーナー向け検索手段、admin-search-ui-necessity-design.md フェーズ57)で該当レコードを
  特定・削除できれば足りる想定で、専用の自動化機能(セルフサービス削除画面等)はスコープ外と
  する(他venture同様)。

## 6. `idempotency_key_index`側ドキュメント削除の組み込みチェックリスト(フェーズ69新規)

idempotency-key-write-conflict-control-design.md(フェーズ67)・同5節(フェーズ68)で確定した
`idempotency_key_index`コレクションは、`inquiry`側のドキュメントには`expireAt`を設定しない
(TTLポリシーによる自動削除の対象外)方針としたため、`inquiry`本体が4節の削除候補化フローで
削除される際に、対応する`idempotency_key_index`側ドキュメントの削除が実装から漏れると、
参照先を失った索引ドキュメントがFirestore上に残り続ける("inquiry"自体は消えても索引だけが
永続する不整合)。`one_time_draft`側は`expireAt`をTTL対象に含めている(フェーズ68)ため本課題は
生じない。

将来、`inquiry`側削除候補化フローを実コード化する際は、以下を実装チェックリストとして必ず
確認する。

- [ ] 削除対象として洗い出した`inquiry/{inquiry_id}`を削除する処理と同一トランザクション
  (または同一バッチ)内で、`idempotency_key_index`から当該`inquiry_id`に対応するドキュメント
  (`idempotency_key`をドキュメントIDとして逆引きが必要、またはクエリで`inquiry_id`フィールド
  一致を検索)も削除する。
- [ ] 上記の逆引きに使うフィールド(`inquiry_id`等)がidempotency-key-write-conflict-control-
  design.mdの`idempotency_key_index`ドキュメント構造に実際に含まれているかを実装直前に再確認
  する(本チェックリスト作成時点では文書上のフィールド一覧の再照合までは行っていない)。
- [ ] 削除漏れがあった場合の検知手段(定期的な整合性チェックバッチ等)の要否は、実装時点の
  件数規模を見て判断する(本フェーズでは要否の結論までは出さない)。

## 今後の課題

- ~~inquiry-handling-design.mdのフィールド設計に、本文書が前提とした`resolvedAt`相当の
  フィールドが実際に含まれているかの照合~~ → フェーズ61で照合した結果、
  inquiry-handling-design.mdのフィールド一覧には`resolvedAt`が含まれていなかったため、
  同文書に`resolvedAt`(`status`が`resolved`に遷移した日時)を正式フィールドとして
  追記し、本文書3節が前提とする削除候補化の起点との整合を確保した(解消)。
- 削除候補の洗い出し・最終確認送信・連絡不能オーナーレビューの具体的ロジックは、他venture
  (aircon-pasha等)のdeletion-candidate-design.md相当の設計をそのまま横展開できるか次回
  検討する。
- 実Firestore接続・実メール送信サービス接続・削除実行バッチのCloud Scheduler化は、既存の
  承認待ち事項の範囲内として残る。
