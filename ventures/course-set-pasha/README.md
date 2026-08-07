# コースセットパシャッと

個人経営のボルダリングジム・クライミングジムのオーナーやフリーランスのルートセッター向けに、
課題(ルート)入れ替え作業後の簡単なメモと写真を送るだけで、AIがSNS(Instagram/X)投稿文・
公式LINE/Web告知文・課題入れ替え履歴の記録下書きをまとめて生成するサービス。

## 概要

- 対象顧客: 個人経営・小規模運営のボルダリングジム・リードクライミングジムのオーナー、
  複数ジムを掛け持ちするフリーランスのルートセッター。
- 入力: 課題入れ替え後のメモ(エリア・テープ色・難易度帯・本数・ムーブの特徴・改訂日など)
  + 任意で課題エリアの写真。
- 出力: (1)SNS投稿文下書き、(2)公式LINE/Web告知文下書き、(3)課題入れ替え履歴の簡易記録。
- 実際のルートセット作業・安全確認・グレーディングの最終判断はセッター本人が行う前提とし、
  本サービスは告知文・記録の下書き作成支援のみを行う(会員管理・決済・予約受付は扱わない)。

## ステータス

- フェーズ1(2026-08-07 10:00 UTC): venture新規作成。ideas.mdの原案(2026-08-07 10:00 UTC)を
  ベースに、市場調査の一次整理(market-research.md)とMVPの入出力フォーマット草案
  (mvp-flow-draft.md)を作成した。
- フェーズ2(2026-08-07 11:00 UTC): mvp-flow-draft.mdの入出力フォーマットをもとに、
  LLM生成エンジンのシステムプロンプト草案(llm-system-prompt-draft.md)を作成した。
  「変更なし」エリアの誤記載防止、写真有無に応じた文面調整、会員管理・予約・決済への
  不応答ルールなど、mvp-flow-draft.md・README.mdの前提を厳守事項として明文化した。
- フェーズ3(2026-08-07 12:00 UTC): llm-system-prompt-draft.mdの「次回以降の検討事項」
  だった構造化出力(JSON化)を具体化し、schema/output.schema.jsonを作成した。
  status(generated/out_of_scope/insufficient_input)で厳守事項7・8の分岐を、
  sns_post.mentions_photoで厳守事項3の分岐結果を、unchanged_areasで厳守事項2の
  検証を、それぞれ機械的に確認できる形にした。
- フェーズ4(2026-08-07 13:00 UTC): 「次にやること」1点目だったボルダリングジムのSNS運用実態の
  WebSearch調査を実施(sns-tone-research.md)。投稿頻度「週2〜3回」の目安と、ハッシュタグは
  「一般タグ+ジム独自のブランドタグ+地域タグ」の組み合わせが定石という知見を得て、
  llm-system-prompt-draft.mdの厳守事項4(ハッシュタグ候補)に反映した。個人経営ジムに
  特化した投稿実例・作成時間の定量データは公開情報からは見つからず、引き続き未検証。

- フェーズ5(2026-08-07 14:00 UTC): 「次にやること」1点目だった料金プラン・無料トライアル条件を
  仮決めした(pricing-plan.md)。line-reservation-aiのpricing-plan.mdの設計方針を踏まえつつ、
  双方向会話・予約状態管理が不要な単方向バッチ処理という特性から「月間生成回数」ベースのシンプルな
  3プラン(ライト/スタンダード/セッター複数)を設計し、sns-tone-research.mdの「投稿頻度週2〜3回」を
  想定利用回数の目安として反映した。課金単位は「1メッセージ送信=1回」と暫定決定。
- フェーズ6(2026-08-07 15:00 UTC): 「次にやること」1点目だったschema/output.schema.jsonの
  allOf条件分岐(if/then)が実際のLLM構造化出力機能でそのまま利用可能かを机上検証した
  (schema-structured-output-compat-check.md新規作成)。Claude Platform Docsの公開情報を
  確認したところ、Claude APIのStructured Outputsは`if`/`then`/`else`・`oneOf`を非対応と
  判明。schema/output.schema.jsonからallOf/if-thenを撤去し、トップレベル全プロパティを
  常時`required`化(該当しない場合は`null`を許容)する設計に改訂した。`status`の値に応じた
  null/非nullの依存関係は、line-reservation-aiのvalidate_test_cases.pyと同様にスキーマ単体
  ではなくコード側検証で担保する方針とした。

- フェーズ7(2026-08-07 16:00 UTC): 「次にやること」1点目だった改訂後のschema/output.schema.json
  に対応する期待JSON出力サンプルを作成し(schema/validate_test_cases.py新規作成)、line-reservation-ai
  のvalidate_test_cases.pyと同じ設計の机上バリデータでstatus⇔null/非nullの依存関係違反が
  ないか検証した(status別5パターン、全件パス。output-samples-validation.md参照)。schema単体
  では表現しない依存関係(status=generatedならsns_post等が非null、等)をコード側検証で
  機械的にチェックできることを確認した。実LLMでの生成安定性・厳守事項遵守率の検証は
  引き続きオーナー承認後のAPI接続時の課題として残る。

## 次にやること(候補)

- 実在の個人経営ボルダリングジムの公式SNSアカウントの投稿例(公開情報)を数件観察し、
  出力1のトーン・粒度をチューニングする。
- pricing-plan.mdの価格帯・生成回数上限・課金単位の妥当性を想定顧客ヒアリングで検証する
  (未検証の仮説として記録済み)。
- 実LLM呼び出し・SNS API連携等、外部サービスとの実接続はオーナー承認が必要なため、
  設計・下書き作成の範囲に留める。
