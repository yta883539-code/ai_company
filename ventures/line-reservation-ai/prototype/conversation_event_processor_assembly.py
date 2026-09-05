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
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Optional

sys.path.insert(0, str(Path(__file__).parent))

from business_hours_assembly import build_availability_searcher_for_store  # noqa: E402
from cloud_function_process_event import (  # noqa: E402
    ConfirmedReplyRecorder,
    ConversationEventProcessor,
    ConversationStateStoreProtocol,
    LinePushClient,
    OwnerFollowStatusStoreProtocol,
    resolve_store_id_from_destination,
)
from engine import NotificationLogAggregator  # noqa: E402
from store_profile_store import build_conversation_flow_state_machine_for_store  # noqa: E402
from store_settings_save_flow import StoreSettingsStoreProtocol  # noqa: E402


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
