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

- フェーズ100(2026-09-13 01:00 UTC): フェーズ99が次のステップ候補としていたschema拡張に
  着手し、schema/output.schema.jsonの`status`enumへ`workshop_invite_request`/
  `workshop_invite_request_unclear`の2値と、これらのときのみ非nullとなる
  `workshop_invite_notice`フィールド(`kind`・`body`・`includes_invite_code`)を新設した
  (checkout_notice〈厳守事項7b、フェーズ58〉と同じ設計思想、`includes_invite_code`は
  kindによらず常にfalse)。厳守事項7c(ii)相当(契約者以外からの表明)は6節の既存パターンに
  帰着させる設計のため専用status・フィールドは追加していない。schema/validate_test_cases.py
  に正例2件(WIR1・WIR2)・ネガティブテスト1件(NEG9、includes_invite_code不一致検出)を
  追加し、既存フィクスチャ全27件にも`workshop_invite_notice: null`を追記した
  (craftsman-account-linking-design.md 11.5節参照)。schema検証27件→30件全件・venture
  全体683件(コード変更無しのため変更前と同じ結果)いずれもパスを確認した。承認不要な
  schema・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回
  発生していないためpending-approval.mdへの追記なし。次回は11.3節に残る
  message-context-selection-design.mdへの優先順位組み込み、または「`member_user_ids`
  上限数の検討」、他venture・アイデア領域の前進を優先候補とする。

- フェーズ101(2026-09-13 03:00 UTC): フェーズ100が次のステップ候補としていた
  message-context-selection-design.mdへの優先順位組み込みに対応した。厳守事項7a
  (解約意図検知)・7b(有料プラン開始意図検知)・7c(職人追加・招待コード発行意図検知)は
  いずれも、message-context-selection-design.mdが定める(a)〜(c)のような呼び出し前の
  pre-injection文脈ではなく、(d)「通常の生成リクエスト文脈」1回のLLM呼び出しが返す
  構造化出力(`status`enum値)の一部にすぎないため、(a)〜(d)の4段階優先順位自体への
  変更は不要と結論した(message-context-selection-design.md 5節・craftsman-account-
  linking-design.md 11.6節)。あわせて、(a)(b)(c)に該当したメッセージでは7a/7b/7cの
  意図検知が行われず次回メッセージへ持ち越されるという意図的な挙動を明文化した。本
  フェーズはドキュメント間の整合性確定のみでコード変更は無く、venture全体683件
  (`python3 prototype/run_all_tests.py`)・schema検証30件
  (`python3 schema/validate_test_cases.py`)いずれも変更前と同じ結果でパスすることを
  確認した。承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は11.3節に残る
  「`member_user_ids`上限数の検討」、または3節`select_message_context`統合関数自体の
  実装、他venture・アイデア領域の前進を優先候補とする。

- フェーズ102(2026-09-13 04:00 UTC): 11.3節に残っていた「複数職人プランの
  `member_user_ids`上限数(何名まで許容するか)」の検討・実装に対応した
  (craftsman-account-linking-design.md 11.7節参照)。market-research.mdが確認した
  実在事業者(個人〜小規模の職人が複数在籍する工房)を想定顧客像とし、契約者本人を
  含めて5名を暫定上限に決定した(pricing-plan.mdにも追記)。5名を超える規模の工房は
  本プランの機械的な値上げ・上限緩和では対応せず、README「投資・大規模につき要相談」
  領域の個別カスタム対応として扱う方針とした。`prototype/workshop_linking.py`に
  `MAX_MEMBER_COUNT`定数を新設し、(1)`issue_invite_code_for_workshop()`で招待コード
  発行時点で上限到達なら`member_limit_reached`エラーとして発行しない、(2)並行して
  発行された別の招待コード経由で上限に達した後にもう片方が使われる事故に備え、
  `add_member_from_invite_code()`側でもメンバー追加直前に同じ上限チェックを行う、
  という2箇所での多重防御構成とした。新規テスト3件追加、venture全体686件
  (683件→686件、`python3 prototype/run_all_tests.py`)・schema検証30件
  (`python3 schema/validate_test_cases.py`、schema・フィクスチャへの変更なしのため
  変更前と同じ結果)いずれもパスを確認した。承認不要な設計文書・コード・テスト追加
  のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。次回は上限到達時の案内文言の設計、または3節
  `select_message_context`統合関数自体の実装、他venture・アイデア領域の前進を優先
  候補とする。

- フェーズ103(2026-09-13 05:00 UTC): フェーズ102が次のステップ候補としていた
  「上限到達時の案内文言の設計(LLM構造化出力への反映要否含む)」に対応した
  (craftsman-account-linking-design.md 11.8節参照)。LLM構造化出力への反映は不要と
  結論した(`member_limit_reached`はPython側が人数を数えて機械的に判定する決定論的な
  分岐であり、LLMによる意図検知を必要としないため)。設計を進める過程で、
  `add_member_from_invite_code()`自体はフェーズ102で`member_limit_reached`エラーを
  返すよう実装済みだったにもかかわらず、呼び出し側の`process_message_event()`
  (フェーズ98)が`membership.ok`のみを見て失敗時は常に`LINKING_REQUIRED_MESSAGE`
  (「先に連携コードの送信が必要です」)を返す実装のままだったため、有効な招待コードを
  送っても工房満員時にはコードが無効であるかのように誤解させる実装漏れを発見・修正した。
  `MEMBER_LIMIT_REACHED_MESSAGE`を新設し、上限到達時はこちらを返すよう修正した
  (`prototype/cloud_function_webhook.py`)。あわせて`already_in_another_workshop`
  エラーにも同様の専用文言を用意しようとしたが、`process_message_event()`の冒頭分岐に
  より`add_member_from_invite_code()`へ到達する時点で送信元は必ず未連携であることが
  保証されているため、同エラー分岐は現在の呼び出し経路では到達不可能であることが判明し、
  対応を見送った(将来workshop移籍機能が追加された場合の課題として11.8節に記録)。
  新規テスト1件追加(発行時点では上限未満だったが解決までの間に別経路で上限に達した
  ケースを再現)、venture全体687件(686件→687件、`python3 prototype/run_all_tests.py`)・
  schema検証30件(`python3 schema/validate_test_cases.py`、schema・フィクスチャへの
  変更なしのため変更前と同じ結果)いずれもパスを確認した。承認不要なコード・テスト
  追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。次回は3節`select_message_context`統合関数
  自体の実装、または他venture・アイデア領域の前進を優先候補とする。

- フェーズ104(2026-09-13 06:00 UTC): フェーズ102・103(craftsman-account-linking-
  design.md 11.6〜11.8節)が「次回候補」として引き継ぎ続けていた「3節`select_message_
  context`統合関数自体の実装」に着手しようとしたところ、実際にはフェーズ44
  (2026-09-08 14:00 UTC)の時点で既に`prototype/usage_counter_workshop.py`へ実装・
  テスト8件追加済みであることが判明した。message-context-selection-design.md 3・4節が
  作成当初(フェーズ43)のまま「未実装」と記載され続け、少なくとも3フェーズにわたり
  解消済みの課題を誤って引き継いでいた記載漏れを訂正した。あわせて調査を進めた結果、
  より本質的なギャップとして、`select_message_context`が実装・単体テストとも存在する
  にもかかわらず、実際のLINEメッセージ受信の入口である`process_message_event()`/
  `process_memo_event()`のどちらからも一度も呼び出されていないこと、および
  `llm-system-prompt-draft.md`に契約者譲渡期限切れ案内・再確認・残すメンバー連絡の
  3状態(a)(b)(c)を扱う記述が一切無いことを発見した。既存テスト(`test_process_memo_
  event_contractor_transfer_expired_notice_returns_body()`等)はLLM呼び出し自体を
  スタブ化し「LLMが該当statusを返した前提」で整形ロジックのみを検証しており、実運用で
  この3状態が実際に到達可能かは検証していなかった。すなわち(a)(b)(c)の3つの通知系統は
  設計文書・schema・整形ロジックが揃っていながら現時点の実装では到達不可能という配線漏れ
  である。配線の修正自体は返信文面生成方針の決定(LLM呼び出し無しの定型文言化か、
  プロンプト文脈新設によるLLM出力への委任か)を要する規模のため本フェーズでは着手せず、
  message-context-selection-design.md 6節・craftsman-account-linking-design.md 11.9節に
  次の課題として記録するにとどめた。コード変更は無く、venture全体687件
  (`python3 prototype/run_all_tests.py`)・schema検証30件(`python3 schema/
  validate_test_cases.py`)いずれも変更前と同じ結果でパスすることを確認した。承認不要な
  調査・設計文書修正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回
  発生していないためpending-approval.mdへの追記なし。次回はmessage-context-selection-
  design.md 6節の次の課題(1. (a)(b)(c)の返信文面生成方針の決定)、または他venture・
  アイデア領域の前進を優先候補とする。

最終更新: 2026-09-13 06:00 UTC(フェーズ104: select_message_context「未実装」記載の
誤りを訂正、および実装済みだが呼び出し元に配線されていない・LLMプロンプトにも対応する
記述が無いという、より本質的な配線漏れを発見・記録)

- フェーズ105(2026-09-13 07:00 UTC): フェーズ104が次のステップ候補としていた
  message-context-selection-design.md 6節の次の課題(1. (a)(b)(c)の返信文面生成方針の
  決定)に対応した(craftsman-account-linking-design.md 11.10節参照)。(a)(b)(c)いずれも
  既存方針(LLM構造化出力への委任)を維持し、`member_limit_reached`のようなPython側
  決定論的テンプレートには切り替えないと結論した((b)(c)は自由記述の自然文からの意図
  解釈が必須、(a)はtone-and-manner-guideline.mdが定める文体一貫性を他のLLM生成文言と
  揃えるため)。あわせて、3つのうち最も設計が確定している(a)契約者交代確認・期限切れ
  案内のプロンプト文面をllm-system-prompt-draft.mdへ新設した(7a〜7cとは別区分の
  「文脈注入時の追加指示」として、通常の依頼メモ生成・7a〜7cの意図判定すべてに優先する
  旨を明記)。(b)(c)のプロンプト文面新設、および`LlmCallClient.generate()`への文脈注入
  経路の実装・`process_message_event()`/`process_memo_event()`の`select_message_
  context()`経由への配線は、渡すべき情報の整理がまだ必要なため次の課題として残した。
  コード変更は無く、venture全体687件(`python3 prototype/run_all_tests.py`)・
  schema検証30件(`python3 schema/validate_test_cases.py`)いずれも変更前と同じ結果で
  パスすることを確認した。承認不要な設計文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記
  なし。次回は(b)(c)のプロンプト文面新設、または他venture・アイデア領域の前進を優先
  候補とする。

最終更新: 2026-09-13 07:00 UTC(フェーズ105: (a)(b)(c)返信文面生成方針を決定〈LLM
構造化出力への委任を維持〉、(a)契約者交代確認・期限切れ案内のプロンプト文面を新設)

- フェーズ106(2026-09-13 10:00 UTC): フェーズ105が次のステップ候補としていた
  (b)契約者交代・再確認応答検知のプロンプト文面新設に対応した(message-context-
  selection-design.md 8節参照)。contractor-transfer-confirmation-detection-design.md
  3節で既に確定していた判定パターン(送信者〈現契約者本人〉からの自由記述の返信を
  肯定/否定/不明瞭の3分類に判定するルール)・schema設計(status 3値・`contractor_
  transfer_confirmation`フィールド)をもとに、llm-system-prompt-draft.mdへ「文脈注入
  時の追加指示: 契約者交代・再確認応答検知」のプロンプト文面を新設した。(a)が「受信
  内容を問わず常に同じ一言を返す」構造だったのに対し、(b)は厳守事項7a〜7cと同種の
  自然文からの意図解釈による3分岐判定である点が異なる(ただし7a〜7cの番号体系には
  含めず、(a)と同じ別区分として扱う)。着手にあたり確認したところ、schema/output.
  schema.json・schema/validate_test_cases.pyへの反映(status enum3値・`contractor_
  transfer_confirmation`フィールド追加)はフェーズ37(2026-09-08 02:00 UTC)の時点で
  既に完了済みであり、本フェーズで新規に必要だったのはプロンプト文面のみだった。
  コード変更は無く、venture全体687件(`python3 prototype/run_all_tests.py`)・
  schema検証30件(`python3 schema/validate_test_cases.py`)いずれも変更前と同じ結果で
  パスすることを確認した。承認不要な設計文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記
  なし。次回は(c)「残すメンバー」連絡検知のプロンプト文面新設(前提となるメンバー
  一覧のプロンプトへの渡し方の設計判断を含む)、または他venture・アイデア領域の前進を
  優先候補とする。

最終更新: 2026-09-13 10:00 UTC(フェーズ106: (b)契約者交代・再確認応答検知のプロンプト
文面を新設。(c)・schema反映・実配線は次の課題)

- フェーズ107(2026-09-13 12:00 UTC): フェーズ106が次のステップ候補としていた
  (c)「残すメンバー」連絡検知のプロンプト文面新設に対応した(message-context-
  selection-design.md 9節・llm-system-prompt-draft.md参照)。着手の前提としていた
  「メンバー一覧(`member_user_ids`)をどうプロンプトへ渡すか」を検討した結果、
  member-retention-notice-design.md 3節が既に「LLMによる本人確認・workshop内
  メンバーとの突き合わせは行わない」と定めていたことから、メンバー一覧・名前は
  プロンプトへ一切渡さず、LLMは受信メッセージ本文からの自由な名前・呼称抽出のみを
  担当する方針で確定した(「どう渡すか」ではなく「渡さない」が答えだったと判明)。
  この結論をもとにllm-system-prompt-draft.mdへ(c)のプロンプト文面(kind=
  member_retention_selection/member_retention_unclearの2分岐)を新設した。
  schema(`member_retention_notice`のstatus enum・専用フィールド)は2026-09-07
  13:02 UTC改訂で既に反映済みのため追加反映は不要だった。これにより(a)(b)(c)いずれも
  プロンプト文面の設計が完了した。コード変更は無く、venture全体687件
  (`python3 prototype/run_all_tests.py`)・schema検証30件(`python3 schema/
  validate_test_cases.py`)いずれも変更前と同じ結果でパスすることを確認した。承認不要な
  設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回
  発生していないためpending-approval.mdへの追記なし。次回は6節で整理した実配線
  (`LlmCallClient.generate()`への文脈注入経路の実装、`process_message_event()`/
  `process_memo_event()`の`select_message_context()`経由への配線、統合テストの追加)、
  または他venture・アイデア領域の前進を優先候補とする。

最終更新: 2026-09-13 12:00 UTC(フェーズ107: (c)「残すメンバー」連絡検知のプロンプト
文面を新設。メンバー一覧はプロンプトへ渡さない方針を確定。(a)(b)(c)すべてプロンプト
文面完了、次は実配線)

- フェーズ108(2026-09-13 14:00 UTC): フェーズ107が次の課題としていた実配線に
  着手した。6節(message-context-selection-design.md)が挙げていた3項目
  (`LlmCallClient.generate()`への文脈注入経路の実装・`process_message_event()`/
  `process_memo_event()`の制御フロー変更・統合テスト追加)を一度に配線するのは
  「1フェーズの作業量を超える」としていた見立て通りだったため、(a)契約者譲渡・期限切れ
  案内1系統のみに絞って配線した。`LlmCallClient.generate()`(Protocol)・
  `_generate_with_api_retry()`へ`context`引数を新設し、`process_memo_event()`が
  `process_generation_request()`を呼び出す直前で`check_and_expire_pending_
  contractor_transfer()`(`select_message_context()`の(a)判定と同じ関数)を直接
  呼び出す分岐を追加、非None検出時は新設の`_process_contractor_transfer_expired_
  notice()`(文脈注入付きLLM呼び出し・既存`format_reply_text()`での返信)へ委譲する
  ようにした。`select_message_context()`統合関数自体はまだ呼び出さず、(a)専用の判定
  関数を直接呼ぶ最小限の変更にとどめた((b)(c)の条件が同時に真の場合のフォールスルーを
  避けるため)。統合テスト2件(期限切れpending検出時の実際のLLM呼び出し・文脈注入・
  usage_counter非加算の確認、期限内pendingでは誤発火しないことの回帰確認)を追加した。
  詳細はmessage-context-selection-design.md 10節参照。(b)契約者交代・再確認応答検知・
  (c)「残すメンバー」連絡検知は同様の配線を次の課題として残した。
  `prototype/test_cloud_function_webhook.py`のcheck()件数292件→301件(統合テスト2件
  追加分)、`python3 prototype/run_all_tests.py`(全10ファイル)・`python3 schema/
  validate_test_cases.py`(30件)いずれもパスすることを確認した。承認不要なコード実装・
  テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。次回は(b)(c)への同様の配線、または他
  venture・アイデア領域の前進を優先候補とする。

最終更新: 2026-09-13 14:00 UTC(フェーズ108: (a)契約者譲渡・期限切れ案内のみ実配線
〈LlmCallClient.generate()のcontext引数新設・process_memo_event()への分岐追加・
統合テスト2件追加〉。(b)(c)・select_message_context()への一本化は次の課題)

- フェーズ109(2026-09-13 15:00 UTC): フェーズ108が次の課題としていた(b)契約者交代・
  再確認応答検知の実配線に対応した(message-context-selection-design.md 11節参照)。
  `process_memo_event()`で(a)がNoneを返した場合に続けて`is_contractor_transfer_
  confirmation_context()`を呼び出す分岐を追加し、真の場合は新設した`_process_
  contractor_transfer_confirmation()`(文脈注入付きLLM呼び出し)へ委譲する。(a)と異なり
  (b)はLLMが返したstatusに応じてアプリケーション側の状態更新(`apply_contractor_
  transfer()`によるcontractor_user_id更新、または`cancel_pending_contractor_
  transfer()`によるpending削除のみ)を行う必要があり、3分岐(確定/取消/不明瞭)の
  呼び分けを実装した。統合テスト追加時、既存の期限内pending回帰テストが送信者を
  契約者本人としていたため図らずも(b)の条件も満たしてしまい、テスト側の前提を
  修正する必要が生じたことも判明した(詳細は同design.md 11節)。統合テスト4件を
  新設し、`test_cloud_function_webhook.py`のcheck()件数301件→318件・venture全体
  10ファイル・schema検証30件いずれもパスを確認した。承認不要なコード実装・テスト
  追加・既存テストの前提修正のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は(c)「残す
  メンバー」連絡検知への同様の配線、または他venture・アイデア領域の前進を優先候補
  とする。

最終更新: 2026-09-13 15:00 UTC(フェーズ109: (b)契約者交代・再確認応答検知を実配線
〈status別のapply_contractor_transfer()/cancel_pending_contractor_transfer()呼び分け〉。
既存回帰テストの送信者設定を(a)(b)分離のため修正。(c)は次の課題)

- フェーズ110(2026-09-13 16:00 UTC): フェーズ109が次の課題としていた(c)「残すメンバー」
  連絡検知の実配線に対応した(message-context-selection-design.md 12節参照)。
  `process_memo_event()`で(a)(b)いずれも該当しない場合に続けて、送信者が契約者本人かつ
  `workshop_store.get_pending_reduction_effective_at()`が設定済みか(select_message_
  context()の(c)判定と同じ条件)を直接評価する分岐を追加し、真の場合は新設した
  `_process_member_retention_notice()`(文脈注入付きのLLM呼び出し)へ委譲する。(a)(b)と
  異なり(c)はこの時点ではまだ`member_user_ids`を縮小せず、`status=member_retention_
  selection`のときのみ`workshop_store.set_specified_retention_member_name()`で
  `specified_member_name`を記録するにとどめる(member-retention-notice-design.md 3節の
  通り、実際の縮小反映は次回生成リクエスト受信時の`check_and_apply_pending_member_
  reduction()`都度チェックで行う)。`status=member_retention_unclear`のときは何もしない。
  (c)は9節で確定した通りメンバー一覧・名前をプロンプトへ渡さないため、注入する
  contextは`{"kind": "member_retention_notice"}`のみとした((a)(b)のような
  `candidate_member_name`は含まない)。統合テスト3件(明確な指定時の記録確認・不明確時の
  未記録確認・契約者以外からのメッセージでは発火しない回帰確認)を新設し、
  `test_cloud_function_webhook.py`のcheck()件数318件→331件、`python3 prototype/
  run_all_tests.py`(全10ファイル)・`python3 schema/validate_test_cases.py`(30件)
  いずれもパスを確認した(schema側の変更は無く既存の`member_retention_notice`
  フィールドをそのまま利用)。これにより(a)(b)(c)すべての実配線が完了した。承認不要な
  コード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回は(a)(b)(c)個別分岐の
  積み上げを`select_message_context()`統合関数への一本化に置き換えるかどうかの検討
  (12節「次の課題」参照)、または他venture・アイデア領域の前進を優先候補とする。

最終更新: 2026-09-13 16:00 UTC(フェーズ110: (c)「残すメンバー」連絡検知を実配線。
(a)(b)(c)すべて配線完了。次は`select_message_context()`への一本化検討)

- フェーズ111(2026-09-13 20:00 UTC): フェーズ110が次の課題としていた
  `select_message_context()`統合関数への一本化(message-context-selection-design.md
  12節)を実施した。`process_memo_event()`内で(a)(b)(c)それぞれ専用の判定条件を
  個別に直接評価していた積み上げ方式(フェーズ108〜110)と、それに続く
  `process_generation_request()`の直接呼び出しを、`select_message_context()`の
  単一呼び出し1つに置き換え、返ってきた`MessageContext.kind`で(a)(b)(c)(d)を
  分岐する形にした。12節が懸念していた「(d)経路で二重呼び出しになる」という論点は、
  実際には二重呼び出しではなく単純な置き換えの問題であり、`select_message_context()`が
  返す`MessageContext.generation_result`をそのまま使えば
  `process_generation_request()`の呼び出し回数は変わらないことを確認した。
  `TrialPeriodOverError`・`PaymentSuspendedError`は(d)経路(select_message_context()
  内部のprocess_generation_request呼び出し)でのみ送出されるため、
  `select_message_context()`呼び出し全体を1つのtry/exceptで囲むだけで従来と同じ捕捉が
  できた。`check_and_expire_pending_contractor_transfer`・
  `is_contractor_transfer_confirmation_context`・`process_generation_request`の
  3関数はcloud_function_webhook.py側で直接使わなくなったためimportから削除した。
  `test_cloud_function_webhook.py`単体でPASS=331(フェーズ110時点と同じ件数、挙動に
  変化なし)、`python3 prototype/run_all_tests.py`(全10ファイル)・`python3 schema/
  validate_test_cases.py`(30件)いずれもパスを確認した。承認不要なリファクタリング
  のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。

最終更新: 2026-09-13 20:00 UTC(フェーズ111: (a)(b)(c)(d)の分岐を
`select_message_context()`統合関数への単一呼び出しに一本化。挙動・テスト件数に
変化なしを確認。次は他venture・アイデア領域の前進を優先候補とする)

- フェーズ112(2026-09-14 00:10 UTC): trial-end-notification-design.md 6節・
  payment-failure-dunning-design.md 6節がそれぞれ独立に残していた「本venture側に
  まだ存在しない日次スケジューラ本体」という同一の未着手事項に対応した。
  daily-scheduler-design.mdを新規作成し、(B)トライアル30日到達報告・決済失敗3日前
  リマインドの選定ロジック(`is_trial_end_report_due()`/`select_due_trial_end_
  reports()`・`is_payment_failure_reminder_due()`/`select_due_payment_failure_
  reminders()`、いずれも純粋関数)を`prototype/daily_scheduler.py`(新設)に実装した。
  `WorkshopStoreProtocol`へ`get_payment_failure_reminder_sent_at`/`set_payment_
  failure_reminder_sent_at`を新設し、`clear_payment_failure_detected_at()`実行時
  (決済成功による復旧)にあわせて`payment_failure_reminder_sent_at`もクリアするよう
  拡張した(aircon-pasha版と同じ理由: リマインド送信済みworkshopが復旧後に再度決済
  失敗した際、二度とリマインドが送信されなくなることを防ぐ)。実際のCloud Function
  本体・LINE Push送信配線・全workshop走査ロジックは、実LINE公式アカウント接続・
  Cloud Scheduler実行環境の構築がオーナー承認待ちのため次の課題として残した(詳細は
  daily-scheduler-design.md 6節)。新規テスト12件追加(`test_daily_scheduler.py`
  新設)、venture全体11ファイル(`python3 prototype/run_all_tests.py`)・schema検証
  30件(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。承認不要な
  設計文書作成・コード実装・テスト追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-14 00:10 UTC(フェーズ112: trial-end-notification-design.md 6節・
payment-failure-dunning-design.md 6節が残していた日次スケジューラ本体の机上設計に
着手。(B)トライアル30日到達報告・決済失敗3日前リマインドの選定ロジックを
`prototype/daily_scheduler.py`として実装、`payment_failure_reminder_sent_at`
フィールドを新設。実際のCloud Function配線・Push送信は引き続き次の課題)

- フェーズ113(2026-09-14 03:00 UTC): aircon-pasha・course-set-pasha・line-reservation-aiには
  既にGitHub Actionsによるテスト自動実行(各venture配下のci-setup.md参照)が導入済みだったが、
  本ventureにはCIワークフロー自体が未導入だったcross-venture parityのギャップに対応した。
  `.github/workflows/kura-pasha-tests.yml`を新規作成し、`ventures/kura-pasha/`配下への変更を
  トリガーに`prototype/run_all_tests.py`(単体テスト)・`schema/validate_test_cases.py`
  (期待出力検証)を自動実行する構成とした。他3ventureのワークフローがそのまま採用している
  `python3 -m unittest discover -p "test_*.py" -v`は、本ventureのprototype/test_*.py
  11ファイルのうち8ファイルが`unittest.TestCase`ベースではなく独自のcheck()/PASS/FAIL形式の
  スクリプトであるため(フェーズ88〜90・cross-venture-discover-compatibility-review.md参照)
  そのまま流用するとテストの大半が実行されずCIが見かけ上「成功」してしまう重大な問題がある
  ことに気付き、discoverコマンドは使わず既存の`run_all_tests.py`(全test_*.pyを個別プロセスで
  実行し終了コードを集約するラッパー)をワークフロー側でも採用した。経緯・判断理由を
  ci-setup.md(新規作成)に記録した。ローカルで`python3 prototype/run_all_tests.py`
  (11ファイル全件パス)・`python3 schema/validate_test_cases.py`(30件全件パス、いずれも
  変更前と同じ結果)を確認した。リポジトリ設定ファイルの追加のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
  次回はコミット後のCI実行結果(status: completed / conclusion: success)の確認、または
  他venture・アイデア領域の前進を優先候補とする。

最終更新: 2026-09-14 03:00 UTC(フェーズ113: GitHub ActionsによるCI自動実行を新規導入
〈discover非互換のため既存run_all_tests.pyを採用〉。他3ventureとのcross-venture parity
ギャップを解消)

- フェーズ114(2026-09-14 04:00 UTC): 他venture・アイデア領域の前進候補を探す過程で
  本README.mdの変更履歴を精査したところ、直前2フェーズの記録に不整合があることを
  発見した。(1) daily-scheduler-design.md・`prototype/daily_scheduler.py`・
  `prototype/test_daily_scheduler.py`の新設(コミット`86424da`、2026-09-14 00:10 UTC、
  trial-end-notification-design.md・payment-failure-dunning-design.md各6節にも
  「フェーズ112で対応済み」という参照あり)は設計文書・コード・テストとも実施済み
  だったにもかかわらず、本README.mdの変更履歴には該当フェーズのエントリが一件も
  追記されていなかった。(2) その欠落に気付かないまま後続でCI自動実行を追加した作業
  (コミット`b99aafe`、同日03:04 UTC)が「フェーズ111の次は112」と判断して自らを
  フェーズ112と記録したため、日次スケジューラのフェーズ番号(本来の112)とCI自動実行の
  フェーズ番号が重複するという整合性の欠落も生じていた。原因はいずれも同じで、
  本ventureの変更(prototype/design doc)を扱うコミットとREADME.md変更履歴への
  追記が同一コミット内で保証される仕組みになっていないことにある。実装自体に手を
  入れる必要は無かったため、上記フェーズ112(daily-scheduler-design.md・コミット
  ログの内容から再構成)を本来の時系列位置(フェーズ111の直後)へ追記し、CI自動実行の
  記録をフェーズ112からフェーズ113へ改番することで整合性を回復した(ヘッダー行・
  「最終更新」行の両方を修正)。あわせてventure全体11ファイル(`python3 prototype/
  run_all_tests.py`)・schema検証30件(`python3 schema/validate_test_cases.py`)を
  再実行し、`test_daily_scheduler.py`12件・他既存テストいずれも変更前と同じ結果で
  パスすることを確認した(コード変更は無いため非該当)。承認不要な変更履歴の記載漏れ・
  番号重複の訂正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回
  発生していないためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の
  前進、またはフェーズ113「今後の課題」(コミット後のCI実行結果確認)を優先候補とする。

最終更新: 2026-09-14 04:00 UTC(フェーズ114: 変更履歴の記載漏れ〈フェーズ112:
日次スケジューラ〉と番号重複〈CI自動実行が誤ってフェーズ112を再利用〉を発見・訂正。
日次スケジューラのエントリを本来の時系列位置へ追記し、CI自動実行の記録をフェーズ113へ
改番。コード変更は無し)

- フェーズ115(2026-09-14 04:00 UTC): フェーズ113「今後の課題」としていた、フェーズ113
  (コミット`b99aafe`)・フェーズ114(コミット`f6d4bc0`)それぞれのpush後にGitHub Actions
  `.github/workflows/kura-pasha-tests.yml`が実際に実行され成功したかをGitHub API
  (`actions_list`/`list_workflow_runs`、`resource_id=kura-pasha-tests.yml`)で確認した。
  2件のワークフロー実行(run_number 1: head_sha `b99aafe`、run_number 2: head_sha
  `f6d4bc0`)がいずれも`status: completed`・`conclusion: success`であることを確認し、
  discover非互換のためrun_all_tests.pyラッパーを採用したフェーズ113の設計判断が実際の
  CI環境でも問題なく機能していることを検証できた。コード変更は無く、ローカルでの
  回帰確認として`python3 prototype/run_all_tests.py`(11ファイル全件パス)・`python3
  schema/validate_test_cases.py`(30件全件パス、いずれも変更前と同じ結果)もあわせて
  実行した。承認不要な状態確認のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は他venture・
  アイデア領域の前進、または引き続き未走査の設計docの残課題棚卸しを優先候補とする。

最終更新: 2026-09-14 04:00 UTC(フェーズ115: フェーズ113・114push後のGitHub Actions
CI実行結果〈2件とも成功〉をGitHub APIで確認。コード変更は無し)

- フェーズ116(2026-09-14 10:00 UTC): payment-failure-dunning-design.md「6. 残課題」に
  残っていた「運営者向け通知(course-set-pasha/payment-suspension-owner-notification-
  design.md相当)は本venture側に運営者向け通知の送信先・仕組み自体がまだ無いため次の課題」
  に対応した。course-set-pasha版の設計・blocked-but-billing-owner-notification-
  design.md(フェーズ81、本venture既存の同種翻案)を踏まえ、payment-suspension-owner-
  notification-design.mdを新規作成した。本venture固有の差分として、判定に必要な情報
  (payment_failure_detected_at・猶予日数・通知済み時刻)が`WorkshopStoreProtocol`1つに
  揃っているため、blocked-but-billingのような候補一覧専用ファイルを新設せず
  `select_due_payment_suspension_owner_notifications()`一本で完結させた点、および
  `clear_payment_failure_detected_at()`が新規フィールド`payment_suspension_owner_
  notified_at`もあわせてクリアするようにしたことで(payment_failure_reminder_sent_atを
  既に同じ関数内でクリアしている既存方針の踏襲)、course-set-pasha版のような呼び出し側
  でのクリア個別呼び出しが不要になった点が異なる。`usage_counter_workshop.py`へ
  `get_payment_suspension_owner_notified_at`/`set_payment_suspension_owner_notified_at`
  (WorkshopStoreProtocol・InMemoryWorkshopStore両方)を追加し、`prototype/payment_
  suspension_owner_notification.py`(新規)・`prototype/test_payment_suspension_owner_
  notification.py`(新規11件)を実装した。payment-failure-dunning-design.md「6. 残課題」
  の該当記載も解消済みとして更新した。venture全体12ファイル(`python3 prototype/
  run_all_tests.py`、11ファイル→12ファイル)・schema検証30件(`python3 schema/
  validate_test_cases.py`、コード変更が新規モジュール追加のみでスキーマ自体は不変のため
  30件のまま)いずれもパスを確認した。実際のオーナーLINEユーザーID取得・LINE Push送信
  配線、3日前リマインド専用スケジューラへの実送信配線はいずれも引き続き次の課題として
  残る(実LINE公式アカウント接続自体がオーナー承認待ちのため)。承認不要な設計文書作成・
  コード追加・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。

最終更新: 2026-09-14 10:00 UTC(フェーズ116: 決済失敗ダニングの残課題だった運営者向け
制限モード移行通知〈payment-suspension-owner-notification-design.md〉を新規設計・実装。
`WorkshopStoreProtocol`へ`payment_suspension_owner_notified_at`追加、新規テスト11件)

- フェーズ117(2026-09-14 14:00 UTC): フェーズ116で新設した`payment_suspension_owner_
  notification.py`(制限モード移行時のオーナー向けLINE通知)が、daily-scheduler-design.md
  (フェーズ112)のCloud Function G構成図(2節)に一切記載されておらず、日次バッチの
  どこで呼ばれるのか設計上未定義のまま残っていた欠落を解消した。同構成図に「4)
  send_payment_suspension_owner_notifications()を呼び出す」ステップを追記し、
  選定ロジック・送信配線とも当該モジュール側で完結済みのため`daily_scheduler.py`への
  ロジック複製は不要である旨も明記した。あわせてpayment-suspension-owner-notification-
  design.md「8. 今後の課題」に残っていた「3日前リマインド送信専用スケジューラは
  daily-scheduler-design.mdへの統合を次回の課題とする」という記載が、実際には
  同スケジューラ(3.2節`select_due_payment_failure_reminders()`)がフェーズ116より
  前のフェーズ112時点で既に実装済みだった(本ドキュメントの対象である制限モード移行時の
  オーナー通知とは別物の契約者向け3日前リマインドを混同した記載誤り)ことに気付き、
  取り消し線付きで訂正した。コード変更は無く、venture全体12ファイル(`python3
  prototype/run_all_tests.py`)・schema検証30件(`python3 schema/validate_test_cases.py`)
  いずれもパス(変更前と同じ結果)を確認した。承認不要な設計doc記載の欠落・誤りの
  訂正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の前進、または
  引き続き未走査の設計docの残課題棚卸しを優先候補とする。

最終更新: 2026-09-14 14:00 UTC(フェーズ117: daily-scheduler-design.md 2節の構成図に
オーナー制限モード通知〈フェーズ116〉の呼び出しステップを追記。あわせて
payment-suspension-owner-notification-design.md「8. 今後の課題」の3日前リマインド
スケジューラに関する記載誤り〈既にフェーズ112で実装済み〉を訂正。コード変更は無し)

- フェーズ118(2026-09-14 19:00 UTC): trial-end-condition-design.md「6. 今後の課題」が
  フェーズ52時点の記載のまま更新されておらず、実際にはフェーズ54(`customer.subscription.
  deleted`受信時の解約完了案内)・フェーズ56(`invoice.payment_failed`/`payment_succeeded`
  ダニング対応、`"past_due"`一律ブロックを`is_payment_suspended()`猶予期間判定へ見直し)で
  既に解消済みだった2項目が「未着手」のまま残っていた記載漏れを発見・訂正した。あわせて
  同セクションが挙げていた`trial_start_at`のworkshop作成時書き込み(`workshop_linking.py`の
  `create_workshop_from_linking_code()`で実装済み、README.mdフェーズ79の「次にやること」
  棚卸しでは解消済みと記録されていたが本設計文書側には未反映のままだった)についても
  同様に記載を訂正した。本セクションに残る未解消項目は実Stripe接続・Checkout Session発行
  フロー自体(オーナー承認待ち)のみであることを明記した。コード変更は無く、回帰確認として
  venture全体12ファイル(`python3 prototype/run_all_tests.py`)・schema検証30件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。承認不要な
  設計doc記載の欠落訂正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の
  前進、または想定顧客ヒアリング実施承認(pending-approval.md記載)を待つ間の他残課題棚卸し
  を優先候補とする。

最終更新: 2026-09-14 19:00 UTC(フェーズ118: trial-end-condition-design.md「6. 今後の
課題」がフェーズ52時点のまま放置され、フェーズ54・56で解消済みのWebhook対応2項目と
`trial_start_at`書き込みが「未着手」表記のまま残っていた記載漏れを発見・訂正。コード
変更は無し)

- フェーズ119(2026-09-14 23:00 UTC): course-set-pashaが本日22:00 UTCの定例更新で
  WebSearchにより確認したクレジットカード継続課金手数料の仮定値改訂(3.6%→4.3%、
  Stripe Billing自体の追加手数料0.7%が上乗せされるとの複数の独立した二次情報での
  記載一致を確認)は、course-set-pasha/subscription-billing-cost-estimate.md「Stripe
  Billing手数料率の一次情報確認」節が本venture(kura-pasha)を含む全4venture共通の
  前提(継続課金をStripe Billingで実現する設計)に影響すると明記していたにもかかわらず、
  本venture固有のunit-economics-estimate.mdには未反映のまま3.6%仮定が残っていた
  cross-venture parityのギャップを解消した。決済手数料の前提記述・月次粗利試算表
  (3プラン×キャッシュ有無)・従量課金(超過分)の粗利試算表・結論・残課題を4.3%仮定で
  再計算・更新した(粗利率はキャッシュなしで93.1〜94.1%〈改訂前93.8〜94.8%〉、キャッシュ
  利用時で94.6〜95.0%〈改訂前95.3〜95.7%〉に低下)。あわせて比較対象のcourse-set-pasha側
  粗利率も同venture側の改訂後数値(91.2〜94.4%)に更新し、aircon-pasha・
  line-reservation-aiのunit-economics-estimate.mdは本フェーズ時点でまだ3.6%仮定のまま
  未反映である旨を残課題として明記した。コード変更は無く、回帰確認としてventure全体
  12ファイル(`python3 prototype/run_all_tests.py`)・schema検証30件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。承認不要な
  ドキュメント内試算値の更新のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の
  前進、aircon-pasha・line-reservation-ai側への同様の改訂反映、または想定顧客ヒアリング
  実施承認(pending-approval.md記載)を待つ間の他残課題棚卸しを優先候補とする。

最終更新: 2026-09-14 23:00 UTC(フェーズ119: course-set-pashaで確認済みの決済手数料
仮定改訂〈3.6%→4.3%〉を本venture固有のunit-economics-estimate.mdに反映し、粗利率
試算表・結論・残課題を再計算・更新した。コード変更は無し)

- フェーズ120(2026-09-15 03:00 UTC): daily-scheduler-design.md 6節が「実LINE公式
  アカウント接続・Cloud Scheduler実行環境の構築がオーナー承認待ち」を理由に次回以降の
  課題としていたCloud Function G本体(送信配線)の実装に着手したところ、その理由自体が
  一部誤りだったことが判明した。`prototype/cloud_function_webhook.py`(フェーズ62)で
  `format_trial_end_notification_message()`が既に実装済みであり、`daily_scheduler.py`
  冒頭コメントの「本venture側でまだ実装していないため対象外」という記載が誤りだった
  (payment_suspension_owner_notification.py〈フェーズ116〉と同じくProtocol経由の
  依存注入・InMemoryStub検証で実クラウド接続なしにCloud Function本体自体は実装・テスト
  可能だった)。`prototype/daily_scheduler.py`に`send_trial_end_reports()`・
  `send_payment_failure_reminders()`・`run_daily_workshop_checks()`(2節のCloud
  Function G本体、3系統の送信を順に実行)を実装し、テスト8件を追加した。実際のCloud
  Scheduler設定・実LINE公式アカウント接続のみ引き続きオーナー承認待ちとして残る。詳細は
  daily-scheduler-design.md 6〜7節参照。venture全体12ファイル(`python3 prototype/
  run_all_tests.py`)・schema検証30件(`python3 schema/validate_test_cases.py`)いずれも
  パスを確認した。承認不要なコード実装・テスト追加・design doc記載訂正のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないためpending-
  approval.mdへの追記なし。

最終更新: 2026-09-15 03:00 UTC(フェーズ120: daily-scheduler-design.md 6節の記載誤りを
発見し、Cloud Function G本体の送信配線〈send_trial_end_reports()・
send_payment_failure_reminders()・run_daily_workshop_checks()〉を実装。テスト8件追加。
実クラウド接続〈Cloud Scheduler・LINE公式アカウント〉のみ引き続きオーナー承認待ち)

- フェーズ121(2026-09-15 07:00 UTC): aircon-pashaがフェーズ222(support-cost-
  estimate.md)で「cross-venture展開の第一弾」として着手した人的サポートコスト
  (オンボーディング・問い合わせ対応)試算の第二弾として、本venture固有の
  support-cost-estimate.mdを新規作成した。course-set-pasha版と同じ時給3,000円
  (未検証の仮置き)を採用しつつ、本venture固有の複数職人プラン(workshop共有)・
  契約者(contractor)譲渡フローに伴う追加対応工数を織り込み、2ヶ月目以降の月次対応
  コストを単一プラン相当500円・複数職人プラン相当500〜1,250円、運営者1人あたりの
  対応可能workshop数の目安を約60〜120workshopと試算した。あわせてunit-economics-
  estimate.mdの残課題1点目が「aircon-pasha・line-reservation-aiへの決済手数料4.3%
  改訂の反映待ち」としていたが、両venture側で既にフェーズ221・フェーズ相当時点で
  改訂済みだったにもかかわらず記載が同期更新されていなかった記載漏れを発見・訂正した。
  現金支出コストではなく機会費用のため既存の粗利率試算自体は変更していない。コード
  変更は無く、回帰確認としてventure全体12ファイル(`python3 prototype/
  run_all_tests.py`)・schema検証30件(`python3 schema/validate_test_cases.py`)
  いずれもパス(変更前と同じ結果)を確認した。承認不要なアイデア追加・ドキュメント
  新規作成・記載漏れ訂正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回はline-reservation-ai
  へのcross-venture展開(残り1件)、または他venture・アイデア領域の前進を優先候補と
  する。
- 最終更新: 2026-09-15 07:00 UTC

- フェーズ122(2026-09-15 10:00 UTC): craftsman-account-linking-design.md(フェーズ25)
  「未検証・残課題」節が、フェーズ25作成時点の3項目(usage_counterのworkshop_idキー
  読み替え・ダウングレード時の余剰メンバー扱い・契約者譲渡機能)をいずれも「未着手・
  次の課題」のまま記載し続けていたが、実際にはその後のフェーズ26(usage-counter-
  workshop-key-design.md)・フェーズ28(downgrade-excess-member-handling-design.md)・
  フェーズ33(contractor-transfer-design.md、以後contractor-transfer-*系ドキュメントに
  発展)でいずれも専用ドキュメントとして解消済みであり、データ構造まとめの表
  (`usage_counter/{workshop_id}`行)にも同様の古い記載が残っていた記載漏れを発見・
  訂正した。各項目に解消先ドキュメントへの参照を追記し、引き続き未着手のまま残るのは
  実LINE公式アカウント接続・Stripe接続・招待コード発行の実装(オーナー承認待ち)のみで
  あることを明記した。コード変更は無く、回帰確認としてventure全体12ファイル
  (`python3 prototype/run_all_tests.py`)・schema検証30件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。承認不要な
  ドキュメント記載漏れ訂正・アイデア追加のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。次回は他venture・
  アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-15 10:00 UTC

- フェーズ123(2026-09-15 11:00 UTC): line-reservation-aiフェーズ続き230「今後は
  4venture間の比較検討・実運用データ取得後の再検証が次の課題」を受け、course-set-pasha
  (フェーズ216)・aircon-pasha(フェーズ222)・kura-pasha(フェーズ121)・
  line-reservation-ai(フェーズ続き230)の4venture分のsupport-cost-estimate.mdを横断
  比較するcross-venture-support-cost-comparison.mdを新規作成した(kura-pashaフェーズ89の
  cross-venture-discover-compatibility-review.mdと同じ横断レビュー形式を踏襲)。2ヶ月目
  以降の月次対応コスト・月次粗利額に対する比率・運営者1人あたり対応可能上限を表形式で
  整理し、(1)対応コストの粗利額比率は4venture間で約24.5〜28%とばらつきが小さいこと、
  (2)運営者1人あたり対応可能上限はcourse-set-pasha(約120顧客)からline-reservation-ai
  (約40顧客)まで約3倍の開きがあること、(3)line-reservation-aiが「対応コスト絶対額
  最高」かつ「対応可能上限最少」の両方に該当する唯一のventureであり、サポート負荷軽減策
  (FAQ整備・セルフサービス化等)を優先検討すべき最有力候補と暫定的に順位付けできること、
  を示唆として整理した。あわせてcourse-set-pasha/support-cost-estimate.md「残課題」に
  本ドキュメントへの参照を追記した。いずれも4venture共通の未検証仮定(時給3,000円・月
  20時間上限)に基づく机上の比較であり、実運用データによる再検証が引き続き最優先の課題
  である旨を明記した。コード変更は無く、回帰確認としてventure全体12ファイル(`python3
  prototype/run_all_tests.py`)・schema検証30件(`python3 schema/validate_test_cases.py`)
  いずれもパス(変更前と同じ結果)を確認した。承認不要なドキュメント新規作成・アイデア
  追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。次回はサポート負荷軽減策(FAQ整備等)の具体的検討、
  他venture・アイデア領域の前進を優先候補とする。
- フェーズ124(2026-09-15 14:00 UTC): 未走査の設計docの残課題棚卸しを継続し、
  payment-failure-dunning-design.md 6節「残課題」の記載が、フェーズ120
  (daily-scheduler-design.md 7節)で実際には対応済みだった「3日前リマインド専用
  スケジューラへの実送信配線」を、依然「次の課題」のまま記載し続けていた記載漏れ
  (フェーズ113・118・119・122等と同種のパターン)を発見・訂正した。
  `prototype/daily_scheduler.py`の`send_payment_failure_reminders()`が
  `run_daily_workshop_checks()`(Cloud Function G本体)から呼び出されるところまで
  実装・テスト済みであることを確認したうえで、該当箇所を打ち消し線化し、残るのは
  実LINE公式アカウント接続・実Cloud Scheduler構築・実オーナーLINEユーザーID設定という
  外部サービスへのアカウント作成・接続を伴う部分のみ(pending-approval.md 2026-09-15
  03:00 UTC記載の通りオーナー承認待ち)である旨を明記した。コード変更は無く、回帰確認
  としてventure全体12ファイル(`python3 prototype/run_all_tests.py`)・schema検証30件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計doc記載漏れの訂正のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回はサポート負荷
  軽減策(FAQ整備等)の具体的検討、他venture・アイデア領域の前進を優先候補とする。
- フェーズ125(2026-09-15 23:00 UTC): フェーズ124の「サポート負荷軽減策(FAQ整備等)の
  具体的検討」に対応した。course-set-pasha・aircon-pasha・line-reservation-aiには既に
  ある契約者向けセルフサービスFAQ(owner-operation-self-service-faq.md)が本venture
  には未整備だったこと(aircon-pashaフェーズ224「次のステップ候補」でも指摘済み)を
  受け、本venture版を新規作成した。他3ventureには無い本venture固有の機能(複数職人
  プランの共同利用・解約権限、ダウングレード時の余剰メンバー扱い、契約者(工房主)
  譲渡)を中心にQ1〜Q8の8項目を既存設計docを参照根拠に整理した。これで4venture全ての
  契約者向けセルフサービスFAQ初回整理が完了した。コード変更は無く、回帰確認として
  venture全体12ファイル(`python3 prototype/run_all_tests.py`)・schema検証30件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要なドキュメント新規作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は本FAQへの導線
  設計(line-reservation-aiのowner-faq-routing-design.md相当の横展開)、または他venture・
  アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-15 23:00 UTC(フェーズ125: 契約者向けセルフサービスFAQ
  〈owner-operation-self-service-faq.md〉を新規作成し、4venture全ての横展開を完了。
  コード変更は無し)
- フェーズ126(2026-09-15 20:00 UTC): フェーズ125「次のステップ候補」だった本FAQへの
  導線実装に着手した。line-reservation-aiのowner-faq-routing-design.md(トークルームで
  「FAQ」→「Q1」〜「Q8」送信によりその場で内容を返信するコマンド方式)を本venture向けに
  横展開し、owner-faq-routing-design.md新規作成・`prototype/owner_faq_router.py`新規実装
  (LLM呼び出し・LINE送信を持たない純粋関数)を行った。本venture固有の複数職人プラン構造
  を踏まえ、判定対象は`workshop_store.get_contractor_user_id(workshop_id)`と一致する
  契約者本人のみに絞り、共同利用者(メンバー)からの同一文言送信は影響を受けず従来通り
  依頼メモとして処理される設計とした。`cloud_function_webhook.py`の
  `process_message_event()`に`_maybe_handle_owner_faq_command()`を新設して配線した
  (連携済み分岐で`process_memo_event()`へ委譲する前に判定)。テストは
  `prototype/test_owner_faq_router.py`新規作成(純粋関数の単体テスト)、
  `prototype/test_cloud_function_webhook.py`に3件追加(契約者のFAQトリガー・Q7照会・
  契約者以外からのFAQ送信が通常の生成フローにフォールバックすること)し、回帰確認として
  venture全体13ファイル(`python3 prototype/run_all_tests.py`)・schema検証30件
  (`python3 schema/validate_test_cases.py`)いずれもパス(新規追加分以外は変更前と同じ
  結果)を確認した。実LINE公式アカウント接続前でも机上実装・テストまで完結できるため
  外部サービスへの公開・アカウント作成等は発生しておらずpending-approval.mdへの追記は
  なし。次回はcourse-set-pasha・aircon-pashaへの同種導線の横展開、または他venture・
  アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-15 20:00 UTC(フェーズ126: 契約者向けセルフサービスFAQへの導線
  〈owner-faq-routing-design.md・prototype/owner_faq_router.py〉を新規実装し、
  line-reservation-aiに続き2venture目の横展開を完了)
- フェーズ127(2026-09-17 20:00 UTC): フェーズ126・owner-faq-routing-design.md 6節が
  残課題として挙げていた「『FAQ』という単語自体を契約者が思いつかない可能性があり、
  コマンドの存在をどう周知するか」に対応した。course-set-pasha・aircon-pashaと同じ
  考え方で、本venture固有の唯一確実な初回導線であるウェルカムメッセージ
  (`format_follow_welcome_message()`)の末尾に「トークルームで『FAQ』と送信すると
  いつでもご案内します。」の一文を追記した。既存の連携コード案内部分の文言・処理は
  変更していない。`test_cloud_function_webhook.py`に、ウェルカムメッセージ本文が
  実際に`owner_faq_router.is_owner_faq_menu_trigger()`のトリガーキーワード「FAQ」と
  一致することを検証するテストを1件追加し、venture全体98件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証30件
  (`python3 schema/validate_test_cases.py`)いずれもパスを確認した(このフェーズは
  コード・設計doc更新時に本README「最終更新」マーカーの追記漏れがあったため、
  本フェーズ128にて事後反映した)。承認不要なドキュメント更新・コード実装のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は発生しておらず
  pending-approval.mdへの追記なし。
- 最終更新: 2026-09-17 20:00 UTC(フェーズ127: ウェルカムメッセージ末尾へのFAQコマンド
  周知文言追記により、line-reservation-ai・course-set-pashaに続き3venture目の周知対応を
  完了)
- フェーズ128(2026-09-17 22:00 UTC): 他3venture(aircon-pasha・course-set-pasha・
  line-reservation-ai)には既にあるが本venture未着手だったdeployment-runbook.md自体の
  cross-venture parityギャップに対応した。aircon-pasha/deployment-runbook.mdの構成を
  踏襲しつつ、本venture固有の(1)課金・生成回数上限管理がworkshop単位である点
  (tech-stack.md・subscription-billing-data-model-design.md・usage-counter-workshop-
  key-design.md)、(2)複数職人プランの共同利用・ダウングレード時の余剰メンバー扱い
  (craftsman-account-linking-design.md・downgrade-excess-member-handling-design.md)、
  (3)Webhook受信用+日次スケジューラ用の2 Cloud Function構成(daily-scheduler-design.md・
  payment-failure-dunning-design.md、line-reservation-aiのFunction Cと同種で
  course-set-pasha・aircon-pashaの単一関数構成とは異なる)を反映した手順書を新規作成した。
  GCPプロジェクト作成・LINE公式アカウント開設・Stripeアカウント接続はいずれも
  アカウント作成・支払いを伴うためオーナー承認待ちの範囲であり、本フェーズは実行手順の
  机上整理のみに留めた(いずれのステップも未実行)。コード変更は無く、回帰確認として
  venture全体13ファイル(`python3 prototype/run_all_tests.py`)・schema検証30件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要なドキュメント新規作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は
  line-reservation-aiへの同種FAQ導線周知の横展開の要否確認、または他venture・
  アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-17 22:00 UTC(フェーズ128: deployment-runbook.mdを新規作成し、
  4venture全てでデプロイ手順書のcross-venture parityを達成。コード変更は無し)
- フェーズ129(2026-09-18 00:00 UTC): 他3venture(aircon-pasha・course-set-pasha・
  line-reservation-ai)には既にあるが本venture未着手だった`PortalLinkProvider`
  (Stripe Customer Portalリンク発行)の実装本体のcross-venture parityギャップに対応した。
  `prototype/cloud_function_webhook.py`のPortalLinkProvider Protocol自体は既存だったが、
  実装本体(`InMemoryPortalLinkProvider`スタブ以外)が無く、payment-failure-dunning-
  design.md・subscription-cancellation-scheduled-notification-design.mdが「未実装のため
  URLを差し込まない」前提としていた。本venture固有の事情として、`stripe_customer_id`が
  `user_id`ではなく`craftsman_workshop/{workshop_id}`側のフィールドであるため
  `user_id→workshop_id→stripe_customer_id`の2ホップ解決が必要な点、Billing Portalは
  checkout-initiation-flow-design.mdのCheckout Session開始と同じ「契約者本人限定」の
  権限モデルを適用すべき点(共同利用メンバーは対象外)が他venture3件との構造的な違いで
  あり、portal-session-provider-design.md(新規)に設計した上で`prototype/portal_session.py`
  に`StripePortalLinkProvider`を新規実装した。`prototype/test_portal_session.py`を新規
  作成(17件、契約者一致/不一致・workshop未紐付け・stripe_customer_id未登録・デフォルト
  session_creator未実装の各ケースを検証)し、payment-failure-dunning-design.md 6節の該当
  残課題を解消済みへ更新した。実`stripe.billing_portal.Session.create()`呼び出しへの
  差し替え・通知文言へのURL差し込み自体は、引き続き実Stripeアカウント接続(オーナー承認待ち、
  pending-approval.md参照)後の課題として残る(portal-session-provider-design.md 5節)。
  回帰確認としてventure全体14ファイル(`python3 prototype/run_all_tests.py`)・schema検証
  30件(`python3 schema/validate_test_cases.py`)いずれもパス(新規追加分以外は変更前と
  同じ結果)を確認した。承認不要なドキュメント新規作成・コード実装のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。次回は実Stripe接続後のURL差し込み配線、または他venture・アイデア領域の前進を
  優先候補とする。
- 最終更新: 2026-09-18 00:00 UTC(フェーズ129: PortalLinkProviderの実装本体
  〈portal-session-provider-design.md・prototype/portal_session.py〉を新規実装し、
  4venture全てでBilling Portalリンク発行実装のcross-venture parityを達成)
- フェーズ130(2026-09-18 定例更新): cross-venture-support-cost-comparison.md(フェーズ123)
  「結論・示唆」が「次の課題」として残していたFAQ整備等のサポート負荷軽減策について、
  2026-09-15〜18の定例更新で4venture全て(course-set-pasha・kura-pasha・aircon-pasha・
  line-reservation-ai)へのowner-faq-routing-design.md実装が既に完了していることを確認し、
  「FAQ自己解決導線の横展開完了と対応コストへの示唆」節を新設した。各ventureのFAQ項目数
  (course-set-pasha 6件・aircon-pasha 7件・line-reservation-ai 7件・kura-pasha 8件)を
  整理した上で、FAQがカバーする範囲(通常の使い方・料金プラン・解約方法の再質問)と
  カバーしない範囲(契約者譲渡・複数職人メンバー整理等、本人確認や個別状況判断を要する
  問い合わせ)を切り分け、「通常の使い方の再質問」区分の3〜5割程度が自己解決に置き換わる
  と仮定しても比較表の月次対応コスト全体を大きく動かす水準ではないという粗い見立てを
  記録した(根拠のない仮定値であることを明記)。比較表・順位付け自体は実測データが無いため
  据え置いた。コード変更は無く、回帰確認としてventure全体98件(`python3 -m unittest
  discover -s prototype -p "test_*.py"`)・schema検証30件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。承認不要な
  ドキュメント更新のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回
  発生していないためpending-approval.mdへの追記なし。次回は実測データが得られるまでの間、
  他venture・アイデア領域の前進を優先候補とする。
- フェーズ131(2026-09-18 定例更新): course-set-pashaフェーズ221が発見した「オーナー向け
  FAQコマンドのトリガー『FAQ』・項目コード『Q1』〜の判定が半角英数字の入力のみを想定して
  おり、全角入力(『ＦＡＱ』『Ｑ１』)では一致しない」という想定漏れについて、
  line-reservation-aiフェーズ続き240に続き、本venture分の横展開を実施した。
  `_normalize_command_text()`(`unicodedata.normalize("NFKC", text)`を`strip().upper()`
  の前段に追加)を新設し、`is_owner_faq_menu_trigger()`・`match_owner_faq_item_code()`
  から呼び出すよう変更した。`prototype/test_owner_faq_router.py`に全角入力のテストを
  2件追加し、owner-faq-routing-design.md 7節に記録した。回帰確認としてventure全体100件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`、98件→100件)・schema検証
  30件(`python3 schema/validate_test_cases.py`)いずれもパスを確認した。承認不要な
  コード実装・ドキュメント更新のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。残るaircon-pashaへの
  同種横展開は次回ローテーション時の課題とした。
- 最終更新: 2026-09-18 定例更新(フェーズ131: オーナー向けFAQコマンドのトリガー・項目
  コード判定に全角入力対応〈NFKC正規化〉を追加。course-set-pashaフェーズ221の
  cross-venture横展開。テスト2件新規追加、venture全体100件・schema検証30件いずれも
  パス)
- フェーズ132(2026-09-18 16:00 UTC定例更新): 2件の記載漏れ(古い記載の訂正)を解消
  した。(1)owner-operation-self-service-faq.md「未検証の仮説」節が、フェーズ126で
  owner-faq-routing-design.mdとして実装済みのFAQ導線(トークルームで「FAQ」送信→
  Q1〜Q8返信)を「未設計」のままと記載していた(フェーズ125作成時点の記載が
  フェーズ126実装後も更新されていなかった)ため、導線実装済みである旨と、真に未検証
  なのは支援コスト削減効果の実測データである旨に訂正した。(2)owner-faq-routing-
  design.md 7節が、全角入力(NFKC正規化)対応の横展開について「残るaircon-pashaへの
  同種横展開のみが未対応」と記載していたが、aircon-pashaフェーズ229(2026-09-18
  13:00 UTC)で既に対応済みであることを確認し、4venture全ての対応完了へ訂正した。
  いずれもコード変更は無く、回帰確認としてventure全体100件(`python3 -m unittest
  discover -s prototype -p "test_*.py"`)・schema検証30件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要なドキュメント記載訂正のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は他venture・
  アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-18 16:00 UTC(フェーズ132: owner-operation-self-service-faq.md・
  owner-faq-routing-design.mdに残っていた2件の記載漏れ〈FAQ導線実装済みの記載漏れ、
  aircon-pashaの全角入力対応完了の記載漏れ〉を訂正。コード変更は無く回帰確認のみ)
- フェーズ133(2026-09-18 20:00 UTC定例更新): pricing-plan.md「次のステップ候補」筆頭が
  「llm-api-cost-estimate.md相当の原価試算(本venture未実施)」としていたのを受け、
  本venture分を新規作成しようと着手したところ、`ventures/kura-pasha/llm-api-cost-
  estimate.md`が2026-09-06時点で既に作成済みであることを発見した(pricing-plan.mdの
  当該記載がフェーズ106前後の作成後に更新されず古いままだった、フェーズ84/85等と同種の
  記載漏れ)。既存のllm-api-cost-estimate.mdの内容を確認したところ、本venture固有の
  試算(シナリオA/B、Sonnet 5・Opus 5・Haiku 4.5別、最も保守的な組み合わせでも最安の
  従量単価150円に対し約5.7%にとどまるとの結論)・低頻度利用ゆえプロンプトキャッシュの
  効果が限定的との留意事項まで既に網羅済みで、内容自体に不足は無いことを確認した。
  pricing-plan.md「未検証の仮説」「次のステップ候補」の該当記載を、既に作成済みである
  旨へ訂正した。ファイルの新規作成は行わず(誤って重複作成しかけたが、既存ファイルを
  上書きする前に発見し原状復帰した)、コード変更も無く、回帰確認としてventure全体100件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証30件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要なドキュメント記載訂正のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回は対象候補
  (実在の鞍職人・馬具師)のロングリスト作成、または他venture・アイデア領域の前進を
  優先候補とする。
- 最終更新: 2026-09-18 20:00 UTC(フェーズ133: pricing-plan.mdが「本venture未実施」と
  古いまま記載していたllm-api-cost-estimate.mdが実際は2026-09-06作成済みだったことを
  発見し記載を訂正。ファイル内容自体は既に十分だったため新規作成はせず、コード変更も
  無く回帰確認のみ)
- 最終更新: 2026-09-18 22:00 UTC(フェーズ134: aircon-pashaのG8_busy_season_grumble_not_
  cancellation(フェーズ230)・course-set-pashaのCI6_busy_season_grumble_not_cancellation
  (フェーズ続き)と対になる、本venture厳守事項7a(iii)版の境界ケース(契約継続・解約の
  いずれにも触れない、修理依頼の立て込みを愚痴る表現がstatus=generatedに帰着することを
  固定するサンプル)をschema/validate_test_cases.pyにC4として新規追加し、cross-venture
  横展開した。schema検証31件(30件→31件)・venture全体100件いずれもパス。承認不要な
  ドキュメント・サンプル追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等
  は今回発生していないためpending-approval.mdへの追記なし。)
- フェーズ135(2026-09-18 23:00 UTC定例更新): initial-contact-message-draft.md
  (2026-09-06 18:00 UTC作成)の「次にやること(候補)」に残っていた2項目の記載漏れを
  発見・訂正した。(1)「customer-interview-design.md相当の質問項目リストを作成する」は
  同日後続フェーズ(19:00 UTC)で既にcustomer-interview-design.md(全13問)として作成
  済みだったにもかかわらず未反映のまま残っていた。(2)「ジャパンギャロップスインポーター
  の追加確認」も、candidate-longlist-draft.md第六弾(22:00 UTC)で既に追加確認済み
  (公開情報のみでは判断できず、優先順位1・2へのヒアリング実施後に改めて判断する方針で
  保留を維持)だったにもかかわらず、あたかも未着手であるかのような書きぶりが残っていた。
  いずれもフェーズ133と同種の「後続ドキュメントで前提が解消されたにもかかわらず起点側の
  記載が未更新のまま残る」cross-document parityの記載漏れパターン。文面草案・未確定事項
  本体の内容変更は無く、コード変更も無いため、回帰確認としてventure全体100件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証31件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要なドキュメント記載漏れの訂正のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。次回は
  ヒアリング実施の承認状況(2026-09-11 04:00 UTC記録分)の確認、または他venture・
  アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-18 23:00 UTC(フェーズ135: initial-contact-message-draft.mdの
  「次にやること」に残っていた2件の記載漏れ〈質問項目リスト作成・JGI追加確認、いずれも
  他ファイルで解消済み〉を訂正。コード変更は無く回帰確認のみ)
- フェーズ136(2026-09-19 04:00 UTC定例更新): aircon-pashaのG9_busy_grumble_not_
  checkout_intent(フェーズ231、2026-09-19 01:00 UTC)と対になる、本venture厳守事項
  7b(iii)版の境界ケースをschema/validate_test_cases.pyにC5_busy_grumble_not_checkout_
  intentとして新規追加し、cross-venture横展開した。フェーズ134で追加したC4が7a(iii)
  (解約意図との混同防止)側を固定したのに対し、本ケースは7b(iii)側で、有料プラン
  (複数職人プラン等)の申込・開始のいずれにも触れず「プラン」の語を含む繁忙の愚痴
  (例:「最近注文が多くてプランのことなんて考える暇もない」)が続いても、status=
  generatedとして通常どおり受注メモの出力を行い、checkout_noticeはNoneのままとなる
  ことを固定した。実LLMがこの区別を実際に守れるかは、他の厳守事項7b境界の検証と同様に
  実LLM接続後(オーナー承認待ち)の検証課題として引き続き残る。schema検証32件
  (31件→32件)・venture全体100件(`python3 -m unittest discover -s prototype -p
  "test_*.py"`)いずれもパス。承認不要なドキュメント・サンプル追加のみで、外部サービス
  への公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.md
  への追記なし。次回はcourse-set-pasha側にも同種7b(iii)境界(checkout intent版)の
  横展開が未着手か確認する、または他venture・アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-19 04:00 UTC(フェーズ136: aircon-pashaのG9_busy_grumble_not_
  checkout_intentと対になる、本venture厳守事項7b(iii)版の境界ケースをC5として新規
  追加。schema検証32件〈31件→32件〉・venture全体100件いずれもパス。コード実装は
  テストフィクスチャ追加のみ)
- フェーズ137(2026-09-19 08:00 UTC定例更新): 直前フェーズ(aircon-pashaフェーズ232、
  2026-09-19 07:00 UTC)で「本venture(prototype/workshop_linking.py)にも同型で
  未対応のまま残っている」と確認・記録されていた、連携コード・招待コードのNFKC全角
  入力対応を本venture側で実装した。course-set-pasha/aircon-pashaのuser_id_linking.py
  で先行実装済みのパターン(`unicodedata.normalize("NFKC", ...)`を`strip().upper()`の
  前段に適用)を、`resolve_linking_code()`(design 2節、workshop新規作成用)・
  `resolve_invite_code()`(design 11.2節、既存workshopへのメンバー追加用)の2箇所に
  同様に適用した。両コードともLINEトーク上での手入力を前提とし、コードのアルファベットが
  英数字のみ(`_CODE_ALPHABET`)である点も共通のため、正規化の妥当性は先行実装と同一の
  理由による。テスト2件追加(全角入力を受理することを確認、それぞれ1件ずつ)、venture
  全体101件→103件(`python3 -m unittest discover -s prototype -p "test_*.py"`
  および`python3 prototype/run_all_tests.py`、14ファイルいずれもOK)・schema検証32件
  いずれもパス(schema側は本修正の対象外のため件数変化なし)を確認した。承認不要な
  コード修正・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回はline-reservation-ai
  (LIFF方式のため今回のNFKC対応は非該当と既に確認済み)以外に本パターンの横展開漏れが
  残っていないか、または他venture・アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-19 08:00 UTC(フェーズ137: aircon-pashaフェーズ232が発見した
  未対応箇所〈workshop_linking.pyのresolve_linking_code()・resolve_invite_code()〉に
  NFKC全角入力対応を横展開。テスト2件追加〈101件→103件〉・schema検証32件いずれもパス)
- フェーズ138(2026-09-19 12:00 UTC定例更新): mvp-flow-draft.mdの棚卸しを行い、
  同ドキュメントの「残課題」節がフェーズ2〜4(2026-09-06)で既に解消済みの3項目
  (llm-system-prompt-draft.mdへの落とし込み、出力の構造化JSONフォーマット設計、
  区分ごとの出力2分岐ロジック)を未着手のまま記載し続けていたREADME記載漏れパターン
  (course-set-pashaフェーズ208・210・211等と同種)であることを発見し、各項目に
  解消済みフェーズ番号を追記して訂正した。判定ロジック・実装への変更は無く、回帰確認
  としてventure全体103件(`python3 -m unittest discover -s prototype -p "test_*.py"`)・
  schema検証32件いずれもパス(変更前と同じ結果)を確認した。承認不要なドキュメント
  記載漏れ訂正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生
  していないためpending-approval.mdへの追記なし。次回は他venture・アイデア領域の
  前進を優先候補とする。
- 最終更新: 2026-09-19 12:00 UTC(フェーズ138: mvp-flow-draft.mdの「残課題」節に
  残っていたフェーズ2〜4解消済み3項目の記載漏れを訂正。venture全体103件・schema検証
  32件いずれもパス、変更前と同じ結果)
- フェーズ139(2026-09-19 16:00 UTC定例更新): unfollow-billing-faq.md(フェーズ45、
  2026-09-08作成)の棚卸しを行い、3件の記載漏れ・事実誤りを発見・訂正した。(1)「前提の
  整理」節が「本venture自体、Stripe Webhook受信・PortalLinkProvider相当の実装がまだ
  無い段階であるため、検知バッチの設計はさらにその前提となるWebhook実装自体が整うまで
  着手できない」と記載していたが、Stripe Webhook受信(stripe-webhook-checkout-completed-
  design.md、フェーズ51、本節作成と同日中)・PortalLinkProvider相当の実装
  (portal-session-provider-design.md・`prototype/portal_session.py`のStripe
  PortalLinkProvider、フェーズ129)とも既に完了しており、フェーズ80・81の検知バッチ・
  オーナー通知実装ともあわせて前提が解消済みだった(フェーズ133・135・138と同種の
  cross-document parity記載漏れパターン)。(2)「文面の補足」節のFAQ返信テンプレート内
  「{Stripeカスタマーポータル URL}」プレースホルダの説明が同じくPortalLinkProvider未実装・
  Stripe Webhook未着手を理由としていたが、プレースホルダのまま残る理由は実装の有無では
  なく実Stripeアカウント接続待ち(オーナー承認待ち、pending-approval.md参照)のみである
  点に訂正した。(3)「今後の課題」がFAQ文面のlanding-page-copy-draft.mdへの反映について
  「同ファイル自体が本venture未作成のため」と記載していたが、確認したところ
  landing-page-copy-draft.mdは本ファイル作成(フェーズ45)より前のフェーズ17
  (2026-09-07 00:00 UTC)時点で既に新規作成済みであり、本ファイル作成時点からの事実
  誤りだったことが判明した(同ファイルのFAQセクションに本FAQ内容が未反映であること自体は
  現在も事実のため、反映自体は引き続き未対応の課題として残した)。いずれもコード変更は
  無く、回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype -p
  "test_*.py"`および`python3 prototype/run_all_tests.py`、14ファイルいずれもOK)・
  schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ
  結果)を確認した。承認不要なドキュメント記載訂正のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記
  なし。次回は同ファイル「未確定事項」3点目(craftsman-account-linking-design.mdの
  複数職人プラン共同利用者向け本人確認手段)の要確認状況の見直し、または他venture・
  アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-19 16:00 UTC(フェーズ139: unfollow-billing-faq.mdに残っていた
  3件の記載漏れ・事実誤り〈Stripe Webhook/PortalLinkProvider未実装記載〈フェーズ51・
  129で解消済み〉、landing-page-copy-draft.md未作成記載〈フェーズ17時点で既に作成済み〉〉
  を訂正。コード変更は無く回帰確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ140(2026-09-19 17:00 UTC、コミット69eeb29): フェーズ139「次回」で挙げた
  unfollow-billing-faq.md「未確定事項」3点目(複数職人プラン共同利用者向け本人確認手段)
  を見直した。旧文は「craftsman-account-linking-design.mdの契約者本人判定の仕組み自体が
  本venture未着手」としていたが、これは事実誤りだった。同ファイルの契約者本人判定
  (`contractor_user_id`と一致するuser_idのみに契約・解約操作権限を機械的に紐付ける仕組み)
  はフェーズ25〜26で既に設計・実装済みであり、共同利用者(`member_user_ids`)自身は
  そもそもStripe顧客・登録メールアドレスを持たず解約・請求操作の権限も一切持たない
  ことを確認した。これにより、(1)共同利用者からの問い合わせは常に契約者本人への
  取次ぎ案内で足り、共同利用者本人の身元確認は不要、(2)契約者本人を名乗る場合の確認は
  他venture3件と同水準の「登録メールアドレスの一致確認」で足りる、との結論に至り、
  「複数職人プラン固有の論点」節・「未確定事項」節の双方に反映してunfollow-billing-faq.md
  の未確定事項を解消した。判定ロジック・実装への変更は無く、回帰確認としてventure全体
  103件(`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証32件
  いずれもパス(変更前と同じ結果)を確認した。承認不要なドキュメント記載訂正のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。なお本フェーズの作業自体はコミット69eeb29
  (2026-09-19 17:05 UTC)で実施済みだったが、README反映が漏れていたため本エントリとして
  事後反映した(course-set-pashaフェーズ220等と同種のREADME記載漏れパターン)。次回は
  他venture・アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-19 17:00 UTC(フェーズ140: unfollow-billing-faq.mdの「未確定事項」
  3点目〈複数職人プラン共同利用者向け本人確認手段〉を解消。共同利用者は解約権限を持たず
  常に契約者への取次ぎで足りる、契約者本人確認は他venture同水準のメール一致確認で足りると
  結論。コード変更は無く回帰確認のみ、venture全体103件・schema検証32件いずれもパス。
  作業自体はコミット69eeb29で実施済みだったREADME記載漏れの事後反映)
- フェーズ141(2026-09-20 02:00 UTC定例更新): landing-page-copy-draft.md(フェーズ17、
  2026-09-07作成)の「次のステップ候補」を棚卸ししたところ、2点が既に対応済みのまま
  未着手として記載され続けていたcross-document parityの記載漏れを発見・訂正した。
  (1)「legal-notices-draft.md相当の作成」はフェーズ19(2026-09-07 02:00 UTC)で
  legal-notices-draft.mdとして既に作成済み。(2)「LPコピーに対応するワイヤーフレームの
  作成」も2026-09-11 20:00 UTCでlanding-page-wireframe.mdとして既に作成済み(他venture
  同様cross-venture parityのギャップに対応する形で新規作成されていた)。3点目の
  「customer-interview-design.mdのヒアリング結果を踏まえた課題提起セクションの見直し」は
  ヒアリング実施自体が2026-09-11 04:00 UTC記録分のオーナー承認待ちのままのため、引き続き
  未着手として残した。コピー文言本体の内容変更は無く、コード変更も無いため、回帰確認として
  venture全体103件(`python3 -m unittest discover -s prototype -p "test_*.py"`)・
  schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を
  確認した。承認不要なドキュメント記載漏れの訂正のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。次回は
  他venture・アイデア領域の前進、または本ventureの他ドキュメントの棚卸しを優先候補とする。
- 最終更新: 2026-09-20 02:00 UTC(フェーズ141: landing-page-copy-draft.mdの「次のステップ
  候補」に残っていた2件〈legal-notices-draft.md作成・LPワイヤーフレーム作成〉が、実際には
  それぞれフェーズ19・2026-09-11 20:00 UTCで作成済みだった記載漏れを発見・訂正。コード
  変更は無く回帰確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ142(2026-09-20 08:00 UTC定例更新): course-set-pashaフェーズ230(2026-09-20
  06:00 UTC)が「本venture・aircon-pasha・kura-pasha共通の未確定事項」として横展開候補に
  挙げていた、決済代行サービス側の都度課金(従量課金)対応可否の調査結果を本ventureへ
  反映した。pricing-plan.mdの「未確定事項」(従量課金には決済代行サービス側での都度課金
  対応可否確認が必要)を、course-set-pashaが調査したStripe BillingのMeters機能(利用の
  都度Meter Eventを送信すると請求サイクル終了時に自動集計・請求書反映する仕組み)により
  技術的に対応可能であることを確認した結論を根拠に解消済みへ更新した。コード変更は無く、
  回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype -p
  "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス
  (変更前と同じ結果)を確認した。承認不要なドキュメント記載更新のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。次回は他venture・アイデア領域の前進を優先候補とする。
- 最終更新: 2026-09-20 08:00 UTC(フェーズ142: course-set-pashaが調査したStripe Billing
  Meters機能による都度課金対応可否の結論をpricing-plan.mdの「未確定事項」に反映し解消済みへ
  更新。コード変更は無く回帰確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ143(2026-09-20 09:00 UTC定例更新): market-research.md「残課題」に残っていた
  「対象候補のロングリスト作成」に着手した。WebSearchで実在の鞍職人・馬具職人を再検索し、
  新規候補として日野純一さん・菜月さん(北海道、2014年開業の個人〜夫婦経営の馬具職人、
  修理・カスタマイズ対応)を追加確認した。あわせてグレイズブラン(革製品修理専業店、
  馬具クリーニングも扱うが新規制作は対象外の見込み)を革研究所と同種の参考情報として、
  株式会社日本馬事普及・CAVALLOを既製品販売中心と見受けられるためソメスサドルと同様に
  直接のターゲット候補から除外する暫定判断を記録した。実際の連絡先(電話・メール
  アドレス等)の収集・記録、候補への連絡・ヒアリング依頼はオーナー承認が必要なアクション
  のため、本フェーズでは事業者名・業態の確認までにとどめ、連絡先情報は記載していない
  (新規のpending-approval.md追記も無し、既存の2026-09-11 04:00 UTC記録分の範囲内)。
  ロングリスト自体は候補を発見次第拡充していく継続課題として残す。コード変更は無く、
  回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype -p
  "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス
  (変更前と同じ結果)を確認した。承認不要な市場調査・ドキュメント追記のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。次回は他venture・アイデア領域の前進、またはロング
  リストの他候補発見を優先候補とする。
- 最終更新: 2026-09-20 09:00 UTC(フェーズ143: market-research.mdの「対象候補のロング
  リスト作成」に着手し、WebSearchで新規候補(日野純一さん・菜月さん)を追加確認、参考
  情報・除外候補も整理。コード変更は無く回帰確認のみ、venture全体103件・schema検証32件
  いずれもパス)
- フェーズ144(2026-09-20 10:00 UTC定例更新): market-research.mdのロングリスト作成を継続し、
  前回(2026-09-13 08:00 UTC)「職人による個別修理受注か完成品販売中心かスニペットのみ
  では未判別」として残していた株式会社渡辺馬具をWebSearchで再確認した。公式サイトに
  「競馬用・競技用馬具販売 通販 馬具修理専門店」と明記されており、通販主軸としつつ独立
  した修理専用ページも持つ、既製品販売中心の事業者と個人職人の中間的な業態と判断し、
  直接のターゲット候補にはせず革研究所・グレイズブランと同種の参考事業者として整理した。
  あわせて新たに発見した「馬具職人工房」(Instagram・楽天/Yahoo!出店)は、出品商品が
  スマートフォンケース等の革小物中心で鞍・馬具本体の受注制作・修理を手掛けている確証が
  得られなかったため、ロングリストには加えず要再確認の参考情報にとどめた。実際の連絡先
  収集・候補への連絡はオーナー承認が必要なアクションのため未着手のまま。コード変更は
  無く、回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype -p
  "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス
  (変更前と同じ結果)を確認した。承認不要な市場調査・ドキュメント追記のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。次回も他venture・アイデア領域の前進、またはロング
  リストの他候補発見を優先候補とする。
- 最終更新: 2026-09-20 10:00 UTC(フェーズ144: market-research.mdのロングリスト作成を
  継続。未判別だった渡辺馬具を通販主軸の参考事業者として整理、新規発見の「馬具職人工房」
  は要再確認にとどめた。コード変更は無く回帰確認のみ、venture全体103件・schema検証32件
  いずれもパス)

- フェーズ145(2026-09-20 11:00 UTC定例更新): market-research.mdのロングリスト作成を
  さらに継続し、WebSearchで「馬具店 鞍 修理 承ります 個人 職人 ブログ 乗馬クラブ」を
  再検索した。新規候補として、主業務は乗馬靴修理だが鞍のベルト部分の個別修理も手掛ける
  ベテラン職人「乗馬靴修理ヒロさん」(アメブロ)を発見し、既存候補(鞍・馬具の修理を
  主軸とする事業者)とは区別した「鞍付随部品・周辺用品を含む乗馬用品修理職人」の参考例
  としてロングリストに追加した。あわせて発見した「馬の鞍話」ブログは運営者が職人か
  乗馬愛好家個人かスニペットのみでは未判別のため要再確認にとどめた。実際の連絡先収集・
  候補への連絡はオーナー承認が必要なアクションのため引き続き未着手のまま。コード変更は
  無く、回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype -p
  "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス
  (変更前と同じ結果)を確認した。承認不要な市場調査・ドキュメント追記のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。次回も他venture・アイデア領域の前進、またはロング
  リストの他候補発見を優先候補とする。
- フェーズ146(2026-09-20 12:00 UTC定例更新): market-research.mdの残課題だった
  「要再確認」候補の再調査に着手し、前回(フェーズ144)要再確認にとどめていた
  「馬具職人工房」をWebSearchで「馬具職人工房 Creema 鞍 馬装品 オーダーメイド」と
  再検索した。楽天・メルカリでの出品は従来どおり革小物中心だったが、Creemaの
  ギャラリー自己紹介文で「乗馬用・競馬用の馬具、馬装品、馬車道具…等を手掛け、
  オーダーメイドのご要望に対応」との記載を新たに確認した。実際の鞍本体の制作・
  修理実例(写真付き納品事例等)はスニペットからは依然確認できないため、既存の
  主軸候補(ライディングショップ池上等)と同列には扱わず、「鞍・馬装品のオーダー
  メイド対応を謳う副次候補」としてロングリストに参考記載するに格上げした。実際の
  連絡先収集・候補への連絡はオーナー承認が必要なアクションのため引き続き未着手の
  まま。コード変更は無く、回帰確認としてventure全体103件(`python3 -m unittest
  discover -s prototype -p "test_*.py"`)・schema検証32件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な市場調査・ドキュメント追記のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
  次回も他venture・アイデア領域の前進、またはロングリストの他候補発見を優先候補と
  する。
- 最終更新: 2026-09-20 12:00 UTC(フェーズ146: market-research.mdの「要再確認」
  候補だった「馬具職人工房」を再調査し、Creema自己紹介文で馬装品・オーダーメイド
  対応の記載を確認、「副次候補」としてロングリストに格上げ記載。コード変更は無く
  回帰確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ147(2026-09-20 13:00 UTC定例更新): market-research.mdのロングリスト
  作成をさらに継続し、WebSearchで「鞍職人 馬具修理 個人 承ります オーダーメイド
  ブログ 乗馬」を再検索した。既存候補(乗馬靴修理ヒロさん、馬の鞍話、ライディング
  ショップ池上、グレイズブラン、エクウスワールド)は状況の変化なし。新たに発見
  した「JODHPURS(ジョッパーズ)」(株式会社ワールドマーケット運営)・「ボロ
  ライディングショップ(BORO)」(有限会社、東京都練馬区)はいずれも輸入・通販
  中心の法人であり、個人職人による受注制作・修理という本venture対象の業態とは
  異なると判断したため、ソメスサドル・CAVALLO等と同種の除外候補(参考事業者)
  として整理した。実際の連絡先収集・候補への連絡はオーナー承認が必要なアクション
  のため引き続き未着手のまま。コード変更は無く、回帰確認としてventure全体103件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を
  確認した。承認不要な市場調査・ドキュメント追記のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。次回も他venture・アイデア領域の前進、またはロングリストの他候補発見を
  優先候補とする。
- 最終更新: 2026-09-20 13:00 UTC(フェーズ147: market-research.mdのロングリスト
  作成を継続。新規発見の「JODHPURS」「ボロライディングショップ」はいずれも輸入・
  通販中心の法人と判明したため除外候補として整理。コード変更は無く回帰確認のみ、
  venture全体103件・schema検証32件いずれもパス)
- フェーズ148(2026-09-20 15:00 UTC定例更新): market-research.mdのロングリスト
  作成をさらに継続し、WebSearchで「鞍 修理 承ります 個人 職人 手縫い 馬具
  ブログ」「馬具 鞍 修理 個人事業主 工房 ホームページ 見積もり 依頼」を再検索
  した。既存候補(ソメスサドル・Apion・ライディングショップ池上・グレイズ
  ブラン・馬の鞍話・levol等)は状況の変化なし。新たに発見した「FREEWILL
  WORKS」(皮革衣料・皮革製品全般のサイズ直し・修理工房、馬具修理は取扱
  カテゴリの一つ)は、既出のグレイズブランと同種の「皮革製品修理業者が馬具
  修理も付随的に手掛けるパターン」に該当すると判断し、鞍・馬具の受注制作・
  修理を主軸とする既存候補とは区別した参考事業者としてロングリストに整理した。
  個人〜小規模の鞍・馬具専業職人の新規発見には至らなかった。コード変更は無く、
  回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype
  -p "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)
  いずれもパス(変更前と同じ結果)を確認した。承認不要な市場調査・ドキュメント
  追記のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生
  していないためpending-approval.mdへの追記なし。次回も他venture・アイデア
  領域の前進、またはロングリストの他候補発見を優先候補とする。
- 最終更新: 2026-09-20 15:00 UTC(フェーズ148: market-research.mdのロングリスト
  作成を継続。新規発見の「FREEWILL WORKS」は皮革製品修理業者が馬具修理も
  付随的に手掛けるパターンと判断し参考事業者として整理。コード変更は無く回帰
  確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ149(2026-09-20 16:00 UTC定例更新): market-research.mdが「要再確認」
  候補として残していた「馬の鞍話」(l-phoenix.sblo.jp)の運営者をWebSearchで
  再確認した。同ブログの記事副題から、運営元が「レザークラフト・フェニックス」
  (1926年創業・大阪なんばのレザークラフト材料店、革・金具・工具・教則本の
  販売が主軸)であることを確認し、既出のFREEWILL WORKS・グレイズブランと同種の
  「レザークラフト材料店・皮革製品修理業者が馬具修理の問い合わせに付随的に対応
  するパターン」の参考事業者として整理し直した(運営者不明という理由での要
  再確認は解消)。鞍・馬具の受注制作・修理を主軸とする既存の最優先候補(ライディング
  ショップ池上・Apion等)とは事業の重心が異なるため、ロングリストの最優先候補には
  加えない。個人〜小規模の鞍・馬具専業職人の新規発見には至らなかった。実際の連絡先
  収集・候補への連絡はオーナー承認が必要なアクションのため引き続き未着手のまま。
  コード変更は無く、回帰確認としてventure全体103件(`python3 -m unittest discover
  -s prototype -p "test_*.py"`)・schema検証32件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な市場調査・ドキュメント追記のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
  次回も他venture・アイデア領域の前進、またはロングリストの他候補発見を優先候補と
  する。
- 最終更新: 2026-09-20 16:00 UTC(フェーズ149: market-research.mdの「要再確認」
  候補だった「馬の鞍話」の運営者を再確認し、レザークラフト材料店「フェニックス」
  運営と判明。FREEWILL WORKS等と同種の参考事業者として整理し直した。コード変更は
  無く回帰確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ150(2026-09-20 19:00 UTC定例更新): 第144〜149弾でmarket-research.mdに
  分散していた「ロングリスト作成の継続」の探索結果(乗馬靴修理ヒロさん・馬具職人
  工房の格上げ・FREEWILL WORKS・馬の鞍話/フェニックス・JODHPURS・ボロライディング
  ショップの計5件)が、本来の正式な優先順位付け記録場所であるcandidate-longlist-
  draft.mdに統合されないまま2026-09-06 22:00 UTC(第六弾)以降更新が止まっていた
  cross-document parityのずれを発見し、candidate-longlist-draft.md第七弾として
  統合・反映した(優先順位自体〈1: ライディングショップ池上、2: エクウスワールド、
  候補継続: 馬具職人工房・Apion-leather craft lab、保留: ジャパンギャロップス
  インポーター、除外: LEVOL〉に変更は無し)。あわせてinterview-candidate-selection-
  criteria.md「未検討事項」に残っていた3項目(初回コンタクト文面草案作成、候補数
  拡充、ヒアリング対象目標合計の検討)が、実際にはいずれも他ドキュメントで対応済み・
  方針確定済みだった記載漏れを発見・訂正した。市場調査の方向性としては、個人〜小規模
  の鞍・馬具専業職人の新規発見が6フェーズ連続で得られていないため、次回以降は同種の
  WebSearchによるロングリスト拡充よりも他venture・アイデア領域の前進を優先候補とする。
  コード変更は無く、回帰確認としてventure全体103件(`python3 -m unittest discover -s
  prototype -p "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)
  いずれもパス(変更前と同じ結果)を確認した。承認不要なドキュメント整理・記載漏れ
  訂正のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生して
  いないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-20 19:00 UTC(フェーズ150: market-research.mdに分散していた
  ロングリスト探索結果をcandidate-longlist-draft.md第七弾に統合、interview-
  candidate-selection-criteria.mdの「未検討事項」3項目の記載漏れを訂正。優先順位・
  選定基準本体の変更は無し。コード変更は無く回帰確認のみ、venture全体103件・
  schema検証32件いずれもパス)
- フェーズ151(2026-09-20 23:00 UTC定例更新): フェーズ150の記録が「次回以降は
  ロングリスト拡充よりも他venture・アイデア領域の前進を優先候補とする」としていた
  ことを踏まえ、market-research.mdの追加探索ではなく、aircon-pasha/output-samples-
  validation.md・course-set-pasha/output-samples-validation.mdに相当する文書が
  本ventureにまだ存在していなかったcross-venture parityのギャップに着手した。
  schema/validate_test_cases.pyの正常系23件・ネガティブ9件(計32件)を1文書に
  まとめたoutput-samples-validation.mdを新規作成し、各ケースの想定シナリオ・
  検証結果・残る未検証事項(実LLM接続後の検証課題であるプロンプト遵守率・
  厳守事項7a(iii)/7b(iii)の境界誤検知防止等)を整理した。既存のllm-quality-
  verification-plan.md・llm-quality-verification-results-template.mdとの役割分担
  (本文書はスキーマ/cross-fieldレベルの机上検証結果、両文書は実LLM接続後の判定基準・
  記録先)も明記した。コード変更は無く、回帰確認としてventure全体103件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認
  した。承認不要な新規ドキュメント作成のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-20 23:00 UTC(フェーズ151: schema/validate_test_cases.pyの
  正常系23件・ネガティブ9件を1文書にまとめたoutput-samples-validation.mdを新規
  作成し、cross-venture parityのギャップを解消。コード変更は無く回帰確認のみ、
  venture全体103件・schema検証32件いずれもパス)
- フェーズ152(2026-09-21 03:00 UTC定例更新): support-cost-estimate.md(フェーズ121)
  「残課題」に残っていた「サポート対応の外部委託・セルフサービス化によるコスト削減
  余地は未検討」に、course-set-pashaフェーズ233の横展開として着手した。
  support-cost-selfservice-reduction.mdを新規作成し、既存資産(owner-operation-
  self-service-faq.mdの8問、onboarding-guide.md、landing-page-copy-draft.mdの
  FAQ4問)を棚卸しした。本venture固有の点として、契約者譲渡はcontractor-transfer-
  design.md等によりLINE公式アカウント上の申請〜確認〜完了/期限切れフロー自体が
  既に自動化されている点を踏まえ、フロー自動化+FAQ(Q7)の両輪で他項目より
  セルフサービス化効果が相対的に大きいと整理した。一方、landing-page-copy-draft.md
  のFAQに「単一プランかworkshop共有プランか」の選び方を案内する項目が無いギャップ、
  workshopメンバー招待手順の契約者向け平易な案内が未整備である点を新たに発見し
  残課題とした。コード変更は無く、回帰確認としてventure全体103件
  (`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認
  した。承認不要な新規ドキュメント作成のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-21 03:00 UTC(フェーズ152: support-cost-selfservice-
  reduction.mdを新規作成し、course-set-pashaフェーズ233の横展開としてサポート対応
  セルフサービス化の削減余地を検討。契約者譲渡フローの自動化+FAQの両輪という
  本venture固有の強みを整理する一方、プラン選択案内・招待手順案内の未整備という
  新規ギャップを発見。コード変更は無く回帰確認のみ、venture全体103件・schema検証
  32件いずれもパス)
- フェーズ153(2026-09-21 04:00 UTC定例更新): フェーズ152が残課題として残した
  「landing-page-copy-draft.mdのFAQに単一プランとworkshop共有プランの選び方の
  案内が無い」ギャップに対応した。pricing-plan.mdのプラン比較表(想定顧客像列・
  月間生成回数上限)を顧客向けの平易な文章に言い換え、FAQセクションに5問目
  (「ライト・スタンダード・複数職人プラン、どれを選べばよいですか?」)として
  追加した。あわせてsupport-cost-selfservice-reduction.md(フェーズ152)の残課題
  該当箇所に対応済みの取り消し線を付けた。もう一方の残課題(workshopメンバー招待
  手順の契約者向け案内)は本フェーズの範囲では未着手のまま残る。コード変更は無く、
  回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype -p
  "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれも
  パス(変更前と同じ結果)を確認した。承認不要な既存ドキュメントの追記のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- 最終更新: 2026-09-21 04:00 UTC(フェーズ153: landing-page-copy-draft.mdのFAQに
  プラン選択案内〈5問目〉を追加し、フェーズ152が発見したギャップの1点を解消。
  コード変更は無く回帰確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ154(2026-09-21 08:00 UTC定例更新): フェーズ153が「本フェーズの範囲では
  未着手のまま残る」としていたもう一方の残課題(workshopメンバー招待手順の契約者向け
  平易な案内が未整備)に対応した。craftsman-account-linking-design.md 5節・11節の
  招待コード発行〜転送〜解決フローの設計内容を顧客向けの平易な文章に言い換え、
  owner-operation-self-service-faq.mdにQ9(「複数職人プランで仲間の職人を招待したい
  (招待手順)」)として追加した。既存のQ4(共同利用時の解約権限)は招待後の運用
  ルールを扱うのに対し、Q9は「職人を追加したい」と送ってから招待コードを転送し
  相手が参加するまでの初回手順そのものを扱う点で役割を分担する。あわせて
  support-cost-selfservice-reduction.md「残課題」の該当箇所に対応済みの取り消し線を
  付けた。コード変更は無く、回帰確認としてventure全体103件(`python3 -m unittest
  discover -s prototype -p "test_*.py"`)・schema検証32件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な既存ドキュメントへの追記のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-21 08:00 UTC(フェーズ154: craftsman-account-linking-design.md
  5節・11節の招待コードフローを顧客向けに言い換え、owner-operation-self-service-
  faq.mdにQ9として追加。support-cost-selfservice-reduction.mdの残課題1点を解消。
  コード変更は無く回帰確認のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ155(2026-09-21 12:00 UTC定例更新): 4venture全て(course-set-pasha
  フェーズ233・kura-pashaフェーズ152・aircon-pashaフェーズ244・line-reservation-ai
  フェーズ続き255〜256)でsupport-cost-selfservice-reduction.mdの削減率試算が出揃った
  ものの、cross-venture-support-cost-comparison.md(フェーズ123、初回サポートコスト
  試算の横断比較)に相当する専用の比較ドキュメントがまだ無く、line-reservation-ai
  フェーズ続き256の4venture比較コメントが自ドキュメント内の追記に留まっていた
  cross-document parityのギャップを発見した。cross-venture-support-selfservice-
  reduction-comparison.mdを新規作成し、4venture分の継続対応削減率(course-set-pasha
  2割弱・kura-pasha契約者譲渡1/3程度/複数職人招待3〜4割・aircon-pasha約3割・
  line-reservation-ai約半減)を1つの比較表に集約した。削減率の楽観度合いに約2倍の
  開きがあること、kura-pashaのみ「フロー自体の自動化」(FAQでなく)を削減手段の
  主軸に据えている点が他3venture(FAQ・案内文書中心)と質的に異なることを観察として
  整理した。各venture固有の試算の前提・計算根拠自体は変更していない。コード変更は
  無く、回帰確認としてventure全体103件(`python3 -m unittest discover -s prototype
  -p "test_*.py"`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれも
  パス(変更前と同じ結果)を確認した。承認不要な新規ドキュメント作成のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- 最終更新: 2026-09-21 12:00 UTC(フェーズ155: cross-venture-support-selfservice-
  reduction-comparison.mdを新規作成し、4venture分のセルフサービス化削減率試算を
  1つの比較表に集約。削減率の楽観度合いの開き・kura-pasha固有の「フロー自動化」
  主軸の違いを観察として整理。コード変更は無く回帰確認のみ、venture全体103件・
  schema検証32件いずれもパス)
- フェーズ156(2026-09-21 16:00 UTC定例更新): unit-economics-estimate.md(フェーズ121)
  「残課題」1点目に残っていた「決済手数料4.3%〈基本手数料3.6%+Stripe Billing追加
  手数料0.7%〉はStripe公式の一次情報での確認が未実施」に再度着手した。WebSearchで
  「Stripe Japan 決済手数料」を検索し、PAY.JP・note.com(SaaS飯)・クラスメソッド
  DevelopersIO・enhanceit.jpの4件の独立した二次情報で「国内発行クレジットカード
  決済3.6%、Stripe Billing追加0.7%」の一致を再確認した。あわせてstripe.com/pricing・
  stripe.com/billing/pricingへのWebFetchによる一次情報直接確認を試みたが、本実行
  環境のネットワークegressポリシーでstripe.comドメイン自体がブロックされており
  取得不能(EGRESS_BLOCKED)だった。したがって一次情報確認は本フェーズでも未達成の
  まま残り、実装着手時に決済代行サービス選定と併せて本環境以外での確認が必要という
  結論に変更はない。コード変更は無く、回帰確認としてventure全体103件(`python3 -m
  unittest discover -s prototype -p "test_*.py"`)・schema検証32件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。承認
  不要な調査・既存ドキュメントへの追記のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-21 16:00 UTC(フェーズ156: 決済手数料4.3%について独立した二次
  情報4件の一致を再確認したが、stripe.com自体へのアクセスが本実行環境でブロックされ
  ており一次情報での確認は引き続き未達成であることを確認。コード変更は無く回帰確認
  のみ、venture全体103件・schema検証32件いずれもパス)
- フェーズ157(2026-09-21 20:00 UTC定例更新): llm-quality-verification-plan.md
  (フェーズ135)の判定基準表8行目(厳守事項8)が「post_generation_checks.py相当の
  絵文字パターン検出、本venture未実装分は本検証時に流用可否を確認」として残していた
  未実装項目に対応した。course-set-pasha/aircon-pashaのprototype/post_generation_
  checks.pyはsns_post/line_web_notice等その2venture固有のスキーマに紐づく実装のため
  単純な流用はできないと判断し、kura-pasha自身のschema/output.schema.jsonに合わせて
  prototype/post_generation_checks.pyを新規実装した。course-set-pashaのSNS投稿文向け
  絵文字ルール(1〜2個まで許容)とは異なり、本ventureは厳守事項8(絵文字は終始不使用)
  に合わせ全10種の出力本文(order_summary.body〜workshop_invite_notice.body)で
  絵文字ゼロを求めるcheck_no_emoji_anywhere()とした。あわせて、既存のvalidate_
  cross_field_rules()がstatus値に応じたフィールドのnull/非null依存関係(構造)のみを
  検証し本文テキストの内容自体は未検証だった間隙を埋める形で、(1)厳守事項6(会員管理
  等への不応答)の機械チェック化(check_no_out_of_scope_topics_in_generated_output）、
  (2)厳守事項4のcategory一致がフィールド値だけでなく本文の実際の記述(「修理」の
  言及有無)とも整合しているかの検証(check_delivery_notice_category_text_
  consistency、新規発見の追加チェック)、(3)厳守事項7a(iv)のポータルリンク・手続き
  完了文言の本文整合性検証(check_subscription_notice_consistency、course-set-pasha
  のPORTAL_KEYWORDSに本venture固有の実際の文言「リンク」を追加)、(4)(5)厳守事項
  7b(i)・7c(i)のincludes_checkout_url/includes_invite_codeが常にfalseである設計の
  本文側裏付け(実URL・招待コードらしき6文字トークンの不在確認、招待コードは
  craftsman-account-linking-design.md 2節・11.1節と同じ31種アルファベットの6文字
  仕様に合わせた正規表現とした)、をあわせて実装した。schema/validate_test_cases.pyの
  TEST_CASES(G1・G2・OOS1・C1〜C5・M1・M2・CT1・CT2・CTC1〜CTC3・CTE1・CO1〜CO3・
  WIR1・WIR2の21件)がいずれも新チェックに違反しないことを確認したうえで、各チェック
  関数の意図的な違反ケース(ネガティブテスト)をあわせてtest_post_generation_checks.py
  として新規作成した(24件)。llm-quality-verification-plan.mdの該当行も実装済みの
  状態に更新した。新規テスト24件追加、回帰確認としてventure全体127件(`python3
  prototype/run_all_tests.py`、103件→127件)・schema検証32件(`python3
  schema/validate_test_cases.py`)いずれもパスを確認した。実LLM呼び出しは行っておらず
  (APIキー取得はオーナー承認待ち、pending-approval.md参照)、機械チェック自体がLLMの
  厳守事項違反を確実に検出できるわけではないヒューリスティックである点はcourse-set-
  pasha/aircon-pashaの既存実装と同じ限界として残る。承認不要なコード実装・テスト
  追加・既存ドキュメントへの記載更新のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-21 20:00 UTC(フェーズ157: llm-quality-verification-plan.mdが
  未実装のまま残していたprototype/post_generation_checks.pyを本venture固有のschemaに
  合わせて新規実装〈絵文字ゼロ・会員等キーワード不在・category本文整合性・ポータル
  リンク整合性・checkout URL/招待コード不在の6チェック〉。新規テスト24件追加、
  回帰確認としてventure全体127件・schema検証32件いずれもパス)
- フェーズ158(2026-09-22 00:00 UTC定例更新): craftsman-account-linking-design.md
  11.3節「未検証・残課題」が「複数職人プランのmember_user_ids上限数は未確定、無制限の
  まま運用してよいか要検討、次の課題とする」として残したままだった記載が、実際には
  同ファイル11.7節(フェーズ102)で契約者含め5名を暫定上限として決定し
  `prototype/workshop_linking.py`の`MAX_MEMBER_COUNT`として実装済み(pricing-plan.mdにも
  反映済み)であることを発見・訂正した。あわせて11.4節(フェーズ98)の「人数上限は未着手
  のまま残す」という記載も、11.7節が後続フェーズで対応済みである旨を明記する形に訂正
  した。コード変更は無く、回帰確認としてventure全体127件(`python3 prototype/run_all_
  tests.py`)・schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス
  (変更前と同じ結果)を確認した。承認不要な既存ドキュメントの記載訂正のみで、外部
  サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。
- 最終更新: 2026-09-22 00:00 UTC(フェーズ158: craftsman-account-linking-design.md
  11.3節・11.4節に残っていた「member_user_ids上限数は未着手」という記載が、実際には
  11.7節〈フェーズ102〉で5名上限として決定・実装済みだった記載漏れを発見・訂正。
  コード変更は無く回帰確認のみ、venture全体127件・schema検証32件いずれもパス)
- フェーズ159(2026-09-22 04:00 UTC定例更新): support-cost-selfservice-reduction.md
  (フェーズ152)「残課題」に残っていた「他venture(aircon-pasha・line-reservation-ai)
  については両ventureでの同種の検討は未着手のまま残る」という記載が、実際には
  aircon-pashaフェーズ244(2026-09-21 09:00 UTC)・line-reservation-aiフェーズ続き
  255〜256(同日10:00〜11:00 UTC)で両venture固有のsupport-cost-selfservice-
  reduction.mdが既に作成済みであり、さらにフェーズ155(同日12:00 UTC)でcross-
  venture-support-selfservice-reduction-comparison.mdとして4venture分の横断比較
  まで完了済みだった記載漏れを発見・訂正した。本項目はフェーズ152作成時点では
  正しかったが、その後の他venture側の前進(フェーズ152より後)に記載更新が追いついて
  いなかったもの。コード変更は無く、回帰確認としてventure全体127件(`python3
  -m unittest discover -s prototype -p "test_*.py"`)・schema検証32件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な既存ドキュメントの記載訂正のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-22 04:00 UTC(フェーズ159: support-cost-selfservice-
  reduction.mdの残課題に残っていた「aircon-pasha・line-reservation-aiは両venture
  未着手」という記載が、実際にはフェーズ152より後の両venture側の前進(フェーズ244・
  続き255〜256)とフェーズ155の横断比較により既に解消済みだった記載漏れを発見・
  訂正。コード変更は無く回帰確認のみ、venture全体127件・schema検証32件いずれも
  パス)
- フェーズ160(2026-09-22 07:00 UTC定例更新): course-set-pashaフェーズ241
  (2026-09-22 05:00 UTC)が発見した「schema statusにフィールドを追加したまま返信文
  組み立て関数〈format_reply_text()〉への配線を忘れる」バグ(該当status受信時に
  `ValueError`で契約者への返信が失敗する)について、同フェーズが申し送っていた他
  venture横断確認のうち本venture分を実施した。craftsman-account-linking-design.md
  11.5節(フェーズ100)でschema拡張した`workshop_invite_request`/
  `workshop_invite_request_unclear`の2statusが、`cloud_function_webhook.py`の
  `format_reply_text()`に一度も分岐追加されないまま60フェーズ(フェーズ100〜159)
  残っていた同型のバグを発見した。`format_reply_text()`に
  `workshop_invite_notice.body`をそのまま返す分岐を追加して修正し、
  `test_cloud_function_webhook.py`に`test_process_memo_event_workshop_invite_
  request_returns_notice_body`・同`_unclear_`版の2件を新規追加した。詳細は
  craftsman-account-linking-design.md 11.11節参照。回帰確認としてventure全体
  (`python3 prototype/run_all_tests.py`、15ファイル全件)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(test_cloud_function_
  webhook.py単体はcheck()呼び出し343件、修正前比+2件)を確認した。承認不要な
  バグ修正・テスト追加のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。line-reservation-ai・
  aircon-pashaについては未確認のまま残っており、次回以降の課題とする。
- 最終更新: 2026-09-22 07:00 UTC(フェーズ160: course-set-pashaフェーズ241の
  申し送りを受け、format_reply_text()未配線バグの横断確認〈本venture分〉を実施。
  workshop_invite_request/workshop_invite_request_unclearの2statusが
  フェーズ100からformat_reply_text()に配線されないまま残っていたバグを発見・修正、
  テスト2件追加。venture全体15ファイル・schema検証32件いずれもパス。
  line-reservation-ai・aircon-pashaは未確認のまま次回以降の課題)
- フェーズ161(2026-09-22 11:00 UTC定例更新): フェーズ160が「line-reservation-ai・
  aircon-pashaについては未確認のまま残っており、次回以降の課題とする」としていた
  横断確認を実施した。aircon-pasha・course-set-pashaはいずれも本venture同様
  「LLM出力のstatus値1つを中央の`format_reply_text()`で分岐する」設計を採用しており、
  両venture共通のschema/output.schema.json status enum(generated/out_of_scope/
  insufficient_input/cancellation_intent/downgrade_intent/cancellation_unclear/
  checkout_intent/pricing_inquiry/checkout_intent_unclearの9種)を実際の
  `prototype/cloud_function_webhook.py`の`format_reply_text()`分岐と1件ずつ突き合わせた
  結果、両venture共9種全てが分岐済みで新たな未配線は発見されなかった(course-set-pasha
  フェーズ241・aircon-pashaフェーズ249でそれぞれ既に修正済みのため)。line-reservation-ai
  は他3venture(本venture・course-set-pasha・aircon-pasha)と異なり、単一の中央関数で
  status値を分岐する設計自体を採用しておらず、`engine.py`内で5種のintent
  (new_booking/cancel/change/faq/escalation)ごとに専用の`format_*_message()`系関数
  (`format_confirmation_message()`・`format_cancel_confirmed_message()`・
  `format_change_started_message()`・faq_segments処理・escalation処理等)を呼び出し元が
  直接呼び分ける構成のため、「schemaにフィールドを追加したのに中央分岐への配線を忘れる」
  という今回発見された不具合パターンはそのままの形では当てはまらないことを確認した。
  同種のリスクがあるとすれば5種のintentいずれかに対応する専用ハンドラ自体の未実装という
  より粗い粒度の欠落になるはずだが、5種いずれも対応する実装(`cancel_booking()`・
  `change_booking()`・faq_segments処理・escalation処理・通常予約確定フロー)が既に
  揃っていることを確認し、粗い粒度の欠落も見当たらなかった。以上によりフェーズ160の
  申し送り事項は解消済みとする。コード変更は無く、回帰確認として本venture全体
  (`python3 prototype/run_all_tests.py`、15ファイル)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な既存コードの監査・確認のみで、外部サービスへの公開・アカウント作成・
  支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-22 11:00 UTC(フェーズ161: フェーズ160が申し送った
  line-reservation-ai・aircon-pashaの横断確認を実施。aircon-pasha・course-set-pashaは
  status enum9種が`format_reply_text()`に漏れなく配線済みで新たな不具合は無し。
  line-reservation-aiは中央分岐方式を採用しておらずintentごとの専用関数呼び分け方式の
  ため同型のバグパターンはそのまま当てはまらないが、5種intent全てに対応実装済みで
  粗い粒度の欠落も無いことを確認。コード変更は無く回帰確認のみ、venture全体15ファイル・
  schema検証32件いずれもパス)
- フェーズ162(2026-09-22 16:00 UTC定例更新): 4venture(aircon-pasha・course-set-pasha・
  kura-pasha・line-reservation-ai)のventuresフォルダ内ファイル名を横断比較し、他3venture
  には存在するが本venture(kura-pasha)には同名ファイルが無い候補8件
  (checkout-session-plan-selection-design・prompt-caching-design・
  stripe-webhook-event-dispatch-design・stripe-webhook-http-entry-point-design・
  stripe-webhook-signature-verification-design・subscription-billing-cost-estimate・
  trial-end-scheduler-design・trial-start-anchor-decision)を抽出し、いずれも本venture
  固有の未着手課題(実装漏れ)ではなく、既存の別ファイルに統合済みの内容であることを
  1件ずつ確認した。具体的には、(a)署名検証・イベント種別ディスパッチ・HTTPエントリ
  ポイントの3ファイルは他venture(course-set-pasha・aircon-pasha)がフェーズ93〜95・
  125〜127で個別ファイルに分けて設計したのに対し、本ventureはフェーズ51作成の
  stripe-webhook-checkout-completed-design.mdで同じ範囲を1本化して設計しており、実装も
  `prototype/stripe_webhook.py`の`verify_stripe_signature()`・`receive_stripe_webhook()`
  (署名検証・イベントディスパッチ・HTTPエントリポイントを1関数に集約)として既に完了
  している、(b)trial-start-anchor-decisionはtrial-end-condition-design.md(フェーズ47)
  2節で本venture固有の結論(起点は「initial生成成功時」ではなく「workshop作成時」、
  他venture2件とは異なる結論に至った理由も含む)として既に確定済み、(c)prompt-caching-
  designはllm-api-cost-estimate.md・tech-stack.mdに、(d)trial-end-scheduler-designは
  daily-scheduler-design.mdに、(e)checkout-session-plan-selection-designは
  subscription-plan-sync-design.mdに、(f)subscription-billing-cost-estimateは
  unit-economics-estimate.mdに、それぞれ相当する内容が既に存在することを確認した。
  以上により、ファイル名の一致のみで判定するcross-venture parity監査は本venture
  ではfalse positiveを生みやすい(本ventureは低頻度受注特性〈月次課金より一括契約に
  近い運用〉のため他3venture〈course-set-pasha・aircon-pasha・line-reservation-ai〉と
  ファイル構成の切り方自体が異なる)ことが判明したため、今後の同種監査ではファイル名
  比較だけで「未着手」と即断せず、本フェーズで確認した対応関係表(上記(a)〜(f))を
  参照した上で実際の内容を確認することとする。コード変更は無く、回帰確認として
  venture全体127件(`python3 -m unittest discover -s prototype -p "test_*.py"`)・
  schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス(変更前と
  同じ結果)を確認した。承認不要な既存ドキュメントの棚卸し・確認のみで、外部サービス
  への公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.md
  への追記なし。
- 最終更新: 2026-09-22 16:00 UTC(フェーズ162: 4venture間のファイル名比較で
  本ventureに無いように見えた8件を1件ずつ確認し、いずれも別ファイルへの統合済み
  内容・本venture固有の設計判断であり実装漏れではないことを確認。ファイル名比較の
  false positiveリスクを記録し、今後の監査手順に対応関係表を残した。コード変更は
  無く回帰確認のみ、venture全体127件・schema検証32件いずれもパス)
- フェーズ163(2026-09-22 20:00 UTC定例更新): onboarding-guide.md(フェーズ96作成)
  手順2・「次のステップ候補」に残っていた「代表者以外の職人を同一workshopに追加登録する
  具体的な手順(2人目以降の連携コード発行・workshopへの合流方法)はcraftsman-
  account-linking-design.md未確定のまま」という記載が、実際にはその後のフェーズ97〜104
  (craftsman-account-linking-design.md 5節・11.1〜11.4節、招待コード〈
  pending_workshop_invites〉の発行・解決・workshop合流のロジック)で設計・実装・
  テストとも解消済みであるにもかかわらず7日以上未反映のまま取り残されていた
  cross-document parityの記載漏れを発見した。onboarding-guide.md手順2に、代表者による
  招待コード発行(「職人を追加したい」の意思表示→招待コード発行→転送)、追加される
  職人がLINE友だち追加後に招待コードを送ると既存workshopへ合流する流れ、契約者含め
  5名の暫定上限(フェーズ102)を実装済みの内容として追記し、「次のステップ候補」から
  当該項目を削除した。実装コード自体への変更は無く、回帰確認としてventure全体687件
  (`python3 prototype/run_all_tests.py`、15ファイル全件)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要なドキュメント記載訂正のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-22 20:00 UTC(フェーズ163: onboarding-guide.mdの「次のステップ候補」に
  7日以上残っていた「代表者以外の職人の追加登録手順は未確定」という記載が、実際には
  フェーズ97〜104(招待コード方式)で解消済みだったcross-document parityの記載漏れを
  発見・訂正。実装済みの招待コードフローを手順2に反映し、該当の次のステップ候補項目を
  削除。コード変更は無く回帰確認のみ、venture全体687件・schema検証32件いずれもパス)
- フェーズ164(2026-09-23 00:00 UTC定例更新): onboarding-guide.md「次のステップ候補」に
  残っていた「本ガイドの各ステップを、想定顧客ヒアリング(customer-interview-design.md)の
  設問に『導入のどのステップで最も不安・手間を感じるか』『複数職人プランの場合、代表者以外の
  職人が自分で送信する運用を実際に望むか』を確認する項目として反映できないか検討する」に
  対応した。customer-interview-design.mdの問11(導入障壁の確認)に、onboarding-guide.mdの
  4ステップ(①LINE友だち追加、②フォームでの連携コード入力、③接続テスト・試験生成、
  ④本番運用開始)のうちどのステップに最も不安・手間を感じるかを問う小問を追記し、複数職人
  プラン検討者向けの条件付き新設問13(代表者以外の職人が自分のLINEアカウントから直接送信する
  運用を望むか、代表者による代行送信の方が実態に合うか)を新設した(全13問→全14問、旧問13
  〈E区分〉は問14に繰り下げ)。onboarding-guide.mdの当該「次のステップ候補」項目は対応済みの
  旨を明記する形に更新した。実際のヒアリング実施(職人・工房への連絡)はオーナー許可が必要な
  アクションのため引き続き未実施。コード変更は無く、回帰確認としてventure全体687件
  (`python3 prototype/run_all_tests.py`、15ファイル全件)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な既存ドキュメントの拡充のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-23 00:00 UTC(フェーズ164: onboarding-guide.mdが残していた
  「ヒアリング設問への導入障壁・複数職人プラン運用実態の反映検討」という次のステップ候補に
  対応。customer-interview-design.mdの問11に導入ステップ別の不安確認を追記し、複数職人プラン
  検討者向けの条件付き新設問13を追加(全13問→全14問)。ヒアリング実施自体は未実施。
  コード変更は無く回帰確認のみ、venture全体687件・schema検証32件いずれもパス)
- フェーズ165(2026-09-23 05:00 UTC定例更新): customer-interview-design.mdフェーズ164の
  「次のステップ候補」に残っていた「line-reservation-aiのinterview-rehearsal-script.mdに
  相当するリハーサル台本を作成し、質問数14問(条件付き設問1問含む)が想定時間に収まるか
  机上で検証する」に対応した。既存のinterview-rehearsal-script.md(フェーズ63作成、全13問
  当時の版のまま7日以上未更新でcross-document parityのずれが生じていた)を、フェーズ164の
  改訂内容(問11へのonboarding-guide.md 4ステップ別不安確認の追記、複数職人プラン検討者向け
  条件付き新設問13、旧問13〈スコープ限定〉の問14への繰り下げ)に合わせて改訂した。想定
  タイムテーブルをD(導入障壁、Q11〜12)2分→2.5分に、新設のD'(条件付きQ13)0.5分を追加し、
  目標時間を13分→14分(Q13が対象外の場合は13.5分)に机上で見積もった。Q11のト書きに
  onboarding 4ステップの読み上げ手順を追加し、新Q13のト書き(候補1・候補2いずれも代表個人が
  主回答者と想定されるため、事前に複数職人の有無を確認してから設問要否を判断する運用)を
  新設、旧Q13(スコープ限定)をQ14に繰り下げた。リハーサル確認ポイントのチェックリストにも
  Q11追加小問・Q13スキップ判定の2項目を追加した。実際のリハーサル実施・候補への連絡は
  オーナー許可が必要なアクションのため引き続き未実施。コード変更は無く、回帰確認として
  venture全体687件(`python3 prototype/run_all_tests.py`、15ファイル全件)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な既存ドキュメントの改訂のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-23 05:00 UTC(フェーズ165: customer-interview-design.mdフェーズ164の
  改訂〈問11への4ステップ別不安確認、条件付き新設問13、旧問13の問14への繰り下げ〉を
  interview-rehearsal-script.mdに反映し、cross-document parityのずれを解消。タイムテーブル・
  Q11ト書き・新Q13ト書き・チェックリストを更新。リハーサル実施自体は未実施。コード変更は
  無く回帰確認のみ、venture全体687件・schema検証32件いずれもパス)
- フェーズ166(2026-09-23 09:00 UTC定例更新): course-set-pashaのchatbot-first-response-
  feasibility.md(フェーズ234)・そのフェーズ248(2026-09-23 04:00 UTC)が「aircon-pasha・
  kura-pashaは同一アーキテクチャのため横展開可能性が高い、実移植は各venture側へ申し送り」と
  していた申し送りに対応し、本venture(鞍パシャッと)固有のFAQ・業務特性を踏まえたチャット
  ボット一次受付自動化の技術的検討をchatbot-first-response-feasibility.mdとして新規作成した。
  tech-stack.mdの単方向バッチ処理構成がcourse-set-pasha・aircon-pashaと同一であることを
  確認し、line-reservation-aiとは異なり選択肢2(LLMによる意図分類+定型回答方式)を適用
  できる前提が揃っていることを確認した。本venture固有の論点として、(1)契約者譲渡が
  静的FAQ(owner-operation-self-service-faq.md Q7)だけでなく専用の自動化フロー
  (contractor-transfer-design.md等)を既に持つため、意図分類のカテゴリ設計では「制度説明」
  と「実際の操作(専用フロー側)」を分離する必要があること、(2)「修理可否の判断」に関する
  質問はFAQ的な表現と専門的判断(mvp-flow-draft.mdの厳守事項により不介入と定める領域)の
  境界が曖昧になりやすく、意図分類のフェイルセーフ方針をcourse-set-pasha以上に明確化する
  必要があること、の2点を整理した。実装・実LLM呼び出し・実LINE接続は行っていない。回帰
  確認としてventure全体687件(`python3 prototype/run_all_tests.py`、15ファイル全件、
  変更前と同数)・schema検証32件(`python3 schema/validate_test_cases.py`、変更前と同じ
  結果)いずれもパスを確認した(ドキュメント新規作成のみでコード変更は無い)。承認不要な
  ドキュメント新規作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回
  発生していないためpending-approval.mdへの追記なし。次回候補: 意図分類プロンプト・
  エスカレーション導線の具体設計、またはaircon-pasha側での同種検討の実施。
- 最終更新: 2026-09-23 09:00 UTC(フェーズ166: course-set-pashaの申し送りに対応し、
  chatbot-first-response-feasibility.mdを本venture向けに新規作成。契約者譲渡の専用フローと
  FAQ回答の役割分離、修理可否判断の境界ケースをフェイルセーフで人的対応に倒す必要性の
  2点を本venture固有の論点として整理。コード変更は無く回帰確認のみ、venture全体687件・
  schema検証32件いずれもパス)
- フェーズ167(2026-09-23 11:00 UTC定例更新): フェーズ166の残課題だった意図分類プロンプト・
  エスカレーション導線の具体設計に着手し、chatbot-intent-classification-design.mdを新規
  作成した。course-set-pashaのchatbot-intent-classification-escalation-design.md
  (フェーズ235)を土台に、本venture固有の設計として、(1)既存の解約意図検知・契約者
  譲渡意図検知(contractor-transfer-design.md)を新設の意図分類レイヤーより常に手前で
  実行する分岐順序を明記し、契約者譲渡の「操作」と「制度概要説明(faq_contractor_
  transfer_overview)」の誤分類を構造的に回避する設計とした、(2)owner-operation-
  self-service-faq.mdのQ1〜Q9を6分類(memo_processing_request/faq_plan/faq_howto/
  faq_cancel/faq_contractor_transfer_overview/other_needs_human)に整理した、
  (3)「修理可否の判断」の境界ケースを「特定の個体・状態への言及が含まれるか」という
  具体的な判定基準で`other_needs_human`側へ倒すフェイルセーフ方針を明文化した、
  (4)エスカレーション通知文言に「修理可否等の専門的判断への言及を含む可能性があります」
  という本venture固有の補足を追加した。実装・実LLM呼び出し・実LINE接続は行っていない。
  回帰確認としてventure全体687件(`python3 prototype/run_all_tests.py`、15ファイル
  全件、変更前と同数)・schema検証32件(`python3 schema/validate_test_cases.py`、
  変更前と同じ結果)いずれもパスを確認した(ドキュメント新規作成のみでコード変更は無い)。
  承認不要なドキュメント新規作成のみで、外部サービスへの公開・アカウント作成・支払い・
  送信等は今回発生していないためpending-approval.mdへの追記なし。次回候補: 意図分類
  プロンプトの具体的な文面(LLM呼び出し部分)の設計、`prototype/`へのマッピング層・
  エスカレーション通知ヘルパーの実装、またはaircon-pasha側での同種検討の実施。
- 最終更新: 2026-09-23 11:00 UTC(フェーズ167: chatbot-intent-classification-design.mdを
  新規作成。意図分類の6分類・既存フローとの分岐順序・修理可否境界ケースのフェイルセーフ・
  エスカレーション通知文言を設計。コード変更は無く回帰確認のみ、venture全体687件・
  schema検証32件いずれもパス)
- フェーズ168(2026-09-23 14:00 UTC定例更新): フェーズ167の残課題だった意図分類プロンプトの
  具体的な文面設計に着手し、chatbot-intent-classification-llm-prompt-draft.mdを新規作成
  した。aircon-pashaのchatbot-intent-classification-llm-prompt-draft.md(フェーズ257)を
  土台に、本venture固有の6分類(memo_processing_request/faq_plan/faq_howto/faq_cancel/
  faq_contractor_transfer_overview/other_needs_human)向けのシステムプロンプト草案を
  作成した。design.md 0節の分岐順序(解約意図検知・契約者譲渡意図検知は本プロンプトより
  手前で実行)をプロンプト自体には含めずコード側の呼び出し順序で担保する設計、design.md
  2節のフェイルセーフ方針(修理可否の境界判定)を判定順位の2番目(中核機能の次、FAQ4分類
  より前)に独立配置してfaq_howtoとの誤分類リスクを構造的に下げる設計、の2点を本venture
  固有の要点として整理した。実装・実LLM呼び出し・実LINE接続は行っていない。回帰確認として
  venture全体687件(`python3 prototype/run_all_tests.py`、15ファイル全件、変更前と同数)・
  schema検証32件(`python3 schema/validate_test_cases.py`、変更前と同じ結果)いずれもパス
  を確認した(ドキュメント新規作成のみでコード変更は無い)。承認不要なドキュメント新規
  作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していない
  ためpending-approval.mdへの追記なし。次回候補: `faq_intent_to_code()`相当のマッピング層・
  エスカレーション通知送信ヘルパーの`prototype/`配下への実装、またはaircon-pasha側での
  同種検討の実施。
- 最終更新: 2026-09-23 14:00 UTC(フェーズ168: chatbot-intent-classification-llm-prompt-
  draft.mdを新規作成。本venture固有6分類向けのシステムプロンプト草案、分岐順序の
  コード側担保、修理可否境界判定の判定順位2番目への独立配置を設計。コード変更は無く
  回帰確認のみ、venture全体687件・schema検証32件いずれもパス)
- フェーズ169(2026-09-23 15:00 UTC定例更新): フェーズ167・168が進めていた意図分類の
  設計作業とは別に、owner_faq_router.py(フェーズ126作成、契約者向け「FAQ」→
  「Q1」〜「Q8」コマンド応答)がowner-operation-self-service-faq.mdのQ9(複数職人プラン
  への招待手順、フェーズ154で追加)に対応しておらず、`test_owner_faq_router.py`が
  `match_owner_faq_item_code("Q9")`をわざわざ「範囲外」としてテストしていた
  cross-document parityの記載漏れ(実装漏れ)を発見した。owner-operation-self-service-
  faq.mdのQ9本文を基に、`_FAQ_HEADINGS`・`_FAQ_ANSWERS`にQ9を追加し、
  `render_owner_faq_menu_message()`・`render_owner_faq_answer_message()`が対応する
  よう実装した(LLM呼び出し・LINE送信・通知ログ記録を行わない純粋関数という既存設計は
  変更していない)。あわせてtest_owner_faq_router.pyの「Q1〜Q8」前提のテスト
  (全件ループ範囲、メニュー見出し一覧、範囲外コード判定)をQ1〜Q9前提に更新し、
  Q9の回答本文が招待コードに言及することを確認する新規テストを1件追加した。
  回帰確認として`python3 prototype/run_all_tests.py`で15ファイル全件[OK]、
  test_owner_faq_router.py単体では`python3 -m unittest`で18件→19件(Q9追加分1件増)が
  いずれもパス、`python3 schema/validate_test_cases.py`は32件中32件パス(変更前と
  同じ結果、本フェーズはowner_faq_router.py側のみの変更でLLM出力スキーマには影響しない)
  であることを確認した。承認が必要なアクション(支払い・アカウント作成・外部公開・
  送信等)は今回発生していないためpending-approval.mdへの追記なし。次回候補:
  chatbot-intent-classification-design.md「残課題」の`faq_intent_to_code()`相当の
  マッピング層(新設の意図分類カテゴリ→本モジュールのQ番号への変換)の実装、または
  aircon-pasha・line-reservation-ai・course-set-pasha側で同種のFAQ追加とコマンド
  応答実装の間にずれが無いかの横断確認。
- 最終更新: 2026-09-23 15:00 UTC(フェーズ169: owner_faq_router.pyがowner-operation-
  self-service-faq.mdのQ9(招待手順、フェーズ154追加)に未対応だったcross-document
  parityの記載漏れ(実装漏れ)を発見・解消。`_FAQ_HEADINGS`・`_FAQ_ANSWERS`にQ9を追加し、
  test_owner_faq_router.pyのQ1〜Q8前提テストをQ1〜Q9に更新・新規テスト1件追加。
  run_all_tests.py 15ファイル全件[OK]、schema検証32件いずれもパス)
- フェーズ170(2026-09-23 16:00 UTC定例更新): フェーズ167・168の残課題だった
  (1) `faq_intent_to_code()`相当のマッピング層、(2) エスカレーション通知送信ヘルパー、
  (3) memo_processing_request判定時への一言追加、の3点を実装し、
  `prototype/chatbot_intent_router.py`を新規作成した。course-set-pashaの
  prototype/chatbot_intent_router.py(フェーズ236)を土台に、本venture固有の6分類
  (course-set-pashaは5分類)に合わせ、(a)`faq_cancel`→Q3・`faq_contractor_transfer_
  overview`→Q7の1対1マッピングと、Q1/Q5/Q6にまたがる`faq_plan`・Q2/Q4/Q8/Q9にまたがる
  `faq_howto`はメニュー全体(`render_owner_faq_menu_message()`)を返す設計、
  (b)chatbot-intent-classification-design.md 3節の通知文言(本venture固有の「修理可否等の
  専門的判断への言及を含む可能性があります」の一文を含む)をそのまま実装した
  `send_chatbot_escalation_notification()`、(c)chatbot-intent-classification-llm-
  prompt-draft.md「設計上の要点4」が課題としていた複合入力(受注メモ+FAQ質問)対策の
  `append_faq_followup_hint()`、を実装した。送信基盤は新規追加せず、既存の
  subscription_cancellation_notification.pyのLinePushClient/LinePushDeliveryErrorと
  payment_suspension_owner_notification.pyのOWNER_LINE_USER_ID_PLACEHOLDERをそのまま
  再利用した(本venture内で運営者宛送信先を複数箇所で個別定義しない方針を踏襲)。
  実LLMによる意図分類自体(自由入力→6分類への分類)は引き続き対象外(オーナー承認待ちの
  実LLM接続領域)で、分類結果が既に得られている前提での配線のみを実装した。
  `test_chatbot_intent_router.py`を新規作成し29件のテストケースを追加した。回帰確認
  として`python3 prototype/run_all_tests.py`で16ファイル全件[OK](15→16ファイル、
  新規ファイル追加分)、`python3 schema/validate_test_cases.py`は32件中32件パス
  (変更前と同じ結果、本フェーズはLLM出力スキーマに影響しないprototype/配下のみの
  変更)であることを確認した。承認が必要なアクション(支払い・アカウント作成・外部
  公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。次回候補:
  上記3関数を実際のLINEメッセージ受信ハンドラ(`cloud_function_webhook.py`)へ配線する
  設計(現時点では意図分類結果を受け取る前提の`route_chatbot_intent()`単体のみで、
  webhook側からの呼び出しは未接続)、またはaircon-pasha側での同種検討の実施
  (course-set-pashaフェーズ248・本ventureフェーズ167の申し送り事項として引き続き残る)。
- 最終更新: 2026-09-23 16:00 UTC(フェーズ170: `prototype/chatbot_intent_router.py`を
  新規作成し、faq_intent_to_code()マッピング層・エスカレーション通知送信ヘルパー・
  memo_processing_request判定時への一言追加を実装。新規テスト29件追加。
  run_all_tests.py 16ファイル全件[OK]、schema検証32件いずれもパス)
- フェーズ171(2026-09-24 定例更新): フェーズ170の「次回候補」だった
  `chatbot_intent_router.py`3関数の`cloud_function_webhook.py`への配線設計に
  着手し、chatbot-intent-classification-wiring-design.mdを新規作成した。配線設計
  そのものより先に、chatbot-intent-classification-design.md(フェーズ167)0節の
  前提(「解約意図検知(厳守事項7a)・契約者譲渡意図検知(contractor-transfer-
  design.md 3節)は新設の意図分類より手前で実行される既存の独立ロジックである」)を
  実装コードで検証したところ、この2つはいずれも独立した事前チェックではなく、
  `process_generation_request()`が呼ぶ受注メモ生成LLMコール単体
  (schema/output.schema.jsonの19-status enumの一部として出力される)の内部でのみ
  判定されることを発見した。この結果、「解約したい」等メモらしき内容を含まない
  解約意図表明が、新設の意図分類レイヤー配線後は`faq_cancel`(Q3の制度説明のみで
  実ポータルURLを含まない回答)に誤誘導され、既存の解約フロー(実URL付き案内)に
  到達できなくなるという実害を具体的に特定した。修正方針として、フェイルセーフ
  方針2節ルール1(メモらしき内容の優先)の適用範囲を「解約・ダウングレード・
  契約者交代の意思表示そのもの」にも拡張し、当該メッセージは`memo_processing_
  request`側へ振り分けて既存の受注メモ生成LLMコールへ一本化させる方針を確定した。
  この方針を前提に、新設Protocol`ChatbotIntentClassificationClient`(分類失敗時は
  memo_processing_requestへフェイルセーフ)を導入し、`process_message_event()`の
  `_maybe_handle_owner_faq_command()`(既存の明示コマンド判定、変更なし)の後段・
  `process_memo_event()`委譲の前段に意図分類コールを挿入する配線案を設計した。
  クライアント未接続時(実LLM接続がオーナー承認待ちの間)はこのステップ自体を
  丸ごとスキップし、フェーズ170時点までと同じ挙動を維持する後方互換設計とした。
  実装・実LLM呼び出しは行っていない、机上の設計・既存設計文書の前提検証のみ。
  回帰確認としてventure全体16ファイル全件(`python3 prototype/run_all_tests.py`)・
  schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス(変更前と
  同じ結果、ドキュメント新規作成のみでコード変更は無い)を確認した。承認が必要な
  アクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
  pending-approval.mdへの追記なし。次回候補: `faq_contractor_transfer_overview`
  側の同種実害シナリオの再検証、および本フェーズの方針をchatbot-intent-
  classification-design.md 2節・chatbot-intent-classification-llm-prompt-draft.md
  本体へ正式反映すること。
- 最終更新: 2026-09-24(フェーズ171: chatbot-intent-classification-wiring-design.md
  を新規作成。配線設計に先立ち、既存の解約意図検知・契約者譲渡意図検知が独立した
  事前チェックではなく受注メモ生成LLMコール内部の判定であることを発見し、
  「解約したい」等が新設意図分類レイヤーで`faq_cancel`に誤誘導され実ポータルURLを
  含む既存フローに届かなくなる実害を特定。フェイルセーフ方針の拡張と配線案を設計。
  コード変更は無く回帰確認のみ、venture全体16ファイル全件・schema検証32件いずれも
  パス)
- フェーズ172(2026-09-24 20:00 UTC定例更新): フェーズ171の次回候補だった、
  「解約・ダウングレード・契約者交代の意思表示そのものをmemo_processing_request
  優先の対象に含める」方針をchatbot-intent-classification-design.md・
  chatbot-intent-classification-llm-prompt-draft.mdへ正式反映した。design.mdは
  0節(当初の「呼び出し順序による分岐」設計を、フェーズ171で判明した実装上の制約と
  「2節ルール1の分類ルール拡張による代替担保」への訂正として書き換え)・1節
  (`faq_cancel`の定義に`faq_contractor_transfer_overview`と同様「制度理解目的の
  質問のみ」の限定を追加)・2節ルール1(解約・ダウングレード・契約者交代の意思表示
  そのものを対象に含める拡張を追記)・4節残課題を更新した。llm-prompt-draft.mdは
  判定順位1に同趣旨の拡張を追記し、faq_cancel/faq_contractor_transfer_overviewの
  カテゴリ説明にも同じ限定を明示した。あわせてchatbot-intent-classification-
  wiring-design.md 6節の該当申し送りに取り消し線で対応済みの旨を追記した。
  コード変更は無くドキュメント3件の記述訂正のみのため、回帰確認として本venture
  全体16ファイル全件(`python3 prototype/run_all_tests.py`)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を
  確認した。承認不要なドキュメント訂正のみで、外部サービスへの公開・アカウント
  作成・支払い・送信等は今回発生していないためpending-approval.mdへの追記なし。
  次回候補: `faq_contractor_transfer_overview`側の同種実害シナリオ(名指しを含む
  具体的な譲渡依頼の誤分類)の再検証(フェーズ171・172でいずれも申し送りのみで
  未着手)、`faq_intent_to_code()`相当のマッピング層・エスカレーション通知送信
  ヘルパーの実装、またはaircon-pasha側での同種の前提(既存の意図検知が独立した
  事前チェックか単一LLMコール内部の判定か)の横展開検証。
- 最終更新: 2026-09-24 20:00 UTC(フェーズ172: フェーズ171で確定した「解約・
  ダウングレード・契約者交代の意思表示をmemo_processing_request優先に含める」
  方針を、chatbot-intent-classification-design.md・chatbot-intent-classification-
  llm-prompt-draft.md本体へ正式反映。コード変更は無く回帰確認のみ、venture全体
  16ファイル全件・schema検証32件いずれもパス)
- フェーズ173(2026-09-24定例更新): 2点対応した。(1)フェーズ172でdesign.md 0節
  のみ「呼び出し順序ではなく判定順位1の分類ルールで担保する」方式へ訂正されたが、
  chatbot-intent-classification-llm-prompt-draft.mdの「位置づけ」節・「設計上の
  要点」1が旧来の「呼び出し順序(コード側)で担保する」記述のまま取り残されて
  いた不整合を発見し、design.mdの訂正内容に合わせて訂正した。(2)chatbot-intent-
  classification-wiring-design.mdフェーズ171の申し送り事項(「契約者を交代したい、
  田中さんにお願いします」のような名指しを含む具体的な譲渡依頼がfaq_contractor_
  transfer_overviewに誤分類されないかの再検証)に着手し、contractor-transfer-
  design.md 3節の検知語彙(「契約者を交代したい」「後継ぎに変更したい」)と
  llm-prompt-draft.md判定順位1の例示文言を突き合わせた結果、判定順位1の例示文言
  自体が既に名指しを含む例(「後継ぎに変更したい、田中さんにお願いします」)を
  カバーしており、構造的リスクは現在の文言上既に回避されていると判断した(実LLMでの
  挙動確認は残課題として継続)。design.md 4節・llm-prompt-draft.md残課題の該当項目を
  対応済みとして更新した。コード変更は無くドキュメント訂正のみのため、回帰確認として
  venture全体16ファイル全件(`python3 prototype/run_all_tests.py`)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認が必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していない
  ためpending-approval.mdへの追記なし。次回候補: aircon-pasha側での同種の前提(既存の
  意図検知が独立した事前チェックか単一LLMコール内部の判定か)の横展開検証、
  `faq_intent_to_code()`相当のマッピング層・エスカレーション通知送信ヘルパーの実装。
- 最終更新: 2026-09-24(フェーズ173: chatbot-intent-classification-llm-prompt-
  draft.mdの「位置づけ」節・「設計上の要点」1をフェーズ172のdesign.md訂正に合わせて
  修正〈ドキュメント間の不整合を発見・修正〉。あわせてフェーズ171の申し送り事項
  〈名指しを含む具体的な譲渡依頼の誤分類リスクの再検証〉に対応し、判定順位1の既存の
  例示文言で構造的リスクが回避されていることを確認。コード変更は無く回帰確認のみ、
  venture全体16ファイル全件・schema検証32件いずれもパス)
- フェーズ174(2026-09-25定例更新): フェーズ173の次回候補
  「`faq_intent_to_code()`相当のマッピング層・エスカレーション通知送信ヘルパーの実装」を
  確認したところ、両者は既にフェーズ170で`prototype/chatbot_intent_router.py`へ実装
  済みであり(フェーズ173の申し送り自体がcross-document parityの記載漏れ、本フェーズで
  発見)、実際に未着手のまま残っていたのはフェーズ171
  (chatbot-intent-classification-wiring-design.md)4節が設計した「3関数を
  `cloud_function_webhook.py`(実際のLINEメッセージ受信ハンドラ)へ配線する」実装
  そのものだった。この配線を実装した: 新設Protocol
  `ChatbotIntentClassificationClient`(wiring-design.md 5節)・
  `_classify_chatbot_intent_with_retry()`(即時1回のみリトライ、2回とも失敗時は
  `memo_processing_request`扱いへフェイルセーフ)を追加し、`process_message_event()`の
  `_maybe_handle_owner_faq_command()`不一致後・`process_memo_event()`委譲前に意図分類
  ステップを挿入した(4節3.の設計通り)。FAQ系4分類・`other_needs_human`は
  `route_chatbot_intent()`委譲でその場返信、`memo_processing_request`
  (分類失敗によるフォールバックを含む)は新設引数`apply_chatbot_followup_hint=True`を
  添えて`process_memo_event()`へ委譲し、同関数側でstatus=="generated"時のみ
  `append_faq_followup_hint()`を返信文末尾に適用する。`chatbot_intent_classifier`・
  `escalation_push_client`はいずれも`dispatch_webhook_events()`・`receive_webhook()`
  含め後方互換の追加引数(未接続時はNone、既定動作は本フェーズ以前と不変)とした。
  新規テスト12件追加、回帰確認としてventure全体16ファイル全件
  (`python3 prototype/run_all_tests.py`)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス。承認が必要なアクション
  (支払い・アカウント作成・外部公開・送信等)は今回発生していないため
  pending-approval.mdへの追記なし(実LLMによる意図分類コール自体の接続は既存の
  「実LLM API接続はオーナー承認待ちの範囲」に含まれるため新規追加は不要と判断)。
  次回候補: `ChatbotIntentClassificationClient`実クライアント接続(実LLM接続、オーナー
  承認待ち)、aircon-pasha/course-set-pashaが実装済みの
  intent-classification-failure-observability-design.md相当(分類失敗時のCloud
  Monitoringログベース指標・アラートポリシー)の本venture向け横展開検討。
- 最終更新: 2026-09-25 01:00 UTC(フェーズ174: chatbot-intent-classification-
  wiring-design.md 4節が設計していた意図分類レイヤーの`cloud_function_webhook.py`
  への配線を実装。`ChatbotIntentClassificationClient`Protocol新設・
  `_classify_chatbot_intent_with_retry()`追加・`process_message_event()`への
  分類ステップ挿入・`process_memo_event()`へのFAQ折り返し文言付記引数追加。
  新規テスト12件追加、venture全体16ファイル全件・schema検証32件いずれもパス)
- フェーズ175(2026-09-25 04:00 UTC定例更新): フェーズ174「次回候補」・
  course-set-pashaフェーズ249「次回候補」で申し送られていた「aircon-pasha/
  course-set-pashaが実装済みのintent-classification-failure-observability-
  design.md相当(分類失敗時のCloud Monitoringログベース指標・アラートポリシー)の
  本venture向け横展開検討」に対応した。確認したところ、ログ出力自体
  (`_classify_chatbot_intent_with_retry()`のWARNINGログ、`event`・`memo_length`の
  2フィールド)はフェーズ174で既に実装済みで、course-set-pasha/aircon-pashaと
  同一構造だったため新規コード変更は不要と判断した。intent-classification-
  failure-observability-design.md(新規作成)にその前提確認を記録し、
  cloud-monitoring-alert-policy-design.md(新規作成)でログベース指標(名前案
  `kura_pasha_chatbot_intent_classification_failure_count`、venture間の指標名
  衝突を避けるため接頭辞を付与)・アラートポリシー(直近60分で合計1件以上、
  course-set-pashaと同一のしきい値)・通知チャネル(契約者向けLINE Push通知とは
  別経路のCloud Monitoring標準メール通知`OWNER_ALERT_EMAIL_PLACEHOLDER`)を
  確定した。実際のログベース指標・アラートポリシーの作成はGCPプロジェクト作成
  (既存のオーナー承認待ち事項)後の課題として据え置き。コード変更は無く、回帰確認
  として本venture全体16ファイル全件(`python3 prototype/run_all_tests.py`)・
  schema検証32件(`python3 schema/validate_test_cases.py`)いずれもパス(変更前と
  同じ結果)を確認した。承認不要な設計文書作成のみで、外部サービスへの公開・
  アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。次回候補: `ChatbotIntentClassificationClient`実クライアント接続
  (実LLM接続、オーナー承認待ち)、または他venture・アイデア領域の前進。
- 最終更新: 2026-09-25 04:00 UTC(フェーズ175: aircon-pasha/course-set-pasha
  実装済みのCloud Monitoringログベース指標・アラートポリシー設計を本venture向けに
  横展開。intent-classification-failure-observability-design.md・
  cloud-monitoring-alert-policy-design.mdを新規作成。ログ出力自体はフェーズ174で
  実装済みのため既存構造の確認のみ。コード変更は無く回帰確認のみ、venture全体
  16ファイル全件・schema検証32件いずれもパス)
- フェーズ176(2026-09-25 08:00 UTC定例更新): line-reservation-ai/line-price-
  revision-2026-check.mdで調査済みの「2026年10月1日実施予定のLINE公式アカウント
  追加メッセージ料金改定」について、本venture固有の影響評価が未作成だったため
  web調査による再確認とcross-venture水平展開を行った。line-price-revision-2026-
  check.md(新規作成)に、改定内容(スタンダードプラン無料枠超過分が「20万通/月まで
  1通3円、20万通超2.5円」の2段階体系に一本化)の再確認と、pricing-plan.mdの
  複数職人プラン上限(月20回・5名共同利用)から見た本venture固有の影響評価(想定
  送信ボリュームは影響が生じる月5万通超の水準から3桁近く少なく、料金プラン設計の
  見直しは不要)を記録した。一次情報(LINEヤフー for Business公式ページ)は
  line-reservation-ai側と同じくegressポリシーによりこの実行環境からは確認できず、
  二次情報源のクロスチェックにとどまる点も明記した。コード変更は無く、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.md
  への追記なし。次回候補: aircon-pasha・course-set-pashaへの同種確認の横展開、または
  `ChatbotIntentClassificationClient`実クライアント接続(実LLM接続、オーナー承認待ち)。
- 最終更新: 2026-09-25 08:00 UTC(フェーズ176: line-price-revision-2026-check.md
  新規作成。line-reservation-ai調査済みの2026年10月LINE料金改定について本venture
  固有の影響評価を実施、料金プラン見直しは不要と判断。コード変更なし)
- フェーズ177(2026-09-25 10:00 UTC定例更新): payment-suspension-owner-notification-
  design.md(フェーズ116)8節が「次回以降の検討課題」として残していた「契約者識別子として
  contractor_user_idをそのまま通知に載せる案で暫定としたが、実運用では工房名等に変換した
  方がオーナーにとって分かりやすい可能性がある」に対応した。aircon-pashaの同種対応
  (フェーズ262・263、business-name-owner-notification-display-design.md)が次回候補として
  残していた「kura-pasha側の同種オーナー通知モジュールが同じ課題を抱えているかの確認」にも
  対応する形。onboarding-guide.md 2節で申込フォームの入力項目として「屋号(または工房名)」が
  既に定義済みだった一方、データモデル(`usage_counter_workshop.WorkshopStoreProtocol`)には
  この値を保持するフィールドが無かった(cross-document parityギャップ)ため、
  workshop-name-owner-notification-display-design.mdを新規作成し、`get_workshop_name`/
  `set_workshop_name`を追加したうえで、`payment_suspension_owner_notification.py`・
  `blocked_but_billing_owner_notification.py`の両方に「屋号: {workshop_name}(契約者ID:
  {contractor_user_id})」併記表示(workshop_name未設定時は従来通り契約者IDのみ)を実装した。
  新規テスト8件追加(各モジュールのbuild_関数でworkshop_name設定時・None時・空文字列時の
  3件+send_関数がstore/resolver経由で反映することを確認する1件、計4件×2モジュール)、
  venture全体165件(`python3 -m unittest discover -s prototype -p "test_*.py"`、既存157件+
  新規8件)・schema検証32件(`python3 schema/validate_test_cases.py`、変更前と同じ結果)
  いずれもパスを確認した。申込フォーム送信〜`set_workshop_name()`呼び出しの実結線
  (Googleフォーム・Firestore接続)はオーナー承認待ちの範囲のため未実装(次回候補として
  design.md 6節に記載)。承認不要なコード変更・ドキュメント作成のみで、外部サービスへの
  公開・アカウント作成・支払い・送信等は今回発生していないためpending-approval.mdへの
  追記なし。
- 最終更新: 2026-09-25 10:00 UTC(フェーズ177: workshop-name-owner-notification-
  display-design.md新規作成。payment_suspension_owner_notification.py・blocked_but_
  billing_owner_notification.pyの両方にworkshop_name〈屋号〉併記表示を実装。
  `WorkshopStoreProtocol`へ`get_workshop_name`/`set_workshop_name`追加。新規テスト8件、
  venture全体165件・schema検証32件いずれもパス)
- フェーズ178(2026-09-25 15:00 UTC定例更新): onboarding-guide.md「未検証の仮説」1点目・
  末尾「次のステップ候補」に残っていた、course-set-pasha/onboarding-settings-and-
  self-check-design.md相当の「初回生成時セルフチェック案内」フォールバック設計の要否検討に
  対応した。first-generation-self-check-notification-design.md(新規作成)にて、本venture
  固有の構造(契約単位が`workshop_id`で最大5名が枠を共有)を踏まえ、判定基準を
  「ユーザー単位の初回」ではなく「workshop単位の初回生成成功時」とする方針、
  `craftsman_workshop/{workshop_id}`へ`first_generation_notice_sent`フィールドを永続化する
  方針、確認案内文面案を確定した。course-set-pashaが持つ「ジム名・地域名未設定時の追加一文」
  相当の分岐は、本ventureのworkshop_nameがLLM生成品質に影響しない(オーナー通知表示専用)
  項目であるため不要と判断した。設計のみでコード変更は無く、回帰確認として本venture全体
  165件(`python3 -m unittest discover -s prototype -p "test_*.py"`)・schema検証32件
  (`python3 schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。
  承認不要な設計文書作成のみで、外部サービスへの公開・アカウント作成・支払い・送信等は
  今回発生していないためpending-approval.mdへの追記なし。次回候補: 本設計の実装
  (`WorkshopStoreProtocol`へのメソッド追加・`process_memo_event()`側の配線・統合テスト)、
  または他venture・アイデア領域の前進。
- 最終更新: 2026-09-25 15:00 UTC(フェーズ178: first-generation-self-check-notification-
  design.md新規作成。「workshop単位の初回生成」を判定基準とする方針・永続化フィールド・
  確認案内文面を確定。設計のみでコード変更は無し、venture全体165件・schema検証32件
  いずれもパス)
- フェーズ179(2026-09-25 16:00 UTC定例更新): フェーズ178のfirst-generation-self-check-
  notification-design.mdが「次回課題」として残していた実装(`WorkshopStoreProtocol`への
  メソッド追加・`process_memo_event()`側の配線・統合テスト)に対応した。
  `usage_counter_workshop.py`の`WorkshopStoreProtocol`へ
  `get_first_generation_notice_sent(workshop_id) -> bool`/
  `set_first_generation_notice_sent(workshop_id) -> None`を追加し(命名・「未設定=False」
  デフォルト方式は`get_trial_generation_used`と同スタイル)、`InMemoryWorkshopStore`にも
  対応する実装(`_first_generation_notice_sent_by_workshop`辞書)を追加した。
  `cloud_function_webhook.py`の`process_memo_event()`docstring9.として配線内容を明記し、
  `FIRST_GENERATION_NOTICE_MESSAGE`定数(design.md 4節の文面案をそのまま採用)を新設、
  8.の(d)`generation_request`経路で`generation_result.usage.workshop_id`を取得できた
  場合に限り、LLM出力の最終的な`status`が`"generated"`かつ`get_first_generation_notice_
  sent()`が`False`(そのworkshopにとって最初の`status="generated"`成功)のときのみ、
  limit_notice・トライアル終了通知の付記(6.7.)の後・`_reply_with_retry`直前で返信本文
  末尾へ確認案内を付記するようにした。character-limit-fallback-design.md該当時(文字数
  上限超過で早期returnする既存分岐)には到達しないため、limit_notice・トライアル終了通知
  と同じく自然に付記対象から除外される。`trial_end_notified_at`(`process_generation_
  request()`内で呼び出し前に書き込む既存方式)とは異なり、本フラグは`_reply_with_retry`
  の戻り値`reply_sent`が`True`だった場合にのみ`set_first_generation_notice_sent()`を
  呼び出す設計とした(LINE API呼び出し自体が失敗した場合まで「案内送信済み」として記録
  してしまわないための意図的な差、design.mdが明記していなかった実装判断)。`MemoProcess
  Result`へ`first_generation_notice_sent`フィールドを追加した。
  新規テストとして、`test_usage_counter_workshop.py`へストア層の単純な読み書き往復
  テスト1件(3 check)、`test_cloud_function_webhook.py`へ統合テスト4件
  (workshop初回generated成功時に付記される/2回目のgenerated成功では付記されない/
  契約者の初回生成後に別メンバーが初送信しても〈workshop単位判定のため〉付記されない/
  status="generated"以外〈out_of_scope〉は「最初の成功」を消費せずその後の最初の
  generated成功で改めて付記される、計12 check)を追加し、既存の文字数上限超過テスト
  (`test_process_memo_event_generated_over_limit_omits_limit_notice_and_trial_end_
  notification`)にも本フラグが便乗しないことの確認(2 check)を追加した。
  `python3 test_usage_counter_workshop.py`123→126(+3 check)、`python3 test_cloud_
  function_webhook.py`343→355(+12 check)、いずれもFAIL=0。venture全体は
  `python3 prototype/run_all_tests.py`で16ファイル全件パス(変更前と同数)、schema検証
  (`python3 schema/validate_test_cases.py`)32件パス(変更前と同じ結果)を確認した。
  なお`python3 -m unittest discover -s prototype -p "test_*.py"`は本フェーズ変更後も
  165件のまま(変更前と同数)だった。これは新規テストを追加した2ファイルがいずれも
  `check()`/PASS/FAIL方式のスクリプト形式であり、discoverが収集するのは
  `unittest.TestCase`ベースの3ファイルのみという既知の非互換(run_all_tests.py
  docstring記載、フェーズ88・89で発見)によるもので、テストの追加漏れではないことを
  `run_all_tests.py`・各ファイル直接実行の両方で確認済み。
  申込フォーム送信〜Firestore実接続(`craftsman_workshop/{workshop_id}.first_generation_
  notice_sent`フィールドの実書き込み)は既存のオーナー承認待ち事項(GCPプロジェクト作成・
  実Firestore接続)の範囲内のため引き続き未着手。承認不要なコード変更・テスト追加のみで、
  外部サービスへの公開・アカウント作成・支払い・送信等は今回発生していないため
  pending-approval.mdへの追記なし。次回候補: 実Firestore・実LINE Messaging API接続
  (いずれもオーナー承認待ち)、または他venture・アイデア領域の前進。
- 最終更新: 2026-09-25 16:00 UTC(フェーズ179: first-generation-self-check-notification-
  design.md〈フェーズ178〉の実装。`WorkshopStoreProtocol`へ`get_first_generation_notice_
  sent`/`set_first_generation_notice_sent`追加、`process_memo_event()`へworkshop単位の
  初回`status="generated"`成功時の確認案内付記を配線。新規テスト
  test_usage_counter_workshop.py+3 check・test_cloud_function_webhook.py+12 check、
  run_all_tests.py 16ファイル全件・schema検証32件いずれもパス)
- フェーズ180(2026-09-25 20:00 UTC定例更新): aircon-pashaフェーズ266の「次回候補」
  として残っていた、course-set-pashaフェーズ253で確定したCloud Functions採用世代
  (2nd gen〈Cloud Run functions〉)決定のtech-stack.mdへの反映を、本venture分として
  実施した。本venture自身のcloud-monitoring-alert-policy-design.md(フェーズ178)では
  既にこの確定を前提に`resource.type: cloud_run_revision`を採用していたにもかかわらず、
  決定の一次情報であるtech-stack.md側への反映が漏れていたcross-document parityの記載
  漏れであり、aircon-pasha・course-set-pasha版tech-stack.mdと同じ書きぶりで
  「想定コンポーネント2」に追記した。コード変更は無くドキュメント更新のみのため、
  回帰確認としてventure全体16ファイル全件(`python3 prototype/run_all_tests.py`、
  変更前と同数)・schema検証32件(`python3 schema/validate_test_cases.py`、変更前と
  同じ結果)いずれもパスを確認した。承認が必要なアクション(支払い・アカウント作成・
  外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。これで
  aircon-pasha・course-set-pasha・kura-pashaの3venture(Cloud Functionsをホスティング
  候補とする4venture中、Cloud Monitoringアラート設計に本決定の反映余地があった3つ)
  全てでtech-stack.md側への反映が完了した。次回候補: 実Firestore・実LINE Messaging
  API接続(いずれもオーナー承認待ち)、または他venture・アイデア領域の前進。
- 最終更新: 2026-09-25 20:00 UTC(フェーズ180: aircon-pashaフェーズ266が残していた
  Cloud Functions 2nd gen確定のtech-stack.mdへの反映のうち、本venture分に対応。
  「想定コンポーネント2」に採用世代確定の経緯を追記。コード変更は無く回帰確認のみ、
  venture全体16ファイル全件・schema検証32件いずれもパス)
- フェーズ181(2026-09-25 22:00 UTC定例更新): legal-notices-draft.md 2.5節が「新たな
  検討課題」として残していた、納品案内・お手入れ案内文に依頼者本人以外の第三者の氏名・
  住所等の個人情報を職人が誤ってメモへ記載してしまうケースへの対応方針を設計した
  (requester-personal-info-inclusion-handling-design.md新規作成)。mvp-flow-draft.mdの
  宛先整理(出力1は職人本人の備忘用、出力2・3は依頼者への転送を前提)に基づき、リスクを
  「依頼者本人以外の第三者情報が出力2・3経由で依頼者へ開示されること」に限定した上で、
  正規表現等による自動マスキングは日本語人名の表記多様性・過検出(依頼者本人の宛名を
  誤って削除する等)のリスクから不採用と判断し、プロンプト側の明示的指示(既存の
  厳守事項1〜8・7a〜7cに続く厳守事項9案として、第三者の氏名・連絡先等を出力2・3に
  転記せず一般化した表現に置き換える指示)+限定的な機械チェック(post_generation_
  checks.py拡張案、あくまで補助的な網)の組み合わせを採用方針とした。legal-notices-
  draft.md 2.5節を本設計への参照に更新した。本フェーズは方針設計のみで、
  llm-system-prompt-draft.md・schema/output.schema.json・prototype/post_generation_
  checks.pyへの実際の反映(厳守事項9の文面確定、対応するチェック関数・テストケース
  追加)は次回以降の実装フェーズとする。コード変更は無く、回帰確認としてventure全体
  16ファイル全件(`python3 prototype/run_all_tests.py`)・schema検証32件(`python3
  schema/validate_test_cases.py`)いずれもパス(変更前と同じ結果)を確認した。承認が
  必要なアクション(支払い・アカウント作成・外部公開・送信等)は今回発生していないため
  pending-approval.mdへの追記なし。次回候補: 厳守事項9のllm-system-prompt-draft.md
  への実際の反映、または他venture・アイデア領域の前進。
- フェーズ182(2026-09-25 23:00 UTC定例更新): フェーズ181のrequester-personal-info-
  inclusion-handling-design.mdが「次の課題」1点目として残していた、厳守事項9(依頼者
  本人以外の第三者個人情報を出力2・3に転記しない)のllm-system-prompt-draft.mdへの
  実際の反映を行った。同design.md 3節の文面案をそのまま採用し新設、文脈注入時の追加
  指示(a)(b)(c)の前文記述も「厳守事項1〜8・7a〜7c」から「厳守事項1〜9・7a〜7c」へ
  更新した。schema/output.schema.json・prototype/post_generation_checks.pyへの反映・
  onboarding-guide.mdの文言追加は次の課題として残す。コード変更は無くドキュメント
  更新のみ、venture全体16ファイル全件・schema検証32件いずれもパス。承認が必要な
  アクションは今回発生していないためpending-approval.mdへの追記なし。
- フェーズ183(2026-09-26 00:00 UTC定例更新): フェーズ182が次の課題として残していた
  2点のうち、design.md 4節の限定的な人名突き合わせ方式をschema/output.schema.json・
  prototype/post_generation_checks.pyへ実装した。order_summaryへ`third_party_names`
  (第三者の氏名らしき文字列のリスト、design.mdの位置づけ通りrequiredには含めない
  補助フィールド)を追加、`check_no_third_party_name_leak_in_customer_facing_notices()`
  を新設してdelivery_notice.body・care_noticeへの名前の紛れ込みを検出できるようにした
  (出力1は厳守事項9の対象外のため突き合わせ先から除外)。新規テスト6件を追加、venture
  全体16ファイル全件・schema検証32件いずれもパス(既存フィクスチャへの変更は不要)。
  onboarding-guide.mdへの入力時留意事項の文言追加は次の課題として残す。承認が必要な
  アクションは今回発生していないためpending-approval.mdへの追記なし。
- 最終更新: 2026-09-26 00:00 UTC(フェーズ183: 厳守事項9の機械チェック補助フィールド
  〈third_party_names〉・チェック関数を実装。新規テスト6件追加、venture全体16ファイル
  全件・schema検証32件いずれもパス。onboarding-guide.md更新は次の課題)
  venture全体16ファイル全件・schema検証32件いずれもパス)
