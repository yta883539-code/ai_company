#!/usr/bin/env python3
"""
schema/output.schema.json(2026-09-06 05:00 UTC作成)に対する期待JSON出力サンプルを
机上検証するスクリプト。course-set-pasha/line-reservation-aiのschema/validate_test_cases.pyと
同じ位置づけ・同じ簡易バリデータ方式(draft-07のサブセットのみ解釈)を踏襲した。

位置づけ:
- 実LLM呼び出しは行わない(APIキー・課金が必要なため、実行にはオーナー承認が必要な範囲)。
- llm-system-prompt-draft.md「次の課題」3点目(status分岐(generated/out_of_scope/
  insufficient_input)とcategory(new/repair)整合性検証用テストケース作成)に対応したもの。
- order_summary.categoryとdelivery_notice.categoryが一致することの検証(厳守事項4)、
  categoryがnew/repairの場合それぞれでdelivery_notice.bodyの分岐内容が反映されているかの
  机上確認を主眼とする。
- 外部ライブラリ(jsonschema等)には依存しない(pure stdlibのみ)。

実行方法: python3 validate_test_cases.py
"""

import json
import sys
from pathlib import Path

SCHEMA_PATH = Path(__file__).parent / "output.schema.json"

with open(SCHEMA_PATH, encoding="utf-8") as f:
    SCHEMA = json.load(f)


def validate_against_schema(instance, schema, path="$"):
    """output.schema.json のサブセット(type/enum/required/additionalProperties)
    のみを解釈する簡易バリデータ。draft-07全体には対応しない。"""
    errors = []

    def type_ok(value, type_spec):
        types = type_spec if isinstance(type_spec, list) else [type_spec]
        for t in types:
            if t == "null" and value is None:
                return True
            if t == "string" and isinstance(value, str):
                return True
            if t == "boolean" and isinstance(value, bool):
                return True
            if t == "integer" and isinstance(value, int) and not isinstance(value, bool):
                return True
            if t == "array" and isinstance(value, list):
                return True
            if t == "object" and isinstance(value, dict):
                return True
        return False

    if "type" in schema and not type_ok(instance, schema["type"]):
        errors.append(f"{path}: 型不一致 (期待={schema['type']}, 実際={type(instance).__name__}: {instance!r})")
        return errors  # 型が違えば以降のチェックは無意味

    if isinstance(schema.get("type"), (str, list)) and "object" in (
        schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
    ) and isinstance(instance, dict):
        required = schema.get("required", [])
        for key in required:
            if key not in instance:
                errors.append(f"{path}: 必須フィールド '{key}' が欠けています")
        if schema.get("additionalProperties") is False:
            allowed = set(schema.get("properties", {}).keys())
            for key in instance:
                if key not in allowed:
                    errors.append(f"{path}: 未定義フィールド '{key}' が含まれています")
        props = schema.get("properties", {})
        for key, value in instance.items():
            if key in props:
                errors.extend(validate_against_schema(value, props[key], path=f"{path}.{key}"))

    if "enum" in schema and instance is not None and instance not in schema["enum"]:
        errors.append(f"{path}: enum不一致 (期待={schema['enum']}, 実際={instance!r})")

    return errors


def validate_cross_field_rules(instance, path="$"):
    """JSON Schema単体では表現しきれない、status値・category値に応じたnull/非nullの
    依存関係ルールをチェックする(llm-system-prompt-draft.md「構造化出力の方針」参照)。"""
    errors = []
    status = instance.get("status")

    generated_fields = ["order_summary", "delivery_notice", "care_notice"]

    if status == "generated":
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=generatedのときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=generatedのときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is None:
                errors.append(f"{path}: status=generatedのとき{f}は非nullである必要があります")

        order_summary = instance.get("order_summary") or {}
        delivery_notice = instance.get("delivery_notice") or {}
        os_category = order_summary.get("category")
        dn_category = delivery_notice.get("category")
        if os_category is None:
            errors.append(f"{path}.order_summary.category: status=generatedのとき非nullである必要があります(厳守事項3)")
        if os_category != dn_category:
            errors.append(
                f"{path}: order_summary.category({os_category!r})とdelivery_notice.category"
                f"({dn_category!r})が一致していません(厳守事項4)"
            )
    elif status == "out_of_scope":
        if instance.get("out_of_scope_message") is None:
            errors.append(f"{path}: status=out_of_scopeのときout_of_scope_messageは非nullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status=out_of_scopeのときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status=out_of_scopeのとき{f}はnullである必要があります")
    elif status == "insufficient_input":
        if instance.get("missing_fields_request") is None:
            errors.append(f"{path}: status=insufficient_inputのときmissing_fields_requestは非nullである必要があります")
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status=insufficient_inputのときout_of_scope_messageはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status=insufficient_inputのとき{f}はnullである必要があります")

    # 2026-09-07 07:00 UTC追加(フェーズ24): subscription-cancellation-flow-design.md
    # 対応のstatus3値(cancellation_intent/downgrade_intent/cancellation_unclear)の
    # 非null制約チェック。course-set-pasha/schema/validate_test_cases.pyの同種ロジックを踏襲。
    notice_statuses = {"cancellation_intent", "downgrade_intent", "cancellation_unclear"}
    notice = instance.get("subscription_procedure_notice")
    if status in notice_statuses:
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status={status}のときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status={status}のときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status={status}のとき{f}はnullである必要があります")
        if notice is None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeは非nullである必要があります")
        else:
            if notice.get("kind") != status:
                errors.append(
                    f"{path}.subscription_procedure_notice.kind: status({status!r})と"
                    f"一致していません(実際={notice.get('kind')!r})"
                )
            expected_portal_link = status in {"cancellation_intent", "downgrade_intent"}
            if notice.get("includes_portal_link") != expected_portal_link:
                errors.append(
                    f"{path}.subscription_procedure_notice.includes_portal_link: "
                    f"kind={status!r}のとき{expected_portal_link}である必要があります"
                    f"(厳守事項7a(iv)相当、実際={notice.get('includes_portal_link')!r})"
                )
    else:
        if notice is not None:
            errors.append(f"{path}: status={status!r}のときsubscription_procedure_noticeはnullである必要があります")

    # 2026-09-07 13:02 UTC追加: member-retention-notice-design.md対応のstatus2値
    # (member_retention_selection/member_retention_unclear)の非null制約チェック。
    retention_statuses = {"member_retention_selection", "member_retention_unclear"}
    retention_notice = instance.get("member_retention_notice")
    if status in retention_statuses:
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status={status}のときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status={status}のときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status={status}のとき{f}はnullである必要があります")
        if instance.get("subscription_procedure_notice") is not None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeはnullである必要があります")
        if retention_notice is None:
            errors.append(f"{path}: status={status}のときmember_retention_noticeは非nullである必要があります")
        else:
            if retention_notice.get("kind") != status:
                errors.append(
                    f"{path}.member_retention_notice.kind: status({status!r})と"
                    f"一致していません(実際={retention_notice.get('kind')!r})"
                )
            expected_has_name = status == "member_retention_selection"
            has_name = retention_notice.get("specified_member_name") is not None
            if has_name != expected_has_name:
                errors.append(
                    f"{path}.member_retention_notice.specified_member_name: "
                    f"status={status!r}のとき非null={expected_has_name}である必要があります"
                    f"(実際のspecified_member_name={retention_notice.get('specified_member_name')!r})"
                )
    else:
        if retention_notice is not None:
            errors.append(f"{path}: status={status!r}のときmember_retention_noticeはnullである必要があります")

    # 2026-09-07 17:58 UTC追加(フェーズ34): contractor-transfer-design.md対応のstatus2値
    # (contractor_transfer_selection/contractor_transfer_unclear)の非null制約チェック。
    # member_retention_notice用のロジックと同じ設計思想を踏襲。
    transfer_statuses = {"contractor_transfer_selection", "contractor_transfer_unclear"}
    transfer_notice = instance.get("contractor_transfer_notice")
    if status in transfer_statuses:
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status={status}のときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status={status}のときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status={status}のとき{f}はnullである必要があります")
        if instance.get("subscription_procedure_notice") is not None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeはnullである必要があります")
        if instance.get("member_retention_notice") is not None:
            errors.append(f"{path}: status={status}のときmember_retention_noticeはnullである必要があります")
        if transfer_notice is None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_noticeは非nullである必要があります")
        else:
            if transfer_notice.get("kind") != status:
                errors.append(
                    f"{path}.contractor_transfer_notice.kind: status({status!r})と"
                    f"一致していません(実際={transfer_notice.get('kind')!r})"
                )
            expected_has_name = status == "contractor_transfer_selection"
            has_name = transfer_notice.get("specified_member_name") is not None
            if has_name != expected_has_name:
                errors.append(
                    f"{path}.contractor_transfer_notice.specified_member_name: "
                    f"status={status!r}のとき非null={expected_has_name}である必要があります"
                    f"(実際のspecified_member_name={transfer_notice.get('specified_member_name')!r})"
                )
    else:
        if transfer_notice is not None:
            errors.append(f"{path}: status={status!r}のときcontractor_transfer_noticeはnullである必要があります")

    # 2026-09-08 02:00 UTC追加(フェーズ37): contractor-transfer-confirmation-detection-design.md
    # 対応のstatus3値(contractor_transfer_confirmed/contractor_transfer_cancelled/
    # contractor_transfer_reconfirm_unclear)の非null制約チェック。transfer_notice用の
    # ロジックと同じ設計思想を踏襲。
    confirmation_statuses = {
        "contractor_transfer_confirmed",
        "contractor_transfer_cancelled",
        "contractor_transfer_reconfirm_unclear",
    }
    confirmation = instance.get("contractor_transfer_confirmation")
    if status in confirmation_statuses:
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status={status}のときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status={status}のときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status={status}のとき{f}はnullである必要があります")
        if instance.get("subscription_procedure_notice") is not None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeはnullである必要があります")
        if instance.get("member_retention_notice") is not None:
            errors.append(f"{path}: status={status}のときmember_retention_noticeはnullである必要があります")
        if transfer_notice is not None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_noticeはnullである必要があります")
        if confirmation is None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_confirmationは非nullである必要があります")
        else:
            if confirmation.get("kind") != status:
                errors.append(
                    f"{path}.contractor_transfer_confirmation.kind: status({status!r})と"
                    f"一致していません(実際={confirmation.get('kind')!r})"
                )
    else:
        if confirmation is not None:
            errors.append(f"{path}: status={status!r}のときcontractor_transfer_confirmationはnullである必要があります")

    # 2026-09-08 06:00 UTC追加(フェーズ40): contractor-transfer-expired-notice-design.md
    # 対応のstatus1値(contractor_transfer_expired_notice)の非null制約チェック。
    # confirmation用のロジックと同じ設計思想を踏襲。candidate_member_nameは常に非null
    # (design.md3節、この文脈が注入される時点で必ず候補者名が存在するため)。
    expired_notice = instance.get("contractor_transfer_expired_notice")
    if status == "contractor_transfer_expired_notice":
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status={status}のときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status={status}のときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status={status}のとき{f}はnullである必要があります")
        if instance.get("subscription_procedure_notice") is not None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeはnullである必要があります")
        if instance.get("member_retention_notice") is not None:
            errors.append(f"{path}: status={status}のときmember_retention_noticeはnullである必要があります")
        if transfer_notice is not None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_noticeはnullである必要があります")
        if confirmation is not None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_confirmationはnullである必要があります")
        if expired_notice is None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_expired_noticeは非nullである必要があります")
        else:
            if expired_notice.get("kind") != status:
                errors.append(
                    f"{path}.contractor_transfer_expired_notice.kind: status({status!r})と"
                    f"一致していません(実際={expired_notice.get('kind')!r})"
                )
            if expired_notice.get("candidate_member_name") is None:
                errors.append(
                    f"{path}.contractor_transfer_expired_notice.candidate_member_name: "
                    "常に非nullである必要があります(design.md3節)"
                )
    else:
        if expired_notice is not None:
            errors.append(f"{path}: status={status!r}のときcontractor_transfer_expired_noticeはnullである必要があります")

    # 2026-09-09 07:00 UTC追加(フェーズ58): llm-system-prompt-draft.md厳守事項7b・
    # checkout-initiation-flow-design.md対応のstatus3値(checkout_intent/pricing_inquiry/
    # checkout_intent_unclear)の非null制約チェック。subscription_procedure_notice用の
    # ロジックと同じ設計思想を踏襲するが、includes_checkout_urlはkindによらず常にfalseで
    # ある点が厳守事項7bの設計(実際のCheckout Session URL発行は自己判断で行わない)を反映している。
    checkout_statuses = {"checkout_intent", "pricing_inquiry", "checkout_intent_unclear"}
    checkout_notice = instance.get("checkout_notice")
    if status in checkout_statuses:
        if instance.get("out_of_scope_message") is not None:
            errors.append(f"{path}: status={status}のときout_of_scope_messageはnullである必要があります")
        if instance.get("missing_fields_request") is not None:
            errors.append(f"{path}: status={status}のときmissing_fields_requestはnullである必要があります")
        for f in generated_fields:
            if instance.get(f) is not None:
                errors.append(f"{path}: status={status}のとき{f}はnullである必要があります")
        if instance.get("subscription_procedure_notice") is not None:
            errors.append(f"{path}: status={status}のときsubscription_procedure_noticeはnullである必要があります")
        if instance.get("member_retention_notice") is not None:
            errors.append(f"{path}: status={status}のときmember_retention_noticeはnullである必要があります")
        if transfer_notice is not None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_noticeはnullである必要があります")
        if confirmation is not None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_confirmationはnullである必要があります")
        if expired_notice is not None:
            errors.append(f"{path}: status={status}のときcontractor_transfer_expired_noticeはnullである必要があります")
        if checkout_notice is None:
            errors.append(f"{path}: status={status}のときcheckout_noticeは非nullである必要があります")
        else:
            if checkout_notice.get("kind") != status:
                errors.append(
                    f"{path}.checkout_notice.kind: status({status!r})と"
                    f"一致していません(実際={checkout_notice.get('kind')!r})"
                )
            if checkout_notice.get("includes_checkout_url") is not False:
                errors.append(
                    f"{path}.checkout_notice.includes_checkout_url: "
                    f"kindによらず常にfalseである必要があります(厳守事項7b、実際="
                    f"{checkout_notice.get('includes_checkout_url')!r})"
                )
    else:
        if checkout_notice is not None:
            errors.append(f"{path}: status={status!r}のときcheckout_noticeはnullである必要があります")

    return errors


# mvp-flow-draft.md・llm-system-prompt-draft.mdで検討してきた入力パターンを踏まえ、
# 期待される構造化出力を机上で書き起こしたフィクスチャ。
TEST_CASES = {
    "G1_new_basic": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": {
            "category": "new",
            "saddle_type": "ブリティッシュ",
            "leather_type": "牛革",
            "hardware_spec": None,
            "usage": "競技用",
            "due_date": "3ヶ月",
            "remarks": None,
            "body": "区分:新規制作/鞍の型:ブリティッシュ/革の種類:牛革/用途:競技用/納期:3ヶ月",
        },
        "delivery_notice": {
            "category": "new",
            "body": (
                "新しい鞍をお届けします。装着直後は革が体に馴染むまで時間がかかりますので、"
                "最初は短時間の騎乗から始め、徐々に締め具合を調整してください。雨天時は"
                "使用後に乾いた布で水分を拭き取ってください。"
            ),
        },
        "care_notice": (
            "定期的にオイル・クリームで革に保湿を与えてください。高温多湿・直射日光を避けた"
            "場所で保管し、カビ・ひび割れを防いでください。金具部分は使用後に乾拭きしさびを防いでください。"
        ),
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    "G2_repair_with_remarks": {
        "status": "generated",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": {
            "category": "repair",
            "saddle_type": "ウエスタン",
            "leather_type": "馬革",
            "hardware_spec": "ステンレス金具",
            "usage": "日常騎乗用",
            "due_date": "2週間",
            "remarks": "鐙革の縫い目がほつれている、金具のさびが目立つ",
            "body": (
                "区分:修理/鞍の型:ウエスタン/革の種類:馬革/金具仕様:ステンレス金具/"
                "用途:日常騎乗用/納期:2週間/症状:鐙革の縫い目がほつれている、金具のさびが目立つ"
            ),
        },
        "delivery_notice": {
            "category": "repair",
            "body": (
                "修理箇所(鐙革の縫い目、金具のさび)の補修が完了しました。修理直後は新規制作時ほど"
                "長期の慣らしは不要ですが、初回騎乗時は締め具合に違和感が無いかご確認ください。"
            ),
        },
        "care_notice": (
            "定期的にオイル・クリームで革に保湿を与えてください。高温多湿・直射日光を避けた"
            "場所で保管し、カビ・ひび割れを防いでください。金具部分は使用後に乾拭きしさびを防いでください。"
        ),
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    "OOS1_membership_question": {
        "status": "out_of_scope",
        "out_of_scope_message": "本サービスは受注整理・納品案内・お手入れ案内の下書き作成支援のみを行っております。",
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    "II1_no_category": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "区分(新規制作/修理)が不明なため下書きを作成できません。区分を教えてください。",
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    "II2_no_saddle_type": {
        "status": "insufficient_input",
        "out_of_scope_message": None,
        "missing_fields_request": "鞍の型が不明なため下書きを作成できません。鞍の型(ブリティッシュ/ウエスタン等)を教えてください。",
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # 2026-09-07 07:00 UTC追加(フェーズ24): subscription-cancellation-flow-design.md
    # 「1. 解約意図検知時の案内メッセージ」相当の期待出力。
    "C1_cancellation_intent": {
        "status": "cancellation_intent",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": {
            "kind": "cancellation_intent",
            "body": (
                "解約をご希望とのことで承知しました。現在のご契約内容をご確認のうえ、"
                "下記リンクから解約手続きをお願いいたします。手続き完了後も今回のご請求"
                "サイクルの終了日まではサービスをご利用いただけます。"
            ),
            "includes_portal_link": True,
        },
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # subscription-cancellation-flow-design.md「ダウングレード(プラン変更)フロー」相当。
    "C2_downgrade_intent": {
        "status": "downgrade_intent",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": {
            "kind": "downgrade_intent",
            "body": (
                "プラン変更をご希望とのことで承知しました。下記リンクからご希望のプランへの"
                "変更手続きをお願いいたします。日割り差額は変更申込み時点で精算されます。"
            ),
            "includes_portal_link": True,
        },
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # 厳守事項7a(iv)相当: 解約意図か雑談か判別しづらい入力に対する意思確認一言のみの出力。
    "C3_cancellation_unclear": {
        "status": "cancellation_unclear",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": {
            "kind": "cancellation_unclear",
            "body": "解約をご希望でしょうか?よろしければ「解約したい」とお送りください。",
            "includes_portal_link": False,
        },
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # 2026-09-07 13:02 UTC追加: member-retention-notice-design.md「2. 検知パターンの整理」1
    # (明確な指定)相当の期待出力。
    "M1_member_retention_selection": {
        "status": "member_retention_selection",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": {
            "kind": "member_retention_selection",
            "specified_member_name": "田中",
            "body": "田中様を継続利用メンバーとして承りました。切り替え日に反映いたします。",
        },
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # member-retention-notice-design.md「2. 検知パターンの整理」2(不明確)相当の期待出力。
    "M2_member_retention_unclear": {
        "status": "member_retention_unclear",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": {
            "kind": "member_retention_unclear",
            "specified_member_name": None,
            "body": "どなたを継続利用としてご希望か、お名前をお知らせください。",
        },
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # 2026-09-07 17:58 UTC追加(フェーズ34): contractor-transfer-design.md「3. 確定する設計」
    # (名指しされた相手がmember_user_idsに含まれる場合)相当の期待出力。
    "CT1_contractor_transfer_selection": {
        "status": "contractor_transfer_selection",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": {
            "kind": "contractor_transfer_selection",
            "specified_member_name": "山田",
            "body": "山田様を新しい契約者として設定します。よろしいですか?",
        },
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # contractor-transfer-design.md「3. 確定する設計」(名指しされた相手がmember_user_idsに
    # 含まれない場合、まだworkshopに参加していない第三者を指定した場合を含む)相当の期待出力。
    "CT2_contractor_transfer_unclear": {
        "status": "contractor_transfer_unclear",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": {
            "kind": "contractor_transfer_unclear",
            "specified_member_name": None,
            "body": "先に招待コードでworkshopへ加わっていただいてから、改めて契約者交代のご連絡をください。",
        },
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # 2026-09-08 02:00 UTC追加(フェーズ37): contractor-transfer-confirmation-detection-design.md
    # 「3. 検知パターン・schema拡張」1(肯定)相当の期待出力。
    "CTC1_contractor_transfer_confirmed": {
        "status": "contractor_transfer_confirmed",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": {
            "kind": "contractor_transfer_confirmed",
            "body": "契約者を山田様に変更いたしました。",
        },
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # contractor-transfer-confirmation-detection-design.md「3. 検知パターン・schema拡張」2
    # (否定)相当の期待出力。
    "CTC2_contractor_transfer_cancelled": {
        "status": "contractor_transfer_cancelled",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": {
            "kind": "contractor_transfer_cancelled",
            "body": "契約者交代の手続きを取り消しました。現在の契約者のまま変更ございません。",
        },
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # contractor-transfer-confirmation-detection-design.md「3. 検知パターン・schema拡張」3
    # (不明瞭)相当の期待出力。
    "CTC3_contractor_transfer_reconfirm_unclear": {
        "status": "contractor_transfer_reconfirm_unclear",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": {
            "kind": "contractor_transfer_reconfirm_unclear",
            "body": "契約者交代についてのご返信でよろしいでしょうか?「はい」か「いいえ」でお知らせください。",
        },
        "contractor_transfer_expired_notice": None,
        "checkout_notice": None,
    },
    # 2026-09-08 06:00 UTC追加(フェーズ40): contractor-transfer-expired-notice-design.md
    # 「3. status・schema拡張」相当の期待出力。
    "CTE1_contractor_transfer_expired_notice": {
        "status": "contractor_transfer_expired_notice",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": {
            "kind": "contractor_transfer_expired_notice",
            "candidate_member_name": "山田",
            "body": (
                "契約者交代(山田様への変更)の確認期限が過ぎたため、手続きを一旦"
                "取り消しました。交代をご希望の場合は、お手数ですが改めてご連絡ください。"
            ),
        },
        "checkout_notice": None,
    },
    # 2026-09-09 07:00 UTC追加(フェーズ58): checkout-initiation-flow-design.md・厳守事項7b(i)
    # 相当の期待出力。実際のCheckout Session URLはhandle_checkout_intent(Python側)に委ね、
    # LLM側は一次応答文言のみを返す(includes_checkout_urlは常にfalse)。
    "CO1_checkout_intent": {
        "status": "checkout_intent",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": {
            "kind": "checkout_intent",
            "body": "お申し込みのご案内をお送りしますね。",
            "includes_checkout_url": False,
        },
    },
    # 厳守事項7b(ii)相当: 料金・プラン内容についての問い合わせ。pricing-plan.mdの内容を
    # もとにした案内を返す(3出力の生成対象からは除外する)。
    "CO2_pricing_inquiry": {
        "status": "pricing_inquiry",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": {
            "kind": "pricing_inquiry",
            "body": (
                "料金プランは、ライト980円/月・スタンダード1,980円/月・複数職人3,980円/月の"
                "3種類(いずれも月間生成回数の上限+従量課金)がございます。"
            ),
            "includes_checkout_url": False,
        },
    },
    # 厳守事項7b(iv)相当: 開始意図か問い合わせか判断できない場合の意思確認一言のみの出力。
    "CO3_checkout_intent_unclear": {
        "status": "checkout_intent_unclear",
        "out_of_scope_message": None,
        "missing_fields_request": None,
        "order_summary": None,
        "delivery_notice": None,
        "care_notice": None,
        "subscription_procedure_notice": None,
        "member_retention_notice": None,
        "contractor_transfer_notice": None,
        "contractor_transfer_confirmation": None,
        "contractor_transfer_expired_notice": None,
        "checkout_notice": {
            "kind": "checkout_intent_unclear",
            "body": "有料プランのお申し込みをご希望でしょうか?よろしければ「有料プランを始めたい」とお送りください。",
            "includes_checkout_url": False,
        },
    },
}

# 厳守事項4違反(categoryの不一致)を意図的に仕込んだ不正フィクスチャ。
# validate_cross_field_rulesが実際にこの不整合を検出できることを確認するための
# ネガティブテストであり、TEST_CASESには含めずmain()内で単体に検証する。
NEGATIVE_CASE_CATEGORY_MISMATCH = {
    "status": "generated",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": {
        "category": "new",
        "saddle_type": "ブリティッシュ",
        "leather_type": "牛革",
        "hardware_spec": None,
        "usage": "競技用",
        "due_date": "3ヶ月",
        "remarks": None,
        "body": "区分:新規制作/...",
    },
    "delivery_notice": {
        "category": "repair",
        "body": "修理箇所の説明...",
    },
    "care_notice": "定期的な保湿・保管環境・さび防止手入れ...",
    "subscription_procedure_notice": None,
    "member_retention_notice": None,
    "contractor_transfer_notice": None,
    "contractor_transfer_confirmation": None,
    "contractor_transfer_expired_notice": None,
    "checkout_notice": None,
}

# 厳守事項7a(iv)相当違反(includes_portal_link不一致)を意図的に仕込んだ不正フィクスチャ。
# cancellation_unclearなのにポータルリンクへの言及ありとして出力してしまうケースを想定。
NEGATIVE_CASE_PORTAL_LINK_MISMATCH = {
    "status": "cancellation_unclear",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": None,
    "delivery_notice": None,
    "care_notice": None,
    "subscription_procedure_notice": {
        "kind": "cancellation_unclear",
        "body": "解約をご希望でしょうか?",
        "includes_portal_link": True,
    },
    "member_retention_notice": None,
    "contractor_transfer_notice": None,
    "contractor_transfer_confirmation": None,
    "contractor_transfer_expired_notice": None,
    "checkout_notice": None,
}

# 2026-09-07 13:02 UTC追加。member_retention_notice.kindがstatusと不一致な不正フィクスチャ
# (member_retention_unclearなのにkind=member_retention_selectionのまま出力してしまう
# ケースを想定)。validate_cross_field_rulesが検出できることを確認するためのネガティブテスト。
NEGATIVE_CASE_MEMBER_RETENTION_KIND_MISMATCH = {
    "status": "member_retention_unclear",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": None,
    "delivery_notice": None,
    "care_notice": None,
    "subscription_procedure_notice": None,
    "member_retention_notice": {
        "kind": "member_retention_selection",
        "specified_member_name": None,
        "body": "どなたを継続利用としてご希望か、お名前をお知らせください。",
    },
    "contractor_transfer_notice": None,
    "contractor_transfer_confirmation": None,
    "contractor_transfer_expired_notice": None,
    "checkout_notice": None,
}

# 2026-09-07 17:58 UTC追加(フェーズ34)。contractor_transfer_notice.kindがstatusと
# 不一致な不正フィクスチャ(contractor_transfer_unclearなのにkind=contractor_transfer_selection
# のまま出力してしまうケースを想定)。validate_cross_field_rulesが検出できることを
# 確認するためのネガティブテスト。
NEGATIVE_CASE_CONTRACTOR_TRANSFER_KIND_MISMATCH = {
    "status": "contractor_transfer_unclear",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": None,
    "delivery_notice": None,
    "care_notice": None,
    "subscription_procedure_notice": None,
    "member_retention_notice": None,
    "contractor_transfer_notice": {
        "kind": "contractor_transfer_selection",
        "specified_member_name": None,
        "body": "先に招待コードでworkshopへ加わっていただいてから、改めて契約者交代のご連絡をください。",
    },
    "contractor_transfer_confirmation": None,
    "contractor_transfer_expired_notice": None,
    "checkout_notice": None,
}

# 2026-09-08 02:00 UTC追加(フェーズ37)。contractor_transfer_confirmation.kindがstatusと
# 不一致な不正フィクスチャ(contractor_transfer_cancelledなのにkind=contractor_transfer_confirmed
# のまま出力してしまうケースを想定)。validate_cross_field_rulesが検出できることを
# 確認するためのネガティブテスト。
NEGATIVE_CASE_CONTRACTOR_TRANSFER_CONFIRMATION_KIND_MISMATCH = {
    "status": "contractor_transfer_cancelled",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": None,
    "delivery_notice": None,
    "care_notice": None,
    "subscription_procedure_notice": None,
    "member_retention_notice": None,
    "contractor_transfer_notice": None,
    "contractor_transfer_confirmation": {
        "kind": "contractor_transfer_confirmed",
        "body": "契約者交代の手続きを取り消しました。現在の契約者のまま変更ございません。",
    },
    "contractor_transfer_expired_notice": None,
    "checkout_notice": None,
}

# 2026-09-08 06:00 UTC追加(フェーズ40)。contractor_transfer_expired_notice.kindは固定
# enum値1つしか取り得ないため他フィールドのような値違いのkind不一致は起こり得ないが、
# 代わりに「statusが別値なのにcontractor_transfer_expired_noticeが非nullのまま残って
# しまう」誤り(排他性違反)を仕込んだ不正フィクスチャ。validate_cross_field_rulesが
# 検出できることを確認するためのネガティブテスト。
NEGATIVE_CASE_CONTRACTOR_TRANSFER_EXPIRED_NOTICE_PRESENT_WHEN_STATUS_MISMATCH = {
    "status": "contractor_transfer_cancelled",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": None,
    "delivery_notice": None,
    "care_notice": None,
    "subscription_procedure_notice": None,
    "member_retention_notice": None,
    "contractor_transfer_notice": None,
    "contractor_transfer_confirmation": {
        "kind": "contractor_transfer_cancelled",
        "body": "契約者交代の手続きを取り消しました。現在の契約者のまま変更ございません。",
    },
    "contractor_transfer_expired_notice": {
        "kind": "contractor_transfer_expired_notice",
        "candidate_member_name": "山田",
        "body": "契約者交代(山田様への変更)の確認期限が過ぎたため、手続きを一旦取り消しました。",
    },
    "checkout_notice": None,
}

# 2026-09-08 06:00 UTC追加(フェーズ40)。contractor-transfer-expired-notice-design.md3節
# 「常に非null(この文脈が注入される時点で必ず候補者名が存在するため)」に違反する
# 不正フィクスチャ(candidate_member_nameがnullのまま出力してしまうケースを想定)。
# validate_cross_field_rulesが検出できることを確認するためのネガティブテスト。
NEGATIVE_CASE_CONTRACTOR_TRANSFER_EXPIRED_NOTICE_NAME_NULL = {
    "status": "contractor_transfer_expired_notice",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": None,
    "delivery_notice": None,
    "care_notice": None,
    "subscription_procedure_notice": None,
    "member_retention_notice": None,
    "contractor_transfer_notice": None,
    "contractor_transfer_confirmation": None,
    "contractor_transfer_expired_notice": {
        "kind": "contractor_transfer_expired_notice",
        "candidate_member_name": None,
        "body": "契約者交代の確認期限が過ぎたため、手続きを一旦取り消しました。",
    },
    "checkout_notice": None,
}

# 2026-09-09 07:00 UTC追加(フェーズ58)。厳守事項7b違反(includes_checkout_url不一致)を
# 意図的に仕込んだ不正フィクスチャ。checkout_intentなのに実際のCheckout Session URLを
# 自己判断で発行したとしてincludes_checkout_url=trueで出力してしまうケースを想定。
# validate_cross_field_rulesが実際にこの違反を検出できることを確認するためのネガティブ
# テスト。NEGATIVE_CASE_PORTAL_LINK_MISMATCHと同じ設計思想を踏襲。
NEGATIVE_CASE_CHECKOUT_URL_MISMATCH = {
    "status": "checkout_intent",
    "out_of_scope_message": None,
    "missing_fields_request": None,
    "order_summary": None,
    "delivery_notice": None,
    "care_notice": None,
    "subscription_procedure_notice": None,
    "member_retention_notice": None,
    "contractor_transfer_notice": None,
    "contractor_transfer_confirmation": None,
    "contractor_transfer_expired_notice": None,
    "checkout_notice": {
        "kind": "checkout_intent",
        "body": "お申し込みのご案内をお送りしますね。",
        "includes_checkout_url": True,
    },
}


def main():
    total = 0
    failed = 0
    for case_id, instance in TEST_CASES.items():
        total += 1
        errors = validate_against_schema(instance, SCHEMA)
        errors += validate_cross_field_rules(instance)
        if errors:
            failed += 1
            print(f"[NG] {case_id}")
            for e in errors:
                print(f"      - {e}")
        else:
            print(f"[OK] {case_id}")

    # ネガティブテスト: category不一致がちゃんと検出されることを確認する
    total += 1
    neg_errors = validate_against_schema(NEGATIVE_CASE_CATEGORY_MISMATCH, SCHEMA)
    neg_errors += validate_cross_field_rules(NEGATIVE_CASE_CATEGORY_MISMATCH)
    if neg_errors:
        print("[OK] NEG1_category_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG1_category_mismatch_is_detected: category不一致を検出できませんでした(バリデータの不備)")

    # ネガティブテスト: includes_portal_linkの不一致(厳守事項7a(iv)相当違反)がちゃんと
    # 検出されることを確認する
    total += 1
    neg_errors2 = validate_against_schema(NEGATIVE_CASE_PORTAL_LINK_MISMATCH, SCHEMA)
    neg_errors2 += validate_cross_field_rules(NEGATIVE_CASE_PORTAL_LINK_MISMATCH)
    if neg_errors2:
        print("[OK] NEG2_portal_link_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors2:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG2_portal_link_mismatch_is_detected: includes_portal_link不一致を検出できませんでした(バリデータの不備)")

    # ネガティブテスト: member_retention_notice.kindのstatus不一致がちゃんと
    # 検出されることを確認する
    total += 1
    neg_errors3 = validate_against_schema(NEGATIVE_CASE_MEMBER_RETENTION_KIND_MISMATCH, SCHEMA)
    neg_errors3 += validate_cross_field_rules(NEGATIVE_CASE_MEMBER_RETENTION_KIND_MISMATCH)
    if neg_errors3:
        print("[OK] NEG3_member_retention_kind_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors3:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG3_member_retention_kind_mismatch_is_detected: kind不一致を検出できませんでした(バリデータの不備)")

    # ネガティブテスト: contractor_transfer_notice.kindのstatus不一致がちゃんと
    # 検出されることを確認する
    total += 1
    neg_errors4 = validate_against_schema(NEGATIVE_CASE_CONTRACTOR_TRANSFER_KIND_MISMATCH, SCHEMA)
    neg_errors4 += validate_cross_field_rules(NEGATIVE_CASE_CONTRACTOR_TRANSFER_KIND_MISMATCH)
    if neg_errors4:
        print("[OK] NEG4_contractor_transfer_kind_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors4:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG4_contractor_transfer_kind_mismatch_is_detected: kind不一致を検出できませんでした(バリデータの不備)")

    # ネガティブテスト: contractor_transfer_confirmation.kindのstatus不一致がちゃんと
    # 検出されることを確認する
    total += 1
    neg_errors5 = validate_against_schema(NEGATIVE_CASE_CONTRACTOR_TRANSFER_CONFIRMATION_KIND_MISMATCH, SCHEMA)
    neg_errors5 += validate_cross_field_rules(NEGATIVE_CASE_CONTRACTOR_TRANSFER_CONFIRMATION_KIND_MISMATCH)
    if neg_errors5:
        print("[OK] NEG5_contractor_transfer_confirmation_kind_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors5:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG5_contractor_transfer_confirmation_kind_mismatch_is_detected: kind不一致を検出できませんでした(バリデータの不備)")

    # ネガティブテスト: statusが別値なのにcontractor_transfer_expired_noticeが非nullの
    # まま残ってしまう排他性違反がちゃんと検出されることを確認する
    total += 1
    neg_errors6 = validate_against_schema(
        NEGATIVE_CASE_CONTRACTOR_TRANSFER_EXPIRED_NOTICE_PRESENT_WHEN_STATUS_MISMATCH, SCHEMA
    )
    neg_errors6 += validate_cross_field_rules(
        NEGATIVE_CASE_CONTRACTOR_TRANSFER_EXPIRED_NOTICE_PRESENT_WHEN_STATUS_MISMATCH
    )
    if neg_errors6:
        print("[OK] NEG6_contractor_transfer_expired_notice_present_when_status_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors6:
            print(f"      - {e}")
    else:
        failed += 1
        print(
            "[NG] NEG6_contractor_transfer_expired_notice_present_when_status_mismatch_is_detected: "
            "排他性違反を検出できませんでした(バリデータの不備)"
        )

    # ネガティブテスト: contractor_transfer_expired_notice.candidate_member_nameのnull
    # 制約違反(design.md3節「常に非null」)がちゃんと検出されることを確認する
    total += 1
    neg_errors7 = validate_against_schema(NEGATIVE_CASE_CONTRACTOR_TRANSFER_EXPIRED_NOTICE_NAME_NULL, SCHEMA)
    neg_errors7 += validate_cross_field_rules(NEGATIVE_CASE_CONTRACTOR_TRANSFER_EXPIRED_NOTICE_NAME_NULL)
    if neg_errors7:
        print("[OK] NEG7_contractor_transfer_expired_notice_name_null_is_detected (想定通りエラー検出)")
        for e in neg_errors7:
            print(f"      - {e}")
    else:
        failed += 1
        print(
            "[NG] NEG7_contractor_transfer_expired_notice_name_null_is_detected: "
            "candidate_member_nameのnull制約違反を検出できませんでした(バリデータの不備)"
        )

    # ネガティブテスト: checkout_notice.includes_checkout_urlの不一致(厳守事項7b違反)が
    # ちゃんと検出されることを確認する
    total += 1
    neg_errors8 = validate_against_schema(NEGATIVE_CASE_CHECKOUT_URL_MISMATCH, SCHEMA)
    neg_errors8 += validate_cross_field_rules(NEGATIVE_CASE_CHECKOUT_URL_MISMATCH)
    if neg_errors8:
        print("[OK] NEG8_checkout_url_mismatch_is_detected (想定通りエラー検出)")
        for e in neg_errors8:
            print(f"      - {e}")
    else:
        failed += 1
        print("[NG] NEG8_checkout_url_mismatch_is_detected: includes_checkout_url不一致を検出できませんでした(バリデータの不備)")

    print()
    print(f"合計 {total} 件中 {total - failed} 件パス、{failed} 件失敗")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
