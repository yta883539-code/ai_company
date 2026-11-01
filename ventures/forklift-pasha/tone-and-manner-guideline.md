# メッセージ統一トーン&マナーガイドライン

aircon-pasha/tone-and-manner-guideline.md(フェーズ103)・course-set-pasha/
tone-and-manner-guideline.md(フェーズ203)・kura-pasha/tone-and-manner-
guideline.md(フェーズ86)・line-reservation-ai/tone-and-manner-guideline.mdは
いずれも既に存在するが、本ventureには相当するドキュメントがまだ無かった
(cross-venture parityのギャップ、oshien-pashaフェーズ48が発見した
market-research.md欠落と同種の棚卸しを本venture側で実施)。他venture同様の構成
(宛先の整理→基本方針→用途別文言一覧→発見した点→残る課題)で新設する。

## 他ventureとの前提の違い

本ventureはLINE非依存のWebフォーム+メール連携(tech-stack.md)であり、
course-set-pasha・kura-pasha・aircon-pasha・line-reservation-aiのようなLINE
トークルーム経由の通知(Push/Reply API)は存在しない。宛先は以下の3種類のみ。

1. **生成物本体(点検記録簿整形・期限リマインド)**: `inspection_record.body`・
   `reminder_notice`として事業者(点検者)に返す構造化出力(llm-system-prompt-
   draft.md)。見出しは付けない(course-set-pashaの出力1・2〈SNS投稿文〉同様、
   最終読者〈現場・検査業者等〉にそのまま見せる実務記録のため、宛名のような
   装飾は不要という既存の実態)。
2. **事業者向けメール通知**: 決済失敗検知・決済失敗再送・決済復旧・トライアル
   終了の4種類(`payment_failure.py`・`payment_failure_reminder_scheduler.py`・
   `trial_end_email_scheduler.py`)。いずれも件名・本文を持つ独立したメールで、
   件名には全角「【フォークリフトパシャっと】」を付す。
3. **運営(オーナー)向け通知**: `payment_failure_reminder_scheduler.
   OWNER_NOTIFICATION_EMAIL_SUBJECT_TEMPLATE`のみ。制限モードへ移行した事業者
   一覧を実際のオーナーへ届ける唯一のメールで、件名は「【フォークリフトパシャっと
   運営者通知】」と事業者向けの「【フォークリフトパシャっと】」から意図的に区別
   されている(aircon-pasha・kura-pashaの運営向け通知が「〜運営」接尾辞で区別
   する既存方針と同型)。

## 基本方針

1. **文体は「ですます調」・絵文字不使用を徹底する**
   (llm-system-prompt-draft.md 厳守事項7「文体は『ですます調』を既定とし、
   絵文字は使用しない(現場の実務記録であるため終始不使用)」)。本フェーズで
   `prototype/*.py`内の全メッセージ定数(`payment_failure.py`・
   `payment_failure_reminder_scheduler.py`・`trial_end_email_scheduler.py`・
   `overage_notifications.py`)を確認した結果、絵文字は一切使用されておらず、
   かつ生成物側の絵文字不使用はすでに`post_generation_checks.py`(厳守事項7の
   機械チェック、フェーズ8)が実装済みであることを確認した。既存の実態は方針と
   矛盾しない。

2. **見出し(件名)の記法は全角「【】」で統一されていることを確認した**
   course-set-pasha(フェーズ203)・kura-pasha(フェーズ86)はいずれも半角
   「[〜]」と全角「【〜】」の表記ゆれを1箇所発見・是正していたため、本venture
   でも同種の不整合がないか`prototype/*.py`内の件名・見出し文字列を全数確認
   した。`PAYMENT_FAILURE_DETECTED_EMAIL_NOTICE`・`PAYMENT_RECOVERED_EMAIL_
   NOTICE`・`PAYMENT_FAILURE_REMINDER_EMAIL_SUBJECT`・`EMAIL_SUBJECT`(トライアル
   終了)・`OWNER_NOTIFICATION_EMAIL_SUBJECT_TEMPLATE`のいずれも全角「【】」で
   統一されており、半角表記は見つからなかった(是正不要、既存の実態がすでに
   他venture是正後の状態と同じ)。

3. **謝罪表現の使いどころ(kura-pashaフェーズ86の記述を精緻化)**
   kura-pashaのtone-and-manner-guideline.mdは「決済関連の通知は事業者側の事情
   (カード期限切れ等)に起因するため謝罪表現を含めない」と記述しているが、
   本venture側の既存文言を確認した結果、`PAYMENT_RECOVERED_EMAIL_NOTICE`
   (決済復旧通知)には「ご不便をおかけしました。」という謝意が1文含まれて
   いる。これはkura-pasha/payment_failure_notification.PAYMENT_RECOVERED_
   MESSAGEの同一文言を踏襲したものであり、kura-pasha側の方針記述とkura-pasha
   自身の実装が厳密には一致していない(方針は「決済関連の通知全般は謝罪なし」
   だが、実装は復旧通知のみ謝罪ありという実態)。
   本venture側では、この実態の方が合理的だと判断し、以下のように方針を精緻化
   して採用する: 謝罪の要否は「決済失敗の原因が誰にあるか」ではなく「サービス
   の生成機能が一時停止していた期間が実際に発生したか」で判断する。
   - `PAYMENT_FAILURE_DETECTED_EMAIL_NOTICE`(検知時、まだ生成は通常利用可能):
     謝罪なし。事業者側の事情(カード期限切れ等)に起因し、かつこの時点では
     実害〈機能停止〉が生じていないため。
     (`PAYMENT_FAILURE_REMINDER_EMAIL_BODY`も同様に謝罪なし。)
   - `PAYMENT_RECOVERED_EMAIL_NOTICE`(復旧時): 猶予期間超過後に実際に生成が
     一時停止していた期間が生じた場合に送られるため、その停止期間自体への
     軽い謝意(「ご不便をおかけしました。」)を1回のみ含める。
   - `PAYMENT_SUSPENDED_NOTICE`(制限モード中に生成リクエストへ返す応答)は
     謝罪を含まない現状のままでよいと判断する。利用停止の事実と再開条件を
     端的に伝える案内文であり、繰り返し表示される性質の文言に謝罪を含めると
     むしろ煩雑になるため(aircon-pashaの「謝罪はしつこくしすぎない」方針と
     同じ理由)。
   他venture側(kura-pasha等)の方針記述をこちらから直接書き換えることは行わず、
   本venture固有の判断として本ファイルにのみ記録する(各venture側の判断に委ねる
   既存の横展開作法を踏襲)。

4. **生成物本体(出力)への「※」付き追加通知の位置づけ**
   `overage_notifications.format_usage_limit_notice()`(月間生成回数90%到達)・
   `format_vehicle_count_overage_notice()`(保有台数プラン超過)はいずれも
   見出しを持たず「※」始まりの1〜2文を生成物本体に追記する形で実装されている
   (`form_submission_flow.py`側での結合を想定)。これは独立したメール・通知
   ではなく生成物の一部であるため、上記1.の「生成物本体は見出し不要」の方針に
   包含され、新たな区分は不要と判断する。

## 用途別文言一覧(既存文言の集約・確認)

| 用途 | 宛先 | 既存文言の出典 | 見出し | 謝罪 |
|---|---|---|---|---|
| 点検記録簿整形・期限リマインド(生成物本体) | 事業者(点検者)向け | llm-system-prompt-draft.md | なし | なし |
| 月間生成回数90%到達の追加通知 | 事業者向け(生成物に追記) | `overage_notifications.format_usage_limit_notice()` | なし | なし |
| 保有台数プラン超過の追加通知 | 事業者向け(生成物に追記) | `overage_notifications.format_vehicle_count_overage_notice()` | なし | なし |
| 制限モード中の生成リクエスト応答 | 事業者向け | `payment_failure.PAYMENT_SUSPENDED_NOTICE` | なし | なし |
| 決済失敗検知通知 | 事業者向け(メール) | `payment_failure.PAYMENT_FAILURE_DETECTED_EMAIL_NOTICE` | 【フォークリフトパシャっと】 | なし |
| 決済失敗再送通知 | 事業者向け(メール) | `payment_failure_reminder_scheduler.PAYMENT_FAILURE_REMINDER_EMAIL_SUBJECT`/`_BODY` | 【フォークリフトパシャっと】 | なし |
| 決済復旧通知 | 事業者向け(メール) | `payment_failure.PAYMENT_RECOVERED_EMAIL_NOTICE` | 【フォークリフトパシャっと】 | あり(1文) |
| トライアル終了通知 | 事業者向け(メール) | `trial_end_email_scheduler.EMAIL_SUBJECT`/`render_trial_end_email_body()` | 【フォークリフトパシャっと】 | なし |
| 制限モード移行の運営者通知 | 運営(オーナー)向け(メール) | `payment_failure_reminder_scheduler.OWNER_NOTIFICATION_EMAIL_SUBJECT_TEMPLATE`/`_BODY_TEMPLATE` | 【フォークリフトパシャっと運営者通知】(意図的に区別、既存) | なし |

いずれも確認した範囲で絵文字は使用されておらず、全角「【】」で統一されており、
方針1・2と矛盾しない。

## 残る課題

- `ACCESS_URL_UNAVAILABLE_FALLBACK`(トライアル終了メール内、アクセスURL取得
  失敗時のフォールバック)は「お手数ですが」という軽い依頼表現のみで謝罪語を
  含まない。これは事業者側の事情に起因しない本venture側のURL発行基盤未接続
  (開発都中)が原因のフォールバックであり、他venture(course-set-pasha等)の
  「API失敗フォールバックには軽い謝意を1回添える」方針との整合性を厳密に
  言えば再検討の余地があるが、本venture未実装(次回候補)の`AccessUrlProvider`
  具象実装が確定してから、実際に顧客が目にする頻度(常用か例外時のみか)を
  踏まえて判断する方が精度が高いため、設計確定前の本フェーズでは変更を保留
  する。
- `access_url_reissue_handler.py`(アクセスURL再発行)は本フェーズ時点で
  settings.htmlからの実際の配線前(オーナー承認待ちの範囲)のため、顧客向け
  メール文言自体がまだ存在しない。配線時に本ガイドラインの方針(ですます調・
  絵文字不使用・全角【】見出し・謝罪は実害発生時のみ)に従って新設文言を作成
  する必要がある(次回候補)。
