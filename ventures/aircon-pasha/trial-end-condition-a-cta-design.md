# トライアル終了通知・条件A(生成回数到達)の実装

作成日: 2026-08-28(フェーズ137)

README.mdフェーズ136の申し送り「`trial_generation_count`の実集計配線」に対応する。
trial-end-notification-design.md「5. 実装への影響メモ」で予告されていた、月次カウンタとは
別立てのトライアル専用生成回数カウンタを実装し、あわせて同ドキュメント2節(A)(生成回数10回
到達)の検知・通知送信を`process_memo_event()`内に配線した。course-set-pashaの
trial-end-condition-a-implementation-design.md(フェーズ113)と同じ実装方針を踏襲しつつ、
本venture固有の差分(CTAがLIFF URLではなくpostbackボタンである点)への対応を新たに設計した。

## 1. トライアル専用生成回数カウンタ

course-set-pashaは`usage_counter`(月次カウンタと同じProtocol)にincrement_trial_generation_
count()を追加したが、本ventureは`user_profile`側に`trial_start_at`等の非月次フィールドを
既に持っているため(フェーズ134)、同じ位置づけで`UserProfile.trial_generation_count`
(既定値0)を追加し、`UserProfileStoreProtocol.increment_trial_generation_count(user_id) -> int`
(インクリメント後の値を返す、未知のuser_idには何もせず0を返す)を実装した
(`user_id_linking.py`)。月次カウンタ(`usage_counter`)とは別立てで、月をまたいでも
リセットされない。

## 2. 条件Aの検知・通知送信

`process_memo_event()`のstatus=="generated"かつprofile_storeが渡された経路で、
`profile.upgraded_at is None`(有料転換前)の場合のみ毎回インクリメントする
(course-set-pashaの`get_upgraded_at(user_id) is None`ガードと同じ考え方)。インクリメント後の
値がTRIAL_GENERATION_LIMIT(10、pricing-plan.md「無料トライアル条件(仮)」の「生成10回到達」
と一致)ちょうど、かつ`profile.trial_end_notified_at is None`(未通知)の場合のみ、通知文を
返信本文に追記し`set_trial_end_notified_at()`を書き込む。(B)期間到達側
(`trial_end_scheduler.select_due_trial_end_notifications()`)は`trial_end_notified_at is not
None`のユーザーを対象外にする設計に既になっているため、(A)側が先に書き込めば(B)側の日次
スケジューラは自動的にそのユーザーをスキップする。逆に(B)側が先に発火した場合も、(A)側は
`trial_end_notified_at is None`チェックで送信をスキップする。どちらが先でも「いずれか早い方で
1回のみ」(trial-end-notification-design.md 2節)が保たれる(course-set-pashaと同じ整合設計)。

## 3. 本venture固有の課題: CTAボタンをどう返信に含めるか

course-set-pashaの条件A通知はLIFF URL(プレーンテキストのhttpsリンク)を文中にそのまま
埋め込めるため、`format_trial_end_notification_message()`はプレーンテキストのみで完結した。
一方、本ventureのCTA(checkout-initiation-flow-design.mdで確定した「有料プランへ進む」)は
LINEのpostbackアクションボタンでのみ実現でき、(B)期間到達側
(`trial_end_scheduler.build_trial_end_notification_flex_message()`)はPush Message APIで
Flex Message(ボタン付きbubble)として送信することでこれを実現している。しかし(A)側は
Reply APIへの返信本文への「便乗」(追加のPush API呼び出し・課金を発生させない方針、2節)で
あり、既存の`reply_text`はプレーン文字列のため、そのままではボタンを表現できないという
本venture固有のギャップがあった。

検討した選択肢:
1. **(A)側もFlex Messageに切り替える**: 返信本文全体をテキストからFlex Messageへ変更する
   ことになり、format_reply_text()が組み立てる完了報告・お手入れ案内・セルフチェック案内・
   利用回数通知などすべてのテキスト便乗ロジックをFlex Message化する必要が生じ、影響範囲が
   過大。却下。
2. **postbackボタンを諦め、案内のみのテキストにする**: 「次回ログイン時にボタンをお送り
   します」等の弱いCTAになり、実質的に(B)側の日次スケジューラ到達(最大14日後)まで
   有料転換の導線が失われる。却下。
3. **LINE Messaging APIのquickReply機能を使う(採用)**: quickReplyはメッセージタイプを
   問わず(テキストメッセージにも)添付できる最大13個のボタン領域で、各ボタンはpostback
   アクションを持てる。本文自体はプレーンテキストのまま、同じ`START_CHECKOUT_POSTBACK_DATA`
   を持つボタンを1個だけ添付すれば、Flex Message化せずに(B)側と同じ`process_postback_event()`
   をそのまま再利用できる。

3を採用し、`ReplyClient.reply()`に`quick_reply: Optional[QuickReplyButton] = None`
(キーワード専用引数、既定None)を追加した。既存の呼び出し元・テスト用スタブ
(`reply(self, reply_token, message_text)`という2引数シグネチャのみを実装するもの)を
一切変更せずに済むよう、`_reply_with_retry()`はquick_replyがNoneのときはキーワード引数
自体を渡さない(`**({"quick_reply": quick_reply} if quick_reply is not None else {})`)。
`InMemoryReplyClient.sent`の既存2要素タプル形式(`(reply_token, message_text)`)も変更せず、
quick_replyは別属性`quick_replies_sent`(indexが`sent`と対応)に記録する形にし、既存テストの
アサーションを一切壊さないようにした。

## 4. 対象外にした範囲

- trial-end-notification-design.md「4. トライアル終了後(未アップグレード)の挙動」の
  「生成一時停止」実装は、本フェーズでも引き続き対象外(course-set-pashaのフェーズ114相当は
  本venture未着手のまま次回以降の課題として残る)。
- 実LINE Messaging API接続(quickReplyの実際のJSON形式でのpostback送信含む)はオーナー承認
  待ちの範囲のまま変更なし。

## テスト

`prototype/test_cloud_function_webhook.py`に`ProcessMemoEventTrialEndConditionATest`を新設し、
以下を確認した(venture全体223件全件パス、schema/validate_test_cases.pyも9件全件パス)。

1. 10回目の生成完了時、返信本文にトライアル終了通知文言(「無料トライアル、お疲れさまでした」)が
   追記されること。
2. 10回目の生成完了時、`quick_reply`として`QuickReplyButton(label=TRIAL_END_BUTTON_LABEL,
   postback_data=START_CHECKOUT_POSTBACK_DATA)`が`reply_client`へ渡ること。
3. 10回目の生成完了時、`set_trial_end_notified_at()`が呼ばれ`trial_end_notified_at`が
   非Noneになること。
4. 9回目まではまだ通知文言・quick_replyが付かないこと。
5. 既に`trial_end_notified_at`が設定済み((B)側で先に送信済み等)の場合、10回到達時でも
   二重送信しないこと。
6. 既に有料転換済み(`upgraded_at`設定済み)の場合、カウンタ自体がインクリメントされず
   通知も送信されないこと(既存の`upgraded_at is None`ガードにより、この経路自体が
   実行されない)。
