# 猶予期間中決済確認メッセージの謝罪強度是正(フェーズ続き363)

course-set-pashaフェーズ346(apology-tone-horizontal-check-result.md)で発見・申し送りされた
不一致への対応。

## 発見内容(申し送り事項)

`prototype/dunning_notification_scheduler.py`の`_MESSAGE_PAYMENT_CONFIRMED_IN_GRACE`
(猶予期間中、予約受付は一度も止まっていない場合の決済確認通知)のformal文言が、
`_MESSAGE_RECOVERED`(制限モードから実際に復旧した場合の通知)のformal文言と同じ強度の
謝罪「誠に申し訳ございませんでした」を使っていた。

## 判断

tone-and-manner-guideline.md方針3「謝罪はお店側の言葉として、しつこくしすぎない」を踏まえ、
謝罪自体を無くす(aircon-pasha方式)のではなく、謝罪の**強度**を実害の大小に合わせて
差別化する方針を採用した。

- `_MESSAGE_RECOVERED`(予約受付が実際に止まっていた): 「ご不便をおかけし、誠に申し訳
  ございませんでした」(最も強い表現を維持。実際の機会損失が発生した場面のため)。
- `_MESSAGE_PAYMENT_CONFIRMED_IN_GRACE`(予約受付は止まっていないが、決済確認の手間が
  発生した): formal文言を「お手数をおかけし、誠に申し訳ございませんでした」→
  「お手数をおかけいたしました」に軽量化。standard「お手数をおかけしました」・
  casual「お手数かけてすみませんでした」は元から軽い表現だったため変更なし。

この変更により、3トーンいずれも猶予期間中メッセージの謝罪が実際の復旧メッセージの謝罪より
強くならないことを保証する(テストで固定)。「お手数をおかけ」自体(決済確認の手間への
軽い謝意)は方針3の範囲内として残し、過度な丁寧さ(「誠に申し訳ございませんでした」)の
部分のみを是正した。

## 対応内容

- `prototype/dunning_notification_scheduler.py`: `_MESSAGE_PAYMENT_CONFIRMED_IN_GRACE`の
  formal文言を軽量化(コード変更1件)。
- `prototype/test_dunning_notification_scheduler.py`:
  `test_in_grace_apology_is_not_stronger_than_actual_outage_recovery`を新規追加し、
  3トーンいずれも`render_payment_confirmed_in_grace_message`が「誠に申し訳ございませんでした」
  を含まないことを固定するテストを追加(テスト1件追加)。
- 回帰確認: `python3 -m unittest discover -s prototype -p "test_*.py"`(1044件、新規1件含め
  全てパス)・`python3 schema/validate_test_cases.py`(28件、変更なしでパス)。

承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは発生していない。

## 次回候補

1. 承認待ち事項がオーナーから承認された場合はその着手を最優先。
2. 他venture・アイデア領域の前進。
