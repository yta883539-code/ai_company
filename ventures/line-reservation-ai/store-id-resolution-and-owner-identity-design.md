# storeId解決の仕組み と owner_user_id/決済導線user_idの同一性整理(フェーズ続き165)

作成日: 2026-09-01(フェーズ続き165)

## 背景・発見の経緯

follow-unfollow-event-handling-design.md「残課題」に残っていた「`owner_user_id`
(owner-notification-channel-design.md)と、Stripe決済導線が用いる`store_id`/`user_id`
(checkout-initiation-flow-design.md)が同一のLINE userIdを指すかどうかの確認」に着手する
ため、関連する既存設計(checkout-initiation-flow-design.md・stripe-webhook-event-
dispatch-design.md・stripe-customer-id-reverse-lookup-design.md・firestore-data-model.md・
owner-notification-channel-design.md)を横断的に読み直した。

その過程で、確認対象だった「同一性」の手前に、より根本的な未解決事項があることを発見した。
**`storeId`自体をLINE Webhookイベントからどう解決するかが、これまで一度も設計されていない。**

- firestore-data-model.md 1節は`stores/{storeId}`を「店舗単位の設定ドキュメント」とし、
  `stores/{storeId}/conversations/{sessionId}`・`stores/{storeId}/bookingSlots/{slotKey}`等
  すべての per-store コレクションが`storeId`をパスの先頭に含める設計としているが、
  「受信したWebhookイベント1件がどの`storeId`宛かをどう判定するか」は一度も書かれていない。
  onboarding-guide.mdの「店舗ごとに1つLINE公式アカウントを発行する」前提から、本来は
  「どの公式アカウント(チャネル)宛のイベントか」で店舗を識別するのが自然なはずである。
- 一方、stripe-webhook-event-dispatch-design.md 2節は「本ventureは`client_reference_id`に
  店舗の`user_id`(LINE user_id)をそのまま設定する設計を既に...」と明記し、
  stripe-customer-id-reverse-lookup-design.md 1節も「本ventureは`user_id`をそのまま
  `store_id`として扱う」と明記している。ここでの`user_id`はcheckout-initiation-flow-
  design.md 2節の通り、LIFF `liff.getIDToken()`で得た**決済操作者本人(オーナー)の
  個人LINE userId**であり、`prototype/store_profile_store.py`の
  `StoreProfileStoreProtocol.set_stripe_customer_id(self, user_id: str, ...)`/
  `get_store_id_by_stripe_customer_id(...) -> Optional[str]`(店舗)も、渡された`user_id`を
  そのまま`store_id`として扱うコードに既になっている(パラメータ名の使い分けではなく、
  同じ辞書のキーとして扱われている)。

この2つを重ね合わせると、**「storeId = 店舗の公式アカウント(チャネル)を指す識別子」と
「storeId = オーナー個人のLINE userId」という、互いに独立でありながら両立を前提とした
2つの定義が同時に存在してしまっている**ことが分かる。通常の会話フロー(顧客がメッセージを
送る場合)ではメッセージ送信者は顧客本人であり、オーナーの個人LINE userIdとは無関係のため、
「送信者のuserId」からstoreIdを引くことはできない。したがって会話フロー側は暗黙に
「宛先(公式アカウント)」ベースのstoreId解決を前提にしているはずだが、それを明示した設計は
存在せず、決済導線側は「操作者(オーナー)個人のuserId」をそのままstoreIdとして書き込む設計に
なっている。この2つのstoreIdは、素朴には一致しない。

## 論点の整理

LINE Messaging APIのWebhookリクエストボディには、`events`配列とは別に、そのWebhookが
どのチャネル(公式アカウント)宛かを示す`destination`フィールド(そのチャネル自身の
bot userId)がトップレベルに含まれる(LINE公式ドキュメントの一次情報での実装時の再確認は
必要だが、複数チャネルを1つのWebhookエンドポイントで受ける構成向けの標準的な仕組みとして
一般に知られている)。本venture固有の事情である「店舗ごとに専用の公式アカウントを発行する」
構成とも自然に噛み合う: `destination`はイベント種別(`message`/`follow`/`unfollow`いずれ)
によらず毎回同じ値が載り、送信者が誰であるか(顧客かオーナーか)に依存しない安定した
識別子になる。

これに対し、決済導線が使う「LIFF ID Token検証で得られる`user_id`」は、そのLIFFアプリを
起動した**人物**の個人LINE userIdであり、`destination`とは全く別の値になる。オーナーが
自分のLIFFリンクを開いて決済しても、その`user_id`は「そのチャネル自身の識別子」には
ならない。

## 結論・推奨方針

1. **storeIdは`destination`(店舗の公式アカウント自身のuserId)を正とする。**
   `stores/{storeId}`以下の全コレクション(bookingSlots・conversations・
   notificationLogEntries・escalationWindows等、いずれもfirestore-data-model.md記載)は、
   顧客・オーナーいずれの発言かに関わらず同じ`destination`値でパーティション分けされる
   ため、この定義であれば会話フロー側の暗黙の前提とも矛盾しない。
2. **決済導線(Checkout Session作成エンドポイント)は、`storeId`をLIFF起動リンクの
   クエリパラメータ(例: `?store_id=<destination値>`)として明示的に受け取る。**
   起点となるリンク(trial-end-report・オンボーディング完了メッセージいずれも
   `_send(user_id, ...)`で特定の店舗の会話コンテキストから生成される)は、生成時点で
   自分がどの`storeId`に属するメッセージかを既に知っているため、リンクへの埋め込み自体に
   新たな技術的障害はない。
3. **LIFF ID Token検証で得られる個人`user_id`は、`store_id`としてではなく、
   「この人物は本当に`stores/{store_id}.owner_user_id`と同一人物か」という認可チェックの
   材料としてのみ使う。** 一致すれば決済続行、不一致(または`owner_user_id`未設定=
   接続テスト未実施)であれば決済を拒否し、オーナー宛にオンボーディング完了を促す案内へ
   誘導する(文言は次回以降の設計課題)。
4. この方針変更により、`client_reference_id`には個人`user_id`ではなく`store_id`
   (=`destination`)を設定する形にstripe-webhook-event-dispatch-design.md 2節・
   stripe-customer-id-reverse-lookup-design.md 1節の記述を改める必要がある。ただし
   **「`client_reference_id`を読むだけで別ストアへの問い合わせなしにstore_idが直接得られる」
   という両ドキュメントの結論自体(course-set-pasha/aircon-pashaとの差分の核心)は変更不要**
   であり、埋め込む値の意味づけ(個人userId→store_id)だけを訂正すればよい。

## 影響範囲・実装コストへの影響

- `create_checkout_session(request)`(Checkout Session作成エンドポイント本体)、
  Function B(Cloud Tasksデキュー後のLINE Webhook実処理エントリポイント、`destination`を
  読んでstoreIdを解決する処理を新たに含む必要がある)は、いずれもchecklist上
  「未実装」のまま(pending-approval.md記載のLIFFアプリ登録・実LINE/Firestore接続待ち)
  だったため、**今回の訂正によって書き直しが必要になる既存コードは存在しない**。
  `prototype/store_profile_store.py`の各メソッド(`user_id`という引数名で店舗を指す値を
  受け取る設計)もそのまま維持でき、呼び出し元が渡す値の由来(個人LINE userId→store_id
  (destination))だけが変わる。テスト・実装への影響がない今のタイミングで発見できたことは
  幸いである。
- `owner_user_id`(オーナー個人のLINE userId、接続テストメッセージのWebhookイベント
  `source.userId`から取得)自体の取得方法(owner-notification-channel-design.md)は
  変更不要。接続テストメッセージのWebhookイベントにも同じ`destination`フィールドが
  含まれるため、「どのstoreIdの`owner_user_id`として保存するか」もこの方針に沿って
  自然に解決できる(接続テストを受信したチャネル=そのdestinationの店舗)。

## 元の疑問への回答

follow-unfollow-event-handling-design.mdが残していた「`owner_user_id`と決済導線の
`user_id`は同一のLINE userIdか」という問いに対しては、**上記の訂正を前提にすれば
「同一である必要はなく、そもそも別の役割(認可チェックの参照値 と 実施主体の入力値)である」
という整理になる**。両者はいずれも「オーナー個人のLINE userId」を指す値である点では
同じ性質を持つため、通常運用では一致する場面が多いと想定されるが、`store_id`としては
どちらも使われなくなるため、当初の問い(=一致しないとバグになるのか)自体が解消される。

## 残課題

- (解消済み 2026-09-02 03:00 UTC・フェーズ続き168: 「destinationを読んでstoreIdを解決する
  実処理」を2段階に分けて実装した。(1)Cloud Function A(`cloud_function_webhook.py`の
  `webhook_receiver()`)に`destination`引数(省略可、既存呼び出し元との後方互換を維持)を
  追加し、渡された場合はenqueueする各イベントのpayloadへ複製するようにした
  (`events`配列内の個々のイベント自体には`destination`が含まれないため、Aの時点で
  複製しておく必要がある)。(2)`cloud_function_process_event.py`に
  `resolve_store_id_from_destination(payload) -> str`を新設し、payloadの`destination`を
  読んでstoreIdとして返す(欠落・非文字列・空文字列は`MissingDestinationError`
  (`ValueError`のサブクラス)を送出、Cloud Tasksの500正規化と同じ扱いを受けられる)。
  ただし`handle_process_conversation_event()`はこれまで通り既に構築済みの`processor`を
  受け取る前提のままで、本関数をそこから呼び出す配線(=店舗プロフィールをFirestoreから
  読み込んで`ConversationEventProcessor`を組み立てる工程に先立ってstoreIdを解決する処理)は
  実Firestore接続がオーナー承認待ちのため未着手のまま残る。テスト9件追加(webhook側5件・
  process_event側4件を含む)、venture全体503件全件パス・schema検証25件パスを確認した。)
- `destination`フィールドの仕様(LINE Messaging APIの一次情報での確認、複数チャネルを
  1つのCloud Functionsエンドポイントで受ける場合の挙動)は、実LINE Developersコンソールでの
  チャネル登録・実Webhook受信後に一次情報で最終確認する必要がある(現時点は一般的な知識に
  基づく設計であり、実装着手時の確認事項として残す)。
- Cloud Function AのHTTPハンドラ本体(実リクエストボディをJSONパースして`events`と
  `destination`を取り出し`webhook_receiver()`へ渡す層)自体は、デプロイ環境確定後の
  課題として引き続き未実装のまま残る(`webhook_receiver()`は`events`・`destination`を
  既に呼び出し元が取り出し済みの引数として受け取る設計を維持している)。
- Firestoreから店舗プロフィール(`owner_user_id`・`menu_durations`・FAQ情報・営業時間等)を
  読み込んで`ConversationEventProcessor`を組み立てるファクトリ関数、およびそこから
  `resolve_store_id_from_destination()`を呼び出す配線自体は、実Firestore接続待ちのため
  引き続き次回以降の課題として残る。
- (解消済み 2026-09-02 11:58 UTC・フェーズ続き172: LIFF起動リンクへの`store_id`クエリ
  パラメータ埋め込みを実装した。`prototype/checkout_session.py`に
  `build_liff_checkout_link(store_id, *, liff_id=DEFAULT_LIFF_ID)`を新設し、
  `cloud_function_send_trial_end_reports.send_trial_end_reports()`が候補ごとに個別の
  リンクを組み立てるよう配線した。改ざん検知は行わない(3.の結論どおりLIFF ID Tokenでの
  認可チェックが最終防波堤)。詳細はcheckout-initiation-flow-design.md 11節参照。)
- (解消済み 2026-09-02 08:00 UTC・フェーズ続き171: 認可チェック不一致時(不正な`store_id`
  指定、または`owner_user_id`未設定)のオーナー向けエラー文言・案内先を、
  checkout-initiation-flow-design.md 10節として新規設計した。詳細は同節参照。)
- (解消済み 2026-09-02 05:00 UTC・フェーズ続き169: checkout-initiation-flow-design.md
  9節・stripe-webhook-event-dispatch-design.md 2節・stripe-customer-id-reverse-
  lookup-design.md 1節に、それぞれ本ドキュメントを参照する形の訂正節・訂正段落を追加した。
  いずれも「`client_reference_id`/`store_id`として書き込まれる値は個人LINE user_idでは
  なく`store_id`(=`destination`)である」「既存コード(`store_profile_store.py`・
  `checkout_session.py`)は引数名`user_id`のままでよく書き直しは不要、呼び出し元が渡す
  値の由来のみが変わる」という4節の結論を反映した。checkout-initiation-flow-design.md
  9節ではCheckout Session作成エンドポイントの手順を「(1)クエリパラメータから`store_id`
  受領→(2)LIFF IDトークン検証で個人`user_id`取得→(3)`owner_user_id`との一致確認〈認可
  チェック〉→(4)`store_id`をキーに決済処理」の4段階に具体化した。いずれもドキュメント
  整合のみでコード変更は無し、venture全体503件全件パス・schema検証25件パスを再確認
  した。)
