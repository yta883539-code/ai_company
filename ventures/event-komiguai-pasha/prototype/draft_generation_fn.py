#!/usr/bin/env python3
"""
README.mdフェーズ101の次回候補(2)で発見したギャップ(実際のCloud Functionエントリ
ポイント実装時にgenerate_fnをどう構成するか: mock_llm_client.run_form_submission_pipeline()
相当を呼ぶには元のフォーム入力〈capacity・entry_exit_points等〉がdraft_id単位で必要だが、
現状のOneTimeDraft/OneTimeDraftStoreProtocolは決済確認後に必要な情報〈checkout_session_id・
customer_email・payment_intent_id〉しか保持しておらず、元のフォーム入力をdraft作成時に
どこへ・どう保存し生成時に取り出すかが未設計のまま残っていた)を埋めるモジュール。

draft-creation-and-event-memo-storage-design.md(フェーズ102)の設計を実コード化する。

位置づけ:
- Webフォーム送信時(厳守事項8の必須項目充足を確認しCheckout Sessionを作成する直前、
  form_submission_intake.handle_form_submission()がLLMリクエストペイロードを返す経路)に、
  `OneTimeDraftStoreProtocol.create_draft()`でevent_memo(5入力要素の生dict)を
  `one_time_draft/{draft_id}`へ保存する(stripe_webhook.pyフェーズ102で追加)。
- generation_retry_and_refund.GenerationFnが要求する「draft_idのみを受け取り構造化出力
  dictを返す」契約を満たすため、本モジュールのbuild_generation_fn()はdraft_storeから
  event_memoを取り出し、mock_llm_client.validate_llm_output()相当の検証まで通した上で
  出力を返すクロージャを組み立てる。
- 実LLM呼び出し自体はllm_client引数(mock_llm_client.LlmCallClient Protocol)に委ね、
  本モジュールはevent_memoの取り出し・LLM呼び出し・検証エラー時のGenerationError変換
  までの配線のみを担う。
"""

from __future__ import annotations

from typing import Callable

from form_submission_intake import handle_form_submission
from generation_retry_and_refund import GenerationError
from mock_llm_client import LlmCallClient, validate_llm_output


class DraftEventMemoMissingError(GenerationError):
    """draft_idに対応するevent_memoがone_time_draftドキュメントに保存されていない場合に
    送出する(design上は発生しない想定。draft作成時に必ずevent_memoを保存する契約のため、
    発生した場合はcreate_draft()を経由していない想定外の呼び出し経路を示す)。"""


def build_generation_fn(
    draft_store,
    llm_client: LlmCallClient,
    scenario_for_draft: Callable[[str], str],
):
    """generation_retry_and_refund.GenerationFnを満たす呼び出し可能オブジェクトを組み立てる。

    - `scenario_for_draft`は本モック環境固有の引数で、draft_idからLLMモックのシナリオ名
      (mock_llm_client.MOCK_LLM_SCENARIOSのキー)を解決する(実LLM接続後は不要になる、
      design「残課題」参照。実クライアントはscenario引数を持たず入力のみから生成する)。
    - event_memoがinsufficient_input相当(必須項目欠落)を返した場合は、本来Checkout
      Session自体が作成されない設計(create_draft()はhandle_form_submission()がLLM
      リクエストペイロードを返せる=必須項目充足している場合のみ呼ばれる想定、design
      2節)だが、防御的にinsufficient_input応答が返った場合もそのまま出力として返す
      (GenerationErrorにはしない。主催者の入力不備であり、リトライ・返金の対象には
      しない方針)。
    - 検証エラー(validate_llm_output()が空でないリストを返す場合)はGenerationErrorを
      送出し、呼び出し側(process_generation_after_payment())のリトライ・返金フローに
      委ねる(generation_retry_and_refund.py冒頭docstringの既存方針どおり、検証エラーも
      生成失敗として同列に扱う)。
    """

    def generate(draft_id: str) -> dict:
        draft = draft_store.get(draft_id)
        if draft is None or draft.event_memo is None:
            raise DraftEventMemoMissingError(
                f"draft_id={draft_id!r}に対応するevent_memoが見つかりません"
                "(create_draft()経由で保存されているはずの入力が欠落しています)"
            )

        intake_result = handle_form_submission(draft.event_memo)
        if "status" in intake_result:
            # insufficient_input相当: design上はCheckout Session作成前のintake層で
            # 弾かれているはずだが、防御的にそのまま返す(リトライ・返金対象にはしない)。
            return intake_result

        scenario = scenario_for_draft(draft_id)
        output = llm_client.generate(intake_result, scenario=scenario)
        errors = validate_llm_output(output)
        if errors:
            raise GenerationError(
                f"draft_id={draft_id!r}の生成結果が検証エラー: {errors}"
            )
        return output

    return generate
