# Webhook同期reply構成のタイムアウトリスク・根本対策要否の検討(本venture版)

## 背景

line-webhook-event-id-idempotency-design.md(フェーズ286)の「4. 未検証・残課題」に、
以下が未着手事項として残っていた。

> 根本対策の要否: 本フェーズの対策は「重複実行を防ぐ」対症療法であり、「2秒タイムアウトに
> 収まるよう処理自体を非同期化する」(line-reservation-aiのCloud Tasksエンキューパターンへの
> 移行)という根本対策とは別物。後者は3venture共通のアーキテクチャ変更(Function分割)を要し、
> 本ventureの低頻度・オーダーメイド中心という特性(deployment-runbook.md参照)を踏まえると
> 費用対効果の検討が必要なため、今回は対症療法(べき等性チェック)のみを先行させた。

course-set-pashaはフェーズ369でこれと同型の残課題について費用対効果検討
(webhook-sync-reply-timeout-root-cause-review.md)を行い、「根本対策は実施すべき」と結論
づけた上で、「aircon-pasha・kura-pashaも同じreply API+同期LLM呼び出し構成であることが
確認済みのため、本venture側の設計・実装が固まった段階で両ventureへの横展開も次回候補」と
注記していた。しかし横展開の前提として「各venture側の経路構造を個別確認する必要がある」
(同ドキュメント3節)とも明記されており、course-set-pasha側の設計はフェーズ370
(process-memo-event-async-split-design.md)時点でもFunction B実装・dispatch振り分け
実装が未着手の段階にある。本フェーズ(7venture中最も更新が止まっていた本ventureの前進)は、
本venture自身に残っていた上記の費用対効果検討そのもの(course-set-pashaの横展開を待たずに
着手できる、本venture固有の検討)に着手する。

## 1. 本ventureの`process_memo_event()`の経路構造の確認

`prototype/cloud_function_webhook.py`の`process_memo_event()`を確認したところ、
本ventureはcourse-set-pashaよりも経路数が多く、かつ**LLM呼び出しを伴わない経路が
存在しない**という点で、同じ「reply API + 同期LLM呼び出し」構成の中でもタイムアウト
リスクへの露出が course-set-pasha より広いことが判明した。

- `select_message_context()`の`kind`に応じて、以下の4経路いずれかに分岐する
  (message-context-selection-design.md 12節準拠)。
  1. `contractor_transfer_expired_notice` → `_process_contractor_transfer_expired_notice()`
  2. `contractor_transfer_confirmation` → `_process_contractor_transfer_confirmation()`
  3. `member_retention_notice` → `_process_member_retention_notice()`
  4. `generation_request`(通常の受注メモ生成、(d)経路) → 4.以降の`process_memo_event()`
     本体処理
- 上記1〜3の「文脈注入」経路は、course-set-pashaのFAQ固定応答経路(LLM呼び出しなしで
  即時reply)とは異なり、**いずれも`_generate_with_api_retry(llm_call, ...)`を呼び出した
  上で`reply_client`へ返信する**実装になっている(`_process_contractor_transfer_expired_
  notice()`739行目以降で確認)。つまり本ventureには「LLM呼び出しを経ずに即時replyで
  終える軽量経路」がそもそも存在せず、`process_memo_event()`に到達する全てのtextメッセージ
  (画像単体送信等の対象外ケースを除く)が、何らかの形でLLM呼び出し→reply、という
  タイムアウト露出のある経路を通る。
- 4.の通常経路はさらに、`process_generation_request()`(usage_counter判定)→LLM呼び出し→
  検証→(5.トライアル終了通知・6.上限接近通知・7.quick_reply付記・9.初回生成案内)の後処理、
  という内部処理のステップ数自体もcourse-set-pashaより多い(course-set-pashaの「本題生成」
  経路は3点セット生成+簡易後処理のみ)。後処理自体はLLM呼び出しを伴わない軽量処理だが、
  LLM呼び出し自体の完了を待つ点は変わらない。

## 2. 費用対効果の検討

course-set-pashaの検討内容(line-reservation-ai/webhook-async-processing-design.mdが
採用した「Webhook即時ACK + Cloud Tasks非同期処理 + push API応答」方式の効果・コスト整理)
は、本ventureにもそのまま当てはまる。本ventureに固有の追加点は以下のとおり。

**効果(本venture固有)**: 上記1節の通り、本ventureは「LLM呼び出しなしの軽量経路」が
存在しないため、FAQ固定応答のような低レイテンシ経路とのハイブリッド化(course-set-pasha
3節で検討された、FAQ経路のみ同期replyに残す案)は本ventureには適用できない。したがって
根本対策を行う場合、**実質的に全ての文字メッセージ処理をCloud Tasksの非同期経路に回す**
設計になる見込みであり、course-set-pashaよりも構成が単純になる(分岐判断がA/Bの
いずれかで済み、「どの経路を同期に残すか」の追加判断が不要)という利点がある。

**コスト(本venture固有)**: 一方で、本venture特有の以下3点は、Function分割の設計時に
追加の検討が必要になる。
- `trial_end_notification_due`(5節)の付記判定・`workshop_store.set_first_generation_
  notice_sent()`(9節)等、`workshop_store`への書き込みを伴う後処理が複数存在する。これらは
  LLM呼び出し成否と独立した副作用(trial_generation_usedの確定等)を含むため、Function
  A(受信・idempotency・enqueue)とFunction B(LLM呼び出し・後処理・push)のどちらで
  実行するかを個別に切り分ける必要がある(現状はいずれも4.の`process_generation_request()`
  呼び出し時点=受信と同じ関数内で確定しており、A/B分割時に「enqueue前にまず
  process_generation_request()を呼ぶ(trial/usage判定を即時確定させる)」か「enqueue後の
  Function B側で呼ぶ」かで、二重課金・二重カウントのリスクプロファイルが変わる可能性がある)。
- 3つの「文脈注入」経路((a)(b)(c))もLLM呼び出しを伴うため、根本対策の対象に含める
  必要がある(course-set-pashaのFAQ経路のように対象外にできる経路が無い)。

## 3. 結論・推奨

本venture自身もcourse-set-pashaと同じ「reply失効によるオーナーへの生成結果未達」
リスクを抱えており、かつLLM呼び出しなしの軽量経路が存在しない分、全ての文字メッセージが
このリスクに露出している。したがって**根本対策(Cloud Tasks非同期処理+ push API応答への
移行)は本ventureでも実施すべきと判断する**。ただし実装・デプロイは実GCPプロジェクト作成
(オーナー承認待ち)後でなければ着手できないため、本フェーズでは費用対効果検討のみを
行い、実際の2関数構成への翻案設計ドキュメントの新規作成は次回候補として積み残す。

## 4. 残課題・次回候補

- 本ventureの`process_memo_event()`を、line-reservation-ai準拠の2関数構成(A: 署名検証・
  idempotency・enqueue・即時200、B: LLM呼び出し・後処理・push)に翻案する設計ドキュメントを
  新規作成する。1節で指摘した「軽量経路が存在しない」「`workshop_store`書き込みをA/Bどちらで
  行うか」の2点を主要な検討事項とする。
- 設計確定後、実コード(`prototype/`配下)への反映は、Cloud Tasks自体はスタブ
  (InMemoryキュー相当)で机上検証可能なため、実GCPプロジェクト作成の承認を待たずに
  着手できる見込み(line_webhook_event_id_store同様、Protocol越しの差し替え設計とすることで
  検証を先行させる)。
- aircon-pashaについても同種の経路構造確認(本フェーズと同じ個別確認)がまだ行われていない
  ため、aircon-pashaが次回選ばれた回での横展開候補として残る。

最終更新: 2026-11-10 19:00 UTC(新規作成。course-set-pashaフェーズ369の横展開前提
「各venture側の経路構造の個別確認」に対応し、本venture自身の費用対効果検討を実施。
本ventureにはLLM呼び出しなしの軽量経路が存在しないことを確認し、根本対策の実施自体は
推奨と結論。実装・デプロイはオーナー承認待ちのため、翻案設計ドキュメントの新規作成を
次回候補として積み残す)
