from datetime import date, timedelta
from src.biologic_schedule import build_prescription_schedule


def xolair_fallback(start_date, qty2, qty3, interval_weeks=None, years=2):
    # replicate the fallback logic in webapp/app.py for xolair
    base_weeks = interval_weeks if interval_weeks and interval_weeks > 0 else 4
    end_date = start_date.replace(year=start_date.year + years)
    presc = []
    order = 1
    cur = start_date
    # Order1
    presc.append({'order': order, 'date': cur, 'qty': 1})
    order += 1
    # Order2
    next_date = cur + timedelta(weeks=base_weeks)
    presc.append({'order': order, 'date': next_date, 'qty': int(qty2)})
    order += 1
    cur = next_date
    # Order3
    third_date = cur + timedelta(weeks=base_weeks)
    presc.append({'order': order, 'date': third_date, 'qty': int(qty3)})
    return presc


def print_schedule(title, presc):
    print(f"--- {title} ---")
    for ev in presc:
        print(f"order={ev['order']}, date={ev['date']}, qty={ev.get('qty')}")
    print()

if __name__ == '__main__':
    sd = date(2026,1,1)
    qty2 = 3
    qty3 = 1

    # Dupixent
    dup = build_prescription_schedule('dupixent', sd, qty2, qty3, sd.replace(year=sd.year+2))
    print_schedule('Dupixent', dup)

    # Tezespia/Tezspire
    teze = build_prescription_schedule('tezspire', sd, qty2, qty3, sd.replace(year=sd.year+2))
    print_schedule('Tezspire', teze)

    # Nucala
    nuc = build_prescription_schedule('nucala', sd, qty2, qty3, sd.replace(year=sd.year+2))
    print_schedule('Nucala', nuc)

    # Xolair fallback (as in app.py)
    xol = xolair_fallback(sd, qty2, qty3, interval_weeks=4)
    print_schedule('Xolair (fallback)', xol)
