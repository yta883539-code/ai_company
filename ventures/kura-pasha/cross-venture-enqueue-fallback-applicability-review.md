# enqueue-fallback-owner-notification / 監視指標設計の他venture横展開可否レビュー

## 背景

フェーズ続き305・306(enqueue-fallback-owner-notification-design.md横展開、
cloud-monitoring-alert-policy-design.md 5節)の「次回候補」として、
forklift-pasha・event-komiguai-pasha・oshien-pashaの3ventureについても
Cloud Tasksのenqueue失敗時フォールバック挙動・関連する監視指標設計が
適用できるかの個別確認が残っていた。本フェーズで確認した。

## 確認結果: 3venture全て「対象外」

grep("Cloud Tasks|enqueue", ventures/<slug>/*.md)を各venture配下の全Markdownに対し実行し、
該当する設計文書・言及の有無を確認した。

- **forklift-pasha**: 0件。`stripe-webhook-entry-point-design.md`のみ存在し、Cloud Tasks等の
  非同期キューへの言及は無い。
- **oshien-pasha**: 0件。同様に`stripe-webhook-entry-point-design.md`のみで、Cloud Tasks言及なし。
- **event-komiguai-pasha**: 1件のみ(`deployment-runbook.md`)。ただし該当箇所を確認した結果、
  言及は「本ventureにはCloud Tasks経由の非同期処理は不要」という設計上の除外理由の説明
  だった。同ドキュメントは、line-reservation-aiのFunction B(Cloud Tasks経由の非同期本処理)・
  Function C(リマインド定期実行)に相当する処理が、本ventureでは不要である理由を以下のように
  明記している:
  - 会話状態マシンが無く「1フォーム送信=1イベント→LLM呼び出し→4出力生成→画面表示」で
    同期的に完結する構成であるため。
  - 課金モデルが都度決済(one-time-checkout)であり、継続課金のサブスクリプション状態管理・
    複数Webhookイベント種別の分岐が不要なため、Stripe Webhook処理自体も単純。

## 結論

3venture(forklift-pasha・event-komiguai-pasha・oshien-pasha)はいずれも、
kura-pasha・course-set-pasha・aircon-pasha・line-reservation-aiが持つ
「LINE Webhook受信→Cloud Tasksへenqueue→非同期本処理」という2段構成を
そもそも採用していない(Stripe Webhookのみ、または同期完結型のフォーム処理)。
したがって、enqueue-fallback-owner-notification-design.mdのパターンおよび
cloud-monitoring-alert-policy-design.md 5節の監視指標設計は、**3venture全てに
適用対象が存在せず「該当なし」**と判断する。今後、これら3ventureが将来的に
Cloud Tasks等の非同期キューを採用する設計変更を行う場合にのみ、本パターンの
適用を再検討すればよい。

本レビューにより、フェーズ続き305・306の次回候補(2)はクローズとする。

## 検証方法

```
grep -lE "Cloud Tasks|enqueue" ventures/forklift-pasha/*.md ventures/event-komiguai-pasha/*.md ventures/oshien-pasha/*.md
```

コード変更・設計変更は発生していない(横展開不要という結論の記録のみ)。
