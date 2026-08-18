# 初回生成確認案内(first_generation_notice_sent)実装設計

onboarding-settings-and-self-check-design.md フェーズ61で「`usage_counter`ドキュメントへの
永続化が必要」と方針決定したのみで、実際のフィールド定義・書き込みタイミングの疑似コードは
未着手だった。本ドキュメントはその設計を行う。実際のFirestore接続・LINE API接続自体は
引き続きオーナー承認待ちのため、ここでは設計・疑似コードの範囲にとどめる。

## 1. usage_counterドキュメントのフィールド追加

tech-stack.mdで定義した最小構成 `{month, count}` に、以下のフィールドを追加する。

```
usage_counter/{user_id}
  month: string                       # "2026-08" 形式、既存
  count: number                       # 既存
  first_generation_notice_sent: bool  # 新規追加。既定値 false
```

- ドキュメントが未作成(そのユーザーの初回生成)の場合、`get_count`相当の読み取り時に
  ドキュメント不在 → `count=0`・`first_generation_notice_sent=false` を暗黙値として扱う
  (line-reservation-aiのFirestoreドキュメント設計と同じ「不在=初期値」方針を踏襲)。
- `month`が繰り上がった場合(新しい月の初回生成)でも `first_generation_notice_sent` は
  リセットしない。確認案内は「そのユーザーにとって生涯で最初の生成成功時」の1回のみを
  意図しており、月次カウントのリセットとは独立したライフサイクルを持つ
  (limit-approaching-notification-design.mdの月次リセット対象フィールドとは別管理)。

## 2. cloud_function_webhook.pyへの配線(疑似コード)

既存の生成フロー(prototype/cloud_function_webhook.py)の末尾、レスポンス組み立て直前に
以下の分岐を挿入する想定。

```python
def handle_webhook(event):
    # ...既存の入力検証・LLM呼び出し・post_generation_checks...
    outputs = build_outputs(llm_result)  # SNS投稿文・LINE/Web告知文・履歴行

    counter = usage_counter.get(user_id)  # 不在なら {count: 0, first_generation_notice_sent: False}
    is_first_generation = (counter.count == 0)

    if is_first_generation and not counter.first_generation_notice_sent:
        outputs = append_first_generation_notice(outputs, gym_area_configured=bool(user.gym_area_pairs))
        notice_sent_this_call = True
    else:
        notice_sent_this_call = False

    # count増分とnotice_sentフラグ更新を1回の書き込みにまとめる(下記3.参照)
    usage_counter.increment_and_mark_notice(
        user_id,
        notice_sent=notice_sent_this_call,
    )

    return outputs
```

- `is_first_generation`の判定は「増分前のcountが0か」で行う。`first_generation_notice_sent`
  単独ではなく`count==0`との組み合わせで判定するのは、将来的に「ドキュメントは存在するが
  何らかの理由でnoticeだけ未送信」という不整合状態が発生しても、count>0なら重複送信しない
  安全側の挙動にするため。
- `append_first_generation_notice()`は既存の
  onboarding-settings-and-self-check-design.md記載の文面(確認案内本文、および
  ジム名・地域名未設定時の追加一文)をそのまま使う。新規のテキスト生成ロジックは
  持たない。

## 3. 書き込みの原子性

`count`のincrementと`first_generation_notice_sent`の更新を別々のFirestore書き込みに
分けると、1回目の書き込み成功後・2回目の書き込み前にWebhookが再試行された場合に
「countは増えたがフラグは立っていない」状態が生じ、次回呼び出しで確認案内が再送される
リスクがある(line-reservation-aiのfirestore-transaction-design.mdで扱った
hold()/confirm()の二重実行問題と同種)。そのため`increment_and_mark_notice()`は
count更新とフラグ更新を単一のFirestoreドキュメント更新(1回のset/update呼び出し)として
実装し、途中状態が外部から観測されないようにする設計とする。line-reservation-aiのような
複数コレクションにまたがる更新ではなく単一ドキュメント内の複数フィールド更新のため、
Firestoreの通常のトランザクション不要な単一ドキュメント更新の原子性で十分と判断する
(line-reservation-aiがトランザクションを要したのは複数ドキュメント〈予約枠と会話状態〉に
またがる整合性が理由であり、本ventureには該当しない)。

## 4. schema/output.schema.jsonへの影響

確認案内・未設定時の追加一文は、SNS投稿文・LINE/Web告知文の末尾に追記する形であり、
既存の`history_rows`等の構造化フィールドには影響しない。schema変更は不要と判断する。

## 5. gym_area_configuredの実データ参照経路

フェーズ73時点では`gym_area_configured`は呼び出し側が明示的に渡すbool引数のままだった
(実データ参照経路が未設計)。本節でその参照経路を設計する。

- onboarding-settings-and-self-check-design.md 1節の通り、ジム名・地域名は申込フォーム
  (ステップ1)の追加項目として、カンマ区切りの自由記述文字列(専用の構造化データストアは
  持たない)で入力される。この値の**書き込み**は申込フォーム提出フローの責務であり、
  本ventureのWebhook処理(cloud_function_webhook.py)の対象外(別途の申込受付経路の課題)。
- Webhook処理側が必要とするのは「そのuser_idについて、この文字列が非空で登録済みか」という
  **読み取り専用**の判定のみ。これを`GymAreaConfigStoreProtocol.is_configured(user_id) -> bool`
  として抽象化する(usage_counter・first_generation_notice_storeと同じ「差し替え可能な
  Protocol」方針を踏襲)。
- 想定する実データの格納先は、`usage_counter`とは別の最小構成ドキュメント
  `user_profile/{user_id} { gym_area_pairs: string }`(空文字列 = 未設定)。
  申込フォーム提出時に1回書き込まれるだけで生成フロー中に更新されない点、また
  `usage_counter`(月次カウント)とライフサイクルが異なる点から、同一ドキュメントに
  同居させず別ドキュメントとする。
- `process_memo_event()`側は`gym_area_config_store`が渡されない場合(実接続前の呼び出し・
  申込フォーム経路が未実装の段階)、既定で「設定済み」として扱う(誤って未設定の注意喚起を
  出さない安全側のデフォルト。usage_counter未接続時にカウント処理自体をスキップするのと
  同じ考え方)。ストアが渡された場合は`is_configured(user_id)`の結果をそのまま使う
  (未登録ユーザーは素直にFalse=未設定を返す)。

## 残課題

- (解消済み 2026-08-18 13:00 UTC: `prototype/cloud_function_webhook.py`フェーズ73で
  「差し替え可能なスタブ」方式のコード実装(`FirstGenerationNoticeStoreProtocol`・
  `InMemoryFirstGenerationNoticeStore`・`append_first_generation_notice()`・
  `process_memo_event()`への統合)を行った。ただし本節が求める`increment_and_mark_notice()`
  という「count増分とnotice_sent更新を単一書き込みにまとめる」形の原子性は、スタブ実装では
  複数ステップのまま(判定→追記→フラグ更新→count増分)であり未反映。実Firestore接続時に
  単一ドキュメント更新へまとめる作業が引き続き残る)
- 実際の`usage_counter`コレクションへのフィールド追加、実Firestore接続への配線自体は、
  実Firestore/実LINE API接続がオーナー承認待ちのため引き続き未着手のまま残す。
- 「count>0だがfirst_generation_notice_sent=falseのまま」という不整合状態(3.で言及した
  安全側フォールバックの対象)が実運用でどの程度発生しうるかは、実Firestore接続後の
  実測データを待って再確認する。
- (解消済み 2026-08-18 16:00 UTC: `gym_area_configured`の実データ参照経路を5節で設計し、
  `prototype/cloud_function_webhook.py`に`GymAreaConfigStoreProtocol`・
  `InMemoryGymAreaConfigStore`を実装、`process_memo_event()`の引数を
  `gym_area_configured: bool`から`gym_area_config_store: Optional[...]`へ差し替えた。
  テスト5件追加、全58件パス。詳細はREADME.mdフェーズ74参照)
- `user_profile/{user_id}.gym_area_pairs`を書き込む側(申込フォーム提出フロー自体の実装)は
  本venture・本ドキュメントの対象外の別課題として残る。実Firestore接続への配線自体は
  引き続きオーナー承認待ち。
