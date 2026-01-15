from datetime import date

from src.biologic_schedule import generate_prescription_schedule


def test_dupixent_schedule():
    d0 = date(2026, 1, 1)
    sched = generate_prescription_schedule("dupixent", d0, 1, 1)
    assert len(sched) == 3
    assert sched[0]["order"] == 1 and sched[0]["date"] == d0 and sched[0]["qty"] == 2
    assert sched[1]["order"] == 2 and sched[1]["date"] == date(2026, 1, 15) and sched[1]["qty"] == 1
    # 3rd date = 2nd + (second_qty * 14 days) => 1 * 14 = 14 days -> 2026-01-29
    assert sched[2]["order"] == 3 and sched[2]["date"] == date(2026, 1, 29) and sched[2]["qty"] == 1


def test_nucala_schedule():
    d0 = date(2026, 2, 10)
    sched = generate_prescription_schedule("ヌーカラ", d0, 2, 3)
    assert sched[0]["qty"] == 1
    assert sched[1]["date"] == date(2026, 3, 10)  # +28 days
    # 3rd date = 2nd + (2 * 28 days) => +56 days
    assert sched[2]["date"] == date(2026, 5, 5)


def test_teze_schedule():
    d0 = date(2026, 3, 1)
    sched = generate_prescription_schedule("Tezespia", d0, 1, 1)
    assert sched[0]["qty"] == 1
    assert sched[1]["date"] == date(2026, 3, 29)
    assert sched[2]["date"] == date(2026, 4, 26)


def test_fasenra_schedule():
    d0 = date(2026, 4, 1)
    sched = generate_prescription_schedule("Fasenra", d0, 1, 1)
    assert sched[1]["date"] == date(2026, 5, 27)  # +56 days


def test_invalid_inputs():
    d0 = date(2026, 1, 1)
    try:
        generate_prescription_schedule("unknown", d0, 1, 1)
        assert False, "unsupported drug should raise"
    except ValueError:
        pass

    try:
        generate_prescription_schedule("dupixent", "not-a-date", 1, 1)
        assert False, "invalid date should raise"
    except ValueError:
        pass
