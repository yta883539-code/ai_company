# 開業告知文(店頭POP・SNS告知文)下書き生成機能の設計(初回メモ)

作成日: 2026-09-18(定例更新)

## 1. 背景

onboarding-guide.md「次のステップ候補」が、ステップ5(本番公開・「LINEで予約できます」告知)
に関連して「店頭POP・SNS告知文の下書き生成を、本サービスの追加機能候補として検討する」と
残していた。あわせて、kura-pashaのcross-venture-support-cost-comparison.mdは、4venture中で
line-reservation-aiを「月次対応コストの絶対額が最高・対応可能顧客数上限が最少の両方に該当する、
最もサポート体制のスケール制約が先に顕在化しうる候補」と暫定順位付けしていた。その後の定例更新
(2026-09-15〜17)でFAQコマンド方式(owner-faq-routing-design.md)・オンボーディング完了メッセージ
への周知文言追記(onboarding-completion-message-design.md)により、設定変更・トライアル等の
問い合わせ対応コストの軽減は4venture全てで対応済みとなった。

本ドキュメントは、上記とは別の切り口の支援策として、オンボーディング完了後にオーナーが実際に
「顧客に周知してLINE予約を使ってもらう」という最後の一歩(onboarding-guide.mdステップ5)を
後押しする機能を設計する。この一歩が滞ると、無料トライアルの条件(pricing-plan.md「初回の
予約確定から14日間、または予約20件到達のいずれか早い方」)の起算自体が始まらず、トライアルの
価値を実感してもらえないまま離脱するリスクがあるため、間接的にトライアル→有料転換率にも
関わる課題と位置づける。

## 2. スコープの確認

- 本機能は**本サービスの主機能(予約対応の会話ボット)とは別スコープの追加機能**であり、
  MVPの必須要件ではない。実装優先度は主機能・課金導線・通知系の設計が一巡した後に回す。
  (course-set-pasha等「パシャッと」系ventureのコア機能である文面下書き生成とは異なり、
  本ventureでは「予約対応」がコア機能、告知文生成はコアを補助する副次的機能という位置づけ)
- 生成対象は(a)店頭・店内掲示用のPOP文言、(b)SNS(Instagram/X等)投稿用の告知文、の2種類。
  実際のPOPデザイン(画像・レイアウト)やSNS投稿の自動実行は行わない。テキストの下書きを
  LINEでオーナーに渡すところまでがスコール。
- QRコード画像自体の生成・添付は本ドキュメントの対象外とする(友だち追加URLをテキストとして
  文中に差し込むところまでに留める。画像添付は実LINE API接続後の課題として残す)。

## 3. トリガー・配信経路

- オンボーディング完了メッセージ(onboarding-completion-message-design.md)の直後に自動送信
  すると「1メッセージ1用件」の原則(同ドキュメント3節)に反するため、**別メッセージとして
  時間を空けて送る**、または**オーナーがコマンドを送った時にのみ生成する**、のいずれかを
  採用する必要がある。
- owner-faq-routing-design.mdのFAQコマンド方式(トークルームに「FAQ」と送ると案内が返る)と
  同じ設計思想を踏襲し、オーナーがトークルームに**「告知文」**と送ると、店舗設定
  (owner-settings-wireframe.mdで登録済みの店舗名・営業曜日・営業時間)をもとにPOP文言・
  SNS告知文の下書きをその場で返信するコマンド方式を採用する(暫定案)。
  - 自動送信ではなくオーナー起点のオンデマンド生成にすることで、(a)「1メッセージ1用件」
    原則を守れる、(b)オンボーディング未完了(必須項目が揃っていない)状態での誤生成を
    自然に防げる(店舗設定が無ければ生成に必要な情報が揃わないため)、という利点がある。
  - 配線本体(cloud_function_process_event.pyへの`_maybe_render_launch_announcement_
    reply()`の追加)は、2026-09-18 03:00 UTC定例更新のフェーズで実施済み(8節参照)。

## 4. 生成内容の設計

### 4.1 入力(店舗設定から取得、いずれも既存フィールド)

- 店舗名(必須、owner-settings-wireframe.md「営業情報設定ページ」)
- 営業曜日・営業時間(必須、同上)
- 業種(任意、onboarding-guide.mdステップ1の申込フォーム任意項目。未入力時は業種に触れない
  汎用文言にフォールバックする)
- LINE公式アカウントの友だち追加URL(必須、実LINE公式アカウント開設後に確定するプレースホルダ)

### 4.2 出力

- POP文言: 店頭掲示を想定した短め(3〜5行程度)の文面。QRコード画像を貼る余白を前提に
  「友だち追加はこちらから」という誘導文言とURLを含む。
- SNS告知文: ハッシュタグを含む投稿文。course-set-pashaのsns-tone-research.mdが確立した
  「(1)一般ハッシュタグ、(2)店舗名ブランドタグ、(3)地域タグ」の3分類方針を踏まえるが、
  本ventureは地域名を店舗設定として収集していないため、当面は(1)一般ハッシュタグ
  (例: #LINE予約 #ネット予約)・(2)店舗名ブランドタグの2種類に留め、地域タグは
  「地域名を店舗設定に追加する」という別課題(6節)として切り出す。

### 4.3 トーン

owner-settings-wireframe.mdの「メッセージトーン」設定(formal/standard/casual)をそのまま
再利用する(新しいトーン設定を増やさない)。

## 5. サンプル下書き(架空の店舗「Hair Salon Lino」・standard トーン・美容室を例に)

### POP文言(standard)

```
【LINEで予約できます】

Hair Salon Linoの空き状況確認・ご予約が、
お手持ちのLINEから24時間いつでもできるようになりました。

▼ 友だち追加はこちら
https://line.me/R/ti/p/@example-lino

ぜひお試しください。
```

### SNS告知文(standard)

```
Hair Salon Linoのご予約が、LINEから簡単にできるようになりました🙌
お電話が繋がりにくい時間帯でも、いつでも空き状況を確認してご予約いただけます。

▼ 友だち追加はこちら
https://line.me/R/ti/p/@example-lino

#LINE予約 #ネット予約 #HairSalonLino
```

(formal/casualトーンの下書き例はprototype/launch_announcement_draft.pyのテストで
3トーン分の差異を検証する形で表現し、本ドキュメントでは代表例のみ示す)

## 6. 未検証の仮説・残課題

- オーナーが実際に「告知文」というコマンド名を思いつくか(owner-faq-routing-design.md
  5節でも同種の課題があった「単語を思いつかない」問題が再発する可能性がある)。FAQコマンドの
  案内文(owner_faq_router.py `_OWNER_FAQ_ITEMS`)に「告知文」コマンドの存在を追記する形で
  周知するのが妥当と考えられる(次のステップ候補)。
- POP・SNS告知文をオーナーが実際に使いたくなる文面か(押しつけがましくないか、店舗の
  ブランドイメージに合うか)は、customer-interview-design.mdのヒアリングでの検証が必要。
- 地域タグ用の地域名を店舗設定に追加すべきかは、地域名を収集する項目自体が現状の
  owner-settings-wireframe.mdに無いため、追加するかどうかも含めて別途要検討。
- QRコード画像の生成・添付は本ドキュメントの対象外(2節)としたが、テキストURLのみでは
  店頭POPとしての実用性が下がる可能性があり、実LINE API接続後にQRコード画像添付の要否を
  再検討する必要がある。

## 7. 次のステップ候補

- ~~`_maybe_handle_launch_announcement_command()`相当のコマンド配線~~
  → 8節の通り実施済み。
- FAQコマンド案内文(owner_faq_router.py `_OWNER_FAQ_ITEMS`)への「告知文」コマンドの
  周知文言追記(6節で指摘した「オーナーがコマンド名を思いつくか」問題への対応)。
- customer-interview-design.mdのヒアリング項目に、告知文の実用性・使いたいと思うかを
  確認する設問を追加できないか検討する。
- friend_add_url(現状FRIEND_ADD_URL_PLACEHOLDERの差し込みのみ)を、実LINE公式
  アカウント開設後にConversationEventProcessorのコンストラクタ引数として実際の
  友だち追加URLを渡すよう接続する(pending-approval.md記載のLINE公式アカウント
  開設承認待ちに紐づく)。

## 8. 実装状況(2026-09-18 03:00 UTC定例更新)

`prototype/launch_announcement_draft.py`に`is_launch_announcement_trigger()`
(reply_textが「告知文」と完全一致するかを判定する純粋関数、前後空白は無視)と
`FRIEND_ADD_URL_PLACEHOLDER`定数を追加した。`prototype/cloud_function_process_event.py`
の`ConversationEventProcessor`に、owner_faq_router.pyと同じ設計思想の
`_maybe_render_launch_announcement_reply()`を追加し、オーナー本人確定時のみ
「FAQ」判定の直後に「告知文」判定を行うよう`_process_message_event()`へ配線した。
コンストラクタに`friend_add_url`(未指定時はFRIEND_ADD_URL_PLACEHOLDER)を追加し、
`store_name_provider.get_business_name()`から取得した店舗名が空文字列の場合
(店舗設定未登録)は実際の下書き生成を行わず、5節・6節で検討した「営業情報設定を
先に完了してください」という案内文言(`_LAUNCH_ANNOUNCEMENT_MISSING_STORE_NAME_
MESSAGE`)を返す安全側フォールバックとした。テスト9件(launch_announcement_draft
側3件・cloud_function_process_event側6件)を追加し、venture全体844件・schema検証
27件いずれもパスを確認した。
