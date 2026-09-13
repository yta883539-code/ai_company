# 鞍パシャッと

個人〜小規模で活動する鞍職人(馬具師、乗馬用の鞍・轡・手綱・鐙革等の馬具を新規制作・修理・
調整する職人)向けに、依頼内容の簡単なメモを送るだけで、AIが(1)受注内容整理メモ、
(2)納品案内下書き、(3)お手入れ案内下書き、の3つをまとめて生成するサービス。

## 概要

- 対象顧客: 乗馬クラブ・牧場からオーダーメイド馬具の制作・修理依頼を受ける個人〜小規模の
  鞍職人(馬具師)、個人の馬主向けに直接販売する独立系の馬具作家。
- 入力: 職人が入力する簡単なメモ(例:「ブリティッシュ鞍、牛革、競技用、納期3ヶ月」等)。
- 出力: (1)受注内容整理メモ(馬体のサイズ・鞍の型・革の種類・金具仕様・用途・納期の
  聞き取り内容を整理したメモ)、(2)納品案内下書き(装着時の皮革のなじませ方、初期の
  締め具合調整の必要性、雨天時の取り扱い注意)、(3)お手入れ案内下書き(オイル・クリームでの
  定期的な革の保湿、カビ・ひび割れ防止のための保管環境、金具のさび防止手入れ)。
- 実際の採寸・型紙作成・革選定・縫製・仕上げ等の専門的な制作作業・判断は職人本人が行う
  前提とし、本サービスは事務作業(整理・下書き作成)の支援のみを行う。会員管理・予約受付・
  決済に関する高度な機能はMVPの範囲外とする(course-set-pasha/aircon-pashaと同型の
  「パシャッと」シリーズの方針を踏襲)。

## 原案

- ideas.md 2026-09-06 02:00 UTCの原案(名前:「鞍パシャッと」)を踏襲。

## ステータス

- フェーズ1(2026-09-06 03:00 UTC): venture新規作成。WebSearchで国内の鞍・馬具修理/
  オーダーメイド業者の実在確認(market-research.md)と、MVPの入出力フォーマット草案
  (mvp-flow-draft.md)を作成した。承認不要な調査・下書き作成のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。
- フェーズ2(2026-09-06 04:00 UTC): llm-system-prompt-draft.mdを新規作成した。
  course-set-pasha・aircon-pashaの既存草案の構成(できること/厳守事項/構造化出力)を
  参考にしつつ、本ventureには継続課金・解約フローが存在しないため解約意図検知
  (course-set-pashaの厳守事項7a相当)は設けず単純化した。区分(新規制作/修理)に応じた
  出力2(納品案内)の分岐、修理可否判断への不介入(mvp-flow-draft.mdの方針を踏襲)を
  厳守事項として明文化した。実装・実LLM検証は未着手。承認不要な設計文書作成のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ3(2026-09-06 05:00 UTC): schema/output.schema.jsonを新規作成した。
  aircon-pasha/course-set-pashaのstatus分岐パターン(generated/out_of_scope/
  insufficient_input)を踏襲し、category(new/repair)整合性検証用フィールドを
  order_summary・delivery_notice双方に持たせた。実LLMでの動作検証は未実施。
- フェーズ4(2026-09-06 06:00 UTC): schema/validate_test_cases.pyを新規作成した。
  course-set-pashaのvalidate_test_cases.pyと同じ簡易バリデータ方式(pure stdlib、
  draft-07のサブセットのみ解釈)を踏襲し、G1(新規制作)・G2(修理、備考欄の症状転記)・
  OOS1(会員管理等への不応答)・II1(区分欠落)・II2(鞍の型欠落)の5ケースに加え、
  厳守事項4(order_summary.categoryとdelivery_notice.categoryの一致)違反を意図的に
  仕込んだネガティブケースを1件作成し、バリデータがその不整合を実際に検出できることを
  確認した。全6件パス。実LLM呼び出しは行っていない(APIキー取得はオーナー承認待ち、
  pending-approval.md参照)。

- フェーズ5(2026-09-06 07:00 UTC): 「次にやること」1点目だった料金プラン・無料トライアル
  条件の仮決めを行った(pricing-plan.md新規作成)。course-set-pasha/pricing-plan.mdの
  月間生成回数ベースの設計方針を踏襲しつつ、本venture固有の受注特性(納期数ヶ月に及ぶ
  オーダーメイドが中心で受注件数自体が少ない)に合わせ、生成回数枠を大幅に下げ従量単価を
  高めに設定した3プラン(ライト/スタンダード/複数職人)とした。トライアル条件も
  「回数基準(生成5回等)だと受注頻度の低さゆえに実質無期限化しうる」と判断し、
  期間上限(30日)を優先する設計に変更した。実LLM呼び出し・実際の受注頻度検証は
  引き続き未実施。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ6(2026-09-06 09:00 UTC): 「次にやること」1点目だったLLM API利用コスト試算を
  行った(llm-api-cost-estimate.md新規作成)。course-set-pasha/aircon-pashaの試算構成を
  踏襲し、本venture固有のプロンプト・スキーマ規模(合計約13,894文字)に基づきシナリオA/B
  で試算した結果、最も保守的な組み合わせ(Opus 5・シナリオB・キャッシュなし)でも
  最安従量単価(150円)の約5.7%にとどまり、pricing-plan.mdの単価設計を圧迫しないとの
  結論を得た。また本venture固有の低頻度利用特性(受注件数の少なさ)ゆえにプロンプト
  キャッシュの効果が薄い可能性が高いことも確認した(キャッシュなし前提でも粗利は
  十分に残るため、実装優先度は他ventureより下げてよいと判断)。実LLM呼び出しは未実施。
  承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ7(2026-09-06 10:00 UTC): 「次にやること」1点目だった対象候補(実在の鞍職人・
  馬具師)のロングリスト作成にWebSearchで着手した(candidate-longlist-draft.md新規作成)。
  ライディングショップ池上(千葉県の名工・池上豊氏)、LEVOL、Apion-leather craft lab、
  エクウスワールド、馬具職人工房(Creema/Instagram)の5件を候補として記録し、大手メーカー
  (ソメスサドル)は個人〜小規模という対象顧客像に合わないため除外条件とした。実際の連絡・
  ヒアリング依頼は行っておらず、着手する場合は別途pending-approval.mdへの記録・オーナー
  承認が必要である旨をドキュメント内に明記した。承認不要な公開情報調査・記録のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ8(2026-09-06 13:00 UTC): 「次にやること」1点目だった選定基準ドキュメントを
  新規作成した(interview-candidate-selection-criteria.md)。aircon-pasha/course-set-pasha/
  line-reservation-aiの既存選定基準の構成(必須条件・望ましい条件・除外条件・情報源・
  選定プロセス)を踏襲しつつ、本venture固有の除外条件(馬具の販売・仲介のみを行い自ら
  制作・修理を行わない小売・卸業者、乗馬クラブ専属スタッフとしてのみ修理を担当し独立した
  受注を行っていない者)を追加した。候補が5件と他ventureの目標合計(8〜10件)より少ない
  ため、選定プロセスに3〜5件の追加探索によるロングリスト拡充を組み込んだ。実際の連絡・
  ヒアリング依頼は行っておらず、着手する場合は別途pending-approval.mdへの記録・オーナー
  承認が必要である旨を明記した。承認不要な設計文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ9(2026-09-06 14:00 UTC): 「次にやること」1点目だった候補拡充のための追加探索
  (3〜5件)をWebSearchで実施し、candidate-longlist-draft.mdを更新した。「馬具 修理 個人
  工房」「サドラー 鞍職人 独立 開業」等複数のキーワードで探索したが、上位に再表示されたのは
  既存5候補とソメスサドル(除外済み)がほとんどで、新規に発見できた個人〜小規模候補は
  ジャパンギャロップスインポーター有限会社(輸入代理店・小売が事業の中心と見られ除外条件に
  該当する可能性が高いため保留)1件のみだった。この結果から、本venture固有の候補母数が
  構造的に少ないことを確認し、目標合計を他venture(8〜10件)水準ではなく現実的な5〜6件程度
  (保留候補を含めて最大6件)に見直す方針とした。実際の連絡・ヒアリング依頼は行っておらず、
  着手する場合は別途pending-approval.mdへの記録・オーナー承認が必要である旨を明記した。
  承認不要な公開情報調査・記録のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ10(2026-09-06 15:00 UTC): 「次にやること」1点目だった第一弾5候補の優先順位付け
  を、interview-candidate-selection-criteria.mdの選定プロセスに沿ってWebSearchによる追加
  確認とともに実施した(candidate-longlist-draft.md「第三弾」)。ライディングショップ池上
  (所在地・個人事業である旨を公式サイトで確認)を最優先候補と確定し、馬具職人工房・
  Apion-leather craft labは望ましい条件を満たすが留保事項付きで候補継続、エクウスワールド
  (運営:トライ企画、代表・伊藤政男氏)は通販サイトとしての性格が強く除外条件該当の有無を
  次回追加確認する保留寄りの扱いとし、LEVOLは検索結果に無関係な同名の別会社(埼玉県川口市の
  美容サロン系「株式会社レボル」)が混在したため誤結合を避けて運営者情報の確定を次回に持ち
  越した。実際の連絡・ヒアリング依頼は行っておらず、着手する場合は別途pending-approval.mdへの
  記録・オーナー承認が必要である旨を明記した。承認不要な公開情報調査・記録のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.md
  への追記なし。

- フェーズ11(2026-09-06 16:00 UTC): 「次にやること」1点目だったLEVOLの運営体制の追加確認を
  WebSearchで行った(candidate-longlist-draft.md「第四弾」)。levol.co.jp/?page_id=40への
  直接アクセスはWebFetchツールがネットワークegressポリシーによりlevol.co.jpドメインを
  ブロックしたため今回も一次情報への到達はできなかったが、検索スニペット経由で(1)LEVOLの
  本業が乗馬靴(履物)のフルオーダー・修理専門店であり、鞍等の馬具修理は対応可能な範囲での
  付随サービスと見られること(本venture対象外の職種が事業の中心である可能性が高い新事実)、
  (2)前回懸念していた「株式会社レボル」(revol.co.jp、埼玉の美容サロン運営会社)との誤結合
  リスクは、revol.co.jpが自社ブランドとして「LEVOL」ブランドを展開する別事業のページを
  持っていたことに起因する表示上の混在であり、levol.co.jp(馬具・乗馬靴修理店)とは無関係な
  別事業者であることが明確になった点、の2点を確認した。LEVOLの優先順位を「保留」から
  「除外方向で次回最終判断」に見直した。実際の連絡・ヒアリング依頼は行っておらず、着手する
  場合は別途pending-approval.mdへの記録・オーナー承認が必要である旨を明記した。承認不要な
  公開情報調査・記録のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生
  していないためpending-approval.mdへの追記なし。

- フェーズ12(2026-09-06 17:00 UTC): 「次にやること」1点目・2点目だったLEVOLの最終判断と
  エクウスワールドの自社修理有無の確認をWebSearchで行った(candidate-longlist-draft.md
  「第五弾」)。LEVOLは本業が乗馬靴(履物)専門店であり馬具修理は付随サービスと再確認できた
  ため除外条件に該当すると判断し正式に除外した。エクウスワールド(トライ企画・伊藤政男氏)は
  頭絡縫い目修理・鞍の託革修理等の具体的な修理メニューを自社サービスとして掲げ、問い合わせも
  代表個人への直通連絡であることから自ら修理を行っていると判断でき、除外条件に該当しないため
  優先順位2に格上げした。実際の連絡・ヒアリング依頼は行っておらず、着手する場合は別途
  pending-approval.mdへの記録・オーナー承認が必要である旨を明記した。承認不要な公開情報
  調査・記録のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。

- フェーズ13(2026-09-06 18:00 UTC): 「次にやること」2点目だった初回コンタクト文面の草案
  作成に着手した(initial-contact-message-draft.md新規作成)。course-set-pasha・
  line-reservation-aiの既存文面草案の構成(チャネル使い分け・文面草案A/B・候補ごとの
  留意点・未確定事項)を踏襲し、優先順位1(ライディングショップ池上、公式サイト問い合わせ
  想定)には長め文面(草案A)、優先順位2(エクウスワールド、代表個人への直通電話想定)には
  電話トーク要点(草案B)を割り当てた。実際の送信・連絡は一切行っていない。承認不要な
  設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。

- フェーズ14(2026-09-06 19:00 UTC): 「次にやること」2点目だったcustomer-interview-design.md
  相当の質問項目リストを新規作成した。course-set-pasha/customer-interview-design.mdの構成
  (目的→対象→質問項目→実施方法→留意点)を踏襲しつつ、本venture固有の論点(受注頻度の
  低さ・pricing-plan.mdの課金単位(区分問わず一律1回)への納得感・llm-system-prompt-draft.md
  厳守事項2(修理可否判断への不介入)の実務感覚との整合)を反映した全13問を設計した。
  対象はcandidate-longlist-draft.md第五弾の優先順位1・2を中心に2〜3件(他venture(7〜10件)
  より少ない、フェーズ9で見直した現実的な目標合計5〜6件を踏まえた設定)とした。実際の
  連絡・ヒアリング依頼は行っておらず、着手する場合は別途pending-approval.mdへの記録・
  オーナー承認が必要である旨を明記した。承認不要な設計文書作成のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ15(2026-09-06 22:00 UTC): 「次にやること」1点目だったジャパンギャロップス
  インポーターの自社修理有無について、WebSearch(3クエリ)で追加確認した
  (candidate-longlist-draft.md第六弾)。公式サイト(j-g-i.com)へのWebFetchはLEVOLの時と
  同様にegressポリシーでブロックされ一次情報には到達できず、検索スニペットからも修理を
  自社職人が行うか外部委託かを示す記述は得られなかった。主力商品と修理対象が同一カテゴリ
  (馬具)である点でLEVOLほど除外条件に明確に該当するとは言えないため「保留」を維持しつつ、
  公開情報のみでの追加探索は費用対効果が低いと判断し、最終判断は優先順位1・2候補への
  ヒアリング実施(承認後)時に持ち越す方針とした。実際の問い合わせ・連絡は行っていない。
  承認不要な公開情報調査のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ16(2026-09-06 23:00 UTC): 「次にやること」1点目だったcustomer-interview-design.md
  の質問数13問が10〜15分に収まるか検証するリハーサル台本を新規作成した
  (interview-rehearsal-script.md)。aircon-pasha・course-set-pashaの既存台本の構成
  (想定タイムテーブル→オープニング台本→質問ごとの補足ト書き→クロージング台本→
  確認ポイント)を踏襲し、優先順位1(ライディングショップ池上、代表・池上豊氏)を
  想定回答者として全13問・目標13分のタイムテーブルを設計した。候補1が新規制作・修理の
  両方に対応する点を活かし、Q7(課金単位の納得感)・Q10(納品案内下書き内容)を区分ごとに
  確認できるト書きを追加した。候補2(エクウスワールド)向けの差分(通販事業との切り分け・
  電話冒頭の一言)も申し送り事項として付した。実際のリハーサル実施・候補への連絡は
  行っていない。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ17(2026-09-07 00:00 UTC): aircon-pasha/course-set-pashaには既にあるが本venture
  未着手だったlanding-page-copy-draft.mdを新規作成した。両venture既存草案の構成
  (ヒーロー→課題提起→機能紹介→差別化→料金→FAQ)を踏襲しつつ、本venture固有の
  「区分(新規制作/修理)に応じて納品案内下書きの内容が分岐する」「受注頻度が低く
  トライアル期間を30日間とやや長めに設定している」特性をヒーロー・機能紹介・料金・FAQの
  各セクションに反映した。content-generation-time-estimate.md相当の作業時間試算が
  本venture未実施のため「時給換算」訴求セクションは見送り、次のステップ候補として
  明記した。実際のLP実装・公開は行っていない。承認不要な設計文書作成のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ18(2026-09-07 01:00 UTC): 「次にやること」1点目だったcontent-generation-
  time-estimate.md相当の作業時間試算を新規作成した。course-set-pashaの試算構成
  (前提→試算表→結論・採用値→残課題)を踏襲しつつ、本venture固有の3点セット
  (受注内容整理メモ・納品案内下書き・お手入れ案内下書き)と聞き取り項目数の多さ
  (馬体サイズ・型・革種類・金具仕様・用途・納期の6項目)を反映し、1回あたり20分
  (幅16〜25分)を仮置き採用値とした。この値を用いてpricing-plan.mdの3プラン別
  「時給換算」(ライト約980円/時・スタンダード約743円/時・複数職人約597円/時)を
  試算し、landing-page-copy-draft.mdの「時給換算」訴求セクションを新規追加した
  (これまで「未着手」としていた同セクションを解消)。実LLM呼び出し・実ヒアリングでの
  検証は引き続き未実施。承認不要な設計文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ19(2026-09-07 02:00 UTC): 「次にやること」1点目だったlegal-notices-draft.md
  相当の特定商取引法・プライバシーポリシー文面草案を新規作成した。aircon-pasha/
  course-set-pashaの既存草案の構成(1.特商法表記→2.プライバシーポリシー→次のステップ候補)を
  踏襲しつつ、本venture固有の特性(受注内容整理メモ・納品案内・お手入れ案内の3点セット、
  鞍・馬具という1件あたり高単価・低頻度のオーダーメイド)を反映した。本venture固有の
  data-retention-policy.mdが未作成であるため、2.4節の保存期間は他venture(1年)の暫定値を
  準用する形にとどめ、data-retention-policy.md新規作成を次のステップ候補として明記した。
  実際のLP公開・外部への表示は行っていない。承認不要な設計文書作成のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ20(2026-09-07 03:00 UTC): 「次にやること」1点目だった本venture固有の
  data-retention-policy.mdを新規作成した。course-set-pasha/data-retention-policy.mdの
  構成(前提整理→保存期間ポリシー→削除候補化後の最終確認→開示・削除請求対応)を
  踏襲しつつ、legal-notices-draft.md 2.4節が残していた固有論点(依頼頻度の低さ・
  単価の高さゆえに保有期間を延ばすべきか)を検討した。結論として、`user_profile`が
  保持するのは屋号・メールアドレス・決済ID等の登録情報のみで発注内容自体は保存
  しない設計のため、依頼頻度の低さは保有期間延長の積極的根拠にならないと判断し、
  他venture(aircon-pasha・course-set-pasha)と同じ1年をそのまま採用した。
  legal-notices-draft.md 2.4節の暫定準用記載を正式内容へ差し替える作業は次のステップ
  候補として残した。実際のデータ削除・通知実装は行っていない。承認不要な設計文書
  作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。

- フェーズ21(2026-09-07 04:00 UTC): 「次にやること」1点目だったlegal-notices-draft.md
  2.4節の「暫定準用」記載を、フェーズ20で新規作成したdata-retention-policy.mdの内容
  (1年保有・解約起点、`user_profile`・`usage_counter`の2種類のみ保有)に基づいて
  正式な記載へ差し替えた。2.4節本文に「本venture固有の受注特性を踏まえても他venture
  (aircon-pasha・course-set-pasha)と異なる保有期間を設定する積極的な根拠はない」という
  data-retention-policy.mdの結論をそのまま反映し、「前提・未確定事項」節および
  「残課題」節に残っていた暫定準用の記述も併せて更新した。data-retention-policy.md側の
  残課題節も対応する記述に更新した。実際のLP公開・外部への表示は行っていない。承認不要な
  設計文書の整合性更新のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ22(2026-09-07 05:00 UTC): llm-system-prompt-draft.md作成時(04:00 UTC)の前提
  「本ventureは継続課金(サブスクリプション)を伴わない単発の下書き生成サービスである」が、
  3時間後に作成されたpricing-plan.md(07:00 UTC、月額サブスク+月間生成回数上限という設計)
  および data-retention-policy.md(`user_profile`が決済ID等を保持)と矛盾していることを
  発見した。本venture固有の受注特性(低頻度・高単価)ゆえに価格体系こそ他venture
  (course-set-pasha等)と異なるが、「月額サブスクリプションである」点自体は同じである
  ことが後に確定したにもかかわらず、先行して書かれたllm-system-prompt-draft.mdの前提が
  未更新のままだったギャップである。course-set-pasha/llm-system-prompt-draft.mdの
  厳守事項7a(解約意図検知、2026-08-15追記分)を参考に、本ventureにも同種の厳守事項7aを
  新設して前提を訂正した。ただし本venture固有の解約フロー設計文書(course-set-pasha/
  subscription-cancellation-flow-design.md相当)・Stripe連携設計は未着手のため、案内先の
  具体的な導線確定やschema/output.schema.jsonのstatus enum拡張(cancellation_intent等の
  追加)は、course-set-pashaが7a新設から5時間後にschema拡張(フェーズ54)を行った前例に
  倣い、次の課題として段階的に進める方針とした。実際のStripe連携・LINE公式アカウント
  接続は行っていない。承認不要な設計文書間の整合性修正のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ23(2026-09-07 06:00 UTC): フェーズ22で先送りとした、本venture固有の解約フロー
  設計文書を新規作成した(subscription-cancellation-flow-design.md)。
  course-set-pasha/subscription-cancellation-flow-design.mdの構成(背景→前提→解約フロー→
  案内メッセージ→ダウングレードフロー→未検証の仮説)を踏襲しつつ、本venture固有の
  pricing-plan.md「複数職人プラン」(複数の職人が共同で1契約を利用する形態)に特有の
  「誰が解約操作を行える権限を持つか」という論点を新設節として追加し、契約者本人のみが
  解約・ダウングレード操作を行える権限モデルを仮決めした。ダウングレード時の当月生成回数
  上限の適用方法は、course-set-pashaがStripe公式ドキュメント調査済みの確定方式
  (`usage_counter`のcountは維持し上限のみ新プラン値へ差し替え)をそのまま踏襲できると
  判断し独自の再調査は行わなかった。schema/output.schema.jsonのstatus enum拡張
  (cancellation_intent等の追加)・validate_test_cases.pyへの対応テストケース追加、
  および複数職人プランの「契約者本人」判定の仕組み自体は未着手のため次の課題として残した。
  実際のStripe接続・Webhook実装・LINE公式アカウント接続は行っていない。承認不要な設計
  文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。

- フェーズ24(2026-09-07 07:00 UTC): 「次にやること」1点目だった、フェーズ23
  (subscription-cancellation-flow-design.md)で先送りとしたschema拡張を行った。
  course-set-pasha/schema/output.schema.jsonのフェーズ54改訂を踏襲し、
  schema/output.schema.jsonの`status` enumへ`cancellation_intent`/`downgrade_intent`/
  `cancellation_unclear`の3値と、これらのときのみ非nullとなる`subscription_procedure_notice`
  フィールド(kind/body/includes_portal_link)を追加した。schema/validate_test_cases.pyにも
  対応するcross-field検証ロジックと3件の期待出力テストケース(C1解約意図/C2ダウングレード
  意図/C3解約意図不明瞭)、およびincludes_portal_link不一致を検出できるかのネガティブ
  テストケースを追加し、全10件(既存7件+新規3件)パス・ネガティブ2件とも想定通りエラー
  検出を確認した(`python3 schema/validate_test_cases.py`)。実LLM呼び出しは未実施。
  複数職人プランの「契約者本人」判定の仕組み自体は引き続き未着手で次の課題として残した。
  承認不要な設計文書・検証スクリプトの作成のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ25(2026-09-07 08:00 UTC): 「次にやること」1点目だった複数職人プランの
  「契約者本人」判定の仕組みを設計した(craftsman-account-linking-design.md新規作成)。
  着手にあたり、本ventureには単一契約向けのLINE user_id紐付け基本設計自体が
  存在しないことが判明したため、course-set-pasha/line-user-id-linking-design.mdの
  連携コード方式(友だち追加時にコード発行)をまず踏襲した上で、複数の職人が1契約を
  共有する単位として`craftsman_workshop/{workshop_id}`を新設し、
  「workshopを最初に作成したuser_id=契約者本人(`contractor_user_id`)」という
  機械的に判定可能なルールを確定した。単一契約(ライト/スタンダード)もメンバー1名の
  workshopとして統一的に扱う設計とし、複数職人プランへのアップグレード時に招待コード
  (`pending_workshop_invites`)で職人を追加できる導線も設計した。これにより
  subscription-cancellation-flow-design.mdの未確定事項(契約者本人の判定方法)を解消
  した。一方で、本設計により`usage_counter`のキーがuser_idからworkshop_idへ読み替え
  られる必要があることが新たに判明し、schema/output.schema.json・
  validate_test_cases.pyへの反映は次の課題として残した。ダウングレード時の余剰
  メンバーの扱い・契約者の譲渡機能もMVP範囲外として次の課題とした。実際のLINE公式
  アカウント接続・Stripe接続・招待コード発行の実装は未着手。承認不要な設計文書作成の
  みで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ26(2026-09-07 09:59 UTC): 「次にやること」1点目だった`usage_counter`の
  キーをuser_idからworkshop_idへ読み替える対応を検討した
  (usage-counter-workshop-key-design.md新規作成)。検討の結果、`usage_counter`は
  LLM構造化出力(schema/output.schema.json)には元々登場しないFirestore側の
  カウンタであることを確認したため、両ファイルへの直接編集ではなく、複数職人プランの
  月間生成回数上限が「工房(workshop)単位」であることを明確化する設計文書を作成する形で
  対応した。生成リクエスト受信時のカウント処理手順(user_id→workshop_id→
  usage_counter参照の3ステップ)とダウングレード時の`count`維持方針を確定した。
  これによりcraftsman-account-linking-design.md(フェーズ25)の残課題1点目を解消した。
  実装(プロトタイプコード)は本venture未着手のため次の課題として残した。実際の
  Stripe接続・LINE公式アカウント接続は行っていない。承認不要な設計文書作成のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ27(2026-09-07 11:02 UTC): 「次にやること」1点目だった生成リクエスト処理の
  プロトタイプコード(course-set-pasha/prototype相当)を新規作成した
  (prototype/usage_counter_workshop.py・test_usage_counter_workshop.py)。
  usage-counter-workshop-key-design.md(フェーズ26)2節で確定した「user_id→
  workshop_id→usage_counter参照」の3ステップと、pricing-plan.mdのプラン別上限
  (ライト3回/スタンダード8回/複数職人20回)・従量単価を実行可能なコードに落とし込んだ。
  同設計書末尾の残課題だった「`user_profile.workshop_id`が未設定(workshop未作成)の
  エッジケース」は`WorkshopNotLinkedError`として明示的に例外処理する形で解消した。
  複数職人プランで異なるuser_idが同一workshopのカウンタを共有し合算される(抜け穴が
  塞がれている)こと、月替わりでcountがリセットされることをテストケースで検証し、
  全12件パスを確認した(`python3 test_usage_counter_workshop.py`)。実Firestore接続・
  実LINE Messaging API接続は行っていない。承認不要なプロトタイプコード作成のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ28(2026-09-07 12:02 UTC): 「次にやること」1点目だった、複数職人プランから
  ライト/スタンダードプランへのダウングレード時の余剰メンバーの扱いを設計した
  (downgrade-excess-member-handling-design.md新規作成)。course-set-pasha・
  aircon-pashaには複数人契約の概念自体が存在せず参照できる既存踏襲元がなかったため、
  即時強制解除・猶予期間付き解除・契約者による選択制の3案を比較検討し、次回請求
  サイクル開始まで猶予したうえで契約者(`contractor_user_id`)のみを残すデフォルト
  ルールで機械的に縮小する方式(猶予期間付き解除)を採用した。これにより
  craftsman-account-linking-design.md(フェーズ25)・subscription-cancellation-
  flow-design.md(フェーズ23)双方に残っていた同一の残課題を解消した。猶予期間中の
  「残すメンバー」連絡導線の具体的な文言・schema拡張、`pending_member_reduction_
  effective_at`の都度チェック実装(prototype拡張)は机上設計にとどまり、次の課題として
  残した。実際のStripe接続・LINE公式アカウント接続は行っていない。承認不要な設計
  文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生
  していないためpending-approval.mdへの追記なし。

- フェーズ29(2026-09-07 13:02 UTC): 「次にやること」1点目だった、猶予期間中に契約者が
  「残すメンバー」を連絡する導線のLINE上での意図検知文言・schema拡張を行った
  (member-retention-notice-design.md新規作成)。course-set-pashaの解約意図検知
  パターン(フェーズ24)を踏襲し、`status`のenumへ`member_retention_selection`
  (明確な指定)/`member_retention_unclear`(不明確)の2値と、非nullとなる
  `member_retention_notice`(kind・specified_member_name・body)フィールドを
  output.schema.jsonへ追加した。validate_test_cases.pyへ対応するクロスフィールド
  検証ロジックと新規2テストケース(M1・M2)・ネガティブテストケース(kind不一致検出)を
  追加し、全13件パスを確認した(`python3 schema/validate_test_cases.py`)。
  `specified_member_name`と`member_user_ids`の突き合わせロジック、
  `pending_member_reduction_effective_at`の都度チェック処理自体の実装は本フェーズでは
  扱わず次の課題として残した。実際のStripe接続・LINE公式アカウント接続は行っていない。
  承認不要な設計文書作成・schema拡張・検証スクリプト更新のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ30(2026-09-07 14:02 UTC): 「次にやること」1点目だった
  `pending_member_reduction_effective_at`の都度チェック処理をprototype/
  usage_counter_workshop.pyへ実装した(`check_and_apply_pending_member_reduction`)。
  downgrade-excess-member-handling-design.md「3. 確定する設計」の通り、猶予期間
  未到達時は何もせず、到達後は`member_user_ids`を契約者のみに縮小し
  `pending_member_reduction_effective_at`をクリアする。あわせて
  member-retention-notice-design.md「4. 未検証・残課題」1点目だった
  `specified_member_name`と表示名の突き合わせロジックも実装し、契約者本人の表示名と
  一致する場合のみ「一致」として扱い、契約者以外を指した指定は契約者譲渡機能が
  MVP範囲外のため反映できない旨をnoteに記録したうえでデフォルトルール(契約者のみ
  残す)を適用する設計とした。縮小後に除外されたメンバーからの生成リクエストを
  検知する`MemberRemovedError`・`ensure_member_is_active`も
  `WorkshopNotLinkedError`の既存例外設計を踏襲して追加し、
  test_usage_counter_workshop.pyに新規7テストケースを追加して全30件パスを確認した
  (`python3 prototype/test_usage_counter_workshop.py`)。縮小処理・除外検知・
  usage_counter加算(`check_and_increment_usage`)の呼び出し順序の統合自体は
  本モジュール未着手のため次の課題として残した。実際のStripe接続・LINE公式
  アカウント接続は行っていない。承認不要なプロトタイプコード実装・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ31(2026-09-07 15:02 UTC): 「次にやること」1点目だった、
  `check_and_apply_pending_member_reduction`→`ensure_member_is_active`→
  `check_and_increment_usage`の呼び出し順序を実際の生成リクエスト処理フローとして
  統合する`process_generation_request`をprototype/usage_counter_workshop.pyに
  追加した。縮小猶予期間到達後の最初の生成リクエストで(1)縮小適用→(2)除外
  チェック→(3)カウント加算が同一呼び出し内で正しい順序で行われること、除外
  対象メンバーからのリクエストは(2)で`MemberRemovedError`を送出しカウント
  加算(課金対象化)に到達しないこと、を新規4テストケースで検証し全39件パスを
  確認した(`python3 prototype/test_usage_counter_workshop.py`)。実Firestore接続・
  実LINE Messaging API接続は行っていない。承認不要なプロトタイプコード実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ32(2026-09-07 16:02 UTC): usage-counter-workshop-key-design.md
  「未検証・残課題」2点目だった、複数職人プランの請求サイクル境界とworkshop
  作成タイミングがずれるケース(月の途中でworkshopが新規作成された場合の当月
  上限の按分要否)を検討し、按分不要(月の途中で作成されたworkshopにもその月の
  残り期間について満額の月間上限をそのまま適用する)と結論づけて同ファイル4節に
  追記した。上限がそもそも日割りの性質を持たない固定枠であること、Stripe側の
  料金プロレーションと生成回数枠は独立した別軸であり単一契約venture(course-set-pasha・
  aircon-pasha)にも既に内在していた前提であることを根拠とした。あわせて同ファイル
  「未検証・残課題」1点目(workshop_id未設定エッジケース)がフェーズ29の
  `WorkshopNotLinkedError`実装により既に解消済みであることを確認・明記し、
  同ファイルの残課題を全て解消済みとした。設計文書の追記のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ33(2026-09-07 16:58 UTC): 「次にやること」で挙げていた契約者譲渡機能の
  要否検討に着手した(contractor-transfer-design.md新規作成)。伝統工芸の工房は
  師弟制・家族経営による事業承継が本venture固有に発生しやすく、`contractor_user_id`
  が解約・ダウングレード操作権限の判定基準そのものになっている(craftsman-account-linking-design.md
  4節)ため、契約者引退時に後継者が解約操作すら行えなくなるリスクがあると判断し、
  「必要な機能」と結論づけた。MVPスコープは既存workshopメンバーへの譲渡のみに限定し
  (第三者への直接譲渡は本人確認の新課題を生むため対象外)、契約者本人からの譲渡意図
  検知→対象メンバーの名指し一致判定(member-retention-notice-design.mdの
  `specified_member_name`ロジックを再利用)→契約者の再確認応答を経た2段階確定、
  という設計を確定した。status enumへの`contractor_transfer_selection`/
  `contractor_transfer_unclear`追加、schema/validate_test_cases.pyへの反映、
  prototypeコード化はいずれも次の課題として残した。設計文書作成のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ34(2026-09-07 17:58 UTC): 「次にやること」4点目だった、契約者譲渡機能
  (contractor-transfer-design.md、フェーズ33)のschema拡張に着手した。`status`のenumへ
  `contractor_transfer_selection`/`contractor_transfer_unclear`の2値と、これらのときのみ
  非nullとなる`contractor_transfer_notice`フィールド(`kind`/`specified_member_name`/`body`、
  member_retention_noticeと同じ設計思想)をschema/output.schema.jsonへ追加し、
  validate_test_cases.pyにクロスフィールド検証ロジック(status⇔kind一致・
  specified_member_nameの非null制約)と新規2テストケース(CT1/CT2)・ネガティブテスト
  ケース(kind不一致検出)を追加、既存テストケース(M1・M2・NEG1・NEG2・NEG3)へも
  新フィールド追加漏れが無いことを確認し全16件パスを確認した
  (`python3 schema/validate_test_cases.py`)。あわせてprototype側の既存39件のテスト
  (`python3 prototype/test_usage_counter_workshop.py`)が本改修の影響を受けず全件パス
  することを確認した。`craftsman_workshop`データ構造のprototypeコード化・
  `contractor_user_id`更新処理の実装、契約者からの再確認応答の検知プロンプト設計は
  次の課題として残した。承認不要なschema拡張・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ35(2026-09-07 20:02 UTC): 「次にやること」4点目だった、契約者譲渡機能
  (contractor-transfer-design.md、フェーズ33/schema拡張はフェーズ34)の
  `prototype/usage_counter_workshop.py`側への`contractor_user_id`更新処理の実装に着手
  した。`WorkshopStoreProtocol`に`set_contractor_user_id`を追加し(InMemory実装含む)、
  契約者のメッセージ中で名指しされた相手が既存メンバー(契約者自身を除く)の表示名と
  一致するかを判定する`resolve_contractor_transfer_target`(一致しなければNoneを返し
  呼び出し側でcontractor_transfer_unclearの案内に切り替える想定)、契約者からの
  再確認応答後に呼び出す確定処理`apply_contractor_transfer`(既存メンバー外への
  呼び出しは`ContractorTransferTargetNotFoundError`で防御、旧契約者は
  `member_user_ids`から自動的には外さない)を実装した。新規5テストケース
  (名指し一致・契約者自身を除外・未加入者はNone・確定処理での更新と旧契約者の残留・
  既存メンバー外への防御)を追加し、`python3 test_usage_counter_workshop.py`で全49件
  パスを確認した。他venture(aircon-pasha・course-set-pasha・line-reservation-ai)の
  prototypeテスト(474件・573件・760件)・4venture合計のschema検証(9+9+16+25件)も
  あわせて実行し、いずれも変更前と同じ結果でパスすることを確認した。契約者からの
  再確認応答自体の検知プロンプト設計は引き続き次の課題として残した。承認不要な
  プロトタイプコード実装のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ36(2026-09-08 01:00 UTC): 「次にやること」4点目だった、契約者譲渡機能
  (contractor-transfer-design.md、フェーズ33)の残課題「契約者からの再確認応答
  (『はい』等の自由記述)をどう検知するか」の具体的なプロンプト設計に着手した
  (contractor-transfer-confirmation-detection-design.md新規作成)。member-retention-
  notice-design.md等の既存の一時状態管理パターンを踏襲し、`craftsman_workshop/
  {workshop_id}.pending_contractor_transfer`(候補user_id・候補メンバー名・申請日時・
  期限〈24時間〉)をアプリケーション側で保持し、送信者が契約者本人かつこの一時状態が
  期限内である場合のみLLM呼び出し時にその文脈を注入する設計とした。契約者の返信を
  肯定(`contractor_transfer_confirmed`)・否定(`contractor_transfer_cancelled`)・
  不明瞭(`contractor_transfer_reconfirm_unclear`)の3パターンに分類する`status`
  enum拡張と`contractor_transfer_confirmation`フィールド(`kind`/`body`)を設計し、
  肯定時のみアプリケーション側がフェーズ35実装済みの`apply_contractor_transfer`を
  呼び出す(LLMは文言生成のみを担い更新処理には関与しない)役割分担を明確化した。
  期限切れ後の扱いは、line-reservation-aiのcandidates-expired-notification-design.md
  (能動プッシュ通知は課金・実測データ不在を理由に見送り)と同種の判断で、本venture
  でも能動通知は行わず次回メッセージ受信時の受動的な案内に留める方針とした。
  schema/output.schema.jsonへの実反映、prototype側の`pending_contractor_transfer`
  読み書き実装、期限切れ後の案内文言自体のschema設計はいずれも次の課題として残した。
  コード変更は無く、venture全体49件(`python3 prototype/test_usage_counter_workshop.py`)・
  schema検証16件(`python3 schema/validate_test_cases.py`)パスを確認した(変更前と
  同じ結果)。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- フェーズ37(2026-09-08 02:00 UTC): 「次にやること」4点目だった、契約者譲渡機能の
  再確認応答検知(contractor-transfer-confirmation-detection-design.md、フェーズ36)の
  schema/output.schema.json・validate_test_cases.pyへの反映を実施した。`status`のenumへ
  `contractor_transfer_confirmed`/`contractor_transfer_cancelled`/
  `contractor_transfer_reconfirm_unclear`の3値と、これらのときのみ非nullとなる
  `contractor_transfer_confirmation`フィールド(`kind`/`body`)を追加し、既存の
  `contractor_transfer_notice`と同型のクロスフィールド検証ロジック(status不一致時の
  他フィールドnull制約、kind一致検証)をvalidate_cross_field_rulesに追加した。新規
  期待出力テストケース3件(肯定/否定/不明瞭それぞれ)、kind不一致を検出するネガティブ
  テストケース1件を追加し、schema検証は全20件パスを確認した。prototype/usage_counter_
  workshop.py側の`pending_contractor_transfer`一時状態の読み書き実装(design.md1節、
  `WorkshopStoreProtocol`への追加・`apply_contractor_transfer`呼び出し時/キャンセル時/
  期限切れ時の削除処理)は未着手のため次の課題として残した。venture全体49件
  (`python3 prototype/test_usage_counter_workshop.py`)パスも確認した(コード変更が
  無いため変更前と同じ結果)。承認不要なschema拡張・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ38(2026-09-08 03:00 UTC): 「次にやること」4点目だった、
  contractor-transfer-confirmation-detection-design.md(フェーズ36)1節の
  `pending_contractor_transfer`一時状態の読み書きをprototype/usage_counter_workshop.py側に
  実装した。`PendingContractorTransfer`データクラス(candidate_user_id/
  candidate_member_name/requested_at/expires_at)、`WorkshopStoreProtocol`への
  `get_pending_contractor_transfer`/`set_pending_contractor_transfer`/
  `clear_pending_contractor_transfer`追加に加え、(1)`start_pending_contractor_transfer`
  (status=contractor_transfer_selection生成と同時にexpires_at=requested_at+24時間で
  書き込む)、(2)`is_contractor_transfer_confirmation_context`(2節のLLM呼び出し前
  コンテキスト注入条件: 送信者が契約者本人かつpending存在かつ期限内)、(3)
  `cancel_pending_contractor_transfer`(3節kind=contractor_transfer_cancelledの
  削除のみの処理)、(4)`check_and_expire_pending_contractor_transfer`(4節の期限切れ
  削除、能動通知は行わず戻り値を受動案内判定に使う想定)を実装し、`apply_contractor_
  transfer`確定処理からも同状態を削除するよう変更した。新規テストケース10件を追加し
  venture全体59件→64件(`python3 prototype/test_usage_counter_workshop.py`)・schema
  検証20件(変更なし、コード変更のみのため)いずれもパスを確認した。4節末尾の「期限切れ
  後の案内文言自体のschema・プロンプト設計」は本フェーズでは扱わず引き続き次の課題として
  残した。承認不要なコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ39(2026-09-08 04:00 UTC): 「次にやること」4点目だった、期限切れ後の案内
  文言自体のschema・プロンプト設計をcontractor-transfer-expired-notice-design.mdとして
  新規作成した。`check_and_expire_pending_contractor_transfer`(フェーズ38実装済み)が
  非Noneを返した(=直前に期限切れを検出した)場合に限り新設の文脈を注入し、受信メッセージ
  の内容によらずstatusを`contractor_transfer_expired_notice`に強制する設計とした。新規
  フィールド`contractor_transfer_expired_notice`(kind/candidate_member_name/body)は
  既存のcontractor_transfer_notice等と同じ設計思想(kindはstatusと冗長だがbody生成分岐
  用)を踏襲した。schema/output.schema.json・validate_test_cases.py・prototypeへの反映
  は次の課題として残した。コード変更は無く、venture全体64件(`python3 prototype/
  test_usage_counter_workshop.py`)・schema検証20件(変更なし)いずれもパスを確認した
  (変更前と同じ結果)。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ40(2026-09-08 06:00 UTC): フェーズ39の残課題だった、contractor-transfer-
  expired-notice-design.mdのschema/output.schema.json・validate_test_cases.py・
  prototypeへの反映を行った。schema側は`status`のenumへ`contractor_transfer_expired_
  notice`の1値、これに対応する`contractor_transfer_expired_notice`(kind/candidate_
  member_name/body)フィールドを追加し、既存のcontractor_transfer_confirmation等と
  同じ設計思想(kindはstatusと冗長だがbody生成分岐用、candidate_member_nameは常に
  非null)を踏襲した。validate_test_cases.pyには期待出力テストケース1件(CTE1)に加え、
  ネガティブテストケース2件(statusが別値なのにフィールドが非nullのまま残る排他性違反
  〈NEG6〉、design.md3節「常に非null」に違反するcandidate_member_name null制約違反
  〈NEG7〉)を追加した(design.md4節が挙げていた1件に、排他性違反の1件を追加した)。
  prototype側は`check_and_expire_pending_contractor_transfer`の呼び出し元配線・
  文脈注入条件として`get_contractor_transfer_expired_notice_context`を新設した。
  design.md1節は`is_contractor_transfer_confirmation_context`と対になる関数名として
  `is_`接頭辞の例を挙げていたが、本関数はbool単体ではなくLLMへ転記するcandidate_
  member_nameを含むPendingContractorTransfer自体を返す必要があるため`get_`接頭辞と
  した(design.md4節に命名差分として記録済み)。テスト3件追加、venture全体70件全件
  (`python3 prototype/test_usage_counter_workshop.py`)・schema検証23件全件
  (`python3 schema/validate_test_cases.py`)パスを確認した。承認不要な設計・実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生
  していないためpending-approval.mdへの追記なし。

- フェーズ41(2026-09-08 07:00 UTC): 「次にやること」4点目だった、契約者以外(譲渡候補
  本人や第三者)が`pending_contractor_transfer`存在中・期限切れ後に何かメッセージを
  送ってきた場合の扱いを検討し、contractor-transfer-non-contractor-message-design.mdと
  して結論を記録した。既存のcontractor-transfer-confirmation-detection-design.md2節の
  条件式(送信者=`contractor_user_id`のときのみ文脈注入)が既に「契約者以外は通常メッセージ
  処理にフォールスルー」という設計になっており、候補者が「はい、お願いします」等と発言
  しても送信者不一致のため`apply_contractor_transfer`が誤って呼ばれることはないと確認
  した。進行中の交代手続きの状態を契約者以外に開示する個別案内も検討したが、契約者以外
  への途中経過の開示は意図しない状況漏洩リスクを伴うためMVPでは見送り、追加のschema
  拡張・prototype変更は行わないことを確定した。コード変更は無く、venture全体70件
  (`python3 prototype/test_usage_counter_workshop.py`)・schema検証23件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な検討・設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ42(2026-09-08 11:00 UTC): ドキュメント整合性の記載漏れを訂正した。
  subscription-cancellation-flow-design.md(フェーズ23)「未検証の仮説・次の課題」に
  残っていた「schema/output.schema.jsonのstatus enum拡張・validate_test_cases.pyへの
  テストケース追加は未着手」という記載が、実際にはフェーズ24(本ファイル作成の1時間後)で
  既に対応済みだったにもかかわらず訂正されないまま持ち越されていた記載漏れであることを
  発見し、同ファイル内に訂正の追記を行った(`python3 schema/validate_test_cases.py`実行、
  23件全件パスを確認)。本README.mdのステータス欄がフェーズ41止まりで本フェーズの記録が
  漏れていたため、本フェーズ42のエントリとして追記する(記載漏れの発見自体の記載漏れという
  形になっていたための遡及記録)。承認不要なドキュメント整合性修正のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ43(2026-09-08 13:00 UTC): 「次にやること」で挙げていなかったが、
  prototype/usage_counter_workshop.pyのコードを見直す中で新たに気付いた設計上の未整理点に
  対応した(message-context-selection-design.md新規作成)。これまで(1)member-retention-
  notice-design.md(フェーズ29、猶予期間中の「残すメンバー」連絡検知)、(2)contractor-
  transfer-confirmation-detection-design.md(フェーズ36、契約者譲渡の再確認応答検知)、
  (3)contractor-transfer-expired-notice-design.md(フェーズ39、譲渡申請の期限切れ案内)、
  という3つの「一時状態に応じてLLM呼び出し前のプロンプト文脈を切り替える」設計がそれぞれ
  個別に確定していたが、1つのworkshopに複数の一時状態が同時に存在しうる場合(例:譲渡
  申請中〈pending_contractor_transfer〉かつメンバー縮小の猶予期間中
  〈pending_member_reduction_effective_at〉)に、どちらの文脈を優先して注入すべきかという
  優先順位が一度も明文化されていないことに気付いた。本ファイルで、(a)期限切れ検知
  (`check_and_expire_pending_contractor_transfer`)を最優先(送信者に依らず強制的に案内を
  返す必要があるため)、(b)契約者本人かつ`pending_contractor_transfer`が期限内なら契約者
  譲渡の再確認応答文脈、(c)契約者本人かつ`pending_member_reduction_effective_at`が
  設定済みなら残すメンバー連絡文脈、(d)いずれにも該当しなければ通常の生成リクエスト文脈
  (`process_generation_request`)、という4段階の優先順位を確定した。優先順位の根拠
  (期限切れ通知は受動案内である以上取りこぼすと機会を失う一方、契約者譲渡は工房の統治
  そのものに関わるため縮小猶予の連絡より優先させる、という2点)を明記した。schema側の
  クロスフィールド制約(status enum同士は排他的に設計済みのため優先順位を人為的に決めて
  も既存schemaと矛盾しない)を確認したが、prototype側に上記4段階を1つの関数へ統合する
  実装(`select_message_context`相当)はまだ無く、次の課題として残した。設計文書作成の
  みで、コード変更は無くventure全体70件(`python3 prototype/test_usage_counter_workshop.py`)・
  schema検証23件(`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ
  結果)を確認した。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ44(2026-09-08 14:00 UTC): 「次にやること」1点目だった、
  message-context-selection-design.md(フェーズ43)1節の4段階の優先順位を
  prototype/usage_counter_workshop.pyに`select_message_context`として統合実装した。
  (a)は設計通り送信者を問わず`check_and_expire_pending_contractor_transfer`を直接
  呼び出す形にし(契約者限定の`get_contractor_transfer_expired_notice_context`は
  使わない)、(d)のみ内部で既存の`process_generation_request`をそのまま呼び出すことで
  既存関数のシグネチャ・挙動を変更しなかった。design.md3節が明示的に求めていた
  「(a)(b)が同時に真になりうる状態で(a)が優先されることを検証するケース」を含め、
  (a)〜(d)それぞれの分岐・契約者以外へのフォールスルー・workshop未連携時の例外の
  計8件の新規テストケースを追加し、venture全体70件→83件
  (`python3 prototype/test_usage_counter_workshop.py`)・schema検証23件(コード変更の
  みのため変更なし、`python3 schema/validate_test_cases.py`)いずれもパスを確認した。
  他venture(aircon-pasha 9件・course-set-pasha 9件・line-reservation-ai 25件)の
  schema検証、および各prototypeディレクトリの既存テストスイートもあわせて実行し、
  いずれも変更前と同じ結果でパスすることを確認した(本venture以外への影響なし)。
  実際のLINE公式アカウント接続・実LLM検証は引き続きオーナー承認待ちの範囲
  (pending-approval.md参照)。承認不要なプロトタイプコード実装・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

- フェーズ45(2026-09-08 15:00 UTC): aircon-pasha(フェーズ165)・course-set-pasha
  (フェーズ86)・line-reservation-aiの3ventureが既に整備済みだった「ブロックしたのに
  課金だけ続く」問い合わせ対応FAQ・返信テンプレートが、本ventureにはまだ無いという
  cross-venture parityのギャップに気付き、unfollow-billing-faq.mdとして新規作成した。
  data-retention-policy.md「削除候補化後の最終確認」節が既にunfollow時のLINE送達不能
  ケースに言及していたにもかかわらず、問い合わせ対応の文面自体は未整備だった。LP掲載用
  FAQ文面(予防)・メール問い合わせ対応テンプレート(事後対応)の2点を他venture3件と
  同一方針で用意し、あわせて本venture固有の複数職人プランの契約者権限モデル
  (subscription-cancellation-flow-design.md「複数職人プラン固有の論点」)を踏まえた
  追加考慮事項(共同利用者からの問い合わせ時は契約者本人のみ手続き可能である旨の案内)を
  盛り込んだ。本ventureはStripe Webhook受信・PortalLinkProvider相当の実装がまだ無い
  段階のため、Stripeカスタマーポータルのプレースホルダ・「ブロック中かつ契約継続中」
  契約者の検知バッチ(他venture3件のblocked-but-billing-detection-design.md相当)は
  今後の課題として明記するにとどめた。コード変更は無く、venture全体83件全件
  (`python3 prototype/test_usage_counter_workshop.py`)・schema検証23件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ46(2026-09-08 17:00 UTC): 本ventureにはこれまでStripe課金関連の
  データモデルが一度も設計されていなかったことに気付き、
  subscription-billing-data-model-design.mdを新規作成した。他3venture
  (aircon-pasha等)は「1事業者=1LINEアカウント=1契約者」構造のため
  `user_profile`に`stripe_customer_id`等を直接持たせるが、本ventureは複数職人プランで
  複数のuser_idが1つの`craftsman_workshop/{workshop_id}`を共同利用し支払い名義人は
  `contractor_user_id`一人に限定される構造(subscription-cancellation-flow-design.md
  「複数職人プラン固有の論点」)であるため、`stripe_customer_id`・
  `subscription_status`・`trial_start_at`・`current_period_end`はworkshop側の
  フィールドとして持たせる設計とした。この配置により、契約者交代
  (contractor-transfer-design.md)発生時もStripe側の顧客・サブスクリプション情報を
  何も変更する必要がなくなり、aircon-pashaフェーズ199・200で発見・横断確認された
  「再連携時にUserProfileを丸ごと上書きし決済関連フィールドが消える」バグと同種の
  問題を構造的に発生させない設計上の利点があることも整理した。`resolve_user_id`の
  解決先が他venture(`stripe_customer_id → user_id`)と異なり
  `stripe_customer_id → workshop_id`になる点も明記した。コード変更は無く、venture全体
  83件全件(`python3 prototype/test_usage_counter_workshop.py`)・schema検証23件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。
- フェーズ47(2026-09-08 19:00 UTC): subscription-billing-data-model-design.md
  (フェーズ46)「未検証・残課題」に残っていたpricing-plan.md「無料トライアル条件(仮)」の
  判定関数設計(他venture`trial-end-condition-a-*-design.md`相当)にtrial-end-condition-
  design.mdとして対応した。他venture(起点=初回生成成功時)をそのまま踏襲せず、
  pricing-plan.mdが期間上限を設けた理由(回数基準だけだと受注が数ヶ月無い場合にトライアル
  無期限化する懸念)に照らし、`trial_start_at`の起点を「workshop作成時」に確定した(初回
  生成成功時を起点にすると期間条件が回数条件と同じ弱点を持ち期間上限の意味が失われるため)。
  月次リセットされる`usage_counter`とは独立な一度切りフラグ`trial_generation_used`を新設し、
  `is_trial_period_over(workshop_id, now, workshop_store)`として「生成1回使用済み」または
  「30日経過」いずれか早い方でトライアル終了と判定する関数をprototype/usage_counter_
  workshop.pyに実装した。pricing-plan.md「無料トライアル条件(仮)」の文言もこの起点確定を
  反映して更新した。トライアル終了後の生成一時停止・通知・`trial_generation_used`書き込み
  処理自体は次の課題として残した。新規テスト4件追加、venture全体83件→87件全件
  (`python3 prototype/test_usage_counter_workshop.py`)・schema検証23件
  (`python3 schema/validate_test_cases.py`)いずれもパスを確認した。承認不要な設計文書
  作成・プロトタイプコード実装のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ48(2026-09-08 20:00 UTC): trial-end-condition-design.md(フェーズ47)
  「6. 今後の課題」1点目のうち、`trial_generation_used`を生成成功時にTrueへ更新する
  書き込み処理を実装した。`WorkshopStoreProtocol`に`set_trial_generation_used`を追加し、
  `process_generation_request`が`check_and_increment_usage`成功後、未設定であれば1回だけ
  Trueへ更新するようにした(`MemberRemovedError`等でusage加算まで到達しなかった場合は
  更新されないことを新規テストで確認)。同課題のもう一方(`is_trial_period_over`を
  トライアル終了後の生成一時停止に組み込む配線)は意図的に見送った。`WorkshopStoreProtocol`
  にはまだ有償契約状態(`subscription_status`相当)を判定する手段が無く(subscription-
  billing-data-model-design.mdフェーズ46「未検証・残課題」1点目が未着手のため)、この状態で
  `is_trial_period_over`の結果だけを使って生成を止めると、30日経過後に正規に有償契約した
  利用者まで永久に生成できなくなる(トライアル終了判定と有償契約済み判定を混同する)バグを
  自ら作り込むことになるため、有償契約判定手段の実装後にまとめて対応する方針とし
  trial-end-condition-design.md「6. 今後の課題」を更新して明記した。新規テスト3件追加、
  venture全体87件→92件全件(`python3 prototype/test_usage_counter_workshop.py`)・
  schema検証23件(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。
  承認不要なプロトタイプコード実装・テスト追加・設計doc記載更新のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。
- フェーズ49(2026-09-08 21:00 UTC): subscription-billing-data-model-design.md
  (フェーズ46)「4. 未検証・残課題」1点目のうち、`WorkshopStoreProtocol`への
  `get_stripe_customer_id`/`set_stripe_customer_id`/`get_subscription_status`/
  `set_subscription_status`メソッド追加を実装した(`InMemoryWorkshopStore`にも対応する
  実装を追加)。`subscription_status`は未契約(トライアル中)workshopの初期値を
  `"trialing"`とし、design.md1節が列挙した4値("trialing"/"active"/"past_due"/
  "canceled")以外を設定しようとした場合は新設の`InvalidSubscriptionStatusError`を
  送出してデータ不整合を早期検知するようにした。Checkout Session発行フロー・Stripe
  Webhookの署名検証・イベントディスパッチの実装、およびフェーズ48で見送った
  `is_trial_period_over`の生成一時停止への配線は、引き続き次の課題として残す
  (`current_period_end`フィールドの読み書きも未着手)。新規テスト4件追加、venture全体
  92件→101件全件(`python3 prototype/test_usage_counter_workshop.py`)・schema検証
  23件(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。承認不要な
  プロトタイプコード実装・テスト追加・設計doc記載更新のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ50(2026-09-08 22:00 UTC): subscription-billing-data-model-design.md
  (フェーズ46・49)「次にやること」1点目のうち、Checkout Session発行フロー(有料プラン
  開始時の申込側導線)をcheckout-initiation-flow-design.mdとして設計した。course-set-pasha/
  checkout-initiation-flow-design.md(フェーズ98)はLIFFアプリ経由のIDトークン検証を
  採用していたが、本ventureはsubscription-cancellation-flow-design.md(フェーズ23)が
  既に確立していた「LINEトーク内の意図検知」方式を有料プラン開始導線にも踏襲することで、
  LINE Platform Webhook受信時点で検証済みの`event.source.userId`をそのまま使え、LIFF
  アプリの新規登録(オーナー承認待ち事項)自体を不要にできる設計とした。契約者
  (`contractor_user_id`)本人のみが開始できる権限チェック、既存`stripe_customer_id`の
  再利用、フェーズ49実装済みの`get_subscription_status`による重複契約防止も設計に含めた。
  Checkout Session作成APIへ渡すパラメータ組み立てを純粋関数として
  `prototype/checkout_session.py`の`build_checkout_session_params(workshop_id, plan_id,
  existing_stripe_customer_id=None)`に実装し(plan_id→Stripe Price ID対応表・
  success_url/cancel_urlは実Stripe接続前の仮プレースホルダ)、新規テスト14件
  (`test_checkout_session.py`)を追加した。Stripe Webhook受信・署名検証・イベント
  ディスパッチ自体、およびフェーズ48で見送った`is_trial_period_over`の生成一時停止配線は
  引き続き次の課題として残す。venture全体101件(usage_counter_workshop)+14件
  (checkout_session)=115件全件・schema検証23件いずれもパスを確認した。承認不要な設計
  文書作成・プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

- フェーズ51(2026-09-08 23:00 UTC): checkout-initiation-flow-design.md(フェーズ50)の
  残課題だった、Stripe Webhook(`checkout.session.completed`)の受信・署名検証・
  イベントディスパッチをstripe-webhook-checkout-completed-design.mdとして設計した。
  `verify_stripe_signature()`はcourse-set-pashaフェーズ93・aircon-pashaフェーズ125と
  同一アルゴリズム(HMAC-SHA256・タイムスタンプ許容誤差300秒)をそのまま踏襲し、
  `handle_checkout_session_completed()`はcheckout-initiation-flow-design.mdが
  `client_reference_id`にworkshop_idを直接設定する設計のため、course-set-pashaの
  連携コード方式ではなくaircon-pashaの直接方式と同じ扱いにできることを整理した。
  フェーズ49実装済みの`set_stripe_customer_id`(未設定時のみ書き込み)・
  `set_subscription_status(workshop_id, "active")`を実際に配線し、`receive_stripe_
  webhook()`エントリポイントとして`prototype/stripe_webhook.py`に実装した(未対応
  イベント種別は200で無視、Stripe側の無限リトライを回避)。新規テスト31件
  (`test_stripe_webhook.py`)を追加、venture全体101件(usage_counter_workshop)+
  14件(checkout_session)+31件(stripe_webhook)=146件全件・schema検証23件いずれも
  パスを確認した。`customer.subscription.deleted`・決済失敗ダニング等の他イベント
  種別対応、および本フェーズ完了により着手可能になった`is_trial_period_over`の
  生成一時停止配線は引き続き次の課題として残す。承認不要な設計文書作成・プロトタイプ
  コード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ52(2026-09-09 00:00 UTC): stripe-webhook-checkout-completed-design.md
  (フェーズ51)の残課題だった、フェーズ48で見送った`is_trial_period_over`の
  トライアル終了時生成一時停止への配線を実装した(trial-end-condition-design.md更新)。
  `process_generation_request`(`prototype/usage_counter_workshop.py`)に、
  `ensure_member_is_active`成功後・`check_and_increment_usage`実行前の段階で
  `is_trial_period_over(...)`が真かつ`get_subscription_status(workshop_id) != "active"`
  の場合に新設の`TrialPeriodOverError`を送出する判定を追加した(呼び出し側は
  `TRIAL_PERIOD_OVER_NOTICE`の文言に変換して返す想定、`WorkshopNotLinkedError`・
  `MemberRemovedError`と同じ扱い)。`"past_due"`(決済失敗)もこの時点では`"active"`
  ではない値として一律ブロック対象とし、ダニング固有の猶予期間つき扱いは
  `invoice.payment_failed`イベント対応(次の課題2点目)に委ねると明記した。ブロック時は
  `check_and_increment_usage`・`trial_generation_used`の更新いずれにも到達しないため、
  月間カウントもトライアル消費フラグも変化しないことを新規テストで確認した。新規テスト
  5件追加、venture全体101件→106件全件(`python3 prototype/test_usage_counter_workshop.py`)・
  schema検証23件(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。
  承認不要なプロトタイプコード実装・テスト追加・設計doc記載更新のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

- フェーズ53(2026-09-09 01:00 UTC): stripe-webhook-checkout-completed-design.md
  (フェーズ51)「未検証・残課題」に残っていた`customer.subscription.deleted`
  (解約確定)へのイベント種別対応を、course-set-pasha/aircon-pashaの既存設計を横展開する
  形でsubscription-canceled-webhook-design.mdとして設計・実装した(`invoice.payment_
  failed`/`invoice.payment_succeeded`のダニング対応は本フェーズの対象外)。
  `client_reference_id`を持たないこのイベント種別のためにworkshop_idを`customer`
  (Stripe顧客ID)から逆引きする必要があり、`WorkshopStoreProtocol`に
  `get_workshop_id_by_stripe_customer_id()`を新設、`InMemoryWorkshopStore`が
  `set_stripe_customer_id()`実行時に逆引き用辞書も同時更新するようにした。
  `handle_customer_subscription_deleted(data_object, workshop_store)`を
  `prototype/stripe_webhook.py`に実装し、`receive_stripe_webhook()`が
  `checkout.session.completed`と並べてディスパッチできるよう配線した(customer欠落は
  400、逆引き失敗〈unresolved〉はStripe側の再送を避けるため200のまま無視、成功時は
  `subscription_status`を`"canceled"`へ更新)。新規テスト16件
  (usage_counter_workshop 3件・stripe_webhook 13件)追加、venture全体146件→167件全件
  (`python3 -m unittest`相当の各`test_*.py`個別実行)・schema検証23件いずれもパスを
  確認した。承認不要な設計文書作成・プロトタイプコード実装・テスト追加のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

## 次にやること(候補)

(2026-09-11 07:00 UTC、フェーズ82で更新。blocked-but-billing系はフェーズ80・81で
候補検知〜オーナー通知設計まで一通り完了したため、残る項目を整理し直した。)

- (解消済み 2026-09-11 05:00 UTC・フェーズ80: unfollow-billing-faq.md(フェーズ45)
  「今後の課題」だった「ブロック中かつ契約継続中」契約者の検知バッチは
  blocked-but-billing-detection-design.mdとして設計・実装した)
- (解消済み 2026-09-11 06:00 UTC・フェーズ81: 上記の候補一覧を実際にオーナーへ届ける
  通知手段は、本venture一貫のプレーンテキスト送信へ翻案しblocked-but-billing-owner-
  notification-design.mdとして設計・実装した。残るのは実Firestoreフィールド追加・実際の
  Cloud Scheduler作成・実LINE API接続のみで、いずれもオーナー承認待ちの範囲〈下記〉)
- trial-end-condition-design.md(フェーズ76の発見)の残課題: 「生涯最初の1回のみ
  無料」というトライアル条件により、limit-approaching-notification-design.mdの
  is_trial=True分岐(残り1回/上限超過通知)が実際のオンボーディング経路では
  到達不能となっている。コード自体の削除・トライアル条件の再設計は
  pricing-plan.mdに関わる製品判断のため、引き続きオーナー判断待ち。
- 想定顧客ヒアリング(ライディングショップ池上・エクウスワールド)の実施は
  2026-09-11 04:00 UTC付でpending-approval.mdに新規記録済み。オーナー承認待ち。
  承認後は本エージェントに電話発信・LINE送信機能が無いため、電話・フォーム送信の
  実連絡はオーナー自身が行うか、Gmail連携接続後の送信直前確認を経てのみ行う。
- ジャパンギャロップスインポーターの正式化・除外の最終判断は、上記ヒアリングが
  承認・実施された際に併せて確認する(公開情報のみでの追加探索は費用対効果が
  低いため見送り済み)。
- `receive_stripe_webhook()`実HTTPエントリポイントでの`push_client`配線・
  実LINE公式アカウント接続・実LLM API検証はいずれもオーナー承認待ち
  (pending-approval.md参照、外部サービスの新規接続・アカウント作成を伴うため)。

- フェーズ54(2026-09-09 02:00 UTC): subscription-canceled-webhook-design.md
  (フェーズ53)「4. 未検証・残課題」に残っていた、`customer.subscription.deleted`
  受信時の契約者向け解約完了案内(LINEトーク送信)をsubscription-cancellation-
  notification-design.mdとして設計・実装した。着手にあたり、
  subscription-cancellation-flow-design.md(フェーズ23)2節が草案していた案内文言
  「それまでは引き続きご利用いただけます」が、`customer.subscription.deleted`が
  契約完全終了後に届くイベントであるという事実と矛盾していることを発見し
  (course-set-pashaフェーズ155が発見したのと同種の誤り)、course-set-pasha/
  aircon-pashaが確定した「契約終了のご案内」パターンに合わせて文言を訂正した
  (同ファイルにも訂正を反映)。本venture固有の契約構造(`craftsman_workshop/
  {workshop_id}`単位、支払い名義人は`contractor_user_id`一人)を踏まえ、
  course-set-pashaの`handle_subscription_cancelled(user_id, push_client)`をそのまま
  踏襲せず`handle_subscription_cancelled(workshop_id, workshop_store, push_client)`
  とし、関数内部で`get_contractor_user_id()`により送信先を契約者本人に限定する設計とした
  (共同利用者には送らない)。新規モジュールprototype/subscription_cancellation_
  notification.pyを作成し、`handle_customer_subscription_deleted()`・
  `receive_stripe_webhook()`双方に`push_client`引数(省略時None、後方互換)を追加して
  配線した。状態更新(`set_subscription_status`)は通知の送信成否と独立して常に行う
  設計とした(course-set-pashaフェーズ155と同じ判断)。新規テスト13件
  (test_subscription_cancellation_notification.py 9件・test_stripe_webhook.py
  追加分4件)、venture全体167件→184件全件・schema検証23件いずれもパスを確認した。
  `customer.subscription.updated`のcancel_at_period_end前後比較(解約予約受理・取消)
  対応は本venture未着手のため次の課題として残した。承認不要な設計文書作成・記載訂正・
  プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 02:00 UTC(フェーズ54: `customer.subscription.deleted`受信時の
契約者向け解約完了案内をsubscription-cancellation-notification-design.mdとして設計・
実装、あわせてsubscription-cancellation-flow-design.md 2節の案内文言の事実矛盾を訂正。
`customer.subscription.updated`のcancel_at_period_end対応・`invoice.payment_failed`/
`invoice.payment_succeeded`のダニング対応は次の課題として残る)

- フェーズ55(2026-09-09 03:00 UTC): フェーズ54「5. 残課題」に残っていた
  `customer.subscription.updated`のcancel_at_period_end前後比較による「解約予約受理・
  解約取り消し」案内を、subscription-cancellation-scheduled-notification-design.mdとして
  設計・実装した。course-set-pashaフェーズ156の設計(`classify_cancel_at_period_end_
  change()`・`render_subscription_cancellation_scheduled_message()`・
  `render_subscription_cancellation_rescheduled_message()`・`handle_subscription_
  cancellation_update()`)を本venture固有のworkshop単位契約構造へ翻案し、通知先を
  契約者本人(`contractor_user_id`)に限定した。本venture側にはPortalLinkProvider相当の
  抽象化がまだ無いため、course-set-pasha版と異なり案内メッセージへのURL差し込みは行わない
  簡略化を採用し、design.mdに理由を明記した。`stripe_webhook.py`に
  `handle_customer_subscription_updated()`を新規追加し、`receive_stripe_webhook()`が
  受理するイベント種別に`customer.subscription.updated`を加えて配線した(本イベントは
  `set_subscription_status`等の状態変更を一切伴わない)。新規テスト37件
  (test_subscription_cancellation_notification.py 19件・test_stripe_webhook.py
  追加分18件)、venture全体184件→221件全件・schema検証23件いずれもパスを確認した。
  承認不要な設計文書作成・プロトタイプコード実装・テスト追加のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。

最終更新: 2026-09-09 03:00 UTC(フェーズ55: `customer.subscription.updated`の
cancel_at_period_end前後比較による解約予約受理・解約取り消し通知を
subscription-cancellation-scheduled-notification-design.mdとして設計・実装。
`invoice.payment_failed`/`invoice.payment_succeeded`のダニング対応、実際の解約取り消し
メッセージ受信時の処理(LINEトーク内での取り消し意図検知)は次の課題として残る)

- フェーズ56(2026-09-09 05:00 UTC): フェーズ55「残課題」に残っていた
  `invoice.payment_failed`/`invoice.payment_succeeded`のダニング対応を、
  payment-failure-dunning-design.md(新規)として設計・実装した。course-set-pasha・
  aircon-pasha・line-reservation-aiのpayment-failure-dunning-design.mdを本venture固有の
  前提(workshop単位契約・契約者1名限定・PortalLinkProvider相当の抽象化が未実装)へ
  翻案する過程で、usage_counter_workshop.mdフェーズ52が意図的に見送っていた既知の制約
  (`subscription_status="past_due"`になった瞬間に猶予期間なく生成が即座に止まっていた)を
  発見し、本フェーズで解消した。`WorkshopStoreProtocol`へ`get_payment_failure_detected_at`/
  `set_payment_failure_detected_at`/`clear_payment_failure_detected_at`を追加し、
  `is_payment_suspended()`(検知時刻から7日間の猶予、is_trial_period_overと同じ都度算出
  方式)を新設したうえで、`process_generation_request()`の`"past_due"`判定を
  `is_trial_period_over`分岐から独立した専用分岐に切り出した。新規モジュール
  `prototype/payment_failure_notification.py`(`render_payment_failure_detected_message()`・
  `classify_payment_recovery()`・`handle_payment_failure_detected()`・
  `handle_payment_succeeded()`)を作成し、`stripe_webhook.py`に
  `handle_invoice_payment_failed()`・`handle_invoice_payment_succeeded()`を追加、
  `receive_stripe_webhook()`が受理するイベント種別に`invoice.payment_failed`/
  `invoice.payment_succeeded`を加えて配線した。本venture固有の簡略化として、(1)
  PortalLinkProvider相当が未実装のため通知本文へURLを差し込まない(design 1節)、
  (2)3日前リマインド送信インフラが本フェーズの対象外のため、決済成功時の分類を他
  venture3件の3〜4分岐ではなく2分岐(制限モードからの復旧/猶予期間中の解消〈通知なし・
  状態リセットのみ〉)に簡略化した(design 4節)、という2点を明記した。新規テスト62件
  (test_usage_counter_workshop.py 3件差し替え〈旧`past_due`即時ブロックのテストは
  猶予期間ありの正しい挙動へ更新〉、test_payment_failure_notification.py新規22件、
  test_stripe_webhook.py新規17件)、venture全体221件→283件全件・schema検証23件いずれも
  パスを確認した。承認不要な設計文書作成・記載訂正・プロトタイプコード実装・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 05:00 UTC(フェーズ56: `invoice.payment_failed`/
`invoice.payment_succeeded`のダニング対応をpayment-failure-dunning-design.mdとして
設計・実装。あわせてフェーズ52が意図的に見送っていた「`past_due`即時ブロック(猶予期間
なし)」という既知の制約を解消した。3日前リマインド送信・運営者向け通知は、本venture側の
定期実行基盤(Cloud Scheduler等)の設計自体がまだ無いため次の課題として残る)

- フェーズ57(2026-09-09 06:00 UTC): checkout-initiation-flow-design.md(フェーズ50)
  「残課題」に残っていた「意図検知(「有料プランを始めたい」等)のllm-system-prompt-
  draft.mdへの厳守事項追加(解約意図検知の厳守事項7aと対になる新規項目)」に対応し、
  厳守事項7b(有料プラン開始意図検知)を新設した。7aの(iv)「解約完了・ポータルリンクを
  含む文言は自己判断で返さない」と同じ設計思想を踏襲し、7bも「開始手続きの案内(Checkout
  SessionのURL等)を自己判断で返さない」構成とした。理由は、実際のURL発行は
  checkout-initiation-flow-design.md 3節の`handle_checkout_intent`(契約者本人確認・
  重複契約確認を経る)が担う前提であり、LLM側が意図判定の段階でURLまで生成すると契約者
  以外や既契約中のケースでも誤って開始案内を返しかねないためである。対応するschema拡張
  (status enumへのcheckout_intent/pricing_inquiry相当の追加)は、
  checkout-initiation-flow-design.md自体が実LINE Messaging API・実Stripe API接続を
  オーナー承認待ちとして見送っている段階であるため、7aのときのような即時追随の必要性は
  無いと判断し次の課題として残した。プロンプト文面の設計のみでコード変更は無く、
  venture全体283件(test_checkout_session.py 14件・test_payment_failure_
  notification.py 22件・test_stripe_webhook.py 107件・test_subscription_
  cancellation_notification.py 28件・test_usage_counter_workshop.py 112件)・
  schema検証23件いずれも変更前と同じ結果でパスすることを確認した。承認不要な設計文書
  作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 06:00 UTC(フェーズ57: 厳守事項7b〈有料プラン開始意図検知〉を
llm-system-prompt-draft.mdに新設。対応するschema拡張は実API接続オーナー承認待ちのため
次の課題として残る)

- フェーズ58(2026-09-09 07:00 UTC): フェーズ57で次の課題としていた厳守事項7b
  (有料プラン開始意図検知)対応のschema拡張を行った。`status` enumへ
  `checkout_intent`/`pricing_inquiry`/`checkout_intent_unclear`の3値、非nullフィールド
  `checkout_notice`を新設し、`includes_checkout_url`は`kind`によらず常にfalse(実際の
  Checkout Session URL発行はcheckout-initiation-flow-design.md 3節の
  `handle_checkout_intent`に委ね、LLM側の自己判断では返さない設計)であることを
  `validate_test_cases.py`側のクロスフィールド検証で担保した。新規期待出力テスト
  ケース3件(有料プラン開始意図/料金問い合わせ/意図不明瞭それぞれ)、
  `includes_checkout_url`不一致を検出するネガティブテストケース1件を追加し、schema検証
  23件→27件全件・venture全体283件いずれもパスを確認した。承認不要な設計文書更新・
  schema/テストコード変更のみで、外部サービスへの公開・アカウント作成・支払い等は
  今回発生していないためpending-approval.mdへの追記なし。
  (本エントリは2026-09-09 08:00 UTC・フェーズ59作業時に、README.mdへの記録が漏れて
  いたことを発見し遡及記録したもの。実際の作業自体はフェーズ58〈07:00 UTCコミット〉で
  完了済み。)

最終更新: 2026-09-09 07:00 UTC(フェーズ58: 厳守事項7b対応のschema拡張。
`status` enumへcheckout_intent/pricing_inquiry/checkout_intent_unclearの3値追加、
includes_checkout_urlが常にfalseであることをテストで担保)

- フェーズ59(2026-09-09 08:00 UTC): checkout-initiation-flow-design.md(フェーズ50)
  「残課題」節を確認したところ、(1)Stripe Webhook(`checkout.session.completed`)受信・
  署名検証・実装が未着手と記載されていたが実際にはフェーズ51で対応済み、(2)
  `is_trial_period_over`の生成一時停止への配線が未着手と記載されていたが実際には
  フェーズ52で対応済み、という2件の記載漏れ(いずれも作成当時〈フェーズ50〉時点では
  正しかったが、後続フェーズでの対応後に訂正されないまま残っていたもの)を発見し、
  該当箇所にコード確認結果とあわせて訂正を追記した。残っていた真の未着手項目
  「トライアル終了通知メッセージ自体は本venture未設計」に対応し、
  trial-end-notification-design.mdを新規作成した。aircon-pasha/trial-end-notification-
  design.md(フェーズ129)の構成(トリガー条件→通知メッセージ→終了後の挙動→実装への
  影響メモ→今後の課題)を踏襲しつつ、本venture固有の無料トライアル条件(「生涯最初の
  生成1回まで無料」という一度切りフラグ+「workshop作成から30日」の二重条件、
  trial-end-condition-design.mdフェーズ47で確定)に合わせ、(A)生涯最初の生成完了時
  (返信に便乗)・(B)30日経過時(日次スケジューラ、本venture未着手のため次の課題)の
  2経路と二重送信防止方針を設計した。通知文言にはcontent-generation-time-estimate.md
  (フェーズ18)の1回20分試算を用いた「浮いた事務作業時間の目安」を含めた。実コード
  実装・(B)経路用の日次スケジューラ本体・通知メッセージからの直接ボタン起動配線は
  いずれも次の課題として残した。コード変更は無く、venture全体283件
  (`python3 prototype/test_usage_counter_workshop.py`)・schema検証27件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計文書作成・記載漏れ訂正のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 08:00 UTC(フェーズ59: checkout-initiation-flow-design.mdの記載漏れ
2件〈Stripe Webhook実装・トライアル終了時生成一時停止配線、いずれも既に対応済みだった
のに残課題のまま放置されていた〉を訂正。残っていた真の未着手項目だったトライアル終了
通知メッセージをtrial-end-notification-design.mdとして新規設計。実コード実装・日次
スケジューラ本体は次の課題として残る)

- フェーズ60(2026-09-09 09:00 UTC): trial-end-notification-design.md(フェーズ59)
  「5. 実装への影響メモ」に残っていた(A)生涯最初の生成完了経路の通知要否判定を
  `prototype/usage_counter_workshop.py`に実装した。`WorkshopStoreProtocol`へ
  `get_trial_end_notified_at`/`set_trial_end_notified_at`を追加(命名は既存の
  `get_payment_failure_detected_at`と同スタイル)し、`process_generation_request()`で
  `trial_generation_used`が今回の呼び出しで初めてFalse→Trueになった、かつ
  `trial_end_notified_at`未設定の場合に限り`GenerationRequestResult.
  trial_end_notification_due`をTrueにして返しつつ`trial_end_notified_at`を書き込む
  (二重送信防止、design.md 2節)処理を追加した。2回目以降の生成では再判定しないこと、
  (B)経路相当で既に通知済みの場合は(A)経路条件を満たしても再通知しないことをテストで
  確認した。新規テスト3件追加、venture全体283件→291件全件
  (`test_checkout_session.py`14件・`test_payment_failure_notification.py`22件・
  `test_stripe_webhook.py`107件・`test_subscription_cancellation_notification.py`28件・
  `test_usage_counter_workshop.py`120件)・schema検証27件いずれもパスを確認した。
  (A)経路の実LINEプッシュ送信配線・(B)経路の日次スケジューラ本体・3節の通知メッセージ
  からの直接ボタン起動配線はいずれも次の課題として残る。承認不要な設計文書更新・
  プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 09:00 UTC(フェーズ60: トライアル終了通知(A)経路〈生涯最初の生成
完了〉の通知要否判定を実装。`trial_end_notified_at`による二重送信防止フラグを追加し、
`process_generation_request`が`trial_end_notification_due`を返すようにした。実LINE
プッシュ送信配線・(B)経路の日次スケジューラ本体は次の課題として残る)

- フェーズ61(2026-09-09 10:00 UTC): trial-end-notification-design.md(フェーズ59)6節に
  残っていた課題のうち、3節の通知メッセージ「▼ 有料プランへ進む」ボタンのpostback_data
  形式を設計・実装した。aircon-pashaのtrial-end-condition-a-cta-design.md(フェーズ137)が
  確立した`"action=start_checkout"`(プラン未指定時はDEFAULT_CHECKOUT_PLAN=standardを既定)/
  `"action=start_checkout&plan=<plan_id>"`形式をそのまま踏襲し、`prototype/checkout_session.py`に
  `build_start_checkout_postback_data(plan_id)`・`parse_start_checkout_postback_data(data)`を
  実装した(design.md 3.1節)。未知のplan_idは`build_checkout_session_params()`と同じ安全側
  方針でValueError(build)・None(parse)とした。新規テスト9件追加、venture全体291件→300件全件
  (`test_checkout_session.py`14件→23件・他4ファイルは変更なし)・schema検証27件いずれも
  パスを確認した。実際にLINE返信・プッシュメッセージへボタンを添付して送る配線
  (aircon-pashaの`ReplyClient.reply()`quick_reply引数・`process_postback_event()`相当)は、
  本venture自体にLINE Webhook層(`cloud_function_webhook.py`相当)がまだ存在しないため
  引き続き次の課題として残す。承認不要な設計文書更新・プロトタイプコード実装・テスト追加
  のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

最終更新: 2026-09-09 10:00 UTC(フェーズ61: トライアル終了通知の「▼ 有料プランへ進む」
ボタンのpostback_data形式をaircon-pashaフェーズ137と同じ形式で確定し、組み立て・解釈用の
純粋関数2つを実装。新規テスト9件追加、venture全体300件・schema検証27件いずれもパス。
実LINE返信への添付配線は本venture未着手のWebhook層を要するため次の課題として残る)

- フェーズ62(2026-09-09 12:00 UTC): trial-end-notification-design.md(フェーズ59)6節に
  繰り返し残っていた「本venture自体にLINE Webhook層(`cloud_function_webhook.py`相当)が
  まだ存在しない」というギャップに対応する最初の一歩として、`prototype/cloud_function_
  webhook.py`を新規作成した。aircon-pashaのwebhook-http-entry-point-design.md(フェーズ115)・
  trial-end-condition-a-cta-design.md(フェーズ137)と同じ構成要素のうち、(1)`verify_line_
  signature()`(HMAC-SHA256署名検証、line-reservation-ai/course-set-pasha/aircon-pashaと同じ
  実装)、(2)`QuickReplyButton`/`ReplyClient`(Protocol)/`InMemoryReplyClient`(返信へ
  postbackボタンを添付するための抽象化)、(3)`format_trial_end_notification_message()`
  (trial-end-notification-design.md 3節の通知文言。経路(A)生成1回完了時は「浮いた事務作業
  時間の目安」を含め、経路(B)相当の生成0回時は当該行を省略する分岐を実装)の3点のみを
  今回のスコープとした。schema/output.schema.jsonの17通りのstatus分岐をテキスト返信へ
  変換する`process_memo_event()`本体・`receive_webhook()`(HTTPエントリポイント)・
  `dispatch_webhook_events()`は本venture側にまだ存在しないため対象外とし、次の課題として
  残す。新規テスト12件追加、venture全体300件→320件全件(`test_checkout_session.py`23件・
  `test_cloud_function_webhook.py`12件〈新設〉・`test_payment_failure_notification.py`22件・
  `test_stripe_webhook.py`107件・`test_subscription_cancellation_notification.py`28件・
  `test_usage_counter_workshop.py`120件)・schema検証27件いずれもパスを確認した。承認不要な
  プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 12:00 UTC(フェーズ62: LINE Webhook層の基盤部品(署名検証・quick_reply
添付用ReplyClient抽象化・トライアル終了通知文言の組み立て)を`prototype/cloud_function_
webhook.py`として新規実装。新規テスト12件追加、venture全体320件・schema検証27件いずれも
パス。process_memo_event()本体・HTTPエントリポイント・dispatch層は次の課題として残る)

- フェーズ63(2026-09-09 13:00 UTC): フェーズ62で次の課題として残した3項目のうち、
  process_memo_event()本体(LLM出力の17通りのstatus分岐をテキスト返信へ変換する処理)に
  着手した。aircon-pasha/prototype/cloud_function_webhook.pyのprocess_memo_event()と
  同じ骨格(LLM呼び出し即時1回リトライ→schema/validate_test_cases.pyのvalidate_against_
  schema()・validate_cross_field_rules()で検証→エラーがあれば同一入力で1回だけ再生成→
  それでも検証エラーが残る場合は定型フォールバック文言)を踏襲し、`format_reply_text()`が
  schema/output.schema.jsonの全17通りのstatus値(generated/out_of_scope/insufficient_input/
  cancellation_intent/downgrade_intent/cancellation_unclear/member_retention_selection/
  member_retention_unclear/contractor_transfer_selection/contractor_transfer_unclear/
  contractor_transfer_confirmed/contractor_transfer_cancelled/contractor_transfer_
  reconfirm_unclear/contractor_transfer_expired_notice/checkout_intent/pricing_inquiry/
  checkout_intent_unclear)を返信文へ振り分ける。cancellation_intent/downgrade_intent/
  cancellation_unclearについては、aircon-pashaと同じ`PortalLinkProvider`Protocol・
  `render_subscription_procedure_notice()`(StripeカスタマーポータルURLプレースホルダの
  置換、未接続時は安全側フォールバック文言)も新規実装した。

  本venture側にはaircon-pasha/course-set-pashaが持つusage_counter・profile_store
  (トライアル生成回数カウント・生成一時停止・決済失敗制限モード・初回生成セルフチェック
  案内)に相当するストア・スケジューラがまだ実装されていないため、それらの配線は今回
  スコープ外とし引き続き次の課題として残した(receive_webhook()〈HTTPエントリポイント〉・
  dispatch_webhook_events()・follow/unfollowイベント処理も同様に未着手のまま)。

  新規テスト12件追加(非テキストメッセージの無視、generated時の3出力見出し、out_of_scope/
  insufficient_inputのメッセージそのまま転記、cancellation_intentのポータルURL置換〈provider
  接続時・未接続時双方〉、cancellation_unclearのプレースホルダ無し文面、checkout_intent・
  contractor_transfer_expired_noticeの単純転記、検証エラー1回リトライ成功、2回とも失敗時の
  フォールバック、LLM API呼び出し失敗時のフォールバック)。venture全体320件→346件全件
  (`python3 test_*.py`を各ファイルで直接実行、`python3 -m unittest discover`ではなく
  この形式が実際の実行方法である点は本フェーズで確認した。README過去記載の「unittest
  discover」表記は実態と異なるため今後の記載では留意する)・schema検証27件いずれもパスを
  確認した。承認不要なプロトタイプコード実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 13:00 UTC(フェーズ63: process_memo_event()本体を実装し、schema/
output.schema.jsonの17通りのstatus分岐すべてを返信文へ変換できるようにした。
cancellation_intent系のStripeカスタマーポータルURL置換〈PortalLinkProvider〉も実装。
新規テスト12件追加、venture全体346件・schema検証27件いずれもパス。usage_counter・
profile_store連携〈トライアル/生成一時停止/決済失敗制限モード〉・HTTPエントリポイント・
dispatch層は次の課題として残る)

- フェーズ64(2026-09-09 14:00 UTC): フェーズ63で次の課題として残した項目のうち、
  usage_counter・profile_store連携(トライアル生成回数カウント・生成一時停止・決済失敗
  制限モード)に着手した。本venture固有の`usage_counter_workshop.py`が既に持つ統合
  エントリポイント`process_generation_request()`(workshop単位、フェーズ30〜60で実装・
  テスト済み)を`process_memo_event()`からLLM呼び出し前に呼び出すよう配線した。
  `user_profile_store`・`workshop_store`・`usage_counter_store`の3引数を新設し
  (いずれも省略可、未接続時は従来通りストア連携なしで動作する後方互換設計)、
  `TrialPeriodOverError`・`PaymentSuspendedError`送出時はLLM呼び出しを行わずそれぞれ
  `TRIAL_PERIOD_OVER_NOTICE`(本フェーズ新規の文言)・`PAYMENT_SUSPENDED_NOTICE`
  (payment-failure-dunning-design.md 4節「制限モード移行時(段階3)」の文言をそのまま
  `prototype/payment_failure_notification.py`に実装)を返す。いずれもtrial-end-condition-
  design.md(フェーズ52)・payment-failure-dunning-design.md(フェーズ56)が呼び出し側の
  変換先として既に名指ししていた定数名をそのまま採用した。`process_generation_request()`が
  返す`trial_end_notification_due=True`(経路(A)、生涯最初の生成成功)の場合は、
  最終的な返信本文の末尾に`format_trial_end_notification_message(1)`(フェーズ62実装済み)
  を付記し`TRIAL_END_QUICK_REPLY`を添付する(aircon-pashaフェーズ137相当)。
  `WorkshopNotLinkedError`・`MemberRemovedError`は、本venture側にまだdispatch層(連携状態に
  応じたルーティング振り分け、aircon-pashaのdispatch_webhook_events()相当)が存在せず
  「process_memo_eventへ到達するのは常に連携済みuser_idのみ」という前提が確立していない
  ため、あえて捕捉せず伝播させる設計とし、次の課題として明記した。また、
  `process_generation_request()`のLLM呼び出し前実行という設計上、`trial_end_notified_at`が
  ブロック判定・カウント成功の時点で書き込まれるため、その後LLM呼び出し自体が失敗する・
  検証エラーが解消しない場合に通知が「送信済み扱いのまま実際には届かない」既知の制約が
  あることをdocstringに明記した(発生頻度は低いと見込むが未解消)。新規テスト7件追加
  (トライアル終了ブロック・active時の継続生成・決済制限モードブロック・猶予期間内の
  継続生成・初回成功時の通知便乗・2回目以降の非重複・ストア未接続時の後方互換動作)、
  venture全体346件→371件全件(`test_checkout_session.py`23件・`test_cloud_function_
  webhook.py`46件→71件・`test_payment_failure_notification.py`22件・
  `test_stripe_webhook.py`107件・`test_subscription_cancellation_notification.py`28件・
  `test_usage_counter_workshop.py`120件)・schema検証27件いずれもパスを確認した。
  `receive_webhook()`(HTTPエントリポイント)・`dispatch_webhook_events()`・初回生成
  セルフチェック案内(aircon-pasha相当)はいずれも本venture未着手のため引き続き次の課題
  として残る。承認不要なプロトタイプコード実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 14:00 UTC(フェーズ64: process_generation_request()をprocess_memo_
event()のLLM呼び出し前に配線し、トライアル終了・決済失敗制限モード時のブロック応答
(TRIAL_PERIOD_OVER_NOTICE/PAYMENT_SUSPENDED_NOTICE)と、生涯最初の生成成功時のトライアル
終了通知便乗を実装した。新規テスト7件追加、venture全体371件・schema検証27件いずれも
パス。receive_webhook()・dispatch_webhook_events()・初回生成セルフチェック案内は次の課題
として残る)

- フェーズ65(2026-09-09 14:01 UTC): フェーズ64で次の課題として残した3項目のうち、
  dispatch_webhook_events()とreceive_webhook()(HTTPエントリポイント)を実装した
  (prototype/cloud_function_webhook.py)。aircon-pashaのwebhook-http-entry-point-design.md
  (フェーズ115)・dispatch_webhook_events()(フェーズ111〜114)と同じ構成を踏襲するが、
  本ventureはfollow/unfollow/postbackイベントの処理関数(process_follow_event()等)が
  まだ存在しないため、本フェーズはmessageイベントのprocess_memo_event()への振り分けのみを
  スコープとし、それ以外の種別(follow/unfollow/postback等)は全て`ignored_types`に記録して
  素通りする設計とした(次の課題として明記)。`dispatch_webhook_events()`は`llm_call`・
  `reply_client`のいずれかが未接続(None)の場合は該当イベントを一切処理しない安全側
  フォールバックを持ち、`user_profile_store`等の3つはprocess_memo_event()自体が省略可能な
  設計(フェーズ64)のため未接続でもmessageイベント処理自体は行う。`receive_webhook()`は
  aircon-pasha/course-set-pashaと同じ4段階(署名検証→JSON parse→"events"キー形式検証→
  dispatch_webhook_events()への委譲)の薄いエントリポイントとし、`get_runtime_dependencies()`
  (現時点では空の辞書、実LINE公式アカウント開設・実GCPプロジェクト作成はオーナー承認待ち)・
  `main()`(Cloud FunctionsのHTTPエントリポイント、`functions_framework`想定)もあわせて
  実装した。テスト作成時、テストヘルパー`_make_event()`に実際のLINE webhookイベントが持つ
  `"type": "message"`キーが欠落していたことが判明し(process_memo_event()単体テストでは
  event["type"]を参照しないため問題化していなかった潜在的な不整合)、本フェーズであわせて
  修正した。新規テスト11件追加、venture全体371件→393件全件(`python3 test_*.py`を各ファイル
  で直接実行)・schema検証27件いずれもパスを確認した。実LINE Messaging API接続・実LINE公式
  アカウント開設・実GCPプロジェクト作成はいずれもオーナー承認待ち(pending-approval.md参照)
  のため未接続のまま。follow/unfollow/postbackイベントの処理関数自体、初回生成セルフチェック
  案内(aircon-pasha相当)は本venture未着手のため引き続き次の課題として残る。承認不要な
  プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 14:01 UTC(フェーズ65: dispatch_webhook_events()・receive_webhook()
〈HTTPエントリポイント〉・get_runtime_dependencies()・main()を実装し、messageイベントを
process_memo_event()へ振り分けられるようにした(follow/unfollow/postbackは次の課題として
ignored_types記録のみ)。新規テスト11件追加、venture全体393件・schema検証27件いずれも
パス。follow/unfollow/postback処理関数・初回生成セルフチェック案内は次の課題として残る)

- フェーズ66(2026-09-09 17:00 UTC): フェーズ65で次の課題として残した「follow/unfollow/
  postback処理関数自体は本venture未着手」に着手する第一歩として、followイベント処理の
  前提となる連携コード発行・解決・workshop新規作成ロジックをprototype/workshop_linking.py
  として新規実装した(craftsman-account-linking-design.md フェーズ25の2〜3節)。
  course-set-pasha/prototype/user_id_linking.pyのコード発行(`issue_linking_code_on_
  follow`)・パージ(`purge_expired_links`/`delete_pending_links_for_user`)ロジックを
  ほぼそのまま踏襲しつつ、解決先を(申込フォームが存在しない本venture固有の事情により)
  フォーム送信ではなく`craftsman_workshop`の新規作成(`create_workshop_from_linking_code`)
  へ差し替えた。実装の過程で、既存のcheck_and_increment_usage()がトライアル中の生成
  リクエストでもworkshop_store.get_plan_id()を必ず参照するため、workshop新規作成時に
  plan_id未設定のままだと生涯最初の無料生成がKeyErrorで失敗するという既存の抜け穴が
  判明し、craftsman-account-linking-design.mdに7節を追記して「workshop作成時は最安
  プラン`"light"`で仮設定し、Checkout完了時に実際に選ばれたプランで上書きする」という
  暫定対応を決定した(上書き処理自体は本ファイル未着手で次の課題)。あわせて
  `UserProfileStoreProtocol`へ`link(user_id, workshop_id)`を追加した
  (`InMemoryUserProfileStore.link()`自体はフェーズ26から既存)。新規テスト23件追加、
  venture全体393件→416件全件・schema検証27件いずれもパスを確認した。
  `process_follow_event()`自体(本モジュールをcloud_function_webhook.pyへ配線する処理)・
  unfollow/postback処理関数・5節の招待コード(`pending_workshop_invites`)・4節のStripe
  Checkout連携(`client_reference_id`=workshop_id)・初回生成セルフチェック案内は
  いずれも未着手のため引き続き次の課題として残る。承認不要なプロトタイプコード実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。

- フェーズ67(2026-09-09 17:02 UTC、遡及記録): フェーズ66追記7節で次の課題としていた
  Checkout完了時のplan_id上書き配線を実装した(craftsman-account-linking-design.md 8節)。
  `checkout_session.build_checkout_session_params()`がCheckout Session作成時に
  `metadata.plan_id`を埋め込み、`stripe_webhook.handle_checkout_session_completed()`が
  既知のplan_idの場合のみ`workshop_store.set_plan()`で上書きするようにした
  (course-set-pashaの`metadata.plan`方式を踏襲)。`WorkshopStoreProtocol`に`set_plan()`の
  宣言が漏れていたため追加した。新規テスト3件+既存テストへのアサーション1件追加、
  venture全体416件→423件全件・schema検証27件いずれもパスを確認した。承認不要な
  プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
  (本エントリはコミット7a55808時点でREADME.mdへの記載自体が漏れていたため、フェーズ68で
  遡及記録した。)

- フェーズ68(2026-09-09 UTC): フェーズ66「process_follow_event()自体(workshop_linking.py
  をcloud_function_webhook.pyへ配線する処理)は未着手」に着手した。
  craftsman-account-linking-design.md 2節の通り、友だち追加(`follow`イベント)時に
  `workshop_linking.issue_linking_code_on_follow()`で連携コードを発行し、
  `format_follow_welcome_message()`で組み立てたウェルカムメッセージ(コード埋め込み、
  本ventureには申込フォームが無いためcourse-set-pashaと異なりフォームURLの差し込みは
  行わない)を返信する`process_follow_event()`を新規実装した。あわせて
  `dispatch_webhook_events()`・`receive_webhook()`に`linking_store`・`rng`引数を追加し、
  `"follow"`種別のイベントも(`reply_client`・`linking_store`双方が接続済みの場合のみ)
  `process_follow_event()`へ振り分けるようにした(`DispatchResult`に`follow_results`を
  新設)。未接続時・`unfollow`/`postback`は従来通り`ignored_types`に記録して素通りする
  安全側フォールバックを維持した。友だち追加後にユーザーがコードをトーク上に送り返した
  際の解決(message event側でコード形式のテキストを`create_workshop_from_linking_code()`
  へルーティングする処理)は本フェーズの対象外とし、引き続き次の課題として残す。
  新規テスト12件追加、venture全体423件→444件全件・schema検証27件いずれもパスを確認した。
  承認不要なプロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 UTC(フェーズ68: 友だち追加時に連携コードを発行しウェルカムメッセージを
返信するprocess_follow_event()を新規実装し、dispatch_webhook_events()のfollow種別振り分けに
配線した。新規テスト12件追加、venture全体444件・schema検証27件いずれもパス。トーク上で
送り返されたコードのworkshop作成への解決(message event側のルーティング)・unfollow/
postback処理関数は次の課題として残る)

- フェーズ69(2026-09-09 UTC): フェーズ68で次の課題として残した「友だち追加後にユーザーが
  コードをトーク上に送り返した際の解決(message event側でコード形式のテキストを
  `create_workshop_from_linking_code()`へルーティングする処理)」を実装した
  (craftsman-account-linking-design.md 10節)。`cloud_function_webhook.
  process_message_event()`を新設し、`dispatch_webhook_events()`のmessageイベント委譲先を
  `process_memo_event()`から本関数へ差し替えた(aircon-pashaのprocess_message_event()と
  同じ骨格)。`user_profile_store`・`workshop_store`・`linking_store`の3つ全てが渡された
  場合のみ、(1)連携済みuser_idはそのまま`process_memo_event()`へ委譲、(2)未連携の場合は
  受信テキストを`workshop_linking.create_workshop_from_linking_code()`へ渡し、成功時は
  新設の`LINKING_SUCCESS_MESSAGE`を返してLLM呼び出しには進まず、失敗時(コード不一致・
  期限切れ・依頼メモの先送り送信のいずれも区別しない)・user_id欠落時は新設の
  `LINKING_REQUIRED_MESSAGE`を返す、という順で分岐する。3ストアのいずれかが未接続の場合は
  連携判定自体を行わずフェーズ68以前と同じく`process_memo_event()`へ直接委譲する後方互換を
  維持した。新規テスト18件追加、venture全体444件→462件全件・schema検証27件いずれもパスを
  確認した。承認不要なプロトタイプコード実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-09 UTC(フェーズ69: message event側でコード形式のテキストを
create_workshop_from_linking_code()へルーティングするprocess_message_event()を新規実装し、
dispatch_webhook_events()のmessage委譲先を差し替えた。新規テスト18件追加、venture全体462件・
schema検証27件いずれもパス。unfollow/postback処理関数は次の課題として残る)

- フェーズ70(2026-09-10 UTC): フェーズ69で次の課題として残した「unfollow/postback処理
  関数」のうちunfollowに着手した。unfollow-billing-faq.md「前提の整理」節の通りブロック中は
  LINEへの返信自体が送達不可であるため返信は行わない`process_unfollow_event()`を新規実装
  した。aircon-pasha等の同名関数と異なり、本ventureのWorkshopStoreProtocol/
  UserProfileStoreProtocolにはis_following相当のフラグ自体が存在せず(blocked-but-billing
  検知〈他venture相当〉の設計もまだ無い、unfollow-billing-faq.md「今後の課題」参照)、
  契約情報(plan_id・subscription_status等)を変更する対象も無いため、本関数はイベント種別
  判定とhandled=Trueを返すのみの受け皿とした(契約情報不変という設計判断自体は他venture3件
  と揃っている)。`dispatch_webhook_events()`に`unfollow_results`を新設し、"unfollow"種別は
  返信・外部ストア依存が無いためmessage/followと異なり依存関係の有無を問わず常に処理する
  ようにした(従来の`ignored_types`記録対象から除外)。新規テスト7件追加、venture全体462件
  →469件全件・schema検証27件いずれもパスを確認した。postback(有料プラン開始ボタン押下の
  処理関数)は未着手のため引き続き次の課題として残す。承認不要なプロトタイプコード実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。

最終更新: 2026-09-10 UTC(フェーズ70: ブロック時のLINE送達不可を踏まえhandled=Trueを返す
のみの受け皿としてprocess_unfollow_event()を新規実装し、dispatch_webhook_events()に
unfollow_results経路を新設した(依存ストア無しで常に処理)。新規テスト7件追加、
venture全体469件・schema検証27件いずれもパス。postback処理関数は次の課題として残る)

- フェーズ71(2026-09-10 UTC): フェーズ70で次の課題として残した「postback(有料プラン開始
  ボタン押下の処理関数)」に着手した。trial-end-notification-design.md(フェーズ59・61・62)が
  確定・実装済みの「▼ 有料プランへ進む」ボタン(postback_data=`START_CHECKOUT_POSTBACK_DATA`)
  がタップされた際の入口として`process_postback_event()`を新規実装した
  (checkout-initiation-flow-design.md 5節、フェーズ50・3節「Checkout Session作成
  エンドポイント(設計)」手順2〜7の実装、aircon-pashaの同名関数と同じ骨格)。
  `event["postback"]["data"]`を既存の`parse_start_checkout_postback_data()`(フェーズ61)で
  解釈し、start_checkout系以外はhandled=Falseで素通り、未連携user_idはLINKING_REQUIRED_
  MESSAGE、契約者本人以外はCONTRACTOR_ONLY_CHECKOUT_NOTICE(本フェーズ新設)、既に
  `subscription_status="active"`の場合はALREADY_SUBSCRIBED_NOTICE(本フェーズ新設)を
  それぞれ返し打ち切る。いずれにも該当しない場合のみ、既存の`build_checkout_session_params()`
  (フェーズ50)と新設の`CheckoutSessionClient`Protocol・`InMemoryCheckoutSessionClient`
  (aircon-pashaと同じ抽象化)でCheckout SessionのURLを取得し返信する。
  `dispatch_webhook_events()`に`postback_results`を新設し、"postback"種別は`reply_client`・
  `user_profile_store`・`workshop_store`・`checkout_session_client`の4つ全てが接続されている
  場合のみ処理し、いずれか未接続時は他の種別(message/follow)と同じく`ignored_types`に
  記録する安全側フォールバックとした。aircon-pashaが持つ`action=update_payment_method`
  (Stripe Billing Portal起動用の別postbackアクション)は、本ventureにはPortalLinkProviderが
  通知本文へURLを差し込まない設計(payment-failure-dunning-design.md「1. 前提」)ゆえ対応する
  ボタン自体の設計が存在しないため対象外とし、次の課題にも含めなかった(unfollow-billing-
  faq.mdにも同種の記述なし)。意図検知(LINEメッセージで「有料プランを始めたい」と伝える経路、
  checkout-initiation-flow-design.md 2節(b)・厳守事項7b)側からの実際のCheckout Session発行
  (`handle_checkout_intent`のmessage event側配線)は本フェーズの対象外とし、引き続き次の
  課題として残す。新規テスト38件追加(process_postback_event()単体8件・dispatch_webhook_
  events()の振り分け/フォールバック5件・receive_webhook()の疎通確認1件、計14関数)、
  venture全体469件→507件全件(`test_checkout_session.py`24件・`test_cloud_function_
  webhook.py`139件→177件・`test_payment_failure_notification.py`22件・
  `test_stripe_webhook.py`113件・`test_subscription_cancellation_notification.py`28件・
  `test_usage_counter_workshop.py`120件・`test_workshop_linking.py`23件)・schema検証27件
  (変更なし、schema/output.schema.jsonへの変更は本フェーズに含まれないため)いずれもパスを
  確認した。承認不要なプロトタイプコード実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-10 UTC(フェーズ71: トライアル終了通知の「▼ 有料プランへ進む」ボタンが
タップされた際の入口process_postback_event()を新規実装し、dispatch_webhook_events()に
postback_results経路を新設した(4依存すべて接続時のみ処理、未接続時はignored_types)。
契約者本人確認・重複契約防止(CONTRACTOR_ONLY_CHECKOUT_NOTICE/ALREADY_SUBSCRIBED_NOTICE)も
実装。新規テスト38件追加、venture全体507件・schema検証27件いずれもパス。update_payment_
method相当のpostback(本venture未設計のため対象外)・LINEメッセージ意図検知からの
Checkout Session発行配線(handle_checkout_intent)は次の課題として残る)

- フェーズ72(2026-09-10 20:00 UTC): フェーズ71で次の課題として残した「LINEメッセージ意図
  検知からの実際のCheckout Session発行(handle_checkout_intentのmessage event側配線)」に
  着手した(checkout-initiation-flow-design.md 6節)。process_postback_event()が実装して
  いたCheckout Session作成エンドポイント(design 3節手順2〜7)を`resolve_checkout_intent()`
  という共通関数に切り出し、process_postback_event()・process_memo_event()の両方から
  呼び出す構成にリファクタリングした(5節末尾で予告していた通り)。process_memo_event()に
  `checkout_session_client`引数を追加し、LLM出力のstatusが`checkout_intent`(厳守事項7bで
  明確な意図と判定された場合のみ、`pricing_inquiry`・`checkout_intent_unclear`は対象外)
  かつ`checkout_session_client`・`user_profile_store`・`workshop_store`の3つ全てが接続
  されている場合のみ、resolve_checkout_intent()の結果(未連携→LINKING_REQUIRED_MESSAGE、
  非契約者→CONTRACTOR_ONLY_CHECKOUT_NOTICE、重複契約防止→ALREADY_SUBSCRIBED_NOTICE、
  それ以外→実Checkout SessionのURL案内)でLLMの一次応答(checkout_notice.body)を置き換える
  ようにした。3依存いずれか未接続時は従来通りcheckout_notice.bodyをそのまま返す後方互換
  フォールバックとし、process_message_event()・dispatch_webhook_events()にも
  checkout_session_clientの貫通配線を追加した(必須依存には加えず後方互換維持)。新規
  テスト13件追加、venture全体507件→520件全件・schema検証27件いずれもパスを確認した。
  トライアル終了が近づいた際の通知メッセージ内の案内文からの起動(design 2節(a))は本
  venture未設計のまま次の課題として残る。承認不要なプロトタイプコード実装・テスト追加
  のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

最終更新: 2026-09-10 20:00 UTC(フェーズ72: process_postback_event()のCheckout Session
発行ロジックをresolve_checkout_intent()として共通化し、process_memo_event()のstatus=
checkout_intent分岐からも呼び出せるようにした(handle_checkout_intentのmessage event側
配線)。3依存〈checkout_session_client・user_profile_store・workshop_store〉未接続時は
従来通りcheckout_notice.bodyのみを返す後方互換。新規テスト13件追加、venture全体520件・
schema検証27件いずれもパス。トライアル終了接近通知からの起動(design 2節(a))は次の課題
として残る)

- フェーズ73(2026-09-10 21:00 UTC): pricing-plan.md「月間生成回数の上限超過時の挙動」・
  checkout-initiation-flow-design.md 2節(a)にそれぞれ残っていた、月間生成回数の上限接近時
  通知が未設計という課題に着手した。aircon-pasha/limit-approaching-notification-design.md
  (月60〜100回、閾値「残り5回」)をそのまま流用すると本ventureのライトプラン(月3回)には
  閾値自体が成立しないため、本venture固有の低頻度利用(pricing-plan.mdより月3回/8回/20回)
  に合わせて独自にlimit-approaching-notification-design.mdとして再設計した(3プラン共通
  閾値「残り1回」を採用)。`prototype/usage_counter_workshop.py`の
  `check_and_increment_usage()`が既に返す`UsageCheckResult`(count_after_increment・
  monthly_limit・overage_price_jpy)をそのまま入力とする純粋関数
  `format_limit_approaching_notice()`を`prototype/cloud_function_webhook.py`に新設し
  (`format_trial_end_notification_message()`と同じ配置方針)、`process_memo_event()`の
  usage_counter_store連携ブロック(フェーズ64)内で`generation_result.usage`を渡し、
  最終的な返信文の末尾にトライアル終了通知と同様の位置で付記するようにした
  (両者は判定条件が独立しており現行3プランでは同一回で重複しない)。新規テスト15件
  (format_limit_approaching_notice()単体5関数・process_memo_event統合1関数〈4回連続生成で
  2回目=残り1回・4回目=超過を確認〉、check()単位で計15件)追加、venture全体520件→535件
  全件・schema検証27件いずれもパスを確認した。トライアル
  期間中の仮plan_idに基づく本通知の文言精度(design 5節)は次の課題として残る。承認不要な
  設計文書作成・プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-10 21:00 UTC(フェーズ73: 月間生成回数の上限接近時通知を
limit-approaching-notification-design.mdとして設計〈3プラン共通閾値「残り1回」〉、
format_limit_approaching_notice()を新設しprocess_memo_event()の返信文末尾に配線した。
新規テスト15件追加、venture全体535件・schema検証27件いずれもパス。トライアル期間中の
文言精度は次の課題として残る)

- フェーズ74(2026-09-10 22:00 UTC): フェーズ73がlimit-approaching-notification-design.md 5節に
  残していた「トライアル期間中(有償契約が未確定な状態)でも「残り1回」通知が届くケースが
  あり、文言中の「上限到達後は追加料金」という表現がトライアル中のユーザーには正確でない」
  という課題に着手した。トライアル中かどうかの判定には新しい状態フラグを追加せず、
  `process_generation_request()`が`TrialPeriodOverError`送出可否の判定に既に使っている
  `workshop_store.get_subscription_status(workshop_id) != "active"`という既存の判定式を
  そのまま流用した(craftsman-account-linking-design.md 7節「workshop作成時は最安プラン
  `"light"`で仮設定」の通り、`subscription_status`はCheckout完了までデフォルト値
  `"trialing"`のままである)。`format_limit_approaching_notice()`に`is_trial: bool`引数を
  新設し、`is_trial=True`の場合は単価(`overage_price_jpy`)に一切触れず「トライアル終了後は
  有料プランへのお申し込みが必要です」という文言に差し替え、`is_trial=False`
  (`subscription_status=="active"`)の場合は従来通り「上限到達後は追加料金[単価]円」の
  文言を返す2分岐とした(design.md 6節として追記、5節の該当課題は取り消し線で完了扱いに
  更新)。`process_memo_event()`側は`generation_result.usage.workshop_id`から
  `workshop_store.get_subscription_status()`を呼んで`is_trial`を求め、
  `format_limit_approaching_notice()`へ渡すよう配線した(追加の外部呼び出しは発生しない、
  同一リクエスト内で`process_generation_request()`が既にworkshop_storeへアクセス済みの
  ため)。トライアル終了通知(`TRIAL_END_QUICK_REPLY`)を本通知にも添付する(「▼ 有料プラン
  へ進む」ボタンを本通知からも押せるようにする)ことは、`process_memo_event()`の
  quick_reply選択ロジック自体の拡張が必要になり本フェーズ(文言の出し分けのみ)のスコープを
  超えるため対象外とし、次の課題として残した。新規テスト17件(`format_limit_approaching_
  notice()`のトライアル文言単体4関数・`process_memo_event()`統合1関数〈ライトプランで
  4回連続生成し、`subscription_status`をactiveへ更新せず既定値`"trialing"`のまま2回目
  =残り1回・4回目=上限超過いずれもトライアル文言になることを確認〉、check()単位で計17件)
  追加、venture全体535件→552件全件(`test_checkout_session.py`24件・
  `test_cloud_function_webhook.py`205件→222件・`test_payment_failure_notification.py`
  22件・`test_stripe_webhook.py`113件・`test_subscription_cancellation_notification.py`
  28件・`test_usage_counter_workshop.py`120件・`test_workshop_linking.py`23件)・
  schema検証27件(変更なし、schema/output.schema.jsonへの変更は本フェーズに含まれないため)
  いずれもパスを確認した。承認不要な設計文書更新・プロトタイプコード実装・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

最終更新: 2026-09-10 22:00 UTC(フェーズ74: limit-approaching-notification-design.md 5節の
課題だったトライアル中の文言不正確さに対応し6節として追記。format_limit_approaching_
notice()にis_trial引数を新設し、workshop_store.get_subscription_status()!="active"を
判定式に流用して「上限到達後は追加料金」ではなく「トライアル終了後は有料プランへの
お申し込みが必要」という文言に差し替えた(process_memo_event()側の配線も追加)。
新規テスト17件追加、venture全体552件・schema検証27件いずれもパス。トライアル終了通知
ボタンの本通知への添付は次の課題として残る)

- フェーズ75(2026-09-11 00:00 UTC): フェーズ74がlimit-approaching-notification-design.md
  6節末尾に残していた「トライアル終了通知ボタン(TRIAL_END_QUICK_REPLY)を本通知(「残り1回」
  /上限超過)にも添付する」課題に着手した。`process_memo_event()`が`limit_notice`を
  `is_trial=True`で組み立てた場合(トライアル期間中、有償契約未確定)のみ、5.のトライアル
  終了通知(生涯最初の生成1回目)と同じ`TRIAL_END_QUICK_REPLY`を返信のquick_replyとして
  併せて添付するようにした。`is_trial=False`(既に有償契約済みで従量課金が発生するケース)は
  「有料プランへ進む」ボタンが文脈上不自然(既に契約済み)なため対象外とした
  (design.md 7節)。両条件(生涯最初の生成1回目/「残り1回」到達時)は判定タイミングが
  独立しており現行3プランでは同一回で重複しないため、単純なor条件で足りる。
  `MemoProcessResult`に新規フィールド`limit_notice_cta_attached`を追加し、本条件による
  ボタン添付の有無を`trial_end_notification_sent`と独立して追跡できるようにした。
  新規テスト2件(トライアル中の「残り1回」/上限超過時にボタンが添付されることを確認する
  統合テスト1件〈既存のtest_process_memo_event_appends_trial_wording_when_subscription_
  not_activeへのアサーション追加を含む〉、既に有償契約済みの場合はボタンを添付しない
  ことを確認する統合テスト1件)追加、venture全体552件→563件全件
  (`test_checkout_session.py`24件・`test_cloud_function_webhook.py`222件→233件・
  `test_payment_failure_notification.py`22件・`test_stripe_webhook.py`113件・
  `test_subscription_cancellation_notification.py`28件・`test_usage_counter_workshop.py`
  120件・`test_workshop_linking.py`23件)・schema検証27件(変更なし)いずれもパスを
  確認した。トライアル中の仮plan_idに基づく通知文言・ボタン導線と、実際にCheckout完了後に
  選ばれたプランとの整合性(design.md 7節「範囲外」)は次の課題として残る。承認不要な
  設計文書更新・プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-11 00:00 UTC(フェーズ75: limit-approaching-notification-design.md 6節末尾の
課題だったトライアル中の本通知へのCTAボタン添付に対応。is_trial=Trueの場合のみ
TRIAL_END_QUICK_REPLYを添付するようにし、MemoProcessResult.limit_notice_cta_attachedを
新設した〈7節〉。新規テスト追加、venture全体563件・schema検証27件いずれもパス。トライアル中の
仮plan_idと実際の契約プランとの整合性は次の課題として残る)

- フェーズ76(2026-09-11 01:00 UTC): フェーズ75が7節に残していた「トライアル期間中の仮plan_id
  に基づく通知文言・ボタン導線と実際の契約プランとの整合性」を調査した結果、それ以前に
  6〜7節の`is_trial=True`分岐(「残り1回」/上限超過の文言・CTAボタン添付)自体が、実際に
  オンボーディングされたworkshopでは到達不能であることを発見した。`pricing-plan.md`の
  無料トライアルは「生涯最初の1回無料」であり、`is_trial_period_over()`は
  `trial_generation_used`が真になった時点(=1回目の生成成功直後)で即座に`True`を返す。
  `process_generation_request()`はこの判定を`check_and_increment_usage()`(6節の
  「残り1回」判定の入力元)より先に行うため、2回目の生成リクエストは常に
  `TrialPeriodOverError`(→`TRIAL_PERIOD_OVER_NOTICE`)で遮断され、6〜7節が想定した
  「2回目=残り1回・4回目=上限超過」という状態には至らない。フェーズ74・75のテストが
  この矛盾に気付かなかったのは、テストが`workshop_store.set_trial_start_at()`を呼ばずに
  workshopを用意していたため(`is_trial_period_over()`が恒久的に`False`のまま)であることも
  特定した。実際のオンボーディング経路(`workshop_linking.create_workshop_from_linking_
  code()`)を通した場合に2回目で遮断されることを実証する新規テスト1件
  (`test_process_memo_event_trial_limit_notice_is_unreachable_for_real_onboarded_
  workshop`)を追加し、design.mdに8節として発見内容を記録した。6〜7節のコード自体の削除・
  トライアル条件(生涯1回無料)の再設計はどちらもpricing-plan.mdに関わる製品判断のため
  本フェーズでは行わず、オーナー判断待ちの次の課題として残した(到達不能なだけで誤った
  文言が実際に送信されるわけではないため緊急度は低いと判断)。新規テスト6件(check()単位)
  追加、venture全体563件→569件全件(test_checkout_session.py 24件・
  test_cloud_function_webhook.py 233件→239件・test_payment_failure_notification.py
  22件・test_stripe_webhook.py 113件・test_subscription_cancellation_notification.py
  28件・test_usage_counter_workshop.py 120件・test_workshop_linking.py 23件)・
  schema検証27件いずれもパスを確認した。承認不要な設計文書更新・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

最終更新: 2026-09-11 01:00 UTC(フェーズ76: limit-approaching-notification-design.md 6〜7節の
is_trial=True分岐〈「残り1回」/上限超過通知・CTAボタン〉が、実際のオンボーディング経路では
生涯最初の1回の生成後に必ずTrialPeriodOverErrorで遮断されるため到達不能であることを発見し、
実際の経路を通した新規テストで実証した〈8節〉。コード自体の削除・トライアル条件の再設計は
製品判断のためオーナー判断待ちの次の課題として残す。新規テスト追加、venture全体569件・
schema検証27件いずれもパス)

- フェーズ77(2026-09-11 02:00 UTC): stripe-webhook-checkout-completed-design.md
  「4. 未検証・残課題」最後の項目に残っていた「イベントID(`event.id`)による
  べき等性チェックは、本ventureでは`checkout.session.completed`が複数回届いても実害が
  無いため当面省略した。将来`invoice.payment_failed`等の非べき等な通知処理を追加する際に
  改めて必要性を検討する」に着手した。`invoice.payment_failed`(フェーズ56)・
  `customer.subscription.deleted`(フェーズ53)・`customer.subscription.updated`
  (フェーズ55)がいずれも実装済みとなった現時点で条件が揃ったと判断し、まず
  各ハンドラの現状を棚卸しした結果、`handle_invoice_payment_failed()`が同一イベントの
  再配信のたびに`payment_failure_detected_at`を新しいタイムスタンプで上書きし
  (猶予期間の起算点が際限なく後ろへずれる)、かつ決済失敗検知のLINE通知を毎回再送する
  という、他の3ハンドラより実害の大きい非べき等性を持つことを確認した(`customer.
  subscription.deleted`の解約完了通知・`customer.subscription.updated`の解約予約
  受理/取り消し通知も同様に再送されるが、状態変更を一切伴わないため実害の性質は同じ)。
  aircon-pashaのstripe-event-idempotency-design.md(フェーズ177)の設計・実装
  (`StripeEventIdStoreProtocol`・`InMemoryStripeEventIdStore`、エントリポイント層
  〈`receive_stripe_webhook()`〉での一括判定)を本ventureへ翻案し、新設した
  stripe-event-idempotency-design.mdとして記録した。翻案にあたり、本venture固有の
  追加判断として「ハンドラ結果が`invalid`(400、`customer`欠落等の不正なイベント)の
  場合は処理済みとして記録しない」ルールを設けた(処理済みにしてしまうとStripe側の
  本物の不具合が2回目以降400を返さなくなり、Stripeダッシュボード上のエラー可視性が
  失われるため)。`unresolved`(逆引き失敗、200)はアプリケーション側では正常な結果
  であるため処理済みとして記録する。`event.id`が欠落・非文字列の場合は従来通り
  チェックをスキップする(安全側)。`event_id_store`は新規キーワード引数(既定`None`)
  とし省略時は従来通りべき等性チェックを行わない(既存呼び出し経路への後方互換)。
  新規テスト12関数・check()単位で19件(`invoice.payment_failed`の重複配信で
  `payment_failure_detected_at`が上書きされず通知も再送されないことを確認する
  回帰テストを含む)追加、venture全体569件→588件全件(test_checkout_session.py 24件・
  test_cloud_function_webhook.py 239件・test_payment_failure_notification.py 22件・
  test_stripe_webhook.py 113件→132件・test_subscription_cancellation_notification.py
  28件・test_usage_counter_workshop.py 120件・test_workshop_linking.py 23件)・
  schema検証27件(変更なし、schema/output.schema.jsonへの変更は本フェーズに含まれない
  ため)いずれもパスを確認した。承認不要な設計文書作成・プロトタイプコード実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。

最終更新: 2026-09-11 02:00 UTC(フェーズ77: stripe-webhook-checkout-completed-design.md
「4. 未検証・残課題」に残っていたevent.idべき等性チェックを実装。aircon-pashaフェーズ177の
設計を翻案し`StripeEventIdStoreProtocol`・`InMemoryStripeEventIdStore`を新設、
`receive_stripe_webhook()`のエントリポイント層で一括判定する方式とした(新設
stripe-event-idempotency-design.md)。特に`invoice.payment_failed`の再配信時に猶予期間の
起算点が後ろへずれ続け通知も二重送信される実害を解消した。新規テスト19件追加、
venture全体569件→588件全件・schema検証27件いずれもパス)

- フェーズ78(2026-09-11 03:00 UTC): checkout-initiation-flow-design.md(フェーズ50)2節(a)・
  「残る課題」に残っていた「トライアル終了が近づいた際の通知メッセージ内の案内文からの
  起動(aircon-pasha/limit-approaching-notification-design.md相当)は本venture未設計」と
  いう記載が、実際にはtrial-end-notification-design.md(フェーズ61・62)・
  limit-approaching-notification-design.md(フェーズ73・75)でいずれも設計・実装済みだった
  にもかかわらず訂正されていなかった記載漏れを発見した。`TRIAL_END_QUICK_REPLY`
  (postback_data=`START_CHECKOUT_POSTBACK_DATA`)が両通知に添付され、押下時は
  `resolve_checkout_intent()`(フェーズ72で共通化)へ配線済みであることをコードで確認した
  うえで、両箇所を解消済みとして訂正した。あわせて、limit-approaching側はフェーズ76の
  調査で「生涯最初の1回のみ無料」というトライアル条件により実際のオンボーディング経路
  では到達不能であることが判明済みである旨も参照として書き添えた(コード削除・トライアル
  条件の再設計はpricing-plan.mdに関わる製品判断のため、引き続きオーナー判断待ちの別課題)。
  コード変更は無く、venture全体588件全件(test_checkout_session.py 24件・
  test_cloud_function_webhook.py 239件・test_payment_failure_notification.py 22件・
  test_stripe_webhook.py 132件・test_subscription_cancellation_notification.py 28件・
  test_usage_counter_workshop.py 120件・test_workshop_linking.py 23件)・schema検証27件
  いずれもパス(変更前と同じ結果)を確認した。承認不要なドキュメント整合性修正のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

最終更新: 2026-09-11 03:00 UTC(フェーズ78: checkout-initiation-flow-design.md 2節(a)・
「残る課題」に残っていた「トライアル終了通知からの決済導線起動は本venture未設計」という
記載漏れを発見・訂正した。実際にはフェーズ61・62・73・75でいずれも実装済みであることを
コードで確認した。コード変更なし、venture全体588件・schema検証27件いずれもパス
〈変更前と同じ〉)

- フェーズ79(2026-09-11 04:00 UTC): 「次にやること(候補)」節(フェーズ54時点で
  作成、以後未更新のまま放置されていた)を棚卸しした結果、記載されていた8項目の
  うち5項目(`invoice.payment_failed`/`payment_succeeded`対応〈フェーズ56〉、
  `customer.subscription.updated`のcancel_at_period_end対応〈フェーズ55〉、
  有料プラン開始の意図検知〈フェーズ72〉、`trial_start_at`のworkshop作成時書き込み
  〈craftsman-account-linking-design.md実装時に対応済み〉)が既に解消済みで
  記載が古いままだったことを確認し、同節を現時点の残課題(blocked-but-billing検知の
  未設計〈フェーズ70で判明〉・実LINE公式アカウント接続/実LLM検証/実Push配線は
  オーナー承認待ち・トライアル条件の再設計はpricing-plan.mdに関わる製品判断のため
  オーナー判断待ち〈フェーズ76〉)に更新した。あわせて棚卸しの過程で、
  interview-candidate-selection-criteria.md・interview-rehearsal-script.md・
  initial-contact-message-draft.md(フェーズ7〜16、2026-09-06 10:00〜23:00 UTC)で
  想定顧客ヒアリング(ライディングショップ池上・エクウスワールド)の候補選定・文面草案
  作成まで完了させていたにもかかわらず、他venture(line-reservation-ai・course-set-pasha・
  aircon-pasha)では毎回行っていた「実際の連絡はオーナー許可が必要なためpending-approval.md
  に記録する」という手順自体が本ventureでは一度も実行されていなかった記載漏れを発見した。
  各フェーズの文面には「着手する場合は別途pending-approval.mdへの記録・オーナー承認が
  必要」との記載こそあったが、実際にpending-approval.mdへ記録する作業が漏れていたもの。
  本フェーズでpending-approval.mdに新規エントリを追加して解消した。コード変更は無く、
  venture全体588件(test_checkout_session.py 24件・test_cloud_function_webhook.py 239件・
  test_payment_failure_notification.py 22件・test_stripe_webhook.py 132件・
  test_subscription_cancellation_notification.py 28件・test_usage_counter_workshop.py 120件・
  test_workshop_linking.py 23件)・schema検証27件いずれもパス(変更前と同じ結果)を確認した。
  承認不要なドキュメント整合性修正・pending-approval.md記載のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないため、これ以外のpending-approval.mdへの
  追記なし。

最終更新: 2026-09-11 04:00 UTC(フェーズ79: フェーズ54作成のまま未更新だった
「次にやること(候補)」節を現状に合わせて更新〈5項目が既に解消済みと判明〉。
あわせて、フェーズ7〜16で完了させていた想定顧客ヒアリング候補選定・文面草案について
pending-approval.mdへの記録が一度も行われていなかった記載漏れを発見・解消した。
コード変更なし、venture全体588件・schema検証27件いずれもパス〈変更前と同じ〉)

- フェーズ80(2026-09-11 05:00 UTC): unfollow-billing-faq.md「今後の課題」に残っていた
  「『ブロック中かつ契約継続中』契約者の検知手段(他venture3件のblocked-but-billing-
  detection-design.md相当)は本venture未着手」に対応した。前提だったStripe Webhook受信は
  既に実装済みだったため、残る前提の`user_profile.is_following`フィールド追加とあわせて
  着手し、blocked-but-billing-detection-design.mdとして設計・実装した。本venture固有の
  workshop(工房)構造(契約単位=workshop、フォロー状態はuser_id単位)を踏まえ、課金関連
  通知が一貫して契約者(`contractor_user_id`)のみを宛先とする既存方針(design 1節)から、
  検知対象も契約者本人の`is_following`に限定する設計とした。「契約継続中」の判定は、
  本ventureの`plan_id`が解約後もクリアされない(aircon-pasha等の`current_plan_id`とは
  異なる)ため`subscription_status != "canceled"`を用いる翻案を行った(design 3節)。
  `prototype/blocked_but_billing_candidates.py`(`list_blocked_but_billing_candidates()`)を
  新規実装し、`process_follow_event()`/`process_unfollow_event()`への`is_following`
  更新配線・`dispatch_webhook_events()`からの`user_profile_store`結線もあわせて行った。
  新規テスト15件(候補洗い出しロジック7件・follow/unfollow配線8件)を追加し、
  venture全体588件→603件全件(`python3 test_*.py`を各ファイルで直接実行)・schema検証
  27件いずれもパスを確認した。あわせてunfollow-billing-faq.md該当箇所を解消済みに更新した。
  承認不要な設計・コード追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。オーナーへ実際に候補一覧を届ける
  通知手段(aircon-pasha/blocked-but-billing-owner-notification-design.md相当)は次回以降の
  課題として残る。

最終更新: 2026-09-11 05:00 UTC(フェーズ80: unfollow-billing-faq.md「今後の課題」に
残っていた「ブロック中かつ契約継続中」契約者の検知手段の未着手をblocked-but-billing-
detection-design.mdとして解消。`user_profile.is_following`追加・
`prototype/blocked_but_billing_candidates.py`新規実装・follow/unfollowイベントへの配線を
行った。新規テスト15件追加、venture全体588件→603件・schema検証27件いずれもパス)

- フェーズ81(2026-09-11 06:00 UTC): blocked-but-billing-detection-design.md(フェーズ80)
  「5. 未着手のまま残る課題」に残っていた「候補一覧を実際にオーナーへ届ける手段
  (aircon-pasha/blocked-but-billing-owner-notification-design.md相当)は本フェーズの対象外」
  に対応した。aircon-pasha版はFlex Message専用クライアント向けの設計だったが、本ventureの
  `LinePushClient`(subscription_cancellation_notification.py)はcourse-set-pasha方式と同じ
  プレーンテキストの`send_message()`のみを提供するため、blocked-but-billing-owner-
  notification-design.mdとして本venture向けに翻案した設計書を新規作成した。候補一覧は
  workshop_id単位(aircon-pasha等のuser_id単位とは異なる)のため、通知フィールド
  `blocked_but_billing_owner_notified_at`は`user_profile`ではなく`craftsman_workshop`
  (`WorkshopStoreProtocol`)側に新設し、送信文言には`get_contractor_user_id()`で解決した
  契約者user_idを差し込む設計とした。`prototype/blocked_but_billing_owner_notification.py`
  (新規)に`select_new_blocked_but_billing_candidates_for_notification()`・
  `build_blocked_but_billing_owner_notification_message()`・
  `send_blocked_but_billing_owner_notifications()`・
  `clear_blocked_but_billing_owner_notified_at()`を実装し、`cloud_function_webhook.
  process_follow_event()`(新規引数`workshop_store`、再フォロー時のクリア)・
  `stripe_webhook.handle_customer_subscription_deleted()`(解約確定時のクリア、
  `set_subscription_status`成功時に常時呼び出し)の両方に配線した(aircon-pashaがフェーズ
  174→175の2段階で行ったクリア配線を本venture側は1フェーズにまとめて実装)。
  `dispatch_webhook_events()`のfollowイベント処理からも`workshop_store`を新たに配線した。
  新規テスト21件(新規ファイルtest_blocked_but_billing_owner_notification.py 14件・
  process_follow_event経由のクリア2件・dispatch_webhook_events経由のクリア配線1件・
  handle_customer_subscription_deleted経由のクリア2件、うち一部は既存分類に計上)を追加し、
  venture全体603件→624件全件・schema検証27件いずれもパスを確認した。あわせて
  blocked-but-billing-detection-design.md「5. 未着手のまま残る課題」・
  unfollow-billing-faq.md「今後の課題」の該当箇所を解消済みに更新した。承認不要な設計文書
  作成・プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-11 06:00 UTC(フェーズ81: blocked-but-billing-detection-design.mdに
残っていた「オーナーへの候補通知手段は未設計」をblocked-but-billing-owner-notification-
design.mdとして解消。本venture一貫のプレーンテキスト送信へ翻案し、
`prototype/blocked_but_billing_owner_notification.py`新規実装・再フォロー/解約確定時の
クリア配線まで実装した。新規テスト21件追加、venture全体603件→624件・schema検証27件
いずれもパス)

- フェーズ82(2026-09-11 07:00 UTC): subscription-cancellation-notification-design.md
  (フェーズ54)「5. 残課題」に残っていた「`customer.subscription.updated`の
  `cancel_at_period_end`前後比較による解約予約受理・解約取り消し案内は本venture未着手」
  という記載が、実際には直後のフェーズ55(subscription-cancellation-scheduled-
  notification-design.md、`handle_customer_subscription_updated()`実装・
  `receive_stripe_webhook()`へのディスパッチ配線)で既に解消されていたにもかかわらず
  訂正されていなかった記載漏れであることを発見した。`prototype/stripe_webhook.py`に
  `handle_customer_subscription_updated()`が実装済みで`receive_stripe_webhook()`が
  `"customer.subscription.updated"`を受理・ディスパッチしていることをコードで確認した
  うえで、該当箇所を解消済みに訂正した。あわせて「次にやること(候補)」節の
  blocked-but-billing系2項目(フェーズ80・81で完了済み)を解消済みとして整理した。
  コード変更は無く、venture全体624件・schema検証27件いずれもパス(変更前と同じ結果)を
  確認した。承認不要なドキュメント整合性修正のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-11 07:00 UTC(フェーズ82: subscription-cancellation-notification-
design.md「5. 残課題」に残っていた`customer.subscription.updated`対応の記載漏れ
〈フェーズ55で解消済みだったが訂正されていなかった〉を訂正。あわせて「次にやること
(候補)」節のblocked-but-billing系2項目を解消済みに整理した。コード変更なし、
venture全体624件・schema検証27件いずれもパス〈変更前と同じ〉)

- フェーズ83(2026-09-11 08:00 UTC): aircon-pasha/character-limit-fallback-design.md
  (フェーズ102)相当の設計が本ventureに存在しないcross-venture parityのギャップに気付き、
  character-limit-fallback-design.mdとして本venture向けに翻案・実装した。本ventureは
  出力1(受注内容整理メモ)・出力2(納品案内下書き)・出力3(お手入れ案内下書き)を
  `format_generated_reply()`で1通のテキストメッセージに連結して返信する設計
  (aircon-pashaが`completion_report`/`care_guide`をそれぞれ独立に文字数チェックするのとは
  異なる)であるため、チェック対象を連結後の1本のテキスト全体とする翻案を行った。
  `count_utf16_code_units()`(LINE Messaging APIの文字数上限がUTF-16コード単位でカウント
  される点に対応)・`check_message_length_within_line_limit()`
  (`LINE_TEXT_MESSAGE_MAX_LENGTH = 5000`)を新設し、`process_memo_event()`の
  `status == "generated"`かつ連結後テキストが上限超過の場合、`limit_notice`・
  トライアル終了通知の付記を行わず(既存の`LlmApiError`・検証エラー時フォールバックと
  同じ扱い)`CHARACTER_LIMIT_FALLBACK_MESSAGE`を職人向けに返す分岐を追加した。切り詰めは
  行わず送信失敗(生成失敗)として扱う方針もaircon-pasha版を踏襲した。`MemoProcessResult`に
  `character_limit_exceeded`フィールドを新設した。新規テスト4件(UTF-16コード単位カウント・
  境界値・上限超過時フォールバック・limit_notice/トライアル終了通知の非付記)を追加し、
  venture全体624件→638件全件・schema検証27件いずれもパスを確認した。承認不要な設計文書
  作成・プロトタイプコード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-11 08:00 UTC(フェーズ83: aircon-pasha/character-limit-fallback-
design.md相当の設計が本ventureに無かったcross-venture parityのギャップに対応し、
character-limit-fallback-design.mdとして新規作成・実装した。3出力を1通に連結する本venture
固有の構造に合わせ、連結後テキスト全体をUTF-16コード単位でチェックする設計とした。
新規テスト4件追加、venture全体624件→638件・schema検証27件いずれもパス)

- フェーズ84(2026-09-11 10:00 UTC): 他venture(line-reservation-ai・course-set-pasha・
  aircon-pasha)には既にあるが本venture未着手だったunit-economics-estimate.md
  (決済手数料・Firestore原価・LLM API原価を統合した1工房あたり月次粗利試算)という
  cross-venture parityのギャップに対応し、新規作成した。決済手数料3.6%・Firestore原価
  0円(他venture以上に低頻度のため無料枠内と判断)の前提を他ventureから踏襲し、
  llm-api-cost-estimate.md(フェーズ6)のSonnet 5・シナリオB試算(キャッシュなし
  5.09円/回・キャッシュ利用2.27円/回)と組み合わせて3プランの粗利率を試算した結果、
  93.8〜95.7%(含まれる回数を使い切った場合)と他venture以上の水準であることを確認した。
  pricing-plan.mdが従量単価・基本料を原価積み上げでなく顧客の受注単価との比較で
  高めに仮決めしたことが主因である点、含まれる回数を使い切らない月が多いほど実際には
  粗利率がさらに高くなる方向に働く可能性がある点(aircon-pashaの季節変動シミュレーション
  と同じ方向性)を結論として記録した。コード変更は無く、venture全体638件・schema検証
  27件いずれもパス(変更前と同じ結果)を確認した。承認不要な設計文書作成のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

最終更新: 2026-09-11 10:00 UTC(フェーズ84: 他venture〈line-reservation-ai・
course-set-pasha・aircon-pasha〉には既にあるが本venture未着手だったunit-economics-
estimate.mdを新規作成し、決済手数料・Firestore原価・LLM API原価を統合した1工房あたり
月次粗利試算〈93.8〜95.7%〉を行った。コード変更なし、venture全体638件・schema検証
27件いずれもパス〈変更前と同じ〉)

- フェーズ85(2026-09-11 11:00 UTC): 他venture(aircon-pasha・course-set-pasha)には
  既にあるが本venture未着手だったapi-call-failure-handling.mdというcross-venture
  parityのギャップに気付き調査したところ、`LlmApiError`・`ReplyApiError`・
  `_generate_with_api_retry()`・`_reply_with_retry()`・`API_FAILURE_FALLBACK_MESSAGE`・
  `MemoProcessResult.api_failure`はいずれも`prototype/cloud_function_webhook.py`に
  既に実装済みだったにもかかわらず、これを文書化した設計書が存在しない記載漏れで
  あることが判明した。api-call-failure-handling.mdとして本venture向けに新規文書化する
  とともに、テストカバレッジを点検した結果、他venture相当の4パターン(LLM API失敗→
  リトライ成功/リトライも失敗、Reply API失敗→リトライ成功/リトライも失敗)のうち
  「LLM API連続失敗→フォールバック」の1パターンしか検証されておらず、残り3パターンが
  未検証だったことを発見した。`_FlakyOnceLlmCall`・`_FlakyOnceReplyClient`・
  `_AlwaysFailingReplyClient`スタブを新規追加し、残り3パターン(LLM APIリトライ成功、
  Reply APIリトライ成功、Reply API連続失敗時にreply_sent=Falseで例外を投げず諦める)を
  検証する新規テスト11件(check()呼び出し単位)を追加した。`test_cloud_function_
  webhook.py`は265件→276件全件・venture全体638件→649件・schema検証27件いずれも
  パスを確認した。コード自体の変更は無く(既存実装の文書化・テスト追加のみ)、承認
  不要な設計文書作成・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-11 11:00 UTC(フェーズ85: 他venture〈aircon-pasha・course-set-pasha〉
には既にあるが本venture未着手だったapi-call-failure-handling.mdの記載漏れに対応。
実装は既に完了済みだったことを確認したうえで新規文書化し、未検証だった3パターン
(LLM API/Reply APIのリトライ成功・Reply API連続失敗時のフォールバック)を検証する
新規テスト11件を追加した。venture全体638件→649件・schema検証27件いずれもパス)

- フェーズ86(2026-09-11 16:00 UTC): 他venture(aircon-pasha・course-set-pasha・
  line-reservation-ai)には既にあるが本venture未着手だったtone-and-manner-
  guideline.mdというcross-venture parityのギャップに対応し、新規作成した。作成の過程で
  `prototype/*.py`内の運用メッセージ見出しを全数確認したところ、course-set-pashaフェーズ
  203が発見したのと同種の不整合が1箇所見つかった。`cloud_function_webhook.
  format_trial_end_notification_message()`のみ半角「[鞍パシャッと] 」を使用しており、
  他の全メッセージ(`payment_failure_notification.py`・`subscription_cancellation_
  notification.py`・`blocked_but_billing_owner_notification.py`)が使う全角
  「【鞍パシャッと】」と表記が分裂していたため、全角に統一する修正を行った。あわせて
  `blocked_but_billing_owner_notification.py`の見出し「【鞍パシャッと運営】」は職人向けと
  運営(オーナー)向けを区別する意図的な設計(design.md 3節で確認)であり修正対象では
  ないことをガイドラインに明記した。この文言をハードコードで検証するテストは無く、
  `prototype/`配下の単体テスト9ファイル合計649件全件・schema検証27件いずれも変更前と
  同じ結果でパスすることを確認した。承認不要な設計文書作成・既存コードの表記統一修正の
  みで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。

最終更新: 2026-09-11 16:00 UTC(フェーズ86: 他venture〈aircon-pasha・course-set-pasha・
line-reservation-ai〉には既にあるが本venture未着手だったtone-and-manner-guideline.mdを
新規作成。作成過程で発見した見出し表記の不整合(トライアル終了通知のみ半角「[鞍パシャッと]」)
を全角「【鞍パシャッと】」に統一する修正を行った。venture全体649件・schema検証27件いずれも
パス〈変更前と同じ〉)

- フェーズ87(2026-09-11 20:00 UTC): 他venture(aircon-pasha・course-set-pasha・
  line-reservation-ai)には既にあるが本venture未着手だったlanding-page-wireframe.mdという
  cross-venture parityのギャップに対応し、新規作成した。landing-page-copy-draft.mdの
  セクション順・CTA文言(30日間無料で試してみる)をそのまま踏襲しつつ、本venture固有の
  「区分(新規制作/修理)によって納品案内下書きの内容が分岐する」という特性を可視化する
  ため、ヒーローセクションのビフォーアフター画像をaircon-pasha(1パターンのみ)とは異なり
  新規制作用・修理用の2パターン(タブ/カルーセル切替)併記する構成とした。実装(HTML/CSS)・
  画像そのものの制作・公開は行わず、テキストベースの画面構成案のみに留めた(他venture
  同様)。コード変更は無く、venture全体(`python3 -m unittest discover -s prototype -p
  "test_*.py"`)・schema検証(`python3 schema/validate_test_cases.py`)27件いずれもパス
  (変更前と同じ結果)を確認した。承認不要な設計文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
  次回は他venture・アイデア領域の前進、または引き続き未走査の設計docの残課題棚卸しを
  優先候補とする。

- フェーズ88(2026-09-12 00:00 UTC): 他venture(aircon-pasha・course-set-pasha・
  line-reservation-ai)には既にあるが本venture未着手だったtech-stack.mdという
  cross-venture parityのギャップに対応し、新規作成した。aircon-pasha/tech-stack.mdの
  構成(全体構成イメージ→想定コンポーネント→MVPスコープ→初期投資・ランニングコストの
  目安→次のステップ候補)を踏襲しつつ、本venture固有の構造(craftsman-account-linking-
  design.md・subscription-billing-data-model-design.md・usage-counter-workshop-key-
  design.mdで確定済みの、課金・回数上限管理が`user_id`単位ではなく
  `craftsman_workshop/{workshop_id}`単位である点、Stripe Webhookの解決先が
  `stripe_customer_id → workshop_id`になる点)を他3ventureとの構造的差異として明記した。
  既存設計文書の内容を集約しただけで新たな設計判断は発生していない。コード変更は無く、
  venture全体649件(`prototype/`配下の単体テスト9ファイルをそれぞれ個別実行、
  test_blocked_but_billing_candidates.py 7件・test_blocked_but_billing_owner_
  notification.py 14件・test_checkout_session.py 24件・test_cloud_function_webhook.py
  276件・test_payment_failure_notification.py 22件・test_stripe_webhook.py 135件・
  test_subscription_cancellation_notification.py 28件・test_usage_counter_workshop.py
  120件・test_workshop_linking.py 23件)・schema検証27件(`python3 schema/
  validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。なお
  `python3 -m unittest discover -s prototype -p "test_*.py"`はモジュールの一部
  (test_blocked_but_billing_candidates・test_blocked_but_billing_owner_notification・
  test_workshop_linkingの3ファイル、計44件)しか収集せず649件との差異があることに
  気付いたが、原因調査(各テストファイルが個別実行前提のスクリプト形式で書かれており
  discover互換のテストランナー統一がされていないためと推測)は本フェーズの範囲外のため
  次の課題として残し、今回の検証は他venture同様「各ファイル個別実行」の方法で行った。
  承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の
  前進、または本フェーズで見つけたdiscover非互換の原因調査を優先候補とする。

- フェーズ89(2026-09-12 04:00 UTC): フェーズ88で見つけた`python3 -m unittest discover`
  非互換の原因調査を行った。`grep -l "unittest.TestCase" test_*.py`で切り分けた結果、
  discoverが収集した3ファイル(test_blocked_but_billing_candidates.py・
  test_blocked_but_billing_owner_notification.py・test_workshop_linking.py)のみが
  `unittest.TestCase`ベースで書かれており、残り6ファイル(test_checkout_session.py・
  test_cloud_function_webhook.py・test_payment_failure_notification.py・
  test_stripe_webhook.py・test_subscription_cancellation_notification.py・
  test_usage_counter_workshop.py)は独自のcheck()/PASS/FAIL関数と
  `if __name__ == "__main__":`直接呼び出しのスクリプト形式であり、TestCaseクラスが
  存在しないためdiscoverの収集対象にならないことを確定した(フェーズ88時点の推測どおり)。
  6ファイルをTestCaseベースへ書き直すのはテスト内容そのものに手を入れる大きな変更に
  なり本フェーズの範囲を超えると判断し、既存ファイルは変更せず、
  `prototype/run_all_tests.py`を新規作成した。各test_*.pyを`python3 <file>`として
  個別プロセス実行し終了コードで合否判定・集約表示する薄いラッパーで、
  discover非互換を回避しつつ9ファイル・649件を一括実行できることを確認した
  (`python3 run_all_tests.py`で9 files run, 9 passed, 0 failed)。
  schema検証(`python3 schema/validate_test_cases.py`)27件も変更前と同じ結果でパス。
  他venture(aircon-pasha・course-set-pasha・line-reservation-ai)にも同じ
  discover非互換が存在する可能性があるため、横展開は次の課題として残す。承認不要な
  調査・新規スクリプト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

- フェーズ90(2026-09-12 08:00 UTC): フェーズ89で「次の課題」として残していた、
  discover非互換が他venture(aircon-pasha・course-set-pasha・line-reservation-ai)にも
  存在するかの横展開確認を行った。3venture全てで`python3 -m unittest discover -s
  prototype -p "test_*.py"`を実行した結果、line-reservation-ai(771件)・
  aircon-pasha(475件)・course-set-pasha(575件)いずれもdiscoverが全テストファイルを
  収集し、従来コミット履歴で報告されてきたテスト総数と一致することを確認した。各venture内の
  全test_*.pyファイルが`unittest.TestCase`を継承していることも`grep`で確認し、
  kura-pashaの6ファイルのような独自check()/PASS/FAIL形式のスクリプトは存在しないことを
  確認した。確認結果をcross-venture-discover-compatibility-review.mdとして新規記録し、
  discover非互換はkura-pasha固有の問題(フェーズ89のrun_all_tests.py新設で対応済み)であり
  他ventureへの横展開は不要と結論した。コード変更は無く、確認のみのため各venture既存の
  テスト・schema検証結果への影響もない。承認不要な調査・設計docレビューのみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないためpending-
  approval.mdへの追記なし。

- フェーズ91(2026-09-12 12:00 UTC): tech-stack.md(フェーズ88)を見直す過程で、同ファイルが
  要約元としていたsubscription-billing-data-model-design.md「4. 未検証・残課題」の
  「Checkout Session発行フロー・Stripe Webhookの署名検証・イベントディスパッチの実装は
  未着手」という記載が、実際にはフェーズ50(checkout-initiation-flow-design.md)・
  フェーズ51(stripe-webhook-checkout-completed-design.md、2026-09-06)で実装済み
  (`prototype/checkout_session.py`・`prototype/stripe_webhook.py`の`verify_stripe_
  signature()`・`receive_stripe_webhook()`)であるにもかかわらず訂正されずに残っていた
  記載漏れであることを発見した。同じ理由で「トライアル条件判定関数は未着手」という記載も
  trial-end-condition-design.md(フェーズ52、`is_trial_period_over`)で既に対応済みだった。
  一方「`current_period_end`フィールドの読み書きメソッド」は実際に`prototype/stripe_
  webhook.py`を確認したところ、Stripeイベントの値をその場で解約予約通知の文面生成に渡す
  のみで永続化用のget/setメソッドは存在せず、こちらは記載どおり引き続き未着手と確認した。
  subscription-billing-data-model-design.md「4.未検証・残課題」・tech-stack.md
  「未検証・残課題」双方を実態に合わせて訂正した。コード変更は無く、venture全体649件
  (`python3 prototype/run_all_tests.py`)・schema検証27件(`python3 schema/
  validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。承認不要な設計
  文書の記載漏れ訂正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回は`current_period_end`の
  読み書きメソッド実装、または他venture・アイデア領域の前進を優先候補とする。

- フェーズ92(2026-09-12 12:58 UTC): フェーズ91で「次にやること」1点目だった
  `current_period_end`フィールドの読み書きメソッド(subscription-billing-data-model-
  design.md「4. 未検証・残課題」)を実装した。`WorkshopStoreProtocol`へ
  `get_current_period_end`/`set_current_period_end`を追加し(`InMemoryWorkshopStore`に
  実装、未設定workshopは他の日時系フィールド〈`trial_start_at`等〉と同じくNoneを返す)、
  `prototype/stripe_webhook.py`の`handle_customer_subscription_updated`を、
  `data_object.get("current_period_end")`(Unixタイムスタンプ)が数値であればUTCの
  `datetime`へ変換して`set_current_period_end`で永続化するよう配線した。従来この値は
  `handle_subscription_cancellation_update`へその場で渡され解約予約通知の文面生成
  (`_format_period_end_date_jst`)に使われるのみで永続化されていなかった(フェーズ91で
  確認済みの記載漏れ)ため、今回で解消した。永続化と解約予約通知の要否判定は独立した
  処理とし、`push_client`未指定(通知を送らない)経路でも永続化自体は行われるよう
  `push_client is None`の早期returnより前に配線した。schema/output.schema.jsonへの
  影響は無い(`current_period_end`はLLM構造化出力にはそもそも登場しないフィールドで
  あることをフェーズ26で確認済み)。新規テスト: test_usage_counter_workshop.pyへ2件
  (デフォルトNone・set/再設定の読み書き)、test_stripe_webhook.pyへ3件相当
  (push_client未指定時の永続化確認1件の既存テスト拡張+新規2件: push_client指定時の
  永続化・current_period_end欠落時は書き込まれないことの確認)を追加し、venture全体
  652件(`python3 prototype/run_all_tests.py`、9 files run, 9 passed)・schema検証27件
  (`python3 schema/validate_test_cases.py`)いずれもパスを確認した。
  subscription-billing-data-model-design.md・tech-stack.mdの該当する残課題記載も
  対応済みへ更新した。実際のStripeアカウント接続・Webhookエンドポイントのデプロイは
  引き続きオーナー承認待ちの範囲(pending-approval.md参照)で、本フェーズでは行って
  いない。承認不要なコード実装・テスト追加・設計文書更新のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記
  なし。次回は他venture・アイデア領域の前進、または本venture未着手のcross-venture
  parityギャップ(他venture既存で本venture未確認のドキュメント種別)の棚卸しを優先
  候補とする。

- フェーズ93(2026-09-12 17:00 UTC): aircon-pashaフェーズ208(course-set-pashaの
  subscription-plan-change-design.mdフェーズ続き154で解消済みの「プラン変更を伴わない
  `customer.subscription.updated`イベントでの無駄な書き込み」と同種のギャップが
  `subscription_plan_sync.py`に残っていた件を解消)が「kura-pasha・line-reservation-ai
  への横展開要否は次回以降の棚卸し候補」と申し送っていたのを受け、本venture側を確認した。
  その結果、aircon-pasha側の対応(差分チェックの追加)より手前の段階、すなわち
  `customer.subscription.updated`受信時にworkshopの`plan_id`を同期する処理自体が
  一度も実装されていない、より根本的な配線漏れだったと判明した(`plan_id`は
  `checkout.session.completed`受信時のみ書き込まれ、Stripeカスタマーポータル経由の
  プラン変更後の`当月上限へ即時適用する`という設計上の確定事項(subscription-
  cancellation-flow-design.md「ダウングレード(プラン変更)フロー」)が実現手段を
  持たないまま残っていた)。aircon-pasha/prototype/subscription_plan_sync.pyの設計を
  翻案し`prototype/subscription_plan_sync.py`を新設(差分チェックはaircon-pashaフェーズ
  208の教訓を踏まえ最初から組み込んだ)、`handle_customer_subscription_updated()`
  (stripe_webhook.py)へ`current_period_end`永続化と同じ位置で配線した。詳細は
  subscription-plan-sync-design.md参照。新規テスト: test_subscription_plan_sync.py
  (新設、14件)、test_stripe_webhook.pyへ3件追加。venture全体673件(`python3
  prototype/run_all_tests.py`、10 files run, 10 passed、既存652件→673件)・schema検証
  27件(`python3 schema/validate_test_cases.py`)いずれもパス(schema/output.schema.json
  への影響は無し、`plan_id`はLLM構造化出力に登場しないフィールド)を確認した。
  承認不要なコード実装・テスト追加・設計文書作成のみで、実Stripeアカウントの接続・
  Price作成(lookup_key設定)自体は引き続きオーナー承認待ちの範囲(pending-approval.md
  参照)であり本フェーズでは行っていない。外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は
  line-reservation-aiへの同種ギャップの横展開要否(店舗単位契約で複数プランを持つか自体の
  確認が必要)、または他venture・アイデア領域の前進を優先候補とする。

- フェーズ94(2026-09-12 19:00 UTC): 他venture・アイデア領域の前進の一環として、
  aircon-pasha/course-set-pashaには既に存在する「実LLM接続後の生成品質検証プラン」
  (llm-quality-verification-plan.md)が本ventureにはまだ作成されていなかったことに
  気づき、新規作成した。llm-system-prompt-draft.mdの厳守事項1〜8・7a・7bと、
  schema/validate_test_cases.pyの19正常系テストケース(G1・G2・OOS1・II1・II2・
  C1〜C3・M1〜M2・CT1〜CT2・CTC1〜CTC3・CTE1・CO1〜CO3)を突き合わせ、各厳守事項の
  検証観点・機械チェック可否・人手判定基準を一覧表にまとめた。aircon-pashaの
  「3回中1回でも不合格なら要改善」という基準を踏襲しつつ、member-retention-notice-
  design.md・contractor-transfer-design.md系のケース(M/CT/CTC/CTE)は専用設計文書側で
  既に判定基準が詳細に定義済みのため本表には重複掲載せず参照にとどめた。コード変更は
  無く、venture全体673件(`python3 prototype/run_all_tests.py`)・schema検証27件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計文書の新規作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。実際のAPIキー取得・
  課金の承認が下りるまで、本プランに基づく実LLM検証自体は引き続き未実施。次回は
  llm-quality-verification-results-template.md(記録表の様式)の作成、または他venture・
  アイデア領域の前進を優先候補とする。

- フェーズ95(2026-09-12 20:00 UTC): フェーズ94が次回候補としていた
  llm-quality-verification-results-template.mdを新規作成した。aircon-pasha/
  course-set-pashaの同名ファイルと同じ位置づけ・記入方法を踏襲しつつ、本ventureの
  ケース構成(schema/validate_test_cases.pyの19正常系: G1・G2・OOS1・II1・II2・
  C1〜C3・M1・M2・CT1・CT2・CTC1〜CTC3・CTE1・CO1〜CO3)にあわせて表を分割した
  (G1・G2表、OOS1・II1・II2表、C1〜C3表、CO1〜CO3表、トークン数・コスト実測表)。
  llm-quality-verification-plan.mdの方針どおり、M1・M2・CT1・CT2・CTC1〜CTC3・CTE1は
  member-retention-notice-design.md・contractor-transfer-design.md系の各設計文書側で
  結果を記録する対象外ケースとして一覧のみ残し、本表には重複掲載しなかった。コード変更は
  無く、venture全体673件(`python3 prototype/run_all_tests.py`)・schema検証27件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計文書の新規作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。実際の記入自体は
  引き続き実LLM接続の承認待ち。次回は他venture・アイデア領域の前進を優先候補とする。

- フェーズ96(2026-09-12 21:00 UTC): 他venture(aircon-pasha・course-set-pasha)には
  既にあるが本venture未着手だったonboarding-guide.md自体のcross-venture parityギャップに
  対応し新規作成した。aircon-pasha/onboarding-guide.mdの構成を踏襲しつつ、本venture固有の
  craftsman-account-linking-design.md(フェーズ25)で確定済みの「LINE友だち追加が先→
  フォームで連携コード入力」という順序(aircon-pashaの申込フォーム主導方式とは逆順、
  course-set-pashaと同じ)、workshop単位の複数職人プランの存在、trial-end-condition-
  design.mdの30日期間上限(低頻度受注特性のため生成回数到達より期間経過でトライアル
  終了を迎える職人が多いと見込まれる点)を反映した。あわせて、craftsman-account-linking-
  design.mdには「代表者以外の職人を同一workshopへ追加登録する具体的な手順」が未確定の
  まま残っていることを本フェーズで確認し、次のステップ候補として明記した。コード変更は
  無く、venture全体673件・schema検証27件いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計文書の新規作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は上記「代表者以外の
  職人の追加登録手順」の設計、または他venture・アイデア領域の前進を優先候補とする。

- フェーズ97(2026-09-12 22:00 UTC): フェーズ96が次のステップ候補としていた「代表者以外の
  職人を同一workshopへ追加登録する具体的な手順」に対応した。craftsman-account-linking-
  design.md 5節の概念設計(招待コード`pending_workshop_invites`)を11節として詳細化し、
  発行条件(契約者本人からの発行であること・`multi_craftsman`プランであること、いずれか
  欠く場合は`not_contractor`/`upgrade_required`エラー)、解決・メンバー追加手順(招待コード
  解決→送信元の所属状況で分岐: 同一workshop既加入なら冪等成功、別workshop加入済みなら
  「1人1工房のみ」というMVP前提〈3節〉に反するため追加を拒否、未所属なら追加)を確定した。
  `workshop_linking.py`に`issue_invite_code_for_workshop`・`resolve_invite_code`・
  `add_member_from_invite_code`を新設し、`WorkshopStoreProtocol`へ`add_member_user_id`を
  追加した(`set_members`は初期作成時の一括設定用のため1名追加には使えず新設)。招待コードの
  期限切れパージ・unfollow時の即時削除は2節の連携コードと同じ`LinkingCodeStoreProtocol`
  形状を共有するため、既存の`purge_expired_links`等を別インスタンスのストアでそのまま
  再利用でき専用関数の新設は不要と判断した。発行契機となる「職人を追加したい」という意図の
  LINEメッセージ検知・message event側のルーティング配線は本フェーズ未着手で次の課題として
  残した(詳細はdesign 11.3節)。新規テスト10件追加、venture全体673件→683件全件
  (`python3 prototype/run_all_tests.py`)・schema検証27件(`python3 schema/validate_test_cases.py`)
  いずれもパスを確認した。承認不要な設計文書追記・コード実装・テスト追加のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないためpending-
  approval.mdへの追記なし。次回は上記「意図検知・ルーティング配線」、または他venture・
  アイデア領域の前進を優先候補とする。

- フェーズ98(2026-09-12 23:00 UTC): フェーズ97が次のステップ候補としていた「招待コード
  解決のmessage event側ルーティング配線」・「ウェルカムメッセージ」の2点に対応した
  (発行契機のLLM意図検知・複数職人プランの人数上限は引き続き次の課題)。
  `cloud_function_webhook.process_message_event()`に`invite_store`引数を追加し、未連携
  ユーザーが送ったテキストを、まず連携コード(`pending_links`、workshop新規作成)、失敗
  した場合のみ招待コード(`pending_workshop_invites`、既存workshopへの追加)の順で解決を
  試みる2段構成とした。両者は11.1節で別名前空間に保存する設計のため、順に試しても事故は
  起きない。`invite_store`は完全省略可能パラメータとし、未指定時はフェーズ69までと同じ
  挙動を保つ後方互換設計とした。`dispatch_webhook_events()`にも同引数を追加し配線した。
  招待コード解決成功時の返信文言として`INVITE_JOIN_SUCCESS_MESSAGE`(「工房への参加が
  完了しました。...」)を新設し、11.3節が未設計としていたウェルカムメッセージを確定した
  (詳細はcraftsman-account-linking-design.md 11.4節)。新規テスト3件(check()呼び出し
  13件分)追加、venture全体`python3 prototype/run_all_tests.py`(10ファイル全件)・
  schema検証27件(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。
  承認不要なコード・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は11.3節に残る
  「発行契機の意図検知・LLM構造化出力へのkind追加」「人数上限の検討」、または他venture・
  アイデア領域の前進を優先候補とする。

- フェーズ99(2026-09-13 00:00 UTC): フェーズ98が次のステップ候補としていた「発行契機の
  意図検知・LLM構造化出力へのkind追加」に着手し、llm-system-prompt-draft.mdに厳守事項7c
  (職人追加・招待コード発行意図検知)を新設した。厳守事項7a(解約意図検知)・7b(有料プラン
  開始意図検知)と対になる構成で、(i)契約者本人からの明確な追加意思表示→招待コード発行
  意図として扱い一次応答文言のみ返す(実際の発行主体チェック・コード発行自体は11.1節
  `issue_invite_code_for_workshop`側の責務)、(ii)非契約者からの同種表明→既存の「契約者様
  にご確認ください」パターンを踏襲、(iii)一般的な相談→通常の受注メモ判定、(iv)判断不能→
  意思確認の一言のみ、の4分岐とした。7bと同様、招待コード自体を自己判断で本文に含めない
  設計とし(コードらしき文字列の生成・引用を避ける)、実際のコード差し込みはPython側に
  委ねる方針を明記した。craftsman-account-linking-design.md 11.3節の該当課題を本フェーズ
  対応済みに更新した。本フェーズはプロンプト文面の設計のみで、対応するschema拡張
  (status enumへの`workshop_invite_request`/`workshop_invite_request_unclear`追加、
  `workshop_invite_notice`フィールド新設)・message-context-selection-design.mdの優先
  順位への組み込みは次の課題として残す(7a・7bと同様、設計→schema拡張を分ける既存の
  進め方を踏襲)。新規テスト・コード変更は無し、venture全体683件
  (`python3 prototype/run_all_tests.py`)・schema検証27件
  (`python3 schema/validate_test_cases.py`)いずれも変更前と同じ結果でパスすることを
  確認した。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は上記schema拡張・
  優先順位組み込み、または他venture・アイデア領域の前進を優先候補とする。

最終更新: 2026-09-13 00:00 UTC
