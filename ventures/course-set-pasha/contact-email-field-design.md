# 連絡先メールアドレス(`user_profile.email`)フィールド設計(フェーズ139)

作成日: 2026-09-01

## 発見した記載漏れ・実装の空白

data-retention-policy.md「今後の課題」・legal-notices-draft.md 2.4節はいずれも、削除候補化後の
オーナーへの最終確認の代替経路(LINE pushが送達不可の場合)として「申込フォームで収集した
連絡先メールアドレス」を挙げつつ、「実際の収集項目は`application-form-submission-flow-design.md`
側の実装確定後に確認する」として先送りしていた。

一方、onboarding-guide.md 1.は申込フォームの入力項目として当初から
「ジム名(または屋号)・運営形態(任意)・**連絡先メールアドレス**」の3点を明記していた。
実際に`application-form-submission-flow-design.md`・`prototype/application_form_submission_flow.py`
を確認したところ、想定ペイロード(design 2節)・`UserProfileStoreProtocol`・
`InMemoryUserProfileStore`のいずれにも`email`に相当するフィールドが一切存在せず、
`gym_area_pairs`(ジム名・地域名)のみが実装されていた。つまり「実装確定を待つ」という
先送りの前提自体が誤りで、実際には**メールアドレスの収集・保存経路自体が未設計のまま
放置されていた**というギャップだった(follow-unfollow-event-handling-design.mdの
「本来設計すべきだったが一度も設計されていなかった」系の記載漏れと同種)。

## 決定

- `user_profile/{user_id}`に`email`フィールドを追加する。onboarding-guide.mdが既に
  「連絡先メールアドレス」を運営形態(任意)とは別に必須項目相当として列挙していたことを
  踏まえ、`gym_area_pairs_raw`(任意・欠落時は空文字列扱い)とは異なり**必須項目**として
  扱う。
- 書き込みは`gym_area_pairs`と同じタイミング(申込フォーム提出時、`handle_form_submission()`)
  で行う。将来メールアドレスのみを別途変更するUIができるまでは、フォーム再提出のたびに
  最新の入力で上書きする(`gym_area_pairs`と同じ全体上書き方針)。
- 値の形式チェック(`@`を含むか等)はMVPでは行わない。本ventureの既存の入力検証方針
  (型チェックのみで内容の妥当性検証は最小限に留める、`gym_area_pairs_raw`の正規化と同じ
  考え方)を踏襲し、非空文字列であることのみを確認する。誤入力時の実害は「削除候補化後の
  最終確認が届かない」程度であり、連絡不能ケースの扱い(オーナーが個別判断)で吸収できる。

## 実装

- `application_form_submission_flow.py`:
  - `UserProfileStoreProtocol`に`set_email`/`get_email`を追加。
  - `InMemoryUserProfileStore`に`_emails: dict[str, str]`を追加し、同メソッドを実装。
  - `FormSubmissionResult`に`email: Optional[str]`を追加。
  - `handle_form_submission()`で`email`をuser_idと同様に必須検証(非空文字列でなければ
    `ok=False`、書き込みは行わない)し、`store.set_email()`へ書き込む。
- `user_id_linking.py`の`handle_form_submission_with_linking_code()`(連携コード経由の
  実際のエントリポイント)が組み立てる`inner_payload`に`email`を追加し、呼び出し元の
  ペイロードから素通しするよう配線した(この配線漏れがあると、実際のGoogleフォーム経由の
  提出ではメールアドレスが一切保存されない状態になっていた)。
- テスト10件追加(`InMemoryUserProfileStore`のemail get/set/上書き3件、
  `handle_form_submission()`側の正常系・欠落・空白・非文字列の4件、
  `handle_form_submission_with_linking_code()`側の正常系上書き確認1件・email欠落時の
  未書き込み確認1件、既存の正常系テストへのemail追加1件)、venture全体438件全件パス・
  schema検証9件パスを確認した。

## 波及: data-retention-policy.md・legal-notices-draft.mdの記載更新

両文書とも「収集項目は実装確定後に確認する」としていた記述を、本フェーズで`email`
フィールドとして実装確定したことを踏まえて更新した(該当箇所は各文書の「今後の課題」
参照)。

## 今後の課題

- 実際のGoogleフォーム作成・GAS Webhook配置(外部サービスへの実設定)はオーナー承認待ちの
  ままであり、実運用でこの`email`フィールドに実データが入るのはフォーム作成後になる。
- メールアドレスの形式検証(誤入力防止)を将来追加するかは、実運用開始後の誤入力発生率を
  見てから判断する(現時点では過剰な検証を避ける)。
- `gym_area_pairs`同様、実Firestore接続後は`FirestoreUserProfileStore`が`email`も含めた
  単一ドキュメントアクセスとして実装できる想定(application-form-submission-flow-design.md
  4節の既存方針と同じ)。
