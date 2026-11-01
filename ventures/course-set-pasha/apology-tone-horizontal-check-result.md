# 謝罪表現方針記述と実装の不一致、横展開確認結果(フェーズ346)

フェーズ345の次回候補(2)「同種の謝罪表現方針記述と実装の不一致がaircon-pasha・
event-komiguai-pasha・oshien-pasha・line-reservation-ai側にも残っていないかの横展開確認」
に対応し、各ventureの`tone-and-manner-guideline.md`(存在する場合)と実装文言を確認した。

確認の基準(フェーズ345で本venture自身に適用した基準、forklift-pashaフェーズ200起点):
謝罪表現の要否は決済失敗の原因ではなく、**生成機能が実際に一時停止していた期間が
生じたか否か**で判断する。猶予期間中(生成が一度も止まっていない)の決済確認通知には
謝罪語を含めるべきではない。

## aircon-pasha: 問題なし

`prototype/payment_recovery_notification.py`の`PAYMENT_RECOVERED_MESSAGE`
(制限モードからの復旧)・`PAYMENT_CONFIRMED_IN_GRACE_MESSAGE`(猶予期間中の決済確認)
を確認したところ、いずれも謝罪語を一切含まない(「作業完了報告・お手入れ案内の生成を
再開しました」「ご確認事項は解消されました」という事実のみの文言)。本venture・
course-set-pashaの基準(実際に止まっていた場合のみ謝罪)よりもさらに厳格(どちらの
ケースでも謝罪なし)であり、矛盾は生じていない。是正不要と判断する。

## event-komiguai-pasha: 対象外(該当パターンが存在しない)

本ventureは単発決済・アカウント登録なしのB2C型サービス(one-time-checkout-no-account-
design.md)であり、line-reservation-ai・aircon-pasha・kura-pasha・course-set-pashaのような
「サブスクリプション決済失敗→制限モード→決済復旧」という継続課金・一時停止の構造自体を
持たない。決済関連の謝罪表現は`ttl-expiry-result-delivery-refund-design.md`の「生成処理に
失敗したため全額返金した」案内文言のみであり、これは生成失敗(本venture側の処理失敗)に
対する謝罪であって「猶予期間中は止まっていないのに謝罪する」という本検証対象のパターンとは
性質が異なる。tone-and-manner-guideline.md(フェーズ80)の方針3でも「主催者側の過失に
よらない失敗」への言及はあるが対象は生成失敗・返金であり、本検証のテーマ(生成停止有無による
謝罪の要否)とは論点が異なるため、本venture側には是正対象が存在しないことを確認した。

## oshien-pasha: tone-and-manner-guideline.md自体が未作成(既知の別ギャップ)

event-komiguai-pashaのtone-and-manner-guideline.md(フェーズ80冒頭の記述)によれば、
oshien-pashaはフェーズ50で別ギャップ(llm-system-prompt-draft.md未作成)を優先したため、
tone-and-manner-guideline.md未作成のギャップ自体は本日時点でも解消されていないことを
`ls ventures/oshien-pasha/`で確認した。謝罪表現の方針記述自体が存在しないため、本検証
(方針記述と実装の不一致の検出)の対象外であり、「記述と実装が食い違っている」という
状態ではなく「記述が存在しない」という別種のギャップである。oshien-pasha自身の今後の
フェーズでtone-and-manner-guideline.mdを新規作成する際に、本検証基準(生成停止有無による
謝罪要否)も踏まえて設計することを申し送り事項として記録する(oshien-pasha側での対応は
本venture側からは実施しない)。

## line-reservation-ai: 不一致を発見(申し送り、本venture側では修正しない)

`prototype/dunning_notification_scheduler.py`の`_MESSAGE_RECOVERED`(制限モードからの復旧)
は「ご不便をおかけし、誠に申し訳ございませんでした」(formal)等、実際に生成(予約受付)が
止まっていた場合の謝罪であり基準に合致する。一方`_MESSAGE_PAYMENT_CONFIRMED_IN_GRACE`
(猶予期間中、予約受付は一度も止まっていない場合)にも「お手数をおかけし、誠に申し訳
ございませんでした」(formal)・「お手数をおかけしました」(standard)・「お手数かけて
すみませんでした」(casual)という謝罪語が含まれている。コード内コメント自身が「予約受付が
止まっていない状態のため『再開しました』とは書けない」と明記しているにもかかわらず、
謝罪語自体は`_MESSAGE_RECOVERED`と同様に残っており、本検証基準(生成停止がない場合は
謝罪不要)との不一致が存在する。

ただしこの謝罪は「予約受付が止まっていたこと」への詫びではなく「決済確認のお手数を
かけたこと」への詫びであり、kura-pasha(forklift-pashaフェーズ200が発見した事例、決済失敗の
原因を問わず画一的に謝罪していた)とは謝罪の対象がわずかに異なる可能性がある。この文言が
本検証基準の「要修正」に該当するか(決済の手間自体への軽い謝意は許容されるか)は、
line-reservation-ai自身のtone-and-manner-guideline.md方針3(「謝罪はしつこくしすぎない」)
を踏まえた判断が必要であり、本venture(course-set-pasha)側からの一方的な修正は行わず、
line-reservation-ai自身の次回フェーズでの確認・判断に委ねることとし、ここに申し送り事項として
記録する。

## 本venture(course-set-pasha)側の結論

本フェーズでの確認はいずれも他venture側の状態確認・記録に留まり、本venture自身のコード・
設計文書の変更は発生していない。コード変更なし、回帰確認として
`python3 -m unittest discover -s prototype -p "test_*.py"`(863件、変更なし)・
`python3 schema/validate_test_cases.py`(21件、変更なし)を実行しいずれもパスすることを
確認した(回帰なし)。

## 次回候補

1. 承認待ち事項がオーナーから承認された場合はその着手を最優先。
2. (line-reservation-ai自身の今後のフェーズ向け申し送り)
   `_MESSAGE_PAYMENT_CONFIRMED_IN_GRACE`の謝罪語の要否を、本検証基準を踏まえて
   line-reservation-ai自身が判断・必要なら是正する。
3. (oshien-pasha自身の今後のフェーズ向け申し送り)
   tone-and-manner-guideline.md新規作成時に本検証基準を反映する。
4. 他venture・アイデア領域の前進。
