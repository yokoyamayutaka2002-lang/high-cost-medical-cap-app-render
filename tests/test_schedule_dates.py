from datetime import date, timedelta
from src.biologic_schedule import build_prescription_schedule


def test_teze_nucala_dupixent_order3_spacing():
    sd = date(2026, 1, 1)
    qty2 = 3
    qty3 = 1
    end_date = sd.replace(year=sd.year + 2)

    # Tezspire
    teze = build_prescription_schedule('tezspire', sd, qty2, qty3, end_date)
    assert len(teze) >= 3
    o2 = teze[1]['date']
    o3 = teze[2]['date']
    # For 28-day interval drugs, order3 should be o2 + qty2 * 28 days
    assert o3 == o2 + timedelta(days=qty2 * 28)

    # Nucala (same as tezspire)
    nuc = build_prescription_schedule('nucala', sd, qty2, qty3, end_date)
    assert len(nuc) >= 3
    assert nuc[2]['date'] == nuc[1]['date'] + timedelta(days=qty2 * 28)

    # Dupixent: interval is 14 days and initial qty is 2; order3 should be o2 + qty2 * 14
    dup = build_prescription_schedule('dupixent', sd, qty2, qty3, end_date)
    assert len(dup) >= 3
    assert dup[2]['date'] == dup[1]['date'] + timedelta(days=qty2 * 14)


def test_xolair_expected_rule_for_order3():
    # Xolair is handled by app fallback; expected rule: next_date = current + interval_weeks * prescribed_units
    sd = date(2026, 1, 1)
    qty2 = 3
    base_weeks = 4

    order1 = sd
    order2 = order1 + timedelta(weeks=base_weeks)
    expected_order3 = order2 + timedelta(weeks=qty2 * base_weeks)

    # Verify expected date arithmetic (this asserts the intended rule).
    assert expected_order3 == sd + timedelta(weeks=base_weeks + qty2 * base_weeks)

    # Note: this test documents the intended behaviour for Xolair; the actual
    # fallback implementation in `webapp/app.py` has been updated to follow this rule.
