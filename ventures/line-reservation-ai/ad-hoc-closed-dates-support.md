# AvailabilitySearcherの臨時休業(特定日付)対応

availability-closed-weekday-support.mdの残課題だった「祝日・臨時休業(定例の曜日ではなく特定の日付を
単発で休業にする)への対応」を行った。

## 設計方針

- `closed_weekdays`(曜日単位の定休日)とは独立した仕組みとして`closed_dates: frozenset[date] = frozenset()`
  を`AvailabilitySearcher.__init__`に追加した。両者は併用可能で、対象日がどちらか一方にでも該当すれば
  その日の枠は候補から除外する(ORの関係)。
- 値は`datetime.date`オブジェクトの集合とした。曜日番号(int)を使う`closed_weekdays`と型を分けることで、
  呼び出し側の取り違えをコード上区別しやすくした。
- デフォルト値を空集合としたため、既存の呼び出し箇所(引数を渡していない箇所)は挙動を変えず後方互換を
  保っている。
- `find_candidates()`のループ条件を
  `if day.weekday() in self._closed_weekdays or day in self._closed_dates:`
  に変更し、いずれかに該当する日はその日の枠を一切生成せず次の日へ進むようにした
  (closed_weekdaysと同様、「営業時間外」ではなく「その日は候補日から除外する」という扱いを踏襲)。

## スコープ外とした事項(意図的)

- 「祝日カレンダーの自動取得(内閣府の祝日データ等との連携)」は行わない。祝日でも営業するサロンが
  多いという availability-closed-weekday-support.md の想定を踏まえ、closed_datesは店舗オーナーが
  個別に登録する「臨時休業日リスト」という位置づけに統一し、祝日か否かの自動判定はしない。
- owner-settings-wireframe.mdの入力UIは今回は未着手。MVPでは「営業情報設定ページ」に日付を1件ずつ
  追加できるシンプルなリスト入力(カレンダーUIではなくテキスト日付の追加/削除)で足りると想定するが、
  ワイヤーフレームへの反映は次のステップとする。
- reminder_scheduler.py側(前日リマインドの送信日決定で`closed_weekdays`により前営業日へ遡る処理)への
  同様の`closed_dates`対応は、影響範囲の切り分けのため今回は見送り、別課題として残す(直近の臨時休業を
  対象とした予約が入るケース自体が少ないと想定されるため優先度は低いが、未対応である旨は明記しておく)。

## 実装

- `prototype/engine.py`の`AvailabilitySearcher`クラスに`closed_dates`パラメータを追加。
- `prototype/test_engine.py`に、(1)臨時休業日単体での除外、(2)曜日定休と臨時休業の併用時に両方が
  正しく除外されることを確認するテストを2件追加。全127件(既存125件+新規2件)パス。

## 残課題

- (解消済み 2026-08-02 23:00 UTC: reminder_scheduler.pyの`compute_initial_reminder_target()`に
  `closed_dates`対応を追加した。`StoreReminderConfig`に`closed_dates: frozenset[date] = frozenset()`を
  追加し、遡りループの条件を`day.weekday() in store.closed_weekdays or day in store.closed_dates`に変更。
  `closed_weekdays`と`closed_dates`は併用可能(OR条件)で、いずれかに該当する日は前日リマインドの
  送信日候補から除外される。テスト2件追加(臨時休業日単体での遡り、定休日と臨時休業日の併用)、
  全129件パス)
- (解消済み 2026-08-03 00:00 UTC: owner-settings-wireframe.mdの「1. 営業情報設定ページ」に
  「臨時休業日」入力欄(日付の追加/削除リスト)を追記した。定休日(曜日単位)の欄とは別枠とし、
  両者併用可能な旨を明記。過去日付・重複日付の入力バリデーションは未検討のまま残課題とした)
- owner-settings-wireframe.mdの臨時休業日入力欄における過去日付・重複日付の入力バリデーション設計。
