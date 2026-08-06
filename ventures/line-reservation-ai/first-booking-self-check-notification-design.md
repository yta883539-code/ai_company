# 店舗全体で最初の予約確定時のセルフチェック通知 設計

作成日: 2026-08-06

## 背景

onboarding-guide.mdの「未検証の仮説」3点目で、ステップ4(接続テスト・試験会話)を
オーナーが省略して本番投入してしまい、設定ミス(営業時間・メニュー内容の入力間違い等)に
気づかないまま実際の顧客対応が始まってしまうリスクを挙げていた。同ドキュメントでは
「初回顧客対応時に自動で簡易セルフチェック通知を送る案も将来検討の余地あり」とだけ
書き残されており、具体設計は未着手だった。本ドキュメントはそのギャップを埋める。

## 方針

- 店舗全体で**最初の1件目の予約確定(confirmed)が発生した直後**に限り、通常の顧客向け
  確定メッセージ(`format_confirmation_message()`)とは別に、オーナー宛の追加通知を1回だけ送る。
- 2件目以降の確定では発火しない(毎回送ると煩わしい通知になり、tone-and-manner-guideline.mdの
  「オーナー通知は必要な時だけ」という既存方針にも反するため)。
- あくまで「設定を見直すきっかけの提供」であり、エスカレーション(厳守事項6・10等)のような
  問題発生の通知ではない。そのため既存のEscalationConsolidator(集約・即時通知の判断ロジック)や
  NotificationLogAggregator(通知ログ集計、`needs_owner_check`起点)は経由しない設計とした。
  この2つは「顧客対応が必要な問題」を集計する仕組みであり、セルフチェック促しを混ぜると
  通知ログ集計画面(owner-settings-wireframe.md)の件数が実態と乖離してしまうため。
- ステップ4(接続テスト)を実施済みの店舗にとっては冗長な通知になるが、実施したかどうかを
  システム側で判別する手段が無いため、MVPでは「実施済みでも1回だけ届く」ことを許容する
  (実施済みなら内容を見て問題なしと分かるだけで、実害は小さいと判断)。

## 実装

`prototype/engine.py`の`ConversationFlowStateMachine`に以下を追加した。

- `__init__`に`_first_booking_self_check_sent`(店舗全体で発火済みかのフラグ)と
  `_first_booking_self_check_pending`(呼び出し側がまだ消費していないかのフラグ)を追加。
- `provide_details()`が`confirm()`成功で`confirmed`へ遷移する際、`_first_booking_self_check_sent`が
  まだFalseなら両フラグをTrueにする(=店舗全体で最初の確定であることを記録)。
- `consume_first_booking_self_check() -> bool`を新設。`_first_booking_self_check_pending`が
  Trueならそれを一度だけ消費してTrueを返し、以降はFalseを返す。呼び出し側は
  `provide_details()`が`True`を返した直後にこれを呼び、`True`ならオーナーへ追加送信する想定
  (Cloud Function Bの本番配線側の実装は、実LINE API接続がオーナー承認待ちのため未着手のまま残る)。
- `format_first_booking_self_check_message(candidate_label, menu, customer_name) -> str`を新設。
  escalation-notification-templates.mdの「オーナー向け通知は主語をAI/システムにしてよい」規約に
  従った固定文面(顧客向けメッセージのようなトーン別出し分けは行わない)。

```
【ご確認のお願い】AIが最初のご予約確定を処理しました。
    {candidate_label} {menu} / {customer_name}様
    営業時間・メニュー内容・所要時間などの店舗設定が意図通りかを、この機会に一度ご確認ください。
    問題がなければ今後この通知はありません。
```

テスト(`prototype/test_engine.py`)を4件追加:
- 最初の確定で`consume_first_booking_self_check()`がTrueを返し、2回連続で呼んでも
  2回目はFalseになること(消費後は再発火しないこと)。
- 2件目の確定(別ユーザー)では発火しないこと。
- メッセージ文面に候補ラベル・メニュー・顧客名が含まれること。

全138件(test_engine.py単体は58件)パス。

## 残課題

- `prototype/cloud_function_process_event.py`側での実際の配線(`provide_details()`成功後に
  `consume_first_booking_self_check()`を呼び、Trueなら`_send()`と同様の仕組みでオーナーへ送信する)は、
  オーナー向け送信先(LINE以外の経路も含めて未確定)自体が実LINE API接続(オーナー承認待ち)後の
  課題として残っている他のオーナー通知実装と合わせて未着手。
- 複数店舗が同一インフラを共有するマルチテナント運用になった場合、
  `ConversationFlowStateMachine`インスタンスが店舗ごとに分かれる設計であることが前提
  (現在のプロトタイプは単一店舗を暗黙の前提としており、この前提はfirestore-data-model.md等
  既存ドキュメントの前提を踏襲している)。
