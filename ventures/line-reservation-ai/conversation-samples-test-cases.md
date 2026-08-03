# 会話サンプル・プロンプトテストケース設計(2026-07-30時点、2026-07-31 14:58 UTC更新: N3・N4・E1・E3・E4・E7・E8の期待構造化出力を追記、2026-08-01 17:00 UTC更新: N3のトーン別(フォーマル/standard/カジュアル)自然文サンプルを追加、2026-08-01 18:00 UTC更新: 仮押さえ直後・前日リマインド・FAQ回答テンプレートのトーン別サンプルを追加)

llm-system-prompt-draft.md・json-output-retry-fallback.md の「次のステップ候補」で
挙げていた「会話サンプル(複数パターン、正常系・崩れ系)を用いたプロンプトテスト設計」に着手する。
本ドキュメントはテストケースの設計のみであり、実際のLLM呼び出し・実装・動作検証は未着手。
実装フェーズで、ここに挙げたケースを実際のプロンプトに投入し、出力を目視/自動チェックする想定。

## テストの目的
- llm-system-prompt-draft.md の「厳守事項」1〜8が、多様な入力パターンで守られるかを
  実装前に机上で洗い出し、抜け漏れのある指示文言を先に修正できるようにする。
- 各ケースに「期待される自然文の要旨」と「期待される構造化出力(JSON)」を明記し、
  実装後の自動テスト(期待値との突合)にそのまま転用できる形にする。

## 正常系ケース

### N1. 標準的な新規予約(情報が揃っている)
- 入力例: 「来週土曜15時にカットお願いしたいです。田中です。」
- 期待挙動: 厳守事項2により、即確定せずまず候補提示(該当時間+前後の空き)を返す。
  `confirmed: false`、`intent: "new_booking"`、`name: "田中"`、`menu: "カット"`、
  `datetime_candidate`に候補、`needs_owner_check: false`。

### N2. 情報が不足した新規予約
- 入力例: 「予約したいです」
- 期待挙動: 厳守事項1により、名前・メニュー・希望日時のうち不足項目を質問。
  `confirmed: false`。すべてnull/未確定のまま。

### N3. 候補提示後の確定
- 入力例(N1の続き): 「その時間でお願いします」
- 期待挙動: 名前・メニュー・日時が揃った時点で初めて`confirmed: true`。
  自然文でも「予約を確定しました」を使ってよい。
- 期待される構造化出力(2026-07-31 14:58 UTC追加、schema-validation-report.mdの指摘を受け明文化):
  ```
  {intent: "new_booking", name: "田中", menu: "カット",
   datetime_candidate: "来週土曜15時", confirmed: true, needs_owner_check: false}
  ```
  ※N1では候補提示段階のため`datetime_candidate`は「候補」の体だったが、
  確定後は具体的な単一の日時に置き換わる想定。

### N4. 常連客の簡略化(precheck-strengthening.md準拠)
- 入力例: 常連客「鈴木」(顧客DB登録: いつものメニュー=カラー、いつもの曜日・時間=土曜10時)
  から「いつもの時間でお願いします」
- 期待挙動: 確認項目は簡略化してよいが、厳守事項8により
  名前・メニュー・日時の確定条件そのものは省略しない(`confirmed`は3項目確定後のみtrue)。
  ただし常連客の場合は顧客DBの登録情報から名前・いつものメニュー・いつもの時間帯を
  補完してよく、顧客に個別の聞き直しはしない。
- 期待される構造化出力(2026-07-31 14:58 UTC追加):
  ```
  {intent: "new_booking", name: "鈴木", menu: "カラー",
   datetime_candidate: "土曜10時(顧客DB登録の通常予約枠)", confirmed: true,
   needs_owner_check: false}
  ```
  ※3項目とも顧客DBからの補完値だが、値が揃っている以上`confirmed: true`の
  条件(厳守事項8)は通常ケースと変わらない。

### N3-トーン. 予約確定メッセージのトーン別自然文サンプル(2026-08-01 17:00 UTC追加)
- 前提: message-tone-variants.mdで設計済みの「予約確定メッセージ」書き換え例(フォーマル/standard/カジュアル)を、
  N3(候補提示後の確定)の自然文側テストケースとして転記する。README.mdの「次にやること」1番目
  (トーン別出力サンプルの追加)に対応。
- 入力例: N3と同じ(「その時間でお願いします」、名前=田中、メニュー=カット、日時=8/9(土)15:30〜)。
- 構造化出力(JSON)はトーンに関わらず不変であることを確認する(トーンは自然文の言い回しにのみ影響し、
  `confirmed`/`name`/`menu`/`datetime_candidate`/`needs_owner_check`の値自体はstandardと同じ):
  ```
  {intent: "new_booking", name: "田中", menu: "カット",
   datetime_candidate: "8/9(土) 15:30〜", confirmed: true, needs_owner_check: false}
  ```
- 期待される自然文(フォーマル、message-tone-variants.md準拠):
  ```
  当店: ご予約を確定いたしました。
      8/9(土) 15:30〜 カット / 田中様
      前日にご案内のご連絡を差し上げますので、当日はお気をつけてお越しくださいませ。
  ```
- 期待される自然文(standard、既存のtone-and-manner-guideline.md準拠):
  ```
  当店: ご予約を確定いたしました。
      8/9(土) 15:30〜 カット / 田中様
      前日にリマインドをお送りしますので、当日お待ちしております!
  ```
- 期待される自然文(カジュアル、message-tone-variants.md準拠):
  ```
  当店: ご予約確定しました🙌
      8/9(土) 15:30〜 カット / 田中様
      前日にリマインドしますね、当日お待ちしてます!
  ```
- 検証観点: (1) JSON生成ロジックとトーン別テンプレート適用が独立している設計(message-tone-variants.mdの
  「言い換え規則は語尾・絵文字・感嘆符の3点のみ」)を、実際のテストケース形式でも矛盾なく表現できるかを
  実装前に確認できた。(2) 実LLMがJSON生成とトーン反映を同時に安定して行えるかは、
  pending-approval.md記載のAPIキー取得・課金承認後の実LLM検証で確認する(本ドキュメントは机上設計のみ)。

### 仮押さえ直後・前日リマインド・FAQ回答テンプレートのトーン別サンプル(2026-08-01 18:00 UTC追加)

README.mdの「次にやること」で残課題としていた、N3-トーン以外の3テンプレート
(仮押さえ直後・前日リマインド・FAQ回答)についてのトーン別(フォーマル/standard/カジュアル)
自然文サンプルを、message-tone-variants.mdの書き換え例からテストケース形式へ転記する。

**仮押さえ直後(pending-timeout-ux.md 1.、対応するJSONはE4と同じ`intent`/`menu`の型)**
- 入力例: N1と同じ新規予約の続きで、AIが仮押さえ(hold)を確定させた直後の一次応答。
- 構造化出力(JSON)はトーンに関わらず不変(`confirmed: false`、`needs_owner_check: false`のまま。
  仮押さえ自体はBookingSlotManager側の状態であり、この時点のJSONには表れない設計は既存のまま):
  ```
  {intent: "new_booking", name: null, menu: "カット",
   datetime_candidate: "8/9(土) 15:30〜", confirmed: false, needs_owner_check: false}
  ```
- 期待される自然文(フォーマル): 「8/9(土) 15:30〜 カットで仮押さえいたしました。お名前を教えていただけますでしょうか。(5分以内にご返信くださいますよう、お願い申し上げます)」
- 期待される自然文(standard、既存のまま): 「8/9(土) 15:30〜 カットで仮押さえいたしました。お名前を教えていただけますか?(5分以内にご返信いただけますと確実にご予約いただけます)」
- 期待される自然文(カジュアル): 「8/9(土) 15:30〜 カットで仮押さえしました!お名前教えてください(5分以内にお願いします🙏)」

**前日リマインド(tone-and-manner-guideline.md、reminder-timing-and-resend-rules.md準拠)**
- 前提: このメッセージは顧客の発話に対する応答ではなく、reminder-timing-and-resend-rules.mdの
  スケジュールロジックにより店舗側から能動的に送信されるプッシュメッセージである。したがって
  N3-トーン・仮押さえ直後のケースと異なり、対応する「入力例」「構造化出力(JSON)」は存在しない
  (LLMが顧客発話をintentに分類する通常フローの対象外)。トーン変換規則(語尾・絵文字・感嘆符)は
  ここでも同じ3点ルールをそのまま適用できるが、実装時はテンプレート生成トリガーがJSON出力ではなく
  スケジューラである点を区別して扱う必要があることが今回の作業で判明した新しい留意点。
- 期待される自然文(フォーマル): 「【リマインド】明日 8/9(土) 15:30〜 カットのご予約を承っております。ご都合が変わりました場合は、このトークにご返信くださいませ。キャンセル・変更を承ります。」
- 期待される自然文(standard、既存のまま): 「【リマインド】明日 8/9(土) 15:30〜 カットのご予約です。ご都合が変わった場合は、このトークにご返信いただければキャンセル・変更を承ります。」
- 期待される自然文(カジュアル): 「【リマインド】明日 8/9(土) 15:30〜 カットのご予約です🙌 予定変わったら、このトークに返信でキャンセル・変更できますよ!」

**FAQ回答テンプレート・駐車場あり(E10と同じ入力、faq-response-templates.md準拠)**
- 入力例: E10と同じ「駐車場はありますか」(駐車場「あり・3台分」を登録済み)。
- 構造化出力(JSON)はトーンに関わらず不変(E10と同一): `{intent: "faq", confirmed: false, needs_owner_check: false}`
- 期待される自然文(フォーマル): 「当店: 駐車場をご用意いたしております(3台分)。」
- 期待される自然文(standard、既存のまま、E10と同一): 「当店: 駐車場がございます(3台分)。」
- 期待される自然文(カジュアル): 「当店: 駐車場ありますよ(3台分)!」

- 検証観点: (1) 仮押さえ直後・FAQ回答はN3-トーンと同様「JSON不変・自然文のみトーン依存」の
  パターンで問題なく表現できた。(2) 前日リマインドは他の2つと異なり「対応するJSON入力」自体が
  存在しないプッシュ通知であることが明確になった。実装時はConversationFlowStateMachine経由の
  応答生成(JSON→自然文)と、reminder-timing-and-resend-rules.md側のスケジューラ発火による
  自然文生成(JSON経由しない)の2つの生成経路がある前提でトーン変換ロジックを共通化する必要が
  あり、この設計の詳細化(共通のトーン変換関数をどちらの経路からも呼べる形にする)は次の課題として残す。

## 崩れ系(会話の意図が曖昧・イレギュラー)

### E1. 曖昧な日時表現
- 入力例: 「来週の平日午後とかで空いてればお願いしたいです」
- 期待挙動: 厳守事項2の候補提示ステップで対応。複数候補を提示し、
  顧客の選択を待つ(`confirmed: false`のまま)。
- 期待される構造化出力(2026-07-31 14:58 UTC追加): 名前・メニューは未言及のためnullのまま。
  ```
  {intent: "new_booking", name: null, menu: null,
   datetime_candidate: "来週平日午後の空き候補(複数)", confirmed: false,
   needs_owner_check: false}
  ```

### E2. キャンセル・変更希望
- 入力例: 「すみません、明日の予約キャンセルできますか」
- 期待挙動: 厳守事項3により即座に確定的な返答をせず、
  「店舗側で確認します」の保留文言。`intent: "cancel"`、`needs_owner_check: true`。

### E3. 二重予約(仮押さえ中の枠への競合)
- 入力例: 顧客Bが、顧客Aが仮押さえ中の枠を指定
- 期待挙動: 厳守事項4により「現在確認中の枠のため少々お待ちください」を返し、
  確定処理は行わない。`confirmed: false`。
- 期待される構造化出力(2026-07-31 14:58 UTC追加): システム側で自動的に検知・保留する
  ケースであり、オーナーの個別判断を要するものではないため`needs_owner_check`はfalse。
  ```
  {intent: "new_booking", name: null, menu: null,
   datetime_candidate: "顧客Aが仮押さえ中の枠(確認中のため保留)", confirmed: false,
   needs_owner_check: false}
  ```

### E4. 保留タイムアウト
- 入力例: 顧客Aが仮押さえ後、pending-timeout-ux.mdで定義した時間内に応答なし
- 期待挙動: 厳守事項5により、pending-timeout-ux.mdの定型文をそのまま使用。
  文言の独自生成・アレンジはしない。
- 期待される構造化出力(2026-07-31 14:58 UTC追加): タイムアウトにより仮押さえ枠は解放され、
  日時候補もリセットされる。名前確認が完了する前にタイムアウトした想定のため`name`はnull。
  こちらもシステム側で自動処理する範囲でありオーナー確認は不要。
  ```
  {intent: "new_booking", name: null, menu: "カット",
   datetime_candidate: null, confirmed: false, needs_owner_check: false}
  ```

### E5. 予約以外の相談(医療・料金交渉・クレーム)
- 入力例: 「施術で肌荒れしたんですが大丈夫でしょうか」「もう少し値引きできませんか」
- 期待挙動: 厳守事項6により、AIが独自に判断・回答せず即座に
  「オーナーへおつなぎします」と案内。`intent: "escalation"`、`needs_owner_check: true`。
  会話ログをオーナー宛に転送(no-show-handling.mdの通知経路と統合)。

### E6. 予約と無関係な雑談・スパム的入力(2026-07-30 17:58 UTC: 対応済み、2026-07-30 21:58 UTC: 分類更新)
- 入力例: 「こんにちは!」「(URLのみのメッセージ)」
- 期待挙動: llm-system-prompt-draft.mdの厳守事項9b(旧9)に該当。短い定型挨拶または
  「ご用件をお知らせください」の一言のみを返し、断定回答・確定処理はしない。
  `intent: "faq"`、`confirmed: false`、`needs_owner_check: false`。
  ※厳守事項9と6(予約以外の相談)の境界線は、faq-escalation-boundary.md・
  厳守事項9a/9bの追記(2026-07-30 18:58〜20:58 UTC)により整理済み。
  下記E10〜E12で9a関連の新規テストケースを追加。
  ※`faq_segments`は特定の店舗FAQ項目(topic)に基づく回答ではない9bのため`null`のまま
  (2026-08-02 14:00 UTC改訂後もE10等の9aケースとは異なり対象外、
  json-schema-multi-intent-extension.md参照)。

### E7. JSON出力の構文崩れ(json-output-retry-fallback.mdの1)
- 入力例: 通常のN1と同じ入力だが、LLM応答が壊れたJSONを返すケースを想定
- 期待挙動: json-output-retry-fallback.mdの方針通り、1回のみ再生成リクエスト。
  再生成後も不正ならフォールバックへ。`needs_owner_check: true`扱い、`confirmed`は常にfalse。
- 期待される構造化出力(2026-07-31 14:58 UTC追加): リトライ後も構文が壊れたままで
  パース自体が成功しないため、N1の入力内容(名前・メニュー等)はバックエンドに引き継がれず、
  フォールバック処理が一律で合成する安全側の値になる。`intent`はスキーマ上null許容が
  ないため、フォールバック時は`"escalation"`(会話ログをオーナーに転送する経路)を割り当てる。
  ```
  {intent: "escalation", name: null, menu: null, datetime_candidate: null,
   confirmed: false, needs_owner_check: true}
  ```

### E8. 自然文とJSONの矛盾(json-output-retry-fallback.mdの4)
- 入力例: LLM応答の自然文が「予約を確定しました」なのに`confirmed: false`を返すケース
  (JSON自体はN1と同じ内容で構文的にはパース成功、`confirmed`値のみ矛盾)
- 期待挙動: 安全側判定(確定/要確認側を優先)によりフォールバック(3)として扱う。
  楽観的に「予約あり」とみなして処理を進めない。
- 期待される構造化出力(2026-07-31 14:58 UTC追加): E7と異なりパース自体は成功しているため
  `name`・`menu`・`datetime_candidate`はJSONの値をそのまま引き継ぐが、矛盾を検知した以上
  `confirmed`は常にfalseへ強制し、`needs_owner_check`はtrueへ上書きする。
  ```
  {intent: "new_booking", name: "田中", menu: "カット",
   datetime_candidate: "来週土曜15時台の候補", confirmed: false,
   needs_owner_check: true}
  ```

### E9. デポジット機能に関する問い合わせ(未実装機能、2026-07-30 17:58 UTC: 対応済み)
- 入力例: 「予約時に前払いできますか?」
- 期待挙動: llm-system-prompt-draft.mdに厳守事項10を追加済み。
  「対応可能/不可」を断定せず「現在確認中のため、後ほど店舗からご案内します」の
  保留文言を返し、オーナーへエスカレーション。`intent: "escalation"`、
  `confirmed: false`、`needs_owner_check: true`。

### E10. 店舗登録済み静的情報によるFAQ回答(厳守事項9a、2026-07-30 21:58 UTC追加、2026-07-31 00:59 UTC: 想定出力をfaq-response-templates.mdに揃えて具体化、2026-08-02 14:00 UTC: 想定構造化出力にfaq_segmentsを追加)
- 入力例: 「駐車場はありますか」(駐車場「あり・3台分」を登録済み)
- 期待挙動: 厳守事項9a・faq-escalation-boundary.mdの2番に該当。オーナー設定画面
  「店舗FAQ情報」欄に登録済みの情報をそのまま案内する自然文を返す。断定的な推測は行わず、
  登録内容の範囲のみ回答する。`intent: "faq"`、`confirmed: false`、`needs_owner_check: false`。
- 期待される自然文(faq-response-templates.mdの駐車場テンプレートに準拠):
  `当店: 駐車場がございます(3台分)。`
  ※登録値をそのまま埋め込むのみとし、近隣コインパーキング等の付加情報は生成しない。
- 期待される構造化出力(2026-08-02 14:00 UTC追加、json-schema-multi-intent-extension.md
  2026-08-02改訂に準拠。単一項目でもfaq_segmentsを1要素配列で付与する):
  ```
  {intent: "faq", name: null, menu: null, datetime_candidate: null,
   confirmed: false, needs_owner_check: false,
   faq_segments: [{topic: "parking", resolved: true}]}
  ```

### E13. 複合質問(複数FAQ項目にまたがる質問)の分割送信(faq-response-templates.md準拠、2026-07-31 00:59 UTC追加)
- 入力例13a: 「駐車場ある?支払いはカード使える?」(駐車場「あり・3台分」、支払い方法「現金・クレジットカード」を登録済み、いずれも回答可能な項目のみのケース)
- 期待挙動13a: 厳守事項9aにより、該当する2項目(駐車場・支払い方法)それぞれについて
  faq-response-templates.mdの項目別テンプレートに従い、1メッセージ1用件の原則通り
  2通に分けて返す。`intent: "faq"`、`confirmed: false`、`needs_owner_check: false`。
- 期待される自然文13a(2通、faq-response-templates.md「複合質問の処理例」に準拠):
  ```
  当店: 駐車場がございます(3台分)。
  当店: お支払い方法は現金、クレジットカードがご利用いただけます。
  ```
- 期待される構造化出力13a(json-schema-multi-intent-extension.md準拠):
  ```
  {intent: "faq", name: null, menu: null, datetime_candidate: null,
   confirmed: false, needs_owner_check: false,
   faq_segments: [{topic: "parking", resolved: true}, {topic: "payment", resolved: true}]}
  ```
- 入力例13b: 「駐車場ある?電子マネーは使える?」(駐車場は登録済み、電子マネー(QRコード決済)は未チェックのケース)
- 期待挙動13b: 駐車場は9aで直接回答するが、電子マネーは未チェット項目のため
  その部分のみ厳守事項6のエスカレーション文言に差し替える(全体を一律エスカレーションにはしない)。
  トップレベルの`intent`は`"faq"`のまま維持し、項目ごとのescalation有無は
  `faq_segments[].resolved`で表現する(json-schema-multi-intent-extension.md参照)。
  `confirmed: false`、`needs_owner_check: true`(未登録項目を含むため全体としてはtrue扱い)。
- 期待される自然文13b(2通、faq-response-templates.md「複合質問の処理例」に準拠):
  ```
  当店: 駐車場がございます(3台分)。
  当店: 恐れ入ります、その点は担当者に確認のうえ改めてご案内いたします。
  ```
- 期待される構造化出力13b(json-schema-multi-intent-extension.md準拠):
  ```
  {intent: "faq", name: null, menu: null, datetime_candidate: null,
   confirmed: false, needs_owner_check: true,
   faq_segments: [{topic: "parking", resolved: true}, {topic: "payment", resolved: false}]}
  ```
- 検証観点: 1回のLLM応答で複数意図(項目)を正しく分離し、項目ごとに9a/6のどちらに
  該当するかを混同なく判定できるか(faq-response-templates.mdの「未検証の仮説」に対応)。
  分離に失敗し1通にまとめて返す、または片方の項目を欠落させる崩れ方を実装後の
  自動テストで重点チェックする。

### E11. 店舗FAQ情報が未入力の項目についての質問(厳守事項9a境界、2026-07-30 21:58 UTC追加)
- 入力例: 「定休日はいつですか」(オーナーが「店舗FAQ情報」欄の定休日を未入力のまま)
- 期待挙動: 厳守事項9aの「未入力項目は9a対象外」規定により、9aでの回答はせず
  6番(オーナーへのエスカレーション)に振り分ける。「確認してご案内します」等の
  保留文言を返す。`intent: "escalation"`、`confirmed: false`、`needs_owner_check: true`。
  ※AIが「情報なし」と断定して回答しない点が9aの通常回答(E10)との違い。

### E12. 店舗が未チェックの支払い方法についての質問(厳守事項9a境界、2026-07-30 21:58 UTC追加)
- 入力例: 「PayPayは使えますか」(オーナーが「支払い方法」欄でQRコード決済を未チェック)
- 期待挙動: 厳守事項9a後半の規定により、チェック済みの支払い方法(現金・クレジット等)
  以外を問われた場合は「対応可否は不明」と断定せず6番エスカレーションへ振り分ける。
  `intent: "escalation"`、`confirmed: false`、`needs_owner_check: true`。
  ※E11と同様、9bの定型一言(雑談扱い)ではなく6番の保留・転送フローに乗る点に注意。

### E14. 支払い方法FAQ(9a)とデポジット機能問い合わせ(10)の境界(2026-07-31 08:59 UTC追加)
- 入力例: 「予約時にクレジットカードは使えますか」(支払い方法欄でクレジットカードをチェック済み)
- 期待挙動: 文言上は「予約時に」とあるが、店舗FAQ情報のチェック済み支払い方法に該当する
  一般的な支払い可否の質問であり、事前決済(デポジット)機能そのものへの言及がないため
  厳守事項9a(E10と同様)で回答する。`escalation_reason`フィールドは省略する。
  `intent: "faq"`、`confirmed: false`、`needs_owner_check: false`。
- 期待される自然文: `当店: お支払い方法はクレジットカードがご利用いただけます。`
- 期待される構造化出力(2026-08-02 14:00 UTC追加、E10と同様に単一項目でもfaq_segmentsを
  1要素配列で付与する):
  ```
  {intent: "faq", name: null, menu: null, datetime_candidate: null,
   confirmed: false, needs_owner_check: false,
   faq_segments: [{topic: "payment", resolved: true}]}
  ```
- 対比ケース(同一トピックだがescalation_reasonが変わる例): 「予約を確定する前にカードで
  先に一部支払っておくことはできますか」→ 支払い方法の可否ではなく前払い・デポジット機能
  そのものへの問い合わせのため、厳守事項10でエスカレーション。`intent: "escalation"`、
  `confirmed: false`、`needs_owner_check: true`、
  `escalation_reason: "unimplemented_feature"`、`feature_hint: "デポジット決済"`。
- 検証観点: 「支払い方法」という語が共通するだけで機械的に9aへ倒さず、
  「事前に」「先に」等、決済タイミングに関する言及の有無で9a/10を判定できるか。
  誤って前者を10番でエスカレーションすると9aの過剰保留(E11同様の過検出)になり、
  後者を9aで断定回答すると未実装機能の存在を誤って示唆してしまう点に注意。

### E15. ノーショー方針FAQとキャンセル料(違約金)機能問い合わせの境界(2026-07-31 08:59 UTC追加)
- 入力例: 「当日キャンセルの場合、キャンセル料はかかりますか」
- 前提: no-show-handling.mdの無断キャンセル対応は「発生時の記録・オーナーへの通知」設計に
  留まり、顧客への違約金請求・自動課金機能は現時点で未実装(deposit-payment-research.mdの
  デポジット機能もMVP範囲外)。よって店舗FAQ情報欄にも「キャンセル料の有無」という
  登録項目自体が現状存在しない。
- 期待挙動: 9aの登録済み項目(住所・アクセス/駐車場/支払い方法)に「キャンセル料」は
  含まれないため9aでは回答不可。同時に、キャンセル料徴収は現時点で未実装の機能への
  問い合わせに当たるため、厳守事項6(E11の「未入力項目」相当の保留)ではなく
  厳守事項10で処理する。`intent: "escalation"`、`confirmed: false`、
  `needs_owner_check: true`、`escalation_reason: "unimplemented_feature"`、
  `feature_hint: "当日キャンセル料の徴収"`。
- 期待される自然文: `当店: その点は担当者に確認のうえ改めてご案内いたします。`
  (E9のデポジット問い合わせと同一の保留文言を流用し、断定回答はしない。)
- 検証観点: 「未入力項目(E11、escalation_reason省略のまま6番相当)」と
  「未実装機能(E15、escalation_reason: unimplemented_feature)」はどちらも表面上
  「保留してエスカレーション」という同じ挙動に見えるため、通知ログ集計画面での
  分類ラベル付けを見据えて両者をLLMが区別できるかが本ケースの主眼。
  区別の基準は「その項目がそもそも店舗FAQ情報欄の入力対象か否か」であり、
  対象外(キャンセル料・前払い等の制度そのものが存在しない)なら
  unimplemented_feature、対象だが未入力・未チェックならconsultation寄りの
  無印(E11/E12同様)とする。

### E16. 3項目にまたがる複合質問(faq_segments配列が3要素以上になるケース、2026-07-31 11:58 UTC追加)
- 入力例: 「駐車場ある?支払いはカード使える?電子マネーは使える?」(駐車場「あり・3台分」、
  支払い方法「現金・クレジットカード」は登録済み、電子マネー(QRコード決済)は未チェックのケース。
  json-schema-multi-intent-extension.mdの未検証事項「3項目以上でも配列方式が破綻しないか」の机上検証)
- 期待挙動: 厳守事項9aにより駐車場・支払い方法(カード)は直接回答、電子マネーのみ
  未チェット項目のため厳守事項6相当の保留文言に差し替える。E13bと同じ判定ロジックを
  項目数3件に拡張するだけで、`faq_segments`配列の要素数を2→3に増やす以外の
  スキーマ変更・分岐追加は不要(topic列挙値はaccess/parking/payment/hours/otherの
  範囲内に収まり、支払い方法とは別に電子マネーは既存のpaymentトピック内の
  未チェック項目として扱う。E12と同じ扱い)。`intent: "faq"`、`confirmed: false`、
  `needs_owner_check: true`(未チェック項目を含むため全体としてはtrue扱い)。
- 期待される自然文(3通、1メッセージ1用件の原則を維持):
  ```
  当店: 駐車場がございます(3台分)。
  当店: お支払い方法は現金、クレジットカードがご利用いただけます。
  当店: 恐れ入ります、その点は担当者に確認のうえ改めてご案内いたします。
  ```
- 期待される構造化出力(json-schema-multi-intent-extension.md準拠):
  ```
  {intent: "faq", name: null, menu: null, datetime_candidate: null,
   confirmed: false, needs_owner_check: true,
   faq_segments: [{topic: "parking", resolved: true}, {topic: "payment", resolved: true},
                   {topic: "payment", resolved: false}]}
  ```
- 検証観点: 同一topic(payment)が「カード(resolved: true)」「電子マネー(resolved: false)」の
  ように1つの複合質問内で2回出現しうる点に注意。`faq_segments`はtopicの重複を許容する配列
  として設計されており(json-schema-multi-intent-extension.mdにtopicの一意性を求める記述は
  無い)、この点は仕様として問題ないが、通知ログ集計画面(owner-settings-wireframe.md)で
  topicごとに単純集計する場合は「同一topicの重複要素」を1件としてカウントするか
  未回答分のみカウントするかの集計ルールを別途詰める必要がある(未着手)。
  なお項目数が2件→3件に増えても配列の構造・リトライ/フォールバック判定
  (json-output-retry-fallback.md)に変更は不要であることを机上で確認した
  (要素数に上限を設けない設計のため)。実LLMが4項目以上でも安定して配列を
  生成できるかは引き続き実装フェーズでの検証が必要。

### E17. 営業時間FAQ(厳守事項9a、hours-other-faq-topic-resolution.md 2026-08-03 08:00 UTC追加)
- 入力例: 「営業時間を教えてください」(曜日別営業時間トグルOFF・休憩時間未設定のシンプルな店舗。
  営業時間9:00〜18:00、定休日は日曜のみ登録済み)
- 期待挙動: 厳守事項9aに該当。曜日別営業時間・休憩時間を使わないシンプルな店舗のみ、
  登録された開始・終了時刻と定休日をそのまま案内する自然文を返す
  (faq-response-templates.mdの営業時間テンプレートに準拠)。`intent: "faq"`、
  `confirmed: false`、`needs_owner_check: false`。
- 期待される自然文(faq-response-templates.mdの営業時間テンプレートに準拠):
  `当店の営業時間は09:00〜18:00です(定休日: 日曜)。`
- 期待される構造化出力:
  ```
  {intent: "faq", name: null, menu: null, datetime_candidate: null,
   confirmed: false, needs_owner_check: false,
   faq_segments: [{topic: "hours", resolved: true}]}
  ```
- 補足: 曜日別営業時間トグルON、または休憩時間を設定している店舗では、単一の開始・終了時刻の
  テンプレートでは不正確な案内になるため自動回答の対象外とし、厳守事項6のエスカレーション
  (保留文言)に振り分ける。この判定はCloud Function B呼び出し側が`store_faq_info`に`hours`
  キーを設定するかどうかで表現する(hours-other-faq-topic-resolution.md参照)。

## 本テストケース設計で見つかったプロンプトの抜け漏れ(修正済み)
- E6(雑談・スパム的入力)とE9(未実装機能への問い合わせ)は、当初
  llm-system-prompt-draft.mdの厳守事項1〜8のどれにも明確に該当していなかったが、
  2026-07-30 17:58 UTCの改訂で厳守事項9(雑談・スパム→定型一言返答、faq扱い)・
  10(未実装機能問い合わせ→断定回答せずエスカレーション)として反映済み。

## 未検証・要検討事項
- 上記すべてのケースは机上設計であり、実際のLLM(実装時に採用するモデル)での
  出力安定性は未検証。実装フェーズで本ケース群を自動テストとして実行する必要がある。
- ~~厳守事項9(雑談・スパム)と6(予約以外の相談)の境界線(例:単純な営業時間FAQ等)が
  未整理のまま残っている~~ → 2026-07-30 18:58〜21:58 UTCの一連の改訂
  (faq-escalation-boundary.md、厳守事項9a/9b分割、E10〜E12追加)で整理済み。
- E10〜E12は机上設計のみで、実LLMでの「未入力/未チェック項目を9aで答えず
  6へ振り分ける」判定精度は未検証。9aの登録済み情報と9b/6の境界誤判定
  (例:未入力項目を誤って「情報なし」と断定回答してしまう)がないか、
  実装後の自動テストで重点的に確認する必要がある。
- ~~N3・N4・E1・E3・E4・E7・E8の期待される構造化出力(JSON)が未明記のまま
  残っている~~ → 2026-07-31 14:58 UTCで全ケース明文化し、schema/validate_test_cases.pyの
  フィクスチャにも追加済み(schema-validation-report.md参照)。E7(構文崩れ)のフォールバック値は
  実際のLLM出力ではなくバックエンドが合成する安全側の値である点に注意。

## 次のステップ候補
- (解消済み 2026-08-01 17:00 UTC: N3(予約確定メッセージ)についてフォーマル/standard/カジュアルの
  3トーン分の期待自然文サンプルを追加した。JSON側は不変であることを明記。他のテンプレート
  (前日リマインド・仮押さえ直後・FAQ回答)のトーン別サンプルは未追加のため今後の課題として残す)
- (解消済み 2026-08-01 18:00 UTC: 仮押さえ直後・前日リマインド・FAQ回答テンプレートについて
  N3と同様の形式でトーン別(フォーマル/standard/カジュアル)期待自然文サンプルを追加した。
  この過程で、前日リマインドのみ「対応するJSON入力が存在しないプッシュ通知」であり、
  仮押さえ直後・FAQ回答とは生成経路が異なる(スケジューラ発火 vs LLM出力起点)ことが判明。
  この2経路でトーン変換ロジックをどう共通化するかの実装設計は次の課題として残す)
- 前日リマインドのスケジューラ発火経路と、仮押さえ直後・FAQ回答等のLLM出力起点経路とで、
  message-tone-variants.mdのトーン変換ロジック(語尾・絵文字・感嘆符の3点)を共通の関数として
  実装できるか(tech-stack.mdの技術選定と合わせて)検討する
- E10〜E16を含めたテストケース群の実装フェーズでの自動テスト化(実LLM呼び出しでの出力検証)
- エスカレーション(no-show-handling.mdの通知設計)発生時のオーナー通知文面の具体化(複合質問時にどのtopicが未回答かを含める)
- E16で発見した「同一topicが複合質問内で重複しうる」場合の通知ログ集計ルール(重複を1件とするか未回答分のみカウントするかの決定)を検討する
- ~~json-schema-multi-intent-extension.mdで設計した`faq_segments`拡張が、3項目以上の複合質問でも破綻しないか~~ → E16で机上検証済み(スキーマ・リトライ設計の変更は不要)。実LLMでの安定生成確認は引き続き実装フェーズで必要。
