# StoreNameProviderProtocol / RegionNameProviderProtocol の実Firestore接続アダプタ設計

## 1. 背景

`cloud_function_process_event.py`には`StoreNameProviderProtocol`
(`get_business_name(store_id)`)・`RegionNameProviderProtocol`
(`get_region_name(store_id)`)の2つのProtocolと、検証用の`InMemoryStoreNameProvider`・
`InMemoryRegionNameProvider`スタブのみが存在し、実際の`stores/{storeId}`ドキュメント
(firestore-data-model.md 1節)から`businessName`・`regionName`フィールドを取得する
具象実装はまだ存在しない(フェーズ続き296の次回候補)。

本ドキュメントは、実Firestoreプロジェクトへの接続(GCPアカウント・課金設定を伴う)が
承認されるまでの間に、接続先が決まった際すぐ実装に移れるよう具象クラスの設計を
先行して詰めておくもの。コード変更・外部アカウント作成のいずれも行わない。

## 2. 設計方針

両Protocolの契約(「未設定・取得失敗時は空文字列を返す安全側フォールバック」)が
対称であり、取得元ドキュメントも同一(`stores/{storeId}`)であるため、
Firestoreドキュメントを1回読むだけで両フィールドを返せるよう、
読み取りをキャッシュ共有する1つのアダプタクラス`FirestoreStoreDocumentProvider`で
両Protocolを実装する(2つの別クラスにして重複した`get()`呼び出しを行うことは避ける)。

```python
class FirestoreStoreDocumentProvider:
    """StoreNameProviderProtocol・RegionNameProviderProtocolの実Firestore接続実装。
    stores/{storeId}ドキュメントを読み、businessName・regionNameを取得する。
    両Protocolの契約(未設定・取得失敗時は空文字列)を維持する。
    """

    def __init__(self, firestore_client) -> None:
        self._client = firestore_client

    def _get_store_doc(self, store_id: str) -> dict:
        try:
            snapshot = self._client.collection("stores").document(store_id).get()
        except Exception:
            # ネットワークエラー・権限エラー等はProtocol契約通り空文字列側の
            # フォールバックに合流させる(呼び出し元に例外を伝播させない)。
            return {}
        if not snapshot.exists:
            return {}
        return snapshot.to_dict() or {}

    def get_business_name(self, store_id: str) -> str:
        return self._get_store_doc(store_id).get("businessName") or ""

    def get_region_name(self, store_id: str) -> str:
        return self._get_store_doc(store_id).get("regionName") or ""
```

## 3. 検討事項

- **キャッシュ化は見送り**: `get_business_name`・`get_region_name`を同一呼び出し内で
  両方使う箇所(フェーズ続き294のSNS告知文生成)では2回ドキュメント読み取りが発生するが、
  firestore-traffic-cost-estimate.mdの試算上は1イベント処理あたりの読み取り回数が
  小規模事業者の想定トラフィックでは無料枠に収まる前提のため、インスタンス単位の
  簡易キャッシュ等は現時点では過剰設計と判断し導入しない。将来、同一イベント処理内で
  3回以上読むケースが出た場合に再検討する。
- **例外方針**: Protocol契約が「取得失敗時は空文字列」であるため、Firestore
  クライアントの例外(権限エラー・タイムアウト等)は`InMemoryStoreNameProvider`と
  同じ安全側フォールバックに合流させ、呼び出し元(`process_follow_event()`・
  SNS告知文生成ロジック)の既存のNoneガード・空文字列フォールバック実装を
  変更せずに差し替えられるようにする。
- **依存ライブラリ**: `google-cloud-firestore`を想定(hosting-platform-selection.md
  のCloud Functions (Python) + Firestore選定と一致)。本設計は`firestore_client`を
  コンストラクタ注入する形とし、ライブラリの具体的なクライアント型には依存しない
  (テスト時は`InMemoryStoreNameProvider`/`InMemoryRegionNameProvider`を使い続け、
  本クラスは実クライアント接続後の結合テストでのみ使用する)。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はpending-approval.md
  (2026-08-28 17:00 UTC記載のCloud Scheduler/LINE公式アカウント開設の承認依頼と
  同種、外部サービス側のアカウント作成・課金設定を伴う)の承認待ちであり、
  本設計のコードは承認後の結合実装フェーズまでコミットしない。
- 承認後は、`cloud_function_process_event.py`の`store_name_provider`・
  `region_name_provider`注入箇所に本クラスのインスタンスを渡すだけで差し替えが
  完了する設計になっていることを、結合実装時に確認する。
