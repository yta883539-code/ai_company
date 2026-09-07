# 契約者(contractor)譲渡機能の要否検討・設計(フェーズ33)

作成日: 2026-09-07(フェーズ33)

## 背景・対応する残課題

craftsman-account-linking-design.md(フェーズ25)「未検証・残課題」3点目、および
downgrade-excess-member-handling-design.md(フェーズ28)4節で、いずれも「MVP範囲外」
として先送りにしてきた契約者(contractor)譲渡機能について、README.md「次にやること」
で要否検討そのものを次の一歩として明記していたため、本ファイルで着手する。

## 1. 要否検討: そもそも必要か

先送りにしてきた理由は「本venture初期のMVP範囲を絞るため」であって、需要が無いという
判断ではなかった。改めて検討すると、本venture(伝統工芸職人向け)固有の事情として、
以下の理由により契約者譲渡は投機的な将来機能ではなく実際に起こりうる導線と判断する。

- 伝統工芸の工房は師弟制・家族経営が多く、契約時の契約者(親方・先代)が引退し、
  弟子・後継者(二代目)が契約を引き継ぐ「事業承継」は、他venture(course-set-pasha・
  aircon-pashaのような単一事業者向けサブスク)よりも本ventureで発生頻度が高いと
  想定される固有のシナリオである。
- 複数職人プランでは`contractor_user_id`が解約・ダウングレード操作権限
  (subscription-cancellation-flow-design.md)や、downgrade-excess-member-handling-design.md
  3節の「残すメンバーのデフォルトルール」の基準そのものになっており、契約者が
  引退してLINEアカウントを使わなくなった場合、後継者は解約操作すら行えなくなる
  (`contractor_user_id`と一致しない限り厳守事項7aの解約意図検知対象にならない
  ため、サポート外の問い合わせとして扱われてしまう)。
- 結論: **必要な機能であり、これ以上の先送りは運用上のリスクになる**。ただし
  MVPとしてのスコープは最小限に絞る(2節)。

## 2. スコープの絞り込み

- 対象を**既存workshopの`member_user_ids`に既に含まれるメンバーへの譲渡のみ**に
  限定する(workshop外の第三者への直接譲渡は不可)。理由: 第三者への譲渡は
  実質的に「新契約者の本人確認」という別課題(なりすまし防止)を新たに生むが、
  既存メンバーへの譲渡であれば、そのメンバーは既に5節(craftsman-account-linking-design.md)
  の招待コードフローを経て本人のLINEアカウントとworkshopの紐付けが完了済みであり、
  追加の本人確認機構を作らずに済む。
- ライト/スタンダードプラン(1人だけのworkshop)では、契約者=唯一のmemberであるため
  本機能の対象外とする(譲渡先となる既存メンバーが存在しない)。複数職人プランに
  限定した機能とする。

## 3. 確定する設計

- 意図検知: 契約者(`contractor_user_id`と一致する`user_id`)からのメッセージで
  「契約者を交代したい」「後継ぎに変更したい」等の譲渡意図を検知した場合、
  member-retention-notice-design.mdの`specified_member_name`突き合わせロジックを
  再利用し、メッセージ中で名指しされた相手が`member_user_ids`内の既存メンバーの
  表示名と一致するかを判定する。
  - 一致する場合: `status`を新設の`contractor_transfer_selection`とし、
    `contractor_transfer_notice`フィールドに「◯◯様を新しい契約者として設定します。
    よろしいですか?」という確認文言下書きを生成する(即時反映せず、契約者からの
    再確認〈"はい"等の応答〉を経てから`craftsman_workshop.contractor_user_id`を
    更新する2段階方式とする。理由: 契約者権限の移動は解約権限そのものの移動でも
    あり、member-retention-notice-design.mdの「残すメンバー選定」より影響が大きい
    ため、確認なしの即時反映は避ける)。
  - 名指しされた相手が`member_user_ids`に含まれない場合(まだworkshopに参加して
    いない第三者を指定した場合を含む): `status`を`contractor_transfer_unclear`とし、
    「先に招待コードでworkshopへ加わっていただいてから、改めて契約者交代のご連絡を
    ください」という案内文言下書きを生成する(2節のスコープ限定をユーザーに伝える
    役割を兼ねる)。
  - 契約者以外のメンバーから譲渡意図が検知された場合は、6節(craftsman-account-linking-design.md)
    の非契約者からの解約意図表明と同様に「契約者様にご確認ください」と案内する
    既存パターンをそのまま踏襲する(契約者本人以外は譲渡を開始できない)。
- 確定処理(コード実装は次の課題、4節参照): 契約者からの再確認応答を受けて
  `craftsman_workshop/{workshop_id}.contractor_user_id`を新しいuser_idへ更新する。
  旧契約者は`member_user_ids`からは自動的には外さない(譲渡後も引き続き工房の
  一員として利用を続けられるようにし、脱退は別途本人の意思表示に委ねる。
  downgrade-excess-member-handling-design.md 3節の「残すメンバー」ロジックとは
  独立した操作として扱う)。
- `usage_counter/{workshop_id}`は契約者譲渡による影響を受けない(workshop_id自体は
  不変のため、usage-counter-workshop-key-design.mdの既定方針をそのまま踏襲できる)。

## データ構造まとめ(追加分)

| コレクション | キー | フィールド | 用途 |
|---|---|---|---|
| `craftsman_workshop/{workshop_id}` | workshop_id | `contractor_user_id`(更新可能に変更) | 譲渡確定処理で書き換え対象になる(craftsman-account-linking-design.md 4節では「以後変更不可」としていたが、本設計により変更可能な運用に改める) |

`status`のenumへ`contractor_transfer_selection`/`contractor_transfer_unclear`の2値、
および対応する`contractor_transfer_notice`フィールドをschema/output.schema.jsonへ
追加する必要がある(実装は次の課題)。

## 4. 未検証・残課題

- ~~schema/output.schema.json・validate_test_cases.pyへの反映(新規enum値2つ・
  `contractor_transfer_notice`フィールド・クロスフィールド検証)~~ → フェーズ34で対応済み
  (`status`のenumへ`contractor_transfer_selection`/`contractor_transfer_unclear`追加、
  `contractor_transfer_notice`フィールド追加、クロスフィールド検証・新規テストケース
  CT1/CT2・ネガティブテストケース追加、全16件パス確認)。
- ~~prototype/usage_counter_workshop.py側の`craftsman_workshop`データ構造は現状
  Firestore設計の机上表現のみで実装されていないため、`contractor_user_id`更新処理の
  プロトタイプコード化も未着手。~~ → フェーズ35で対応済み(`WorkshopStoreProtocol`に
  `set_contractor_user_id`を追加、名指しされた相手が既存メンバーの表示名と一致するかを
  判定する`resolve_contractor_transfer_target`、契約者からの再確認応答後に呼び出す
  確定処理`apply_contractor_transfer`〈既存メンバー外への呼び出しは
  `ContractorTransferTargetNotFoundError`で防御〉を実装し、新規5テストケースを追加して
  全49件パスを確認した)。
- 「契約者からの再確認応答」をどう検知するか(単純な「はい」「お願いします」等の
  自由記述をLLMにどう判定させるか)の具体的なプロンプト設計は未着手のまま残る。
- 実際のLINE公式アカウント接続・Firestore接続は未着手(オーナー承認待ちの範囲、
  pending-approval.md参照)。

最終更新: 2026-09-07 20:02 UTC(フェーズ35: `contractor_user_id`更新処理のプロトタイプ
コード化)
