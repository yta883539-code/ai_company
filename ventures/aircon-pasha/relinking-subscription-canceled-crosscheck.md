# 再連携時のsubscription_canceled_at引き継ぎに関する横断確認(フェーズ276)

## 経緯

subscription-canceled-immediate-block-design.md(フェーズ275)で、aircon-pashaの
`resolve_linking_code()`(再連携時のフィールド引き継ぎ)に`subscription_canceled_at`を
追加した際、「引き継ぎ漏れがあると、解約済みuser_idが新規連携コードを送っただけで
生成ブロックが解除されてしまう別の欠落になる」ため同時に対応した旨を記録した。本フェーズは
この論点(「既存プロファイルのフィールドを新しいuser_idへ引き継ぐ再連携」という構造自体が
他venture(course-set-pasha・kura-pasha)にも存在し、同型の引き継ぎ漏れが起こりうるか)を
横断確認した。

## 確認結果: 該当する構造(既存プロファイルを新user_idへ引き継ぐ再連携)自体が無い

course-set-pasha・kura-pashaいずれも`resolve_linking_code()`を持つが、いずれも
aircon-pashaの「既に登録済みのworkshopが、新しい連携コードを送って別のuser_idへ
プロファイルを引き継ぐ」という再連携フローとは異なる用途で使われている。

- **course-set-pasha**(`user_id_linking.py`の`resolve_linking_code()`→
  `handle_form_submission_with_linking_code()`): 連携コードは申込フォーム(GAS Webhook)の
  送信者を最初にひも付けるためだけに使われ、`handle_form_submission()`は与えられた
  `user_id`に対して`gym_area_pairs`・`email`を上書き設定するのみ(`application_form_
  submission_flow.py`)。別のuser_idから既存プロファイルのフィールド(`subscription_
  canceled_at`を含む決済関連フィールド一式)を移し替える処理は存在しない。
- **kura-pasha**(`workshop_linking.py`の`resolve_linking_code()`→
  `create_workshop_from_linking_code()`): 連携コードは新規workshop作成時にのみ使われ、
  解決したuser_idが既にworkshopへ所属済みの場合は新規作成せず`already_linked=True`を
  返すのみ(2重作成防止の防御的分岐であり、既存プロファイルを他のuser_idへ移し替える
  処理ではない)。workshopのuser_id割り当ては`create_workshop_from_linking_code()`実行時に
  一度確定した後、他のuser_idへ引き継ぐ経路自体が無い。

すなわち両venture共通で、「一度確定したuser_idに紐づくプロファイル(決済状態を含む)を
別のuser_idへ移し替える」という再連携の概念そのものが存在しない。aircon-pashaがこの
概念を持つのは、本venture固有のuser_id_linking.mdの再連携設計(LINEのブロック解除・
再フォロー等でuser_idが変わり得る運用を前提とした設計)によるものであり、他2venture側の
プロファイル管理はuser_idを不変の主キーとして扱う設計のため、同型の「引き継ぎ漏れ」は
構造的に発生し得ないと判断した。

なお、line-reservation-aiは本論点の対象外として確認していない(subscription-canceled-
block-crosscheck.md(line-reservation-ai)が既に扱った「解約確定の専用分岐の有無」とは
別の論点だが、line-reservation-aiは`suspension_reason`を店舗単位の単一フィールドとして
持つ設計であり、店舗のuser_idが変わる再連携という概念自体が無いことは既存確認内容から
明らかなため、追加確認は不要と判断した)。

## 結論・次回候補

コード変更は行わず、確認・文書化のみ。回帰確認として`python3 -m unittest discover
-s prototype -p "test_*.py"`610件・`python3 schema/validate_test_cases.py`25件、
いずれも変更前と同じ結果でパスを確認した。承認が必要なアクション(支払い・アカウント
作成・外部公開・送信等)は今回発生していないためpending-approval.mdへの追記なし。

次回候補: (1)実Stripeアカウント接続(オーナー承認待ち)、(2)候補研究は第五十九弾で
打ち切り済みのため、character-limit-fallback-design.mdのソフト閾値検討等、実LLM接続後の
実運用データを要するもの以外の未着手領域の棚卸し、(3)他venture・アイデア領域の前進。
