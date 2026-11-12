# process_message_event() のWebhook即時ACK・2関数構成への翻案設計

## 背景

webhook-sync-reply-timeout-root-cause-review.md(フェーズ続き297)が次回候補として
積み残した「本ventureの`process_memo_event()`を、line-reservation-ai準拠の2関数構成
(A: 署名検証・idempotency・enqueue・即時200、B: LLM呼び出し・後処理・push)に翻案する
設計ドキュメント」に対応する。course-set-pashaのprocess-memo-event-async-split-design.md
(フェーズ370、フェーズ371・372で実装済み)と同じ「Webhook即時ACK + Cloud Tasks非同期処理 +
Push API応答」パターンを、本venture固有の分岐構造に合わせて翻案する。実装・デプロイは
実GCPプロジェクト作成(オーナー承認待ち、pending-approval.md参照)後の課題として残し、
本書は机上設計のみ行う。

## 分岐境界の再確認: root-cause-reviewの指摘は`process_memo_event()`自身に限定される

webhook-sync-reply-timeout-root-cause-review.md 1節は「本ventureには`process_memo_event()`
内にLLM呼び出しを経ない軽量経路が存在しない」と結論づけたが、これは`process_memo_event()`
**自身**の内部分岐((a)(b)(c)の文脈注入経路・(d)通常生成経路のいずれも
`_generate_with_api_retry(llm_call, ...)`を経由する)についての指摘であり、
`process_memo_event()`の呼び出し元である`process_message_event()`(1427行目、message
イベントの実際の入口)まで範囲を広げて確認すると、LLM呼び出しを一切経ない同期的な
軽量経路が複数存在することが判明した。course-set-pashaのFAQ固定応答(経路2、文字列
一致のみ)と同じ位置づけの経路であり、本venture側の2関数構成でも温存すべきである。

`process_message_event()`(1427〜1605行目)を確認した結果、以下の分岐が判明した。

1. `message.type != "text"`(画像単体送信等): `process_memo_event()`に委譲されるが、
   そちら側も即座に`handled=False`を返すのみで、LLM呼び出し・返信・状態書き込みの
   いずれも発生しない(既存の無反応挙動)。
2. 連携済みユーザー(`user_profile_store.get_workshop_id(user_id)`が設定済み)の場合:
   a. `_maybe_handle_owner_faq_command()`(契約者本人からの「FAQ」「Q1」〜「Q8」コマンド
      判定、owner-faq-routing-design.md)が一致 → LLM呼び出しなしでその場で返信。
   b. 上記不一致かつ`chatbot_intent_classifier`接続時: `_classify_chatbot_intent_with_
      retry()`自体がLLM呼び出しであるため、ここから先(分類結果に応じた
      `route_chatbot_intent()`委譲、または`memo_processing_request`判定時の
      `process_memo_event()`呼び出し)は全てLLM呼び出しを経由する。
   c. `chatbot_intent_classifier`未接続時(既存呼び出し元、後方互換): 分類自体を行わず
      `process_memo_event()`へ直接委譲するため、最初の1行目からLLM呼び出しを経由する。
3. 未連携ユーザー(`workshop_id`未設定、または`user_id`自体が無い)の場合:
   `create_workshop_from_linking_code()`・(失敗時のみ)`add_member_from_invite_code()`
   による連携コード・招待コード解決(いずれも辞書引き・Firestore照合のみでLLM呼び出し
   なし) → LINKING_SUCCESS_MESSAGE/INVITE_JOIN_SUCCESS_MESSAGE/MEMBER_LIMIT_REACHED_
   MESSAGE/LINKING_REQUIRED_MESSAGEのいずれかをその場で返信。
4. `linking_enabled`が偽(`user_profile_store`・`workshop_store`・`linking_store`の
   いずれかが未接続、後方互換フォールバック)の場合: 2.の判定自体を行わず
   `process_memo_event()`へ直接委譲するため、これも最初の1行目からLLM呼び出しを経由する。

結論: **1.・2a.・3.の3経路のみ同期reply(LLM呼び出しなし)、2b.・2c.・4.はまとめて
非同期push**という境界でFunction A/Bを設計する。1.・2a.・3.はいずれも「文字列比較・
辞書引き・Firestore単純照合」のみで完結し、LINEの2秒タイムアウト内に収まる見込みが高い
(course-set-pashaのFAQ固定応答と同じ理由)。2a.の判定自体はLLM呼び出し前に行われるため、
Function A側で2a.を評価してもFunction Bへ回す経路のレイテンシ特性には影響しない。

## 採用方式

```
LINE Platform
   │ Webhook (event)
   ▼
[Cloud Function A: receive_webhook (既存のエントリポイント)]
   - 署名検証(既存)
   - webhookEventId べき等性チェック(line-webhook-event-id-idempotency-design.md
     フェーズ286実装済み、そのまま流用。ただし「処理済みマーク」のタイミングは
     後述の「べき等性の再配置」節で変更する)
   - message.type!="text" → 無反応(既存通り、何もしない)
   - message.type=="text"かつ`linking_enabled`(3ストア接続済み)の場合:
     - `user_profile_store.get_workshop_id(user_id)`を読み、
       - 連携済み: `_maybe_handle_owner_faq_command()`を評価。一致すれば
         reply APIでその場に返信して終了。不一致ならイベント本体
         (userId・message本文・webhookEventId、replyTokenは使わない)を
         Cloud Tasksキューへenqueueし、200 OKを即返却する(chatbot_intent_classifier
         が接続されているか否かに関わらず、分類自体をFunction B側に委ねる)。
       - 未連携: `create_workshop_from_linking_code()`→(失敗時のみ)
         `add_member_from_invite_code()`を評価し、結果に応じた案内文言を
         reply APIでその場に返信して終了(process_memo_event()へは一切進めない、
         既存方針を維持)。
   - message.type=="text"かつ`linking_enabled`が偽(後方互換フォールバック)の場合:
     イベント本体をCloud Tasksキューへenqueueし、200 OKを即返却する
     (この場合は最初の1行目からLLM呼び出しを経由するため、2a./3.相当の
     軽量判定自体を行う前提〈3ストア接続〉が成立しないため)。
   - follow/unfollow/postbackイベントは既存通り同期処理のまま(いずれもLLM呼び出しを
     含まない。process_follow_event()/process_unfollow_event()/process_postback_event()
     は変更不要、postback系にllm_call呼び出しが無いことを本フェーズでコード確認済み)。
   │
   ▼ (Cloud Tasks経由で非同期起動)
[Cloud Function B: process_message_event_async (新設)]
   - `chatbot_intent_classifier`接続時: `_classify_chatbot_intent_with_retry()`で
     意図分類 → `memo_processing_request`以外は`route_chatbot_intent()`相当の処理
     (`other_needs_human`時の`escalation_push_client`呼び出しを含む)を行い、
     結果をpush APIで送信。
   - `memo_processing_request`と判定された場合(分類失敗によるNoneフォールバック・
     `chatbot_intent_classifier`未接続時を含む): `process_memo_event()`本体
     (経路(a)(b)(c)(d)の全て、usage_counter判定・LLM呼び出し・workshop_store書き込み・
     quick_reply付記を含む既存ロジック全体)をそのまま呼び出し、結果をpush APIで送信。
```

## 既存コードへの影響

- `process_message_event()`・`process_memo_event()`本体のロジック(各経路の分岐・
  後処理・リトライ方針)は変更不要。Function Bからの呼び出され方(`reply_client`の
  代わりに`push_client`を渡す形)に差し替えるだけで流用できる見込み(course-set-pasha
  フェーズ371の`PushBackedReplyClient`パターンと同じ、`ReplyClient`プロトコルを
  満たすpush_client用アダプタを新設するだけで両関数とも無変更のまま流用できる)。
  `event`に`replyToken`キーが無くても動作することは、Cloud Tasks経由では
  `replyToken`が伝播されない前提のため、course-set-pashaフェーズ371の確認結果
  (`event`からの`replyToken`キー欠落時の動作検証)がそのまま当てはまる。
- `dispatch_webhook_events()`は、messageイベントを「2a./3.相当(同期reply)」と
  「それ以外(非同期キュー行き)」に振り分ける前処理を追加する必要がある。
  course-set-pashaのFAQ振り分け(文字列比較のみ)と異なり、本venture側の振り分けは
  `user_profile_store.get_workshop_id()`等のストア読み取りを伴うため、振り分け判定
  自体にFirestore読み取りが発生する点が差分となる(ただし読み取りのみで書き込みは
  発生せず、LLM呼び出しと比較して無視できる遅延と判断する)。
- Cloud Tasksのタスク名導出は`f"kura-pasha-event-{webhook_event_id}"`とし、
  line-reservation-ai/webhook-async-processing-design.md「二重処理対策」節・
  course-set-pashaの`make_memo_task_name()`と同じ構造(Cloud Tasks側の重複排除に
  依拠)を流用する。

## べき等性の再配置(root-cause-review 2節が指摘した課題への回答)

webhook-sync-reply-timeout-root-cause-review.md 2節は「`workshop_store`への書き込み
(trial_end_notified_at・set_specified_retention_member_name・set_first_generation_
notice_sent等)をFunction A/Bのどちらで行うか」を主要な検討事項として残していた。
本設計では**これらの書き込みは個別に分割せず、いずれも`process_memo_event()`本体
(または`route_chatbot_intent()`相当処理)としてFunction B内で一括して行う**(2b./2c.
相当の経路が丸ごとFunction Bへ移るため、内部の書き込み箇所ごとに分割する必要はない)。

二重課金・二重カウント対策は、既存のline_webhook_event_id_storeによる
べき等性チェック(フェーズ286)の「記録タイミング」を次のように再配置することで、
現行の保証を維持する。

- 現行: `dispatch_webhook_events()`が各ハンドラ(同期呼び出し)の**直後**に
  `mark_processed()`を呼ぶ(ハンドラ内例外時に未処理のまま処理済み扱いになる事故を
  避ける設計、フェーズ286)。
- 翻案後: Function Aは2b./2c./4.相当のイベントをenqueueする**前**に
  `has_processed(webhook_event_id)`を確認し(既に処理済みならenqueueせず200のみ
  返す)、`mark_processed()`自体はFunction B側が`process_message_event_async()`の
  呼び出しに**成功した後**(push送信の成否は問わず、ハンドラ呼び出し自体が例外を
  投げずに完了した後)に呼ぶ。これはフェーズ286の「ハンドラ呼び出し後にmark_
  processed()」という設計思想を、ハンドラの実行場所がFunction Bに移っただけで
  そのまま維持したものであり、Cloud Tasks自体のタスク名重複排除(上記)と合わせて
  二重の防御層になる(line-reservation-aiの「二重処理対策」節と同じ二層構成)。
- 2a./3.相当(Function A内で同期処理する軽量経路)は、既存通りFunction A内で
  ハンドラ呼び出し直後に`mark_processed()`を呼ぶ(変更なし)。

この再配置により、`process_generation_request()`の呼び出し(usage_counter加算・
trial_end_notified_at書き込みを含む)自体は「Function B内で1回だけ」という既存の
保証がそのまま成立し、A/Bどちらで書き込むかという論点自体を解消できる
(root-cause-review 2節の懸念は、書き込み箇所を分割せずFunction Bへ丸ごと移す
という本設計の選択によって生じない)。

## 残課題・次回候補

- (1) Function Bの実装(`process_message_event_async()`・push_client用`ReplyClient`
  アダプタ、`prototype/cloud_function_webhook.py`)。course-set-pashaフェーズ371の
  `PushBackedReplyClient`をそのまま流用できる見込み。
- (2) `dispatch_webhook_events()`への2a./3.相当(同期)と2b./2c./4.相当(非同期
  キュー行き)の振り分け前処理の実コード反映。course-set-pashaフェーズ372の
  `TaskQueueClient`/`InMemoryTaskQueueClient`/`make_memo_task_name()`と同じ構造を
  `kura-pasha-event-`プレフィックスで流用する。振り分け判定自体に`user_profile_
  store`読み取りを伴う点が本venture固有の差分(上記「既存コードへの影響」節参照)。
- (3) aircon-pashaの同種部分への横展開は、course-set-pasha・kura-pasha・
  line-reservation-aiの状況を踏まえて別途検討する(aircon-pashaはpostbackアクション
  中心でFAQキーワード一致方式を採用していない可能性があるため、横展開前に
  aircon-pasha側の経路構造を個別確認する必要がある、webhook-sync-reply-timeout-
  root-cause-review.md 4節の既存注記を維持)。
- (4) Cloud Tasksキュー・Function Bの実デプロイは実GCPプロジェクト作成
  (オーナー承認待ち、pending-approval.md参照)後の課題として残る。Cloud Tasks
  自体はスタブ(InMemoryキュー相当)で机上検証可能なため、(1)(2)の設計確定後は
  実GCPプロジェクト作成の承認を待たずに着手できる見込み(line_webhook_event_id_store
  同様、Protocol越しの差し替え設計とすることで検証を先行させる、webhook-sync-reply-
  timeout-root-cause-review.md 4節の既存見込みを維持)。

最終更新: 2026-11-12 21:00 UTC(新規作成。webhook-sync-reply-timeout-root-cause-review.md
フェーズ続き297の次回候補に対応。root-cause-reviewが「`process_memo_event()`自身には
軽量経路が存在しない」と指摘した範囲を、呼び出し元の`process_message_event()`まで
広げて確認した結果、課題同期reply可能な3経路(非テキスト無反応・owner FAQコマンド・
連携コード/招待コード解決)が実在することを新たに確認し、course-set-pasha型の
「同期経路と非同期経路の2分岐」をFunction A/Bの境界として採用した。root-cause-review
2節が残していた「workshop_store書き込みをA/Bどちらで行うか」という論点は、書き込みを
分割せずFunction Bへ丸ごと移す設計を採ることで解消し、既存のline_webhook_event_id_store
べき等性チェックの記録タイミングをFunction B呼び出し後に再配置することで二重課金・
二重カウント対策を維持する設計とした。実コード反映・実デプロイは次回候補として
積み残す)
