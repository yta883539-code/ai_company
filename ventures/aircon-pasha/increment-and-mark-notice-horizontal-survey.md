# course-set-pashaフェーズ313の横展開可否調査(フェーズ327)

## 目的

フェーズ325・326の次回候補(2)として持ち越していた「他venture(kura-pasha・
course-set-pasha・line-reservation-ai)分の『完了宣言後の追加フィールド反映漏れ』棚卸し」
を実施する。直接の発端は、course-set-pashaフェーズ313(2026-10-18 21:00 UTC)で
`FirestoreUsageCounter.increment_and_mark_notice()`(count・first_generation_notice_sent・
trial_start_atの3フィールドを単一トランザクションで更新)が実コード化されたことであり、
他venture側で同種の実装が既に「完了宣言」されているにもかかわらず、この3フィールド
結合パターンが反映されていない箇所(反映漏れ)がないかを確認する。

## 調査結果

### kura-pasha: 反映漏れではない(データモデルが異なるため対象外)

kura-pashaの`UsageCounterStoreProtocol`(prototype/usage_counter_workshop.py)は
`get`/`set`/`increment_or_reset`の3メソッドのみを持ち、`count`フィールドの読み書きに
特化している。`first_generation_notice_sent`・`trial_start_at`は同じ
`UsageCounterStoreProtocol`ではなく別の`WorkshopStoreProtocol`側のフィールドとして
定義されている(get/set_first_generation_notice_sent、get/set_trial_start_at)。

course-set-pashaが3フィールドを単一トランザクションに結合する必要があったのは、
3フィールドが同一ドキュメント(usage_counter側)に存在し、並行書き込みでの取り落としを
防ぐためだった(firestore-provider-adapter-design.md 20節)。kura-pashaでは
count(usage_counter側)とfirst_generation_notice_sent・trial_start_at(workshop側)が
そもそも別ドキュメントに分かれているため、同一トランザクションへの結合という論点が
発生しない(ドキュメントを跨ぐ結合は別の設計判断であり、今回course-set-pashaが
解消した「同一ドキュメント内の複数フィールド」問題とは異なる)。したがって本件は
反映漏れではなく、データモデル上の構造差異により最初から対象外であることを確認した。

### forklift-pasha: 反映漏れではない(実Firestore接続アダプタ自体が未着手)

forklift-pashaの`UsageCounterStoreProtocol`(prototype/overage_notifications.py)は
Protocol定義とInMemory実装のみが存在し、「実際のFirestore接続は未実装で、本venture内
ではInMemoryUsageCounterStoreのみを実装として用意する」とコード内コメントに明記
されている。実Firestore接続アダプタ自体がまだ存在しないため、3フィールド結合の
反映漏れという論点は時期尚早であり、対象外であることを確認した。

### aircon-pasha(自ventureの再確認): 反映漏れではない(意図的に別方式を採用)

firestore-provider-adapter-design.md(279〜343行目)で、自venture内の2つの
`increment_*`メソッド(user_id_linking.py)について、`UsageCounterStoreProtocol.
increment_or_reset`と同種のread-modify-write構成が類似のリスクを持つことを認識した
上で、意図的にトランザクション方式ではなくFirestoreの`Increment`フィールド変換を
採用したことが明記されている。理由は、自ventureの2メソッドには「月替わりでリセット」
のような条件分岐がなく、クライアント側で現在値を読んで分岐する必要がないため、
サーバー側加算で十分という判断である。したがって本件も反映漏れではなく、既に
検討済みの意図的な設計差異であることを再確認した。

### line-reservation-ai: 反映漏れではない(該当機能自体が存在しない)

line-reservation-aiには`UsageCounterStoreProtocol`・`increment_or_reset`に相当する
実装が見当たらず、`first_generation_notice_sent`に相当する概念も存在しない
(trial-start-anchor-decision.mdはトライアル開始基準点の決定のみを扱い、月次生成回数
カウンターとは無関係)。本venture側は予約件数ベースの`monthly-booking-limit-
notification-design.md`という別種の月次上限管理を持つが、course-set-pashaの
`increment_and_mark_notice()`が解決した「生成回数カウンター側の初回生成通知フラグ・
トライアル開始日時との結合」という問題構造そのものが存在しないため対象外である。

## 結論

4venture(kura-pasha・forklift-pasha・aircon-pasha・line-reservation-ai)のいずれも、
course-set-pashaフェーズ313の3フィールド結合パターンの「反映漏れ」には該当しない
ことを確認した。理由はそれぞれ異なる(データモデル分割・実装未着手・意図的な別方式・
機能自体が不存在)が、いずれも追加の実装対応は不要と判断する。フェーズ325・326から
持ち越していた次回候補(2)は本調査により解消済みとしてクローズする。

なお、forklift-pashaの`UsageCounterStoreProtocol`実Firestore接続アダプタが
将来着手される際には、kura-pashaフェーズ212の知見(read-modify-writeの並行書き込み
競合)に加え、本調査で確認した「月替わり条件分岐を伴う場合はトランザクション必須」
という整理(aircon-pashaフェーズ281の判断基準)を参照すべきである。

コード変更なし、文書追記のみのため回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(719件、変更なし)・
`python3 schema/validate_test_cases.py`(25件、変更なし)を実行しいずれも変更なしで
パスすることを確認した(回帰なし)。承認が必要なアクション(支払い・アカウント作成・
外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。
