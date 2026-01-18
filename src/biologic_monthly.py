"""月次集計ヘルパー（Step 2-3）

役割:
 - 投与イベント配列を受け取り、月次合算を返す

提供関数:
 - aggregate_events_by_month(events) -> Dict[str,int]
 - aggregate_events_by_month_detailed(events) -> Dict[str, Dict]

仕様:
 - イベントの date から YYYY-MM を決定して合算
 - gross をそのまま足し合わせる（丸め・補正なし）
 - イベント配列は順不同でも正しく集計
 - エラーは握りつぶさず伝播する（入力イベントの妥当性は呼び出し側が保証）
"""
from __future__ import annotations

from collections import defaultdict
from datetime import date
from typing import Any, Dict, Iterable, List


def _ym_from_date(d: Any) -> str:
    """date-like から YYYY-MM を返す。date 型であることを期待する。"""
    if not hasattr(d, "year") or not hasattr(d, "month"):
        raise TypeError(f"event[\"date\"] must be date-like, got: {type(d)!r}")
    return f"{d.year:04d}-{d.month:02d}"


def aggregate_events_by_month(events: Iterable[Dict[str, Any]]) -> Dict[str, int]:
    """イベント配列を集計し、{ 'YYYY-MM': total_gross } を返す。

    - events: 各要素が共通イベント形式の dict を持つイテラブル
    - gross 欄は int として扱う（int に変換できない場合は例外が発生する）
    """
    totals: Dict[str, int] = defaultdict(int)
    for ev in events:
        # 必須キーの最小限チェック（エラーは伝播）
        d = ev["date"]
        ym = _ym_from_date(d)
        gross = ev["gross"]
        # 明示的に int に変換（失敗すれば例外）
        totals[ym] += int(gross)
    return dict(totals)


def aggregate_events_by_month_detailed(events: Iterable[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """詳細版: { 'YYYY-MM': { 'total': int, 'events': [event,...] } }

    - 入力イベントはソートされず受け取れる。出力の 'events' は日付昇順で返す。
    - gross はそのまま加算する。
    """
    buckets: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    for ev in events:
        d = ev["date"]
        ym = _ym_from_date(d)
        buckets[ym].append(ev)

    result: Dict[str, Dict[str, Any]] = {}
    for ym, evs in buckets.items():
        # 日付順にソート（安定ソート）
        evs_sorted = sorted(evs, key=lambda e: e["date"])
        total = sum(int(e["gross"]) for e in evs_sorted)
        result[ym] = {"total": total, "events": evs_sorted}
    return result


# 利用例（モジュール直下での簡単な説明）
__doc__ += """
利用例:

from src.biologic_monthly import aggregate_events_by_month

# events は src.biologic_events.generate_events などで生成された配列
monthly = aggregate_events_by_month(events)
# 例:
# {
#   '2025-04': 123456,
#   '2025-05': 234567,
# }
"""


def merge_monthly_costs(
    base_monthly_costs: Dict[str, int],
    biologic_monthly_costs: Dict[str, int],
) -> Dict[str, int]:
    """既存の月次医療費と生物学的製剤の月次合計をマージして返す。

    - 両方に存在する月は加算する。
    - どちらか一方のみの月はその値を採用する。
    - 月キーは `YYYY-MM` 文字列を期待する。
    - 入力の数値変換に失敗した場合は例外を伝播する（握りつぶさない）。
    """
    merged: Dict[str, int] = {}
    # キー集合は順序に依存しない
    all_keys = set(base_monthly_costs) | set(biologic_monthly_costs)
    for ym in all_keys:
        a = base_monthly_costs.get(ym, 0)
        b = biologic_monthly_costs.get(ym, 0)
        # int に変換して加算（失敗すれば例外伝播）
        merged[ym] = int(a) + int(b)
    return merged


def integrate_biologic_monthly(
        base_monthly_costs: Dict[str, int],
        events: Iterable[Dict[str, Any]],
) -> Dict[str, int]:
        """生物学的製剤のイベント一覧を月次集計して `base_monthly_costs` とマージして返す。

        - `base_monthly_costs`: 既存ロジックで得られた月次医療費辞書（YYYY-MM -> int）
        - `events`: `src.biologic_events.generate_events` などが返すイベント一覧
        - 戻り値: 両者を合算した月次医療費辞書（YYYY-MM -> int）

        例:
            merged = integrate_biologic_monthly(base, events)
        """
        biologic_monthly = aggregate_events_by_month(events)
        return merge_monthly_costs(base_monthly_costs, biologic_monthly)


def apply_monthly_subsidy_to_monthly_map(monthly_map: Dict[str, Dict[str, Any]], subsidy_cap: int | None) -> Dict[str, Dict[str, Any]]:
    """Apply monthly subsidy cap and produce canonical per-event and per-month fields.

    This function enforces the Single Source of Truth (SSOT) requirement:
    - Each month in `monthly_map[ym]['post_subsidy_self_pay']` is the canonical
      monthly post-subsidy total used by downstream logic.
    - Each event is annotated with `self_pay` (int) and `post_subsidy_payment` (int).

    Algorithm (strict spec):
    1) Ensure every event has `self_pay` (int). If absent, derive from `actual_payment`.
    2) month_total_self_pay = sum(event['self_pay'])
    3) post_subsidy_self_pay = min(month_total_self_pay, subsidy_cap) if subsidy_cap is not None else month_total_self_pay
    4) subsidy_amount = max(0, month_total_self_pay - post_subsidy_self_pay)
    5) Distribute `subsidy_amount` proportionally to each event's `self_pay` to compute
       the per-event reduction; set event['post_subsidy_payment'] = self_pay - alloc.
       Use integer arithmetic and put any rounding remainder onto the last event.
    6) Assert that sum(event['post_subsidy_payment']) == post_subsidy_self_pay and raise on mismatch.

    - monthly_map: map of YYYY-MM -> { 'events': [ { 'actual_payment': int, ... }, ... ], ... }
    - subsidy_cap: monthly cap (int) or None to skip subsidy

    Returns the same monthly_map with each event annotated and each month annotated
    with 'post_subsidy_self_pay'. Raises AssertionError on any allocation mismatch.
    """
    for ym, bucket in monthly_map.items():
        evs = bucket.get('events') or []

        # 1) Ensure canonical `self_pay` on each event
        for ev in evs:
            if 'self_pay' in ev and ev['self_pay'] is not None:
                # preserve provided value but ensure it's an int (fail fast on bad data)
                ev['self_pay'] = int(ev['self_pay'])
            else:
                ev['self_pay'] = int(ev.get('actual_payment') or 0)

        # 2) month total
        month_total_self_pay = int(sum(int(ev.get('self_pay') or 0) for ev in evs))

        # 3) compute post_subsidy_self_pay (SSOT monthly value)
        if subsidy_cap is not None:
            post_subsidy = int(min(month_total_self_pay, int(subsidy_cap)))
        else:
            post_subsidy = int(month_total_self_pay)

        bucket['post_subsidy_self_pay'] = int(post_subsidy)

        # 4) subsidy amount (amount reduced from patient responsibility)
        subsidy_amount = int(max(0, month_total_self_pay - post_subsidy))

        # 5) per-event distribution
        if not evs:
            # nothing to do
            continue

        if subsidy_amount == 0 or month_total_self_pay == 0:
            for ev in evs:
                ev['post_subsidy_payment'] = int(ev.get('self_pay') or 0)
        else:
            allocated = 0
            for idx, ev in enumerate(evs):
                sp = int(ev.get('self_pay') or 0)
                if idx < len(evs) - 1:
                    # proportional share of the total reduction
                    alloc = int(round((sp * subsidy_amount) / float(month_total_self_pay))) if month_total_self_pay > 0 else 0
                    allocated += int(alloc)
                else:
                    alloc = int(subsidy_amount - allocated)
                post = int(max(0, sp - int(alloc)))
                ev['post_subsidy_payment'] = post

        # 6) assert sums match SSOT
        sum_after = int(sum(int(e.get('post_subsidy_payment') or 0) for e in evs))
        expected = int(bucket.get('post_subsidy_self_pay') or 0)
        if sum_after != expected:
            raise AssertionError(f"SUBSIDY ALLOCATION MISMATCH for {ym}: sum_after={sum_after} expected(post_subsidy_self_pay)={expected}")

    return monthly_map
