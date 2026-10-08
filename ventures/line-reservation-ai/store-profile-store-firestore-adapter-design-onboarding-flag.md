# StoreProfileStoreProtocol の実Firestore接続アダプタ設計(オンボーディング完了メッセージ送信済みフラグ)

## 1. 背景・範囲

`store-profile-store-firestore-adapter-design.md`(フェーズ続き301)でStripeグループ
(3メソッド)の設計に着手した際、次回候補として「`is_onboarding_completion_message_sent`/
`mark_onboarding_completion_message_sent`(booleanフラグ1件のみで依存関係が薄い)」を
挙げていた。本フェーズはこのグループに着手する。

- **対象(2メソッド)**: `is_onboarding_completion_message_sent(user_id) -> bool`/
  `mark_onboarding_completion_message_sent(user_id) -> None`
  (`prototype/store_profile_store.py` 129-133行目、InMemory実装246-252行目)。
- `firestore-data-model.md`(1節、86-95行目)は、対応するFirestoreフィールド
  `onboardingCompletionMessageSentAt`(`stores/{storeId}`直下、Timestamp | null)を
  2026-08-30(フェーズ続き155)の時点で既に定義済みだが、実アダプタのコードは
  未設計だった。本フェーズでその設計を行う。

他のグループ(owner_user_id・owner_is_following・suspension_reason・owner_email・
blocked_but_billing_owner_notified_at・plan・checkout_session_completed_event_time・
menu_durations・store_faq_info・all_store_ids)は引き続き次回候補とする(4節)。

## 2. 設計

InMemory実装(246-252行目)は、送信済みかどうかをブール値相当の`set[str]`で保持する
だけで、送信時刻そのものは記録しない。一方`firestore-data-model.md`は実Firestore側の
フィールドをTimestamp型(`onboardingCompletionMessageSentAt`)として定義している。
これは、aircon-pasha(`set_trial_end_notified_at`等)・本venture自身の
`checkout_session_completed_event_time`と同じく「送信済みフラグを、送信時刻という
監査可能な情報を保持したまま冪等性チェックにも使う」設計方針を踏襲するためであり、
InMemory版が単純なset(真偽値のみ)にとどまっているのは、MVP段階では送信時刻までは
不要だったことによる簡略化と判断する(契約の食い違いではなく、実Firestore版の方が
情報量が多い正当な拡張)。

```python
class FirestoreStoreProfileStore:
    """(前節からの続き。本節はオンボーディング完了メッセージ送信済みフラグのみ追加)"""

    def is_onboarding_completion_message_sent(self, user_id: str) -> bool:
        try:
            snapshot = self._doc_ref(user_id).get()
        except Exception:
            # firestore-provider-adapter-design.md 3節と同じ安全側方針:
            # 接続エラーは「未送信」側に合流させる。これにより、接続エラー時に
            # evaluate_onboarding_completion_message_dispatch()(engine側)が
            # 「未送信」と誤判定し重複送信を試みる可能性はあるが、LINE
            # messaging_api.push_message()側の冪等性は別途保証されていないため、
            # 本メソッド単体では「取得できない時は送信済みとみなさない」という
            # 既存の安全側方針を優先する(courseset-pashaのstripe_webhook冪等性
            # チェックとは異なり、本フラグは「送信するorしない」の判定にのみ
            # 使われ、金銭処理の重複実行防止ではないため、安全側の基準は
            # 「取りこぼしなく機会を確保する」側を取る)。
            return False
        if not snapshot.exists:
            return False
        return (snapshot.to_dict() or {}).get("onboardingCompletionMessageSentAt") is not None

    def mark_onboarding_completion_message_sent(self, user_id: str) -> None:
        if not user_id:
            raise ValueError("user_id must be a non-empty string")
        self._doc_ref(user_id).set(
            {"onboardingCompletionMessageSentAt": firestore.SERVER_TIMESTAMP},
            merge=True,
        )
```

## 3. 検討事項

- **`firestore.SERVER_TIMESTAMP`の採用**: 本venture・他venture含め、本リポジトリで
  サーバー側タイムスタンプ(`google.cloud.firestore.SERVER_TIMESTAMP`)を使う設計は
  本フェーズが初出である。これまでの`set_trial_end_notified_at`等は呼び出し元から
  `datetime`を引数として受け取る方式だったが、`mark_onboarding_completion_message_sent`
  はProtocol契約上引数を取らない(129行目)ため、呼び出し元にタイムスタンプ生成の
  責務を持たせられない。クライアント側で`datetime.now(timezone.utc)`を生成して
  書き込む方式も代替案としてあり得るが、Cloud Functions実行環境のクロックずれや、
  リトライ時に複数回呼ばれた場合の時刻のずれを避けるため、Firestoreサーバー側の
  時刻を単一の信頼できる基準として採用する`SERVER_TIMESTAMP`を優先する。今後、
  他グループで同種の「引数なしmark系」メソッドをFirestore化する際はこの判断を
  参照する。
- **再実行(冪等性)**: `mark_onboarding_completion_message_sent`は`merge=True`の
  単純な上書きであり、複数回呼ばれても最後の呼び出し時刻に更新されるだけで
  エラーにはならない(InMemory版の`set.add()`と同じ「既に入っていても例外なし」
  という冪等性を保つ)。呼び出し元の`evaluate_onboarding_completion_message_dispatch()`
  (engine.py 542-581行目)は送信前に`is_onboarding_completion_message_sent()`を
  必ず確認する契約のため、通常経路での複数回書き込みは発生しない想定。
- **読み取り1回で判定可能**: Stripeグループの`set_stripe_customer_id`と異なり、
  本メソッド群は逆引きインデックスを持たないため、`is_...`は単純な1回の
  ドキュメント読み取りのみで済む(バッチ書き込み不要)。
- **例外方針**: `firestore-provider-adapter-design.md` 3節と同じ安全側フォールバックを
  踏襲するが、2節のコメントに記載した通り「安全側」の方向はフラグの性質によって
  逆転しうる(本フラグは「未送信」側を安全側とする)点を明記した。

## 4. 残課題・次回候補

- 実Firestoreプロジェクト・GCPアカウントの開設自体はオーナー承認待ち
  (pending-approval.md参照)のため、本設計のコードは承認後の結合実装フェーズまで
  コミットしない(前節と同じ方針)。
- 残りのグループ(owner_user_id・owner_is_following・suspension_reason・owner_email・
  blocked_but_billing_owner_notified_at・plan・checkout_session_completed_event_time・
  menu_durations・store_faq_info・all_store_ids)は引き続き次回候補。次に着手しやすいのは
  `owner_is_following`(boolean 1件、`get_owner_is_following`/`set_owner_is_following`)と
  判断する(suspension_reason・owner_emailはOptional[str]でNone許容のためnull消去の
  扱いを別途検討する必要があり、より単純なboolean 2件を先に片付ける)。
