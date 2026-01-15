from src.billing import normalize_burden_rate, apply_monthly_cap


def test_normalize_burden_examples():
    assert normalize_burden_rate(0.3) == 0.3
    assert normalize_burden_rate('0.3') == 0.3
    assert normalize_burden_rate(3) == 0.3
    assert normalize_burden_rate('3') == 0.3
    assert normalize_burden_rate(30) == 0.3
    assert normalize_burden_rate('30') == 0.3


def test_apply_monthly_cap():
    # total 321954, burden 0.3 => patient before cap 96586
    assert apply_monthly_cap(321954, 0.3, 80100) == 80100
    # if cap higher than patient before, return patient_before
    assert apply_monthly_cap(100000, 0.3, 100000) == 30000


def test_many_times_sequence():
    # Simulate 5 consecutive months where raw patient cost exceeds the normal cap.
    normal = 80100
    many = 44400
    burden = 0.3
    over_count = 0
    results = []
    # pick a total_medical_cost that makes patient_raw > normal
    total_medical_cost = 400000
    for i in range(5):
        patient_raw = int(round(total_medical_cost * burden))
        if over_count < 3:
            cap = normal
        else:
            cap = many
        applied = apply_monthly_cap(total_medical_cost, burden, cap)
        if patient_raw > cap:
            over_count += 1
        results.append(applied)

    # first three months should be limited to normal cap, months 4-5 to many cap
    assert results[0] == normal
    assert results[1] == normal
    assert results[2] == normal
    assert results[3] == many
    assert results[4] == many
