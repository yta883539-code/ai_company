# `idempotency_key`重複検知のFirestoreクエリ設計(フェーズ66)

web-form-ui-design.md(フェーズ65)4節「次回候補」(1)「`idempotency_key`の重複検知
ロジックのFirestoreクエリ設計(複合インデックスの要否含む)」に対応する。机上設計であり、
実`google-cloud-firestore`導入・結合実装は実GCPプロジェクト作成(オーナー承認待ち)後に
行う。

## 1. 対象の2クエリ

web-form-ui-design.md 4節の方針(新規作成前に同一`idempotency_key`を持つ既存ドキュメントを
検索し、存在すれば既存の`draft_id`/`inquiry_id`を返す)を実現するためのクエリは次の2つ。

| # | コレクション | クエリ | 用途 |
|---|---|---|---|
| 1 | `one_time_draft`(ルートコレクション) | `WHERE idempotencyKey == X` | `submit_event_form`の再送時、同一キーの既存ドラフトを検索 |
| 2 | `inquiry`(ルートコレクション) | `WHERE idempotencyKey == X` | `submit_inquiry`の再送時、同一キーの既存問い合わせを検索 |

いずれも単一フィールドの等価条件のみで、2フィールド以上を組み合わせたクエリではない。

## 2. 複合インデックスの要否: 不要

Firestoreは単一フィールドに対する等価条件クエリについて、デフォルトの単一フィールド
インデックスを自動的に作成する(明示的な複合インデックス定義は不要)。本venture内の既出
複合インデックス事例(forklift-pasha/firestore-composite-index-plan.md等、他venture)は
いずれも「2フィールド以上の組み合わせ条件」または「不等号条件を含む複数フィールドの
範囲指定」を扱うものだが、上記1・2はどちらも単一フィールドの等価条件のみであるため、
`firestore.indexes.json`への追記は不要と判断する。

## 3. `one_time_draft`側: TTL(24時間)が重複検知の有効期間を自然に境界付ける

web-form-ui-design.md 5節で残課題として挙げられていた「`idempotency_key`の有効期間を
`one_time_draft`のTTL(24時間、result-page-ttl-access-design.md フェーズ14)と揃えるか」
について、本フェーズで次のように結論する。

- `one_time_draft/{draft_id}`はFirestore TTLポリシーにより作成から24時間後を目安に
  自動削除される(result-page-ttl-access-design.md 2節)。
- したがって`idempotencyKey`の重複検知クエリは、ドキュメントが存在する限りヒットし、
  TTL失効により当該ドキュメントが削除された後は自動的にヒットしなくなる。別途
  `idempotencyKey`専用の有効期限フィールドやバッチ処理を追加する必要はなく、既存の
  TTLポリシーがそのまま重複検知の有効期間を境界付ける。
- 結論: 「`idempotency_key`の有効期間をTTLと揃える」という5節の課題は、追加実装なしに
  TTLポリシーへの委譲によって解消される(data-retention-policy.mdが確定した削除方針を
  そのまま再利用するのみで、本文書独自の期限管理は持たない)。

## 4. `inquiry`側: 永続的な重複検知(TTLに委ねられない)

`inquiry`コレクションはdata-retention-policy.md 3節により24時間TTLを採用せず、
`resolvedAt`起点でより長い保存期間方針が別途定められている(苦情・返金対応の経緯追跡の
ため)。したがって`one_time_draft`側のような「TTL削除が重複検知の有効期間を自然に境界付ける」
前提は`inquiry`には適用できず、`idempotencyKey`での重複検知は保存期間中、恒久的に有効と
なる。これは望ましい挙動である(問い合わせの二重送信防止に有効期限を設ける理由がなく、
data-retention-policy.mdの削除候補化フローに従って`inquiry`ドキュメント自体が削除された
後に同じキーが再送されても、新規ドキュメントとして扱われるのみで実害はない)。

## 5. 書き込み側の整合(参考、実装は結合実装フェーズに持ち越し)

- クエリ実行とドキュメント作成の間に競合(同一`idempotency_key`での同時2リクエスト)が
  生じた場合の扱いは、`draft_id`/`inquiry_id`をサーバー側で`idempotencyKey`から導出した
  決定的な値にする(例: `idempotencyKey`をそのまま`draft_id`として採用する、または
  ハッシュ化して使う)ことで、Firestoreのドキュメント作成操作自体の一意性保証に委ねる案と、
  クエリ結果を信頼して後発リクエストをスキップする案の2つが考えられる。前者は`draft_id`の
  命名規則(既出のdraft-id-last4-collision-design.md フェーズ?との整合確認が必要)に影響する
  ため、本フェーズでは結論を出さず次回候補とする。
- 本フェーズはクエリ設計(読み取り側)のみを対象とし、書き込み側の実装・競合制御の確定は
  実`google-cloud-firestore`導入とセットの結合実装フェーズに持ち越す(web-form-ui-design.md
  4節と同じ方針)。

## 6. 未検証・残課題

- 5節で挙げた書き込み時の競合制御方式(決定的`draft_id`導出 vs. クエリ結果への依存)の
  確定は次回候補とする。
- 実Firestore接続後、単一フィールド等価条件クエリが想定通りデフォルトインデックスで
  処理されること(明示的な複合インデックス追加が実際に不要であること)の実環境での
  確認は、他venture同様、GCPプロジェクト作成(オーナー承認待ち)後の検証課題として残る。

最終更新: 2026-10-27 00:00 UTC(フェーズ66: web-form-ui-design.mdフェーズ65次回候補(1)に
対応し、`idempotency_key`重複検知の2クエリ(`one_time_draft`・`inquiry`)を設計。いずれも
単一フィールド等価条件のため複合インデックスは不要と判断し、`one_time_draft`側は既存のTTL
ポリシーが重複検知の有効期間を自然に境界付けることを確認、`inquiry`側は保存期間中恒久的な
重複検知となることを整理した。コード変更なし、回帰確認として`python3 -m unittest discover
-s prototype -p "test_*.py"`(50件、変更なし)・`python3 schema/validate_test_cases.py`
(22件、変更なし)を実行しいずれも変更なしでパスすることを確認した(回帰なし)。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。)
