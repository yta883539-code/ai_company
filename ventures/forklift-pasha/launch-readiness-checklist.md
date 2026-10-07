# forklift-pasha 公開までのチェックリスト(フェーズ94時点)

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
- 特商法表記・プライバシーポリシー草案(legal-notices-draft.md): 他venture対比で
  未着手だったcross-venture parityギャップを解消し、フェーズ94で新規作成(【要記入】
  箇所あり、実際のLP公開は別途オーナー承認が必要)。
- 決済時の本人確認方式(payment-identity-verification-design.md): LINE非依存のため
  LIFF経由IDトークン検証が使えない本venture固有の課題として、フェーズ95でアクセス
  トークン方式を設計(operator_idをランダム発行方式に確定、firestore-data-model.md
  も合わせて更新)。フェーズ96でドキュメントID(internal_id)とアクセストークンを分離し
  (access-token-reissue-design.md)、フェーズ97で実ファイルに反映、フェーズ98で
  `accessToken`の有効期限方針を無期限に確定した。

## 承認待ち事項(pending-approval.md記載の要約)

1. **建荷協(本部・Aランク7支部)・都道府県労働局(千葉・岐阜)への電話・メール連絡**
   (2026-10-05 21:00 UTC記載)
   kenkakyo-proposal-draft.md・branch-outreach-individual-drafts.mdで下書き済みの
   提案文面(提案パスA: 会員向け付加サービス提案/パスB: 広報チャネル活用提案/
   パスC: 都道府県労働局向け)を用いた実際の対外連絡。
   → 承認後: 電話連絡はオーナー自身が行い、メール送信はメール連携接続後に
   送信直前の毎回確認を経てのみ行う(line-reservation-ai等の既承認案件と
   同じ運用)。
   **時期的な緊急性**: kenkakyo-proposal-draft.mdフェーズ47・53(2026-10-04〜05)の
   調査により、提案パスB・Cが紹介機会として想定する「特定自主検査強調月間」
   (毎年11月、2026年版スローガン「災害の 危険の芽を摘む 特自検」制定済み)の
   開始まで、本日(2026-10-06)時点で残り約25日。フェーズ53では「月間開始前
   (10月頃)の接触が望ましい」との仮説も記録済みであり、承認・電話連絡・
   建荷協側の月間準備(例年10月下旬〜11月上旬に労働局通達)のリードタイムを
   踏まえると、10月中の承認が得られないと今年度の月間に合わせた紹介機会を
   逃す可能性がある。

2. **Stripeアカウントの開設**(2026-10-06 22:00 UTC記載)
   本venture稼働に必須の実際のStripeアカウント開設(本人確認・銀行口座登録を含む)・
   本番用APIキー・Webhook署名シークレットの取得・`plan_id`→Price ID対応表確定・
   Webhookエンドポイント登録。他venture(course-set-pasha・kura-pasha・aircon-pasha)で
   発見された同種の記載漏れ(フェーズ94でlegal-notices-draft.md作成時に本venture側の
   記載漏れも発見・是正)。
   → 承認後: 実APIキー・Webhookシークレットの設定、plan_id→Price ID対応表の確定から
   着手する。なお本ventureはLINE非依存のWebフォームであり、LIFF経由IDトークン検証は
   前提としないため、決済時の本人確認方式は別途検討が必要だったが、フェーズ95で
   payment-identity-verification-design.md(アクセストークン方式)として設計済み。

本ventureは他4ventureと異なり、LINE公式アカウントの開設は入力チャネルがLINE非依存の
汎用Webフォーム(tech-stack.mdフェーズ70暫定決定)であるため不要と見込まれる。上記2の
Stripeアカウント開設が、本venture稼働に必須の外部サービス契約としては現時点で唯一の
記載済み事項である。

## 次回候補

上記1・2のいずれかがオーナーから承認された場合、その着手を最優先とする。上記1は
時期的な緊急性(月間開始まで残り約25日)があるため、承認判断自体を急いでいただきたい
旨を次回のオーナー向け案内でも明示する。承認が得られるまでの間は、(1)annual区分の
法定保存義務との整合確認(legal-notices-draft.md次回候補(1))、(2)data-retention-
policy.mdの切り出し、または他venture・アイデア領域の前進を行う。
(access-token-reissue-design.mdフェーズ98が次回候補とした`lastAccessedAt`表示の実装
検討は、フェーズ99でfirestore-data-model.mdへのフィールド追加・更新タイミング・表示方法
の確定まで完了した。)

最終更新: 2026-10-06 22:00 UTC(フェーズ94: 他venture対比で未着手だった
legal-notices-draft.mdを新規作成し、その過程で発見したStripeアカウント開設の
記載漏れを承認待ち事項2として追加した。コード変更なし、テスト4ファイル・
schema検証11件・ブラウザ検証17件いずれもパス)
最終更新: 2026-10-06 23:00 UTC(フェーズ95: 次回候補(3)だった決済時の本人確認方式
〈LIFF非依存〉をpayment-identity-verification-design.mdとして設計し、アクセス
トークン方式に確定。firestore-data-model.mdのoperator_id割り振り方針も合わせて
更新した。コード変更なし、テスト4ファイル・schema検証11件・ブラウザ検証17件
いずれもパス)
最終更新: 2026-10-07 03:00 UTC(フェーズ98: payment-identity-verification-design.md
〈フェーズ95〉の残課題だった`accessToken`有効期限方針を無期限に確定し、
access-token-reissue-design.md「5.」に決定理由を記録。副作用として
`lastAccessedAt`表示案を次回候補に追加した。コード変更なし、テスト4ファイル・
schema検証11件・ブラウザ検証17件いずれもパス)
最終更新: 2026-10-07 04:00 UTC(フェーズ99: フェーズ98次回候補だった`lastAccessedAt`
〈最終アクセス日時〉を、firestore-data-model.mdの`fleet_operator`にフィールド追加し、
access-token-reissue-design.md「6.」に更新タイミング〈設定ページアクセス時のみ〉・
表示方法〈前回アクセス時点の値を表示〉を設計した。コード変更なし、テスト4ファイル・
schema検証11件・ブラウザ検証17件いずれもパス)
