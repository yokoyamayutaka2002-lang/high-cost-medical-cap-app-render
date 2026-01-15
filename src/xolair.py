from pathlib import Path
import csv
from typing import Optional, Tuple

DATA_DIR = Path(__file__).parent.parent / 'data'
XOLAIR_MASTER = DATA_DIR / 'xolair_dose_master.csv'


def _load_master():
    rows = []
    if not XOLAIR_MASTER.exists():
        return rows
    with XOLAIR_MASTER.open(encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for r in reader:
            try:
                rows.append({
                    'drug': r.get('drug'),
                    'ige_min': float(r.get('ige_min') or 0),
                    'ige_max': float(r.get('ige_max') or 0),
                    'weight_min': float(r.get('weight_min') or 0),
                    'weight_max': float(r.get('weight_max') or 0),
                    'interval_weeks': int(r.get('interval_weeks') or 0),
                    'dose_mg': int(r.get('dose_mg') or 0),
                })
            except Exception:
                # skip malformed rows
                continue
    return rows


def get_xolair_dose(ige: float, weight: float) -> Optional[Tuple[int, int]]:
    """
    Return (dose_mg, interval_weeks) for given ige and weight according to
    data/xolair_dose_master.csv. Matching rule: ige_min <= ige < ige_max and
    weight_min <= weight < weight_max. If no match, return None.
    """
    try:
        ige_v = float(ige)
        w_v = float(weight)
    except Exception:
        return None

    rows = _load_master()
    for r in rows:
        if r['ige_min'] <= ige_v < r['ige_max'] and r['weight_min'] <= w_v < r['weight_max']:
            return (r['dose_mg'], r['interval_weeks'])
    return None


def load_xolair_table_for_ui():
    """Return master rows as list of dicts (for embedding into UI)."""
    return _load_master()


# Deterministic dose -> pen mapping (must not be changed)
_DOSE_TO_PEN = {
    150: {'pen_75mg': 0, 'pen_150mg': 1, 'pen_300mg': 0, 'total_mg': 150, 'pen_count': 1},
    225: {'pen_75mg': 0, 'pen_150mg': 2, 'pen_300mg': 0, 'total_mg': 300, 'pen_count': 2},
    300: {'pen_75mg': 0, 'pen_150mg': 0, 'pen_300mg': 1, 'total_mg': 300, 'pen_count': 1},
    375: {'pen_75mg': 1, 'pen_150mg': 0, 'pen_300mg': 1, 'total_mg': 375, 'pen_count': 2},
}


def build_xolair_prescription(dose_mg: int):
    """Return list of ordered dicts describing pen prescription for given dose_mg.

    Returned items use exact Japanese `drug_name` keys matching the biologic price CSV
    and `qty` integer. Items with qty==0 are excluded.

    Examples:
      build_xolair_prescription(150) -> [{"drug_name": "ゾレア皮下注150mgペン", "qty": 1}]
    """
    if dose_mg not in _DOSE_TO_PEN:
        raise ValueError(f"Unsupported dose_mg for Xolair prescription: {dose_mg!r}")
    row = _DOSE_TO_PEN[dose_mg]
    # Exact Japanese product names used in biologic price CSV
    # Map to both `drug_id` and `drug_name` matching `data/drug_price.csv` so
    # price lookups can use either key. drug_id values must match entries in
    # `data/drug_price.csv` (xolair_75, xolair_150, xolair_300).
    items = [
        ("xolair_75", "ゾレア皮下注７５ｍｇペン", int(row.get('pen_75mg') or 0)),
        ("xolair_150", "ゾレア皮下注１５０ｍｇペン", int(row.get('pen_150mg') or 0)),
        ("xolair_300", "ゾレア皮下注３００ｍｇペン", int(row.get('pen_300mg') or 0)),
    ]
    out = []
    for did, name, qty in items:
        if qty and qty > 0:
            out.append({'drug_id': did, 'drug_name': name, 'qty': int(qty)})
    return out


def _get_total_dispensed_mg(dose_mg: int) -> int:
    """Return the total_mg actually dispensed for given dose_mg according to table."""
    if dose_mg not in _DOSE_TO_PEN:
        raise ValueError(f"Unsupported dose_mg for Xolair prescription: {dose_mg!r}")
    return int(_DOSE_TO_PEN[dose_mg]['total_mg'])

