#!/usr/bin/env python3
"""Join `reports/oral_drug_price_2025-04.csv` with `data/dosing_master.csv`,
compute daily_price_yen = price_yen * dose_per_day, and write the result to
`reports/oral_drug_daily_price_2025-04.csv`.

Columns written: drug_name,strength_mg,price_yen,dose_per_day,daily_price_yen,source_excel,sheet,row,unit
"""
from pathlib import Path
import csv


def read_dosing_master(path: Path):
    dosing = {}
    with path.open('r', encoding='utf-8') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            key = (r['drug_name'], int(r['strength_mg']))
            dosing[key] = {
                'dose_per_day': int(r['dose_per_day']),
                'unit': r.get('unit', ''),
            }
    return dosing


def read_oral_prices(path: Path):
    rows = []
    with path.open('r', encoding='utf-8-sig') as fh:
        reader = csv.DictReader(fh)
        for r in reader:
            try:
                strength = int(float(r['strength_mg']))
            except Exception:
                strength = int(r['strength_mg'])
            try:
                price = float(r['price_yen'])
            except Exception:
                price = None
            rows.append({
                'drug_name': r['drug_name'],
                'strength_mg': strength,
                'price_yen': price,
                'source_excel': r.get('source_excel', ''),
                'sheet': r.get('sheet', ''),
                'row': r.get('row', ''),
            })
    return rows


def main():
    repo_root = Path('.')
    price_csv = repo_root / 'reports' / 'oral_drug_price_2025-04.csv'
    dosing_csv = repo_root / 'data' / 'dosing_master.csv'
    out_csv = repo_root / 'reports' / 'oral_drug_daily_price_2025-04.csv'

    if not price_csv.exists():
        print('ERROR: price CSV not found at', price_csv)
        return
    if not dosing_csv.exists():
        print('ERROR: dosing master not found at', dosing_csv)
        return

    dosing = read_dosing_master(dosing_csv)
    prices = read_oral_prices(price_csv)

    out_rows = []
    for p in prices:
        key = (p['drug_name'], p['strength_mg'])
        d = dosing.get(key)
        if d is None:
            # skip rows without dosing info
            continue
        dose = d['dose_per_day']
        unit = d.get('unit', '')
        price = p['price_yen']
        daily = None if price is None else price * dose
        out_rows.append({
            'drug_name': p['drug_name'],
            'strength_mg': p['strength_mg'],
            'price_yen': price,
            'dose_per_day': dose,
            'daily_price_yen': daily,
            'source_excel': p['source_excel'],
            'sheet': p['sheet'],
            'row': p['row'],
            'unit': unit,
        })

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with out_csv.open('w', encoding='utf-8-sig', newline='') as fh:
        fieldnames = ['drug_name', 'strength_mg', 'price_yen', 'dose_per_day', 'daily_price_yen', 'source_excel', 'sheet', 'row', 'unit']
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        for r in out_rows:
            writer.writerow(r)

    print('WROTE:', out_csv)


if __name__ == '__main__':
    main()
