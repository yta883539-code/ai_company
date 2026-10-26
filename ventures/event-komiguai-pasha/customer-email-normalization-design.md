# customer_email 照合ロジックの詳細設計(フェーズ56)

draft-id-last4-collision-design.md(フェーズ53)6節で「実装時の詳細設計として残す」と
していた、`customer_email`の実際の照合ロジック(大文字小文字・前後空白の正規化、
全角/半角等)を本フェーズで確定する。

## 1. 入力が揺れる想定経路

`customer_email`は2つの異なる入力経路を通ってFirestore上で突き合わせられる
(draft-id-last4-collision-design.md 4節)。

1. **決済経路**: Stripe Checkout Session作成時に主催者が入力し、Webhook受信時に
   `one_time_draft/{draft_id}`へ保存される値(ttl-expiry-result-delivery-refund-
   design.md フェーズ12 2節)。
2. **問い合わせ経路**: inquiry-handling-design.md(フェーズ15)の問い合わせフォームに
   主催者が改めて手入力する値(`inquiry/{inquiry_id}.customer_email`)。

同一人物であっても、2回の入力タイミング・入力環境(スマートフォンの日本語IME等)が
異なるため、文字列として完全一致しない揺れが生じ得る。これを吸収しないまま
文字列比較すると、draft-id-last4-collision-design.md 4節で確定した二段階照合
(末尾4文字→`customer_email`一致)の2段目が機能せず、同venture共通方針である
「AIは判断主体にならず機械的な照合に留める」設計が崩れる。

## 2. 正規化ルール

他「パシャっと」系ventureのメールアドレス系フィールドに共通する正規化方針はまだ
存在しないため(cross-venture-inquiry-collection-naming-parity-review.mdは命名統一の
観点のみで、値の正規化には触れていない)、本venture単独で以下を確定する。

1. **NFKC正規化**: 日本語IME変換時に全角英数字・全角記号(`＠`・`．`等)が混入する
   ケースを吸収するため、Unicode正規化形式NFKC(`unicodedata.normalize("NFKC", s)`)を
   最初に適用する。全角`Ａ-Ｚ０-９＠．－＿`等は対応する半角文字に変換される。
2. **前後の空白除去**: 半角スペース・全角スペース(`　`)・タブ・改行をNFKC後に
   `strip()`で除去する。NFKC適用後は全角スペースも半角スペースに正規化されるため、
   標準の`str.strip()`で両方除去できる。
3. **小文字化**: `str.lower()`を適用する。RFC 5321上はローカル部(`@`より前)の
   大小文字を区別する実装が理論上あり得るが、実務上主要なメールプロバイダ
   (Gmail・Yahoo!・各種キャリアメール等、本venture想定顧客である個人主催者が
   使う可能性が高い層)はローカル部の大小文字を区別しないため、他venture
   (line-reservation-ai等)のメールアドレス比較方針との整合も考慮し、実務優先で
   大小文字を区別しない方針を採用する。
4. **ドット・プラスエイリアス等のプロバイダ固有の揺れは吸収しない**: Gmailの
   「ドット無視」「`+`以降無視」等はプロバイダ固有の仕様であり、プロバイダ判定を
   要するため本venture規模では過剰設計と判断し対応しない。同一人物が決済時と
   問い合わせ時に別のエイリアス表記を使った場合は二段階照合の2段目で不一致となるが、
   draft-id-last4-collision-design.md 4節で既に確定済みの最終手段
   (`category`・`detail`と結果ページ内容をオーナーが目視で照合する手動対応)に
   委ねる。

## 3. 一致判定関数

上記正規化を適用した上で文字列完全一致を判定する。正規化後の空文字列同士
(両方が空という異常系)は意図的に不一致として扱う(必須項目のため実運用では
発生しない想定だが、空文字列の取り扱いを明示しておく)。

```
normalize_customer_email(raw: str) -> str
    1. unicodedata.normalize("NFKC", raw)
    2. .strip()
    3. .lower()

customer_emails_match(a: str, b: str) -> bool
    normalize_customer_email(a) と normalize_customer_email(b) を比較する。
    どちらかの正規化後の結果が空文字列の場合は常にFalse。
```

## 4. prototype実装

`prototype/customer_email_matching.py`として実装し、`prototype/
test_customer_email_matching.py`で以下の観点のテストケースを設けた(14件)。

- 前後の半角/全角空白の除去
- 大文字小文字の違いの吸収
- 全角英数字・全角`＠`・全角`．`のNFKC正規化による半角化
- 全角と半角が混在した入力同士の一致判定
- 完全に異なるメールアドレスの不一致判定
- 両方・片方が空文字列(またはstrip後に空文字列になる空白のみの入力)の場合の
  不一致判定(異常系)
- `None`相当の入力は呼び出し側の必須項目チェック(inquiry-handling-design.md)で
  防ぐ前提のため、本関数は`str`入力のみを対象とする(契約として未対応)

## 5. 更新箇所

- draft-id-last4-collision-design.md 6節: 「`customer_email`の実際の照合ロジック」の
  残課題を本フェーズで解消済みとして取消線化。

## 6. 未検証・残課題

- オーナー向け検索UI(どこで末尾4文字検索・`customer_email`一致確認を行うか)自体は
  未設計(Firestoreコンソール上の手動操作を想定しているが、件数が増えた場合の
  専用管理画面の要否は次回以降の検討課題)。
- 実LLM呼び出し・実Firestore接続はいずれもオーナー承認待ちの範囲(pending-
  approval.md参照)。今回は正規化ロジックの机上設計・prototype実装のみに留める。

次回候補: (1)承認待ち事項(候補1〈奈良NEVER LAND〉への電話連絡等)がオーナーから
承認された場合はその着手を最優先、(2)対象候補のロングリスト作成(フェーズ9から
持ち越し)、(3)市場仮説を踏まえたcustomer-interview-design.mdのヒアリング対象候補への
反映(フェーズ13から持ち越し)、(4)オーナー向け検索UIの要否検討、(5)他venture・
アイデア領域の前進。

最終更新: 2026-10-26 03:00 UTC(フェーズ56: `customer_email`照合ロジック(NFKC正規化・
前後空白除去・小文字化)を確定し、prototype/customer_email_matching.pyとして実装。
unittest 14件追加、既存schema検証22件・既存prototype試験35件は変更なしでパス)
