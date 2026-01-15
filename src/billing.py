from typing import Union


def normalize_burden_rate(value: Union[int, float, str]) -> float:
    """Normalize burden representation to a decimal rate (e.g. 0.3).

    Accepted inputs:
    - 0.3 -> 0.3
    - 3   -> interpreted as '3割' -> 0.3
    - 30  -> interpreted as percent -> 0.3
    """
    try:
        v = float(value)
    except Exception:
        raise ValueError("burden value must be numeric")

    if v <= 0:
        raise ValueError("burden must be positive")

    # Interpret common Japanese notations:
    # - 0 < v < 1 : already a decimal fraction (e.g. 0.3)
    # - 1 <= v <= 10 : likely '割' notation (e.g. 3 -> 3割 -> 0.3)
    # - v > 10 : likely percent (e.g. 30 -> 30%) -> 0.3
    if v < 1:
        return v
    if 1 <= v <= 10:
        return v / 10.0
    return v / 100.0


def apply_monthly_cap(total_medical_cost: int, burden_rate: float, monthly_cap: int) -> int:
    """Apply burden and monthly cap, returning patient payable after cap.

    Ensures correct order: burden applied to total_medical_cost first, then cap applied.
    """
    if total_medical_cost < 0:
        raise ValueError("total_medical_cost must be non-negative")
    if not (0 < burden_rate <= 1):
        raise ValueError("burden_rate must be between 0 and 1")
    patient_before = int(round(total_medical_cost * burden_rate))
    return min(patient_before, int(monthly_cap))
