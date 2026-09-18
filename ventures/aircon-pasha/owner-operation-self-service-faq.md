# 契約者(施工業者・管理会社)向け運用セルフサービスFAQ(初回メモ、2026-09-15 22:00 UTC・フェーズ224)

course-set-pasha/owner-operation-self-service-faq.md・line-reservation-ai/owner-
operation-self-service-faq.mdが、cross-venture-support-cost-comparison.md
(kura-pashaフェーズ123)の指摘(サポート負荷軽減策の検討)を受けて作成済みであり、
両ドキュメント末尾「次のステップ候補」に「他venture(course-set-pasha・aircon-pasha・
kura-pasha)でも同種のFAQが未整備であれば横展開を検討する」旨の記載があった。
support-cost-estimate.md(本ventureフェーズ222)・フェーズ223でも「サポート負荷軽減策
(FAQ整備等)の具体的検討」が次回候補として挙げられていた。本venture(aircon-pasha)には
まだ同種のFAQが存在しなかったため、本ドキュメントで着手する。

## 前提: line-reservation-aiとの構造の違い

line-reservation-aiは「来店客(エンドカスタマー)」と「店舗オーナー(契約者)」が別人で
あり、来店客向けFAQ(厳守事項9a系)とオーナー向けFAQ(本ドキュメント相当)が別レイヤー
として存在する。

一方、本ventureにも「テナント(入居者)」という完了報告の宛先が存在するが、テナントは
本サービスの利用者ではなく、あくまで**訪問施工完了報告を作成する施工業者自身、または
BtoBプランで契約する管理会社が契約者=本サービスの利用者**である
(README.md「対象顧客」、pricing-plan.md)。この点はcourse-set-pasha(ジムオーナー・
セッター自身が契約者)と同じ構造であり、本ドキュメントが扱う「セルフサービスFAQ」は、
契約者(施工業者・管理会社)が運営者(本サービスの提供者)に直接尋ねる問い合わせを
自己解決できるようにするための文書、という位置づけになる。

なお本venture固有の事情として、来店客向けの自動応答チャットボット
(faq-escalation-boundary.md相当)が存在しないため、line-reservation-aiのFAQにあった
「エスカレーション挙動の説明」項目は本ドキュメントには存在しない(course-set-pashaと
同じ)。

## 想定される用途

- course-set-pasha・line-reservation-aiと同様、オンボーディング完了メッセージ
  (onboarding-guide.md)の末尾や将来のヘルプメニューから本FAQへのリンクを案内する想定
  (導線の実装は別途要検討、本フェーズはFAQ本文の内容整理にとどめる)。
- 運営者への問い合わせが来た際、本FAQの該当項目をそのまま案内文として返信できるように
  し、個別文章作成の手間を減らす。

## FAQ項目

### Q1. 料金プランを変更したい(アップグレード/ダウングレード)
Stripeカスタマーポータル(portal-session-provider-design.md)経由で契約者自身がプラン
変更できる想定(course-set-pasha・line-reservation-aiと同じ設計方針)。変更後の
プランはWebhookイベント受信時に自動更新される想定。運営者側の手作業は不要。

### Q2. 無料トライアルはいつまで?延長できる?
初回の作業完了報告生成成功から14日間、または生成10回到達のいずれか早い方まで無料
(pricing-plan.md、起点の確定はtrial-start-anchor-decision.md参照)。トライアル終了が
近づくとLINE通知が届き(trial-end-notification-design.md、
trial-end-condition-a-cta-design.md)、クレジットカード登録なしで開始できるため自動
課金は行われない。終了時点で有料プランを選ばなければ利用が制限モードに移行するだけで、
意図しない請求は発生しない(restricted-mode-cancellation-message-copy-review.md)。
延長自体は現時点で仕組み化されておらず、個別相談が必要な場合は運営者への問い合わせが
必要(course-set-pashaのQ2・line-reservation-aiのQ4と同じ、未実装機能)。

### Q3. 解約したい/解約後の再開はどうなる?
Stripeカスタマーポータルから契約者自身が解約手続きできる
(subscription-cancellation-flow-design.md)。解約は現在の請求期間終了時点で有効になり、
それまでは通常通り利用できる。LINEをブロックしただけでは解約にならない点、ブロック後も
課金が続く場合の問い合わせ対応はunfollow-billing-faq.md参照。本venture固有の補足として、
「ブロック中かつ契約継続中」の候補は運営者へ自動通知される仕組みが既にある
(blocked-but-billing-owner-notification-design.md)ため、業者本人が気づかなくても
運営者側から事後対応できる可能性がある点がcourse-set-pashaと共通する。

### Q4. 複数職人・複数拠点での共同利用をしたい(繁忙期対応プランの複数職人共有)
繁忙期対応プラン(月額8,980円)は、1つのLINEアカウントを事業所内で複数職人が共有運用する
前提で設計されている(pricing-plan.md、multi-technician-shared-usage-design.md)。
course-set-pashaのセッター複数プランと異なり、本ventureは「1メモ送信=1台の訪問施工完了
報告」という単方向バッチ処理のため、複数職人が同一LINEアカウントから順にメモを送信する
運用を想定している(詳細はmulti-technician-shared-usage-design.md参照)。個々の職人ごとに
LINEアカウントを分けたい場合は、職人ごとに別契約(別プラン)が必要になる想定。

### Q5. 月間生成回数の上限に達した/超過分の課金はどうなる?
本ventureは上限到達時に生成を止めるのではなく、従量課金(プランごとに40〜60円/回)で
継続利用できる方式を採用している(pricing-plan.md「プラン案」表)。梅雨〜夏場の繁忙期
(施工件数が閑散期の2〜3倍程度に増える可能性)でもサービスが使えなくなることはない。
上限に近づいた際の通知内容・タイミングはlimit-approaching-notification-design.md参照。

### Q6. 管理会社向けプランと個人向けプランの違いは?どちらで契約すればよい?
施工業者本人が個人向けプラン(スモール/スタンダード/繁忙期対応)で契約する場合と、
物件を管理する管理会社自身が管理会社向けプラン(管理会社ライト/スタンダード、戸数課金)
で契約する場合の2通りがある(pricing-plan.md「管理会社向け一括契約プラン」節)。
施工業者側の個人向けプランと管理会社向けプランが同一物件で二重に課金されることは
想定しておらず、いずれか一方(施工業者が個人向けプランで契約し出力を管理会社へ転送
するか、管理会社自身が管理会社向けプランで契約し提携業者からのメモ入力を受け付ける
か)の排他的な契約形態を案内する。完了報告の宛先(recipient: tenant/management_
company)はメモの記載(「宛先:管理会社」等)からLLMが判定する
(llm-system-prompt-draft.md厳守事項9)。なお料金水準・戸数区分はいずれも実際の
管理会社へのヒアリング(オーナー承認待ち、pending-approval.md記載)前の仮設計である旨、
問い合わせ時には留保付きで案内する必要がある。

### Q7. 生成された完了報告・お手入れ案内の内容がイメージと違う
実際の施工内容・原因判断・是非の最終判断は職人本人が行う前提であり、本サービスは下書き
生成にとどまる(course-set-pashaのQ6と同じ構造)。送信するメモの粒度(交換・清掃した
部品、症状と対処内容、食洗機可否等の取り扱い条件を具体的に書く)を調整することで生成
内容の精度が上がりやすい旨を案内する(llm-system-prompt-draft.md参照)。個別の生成結果の
修正代行は運営者側では行わない。

## 未検証の仮説(要検証)

- course-set-pasha・line-reservation-aiのFAQと同様、本FAQへの導線(オンボーディング完了
  メッセージへのリンク等)が未設計であり、FAQ本文を用意しただけでは支援コスト削減効果は
  限定的。
- Q6(管理会社向けプランと個人向けプランの使い分け)が、契約者にとって文章だけで直感的に
  理解できるかは実際の問い合わせが蓄積されるまで未検証。本venture固有の分岐(BtoB/BtoC
  併存)であり、他3venture(BtoCのみ)より問い合わせが複雑になりやすい懸念がある。
- 本FAQで扱った7項目が実際の問い合わせの主要因をどの程度カバーできているかは、
  support-cost-estimate.md「残課題」と同じく実運用データが無いため不明。

## 次のステップ候補

- (解消済み・フェーズ225 owner-faq-routing-design.md: line-reservation-aiと同じ
  コマンド方式〈トークルームで「FAQ」→「Q1」〜「Q7」〉を本venture向けにも実装済み。
  `prototype/owner_faq_router.py`・`cloud_function_webhook.py`の
  `is_owner_faq_menu_trigger()`分岐として導線が完成している)
- 実運用データが取得でき次第、実際の問い合わせ内容とFAQ項目の一致率を検証する。
- (解消済み 2026-09-18確認: 残る1venture〈kura-pasha〉についても
  `prototype/owner_faq_router.py`〈フェーズ126、line-reservation-aiのフェーズ続き233と
  同設計〉で同種のコマンド方式セルフサービスFAQが実装済みであることを確認した。これで
  4venture全てにオーナー向けセルフサービスFAQのコマンド方式導線実装が完了している)
