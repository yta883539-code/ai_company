# 主催者向け申込フォーム(submit_event_form)のUI草案(フェーズ126)

mvp-flow-draft.md「capacity入力時のヘルプテキスト方針」(フェーズ125)の次回候補6
「web-form-ui-design.md相当の主催者向け入力画面の実UI設計(フィールド配置・文言の確定)に
反映する」に対応する。問い合わせフォーム側はinquiry-form-ui-draft.md(フェーズ52)で
既に画面構成を具体化済みだが、主催者が最初にチェックリスト生成を申し込む本体フォーム
(`submit_event_form`が受け取る5項目)の画面構成はこれまで未作成だったため、本文書で
新規に具体化する。机上設計であり実際のフォーム実装・操作感検証は未着手。

## 1. 前提の整理

- 送信先はsubmit-event-form-http-entry-point-design.md(フェーズ113)が定義する
  `submit_event_form`。リクエスト本文は`capacity`・`entry_exit_points`・
  `admission_type`・`staffing`・`outdoor_queue`(任意で`idempotency_key`)。
- `capacity`・`entry_exit_points`は必須項目(output-samples-validation.md
  `II1_missing_capacity_and_entry_exit`、両方欠落時は`insufficient_input`応答で
  再入力を促す)。`admission_type`・`staffing`・`outdoor_queue`は未入力でも
  `insufficient_input`にはならず、mvp-flow-draft.mdが定める既定の取り扱い
  (`outdoor_queue`未入力時は「屋外に及ぶ可能性あり」側の注記を必ず付す等)に従う。
- web-form-ui-design.md(フェーズ65)が定めた3関数共通の再試行導線・
  `idempotency_key`方式をそのまま踏襲する(本フォームは`submit_event_form`に該当)。

## 2. 入力画面の構成

1. **`capacity`(会場キャパシティ、必須・数値入力)**: ラベル「会場キャパシティ(人)」。
   入力欄の直下に、mvp-flow-draft.mdフェーズ125の方針に沿ったヘルプテキストを常設する:
   「会場情報サイト等の『〜500人』のような規模帯の見出し表記は実際の収容人数では
   ないことがあります。会場の座席表・公式サイト等に記載の具体的な人数を入力して
   ください」。プレースホルダは具体例を示す「例: 300」とする(規模帯表記の転記を
   誘発しないよう、プレースホルダ自体にも「〜500人」のような見出し的な表記は使わない)。
2. **`entry_exit_points`(入場口・退場口の数、必須)**: 入場口数・退場口数をそれぞれ
   数値入力させた上で「入退場共用」チェックボックスを設け、チェック時は退場口欄を
   入力不要にする(mvp-flow-draft.mdの入力例「入場口1箇所(入退場共用)」に対応)。
3. **`admission_type`(任意、ボタン選択)**: 「自由入場」「指定席」「事前予約制
   (先着/抽選)」の3択ボタン(mvp-flow-draft.mdフェーズ21で追加した3値)。未選択
   のまま送信可能とする(必須項目ではないため)。
4. **`staffing`(任意、数値入力2欄)**: 「自社スタッフ数」「外部委託警備員数」を
   それぞれ数値入力(0可)。
5. **`outdoor_queue`(任意、3択ボタン)**: 「屋内に収まる」「屋外・公道に及ぶ可能性
   あり」「わからない」の3択。未選択のまま送信した場合、mvp-flow-draft.mdの既定
   方針により「屋外に及ぶ可能性あり」側と同じ注記付き出力になる旨を、選択欄の下に
   小さく注記する(「未選択の場合は安全側〈屋外に及ぶ可能性あり〉として出力します」)。
6. 送信ボタンは1つのみ。`capacity`・`entry_exit_points`の必須2項目が入力されて
   いれば送信可能とする(他3項目は未入力でも送信を妨げない)。

## 3. 送信後・エラー時の表示

- web-form-ui-design.md(フェーズ65)の方針どおり、`submit_event_form`はStripe
  Checkout Session発行までの2段階処理を内部で行うため、送信ボタン押下時に
  クライアント側で`idempotency_key`(UUID4)を発行し送信する。失敗時は「送信に
  失敗しました。もう一度送信しますか?」の確認付き再送ボタンを表示する(無確認の
  即時再送は行わない)。
- `outcome="insufficient_input"`応答を受けた場合は、送信済みの入力値を保持した
  まま同一画面上に不足項目を強調表示し、再送信を求める(ページ遷移・入力の
  やり直しはさせない)。
- `outcome="checkout_session_created"`時は、応答に含まれる`checkout_url`へ
  即座にリダイレクトする(本画面に確認表示は設けない)。

## 4. 未検証・残課題

- 実際のフォームHTML実装・Cloud Runルーティングへの追加自体は、他の実装作業と
  同様に実GCPプロジェクト作成後に着手する(pending-approval.md参照、承認待ち)。
  今回は画面構成・ヘルプテキスト文言の確定のみに留める。
- `admission_type`「事前予約制」選択時に予約枠の時刻情報まで追加入力させるかは
  未検討(現状のスキーマが時刻情報を持たないため、本フェーズでは追加入力欄を
  設けない判断とした)。次回検討課題とする。
- `staffing`の2欄が両方0で送信された場合の警告表示有無(入力ミスの可能性)は
  次回検討課題とする。

次回候補: (1)承認待ち事項(launch-readiness-checklist.md記載の1〜3)がオーナーから
承認された場合はその着手を最優先、(2)上記「事前予約制」の予約枠時刻情報の扱い、
`staffing`両方0入力時の警告表示有無の検討、(3)他venture・アイデア領域の前進。

最終更新: 2026-11-16 23:57 UTC(フェーズ126: mvp-flow-draft.mdフェーズ125の次回候補6に
対応し、主催者向け申込フォーム(submit_event_form)のUI草案を新規作成。capacity欄の
ヘルプテキスト文言・プレースホルダを確定し、他4項目(entry_exit_points・
admission_type・staffing・outdoor_queue)の画面構成も合わせて具体化した。コード変更
なし、既存テスト184件・schema検証22件いずれも変更なしでパス(回帰なし)。実GCP/Stripe
接続・支払い・アカウント作成・外部公開・送信は一切行っていない。承認が必要なアクションは
今回発生していないためpending-approval.mdへの追記なし)
