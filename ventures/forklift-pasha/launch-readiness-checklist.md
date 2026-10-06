# forklift-pasha 公開までのチェックリスト(フェーズ92時点)

目的: aircon-pasha・course-set-pasha・kura-pasha・line-reservation-aiの4ventureは
launch-readiness-checklist.mdで承認待ち事項を依存順に一覧化済みだが、本venture
(forklift-pasha)は候補発見・リハーサル設計が中心でまだ同種のチェックリストを
持っていなかった。フェーズ33〜69で間接チャネル(建荷協・都道府県労働局)への
提案文面・送付先候補の準備がほぼ尽くされ、フェーズ88〜91でヒアリングリハーサル
台本の整備も一区切りついた現時点で、承認待ち事項と現状の棚卸しを1箇所にまとめる。

## 現状(設計・検証済み、追加作業不要)

- 市場調査・料金プラン・技術構成(market-research.md・pricing-plan.md・
  tech-stack.md): 作成済み。
- プロトタイプ・テスト: `python3 prototype/run_all_tests.py`(4ファイルOK)・
  `python3 schema/validate_test_cases.py`(11件)・
  `node prototype/browser_mockup_checks.js`(17件)いずれもパス(2026-10-06時点で
  再確認済み)。
- Webフォームモックアップ(web-form-mockup/、daily.html・monthly.html、
  CSS:has()による出し分け方式): 実装済み。
- 間接チャネル探索・提案文面(channel-partner-exploration.md・
  kenkakyo-proposal-draft.md・branch-outreach-priority-ranking.md・
  branch-outreach-individual-drafts.md): 建荷協本部・地方支部(Aランク7支部:
  群馬・山梨・広島・栃木・兵庫・茨城・福岡)・都道府県労働局(千葉・岐阜で
  部署名確認済み)向けの個別提案文面下書きがフェーズ65・67までに揃い、
  フェーズ69で「WebSearchで到達可能な範囲ではほぼ尽くした」と結論済み。
- ヒアリング設計・リハーサル(customer-interview-design.md・
  interview-candidate-selection-criteria.md・interview-rehearsal-script.md・
  rehearsal-timing-desk-estimate.md・mock-interview-responses-draft.md):
  仮想の想定回答者に基づく机上リハーサル・ストレステストまで完了(フェーズ88〜91)。
  実在候補が未確定のため、実際の社内リハーサル(実時間計測)・実在候補への実施は
  いずれも次段階。

## 承認待ち事項(pending-approval.md記載の要約)

1. **建荷協(本部・Aランク7支部)・都道府県労働局(千葉・岐阜)への電話・メール連絡**
   (2026-10-05 21:00 UTC記載)
   kenkakyo-proposal-draft.md・branch-outreach-individual-drafts.mdで下書き済みの
   提案文面(提案パスA: 会員向け付加サービス提案/パスB: 広報チャネル活用提案/
   パスC: 都道府県労働局向け)を用いた実際の対外連絡。
   → 承認後: 電話連絡はオーナー自身が行い、メール送信はメール連携接続後に
   送信直前の毎回確認を経てのみ行う(line-reservation-ai等の既承認案件と
   同じ運用)。

本ventureは他4ventureと異なり、LINE公式アカウント・Stripeアカウント等の
「稼働に必須の外部サービス」契約そのものはまだ承認待ち事項として記録していない
(実在候補確保・初回ヒアリングが先行する段階のため)。実在候補への初回コンタクトが
承認された後、ヒアリング結果を踏まえてLINE公式アカウント・Stripe等の稼働基盤の
承認依頼が生じる見込みである。

## 次回候補

上記1がオーナーから承認された場合、その着手(電話・メール連絡の実施)を最優先とする。
承認が得られるまでの間は、他venture・アイデア領域の前進、または本チェックリストと
pending-approval.mdの記載に齟齬がないかの定期的な棚卸しを行う。

最終更新: 2026-10-06 20:00 UTC(フェーズ92: 本チェックリストを新規作成し、
フェーズ33〜69の間接チャネル提案準備・フェーズ88〜91のヒアリングリハーサル整備の
現状と、承認待ち事項1件〈2026-10-05 21:00 UTC記載〉を1箇所にまとめた。コード変更なし、
テスト4ファイル・schema検証11件・ブラウザ検証17件いずれもパス)
