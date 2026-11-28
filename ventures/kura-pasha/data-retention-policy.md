# 個人情報の保存期間・削除方針

作成日: 2026-09-07(フェーズ20)

## 目的

README.md「次にやること(候補)」1点目、および legal-notices-draft.md 2.4節が
「本venture固有のdata-retention-policy.md相当の検討は未着手」として暫定的に
aircon-pasha・course-set-pashaの既存整理(1年保有・解約起点)を準用していた点に
対応する。course-set-pasha/data-retention-policy.mdの構成・考え方を踏襲しつつ、
本venture固有の受注特性(1件あたりの制作期間が長く、依頼頻度が低いオーダーメイド
中心)を踏まえて保有期間の妥当性を検討する。

本文書は個人情報保護法の一般的な考え方を踏まえた設計方針の整理であり、法的助言
そのものではない。最終的な妥当性の確認は引き続き法律専門家への確認が必要な事項
として残す(legal-notices-draft.mdと同様の位置づけ)。

## 前提の整理: 本ventureが持つ永続データは3種類(訂正 2026-11-27 16:00 UTC・フェーズ続き338)

legal-notices-draft.md 2.4節・course-set-pashaの想定を踏襲し、本venture(鞍
パシャッと)もline-reservation-aiのような会話状態・予約履歴・通知ログの継続的な
蓄積は持たない。生成した受注内容整理メモ・納品案内下書き・お手入れ案内下書きの
文面自体は、LINE返信メッセージ本文等としてその場で返すのみでサーバー側には
保存しない設計を想定する(course-set-pashaと同じ。mvp-flow-draft.mdの入出力構成
からもサーバー側での本文保存を必要とする理由はない)。

本節は当初(2026-09-07時点)「tech-stack.md相当の設計文書が本venture未作成」という
前提で書かれていたが、tech-stack.mdはフェーズ91(2026-09-12)で新規作成済みであり、
サーバー側に永続保存するコレクションは下表の3種類であることが確定している(下記の
2点目「残課題」が指摘していた確認作業を本フェーズで実施し解消する)。

| コレクション | 用途 | 既存の期限方針 |
|---|---|---|
| `craftsman_workshop/{workshop_id}` | 契約・課金に関するフィールド一式(`contractor_user_id`・`member_user_ids`・`plan_id`・`stripe_customer_id`・`subscription_status`・`trial_start_at`・`current_period_end`等) | 本文書で整理する(下記「保存期間ポリシー(案)」参照) |
| `user_profile/{user_id}` | 職人本人に関する情報(`workshop_id`のみ。屋号・事業形態・メールアドレス等の登録情報は現状craftsman_profile-collection-design.md側の設計を参照) | 本文書で整理する |
| `usage_counter/{workshop_id}` | 月間生成回数カウント | 本文書で整理する |

いずれも「サービス利用者(職人本人)自身」に関する記録であり、course-set-pashaの
`user_profile`・`usage_counter`と同じ位置づけ。顧客(乗馬クラブ・牧場・馬主)の
発注内容自体はサーバー側に保存されないため、本文書が扱う保存期間の論点にはならない。

なお`craftsman_workshop`は本文書が従来「`user_profile`・`usage_counter`」としてのみ
整理していた保存期間ポリシーの判定材料そのもの(`subscription_status`)を保持する
コレクションであり、本文書の対象から漏らしてよいものではない。下記「保存期間
ポリシー(案)」の1年保有ルールは`craftsman_workshop`にも同様に適用する(契約者
`contractor_user_id`・メンバー`member_user_ids`のいずれも、当該workshopの解約を
起点として扱う)。

## 保存期間ポリシー(案)

course-set-pashaと同様、契約関係(Stripeサブスクリプションの状態、pricing-plan.md
「無料トライアル条件」参照)を基準に整理する。

| 状態 | `craftsman_workshop`・`user_profile`・`usage_counter`の扱い |
|---|---|
| トライアル中・有料プラン中(Stripeサブスクリプションが active/trialing) | 保有継続 |
| Stripeカスタマーポータルで解約済み | 解約日から**1年**保有した後、削除候補として洗い出す |

## 本venture固有の論点: 依頼頻度の低さは保有期間を延ばす理由になるか

legal-notices-draft.md 2.4節が残していた検討課題(「1年で十分か、より長期の記録
価値がある高額オーダーメイド品ゆえの特殊性があるか」)を検討する。

- 保有される`user_profile`の中身は屋号・事業形態・メールアドレス・決済ID等の
  「職人自身の登録情報」にとどまり、個々の発注内容(鞍の型・革の種類等)は
  サーバー側に保存されない設計のため、そもそも「高額オーダーメイド品ゆえの
  記録価値」に該当する情報自体を`user_profile`は保持していない。したがって
  依頼頻度の低さ・単価の高さという受注特性は、`user_profile`の保有期間を
  延ばす直接の理由にはならないと判断する。
- 一方、依頼頻度が低い(pricing-plan.mdの想定で月数件〜十数件程度、かつ職人
  1名あたりでは更に少ない)ことは「解約後、しばらくして再開したくなる」
  可能性がcourse-set-pasha(週次のSNS投稿という高頻度反復業務)より高いとも
  考えられる。ただし`user_profile`の中身自体が屋号・メールアドレス・決済ID
  という再入力コストの低い情報にとどまるため、「再登録の手間を省く」ことを
  理由に保有期間を延ばすメリットは小さいと判断する(決済IDはStripe側で
  解約時に別途無効化されるため、保有し続けても即時決済再開には使えない)。
- 以上より、本venture固有の事情を理由に他venture(1年)と異なる保有期間を
  設定する積極的な根拠はないと結論し、**course-set-pasha・aircon-pashaと同じ
  1年**をそのまま採用する。個人情報保護の観点では保有期間は必要最小限に
  とどめるべきであり、独自の延長理由がない以上は既存venture群と揃えることを
  優先した。

## 削除候補化後の最終確認

course-set-pasha/data-retention-policy.mdと同じ考え方を採用する。削除候補として
洗い出した後も即座には削除せず、職人本人へ最終確認を試みることが望ましい。

- 主経路: LINE公式アカウントからのpush送信。
- 代替経路: unfollow(ブロック)済みでLINE送達ができない場合、`user_profile`に
  登録されたメールアドレスへの通知を代替経路とする(実装はメール送信基盤の
  整備後、他venture共通の課題)。
- いずれの経路でも応答が得られない場合は自動削除せず、運営者(本リポジトリの
  オーナー)が個別に削除可否を判断する。

## 開示・削除請求への対応

職人からの開示・削除請求への対応窓口は運営者(本リポジトリのオーナー)とし、
LINEの公式アカウントへのメッセージ、または登録メールアドレスからの連絡を
受付経路とする(他venture共通の想定)。

## 非契約者メンバー除外時の保存期間論点(新規検討 2026-11-28 00:00 UTC・フェーズ続き339)

上記「残課題」最終項(member側固有の削除候補化論点)を検討する。
downgrade-excess-member-handling-design.md(フェーズ28)「3. 確定する設計」により、
複数職人プランからのダウングレード時、猶予期間経過後に契約者以外の`member_user_ids`は
機械的に解除される(デフォルトルール)。この「解除」はworkshop自体の解約ではなく、
`craftsman_workshop`は契約者のもとで存続し続ける点が、本文書が従来前提としていた
「`craftsman_workshop`解約」を起点とする1年保有ルール(上記「保存期間ポリシー(案)」)
とは異なるトリガーである。

- **解除された非契約者メンバーの`user_profile/{user_id}`は現状放置される**:
  downgrade-excess-member-handling-design.md「3. 確定する設計」は解除後に
  `WorkshopNotLinkedError`相当の案内を返す設計までは定めているが、
  `user_profile/{user_id}.workshop_id`(craftsman-account-linking-design.md
  フェーズ変更分、115行目)を解除時にクリアする処理は定義しておらず、このままでは
  解除後も存在しないworkshopへの参照が残り続ける。
- **解除は契約者側の`craftsman_workshop`解約と独立したイベントであるため、本文書の
  既存トリガー(workshop解約起点の1年保有)では捕捉できない**。解除された本人は
  当該workshopの契約者ではなく、Stripeサブスクリプションの状態変化を直接には
  持たないため、「Stripeカスタマーポータルで解約済み」という既存トリガー文言は
  そのままでは適用できない。

### 確定する方針

1. 余剰メンバー解除(downgrade-excess-member-handling-design.md「3. 確定する設計」の
   都度チェック処理)の実装時、解除対象の`user_id`について
   `user_profile/{user_id}.workshop_id`を同時にクリア(null化)する処理を追加する。
   これによりダングリング参照を防ぎ、かつ「workshop_idがnullになった時点」を
   当該ユーザー固有の新たな削除候補化起点として扱えるようにする。
2. 解除された本人がcraftsman-account-linking-design.md(フェーズ58相当、58行目)の
   既存ロジック「未所属の場合は1人だけのworkshopを自動作成」により改めてサービスを
   利用した場合は、新規workshopの契約者としての`craftsman_workshop`レコードが
   作られるため、削除候補化は発生しない(上記1年保有ルールの通常起点に戻る)。
3. 解除後、一定期間(`craftsman_workshop`解約と同じ1年を暫定採用し、本venture固有の
   延長理由がないことは上記「本venture固有の論点」の結論をそのまま準用する)
   再利用がない場合、`user_profile/{user_id}`(workshop_idは既にnull)を削除候補として
   洗い出す。最終確認の経路(LINE push、不達時はメール代替)は上記「削除候補化後の
   最終確認」節と同一の仕組みを流用する。

### 未着手・次回候補

- (対応済み 2026-11-28 08:00 UTC・フェーズ続き340): 本節1点目「解除時の
  workshop_idクリア」処理を実コード化した。`UserProfileStoreProtocol.unlink`
  (prototype/usage_counter_workshop.py)・`FirestoreUserProfileProvider.unlink`
  (prototype/firestore_user_profile_adapter.py)を追加し、
  `check_and_apply_pending_member_reduction`が縮小によって実際に除外した
  user_id全員について呼び出すよう配線した。詳細は
  downgrade-excess-member-handling-design.md「4. 未検証・残課題」フェーズ続き340
  追記を参照。
- (対応済み 2026-11-28 15:00 UTC・フェーズ続き341): 本節に残っていた
  「`workshop_id`がnullになったuser_profileを1年後に削除候補として洗い出す」
  ロジックを実コード化した。`unlink()`に`unlinked_at`引数を追加して除外時刻を
  記録し、新規モジュール`member_user_profile_deletion_candidate.
  list_member_deletion_candidates()`で`unlinked_at + 365日`経過分を洗い出せる
  ようにした(既存の解約起点フロー`deletion_candidate.py`とRETENTION_DAYS定数は
  共通化、関数自体はuser_profile単位で別モジュールとした)。詳細は
  member-user-profile-deletion-candidate-design.md参照。日次バッチへの配線・
  最終確認通知との結線は次回候補として残る(同ファイル5節参照)。

## 残課題

- (対応済み 2026-11-27 16:00 UTC・フェーズ続き338): 「tech-stack.md新規作成時に
  本文書の想定〈2コレクションのみ〉との整合を確認する」としていた本課題を対応した。
  tech-stack.mdはフェーズ91(2026-09-12)に新規作成済みであり、実際のコレクション数は
  2ではなく3(`craftsman_workshop`・`user_profile`・`usage_counter`)だったことを
  確認し、「前提の整理」節・上記表を訂正した。約2ヶ月半(tech-stack.md作成から本訂正
  まで)陳腐化した記載が残っていたことになる。
- legal-notices-draft.md 2.4節の「暫定準用」の記述は、本文書の内容に基づいて
  正式な記載へ差し替え済み(フェーズ21)。
- 削除候補化後のメール通知の実装(メール送信基盤の整備)は他venture共通の
  未実装課題であり、本venture固有の追加課題ではない。
- ~~`craftsman_workshop.member_user_ids`に含まれる非契約者(追加メンバーの職人)の
  削除候補化・最終確認フローは、本文書は契約者(`contractor_user_id`)起点の整理に
  留まっており、member側固有の論点(退会・権利関係)は未検討のまま残る。~~
  (対応済み 2026-11-28 00:00 UTC・フェーズ続き339: 上記「非契約者メンバー除外時の
  保存期間論点」節で方針確定。実装〈user_profile.workshop_idクリア処理〉は
  downgrade-excess-member-handling-design.md側の実装とあわせて次回候補)。

最終更新: 2026-11-28 00:00 UTC(フェーズ続き339: 非契約者メンバー除外〈ダウングレード
時の余剰メンバー解除〉時の`user_profile`保存期間・削除候補化トリガーを新規検討・
方針確定。ドキュメントのみの更新、コード変更なし)
