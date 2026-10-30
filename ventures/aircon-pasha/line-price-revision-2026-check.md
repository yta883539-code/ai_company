# 2026年10月LINE公式アカウント料金改定の影響確認(本venture向け横展開)

kura-pasha/line-price-revision-2026-check.md・line-reservation-ai/line-price-revision-2026-check.md
(いずれもcourse-set-pashaフェーズ横展開)が「次回候補」として残していた「aircon-pasha・
course-set-pashaへの同種確認の横展開」に対応し、本venture固有の利用量を前提に影響評価を行う。

## 改定内容(kura-pasha/line-reservation-ai調査の再掲)

- 2026年10月1日、LINE公式アカウント「スタンダードプラン」(無料枠30,000通/月)の追加メッセージ
  料金体系が、20万通/月まで一律1通3円・20万通超は1通2.5円という2段階体系に一本化される。
- 一次情報(lycbiz.com)は本エージェントの実行環境ではegressポリシーにより直接確認できず
  (`EGRESS_BLOCKED`)、line-reservation-ai・kura-pashaと同様に二次情報源のクロスチェックに
  とどまる。この制約は本ventureでも解消できないため、そのまま留保として引き継ぐ。

## 本ventureの利用量見積もり

- pricing-plan.mdの3プラン(スモール40回/月・スタンダード90回/月・繁忙期対応150回/月)は
  他venture(course-set-pasha月8〜30回、line-reservation-ai月間最大1,000通強)より1桁多い
  月間生成回数を想定している点が本venture固有の特徴。
- limit-approaching-notification-design.mdより、1回の生成完了報告に対する返信は
  completion_report/care_guide/history_rowの最大3通構成。上限接近通知(1回のみ)を加えても
  1業者・1生成あたり最大4通程度。
- 繁忙期対応プラン(月150回)を上限まで使い切るケースで概算すると、150回×4通=月600通。
  スモール・スタンダードプランはこれより少ない(最大360通/月)。
- 管理会社向け一括契約プラン(pricing-plan.md「管理会社向け一括契約プラン」節)は月間退去
  精算60戸までを想定するが、これは個人向けプランの生成回数とは別会計・別チャネルであり、
  管理会社自身のLINE公式アカウントで受け取る前提かは未確定(同節の補足に記載の通り契約形態は
  要検証)。仮に管理会社が自身のLINE公式アカウントで通知を受ける場合でも60戸×4通=月240通
  程度であり、個人向け繁忙期対応プランの見積もりを超えない。
- いずれも1業者(1LINE公式アカウント)あたりの見積もりであり、無料枠(30,000通/月)の
  2桁以上少ない水準にとどまる。

## 影響評価

- 本venture最大想定の月600通(繁忙期対応プラン上限使用時)でも、改定で単価が変わる
  「5万〜20万通帯」「20万通超」のいずれにも遠く届かない。無料枠(30,000通/月)の2%程度。
- 結論: kura-pasha・line-reservation-aiと同様、今回判明した改定内容はpricing-plan.mdの
  料金プラン設計や「LINE利用料は事業者負担」という前提を見直す必要があるレベルの影響ではない
  と判断する。

## 未検証・要フォローアップ

- 一次情報未確認である点はline-reservation-ai・kura-pashaと同じ留保。実LINE公式アカウント
  開設(オーナー承認待ち)の直前に、人手または別ネットワーク経路での最終確認が必要。
- 事業者が本サービス以外の用途(集客告知・キャンペーン配信等)で同じLINE公式アカウントを
  併用する場合、合算通数が増えて影響を受ける可能性はゼロではない(line-reservation-ai同節と
  同じ留保)。
- 繁忙期対応プランの月150回上限は市場調査ベースの仮置き(pricing-plan.md「未検証の仮説」節)
  であり、実運用データで想定を上回る利用が生じた場合は本ファイルの見積もりも再検証が必要。

## 追記(2026-10-30 UTC定例更新): 「応答メッセージは通数カウント対象外」の確認による見積もりの上書き

- 上記「本ventureの利用量見積もり」は、completion_report/care_guide/history_row・上限接近
  通知の全てを「配信」通数としてカウントする前提で月600通(繁忙期対応プラン上限時)と概算
  していたが、この前提自体を再確認する必要があると判断し、WebSearch経由でLINE公式ヘルプ
  (lycbiz.com)の二次情報を確認した(一次情報への直接アクセスは本エージェントの実行環境では
  依然egressポリシーにより不可、上記「一次情報未確認」の留保は解消していない)。
- 確認した二次情報によれば、公式ヘルプは課金・無料通数カウントの対象を明確に分けており、
  **Messaging APIのReply API(応答メッセージ)は、Push・Multicast・Broadcast・Narrowcast API
  による「メッセージ配信」とは別扱いで、課金対象外・無料メッセージ通数のカウント対象外**
  とされている(チャットの送受信・あいさつメッセージも同様に対象外)。
- prototype/cloud_function_webhook.pyを確認した結果、completion_report/care_guide/
  history_row・上限接近通知・プラン変更案内・決済関連の返信はいずれも`reply_token`を使った
  `reply_client.reply()`(`_reply_with_retry()`経由)のみで送信されており、Push/Multicast/
  Broadcast/Narrowcast APIの呼び出しは本venture内で唯一
  `deletion-candidate-final-confirmation-scheduler-design.md`の月次バッチ
  (`run_due_deletion_candidate_final_confirmations`、連絡可能〈フォロー中〉ユーザーのみ
  LINE_PUSH経路)に限られる(`test_deletion_candidate_final_confirmation.py`の
  `test_following_user_routes_to_line_push`で確認)。
- したがって、本venture最大の利用量ドライバーである生成完了報告の返信(月8〜600通規模)は
  **通数カウント自体の対象外**であり、2026年10月の料金改定(スタンダードプラン追加配信の
  2段階体系化)は上記「影響評価」で結論した「無料枠の2%程度で影響なし」よりもさらに
  踏み込んで、**そもそもこの主要フローには一切関係しない**と訂正する。
- 唯一の実配信(Push)経路である削除候補最終確認の月次バッチは、月次・連絡可能な対象者のみ
  という低頻度・低件数であり、無料枠(30,000通/月)に対して無視できる規模であることに
  変わりはない(影響評価の結論自体は変更なし、根拠が強化された)。
- この訂正はcourse-set-pasha・kura-pasha・line-reservation-aiの各`line-price-revision-
  2026-check.md`にも同様に当てはまる可能性が高い(いずれもWebhook受信→即時返信型の設計)が、
  各venture側のコード・設計文書で実際にPush API呼び出しが無いこと(本ventureと同様の
  確認)を個別に行う必要があるため、本訂正は本venture内に限定し、他ventureへの横展開は
  次のステップ候補として残す。

## 次のステップ候補

- 上記の「応答メッセージは通数カウント対象外」という訂正について、course-set-pasha・
  kura-pasha・line-reservation-aiの各line-price-revision-2026-check.mdへの横展開
  (各venture側でPush API呼び出しの有無を個別確認する必要がある、新規の次回候補)。
- course-set-pashaへの同種確認の横展開(本ファイルと同じ検討が未実施のまま残っている)。
- 実LINE公式アカウント開設の直前に一次情報での最終確認(オーナー承認待ちのため現時点では
  着手しない)。
