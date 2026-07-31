# 複合FAQ質問における構造化出力(JSON)スキーマ拡張案(2026-07-31時点)

conversation-samples-test-cases.md の E13(複合質問の分割送信)で見つかった課題、
「1回のAI応答内で `intent` が項目ごとに混在しうる(例: 駐車場は`faq`で回答済み、
電子マネーは`escalation`)点を、json-output-retry-fallback.md が前提としてきた
「1応答=1 JSON」の構造とどう整合させるか」について設計する。
机上設計のみ、実装・実LLM検証は未着手。

## 方針: トップレベルの1 JSONは維持し、任意フィールドで内訳を表現する

「1応答=1 JSON」自体は崩さない。理由:
- json-output-retry-fallback.md のリトライ・フォールバック方針(パース失敗時の
  再生成1回、それでも失敗なら`needs_owner_check: true`一律扱い)は
  「JSONが1個である」ことを前提に設計済みで、これを崩すとリトライ対象の
  特定(どの項目が壊れたか)が複雑化し、フォールバックの安全側判定
  (壊れたら即エスカレーション)という単純さが失われる。
- E13で混在するのはあくまで「FAQ項目ごとの回答可否」であり、予約系の
  intent(new_booking/cancel/change)とは同時発生しない
  (faq-escalation-boundary.mdの整理上、予約相談中に複合FAQが混ざるケースは
  現状スコープ外)。したがって混在は実質「faq内でのみ起きる」局所的な問題であり、
  トップレベルのintent種類自体を配列化する必要はない。

## スキーマ拡張案

既存スキーマ(llm-system-prompt-draft.md記載)に、任意(optional)の
`faq_segments` 配列を追加する。予約系のやり取り(new_booking/cancel/change)や
単一項目のFAQ(E10等)では `faq_segments` は付与しない(null)。

```
{
  intent: "new_booking" | "cancel" | "change" | "faq" | "escalation",
  name: string | null,
  menu: string | null,
  datetime_candidate: string | null,
  confirmed: boolean,
  needs_owner_check: boolean,
  faq_segments: [
    { topic: "access" | "parking" | "payment" | "hours" | "other", resolved: boolean }
  ] | null
}
```

- `intent` はトップレベルでは従来通り単一値。複合FAQのケースは
  `intent: "faq"` を維持する(E13aは全項目回答可のため`faq`のまま、
  E13bも「主たる応答種別」としては`faq`のまま。個々の項目のescalation有無は
  `faq_segments[].resolved`で表現する)。
- `faq_segments[].resolved: false` の項目が1つでもあれば、
  トップレベルの `needs_owner_check` は true とする
  (E13bのように一部項目が未登録・未チェックの場合、全体としては
  オーナー確認が必要という既存ルールをそのまま踏襲)。
- `faq_segments[].resolved: true` のみで構成される場合(E13a相当)は
  `needs_owner_check: false` のまま。
- `confirmed` はFAQ系では常にfalseのため、この拡張による影響を受けない。
- 単一項目FAQ(E10〜E12)は `faq_segments` を付与してもしなくても良いが、
  実装を単純化するため「複合質問(2項目以上)のときのみ付与、単一項目では省略」を
  推奨する(単一項目まで配列化すると自然文の分割送信ロジックと二重管理になるため)。

## リトライ・フォールバックへの影響(json-output-retry-fallback.md整合)

- スキーマ不一致の判定対象に `faq_segments` を追加する。
  `faq_segments` が存在するのに配列でない/各要素に`topic`または`resolved`が
  欠けている場合は、既存の「2. キー不足/余分」と同種の不正として扱い、
  同じリトライ(1回まで)→フォールバック(`needs_owner_check: true`一律、
  `confirmed: false`)の経路に乗せる。新しいフォールバック分岐は不要。
- `faq_segments` 内の `resolved: false` から導かれる `needs_owner_check: true` は
  「オーナーへの通知」トリガーとしては no-show-handling.md の通知経路と同じだが、
  通知文面には「複合質問のうちどの項目が未回答か(topic)」を含めることを
  次のステップとして検討する(現状の通知文面は単一escalationケースを想定した文面のため、
  複合質問向けの追記が必要)。

## 未検証・要検討事項
- `topic` の列挙値(access/parking/payment/hours/other)が
  owner-settings-wireframe.mdの「店舗FAQ情報」入力欄の項目名と過不足なく対応しているか、
  項目追加時(将来的な入力欄拡張)にどう同期させるかは未検討。
- 3項目以上にまたがる複合質問(現状のテストケースは2項目まで)でも
  同じ配列方式で破綻しないか、実LLM検証時に確認が必要。
- 実際のLLMがこの拡張スキーマを安定して出力できるか(項目数が可変の配列を
  安定生成できるか)は、単一固定キーのみの現行スキーマより不確実性が高い可能性があり、
  実装フェーズでのプロンプトチューニング・few-shot例の追加が必要になる見込み。

## 次のステップ候補
- この拡張案をllm-system-prompt-draft.mdの出力形式セクションに反映し、
  E13の想定JSON出力例(13a/13b)を具体化する
- 複合質問向けのオーナー通知文面(no-show-handling.mdの通知設計への追記)を検討する
