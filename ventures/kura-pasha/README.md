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

## 次にやること(候補)

- subscription-billing-data-model-design.md(フェーズ46)の「未検証・残課題」:
  `WorkshopStoreProtocol`への`get_stripe_customer_id`/`set_stripe_customer_id`/
  `get_subscription_status`等のメソッド追加、Checkout Session発行フロー、Stripe
  Webhookの署名検証・イベントディスパッチの実装(course-set-pasha/
  stripe-webhook-http-entry-point-design.md相当)を設計・実装する。
- trial-end-condition-design.md(フェーズ47)の「6. 今後の課題」: `trial_generation_used`を
  生成成功時にTrueへ更新する書き込み処理、`is_trial_period_over`の`process_generation_
  request`/`select_message_context`への組み込み(トライアル終了後の生成一時停止・案内文言
  への切り替え)、`trial_start_at`をworkshop作成時に書き込む実処理。
- unfollow-billing-faq.md(フェーズ45)の「今後の課題」: Stripe Webhook受信・
  `user_profile`の`is_following`相当フィールドの実装後に、「ブロック中かつ契約継続中」
  契約者の検知バッチを設計する。landing-page-copy-draft.md新規作成時にFAQ文面を反映する。
- 社内リハーサルの実施(オーナー内部で完結するため許可不要)を踏まえた
  interview-rehearsal-script.mdのタイムテーブル・ト書きの見直し。
- initial-contact-message-draft.mdの「未確定事項」(謝礼の有無・送信者名表記・返信先連絡先)
  についてオーナーの方針を確認する。実際の連絡・ヒアリング依頼はオーナー承認が必要な範囲と
  して別途pending-approval.mdに記録する。
- ジャパンギャロップスインポーターの正式化・除外の最終判断は、優先順位1・2候補への
  ヒアリング実施(承認後)時に併せて確認する(公開情報のみでの追加探索は当面見送り)。
- 実際のLINE公式アカウント接続・実LLM検証はオーナー承認待ち(pending-approval.md参照)。

最終更新: 2026-09-08 19:00 UTC(フェーズ47: 無料トライアル終了判定関数
`is_trial_period_over`をtrial-end-condition-design.mdとして設計・プロトタイプコード化)
