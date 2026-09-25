# 初回生成時セルフチェック案内の設計(フェーズ178)

作成日: 2026-09-25(フェーズ178)

onboarding-guide.md「未検証の仮説」1点目(手順3〈接続テスト〉を代表者が実際に自発的に
行うか、省略して本番の依頼者対応を開始し誤った内容に気づかないまま運用が始まるリスクが
あるか)、および同ファイル末尾の「course-set-pashaのonboarding-settings-and-self-check-
design.md相当のフォールバック設計の要否は次のステップ候補とする」に対応する。
course-set-pasha/onboarding-settings-and-self-check-design.md 2節、line-reservation-ai/
first-booking-self-check-notification-design.mdを踏襲しつつ、本venture固有の構造
(workshop単位契約・複数職人プラン)を反映する。

**本ドキュメントは設計のみを行うものであり、実装(コード変更)は次フェーズ以降の課題とする。**

## 1. 前提の確認

- 本ventureはtech-stack.mdの通り会話状態を持たない単方向バッチ処理(1メモ入力→1回の
  生成で完結)であり、course-set-pashaと同じく「試験生成」と「本番生成」を区別する専用
  フラグや別エンドポイントをonboarding-guide.mdは想定していない(手順3は手順4と同じ
  入出力の仕組みをそのまま使う「試しに送ってみる」行為でしかない)。したがってシステム側は
  特定の1回を「これは接続テストだ」と判別する手段を持たない。
- 出力はmvp-flow-draft.mdの3種(受注内容整理メモ・納品案内下書き・お手入れ案内下書き、
  schema上は`order_summary`・`delivery_notice`・`care_notice`)で、
  `format_generated_reply()`(`prototype/cloud_function_webhook.py`)が
  `status="generated"`の場合にこの3出力を1通のLINE返信文へ結合している。

## 2. course-set-pashaとの構造的な違い

course-set-pashaは契約単位が`user_id`(1人=1契約)であるため、「そのユーザーにとって
最初の生成成功時」という判定がそのまま「その契約にとって最初」と一致する。

本ventureは契約単位が`workshop_id`であり、1つのworkshopに契約者(代表)+参加職人
最大4名、計最大5名(craftsman-account-linking-design.md 11.7節)が同一の月間生成回数枠
(`usage_counter/{workshop_id}`、usage-counter-workshop-key-design.md)を共有しうる。
このため「ユーザー単位の初回」ではなく**「workshop単位の初回」**を判定基準とすべきである。
理由は次の2点。

1. usage-counter-workshop-key-design.md 1節が指摘した通り、本ventureは既に
   「メンバーごとに別々の枠を持つとworkshop単位の上限が意味を失う」という理由で
   `usage_counter`をuser_idキーからworkshop_idキーへ移行済みである。初回生成の判定も
   これと同じ理由(ユーザー単位に分解すると、workshopとしては既に本番運用が始まって
   いるのに新規参加メンバーの初回送信のたびに案内が再度付記されてしまい、既存メンバーに
   とっては煩わしい二重案内になる)で、workshop単位に統一するのが自然である。
2. セルフチェック案内の目的(ジム名・地域名等の設定確認、というcourse-set-pashaの
   意図に相当するもの)は、本ventureでは「屋号(workshop_name、フェーズ177で
   `set_workshop_name()`実装済み)や出力形式が意図通りか」の確認であり、これは
   workshop全体で共有される設定であって個々の参加職人ごとに異なるものではない。
   代表者以外の職人が後から追加された場合、その職人個人にとっては初めての送信でも、
   workshopとしての設定確認は既に代表者の初回生成時に完了している。

## 3. 方針

- **判定基準**: そのworkshopにとって最初の`status="generated"`成功時(送信者が
  代表者・追加職人のいずれであっても、workshop単位で1回のみ)に、通常の3出力
  (`format_generated_reply()`の結合結果)の末尾に確認案内を1回だけ付記する。
  2回目以降(同じworkshop内の別メンバーによる送信を含む)は付記しない。
- **永続化**: course-set-pashaの残課題(line-reservation-aiのインメモリフラグは
  サーバーレス関数の再起動・インスタンス使い捨てのたびに失われる既知の差異)と同じ理由で、
  `craftsman_workshop/{workshop_id}`ドキュメントへ`first_generation_notice_sent: bool`
  フィールドを永続化する。`WorkshopStoreProtocol`(`prototype/usage_counter_workshop.py`)へ
  `get_first_generation_notice_sent(workshop_id) -> bool`・
  `set_first_generation_notice_sent(workshop_id) -> None`を追加する想定とし、
  フェーズ177の`get_workshop_name`/`set_workshop_name`追加と同じ形を踏襲する。
- **実装位置**: course-set-pashaと同じく、post_generation_checks相当の厳守事項違反検知
  ロジックとは責務が別であるため、この確認案内は出力組み立て側
  (`format_generated_reply()`の呼び出し元、`process_memo_event()`の返信文確定直前)に
  実装し、違反検知ロジックとは混在させない。
- **ジム名・地域名相当の未設定時追加一文は不要**: course-set-pasha 2節後半は
  「ジム名・地域名が未入力の場合に追加の一文を付記する」設計を持つが、これは
  ジム名・地域名がLLM生成品質(ハッシュタグの地域タグ精度)に直接影響する入力だから
  である。本ventureのonboarding-guide.md 2節が定める申込フォーム項目(屋号・連携コード・
  連絡先メール・想定利用形態)のうち、屋号(workshop_name)はフェーズ177で追加した
  オーナー向け通知(payment_suspension_owner_notification.py等)の表示にのみ使われ、
  LLM生成そのもの(`order_summary`等の内容)には渡していない
  (`llm-system-prompt-draft.md`・`mvp-flow-draft.md`のいずれにもworkshop_name等を
  プロンプト変数として参照する記述が無いことを確認済み)。したがって本ventureには
  course-set-pashaのような「未設定時に生成品質が落ちる項目」自体が存在せず、
  未設定時の追加一文分岐は不要と判断する。

## 4. 確認案内の文面案

3出力の結合結果(`format_generated_reply()`の戻り値)の末尾に、空行を挟んで追記する。

```
【ご確認のお願い】これが本workshopでの最初の生成です。受注内容整理メモ・納品案内・
お手入れ案内の内容や書き味が意図通りか、この機会にご確認ください。修正したい点があれば
申込内容の変更フォームからご連絡ください。問題がなければ今後この案内はありません。
```

- tone-and-manner-guideline.mdの文体(ですます調・絵文字不使用)に合わせた定型文とし、
  `member_limit_reached`等と同じくPython側の決定論的テンプレート(LLM呼び出しを経ない
  固定文言)とする(この案内自体は入力内容に応じて変わる余地が無く、7節で述べた
  (a)〜(c)のような自然文解釈を必要としないため)。

## 5. 未検証の仮説・残課題

- 「試験生成のつもりで送ったメモが、実は最初の生成ではなく2回目以降だった」ケース
  (例: 代表者が試験のつもりで送った初回メモに気づかず、2回目の送信で案内が出ずそのまま
  本番の納品案内として依頼者へ転記してしまう)は、course-set-pasha/line-reservation-ai
  同様システム側では区別できない既知の限界として残す。
- 複数職人プランで、代表者の初回生成時に案内が出た後、参加職人が追加されて初めて
  送信した際には案内が出ない(3節2.の判定基準通り)。この場合、追加された職人本人が
  workshop全体の設定確認を代表者から引き継いで把握しているかは未検証
  (onboarding-guide.md「未検証の仮説」2点目〈代表者以外の職人が実際にどの程度自分で
  送信するか〉と関連する論点であり、customer-interview-design.mdのヒアリングで
  実運用の傾向を確認してから、追加職人向けの簡易案内の要否を再検討する)。
- 実装自体(`WorkshopStoreProtocol`への2メソッド追加、`process_memo_event()`側の配線、
  統合テスト追加)は本フェーズでは行わず、次フェーズ以降の課題とする
  (course-set-pashaもonboarding-settings-and-self-check-design.md作成〈2026-08-16〉から
  実装〈フェーズ73〜75〉まで複数フェーズを要した)。

最終更新: 2026-09-25 15:00 UTC(フェーズ178: 新規作成。onboarding-guide.mdが次のステップ
候補としていたcourse-set-pasha相当のセルフチェック案内フォールバック設計を本venture向けに
検討。workshop単位契約の構造上、判定基準を「ユーザー単位」ではなく「workshop単位」の
初回生成とする点、ジム名・地域名相当の未設定時追加一文が本ventureには不要な点を確定。
設計のみでコード変更は無し)
