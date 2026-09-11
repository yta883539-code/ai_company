# メッセージ統一トーン&マナーガイドライン(フェーズ86)

aircon-pasha/tone-and-manner-guideline.md(フェーズ103)・course-set-pasha/
tone-and-manner-guideline.md(フェーズ203)・line-reservation-ai/tone-and-manner-
guideline.mdはいずれも既に存在するが、本ventureには相当するドキュメントがまだ無かった
(cross-venture parityのギャップ)。他venture同様の構成(基本方針→用途別文言一覧→
発見した不整合とその解消→残る課題)で新設する。

## 他ventureとの前提の違い

course-set-pashaは「顧客向け(公開・転送される文面)/内部記録/セッター本人向け運用
メッセージ」の3宛先を区別する必要があったが、本ventureはより単純である。

1. **職人向け(出力1〜3、すべて「下書き」)**: 出力1(受注内容整理メモ)・出力2
   (納品案内下書き)・出力3(お手入れ案内下書き)はいずれも`format_generated_reply()`で
   1通に連結され、職人本人がLINEで受け取る「下書き」であり(README.md「出力」参照)、
   顧客への転送前に職人自身が文面を確認・編集する前提(llm-system-prompt-draft.md)。
   course-set-pashaの出力1・2(そのまま転載される想定)とは異なり、本venture出力は
   最終読者(顧客)に直接届く保証が無いため、「顧客向け」と「職人向け運用メッセージ」を
   区別する必要が元から無い。
2. **職人向け運用メッセージ**: 出力1〜3以外の全て(対象外案内・入力不足時の再送依頼・
   各種フォールバック・トライアル終了通知・決済関連通知・解約関連通知・アカウント連携
   関連通知)。いずれも`craftsman_workshop`の契約者(`contractor_user_id`)がLINEトーク
   ルームで受け取る。
3. **運営(オーナー)向け通知**: `blocked_but_billing_owner_notification.py`のみ。
   ブロック中かつ契約継続中の候補一覧を実際のオーナー(本AI Companyの実オーナー、
   契約継続中の職人=顧客とは別人)へ届ける唯一のメッセージで、見出しも
   「【鞍パシャッと運営】」と職人向けの「【鞍パシャッと】」から意図的に区別されている
   (blocked-but-billing-owner-notification-design.md 3節で確認)。

## 基本方針

1. **文体はllm-system-prompt-draft.md厳守事項8のとおり「ですます調」・絵文字不使用を
   徹底する**
   職人向けの実務文書であるため、course-set-pashaのSNS投稿文(出力1のみ絵文字1〜2個
   許容)のような区分が無く、出力1〜3・運用メッセージ・オーナー向け通知のすべてに
   一貫して絵文字不使用が適用される。本フェーズで`prototype/*.py`内の全メッセージ定数を
   確認した結果、絵文字は一切使用されておらず既存の実態はこの方針と矛盾しないことを
   確認した。

2. **見出し(タイトル行)の記法を全角「【】」に統一する(不整合の発見・解消)**
   本フェーズで`prototype/*.py`内の運用メッセージ定数を全数確認したところ、
   course-set-pashaフェーズ203が発見したのと同種の不整合が本ventureにも1箇所存在する
   ことを発見した。
   - `payment_failure_notification.py`・`subscription_cancellation_notification.py`・
     `blocked_but_billing_owner_notification.py`は当初から全角「【鞍パシャッと】」
     (運営向けのみ「【鞍パシャッと運営】」)を使用。
   - しかし`cloud_function_webhook.format_trial_end_notification_message()`のみ
     半角「[鞍パシャッと] 」を使用していた(course-set-pashaフェーズ203が発見した
     `trial_end_scheduler.py`側の不整合と同じ種類の表記ゆれ)。
   - 本venture固有の原因として、`cloud_function_webhook.py`内の別のFlex Message風
     alt_text相当の記法との混同は確認されなかった(本ventureはaircon-pasha同様Flex
     Messageの実装自体が無く、常にプレーンテキスト本文を送信する設計)。単純な表記ゆれと
     判断し、他箇所と同じ全角「【鞍パシャッと】」に統一する修正を行った(本フェーズ)。
   - この文言をハードコードで検証するテストは無く(`test_cloud_function_webhook.py`は
     `format_trial_end_notification_message(...)`の戻り値を`in`演算子で比較する形の
     テストのみで、括弧の記法自体を検証する箇所は無い)、既存テストへの影響は無いことを
     確認した。`prototype/`配下の単体テスト9ファイル合計649件全件・
     `schema/validate_test_cases.py`27件いずれも変更前と同じ結果でパスすることを
     確認した。

3. **謝罪表現の使いどころ**
   職人側の入力に起因しない失敗(API失敗フォールバック`API_FAILURE_FALLBACK_MESSAGE`・
   文字数上限超過フォールバック`CHARACTER_LIMIT_FALLBACK_MESSAGE`)では「恐れ入りますが」
   程度の軽い謝意を1回のみ添える(aircon-pasha/course-set-pashaの「謝罪はしつこく
   しすぎない」方針を踏襲、既存文言はこの方針に合致していることを確認した)。決済関連の
   通知(`PAYMENT_FAILURE_DETECTED_MESSAGE`等)は職人側の事情(カード期限切れ等)に起因
   するため謝罪表現を含めない既存の実態も方針と合致する。

## 用途別文言一覧(既存文言の集約・確認)

| 用途 | 宛先 | 既存文言の出典 | 見出し |
|---|---|---|---|
| 受注内容整理メモ(出力1) | 職人向け(下書き) | llm-system-prompt-draft.md | 【受注内容整理メモ】 |
| 納品案内下書き(出力2) | 職人向け(下書き) | llm-system-prompt-draft.md | 【納品案内の下書き】 |
| お手入れ案内下書き(出力3) | 職人向け(下書き) | llm-system-prompt-draft.md | 【お手入れ案内の下書き】 |
| 対象外案内・入力不足時の再送依頼 | 職人向け | llm-system-prompt-draft.md | なし |
| 検証失敗フォールバック | 職人向け | `VALIDATION_FAILURE_FALLBACK_MESSAGE` | なし |
| API失敗フォールバック | 職人向け | `API_FAILURE_FALLBACK_MESSAGE` | なし |
| 文字数上限超過フォールバック | 職人向け | `CHARACTER_LIMIT_FALLBACK_MESSAGE` | なし |
| アカウント連携成功/要連携 | 職人向け | `LINKING_SUCCESS_MESSAGE`・`LINKING_REQUIRED_MESSAGE` | なし |
| トライアル終了通知 | 職人向け | `format_trial_end_notification_message()` | 【鞍パシャッと】(本フェーズで統一) |
| 決済失敗検知/復旧通知 | 職人向け | `payment_failure_notification.py` | 【鞍パシャッと】(既存) |
| 解約完了/取り消し通知 | 職人向け | `subscription_cancellation_notification.py` | 【鞍パシャッと】(既存) |
| ブロック中かつ契約継続中の候補通知 | 運営(オーナー)向け | `blocked_but_billing_owner_notification.py` | 【鞍パシャッと運営】(意図的に区別、既存) |

いずれも確認した範囲で絵文字は使用されておらず、方針1と矛盾しない。

## 残る課題

- 出力1〜3はいずれも「下書き」であり実際に顧客へ届く文面はcourse-set-pashaの出力1・2
  (SNS投稿文)のように本ventureのLLM生成物がそのまま公開される想定ではないため、
  絵文字ルールの検証(course-set-pasha「残る課題」相当)は本ventureでは不要と判断する。
  この判断根拠をここに明記する(将来の棚卸しで誤って対象外の課題を追加しないための記録)。
- 見出し「【】」統一は運用メッセージ・出力1〜3すべてを対象として確認済みで、統一されて
  いない箇所は本フェーズの修正により解消済み。
