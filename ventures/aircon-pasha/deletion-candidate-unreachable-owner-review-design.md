# 削除候補「連絡不能」ケースのオーナー対話確認フロー設計

作成日: 2026-10-13(フェーズ311)

## 1. 背景

line-reservation-aiのフェーズ続き319で、削除候補化後の最終確認が送達できなかった
「連絡不能」ケース(`deletion_confirmation_unreachable_at`が設定済みの状態)について、
オーナーが対話セッションで一覧を参照し個別に削除可否を判断するための読み取り専用レポート
生成機能(`list_unreachable_store_deletion_candidates()`・
`render_unreachable_store_deletion_candidates_report()`)が実装された。同フェーズの
次回候補(2)は、aircon-pasha・course-set-pasha・kura-pashaの`deletion_candidate.py`
関連モジュールにも同種の機能が欠けていないかの横断点検・展開を挙げていた。

本venture(aircon-pasha)を確認した結果、`deletion_candidate_final_confirmation.py`
フェーズ307で`deletion_confirmation_unreachable_at`フィールド自体の記録
(`send_deletion_candidate_final_confirmations()`がLINEブロック中のユーザーに対して
設定)までは実装済みだが、line-reservation-aiと同様にこのフラグ付き候補をオーナーが
参照する導線(一覧表示)が未設計のまま残っていたことを確認した。本フェーズはこの欠落を
埋める。

## 2. スコープ

line-reservation-ai版の設計方針をそのまま踏襲する。

- 読み取り専用のレポート生成に限定。削除実行・自動削除・外部への通知送信(メール・LINE
  再送信等)は一切行わない。
- オーナーへの提示は対話セッション内での表示を想定(Slack通知・メール送信等の自動送信は
  「メッセージの送信」に該当し承認待ち事項になるため対象外)。

## 3. line-reservation-ai版との構成の違い

line-reservation-aiは店舗情報を単一の`stores/{storeId}`ドキュメントに集約する構成の
ため、`StoreDeletionCandidateState`(dataclass)のシーケンスを直接走査する設計だった。
aircon-pashaは`user_profile/{user_id}`ドキュメントを`InMemoryUserProfileStore`等の
ストアが保持し、`all_user_ids()`で列挙してから個別に`get_deletion_confirmation_
unreachable_at(user_id)`を読む構成(deletion_candidate.py・deletion_candidate_final_
confirmation.pyが既に踏襲している構成)のため、本機能も「ストア(Protocol)を受け取り
内部で`all_user_ids()`を走査する」形にする(dataclassのシーケンスを直接渡す形にはしない)。

## 4. 選定ロジックの設計

対象: ストアの`all_user_ids()`が返す全user_idのうち、`get_deletion_confirmation_
unreachable_at(user_id)`が設定済みのもの。user_id昇順で返す(line-reservation-ai版・
`deletion_candidate.list_deletion_candidates()`と同じ、呼び出し順の非決定性を避ける
方針)。各候補に「連絡不能判定からの経過日数」(`now`との差分)を付与する。

既知の限界(line-reservation-ai版と同じ): 連絡不能と判定された理由(ブロック中か、
送信自体の失敗か)は現行`UserProfile`に永続化されておらず、本レポートは理由までは
提示できない。

## 5. レポート内容の設計

line-reservation-ai版と同一の文言方針を踏襲する。

- 候補が0件の場合は「連絡不能の削除候補ユーザーはいません。」の1行のみ。
- 候補がある場合は、件数の見出し・各user_idと経過日数・判定日時の一覧・末尾に
  「本リストは自動削除の対象ではなく、オーナーが対話セッションで個別に削除可否を判断する」
  旨の注記を含める。

## 6. 実施内容

`prototype/deletion_candidate_final_confirmation.py`に`UnreachableDeletionCandidate`
データクラス・`UnreachableDeletionCandidateReader`Protocol(`all_user_ids`・
`get_deletion_confirmation_unreachable_at`の2メソッド、`InMemoryUserProfileStore`は
既存メソッドでそのまま構造的に満たす)・`list_unreachable_deletion_candidates()`・
`render_unreachable_deletion_candidates_report()`を実装する。既存の`list_deletion_
candidates()`等の判定条件には影響しない追加のため、既存ロジック・既存テストとの後方
互換性は保たれる。

## 7. 次回候補

1. 承認待ち事項がオーナーから承認された場合は本venture既存設計一式の実装着手を最優先。
2. course-set-pashaの`deletion_candidate_final_confirmation.py`にも同種の機能が欠けて
   いることを確認済みのため、次回以降の定例更新での展開対象とする(kura-pashaは
   `deletion_candidate.py`相当の構成自体を持たず対象外、別途ワークショップ向けの保存
   期間ポリシーで管理されていることを確認済み)。
3. 他venture・アイデア領域の前進。
