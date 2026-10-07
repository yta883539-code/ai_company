# アクセストークン(operator_id)漏洩時の再発行・メールアドレス変更時の旧トークン失効設計

作成日: 2026-10-07 01:00 UTC(フェーズ96)

payment-identity-verification-design.md(フェーズ95)「4. 残課題」に残っていた以下の
2点に着手する。

- アクセストークン(`operator_id`)が漏洩した場合の再発行機能は未設計。
- メールアドレス変更時の再送・旧トークン失効の扱いは未設計。

## 1. 前提の見直し: ドキュメントIDとアクセストークンの分離が必要

payment-identity-verification-design.md(フェーズ95)は`fleet_operator/{operator_id}`、
すなわち**FirestoreのドキュメントID自体をアクセストークンとして使う**設計だった。この
前提のまま「漏洩時に`operator_id`を再発行する」を素朴に実装すると、ドキュメントIDの
変更(Firestoreではドキュメントの`rename`は存在せず、新ドキュメントへのコピー+旧
ドキュメント削除でしか実現できない)が必要になり、次の問題が生じる。

- `stripeCustomerId`・`subscriptionStatus`・`trialStartAt`・`currentPeriodEnd`(すべて
  firestore-data-model.mdの既存フィールド)を新ドキュメントへ漏れなくコピーする処理が
  再発行のたびに必要になり、コピー漏れ・コピー中の二重書き込み競合のリスクが生じる。
- 旧ドキュメント削除とStripe側`client_reference_id`(=旧operator_id)の対応関係が
  過去のCheckout Session履行(`checkout.session.completed`、一度きりのイベント)以降は
  使われないため実害は小さいが、将来Stripe Customer Portal等で`client_reference_id`を
  再度参照する機能を追加した場合に不整合の芽になる。

この構造的な問題を避けるため、本フェーズで**ドキュメントIDとユーザーに配布するアクセス
トークンを分離する**設計変更を行う。

### 変更後の構造

- ドキュメントID: Firestoreの自動生成ID(`internal_id`と呼ぶ)。不変。Stripeとの紐付け
  (`client_reference_id`)にはこちらを使う(自動生成IDも十分ランダムで推測不能なため、
  payment-identity-verification-design.mdが要求する「推測不能な識別子」の性質を保つ)。
- `fleet_operator/{internal_id}`内に`accessToken`フィールド(現在有効なアクセストークン、
  値自体は従来の`operator_id`と同じ生成方法=サーバー側ランダム発行)を追加。アクセスURLは
  `https://<ドメイン>/f/{accessToken}`形式に変更する(URLの見た目は変わらない。パスパラ
  メータの意味が「ドキュメントID」から「現在有効なトークン」に変わるだけ)。
- アクセスURL受信時のドキュメント特定は、`accessToken`フィールドへの単一フィールド
  クエリ(Firestoreは単一フィールドに自動でインデックスを作成するため追加設定不要)で
  行う。

この分離により、再発行は「同一ドキュメントの`accessToken`フィールドを書き換えるだけ」の
単純な更新操作になり、他フィールドのコピーや旧ドキュメント削除が不要になる。

## 2. 再発行フローの設計

漏洩時の再発行とメールアドレス変更時の再発行は、いずれも「現在のトークンを失効させ、
新トークンを発行して新しい宛先(同じ、または変更後のメールアドレス)に送る」という同じ
操作であるため、**1つの再発行フローに統一する**(course-set-pasha等の既存シリーズが
採用する「機能を増やさずシンプルに保つ」方針を踏襲)。

1. アクセスURL(現在有効な`accessToken`)経由でアクセスできる設定ページに「アクセスURLを
   再発行する」ボタンを置く(メールアドレス変更時は、変更フォームの送信操作自体が同じ
   再発行処理を内部的に呼ぶ)。
2. サーバー側で新しい`accessToken`をランダム発行し、該当`fleet_operator/{internal_id}`の
   `accessToken`フィールドを新トークンで上書きする(旧トークンの値はどこにも保持しない。
   漏洩対策の観点では「旧トークンが即時に使えなくなること」自体が目的であり、失効ログの
   保持は不要と判断)。
3. 新しいアクセスURL(`https://<ドメイン>/f/{新accessToken}`)を、送信先メールアドレス
   (通常ケースでは`fleet_operator.email`、メールアドレス変更ケースでは変更後の新アドレス)
   宛に送信する。この送信自体は既存のメール送信運用方針(メール連携接続後、送信直前の
   毎回オーナー確認を経てのみ送信。pending-approval.md記載の既存事例と同型)に従う。
4. 旧`accessToken`での以降のアクセスは、クエリでドキュメントが見つからない状態になるため
   自然に失効する(明示的な無効化リストの管理は不要)。

### メールアドレス変更時の到達性確認

payment-identity-verification-design.md(フェーズ95)「3. 到達性確認の設計判断」は初回
登録時にダブルオプトインを設けない方針を既に確定している。メールアドレス変更時も同じ
理由(新アドレスが誤記の場合、新しいアクセスURLが届かず本人がそもそも設定変更後の画面に
到達できない=到達性が利用継続の前提条件になっている)により、同じ簡易設計を踏襲する。
変更後アドレスへの新アクセスURL送信が成功して初めて変更が実質的に完了する、という暗黙の
確認フローとする。

## 3. 他ファイルへの反映

- firestore-data-model.md「1. `fleet_operator/{operator_id}`」のドキュメントID定義を
  `internal_id`(自動生成)に変更し、`accessToken`フィールドを追加する必要がある(次回候補。
  本フェーズではスキーマ方針の確定のみ行い、実ファイルへの反映は別フェーズで行う)。
- payment-identity-verification-design.md「3. Checkout Session発行・Webhook紐付け」の
  `client_reference_id = operator_id`は`client_reference_id = internal_id`に読み替える
  必要がある(次回候補)。

## 4. 残課題

- firestore-data-model.md・payment-identity-verification-design.mdへの実際の反映
  (上記3節の変更)は次回候補とする。
- `accessToken`の有効期限(無期限か、一定期間での自動失効を設けるか)は未設計(実装時の
  課題)。他venture(course-set-pashaの連携コードは24時間TTL)と異なり、本トークンは
  「ログインID/パスワードを発行しない」運用の代替そのものであるため無期限が妥当と考えられ
  るが、結論は次回候補とする。
- 実際のメール送信実装・Firestore接続自体はメール連携接続後・GCPプロジェクト作成
  (アカウント作成に該当)後の作業であり、本フェーズでは机上設計のみ(pending-approval.md
  への新規追記は不要。既存の承認待ち事項2〈Stripeアカウント開設〉の範囲内で扱う)。

最終更新: 2026-10-07 01:00 UTC(フェーズ96: payment-identity-verification-design.mdの
残課題〈トークン漏洩時の再発行・メールアドレス変更時の旧トークン失効〉に着手。ドキュメント
IDとアクセストークンを分離する設計変更が必要と判断し、再発行フローを設計した。firestore-
data-model.md・payment-identity-verification-design.mdへの実反映は次回候補として残す)
