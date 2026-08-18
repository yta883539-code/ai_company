# 申込フォーム提出フロー設計(user_profile.gym_area_pairsの書き込み側)

作成日: 2026-08-18(フェーズ76)

first-generation-notice-implementation-design.md 5節・
`ventures/course-set-pasha/prototype/cloud_function_webhook.py`の`GymAreaConfigStoreProtocol`は
「`user_profile/{user_id}.gym_area_pairs`の**読み取り**」のみを扱い、書き込み側(申込フォーム
提出フロー自体)は「本モジュールの対象外・別途の申込受付経路の課題」として明示的に残されていた
(フェーズ74・75のREADMEエントリ参照)。本ドキュメントはその書き込み側を設計する。

## 1. フォームツールの選定

- onboarding-guide.md 1.の通り、申込はLP経由の申込フォームで受け付ける前提が既にある。
  本ventureは無料トライアル+有料プランのSaaS型MVPであり、line-reservation-ai・
  aircon-pashaと同様に個人開発・初期投資ほぼ不要という分類理由を維持する必要がある。
- 候補比較:
  - **Googleフォーム + Google Apps Script(GAS)Webhook**: 無料、フォーム作成・GAS記述のみで
    始められ、追加のSaaS契約が不要。回答をGASのonFormSubmitトリガーで検知し、Cloud Functions
    のHTTPエンドポイントへPOSTする構成が可能。デメリットはUIのカスタマイズ性が低い(LPに
    埋め込む申込フォームとしてはブランド外観に難がある)。
  - **Typeform / Tally等の外部フォームSaaS**: UIは良いが有料プラン・アカウント作成が絡み、
    「初期投資ほぼ不要」の前提を崩しうる。account作成自体はpending-approval.md記載の
    承認待ち事項となる。
  - **LP自前のHTMLフォーム + Cloud Functions直接受信**: line-reservation-ai・aircon-pashaの
    LPワイヤーフレーム(landing-page-wireframe.md)は既にLP実装自体をオーナー承認待ちの
    範囲としている。フォームをLPに直接組み込む場合、フォームHTML自体はLP実装の一部として
    同じタイミングで着手でき、GASのような中間層を挟まない分Webhook処理がシンプルになる。
- **結論(暫定)**: MVPの初期段階はGoogleフォーム+GAS Webhookを第一候補とする(即座に無料で
  動かせ、アカウント作成はGoogleアカウント〈オーナーが既存で保有想定〉の範囲に留まり新規の
  有料契約を伴わない)。LP実装(オーナー承認待ち)着手時に、LP自前フォームへの切り替えを
  再検討する二段階移行とする。実際のGoogleフォーム作成・GAS配置(外部サービスへの設定作業)
  自体はpending-approval.mdの承認待ち事項として扱う(本ドキュメントは設計のみ)。

## 2. 受信データの形と正規化

- Googleフォーム側の項目は onboarding-settings-and-self-check-design.md 1.の通り、
  「ジム名・地域名(任意、複数可)」の自由記述欄1つ(カンマ区切りで複数組)。
- GAS Webhookからのペイロード想定(簡略化したJSON。実フィールド名はフォーム実装時に確定):

  ```json
  {
    "user_id": "U1234567890abcdef",
    "gym_area_pairs_raw": "クライミングジムA/○○区, ボルダリングジムB/△△市"
  }
  ```

  `user_id`はLINE公式アカウントの友だち追加時に発行されるIDを申込フォーム側にも
  事前入力させる想定(line-reservation-aiのfriend-add-user-id-linking-design.md相当の
  仕組みが本ventureにまだ無い場合は、フォーム内にLINE友だち追加時の案内文で手入力を
  依頼する形が暫定対応となる。this linking自体は別課題として残す)。
- 正規化ルール(`normalize_gym_area_pairs_raw()`として実装):
  - 前後の空白除去。
  - 空文字列・空白のみの入力はそのまま空文字列として保持(`is_configured()`はFalseを返す
    設計を維持)。
  - カンマ区切りの各要素についても前後の空白を除去した上で、カンマ区切りのまま1つの文字列
    として保持する(llm-system-prompt-draft.md厳守事項4がこの文字列をそのままLLM
    システムプロンプトへ渡す設計のため、構造化データへの分解はここでは行わない)。
  - 明らかに壊れた入力(例: 連続カンマのみ`,,,`で実質空)は正規化後に空文字列へ落とし込み、
    未設定として扱う(誤ったタグ付けより「タグ無し」の安全側を優先する既存方針を踏襲)。

## 3. 書き込み先

- `user_profile/{user_id}` ドキュメントの `gym_area_pairs` フィールドへ`set()`(新規作成
  または上書き)。既存の`GymAreaConfigStoreProtocol.is_configured(user_id)`はこの
  フィールドが非空かどうかで判定する。
- 複数回の申込フォーム再提出(ジム移籍・地域追加等での更新)は**全体を上書き**する仕様とする
  (追記ではない。ユーザーが最新の状態を都度フォームで再入力する運用を想定し、差分マージの
  複雑さを避ける)。

## 4. プロトタイプ実装方針

- 既存の`GymAreaConfigStoreProtocol`(読み取り専用)とは別に、本ドキュメントでは
  書き込み側を担う`UserProfileStoreProtocol`(`set_gym_area_pairs`/`get_gym_area_pairs`)を
  新設する。既存のcloud_function_webhook.py本体(生成フロー)とは責務が異なる別モジュール
  (`application_form_submission_flow.py`)とし、Webhook本体のインポート依存を増やさない。
- `InMemoryUserProfileStore`は`GymAreaConfigStoreProtocol`も同時に満たす(`is_configured()`は
  `get_gym_area_pairs()`が非空かどうかで判定)ことで、実Firestore接続後は単一の
  `FirestoreUserProfileStore`が両Protocolを満たす1つのドキュメントアクセスに統合できる
  設計とする(usage_counter/first_generation_notice_storeで同一インスタンス共有により
  原子性を担保したフェーズ75のパターンを踏襲)。
- 受信ペイロードの検証(`user_id`必須・型チェック)、正規化、書き込みまでを行う
  `handle_form_submission(payload, store) -> FormSubmissionResult`をエントリポイントとする。

## 残課題

- Googleフォーム自体の作成・GAS配置(外部サービスへの実設定)はオーナー承認待ち。
- LINE友だち追加時のuser_id事前紐付け経路が本venture未設計のため、フォーム側でのuser_id
  手入力運用の是非(誤入力リスク)は別途検討が必要。
- 実Firestore接続後、`FirestoreUserProfileStore`が`GymAreaConfigStoreProtocol`と
  `UserProfileStoreProtocol`の両方を満たす実装になることの最終確認。
