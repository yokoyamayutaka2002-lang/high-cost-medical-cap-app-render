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
    """Apply monthly subsidy cap across biologic events in-place.

    Algorithm (per spec):
    1) monthly_after_kougaku[YYYY-MM] = sum(event.after_kougaku)  # here event.after_kougaku == ev['actual_payment']
    2) monthly_after_subsidy = min(monthly_after_kougaku, subsidy_cap)
    3) Distribute monthly_after_subsidy back to events proportionally to event.after_kougaku

    - monthly_map: map of YYYY-MM -> { 'events': [ { 'actual_payment': int, ... }, ... ], ... }
    - subsidy_cap: monthly cap (int) or None to skip subsidy

    Returns the same monthly_map with each event annotated with 'final_pay' and
    each month annotated with 'post_subsidy_self_pay'.
    """
    for ym, bucket in monthly_map.items():
        evs = bucket.get('events') or []
        # sum of per-event amounts after high-cost cap (after_kougaku)
        try:
            total_after_kougaku = sum(int(ev.get('actual_payment') or 0) for ev in evs)
        except Exception:
            total_after_kougaku = 0

        if subsidy_cap is not None:
            try:
                monthly_after_subsidy = min(int(total_after_kougaku), int(subsidy_cap))
            except Exception:
                monthly_after_subsidy = int(total_after_kougaku)
        else:
            monthly_after_subsidy = int(total_after_kougaku)

        # store the monthly-level post-subsidy total (used by aggregates)
        bucket['post_subsidy_self_pay'] = int(monthly_after_subsidy)

        # distribute proportionally; preserve zeros and ensure integer sum matches monthly_after_subsidy
        if not evs:
            continue
        if total_after_kougaku > 0:
            assigned = 0
            for i, ev in enumerate(evs):
                pre = int(ev.get('actual_payment') or 0)
                if i < len(evs) - 1:
                    # rounding per-event; last event receives remainder
                    share = int(round((pre / float(total_after_kougaku)) * monthly_after_subsidy)) if total_after_kougaku > 0 else 0
                    ev['final_pay'] = max(0, int(share))
                    assigned += int(ev['final_pay'])
                else:
                    ev['final_pay'] = max(0, int(monthly_after_subsidy) - assigned)
        else:
            # no pre-subsidy amounts -> zero out final_pay
            for ev in evs:
                ev['final_pay'] = 0

    return monthly_map
