# AccessTokenStoreProtocolの実Firestore接続アダプタ設計(フェーズ159)

runtime-dependency-switching-design.md(フェーズ158)「4. 未検証・残課題」に残っていた
「`access_token_store`(アクセストークン方式そのもの)のFirestore化は本フェーズでは
対象外としたため、別途検討が必要」に着手する。他venture(kura-pashaの
workshop-store-firestore-adapter-design.md等)が採用する「関連性の高い最小グループから
着手する」方針を踏襲するが、`AccessTokenStoreProtocol`自体が5メソッドと小規模なため、
本フェーズで全メソッドを一度に設計する。

`FleetOperatorStoreProtocol`(`trial_management.py`)自体の実Firestore接続アダプタは
本venture にまだ存在せず、別の次回候補として残る(4節)。本ドキュメントは
`AccessTokenStoreProtocol`(`prototype/access_token_store.py`)のみを対象とする。

## 1. 前提: 同一ドキュメントを2つのProtocolが分担する構造

firestore-data-model.md「1. `fleet_operator/{internal_id}`」が示すとおり、`accessToken`・
`lastAccessedAt`は`FleetOperatorStoreProtocol`が管理する`planId`・`stripeCustomerId`等と
同じ`fleet_operator/{internal_id}`ドキュメント内のフィールドである。InMemory実装では
`InMemoryAccessTokenStore`と`InMemoryFleetOperatorStore`が別々の辞書を持つ独立した
クラスだが、実Firestoreでは両方が同一ドキュメントへのget/updateを行うことになる。

本フェーズでは、この2クラスを統合して単一のFirestoreアダプタにする(ドキュメント取得を
1回にまとめて効率化する)案も検討したが、以下の理由により**2クラスを独立させたまま、
それぞれが個別にドキュメントのget/updateを行う**方針を採る(aircon-pasha・course-set-pasha
が`UserProfileStoreProtocol`1つに統合している構造とは異なり、本ventureは元々2つの
Protocolに分かれているため、Firestore化のタイミングで統合する必然性はない)。

- 統合すると`AccessTokenStoreProtocol`単体のテスト・差し替えができなくなり、
  `checkout_session.get_checkout_runtime_dependencies()`(`access_token_store`のみを
  必要とする)のような一部エントリポイントの依存注入がしづらくなる。
- 本venture のアクセスパターン(アクセスURL受信時・申込フォーム処理時のいずれも低頻度)
  では、ドキュメント読み取りが2回に分かれること自体のコスト増は無視できる水準であり、
  時期尚早な最適化(将来必要になった時点で統合を検討すれば足りる)と判断した。

## 2. 各メソッドの実装方針

### 2.1. `get_access_token` / `set_access_token`

`fleet_operator/{internal_id}`ドキュメントの`accessToken`フィールドへの単純な
get/update。`set_access_token`はInMemory版が持つ「旧トークンの逆引きインデックスを
あわせて削除する」処理(`_internal_id_by_access_token.pop(old, None)`)が不要になる
(2.3節参照、Firestoreでは逆引き専用のインデックス構造を自前で保持しないため)。

```python
doc_ref = self._client.collection("fleet_operator").document(internal_id)
doc_ref.update({"accessToken": value})
```

### 2.2. `get_last_accessed_at` / `set_last_accessed_at`

`lastAccessedAt`フィールド(Firestore Timestamp)への単純なget/update。
`access_token_store.record_access_and_get_previous()`が読み取り→書き込みの順序を
既に関数として固定しているため、本アダプタ自体に順序制御のロジックは持たせない
(呼び出し側の既存設計をそのまま活かす)。

### 2.3. `get_internal_id_by_access_token`(逆引き)

access-token-reissue-design.md「1. 前提の見直し」が既に言及している通り、
`accessToken`フィールドへの単一フィールドクエリで実現する。Firestoreは単一フィールドに
自動でインデックスを作成するため、追加の複合インデックス設定は不要
(firestore-composite-index-plan.mdへの追記も不要)。

```python
query = (
    self._client.collection("fleet_operator")
    .where("accessToken", "==", access_token)
    .limit(1)
)
docs = list(query.stream())
return docs[0].id if docs else None
```

InMemory版は`set_access_token`実行時に旧トークンの逆引きエントリを明示的に削除する
ことで「旧トークンでの照会は見つからない」(2節4.の自然な失効)を実現していたが、
Firestore版はライブクエリのため、`accessToken`フィールドが新トークンで上書きされた
瞬間に旧トークンでの照会は自動的に0件になる。逆引き専用のインデックス構造を自前で
保持・清掃する処理が不要になる分、InMemory版より実装が単純になる。

## 3. 未検証・残課題

- 同時再発行(同一`internal_id`に対し`reissue_access_token`が極短時間内に2回呼ばれる
  競合)はFirestoreの単純な`update()`では後勝ちになるだけで、InMemory版と同じく
  明示的な排他制御は設けない(他venture共通の「必要になった時点で検討する」方針を踏襲)。
- `FleetOperatorStoreProtocol`自体の実Firestore接続アダプタはまだ存在しない
  (`fleet_operator`コレクションの`planId`・`stripeCustomerId`等の残りのフィールド群)。
  次回候補として残す。
- 実`google-cloud-firestore`ライブラリの導入・`FORKLIFT_PASHA_FIRESTORE_ENABLED`
  フラグによる実コード化(runtime-dependency-switching-design.md 2節)は、承認後の
  結合実装フェーズに持ち越す(本フェーズはコード変更を行わない机上設計のみ)。

最終更新: 2026-10-16 15:00 UTC(フェーズ159)
