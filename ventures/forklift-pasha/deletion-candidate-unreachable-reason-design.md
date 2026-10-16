# 削除候補・連絡不能の理由コード設計

作成日: 2026-10-16(フェーズ157)

## 1. 背景

aircon-pashaフェーズ313・line-reservation-aiフェーズ続き320は、削除候補の最終確認が
「連絡不能」と判定された際に、その理由(なぜ連絡が取れなかったか)が一切記録されておらず、
オーナーが連絡不能リストを見ても次に取るべき対応(メールアドレスの再確認を依頼するか、
再送を試すか等)を判断できないという既知の限界を発見した。aircon-pasha・course-set-pasha・
kura-pashaは既にこの発見を受けて`unreachable_reason`フィールドを追加済みだったが、
forklift-pashaのみ未対応のまま残っていたため、本フェーズで横展開する。

## 2. 他ventureとの相違点

- aircon-pasha(LINEブロック由来の`not_following`)・course-set-pasha
  (`UNREACHABLE_REASON_NOT_FOLLOWING`1種類)はいずれも連絡経路がLINE1本であるため、
  理由コードも1種類で足りた(course-set-pashaフェーズ294で「2種類必要」という見込みが
  誤りだったと確認済み)。
- forklift-pashaはLINEフォロー概念を持たず、連絡経路がメール1本のみ
  (deletion-candidate-design.md 2節)だが、メール特有の事情として「メールアドレス自体が
  未登録」と「メールアドレスは登録済みだが送信に失敗した」の2つの異なる原因が区別できる。
  前者は本フォームでの登録漏れ(オーナーが別経路で本人確認すべき)、後者は配信エラー
  (再送を試す価値がある)と対応が異なるため、本ventureでは1種類に単純化せず
  `UNREACHABLE_REASON_NO_EMAIL`・`UNREACHABLE_REASON_SEND_FAILED`の2種類とする。

## 3. 実装

- `prototype/deletion_candidate.py`: 上記2定数と、理由コード→表示ラベルの辞書
  (`_UNREACHABLE_REASON_LABELS`)を追加。
- `send_deletion_candidate_final_confirmations()`: `email_sender.send()`が失敗した際、
  `email is None`なら`NO_EMAIL`、そうでなければ`SEND_FAILED`を`unreachable_reason`として
  `store.set_deletion_confirmation_unreachable_reason()`に書き込む。
- `UnreachableDeletionCandidate`データクラスに`unreachable_reason`フィールド(既定値
  `None`、本フィールド追加前に記録された候補との後方互換)と`unreachable_reason_label`
  プロパティ(Noneなら「不明(本フィールド追加前に記録された候補)」にフォールバック、
  aircon-pasha等と同じ方針)を追加。
- `render_unreachable_deletion_candidates_report()`の各行に理由ラベルを追記。
- `trial_management.FleetOperatorStoreProtocol`/`InMemoryFleetOperatorStore`に
  `get/set_deletion_confirmation_unreachable_reason()`を追加。
- `firestore-data-model.md`に`deletionConfirmationUnreachableReason`フィールドを追記。

## 4. テスト

`test_deletion_candidate.py`にケース4件を追加(メールアドレス未登録時の理由コード、
送信失敗時の理由コード、フィールド追加前の候補の不明表示フォールバック、レポートへの
理由反映)。全20件パス(`python3 test_deletion_candidate.py`)。
`python3 run_all_tests.py`で全18ファイルパスを確認。

## 5. スコープ外

- 実際のメール送信サービス接続・実送信は、既存の承認待ち事項(data-retention-policy.md
  5節・pending-approval.md記載)の範囲内であり、本フェーズで新たな承認待ち事項は発生しない。

## 6. 次回候補

1. 承認待ち事項(実Stripe/メール送信サービス等)がオーナーから承認された場合、実装着手を
   最優先。
2. 他venture・アイデア領域の前進。
