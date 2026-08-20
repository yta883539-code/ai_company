# LINE友だち追加時のuser_id事前紐付け設計(連携コード方式)

作成日: 2026-08-20(フェーズ77)

application-form-submission-flow-design.md 残課題「LINE友だち追加時のuser_id事前紐付け経路が
本venture未設計のため、フォーム側でのuser_id手入力運用の是非(誤入力リスク)は別途検討が必要」に
対応する。

## 1. 問題の再整理

フェーズ76時点の設計は「申込フォームにLINE user_idを本人が手入力する」という暫定運用だった。
検討の結果、これは単なる「誤入力リスク」の問題ではなく、**そもそも一般のLINEユーザーは自分の
user_id(`U`で始まる文字列)をLINEアプリのUI上から確認する手段を持たない**ため、運用として
成立しない設計であることが判明した(トーク画面・プロフィール画面のいずれにもuser_idの表示箇所は
無く、開発者向けのLINE Developersコンソールを経由しないと取得できない)。したがって手入力前提の
設計は根本的に見直す必要がある。

## 2. 設計方針: 連携コード方式

- LINE公式アカウントを友だち追加した時点(`follow`イベント)で、Cloud Function側が
  ランダムな短い**連携コード**(6文字、英数字)を発行し、`pending_links/{code}`ドキュメントに
  `{user_id, issued_at}`を保存したうえで、ウェルカムメッセージの返信本文にそのコードを埋め込んで
  本人へ送る。
- 申込フォームの入力項目を「user_id」から「連携コード」に変更する(onboarding-settings-and-
  self-check-design.md・application-form-submission-flow-design.md 2節のフォーム項目定義を
  併せて更新する必要がある。フォーム自体の実設定はオーナー承認待ちのため、項目名の変更方針のみ
  ここで確定する)。
- GAS Webhookのペイロードは`user_id`ではなく`linking_code`を送るよう変更する:

  ```json
  {
    "linking_code": "7K9XPQ",
    "gym_area_pairs_raw": "クライミングジムA/○○区, ボルダリングジムB/△△市"
  }
  ```

- Cloud Function側で`linking_code`を`user_id`へ解決してから、フェーズ76で実装済みの
  `handle_form_submission()`(user_id版)へ委譲する。既存の正規化・上書きロジックは変更しない。

## 3. コード仕様

- 文字種: 英大文字26種+数字10種から、視認性の低い文字(`0`/`O`、`1`/`I`/`L`)を除いた
  31種のアルファベットを使用する(スマートフォンでの手入力ミスを減らすため)。
- 長さ: 6文字(31^6 ≈ 8.9億通り。同時に有効なコード数はfollow直後のごく短期間に限られるため
  衝突確率は無視できる水準。念のため発行時に既存コードとの重複チェックを行い、衝突時は
  最大5回まで再生成する)。
- 有効期限: 発行から24時間。フォーム提出時にこれを超えていれば無効として扱う。
  「友だち追加してすぐ申し込む」という主要導線を想定すれば24時間で十分だが、後日改めて
  申し込む(=フォームだけ後で埋める)利用者のために、期限切れの場合は「もう一度LINEで
  トークを開くと新しいコードが届きます」という趣旨の案内をフォーム側のエラーメッセージに
  表示する想定とした(実際のエラーメッセージ文言はGoogleフォーム側の実装時に確定)。
- 使い切り(one-time use): フォーム提出で解決に成功したコードはその場で`pending_links`から
  削除する。同じコードを2回目に使おうとした場合は「見つからない」扱いとなり、再提出には
  新しいコードの再取得(再度LINEで話しかける等)が必要になる。これはline-reservation-aiの
  `booking-slot-manager-design.md`が採用した「使用済み・期限切れの区別をユーザーには
  意識させず、単に無効として扱う」方針を踏襲したもの。

## 4. 未フォロー・再フォロー時の扱い

- ブロック後の再フォロー(`follow`イベントの再発火)では、その都度新しいコードを発行する。
  ブロック前に発行済みで未使用のまま残っていたコードは明示的には削除しない(MVPでは
  `pending_links`のガベージコレクションの仕組みを持たないため)。有効期限(24時間)が
  自然な失効境界として機能するため、実害(古いコードが後から別人に渡ることによる誤紐付け)は
  実質的に発生しない設計とした。

## 5. プロトタイプ実装方針

- `prototype/user_id_linking.py`に、`LinkingCodeStoreProtocol`(`save`/`get`/`delete`)と
  実Firestore接続前の検証用`InMemoryLinkingCodeStore`を新設した
  (application_form_submission_flow.pyの`UserProfileStoreProtocol`と同じ責務分離パターン)。
- `issue_linking_code_on_follow(user_id, store, now, rng)`: コード生成・重複チェック・保存までを
  行い、発行したコード文字列を返す(呼び出し側がこれをウェルカムメッセージに埋め込む)。
- `resolve_linking_code(code, store, now)`: 存在確認・期限切れ判定・使い切り(削除)までを行い、
  `LinkingResolution(ok, user_id, error)`を返す。
- `handle_form_submission_with_linking_code(payload, profile_store, linking_store, now)`:
  上記の解決を行ったうえで、既存の`handle_form_submission()`(application_form_submission_flow.py)
  へ委譲する薄いオーケストレーター。既存モジュールへの変更は行わず、依存を追加するだけとした。

## 残課題

- Googleフォームの項目名変更(「LINE user_id」→「連携コード」)自体はフォーム未作成のため
  今回は反映できず、実設定時(オーナー承認待ち、pending-approval.md参照)に合わせて行う。
- `follow`イベント受信時にウェルカムメッセージへコードを埋め込んで実際に返信する処理は、
  実LINE Messaging API接続自体がオーナー承認待ちのため未着手(コード発行ロジック自体は
  実接続なしで検証済み)。
- `pending_links`の期限切れドキュメントの定期パージ(Firestore TTLポリシーの利用を想定)は
  実Firestore接続後の課題として残す。
