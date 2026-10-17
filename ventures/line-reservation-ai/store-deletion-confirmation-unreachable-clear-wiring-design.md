# 削除候補最終確認「連絡不能」クリア配線 設計決定メモ

フェーズ続き327(2026-10-17 00:00 UTC定例更新)

## 1. 背景

aircon-pashaフェーズ321・course-set-pashaフェーズ300は、削除候補の最終確認が
「連絡不能」(`*_unreachable_at`)と記録された後、オーナーが再フォローしても
その記録がクリアされず、統合後の単一クエリに永久に残り続ける問題を「クリア配線」
(再フォロー時に`clear_*_unreachable_at()`を呼ぶ)で解消した。本ventureにも同種の
問題が存在するかを棚卸しした。

## 2. 本ventureの該当箇所

`store_deletion_candidate.py`の`send_store_deletion_confirmations()`
(`cloud_function_send_store_deletion_confirmations.py`)は、オーナー宛LINE push送信が
1回失敗した時点で`store_deletion_confirmation_unreachable_at`・
`store_deletion_confirmation_unreachable_reason`を設定する(design 5節の簡略化方針)。
しかし`is_store_deletion_candidate()`は`store_deletion_confirmation_sent_at`のみを
冪等性ガードとして見ており、`unreachable_at`は判定条件に含まれない。このため、一度
連絡不能になったオーナーが再フォローしても状態がクリアされず、毎回のバッチ実行で
再び同じ店舗が削除候補として評価され続ける(かつ正常なLINE push経路には戻れない)
という、aircon-pasha・course-set-pashaと同種の問題があることを確認した。

他venture(aircon-pasha・course-set-pasha)と異なり、本ventureはこれらのフィールドが
`store_profile_store.py`の`StoreProfileStoreProtocol`に未実装だった(`store_deletion_
candidate.py`側は独立したdataclass `StoreDeletionCandidateState`としてのみ定義されており、
永続化層への読み書きメソッドが存在しなかった)。本フェーズでまずこのギャップを埋め、
`get_store_deletion_confirmation_unreachable_at()`/`set_store_deletion_confirmation_
unreachable_at()`・`get_store_deletion_confirmation_unreachable_reason()`/
`set_store_deletion_confirmation_unreachable_reason()`の4メソッドを追加した。

## 3. クリア配線

`store_deletion_candidate.py`に`clear_store_deletion_confirmation_unreachable_at()`を
新設し(`StoreDeletionConfirmationUnreachableStoreProtocol`という最小Protocolを要求する、
aircon-pasha/course-set-pashaの同名関数と同じ設計)、`cloud_function_process_event.
ConversationEventProcessor.process_follow_event()`のオーナー再フォロー分岐
(`clear_blocked_but_billing_owner_notified_at()`と並ぶ位置)に配線した。

本venture固有の単純化点: aircon-pasha・course-set-pashaは別コレクション
(`deletion_candidate_final_confirmation.py`等)を介するため新規引数(`deletion_store`等)の
追加が必要だったが、本ventureは店舗情報を単一の`stores/{storeId}`ドキュメントに集約する
構成(store-deletion-candidate-final-confirmation-design.md 2節)のため、
`process_follow_event()`が既に保持している`self._store_profile`をそのまま渡せ、新規引数
・後方互換のデフォルト値は不要だった。

## 4. スコープ外・既知の限界

- 複合インデックスを使う2段階クエリの1クエリ統合(kura-pashaフェーズ239・aircon-pasha
  フェーズ320・course-set-pashaフェーズ299のパターン)は、本ventureには適用対象がない
  ことを確認した。`send_store_deletion_confirmations()`は「呼び出し元でFirestoreから
  読み取った店舗一覧全体」を受け取り、絞り込みは`list_store_deletion_candidates()`が
  インメモリで行う設計(design 5節)であり、そもそも2段階の絞り込みクエリ自体が存在しない
  (`stores`コレクションは店舗数が少ない前提の全件スキャンを既に採用している、
  firestore-data-model.md参照)。よって本フェーズの対象はクリア配線のみとした。
- 実Firestore接続自体は引き続きオーナー承認後の結合実装フェーズに持ち越す。

## 5. 検証

コード変更あり(`store_profile_store.py`・`store_deletion_candidate.py`・
`cloud_function_process_event.py`)。`python3 -m unittest discover -p "test_*.py"`
(942件、既存936件+新規6件)・`python3 schema/validate_test_cases.py`(28件)を実行し、
いずれもパスすることを確認した(回帰なし)。承認が必要なアクション(支払い・アカウント
作成・外部公開・送信等)は本フェーズでは発生していないためpending-approval.mdへの
追記なし。

## 6. 次回候補

1. 承認待ち事項がオーナーから承認された場合はその着手を最優先。
2. `handle_subscription_deleted()`(解約確定)側でも同様のクリア配線が必要かの検討
   (aircon-pasha/course-set-pashaの`blocked_but_billing_owner_notified_at`クリアは
   解約確定側でも行われているため、対称性の観点で確認する価値がある)。
3. 他venture・アイデア領域の前進。

## 7. 追記(フェーズ続き328、2026-10-17 05:00 UTC定例更新): 上記6節(2)の検討結果

上記6節(2)の「`handle_subscription_deleted()`側でも同様のクリア配線が必要か」を検討した
結果、**本venture・aircon-pasha・course-set-pashaのいずれでも不要**と結論した。理由は以下の
対称性の違いによる。

- `blocked_but_billing_owner_notified_at`(「ブロックされているが決済は継続中」通知済み
  フラグ)は、(a)オーナーの再フォロー、(b)`customer.subscription.deleted`受信による
  解約確定、のいずれでもクリアする設計になっている(本ventureの
  `handle_subscription_deleted()`内インライン実装、aircon-pashaフェーズ175の
  `stripe_dispatch.py`配線を確認)。これは、このフラグが示す懸念(「ブロック中なのに
  課金され続けている」こと)自体が、解約確定によって課金が止まった時点で解消される
  ため、再フォローとは独立した経路でもクリアが正しい。
- 一方`store_deletion_confirmation_unreachable_at`(削除候補最終確認の「連絡不能」
  フラグ)が示す懸念は「LINEのpush配信が届かない(オーナーがブロック中)」という
  reachability自体であり、解約確定(`customer.subscription.deleted`)はこの
  reachabilityに何の影響も与えない。実際、aircon-pasha/course-set-pashaの
  `deletion_candidate.py`を確認したところ、`clear_deletion_candidate_on_subscription_
  reactivated()`(再契約時のクリア)は存在するが、こちらも`unreachable`系フィールドは
  一切参照しておらず、両venture共にクリア配線は再フォロー経路のみに限定されている。
  本venture・aircon-pasha・course-set-pashaの3venture全てで同じ設計方針であることを
  確認した。
- さらに、本venture固有の`is_store_deletion_candidate()`の前提条件(`dormant_
  renotify_count == 3`かつfinal送信から365日以上経過、かつ`suspension_reason`が
  設定済み)を踏まえると、「`store_deletion_confirmation_unreachable_at`が設定済み
  (=LINEブロック中)の店舗に対して新たな`customer.subscription.deleted`イベントが
  届く」という事象自体が実質的に到達不能である。再契約(Stripe Checkout)にはLINE
  LIFF経由の本人確認が必要な構成(checkout-initiation-flow-design.md)であり、
  LINEをブロックしたまま新規決済に至ることは想定できないため。

よって本フェーズではコード変更を行わない。コード変更なし、
`python3 -m unittest discover -s prototype -p "test_*.py"`(942件、変更なし)・
`python3 schema/validate_test_cases.py`(28件、変更なし)を実行し、いずれも変更なしで
パスすることを確認した。承認が必要なアクション(支払い・アカウント作成・外部公開・
送信等)は本フェーズでは発生していないためpending-approval.mdへの追記なし。

次回候補: (1)承認待ち事項がオーナーから承認された場合はその着手を最優先、
(2)他venture・アイデア領域の前進。
