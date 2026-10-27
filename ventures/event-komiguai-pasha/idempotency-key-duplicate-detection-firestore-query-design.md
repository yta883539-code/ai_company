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

- ~~5節で挙げた書き込み時の競合制御方式(決定的`draft_id`導出 vs. クエリ結果への依存)の
  確定は次回候補とする。~~ → フェーズ70で「クエリ結果への依存(後発案)」を確定した。
  7節参照。
- 実Firestore接続後、単一フィールド等価条件クエリが想定通りデフォルトインデックスで
  処理されること(明示的な複合インデックス追加が実際に不要であること)の実環境での
  確認は、他venture同様、GCPプロジェクト作成(オーナー承認待ち)後の検証課題として残る。

## 7. 書き込み側の競合制御方式の確定(フェーズ70)

5節で保留していた「決定的`draft_id`導出」案と「クエリ結果への依存」案のうち、
**クエリ結果への依存(後者)を採用**し、決定的`draft_id`導出は不採用と確定する。

### 7.1. 決定的`draft_id`導出を不採用とする理由

- `idempotencyKey`はクライアント(ブラウザ)側で生成される値であり(web-form-ui-design.md
  3節「送信ボタン押下時にクライアント側で生成する」)、サーバーが信頼して生成する値ではない。
  送信元は任意の値を`idempotencyKey`として送信できる。
- `draft_id`は単なる内部キーではなく、result-page-ttl-access-design.md(フェーズ14)が
  定める`/result/{draft_id}`の結果ページへの実質的なアクセストークンを兼ねる(推測不能な
  ランダム値であることが前提、draft-id-last4-collision-design.md 1節で確認済み)。
- 仮に`draft_id`を`idempotencyKey`から決定的に導出する(例: そのまま採用する、またはハッシュ
  化する)と、`draft_id`の予測可能性がクライアントの入力に依存することになり、「推測不能な
  ランダムトークン」という前提そのものを弱める。クライアントが`idempotencyKey`を自由に選べる
  以上、攻撃者が特定の`idempotencyKey`→`draft_id`の対応を計算・列挙できてしまう余地を
  設計に持ち込むべきではないと判断する。
- したがって、`draft_id`は引き続きフェーズ53確定のとおりサーバー側で生成するUUID4に限定し、
  クライアント由来の値からの導出は行わない。

### 7.2. 採用する方式: クエリ結果への依存(ベストエフォート方式)

- `submit_event_form`/`submit_inquiry`受信時、まず1節のクエリで同一`idempotencyKey`を
  持つ既存ドキュメントの有無を確認し、存在すれば既存の`draft_id`/`inquiry_id`を返す
  (新規作成しない)。存在しなければ、サーバー側で新規UUID4の`draft_id`を発行し、
  `idempotencyKey`を含めて新規ドキュメントを作成する。
- クエリ実行とドキュメント作成の間はトランザクション等で保護しない(読み取り→書き込みの
  間に競合が生じ得る、ベストエフォートの重複排除とする)。
- この方式でも稀に重複ドキュメントが作成され得るが、実害は限定的と判断する。
  - 同一`idempotencyKey`での完全に同時(ミリ秒単位)の2リクエストが発生する確率自体が
    極めて低い(本venture想定規模は1日一桁〜十数件、draft-id-last4-collision-design.md
    3節参照)。
  - 重複が生じても、本venture1注文1決済(one-time-checkout-no-account-design.md)の構成上、
    Stripe Checkout Session自体はこの`idempotencyKey`に紐づいておらず(決済はCheckout
    Session単位で別途管理)、二重決済・二重請求にはつながらない。
  - `one_time_draft`側は重複しても各ドキュメントが独立に24時間TTLで自動削除され
    (3節参照)、永続的な汚染にはならない。`inquiry`側の重複は、オーナーが同一問い合わせの
    二重受信として目視で気づける範囲(低頻度運用)と判断する。
- 以上より、本venture規模ではトランザクション等による厳密な排他制御の追加実装は不要であり、
  「クエリ→存在しなければ作成」のシンプルな方式を採用することで5節の論点を解消する。
  実装自体は実`google-cloud-firestore`導入とセットの結合実装フェーズに持ち越す(1節冒頭の
  前提と同じ)。

最終更新: 2026-10-27 00:00 UTC(フェーズ66: web-form-ui-design.mdフェーズ65次回候補(1)に
対応し、`idempotency_key`重複検知の2クエリ(`one_time_draft`・`inquiry`)を設計。いずれも
単一フィールド等価条件のため複合インデックスは不要と判断し、`one_time_draft`側は既存のTTL
ポリシーが重複検知の有効期間を自然に境界付けることを確認、`inquiry`側は保存期間中恒久的な
重複検知となることを整理した。コード変更なし、回帰確認として`python3 -m unittest discover
-s prototype -p "test_*.py"`(50件、変更なし)・`python3 schema/validate_test_cases.py`
(22件、変更なし)を実行しいずれも変更なしでパスすることを確認した(回帰なし)。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。)

追記: 2026-10-27 13:00 UTC(フェーズ70: 5節で保留していた書き込み側競合制御方式を確定。
`draft_id`はresult-page-ttl-access-design.mdが前提とする「推測不能なランダムトークン」を
崩さないため決定的導出を不採用とし、「クエリ→存在しなければサーバー側でUUID4発行」という
ベストエフォート方式を採用、稀な重複の実害が限定的であることを7節として整理した。6節の
該当残課題を解消済みとして取消線化。コード変更なし、回帰確認として`python3 -m unittest
discover -s prototype -p "test_*.py"`(50件、変更なし)・`python3 schema/validate_test_cases.py`
(22件、変更なし)を実行しいずれも変更なしでパスすることを確認した(回帰なし)。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
pending-approval.mdへの追記なし。)
