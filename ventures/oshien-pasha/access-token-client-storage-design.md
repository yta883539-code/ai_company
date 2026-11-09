# 決済結果ページにおける`access_token`のクライアント側保持方針

作成日: 2026-11-09(フェーズ101)

checkout-result-http-entry-point-design.md(フェーズ100)3節・4節が残した課題「`access_token`
をレスポンス本文に含めたままクライアント側でどう保持するか」について、data-retention-policy.md
の観点から検討する(README.mdフェーズ100「次回候補(2)」対応)。

## 1. 検討対象となる3つの選択肢

1. **Cookie**: サーバー側で`Set-Cookie`して以後のリクエストに自動添付する方式。
2. **localStorage**: ブラウザに永続保存し、タブを閉じても次回訪問時に読み出せる方式。
3. **sessionStorage(またはメモリ上の変数のみ)**: タブ/ウィンドウを閉じると消え、ページ遷移の
   間だけ保持される方式。

## 2. 方針: sessionStorageのみを採用し、Cookie・localStorageは採用しない

- **Cookieを採用しない理由**: 本エンドポイントはCloud Run上のバックエンドAPI
  (`receive_checkout_result_request()`)がJSONレスポンスを返す構成であり、`Set-Cookie`で
  `access_token`を自動送信対象にする必要性がない。むしろCookieにすると、もちだしパシャっと
  (CWE-614/1004、Secure/HttpOnly/SameSite属性欠落)のチェック対象を自ら増やす上に、
  本venture唯一の継続課金識別子を毎リクエスト自動送信することになり、CSRF対策
  (れんだパシャっと系と別軸の論点)まで検討範囲が広がる。結果ページから次画面への遷移にしか
  使わない値にその複雑さを持たせる必要はない。
- **localStorageを採用しない理由**: data-retention-policy.md 2節が「都度プランの入力・出力は
  原則永続レコードを持たない」「月額フリーパスの`accessToken`自体はサーバー側(Firestore
  `fan_pass/{internal_id}`)で1年保持する」と整理したのは**サーバー側**の話であり、
  クライアント側(ブラウザ)に同じ値をさらに無期限保持する理由にはならない。むしろ
  localStorageは同一オリジンの他のJS(将来追加されるかもしれない計測タグ等)からも読み取れる
  上、端末を共有利用するケース(例: 会場で友人の端末を借りて決済する場合)で次回利用者に
  前利用者の`access_token`が残り続けるリスクがある。monthly-pass-identity-design.md4節が
  想定する「再契約時の`accessToken`継続利用」は、そもそもメール経由の再発行フロー
  (access-url-resend-http-entry-point-design.md)で担保されており、クライアント側の永続
  保存に依存しない設計になっている。したがって本画面でlocalStorageに保存するメリットは
  存在しない。
- **採用: sessionStorage**。決済結果ページの読み込み時にレスポンス本文の`access_token`を
  `sessionStorage`に一時保持し、同タブ内での「準備中→完了」の再ポーリング・次画面への遷移
  にのみ使う。タブを閉じれば自動的に消え、ブラウザのJSヒープ上に長時間値を持ち続ける
  素朴なグローバル変数方式よりも、ページ遷移(結果ページ→生成物表示ページ)をまたいで値を
  引き渡せる点でsessionStorageを優先する。

## 3. 実装方針(次回以降のコード化に向けたメモ)

- 結果ページ(フロントエンド、未実装)の擬似フロー:
  1. `fetch('/checkout-result?checkout_session_id=...')`のレスポンスを受け取る。
  2. `status === "ready"`なら`sessionStorage.setItem('oshien_pasha_access_token', access_token)`
     した上で次画面へ`location.href`遷移する。
  3. `status === "pending"`なら`sessionStorage`には書き込まず、interval_seconds相当の間隔で
     再度同エンドポイントをポーリングする(poll_attempts_usedの上限はサーバー側で既に
     `max_attempts`として管理済み、checkout-result-http-entry-point-design.md 2節)。
  4. 次画面はページ読み込み時に`sessionStorage.getItem(...)`で値を取り出し、以後の画面内
     API呼び出し(未設計、生成結果取得用の別エンドポイントが必要になった場合)にのみ使う。
     使い終わった後の明示的な`sessionStorage.removeItem(...)`呼び出しは、次画面自体の設計
     (未着手)で検討する。
- 本venture全体がLINE非依存のためLIFF SDKのトークン管理機構(他6venture)を流用できない点は
  tech-stack.md既出のとおりだが、sessionStorageはブラウザ標準APIであり追加ライブラリ・
  追加のGCPリソースを必要としない。「小規模・自動起業可能」の前提(初期投資ほぼ不要)に
  適合する。

## 4. 残課題

- 次画面(生成物表示ページ)自体の設計・実装は本フェーズの対象外。`sessionStorage`から
  取り出した`access_token`を使って何を取得するか(4出力をこの時点で既にレスポンスに含めて
  渡すのか、別エンドポイントを新設するのか)は未確定であり、次画面の設計時に改めて検討する。
- 結果ページ自体のフロントエンド実装(HTML/JS)は、他の未着手フロントエンド項目
  (landing-page以外)と同様、実Cloud Functions/Cloud Runデプロイがオーナー承認待ちである
  ことと合わせて次回以降の課題として残る。
- 本方針はクライアント側の保持方法のみを扱う。サーバー側の`accessToken`保存期間
  (1年)・削除方針はdata-retention-policy.mdの既存記載のまま変更しない。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成・
実際のHTTPデプロイ自体はオーナー承認が必要なアクションに該当するため、本メモは設計・方針の
検討に留める(外部サービスへの接続・フロントエンドコードの実装は一切行っていない)。承認が
必要なアクション(支払い・アカウント作成・外部公開・送信等)は本フェーズでは発生していない
ためpending-approval.mdへの新規追記は不要(既存の承認待ち事項の範囲内で扱う)。

最終更新: 2026-11-09 02:00 UTC(フェーズ101: checkout-result-http-entry-point-design.md
フェーズ100の残課題に対応し、決済結果ページにおける`access_token`のクライアント側保持方針を
sessionStorage採用・Cookie/localStorage非採用として決定した)
