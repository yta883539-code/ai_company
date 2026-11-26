# 解約・ダウングレード意図検知時 トーク画面モックスクリプト

## 位置づけ

step4-non-happy-path-mock-script.md「次のステップ候補」(2)「他venture・アイデア領域の
前進」、および本venture内で最も更新が止まっていた状態への対応として、
subscription-cancellation-flow-design.md・schema/validate_test_cases.pyの
`C1_cancellation_intent`/`C2_downgrade_intent`/`C3_cancellation_unclear`を素材に、
解約・ダウングレード意図検知時のやり取りをトーク画面の文面としてモックスクリプト化した。
既存のstep4系モックスクリプト(production-usage・non-happy-path・multi-craftsman-member-
usage)はいずれも通常の依頼メモ生成ケースのみを対象としており、解約・ダウングレード導線を
対象としたモックスクリプトはこれまで未作成だった。実LINE公式アカウント・実LLM API・実Stripe
カスタマーポータルの接続は一切行っていない。

## モック対象ケース

- `C1_cancellation_intent`: 入力「解約したい」
  (`prototype/test_cloud_function_webhook.py`の
  `test_process_memo_event_cancellation_intent_replaces_portal_placeholder()`で
  実際に使用されている入力文言をそのまま採用)
- `C3_cancellation_unclear`: 入力「やめようかな」
  (同ファイルの`test_process_memo_event_cancellation_unclear_does_not_need_provider()`で
  実際に使用されている入力文言をそのまま採用)
- `C2_downgrade_intent`: 入力「プランを変更したい」
  (`prototype/test_cloud_function_webhook.py`には`C2_downgrade_intent`を直接使用する
  テストが存在しないため、この入力文言は既存テストケースからの引用ではなく、
  subscription-cancellation-flow-design.md「ダウングレード(プラン変更)フロー」の記述を
  踏まえて本ドキュメントのために新たに作成した例文である。この点はC1・C3との違いとして
  明記する)
- 非契約者(複数職人プランの追加メンバー)からの`C1_cancellation_intent`相当の入力
  (フェーズ続き334で配線した`CONTRACTOR_ONLY_CANCELLATION_NOTICE`分岐を可視化するための
  ケース。workshop構成はstep4-multi-craftsman-member-usage-mock-script.mdと同じ前提
  〈契約者A・招待コード経由で参加済みの職人B〉を踏襲し、新しい事実確認・WebSearch調査は
  行っていない)

## トーク画面の見え方(案)

```
[LINE公式アカウント「鞍パシャッと」とのトーク画面(本番運用中)]

(契約者本人から送信)
解約したい

(アプリから自動返信・subscription_procedure_notice.bodyのプレースホルダを
 実Stripeカスタマーポータルの実URLへ置換して返す〈portal_link_provider接続時〉)
解約をご希望とのことで承知しました。現在のご契約内容をご確認のうえ、下記リンクから
解約手続きをお願いいたします。手続き完了後も今回のご請求サイクルの終了日まではサービスを
ご利用いただけます。
https://billing.stripe.com/p/session/abc123
```

```
[同トーク画面・別のやり取り(portal_link_provider未接続時のフォールバック)]

(契約者本人から送信)
解約したい

(アプリから自動返信・PORTAL_LINK_UNAVAILABLE_FALLBACKを返す)
現在、お手続きページの発行に失敗しました。お手数ですが、しばらく経ってから再度
このメッセージを送信いただくか、サポート窓口まで直接ご連絡ください。
```

```
[同トーク画面・ダウングレード意図のケース]

(契約者本人から送信)
プランを変更したい

(アプリから自動返信・C2_downgrade_intentのbodyをそのまま返す)
プラン変更をご希望とのことで承知しました。下記リンクからご希望のプランへの変更手続きを
お願いいたします。日割り差額は変更申込み時点で精算されます。
```

```
[同トーク画面・解約意図か判別しづらいケース]

(契約者本人から送信)
やめようかな

(アプリから自動返信・C3_cancellation_unclearのbodyをそのまま返す)
解約をご希望でしょうか?よろしければ「解約したい」とお送りください。
```

```
[LINE公式アカウント「鞍パシャッと」とのトーク画面(職人B本人のLINEアカウント、
 工房への参加〈招待コード解決〉完了後。契約者はAで、Bは追加メンバー)]

(職人B本人から送信・契約者Aを介さない直接の解約意図表明)
解約したい

(アプリから自動返信・user_id != workshop_store.get_contractor_user_id(workshop_id)判定が
 真となり、CONTRACTOR_ONLY_CANCELLATION_NOTICEをそのまま返す〈フェーズ続き334で配線〉)
解約・プラン変更のお手続きは、契約者(工房を最初に作成した方)のみ操作できます。
お手数ですが、契約者の方からご確認・お手続きください。
```

## 注記・限界

- C1の1つ目の例(実URL置換版)は`_cancellation_intent_case_with_portal_placeholder()`が
  合成した`PORTAL_LINK_PLACEHOLDER`入りのフィクスチャを素材としており、
  `TEST_CASES["C1_cancellation_intent"]`自体のbody文字列には
  `_cancellation_intent_case_with_portal_placeholder()`のコメントが指摘するとおり
  プレースホルダ文字列が literal には含まれていない。本ドキュメントでは
  `render_subscription_procedure_notice()`による置換後の見え方を示すため、
  テストコード側の合成フィクスチャの構成をそのまま踏襲した。
- C1の2つ目の例(フォールバック版)の文面は`prototype/cloud_function_webhook.py`の
  `PORTAL_LINK_UNAVAILABLE_FALLBACK`定義(610行目付近)を直接確認し、その文字列を
  そのまま採用した。
- C2(ダウングレード)の入力文言「プランを変更したい」は、上記のとおり既存テストケースからの
  引用ではなく本ドキュメントのための例文であり、実LLMがこの入力から実際に
  `downgrade_intent`へ分類できるかはoutput-samples-validation.md「残る未検証事項」と
  同様に実LLM接続後(オーナー承認待ち)の検証課題として引き続き未検証。
- ~~複数職人プランにおける「契約者本人以外からの解約・ダウングレード意図表明」への案内
  (「契約者様にご確認ください」)は、subscription-cancellation-flow-design.md「複数職人
  プラン固有の論点」の仮決め方針であるが、`prototype/cloud_function_webhook.py`の
  cancellation_intent/downgrade_intent処理経路(`format_reply_text()`696〜698行目)には、
  checkout_intent処理(`resolve_checkout_intent()`1950行目)やmember_retention・
  contractor_transfer処理(1534・2255行目)と同様の`user_id != workshop_store.
  get_contractor_user_id(workshop_id)`判定がまだ配線されていない(2026-11-24フェーズ続き331
  で「契約者本人」の判定方法自体〈craftsman-account-linking-design.md 4節〉は解決済みと
  判明したが、その判定をcancellation系statusへ実際に組み込む実装はまだ別課題として残る)。
  本モックスクリプトでも、この未配線を理由に対象外のまま持ち越す。~~
  → 2026-11-25フェーズ続き334で配線完了。`process_memo_event()`のcheckout_intent分岐の
  直後に同型のelif分岐を追加し、契約者本人以外からのcancellation_intent/downgrade_intentに
  新設の`CONTRACTOR_ONLY_CANCELLATION_NOTICE`を返すようにした(cancellation_unclearは
  厳守事項7a(iv)の意思確認一言のみの性質を変えないため対象外のまま)。
  → 2026-11-26フェーズ続き335で、非契約者(職人B)からの`C1_cancellation_intent`相当入力を
  題材にした新規モックケースを本ファイルに追加し、CONTRACTOR_ONLY_CANCELLATION_NOTICEが
  実際にトーク画面上でどう見えるかを可視化した(C2相当・ダウングレード側の非契約者ケースは
  文面が解約側と同一〈`CONTRACTOR_ONLY_CANCELLATION_NOTICE`は分岐の入口がcancellation_intent/
  downgrade_intent共通のため〉で新たに示す情報が増えないと判断し、追加は見送った)。
- 本番運用時のやり取りである前提(実LINE公式アカウント接続・オーナー承認待ち)自体は
  他のstep4系モックスクリプトと同じ限界が残る。

## 次のステップ候補

- 他venture・アイデア領域の前進。

最終更新: 2026-11-26 18:00 UTC(フェーズ続き335: 非契約者〈職人B〉からの解約意図表明が
CONTRACTOR_ONLY_CANCELLATION_NOTICEを返すケースをモックスクリプトに追加)。
