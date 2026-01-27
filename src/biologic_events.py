"""Biologic event generator (Step 2-2)

共通イベント形式:
{
  "date": datetime.date,
  "drug": str,
  "exact_item_name": str,
  "units": int,
  "unit_price": int,
  "gross": int
}

サポート薬剤（現時点）:
- デュピクセント: 初回 units=2（300mg x2）、以降 14日ごと units=1
- ヌーカラ: 初回から毎回 units=1、28日ごと
- テゼスパイア: 初回から毎回 units=1、28日ごと

価格取得は src.biologic_price.get_biologic_price を使用し、見つからない場合は例外を伝播します。
"""
from __future__ import annotations

from datetime import date, timedelta
from typing import List, Dict

from src.biologic_price import get_biologic_price
from src.biologic_schedule import build_prescription_schedule


def _add_months(d: date, months: int) -> date:
    """簡易的に月数を足す。月末の厳密な扱いは省略（start_date 基準）。"""
    month = d.month - 1 + months
    year = d.year + month // 12
    month = month % 12 + 1
    day = min(d.day, 28)
    return date(year, month, day)


def _to_event_list(drug_label: str, exact_name: str, unit_price: int, presc_events: List[Dict[str, object]]) -> List[Dict]:
    """Convert prescription dicts (order,date,qty) to biologic event dicts with pricing."""
    evs: List[Dict] = []
    for pe in presc_events:
        qty = int(pe.get("qty") or 0)
        evs.append({
            "date": pe["date"],
            "drug": drug_label,
            "exact_item_name": exact_name,
            "units": qty,
            "unit_price": unit_price,
            "gross": qty * unit_price,
        })
    return evs


def generate_dupixent_events(start_date: date, months: int) -> List[Dict]:
    """デュピクセント: 初回2本、その後処方スケジュール + 維持期を追加（Step2）。"""
    if months <= 0:
        return []

    exact_name = "デュピクセント皮下注３００ｍｇペン"
    unit_price = get_biologic_price(exact_name)
    # Use default second/third qty = 1 for non-interactive generation
    end_date = _add_months(start_date, months)
    presc = build_prescription_schedule("dupixent", start_date, 1, 1, end_date)
    events = _to_event_list("デュピクセント", exact_name, unit_price, presc)

    events.sort(key=lambda e: e["date"])
    return events


def generate_nucala_events(start_date: date, months: int) -> List[Dict]:
    """ヌーカラ: 初回1本、その後処方スケジュール + 維持期を追加（Step2）。"""
    if months <= 0:
        return []

    exact_name = "ヌーカラ皮下注１００ｍｇペン"
    unit_price = get_biologic_price(exact_name)
    end_date = _add_months(start_date, months)
    presc = build_prescription_schedule("nucala", start_date, 1, 1, end_date)
    events = _to_event_list("ヌーカラ", exact_name, unit_price, presc)

    events.sort(key=lambda e: e["date"])
    return events


def generate_teze_events(start_date: date, months: int) -> List[Dict]:
    """テゼスパイア: 初回1本、その後処方スケジュール + 維持期を追加（Step2）。"""
    if months <= 0:
        return []

    exact_name = "テゼスパイア皮下注２１０ｍｇペン"
    unit_price = get_biologic_price(exact_name)
    end_date = _add_months(start_date, months)
    presc = build_prescription_schedule("tezespia", start_date, 1, 1, end_date)
    events = _to_event_list("テゼスパイア", exact_name, unit_price, presc)

    events.sort(key=lambda e: e["date"])
    return events


def generate_fasenra_events(start_date: date, months: int) -> List[Dict]:
    """ファセンラ: 初回1本、その後処方スケジュール + 維持期を追加（Step2）。"""
    if months <= 0:
        return []

    exact_name = "ファセンラ皮下注３０ｍｇペン"
    unit_price = get_biologic_price(exact_name)
    end_date = _add_months(start_date, months)
    presc = build_prescription_schedule("fasenra", start_date, 1, 1, end_date)
    events = _to_event_list("ファセンラ", exact_name, unit_price, presc)

    events.sort(key=lambda e: e["date"])
    return events


def generate_events(start_date: date, months: int, drug: str = "dupixent") -> List[Dict]:
    """汎用エントリポイント。drug 引数で生成ロジックを切替。

    drug の受け入れ例:
      - "dupixent" / "デュピクセント"
      - "nucala" / "ヌーカラ"
      - "teze" / "tezespia" / "テゼスパイア"
    """
    drug_key = (drug or "").strip().lower()
    if drug_key in ("dupixent", "デュピクセント"):
        return generate_dupixent_events(start_date, months)
    if drug_key in ("nucala", "ヌーカラ"):
        return generate_nucala_events(start_date, months)
    if drug_key in ("teze", "tezespia", "テゼスパイア"):
        return generate_teze_events(start_date, months)
    if drug_key in ("fasenra", "ファセンラ"):
        return generate_fasenra_events(start_date, months)
    raise NotImplementedError(f"Event generation for drug not implemented: {drug!r}")
