# 初回daily入力成功時の確認案内の設計(フェーズ226)

作成日: 2026-11-09(フェーズ226)

onboarding-guide.md(フェーズ225)「未検証の仮説」2点目(手順3〈接続テスト〉を事業者が
実際に自発的に行うか、省略していきなり本番のdaily入力を開始し、試験入力のつもりで送った
内容がそのまま`vehicle_id`として本登録されてしまうリスク)、および同ファイル「次のステップ
候補」1点目に対応する。kura-pasha/first-generation-self-check-notification-design.md
(フェーズ178)の構成・考え方を踏襲しつつ、本venture固有の構造(事業者単位契約・
vehicle_id自動発行・3区分の利用頻度差)を反映する。

**本ドキュメントは設計のみを行うものであり、実装(コード変更)は次フェーズ以降の課題とする。**

## 1. 前提の確認

- 契約単位は`fleet_operator/{internal_id}`(事業者単位)であり、kura-pashaのworkshopの
  ような複数メンバーの共有構造は本ventureには存在しない(1事業者=1アクセストークン、
  access-token-reissue-design.md)。この点ではkura-pashaより判定基準の検討は単純になる。
- `form_submission_flow.process_form_submission()`がstatus="generated"の場合のみ
  `record_generation_and_get_trial_end_notice()`を呼び、response_textに追記して返す構造
  (course-set-pasha/line-reservation-ai等の`format_generated_reply()`相当の末尾追記ポイント)
  を、本確認案内もそのまま利用する。
- schema/output.schema.jsonのinstanceにはdaily/monthly/annualの区分(`type`フィールド、
  URLで確定・web-form-ui-design.md「設計方針」)が含まれており、`process_form_submission()`
  側でもinstanceを受け取った時点でこの値を参照できる。

## 2. 判定基準の検討: なぜ「daily区分かつ事業者単位の初回」に限定するか

kura-pashaのworkshop単位(2節)と異なり、本venture側で検討が必要なのは「複数メンバー」では
なく「3区分のうちどれを対象にするか」という軸である。

1. **daily区分に限定する理由**: onboarding-guide.mdの「未検証の仮説」が懸念しているのは、
   手順3の接続テストが実際にはdaily入力画面(web-form-ui-design.md「daily区分の入力画面」、
   想定3タップで完了する最も使われる画面)で行われる想定であり、月1回・年1回しか使われない
   monthly/annual区分で「初回入力」を待っていては、確認案内が事業者にとって意味を持つ
   タイミング(接続テスト直後)から大きく外れてしまう(monthlyなら最大1か月後、annualなら
   最大1年後になりかねない)。したがって、確認案内はdaily区分の初回成功時にのみ出し、
   monthly/annual区分は対象外とする。
   - monthly/annual区分についても同種の確認案内が必要かどうかは、4節末尾の「次のステップ
     候補」に残す(daily区分での運用実績を見てから判断する)。
2. **事業者単位(`internal_id`)で判定する理由**: 1節の通り本ventureにはworkshopのような
   複数メンバー共有構造が無いため、kura-pashaが行った「ユーザー単位かworkshop単位か」の
   検討は不要で、契約単位である`internal_id`そのものを判定キーとすればよい。

## 3. 方針

- **判定基準**: その`internal_id`にとって最初の「daily区分かつstatus="generated"」の成功時
  (`instance.get("type") == "daily"`かつstatus="generated"の場合のみ)に、通常の応答
  (`response_text`、`record.body`+任意の`reminder_notice`)の末尾に確認案内を1回だけ
  付記する。2回目以降(同一事業者の2回目以降のdaily送信、およびmonthly/annual送信)は
  付記しない。
- **永続化**: kura-pashaと同じ理由(サーバーレス関数のインメモリフラグは再起動・インスタンス
  使い捨てのたびに失われる)で、`fleet_operator/{internal_id}`ドキュメントへ
  `firstDailyGenerationNoticeSent: bool`フィールドを永続化する。`FleetOperatorStoreProtocol`
  (`prototype/trial_management.py`)へ`get_first_daily_generation_notice_sent(internal_id)
  -> bool`・`set_first_daily_generation_notice_sent(internal_id) -> None`を追加する想定とし、
  既存の`get_trial_start_at`/`set_trial_start_at`等と同じ「初回のみ設定・以降不変」の形を
  踏襲する(firestore-data-model.mdへの反映、`InMemoryFleetOperatorStore`・
  `FirestoreFleetOperatorAdapter`両方への実装は次回候補とする)。
- **実装位置**: `form_submission_flow.process_form_submission()`内、status=="generated"
  確定後・`record_generation_and_get_trial_end_notice()`呼び出しと同じ分岐(5.の処理順序)
  に追加する。post_generation_checks(厳守事項違反検知)とは責務が別であるため混在させない
  (kura-pashaと同じ方針)。
  - 呼び出し順序としては、トライアル終了通知(`trial_end_notice`)より先に本確認案内を
    追記する(初回daily成功は定義上トライアル開始直後であり、トライアル終了通知が同時に
    発生することは実務上ほぼ無いが、両方が発生した場合は「まず内容確認、次に契約状態」の
    順で伝える方が読み手にとって自然なため)。

## 4. 確認案内の文面案

`response_text`(`record.body`+任意の`reminder_notice`)の末尾に、改行を挟んで追記する。
tone-and-manner-guideline.mdの方針(ですます調・絵文字不使用、実務記録のため宛名等の装飾は
付けない)に合わせる。

```
【ご確認のお願い】これが最初の点検記録です。車両番号の表記や記録内容が意図通りか、この
機会にご確認ください。表記を変えて送ると別の車両として扱われますので、今後は同じ表記で
送ることをおすすめします。問題がなければ今後この案内はありません。
```

- kura-pashaの文面と異なり「表記を変えると別車両として扱われる」旨を明示する一文を加えた。
  理由は、vehicle-label-duplicate-handling-design.md 3節が確定した「完全一致のみで重複判定、
  表記ゆらぎの吸収はしない」という本venture固有の仕様が、まさに onboarding-guide.mdの
  「未検証の仮説」が懸念する典型的な事故(タイプミスがそのまま別車両として本登録される)の
  直接の原因であり、事業者が初回成功時に最も確認すべき点そのものだからである。kura-pashaの
  workshop名確認(表示設定の確認)とは異なり、本venture側は「表記の一貫性」という運用上の
  注意点そのものを案内に含める方が実効性が高いと判断した。
- course-set-pasha/kura-pasha同様、この案内自体は入力内容に応じて変わる余地が無く自然文
  解釈を必要としないため、LLM呼び出しを経ないPython側の決定論的テンプレート(固定文言)
  とする。

## 5. 関連して発見した、web-form-ui-design.mdとの整合性の懸念(次回候補)

本設計の検討過程で、本venture内の2つの既存設計文書の間に、車両番号入力方式についての
記載齟齬の疑いを発見した。

- vehicle-label-duplicate-handling-design.md(フェーズ114、`prototype/vehicle_registry.py`
  としてフェーズ149に実コード化済み)は、`vehicleLabel`を点検メモの**自由記述**から取得し、
  `(operatorInternalId, vehicleLabel)`の完全一致で既存車両かどうかを判定し、一致しなければ
  **新規車両として自動発行**する方式を確定・実コード化している。事前の「車両登録」という
  独立したステップは想定していない。
- 一方web-form-ui-design.md(フェーズ77〜205、vehicle-label-duplicate-handling-design.mdより
  後に多数のフェーズを経て更新されている)は「車両番号: プルダウン(事業者が保有する車両を
  あらかじめ登録、vehicle_idに対応)」「車両番号必須選択」と記載し、daily/monthly区分とも
  車両番号をボタン/プルダウンからの**選択のみ**とする設計になっており、自由記述欄や
  「新しい車両を追加」に相当する操作は一切記載されていない。
- この2つを単純に重ねると、**契約直後(保有車両が0台の時点)に最初の車両をどう入力に
  反映させるか**の経路が設計上存在しないことになる(プルダウン/ボタンの選択対象となる
  「あらかじめ登録された車両」が、本venture側には「車両登録」という独立したUI・APIが
  一切存在しないため、何も表示されない空のプルダウンになってしまう)。
- 本フェーズでは、この記載齟齬自体の是正(どちらの方式に統一するか)は範囲外とし、
  次回候補として記録する。考えられる解消方向としては、(a)web-form-ui-design.mdの
  「プルダウン」記載を「既存車両はプルダウン選択、未登録表記は自由記述欄で新規入力可」に
  修正しvehicle_registry.pyの自由記述方式と整合させる、(b)逆にvehicle-label-duplicate-
  handling-design.mdの自由記述方式を改め、事業者が別途「車両登録」操作を行う専用UI・APIを
  新設する、のいずれかが考えられるが、どちらが望ましいかは実際のフォーム実装時
  (web-form-mockup/)に合わせて判断すべき事項であり、本フェーズでは断定しない。
  なお、本5節の懸念は4節の確認案内の文面(「表記を変えると別の車両として扱われる」)の
  前提である「車両番号を自由記述できる」という理解と直接関わるため、(a)の方向で解消される
  蓋然性が高いと考えるが、確定事項ではない。

## 6. 未検証の仮説・残課題

- 5節の記載齟齬が実際にどちらの方向で解消されるかにより、4節の確認案内文面(「表記を変える
  と別の車両として扱われる」という一文)の妥当性も変わりうる。(b)の方向(専用の車両登録UI
  新設)で解消された場合、車両番号入力自体が選択式に統一され表記ゆらぎのリスクが構造的に
  下がるため、この一文は不要になる可能性がある。
- monthly/annual区分についても同種の確認案内が必要かどうかは、daily区分での運用実績
  (オーナー承認待ちの実メール送信・実Stripe/実GCP接続後)を見てから判断する。
- 実装自体(`FleetOperatorStoreProtocol`への2メソッド追加、firestore-data-model.mdへの
  フィールド反映、`process_form_submission()`側の配線、統合テスト追加)は本フェーズでは
  行わず、次フェーズ以降の課題とする。

最終更新: 2026-11-09 21:00 UTC(フェーズ226: 新規作成。onboarding-guide.mdが次のステップ
候補としていたkura-pasha相当のセルフチェック案内を本venture向けに検討。事業者単位契約・
vehicle_id自動発行という構造を踏まえ、判定基準を「daily区分かつ事業者単位の初回」とする点、
文面に「表記を変えると別車両扱いになる」という本venture固有の注意点を含める点を確定した。
検討過程でweb-form-ui-design.md(車両番号はプルダウン選択のみ)とvehicle-label-duplicate-
handling-design.md/vehicle_registry.py(車両番号は自由記述から自動発行)との間の記載齟齬
(契約直後・車両0台時点の入力経路が設計上存在しない)を発見し、5節に記録・次回候補とした。
設計のみでコード変更は無し。)
