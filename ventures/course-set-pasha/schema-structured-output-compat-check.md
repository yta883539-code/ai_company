# 構造化出力スキーマの実API互換性 机上検証(2026-08-07 15:00 UTC)

## 位置づけ

llm-system-prompt-draft.mdの「次の課題」2点目
「schema/output.schema.jsonのallOf条件分岐(if/then)が実際のLLM構造化出力機能で
そのまま利用可能かの確認」に対応。line-reservation-aiのschema-validation-report.mdと
同じく、実LLM呼び出し(APIキー・課金、オーナー承認待ち)を行わずに実施できる範囲の
机上検証として、公開ドキュメント(WebSearch/WebFetch)でClaude API・OpenAI APIの
構造化出力機能が対応するJSON Schemaのサブセットを確認した。

## 確認結果

### Claude API(Structured Outputs、2026年時点)

Claude Platform Docs(structured-outputs)によれば、対応する条件分岐・合成キーワードは
以下の通り:

- `anyOf`: 対応(制限あり)
- `allOf`: 対応(制限あり。`allOf`内での`$ref`使用は非対応)
- `oneOf`: **非対応**
- `if` / `then` / `else`: **非対応**

その他の非対応機能: 再帰スキーマ、enum内の複雑な型、外部`$ref`、数値制約
(`minimum`/`maximum`/`multipleOf`)、文字列長制約(`minLength`/`maxLength`)、
`minItems`が0または1を超える配列制約、`additionalProperties`を`false`以外に
設定すること。

### OpenAI API(Structured Outputs strict mode、参考)

同様にJSON Schemaのサブセットのみ対応。`anyOf`/`oneOf`/`allOf`/`prefixItems`/`$ref`を
用いたスキーマ合成・条件分岐、および`pattern`(正規表現)は非対応。strict modeでは
全プロパティを`required`に列挙する必要がある(オプショナル項目は`null`許容型で表現)。

## 本ventureのスキーマへの影響

`schema/output.schema.json`(2026-08-07 12:00 UTC作成)は、`status`の値に応じて
`sns_post`/`line_web_notice`/`history_row`等の必須化を切り替えるために
`allOf`+`if`/`then`を使用していた。上記の通り**Claude APIのStructured Outputsでは
`if`/`then`は非対応**のため、このままでは実API投入時にスキーマとして受理されない、
または`strict`検証が効かない可能性が高いと判断した。

## 対応方針

line-reservation-aiのbooking_output.schema.json(faq_segments依存関係)と同じ考え方を
踏襲する。すなわち、

- スキーマ自体では「`status=generated`のとき3出力が必須」のような**条件付き必須**を
  表現せず、代わりに**全プロパティを常に`required`に列挙し、該当しない場合は`null`を
  許容する**設計に変更する(Claude/OpenAI双方のstrict modeで対応可能な書き方)。
- 「`status`の値に応じてどのフィールドが`null`であるべきか」というクロスフィールドの
  依存関係は、システムプロンプトの厳守事項として明記した上で、line-reservation-aiの
  `validate_test_cases.py`と同様に、実装時にコード側の検証ロジックとして機械的に
  チェックする(スキーマ単体では表現しない)。

この方針に沿ってschema/output.schema.jsonを改訂した(allOf/if-then撤去、
トップレベル全プロパティをrequired化、該当しない場合はnull)。

## 残る未検証事項

- 上記はあくまで公開ドキュメントに基づく机上確認であり、実際にClaude APIへこの
  改訂後のスキーマを投入した動作確認は未実施(APIキー取得・課金がオーナー承認待ちのため)。
- line-reservation-aiのbooking_output.schema.jsonも同様に`allOf`を使用しているが、
  中身が`if`/`then`ではなく説明用のプレースホルダー(コード側検証の言及のみ)のため、
  今回の非対応事項には抵触しないことを確認済み(実質的な変更は不要)。

## 参照

- Claude Platform Docs: Structured outputs
  (https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- OpenAI: Introducing Structured Outputs in the API
  (https://openai.com/index/introducing-structured-outputs-in-the-api/)
