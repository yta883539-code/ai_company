# メッセージ統一トーン&マナーガイドライン(フェーズ60)

他6venture(aircon-pasha・course-set-pasha・event-komiguai-pasha・forklift-pasha・
kura-pasha・line-reservation-ai)はいずれもtone-and-manner-guideline.mdを作成済みだが、
本ventureには同種の文書が未作成のまま残っていた。この欠落はcourse-set-pashaフェーズ346
(apology-tone-horizontal-check-result.md)で「oshien-pashaはtone-and-manner-guideline.md
自体が未作成で方針記述と実装の不一致を検出できる状態になく別種のギャップとして申し送りのみ」
と既に指摘されていたcross-venture parityギャップであり、本フェーズでこれを解消する。
他venture同様の構成(他ventureとの前提の違い→基本方針→用途別文言一覧→発見した不整合→
残る課題)で新設する。

## 他ventureとの前提の違い

1. **LINE非依存のWeb+メール構成**(tech-stack.md参照)。他6ventureはいずれもLINE公式
   アカウント(LIFF)が入力・出力チャネルだが、本ventureはWebフォーム単体で入力を受け、
   生成結果もWeb画面に表示する。運用メッセージ(アクセスURL再送等)はメールで送る設計
   (access-url-resend-api-design.md参照、実際のメール送信自体は実装前・オーナー承認待ち)。
   LINE公式アカウントのトークルームという「宛先」が存在しないため、他venture
   (course-set-pasha等)が区別する「LINE公式アカウントで受け取る運用メッセージ」という
   カテゴリは本ventureには存在しない。
2. **単一の読み手**。他6ventureは「事業主(セッター等の契約者)が受け取った文面を、別の
   最終読者(顧客・会員)へ転載・転送する」という2段階の宛先構造を持つ(course-set-pasha
   tone-and-manner-guideline.mdの宛先3分類が典型)。本ventureはB2Cであり、入力した
   ファン本人がそのまま4出力(遠征プラン下書き・タイムテーブル草案・費用見積り・ハシゴ
   無理チェック)の読み手になる。README.md「他ventureとの構成上の違い(初期仮説)」で
   既に指摘されていた顧客層の違いが、トーン設計にも「転載用の宣伝的文面」対「本人が直接
   読む事務的な下書き情報」という違いとして表れる。
3. **出力形式が構造化JSON(自由文は一部フィールドのみ)**。llm-quality-verification-plan.md
   「他ventureとの差分」節で既に指摘されているとおり、他venture(course-set-pasha・
   aircon-pasha等)の出力は自由文の3点セットだが、本ventureはschema/output.schema.jsonの
   `status`分岐+構造化フィールド(`itinerary_draft`・`day_timetable`・`cost_estimate`・
   `hashigo_check`)であり、自由文はその中の`note`・`missing_fields_request`・
   `out_of_scope_message`等の一部フィールドに限られる。

## 基本方針

1. **全出力フィールドでですます調・絵文字不使用を既定とする**
   llm-system-prompt-draft.mdの4出力(遠征プラン下書き・タイムテーブル草案・費用見積り・
   ハシゴ無理チェック)は、course-set-pasha/aircon-pashaのSNS投稿文のような宣伝・拡散
   目的の文面ではなく、本人が直接読む事務的な下書き情報(交通手段の当たり・時刻・金額・
   移動リスク)である。そのため、他venture(course-set-pasha厳守事項9等)がSNS投稿文のみに
   許容している絵文字1〜2個の例外は本ventureには存在せず、4出力・`out_of_scope_message`・
   `missing_fields_request`のいずれも絵文字不使用で統一する。landing-page-copy-draft.md
   (フェーズ30・45)のLPコピー本文・FAQも、確認した範囲で絵文字を使用せずですます調で
   統一されており、この既定方針と矛盾しない。
2. **断定しない表現を徹底する(既存設計から収集・再確認)**
   以下はいずれも既存の設計文書で個別に定められていた「断定しない」ルールだが、本venture
   として一箇所に明文化されたことがなかったため、ここに集約する。
   - 厳守事項1: 実際の交通機関・宿泊施設の予約・決済を代行しない旨を明示し、「予約します」
     「手配します」等の断定的な表現を避ける(landing-page-copy-draft.mdファーストビュー
     節でも同じ理由で「下書きします」の語を採用)。
   - 厳守事項2: `venue_matched: false`の場合、具体的な最寄り駅・徒歩目安を推測で補わず、
     一般的な調べ方の案内に留める(venue-name-normalization-design.md・FAQ「入力した
     会場名の表記が正式名称と違う場合」も同じ留保方針)。
   - 厳守事項4: ハシゴ移動チェックは会場間の一般的な移動時間の目安に基づく参考情報である
     旨を明示し、実際の乗換検索・交通状況の確認は行わない。
   - venue-operational-status-output-reflection-design.mdの会場休館・稼働停止注記、
     FAQ「会場が休館中・稼働していない場合」も、全会場の最新状況を保証しない留保文言で
     統一されている。
   このように「断定しない」方針は既に各設計文書に散在して実装されていたが、本フェーズで
   横断的に確認した結果、方針間の矛盾は見つからなかった(是正の必要なし)。
3. **メール文面は実装前だが、将来も本ガイドラインの方針(ですます調・絵文字不使用・
   断定しない)を既定とする**
   access-url-resend-api-design.md「実際のメール送信はここでは行わない」(他venture共通の
   運用方針「メール連携接続後、送信直前に毎回オーナー確認」)のとおり、メール文面自体は
   未着手である。本ガイドラインは、将来メール文面を新規作成する際にWeb出力・LPコピーと
   同じ基本方針1・2を踏襲する既定ルールとして示すに留め、現時点で架空の文面を新設する
   ものではない。

## 用途別文言一覧(既存文言の集約・確認)

| 用途 | 宛先 | 既存文言の出典 | 絵文字 | 断定しない表現 |
|---|---|---|---|---|
| 遠征プラン下書き(出力1) | ファン本人(直接) | llm-system-prompt-draft.md厳守事項1 | 不使用 | 「当たり」止まり、予約代行なし |
| 当日タイムテーブル草案(出力2) | ファン本人(直接) | llm-system-prompt-draft.md厳守事項4a | 不使用 | グッズ列目安は一般論止まり |
| 費用見積り(出力3) | ファン本人(直接) | llm-system-prompt-draft.md厳守事項3・3a | 不使用 | 概算である旨を`note`に明記 |
| ハシゴ移動チェック(出力4) | ファン本人(直接) | llm-system-prompt-draft.md厳守事項4 | 不使用 | 参考情報である旨を明示 |
| 入力不足時の再送依頼 | ファン本人(直接) | llm-system-prompt-draft.md厳守事項5 | 不使用 | 推測で埋めない |
| 対象外案内 | ファン本人(直接) | llm-system-prompt-draft.md厳守事項6 | 不使用 | (該当なし) |
| LPコピー・FAQ | 見込み利用者(Web) | landing-page-copy-draft.md | 不使用 | 「下書きします」等、代行表現を回避 |
| アクセスURL再送メール | ファン本人(メール) | access-url-resend-api-design.md | 未着手 | 未着手(本方針を将来適用) |

## 発見した不整合・ギャップ

- llm-system-prompt-draft.mdの厳守事項1〜7には、他venture(course-set-pasha厳守事項9・
  aircon-pasha厳守事項9相当)のような文体・絵文字ルールの明文化が存在しなかった。これは
  実装(prototype側)に文言が無く検証できる自由文メッセージがほぼ無いこと(llm-quality-
  verification-plan.md「他ventureとの差分」節参照)と、本ガイドラインが未作成だったことの
  両方が重なって生じたギャップである。本フェーズでllm-system-prompt-draft.mdに厳守事項8
  (ですます調・絵文字不使用)を新設し、本ガイドラインと整合させた(実装コードへの影響なし、
  自由文メッセージがまだprototype側に存在しないため既存テストへの影響もない)。
- 絵文字使用の機械チェック(course-set-pasha・aircon-pasha・kura-pasha・forklift-pasha・
  event-komiguai-pashaが実装済みの`check_no_emoji_anywhere()`相当)は、本ventureの出力が
  構造化JSONで自由文メッセージの実装(prototype側のPython定数)がまだ存在しないため、
  適用対象となるコードが無い。将来、`out_of_scope_message`等の自由文を定数としてコード化
  する際に、他venture同様のpost_generation_checks.py相当の機械チェックを追加することを
  次回以降の検討課題とする(本フェーズでは新設しない)。

## 残る課題

- メール文面(アクセスURL再送・決済関連通知)の実際の文言草案は未作成。実装着手時に本
  ガイドラインの基本方針3を踏まえて新規作成する。
- 出力1〜4の自由文フィールド(`note`・`missing_fields_request`・`out_of_scope_message`等)
  に対するLLM生成結果が、実際にですます調・絵文字不使用を守るかどうかの実測検証は未実施
  (llm-quality-verification-plan.md「残る未確定事項」に記載の、実LLM呼び出しでの検証が
  必要な項目と合わせて次回以降に実施する)。
