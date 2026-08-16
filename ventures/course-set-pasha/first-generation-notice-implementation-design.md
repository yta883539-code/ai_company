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

## 残課題

- 実際の`usage_counter`コレクションへのフィールド追加、`increment_and_mark_notice()`の
  実装・実Firestore接続への配線は、実Firestore/実LINE API接続自体がオーナー承認待ちのため
  引き続き未着手のまま残す(設計・疑似コードまでは完了)。
- 「count>0だがfirst_generation_notice_sent=falseのまま」という不整合状態(3.で言及した
  安全側フォールバックの対象)が実運用でどの程度発生しうるかは、実Firestore接続後の
  実測データを待って再確認する。
