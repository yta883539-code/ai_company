# hold()/confirm()・escalationWindows更新のFirestoreトランザクション設計

firestore-data-model.md の残課題だった、`BookingSlotManager.hold()`/`confirm()` と
`EscalationConsolidator.on_event()`(escalationWindows更新)をFirestoreトランザクション
(`runTransaction`/Pythonクライアントの`@firestore.transactional`)に置き換える際の
実装方針を詳細化する。実際のFirestoreクライアント接続・GCPプロジェクト作成は
「アカウント作成」に該当するため未着手のままとし、本設計は関数シグネチャ・
トランザクション境界・失敗時の扱いを確定させる机上設計に留める。

## 前提: Firestoreトランザクションの性質

- 1トランザクション関数内で行った全ての`get()`はスナップショット分離で読み込まれ、
  関数内の`set()`/`update()`はコミット時に「読み込んだドキュメントが他のトランザクションに
  よって変更されていないか」を検証し、変更されていれば関数全体を自動リトライする
  (デフォルト最大5回)。
- この性質により、`BookingSlotManager`のクラスコメントに残っていた
  「MVP段階では単一プロセス・単一スレッドの逐次呼び出し前提で、真の並行アクセス
  (マルチプロセス)には未対応」という制約は、Cloud Functionsが同時多重起動されても
  Firestore側の楽観的並行性制御(OCC)でそのまま解消できる。呼び出し側
  (engine.py)のロジックを複雑化させる必要はない。

## `hold()`のトランザクション化

```python
@firestore.transactional
def _hold_tx(transaction, slot_ref, session_id, now):
    snapshot = slot_ref.get(transaction=transaction)
    if snapshot.exists:
        data = snapshot.to_dict()
        expired = (
            data["status"] == "pending"
            and now - data["heldAt"] > BookingSlotManager.HOLD_TIMEOUT
        )
        if not expired and data["sessionId"] != session_id:
            return False  # 既に他ユーザーが保持中(pending/confirmed問わず)
    transaction.set(slot_ref, {
        "status": "pending",
        "sessionId": session_id,
        "heldAt": now,
    })
    return True

def hold(self, slot_key, session_id, now):
    slot_ref = self._slot_ref(slot_key)  # stores/{storeId}/bookingSlots/{slotKey}
    return _hold_tx(self._client.transaction(), slot_ref, session_id, now)
```

- `_expire_if_needed()`(既存の読み取り時失効チェック)は、トランザクション関数内の
  `expired`判定にそのまま吸収する形とし、独立した削除呼び出しは行わない
  (削除してもしなくても`status`と`sessionId`の上書きで意味的に等価であり、
  トランザクション内の書き込み回数を1回に抑えられるため)。
- 既存の`_slots: dict`版と挙動を完全一致させるため、「他ユーザーのpending/confirmedに
  ぶつかったらFalse、期限切れpendingや同一ユーザーの再holdはTrue」という分岐は変えない。

## `confirm()`のトランザクション化

```python
@firestore.transactional
def _confirm_tx(transaction, slot_ref, session_id, now):
    snapshot = slot_ref.get(transaction=transaction)
    if not snapshot.exists:
        return False
    data = snapshot.to_dict()
    expired = (
        data["status"] == "pending"
        and now - data["heldAt"] > BookingSlotManager.HOLD_TIMEOUT
    )
    if expired or data["sessionId"] != session_id or data["status"] != "pending":
        return False
    transaction.update(slot_ref, {"status": "confirmed"})
    return True
```

- `hold()`と`confirm()`は必ず別々のトランザクションになる(顧客の返信を待つ間隔が
  空くため、1トランザクションにまとめることはできない)。この間に別ユーザーが
  同じ`slotKey`を横取りする競合は、`confirm()`側のトランザクション内で
  `sessionId`不一致として検出され、既存設計通り
  `ConversationFlowStateMachine`側の「pending差し戻しはせずオーナー通知のみ」
  (conversation-flow-state-machine-design.md)にそのまま接続できる。

## `escalationWindows`更新のトランザクション化

`EscalationConsolidator.on_event()`は「読み込み→(30分リセット/ウィンドウ内追加/
再発火判定)→書き込み」を1回の呼び出しで行っており、`hold()`と同様の
read-modify-write構造のためトランザクション化の要否・方式もほぼ同型となる。

```python
@firestore.transactional
def _on_event_tx(transaction, window_ref, event, now):
    snapshot = window_ref.get(transaction=transaction)
    actions = []
    if not snapshot.exists:
        transaction.set(window_ref, {
            "windowOpenedAt": now, "lastEventAt": now,
            "reopenCount": 0, "queued": [], "queuedCount": 0,
        })
        actions.append(("immediate", event))
        return actions

    data = snapshot.to_dict()
    if now - data["lastEventAt"] > EscalationConsolidator.RESET_AFTER:
        transaction.set(window_ref, {
            "windowOpenedAt": now, "lastEventAt": now,
            "reopenCount": 0, "queued": [], "queuedCount": 0,
        })
        actions.append(("immediate", event))
        return actions

    if now - data["windowOpenedAt"] <= EscalationConsolidator.WINDOW:
        transaction.update(window_ref, {
            "lastEventAt": now,
            "queued": firestore.ArrayUnion([event]),
            "queuedCount": firestore.Increment(1),
        })
        return actions

    reopen_count = data["reopenCount"] + 1
    if reopen_count >= EscalationConsolidator.REFIRE_LIMIT:
        transaction.update(window_ref, {
            "lastEventAt": now, "windowOpenedAt": now,
            "reopenCount": reopen_count, "queued": [], "queuedCount": 0,
        })
        actions.append(("immediate_refire", event))
    else:
        transaction.update(window_ref, {
            "lastEventAt": now, "windowOpenedAt": now,
            "reopenCount": reopen_count,
            "queued": [event], "queuedCount": 1,
        })
    return actions
```

- 同一顧客からの短時間の連続イベント(集約対象そのもの)は同一`sessionId`
  ドキュメントへの書き込みが競合しうるため、`hold()`以上にトランザクションの
  リトライが発生しやすい想定。ただし1顧客あたりの連続イベント頻度は
  「同時に複数チャネルから同時送信」のような特殊ケースを除き通常低いため、
  デフォルトのリトライ回数(5回)で十分と判断する。
- `queued`(配列)に加えて`queuedCount`(数値)を並存させる設計とした。理由は
  下記「flush_due_windows()のクエリ設計」参照。

## `flush_due_windows()`のクエリ設計

`flush_due_windows()`は特定の`sessionId`に対する単発の読み書きではなく、
「ウィンドウ(5分)を過ぎてキュー未送信のユーザー全員」を横断的に見つけるバッチ処理で、
idle-conversation-trigger-design.mdと同じ「Webhook便乗+間引き」方式での定期実行を想定する。

- Firestoreは配列フィールドの「非空」判定を効率的にクエリできない
  (`array_length`のようなクエリ演算子が無い)ため、`queuedCount > 0`という
  数値フィールドでの範囲クエリに置き換える。
- 対象クエリは `queuedCount > 0 AND windowOpenedAt < (now - WINDOW)` の
  2フィールド不等号条件になり、Firestoreでは複合インデックス
  (`queuedCount`, `windowOpenedAt`の複合インデックス定義)が必要になる点を
  実装時の注意点として記録する。
- ヒットしたドキュメントは`queued`配列を読み出してまとめ通知を送った後、
  `queued: [], queuedCount: 0`にリセットする更新を行う(この更新は
  「送信直後の新規イベント追加」との競合を避けるため、こちらもトランザクション
  もしくは`update()`の条件付き書き込み(前提条件チェック)で行うことが望ましい)。

## 残課題

- 上記はいずれも疑似コードレベルの設計であり、実際のFirestore Pythonクライアント
  (`google-cloud-firestore`)を用いた動作確認は、GCPプロジェクト作成・Firestore
  有効化(オーナー承認待ち、pending-approval.md参照)の後に着手する。
- `flush_due_windows()`用の複合インデックス定義(Firestoreの`firestore.indexes.json`
  相当)の具体的な記述は、実装着手時に行う。
- 想定トラフィックでのトランザクションリトライ発生率・読み書き課金試算は、
  firestore-data-model.mdの残課題と合わせて未着手のまま。
