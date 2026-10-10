#!/usr/bin/env python3
"""
usage-and-fleet-overage-notification-design.md(フェーズ115)2節・3節で設計した、
月間生成回数上限接近通知(利用率90%方式)・保有台数プラン超過時のアップセル通知を
純粋関数として実装する(フェーズ115「5. 実装方針(次回候補)」)。

usage_counter・vehicleドキュメントの実際の読み書き(Firestore接続)は未実装のまま
(他venture同様、アカウント作成・外部サービス接続を伴う範囲はオーナー承認待ち)で、
本モジュールは「加算後カウント」を入力として受け取り、通知文(または非対象ならNone)を
返す計算のみを行う。実LLM呼び出しは行わない。
"""

PLAN_MONTHLY_LIMIT = {
    "light": 25,
    "standard": 70,
    "fleet": 220,
}  # pricing-plan.md「プラン案(仮)」の「含まれる生成回数」

PLAN_VEHICLE_LIMIT = {
    "light": 1,
    "standard": 3,
    "fleet": 10,
}  # pricing-plan.md「プラン案(仮)」の「対象台数」

PLAN_ORDER = ["light", "standard", "fleet"]  # アップセル案内の次プラン決定に使う昇順リスト

PLAN_LABEL = {
    "light": "ライトプラン",
    "standard": "スタンダードプラン",
    "fleet": "複数台プラン",
}

USAGE_LIMIT_NOTICE_RATIO = 0.9  # 2節: 月間生成回数上限の90%


def format_usage_limit_notice(count_after_increment: int, monthly_limit: int) -> "str | None":
    """2節: 月間生成回数上限の90%に達した生成完了時点で1回のみ通知する。

    `count_after_increment`は今回の生成を加算した後のカウント値。90%到達前の
    呼び出し元で「前回カウントが既に90%以上だったか」を突き合わせることで、呼び出し側が
    複数回通知を出さないようにする(本関数自体は閾値を跨いだ値であれば毎回True相当の文を
    返す点に注意。『1回のみ』の制御は呼び出し側がusage_counterの前回値と比較して行う、
    設計文書4節・kura-pasha方式と同じ責務分離)。
    """
    if monthly_limit <= 0:
        raise ValueError(f"monthly_limitは正の整数である必要がある: {monthly_limit!r}")
    if count_after_increment < 0:
        raise ValueError(f"count_after_incrementは0以上である必要がある: {count_after_increment!r}")

    threshold = _ceil_ratio(monthly_limit, USAGE_LIMIT_NOTICE_RATIO)
    if count_after_increment < threshold:
        return None
    remaining = monthly_limit - count_after_increment
    return (
        f"※今月の生成回数が上限{monthly_limit}回のうち{count_after_increment}回に達しました"
        f"(残り{remaining}回)。上限を超えた生成は従量課金となります。"
    )


def _ceil_ratio(limit: int, ratio: float) -> int:
    """limit*ratioの天井(ceil)を整数で返す。浮動小数点誤差を避けるため整数演算で行う
    (pricing-plan.mdのプラン値は整数のため、limit*ratio*10を整数除算で天井計算する)。"""
    scaled = limit * int(round(ratio * 10))
    quotient, remainder = divmod(scaled, 10)
    return quotient + 1 if remainder else quotient


def format_fleet_overage_notice(
    vehicle_count_before: int, vehicle_count_after: int, plan_id: str
) -> "str | None":
    """3節: 保有台数がプラン上限を新たに超えた登録1回のみ通知する。

    判定式(設計文書3節): vehicle_count_before <= planLimit[plan_id] < vehicle_count_after
    の場合のみ発火。既に超過済みの状態からさらに台数が増える場合は再通知しない。
    """
    if plan_id not in PLAN_VEHICLE_LIMIT:
        raise ValueError(f"未知のplan_id: {plan_id!r}")
    if vehicle_count_after < vehicle_count_before:
        raise ValueError(
            "vehicle_count_afterはvehicle_count_before以上である必要がある: "
            f"before={vehicle_count_before!r} after={vehicle_count_after!r}"
        )

    limit = PLAN_VEHICLE_LIMIT[plan_id]
    newly_exceeded = vehicle_count_before <= limit < vehicle_count_after
    if not newly_exceeded:
        return None

    next_plan_id = _next_plan(plan_id)
    if next_plan_id is None:
        return (
            f"※保有台数が10台を超えました。10台を超える規模のご利用については"
            "個別にご相談ください。"
        )
    current_limit = PLAN_VEHICLE_LIMIT[plan_id]
    next_limit = PLAN_VEHICLE_LIMIT[next_plan_id]
    return (
        f"※保有台数が現在のプラン({PLAN_LABEL[plan_id]})の対象台数{current_limit}台を"
        f"超えました。{PLAN_LABEL[next_plan_id]}({next_limit}台まで)への"
        "プラン変更をご検討ください。"
    )


def _next_plan(plan_id: str) -> "str | None":
    """plan_idの次(上位)プランのplan_idを返す。既に最上位(fleet)ならNone。"""
    index = PLAN_ORDER.index(plan_id)
    if index + 1 >= len(PLAN_ORDER):
        return None
    return PLAN_ORDER[index + 1]


def determine_usage_limit_notice(
    count_before_increment: int, count_after_increment: int, monthly_limit: int
) -> "str | None":
    """format_usage_limit_notice()のdocstringが呼び出し側の責務とした「1回のみ通知」の
    判定を実装する(フェーズ116次回候補(2))。format_fleet_overage_notice()と同型の
    before/after判定(閾値をこの増分で新たに跨いだ場合のみ発火)に揃える。
    """
    if count_before_increment > count_after_increment:
        raise ValueError(
            "count_before_incrementはcount_after_increment以下である必要がある: "
            f"before={count_before_increment!r} after={count_after_increment!r}"
        )
    threshold = _ceil_ratio(monthly_limit, USAGE_LIMIT_NOTICE_RATIO)
    if count_before_increment >= threshold:
        return None
    return format_usage_limit_notice(count_after_increment, monthly_limit)


class UsageCounterStoreProtocol:
    """usage_counterドキュメントの読み書きを模したProtocol(design 5節)。実際のFirestore
    接続は未実装で、本venture内ではInMemoryUsageCounterStoreのみを実装として用意する。
    """

    def get_count(self, user_id: str, year_month: str) -> int:
        raise NotImplementedError

    def increment_count(self, user_id: str, year_month: str) -> "tuple[int, int]":
        """1回分の生成を加算し、(加算前カウント, 加算後カウント)を返す。"""
        raise NotImplementedError


class VehicleCountStoreProtocol:
    """vehicleドキュメント件数の読み書きを模したProtocol(design 5節)。InMemory実装のみ。"""

    def get_vehicle_count(self, user_id: str) -> int:
        raise NotImplementedError

    def increment_vehicle_count(self, user_id: str, delta: int = 1) -> "tuple[int, int]":
        """台数登録を加算し、(加算前台数, 加算後台数)を返す。"""
        raise NotImplementedError


class InMemoryUsageCounterStore(UsageCounterStoreProtocol):
    """usage_counterドキュメントを模したInMemory実装(Firestore接続は未実装のまま)。"""

    def __init__(self) -> None:
        self._counts: "dict[tuple[str, str], int]" = {}

    def get_count(self, user_id: str, year_month: str) -> int:
        return self._counts.get((user_id, year_month), 0)

    def increment_count(self, user_id: str, year_month: str) -> "tuple[int, int]":
        key = (user_id, year_month)
        before = self._counts.get(key, 0)
        after = before + 1
        self._counts[key] = after
        return before, after


class InMemoryVehicleCountStore(VehicleCountStoreProtocol):
    """vehicleドキュメント件数を模したInMemory実装(Firestore接続は未実装のまま)。"""

    def __init__(self) -> None:
        self._counts: "dict[str, int]" = {}

    def get_vehicle_count(self, user_id: str) -> int:
        return self._counts.get(user_id, 0)

    def increment_vehicle_count(self, user_id: str, delta: int = 1) -> "tuple[int, int]":
        if delta <= 0:
            raise ValueError(f"deltaは正の整数である必要がある: {delta!r}")
        before = self._counts.get(user_id, 0)
        after = before + delta
        self._counts[user_id] = after
        return before, after


def record_generation_and_get_usage_notice(
    store: UsageCounterStoreProtocol, user_id: str, year_month: str, plan_id: str
) -> "str | None":
    """1回分の生成完了をusage_counterに加算し、90%閾値を新たに跨いだ場合のみ通知文を
    返す(store.increment_count()で加算前後を取得し、determine_usage_limit_notice()に
    委譲することで『1回のみ』を保証する)。
    """
    if plan_id not in PLAN_MONTHLY_LIMIT:
        raise ValueError(f"未知のplan_id: {plan_id!r}")
    before, after = store.increment_count(user_id, year_month)
    return determine_usage_limit_notice(before, after, PLAN_MONTHLY_LIMIT[plan_id])


def record_vehicle_and_get_overage_notice(
    store: VehicleCountStoreProtocol, user_id: str, plan_id: str, delta: int = 1
) -> "str | None":
    """台数登録をvehicleドキュメント件数に加算し、新たにプラン上限を超えた場合のみ通知文を
    返す(store.increment_vehicle_count()で加算前後を取得し、format_fleet_overage_notice()
    に委譲する)。
    """
    before, after = store.increment_vehicle_count(user_id, delta)
    return format_fleet_overage_notice(before, after, plan_id)
