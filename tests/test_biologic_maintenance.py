from datetime import date

from src.biologic_schedule import generate_prescription_schedule, extend_maintenance_schedule
def test_extend_dupixent_maintenance():
    # initial events
    assert len(maint) >= 1
    assert maint[0]["order"] == 4
def test_nucala_and_teze_maintenance():
    evs_n = generate_prescription_schedule("ヌーカラ", date(2026, 2, 10), 2, 3)
    if maint_n:
        assert maint_n[0]["qty"] == 3
    evs_t = generate_prescription_schedule("Tezespia", date(2026, 3, 1), 1, 1)
    maint_t = extend_maintenance_schedule(evs_t, "teze", end)
def test_fasenra_maintenance_interval_and_qty():
    evs = generate_prescription_schedule("Fasenra", date(2026, 4, 1), 1, 1)
    if maint:
        assert maint[0]["qty"] == 1
def test_end_date_cutoff():
    evs = generate_prescription_schedule("dupixent", date(2026, 1, 1), 1, 1)
from datetime import date

from src.biologic_schedule import generate_prescription_schedule, extend_maintenance_schedule


def test_extend_dupixent_maintenance():
    # initial events
    evs = generate_prescription_schedule("dupixent", date(2026, 1, 1), 1, 1)
    # end_date covers 3 maintenance cycles (84 * 3 = 252 days)
    end = date(2026, 10, 10)
    maint = extend_maintenance_schedule(evs, "dupixent", end)
    # first maintenance should be 3rd_date + 84 days = 2026-04-23
    assert len(maint) >= 1
    assert maint[0]["order"] == 4
    assert maint[0]["date"] == date(2026, 4, 23)


def test_nucala_and_teze_maintenance():
    evs_n = generate_prescription_schedule("ヌーカラ", date(2026, 2, 10), 2, 3)
    end = date(2026, 12, 31)
    maint_n = extend_maintenance_schedule(evs_n, "ヌーカラ", end)
    # nucala maintenance qty should be 3
    if maint_n:
        assert maint_n[0]["qty"] == 3

    evs_t = generate_prescription_schedule("Tezespia", date(2026, 3, 1), 1, 1)
    maint_t = extend_maintenance_schedule(evs_t, "teze", end)
    if maint_t:
        assert maint_t[0]["qty"] == 3


def test_fasenra_maintenance_interval_and_qty():
    evs = generate_prescription_schedule("Fasenra", date(2026, 4, 1), 1, 1)
    end = date(2027, 1, 1)
    maint = extend_maintenance_schedule(evs, "fasenra", end)
    # fasenra interval is 56 days and qty 1
    if maint:
        assert maint[0]["qty"] == 1
        # check interval between first two maint events if present
        if len(maint) > 1:
            delta = (maint[1]["date"] - maint[0]["date"]).days
            assert delta == 56


def test_end_date_cutoff():
    evs = generate_prescription_schedule("dupixent", date(2026, 1, 1), 1, 1)
    # set end_date before first maintenance => no maintenance events
    end = date(2026, 2, 1)
    maint = extend_maintenance_schedule(evs, "dupixent", end)
    assert maint == []
