# line-reservation-ai 公開までのチェックリスト(フェーズ続き286時点)

目的: kura-pasha(launch-readiness-checklist.md)と同様、設計・実装・テストは完了している
一方で実際の稼働にはオーナー承認が必要な外部サービス設定・実LLM呼び出しが複数残っている。
オーナーがpending-approval.mdを一つずつ確認する際に迷わないよう、本ventureに関わる承認待ち
事項を依存順に並べ、承認後すぐ着手できる作業内容を1箇所にまとめる。

## 現状(実装・検証済み、追加作業不要)

- 会話フロー本体(候補提示→確定)・二重予約防止(BookingSlotManager)・空き枠検索
  (AvailabilitySearcher)・保留タイムアウト・キャンセル/変更intent処理: prototype/engine.py
  として実装済み、デモシナリオ・自動テストで動作確認済み。
- 構造化出力(JSON)スキーマ(schema/booking_output.schema.json)・リトライ/フォールバック・
  エスカレーション集約通知・通知ログのユニーク集計: 机上検証(schema/validate_test_cases.py)
  まで完了。
- Stripe Checkout Session発行・Webhook受信/署名検証/イベントディスパッチ、および配信順序
  入れ替わりガード(subscription側・dunning側・checkout.session.completed側すべて):
  フェーズ続き282〜285で対応完了。他venture(aircon-pasha・course-set-pasha・kura-pasha)
  との横断確認も済み。
- venture全体`python3 -m unittest discover -s prototype -p "test_*.py"`891件・
  schema検証28件(`python3 schema/validate_test_cases.py`)いずれもパス(2026-09-28時点)。
- 想定顧客ヒアリング候補選定(美容室・整体院・パーソナルジム・学習塾、候補ロングリスト
  第一弾〜第二十一弾)・連絡文面ドラフト(初回コンタクト依頼文面草案)・LP文言草案
  (landing-page-copy-draft.md)・特定商取引法表記/プライバシーポリシー草案
  (legal-notices-draft.md): 作成済み。
- LP HTML/CSS実装ドラフト(landing-page/index.html、2026-10-01 23:00 UTC追加、
  aircon-pasha 2026-10-01 22:00 UTC作成分と同じ位置づけ): ローカルの静的ファイルのみで
  ドメイン取得・ホスティング・外部公開は未実施、CTAは非活性のプレースホルダー。公開自体は
  下記承認待ち事項(LINE公式アカウント開設等)と合わせて別途オーナー承認が必要。

## 承認待ち事項(依存順、pending-approval.md記載の要約)

1. **実LLM API呼び出しによる自動テスト**(2026-07-31 13:58 UTC記載)
   schema/validate_test_cases.pyで机上検証したシステムプロンプト・構造化出力スキーマを、
   実際のLLM API(Claude API等)に投入してconversation-samples-test-cases.mdの各ケース
   (N1〜N4、E1〜E16)を自動テストしたい。APIキー取得(アカウント作成)・従量課金(支払い)を
   伴うため未承認。
   → 承認後: APIキー取得方法の提示・テストスクリプトの実装から着手する。

2. **LIFFアプリ登録 + LINE公式アカウント開設**(2026-08-28 17:00 UTC記載)
   本venture用LIFFアプリ登録(なりすまし防止のIDトークン検証に必要)、LINE公式アカウントの
   開設(Basic ID確定、決済完了後にLINEへ戻るユニバーサルリンクの組み立てに必要)。
   → 承認後: LIFFアプリのURL・スコープ設定、IDトークン検証処理の実装、LINE公式アカウントの
   Basic ID確定・`build_line_return_link()`への反映から着手する。

3. **想定顧客ヒアリングの実施**(2026-07-30 01:58 UTC記載・承認済み、Instagram DM等での
   個別連絡自体は未実施)
   候補ロングリスト(candidate-longlist-draft.md)のうち優先度B候補(9・11・1・10・17)への
   実連絡は、interview-request-package.md記載の未確定事項(謝礼有無・送信者名表記・
   返信先連絡先)へのオーナー回答待ちの段階にある。
   → オーナー回答後: 文面案を使い電話・LINEでの実連絡はオーナー自身が行うか、
   Gmail連携接続後に送信直前の毎回確認を経てメール送信を行う。

## 次回候補

上記1〜3のいずれかがオーナーから承認・回答された場合、その着手を最優先とする。それまでの
間は、他venture・アイデア領域の前進、または本チェックリストとpending-approval.mdの記載に
齟齬がないかの定期的な棚卸しを行う。
