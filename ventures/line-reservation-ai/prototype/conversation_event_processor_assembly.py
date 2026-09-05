#!/usr/bin/env python3
"""conversation-event-processor-assembly-design.md 4節の残課題(フェーズ続き195)。

business_hours_assembly.build_availability_searcher_for_store()(フェーズ続き194)で
searcher組み立てが揃ったことを受け、design 4節に残っていた最上位の組み立て関数
build_conversation_event_processor_for_payload()を実装する。design時点では
「push_client・conversation_state_store等の実クラウド接続に依存する引数がある間は
実装しても動かせないため優先度は低い」としていたが、他venture(aircon-pasha・
course-set-pashaのportal_link_provider配線等)と同じDI(依存性注入)パターンで
InMemory実装を注入すれば、実クラウド接続なしでも組み立てロジック自体は机上検証できる
と判断し、本フェーズで実装する。実LINE Messaging API・実Firestore接続自体は引き続き
オーナー承認待ちのまま変わらない。

`store`引数はStoreSettingsStoreProtocol(store_profile_store.StoreProfileStoreProtocolを
継承)1つで、営業時間raw値(business_hours_assembly向け)・menu_durations/
store_faq_info/owner_user_id(store_profile_store向け)の両方を賄う。design時点の
スケッチ`build_conversation_event_processor_for_payload(payload, store, push_client,
...)`通り、`store`と`settings_store`を別引数にしない(実Firestoreでも
`stores/{storeId}`という単一ドキュメントである想定のため、store_settings_save_flow.py
がStoreSettingsStoreProtocolをStoreProfileStoreProtocolのサブタイプとして設計している
のと同じ考え方)。

`get_process_conversation_event_runtime_dependencies()`/`main(request)`
(フェーズ続き197): フェーズ続き196「残る課題」(a)に残っていた、Cloud Functions上で
`process_conversation_event_from_payload()`を実際に呼び出すHTTPハンドラ本体を実装した。
checkout_session.py/stripe_webhook_entry_point.pyと同じ「本体は依存注入でテスト可能、
`main(request)`だけが実`functions_framework`リクエストオブジェクトを扱う薄い配線」構成を
踏襲する。実LINE Messaging API・実LLM API・実Firestore接続自体(オーナー承認待ち)は
`InMemoryLinePushClient`・`_llm_call_not_implemented`・`InMemoryStoreSettingsStore`の
プレースホルダのまま変わらない。
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from datetime import datetime, timezone  # noqa: E402
from typing import Callable  # noqa: E402

from business_hours_assembly import build_availability_searcher_for_store  # noqa: E402
from cloud_function_process_event import (  # noqa: E402
    ConfirmedReplyRecorder,
    ConversationEventProcessor,
    ConversationStateStoreProtocol,
    InMemoryLinePushClient,
    LinePushClient,
    MissingDestinationError,
    OwnerFollowStatusStoreProtocol,
    ProcessEventResult,
    handle_process_conversation_event,
    resolve_store_id_from_destination,
)
from engine import NotificationLogAggregator  # noqa: E402
from store_profile_store import build_conversation_flow_state_machine_for_store  # noqa: E402
from store_settings_save_flow import (  # noqa: E402
    InMemoryStoreSettingsStore,
    StoreSettingsStoreProtocol,
)


def build_conversation_event_processor_for_payload(
    payload: dict,
    store: StoreSettingsStoreProtocol,
    push_client: LinePushClient,
    *,
    conversation_state_store: Optional[ConversationStateStoreProtocol] = None,
    confirmed_reply_recorder: Optional[ConfirmedReplyRecorder] = None,
    store_profile: Optional[OwnerFollowStatusStoreProtocol] = None,
) -> ConversationEventProcessor:
    """Cloud Tasksからデキューされたペイロード1件から、1店舗分の
    ConversationEventProcessorを組み立てる(handle_process_conversation_event()の
    `processor`引数を用意する呼び出し元)。

    手順:
    1. resolve_store_id_from_destination(payload)でstore_idを解決する
       (store-id-resolution-and-owner-identity-design.md準拠)。
    2. build_conversation_flow_state_machine_for_store()でConversationFlowStateMachine
       (フェーズ続き187)を、build_availability_searcher_for_store()でAvailabilitySearcher
       (フェーズ続き194)をそれぞれ組み立てる。
    3. booking_slots・consolidatorはflow内部で生成されたインスタンス(flow._slots/
       flow._consolidator)をそのまま共有する(cloud_function_process_event._demo()と
       同じ考え方)。
    4. logsはflow・processor双方に同一のNotificationLogAggregatorを渡し、
       booking_conflict等のシステム内部イベントがログへ記録されるようにする
       (system-event-log-gap-fix.md準拠)。
    5. menu_durations・store_faq_info・owner_user_idはstore(StoreProfileStoreProtocol
       部分)から読み出す。未設定の店舗はmenu_durations/store_faq_infoが空dict、
       owner_user_idがNoneになる(各getterの既定動作、store_profile_store.py参照)。

    push_client・conversation_state_store・confirmed_reply_recorder・store_profileは
    実クラウド接続(実LINE Messaging API・実Firestore)に依存するため、呼び出し元が
    DIで渡す。未指定(None)の引数は、ConversationEventProcessor自身の既存の
    後方互換動作(それぞれ「hydrate/dehydrateしない」「記録しない」「更新しない」)に
    委ねる。
    """
    store_id = resolve_store_id_from_destination(payload)
    logs = NotificationLogAggregator()
    flow = build_conversation_flow_state_machine_for_store(store_id, store, logs=logs)
    searcher = build_availability_searcher_for_store(store_id, store)

    return ConversationEventProcessor(
        flow=flow,
        searcher=searcher,
        booking_slots=flow._slots,
        consolidator=flow._consolidator,
        logs=logs,
        push_client=push_client,
        store_id=store_id,
        menu_durations=store.get_menu_durations(store_id),
        store_faq_info=store.get_store_faq_info(store_id),
        confirmed_reply_recorder=confirmed_reply_recorder,
        owner_user_id=store.get_owner_user_id(store_id),
        store_profile=store_profile,
        conversation_state_store=conversation_state_store,
    )


def process_conversation_event_from_payload(
    payload: dict,
    store: StoreSettingsStoreProtocol,
    push_client: LinePushClient,
    llm_call: Callable[[], dict],
    now: datetime,
    *,
    tone: str = "standard",
    conversation_state_store: ConversationStateStoreProtocol | None = None,
    confirmed_reply_recorder: ConfirmedReplyRecorder | None = None,
    store_profile: OwnerFollowStatusStoreProtocol | None = None,
) -> ProcessEventResult:
    """Cloud Function B(process_conversation_event)の実エントリポイント本体。

    design 4節に残っていた最後の配線ギャップ(フェーズ続き196)。
    `build_conversation_event_processor_for_payload()`(processor組み立て)と
    `handle_process_conversation_event()`(組み立て済みprocessorでの実処理)は
    フェーズ続き195までに個別には実装済みだったが、Cloud Tasksからデキューされた
    1件のpayloadを受け取ってから両者を順に呼び出す配線本体が存在しなかった。

    `handle_process_conversation_event()`は`dispatch_process_event()`が送出した例外を
    status_code=500へ正規化するが、これは処理対象を正しく組み立てられた後の実行時エラー
    (リトライすれば直る可能性がある)を想定したもの。一方、組み立て段階
    (`build_conversation_event_processor_for_payload()`)で送出される
    `MissingDestinationError`(payloadにdestinationが無い)・`ValueError`
    (destinationが解決するstore_idが未オンボーディングでbusiness_hours_raw未設定)は
    いずれもpayload自体かstore設定の不備であり、Cloud Tasksに同じpayloadをリトライさせても
    解消しない。これらは400(非リトライ)として区別し、Cloud Function Aが署名検証失敗時に
    401を返すのと同じ「リトライしても無駄なものは専用のステータスで切り分ける」設計方針に
    揃える。

    実際にCloud Functions上のHTTPハンドラ(Cloud Tasksのリクエストボディをパースして
    本関数を呼び出す側)自体は、Cloud Function AのHTTPハンドラ本体(webhook_receiver()の
    呼び出し元)と同様、デプロイ環境確定後の課題として引き続き残る。store・
    conversation_state_store・confirmed_reply_recorder・store_profileの実Firestore実装
    への差し替えも、実GCPプロジェクト作成(オーナー承認待ち)後の課題として残る。
    """
    try:
        processor = build_conversation_event_processor_for_payload(
            payload,
            store,
            push_client,
            conversation_state_store=conversation_state_store,
            confirmed_reply_recorder=confirmed_reply_recorder,
            store_profile=store_profile,
        )
    except MissingDestinationError as exc:
        return ProcessEventResult(status_code=400, detail=f"missing_destination: {exc}")
    except ValueError as exc:
        return ProcessEventResult(status_code=400, detail=f"store_not_onboarded: {exc}")

    return handle_process_conversation_event(payload, processor, llm_call, now, tone)


def _llm_call_not_implemented() -> dict:
    """checkout_session._verify_id_token_not_implementedと同じ位置づけのプレースホルダ。

    実LLM API呼び出しはAPIキー取得・従量課金が発生するためオーナー承認待ち
    (pending-approval.md参照)。恒久的に失敗を返すダミーだと誤って動いているように
    見えてしまうため、呼ばれたら意図的にNotImplementedErrorを送出する。承認後は
    conversation-samples-test-cases.mdのN1〜N4・E1〜E16を実際にClaude API等へ投入する
    実装へ差し替える。
    """
    raise NotImplementedError(
        "llm_call is not implemented yet: pending LLM API key issuance and billing "
        "approval (owner approval required, see pending-approval.md)"
    )


def get_process_conversation_event_runtime_dependencies() -> dict:
    """main()が使う依存の既定値を組み立てる(checkout_session.
    get_checkout_runtime_dependencies()と対称の構成)。

    - `store`: `InMemoryStoreSettingsStore()`を1つ生成する。実運用ではCloud Function A・
      Stripe Webhook側と同一Firestoreの`stores`コレクションを共有する想定だが、本プロセスでは
      別プロセス・別インスタンスとして初期化されるため、店舗設定・会話状態は呼び出しをまたいで
      保持されない(実Firestore接続後に解消される既知の限界、checkout_session側と同種)。
    - `push_client`: `InMemoryLinePushClient()`。実LINE Messaging API接続
      (公式アカウント開設・チャネルアクセストークン発行)はオーナー承認待ちのため、
      承認後に実クライアントへ差し替える。
    - `llm_call`: `_llm_call_not_implemented`。実LLM API接続はオーナー承認待ちのため、
      承認後にスタブを実API呼び出し関数へ差し替える(design「次にやること」参照)。
    - `conversation_state_store`/`confirmed_reply_recorder`/`store_profile`は未指定(None)の
      まま返す。いずれも省略時の後方互換動作(hydrate/dehydrateしない等)に委ねる、実Firestore
      実装への差し替えを待つ課題として残す。
    """
    return {
        "store": InMemoryStoreSettingsStore(),
        "push_client": InMemoryLinePushClient(),
        "llm_call": _llm_call_not_implemented,
    }


def main(request):
    """Cloud FunctionsのHTTPエントリポイント(`functions_framework`想定、Cloud Function B
    `process_conversation_event`のHTTPハンドラ本体)。

    Cloud Tasksのタスクリクエスト(Cloud Function Aがenqueueした1件のLINE webhookイベント
    dict、`destination`付き)をJSONボディとして受け取り、`request.get_json()`で
    パースした上で`process_conversation_event_from_payload()`に委譲する
    (checkout_session.main()・stripe_webhook_entry_point.main()と対称の「本体は依存注入で
    テスト可能、main(request)だけが実functions_frameworkリクエストオブジェクトを扱う薄い
    配線」という構成)。

    `llm_call`が`_llm_call_not_implemented`のまま(LLM API未接続、オーナー承認待ち)呼ばれた
    場合、その`NotImplementedError`は`handle_process_conversation_event()`が他の実行時
    エラーと同様status_code=500へ正規化する(dispatch_process_event()起因のエラーと区別
    しない。checkout_session.main()のverify_id_token(組み立て前に判定できるため501で
    即時判別可能)とは異なり、本関数の`llm_call`はintent振り分け後に呼ばれるため組み立て
    段階では未実装かどうか判定できないことによる仕様上の違い)。Cloud Tasksは5xxを
    リトライ対象として扱うため、オーナー承認・実装差し替え後に自然に再処理される。
    """
    payload = request.get_json(silent=True) or {}

    result = process_conversation_event_from_payload(
        payload,
        now=datetime.now(timezone.utc),
        **get_process_conversation_event_runtime_dependencies(),
    )
    return result.detail, result.status_code
