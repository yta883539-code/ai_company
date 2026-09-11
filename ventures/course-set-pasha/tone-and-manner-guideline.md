# メッセージ統一トーン&マナーガイドライン(フェーズ203)

aircon-pasha/tone-and-manner-guideline.md(フェーズ103)・line-reservation-ai/
tone-and-manner-guideline.mdはいずれも既に存在するが、本ventureには相当するドキュメントが
まだ無かった(cross-venture parityのギャップ)。他venture同様の構成(基本方針→用途別文言
一覧→発見した不整合とその解消→残る課題)で新設する。

## 他ventureとの前提の違い

aircon-pashaは「業者→依頼者」という単方向の実務代行構造で、依頼者向け(`completion_report`・
`care_guide`)と業者向け(その他運用メッセージ)の2種類の宛先を区別するのが基本方針の核だった。
本ventureは以下の3種類の宛先が存在し、aircon-pasha以上に区別が必要である。

1. **顧客向け(公開・転送される文面)**: 出力1(SNS投稿文下書き)・出力2(公式LINE/Web告知文
   下書き)。セッター(契約者)がそのままInstagram/X・LINE公式アカウント・Webサイトに
   転載する前提(README.md「出力」参照)で、ジムの会員・フォロワーという最終読者が
   セッター自身とは別に存在する。
2. **内部記録(セッター本人のみが見る)**: 出力3(課題入れ替え履歴、表形式1行)。
   顧客に見せる前提が無く、スプレッドシート等への転記用の事務記録(mvp-flow-draft.md参照)。
3. **セッター本人向け運用メッセージ**: 上記1・2以外の全て。対象外案内(厳守事項7)・
   入力不足時の再送依頼(厳守事項8)・上限超過時のフォールバック通知
   (character-limit-fallback-design.md)・API失敗時のフォールバック通知
   (api-call-failure-handling.md)・トライアル終了通知(trial-end-notification-design.md)・
   決済失敗検知/リマインド/復旧通知(payment-failure-dunning-design.md)・解約関連の各通知
   (subscription-cancellation-flow-design.md、subscription-cancellation-notification-
   design.md)。いずれもセッター(契約者)本人がLINE公式アカウントとのトークルームで
   受け取るのみで、顧客への転送は想定しない。

## 基本方針

1. **宛先3種類を混在させない**
   顧客向け文面(出力1・2)には運用上の案件(決済・トライアル等)の言及を一切含めない。
   セッター本人向け運用メッセージには、出力1・2のような顧客向けの宣伝的な言い回し
   (ハッシュタグ・来店を促す一文等)を含めない。

2. **顧客向け文面(出力1・2)のトーンはllm-system-prompt-draft.md厳守事項9のとおり**
   「ですます調」を既定とし、絵文字は出力1(SNS投稿文)のみ1〜2個程度まで許容、出力2
   (公式LINE/Web告知文)・出力3(履歴記録)には使用しない。この既存ルールを本ガイドラインが
   代替するものではなく、そのままここに集約・再確認する。

3. **セッター本人向け運用メッセージも同じくですます調・絵文字不使用で統一する**
   既存の運用メッセージ(下記「用途別文言一覧」参照)をprototype/配下で確認したところ、
   いずれも絵文字を使わないですます調で統一されており、aircon-pashaの方針3
   (依頼者向け・業者向けでトーン自体に差は無い)と同じ実態だった。この既存の実態を
   本ガイドラインで明文化し、今後新設する運用メッセージの既定ルールとする。

4. **見出し(タイトル行)の記法を全角「【】」に統一する(不整合の発見・解消)**
   本フェーズで`prototype/*.py`内の運用メッセージ定数を全数確認したところ、見出し行の
   括弧記法が2種類に分裂していたことを発見した。
   - `subscription_cancellation_notification.py`(解約完了・解約取り消し・ダウングレード
     予約通知)は当初から全角「【コースセットパシャッと】」を使用。
   - 一方、`payment_recovery_notification.py`・`payment_failure_reminder_scheduler.py`・
     `trial_end_scheduler.py`の合計5箇所は半角「[コースセットパシャッと] 」を使用していた
     (`payment_recovery_notification.py`のコメントに「line-reservation-ai・aircon-pashaと
     同じ考え方」との記載があり、aircon-pashaの文言を参考にした際にそのまま転用したと
     推測される)。
   - しかし半角「[...] 」はaircon-pasha側では`*_ALT_TEXT`定数(LINE Flex Messageの
     プレビューテキスト欄専用)の記法であり、本文そのものの見出しではない
     (aircon-pashaはFlex Messageの本文とalt_textを別々に持つ)。本ventureは
     `prototype/*.py`内にFlex Message・alt_textの実装が一切無く(grep確認済み)、
     常にプレーンテキストの本文をそのまま送信する設計(kura-pashaと同じ、cloud_function_
     webhook.py参照)であるため、alt_text専用の記法をそのまま本文の見出しに転用したのは
     本ventureの実態に合わない不整合と判断した。
   - 半角側5箇所(`payment_failure_reminder_scheduler.PAYMENT_FAILURE_REMINDER_TEMPLATE`・
     `payment_recovery_notification._TITLE_LINE`・
     `payment_recovery_notification.PAYMENT_FAILURE_DETECTED_TEMPLATE`・
     `trial_end_scheduler.TRIAL_END_NOTIFICATION_TEMPLATE`・
     `trial_end_scheduler.TRIAL_END_NOTIFICATION_TEMPLATE_WITH_AREA_COUNT`)を、先行していた
     `subscription_cancellation_notification.py`の全角「【】」に統一する修正を行った(本フェーズ)。
     いずれの文言もハードコードされた文字列を直接検証するテストは無く(`test_cloud_function_
     webhook.py`の該当箇所は`assertIn("コースセットパシャッと", sent_text)`という括弧を含まない
     部分文字列検証のみ)、既存テストへの影響は無いことを確認した。venture全体の単体テスト
     (`python3 -m unittest discover -s prototype -p "test_*.py"`)575件全件・schema検証
     (`python3 schema/validate_test_cases.py`)9件いずれも変更前と同じ結果でパスすることを
     確認した。

5. **謝罪表現の使いどころ**
   セッター側の入力に起因しない失敗(上限超過フォールバック、API失敗、想定外エラー)では
   「恐れ入りますが」程度の軽い謝意を1回のみ添える(aircon-pasha/line-reservation-aiの
   「謝罪はしつこくしすぎない」方針を踏襲、既存の`VALIDATION_FAILURE_FALLBACK_MESSAGE`・
   `LENGTH_LIMIT_FALLBACK_MESSAGE`はこの方針に合致していることを確認した)。決済関連の
   通知(`PAYMENT_SUSPENDED_MESSAGE`等)はセッター側の事情(カード期限切れ等)に起因するため
   謝罪表現を含めない既存の実態も方針と合致する。

## 用途別文言一覧(既存文言の集約・確認)

| 用途 | 宛先 | 既存文言の出典 | 見出し |
|---|---|---|---|
| SNS投稿文下書き(出力1) | 顧客向け | llm-system-prompt-draft.md厳守事項4 | (本文そのもの) |
| 公式LINE/Web告知文下書き(出力2) | 顧客向け | llm-system-prompt-draft.md厳守事項5 | (本文そのもの) |
| 課題入れ替え履歴(出力3) | 内部記録 | llm-system-prompt-draft.md厳守事項6 | (該当なし) |
| 対象外案内(厳守事項7) | セッター向け | llm-system-prompt-draft.md厳守事項7 | なし |
| 入力不足時の再送依頼(厳守事項8) | セッター向け | llm-system-prompt-draft.md厳守事項8 | なし |
| 解約意図案内(厳守事項7a(i)(ii)(iv)) | セッター向け | subscription-cancellation-flow-design.md | なし |
| 検証失敗フォールバック | セッター向け | `VALIDATION_FAILURE_FALLBACK_MESSAGE` | なし |
| API失敗フォールバック | セッター向け | `API_FAILURE_FALLBACK_MESSAGE` | なし |
| 文字数上限超過フォールバック | セッター向け | `LENGTH_LIMIT_FALLBACK_MESSAGE` | なし |
| 生成一時停止通知(トライアル/上限) | セッター向け | `GENERATION_PAUSED_MESSAGE` | なし |
| 決済保留中の一時停止通知 | セッター向け | `PAYMENT_SUSPENDED_MESSAGE` | なし |
| トライアル終了通知 | セッター向け | `trial_end_scheduler.py` | 【】(本フェーズで統一) |
| 決済失敗検知/リマインド通知 | セッター向け | `payment_recovery_notification.py`他 | 【】(本フェーズで統一) |
| 決済復旧通知 | セッター向け | `payment_recovery_notification.py` | 【】(本フェーズで統一) |
| 解約完了/取り消し通知 | セッター向け | `subscription_cancellation_notification.py` | 【】(既存) |

いずれも確認した範囲で絵文字は使用されておらず、方針2・3と矛盾しない。

## 残る課題

- 出力1(SNS投稿文)自体は絵文字1〜2個を許容する方針だが、実際にLLMが生成する絵文字の
  選定基準(ジムの雰囲気に合わないスタンプ的な絵文字を避ける等)は未検証。
  llm-quality-verification-plan.md実施時に合わせて確認することを推奨する。
- 見出し「【】」統一は運用メッセージ側のみを対象とした。出力1・2・3(顧客向け・内部記録)は
  そもそも見出し行を持たない設計のため対象外である旨をここに明記する(将来の棚卸しで
  誤って対象と誤認しないための記録)。
