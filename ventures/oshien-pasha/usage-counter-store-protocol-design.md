# UsageCounterStoreProtocol相当のインターフェース設計(フェーズ37)

firestore-data-model.md(フェーズ36)「4. 未確定・残課題」が次回候補(1)として残した、
生成回数カウンタ(`currentMonthGenerationCount`・`generationCountMonth`・
`generation_log`サブコレクション)に対する`UsageCounterStoreProtocol`相当の
インターフェース設計に対応する。本venture自身は`prototype`ディレクトリが未着手の
ため、kura-pasha/course-set-pashaの`UsageCounterProtocol`(`cloud_function_webhook.py`)
の記法に倣い、本フェーズでは実ファイル化前の設計メモとしてインターフェース定義を
確定させるところまでを範囲とする。

## 1. 対象範囲の確認(generation-count-design.mdとの関係)

generation-count-design.md(フェーズ8)が確定した構造は、kura-pasha等の「月間上限との
比較」を目的とする`UsageCounterProtocol.get_count`/`increment`とは目的が異なり、
「異常検知用の内部ログ」である。したがって本インターフェースは、kura-pashaの
`get_count(user_id, month) -> int`のような単純な数値取得ではなく、(a)1回の生成
リクエストごとに`generation_log`へ1件追記する、(b)同時に`currentMonthGenerationCount`を
加算する、という2つの書き込みを1メソッドで原子的に行う契約を主に持つ。

## 2. インターフェース定義(案)

```python
class UsageCounterStoreProtocol(Protocol):
    def record_generation(
        self,
        internal_id: str,
        *,
        requested_at: datetime,
        venue_matched: bool,
        input_performance_count: int,
    ) -> int:
        """1回の生成リクエストを記録し、記録後のcurrentMonthGenerationCountを返す。

        実装側は以下を単一書き込み(Firestoreではトランザクション)として行う契約と
        する(kura-pashaのAtomicNoticeUsageCounterProtocol.increment_and_mark_noticeと
        同様、複数フィールドの原子性を担保する目的):
          1. fan_pass/{internal_id}.generationCountMonthが当月文字列
             (current_month_jst()形式の"YYYY-MM")と不一致であれば、
             currentMonthGenerationCountを0にリセットしてからgenerationCountMonthを
             当月値に更新する(generation-count-design.md 2節のリセット判定)。
          2. fan_pass/{internal_id}.currentMonthGenerationCountを1加算する。
          3. fan_pass/{internal_id}/generation_log配下へ自動生成IDで1ドキュメント
             追記する({requestedAt, venueMatched, inputPerformanceCount})。
        呼び出し自体(internal_idに対応するfan_passドキュメントが存在しない等)が
        失敗した場合は例外を送出する契約とする(実Firestore接続はオーナー承認待りの
        ため未実装)。
        """
        ...

    def get_current_month_count(self, internal_id: str) -> int:
        """fan_pass/{internal_id}.currentMonthGenerationCountを読む。

        generationCountMonthが当月文字列と不一致の場合は0を返す(リセット前提、
        kura-pashaのget_countと同じ「読み取り時はリセット書き込みを行わず0返却に
        留める」方針を踏襲。実際のリセット書き込みはrecord_generation呼び出し時にのみ
        発生する)。将来、本メソッドの戻り値を異常検知の閾値判定(generation-count-
        design.md 3節、未確定)に使う想定だが、本フェーズでは閾値判定ロジック自体は
        設計対象外のまま残す。
        """
        ...
```

## 3. 設計判断の根拠

- `record_generation`を単一メソッドに統合した理由: generation-count-design.mdの
  構造は「カウンタ加算」と「ログ追記」が常に1対1で発生し、どちらか一方だけが
  書き込まれる状態(カウンタだけ加算されたがログが欠落、またはその逆)は異常検知の
  信頼性を損なう。kura-pashaが`increment`と`increment_and_mark_notice`を分けたのは
  「通知済みフラグの更新を伴う場合とそうでない場合がある」という条件分岐が理由だが、
  本venture固有の`generation_log`追記はgenerate処理が成功した場合に常に発生する
  (条件分岐が存在しない)ため、2メソッドに分ける理由がなく単一メソッドで十分と判断した。
- `month`引数を持たない理由: kura-pashaの`get_count(user_id, month)`はmonthを呼び出し側
  (アプリケーション層)が渡す設計だが、本venture固有の「異常検知用ログ」という目的上、
  常に「現在時刻時点の当月」を基準にリセット判定する(過去の任意月を指定して参照する
  ユースケースが存在しない)ため、`get_current_month_count`はinternal_idのみを引数とし、
  当月判定は実装側(current_month_jst()相当)に委ねる設計とした。
- `internal_id`キーである理由: firestore-data-model.md(フェーズ36)が確定した
  `fan_pass/{internal_id}`ドキュメント構成にそのまま対応させる(kura-pashaが
  `usage_counter`を`user_id`から`workshop_id`へ移行した経緯(usage-counter-workshop-
  key-design.md)と異なり、本ventureは1契約=1利用者のため複数利用者で1枠を共有する
  概念がなく、当初からfan_pass自身のドキュメントキーと同一のinternal_idで一貫させられる)。

## 4. schema/output.schema.json・validate_test_cases.pyへの影響

usage-counter-workshop-key-design.md(kura-pasha)・firestore-provider-adapter-design.md
(course-set-pasha)と同様の確認を行った結果、`UsageCounterStoreProtocol`が扱う
`currentMonthGenerationCount`・`generationCountMonth`・`generation_log`はいずれもLLMの
構造化出力ではなく生成リクエスト処理のサーバー側ログ・カウンタであるため、
schema/output.schema.jsonの`required`/`properties`定義には変更が発生しない。
validate_test_cases.pyの各TEST_CASESフィクスチャ(1回の生成リクエストに対する出力形の
検証)にも影響はない。よって本フェーズでは両ファイルへの編集は不要と結論づける。

## 未検証・残課題

- 本ファイルはインターフェース定義の確定のみであり、`prototype`ディレクトリ自体が
  本venture未着手のため、`InMemoryUsageCounterStore`相当の検証用実装・実Firestore
  接続アダプタ(kura-pashaのfirestore_usage_counter_adapter.py相当)の作成は次回以降の
  課題として残す。
- 異常検知の具体的な閾値・検知時の対応方針(generation-count-design.md 3節、既存の
  残課題)は、本フェーズのインターフェース設計でも確定させていない
  (`get_current_month_count`の戻り値を将来の閾値判定に使える形にする、という設計方針
  の確認のみに留めた)。
- venue-master-draft.mdの各会場アクセス情報精査・会場名表記揺れの名寄せ方法の検討は
  本フェーズの範囲外、未着手のまま持ち越し。

実LLM呼び出し・Stripe等決済代行サービスとの実接続、実際のFirestore・GCPプロジェクト作成自体は
オーナー承認が必要なアクションに該当するため、本メモは設計の整理に留める(コード実装・外部
サービスへの接続は一切行っていない)。承認が必要なアクション(支払い・アカウント作成・外部
公開・送信等)は本フェーズでは発生していないためpending-approval.mdへの新規追記は不要
(既存の承認待ち事項〈GCPプロジェクト・Firestoreデータベース作成〉の範囲内で扱う)。

最終更新: 2026-10-31 15:00 UTC(フェーズ37: firestore-data-model.md〈フェーズ36〉の次回候補
(1)に対応し、`UsageCounterStoreProtocol`相当のインターフェース(`record_generation`・
`get_current_month_count`の2メソッド)を設計した。generation-count-design.mdが「異常検知用
ログ」として確定した目的に合わせ、カウンタ加算とログ追記を単一メソッドで原子的に行う契約と
した。prototypeディレクトリ自体の新規作成〈検証用実装・実Firestoreアダプタ〉は次回以降の
課題として残した)
