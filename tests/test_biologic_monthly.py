from datetime import date

try:
    import pytest
except Exception:
    pytest = None

from src.biologic_monthly import (
    aggregate_events_by_month,
    merge_monthly_costs,
    integrate_biologic_monthly,
)


def make_event(d: date, gross: int, drug: str = "X") -> dict:
    """簡易ダミーイベント生成ヘルパー"""
    return {
        "date": d,
        "drug": drug,
        "exact_item_name": f"{drug}-dummy",
        "units": 1,
        "unit_price": gross,
        "gross": gross,
    }


def test_aggregate_events_by_month_multiple_in_same_month():
    # 同一月に複数イベント -> gross が合算される
    evs = [
        make_event(date(2025, 4, 1), 1000),
        make_event(date(2025, 4, 15), 2000),
        make_event(date(2025, 5, 3), 500),
    ]

    got = aggregate_events_by_month(evs)
    expected = {"2025-04": 3000, "2025-05": 500}
    assert got == expected, f"aggregate mismatch\nexpected={expected}\n got={got}"


def test_merge_monthly_costs_various_presence():
    base = {"2025-04": 50000, "2025-05": 40000}
    bio = {"2025-04": 300000, "2025-06": 300000}

    merged = merge_monthly_costs(base, bio)
    expected = {"2025-04": 350000, "2025-05": 40000, "2025-06": 300000}
    # dict equality is order-independent
    assert merged == expected, f"merge mismatch\nexpected={expected}\n got={merged}"


def test_integrate_biologic_monthly_full_flow():
    # base has one month; events produce two months (one overlapping)
    base = {"2025-04": 50000}
    evs = [
        make_event(date(2025, 4, 1), 100000, drug="A"),
        make_event(date(2025, 5, 1), 200000, drug="A"),
    ]

    merged = integrate_biologic_monthly(base, evs)
    expected = {"2025-04": 150000, "2025-05": 200000}
    assert merged == expected, f"integrate mismatch\nexpected={expected}\n got={merged}"


if __name__ == "__main__":
    pytest.main(["-q"])
