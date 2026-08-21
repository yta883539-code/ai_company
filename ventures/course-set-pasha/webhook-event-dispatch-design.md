# Webhook本体のイベント種別ディスパッチ設計

作成日: 2026-08-21(フェーズ81)

follow-event-welcome-message-design.md 残課題「実際の`follow`イベントをWebhook本体
(署名検証後のイベント種別ディスパッチ)からどう`process_follow_event()`へ振り分けるか」に
対応する。`cloud_function_webhook.py`には現状、`process_follow_event()`(follow イベント
1件を処理)と`process_memo_event()`(message イベント1件を処理)がそれぞれ単体で存在する
のみで、実際のLINE Webhookリクエストボディ(`{"events": [...]}`、1リクエストに複数種別の
イベントが混在しうる)を受け取ってどちらへ振り分けるかのエントリポイントが未実装だった。

## 1. 方針: 単一関数`dispatch_webhook_events()`

line-reservation-aiは会話状態管理・Cloud Tasksによる非同期処理基盤を持つため
Cloud Function A(受信・enqueueのみ)/B(実処理)の2段構成だが、本ventureは
webhook-processing-flow-design.md時点から一貫して単一Cloud Function・同期処理の
方針を採っている(tech-stack.md参照)。そのため本フェーズも2段構成にはせず、
署名検証後の`events`配列をそのままイベント種別ごとに振り分ける単一関数
`dispatch_webhook_events()`を追加する。

```python
def dispatch_webhook_events(
    events: list[dict],
    *,
    linking_store=None, reply_client=None, llm_call=None,
    form_link_provider=None, portal_link_provider=None,
    usage_counter=None, plan=None, month=None,
    first_generation_notice_store=None, gym_area_config_store=None,
    purge_throttle=None, rng=None, now=None,
) -> DispatchResult:
```

- `event["type"] == "follow"`のイベントは`process_follow_event()`へ、そのまま1件ずつ渡す
  (text-image束ね処理の対象外)。
- `event["type"] == "message"`のイベントは、まず`merge_text_and_photo_events()`で
  同一`source.userId`単位に束ねてから`process_memo_event()`へ1件ずつ渡す(既存の
  `merge_text_and_photo_events()`はmessage イベントのみを対象とする設計のため、
  follow イベントを混ぜて渡すと`ungrouped`扱いで素通りしてしまい意図と異なる。
  そのため呼び出し前に`event["type"] == "message"`で明示的に絞り込む)。
- それ以外の種別(`unfollow`・`postback`・`join`等)は現時点で対応するハンドラを
  持たないため無視し、`DispatchResult.ignored_types`に種別名を記録するのみに留める
  (実処理は行わない。将来必要になった時点で個別に設計する)。
- `reply_client`/`linking_store`が未接続(None)の場合はfollow イベントを、
  `reply_client`/`llm_call`が未接続の場合はmessage イベントを、それぞれ処理せず
  素通りする(実LINE API/実LLM接続前の呼び出しで、未接続を理由にした例外ではなく
  「そのイベント種別は今は処理しない」という安全側の挙動に倒す。process_follow_event()・
  process_memo_event()自体はNone未対応のため、ここで事前にガードする)。

## 2. 結果の集約

```python
@dataclass
class DispatchResult:
    follow_results: list = field(default_factory=list)  # list[FollowProcessResult]
    memo_results: list = field(default_factory=list)     # list[MemoProcessResult]
    ignored_types: list = field(default_factory=list)    # 無視した種別名(順不同で構わない)
```

呼び出し元(実Cloud Function化した際のHTTPハンドラ)が、follow/messageそれぞれの
処理結果を個別に参照できるよう種別ごとに分けて保持する。line-reservation-aiの
`WebhookReceiverResult`(enqueue結果のみを保持する薄い集約)とは異なり、本venture側は
同期処理でその場で返信まで完了するため、`FollowProcessResult`/`MemoProcessResult`を
そのまま保持する形とした。

## 3. プロトタイプ実装方針

- `cloud_function_webhook.py`に`DispatchResult`(dataclass)・`dispatch_webhook_events()`を
  追加する。既存の`process_follow_event()`・`process_memo_event()`・
  `merge_text_and_photo_events()`はいずれも変更しない(振り分けのみを行う薄い関数として
  追加する)。
- テストは`test_cloud_function_webhook.py`に追加し、(1)follow・messageが混在する
  events配列で両方が正しく振り分けられる、(2)message イベントのみtext-image束ねが
  適用される(follow イベントが束ね処理に混入しない)、(3)未対応種別(例:
  `unfollow`)は`ignored_types`に記録されるだけで例外を出さない、(4)`reply_client`等が
  未接続の場合は該当種別のイベントを処理せず結果も空のまま返す、の4ケースを
  最低限カバーする。

## 残課題

- 実際にHTTPリクエストボディ(JSON)をパースして`events`配列を取り出す部分・
  `verify_line_signature()`との結線(署名検証失敗時は`dispatch_webhook_events()`自体を
  呼ばない)は、実Cloud Functions環境確定後の課題として残る(署名検証関数自体は
  既存の`verify_line_signature()`がそのまま使える想定)。
- (解消済み 2026-08-21 15:00 UTC: `unfollow`イベント受信時の扱い(連携コード・利用状況
  データの扱い)をフェーズ84・unfollow-event-handling-design.mdで決定・実装した。詳細は
  そちらを参照)
