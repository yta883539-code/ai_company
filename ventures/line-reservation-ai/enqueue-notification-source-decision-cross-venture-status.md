# enqueue失敗時オーナー通知「送信元」確定方針の他venture展開状況

## 背景

フェーズ続き388で、本venture(line-reservation-ai)のenqueue-fallback-owner-
notification-design.md 4節に残っていた送信元未確定事項((a) HTTPハンドラ経由 or
(b) 定期実行ジョブ経由)を(a)に確定し、通知文言テンプレート関数
`render_enqueue_failed_owner_notification()`を`prototype/cloud_function_webhook.py`に
実装した(6節に確定理由を追記)。同フェーズの次回候補(2)で、「LINE Webhook受信→
Cloud Tasksへenqueue→非同期本処理」という同一の2段構成を持つ他venture
(aircon-pasha・kura-pasha・course-set-pasha)についても同種の通知設計を横展開できるか
の確認が残っていたため、本フェーズで現状を確認した。

(forklift-pasha・event-komiguai-pasha・oshien-pashaの3ventureは、kura-pasha
フェーズ続き307のcross-venture-enqueue-fallback-applicability-review.mdで既に
「Cloud Tasks非同期キュー構成を採用していないため該当なし」と結論済みのため、
本レビューの対象外とする。)

## 確認結果

対象3venture(aircon-pasha・kura-pasha・course-set-pasha)はいずれも
`enqueue-fallback-owner-notification-design.md`を持ち`dispatch_webhook_events()`を
実装済みだが、grepで確認した限り、送信元(a)/(b)の確定記述・
`render_enqueue_failed_owner_notification()`相当の実装はいずれも未着手だった。

- **aircon-pasha**: `enqueue-fallback-owner-notification-design.md`に
  「HTTPハンドラ経由」「定期実行ジョブ経由」の記述なし。`prototype/cloud_function_webhook.py`に
  `render_enqueue_failed_owner_notification`なし。
- **kura-pasha**: 同上(未確定・未実装)。
- **course-set-pasha**: `enqueue-fallback-owner-notification-design.md`内の
  (a)/(b)表記は本論点とは別の項目(日次バッチ洗い出し vs 永続通知済みフラグによる
  冪等性確保の選択)であり、送信元確定の記述は無し。

## 所見・引き継ぎ事項

3venture共通で、本venture phase 388の確定理由(enqueue失敗という低頻度異常系の
早期検知優先・HTTPハンドラが`destination`を既に保持している・Function A単一責務設計を
破らない)が同様に成立する可能性が高いと見込まれるが、各venture固有の
Function A/B構成差異(例: aircon-pashaの`process-memo-event-async-split-design.md`等)を
未確認のため、本フェーズでは断定・他venture側ファイルの変更は行わない。
各ventureが次回ローテーションで前進する際、本ファイルを参照の上、(a)確定の横展開が
妥当か再確認することを引き継ぎ事項とする。

## 検証方法

```
grep -n "送信元\|HTTPハンドラ経由\|定期実行ジョブ経由" \
  ventures/{aircon-pasha,kura-pasha,course-set-pasha}/enqueue-fallback-owner-notification-design.md
grep -n "render_enqueue_failed_owner_notification" \
  ventures/{aircon-pasha,kura-pasha,course-set-pasha}/prototype/cloud_function_webhook.py
```

コード変更なし(現状確認と引き継ぎ事項の記録のみ)。他venture側ファイルの変更はしていない。
