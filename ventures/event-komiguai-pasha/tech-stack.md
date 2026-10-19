# 技術構成案(初回メモ、フェーズ7)

他venture(aircon-pasha・course-set-pasha・kura-pasha・line-reservation-ai)には既にあるが
本venture未着手だったtech-stack.md自体のcross-venture parityギャップに対応する初回メモ。
llm-api-cost-estimate.md(フェーズ6)で明らかになった本venture固有の特性(1主催者あたりの
利用頻度が月数件程度と他ventureより低く、かつ1イベント=1回の単発入力→4出力生成で完結し、
双方向の会話状態管理が不要)を踏まえた構成とする。

## 全体構成イメージ

主催者 → Webフォーム(単発入力) → Webhook/バックエンド → LLM(4出力生成) → 画面表示・
ダウンロード(生成結果をその場で返す、下書きをそのまま提示)

course-set-pasha・aircon-pasha・kura-pashaはLINE公式アカウントを入力チャネルとしているが、
本ventureはmvp-flow-draft.md(フェーズ2)が想定する入力が「イベント開催の都度の単発メモ」で
あり、フォロー/アンフォロー管理や月次の継続的な会話を要する他venture(美容室の予約・工房の
受注等、日常的に発生する業務)とは利用シーンが異なる。月数件程度の低頻度利用にLINE公式
アカウントの友だち登録・運用コストを課すメリットが薄いと判断し、本venture第一候補は
**シンプルなWebフォーム**(LINEアカウント登録不要、URLアクセスのみ)とする。既存
venture群とのLINE Messaging API運用一元化のメリットは失うが、低頻度利用者の導入障壁を
下げる方を優先する仮説として残す(pricing-plan.mdフェーズ4の単発利用プラン500円/回とも
整合する)。

## 想定コンポーネント

1. **Webフォーム(入力受付・結果表示)**
   - mvp-flow-draft.mdの5入力要素(`capacity`・`entry_exit_points`・`admission_type`・
     `staffing`・`outdoor_queue`)を入力するシンプルな単一ページフォーム。
   - LINEのfollow/unfollow相当の継続的な顧客管理は不要なため、課金前提のアカウント登録
     (メールアドレス+決済情報程度)のみを想定する。
   - 送信後、画面上に4出力(セルフチェックリスト・警備員重点配置案/誘導アナウンス文案・
     来場者向け掲示文案・ヒヤリハット記録フォーマット例)をその場で表示し、ダウンロード
     (PDF/テキスト)も可能にする。
2. **Webhook / バックエンド**
   - line-reservation-aiで選定済みのGCP Cloud Run functions(2nd gen、course-set-pasha/
     cloud-functions-generation-decision.mdの確定を踏襲)を第一候補として流用する。実際の
     GCPプロジェクト作成・請求先設定は着手時にオーナー承認が必要。
   - フォーム送信(HTTPSトリガー)→ schema/output.schema.jsonへの構造化出力生成 → レスポンス
     として4出力を返すだけの単方向バッチ処理で完結し、line-reservation-aiのような会話状態
     マシンは不要(mvp-flow-draft.mdの前提の通り)。
3. **LLM(4出力生成)**
   - llm-system-prompt-draft.md(フェーズ3)の厳守事項10件に沿い、schema/output.schema.json
     (フェーズ5)のstatus分岐(`generated`/`out_of_scope`/`insufficient_input`)で4出力を
     構造化出力形式で生成する。
   - llm-api-cost-estimate.md(フェーズ6)の試算により、最も保守的な組み合わせでもコストは
     従量単価の5%未満にとどまり、Sonnet 5.5で十分な品質が見込める。低頻度利用のため
     プロンプトキャッシュの効果は他venture以上に限定的である点は既存の課題認識を維持する。
4. **課金・利用回数のデータストア(Firestore)**
   - `organizer_account/{account_id}`: `stripe_customer_id`・`plan_id`・
     `subscription_status`・`trial_start_at`・`current_period_end`等。LINEのuser_idに
     相当する固定識別子がないため、メールアドレス+認証(マジックリンク等)を主キー候補とする。
   - `usage_counter/{account_id}`: 月間生成回数の積算(`month`・`count`)。他venture同様の
     構造を踏襲し、プラン間でカウンタ参照ロジックを分岐させない。
   - 単発利用プラン(500円/回、アカウント登録不要の想定)の扱いは未確定(アカウント登録なしの
     単発決済フローをStripe Checkoutの一回払いモードで実現する案を次回検討課題とする)。
5. **画像・添付の扱い**

   - 本ventureの入力は基本的にテキストメモのみを想定し、画像添付は現時点でスコープ外
     (他venture「添付の有無のみ判定」方式すら不要と判断)。

## MVPスコープ(最小構成)

- 入力は1フォーム送信=1イベント分(pricing-plan.mdの課金単位「1回=1イベント」に対応)。
- LINE公式アカウントは採用しない(本ventureの低頻度利用特性に合わせた構成)。
- 会話状態マシンは不要(他venture同様)。
- 課金・回数上限管理はaccount_id単位(アカウント登録方式は次回検討課題)。

## 初期投資・ランニングコストの目安

- 開発: 既存クラウドサービス・LLM APIの組み合わせのみで、専用インフラ購入は不要。
- ランニング: Webフォームホスティング(静的ホスティング無料枠程度)+LLM API従量課金+
  Firestore読み書き課金。LINE Messaging APIを使わないため他venture比でさらに固定費が
  小さくなる見込み(未検証の仮説)。

## 未検証・残課題

- アカウント登録なしの単発決済(500円/回プラン)の具体的な実装方式(Stripe Checkoutの
  one-time payment modeとFirestore上の利用回数カウントの紐付け方)は未検討。
- 継続課金プラン(ライト/スタンダード)利用時の認証方式(メールアドレス+マジックリンク等)
  の具体的な設計はcustomer-interview-design.md相当の検証とあわせて次回以降の課題とする。
- 実際のGCPプロジェクト作成・Stripeアカウント接続は、他ventureと同様にアカウント作成・
  支払いが発生するためオーナー承認待ちの範囲(pending-approval.md参照)。今回は技術構成の
  整理・cross-venture parityギャップの解消のみに留める。

最終更新: 2026-10-19 09:00 UTC(フェーズ7: tech-stack.md新規作成)
