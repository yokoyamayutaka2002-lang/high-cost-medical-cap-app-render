import csv
from pathlib import Path
from math import floor
import re

# Cache for biologic report prices (exact_item_name -> price_yen int)
_BIOLOGIC_REPORT_PRICES = None


def _load_biologic_report_prices():
    global _BIOLOGIC_REPORT_PRICES
    if _BIOLOGIC_REPORT_PRICES is not None:
        return _BIOLOGIC_REPORT_PRICES
    prices = {}
    # Prefer data/drug_price.csv as the authoritative source for per-unit prices
    data_path = Path(__file__).parent.parent / 'data' / 'drug_price.csv'
    if data_path.exists():
        try:
            with data_path.open(encoding='utf-8') as f:
                reader = csv.DictReader(f)
                for r in reader:
                    # Prefer `drug_name` column; fall back to other name columns
                    name = (r.get('drug_name') or r.get('exact_item_name') or r.get('品名') or '').strip()
                    raw = r.get('price_per_unit') or r.get('price_yen') or r.get('unit_price') or r.get('price')
                    if not name or raw in (None, ''):
                        continue
                    s = str(raw).strip().replace(',', '')
                    if not re.fullmatch(r"\d+", s):
                        continue
                    prices[name] = int(s)
            _BIOLOGIC_REPORT_PRICES = prices
            return prices
        except Exception:
            # If parsing fails, fall through to try reports CSV below
            prices = {}

    # Fallback: legacy reports CSV if data file not available or failed
    path = Path(__file__).parent.parent / 'reports' / 'biologic_drug_price_2025-04.csv'
    if not path.exists():
        _BIOLOGIC_REPORT_PRICES = prices
        return prices
    with path.open(encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            name = (r.get('exact_item_name') or r.get('品名') or r.get('display_name') or '').strip()
            raw = r.get('price_yen') or r.get('price') or r.get('price_per_unit') or r.get('薬価')
            if not name:
                continue
            if raw is None:
                continue
            s = str(raw).strip().replace(',', '')
            if not re.fullmatch(r"\d+", s):
                continue
            prices[name] = int(s)
    _BIOLOGIC_REPORT_PRICES = prices
    return prices


def is_high_cost_12w(
    system_version: str,
    income_code: str,
    age_group: str,
    drug_id: str
) -> bool:
    data_dir = Path(__file__).parent.parent / "data"
    drug_price_path = data_dir / "drug_price.csv"
    limit_table_path = data_dir / "limit_table.csv"

    with drug_price_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        drug_row = None
        for row in reader:
            if row["drug_id"] == drug_id:
                drug_row = row
                break
        if drug_row is None:
            raise ValueError(f"drug_id {drug_id} not found")

    try:
        price_per_unit = int(drug_row["price_per_unit"])
        units_per_12w = int(drug_row["units_per_12w"])
    except Exception:
        raise ValueError("drug_price.csv の値が不正です")

    self_pay = int(price_per_unit * units_per_12w * 0.3)

    with limit_table_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        limit_row = None
        for row in reader:
            if (
                row["system_version"] == system_version
                and row["income_code"] == income_code
                and row["age_group"] == age_group
            ):
                limit_row = row
                break
        if limit_row is None:
            raise ValueError("limit_table.csv に該当データなし")

    try:
        monthly_limit = int(limit_row["monthly_limit"])
    except Exception:
        raise ValueError("limit_table.csv の値が不正です")

    return self_pay > monthly_limit


def simulate_annual_cost(
    system_version: str,
    income_code: str,
    age_group: str,
    drug_id: str,
    prescription_interval_weeks: int = 12,
    existing_weekly_cost_yen: int = 0,
    existing_dispense_weeks: int = 12,
    include_existing: bool = False,
    xolair_dose_info: tuple | None = None,
) -> dict:
    """Wrapper around the core annual simulation.

    This wrapper preserves the original behavior when `include_existing` is False
    (backward compatibility). When `include_existing` is True, it computes both
    the biologic-only and biologic+existing variants and returns the combined
    result while keeping top-level numeric keys for callers that expect the
    original shape.
    """
    # compute existing cost per biologic event (one-time added cost when include_existing)
    try:
        existing_dispense_weeks = int(existing_dispense_weeks or 0)
        existing_weekly_cost_yen = int(existing_weekly_cost_yen or 0)
    except Exception:
        raise ValueError("existing inputs must be integers")

    existing_cost_for_event = existing_weekly_cost_yen * existing_dispense_weeks

    # compute biologic-only
    biologic_only = _simulate_annual_cost_core(
        system_version=system_version,
        income_code=income_code,
        age_group=age_group,
        drug_id=drug_id,
        prescription_interval_weeks=prescription_interval_weeks,
        per_event_extra=0,
        xolair_dose_info=xolair_dose_info,
    )

    if not include_existing:
        return biologic_only

    # compute biologic + existing aggregated into each event
    biologic_plus_existing = _simulate_annual_cost_core(
        system_version=system_version,
        income_code=income_code,
        age_group=age_group,
        drug_id=drug_id,
        prescription_interval_weeks=prescription_interval_weeks,
        per_event_extra=existing_cost_for_event,
        xolair_dose_info=xolair_dose_info,
    )

    result = dict(biologic_plus_existing)
    result["biologic_only"] = biologic_only
    result["biologic_plus_existing"] = biologic_plus_existing
    result["existing_cost_for_event"] = existing_cost_for_event
    result["difference_annual_cost"] = int(biologic_plus_existing.get("annual_cost", 0)) - int(biologic_only.get("annual_cost", 0))

    return result


def _simulate_annual_cost_core(
    system_version: str,
    income_code: str,
    age_group: str,
    drug_id: str,
    prescription_interval_weeks: int = 12,
    per_event_extra: int = 0,
    xolair_dose_info: tuple | None = None,
) -> dict:
    """Core implementation of the original simulate_annual_cost logic.

    `per_event_extra` is added to the per-event self_pay before applying
    the applied monthly limit. When `per_event_extra == 0` behavior matches
    the prior implementation.
    """
    data_dir = Path(__file__).parent.parent / "data"
    drug_price_path = data_dir / "drug_price.csv"
    limit_table_path = data_dir / "limit_table.csv"

    # Special-case Xolair: if caller provided dose info, compute per-event
    # gross by mapping dose -> pen combinations and looking up exact
    # pen prices from the biologic report. This keeps the rest of the
    # logic unchanged by setting `self_pay` appropriately.
    self_pay = None
    if xolair_dose_info and drug_id and ('xolair' in str(drug_id).lower()):
        try:
            from src.xolair import build_xolair_prescription
        except Exception:
            raise
        dose_mg, interval_weeks = xolair_dose_info
        # override interval
        try:
            prescription_interval_weeks = int(interval_weeks)
        except Exception:
            prescription_interval_weeks = prescription_interval_weeks

        # load report prices
        prices = _load_biologic_report_prices()
        presc = build_xolair_prescription(int(dose_mg))
        if not presc:
            raise ValueError(f"No pen mapping for Xolair dose: {dose_mg}")
        per_event_gross = 0
        for it in presc:
            name = it.get('drug_name')
            qty = int(it.get('qty') or 0)
            if name not in prices:
                raise ValueError(f"Biologic price not found for exact item name: {name!r}")
            per_event_gross += int(prices[name]) * qty

        # burdened self-pay per event (0.3) as used elsewhere in calculator
        self_pay = float(per_event_gross) * 0.3

    else:
        # load drug
        with drug_price_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            drug_row = None
            for row in reader:
                if row["drug_id"] == drug_id:
                    drug_row = row
                    break
            if drug_row is None:
                raise ValueError("drug_id not found")

        try:
            price_per_unit = int(drug_row["price_per_unit"])
            units_per_12w = int(drug_row["units_per_12w"])
        except Exception:
            raise ValueError("drug_price.csv の値が不正です")

        # self_pay kept as float for per-event min comparison, applied is cast to int
        self_pay = price_per_unit * units_per_12w * 0.3

    # --- Strict rule: handle 70+ outpatient special cases first (do NOT consult limit_table.csv) ---
    if age_group == "over70":
        # If caller passed canonical category codes directly, apply outpatient special immediately
        if income_code in ("G", "L1", "L2"):
            events_per_year = floor(52 / prescription_interval_weeks)

            if income_code == "G":
                applied_monthly_limit = 18000
                applied_annual_limit = 144000
            else:
                # L1 or L2
                applied_monthly_limit = 8000
                applied_annual_limit = None

            total = 0
            events = []
            is_many_times_applied = False
            many_times_start_event = None

            for i in range(1, events_per_year + 1):
                applied = int(min(self_pay + per_event_extra, applied_monthly_limit))
                total += applied
                events.append({
                    "event": i,
                    "applied_limit": applied_monthly_limit,
                    "is_many_times": False,
                    "applied": applied,
                })

                if applied_annual_limit and total >= applied_annual_limit:
                    total = applied_annual_limit
                    break

            try:
                monthly_average_cost = int(round(total / 12))
            except Exception:
                monthly_average_cost = int(total // 12)

            return {
                "annual_cost": total,
                "monthly_average_cost": monthly_average_cost,
                "is_many_times_applied": is_many_times_applied,
                "many_times_start_event": many_times_start_event,
                "events": events,
            }

        # Otherwise, the caller passed a CSV-style income_code (e.g. R9_...)
        with limit_table_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            lookup_row = None
            for row in reader:
                if (
                    row["system_version"] == system_version
                    and row["income_code"] == income_code
                    and row["age_group"] == age_group
                ):
                    lookup_row = row
                    break

        if lookup_row is not None:
            income_label = (lookup_row.get("income_label") or "")
            outpatient_limit_70 = lookup_row.get("outpatient_limit_70plus")

            # Non-tax detection (L1/L2)
            if "非課税" in income_label or "一定所得以下" in income_label or "低所得" in income_label:
                # treat as L1/L2
                events_per_year = floor(52 / prescription_interval_weeks)
                applied_monthly_limit = 8000
                applied_annual_limit = None

                total = 0
                events = []
                is_many_times_applied = False
                many_times_start_event = None

                for i in range(1, events_per_year + 1):
                    applied = int(min(self_pay + per_event_extra, applied_monthly_limit))
                    total += applied
                    events.append({
                        "event": i,
                        "applied_limit": applied_monthly_limit,
                        "is_many_times": False,
                        "applied": applied,
                    })

                    if applied_annual_limit and total >= applied_annual_limit:
                        total = applied_annual_limit
                        break

                try:
                    monthly_average_cost = int(round(total / 12))
                except Exception:
                    monthly_average_cost = int(total // 12)

                return {
                    "annual_cost": total,
                    "monthly_average_cost": monthly_average_cost,
                    "is_many_times_applied": is_many_times_applied,
                    "many_times_start_event": many_times_start_event,
                    "events": events,
                }

            # Outpatient-specific limit present -> treat as G
            if outpatient_limit_70 and outpatient_limit_70.strip() != "":
                events_per_year = floor(52 / prescription_interval_weeks)
                applied_monthly_limit = 18000
                applied_annual_limit = 144000

                total = 0
                events = []
                is_many_times_applied = False
                many_times_start_event = None

                for i in range(1, events_per_year + 1):
                    applied = int(min(self_pay + per_event_extra, applied_monthly_limit))
                    total += applied
                    events.append({
                        "event": i,
                        "applied_limit": applied_monthly_limit,
                        "is_many_times": False,
                        "applied": applied,
                    })

                    if applied_annual_limit and total >= applied_annual_limit:
                        total = applied_annual_limit
                        break

                try:
                    monthly_average_cost = int(round(total / 12))
                except Exception:
                    monthly_average_cost = int(total // 12)

                return {
                    "annual_cost": total,
                    "monthly_average_cost": monthly_average_cost,
                    "is_many_times_applied": is_many_times_applied,
                    "many_times_start_event": many_times_start_event,
                    "events": events,
                }

    # load limits
    with limit_table_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        limit_row = None
        for row in reader:
            if (
                row["system_version"] == system_version
                and row["income_code"] == income_code
                and row["age_group"] == age_group
            ):
                limit_row = row
                break
        if limit_row is None:
            raise ValueError("limit_table.csv に該当データなし")

    try:
        monthly_limit = int(limit_row["monthly_limit"])
    except Exception:
        raise ValueError("limit_table.csv の値が不正です")

    # read optional fields
    try:
        monthly_limit_after_many = int(limit_row.get("monthly_limit_after_many") or 0)
    except Exception:
        monthly_limit_after_many = None

    try:
        annual_limit = int(limit_row.get("annual_limit") or 0)
    except Exception:
        annual_limit = None

    # Determine special handling for 70+ outpatient exceptions and non-tax cases
    income_label = (limit_row.get("income_label") or "")
    outpatient_limit_70 = limit_row.get("outpatient_limit_70plus")

    is_over70_outpatient_special = False
    is_non_tax = False
    # classify based on CSV data (no external guessing)
    if age_group == "over70":
        if outpatient_limit_70 and outpatient_limit_70.strip() != "":
            # if an outpatient-specific limit is present for this row, treat as outpatient special
            is_over70_outpatient_special = True
        # treat labels mentioning 非課税 or 一定所得以下 as non-tax categories
        if "非課税" in income_label or "一定所得以下" in income_label or "低所得" in income_label:
            is_non_tax = True

    events_per_year = floor(52 / prescription_interval_weeks)

    total = 0
    events = []
    is_many_times_applied = False
    many_times_start_event = None

    # For over70 outpatient special handling override limits per spec
    if age_group == "over70" and is_non_tax:
        # L1/L2: monthly cap 8000, no annual cap per spec
        applied_monthly_limit = 8000
        applied_annual_limit = None
        # According to spec, many-times does not apply for non-tax outpatient
        many_times_applicable_globally = False
    elif age_group == "over70" and is_over70_outpatient_special:
        # G: general outpatient special: monthly 18,000, annual 144,000
        applied_monthly_limit = 18000
        applied_annual_limit = 144000
        many_times_applicable_globally = False
    else:
        # Default: use table values
        applied_monthly_limit = monthly_limit
        applied_annual_limit = annual_limit
        many_times_applicable_globally = True

    for i in range(1, events_per_year + 1):
        # Decide whether this event is considered 'many times' reduced limit
        if not many_times_applicable_globally:
            # outpatient special -> never many-times
            applied_limit = applied_monthly_limit
            is_many = False
        else:
            # for normal cases, first 3 events use monthly_limit, from 4th use monthly_limit_after_many if present
            if i <= 3 or not monthly_limit_after_many:
                applied_limit = applied_monthly_limit
                is_many = False
            else:
                # if monthly_limit_after_many is missing, fall back to applied_monthly_limit
                applied_limit = monthly_limit_after_many or applied_monthly_limit
                is_many = True
                if not is_many_times_applied:
                    is_many_times_applied = True
                    many_times_start_event = i

        applied = int(min(self_pay + per_event_extra, applied_limit))
        total += applied
        events.append({
            "event": i,
            "applied_limit": applied_limit,
            "is_many_times": is_many,
            "applied": applied,
        })

        if applied_annual_limit and total >= applied_annual_limit:
            total = applied_annual_limit
            break

    # monthly average: round(annual / 12) then cast to int
    try:
        monthly_average_cost = int(round(total / 12))
    except Exception:
        monthly_average_cost = int(total // 12)

    return {
        "annual_cost": total,
        "monthly_average_cost": monthly_average_cost,
        "is_many_times_applied": is_many_times_applied,
        "many_times_start_event": many_times_start_event,
        "events": events,
    }

    # load limits
    with limit_table_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        limit_row = None
        for row in reader:
            if (
                row["system_version"] == system_version
                and row["income_code"] == income_code
                and row["age_group"] == age_group
            ):
                limit_row = row
                break
        if limit_row is None:
            raise ValueError("limit_table.csv に該当データなし")

    try:
        monthly_limit = int(limit_row["monthly_limit"])
    except Exception:
        raise ValueError("limit_table.csv の値が不正です")

    # read optional fields
    try:
        monthly_limit_after_many = int(limit_row.get("monthly_limit_after_many") or 0)
    except Exception:
        monthly_limit_after_many = None

    try:
        annual_limit = int(limit_row.get("annual_limit") or 0)
    except Exception:
        annual_limit = None

    # Determine special handling for 70+ outpatient exceptions and non-tax cases
    income_label = (limit_row.get("income_label") or "")
    outpatient_limit_70 = limit_row.get("outpatient_limit_70plus")

    is_over70_outpatient_special = False
    is_non_tax = False
    # classify based on CSV data (no external guessing)
    if age_group == "over70":
        if outpatient_limit_70 and outpatient_limit_70.strip() != "":
            # if an outpatient-specific limit is present for this row, treat as outpatient special
            is_over70_outpatient_special = True
        # treat labels mentioning 非課税 or 一定所得以下 as non-tax categories
        if "非課税" in income_label or "一定所得以下" in income_label or "低所得" in income_label:
            is_non_tax = True

    events_per_year = floor(52 / prescription_interval_weeks)

    total = 0
    events = []
    is_many_times_applied = False
    many_times_start_event = None

    # For over70 outpatient special handling override limits per spec
    if age_group == "over70" and is_non_tax:
        # L1/L2: monthly cap 8000, no annual cap per spec
        applied_monthly_limit = 8000
        applied_annual_limit = None
        # According to spec, many-times does not apply for non-tax outpatient
        many_times_applicable_globally = False
    elif age_group == "over70" and is_over70_outpatient_special:
        # G: general outpatient special: monthly 18,000, annual 144,000
        applied_monthly_limit = 18000
        applied_annual_limit = 144000
        many_times_applicable_globally = False
    else:
        # Default: use table values
        applied_monthly_limit = monthly_limit
        applied_annual_limit = annual_limit
        many_times_applicable_globally = True

    for i in range(1, events_per_year + 1):
        # Decide whether this event is considered 'many times' reduced limit
        if not many_times_applicable_globally:
            # outpatient special -> never many-times
            applied_limit = applied_monthly_limit
            is_many = False
        else:
            # for normal cases, first 3 events use monthly_limit, from 4th use monthly_limit_after_many if present
            if i <= 3 or not monthly_limit_after_many:
                applied_limit = applied_monthly_limit
                is_many = False
            else:
                # if monthly_limit_after_many is missing, fall back to applied_monthly_limit
                applied_limit = monthly_limit_after_many or applied_monthly_limit
                is_many = True
                if not is_many_times_applied:
                    is_many_times_applied = True
                    many_times_start_event = i

        applied = int(min(self_pay, applied_limit))
        total += applied
        events.append({
            "event": i,
            "applied_limit": applied_limit,
            "is_many_times": is_many,
        })

        if applied_annual_limit and total >= applied_annual_limit:
            total = applied_annual_limit
            break

    # monthly average: round(annual / 12) then cast to int
    try:
        monthly_average_cost = int(round(total / 12))
    except Exception:
        monthly_average_cost = int(total // 12)

    return {
        "annual_cost": total,
        "monthly_average_cost": monthly_average_cost,
        "is_many_times_applied": is_many_times_applied,
        "many_times_start_event": many_times_start_event,
        "events": events,
    }


def is_many_times_applicable(
    system_version: str,
    income_code: str,
    age_group: str,
    drug_id: str,
    prescription_interval_weeks: int = 12
) -> bool:
    data_dir = Path(__file__).parent.parent / "data"
    drug_price_path = data_dir / "drug_price.csv"
    limit_table_path = data_dir / "limit_table.csv"

    with drug_price_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        drug_row = None
        for row in reader:
            if row["drug_id"] == drug_id:
                drug_row = row
                break
        if drug_row is None:
            raise ValueError("drug_id not found")

    try:
        price_per_unit = int(drug_row["price_per_unit"])
        units_per_12w = int(drug_row["units_per_12w"])
    except Exception:
        raise ValueError("drug_price.csv の値が不正です")

    self_pay = price_per_unit * units_per_12w * 0.3

    # If age_group == over70 and income_code is G/L1/L2, many-times does not apply per spec
    if age_group == "over70" and income_code in ("G", "L1", "L2"):
        return False

    # If caller passed a CSV-style income_code, consult the limit table to see
    # whether this income_code corresponds to an outpatient-special or non-tax row.
    if age_group == "over70":
        with limit_table_path.open(encoding="utf-8") as f:
            reader = csv.DictReader(f)
            lookup_row = None
            for row in reader:
                if (
                    row["system_version"] == system_version
                    and row["income_code"] == income_code
                    and row["age_group"] == age_group
                ):
                    lookup_row = row
                    break

        if lookup_row is not None:
            income_label = (lookup_row.get("income_label") or "")
            outpatient_limit_70 = lookup_row.get("outpatient_limit_70plus")

            if outpatient_limit_70 and outpatient_limit_70.strip() != "":
                return False
            if "非課税" in income_label or "一定所得以下" in income_label or "低所得" in income_label:
                return False

    with limit_table_path.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        limit_row = None
        for row in reader:
            if (
                row["system_version"] == system_version
                and row["income_code"] == income_code
                and row["age_group"] == age_group
            ):
                limit_row = row
                break
        if limit_row is None:
            raise ValueError("limit_table.csv に該当データなし")

    try:
        monthly_limit = int(limit_row["monthly_limit"])
    except Exception:
        raise ValueError("limit_table.csv の値が不正です")

    # If over70 and outpatient special/non-tax, many-times does not apply
    income_label = (limit_row.get("income_label") or "")
    outpatient_limit_70 = limit_row.get("outpatient_limit_70plus")

    if age_group == "over70":
        if outpatient_limit_70 and outpatient_limit_70.strip() != "":
            return False
        if "非課税" in income_label or "一定所得以下" in income_label or "低所得" in income_label:
            return False

    events_per_year = floor(52 / prescription_interval_weeks)
    return (self_pay > monthly_limit) and (events_per_year >= 4)


def simulate_selected_system(
    system_version: str,
    income_code: str,
    age_group: str,
    drug_id: str,
    prescription_interval_weeks: int = 12,
    existing_weekly_cost_yen: int = 0,
    existing_dispense_weeks: int = 12,
    include_existing: bool = False,
    xolair_dose_info: tuple | None = None,
) -> dict:
    """Call simulate_annual_cost for the selected system and return its result.

    This wrapper exists so UI code can call a single function per selected
    system (R7/R8/R9). It calls `simulate_annual_cost` exactly once and
    returns the result unchanged.
    """
    return simulate_annual_cost(
        system_version=system_version,
        income_code=income_code,
        age_group=age_group,
        drug_id=drug_id,
        prescription_interval_weeks=prescription_interval_weeks,
        existing_weekly_cost_yen=existing_weekly_cost_yen,
        existing_dispense_weeks=existing_dispense_weeks,
        include_existing=include_existing,
        xolair_dose_info=xolair_dose_info,
    )


def generate_patient_explanation(
    system_version: str,
    income_code: str,
    age_group: str,
    drug_name: str,
    drug_id: str,
    prescription_interval_weeks: int = 12
) -> str:
    """患者向けの説明文を生成して返す。

    - `simulate_selected_system` を呼び出して計算結果を取得する。
    - 年間・月平均の自己負担額と多数回該当の有無を元に、やさしい口調の日本語文章を返す。
    """
    result = simulate_selected_system(
        system_version=system_version,
        income_code=income_code,
        age_group=age_group,
        drug_id=drug_id,
        prescription_interval_weeks=prescription_interval_weeks,
    )

    annual_cost = int(result.get("annual_cost", 0))
    monthly_average = int(result.get("monthly_average_cost", 0))
    many_applied = bool(result.get("is_many_times_applied", False))

    interval_text = f"{prescription_interval_weeks}週間ごと"

    if many_applied:
        many_text = (
            "高額療養費制度の多数回該当に該当する可能性があります。"
            "この場合、4回目以降の自己負担の扱いが変わることがあります。"
        )
    else:
        many_text = "今回の条件では、多数回該当には該当しない見込みです。"

    explanation = (
        f"{drug_name}を{interval_text}に投与した場合の目安として、\n"
        f"年間の自己負担はおおよそ{annual_cost:,}円、月あたりの平均はおおよそ{monthly_average:,}円です。\n"
        f"{many_text}\n"
        "最終的な適用可否や手続きについては、窓口や担当医師とご確認いただくことをおすすめします。"
    )

    return explanation
