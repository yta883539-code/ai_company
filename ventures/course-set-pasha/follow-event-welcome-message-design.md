# followイベントハンドラ・ウェルカムメッセージ設計

作成日: 2026-08-21(フェーズ80)

line-user-id-linking-design.md 残課題「`follow`イベント受信時にウェルカムメッセージへ
コードを埋め込んで実際に返信する処理は、実LINE Messaging API接続自体がオーナー承認待ちの
ため未着手(コード発行ロジック自体は実接続なしで検証済み)」と、
linking-code-purge-trigger-design.md 未解決事項「ハンドラ実装時に案B(followイベント便乗)の
二重便乗を追加するかは、その時点でのfollow頻度の実測データを見て判断する」の2点に対応する。

これまでの本venture・line-reservation-aiの一貫した方針(実クラウド接続なしで処理ロジック
自体を検証可能にしておき、承認後は差し替えのみで動作させる)に倣い、`follow`イベントを
受信した際の処理フロー自体を設計・実装する。実LINE公式アカウント開設・Messaging API接続は
引き続きpending-approval.md記載の承認待ち事項のまま変えない。

## 1. ウェルカムメッセージの内容

友だち追加直後の1通で、(1)サービス概要の一言、(2)連携コード、(3)コードの使い方(申込
フォームへの入力依頼)、(4)有効期限、の4点を伝える。post_generation_checks.pyが対象とする
生成文(SNS投稿文・告知文)とは性質が異なる固定テンプレート文言のため、機械チェックの対象
には含めない(厳守事項1〜9はメモ入力に対する生成文のルールであり、友だち追加時の定型
案内文には適用されない)。

```
コースセットパシャッと 友だち追加ありがとうございます!

このサービスは、課題入れ替え後のメモを送るだけでSNS投稿文・告知文・履歴記録の下書きを
まとめて生成するツールです。

ご利用開始には、下記の連携コードを申込フォームにご入力ください(24時間有効・1回限り)。

連携コード: {LINKING_CODE}

▼ お申込みフォーム
{APPLICATION_FORM_URL_PLACEHOLDER}

コードの有効期限が切れた場合は、もう一度このトークを開くと新しいコードが届きます。
```

- `{LINKING_CODE}`は`issue_linking_code_on_follow()`が返す6文字のコードをそのまま埋め込む。
- `{APPLICATION_FORM_URL_PLACEHOLDER}`は、`render_subscription_procedure_notice()`の
  `PORTAL_LINK_PLACEHOLDER`と同じ考え方で、実フォームURL確定(Googleフォーム作成、
  オーナー承認待ち)までのプレースホルダとして残す。`PortalLinkProvider`と同じ形の
  Protocol(`ApplicationFormLinkProvider`)を新設し、未接続時(Noneまたは取得失敗)は
  プレースホルダ文字列をそのまま返す(顧客が実際に受け取るのはオーナー承認・接続後のため、
  MVP段階でプレースホルダが人目に触れることはない。`PORTAL_LINK_UNAVAILABLE_FALLBACK`の
  ような全文差し替えフォールバックまでは不要と判断した。理由: ポータルURLは解約導線という
  顧客が実際に手続きに詰まりうる場面である一方、フォームURLは友だち追加直後の案内であり
  URL自体が未接続な段階では本メッセージ自体もまだ実送信されないため、実害が生じる場面が
  存在しない)。
- 「もう一度このトークを開くと新しいコードが届きます」の一文は、line-user-id-linking-design.md
  3節で既に暫定確定していたエラー案内文言と表現をそろえた。

## 2. 処理フロー

`prototype/cloud_function_webhook.py`に`process_follow_event()`を新設する。

```python
def process_follow_event(
    event: dict,
    linking_store: LinkingCodeStoreProtocol,
    reply_client: ReplyClient,
    *,
    form_link_provider: Optional[ApplicationFormLinkProvider] = None,
    rng: Optional[RandomChoiceSource] = None,
    now: Optional[datetime] = None,
) -> FollowProcessResult:
```

- `event["type"] != "follow"`の場合は`handled=False`で返す(`process_memo_event()`の
  `message.type != "text"`と同じ、対象外イベントを静かに無視する設計)。
- `event["source"]["userId"]`が取得できない場合は返信を送らずreply_sent=Falseで返す
  (実運用では発生しない想定だが、`process_memo_event()`のuser_id欠落時の防御的分岐と
  設計をそろえる)。
- `issue_linking_code_on_follow(user_id, linking_store, now, rng)`でコードを発行する。
  `rng`未指定時は`random.Random()`を既定値として使う(test_user_id_linking.pyの
  既存テストと同じ、呼び出し側がテストで決定的な値を注入できる設計を踏襲)。
- ウェルカムメッセージ文言を組み立て、`_reply_with_retry()`(既存の再送ロジック、
  api-call-failure-handling.md方針2準拠)で送信する。既存の`process_memo_event()`と
  同じ再送クライアントを再利用することで、リトライ回数・待機時間等の挙動を統一する。
- 送信失敗時(`_reply_with_retry()`がFalseを返す)もコード発行自体は取り消さない
  (`pending_links`にコードは残ったまま。ユーザーが再度トークを開けば新コードが発行され、
  古いコードは有効期限で自然に失効するため実害はない。line-user-id-linking-design.md 4節の
  「実害は実質的に発生しない」方針と同じ考え方)。

## 3. 案B(followイベント便乗パージ)の二重便乗

linking-code-purge-trigger-design.md未解決事項への回答として、`process_follow_event()`にも
`process_memo_event()`と同じ`linking_store`・`purge_throttle`引数(共有インスタンスを渡す
想定)を追加し、本題(コード発行・返信)に先立って`purge_throttle.maybe_run()`を呼べる形に
しておく。ただし**MVP初期は呼び出し元でこの二重便乗を有効にしない(案Cのみ稼働)**という
結論は変えない。理由:

- 案Cが既に主トリガーとして機能しており、案Bを追加しても「掃除がより早く走る」以上の効果は
  薄い(purge対象はいずれにせよ実害の無い空きドキュメントの掃除)。
- follow頻度が実測できていない段階で追加の書き込み(スロットル判定・場合によっては削除)を
  増やすより、まずは案Cのみで運用し、実測データが揃ってから要否を判断する
  linking-code-purge-trigger-design.mdの元の方針を維持する。

「実装時に判断する」としていた分岐点を、実装はしておくが有効化はしない(呼び出し元で
`purge_throttle`引数を渡さなければ従来通りスキップされる)という形で解消した。これにより
将来案Bを有効化したくなった場合もコード変更ゼロ(呼び出し元の引数追加のみ)で対応できる。

## 4. プロトタイプ実装方針

- `cloud_function_webhook.py`に`ApplicationFormLinkProvider`(Protocol)・
  `APPLICATION_FORM_URL_PLACEHOLDER`定数・`format_welcome_message()`・
  `process_follow_event()`・`FollowProcessResult`(dataclass)を追加する。
- `user_id_linking.py`の`issue_linking_code_on_follow`・`LinkingCodeStoreProtocol`・
  `RandomChoiceSource`をインポートして利用する(既存の`resolve_linking_code`系と同じ
  依存方向、`user_id_linking.py`側への変更は不要)。
- テストは`test_cloud_function_webhook.py`に追加し、(1)正常系(コード発行・返信文への
  埋め込み確認)、(2)`form_link_provider`未接続時にプレースホルダのまま送信される、
  (3)`form_link_provider`接続時に実URLへ置換される、(4)`type`が`follow`以外のイベントは
  無視される、(5)`source.userId`欠落時は返信しない、(6)返信失敗時もFollowProcessResultの
  `linking_code`は発行済みの値を保持する、の6ケースを最低限カバーする。

## 残課題

- (解消済み 2026-08-22 17:00 UTC・フェーズ93での確認: `follow`イベントのディスパッチ経路は
  フェーズ81〜83(`webhook-event-dispatch-design.md`・`receive-webhook-http-entry-point-
  design.md`)で既に実装済みだった。`dispatch_webhook_events()`が`event["type"] == "follow"`
  を`process_follow_event()`へ1件ずつ振り分ける構成になっており、本項目は記載が古いまま
  残っていた点を訂正する)
- `ApplicationFormLinkProvider`の実装(実フォームURLの取得元)は、Googleフォーム作成
  (オーナー承認待ち)後、フォームの共有URLを固定値として返す最小実装で足りる見込み
  (`portal_link_provider`のような動的なユーザーごとの出し分けは不要)。
- ウェルカムメッセージの文面は最終的な日本語表現の推敲(オーナーレビュー)を経ていない
  下書き段階。
