# ConversationFlowStateMachine構築ヘルパー設計(フェーズ続き187)

作成日: 2026-09-04(フェーズ続き187)

## 1. 背景・対応する残課題

checkout-session-plan-selection-design.md「残課題」・monthly-booking-limit-notification-
design.md 6節に残っていた、`store_profile_store.resolve_monthly_booking_limit()`
(フェーズ続き182)が求めた`monthly_booking_limit`の値を、実際に`ConversationFlowStateMachine`
(engine.py)のコンストラクタへ渡す配線が存在しないギャップに対応する。

`resolve_monthly_booking_limit()`のdocstringは、この配線が実装されない理由を「呼び出し元
自体(実際にConversationFlowStateMachineを構築している箇所)は、実Firestore接続後にどの
タイミングで構築するか(会話イベントごとに毎回構築するか、店舗単位でキャッシュするか)が
未確定なため」としていた。本フェーズはこの「未確定」のうち、**構築時に渡す引数の組み立て**
という限定された範囲を切り出して解消する。**会話状態(`_states`辞書)を呼び出しの合間に
どう永続化・復元するか(Firestoreドキュメントとの間でどうhydrate/dehydrateするか)は、
本フェーズの対象外のまま次回以降の課題として残す**(cloud_function_process_event.pyの
`ConversationEventProcessor`docstring・`handle_process_conversation_event()`docstringが
既に明記している、実Firestore接続後の別課題)。

## 2. 切り出す理由

`monthly_booking_limit`の値は「店舗が現在契約しているプラン」という、会話状態とは独立した
店舗プロフィール側の値であり、会話状態の永続化方式(毎回新規構築かキャッシュか)がどちらに
決まっても、コンストラクタへ渡すべき値の求め方自体は変わらない。すなわち:

- 会話イベントごとに毎回新規構築する設計を採る場合: 毎回`resolve_monthly_booking_limit()`を
  呼んで最新のプラン上限を渡す(プラン変更が即座に反映される利点がある)。
- 店舗単位でインスタンスをキャッシュする設計を採る場合: 初回構築時に
  `resolve_monthly_booking_limit()`を呼んで渡し、以降はプラン変更Webhook受信時に
  `ConversationFlowStateMachine`側へ値を更新する別の配線(未設計)が必要になる。

いずれの場合も「`resolve_monthly_booking_limit()`を呼んでコンストラクタへ渡す」という最小
単位の処理自体は共通であり、キャッシュ有無の設計判断を待たずに先に切り出して実装・テスト
できる。

## 3. 決定: 構築ヘルパー関数を新設

`prototype/store_profile_store.py`に`build_conversation_flow_state_machine_for_store()`を
新設する。`resolve_existing_stripe_customer_id()`・`make_resolve_store_id_by_customer()`と
同じ「店舗プロフィールストアとengine.py側との結線点を切り出すヘルパー」という位置づけを
踏襲する。

```python
def build_conversation_flow_state_machine_for_store(
    store_id: str,
    store: StoreProfileStoreProtocol,
    *,
    slots=None,
    consolidator=None,
    logs=None,
    record_store=None,
) -> ConversationFlowStateMachine:
    monthly_booking_limit = resolve_monthly_booking_limit(store_id, store)
    return ConversationFlowStateMachine(
        slots if slots is not None else BookingSlotManager(),
        consolidator if consolidator is not None else EscalationConsolidator(),
        logs=logs,
        record_store=record_store,
        monthly_booking_limit=monthly_booking_limit,
    )
```

- `slots`・`consolidator`は未指定時それぞれ新規`BookingSlotManager()`・
  `EscalationConsolidator()`を生成する(呼び出し側が既存インスタンスを再利用したい場合
  〈例: テストで内部状態を検査したい〉は明示的に渡せる、`ConversationEventProcessor`の
  `booking_slots`/`consolidator`引数と同様の任意上書きパターン)。
- `logs`・`record_store`はそのまま`ConversationFlowStateMachine`へ透過する(未指定時は
  従来通り機能しない後方互換)。
- `store_profile_store.py`が`engine.py`をインポートする形になる(逆方向の依存は無い、
  循環インポートなし)。`resolve_monthly_booking_limit()`・
  `resolve_existing_stripe_customer_id()`と同じファイルに置くことで、店舗プロフィール
  ストアに関する「結線ヘルパー」を1箇所に集約する既存の整理方針を維持する。

## 4. 本フェーズでは対応しない範囲(引き続き残る課題)

- 実際にこの関数をどこから(Cloud Function Bの初回リクエスト時か、店舗単位のキャッシュ層か)
  呼ぶ配線自体は、cloud_function_process_event.pyの`ConversationEventProcessor`
  docstringが明記する「1呼び出し=1店舗分のprocessorを呼び出し元が既に構築済み」という
  前提の実体(実Firestore接続後にどう構築するか)が未確定なままのため、次回以降の課題
  として残る。
- (解消済み 2026-09-04 03:00 UTC・フェーズ続き188: 会話状態(`_states`)自体を
  Firestoreドキュメントとの間でhydrate/dehydrateする方式は、
  conversation-state-persistence-design.mdで`export_state_for_persistence()`/
  `import_state_from_persistence()`として実装した。ただしこれを実際に「どこから」
  呼ぶか〈上記と同じ、キャッシュ有無の判断待ち〉は同ドキュメント4節に次回以降の
  課題として引き続き残る)
- プラン変更(アップグレード/ダウングレード)がキャッシュ済みインスタンスへどう反映される
  かの検討は、2節で述べた「店舗単位でキャッシュする設計を採る場合」の派生課題として、
  キャッシュ方式自体が決まった後にあらためて設計する。

## 5. テスト

`prototype/test_store_profile_store.py`に追加(詳細はREADME.md本フェーズ参照)。
- プラン未設定(トライアル中、`store.get_plan()`がNone)の店舗では
  `monthly_booking_limit=None`のまま`ConversationFlowStateMachine`が構築されること
  (機能無効の後方互換動作)。
- プラン設定済みの店舗では、`PLAN_MONTHLY_BOOKING_LIMITS`に対応する上限値が
  `monthly_booking_limit`として渡されること(3プランそれぞれ)。
- `slots`・`consolidator`を明示的に渡した場合、新規生成されず渡したインスタンスが
  そのまま使われること。
- 存在しない`store_id`(空文字列)を渡した場合、`resolve_monthly_booking_limit()`と
  同じ`ValueError`が送出されること。
