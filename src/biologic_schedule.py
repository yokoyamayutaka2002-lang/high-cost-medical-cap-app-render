from __future__ import annotations

from datetime import date, timedelta
from typing import Dict, List


def _normalize_drug_key(drug_name: str) -> str:
    return (drug_name or "").strip().lower()


def build_prescription_schedule(
    drug_key: str,
    start_date: date,
    qty2: int,
    qty3: int,
    end_date: date,
) -> List[Dict[str, object]]:
    """Build prescription schedule driven by prescribed quantities.

    Rules implemented exactly as specified in the architecture request:
    - Each drug has a days-per-unit value.
    - Order 1: date = start_date, qty = initial fixed per drug.
    - Order 2: date = order1_date + (initial_qty * days_per_unit), qty = qty2 (user input).
    - Order 3: date = order2_date + (qty2 * days_per_unit), qty = qty3 (user input).
    - Order 4: date = order3_date + (qty3 * days_per_unit), qty = maintenance fixed per drug.
    - Order 5+: repeating maintenance events with step = (maintenance_qty * days_per_unit).

    Returns list of dicts: {"order": int, "date": date, "qty": int}
    """
    if not isinstance(start_date, date):
        raise ValueError("start_date must be a date")
    if not isinstance(end_date, date):
        raise ValueError("end_date must be a date")
    try:
        q2 = int(qty2)
        q3 = int(qty3)
    except Exception:
        raise ValueError("qty2 and qty3 must be integers")
    if q2 <= 0 or q3 <= 0:
        raise ValueError("qty2 and qty3 must be positive integers")

    key = _normalize_drug_key(drug_key)

    # days per unit and initial/maintenance quantities
    if "dupixent" in key or "デュピクセント" in drug_key:
        days_per_unit = 14
        initial_qty = 2
        maint_qty = 6
    elif "nucala" in key or "ヌーカラ" in drug_key:
        days_per_unit = 28
        initial_qty = 1
        maint_qty = 3
    elif "teze" in key or "tezespia" in key or "tezspire" in key or "テゼスパイア" in drug_key:
        days_per_unit = 28
        initial_qty = 1
        maint_qty = 3
    elif "fasenra" in key or "ファセンラ" in drug_key:
        days_per_unit = 56
        initial_qty = 1
        maint_qty = 1
    else:
        raise ValueError(f"Unsupported drug: {drug_key!r}")

    events: List[Dict[str, object]] = []

    # Order 1
    o1_date = start_date
    if o1_date <= end_date:
        # Dupixent first dose has fixed 14-day exposure regardless of qty
        if "dupixent" in key or "デュピクセント" in drug_key:
            o1_days = days_per_unit  # 14
        else:
            o1_days = int(initial_qty * days_per_unit)
        events.append({"order": 1, "date": o1_date, "qty": int(initial_qty), "days": int(o1_days)})

    # Order 2: for most drugs date depends on initial_qty, but Dupixent is special:
    # Dupixent: 2回目は start_date + 14日（1 unit 相当）
    if "dupixent" in key or "デュピクセント" in drug_key:
        o2_date = o1_date + timedelta(days=days_per_unit)
    else:
        o2_date = o1_date + timedelta(days=initial_qty * days_per_unit)
    if o2_date <= end_date:
        # days for order 2 corresponds to qty2 * days_per_unit
        o2_days = int(q2 * days_per_unit)
        events.append({"order": 2, "date": o2_date, "qty": int(q2), "days": o2_days})

    # Order 3: date depends on qty2
    o3_date = o2_date + timedelta(days=q2 * days_per_unit)
    if o3_date <= end_date:
        o3_days = int(q3 * days_per_unit)
        events.append({"order": 3, "date": o3_date, "qty": int(q3), "days": o3_days})

    # Order 4: date depends on qty3, qty is maintenance fixed
    o4_date = o3_date + timedelta(days=q3 * days_per_unit)
    if o4_date <= end_date:
        # maintenance is fixed interval (maint_qty * days_per_unit)
        o4_days = int(maint_qty * days_per_unit)
        events.append({"order": 4, "date": o4_date, "qty": int(maint_qty), "days": o4_days})

    # Maintenance loop from order 5 onwards
    step_days = maint_qty * days_per_unit
    next_order = 5
    next_date = o4_date + timedelta(days=step_days)
    while next_date <= end_date:
        events.append({"order": next_order, "date": next_date, "qty": int(maint_qty), "days": int(step_days)})
        next_order += 1
        next_date = next_date + timedelta(days=step_days)

    return events


__all__ = ["build_prescription_schedule"]


def generate_prescription_schedule(
    drug_name: str,
    first_prescription_date: date,
    second_prescription_qty: int,
    third_prescription_qty: int,
) -> List[Dict[str, object]]:
    """Backward-compatible wrapper that reproduces the previous 3-event API.

    Keeps original behavior: returns exactly three events (orders 1..3) where
    order1 qty is fixed, order2 qty is the provided `second_prescription_qty`,
    and order3 qty is `third_prescription_qty`. Dates follow the clinical
    prescription rules: order2 = order1 + interval, order3 = order2 + (second_qty * interval).
    """
    if not isinstance(first_prescription_date, date):
        raise ValueError("first_prescription_date must be a date")
    try:
        s_qty = int(second_prescription_qty)
        t_qty = int(third_prescription_qty)
    except Exception:
        raise ValueError("second_prescription_qty and third_prescription_qty must be integers")
    if s_qty <= 0 or t_qty <= 0:
        raise ValueError("prescription quantities must be positive integers")

    # Reuse build_prescription_schedule to compute dates, but limit qty for 3rd
    # Build with an end_date far enough to include the 3rd event
    # compute interval and initial qty by calling build_prescription_schedule parameters
    # Determine interval via temporary dispatch
    key = _normalize_drug_key(drug_name)
    if "dupixent" in key or "デュピクセント" in drug_name:
        interval_days = 14
        initial_qty = 2
    elif "nucala" in key or "ヌーカラ" in drug_name:
        interval_days = 28
        initial_qty = 1
    elif "teze" in key or "tezespia" in key or "tezspire" in key or "テゼスパイア" in drug_name:
        interval_days = 28
        initial_qty = 1
    elif "fasenra" in key or "ファセンラ" in drug_name:
        interval_days = 56
        initial_qty = 1
    else:
        raise ValueError(f"Unsupported drug: {drug_name!r}")

    e1_date = first_prescription_date
    e2_date = e1_date + timedelta(days=interval_days)
    e3_date = e2_date + timedelta(days=s_qty * interval_days)

    # include days fields for backward compatibility
    if "dupixent" in key or "デュピクセント" in drug_name:
        e1_days = interval_days
    else:
        e1_days = int(initial_qty * interval_days)
    e2_days = int(s_qty * interval_days)
    e3_days = int(t_qty * interval_days)

    return [
        {"order": 1, "date": e1_date, "qty": int(initial_qty), "days": e1_days},
        {"order": 2, "date": e2_date, "qty": int(s_qty), "days": e2_days},
        {"order": 3, "date": e3_date, "qty": int(t_qty), "days": e3_days},
    ]


def extend_maintenance_schedule(
    initial_events: List[Dict[str, object]],
    drug: str,
    end_date: date,
) -> List[Dict[str, object]]:
    """Backward-compatible wrapper to produce maintenance events starting after 3rd event.

    Uses the same maintenance stepping as `build_prescription_schedule` (step = maint_qty * interval_days).
    Returns list of events with orders starting at 4.
    """
    if not isinstance(end_date, date):
        raise ValueError("end_date must be a date")
    if not isinstance(initial_events, list) or len(initial_events) < 3:
        raise ValueError("initial_events must be a list with at least 3 events")

    try:
        third = initial_events[2]
        third_date = third["date"]
    except Exception:
        raise ValueError("initial_events must contain dicts with a 'date' key")
    if not isinstance(third_date, date):
        raise ValueError("initial_events[2]['date'] must be a date")

    key = _normalize_drug_key(drug)
    if "dupixent" in key or "デュピクセント" in drug:
        interval_days = 14
        maint_qty = 6
    elif "nucala" in key or "ヌーカラ" in drug:
        interval_days = 28
        maint_qty = 3
    elif "teze" in key or "tezespia" in key or "tezspire" in key or "テゼスパイア" in drug:
        interval_days = 28
        maint_qty = 3
    elif "fasenra" in key or "ファセンラ" in drug:
        interval_days = 56
        maint_qty = 1
    else:
        raise ValueError(f"Unsupported drug for maintenance: {drug!r}")

    maintenance_events: List[Dict[str, object]] = []
    step_days = interval_days * maint_qty
    next_date = third_date + timedelta(days=step_days)
    next_order = 4
    while next_date <= end_date:
        maintenance_events.append({"order": next_order, "date": next_date, "qty": int(maint_qty), "days": int(step_days)})
        next_order += 1
        next_date = next_date + timedelta(days=step_days)

    return maintenance_events

__all__.extend(["generate_prescription_schedule", "extend_maintenance_schedule"])
