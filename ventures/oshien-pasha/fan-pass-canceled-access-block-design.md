# 解約後のaccessTokenアクセス時のブロック分岐の詳細設計(フェーズ35)

monthly-pass-user-identification-design.md(フェーズ34)3節(2)の残課題
「解約(`subscription`のcanceled化)後は`accessToken`によるアクセス時に『生成機能』への
導線は閉じ、月額フリーパスへの再加入を促す簡易ページを表示する分岐を設ける」に対応する。

## 1. 参照元: aircon-pashaのsubscription-canceled-immediate-block-design.md

aircon-pashaフェーズ(subscription-canceled-immediate-block-design.md)は、個別タイムスタンプ
方式(`_is_generation_paused`/`_is_payment_suspended`)だけでは「決済失敗を一度も経験せずに
解約したユーザー」が無期限に生成を使い続けられてしまう欠落を発見し、`subscription_canceled_at`
という専用フィールドと`_is_subscription_canceled()`判定を追加し、他の判定よりも先に(最優先で)
チェックする設計を確立した。本ventureも同じ欠落パターンを未然に防ぐため、この設計をそのまま
踏襲する。

## 2. 判定ロジック

- `fan_pass`ドキュメント(内部ID: `internal_id`)に`subscriptionStatus`
  (`active`/`canceled`)フィールドを持つ(monthly-pass-identity-design.mdフェーズ7が既に
  想定していたフィールド)。
- 判定関数`_is_fan_pass_canceled(doc)`: `doc.subscriptionStatus == "canceled"`のときTrue。
- 本venture固有の追加判定: `accessToken`自体がどのドキュメントにも一致しない(誤入力・
  URL切れ)場合は本分岐の対象外とし、別のエラーページ(未登録アクセストークン用)で扱う
  (本フェーズの対象は「有効なaccessTokenだが解約済み」のケースに限定する)。

## 3. 本venture固有の差異: 「停止応答」ではなく「ページ表示内容」の分岐

aircon-pasha等の既存6ventureはLINE webhookでメッセージ受信時に判定し、該当時はLLM呼び出しを
行わず停止応答メッセージを返す設計である。本ventureはREADME.md・tech-stack.mdの方針どおり
Web単体(LINE非依存)・`/m/{accessToken}`形式のURLへのGETアクセスを起点とするため、
「メッセージ応答」ではなく「ページの表示内容」を切り替える設計とする。

- `subscriptionStatus == "active"`: 通常の入力フォーム(当選公演の会場・日時等を入力する
  画面)を表示する。
- `subscriptionStatus == "canceled"`: 入力フォームを表示せず、(a)解約済みである旨の案内文、
  (b)再加入用のStripe Checkout URLへの導線、のみを表示する専用ページを返す。
- 本ventureはdata-retention-policy.mdの方針により生成結果の履歴を保存しないため、
  aircon-pasha等で論点になりうる「過去の生成結果へのアクセス継続を許すか」という問題は
  発生しない(表示するコンテンツが無いため)。

## 4. 再加入時の扱い: 同一accessTokenの再利用

monthly-pass-identity-design.md(フェーズ7)が確立した「解約後に再契約した利用者が同じ
アクセスURLを使い続けられる」方針をそのまま適用する。

- Stripe `customer.subscription.deleted`受信時: 該当`fan_pass`ドキュメントの
  `subscriptionStatus`を`canceled`に更新する(`accessToken`自体は失効させない)。
- Stripe `customer.subscription.created`受信時(再加入): 同一`accessToken`を保持した
  まま`subscriptionStatus`を`active`に戻す(aircon-pashaの`customer.subscription.created`
  分岐での`subscription_canceled_at`クリアと同型)。
- 再加入の経路は「解約済み案内ページ」内のStripe Checkout URL経由を基本とし、Checkout時に
  既存の`accessToken`と紐づくStripe顧客IDを引き継ぐ想定とする(具体的な紐づけ方法は
  firestore-data-model.md相当の文書作成時に詳細化、本フェーズでは対象外)。

## 5. フィールド名の揺れに関する指摘

本venture内の既存ドキュメントでコレクション名の表記が揺れている。

- フェーズ7(monthly-pass-identity-design.md)・フェーズ8(generation-count-design.md)は
  `monthly_pass/{internal_id}`と表記。
- フェーズ34(monthly-pass-user-identification-design.md)の次回候補(2)は
  `fan_pass/{internal_id}`と表記。

本フェーズの判定ロジック・ページ分岐設計自体はコレクション名のどちらでも影響を受けないため
`fan_pass`の表記で記述したが、次回候補(2)でfirestore-data-model.md相当の文書を新規作成する際に
名称を一つに確定させ、既存2文書(フェーズ7・8)側も必要に応じて表記を揃える統一作業が必要である。

## 6. テスト観点(次の実装フェーズ向けメモ、本venture未着手のprototypeコード向け)

- `subscriptionStatus == "active"`: 通常フォーム表示(素通り)。
- `subscriptionStatus == "canceled"`: 解約済み案内ページ表示、入力フォームは表示しない。
- 再加入後(`active`復帰): 同一`accessToken`で通常フォーム表示に戻る。
- `accessToken`が未登録: 本分岐とは別の「未登録アクセストークン」エラーページ。
- `fan_pass`ドキュメント自体が存在しない(Firestore未接続等の異常系): 安全側で解約済み
  相当の案内(生成機能を誤って開放しない)を返す方針とする(aircon-pashaの
  profile_store未接続時「安全側False」と方向性を揃えるが、本venture側は「安全側で閉じる」
  ことがaircon-pashaの「安全側で通す」とは逆になる点に注意。これは判定対象がそもそも
  「生成を許可する根拠となるドキュメント」であり、ドキュメントが無いことは根拠が無いことを
  意味するため)。

## 7. 残課題

- `fan_pass/{internal_id}`(名称は5節の指摘どおり次回確定)コレクション定義の新規作成
  (`accessToken`・`stripeCustomerId`・`subscriptionStatus`・`currentPeriodEnd`等、
  firestore-data-model.md相当)。
- 生成回数カウンタ設計(tech-stack.mdコンポーネント7、識別方法確定〈フェーズ34〉により
  着手可能)。
- venue-master-draft.mdの各会場アクセス情報精査・会場名表記揺れの名寄せ方法の検討
  (README.md既出の残課題、未着手のまま持ち越し)。
- 複数デバイス利用の案内文・本フェーズの解約済み案内文のlegal-notices-draft.md・
  landing-page-copy-draft.mdへの反映(フェーズ34次回候補(1)相当分も含む)。
- 承認待ち事項がオーナーから承認された場合はその着手を最優先。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のGCPプロジェクト・Firestore
データベース・Stripeアカウントの開設自体はオーナー承認が必要なアクションに該当するため、
本メモは設計の検討に留める(コード実装・外部サービスへの接続は一切行っていない)。
