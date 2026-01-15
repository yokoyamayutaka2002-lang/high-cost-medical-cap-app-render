from datetime import date

from src.biologic_schedule import build_prescription_schedule


def test_dupixent_schedule_qty_driven():
    start = date(2026, 1, 1)
    end = date(2026, 12, 31)
    # Example from spec: qty2=1, qty3=3
    sched = build_prescription_schedule("dupixent", start, 1, 3, end)
    # expected (with days):
    # 1) 2026-01-01  2本  14日
    # 2) 2026-01-15  1本  14日  (start + 14d)
    # 3) 2026-01-29  3本  42日  (2nd + 1*14d)
    # 4) 2026-03-12  6本  84日  (3rd + 3*14d)
    # 5) 2026-06-04  6本  84日  (maintenance every 84d)
    assert sched[0]["order"] == 1 and sched[0]["date"] == date(2026, 1, 1) and sched[0]["qty"] == 2 and sched[0].get("days") == 14
    assert sched[1]["order"] == 2 and sched[1]["date"] == date(2026, 1, 15) and sched[1]["qty"] == 1 and sched[1].get("days") == 14
    assert sched[2]["order"] == 3 and sched[2]["date"] == date(2026, 1, 29) and sched[2]["qty"] == 3 and sched[2].get("days") == 42
    assert sched[3]["order"] == 4 and sched[3]["date"] == date(2026, 3, 12) and sched[3]["qty"] == 6 and sched[3].get("days") == 84
    assert sched[4]["order"] == 5 and sched[4]["date"] == date(2026, 6, 4) and sched[4]["qty"] == 6 and sched[4].get("days") == 84


def test_nucala_schedule_qty_driven():
    start = date(2026, 1, 1)
    end = date(2026, 12, 31)
    # qty2=3 -> order3 = order2 + (3 * 28 days) = 2026-01-29 + 84 days = 2026-04-23
    sched = build_prescription_schedule("nucala", start, 3, 3, end)
    assert sched[2]["order"] == 3 and sched[2]["date"] == date(2026, 4, 23)
