# 候補一覧の採番提示・顧客返信からのslot_key特定 設計

intent-to-flow-mapping.md の残課題1・2(`search_candidates_from_llm_output()`が返す候補一覧を
顧客へどう提示し、その返信からどうやって`select_slot()`に渡す`slot_key`を1件特定するか)を設計する。

## 1. 候補一覧の提示文言(残課題1)

tone-and-manner-guideline.md の「数字表記の統一」「1メッセージ1用件」に従い、番号付きリストで提示する。

```
ご希望に近い空き枠はこちらです。番号でお知らせください。

1. 8/9 14:00〜
2. 8/9 15:00〜
3. 8/10 10:00〜
```

- 番号は半角数字+ピリオド(`1.`)で統一。
- 件数は`AvailabilitySearcher.find_candidates()`の`max_candidates`(既定3件)に従う。
- **(解消済み 2026-08-24 09:00 UTC・フェーズ続き132)** 当初「`_Candidate.label`は現状
  `8/9 14:00〜`のように曜日を含まない」という残課題として記載していたが、
  `prototype/engine.py`の`AvailabilitySearcher.find_candidates()`を実際に実行して確認した
  ところ、`_WEEKDAY_JA[day.weekday()]`を用いて`8/9(土) 14:00〜`の形式(tone-and-manner-
  guideline.mdの表記例と一致)で既に生成されていることを確認した。この修正は本ドキュメント
  作成と同一コミット(74412df)内で既に実装済みだったが、本文の記載更新が漏れていたための
  見かけ上の残課題だったと判明した。5節の該当項目もあわせて解消済みに更新する。

## 2. 顧客の返信からslot_keyを特定する処理(残課題2)

自然文の柔軟な解釈を将来的にLLM(intent-to-flow-mappingの構造化出力拡張)に委ねる方針は変えないが、
まずはルールベースで解決できる範囲を実装し、特定できない場合は安全側(schema-validation-report.mdの
E8方針と同様、誤確定より聞き直しを優先)に倒して再確認文言を返す設計とする。

判定優先順位(`resolve_candidate_selection()`):

1. **漢数字**(一/二/三/四/五)が返信に含まれる → その番号として確定
2. **丸数字**(①②③④⑤)が返信に含まれる → その番号として確定
3. **「N番」「N番目」**の形式(全角/半角数字とも可、`unicodedata.normalize("NFKC", ...)`で正規化) →
   その番号として確定
4. **返信全体が数字のみ**(前後の空白・句読点を除き`"2"`や`"2."`など) → その番号として確定
5. 上記いずれにも該当しない場合、候補一覧の`label`(日付部分・時刻部分)がどちらも返信文に
   含まれる候補を探す。1件だけヒットすれば確定、0件または複数件ヒットなら特定不能。
6. **候補が1件のみ提示されている場合に限り**、「それで」「その時間で」「その日で」等の
   指示語のみの肯定的な返信(`_is_single_candidate_affirmation()`)であればその1件を確定する。
   「無理」「難しい」等の否定語を伴う場合は対象外とする(2026-08-23追記、フェーズ130)。
7. 特定不能 → `None`を返す。呼び出し側は`format_reconfirm_message()`で候補一覧を再掲し、
   番号での回答を促す。

**手順6を候補1件時のみに限定した理由**: 候補が複数ある状態で「それで」とだけ返された場合は
どの候補を指しているか一意に定まらず、誤った枠を確定するリスクがある。候補が1件のみなら
指すもの自体に曖昧さが無いため、指示語表現でも安全に確定できる
(multi-turn-scenario-harness-design.md「残る課題」参照)。

**優先順位4を「返信全体が数字のみ」に限定した理由**: `"8/9の方で"`のような返信は`"8"`という
数字を含むが、これは候補番号ではなく日付の一部である。単純な「最初に出てくる数字」抽出だと
誤って1番目の候補を確定してしまう(顧客の意図と異なる枠が仮押さえされる)重大な誤爆リスクがある。
そのため、番号指定であることが明確なパターン(漢数字・丸数字・「N番」表記・返信が数字のみ)に
限定し、それ以外は手順5の日付・時刻文字列の突き合わせに委ねる。

## 3. 再確認メッセージ(特定不能時)

```
申し訳ございません、番号でお知らせいただけますか?

1. 8/9 14:00〜
2. 8/9 15:00〜
3. 8/10 10:00〜
```

- tone-and-manner-guideline.mdの「お詫びと催促を同じメッセージで重ねない」方針に従い、
  お詫びは1回のみ・候補再掲は情報提供であって催促ではないため許容する。
- 再確認を送った後も特定できない状態が続く場合(顧客が何度も自由記述で返す等)の
  エスカレーション判断(オーナー通知に切り替えるタイミング)は6節で設計・実装済み
  (`RECONFIRM_MAX_ATTEMPTS = 2`、3回目の特定不能でオーナーへエスカレーション)。
  **(2026-08-30 23:00 UTC訂正: 本節が「未設計。次回以降の課題とする」のまま未更新で
  残っていた記載漏れを解消。6節の設計は既に完了しており、以後この項目を「未設計」として
  再掲しないこと)**

## 4. 実装

`prototype/engine.py`に以下を追加し、デモで動作確認済み:

- `format_candidates_message(candidates)`: 番号付き候補一覧の文言を生成
- `format_reconfirm_message(candidates)`: 特定不能時の再確認文言を生成
- `resolve_candidate_selection(reply_text, candidates)`: 上記優先順位で`slot_key`を特定、
  不能なら`None`

## 5. 今後の課題

- ~~ConversationFlowStateMachine.select_slot()との接続~~ → 対応済み。`present_candidates(user_id, candidates)`
  でcandidatesを状態に保持できるようにし、`select_slot_from_reply(user_id, reply_text, now)`を
  新規追加した。内部で`resolve_candidate_selection()`を呼び、特定できれば`select_slot()`
  (slot_label/alt_candidatesは選ばれた候補・残りの候補labelから自動生成)、特定できなければ
  `format_reconfirm_message()`をmessageに詰めた`SelectSlotResult(success=False, ...)`を返す
  (会話ステージは`candidates_presented`のまま据え置き)。`select_slot()`自体は`slot_key`を直接
  受け取る従来のシグネチャのまま残し、呼び出し側でslot_keyを既に特定できているケース向けに併存させる
  設計とした(prototype/engine.py、デモで鈴木さん(特定成功)・渡辺さん(特定不能→ステージ据え置き)を確認)。
- ~~`resolve_candidate_selection()`が`None`を返した場合の再確認ループの上限回数・
  エスカレーション切り替えタイミングの設計~~ → 対応済み(6節参照)。
- ~~`_Candidate.label`への曜日追加(上記1節の既知の残課題)~~ → (解消済み 2026-08-24 09:00 UTC)
  実装済みであることを確認済み。上記1節参照。
- booking_output.schema.jsonへの「候補選択」用フィールド追加要否の再検討
  (現状はLLM構造化出力を経由せず、顧客の生返信テキストを直接`resolve_candidate_selection()`に
  渡す設計としているため、スキーマ拡張は不要という結論を暫定的に採用しているが、
  LLM側で先に意図抽出させる設計に変える場合は再検討が必要)。

## 6. 再確認ループの上限・エスカレーション切り替え設計

5節で残っていた「特定不能が続いた場合の再確認ループの上限」を設計・実装した。

- `_ConversationState`に`reconfirm_count`(既定0)を追加し、`select_slot_from_reply()`で
  特定不能(`resolve_candidate_selection()`が`None`)のたびに加算する。
- 上限は`RECONFIRM_MAX_ATTEMPTS = 2`(再確認メッセージを最大2回まで送る)。3回目の特定不能で、
  同じ再確認文言を繰り返す代わりにオーナーへエスカレーションし、顧客には
  `ESCALATION_HANDOFF_MESSAGE`(「担当より改めてご連絡いたします」の定型文)を返す。
- エスカレーション通知は`EscalationConsolidator.on_event()`経由で送る(連続エスカレーション時の
  集約ロジックをそのまま流用できる)。`escalation_reason`は`'candidate_selection_unresolved'`と
  したが、`booking_conflict`(conversation-flow-state-machine-design.md参照)と同様、
  LLM構造化出力ではなくシステム内部で生成するイベントのため、booking_output.schema.jsonの
  enum(`consultation`/`unimplemented_feature`)への追加は行わない方針とした。通知ログ集計側の
  `NotificationLogAggregator`に`SYSTEM_ESCALATION_REASONS`区分を新設し、一般相談とは別枠の
  `system_event_counts`として集計する(2026-08-01決定・対応済み、notification-log-classification-labels.md
  「システム内部イベントの扱い」参照)。
- エスカレーション後は`reconfirm_count`を0にリセットする(会話ステージは`candidates_presented`の
  ままとし、同じ候補一覧に対して顧客が改めて明確な返信をすれば特定を継続できるようにした。
  次に特定不能が続いた場合は再度2回の再確認を経てからエスカレーションする)。
- 番号選択に成功した場合も`reconfirm_count`を0にリセットする。

**今後の課題**: `RECONFIRM_MAX_ATTEMPTS = 2`は他のエスカレーション系設計(escalation-consolidation-logic.mdの
再発火上限等)と同様、仮の目安であり実測データが取れた際に見直す。

**(解消済み 2026-08-24 04:00 UTC)** エスカレーション後に顧客が無反応のまま会話が終了した場合の
会話状態クリーンアップについて、専用ロジックが必要かを検証した。`select_slot_from_reply()`は
エスカレーション分岐に入る場合も含め毎回`state.last_activity_at = now`を更新しており
(prototype/engine.py)、エスカレーション後も`stage`は`candidates_presented`のまま
`_states`に残り続けるため、idle-conversation-trigger-design.mdで既に実装済みの汎用idle cleanup
(`release_idle_conversations()`、`CONVERSATION_IDLE_TIMEOUT`=30分経過で失効)がそのまま
この状態も回収することを確認した。専用の実装は不要と結論づけ、回帰防止テスト
`test_release_idle_conversations_frees_state_stuck_after_escalation`を
`prototype/test_engine.py`に追加した(29分後は未失効、31分後に失効することを確認、
プロトタイプ全体313件パス)。これにより本ステップの「今後の課題」はRECONFIRM_MAX_ATTEMPTSの
実測見直しのみとなった。
